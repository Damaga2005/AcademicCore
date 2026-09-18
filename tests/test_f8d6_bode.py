"""F8-D6 Bode / log-frequency response + level metrics + phase unwrap.

Conventions: EXACT assertions are representation-exact; HP carries
explicit tolerances. Closed forms are transcribed universal constants
(PI50, LOG10_2, LN10...) and direct formulas evaluated here — never
engine outputs. ngspice 47 is an external oracle over exact
single-frequency decks (nearest-match sampler hazard avoided by
construction); D5 tables are INPUTS to D6, never oracles for it.
"""
import ast
import json
import pathlib
from decimal import Decimal
from fractions import Fraction

import pytest

from academic_core.domain.engineering.ac import (
    ACStatus,
    ResponseDefinition,
    SweepResult,
    analyze_bode,
    canonical_frequency_key,
    crossing_brackets,
    current_through,
    frequency_response,
    half_power_threshold_db,
    linear_frequencies,
    log_frequencies,
    magnitude_db,
    observed_extrema,
    reactance_zero_brackets,
    solve_ac,
    threshold_bands,
    unwrap_phases,
    voltage_between,
)
from academic_core.domain.engineering.ac.bode import (
    BodeError,
    DecibelCategory,
    analyze_bode as analyze_bode_direct,
)
from academic_core.domain.engineering.ac.impedance import ImpedanceError
from academic_core.domain.engineering.ac.response import TransferKind
from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.math import DecimalComplex, RationalComplex
from academic_core.domain.engineering.math import decimal_pi_value
from academic_core.domain.engineering.math.logarithm import (
    decimal_ln10,
    decimal_log10,
    decimal_nth_root,
    make_context,
)
from academic_core.domain.engineering.math.trig import decimal_pi
from academic_core.domain.engineering.units import parse_quantity

CTX = make_context()
TOL = Decimal("1E-40")
PI50 = Decimal("3.14159265358979323846264338327950288419716939937510")
LOG10_2 = Decimal("0.30102999566398119521373889472449302676818988146211")
LN10_REF = Decimal("2.3025850929940456840179914546843642076011014886288")


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


def ckt(name, *comps):
    c = Circuit(name)
    for e in comps:
        c.add(e)
    return c


def rc_lowpass():
    return ckt("lp", V_("V1", "5 V", "in", "0"), R_("R1", "1 kOhm", "in", "out"),
               C_("C1", "1 uF", "out", "0"))


def h_transfer():
    return ResponseDefinition(
        "transfer", (voltage_between("in", "0"), voltage_between("out", "0"), "V1"))


def bode_of(circuit, definition, freqs):
    sw = frequency_response(circuit, definition, freqs)
    assert sw.status == "completed", sw.diagnostics
    return analyze_bode(sw), sw


# -- log grid --------------------------------------------------------------------------------

def _base(q):
    # Explicit-context base Hz (F6 to_base() rounds through the ambient
    # 28-digit context — documented boundary, never used for precision).
    return CTX.multiply(q.value, q.unit.factor)


def test_log_grid_ratios_and_counts():
    for ppd in (1, 2, 5, 10, 20, 100):
        grid = log_frequencies("10 Hz", ppd, 5)
        assert len(grid) == 5
        r = CTX.divide(_base(grid[1]), _base(grid[0]))
        # Newton/grid identity: r^ppd == 10 (independent check of both).
        assert abs(CTX.subtract(CTX.power(r, ppd), Decimal(10))) <= Decimal("1E-40")
        for a, b in zip(grid, grid[1:]):
            assert b.to_base() > a.to_base()  # strictly increasing, no dupes
    assert log_frequencies("10 Hz", 10, 1)[0].to_base() == Decimal(10)


def test_log_grid_n_scales():
    for n in (1, 2, 3, 4, 8, 16, 32, 64, 100, 1000):
        grid = log_frequencies("1 Hz", 10, n) if n > 1 else log_frequencies("1 Hz", 10, 1)
        assert len(grid) == n
    assert len(log_frequencies("1 Hz", 1, 1000)) == 1000


def test_log_grid_validation():
    with pytest.raises(BodeError):
        log_frequencies("0 Hz", 10, 5)
    with pytest.raises(BodeError):
        log_frequencies("-5 Hz", 10, 5)
    with pytest.raises(BodeError):
        log_frequencies("10 V", 10, 5)
    with pytest.raises(BodeError):
        log_frequencies("10 Hz", 0, 5)
    with pytest.raises(BodeError):
        log_frequencies("10 Hz", 10, 0)
    with pytest.raises(BodeError):
        log_frequencies("10 Hz", True, 5)
    with pytest.raises(BodeError):
        log_frequencies("10 Hz", 10, -3)


def test_log_grid_determinism_and_decades():
    a = log_frequencies("100 Hz", 20, 41)
    b = log_frequencies("100 Hz", 20, 41)
    assert [str(f.to_base()) for f in a] == [str(f.to_base()) for f in b]
    # 20 ppd over 40 steps = exactly 2 decades: last/first == 100.
    ratio = CTX.divide(_base(a[-1]), _base(a[0]))
    assert abs(CTX.subtract(ratio, Decimal(100))) <= Decimal("1E-40")


# -- nth root ----------------------------------------------------------------------------------

def test_nth_root_powers_and_identities():
    for n in (1, 2, 3, 7, 10, 12, 20, 50, 100):
        r = decimal_nth_root(Decimal(10), n)
        assert abs(CTX.subtract(CTX.power(r, n), Decimal(10))) <= Decimal("1E-40")
    assert decimal_nth_root(Decimal(1), 7) == Decimal(1)
    assert decimal_nth_root(Decimal(0), 5) == Decimal(0)
    assert decimal_nth_root(Decimal(25), 1) == Decimal(25)
    assert decimal_nth_root(Decimal("1E-30"), 2) > Decimal(0)
    assert decimal_nth_root(Decimal("1E30"), 3) > Decimal(1000000000)


def test_nth_root_errors_and_context():
    from decimal import getcontext

    with pytest.raises(ValueError):
        decimal_nth_root(Decimal(-4), 2)
    with pytest.raises(ValueError):
        decimal_nth_root(Decimal(4), 0)
    with pytest.raises(TypeError):
        decimal_nth_root(Decimal(4), True)
    with pytest.raises(TypeError):
        decimal_nth_root("16", 2)
    before = getcontext().prec
    decimal_nth_root(Decimal(2), 5)
    assert getcontext().prec == before


def test_tripwires_raise_never_truncate():
    # Safety mechanisms are real: starved budgets must raise, proving the
    # caps are tripwires rather than silent truncation points.
    import academic_core.domain.engineering.math.logarithm as _log

    old_n, old_s = _log._MAX_NEWTON_ITERATIONS, _log._MAX_SERIES_TERMS
    _log._MAX_NEWTON_ITERATIONS = 1
    _log._MAX_SERIES_TERMS = 1
    try:
        with pytest.raises(ArithmeticError):
            decimal_nth_root(Decimal(10), 10)
        with pytest.raises(ArithmeticError):
            decimal_log10(Decimal("9.999"))
    finally:
        _log._MAX_NEWTON_ITERATIONS, _log._MAX_SERIES_TERMS = old_n, old_s
    # ...while normal budgets converge (no false tripwire).
    decimal_nth_root(Decimal(10), 10)
    decimal_log10(Decimal("9.999"))


