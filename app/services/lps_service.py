"""LPS service — SQLite CRUD for components, feature models, runs (Change 007).

Lives in the **same** SQLite file as the catalog (``catalogo.db``).
Adds three new tables (``lps_components``, ``lps_feature_models``,
``lps_product_runs``) without touching the catalog tables.

Connection handling mirrors :class:`CatalogoService`:
- Foreign keys ON per-connection
- ``row_factory = sqlite3.Row`` for column-by-name access
- Schema materialized on every ``__init__`` via ``CREATE IF NOT EXISTS``
- Corruption -> ``.db.bak`` rename + raise :class:`LpsSpecError`

The service is intentionally **read-write only** — it doesn't know
about QGraphicsView, Jinja2, or pysat. Those live in their own
modules (``lps_solver_worker``, ``template_engine``, etc.) and call
into ``LpsService`` for persistence.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from app.services.catalog_service import default_catalog_path
from app.services.exceptions import LpsSpecError
from app.services.lps_models import (
    FeatureEdge,
    FeatureGroup,
    FeatureModel,
    FeatureNode,
    LpsComponent,
    ProductRun,
)

# --- Validation regexes / constants ---------------------------------------

# UUID v4 — lowercase, hyphen-separated, 8-4-4-4-12 hex.
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

# Whitelisted component categories (matches lps_models.LPS_COMPONENT_CATEGORIES).
_ALLOWED_CATEGORIES = frozenset({
    "ui_ux", "architecture", "design_pattern",
    "database", "service", "infra", "test",
})

# Whitelisted variability / relation / group-kind strings.
_ALLOWED_VARIABILITY = frozenset({"ROOT", "MANDATORY", "OPTIONAL", "ALTERNATIVE"})
_ALLOWED_RELATIONS = frozenset({"REQUIRES", "EXCLUDES"})
_ALLOWED_GROUP_KINDS = frozenset({"MANDATORY", "OPTIONAL", "ALTERNATIVE", "OR"})
_ALLOWED_VALIDATION = frozenset({"DRAFT", "VALID", "INVALID"})
_ALLOWED_RUN_STATUS = frozenset({"SUCCESS", "FAILED", "PARTIAL"})


def _utcnow_iso() -> str:
    """ISO-8601 in UTC with explicit ``+00:00`` offset."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_timestamp(value: str) -> datetime:
    """Parse a stored timestamp; append ``+00:00`` if no tz present."""
    if "T" in value and ("+" not in value and "Z" not in value):
        value = value + "+00:00"
    return datetime.fromisoformat(value)


