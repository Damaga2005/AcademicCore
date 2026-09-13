"""F8-C: General Thevenin & Norton Analysis test suite.

Covers:
  * Open-circuit Vth, short-circuit In, and deactivated-network Rth
  * All topologies: series, parallel, divider, bridge (balanced & unbalanced),
    ladder, arbitrary non-series-parallel graphs
  * Multiple sources: multiple V, multiple I, mixed V + I
  * Port between two non-GND nodes (negative_terminal != GND)
  * Degenerate cases: Rth = 0, Rth = infinity, singular, inconsistent,
    invalid port (A == B, non-existent nets), unsupported element (diode, C, L)
  * Generality & parametric scaling: N in {1, 2, 3, 4, 8, 16, 32, 64}
  * Metamorphic invariants: source scaling (x k), resistance scaling (x k),
    component permutation invariance, bijective node renaming invariance,
    Thevenin <-> Norton equivalence
  * Dimensional algebra: Quantity exclusively, dimensions V, A, ohm
  * Multi-load verification: terminal voltage & current matching across loads
  * Real ngspice 47 cross-validation
  * Determinism & Provenance
  * Security AST scan
"""

from __future__ import annotations

import ast
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.thevenin import (
    EquivalentStatus,
    InvalidPortError,
    ResistanceKind,
    TheveninPort,
    UnsupportedCircuitError,
    analyze_norton,
    analyze_one_port,
    analyze_thevenin,
    verify_equivalent_with_loads,
)
from academic_core.domain.engineering.units import parse_quantity

try:
    from academic_core.infrastructure.ngspice import NgSpiceBackend

    _NGSPICE = NgSpiceBackend()
    _NGSPICE_AVAILABLE = _NGSPICE.detect().available
except Exception:  # pragma: no cover
    _NGSPICE_AVAILABLE = False


# ==============================================================================
# Helper builders
# ==============================================================================
def r(ref: str, value: str, n1: str, n2: str) -> Component:
    return Component(ref, "R", parse_quantity(value), {"1": n1, "2": n2})


def v(ref: str, value: str, np_: str, nm: str) -> Component:
    return Component(ref, "V", parse_quantity(value), {"+": np_, "-": nm})


def isrc(ref: str, value: str, np_: str, nm: str) -> Component:
    return Component(ref, "I", parse_quantity(value), {"+": np_, "-": nm})


def build(name: str, comps: list[Component]) -> Circuit:
    c = Circuit(name=name)
    for comp in comps:
        c.add(comp)
    return c


def series_circuit(n: int, r_ohm: str = "100 ohm", vs: str = "10 V") -> Circuit:
    """V1 from n0 to 0. R1..Rn in series from n0 to 'out'."""
    nodes = ["n0"] + [f"n{i}" for i in range(1, n)] + ["out"]
    comps = [v("V1", vs, "n0", "0")]
    for i in range(n):
        comps.append(r(f"R{i + 1}", r_ohm, nodes[i], nodes[i + 1]))
    return build(f"series_{n}", comps)


def parallel_circuit(n: int, r_ohm: str = "1000 ohm", vs: str = "10 V") -> Circuit:
    comps = [v("V1", vs, "n1", "0")]
    for i in range(n):
        comps.append(r(f"R{i + 1}", r_ohm, "n1", "0"))
    return build(f"parallel_{n}", comps)


def bridge_circuit(
    r1: str = "100 ohm",
    r2: str = "200 ohm",
    r3: str = "300 ohm",
    r4: str = "400 ohm",
    vs: str = "10 V",
) -> Circuit:
    """Wheatstone bridge with open mid-branch (port between n2 and n3)."""
    return build(
        "bridge",
        [
            v("V1", vs, "n1", "0"),
            r("R1", r1, "n1", "n2"),
            r("R2", r2, "n1", "n3"),
            r("R3", r3, "n2", "0"),
            r("R4", r4, "n3", "0"),
        ],
    )


