"""Personal catalog service (Change 006).

SQLite-backed storage for the user's own solutions/patterns.
Uses SQLite's FTS5 for full-text search. Schema is created
automatically on first use — no separate ``init`` step.

Location
--------
Default path: ``%USERPROFILE%/Documents/ArchExplorer/catalogo.db``
(on Windows; ``~/Documents/ArchExplorer/`` on macOS/Linux).
Overridable by:

- Environment variable ``ARCHEXPLORER_CATALOG_DB``
- CLI flag ``--catalog-db`` (handled in ``app/main.py``)
- QSettings key ``catalog/db_path`` (set by user via Settings dialog,
  not yet implemented in Change 006)
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from app.services.exceptions import CatalogoError
from app.services.models import Entry, Tag


# Validation regex for tag names: lowercase alphanum + . _ -
_TAG_RE = re.compile(r"^[a-z0-9_.\-]{1,30}$")

# Default location of the catalog database file.
def default_catalog_path() -> Path:
    """Return the default catalog.db path for the current OS.

    Also creates the parent directory (``~/Documents/ArchExplorer/``) so
    the first run doesn't fail when the user hasn't navigated there
    yet. The directory creation is idempotent and silent.

    - Windows: ``%USERPROFILE%/Documents/ArchExplorer/catalogo.db``
    - macOS / Linux: ``$HOME/Documents/ArchExplorer/catalogo.db``
    """
    home = Path(os.path.expanduser("~"))
    docs = home / "Documents"
    target_dir = docs / "ArchExplorer"
    # Idempotent: exists_ok=True means no error if the directory is
    # already there. ``parents=True`` covers the (rare) case where
    # ``Documents`` itself does not exist yet on a brand-new profile.
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / "catalogo.db"


def normalize_tags(raw_tags: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """Normalize tag input for storage.

    Rules (mirrored in the spec):
      - lowercase, strip whitespace
      - drop empties
      - drop duplicates (case-insensitive)
      - max 20 tags
      - silently drop tags that don't match ``_TAG_RE`` (e.g. with spaces
        or uppercase). Caller is expected to surface the count.
    """
    seen: set[str] = set()
    result: list[str] = []
    for tag in raw_tags:
        normalized = tag.strip().lower()
        if not normalized or normalized in seen:
            continue
        if not _TAG_RE.match(normalized):
            continue
        seen.add(normalized)
        result.append(normalized)
        if len(result) >= 20:
            break
    return tuple(result)


class CatalogoService:
    """SQLite-backed CRUD + FTS5 search for the personal catalog.

    The schema (entries / tags / entry_tags + entries_fts + triggers)
    is created on every ``__init__`` via ``CREATE TABLE IF NOT EXISTS``,
    so opening an existing DB is a no-op.

    All write operations are wrapped in a single ``BEGIN/COMMIT`` to
    keep entries and their tags consistent. Read operations use
    implicit transactions (autocommit) but still acquire a fresh
    connection from the pool.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        if db_path is None:
            db_path_str = os.environ.get("ARCHEXPLORER_CATALOG_DB")
            db_path = Path(db_path_str) if db_path_str else default_catalog_path()
        self._db_path: Path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        # Open once at construction so the schema is materialized and
        # any corruption is caught eagerly (better than on first write).
        self._init_schema()

    # ----- Connection management -----------------------------------------

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a sqlite3 connection; close it on exit.

        Foreign keys are enabled per-connection (SQLite has them off
        by default for backwards compatibility). ``row_factory`` is
        set to :class:`sqlite3.Row` so we can access columns by name.
        """
        conn = sqlite3.connect(self._db_path)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            yield conn
        finally:
            conn.close()

    def _init_schema(self) -> None:
        """Create tables, FTS5 virtual table, triggers, _migrations."""
        try:
            with self._connect() as conn:
                conn.executescript(_SCHEMA_SQL)
                conn.commit()
        except sqlite3.DatabaseError as exc:
            # Corrupted DB → backup and let the next open create fresh.
            backup = self._db_path.with_suffix(".db.bak")
            try:
                self._db_path.rename(backup)
            except OSError:
                pass  # give up on backup, try to create fresh anyway
            with self._connect() as conn:
                conn.executescript(_SCHEMA_SQL)
                conn.commit()
            raise CatalogoError(
                "Catalog database was corrupted; backed up and recreated",
                path=str(self._db_path),
                backup=str(backup),
                cause=str(exc),
            )

    # ----- CRUD ------------------------------------------------------------

    def create_entry(
        self,
        *,
        title: str,
        code: str,
        description: str | None = None,
        language: str = "text",
        category: str | None = None,
        tags: list[str] | tuple[str, ...] = (),
        origin_path: str | None = None,
        origin_line: int | None = None,
        is_public: bool = False,
    ) -> Entry:
        """Insert a new entry and return the persisted :class:`Entry`.

        Validates required fields and clamps lengths. Tags are
        normalized (lowercase, dedup, max 20) before storage.
        Raises :class:`CatalogoError` with field context on failure.
        """
        self._validate_entry_fields(
            title=title, code=code, description=description,
            language=language, category=category,
            origin_path=origin_path, origin_line=origin_line,
        )
        normalized_tags = normalize_tags(tags)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO entries
                        (title, description, code, language, category,
                         origin_path, origin_line, is_public,
                         created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        title.strip(),
                        (description or None),
                        code,
                        language.strip().lower(),
                        (category.strip() if category else None),
                        origin_path,
                        origin_line,
                        int(is_public),
                        now, now,
                    ),
                )
                entry_id = cur.lastrowid
                assert entry_id is not None
                for tag_name in normalized_tags:
                    tag_id = self._upsert_tag(conn, tag_name)
                    conn.execute(
                        "INSERT OR IGNORE INTO entry_tags (entry_id, tag_id) VALUES (?, ?)",
                        (entry_id, tag_id),
                    )
                conn.commit()
        except sqlite3.Error as exc:
            raise CatalogoError(
                "Failed to insert catalog entry",
                title=title,
                cause=str(exc),
            ) from exc
        return self.get_entry(entry_id)  # type: ignore[return-value]

    def get_entry(self, entry_id: int) -> Entry | None:
        """Fetch a single entry by id (with its tags) or return None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM entries WHERE id = ?", (entry_id,)
            ).fetchone()
            if row is None:
                return None
            tags = self._tags_for_entry(conn, entry_id)
        return self._row_to_entry(row, tags)

    def update_entry(
        self,
        entry_id: int,
        *,
        title: str | None = None,
        code: str | None = None,
        description: str | None = None,
        language: str | None = None,
        category: str | None = None,
        tags: list[str] | tuple[str, ...] | None = None,
        origin_path: str | None = None,
        origin_line: int | None = None,
        is_public: bool | None = None,
    ) -> Entry:
        """Partial update; only the fields explicitly passed are changed.

        When ``tags`` is passed (even as an empty list), the tag set
        is replaced. Passing ``tags=None`` means "don't touch tags".
        Raises :class:`CatalogoError` if the entry doesn't exist.
        """
        existing = self.get_entry(entry_id)
        if existing is None:
            raise CatalogoError("Entry not found", entry_id=entry_id)

        new_title = title if title is not None else existing.title
        new_code = code if code is not None else existing.code
        new_desc = description if description is not None else existing.description
        new_lang = language if language is not None else existing.language
        new_cat = category if category is not None else existing.category
        new_origin = origin_path if origin_path is not None else existing.origin_path
        new_origin_line = origin_line if origin_line is not None else existing.origin_line
        new_public = is_public if is_public is not None else existing.is_public

        self._validate_entry_fields(
            title=new_title, code=new_code, description=new_desc,
            language=new_lang, category=new_cat,
            origin_path=new_origin, origin_line=new_origin_line,
        )

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE entries SET
                        title = ?, description = ?, code = ?, language = ?,
                        category = ?, origin_path = ?, origin_line = ?,
                        is_public = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        new_title.strip(),
                        new_desc,
                        new_code,
                        new_lang.strip().lower(),
                        new_cat,
                        new_origin,
                        new_origin_line,
                        int(new_public),
                        now,
                        entry_id,
                    ),
                )
                if tags is not None:
                    conn.execute(
                        "DELETE FROM entry_tags WHERE entry_id = ?", (entry_id,)
                    )
                    for tag_name in normalize_tags(tags):
                        tag_id = self._upsert_tag(conn, tag_name)
                        conn.execute(
                            "INSERT OR IGNORE INTO entry_tags (entry_id, tag_id) "
                            "VALUES (?, ?)",
                            (entry_id, tag_id),
                        )
                conn.commit()
        except sqlite3.Error as exc:
            raise CatalogoError(
                "Failed to update catalog entry",
                entry_id=entry_id,
                cause=str(exc),
            ) from exc
        refreshed = self.get_entry(entry_id)
        assert refreshed is not None
        return refreshed

    def delete_entry(self, entry_id: int) -> None:
        """Delete an entry; entry_tags are removed by FK CASCADE."""
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    "DELETE FROM entries WHERE id = ?", (entry_id,)
                )
                conn.commit()
        except sqlite3.Error as exc:
            raise CatalogoError(
                "Failed to delete catalog entry",
                entry_id=entry_id,
                cause=str(exc),
            ) from exc
        if cur.rowcount == 0:
            raise CatalogoError("Entry not found", entry_id=entry_id)

    # ----- Listing & search -------------------------------------------------

    def list_entries(
        self,
        *,
        language: str | None = None,
        category: str | None = None,
        tag: str | None = None,
        limit: int = 200,
    ) -> list[Entry]:
        """List entries, optionally filtered by language / category / tag.

        Results are ordered by ``updated_at DESC`` (most recent first).
        """
        clauses: list[str] = []
        params: list = []
        if language:
            clauses.append("e.language = ?")
            params.append(language.strip().lower())
        if category:
            clauses.append("e.category = ?")
            params.append(category.strip())
        if tag:
            clauses.append(
                "e.id IN (SELECT et.entry_id FROM entry_tags et "
                "JOIN tags t ON t.id = et.tag_id WHERE t.name = ?)"
            )
            params.append(tag.strip().lower())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            f"SELECT e.* FROM entries e {where} "
            "ORDER BY e.updated_at DESC LIMIT ?"
        )
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            entries: list[Entry] = []
            for row in rows:
                tags = self._tags_for_entry(conn, row["id"])
                entries.append(self._row_to_entry(row, tags))
        return entries

    def search_entries(self, query: str, *, limit: int = 50) -> list[Entry]:
        """Full-text search via FTS5. Prefix-match on each term.

        Example: ``"cache lru"`` → ``cache* lru*`` (both terms must
        match; ``cache*`` also matches ``caching``, ``cached``, etc.).
        Returns the most relevant hits first (BM25 ranking).
        """
        terms = [t for t in query.split() if t]
        if not terms:
            return self.list_entries(limit=limit)
        # FTS5 prefix query: each term gets a `*` suffix. We do NOT
        # quote the term — quoting ``"cach*"`` treats the asterisk as
        # part of the literal token (no match). Each term from
        # ``query.split()`` is already whitespace-free, so no quoting
        # is needed.
        fts_query = " ".join(f"{term}*" for term in terms)
        sql = (
            "SELECT e.* FROM entries_fts fts "
            "JOIN entries e ON e.id = fts.rowid "
            "WHERE entries_fts MATCH ? "
            "ORDER BY rank LIMIT ?"
        )
        try:
            with self._connect() as conn:
                rows = conn.execute(sql, (fts_query, limit)).fetchall()
                entries: list[Entry] = []
                for row in rows:
                    tags = self._tags_for_entry(conn, row["id"])
                    entries.append(self._row_to_entry(row, tags))
        except sqlite3.OperationalError:
            # FTS5 syntax error (e.g. unbalanced quotes) — fall back to
            # a safe LIKE search so the user still gets *something*.
            return self._fallback_like_search(query, limit=limit)
        return entries

    def _fallback_like_search(self, query: str, *, limit: int) -> list[Entry]:
        """Used only if FTS5 raises on the user's query (rare)."""
        like = f"%{query}%"
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM entries
                WHERE title LIKE ? OR description LIKE ? OR code LIKE ?
                ORDER BY updated_at DESC LIMIT ?
                """,
                (like, like, like, limit),
            ).fetchall()
            entries: list[Entry] = []
            for row in rows:
                tags = self._tags_for_entry(conn, row["id"])
                entries.append(self._row_to_entry(row, tags))
        return entries

    def list_tags(self) -> list[Tag]:
        """All tags in use, ordered by name."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, name FROM tags ORDER BY name COLLATE NOCASE"
            ).fetchall()
        return [Tag(id=row["id"], name=row["name"]) for row in rows]

    def list_categories(self) -> list[str]:
        """Distinct categories (non-null), ordered alphabetically."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT category FROM entries "
                "WHERE category IS NOT NULL AND category <> '' "
                "ORDER BY category COLLATE NOCASE"
            ).fetchall()
        return [row["category"] for row in rows]

    def list_languages(self) -> list[str]:
        """Distinct languages in use, ordered alphabetically."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT language FROM entries "
                "WHERE language IS NOT NULL AND language <> '' "
                "ORDER BY language COLLATE NOCASE"
            ).fetchall()
        return [row["language"] for row in rows]

    def stats(self) -> dict:
        """Aggregate stats: total count + breakdown by language/category."""
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) AS c FROM entries").fetchone()["c"]
            by_lang = {
                row["language"]: row["c"]
                for row in conn.execute(
                    "SELECT language, COUNT(*) AS c FROM entries "
                    "GROUP BY language ORDER BY c DESC"
                ).fetchall()
            }
            by_cat = {
                row["category"]: row["c"]
                for row in conn.execute(
                    "SELECT category, COUNT(*) AS c FROM entries "
                    "WHERE category IS NOT NULL "
                    "GROUP BY category ORDER BY c DESC"
                ).fetchall()
            }
            tag_count = conn.execute("SELECT COUNT(*) AS c FROM tags").fetchone()["c"]
        return {
            "total": total,
            "by_language": by_lang,
            "by_category": by_cat,
            "tag_count": tag_count,
        }

    # ----- Import / Export -------------------------------------------------

    def export_json(self) -> str:
        """Serialize the entire catalog to a JSON string.

        The format is self-contained: each entry embeds its tags
        inline. The export is meant to be human-readable (not a
        SQLite backup) and re-importable via :meth:`import_json`.
        """
        with self._connect() as conn:
            entries: list[dict] = []
            for row in conn.execute(
                "SELECT * FROM entries ORDER BY id"
            ).fetchall():
                tags = self._tags_for_entry(conn, row["id"])
                payload = dict(row)
                payload["tags"] = list(tags)
                # ISO-format timestamps so the export is portable.
                payload["created_at"] = row["created_at"]
                payload["updated_at"] = row["updated_at"]
                payload["is_public"] = bool(row["is_public"])
                entries.append(payload)
        return json.dumps(
            {"version": 1, "exported_at": datetime.now(timezone.utc).isoformat(),
             "entries": entries},
            indent=2,
            ensure_ascii=False,
        )

    def import_json(self, payload: str) -> int:
        """Import entries from a JSON payload (same format as export).

        Returns the number of entries successfully imported. Raises
        :class:`CatalogoError` on malformed JSON or schema errors.

        Note: this does NOT deduplicate by title — the user might
        intentionally have multiple entries with the same title.
        New ids are assigned; old ids are discarded.
        """
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise CatalogoError(
                "Import payload is not valid JSON", cause=str(exc)
            ) from exc
        if not isinstance(data, dict) or "entries" not in data:
            raise CatalogoError(
                "Import payload missing 'entries' key",
                payload_keys=list(data) if isinstance(data, dict) else None,
            )
        entries = data["entries"]
        if not isinstance(entries, list):
            raise CatalogoError(
                "Import 'entries' must be a list", type_observed=type(entries).__name__
            )
        imported = 0
        errors: list[str] = []
        for index, raw in enumerate(entries):
            try:
                self.create_entry(
                    title=raw["title"],
                    code=raw["code"],
                    description=raw.get("description"),
                    language=raw.get("language", "text"),
                    category=raw.get("category"),
                    tags=raw.get("tags", []),
                    origin_path=raw.get("origin_path"),
                    origin_line=raw.get("origin_line"),
                    is_public=bool(raw.get("is_public", False)),
                )
                imported += 1
            except (KeyError, CatalogoError) as exc:
                errors.append(f"entry #{index}: {exc}")
        if errors and imported == 0:
            # All entries failed — surface a single combined error.
            raise CatalogoError(
                "No entries could be imported",
                errors=errors,
            )
        return imported

    # ----- Internal helpers ------------------------------------------------

    def _upsert_tag(self, conn: sqlite3.Connection, name: str) -> int:
        """Insert a tag (idempotent) and return its id.

        We deliberately do not rely on ``Cursor.lastrowid`` after
        ``INSERT OR IGNORE`` because that attribute is **sticky** in
        sqlite3 — it returns the rowid of the *last successful* insert
        on the same connection, not the one we just executed. So if
        the previous INSERT succeeded with id=5 and this one is a
        no-op (tag already exists), ``lastrowid`` would still be 5 and
        we'd return the wrong id. The robust pattern is to always
        re-query by name after the upsert.
        """
        conn.execute(
            "INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,)
        )
        row = conn.execute(
            "SELECT id FROM tags WHERE name = ?", (name,)
        ).fetchone()
        assert row is not None, (
            f"tag disappeared after INSERT OR IGNORE: {name!r}"
        )
        return row["id"]

    def _tags_for_entry(
        self, conn: sqlite3.Connection, entry_id: int
    ) -> tuple[str, ...]:
        """Return the tag names for an entry, sorted alphabetically (case-insensitive).

        Sorting at read time (rather than relying on insertion order)
        makes the result deterministic and stable regardless of which
        order tags were provided in.
        """
        rows = conn.execute(
            """
            SELECT t.name FROM entry_tags et
            JOIN tags t ON t.id = et.tag_id
            WHERE et.entry_id = ?
            ORDER BY t.name COLLATE NOCASE
            """,
            (entry_id,),
        ).fetchall()
        return tuple(sorted((row["name"] for row in rows), key=str.lower))

    @staticmethod
    def _row_to_entry(row: sqlite3.Row, tags: tuple[str, ...]) -> Entry:
        # Timestamps are stored without timezone suffix (sqlite3 doesn't
        # enforce a tz). We append "+00:00" before parsing so the
        # resulting datetime is timezone-aware (UTC).
        def _parse(ts: str) -> datetime:
            if "T" in ts and ("+" not in ts and "Z" not in ts):
                ts = ts + "+00:00"
            return datetime.fromisoformat(ts)
        return Entry(
            id=row["id"],
            title=row["title"],
            code=row["code"],
            language=row["language"],
            description=row["description"],
            category=row["category"],
            origin_path=row["origin_path"],
            origin_line=row["origin_line"],
            is_public=bool(row["is_public"]),
            created_at=_parse(row["created_at"]),
            updated_at=_parse(row["updated_at"]),
            tags=tags,
        )

    @staticmethod
    def _validate_entry_fields(
        *,
        title: str,
        code: str,
        description: str | None,
        language: str,
        category: str | None,
        origin_path: str | None,
        origin_line: int | None,
    ) -> None:
        """Raise :class:`CatalogoError` if any field is invalid."""
        if not title or not title.strip():
            raise CatalogoError("Title is required")
        if len(title) > 200:
            raise CatalogoError(
                "Title is too long (max 200 chars)",
                length=len(title), max_length=200,
            )
        if not code:
            raise CatalogoError("Code is required")
        if len(code) > 100_000:
            raise CatalogoError(
                "Code is too long (max 100,000 chars)",
                length=len(code), max_length=100_000,
            )
        if description is not None and len(description) > 10_000:
            raise CatalogoError(
                "Description is too long (max 10,000 chars)",
                length=len(description), max_length=10_000,
            )
        if not language or len(language) > 30:
            raise CatalogoError(
                "Language must be 1-30 chars", length=len(language or "")
            )
        if category is not None and len(category) > 50:
            raise CatalogoError(
                "Category must be ≤ 50 chars", length=len(category)
            )
        if origin_line is not None and origin_line < 1:
            raise CatalogoError(
                "Origin line must be ≥ 1", origin_line=origin_line
            )

    # ----- Introspection (for tests / Settings dialog) -------------------

    @property
    def db_path(self) -> Path:
        return self._db_path


