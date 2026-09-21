"""LpsPalettePanel — draggable list of components for the LPS canvas (Change 007).

Shows the available :class:`LpsComponent`s on the left side of the
LPS mode. The user drags an item onto the canvas (or clicks ``+Node``
to add an empty stub) and the scene creates a matching node.

MIME type: ``application/x-lps-component`` carries a JSON blob
``{"component_id": str, "name": str, "category": str}`` so the
scene's :meth:`LpsCanvasScene.dropEvent` can recreate the node.

The panel does NOT call LpsService directly — it's a pure widget over
a list of pre-fetched components. The MainWindow seeds the list on
``refresh()`` (called after the user opens the panel or after a
new component is added via the inspector).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable

from PySide6.QtCore import QByteArray, QMimeData, Qt
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services import LpsComponent
from app.ui.lps_canvas_scene import LPS_COMPONENT_MIME


@dataclass(frozen=True)
class PaletteItem:
    """One entry in the palette list.

    Kept simple (frozen dataclass) so the panel can be repopulated
    cheaply by the MainWindow without going through the DB every
    paint cycle.
    """

    component_id: str
    name: str
    category: str


class LpsPalettePanel(QWidget):
    """Left-column panel of the LPS mode."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: list[PaletteItem] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Toolbar (refresh + clear) ------------------------------------
        tb = QWidget(self)
        tb_layout = QHBoxLayout(tb)
        tb_layout.setContentsMargins(4, 4, 4, 4)
        self._refresh_btn = QPushButton("Atualizar", tb)
        self._refresh_btn.setToolTip("Recarregar componentes do SQLite")
        self._refresh_btn.clicked.connect(self.refresh_requested.emit)
        tb_layout.addWidget(self._refresh_btn)
        tb_layout.addStretch(1)
        layout.addWidget(tb)

        # --- List ----------------------------------------------------------
        self._list = QListWidget(self)
        self._list.setDragEnabled(True)
        self._list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._list.setUniformItemSizes(True)
        self._list.setAlternatingRowColors(True)
        layout.addWidget(self._list, stretch=1)

        # --- Status footer -------------------------------------------------
        self._status = QLabel(self)
        self._status.setContentsMargins(6, 2, 6, 2)
        layout.addWidget(self._status)

        self._update_status()

    # ----- Public API -----------------------------------------------------

    def set_components(self, components: Iterable[LpsComponent]) -> None:
        """Replace the list with the given components."""
        self._items = [
            PaletteItem(
                component_id=c.id, name=c.name, category=c.category,
            )
            for c in components
        ]
        self._rebuild_list()

    def clear(self) -> None:
        """Empty the palette."""
        self._items = []
        self._rebuild_list()

    def selected_item(self) -> PaletteItem | None:
        """Return the currently selected palette item, or ``None``."""
        row = self._list.currentRow()
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def count(self) -> int:
        return len(self._items)

    # ----- Signals --------------------------------------------------------

    from PySide6.QtCore import Signal
    item_activated = Signal(str)         # component_id (double-click)
    refresh_requested = Signal()         # user clicked "Atualizar"

    # ----- Internal -------------------------------------------------------

    def _rebuild_list(self) -> None:
        self._list.clear()
        for item in self._items:
            qitem = QListWidgetItem(self._format_label(item))
            qitem.setData(Qt.ItemDataRole.UserRole, item.component_id)
            qitem.setToolTip(f"ID: {item.component_id}\nCategoria: {item.category}")
            self._list.addItem(qitem)
        self._update_status()

    @staticmethod
    def _format_label(item: PaletteItem) -> str:
        return f"{item.name}  ({item.category})"

    def _update_status(self) -> None:
        n = len(self._items)
        if n == 0:
            self._status.setText("Nenhum componente — clique em Atualizar")
        elif n == 1:
            self._status.setText("1 componente")
        else:
            self._status.setText(f"{n} componentes")

    # ----- Drag start -----------------------------------------------------

    def startDrag(self, supportedActions) -> None:  # noqa: N802
        """QAbstractItemView.startDrag override — emit our MIME payload.

        The default Qt drag would only carry the QListWidgetItem's
        text. We override to ship the JSON the canvas scene expects.
        """
        current = self._list.currentItem()
        if current is None:
            return
        row = self._list.row(current)
        if not (0 <= row < len(self._items)):
            return
        item = self._items[row]
        payload = json.dumps({
            "component_id": item.component_id,
            "name": item.name,
            "category": item.category,
        })
        mime = QMimeData()
        mime.setData(LPS_COMPONENT_MIME, QByteArray(payload.encode("utf-8")))
        # Also set plain text so external drop targets (debuggers)
        # can see something readable.
        mime.setText(item.name)
        drag = QDrag(self._list)
        drag.setMimeData(mime)
        drag.exec(supportedActions)