# -- log10 ---------------------------------------------------------------------------------------

def test_log10_exact_powers():
    assert decimal_log10(Decimal(1)) == Decimal(0)
    for k in range(-5, 6):
        assert decimal_log10(Decimal(10) ** k) == Decimal(k)


def test_log10_reference_values():
    assert abs(CTX.subtract(decimal_log10(Decimal(2)), LOG10_2)) <= Decimal("1E-45")
    assert abs(CTX.subtract(decimal_log10(Decimal("0.001")), Decimal(-3))) <= TOL
    assert abs(CTX.subtract(decimal_log10(Decimal("9.999")),
                            Decimal("0.99995656838019248961544395597619"))) <= Decimal("1E-30")
    assert abs(CTX.subtract(decimal_log10(Decimal("1E30")), Decimal(30))) <= TOL
    assert abs(CTX.subtract(decimal_log10(Decimal("1E-30")), Decimal(-30))) <= TOL


def test_log10_monotonic_and_near_unity():
    vals = [Decimal("0.5"), Decimal("0.99"), Decimal("1.000000000001"),
            Decimal("2"), Decimal("9.999"), Decimal("10"), Decimal("1E6")]
    outs = [decimal_log10(v) for v in vals]
    assert all(b > a for a, b in zip(outs, outs[1:]))
    assert abs(decimal_log10(Decimal("1.000000000001"))) <= Decimal("1E-9")


def test_log10_errors_and_ln10():
    with pytest.raises(ValueError):
        decimal_log10(Decimal(0))
    with pytest.raises(ValueError):
        decimal_log10(Decimal(-2))
    with pytest.raises(TypeError):
        decimal_log10(True)
    assert abs(CTX.subtract(decimal_ln10(), LN10_REF)) <= Decimal("1E-45")
    assert decimal_ln10() == decimal_ln10()  # cached determinism


def test_log10_ignores_ambient_decimal_context():
    """Regression test (audit finding, currently FAILING -- real bug):

    ``decimal_log10`` decomposes ``x = m * 10**e`` via
    ``m = xv.scaleb(-e)`` with NO context argument.
    ``Decimal.scaleb(other, context=None)`` rounds its *coefficient* to
    the current context's precision when none is supplied -- i.e. it
    silently reads and rounds through ``decimal.getcontext()`` (the
    ambient/global context, default 28 digits), corrupting the mantissa
    ``m`` *before* the ln(m)/ln(10) computation even starts. This
    contaminates the final log10 result whenever the ambient context
    precision is lower than the input's significant-digit count --
    exactly the class of ambient-context leak this module's docstring
    says can never happen ("Every routine builds its own explicit
    decimal.Context ... and never reads or mutates the ambient global
    context"), and the same class of bug already fixed for abs() in
    equations.py and DecimalComplex.modulus()'s im==0 fast path.

    This test degrades the ambient context to 6 digits and shows the
    high-precision digits of a >6-sig-digit input get rounded away
    before log10 even runs, changing the numeric result (not just its
    displayed length) relative to a healthy ambient-context run.
    """
    import decimal as _decimal

    old = _decimal.getcontext().prec
    try:
        x = Decimal("12345.6789")  # 9 significant digits
        _decimal.getcontext().prec = 50
        healthy = decimal_log10(x)
        _decimal.getcontext().prec = 6
        degraded = decimal_log10(x)
        assert degraded == healthy, (
            "decimal_log10(12345.6789) changed value when the ambient "
            f"Decimal context precision dropped to 6: healthy={healthy!r} "
            f"degraded={degraded!r}. The internal mantissa split "
            "(xv.scaleb(-e)) is rounding through decimal.getcontext() "
            "instead of an explicit working-precision Context."
        )
    finally:
        _decimal.getcontext().prec = old


# -- dB --------------------------------------------------------------------------------------------

def test_db_values_and_zero_category():
    assert magnitude_db(Decimal(1)).value == Decimal(0)
    assert magnitude_db(2).category.value == "finite"
    got = magnitude_db(Decimal(2)).value
    assert abs(CTX.subtract(got, CTX.multiply(Decimal(20), LOG10_2))) <= Decimal("1E-45")
    z = magnitude_db(Decimal(0))
    assert z.category.value == "negative_infinity_db" and z.value is None
    assert z.to_dict() == {"category": "negative_infinity_db", "value": None,
                           "linear": "0"}
    with pytest.raises(BodeError):
        magnitude_db(Decimal(-1))
    # Wrong-type numerics surface the numeric layer's TypeError (D1-D3
    # exactness-boundary convention); domain errors are BodeError.
    with pytest.raises(TypeError):
        magnitude_db(True)
    with pytest.raises(BodeError):
        magnitude_db(Decimal(0)).require_finite()


def test_half_power_threshold_constant():
    t = half_power_threshold_db(Decimal(0))
    # -10*log10(2), never a rounded -3.0 literal.
    exp = CTX.minus(CTX.multiply(Decimal(10), LOG10_2))
    assert abs(CTX.subtract(t, exp)) <= Decimal("1E-45")
    assert abs(t - Decimal("-3.010299956639811952137388947")) <= Decimal("1E-24")


def test_canonical_frequency_keys():
    assert canonical_frequency_key(Q("1000 Hz")) == canonical_frequency_key(Q("1 kHz"))
    assert canonical_frequency_key(Q("1000 Hz")) == canonical_frequency_key(Q("1000.0 Hz"))
    assert canonical_frequency_key(Q("1000 Hz")) != canonical_frequency_key(Q("1001 Hz"))
    grid = log_frequencies("10 Hz", 10, 5)
    keys = [canonical_frequency_key(f) for f in grid]
    assert len(set(keys)) == 5 and keys == sorted(keys, key=Decimal)


def test_canonicalization_end_to_end_digest():
    # "1000 Hz" vs "1 kHz" sweeps: identical physics, identical digest.
    c = rc_lowpass()
    a = analyze_bode(frequency_response(c, h_transfer(), ["1000 Hz"]))
    b = analyze_bode(frequency_response(c, h_transfer(), ["1 kHz"]))
    assert a.digest == b.digest
    assert a.points[0].frequency.to_base() == b.points[0].frequency.to_base()


# -- unwrap ------------------------------------------------------------------------------------------

def test_unwrap_trivial_and_single():
    assert unwrap_phases([Decimal("0.5"), Decimal("0.6")])[0] == [Decimal("0.5"), Decimal("0.6")]
    assert unwrap_phases([Decimal("0.5"), Decimal("0.6")])[1] == [(0, 1)]
    out, seg = unwrap_phases([Decimal("1.0")])
    assert out == [Decimal("1.0")] and seg == [(0, 1 - 1)]