# Schema as a single script for atomic execution. Kept here (not in a
# .sql file) so the service is self-contained and the schema travels
# with the code. Triggers keep entries_fts in sync with entries.
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS entries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 200),
    description   TEXT CHECK(description IS NULL OR length(description) <= 10000),
    code          TEXT NOT NULL CHECK(length(code) BETWEEN 1 AND 100000),
    language      TEXT NOT NULL DEFAULT 'text' CHECK(length(language) <= 30),
    category      TEXT CHECK(category IS NULL OR length(category) <= 50),
    origin_path   TEXT,
    origin_line   INTEGER CHECK(origin_line IS NULL OR origin_line >= 1),
    is_public     INTEGER NOT NULL DEFAULT 0 CHECK(is_public IN (0, 1)),
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_entries_language   ON entries(language);
CREATE INDEX IF NOT EXISTS idx_entries_category   ON entries(category);
CREATE INDEX IF NOT EXISTS idx_entries_updated_at ON entries(updated_at DESC);

CREATE TABLE IF NOT EXISTS tags (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE CHECK(length(name) BETWEEN 1 AND 30)
);

CREATE TABLE IF NOT EXISTS entry_tags (
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    tag_id   INTEGER NOT NULL REFERENCES tags(id)   ON DELETE CASCADE,
    PRIMARY KEY (entry_id, tag_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
    title,
    description,
    code,
    content='entries',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
    INSERT INTO entries_fts(rowid, title, description, code)
    VALUES (new.id, new.title, new.description, new.code);
END;

CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN
    INSERT INTO entries_fts(entries_fts, rowid, title, description, code)
    VALUES ('delete', old.id, old.title, old.description, old.code);
END;

CREATE TRIGGER IF NOT EXISTS entries_au AFTER UPDATE ON entries BEGIN
    INSERT INTO entries_fts(entries_fts, rowid, title, description, code)
    VALUES ('delete', old.id, old.title, old.description, old.code);
    INSERT INTO entries_fts(rowid, title, description, code)
    VALUES (new.id, new.title, new.description, new.code);
END;

CREATE TABLE IF NOT EXISTS _migrations (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

INSERT OR IGNORE INTO _migrations (version, applied_at) VALUES (1, datetime('now'));
"""
