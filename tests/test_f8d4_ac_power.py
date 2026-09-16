"""F8-D4 AC power analysis: element laws, conservation, oracle, metamorphic.

Conventions: EXACT assertions are representation-exact (Fractions, no
tolerances). HP assertions carry explicit tolerances. Closed-form
expected values are transcribed literals and direct formulas evaluated
in this file — never outputs of the engine under test. ngspice 47 is an
external oracle (peak convention normalized before comparison); it
never generates unit-test expected values. Conservation alone is never
treated as sufficiency (a global sign flip preserves it): element laws,
closed forms and the oracle close the loop.
"""
import ast
import json
import pathlib
from decimal import Decimal
from fractions import Fraction

import pytest

from academic_core.domain.engineering.ac import (
    ACStatus,
    analyze_power,
    compute_element_power,
    solve_ac,
    verify_conservation,
)
from academic_core.domain.engineering.ac.power import (
    POWER_CONVENTION,
    PowerAnalysisError,
)
from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.math import DecimalComplex, RationalComplex
from academic_core.domain.engineering.math.linsolve import NumericMode
from academic_core.domain.engineering.math.trig import make_context
from academic_core.domain.engineering.units import POWER, parse_quantity, parse_unit

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


def V_(ref, value, np_, nm, phase_=0, punit="deg"):
    params = {}
    if not (isinstance(phase_, int) and phase_ == 0):
        params["phase"] = phase_
    if punit != "deg":
        params["phase_unit"] = punit
    return Component(ref, "V", Q(value), {"+": np_, "-": nm}, dict(params))


def I_(ref, value, np_, nm, phase_=0, punit="deg"):
    params = {}
    if not (isinstance(phase_, int) and phase_ == 0):
        params["phase"] = phase_
    if punit != "deg":
        params["phase_unit"] = punit
    return Component(ref, "I", Q(value), {"+": np_, "-": nm}, dict(params))


def ckt(name, *comps):
    c = Circuit(name)
    for e in comps:
        c.add(e)
    return c


def analyze(circuit, freq):
    sol = solve_ac(circuit, freq)
    assert sol.status == ACStatus.SOLVED, sol.diagnostics
    return analyze_power(sol), sol


# -- 1. units ----------------------------------------------------------------------------------

def test_units_w_var_va_parse_and_share_power_dimension():
    for s in ("W", "kW", "var", "kvar", "mvar", "VA", "kVA"):
        u = parse_unit(s)
        assert u.dimension == POWER, s
    assert parse_unit("var").display == "var"
    assert parse_unit("kvar").display == "kvar"
    assert parse_unit("VA").display == "VA"
    assert parse_unit("kVA").display == "kVA"


def test_units_var_va_conversions():
    assert parse_quantity("5 kvar").to_base() == Decimal(5000)
    assert parse_quantity("5 kvar").convert_to("W").value == Decimal(5000)
    assert parse_quantity("3 kVA").convert_to("VA").value == Decimal(3000)
    assert parse_quantity("2 W").convert_to("var").value == Decimal(2)


def test_units_w_behavior_unchanged():
    assert parse_quantity("1 kohm").to_base() == Decimal(1000)
    assert parse_quantity("10 V").convert_to("mV").value == Decimal(10000)
    assert parse_unit("W").display == "W"
    assert parse_unit("kW").display == "kW"


def test_units_no_separate_power_dimensions():
    # W/var/VA are role labels over one physical dimension by design.
    assert parse_unit("var").dimension == parse_unit("W").dimension
    assert parse_unit("VA").dimension == parse_unit("W").dimension


# -- 2. element laws -------------------------------------------------------------------------------

def test_resistor_exact_law():
    # V=12 peak over 4k: P = |V|^2/(2R) = 144/8000 = 9/500, Q = 0.
    a, _ = analyze(ckt("r", V_("V1", "12 V", "n", "0"), R_("R1", "4 kOhm", "n", "0")),
                   "60 Hz")
    e = a.power_of("R1")
    assert e.active == Fraction(9, 500) and e.reactive == Fraction(0)
    assert e.apparent == Decimal("0.018") and e.pf == Decimal(1)
    assert e.regime == "absorbing"


def test_inductor_law():
    # L=10mH @1kHz, |V|=10: Q = |V|^2/(2wL) with wL from PI50 here.
    wl = CTX.multiply(CTX.multiply(CTX.multiply(Decimal(2), PI50), Decimal(1000)),
                      Decimal("0.01"))
    a, _ = analyze(ckt("l", V_("V1", "10 V", "n", "0"), L_("L1", "10 mH", "n", "0")),
                   "1000 Hz")
    e = a.power_of("L1")
    assert abs(e.active) <= Decimal("1E-45") * e.apparent  # HP noise, not Q
    assert e.reactive > 0
    exp = CTX.divide(Decimal(100), CTX.multiply(Decimal(2), wl))
    assert abs(CTX.subtract(e.reactive, exp)) <= Decimal("1E-40")
    assert abs(e.pf) <= Decimal("1E-45")


def test_capacitor_law():
    # C=1uF @1kHz, |V|=10: Q = -wC|V|^2/2 with wC from PI50 here.
    wc = CTX.multiply(CTX.multiply(CTX.multiply(Decimal(2), PI50), Decimal(1000)),
                      Decimal("0.000001"))
    a, _ = analyze(ckt("c", V_("V1", "10 V", "n", "0"), C_("C1", "1 uF", "n", "0")),
                   "1000 Hz")
    e = a.power_of("C1")
    assert abs(e.active) <= Decimal("1E-45") * e.apparent
    assert e.reactive < 0
    exp = CTX.minus(CTX.divide(CTX.multiply(wc, Decimal(100)), Decimal(2)))
    assert abs(CTX.subtract(e.reactive, exp)) <= Decimal("1E-40")
    assert abs(e.pf) <= Decimal("1E-45")


