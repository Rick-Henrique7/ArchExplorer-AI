"""Left column: file explorer panel (placeholder for Change 001)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class FileExplorerPanel(QWidget):
    """Placeholder for the file explorer column.

    Real implementation (QTreeView + QFileSystemModel + context menu) lands
    in the change that introduces the FileManager service.
    """

    PLACEHOLDER_TEXT = "File Explorer"

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
