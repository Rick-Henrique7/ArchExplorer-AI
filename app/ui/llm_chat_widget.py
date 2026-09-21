"""LLM chat widget — runs an agent loop with Tool Use (Change 007 — Bloco G).

A drop-in ``QWidget`` the MainWindow can plug into the visualizer
column (or anywhere). Sends the user's prompt to the LLM with the
file-system tools attached; the agent loop executes tool calls,
feeds results back, and shows the transcript inline.

Why this exists separate from :class:`VisualizerPanel`: the latter
is about analyzing files via the local AI engine + chat; this one
is about delegating filesystem mutations to the LLM. Two
different intents, two different widgets, kept understandable.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject, QThreadPool, Qt, Signal, Slot
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services import (
    FILE_TOOLS,
    FileSystemAgent,
    LiteLlmAdapter,
    run_agent_loop,
)

_logger = logging.getLogger(__name__)


class _AgentWorker(QObject):
    """Background runner for :func:`run_agent_loop`.

    We use ``QObject.moveToThread`` semantics in spirit but execute
    synchronously inside ``QThreadPool.start`` — the actual loop is
    CPU-light (HTTP-bound), so a dedicated QThread is overkill. A
    short ``run_agent_loop`` runs in milliseconds on Ollama.
    """

    def __init__(
        self,
        *,
        adapter: LiteLlmAdapter,
        agent: FileSystemAgent,
        user_prompt: str,
        system_prompt: str,
        max_iterations: int = 10,
    ) -> None:
        super().__init__()
        self._adapter = adapter
        self._agent = agent
        self._user_prompt = user_prompt
        self._system_prompt = system_prompt
        self._max_iterations = max_iterations

    @Slot()
    def run(self) -> None:
        """One pass; the loop is small enough that we don't need a thread."""
        try:
            final, transcript = run_agent_loop(
                adapter=self._adapter,
                user_prompt=self._user_prompt,
                tool_executor=self._agent,
                system_prompt=self._system_prompt,
                tools=FILE_TOOLS,
                max_iterations=self._max_iterations,
            )
        except Exception as exc:  # noqa: BLE001
            _logger.exception("agent loop crashed")
            self.finished_with_error.emit(str(exc))
            return
        self.finished_with_response.emit(final, transcript)

    # Signals — must be declared on a QObject so the worker can emit.
    finished_with_response = Signal(str, list)   # final_content, transcript
    finished_with_error = Signal(str)             # error_message


