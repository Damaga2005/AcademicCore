"""Top-level F8-B API: `solve_linear_dc`.

Orchestrates: `build_mna_problem` (validate + assemble) -> `solve_exact`
(exact rational Gauss-Jordan) -> node voltages / branch currents / element
powers / conservation checks -> `AnalysisResult` with provenance.

Design choice (documented, not accidental): `build_mna_problem` is the
lower-level diagnostic/audit API (section 36) and raises the typed
exceptions in `mna.errors` eagerly, for callers who want to inspect the
assembled system or handle failures as exceptions. `solve_linear_dc` is the
convenience API and instead catches the *expected, classifiable* subset of
those exceptions (bad domain/topology) and reports them in-band as
`AnalysisResult(status=INVALID|UNSUPPORTED, diagnostics=[...])`, matching
section 15's requirement that INVALID/UNSUPPORTED be first-class result
statuses. `NumericalSolveError` and any unexpected exception are never
caught here — an unexpected failure is surfaced as a real exception, never
silently turned into a fabricated `0` result (section 12).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from fractions import Fraction

from academic_core.domain.engineering.circuit import Circuit
from academic_core.domain.engineering.mna.errors import (
    DimensionalityError,
    FloatingCircuitError,
    InvalidCircuitError,
    MissingReferenceError,
    UnsupportedElementError,
)
from academic_core.domain.engineering.mna.linear import LinearSolveStatus, solve_exact
from academic_core.domain.engineering.mna.problem import MNAProblem, build_mna_problem
from academic_core.domain.engineering.mna.result import (
    AnalysisResult,
    BranchCurrent,
    ConservationChecks,
    ElementPower,
    NodeVoltage,
    SolveStatus,
)
from academic_core.domain.engineering.units import Quantity, parse_unit

SOLVER_VERSION = "f8b-mna/1.0"

# Fraction -> Decimal is a presentation-layer rounding step (spec section 13:
# "redondeo solamente en presentación"). 34 significant digits (~decimal128)
# is documented and scale-independent: it is a digit count, not an absolute
# epsilon, so it does not silently degrade for very large or very small
# component values.
PRESENTATION_PRECISION = 34

_VOLT = parse_unit("V")
_AMP = parse_unit("A")
_WATT = parse_unit("W")

_INVALID_ERRORS = (InvalidCircuitError, MissingReferenceError, FloatingCircuitError, DimensionalityError)


def _fraction_to_decimal(fr: Fraction) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = PRESENTATION_PRECISION
        return Decimal(fr.numerator) / Decimal(fr.denominator)


def _canonical_structure(circuit: Circuit) -> dict:
    return {
        "solver": SOLVER_VERSION,
        "formulation": "MNA: KCL + resistor stamps + ideal voltage-source constraints",
        "tolerance": "0 (exact rational arithmetic)",
        "circuit_name": circuit.name,
        "components": sorted(
            (
                {
                    "ref": c.ref,
                    "type": c.type.upper(),
                    "value_base_units": str(c.value.to_base()) if c.value is not None else None,
                    "pins": dict(sorted(c.pins.items())),
                }
                for c in circuit.components
            ),
            key=lambda d: d["ref"],
        ),
    }


def _digest_for(structure: dict) -> str:
    return hashlib.sha256(json.dumps(structure, sort_keys=True, default=str).encode()).hexdigest()


def _voltage_of(net: str, problem: MNAProblem, solution: tuple) -> Fraction:
    idx = problem.node_index.get(net)
    return Fraction(0) if idx is None else solution[idx]


def _fundamental_cycle_kvl_residual(problem: MNAProblem, solution: tuple) -> Fraction:
    """Max |sum of potential drops| around every fundamental cycle of the
    circuit graph (spanning tree over all nets, via all components as
    edges). General for arbitrary N and topology — not hardcoded to a fixed
    number of loops. See module docstring for why this is, correctly, an
    algebraic identity of a potential-based nodal solve."""
    circuit = problem.circuit
    parent: dict[str, str | None] = {problem.ground: None}
    order = [problem.ground]
    adjacency: dict[str, list[str]] = {net: [] for net in circuit.nets}
    for c in circuit.components:
        pins = list(c.pins.values())
        for a, b in zip(pins, pins[1:]):
            adjacency[a].append(b)
            adjacency[b].append(a)
    tree_edges: set[frozenset] = set()
    i = 0
    while i < len(order):
        cur = order[i]
        i += 1
        for nxt in adjacency[cur]:
            if nxt not in parent:
                parent[nxt] = cur
                tree_edges.add(frozenset((cur, nxt)))
                order.append(nxt)

    def path_to_root(net: str) -> list[str]:
        path = [net]
        while parent[path[-1]] is not None:
            path.append(parent[path[-1]])
        return path

    max_residual = Fraction(0)
    seen_edges: set[frozenset] = set()
    for c in circuit.components:
        pins = list(c.pins.values())
        for a, b in zip(pins, pins[1:]):
            edge = frozenset((a, b))
            if edge in tree_edges or edge in seen_edges or a == b:
                continue
            seen_edges.add(edge)
            pa, pb = path_to_root(a), path_to_root(b)
            set_pb = set(pb)
            lca = next(n for n in pa if n in set_pb)
            loop = pa[: pa.index(lca) + 1] + list(reversed(pb[: pb.index(lca)]))
            loop.append(a)  # close a -> ... -> lca -> ... -> b -> a
            drop = Fraction(0)
            for n1, n2 in zip(loop, loop[1:]):
                drop += _voltage_of(n1, problem, solution) - _voltage_of(n2, problem, solution)
            max_residual = max(max_residual, abs(drop))
    return max_residual


def solve_linear_dc(circuit: Circuit) -> AnalysisResult:
    """Solve a DC linear resistive `Circuit` (R, ideal V, ideal I) via MNA.

    Returns a structured `AnalysisResult`; never raises for a circuit that
    is merely outside F8-B's domain or ill-posed (INVALID/UNSUPPORTED), and
    never fabricates a `SOLVED` result for a singular/inconsistent system.
    """
    try:
        problem = build_mna_problem(circuit)
    except UnsupportedElementError as exc:
        return AnalysisResult(status=SolveStatus.UNSUPPORTED, diagnostics=(str(exc),))
    except _INVALID_ERRORS as exc:
        return AnalysisResult(status=SolveStatus.INVALID, diagnostics=(str(exc),))

    outcome = solve_exact([list(row) for row in problem.matrix], list(problem.rhs))

    system_summary = {
        "n_nodes": len(problem.nodes),
        "n_voltage_sources": len(problem.vsource_refs),
        "n_unknowns": problem.size,
        "reference_node": problem.ground,
    }

    if outcome.status == LinearSolveStatus.SINGULAR:
        return AnalysisResult(
            status=SolveStatus.SINGULAR,
            system_summary=system_summary,
            diagnostics=(
                f"MNA matrix is rank-deficient but consistent (rank "
                f"{outcome.rank} of {problem.size}): infinitely many "
                f"solutions, no unique node-voltage assignment exists",
            ),
        )
    if outcome.status == LinearSolveStatus.INCONSISTENT:
        return AnalysisResult(
            status=SolveStatus.INCONSISTENT,
            system_summary=system_summary,
            diagnostics=(
                "MNA matrix is inconsistent: constraints contradict each "
                "other (e.g. incompatible ideal sources) — no solution exists",
            ),
        )

    solution = outcome.solution

    node_voltages = tuple(
        NodeVoltage(node=n, voltage=Quantity(_fraction_to_decimal(solution[problem.node_index[n]]), _VOLT))
        for n in problem.nodes
    )
    node_voltages += (NodeVoltage(node=problem.ground, voltage=Quantity(Decimal(0), _VOLT)),)

    branch_currents = []
    element_powers = []
    total_power = Fraction(0)
    for c in sorted(problem.circuit.components, key=lambda c: c.ref):
        t = c.type.upper()
        if t == "R":
            v1, v2 = _voltage_of(c.pins["1"], problem, solution), _voltage_of(c.pins["2"], problem, solution)
            g = Fraction(1) / Fraction(c.value.to_base())
            i_branch = (v1 - v2) * g
            convention = "pin1->pin2: I = (V1 - V2) / R"
        elif t == "V":
            v_p, v_m = _voltage_of(c.pins["+"], problem, solution), _voltage_of(c.pins["-"], problem, solution)
            i_branch = solution[problem.vsource_index[c.ref]]
            convention = "+->-: MNA unknown current through the source"
        else:  # I
            v_p, v_m = _voltage_of(c.pins["+"], problem, solution), _voltage_of(c.pins["-"], problem, solution)
            # Is is delivered into the external circuit at "+" (flows "-"
            # through the source to "+"); reported here in the same
            # "+ -> -" through-the-element direction used for every other
            # element, so it is the negative of the delivered value.
            i_branch = -Fraction(c.value.to_base())
            convention = "+->-: through-the-source current (Is is delivered into '+', so I = -Is)"
        if t == "R":
            v_drop = v1 - v2
        else:
            v_drop = v_p - v_m
        power = v_drop * i_branch
        total_power += power
        branch_currents.append(
            BranchCurrent(ref=c.ref, current=Quantity(_fraction_to_decimal(i_branch), _AMP), convention=convention)
        )
        element_powers.append(
            ElementPower(ref=c.ref, power=Quantity(_fraction_to_decimal(power), _WATT), absorbed=power >= 0)
        )

    kcl_residual = Fraction(0)
    for row in range(problem.size):
        val = sum(
            (problem.matrix[row][col] * solution[col] for col in range(problem.size)),
            Fraction(0),
        )
        kcl_residual = max(kcl_residual, abs(val - problem.rhs[row]))
    kvl_residual = _fundamental_cycle_kvl_residual(problem, solution)

    conservation = ConservationChecks(
        kcl_max_residual=str(kcl_residual),
        kvl_max_residual=str(kvl_residual),
        power_balance_residual=str(abs(total_power)),
        tolerance="0 (exact rational arithmetic; no numerical tolerance is needed)",
        passed=(kcl_residual == 0 and kvl_residual == 0 and total_power == 0),
    )

    structure = _canonical_structure(problem.circuit)
    digest = _digest_for(structure)
    provenance = {
        "engine": SOLVER_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "digest": digest,
        "reference_node": problem.ground,
        "formulation": structure["formulation"],
        "tolerance": structure["tolerance"],
        "inputs": [c["ref"] for c in structure["components"]],
    }

    return AnalysisResult(
        status=SolveStatus.SOLVED,
        node_voltages=node_voltages,
        branch_currents=tuple(branch_currents),
        element_powers=tuple(element_powers),
        system_summary=system_summary,
        conservation_checks=conservation,
        provenance=provenance,
    )