# ==============================================================================
# 1. Basic Topologies: Series, Parallel, Voltage Divider
# ==============================================================================
def test_voltage_divider_thevenin_and_norton():
    # V1(10V) -> R1(100) -> n1 -> R2(100) -> 0. Port: (n1, 0)
    # Vth = 10 * 100/(100+100) = 5 V
    # Rth = 100 || 100 = 50 ohm
    # In = 5 / 50 = 0.1 A
    c = build(
        "divider",
        [
            v("V1", "10 V", "n0", "0"),
            r("R1", "100 ohm", "n0", "n1"),
            r("R2", "100 ohm", "n1", "0"),
        ],
    )
    port = TheveninPort("n1", "0")
    one = analyze_one_port(c, port)

    assert one.status == EquivalentStatus.VERIFIED
    assert one.is_equivalent
    assert one.thevenin.v_th.to_base() == Decimal("5")
    assert one.thevenin.r_th.to_base() == Decimal("50")
    assert one.norton.i_n.to_base() == Decimal("0.1")
    assert one.norton.r_n.to_base() == Decimal("50")


def test_series_resistors_port_at_end():
    # V1(12V) -- R1(10) -- R2(20) -- R3(30) -- port(n3, 0)
    c = build(
        "series_end",
        [
            v("V1", "12 V", "n0", "0"),
            r("R1", "10 ohm", "n0", "n1"),
            r("R2", "20 ohm", "n1", "n2"),
            r("R3", "30 ohm", "n2", "n3"),
        ],
    )
    port = TheveninPort("n3", "0")
    thev = analyze_thevenin(c, port)
    assert thev.status == EquivalentStatus.VERIFIED
    assert thev.v_th.to_base() == Decimal("12")
    assert thev.r_th.to_base() == Decimal("60")  # 10 + 20 + 30


def test_parallel_branches_thevenin():
    # Two identical source-resistor branches in parallel:
    # V1(12V) + R1(60) in parallel with V2(12V) + R2(60)
    # Vth = 12 V, Rth = 60 || 60 = 30 ohm, In = 12 / 30 = 0.4 A
    c = build(
        "parallel_sources",
        [
            v("V1", "12 V", "n1", "0"),
            r("R1", "60 ohm", "n1", "port_node"),
            v("V2", "12 V", "n2", "0"),
            r("R2", "60 ohm", "n2", "port_node"),
        ],
    )
    port = TheveninPort("port_node", "0")
    one = analyze_one_port(c, port)
    assert one.status == EquivalentStatus.VERIFIED
    assert one.thevenin.v_th.to_base() == Decimal("12")
    assert one.thevenin.r_th.to_base() == Decimal("30")
    assert one.norton.i_n.to_base() == Decimal("0.4")


# ==============================================================================
# 2. Bridge Networks: Balanced & Unbalanced (Non-series-parallel)
# ==============================================================================
def test_unbalanced_bridge_thevenin_and_norton():
    # Bridge with V1=10V, R1=100, R2=200, R3=300, R4=400. Port: (n2, n3) (neither is GND!)
    # V(n2) = 10 * 300 / 400 = 7.5 V = 15/2 V
    # V(n3) = 10 * 400 / 600 = 20/3 V
    # Vth = 15/2 - 20/3 = (45 - 40)/6 = 5/6 V
    # Dead network: V1 shorted to 0.
    # Rth = (R1 || R3) + (R2 || R4) = (30000/400) + (80000/600) = 75 + 400/3 = 625/3 ohm
    # In = Vth / Rth = (5/6) / (625/3) = (5/6) * (3/625) = 1/250 A = 0.004 A
    c = bridge_circuit()
    port = TheveninPort("n2", "n3")
    one = analyze_one_port(c, port)

    assert one.status == EquivalentStatus.VERIFIED
    assert one.is_equivalent
    assert one.thevenin.polarity == "+ on n2, - on n3"
    assert one.thevenin.v_th.to_base() == Decimal(5) / Decimal(6)
    assert one.thevenin.r_th.to_base() == Decimal(625) / Decimal(3)
    assert one.norton.i_n.to_base() == Decimal("0.004")


def test_balanced_bridge_zero_vth():
    # Balanced bridge: R1/R3 == R2/R4 -> V(n2) == V(n3) -> Vth = 0 V
    c = bridge_circuit(r1="100 ohm", r2="200 ohm", r3="200 ohm", r4="400 ohm")
    port = TheveninPort("n2", "n3")
    one = analyze_one_port(c, port)

    assert one.status == EquivalentStatus.VERIFIED
    assert one.thevenin.v_th.to_base() == Decimal("0")
    assert one.norton.i_n.to_base() == Decimal("0")
    # Rth = (100 || 200) + (200 || 400) = 200/3 + 400/3 = 600/3 = 200 ohm
    assert one.thevenin.r_th.to_base() == Decimal("200")


