"""Tests for the FileManager service.

All tests run against a fresh ``tmp_path`` fixture provided by pytest.
No real user files are touched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services import FileManager, FileOperationError


# ----- list_directory -----


def test_list_empty_directory(tmp_path: Path) -> None:
    assert FileManager().list_directory(str(tmp_path)) == []


def test_list_populated_directory_sorts_dirs_first_then_alphabetical(
    tmp_path: Path,
) -> None:
    (tmp_path / "b.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "a.txt").write_text("world!", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    items = FileManager().list_directory(str(tmp_path))
    assert [i.name for i in items] == ["sub", "a.txt", "b.txt"]
    sub_item, a_item, b_item = items
    assert sub_item.is_dir is True
    assert sub_item.size == 0
    assert a_item.is_dir is False
    assert a_item.size == 6  # "world!"
    assert b_item.is_dir is False
    assert b_item.size == 5  # "hello"


def test_list_nonexistent_directory_raises(tmp_path: Path) -> None:
    with pytest.raises(FileOperationError):
        FileManager().list_directory(str(tmp_path / "missing"))


def test_list_file_as_directory_raises(tmp_path: Path) -> None:
    f = tmp_path / "file.txt"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(FileOperationError):
        FileManager().list_directory(str(f))


# ----- create_folder -----


def test_create_folder_success(tmp_path: Path) -> None:
    new = FileManager().create_folder(str(tmp_path), "my_folder")
    assert (tmp_path / "my_folder").is_dir()
    assert new == str((tmp_path / "my_folder").resolve())


def test_create_folder_already_exists_raises(tmp_path: Path) -> None:
    (tmp_path / "dup").mkdir()
    with pytest.raises(FileOperationError):
        FileManager().create_folder(str(tmp_path), "dup")


@pytest.mark.parametrize(
    "bad_name",
    ["", ".", "..", "a/b", "a\\b", "a<b", "x:y", "a|b", "a?b", "a*b", 'a"b'],
)
def test_create_folder_rejects_invalid_names(tmp_path: Path, bad_name: str) -> None:
    with pytest.raises(FileOperationError):
        FileManager().create_folder(str(tmp_path), bad_name)


# ----- create_file -----


def test_create_file_success(tmp_path: Path) -> None:
    new = FileManager().create_file(str(tmp_path), "x.py", "print('hi')\n")
    assert (tmp_path / "x.py").read_text(encoding="utf-8") == "print('hi')\n"
    assert new == str((tmp_path / "x.py").resolve())


def test_create_file_default_content_is_empty(tmp_path: Path) -> None:
    FileManager().create_file(str(tmp_path), "empty.txt")
    assert (tmp_path / "empty.txt").read_text(encoding="utf-8") == ""


def test_create_file_already_exists_raises(tmp_path: Path) -> None:
    (tmp_path / "x.py").write_text("x", encoding="utf-8")
    with pytest.raises(FileOperationError):
        FileManager().create_file(str(tmp_path), "x.py")


# ----- copy_item -----


def test_copy_file_preserves_source(tmp_path: Path) -> None:
    src = tmp_path / "a.txt"
    src.write_text("data", encoding="utf-8")
    dest = tmp_path / "dest"
    dest.mkdir()
    new = FileManager().copy_item(str(src), str(dest))
    assert (dest / "a.txt").read_text(encoding="utf-8") == "data"
    assert src.exists()  # source preserved on copy
    assert new == str((dest / "a.txt").resolve())


def test_copy_directory_recursive(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("x", encoding="utf-8")
    (src / "sub").mkdir()
    (src / "sub" / "b.txt").write_text("y", encoding="utf-8")
    dest = tmp_path / "dest"
    dest.mkdir()  # copy_item requires the destination directory to exist
    FileManager().copy_item(str(src), str(dest))
    assert (dest / "src" / "a.txt").exists()
    assert (dest / "src" / "sub" / "b.txt").exists()


def test_copy_destination_exists_raises(tmp_path: Path) -> None:
    src = tmp_path / "a.txt"
    src.write_text("x", encoding="utf-8")
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "a.txt").write_text("y", encoding="utf-8")
    with pytest.raises(FileOperationError):
        FileManager().copy_item(str(src), str(dest))


# ----- move_item -----


def test_move_file_removes_source(tmp_path: Path) -> None:
    src = tmp_path / "a.txt"
    src.write_text("data", encoding="utf-8")
    dest = tmp_path / "dest"
    dest.mkdir()
    new = FileManager().move_item(str(src), str(dest))
    assert (dest / "a.txt").read_text(encoding="utf-8") == "data"
    assert not src.exists()
    assert new == str((dest / "a.txt").resolve())


def test_move_destination_exists_raises(tmp_path: Path) -> None:
    src = tmp_path / "a.txt"
    src.write_text("x", encoding="utf-8")
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "a.txt").write_text("y", encoding="utf-8")
    with pytest.raises(FileOperationError):
        FileManager().move_item(str(src), str(dest))


# ----- delete_item -----


def test_delete_file(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    FileManager().delete_item(str(f))
    assert not f.exists()


def test_delete_directory_recursive(tmp_path: Path) -> None:
    d = tmp_path / "sub"
    d.mkdir()
    (d / "a.txt").write_text("x", encoding="utf-8")
    (d / "nested").mkdir()
    (d / "nested" / "b.txt").write_text("y", encoding="utf-8")
    FileManager().delete_item(str(d))
    assert not d.exists()


def test_delete_nonexistent_raises(tmp_path: Path) -> None:
    with pytest.raises(FileOperationError):
        FileManager().delete_item(str(tmp_path / "ghost"))


# ----- clipboard -----


def test_clipboard_paste_empty_returns_none(tmp_path: Path) -> None:
    assert FileManager().paste_from_clipboard(str(tmp_path)) is None
    assert FileManager().clipboard_state() is None


def test_clipboard_copy_paste_preserves_source_and_buffer(tmp_path: Path) -> None:
    src = tmp_path / "a.txt"
    src.write_text("data", encoding="utf-8")
    dest = tmp_path / "dest"
    dest.mkdir()
    fm = FileManager()
    fm.copy_to_clipboard(str(src))
    state = fm.clipboard_state()
    assert state is not None
    assert state.mode == "copy"
    assert Path(state.source_path) == src.resolve()
    new = fm.paste_from_clipboard(str(dest))
    assert (dest / "a.txt").exists()
    assert src.exists()  # copy: source preserved
    assert fm.clipboard_state() is not None  # copy: clipboard preserved


def test_clipboard_cut_paste_removes_source_and_clears_buffer(tmp_path: Path) -> None:
    src = tmp_path / "a.txt"
    src.write_text("data", encoding="utf-8")
    dest = tmp_path / "dest"
    dest.mkdir()
    fm = FileManager()
    fm.cut_to_clipboard(str(src))
    new = fm.paste_from_clipboard(str(dest))
    assert (dest / "a.txt").exists()
    assert not src.exists()  # cut: source removed
    assert fm.clipboard_state() is None  # cut: clipboard cleared


def test_clipboard_with_missing_source_raises(tmp_path: Path) -> None:
    fm = FileManager()
    with pytest.raises(FileOperationError):
        fm.copy_to_clipboard(str(tmp_path / "ghost"))
    with pytest.raises(FileOperationError):
        fm.cut_to_clipboard(str(tmp_path / "ghost"))


def test_clipboard_paste_failure_preserves_buffer(tmp_path: Path) -> None:
    src = tmp_path / "a.txt"
    src.write_text("data", encoding="utf-8")
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "a.txt").write_text("collision", encoding="utf-8")
    fm = FileManager()
    fm.copy_to_clipboard(str(src))
    with pytest.raises(FileOperationError):
        fm.paste_from_clipboard(str(dest))
    # Clipboard should still hold the item — caller can retry.
    assert fm.clipboard_state() is not None


# ----- error path -----


def test_create_in_missing_directory_raises(tmp_path: Path) -> None:
    with pytest.raises(FileOperationError):
        FileManager().create_folder(str(tmp_path / "missing"), "x")


# ----- write_file (Change 005) -----


def test_write_file_overwrites_existing(tmp_path: Path) -> None:
    """Editor 'Save' flow: existing file gets the new content."""
    target = tmp_path / "x.py"
    target.write_text("old", encoding="utf-8")
    FileManager().write_file(str(target), "new content")
    assert target.read_text(encoding="utf-8") == "new content"


def test_write_file_creates_when_missing(tmp_path: Path) -> None:
    """A new file can be created by write_file if the parent exists."""
    target = tmp_path / "new.py"
    FileManager().write_file(str(target), "hello")
    assert target.read_text(encoding="utf-8") == "hello"


def test_write_file_preserves_unicode(tmp_path: Path) -> None:
    """Unicode content is round-tripped via UTF-8."""
    target = tmp_path / "i18n.txt"
    payload = "olá — 你好 — 🚀"
    FileManager().write_file(str(target), payload)
    assert target.read_text(encoding="utf-8") == payload


def test_write_file_empty_string_clears(tmp_path: Path) -> None:
    """An empty payload empties the file (not delete it)."""
    target = tmp_path / "x.txt"
    target.write_text("content", encoding="utf-8")
    FileManager().write_file(str(target), "")
    assert target.read_text(encoding="utf-8") == ""


def test_write_file_to_missing_parent_raises(tmp_path: Path) -> None:
    """Refuses to silently create parent directories — editor saves in-place only."""
    with pytest.raises(FileOperationError):
        FileManager().write_file(str(tmp_path / "no" / "such" / "x.py"), "x")


def test_write_file_on_directory_raises(tmp_path: Path) -> None:
    """Refuses to 'write' a directory — that is a programmer error."""
    d = tmp_path / "sub"
    d.mkdir()
    with pytest.raises(FileOperationError):
        FileManager().write_file(str(d), "nope")

