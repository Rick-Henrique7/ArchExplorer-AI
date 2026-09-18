"""Custom exceptions raised by the services layer.

All ArchExplorer-specific exceptions share a common base
(``ArchExplorerError``) which carries an optional diagnostic
``context`` dict. The UI / logging layer is responsible for surfacing
those contexts to the user; the services themselves never log.
"""

from __future__ import annotations

from typing import Any


class ArchExplorerError(Exception):
    """Base class for all custom ArchExplorer AI exceptions."""

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message)
        self.message = message
        self.context: dict[str, Any] = dict(context)

    def __str__(self) -> str:
        if self.context:
            ctx = ", ".join(f"{k}={v!r}" for k, v in self.context.items())
            return f"{self.message} ({ctx})"
        return self.message

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.message!r}, **{self.context!r})"


class FileOperationError(ArchExplorerError):
    """Raised when a filesystem operation fails (missing path, permission, collision)."""


class AIServiceUnavailableError(ArchExplorerError):
    """Raised when the AI backend is unreachable, returns an error, or its response is unusable."""


class DiagramParsingError(ArchExplorerError):
    """Raised when an LLM response cannot be coerced into a valid diagram syntax."""


class CatalogoError(ArchExplorerError):
    """Raised when the personal catalog cannot perform the requested operation.

    Covers SQLite errors (corrupted database, disk full, permission
    denied), validation failures (empty title, oversized code, etc.)
    and import/export errors (malformed JSON).
    """


class LpsSpecError(ArchExplorerError):
    """Raised when a feature model JSON does not match the LPS DSL (Contrato 1).

    The context dict carries the JSON Pointer path of the offending
    field (e.g. ``"/nodes/3/variability"``) so the UI can highlight the
    specific row in the inspector.
    """


class LpsValidationError(ArchExplorerError):
    """Raised when a feature model selection violates SAT constraints.

    The context carries the conflicting node ids (when the solver
    can isolate them) so the UI can draw the bad edges in red.
    """


class LlmToolError(ArchExplorerError):
    """Raised when a LLM Tool Use invocation is rejected or fails.

    The ``reason`` field (in the context dict) is one of:
    - ``path_traversal``  — agent tried to escape the workspace
    - ``invalid_chars``   — path contains forbidden characters
    - ``file_too_large``  — content exceeds the 1 MB cap
    - ``file_not_found``  — read_file on a missing path
    - ``not_a_directory`` — list_directory on a non-dir
    - ``unknown_tool``    — IA invoked a tool that doesn't exist
    - ``tool_failed``     — tool raised an unexpected exception
    """
