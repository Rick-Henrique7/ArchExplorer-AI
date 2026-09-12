"""Domain models for the personal catalog (Change 006).

Plain `@dataclass(frozen=True)` — no ORM. The schema is small
(3 tables + 1 FTS5 virtual) and we want full control over SQL.
Validation lives in :class:`CatalogoService.create_entry`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class Entry:
    """A single entry in the user's personal catalog.

    Immutable; ``CatalogoService`` returns a new instance on every
    mutation. ``tags`` is a tuple (not list) so the frozen dataclass
    is truly hashable.
    """

    id: int
    title: str
    code: str
    language: str = "text"
    description: str | None = None
    category: str | None = None
    origin_path: str | None = None
    origin_line: int | None = None
    is_public: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tags: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        """Plain-dict serialization (used by export_json)."""
        return {
            "id": self.id,
            "title": self.title,
            "code": self.code,
            "language": self.language,
            "description": self.description,
            "category": self.category,
            "origin_path": self.origin_path,
            "origin_line": self.origin_line,
            "is_public": self.is_public,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "Entry":
        """Inverse of :meth:`to_dict`."""
        return cls(
            id=payload["id"],
            title=payload["title"],
            code=payload["code"],
            language=payload.get("language", "text"),
            description=payload.get("description"),
            category=payload.get("category"),
            origin_path=payload.get("origin_path"),
            origin_line=payload.get("origin_line"),
            is_public=bool(payload.get("is_public", False)),
            created_at=datetime.fromisoformat(payload["created_at"]),
            updated_at=datetime.fromisoformat(payload["updated_at"]),
            tags=tuple(payload.get("tags", [])),
        )


@dataclass(frozen=True)
class Tag:
    """A single tag (unique by lowercase name)."""

    id: int
    name: str
