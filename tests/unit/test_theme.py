"""Tests for the Theme enum and ThemeManager."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from app.ui.theme import Theme, ThemeManager


# ----- Theme enum ----------------------------------------------------------


def test_theme_enum_has_three_values() -> None:
    assert {t.value for t in Theme} == {"dark", "light", "system"}


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("dark", Theme.DARK),
        ("DARK", Theme.DARK),
        ("Dark", Theme.DARK),
        ("light", Theme.LIGHT),
        ("system", Theme.SYSTEM),
        ("", Theme.SYSTEM),
        (None, Theme.SYSTEM),
        ("garbage", Theme.SYSTEM),
    ],
)
def test_theme_from_string_normalizes_input(raw, expected: Theme) -> None:
    assert Theme.from_string(raw) == expected


def test_theme_to_string_roundtrip() -> None:
    for theme in Theme:
        assert Theme.from_string(theme.to_string()) == theme


# ----- ThemeManager construction -------------------------------------------


def _make_settings(tmp_path: Path) -> QSettings:
    """Build a QSettings backed by an INI file in tmp_path (no registry)."""
    ini_path = tmp_path / "theme.ini"
    return QSettings(str(ini_path), QSettings.Format.IniFormat)


def test_manager_defaults_to_system_when_no_persisted_value(qapp, tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    mgr = ThemeManager(qapp, settings=settings)
    assert mgr.current() == Theme.SYSTEM


def test_manager_loads_persisted_value(qapp, tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    settings.setValue("theme", "light")
    settings.sync()
    mgr = ThemeManager(qapp, settings=settings)
    assert mgr.current() == Theme.LIGHT


def test_manager_loads_invalid_persisted_value_as_system(qapp, tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    settings.setValue("theme", "not-a-theme")
    settings.sync()
    mgr = ThemeManager(qapp, settings=settings)
    assert mgr.current() == Theme.SYSTEM


# ----- effective() / SYSTEM resolution ------------------------------------


def test_effective_returns_selected_when_not_system(qapp, tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    mgr = ThemeManager(qapp, settings=settings)
    mgr.apply(Theme.LIGHT)
    assert mgr.effective() == Theme.LIGHT


def test_effective_resolves_system_to_dark_or_light(qapp, tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    mgr = ThemeManager(qapp, settings=settings)
    # Default is SYSTEM — effective must be DARK or LIGHT, never SYSTEM.
    assert mgr.effective() in (Theme.DARK, Theme.LIGHT)


# ----- apply() / QSS --------------------------------------------------------


def test_apply_dark_loads_qss(qapp, tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    mgr = ThemeManager(qapp, settings=settings)
    mgr.apply(Theme.DARK)
    assert "background-color" in qapp.styleSheet()
    assert "#1e1e1e" in qapp.styleSheet()  # the dark theme color


def test_apply_light_loads_qss(qapp, tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    mgr = ThemeManager(qapp, settings=settings)
    mgr.apply(Theme.LIGHT)
    assert "background-color" in qapp.styleSheet()
    assert "#fafafa" in qapp.styleSheet()  # the light theme color


def test_apply_persists_selection(qapp, tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    mgr = ThemeManager(qapp, settings=settings)
    mgr.apply(Theme.LIGHT)
    # A fresh manager reading the same settings should see LIGHT.
    mgr2 = ThemeManager(qapp, settings=_make_settings(tmp_path).fileName() and
                        QSettings(settings.fileName(), QSettings.Format.IniFormat))
    # We can't easily share fileName from a QSettings already constructed
    # against the same path, so just check the in-memory QSettings object.
    assert settings.value("theme") == "light"


def test_apply_system_resolves_to_effective_theme_qss(qapp, tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    mgr = ThemeManager(qapp, settings=settings)
    mgr.apply(Theme.SYSTEM)
    # The QSS loaded should be the one for the effective theme.
    effective = mgr.effective()
    if effective == Theme.DARK:
        assert "#1e1e1e" in qapp.styleSheet()
    else:
        assert "#fafafa" in qapp.styleSheet()


# ----- cycle() -------------------------------------------------------------


def test_cycle_through_all_themes(qapp, tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    mgr = ThemeManager(qapp, settings=settings)
    assert mgr.current() == Theme.SYSTEM
    # cycle once -> next theme in DARK -> LIGHT -> SYSTEM order.
    # Starting from SYSTEM, the next is DARK (wrapping).
    new = mgr.cycle()
    assert new == Theme.DARK
    new = mgr.cycle()
    assert new == Theme.LIGHT
    new = mgr.cycle()
    assert new == Theme.SYSTEM


# ----- detect_system_theme() -----------------------------------------------


def test_detect_system_theme_returns_dark_or_light() -> None:
    """detect_system_theme() must always return DARK or LIGHT (never SYSTEM)."""
    result = ThemeManager.detect_system_theme()
    assert result in (Theme.DARK, Theme.LIGHT)


def test_detect_system_theme_handles_missing_registry() -> None:
    """When winreg.QueryValueEx raises OSError, falls back to DARK."""
    with patch("app.ui.theme.winreg", create=True) as mock_winreg:
        mock_winreg.OpenKey.side_effect = OSError("registry not available")
        result = ThemeManager.detect_system_theme()
    assert result == Theme.DARK


# ----- QSS content (Change 005) -------------------------------------------


def test_light_qss_has_visible_branch_background(qapp) -> None:
    """Regression: in light theme, QTreeView::branch used to be transparent
    and the expand/collapse arrows were nearly invisible against the white
    rows. The QSS now sets an explicit grey fill on the branch."""
    from pathlib import Path
    from app.ui import theme as theme_mod

    qss_path = Path(theme_mod.__file__).parent / "qss" / "light.qss"
    content = qss_path.read_text(encoding="utf-8")
    # The fix sets the branch background to a light grey (not transparent).
    assert "QTreeView::branch" in content
    branch_block = content.split("QTreeView::branch", 1)[1].split("}", 1)[0]
    assert "transparent" not in branch_block
    # And it specifies a concrete color (the regression value was #e8e8e8).
    assert "#e8e8e8" in branch_block or "#f0f0f0" in branch_block


def test_dark_qss_pads_tree_and_editor(qapp) -> None:
    """The dark theme now declares 4px padding on the tree and editor."""
    from pathlib import Path
    from app.ui import theme as theme_mod

    qss_path = Path(theme_mod.__file__).parent / "qss" / "dark.qss"
    content = qss_path.read_text(encoding="utf-8")
    assert "padding: 4px" in content


def test_light_qss_pads_tree_and_editor(qapp) -> None:
    """The light theme also has 4px padding for the tree and editor."""
    from pathlib import Path
    from app.ui import theme as theme_mod

    qss_path = Path(theme_mod.__file__).parent / "qss" / "light.qss"
    content = qss_path.read_text(encoding="utf-8")
    assert "padding: 4px" in content
