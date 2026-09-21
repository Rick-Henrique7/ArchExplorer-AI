"""LpsEdgeItem — visual representation of a feature-model edge (Change 007).

A directed arrow between two :class:`LpsNodeItem`s. Two visual styles:

- ``REQUIRES`` → solid line with filled triangle arrow-head.
- ``EXCLUDES`` → dashed line with hollow circle end (the "mutual
  exclusion" cue used in Eclipse FeatureIDE / literature).

Edges track their endpoints via callbacks (registered by the scene)
so that moving a node updates the line in real time. We avoid
re-implementing QGraphicsItem.itemChange's geometry hook here —
keeping the moving logic in the scene simplifies tests and avoids
subtle bugs when both endpoints move simultaneously.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsPathItem,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)


# Edge styling constants.
_REQUIRES_COLOR = QColor("#4a90e2")  # blue
_EXCLUDES_COLOR = QColor("#d0021b")   # red

# Arrow head size in scene units.
_ARROW_SIZE = 10.0
# How much the arrowhead shortens the line (so it doesn't overlap the
# target node's border).
_ARROW_SHORTEN = 4.0
# Line width.
_LINE_WIDTH = 2.0


@dataclass(frozen=True)
class EdgeEndpoints:
    """A pair (source_anchor, target_anchor) used to draw the edge.

    The scene subscribes to changes on the underlying nodes and
    re-reads these anchors via :meth:`LpsNodeItem.anchor_center` to
    keep the line in sync.
    """

    source_node_id: str
    source_side: str  # AnchorSide value
    target_node_id: str
    target_side: str


class LpsEdgeItem(QGraphicsPathItem):
    """A directed edge drawn between two anchors."""

    def __init__(
        self,
        *,
        edge_id: str | None = None,
        endpoints: EdgeEndpoints,
        relation: str = "REQUIRES",
    ) -> None:
        super().__init__()
        self._edge_id = edge_id or f"edge-{uuid.uuid4().hex[:8]}"
        self._endpoints = endpoints
        self._relation = relation
        # Not movable on its own; only the endpoints drive the path.
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable, True)
        # Below the nodes so the rectangles render on top.
        self.setZValue(1.0)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self._apply_style()

    # ----- Public API -----------------------------------------------------

    @property
    def edge_id(self) -> str:
        return self._edge_id

    @property
    def relation(self) -> str:
        return self._relation

    @relation.setter
    def relation(self, value: str) -> None:
        if value not in ("REQUIRES", "EXCLUDES"):
            raise ValueError(
                f"relation must be REQUIRES or EXCLUDES, got {value!r}"
            )
        self._relation = value
        self._apply_style()

    @property
    def endpoints(self) -> EdgeEndpoints:
        return self._endpoints

    def update_path(
        self,
        source_pos: QPointF,
        target_pos: QPointF,
    ) -> None:
        """Recompute the path between two scene-space anchor points.

        Called by the scene on node moves / scene rebuilds. We don't
        keep scene references here (no ownership cycle) — the
        caller passes the points in.
        """
        # Compute a short curve between source and target. A pure
        # straight line is the simplest and most legible choice;
        # offsetting the control point along the perpendicular gives
        # a gentle curve when anchors are not collinear.
        path = QPainterPath()
        path.moveTo(source_pos)
        # Truncate the line a few units before the target so the
        # arrowhead lands cleanly on the node's edge.
        dx = target_pos.x() - source_pos.x()
        dy = target_pos.y() - source_pos.y()
        dist_sq = dx * dx + dy * dy
        if dist_sq > 0.0001:
            length = dist_sq ** 0.5
            ux, uy = dx / length, dy / length
            truncated = QPointF(
                target_pos.x() - ux * _ARROW_SHORTEN,
                target_pos.y() - uy * _ARROW_SHORTEN,
            )
            path.lineTo(truncated)
        else:
            path.lineTo(target_pos)
        self.setPath(path)
        # Update the brush / pen for arrowhead at the tip.
        self._apply_style()

    def to_dict(self) -> dict[str, str]:
        """Serialize for ``LpsCanvasScene.to_json``."""
        return {
            "id": self._edge_id,
            "source": self._endpoints.source_node_id,
            "source_side": self._endpoints.source_side,
            "target": self._endpoints.target_node_id,
            "target_side": self._endpoints.target_side,
            "relation": self._relation,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "LpsEdgeItem":
        return cls(
            edge_id=payload["id"],
            endpoints=EdgeEndpoints(
                source_node_id=payload["source"],
                source_side=payload["source_side"],
                target_node_id=payload["target"],
                target_side=payload["target_side"],
            ),
            relation=payload["relation"],
        )

    # ----- Internal styling ------------------------------------------------

    def _apply_style(self) -> None:
        if self._relation == "REQUIRES":
            self.setPen(QPen(_REQUIRES_COLOR, _LINE_WIDTH))
            self.setBrush(QBrush(_REQUIRES_COLOR))
        else:
            pen = QPen(_EXCLUDES_COLOR, _LINE_WIDTH)
            pen.setStyle(Qt.PenStyle.DashLine)
            self.setPen(pen)
            self.setBrush(QBrush(_EXCLUDES_COLOR))

    # ----- Qt overrides ----------------------------------------------------

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Paint the line + an arrow head at the tip.

        We use the path the scene set, then draw a triangle at the
        end so the direction is visible. The triangle points along
        the tangent of the last segment.
        """
        super().paint(painter, option, widget)
        path = self.path()
        if path.length() < 0.001:
            return
        # Compute the angle of the last segment for the arrow head.
        # Qt's QPainterPath exposes percent-length helpers; we use
        # the angle of the tangent at 100%.
        end = path.pointAtPercent(1.0)
        # Sample a tiny bit before the end to get the direction.
        prev = path.pointAtPercent(0.999)
        angle_rad = _angle_between(prev, end)
        # Make sure the painter's pen has the right color; the pen
        # was already set by setPen(), so we just draw the triangle
        # in the same color via brush.
        painter.save()
        painter.setBrush(self.brush())
        painter.setPen(Qt.PenStyle.NoPen)
        # Build the triangle in scene coords; painter's transform
        # already accounts for item pos (which is 0,0 here).
        triangle = QPolygonF()
        tip = QPointF(end.x(), end.y())
        # Two base corners perpendicular to the direction.
        angle_back = angle_rad + _PI
        base_center_x = end.x() + _ARROW_SIZE * 0.5 * _cos(angle_back)
        base_center_y = end.y() + _ARROW_SIZE * 0.5 * _sin(angle_back)
        perp = angle_back + _PI / 2
        half_width = _ARROW_SIZE * 0.6
        triangle.append(tip)
        triangle.append(QPointF(
            base_center_x + half_width * _cos(perp),
            base_center_y + half_width * _sin(perp),
        ))
        triangle.append(QPointF(
            base_center_x - half_width * _cos(perp),
            base_center_y - half_width * _sin(perp),
        ))
        painter.drawPolygon(triangle)
        painter.restore()

    # ----- Mouse interaction (open relation picker) ---------------------

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # noqa: N802
        """Double-click toggles REQUIRES ↔ EXCLUDES.

        Cheap in-canvas editing: no dialog. The user can also use
        the inspector panel for explicit relation choice.
        """
        self.relation = (
            "EXCLUDES" if self._relation == "REQUIRES" else "REQUIRES"
        )
        # Notify the scene so it can update its JSON model.
        scene = self.scene()
        if scene is not None:
            from app.ui.lps_canvas_scene import LpsCanvasScene
            if isinstance(scene, LpsCanvasScene):
                scene.notify_edge_changed(self)
        super().mouseDoubleClickEvent(event)


# ----- Math helpers -----------------------------------------------------

import math

_PI = math.pi


def _cos(angle: float) -> float:
    return math.cos(angle)


def _sin(angle: float) -> float:
    return math.sin(angle)


def _angle_between(p1: QPointF, p2: QPointF) -> float:
    """Return the angle of the vector p1 → p2 in screen coords (radians)."""
    return math.atan2(p2.y() - p1.y(), p2.x() - p1.x())
