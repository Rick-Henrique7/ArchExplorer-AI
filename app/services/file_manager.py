"""Filesystem operations with an internal single-item clipboard.

This service is **synchronous** and **stateless across instances** —
each ``FileManager`` keeps its own clipboard, so two independent
instances in the same process never interfere with each other.
Threading is the UI layer's responsibility (Change 003).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from app.services.exceptions import FileOperationError

ClipboardMode = Literal["copy", "cut"]

# Windows-illegal filename characters (also rejected on POSIX for cross-platform safety).
_ILLEGAL_NAME_CHARS: Final[set[str]] = set('<>:"/\\|?*\0')


@dataclass(frozen=True)
class FileItem:
    """Metadata for a single file or directory entry."""

    name: str
    path: str  # absolute, normalized
    is_dir: bool
    size: int  # bytes; 0 for directories


@dataclass(frozen=True)
class ClipboardState:
    """Internal clipboard buffer — one source path plus a mode."""

    source_path: str
    mode: ClipboardMode


class FileManager:
    """High-level filesystem operations used by the UI layer."""

    def __init__(self) -> None:
        self._clipboard: ClipboardState | None = None

    # ----- Listing -----------------------------------------------------------

    def list_directory(self, path: str) -> list[FileItem]:
        target = self._validate_dir(path)
        try:
            entries: list[FileItem] = []
            for entry in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                try:
                    stat = entry.stat()
                except OSError as exc:
                    raise FileOperationError(
                        f"Cannot stat {entry}",
                        path=str(entry),
                    ) from exc
                entries.append(
                    FileItem(
                        name=entry.name,
                        path=str(entry.resolve()),
                        is_dir=entry.is_dir(),
                        size=stat.st_size if entry.is_file() else 0,
                    )
                )
            return entries
        except FileOperationError:
            raise
        except OSError as exc:
            raise FileOperationError(
                f"Cannot list directory {path}",
                path=path,
            ) from exc

    # ----- Write ------------------------------------------------------------

    def write_file(self, path: str, content: str) -> None:
        """Overwrite ``path`` with ``content`` (UTF-8, no BOM).

        Used by the editor's "Save" action (Change 005) and by the
        AI-edit "apply" flow. Refuses to write if the parent directory
        does not exist or the path is a directory — the editor only
        edits known-existing files, so those are bugs in the caller.
        """
        target = Path(path)
        if not target.parent.exists():
            raise FileOperationError(
                f"Parent directory does not exist: {target.parent}",
                path=str(target),
            )
        if target.exists() and target.is_dir():
            raise FileOperationError(
                f"Cannot write a directory: {path}",
                path=str(target),
            )
        try:
            target.write_text(content, encoding="utf-8")
        except OSError as exc:
            raise FileOperationError(
                f"Cannot write file {path}",
                path=str(target),
            ) from exc

    # ----- Creation ----------------------------------------------------------

    def create_folder(self, target_dir: str, name: str) -> str:
        self._validate_name(name)
        target = self._validate_dir(target_dir)
        new_path = target / name
        if new_path.exists():
            raise FileOperationError(
                f"Path already exists: {new_path}",
                path=str(new_path),
            )
        try:
            new_path.mkdir(parents=False, exist_ok=False)
        except OSError as exc:
            raise FileOperationError(
                f"Cannot create folder {new_path}",
                path=str(new_path),
            ) from exc
        return str(new_path.resolve())

    def create_file(self, target_dir: str, name: str, content: str = "") -> str:
        self._validate_name(name)
        target = self._validate_dir(target_dir)
        new_path = target / name
        if new_path.exists():
            raise FileOperationError(
                f"Path already exists: {new_path}",
                path=str(new_path),
            )
        try:
            new_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            raise FileOperationError(
                f"Cannot create file {new_path}",
                path=str(new_path),
            ) from exc
        return str(new_path.resolve())

    # ----- Copy / Move -------------------------------------------------------

    def copy_item(self, source_path: str, destination_dir: str) -> str:
        source = self._validate_path(source_path)
        dest_dir = self._validate_dir(destination_dir)
        dest_path = dest_dir / source.name
        if dest_path.exists():
            raise FileOperationError(
                f"Destination already exists: {dest_path}",
                path=str(dest_path),
            )
        try:
            if source.is_dir():
                shutil.copytree(source, dest_path)
            else:
                shutil.copy2(source, dest_path)
        except OSError as exc:
            raise FileOperationError(
                f"Cannot copy {source} to {dest_path}",
                path=str(source),
            ) from exc
        return str(dest_path.resolve())

    def move_item(self, source_path: str, destination_dir: str) -> str:
        source = self._validate_path(source_path)
        dest_dir = self._validate_dir(destination_dir)
        dest_path = dest_dir / source.name
        if dest_path.exists():
            raise FileOperationError(
                f"Destination already exists: {dest_path}",
                path=str(dest_path),
            )
        try:
            shutil.move(str(source), str(dest_path))
        except OSError as exc:
            raise FileOperationError(
                f"Cannot move {source} to {dest_path}",
                path=str(source),
            ) from exc
        return str(dest_path.resolve())

    # ----- Delete ------------------------------------------------------------

    def delete_item(self, path: str) -> None:
        target = self._validate_path(path)
        try:
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        except OSError as exc:
            raise FileOperationError(
                f"Cannot delete {target}",
                path=str(target),
            ) from exc

    # ----- Clipboard ---------------------------------------------------------

    def copy_to_clipboard(self, path: str) -> None:
        self._validate_path(path)  # raises FileOperationError if missing
        self._clipboard = ClipboardState(
            source_path=str(Path(path).resolve()),
            mode="copy",
        )

    def cut_to_clipboard(self, path: str) -> None:
        self._validate_path(path)
        self._clipboard = ClipboardState(
            source_path=str(Path(path).resolve()),
            mode="cut",
        )

    def paste_from_clipboard(self, destination_dir: str) -> str | None:
        if self._clipboard is None:
            return None
        state = self._clipboard
        result = (
            self.copy_item(state.source_path, destination_dir)
            if state.mode == "copy"
            else self.move_item(state.source_path, destination_dir)
        )
        # Cut is destructive: clear clipboard after a successful paste.
        if state.mode == "cut":
            self._clipboard = None
        return result

    def clipboard_state(self) -> ClipboardState | None:
        return self._clipboard

    # ----- Internal helpers --------------------------------------------------

    @staticmethod
    def _validate_path(path: str) -> Path:
        p = Path(path)
        if not p.exists():
            raise FileOperationError(f"Path does not exist: {path}", path=path)
        return p

    @staticmethod
    def _validate_dir(path: str) -> Path:
        p = Path(path)
        if not p.exists():
            raise FileOperationError(f"Directory does not exist: {path}", path=path)
        if not p.is_dir():
            raise FileOperationError(f"Not a directory: {path}", path=path)
        return p

    @staticmethod
    def _validate_name(name: str) -> None:
        if not name:
            raise FileOperationError("Name is empty")
        if name in (".", ".."):
            raise FileOperationError(f"Invalid name: {name!r}")
        if any(c in name for c in _ILLEGAL_NAME_CHARS):
            raise FileOperationError(
                f"Name contains illegal character: {name!r}",
                name=name,
            )
