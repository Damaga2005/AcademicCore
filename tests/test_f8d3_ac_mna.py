"""F8-D3 General AC MNA: operating point, stamps, KCL/KVL, refs, oracle.

Conventions: EXACT assertions are representation-exact. HIGH_PRECISION
assertions carry explicit tolerances. Analytical expected values are
transcribed literals and direct formulas evaluated in this file —
never outputs of the engine under test. ngspice 47 is an external
oracle (comparison with explicit tolerances, both directions
unprivileged); it never generates unit-test expected values.

Empirically established on 2026-09-13 (ngspice 47, verified backend):
* `ac <mag>` is PEAK amplitude (10 -> v = 10+0j on 1k load);
* `i(v1)` uses the + -> - through-source reference direction, i.e. it
  equals the D3 branch current directly (10V/1k probe: -0.01, no flip);
* current-source branches cannot be probed (`i1#branch` unavailable and
  its print vector poisons table parsing), so oracle netlists use
  V + R/L/C only; I-source behavior is pinned by analytical
  references plus physical KCL instead.
"""
import ast
import json
import pathlib
from decimal import Decimal
from fractions import Fraction

import pytest

from academic_core.domain.engineering.ac import (
    ACOperatingPoint,
    ACStatus,
    build_ac_problem,
    magnitude,
    phase,
    rms_from_peak,
    solve_ac,
    solve_ac_problem,
    to_polar,
)
from academic_core.domain.engineering.ac.errors import (
    ACFrequencyError,
    ACModeError,
    ACPhaseError,
    DimensionalityError,
    FloatingCircuitError,
    InvalidCircuitError,
    MissingReferenceError,
    UnsupportedElementError,
)
from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.math import DecimalComplex, RationalComplex
from academic_core.domain.engineering.math.linsolve import NumericMode
from academic_core.domain.engineering.math.trig import make_context
from academic_core.domain.engineering.units import FREQUENCY, parse_quantity

CTX = make_context()
TOL = Decimal("1E-40")
PI50 = Decimal("3.14159265358979323846264338327950288419716939937510")


def Q(text):
    return parse_quantity(text)


def R_(ref, value, n1, n2):
    return Component(ref, "R", Q(value), {"1": n1, "2": n2})


def L_(ref, value, n1, n2):
    return Component(ref, "L", Q(value), {"1": n1, "2": n2})


def C_(ref, value, n1, n2):
    return Component(ref, "C", Q(value), {"1": n1, "2": n2})


def V_(ref, value, np_, nm, phase_=0, punit="deg", extra=None):
    params = {}
    if not (isinstance(phase_, int) and phase_ == 0):
        params["phase"] = phase_
    if punit != "deg":
        params["phase_unit"] = punit
    if extra:
        params.update(extra)
    return Component(ref, "V", Q(value), {"+": np_, "-": nm}, dict(params))


def I_(ref, value, np_, nm, phase_=0, punit="deg", extra=None):
    params = {}
    if not (isinstance(phase_, int) and phase_ == 0):
        params["phase"] = phase_
    if punit != "deg":
        params["phase_unit"] = punit
    if extra:
        params.update(extra)
    return Component(ref, "I", Q(value), {"+": np_, "-": nm}, dict(params))


def ckt(name, *comps):
    c = Circuit(name)
    for e in comps:
        c.add(e)
    return c


def cmul(a, b):
    ar, ai = a
    br, bi = b
    return (CTX.subtract(CTX.multiply(ar, br), CTX.multiply(ai, bi)),
            CTX.add(CTX.multiply(ar, bi), CTX.multiply(ai, br)))


def cdiv(a, b):
    ar, ai = a
    br, bi = b
    den = CTX.add(CTX.multiply(br, br), CTX.multiply(bi, bi))
    return (CTX.divide(CTX.add(CTX.multiply(ar, br), CTX.multiply(ai, bi)), den),
            CTX.divide(CTX.subtract(CTX.multiply(ai, br), CTX.multiply(ar, bi)), den))


def close_dc(got, want_re, want_im, tol=TOL):
    return (abs(CTX.subtract(got.re, Decimal(str(want_re)))) <= tol
            and abs(CTX.subtract(got.im, Decimal(str(want_im)))) <= tol)


def phasedeg(z):
    from academic_core.domain.engineering.math.trig import decimal_pi

    return CTX.multiply(phase(z), CTX.divide(Decimal(180), decimal_pi()))


# -- 1. operating point ---------------------------------------------------------------

def test_op_construction_and_conventions():
    op = ACOperatingPoint.from_frequency(Q("1 kHz"), "0")
    assert op.frequency.to_base() == Decimal(1000)
    assert op.frequency_unit == "kHz"
    assert op.angular_unit == "rad/s"
    assert op.time_convention == "e^(+jwt)"
    assert op.amplitude_convention == "peak"
    assert op.reference_node == "0"
    assert "atan2" in op.phase_convention


def test_op_omega_involves_pi():
    op = ACOperatingPoint.from_frequency(Q("1000 Hz"), "0")
    ratio = CTX.divide(op.omega, CTX.multiply(Decimal(2), Decimal(1000)))
    assert abs(CTX.subtract(ratio, PI50)) <= Decimal("1E-45")


def test_op_rejects_zero_frequency():
    with pytest.raises(ACFrequencyError, match="(?i)f = 0|DC reduction"):
        ACOperatingPoint.from_frequency(Q("0 Hz"), "0")


def test_op_rejects_negative_frequency():
    with pytest.raises(ACFrequencyError, match="(?i)product boundary"):
        ACOperatingPoint.from_frequency(Q("-50 Hz"), "0")


def test_op_rejects_wrong_dimension():
    with pytest.raises(ACFrequencyError):
        ACOperatingPoint.from_frequency(Q("5 V"), "0")
    with pytest.raises(ACFrequencyError):
        ACOperatingPoint.from_frequency(Q("10 s"), "0")


def test_op_reference_mismatch_rejected():
    c = ckt("m", V_("V1", "10 V", "in", "0"), R_("R1", "1 kΩ", "in", "0"))
    op = ACOperatingPoint.from_frequency(Q("1 kHz"), "GND")
    with pytest.raises(InvalidCircuitError, match="reference"):
        build_ac_problem(c, op)


# -- 2. units / frequency / degenerate values -----------------------------------------------

def test_units_hz_prefixes():
    assert Q("1 kHz").to_base() == Decimal(1000)
    assert Q("1 MHz").to_base() == Decimal(1000000)
    assert Q("50 Hz").to_base() == Decimal(50)
    assert Q("50 Hz").dimension == FREQUENCY


def test_radian_is_not_a_unit_dimension():
    from academic_core.domain.engineering.units import UnitError

    for bad in ("rad", "rad/s", "deg"):
        try:
            q = parse_quantity(f"1 {bad}")
        except UnitError:
            continue
        assert q.dimension == (0, 0, 0, 0, 0, 0, 0), bad  # dimensionless if parseable
    op = ACOperatingPoint.from_frequency(Q("1 kHz"), "0")
    assert op.angular_unit == "rad/s"  # documentary label, not physics


def test_value_dimensions_checked():
    bad = ckt("b", Component("R1", "R", Q("5 V"), {"1": "a", "2": "0"}),
              V_("V1", "1 V", "a", "0"))
    assert solve_ac(bad, "1 kHz").status == ACStatus.INVALID
    bad2 = ckt("b2", Component("C1", "C", Q("2 H"), {"1": "a", "2": "0"}),
               V_("V1", "1 V", "a", "0"))
    assert solve_ac(bad2, "1 kHz").status == ACStatus.INVALID


def test_zero_and_negative_rlc_rejected():
    for comp in (R_("R1", "0 ohm", "a", "0"), L_("L1", "0 H", "a", "0"),
                 C_("C1", "0 F", "a", "0"), R_("R1", "-5 ohm", "a", "0"),
                 L_("L1", "-1 mH", "a", "0"), C_("C1", "-1 uF", "a", "0")):
        c = ckt("z", V_("V1", "1 V", "a", "0"), comp)
        assert solve_ac(c, "1 kHz").status == ACStatus.INVALID, comp.ref


def test_missing_value_rejected():
    c = Circuit("m")
    c.add(Component("R1", "R", None, {"1": "a", "2": "0"}))
    c.add(V_("V1", "1 V", "a", "0"))
    assert solve_ac(c, "1 kHz").status == ACStatus.INVALID