def test_rl_series_power_split():
    a, _ = analyze(ckt("rl", V_("V1", "10 V", "in", "0"),
                       R_("R1", "100 ohm", "in", "a"), L_("L1", "10 mH", "a", "0")),
                   "1000 Hz")
    pr, pl = a.power_of("R1"), a.power_of("L1")
    assert pr.active > 0 and abs(pr.reactive) <= Decimal("1E-45") * pr.apparent
    assert abs(pl.active) <= Decimal("1E-45") * pl.apparent and pl.reactive > 0
    assert a.conservation.passed


def test_rc_series_power_split():
    a, _ = analyze(ckt("rc", V_("V1", "10 V", "in", "0"),
                       R_("R1", "1 kOhm", "in", "a"), C_("C1", "1 uF", "a", "0")),
                   "1000 Hz")
    pr, pc = a.power_of("R1"), a.power_of("C1")
    assert pr.active > 0 and abs(pr.reactive) <= Decimal("1E-45") * pr.apparent
    assert abs(pc.active) <= Decimal("1E-45") * pc.apparent and pc.reactive < 0
    assert a.conservation.passed


def test_rlc_series_resonance_power():
    # At f0 the reactances cancel: source sees R only (P=V^2/2R, Q~0).
    a, _ = analyze(ckt("rlc", V_("V1", "10 V", "in", "0"),
                       R_("R1", "10 ohm", "in", "a"), L_("L1", "10 mH", "a", "b"),
                       C_("C1", "10 uF", "b", "0")), "503.29212104487018 Hz")
    ps = a.power_of("V1")
    assert abs(CTX.subtract(ps.active, Decimal(-5))) <= Decimal("1E-6") * Decimal(5)
    assert abs(ps.reactive) <= Decimal("1E-6") * abs(ps.active)
    pl, pc = a.power_of("L1"), a.power_of("C1")
    assert pl.reactive > 0 and pc.reactive < 0  # large, opposite, cancelling
    assert abs(CTX.add(pl.reactive, pc.reactive)) <= Decimal("1E-3") * pl.reactive


def test_parallel_rl_laws():
    a, _ = analyze(ckt("prl", V_("V1", "5 V", "n", "0"),
                       R_("R1", "1 kOhm", "n", "0"), L_("L1", "10 mH", "n", "0")),
                   "1000 Hz")
    pr, pl = a.power_of("R1"), a.power_of("L1")
    # |V|^2/2R = 0.0125 up to working-precision rounding of the solve.
    assert abs(CTX.subtract(pr.active, Decimal("0.0125"))) <= Decimal("1E-45")
    assert abs(pr.reactive) <= Decimal("1E-45") * pr.apparent
    assert abs(pl.active) <= Decimal("1E-45") * pl.apparent and pl.reactive > 0


def test_parallel_rc_laws():
    a, _ = analyze(ckt("prc", V_("V1", "5 V", "n", "0"),
                       R_("R1", "1 kOhm", "n", "0"), C_("C1", "1 uF", "n", "0")),
                   "1000 Hz")
    pr, pc = a.power_of("R1"), a.power_of("C1")
    assert pr.active > 0 and abs(pr.reactive) <= Decimal("1E-45") * pr.apparent
    assert abs(pc.active) <= Decimal("1E-45") * pc.apparent and pc.reactive < 0


def test_parallel_rlc_conservation():
    a, _ = analyze(ckt("prlc", I_("I1", "1 A", "n", "0"),
                       R_("R1", "1 kOhm", "n", "0"), L_("L1", "10 mH", "n", "0"),
                       C_("C1", "1 uF", "n", "0")), "1000 Hz")
    assert a.conservation.passed
    assert a.power_of("I1").regime == "delivering"


# -- 3. topologies ------------------------------------------------------------------------------------

def test_topology_bridge():
    a, _ = analyze(ckt("br", V_("V1", "10 V", "t", "0"),
                       R_("R1", "1 kOhm", "t", "a"), R_("R2", "2 kOhm", "t", "b"),
                       R_("R3", "1 kOhm", "a", "0"), R_("R4", "2 kOhm", "b", "0"),
                       R_("R5", "1 kOhm", "a", "b")), "1 kHz")
    assert a.conservation.passed
    assert a.conservation.total_S == RationalComplex(Fraction(0), Fraction(0))
    assert len(a.elements) == 6


def test_topology_ladder():
    comps = [V_("V1", "12 V", "n0", "0"), R_("R1", "1 kOhm", "n0", "n1")]
    for k in range(1, 4):
        comps.append(R_(f"R{2 * k}", "1 kOhm", f"n{k}", f"n{k + 1}"))
        comps.append(C_(f"C{k}", "100 nF", f"n{k}", "0"))
    comps.append(C_("C4", "100 nF", "n4", "0"))
    a, _ = analyze(ckt("lad", *comps), "1 kHz")
    assert a.conservation.passed
    assert a.power_of("V1").regime == "delivering"


def test_topology_mesh():
    a, _ = analyze(ckt("mesh", V_("V1", "10 V", "a", "0"),
                       R_("R1", "1 kOhm", "a", "b"), R_("R2", "1 kOhm", "b", "c"),
                       R_("R3", "1 kOhm", "c", "a"), R_("R4", "1 kOhm", "b", "0"),
                       L_("L1", "5 mH", "c", "0")), "2 kHz")
    assert a.conservation.passed
    assert len(a.elements) == 6


