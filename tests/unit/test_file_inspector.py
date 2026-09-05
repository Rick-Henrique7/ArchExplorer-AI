"""Tests for the file_inspector helper."""

from __future__ import annotations

from pathlib import Path

from app.ui.file_inspector import (
    EXTENSION_TO_FILE_TYPE,
    MAX_FILE_SIZE,
    SUPPORTED_EXTENSIONS,
    inspect_file,
)


# ----- Whitelist / mapping -------------------------------------------------


def test_python_in_whitelist() -> None:
    assert ".py" in SUPPORTED_EXTENSIONS
    assert EXTENSION_TO_FILE_TYPE[".py"] == "python"


def test_typescript_in_whitelist() -> None:
    assert ".ts" in SUPPORTED_EXTENSIONS
    assert ".tsx" in SUPPORTED_EXTENSIONS
    assert EXTENSION_TO_FILE_TYPE[".ts"] == "typescript"
    assert EXTENSION_TO_FILE_TYPE[".tsx"] == "typescript"


def test_javascript_in_whitelist() -> None:
    assert ".js" in SUPPORTED_EXTENSIONS
    assert ".jsx" in SUPPORTED_EXTENSIONS
    assert EXTENSION_TO_FILE_TYPE[".js"] == "javascript"
    assert EXTENSION_TO_FILE_TYPE[".jsx"] == "javascript"


def test_java_json_md_txt_in_whitelist() -> None:
    for ext in (".java", ".json", ".md", ".txt"):
        assert ext in SUPPORTED_EXTENSIONS


def test_supported_extensions_is_frozenset() -> None:
    assert isinstance(SUPPORTED_EXTENSIONS, frozenset)


def test_max_file_size_is_1_mib() -> None:
    assert MAX_FILE_SIZE == 1 * 1024 * 1024


# ----- Success paths --------------------------------------------------------


def test_inspect_python_success(tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("print('hi')\n", encoding="utf-8")
    r = inspect_file(str(f))
    assert r.ok is True
    assert r.content == "print('hi')\n"
    assert r.file_type == "python"
    assert r.error_message == ""


def test_inspect_typescript(tmp_path: Path) -> None:
    f = tmp_path / "x.ts"
    f.write_text("const x: number = 1", encoding="utf-8")
    r = inspect_file(str(f))
    assert r.ok is True
    assert r.file_type == "typescript"


def test_inspect_json(tmp_path: Path) -> None:
    f = tmp_path / "x.json"
    f.write_text('{"key": "value"}', encoding="utf-8")
    r = inspect_file(str(f))
    assert r.ok is True
    assert r.file_type == "json"


def test_inspect_markdown(tmp_path: Path) -> None:
    f = tmp_path / "x.md"
    f.write_text("# Title\n\ntext", encoding="utf-8")
    r = inspect_file(str(f))
    assert r.ok is True
    assert r.file_type == "markdown"


def test_inspect_empty_file(tmp_path: Path) -> None:
    f = tmp_path / "empty.py"
    f.write_text("", encoding="utf-8")
    r = inspect_file(str(f))
    assert r.ok is True
    assert r.content == ""
    assert r.file_type == "python"


def test_inspect_file_at_size_limit(tmp_path: Path) -> None:
    """A file of exactly MAX_FILE_SIZE bytes is accepted (boundary)."""
    f = tmp_path / "max.py"
    # All 'x' so it's valid ASCII/UTF-8
    f.write_bytes(b"x" * MAX_FILE_SIZE)
    r = inspect_file(str(f))
    assert r.ok is True


# ----- Rejection paths ------------------------------------------------------


def test_inspect_missing_file(tmp_path: Path) -> None:
    r = inspect_file(str(tmp_path / "missing.py"))
    assert r.ok is False
    assert "does not exist" in r.error_message


def test_inspect_directory(tmp_path: Path) -> None:
    d = tmp_path / "sub"
    d.mkdir()
    r = inspect_file(str(d))
    assert r.ok is False
    assert "Not a file" in r.error_message


def test_inspect_unsupported_extension(tmp_path: Path) -> None:
    f = tmp_path / "x.exe"
    f.write_text("content", encoding="utf-8")
    r = inspect_file(str(f))
    assert r.ok is False
    assert "not supported" in r.error_message
    assert ".exe" in r.error_message


def test_inspect_no_extension(tmp_path: Path) -> None:
    f = tmp_path / "Makefile"
    f.write_text("all:", encoding="utf-8")
    r = inspect_file(str(f))
    assert r.ok is False
    assert "(none)" in r.error_message


def test_inspect_binary_content(tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    # Bytes that are not valid UTF-8
    f.write_bytes(b"\x00\x01\x02\xff\xfe\xfd")
    r = inspect_file(str(f))
    assert r.ok is False
    assert "Binary file" in r.error_message


def test_inspect_file_too_large(tmp_path: Path) -> None:
    f = tmp_path / "big.py"
    # Slightly over the limit
    f.write_bytes(b"x" * (MAX_FILE_SIZE + 1))
    r = inspect_file(str(f))
    assert r.ok is False
    assert "too large" in r.error_message
    # The size is reported in MB
    assert "MB" in r.error_message
