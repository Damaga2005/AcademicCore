"""F8-B: General Linear Circuit Solver (MNA) test suite.

Covers: matrix assembly/stamping per element, generality across N and
topology (series/parallel/ladder/bridge/arbitrary graph, N in
{1,2,3,4,8,16,32} where applicable), multiple sources, branch
currents/power, KCL/KVL/power-balance validation, determinism, permutation
and node-renaming invariance, scaling metamorphic invariants, adversarial/
degenerate circuits (singular, inconsistent, floating, no-reference,
unsupported element, invalid parameter), ngspice cross-validation, and
security (no eval/exec/subprocess in the solver).
"""

from __future__ import annotations

import ast
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.mna import (
    DimensionalityError,
    FloatingCircuitError,
    InvalidCircuitError,
    MissingReferenceError,
    SolveStatus,
    UnsupportedElementError,
    build_mna_problem,
    solve_linear_dc,
)
from academic_core.domain.engineering.mna.linear import LinearSolveStatus, solve_exact
from academic_core.domain.engineering.units import parse_quantity

try:
    from academic_core.infrastructure.ngspice import NgSpiceBackend

    _NGSPICE = NgSpiceBackend()
    _NGSPICE_AVAILABLE = _NGSPICE.detect().available
except Exception:  # pragma: no cover - environment without ngspice at all
    _NGSPICE_AVAILABLE = False


# ==============================================================================
# Helpers
# ==============================================================================
def r(ref, value, n1, n2):
    return Component(ref, "R", parse_quantity(value), {"1": n1, "2": n2})


def v(ref, value, np_, nm):
    return Component(ref, "V", parse_quantity(value), {"+": np_, "-": nm})


def isrc(ref, value, np_, nm):
    return Component(ref, "I", parse_quantity(value), {"+": np_, "-": nm})


def build(name, comps):
    c = Circuit(name=name)
    for comp in comps:
        c.add(comp)
    return c


def series_circuit(n, r_ohm="1000 ohm", vs="10 V"):
    """V1 -- R1 -- n1 -- R2 -- n2 -- ... -- Rn -- 0."""
    nodes = ["n0"] + [f"n{i}" for i in range(1, n)] + ["0"]
    comps = [v("V1", vs, "n0", "0")]
    for i in range(n):
        comps.append(r(f"R{i + 1}", r_ohm, nodes[i], nodes[i + 1]))
    return build(f"series{n}", comps)


def parallel_circuit(n, r_ohm="1000 ohm", vs="10 V"):
    comps = [v("V1", vs, "n1", "0")]
    for i in range(n):
        comps.append(r(f"R{i + 1}", r_ohm, "n1", "0"))
    return build(f"parallel{n}", comps)


def ladder_circuit(n, r_ohm="1000 ohm", vs="10 V"):
    """N stages of series R then shunt R to ground (classic R-2R-style ladder,
    without requiring the 2x ratio). Component refs are R<k> — the ref regex
    only allows a single type letter, so stages are numbered sequentially."""
    comps = [v("V1", vs, "a0", "0")]
    prev = "a0"
    k = 1
    for i in range(n):
        mid = f"s{i}"
        nxt = f"a{i + 1}"
        comps.append(r(f"R{k}", r_ohm, prev, mid))
        k += 1
        comps.append(r(f"R{k}", r_ohm, mid, "0"))
        k += 1
        comps.append(r(f"R{k}", r_ohm, mid, nxt))
        k += 1
        prev = nxt
    comps.append(r(f"R{k}", r_ohm, prev, "0"))
    return build(f"ladder{n}", comps)


def bridge_circuit(r1="100 ohm", r2="200 ohm", r3="300 ohm", r4="400 ohm", r5="500 ohm", vs="10 V"):
    return build(
        "bridge",
        [
            v("V1", vs, "n1", "0"),
            r("R1", r1, "n1", "n2"),
            r("R2", r2, "n1", "n3"),
            r("R3", r3, "n2", "0"),
            r("R4", r4, "n3", "0"),
            r("R5", r5, "n2", "n3"),
        ],
    )