def test_topology_high_degree_star():
    comps = [V_("V1", "5 V", "ctr", "0")]
    for k in range(12):
        comps.append(R_(f"R{k + 1}", "1 kOhm", "ctr", "0"))
    a, _ = analyze(ckt("star", *comps), "1 kHz")
    assert a.conservation.passed
    tot_p = sum((e.active for e in a.elements if e.ref != "V1"), Fraction(0))
    assert tot_p == Fraction(12) * Fraction(25, 2000)  # 12 x 25/2000 W
    assert a.power_of("V1").active == -tot_p


def test_topology_parallel_same_endpoints():
    a, _ = analyze(ckt("par", V_("V1", "10 V", "n", "0"),
                       R_("R1", "1 kOhm", "n", "0"), R_("R2", "2 kOhm", "n", "0"),
                       C_("C1", "1 uF", "n", "0")), "2 kHz")
    assert a.conservation.passed
    assert len(a.elements) == 4


def test_topology_nongnd_branch():
    # R2 floats between non-ground nodes: its power uses V(a)-V(b).
    a, _ = analyze(ckt("ng", V_("V1", "9 V", "a", "0"),
                       R_("R1", "1 kOhm", "a", "b"), R_("R2", "2 kOhm", "b", "c"),
                       R_("R3", "3 kOhm", "c", "0")), "1 kHz")
    e = a.power_of("R2")
    assert e.active > 0 and e.reactive == Fraction(0)
    assert a.conservation.passed


# -- 4. sources ------------------------------------------------------------------------------------------

def test_source_delivering():
    a, _ = analyze(ckt("sd", V_("V1", "10 V", "n", "0"), R_("R1", "1 kOhm", "n", "0")),
                   "1 kHz")
    e = a.power_of("V1")
    assert e.active == Fraction(-1, 20) and e.pf == Decimal(-1)
    assert e.regime == "delivering"


def test_source_absorbing_opposed_sources():
    # V2=15V overpowers V1=10V through R: V1 absorbs (being charged).
    a, _ = analyze(ckt("sa", V_("V1", "10 V", "a", "0"), V_("V2", "15 V", "b", "0"),
                       R_("R1", "1 kOhm", "a", "b")), "1 kHz")
    assert a.power_of("V2").active < 0
    assert a.power_of("V1").active > 0
    assert a.power_of("V1").regime == "absorbing"
    assert a.conservation.passed


def test_current_source_power():
    # 1A into 1k: V=1000V; S = 1/2 * 1000 * conj(-1) = -500 W delivered.
    a, _ = analyze(ckt("cs", I_("I1", "1 A", "n", "0"), R_("R1", "1 kOhm", "n", "0")),
                   "1 kHz")
    e = a.power_of("I1")
    assert e.active == Fraction(-500) and e.reactive == Fraction(0)
    assert e.regime == "delivering"
    # Branch current is -Is per D3 convention: do NOT invert again.
    assert a.power_of("R1").active == Fraction(500)


def test_multiple_voltage_sources():
    a, _ = analyze(ckt("mv", V_("V1", "10 V", "a", "0", phase_=30),
                       V_("V2", "5 V", "b", "0", phase_=-45),
                       R_("R1", "1 kOhm", "a", "b"), R_("R2", "2 kOhm", "b", "0")),
                   "1 kHz")
    assert a.conservation.passed
    assert len(a.elements) == 4


def test_mixed_vi_sources():
    a, _ = analyze(ckt("mx", V_("V1", "10 V", "a", "0", phase_=30),
                       I_("I1", "2 mA", "c", "0", phase_=90),
                       R_("R1", "1 kOhm", "a", "c"), C_("C1", "1 uF", "b", "c"),
                       L_("L1", "5 mH", "c", "0"), R_("R2", "2 kOhm", "a", "b")),
                   "1 kHz")
    assert a.conservation.passed


# -- 5. zero / PF cases ---------------------------------------------------------------------------------------

def test_zero_power_bridge_center():
    # Balanced bridge: R5 carries no voltage/current -> S = 0 exactly.
    a, _ = analyze(ckt("z0", V_("V1", "10 V", "t", "0"),
                       R_("R1", "1 kOhm", "t", "a"), R_("R2", "1 kOhm", "t", "b"),
                       R_("R3", "1 kOhm", "a", "0"), R_("R4", "1 kOhm", "b", "0"),
                       R_("R5", "1 kOhm", "a", "b")), "1 kHz")
    e = a.power_of("R5")
    assert e.power == RationalComplex(Fraction(0), Fraction(0))
    assert e.pf is None and e.regime == "zero"
    assert any("PF" in d or "undefined" in d for d in a.diagnostics)


def test_zero_power_open_source():
    # Zero-valued current source: branch current is -0 -> S = 0.
    a, _ = analyze(ckt("z1", V_("V1", "10 V", "a", "0"),
                       I_("I1", "0 A", "a", "b"), R_("R1", "1 kOhm", "b", "0")),
                   "1 kHz")
    e = a.power_of("I1")
    assert e.power == RationalComplex(Fraction(0), Fraction(0))
    assert e.pf is None


def test_pf_plus_one_minus_one_zero():
    r, _ = analyze(ckt("p1", V_("V1", "10 V", "n", "0"), R_("R1", "1 kOhm", "n", "0")),
                   "1 kHz")
    assert r.power_of("R1").pf == Decimal(1)
    assert r.power_of("V1").pf == Decimal(-1)
    l, _ = analyze(ckt("p0", V_("V1", "10 V", "n", "0"), L_("L1", "10 mH", "n", "0")),
                   "1000 Hz")
    assert abs(l.power_of("L1").pf) <= Decimal("1E-45")


