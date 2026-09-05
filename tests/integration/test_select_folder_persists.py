"""Integration test: Select Folder persists root_dir to QSettings."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings

from app.ui.main_window import MainWindow


def test_select_folder_persists_to_qsettings(
    qapp, tmp_path, monkeypatch
) -> None:
    """Picking a new root via the toolbar writes the path to QSettings."""
    from app.ui import file_explorer as explorer_mod

    target = tmp_path / "my_workspace"
    target.mkdir()

    monkeypatch.setattr(
        explorer_mod.QFileDialog,
        "getExistingDirectory",
        lambda *a, **kw: str(target),
    )

    window = MainWindow()
    # Start from a different root, then "select" the new one.
    window._file_explorer.set_root(tmp_path)
    window._file_explorer._on_select_folder()
    assert window._file_explorer.root() == target

    # The QSettings store should now hold the new root.
    settings = QSettings()
    assert settings.value("workspace/root_dir", "") == str(target.resolve())


def test_new_window_restores_persisted_root(qapp, tmp_path, monkeypatch) -> None:
    """A second MainWindow instance reads the persisted root on construction."""
    from app.ui import file_explorer as explorer_mod

    target = tmp_path / "restored"
    target.mkdir()

    # First window: pick the target.
    monkeypatch.setattr(
        explorer_mod.QFileDialog,
        "getExistingDirectory",
        lambda *a, **kw: str(target),
    )
    window1 = MainWindow()
    window1._file_explorer._on_select_folder()
    assert window1._file_explorer.root() == target

    # Second window: should read QSettings and start at the same root.
    window2 = MainWindow()
    assert window2._file_explorer.root() == target


def test_root_changed_signal_persists_on_direct_set_root(
    qapp, tmp_path
) -> None:
    """Calling set_root() directly (without the dialog) also persists."""
    target = tmp_path / "via_set_root"
    target.mkdir()
    window = MainWindow()
    window._file_explorer.set_root(target)
    settings = QSettings()
    assert settings.value("workspace/root_dir", "") == str(target.resolve())
