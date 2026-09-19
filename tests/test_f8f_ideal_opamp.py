"""F8-F Ideal op-amps (nullor MNA): O type, exact constraint, no parameters.

Canonical model: Component(ref, "O", None, {"+":inp,"-":inn,"o":out}, {}).
Semantics per pin: V(in+) - V(in-) = 0 (constraint row); I(in+) = I(in-)
= 0 (no stamp entries = exact open); aux unknown i_o delivered INTO
"out" (KCL sum-leaving at "o": -i_o). Reconstructed output leg is
(out -> ground) with current -i_o and voltage Vout, so absorbed power
P = Vout * (-i_o) via the generic D4/DC formulas — no special power
path, no weakened conservation check.

ngspice mapping: ideal device approximated by an E-macro with μ=1e9;
closed-loop error ~ G_loop/(μ·β), negligible at assertion tolerances
(probed: follower and x10-inverter exact to printed precision).
The academic constraint model is authoritative on any disagreement.

Expected values are hand derivations (nodal/KCL, closed forms) —
never implementation outputs. Classical configurations are TESTS,
never domain limits: no formula dispatch exists in the engines.
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
from academic_core.domain.engineering.circuit import Circuit, CircuitError, Component
from academic_core.domain.engineering.math import RationalComplex
from academic_core.domain.engineering.mna import (
    build_mna_problem,
    solve_linear_dc,
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


def O_(ref, inp, inn, out):
    return Component(ref, "O", None, {"+": inp, "-": inn, "o": out}, {})


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


# -- validation ---------------------------------------------------------------

def test_o_rejects_value():
    # Component accepts value syntactically (generic model); the engines
    # reject it loudly since a value would be silently ignored physics.
    c = ckt("ov", V_("V1", "10 V", "in", "0"),
            Component("O1", "O", Q("5"), {"+": "in", "-": "out", "o": "out"}, {}),
            R_("R1", "1 kOhm", "out", "0"))
    r = solve_linear_dc(c)
    assert r.status == SolveStatus.INVALID


def test_o_rejects_parameters():
    c = ckt("op", V_("V1", "10 V", "in", "0"),
            Component("O1", "O", None, {"+": "in", "-": "out", "o": "out"},
                      {"gain": "100"}),
            R_("R1", "1 kOhm", "out", "0"))
    r = solve_linear_dc(c)
    assert r.status == SolveStatus.INVALID


def test_o_rejects_bad_pins_and_refs():
    with pytest.raises(CircuitError):
        Component("O1", "O", None, {"+": "a", "-": "b"}, {})
    with pytest.raises(CircuitError):
        Component("O1", "O", None, {"+": "", "-": "b", "o": "c"}, {})
    with pytest.raises(CircuitError):
        Component("R1", "O", None, {"+": "a", "-": "b", "o": "c"}, {})
    with pytest.raises(CircuitError):
        Component("O1", "E", Q("2"), {"+": "a", "-": "b"}, {})


def test_o_ac_rejects_value_and_params():
    c = ckt("oav", V_("V1", "10 V", "in", "0"),
            Component("O1", "O", Q("5"), {"+": "in", "-": "out", "o": "out"}, {}),
            R_("R1", "1 kOhm", "out", "0"))
    assert solve_ac(c, "1 kHz").status == ACStatus.INVALID
    c2 = ckt("oap", V_("V1", "10 V", "in", "0"),
             Component("O1", "O", None, {"+": "in", "-": "out", "o": "out"},
                       {"mu": "2"}),
             R_("R1", "1 kOhm", "out", "0"))
    assert solve_ac(c2, "1 kHz").status == ACStatus.INVALID


def test_o_netlist_roundtrip_structural():
    c = ckt("onl", V_("V1", "10 V", "in", "0"), O_("O1", "in", "m", "out"),
            R_("R1", "1 kOhm", "m", "out"), R_("R2", "1 kOhm", "out", "0"))
    nl = c.to_netlist()
    assert "O1 in m out O" in nl
    back = Circuit.from_netlist(nl, name="onl")
    o1 = next(x for x in back.components if x.ref == "O1")
    assert o1.type == "O" and o1.value is None
    assert o1.pins == {"+": "in", "-": "m", "o": "out"}
    assert back.to_netlist() == nl


# -- DC classics (hand nodal) ---------------------------------------------------

def test_dc_follower_exact():
    c = ckt("fol", V_("V1", "10 V", "inn", "0"), R_("R1", "1 kOhm", "inn", "0"),
            O_("O1", "inn", "out", "out"), R_("R2", "1 kOhm", "out", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    assert dc_voltages(r)["out"] == Decimal("10")
    # O1 delivers 10 mA into out; reported leg current (out->gnd) is -10 mA.
    assert dc_currents(r)["O1"] == Decimal("-0.01")
    assert r.conservation_checks.passed is True


def test_dc_inverting_exact():
    # KCL at m (virtual ground): (0-10)/10k + (0-Vout)/100k = 0 -> -100.
    c = ckt("inv", V_("V1", "10 V", "inn", "0"), R_("R1", "10 kOhm", "inn", "m"),
            R_("R2", "100 kOhm", "m", "out"), O_("O1", "0", "m", "out"))
    r = assert_dc_solved(solve_linear_dc(c))
    v = dc_voltages(r)
    assert v["m"] == Decimal("0")
    assert v["out"] == Decimal("-100")
    assert r.conservation_checks.passed is True


def test_dc_noninverting_exact():
    # Vm = 2 (constraint); (2-0)/10k + (2-Vout)/20k = 0 -> Vout = 6.
    c = ckt("ninv", V_("V1", "2 V", "inn", "0"), O_("O1", "inn", "m", "out"),
            R_("R1", "10 kOhm", "m", "0"), R_("R2", "20 kOhm", "out", "m"))
    r = assert_dc_solved(solve_linear_dc(c))
    v = dc_voltages(r)
    assert v["m"] == Decimal("2")
    assert v["out"] == Decimal("6")


def test_dc_summer_exact():
    # Vout = -(V1+V2) = -3 with equal 10k.
    c = ckt("sum", V_("V1", "1 V", "a", "0"), V_("V2", "2 V", "b", "0"),
            R_("R1", "10 kOhm", "a", "m"), R_("R2", "10 kOhm", "b", "m"),
            R_("R3", "10 kOhm", "m", "out"), O_("O1", "0", "m", "out"))
    r = assert_dc_solved(solve_linear_dc(c))
    assert dc_voltages(r)["out"] == Decimal("-3")


def test_dc_differential_exact():
    # Matched 10k: V+ = 0.5; KCL at -: (0.5-3) + (0.5-Vout) = 0 -> -2.
    c = ckt("dif", V_("V1", "3 V", "a", "0"), V_("V2", "1 V", "b", "0"),
            R_("R1", "10 kOhm", "a", "m"), R_("R2", "10 kOhm", "m", "out"),
            R_("R3", "10 kOhm", "b", "p"), R_("R4", "10 kOhm", "p", "0"),
            O_("O1", "p", "m", "out"))
    r = assert_dc_solved(solve_linear_dc(c))
    v = dc_voltages(r)
    assert v["p"] == Decimal("0.5")
    assert v["m"] == Decimal("0.5")
    assert v["out"] == Decimal("-2")


def test_dc_transimpedance_exact():
    # 1 mA into m, Rf = 10k to out, + grounded: Vout = -10.
    c = ckt("tia", I_("I1", "1 mA", "m", "0"), R_("R1", "10 kOhm", "m", "out"),
            O_("O1", "0", "m", "out"))
    r = assert_dc_solved(solve_linear_dc(c))
    assert dc_voltages(r)["out"] == Decimal("-10")


def test_dc_two_opamps_cascade():
    # Follower (x2? no: follower gain 1) then x10 inverter: 5 -> 5 -> -50.
    c = ckt("cas", V_("V1", "5 V", "inn", "0"), O_("O1", "inn", "a", "a"),
            R_("R1", "10 kOhm", "a", "m"), R_("R2", "100 kOhm", "m", "out"),
            O_("O2", "0", "m", "out"))
    r = assert_dc_solved(solve_linear_dc(c))
    v = dc_voltages(r)
    assert v["a"] == Decimal("5")
    assert v["out"] == Decimal("-50")


def test_dc_four_opamps_instrumentation_like():
    # Two non-inverting x2 front ends (3V, 1V) then diff x1: out = 6-2 = 4.
    # Front ends: O1: +<-3V, m1 divider 10k/10k -> 6V; O2: +<-1V -> 2V.
    # Diff: R 10k matched, V+ = 1V? Build: a=6, b=2 feed diff with gain 1:
    # Vp = b/2 = 1; KCL at m: (1-6)+(1-Vout) = 0 -> Vout = -4?? recompute:
    # (Vm-Va)/10k + (Vm-Vout)/10k = 0 with Vm = Vp = 1, Va = 6:
    # (1-6) + (1-Vout) = 0 -> Vout = -4. So expected -4.
    c = ckt("ina", V_("V1", "3 V", "s1", "0"), V_("V2", "1 V", "s2", "0"),
            O_("O1", "s1", "m1", "a"), R_("R1", "10 kOhm", "m1", "0"),
            R_("R2", "10 kOhm", "a", "m1"),
            O_("O2", "s2", "m2", "b"), R_("R3", "10 kOhm", "m2", "0"),
            R_("R4", "10 kOhm", "b", "m2"),
            R_("R5", "10 kOhm", "a", "m"), R_("R6", "10 kOhm", "m", "out"),
            R_("R7", "10 kOhm", "b", "p"), R_("R8", "10 kOhm", "p", "0"),
            O_("O3", "p", "m", "out"))
    r = assert_dc_solved(solve_linear_dc(c))
    v = dc_voltages(r)
    assert v["a"] == Decimal("6")
    assert v["b"] == Decimal("2")
    assert v["out"] == Decimal("-4")


# -- output current / power -------------------------------------------------------

def test_dc_output_current_sign_and_power():
    # Follower sourcing into 1k: i_o delivered = +10 mA; reported -10 mA;
    # absorbed power -0.1 W (delivering); Tellegen exact.
    c = ckt("opw", V_("V1", "10 V", "inn", "0"), O_("O1", "inn", "out", "out"),
            R_("R1", "1 kOhm", "out", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    assert dc_currents(r)["O1"] == Decimal("-0.01")
    pw = {e.ref: e for e in r.element_powers}
    assert pw["O1"].absorbed is False
    assert pw["R1"].absorbed is True
    assert r.conservation_checks.passed is True


def test_dc_output_sinking_current():
    # Inverting amp sinking: Vout = -100 across 100k feedback only... use
    # follower with pulldown conflict? Sinking case: non-inverting x6 of 2V
    # with load to +rail-side? Simplest: follower driven -5V into 2k load:
    # i_o delivered = -2.5 mA (sinks 2.5 mA); reported +2.5 mA.
    c = ckt("osk", V_("V1", "-5 V", "inn", "0"), O_("O1", "inn", "out", "out"),
            R_("R1", "2 kOhm", "out", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    assert dc_voltages(r)["out"] == Decimal("-5")
    assert dc_currents(r)["O1"] == Decimal("0.0025")
    assert r.conservation_checks.passed is True


# -- singularities (solver decides; hand-derived expectations) ---------------------

def test_sing_open_loop_driven_inconsistent():
    # V+ = 1V forced, V- = 0: constraint 1 = 0 impossible.
    c = ckt("ol1", V_("V1", "1 V", "p", "0"), O_("O1", "p", "0", "out"),
            R_("R1", "1 kOhm", "out", "0"))
    assert solve_linear_dc(c).status == SolveStatus.INCONSISTENT


def test_sing_open_loop_consistent_singular():
    # Constraint 0 = 0; Vout and i_o free -> rank-deficient, consistent.
    c = ckt("ol2", O_("O1", "0", "0", "out"), R_("R1", "1 kOhm", "out", "0"))
    # Note: "0" net as input pins is allowed (nets exist); KCL at out:
    # Vout/1k - i_o = 0 with Vout free -> singular.
    assert solve_linear_dc(c).status == SolveStatus.SINGULAR


def test_sing_positive_feedback_loop_singular():
    # Two followers in a loop, no drive: V1 = V2 free -> singular.
    c = ckt("pf1", O_("O1", "b", "a", "a"), O_("O2", "a", "b", "b"),
            R_("R1", "1 kOhm", "a", "0"), R_("R2", "1 kOhm", "b", "0"))
    assert solve_linear_dc(c).status == SolveStatus.SINGULAR


def test_sing_positive_feedback_solved_zero():
    # Loop with consistent zero: O1 follower of b, O2 x2 of a... Vb = Va,
    # Va = 2Vb -> only zero. R loads keep nets reachable.
    c = ckt("pf2", O_("O1", "b", "a", "a"), O_("O2", "a", "m", "b"),
            R_("R1", "1 kOhm", "m", "0"), R_("R2", "1 kOhm", "b", "0"),
            R_("R3", "1 kOhm", "a", "0"))
    # O2: +<-a, divider m: Vm = Va/2? R1 m-0 only... m only at O2.- and R1:
    # constraint Va = Vm; KCL at m: Vm/1k (+ nothing else, input draws 0)
    # -> Vm = 0 -> Va = 0 -> Vb = 0. Unique zero -> SOLVED.
    r = assert_dc_solved(solve_linear_dc(c))
    assert dc_voltages(r)["a"] == Decimal("0")
    assert dc_voltages(r)["b"] == Decimal("0")


def test_sing_tied_outputs_same_drive_singular():
    # Both followers drive 5V into tied node: voltages agree, but the
    # current split (i1+i2 = Vout/R) is undetermined -> singular.
    c = ckt("tie1", V_("V1", "5 V", "inn", "0"), O_("O1", "inn", "out", "out"),
            O_("O2", "inn", "out", "out"), R_("R1", "1 kOhm", "out", "0"))
    assert solve_linear_dc(c).status == SolveStatus.SINGULAR


def test_sing_tied_outputs_conflict_inconsistent():
    c = ckt("tie2", V_("V1", "5 V", "a", "0"), V_("V2", "10 V", "b", "0"),
            O_("O1", "a", "out", "out"), O_("O2", "b", "out", "out"),
            R_("R1", "1 kOhm", "out", "0"))
    assert solve_linear_dc(c).status == SolveStatus.INCONSISTENT


def test_sing_positive_feedback_contradictory_inconsistent():
    # Positive-feedback loop driven against itself: O1 follows X (=5V by
    # V1); O2 non-inverting x2 of out1 wants out2 = 10V; out2 tied to X.
    # Constraint chain forces 5 = 10 -> INCONSISTENT (solver verdict).
    c = ckt("pfc", V_("V1", "5 V", "x", "0"), O_("O1", "x", "o1", "o1"),
            R_("R1", "1 kOhm", "o1", "0"), O_("O2", "o1", "m", "x"),
            R_("R2", "1 kOhm", "m", "0"), R_("R3", "1 kOhm", "x", "m"))
    assert solve_linear_dc(c).status == SolveStatus.INCONSISTENT


def test_sing_output_shorted_to_ground_singular():
    # + driven 0V (constraint 0=0 ok); o tied to ground so Vout = 0;
    # i_o appears in no KCL row -> free -> consistent SINGULAR.
    c = ckt("sh1b", V_("V1", "0 V", "inn", "0"),
             O_("O1", "inn", "0", "0"))
    assert solve_linear_dc(c).status == SolveStatus.SINGULAR


def test_sing_output_short_vs_network_solved():
    # Follower 10V with out shorted to ground THROUGH 0-ohm? Use explicit
    # short: o pin tied to "0", + driven 10V: constraint 10 = V- = 0 fails.
    c = ckt("sh2", V_("V1", "10 V", "inn", "0"), O_("O1", "inn", "0", "0"))
    assert solve_linear_dc(c).status == SolveStatus.INCONSISTENT


def test_sing_zero_excitation_solved_zero():
    # Follower, + grounded, out loaded: unique zero solution.
    c = ckt("zez", O_("O1", "0", "out", "out"), R_("R1", "1 kOhm", "out", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    assert dc_voltages(r)["out"] == Decimal("0")
    assert dc_currents(r)["O1"] == Decimal("0")


# -- AC -----------------------------------------------------------------------------

def test_ac_follower_exact():
    c = ckt("af", V_("V1", "10 V", "inn", "0"), O_("O1", "inn", "out", "out"),
            R_("R1", "1 kOhm", "out", "0"))
    r = ac_solved(c)
    assert r.numeric_mode.value == "exact"
    vo = next(n.phasor for n in r.node_voltages if n.node == "out")
    assert isinstance(vo, RationalComplex)
    assert vo.re == Fraction(10) and vo.im == Fraction(0)


def test_ac_inverting_exact():
    c = ckt("ainv", V_("V1", "1 V", "inn", "0"), R_("R1", "10 kOhm", "inn", "m"),
            R_("R2", "100 kOhm", "m", "out"), O_("O1", "0", "m", "out"))
    r = ac_solved(c)
    vo = next(n.phasor for n in r.node_voltages if n.node == "out")
    assert vo.re == Fraction(-10) and vo.im == Fraction(0)


def test_ac_integrator_hp_hand():
    # H = -1/(j w R C), R=10k, C=100nF, f=1kHz, Vin=10: Vout = +j1.5915...
    import cmath
    c = ckt("aint", V_("V1", "10 V", "inn", "0"), R_("R1", "10 kOhm", "inn", "m"),
            C_("C1", "100 nF", "m", "out"), O_("O1", "0", "m", "out"))
    r = ac_solved(c)
    assert r.numeric_mode.value == "high_precision"
    w = 2 * cmath.pi * 1000.0
    ref = -10.0 / complex(0, w * 10e3 * 100e-9)
    got = next(n.phasor for n in r.node_voltages if n.node == "out")
    gotc = complex(float(got.re), float(got.im))
    assert abs(gotc - ref) / abs(ref) <= 1e-9
    assert gotc.imag > 1.0  # integrator phase: +90 deg


def test_ac_differentiator_hp_hand():
    # H = -j w Rf C, Rf=10k, C=100nF, f=1kHz, Vin=10: Vout = -j62.832.
    import cmath
    c = ckt("adif", V_("V1", "10 V", "inn", "0"), C_("C1", "100 nF", "inn", "m"),
            R_("R1", "10 kOhm", "m", "out"), O_("O1", "0", "m", "out"))
    r = ac_solved(c)
    w = 2 * cmath.pi * 1000.0
    ref = -complex(0, w * 10e3 * 100e-9) * 10.0
    got = next(n.phasor for n in r.node_voltages if n.node == "out")
    gotc = complex(float(got.re), float(got.im))
    assert abs(gotc - ref) / abs(ref) <= 1e-9


def test_ac_active_lowpass_two_frequencies():
    # Inverting with Cf across Rf: |H| falls with f; Vout(100Hz) vs (10kHz).
    c = ckt("alp", V_("V1", "10 V", "inn", "0"), R_("R1", "10 kOhm", "inn", "m"),
            R_("R2", "10 kOhm", "m", "out"), C_("C1", "100 nF", "m", "out"),
            O_("O1", "0", "m", "out"))
    r1 = ac_solved(c, "100 Hz")
    r2 = ac_solved(c, "10 kHz")
    m1 = abs(complex(float((next(n.phasor for n in r1.node_voltages if n.node == "out")).re),
                     float((next(n.phasor for n in r1.node_voltages if n.node == "out")).im)))
    m2 = abs(complex(float((next(n.phasor for n in r2.node_voltages if n.node == "out")).re),
                     float((next(n.phasor for n in r2.node_voltages if n.node == "out")).im)))
    # DC gain -1; pole at 1/(2π·10k·100nF) ≈ 159 Hz: |H(100)|>|H(10k)|.
    assert m1 > m2
    assert abs(m1 - 10.0 * abs(1 / complex(1, 100.0 / 159.155))) / 10.0 <= 0.02


def test_ac_power_delivering_conservation():
    c = ckt("apw", V_("V1", "10 V", "inn", "0"), O_("O1", "inn", "out", "out"),
            R_("R1", "1 kOhm", "out", "0"))
    r = ac_solved(c)
    p = analyze_power(r)
    by_ref = {e.ref: e for e in p.elements}
    assert by_ref["O1"].regime == "delivering"
    assert by_ref["R1"].regime == "absorbing"
    assert p.conservation.passed is True


def test_ac_open_loop_driven_inconsistent():
    c = ckt("aol", V_("V1", "1 V", "p", "0"), O_("O1", "p", "0", "out"),
            R_("R1", "1 kOhm", "out", "0"))
    assert solve_ac(c, "1 kHz").status == ACStatus.INCONSISTENT


def test_ac_e_opamp_coexist():
    # Divider 5V -> Va = 2.5; E gain 2 -> Vb = 5; follower -> 5.
    c = ckt("aeo", V_("V1", "5 V", "s", "0"), R_("R0", "1 kOhm", "s", "a"),
            R_("R1", "1 kOhm", "a", "0"),
            Component("E1", "E", Q("2"), {"+": "b", "-": "0"},
                      {"cp": "a", "cn": "0"}),
            R_("R2", "1 kOhm", "b", "0"), O_("O1", "b", "out", "out"),
            R_("R3", "1 kOhm", "out", "0"))
    r = ac_solved(c)
    vo = next(n.phasor for n in r.node_voltages if n.node == "out")
    assert vo.re == Fraction(5) and vo.im == Fraction(0)


# -- D5 transfer ----------------------------------------------------------------------

def test_d5_transfer_inverting():
    c = ckt("tinv", V_("V1", "1 V", "inn", "0"), R_("R1", "10 kOhm", "inn", "m"),
            R_("R2", "100 kOhm", "m", "out"), O_("O1", "0", "m", "out"))
    d = ResponseDefinition("transfer", (voltage_between("inn", "0"),
                                       voltage_between("out", "0"), "V1"))
    sw = frequency_response(c, d, ["1 kHz"])
    h = sw.points[0].value.require_defined()
    assert h.re == Fraction(-10) and h.im == Fraction(0)


def test_d5_transfer_noninverting_follower():
    c = ckt("tfol", V_("V1", "7 V", "inn", "0"), O_("O1", "inn", "out", "out"),
            R_("R1", "1 kOhm", "out", "0"))
    d = ResponseDefinition("transfer", (voltage_between("inn", "0"),
                                       voltage_between("out", "0"), "V1"))
    sw = frequency_response(c, d, ["1 kHz"])
    h = sw.points[0].value.require_defined()
    assert h.re == Fraction(1) and h.im == Fraction(0)


def test_d5_transfer_zero_input_undefined():
    # Input endpoint at an undriven node pair reads zero -> UNDEFINED.
    c = ckt("tzi", V_("V1", "1 V", "inn", "0"), R_("R1", "10 kOhm", "inn", "m"),
            R_("R2", "100 kOhm", "m", "out"), O_("O1", "0", "m", "out"))
    d = ResponseDefinition("transfer", (voltage_between("m", "m"),
                                       voltage_between("out", "0"), "V1"))
    sw = frequency_response(c, d, ["1 kHz"])
    assert not sw.points[0].value.defined


def test_d5_transfer_current_kinds_with_opamp():
    # Zt of transimpedance amp: Vout/I(R1) = -Rf. Hi through R1/R2 chain.
    c = ckt("ttk", I_("I1", "1 mA", "m", "0"), R_("R1", "10 kOhm", "m", "out"),
            O_("O1", "0", "m", "out"))
    d_zt = ResponseDefinition("transfer", (current_through("R1"),
                                          voltage_between("out", "0"), "I1"))
    sw = frequency_response(c, d_zt, ["1 kHz"])
    h = sw.points[0].value.require_defined()
    # I(R1) 1->2: m->out; Vout = -10; Zt = Vout/I(R1) = -10/...+? KCL at m:
    # I1 delivers 1mA into m; (0-Vm)/... Vm=0; I(R1) = (0-(-10))/10k = 1mA.
    # Zt = -10V/1mA = -10kohm.
    assert h.re == Fraction(-10000) and h.im == Fraction(0)


def test_d5_port_impedance_opamp_output():
    # Direct port on the O output leg (out,gnd): Vport = Vout, Iport = -i_o.
    c = ckt("pz", V_("V1", "10 V", "inn", "0"), O_("O1", "inn", "out", "out"),
            R_("R1", "1 kOhm", "out", "0"))
    from academic_core.domain.engineering.ac.problem import build_ac_problem
    from academic_core.domain.engineering.ac.operating_point import ACOperatingPoint
    from academic_core.domain.engineering.ac.topology import reference_net
    from academic_core.domain.engineering.ac.impedance import measure_port
    from academic_core.domain.engineering.math.linsolve import NumericMode
    op = ACOperatingPoint.from_frequency(Q("1 kHz"), reference_net(c.nets))
    prob = build_ac_problem(c, op, NumericMode.AUTO)
    sol = solve_ac(c, "1 kHz")
    z = measure_port(prob, sol, PortDefinition("out", "0"), quantity="impedance")
    assert z.category == ImpedanceCategory.FINITE


def test_d5_frequency_response_active_lowpass():
    from academic_core.domain.engineering.ac.bode import analyze_bode
    c = ckt("frlp", V_("V1", "10 V", "inn", "0"), R_("R1", "10 kOhm", "inn", "m"),
            R_("R2", "10 kOhm", "m", "out"), C_("C1", "100 nF", "m", "out"),
            O_("O1", "0", "m", "out"))
    d = ResponseDefinition("transfer", (voltage_between("inn", "0"),
                                       voltage_between("out", "0"), "V1"))
    sw = frequency_response(c, d, ["10 Hz", "100 Hz", "1 kHz", "100 kHz"])
    assert sw.status == "completed"
    b = analyze_bode(sw)
    assert len(b.points) == 4  # D6 pipeline untouched, works with O


# -- F8-C Thevenin/Norton ------------------------------------------------------------------

def test_f8c_follower_port_zero_rth():
    c = ckt("thf", V_("V1", "10 V", "inn", "0"), O_("O1", "inn", "out", "out"),
            R_("R1", "1 kOhm", "out", "0"))
    t = analyze_thevenin(c, TheveninPort("out", "0"))
    assert t.status in (EquivalentStatus.SOLVED, EquivalentStatus.VERIFIED), t.diagnostics
    assert Fraction(t.v_th.to_base()) == Fraction(10)
    assert t.resistance_kind == ResistanceKind.ZERO
    n = analyze_norton(c, TheveninPort("out", "0"))
    assert n.status == EquivalentStatus.UNDEFINED  # zero Rth: no finite In


def test_f8c_inverting_port_values():
    # Port (out,0): Vth = -100 (Vin=10); Rth = 0 (ideal output).
    c = ckt("thi", V_("V1", "10 V", "inn", "0"), R_("R1", "10 kOhm", "inn", "m"),
            R_("R2", "100 kOhm", "m", "out"), O_("O1", "0", "m", "out"))
    t = analyze_thevenin(c, TheveninPort("out", "0"))
    assert t.status in (EquivalentStatus.SOLVED, EquivalentStatus.VERIFIED), t.diagnostics
    assert Fraction(t.v_th.to_base()) == Fraction(-100)
    assert t.resistance_kind == ResistanceKind.ZERO


def test_f8c_input_port_finite_rth():
    # Port (a,0) driven through R0 (drive NOT across the port):
    # Vth = 9, Rth = 900 (terminating decimals keep display values exact).
    # A port coinciding with an independent source would read Rth = 0
    # (deactivated short) instead.
    c = ckt("thr", V_("V1", "10 V", "s", "0"), R_("R0", "1 kOhm", "s", "a"),
            R_("R1", "9 kOhm", "a", "0"), O_("O1", "a", "out", "out"),
            R_("R2", "1 kOhm", "out", "0"))
    t = analyze_thevenin(c, TheveninPort("a", "0"))
    assert t.status in (EquivalentStatus.SOLVED, EquivalentStatus.VERIFIED), t.diagnostics
    assert Fraction(t.v_th.to_base()) == Fraction(9)
    assert Fraction(t.r_th.to_base()) == Fraction(900)


def test_f8c_nongnd_port_with_opamp():
    # Port across R2 of the inverting amp: V(m)-V(out) = 0-(-100) = 100.
    c = ckt("thn", V_("V1", "10 V", "inn", "0"), R_("R1", "10 kOhm", "inn", "m"),
            R_("R2", "100 kOhm", "m", "out"), O_("O1", "0", "m", "out"))
    t = analyze_thevenin(c, TheveninPort("out", "m"))
    assert t.status in (EquivalentStatus.SOLVED, EquivalentStatus.VERIFIED), t.diagnostics
    assert Fraction(t.v_th.to_base()) == Fraction(-100)


def test_f8c_norton_finite_with_opamp():
    # Same divider port: Vth = 9, Rth = 900 -> In = 10 mA (A->B).
    # Hand: short a-0: R0 carries 10V/1k = 10 mA into the short.
    c = ckt("thn2", V_("V1", "10 V", "s", "0"), R_("R0", "1 kOhm", "s", "a"),
            R_("R1", "9 kOhm", "a", "0"), O_("O1", "a", "out", "out"),
            R_("R2", "1 kOhm", "out", "0"))
    t = analyze_thevenin(c, TheveninPort("a", "0"))
    assert t.status in (EquivalentStatus.SOLVED, EquivalentStatus.VERIFIED), t.diagnostics
    assert Fraction(t.v_th.to_base()) == Fraction(9)
    assert Fraction(t.r_th.to_base()) == Fraction(900)
    n = analyze_norton(c, TheveninPort("a", "0"))
    assert n.status in (EquivalentStatus.SOLVED, EquivalentStatus.VERIFIED), n.diagnostics
    assert Fraction(n.i_n.to_base()) == Fraction(1, 100)
    # Thevenin identity holds with the active follower present.
    assert Fraction(t.v_th.to_base()) / Fraction(t.r_th.to_base()) == Fraction(n.i_n.to_base())


def test_f8c_norton_port_across_ideal_source_undefined():
    # Port coinciding with the 10 V drive: Rth = 0, so Norton has no
    # finite current source (F8-C zero-Rth rule, honest UNDEFINED).
    c = ckt("thn3", V_("V1", "10 V", "inn", "0"), R_("R1", "10 kOhm", "inn", "m"),
            R_("R2", "100 kOhm", "m", "out"), O_("O1", "0", "m", "out"))
    n = analyze_norton(c, TheveninPort("inn", "0"))
    assert n.status == EquivalentStatus.UNDEFINED
    assert "zero" in " ".join(n.diagnostics).lower()


def test_f8c_two_opamps_cascade_port():
    # Follower (10V) feeding a x-10 inverter: port (out2,0).
    # Vth = -100; Rth = 0 (ideal output); Norton UNDEFINED.
    c = ckt("thc", V_("V1", "10 V", "inn", "0"), O_("O1", "inn", "a", "a"),
            R_("R1", "1 kOhm", "a", "0"), R_("R2", "10 kOhm", "a", "m"),
            R_("R3", "100 kOhm", "m", "out2"), O_("O2", "0", "m", "out2"))
    t = analyze_thevenin(c, TheveninPort("out2", "0"))
    assert t.status in (EquivalentStatus.SOLVED, EquivalentStatus.VERIFIED), t.diagnostics
    assert Fraction(t.v_th.to_base()) == Fraction(-100)
    assert t.resistance_kind == ResistanceKind.ZERO


def test_f8c_deactivation_keeps_opamp():
    # If O were deactivated/removed, Zth at (out,0) would read R2-load
    # behavior instead of the ideal-output 0. Direct unit check:
    from academic_core.domain.engineering.thevenin.analysis import (
        _deactivate_sources,
    )
    c = ckt("dk", V_("V1", "10 V", "inn", "0"), O_("O1", "inn", "out", "out"),
            R_("R1", "1 kOhm", "out", "0"))
    dead = _deactivate_sources(c)
    kept = next(x for x in dead.components if x.ref == "O1")
    assert kept.type == "O" and kept.pins == {"+": "inn", "-": "out", "o": "out"}
    assert "V1" in {x.ref for x in dead.components}  # shorted, still present


# -- D7 AC Thevenin/Norton ---------------------------------------------------------------------

def test_d7_vth_zth_follower_exact():
    c = ckt("d7f", V_("V1", "10 V", "inn", "0"), O_("O1", "inn", "out", "out"),
            R_("R1", "1 kOhm", "out", "0"))
    r = analyze_ac_thevenin(c, PortDefinition("out", "0"), "1 kHz")
    assert r.status == ACStatus.SOLVED
    assert r.vth.re == Fraction(10) and r.vth.im == Fraction(0)
    assert r.zth.category == ImpedanceCategory.FINITE
    assert r.zth.value.re == Fraction(0) and r.zth.value.im == Fraction(0)


def test_d7_negative_resistance_opamp():
    # Negative-impedance cell with op-amp: port (p,0): R1 p-m 1k... Design:
    # follower O1 buffering node m, with R1 p-m and E-like positive
    # feedback? Pure-O NIC: O1 o? Use: O1 with + <- p, - <- m, o <- m
    # (follower of p at m), R1 p-m 1k, R2 m-0 1k: Zin?
    # Vm = Vp; I(R1) = 0 -> Zin = infinite. Not negative; instead:
    # Howland-style with O only: needs 4R + O. Vp port; R1 p-a 1k;
    # O1: + <- b, - <- a, o <- out; R2 a-out 1k; R3 b-0 1k; R4 out-b 1k?
    # Solve generally; assert FINITE + record hand value below.
    # Hand: constraint Vb = Va. KCL a: (Va-Vp)/1k + (Va-Vout)/1k = 0.
    # KCL b: Vb/1k + (Vb-Vout)/1k = 0 -> 2Vb - Vout = 0... wait R4 out-b:
    # (Vb-Vout)/1k. So 2Vb = Vout. KCL at p (test 1V... use Vth-style):
    # drive Vp with source via test: Itest entering p = (Vp-Va)/1k.
    # From a: 2Va - Vp - Vout = 0; Vb = Va; 2Va - Vout = 0 -> Vout = 2Va.
    # Then 2Va - Vp - 2Va = 0 -> Vp = 0?! For test Vp=1V: contradiction ->
    # INCONSISTENT (pole at balance). Choose unbalanced: R4 = 2k:
    # KCL b: Vb/1k + (Vb-Vout)/2k = 0 -> 3Vb - Vout = 0 (k-mA units V/1k).
    # Vout = 3Va. KCL a: (Va-Vp) + (Va-Vout) = 0 -> 2Va - Vp - 3Va = 0
    # -> -Va - Vp = 0 -> Va = -Vp. Itest = (Vp-Va)/1k = 2Vp/1k.
    # Zth = Vp/Itest = 500 ohm. Positive. For negative, mirror: swap R4
    # to the a side? Set R2 (a-out) = 2k, R4 (out-b) = 1k:
    # KCL b: Vb + (Vb-Vout) = 0 -> 2Vb = Vout. KCL a: (Va-Vp) + (Va-Vout)/2
    # = 0 -> 2Va - 2Vp + Va - Vout = 0 -> 3Va - 2Vp - 2Va = 0 (Vout=2Va)
    # -> Va = 2Vp. Itest = (Vp-2Vp)/1k = -Vp/1k -> Zth = -1kohm. NEGATIVE.
    c = ckt("d7n", R_("R1", "1 kOhm", "p", "a"), O_("O1", "b", "a", "out"),
            R_("R2", "2 kOhm", "a", "out"), R_("R3", "1 kOhm", "b", "0"),
            R_("R4", "1 kOhm", "out", "b"))
    r = analyze_ac_thevenin(c, PortDefinition("p", "0"), "1 kHz")
    assert r.status == ACStatus.SOLVED
    assert r.zth.category == ImpedanceCategory.FINITE
    assert r.zth.value.re == Fraction(-1000) and r.zth.value.im == Fraction(0)


def test_d7_dependents_change_zth_with_opamp():
    mk = lambda tag, extra: ckt(tag, V_("V1", "10 V", "inn", "0"),
                                R_("R1", "1 kOhm", "inn", "out"),
                                R_("R2", "1 kOhm", "out", "0"), *extra)
    r_off = analyze_ac_thevenin(mk("z0", []), PortDefinition("out", "0"), "1 kHz")
    r_on = analyze_ac_thevenin(
        mk("z1", [O_("O1", "inn", "out", "out")]), PortDefinition("out", "0"), "1 kHz")
    assert r_off.zth.value.re == Fraction(500)
    assert r_on.zth.value.re == Fraction(0)  # ideal O output shorts the port
    assert r_on.vth.re == Fraction(10)


# -- metamorphic -----------------------------------------------------------------------------

def test_meta_input_swap_invariant_opamp():
    # V+ - V- = 0 is symmetric: swapping in+/in- changes nothing.
    mk = lambda tag, p, m: ckt(tag, V_("V1", "10 V", "inn", "0"),
                               R_("R1", "1 kOhm", "inn", "a"),
                               R_("R2", "1 kOhm", "a", "0"),
                               O_("O1", p, m, "out"),
                               R_("R3", "1 kOhm", "out", "0"))
    # O as comparator-buffer: + <- a (5V divider), - <- out: follower.
    r1 = assert_dc_solved(solve_linear_dc(mk("m1", "a", "out")))
    r2 = assert_dc_solved(solve_linear_dc(mk("m2", "out", "a")))
    # m2: + <- out, - <- a: still follower (constraint symmetric).
    assert dc_voltages(r1)["out"] == dc_voltages(r2)["out"] == Decimal("5")


def test_meta_source_scaling_linear():
    mk = lambda tag, v: ckt(tag, V_("V1", v, "inn", "0"),
                            R_("R1", "10 kOhm", "inn", "m"),
                            R_("R2", "100 kOhm", "m", "out"),
                            O_("O1", "0", "m", "out"))
    assert dc_voltages(assert_dc_solved(solve_linear_dc(mk("s1", "1 V"))))["out"] == Decimal("-10")
    assert dc_voltages(assert_dc_solved(solve_linear_dc(mk("s2", "3 V"))))["out"] == Decimal("-30")


def test_meta_resistor_scaling_homogeneous():
    # All R x10: inverting gain unchanged (-100k/10k = -1M/100k).
    mk = lambda tag, k: ckt(tag, V_("V1", "10 V", "inn", "0"),
                            R_("R1", f"{10 * k} kOhm", "inn", "m"),
                            R_("R2", f"{100 * k} kOhm", "m", "out"),
                            O_("O1", "0", "m", "out"))
    assert dc_voltages(assert_dc_solved(solve_linear_dc(mk("r1", 1))))["out"] == Decimal("-100")
    assert dc_voltages(assert_dc_solved(solve_linear_dc(mk("r2", 10))))["out"] == Decimal("-100")


def test_meta_node_rename_digest_equal():
    c1 = ckt("n1", V_("V1", "10 V", "inn", "0"), R_("R1", "1 kOhm", "inn", "0"),
             O_("O1", "inn", "out", "out"), R_("R2", "1 kOhm", "out", "0"))
    c2 = ckt("n2", V_("V1", "10 V", "src", "0"), R_("R1", "1 kOhm", "src", "0"),
             O_("O1", "src", "dst", "dst"), R_("R2", "1 kOhm", "dst", "0"))
    r1, r2 = (assert_dc_solved(solve_linear_dc(c)) for c in (c1, c2))
    assert r1.provenance["digest"] != r2.provenance["digest"]  # names differ
    assert dc_voltages(r1)["out"] == dc_voltages(r2)["dst"] == Decimal("10")


def test_meta_component_permutation_identical():
    comps = [V_("V1", "10 V", "inn", "0"), R_("R1", "10 kOhm", "inn", "m"),
             R_("R2", "100 kOhm", "m", "out"), O_("O1", "0", "m", "out")]
    r1 = assert_dc_solved(solve_linear_dc(ckt("p", *comps)))
    r2 = assert_dc_solved(solve_linear_dc(ckt("p", *reversed(comps))))
    assert r1.provenance["digest"] == r2.provenance["digest"]
    d1, d2 = r1.to_dict(), r2.to_dict()
    d1["provenance"].pop("timestamp")
    d2["provenance"].pop("timestamp")
    assert d1 == d2
    assert dc_voltages(r1) == dc_voltages(r2)


def test_meta_opamp_permutation_two_stage():
    # Swapping the ORDER of two op-amps in the component list changes nothing.
    comps = [V_("V1", "2 V", "inn", "0"), O_("O1", "inn", "a", "a"),
             R_("R1", "10 kOhm", "a", "m"), R_("R2", "20 kOhm", "m", "out"),
             O_("O2", "0", "m", "out"), R_("R3", "1 kOhm", "out", "0")]
    r1 = assert_dc_solved(solve_linear_dc(ckt("q1", *comps)))
    ro = [c for c in comps if c.ref != "O1"] + [c for c in comps if c.ref == "O1"]
    r2 = assert_dc_solved(solve_linear_dc(ckt("q2", *ro)))
    assert dc_voltages(r1)["out"] == dc_voltages(r2)["out"] == Decimal("-4")


def test_meta_deterministic_repeat():
    c = ckt("dr", V_("V1", "3 V", "s1", "0"), V_("V2", "1 V", "s2", "0"),
            O_("O1", "s1", "m1", "a"), R_("R1", "10 kOhm", "m1", "0"),
            R_("R2", "10 kOhm", "a", "m1"), O_("O2", "s2", "m2", "b"),
            R_("R3", "10 kOhm", "m2", "0"), R_("R4", "10 kOhm", "b", "m2"))
    r1, r2 = solve_linear_dc(c), solve_linear_dc(c)
    assert r1.provenance["digest"] == r2.provenance["digest"]
    d1, d2 = r1.to_dict(), r2.to_dict()
    d1["provenance"].pop("timestamp")
    d2["provenance"].pop("timestamp")
    assert d1 == d2


# -- generality ----------------------------------------------------------------------------------

def follower_chain(n):
    comps = [V_("V1", "7 V", "in", "0")]
    prev = "in"
    for i in range(1, n + 1):
        comps.append(O_(f"O{i}", prev, f"m{i}", f"m{i}"))
        comps.append(R_(f"R{i}", "1 kOhm", f"m{i}", "0"))
        prev = f"m{i}"
    return ckt(f"fchain{n}", *comps)


def test_generality_dc_chain_scales():
    for n in (1, 2, 4, 8, 16, 32, 64):
        r = assert_dc_solved(solve_linear_dc(follower_chain(n)))
        v = dc_voltages(r)
        for i in range(1, n + 1):
            assert v[f"m{i}"] == Decimal("7"), (n, i)


def test_generality_ac_chain_scales():
    for n in (1, 2, 4, 8, 16):
        r = ac_solved(follower_chain(n))
        for i in range(1, n + 1):
            ph = next(x.phasor for x in r.node_voltages if x.node == f"m{i}")
            assert abs(Decimal(str(ph.re)) - Decimal("7")) <= Decimal("1E-25"), (n, i)
            assert abs(Decimal(str(ph.im))) <= Decimal("1E-25")


def test_generality_topologies_with_opamps():
    # Bridge with op-amp buffer on the bridge output.
    bridge = ckt("gb", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "a"),
                 R_("R2", "2 kOhm", "in", "b"), R_("R3", "1 kOhm", "a", "0"),
                 R_("R4", "2 kOhm", "b", "0"), O_("O1", "a", "c", "c"),
                 R_("R5", "1 kOhm", "c", "0"))
    assert solve_linear_dc(bridge).status == SolveStatus.SOLVED
    # Mesh with op-amp.
    mesh = ckt("gm", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "a"),
               R_("R2", "1 kOhm", "a", "b"), R_("R3", "1 kOhm", "b", "0"),
               R_("R4", "1 kOhm", "in", "b"), O_("O1", "a", "c", "c"),
               R_("R5", "1 kOhm", "c", "0"))
    assert solve_linear_dc(mesh).status == SolveStatus.SOLVED
    # Star with op-amp summer.
    star = ckt("gs", V_("V1", "1 V", "a", "0"), V_("V2", "2 V", "b", "0"),
               R_("R1", "10 kOhm", "a", "m"), R_("R2", "10 kOhm", "b", "m"),
               R_("R3", "10 kOhm", "m", "out"), R_("R4", "1 kOhm", "c", "0"),
               O_("O1", "c", "m", "out"), R_("R5", "1 kOhm", "c", "m"))
    # + driven via divider c-m? c connects R4(0), R5(m), O1.+: constraint
    # Vc = Vm; KCL m: (Vm-1)+(Vm-2)+(Vm-Vout) = 0 (10k units).
    r = assert_dc_solved(solve_linear_dc(star))
    # KCL c: Vc/1 + (Vc-Vm)/1 = 0 -> 2Vc = Vm. With Vm = Vc: Vc = 0?!
    # Then KCL m: (0-1)+(0-2)+(0-Vout) = 0 -> Vout = -3. Consistent.
    assert dc_voltages(r)["out"] == Decimal("-3")
    # K3,3 resistive core + one op-amp buffer.
    comps = [V_("V1", "10 V", "a1", "0")]
    k = 0
    for a in ("a1", "a2", "a3"):
        for b in ("b1", "b2", "b3"):
            k += 1
            comps.append(R_(f"R{k}", "1 kOhm", a, b))
    comps.append(O_("O1", "a2", "c", "c"))
    comps.append(R_(f"R{k + 1}", "1 kOhm", "c", "0"))
    k33 = ckt("gk", *comps)
    assert solve_linear_dc(k33).status == SolveStatus.SOLVED
    # Multigraph + high-degree + non-GND port target.
    multi = ckt("gx", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "x"),
                R_("R2", "2 kOhm", "in", "x"), R_("R3", "3 kOhm", "in", "x"),
                O_("O1", "x", "y", "y"), R_("R4", "1 kOhm", "y", "0"),
                R_("R5", "1 kOhm", "y", "z"), R_("R6", "1 kOhm", "z", "0"))
    rm = assert_dc_solved(solve_linear_dc(multi))
    assert rm.conservation_checks.passed is True


# -- ngspice (E-macro oracle, bounded error) ----------------------------------------------------------

def _ng_backend():
    from academic_core.infrastructure.ngspice import NgSpiceBackend

    b = NgSpiceBackend()
    return b if b.detect().verified else None


NG = _ng_backend()


def _ng_version():
    import subprocess

    out = subprocess.run(
        ["C:\\Users\\dmart\\Documents\\ngspice-47_64\\Spice64\\bin\\ngspice_con.exe",
         "--version"], capture_output=True, text=True, timeout=60)
    lines = (out.stdout + out.stderr).splitlines()
    return next((ln for ln in lines if "ngspice-47" in ln), "unknown")


def _ng_op(deck):
    assert NG is not None
    res = NG.simulate(deck, analyses=("op",))
    assert res.status == "COMPLETED", res.raw_stderr
    return {n: float(s.samples[0]) for n, s in res.signals.items()}


def test_ngspice_version_recorded():
    if NG is None:
        pytest.skip("ngspice 47 verified backend unavailable")
    assert "ngspice-47" in _ng_version()


def test_ngspice_emacro_oracle_follower_dc():
    # E-macro μ=1e9 follower: closed-loop error ~ 1/1e9. Hand = 10.
    if NG is None:
        pytest.skip("ngspice 47 verified backend unavailable")
    c = ckt("ngf", V_("V1", "10 V", "inn", "0"), O_("O1", "inn", "out", "out"),
            R_("R1", "1 kOhm", "out", "0"))
    assert dc_voltages(assert_dc_solved(solve_linear_dc(c)))["out"] == Decimal("10")
    sigs = _ng_op("* fol macro\nVin inn 0 DC 10\nE1 out 0 inn out 1e9\n"
                  "R1 out 0 1k\n.op\n.end\n")
    assert abs(sigs["v(out)"] - 10.0) <= 1e-6


def test_ngspice_emacro_oracle_inverting_dc():
    # Closed-loop gain -10 (β = 1/11); macro error ~ |G|/(μ·β) < 1e-6.
    if NG is None:
        pytest.skip("ngspice 47 verified backend unavailable")
    sigs = _ng_op("* inv macro\nVin inn 0 DC 10\nRin inn m 10k\n"
                  "Rfb m out 100k\nE1 out 0 0 m 1e9\n.op\n.end\n")
    assert abs(sigs["v(out)"] + 100.0) <= 1e-3


def test_ngspice_emacro_oracle_noninverting_dc():
    if NG is None:
        pytest.skip("ngspice 47 verified backend unavailable")
    sigs = _ng_op("* nin macro\nVin inn 0 DC 2\nE1 out 0 inn m 1e9\n"
                  "R1 m 0 10k\nR2 out m 20k\n.op\n.end\n")
    assert abs(sigs["v(out)"] - 6.0) <= 1e-5


def test_ngspice_emacro_oracle_summer_dc():
    if NG is None:
        pytest.skip("ngspice 47 verified backend unavailable")
    sigs = _ng_op("* sum macro\nV1 a 0 DC 1\nV2 b 0 DC 2\nR1 a m 10k\n"
                  "R2 b m 10k\nR3 m out 10k\nE1 out 0 0 m 1e9\n.op\n.end\n")
    assert abs(sigs["v(out)"] + 3.0) <= 1e-5


def test_ngspice_emacro_oracle_ac_integrator():
    # Integrator at 1 kHz: hand H = +j1.5915 (see test_ac_integrator_hp_hand).
    import cmath
    if NG is None:
        pytest.skip("ngspice 47 verified backend unavailable")
    from academic_core.domain.engineering.simulation import ACAnalysis
    deck = ("* int macro\nVin inn 0 DC 0 AC 10\nRin inn m 10k\n"
            "Cf m out 100n\nE1 out 0 0 m 1e9\n"
            ".ac lin 2 1000 1001\n.print ac v(out)\n.end\n")
    res = NG.simulate(deck, analyses=(ACAnalysis(sweep_type="lin", points=2,
                                                fstart="1000", fstop="1001"),))
    assert res.status == "COMPLETED"
    w = 2 * cmath.pi * 1000.0
    ref = -10.0 / complex(0, w * 10e3 * 100e-9)
    got = res.sample_complex_at("v(out)", "1000")
    assert abs(got - ref) / abs(ref) <= 0.02


def test_ngspice_emacro_oracle_ac_transfer():
    # Hv of x10 inverter at 1 kHz via macro vs D5 transfer (exact -10).
    if NG is None:
        pytest.skip("ngspice 47 verified backend unavailable")
    from academic_core.domain.engineering.simulation import ACAnalysis
    deck = ("* inv ac macro\nVin inn 0 DC 0 AC 1\nRin inn m 10k\n"
            "Rfb m out 100k\nE1 out 0 0 m 1e9\n"
            ".ac lin 2 1000 1001\n.print ac v(out) v(inn)\n.end\n")
    res = NG.simulate(deck, analyses=(ACAnalysis(sweep_type="lin", points=2,
                                                fstart="1000", fstop="1001"),))
    assert res.status == "COMPLETED"
    h = res.sample_complex_at("v(out)", "1000") / res.sample_complex_at("v(inn)", "1000")
    assert abs(h + 10.0) / 10.0 <= 0.02


# -- provenance / security / immutability ---------------------------------------------------------------

def test_provenance_opamp_identity():
    c = ckt("pv", V_("V1", "10 V", "inn", "0"), O_("O1", "inn", "out", "out"),
            R_("R1", "1 kOhm", "out", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    assert r.system_summary["ideal_opamps"] == [
        {"ref": "O1", "in_p": "inn", "in_n": "out", "out": "out"}]
    assert "timestamp" not in r.provenance["digest"]
    r2 = assert_dc_solved(solve_linear_dc(c))
    assert r2.provenance["digest"] == r.provenance["digest"]


def test_provenance_rvi_untouched():
    c = ckt("pr", V_("V1", "10 V", "a", "0"), R_("R1", "1 kOhm", "a", "0"))
    r = assert_dc_solved(solve_linear_dc(c))
    assert "ideal_opamps" not in r.system_summary
    assert set(r.system_summary) == {"n_nodes", "n_voltage_sources", "n_unknowns",
                                     "reference_node"}


def test_provenance_ac_opamp_identity():
    c = ckt("pva", V_("V1", "10 V", "inn", "0"), O_("O1", "inn", "out", "out"),
            R_("R1", "1 kOhm", "out", "0"))
    r = ac_solved(c)
    assert r.provenance["ideal_opamps"] == [
        {"ref": "O1", "in_p": "inn", "in_n": "out", "out": "out"}]
    assert solve_ac(c, "1 kHz").digest == r.digest


def test_security_ast_gates():
    import pathlib
    roots = [pathlib.Path(__file__).parent.parent / "src" / "academic_core" /
             "domain" / "engineering" / p
             for p in ("mna/problem.py", "mna/solver.py", "mna/dependent.py",
                       "mna/errors.py", "ac/problem.py", "ac/solution.py",
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


def test_immutability_snapshot():
    c = ckt("im", V_("V1", "10 V", "inn", "0"), O_("O1", "inn", "out", "out"),
            R_("R1", "1 kOhm", "out", "0"))
    before = [(e.ref, e.type, str(e.value.to_base()) if e.value else None,
               dict(e.pins), dict(e.parameters)) for e in c.components]
    solve_linear_dc(c)
    solve_ac(c, "1 kHz")
    from academic_core.domain.engineering.ac.impedance import measure_port
    from academic_core.domain.engineering.ac.problem import build_ac_problem
    from academic_core.domain.engineering.ac.operating_point import ACOperatingPoint
    from academic_core.domain.engineering.ac.topology import reference_net
    from academic_core.domain.engineering.math.linsolve import NumericMode
    op = ACOperatingPoint.from_frequency(Q("1 kHz"), reference_net(c.nets))
    prob = build_ac_problem(c, op, NumericMode.AUTO)
    sol = solve_ac(c, "1 kHz")
    measure_port(prob, sol, PortDefinition("out", "0"))
    analyze_ac_thevenin(c, PortDefinition("out", "0"), "1 kHz")
    after = [(e.ref, e.type, str(e.value.to_base()) if e.value else None,
              dict(e.pins), dict(e.parameters)) for e in c.components]
    assert before == after


# -- performance (follower chains; reuse generality builder) ------------------------------


def test_perf_dc_scales():
    # Timings diagnostic only (no wall-clock bound asserted by design).
    marks = {}
    for n in (16, 32, 64):
        t0 = time.perf_counter()
        r = assert_dc_solved(solve_linear_dc(follower_chain(n)))
        dt = time.perf_counter() - t0
        marks[n] = round(dt, 2)
        assert dc_voltages(r)[f"m{n}"] == Decimal("7")
    print(f"\nF8-F DC perf seconds by N: {marks}")


def test_perf_ac_scales():
    # Timings diagnostic only (no wall-clock bound asserted by design).
    marks = {}
    for n in (16, 32, 64):
        t0 = time.perf_counter()
        r = solve_ac(follower_chain(n), "1 kHz")
        dt = time.perf_counter() - t0
        marks[n] = round(dt, 2)
        assert r.status == ACStatus.SOLVED, (n, r.diagnostics)
    print(f"\nF8-F AC perf seconds by N: {marks}")