def test_unsupported_diode_rejected_as_unsupported():
    c = Circuit("d")
    c.add(Component("D1", "D", None, {"A": "a", "K": "0"}))
    c.add(V_("V1", "1 V", "a", "0"))
    assert solve_ac(c, "1 kHz").status == ACStatus.UNSUPPORTED


# -- 3. phase -------------------------------------------------------------------------------

def test_phase_defaults_to_zero():
    c = ckt("p", V_("V1", "10 V", "in", "0"), R_("R1", "1 kΩ", "in", "0"))
    r = solve_ac(c, "1 kHz")
    assert r.status == ACStatus.SOLVED
    assert r.current_of("V1") == RationalComplex(Fraction(-1, 100), Fraction(0))


@pytest.mark.parametrize("deg, want_re, want_im", [
    (0, 10, 0), (90, 0, 10), (180, -10, 0), (-90, 0, -10),
])
def test_axis_phases_exact(deg, want_re, want_im):
    c = ckt("ax", V_("V1", "10 V", "in", "0", phase_=deg),
            R_("R1", "1 kΩ", "in", "0"))
    r = solve_ac(c, "1 kHz")
    assert r.status == ACStatus.SOLVED
    assert r.numeric_mode == NumericMode.EXACT
    v = r.voltage_of("in")
    assert v == RationalComplex(Fraction(want_re), Fraction(want_im))


def test_phase_45_is_hp_and_matches_transcription():
    s = CTX.divide(CTX.sqrt(Decimal(2)), Decimal(2))  # sqrt(2)/2, independent path
    c = ckt("p45", V_("V1", "10 V", "in", "0", phase_=45),
            R_("R1", "1 kΩ", "in", "0"))
    r = solve_ac(c, "1 kHz")
    assert r.status == ACStatus.SOLVED
    assert r.numeric_mode == NumericMode.HIGH_PRECISION
    v = r.voltage_of("in")
    assert close_dc(v, CTX.multiply(Decimal(10), s), CTX.multiply(Decimal(10), s),
                    Decimal("1E-40"))


def test_phase_radians_pi_over_2():
    c = ckt("pr", V_("V1", "10 V", "in", "0", phase_="1.57079632679489661923132169163975",
                      punit="rad"), R_("R1", "1 kΩ", "in", "0"))
    r = solve_ac(c, "1 kHz")
    assert r.status == ACStatus.SOLVED
    v = r.voltage_of("in")
    assert abs(CTX.subtract(magnitude(v), Decimal(10))) <= Decimal("1E-30")
    assert abs(v.re) <= Decimal("1E-30")


def test_phase_invalid_unit_rejected():
    c = ckt("pu", V_("V1", "10 V", "in", "0", phase_=30, punit="grad"),
            R_("R1", "1 kΩ", "in", "0"))
    assert solve_ac(c, "1 kHz").status == ACStatus.INVALID


def test_phase_float_rejected():
    c = ckt("pf", V_("V1", "10 V", "in", "0", phase_=45.0),
            R_("R1", "1 kΩ", "in", "0"))
    assert solve_ac(c, "1 kHz").status == ACStatus.INVALID


def test_phase_unparseable_rejected():
    c = ckt("px", V_("V1", "10 V", "in", "0", phase_="soon"),
            R_("R1", "1 kΩ", "in", "0"))
    assert solve_ac(c, "1 kHz").status == ACStatus.INVALID


def test_per_source_frequency_metadata_compatible_accepted():
    extra = {"frequency": "1 kHz"}
    c = ckt("fm", V_("V1", "10 V", "in", "0", extra=extra),
            R_("R1", "1 kΩ", "in", "0"))
    assert solve_ac(c, "1 kHz").status == ACStatus.SOLVED


def test_per_source_frequency_metadata_conflict_rejected():
    extra = {"frequency": "2 kHz"}
    c = ckt("fx", V_("V1", "10 V", "in", "0", extra=extra),
            R_("R1", "1 kΩ", "in", "0"))
    st = solve_ac(c, "1 kHz")
    assert st.status == ACStatus.INVALID
    assert any("frequency" in d for d in st.diagnostics)


def test_forced_exact_with_lc_refused():
    c = ckt("fe", V_("V1", "1 V", "in", "0"), R_("R1", "1 kΩ", "in", "out"),
            C_("C1", "1 uF", "out", "0"))
    assert solve_ac(c, "1 kHz", NumericMode.EXACT).status == ACStatus.INVALID


def test_forced_exact_with_45deg_refused():
    c = ckt("fe2", V_("V1", "1 V", "in", "0", phase_=45),
            R_("R1", "1 kΩ", "in", "0"))
    assert solve_ac(c, "1 kHz", NumericMode.EXACT).status == ACStatus.INVALID


def test_phase_at_pmpi_edge_and_quadrants():
    c = ckt("pe", V_("V1", "10 V", "in", "0", phase_=180),
            R_("R1", "1 kΩ", "in", "0"))
    r = solve_ac(c, "1 kHz")
    assert r.status == ACStatus.SOLVED
    assert phase(r.voltage_of("in")) == PI50  # -180 deg maps to +pi, deterministic
    c2 = ckt("pe2", V_("V1", "10 V", "in", "0", phase_="179.9999"),
             R_("R1", "1 kΩ", "in", "0"))
    r2 = solve_ac(c2, "1 kHz")
    d = abs(CTX.subtract(abs(phase(r2.voltage_of("in"))), PI50))
    assert d <= Decimal("1E-4") and d > 0
    c3 = ckt("pe3", V_("V1", "10 V", "in", "0", phase_="-179.9999"),
             R_("R1", "1 kΩ", "in", "0"))
    r3 = solve_ac(c3, "1 kHz")
    assert phase(r3.voltage_of("in")) < 0  # negative side of the cut
    assert r2.digest != r3.digest  # the two sides are distinct solutions


@pytest.mark.parametrize("deg, re_sign, im_sign", [
    (0, 1, 0), (90, 0, 1), (180, -1, 0), (-90, 0, -1), (45, 1, 1),
])
def test_phase_quadrants_cartesian_polar_signs(deg, re_sign, im_sign):
    c = ckt("q", V_("V1", "7 V", "in", "0", phase_=deg),
            R_("R1", "1 kΩ", "in", "0"))
    r = solve_ac(c, "7 kHz")
    assert r.status == ACStatus.SOLVED
    v = r.voltage_of("in")
    mag, ang = to_polar(v)
    assert abs(CTX.subtract(mag, Decimal(7))) <= Decimal("1E-30")
    if re_sign > 0:
        assert v.re > 0
    elif re_sign < 0:
        assert v.re < 0
    else:
        assert abs(v.re) <= Decimal("1E-30")
    if im_sign > 0:
        assert v.im > 0
    elif im_sign < 0:
        assert v.im < 0
    else:
        assert abs(v.im) <= Decimal("1E-30")
    if deg == 45:
        assert abs(CTX.subtract(phasedeg(v), Decimal(45))) <= Decimal("1E-30")


# -- 4. stamps / MNA -------------------------------------------------------------------------------

def test_r_divider_exact_stamp():
    c = ckt("div", V_("V1", "10 V", "in", "0"), R_("R1", "1 kΩ", "in", "out"),
            R_("R2", "1 kΩ", "out", "0"))
    r = solve_ac(c, "1 kHz")
    assert r.status == ACStatus.SOLVED
    assert r.voltage_of("out") == RationalComplex(Fraction(5), Fraction(0))
    assert r.current_of("R1") == RationalComplex(Fraction(1, 200), Fraction(0))


def test_v_constraint_and_branch_vs():
    c = ckt("vs", V_("V1", "10 V", "a", "b", phase_=90),
            R_("R1", "1 kΩ", "a", "0"), R_("R2", "2 kΩ", "b", "0"))
    r = solve_ac(c, "1 kHz")
    assert r.status == ACStatus.SOLVED
    va = r.voltage_of("a")
    vb = r.voltage_of("b")
    assert va - vb == RationalComplex(Fraction(0), Fraction(10))  # V(a)-V(b)=Vs
    bv = {x.ref: x.voltage for x in r.branch_voltages}["V1"]
    assert bv == RationalComplex(Fraction(0), Fraction(10))  # independent Vs path