def assert_solved(res):
    assert res.status == SolveStatus.SOLVED, res.diagnostics
    assert res.conservation_checks.passed
    assert res.conservation_checks.kcl_max_residual == "0"
    assert res.conservation_checks.kvl_max_residual == "0"
    assert res.conservation_checks.power_balance_residual == "0"
    return res


def voltage_map(res):
    return {nv.node: nv.voltage.to_base() for nv in res.node_voltages}


def current_map(res):
    return {bc.ref: bc.current.to_base() for bc in res.branch_currents}


def power_map(res):
    return {ep.ref: ep.power.to_base() for ep in res.element_powers}


def exact_node_voltages(circuit):
    """Exact `Fraction` node voltages, bypassing the solver's presentation-
    layer Decimal rounding (needed for circuits whose exact values are
    non-terminating decimals, e.g. a bridge with a factor of 3 in a
    denominator — rounding two independently-computed 34-digit decimals and
    comparing them is not a fair equality test; the underlying rational
    arithmetic is what's exact, and is exercised directly here)."""
    problem = build_mna_problem(circuit)
    outcome = solve_exact([list(row) for row in problem.matrix], list(problem.rhs))
    assert outcome.status == LinearSolveStatus.UNIQUE
    volts = {n: outcome.solution[problem.node_index[n]] for n in problem.nodes}
    volts[problem.ground] = Fraction(0)
    return problem, outcome, volts


def exact_branch_currents(circuit):
    """Exact `Fraction` branch currents, same sign conventions as
    `mna.solver.solve_linear_dc` (see its docstring), computed independently
    here so scaling/equivalence invariants can be checked without
    presentation-layer Decimal rounding."""
    problem, outcome, volts = exact_node_voltages(circuit)
    currents = {}
    for c in problem.circuit.components:
        t = c.type.upper()
        if t == "R":
            v1, v2 = volts[c.pins["1"]], volts[c.pins["2"]]
            g = Fraction(1) / Fraction(c.value.to_base())
            currents[c.ref] = (v1 - v2) * g
        elif t == "V":
            currents[c.ref] = outcome.solution[problem.vsource_index[c.ref]]
        else:  # I
            currents[c.ref] = -Fraction(c.value.to_base())
    return currents


# ==============================================================================
# 1. MNA assembly / stamping
# ==============================================================================
def test_mna_assembly_single_resistor_divider_sizes():
    problem = build_mna_problem(series_circuit(2))
    assert len(problem.nodes) == 2  # n0, n1 (0 excluded)
    assert len(problem.vsource_refs) == 1
    assert problem.size == 3


def test_resistor_stamping_symmetry():
    problem = build_mna_problem(series_circuit(1))
    # single resistor n0 -- R1 -- 0, V1 n0..0: matrix rows are [n0, V1-current]
    g = Fraction(1) / Fraction(1000)
    assert problem.matrix[problem.node_index["n0"]][problem.node_index["n0"]] == g


def test_voltage_source_stamping_symmetric_placement():
    problem = build_mna_problem(series_circuit(1))
    k = problem.vsource_index["V1"]
    n0 = problem.node_index["n0"]
    assert problem.matrix[n0][k] == 1
    assert problem.matrix[k][n0] == 1
    assert problem.rhs[k] == Fraction(10)


def test_current_source_stamping_into_rhs():
    c = build("isrc", [isrc("I1", "2 A", "n1", "0"), r("R1", "500 ohm", "n1", "0")])
    problem = build_mna_problem(c)
    assert problem.rhs[problem.node_index["n1"]] == Fraction(2)


def test_ground_reference_accepts_0_and_gnd_case_insensitive():
    for gnd in ("0", "GND", "gnd", "Gnd"):
        c = build("g", [v("V1", "5 V", "n1", gnd), r("R1", "1 kohm", "n1", gnd)])
        problem = build_mna_problem(c)
        assert problem.ground == gnd


# ==============================================================================
# 2. Single resistor / series / parallel / ladder — parametric generality
# ==============================================================================
def test_single_resistor():
    res = assert_solved(solve_linear_dc(series_circuit(1, "1 kohm", "10 V")))
    assert voltage_map(res)["n0"] == Decimal("10")
    assert current_map(res)["R1"] == Decimal("0.01")


