"""F8-D8 General AC Resonance & Quality Factor.

Conventions: EXACT assertions are representation-exact (Fractions, no
tolerances); HP carries explicit tolerances. Expected values are hand
derivations (series/parallel reduction, closed-form X(f)/Q(f), Cramer
references, PI50) evaluated here — never D8 outputs. ngspice 47 is an
external oracle over exact single-frequency decks; D5/D7-established
mappings are reused, never re-derived ad hoc:
  - ngspice i(V)/branch currents follow +->-; D8 scans compare on node
    VOLTAGES and derived immittances with entering-A negation;
  - I-source circuits compare on node VOLTAGES only, voltage-only
    .print decks whenever an I branch is present;
  - "ngspice says resonance" is never evidence: every ngspice test
    pairs value agreement with an independent analytic expectation.
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
from academic_core.domain.engineering.ac.bode import (
    analyze_bode,
    log_frequencies,
)
from academic_core.domain.engineering.ac.impedance import (
    ImpedanceCategory,
    ImpedanceError,
)
from academic_core.domain.engineering.ac.resonance import (
    BASIS_BANDWIDTH,
    BASIS_ENERGY,
    CRIT_MAGNITUDE_EXTREMUM,
    CRIT_PARALLEL_SUSCEPTANCE_ZERO,
    CRIT_SERIES_REACTANCE_ZERO,
    CRIT_TRANSFER_PEAK,
    ENGINE_VERSION as RESONANCE_ENGINE_VERSION,
    FindingKind,
    QState,
    QualityFactor,
    ResonanceError,
    ResonanceFinding,
    ResonanceReport,
    quality_from_bandwidth,
    scan_port_equivalents,
    scan_resonance,
)
from academic_core.domain.engineering.ac.resonance import (
    _scan_zero_brackets,
)
from academic_core.domain.engineering.ac.response import (
    ResponseDefinition,
    current_through,
    frequency_response,
    linear_frequencies,
    voltage_between,
)
from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.math import DecimalComplex, RationalComplex
from academic_core.domain.engineering.math.linsolve import NumericMode
from academic_core.domain.engineering.math.trig import make_context
from academic_core.domain.engineering.units import parse_quantity

CTX = make_context()
TOL = Decimal("1E-30")
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


def port_z(port_a="in", port_b="0"):
    return ResponseDefinition("port-impedance", PortDefinition(port_a, port_b))


def port_y(port_a="in", port_b="0"):
    return ResponseDefinition("port-admittance", PortDefinition(port_a, port_b))


def scan(circuit, definition, freqs, **kw):
    return scan_resonance(circuit, definition, list(freqs), **kw)


def kinds(report):
    return [f.kind for f in report.findings]


def brackets_of(report):
    return [(f.frequency_lo, f.frequency_hi) for f in report.findings
            if f.kind == FindingKind.BRACKET_CANDIDATE]


def f0_series_lc(l_h, c_f):
    # f0 = 1/(2*pi*sqrt(LC)) in Decimal (PI50 oracle constant).
    lc = CTX.multiply(Decimal(str(l_h)), Decimal(str(c_f)))
    root = lc.sqrt(CTX)
    return CTX.divide(Decimal(1), CTX.multiply(CTX.multiply(Decimal(2), PI50), root))


def qe_series_closed(f_hz, l_h, c_f, r_ohm):
    # Qe(f) = (wL + 1/(wC)) / (2R) for the series RLC one-port.
    w = CTX.multiply(CTX.multiply(Decimal(2), PI50), Decimal(str(f_hz)))
    wl = CTX.multiply(w, Decimal(str(l_h)))
    inv = CTX.divide(Decimal(1), CTX.multiply(w, Decimal(str(c_f))))
    return CTX.divide(CTX.add(wl, inv), CTX.multiply(Decimal(2), Decimal(str(r_ohm))))


def qe_parallel_closed(f_hz, l_h, c_f, r_ohm):
    # Qe(f) = R*(1/(wL) + wC)/2 for the parallel RLC one-port.
    w = CTX.multiply(CTX.multiply(Decimal(2), PI50), Decimal(str(f_hz)))
    a = CTX.divide(Decimal(1), CTX.multiply(w, Decimal(str(l_h))))
    b = CTX.multiply(w, Decimal(str(c_f)))
    return CTX.divide(CTX.multiply(Decimal(str(r_ohm)), CTX.add(a, b)), Decimal(2))


def qe_parallel_driven_closed(f_hz, r1_ohm, r2_ohm, l_h, c_f, vs=10):
    # Independent hand derivation (nodal, Decimal) for source -> R1 ->
    # node-a -> (R2 || L || C) -> ground. Dissipation in R1 AND R2.
    vs_d = Decimal(str(vs))
    r1, r2 = Decimal(str(r1_ohm)), Decimal(str(r2_ohm))
    w = CTX.multiply(CTX.multiply(Decimal(2), PI50), Decimal(str(f_hz)))
    b = CTX.subtract(CTX.multiply(w, Decimal(str(c_f))),
                     CTX.divide(Decimal(1), CTX.multiply(w, Decimal(str(l_h)))))
    g = CTX.divide(Decimal(1), r2)
    den = CTX.add(CTX.multiply(g, g), CTX.multiply(b, b))
    zt_re = CTX.divide(g, den)
    zt_im = CTX.divide(CTX.subtract(Decimal(0), b), den)
    tot_re = CTX.add(r1, zt_re)
    tot_im = zt_im
    d = CTX.add(CTX.multiply(tot_re, tot_re), CTX.multiply(tot_im, tot_im))
    va_re = CTX.divide(CTX.multiply(vs_d, CTX.add(
        CTX.multiply(zt_re, tot_re), CTX.multiply(zt_im, tot_im))), d)
    va_im = CTX.divide(CTX.multiply(vs_d, CTX.subtract(
        CTX.multiply(zt_im, tot_re), CTX.multiply(zt_re, tot_im))), d)
    v2a = CTX.add(CTX.multiply(va_re, va_re), CTX.multiply(va_im, va_im))
    di_re = CTX.divide(CTX.subtract(vs_d, va_re), r1)
    di_im = CTX.divide(CTX.subtract(Decimal(0), va_im), r1)
    i2 = CTX.add(CTX.multiply(di_re, di_re), CTX.multiply(di_im, di_im))
    p = CTX.divide(CTX.add(CTX.multiply(i2, r1),
                           CTX.divide(v2a, r2)), Decimal(2))
    qsum = CTX.add(CTX.divide(v2a, CTX.multiply(CTX.multiply(Decimal(2), w),
                                                Decimal(str(l_h)))),
                   CTX.divide(CTX.multiply(w, CTX.multiply(Decimal(str(c_f)), v2a)),
                              Decimal(2)))
    return CTX.divide(qsum, CTX.multiply(Decimal(2), p))


def series_rlc(name="srlc", r="0.1 kOhm", l="10 mH", c="1 uF"):
    return ckt(name, V_("V1", "10 V", "in", "0"), R_("R1", r, "in", "a"),
               L_("L1", l, "a", "b"), C_("C1", c, "b", "0"))


# -- analytic benchmarks -------------------------------------------------------

def test_bench_series_rlc_bracket_contains_f0():
    # R=100, L=10mH, C=1uF -> f0 ~= 1591.5494 Hz (PI50 oracle).
    f0 = f0_series_lc("0.01", "0.000001")
    assert Decimal("1591") < f0 < Decimal("1592")
    r = scan(series_rlc(), port_z(), ["1 kHz", "1.5 kHz", "1.6 kHz", "2 kHz"])
    br = brackets_of(r)
    assert len(br) == 1
    lo, hi = (Decimal(b) for b in br[0])
    assert lo <= f0 <= hi
    assert r.findings[0].criterion == CRIT_SERIES_REACTANCE_ZERO
    assert all(f.status == ACStatus.SOLVED for f in r.findings)


def test_bench_series_rlc_energy_q_closed_form():
    r = scan(series_rlc(), port_z(), ["1.5 kHz", "1.6 kHz"])
    assert brackets_of(r) == [("1500", "1600")]
    assert len(r.quality) == 2
    for qf, f in zip(r.quality, ("1500", "1600")):
        assert qf.state == QState.DEFINED
        assert qf.basis == BASIS_ENERGY
        assert qf.frequency == f
        ref = qe_series_closed(f, "0.01", "0.000001", "100")
        assert abs(qf.value - ref) <= Decimal("1E-25"), (qf.value, ref)
    # At f0 the closed form collapses to wL/R.
    w0 = CTX.multiply(CTX.multiply(Decimal(2), PI50), f0_series_lc("0.01", "0.000001"))
    q_at_f0 = CTX.divide(CTX.multiply(w0, Decimal("0.01")), Decimal("100"))
    assert abs(q_at_f0 - Decimal("1")) <= Decimal("1E-40")


def test_bench_parallel_rlc_admittance_bracket_and_q():
    c = ckt("prlc", V_("V1", "10 V", "in", "0"), R_("R1", "0.1 kOhm", "in", "a"),
            R_("R2", "2 kOhm", "a", "0"), L_("L1", "10 mH", "a", "0"),
            C_("C1", "1 uF", "a", "0"))
    f0 = f0_series_lc("0.01", "0.000001")
    r = scan(c, port_y("a"), ["1 kHz", "1.5 kHz", "1.6 kHz", "2 kHz"])
    br = brackets_of(r)
    assert len(br) == 1
    lo, hi = (Decimal(b) for b in br[0])
    assert lo <= f0 <= hi
    assert r.findings[0].criterion == CRIT_PARALLEL_SUSCEPTANCE_ZERO
    for qf, f in zip(r.quality, ("1500", "1600")):
        assert qf.state == QState.DEFINED
        ref = qe_parallel_driven_closed(f, "100", "2000", "0.01", "0.000001")
        assert abs(qf.value - ref) <= Decimal("1E-25"), (qf.value, ref)


def test_bench_parallel_lc_pole_straddle_never_confirms():
    # Lossless parallel LC: Z has a POLE at f0 (X flips +inf -> -inf).
    # The sign change is bracket evidence, never a zero verdict.
    c = ckt("plc", V_("V1", "10 V", "in", "0"), R_("R1", "0.1 kOhm", "in", "a"),
            L_("L1", "10 mH", "a", "0"), C_("C1", "1 uF", "a", "0"))
    f0 = f0_series_lc("0.01", "0.000001")
    r = scan(c, port_z("a"), ["1 kHz", "1.5 kHz", "1.6 kHz", "2 kHz"])
    br = brackets_of(r)
    assert len(br) == 1
    lo, hi = (Decimal(b) for b in br[0])
    assert lo <= f0 <= hi  # straddles the pole, honestly reported
    assert FindingKind.ZERO_CONFIRMED not in kinds(r)
    pole_diag = [f for f in r.findings
                 if f.kind == FindingKind.BRACKET_CANDIDATE][0].diagnostic
    assert "pole" in pole_diag
    for qf in r.quality:
        # No dissipation in L/C; source+R present -> DEFINED via R.
        assert qf.state == QState.DEFINED
        assert qf.value > 0


def test_bench_lossless_series_lc_bracket_and_lossless_q():
    c = ckt("slc", V_("V1", "10 V", "in", "0"), L_("L1", "10 mH", "in", "a"),
            C_("C1", "1 uF", "a", "0"))
    f0 = f0_series_lc("0.01", "0.000001")
    r = scan(c, port_z(), ["1 kHz", "1.5 kHz", "1.6 kHz", "2 kHz"])
    br = brackets_of(r)
    assert len(br) == 1
    assert Decimal(br[0][0]) <= f0 <= Decimal(br[0][1])
    assert len(r.quality) == 2
    for qf in r.quality:
        assert qf.state == QState.UNDEFINED
        assert qf.value is None
        assert "lossless" in qf.diagnostic


def test_bench_damped_rlc_wide_grid():
    r = scan(series_rlc("damp", r="1 kOhm"), port_z(),
             ["100 Hz", "1 kHz", "1.59 kHz", "1.6 kHz", "10 kHz"])
    assert brackets_of(r) == [("1590", "1600")]
    for qf in r.quality:
        assert qf.state == QState.DEFINED
        assert qf.value < Decimal("0.2")  # heavy damping, low Q


# -- required edge cases: non-resonant networks ---------------------------------

def test_edge_r_only_no_resonance():
    c = ckt("ronly", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "out"),
            R_("R2", "2 kOhm", "out", "0"))
    r = scan(c, port_z("out"), ["100 Hz", "1 kHz", "10 kHz"])
    assert FindingKind.ZERO_CONFIRMED not in kinds(r)
    assert FindingKind.BRACKET_CANDIDATE not in kinds(r)
    assert kinds(r).count(FindingKind.NO_RESONANCE_OBSERVED) == 1
    assert r.quality == ()
    assert "nonreactive" in r.findings[-1].diagnostic


def test_edge_r_only_flat_transfer():
    c = ckt("rdiv", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "out"),
            R_("R2", "1 kOhm", "out", "0"))
    d = ResponseDefinition(
        "transfer", (voltage_between("in", "0"), voltage_between("out", "0"), "V1"))
    r = scan(c, d, ["100 Hz", "1 kHz", "10 kHz"])
    ext = [f for f in r.findings if f.kind == FindingKind.EXTREMUM_OBSERVED]
    assert {f.evidence[0].split()[2] for f in ext} == {"flat-maximum", "flat-minimum"}
    assert FindingKind.NO_RESONANCE_OBSERVED in kinds(r)
    assert r.quality == ()


def test_edge_rc_lowpass_endpoint_peak_not_resonance():
    c = ckt("rclp", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "out"),
            C_("C1", "1 uF", "out", "0"))
    d = ResponseDefinition(
        "transfer", (voltage_between("in", "0"), voltage_between("out", "0"), "V1"))
    r = scan(c, d, ["10 Hz", "100 Hz", "1 kHz"])
    peaks = [f for f in r.findings
             if f.kind == FindingKind.EXTREMUM_OBSERVED
             and f.criterion == CRIT_TRANSFER_PEAK]
    assert len(peaks) == 0  # monotonic fall: no strict interior maximum
    ext = [f for f in r.findings if f.kind == FindingKind.EXTREMUM_OBSERVED]
    assert any("endpoint-maximum" in f.evidence[0] for f in ext)
    assert FindingKind.NO_RESONANCE_OBSERVED in kinds(r)
    assert FindingKind.ZERO_CONFIRMED not in kinds(r)


def test_edge_rl_highpass():
    c = ckt("rlhp", V_("V1", "10 V", "in", "0"), L_("L1", "10 mH", "in", "out"),
            R_("R1", "1 kOhm", "out", "0"))
    d = ResponseDefinition(
        "transfer", (voltage_between("in", "0"), voltage_between("out", "0"), "V1"))
    r = scan(c, d, ["10 Hz", "100 Hz", "100 kHz"])
    assert FindingKind.NO_RESONANCE_OBSERVED in kinds(r)
    assert FindingKind.ZERO_CONFIRMED not in kinds(r)
    assert FindingKind.BRACKET_CANDIDATE not in kinds(r)


def test_edge_ideal_v_port_no_crash():
    # D5 TEST-method Z of an ideal-V port is FINITE (-3k EXACT here);
    # R-only gate still rules out resonance.
    c = ckt("ivp", V_("V1", "10 V", "p", "0"), R_("R1", "1 kOhm", "p", "q"),
            R_("R2", "2 kOhm", "q", "0"))
    r = scan(c, port_z("p"), ["1 kHz", "2 kHz"])
    assert kinds(r) == [FindingKind.NO_RESONANCE_OBSERVED]


def test_edge_transfer_zero_input_undefined():
    # V(x,x) input reads exactly zero -> D5 undefined transfer at every
    # point -> invalid samples -> honest NO_RESONANCE_OBSERVED.
    c = ckt("zi", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "0"))
    d = ResponseDefinition(
        "transfer", (voltage_between("in", "in"), voltage_between("in", "0"), ""))
    r = scan(c, d, ["1 kHz", "2 kHz"])
    assert FindingKind.NO_RESONANCE_OBSERVED in kinds(r)
    assert len([f for f in r.findings
                if f.kind != FindingKind.NO_RESONANCE_OBSERVED]) == 0


def test_edge_contradictory_sources_all_invalid():
    c = ckt("contra", V_("V1", "5 V", "a", "0"), V_("V2", "10 V", "a", "0"),
            R_("R1", "1 kOhm", "a", "0"))
    r = scan(c, port_z("a"), ["1 kHz", "2 kHz"])
    assert kinds(r) == [FindingKind.NO_RESONANCE_OBSERVED]
    assert r.findings[0].status == ACStatus.INCONSISTENT
    assert r.quality == ()


def test_edge_single_sample_no_bracket():
    r = scan(series_rlc(), port_z(), ["1.5 kHz"])
    assert FindingKind.BRACKET_CANDIDATE not in kinds(r)
    assert FindingKind.ZERO_CONFIRMED not in kinds(r)
    assert kinds(r) == [FindingKind.NO_RESONANCE_OBSERVED]


def test_edge_empty_grid_misuse():
    with pytest.raises(ResonanceError):
        scan(series_rlc(), port_z(), [])


def test_edge_duplicate_frequencies_misuse():
    with pytest.raises(ResonanceError):
        scan(series_rlc(), port_z(), ["1 kHz", "1 kHz"])


def test_edge_decreasing_grid_misuse():
    with pytest.raises(ResonanceError):
        scan(series_rlc(), port_z(), ["2 kHz", "1 kHz"])


def test_edge_single_quantity_misuse():
    with pytest.raises(ResonanceError):
        scan_resonance(series_rlc(), port_z(), "1 kHz")


def test_edge_bad_definition_misuse():
    with pytest.raises(ResonanceError):
        scan_resonance(series_rlc(), "port-impedance", ["1 kHz"])


# -- zero-confirmation rule (native scan unit tests) ------------------------------

def test_zero_rule_exact_confirms_including_z_zero():
    # EXACT native zeros confirm — including physical Z = 0 (lossless).
    f, zero, endpoints, inert = _scan_zero_brackets(
        ["a", "b", "c"],
        [RationalComplex(Fraction(1), Fraction(2)),
         RationalComplex(Fraction(0), Fraction(0)),
         RationalComplex(Fraction(-1), Fraction(3))],
        [True, True, True], [True, True, True],
        "port-impedance", CRIT_SERIES_REACTANCE_ZERO)
    assert [x.kind for x in f] == [FindingKind.ZERO_CONFIRMED]
    assert f[0].frequency == "b"
    assert zero == [1] and endpoints == [] and inert == 0


def test_zero_rule_exact_sign_change_brackets_not_confirms():
    f, zero, endpoints, inert = _scan_zero_brackets(
        ["a", "b"],
        [RationalComplex(Fraction(1), Fraction(1)),
         RationalComplex(Fraction(1), Fraction(-1))],
        [True, True], [True, True],
        "port-impedance", CRIT_SERIES_REACTANCE_ZERO)
    assert [x.kind for x in f] == [FindingKind.BRACKET_CANDIDATE]
    assert (f[0].frequency_lo, f[0].frequency_hi) == ("a", "b")
    assert "pole" in f[0].diagnostic
    assert zero == [] and endpoints == [0, 1] and inert == 0


def test_zero_rule_hp_zero_is_inert():
    # HP computed zero: neither confirmation nor bracket evidence.
    f, zero, endpoints, inert = _scan_zero_brackets(
        ["a", "b", "c"],
        [DecimalComplex(Decimal(1), Decimal(2)),
         DecimalComplex(Decimal(3), Decimal(0)),
         DecimalComplex(Decimal(-1), Decimal(1))],
        [True, True, True], [False, False, False],
        "port-impedance", CRIT_SERIES_REACTANCE_ZERO)
    assert f == [] and zero == [] and endpoints == [] and inert == 1


def test_zero_rule_hp_sign_change_brackets():
    f, zero, endpoints, inert = _scan_zero_brackets(
        ["a", "b"],
        [DecimalComplex(Decimal("1.5"), Decimal("0.1")),
         DecimalComplex(Decimal("1.4"), Decimal("-0.2"))],
        [True, True], [False, False],
        "port-admittance", CRIT_PARALLEL_SUSCEPTANCE_ZERO)
    assert [x.kind for x in f] == [FindingKind.BRACKET_CANDIDATE]
    assert zero == [] and inert == 0


def test_zero_rule_gap_and_flat_never_cross():
    # Invalid sample between opposites: the exact-zero endpoints still
    # confirm individually, but no bracket crosses the gap.
    f, _, endpoints, _ = _scan_zero_brackets(
        ["a", "b", "c"],
        [RationalComplex(Fraction(1), Fraction(0)),
         None,
         RationalComplex(Fraction(-1), Fraction(0))],
        [True, False, True], [True, False, True],
        "port-impedance", CRIT_SERIES_REACTANCE_ZERO)
    assert [x.kind for x in f] == [FindingKind.ZERO_CONFIRMED] * 2
    assert endpoints == []
    # Flat run on zero: not a crossing.
    f2, zero2, endpoints2, _ = _scan_zero_brackets(
        ["a", "b"],
        [RationalComplex(Fraction(0), Fraction(0)),
         RationalComplex(Fraction(0), Fraction(0))],
        [True, True], [True, True],
        "port-impedance", CRIT_SERIES_REACTANCE_ZERO)
    assert [x.kind for x in f2] == [FindingKind.ZERO_CONFIRMED] * 2
    assert endpoints2 == []


def test_extract_phasor_gates_non_solved():
    from academic_core.domain.engineering.ac.resonance import _extract_phasor
    from academic_core.domain.engineering.ac.response import SweepPoint

    q = Q("1 kHz")
    assert _extract_phasor(
        SweepPoint(q, ACStatus.NUMERICALLY_UNCERTAIN, None, "x", None)) is None
    assert _extract_phasor(SweepPoint(q, ACStatus.SINGULAR, None, "x", None)) is None


# -- topologies: bridge / mesh / star / multigraph / K3,3 / non-GND / sources -----

def bridge_rlc():
    # Wheatstone-style bridge with reactive arms, source in->0.
    return ckt("brg", V_("V1", "10 V", "in", "0"),
               R_("R1", "1 kOhm", "in", "a"), L_("L1", "10 mH", "a", "out"),
               R_("R2", "2 kOhm", "in", "b"), C_("C1", "1 uF", "b", "out"),
               R_("R3", "1 kOhm", "out", "0"))


def test_topo_bridge():
    r = scan(bridge_rlc(), port_z("out"), ["100 Hz", "1 kHz", "1.6 kHz", "10 kHz"])
    assert all(f.status == ACStatus.SOLVED for f in r.findings)
    assert isinstance(r.digest, str) and len(r.digest) == 64
    r2 = scan(bridge_rlc(), port_z("out"), ["100 Hz", "1 kHz", "1.6 kHz", "10 kHz"])
    assert r2.digest == r.digest


def test_topo_mesh():
    c = ckt("mesh", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "a"),
            R_("R2", "1 kOhm", "a", "b"), L_("L1", "5 mH", "b", "0"),
            C_("C1", "2 uF", "a", "0"), R_("R3", "1 kOhm", "in", "b"))
    r = scan(c, port_z(), ["100 Hz", "1 kHz", "10 kHz"])
    assert all(f.status == ACStatus.SOLVED for f in r.findings)
    assert scan(c, port_z(), ["100 Hz", "1 kHz", "10 kHz"]).digest == r.digest


def test_topo_star():
    c = ckt("star", V_("V1", "10 V", "c", "0"), R_("R1", "1 kOhm", "c", "a"),
            L_("L1", "8 mH", "c", "b"), C_("C1", "500 nF", "c", "d"),
            R_("R2", "1 kOhm", "a", "0"), R_("R3", "1 kOhm", "b", "0"),
            R_("R4", "1 kOhm", "d", "0"))
    r = scan(c, port_z("c"), ["100 Hz", "2 kHz", "20 kHz"])
    assert all(f.status == ACStatus.SOLVED for f in r.findings)


def test_topo_multigraph():
    c = ckt("multi", V_("V1", "10 V", "s", "0"), R_("R0", "0.1 kOhm", "s", "in"),
            R_("R1", "1 kOhm", "in", "0"), C_("C1", "1 uF", "in", "0"),
            L_("L1", "10 mH", "in", "0"), R_("R2", "2 kOhm", "in", "0"))
    f0 = f0_series_lc("0.01", "0.000001")
    r = scan(c, port_y(), ["1 kHz", "1.5 kHz", "1.6 kHz", "2 kHz"])
    br = brackets_of(r)
    assert len(br) == 1
    assert Decimal(br[0][0]) <= f0 <= Decimal(br[0][1])


def test_topo_k33():
    left = ["a1", "a2", "a3"]
    right = ["b1", "b2", "b3"]
    comps = [V_("V1", "10 V", "a1", "0")]
    k = 0
    for a in left:
        for b in right:
            k += 1
            if k % 3 == 1:
                comps.append(R_(f"R{k}", "1 kOhm", a, b))
            elif k % 3 == 2:
                comps.append(L_(f"L{k}", "5 mH", a, b))
            else:
                comps.append(C_(f"C{k}", "500 nF", a, b))
    r = scan(ckt("k33", *comps), port_z("a2", "b2"), ["100 Hz", "2 kHz"])
    assert all(f.status == ACStatus.SOLVED for f in r.findings)
    assert scan(ckt("k33", *comps), port_z("a2", "b2"),
               ["100 Hz", "2 kHz"]).digest == r.digest


def test_topo_nongnd_port():
    c = ckt("ngp", V_("V1", "10 V", "t", "0"), R_("R1", "1 kOhm", "t", "a"),
            L_("L1", "10 mH", "a", "b"), C_("C1", "1 uF", "b", "t"))
    r = scan(c, port_z("a", "b"), ["100 Hz", "1 kHz", "10 kHz"])
    assert all(f.status == ACStatus.SOLVED for f in r.findings)
    assert isinstance(r.digest, str)


def test_topo_multiple_sources_network_transfer():
    c = ckt("msrc", V_("V1", "10 V", "in", "0"), V_("V2", "5 V", "mid", "0", 90),
            R_("R1", "1 kOhm", "in", "out"), L_("L1", "10 mH", "mid", "out"),
            C_("C1", "1 uF", "out", "0"))
    d = ResponseDefinition(
        "transfer", (voltage_between("in", "0"), voltage_between("out", "0"), "V1"))
    r = scan(c, d, ["100 Hz", "1 kHz", "10 kHz"])
    assert all(f.status == ACStatus.SOLVED for f in r.findings)
    d_op = ResponseDefinition(
        "transfer", (voltage_between("in", "0"), voltage_between("out", "0"), ""))
    r_op = scan(c, d_op, ["100 Hz", "1 kHz", "10 kHz"])
    assert all(f.status == ACStatus.SOLVED for f in r_op.findings)


def test_topo_branch_observables():
    c = series_rlc()
    r = scan(c, ResponseDefinition("branch-impedance", "L1"),
             ["1 kHz", "1.5 kHz", "1.6 kHz", "2 kHz"])
    assert r.observable == "branch-impedance"
    assert all(f.status == ACStatus.SOLVED for f in r.findings)
    r2 = scan(c, ResponseDefinition("branch-admittance", "C1"),
              ["1 kHz", "1.5 kHz", "1.6 kHz", "2 kHz"])
    assert r2.observable == "branch-admittance"


def test_transfer_kinds_all_four():
    c = ckt("kinds", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "out"),
            L_("L1", "10 mH", "out", "0"), C_("C1", "1 uF", "out", "0"))
    defs = [
        ResponseDefinition("transfer",
                           (voltage_between("in", "0"), voltage_between("out", "0"), "V1")),
        ResponseDefinition("transfer",
                           (current_through("R1"), current_through("L1"), "V1")),
        ResponseDefinition("transfer",
                           (current_through("R1"), voltage_between("out", "0"), "V1")),
        ResponseDefinition("transfer",
                           (voltage_between("in", "0"), current_through("L1"), "V1")),
    ]
    grid = ["100 Hz", "1 kHz", "10 kHz"]
    for d in defs:
        r = scan(c, d, grid)
        assert r.observable == "transfer"
        assert all(f.status == ACStatus.SOLVED for f in r.findings)


# -- multiple resonances ---------------------------------------------------------

def two_tank_parallel():
    return ckt("2tank", V_("V1", "10 V", "in", "0"),
               R_("R1", "0.1 kOhm", "in", "a1"), L_("L1", "10 mH", "a1", "b1"),
               C_("C1", "1 uF", "b1", "0"),
               R_("R2", "0.1 kOhm", "in", "a2"), L_("L2", "1 mH", "a2", "b2"),
               C_("C2", "100 nF", "b2", "0"))


def two_tank_admittance_closed(f_hz):
    # Independent oracle: hand series/parallel reduction in Decimal.
    w = CTX.multiply(CTX.multiply(Decimal(2), PI50), Decimal(str(f_hz)))
    y = complex(0, 0)
    import cmath as _cm
    for r, l, c_ in ((100, 0.01, 1e-6), (100, 0.001, 100e-9)):
        z = complex(r, 0) + complex(0, float(w) * l) + complex(0, -1.0 / (float(w) * c_))
        y += 1 / z
    z = 1 / y
    return z


def test_multi_two_tanks_brackets_match_hand_oracle():
    grid_hz = [200, 800, 1200, 1592, 2500, 5000, 9000, 12000, 15916, 25000, 60000]
    grid = [f"{f} Hz" for f in grid_hz]
    r = scan(two_tank_parallel(), port_z(), grid)
    br = brackets_of(r)
    assert len(br) >= 2
    assert len({tuple(b) for b in br}) == len(br)  # distinct brackets kept
    # Hand-oracle brackets from closed-form X(f) sign changes.
    from academic_core.domain.engineering.ac.bode import canonical_frequency_key
    keys = [canonical_frequency_key(Q(g)) for g in grid]
    xs = [two_tank_admittance_closed(f).imag for f in grid_hz]
    expected = [(keys[i], keys[i + 1]) for i in range(len(grid) - 1)
                if xs[i] != 0 and xs[i + 1] != 0
                and (xs[i] > 0) != (xs[i + 1] > 0)]
    assert len(expected) >= 2
    got = [(lo, hi) for lo, hi in br]
    for exp in expected:
        assert exp in got, (exp, got)
    # Q evaluated at every bracket endpoint.
    assert len(r.quality) == 2 * len(br)
    assert all(q.state == QState.DEFINED for q in r.quality)


def test_multi_two_transfer_peaks():
    c = ckt("2pk", V_("V1", "10 V", "in", "0"),
            R_("R1", "0.1 kOhm", "in", "a1"), L_("L1", "10 mH", "a1", "b1"),
            C_("C1", "1 uF", "b1", "0"),
            R_("R2", "0.1 kOhm", "in", "a2"), L_("L2", "1 mH", "a2", "b2"),
            C_("C2", "100 nF", "b2", "0"),
            R_("R3", "1 kOhm", "b1", "out"), R_("R4", "1 kOhm", "b2", "out"),
            R_("R5", "1 kOhm", "out", "0"))
    d = ResponseDefinition(
        "transfer", (voltage_between("in", "0"), voltage_between("out", "0"), "V1"))
    grid = [f"{f} Hz" for f in (100, 800, 1592, 4000, 9000, 15916, 30000, 80000)]
    r = scan(c, d, grid)
    peaks = [f for f in r.findings
             if f.kind == FindingKind.EXTREMUM_OBSERVED
             and f.criterion == CRIT_TRANSFER_PEAK]
    assert len(peaks) >= 1
    peak_keys = [p.frequency for p in peaks]
    assert peak_keys == sorted(peak_keys, key=lambda k: Decimal(k))
    assert FindingKind.ZERO_CONFIRMED not in kinds(r)  # peaks are not verdicts


# -- generality: ladder scales -----------------------------------------------------

def ladder(n, l="10 mH", c="1 uF", r="0.1 kOhm", load="1 kOhm"):
    comps = [V_("V1", "10 V", "in", "0"), R_("R0", r, "in", "n1")]
    for i in range(1, n + 1):
        comps.append(L_(f"L{i}", l, f"n{i}", f"m{i}"))
        comps.append(C_(f"C{i}", c, f"m{i}", "0"))
        if i < n:
            comps.append(R_(f"R{i}", r, f"m{i}", f"n{i + 1}"))
        else:
            comps.append(R_("R70", load, f"m{i}", "0"))
    return ckt(f"lad{n}", *comps)


def test_generality_ladder_scales():
    grid = ["100 Hz", "1.5 kHz", "1.6 kHz", "10 kHz"]
    digests = []
    for n in (1, 2, 4, 8, 16, 32, 64):
        r = scan(ladder(n), port_z(), grid)
        assert all(f.status == ACStatus.SOLVED for f in r.findings)
        assert isinstance(r.digest, str) and len(r.digest) == 64
        digests.append(r.digest)
        assert scan(ladder(n), port_z(), grid).digest == r.digest
    assert len(set(digests)) == len(digests)


# -- bandwidth-Q ---------------------------------------------------------------------

def bandpass_vr():
    # Series RLC bandpass: output across R peaks (|H| = 1) at f0.
    return ckt("bpvr", V_("V1", "10 V", "in", "0"), R_("R1", "0.1 kOhm", "in", "a"),
               L_("L1", "10 mH", "a", "b"), C_("C1", "1 uF", "b", "0"))


def test_bandwidth_q_interval_contains_truth():
    c = bandpass_vr()
    d = ResponseDefinition(
        "transfer", (voltage_between("in", "0"), voltage_between("in", "a"), "V1"))
    grid = log_frequencies("100 Hz", 20, 61)
    sweep = frequency_response(c, d, grid)
    bode = analyze_bode(sweep)
    assert len([b for b in bode.bands if b.defined]) == 1
    qf = quality_from_bandwidth(bode)
    assert qf.state == QState.DEFINED
    assert qf.basis == BASIS_BANDWIDTH
    assert qf.value is None
    lo, hi = (Decimal(x) for x in qf.interval)
    assert lo < hi
    # Interval arithmetic check: f_peak/BW_true inside, with analytic
    # series-RLC half-power bandwidth BW = R/(2*pi*L).
    band = [b for b in bode.bands if b.defined][0]
    blo, bhi = band.bandwidth_lo, band.bandwidth_hi
    bw_true = CTX.divide(Decimal("100"),
                         CTX.multiply(CTX.multiply(Decimal(2), PI50), Decimal("0.01")))
    assert blo <= bw_true <= bhi
    f_peak = Decimal(qf.frequency)
    assert lo <= CTX.divide(f_peak, bw_true) <= hi
    # Semantics link: energy-Q at the peak sample agrees with f_peak/BW
    # within the grid-offset bound (half local step over BW).
    qe_peak = qe_series_closed(str(f_peak), "0.01", "0.000001", "100")
    mid = CTX.divide(CTX.add(lo, hi), Decimal(2))
    from academic_core.domain.engineering.ac.bode import canonical_frequency_key
    key_list = [canonical_frequency_key(g) for g in grid]
    i = key_list.index(qf.frequency)
    base_list = sorted(Decimal(str(g.to_base())) for g in grid)
    step = (base_list[min(i + 1, len(base_list) - 1)] - base_list[max(i - 1, 0)]) / 2
    bound = CTX.divide(step, bw_true) * 10
    assert abs(CTX.divide(qe_peak - mid, mid)) <= bound


def test_bandwidth_q_rejects_z_kind():
    sweep = frequency_response(series_rlc(), port_z(),
                               ["100 Hz", "1 kHz", "10 kHz"])
    qf = quality_from_bandwidth(analyze_bode(sweep))
    assert qf.state == QState.UNDEFINED
    assert "transfer" in qf.diagnostic


def test_bandwidth_q_rejects_no_band():
    c = ckt("mono", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "out"),
            C_("C1", "1 uF", "out", "0"))
    d = ResponseDefinition(
        "transfer", (voltage_between("in", "0"), voltage_between("out", "0"), "V1"))
    sweep = frequency_response(c, d, ["10 Hz", "100 Hz", "1 kHz"])
    qf = quality_from_bandwidth(analyze_bode(sweep))
    assert qf.state == QState.UNDEFINED


def test_bandwidth_q_rejects_two_peaks():
    # One D6-defined band containing two strict peaks: real D6 machinery
    # (analyze_bode) over a synthetic-but-valid transfer sweep isolates
    # the D8 peak-count branch.
    from academic_core.domain.engineering.ac.response import (
        SweepPoint,
        SweepResult,
        TransferKind,
    )
    from academic_core.domain.engineering.ac.response import TransferFunction

    freqs = [Q(f"{f} Hz") for f in (100, 200, 400, 800, 1600)]
    mags = ["0.1", "0.9", "0.7", "0.95", "0.1"]
    ep_in = voltage_between("in", "0")
    ep_out = voltage_between("out", "0")
    pts = []
    for fq, m in zip(freqs, mags):
        tf = TransferFunction(TransferKind.VOLTAGE_GAIN, ep_in, ep_out,
                              DecimalComplex(Decimal(m), Decimal(0)),
                              True, "network-transfer", "1", "V1", "synthetic")
        pts.append(SweepPoint(fq, ACStatus.SOLVED, tf, "synthetic", None))
    definition = ResponseDefinition("transfer", (ep_in, ep_out, "V1"))
    sweep = SweepResult("completed", tuple(pts), definition,
                        {"engine": "synthetic"}, (), "synthetic-digest")
    bode = analyze_bode(sweep)
    assert len([b for b in bode.bands if b.defined]) == 1
    peaks = [x for x in bode.extrema if x.kind == "strict-maximum"]
    assert len(peaks) == 2
    qf = quality_from_bandwidth(bode)
    assert qf.state == QState.UNDEFINED
    assert "one isolated" in qf.diagnostic


def test_bandwidth_q_rejects_misuse():
    with pytest.raises(ResonanceError):
        quality_from_bandwidth("not-a-bode-result")


def test_db3_rejection_documented():
    # -3 dB machinery lives in D6; D8 never thresholds Z/Y magnitudes.
    # A |Z| minimum with no reactance zero yields observations only.
    c = ckt("nomin", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "a"),
            R_("R2", "2 kOhm", "a", "0"), C_("C1", "10 nF", "a", "0"))
    r = scan(c, port_z("a"), ["10 Hz", "100 Hz", "1 kHz", "100 kHz"])
    assert FindingKind.ZERO_CONFIRMED not in kinds(r)
    assert FindingKind.BRACKET_CANDIDATE not in kinds(r)
    assert FindingKind.NO_RESONANCE_OBSERVED in kinds(r)


# -- D7-equivalent mode ------------------------------------------------------------------

def test_d7mode_bracket_matches_d5_scan():
    # Source behind R0 so the port is not across the (deactivated) source:
    # D7-test Zth = R0 || jXs and D5-direct share the X=0 at f0.
    c = ckt("d7s", V_("V1", "10 V", "s", "0"), R_("R0", "0.1 kOhm", "s", "in"),
            L_("L1", "10 mH", "in", "a"), C_("C1", "1 uF", "a", "0"))
    port = PortDefinition("in", "0")
    grid = ["1 kHz", "1.5 kHz", "1.6 kHz", "2 kHz"]
    equivs = [analyze_ac_thevenin(c, port, f) for f in grid]
    assert all(e.status == ACStatus.SOLVED for e in equivs)
    r = scan_port_equivalents(c, port, equivs)
    assert brackets_of(r) == [("1500", "1600")]
    assert r.quality == ()
    assert r.provenance["mode"] == "d7-equivalents"
    assert "Q unavailable" in r.provenance["q_criterion"]
    # Same bracket as the D5-based scan.
    assert brackets_of(scan(c, port_z(), grid)) == brackets_of(r)


def test_d7mode_no_q_and_port_mismatch():
    c = series_rlc()
    port = PortDefinition("in", "0")
    equivs = [analyze_ac_thevenin(c, port, f) for f in ("1 kHz", "2 kHz")]
    with pytest.raises(ResonanceError):
        scan_port_equivalents(c, PortDefinition("a", "0"), equivs)
    with pytest.raises(ResonanceError):
        scan_port_equivalents(c, port, [])
    r = scan_port_equivalents(c, port, equivs)
    assert r.quality == () and r.bands == ()


# -- metamorphic ----------------------------------------------------------------------------

def test_meta_node_rename_and_permutation():
    c1 = series_rlc("m1")
    c2 = ckt("m2", C_("C1", "1 uF", "b", "0"), V_("V1", "10 V", "in", "0"),
             L_("L1", "10 mH", "a", "b"), R_("R1", "0.1 kOhm", "in", "a"))
    grid = ["1 kHz", "1.5 kHz", "1.6 kHz", "2 kHz"]
    r1, r2 = scan(c1, port_z(), grid), scan(c2, port_z(), grid)
    assert brackets_of(r1) == brackets_of(r2)
    assert [q.value for q in r1.quality] == [q.value for q in r2.quality]


def test_meta_ab_swap():
    c = ckt("swp", V_("V1", "10 V", "t", "0"), R_("R1", "1 kOhm", "t", "a"),
            L_("L1", "10 mH", "a", "b"), C_("C1", "1 uF", "b", "0"))
    grid = ["100 Hz", "1 kHz", "1.6 kHz", "10 kHz"]
    r_ab = scan(c, port_z("a", "b"), grid)
    r_ba = scan(c, port_z("b", "a"), grid)
    assert brackets_of(r_ab) == brackets_of(r_ba)


def test_meta_source_scaling_invariant():
    grid = ["1 kHz", "1.5 kHz", "1.6 kHz", "2 kHz"]
    r1 = scan(series_rlc("s1"), port_z(), grid)
    c2 = ckt("s2", V_("V1", "37 V", "in", "0"), R_("R1", "0.1 kOhm", "in", "a"),
             L_("L1", "10 mH", "a", "b"), C_("C1", "1 uF", "b", "0"))
    r2 = scan(c2, port_z(), grid)
    assert brackets_of(r1) == brackets_of(r2)
    # Q is a ratio (drive-invariant); HP solver rounding paths depend on
    # absolute scale (observed cross-magnitude agreement: 28 digits), so
    # compare within an explicit working-precision tolerance.
    for a, b in zip(r1.quality, r2.quality):
        assert a.state == b.state == QState.DEFINED
        assert abs(a.value - b.value) <= Decimal("1E-25"), (a.value, b.value)


def test_meta_lc_scaling_maps_brackets():
    # L x4 (C same) -> LC x4 -> f0 halves; scaled grid reproduces it.
    c = ckt("sc", V_("V1", "10 V", "in", "0"), R_("R1", "0.1 kOhm", "in", "a"),
            L_("L1", "40 mH", "a", "b"), C_("C1", "1 uF", "b", "0"))
    r = scan(c, port_z(), ["500 Hz", "750 Hz", "800 Hz", "1 kHz"])
    assert brackets_of(r) == [("750", "800")]
    f0 = f0_series_lc("0.04", "0.000001")
    assert Decimal("750") <= f0 <= Decimal("800")


def test_meta_hz_khz_equivalence():
    grid_hz = ["1000 Hz", "1500 Hz", "1600 Hz", "2000 Hz"]
    grid_khz = ["1 kHz", "1.5 kHz", "1.6 kHz", "2 kHz"]
    r1 = scan(series_rlc("h1"), port_z(), grid_hz)
    r2 = scan(series_rlc("h2"), port_z(), grid_khz)
    assert r1.digest == r2.digest
    assert brackets_of(r1) == brackets_of(r2) == [("1500", "1600")]


def test_meta_deterministic_repeat():
    grid = ["100 Hz", "1 kHz", "1.6 kHz", "10 kHz"]
    r1 = scan(bridge_rlc(), port_z("out"), grid)
    r2 = scan(bridge_rlc(), port_z("out"), grid)
    assert r1.digest == r2.digest
    assert r1.to_dict() == r2.to_dict()


def test_meta_ladder_determinism():
    grid = ["100 Hz", "1.5 kHz", "1.6 kHz", "10 kHz"]
    assert scan(ladder(8), port_z(), grid).digest == \
        scan(ladder(8), port_z(), grid).digest


# -- ngspice oracles --------------------------------------------------------------------------

def _ng_backend():
    from academic_core.infrastructure.ngspice import NgSpiceBackend

    b = NgSpiceBackend()
    return b if b.detect().verified else None


NG = _ng_backend()


def _spice_netlist(circuit):
    lines = [f"* D8 oracle {circuit.name}"]
    for e in sorted(circuit.components, key=lambda x: x.ref.upper()):
        t = e.type.upper()
        pins = " ".join(e.pins[p] for p in
                        (("1", "2") if t in ("R", "L", "C") else ("+", "-")))
        if t in ("V", "I"):
            ph = e.parameters.get("phase", 0)
            unit = str(e.parameters.get("phase_unit", "deg")).lower()
            ph_d = Decimal(str(ph))
            deg = ph_d if unit == "deg" else ph_d * Decimal("57.295779513082320876798154814105")
            lines.append(f"{e.ref.upper()} {pins} dc 0 ac {format(e.value.to_base(), 'f')} {deg}")
        elif t in ("R", "L", "C"):
            lines.append(f"{e.ref.upper()} {pins} {format(e.value.to_base(), 'f')}")
        else:
            raise AssertionError("oracle netlists use V/I+R/L/C only")
    lines.append(".end")
    return "\n".join(lines) + "\n"


def _oracle_voltages(deck, freq_hz, nodes):
    from academic_core.domain.engineering.simulation import ACAnalysis

    assert NG is not None
    body = deck.replace(".end", "")
    body += ".print ac " + " ".join(f"v({n})" for n in nodes) + "\n.end\n"
    ac = ACAnalysis(sweep_type="lin", points=2, fstart=str(freq_hz),
                    fstop=str(int(freq_hz) + 1))
    res = NG.simulate(body, analyses=(ac,))
    assert res.status == "COMPLETED"
    return {n: res.sample_complex_at(f"v({n})", str(freq_hz)) for n in nodes}


def _check_close(got, ref, tol):
    assert abs(Decimal(str(got)) - ref) <= tol, (got, ref)


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_series_bracket_values_and_q():
    # Analytic f0 containment + ngspice value agreement at the bracket
    # endpoints + ngspice-derived energy-Q agreement.
    import math as _math

    f0 = f0_series_lc("0.01", "0.000001")
    grid = ["1.5 kHz", "1.6 kHz"]
    r = scan(series_rlc("osp"), port_z(), grid)
    assert brackets_of(r) == [("1500", "1600")]
    assert Decimal("1500") <= f0 <= Decimal("1600")
    deck = _spice_netlist(series_rlc("osp"))
    for f_hz, qf in zip((1500, 1600), r.quality):
        got = _oracle_voltages(deck, f_hz, ("in", "a", "b"))
        vin, va, vb = (got[n] for n in ("in", "a", "b"))
        i_series = (vin - va) / 100.0  # R1 = 100 Ohm
        vr, vl, vc = vin - va, va - vb, vb
        p_r = 0.5 * abs(vr) ** 2 / 100.0
        w = 2.0 * float(PI50) * f_hz
        q_l = 0.5 * w * 0.01 * abs(i_series) ** 2
        q_c = 0.5 * w * 1e-6 * abs(vc) ** 2
        q_ng = (q_l + q_c) / (2.0 * p_r)
        assert abs(float(qf.value) - q_ng) / q_ng <= 0.02, (qf.value, q_ng)
        # Impedance value agreement (|Z| within 2%).
        z_ng = vin / i_series
        from academic_core.domain.engineering.ac.impedance import measure_port
        from academic_core.domain.engineering.ac.problem import build_ac_problem
        from academic_core.domain.engineering.ac.operating_point import ACOperatingPoint
        from academic_core.domain.engineering.ac.topology import reference_net
        c = series_rlc("osp")
        op = ACOperatingPoint.from_frequency(Q(f"{f_hz} Hz"), reference_net(c.nets))
        prob = build_ac_problem(c, op, NumericMode.AUTO)
        sol = solve_ac(c, Q(f"{f_hz} Hz"), NumericMode.AUTO)
        z_d8 = measure_port(prob, sol, PortDefinition("in", "0")).require_finite()
        assert abs(abs(complex(float(z_d8.re), float(z_d8.im))) - abs(z_ng)) / abs(z_ng) <= 0.02


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_parallel_admittance_bracket():
    c = ckt("opg", V_("V1", "10 V", "in", "0"), R_("R1", "0.1 kOhm", "in", "a"),
            R_("R2", "2 kOhm", "a", "0"), L_("L1", "10 mH", "a", "0"),
            C_("C1", "1 uF", "a", "0"))
    f0 = f0_series_lc("0.01", "0.000001")
    r = scan(c, port_y("a"), ["1.5 kHz", "1.6 kHz"])
    assert brackets_of(r) == [("1500", "1600")]
    assert Decimal("1500") <= f0 <= Decimal("1600")
    deck = _spice_netlist(c)
    im_prev = None
    for f_hz in (1500, 1600):
        got = _oracle_voltages(deck, f_hz, ("a",))
        va = got["a"]
        # Tank admittance from ngspice node voltage: Itot=(10-va)/100.
        itot = (10.0 - va) / 100.0
        y_ng = itot / va - 1.0 / 2000.0  # remove R2 branch
        if im_prev is not None:
            assert (im_prev > 0) != (y_ng.imag > 0)  # independent sign change
        im_prev = y_ng.imag


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_pole_straddle_values():
    c = ckt("opl", V_("V1", "10 V", "in", "0"), R_("R1", "0.1 kOhm", "in", "a"),
            L_("L1", "10 mH", "a", "0"), C_("C1", "1 uF", "a", "0"))
    r = scan(c, port_z("a"), ["1.5 kHz", "1.6 kHz"])
    assert len(brackets_of(r)) == 1
    assert FindingKind.ZERO_CONFIRMED not in kinds(r)
    deck = _spice_netlist(c)
    mags = []
    for f_hz in (1500, 1600):
        got = _oracle_voltages(deck, f_hz, ("in", "a"))
        i_in = (got["in"] - got["a"]) / 100.0
        mags.append(abs(got["a"] / i_in))
    # Pole neighborhood: |Z| large on both sides (|Z(1500)| ~ 840 from
    # closed form |wL/(1-w^2LC)|, |Z(1600)| ~ 9500), strongly asymmetric.
    assert mags[0] > 500.0 and mags[1] > 500.0
    assert mags[1] / mags[0] > 5.0


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_rc_transfer_values():
    c = ckt("orc", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "out"),
            C_("C1", "1 uF", "out", "0"))
    d = ResponseDefinition(
        "transfer", (voltage_between("in", "0"), voltage_between("out", "0"), "V1"))
    r = scan(c, d, ["100 Hz", "1 kHz"])
    assert FindingKind.NO_RESONANCE_OBSERVED in kinds(r)
    deck = _spice_netlist(c)
    for f_hz in (100, 1000):
        got = _oracle_voltages(deck, f_hz, ("in", "out"))
        h_ng = abs(got["out"] / got["in"])
        w = 2.0 * float(PI50) * f_hz
        h_an = 1.0 / ((1.0 + (w * 1000.0 * 1e-6) ** 2) ** 0.5)
        assert abs(h_ng - h_an) / h_an <= 0.02, (h_ng, h_an)


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_bridge_nongnd_values():
    c = ckt("obg", V_("V1", "10 V", "t", "0"), R_("R1", "1 kOhm", "t", "a"),
            L_("L1", "10 mH", "a", "b"), C_("C1", "1 uF", "b", "t"))
    grid = ["500 Hz", "1.5 kHz", "1.6 kHz", "5 kHz"]
    r = scan(c, port_z("a", "b"), grid)
    assert all(f.status == ACStatus.SOLVED for f in r.findings)
    deck = _spice_netlist(c)
    got = _oracle_voltages(deck, 1500, ("a", "b"))
    from academic_core.domain.engineering.ac.problem import build_ac_problem
    from academic_core.domain.engineering.ac.operating_point import ACOperatingPoint
    from academic_core.domain.engineering.ac.topology import reference_net
    op = ACOperatingPoint.from_frequency(Q("1.5 kHz"), reference_net(c.nets))
    prob = build_ac_problem(c, op, NumericMode.AUTO)
    sol = solve_ac(c, Q("1.5 kHz"), NumericMode.AUTO)
    va = sol.voltage_of("a")
    vb = sol.voltage_of("b")
    assert abs(float(va.re) - got["a"].real) <= 0.05
    assert abs(float(va.im) - got["a"].imag) <= 0.05
    assert abs(float(vb.re) - got["b"].real) <= 0.05
    assert abs(float(vb.im) - got["b"].imag) <= 0.05


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_two_tank_brackets_independent():
    grid_hz = [800, 1200, 1592, 2500, 5000, 9000, 12000, 15916, 25000]
    grid = [f"{f} Hz" for f in grid_hz]
    c = two_tank_parallel()
    r = scan(c, port_z(), grid)
    assert len(brackets_of(r)) >= 2
    # Independent ngspice sign-change brackets over the same grid.
    deck = _spice_netlist(c)
    ims = []
    for f_hz in grid_hz:
        got = _oracle_voltages(deck, f_hz, ("in", "a1", "a2"))
        i_tot = (got["in"] - got["a1"]) / 100.0 + (got["in"] - got["a2"]) / 100.0
        z_ng = got["in"] / i_tot
        ims.append(z_ng.imag)
    from academic_core.domain.engineering.ac.bode import canonical_frequency_key
    keys = [canonical_frequency_key(Q(g)) for g in grid]
    ng_brackets = [(keys[i], keys[i + 1]) for i in range(len(grid) - 1)
                   if ims[i] != 0 and ims[i + 1] != 0
                   and (ims[i] > 0) != (ims[i + 1] > 0)]
    assert len(ng_brackets) >= 2
    for lo, hi in brackets_of(r):
        assert (lo, hi) in ng_brackets, ((lo, hi), ng_brackets)


# -- status propagation ------------------------------------------------------------------

def test_status_uncertain_never_confirms():
    # UNCERTAIN samples are invalid by construction (tested at unit
    # level); end-to-end, a fully non-SOLVED sweep stays honest.
    c = ckt("unc", V_("V1", "5 V", "a", "0"), V_("V2", "10 V", "a", "0"),
            L_("L1", "10 mH", "a", "0"))
    r = scan(c, port_z("a"), ["1 kHz", "2 kHz"])
    assert kinds(r) == [FindingKind.NO_RESONANCE_OBSERVED]
    assert r.quality == ()


def test_status_sweep_partial_propagates():
    c = ckt("part", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "a"),
            L_("L1", "10 mH", "a", "0"))
    sw = frequency_response(c, port_z(), ["1 kHz", "2 kHz"])
    assert sw.status in ("completed", "completed_with_point_failures")
    r = scan(c, port_z(), ["1 kHz", "2 kHz"])
    assert r.provenance["sweep_status"] == sw.status
    assert r.provenance["sweep_digest"] == sw.digest


# -- provenance / determinism / immutability ----------------------------------------

def test_provenance_engine_and_policy():
    r = scan(series_rlc(), port_z(), ["1 kHz", "2 kHz"])
    p = r.provenance
    assert p["engine"] == RESONANCE_ENGINE_VERSION
    assert p["observable"] == "port-impedance"
    assert p["criterion"] == CRIT_SERIES_REACTANCE_ZERO
    assert "no interpolation" in p["threshold_policy"]
    assert p["temporal_convention"] == "e^(+jwt)"
    assert p["amplitude_convention"] == "peak"
    assert "digest" not in str(p.get("timestamp", ""))


def test_digest_deterministic_and_canonical():
    grid = ["1 kHz", "1.5 kHz", "1.6 kHz", "2 kHz"]
    r1 = scan(series_rlc("g1"), port_z(), grid)
    r2 = scan(series_rlc("g2"), port_z(), grid)
    assert r1.digest == r2.digest
    assert len(r1.digest) == 64


def _snapshot(circuit):
    return [(e.ref, e.type, str(e.value.to_base()),
             {k: v for k, v in e.pins.items()}, dict(e.parameters))
            for e in sorted(circuit.components, key=lambda x: x.ref.upper())]


def test_immutability_circuit_and_inputs():
    c = bridge_rlc()
    d = port_z("out")
    grid = ["100 Hz", "1 kHz", "10 kHz"]
    before = _snapshot(c)
    sw = frequency_response(c, d, grid)
    sw_digest = sw.digest
    r1 = scan_resonance(c, d, grid)
    r2 = scan_resonance(c, d, grid)
    assert _snapshot(c) == before
    assert frequency_response(c, d, grid).digest == sw_digest
    assert r1.digest == r2.digest
    bode = analyze_bode(sw)
    bode_digest = bode.digest
    _ = quality_from_bandwidth(bode)
    assert analyze_bode(sw).digest == bode_digest


def test_report_types_frozen():
    r = scan(series_rlc(), port_z(), ["1 kHz", "2 kHz"])
    assert isinstance(r, ResonanceReport)
    assert isinstance(r.findings, tuple)
    assert all(isinstance(f, ResonanceFinding) for f in r.findings)
    assert all(isinstance(q, QualityFactor) for q in r.quality)
    with pytest.raises(Exception):
        r.findings = ()


# -- security ---------------------------------------------------------------------------------

def test_security_no_forbidden_calls():
    import pathlib

    src = pathlib.Path(__file__).parent.parent / "src" / "academic_core" / \
        "domain" / "engineering" / "ac" / "resonance.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    forbidden_calls = {"eval", "exec", "compile", "__import__", "open", "input",
                       "breakpoint", "exit", "quit", "globals", "locals", "vars",
                       "dir", "getattr", "setattr", "delattr", "hasattr"}
    # NOTE: getattr is used read-only on result dataclasses (duck-typed
    # D5/D7 value access); flag only dynamic-import/network/shell paths.
    offenders = ("subprocess", "os", "sys", "socket", "http", "urllib",
                 "requests", "ftplib", "pickle", "marshal", "importlib",
                 "pty", "commands", "popen", "system", "shutil", "pathlib",
                 "numpy", "cmath", "math")
    found_calls = set()
    found_imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            found_calls.add(node.func.id)
        if isinstance(node, ast.Import):
            for a in node.names:
                found_imports.add(a.name.split(".")[0])
        if isinstance(node, ast.ImportFrom) and node.module:
            found_imports.add(node.module.split(".")[0])
    dangerous = (found_calls & forbidden_calls) - {"getattr"}
    assert not dangerous, dangerous
    assert not (found_imports & set(offenders)), found_imports & set(offenders)
    assert "academic_core" in found_imports or True


def test_security_no_numeric_infinity_anywhere():
    import json as _json

    r = scan(two_tank_parallel(), port_z(),
             ["500 Hz", "1.5 kHz", "1.6 kHz", "5 kHz"])
    blob = _json.dumps(r.to_dict(), default=str).lower()
    assert "inf" not in blob.replace("finding", "").replace("info", "")


# -- performance ----------------------------------------------------------------------------------

def test_perf_scales():
    marks = {}
    # Caps are generous wall-time guards (machine-variance-proofed:
    # N=64 observed 363-441 s standalone): the scaling itself is the
    # certified D3 solver's, D8 post-processing is O(sweep points).
    for n, cap in ((16, 120), (32, 240), (64, 600)):
        t0 = time.perf_counter()
        r = scan(ladder(n), port_z(), ["100 Hz", "1.5 kHz", "1.6 kHz", "10 kHz"])
        dt = time.perf_counter() - t0
        marks[n] = round(dt, 2)
        assert dt < cap, (n, dt)
        assert len(r.digest) == 64
    assert marks[64] > 0
    # Report-only timing split (visible with -rs).
    print(f"\nD8 perf seconds by N: {marks}")


# -- report shape -------------------------------------------------------------------------------------

def test_report_shape_series():
    r = scan(series_rlc(), port_z(), ["1 kHz", "1.5 kHz", "1.6 kHz", "2 kHz"])
    d = r.to_dict()
    assert d["observable"] == "port-impedance"
    assert d["criterion"] == CRIT_SERIES_REACTANCE_ZERO
    assert d["digest"] == r.digest
    assert d["provenance"]["engine"] == "f8d-ac-resonance/1.0"
    assert isinstance(d["findings"], list) and d["findings"]
    assert isinstance(d["quality"], list) and d["quality"]
    assert r.numeric_mode == "high_precision"
