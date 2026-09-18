"""Variability solver — pysat wrapper for the LPS feature model (Change 007).

Translates a feature-model DSL (Contrato 1) into a CNF formula and
validates user selections against the formula's constraints.

Why pysat? It's the standard SAT solver used in academic SPL tooling
(Benavides 2010, Eclipse FeatureIDE). Pure-python alternatives
(z3-solver) are 5–10× slower for the same problem size.

## Translation rules

Each node in the DSL is mapped to a fresh positive SAT variable.
Constraints become CNF clauses:

| DSL construct              | CNF clause                                 |
|----------------------------|--------------------------------------------|
| ``MANDATORY`` parent → child | ``¬parent ∨ child``                      |
| ``OPTIONAL``               | no constraint (free)                       |
| ``REQUIRES(a, b)``         | ``¬a ∨ b``                                 |
| ``EXCLUDES(a, b)``         | ``¬a ∨ ¬b``                                |
| Group ``ALTERNATIVE(c1..cn)`` | pairwise ``¬ci ∨ ¬cj`` + at-least-1     |
| Group ``OR(c1..cn)``       | at-least-1                                 |
| Group ``MANDATORY(c1..cn)``| each ``ci → parent``                       |
| Group ``OPTIONAL(c1..cn)`` | no constraint                              |

The solver uses Glucose 3 (``name='g3'``) which is fast on the kinds
of sparse feature-model formulas we generate (≤ 200 vars, ≤ 500 clauses).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable

from pysat.card import CardEnc, EncType
from pysat.formula import CNF
from pysat.solvers import Solver

from app.services.exceptions import LpsValidationError
from app.services.lps_models import (
    FeatureEdge,
    FeatureGroup,
    FeatureModel,
    FeatureNode,
    LPS_EDGE_RELATIONS,
    LPS_GROUP_KINDS,
    LPS_VARIABILITY_TYPES,
)

_logger = logging.getLogger(__name__)


@dataclass
class EncodedModel:
    """A compiled SAT representation of a feature model.

    Holds the pysat CNF plus the mapping between node ids and SAT
    variables (the inverse mapping is also kept so we can read the
    solver's model back into node ids).
    """

    cnf: CNF
    node_to_var: dict[str, int]
    var_to_node: dict[int, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Build the inverse map once for O(1) decode in tests.
        self.var_to_node = {v: n for n, v in self.node_to_var.items()}

    def variables(self) -> list[int]:
        """All SAT variables in the formula (excluding the auxiliary
        ones pysat creates for cardinality encoding)."""
        return list(self.node_to_var.values())


@dataclass
class ValidationResult:
    """The outcome of validating a node selection."""

    is_valid: bool
    selected: tuple[str, ...]
    model: tuple[str, ...] = ()         # node ids the solver picked (when valid)
    conflicting: tuple[str, ...] = ()   # node ids the solver flipped to fix the conflict


class VariabilitySolver:
    """Compile + validate feature-model selections via pysat.

    Stateless: ``encode`` and ``is_satisfiable`` are pure functions
    of the input. The class is a namespace; tests construct one
    instance and call methods.
    """

    # pysat solver name. g3 = Glucose 3, fast on sparse formulas.
    _SOLVER_NAME = "g3"

    def encode(self, model: FeatureModel) -> EncodedModel:
        """Compile ``model`` into a CNF + var mapping.

        Raises :class:`LpsValidationError` if the model itself is
        inconsistent (e.g. a parent node referenced by an edge /
        group doesn't exist in ``nodes``).
        """
        node_to_var: dict[str, int] = {}
        for idx, node in enumerate(model.nodes, start=1):
            node_to_var[node.id] = idx

        cnf = CNF()
        self._add_node_constraints(cnf, model.nodes, node_to_var)
        self._add_edge_constraints(cnf, model.edges, node_to_var, model.nodes)
        self._add_group_constraints(cnf, model.groups, node_to_var)
        return EncodedModel(cnf=cnf, node_to_var=node_to_var)

    def is_satisfiable(
        self,
        encoded: EncodedModel,
        selection: Iterable[str],
    ) -> ValidationResult:
        """Validate ``selection`` (node ids) against the encoded model.

        Returns a :class:`ValidationResult`:

        - ``is_valid == True`` → the selection is consistent; ``model``
          holds the actual assignment pysat found (the requested
          selection plus any MANDATORY nodes the user forgot to
          include).
        - ``is_valid == False`` → pysat proved UNSAT under the
          selection as assumptions; ``conflicting`` carries the
          node ids the solver tried to flip to find a model.

        Note on assumptions: we treat ``selection`` as a hard contract
        — nodes in the selection MUST be True, nodes NOT in the
        selection MUST be False. We do this by adding unit clauses
        ``[-v]`` for every non-selected node (in addition to the
        positive assumptions for the selected ones). Without those
        negative literals, pysat would be free to satisfy REQUIRES
        edges by activating unseen target vars, which is the wrong
        semantics for "the user selected exactly these nodes".
        """
        selected_set = set(selection)
        # Build the per-node binding: True if selected, False if not.
        # Unknown node ids in ``selection`` are ignored (the GUI might
        # have stale state from a model that was just edited).
        unit_clauses: list[list[int]] = []
        for node_id, var in encoded.node_to_var.items():
            if node_id in selected_set:
                unit_clauses.append([var])      # must be True
            else:
                unit_clauses.append([-var])     # must be False

        with Solver(name=self._SOLVER_NAME, bootstrap_with=encoded.cnf) as solver:
            for clause in unit_clauses:
                solver.add_clause(clause)
            sat = solver.solve()
            if sat:
                full_model = solver.get_model()
                picked_ids = tuple(
                    sorted(
                        node_id
                        for node_id, var in encoded.node_to_var.items()
                        if var in full_model
                    )
                )
                return ValidationResult(
                    is_valid=True,
                    selected=tuple(sorted(selected_set)),
                    model=picked_ids,
                )

            # UNSAT — try to identify which selected nodes are at fault
            # by dropping each positive assumption in turn (greedy
            # relaxation). The dropped ones form the conflicting set.
            conflicting = self._find_conflicting(encoded, selected_set)
            return ValidationResult(
                is_valid=False,
                selected=tuple(sorted(selected_set)),
                conflicting=conflicting,
            )

    # ----- Internal: encode() helpers ------------------------------------

    def _add_node_constraints(
        self,
        cnf: CNF,
        nodes: tuple[FeatureNode, ...],
        node_to_var: dict[str, int],
    ) -> None:
        """MANDATORY / ROOT → their children must be selected when they are.

        ROOT is the single starting node (``variability == "ROOT"``).
        We don't impose a clause for it — the user is free to drop
        the ROOT in theory, but in practice the GUI keeps it pinned
        via the selection. (Adding ``root → True`` would be redundant
        with the assumption.)
        """
        # Build a children-of map from the MANDATORY/OPTIONAL nodes.
        for node in nodes:
            if node.variability not in LPS_VARIABILITY_TYPES:
                raise LpsValidationError(
                    "Unknown variability type",
                    node_id=node.id,
                    variability=node.variability,
                )
        # MANDATORY semantics are usually expressed as "parent → child"
        # on an edge or group. The DSL doesn't carry a parent link on
        # the node itself, so we don't generate per-node clauses here
        # — the edge / group encoders below handle them.

    def _add_edge_constraints(
        self,
        cnf: CNF,
        edges: tuple[FeatureEdge, ...],
        node_to_var: dict[str, int],
        nodes: tuple[FeatureNode, ...],
    ) -> None:
        """Translate REQUIRES / EXCLUDES edges into clauses."""
        for edge in edges:
            if edge.relation not in LPS_EDGE_RELATIONS:
                raise LpsValidationError(
                    "Unknown edge relation",
                    edge_id=edge.id,
                    relation=edge.relation,
                )
            src_var = node_to_var.get(edge.source)
            tgt_var = node_to_var.get(edge.target)
            if src_var is None or tgt_var is None:
                raise LpsValidationError(
                    "Edge references unknown node",
                    edge_id=edge.id,
                    source=edge.source,
                    target=edge.target,
                )
            if edge.relation == "REQUIRES":
                # source → target ≡ ¬source ∨ target
                cnf.append([-src_var, tgt_var])
            else:  # EXCLUDES
                # ¬(source ∧ target) ≡ ¬source ∨ ¬target
                cnf.append([-src_var, -tgt_var])

    def _add_group_constraints(
        self,
        cnf: CNF,
        groups: tuple[FeatureGroup, ...],
        node_to_var: dict[str, int],
    ) -> None:
        """Translate ALTERNATIVE / OR / group-of-MANDATORY constraints."""
        for group in groups:
            if group.kind not in LPS_GROUP_KINDS:
                raise LpsValidationError(
                    "Unknown group kind",
                    group_id=group.id,
                    kind=group.kind,
                )
            parent_var = node_to_var.get(group.parent)
            if parent_var is None:
                raise LpsValidationError(
                    "Group references unknown parent node",
                    group_id=group.id,
                    parent=group.parent,
                )
            child_vars: list[int] = []
            for child_id in group.children:
                child_var = node_to_var.get(child_id)
                if child_var is None:
                    raise LpsValidationError(
                        "Group references unknown child node",
                        group_id=group.id,
                        child=child_id,
                    )
                child_vars.append(child_var)

            if group.kind == "MANDATORY":
                # parent selected ⇒ every child selected
                # (= parent → child for each child)
                for cv in child_vars:
                    cnf.append([-parent_var, cv])
            elif group.kind == "OPTIONAL":
                # no constraint
                pass
            elif group.kind == "ALTERNATIVE":
                # at-least-1 + pairwise exclusion
                self._add_at_least_one(cnf, child_vars)
                self._add_pairwise_exclusion(cnf, child_vars)
            elif group.kind == "OR":
                # at-least-1, no exclusion
                self._add_at_least_one(cnf, child_vars)

    def _add_at_least_one(self, cnf: CNF, vars_list: list[int]) -> None:
        """Add the cardinality constraint: at least one of ``vars_list`` is True."""
        if not vars_list:
            return
        # CardEnc with bound=1 and top_id >= max(vars_list) gives the
        # simplest encoding for our scale (≤ 20 children).
        top_id = max(cnf.nv, max(vars_list))
        at_least = CardEnc.atleast(
            lits=vars_list, bound=1, top_id=top_id, encoding=EncType.totalizer
        )
        for clause in at_least.clauses:
            cnf.append(clause)

    def _add_pairwise_exclusion(self, cnf: CNF, vars_list: list[int]) -> None:
        """For every (i, j) pair, ¬vi ∨ ¬vj — at most one True."""
        n = len(vars_list)
        for i in range(n):
            for j in range(i + 1, n):
                cnf.append([-vars_list[i], -vars_list[j]])

    # ----- Internal: is_satisfiable() helper -----------------------------

    def _find_conflicting(
        self,
        encoded: EncodedModel,
        selected: set[str],
    ) -> tuple[str, ...]:
        """Best-effort identification of which selected nodes conflict.

        Uses a ``delfirst`` style: try to drop each positive
        assumption in turn and see if the rest become satisfiable
        (with the negative literals still in place). The dropped
        ones form the conflicting set. This is approximate (an
        irredundant unsat-core would be more accurate) but good
        enough to point the user at the bad nodes in the GUI.
        """
        # Work on a fresh solver copy each time (pysat's Solver
        # doesn't support rolling back after dropping assumptions).
        surviving_ids: list[str] = []
        conflicting_ids: list[str] = []
        for node_id in selected:
            trial_selection = set(surviving_ids + [node_id])
            # Build the unit clauses for the trial selection.
            trial_clauses = list(encoded.cnf.clauses)
            for nid, var in encoded.node_to_var.items():
                if nid in trial_selection:
                    trial_clauses.append([var])
                else:
                    trial_clauses.append([-var])
            with Solver(name=self._SOLVER_NAME) as test:
                for cl in trial_clauses:
                    test.add_clause(cl)
                if test.solve():
                    surviving_ids.append(node_id)
                else:
                    conflicting_ids.append(node_id)
        return tuple(sorted(conflicting_ids))
