"""Tests for LpsCanvasScene (Change 007 — Bloco D — task D11).

Covers:

- Add / remove nodes + edges.
- Signals fire on mutation.
- Drag-to-create-edge state machine (begin → update → end).
- to_json / load_from_json round-trip preserves structure.
- Clear wipes everything.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QPointF, QByteArray
from PySide6.QtGui import QDragEnterEvent

from app.ui.lps_canvas_scene import LPS_COMPONENT_MIME, LpsCanvasScene
from app.ui.lps_edge_item import EdgeEndpoints
from app.ui.lps_node_item import AnchorSide, LpsNodeItem


@pytest.fixture
def scene(qapp) -> LpsCanvasScene:
    s = LpsCanvasScene()
    # Make the scene long-lived by parenting on the qapp fixture.
    return s


# ----- Node lifecycle ---------------------------------------------------

def test_add_node_emits_signals(scene: LpsCanvasScene) -> None:
    added: list[str] = []
    changed: list[int] = []
    scene.node_added.connect(added.append)
    scene.tree_changed.connect(lambda: changed.append(1))
    scene.add_node(node_id="n1", label="X", x=10, y=20)
    assert added == ["n1"]
    assert len(changed) == 1


def test_add_node_auto_id(scene: LpsCanvasScene) -> None:
    n = scene.add_node(label="X")
    assert n.node_id == "node_1"
    n2 = scene.add_node(label="Y")
    assert n2.node_id == "node_2"


def test_remove_node_cascades_edges(scene: LpsCanvasScene) -> None:
    a = scene.add_node(node_id="a", label="A")
    b = scene.add_node(node_id="b", label="B")
    edge = scene.add_edge(
        endpoints=EdgeEndpoints("a", "right", "b", "left"),
    )
    scene.remove_node("a")
    assert scene.get_node("a") is None
    assert scene.get_edge(edge.edge_id) is None
    assert b.node_id == "b"  # b is untouched


def test_clear_empties_scene(scene: LpsCanvasScene) -> None:
    scene.add_node(node_id="a", label="A")
    scene.add_node(node_id="b", label="B")
    scene.add_edge(endpoints=EdgeEndpoints("a", "right", "b", "left"))
    scene.clear()
    assert scene.nodes() == []
    assert scene.edges() == []


# ----- Edge lifecycle --------------------------------------------------

def test_add_edge_emits_signals(scene: LpsCanvasScene) -> None:
    scene.add_node(node_id="a", label="A")
    scene.add_node(node_id="b", label="B")
    received: list[str] = []
    scene.edge_added.connect(received.append)
    e = scene.add_edge(
        endpoints=EdgeEndpoints("a", "right", "b", "left"),
        relation="EXCLUDES",
    )
    assert received == [e.edge_id]
    assert e.relation == "EXCLUDES"


def test_remove_edge_emits_signal(scene: LpsCanvasScene) -> None:
    scene.add_node(node_id="a", label="A")
    scene.add_node(node_id="b", label="B")
    e = scene.add_edge(endpoints=EdgeEndpoints("a", "right", "b", "left"))
    received: list[str] = []
    scene.edge_removed.connect(received.append)
    scene.remove_edge(e.edge_id)
    assert received == [e.edge_id]


def test_update_edge_relation(scene: LpsCanvasScene) -> None:
    scene.add_node(node_id="a", label="A")
    scene.add_node(node_id="b", label="B")
    e = scene.add_edge(endpoints=EdgeEndpoints("a", "right", "b", "left"))
    scene.update_edge_relation(e.edge_id, "EXCLUDES")
    assert scene.get_edge(e.edge_id).relation == "EXCLUDES"


# ----- Drag-to-create-edge state machine ------------------------------

def test_is_dragging_edge_starts_false(scene: LpsCanvasScene) -> None:
    assert scene.is_dragging_edge() is False


def test_begin_and_end_edge_drag_creates_edge(scene: LpsCanvasScene) -> None:
    scene.add_node(node_id="a", label="A", x=0, y=0)
    scene.add_node(node_id="b", label="B", x=200, y=0)
    from app.ui.lps_node_item import AnchorInfo
    scene.begin_edge_drag(AnchorInfo("a", AnchorSide.RIGHT), QPointF(0, 0))
    assert scene.is_dragging_edge() is True
    # Drop on the center of node B (200 + 70 = 270; that's inside its rect).
    edge = scene.end_edge_drag(QPointF(270, 28))
    assert edge is not None
    assert edge.endpoints.source_node_id == "a"
    assert edge.endpoints.target_node_id == "b"


def test_end_edge_drag_cancelled_without_target(scene: LpsCanvasScene) -> None:
    """Dropping on empty space returns None and doesn't create an edge."""
    scene.add_node(node_id="a", label="A", x=0, y=0)
    from app.ui.lps_node_item import AnchorInfo
    scene.begin_edge_drag(AnchorInfo("a", AnchorSide.RIGHT), QPointF(0, 0))
    # Drop far from any node (the scene is 4000x4000, so 3000,3000 is empty).
    result = scene.end_edge_drag(QPointF(3000, 3000))
    assert result is None