def test_i_injection_sign():
    c = ckt("is", I_("I1", "1 A", "n", "0"), R_("R1", "1 kΩ", "n", "0"))
    r = solve_ac(c, "1 kHz")
    assert r.status == ACStatus.SOLVED
    # Is delivered into "n": node rises to Is*R = 1000 V (F8-B rule).
    assert r.voltage_of("n") == RationalComplex(Fraction(1000), Fraction(0))
    assert r.current_of("I1") == RationalComplex(Fraction(-1), Fraction(0))


def test_ground_side_stamping():
    c = ckt("g", V_("V1", "5 V", "a", "0"), R_("R1", "2 kΩ", "a", "0"),
            C_("C1", "1 uF", "a", "0"))
    r = solve_ac(c, "50 Hz")
    assert r.status == ACStatus.SOLVED
    assert r.voltage_of("a").re == Decimal(5)


def test_parallel_branches_stamp_additively():
    c = ckt("par", V_("V1", "12 V", "n", "0"), R_("R1", "1 kΩ", "n", "0"),
            R_("R2", "2 kΩ", "n", "0"), R_("R3", "3 kΩ", "n", "0"))
    r = solve_ac(c, "1 kHz")
    assert r.status == ACStatus.SOLVED
    assert r.voltage_of("n") == RationalComplex(Fraction(12), Fraction(0))
    tot = sum((x.current for x in r.branch_currents if x.ref != "V1"),
              RationalComplex(Fraction(0), Fraction(0)))
    assert tot == RationalComplex(Fraction(12, 1000) + Fraction(12, 2000)
                                  + Fraction(12, 3000), Fraction(0))


def test_mna_ordering_deterministic():
    c = ckt("ord", V_("V2", "3 V", "b", "0"), V_("V1", "10 V", "a", "0"),
            R_("R1", "1 kΩ", "a", "b"))
    op = ACOperatingPoint.from_frequency(Q("1 kHz"), "0")
    p = build_ac_problem(c, op)
    assert p.nodes == ("a", "b") and p.vsource_refs == ("V1", "V2")
    assert p.node_index == {"a": 0, "b": 1}
    assert p.vsource_index == {"V1": 2, "V2": 3}


def test_problem_kind_matches_content():
    c = ckt("k1", V_("V1", "1 V", "a", "0"), R_("R1", "1 kΩ", "a", "0"))
    op = ACOperatingPoint.from_frequency(Q("1 kHz"), "0")
    assert build_ac_problem(c, op).kind == "rational"
    c2 = ckt("k2", V_("V1", "1 V", "a", "0"), R_("R1", "1 kΩ", "a", "0"),
             C_("C1", "1 uF", "a", "0"))
    assert build_ac_problem(c2, op).kind == "decimal"


# -- 5. KCL ------------------------------------------------------------------------------------------------

def test_kcl_exact_zero_divider():
    c = ckt("kcl", V_("V1", "10 V", "in", "0"), R_("R1", "1 kΩ", "in", "out"),
            R_("R2", "1 kΩ", "out", "0"))
    r = solve_ac(c, "1 kHz")
    assert r.kcl_max_residual == Decimal(0)


def test_kcl_physical_recomputation_not_axb():
    # Independent per-net summation from branch currents (pin1->pin2 out
    # of a, into b): every net incl. ground must balance.
    c = ckt("kclp", V_("V1", "10 V", "in", "0", phase_=30),
            R_("R1", "1 kΩ", "in", "out"), C_("C1", "1 uF", "out", "0"),
            L_("L1", "10 mH", "out", "0"))
    r = solve_ac(c, "2 kHz")
    assert r.status == ACStatus.SOLVED
    bic = {x.ref: x.current for x in r.branch_currents}
    pins = {"V1": ("in", "0"), "R1": ("in", "out"), "C1": ("out", "0"), "L1": ("out", "0")}
    for net in ("in", "out", "0"):
        tot = DecimalComplex.zero()
        for ref, (a, b) in pins.items():
            if a == net:
                tot = tot + bic[ref]
            if b == net:
                tot = tot - bic[ref]
        assert tot.modulus() <= Decimal("1E-38"), net
    assert r.kcl_max_residual <= Decimal("1E-38")


def test_kcl_high_degree_star_8_and_16():
    for deg in (8, 16):
        comps = [V_("V1", "5 V", "ctr", "0")]
        for k in range(deg):
            comps.append(R_(f"R{k + 1}", "1 kΩ", "ctr", "0"))
        c = ckt(f"star{deg}", *comps)
        r = solve_ac(c, "1 kHz")
        assert r.status == ACStatus.SOLVED
        assert r.kcl_max_residual == Decimal(0)


def test_kcl_ground_always_covered():
    c = ckt("gnd", V_("V1", "9 V", "a", "0"), R_("R1", "1 kΩ", "a", "b"),
            R_("R2", "2 kΩ", "b", "0"), I_("I1", "1 mA", "b", "0"))
    r = solve_ac(c, "1 kHz")
    assert r.status == ACStatus.SOLVED
    assert r.kcl_max_residual == Decimal(0)
    assert r.voltage_of("0") == RationalComplex(Fraction(0), Fraction(0))


# -- 6. KVL ---------------------------------------------------------------------------------------------------

def test_kvl_cycle_counts_eddge_identity():
    div = ckt("c1", V_("V1", "1 V", "a", "0"), R_("R1", "1 kΩ", "a", "b"),
              R_("R2", "1 kΩ", "b", "0"))
    assert solve_ac(div, "1 kHz").kvl_cycles == 1  # E=3 V=3
    par = ckt("c2", V_("V1", "1 V", "n", "0"), R_("R1", "1 kΩ", "n", "0"),
              R_("R2", "2 kΩ", "n", "0"), R_("R3", "3 kΩ", "n", "0"))
    assert solve_ac(par, "1 kHz").kvl_cycles == 3  # E=4 V=2
    br = ckt("c3", V_("V1", "10 V", "t", "0"), R_("R1", "1 kΩ", "t", "a"),
             R_("R2", "1 kΩ", "t", "b"), R_("R3", "1 kΩ", "a", "0"),
             R_("R4", "1 kΩ", "b", "0"), R_("R5", "1 kΩ", "a", "b"))
    assert solve_ac(br, "1 kHz").kvl_cycles == 3  # E=6 V=4


def test_kvl_exact_zero_on_loops():
    c = ckt("kvl", V_("V1", "10 V", "in", "0"), R_("R1", "1 kΩ", "in", "out"),
            R_("R2", "1 kΩ", "out", "0"))
    r = solve_ac(c, "1 kHz")
    assert r.kvl_max_residual == Decimal(0)


def test_kvl_hp_small_on_rlc_loop():
    c = ckt("kvll", V_("V1", "5 V", "in", "0"), R_("R1", "100 ohm", "in", "a"),
            L_("L1", "10 mH", "a", "b"), C_("C1", "1 uF", "b", "0"))
    r = solve_ac(c, "1 kHz")
    assert r.status == ACStatus.SOLVED
    assert r.kvl_max_residual <= Decimal("1E-38")
    assert r.kcl_max_residual <= Decimal("1E-38")


def test_kvl_uses_independent_vs():
    c = ckt("vs2", V_("V1", "10 V", "a", "0"), V_("V2", "4 V", "0", "b"),
            R_("R1", "1 kΩ", "a", "b"))
    r = solve_ac(c, "1 kHz")
    assert r.status == ACStatus.SOLVED
    # Loop a->b through R1 then b->a through sources: (Va-Vb) + (Vb-Va) = 0
    # with V2 contributing its independent -4 V phasor on the return path.
    assert r.kvl_max_residual == Decimal(0)
    assert r.voltage_of("a") - r.voltage_of("b") == RationalComplex(Fraction(14), Fraction(0))


# -- 7. ground / solvability ----------------------------------------------------------------------------------------

def test_missing_ground_invalid():
    c = ckt("ng", V_("V1", "1 V", "a", "b"), R_("R1", "1 kΩ", "a", "b"))
    st = solve_ac(c, "1 kHz")
    assert st.status == ACStatus.INVALID
    assert any("reference" in d for d in st.diagnostics)


def test_ambiguous_ground_invalid():
    c = ckt("ag", V_("V1", "1 V", "a", "0"), R_("R1", "1 kΩ", "a", "GND"))
    assert solve_ac(c, "1 kHz").status == ACStatus.INVALID


