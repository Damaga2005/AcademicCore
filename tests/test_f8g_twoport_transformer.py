"""F8-G Ideal transformers + linear two-port parameters.

Conventions (frozen, hand-verified):
  - T pins "1"/"2" primary +/-, "3"/"4" secondary +/-; value n real.
  - Aux i1 = current 1->2, aux i2 = current 3->4 (both leaving "+").
  - Constraints: V(3)-V(4)-n(V(1)-V(2)) = 0; I1+n·I2 = 0.
  - Leg records "T1:1"/"T1:2" keep ref-keyed consumers generic.
  - Two-port currents ENTER both ports (D5 rule); ABCD uses -I2
    (leaving port 2): V1 = A·V2 - B·I2, I1 = C·V2 - D·I2.
  - Power absorbed P = V*I (DC), S = 1/2 V conj(I) (AC); ideal T
    stores/delivers nothing: P1+P2 = 0 exactly.

ngspice mapping: no ideal device exists; coupled inductors
(L2 = n^2·L1, K -> 1, large L) approximate it with a per-case
analytic bound (magnetizing branch). Academic Core is authoritative.
"""
import ast
import time
from decimal import Decimal
from fractions import Fraction

import pytest

from academic_core.domain.engineering.ac import (
    ACStatus,
    PortDefinition,
    analyze_ac_thevenin,
    solve_ac,
)
from academic_core.domain.engineering.ac.impedance import ImpedanceCategory
from academic_core.domain.engineering.ac.power import analyze_power
from academic_core.domain.engineering.ac.response import (
    ResponseDefinition,
    current_through,
    frequency_response,
    voltage_between,
)
from academic_core.domain.engineering.ac.twoport import (
    TwoPortCategory,
    abcd_parameters,
    g_parameters,
    h_parameters,
    y_parameters,
    z_parameters,
)
from academic_core.domain.engineering.circuit import (
    Circuit,
    CircuitError,
    Component,
)
from academic_core.domain.engineering.math import RationalComplex
from academic_core.domain.engineering.math.linsolve.problem import NumericMode
from academic_core.domain.engineering.mna import (
    build_mna_problem,
    describe_dependents,
    solve_linear_dc,
)
from academic_core.domain.engineering.mna.errors import (
    CircularControlError,
    InvalidCircuitError,
)
from academic_core.domain.engineering.mna.result import SolveStatus
from academic_core.domain.engineering.thevenin import analyze_norton, analyze_thevenin
from academic_core.domain.engineering.thevenin.port import TheveninPort
from academic_core.domain.engineering.thevenin.result import (
    EquivalentStatus,
    ResistanceKind,
)
from academic_core.domain.engineering.units import parse_quantity


def Q(text):
    return parse_quantity(text)


def R_(ref, value, n1, n2):
    return Component(ref, "R", Q(value), {"1": n1, "2": n2}, {})


def L_(ref, value, n1, n2):
    return Component(ref, "L", Q(value), {"1": n1, "2": n2}, {})


def C_(ref, value, n1, n2):
    return Component(ref, "C", Q(value), {"1": n1, "2": n2}, {})


def V_(ref, value, np_, nm):
    return Component(ref, "V", Q(value), {"+": np_, "-": nm}, {})


def I_(ref, value, np_, nm):
    return Component(ref, "I", Q(value), {"+": np_, "-": nm}, {})


def T_(ref, n, p1, p2, s1, s2):
    return Component(ref, "T", Q(n), {"1": p1, "2": p2, "3": s1, "4": s2}, {})


def E_(ref, gain, np_, nm, cp, cn):
    return Component(ref, "E", Q(gain), {"+": np_, "-": nm},
                     {"cp": cp, "cn": cn})


def G_(ref, gain, np_, nm, cp, cn):
    return Component(ref, "G", Q(gain), {"+": np_, "-": nm},
                     {"cp": cp, "cn": cn})


def H_(ref, gain, np_, nm, ctrl):
    return Component(ref, "H", Q(gain), {"+": np_, "-": nm},
                     {"control_ref": ctrl})


def F_(ref, gain, np_, nm, ctrl):
    return Component(ref, "F", Q(gain), {"+": np_, "-": nm},
                     {"control_ref": ctrl})


def O_(ref, np_, nm, no_):
    return Component(ref, "O", None, {"+": np_, "-": nm, "o": no_}, {})


def ckt(name, *comps):
    c = Circuit(name)
    for e in comps:
        c.add(e)
    return c


def assert_dc_solved(res):
    assert res.status == SolveStatus.SOLVED, res.diagnostics
    return res


def dc_voltages(res):
    return {n.node: n.voltage.to_base() for n in res.node_voltages}


def dc_currents(res):
    return {b.ref: b.current.to_base() for b in res.branch_currents}


def ac_solved(circuit, freq="1 kHz"):
    r = solve_ac(circuit, freq)
    assert r.status == ACStatus.SOLVED, r.diagnostics
    return r


# -- model & validation ---------------------------------------------------------

def test_model_pins_and_ref():
    t = T_("T1", "2", "a", "0", "b", "0")
    assert t.pins == {"1": "a", "2": "0", "3": "b", "4": "0"}
    assert t.value.to_base() == Decimal("2")
    assert t.parameters == {}


def test_model_bad_pins_rejected():
    with pytest.raises(CircuitError):
        Component("T1", "T", Q("2"), {"1": "a", "2": "0", "3": "b"}, {})
    with pytest.raises(CircuitError):
        Component("T1", "T", Q("2"), {"1": "", "2": "0", "3": "b", "4": "0"}, {})
    with pytest.raises(CircuitError):
        Component("R1", "T", Q("2"), {"1": "a", "2": "0", "3": "b", "4": "0"}, {})
    with pytest.raises(CircuitError):
        Component("T1", "R", Q("2"), {"1": "a", "2": "0", "3": "b", "4": "0"}, {})


def test_validation_voltage_dimension_rejected_dc():
    c = ckt("tBX", V_("V1", "10 V", "a", "0"),
            Component("T1", "T", Q("2 V"), {"1": "a", "2": "0", "3": "b", "4": "0"}, {}),
            R_("R1", "1 kOhm", "b", "0"))
    assert solve_linear_dc(c).status == SolveStatus.INVALID


def test_validation_current_dimension_rejected_dc():
    c = ckt("tBC", V_("V1", "10 V", "a", "0"),
            Component("T1", "T", Q("2 mS"), {"1": "a", "2": "0", "3": "b", "4": "0"}, {}),
            R_("R1", "1 kOhm", "b", "0"))
    assert solve_linear_dc(c).status == SolveStatus.INVALID


def test_validation_nonfinite_gain_rejected():
    from decimal import Decimal as _D
    from academic_core.domain.engineering.units import Quantity
    unit = Q("2").unit
    for bad in (Decimal("Infinity"), Decimal("-Infinity"), Decimal("NaN")):
        c = ckt("tNF", V_("V1", "10 V", "a", "0"),
                Component("T1", "T", Quantity(bad, unit),
                          {"1": "a", "2": "0", "3": "b", "4": "0"}, {}),
                R_("R1", "1 kOhm", "b", "0"))
        assert solve_linear_dc(c).status == SolveStatus.INVALID, bad


def test_validation_params_rejected():
    c = ckt("tPR", V_("V1", "10 V", "a", "0"),
            Component("T1", "T", Q("2"), {"1": "a", "2": "0", "3": "b", "4": "0"},
                      {"n": "2"}),
            R_("R1", "1 kOhm", "b", "0"))
    assert solve_linear_dc(c).status == SolveStatus.INVALID


def test_validation_missing_value_rejected():
    c = Circuit("tMV")
    c.add(V_("V1", "10 V", "a", "0"))
    c.add(Component("T1", "T", None, {"1": "a", "2": "0", "3": "b", "4": "0"}, {}))
    c.add(R_("R1", "1 kOhm", "b", "0"))
    assert solve_linear_dc(c).status == SolveStatus.INVALID


def test_validation_ac_dimension_rejected():
    c = ckt("tAV", V_("V1", "10 V", "a", "0"),
            Component("T1", "T", Q("2 V"), {"1": "a", "2": "0", "3": "b", "4": "0"}, {}),
            R_("R1", "1 kOhm", "b", "0"))
    assert solve_ac(c, "1 kHz").status == ACStatus.INVALID


def test_validation_hf_control_by_T_rejected_dc():
    # Ambiguous (two winding currents) — loud INVALID, never a guess.
    c = ckt("tHC", V_("V1", "10 V", "s", "0"), R_("R0", "1 kOhm", "s", "a"),
            T_("T1", "2", "a", "0", "b", "0"), R_("R1", "1 kOhm", "b", "0"),
            H_("H1", "100 ohm", "c", "0", "T1"), R_("R2", "1 kOhm", "c", "0"))
    assert solve_linear_dc(c).status == SolveStatus.INVALID


def test_validation_hf_control_by_T_rejected_ac():
    c = ckt("tHA", V_("V1", "10 V", "s", "0"), R_("R0", "1 kOhm", "s", "a"),
            T_("T1", "2", "a", "0", "b", "0"), R_("R1", "1 kOhm", "b", "0"),
            F_("F1", "3", "c", "0", "T1"), R_("R2", "1 kOhm", "c", "0"))
    assert solve_ac(c, "1 kHz").status == ACStatus.INVALID


def test_validation_hf_control_by_leg_ref_rejected():
    # Leg refs are branch records, not components — also invalid.
    c = ckt("tHL", V_("V1", "10 V", "s", "0"), R_("R0", "1 kOhm", "s", "a"),
            T_("T1", "2", "a", "0", "b", "0"), R_("R1", "1 kOhm", "b", "0"),
            H_("H1", "100 ohm", "c", "0", "T1:1"), R_("R2", "1 kOhm", "c", "0"))
    assert solve_linear_dc(c).status == SolveStatus.INVALID


def test_validation_gains_zero_negative_fractional():
    for n, tag in (("0", "zero"), ("-1", "neg"), ("0.5", "frac"),
                   ("1000", "big"), ("0.001", "small")):
        c = ckt(f"tG{tag}", V_("V1", "10 V", "a", "0"),
                T_("T1", n, "a", "0", "b", "0"),
                R_("R1", "1 kOhm", "b", "0"))
        r = solve_linear_dc(c)
        assert r.status == SolveStatus.SOLVED, (tag, r.diagnostics)


# -- stamping & signs ------------------------------------------------------------

def test_stamp_matrix_shape_and_squareness():
    from academic_core.domain.engineering.mna.problem import build_mna_problem
    c = ckt("tST", V_("V1", "10 V", "a", "0"),
            T_("T1", "2", "a", "0", "b", "0"),
            R_("R1", "1 kOhm", "b", "0"))
    p = build_mna_problem(c)
    # 2 non-ground nets + 1 V aux + 2 T aux = 5 unknowns, square system.
    assert p.size == 5
    assert len(p.matrix) == 5 and all(len(row) == 5 for row in p.matrix)
    assert len(p.rhs) == 5
    assert p.tx_leg_refs == ("T1:1", "T1:2")
    assert p.vsource_index["T1:1"] == 3 and p.vsource_index["T1:2"] == 4


def test_stamp_constraint_rows():
    # Row k1: V(3)-V(4)-n(V(1)-V(2)) = 0; row k2: I1+n·I2 = 0.
    from academic_core.domain.engineering.mna.problem import build_mna_problem
    c = ckt("tSR", T_("T1", "3", "a", "b", "c", "d"),
            R_("R1", "1 kOhm", "a", "0"), R_("R2", "1 kOhm", "b", "0"),
            R_("R3", "1 kOhm", "c", "0"), R_("R4", "1 kOhm", "d", "0"),
            V_("V1", "1 V", "a", "0"))
    p = build_mna_problem(c)
    k1, k2 = p.vsource_index["T1:1"], p.vsource_index["T1:2"]
    row1, row2 = p.matrix[k1], p.matrix[k2]
    ni = p.node_index
    assert row1[ni["c"]] == Fraction(1) and row1[ni["d"]] == Fraction(-1)
    assert row1[ni["a"]] == Fraction(-3) and row1[ni["b"]] == Fraction(3)
    assert p.rhs[k1] == Fraction(0)
    assert row2[k1] == Fraction(1) and row2[k2] == Fraction(3)
    assert all(v == Fraction(0) for j, v in enumerate(row2) if j not in (k1, k2))
    assert p.rhs[k2] == Fraction(0)


def test_stamp_kcl_entries():
    # Aux i1 leaves pin-1 net (+1), enters pin-2 net (-1); same for i2.
    from academic_core.domain.engineering.mna.problem import build_mna_problem
    c = ckt("tSK", T_("T1", "2", "a", "b", "c", "d"),
            R_("R1", "1 kOhm", "a", "0"), R_("R2", "1 kOhm", "b", "0"),
            R_("R3", "1 kOhm", "c", "0"), R_("R4", "1 kOhm", "d", "0"),
            V_("V1", "1 V", "a", "0"))
    p = build_mna_problem(c)
    k1, k2 = p.vsource_index["T1:1"], p.vsource_index["T1:2"]
    ni = p.node_index
    assert p.matrix[ni["a"]][k1] == Fraction(1)
    assert p.matrix[ni["b"]][k1] == Fraction(-1)
    assert p.matrix[ni["c"]][k2] == Fraction(1)
    assert p.matrix[ni["d"]][k2] == Fraction(-1)


