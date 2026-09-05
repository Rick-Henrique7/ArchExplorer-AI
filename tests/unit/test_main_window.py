"""Smoke tests for the main window skeleton (Change 001)."""

from __future__ import annotations

from PySide6.QtWidgets import QSplitter

from app.ui.code_editor import CodeEditorPanel
from app.ui.file_explorer import FileExplorerPanel
from app.ui.main_window import MainWindow
from app.ui.visualizer import VisualizerPanel


def test_window_title_is_archexplorer_ai(qapp) -> None:
    window = MainWindow()
    assert window.windowTitle() == "ArchExplorer AI"


def test_window_has_three_panels(qapp) -> None:
    window = MainWindow()
    panels = window.panels()
    assert len(panels) == 3
    fe, ce, vz = panels
    assert isinstance(fe, FileExplorerPanel)
    assert isinstance(ce, CodeEditorPanel)
    assert isinstance(vz, VisualizerPanel)


def test_splitter_has_three_children(qapp) -> None:
    window = MainWindow()
    splitter = window.splitter()
    assert isinstance(splitter, QSplitter)
    assert splitter.count() == 3
    assert splitter.orientation() == splitter.orientation().Horizontal
