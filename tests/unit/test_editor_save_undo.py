"""Tests for CodeEditorPanel's editable + Save / Edit-with-AI flow (Change 005)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services import FileManager, FileOperationError
from app.ui.code_editor import CodeEditorPanel


# ----- Basic state ---------------------------------------------------------


def test_editor_is_editable_by_default(qapp) -> None:
    """Change 005: the editor is no longer read-only."""
    panel = CodeEditorPanel()
    assert panel._editor.isReadOnly() is False


def test_initial_path_is_none(qapp) -> None:
    panel = CodeEditorPanel()
    assert panel.current_path() is None
    assert panel.current_content() == ""


def test_set_content_stores_text(qapp) -> None:
    panel = CodeEditorPanel()
    panel.set_content("hello\n")
    assert panel.current_content() == "hello\n"


def test_set_content_with_path_stores_path(qapp) -> None:
    panel = CodeEditorPanel()
    panel.set_content("x = 1\n", path="/tmp/x.py")
    assert panel.current_path() == "/tmp/x.py"


def test_clear_resets_path_and_text(qapp) -> None:
    panel = CodeEditorPanel()
    panel.set_content("x", path="/tmp/x.py")
    panel.clear()
    assert panel.current_path() is None
    assert panel.current_content() == ""


# ----- Save button state ---------------------------------------------------


def test_save_button_disabled_when_no_file(qapp) -> None:
    panel = CodeEditorPanel()
    assert panel._save_button.isEnabled() is False


def test_save_button_enabled_when_file_bound(qapp) -> None:
    panel = CodeEditorPanel()
    panel.set_content("x", path="/tmp/x.py")
    assert panel._save_button.isEnabled() is True


def test_ai_edit_button_disabled_when_no_file(qapp) -> None:
    panel = CodeEditorPanel()
    assert panel._ai_edit_button.isEnabled() is False


def test_ai_edit_button_enabled_when_file_bound(qapp) -> None:
    panel = CodeEditorPanel()
    panel.set_content("x", path="/tmp/x.py")
    assert panel._ai_edit_button.isEnabled() is True


# ----- Save flow -----------------------------------------------------------


def test_save_writes_file_to_disk(qapp, tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("old", encoding="utf-8")
    fm = FileManager()
    panel = CodeEditorPanel(file_manager=fm)
    panel.set_content("new content", path=str(f))
    panel._on_save_clicked()
    assert f.read_text(encoding="utf-8") == "new content"


def test_save_clears_dirty_flag(qapp, tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("old", encoding="utf-8")
    panel = CodeEditorPanel()
    panel.set_content("new", path=str(f))
    # Mark the document as dirty (simulating user editing).
    panel._editor.document().setModified(True)
    assert panel.is_dirty() is True
    panel._on_save_clicked()
    assert panel.is_dirty() is False


def test_save_emits_save_failed_on_write_error(qapp, tmp_path: Path) -> None:
    """When the file_manager raises, the panel emits save_failed with the message."""
    f = tmp_path / "x.py"
    f.write_text("old", encoding="utf-8")
    fm = FileManager()

    panel = CodeEditorPanel(file_manager=fm)
    panel.set_content("new", path=str(f))

    captured: list[str] = []
    panel.save_failed.connect(captured.append)

    # Force write_file to fail by binding to a path whose parent does not exist.
    missing = tmp_path / "no_such_dir" / "x.py"
    panel.set_content("new", path=str(missing))
    panel._on_save_clicked()
    assert len(captured) == 1
    assert "does not exist" in captured[0] or "Cannot write" in captured[0]


def test_save_noop_when_no_file_bound(qapp) -> None:
    """Save with no file bound must not raise or write anything."""
    panel = CodeEditorPanel()
    captured: list[str] = []
    panel.save_failed.connect(captured.append)
    panel._on_save_clicked()
    assert captured == []


# ----- Edit-with-AI signal -------------------------------------------------


def test_ai_edit_requested_signal_carries_path_and_instruction(
    qapp, tmp_path: Path, monkeypatch
) -> None:
    """The signal payload is (path, instruction) so MainWindow can drive the worker."""
    f = tmp_path / "x.py"
    f.write_text("old", encoding="utf-8")
    panel = CodeEditorPanel()
    panel.set_content("old", path=str(f))

    # Stub QInputDialog.getText to return ('add docstring', True) immediately.
    from app.ui import code_editor as editor_mod

    monkeypatch.setattr(
        editor_mod.QInputDialog,
        "getText",
        lambda *a, **kw: ("add docstring", True),
    )

    captured: list[tuple[str, str]] = []
    panel.ai_edit_requested.connect(lambda p, i: captured.append((p, i)))
    panel._on_ai_edit_clicked()
    assert captured == [(str(f), "add docstring")]


def test_ai_edit_noop_when_user_cancels_dialog(qapp, tmp_path, monkeypatch) -> None:
    f = tmp_path / "x.py"
    f.write_text("old", encoding="utf-8")
    panel = CodeEditorPanel()
    panel.set_content("old", path=str(f))

    from app.ui import code_editor as editor_mod

    monkeypatch.setattr(
        editor_mod.QInputDialog, "getText", lambda *a, **kw: ("", False)
    )
    captured: list[tuple[str, str]] = []
    panel.ai_edit_requested.connect(lambda p, i: captured.append((p, i)))
    panel._on_ai_edit_clicked()
    assert captured == []


def test_ai_edit_noop_when_instruction_is_empty(qapp, tmp_path, monkeypatch) -> None:
    f = tmp_path / "x.py"
    f.write_text("old", encoding="utf-8")
    panel = CodeEditorPanel()
    panel.set_content("old", path=str(f))

    from app.ui import code_editor as editor_mod

    monkeypatch.setattr(
        editor_mod.QInputDialog, "getText", lambda *a, **kw: ("   ", True)
    )
    captured: list[tuple[str, str]] = []
    panel.ai_edit_requested.connect(lambda p, i: captured.append((p, i)))
    panel._on_ai_edit_clicked()
    assert captured == []


def test_ai_edit_noop_when_no_file_bound(qapp, monkeypatch) -> None:
    panel = CodeEditorPanel()
    from app.ui import code_editor as editor_mod

    monkeypatch.setattr(
        editor_mod.QInputDialog, "getText", lambda *a, **kw: ("x", True)
    )
    captured: list[tuple[str, str]] = []
    panel.ai_edit_requested.connect(lambda p, i: captured.append((p, i)))
    panel._on_ai_edit_clicked()
    assert captured == []
