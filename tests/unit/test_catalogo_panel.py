"""Tests for CatalogoPanel — the catalog UI (Change 006 — Bloco F).

Covers:

- Initial state, filter combo population, list rendering
- Search debounce + filtering
- Selection change -> entry_selected signal
- Action buttons emit their signals only when something is selected
- Filters (category / language) trim the list
- ``refresh()`` re-queries the service
"""

from __future__ import annotations

import pytest

from app.services import CatalogoService, Entry
from app.ui.catalogo_panel import CatalogoListModel, CatalogoPanel


@pytest.fixture
def service(tmp_path) -> CatalogoService:
    """A populated catalog with 3 entries spanning 2 languages and 2 categories."""
    svc = CatalogoService(db_path=tmp_path / "test.db")
    svc.create_entry(
        title="LRU cache",
        code="class LRU: pass",
        language="python",
        category="data-structures",
        tags=("cache", "lru"),
        description="A least-recently-used cache",
    )
    svc.create_entry(
        title="Memoization decorator",
        code="def memo(f): pass",
        language="python",
        category="patterns",
        tags=("memo", "decorator"),
        description="Caches function results",
    )
    svc.create_entry(
        title="Quick sort",
        code="void qsort() {}",
        language="c",
        category="algorithms",
        tags=("sort",),
        description="Classic quicksort",
    )
    return svc


@pytest.fixture
def panel(qapp, service: CatalogoService) -> CatalogoPanel:
    return CatalogoPanel(catalogo_service=service)


def test_initial_refresh_loads_all_entries(panel: CatalogoPanel) -> None:
    """All 3 entries appear in the list on first paint."""
    entries = panel._model.entries()
    assert len(entries) == 3
    titles = {e.title for e in entries}
    assert titles == {"LRU cache", "Memoization decorator", "Quick sort"}


def test_status_label_counts(panel: CatalogoPanel) -> None:
    """Status label reports the visible count."""
    assert panel._status.text() == "3 entradas"


def test_filter_combos_populated_from_service(panel: CatalogoPanel) -> None:
    """Combos include the sentinel + each distinct category/language."""
    cats = [panel._category_combo.itemText(i)
            for i in range(panel._category_combo.count())]
    langs = [panel._language_combo.itemText(i)
             for i in range(panel._language_combo.count())]
    assert cats[0] == CatalogoPanel._ALL_SENTINEL
    assert "algorithms" in cats
    assert "patterns" in cats
    assert "data-structures" in cats
    assert langs[0] == CatalogoPanel._ALL_SENTINEL
    assert "python" in langs
    assert "c" in langs


def test_search_filters_via_fts5(panel: CatalogoPanel) -> None:
    """Typing in the search box debounces then narrows the list."""
    panel._search_input.setText("memo")
    # Debounce hasn't fired yet — list still shows everything.
    panel._search_debounce.stop()
    assert len(panel._model.entries()) == 3
    # Now run the debounce manually.
    panel._search_debounce.start()
    panel._search_debounce.timeout.emit()
    titles = {e.title for e in panel._model.entries()}
    assert titles == {"Memoization decorator"}


def test_search_is_prefix_matched(panel: CatalogoPanel) -> None:
    """FTS5 prefix matching: 'cach' matches 'LRU cache'."""
    panel._search_input.setText("cach")
    panel._search_debounce.start()
    panel._search_debounce.timeout.emit()
    titles = {e.title for e in panel._model.entries()}
    assert "LRU cache" in titles


def test_filter_by_language(panel: CatalogoPanel) -> None:
    """Selecting 'python' in the language combo narrows the list."""
    panel._language_combo.setCurrentText("python")
    titles = {e.title for e in panel._model.entries()}
    assert titles == {"LRU cache", "Memoization decorator"}
    assert panel.current_language() == "python"


def test_filter_by_category(panel: CatalogoPanel) -> None:
    """Selecting 'patterns' in the category combo narrows to that entry."""
    panel._category_combo.setCurrentText("patterns")
    titles = {e.title for e in panel._model.entries()}
    assert titles == {"Memoization decorator"}