# ==============================================================================
# 3. Multiple Sources: Multiple V, Multiple I, Mixed V + I
# ==============================================================================
def test_multiple_voltage_sources_thevenin():
    # V1(5V) + V2(7V) aiding in series, across R1(20) + R2(40)
    c = build(
        "multiv",
        [
            v("V1", "5 V", "n1", "0"),
            v("V2", "7 V", "n2", "n1"),
            r("R1", "20 ohm", "n2", "n3"),
            r("R2", "40 ohm", "n3", "0"),
        ],
    )
    port = TheveninPort("n3", "0")
    res = analyze_thevenin(c, port)
    assert res.status == EquivalentStatus.VERIFIED
    # Total voltage = 12V. Divider across R2(40): Vth = 12 * 40 / 60 = 8 V
    assert res.v_th.to_base() == Decimal("8")
    assert res.r_th.to_base() == Decimal(20 * 40) / Decimal(60)  # 40/3 ohm


def test_multiple_current_sources_thevenin():
    # I1(1A) into n1, I2(2A) into n1, R1(10) to 0, R2(20) to port
    c = build(
        "multii",
        [
            isrc("I1", "1 A", "n1", "0"),
            isrc("I2", "2 A", "n1", "0"),
            r("R1", "10 ohm", "n1", "0"),
            r("R2", "20 ohm", "n1", "port_node"),
        ],
    )
    port = TheveninPort("port_node", "0")
    res = analyze_thevenin(c, port)
    assert res.status == EquivalentStatus.VERIFIED
    # Total current = 3A. V(n1) = 3 * 10 = 30 V. Open circuit V(port) = 30 V
    # Dead network: I1, I2 open. Rth = R1 + R2 = 30 ohm
    assert res.v_th.to_base() == Decimal("30")
    assert res.r_th.to_base() == Decimal("30")


def test_mixed_v_and_i_sources_thevenin_and_norton():
    # V1(12V) -- R1(100) -- n2 -- R2(200) -- 0, with I1=10mA into n2. Port: (n2, 0)
    # V(n2) = (12/100 + 0.01)/(1/100 + 1/200) = 0.13 / 0.015 = 26/3 V
    # Dead network: V1 shorted, I1 open -> Rth = 100 || 200 = 200/3 ohm
    # In = (26/3) / (200/3) = 26 / 200 = 0.13 A
    c = build(
        "mixed",
        [
            v("V1", "12 V", "n1", "0"),
            r("R1", "100 ohm", "n1", "n2"),
            isrc("I1", "0.01 A", "n2", "0"),
            r("R2", "200 ohm", "n2", "0"),
        ],
    )
    port = TheveninPort("n2", "0")
    one = analyze_one_port(c, port)
    assert one.status == EquivalentStatus.VERIFIED
    assert one.thevenin.v_th.to_base() == Decimal(26) / Decimal(3)
    assert one.thevenin.r_th.to_base() == Decimal(200) / Decimal(3)
    assert one.norton.i_n.to_base() == Decimal("0.13")


# ==============================================================================
# 4. Port Between Two Non-GND Nodes
# ==============================================================================
def test_port_between_two_non_gnd_nodes():
    # Floating one-port: neither terminal is GND
    c = build(
        "non_gnd_port",
        [
            v("V1", "24 V", "n1", "0"),
            r("R1", "10 ohm", "n1", "A"),
            r("R2", "30 ohm", "A", "0"),
            r("R3", "20 ohm", "n1", "B"),
            r("R4", "40 ohm", "B", "0"),
        ],
    )
    # Port from A to B: V(A) = 24 * 30/40 = 18V; V(B) = 24 * 40/60 = 16V
    # Vth = V(A) - V(B) = 18 - 16 = 2 V
    # Dead network: Rth = (10 || 30) + (20 || 40) = 300/40 + 800/60 = 7.5 + 13.333... = 125/6 ohm
    port = TheveninPort("A", "B")
    one = analyze_one_port(c, port)
    assert one.status == EquivalentStatus.VERIFIED
    assert one.thevenin.v_th.to_base() == Decimal("2")
    assert abs(one.thevenin.r_th.to_base() - Decimal(125) / Decimal(6)) < Decimal("1e-25")
    assert abs(one.norton.i_n.to_base() - Decimal("0.096")) < Decimal("1e-25")
    assert one.thevenin._r_th_exact == Fraction(125, 6)
    assert one.norton._i_n_exact == Fraction(12, 125)