class LpsService:
    """SQLite-backed CRUD for the LPS module (Change 007 — Bloco A).

    See ``changes/007-lps-feature-modeling/spec.md`` (Contrato 2) for
    the table layout and ``design.md`` (sec. 5) for migration notes.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        if db_path is None:
            env_value = os.environ.get("ARCHEXPLORER_CATALOG_DB")
            db_path = Path(env_value) if env_value else default_catalog_path()
        self._db_path: Path = Path(db_path)
        # The directory was created by CatalogoService; safe even if not.
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ----- Connection management -----------------------------------------

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a sqlite3 connection; close it on exit.

        Foreign keys are enabled per-connection (SQLite disables them
        by default for backwards compatibility). ``row_factory`` is
        set to :class:`sqlite3.Row` for column-by-name access.
        """
        conn = sqlite3.connect(self._db_path)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            yield conn
        finally:
            conn.close()

    def _init_schema(self) -> None:
        """Create the LPS tables. Idempotent. Corrupt DB → ``*.bak`` rename."""
        try:
            with self._connect() as conn:
                conn.executescript(_SCHEMA_SQL)
                conn.commit()
        except sqlite3.DatabaseError as exc:
            backup = self._db_path.with_suffix(".db.bak")
            try:
                self._db_path.rename(backup)
            except OSError:
                pass
            with self._connect() as conn:
                conn.executescript(_SCHEMA_SQL)
                conn.commit()
            raise LpsSpecError(
                "LPS database was corrupted; backed up and recreated",
                path=str(self._db_path),
                backup=str(backup),
                cause=str(exc),
            )

    # ----- Components CRUD ------------------------------------------------

    def create_component(
        self,
        *,
        id: str | None = None,
        name: str,
        category: str,
        description: str | None = None,
        code_snippet: str | None = None,
        svg_icon_path: str | None = None,
        jinja_template: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LpsComponent:
        """Insert a new component and return it.

        Validates ``id`` (UUID v4) and ``category`` (whitelist) up
        front; relies on CHECK constraints to catch the rest.
        """
        if not name or not name.strip():
            raise LpsSpecError("Component name is required")
        if category not in _ALLOWED_CATEGORIES:
            raise LpsSpecError(
                "Invalid category",
                category=category,
                allowed=sorted(_ALLOWED_CATEGORIES),
            )
        comp_id = id or str(uuid.uuid4())
        if not _UUID_RE.match(comp_id):
            raise LpsSpecError("Component id must be UUID v4", id=comp_id)
        now = _utcnow_iso()
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO lps_components
                        (id, name, category, description, code_snippet,
                         svg_icon_path, jinja_template, metadata_json,
                         created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        comp_id,
                        name.strip(),
                        category,
                        description,
                        code_snippet,
                        svg_icon_path,
                        jinja_template,
                        meta_json,
                        now, now,
                    ),
                )
                conn.commit()
        except sqlite3.IntegrityError as exc:
            raise LpsSpecError(
                "Failed to insert LPS component",
                id=comp_id,
                cause=str(exc),
            ) from exc
        return self.get_component(comp_id)  # type: ignore[return-value]

    def get_component(self, component_id: str) -> LpsComponent | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM lps_components WHERE id = ?",
                (component_id,),
            ).fetchone()
        return self._row_to_component(row) if row else None

    def list_components(
        self, *, category: str | None = None, limit: int = 200
    ) -> list[LpsComponent]:
        """All components, optionally filtered by category."""
        if category:
            if category not in _ALLOWED_CATEGORIES:
                raise LpsSpecError(
                    "Invalid category", category=category,
                )
            sql = (
                "SELECT * FROM lps_components WHERE category = ? "
                "ORDER BY updated_at DESC LIMIT ?"
            )
            params: tuple = (category, limit)
        else:
            sql = "SELECT * FROM lps_components ORDER BY updated_at DESC LIMIT ?"
            params = (limit,)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_component(r) for r in rows if r is not None]

    def update_component(
        self,
        component_id: str,
        *,
        name: str | None = None,
        category: str | None = None,
        description: str | None = None,
        code_snippet: str | None = None,
        svg_icon_path: str | None = None,
        jinja_template: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LpsComponent:
        existing = self.get_component(component_id)
        if existing is None:
            raise LpsSpecError("Component not found", component_id=component_id)
        new_name = name if name is not None else existing.name
        new_category = category if category is not None else existing.category
        new_desc = description if description is not None else existing.description
        new_code = code_snippet if code_snippet is not None else existing.code_snippet
        new_svg = svg_icon_path if svg_icon_path is not None else existing.svg_icon_path
        new_template = (
            jinja_template if jinja_template is not None else existing.jinja_template
        )
        new_meta_json = (
            json.dumps(metadata, ensure_ascii=False)
            if metadata is not None
            else json.dumps(existing.metadata, ensure_ascii=False)
        )
        if new_category not in _ALLOWED_CATEGORIES:
            raise LpsSpecError(
                "Invalid category", category=new_category,
            )
        now = _utcnow_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE lps_components SET
                    name = ?, category = ?, description = ?,
                    code_snippet = ?, svg_icon_path = ?,
                    jinja_template = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    new_name.strip(),
                    new_category,
                    new_desc,
                    new_code,
                    new_svg,
                    new_template,
                    new_meta_json,
                    now,
                    component_id,
                ),
            )
            conn.commit()
        refreshed = self.get_component(component_id)
        assert refreshed is not None
        return refreshed

    def delete_component(self, component_id: str) -> None:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM lps_components WHERE id = ?",
                (component_id,),
            )
            conn.commit()
        if cur.rowcount == 0:
            raise LpsSpecError("Component not found", component_id=component_id)

    # ----- Feature models ------------------------------------------------

    def create_feature_model(
        self,
        *,
        id: str | None = None,
        title: str,
        description: str | None = None,
        tree_structure: dict[str, Any] | None = None,
    ) -> FeatureModel:
        """Insert a new feature model and return it.

        ``tree_structure`` is the DSL JSON (Contrato 1). It's
        validated via :class:`FeatureModelPayload` (pydantic) on
        insert; invalid payloads raise :class:`LpsSpecError` with the
        JSON Pointer path of the offending field.
        """
        if not title or not title.strip():
            raise LpsSpecError("Feature model title is required")
        model_id = id or str(uuid.uuid4())
        if not _UUID_RE.match(model_id):
            raise LpsSpecError("Feature model id must be UUID v4", id=model_id)
        # Validate the tree (defaults to empty).
        payload = tree_structure or {"nodes": [], "edges": [], "groups": []}
        tree_json = self._validate_tree(payload)
        now = _utcnow_iso()
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO lps_feature_models
                        (id, title, description, tree_structure_json,
                         validation_status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'DRAFT', ?, ?)
                    """,
                    (model_id, title.strip(), description, tree_json, now, now),
                )
                conn.commit()
        except sqlite3.IntegrityError as exc:
            raise LpsSpecError(
                "Failed to insert feature model",
                id=model_id,
                cause=str(exc),
            ) from exc
        result = self.get_feature_model(model_id)
        assert result is not None
        return result

    def get_feature_model(self, model_id: str) -> FeatureModel | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM lps_feature_models WHERE id = ?",
                (model_id,),
            ).fetchone()
        return self._row_to_feature_model(row) if row else None

    def list_feature_models(self, *, limit: int = 200) -> list[FeatureModel]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM lps_feature_models ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_feature_model(r) for r in rows if r is not None]

    def update_tree_structure(
        self, model_id: str, tree_structure: dict[str, Any]
    ) -> FeatureModel:
        existing = self.get_feature_model(model_id)
        if existing is None:
            raise LpsSpecError("Feature model not found", model_id=model_id)
        tree_json = self._validate_tree(tree_structure)
        now = _utcnow_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE lps_feature_models SET
                    tree_structure_json = ?, updated_at = ?,
                    validation_status = 'DRAFT'
                WHERE id = ?
                """,
                (tree_json, now, model_id),
            )
            conn.commit()
        refreshed = self.get_feature_model(model_id)
        assert refreshed is not None
        return refreshed

    def set_validation_status(
        self,
        model_id: str,
        status: str,
        *,
        last_solved_at: datetime | None = None,
    ) -> None:
        if status not in _ALLOWED_VALIDATION:
            raise LpsSpecError(
                "Invalid validation_status", status=status,
                allowed=sorted(_ALLOWED_VALIDATION),
            )
        ts = (last_solved_at or datetime.now(timezone.utc)).isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE lps_feature_models SET
                    validation_status = ?, last_solved_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (status, ts, ts, model_id),
            )
            conn.commit()

    def delete_feature_model(self, model_id: str) -> None:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM lps_feature_models WHERE id = ?",
                (model_id,),
            )
            conn.commit()
        if cur.rowcount == 0:
            raise LpsSpecError("Feature model not found", model_id=model_id)

    # ----- Product runs --------------------------------------------------

    def record_run(
        self,
        *,
        feature_model_id: str,
        resolved_json: str,
        output_dir: str,
        file_count: int,
        duration_ms: int,
        status: str,
        error_message: str | None = None,
    ) -> ProductRun:
        if status not in _ALLOWED_RUN_STATUS:
            raise LpsSpecError("Invalid run status", status=status)
        now = _utcnow_iso()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO lps_product_runs
                    (feature_model_id, resolved_json, output_dir,
                     file_count, duration_ms, status, error_message,
                     created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feature_model_id, resolved_json, output_dir,
                    file_count, duration_ms, status, error_message,
                    now,
                ),
            )
            conn.commit()
            run_id = cur.lastrowid
        assert run_id is not None
        runs = self.list_runs(feature_model_id=feature_model_id, limit=1)
        # Just-fetched; must include our row.
        assert runs and runs[0].id == run_id
        return runs[0]

    def list_runs(
        self, *, feature_model_id: str | None = None, limit: int = 50
    ) -> list[ProductRun]:
        if feature_model_id is not None:
            sql = (
                "SELECT * FROM lps_product_runs WHERE feature_model_id = ? "
                "ORDER BY id DESC LIMIT ?"
            )
            params: tuple = (feature_model_id, limit)
        else:
            sql = "SELECT * FROM lps_product_runs ORDER BY id DESC LIMIT ?"
            params = (limit,)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_run(r) for r in rows if r is not None]

    # ----- Validation ----------------------------------------------------

    def _validate_tree(self, payload: dict[str, Any]) -> str:
        """Validate ``payload`` against the DSL JSON (Contrato 1).

        Returns the canonical JSON string to be stored. Raises
        :class:`LpsSpecError` with the JSON Pointer path on failure.
        """
        # Pydantic models live in this same module (kept light to
        # avoid creating yet another file for a 20-line model).
        try:
            FeatureModelPayload.model_validate(payload)
        except PydanticValidationError as exc:
            errors = exc.errors()
            first = errors[0] if errors else {}
            path = "/".join(str(p) for p in first.get("loc", ()))
            raise LpsSpecError(
                "Invalid feature model JSON",
                path=path or "/",
                errors=errors,
            ) from exc
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    # ----- Row → dataclass helpers ---------------------------------------

    @staticmethod
    def _row_to_component(row: sqlite3.Row) -> LpsComponent:
        meta_raw = row["metadata_json"] or "{}"
        try:
            meta = json.loads(meta_raw)
        except json.JSONDecodeError:
            meta = {}
        return LpsComponent(
            id=row["id"],
            name=row["name"],
            category=row["category"],
            description=row["description"],
            code_snippet=row["code_snippet"],
            svg_icon_path=row["svg_icon_path"],
            jinja_template=row["jinja_template"],
            metadata=meta,
            created_at=_parse_timestamp(row["created_at"]),
            updated_at=_parse_timestamp(row["updated_at"]),
        )

    @staticmethod
    def _row_to_feature_model(row: sqlite3.Row) -> FeatureModel:
        tree = json.loads(row["tree_structure_json"])
        nodes = tuple(
            FeatureNode.from_dict(n) for n in tree.get("nodes", [])
        )
        edges = tuple(
            FeatureEdge.from_dict(e) for e in tree.get("edges", [])
        )
        groups = tuple(
            FeatureGroup.from_dict(g) for g in tree.get("groups", [])
        )
        last_solved_raw = row["last_solved_at"]
        return FeatureModel(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            tree_structure_json=row["tree_structure_json"],
            nodes=nodes,
            edges=edges,
            groups=groups,
            validation_status=row["validation_status"],
            last_solved_at=(
                _parse_timestamp(last_solved_raw) if last_solved_raw else None
            ),
            created_at=_parse_timestamp(row["created_at"]),
            updated_at=_parse_timestamp(row["updated_at"]),
        )

    @staticmethod
    def _row_to_run(row: sqlite3.Row) -> ProductRun:
        return ProductRun(
            id=row["id"],
            feature_model_id=row["feature_model_id"],
            resolved_json=row["resolved_json"],
            output_dir=row["output_dir"],
            file_count=row["file_count"],
            duration_ms=row["duration_ms"],
            status=row["status"],
            error_message=row["error_message"],
            created_at=_parse_timestamp(row["created_at"]),
        )

    # ----- Introspection --------------------------------------------------

    @property
    def db_path(self) -> Path:
        return self._db_path


