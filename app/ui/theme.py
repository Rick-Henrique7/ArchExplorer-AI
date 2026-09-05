"""Theme management — Dark / Light / System with persistence.

The :class:`ThemeManager`:

- Loads the user's persisted preference (via :class:`QSettings`)
- Applies the matching QSS file to the :class:`QApplication`
- Detects the OS theme on Windows (via ``winreg``) when ``SYSTEM`` is
  selected
- Cycles through the 3 values for the Ctrl+Shift+T shortcut
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication


class Theme(Enum):
    """User-selectable theme."""

    DARK = "dark"
    LIGHT = "light"
    SYSTEM = "system"

    @classmethod
    def from_string(cls, value: str | None) -> "Theme":
        """Parse a string into a Theme; fall back to SYSTEM on garbage input."""
        if not value:
            return cls.SYSTEM
        try:
            return cls(value.lower())
        except ValueError:
            return cls.SYSTEM

    def to_string(self) -> str:
        return self.value


class ThemeManager:
    """Applies and persists the active theme for the running app."""

    _QSS_DIR: Path = Path(__file__).parent / "qss"
    _SETTINGS_KEY: str = "theme"

    def __init__(
        self,
        app: QApplication,
        settings: QSettings | None = None,
    ) -> None:
        self._app = app
        # Allow injecting a custom QSettings (for tests) to avoid touching
        # the real Windows registry. Default uses QApplication's org/app.
        self._settings = settings if settings is not None else QSettings()
        persisted = self._settings.value(
            self._SETTINGS_KEY, Theme.SYSTEM.value, type=str,
        )
        self._selected: Theme = Theme.from_string(persisted)

    # ----- Public API --------------------------------------------------------

    def current(self) -> Theme:
        """The user's selected theme (may be SYSTEM)."""
        return self._selected

    def effective(self) -> Theme:
        """Resolve SYSTEM to DARK or LIGHT based on the OS."""
        if self._selected == Theme.SYSTEM:
            return self.detect_system_theme()
        return self._selected

    def apply(self, theme: Theme) -> None:
        """Persist ``theme`` and load the matching QSS into the app."""
        self._selected = theme
        self._settings.setValue(self._SETTINGS_KEY, theme.to_string())
        self._settings.sync()  # write through to disk/registry immediately
        qss_text = self._load_qss(self.effective())
        self._app.setStyleSheet(qss_text)

    def cycle(self) -> Theme:
        """Advance to the next theme in DARK -> LIGHT -> SYSTEM -> DARK."""
        order = [Theme.DARK, Theme.LIGHT, Theme.SYSTEM]
        try:
            next_idx = (order.index(self._selected) + 1) % len(order)
        except ValueError:
            next_idx = 0
        self.apply(order[next_idx])
        return self._selected

    @staticmethod
    def detect_system_theme() -> Theme:
        """Read the Windows registry to determine the active OS theme.

        Returns ``DARK`` on any failure (missing key, non-Windows OS,
        ImportError) — the user's manual choice in the menu always wins.
        """
        try:
            import winreg
        except ImportError:
            return Theme.DARK
        try:
            key = winreg.OpenKey(  # type: ignore[attr-defined]
                winreg.HKEY_CURRENT_USER,  # type: ignore[attr-defined]
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")  # type: ignore[attr-defined]
            winreg.CloseKey(key)  # type: ignore[attr-defined]
            return Theme.LIGHT if value == 1 else Theme.DARK
        except OSError:
            return Theme.DARK

    # ----- Internal helpers --------------------------------------------------

    def _load_qss(self, effective: Theme) -> str:
        qss_file = self._QSS_DIR / f"{effective.value}.qss"
        if qss_file.is_file():
            return qss_file.read_text(encoding="utf-8")
        return ""  # fallback: let the OS theme paint the widgets