def test_pf_intermediate_and_negative():
    a, _ = analyze(ckt("pm", V_("V1", "10 V", "in", "0"),
                       R_("R1", "100 ohm", "in", "a"), L_("L1", "10 mH", "a", "0")),
                   "1000 Hz")
    pr = a.power_of("R1")
    assert pr.pf == Decimal(1)  # resistive branch: exact unity PF
    ps = a.power_of("V1")
    assert Decimal(-1) < ps.pf < Decimal(0)  # source sees the mixed load
    assert ps.regime == "delivering"


def test_q_sign_separate_from_pf():
    a, _ = analyze(ckt("qs", V_("V1", "5 V", "n", "0"),
                       L_("L1", "10 mH", "n", "0"), C_("C1", "100 uF", "n", "0")),
                   "1000 Hz")
    # wL=62.8, 1/(wC)=1.59: net capacitive tank, no resistor anywhere,
    # so the source exchanges only vars (P ~ 0) while absorbing +7.65 var
    # to balance the tank. Lead/lag lives on the Q axis, never inferred
    # from the PF sign alone.
    ps = a.power_of("V1")
    assert abs(ps.active) <= Decimal("1E-40") * abs(ps.reactive)
    assert ps.reactive > 0
    assert ps.pf is not None and abs(ps.pf) <= Decimal("1E-40")
    assert a.power_of("L1").reactive > 0 and a.power_of("C1").reactive < 0


# -- 6. conservation -----------------------------------------------------------------------------------------------

def test_conservation_exact_zero():
    a, _ = analyze(ckt("ce", V_("V1", "9 V", "a", "0"),
                       R_("R1", "1 kOhm", "a", "b"), R_("R2", "2 kOhm", "b", "0")),
                   "1 kHz")
    assert a.conservation.total_S == RationalComplex(Fraction(0), Fraction(0))
    assert a.conservation.total_P == Fraction(0)
    assert a.conservation.total_Q == Fraction(0)
    assert a.conservation.passed


def test_conservation_hp_bound_exact_formula():
    # The bound must equal the documented two-term formula recomputed
    # here: Tellegen defect + rounding account. No hidden epsilon.
    a, sol = analyze(ckt("cb", V_("V1", "10 V", "in", "0", phase_=30),
                         R_("R1", "1 kOhm", "in", "out"), C_("C1", "1 uF", "out", "0")),
                     "2 kHz")
    assert a.conservation.passed
    maxv = max((nv.phasor.modulus() for nv in sol.node_voltages))
    kcl_term = CTX.multiply(CTX.multiply(maxv, Decimal(len(sol.node_voltages))),
                            sol.kcl_max_residual)
    maxs = max((e.apparent for e in a.elements))
    rounding = CTX.multiply(
        CTX.multiply(Decimal(len(a.elements) * 64), Decimal("1E-50")), maxs)
    expect = CTX.add(kcl_term, rounding)
    assert a.conservation.bound == expect
    assert a.conservation.total_S.modulus() <= expect
    # ...and it stays tight: bound/scale far below sloppy-epsilon regimes.
    assert expect / max(maxs, Decimal("1E-300")) <= Decimal("1E-30")


def test_conservation_refuses_nonsolved():
    bad = solve_ac(ckt("ns", V_("V1", "10 V", "n", "0"), V_("V2", "5 V", "n", "0")),
                   "1 kHz")
    assert bad.status == ACStatus.INCONSISTENT
    with pytest.raises(PowerAnalysisError):
        analyze_power(bad)
    bad2 = solve_ac(ckt("ns2", V_("V1", "10 V", "n", "0"), V_("V2", "10 V", "n", "0")),
                    "1 kHz")
    assert bad2.status == ACStatus.SINGULAR
    with pytest.raises(PowerAnalysisError):
        analyze_power(bad2)


def test_conservation_verify_standalone():
    e1 = compute_element_power(RationalComplex(Fraction(10), Fraction(0)),
                               RationalComplex(Fraction(1, 100), Fraction(0)), "R1")
    e2 = compute_element_power(RationalComplex(Fraction(10), Fraction(0)),
                               RationalComplex(Fraction(-1, 100), Fraction(0)), "V1")
    rep = verify_conservation((e1, e2), exact=True, kcl_max=Decimal(0),
                              max_vmag=Decimal(10), n_nets=2)
    assert rep.passed and rep.total_P == Fraction(0)
    with pytest.raises(PowerAnalysisError):
        verify_conservation((), exact=True, kcl_max=Decimal(0),
                            max_vmag=Decimal(0), n_nets=0)


# -- 7. peak / RMS ------------------------------------------------------------------------------------------------------

def test_explicit_half_factor():
    v = RationalComplex(Fraction(10), Fraction(0))
    i = RationalComplex(Fraction(1, 100), Fraction(0))
    e = compute_element_power(v, i, "R1")
    assert e.power == RationalComplex(Fraction(10), Fraction(0)) * i.conjugate() / 2
    assert e.active == Fraction(1, 20)  # NOT 1/10 (that would be V*conj(I))


