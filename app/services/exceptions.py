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
