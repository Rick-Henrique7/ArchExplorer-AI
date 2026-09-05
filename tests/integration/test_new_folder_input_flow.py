"""Integration test: +Folder button -> inline input -> commit -> folder on disk."""

from __future__ import annotations

import pytest

from app.ui.main_window import MainWindow


def test_new_folder_full_flow_creates_directory(qapp, tmp_path) -> None:
    """+Folder reveals the input; typing + Enter creates the folder."""
    window = MainWindow()
    # Re-root the explorer to tmp_path so the new folder lands there.
    window._file_explorer.set_root(tmp_path)
    assert window._file_explorer.root() == tmp_path

    # 1. Click +Folder — input row becomes visible.
    window._file_explorer._on_new_folder()
    assert window._file_explorer._new_folder_input_row.isHidden() is False

    # 2. Type a name — type into the QLineEdit.
    window._file_explorer._new_folder_input.setText("brand_new_folder")

    # 3. Press Enter — QLineEdit.returnPressed commits.
    window._file_explorer._commit_new_folder()

    # 4. Folder exists on disk.
    assert (tmp_path / "brand_new_folder").is_dir()


def test_new_folder_empty_name_does_not_create(qapp, tmp_path) -> None:
    window = MainWindow()
    window._file_explorer.set_root(tmp_path)
    window._file_explorer._on_new_folder()
    window._file_explorer._new_folder_input.setText("")
    window._file_explorer._commit_new_folder()
    # No folder created.
    assert list(tmp_path.iterdir()) == []


def test_new_folder_collision_keeps_input_visible_with_error(
    qapp, tmp_path
) -> None:
    """When the folder already exists, the input stays visible with a tooltip."""
    (tmp_path / "dup").mkdir()
    window = MainWindow()
    window._file_explorer.set_root(tmp_path)

    window._file_explorer._on_new_folder()
    window._file_explorer._new_folder_input.setText("dup")
    window._file_explorer._commit_new_folder()

    # Input still visible (user can edit and retry).
    assert window._file_explorer._new_folder_input_row.isHidden() is False
    # Tooltip carries the error message.
    assert "already exists" in window._file_explorer._new_folder_input.toolTip()