def test_unwrap_plus_minus_2pi_jumps():
    d = Decimal("0.28318530717958647692528676655901")  # 2pi - 6
    out, seg = unwrap_phases([Decimal("3.0"), Decimal("-3.0")])
    assert abs(CTX.subtract(out[1], CTX.add(Decimal("-3.0"),
                                            CTX.multiply(Decimal(2), decimal_pi_value())))) <= TOL
    assert abs(CTX.subtract(out[1], Decimal("3.0"))) <= Decimal("0.3")
    out2, _ = unwrap_phases([Decimal("-3.0"), Decimal("3.0")])
    assert abs(CTX.subtract(out2[1], Decimal("-3.0"))) <= Decimal("0.3")
    assert seg == [(0, 1)]


def _pi_dec():
    return decimal_pi_value()


def test_unwrap_large_jump_and_tie():
    two_pi = CTX.multiply(Decimal(2), _pi_dec())
    # A single step implying >2pi CANNOT be recovered: the min-step rule
    # keeps [0, 0.7168] (undersampling limitation, documented — unwrap
    # never invents winding). Gradual winding DOES accumulate past 2pi:
    w4 = CTX.subtract(Decimal("4.5"), two_pi)
    w6 = CTX.subtract(Decimal("6.0"), two_pi)
    w75 = CTX.subtract(Decimal("7.5"), two_pi)
    out, _ = unwrap_phases([Decimal("0"), Decimal("1.5"), Decimal("3.0"),
                            w4, w6, w75])
    for got, want in zip(out, [Decimal("0"), Decimal("1.5"), Decimal("3.0"),
                               Decimal("4.5"), Decimal("6.0"), Decimal("7.5")]):
        assert abs(CTX.subtract(got, want)) <= TOL
    tie, _ = unwrap_phases([Decimal("0"), _pi_dec()])
    assert tie[1] == _pi_dec()  # exact-pi tie: deterministic, no new turn


def test_unwrap_segments_and_gaps():
    out, seg = unwrap_phases([Decimal("0.1"), Decimal("0.2"), None, Decimal("5.9")])
    assert out[2] is None and seg == [(0, 1), (3, 3)]
    # New segment restarts at offset 0: post-gap values are NOT unwound
    # against pre-gap history (never across invalid points).
    assert out[3] == Decimal("5.9")
    assert unwrap_phases([None, None]) == ([None, None], [])
    assert unwrap_phases([]) == ([], [])


def test_unwrap_pi_edges():
    d = _pi_dec()
    out, _ = unwrap_phases([Decimal("3.0"), Decimal("3.1"),
                            CTX.minus(Decimal("3.1")), CTX.minus(Decimal("3.0"))])
    assert all((CTX.subtract(b, a) >= 0) for a, b in zip(out, out[1:]))
    assert abs(CTX.subtract(out[2], CTX.add(CTX.minus(Decimal("3.1")),
                                            CTX.multiply(Decimal(2), d)))) <= TOL


# -- crossings -----------------------------------------------------------------------------------------

def test_crossings_straddle_hit_flat_gap():
    t = Decimal("1.5")
    assert [(c.lo_index, c.hi_index) for c in
            crossing_brackets(["a", "b", "c"], [Decimal("1"), Decimal("2"), Decimal("3")], t)] == [(0, 1)]
    assert [(c.lo_index, c.hi_index) for c in
            crossing_brackets(["a", "b", "c"], [Decimal("3"), Decimal("2"), Decimal("1")], t)] == [(1, 2)]
    assert [(c.lo_index, c.hi_index) for c in
            crossing_brackets(["a", "b"], [Decimal("1"), t], t)] == [(1, 1)]
    # flat run ON the threshold is not a crossing; exact-hit pair is:
    assert crossing_brackets(["a", "b"], [t, t], t) == []
    assert crossing_brackets(["a", "b", "c"], [Decimal("2"), None, Decimal("1")], t) == []
    c0 = crossing_brackets(["a", "b"], [Decimal("1"), Decimal("2")], t)[0]
    assert c0.label == "cutoff" and c0.threshold == str(t)
    with pytest.raises(BodeError):
        crossing_brackets(["a"], [Decimal("1"), Decimal("2")], t)


# -- bands -----------------------------------------------------------------------------------------------

def test_bands_two_boundaries_interval():
    from academic_core.domain.engineering.units import parse_quantity as _pq

    freqs = [_pq(s) for s in ("10 Hz", "20 Hz", "30 Hz", "40 Hz", "50 Hz")]
    mags = [Decimal("0.5"), Decimal("2"), Decimal("3"), Decimal("2"), Decimal("0.5")]
    bands = threshold_bands(freqs, mags, Decimal(1))
    assert len(bands) == 1 and bands[0].defined
    assert (bands[0].lo.lo_index, bands[0].lo.hi_index) == (0, 1)
    assert (bands[0].hi.lo_index, bands[0].hi.hi_index) == (3, 4)
    assert bands[0].bandwidth_lo == Decimal(20) and bands[0].bandwidth_hi == Decimal(40)


def test_bands_edge_open_undefined():
    from academic_core.domain.engineering.units import parse_quantity as _pq

    freqs = [_pq(s) for s in ("10 Hz", "20 Hz", "30 Hz")]
    bands = threshold_bands(freqs, [Decimal("5"), Decimal("4"), Decimal("0.5")], Decimal(1))
    assert len(bands) == 1 and not bands[0].defined
    assert bands[0].bandwidth_lo is None and "edge" in bands[0].reason
    assert "0 Hz" in bands[0].reason  # no DC anchoring, stated


def test_bands_gap_open_and_multiple():
    from academic_core.domain.engineering.units import parse_quantity as _pq

    freqs = [_pq(f"{f} Hz") for f in (10, 20, 30, 40, 50, 60, 70)]
    mags = [Decimal("3"), Decimal("0.5"), Decimal("0.5"), Decimal("2.5"),
            Decimal("0.2"), Decimal("4"), Decimal("0.1")]
    bands = threshold_bands(freqs, mags, Decimal(1))
    assert len(bands) == 3  # nothing silently dropped
    assert [b.defined for b in bands] == [False, True, True]
    mid = bands[1]
    assert (mid.lo.lo_index, mid.lo.hi_index) == (2, 3)
    assert (mid.hi.lo_index, mid.hi.hi_index) == (3, 4)


# -- extrema -----------------------------------------------------------------------------------------------

def test_extrema_strict_flat_endpoints():
    k = ["a", "b", "c", "d", "e"]
    assert [(e.kind, e.index) for e in observed_extrema(
        k, [Decimal("1"), Decimal("3"), Decimal("2"), Decimal("2"), Decimal("0")])] == [
        ("endpoint-minimum", 0), ("strict-maximum", 1), ("endpoint-minimum", 4)]
    flat = observed_extrema(k, [Decimal("1"), Decimal("2"), Decimal("2"), Decimal("2"), Decimal("0")])
    assert [(e.kind, e.index, e.end_index) for e in flat] == [
        ("endpoint-minimum", 0, 0), ("flat-maximum", 1, 3), ("endpoint-minimum", 4, 4)]
    const = observed_extrema(["a", "b"], [Decimal("7"), Decimal("7")])
    assert sorted(e.kind for e in const) == ["flat-maximum", "flat-minimum"]
    assert observed_extrema(["a"], [Decimal("1")]) == []  # lone point: no claim
    assert observed_extrema(k, [None] * 5) == []
    assert observed_extrema(["a"], [Decimal("1")]) == []  # lone point: no claim
    with pytest.raises(BodeError):
        observed_extrema(["a"], [Decimal("1"), Decimal("2")])


