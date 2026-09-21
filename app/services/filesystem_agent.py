"""FileSystemAgent — sandboxed executor for the LLM tool calls (Change 007).

The LLM emits tool calls (``create_file``, ``create_directory``,
``read_file``, ``list_directory``). We execute each via this class,
which enforces:

- **Path traversal protection** — every relative path is joined
  with ``workspace_root`` and the result must ``startswith`` the
  resolved root. ``../etc/passwd`` is rejected.
- **Character whitelist** — paths must match
  ``^[a-zA-Z0-9._/-]+$`` (no null bytes, no backslashes, no
  spaces). This dodges a long tail of path-injection attacks.
- **Size cap** — file contents are rejected above 1 MiB to keep
  the LLM from filling the disk in one call.
- **Encoding** — UTF-8 read/write only; non-UTF-8 raises ``LlmToolError``.

Why all of this? The LLM is untrusted code. We can't just exec what
the model tells us to. Even a "harmless" prompt like
"create a file called ``../../windows/system32/config.txt``" should
be rejected.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.services.exceptions import LlmToolError


# Whitelist of safe path characters. Excludes ``..``, ``\\``, null
# bytes, and shell metacharacters. ``/`` is allowed because the
# path is relative to workspace_root.
_PATH_RE = re.compile(r"^[a-zA-Z0-9._/\-]+$")

# Single-file size limit. 1 MiB is plenty for source code and
# keeps the LLM from generating gigabyte payloads.
_MAX_FILE_SIZE = 1_048_576


class FileSystemAgent:
    """Sandboxed executor for LLM tool calls.

    Construction:
        agent = FileSystemAgent(workspace_root=Path("~/projects/foo"))
        # The workspace_root is RESOLVED at construction so subsequent
        # path comparisons are consistent (no symlink surprises).

    The four public methods correspond 1:1 to the MCP-style tool
    schemas in ``llm_adapter.FILE_TOOLS``.
    """

    def __init__(self, workspace_root: Path) -> None:
        self._root = Path(workspace_root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def workspace_root(self) -> Path:
        return self._root

    # ----- Public tools ---------------------------------------------------

    def create_file(self, file_path: str, content: str) -> str:
        """Create ``file_path`` with ``content``. Overwrites if exists."""
        target = self._safe_path(file_path)
        # Size check on the *content* (cheap, before any I/O).
        encoded = content.encode("utf-8", errors="strict")
        if len(encoded) > _MAX_FILE_SIZE:
            raise LlmToolError(
                "file_too_large",
                path=file_path,
                size=len(encoded),
                max=_MAX_FILE_SIZE,
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(encoded)
        return f"Created {file_path} ({len(encoded)} bytes)"

    def create_directory(self, dir_path: str) -> str:
        """Create ``dir_path`` recursively."""
        target = self._safe_path(dir_path)
        target.mkdir(parents=True, exist_ok=True)
        return f"Created directory {dir_path}"

    def read_file(self, file_path: str) -> str:
        """Read ``file_path`` and return its contents."""
        target = self._safe_path(file_path)
        if not target.is_file():
            raise LlmToolError(
                "file_not_found",
                path=file_path,
            )
        try:
            text = target.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise LlmToolError(
                "not_utf8",
                path=file_path,
                detail=str(exc),
            ) from exc
        if len(text.encode("utf-8")) > _MAX_FILE_SIZE:
            # Truncate in the response so the LLM doesn't get a
            # 100 MB file back, but the on-disk file is untouched.
            text = text[:_MAX_FILE_SIZE] + "\n... [truncated]"
        return text

    def list_directory(self, dir_path: str = ".") -> list[str]:
        """List entries under ``dir_path`` (suffixed with ``/`` if dir)."""
        target = self._safe_path(dir_path)
        if not target.is_dir():
            raise LlmToolError(
                "not_a_directory",
                path=dir_path,
            )
        entries: list[str] = []
        for p in sorted(target.iterdir()):
            name = p.name + ("/" if p.is_dir() else "")
            entries.append(name)
        return entries

    # ----- Internal --------------------------------------------------------

    def _safe_path(self, relative_path: str) -> Path:
        """Resolve a relative path against the workspace root safely.

        Raises :class:`LlmToolError` with a JSON-friendly ``reason``
        if the path is invalid.
        """
        if not isinstance(relative_path, str):
            raise LlmToolError(
                "invalid_chars",
                hint=f"path must be a string, got {type(relative_path).__name__}",
            )
        if not _PATH_RE.match(relative_path):
            raise LlmToolError(
                "invalid_chars",
                path=relative_path,
            )
        # ``resolve()`` collapses any ``..`` segments; combined with
        # the ``startswith`` check below, traversal is impossible.
        target = (self._root / relative_path).resolve()
        try:
            target.relative_to(self._root)
        except ValueError as exc:
            raise LlmToolError(
                "path_traversal",
                path=relative_path,
                resolved=str(target),
            ) from exc
        return target