def test_floating_net_invalid():
    c = ckt("fl", V_("V1", "1 V", "a", "0"), R_("R1", "1 kΩ", "a", "0"),
            R_("R2", "1 kΩ", "x", "y"))
    st = solve_ac(c, "1 kHz")
    assert st.status == ACStatus.INVALID
    assert any("no path" in d for d in st.diagnostics)


def test_parallel_equal_sources_singular_kept():
    c = ckt("ps", V_("V1", "10 V", "n", "0"), V_("V2", "10 V", "n", "0"),
            R_("R1", "1 kΩ", "n", "0"))
    r = solve_ac(c, "1 kHz")
    assert r.status == ACStatus.SINGULAR
    assert any("rank-deficient" in d for d in r.diagnostics)


def test_contradictory_sources_inconsistent_kept():
    c = ckt("cs", V_("V1", "10 V", "n", "0"), V_("V2", "5 V", "n", "0"),
            R_("R1", "1 kΩ", "n", "0"))
    r = solve_ac(c, "1 kHz")
    assert r.status == ACStatus.INCONSISTENT
    assert any("contradictory" in d for d in r.diagnostics)


def test_near_duplicate_sources_inconsistent_at_input_precision():
    # Representability boundary (provenance: F6 to_base() rounds inputs to
    # the ambient 28 digits, so sub-1E-28 phasor differences cannot enter
    # D3 at all). A 1E-20 difference survives and must read as a genuine
    # contradiction, not as uncertainty (D2 floor is 1E-40 of scale).
    from academic_core.domain.engineering.math.trig import make_context as _mc

    ctx = _mc()
    v2mag = ctx.add(Decimal(10), Decimal("1E-20"))
    c = Circuit("nd")
    c.add(V_("V1", "10 V", "n", "0"))
    c.add(Component("V2", "V", Q(f"{v2mag} V"), {"+": "n", "-": "0"}))
    c.add(R_("R1", "1 kΩ", "n", "0"))
    r = solve_ac(c, "1 kHz")
    assert r.status == ACStatus.INCONSISTENT


def test_d2_uncertain_mapping_preserved():
    # D3-level NUMERICALLY_UNCERTAIN is unreachable for F6-input circuits:
    # triggering it needs >28-digit conspiracies, but F6 to_base() caps
    # input precision at the ambient 28 digits (see test above). The
    # status therefore exists as a preserved mapping (D2 verdicts are
    # never overridden), unit-tested here; D2's own suite triggers it.
    from academic_core.domain.engineering.ac.solver import _D2_TO_AC
    from academic_core.domain.engineering.math.linsolve import SolveStatus as _SS

    assert _D2_TO_AC[_SS.NUMERICALLY_UNCERTAIN] == ACStatus.NUMERICALLY_UNCERTAIN
    assert _D2_TO_AC[_SS.SOLVED] == ACStatus.SOLVED
    assert _D2_TO_AC[_SS.SINGULAR] == ACStatus.SINGULAR
    assert _D2_TO_AC[_SS.INCONSISTENT] == ACStatus.INCONSISTENT


def test_zero_frequency_invalid_explicit():
    c = ckt("z0", V_("V1", "1 V", "a", "0"), R_("R1", "1 kΩ", "a", "0"))
    st = solve_ac(c, "0 Hz")
    assert st.status == ACStatus.INVALID
    assert any("f = 0" in d for d in st.diagnostics)


def test_negative_frequency_invalid_explicit():
    c = ckt("zn", V_("V1", "1 V", "a", "0"), R_("R1", "1 kΩ", "a", "0"))
    st = solve_ac(c, "-60 Hz")
    assert st.status == ACStatus.INVALID
    assert any("product boundary" in d for d in st.diagnostics)


# -- 8. resonance / degenerate --------------------------------------------------------------------------------------

def test_series_rlc_resonance_solves():
    # f0 = 1/(2*pi*sqrt(LC)), L=10mH C=10uF -> ~503.29 Hz; current ~ Vs/R.
    c = ckt("res", V_("V1", "10 V", "in", "0"), R_("R1", "10 ohm", "in", "a"),
            L_("L1", "10 mH", "a", "b"), C_("C1", "10 uF", "b", "0"))
    r = solve_ac(c, "503.29212104487018 Hz")
    assert r.status == ACStatus.SOLVED
    i = r.current_of("R1")
    assert abs(CTX.divide(i.im, i.re)) <= Decimal("1E-6")
    assert abs(CTX.subtract(magnitude(i), Decimal(1))) <= Decimal("1E-6")


def test_series_lc_without_r_near_resonance():
    # Exact resonance (f0 = 1/(2*pi*sqrt(LC))) is UNREPRESENTABLE: f0 is
    # irrational for rational L/C, and F6 inputs cap at 28 digits, so no
    # finite-decimal f can place Z_LC exactly at zero. The global MNA
    # verdict for the reachable near-resonance is SOLVED with a huge
    # (near-short) current — classified by the matrix, never hardcoded.
    c = ckt("lc0", V_("V1", "10 V", "in", "0"), L_("L1", "10 mH", "in", "a"),
            C_("C1", "10 uF", "a", "0"))
    r = solve_ac(c, "503.29212104487018 Hz")
    assert r.status == ACStatus.SOLVED
    assert magnitude(r.current_of("L1")) > Decimal("1E6")
    assert r.kcl_max_residual <= Decimal("1E-30")
    assert r.kvl_max_residual <= Decimal("1E-30")


def test_parallel_lc_at_resonance_is_open_solved():
    c = ckt("plc", I_("I1", "1 A", "n", "0"), L_("L1", "10 mH", "n", "0"),
            C_("C1", "10 uF", "n", "0"), R_("R1", "1 kΩ", "n", "0"))
    r = solve_ac(c, "503.29212104487018 Hz")
    assert r.status == ACStatus.SOLVED
    # Tank open: nearly all 1 A flows through R1 -> V ~ 1000 V.
    assert abs(CTX.subtract(magnitude(r.voltage_of("n")), Decimal(1000))) <= Decimal("1")


def test_floating_resonator_invalid():
    c = ckt("fr", V_("V1", "1 V", "a", "0"), R_("R1", "1 kΩ", "a", "0"),
            L_("L1", "1 mH", "x", "y"), C_("C1", "1 uF", "y", "x"))
    assert solve_ac(c, "1 kHz").status == ACStatus.INVALID


def test_ideal_source_across_near_resonant_tank():
    # Parallel LC tank directly across the source at f0: the tank is
    # nearly open (Y = j*(wC - 1/(wL)) ~ 0, exactly zero being
    # unrepresentable — see test above), so the source holds Vs.
    c = ckt("zs", V_("V1", "5 V", "n", "0"), L_("L1", "10 mH", "n", "0"),
            C_("C1", "10 uF", "n", "0"))
    r = solve_ac(c, "503.29212104487018 Hz")
    assert r.status == ACStatus.SOLVED
    assert close_dc(r.voltage_of("n"), Decimal(5), Decimal(0), Decimal("1E-20"))


# -- 9. peak / RMS -----------------------------------------------------------------------------------------------------

def test_peak_not_rms():
    c = ckt("pk", V_("V1", "10 V", "n", "0"), R_("R1", "1 kΩ", "n", "0"))
    r = solve_ac(c, "1 kHz")
    assert magnitude(r.voltage_of("n")) == Decimal(10)  # peak, not 10/sqrt(2)
    assert r.operating_point is not None
    assert r.operating_point.amplitude_convention == "peak"


def test_rms_conversion_factor():
    # 10/sqrt(2) = 7.0710678118654752... (16 certain digits, tol 1E-15).
    assert abs(CTX.subtract(rms_from_peak(Decimal(10)),
                            Decimal("7.0710678118654752"))) <= Decimal("1E-15")
    # Solver state never holds RMS: branch/node values are peak phasors.
    c = ckt("pk2", V_("V1", "10 V", "n", "0"), R_("R1", "1 kΩ", "n", "0"))
    r = solve_ac(c, "1 kHz")
    assert r.current_of("R1") == RationalComplex(Fraction(1, 100), Fraction(0))


# -- 10. independent analytical references -------------------------------------------------------------------------------

