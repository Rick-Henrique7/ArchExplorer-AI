"""Tests for LpsPalettePanel (Change 007 — Bloco D — task D10).

Covers:

- set_components populates the list.
- clear empties it.
- selected_item returns the highlighted PaletteItem.
- startDrag attaches the right MIME payload.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from PySide6.QtCore import QByteArray, QMimeData

from app.services import LpsComponent
from app.ui.lps_canvas_scene import LPS_COMPONENT_MIME
from app.ui.lps_palette_panel import LpsPalettePanel, PaletteItem


def _make_component(name: str, category: str = "service") -> LpsComponent:
    return LpsComponent(
        id=f"id-{name}", name=name, category=category,
        description=None, code_snippet=None,
        svg_icon_path=None, jinja_template=None,
        metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def test_initial_palette_is_empty(qapp) -> None:
    panel = LpsPalettePanel()
    assert panel.count() == 0
    assert panel.selected_item() is None


def test_set_components_populates_list(qapp) -> None:
    panel = LpsPalettePanel()
    components = [
        _make_component("OAuth"),
        _make_component("JWT", category="architecture"),
        _make_component("DB", category="database"),
    ]
    panel.set_components(components)
    assert panel.count() == 3
    # Status label shows the count.
    assert "3" in panel._status.text()


def test_set_components_clears_previous(qapp) -> None:
    panel = LpsPalettePanel()
    panel.set_components([_make_component("A"), _make_component("B")])
    panel.set_components([_make_component("C")])
    assert panel.count() == 1


def test_clear_empties(qapp) -> None:
    panel = LpsPalettePanel()
    panel.set_components([_make_component("X")])
    panel.clear()
    assert panel.count() == 0


def test_selected_item_returns_palette_item(qapp) -> None:
    panel = LpsPalettePanel()
    panel.set_components([_make_component("A"), _make_component("B")])
    # The first item is auto-selected on add; check we get a valid
    # PaletteItem back.
    item = panel.selected_item()
    if item is not None:
        assert item.component_id in {"id-A", "id-B"}
    # Explicitly select row 1.
    panel._list.setCurrentRow(1)
    item = panel.selected_item()
    assert item is not None
    assert item.component_id == "id-B"


def test_startDrag_attaches_lps_mime(qapp, monkeypatch) -> None:
    panel = LpsPalettePanel()
    panel.set_components([_make_component("OAuth", category="architecture")])
    # Select the first row so startDrag finds an item.
    panel._list.setCurrentRow(0)

    captured = {}

    class _FakeDrag:
        def __init__(self, parent):
            pass

        def setMimeData(self, mime):
            captured["mime"] = mime

        def exec(self, actions):
            return 0

    monkeypatch.setattr("app.ui.lps_palette_panel.QDrag", _FakeDrag)
    panel.startDrag(0)
    mime = captured.get("mime")
    assert mime is not None
    assert mime.hasFormat(LPS_COMPONENT_MIME)
    raw = bytes(mime.data(LPS_COMPONENT_MIME)).decode("utf-8")
    payload = json.loads(raw)
    assert payload == {
        "component_id": "id-OAuth",
        "name": "OAuth",
        "category": "architecture",
    }


def test_startDrag_no_item_is_noop(qapp, monkeypatch) -> None:
    """No current item → no drag created."""
    panel = LpsPalettePanel()  # empty
    called = {"drag": 0}

    class _FakeDrag:
        def __init__(self, parent):
            called["drag"] += 1

        def setMimeData(self, mime): pass

        def exec(self, actions): return 0

    monkeypatch.setattr("app.ui.lps_palette_panel.QDrag", _FakeDrag)
    panel.startDrag(0)
    assert called["drag"] == 0


def test_palette_status_one_vs_many(qapp) -> None:
    panel = LpsPalettePanel()
    # 1 component → singular.
    panel.set_components([_make_component("X")])
    assert "1 componente" in panel._status.text()
    # 2+ → plural.
    panel.set_components([_make_component("A"), _make_component("B")])
    assert "2 componentes" in panel._status.text()
    # 0 → empty message.
    panel.clear()
    assert "Nenhum" in panel._status.text()
