"""Main window — three horizontal panels (File Explorer / Editor / Visualizer)."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.ui.code_editor import CodeEditorPanel
from app.ui.file_explorer import FileExplorerPanel
from app.ui.visualizer import VisualizerPanel


class MainWindow(QMainWindow):
    """ArchExplorer AI main window.

    Hosts three resizable panels in a horizontal ``QSplitter``. Future
    changes inject concrete services through the ``services`` dict
    (Dependency Inversion — see ``docs/guidelines/diretriz.md``).

    Parameters
    ----------
    services:
        Optional map of injected services. The skeleton ignores it; later
        changes consume it (e.g. ``services["file_manager"]``,
        ``services["ai_engine"]``).
    parent:
        Optional parent widget for Qt ownership semantics.
    """

    WINDOW_TITLE = "ArchExplorer AI"
    DEFAULT_SIZE = (1100, 700)
    # Relative widths of the three columns: 25% / 45% / 30%
    SPLITTER_STRETCH = (25, 45, 30)

    def __init__(
        self,
        services: dict[str, Any] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._services: dict[str, Any] = services if services is not None else {}
        self._build_ui()

    def _build_ui(self) -> None:
        self.setWindowTitle(self.WINDOW_TITLE)
        self.resize(*self.DEFAULT_SIZE)

        self._file_explorer = FileExplorerPanel(self)
        self._code_editor = CodeEditorPanel(self)
        self._visualizer = VisualizerPanel(self)

        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._splitter.addWidget(self._file_explorer)
        self._splitter.addWidget(self._code_editor)
        self._splitter.addWidget(self._visualizer)
        self._splitter.setStretchFactor(0, self.SPLITTER_STRETCH[0])
        self._splitter.setStretchFactor(1, self.SPLITTER_STRETCH[1])
        self._splitter.setStretchFactor(2, self.SPLITTER_STRETCH[2])
        self._splitter.setChildrenCollapsible(False)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._splitter)
        self.setCentralWidget(central)

    # ----- Public API used by tests and future controllers -----

    def panels(
        self,
    ) -> tuple[FileExplorerPanel, CodeEditorPanel, VisualizerPanel]:
        """Return the three panels in left-to-right order."""
        return (self._file_explorer, self._code_editor, self._visualizer)

    def splitter(self) -> QSplitter:
        """Return the horizontal splitter hosting the three panels."""
        return self._splitter

    def services(self) -> dict[str, Any]:
        """Return the injected services map (read-only view)."""
        return dict(self._services)