def test_rms_consistency_identity():
    # S = Vrms * conj(Irms) with complex RMS phasors = peak/sqrt(2):
    # catches any 1/2-factor bug. Independent path from analyze_power.
    from academic_core.domain.engineering.ac import rms_from_peak

    a, _ = analyze(ckt("rms", V_("V1", "10 V", "in", "0", phase_=30),
                       R_("R1", "1 kOhm", "in", "out"), C_("C1", "1 uF", "out", "0")),
                   "2 kHz")
    sq2 = CTX.sqrt(Decimal(2))
    sol = solve_ac(ckt("rms2", V_("V1", "10 V", "in", "0", phase_=30),
                       R_("R1", "1 kOhm", "in", "out"), C_("C1", "1 uF", "out", "0")),
                   "2 kHz")
    for bc, bv in zip(sorted(sol.branch_currents, key=lambda x: x.ref.upper()),
                      sorted(sol.branch_voltages, key=lambda x: x.ref.upper())):
        assert bc.ref == bv.ref
        vm = rms_from_peak(bc.current.modulus() if False else bv.voltage.modulus())
        im = rms_from_peak(bc.current.modulus())
        # Rebuild complex RMS phasors by scaling peak phasors with (rms/peak).
        vpeak_mag = bv.voltage.modulus()
        scale = CTX.divide(vm, vpeak_mag) if vpeak_mag != 0 else Decimal(0)
        vr = DecimalComplex(CTX.multiply(bv.voltage.re, scale),
                            CTX.multiply(bv.voltage.im, scale))
        ir = DecimalComplex(CTX.multiply(bc.current.re, scale),
                            CTX.multiply(bc.current.im, scale))
        s_rms = vr * ir.conjugate()
        got = a.power_of(bc.ref)
        assert (s_rms - got.power).modulus() <= Decimal("1E-38"), bc.ref


def test_peak_not_rms_regression():
    # P = |V|^2/(2R): with |V|=10, R=1k -> 0.05 W, never 0.1 W.
    a, _ = analyze(ckt("pkr", V_("V1", "10 V", "n", "0"), R_("R1", "1 kOhm", "n", "0")),
                   "1 kHz")
    assert a.power_of("R1").active == Fraction(1, 20)
    assert a.power_of("R1").active != Fraction(1, 10)


# -- 8. independent closed forms -----------------------------------------------------------------------------------------------

def test_closed_form_resistor():
    # P = |V|^2/(2R): divider R1=1k/R2=2k, Vs=10 -> Vout=20/3.
    a, _ = analyze(ckt("cf", V_("V1", "10 V", "in", "0"),
                       R_("R1", "1 kOhm", "in", "out"), R_("R2", "2 kOhm", "out", "0")),
                   "1 kHz")
    vo = Fraction(20, 3)
    assert a.power_of("R2").active == vo * vo / (2 * Fraction(2000))
    assert a.power_of("R2").reactive == Fraction(0)


def test_closed_form_inductor():
    # Q = |V|^2/(2wL), |V|=10, wL from PI50.
    wl = CTX.multiply(CTX.multiply(CTX.multiply(Decimal(2), PI50), Decimal(1000)),
                      Decimal("0.01"))
    a, _ = analyze(ckt("cfl", V_("V1", "10 V", "n", "0"), L_("L1", "10 mH", "n", "0")),
                   "1000 Hz")
    exp = CTX.divide(Decimal(100), CTX.multiply(Decimal(2), wl))
    assert abs(CTX.subtract(a.power_of("L1").reactive, exp)) <= Decimal("1E-40")
    assert a.power_of("L1").active == Decimal(0)


def test_closed_form_capacitor():
    # Q = -wC|V|^2/2, |V|=10, wC from PI50.
    wc = CTX.multiply(CTX.multiply(CTX.multiply(Decimal(2), PI50), Decimal(1000)),
                      Decimal("0.000001"))
    a, _ = analyze(ckt("cfc", V_("V1", "10 V", "n", "0"), C_("C1", "1 uF", "n", "0")),
                   "1000 Hz")
    exp = CTX.minus(CTX.divide(CTX.multiply(wc, Decimal(100)), Decimal(2)))
    assert abs(CTX.subtract(a.power_of("C1").reactive, exp)) <= Decimal("1E-40")
    assert a.power_of("C1").active == Decimal(0)


# -- 9. multi-source crossterms -----------------------------------------------------------------------------------------------------

def test_power_not_linear_cross_terms():
    # V1 clamps node a at 10 V; I1 drives node b through R1/R2.
    # Joint: Vb = 7.5 V. Singles: V-only (I open) gives 5 V, I-only
    # (V shorted to 0 V) gives 2.5 V. Voltages superpose (5+2.5=7.5);
    # resistor power does NOT: |7.5|^2/2R = 9/320 vs 4/320 + 1/320.
    jx = ckt("jx", V_("V1", "10 V", "a", "0"), I_("I1", "5 mA", "b", "0"),
             R_("R1", "1 kOhm", "a", "b"), R_("R2", "1 kOhm", "b", "0"))
    vx = ckt("vx", V_("V1", "10 V", "a", "0"),
             R_("R1", "1 kOhm", "a", "b"), R_("R2", "1 kOhm", "b", "0"))
    ix = ckt("ix", V_("V1", "0 V", "a", "0"), I_("I1", "5 mA", "b", "0"),
             R_("R1", "1 kOhm", "a", "b"), R_("R2", "1 kOhm", "b", "0"))
    joint, jsol = analyze(jx, "1 kHz")
    v_only, _ = analyze(vx, "1 kHz")
    i_only, _ = analyze(ix, "1 kHz")
    assert jsol.voltage_of("b") == RationalComplex(Fraction(15, 2), Fraction(0))
    assert v_only.power_of("R2").active == Fraction(1, 80)  # |5|^2/2R
    assert i_only.power_of("R2").active == Fraction(1, 320)  # |2.5|^2/2R
    pj = joint.power_of("R2").active
    ps = v_only.power_of("R2").active + i_only.power_of("R2").active
    assert pj == Fraction(9, 320) and ps == Fraction(5, 320) and pj != ps


# -- 10. metamorphic --------------------------------------------------------------------------------------------------------------------