@pytest.mark.parametrize("n", [1, 2, 3, 4, 8, 16, 32])
def test_series(n):
    res = assert_solved(solve_linear_dc(series_circuit(n, "1000 ohm", "10 V")))
    # equal series resistors -> equal current everywhere = V / (n*R)
    expected_i = Decimal(10) / (n * Decimal(1000))
    for ref, i_val in current_map(res).items():
        if ref.startswith("R"):
            assert i_val == expected_i


@pytest.mark.parametrize("n", [1, 2, 3, 4, 8, 16, 32])
def test_parallel(n):
    res = assert_solved(solve_linear_dc(parallel_circuit(n, "1000 ohm", "10 V")))
    volts = voltage_map(res)
    assert volts["n1"] == Decimal("10")
    total_i = sum(v_ for k, v_ in current_map(res).items() if k.startswith("R"))
    # Req = R/n -> total current = 10 / (1000/n) = 10*n/1000
    assert total_i == Decimal(10) * n / Decimal(1000)


@pytest.mark.parametrize("n", [1, 2, 3, 4, 8, 16])
def test_ladder(n):
    res = assert_solved(solve_linear_dc(ladder_circuit(n, "1000 ohm", "10 V")))
    assert res.status == SolveStatus.SOLVED


def test_arbitrary_graph_bridge_is_not_series_parallel_reducible_but_solves():
    # A bridge with R5 connecting the two mid-nodes cannot be reduced by
    # series/parallel combination alone; the general MNA solve must still
    # produce a unique, physically consistent solution (verified exactly
    # against an independent hand-derivation in the next test, and against
    # ngspice further below).
    res = assert_solved(solve_linear_dc(bridge_circuit()))
    assert len(res.node_voltages) == 4  # n1, n2, n3, and the reference node 0


def test_bridge_unbalanced_exact_value():
    assert_solved(solve_linear_dc(bridge_circuit()))  # status/conservation still checked end-to-end
    _, _, volts = exact_node_voltages(bridge_circuit())
    # Solve independently by hand-substitution using Fraction to avoid
    # depending on the solver under test for the expected value.
    # Node equations (G in mho): n2: (n2-10)/100 + (n2-0)/300 + (n2-n3)/500 = 0
    #                            n3: (n3-10)/200 + (n3-0)/400 + (n3-n2)/500 = 0
    from fractions import Fraction as F

    g12, g13, g20, g30, g23 = F(1, 100), F(1, 200), F(1, 300), F(1, 400), F(1, 500)
    # matrix for [n2, n3]
    a11 = g12 + g20 + g23
    a12 = -g23
    a21 = -g23
    a22 = g13 + g30 + g23
    z1 = g12 * 10
    z2 = g13 * 10
    det = a11 * a22 - a12 * a21
    n2 = (z1 * a22 - a12 * z2) / det
    n3 = (a11 * z2 - a21 * z1) / det
    assert volts["n2"] == n2
    assert volts["n3"] == n3


def test_bridge_balanced_zero_across_galvanometer():
    # balanced bridge: R1/R3 == R2/R4 -> no current through R5
    res = assert_solved(
        solve_linear_dc(bridge_circuit(r1="100 ohm", r2="200 ohm", r3="200 ohm", r4="400 ohm", r5="1 kohm"))
    )
    currents = current_map(res)
    assert currents["R5"] == Decimal("0")


# ==============================================================================
# 3. Multiple sources / mixed sources
# ==============================================================================
def test_multiple_voltage_sources_series_aiding():
    c = build(
        "mvs",
        [
            v("V1", "5 V", "n1", "0"),
            v("V2", "5 V", "n2", "n1"),
            r("R1", "1 kohm", "n2", "0"),
        ],
    )
    res = assert_solved(solve_linear_dc(c))
    assert voltage_map(res)["n2"] == Decimal("10")


def test_multiple_current_sources_superposition():
    c = build(
        "mis",
        [
            isrc("I1", "1 A", "n1", "0"),
            isrc("I2", "2 A", "n1", "0"),
            r("R1", "10 ohm", "n1", "0"),
        ],
    )
    res = assert_solved(solve_linear_dc(c))
    assert voltage_map(res)["n1"] == Decimal("30")


