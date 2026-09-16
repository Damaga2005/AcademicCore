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
from academic_core.domain.engineering.mna.dependent import (
    DEPENDENT_TYPES,
    describe_dependents,
)
from academic_core.domain.engineering.mna.errors import (
    CircularControlError,
    DimensionalityError,
    FloatingCircuitError,
    InvalidCircuitError,
    MissingReferenceError,
    NumericalSolveError,
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
# "redondeo solamente en presentación"). This MUST match Python's ambient
# Decimal context precision (`decimal.getcontext().prec`, default 28) rather
# than exceed it: an earlier version used 34 (~decimal128), which looked more
# precise but was a false promise — the moment any caller does ordinary
# Decimal arithmetic on the result under the ambient (28-digit) context, e.g.
# `Quantity.to_base()`'s `self.value * self.unit.factor` (F6, unmodified),
# Python silently re-rounds to 28 digits anyway. Found during the F8-B
# independent audit via `test_independent_reference_*`, which compare against
# a value rounded once, correctly, at construction — not rounded again,
# invisibly, on first use. 28 is a digit count, not an absolute epsilon, so
# it does not silently degrade for very large or very small component values.
PRESENTATION_PRECISION = 28

_VOLT = parse_unit("V")
_AMP = parse_unit("A")
_WATT = parse_unit("W")

_INVALID_ERRORS = (InvalidCircuitError, MissingReferenceError, FloatingCircuitError, DimensionalityError,
                   CircularControlError)


def _fraction_to_decimal(fr: Fraction) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = PRESENTATION_PRECISION
        return Decimal(fr.numerator) / Decimal(fr.denominator)


def _canonical_structure(circuit: Circuit) -> dict:
    entries = []
    for c in circuit.components:
        entry = {
            "ref": c.ref,
            "type": c.type.upper(),
            "value_base_units": str(c.value.to_base()) if c.value is not None else None,
            "pins": dict(sorted(c.pins.items())),
        }
        if c.type.upper() in DEPENDENT_TYPES:
            # Control identity is physics identity: covered by the digest.
            # RVI components carry no such entry, so certified digests
            # are byte-identical.
            entry["control"] = {
                k: str(v) for k, v in sorted(
                    dict(c.parameters or {}).items(), key=lambda kv: kv[0])
            }
        entries.append(entry)
    return {
        "solver": SOLVER_VERSION,
        "formulation": "MNA: KCL + resistor stamps + ideal voltage-source constraints",
        "tolerance": "0 (exact rational arithmetic)",
        "circuit_name": circuit.name,
        "components": sorted(entries, key=lambda d: d["ref"]),
    }


def _digest_for(structure: dict) -> str:
    return hashlib.sha256(json.dumps(structure, sort_keys=True, default=str).encode()).hexdigest()


def _voltage_of(net: str, problem: MNAProblem, solution: tuple) -> Fraction:
    idx = problem.node_index.get(net)
    return Fraction(0) if idx is None else solution[idx]


def fundamental_cycle_chords(circuit: Circuit, ground: str) -> list[tuple[str, str, list[str]]]:
    """Pure graph computation (no solved values, independently unit-testable):
    a spanning tree of the circuit's net graph rooted at `ground`, and for
    every non-tree ("chord") edge, the closed loop it forms with the tree.

    Returns one `(a, b, loop)` entry per chord, `loop` being the node
    sequence `a -> ... -> lca -> ... -> b -> a`. The number of chords
    returned equals the graph's cyclomatic number `E - V + 1` for a
    connected graph — this is what `test_kvl_...` checks to guarantee no
    independent loop is silently dropped.

    The circuit is a MULTIGRAPH: two components can share the same pair of
    nets (e.g. resistors in parallel). Edges are therefore identified by
    component position, never by the `{net_a, net_b}` pair — an earlier
    version deduplicated by node-pair and silently dropped every parallel
    component beyond the first as "already covered", undercounting the
    independent-cycle basis for any circuit with a parallel branch (found
    during the F8-B independent audit; see
    `test_kvl_covers_parallel_multi_edge_loops`).
    """
    edges: list[tuple[str, str]] = []
    adjacency: dict[str, list[tuple[str, int]]] = {net: [] for net in circuit.nets}
    for c in circuit.components:
        pins = list(c.pins.values())
        for a, b in zip(pins, pins[1:]):
            if a == b:
                continue  # a self-loop's drop is v(a)-v(a) == 0 identically
            eid = len(edges)
            edges.append((a, b))
            adjacency[a].append((b, eid))
            adjacency[b].append((a, eid))

    parent: dict[str, str | None] = {ground: None}
    order = [ground]
    tree_edge_ids: set[int] = set()
    i = 0
    while i < len(order):
        cur = order[i]
        i += 1
        for nxt, eid in adjacency[cur]:
            if nxt not in parent:
                parent[nxt] = cur
                tree_edge_ids.add(eid)
                order.append(nxt)

    def path_to_root(net: str) -> list[str]:
        path = [net]
        while parent[path[-1]] is not None:
            path.append(parent[path[-1]])
        return path

    chords = []
    for eid, (a, b) in enumerate(edges):
        if eid in tree_edge_ids:
            continue
        pa, pb = path_to_root(a), path_to_root(b)
        set_pb = set(pb)
        lca = next(n for n in pa if n in set_pb)
        loop = pa[: pa.index(lca) + 1] + list(reversed(pb[: pb.index(lca)]))
        loop.append(a)  # close a -> ... -> lca -> ... -> b -> a
        chords.append((a, b, loop))
    return chords


def _fundamental_cycle_kvl_residual(problem: MNAProblem, solution: tuple) -> Fraction:
    """Max |sum of potential drops| around every fundamental cycle of the
    circuit graph. General for arbitrary N and topology — not hardcoded to
    a fixed number of loops. See module docstring for why this is,
    correctly, an algebraic identity of a potential-based nodal solve."""
    max_residual = Fraction(0)
    for _a, _b, loop in fundamental_cycle_chords(problem.circuit, problem.ground):
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
    dep_graph = describe_dependents(problem.circuit)
    if dep_graph.entries:
        # F8-E provenance (conditional: RVI summaries byte-identical).
        system_summary["dependent_sources"] = dep_graph.to_dict()
        system_summary["dependent_digest"] = dep_graph.digest
    opamps = sorted(
        ({"ref": c.ref, "in_p": c.pins["+"], "in_n": c.pins["-"],
          "out": c.pins["o"]}
         for c in problem.circuit.components if c.type.upper() == "O"),
        key=lambda d: d["ref"],
    )
    if opamps:
        # F8-F provenance (conditional: summaries without O byte-identical).
        # The ideal op-amp is pins-only (no value/parameters); full
        # identity is these three nets.
        system_summary["ideal_opamps"] = opamps
    xfmrs = sorted(
        ({"ref": c.ref, "p1": c.pins["1"], "p2": c.pins["2"],
          "s1": c.pins["3"], "s2": c.pins["4"],
          "n": str(c.value.to_base())}
         for c in problem.circuit.components if c.type.upper() == "T"),
        key=lambda d: d["ref"],
    )
    if xfmrs:
        # F8-G provenance (conditional: summaries without T byte-identical).
        # Identity is four nets plus the turns ratio from the digest.
        system_summary["ideal_transformers"] = xfmrs

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
    exact_branch_currents: dict[str, Fraction] = {}
    by_ref = {c.ref.upper(): c for c in problem.circuit.components}

    def _node_v(net: str) -> Fraction:
        return _voltage_of(net, problem, solution)

    control_memo: dict[str, Fraction] = {}

    def _eval_control(ref_upper: str, active: tuple[str, ...] = ()) -> Fraction:
        """Reconstructed branch current (F8-B orientation conventions).

        Cycles are excluded at problem build; the active set below is
        defense in depth.
        """
        if ref_upper in control_memo:
            return control_memo[ref_upper]
        if ref_upper in active:
            raise CircularControlError(
                f"circular current control involving {ref_upper}")
        c = by_ref[ref_upper]
        t = c.type.upper()
        if t in ("V", "E", "H"):
            value = solution[problem.vsource_index[c.ref]]
        elif t == "O":
            # Reconstructed output-leg current (out -> ground): -i_o.
            value = -solution[problem.vsource_index[c.ref]]
        elif t == "R":
            value = (_node_v(c.pins["1"]) - _node_v(c.pins["2"]))
            value = value * Fraction(1) / Fraction(c.value.to_base())
        elif t == "I":
            value = -Fraction(c.value.to_base())
        elif t == "G":
            gm = Fraction(c.value.to_base())
            value = -(gm * (_node_v(c.parameters["cp"]) - _node_v(c.parameters["cn"])))
        elif t == "F":
            beta = Fraction(c.value.to_base())
            value = -(beta * _eval_control(
                str(c.parameters["control_ref"]).upper(), active + (ref_upper,)))
        else:
            raise UnsupportedElementError(
                f"{c.ref}: type {t!r} cannot carry control current")
        control_memo[ref_upper] = value
        return value

    for c in sorted(problem.circuit.components, key=lambda c: c.ref):
        t = c.type.upper()
        if t == "R":
            v1, v2 = _voltage_of(c.pins["1"], problem, solution), _voltage_of(c.pins["2"], problem, solution)
            g = Fraction(1) / Fraction(c.value.to_base())
            i_branch = (v1 - v2) * g
            convention = "pin1->pin2: I = (V1 - V2) / R"
        elif t in ("V", "E", "H"):
            v_p, v_m = _voltage_of(c.pins["+"], problem, solution), _voltage_of(c.pins["-"], problem, solution)
            i_branch = solution[problem.vsource_index[c.ref]]
            convention = "+->-: MNA unknown current through the source"
        elif t == "G":
            v_p, v_m = _voltage_of(c.pins["+"], problem, solution), _voltage_of(c.pins["-"], problem, solution)
            # Same convention as independent I (delivered into "+"):
            # reported +->- current is the negative of the delivered J.
            i_branch = _eval_control(c.ref.upper())
            convention = "+->-: dependent output current (delivered into '+', so I = -J)"
        elif t == "F":
            v_p, v_m = _voltage_of(c.pins["+"], problem, solution), _voltage_of(c.pins["-"], problem, solution)
            i_branch = _eval_control(c.ref.upper())
            convention = "+->-: dependent output current (delivered into '+', so I = -J)"
        elif t == "O":
            # Ideal op-amp output leg (out -> ground return): the aux
            # unknown i_o is delivered INTO "o", so the leg current
            # leaving "o" is -i_o. Absorbed power P = Vout * (-i_o).
            v_out = _voltage_of(c.pins["o"], problem, solution)
            i_o = solution[problem.vsource_index[c.ref]]
            v_p, v_m = v_out, Fraction(0)
            v_drop = v_out
            i_branch = -i_o
            convention = "o->gnd (op-amp output leg; reported = -i_o)"
        elif t == "T":
            # Ideal transformer: two physical winding legs, reported
            # 1->2 (primary) and 3->4 (secondary) straight from the aux
            # unknowns. Absorbed power per leg sums to exactly zero for
            # the ideal device (V1·I1 + V2·I2 = 0 by the constraints).
            v1 = _voltage_of(c.pins["1"], problem, solution) - _voltage_of(c.pins["2"], problem, solution)
            v2 = _voltage_of(c.pins["3"], problem, solution) - _voltage_of(c.pins["4"], problem, solution)
            i1 = solution[problem.vsource_index[f"{c.ref}:1"]]
            i2 = solution[problem.vsource_index[f"{c.ref}:2"]]
            for leg, vv, ii in (("1", v1, i1), ("2", v2, i2)):
                pw = vv * ii
                total_power += pw
                exact_branch_currents[f"{c.ref}:{leg}"] = ii
                branch_currents.append(
                    BranchCurrent(ref=f"{c.ref}:{leg}", current=Quantity(_fraction_to_decimal(ii), _AMP),
                                  convention=f"winding {leg} (1->2 primary, 3->4 secondary): aux current"))
                element_powers.append(
                    ElementPower(ref=f"{c.ref}:{leg}", power=Quantity(_fraction_to_decimal(pw), _WATT),
                                 absorbed=pw >= 0))
            continue
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
        exact_branch_currents[c.ref] = i_branch
        branch_currents.append(
            BranchCurrent(ref=c.ref, current=Quantity(_fraction_to_decimal(i_branch), _AMP), convention=convention)
        )
        element_powers.append(
            ElementPower(ref=c.ref, power=Quantity(_fraction_to_decimal(power), _WATT), absorbed=power >= 0)
        )

    # Physical KCL validation: for every net in the circuit (including the
    # reference/ground node, which is omitted from the MNA matrix), sum the
    # actual branch currents leaving the node through every connected pin.
    # Avoids circular re-evaluation of the linear system equations A x - z = 0.
    pin_pairs = {"R": ("1", "2"), "V": ("+", "-"), "I": ("+", "-"),
                 "E": ("+", "-"), "G": ("+", "-"), "H": ("+", "-"), "F": ("+", "-")}
    net_kcl: dict[str, Fraction] = {net: Fraction(0) for net in problem.circuit.nets}
    for c in problem.circuit.components:
        if c.type.upper() == "O":
            ib = exact_branch_currents[c.ref]
            # Output leg (o -> ground return): leaving "o" is ib (=-i_o);
            # the return enters ground. Inputs draw nothing (no entries).
            net_kcl[c.pins["o"]] += ib
            net_kcl[problem.ground] -= ib
            continue
        if c.type.upper() == "T":
            # Two winding legs: 1->2 carries i1, 3->4 carries i2.
            i1 = exact_branch_currents[f"{c.ref}:1"]
            i2 = exact_branch_currents[f"{c.ref}:2"]
            net_kcl[c.pins["1"]] += i1
            net_kcl[c.pins["2"]] -= i1
            net_kcl[c.pins["3"]] += i2
            net_kcl[c.pins["4"]] -= i2
            continue
        ib = exact_branch_currents[c.ref]
        p1, p2 = pin_pairs[c.type.upper()]
        net_kcl[c.pins[p1]] += ib
        net_kcl[c.pins[p2]] -= ib
    kcl_residual = max((abs(resid) for resid in net_kcl.values()), default=Fraction(0))
    kvl_residual = _fundamental_cycle_kvl_residual(problem, solution)

    passed = kcl_residual == 0 and kvl_residual == 0 and total_power == 0
    if not passed:
        # Given exact rational arithmetic, a UNIQUE solve mathematically
        # guarantees KCL/KVL/power-balance residuals of exactly zero (see
        # module docstring); a nonzero residual here cannot correspond to a
        # genuinely solved physical circuit; it can only mean an internal
        # defect in this solver. Never report SOLVED with a failing
        # conservation check silently (spec section 30) — surface it as a
        # hard failure instead of a contradictory result.
        raise NumericalSolveError(
            f"internal solver defect: UNIQUE solve produced nonzero "
            f"conservation residuals (kcl={kcl_residual}, kvl={kvl_residual}, "
            f"power={total_power}) for circuit {problem.circuit.name!r}"
        )

    conservation = ConservationChecks(
        kcl_max_residual=str(kcl_residual),
        kvl_max_residual=str(kvl_residual),
        power_balance_residual=str(abs(total_power)),
        tolerance="0 (exact rational arithmetic; no numerical tolerance is needed)",
        passed=True,
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
