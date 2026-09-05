"""Right column: QWebEngineView rendering markdown with Mermaid support."""

from __future__ import annotations

from html import escape as html_escape

from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

from app.ui.html_template import build_html_template


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
        '<body style="font-family: sans-serif; padding: 24px; color: #888;">'
        '<h1>ArchExplorer</h1>'
        '<p>Click a file in the explorer to analyze its architecture.</p>'
        '</body></html>'
    )

    _LOADING_HTML_TEMPLATE: str = (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<title>ArchExplorer</title></head>'
        '<body style="font-family: sans-serif; padding: 24px; color: #888;">'
        '<h1>Analyzing {label}...</h1>'
        '<p>Qwen 2.5 Coder 3B is generating the analysis.</p>'
        '</body></html>'
    )

    _ERROR_HTML_TEMPLATE: str = (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<title>ArchExplorer</title></head>'
        '<body style="font-family: sans-serif; padding: 24px; color: #c00;">'
        '<h1>Error</h1><pre style="background: #fee; padding: 12px; '
        'border-radius: 4px; white-space: pre-wrap;">'
        '{message}</pre></body></html>'
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

    def show_idle(self) -> None:
        """Reset to the initial 'click a file' state."""
        self.last_markdown = None
        self.last_error = None
        self._web.setHtml(self._IDLE_HTML)

    def show_loading(self, label: str = "file") -> None:
        """Show a 'Analyzing <label>...' placeholder while inference runs."""
        self.last_markdown = None
        self.last_error = None
        self._web.setHtml(self._LOADING_HTML_TEMPLATE.format(label=html_escape(label)))

    def show_markdown(self, text: str) -> None:
        """Render the LLM response as HTML with Mermaid support."""
        self.last_markdown = text
        self.last_error = None
        self._web.setHtml(build_html_template(text))

    def show_error(self, message: str) -> None:
        """Display an error message (no AI call)."""
        self.last_markdown = None
        self.last_error = message
        self._web.setHtml(self._ERROR_HTML_TEMPLATE.format(message=html_escape(message)))
