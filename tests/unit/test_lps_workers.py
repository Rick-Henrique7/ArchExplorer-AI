"""Tests for LPS workers (Change 007 — Bloco E — tasks E11/E12).

We don't run the workers through QThreadPool (those integration
paths are covered by ``test_lps_full_flow``). Instead we call
``worker.run()`` synchronously — the same pattern used by
``test_analysis_worker.py`` — to validate the synchronous contract
and signal payloads.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services import (
    LpsService,
    LpsComponent,
    TemplateEngine,
    VariabilitySolver,
)
from app.services.lps_models import (
    FeatureEdge,
    FeatureModel,
    FeatureNode,
)
from app.workers import (
    GeneratorResult,
    LpsGeneratorWorker,
    LpsSolverWorker,
)


# ----- Helpers -----------------------------------------------------------

def _make_feature_model() -> FeatureModel:
    nodes = (
        FeatureNode(id="root", component_id=None, variability="ROOT", label="R"),
        FeatureNode(
            id="comp", component_id="11111111-1111-4111-8111-111111111111",
            variability="MANDATORY", label="FastAPI",
        ),
    )
    edges = ()
    groups = ()
    now = datetime.now(timezone.utc)
    return FeatureModel(
        id="m", title="t", description=None, tree_structure_json="{}",
        nodes=nodes, edges=edges, groups=groups,
        validation_status="DRAFT", last_solved_at=None,
        created_at=now, updated_at=now,
    )


def _make_component(component_id: str, name: str, template: str) -> LpsComponent:
    return LpsComponent(
        id=component_id, name=name, category="service",
        description="test", code_snippet="x = 1",
        svg_icon_path=None, jinja_template=template,
        metadata={}, created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


# Stable UUIDs used throughout the worker tests.
_UUID_FASTAPI = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def template_root(tmp_path: Path) -> Path:
    """A minimal template tree with one Jinja2 file."""
    (tmp_path / "tpl").mkdir()
    (tmp_path / "tpl" / "hello.md.j2").write_text(
        "# {{ component.name }}\n", encoding="utf-8",
    )
    return tmp_path


# ----- LpsSolverWorker --------------------------------------------------

def test_solver_worker_emits_valid_result_for_valid_selection(qapp) -> None:
    model = _make_feature_model()
    worker = LpsSolverWorker(feature_model=model, selection=["root", "comp"])
    finished: list = []
    worker.signals.finished.connect(finished.append)
    worker.run()
    assert len(finished) == 1
    result = finished[0]
    assert result.is_valid is True
    assert "root" in result.model
    assert "comp" in result.model


def test_solver_worker_emits_invalid_for_self_loop(qapp) -> None:
    """Selection with self-loop edge → UNSAT → is_valid=False + conflict.

    The semantic check (in _validate_tree) rejects self-loops at the
    DSL layer, but the solver itself can still handle it: the
    self-loop on EXCLUDES forces ``a == False``, so when the user
    selects ``a``, the solver returns UNSAT. This test exercises the
    solver-level path (no DSL validation in the worker).
    """
    nodes = (
        FeatureNode(id="root", component_id=None, variability="ROOT", label="R"),
        FeatureNode(
            id="a", component_id=None, variability="OPTIONAL", label="A",
        ),
    )
    edges = (
        FeatureEdge(id="e", source="a", target="a", relation="EXCLUDES"),
    )
    now = datetime.now(timezone.utc)
    model = FeatureModel(
        id="m", title="t", description=None, tree_structure_json="{}",
        nodes=nodes, edges=edges, groups=(),
        validation_status="DRAFT", last_solved_at=None,
        created_at=now, updated_at=now,
    )
    worker = LpsSolverWorker(feature_model=model, selection=["root", "a"])
    finished: list = []
    worker.signals.finished.connect(finished.append)
    worker.run()
    assert len(finished) == 1
    result = finished[0]
    assert result.is_valid is False
    # The solver pinpoints the conflicting node.
    assert "a" in result.conflicting


# ----- LpsGeneratorWorker -----------------------------------------------

def test_generator_worker_writes_files(
    qapp, tmp_path: Path, template_root: Path,
) -> None:
    """Successful generation writes the expected files to output_dir."""
    output_dir = tmp_path / "out"
    component = _make_component(_UUID_FASTAPI, "FastAPI Service", "tpl/hello.md.j2")
    components_by_id = {component.id: component}
    template_engine = TemplateEngine(template_root=template_root)
    worker = LpsGeneratorWorker(
        feature_model=_make_feature_model(),
        selection=["root", "comp"],
        components_by_id=components_by_id,
        template_engine=template_engine,
        output_dir=output_dir,
        service=None,
    )
    finished: list = []
    failed: list[str] = []
    progress: list[tuple[int, int, str]] = []
    worker.signals.finished.connect(finished.append)
    worker.signals.failed.connect(failed.append)
    worker.signals.progress.connect(lambda d, t, p: progress.append((d, t, p)))
    worker.run()
    assert failed == []
    assert len(finished) == 1
    result = finished[0]
    assert isinstance(result, GeneratorResult)
    assert result.file_count == 1
    assert result.duration_ms >= 0
    # The file was written.
    written = list(output_dir.rglob("*.md"))
    assert len(written) == 1
    assert "FastAPI Service" in written[0].read_text(encoding="utf-8")


def test_generator_worker_aborts_on_invalid_selection(
    qapp, tmp_path: Path, template_root: Path,
) -> None:
    output_dir = tmp_path / "out"
    worker = LpsGeneratorWorker(
        feature_model=_make_feature_model(),
        selection=[],   # empty → fails the OR/ALTERNATIVE constraint
        components_by_id={},
        template_engine=TemplateEngine(template_root=template_root),
        output_dir=output_dir,
        service=None,
    )
    # Add an ALTERNATIVE group so empty selection fails.
    from app.services.lps_models import FeatureGroup
    worker._model = FeatureModel(
        id="m", title="t", description=None, tree_structure_json="{}",
        nodes=worker._model.nodes,
        edges=(),
        groups=(
            FeatureGroup(id="g", parent="root", kind="ALTERNATIVE",
                         children=("comp",)),
        ),
        validation_status="DRAFT", last_solved_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    failed: list[str] = []
    finished: list = []
    worker.signals.failed.connect(failed.append)
    worker.signals.finished.connect(finished.append)
    worker.run()
    assert finished == []
    assert failed
    assert "inválida" in failed[0].lower() or "inv" in failed[0].lower()


def test_generator_worker_records_run(
    qapp, tmp_path: Path, template_root: Path,
) -> None:
    """The service receives a SUCCESS row when generation completes."""
    db_path = tmp_path / "lps.db"
    service = LpsService(db_path=db_path)
    fm = service.create_feature_model(
        title="t",
        tree_structure={
            "spec_version": "1.0",
            "nodes": [
                {"id": "root", "component_id": None, "variability": "ROOT",
                 "label": "R"},
                {"id": "comp", "component_id": _UUID_FASTAPI,
                 "variability": "MANDATORY", "label": "F"},
            ],
            "edges": [], "groups": [],
        },
    )
    component = _make_component(_UUID_FASTAPI, "FastAPI", "tpl/hello.md.j2")
    service.create_component(
        id=_UUID_FASTAPI, name="FastAPI", category="service",
        jinja_template="tpl/hello.md.j2",
    )
    output_dir = tmp_path / "out"
    worker = LpsGeneratorWorker(
        feature_model=fm,
        selection=["root", "comp"],
        components_by_id={component.id: component},
        template_engine=TemplateEngine(template_root=template_root),
        output_dir=output_dir,
        service=service,
    )
    finished: list = []
    worker.signals.finished.connect(finished.append)
    worker.run()
    assert len(finished) == 1
    runs = service.list_runs(feature_model_id=fm.id)
    assert len(runs) == 1
    assert runs[0].status == "SUCCESS"
    assert runs[0].file_count == 1
