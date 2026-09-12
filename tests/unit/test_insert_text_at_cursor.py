"""Tests for CodeEditorPanel.insert_text_at_cursor (Change 006 — Bloco I).

Covers the contract documented in code_editor.py:

- Returns ``False`` if no file is bound (anonymous editor).
- Otherwise inserts the text at the cursor, marks the document
  modified, and advances the cursor to the end of the block.
- Does NOT touch the disk; only mutates the in-memory QPlainTextEdit.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QTextCursor

from app.services import FileManager
from app.ui.code_editor import CodeEditorPanel


@pytest.fixture
def editor(tmp_path) -> CodeEditorPanel:
    """Editor bound to a real file on disk (so ``is_dirty`` semantics work)."""
    file_manager = FileManager()
    panel = CodeEditorPanel(file_manager=file_manager)
    target = tmp_path / "sample.py"
    target.write_text("def hello():\n    pass\n", encoding="utf-8")
    panel.set_content(target.read_text(encoding="utf-8"), path=str(target), file_type="python")
    yield panel


def test_returns_false_when_no_file_bound(qapp) -> None:
    """An anonymous editor (no path) rejects insertion."""
    panel = CodeEditorPanel()
    panel.set_content("anything", path=None, file_type=None)
    assert panel.current_path() is None
    assert panel.insert_text_at_cursor("# snippet") is False
    # Content is untouched.
    assert panel.current_content() == "anything"


def test_returns_true_and_inserts_text(editor: CodeEditorPanel) -> None:
    """Happy path: returns True and the new text appears in the editor."""
    # Place cursor at the very end so we have a deterministic insertion point.
    cursor = editor._editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor._editor.setTextCursor(cursor)
    before = editor.current_content()
    inserted = "\n# pasted snippet\nprint('hi')\n"
    ok = editor.insert_text_at_cursor(inserted)
    assert ok is True
    after = editor.current_content()
    assert after == before + inserted
    assert inserted in after


def test_marks_document_as_dirty(editor: CodeEditorPanel) -> None:
    """After insertion, ``is_dirty()`` flips to True."""
    assert editor.is_dirty() is False  # pristine after set_content
    cursor = editor._editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor._editor.setTextCursor(cursor)
    editor.insert_text_at_cursor("# change\n")
    assert editor.is_dirty() is True


def test_inserts_at_cursor_position_not_always_at_end(editor: CodeEditorPanel) -> None:
    """Insertion happens at the cursor, not blindly at EOF."""
    # Move to position 0 (start of "def hello():")
    cursor = editor._editor.textCursor()
    cursor.setPosition(0)
    editor._editor.setTextCursor(cursor)
    # Insert "X " at the very start of the document.
    ok = editor.insert_text_at_cursor("X ")
    assert ok is True
    # First line now begins with "X def hello():".
    assert editor.current_content().startswith("X def hello():")


def test_does_not_write_to_disk(editor: CodeEditorPanel, tmp_path) -> None:
    """insert_text_at_cursor is a pure in-memory operation."""
    target = tmp_path / "sample.py"
    original_on_disk = target.read_text(encoding="utf-8")
    cursor = editor._editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor._editor.setTextCursor(cursor)
    editor.insert_text_at_cursor("# in-memory only\n")
    # File on disk must be unchanged until the user actually saves.
    assert target.read_text(encoding="utf-8") == original_on_disk


def test_consecutive_insertions_append(editor: CodeEditorPanel) -> None:
    """Two insertions in a row land adjacent to each other."""
    cursor = editor._editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor._editor.setTextCursor(cursor)
    editor.insert_text_at_cursor("FIRST")
    editor.insert_text_at_cursor("SECOND")
    # The cursor moves to EndOfBlock after each insert; both inserts
    # therefore land at the end of the file in order.
    assert editor.current_content().endswith("FIRSTSECOND")