# ==============================================================================
# 5. Arbitrary Non-Series-Parallel Mesh
# ==============================================================================
def test_arbitrary_5_node_mesh_thevenin():
    # 5-node planar mesh with cross-connections that cannot be reduced via series/parallel
    c = build(
        "mesh5",
        [
            v("V1", "15 V", "n1", "0"),
            r("R1", "100 ohm", "n1", "n2"),
            r("R2", "150 ohm", "n1", "n3"),
            r("R3", "200 ohm", "n2", "n3"),
            r("R4", "250 ohm", "n2", "n4"),
            r("R5", "300 ohm", "n3", "n4"),
            r("R6", "400 ohm", "n4", "0"),
            r("R7", "500 ohm", "n3", "0"),
        ],
    )
    port = TheveninPort("n4", "0")
    one = analyze_one_port(c, port)
    assert one.status == EquivalentStatus.VERIFIED
    assert one.thevenin._v_th_exact == Fraction(7572, 833)
    assert one.thevenin._r_th_exact == Fraction(107280, 833)
    assert one.norton._i_n_exact == Fraction(631, 8940)


# ==============================================================================
# 6. Degenerate Cases: Rth=0, Rth=inf, Singular, Inconsistent, Invalid Port
# ==============================================================================
def test_degenerate_ideal_voltage_source_rth_zero():
    # Pure voltage source across port: Rth = 0 ohm, Norton current undefined/infinite
    c = build("pure_v", [v("V1", "10 V", "n1", "0")])
    port = TheveninPort("n1", "0")
    thev = analyze_thevenin(c, port)
    assert thev.status == EquivalentStatus.VERIFIED
    assert thev.resistance_kind == ResistanceKind.ZERO
    assert thev.v_th.to_base() == Decimal("10")
    assert thev.r_th.to_base() == Decimal("0")

    nort = analyze_norton(c, port)
    assert nort.status == EquivalentStatus.UNDEFINED
    assert nort.resistance_kind == ResistanceKind.ZERO
    assert nort.i_n is None
    assert "not representable as a finite ordinary current source" in nort.diagnostics[0]


def test_degenerate_ideal_current_source_inconsistent_in_open_circuit():
    # Pure current source across open port with no return path is inconsistent in open circuit
    c = build("pure_i", [isrc("I1", "2 A", "n1", "0")])
    port = TheveninPort("n1", "0")
    thev = analyze_thevenin(c, port)
    assert thev.status == EquivalentStatus.INCONSISTENT


def test_singular_circuit_returns_singular_status():
    # Redundant parallel identical voltage sources
    c = build(
        "sing",
        [
            v("V1", "10 V", "n1", "0"),
            v("V2", "10 V", "n1", "0"),
            r("R1", "100 ohm", "n1", "0"),
        ],
    )
    port = TheveninPort("n1", "0")
    thev = analyze_thevenin(c, port)
    assert thev.status == EquivalentStatus.SINGULAR


def test_inconsistent_circuit_returns_inconsistent_status():
    # Incompatible parallel voltage sources
    c = build(
        "incon",
        [
            v("V1", "10 V", "n1", "0"),
            v("V2", "20 V", "n1", "0"),
        ],
    )
    port = TheveninPort("n1", "0")
    thev = analyze_thevenin(c, port)
    assert thev.status == EquivalentStatus.INCONSISTENT


def test_invalid_port_same_terminal_rejected():
    with pytest.raises(InvalidPortError):
        _ = TheveninPort("n1", "n1")


def test_invalid_port_nonexistent_terminal_rejected():
    c = build("c_valid", [v("V1", "5 V", "n1", "0"), r("R1", "100 ohm", "n1", "0")])
    port = TheveninPort("n1", "nonexistent_node")
    thev = analyze_thevenin(c, port)
    assert thev.status == EquivalentStatus.INVALID_PORT


def test_unsupported_component_diode_abstains():
    c = Circuit(name="diode_c")
    c.add(Component("D1", "D", None, {"A": "n1", "K": "0"}))
    port = TheveninPort("n1", "0")
    thev = analyze_thevenin(c, port)
    assert thev.status == EquivalentStatus.UNSUPPORTED


