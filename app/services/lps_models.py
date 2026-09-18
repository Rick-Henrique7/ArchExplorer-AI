"""Domain models for the LPS module (Change 007 — Bloco A).

Frozen dataclasses mirror the SQLite schema (Contrato 2 of
``changes/007-lps-feature-modeling/spec.md``). They are returned by
:class:`LpsService` on reads; writes accept plain kwargs and the
service builds the dataclass before returning.

Why a separate module instead of extending ``app/services/models.py``
(catalog models)? LPS has different lifetimes, FK targets and JSON
shapes; mixing them in one module would create a confusing "models.py"
that spans two domains. The cost is a second import line — the win
is that each domain stays small and self-contained.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# Allowed enums (mirrored from the spec). Kept as plain strings rather
# than Enum so the dataclasses stay JSON-friendly without adapters.

LPS_COMPONENT_CATEGORIES: tuple[str, ...] = (
    "ui_ux",
    "architecture",
    "design_pattern",
    "database",
    "service",
    "infra",
    "test",
)

LPS_VARIABILITY_TYPES: tuple[str, ...] = (
    "ROOT",
    "MANDATORY",
    "OPTIONAL",
    "ALTERNATIVE",
)

LPS_EDGE_RELATIONS: tuple[str, ...] = (
    "REQUIRES",
    "EXCLUDES",
)

LPS_GROUP_KINDS: tuple[str, ...] = (
    "MANDATORY",
    "OPTIONAL",
    "ALTERNATIVE",
    "OR",
)

LPS_VALIDATION_STATUS: tuple[str, ...] = (
    "DRAFT",
    "VALID",
    "INVALID",
)

LPS_RUN_STATUS: tuple[str, ...] = (
    "SUCCESS",
    "FAILED",
    "PARTIAL",
)


def _utcnow() -> datetime:
    """UTC ``datetime`` factory (timezone-aware)."""
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class LpsComponent:
    """A reusable building block the user drags into feature models.

    Mirrors the ``lps_components`` table. ``metadata_json`` is stored
    as a string in SQLite and parsed into a ``dict`` on read.
    """

    id: str
    name: str
    category: str
    description: str | None = None
    code_snippet: str | None = None
    svg_icon_path: str | None = None
    jinja_template: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Plain-dict serialization (export / debug)."""
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "code_snippet": self.code_snippet,
            "svg_icon_path": self.svg_icon_path,
            "jinja_template": self.jinja_template,
            "metadata": dict(self.metadata),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True)
class FeatureNode:
    """A single node in a feature model.

    The dataclass mirrors the JSON DSL (Contrato 1) one-to-one so
    the GUI can hand the JSON over without reshaping.
    """

    id: str
    component_id: str | None
    variability: str         # one of LPS_VARIABILITY_TYPES
    label: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "component_id": self.component_id,
            "variability": self.variability,
            "label": self.label,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FeatureNode":
        return cls(
            id=payload["id"],
            component_id=payload.get("component_id"),
            variability=payload["variability"],
            label=payload.get("label", payload["id"]),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(frozen=True)
class FeatureEdge:
    """A relation between two nodes (REQUIRES or EXCLUDES)."""

    id: str
    source: str
    target: str
    relation: str            # one of LPS_EDGE_RELATIONS

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "relation": self.relation,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FeatureEdge":
        return cls(
            id=payload["id"],
            source=payload["source"],
            target=payload["target"],
            relation=payload["relation"],
        )


@dataclass(frozen=True)
class FeatureGroup:
    """A cardinality constraint over a set of children of one parent.

    - ``kind == "MANDATORY"``  : every child must be present
    - ``kind == "OPTIONAL"``   : zero or more children
    - ``kind == "ALTERNATIVE"``: exactly one child
    - ``kind == "OR"``         : at least one child
    """

    id: str
    parent: str
    kind: str                # one of LPS_GROUP_KINDS
    children: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "parent": self.parent,
            "kind": self.kind,
            "children": list(self.children),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FeatureGroup":
        return cls(
            id=payload["id"],
            parent=payload["parent"],
            kind=payload["kind"],
            children=tuple(payload.get("children") or ()),
        )


@dataclass(frozen=True)
class FeatureModel:
    """The full feature model (DSL JSON, validated).

    Combines the persisted metadata (title, validation_status) with
    the parsed graph (nodes / edges / groups). The raw
    ``tree_structure_json`` is kept for round-tripping — the GUI
    re-serializes from the dataclasses anyway.
    """

    id: str
    title: str
    description: str | None
    tree_structure_json: str
    nodes: tuple[FeatureNode, ...]
    edges: tuple[FeatureEdge, ...]
    groups: tuple[FeatureGroup, ...]
    validation_status: str       # one of LPS_VALIDATION_STATUS
    last_solved_at: datetime | None
    created_at: datetime
    updated_at: datetime

    def selected_node_ids(self) -> tuple[str, ...]:
        """Default selection: ROOT + every MANDATORY node.

        OPTIONAL nodes are off; ALTERNATIVE children are off
        (caller must pick one). The SAT solver then validates this
        baseline selection; the user toggles individual nodes in the
        inspector and re-runs validation.
        """
        ids: list[str] = []
        for node in self.nodes:
            if node.variability in ("ROOT", "MANDATORY"):
                ids.append(node.id)
        return tuple(ids)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "tree_structure_json": self.tree_structure_json,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "groups": [g.to_dict() for g in self.groups],
            "validation_status": self.validation_status,
            "last_solved_at": (
                self.last_solved_at.isoformat() if self.last_solved_at else None
            ),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True)
class ProductRun:
    """One execution of "Generate Product" — kept for audit + debug.

    ``resolved_json`` is the JSON the SAT solver produced (the
    selection that passed validation). ``output_dir`` is the
    user-chosen destination. ``status`` is SUCCESS / FAILED / PARTIAL
    (PARTIAL = some files written, some failed).
    """

    id: int
    feature_model_id: str
    resolved_json: str
    output_dir: str
    file_count: int
    duration_ms: int
    status: str                # one of LPS_RUN_STATUS
    error_message: str | None
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "feature_model_id": self.feature_model_id,
            "resolved_json": self.resolved_json,
            "output_dir": self.output_dir,
            "file_count": self.file_count,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat(),
        }
