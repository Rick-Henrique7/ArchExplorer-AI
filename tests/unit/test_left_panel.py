"""Tests for LeftPanel — the QStackedWidget container (Change 006 — Bloco E)."""

from __future__ import annotations

import pytest

from app.ui.catalogo_panel import CatalogoPanel
from app.ui.file_explorer import FileExplorerPanel
from app.ui.left_panel import LeftPanel, LeftPanelMode


@pytest.fixture
def left_panel(qapp, tmp_path) -> LeftPanel:
    explorer = FileExplorerPanel(root=tmp_path)
    catalog = CatalogoPanel()
    return LeftPanel(explorer=explorer, catalog=catalog)


def _visible_widget(left_panel: LeftPanel):
    """Return whichever child the QStackedWidget is currently showing.

    ``isVisible()`` is unreliable in offscreen tests (the top-level
    window was never ``show()``-ed, so every widget reports
    ``isVisible() == False``). Reading the stack's currentIndex is the
    definitive check.
    """
    return left_panel._stack.currentWidget()


def test_initial_mode_is_explorer(left_panel: LeftPanel) -> None:
    """Default constructor mode is the file tree (back-compat with Change 005)."""
    assert left_panel.current_mode() == LeftPanelMode.EXPLORER
    assert _visible_widget(left_panel) is left_panel.explorer()


def test_show_catalog_switches_visible_child(left_panel: LeftPanel) -> None:
    """``show_catalog()`` reveals the catalog and hides the explorer."""
    left_panel.show_catalog()
    assert left_panel.current_mode() == LeftPanelMode.CATALOG
    assert _visible_widget(left_panel) is left_panel.catalog()


def test_show_explorer_returns_to_file_tree(left_panel: LeftPanel) -> None:
    """Round-trip explorer -> catalog -> explorer."""
    left_panel.show_catalog()
    left_panel.show_explorer()
    assert left_panel.current_mode() == LeftPanelMode.EXPLORER
    assert _visible_widget(left_panel) is left_panel.explorer()


def test_mode_changed_signal_emits_on_transition(qapp, tmp_path) -> None:
    """Signal fires only on actual transitions, not on no-op calls."""
    explorer = FileExplorerPanel(root=tmp_path)
    catalog = CatalogoPanel()
    panel = LeftPanel(explorer=explorer, catalog=catalog)

    received: list[str] = []
    panel.mode_changed.connect(received.append)

    # No-op: still in EXPLORER → must not fire.
    panel.show_explorer()
    assert received == []

    # Real transition.
    panel.show_catalog()
    assert received == [LeftPanelMode.CATALOG.value]

    # Another transition back.
    panel.show_explorer()
    assert received == [LeftPanelMode.CATALOG.value, LeftPanelMode.EXPLORER.value]


def test_show_mode_accepts_string(qapp, tmp_path) -> None:
    """``show_mode`` accepts the enum or its string value."""
    explorer = FileExplorerPanel(root=tmp_path)
    catalog = CatalogoPanel()
    panel = LeftPanel(explorer=explorer, catalog=catalog)

    panel.show_mode("catalog")
    assert panel.current_mode() == LeftPanelMode.CATALOG

    panel.show_mode(LeftPanelMode.EXPLORER)
    assert panel.current_mode() == LeftPanelMode.EXPLORER


def test_show_mode_with_unknown_string_is_noop(qapp, tmp_path) -> None:
    """Unknown string keeps the current mode (defensive)."""
    explorer = FileExplorerPanel(root=tmp_path)
    catalog = CatalogoPanel()
    panel = LeftPanel(explorer=explorer, catalog=catalog)

    received: list[str] = []
    panel.mode_changed.connect(received.append)

    panel.show_mode("not_a_mode")
    assert panel.current_mode() == LeftPanelMode.EXPLORER
    assert received == []  # signal must not fire for invalid input


def test_state_preserved_across_toggle(qapp, tmp_path) -> None:
    """Children are kept alive — switching back exposes the same widget."""
    explorer = FileExplorerPanel(root=tmp_path)
    catalog = CatalogoPanel()
    panel = LeftPanel(explorer=explorer, catalog=catalog)

    panel.show_catalog()
    same_catalog = panel.catalog()
    panel.show_explorer()
    panel.show_catalog()
    # Identity check — proves the widget wasn't recreated.
    assert panel.catalog() is same_catalog


def test_initial_mode_can_be_catalog(qapp, tmp_path) -> None:
    """Restore path: starting in CATALOG mode for users who prefer it."""
    explorer = FileExplorerPanel(root=tmp_path)
    catalog = CatalogoPanel()
    panel = LeftPanel(
        explorer=explorer, catalog=catalog, initial_mode=LeftPanelMode.CATALOG
    )
    assert panel.current_mode() == LeftPanelMode.CATALOG
    assert _visible_widget(panel) is panel.catalog()


def test_lps_mode_starts_and_switches(qapp, tmp_path) -> None:
    """Change 007: LPS mode is the 3rd value of LeftPanelMode."""
    from app.ui.lps_palette_panel import LpsPalettePanel
    explorer = FileExplorerPanel(root=tmp_path)
    catalog = CatalogoPanel()
    palette = LpsPalettePanel()
    panel = LeftPanel(
        explorer=explorer, catalog=catalog, palette=palette,
        initial_mode=LeftPanelMode.LPS,
    )
    assert panel.current_mode() == LeftPanelMode.LPS
    assert _visible_widget(panel) is palette
    panel.show_explorer()
    assert panel.current_mode() == LeftPanelMode.EXPLORER
    panel.show_lps()
    assert panel.current_mode() == LeftPanelMode.LPS
    assert _visible_widget(panel) is palette


def test_palette_accessor_returns_none_when_not_provided(qapp, tmp_path) -> None:
    """Legacy 2-mode constructor leaves palette=None."""
    explorer = FileExplorerPanel(root=tmp_path)
    catalog = CatalogoPanel()
    panel = LeftPanel(explorer=explorer, catalog=catalog)
    assert panel.palette() is None


def test_palette_mode_is_unknown_when_palette_missing(qapp, tmp_path) -> None:
    """Without a palette widget, show_lps() is a no-op (no crash)."""
    explorer = FileExplorerPanel(root=tmp_path)
    catalog = CatalogoPanel()
    panel = LeftPanel(explorer=explorer, catalog=catalog)
    received: list[str] = []
    panel.mode_changed.connect(received.append)
    panel.show_lps()
    # Mode doesn't actually flip because there's no palette widget
    # to show; the signal must NOT fire (avoids stale state).
    assert received == []
    assert panel.current_mode() == LeftPanelMode.EXPLORER