class LlmChatWidget(QWidget):
    """Mini chat panel with Tool Use.

    Usage:

        widget = LlmChatWidget(adapter=adapter, agent=agent)
        widget.append_user_message("Cria a pasta src e o arquivo main.py")
        widget.run_agent()  # or wire run_requested to your own button.

    Public API:
    - :attr:`run_requested` — emitted when the user presses Enter or
      clicks "Executar".
    - :meth:`set_adapter` / :meth:`set_agent` — swap implementations.
    """

    run_requested = Signal()

    def __init__(
        self,
        adapter: LiteLlmAdapter | None = None,
        agent: FileSystemAgent | None = None,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._adapter = adapter
        self._agent = agent
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Transcript area.
        self._transcript = QPlainTextEdit(self)
        self._transcript.setReadOnly(True)
        font = QFont("Consolas, Menlo, monospace", 9)
        self._transcript.setFont(font)
        layout.addWidget(self._transcript, stretch=1)

        # Input row.
        input_row = QHBoxLayout()
        self._input = QLineEdit(self)
        self._input.setPlaceholderText(
            "Pergunte à IA — ou peça para criar arquivos…",
        )
        self._input.returnPressed.connect(self._on_run)
        input_row.addWidget(self._input, stretch=1)
        self._run_button = QPushButton("Executar", self)
        self._run_button.clicked.connect(self._on_run)
        self._run_button.setEnabled(self._adapter is not None)
        input_row.addWidget(self._run_button)
        layout.addLayout(input_row)

        # Status.
        self._status = QLabel("", self)
        self._status.setContentsMargins(2, 0, 2, 2)
        layout.addWidget(self._status)

    # ----- Public API -----------------------------------------------------

    def set_adapter(self, adapter: LiteLlmAdapter | None) -> None:
        self._adapter = adapter
        self._run_button.setEnabled(adapter is not None)

    def set_agent(self, agent: FileSystemAgent | None) -> None:
        self._agent = agent

    def append_user_message(self, text: str) -> None:
        """Append a user prompt to the transcript (call before run_agent)."""
        self._append_html(f'<div style="color:#4a90e2"><b>Você:</b> {text}</div>')

    def run_agent(self) -> None:
        """Send the current input box text to the agent loop."""
        self._on_run()

    def run_agent_sync(self) -> None:
        """Synchronous variant used by tests; bypasses the QThreadPool."""
        # Same prep as _on_run, but we don't queue to the pool.
        text = self._input.text().strip()
        if not text:
            return
        if self._adapter is None or self._agent is None:
            self._set_status("Adapter ou FileSystemAgent não configurados.")
            return
        self.append_user_message(text)
        self._input.clear()
        self._run_button.setEnabled(False)
        self._set_status("Executando...")
        worker = _AgentWorker(
            adapter=self._adapter,
            agent=self._agent,
            user_prompt=text,
            system_prompt=(
                "Você é um assistente que pode usar ferramentas para "
                "ler e criar arquivos no diretório de trabalho. "
                "Responda em PT-BR."
            ),
        )
        worker.finished_with_response.connect(self._on_response)
        worker.finished_with_error.connect(self._on_error)
        worker.run()  # synchronous — for tests only

    def clear_transcript(self) -> None:
        self._transcript.clear()

    # ----- Internal -------------------------------------------------------

    def _on_run(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        if self._adapter is None or self._agent is None:
            self._set_status("Adapter ou FileSystemAgent não configurados.")
            return
        self.append_user_message(text)
        self._input.clear()
        self._run_button.setEnabled(False)
        self._set_status("Executando...")

        worker = _AgentWorker(
            adapter=self._adapter,
            agent=self._agent,
            user_prompt=text,
            system_prompt=(
                "Você é um assistente que pode usar ferramentas para "
                "ler e criar arquivos no diretório de trabalho. "
                "Responda em PT-BR."
            ),
        )
        worker.finished_with_response.connect(self._on_response)
        worker.finished_with_error.connect(self._on_error)
        # Run synchronously inside the global thread pool. The
        # worker is tiny; threading matters more for the SAT solver
        # and LLM HTTP, both of which are off-thread already.
        QThreadPool.globalInstance().start(worker.run)

    @Slot(str, list)
    def _on_response(self, final: str, transcript: list) -> None:
        """Render the transcript (tool calls + assistant text)."""
        for message in transcript:
            role = message.get("role", "")
            if role == "system":
                continue
            if role == "user":
                self._append_html(
                    f'<div style="color:#4a90e2"><b>Você:</b> '
                    f'{_html_escape(message.get("content", ""))}</div>'
                )
            elif role == "assistant":
                content = message.get("content") or ""
                tool_calls = message.get("tool_calls") or []
                if content:
                    self._append_html(
                        f'<div style="color:#2c2c2c"><b>IA:</b> '
                        f'{_html_escape(content)}</div>'
                    )
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    name = fn.get("name", "?")
                    args = fn.get("arguments", "{}")
                    self._append_html(
                        f'<div style="color:#a55a3a"><b>tool:</b> '
                        f'{_html_escape(name)}({_html_escape(args)})</div>'
                    )
            elif role == "tool":
                self._append_html(
                    f'<div style="color:#5a5a5a"><b>→</b> '
                    f'{_html_escape(message.get("content", ""))}</div>'
                )
        self._run_button.setEnabled(True)
        self._set_status("Pronto.")

    @Slot(str)
    def _on_error(self, message: str) -> None:
        self._append_html(f'<div style="color:#d0021b"><b>Erro:</b> '
                          f'{_html_escape(message)}</div>')
        self._run_button.setEnabled(True)
        self._set_status("Erro.")

    # ----- UI helpers -----------------------------------------------------

    def _append_html(self, html: str) -> None:
        # ``appendHtml`` keeps the existing block format; we use it to
        # color-code roles.
        cursor = self._transcript.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._transcript.setTextCursor(cursor)
        self._transcript.appendHtml(html)

    def _set_status(self, text: str) -> None:
        self._status.setText(text)


def _html_escape(value: str) -> str:
    """Tiny HTML escaper for transcript rendering."""
    return (
        value.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
    )
