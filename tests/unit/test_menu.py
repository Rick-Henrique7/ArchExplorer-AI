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
    menubar = window.menuBar()
    view_action = next(a for a in menubar.actions() if "View" in a.text())
    view_menu = view_action.menu()
    assert view_menu is not None
    submenu_titles = [a.text() for a in view_menu.actions() if a.menu() is not None]
    assert any("Theme" in t for t in submenu_titles)


def test_theme_submenu_has_dark_light_system_actions(qapp, tmp_path: Path) -> None:
    window = _make_window_with_theme(qapp, tmp_path)
    menubar = window.menuBar()
    view_action = next(a for a in menubar.actions() if "View" in a.text())
    view_menu = view_action.menu()
    theme_action = next(a for a in view_menu.actions() if a.menu() is not None)
    theme_menu = theme_action.menu()
    labels = {a.text() for a in theme_menu.actions()}
    assert {"Dark", "Light", "System"} <= labels


def test_exactly_one_theme_action_is_checked(qapp, tmp_path: Path) -> None:
    window = _make_window_with_theme(qapp, tmp_path, theme=Theme.DARK)
    menubar = window.menuBar()
    view_action = next(a for a in menubar.actions() if "View" in a.text())
    view_menu = view_action.menu()
    theme_action = next(a for a in view_menu.actions() if a.menu() is not None)
    theme_menu = theme_action.menu()
    checked = [a for a in theme_menu.actions() if a.isChecked()]
    assert len(checked) == 1
    assert checked[0].text() == "Dark"


def test_checked_action_reflects_current_theme(qapp, tmp_path: Path) -> None:
    window = _make_window_with_theme(qapp, tmp_path, theme=Theme.LIGHT)
    menubar = window.menuBar()
    view_action = next(a for a in menubar.actions() if "View" in a.text())
    view_menu = view_action.menu()
    theme_action = next(a for a in view_menu.actions() if a.menu() is not None)
    theme_menu = theme_action.menu()
    checked = [a for a in theme_menu.actions() if a.isChecked()]
    assert checked[0].text() == "Light"


def test_toggle_theme_shortcut_registered(qapp, tmp_path: Path) -> None:
    """Ctrl+Shift+T is bound to the 'Toggle Theme' action."""
    window = _make_window_with_theme(qapp, tmp_path)
    menubar = window.menuBar()
    view_action = next(a for a in menubar.actions() if "View" in a.text())
    view_menu = view_action.menu()
    toggle = next(a for a in view_menu.actions() if "Toggle" in a.text())
    assert toggle.shortcut() == QKeySequence("Ctrl+Shift+T")