# --- Pydantic payload for the DSL JSON (Contrato 1) ---------------------

from pydantic import BaseModel, Field, field_validator


class FeatureNodePayload(BaseModel):
    """Pydantic shape for one node in the DSL JSON.

    Kept permissive on extra fields (``metadata`` is free-schema) so
    the GUI can pass custom props without friction.
    """

    id: str = Field(..., min_length=1, max_length=64)
    component_id: str | None = None
    variability: str
    label: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("variability")
    @classmethod
    def _v_variability(cls, value: str) -> str:
        if value not in _ALLOWED_VARIABILITY:
            raise ValueError(
                f"variability must be one of {sorted(_ALLOWED_VARIABILITY)}"
            )
        return value


class FeatureEdgePayload(BaseModel):
    """Pydantic shape for one edge."""

    id: str = Field(..., min_length=1, max_length=64)
    source: str = Field(..., min_length=1, max_length=64)
    target: str = Field(..., min_length=1, max_length=64)
    relation: str

    @field_validator("relation")
    @classmethod
    def _v_relation(cls, value: str) -> str:
        if value not in _ALLOWED_RELATIONS:
            raise ValueError(
                f"relation must be one of {sorted(_ALLOWED_RELATIONS)}"
            )
        return value


class FeatureGroupPayload(BaseModel):
    """Pydantic shape for one cardinality group."""

    id: str = Field(..., min_length=1, max_length=64)
    parent: str = Field(..., min_length=1, max_length=64)
    kind: str
    children: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("kind")
    @classmethod
    def _v_kind(cls, value: str) -> str:
        if value not in _ALLOWED_GROUP_KINDS:
            raise ValueError(
                f"kind must be one of {sorted(_ALLOWED_GROUP_KINDS)}"
            )
        return value


