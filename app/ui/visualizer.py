"""Right column: QWebEngineView rendering markdown with Mermaid + chat input."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from html import escape as html_escape

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.ui.html_template import build_html_template


# Maximum number of chat turns kept in the LRU history.
_CHAT_HISTORY_MAX: int = 50
# How many recent turns to include in the prompt for context.
_CHAT_PROMPT_CONTEXT_TURNS: int = 5


# Body background + text color per theme. Matches the values used by
# ``build_html_template`` for the markdown render. Keeping them here too
# means the idle/loading/error inline pages look consistent with the
# rendered markdown (no white flash, no low-contrast transition).
_THEME_BG: dict[str, str] = {
    "dark": "#0d1117",
    "light": "#ffffff",
}
_THEME_TEXT: dict[str, str] = {
    "dark": "#c9d1d9",
    "light": "#24292f",
}
_THEME_MUTED: dict[str, str] = {
    "dark": "#8b949e",  # subtle text for the idle/loading messages
    "light": "#57606a",
}
_THEME_ERROR_ACCENT: dict[str, str] = {
    "dark": "#ff7b72",
    "light": "#cf222e",
}
_THEME_ERROR_BG: dict[str, str] = {
    "dark": "#3a1d1d",  # subtle red tint for the error pre block
    "light": "#ffebe9",
}


def _body_style(theme: str) -> str:
    """Inline ``<body>`` style matching the chosen theme.

    Used by the inline HTML for idle / loading / error states so they
    blend visually with the markdown render produced by
    :func:`app.ui.html_template.build_html_template`.
    """
    bg = _THEME_BG.get(theme, _THEME_BG["dark"])
    color = _THEME_TEXT.get(theme, _THEME_TEXT["dark"])
    return f"background-color: {bg}; color: {color};"


@dataclass
class ChatTurn:
    """A single user -> assistant exchange in the chat history.

    ``assistant`` is ``None`` while the AI is still generating; the
    :class:`VisualizerPanel` flips it once the response arrives.
    """

    user: str
    assistant: str | None = None
    file_path: str | None = None
    timestamp: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )


class VisualizerPanel(QWidget):
    """Renders LLM responses as HTML with markdown + Mermaid support.

    Also hosts a chat input area (history dropdown, free-form input,
    Send button) for follow-up Q&A with the AI. The visualizer owns the
    chat state (history, file context) but does **not** call the AI
    itself — it emits :attr:`chat_requested` and the MainWindow spawns
    a worker. The worker calls back via :meth:`add_chat_response`.

    Public API mirrors the :class:`AnalysisWorker` signal contract:

    - :meth:`show_idle` — initial / reset state
    - :meth:`show_loading` — analysis in progress (with spinner)
    - :meth:`show_markdown` — successful response (renders via Mermaid.js)
    - :meth:`show_error` — error message

    Chat-specific:
    - :attr:`chat_history` (list[ChatTurn]) — bounded LRU
    - :meth:`set_file_context` — bind the current file for prompts
    - :meth:`start_chat` — append a pending turn + show loading
    - :meth:`add_chat_response` — mark a turn as answered + re-render
    - :meth:`clear_chat` — reset history + show idle
    - :meth:`build_chat_prompt` — assemble the prompt for the worker
    - :meth:`set_theme` — remember the active theme for internal renders
    """

    chat_requested = Signal(str)  # user message text

    _IDLE_HTML: str = (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<title>ArchExplorer</title></head>'
        "<body style=\"font-family: -apple-system, sans-serif; padding: 24px; "
        "{body_style}\">"
        "<h1>ArchExplorer</h1>"
        "<p>Click a file in the explorer to analyze its architecture.</p>"
        "<p>Ou converse com a IA no campo abaixo.</p>"
        "</body></html>"
    )

    # Inline SVG spinner + CSS animation. The @keyframes rotates the
    # circle so the user sees movement while the LLM is loading.
    _LOADING_HTML_TEMPLATE: str = (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<title>ArchExplorer</title>'
        "<style>"
        "@keyframes spin {{ from {{ transform: rotate(0deg); }} to {{ transform: rotate(360deg); }} }}"
        ".spinner {{ animation: spin 0.9s linear infinite; }}"
        ".spinner .path {{ stroke: {spinner_color}; opacity: 0.25; }}"
        ".spinner .path {{ stroke-dasharray: 90 150; stroke-dashoffset: 0; "
        "stroke-linecap: round; }}"
        ".muted {{ color: {muted_color}; }}"
        "</style></head>"
        "<body style=\"font-family: -apple-system, sans-serif; padding: 24px; "
        "{body_style}\">"
        '<div style="display: flex; align-items: center; gap: 16px;">'
        '<svg class="spinner" viewBox="0 0 50 50" width="40" height="40">'
        '<circle class="path" cx="25" cy="25" r="20" fill="none" '
        'stroke-width="4"></circle></svg>'
        '<h1 style="margin: 0;">Analyzing {label}...</h1>'
        "</div>"
        '<p class="muted">Qwen 2.5 Coder 3B is generating the analysis.</p>'
        "</body></html>"
    )

    _ERROR_HTML_TEMPLATE: str = (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<title>ArchExplorer</title></head>'
        "<body style=\"font-family: -apple-system, sans-serif; padding: 24px; "
        "{body_style}\">"
        '<h1 style="color: {error_accent};">Error</h1>'
        '<pre style="background: {error_bg}; padding: 12px; '
        "border-radius: 4px; white-space: pre-wrap;\">"
        "{message}</pre></body></html>"
    )

    _SPINNER_COLOR: dict[str, str] = {
        # Gray strokes that work on both dark and light backgrounds.
        "dark": "#58a6ff",
        "light": "#0969da",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Public state for tests and downstream consumers.
        self.last_markdown: str | None = None
        self.last_error: str | None = None
        # Chat state (Change 005).
        self.chat_history: list[ChatTurn] = []
        self._file_context_path: str | None = None
        self._file_context_content: str | None = None
        # The active theme — internal renders use this; explicit theme
        # kwargs to show_* always win (backwards compatible).
        self._current_theme: str = "dark"
        self._build_ui()
        self.show_idle()

    # ----- UI construction ---------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Top: web view (markdown render).
        self._web = QWebEngineView(self)
        outer.addWidget(self._web, stretch=1)

        # Bottom: chat panel.
        self._chat_panel = QWidget(self)
        chat_layout = QVBoxLayout(self._chat_panel)
        chat_layout.setContentsMargins(6, 6, 6, 6)
        chat_layout.setSpacing(4)

        # History row: dropdown + clear button.
        history_row = QHBoxLayout()
        history_label = QLabel("Histórico:", self._chat_panel)
        self._history_combo = QComboBox(self._chat_panel)
        self._history_combo.setMinimumWidth(120)
        self._history_combo.addItem("(vazio)", userData=-1)
        self._history_combo.currentIndexChanged.connect(self._on_history_selected)
        history_clear = QPushButton("Limpar", self._chat_panel)
        history_clear.clicked.connect(self.clear_chat)
        history_row.addWidget(history_label)
        history_row.addWidget(self._history_combo, stretch=1)
        history_row.addWidget(history_clear)
        chat_layout.addLayout(history_row)

        # Input row: multi-line QTextEdit + Send.
        input_row = QHBoxLayout()
        self._input = QPlainTextEdit(self._chat_panel)
        self._input.setPlaceholderText(
            "Pergunte à IA... (Enter envia, Shift+Enter quebra linha)"
        )
        self._input.setFixedHeight(70)
        # Enter vs Shift+Enter handling — see eventFilter below.
        self._input.installEventFilter(self)
        # Submit on Ctrl+Enter too (familiar from many chat UIs).
        self._send_button = QPushButton("Enviar", self._chat_panel)
        self._send_button.clicked.connect(self._on_send_clicked)
        input_row.addWidget(self._input, stretch=1)
        input_row.addWidget(self._send_button, stretch=0)
        chat_layout.addLayout(input_row)

        outer.addWidget(self._chat_panel, stretch=0)

    # ----- Event filter: Enter to send, Shift+Enter for newline -------------

    def eventFilter(self, obj: QWidget, event: QEvent) -> bool:  # noqa: N802 — Qt API
        if obj is self._input and event.type() == QEvent.Type.KeyPress:
            assert isinstance(event, QKeyEvent)
            # Enter / Return without Shift sends the message.
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    # Shift+Enter: insert a newline (default behaviour).
                    return False
                self._on_send_clicked()
                return True  # consume — do not insert a newline
        return super().eventFilter(obj, event)

    # ----- Public state transitions -----------------------------------------

    def show_idle(self, theme: str = "dark") -> None:
        """Reset to the initial 'click a file' state."""
        self.last_markdown = None
        self.last_error = None
        self._web.setHtml(self._render_idle(theme))

    def show_loading(self, label: str = "file", theme: str = "dark") -> None:
        """Show a 'Analyzing <label>...' placeholder with spinner while inference runs."""
        self.last_markdown = None
        self.last_error = None
        self._web.setHtml(self._render_loading(label, theme))

    def show_markdown(self, text: str, theme: str = "dark") -> None:
        """Render the LLM response as HTML with Mermaid support."""
        self.last_markdown = text
        self.last_error = None
        self._web.setHtml(build_html_template(text, theme=theme))

    def show_error(self, message: str, theme: str = "dark") -> None:
        """Display an error message (no AI call)."""
        self.last_markdown = None
        self.last_error = message
        self._web.setHtml(self._render_error(message, theme))

    def set_theme(self, theme: str) -> None:
        """Remember the active theme for chat renders (called by MainWindow)."""
        self._current_theme = theme

    # ----- Chat API ----------------------------------------------------------

    def set_file_context(self, path: str | None, content: str | None) -> None:
        """Bind the currently-open file so chat prompts can reference it."""
        self._file_context_path = path
        self._file_context_content = content

    def clear_chat(self) -> None:
        """Drop the entire chat history and reset to the idle view."""
        self.chat_history = []
        self._refresh_history_combo()
        self.show_idle(theme=self._current_theme)

    def start_chat(self, user_msg: str) -> None:
        """Queue a chat turn and signal the MainWindow to call the AI.

        Appends a pending :class:`ChatTurn` to history, updates the
        history dropdown, shows the loading state, and emits
        :attr:`chat_requested` so the MainWindow can spawn a worker.
        """
        text = user_msg.strip()
        if not text:
            return
        turn = ChatTurn(user=text, file_path=self._file_context_path)
        self._append_chat_turn(turn)
        # Show the user message immediately, with a "(waiting...)" hint.
        self._render_chat_history()
        # Then overlay the spinner.
        self.show_loading("chat response", theme=self._current_theme)
        self.chat_requested.emit(text)

    def add_chat_response(self, user_msg: str, response: str) -> None:
        """Attach ``response`` to the most recent pending turn matching ``user_msg``.

        Called by the chat worker's ``finished`` signal. Re-renders the
        chat history in the web view. If no matching pending turn is
        found (e.g. the user cleared the chat in between), the response
        is dropped silently — the chat history is the source of truth.
        """
        for turn in reversed(self.chat_history):
            if turn.user == user_msg and turn.assistant is None:
                turn.assistant = response
                break
        self._render_chat_history()

    def build_chat_prompt(self, user_msg: str) -> str:
        """Assemble the prompt for the AI, including file context and recent history.

        Format::

            [Contexto: arquivo <basename>]
            ```
            <file content>
            ```

            Histórico recente:
            User: <u1>
            Assistant: <a1>
            ...

            User: <new message>
            Assistant:
        """
        parts: list[str] = []
        if self._file_context_path is not None and self._file_context_content is not None:
            basename = os.path.basename(self._file_context_path)
            parts.append(f"Contexto: arquivo {basename}")
            parts.append(f"```\n{self._file_context_content}\n```")
        # Recent history (last N turns with answers).
        recent = [t for t in self.chat_history if t.assistant is not None][
            -_CHAT_PROMPT_CONTEXT_TURNS:
        ]
        if recent:
            lines: list[str] = ["Histórico recente:"]
            for t in recent:
                lines.append(f"User: {t.user}")
                lines.append(f"Assistant: {t.assistant}")
            parts.append("\n".join(lines))
        parts.append(f"User: {user_msg}\nAssistant:")
        return "\n\n".join(parts)

    # ----- Internal helpers --------------------------------------------------

    def _append_chat_turn(self, turn: ChatTurn) -> None:
        """Append a turn, enforcing the LRU cap."""
        if len(self.chat_history) >= _CHAT_HISTORY_MAX:
            self.chat_history.pop(0)
        self.chat_history.append(turn)
        self._refresh_history_combo()

    def _refresh_history_combo(self) -> None:
        """Rebuild the history dropdown entries from ``self.chat_history``."""
        self._history_combo.blockSignals(True)
        self._history_combo.clear()
        for i, turn in enumerate(self.chat_history):
            label = turn.user
            if len(label) > 60:
                label = label[:57] + "..."
            self._history_combo.addItem(f"{i + 1}. {label}", userData=i)
        self._history_combo.blockSignals(False)
        # Keep "(vazio)" / latest item as the displayed entry without
        # firing the change handler repeatedly.
        if self.chat_history:
            self._history_combo.setCurrentIndex(len(self.chat_history) - 1)
        else:
            self._history_combo.addItem("(vazio)", userData=-1)
            self._history_combo.setCurrentIndex(0)

    def _on_history_selected(self, index: int) -> None:
        """When the user picks an old turn from the dropdown, show that turn."""
        if index < 0 or index >= len(self.chat_history):
            return
        turn = self.chat_history[index]
        # Render the single turn as a tiny markdown snippet so the user
        # can review the past exchange without scrolling.
        if turn.assistant is None:
            md = f"**Você:** {turn.user}\n\n_(aguardando resposta...)_"
        else:
            md = f"**Você:** {turn.user}\n\n---\n\n{turn.assistant}"
        self.show_markdown(md, theme=self._current_theme)

    def _on_send_clicked(self) -> None:
        """Send-button (or Enter) handler: pull the text and queue a turn."""
        text = self._input.toPlainText()
        # Strip only the trailing newline Qt sometimes leaves in.
        if text.endswith("\n"):
            text = text[:-1]
        text = text.strip()
        if not text:
            return
        self._input.clear()
        self.start_chat(text)

    def _render_chat_history(self) -> None:
        """Render the entire chat history in the web view as markdown."""
        if not self.chat_history:
            self.show_idle(theme=self._current_theme)
            return
        sections: list[str] = ["# Chat com a IA"]
        for turn in self.chat_history:
            sections.append(f"**Você:** {turn.user}")
            if turn.assistant is None:
                sections.append("_(aguardando resposta...)_")
            else:
                sections.append(turn.assistant)
        self.show_markdown("\n\n---\n\n".join(sections), theme=self._current_theme)

    # ----- Internal HTML builders --------------------------------------------

    def _render_idle(self, theme: str) -> str:
        return self._IDLE_HTML.format(body_style=_body_style(theme))

    def _render_loading(self, label: str, theme: str) -> str:
        return self._LOADING_HTML_TEMPLATE.format(
            label=html_escape(label),
            body_style=_body_style(theme),
            spinner_color=self._SPINNER_COLOR.get(theme, self._SPINNER_COLOR["dark"]),
            muted_color=_THEME_MUTED.get(theme, _THEME_MUTED["dark"]),
        )

    def _render_error(self, message: str, theme: str) -> str:
        return self._ERROR_HTML_TEMPLATE.format(
            message=html_escape(message),
            body_style=_body_style(theme),
            error_accent=_THEME_ERROR_ACCENT.get(theme, _THEME_ERROR_ACCENT["dark"]),
            error_bg=_THEME_ERROR_BG.get(theme, _THEME_ERROR_BG["dark"]),
        )
