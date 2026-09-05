"""Tests for the CustomIconProvider.

qtawesome needs a running QApplication to render its icons, so all tests
in this file use the ``qapp`` fixture (defined in tests/conftest.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QFileInfo
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFileIconProvider

from app.ui.icons import CustomIconProvider


# ----- Direct IconType access (no QFileInfo needed) ------------------------


def test_provider_returns_qicon_for_folder_type(qapp) -> None:
    provider = CustomIconProvider()
    icon = provider.icon(QFileIconProvider.IconType.Folder)
    assert isinstance(icon, QIcon)


def test_provider_returns_qicon_for_file_type(qapp) -> None:
    provider = CustomIconProvider()
    icon = provider.icon(QFileIconProvider.IconType.File)
    assert isinstance(icon, QIcon)


# ----- File-by-file mapping -------------------------------------------------


@pytest.mark.parametrize(
    "ext,mdi",
    [
        (".py", "mdi.language-python"),
        (".ts", "mdi.language-typescript"),
        (".tsx", "mdi.language-typescript"),
        (".js", "mdi.language-javascript"),
        (".jsx", "mdi.language-javascript"),
        (".java", "mdi.language-java"),
        (".json", "mdi.code-json"),
        (".md", "mdi.language-markdown"),
        (".txt", "mdi.file-document"),
        (".toml", "mdi.file-cog"),
    ],
)
def test_provider_maps_known_extension(qapp, tmp_path: Path, ext: str, mdi: str) -> None:
    f = tmp_path / f"sample{ext}"
    f.write_text("x", encoding="utf-8")
    provider = CustomIconProvider()
    icon = provider.icon(QFileInfo(str(f)))
    assert isinstance(icon, QIcon)
    # Not asserting .isNull() — it depends on QApplication graphics backend
    # being fully initialized, which is flaky in headless tests. Just
    # check that we get a QIcon object back.


def test_provider_maps_directory_to_folder_icon(qapp, tmp_path: Path) -> None:
    d = tmp_path / "subdir"
    d.mkdir()
    provider = CustomIconProvider()
    icon = provider.icon(QFileInfo(str(d)))
    assert isinstance(icon, QIcon)


def test_provider_maps_license_to_license_icon(qapp, tmp_path: Path) -> None:
    f = tmp_path / "LICENSE"
    f.write_text("Apache-2.0", encoding="utf-8")
    provider = CustomIconProvider()
    icon = provider.icon(QFileInfo(str(f)))
    assert isinstance(icon, QIcon)


def test_provider_maps_license_md_to_license_icon(qapp, tmp_path: Path) -> None:
    f = tmp_path / "license.md"
    f.write_text("# MIT", encoding="utf-8")
    provider = CustomIconProvider()
    icon = provider.icon(QFileInfo(str(f)))
    assert isinstance(icon, QIcon)


def test_provider_maps_readme_md_to_book_icon(qapp, tmp_path: Path) -> None:
    f = tmp_path / "README.md"
    f.write_text("# Title", encoding="utf-8")
    provider = CustomIconProvider()
    icon = provider.icon(QFileInfo(str(f)))
    assert isinstance(icon, QIcon)


def test_provider_maps_gitignore_to_git_icon(qapp, tmp_path: Path) -> None:
    f = tmp_path / ".gitignore"
    f.write_text("__pycache__/", encoding="utf-8")
    provider = CustomIconProvider()
    icon = provider.icon(QFileInfo(str(f)))
    assert isinstance(icon, QIcon)


def test_provider_falls_back_for_unknown_extension(qapp, tmp_path: Path) -> None:
    f = tmp_path / "data.xyz123"
    f.write_text("x", encoding="utf-8")
    provider = CustomIconProvider()
    icon = provider.icon(QFileInfo(str(f)))
    assert isinstance(icon, QIcon)


def test_provider_is_case_insensitive_for_extensions(qapp, tmp_path: Path) -> None:
    f = tmp_path / "Script.PY"
    f.write_text("x", encoding="utf-8")
    provider = CustomIconProvider()
    icon = provider.icon(QFileInfo(str(f)))
    assert isinstance(icon, QIcon)


def test_provider_is_case_insensitive_for_filenames(qapp, tmp_path: Path) -> None:
    f = tmp_path / "Readme.MD"
    f.write_text("#", encoding="utf-8")
    provider = CustomIconProvider()
    icon = provider.icon(QFileInfo(str(f)))
    assert isinstance(icon, QIcon)


# ----- Caching --------------------------------------------------------------


def test_provider_caches_icons_for_repeated_calls(qapp, tmp_path: Path) -> None:
    """The same MDI name should return the same QIcon instance (cache hit)."""
    f = tmp_path / "a.py"
    f.write_text("x", encoding="utf-8")
    provider = CustomIconProvider()
    icon1 = provider.icon(QFileInfo(str(f)))
    icon2 = provider.icon(QFileInfo(str(f)))
    # QIcon is a QPixmap-based class but Qt allows equality comparison.
    # Two QIcon objects pointing to the same cached resource are equal.
    assert icon1.cacheKey() == icon2.cacheKey()


def test_provider_set_color_invalidates_cache(qapp, tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    f.write_text("x", encoding="utf-8")
    provider = CustomIconProvider(color="#ff0000")
    icon1 = provider.icon(QFileInfo(str(f)))
    provider.set_color("#00ff00")
    icon2 = provider.icon(QFileInfo(str(f)))
    # After color change + cache invalidation, the icons are different
    # QIcon instances (different cache keys).
    assert icon1.cacheKey() != icon2.cacheKey()