def test_ref_r_only_ohms_law():
    c = ckt("r", V_("V1", "12 V", "n", "0"), R_("R1", "4 kΩ", "n", "0"))
    r = solve_ac(c, "60 Hz")
    i = r.current_of("R1")
    assert i == RationalComplex(Fraction(12, 4000), Fraction(0))  # V/R, hand


def _w(f_hz, L=None, C=None):
    # Angular-frequency building blocks from the transcribed PI50 literal,
    # evaluated here by direct formulas (independent path from the engine,
    # which uses the Machin-series pi and MNA+elimination). PI50's own
    # correctness is established in GATE-F8D1 and checkable anywhere.
    two_pi_f = CTX.multiply(CTX.multiply(Decimal(2), PI50), Decimal(str(f_hz)))
    if L is not None:
        return CTX.multiply(two_pi_f, Decimal(str(L)))
    if C is not None:
        return CTX.divide(Decimal(1), CTX.multiply(two_pi_f, Decimal(str(C))))
    raise AssertionError("need L or C")


def test_ref_rl_series_transcribed():
    # f=1000, R=100, L=10mH: Z = R + j*wL.
    z = (Decimal(100), _w(1000, L="0.01"))
    e = cdiv((Decimal(10), Decimal(0)), z)
    c = ckt("rl", V_("V1", "10 V", "in", "0"), R_("R1", "100 ohm", "in", "a"),
            L_("L1", "10 mH", "a", "0"))
    r = solve_ac(c, "1000 Hz")
    assert r.status == ACStatus.SOLVED
    i = r.current_of("R1")
    assert close_dc(i, e[0], e[1], Decimal("1E-40"))


def test_ref_rc_series_transcribed():
    # f=1000, R=1000, C=1uF: Z = R - j/(wC).
    z = (Decimal(1000), CTX.minus(_w(1000, C="0.000001")))
    e = cdiv((Decimal(10), Decimal(0)), z)
    c = ckt("rc", V_("V1", "10 V", "in", "0"), R_("R1", "1 kΩ", "in", "a"),
            C_("C1", "1 uF", "a", "0"))
    r = solve_ac(c, "1000 Hz")
    i = r.current_of("R1")
    assert close_dc(i, e[0], e[1], Decimal("1E-40"))


def test_ref_rlc_series_transcribed():
    # f=1000: Z = R + j*(wL - 1/(wC)).
    x = CTX.subtract(_w(1000, L="0.01"), _w(1000, C="0.000001"))
    z = (Decimal(100), x)
    e = cdiv((Decimal(10), Decimal(0)), z)
    c = ckt("rlc", V_("V1", "10 V", "in", "0"), R_("R1", "100 ohm", "in", "a"),
            L_("L1", "10 mH", "a", "b"), C_("C1", "1 uF", "b", "0"))
    r = solve_ac(c, "1000 Hz")
    assert close_dc(r.current_of("R1"), e[0], e[1], Decimal("1E-40"))


def test_ref_rlc_parallel_transcribed():
    # Is=1A: Y = G + j*(wC - 1/(wL)), wC and 1/(wL) from PI50 here.
    two_pi_f = CTX.multiply(CTX.multiply(Decimal(2), PI50), Decimal(1000))
    wc = CTX.multiply(two_pi_f, Decimal("0.000001"))
    yl = CTX.divide(Decimal(1), CTX.multiply(two_pi_f, Decimal("0.01")))
    y = (Decimal("0.001"), CTX.subtract(wc, yl))
    e = cdiv((Decimal(1), Decimal(0)), y)
    c = ckt("pll", I_("I1", "1 A", "n", "0"), R_("R1", "1 kΩ", "n", "0"),
            L_("L1", "10 mH", "n", "0"), C_("C1", "1 uF", "n", "0"))
    r = solve_ac(c, "1000 Hz")
    assert close_dc(r.voltage_of("n"), e[0], e[1], Decimal("1E-38"))


def test_ref_rc_divider_hand_formula():
    # Vout = Vs/(1 + j*w*R*C); wRC from PI50 here (R=2k, C=500nF, f=1000).
    wrc = CTX.multiply(CTX.multiply(CTX.multiply(Decimal(2), PI50), Decimal(1000)),
                       CTX.multiply(Decimal(2000), Decimal("0.0000005")))
    e = cdiv((Decimal(5), Decimal(0)), (Decimal(1), wrc))
    c = ckt("rcd", V_("V1", "5 V", "in", "0"), R_("R1", "2 kΩ", "in", "out"),
            C_("C1", "500 nF", "out", "0"))
    r = solve_ac(c, "1000 Hz")
    assert close_dc(r.voltage_of("out"), e[0], e[1], Decimal("1E-40"))


def test_ref_bridge_balanced_and_offbalance():
    bal = ckt("br0", V_("V1", "10 V", "t", "0"), R_("R1", "1 kΩ", "t", "a"),
              R_("R2", "1 kΩ", "t", "b"), R_("R3", "1 kΩ", "a", "0"),
              R_("R4", "1 kΩ", "b", "0"), R_("R5", "1 kΩ", "a", "b"))
    rb = solve_ac(bal, "1 kHz")
    assert rb.status == ACStatus.SOLVED
    assert rb.voltage_of("a") - rb.voltage_of("b") == RationalComplex(Fraction(0), Fraction(0))
    off = ckt("br1", V_("V1", "10 V", "t", "0"), R_("R1", "1 kΩ", "t", "a"),
              R_("R2", "1 kΩ", "t", "b"), R_("R3", "1 kΩ", "a", "0"),
              R_("R4", "2 kΩ", "b", "0"), R_("R5", "1 kΩ", "a", "b"))
    ro = solve_ac(off, "1 kHz")
    assert ro.status == ACStatus.SOLVED
    # Independent 2-node hand solve (Cramer on Fractions, no elimination):
    # a: 3Va - Vb = 10 ; b: -2Va + 5Vb = 20 (mA/kΩ units) -> det 13,
    # Va = 70/13, Vb = 80/13.
    det = Fraction(3 * 5 - (-1) * (-2))
    va = (Fraction(10) * 5 - Fraction(-1) * 20) / det
    vb = (Fraction(3) * 20 - Fraction(10) * Fraction(-2)) / det
    assert ro.voltage_of("a") == RationalComplex(va, Fraction(0))
    assert ro.voltage_of("b") == RationalComplex(vb, Fraction(0))


def test_ref_ladder_reduction_independent():
    # 2-rung ladder by series/parallel reduction (algebra, not elimination):
    # in -R1- m -R2- out, shunts R3 (m-0), R4 (out-0); Vs=12.
    # Zeq_out = R2+R4; Zm = (R3 || Zeq_out); Itot = Vs/(R1+Zm); Vm = Vs - Itot R1...
    r1, r2, r3, r4, vs = (Fraction(1000), Fraction(2000), Fraction(3000),
                          Fraction(4000), Fraction(12))
    z_out = r2 + r4
    zm = r3 * z_out / (r3 + z_out)
    itot = vs / (r1 + zm)
    vm = vs - itot * r1
    vo = vm * r4 / (r2 + r4)
    c = ckt("lad", V_("V1", "12 V", "in", "0"), R_("R1", "1 kΩ", "in", "m"),
            R_("R2", "2 kΩ", "m", "out"), R_("R3", "3 kΩ", "m", "0"),
            R_("R4", "4 kΩ", "out", "0"))
    r = solve_ac(c, "1 kHz")
    assert r.voltage_of("m") == RationalComplex(vm, Fraction(0))
    assert r.voltage_of("out") == RationalComplex(vo, Fraction(0))


def test_ref_multinode_exact_hand_fractions():
    c = ckt("mn", V_("V1", "9 V", "a", "0"), R_("R1", "1 kΩ", "a", "b"),
            R_("R2", "2 kΩ", "b", "0"), R_("R3", "3 kΩ", "b", "c2"),
            R_("R4", "4 kΩ", "c2", "0"))
    r = solve_ac(c, "1 kHz")
    # b sees divider a->b->(R2 || (R3+R4)): hand fractions.
    rlow = Fraction(2000) * Fraction(7000) / (Fraction(2000) + Fraction(7000))
    vb = Fraction(9) * rlow / (Fraction(1000) + rlow)
    vc = vb * Fraction(4000) / Fraction(7000)
    assert r.voltage_of("b") == RationalComplex(vb, Fraction(0))
    assert r.voltage_of("c2") == RationalComplex(vc, Fraction(0))