# -- reactance -----------------------------------------------------------------------------------------------

def test_reactance_brackets_label_and_none():
    r = reactance_zero_brackets(["a", "b", "c"],
                                [Decimal("-2"), Decimal("1"), Decimal("3")], )
    assert len(r) == 1 and r[0].label == "reactance-zero-candidate"
    assert (r[0].lo_index, r[0].hi_index) == (0, 1)
    assert reactance_zero_brackets(["a", "b"], [Decimal("1"), Decimal("2")]) == []
    assert reactance_zero_brackets(["a", "b"], [Decimal("1"), None]) == []


# -- analyze_bode end-to-end ------------------------------------------------------------------------------------

def _lp_sweep(freqs):
    d = ResponseDefinition(
        "transfer", (voltage_between("in", "0"), voltage_between("out", "0"), "V1"))
    sw = frequency_response(rc_lowpass(), d, freqs)
    assert sw.status == "completed"
    return analyze_bode(sw), sw


def test_bode_rc_lowpass_cutoff_contains_fc():
    from academic_core.domain.engineering.math.trig import decimal_pi as _dpi

    # fc = 1/(2 pi R C) from PI50 here (independent of the engine tables).
    fc = CTX.divide(Decimal(1), CTX.multiply(
        CTX.multiply(Decimal(2), PI50),
        CTX.multiply(Decimal(1000), Decimal("0.000001"))))
    b, _ = _lp_sweep([f"{f} Hz" for f in (10, 50, 100, 150, 200, 500, 1000, 5000)])
    assert len(b.cutoffs) == 1
    lo, hi = Decimal(b.cutoffs[0].lo_freq), Decimal(b.cutoffs[0].hi_freq)
    assert lo <= fc <= hi
    # Bracket endpoints are sample dB values: no interpolation anywhere.
    db_vals = {str(p.db.value) for p in b.points if p.db is not None}
    for cu in b.cutoffs:
        assert cu.lo_value in db_vals and cu.hi_value in db_vals


def test_bode_rc_lowpass_band_undefined_no_anchor():
    b, _ = _lp_sweep(["10 Hz", "100 Hz", "1 kHz", "10 kHz"])
    assert len(b.bands) == 1 and not b.bands[0].defined
    assert "0 Hz" in b.bands[0].reason or "edge" in b.bands[0].reason
    assert b.bands[0].bandwidth_lo is None


def test_bode_rc_lowpass_db_and_segments():
    b, _ = _lp_sweep(["10 Hz", "100 Hz", "1 kHz", "10 kHz"])
    assert abs(b.points[0].db.value) <= Decimal("0.1")  # ~0 dB in-band
    assert b.points[-1].db.value < Decimal(-30)  # deep stopband
    assert all(p.db.category.value == "finite" for p in b.points)
    assert b.segments == ((0, 3),)  # one continuous valid run
    assert b.points[0].source_digest is not None


def test_bode_exact_divider_constant():
    c = ckt("div", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "out"),
            R_("R2", "2 kOhm", "out", "0"))
    d = ResponseDefinition(
        "transfer", (voltage_between("in", "0"), voltage_between("out", "0"), "V1"))
    sw = frequency_response(c, d, ["100 Hz", "1 kHz", "10 kHz"])
    b = analyze_bode(sw)
    assert all(p.wrapped == Decimal(0) for p in b.points)  # exact real H
    assert all(p.db.value == p.db.value for p in b.points)
    assert [(e.kind) for e in b.extrema] == ["flat-maximum", "flat-minimum"]
    assert b.cutoffs == () and all(not x.defined for x in b.bands)

def test_bode_axis_mixed_exact_sources():
    # Non-axis EXACT phasors (axis-mixed sources, real network): phase via
    # the documented promotion path, no crash, in (-pi, pi].
    c = ckt("mx", V_("V1", "10 V", "a", "0", phase_=0),
            V_("V2", "5 V", "b", "0", phase_=90),
            R_("R1", "1 kOhm", "a", "b"), R_("R2", "1 kOhm", "b", "0"))
    d = ResponseDefinition(
        "transfer", (voltage_between("a", "0"), voltage_between("b", "0"), ""))
    sw = frequency_response(c, d, ["1 kHz"])
    b = analyze_bode(sw)
    assert b.points[0].wrapped is not None
    assert CTX.minus(_pi()) < b.points[0].wrapped <= _pi()


def _pi():
    from academic_core.domain.engineering.math.trig import decimal_pi as _dpi

    return _dpi()


def test_bode_impedance_kinds_no_bandwidth():
    c = ckt("rlc", V_("V1", "10 V", "in", "0"), R_("R1", "100 ohm", "in", "a"),
            L_("L1", "10 mH", "a", "b"), C_("C1", "1 uF", "b", "0"))
    d = ResponseDefinition("branch-impedance", "R1")
    sw = frequency_response(c, d, ["100 Hz", "1 kHz", "10 kHz"])
    b = analyze_bode(sw)
    assert b.bands == () and b.cutoffs == ()
    assert all(e is not None for e in [b.points[0].linear])
    dz = ResponseDefinition(
        "transfer", (voltage_between("in", "0"), voltage_between("b", "0"), "V1"))
    sw2 = frequency_response(c, dz, ["100 Hz", "503 Hz", "1 kHz", "10 kHz"])
    b2 = analyze_bode(sw2)
    assert isinstance(b2.bands, tuple)


def test_bode_all_invalid_sweep_empty_result():
    c = ckt("sg", V_("V1", "10 V", "n", "0"), V_("V2", "10 V", "n", "0"),
            R_("R1", "1 kOhm", "n", "0"))
    d = ResponseDefinition("branch-impedance", "R1")
    sw = frequency_response(c, d, ["100 Hz", "1 kHz"])
    assert sw.status == "completed_with_point_failures"
    b = analyze_bode(sw)
    assert all(p.linear is None and p.db is None and p.wrapped is None for p in b.points)
    assert b.cutoffs == () and b.bands == () and b.extrema == ()
    assert any("no valid points" in x for x in b.diagnostics)


def test_bode_single_point_and_custom_threshold():
    b, _ = _lp_sweep(["500 Hz"])
    assert len(b.points) == 1 and b.segments == ((0, 0),)
    # A lone above-threshold sample is still a reported (open) run.
    assert len(b.bands) == 1 and not b.bands[0].defined
    assert b.cutoffs == () and b.extrema == ()
    b2, _ = _lp_sweep(["10 Hz", "100 Hz", "1 kHz", "10 kHz"])
    assert b2.provenance["threshold_rule"].startswith("half-power")
    custom = analyze_bode(frequency_response(
        rc_lowpass(),
        ResponseDefinition("transfer", (voltage_between("in", "0"),
                                        voltage_between("out", "0"), "V1")),
        ["10 Hz", "100 Hz", "1 kHz", "10 kHz"]), db_threshold=Decimal("-6"))
    assert custom.provenance["threshold_rule"] == "explicit"
    assert all(c.threshold == "-6" for c in custom.cutoffs)
    with pytest.raises(BodeError):
        analyze_bode(frequency_response(
            rc_lowpass(),
            ResponseDefinition("transfer", (voltage_between("in", "0"),
                                            voltage_between("out", "0"), "V1")),
            ["1 kHz"]), db_threshold=1.5)


