"""Tests for EntryEditorDialog — form for create/edit (Change 006 — Bloco G)."""

from __future__ import annotations

import pytest

from app.services import Entry
from app.ui.entry_editor_dialog import EntryDraft, EntryEditorDialog


@pytest.fixture
def dialog(qapp) -> EntryEditorDialog:
    return EntryEditorDialog(mode=EntryEditorDialog.MODE_CREATE)


@pytest.fixture
def sample_entry() -> Entry:
    """A pre-built Entry to populate the form in edit mode."""
    return Entry(
        id=42,
        title="LRU cache",
        code="class LRU:\n    pass\n",
        language="python",
        description="Least-recently-used cache",
        category="data-structures",
        origin_path="src/cache.py",
        origin_line=12,
        is_public=False,
        tags=("cache", "lru"),
    )


def _fill_create_form(
    dialog: EntryEditorDialog,
    *,
    title: str = "Memoization",
    language: str = "python",
    category: str = "patterns",
    tags: str = "memo, decorator, python",
    code: str = "def memo(f):\n    cache = {}\n    return f\n",
    description: str = "Caches function results by args.",
    origin_path: str = "",
    origin_line: str = "",
    is_public: bool = False,
) -> None:
    """Type into the dialog's fields via the same widget APIs the UI uses."""
    dialog._title_input.setText(title)
    dialog._language_combo.setCurrentText(language)
    # Always assign category (even ""), so we can test the "blank"
    # path. ``if category:`` would skip the assignment and leave the
    # combo at its default ("patterns").
    dialog._category_combo.setCurrentText(category)
    dialog._tags_input.setText(tags)
    dialog._code_input.setPlainText(code)
    if description:
        dialog._desc_input.setPlainText(description)
    dialog._origin_path_input.setText(origin_path)
    dialog._origin_line_input.setText(origin_line)
    dialog._public_checkbox.setChecked(is_public)


def test_mode_create_starts_empty(dialog: EntryEditorDialog) -> None:
    """A fresh create-mode dialog has empty fields and no draft."""
    assert dialog.mode == EntryEditorDialog.MODE_CREATE
    assert dialog._title_input.text() == ""
    assert dialog._code_input.toPlainText() == ""
    assert dialog.get_draft() is None


def test_accept_in_create_returns_draft(dialog: EntryEditorDialog) -> None:
    """Filling the form and accepting returns a populated EntryDraft."""
    _fill_create_form(dialog)
    dialog._on_accept()
    draft = dialog.get_draft()
    assert draft is not None
    assert isinstance(draft, EntryDraft)
    assert draft.title == "Memoization"
    assert draft.language == "python"
    assert draft.category == "patterns"
    assert draft.tags == ("memo", "decorator", "python")  # normalized, input order
    assert "def memo" in draft.code
    assert draft.description == "Caches function results by args."
    assert draft.is_public is False


def test_accept_rejects_missing_title(dialog: EntryEditorDialog) -> None:
    """An empty title blocks accept() and surfaces a validation error."""
    _fill_create_form(dialog, title="", code="x = 1")
    dialog._on_accept()
    assert dialog.get_draft() is None
    assert dialog.validation_error is not None
    assert "Título" in dialog.validation_error


def test_accept_rejects_missing_code(dialog: EntryEditorDialog) -> None:
    """An empty code blocks accept()."""
    _fill_create_form(dialog, title="Title", code="")
    dialog._on_accept()
    assert dialog.get_draft() is None
    assert dialog.validation_error is not None
    assert "Código" in dialog.validation_error


def test_accept_rejects_missing_language(dialog: EntryEditorDialog) -> None:
    """An empty language blocks accept()."""
    _fill_create_form(dialog, language="")
    dialog._on_accept()
    assert dialog.get_draft() is None
    assert dialog.validation_error is not None
    assert "Linguagem" in dialog.validation_error