# -- 11. D2 cross-validation -------------------------------------------------------------------------------------

def test_d2_crosscheck_hand_stamped_mna():
    # Hand-stamped divider MNA (R1 in-out, R2 out-0, V1 in-0), solved by
    # F8-D2 directly; node voltages must match the AC engine.
    from academic_core.domain.engineering.math.linsolve import (
        ComplexLinearProblem, solve)
    from academic_core.domain.engineering.math import RationalComplex as RC

    F = Fraction
    g1, g2 = F(1, 1000), F(1, 2000)
    A = [[RC(g1, F(0)), RC(-g1, F(0)), RC(1, F(0))],
         [RC(-g1, F(0)), RC(g1 + g2, F(0)), RC(0, F(0))],
         [RC(1, F(0)), RC(0, F(0)), RC(0, F(0))]]
    b = [RC(0, F(0)), RC(0, F(0)), RC(10, F(0))]
    lin = solve(ComplexLinearProblem.from_sequences(A, b))
    assert lin.status.value == "solved"
    c = ckt("x", V_("V1", "10 V", "in", "0"), R_("R1", "1 kΩ", "in", "out"),
            R_("R2", "2 kΩ", "out", "0"))
    r = solve_ac(c, "1 kHz")
    assert r.voltage_of("in") == lin.solution[0]
    assert r.voltage_of("out") == lin.solution[1]
    assert lin.solution[1] == RC(F(20, 3), F(0))  # 10*2k/3k hand value


def test_d2_status_inherited_not_overridden():
    c = ckt("inh", V_("V1", "10 V", "n", "0"), V_("V2", "5 V", "n", "0"))
    r = solve_ac(c, "1 kHz")
    assert r.status == ACStatus.INCONSISTENT
    assert r.solver_result is not None
    assert r.solver_result.status.value == "inconsistent"
    assert r.node_voltages == () and r.residual is None


def test_hp_solution_carries_solver_result():
    c = ckt("hp", V_("V1", "1 V", "a", "0"), R_("R1", "1 kΩ", "a", "0"),
            C_("C1", "1 uF", "a", "0"))
    r = solve_ac(c, "1 kHz")
    assert r.solver_result is not None
    assert r.numeric_mode == NumericMode.HIGH_PRECISION
    assert r.working_precision == 50
    assert r.residual is not None


# -- 12. ngspice oracle -------------------------------------------------------------------------------------

def _ng_backend():
    from academic_core.infrastructure.ngspice import NgSpiceBackend

    b = NgSpiceBackend()
    return b if b.detect().verified else None


NG = _ng_backend()


def _spice_value(q):
    return format(q.to_base(), "f")


def _spice_netlist(circuit, freq_hz):
    from academic_core.domain.engineering.units import parse_quantity as _pq

    lines = [f"* D3 oracle {circuit.name}"]
    for e in sorted(circuit.components, key=lambda x: x.ref.upper()):
        t = e.type.upper()
        pins = " ".join(e.pins[p] for p in
                        (("1", "2") if t in ("R", "L", "C") else ("+", "-")))
        if t == "V":
            ph = e.parameters.get("phase", 0)
            unit = str(e.parameters.get("phase_unit", "deg")).lower()
            ph_d = Decimal(str(ph))
            deg = ph_d if unit == "deg" else ph_d * Decimal("57.295779513082320876798154814105")
            lines.append(f"{e.ref.upper()} {pins} dc 0 ac {_spice_value(e.value)} {deg}")
        elif t in ("R", "L", "C"):
            lines.append(f"{e.ref.upper()} {pins} {_spice_value(e.value)}")
        else:
            raise AssertionError("oracle netlists use V+R/L/C only")
    lines.append(".end")
    return "\n".join(lines) + "\n"


def _oracle(circuit, freq_hz):
    from academic_core.domain.engineering.simulation import ACAnalysis

    assert NG is not None
    ac = ACAnalysis(sweep_type="lin", points=2, fstart=str(freq_hz),
                    fstop=str(int(freq_hz) + 1))
    res = NG.simulate(_spice_netlist(circuit, freq_hz), analyses=(ac,))
    assert res.status == "COMPLETED"
    return res


def _check_node(r, res, node, freq_hz, mag_tol=0.002, ph_tol=0.5):
    import math as _math

    v = r.voltage_of(node)
    assert v is not None
    c = res.sample_complex_at(f"v({node})", str(freq_hz))
    assert c is not None
    mag = float(magnitude(v))
    ang = float(phasedeg(v))
    mag_o = abs(c)
    ang_o = _math.degrees(_math.atan2(c.imag, c.real))
    assert abs(mag - mag_o) <= mag_tol * max(1.0, mag_o), (node, mag, mag_o)
    if mag_o > 1e-9:
        assert abs(ang - ang_o) <= ph_tol, (node, ang, ang_o)
    assert abs(float(v.re) - c.real) <= mag_tol * max(1.0, mag_o)
    assert abs(float(v.im) - c.imag) <= mag_tol * max(1.0, mag_o)


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_rc_lowpass():
    c = ckt("orc", V_("V1", "1 V", "in", "0"), R_("R1", "1 kΩ", "in", "out"),
            C_("C1", "1 uF", "out", "0"))
    r = solve_ac(c, "1000 Hz")
    assert r.status == ACStatus.SOLVED
    _check_node(r, _oracle(c, 1000), "out", 1000)
    _check_node(r, _oracle(c, 1000), "in", 1000)


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_rl():
    c = ckt("orl", V_("V1", "10 V", "in", "0"), R_("R1", "100 ohm", "in", "a"),
            L_("L1", "10 mH", "a", "0"))
    r = solve_ac(c, "1000 Hz")
    _check_node(r, _oracle(c, 1000), "a", 1000)


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_rlc_series():
    c = ckt("orlc", V_("V1", "10 V", "in", "0"), R_("R1", "100 ohm", "in", "a"),
            L_("L1", "10 mH", "a", "b"), C_("C1", "1 uF", "b", "0"))
    r = solve_ac(c, "1000 Hz")
    res = _oracle(c, 1000)
    _check_node(r, res, "a", 1000)
    _check_node(r, res, "b", 1000)


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_bridge():
    c = ckt("obr", V_("V1", "10 V", "t", "0"), R_("R1", "1 kΩ", "t", "a"),
            R_("R2", "2 kΩ", "t", "b"), R_("R3", "1 kΩ", "a", "0"),
            R_("R4", "2 kΩ", "b", "0"), R_("R5", "1 kΩ", "a", "b"))
    r = solve_ac(c, "500 Hz")
    res = _oracle(c, 500)
    _check_node(r, res, "a", 500)
    _check_node(r, res, "b", 500)


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_parallel_rlc():
    c = ckt("opl", V_("V1", "5 V", "n", "0"), R_("R1", "1 kΩ", "n", "0"),
            L_("L1", "10 mH", "n", "0"), C_("C1", "1 uF", "n", "0"))
    r = solve_ac(c, "1000 Hz")
    res = _oracle(c, 1000)
    _check_node(r, res, "n", 1000)
    iv = res.sample_complex_at("i(v1)", "1000")
    i_d3 = r.current_of("V1")
    assert abs(float(i_d3.re) - iv.real) <= 0.002 * max(1.0, abs(iv.real))
    assert abs(float(i_d3.im) - iv.imag) <= 0.002 * max(1.0, abs(iv.imag))


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_multinode_ladder():
    c = ckt("oml", V_("V1", "12 V", "in", "0"), R_("R1", "1 kΩ", "in", "m"),
            R_("R2", "2 kΩ", "m", "out"), R_("R3", "3 kΩ", "m", "0"),
            C_("C1", "1 uF", "out", "0"))
    r = solve_ac(c, "1000 Hz")
    res = _oracle(c, 1000)
    _check_node(r, res, "m", 1000)
    _check_node(r, res, "out", 1000)


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_phase_source_45deg():
    c = ckt("op45", V_("V1", "5 V", "in", "0", phase_=45),
            R_("R1", "1 kΩ", "in", "out"), C_("C1", "1 uF", "out", "0"))
    r = solve_ac(c, "1000 Hz")
    res = _oracle(c, 1000)
    v = r.voltage_of("out")
    o = res.sample_complex_at("v(out)", "1000")
    assert o is not None
    # Phase and both cartesian signs must match, not just magnitude.
    assert v.re > 0 and v.im < 0, (v.re, v.im)
    assert o.real > 0 and o.imag < 0
    assert abs(float(v.re) - o.real) <= 0.002
    assert abs(float(v.im) - o.imag) <= 0.002


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_parallel_branches():
    c = ckt("opb", V_("V1", "10 V", "n", "0"), R_("R1", "1 kΩ", "n", "0"),
            R_("R2", "2 kΩ", "n", "0"), C_("C1", "1 uF", "n", "0"))
    r = solve_ac(c, "2000 Hz")
    res = _oracle(c, 2000)
    _check_node(r, res, "n", 2000)
    iv = res.sample_complex_at("i(v1)", "2000")
    i_d3 = r.current_of("V1")
    assert abs(float(i_d3.re) - iv.real) <= 0.003
    assert abs(float(i_d3.im) - iv.imag) <= 0.003


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_general_mesh():
    c = ckt("omsh", V_("V1", "10 V", "a", "0"), R_("R1", "1 kΩ", "a", "b"),
            R_("R2", "2 kΩ", "b", "0"), R_("R3", "1 kΩ", "a", "c"),
            C_("C1", "500 nF", "c", "0"), L_("L1", "5 mH", "b", "c"),
            R_("R4", "3 kΩ", "b", "c"))
    r = solve_ac(c, "1500 Hz")
    assert r.status == ACStatus.SOLVED
    res = _oracle(c, 1500)
    for node in ("a", "b", "c"):
        _check_node(r, res, node, 1500)
    assert r.kcl_max_residual <= Decimal("1E-38")
    assert r.kvl_max_residual <= Decimal("1E-38")