# ==============================================================================
# 7. Generality & Parametric Scaling: N in {1, 2, 3, 4, 8, 16, 32, 64}
# ==============================================================================
@pytest.mark.parametrize("n", [1, 2, 3, 4, 8, 16, 32, 64])
def test_series_scaling_thevenin(n):
    # N identical series resistors of 100 ohm each: Rth = N * 100 ohm, Vth = 10 V
    c = series_circuit(n, r_ohm="100 ohm", vs="10 V")
    port = TheveninPort("out", "0")
    thev = analyze_thevenin(c, port)
    assert thev.status == EquivalentStatus.VERIFIED
    assert thev.v_th.to_base() == Decimal("10")
    assert thev.r_th.to_base() == Decimal(n * 100)


@pytest.mark.parametrize("n", [1, 2, 3, 4, 8, 16, 32, 64])
def test_parallel_scaling_thevenin(n):
    # N identical parallel resistors of 1000 ohm each across port:
    # Rth = 1000 / N ohm, Vth = 10 V
    c = parallel_circuit(n, r_ohm="1000 ohm", vs="10 V")
    port = TheveninPort("n1", "0")
    thev = analyze_thevenin(c, port)
    # Notice: V1 is connected directly between n1 and 0 in parallel_circuit!
    # So V1 is in parallel with the resistors -> Rth = 0 ohm (ideal voltage source)!
    assert thev.status == EquivalentStatus.VERIFIED
    assert thev.resistance_kind == ResistanceKind.ZERO
    assert thev.v_th.to_base() == Decimal("10")
    assert thev.r_th.to_base() == Decimal("0")


@pytest.mark.parametrize("stages", [1, 2, 3, 4, 8, 16])
def test_ladder_thevenin(stages):
    from tests.test_f8b_mna_solver import ladder_circuit

    c = ladder_circuit(stages, r_ohm="1000 ohm", vs="10 V")
    port = TheveninPort("a0", "0")
    thev = analyze_thevenin(c, port)
    assert thev.status == EquivalentStatus.VERIFIED
    assert thev.v_th.to_base() == Decimal("10")


# ==============================================================================
# 8. Metamorphic Invariants: Scaling, Permutation, Renaming
# ==============================================================================
@pytest.mark.parametrize("k", [Decimal(2), Decimal("0.5"), Decimal(5)])
def test_metamorphic_source_scaling(k):
    # Vth -> k * Vth, In -> k * In, Rth -> Rth
    base = bridge_circuit()
    port = TheveninPort("n2", "n3")
    one_base = analyze_one_port(base, port)

    c_scaled = build(
        "scaled_src",
        [
            v("V1", f"{Decimal(10) * k} V", "n1", "0"),
            r("R1", "100 ohm", "n1", "n2"),
            r("R2", "200 ohm", "n1", "n3"),
            r("R3", "300 ohm", "n2", "0"),
            r("R4", "400 ohm", "n3", "0"),
        ],
    )
    one_scaled = analyze_one_port(c_scaled, port)

    assert abs(one_scaled.thevenin.v_th.to_base() - one_base.thevenin.v_th.to_base() * k) < Decimal("1e-24")
    assert abs(one_scaled.norton.i_n.to_base() - one_base.norton.i_n.to_base() * k) < Decimal("1e-24")
    assert one_scaled.thevenin.r_th.to_base() == one_base.thevenin.r_th.to_base()
    assert one_scaled.thevenin._v_th_exact == one_base.thevenin._v_th_exact * Fraction(k)
    assert one_scaled.norton._i_n_exact == one_base.norton._i_n_exact * Fraction(k)


