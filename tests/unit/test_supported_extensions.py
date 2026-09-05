"""Parametrized tests for the supported file extensions whitelist."""

from __future__ import annotations

import pytest

from app.ui.file_inspector import SUPPORTED_EXTENSIONS


@pytest.mark.parametrize(
    "ext",
    [".py", ".ts", ".tsx", ".jsx", ".js", ".java", ".json", ".md", ".txt"],
)
def test_supported_extensions_include_common_code_and_text_files(ext: str) -> None:
    assert ext in SUPPORTED_EXTENSIONS


@pytest.mark.parametrize(
    "ext",
    [".exe", ".dll", ".png", ".jpg", ".jpeg", ".pdf", ".zip", ".docx", ".pptx", ".xlsx"],
)
def test_supported_extensions_exclude_binaries_and_archives(ext: str) -> None:
    assert ext not in SUPPORTED_EXTENSIONS


def test_supported_extensions_is_immutable() -> None:
    """frozenset has no add/remove — prevents accidental mutation."""
    assert isinstance(SUPPORTED_EXTENSIONS, frozenset)
