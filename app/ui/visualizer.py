"""Right column: QWebEngineView rendering markdown with Mermaid support."""

from __future__ import annotations

from html import escape as html_escape

from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

from app.ui.html_template import build_html_template


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


class VisualizerPanel(QWidget):
    """Renders LLM responses as HTML with markdown + Mermaid support.

    Public API mirrors the :class:`AnalysisWorker` signal contract:

    - :meth:`show_idle` — initial / reset state
    - :meth:`show_loading` — analysis in progress
    - :meth:`show_markdown` — successful response (renders via Mermaid.js)
    - :meth:`show_error` — error message

    The panel exposes :attr:`last_markdown` and :attr:`last_error` for
    inspection by tests and downstream UI (status bar, history, etc.).
    """

    _IDLE_HTML: str = (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<title>ArchExplorer</title></head>'
        "<body style=\"font-family: -apple-system, sans-serif; padding: 24px; "
        "{body_style}\">"
        "<h1>ArchExplorer</h1>"
        "<p>Click a file in the explorer to analyze its architecture.</p>"
        "</body></html>"
    )

    _LOADING_HTML_TEMPLATE: str = (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<title>ArchExplorer</title></head>'
        "<body style=\"font-family: -apple-system, sans-serif; padding: 24px; "
        "{body_style}\">"
        "<h1>Analyzing {label}...</h1>"
        "<p>Qwen 2.5 Coder 3B is generating the analysis.</p>"
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

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Public state for tests and downstream consumers.
        self.last_markdown: str | None = None
        self.last_error: str | None = None
        self._build_ui()
        self.show_idle()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._web = QWebEngineView(self)
        layout.addWidget(self._web)

    # ----- Public state transitions -----------------------------------------

    def show_idle(self, theme: str = "dark") -> None:
        """Reset to the initial 'click a file' state."""
        self.last_markdown = None
        self.last_error = None
        self._web.setHtml(self._render_idle(theme))

    def show_loading(self, label: str = "file", theme: str = "dark") -> None:
        """Show a 'Analyzing <label>...' placeholder while inference runs."""
        self.last_markdown = None
        self.last_error = None
        self._web.setHtml(self._render_loading(label, theme))

    def show_markdown(self, text: str, theme: str = "dark") -> None:
        """Render the LLM response as HTML with Mermaid support.

        Parameters
        ----------
        text:
            Markdown response from the LLM.
        theme:
            ``"dark"`` or ``"light"`` — picks the matching github-markdown-css
            variant and the matching body background/foreground colors so
            the page is readable in both app themes.
        """
        self.last_markdown = text
        self.last_error = None
        self._web.setHtml(build_html_template(text, theme=theme))

    def show_error(self, message: str, theme: str = "dark") -> None:
        """Display an error message (no AI call)."""
        self.last_markdown = None
        self.last_error = message
        self._web.setHtml(self._render_error(message, theme))

    # ----- Internal HTML builders --------------------------------------------

    def _render_idle(self, theme: str) -> str:
        return self._IDLE_HTML.format(body_style=_body_style(theme))

    def _render_loading(self, label: str, theme: str) -> str:
        return self._LOADING_HTML_TEMPLATE.format(
            label=html_escape(label),
            body_style=_body_style(theme),
        )

    def _render_error(self, message: str, theme: str) -> str:
        return self._ERROR_HTML_TEMPLATE.format(
            message=html_escape(message),
            body_style=_body_style(theme),
            error_accent=_THEME_ERROR_ACCENT.get(theme, _THEME_ERROR_ACCENT["dark"]),
            error_bg=_THEME_ERROR_BG.get(theme, _THEME_ERROR_BG["dark"]),
        )