@pytest.mark.parametrize("k", [Decimal(2), Decimal("0.5"), Decimal(10)])
def test_metamorphic_resistance_scaling(k):
    # Rth -> k * Rth, Vth -> Vth, In -> In / k
    base = bridge_circuit()
    port = TheveninPort("n2", "n3")
    one_base = analyze_one_port(base, port)

    c_scaled = build(
        "scaled_r",
        [
            v("V1", "10 V", "n1", "0"),
            r("R1", f"{Decimal(100) * k} ohm", "n1", "n2"),
            r("R2", f"{Decimal(200) * k} ohm", "n1", "n3"),
            r("R3", f"{Decimal(300) * k} ohm", "n2", "0"),
            r("R4", f"{Decimal(400) * k} ohm", "n3", "0"),
        ],
    )
    one_scaled = analyze_one_port(c_scaled, port)

    assert abs(one_scaled.thevenin.r_th.to_base() - one_base.thevenin.r_th.to_base() * k) < Decimal("1e-24")
    assert one_scaled.thevenin.v_th.to_base() == one_base.thevenin.v_th.to_base()
    assert abs(one_scaled.norton.i_n.to_base() - one_base.norton.i_n.to_base() / k) < Decimal("1e-24")
    assert one_scaled.thevenin._r_th_exact == one_base.thevenin._r_th_exact * Fraction(k)
    assert one_scaled.norton._i_n_exact == one_base.norton._i_n_exact / Fraction(k)


def test_metamorphic_component_permutation():
    # Permuting insertion order does not alter physical result
    import itertools

    comps = [
        v("V1", "10 V", "n1", "0"),
        r("R1", "100 ohm", "n1", "n2"),
        r("R2", "200 ohm", "n2", "0"),
    ]
    port = TheveninPort("n2", "0")
    baseline = None
    for perm in itertools.permutations(comps):
        c = Circuit(name="perm")
        for comp in perm:
            c.add(comp)
        one = analyze_one_port(c, port)
        d = one.to_dict()
        d["provenance"].pop("timestamp")
        d["thevenin"]["provenance"].pop("timestamp")
        d["norton"]["provenance"].pop("timestamp")
        if baseline is None:
            baseline = d
        else:
            assert d == baseline


def test_metamorphic_node_renaming():
    # Bijective node renaming preserves physical equivalent
    c_orig = bridge_circuit()
    mapping = {"n1": "alpha", "n2": "beta", "n3": "gamma", "0": "0"}
    c_renamed = Circuit(name="renamed")
    for comp in c_orig.components:
        c_renamed.add(
            Component(
                comp.ref,
                comp.type,
                comp.value,
                {pin: mapping[net] for pin, net in comp.pins.items()},
            )
        )
    port_orig = TheveninPort("n2", "n3")
    port_renamed = TheveninPort("beta", "gamma")

    one_orig = analyze_one_port(c_orig, port_orig)
    one_renamed = analyze_one_port(c_renamed, port_renamed)

    assert one_orig.thevenin.v_th == one_renamed.thevenin.v_th
    assert one_orig.thevenin.r_th == one_renamed.thevenin.r_th
    assert one_orig.norton.i_n == one_renamed.norton.i_n


def test_metamorphic_port_ab_swapped():
    # Invariant: Vth(A, B) == -Vth(B, A), In(A, B) == -In(B, A), Rth(A, B) == Rth(B, A)
    c = bridge_circuit()
    port_ab = TheveninPort("n2", "n3")
    port_ba = TheveninPort("n3", "n2")

    res_ab = analyze_one_port(c, port_ab)
    res_ba = analyze_one_port(c, port_ba)

    assert res_ab.thevenin._v_th_exact == -res_ba.thevenin._v_th_exact
    assert res_ab.norton._i_n_exact == -res_ba.norton._i_n_exact
    assert res_ab.thevenin._r_th_exact == res_ba.thevenin._r_th_exact
    assert res_ab.thevenin.v_th.to_base() == -res_ba.thevenin.v_th.to_base()
    assert res_ab.norton.i_n.to_base() == -res_ba.norton.i_n.to_base()
    assert res_ab.thevenin.r_th.to_base() == res_ba.thevenin.r_th.to_base()


def test_parallel_branches_multigraph():
    # Circuit multigraph with parallel resistors between the same pair of nodes
    c = Circuit(name="multigraph")
    c.add(Component("V1", "V", parse_quantity("12 V"), {"+": "n1", "-": "0"}))
    c.add(Component("R1", "R", parse_quantity("200 ohm"), {"1": "n1", "2": "A"}))
    c.add(Component("R2", "R", parse_quantity("200 ohm"), {"1": "n1", "2": "A"}))  # R1 || R2 = 100 ohm
    c.add(Component("R3", "R", parse_quantity("600 ohm"), {"1": "A", "2": "0"}))
    c.add(Component("R4", "R", parse_quantity("300 ohm"), {"1": "A", "2": "0"}))  # R3 || R4 = 200 ohm
    # Vth = 12 * 200 / 300 = 8 V
    # Rth = 100 || 200 = 200/3 ohm
    # In = 8 / (200/3) = 24/200 = 0.12 A = 3/25 A
    port = TheveninPort("A", "0")
    one = analyze_one_port(c, port)

    assert one.status == EquivalentStatus.VERIFIED
    assert one.thevenin._v_th_exact == Fraction(8, 1)
    assert one.thevenin._r_th_exact == Fraction(200, 3)
    assert one.norton._i_n_exact == Fraction(3, 25)


