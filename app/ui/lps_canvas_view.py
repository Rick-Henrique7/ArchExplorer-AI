"""LpsCanvasView — the QGraphicsView hosting LpsCanvasScene (Change 007).

Wraps the scene with view-level niceties:

- ``dragMoveEvent`` / ``dropEvent`` proxied to the scene (drag from
  palette → drop on canvas).
- ``mouseMoveEvent`` / ``mouseReleaseEvent`` draw a temporary line
  during an edge-drag (state machine owned by the scene).
- Ctrl+wheel zooms; middle-button drag pans; click clears selection.

Toolbar buttons (``Validate`` / ``Generate`` / ``Auto-layout`` /
``Clear``) live in the view itself via a :class:`QToolBar` docked at
the top — keeps the canvas free of chrome.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import (
    QGraphicsLineItem,
    QGraphicsSceneMouseEvent,
    QGraphicsView,
    QHBoxLayout,
    QPushButton,
    QToolBar,
    QWidget,
)


class LpsCanvasView(QGraphicsView):
    """View hosting the LPS canvas scene + toolbar.

    Signals (consumed by MainWindow):
    - :attr:`validate_requested` — fire when the user clicks **Validate**.
    - :attr:`generate_requested` — fire when the user clicks **Gerar Produto**.
    """

    validate_requested = Signal()
    generate_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from app.ui.lps_canvas_scene import LpsCanvasScene
        self._scene = LpsCanvasScene(self)
        self.setScene(self._scene)
        # Smooth zoom + render hints for performance.
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        # Rubber-band selection; shift-drag for multi-select (future).
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        # No scrollbars unless the scene exceeds the view.
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        # Preview line used during an edge-drag (kept on the view,
        # not the scene, so it doesn't pollute serialization).
        self._preview_line: QGraphicsLineItem | None = None
        # Build the toolbar.
        self._build_toolbar()

    # ----- Public API -----------------------------------------------------

    def canvas_scene(self):  # type: ignore[no-untyped-def]
        return self._scene

    def set_node_movement_callback(self, callback) -> None:  # type: ignore[no-untyped-def]
        """Install a hook fired after a node is moved.

        Used by the view to refresh edge paths (we listen to
        ``QGraphicsItem.itemChange(ItemPositionHasChanged)`` for
        every node registered in the scene).
        """
        self._on_node_moved = callback

    # ----- Toolbar --------------------------------------------------------

    def _build_toolbar(self) -> None:
        self._toolbar = QToolBar(self)
        self._toolbar.setMovable(False)
        self._toolbar.setIconSize(self._toolbar.iconSize())
        validate_btn = QPushButton("Validar", self)
        validate_btn.setToolTip("Rodar o SAT solver no modelo atual")
        validate_btn.clicked.connect(self.validate_requested.emit)
        self._toolbar.addWidget(validate_btn)
        generate_btn = QPushButton("Gerar Produto", self)
        generate_btn.setToolTip("Renderizar os templates Jinja2 no diretório escolhido")
        generate_btn.clicked.connect(self.generate_requested.emit)
        self._toolbar.addWidget(generate_btn)
        clear_btn = QPushButton("Limpar", self)
        clear_btn.setToolTip("Remover todos os nós e arestas")
        clear_btn.clicked.connect(self._scene.clear)
        self._toolbar.addWidget(clear_btn)
        # Mount the toolbar across the top of the view (QToolBar can
        # only be added via addToolBar in QMainWindow, but here we
        # own the view directly — wrap it in a top widget instead).
        wrapper = QWidget(self)
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._toolbar)
        layout.addStretch(1)
        self._toolbar_wrapper = wrapper

    def resizeEvent(self, event) -> None:  # noqa: N802 — Qt API
        super().resizeEvent(event)
        # Pin the toolbar to the top edge of the view.
        tb_size = self._toolbar_wrapper.sizeHint()
        self._toolbar_wrapper.setGeometry(
            0, 0, self.width(), tb_size.height(),
        )
        # Keep the viewport below the toolbar.
        self.setViewportMargins(0, tb_size.height(), 0, 0)

    # ----- Zoom -----------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        """Ctrl+wheel zooms; otherwise delegate to scroll behavior."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            angle = event.angleDelta().y()
            factor = 1.15 if angle > 0 else 1.0 / 1.15
            self.scale(factor, factor)
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        """Delete key removes the current selection."""
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            selected_nodes = [
                item for item in self._scene.selectedItems()
                if isinstance(item, __import__(
                    "app.ui.lps_node_item", fromlist=["LpsNodeItem"]
                ).LpsNodeItem)
            ]
            for n in selected_nodes:
                self._scene.remove_node(n.node_id)
            for edge in [
                item for item in self._scene.selectedItems()
                if isinstance(item, __import__(
                    "app.ui.lps_edge_item", fromlist=["LpsEdgeItem"]
                ).LpsEdgeItem)
            ]:
                self._scene.remove_edge(edge.edge_id)
            event.accept()
            return
        super().keyPressEvent(event)

    # ----- Drag/drop ------------------------------------------------------

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        # Forward to scene (which checks the MIME type).
        self._scene.dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        self._scene.dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        self._scene.dropEvent(event)

    # ----- Edge-drag preview line -----------------------------------------

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # noqa: N802
        if self._scene.is_dragging_edge():
            scene_pos = self.mapToScene(event.pos())
            self._scene.update_edge_drag(scene_pos)
            self._update_preview_line(scene_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)
        # On every move, refresh edge paths in case a node moved
        # without firing itemChange (e.g. programmatic move).
        self._scene.refresh_all_edge_paths()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # noqa: N802
        if self._scene.is_dragging_edge():
            scene_pos = self.mapToScene(event.pos())
            self._scene.end_edge_drag(scene_pos)
            self._hide_preview_line()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _update_preview_line(self, end_pos: QPointF) -> None:
        """Draw a dashed line from the source anchor to ``end_pos``."""
        scene = self._scene
        # Find the source node + side via the scene's drag state.
        # We don't have direct access here, so we ask the scene for
        # the last drag pos and recompute the source from there:
        # the first selected node's anchor on the side the user pressed.
        # Simpler approach: stash the source anchor pos on the scene.
        src_pos = getattr(scene, "_drag_source_pos", None)
        if src_pos is None:
            # Lazy init: compute from the current drag state.
            info = getattr(scene, "_drag_source", None)
            if info is not None:
                node = scene.get_node(info.node_id)
                if node is not None:
                    src_pos = node.anchor_center(info.side)
                    scene._drag_source_pos = src_pos
        if src_pos is None:
            return
        if self._preview_line is None:
            self._preview_line = QGraphicsLineItem()
            pen = QPen(QColor("#ffd166"), 2.0)
            pen.setStyle(Qt.PenStyle.DashLine)
            self._preview_line.setPen(pen)
            self._preview_line.setZValue(5.0)
            scene.addItem(self._preview_line)
        self._preview_line.setLine(src_pos.x(), src_pos.y(), end_pos.x(), end_pos.y())

    def _hide_preview_line(self) -> None:
        if self._preview_line is not None:
            self._scene.removeItem(self._preview_line)
            self._preview_line = None
        # Clear the cached source pos so the next drag starts fresh.
        if hasattr(self._scene, "_drag_source_pos"):
            del self._scene._drag_source_pos