def test_metamorphic_amplitude_scaling_exact():
    def build(v):
        return ckt("mk", V_("V1", f"{v} V", "in", "0"),
                   R_("R1", "1 kOhm", "in", "out"), R_("R2", "2 kOhm", "out", "0"))

    r1, _ = analyze(build(10), "1 kHz")
    r2, _ = analyze(build(30), "1 kHz")
    for e1, e2 in zip(r1.elements, r2.elements):
        assert e1.ref == e2.ref
        assert e2.power == e1.power * 9
        assert e2.active == e1.active * 9 and e2.reactive == e1.reactive * 9
        assert e2.apparent == e1.apparent * 9 and e2.pf == e1.pf


def test_metamorphic_amplitude_scaling_hp():
    def build(v):
        return ckt("mkh", V_("V1", f"{v} V", "in", "0", phase_=30),
                   R_("R1", "1 kOhm", "in", "out"), C_("C1", "1 uF", "out", "0"))

    r1, _ = analyze(build(10), "2 kHz")
    r2, _ = analyze(build(20), "2 kHz")
    for e1, e2 in zip(r1.elements, r2.elements):
        assert (e2.power - e1.power * 4).modulus() <= Decimal("1E-36")
        assert abs(CTX.subtract(e2.pf, e1.pf)) <= Decimal("1E-45")


def test_metamorphic_permutation_identical():
    c1 = ckt("mp", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "out"),
             C_("C1", "1 uF", "out", "0"))
    c2 = ckt("mp", C_("C1", "1 uF", "out", "0"), R_("R1", "1 kOhm", "in", "out"),
             V_("V1", "10 V", "in", "0"))
    a1, _ = analyze(c1, "1 kHz")
    a2, _ = analyze(c2, "1 kHz")
    assert a1.digest == a2.digest


def test_metamorphic_node_rename_equivalent():
    c1 = ckt("mn", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "out"),
             R_("R2", "2 kOhm", "out", "0"))
    c2 = ckt("mn", V_("V1", "10 V", "src", "0"), R_("R1", "1 kOhm", "src", "dst"),
             R_("R2", "2 kOhm", "dst", "0"))
    a1, _ = analyze(c1, "1 kHz")
    a2, _ = analyze(c2, "1 kHz")
    assert a1.power_of("R1").power == a2.power_of("R1").power
    assert a1.conservation.total_P == a2.conservation.total_P


def test_metamorphic_conjugation_algebraic_only():
    # conj(S) = P - jQ is an algebraic identity of the computation, NOT
    # a physical invariance (conjugated phasors leave the e^+jwt regime).
    v = DecimalComplex(Decimal("3"), Decimal("4"))
    i = DecimalComplex(Decimal("1"), Decimal("-2"))
    e = compute_element_power(v, i, "X")
    ec = compute_element_power(v.conjugate(), i.conjugate(), "Xc")
    assert ec.power == e.power.conjugate()
    assert ec.active == e.active and ec.reactive == -e.reactive


# -- 11. ngspice oracle ------------------------------------------------------------------------------------------------------------------

def _ng_backend():
    from academic_core.infrastructure.ngspice import NgSpiceBackend

    b = NgSpiceBackend()
    return b if b.detect().verified else None


NG = _ng_backend()


def _spice_netlist(circuit):
    lines = [f"* D4 oracle {circuit.name}"]
    for e in sorted(circuit.components, key=lambda x: x.ref.upper()):
        t = e.type.upper()
        pins = " ".join(e.pins[p] for p in
                        (("1", "2") if t in ("R", "L", "C") else ("+", "-")))
        if t == "V":
            ph = e.parameters.get("phase", 0)
            unit = str(e.parameters.get("phase_unit", "deg")).lower()
            ph_d = Decimal(str(ph))
            deg = ph_d if unit == "deg" else ph_d * Decimal("57.295779513082320876798154814105")
            lines.append(f"{e.ref.upper()} {pins} dc 0 ac {format(e.value.to_base(), 'f')} {deg}")
        elif t in ("R", "L", "C"):
            lines.append(f"{e.ref.upper()} {pins} {format(e.value.to_base(), 'f')}")
        else:
            raise AssertionError("oracle netlists use V+R/L/C only")
    lines.append(".end")
    return "\n".join(lines) + "\n"


def _oracle(circuit, freq_hz):
    from academic_core.domain.engineering.simulation import ACAnalysis

    assert NG is not None
    ac = ACAnalysis(sweep_type="lin", points=2, fstart=str(freq_hz),
                    fstop=str(int(freq_hz) + 1))
    res = NG.simulate(_spice_netlist(circuit), analyses=(ac,))
    assert res.status == "COMPLETED"
    return res


def _ref_power(res, vnode, isrc, freq_hz):
    # S = 1/2 V conj(I) from oracle samples (peak both sides).
    v = res.sample_complex_at(f"v({vnode})", str(freq_hz))
    assert v is not None
    cur = res.sample_complex_at(f"i({isrc})", str(freq_hz))
    assert cur is not None
    p = 0.5 * (v.real * cur.real + v.imag * cur.imag)
    q = 0.5 * (v.imag * cur.real - v.real * cur.imag)
    return p, q, abs(complex(p, q))


