"""Main window — three horizontal panels (File Explorer / Editor / Visualizer)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QThreadPool, Slot
from PySide6.QtWidgets import (
    QMainWindow,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.ui.analysis_worker import AnalysisWorker
from app.ui.code_editor import CodeEditorPanel
from app.ui.file_explorer import FileExplorerPanel
from app.ui.file_inspector import inspect_file
from app.ui.visualizer import VisualizerPanel


class MainWindow(QMainWindow):
    """ArchExplorer AI main window.

    Hosts three resizable panels in a horizontal ``QSplitter``:

    - :class:`FileExplorerPanel` — real file tree (``QTreeView``)
    - :class:`CodeEditorPanel` — read-only file viewer
    - :class:`VisualizerPanel` — ``QWebEngineView`` rendering LLM responses

    The MainWindow accepts an optional ``services`` dict for dependency
    injection (per ``docs/guidelines/diretriz.md`` — DIP). Required key:
    ``"ai_engine"``. Missing services produce a clear error in the
    visualizer instead of a crash.
    """

    WINDOW_TITLE: str = "ArchExplorer AI"
    DEFAULT_SIZE: tuple[int, int] = (1100, 700)
    SPLITTER_STRETCH: tuple[int, int, int] = (25, 45, 30)

    def __init__(
        self,
        services: dict[str, Any] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._services: dict[str, Any] = services if services is not None else {}
        self._build_ui()
        self._wire()

    def _build_ui(self) -> None:
        self.setWindowTitle(self.WINDOW_TITLE)
        self.resize(*self.DEFAULT_SIZE)

        cwd = Path(os.getcwd())
        self._file_explorer = FileExplorerPanel(root=cwd, parent=self)
        self._code_editor = CodeEditorPanel(self)
        self._visualizer = VisualizerPanel(self)

        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._splitter.addWidget(self._file_explorer)
        self._splitter.addWidget(self._code_editor)
        self._splitter.addWidget(self._visualizer)
        for i, stretch in enumerate(self.SPLITTER_STRETCH):
            self._splitter.setStretchFactor(i, stretch)
        self._splitter.setChildrenCollapsible(False)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._splitter)
        self.setCentralWidget(central)

    def _wire(self) -> None:
        self._file_explorer.file_selected.connect(self._on_file_selected)

    @Slot(str)
    def _on_file_selected(self, path: str) -> None:
        """Handle a file click from the explorer.

        1. Validate the file (inspect_file) — bail early with an error if
           extension/size/encoding reject it.
        2. Update the code editor synchronously with the file content.
        3. Show a 'loading' placeholder in the visualizer.
        4. Dispatch an :class:`AnalysisWorker` to the QThreadPool.
        5. Worker signals update the visualizer when finished / failed.
        """
        result = inspect_file(path)
        if not result.ok:
            self._code_editor.clear()
            self._visualizer.show_error(result.error_message)
            return

        # Synchronous UI update — editor always shows the file content
        # even if the AI call is still running.
        self._code_editor.set_content(result.content)
        self._visualizer.show_loading(Path(path).name)

        engine = self._services.get("ai_engine")
        if engine is None:
            self._visualizer.show_error(
                "No AI engine configured (services['ai_engine'] missing).",
            )
            return

        worker = AnalysisWorker(
            ai_engine=engine,
            code_content=result.content,
            file_type=result.file_type,
            file_label=Path(path).name,
        )
        worker.signals.finished.connect(self._visualizer.show_markdown)
        worker.signals.failed.connect(self._visualizer.show_error)
        QThreadPool.globalInstance().start(worker)

    # ----- Public API used by tests and future controllers ------------------

    def panels(
        self,
    ) -> tuple[FileExplorerPanel, CodeEditorPanel, VisualizerPanel]:
        """Return the three panels in left-to-right order."""
        return (self._file_explorer, self._code_editor, self._visualizer)

    def splitter(self) -> QSplitter:
        """Return the horizontal splitter hosting the three panels."""
        return self._splitter

    def services(self) -> dict[str, Any]:
        """Return a copy of the injected services map."""
        return dict(self._services)