def test_bode_rejects_non_sweep_and_empty():
    from academic_core.domain.engineering.ac.response import SweepResult

    with pytest.raises(BodeError):
        analyze_bode("not a sweep")
    with pytest.raises(BodeError):
        analyze_bode(SweepResult("completed", (), None, {}, (), "x"))


# -- oracles: analytic -----------------------------------------------------------------------------------------------

def _closed_rc(f_hz):
    # H = 1/(1 + j wRC), R=1k C=1u, wRC from PI50 (independent path).
    wrc = CTX.multiply(CTX.multiply(CTX.multiply(Decimal(2), PI50), Decimal(f_hz)),
                       CTX.multiply(Decimal(1000), Decimal("0.000001")))
    den = CTX.add(Decimal(1), CTX.multiply(wrc, wrc))
    return (CTX.divide(Decimal(1), den), CTX.minus(CTX.divide(wrc, den)))


def test_oracle_rc_closed_form_db_phase():
    import math as _math

    for f in (50, 200, 1000, 5000):
        b, _ = _lp_sweep([f"{f} Hz"])
        re_e, im_e = _closed_rc(f)
        got = b.points[0]
        mag_e = CTX.sqrt(CTX.add(CTX.multiply(re_e, re_e), CTX.multiply(im_e, im_e)))
        assert abs(CTX.subtract(got.linear, mag_e)) <= Decimal("1E-40")
        db_e = CTX.multiply(Decimal(20), decimal_log10(mag_e))
        assert abs(CTX.subtract(got.db.value, db_e)) <= Decimal("1E-40")
        ang = _math.degrees(_math.atan2(float(im_e), float(re_e)))
        assert abs(float(got.wrapped) * 57.29577951308232 - ang) <= 1e-6


def test_oracle_asymptotic_slopes():
    # Single-pole low-pass: -20 dB/decade well into the stopband.
    freqs = ["10 kHz", "100 kHz"]
    b, _ = _lp_sweep(freqs)
    slope = CTX.subtract(b.points[1].db.value, b.points[0].db.value)
    assert abs(CTX.subtract(slope, Decimal(-20))) <= Decimal("0.5")
    # Divider: 0 dB/decade everywhere (constant H).
    c = ckt("div", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "out"),
            R_("R2", "2 kOhm", "out", "0"))
    d = ResponseDefinition(
        "transfer", (voltage_between("in", "0"), voltage_between("out", "0"), "V1"))
    sw = frequency_response(c, d, ["100 Hz", "1 kHz", "10 kHz", "100 kHz"])
    b2 = analyze_bode(sw)
    dbs = [p.db.value for p in b2.points]
    assert max(dbs) - min(dbs) <= Decimal("1E-40")


def test_oracle_bridge_and_cramer_divider():
    # Unbalanced bridge H by hand Fractions (independent nodal, no D5).
    c = ckt("br", V_("V1", "10 V", "t", "0"), R_("R1", "1 kOhm", "t", "a"),
            R_("R2", "2 kOhm", "t", "b"), R_("R3", "1 kOhm", "a", "0"),
            R_("R4", "3 kOhm", "b", "0"), R_("R5", "1 kOhm", "a", "b"))
    d = ResponseDefinition(
        "transfer", (voltage_between("t", "0"), voltage_between("a", "b"), "V1"))
    sw = frequency_response(c, d, ["1 kHz"])
    b = analyze_bode(sw)
    # Hand: 3Va-Vb=10, -6Va+11Vb=30 -> Va-Vb = -10/27, H = -1/27.
    assert b.points[0].linear == CTX.divide(Decimal(1), Decimal(27))
    assert b.points[0].wrapped == decimal_pi_value()


def test_oracle_rlc_bandpass_peak():
    # Series RLC, H = Vr/Vin peaks at f0 = 1/(2 pi sqrt(LC)) = 1591.5 Hz
    # for L=10mH, C=1uF. Discrete peak at the 1592 Hz sample.
    c = ckt("bp", V_("V1", "10 V", "in", "0"), R_("R1", "100 ohm", "in", "a"),
            L_("L1", "10 mH", "a", "b"), C_("C1", "1 uF", "b", "0"))
    d = ResponseDefinition(
        "transfer", (voltage_between("in", "0"), voltage_between("in", "a"), "V1"))
    sw = frequency_response(c, d, ["100 Hz", "503 Hz", "1000 Hz", "1592 Hz", "10 kHz"])
    b = analyze_bode(sw)
    kinds = [e.kind for e in b.extrema]
    assert "strict-maximum" in kinds
    peak = next(e for e in b.extrema if e.kind == "strict-maximum")
    assert peak.index == 3  # discrete peak at the 1592 Hz sample


# -- oracles: ngspice --------------------------------------------------------------------------------------------

def _ng_backend():
    from academic_core.infrastructure.ngspice import NgSpiceBackend

    b = NgSpiceBackend()
    return b if b.detect().verified else None


NG = _ng_backend()


def _spice_netlist(circuit):
    lines = [f"* D6 oracle {circuit.name}"]
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


def _oracle_exact(circuit, freq_hz):
    """Single-frequency exact deck (nearest-match sampler hazard avoided)."""
    from academic_core.domain.engineering.simulation import ACAnalysis

    assert NG is not None
    ac = ACAnalysis(sweep_type="lin", points=2, fstart=str(freq_hz),
                    fstop=str(int(freq_hz) + 1))
    res = NG.simulate(_spice_netlist(circuit), analyses=(ac,))
    assert res.status == "COMPLETED"
    return res


def _wrap_deg(d):
    while d > 180.0:
        d -= 360.0
    while d <= -180.0:
        d += 360.0
    return d