def test_reset_filter_to_all(qapp, service: CatalogoService) -> None:
    """Selecting the sentinel resets the filter."""
    panel = CatalogoPanel(catalogo_service=service)
    panel._category_combo.setCurrentText("patterns")
    assert len(panel._model.entries()) == 1
    panel._category_combo.setCurrentIndex(0)  # sentinel
    assert len(panel._model.entries()) == 3


def test_entry_selected_emits_on_selection_change(
    panel: CatalogoPanel, service: CatalogoService
) -> None:
    """Clicking an entry fires entry_selected with its id."""
    received: list[int] = []
    panel.entry_selected.connect(received.append)

    # Pick the first row in the model.
    target_id = panel._model.entries()[0].id
    panel._list.setCurrentIndex(panel._model.index(0, 0))

    assert received == [target_id]
    assert panel.selected_entry_id() == target_id


def test_action_buttons_disabled_without_selection(panel: CatalogoPanel) -> None:
    """Edit / Delete / Insert are disabled until something is picked."""
    assert panel._edit_button.isEnabled() is False
    assert panel._delete_button.isEnabled() is False
    assert panel._insert_button.isEnabled() is False


def test_action_buttons_enabled_with_selection(panel: CatalogoPanel) -> None:
    """After selecting, action buttons become clickable."""
    panel._list.setCurrentIndex(panel._model.index(0, 0))
    assert panel._edit_button.isEnabled() is True
    assert panel._delete_button.isEnabled() is True
    assert panel._insert_button.isEnabled() is True


def test_new_button_always_emits(panel: CatalogoPanel) -> None:
    """The +Nova button has no selection requirement."""
    received: list[int] = []
    panel.new_entry_requested.connect(lambda: received.append(1))
    panel._new_button.click()
    assert received == [1]


def test_edit_button_emits_selected_id(panel: CatalogoPanel) -> None:
    """Edit button emits edit_entry_requested with selected id."""
    received: list[int] = []
    panel.edit_entry_requested.connect(received.append)
    panel._list.setCurrentIndex(panel._model.index(0, 0))
    panel._edit_button.click()
    assert len(received) == 1
    assert received[0] == panel._model.entries()[0].id


def test_delete_button_emits_selected_id(panel: CatalogoPanel) -> None:
    """Delete button emits delete_entry_requested with selected id."""
    received: list[int] = []
    panel.delete_entry_requested.connect(received.append)
    panel._list.setCurrentIndex(panel._model.index(0, 0))
    panel._delete_button.click()
    assert received == [panel._model.entries()[0].id]


def test_insert_button_emits_selected_id(panel: CatalogoPanel) -> None:
    """Insert button emits insert_into_editor_requested with selected id."""
    received: list[int] = []
    panel.insert_into_editor_requested.connect(received.append)
    panel._list.setCurrentIndex(panel._model.index(0, 0))
    panel._insert_button.click()
    assert received == [panel._model.entries()[0].id]


def test_refresh_re_queries_service(panel: CatalogoPanel, service: CatalogoService) -> None:
    """Adding an entry then calling refresh() includes it."""
    service.create_entry(title="New one", code="x = 1", language="python")
    panel.refresh()
    titles = {e.title for e in panel._model.entries()}
    assert "New one" in titles


def test_list_model_data_roles(panel: CatalogoPanel) -> None:
    """CatalogoListModel exposes DisplayRole / EntryRole / IdRole."""
    entries = panel._model.entries()
    idx = panel._model.index(0, 0)
    assert panel._model.data(idx, CatalogoListModel.EntryRole) is entries[0]
    assert panel._model.data(idx, CatalogoListModel.IdRole) == entries[0].id


def test_list_model_entry_at_bounds() -> None:
    """``entry_at`` returns None for out-of-range rows."""
    model = CatalogoListModel()
    assert model.entry_at(0) is None
    assert model.entry_at(-1) is None


def test_selection_clears_after_refresh(panel: CatalogoPanel, service: CatalogoService) -> None:
    """After refresh(), the previously-selected row is no longer current."""
    panel._list.setCurrentIndex(panel._model.index(0, 0))
    assert panel.selected_entry_id() is not None
    panel.refresh()
    assert panel.selected_entry_id() is None