def test_mixed_sources():
    c = build(
        "mixed",
        [
            v("V1", "12 V", "n1", "0"),
            r("R1", "100 ohm", "n1", "n2"),
            isrc("I1", "0.01 A", "n2", "0"),
            r("R2", "200 ohm", "n2", "0"),
        ],
    )
    res = assert_solved(solve_linear_dc(c))
    assert res.status == SolveStatus.SOLVED


# ==============================================================================
# 4. Branch currents / power
# ==============================================================================
def test_branch_currents_sign_convention_source_delivers():
    res = assert_solved(solve_linear_dc(series_circuit(1, "1 kohm", "10 V")))
    powers = power_map(res)
    assert powers["V1"] < 0  # delivering power
    assert powers["R1"] > 0  # absorbing power


def test_power_conservation_multi_source():
    # The presentation layer rounds each power to 34 significant digits
    # independently, so re-summing *rounded* Decimals is not guaranteed to
    # cancel exactly for a non-terminating fraction (bridge has a factor of
    # 3 in a denominator); `conservation_checks.passed` is the authoritative
    # check and is computed from the exact Fraction solution pre-rounding.
    res = assert_solved(solve_linear_dc(bridge_circuit()))
    assert res.conservation_checks.power_balance_residual == "0"


# ==============================================================================
# 5. KCL / KVL
# ==============================================================================
@pytest.mark.parametrize("n", [2, 8, 32])
def test_kcl_residual_zero_for_arbitrary_n(n):
    res = assert_solved(solve_linear_dc(parallel_circuit(n)))
    assert res.conservation_checks.kcl_max_residual == "0"


def test_kvl_residual_zero_on_bridge():
    res = assert_solved(solve_linear_dc(bridge_circuit()))
    assert res.conservation_checks.kvl_max_residual == "0"


# ==============================================================================
# 6. Singular / inconsistent / floating / degenerate
# ==============================================================================
def test_singular_redundant_consistent_voltage_sources():
    # two identical ideal V sources in parallel: consistent but redundant
    c = build("redundant", [v("V1", "10 V", "n1", "0"), v("V2", "10 V", "n1", "0"), r("R1", "1 kohm", "n1", "0")])
    res = solve_linear_dc(c)
    assert res.status == SolveStatus.SINGULAR


def test_inconsistent_incompatible_parallel_voltage_sources():
    c = build("incompatible", [v("V1", "10 V", "n1", "0"), v("V2", "20 V", "n1", "0")])
    res = solve_linear_dc(c)
    assert res.status == SolveStatus.INCONSISTENT


def test_floating_disconnected_island():
    c = build(
        "island",
        [v("V1", "5 V", "n1", "0"), r("R1", "1 kohm", "n1", "0"), r("R2", "1 kohm", "x1", "x2")],
    )
    res = solve_linear_dc(c)
    assert res.status == SolveStatus.INVALID
    assert "x1" in res.diagnostics[0] or "x2" in res.diagnostics[0]


def test_missing_reference_node():
    c = build("noref", [r("R1", "1 kohm", "a", "b")])
    res = solve_linear_dc(c)
    assert res.status == SolveStatus.INVALID


def test_ambiguous_reference_nodes():
    c = Circuit(name="ambiguous")
    c.add(v("V1", "5 V", "n1", "0"))
    c.add(r("R1", "1 kohm", "n1", "GND"))  # a second, distinct net also matching GND convention
    res = solve_linear_dc(c)
    assert res.status == SolveStatus.INVALID


def test_empty_circuit_invalid():
    res = solve_linear_dc(Circuit(name="empty"))
    assert res.status == SolveStatus.INVALID


def test_unsupported_component_diode():
    c = Circuit(name="diode")
    c.add(Component("D1", "D", None, {"A": "n1", "K": "0"}))
    res = solve_linear_dc(c)
    assert res.status == SolveStatus.UNSUPPORTED


def test_negative_resistance_rejected():
    c = build("negr", [r("R1", "-5 ohm", "n1", "0"), v("V1", "1 V", "n1", "0")])
    assert solve_linear_dc(c).status == SolveStatus.INVALID


def test_zero_resistance_rejected():
    c = build("zeror", [r("R1", "0 ohm", "n1", "0"), v("V1", "1 V", "n1", "0")])
    assert solve_linear_dc(c).status == SolveStatus.INVALID


