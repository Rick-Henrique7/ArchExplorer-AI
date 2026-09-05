"""Smoke + structural tests for the main window (Change 003)."""

from __future__ import annotations

from PySide6.QtWidgets import QSplitter

from app.ui.code_editor import CodeEditorPanel
from app.ui.file_explorer import FileExplorerPanel
from app.ui.main_window import MainWindow
from app.ui.visualizer import VisualizerPanel


def test_window_title_is_archexplorer_ai(qapp) -> None:
    window = MainWindow()
    assert window.windowTitle() == "ArchExplorer AI"


def test_window_has_three_real_panels(qapp) -> None:
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


def test_panels_returned_in_left_to_right_order(qapp) -> None:
    window = MainWindow()
    fe, ce, vz = window.panels()
    # The first panel in the splitter should be the file explorer.
    splitter = window.splitter()
    assert splitter.widget(0) is fe
    assert splitter.widget(1) is ce
    assert splitter.widget(2) is vz


def test_file_explorer_file_selected_signal_exists(qapp) -> None:
    """The signal is declared on the class; check the meta-object."""
    from PySide6.QtCore import QMetaObject
    # The signal should be present in the FileExplorerPanel's meta-info
    mo = FileExplorerPanel.staticMetaObject
    # Indices for 'file_selected' — Qt exposes signals via the method table
    found = False
    for i in range(mo.methodCount()):
        m = mo.method(i)
        if bytes(m.name()).decode() == "file_selected":
            found = True
            break
    assert found, "FileExplorerPanel.file_selected signal not declared"


def test_services_default_is_empty_dict(qapp) -> None:
    window = MainWindow()
    assert window.services() == {}


def test_services_returns_copy(qapp) -> None:
    """Mutating the returned dict must not affect the window's state."""
    services = {"ai_engine": "fake"}
    window = MainWindow(services=services)
    snap = window.services()
    snap["mutated"] = True
    assert "mutated" not in window.services()