def test_analysis_immutability_idempotence():
    # Calling analysis repeatedly on the same Circuit object mutates nothing
    c = bridge_circuit()
    comps_before = [(comp.ref, comp.type, str(comp.value), dict(comp.pins)) for comp in c.components]
    nets_before = set(c.nets)

    port = TheveninPort("n2", "n3")
    res1 = analyze_one_port(c, port)
    res2 = analyze_one_port(c, port)

    comps_after = [(comp.ref, comp.type, str(comp.value), dict(comp.pins)) for comp in c.components]
    nets_after = set(c.nets)

    assert comps_before == comps_after
    assert nets_before == nets_after
    assert res1.thevenin._v_th_exact == res2.thevenin._v_th_exact
    assert res1.thevenin._r_th_exact == res2.thevenin._r_th_exact
    assert res1.norton._i_n_exact == res2.norton._i_n_exact
    assert res1.thevenin.provenance["digest"] == res2.thevenin.provenance["digest"]


# ==============================================================================
# 9. Dimensionality Tests
# ==============================================================================
def test_dimensional_integrity_units():
    c = bridge_circuit()
    port = TheveninPort("n2", "n3")
    one = analyze_one_port(c, port)

    assert one.thevenin.v_th.unit.symbol in ("V", "volt", "volts")
    assert one.thevenin.r_th.unit.symbol in ("ohm", "Ω", "Ω")
    assert one.norton.i_n.unit.symbol in ("A", "amp", "amps")
    assert one.thevenin.v_th.dim_name == "voltage"
    assert one.thevenin.r_th.dim_name == "resistance"
    assert one.norton.i_n.dim_name == "current"


# ==============================================================================
# 10. Multi-Load Verification Coverage
# ==============================================================================
def test_multi_load_verification_detail():
    c = build(
        "div_load",
        [
            v("V1", "12 V", "n1", "0"),
            r("R1", "150 ohm", "n1", "n2"),
            r("R2", "300 ohm", "n2", "0"),
        ],
    )
    port = TheveninPort("n2", "0")
    res = analyze_thevenin(c, port)
    assert res.status == EquivalentStatus.VERIFIED
    assert len(res.load_verifications) >= 5
    for lv in res.load_verifications:
        assert lv.passed
        # Check Ohm's law on original port terminals
        assert lv.v_port_original == lv.v_port_equivalent
        assert lv.i_port_original == lv.i_port_equivalent


# ==============================================================================
# 11. Determinism
# ==============================================================================
def test_determinism_repeated_execution():
    c = bridge_circuit()
    port = TheveninPort("n2", "n3")
    one_0 = analyze_one_port(c, port)
    d0 = one_0.to_dict()
    d0["provenance"].pop("timestamp")
    d0["thevenin"]["provenance"].pop("timestamp")
    d0["norton"]["provenance"].pop("timestamp")

    for _ in range(50):
        one = analyze_one_port(c, port)
        d = one.to_dict()
        d["provenance"].pop("timestamp")
        d["thevenin"]["provenance"].pop("timestamp")
        d["norton"]["provenance"].pop("timestamp")
        assert d == d0
        assert one.provenance["digest"] == one_0.provenance["digest"]


# ==============================================================================
# 12. Real ngspice 47 Cross-Validation
# ==============================================================================
def _ngspice_op(netlist: str) -> dict:
    result = _NGSPICE.simulate(netlist, analyses=("op",))
    assert result.status == "COMPLETED", result.raw_stderr
    return {name: sig.samples[0] for name, sig in result.signals.items()}