def test_wrong_dimension_value_raises_at_build():
    c = Circuit(name="dim")
    c.add(Component("R1", "R", parse_quantity("5 V"), {"1": "n1", "2": "0"}))
    with pytest.raises(DimensionalityError):
        build_mna_problem(c)


def test_missing_value_raises_at_build():
    c = Circuit(name="missing")
    c.add(Component("R1", "R", None, {"1": "n1", "2": "0"}))
    with pytest.raises(InvalidCircuitError):
        build_mna_problem(c)


def test_unsupported_raises_at_build_mna_problem_level():
    c = Circuit(name="d")
    c.add(Component("D1", "D", None, {"A": "n1", "K": "0"}))
    with pytest.raises(UnsupportedElementError):
        build_mna_problem(c)


def test_no_reference_raises_at_build_mna_problem_level():
    c = build("noref2", [r("R1", "1 kohm", "a", "b")])
    with pytest.raises(MissingReferenceError):
        build_mna_problem(c)


def test_floating_raises_at_build_mna_problem_level():
    c = build("float2", [v("V1", "5 V", "n1", "0"), r("R2", "1 kohm", "x1", "x2")])
    with pytest.raises(FloatingCircuitError):
        build_mna_problem(c)


# ==============================================================================
# 7. Determinism / permutation / node-renaming / isomorphism
# ==============================================================================
def test_determinism_repeated_solve():
    # Two solves of the same circuit must agree on everything mathematical
    # (digest, node voltages, currents, powers, diagnostics) — only the
    # wall-clock `timestamp` in provenance is allowed to differ (spec
    # section 19: determinism excludes timestamps from "content").
    c = bridge_circuit()
    r1 = solve_linear_dc(c)
    r2 = solve_linear_dc(c)
    d1, d2 = r1.to_dict(), r2.to_dict()
    d1["provenance"].pop("timestamp")
    d2["provenance"].pop("timestamp")
    assert d1 == d2
    assert r1.provenance["digest"] == r2.provenance["digest"]


def test_permutation_invariance_series():
    comps = [
        v("V1", "10 V", "n0", "0"),
        r("R1", "100 ohm", "n0", "n1"),
        r("R2", "200 ohm", "n1", "n2"),
        r("R3", "300 ohm", "n2", "0"),
    ]
    import itertools

    results = []
    for perm in itertools.permutations(comps):
        c = Circuit(name="perm")
        for comp in perm:
            c.add(comp)
        d = solve_linear_dc(c).to_dict()
        d["provenance"].pop("timestamp")
        results.append(d)
    first = results[0]
    for other in results[1:]:
        assert other == first


def test_permutation_invariance_bridge_components():
    import random

    base = bridge_circuit().components
    baseline = None
    rng = random.Random(1234)
    for _ in range(6):
        order = list(base)
        rng.shuffle(order)
        c = Circuit(name="bridge_perm")
        for comp in order:
            c.add(comp)
        result = solve_linear_dc(c).to_dict()
        result["provenance"].pop("timestamp")
        if baseline is None:
            baseline = result
        else:
            assert result == baseline


def test_node_renaming_invariance():
    c1 = series_circuit(3, "1000 ohm", "10 V")
    mapping = {"n0": "alpha", "n1": "beta", "n2": "gamma", "0": "0"}
    c2 = Circuit(name="renamed")
    for comp in c1.components:
        c2.add(
            Component(
                comp.ref,
                comp.type,
                comp.value,
                {pin: mapping[net] for pin, net in comp.pins.items()},
            )
        )
    res1 = solve_linear_dc(c1)
    res2 = solve_linear_dc(c2)
    # Physically identical: same currents/powers per ref, voltages equal
    # once mapped back through the renaming.
    assert current_map(res1) == current_map(res2)
    assert power_map(res1) == power_map(res2)
    v1 = voltage_map(res1)
    v2 = voltage_map(res2)
    for old, new in mapping.items():
        assert v1[old] == v2[new]


