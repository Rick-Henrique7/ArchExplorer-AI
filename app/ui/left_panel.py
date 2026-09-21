"""Left column container — toggles between FileExplorerPanel and CatalogoPanel.

Change 006 introduces a second mode for the left column: instead of
always showing the file tree, the user can flip to the personal catalog
via ``View > Painel esquerdo > Catálogo`` (Ctrl+2) and back to the file
tree via ``View > Painel esquerdo > Projeto`` (Ctrl+1).

Why a ``QStackedWidget`` instead of hide/show? Both children stay
constructed (no rebuild cost on toggle), retain their scroll position,
selection state, and any in-flight search. Hide/show would force a
reflow on the splitter and lose state.
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from app.ui.catalogo_panel import CatalogoPanel
from app.ui.file_explorer import FileExplorerPanel


class LeftPanelMode(str, Enum):
    """Identifier for the active left-column mode.

    Inherits from ``str`` so :attr:`LeftPanel.mode_changed` payloads
    can be compared against the enum or used as QSettings keys.

    The values are NOT just for the left column — they're the
    application's "operating mode". Switching to LPS swaps all three
    columns: palette (left), canvas (center), inspector (right).
    """

    EXPLORER = "explorer"
    CATALOG = "catalog"
    LPS = "lps"


class LeftPanel(QWidget):
    """Container that swaps between :class:`FileExplorerPanel` and :class:`CatalogoPanel`.

    Both children are constructed up-front and stacked. Toggling via
    :meth:`show_explorer` / :meth:`show_catalog` (or the enum version
    :meth:`show_mode`) preserves their state across switches.

    Signals:
    - :attr:`mode_changed` — emitted with the new
      :class:`LeftPanelMode` value whenever the stack index flips. The
      MainWindow listens to this to update the View menu check-state
      and persist the choice in QSettings.
    """

    mode_changed = Signal(str)   # LeftPanelMode.value

    def __init__(
        self,
        explorer: FileExplorerPanel,
        catalog: CatalogoPanel,
        palette: object | None = None,
        initial_mode: LeftPanelMode = LeftPanelMode.EXPLORER,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._explorer = explorer
        self._catalog = catalog
        # ``palette`` is optional for back-compat with the original
        # 2-mode constructor. When provided, it's shown in LPS mode.
        self._palette = palette

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget(self)
        # addWidget order defines indices — keep these stable, the
        # ``LeftPanelMode`` values are intentionally aligned.
        self._explorer_index = self._stack.addWidget(self._explorer)  # 0
        self._catalog_index = self._stack.addWidget(self._catalog)    # 1
        self._palette_index = (
            self._stack.addWidget(self._palette) if self._palette is not None else 1
        )                                                          # 2 (or 1 fallback)
        layout.addWidget(self._stack)

        # Initial mode (do not emit on construction; the MainWindow
        # already knows which mode it asked for).
        self._current_mode: LeftPanelMode = initial_mode
        self._stack.setCurrentIndex(self._index_for(initial_mode))

    # ----- Public API -------------------------------------------------------

    def show_explorer(self) -> None:
        """Switch the stack to the file tree."""
        self._switch_to(LeftPanelMode.EXPLORER)

    def show_catalog(self) -> None:
        """Switch the stack to the catalog."""
        self._switch_to(LeftPanelMode.CATALOG)

    def show_lps(self) -> None:
        """Switch the stack to the LPS palette."""
        self._switch_to(LeftPanelMode.LPS)

    def show_mode(self, mode: LeftPanelMode | str) -> None:
        """Switch to ``mode`` (accepts the enum or its ``.value`` string)."""
        if isinstance(mode, str):
            try:
                mode = LeftPanelMode(mode)
            except ValueError:
                # Unknown string — keep the current mode instead of
                # silently breaking the layout.
                return
        self._switch_to(mode)

    def current_mode(self) -> LeftPanelMode:
        """Return which child is currently visible."""
        return self._current_mode

    def explorer(self) -> FileExplorerPanel:
        """Direct accessor for the file tree (used by MainWindow wiring)."""
        return self._explorer

    def catalog(self) -> CatalogoPanel:
        """Direct accessor for the catalog panel."""
        return self._catalog

    def palette(self) -> object | None:
        """Direct accessor for the LPS palette (may be ``None`` in legacy builds)."""
        return self._palette

    # ----- Internal ---------------------------------------------------------

    def _index_for(self, mode: LeftPanelMode) -> int:
        return {
            LeftPanelMode.EXPLORER: self._explorer_index,
            LeftPanelMode.CATALOG: self._catalog_index,
            LeftPanelMode.LPS: self._palette_index,
        }[mode]

    def _switch_to(self, mode: LeftPanelMode) -> None:
        if mode == self._current_mode:
            # No-op; do not emit (avoids spurious QSettings writes
            # on every menu activation).
            return
        # If LPS mode is requested without a palette widget, treat
        # as a silent no-op (legacy 2-mode builds).
        if mode == LeftPanelMode.LPS and self._palette is None:
            return
        self._current_mode = mode
        self._stack.setCurrentIndex(self._index_for(mode))
        self.mode_changed.emit(mode.value)
