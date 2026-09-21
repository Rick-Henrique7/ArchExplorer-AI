"""LpsCanvasScene — the QGraphicsScene for the LPS canvas (Change 007).

Owns:

- The set of :class:`LpsNodeItem` keyed by node id.
- The set of :class:`LpsEdgeItem` keyed by edge id.
- A 4-step drag-to-create-edge state machine (idle → pressed → dragging → released).
- Serialization to / from the DSL JSON (Contrato 1).

Signals (Qt convention):
- :attr:`node_added` / :attr:`node_removed` — for MainWindow autosave.
- :attr:`edge_added` / :attr:`edge_removed`
- :attr:`node_selected` — fires with the node id when the user clicks.
- :attr:`tree_changed` — fires whenever the canvas structure mutates,
  so MainWindow can mark the model dirty + autosave.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGraphicsScene,
    QGraphicsSceneDragDropEvent,
    QGraphicsSceneMouseEvent,
)

from app.services.lps_models import (
    FeatureEdge,
    FeatureGroup,
    FeatureNode,
    FeatureModel,
)
from app.ui.lps_edge_item import EdgeEndpoints, LpsEdgeItem
from app.ui.lps_node_item import AnchorInfo, AnchorSide, LpsNodeItem


if TYPE_CHECKING:
    pass


# Custom MIME used by LpsPalettePanel → LpsCanvasScene drag-and-drop.
LPS_COMPONENT_MIME = "application/x-lps-component"


# QGraphicsScene.dropEvent needs a serializable payload — we wrap the
# component dict in JSON via Qt's native MIME machinery.
import json


class LpsCanvasScene(QGraphicsScene):
    """Manages the live LPS feature-model canvas."""

    # Signals (naming convention: past-tense events).
    node_added = Signal(str)             # node_id
    node_removed = Signal(str)           # node_id
    node_moved = Signal(str, float, float)  # node_id, x, y
    node_selected = Signal(str)          # node_id (or "" when cleared)
    edge_added = Signal(str)             # edge_id
    edge_removed = Signal(str)           # edge_id
    edge_changed = Signal(str)           # edge_id (relation toggled)
    tree_changed = Signal()              # any mutation; autosave hook

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)
        # Set a generous default size so users have room to drop nodes.
        self.setSceneRect(-2000, -2000, 4000, 4000)
        self.setBackgroundBrush(QColor("#1e1e1e"))
        # id → item lookups (kept here because Qt items can be removed
        # by deleteLater() and we want a stable id reference).
        self._nodes_by_id: dict[str, LpsNodeItem] = {}
        self._edges_by_id: dict[str, LpsEdgeItem] = {}
        # Edge-drag state.
        self._drag_source: AnchorInfo | None = None
        self._drag_target_node: LpsNodeItem | None = None
        # Counter for unique ids when the user clicks "Add node" instead
        # of dragging from the palette.
        self._node_counter = 0
        # Hook node moves so we can re-emit node_moved + tree_changed.
        self.selectionChanged.connect(self._on_selection_changed)

    # ----- Drag-and-drop --------------------------------------------------

    def dragEnterEvent(self, event: QGraphicsSceneDragDropEvent) -> None:  # noqa: N802
        if event.mimeData().hasFormat(LPS_COMPONENT_MIME):
            event.acceptProposedAction()

    def dragMoveEvent(self, event: QGraphicsSceneDragDropEvent) -> None:  # noqa: N802
        if event.mimeData().hasFormat(LPS_COMPONENT_MIME):
            event.acceptProposedAction()

    def dropEvent(self, event: QGraphicsSceneDragDropEvent) -> None:  # noqa: N802
        """A palette item landed on the canvas — create a node at the drop pos."""
        if not event.mimeData().hasFormat(LPS_COMPONENT_MIME):
            return
        raw = bytes(event.mimeData().data(LPS_COMPONENT_MIME)).decode("utf-8")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return
        drop_pos = event.scenePos()
        self.add_node(
            label=payload.get("name", "Component"),
            component_id=payload.get("component_id"),
            category=payload.get("category"),
            x=drop_pos.x() - LpsNodeItem.DEFAULT_WIDTH / 2.0,
            y=drop_pos.y() - LpsNodeItem.DEFAULT_HEIGHT / 2.0,
        )
        event.acceptProposedAction()

    # ----- Public API -----------------------------------------------------

    def add_node(
        self,
        *,
        node_id: str | None = None,
        label: str = "Node",
        component_id: str | None = None,
        category: str | None = None,
        variability: str = "OPTIONAL",
        x: float = 0.0,
        y: float = 0.0,
    ) -> LpsNodeItem:
        """Create a node at (x, y) and add it to the scene."""
        self._node_counter += 1
        nid = node_id or f"node_{self._node_counter}"
        node = LpsNodeItem(
            node_id=nid, label=label, variability=variability,
            component_id=component_id, x=x, y=y,
        )
        self.addItem(node)
        self._nodes_by_id[nid] = node
        self.node_added.emit(nid)
        self.tree_changed.emit()
        return node

    def remove_node(self, node_id: str) -> None:
        node = self._nodes_by_id.get(node_id)
        if node is None:
            return
        # First, remove every edge touching this node.
        edges_to_remove = [
            edge.edge_id
            for edge in self._edges_by_id.values()
            if edge.endpoints.source_node_id == node_id
            or edge.endpoints.target_node_id == node_id
        ]
        for eid in edges_to_remove:
            self.remove_edge(eid)
        del self._nodes_by_id[node_id]
        self.removeItem(node)
        self.node_removed.emit(node_id)
        self.tree_changed.emit()

    def add_edge(
        self,
        *,
        edge_id: str | None = None,
        endpoints: EdgeEndpoints,
        relation: str = "REQUIRES",
    ) -> LpsEdgeItem:
        eid = edge_id or f"edge-{uuid.uuid4().hex[:8]}"
        edge = LpsEdgeItem(edge_id=eid, endpoints=endpoints, relation=relation)
        self.addItem(edge)
        self._edges_by_id[eid] = edge
        # Re-draw using the current anchor positions.
        self._refresh_edge_path(edge)
        self.edge_added.emit(eid)
        self.tree_changed.emit()
        return edge

    def remove_edge(self, edge_id: str) -> None:
        edge = self._edges_by_id.get(edge_id)
        if edge is None:
            return
        del self._edges_by_id[edge_id]
        self.removeItem(edge)
        self.edge_removed.emit(edge_id)
        self.tree_changed.emit()

    def update_edge_relation(self, edge_id: str, relation: str) -> None:
        edge = self._edges_by_id.get(edge_id)
        if edge is None:
            return
        edge.relation = relation
        self._refresh_edge_path(edge)
        self.edge_changed.emit(edge_id)
        self.tree_changed.emit()

    def nodes(self) -> list[LpsNodeItem]:
        return list(self._nodes_by_id.values())

    def edges(self) -> list[LpsEdgeItem]:
        return list(self._edges_by_id.values())

    def get_node(self, node_id: str) -> LpsNodeItem | None:
        return self._nodes_by_id.get(node_id)

    def get_edge(self, edge_id: str) -> LpsEdgeItem | None:
        return self._edges_by_id.get(edge_id)

    def clear(self) -> None:
        """Remove every node + edge (used by the 'Clear' toolbar button)."""
        edge_ids = list(self._edges_by_id.keys())
        for eid in edge_ids:
            self.remove_edge(eid)
        node_ids = list(self._nodes_by_id.keys())
        for nid in node_ids:
            self.remove_node(nid)
        # tree_changed is already emitted by the remove_* helpers; we
        # don't want to duplicate it.

    def notify_edge_changed(self, edge: LpsEdgeItem) -> None:
        """Called by LpsEdgeItem when the user double-clicks to toggle."""
        # Re-draw the path so the new colour/dash style applies.
        self._refresh_edge_path(edge)
        self.edge_changed.emit(edge.edge_id)
        self.tree_changed.emit()

    # ----- Edge drag state machine ---------------------------------------

    def begin_edge_drag(
        self, anchor: AnchorInfo, scene_pos: QPointF,
    ) -> None:
        """Called by LpsAnchorItem.mousePressEvent.

        We remember the source anchor and the node the press started
        on (for the ``right-click on node to create edge`` case the
        source is itself a node). On mouseMove (handled at the view
        level) we draw a temporary line; on mouseRelease we commit.
        """
        self._drag_source = anchor
        # Find the source node (the press started on its anchor).
        self._drag_target_node = self._nodes_by_id.get(anchor.node_id)

    def update_edge_drag(self, scene_pos: QPointF) -> None:
        """Hook called by LpsCanvasView.mouseMoveEvent during a drag.

        Renders a preview line from the source anchor to the cursor
        (handled here by storing the last position; the view draws
        the preview).
        """
        # No persistent preview line kept in the scene — the view
        # renders it via a QGraphicsLineItem created on demand. We
        # just stash the latest position so the view can read it.
        # (The view owns the lifecycle of the preview line.)
        self._last_drag_pos = scene_pos

    def end_edge_drag(self, scene_pos: QPointF) -> LpsEdgeItem | None:
        """Commit the edge if the user released on a node anchor.

        Returns the new edge, or ``None`` if the drag was cancelled.
        """
        source_anchor = self._drag_source
        self._drag_source = None
        target_node = None
        target_side = AnchorSide.LEFT  # default if dropped on the node body
        # Walk all items at the drop position; prefer anchors.
        for item in self.items(scene_pos):
            from app.ui.lps_node_item import LpsAnchorItem
            if isinstance(item, LpsAnchorItem) and item.anchor_info is not None:
                if (
                    source_anchor is not None
                    and item.anchor_info.node_id == source_anchor.node_id
                ):
                    # Dropped on the source's own anchor — ignore.
                    continue
                target_node = self._nodes_by_id.get(item.anchor_info.node_id)
                target_side = item.anchor_info.side
                break
        else:
            # No anchor under the cursor — try a node body.
            for item in self.items(scene_pos):
                if isinstance(item, LpsNodeItem):
                    if (
                        source_anchor is not None
                        and item.node_id == source_anchor.node_id
                    ):
                        continue
                    target_node = item
                    target_side = AnchorSide.LEFT
                    break

        if source_anchor is None or target_node is None:
            self._drag_target_node = None
            return None

        # The source side is whatever anchor the user pressed.
        new_edge = self.add_edge(
            endpoints=EdgeEndpoints(
                source_node_id=source_anchor.node_id,
                source_side=source_anchor.side.value,
                target_node_id=target_node.node_id,
                target_side=target_side.value,
            ),
            relation="REQUIRES",
        )
        self._drag_target_node = None
        return new_edge

    def last_drag_position(self) -> QPointF | None:
        """Return the cursor position during an in-flight edge drag."""
        return getattr(self, "_last_drag_pos", None)

    def is_dragging_edge(self) -> bool:
        return self._drag_source is not None

    def cancel_edge_drag(self) -> None:
        self._drag_source = None
        self._drag_target_node = None

    # ----- Selection forwarding ------------------------------------------

    def _on_selection_changed(self) -> None:
        if not self.selectedItems():
            self.node_selected.emit("")
            return
        # Fire for the first selected node (we don't support multi-select
        # in the inspector yet).
        for item in self.selectedItems():
            if isinstance(item, LpsNodeItem):
                self.node_selected.emit(item.node_id)
                return
        # Non-node selection (e.g. an edge) → emit empty.
        self.node_selected.emit("")

    # ----- Path refresh ---------------------------------------------------

    def _refresh_edge_path(self, edge: LpsEdgeItem) -> None:
        """Recompute the line geometry between two anchor centers."""
        src_node = self._nodes_by_id.get(edge.endpoints.source_node_id)
        tgt_node = self._nodes_by_id.get(edge.endpoints.target_node_id)
        if src_node is None or tgt_node is None:
            return
        try:
            src_side = AnchorSide(edge.endpoints.source_side)
            tgt_side = AnchorSide(edge.endpoints.target_side)
        except ValueError:
            return
        src_pos = src_node.anchor_center(src_side)
        tgt_pos = tgt_node.anchor_center(tgt_side)
        edge.update_path(src_pos, tgt_pos)

    def refresh_all_edge_paths(self) -> None:
        """Call after a node move so every edge endpoint snaps."""
        for edge in self._edges_by_id.values():
            self._refresh_edge_path(edge)

    def itemChange_handler_for_nodes(self, node: LpsNodeItem):  # noqa: N802
        """No-op hook; the canvas_view listens to its own items."""
        return None

    # ----- JSON serialization (Contrato 1) ------------------------------

    def to_json(self) -> dict[str, Any]:
        """Serialize the canvas to a feature-model DSL payload.

        Edges use the ``source_node_id`` / ``target_node_id`` form
        directly (the DSL doesn't carry the anchor side). We include
        the side info as ``source_side`` / ``target_side`` for
        round-trip fidelity even though the current DSL doesn't use
        it (``LpsService._validate_tree_semantics`` accepts both).
        """
        nodes_payload: list[dict[str, Any]] = []
        # Detect the ROOT node so it can be flagged explicitly.
        root_ids = [
            n.node_id for n in self._nodes_by_id.values()
            if n.variability == "ROOT"
        ]
        if not root_ids:
            # Promote the first node to ROOT if none exists (lets us
            # round-trip an in-progress graph without forcing the user
            # to designate a ROOT before saving).
            first = next(iter(self._nodes_by_id.values()), None)
            if first is not None:
                root_ids = [first.node_id]

        for node in self._nodes_by_id.values():
            nodes_payload.append({
                "id": node.node_id,
                "component_id": node.component_id,
                "variability": (
                    "ROOT" if node.node_id in root_ids else node.variability
                ),
                "label": node.label,
                "metadata": {
                    "x": node.pos().x(),
                    "y": node.pos().y(),
                },
            })

        edges_payload: list[dict[str, Any]] = []
        for edge in self._edges_by_id.values():
            edges_payload.append({
                "id": edge.edge_id,
                "source": edge.endpoints.source_node_id,
                "target": edge.endpoints.target_node_id,
                "relation": edge.relation,
                "metadata": {
                    "source_side": edge.endpoints.source_side,
                    "target_side": edge.endpoints.target_side,
                },
            })

        return {
            "spec_version": "1.0",
            "nodes": nodes_payload,
            "edges": edges_payload,
            "groups": [],  # groups aren't yet represented in the GUI
        }

    def load_from_json(self, payload: dict[str, Any]) -> None:
        """Replace the canvas with the contents of a DSL payload.

        Existing nodes/edges are removed first (via ``clear``). Each
        node is re-created at its ``metadata.x/y`` position; each
        edge is added with its source/target + relation.
        """
        self.clear()
        # First pass: nodes (without edges, since edges need the
        # source/target nodes already present).
        for n in payload.get("nodes") or []:
            meta = n.get("metadata") or {}
            self.add_node(
                node_id=n["id"],
                label=n.get("label", n["id"]),
                component_id=n.get("component_id"),
                variability=n.get("variability", "OPTIONAL"),
                x=float(meta.get("x", 0.0)),
                y=float(meta.get("y", 0.0)),
            )
        # Second pass: edges.
        for e in payload.get("edges") or []:
            meta = e.get("metadata") or {}
            self.add_edge(
                edge_id=e["id"],
                endpoints=EdgeEndpoints(
                    source_node_id=e["source"],
                    source_side=meta.get("source_side", "right"),
                    target_node_id=e["target"],
                    target_side=meta.get("target_side", "left"),
                ),
                relation=e.get("relation", "REQUIRES"),
            )
        # Refresh geometry (anchor positions depend on node layout).
        self.refresh_all_edge_paths()