# ==============================================================================
# 8. Metamorphic / property testing: scaling
# ==============================================================================
def _scale_source_values(circuit, k):
    c = Circuit(name=circuit.name)
    for comp in circuit.components:
        if comp.type.upper() in ("V", "I"):
            scaled = parse_quantity(f"{comp.value.to_base() * k} {comp.value.unit.display}")
            c.add(Component(comp.ref, comp.type, scaled, dict(comp.pins)))
        else:
            c.add(comp)
    return c


def _scale_resistances(circuit, k):
    c = Circuit(name=circuit.name)
    for comp in circuit.components:
        if comp.type.upper() == "R":
            scaled = parse_quantity(f"{comp.value.to_base() * k} {comp.value.unit.display}")
            c.add(Component(comp.ref, comp.type, scaled, dict(comp.pins)))
        else:
            c.add(comp)
    return c


@pytest.mark.parametrize("k", [Decimal(2), Decimal("0.5"), Decimal(10)])
def test_scaling_sources_invariant(k):
    kf = Fraction(k)
    base = bridge_circuit()
    assert_solved(solve_linear_dc(base))  # status/conservation sanity
    _, _, v0 = exact_node_voltages(base)
    _, _, v1 = exact_node_voltages(_scale_source_values(base, k))
    for node in v0:
        assert v1[node] == v0[node] * kf
    i0, i1 = exact_branch_currents(base), exact_branch_currents(_scale_source_values(base, k))
    for ref in i0:
        assert i1[ref] == i0[ref] * kf


@pytest.mark.parametrize("k", [Decimal(2), Decimal("0.5"), Decimal(10)])
def test_scaling_resistances_invariant(k):
    kf = Fraction(k)
    base = bridge_circuit()
    assert_solved(solve_linear_dc(base))
    _, _, v0 = exact_node_voltages(base)
    _, _, v1 = exact_node_voltages(_scale_resistances(base, k))
    for node in v0:
        assert v1[node] == v0[node]
    i0, i1 = exact_branch_currents(base), exact_branch_currents(_scale_resistances(base, k))
    for ref in i0:
        assert i1[ref] == i0[ref] / kf


def test_series_equivalent_resistance_law():
    n = 6
    circuit = series_circuit(n, "1000 ohm", "10 V")
    currents = exact_branch_currents(circuit)
    i = currents["R1"]
    req = Fraction(10) / i
    assert req == Fraction(1000) * n


def test_parallel_equivalent_resistance_law():
    n = 6
    circuit = parallel_circuit(n, "1000 ohm", "10 V")
    currents = exact_branch_currents(circuit)
    total_i = sum(i for ref, i in currents.items() if ref.startswith("R"))
    req = Fraction(10) / total_i
    assert req == Fraction(1000) / n


# ==============================================================================
# 9. Units
# ==============================================================================
def test_units_prefixed_values():
    c = build("units", [v("V1", "1 kV", "n1", "0"), r("R1", "1 Mohm", "n1", "0")])
    res = assert_solved(solve_linear_dc(c))
    assert voltage_map(res)["n1"] == Decimal(1000)
    assert current_map(res)["R1"] == Decimal(1000) / Decimal(1_000_000)


# ==============================================================================
# 10. Linear solve primitive (isolated layer test)
# ==============================================================================
def test_solve_exact_unique():
    outcome = solve_exact([[Fraction(2), Fraction(1)], [Fraction(1), Fraction(-1)]], [Fraction(3), Fraction(0)])
    assert outcome.status == LinearSolveStatus.UNIQUE
    assert outcome.solution == (Fraction(1), Fraction(1))


def test_solve_exact_singular_consistent():
    outcome = solve_exact([[Fraction(1), Fraction(1)], [Fraction(2), Fraction(2)]], [Fraction(3), Fraction(6)])
    assert outcome.status == LinearSolveStatus.SINGULAR


def test_solve_exact_inconsistent():
    outcome = solve_exact([[Fraction(1), Fraction(1)], [Fraction(2), Fraction(2)]], [Fraction(3), Fraction(7)])
    assert outcome.status == LinearSolveStatus.INCONSISTENT


# ==============================================================================
# 11. ngspice cross-validation (external oracle, not the solver under test)
# ==============================================================================
def _ngspice_op(netlist):
    result = _NGSPICE.simulate(netlist, analyses=("op",))
    assert result.status == "COMPLETED", result.raw_stderr
    return {name: sig.samples[0] for name, sig in result.signals.items()}


