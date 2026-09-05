"""File inspection helper — validates and reads files for AI analysis.

This helper is pure (no Qt) and testable in isolation. It enforces:

- File exists and is a regular file (not a directory)
- File extension is in the supported whitelist
- File size is below the limit (so the content fits in the LLM context)
- File content is valid UTF-8 (binary files are rejected)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Mapping of file extension to the ``file_type`` string passed to
# :meth:`AIEngine.analyze_architecture`. Keep in sync with the prompt
# templates in ``app.services.ai_engine``.
EXTENSION_TO_FILE_TYPE: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".java": "java",
    ".json": "json",
    ".md": "markdown",
    ".txt": "text",
}

# Frozen whitelist of extensions the file explorer will accept for AI analysis.
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(EXTENSION_TO_FILE_TYPE.keys())

# Maximum file size (in bytes) accepted for AI analysis. 1 MiB comfortably
# fits in the 3B model's 32k context (~24k tokens).
MAX_FILE_SIZE: int = 1 * 1024 * 1024  # 1 MiB


@dataclass(frozen=True)
class InspectResult:
    """Outcome of :func:`inspect_file`.

    On success, ``ok`` is True and ``content``/``file_type`` are populated.
    On failure, ``ok`` is False and ``error_message`` is user-facing.
    """

    ok: bool
    content: str
    file_type: str
    error_message: str


def inspect_file(path: str) -> InspectResult:
    """Validate and read a file for AI analysis.

    Returns an :class:`InspectResult` with either:
    - ``ok=True, content=<text>, file_type=<language>`` on success, or
    - ``ok=False, error_message=<reason>`` on rejection.

    The function never raises — all failure modes are encoded in the result.
    """
    p = Path(path)

    if not p.exists():
        return InspectResult(False, "", "", f"File does not exist: {path}")
    if not p.is_file():
        return InspectResult(False, "", "", f"Not a file: {path}")

    suffix = p.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        return InspectResult(
            False, "", "",
            f"File extension not supported: {suffix or '(none)'}",
        )

    try:
        size = p.stat().st_size
    except OSError as exc:
        return InspectResult(False, "", "", f"Cannot stat file: {exc}")

    if size > MAX_FILE_SIZE:
        size_mb = size / 1024 / 1024
        return InspectResult(
            False, "", "",
            f"File too large ({size_mb:.1f} MB). Limit is 1.0 MB.",
        )

    try:
        content = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return InspectResult(False, "", "", "Binary file, not supported.")
    except OSError as exc:
        return InspectResult(False, "", "", f"Cannot read file: {exc}")

    file_type = EXTENSION_TO_FILE_TYPE[suffix]
    return InspectResult(True, content, file_type, "")