class FeatureModelPayload(BaseModel):
    """Pydantic shape for the top-level DSL JSON (Contrato 1)."""

    spec_version: str = Field(default="1.0")
    model_id: str | None = None
    title: str | None = None
    description: str | None = None
    nodes: list[FeatureNodePayload] = Field(default_factory=list, max_length=200)
    edges: list[FeatureEdgePayload] = Field(default_factory=list, max_length=500)
    groups: list[FeatureGroupPayload] = Field(default_factory=list, max_length=50)

    @field_validator("spec_version")
    @classmethod
    def _v_spec_version(cls, value: str) -> str:
        if value != "1.0":
            raise ValueError(f"spec_version must be '1.0', got {value!r}")
        return value


# --- Schema ---------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS lps_components (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 100),
    category      TEXT NOT NULL CHECK(category IN (
                      'ui_ux','architecture','design_pattern',
                      'database','service','infra','test'
                  )),
    description   TEXT CHECK(description IS NULL OR length(description) <= 5000),
    code_snippet  TEXT CHECK(code_snippet IS NULL OR length(code_snippet) <= 100000),
    svg_icon_path TEXT,
    jinja_template TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_lps_components_category ON lps_components(category);

CREATE TABLE IF NOT EXISTS lps_feature_models (
    id                  TEXT PRIMARY KEY,
    title               TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 200),
    description         TEXT,
    tree_structure_json TEXT NOT NULL,
    validation_status   TEXT NOT NULL DEFAULT 'DRAFT' CHECK(validation_status IN ('DRAFT','VALID','INVALID')),
    last_solved_at      TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_lps_models_status ON lps_feature_models(validation_status);

CREATE TABLE IF NOT EXISTS lps_product_runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    feature_model_id TEXT NOT NULL REFERENCES lps_feature_models(id) ON DELETE CASCADE,
    resolved_json    TEXT NOT NULL,
    output_dir       TEXT NOT NULL,
    file_count       INTEGER NOT NULL,
    duration_ms      INTEGER NOT NULL,
    status           TEXT NOT NULL CHECK(status IN ('SUCCESS','FAILED','PARTIAL')),
    error_message    TEXT,
    created_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_lps_runs_model ON lps_product_runs(feature_model_id);
"""