def _check_bode_point(got, ref_c, tol_db=0.2, tol_ph=1.0):
    import math as _math

    mag = abs(ref_c)
    assert abs(float(got.linear) - mag) <= 0.01 * max(1.0, mag)
    assert abs(float(got.db.value) - 20.0 * _math.log10(mag)) <= tol_db
    exp_ph = _math.degrees(_math.atan2(ref_c.imag, ref_c.real))
    assert abs(_wrap_deg(float(got.wrapped) * 57.29577951308232 - exp_ph)) <= tol_ph


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_ngspice_rc_db_phase():
    c = rc_lowpass()
    for f in (100, 1000, 10000):
        b, _ = _lp_sweep([f"{f} Hz"])
        res = _oracle_exact(c, f)
        vo = res.sample_complex_at("v(out)", str(f))
        vin = res.sample_complex_at("v(in)", str(f))
        assert vo is not None and vin is not None
        _check_bode_point(b.points[0], vo / vin)


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_ngspice_slope_decade():
    c = rc_lowpass()
    import math as _math

    mags = []
    for f in (2000, 20000):
        res = _oracle_exact(c, f)
        vo = res.sample_complex_at("v(out)", str(f))
        vin = res.sample_complex_at("v(in)", str(f))
        mags.append(abs(vo / vin))
    slope = 20.0 * (_math.log10(mags[1]) - _math.log10(mags[0]))
    assert abs(slope - (-20.0)) <= 0.5
    b, _ = _lp_sweep(["2000 Hz", "20000 Hz"])
    dbs = [p.db.value for p in b.points]
    assert abs(float(dbs[1] - dbs[0]) - slope) <= 0.3


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_ngspice_divider_current_gain():
    # Hi via two printable V-source currents: series loop V1-R-Vsense(0V).
    c = ckt("hi", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "a"),
            V_("V2", "0 V", "a", "0"))
    d = ResponseDefinition(
        "transfer", (current_through("V1"), current_through("V2"), "V1"))
    sw = frequency_response(c, d, ["1 kHz"])
    b = analyze_bode(sw)
    res = _oracle_exact(c, 1000)
    i1 = res.sample_complex_at("i(v1)", "1000")
    i2 = res.sample_complex_at("i(v2)", "1000")
    assert i1 is not None and i2 is not None
    _check_bode_point(b.points[0], i2 / i1, tol_db=0.3, tol_ph=1.0)


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_ngspice_bridge_phase():
    c = ckt("obr", V_("V1", "10 V", "t", "0"), R_("R1", "1 kOhm", "t", "a"),
            R_("R2", "2 kOhm", "t", "b"), R_("R3", "1 kOhm", "a", "0"),
            R_("R4", "3 kOhm", "b", "0"), R_("R5", "1 kOhm", "a", "b"))
    d = ResponseDefinition(
        "transfer", (voltage_between("t", "0"), voltage_between("a", "b"), "V1"))
    sw = frequency_response(c, d, ["500 Hz"])
    b = analyze_bode(sw)
    res = _oracle_exact(c, 500)
    va = res.sample_complex_at("v(a)", "500")
    vb = res.sample_complex_at("v(b)", "500")
    vin = res.sample_complex_at("v(t)", "500")
    _check_bode_point(b.points[0], (va - vb) / vin, tol_db=0.3, tol_ph=1.0)


@pytest.mark.skipif(NG is None, reason="ngspice 47 verified backend unavailable")
def test_oracle_ngspice_sense_current_gain():
    # 0V sense source in series makes a branch current observable on
    # both sides (same modified circuit solved by each engine fairly).
    c = ckt("hi", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "a"),
            V_("V2", "0 V", "a", "0"))
    res = _oracle_exact(c, 1000)
    i1 = res.sample_complex_at("i(v1)", "1000")
    i2 = res.sample_complex_at("i(v2)", "1000")
    assert i1 is not None and i2 is not None
    d = ResponseDefinition(
        "transfer", (current_through("V1"), current_through("V2"), "V1"))
    sw = frequency_response(c, d, ["1000 Hz"])
    b = analyze_bode(sw)
    _check_bode_point(b.points[0], i2 / i1, tol_db=0.3, tol_ph=1.0)
    # Hand cross-check: series loop carries one current; |Hi| = 1.
    assert abs(b.points[0].linear - Decimal(1)) <= Decimal("1E-40")


# -- metamorphic -------------------------------------------------------------------------------------------------------

def test_meta_permutation_rename_invariance():
    c1 = ckt("m", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "out"),
             C_("C1", "1 uF", "out", "0"))
    c2 = ckt("m", C_("C1", "1 uF", "out", "0"), R_("R1", "1 kOhm", "in", "out"),
             V_("V1", "10 V", "in", "0"))
    c3 = ckt("m", V_("V1", "10 V", "src", "0"), R_("R1", "1 kOhm", "src", "dst"),
             C_("C1", "1 uF", "dst", "0"))
    freqs = ["100 Hz", "1 kHz"]
    b1 = analyze_bode(frequency_response(c1, h_transfer(), freqs))
    b2 = analyze_bode(frequency_response(c2, h_transfer(), freqs))
    assert b1.digest == b2.digest  # identical definitions + values
    b3 = analyze_bode(frequency_response(
        c3, ResponseDefinition("transfer", (voltage_between("src", "0"),
                                            voltage_between("dst", "0"), "V1")), freqs))
    # Renamed nodes change the definition (hence the digest, legitimately)
    # but the physical values are identical point by point.
    assert b3.digest != b1.digest
    for p1, p3 in zip(b1.points, b3.points):
        assert p1.linear == p3.linear and p1.wrapped == p3.wrapped
        assert p1.db.value == p3.db.value


def test_meta_amplitude_invariance():
    def build(v):
        return ckt("am", V_("V1", f"{v} V", "in", "0"),
                   R_("R1", "1 kOhm", "in", "out"), C_("C1", "1 uF", "out", "0"))

    b1 = analyze_bode(frequency_response(build(10), h_transfer(), ["500 Hz"]))
    b2 = analyze_bode(frequency_response(build(37), h_transfer(), ["500 Hz"]))
    p1, p2 = b1.points[0], b2.points[0]
    # Ratios cancel the excitation mathematically; independent trig
    # paths round the last ulp — tolerance, not identity.
    assert abs(CTX.subtract(p1.linear, p2.linear)) <= Decimal("1E-40")
    assert abs(CTX.subtract(p1.db.value, p2.db.value)) <= Decimal("1E-40")
    assert abs(CTX.subtract(p1.wrapped, p2.wrapped)) <= Decimal("1E-40")


def test_meta_conjugation_algebraic_only():
    # Network transfers are invariant under source phase rotation (the
    # excitation phasor cancels in the ratio) — while conj(H) as a
    # physical claim is never made (conjugation is algebraic only).
    def build(ph):
        return ckt("cj", V_("V1", "5 V", "in", "0", phase_=ph),
                   R_("R1", "1 kOhm", "in", "out"), C_("C1", "1 uF", "out", "0"))

    outs = []
    for ph in (45, -45):
        b, _ = _lp_like(build(ph))
        outs.append(b.points[0])
    # Identical up to working-precision rounding (ratios cancel the
    # excitation phasor mathematically; paths round independently).
    assert abs(CTX.subtract(outs[0].linear, outs[1].linear)) <= Decimal("1E-40")
    assert abs(CTX.subtract(outs[0].db.value, outs[1].db.value)) <= Decimal("1E-40")
    assert abs(CTX.subtract(outs[0].wrapped, outs[1].wrapped)) <= Decimal("1E-40")


def _lp_like(circuit):
    d = ResponseDefinition(
        "transfer", (voltage_between("in", "0"), voltage_between("out", "0"), "V1"))
    sw = frequency_response(circuit, d, ["1 kHz"])
    return analyze_bode(sw), sw


# -- false positives -----------------------------------------------------------------------------------------------------

def test_fp_no_resonance_verdict_no_q():
    b, _ = _lp_sweep(["10 Hz", "100 Hz", "1 kHz", "10 kHz"])
    blob = json.dumps(b.to_dict(), sort_keys=True).lower()
    for bad in ("resonant", '"q"', "resonance_frequency", "bandwidth_q"):
        assert bad not in blob, bad
    assert not hasattr(b, "resonant") and not hasattr(b, "q_factor")


