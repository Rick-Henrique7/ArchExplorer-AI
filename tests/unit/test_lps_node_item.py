"""Tests for LpsNodeItem (Change 007 — Bloco D — task D12).

Covers:

- Construction defaults (UUID, position, size).
- Variability → colour mapping.
- Label and component_id setters.
- Anchors: 4 sides, anchor_center in scene coords.
- Selection → anchors become visible.
"""

from __future__ import annotations

import pytest

from app.ui.lps_node_item import AnchorSide, LpsNodeItem


@pytest.fixture
def node(qapp) -> LpsNodeItem:
    return LpsNodeItem(
        node_id="n1", label="DB", variability="MANDATORY",
        component_id="c-db", x=100, y=50,
    )


def test_construction_uses_provided_id(node: LpsNodeItem) -> None:
    assert node.node_id == "n1"


def test_construction_auto_uuid_when_id_missing(qapp) -> None:
    n = LpsNodeItem(label="X")
    assert n.node_id
    assert len(n.node_id) == 36  # UUID4 hex+hyphens


def test_default_size_is_140x56(node: LpsNodeItem) -> None:
    rect = node.rect()
    assert rect.width() == LpsNodeItem.DEFAULT_WIDTH
    assert rect.height() == LpsNodeItem.DEFAULT_HEIGHT


def test_position_is_set_from_ctor(node: LpsNodeItem) -> None:
    assert node.pos().x() == 100
    assert node.pos().y() == 50


def test_variability_setter_updates_brush(qapp) -> None:
    n = LpsNodeItem(label="X", variability="OPTIONAL")
    n.variability = "ROOT"
    assert n.variability == "ROOT"
    # Brush should not be None (the colour swap re-applies the style).
    assert n.brush().style() != 0  # Qt.NoBrush == 0


def test_label_setter_updates_label_item(node: LpsNodeItem) -> None:
    node.label = "New label"
    assert node.label == "New label"


def test_component_id_setter(node: LpsNodeItem) -> None:
    node.component_id = "c-new"
    assert node.component_id == "c-new"
    node.component_id = None
    assert node.component_id is None


def test_anchors_built_for_all_four_sides(node: LpsNodeItem) -> None:
    for side in AnchorSide:
        anchor = node.anchor_for(side)
        assert anchor is not None
        assert anchor.anchor_info is not None
        assert anchor.anchor_info.node_id == "n1"
        assert anchor.anchor_info.side == side


def test_anchor_center_returns_scene_position(node: LpsNodeItem) -> None:
    """The TOP anchor center should be above the rect, in world coords."""
    top_center = node.anchor_center(AnchorSide.TOP)
    # y < rect.top() because the anchor is offset above the node.
    assert top_center.y() < node.pos().y()
    # x is roughly at the center of the node (140/2 = 70, plus node x=100).
    assert abs(top_center.x() - (100 + LpsNodeItem.DEFAULT_WIDTH / 2)) < 1


def test_anchors_hidden_by_default(qapp) -> None:
    n = LpsNodeItem(label="X")
    for side in AnchorSide:
        assert n.anchor_for(side).isVisible() is False


def test_anchors_become_visible_when_node_selected(node: LpsNodeItem) -> None:
    node.setSelected(True)
    for side in AnchorSide:
        # Qt schedules visibility updates via itemChange; force a
        # round-trip so the test is not racy.
        anchor = node.anchor_for(side)
        # PySide6 keeps the itemChange handler synchronous, so
        # visibility should already be True.
        assert anchor.isVisible() is True