def test_cancel_edge_drag(scene: LpsCanvasScene) -> None:
    from app.ui.lps_node_item import AnchorInfo
    scene.begin_edge_drag(AnchorInfo("a", AnchorSide.RIGHT), QPointF(0, 0))
    scene.cancel_edge_drag()
    assert scene.is_dragging_edge() is False


# ----- JSON round-trip -------------------------------------------------

def test_to_json_round_trip_preserves_structure(scene: LpsCanvasScene) -> None:
    scene.add_node(node_id="root", label="R", variability="ROOT", x=10, y=20)
    scene.add_node(node_id="db", label="DB", variability="MANDATORY", x=200, y=20)
    scene.add_edge(
        endpoints=EdgeEndpoints("root", "right", "db", "left"),
        relation="REQUIRES",
    )
    payload = scene.to_json()
    # Re-load into a fresh scene.
    scene2 = LpsCanvasScene()
    scene2.load_from_json(payload)
    assert {n.node_id for n in scene2.nodes()} == {"root", "db"}
    assert len(scene2.edges()) == 1
    loaded_edge = scene2.edges()[0]
    assert loaded_edge.endpoints.source_node_id == "root"
    assert loaded_edge.endpoints.target_node_id == "db"
    assert loaded_edge.relation == "REQUIRES"


def test_to_json_promotes_first_node_to_root_if_missing(scene: LpsCanvasScene) -> None:
    """If no ROOT exists, the first node is promoted so the payload validates."""
    scene.add_node(node_id="x", label="X", variability="OPTIONAL", x=0, y=0)
    payload = scene.to_json()
    # The auto-promoted node keeps its OPTIONAL ``variability`` from
    # the LpsNodeItem but the payload says ROOT — the inspector /
    # canvas can sync this after load if the user wants.
    root_count = sum(1 for n in payload["nodes"] if n["variability"] == "ROOT")
    assert root_count == 1


def test_to_json_includes_anchor_sides(scene: LpsCanvasScene) -> None:
    scene.add_node(node_id="a", label="A", x=0, y=0)
    scene.add_node(node_id="b", label="B", x=100, y=0)
    e = scene.add_edge(
        endpoints=EdgeEndpoints("a", "right", "b", "left"),
    )
    payload = scene.to_json()
    edge_payload = payload["edges"][0]
    assert edge_payload["metadata"]["source_side"] == "right"
    assert edge_payload["metadata"]["target_side"] == "left"


# ----- Drag-from-palette acceptance -----------------------------------

def test_drop_with_valid_mime_creates_node(
    scene: LpsCanvasScene, qapp,
) -> None:
    """The drop event pathway creates a node from the MIME payload."""
    from PySide6.QtGui import QDragEnterEvent, QDropEvent, QMouseEvent
    payload = json.dumps({
        "component_id": "c-1",
        "name": "OAuth",
        "category": "architecture",
    })
    mime = QMimeData()
    mime.setData(LPS_COMPONENT_MIME, QByteArray(payload.encode("utf-8")))
    # Synthesize a drop event via a simple call to dropEvent.
    # PySide6 event constructors are clunky, so we call the public
    # dropEvent with a real QDropEvent-shaped object via mock.
    from unittest.mock import MagicMock
    event = MagicMock()
    event.mimeData.return_value = mime
    event.scenePos.return_value = QPointF(150, 75)
    event.acceptProposedAction = lambda: None
    scene.dropEvent(event)
    # A new node should have been added.
    assert scene.nodes()
    assert scene.nodes()[0].label == "OAuth"


def test_drop_with_unknown_mime_does_nothing(
    scene: LpsCanvasScene, qapp,
) -> None:
    """MIME types other than the LPS one are ignored."""
    from unittest.mock import MagicMock
    mime = QMimeData()
    mime.setText("not an LPS component")
    event = MagicMock()
    event.mimeData.return_value = mime
    event.scenePos.return_value = QPointF(0, 0)
    scene.dropEvent(event)
    assert scene.nodes() == []


# ----- CanvasView smoke -------------------------------------------------

def test_canvas_view_smoke(qapp) -> None:
    """LpsCanvasView instantiates and wires its scene correctly."""
    from app.ui.lps_canvas_view import LpsCanvasView
    view = LpsCanvasView()
    assert view.canvas_scene() is not None
    # Toolbar buttons exist.
    assert view._toolbar is not None
    # Required signals exist.
    assert hasattr(view, "validate_requested")
    assert hasattr(view, "generate_requested")