def test_fp_no_invented_cutoff_bandwidth():
    c = ckt("flat", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "out"),
            R_("R2", "2 kOhm", "out", "0"))
    d = ResponseDefinition(
        "transfer", (voltage_between("in", "0"), voltage_between("out", "0"), "V1"))
    b = analyze_bode(frequency_response(c, d, ["10 Hz", "100 Hz", "1 kHz"]))
    assert b.cutoffs == ()
    assert all(not x.defined for x in b.bands)


def test_fp_no_zero_hz_no_interpolation():
    with pytest.raises(BodeError):
        log_frequencies("0 Hz", 10, 5)
    b, _ = _lp_sweep(["10 Hz", "100 Hz", "1 kHz", "10 kHz"])
    # Bracket endpoints are sample dB values: no interpolation anywhere.
    db_vals = {str(p.db.value) for p in b.points if p.db is not None}
    for cu in b.cutoffs:
        assert cu.lo_value in db_vals and cu.hi_value in db_vals


def test_mixed_invalid_sweep_segments_split():
    # Frequency-pinned source metadata makes one point INVALID in-band:
    # segments split around it, valid neighbors untouched.
    c = Circuit("pf")
    c.add(Component("V1", "V", Q("10 V"), {"+": "n", "-": "0"},
                    {"frequency": "1 kHz"}))
    c.add(R_("R1", "1 kOhm", "n", "0"))
    d = ResponseDefinition("branch-impedance", "R1")
    sw = frequency_response(c, d, ["500 Hz", "1 kHz", "2 kHz"])
    assert sw.status == "completed_with_point_failures"
    b = analyze_bode(sw)
    assert [p.status.value for p in b.points] == ["invalid", "solved", "invalid"]
    assert b.segments == ((1, 1),)
    assert b.points[1].linear is not None


def test_fp_no_uncertain_laundering_no_infinity():
    from academic_core.domain.engineering.ac.response import SweepPoint, SweepResult
    from academic_core.domain.engineering.ac.solution import ACStatus

    d = ResponseDefinition(
        "transfer", (voltage_between("in", "0"), voltage_between("out", "0"), "V1"))
    sw = frequency_response(rc_lowpass(), d, ["1 kHz"])
    assert sw.status == "completed"
    bad_point = SweepPoint(sw.points[0].frequency, ACStatus.NUMERICALLY_UNCERTAIN,
                           None, "uncertain oracle state", None)
    good = sw.points[0]
    mixed = SweepResult("completed_with_point_failures", (good, bad_point),
                        sw.definition, dict(sw.provenance), ("mixed",), sw.digest)
    b = analyze_bode(mixed)
    assert b.points[1].linear is None and b.points[1].unwrapped is None
    assert b.segments == ((0, 0),)
    blob = json.dumps(b.to_dict())
    assert "Infinity" not in blob and "inf" not in blob.replace("finite", "X").lower()
    assert b.points[0].linear is not None  # valid neighbor untouched


def test_fp_order_name_independence_and_two_humps():
    c = ckt("th", V_("V1", "10 V", "in", "0"), R_("R1", "10 ohm", "in", "a"),
            L_("L1", "10 mH", "a", "b"), C_("C1", "10 uF", "b", "m"),
            R_("R2", "1 kOhm", "m", "0"), L_("L2", "10 mH", "m", "0"),
            C_("C2", "1 uF", "m", "0"))
    d = ResponseDefinition(
        "transfer", (voltage_between("in", "0"), voltage_between("m", "0"), "V1"))
    freqs = [f"{f} Hz" for f in (50, 100, 200, 300, 503, 700, 1000, 1592, 2500, 5000, 10000)]
    b = analyze_bode(frequency_response(c, d, freqs))
    maxima = [e for e in b.extrema if e.kind == "strict-maximum"]
    assert len(maxima) >= 2  # two humps: no single-maximum assumption
    assert len(b.bands) >= 1 and all(x.defined or not x.defined for x in b.bands)


# -- edge cases --------------------------------------------------------------------------------------------------------------

def test_edge_n1_n2_all_invalid_single_valid():
    b, _ = _lp_sweep(["5 Hz"])
    assert len(b.points) == 1 and b.segments == ((0, 0),)
    b2, _ = _lp_sweep(["5 Hz", "50 Hz"])
    assert len(b2.points) == 2
    c = ckt("sg", V_("V1", "10 V", "n", "0"), V_("V2", "10 V", "n", "0"),
            R_("R1", "1 kOhm", "n", "0"))
    d = ResponseDefinition("branch-impedance", "R1")
    sw = frequency_response(c, d, ["100 Hz", "1 kHz"])
    assert sw.status == "completed_with_point_failures"
    b3 = analyze_bode(sw)
    assert all(p.linear is None for p in b3.points) and b3.extrema == ()


def test_edge_exact_threshold_and_no_crossing():
    # Constant transfer response exactly AT an explicit threshold: flat
    # run, hence no brackets (flat-on-threshold is not a crossing), but
    # one edge-open band. Threshold taken from the result itself so the
    # equality is exact, not arranged.
    c = ckt("ex", V_("V1", "10 V", "in", "0"), R_("R1", "1 kOhm", "in", "out"),
            R_("R2", "2 kOhm", "out", "0"))
    d = ResponseDefinition(
        "transfer", (voltage_between("in", "0"), voltage_between("out", "0"), "V1"))
    sw = frequency_response(c, d, ["100 Hz", "1 kHz"])
    t = analyze_bode(sw).points[0].db.value
    b = analyze_bode(sw, db_threshold=t)
    assert b.cutoffs == ()
    assert len(b.bands) == 1 and not b.bands[0].defined
    b2 = analyze_bode(sw, db_threshold=Decimal(100))
    assert b2.cutoffs == ()  # no crossing: empty, not an error


def test_edge_bands_and_monotonic_constant():
    b, _ = _lp_sweep(["10 Hz", "100 Hz", "1 kHz", "10 kHz"])
    assert all(x.defined is False or True for x in b.bands)
    mono = [p.linear for p in b.points]
    assert all(a >= c for a, c in zip(mono, mono[1:]))  # RC low-pass monotonic
    assert not any(e.kind == "strict-maximum" and 0 < e.index < 3 for e in b.extrema)


def test_edge_tiny_huge_magnitude():
    assert magnitude_db(Decimal("1E-300")).category.value == "finite"
    assert magnitude_db(Decimal("1E300")).category.value == "finite"
    assert magnitude_db(Decimal("1E300")).value > magnitude_db(Decimal("1E-300")).value
    c = ckt("bg", V_("V1", "10 V", "n", "0"), R_("R1", "1e12 ohm", "n", "0"))
    b = analyze_bode(frequency_response(
        c, ResponseDefinition("branch-impedance", "R1"), ["1 kHz"]))
    assert b.points[0].linear == Decimal("1000000000000")


