"""LpsNodeItem — visual representation of a feature-model node (Change 007).

One ``LpsNodeItem`` per node in the feature model. Hosts:

- A coloured rectangle (variability-dependent colour: ROOT = blue,
  MANDATORY = orange, OPTIONAL = grey, ALTERNATIVE = purple).
- A label inside the rectangle.
- Four "anchor" ellipses (top / bottom / left / right) used as
  drag-handles for edge creation. The user drags from an anchor to
  another node's anchor to spawn a new edge.

The class is intentionally a thin QGraphicsRectItem subclass: we
keep state on the Qt object directly so the scene can iterate
``scene.items()`` without keeping a parallel dict. The scene also
maintains its own id→node lookup via :class:`LpsCanvasScene`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsRectItem,
    QGraphicsSceneMouseEvent,
    QGraphicsTextItem,
)


class AnchorSide(str, Enum):
    """Which side of the node the anchor is on."""

    TOP = "top"
    BOTTOM = "bottom"
    LEFT = "left"
    RIGHT = "right"


# Colour palette per variability type. Picked for AA-contrast against
# the dark/light themes already used elsewhere in the app.
_NODE_COLORS: dict[str, tuple[QColor, QColor]] = {
    # (fill, border)
    "ROOT":        (QColor("#3a6ea5"), QColor("#1e3a5f")),
    "MANDATORY":   (QColor("#a55a3a"), QColor("#5f2e1c")),
    "OPTIONAL":    (QColor("#5a5a5a"), QColor("#2c2c2c")),
    "ALTERNATIVE": (QColor("#8a4aaf"), QColor("#4a2858")),
}


# Anchor visual constants.
_ANCHOR_RADIUS = 6.0
_ANCHOR_OFFSET = 8.0   # distance from node edge to anchor center


@dataclass(frozen=True)
class AnchorInfo:
    """The id of a specific anchor on a node."""

    node_id: str
    side: AnchorSide

    @property
    def key(self) -> str:
        """Stable id used by the scene to match anchors during edge drag."""
        return f"{self.node_id}::{self.side.value}"


class LpsNodeItem(QGraphicsRectItem):
    """A single feature-model node rendered in the canvas."""

    # Reasonable size for a feature-model diagram. Wider for labels
    # of 1–20 chars; resize is left to future work (Bloco D+).
    DEFAULT_WIDTH = 140.0
    DEFAULT_HEIGHT = 56.0

    def __init__(
        self,
        *,
        node_id: str | None = None,
        label: str = "Node",
        variability: str = "OPTIONAL",
        component_id: str | None = None,
        x: float = 0.0,
        y: float = 0.0,
    ) -> None:
        super().__init__(0, 0, self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
        self._node_id = node_id or str(uuid.uuid4())
        self._variability = variability
        self._component_id = component_id
        self.setPos(QPointF(x, y))
        # Make it draggable + selectable but ignore the view's
        # drag-mode (we use the default so rubber-band selection still
        # works on the canvas).
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        # Z-order above edges so they always render on top of them.
        self.setZValue(2.0)
        self._apply_style()
        self._build_label(label)
        self._build_anchors()

    # ----- Public API -----------------------------------------------------

    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def variability(self) -> str:
        return self._variability

    @variability.setter
    def variability(self, value: str) -> None:
        self._variability = value
        self._apply_style()

    @property
    def component_id(self) -> str | None:
        return self._component_id

    @component_id.setter
    def component_id(self, value: str | None) -> None:
        self._component_id = value

    @property
    def label(self) -> str:
        return self._label_item.toPlainText() if self._label_item else ""

    @label.setter
    def label(self, text: str) -> None:
        if self._label_item is not None:
            self._label_item.setPlainText(text)

    def anchor_for(self, side: AnchorSide) -> "LpsAnchorItem":
        """Return the anchor QGraphicsItem for ``side``."""
        return self._anchors[side]

    def anchor_center(self, side: AnchorSide) -> QPointF:
        """Return the world-coordinate center of the given anchor."""
        local = self._anchor_center_local(side)
        return self.mapToScene(local)

    # ----- Internal styling ------------------------------------------------

    def _apply_style(self) -> None:
        fill, border = _NODE_COLORS.get(
            self._variability, _NODE_COLORS["OPTIONAL"],
        )
        self.setBrush(QBrush(fill))
        self.setPen(QPen(border, 2.0))
        self.setOpacity(0.95)

    def _build_label(self, label: str) -> None:
        self._label_item = QGraphicsTextItem(label, parent=self)
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        self._label_item.setFont(font)
        # Centre the label inside the rectangle.
        br = self._label_item.boundingRect()
        self._label_item.setPos(
            (self.DEFAULT_WIDTH - br.width()) / 2.0,
            (self.DEFAULT_HEIGHT - br.height()) / 2.0,
        )
        self._label_item.setDefaultTextColor(QColor("#ffffff"))
        # Disable text interaction so clicks pass through to the parent.
        self._label_item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._label_item.setFlag(
            QGraphicsTextItem.GraphicsItemFlag.ItemIsMovable, False,
        )
        self._label_item.setZValue(0.5)

    def _build_anchors(self) -> None:
        self._anchors: dict[AnchorSide, "LpsAnchorItem"] = {}
        for side in AnchorSide:
            center = self._anchor_center_local(side)
            anchor = LpsAnchorItem(
                -_ANCHOR_RADIUS, -_ANCHOR_RADIUS,
                _ANCHOR_RADIUS * 2, _ANCHOR_RADIUS * 2,
                parent=self,
            )
            anchor.setPos(center)
            anchor.setZValue(3.0)
            anchor_info = AnchorInfo(self._node_id, side)
            anchor.anchor_info = anchor_info
            self._anchors[side] = anchor

    def _anchor_center_local(self, side: AnchorSide) -> QPointF:
        """Local-space center of the given anchor (relative to the rect's origin)."""
        mid_x = self.DEFAULT_WIDTH / 2.0
        mid_y = self.DEFAULT_HEIGHT / 2.0
        if side == AnchorSide.TOP:
            return QPointF(mid_x, -_ANCHOR_OFFSET)
        if side == AnchorSide.BOTTOM:
            return QPointF(mid_x, self.DEFAULT_HEIGHT + _ANCHOR_OFFSET)
        if side == AnchorSide.LEFT:
            return QPointF(-_ANCHOR_OFFSET, mid_y)
        return QPointF(self.DEFAULT_WIDTH + _ANCHOR_OFFSET, mid_y)

    # ----- Item-change events ---------------------------------------------

    def itemChange(self, change, value):  # noqa: N802 — Qt API
        """Forward selection-state changes to the anchor visibility.

        When the node is selected we show the anchors (handles for
        edge creation); when deselected, we hide them to keep the
        canvas clean.
        """
        if change == QGraphicsRectItem.GraphicsItemChange.ItemSelectedChange:
            visible = bool(value)
            for anchor in self._anchors.values():
                anchor.setVisible(visible)
        return super().itemChange(change, value)


class LpsAnchorItem(QGraphicsEllipseItem):
    """A small ellipse at one side of a node, used as a drag handle.

    Anchors are **only visible when their parent node is selected**,
    so the canvas stays clean during browsing. Drag from an anchor
    to another anchor to spawn an edge (handled by the scene).
    """

    def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self._anchor_info: AnchorInfo | None = None
        self.setBrush(QBrush(QColor("#ffd166")))
        self.setPen(QPen(QColor("#3a2c00"), 1.5))
        # Anchors are pickable but not movable on their own.
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setVisible(False)
        # Z-order above the node and labels.
        self.setZValue(4.0)

    @property
    def anchor_info(self) -> AnchorInfo | None:
        return self._anchor_info

    @anchor_info.setter
    def anchor_info(self, value: AnchorInfo) -> None:
        self._anchor_info = value

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # noqa: N802
        """Forward the press to the scene so it can start an edge-drag."""
        super().mousePressEvent(event)
        scene = self.scene()
        if scene is not None and self._anchor_info is not None:
            # ``anchor_pressed`` is handled by LpsCanvasScene.
            from app.ui.lps_canvas_scene import LpsCanvasScene
            if isinstance(scene, LpsCanvasScene):
                scene.begin_edge_drag(self._anchor_info, event.scenePos())
        event.accept()