# -- 13. metamorphic -------------------------------------------------------------------------------------

def test_metamorphic_source_scaling():
    c = ckt("ms", V_("V1", "10 V", "in", "0"), R_("R1", "1 kΩ", "in", "out"),
            C_("C1", "1 uF", "out", "0"))
    r1 = solve_ac(c, "1 kHz")
    c2 = ckt("ms2", V_("V1", "30 V", "in", "0"), R_("R1", "1 kΩ", "in", "out"),
             C_("C1", "1 uF", "out", "0"))
    r2 = solve_ac(c2, "1 kHz")
    assert r1.status == r2.status == ACStatus.SOLVED
    for a, b in zip(r1.node_voltages, r2.node_voltages):
        assert a.node == b.node
        assert (b.phasor - a.phasor * 3).modulus() <= Decimal("1E-40")


def test_metamorphic_source_scaling_exact():
    c = ckt("mse", V_("V1", "10 V", "in", "0"), R_("R1", "1 kΩ", "in", "out"),
            R_("R2", "2 kΩ", "out", "0"))
    r1 = solve_ac(c, "1 kHz")
    c2 = ckt("mse2", V_("V1", "-5 V", "in", "0"), R_("R1", "1 kΩ", "in", "out"),
             R_("R2", "2 kΩ", "out", "0"))
    r2 = solve_ac(c2, "1 kHz")
    for a, b in zip(r1.node_voltages, r2.node_voltages):
        assert b.phasor * 2 == a.phasor * -1  # k = -1/2 exactly


def test_metamorphic_resistance_scaling_physical():
    c = ckt("mr", V_("V1", "12 V", "in", "0"), R_("R1", "1 kΩ", "in", "out"),
            R_("R2", "2 kΩ", "out", "0"))
    r1 = solve_ac(c, "1 kHz")
    c2 = ckt("mr2", V_("V1", "12 V", "in", "0"), R_("R1", "1 kΩ", "in", "out"),
             R_("R2", "4 kΩ", "out", "0"))
    r2 = solve_ac(c2, "1 kHz")
    assert r1.voltage_of("out") == RationalComplex(Fraction(8), Fraction(0))
    assert r2.voltage_of("out") == RationalComplex(Fraction(48, 5), Fraction(0))


def test_metamorphic_component_permutation_identical():
    # Same name: the digest covers circuit identity, so only insertion
    # order may vary here.
    c1 = ckt("mp", V_("V1", "10 V", "in", "0"), R_("R1", "1 kΩ", "in", "out"),
             C_("C1", "1 uF", "out", "0"))
    c2 = ckt("mp", C_("C1", "1 uF", "out", "0"), R_("R1", "1 kΩ", "in", "out"),
             V_("V1", "10 V", "in", "0"))
    r1, r2 = solve_ac(c1, "1 kHz"), solve_ac(c2, "1 kHz")
    assert r1.digest == r2.digest
    assert r1.voltage_of("out") == r2.voltage_of("out")


def test_metamorphic_node_rename_equivalent():
    c1 = ckt("mn1", V_("V1", "10 V", "in", "0"), R_("R1", "1 kΩ", "in", "out"),
             R_("R2", "2 kΩ", "out", "0"))
    c2 = ckt("mn2", V_("V1", "10 V", "src", "0"), R_("R1", "1 kΩ", "src", "dst"),
             R_("R2", "2 kΩ", "dst", "0"))
    r1, r2 = solve_ac(c1, "1 kHz"), solve_ac(c2, "1 kHz")
    assert r1.voltage_of("out") == r2.voltage_of("dst")
    assert r1.voltage_of("in") == r2.voltage_of("src")


def test_metamorphic_conjugation_exact():
    # Separate nodes per source (parallel ideal sources would be a
    # topology verdict, not a phasor test).
    c1 = ckt("mc1", V_("V1", "10 V", "a", "0", phase_=90),
             V_("V2", "5 V", "b", "0", phase_=0),
             R_("R1", "1 kΩ", "a", "b"))
    c2 = ckt("mc2", V_("V1", "10 V", "a", "0", phase_=-90),
             V_("V2", "5 V", "b", "0", phase_=0),
             R_("R1", "1 kΩ", "a", "b"))
    r1, r2 = solve_ac(c1, "1 kHz"), solve_ac(c2, "1 kHz")
    assert r1.status == r2.status == ACStatus.SOLVED
    assert r2.voltage_of("a") == r1.voltage_of("a").conjugate()
    assert r2.voltage_of("b") == r1.voltage_of("b").conjugate()


def test_metamorphic_unit_representation_invariant():
    c1 = ckt("mu1", V_("V1", "10 V", "in", "0"), R_("R1", "1 kΩ", "in", "out"),
             R_("R2", "2000 ohm", "out", "0"))
    c2 = ckt("mu2", V_("V1", "10000 mV", "in", "0"), R_("R1", "1000 ohm", "in", "out"),
             R_("R2", "2 kΩ", "out", "0"))
    r1, r2 = solve_ac(c1, "1 kHz"), solve_ac(c2, "1 kHz")
    assert r1.voltage_of("out") == r2.voltage_of("out")
    # The digest is representation-sensitive by design ("1 kΩ" vs
    # "1000 ohm" spell the same physics differently); values are equal.
    assert r1.digest != r2.digest


# -- 14. immutability / determinism -------------------------------------------------------------------------------

def test_immutability_circuit_untouched_and_repeatable():
    c = ckt("im", V_("V1", "10 V", "in", "0", phase_=30),
            R_("R1", "1 kΩ", "in", "out"), C_("C1", "1 uF", "out", "0"),
            L_("L1", "5 mH", "out", "0"))
    before = c.to_netlist()
    params_before = {e.ref: dict(e.parameters) for e in c.components}
    r1 = solve_ac(c, "2 kHz")
    assert c.to_netlist() == before
    assert {e.ref: dict(e.parameters) for e in c.components} == params_before
    r2 = solve_ac(c, "2 kHz")
    assert r1.digest == r2.digest
    assert r1.voltage_of("out") == r2.voltage_of("out")


def test_determinism_100_runs():
    c = ckt("det", V_("V1", "7 V", "in", "0", phase_=45),
            R_("R1", "1 kΩ", "in", "out"), C_("C1", "220 nF", "out", "0"))
    first = solve_ac(c, "3 kHz")
    first_dict = json.dumps(first.to_dict(), sort_keys=True)
    for _ in range(100):
        rep = solve_ac(c, "3 kHz")
        assert rep.status == first.status
        assert rep.voltage_of("out") == first.voltage_of("out")
        assert rep.kcl_max_residual == first.kcl_max_residual
        assert rep.kvl_max_residual == first.kvl_max_residual
        assert rep.digest == first.digest
        assert json.dumps(rep.to_dict(), sort_keys=True) == first_dict