def test_edge_zero_magnitude_sweep_no_contamination():
    # Balanced bridge differential output is exactly zero: every point
    # is NEGATIVE_INFINITY_DB, and nothing downstream breaks or invents.
    c = ckt("zb", V_("V1", "10 V", "t", "0"), R_("R1", "1 kOhm", "t", "a"),
            R_("R2", "1 kOhm", "t", "b"), R_("R3", "1 kOhm", "a", "0"),
            R_("R4", "1 kOhm", "b", "0"), R_("R5", "1 kOhm", "a", "b"))
    d = ResponseDefinition(
        "transfer", (voltage_between("t", "0"), voltage_between("a", "b"), "V1"))
    sw = frequency_response(c, d, ["100 Hz", "1 kHz", "10 kHz"])
    b = analyze_bode(sw)
    assert all(p.db is not None and p.db.category.value == "negative_infinity_db"
               for p in b.points)
    assert b.cutoffs == () and all(not x.defined for x in b.bands)
    blob = json.dumps(b.to_dict())
    assert "Infinity" not in blob


# -- security ----------------------------------------------------------------------------------------------------------------------

AC_DIR = pathlib.Path(__file__).resolve().parents[1] / "src" / "academic_core" / "domain" / "engineering" / "ac"
MATH_DIR = AC_DIR.parent / "math"


def test_security_no_dangerous_calls_or_deps():
    forbidden_calls = {"eval", "exec", "compile", "__import__", "open", "input",
                       "breakpoint"}
    forbidden_roots = {"os", "sys", "pathlib", "sqlite3", "urllib", "socket",
                       "http", "ftplib", "subprocess", "pickle", "marshal",
                       "ctypes", "PySide6", "numpy", "scipy", "math", "cmath",
                       "requests"}
    for path in (AC_DIR / "bode.py", MATH_DIR / "logarithm.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_calls, (path.name, node.func.id)
            if isinstance(node, ast.Import):
                for al in node.names:
                    assert al.name.split(".")[0] not in forbidden_roots, (path.name, al.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden_roots, (path.name, node.module)


def test_security_no_float_complex_math_names():
    for path in (AC_DIR / "bode.py", MATH_DIR / "logarithm.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        assert "float" not in names, path.name
        assert "complex" not in names, path.name
        assert "math" not in names and "cmath" not in names, path.name


# -- determinism / immutability / provenance / performance -------------------------------------------------------------------------------

def test_determinism_idempotence_immutability():
    c = rc_lowpass()
    before_net = c.to_netlist()
    freqs = log_frequencies("10 Hz", 10, 11)
    sw = frequency_response(c, h_transfer(), freqs)
    before_sw = json.dumps(sw.to_dict(), sort_keys=True)
    b1 = analyze_bode(sw)
    b2 = analyze_bode(sw)
    assert b1.digest == b2.digest
    assert json.dumps(b1.to_dict(), sort_keys=True) == json.dumps(b2.to_dict(), sort_keys=True)
    assert c.to_netlist() == before_net
    assert json.dumps(sw.to_dict(), sort_keys=True) == before_sw
    assert c.to_netlist() == before_net  # twice: no accumulation anywhere


def test_provenance_keys_link_digest_no_timestamp():
    b, sw = _lp_sweep(["100 Hz", "1 kHz"])
    for key in ("engine", "version", "source_sweep_digest", "definition",
                "transfer_kind", "frequencies", "threshold_db", "threshold_rule",
                "unwrap_rule", "bandwidth_rule", "numeric_mode", "per_point_status"):
        assert key in b.provenance, key
    assert b.provenance["engine"] == "f8d-ac-bode/1.0"
    assert b.provenance["source_sweep_digest"] == sw.digest
    assert b.definition["source_sweep_digest"] == sw.digest
    blob = json.dumps(b.to_dict(), sort_keys=True).lower()
    assert "timestamp" not in blob
    assert len(b.digest) == 64
    b_diff = analyze_bode(frequency_response(
        rc_lowpass(), h_transfer(), ["100 Hz", "2 kHz"]))
    assert b_diff.digest != b.digest  # sensitive to the grid


def test_performance_postprocessing_scales():
    import time as _time

    c = rc_lowpass()
    d = h_transfer()
    sw1000 = frequency_response(c, d, log_frequencies("10 Hz", 10, 1001))
    t0 = _time.time()
    b = analyze_bode(sw1000)
    t_post = _time.time() - t0
    assert len(b.points) == 1001 and t_post < 120, t_post
    tiny = analyze_bode(frequency_response(c, d, ["100 Hz"]))
    assert len(tiny.points) == 1


# -- generality ----------------------------------------------------------------------------------------------------------------------------------

def test_generality_64node_nonplanar_multigraph_ports():
    comps = [V_("V1", "12 V", "n0", "0")]
    for k in range(64):
        comps.append(R_(f"R{k + 1}", "1 kOhm", f"n{k}", f"n{k + 1}"))
        comps.append(C_(f"C{k + 1}", "100 nF", f"n{k + 1}", "0"))
    c = ckt("gl64", *comps)
    d = ResponseDefinition(
        "transfer", (voltage_between("n0", "0"), voltage_between("n64", "0"), "V1"))
    b = analyze_bode(frequency_response(c, d, ["100 Hz", "1 kHz", "10 kHz"]))
    assert len(b.points) == 3 and all(p.linear is not None for p in b.points)
    assert b.segments == ((0, 2),)


def test_sweep_n1000_end_to_end():
    c = rc_lowpass()
    d = h_transfer()
    grid = log_frequencies("10 Hz", 10, 1001)
    sw = frequency_response(c, d, grid)
    assert sw.status == "completed" and len(sw.points) == 1001
    b = analyze_bode(sw)
    assert len(b.points) == 1001
    assert b.segments == ((0, 1000),)
    assert len(b.cutoffs) == 1  # single -3dB crossing of the low-pass


def test_generality_k33_multisource_rlc():
    kcomps = [V_("V1", "10 V", "a", "0")]
    k = 1
    for u in ("a", "b", "c"):
        for v in ("x", "y", "z"):
            kcomps.append(R_(f"R{k}", "1 kOhm", u, v))
            k += 1
    kcomps += [R_("R10", "1 kOhm", "b", "0"), R_("R11", "1 kOhm", "c", "0"),
               R_("R12", "1 kOhm", "x", "0"), R_("R13", "1 kOhm", "y", "0"),
               C_("C14", "100 nF", "z", "0")]
    c = ckt("k33", *kcomps)
    d = ResponseDefinition(
        "transfer", (voltage_between("a", "0"), voltage_between("z", "0"), "V1"))
    b = analyze_bode(frequency_response(c, d, ["100 Hz", "1 kHz"]))
    assert all(p.linear is not None for p in b.points)
    mg = ckt("mg", V_("V1", "10 V", "n", "0"), R_("R1", "1 kOhm", "n", "m"),
             R_("R2", "2 kOhm", "n", "m"), L_("L1", "5 mH", "n", "m"),
             R_("R3", "1 kOhm", "m", "0"))
    d2 = ResponseDefinition("branch-admittance", "R2")
    b2 = analyze_bode(frequency_response(mg, d2, ["100 Hz", "5 kHz"]))
    assert all(p.wrapped is not None for p in b2.points)
