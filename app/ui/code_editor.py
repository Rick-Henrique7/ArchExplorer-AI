"""Center column: read-only code viewer (no syntax highlighting yet)."""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget


class CodeEditorPanel(QWidget):
    """Read-only file content viewer.

    Syntax highlighting is intentionally out of scope for Change 003 —
    it lands in a dedicated change after the UI integration is stable.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._editor = QPlainTextEdit(self)
        self._editor.setReadOnly(True)
        font = QFont("Consolas, Menlo, monospace", 10)
        self._editor.setFont(font)
        # Show line numbers in the gutter (free with QPlainTextEdit).
        # setLineWrapMode is left at default (no wrap) for code legibility.

        layout.addWidget(self._editor)

    def set_content(self, text: str) -> None:
        """Replace the editor content with ``text``."""
        self._editor.setPlainText(text)

    def clear(self) -> None:
        """Empty the editor."""
        self._editor.clear()
