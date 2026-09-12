"""Tests for the View > Theme menu in MainWindow."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow
from app.ui.theme import Theme, ThemeManager


def _make_settings(tmp_path: Path) -> QSettings:
    ini_path = tmp_path / "theme.ini"
    return QSettings(str(ini_path), QSettings.Format.IniFormat)


def _make_window_with_theme(qapp, tmp_path: Path, theme: Theme = Theme.DARK) -> MainWindow:
    settings = _make_settings(tmp_path)
    mgr = ThemeManager(qapp, settings=settings)
    mgr.apply(theme)
    window = MainWindow(theme_manager=mgr)
    return window


def _view_menu(window: MainWindow):
    menubar = window.menuBar()
    view_action = next(a for a in menubar.actions() if "View" in a.text())
    assert view_action.menu() is not None
    return view_action.menu()


def _theme_menu(view_menu):
    """Find the Theme submenu specifically (Change 006 added a 'Painel esquerdo'
    submenu before it)."""
    for action in view_menu.actions():
        if action.menu() is not None and "Theme" in action.text():
            return action.menu()
    raise AssertionError("Theme submenu not found")


def _left_menu(view_menu):
    """Find the 'Painel esquerdo' submenu (Change 006)."""
    for action in view_menu.actions():
        if action.menu() is not None and "Painel" in action.text():
            return action.menu()
    raise AssertionError("Painel esquerdo submenu not found")


def test_window_without_theme_manager_has_no_menu(qapp) -> None:
    """A MainWindow without a ThemeManager should still work (no menu)."""
    window = MainWindow()
    # menuBar exists but has no items added by us.
    assert window.menuBar() is not None


def test_window_with_theme_manager_has_view_menu(qapp, tmp_path: Path) -> None:
    window = _make_window_with_theme(qapp, tmp_path)
    menubar = window.menuBar()
    titles = [a.text() for a in menubar.actions()]
    assert any("View" in t for t in titles)


def test_view_menu_has_theme_submenu(qapp, tmp_path: Path) -> None:
    window = _make_window_with_theme(qapp, tmp_path)
    vm = _view_menu(window)
    submenu_titles = [a.text() for a in vm.actions() if a.menu() is not None]
    assert any("Theme" in t for t in submenu_titles)


def test_view_menu_has_left_panel_submenu(qapp, tmp_path: Path) -> None:
    """Change 006: View > Painel esquerdo with Projeto/Catálogo actions."""
    window = _make_window_with_theme(qapp, tmp_path)
    vm = _view_menu(window)
    left_menu = _left_menu(vm)
    labels = {a.text() for a in left_menu.actions()}
    assert any("Projeto" in lbl for lbl in labels)
    # Mnemonic marker & sits inside the text ("Ca&tálogo"); a substring
    # check that survives the marker is enough.
    assert any("tálogo" in lbl for lbl in labels)


def test_theme_submenu_has_dark_light_system_actions(qapp, tmp_path: Path) -> None:
    window = _make_window_with_theme(qapp, tmp_path)
    vm = _view_menu(window)
    theme_menu = _theme_menu(vm)
    labels = {a.text() for a in theme_menu.actions()}
    assert {"Dark", "Light", "System"} <= labels


def test_exactly_one_theme_action_is_checked(qapp, tmp_path: Path) -> None:
    window = _make_window_with_theme(qapp, tmp_path, theme=Theme.DARK)
    vm = _view_menu(window)
    theme_menu = _theme_menu(vm)
    checked = [a for a in theme_menu.actions() if a.isChecked()]
    assert len(checked) == 1
    assert checked[0].text() == "Dark"


def test_checked_action_reflects_current_theme(qapp, tmp_path: Path) -> None:
    window = _make_window_with_theme(qapp, tmp_path, theme=Theme.LIGHT)
    vm = _view_menu(window)
    theme_menu = _theme_menu(vm)
    checked = [a for a in theme_menu.actions() if a.isChecked()]
    assert checked[0].text() == "Light"


def test_toggle_theme_shortcut_registered(qapp, tmp_path: Path) -> None:
    """Ctrl+Shift+T is bound to the 'Toggle Theme' action."""
    window = _make_window_with_theme(qapp, tmp_path)
    vm = _view_menu(window)
    toggle = next(a for a in vm.actions() if "Toggle" in a.text())
    assert toggle.shortcut() == QKeySequence("Ctrl+Shift+T")


def test_left_panel_shortcuts_ctrl1_and_ctrl2(qapp, tmp_path: Path) -> None:
    """Change 006: Ctrl+1 -> Projeto, Ctrl+2 -> Catálogo."""
    window = _make_window_with_theme(qapp, tmp_path)
    vm = _view_menu(window)
    left_menu = _left_menu(vm)
    projeto = next(a for a in left_menu.actions() if "Projeto" in a.text())
    catalogo = next(a for a in left_menu.actions() if "tálogo" in a.text())
    assert projeto.shortcut() == QKeySequence("Ctrl+1")
    assert catalogo.shortcut() == QKeySequence("Ctrl+2")
