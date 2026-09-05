"""Right column: diagram / visualizer panel (placeholder for Change 001)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class VisualizerPanel(QWidget):
    """Placeholder for the diagram visualizer column.

    Real implementation (QWebEngineView rendering Mermaid.js) lands in
    the change that introduces the DiagramGenerator service. The web
    engine pulls Chromium and is intentionally kept out of the skeleton.
    """

    PLACEHOLDER_TEXT = "Visualizer"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel(self.PLACEHOLDER_TEXT, self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = label.font()
        font.setPointSize(14)
        label.setFont(font)

        layout.addWidget(label)
        self._label = label
