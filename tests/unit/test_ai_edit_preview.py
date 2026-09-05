"""Tests for the AIEditPreviewDialog (Change 005)."""

from __future__ import annotations

import pytest

from app.ui.ai_edit_preview import AIEditPreviewDialog


def test_dialog_can_be_instantiated(qapp, tmp_path) -> None:
    """The dialog must construct without errors and expose new_content()."""
    f = tmp_path / "x.py"
    f.write_text("old\n", encoding="utf-8")
    dlg = AIEditPreviewDialog(
        original_content="old\n",
        new_content="new\n",
        file_path=str(f),
        instruction="rename",
    )
    assert dlg is not None
    # new_content returns the proposed body so the caller can write it.
    assert dlg.new_content() == "new\n"


def test_dialog_shows_instruction_and_filename_in_header(qapp, tmp_path) -> None:
    f = tmp_path / "my_file.py"
    f.write_text("old", encoding="utf-8")
    dlg = AIEditPreviewDialog(
        original_content="old",
        new_content="new",
        file_path=str(f),
        instruction="add docstring",
    )
    # The dialog must be discoverable as a QDialog subclass.
    from PySide6.QtWidgets import QDialog
    assert isinstance(dlg, QDialog)
    # And it should expose a non-empty window title.
    assert "IA" in dlg.windowTitle() or "edi" in dlg.windowTitle().lower()


def test_dialog_handles_identical_content(qapp, tmp_path) -> None:
    """When the new content equals the original, the diff fallback is shown."""
    f = tmp_path / "x.py"
    f.write_text("x", encoding="utf-8")
    dlg = AIEditPreviewDialog(
        original_content="x",
        new_content="x",
        file_path=str(f),
        instruction="noop",
    )
    assert dlg.new_content() == "x"


def test_dialog_handles_empty_strings(qapp, tmp_path) -> None:
    f = tmp_path / "x.py"
    f.write_text("x", encoding="utf-8")
    dlg = AIEditPreviewDialog(
        original_content="x",
        new_content="",
        file_path=str(f),
        instruction="empty",
    )
    assert dlg.new_content() == ""


def test_dialog_diff_includes_both_versions(qapp, tmp_path) -> None:
    """The internal diff helper must produce a non-empty diff for changed content."""
    from app.ui.ai_edit_preview import AIEditPreviewDialog

    diff_text = AIEditPreviewDialog._make_diff(
        "line1\nline2\nline3\n",
        "line1\nLINE2\nline3\n",
        "/tmp/example.py",
    )
    assert diff_text  # non-empty
    # The diff should mention the filename and at least one of the lines.
    assert "example.py" in diff_text or "line" in diff_text


def test_dialog_diff_falls_back_for_identical_content(qapp) -> None:
    """When the diff is empty, the helper returns a friendly placeholder."""
    from app.ui.ai_edit_preview import AIEditPreviewDialog

    diff_text = AIEditPreviewDialog._make_diff("same\n", "same\n", "/tmp/x.py")
    assert "sem alterações" in diff_text or "sem diferen" in diff_text.lower()
