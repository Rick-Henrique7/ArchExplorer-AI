"""Custom QFileIconProvider backed by Material Design Icons via qtawesome.

By default, ``QFileSystemModel`` consults ``QFileIconProvider`` which on
Windows delegates to the OS file-type associations — that yields the
generic yellow folder and blank-page icons the user sees in Explorer.

This provider replaces that with a curated set of Material Design Icons
(MDI) so the project tree reads as a developer's tool, not a file
browser. Icons are cached per MDI name (1 QIcon() per name, ever).
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import qtawesome as qta
from PySide6.QtCore import QFileInfo
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFileIconProvider


class CustomIconProvider(QFileIconProvider):
    """Maps file extensions and special filenames to Material Design Icons."""

    EXTENSION_ICONS: Final[dict[str, str]] = {
        ".py": "mdi.language-python",
        ".ts": "mdi.language-typescript",
        ".tsx": "mdi.language-typescript",
        ".js": "mdi.language-javascript",
        ".jsx": "mdi.language-javascript",
        ".java": "mdi.language-java",
        ".json": "mdi.code-json",
        ".md": "mdi.language-markdown",
        ".txt": "mdi.file-document",
        ".toml": "mdi.file-cog",
        ".yaml": "mdi.file-cog",
        ".yml": "mdi.file-cog",
    }

    FILENAME_ICONS: Final[dict[str, str]] = {
        "license": "mdi.license",
        "license.md": "mdi.license",
        "license.txt": "mdi.license",
        "readme.md": "mdi.book-open-variant",
        "readme.txt": "mdi.book-open-variant",
        ".gitignore": "mdi.git",
        ".gitattributes": "mdi.git",
        "dockerfile": "mdi.docker",
        "makefile": "mdi.console",
    }

    DEFAULT_FILE_ICON: Final[str] = "mdi.file"
    DEFAULT_DIR_ICON: Final[str] = "mdi.folder"

    def __init__(self, color: str | None = None) -> None:
        super().__init__()
        self._color = color
        self._cache: dict[str, QIcon] = {}

    def icon(self, argument) -> QIcon:  # type: ignore[override]
        """Return the QIcon for a file/dir or IconType enum.

        ``QFileIconProvider.icon`` is overloaded — it can be called with
        a :class:`QFileInfo` (file-by-file case) or with an
        :class:`QFileIconProvider.IconType` enum (e.g. for the empty
        area of the tree view). We handle both.
        """
        if isinstance(argument, QFileInfo):
            return self._icon_for_path(Path(argument.filePath()))
        if argument == QFileIconProvider.IconType.Folder:
            return self._get_cached(self.DEFAULT_DIR_ICON)
        # File, Drive, Computer, Network, etc. — all fall back to file.
        return self._get_cached(self.DEFAULT_FILE_ICON)

    def _icon_for_path(self, path: Path) -> QIcon:
        if path.is_dir():
            return self._get_cached(self.DEFAULT_DIR_ICON)
        name_lower = path.name.lower()
        if name_lower in self.FILENAME_ICONS:
            return self._get_cached(self.FILENAME_ICONS[name_lower])
        suffix_lower = path.suffix.lower()
        if suffix_lower in self.EXTENSION_ICONS:
            return self._get_cached(self.EXTENSION_ICONS[suffix_lower])
        return self._get_cached(self.DEFAULT_FILE_ICON)

    def _get_cached(self, mdi_name: str) -> QIcon:
        if mdi_name not in self._cache:
            kwargs: dict = {}
            if self._color is not None:
                kwargs["color"] = self._color
            self._cache[mdi_name] = qta.icon(mdi_name, **kwargs)
        return self._cache[mdi_name]

    def set_color(self, color: str | None) -> None:
        """Change the icon color and invalidate the cache.

        Useful when the theme changes (a future change can wire this up
        to ``ThemeManager`` so icons follow light/dark palette).
        """
        self._color = color
        self._cache.clear()