@pytest.mark.integration
@pytest.mark.skipif(not _NGSPICE_AVAILABLE, reason="ngspice not available in this environment")
def test_ngspice_cross_validation_series_divider():
    res = assert_solved(solve_linear_dc(series_circuit(3, "1000 ohm", "9 V")))
    netlist = "series\nV1 n0 0 DC 9\nR1 n0 n1 1000\nR2 n1 n2 1000\nR3 n2 0 1000\n.op\n.end\n"
    signals = _ngspice_op(netlist)
    volts = voltage_map(res)
    assert round(signals["v(n1)"], 4) == round(Decimal(volts["n1"]), 4)
    assert round(signals["v(n2)"], 4) == round(Decimal(volts["n2"]), 4)


@pytest.mark.integration
@pytest.mark.skipif(not _NGSPICE_AVAILABLE, reason="ngspice not available in this environment")
def test_ngspice_cross_validation_parallel():
    res = assert_solved(solve_linear_dc(parallel_circuit(4, "2000 ohm", "6 V")))
    netlist = "par\nV1 n1 0 DC 6\nR1 n1 0 2000\nR2 n1 0 2000\nR3 n1 0 2000\nR4 n1 0 2000\n.op\n.end\n"
    signals = _ngspice_op(netlist)
    assert round(signals["v(n1)"], 4) == round(Decimal(voltage_map(res)["n1"]), 4)


@pytest.mark.integration
@pytest.mark.skipif(not _NGSPICE_AVAILABLE, reason="ngspice not available in this environment")
def test_ngspice_cross_validation_bridge_unbalanced():
    res = assert_solved(solve_linear_dc(bridge_circuit()))
    netlist = (
        "bridge\nV1 n1 0 DC 10\nR1 n1 n2 100\nR2 n1 n3 200\n"
        "R3 n2 0 300\nR4 n3 0 400\nR5 n2 n3 500\n.op\n.end\n"
    )
    signals = _ngspice_op(netlist)
    volts = voltage_map(res)
    assert round(signals["v(n2)"], 4) == round(Decimal(volts["n2"]), 4)
    assert round(signals["v(n3)"], 4) == round(Decimal(volts["n3"]), 4)


@pytest.mark.integration
@pytest.mark.skipif(not _NGSPICE_AVAILABLE, reason="ngspice not available in this environment")
def test_ngspice_cross_validation_mixed_sources():
    res = assert_solved(
        solve_linear_dc(
            build(
                "mixed_x",
                [
                    v("V1", "12 V", "n1", "0"),
                    r("R1", "100 ohm", "n1", "n2"),
                    isrc("I1", "0.01 A", "n2", "0"),
                    r("R2", "200 ohm", "n2", "0"),
                ],
            )
        )
    )
    netlist = "mixed\nV1 n1 0 DC 12\nR1 n1 n2 100\nI1 0 n2 DC 0.01\nR2 n2 0 200\n.op\n.end\n"
    signals = _ngspice_op(netlist)
    assert round(signals["v(n2)"], 4) == round(Decimal(voltage_map(res)["n2"]), 4)


# ==============================================================================
# 12. Security — no eval/exec/subprocess/os.system/shell=True/pickle/dynamic import
# ==============================================================================
_MNA_SRC_DIR = Path(__file__).resolve().parents[1] / "src" / "academic_core" / "domain" / "engineering" / "mna"

_FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__"}
_FORBIDDEN_MODULES = {"subprocess", "pickle", "os", "socket", "urllib", "requests", "http"}


def test_no_eval_exec_subprocess_in_mna_solver():
    for path in sorted(_MNA_SRC_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in _FORBIDDEN_CALLS, f"{path}: forbidden call {node.func.id}"
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mod = node.module if isinstance(node, ast.ImportFrom) else None
                names = [mod] if mod else [alias.name for alias in node.names]
                for name in names:
                    top = (name or "").split(".")[0]
                    assert top not in _FORBIDDEN_MODULES, f"{path}: forbidden import {name}"


def test_no_shell_true_or_dynamic_import_in_mna_solver():
    for path in sorted(_MNA_SRC_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert "shell=True" not in text
        assert "importlib" not in text