def test_accept_rejects_non_integer_origin_line(dialog: EntryEditorDialog) -> None:
    """A non-numeric origin line blocks accept()."""
    _fill_create_form(dialog, origin_path="src/x.py", origin_line="not_a_number")
    dialog._on_accept()
    assert dialog.get_draft() is None
    assert dialog.validation_error is not None
    assert "inteiro" in dialog.validation_error.lower() or "linha" in dialog.validation_error.lower()


def test_accept_rejects_origin_line_below_one(dialog: EntryEditorDialog) -> None:
    """origin_line < 1 is rejected."""
    _fill_create_form(dialog, origin_path="src/x.py", origin_line="0")
    dialog._on_accept()
    assert dialog.get_draft() is None
    assert dialog.validation_error is not None


def test_accept_normalizes_tags(dialog: EntryEditorDialog) -> None:
    """Tags are normalized (lowercase, dedup, sort) on accept."""
    _fill_create_form(dialog, tags="PYTHON, python, Python, , memo")
    dialog._on_accept()
    draft = dialog.get_draft()
    assert draft is not None
    assert draft.tags == ("python", "memo")  # dedup, lowercase, input order


def test_accept_with_public_checkbox(dialog: EntryEditorDialog) -> None:
    """is_public flag is captured from the checkbox."""
    _fill_create_form(dialog, is_public=True)
    dialog._on_accept()
    draft = dialog.get_draft()
    assert draft is not None
    assert draft.is_public is True


def test_edit_mode_populates_fields(qapp, sample_entry: Entry) -> None:
    """An edit-mode dialog prefills from the existing Entry."""
    dialog = EntryEditorDialog(mode=EntryEditorDialog.MODE_EDIT, entry=sample_entry)
    assert dialog.mode == EntryEditorDialog.MODE_EDIT
    assert dialog._title_input.text() == "LRU cache"
    assert dialog._language_combo.currentText() == "python"
    assert dialog._category_combo.currentText() == "data-structures"
    assert "cache" in dialog._tags_input.text()
    assert "lru" in dialog._tags_input.text()
    assert "class LRU" in dialog._code_input.toPlainText()
    assert dialog._origin_path_input.text() == "src/cache.py"
    assert dialog._origin_line_input.text() == "12"
    assert dialog._public_checkbox.isChecked() is False


def test_edit_mode_accept_returns_draft(qapp, sample_entry: Entry) -> None:
    """Edit-mode accept returns a fresh draft reflecting any edits."""
    dialog = EntryEditorDialog(mode=EntryEditorDialog.MODE_EDIT, entry=sample_entry)
    dialog._title_input.setText("LRU cache (updated)")
    dialog._on_accept()
    draft = dialog.get_draft()
    assert draft is not None
    assert draft.title == "LRU cache (updated)"
    # Untouched fields carry through.
    assert draft.language == "python"
    assert draft.category == "data-structures"


def test_accept_with_blank_description_yields_none(dialog: EntryEditorDialog) -> None:
    """Description of all-whitespace is normalized to None."""
    _fill_create_form(dialog, description="   \n  ")
    dialog._on_accept()
    draft = dialog.get_draft()
    assert draft is not None
    assert draft.description is None


def test_accept_with_blank_category_yields_none(dialog: EntryEditorDialog) -> None:
    """An empty category box becomes None in the draft."""
    _fill_create_form(dialog, category="")
    dialog._on_accept()
    draft = dialog.get_draft()
    assert draft is not None
    assert draft.category is None


def test_draft_origin_line_is_int_when_valid(dialog: EntryEditorDialog) -> None:
    """A valid origin line is parsed into an int."""
    _fill_create_form(dialog, origin_path="src/x.py", origin_line="42")
    dialog._on_accept()
    draft = dialog.get_draft()
    assert draft is not None
    assert draft.origin_line == 42
    assert draft.origin_path == "src/x.py"