@pytest.mark.integration
@pytest.mark.skipif(not _NGSPICE_AVAILABLE, reason="ngspice not available in this environment")
def test_ngspice_cross_validation_divider():
    c = build(
        "div_sp",
        [
            v("V1", "10 V", "n1", "0"),
            r("R1", "100 ohm", "n1", "n2"),
            r("R2", "100 ohm", "n2", "0"),
        ],
    )
    port = TheveninPort("n2", "0")
    thev = analyze_thevenin(c, port)

    # Open-circuit in ngspice
    netlist_oc = "divider_oc\nV1 n1 0 DC 10\nR1 n1 n2 100\nR2 n2 0 100\n.op\n.end\n"
    signals_oc = _ngspice_op(netlist_oc)
    assert round(signals_oc["v(n2)"], 4) == round(thev.v_th.to_base(), 4)

    # Short-circuit in ngspice: short n2 to 0 via dummy 0V source
    netlist_sc = "divider_sc\nV1 n1 0 DC 10\nR1 n1 n2 100\nR2 n2 0 100\nVsc n2 0 DC 0\n.op\n.end\n"
    signals_sc = _ngspice_op(netlist_sc)
    # Current flowing through Vsc from n2 to 0
    i_sc_spice = abs(signals_sc["i(vsc)"])
    nort = analyze_norton(c, port)
    assert round(i_sc_spice, 4) == round(nort.i_n.to_base(), 4)


@pytest.mark.integration
@pytest.mark.skipif(not _NGSPICE_AVAILABLE, reason="ngspice not available in this environment")
def test_ngspice_cross_validation_unbalanced_bridge():
    c = bridge_circuit()
    port = TheveninPort("n2", "n3")
    one = analyze_one_port(c, port)

    # Open-circuit bridge in ngspice
    netlist_oc = (
        "bridge_oc\nV1 n1 0 DC 10\nR1 n1 n2 100\nR2 n1 n3 200\n"
        "R3 n2 0 300\nR4 n3 0 400\n.op\n.end\n"
    )
    sig_oc = _ngspice_op(netlist_oc)
    vth_spice = sig_oc["v(n2)"] - sig_oc["v(n3)"]
    assert round(vth_spice, 4) == round(one.thevenin.v_th.to_base(), 4)

    # Short-circuit bridge in ngspice (0V dummy source between n2 and n3)
    netlist_sc = (
        "bridge_sc\nV1 n1 0 DC 10\nR1 n1 n2 100\nR2 n1 n3 200\n"
        "R3 n2 0 300\nR4 n3 0 400\nVsc n2 n3 DC 0\n.op\n.end\n"
    )
    sig_sc = _ngspice_op(netlist_sc)
    isc_spice = abs(sig_sc["i(vsc)"])
    assert round(isc_spice, 6) == round(one.norton.i_n.to_base(), 6)

    # Loaded bridge in ngspice with Rload = 500 ohm across n2 and n3
    netlist_load = (
        "bridge_load\nV1 n1 0 DC 10\nR1 n1 n2 100\nR2 n1 n3 200\n"
        "R3 n2 0 300\nR4 n3 0 400\nRL n2 n3 500\n.op\n.end\n"
    )
    sig_ld = _ngspice_op(netlist_load)
    vport_spice = sig_ld["v(n2)"] - sig_ld["v(n3)"]
    iport_spice = abs(vport_spice / Decimal(500))

    # Equivalent model loaded with 500 ohm:
    rth = float(one.thevenin.r_th.to_base())
    vth = float(one.thevenin.v_th.to_base())
    vport_thev = vth * 500.0 / (rth + 500.0)
    iport_thev = vport_thev / 500.0

    assert round(Decimal(vport_spice), 4) == round(Decimal(str(vport_thev)), 4)
    assert round(Decimal(iport_spice), 6) == round(Decimal(str(iport_thev)), 6)


# ==============================================================================
# 13. Security AST Scan
# ==============================================================================
_THEVENIN_SRC_DIR = Path(__file__).resolve().parents[1] / "src" / "academic_core" / "domain" / "engineering" / "thevenin"
_FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__"}
_FORBIDDEN_MODULES = {"subprocess", "pickle", "marshal", "os", "socket", "urllib", "requests", "http"}


def test_no_eval_exec_subprocess_in_thevenin_package():
    for path in sorted(_THEVENIN_SRC_DIR.glob("*.py")):
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


def test_no_shell_true_or_dynamic_import_in_thevenin_package():
    for path in sorted(_THEVENIN_SRC_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert "shell=True" not in text
        assert "importlib" not in text
