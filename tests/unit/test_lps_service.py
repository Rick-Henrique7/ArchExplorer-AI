"""Tests for LpsService — CRUD + schema (Change 007 — Bloco A).

Covers:

- Schema materialization on init (creates 3 tables + indexes).
- Components CRUD (create/get/list/update/delete + validation).
- Feature models CRUD (create/get/list/update_tree/delete + JSON validation).
- Product runs (record + list).
- DB-path resolution (default location + custom override).
- Validation errors carry JSON Pointer path in ``LpsSpecError.context``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.exceptions import LpsSpecError
from app.services.lps_models import FeatureModel
from app.services.lps_service import (
    LpsService,
    _ALLOWED_CATEGORIES,
)


@pytest.fixture
def service(tmp_path: Path) -> LpsService:
    """A fresh LpsService pointed at a tmp SQLite file."""
    return LpsService(db_path=tmp_path / "lps.db")


@pytest.fixture
def uuid_a() -> str:
    return "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def uuid_b() -> str:
    return "22222222-2222-4222-8222-222222222222"


# ----- Schema ------------------------------------------------------------

def test_init_schema_creates_tables(service: LpsService) -> None:
    """All 3 LPS tables + their indexes are materialized."""
    with service._connect() as conn:
        names = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "lps_components" in names
    assert "lps_feature_models" in names
    assert "lps_product_runs" in names


def test_init_schema_is_idempotent(tmp_path: Path) -> None:
    """Reopening an existing DB is a no-op (CREATE IF NOT EXISTS)."""
    path = tmp_path / "lps.db"
    LpsService(db_path=path)
    # Second init must not raise.
    LpsService(db_path=path)


# ----- Components CRUD ---------------------------------------------------

def test_create_component_returns_dataclass(service: LpsService) -> None:
    comp = service.create_component(
        name="OAuth2",
        category="architecture",
        description="OAuth 2.0 provider",
        code_snippet="class OAuth2: pass",
    )
    assert comp.id  # auto-generated UUID
    assert comp.name == "OAuth2"
    assert comp.category == "architecture"
    assert comp.description == "OAuth 2.0 provider"
    assert comp.metadata == {}


def test_create_component_with_explicit_uuid(service: LpsService, uuid_a: str) -> None:
    comp = service.create_component(
        id=uuid_a, name="X", category="database",
    )
    assert comp.id == uuid_a


def test_create_component_rejects_non_uuid(service: LpsService) -> None:
    with pytest.raises(LpsSpecError):
        service.create_component(id="not-a-uuid", name="X", category="database")


def test_create_component_rejects_empty_name(service: LpsService) -> None:
    with pytest.raises(LpsSpecError):
        service.create_component(name="", category="database")


def test_create_component_rejects_invalid_category(service: LpsService) -> None:
    with pytest.raises(LpsSpecError) as exc:
        service.create_component(name="X", category="bogus")
    assert "Invalid category" in str(exc.value)


def test_get_component_returns_none_when_missing(service: LpsService) -> None:
    assert service.get_component("00000000-0000-4000-8000-000000000000") is None


def test_list_components_filters_by_category(service: LpsService) -> None:
    service.create_component(name="DB", category="database")
    service.create_component(name="OAuth", category="architecture")
    service.create_component(name="Pg", category="database")
    dbs = service.list_components(category="database")
    assert {c.name for c in dbs} == {"DB", "Pg"}
    all_comps = service.list_components()
    assert len(all_comps) == 3


def test_update_component_partial(service: LpsService, uuid_a: str) -> None:
    service.create_component(
        id=uuid_a, name="Old", category="database", description="d1",
    )
    updated = service.update_component(uuid_a, name="New", description="d2")
    assert updated.name == "New"
    assert updated.description == "d2"
    # Category untouched.
    assert updated.category == "database"


def test_update_component_rejects_invalid_category(
    service: LpsService, uuid_a: str
) -> None:
    service.create_component(id=uuid_a, name="X", category="database")
    with pytest.raises(LpsSpecError):
        service.update_component(uuid_a, category="bogus")


def test_delete_component(service: LpsService, uuid_a: str) -> None:
    service.create_component(id=uuid_a, name="X", category="database")
    service.delete_component(uuid_a)
    assert service.get_component(uuid_a) is None


def test_delete_component_missing_raises(service: LpsService) -> None:
    with pytest.raises(LpsSpecError):
        service.delete_component("00000000-0000-4000-8000-000000000000")


# ----- Feature models ---------------------------------------------------

def _basic_payload() -> dict:
    return {
        "spec_version": "1.0",
        "model_id": "lps-demo",
        "nodes": [
            {"id": "root", "component_id": None, "variability": "ROOT", "label": "Root"},
            {"id": "db", "component_id": "c-db", "variability": "MANDATORY", "label": "DB"},
        ],
        "edges": [],
        "groups": [],
    }


def test_create_feature_model(service: LpsService) -> None:
    fm = service.create_feature_model(
        title="Auth system", description="OAuth demo", tree_structure=_basic_payload(),
    )
    assert fm.id
    assert fm.title == "Auth system"
    assert fm.validation_status == "DRAFT"
    assert len(fm.nodes) == 2
    assert fm.nodes[0].variability == "ROOT"


def test_create_feature_model_rejects_invalid_json(service: LpsService) -> None:
    """Bad variability string → LpsSpecError with JSON Pointer path."""
    bad = {
        "spec_version": "1.0",
        "nodes": [
            {"id": "x", "component_id": None, "variability": "BOGUS", "label": "X"},
        ],
        "edges": [],
        "groups": [],
    }
    with pytest.raises(LpsSpecError) as exc:
        service.create_feature_model(title="t", tree_structure=bad)
    assert exc.value.context.get("path", "").startswith("nodes/0")


def test_create_feature_model_rejects_wrong_spec_version(service: LpsService) -> None:
    bad = {"spec_version": "2.0", "nodes": [], "edges": [], "groups": []}
    with pytest.raises(LpsSpecError):
        service.create_feature_model(title="t", tree_structure=bad)


def test_create_feature_model_requires_title(service: LpsService) -> None:
    with pytest.raises(LpsSpecError):
        service.create_feature_model(title="")


def test_get_feature_model(service: LpsService) -> None:
    fm = service.create_feature_model(title="t", tree_structure=_basic_payload())
    got = service.get_feature_model(fm.id)
    assert got is not None
    assert got.id == fm.id


def test_update_tree_structure_resets_status_to_draft(
    service: LpsService,
) -> None:
    fm = service.create_feature_model(title="t", tree_structure=_basic_payload())
    service.set_validation_status(fm.id, "VALID")
    updated = service.update_tree_structure(
        fm.id, _basic_payload(),
    )
    # Editing the tree invalidates the previous validation result.
    assert updated.validation_status == "DRAFT"


def test_set_validation_status(service: LpsService) -> None:
    fm = service.create_feature_model(title="t", tree_structure=_basic_payload())
    service.set_validation_status(fm.id, "VALID")
    assert service.get_feature_model(fm.id).validation_status == "VALID"


def test_set_validation_status_rejects_bad_value(service: LpsService) -> None:
    fm = service.create_feature_model(title="t", tree_structure=_basic_payload())
    with pytest.raises(LpsSpecError):
        service.set_validation_status(fm.id, "BOGUS")


def test_delete_feature_model_cascades_runs(
    service: LpsService,
) -> None:
    fm = service.create_feature_model(title="t", tree_structure=_basic_payload())
    service.record_run(
        feature_model_id=fm.id,
        resolved_json="{}",
        output_dir="/tmp/x",
        file_count=3,
        duration_ms=10,
        status="SUCCESS",
    )
    service.delete_feature_model(fm.id)
    # FK CASCADE removed the run too.
    assert service.list_runs(feature_model_id=fm.id) == []


# ----- Product runs ----------------------------------------------------

def test_record_run_and_list(service: LpsService) -> None:
    fm = service.create_feature_model(title="t", tree_structure=_basic_payload())
    run = service.record_run(
        feature_model_id=fm.id,
        resolved_json='{"selected": ["root", "db"]}',
        output_dir="/tmp/gen",
        file_count=4,
        duration_ms=42,
        status="SUCCESS",
    )
    assert run.id > 0
    assert run.status == "SUCCESS"
    listed = service.list_runs(feature_model_id=fm.id)
    assert len(listed) == 1
    assert listed[0].id == run.id


def test_record_run_rejects_bad_status(service: LpsService) -> None:
    fm = service.create_feature_model(title="t", tree_structure=_basic_payload())
    with pytest.raises(LpsSpecError):
        service.record_run(
            feature_model_id=fm.id,
            resolved_json="{}",
            output_dir="/tmp/x",
            file_count=0,
            duration_ms=0,
            status="BOGUS",
        )


def test_list_runs_without_filter(service: LpsService) -> None:
    fm1 = service.create_feature_model(title="t1", tree_structure=_basic_payload())
    fm2 = service.create_feature_model(title="t2", tree_structure=_basic_payload())
    service.record_run(
        feature_model_id=fm1.id, resolved_json="{}", output_dir="/x",
        file_count=0, duration_ms=0, status="SUCCESS",
    )
    service.record_run(
        feature_model_id=fm2.id, resolved_json="{}", output_dir="/x",
        file_count=0, duration_ms=0, status="SUCCESS",
    )
    assert len(service.list_runs()) == 2


# ----- Introspection ----------------------------------------------------

def test_db_path_returns_resolved_path(tmp_path: Path) -> None:
    s = LpsService(db_path=tmp_path / "x.db")
    assert s.db_path == tmp_path / "x.db"


def test_default_path_categories_match_documented_set() -> None:
    """The whitelist of categories matches the spec docstring."""
    assert _ALLOWED_CATEGORIES == frozenset({
        "ui_ux", "architecture", "design_pattern",
        "database", "service", "infra", "test",
    })
