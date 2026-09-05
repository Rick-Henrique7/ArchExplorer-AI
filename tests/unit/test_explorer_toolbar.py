"""Tests for FileExplorerPanel's toolbar (Select Folder / +Folder / Refresh)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services import FileOperationError
from app.ui.file_explorer import FileExplorerPanel


# ----- Toolbar presence ----------------------------------------------------


def test_explorer_has_three_action_buttons(qapp, tmp_path: Path) -> None:
    panel = FileExplorerPanel(root=tmp_path)
    assert hasattr(panel, "_select_button")
    assert hasattr(panel, "_new_folder_button")
    assert hasattr(panel, "_refresh_button")
    assert panel._select_button.text() == "Select Folder"
    assert panel._new_folder_button.text() == "+Folder"
    assert panel._refresh_button.text() == "Refresh"


# ----- Select Folder -------------------------------------------------------


def test_select_folder_reroots_tree(qapp, tmp_path: Path, monkeypatch) -> None:
    """When the user picks a folder, set_root() is called with that path."""
    target = tmp_path / "elsewhere"
    target.mkdir()

    from app.ui import file_explorer as explorer_mod

    monkeypatch.setattr(
        explorer_mod.QFileDialog,
        "getExistingDirectory",
        lambda *a, **kw: str(target),
    )

    panel = FileExplorerPanel(root=tmp_path)
    assert panel.root() == tmp_path
    panel._on_select_folder()
    assert panel.root() == target


def test_select_folder_emits_root_changed(qapp, tmp_path, monkeypatch) -> None:
    target = tmp_path / "elsewhere"
    target.mkdir()
    from app.ui import file_explorer as explorer_mod

    monkeypatch.setattr(
        explorer_mod.QFileDialog,
        "getExistingDirectory",
        lambda *a, **kw: str(target),
    )
    panel = FileExplorerPanel(root=tmp_path)
    captured: list[str] = []
    panel.root_changed.connect(captured.append)
    panel._on_select_folder()
    assert len(captured) == 1
    assert Path(captured[0]) == target.resolve()


def test_select_folder_cancel_does_nothing(qapp, tmp_path, monkeypatch) -> None:
    """An empty selection (user clicked Cancel) must not change the root."""
    from app.ui import file_explorer as explorer_mod

    monkeypatch.setattr(
        explorer_mod.QFileDialog, "getExistingDirectory", lambda *a, **kw: ""
    )
    panel = FileExplorerPanel(root=tmp_path)
    captured: list[str] = []
    panel.root_changed.connect(captured.append)
    panel._on_select_folder()
    assert captured == []
    assert panel.root() == tmp_path


# ----- set_root ------------------------------------------------------------


def test_set_root_changes_model_root(qapp, tmp_path: Path) -> None:
    target = tmp_path / "other"
    target.mkdir()
    panel = FileExplorerPanel(root=tmp_path)
    panel.set_root(target)
    assert panel.root() == target


def test_set_root_ignores_nonexistent(qapp, tmp_path: Path) -> None:
    panel = FileExplorerPanel(root=tmp_path)
    panel.set_root(tmp_path / "ghost")  # does not exist
    assert panel.root() == tmp_path


# ----- +Folder (inline new folder) -----------------------------------------


def test_new_folder_button_reveals_input_row(qapp, tmp_path: Path) -> None:
    panel = FileExplorerPanel(root=tmp_path)
    # Initially hidden.
    assert panel._new_folder_input_row.isHidden() is True
    panel._on_new_folder()
    assert panel._new_folder_input_row.isHidden() is False


def test_commit_new_folder_creates_folder(qapp, tmp_path: Path) -> None:
    panel = FileExplorerPanel(root=tmp_path)
    panel._on_new_folder()
    panel._new_folder_input.setText("my_subfolder")
    panel._commit_new_folder()
    assert (tmp_path / "my_subfolder").is_dir()
    # Input row is hidden again on success.
    assert panel._new_folder_input_row.isHidden() is True


def test_commit_new_folder_ignores_empty_name(qapp, tmp_path: Path) -> None:
    panel = FileExplorerPanel(root=tmp_path)
    panel._on_new_folder()
    panel._new_folder_input.setText("   ")
    panel._commit_new_folder()
    # No folder created, input row hidden.
    assert not (tmp_path / "any_folder").exists()
    assert panel._new_folder_input_row.isHidden() is True


def test_commit_new_folder_shows_error_tooltip_on_collision(
    qapp, tmp_path: Path
) -> None:
    panel = FileExplorerPanel(root=tmp_path)
    (tmp_path / "dup").mkdir()
    panel._on_new_folder()
    panel._new_folder_input.setText("dup")
    panel._commit_new_folder()
    # Tooltip carries the error; input stays visible so the user can edit.
    assert panel._new_folder_input_row.isHidden() is False
    assert "already exists" in panel._new_folder_input.toolTip()


# ----- Refresh -------------------------------------------------------------


def test_refresh_reapplies_root_path(qapp, tmp_path: Path) -> None:
    """PySide6's QFileSystemModel doesn't expose refresh(); we re-apply rootPath."""
    panel = FileExplorerPanel(root=tmp_path)
    called: list[str] = []
    # Spy on setRootPath to confirm the refresh pathway is hit.
    original = panel._model.setRootPath
    def _spy(path: str) -> str:
        called.append(path)
        return original(path)
    panel._model.setRootPath = _spy  # type: ignore[method-assign]
    panel._on_refresh()
    assert called == [str(tmp_path)]
