"""Tests for VariabilitySolver — pysat wrapper (Change 007 — Bloco A).

Covers:

- Encoding each individual rule (MANDATORY, REQUIRES, EXCLUDES,
  ALTERNATIVE, OR, group-of-MANDATORY) in isolation.
- Combined models with mixed constraints.
- ``is_satisfiable`` with valid / invalid selections.
- Conflict identification (which nodes the solver flipped).
- Performance baseline: a 20-feature model validates in < 100ms.
"""

from __future__ import annotations

import time

import pytest

from app.services.exceptions import LpsValidationError
from app.services.lps_models import (
    FeatureEdge,
    FeatureGroup,
    FeatureModel,
    FeatureNode,
)
from app.services.variability_solver import VariabilitySolver, ValidationResult


@pytest.fixture
def solver() -> VariabilitySolver:
    return VariabilitySolver()


# ----- Helpers -----------------------------------------------------------

def _make_model(
    nodes: list[FeatureNode],
    edges: list[FeatureEdge] | None = None,
    groups: list[FeatureGroup] | None = None,
) -> FeatureModel:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    return FeatureModel(
        id="m", title="t", description=None, tree_structure_json="{}",
        nodes=tuple(nodes),
        edges=tuple(edges or []),
        groups=tuple(groups or []),
        validation_status="DRAFT",
        last_solved_at=None,
        created_at=now,
        updated_at=now,
    )


def _node(id: str, var: str = "OPTIONAL", label: str | None = None) -> FeatureNode:
    return FeatureNode(
        id=id, component_id=None, variability=var, label=label or id,
    )


# ----- Encoding sanity ---------------------------------------------------

def test_encode_assigns_one_var_per_node(solver: VariabilitySolver) -> None:
    model = _make_model([_node("a"), _node("b"), _node("c")])
    enc = solver.encode(model)
    assert sorted(enc.node_to_var) == ["a", "b", "c"]
    # Vars are 1..N, positive integers.
    assert set(enc.node_to_var.values()) == {1, 2, 3}


def test_encode_empty_model(solver: VariabilitySolver) -> None:
    """No nodes → empty clause set; trivially satisfiable."""
    model = _make_model([])
    enc = solver.encode(model)
    assert enc.node_to_var == {}
    result = solver.is_satisfiable(enc, [])
    assert result.is_valid is True


# ----- MANDATORY edges / groups ------------------------------------------

def test_requires_edge_blocks_selecting_source_without_target(
    solver: VariabilitySolver,
) -> None:
    """a REQUIRES b → selecting only a is invalid."""
    model = _make_model(
        [_node("a"), _node("b")],
        edges=[FeatureEdge(id="e", source="a", target="b", relation="REQUIRES")],
    )
    enc = solver.encode(model)
    bad = solver.is_satisfiable(enc, ["a"])
    assert bad.is_valid is False
    good = solver.is_satisfiable(enc, ["a", "b"])
    assert good.is_valid is True


def test_excludes_edge_blocks_selecting_both(
    solver: VariabilitySolver,
) -> None:
    """a EXCLUDES b → selecting both is invalid."""
    model = _make_model(
        [_node("a"), _node("b")],
        edges=[FeatureEdge(id="e", source="a", target="b", relation="EXCLUDES")],
    )
    enc = solver.encode(model)
    bad = solver.is_satisfiable(enc, ["a", "b"])
    assert bad.is_valid is False
    good = solver.is_satisfiable(enc, ["a"])
    assert good.is_valid is True


def test_alternative_group_blocks_selecting_two_children(
    solver: VariabilitySolver,
) -> None:
    """Group ALTERNATIVE(a, b, c) → at most one selected."""
    model = _make_model(
        [_node("a"), _node("b"), _node("c"), _node("root", "ROOT")],
        groups=[FeatureGroup(
            id="g", parent="root", kind="ALTERNATIVE",
            children=("a", "b", "c"),
        )],
    )
    enc = solver.encode(model)
    # Two children → invalid.
    bad = solver.is_satisfiable(enc, ["root", "a", "b"])
    assert bad.is_valid is False
    # One child + root → valid.
    good = solver.is_satisfiable(enc, ["root", "a"])
    assert good.is_valid is True


