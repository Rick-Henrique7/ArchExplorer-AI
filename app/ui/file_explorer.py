"""Left column: real file tree with click-to-select signal."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtWidgets import QFileSystemModel, QTreeView, QVBoxLayout, QWidget


class FileExplorerPanel(QWidget):
    """File tree rooted at ``root`` (default: current working directory).

    Emits :attr:`file_selected` (carrying the absolute path) when the user
    clicks a file (directories are navigated natively by the tree and do
    not emit). The actual content validation (extension, size, encoding)
    happens in :func:`app.ui.file_inspector.inspect_file` on the consumer
    side (typically :class:`app.ui.main_window.MainWindow`).
    """

    file_selected = Signal(str)  # absolute path

    def __init__(
        self,
        root: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._build_ui(root or Path(os.getcwd()))

    def _build_ui(self, root: Path) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._model = QFileSystemModel(self)
        self._model.setRootPath(str(root))

        self._view = QTreeView(self)
        self._view.setModel(self._model)
        self._view.setRootIndex(self._model.index(str(root)))
        self._view.setHeaderHidden(True)
        # Only show the name column; hide size/type/modified for compactness.
        for col in range(1, 4):
            self._view.hideColumn(col)
        self._view.clicked.connect(self._on_clicked)

        layout.addWidget(self._view)

    def _on_clicked(self, index: QModelIndex) -> None:
        # Only emit for files; directories are handled by the tree itself.
        if not self._model.isDir(index):
            path = self._model.filePath(index)
            self.file_selected.emit(path)

    def root(self) -> Path:
        """Return the current root path of the tree."""
        return Path(self._model.rootPath())
