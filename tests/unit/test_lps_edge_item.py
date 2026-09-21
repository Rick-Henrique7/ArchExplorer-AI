"""Tests for LpsEdgeItem (Change 007 — Bloco D — task D13).

Covers:

- Construction (id, endpoints, relation).
- to_dict / from_dict round-trip.
- Relation setter (REQUIRES ↔ EXCLUDES) updates pen style.
- update_path stores a valid QPainterPath.
- Z-order + flag semantics.
- Validation rejects unknown relation values.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainterPath
from PySide6.QtWidgets import QGraphicsScene

from app.ui.lps_edge_item import EdgeEndpoints, LpsEdgeItem


@pytest.fixture
def endpoints() -> EdgeEndpoints:
    return EdgeEndpoints(
        source_node_id="a",
        source_side="right",
        target_node_id="b",
        target_side="left",
    )


@pytest.fixture
def scene(qapp) -> QGraphicsScene:
    """A long-lived scene; the edge fixture parents onto this so it
    survives the test function body."""
    return QGraphicsScene()


@pytest.fixture
def edge(scene: QGraphicsScene, endpoints: EdgeEndpoints) -> LpsEdgeItem:
    e = LpsEdgeItem(endpoints=endpoints, relation="REQUIRES")
    scene.addItem(e)
    return e


def test_construction_uses_provided_id(qapp, endpoints: EdgeEndpoints) -> None:
    e = LpsEdgeItem(edge_id="e-x", endpoints=endpoints, relation="REQUIRES")
    assert e.edge_id == "e-x"


def test_construction_auto_id_when_missing(edge: LpsEdgeItem) -> None:
    assert edge.edge_id
    assert edge.edge_id.startswith("edge-")


def test_relation_setter_toggles(edge: LpsEdgeItem) -> None:
    assert edge.relation == "REQUIRES"
    edge.relation = "EXCLUDES"
    assert edge.relation == "EXCLUDES"


def test_relation_setter_rejects_unknown(edge: LpsEdgeItem) -> None:
    with pytest.raises(ValueError):
        edge.relation = "BOGUS"


def test_to_dict_round_trip(edge: LpsEdgeItem) -> None:
    payload = edge.to_dict()
    assert payload["id"] == edge.edge_id
    assert payload["source"] == "a"
    assert payload["target"] == "b"
    assert payload["relation"] == "REQUIRES"
    assert payload["source_side"] == "right"
    assert payload["target_side"] == "left"
    rebuilt = LpsEdgeItem.from_dict(payload)
    assert rebuilt.edge_id == edge.edge_id
    assert rebuilt.relation == edge.relation
    assert rebuilt.endpoints == edge.endpoints


def test_update_path_stores_valid_qpainterpath(edge: LpsEdgeItem) -> None:
    edge.update_path(QPointF(0, 0), QPointF(100, 50))
    p = edge.path()
    assert isinstance(p, QPainterPath)
    assert p.length() > 0


def test_z_value_below_nodes(edge: LpsEdgeItem) -> None:
    """Edges sit below nodes so rectangles render on top."""
    # LpsNodeItem defaults z=2.0; LpsEdgeItem uses 1.0.
    assert edge.zValue() < 2.0


def test_edge_is_not_movable(edge: LpsEdgeItem) -> None:
    """Edges move only via their endpoints, never directly."""
    # ``flags()`` returns the bitmask; ``ItemIsMovable`` must be cleared.
    assert not bool(edge.flags() & LpsEdgeItem.GraphicsItemFlag.ItemIsMovable)


def test_excludes_relation_uses_dashed_pen(scene: QGraphicsScene, endpoints: EdgeEndpoints) -> None:
    e = LpsEdgeItem(endpoints=endpoints, relation="EXCLUDES")
    scene.addItem(e)
    assert e.pen().style() == Qt.PenStyle.DashLine


def test_requires_relation_uses_solid_pen(edge: LpsEdgeItem) -> None:
    assert edge.pen().style() == Qt.PenStyle.SolidLine
