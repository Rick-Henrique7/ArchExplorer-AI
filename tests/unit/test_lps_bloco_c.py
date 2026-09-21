"""Tests for Bloco C extras — stats, latest_run, semantic validation,
catalog bridge, starter components (Change 007).

Bloco A already covers CRUD + JSON schema validation; this file
focuses on the *additions* the Bloco C task list calls out:

- C6: latest_run(model_id)
- C7+: cross-references (edge/group refs to missing nodes, ROOT
  uniqueness, self-loop edges)
- C7+: stats() aggregate
- Bridge: create_component_from_catalog() pulls a catalog Entry
- Starter components: seed_default_components() idempotency
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services import (
    CatalogoService,
    Entry,
    LpsService,
    seed_default_components,
)
from app.services.exceptions import LpsSpecError


@pytest.fixture
def service(tmp_path: Path) -> LpsService:
    return LpsService(db_path=tmp_path / "lps.db")


def _basic_payload() -> dict:
    return {
        "spec_version": "1.0",
        "nodes": [
            {"id": "root", "component_id": None, "variability": "ROOT", "label": "R"},
            {"id": "db", "component_id": None, "variability": "MANDATORY", "label": "DB"},
        ],
        "edges": [],
        "groups": [],
    }


def _make_entry(**overrides) -> Entry:
    base = dict(
        id=1, title="JWT helper", code="x = 1", language="python",
        description="JWT issuance helper", category="auth",
        origin_path=None, origin_line=None, is_public=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        tags=("jwt", "auth"),
    )
    base.update(overrides)
    return Entry(**base)


# ----- latest_run --------------------------------------------------------

def test_latest_run_returns_none_when_no_runs(service: LpsService) -> None:
    fm = service.create_feature_model(title="t", tree_structure=_basic_payload())
    assert service.latest_run(fm.id) is None


def test_latest_run_returns_most_recent(service: LpsService) -> None:
    fm = service.create_feature_model(title="t", tree_structure=_basic_payload())
    service.record_run(
        feature_model_id=fm.id, resolved_json="{}",
        output_dir="/tmp/a", file_count=1, duration_ms=10, status="SUCCESS",
    )
    service.record_run(
        feature_model_id=fm.id, resolved_json="{}",
        output_dir="/tmp/b", file_count=2, duration_ms=20, status="SUCCESS",
    )
    latest = service.latest_run(fm.id)
    assert latest is not None
    assert latest.output_dir == "/tmp/b"  # newer = output_dir = b


def test_latest_run_filters_by_model(service: LpsService) -> None:
    fm1 = service.create_feature_model(title="t1", tree_structure=_basic_payload())
    fm2 = service.create_feature_model(title="t2", tree_structure=_basic_payload())
    service.record_run(
        feature_model_id=fm1.id, resolved_json="{}",
        output_dir="/tmp/fm1", file_count=0, duration_ms=0, status="SUCCESS",
    )
    assert service.latest_run(fm2.id) is None


# ----- Semantic validation ----------------------------------------------

def test_validate_rejects_missing_root_node(service: LpsService) -> None:
    payload = {
        "spec_version": "1.0",
        "nodes": [
            {"id": "a", "component_id": None, "variability": "MANDATORY", "label": "A"},
        ],
        "edges": [],
        "groups": [],
    }
    with pytest.raises(LpsSpecError) as exc:
        service.create_feature_model(title="t", tree_structure=payload)
    assert "ROOT" in str(exc.value)


def test_validate_rejects_two_root_nodes(service: LpsService) -> None:
    payload = {
        "spec_version": "1.0",
        "nodes": [
            {"id": "r1", "component_id": None, "variability": "ROOT", "label": "R1"},
            {"id": "r2", "component_id": None, "variability": "ROOT", "label": "R2"},
        ],
        "edges": [],
        "groups": [],
    }
    with pytest.raises(LpsSpecError) as exc:
        service.create_feature_model(title="t", tree_structure=payload)
    assert "exactly one ROOT" in str(exc.value)


def test_validate_rejects_duplicate_node_ids(service: LpsService) -> None:
    payload = {
        "spec_version": "1.0",
        "nodes": [
            {"id": "root", "component_id": None, "variability": "ROOT", "label": "R"},
            {"id": "dup", "component_id": None, "variability": "MANDATORY", "label": "D1"},
            {"id": "dup", "component_id": None, "variability": "OPTIONAL", "label": "D2"},
        ],
        "edges": [],
        "groups": [],
    }
    with pytest.raises(LpsSpecError) as exc:
        service.create_feature_model(title="t", tree_structure=payload)
    assert "Duplicate node id" in str(exc.value)


def test_validate_rejects_edge_to_unknown_node(service: LpsService) -> None:
    payload = {
        "spec_version": "1.0",
        "nodes": [
            {"id": "root", "component_id": None, "variability": "ROOT", "label": "R"},
            {"id": "db", "component_id": None, "variability": "MANDATORY", "label": "DB"},
        ],
        "edges": [
            {"id": "e1", "source": "jwt", "target": "db", "relation": "REQUIRES"},
        ],
        "groups": [],
    }
    with pytest.raises(LpsSpecError) as exc:
        service.create_feature_model(title="t", tree_structure=payload)
    # JSON Pointer path (starts with "/" per RFC 6901).
    assert exc.value.context.get("path", "").endswith("/edges/0/source")
    assert exc.value.context.get("source") == "jwt"


def test_validate_rejects_self_loop_edge(service: LpsService) -> None:
    payload = {
        "spec_version": "1.0",
        "nodes": [
            {"id": "root", "component_id": None, "variability": "ROOT", "label": "R"},
            {"id": "a", "component_id": None, "variability": "OPTIONAL", "label": "A"},
        ],
        "edges": [
            {"id": "e1", "source": "a", "target": "a", "relation": "REQUIRES"},
        ],
        "groups": [],
    }
    with pytest.raises(LpsSpecError) as exc:
        service.create_feature_model(title="t", tree_structure=payload)
    assert "cannot connect a node to itself" in str(exc.value)


def test_validate_rejects_group_with_unknown_parent(service: LpsService) -> None:
    payload = {
        "spec_version": "1.0",
        "nodes": [
            {"id": "root", "component_id": None, "variability": "ROOT", "label": "R"},
            {"id": "a", "component_id": None, "variability": "OPTIONAL", "label": "A"},
        ],
        "edges": [],
        "groups": [
            {"id": "g1", "parent": "ghost", "kind": "OR", "children": ["a"]},
        ],
    }
    with pytest.raises(LpsSpecError) as exc:
        service.create_feature_model(title="t", tree_structure=payload)
    assert exc.value.context.get("path", "").endswith("/groups/0/parent")


def test_validate_rejects_group_with_unknown_child(service: LpsService) -> None:
    payload = {
        "spec_version": "1.0",
        "nodes": [
            {"id": "root", "component_id": None, "variability": "ROOT", "label": "R"},
            {"id": "a", "component_id": None, "variability": "OPTIONAL", "label": "A"},
        ],
        "edges": [],
        "groups": [
            {"id": "g1", "parent": "root", "kind": "OR", "children": ["a", "ghost"]},
        ],
    }
    with pytest.raises(LpsSpecError) as exc:
        service.create_feature_model(title="t", tree_structure=payload)
    assert exc.value.context.get("path", "").startswith("/groups/0/children/")


def test_update_tree_also_validates_semantics(service: LpsService) -> None:
    """``update_tree_structure`` runs the same checks as create."""
    fm = service.create_feature_model(title="t", tree_structure=_basic_payload())
    bad = {
        "spec_version": "1.0",
        "nodes": [
            {"id": "root", "component_id": None, "variability": "ROOT", "label": "R"},
        ],
        "edges": [],
        "groups": [],
    }
    # Only ROOT, no MANDATORY sibling — still valid (just a single
    # node tree). Add a bad edge to trigger the semantic check.
    bad_with_edge = dict(bad)
    bad_with_edge["edges"] = [
        {"id": "e1", "source": "ghost", "target": "root", "relation": "REQUIRES"},
    ]
    with pytest.raises(LpsSpecError):
        service.update_tree_structure(fm.id, bad_with_edge)


# ----- stats() ----------------------------------------------------------

def test_stats_empty_db(service: LpsService) -> None:
    s = service.stats()
    assert s["components_total"] == 0
    assert s["components_by_category"] == {}
    assert s["feature_models_total"] == 0
    assert s["feature_models_by_status"] == {}
    assert s["runs_total"] == 0
    assert s["runs_by_status"] == {}
    assert s["runs_total_files"] == 0


def test_stats_aggregates_components_by_category(service: LpsService) -> None:
    service.create_component(name="DB", category="database")
    service.create_component(name="OAuth", category="architecture")
    service.create_component(name="Pg", category="database")
    s = service.stats()
    assert s["components_total"] == 3
    assert s["components_by_category"] == {"database": 2, "architecture": 1}


def test_stats_aggregates_models_by_status(service: LpsService) -> None:
    fm1 = service.create_feature_model(title="t1", tree_structure=_basic_payload())
    fm2 = service.create_feature_model(title="t2", tree_structure=_basic_payload())
    service.set_validation_status(fm1.id, "VALID")
    s = service.stats()
    assert s["feature_models_total"] == 2
    assert s["feature_models_by_status"]["VALID"] == 1
    # DRAFT (fm2) + the DRAFT reset if any.
    assert s["feature_models_by_status"]["DRAFT"] >= 1


def test_stats_aggregates_runs(service: LpsService) -> None:
    fm = service.create_feature_model(title="t", tree_structure=_basic_payload())
    service.record_run(
        feature_model_id=fm.id, resolved_json="{}",
        output_dir="/x", file_count=3, duration_ms=10, status="SUCCESS",
    )
    service.record_run(
        feature_model_id=fm.id, resolved_json="{}",
        output_dir="/y", file_count=5, duration_ms=20, status="FAILED",
    )
    s = service.stats()
    assert s["runs_total"] == 2
    assert s["runs_by_status"]["SUCCESS"] == 1
    assert s["runs_by_status"]["FAILED"] == 1
    # total_files counts only SUCCESS runs.
    assert s["runs_total_files"] == 3


# ----- Catalog bridge ----------------------------------------------------

def test_create_component_from_catalog_pulls_fields(service: LpsService) -> None:
    entry = _make_entry(
        title="JWT helper",
        code="def issue(): pass",
        language="python",
        description="JWT issuance",
        tags=("jwt", "auth"),
    )
    comp = service.create_component_from_catalog(
        entry, category="architecture", jinja_template="services/fastapi_app.py.j2",
    )
    assert comp.name == "JWT helper"
    assert comp.category == "architecture"
    assert comp.code_snippet == "def issue(): pass"
    assert comp.jinja_template == "services/fastapi_app.py.j2"
    # Metadata bridges the catalog fields.
    assert comp.metadata["language"] == "python"
    assert comp.metadata["tags"] == ["jwt", "auth"]
    assert comp.metadata["source"] == "catalog"
    assert comp.metadata["catalog_id"] == 1


def test_create_component_from_catalog_uses_defaults(
    service: LpsService,
) -> None:
    """Defaults: category='service', jinja_template=None, svg=None."""
    entry = _make_entry()
    comp = service.create_component_from_catalog(entry)
    assert comp.category == "service"
    assert comp.jinja_template is None
    assert comp.svg_icon_path is None


def test_create_component_from_catalog_real_catalog_service(
    tmp_path: Path,
) -> None:
    """End-to-end: create an Entry in CatalogoService, bridge to LpsService."""
    catalog = CatalogoService(db_path=tmp_path / "cat.db")
    entry = catalog.create_entry(
        title="Real catalog entry",
        code="x = 42",
        language="python",
        tags=("real", "test"),
    )
    lps = LpsService(db_path=tmp_path / "lps.db")
    comp = lps.create_component_from_catalog(entry)
    assert comp.name == "Real catalog entry"
    assert comp.metadata["catalog_id"] == entry.id


# ----- Starter components -----------------------------------------------

def test_seed_inserts_all_starters_on_empty_db(service: LpsService) -> None:
    inserted = seed_default_components(service)
    assert inserted == 8
    assert service.stats()["components_total"] == 8


def test_seed_is_idempotent(service: LpsService) -> None:
    """Running seed twice does not duplicate rows."""
    seed_default_components(service)
    inserted = seed_default_components(service)
    assert inserted == 0
    assert service.stats()["components_total"] == 8


def test_seed_covers_all_categories(service: LpsService) -> None:
    """At least one starter per major category the user is likely to need."""
    seed_default_components(service)
    cats = {c.category for c in service.list_components()}
    assert {"service", "architecture", "database", "infra", "ui_ux", "design_pattern"} <= cats


def test_seed_uuids_are_deterministic() -> None:
    """UUIDs are stable across runs — used by the GUI to detect re-seed."""
    from app.services.lps_components_seed import list_starter_uuids
    a = list_starter_uuids()
    b = list_starter_uuids()
    assert a == b
    # All UUIDs are well-formed.
    for u in a:
        assert len(u) == 36