def test_or_group_blocks_empty_selection(
    solver: VariabilitySolver,
) -> None:
    """Group OR(a, b) → at least one selected."""
    model = _make_model(
        [_node("a"), _node("b"), _node("root", "ROOT")],
        groups=[FeatureGroup(
            id="g", parent="root", kind="OR",
            children=("a", "b"),
        )],
    )
    enc = solver.encode(model)
    bad = solver.is_satisfiable(enc, ["root"])
    assert bad.is_valid is False
    good = solver.is_satisfiable(enc, ["root", "a"])
    assert good.is_valid is True


def test_or_group_allows_two_children(solver: VariabilitySolver) -> None:
    """Group OR → selecting all children is fine."""
    model = _make_model(
        [_node("a"), _node("b"), _node("root", "ROOT")],
        groups=[FeatureGroup(
            id="g", parent="root", kind="OR",
            children=("a", "b"),
        )],
    )
    enc = solver.encode(model)
    result = solver.is_satisfiable(enc, ["root", "a", "b"])
    assert result.is_valid is True


def test_mandatory_group_requires_children_when_parent_selected(
    solver: VariabilitySolver,
) -> None:
    """Group MANDATORY under root: selecting root requires every child."""
    model = _make_model(
        [_node("a"), _node("b"), _node("root", "ROOT")],
        groups=[FeatureGroup(
            id="g", parent="root", kind="MANDATORY",
            children=("a", "b"),
        )],
    )
    enc = solver.encode(model)
    bad = solver.is_satisfiable(enc, ["root"])
    assert bad.is_valid is False
    good = solver.is_satisfiable(enc, ["root", "a", "b"])
    assert good.is_valid is True


def test_optional_group_imposes_no_constraint(
    solver: VariabilitySolver,
) -> None:
    """Group OPTIONAL → any selection (including empty) is fine."""
    model = _make_model(
        [_node("a"), _node("b"), _node("root", "ROOT")],
        groups=[FeatureGroup(
            id="g", parent="root", kind="OPTIONAL",
            children=("a", "b"),
        )],
    )
    enc = solver.encode(model)
    empty = solver.is_satisfiable(enc, ["root"])
    assert empty.is_valid is True
    both = solver.is_satisfiable(enc, ["root", "a", "b"])
    assert both.is_valid is True


# ----- Combined models --------------------------------------------------

def test_combined_requires_excludes_alternative(
    solver: VariabilitySolver,
) -> None:
    """JWT REQUIRES db; JWT EXCLUDES basic; group ALTERNATIVE(jwt, basic)."""
    model = _make_model(
        [
            _node("root", "ROOT"),
            _node("db", "MANDATORY"),
            _node("jwt"),
            _node("basic"),
        ],
        edges=[
            FeatureEdge(id="e1", source="jwt", target="db", relation="REQUIRES"),
            FeatureEdge(id="e2", source="jwt", target="basic", relation="EXCLUDES"),
        ],
        groups=[FeatureGroup(
            id="g", parent="root", kind="ALTERNATIVE",
            children=("jwt", "basic"),
        )],
    )
    enc = solver.encode(model)
    # JWT alone (with MANDATORY db + root) → valid.
    assert solver.is_satisfiable(enc, ["root", "db", "jwt"]).is_valid is True
    # Basic alone → valid (basic doesn't require db).
    assert solver.is_satisfiable(enc, ["root", "db", "basic"]).is_valid is True
    # JWT + Basic → invalid (EXCLUDES + ALTERNATIVE).
    assert solver.is_satisfiable(enc, ["root", "db", "jwt", "basic"]).is_valid is False
    # JWT without db → invalid (REQUIRES).
    assert solver.is_satisfiable(enc, ["root", "jwt"]).is_valid is False