def _check_power(got, ref, tol_rel=0.005, tol_abs=0.003):
    p, q, _ = ref
    scale = max(1.0, abs(p), abs(q))
    assert abs(float(got.active) - p) <= max(tol_abs, tol_rel * scale)
    assert abs(float(got.reactive) - q) <= max(tol_abs, tol_rel * scale)
    assert (got.active >= 0) == (p >= 0) or abs(p) <= tol_abs
    assert (got.reactive >= 0) == (q >= 0) or abs(q) <= tol_abs


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_resistor_power():
    c = ckt("or", V_("V1", "10 V", "n", "0"), R_("R1", "1 kOhm", "n", "0"))
    a, _ = analyze(c, "1000 Hz")
    pref = _ref_power(_oracle(c, 1000), "n", "v1", 1000)
    # Oracle ref is the SOURCE power (delivering, P<0); the resistor
    # absorbs the opposite. Both directions checked explicitly.
    _check_power(a.power_of("V1"), pref)
    _check_power(a.power_of("R1"), (-pref[0], -pref[1], pref[2]))


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_rl_power():
    c = ckt("orl", V_("V1", "10 V", "in", "0"), R_("R1", "100 ohm", "in", "a"),
            L_("L1", "10 mH", "a", "0"))
    a, _ = analyze(c, "1000 Hz")
    res = _oracle(c, 1000)
    va = res.sample_complex_at("v(a)", "1000")
    vin = res.sample_complex_at("v(in)", "1000")
    i = res.sample_complex_at("i(v1)", "1000")
    # Resistor power from its own branch drop (independent of D3 mapping).
    # Resistor power from its own branch drop. KCL at node in gives
    # I_R1(in->a) = -I_V1, hence the negation (reference, not engine).
    p = -0.5 * ((vin.real - va.real) * i.real + (vin.imag - va.imag) * i.imag)
    q = -0.5 * ((vin.imag - va.imag) * i.real - (vin.real - va.real) * i.imag)
    _check_power(a.power_of("R1"), (p, q, abs(complex(p, q))))
    # Inductor power via KCL at node a (only R1 and L1 meet there):
    # entering current (Vin-Va)/R leaves through L1: I_L = (Vin-Va)/R.
    ia_re = (vin.real - va.real) / 100.0
    ia_im = (vin.imag - va.imag) / 100.0
    lp = 0.5 * (va.real * ia_re + va.imag * ia_im)
    lq = 0.5 * (va.imag * ia_re - va.real * ia_im)
    _check_power(a.power_of("L1"), (lp, lq, abs(complex(lp, lq))))
    assert lp is not None and lq > 0  # inductive sign from the oracle
    _check_power(a.power_of("V1"), _ref_power(res, "in", "v1", 1000))


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_rc_power():
    c = ckt("orc", V_("V1", "5 V", "in", "0", phase_=45),
            R_("R1", "1 kOhm", "in", "out"), C_("C1", "1 uF", "out", "0"))
    a, _ = analyze(c, "1000 Hz")
    res = _oracle(c, 1000)
    _check_power(a.power_of("V1"), _ref_power(res, "in", "v1", 1000))
    vo = res.sample_complex_at("v(out)", "1000")
    assert vo is not None and vo.real > 0 and vo.imag < 0
    assert a.power_of("C1").reactive < 0


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_rlc_power():
    c = ckt("orlc", V_("V1", "10 V", "in", "0"), R_("R1", "100 ohm", "in", "a"),
            L_("L1", "10 mH", "a", "b"), C_("C1", "1 uF", "b", "0"))
    a, _ = analyze(c, "1000 Hz")
    res = _oracle(c, 1000)
    _check_power(a.power_of("V1"), _ref_power(res, "in", "v1", 1000))
    assert a.power_of("R1").active > 0
    assert a.power_of("L1").reactive > 0 and a.power_of("C1").reactive < 0


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_bridge_power():
    c = ckt("obr", V_("V1", "10 V", "t", "0"), R_("R1", "1 kOhm", "t", "a"),
            R_("R2", "2 kOhm", "t", "b"), R_("R3", "1 kOhm", "a", "0"),
            R_("R4", "2 kOhm", "b", "0"), R_("R5", "1 kOhm", "a", "b"))
    a, _ = analyze(c, "500 Hz")
    res = _oracle(c, 500)
    _check_power(a.power_of("V1"), _ref_power(res, "t", "v1", 500))
    for ref in ("R1", "R2", "R3", "R4", "R5"):
        e = a.power_of(ref)
        assert e.reactive == Fraction(0) and e.active >= 0


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_mesh_source_power():
    c = ckt("omsh", V_("V1", "10 V", "a", "0"), R_("R1", "1 kOhm", "a", "b"),
            R_("R2", "2 kOhm", "b", "0"), R_("R3", "1 kOhm", "a", "c"),
            C_("C1", "500 nF", "c", "0"), L_("L1", "5 mH", "b", "c"),
            R_("R4", "3 kOhm", "b", "c"))
    a, _ = analyze(c, "1500 Hz")
    res = _oracle(c, 1500)
    _check_power(a.power_of("V1"), _ref_power(res, "a", "v1", 1500))
    assert a.conservation.passed


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_current_source_analytical_only():
    # Harness limit (documented): ngspice cannot probe I-source branches,
    # so I-source power is pinned analytically: 2mA∠90 into 1k -> V=j2V,
    # S = 1/2 * j2 * conj(-j2mA) = 1/2 * j2 * j0.002 = -0.002 W delivered.
    a, _ = analyze(ckt("oana", I_("I1", "2 mA", "n", "0", phase_=90),
                       R_("R1", "1 kOhm", "n", "0")), "1000 Hz")
    e = a.power_of("I1")
    assert e.active == Fraction(-1, 500) and e.reactive == Fraction(0)
    assert e.regime == "delivering"


# -- 12. generality -------------------------------------------------------------------------------------------------------------------