# -- 15. security ------------------------------------------------------------------------------------------------------

AC_DIR = pathlib.Path(__file__).resolve().parents[1] / "src" / "academic_core" / "domain" / "engineering" / "ac"

FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__", "open", "input", "breakpoint"}
FORBIDDEN_IMPORT_ROOTS = {
    "os", "sys", "pathlib", "sqlite3", "urllib", "socket", "http",
    "ftplib", "subprocess", "pickle", "marshal", "ctypes",
    "PySide6", "numpy", "scipy", "math", "cmath",
}
FORBIDDEN_QUALIFIED = {
    "academic_core.infrastructure",
    "academic_core.application",
    "academic_core.app",
}


def _sources():
    return sorted(AC_DIR.glob("*.py"))


def test_security_package_files_present():
    names = {p.name for p in _sources()}
    assert {"__init__.py", "errors.py", "operating_point.py", "problem.py",
            "phasors.py", "solution.py", "solver.py", "topology.py"} <= names


def test_security_no_dangerous_calls():
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in FORBIDDEN_CALLS, (path.name, node.func.id)


def test_security_no_forbidden_dependencies():
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    assert a.name.split(".")[0] not in FORBIDDEN_IMPORT_ROOTS, (
                        path.name, a.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in FORBIDDEN_IMPORT_ROOTS, (
                    path.name, node.module)
                for qual in FORBIDDEN_QUALIFIED:
                    assert node.module != qual and not node.module.startswith(qual + "."), (
                        path.name, node.module)


def test_security_no_float_complex_names_in_core():
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        assert "float" not in names, path.name
        assert "complex" not in names, path.name


def test_security_no_ngspice_in_core():
    for path in _sources():
        text = path.read_text(encoding="utf-8").lower()
        assert "ngspice" not in text, path.name
        assert "subprocess" not in text, path.name


# -- 16. provenance -------------------------------------------------------------------------------------------------------

def test_provenance_keys_no_timestamp_deterministic():
    c = ckt("pr", V_("V1", "10 V", "in", "0"), R_("R1", "1 kΩ", "in", "out"),
            C_("C1", "1 uF", "out", "0"))
    r = solve_ac(c, "1 kHz")
    for key in ("engine", "version", "numeric_mode", "working_precision",
                "frequency", "angular_frequency_rad_per_s",
                "phase_convention", "amplitude_convention", "reference_node",
                "component_refs", "topology_digest", "solver_digest", "status"):
        assert key in r.provenance, key
    assert r.provenance["engine"] == "f8d-ac-mna"
    assert r.provenance["version"] == "1.0"
    blob = json.dumps(r.to_dict(), sort_keys=True).lower()
    assert "timestamp" not in blob
    assert len(r.digest) == 64


def test_provenance_digest_sensitive_and_stable():
    c1 = ckt("pd", V_("V1", "10 V", "in", "0"), R_("R1", "1 kΩ", "in", "out"),
             R_("R2", "2 kΩ", "out", "0"))
    c2 = ckt("pd", V_("V1", "10 V", "in", "0"), R_("R1", "1 kΩ", "in", "out"),
             R_("R2", "3 kΩ", "out", "0"))
    assert solve_ac(c1, "1 kHz").digest == solve_ac(c1, "1 kHz").digest
    assert solve_ac(c1, "1 kHz").digest != solve_ac(c2, "1 kHz").digest
    assert solve_ac(c1, "1 kHz").digest != solve_ac(c1, "2 kHz").digest


def test_provenance_solver_digest_matches_d2():
    c = ckt("psd", V_("V1", "10 V", "in", "0"), R_("R1", "1 kΩ", "in", "out"),
            R_("R2", "2 kΩ", "out", "0"))
    r = solve_ac(c, "1 kHz")
    assert r.provenance["solver_digest"] == r.solver_result.digest


# -- 17. generality ------------------------------------------------------------------------------------------------------------

def _ladder(n, with_c=True):
    # F6 refs are a single type letter plus digits: separate R/C counters.
    ri, ci = [0], [0]

    def _r(value, n1, n2):
        ri[0] += 1
        return R_(f"R{ri[0]}", value, n1, n2)

    def _c(value, n1, n2):
        ci[0] += 1
        return C_(f"C{ci[0]}", value, n1, n2)

    comps = [V_("V1", "12 V", "n0", "0"), _r("1 kΩ", "n0", "n1")]
    for k in range(1, n):
        comps.append(_r("1 kΩ", f"n{k}", f"n{k + 1}"))
        if with_c:
            comps.append(_c("100 nF", f"n{k}", "0"))
        else:
            comps.append(_r("2 kΩ", f"n{k}", "0"))
    comps.append(_c("100 nF", f"n{n}", "0") if with_c else _r("2 kΩ", f"n{n}", "0"))
    return ckt(f"lad{n}", *comps)


def test_generality_ladder_scales():
    for n in (2, 3, 4, 8, 16, 32, 64):
        r = solve_ac(_ladder(n), "1 kHz")
        assert r.status == ACStatus.SOLVED, n
        assert r.kcl_max_residual <= Decimal("1E-30"), n
        assert r.kvl_max_residual <= Decimal("1E-30"), n
        assert len(r.node_voltages) == n + 2, n  # n+1 nets + ground


def test_generality_bridge_mesh_star_parallel():
    bridge = ckt("gb", V_("V1", "10 V", "t", "0"), R_("R1", "1 kΩ", "t", "a"),
                 R_("R2", "2 kΩ", "t", "b"), R_("R3", "3 kΩ", "a", "0"),
                 R_("R4", "4 kΩ", "b", "0"), R_("R5", "5 kΩ", "a", "b"),
                 C_("C1", "1 uF", "a", "b"))
    rb = solve_ac(bridge, "500 Hz")
    assert rb.status == ACStatus.SOLVED and rb.kvl_cycles == 4
    mesh = ckt("gm", V_("V1", "10 V", "a", "0"), R_("R1", "1 kΩ", "a", "b"),
               R_("R2", "1 kΩ", "b", "c"), R_("R3", "1 kΩ", "c", "a"),
               R_("R4", "1 kΩ", "b", "0"), L_("L1", "5 mH", "c", "0"))
    rm = solve_ac(mesh, "2 kHz")
    assert rm.status == ACStatus.SOLVED
    assert rm.kcl_max_residual <= Decimal("1E-38")


def test_generality_nonplanar_k33():
    # K3,3 (canonical nonplanar): partitions {a,b,c} x {x,y,z}, R branches.
    comps = [V_("V1", "10 V", "a", "0")]
    k = 1
    for u in ("a", "b", "c"):
        for v in ("x", "y", "z"):
            comps.append(R_(f"R{k}", "1 kΩ", u, v))
            k += 1
    comps += [R_("R10", "1 kΩ", "b", "0"), R_("R11", "1 kΩ", "c", "0"),
              R_("R12", "1 kΩ", "x", "0"), R_("R13", "1 kΩ", "y", "0"),
              R_("R14", "1 kΩ", "z", "0")]
    c = ckt("k33", *comps)
    r = solve_ac(c, "1 kHz")
    assert r.status == ACStatus.SOLVED
    assert r.kcl_max_residual == Decimal(0)
    assert r.kvl_max_residual == Decimal(0)
    assert r.kvl_cycles == len(comps) - 7 + 1  # E - V + 1, V = 7 nets


def test_generality_multi_source_mixed():
    c = ckt("gms", V_("V1", "10 V", "a", "0", phase_=30),
            V_("V2", "5 V", "b", "0", phase_=-45),
            I_("I1", "2 mA", "c", "0", phase_=90),
            R_("R1", "1 kΩ", "a", "c"), C_("C1", "1 uF", "b", "c"),
            L_("L1", "5 mH", "c", "0"), R_("R2", "2 kΩ", "a", "b"))
    r = solve_ac(c, "1 kHz")
    assert r.status == ACStatus.SOLVED
    assert r.kcl_max_residual <= Decimal("1E-38")
    assert r.kvl_max_residual <= Decimal("1E-38")