def test_selected_node_ids_default(solver: VariabilitySolver) -> None:
    """The default selection includes ROOT + every MANDATORY node."""
    model = _make_model([
        _node("root", "ROOT"),
        _node("db", "MANDATORY"),
        _node("jwt"),   # OPTIONAL
        _node("basic"), # OPTIONAL
    ])
    sel = model.selected_node_ids()
    assert "root" in sel
    assert "db" in sel
    # OPTIONAL nodes excluded.
    assert "jwt" not in sel
    assert "basic" not in sel


# ----- Conflict identification -------------------------------------------

def test_conflicting_set_pinpoints_problem_node(
    solver: VariabilitySolver,
) -> None:
    """Invalid selection → ``conflicting`` lists the bad node(s)."""
    model = _make_model(
        [_node("a"), _node("b")],
        edges=[FeatureEdge(id="e", source="a", target="b", relation="EXCLUDES")],
    )
    enc = solver.encode(model)
    bad = solver.is_satisfiable(enc, ["a", "b"])
    assert bad.is_valid is False
    # ``a`` (or ``b``) is the conflicting node — the solver drops
    # one of them to make the formula satisfiable.
    assert bad.conflicting  # non-empty
    # And the conflicting ids are subset of the selection.
    assert set(bad.conflicting) <= {"a", "b"}


# ----- Validation: malformed models -------------------------------------

def test_encode_rejects_unknown_variability(solver: VariabilitySolver) -> None:
    model = _make_model(
        [_node("a", var="BOGUS")],
    )
    with pytest.raises(LpsValidationError):
        solver.encode(model)


def test_encode_rejects_unknown_relation(solver: VariabilitySolver) -> None:
    model = _make_model(
        [_node("a"), _node("b")],
        edges=[FeatureEdge(id="e", source="a", target="b", relation="BOGUS")],
    )
    with pytest.raises(LpsValidationError):
        solver.encode(model)


def test_encode_rejects_edge_to_unknown_node(solver: VariabilitySolver) -> None:
    model = _make_model(
        [_node("a")],
        edges=[FeatureEdge(id="e", source="a", target="ghost", relation="REQUIRES")],
    )
    with pytest.raises(LpsValidationError):
        solver.encode(model)


def test_encode_rejects_group_with_unknown_child(
    solver: VariabilitySolver,
) -> None:
    model = _make_model(
        [_node("root", "ROOT"), _node("a")],
        groups=[FeatureGroup(
            id="g", parent="root", kind="OR",
            children=("a", "ghost"),
        )],
    )
    with pytest.raises(LpsValidationError):
        solver.encode(model)


# ----- Performance baseline ---------------------------------------------

def test_20_features_validate_under_100ms(solver: VariabilitySolver) -> None:
    """AC-04: SAT solver rejects/accepts a 20-feature model in < 100ms."""
    nodes: list[FeatureNode] = [_node(f"n{i}", "OPTIONAL") for i in range(20)]
    # Add some inter-feature constraints to make the formula non-trivial.
    edges: list[FeatureEdge] = []
    for i in range(0, 19, 2):
        edges.append(
            FeatureEdge(
                id=f"e{i}", source=f"n{i}", target=f"n{i+1}", relation="REQUIRES",
            )
        )
    model = _make_model(nodes, edges=edges)
    enc = solver.encode(model)
    start = time.perf_counter()
    # Run a few selections to amortize the solver's bootstrap cost.
    for _ in range(10):
        solver.is_satisfiable(enc, [f"n{i}" for i in range(0, 20, 2)])
    elapsed_ms = (time.perf_counter() - start) * 1000 / 10
    assert elapsed_ms < 100, f"average validation took {elapsed_ms:.1f}ms"
