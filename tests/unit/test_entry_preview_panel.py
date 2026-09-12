"""Tests for EntryPreviewPanel — single entry render (Change 006 — Bloco H)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services import CatalogoService, Entry
from app.ui.entry_preview_panel import EntryPreviewPanel, _render_entry_markdown


def _make_entry(**overrides) -> Entry:
    """Convenience builder for an Entry with sensible defaults."""
    base = dict(
        id=1,
        title="LRU cache",
        code="class LRU:\n    pass\n",
        language="python",
        description="A least-recently-used cache.",
        category="data-structures",
        origin_path="src/cache.py",
        origin_line=42,
        is_public=False,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        tags=("cache", "lru"),
    )
    base.update(overrides)
    return Entry(**base)


@pytest.fixture
def service(tmp_path) -> CatalogoService:
    svc = CatalogoService(db_path=tmp_path / "test.db")
    svc.create_entry(
        title="Memoization",
        code="def memo(f): pass",
        language="python",
        category="patterns",
        tags=("memo",),
    )
    return svc


@pytest.fixture
def panel(qapp) -> EntryPreviewPanel:
    return EntryPreviewPanel()


# ----- Markdown helper (pure) --------------------------------------------

def test_render_markdown_includes_title() -> None:
    md = _render_entry_markdown(_make_entry(title="My pattern"))
    assert "# My pattern" in md


def test_render_markdown_includes_description() -> None:
    md = _render_entry_markdown(_make_entry(description="Use when X"))
    assert "## Descrição" in md
    assert "Use when X" in md


def test_render_markdown_includes_code_block() -> None:
    md = _render_entry_markdown(_make_entry(language="python", code="x = 1\n"))
    assert "```python" in md
    assert "x = 1" in md


def test_render_markdown_omits_description_when_empty() -> None:
    md = _render_entry_markdown(_make_entry(description=None))
    assert "## Descrição" not in md


def test_render_markdown_includes_tags_as_inline_code() -> None:
    md = _render_entry_markdown(_make_entry(tags=("alpha", "beta")))
    assert "`alpha`" in md
    assert "`beta`" in md


def test_render_markdown_includes_origin_path_and_line() -> None:
    md = _render_entry_markdown(_make_entry(origin_path="src/x.py", origin_line=12))
    assert "src/x.py:12" in md


def test_render_markdown_handles_pipe_in_category() -> None:
    """Pipes inside values must be escaped so the table stays valid."""
    md = _render_entry_markdown(_make_entry(category="a|b"))
    # The escaped pipe appears as \| inside the cell.
    assert "a\\|b" in md


def test_render_markdown_mentions_public_flag() -> None:
    md_public = _render_entry_markdown(_make_entry(is_public=True))
    assert "Pública" in md_public


# ----- Panel behavior ---------------------------------------------------

def test_initial_state_is_empty(panel: EntryPreviewPanel) -> None:
    """A freshly-built panel has no current entry and disabled buttons."""
    assert panel.current_entry() is None
    assert panel._insert_button.isEnabled() is False
    assert panel._edit_button.isEnabled() is False
    assert panel._delete_button.isEnabled() is False
    assert panel._title_label.text() == ""


def test_show_entry_enables_action_buttons(panel: EntryPreviewPanel) -> None:
    entry = _make_entry()
    panel.show_entry(entry)
    assert panel.current_entry() is entry
    assert panel._insert_button.isEnabled() is True
    assert panel._edit_button.isEnabled() is True
    assert panel._delete_button.isEnabled() is True
    assert panel._title_label.text() == entry.title


def test_show_entry_sets_title_label(panel: EntryPreviewPanel) -> None:
    panel.show_entry(_make_entry(title="Specific title"))
    assert panel._title_label.text() == "Specific title"


def test_clear_resets_panel(panel: EntryPreviewPanel) -> None:
    panel.show_entry(_make_entry())
    panel.clear()
    assert panel.current_entry() is None
    assert panel._title_label.text() == ""
    assert panel._insert_button.isEnabled() is False
    assert panel._edit_button.isEnabled() is False


def test_insert_button_emits_with_id(panel: EntryPreviewPanel) -> None:
    received: list[int] = []
    panel.insert_into_editor.connect(received.append)
    panel.show_entry(_make_entry(id=7))
    panel._insert_button.click()
    assert received == [7]


def test_edit_button_emits_with_id(panel: EntryPreviewPanel) -> None:
    received: list[int] = []
    panel.edit_entry.connect(received.append)
    panel.show_entry(_make_entry(id=11))
    panel._edit_button.click()
    assert received == [11]


def test_delete_button_emits_with_id(panel: EntryPreviewPanel) -> None:
    received: list[int] = []
    panel.delete_entry.connect(received.append)
    panel.show_entry(_make_entry(id=99))
    panel._delete_button.click()
    assert received == [99]


def test_buttons_disabled_when_no_entry_does_not_emit(panel: EntryPreviewPanel) -> None:
    """Clicking an action with no entry loaded is a no-op (buttons off)."""
    received: list[int] = []
    panel.insert_into_editor.connect(received.append)
    # Even if we force-click, the slot short-circuits on _current_entry.
    panel._on_insert_clicked()
    assert received == []


def test_show_entry_by_id_returns_true_for_known_id(
    qapp, service: CatalogoService
) -> None:
    panel = EntryPreviewPanel(service=service)
    # Pick the first entry the service has.
    entries = service.list_entries()
    target_id = entries[0].id
    assert panel.show_entry_by_id(target_id) is True
    assert panel.current_entry() is not None
    assert panel.current_entry().id == target_id


def test_show_entry_by_id_returns_false_for_unknown_id(
    qapp, service: CatalogoService
) -> None:
    panel = EntryPreviewPanel(service=service)
    assert panel.show_entry_by_id(999_999) is False
    assert panel.current_entry() is None


def test_show_entry_by_id_without_service_returns_false(qapp) -> None:
    panel = EntryPreviewPanel()
    assert panel.show_entry_by_id(1) is False


def test_set_theme_re_renders_current_entry(panel: EntryPreviewPanel) -> None:
    """Theme change re-renders the markdown so colors follow the theme."""
    panel.show_entry(_make_entry())
    # No assertion on the HTML output (Qt WebEngine is hard to assert
    # on), but we verify the call doesn't raise and the entry stays set.
    panel.set_theme("light")
    assert panel.current_entry() is not None
    panel.set_theme("dark")
    assert panel.current_entry() is not None