def test_sign_constraints_hold_on_solution():
    # V2 - n·V1 = 0 and I1 + n·I2 = 0 on solved values (DC exact).
    c = ckt("tSG", V_("V1", "10 V", "s", "0"), R_("R0", "100 ohm", "s", "a"),
            T_("T1", "2", "a", "0", "b", "0"), R_("R1", "400 ohm", "b", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    v = dc_voltages(r)
    i = dc_currents(r)
    assert v["b"] == 2 * v["a"]
    assert i["T1:1"] + 2 * i["T1:2"] == Decimal("0")


def test_sign_power_sums_to_zero():
    # Per-leg absorbed powers cancel exactly for the ideal device.
    c = ckt("tPW", V_("V1", "10 V", "s", "0"), R_("R0", "100 ohm", "s", "a"),
            T_("T1", "2", "a", "0", "b", "0"), R_("R1", "400 ohm", "b", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    pw = {e.ref: e.power.to_base() for e in r.element_powers}
    assert pw["T1:1"] + pw["T1:2"] == Decimal("0")
    assert r.conservation_checks.passed is True


# -- DC benchmarks (hand nodal, exact Fractions) ----------------------------------

def test_dc_step_up_loaded():
    # V=10, n=2, R=1k secondary: Vb=20; I1=40mA; I2=-20mA.
    c = ckt("tDC", V_("V1", "10 V", "a", "0"),
            T_("T1", "2", "a", "0", "b", "0"), R_("R1", "1 kOhm", "b", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    assert dc_voltages(r)["b"] == Decimal("20")
    assert dc_currents(r)["T1:1"] == Decimal("0.04")
    assert dc_currents(r)["T1:2"] == Decimal("-0.02")


def test_dc_step_down():
    # n=1/2: V=10 -> 5; I2 = -5mA (R=1k); I1 = -n·I2 = +2.5mA.
    c = ckt("tSD", V_("V1", "10 V", "a", "0"),
            T_("T1", "0.5", "a", "0", "b", "0"), R_("R1", "1 kOhm", "b", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    assert dc_voltages(r)["b"] == Decimal("5")
    assert dc_currents(r)["T1:2"] == Decimal("-0.005")
    assert dc_currents(r)["T1:1"] == Decimal("0.0025")


def test_dc_inverting_negative_n():
    # n=-1: V=10 -> -10; I2 = +10mA?? KCL b: Vb/1k + I2w = 0 ->
    # I2w = +0.01; I1w = -n·I2w = +0.01.
    c = ckt("tNG", V_("V1", "10 V", "a", "0"),
            T_("T1", "-1", "a", "0", "b", "0"), R_("R1", "1 kOhm", "b", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    assert dc_voltages(r)["b"] == Decimal("-10")
    assert dc_currents(r)["T1:2"] == Decimal("0.01")
    assert dc_currents(r)["T1:1"] == Decimal("0.01")


def test_dc_cascade_ratio_product():
    # n1=2 then n2=3: 10 -> 20 -> 60 (no inter-stage loading: E? no,
    # direct winding-to-winding node a shared; KCL couples — hand:
    # stage2 secondary open except R: I2w2 = -60mA?? R(out,0)=1k: 60mA
    # leaving out; I2w(T2) = -60mA; I1w(T2) = -3·(-60mA) = +180mA
    # leaving node a into T2 primary; T1 secondary must sink it:
    # I2w(T1) entering a... KCL at a: I1w(T2) leaving a + I2w(T1) leaving
    # a = 0 -> I2w(T1) = -180mA; I1w(T1) = -2·(-180mA) = +360mA;
    # KCL at s: source aux + R? V1 directly across T1 primary: source
    # delivers 360mA. Va = 10 (forced), Vb = 20, Vout = 60. Assert all.
    c = ckt("tCAS", V_("V1", "10 V", "s", "0"),
            T_("T1", "2", "s", "0", "a", "0"),
            T_("T2", "3", "a", "0", "out", "0"),
            R_("R1", "1 kOhm", "out", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    v = dc_voltages(r)
    assert v["a"] == Decimal("20")
    assert v["out"] == Decimal("60")
    assert r.conservation_checks.passed is True


def test_dc_impedance_reflection():
    # R0=100 series primary, R1=400 secondary, n=2, V=10:
    # Zin = 400/4 = 100; I = 50mA; Va = 5; Vb = 10.
    c = ckt("tRE", V_("V1", "10 V", "s", "0"), R_("R0", "100 ohm", "s", "a"),
            T_("T1", "2", "a", "0", "b", "0"), R_("R1", "400 ohm", "b", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    v = dc_voltages(r)
    assert v["a"] == Decimal("5")
    assert v["b"] == Decimal("10")
    i = dc_currents(r)
    assert i["T1:1"] == Decimal("0.05")
    assert i["T1:2"] == Decimal("-0.025")


def test_dc_open_secondary_voltage():
    # Unloaded secondary follows ratio with zero secondary current.
    c = ckt("tOS", V_("V1", "10 V", "s", "0"), R_("R0", "1 kOhm", "s", "a"),
            T_("T1", "3", "a", "0", "b", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    v = dc_voltages(r)
    # KCL a: (Va-10)/1k + I1w = 0; secondary open: I2w = 0 -> I1w = 0
    # -> Va = 10; Vb = 30.
    assert v["a"] == Decimal("10")
    assert v["b"] == Decimal("30")
    assert dc_currents(r)["T1:2"] == Decimal("0")


def test_dc_n_zero_valid():
    # n=0: Vb = 0 forced; I1w = 0 (primary open); Va follows source.
    c = ckt("tZ0", V_("V1", "10 V", "a", "0"),
            T_("T1", "0", "a", "0", "b", "0"), R_("R1", "1 kOhm", "b", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    v = dc_voltages(r)
    assert v["a"] == Decimal("10")
    assert v["b"] == Decimal("0")
    assert dc_currents(r)["T1:1"] == Decimal("0")


def test_dc_n_zero_contradictory_inconsistent():
    # 5V forced across a secondary constrained to 0V: no solution.
    c = ckt("tZX", V_("V1", "10 V", "a", "0"),
            T_("T1", "0", "a", "0", "b", "0"), V_("V2", "5 V", "b", "0"))
    assert solve_linear_dc(c).status == SolveStatus.INCONSISTENT


def test_dc_contradictory_secondary_inconsistent():
    # n=2 forces Vb=20; independent 5V across secondary contradicts.
    c = ckt("tCX", V_("V1", "10 V", "a", "0"),
            T_("T1", "2", "a", "0", "b", "0"), V_("V2", "5 V", "b", "0"))
    assert solve_linear_dc(c).status == SolveStatus.INCONSISTENT


def test_dc_bare_transformer_singular():
    # T alone (no sources, no loads): homogeneous system with free
    # winding voltages (Vb = n·Va, Va free) -> rank-deficient consistent.
    c = ckt("tSG", T_("T1", "2", "a", "0", "b", "0"))
    assert solve_linear_dc(c).status == SolveStatus.SINGULAR


def test_dc_unloaded_unique_zero():
    # R on primary only, secondary open: I2w = 0 -> I1w = 0 -> Va = 0.
    # Unique zero solution (SOLVED, not singular).
    c = ckt("tUZ", T_("T1", "2", "a", "0", "b", "0"),
            R_("R1", "1 kOhm", "a", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    assert dc_voltages(r)["a"] == Decimal("0")
    assert dc_voltages(r)["b"] == Decimal("0")


def test_dc_coexistence_eghfO():
    # T alongside E/G/H/F/O: hand nodal in Fractions via Decimals.
    # V1=10 s; R0 s-a 1k. T1 n=2 (a,0,b,0). E1(+:c,-:0, 3*(b,0)).
    # R1 c-0 1k. G1(+:d,-:0, 1mS*(a,0)). R2 d-0 1k.
    # H1(+:e,-:0, 100*R0). R3 e-0 1k. F1(+:f,-:0, 2*R0). R4 f-0 1k.
    # O1(+:a,-:g,o:g) follower of a with R5 g-0 1k.
    # Va: KCL a: (Va-10)/1k + I1w = 0. Secondary b: E draws nothing,
    # R? none on b! b connects T pin3 + E cp only -> KCL b: I2w = 0
    # -> I1w = 0 -> Va = 10. Vb = 20. Vc = 60. I(R1) = 60mA.
    # G1: J = 1mS*10V = 10mA into d; Vd = 10. I(R0) = (10-10)/1k = 0.
    # H1 = 100*0 = 0 -> Ve = 0. F1 = 2*0 = 0 -> Vf = 0 (R4: 0).
    # O1: Vg = Va = 10.
    c = ckt("tMX", V_("V1", "10 V", "s", "0"), R_("R0", "1 kOhm", "s", "a"),
            T_("T1", "2", "a", "0", "b", "0"),
            E_("E1", "3", "c", "0", "b", "0"), R_("R1", "1 kOhm", "c", "0"),
            G_("G1", "1 mS", "d", "0", "a", "0"), R_("R2", "1 kOhm", "d", "0"),
            H_("H1", "100 ohm", "e", "0", "R0"), R_("R3", "1 kOhm", "e", "0"),
            F_("F1", "2", "f", "0", "R0"), R_("R4", "1 kOhm", "f", "0"),
            O_("O1", "a", "g", "g"), R_("R5", "1 kOhm", "g", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    v = dc_voltages(r)
    assert v["a"] == Decimal("10")
    assert v["b"] == Decimal("20")
    assert v["c"] == Decimal("60")
    assert v["d"] == Decimal("10")
    assert v["e"] == Decimal("0")
    assert v["f"] == Decimal("0")
    assert v["g"] == Decimal("10")
    assert r.conservation_checks.passed is True


def test_dc_bridge_with_T():
    # Bridge with T (n=1) in one arm. Hand nodal (V, mA, kΩ): Va is the
    # s-a-0 divider 12*2/(1+2) = 8. b/c: Vc = Vb; KCL c gives
    # I2w = -Vb/1k; KCL b gives (Vb-12)/2k + I1w = 0 with I1w = -I2w
    # = +Vb/1k, i.e. (Vb-12)/2 + Vb = 0, so Vb = Vc = 4 (inside the
    # source rails, as befits a passive network).
    c = ckt("tBR", V_("V1", "12 V", "s", "0"), R_("R1", "1 kOhm", "s", "a"),
            R_("R2", "2 kOhm", "s", "b"), R_("R3", "2 kOhm", "a", "0"),
            T_("T1", "1", "b", "0", "c", "0"), R_("R4", "1 kOhm", "c", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    v = dc_voltages(r)
    assert v["a"] == Decimal("8")
    assert v["b"] == Decimal("4")
    assert v["c"] == Decimal("4")
    assert r.conservation_checks.passed is True


def _ladder_T(n, name="tLAD", ratio="1"):
    # n-section R ladder, T (n=1) buffering each shunt node to a load.
    # With ratio 1 every buffered node copies its divider node exactly.
    comps = [V_("V1", "7 V", "in", "0")]
    prev = "in"
    for i in range(1, n + 1):
        comps.append(R_(f"R{i}", "1 kOhm", prev, f"m{i}"))
        comps.append(T_(f"T{i}", ratio, f"m{i}", "0", f"o{i}", "0"))
        comps.append(R_(f"R{100 + i}", "1 kOhm", f"o{i}", "0"))
        prev = f"m{i}"
    return ckt(f"{name}{n}", *comps)


def test_dc_chain_scales():
    # n=1 buffers reflect the 1k load straight through, so the chain is
    # EXACTLY a uniform R-1k ladder (series 1k, shunt 1k). Independent
    # in-test nodal recurrence with Fractions, compared bit-exactly via
    # the same presentation rounding the engine uses.
    from academic_core.domain.engineering.mna.solver import (
        _fraction_to_decimal as _f2d)
    from fractions import Fraction as _F
    for n in (1, 2, 4, 8, 16, 32, 64):
        r = assert_dc_solved(solve_linear_dc(_ladder_T(n)))
        v = dc_voltages(r)
        # Backward: Z_k = 1k + 1/(1mS + 1/Z_{k+1}), Z_{N+1} = oo.
        inv_z_next = _F(0)  # 1/Z past the last node (open end)
        z_from_right = []
        for _ in range(n):
            y_here = _F(1, 1000) + inv_z_next
            z_here = _F(1000) + _F(1, 1) / y_here
            z_from_right.append(z_here)
            inv_z_next = _F(1, 1) / z_here
        z_from_right.reverse()  # index k-1 holds Z_k
        # Forward: V(m_k) = V(m_{k-1}) * Zpar_k/(R + Zpar_k) with
        # Zpar_k = 1/(Y + 1/Z_{k+1}), Z_{N+1} = oo.
        expect = {}
        v_prev = _F(7)
        for k in range(1, n + 1):
            z_next = z_from_right[k] if k < n else None
            y_here = _F(1, 1000) + (_F(1, 1) / z_next if z_next is not None else _F(0))
            zpar = _F(1, 1) / y_here
            v_here = v_prev * zpar / (_F(1000) + zpar)
            expect[f"m{k}"] = v_here
            v_prev = v_here
        for k in range(1, n + 1):
            assert _f2d(expect[f"m{k}"]) == v[f"m{k}"], (n, k)
            assert _f2d(expect[f"m{k}"]) == v[f"o{k}"], (n, k)
        assert r.conservation_checks.passed is True


# -- AC (same stamp, complex arithmetic) ------------------------------------------

def _ac_voltages(res):
    return {n.node: (n.phasor.re, n.phasor.im) for n in res.node_voltages}


def test_ac_step_up_exact():
    # R-only + axis phases + T -> EXACT Fractions, no HP fallback.
    c = ckt("tAC", V_("V1", "10 V", "a", "0"),
            T_("T1", "2", "a", "0", "b", "0"), R_("R1", "1 kOhm", "b", "0"))
    r = ac_solved(c)
    assert r.numeric_mode.value == "exact"
    v = _ac_voltages(r)
    assert v["b"] == (Fraction(20), Fraction(0))
    i = {b.ref: (b.current.re, b.current.im) for b in r.branch_currents}
    assert i["T1:1"] == (Fraction(1, 25), Fraction(0))
    assert i["T1:2"] == (Fraction(-1, 50), Fraction(0))


def test_ac_lc_hp_cmath():
    # T + series L + shunt C at 1 kHz: independent cmath oracle.
    import cmath
    c = ckt("tLC", V_("V1", "10 V", "s", "0"), R_("R0", "100 ohm", "s", "a"),
            L_("L1", "10 mH", "a", "m"), T_("T1", "2", "m", "0", "b", "0"),
            C_("C1", "1 uF", "b", "0"))
    r = ac_solved(c)
    assert r.numeric_mode.value == "high_precision"
    w = 2 * cmath.pi * 1000.0
    zl, zc = complex(0, w * 0.01), complex(0, -1 / (w * 1e-6))
    # Nodal by hand: unknowns Va, Vm, Vb, I1w, I2w.
    # KCL s: source; KCL a: (Va-10)/100 + (Va-Vm)/zl = 0;
    # KCL m: (Vm-Va)/zl + I1w = 0; KCL b: Vb/zc + I2w = 0;
    # Vb = 2*Vm; I1w = -2*I2w. From b: Vb/zc + I2w = 0.
    # I1w = -2*I2w = 2*Vb/zc... solve: let Vb = v.
    # Vm = v/2. KCL m: (v/2-Va)/zl + I1w = 0; I1w = -2*I2w = 2*v/zc.
    # KCL a: (Va-10)/100 + (Va-v/2)/zl = 0.
    # From m: Va = v/2 + zl*2*v/zc... Va = v*(1/2 + 2*zl/zc).
    # Into a: (v*(1/2+2*zl/zc) - 10)/100 + (v*(1/2+2*zl/zc) - v/2)/zl = 0
    # -> v*((1/2+2*zl/zc)/100 + (2*zl/zc)/zl) = 10/100
    # -> v = 0.1/((1/2+2*zl/zc)/100 + 2/zc).
    v_ref = 0.1 / ((0.5 + 2 * zl / zc) / 100 + 2 / zc)
    got = _ac_voltages(r)
    got_b = complex(float(got["b"][0]), float(got["b"][1]))
    assert abs(got_b - v_ref) / abs(v_ref) <= 1e-9
    assert r.kcl_max_residual is not None


def test_ac_chain_scales():
    # R-only + axis phases -> EXACT; AC phasors must equal DC values to
    # presentation precision (DC node voltages are 28-digit presentation
    # Decimals of the same exact rationals; 1E-25 documents that layer).
    for n in (1, 2, 4, 8, 16):
        c = _ladder_T(n)
        r = ac_solved(c, "1 kHz")
        assert r.numeric_mode.value == "exact"
        d = assert_dc_solved(solve_linear_dc(c))
        dv = dc_voltages(d)
        for i in range(1, n + 1):
            ph = _ac_voltages(r)[f"m{i}"]
            assert abs(Decimal(ph[0].numerator) / Decimal(ph[0].denominator)
                       - dv[f"m{i}"]) <= Decimal("1E-25"), (n, i)
            assert ph[1] == Fraction(0)


def test_ac_coexistence_eghfO_hp():
    # T + E/G/H/F/O + L/C at 1 kHz: SOLVED + conservation within bound.
    c = ckt("tAH", V_("V1", "10 V", "s", "0"), R_("R0", "100 ohm", "s", "a"),
            T_("T1", "2", "a", "0", "b", "0"),
            E_("E1", "2", "c", "0", "b", "0"), R_("R1", "1 kOhm", "c", "0"),
            G_("G1", "1 mS", "d", "0", "a", "0"), R_("R2", "1 kOhm", "d", "0"),
            O_("O1", "a", "e", "e"), R_("R3", "1 kOhm", "e", "0"),
            L_("L1", "5 mH", "e", "f"), C_("C1", "2 uF", "f", "0"))
    r = ac_solved(c)
    from academic_core.domain.engineering.ac.power import analyze_power
    p = analyze_power(r)
    assert p.conservation.passed is True, p.conservation.diagnostics


def test_ac_n_zero_and_negative():
    for n, tag in (("0", "zero"), ("-3", "neg")):
        c = ckt(f"tA{tag}", V_("V1", "10 V", "a", "0"),
                T_("T1", n, "a", "0", "b", "0"), R_("R1", "1 kOhm", "b", "0"))
        r = ac_solved(c)
        assert r.numeric_mode.value == "exact"


def _rc_series_shunt():
    # Port1 (a,0), port2 (b,0): R1 a-b 1k series, R2 b-0 1k shunt.
    return ckt("tSS", R_("R1", "1 kOhm", "a", "b"), R_("R2", "1 kOhm", "b", "0"),
               V_("V9", "0 V", "z", "0"))


def _ports_ab():
    from academic_core.domain.engineering.ac.impedance import PortDefinition
    return PortDefinition("a", "0"), PortDefinition("b", "0")


def _vals(m):
    return {(r, c): (getattr(m, f"a{r + 1}{c + 1}").category.value,
                     getattr(m, f"a{r + 1}{c + 1}").value)
            for r in (0, 1) for c in (0, 1)}


# -- two-port Z ------------------------------------------------------------------

def test_z_series_shunt_exact():
    # Hand nodal (cond A: 1A into a, b open): Va=2000, Vb=1000.
    # Cond B (1A into b, a open): Va=Vb=1000.
    # Z = [[2000,1000],[1000,1000]]; reciprocal (passive R net).
    from academic_core.domain.engineering.ac.impedance import PortDefinition
    p1, p2 = PortDefinition("a", "0"), PortDefinition("b", "0")
    z = z_parameters(_rc_series_shunt(), p1, p2, "1 kHz")
    got = _vals(z)
    assert got[(0, 0)] == ("finite", RationalComplex(Fraction(2000), Fraction(0)))
    assert got[(0, 1)] == ("finite", RationalComplex(Fraction(1000), Fraction(0)))
    assert got[(1, 0)] == ("finite", RationalComplex(Fraction(1000), Fraction(0)))
    assert got[(1, 1)] == ("finite", RationalComplex(Fraction(1000), Fraction(0)))
    assert z.a12.value == z.a21.value  # reciprocity, not assumed by engine
    assert z.provenance["engine"] == "f8g-twoport/1.0"
    assert "timestamp" not in z.provenance


def test_z_cramer_crosscheck():
    # Independent 2x2 Cramer on cond-A nodal equations (Fractions):
    # [[1,-1],[-1,2]]·[Va,Vb] = [1000,0] (V, mA, kΩ units).
    from academic_core.domain.engineering.ac.impedance import PortDefinition
    det = Fraction(1) * Fraction(2) - Fraction(-1) * Fraction(-1)
    assert det == Fraction(1)
    va = (Fraction(1000) * Fraction(2) - Fraction(-1) * Fraction(0)) / det
    vb = (Fraction(1) * Fraction(0) - Fraction(-1) * Fraction(1000)) / det
    assert (va, vb) == (Fraction(2000), Fraction(1000))
    p1, p2 = PortDefinition("a", "0"), PortDefinition("b", "0")
    z = z_parameters(_rc_series_shunt(), p1, p2, "1 kHz")
    assert z.a11.value.re == va and z.a21.value.re == vb


def test_z_transformer_loaded_exact():
    # n=2, R=1k secondary: reflection R/n^2 -> [[250,500],[500,1000]].
    from academic_core.domain.engineering.ac.impedance import PortDefinition
    c = ckt("tZ", T_("T1", "2", "a", "0", "b", "0"), R_("R1", "1 kOhm", "b", "0"),
            V_("V9", "0 V", "z", "0"))
    p1, p2 = PortDefinition("a", "0"), PortDefinition("b", "0")
    z = z_parameters(c, p1, p2, "1 kHz")
    got = {k: v.value.re for k, v in
           (("11", z.a11), ("12", z.a12), ("21", z.a21), ("22", z.a22))}
    assert got == {"11": Fraction(250), "12": Fraction(500),
                   "21": Fraction(500), "22": Fraction(1000)}
    for e in (z.a11, z.a12, z.a21, z.a22):
        assert e.category.value == "finite" and e.value.im == Fraction(0)


def test_z_bare_transformer_undefined():
    # Open windings admit no test current: INCONSISTENT solves ->
    # UNDEFINED entries carrying solver status, never invented values.
    from academic_core.domain.engineering.ac.impedance import PortDefinition
    c = ckt("tZB", T_("T1", "2", "a", "0", "b", "0"),
            V_("V9", "0 V", "z", "0"))
    p1, p2 = PortDefinition("a", "0"), PortDefinition("b", "0")
    z = z_parameters(c, p1, p2, "1 kHz")
    for e in (z.a11, z.a12, z.a21, z.a22):
        assert e.category.value == "undefined"
        assert e.value is None
    assert any("inconsistent" in d.lower() for d in z.diagnostics)


def test_z_degenerate_port_rejected():
    from academic_core.domain.engineering.ac.impedance import PortDefinition
    from academic_core.domain.engineering.ac.twoport import TwoPortError
    c = _rc_series_shunt()
    with pytest.raises(Exception):
        PortDefinition("a", "a")
    with pytest.raises(TwoPortError):
        z_parameters(c, PortDefinition("a", "zz"), PortDefinition("b", "0"), "1 kHz")


def test_z_nongnd_ports():
    # Ports (a,b) and (c,0) share no net: single-source extraction valid.
    # Hand, cond A (1A across a-b, + at a), amps/ohms/volts:
    # KCL a: 1 = (Va-Vb)/1000, so Va-Vb = 1000 = z11.
    # KCL b: (Vb-Va)/1000 + (Vb-Vc)/2000 + 1 = 0 (test returns via b),
    #   i.e. -1 + (Vb-Vc)/2000 + 1 = 0, so Vb = Vc.
    # KCL c: (Vc-Vb)/2000 + Vc/3000 = 0, giving Vc = Vb = 0, Va = 1000.
    # z21 = Vc-0 = 0 (ZERO: differential drive cannot reach c here).
    # Cond B (1A into c, port1 open): KCL a: (Va-Vb)/1000 = 0;
    # KCL b: (Vb-Va)/1000 + (Vb-Vc)/2000 = 0; KCL c: 1 = rest.
    # From a/b: Va = Vb = Vc; into c: 1 = Vc/3000, so Vc = 3000 = z22;
    # z12 = Va-Vb = 0.
    from academic_core.domain.engineering.ac.impedance import PortDefinition
    c = ckt("tZng", V_("V9", "0 V", "z", "0"),
            R_("R1", "1 kOhm", "a", "b"), R_("R2", "2 kOhm", "b", "c"),
            R_("R3", "3 kOhm", "c", "0"))
    p1, p2 = PortDefinition("a", "b"), PortDefinition("c", "0")
    z = z_parameters(c, p1, p2, "1 kHz")
    assert z.a11.value.re == Fraction(1000)
    assert z.a21.value.re == Fraction(0)
    assert z.a21.category.value == "zero"
    assert z.a22.value.re == Fraction(3000)
    assert z.a12.value.re == Fraction(0)


def test_shared_non_ground_net_rejected():
    # Ports (a,b)+(b,c) share net b: the drive return would violate the
    # other port's boundary condition -> explicit TwoPortError.
    from academic_core.domain.engineering.ac.impedance import PortDefinition
    from academic_core.domain.engineering.ac.twoport import TwoPortError
    c = ckt("tSH", V_("V9", "0 V", "z", "0"),
            R_("R1", "1 kOhm", "a", "b"), R_("R2", "2 kOhm", "b", "c"),
            R_("R3", "3 kOhm", "c", "0"))
    with pytest.raises(TwoPortError):
        z_parameters(c, PortDefinition("a", "b"), PortDefinition("b", "c"),
                     "1 kHz")
    with pytest.raises(TwoPortError):
        y_parameters(c, PortDefinition("a", "b"), PortDefinition("b", "c"),
                     "1 kHz")


# -- two-port Y ------------------------------------------------------------------

def test_y_series_shunt_exact_and_inverse():
    # Hand (cond C: 1A into a, 0V across b): Va=1000 (KCL a: 1=(Va-0)/1k);
    # I2 entering b: R1 leaving b->a = (0-1000)/1k = -1A, R2 0, so the
    # short carries +1A leaving b; entering = -1A. y11 = 1/1000 S,
    # y21 = -1/1000 S. Cond D (1A into b, a shorted): symmetric with
    # R1+R2 divider: KCL b: 1 = Vb/1k + Vb/1k -> Vb = 500; y22 = 1/500 S.
    # I1 entering a: KCL a: R1 leaving (0-500)/1k = -0.5A + short 0.5A
    # leaving -> entering = -0.5A; y12 = -0.5/500 = -1/1000 S.
    # Y = [[1,-1],[-1,2]] mS = Z^-1 with Z=[[2000,1000],[1000,1000]]:
    # det = 1e6; [[1000,-1000],[-1000,2000]]/1e6. Cross-check in-test.
    from academic_core.domain.engineering.ac.impedance import PortDefinition
    p1, p2 = PortDefinition("a", "0"), PortDefinition("b", "0")
    y = y_parameters(_rc_series_shunt(), p1, p2, "1 kHz")
    assert y.a11.value.re == Fraction(1, 1000)
    assert y.a12.value.re == Fraction(-1, 1000)
    assert y.a21.value.re == Fraction(-1, 1000)
    assert y.a22.value.re == Fraction(1, 500)
    assert all(e.category.value == "finite" for e in
               (y.a11, y.a12, y.a21, y.a22))
    assert all(e.unit == "S" for e in (y.a11, y.a12, y.a21, y.a22))
    # Independent cross-check: Y == Z^-1 elementwise (Fractions).
    z11, z12, z21, z22 = (Fraction(2000), Fraction(1000),
                          Fraction(1000), Fraction(1000))
    det = z11 * z22 - z12 * z21
    assert det == Fraction(1000000)
    assert y.a11.value.re == z22 / det
    assert y.a12.value.re == -z12 / det
    assert y.a21.value.re == -z21 / det
    assert y.a22.value.re == z11 / det


def test_y_transformer_loaded_all_infinite():
    # Shorted secondary reflects a short: 1/V with V=0 -> INFINITE.
    from academic_core.domain.engineering.ac.impedance import PortDefinition
    c = ckt("tY", T_("T1", "2", "a", "0", "b", "0"), R_("R1", "1 kOhm", "b", "0"),
            V_("V9", "0 V", "z", "0"))
    p1, p2 = PortDefinition("a", "0"), PortDefinition("b", "0")
    y = y_parameters(c, p1, p2, "1 kHz")
    for e in (y.a11, y.a12, y.a21, y.a22):
        assert e.category.value == "infinite"
        assert e.value is None


# -- two-port h ------------------------------------------------------------------

def test_h_series_shunt_exact():
    # h11 = V1/I1|V2=0 = 1000 (cond C above); h21 = I2/I1 = -1;
    # h12 = V1/V2|I1=0 = 1000/1000 = 1 (cond B); h22 = I2/V2 = 1/1000.
    # Cross-check vs Z: h11 = det/z22, h12 = z12/z22, h21 = -z21/z22,
    # h22 = 1/z22 with det = 1e6.
    from academic_core.domain.engineering.ac.impedance import PortDefinition
    p1, p2 = PortDefinition("a", "0"), PortDefinition("b", "0")
    h = h_parameters(_rc_series_shunt(), p1, p2, "1 kHz")
    assert h.a11.value.re == Fraction(1000)
    assert h.a12.value.re == Fraction(1)
    assert h.a21.value.re == Fraction(-1)
    assert h.a22.value.re == Fraction(1, 1000)
    assert [e.unit for e in (h.a11, h.a12, h.a21, h.a22)] == ["Ω", "1", "1", "S"]
    z11, z12, z21, z22 = (Fraction(2000), Fraction(1000),
                          Fraction(1000), Fraction(1000))
    det = z11 * z22 - z12 * z21
    assert h.a11.value.re == det / z22
    assert h.a12.value.re == z12 / z22
    assert h.a21.value.re == -z21 / z22
    assert h.a22.value.re == Fraction(1) / z22


def test_h_transformer_loaded():
    # n=2, R=1k: h11 = 0 ZERO (V1=0 under shorted secondary... verify:
    # cond C drives port1 1A with port2 shorted: Vb=0 -> Va = Vb/2 = 0,
    # so h11 = 0/1 = 0); h21 = I2/I1 = -1/2 (I2 entering b = -0.5A:
    # KCL b: R 0 + winding I2w + short: I2w = -I1w/2 = -0.5; short
    # leaving +0.5, entering -0.5); h12 = 1/2, h22 = 1/1000 (cond B:
    # drive b open-port-1: V2 = 1000 (R carries the 1A, windings 0).
    from academic_core.domain.engineering.ac.impedance import PortDefinition
    c = ckt("tH", T_("T1", "2", "a", "0", "b", "0"), R_("R1", "1 kOhm", "b", "0"),
            V_("V9", "0 V", "z", "0"))
    p1, p2 = PortDefinition("a", "0"), PortDefinition("b", "0")
    h = h_parameters(c, p1, p2, "1 kHz")
    assert h.a11.value.re == Fraction(0) and h.a11.category.value == "zero"
    assert h.a12.value.re == Fraction(1, 2)
    assert h.a21.value.re == Fraction(-1, 2)
    assert h.a22.value.re == Fraction(1, 1000)


# -- two-port g ------------------------------------------------------------------

def test_g_series_shunt_exact():
    # g11 = 1/V1A = 1/2000; g21 = V2A/V1A = 1/2; g12 = I1D = -1/2
    # (cond D: short a, drive b 1A: Vb = 500; KCL a gives short
    # leaving +0.5A, entering -0.5A); g22 = V2D = 500.
    # Cross-check vs Z: g11 = 1/z11, g21 = z21/z11, g12 = -z12/z11,
    # g22 = det/z11.
    from academic_core.domain.engineering.ac.impedance import PortDefinition
    p1, p2 = PortDefinition("a", "0"), PortDefinition("b", "0")
    g = g_parameters(_rc_series_shunt(), p1, p2, "1 kHz")
    assert g.a11.value.re == Fraction(1, 2000)
    assert g.a12.value.re == Fraction(-1, 2)
    assert g.a21.value.re == Fraction(1, 2)
    assert g.a22.value.re == Fraction(500)
    assert [e.unit for e in (g.a11, g.a12, g.a21, g.a22)] == ["S", "1", "1", "Ω"]
    z11, z12, z21, z22 = (Fraction(2000), Fraction(1000),
                          Fraction(1000), Fraction(1000))
    det = z11 * z22 - z12 * z21
    assert g.a11.value.re == Fraction(1) / z11
    assert g.a12.value.re == -z12 / z11
    assert g.a21.value.re == z21 / z11
    assert g.a22.value.re == det / z11


def test_g_transformer_loaded():
    # n=2, R=1k: g11 = 1/250 S; g21 = 500/250 = 2; cond D (short a,
    # drive b 1A): Va=0 -> Vb=0 -> R carries 0; I2w free? KCL b:
    # 1A in = I2w leaving; I1w = -2·I2w = -2A; KCL a: short + I1w = 0
    # -> short leaving +2A, entering -2A = I1D. g12 = -2/1 = -2;
    # g22 = V2/I2 = 0/1 = 0 ZERO.
    from academic_core.domain.engineering.ac.impedance import PortDefinition
    c = ckt("tG", T_("T1", "2", "a", "0", "b", "0"), R_("R1", "1 kOhm", "b", "0"),
            V_("V9", "0 V", "z", "0"))
    p1, p2 = PortDefinition("a", "0"), PortDefinition("b", "0")
    g = g_parameters(c, p1, p2, "1 kHz")
    assert g.a11.value.re == Fraction(1, 250)
    assert g.a12.value.re == Fraction(-2)
    assert g.a21.value.re == Fraction(2)
    assert g.a22.value.re == Fraction(0) and g.a22.category.value == "zero"


# -- two-port ABCD (mandatory vectors, external derivations) ---------------------

def _t_loaded(n, r="1 kOhm", tag="tABCD"):
    return ckt(tag, T_("T1", n, "a", "0", "b", "0"), R_("R1", r, "b", "0"),
               V_("V9", "0 V", "z", "0"))


def test_abcd_n2_vector():
    # n=2, R=1k: cond A gives V1=250, V2=500 (I1=1A); cond C (drive a
    # 1A, short b): V1=V2=0, I2 entering b = -0.5A (KCL b: R 0 +
    # I2w + short: I2w = -I1w/2 = -0.5 leaving; short leaving +0.5,
    # entering -0.5). Hence A = 250/500 = 1/2; B = -0/(-0.5) = 0 ZERO;
    # C = 1/500 S; D = -1/(-0.5) = 2. Textbook ideal-T ABCD.
    from academic_core.domain.engineering.ac.impedance import PortDefinition
    p1, p2 = PortDefinition("a", "0"), PortDefinition("b", "0")
    m = abcd_parameters(_t_loaded("2"), p1, p2, "1 kHz")
    assert m.a11.value.re == Fraction(1, 2)
    assert m.a12.value.re == Fraction(0) and m.a12.category.value == "zero"
    assert m.a21.value.re == Fraction(1, 500)
    assert m.a22.value.re == Fraction(2)
    assert [e.unit for e in (m.a11, m.a12, m.a21, m.a22)] == ["1", "Ω", "S", "1"]


def test_abcd_n_half_vector():
    # n=1/2, R=1k: reflection R/n^2 = 4k. Cond A: V1 = 4000, V2 = 2000.
    # Cond C: V1 = V2 = 0; I2w: KCL b: 0 + I2w + short = 0; primary:
    # KCL a: 1A in = I1w; I1w = -n·I2w = -I2w/2 -> I2w = -2A leaving b;
    # short leaving +2A, entering -2A = I2C. B = -0/-2 = 0; D = 2.
    from academic_core.domain.engineering.ac.impedance import PortDefinition
    p1, p2 = PortDefinition("a", "0"), PortDefinition("b", "0")
    m = abcd_parameters(_t_loaded("0.5", tag="tABCh"), p1, p2, "1 kHz")
    assert m.a11.value.re == Fraction(2)
    assert m.a12.value.re == Fraction(0) and m.a12.category.value == "zero"
    assert m.a21.value.re == Fraction(1, 2000)
    assert m.a22.value.re == Fraction(1, 2)


def test_abcd_n_negative_vector():
    # n=-1, R=1k: cond A: I1w=1A; I2w = -1/(-1) = +1A?? constraint
    # I1w + n·I2w = 0 -> 1 - I2w = 0 -> I2w = +1 (leaving b).
    # KCL b: V2/1k + 1 = 0 -> V2 = -1000. V1 = V2/n = +1000.
    # A = 1000/-1000 = -1. C = 1/-1000 S. Cond C: V1=V2=0;
    # KCL b: 0 + 1 + short = 0 -> short leaving -1A, entering +1A = I2C.
    # B = 0; D = -1/+1 = -1.
    from academic_core.domain.engineering.ac.impedance import PortDefinition
    p1, p2 = PortDefinition("a", "0"), PortDefinition("b", "0")
    m = abcd_parameters(_t_loaded("-1", tag="tABCn"), p1, p2, "1 kHz")
    assert m.a11.value.re == Fraction(-1)
    assert m.a12.value.re == Fraction(0) and m.a12.category.value == "zero"
    assert m.a21.value.re == Fraction(-1, 1000)
    assert m.a22.value.re == Fraction(-1)


def test_abcd_series_shunt():
    # [[2,1000],[1/1000,1]] by direct cond-A/cond-C solves above.
    from academic_core.domain.engineering.ac.impedance import PortDefinition
    p1, p2 = PortDefinition("a", "0"), PortDefinition("b", "0")
    m = abcd_parameters(_rc_series_shunt(), p1, p2, "1 kHz")
    assert m.a11.value.re == Fraction(2)
    assert m.a12.value.re == Fraction(1000)
    assert m.a21.value.re == Fraction(1, 1000)
    assert m.a22.value.re == Fraction(1)


def test_abcd_sign_convention_explicit():
    # The -I2 convention pinned down: with I2 entering port 2 in cond C
    # measured negative (-0.5A), B = -V1/I2 and D = -1/I2 must come out
    # +0 and +2 (not negated the other way). Any sign flip in the
    # implementation breaks this test while keeping magnitudes right.
    from academic_core.domain.engineering.ac.impedance import PortDefinition
    p1, p2 = PortDefinition("a", "0"), PortDefinition("b", "0")
    m = abcd_parameters(_t_loaded("2", tag="tABCs"), p1, p2, "1 kHz")
    assert m.a12.value.re == Fraction(0)  # -0/+... exactly zero, not -0
    assert m.a22.value.re == Fraction(2)  # -1/(-0.5), not -2
    assert m.a12.category.value == "zero"


# -- D5 transfer / impedance with T --------------------------------------------------

def test_d5_transfer_hv_through_T():
    # V1=10 s; R0 s-a 100; T1 n=2 (a,0,b,0); R1 b-0 900.
    # Zin = 900/4 = 225; I = 10/325 = 2/65 A; Va = 10-200/65 = 450/65;
    # Vb = 900/65. Hv = Vb/Vin = 90/65 = 18/13.
    from academic_core.domain.engineering.ac.impedance import PortDefinition
    c = ckt("tTR", V_("V1", "10 V", "s", "0"), R_("R0", "100 ohm", "s", "a"),
            T_("T1", "2", "a", "0", "b", "0"), R_("R1", "900 ohm", "b", "0"))
    d = ResponseDefinition("transfer", (voltage_between("s", "0"),
                                       voltage_between("b", "0"), "V1"))
    sw = frequency_response(c, d, ["1 kHz"])
    h = sw.points[0].value.require_defined()
    assert h.re == Fraction(18, 13) and h.im == Fraction(0)


def test_d5_port_impedance_reflection():
    # Test-source method: equivalent Z at primary = R/n^2 = 250 exact.
    # (Direct operating-point ratio needs an excited network; the bare
    # deck above is undriven, honestly 0/0 -> UNDEFINED. Both covered.)
    from academic_core.domain.engineering.ac.impedance import (
        PortDefinition, measure_port, METHOD_TEST, METHOD_DIRECT)
    from academic_core.domain.engineering.ac.problem import build_ac_problem
    from academic_core.domain.engineering.ac.operating_point import ACOperatingPoint
    from academic_core.domain.engineering.ac.topology import reference_net
    from academic_core.domain.engineering.math.linsolve.problem import NumericMode
    c = ckt("tPZ", T_("T1", "2", "a", "0", "b", "0"),
            R_("R1", "1 kOhm", "b", "0"), V_("V9", "0 V", "z", "0"))
    op = ACOperatingPoint.from_frequency(Q("1 kHz"), reference_net(c.nets))
    prob = build_ac_problem(c, op, NumericMode.AUTO)
    sol = solve_ac(c, "1 kHz")
    z = measure_port(prob, sol, PortDefinition("a", "0"), quantity="impedance",
                     method=METHOD_TEST)
    assert z.category == ImpedanceCategory.FINITE
    assert z.value.re == Fraction(250) and z.value.im == Fraction(0)
    d = measure_port(prob, sol, PortDefinition("a", "0"), quantity="impedance",
                     method=METHOD_DIRECT)
    assert d.category == ImpedanceCategory.UNDEFINED and d.value is None


def test_d5_direct_operating_ratio_driven():
    # Driven network: direct method reads the winding operating ratio.
    # V1=10 s; R0 s-a 100; T1 n=2 (a,0,b,0); R1 b-0 400.
    # Hand: Va=5, I1w = 50mA -> V/I = 100 (winding operating ratio,
    # NOT the equivalent impedance 250 — different question, labeled).
    from academic_core.domain.engineering.ac.impedance import (
        PortDefinition, measure_port, METHOD_DIRECT)
    from academic_core.domain.engineering.ac.problem import build_ac_problem
    from academic_core.domain.engineering.ac.operating_point import ACOperatingPoint
    from academic_core.domain.engineering.ac.topology import reference_net
    from academic_core.domain.engineering.math.linsolve.problem import NumericMode
    c = ckt("tPD", V_("V1", "10 V", "s", "0"), R_("R0", "100 ohm", "s", "a"),
            T_("T1", "2", "a", "0", "b", "0"), R_("R1", "400 ohm", "b", "0"))
    op = ACOperatingPoint.from_frequency(Q("1 kHz"), reference_net(c.nets))
    prob = build_ac_problem(c, op, NumericMode.AUTO)
    sol = solve_ac(c, "1 kHz")
    z = measure_port(prob, sol, PortDefinition("a", "0"), quantity="impedance",
                     method=METHOD_DIRECT)
    assert z.category == ImpedanceCategory.FINITE
    assert z.value.re == Fraction(100) and z.value.im == Fraction(0)


def test_d5_frequency_response_with_T():
    c = ckt("tFR", V_("V1", "10 V", "s", "0"), R_("R0", "100 ohm", "s", "a"),
            T_("T1", "2", "a", "0", "b", "0"), R_("R1", "900 ohm", "b", "0"))
    d = ResponseDefinition("transfer", (voltage_between("s", "0"),
                                       voltage_between("b", "0"), "V1"))
    sw = frequency_response(c, d, ["100 Hz", "1 kHz", "10 kHz"])
    assert sw.status == "completed"
    for p in sw.points:
        h = p.value.require_defined()
        assert h.re == Fraction(18, 13) and h.im == Fraction(0)


# -- F8-C Thevenin/Norton with T -------------------------------------------------------

def test_f8c_vth_rth_loaded_reflection():
    # V1=10 s; R0 s-a 100; T1 n=2 (a,0,b,0); R1 b-0 400; port (b,0).
    # Hand: Va=5, Vb=10 -> Vth = 10. Deactivated + 1A into b:
    # Va=100, Vb=200 -> Rth = 200 = (100*4)||400.
    t = analyze_thevenin(ckt("tTH", V_("V1", "10 V", "s", "0"),
                             R_("R0", "100 ohm", "s", "a"),
                             T_("T1", "2", "a", "0", "b", "0"),
                             R_("R1", "400 ohm", "b", "0")),
                         TheveninPort("b", "0"))
    assert t.status in (EquivalentStatus.SOLVED, EquivalentStatus.VERIFIED), t.diagnostics
    assert Fraction(t.v_th.to_base()) == Fraction(10)
    assert Fraction(t.r_th.to_base()) == Fraction(200)


def test_f8c_negative_rth_with_T():
    # Port (p,0); T1 n=2 (1:p,2:0,3:q,4:0); R1(q,0) 1k;
    # G1(+:q,-:0, 2mS*(q,0)). Secondary Y = 1mS-2mS = -1mS -> -1k;
    # R0(s,p) 1k to mix: total Rth = 1k || ... full hand derivation:
    # Vth = -10/3 V, Rth = -1000/3 ohm, In = +10 mA, Vth/Rth = In.
    # KCL p (live): (Vp-10)/1k + I1w = 0. KCL q: Vq/1k - 0.002*Vq + I2w
    # = 0. Vq = 2Vp; I1w = -2*I2w. From q: -Vp/1000 + I2w = 0.
    # From p with I1w = -2Vp/1000: (Vp-10)/1000 - Vp/500 = 0 ->
    # Vp - 10 - 2Vp = 0 -> Vp = -10. WAIT recompute: I2w = Vp/1000?
    # -Vq/1000 + I2w = 0 -> I2w = Vq/1000 = 2Vp/1000 = Vp/500.
    # I1w = -2*Vp/500 = -Vp/250. KCL p: (Vp-10)/1000 - Vp/250 = 0 ->
    # Vp - 10 - 4Vp = 0 -> -3Vp = 10 -> Vp = -10/3. Vth = -10/3.
    # Rth: deactivate (short s): test 1A into p: KCL p: Vp/1k + I1w - 1
    # = 0 (test enters p); KCL q: Vq/1k - 0.002Vq + I2w = 0 ->
    # -Vq/1000 + I2w = 0 -> I2w = Vq/1000 = Vp/500; I1w = -Vp/250.
    # Into p: Vp/1000 - Vp/250 - 1 = 0 -> -3Vp/1000 = 1 -> Vp = -1000/3.
    # Rth = -1000/3. Isc (short p): KCL p: (0-10)/1k + I1w + Isc = 0;
    # secondary: Vq = 0 -> J = 0, R1: 0, I2w = 0 -> I1w = 0 ->
    # Isc = +10mA leaving p. Vth/Rth = (-10/3)/(-1000/3) = 10mA. HOLDS.
    c = ckt("tNR", V_("V1", "10 V", "s", "0"), R_("R0", "1 kOhm", "s", "p"),
            T_("T1", "2", "p", "0", "q", "0"), R_("R1", "1 kOhm", "q", "0"),
            G_("G1", "2 mS", "q", "0", "q", "0"))
    t = analyze_thevenin(c, TheveninPort("p", "0"))
    assert t.status in (EquivalentStatus.SOLVED, EquivalentStatus.VERIFIED), t.diagnostics
    # Exact engine fields (display Quantities round repeating decimals).
    assert t._v_th_exact == Fraction(-10, 3)
    assert t._r_th_exact == Fraction(-1000, 3)
    n = analyze_norton(c, TheveninPort("p", "0"))
    assert n.status in (EquivalentStatus.SOLVED, EquivalentStatus.VERIFIED), n.diagnostics
    assert n._i_n_exact == Fraction(1, 100)
    assert t._v_th_exact / t._r_th_exact == n._i_n_exact


def test_f8c_zero_rth_port_across_source_with_T():
    # Port coinciding with the drive: Rth = 0 even with T present.
    c = ckt("tZR", V_("V1", "10 V", "s", "0"),
            T_("T1", "2", "s", "0", "b", "0"), R_("R1", "1 kOhm", "b", "0"))
    t = analyze_thevenin(c, TheveninPort("s", "0"))
    assert t.status in (EquivalentStatus.SOLVED, EquivalentStatus.VERIFIED), t.diagnostics
    assert Fraction(t.v_th.to_base()) == Fraction(10)
    assert t.resistance_kind == ResistanceKind.ZERO


def test_f8c_nongnd_port_with_T():
    # Port (a,b): Vth = Va-Vb = 10/3-20/3 = -10/3; Rth = 1000/3 (derived
    # in analysis: deactivated, 1A differential drive gives Vp = -1000/3
    # for the analogous single-ended topology; differential port across
    # the two windings reads the same ratio by linearity).
    c = ckt("tNG", V_("V1", "10 V", "s", "0"), R_("R0", "1 kOhm", "s", "a"),
            T_("T1", "2", "a", "0", "b", "0"), R_("R1", "1 kOhm", "b", "0"))
    # Hand, live: KCL a: (Va-10)/1k + I1w = 0; KCL b: Vb/1k + I2w = 0;
    # Vb = 2Va; I1w = -2I2w. From b: 2Va/1k + I2w = 0 -> I2w = -Va/500;
    # I1w = Va/250. Into a: (Va-10)/1k + Va/250 = 0 -> 5Va = 10 ->
    # Va = 2, Vb = 4. Vth(a,b) = -2.
    # Rth: F8-C uses Vtest = 1V across (a,b). Deactivated (short s).
    # Unknowns Va,Vb,I1w,I2w,It (It = internal test current b->a).
    # Test: Va-Vb = 1. KCL a (mA): Va/1 + I1w - It = 0.
    # KCL b: Vb/1 + I2w + It = 0. Constraints: Vb = 2Va; I1w = -2I2w.
    # From test+constraint: Va - 2Va = 1 -> Va = -1, Vb = -2.
    # Into b: -2 + I2w + It = 0; into a with I1w = -2I2w: -1 - 2I2w - It
    # = 0... solving: It = 5mA internal (b->a), i.e. +5mA delivered
    # into A. Rth = 1V/5mA = 200 ohm.
    t = analyze_thevenin(c, TheveninPort("a", "b"))
    assert t.status in (EquivalentStatus.SOLVED, EquivalentStatus.VERIFIED), t.diagnostics
    assert Fraction(t.v_th.to_base()) == Fraction(-2)
    assert Fraction(t.r_th.to_base()) == Fraction(200)


def test_f8c_T_with_O_follower_drive():
    # Follower buffers the source in front of the transformer port.
    # V1=10 -> follower out 10 -> T n=2 -> Vb = 20 (R loaded).
    c = ckt("tOF", V_("V1", "10 V", "s", "0"), O_("O1", "s", "m", "m"),
            R_("R9", "1 kOhm", "m", "0"), T_("T1", "2", "m", "0", "b", "0"),
            R_("R1", "1 kOhm", "b", "0"))
    t = analyze_thevenin(c, TheveninPort("b", "0"))
    assert t.status in (EquivalentStatus.SOLVED, EquivalentStatus.VERIFIED), t.diagnostics
    assert Fraction(t.v_th.to_base()) == Fraction(20)


# -- netlist roundtrip (no format change) ------------------------------------------

def test_netlist_T_roundtrip():
    c = ckt("tNL", V_("V1", "10 V", "a", "0"),
            T_("T1", "2", "a", "0", "b", "0"), R_("R1", "1 kOhm", "b", "0"))
    nl = c.to_netlist()
    assert "T1 a 0 b 0 2" in nl
    back = Circuit.from_netlist(nl, name="tNL")
    t1 = next(x for x in back.components if x.ref == "T1")
    assert t1.type == "T"
    assert t1.pins == {"1": "a", "2": "0", "3": "b", "4": "0"}
    assert t1.value.to_base() == Decimal("2")
    assert dict(t1.parameters) == {}
    assert back.to_netlist() == nl
    # Solved identically after roundtrip.
    r = assert_dc_solved(solve_linear_dc(back))
    assert dc_voltages(r)["b"] == Decimal("20")


def test_netlist_fractional_n_roundtrip():
    c = ckt("tNLf", T_("T1", "0.5", "a", "0", "b", "0"),
            R_("R1", "1 kOhm", "a", "0"), R_("R2", "1 kOhm", "b", "0"))
    nl = c.to_netlist()
    assert "T1 a 0 b 0 0.5" in nl
    back = Circuit.from_netlist(nl, name="tNLf")
    assert back.to_netlist() == nl
    assert next(x for x in back.components
                if x.ref == "T1").value.to_base() == Decimal("0.5")


# -- provenance ----------------------------------------------------------------------

def test_provenance_ideal_transformers_dc():
    c = ckt("tPV", V_("V1", "10 V", "a", "0"),
            T_("T1", "2", "a", "0", "b", "0"), R_("R1", "1 kOhm", "b", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    summ = r.system_summary
    assert summ["ideal_transformers"] == [
        {"ref": "T1", "p1": "a", "p2": "0", "s1": "b", "s2": "0", "n": "2"}]
    assert len(r.provenance["digest"]) == 64
    r2 = assert_dc_solved(solve_linear_dc(c))
    assert r2.provenance["digest"] == r.provenance["digest"]


def test_provenance_rvi_untouched():
    c = ckt("tPR", V_("V1", "10 V", "a", "0"), R_("R1", "1 kOhm", "a", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    assert "ideal_transformers" not in r.system_summary
    assert "dependent_digest" not in r.system_summary
    assert set(r.system_summary) == {"n_nodes", "n_voltage_sources", "n_unknowns",
                                     "reference_node"}


def test_provenance_ac_ideal_transformers():
    c = ckt("tPA", V_("V1", "10 V", "a", "0"),
            T_("T1", "2", "a", "0", "b", "0"), R_("R1", "1 kOhm", "b", "0"))
    r = ac_solved(c)
    assert r.provenance["ideal_transformers"] == [
        {"ref": "T1", "p1": "a", "p2": "0", "s1": "b", "s2": "0", "n": "2"}]
    assert solve_ac(c, "1 kHz").digest == r.digest


def test_provenance_twoport_deterministic():
    from academic_core.domain.engineering.ac.impedance import PortDefinition
    c = ckt("tPD", T_("T1", "2", "a", "0", "b", "0"),
            R_("R1", "1 kOhm", "b", "0"), V_("V9", "0 V", "z", "0"))
    p1, p2 = PortDefinition("a", "0"), PortDefinition("b", "0")
    z1 = z_parameters(c, p1, p2, "1 kHz")
    z2 = z_parameters(c, p1, p2, "1 kHz")
    assert z1.digest == z2.digest
    assert z1.to_dict() == z2.to_dict()
    assert "timestamp" not in z1.provenance


# -- immutability ----------------------------------------------------------------------

def _snapshot(circuit):
    return [(e.ref, e.type,
             str(e.value.to_base()) if e.value is not None else None,
             dict(e.pins), dict(e.parameters), dict(e.metadata))
            for e in sorted(circuit.components, key=lambda x: x.ref.upper())]


def test_immutability_across_analyses():
    from academic_core.domain.engineering.ac.impedance import (
        PortDefinition, measure_port)
    from academic_core.domain.engineering.ac.problem import build_ac_problem
    from academic_core.domain.engineering.ac.operating_point import ACOperatingPoint
    from academic_core.domain.engineering.ac.topology import reference_net
    from academic_core.domain.engineering.math.linsolve.problem import NumericMode
    c = ckt("tIM", V_("V1", "10 V", "s", "0"), R_("R0", "100 ohm", "s", "a"),
            T_("T1", "2", "a", "0", "b", "0"), R_("R1", "1 kOhm", "b", "0"))
    before = (_snapshot(c), sorted(c.nets))
    solve_linear_dc(c)
    sol = solve_ac(c, "1 kHz")
    op = ACOperatingPoint.from_frequency(Q("1 kHz"), reference_net(c.nets))
    prob = build_ac_problem(c, op, NumericMode.AUTO)
    measure_port(prob, sol, PortDefinition("a", "0"), quantity="impedance")
    analyze_ac_thevenin(c, PortDefinition("b", "0"), "1 kHz")
    z_parameters(c, PortDefinition("a", "0"), PortDefinition("b", "0"), "1 kHz")
    assert (_snapshot(c), sorted(c.nets)) == before


# -- security ----------------------------------------------------------------------------

def test_security_ast_gates():
    import pathlib
    roots = [pathlib.Path(__file__).parent.parent / "src" / "academic_core" /
             "domain" / "engineering" / p
             for p in ("mna/problem.py", "mna/solver.py", "mna/dependent.py",
                       "mna/errors.py", "ac/problem.py", "ac/solution.py",
                       "ac/solver.py", "ac/twoport.py", "ac/impedance.py",
                       "circuit.py", "thevenin/analysis.py",
                       "thevenin/verification.py", "thevenin/port.py")]
    forbidden = {"eval", "exec", "compile", "__import__", "open", "input",
                 "subprocess", "os", "sys", "socket", "http", "urllib",
                 "numpy", "scipy", "pickle", "marshal", "importlib"}
    for src in roots:
        tree = ast.parse(src.read_text(encoding="utf-8"))
        found_calls, found_imports = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                found_calls.add(node.func.id)
            if isinstance(node, ast.Import):
                for a in node.names:
                    found_imports.add(a.name.split(".")[0])
            if isinstance(node, ast.ImportFrom) and node.module:
                found_imports.add(node.module.split(".")[0])
        assert not (found_calls & forbidden), (src.name, found_calls & forbidden)
        assert not (found_imports & forbidden), (src.name, found_imports & forbidden)


# -- determinism ---------------------------------------------------------------------------

def test_determinism_dc_ac_twoport_x10():
    from academic_core.domain.engineering.ac.impedance import PortDefinition
    c = ckt("tDT", V_("V1", "10 V", "s", "0"), R_("R0", "100 ohm", "s", "a"),
            T_("T1", "2", "a", "0", "b", "0"), R_("R1", "1 kOhm", "b", "0"))
    p1, p2 = PortDefinition("a", "0"), PortDefinition("b", "0")
    seen = set()
    for _ in range(10):
        r = assert_dc_solved(solve_linear_dc(c))
        d = r.to_dict()
        d["provenance"] = {k: v for k, v in d["provenance"].items()
                           if k != "timestamp"}
        a = ac_solved(c)
        z = z_parameters(c, p1, p2, "1 kHz")
        m = abcd_parameters(c, p1, p2, "1 kHz")
        seen.add((json_dumps(d), a.digest, z.digest, m.digest))
    assert len(seen) == 1


def json_dumps(d):
    import json
    return json.dumps(d, sort_keys=True, default=str)


# -- metamorphic -------------------------------------------------------------------------

def test_meta_permutation_identical():
    comps = [V_("V1", "10 V", "s", "0"), R_("R0", "100 ohm", "s", "a"),
             T_("T1", "2", "a", "0", "b", "0"), R_("R1", "400 ohm", "b", "0")]
    r1 = assert_dc_solved(solve_linear_dc(ckt("tPM", *comps)))
    r2 = assert_dc_solved(solve_linear_dc(ckt("tPM", *reversed(comps))))
    assert r1.provenance["digest"] == r2.provenance["digest"]
    assert dc_voltages(r1) == dc_voltages(r2)


def test_meta_node_rename_identical_values():
    c1 = ckt("n1", V_("V1", "10 V", "s", "0"), R_("R0", "100 ohm", "s", "a"),
             T_("T1", "2", "a", "0", "b", "0"), R_("R1", "400 ohm", "b", "0"))
    c2 = ckt("n2", V_("V1", "10 V", "src", "0"), R_("R0", "100 ohm", "src", "x"),
             T_("T1", "2", "x", "0", "y", "0"), R_("R1", "400 ohm", "y", "0"))
    assert dc_voltages(assert_dc_solved(solve_linear_dc(c1)))["b"] == \
        dc_voltages(assert_dc_solved(solve_linear_dc(c2)))["y"] == Decimal("10")


def test_meta_winding_swap_with_inverse_n():
    # Swapping windings (1,2)<->(3,4) with n -> 1/n is the same device:
    # identical node voltages on identical nets.
    # A: T(1:a,2:0,3:b,4:0) n=2 gives Va=5, Vb=10 (reflection case).
    # D: T(1:b,2:0,3:a,4:0) n=1/2, same hookup. Hand: voltage row
    # Va - (1/2)Vb = 0, so Va = Vb/2. KCL b (leaving): Vb/400 + i1 = 0
    # with i1 the 1->2 (b->0) current. KCL a: (Va-10)/100 + i2 = 0.
    # Current row: i1 + (1/2)i2 = 0, i.e. -Vb/400 + i2/2 = 0, i2 = Vb/200.
    # Into a: (Vb/2-10)/100 + Vb/200 = 0 -> Vb - 20 + Vb = 0 -> Vb = 10,
    # Va = 5. IDENTICAL to A.
    a = ckt("tSWa", V_("V1", "10 V", "s", "0"), R_("R0", "100 ohm", "s", "a"),
            T_("T1", "2", "a", "0", "b", "0"), R_("R1", "400 ohm", "b", "0"))
    d = ckt("tSWd", V_("V1", "10 V", "s", "0"), R_("R0", "100 ohm", "s", "a"),
            T_("T1", "0.5", "b", "0", "a", "0"), R_("R1", "400 ohm", "b", "0"))
    va = dc_voltages(assert_dc_solved(solve_linear_dc(a)))
    vd = dc_voltages(assert_dc_solved(solve_linear_dc(d)))
    assert va["a"] == vd["a"] == Decimal("5")
    assert va["b"] == vd["b"] == Decimal("10")


def test_meta_n_negate_with_secondary_swap():
    # n -> -n with secondary pins (3<->4) swapped is the same device:
    # flipping both the ratio sign and the secondary orientation
    # preserves every equation. Same nets, same values.
    a = ckt("tNPa", V_("V1", "10 V", "s", "0"), R_("R0", "100 ohm", "s", "x"),
            T_("T1", "2", "x", "0", "y", "0"), R_("R1", "400 ohm", "y", "0"))
    b = ckt("tNPb", V_("V1", "10 V", "s", "0"), R_("R0", "100 ohm", "s", "x"),
            T_("T1", "-2", "x", "0", "0", "y"), R_("R1", "400 ohm", "y", "0"))
    # B: pins 3:0, 4:y. Voltage row: V(0)-V(y) - (-2)(V(x)-0) = 0 ->
    # -Vy + 2Vx = 0 -> Vy = 2Vx. Same as A. Current row: i(0->y) +
    # (-2)i(x->0) = 0. KCL identical up to aux sign, voltages equal.
    va = dc_voltages(assert_dc_solved(solve_linear_dc(a)))
    vb = dc_voltages(assert_dc_solved(solve_linear_dc(b)))
    assert va["x"] == vb["x"] == Decimal("5")
    assert va["y"] == vb["y"] == Decimal("10")


def test_meta_source_scaling_linear():
    mk = lambda tag, v: ckt(tag, V_("V1", v, "s", "0"),
                            R_("R0", "100 ohm", "s", "a"),
                            T_("T1", "2", "a", "0", "b", "0"),
                            R_("R1", "400 ohm", "b", "0"))
    r1 = dc_voltages(assert_dc_solved(solve_linear_dc(mk("tSS1", "10 V"))))
    r2 = dc_voltages(assert_dc_solved(solve_linear_dc(mk("tSS2", "30 V"))))
    assert r1["a"] * 3 == r2["a"] and r1["b"] * 3 == r2["b"]


def test_meta_impedance_scaling():
    # All R x10 (turns ratio fixed): Z -> 10Z, Y -> Y/10.
    from academic_core.domain.engineering.ac.impedance import PortDefinition
    base = ckt("tSC0", R_("R1", "1 kOhm", "a", "b"), R_("R2", "1 kOhm", "b", "0"),
               V_("V9", "0 V", "z", "0"))
    big = ckt("tSC1", R_("R1", "10 kOhm", "a", "b"), R_("R2", "10 kOhm", "b", "0"),
              V_("V9", "0 V", "z", "0"))
    p1, p2 = PortDefinition("a", "0"), PortDefinition("b", "0")
    z0 = z_parameters(base, p1, p2, "1 kHz")
    z1 = z_parameters(big, p1, p2, "1 kHz")
    y0 = y_parameters(base, p1, p2, "1 kHz")
    y1 = y_parameters(big, p1, p2, "1 kHz")
    for e0, e1 in ((z0.a11, z1.a11), (z0.a12, z1.a12),
                   (z0.a21, z1.a21), (z0.a22, z1.a22)):
        assert e1.value.re == 10 * e0.value.re
    for e0, e1 in ((y0.a11, y1.a11), (y0.a12, y1.a12),
                   (y0.a21, y1.a21), (y0.a22, y1.a22)):
        assert e1.value.re * 10 == e0.value.re


def test_meta_port_swap_identities():
    # Swapping ports exchanges 11<->22 and 12<->21 (all kinds).
    from academic_core.domain.engineering.ac.impedance import PortDefinition
    p1, p2 = PortDefinition("a", "0"), PortDefinition("b", "0")
    z = z_parameters(_rc_series_shunt(), p1, p2, "1 kHz")
    zs = z_parameters(_rc_series_shunt(), p2, p1, "1 kHz")
    assert zs.a11.value == z.a22.value and zs.a22.value == z.a11.value
    assert zs.a12.value == z.a21.value and zs.a21.value == z.a12.value
    h = h_parameters(_rc_series_shunt(), p1, p2, "1 kHz")
    assert h.a12.value == Fraction(1) and h.a21.value == Fraction(-1)


def test_meta_reciprocity_passive():
    # R/L/C-only nets: z12 == z21 and y12 == y21 (verification
    # identities, never used as computation by the engine). HP Decimal
    # paths compared within working-precision tolerance (exact == holds
    # in the EXACT R-only test above).
    from academic_core.domain.engineering.ac.impedance import PortDefinition
    c = ckt("tRC", V_("V9", "0 V", "z", "0"),
            R_("R1", "1 kOhm", "a", "m"), L_("L1", "10 mH", "m", "b"),
            C_("C1", "1 uF", "b", "0"))
    p1, p2 = PortDefinition("a", "0"), PortDefinition("b", "0")
    z = z_parameters(c, p1, p2, "1 kHz")
    dz = abs(complex(float(z.a12.value.re), float(z.a12.value.im))
             - complex(float(z.a21.value.re), float(z.a21.value.im)))
    sc = abs(complex(float(z.a12.value.re), float(z.a12.value.im)))
    assert dz <= 1e-12 * max(sc, 1e-30)
    y = y_parameters(c, p1, p2, "1 kHz")
    dy = abs(complex(float(y.a12.value.re), float(y.a12.value.im))
             - complex(float(y.a21.value.re), float(y.a21.value.im)))
    scy = abs(complex(float(y.a12.value.re), float(y.a12.value.im)))
    assert dy <= 1e-12 * max(scy, 1e-30)


def test_meta_cascade_ratio_identity():
    # Chained 1:2 then 1:3 with common winding net: overall 1:6.
    # V=12 -> 24 -> 72; exact Fractions.
    c = ckt("tCZ", V_("V1", "12 V", "s", "0"),
            T_("T1", "2", "s", "0", "a", "0"),
            T_("T2", "3", "a", "0", "b", "0"),
            R_("R1", "1 kOhm", "b", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    v = dc_voltages(r)
    assert v["a"] == Decimal("24")
    assert v["b"] == Decimal("72")


# -- topology matrix -----------------------------------------------------------------

def test_topo_mesh_with_T():
    # Two meshes sharing R2 (a-b): mesh1 s-a-b-0-s, mesh2 a-b-0-a via
    # the T primary leg. Hand nodal (V, mA, kΩ): Vc = 2Vb;
    # I2w = -Vc = -2Vb (KCL c); I1w = +4Vb.
    # KCL b: (Vb-Va) + Vb + 4Vb = 0 -> -Va + 6Vb = 0.
    # KCL a: (Va-10) + (Va-Vb) = 0 -> 2Va - Vb = 10.
    # Solve: Va = 6Vb -> 12Vb - Vb = 10 -> Vb = 10/11, Va = 60/11,
    # Vc = 20/11. All inside rails. Exact integer-relation asserts:
    c = ckt("tMESH", V_("V1", "10 V", "s", "0"),
            R_("R1", "1 kOhm", "s", "a"), R_("R2", "1 kOhm", "a", "b"),
            R_("R3", "1 kOhm", "b", "0"), T_("T1", "2", "b", "0", "c", "0"),
            R_("R4", "1 kOhm", "c", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    v = dc_voltages(r)
    from academic_core.domain.engineering.mna.solver import (
        _fraction_to_decimal as _f2d)
    from fractions import Fraction as _F
    assert v["a"] == _f2d(_F(60, 11))
    assert v["b"] == _f2d(_F(10, 11))
    assert v["c"] == _f2d(_F(20, 11))
    assert r.conservation_checks.passed is True


def test_topo_mesh_determinism():
    c = ckt("tMESH", V_("V1", "10 V", "s", "0"),
            R_("R1", "1 kOhm", "s", "a"), R_("R2", "1 kOhm", "a", "b"),
            R_("R3", "1 kOhm", "b", "0"), T_("T1", "2", "b", "0", "c", "0"),
            R_("R4", "1 kOhm", "c", "0"))
    r1 = assert_dc_solved(solve_linear_dc(c))
    r2 = assert_dc_solved(solve_linear_dc(c))
    assert r1.provenance["digest"] == r2.provenance["digest"]


def test_topo_star_with_T():
    # Star center s driven 12V; arms: R1 s-a + R2 a-0 (divider),
    # R3 s-b + T1 n=3 (b,0,c,0) + R4 c-0, R5 s-d + R6 d-0.
    # Hand: Va = 12*2/3 = 8 (R1=1k, R2=2k).Vb arm: KCL b: (Vb-12)/1 +
    # I1w = 0 (mA); Vc = 3Vb; KCL c: Vc/1 + I2w = 0 -> I2w = -3Vb;
    # I1w = +9Vb. Into b: (Vb-12) + 9Vb = 0 -> Vb = 1.2, Vc = 3.6.
    # Vd = 12/2 = 6 (plain divider).
    c = ckt("tSTAR", V_("V1", "12 V", "s", "0"),
            R_("R1", "1 kOhm", "s", "a"), R_("R2", "2 kOhm", "a", "0"),
            R_("R3", "1 kOhm", "s", "b"), T_("T1", "3", "b", "0", "c", "0"),
            R_("R4", "1 kOhm", "c", "0"),
            R_("R5", "1 kOhm", "s", "d"), R_("R6", "1 kOhm", "d", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    v = dc_voltages(r)
    assert v["a"] == Decimal("8")
    assert 5 * v["b"] - 6 == 0
    assert 5 * v["c"] - 18 == 0
    assert v["d"] == Decimal("6")
    assert r.conservation_checks.passed is True


def test_topo_k33_with_T():
    # K3,3 resistive core ({a1,a2,a3}x{b1,b2,b3}, all 1k) driven at a1,
    # ground at b1, plus T1 (n=2) from a2 to a loaded secondary.
    # Assert SOLVED + exact conservation + determinism (topology
    # generality, not a closed form).
    comps = [V_("V1", "10 V", "a1", "0")]
    k = 0
    for a in ("a1", "a2", "a3"):
        for b in ("b1", "b2", "b3"):
            if (a, b) == ("a1", "b1"):
                continue
            k += 1
            comps.append(R_(f"R{k}", "1 kOhm", a, b))
    comps.append(R_("R9", "1 kOhm", "a1", "b1"))
    comps.append(T_("T1", "2", "a2", "0", "c", "0"))
    comps.append(R_("R10", "1 kOhm", "c", "0"))
    c = ckt("tK33", *comps)
    r = assert_dc_solved(solve_linear_dc(c))
    assert r.conservation_checks.passed is True
    r2 = assert_dc_solved(solve_linear_dc(c))
    assert r2.provenance["digest"] == r.provenance["digest"]


def test_topo_multigraph_parallel_T():
    # Two IDENTICAL transformers in parallel: the circulating/split
    # currents are undetermined (only their sum is fixed) -> honest
    # SINGULAR, consistent. A general lesson: parallel ideal windings
    # need series impedance for uniqueness.
    c = ckt("tMG", V_("V1", "10 V", "a", "0"),
            T_("T1", "2", "a", "0", "b", "0"),
            T_("T2", "2", "a", "0", "b", "0"),
            R_("R1", "1 kOhm", "b", "0"))
    assert solve_linear_dc(c).status == SolveStatus.SINGULAR


def test_topo_multigraph_distinct_T_solved():
    # Different ratios in parallel: fully determined. Hand: Vb = 2Va
    # (T1) and Vb = 3Va (T2)?? CONFLICT unless Va = Vb = 0... with
    # drive V1=10 at a: Vb = 20 AND Vb = 30 -> INCONSISTENT. Correct
    # honest outcome, but for a SOLVED multigraph use shared-primary,
    # separate-secondary windings instead (next test's concern is
    # determinism of parallel edges; keep this one minimal):
    c = ckt("tMG2", V_("V1", "10 V", "a", "0"),
            T_("T1", "2", "a", "0", "b", "0"),
            T_("T2", "3", "a", "0", "c", "0"),
            R_("R1", "1 kOhm", "b", "0"), R_("R2", "1 kOhm", "c", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    v = dc_voltages(r)
    assert v["b"] == Decimal("20")
    assert v["c"] == Decimal("30")
    assert r.conservation_checks.passed is True


def test_topo_high_degree_node_with_T():
    # Node x of degree 6 (source, 3 resistors, T primary, meter R):
    # hand nodal spot-checks.
    # V1=12 x? No: drive s=12; R0 s-x 1k. At x: R1 x-0 2k, R2 x-0 3k,
    # R3 x-m 4k, T1 n=2 (x,0,y,0), R4 y-0 5k.
    # Constraints: Vy = 2Vx. KCL y: Vy/5 + I2w = 0 (mA, kΩ, V).
    # KCL x: (Vx-12)/1 + Vx/2 + Vx/3 + (Vx-Vm)/4... wait R3 x-m where
    # m is what? Redefine cleanly: R3 x-0 4k (third shunt). Then:
    # KCL x: (Vx-12) + Vx/2 + Vx/3 + Vx/4 + I1w = 0 (mA).
    # From y: I2w = -Vy/5 = -2Vx/5; I1w = +4Vx/5.
    # Into x: Vx-12 + Vx/2 + Vx/3 + Vx/4 + 4Vx/5 = 0. Common denom 60:
    # 60Vx - 720 + 30Vx + 20Vx + 15Vx + 48Vx = 0 -> 173Vx = 720 ->
    # Vx = 720/173 (non-terminating!). Assert integer relations:
    # 173*Vx - 720 = 0 and Vy - 2Vx = 0, exactly in Decimals.
    c = ckt("tHD", V_("V1", "12 V", "s", "0"), R_("R0", "1 kOhm", "s", "x"),
            R_("R1", "2 kOhm", "x", "0"), R_("R2", "3 kOhm", "x", "0"),
            R_("R3", "4 kOhm", "x", "0"), T_("T1", "2", "x", "0", "y", "0"),
            R_("R4", "5 kOhm", "y", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    v = dc_voltages(r)
    from academic_core.domain.engineering.mna.solver import (
        _fraction_to_decimal as _f2d)
    from fractions import Fraction as _F
    assert v["x"] == _f2d(_F(720, 173))
    # Presentation Decimals are rounded independently per node: the exact
    # law Vy = 2*Vx holds in Fractions, so compare each side against its
    # own exact rounding (2*Decimal(x) would double the rounding error).
    assert v["y"] == _f2d(2 * _F(720, 173))
    assert r.conservation_checks.passed is True


# -- F8-G closure: AC power, ngspice oracle, perf, D6/D8 reuse, extra topo ----

def test_ac_power_T_exact_zero():
    # R-only + T -> EXACT phasors: S = 1/2 V conj(I) per leg; the ideal
    # device stores/delivers nothing, so S(T1:1) + S(T1:2) == 0 exactly.
    c = ckt("tPWac", V_("V1", "10 V", "s", "0"), R_("R0", "100 ohm", "s", "a"),
            T_("T1", "2", "a", "0", "b", "0"), R_("R1", "400 ohm", "b", "0"))
    r = ac_solved(c)
    assert r.numeric_mode.value == "exact"
    p = analyze_power(r)
    assert p.conservation.passed is True, p.conservation.diagnostics
    by_ref = {e.ref: e for e in p.elements}
    s1, s2 = by_ref["T1:1"].power, by_ref["T1:2"].power
    from academic_core.domain.engineering.math.rational import RationalComplex
    assert s1 + s2 == RationalComplex(Fraction(0), Fraction(0))
    # Active and reactive parts cancel independently (lossless, no shift).
    assert by_ref["T1:1"].active + by_ref["T1:2"].active == Fraction(0)
    assert by_ref["T1:1"].reactive + by_ref["T1:2"].reactive == Fraction(0)


def test_ac_power_T_hp_within_bound():
    # T + L/C at 1 kHz (HP): conservation holds within the D4 derived
    # bound, and the transformer legs still cancel to solver precision.
    c = ckt("tPWhp", V_("V1", "10 V", "s", "0"), R_("R0", "100 ohm", "s", "a"),
            L_("L1", "10 mH", "a", "m"), T_("T1", "2", "m", "0", "b", "0"),
            C_("C1", "1 uF", "b", "0"))
    r = ac_solved(c)
    assert r.numeric_mode.value == "high_precision"
    p = analyze_power(r)
    assert p.conservation.passed is True, p.conservation.diagnostics
    by_ref = {e.ref: e for e in p.elements}
    stot = by_ref["T1:1"].power + by_ref["T1:2"].power
    smax = max((e.power.modulus() for e in p.elements),
               key=lambda d: float(d))
    assert float(stot.modulus()) <= 1e-9 * max(1.0, float(smax))


def _ng_backend():
    from academic_core.infrastructure.ngspice import NgSpiceBackend

    b = NgSpiceBackend()
    return b if b.detect().verified else None


NG = _ng_backend()


def _coupled_L_bound(n, r0, r1, lp, k, freq_hz):
    # Per-case analytic bound for the coupled-inductor approximation:
    # magnetizing error ~ Zin_ideal/(w*Lp) at the primary plus leakage
    # error ~ w*(1-k^2)*Ls/R1 at the secondary, plus a fixed 1% account
    # for ngspice/H P solver noise. Nothing is copied across cases: every
    # term is evaluated from THIS case's own parameters below.
    import cmath
    w = 2 * cmath.pi * freq_hz
    zref = r1 / n ** 2
    zin = r0 + zref
    mag = abs(zin / (w * lp))
    leak = abs(w * (1 - k ** 2) * (n ** 2 * lp) / r1)
    return mag + leak + 0.01


def _ng_ac_coupled_T(name, n, r0, r1, lp, k, freq_hz=1000):
    # Academic ideal-T circuit (authoritative) + ngspice coupled-L deck
    # (L2 = n^2*Lp, coupling k): bounded numerical oracle only.
    from academic_core.domain.engineering.simulation import ACAnalysis
    c = ckt(name, V_("V1", "10 V", "s", "0"), R_("R0", f"{r0} ohm", "s", "a"),
            T_("T1", str(n), "a", "0", "b", "0"),
            R_("R1", f"{r1} ohm", "b", "0"))
    r = ac_solved(c, f"{freq_hz} Hz")
    assert r.numeric_mode.value == "exact"
    ls = n ** 2 * lp
    deck = (f"* F8-G coupled-L oracle {name}\nV1 s 0 DC 0 AC 10\n"
            f"R0 s a {r0}\nL1 a 0 {lp}\nL2 b 0 {ls}\n"
            f"K1 L1 L2 {k}\nR1 b 0 {r1}\n"
            f".ac lin 2 {freq_hz} {freq_hz + 1}\n"
            f".print ac v(a) v(b)\n.end\n")
    res = NG.simulate(deck, analyses=(ACAnalysis(
        sweep_type="lin", points=2, fstart=str(freq_hz),
        fstop=str(freq_hz + 1)),))
    assert res.status == "COMPLETED", res.raw_stderr
    return r, res


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_ngspice_T_step_up_bounded():
    # n=2, R0=1k, R1=10k: ideal Va=50/7, Vb=100/7 (reflection 2.5k).
    # Coupled L1=100H/L2=400H/k=0.999999 must land inside the per-case
    # bound derived above — approximate agreement, never equivalence.
    import cmath
    r, res = _ng_ac_coupled_T("tNG2", 2, 1000, 10000, 100, 0.999999)
    got = {n.node: complex(float(n.phasor.re), float(n.phasor.im))
           for n in r.node_voltages}
    assert abs(got["a"] - 50.0 / 7.0) / (50.0 / 7.0) <= 1e-9
    assert abs(got["b"] - 100.0 / 7.0) / (100.0 / 7.0) <= 1e-9
    bound = _coupled_L_bound(2, 1000, 10000, 100, 0.999999, 1000)
    for node, ref in (("a", 50.0 / 7.0), ("b", 100.0 / 7.0)):
        o = res.sample_complex_at(f"v({node})", "1000")
        assert o is not None
        assert abs(o - ref) / abs(ref) <= bound, (node, o, ref, bound)


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_ngspice_T_step_down_bounded():
    # n=1/2, R0=1k, R1=10k: ideal Va=400/41, Vb=200/41 (reflection 40k).
    # Own bound from own parameters (L1=100H/L2=25H/k=0.999999).
    r, res = _ng_ac_coupled_T("tNGh", 0.5, 1000, 10000, 100, 0.999999)
    got = {n.node: complex(float(n.phasor.re), float(n.phasor.im))
           for n in r.node_voltages}
    assert abs(got["a"] - 400.0 / 41.0) / (400.0 / 41.0) <= 1e-9
    assert abs(got["b"] - 200.0 / 41.0) / (200.0 / 41.0) <= 1e-9
    bound = _coupled_L_bound(0.5, 1000, 10000, 100, 0.999999, 1000)
    for node, ref in (("a", 400.0 / 41.0), ("b", 200.0 / 41.0)):
        o = res.sample_complex_at(f"v({node})", "1000")
        assert o is not None
        assert abs(o - ref) / abs(ref) <= bound, (node, o, ref, bound)


def test_perf_f8g_scales():
    # N=16/32/64 on the T-buffered ladder: solver time (DC exact, AC) and
    # observable time (Z extraction, 2 derived solves) measured
    # separately, totals printed. Exact rational arithmetic scales
    # superlinearly (measured 2026-09-16: AC exact N=32 ~= 170 s), so N=64
    # AC/extraction use the certified HP path (same stamp, D2 HP solver;
    # modes labeled, no math changed, no cache introduced). Caps are
    # generous honesty rails, aligned with F8-E perf practice.
    from academic_core.domain.engineering.ac.impedance import PortDefinition
    from academic_core.domain.engineering.math.linsolve.problem import (
        NumericMode)
    marks = {}
    for n, cap in ((16, 120), (32, 300), (64, 900)):
        c = _ladder_T(n, name="tPG")
        t0 = time.perf_counter()
        assert_dc_solved(solve_linear_dc(c))
        dt_dc = time.perf_counter() - t0
        t0 = time.perf_counter()
        if n <= 32:
            ac_solved(c, "1 kHz")
            ac_mode = "exact"
        else:
            r64 = solve_ac(c, "1 kHz", NumericMode.HIGH_PRECISION)
            assert r64.status == ACStatus.SOLVED, r64.diagnostics
            ac_mode = "hp"
        dt_ac = time.perf_counter() - t0
        t0 = time.perf_counter()
        z_parameters(c, PortDefinition("in", "0"),
                     PortDefinition(f"o{n}", "0"), "1 kHz",
                     NumericMode.AUTO if n <= 16 else NumericMode.HIGH_PRECISION)
        dt_z = time.perf_counter() - t0
        z_mode = "exact" if n <= 16 else "hp"
        marks[n] = (round(dt_dc, 2), round(dt_ac, 2), round(dt_z, 2))
        assert dt_dc < cap and dt_ac < cap and dt_z < cap, (n, marks[n])
    print(f"\nF8-G perf seconds by N (dc-exact, ac, z-extract): {marks} "
          f"(ac: exact,exact,hp; z: exact,hp,hp)")


def test_d6_bode_with_T():
    # D6 reuse (no new logic): sweep a T transfer, then dB + unwrap.
    # Hv = 18/13 (test_d5_transfer_hv_through_T); dB = 20 log10(18/13).
    from academic_core.domain.engineering.ac.bode import (
        magnitude_db, unwrap_phases)
    from academic_core.domain.engineering.math.logarithm import decimal_log10
    from academic_core.domain.engineering.math.trig import make_context
    c = ckt("tBD", V_("V1", "10 V", "s", "0"), R_("R0", "100 ohm", "s", "a"),
            T_("T1", "2", "a", "0", "b", "0"), R_("R1", "900 ohm", "b", "0"))
    d = ResponseDefinition("transfer", (voltage_between("s", "0"),
                                       voltage_between("b", "0"), "V1"))
    sw = frequency_response(c, d, ["100 Hz", "1 kHz", "10 kHz"])
    assert sw.status == "completed"
    mags = [p.value.magnitude() for p in sw.points]
    ctx = make_context()
    for m in mags:
        assert abs(m - Decimal(18) / Decimal(13)) <= Decimal("1E-25")
        db = magnitude_db(m)
        expect = ctx.multiply(Decimal(20), decimal_log10(
            ctx.divide(Decimal(18), Decimal(13)), ctx))
        assert db.category.value == "finite"
        assert abs(db.value - expect) <= Decimal("1E-30"), (db.value, expect)
    ph, _lags = unwrap_phases([p.value.phase() for p in sw.points])
    assert ph == [Decimal("0"), Decimal("0"), Decimal("0")]


def test_d8_scan_with_T():
    # D8 reuse (no new logic, no resonance claims for T): a T+R-only
    # network has no reactive branch, so the scan report must be honest
    # (a report object with digest, never a fabricated resonance).
    from academic_core.domain.engineering.ac.resonance import scan_resonance
    c = ckt("tRS", V_("V1", "10 V", "s", "0"), R_("R0", "100 ohm", "s", "a"),
            T_("T1", "2", "a", "0", "b", "0"), R_("R1", "900 ohm", "b", "0"))
    d = ResponseDefinition("transfer", (voltage_between("s", "0"),
                                       voltage_between("b", "0"), "V1"))
    rep = scan_resonance(c, d, ["100 Hz", "1 kHz", "10 kHz"])
    assert rep.observable == "transfer"
    assert len(rep.digest) == 64
    # Honest verdict for a reactance-free network: D6 observes the flat
    # discrete extrema (corroboration only, never resonance verdicts) and
    # the transfer-peak criterion reports the explicit no-resonance
    # verdict. No confirmed zero, no bracket candidate may appear.
    from academic_core.domain.engineering.ac.resonance import FindingKind
    assert all(f.kind != FindingKind.ZERO_CONFIRMED for f in rep.findings)
    assert all(f.kind != FindingKind.BRACKET_CANDIDATE for f in rep.findings)
    peak = [f for f in rep.findings if str(f.criterion) == "transfer-peak"]
    assert peak and all(f.kind == FindingKind.NO_RESONANCE_OBSERVED
                        for f in peak)
    # Deterministic: same inputs, same digest.
    rep2 = scan_resonance(c, d, ["100 Hz", "1 kHz", "10 kHz"])
    assert rep2.digest == rep.digest


def test_f8c_ac_zth_with_T():
    # AC Thevenin reuse (D7 engine, T kept active): reflection circuit
    # V=10, R0=100, T n=2, R1=400, port (b,0): Vth=10, Zth=200 FINITE.
    from academic_core.domain.engineering.ac import analyze_ac_thevenin
    from academic_core.domain.engineering.ac.impedance import ImpedanceCategory
    c = ckt("tAZ", V_("V1", "10 V", "s", "0"), R_("R0", "100 ohm", "s", "a"),
            T_("T1", "2", "a", "0", "b", "0"), R_("R1", "400 ohm", "b", "0"))
    r = analyze_ac_thevenin(c, PortDefinition("b", "0"), "1 kHz")
    assert r.status == ACStatus.SOLVED, r.diagnostics
    assert r.vth == RationalComplex(Fraction(10), Fraction(0))
    assert r.zth.category == ImpedanceCategory.FINITE
    assert r.zth.value == RationalComplex(Fraction(200), Fraction(0))
    assert r.numeric_mode.value == "exact"


def test_topo_series_aiding_secondaries():
    # Two n=1 secondaries in series (b-c, c-0) with primaries across the
    # 10 V drive: Vc = 10, Vb - Vc = 10 -> Vb = 20 (voltages add).
    c = ckt("tSE", V_("V1", "10 V", "a", "0"),
            T_("T1", "1", "a", "0", "b", "c"),
            T_("T2", "1", "a", "0", "c", "0"),
            R_("R1", "1 kOhm", "b", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    v = dc_voltages(r)
    assert v["c"] == Decimal("10")
    assert v["b"] == Decimal("20")
    assert r.conservation_checks.passed is True


def test_topo_parallel_T_direct_singular():
    # Directly paralleled ideal windings (same nets, equal ratios) leave
    # the circulating winding current undetermined — the exact analogue
    # of paralleled ideal voltage sources: SINGULAR, never an invented
    # equal split.
    c = ckt("tPA", V_("V1", "10 V", "a", "0"),
            T_("T1", "2", "a", "0", "b", "0"),
            T_("T2", "2", "a", "0", "b", "0"),
            R_("R1", "1 kOhm", "b", "0"))
    assert solve_linear_dc(c).status == SolveStatus.SINGULAR


def test_topo_parallel_T_sharing_resistive():
    # Series ballast resistors break the degeneracy; symmetry then forces
    # exact equal sharing. Hand (V, mA, kOhm): Vx1 = Vx2 = Vx by
    # symmetry; Vb = 2Vx; KCL b: Vb + 2*I2w = 0 -> I2w = -Vx;
    # KCL x1: (Vx-10)/0.1 - 2*I2w... I1w = -2*I2w = 2Vx, so
    # (Vx-10)/0.1 + 2Vx = 0 -> 1.2Vx = 10 -> Vx = 25/3, Vb = 50/3.
    c = ckt("tPAr", V_("V1", "10 V", "s", "0"),
            R_("R3", "100 ohm", "s", "x1"), R_("R4", "100 ohm", "s", "x2"),
            T_("T1", "2", "x1", "0", "b", "0"),
            T_("T2", "2", "x2", "0", "b", "0"),
            R_("R1", "1 kOhm", "b", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    v = dc_voltages(r)
    assert v["b"] == Decimal(50) / Decimal(3)
    assert v["x1"] == v["x2"] == Decimal(25) / Decimal(3)
    i = dc_currents(r)
    assert i["T1:2"] == i["T2:2"]
    assert i["T1:1"] == i["T2:1"]
    assert r.conservation_checks.passed is True


def test_topo_cross_coupled_contradiction():
    # Loop gain n1*n2 = 6 != 1 with Va forced to 10 V: the two voltage
    # constraints (Vb = 2Va, Va = 3Vb) contradict -> INCONSISTENT.
    c = ckt("tXC", V_("V1", "10 V", "a", "0"),
            T_("T1", "2", "a", "0", "b", "0"),
            T_("T2", "3", "b", "0", "a", "0"))
    assert solve_linear_dc(c).status == SolveStatus.INCONSISTENT


def test_topo_cross_coupled_loop_gain_one():
    # Loop gain n1*n2 = 1 with Va forced: voltage constraints coincide
    # (Vb = 2Va both ways) but the circulating winding current is free
    # -> rank-deficient consistent system: SINGULAR, never invented.
    c = ckt("tX1", V_("V1", "10 V", "a", "0"),
            T_("T1", "2", "a", "0", "b", "0"),
            T_("T2", "0.5", "b", "0", "a", "0"))
    assert solve_linear_dc(c).status == SolveStatus.SINGULAR