def _ladder(n):
    ri, ci = [0], [0]

    def _r(value, n1, n2):
        ri[0] += 1
        return R_(f"R{ri[0]}", value, n1, n2)

    def _c(value, n1, n2):
        ci[0] += 1
        return C_(f"C{ci[0]}", value, n1, n2)

    comps = [V_("V1", "12 V", "n0", "0"), _r("1 kOhm", "n0", "n1")]
    for k in range(1, n):
        comps.append(_r("1 kOhm", f"n{k}", f"n{k + 1}"))
        comps.append(_c("100 nF", f"n{k}", "0"))
    comps.append(_c("100 nF", f"n{n}", "0"))
    return ckt(f"lad{n}", *comps)


def test_generality_ladder_power_scales():
    for n in (1, 2, 4, 8, 16, 32, 64):
        a, sol = analyze(_ladder(n), "1 kHz")
        assert a.conservation.passed, n
        assert len(a.elements) == 2 * n + 1, n
        assert a.power_of("V1").regime == "delivering"
        for e in a.elements:
            assert e.regime in ("absorbing", "delivering", "reactive-only", "zero"), e


# -- 13. immutability / determinism --------------------------------------------------------------------------------------------------------

def test_immutability_inputs_untouched():
    c = ckt("im", V_("V1", "10 V", "in", "0", phase_=30),
            R_("R1", "1 kOhm", "in", "out"), C_("C1", "1 uF", "out", "0"))
    sol = solve_ac(c, "2 kHz")
    before_net, before_sol = c.to_netlist(), json.dumps(sol.to_dict(), sort_keys=True)
    a1 = analyze_power(sol)
    assert c.to_netlist() == before_net
    assert json.dumps(sol.to_dict(), sort_keys=True) == before_sol
    a2 = analyze_power(sol)
    assert a1.digest == a2.digest


def test_determinism_100_runs():
    c = ckt("det", V_("V1", "7 V", "in", "0", phase_=45),
            R_("R1", "1 kOhm", "in", "out"), C_("C1", "220 nF", "out", "0"))
    sol = solve_ac(c, "3 kHz")
    first = analyze_power(sol)
    first_dict = json.dumps(first.to_dict(), sort_keys=True)
    for _ in range(100):
        rep = analyze_power(sol)
        assert rep.digest == first.digest
        assert rep.conservation.passed == first.conservation.passed
        assert json.dumps(rep.to_dict(), sort_keys=True) == first_dict


# -- 14. security -------------------------------------------------------------------------------------------------------------------------------

AC_DIR = pathlib.Path(__file__).resolve().parents[1] / "src" / "academic_core" / "domain" / "engineering" / "ac"


def test_security_no_dangerous_calls_or_deps():
    forbidden_calls = {"eval", "exec", "compile", "__import__", "open", "input",
                       "breakpoint"}
    forbidden_roots = {"os", "sys", "pathlib", "sqlite3", "urllib", "socket",
                       "http", "ftplib", "subprocess", "pickle", "marshal",
                       "ctypes", "PySide6", "numpy", "scipy", "math", "cmath",
                       "requests"}
    path = AC_DIR / "power.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in forbidden_calls, node.func.id
        if isinstance(node, ast.Import):
            for al in node.names:
                assert al.name.split(".")[0] not in forbidden_roots, al.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in forbidden_roots, node.module
            assert node.module != "academic_core.infrastructure"
            assert not node.module.startswith("academic_core.infrastructure.")


def test_security_no_float_complex_names():
    path = AC_DIR / "power.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "float" not in names and "complex" not in names


def test_security_no_new_dependencies():
    import inspect

    import academic_core.domain.engineering.ac.power as pw

    tree = ast.parse(inspect.getsource(pw))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(al.name.split(".")[0] for al in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {"__future__", "dataclasses", "decimal", "fractions",
                        "hashlib", "json", "academic_core"}, imported


# -- 15. provenance -------------------------------------------------------------------------------------------------------------------------------

def test_provenance_keys_no_timestamp_deterministic():
    a, _ = analyze(ckt("pr", V_("V1", "10 V", "in", "0"),
                       R_("R1", "1 kOhm", "in", "out"), C_("C1", "1 uF", "out", "0")),
                   "1 kHz")
    for key in ("engine", "version", "frequency", "angular_frequency_rad_per_s",
                "temporal_convention", "amplitude_convention", "power_convention",
                "numeric_mode", "working_precision", "branch_refs",
                "conservation_bound", "conservation_passed", "solution_digest"):
        assert key in a.provenance, key
    assert a.provenance["engine"] == "f8d-ac-power"
    assert a.provenance["version"] == "1.0"
    assert POWER_CONVENTION in a.provenance["power_convention"]
    blob = json.dumps(a.to_dict(), sort_keys=True).lower()
    assert "timestamp" not in blob


def test_provenance_digest_stable_sensitive_linked():
    def build(r2):
        return ckt("pd", V_("V1", "10 V", "in", "0"),
                   R_("R1", "1 kOhm", "in", "out"), R_("R2", f"{r2} kOhm", "out", "0"))

    a1, s1 = analyze(build(2), "1 kHz")
    a2, _ = analyze(build(2), "1 kHz")
    b, _ = analyze(build(3), "1 kHz")
    assert a1.digest == a2.digest
    assert a1.digest != b.digest
    assert a1.provenance["solution_digest"] == s1.digest
    assert len(a1.digest) == 64


def test_provenance_convention_strings():
    a, _ = analyze(ckt("pc", V_("V1", "1 V", "n", "0"), R_("R1", "1 kOhm", "n", "0")),
                   "1 kHz")
    assert "1/2" in a.provenance["power_convention"]
    assert a.frequency == "1 kHz"
    assert a.numeric_mode.value == a.provenance["numeric_mode"]
    assert a.working_precision is None
    assert '"working_precision": null' in json.dumps(a.to_dict())
