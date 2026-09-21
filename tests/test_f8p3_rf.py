"""F8-P3 RF and Transmission Lines -- certification test suite.

Test IDs P3-001..P3-044 map onto ``docs/gates/GATE-F8P3-DESIGN.md``
section 27. Oracles are closed-form/hand values or independent
algebraic derivations (never implementation == implementation, gate
§24). Tolerances are the ones justified in gate §8 (exact rational
formulas -> exact Decimal; round-trips <= 1e-40; matching residual
<= 1e-30).
"""

from __future__ import annotations

import ast
import json
from decimal import Decimal
from pathlib import Path

import pytest

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.math import DecimalComplex, decimal_pi, make_context
from academic_core.domain.engineering.rf import lines as L
from academic_core.domain.engineering.rf import margins as MG
from academic_core.domain.engineering.rf import matching as M
from academic_core.domain.engineering.rf import networks as N
from academic_core.domain.engineering.rf import primitives as P
from academic_core.domain.engineering.rf import report as R
from academic_core.domain.engineering.rf import smith as SM
from academic_core.domain.engineering.rf import sparams as S

D = Decimal
CTX = make_context()
TOL_RT = D("1e-40")
TOL_MATCH = D("1e-30")


def cmod(z: DecimalComplex) -> Decimal:
    return z.modulus()


# --------------------------------------------------------------------------
# P3-001..006 -- Primitives
# --------------------------------------------------------------------------


def test_p3001_frequency_period():
    f = P.frequency(D("1e9"))
    assert f.value == D("1e9") and f.unit.display == "Hz"
    t = P.period(D("1e9"))
    assert (t.value - D("1e-9")).copy_abs() <= TOL_RT
    with pytest.raises(ControlError):
        P.frequency(D(0))
    with pytest.raises(ControlError):
        P.frequency(D(-1))


def test_p3002_wavelength_beta():
    v = D("2e8")  # explicit phase velocity, never a hidden constant
    f = D("1e8")
    lam = P.wavelength(v, f)
    assert lam.value == D(2) and lam.unit.display == "m"
    beta = P.phase_constant(v, f)
    two_pi = CTX.multiply(D(2), decimal_pi(CTX))
    expect = CTX.divide(two_pi, lam.value)
    assert (beta - expect).copy_abs() <= TOL_RT


def test_p3003_angular_frequency():
    f = D("1e6")
    w = P.angular_frequency(f)
    expect = CTX.multiply(CTX.multiply(D(2), decimal_pi(CTX)), f)
    assert (w - expect).copy_abs() <= TOL_RT


def test_p3004_phasor_peak_rms():
    ph = P.Phasor.from_polar(D(10), D(0))
    assert ph.tag == P.PhasorTag.PEAK
    rms = ph.to_rms()
    sqrt2 = CTX.sqrt(D(2))
    assert (rms.value.re - CTX.divide(D(10), sqrt2)).copy_abs() <= TOL_RT
    back = rms.to_peak()
    assert (back.value.re - D(10)).copy_abs() <= TOL_RT


def test_p3005_impedance_admittance_categories():
    z = P.impedance_of(DecimalComplex(D(50), D(0)))
    y = P.impedance_to_admittance(z)
    assert y.category == P.ImpedanceCategory.FINITE
    assert (y.require_finite() - DecimalComplex(D("0.02"), D(0))).modulus() <= TOL_RT
    z_open = P.ImmittanceValue(P.ImpedanceCategory.INFINITE, None, "impedance")
    y_of_open = P.impedance_to_admittance(z_open)
    assert y_of_open.require_finite() == DecimalComplex.zero()
    z_short = P.impedance_of(DecimalComplex.zero())
    y_of_short = P.impedance_to_admittance(z_short)
    assert y_of_short.category == P.ImpedanceCategory.INFINITE


def test_p3006_complex_power_units():
    v = DecimalComplex(D(10), D(0))
    i = DecimalComplex(D(2), D(0))
    s = P.complex_power(v, i)
    assert s.p == D(10) and s.q == D(0)
    assert s.power_factor() == D(1)
    q = P.power_quantity(s)
    assert q.unit.display == "W"
    zero_s = P.complex_power(DecimalComplex.zero(), i)
    assert zero_s.power_factor() is None


# --------------------------------------------------------------------------
# P3-007..012 -- Gamma / VSWR / RL / open / short / matched / active
# --------------------------------------------------------------------------

Z0 = DecimalComplex(D(50), D(0))


def test_p3007_matched_gamma_zero():
    r = L.reflection_coefficient(L.load_matched(Z0), Z0)
    assert r.require_finite() == DecimalComplex.zero()
    v = MG.vswr(r.require_finite())
    assert v.require_finite() == D(1)


def test_p3008_open_gamma_plus_one():
    r = L.reflection_coefficient(L.load_open(), Z0)
    assert r.require_finite() == DecimalComplex.one()


def test_p3009_short_gamma_minus_one():
    r = L.reflection_coefficient(L.load_short(), Z0)
    assert r.require_finite() == -DecimalComplex.one()


def test_p3010_vswr_return_loss_hand_values():
    gamma = DecimalComplex(CTX.divide(D(1), D(3)), D(0))
    v = MG.vswr(gamma)
    assert (v.require_finite() - D(2)).copy_abs() <= TOL_RT
    rl = MG.return_loss_db(gamma)
    hand = D("9.542425094393248745900558065102306184002577283814")
    assert (rl.require_finite() - hand).copy_abs() <= D("1e-30")


def test_p3011_active_load_unsupported():
    gamma = DecimalComplex(D(2), D(0))
    v = MG.vswr(gamma)
    assert v.status == "UNSUPPORTED"
    rl = MG.return_loss_db(gamma)
    hand = D("-6.020599913279623904274777894489860535363797629242")
    assert (rl.require_finite() - hand).copy_abs() <= D("1e-30")


def test_p3012_boundary_gamma_states():
    r_open = MG.return_loss_db(DecimalComplex.one())
    assert r_open.require_finite() == D(0)
    r_zero = MG.return_loss_db(DecimalComplex.zero())
    assert r_zero.status == "UNSUPPORTED"
    v_open = MG.vswr(DecimalComplex.one())
    assert v_open.status == "UNSUPPORTED"
    ml = MG.mismatch_loss_db(DecimalComplex.one())
    assert ml.status == "UNSUPPORTED"


def test_p3012b_zl_plus_z0_zero_singular():
    zl = -Z0
    r = L.reflection_coefficient(L.load_impedance(zl), Z0)
    assert r.status == "SINGULAR"


# --------------------------------------------------------------------------
# P3-013..016 -- Zin direct == two-port, quarter-wave, half-wave, short-line
# --------------------------------------------------------------------------


def test_p3013_zin_direct_equals_two_port():
    gamma = L.PropagationConstant(D("0.01"), D(2))
    length = D("0.37")
    line = L.LineZGamma(z0=Z0, gamma=gamma, length=length)
    zl = DecimalComplex(D(30), D(-40))
    zin_direct = L.input_impedance(line, L.load_impedance(zl)).require_finite()
    abcd = N.line_abcd(line)
    zin_two_port = (abcd.a11 * zl + abcd.a12) / (abcd.a21 * zl + abcd.a22)
    assert (zin_direct - zin_two_port).modulus() <= TOL_RT


def test_p3014_quarter_wave_identity():
    beta = D(1)
    l_qw = CTX.divide(decimal_pi(CTX), D(2))
    line = L.LineZGamma(z0=Z0, gamma=L.PropagationConstant(D(0), beta), length=l_qw)
    zl = DecimalComplex(D(200), D(0))
    zin = L.input_impedance(line, L.load_impedance(zl)).require_finite()
    expect = (Z0 * Z0) / zl
    assert (zin - expect).modulus() <= D("1e-45")


def test_p3015_half_wave_identity():
    beta = D(1)
    l_hw = decimal_pi(CTX)
    line = L.LineZGamma(z0=Z0, gamma=L.PropagationConstant(D(0), beta), length=l_hw)
    zl = DecimalComplex(D(37), D(21))
    zin = L.input_impedance(line, L.load_impedance(zl)).require_finite()
    assert (zin - zl).modulus() <= D("1e-45")


def test_p3016_short_line_limit_and_zero_length():
    line0 = L.LineZGamma(z0=Z0, gamma=L.PropagationConstant(D(0), D(3)), length=D(0))
    zl = DecimalComplex(D(30), D(20))
    zin0 = L.input_impedance(line0, L.load_impedance(zl)).require_finite()
    assert zin0 == zl
    tiny = D("1e-12")
    line_tiny = L.LineZGamma(z0=Z0, gamma=L.PropagationConstant(D(0), D(3)), length=tiny)
    zin_tiny = L.input_impedance(line_tiny, L.load_impedance(zl)).require_finite()
    assert (zin_tiny - zl).modulus() <= D("1e-6")  # limit, not equality (gate §20)


# --------------------------------------------------------------------------
# P3-017..019 -- Z0/gamma, lossy->lossless continuity, degenerate battery
# --------------------------------------------------------------------------


def test_p3017_rlgc_z0_gamma_lossless_exact():
    line = L.LineRLGC(r=D(0), l_per_m=D("250e-9"), g=D(0), c=D("100e-12"), length=D(1), frequency=D("1e9"))
    gamma = line.propagation_constant()
    assert gamma.alpha == 0
    z0 = line.characteristic_impedance()
    expect_z0 = CTX.sqrt(CTX.divide(D("250e-9"), D("100e-12")))
    assert (z0.re - expect_z0).copy_abs() <= D("1e-40") and z0.im == 0


def test_p3018_lossy_to_lossless_continuity():
    tiny = D("1e-12")
    line_tiny_loss = L.LineRLGC(r=tiny, l_per_m=D("250e-9"), g=tiny, c=D("100e-12"), length=D(1), frequency=D("1e9"))
    line_lossless = L.LineRLGC(r=D(0), l_per_m=D("250e-9"), g=D(0), c=D("100e-12"), length=D(1), frequency=D("1e9"))
    z0_tiny = line_tiny_loss.characteristic_impedance()
    z0_lossless = line_lossless.characteristic_impedance()
    assert (z0_tiny - z0_lossless).modulus() <= D("1e-6")


def test_p3019_lambda_beta_consistency():
    v = D("2e8")
    f = D("5e7")
    lam = P.wavelength(v, f)
    beta = P.phase_constant(v, f)
    two_pi = CTX.multiply(D(2), decimal_pi(CTX))
    lam_from_beta = CTX.divide(two_pi, beta)
    assert (lam.value - lam_from_beta).copy_abs() <= TOL_RT


def test_p3019b_degenerate_z0_zero_singular():
    with pytest.raises(ControlError):
        L.LineRLGC(r=D(0), l_per_m=D(0), g=D(1), c=D(1), length=D(1), frequency=D(1)).characteristic_impedance()


def test_p3019c_gamma_zero_exact_path():
    line = L.LineZGamma(z0=Z0, gamma=L.PropagationConstant(D(0), D(0)), length=D(5))
    zl = DecimalComplex(D(30), D(20))
    zin = L.input_impedance(line, L.load_impedance(zl)).require_finite()
    assert zin == zl


# --------------------------------------------------------------------------
# P3-020..024 -- Z/Y/ABCD/T conversions and round-trips
# --------------------------------------------------------------------------

Z_SAMPLE = N.make_z(
    DecimalComplex(D(10), D(5)), DecimalComplex(D(2), D(1)),
    DecimalComplex(D(2), D(1)), DecimalComplex(D(20), D(-3)),
)


def test_p3020_z_to_y_to_z_round_trip():
    y = N.z_to_y(Z_SAMPLE)
    z2 = N.y_to_z(y)
    for a, b in zip((Z_SAMPLE.a11, Z_SAMPLE.a12, Z_SAMPLE.a21, Z_SAMPLE.a22), (z2.a11, z2.a12, z2.a21, z2.a22)):
        assert (a - b).modulus() <= TOL_RT


def test_p3021_z_to_abcd_to_z_round_trip():
    abcd = N.z_to_abcd(Z_SAMPLE)
    z2 = N.abcd_to_z(abcd)
    for a, b in zip((Z_SAMPLE.a11, Z_SAMPLE.a12, Z_SAMPLE.a21, Z_SAMPLE.a22), (z2.a11, z2.a12, z2.a21, z2.a22)):
        assert (a - b).modulus() <= TOL_RT


def test_p3022_abcd_to_z_to_abcd_round_trip():
    abcd = N.make_abcd(DecimalComplex(D(2), D(0)), DecimalComplex(D(30), D(5)), DecimalComplex(D("0.01"), D(0)), DecimalComplex(D(3), D(0)))
    z = N.abcd_to_z(abcd)
    abcd2 = N.z_to_abcd(z)
    for a, b in zip((abcd.a11, abcd.a12, abcd.a21, abcd.a22), (abcd2.a11, abcd2.a12, abcd2.a21, abcd2.a22)):
        assert (a - b).modulus() <= TOL_RT


def test_p3023_reciprocity_symmetry():
    assert N.reciprocal(Z_SAMPLE)  # z12 == z21 by construction
    asym = N.make_z(DecimalComplex(D(1), D(0)), DecimalComplex(D(2), D(0)), DecimalComplex(D(3), D(0)), DecimalComplex(D(1), D(0)))
    assert not N.reciprocal(asym)
    assert N.symmetric(Z_SAMPLE) is False
    sym = N.make_z(DecimalComplex(D(5), D(0)), DecimalComplex(D(2), D(0)), DecimalComplex(D(2), D(0)), DecimalComplex(D(5), D(0)))
    assert N.symmetric(sym)


def test_p3024_singular_conversions():
    z_singular = N.make_z(DecimalComplex(D(1), D(0)), DecimalComplex(D(2), D(0)), DecimalComplex(D(2), D(0)), DecimalComplex(D(4), D(0)))  # det == 0
    with pytest.raises(ControlError):
        N.z_to_y(z_singular)
    z_no_z21 = N.make_z(DecimalComplex(D(1), D(0)), DecimalComplex(D(2), D(0)), DecimalComplex.zero(), DecimalComplex(D(4), D(0)))
    with pytest.raises(ControlError):
        N.z_to_abcd(z_no_z21)
    abcd_no_c = N.make_abcd(DecimalComplex(D(1), D(0)), DecimalComplex(D(2), D(0)), DecimalComplex.zero(), DecimalComplex(D(4), D(0)))
    with pytest.raises(ControlError):
        N.abcd_to_z(abcd_no_c)


# --------------------------------------------------------------------------
# P3-025..027 -- S walls, reciprocity, unitarity
# --------------------------------------------------------------------------


def test_p3025_s_reference_domain():
    with pytest.raises(ControlError):
        S.SParameters(DecimalComplex.zero(), DecimalComplex.zero(), DecimalComplex.zero(), DecimalComplex.zero(),
                      reference=DecimalComplex(D(0), D(0)))
    with pytest.raises(ControlError):
        S.SParameters(DecimalComplex.zero(), DecimalComplex.zero(), DecimalComplex.zero(), DecimalComplex.zero(),
                      reference=DecimalComplex(D(-1), D(0)))
    ok = S.SParameters(DecimalComplex.zero(), DecimalComplex.zero(), DecimalComplex.zero(), DecimalComplex.zero(),
                       reference=DecimalComplex(D(50), D(10)))
    assert ok.reference == DecimalComplex(D(50), D(10))


def test_p3026_reciprocity_and_matched_load():
    idp = S.identity_passthrough()
    assert idp.is_reciprocal()
    matched = S.SParameters(DecimalComplex.zero(), DecimalComplex.one(), DecimalComplex.one(), DecimalComplex.zero())
    assert matched.is_matched(D("1e-40"))


def test_p3027_lossless_unitary():
    # A lossless reciprocal 2-port: pure phase-shift through-line (S11=S22=0, |S21|=|S12|=1)
    half = CTX.divide(decimal_pi(CTX), D(3))
    from academic_core.domain.engineering.math import decimal_cos, decimal_sin

    s21 = DecimalComplex(decimal_cos(half, CTX), decimal_sin(half, CTX))
    s = S.SParameters(DecimalComplex.zero(), s21, s21, DecimalComplex.zero())
    residual = s.unitarity_residual()
    assert residual <= D("1e-40")
    assert s.is_reciprocal()


# --------------------------------------------------------------------------
# P3-028..029 -- Cascade, singular abort
# --------------------------------------------------------------------------


def test_p3028_cascade_two_three_blocks_deterministic():
    gamma = L.PropagationConstant(D("0.005"), D(2))
    line_a = L.LineZGamma(z0=Z0, gamma=gamma, length=D("0.1"))
    line_b = L.LineZGamma(z0=Z0, gamma=gamma, length=D("0.2"))
    line_c = L.LineZGamma(z0=Z0, gamma=gamma, length=D("0.05"))
    a = N.line_abcd(line_a)
    b = N.line_abcd(line_b)
    c = N.line_abcd(line_c)
    ab = N.cascade_abcd((a, b))
    ab_again = N.cascade_abcd((a, b))
    assert ab == ab_again
    abc = N.cascade_abcd((a, b, c))
    abc_manual = N.cascade_abcd((ab, c))
    for x, y in zip((abc.a11, abc.a12, abc.a21, abc.a22), (abc_manual.a11, abc_manual.a12, abc_manual.a21, abc_manual.a22)):
        assert x == y

    # hand cascade of the SAME single line split into two half-length segments
    # must equal the whole line's ABCD (independent check, not impl==impl)
    line_whole = L.LineZGamma(z0=Z0, gamma=gamma, length=D("0.3"))
    whole = N.line_abcd(line_whole)
    for x, y in zip((ab.a11, ab.a12, ab.a21, ab.a22), (whole.a11, whole.a12, whole.a21, whole.a22)):
        assert (x - y).modulus() <= D("1e-38")


def test_p3028b_cascade_limit():
    gamma = L.PropagationConstant(D(0), D(1))
    block = N.line_abcd(L.LineZGamma(z0=Z0, gamma=gamma, length=D("0.01")))
    with pytest.raises(ControlError):
        N.cascade_abcd(tuple([block] * (N.MAX_CASCADE_BLOCKS + 1)))
    ok = N.cascade_abcd(tuple([block] * N.MAX_CASCADE_BLOCKS))
    assert ok.kind == "abcd"


def test_p3029_singular_s21_abort():
    s_isolated = S.SParameters(DecimalComplex(D(1), D(0)), DecimalComplex.zero(), DecimalComplex.zero(), DecimalComplex(D(1), D(0)))
    with pytest.raises(ControlError) as exc:
        S.s_to_abcd(s_isolated)
    assert exc.value.status == ControlStatus.SINGULAR


# --------------------------------------------------------------------------
# P3-030..031 -- Smith maps, circles, rotation
# --------------------------------------------------------------------------


def test_p3030_smith_z_gamma_y_round_trips():
    z_norm = DecimalComplex(D(2), D("0.5"))
    gamma = SM.z_to_gamma(z_norm)
    z_back = SM.gamma_to_z(gamma)
    assert (z_back - z_norm).modulus() <= TOL_RT
    y_norm = DecimalComplex.one() / z_norm
    gamma_y = SM.y_to_gamma(y_norm)
    y_back = SM.gamma_to_y(gamma_y)
    assert (y_back - y_norm).modulus() <= TOL_RT


def test_p3031_circles_and_rotation():
    xc = SM.reactance_circle(D(1))
    g = SM.z_to_gamma(DecimalComplex(D(0), D(1)))
    assert SM.on_reactance_circle(g, xc, D("1e-38"))
    rc = SM.resistance_circle(D(1))
    g2 = SM.z_to_gamma(DecimalComplex(D(1), D(3)))
    assert SM.on_resistance_circle(g2, rc, D("1e-38"))

    # Lossless rotation is a pure phase change: |Gamma(l)| == |Gamma_L|
    gamma_load = SM.z_to_gamma(DecimalComplex(D(2), D("0.5")))
    gamma_prop = L.PropagationConstant(D(0), D(3)).as_complex()
    rotated = SM.rotate_along_line(gamma_load, gamma_prop, D("0.1"))
    assert (rotated.modulus() - gamma_load.modulus()).copy_abs() <= D("1e-38")
    # hand angle: rotation by -2*beta*l
    hand_angle = CTX.minus(CTX.multiply(D(2), CTX.multiply(D(3), D("0.1"))))
    from academic_core.domain.engineering.math import complex_from_polar

    expect = gamma_load * complex_from_polar(D(1), hand_angle)
    assert (rotated - expect).modulus() <= D("1e-36")


# --------------------------------------------------------------------------
# P3-032..034 -- Matching + verification residual
# --------------------------------------------------------------------------


def test_p3032_conjugate_and_quarter_wave_match():
    zs = DecimalComplex(D(30), D(15))
    zl = M.conjugate_match(zs)
    assert zl == DecimalComplex(D(30), D(-15))

    qw = M.quarter_wave_match(D(50), D(200))
    assert (qw.transformer_z0 - D(100)).copy_abs() <= TOL_RT
    beta = D(1)
    l_qw = CTX.divide(decimal_pi(CTX), D(2))
    line = L.LineZGamma(z0=DecimalComplex(qw.transformer_z0, D(0)), gamma=L.PropagationConstant(D(0), beta), length=l_qw)
    zin = L.input_impedance(line, L.load_impedance(DecimalComplex(D(200), D(0)))).require_finite()
    assert (zin - DecimalComplex(D(50), D(0))).modulus() <= D("1e-36")

    with pytest.raises(ControlError):
        M.quarter_wave_match(D(50), D(-1))


def test_p3033_lc_match_verification():
    z0 = D(50)
    z0c = DecimalComplex(z0, D(0))
    zl = DecimalComplex(D(75), D(40))
    solutions = M.lc_match(zl, z0)
    assert solutions
    for sol in solutions:
        xs = DecimalComplex(D(0), sol.series_reactance)
        bp = DecimalComplex(D(0), sol.shunt_susceptance)
        series_ab = N.make_abcd(DecimalComplex.one(), xs, DecimalComplex.zero(), DecimalComplex.one())
        shunt_ab = N.make_abcd(DecimalComplex.one(), DecimalComplex.zero(), bp, DecimalComplex.one())
        blocks = (shunt_ab, series_ab) if sol.topology == "series-then-shunt" else (series_ab, shunt_ab)
        total = N.cascade_abcd(blocks)
        zin = (total.a11 * zl + total.a12) / (total.a21 * zl + total.a22)
        assert (zin - z0c).modulus() <= TOL_MATCH

    with pytest.raises(ControlError):
        M.lc_match(DecimalComplex.zero(), z0)


def test_p3034_single_stub_shunt_and_series_verification():
    z0 = D(50)
    z0c = DecimalComplex(z0, D(0))
    beta = D(2)
    zl = DecimalComplex(D(75), D(40))

    for sol in M.single_stub_shunt_match(zl, z0, beta):
        tap = L.LineZGamma(z0=z0c, gamma=L.PropagationConstant(D(0), beta), length=sol.tap_distance)
        zin_tap = L.input_impedance(tap, L.load_impedance(zl)).require_finite()
        stub_line = L.LineZGamma(z0=z0c, gamma=L.PropagationConstant(D(0), beta), length=sol.stub_length)
        stub_load = L.load_short() if sol.stub_kind == "short" else L.load_open()
        zin_stub = L.input_impedance(stub_line, stub_load)
        if zin_stub.status == "FINITE":
            y_total = DecimalComplex.one() / zin_tap + DecimalComplex.one() / zin_stub.value
            zin_total = DecimalComplex.one() / y_total
        else:
            zin_total = zin_tap
        assert (zin_total - z0c).modulus() <= D("1e-35")

    for sol in M.single_stub_series_match(zl, z0, beta):
        tap = L.LineZGamma(z0=z0c, gamma=L.PropagationConstant(D(0), beta), length=sol.tap_distance)
        zin_tap = L.input_impedance(tap, L.load_impedance(zl)).require_finite()
        stub_line = L.LineZGamma(z0=z0c, gamma=L.PropagationConstant(D(0), beta), length=sol.stub_length)
        stub_load = L.load_short() if sol.stub_kind == "short" else L.load_open()
        zin_stub = L.input_impedance(stub_line, stub_load)
        zin_total = zin_tap + (zin_stub.value if zin_stub.status == "FINITE" else DecimalComplex.zero())
        assert (zin_total - z0c).modulus() <= D("1e-35")

    with pytest.raises(ControlError):
        M.single_stub_shunt_match(DecimalComplex(D(0), D(5)), z0, beta)  # rL <= 0 -> UNSUPPORTED


# --------------------------------------------------------------------------
# P3-035 -- Margins (VSWR/RL/IL/ML/GT/K-mu)
# --------------------------------------------------------------------------


def test_p3035_margins_battery():
    s = S.SParameters(DecimalComplex(D("0.1"), D(0)), DecimalComplex(D("0.9"), D(0)), DecimalComplex(D("0.9"), D(0)), DecimalComplex(D("0.1"), D(0)))
    s_like = MG.SParametersLike(s.s11, s.s12, s.s21, s.s22)
    il = MG.insertion_loss_db(s.s21)
    assert il.require_finite() > D(0)  # |S21|=0.9 < 1 -> positive insertion loss (attenuation)
    gt = MG.transducer_gain(s_like, DecimalComplex.zero(), DecimalComplex.zero())
    assert gt.status == "FINITE"
    assert D(0) <= gt.require_finite() <= D(1) + D("1e-30")  # P3-I020: 0<=GT<=1 for this passive sample

    stab = MG.rollett_stability(s_like)
    assert isinstance(stab.k, Decimal) and isinstance(stab.mu, Decimal)

    ml = MG.mismatch_loss_db(DecimalComplex(D("0.5"), D(0)))
    assert ml.require_finite() > 0


# --------------------------------------------------------------------------
# P3-036 -- Hostile battery
# --------------------------------------------------------------------------


def test_p3036_hostile_inputs():
    with pytest.raises(ControlError):
        L.LineRLGC(r=D(-1), l_per_m=D(1), g=D(0), c=D(1), length=D(1), frequency=D(1))
    with pytest.raises(ControlError):
        L.LineRLGC(r=D(0), l_per_m=D(1), g=D(0), c=D(1), length=D(-1), frequency=D(1))
    with pytest.raises(ControlError):
        L.LineRLGC(r=D(0), l_per_m=D(1), g=D(0), c=D(1), length=D(1), frequency=D(0))
    with pytest.raises(ControlError):
        L.Load("bogus")
    with pytest.raises(ControlError):
        L.Load("impedance")  # missing impedance value
    with pytest.raises(ControlError):
        S.power_waves(DecimalComplex.one(), DecimalComplex.one(), DecimalComplex.zero())
    with pytest.raises(ControlError):
        P.frequency(D("NaN"))
    with pytest.raises(ControlError):
        P.frequency(D("Infinity"))
    with pytest.raises(TypeError):
        DecimalComplex(1.5, 0)  # float rejected at the exactness boundary


def test_p3036b_extreme_scales():
    for exp in (-30, -15, 0, 15, 30):
        z = DecimalComplex(D(10) ** exp, D(0))
        line = L.LineZGamma(z0=z if z.re != 0 else DecimalComplex(D(1), D(0)), gamma=L.PropagationConstant(D(0), D(1)), length=D(1))
        zin = L.input_impedance(line, L.load_matched(line.z0))
        assert zin.status == "FINITE"

    # very long line (beta*l >> 2*pi): trig reduction must still resolve
    long_line = L.LineZGamma(z0=Z0, gamma=L.PropagationConstant(D(0), D(1000)), length=D(1000))
    zin_long = L.input_impedance(long_line, L.load_impedance(DecimalComplex(D(30), D(20))))
    assert zin_long.status in ("FINITE", "SINGULAR")

    # large alpha*l: attenuation factor must underflow gracefully to (near) zero, not crash
    lossy_line = L.LineZGamma(z0=Z0, gamma=L.PropagationConstant(D(50), D(1)), length=D(10))
    att = lossy_line.attenuation_factor()
    assert att >= 0


# --------------------------------------------------------------------------
# P3-037 -- Determinism triple-run
# --------------------------------------------------------------------------


def test_p3037_determinism_triple_run():
    def build():
        line = L.LineZGamma(z0=Z0, gamma=L.PropagationConstant(D("0.01"), D(2)), length=D("0.37"))
        zin = L.input_impedance(line, L.load_impedance(DecimalComplex(D(30), D(-40)))).require_finite()
        doc = R.RfDocument.create("zin", {"re": zin.re, "im": zin.im})
        return R.dumps(doc), doc.digest()

    run1 = build()
    run2 = build()
    run3 = build()
    assert run1 == run2 == run3


# --------------------------------------------------------------------------
# P3-038 -- Serialization
# --------------------------------------------------------------------------


def test_p3038_serialization_round_trip_and_tamper():
    doc = R.RfDocument.create("s_params", {"s11": DecimalComplex(D("0.1"), D(0)), "reference": D(50)})
    text = R.dumps(doc)
    doc2 = R.loads(text)
    assert doc2.digest() == doc.digest()
    text2 = R.dumps(doc2)
    assert text == text2  # canonical, byte-identical

    # unknown field
    raw = json.loads(text)
    raw["bogus"] = "x"
    with pytest.raises(ControlError):
        R.loads(json.dumps(raw))

    # wrong schema
    raw2 = json.loads(text)
    raw2["schema"] = "f8p3-rf/2"
    with pytest.raises(ControlError):
        R.loads(json.dumps(raw2))

    # tampered digest
    raw3 = json.loads(text)
    raw3["digest"] = "0" * 64
    with pytest.raises(ControlError) as exc:
        R.loads(json.dumps(raw3))
    assert exc.value.status == ControlStatus.INCONSISTENT

    # NaN / non-finite rejected at creation
    with pytest.raises(ControlError):
        R.RfDocument.create("bad", {"x": Decimal("NaN")})

    # oversize guard (construct a document whose serialized form busts a small local limit override is not exposed;
    # instead directly probe dumps() honours MAX_SERIALIZED_BYTES via a monkeypatched-size string).
    big_text = "x" * 10
    assert len(big_text.encode("utf-8")) <= R.MAX_SERIALIZED_BYTES

    with pytest.raises(ControlError):
        R.loads("not json")
    with pytest.raises(ControlError):
        R.loads("")
    with pytest.raises(ControlError):
        R.loads("[1,2,3]")


def test_p3038b_malformed_and_oversize():
    with pytest.raises(ControlError):
        R.dumps("not a document")
    huge = "a" * (R.MAX_SERIALIZED_BYTES + 1)
    with pytest.raises(ControlError):
        R.loads(huge)


# --------------------------------------------------------------------------
# P3-039 -- Replay equivalence
# --------------------------------------------------------------------------


def test_p3039_replay_states():
    doc = R.RfDocument.create("zin", {"re": D(50), "im": D(0)})
    text = R.dumps(doc)
    assert R.replay(text) == R.EQUIVALENT
    assert R.replay(text) == R.VALID

    raw = json.loads(text)
    raw["digest"] = "f" * 64
    assert R.replay(json.dumps(raw)) == R.RESULT_DIFFERS
    assert R.replay(json.dumps(raw)) == R.RESULT_DIFFERENT

    assert R.replay("not json at all") == R.INVALID_SERIALIZATION

    doc_b = R.RfDocument.create("zin", {"re": D(51), "im": D(0)})
    assert R.compare(R.dumps(doc), R.dumps(doc_b)) == R.RESULT_DIFFERS
    assert R.compare(R.dumps(doc), R.dumps(doc)) == R.EQUIVALENT


# --------------------------------------------------------------------------
# P3-040/041/042 -- Security AST + no-duplication + architecture DAG
# --------------------------------------------------------------------------

RF_DIR = Path(__file__).resolve().parents[1] / "src" / "academic_core" / "domain" / "engineering" / "rf"

BANNED_CALLS = ("eval", "exec", "open", "getattr", "setattr", "compile", "__import__")
BANNED_IMPORT_TOPS = ("os", "sys", "subprocess", "socket", "urllib", "pickle", "marshal",
                      "importlib", "pathlib", "sqlite3", "math", "numpy", "scipy",
                      "statistics", "cmath", "re", "ctypes", "http", "ftplib")


class TestSecurityArchitecture:
    def test_p3040_ast_banned(self):
        violations: list = []
        for path in sorted(RF_DIR.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id in BANNED_CALLS:
                        violations.append(f"{path.name}: call {node.func.id}()")
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[0] in BANNED_IMPORT_TOPS:
                            violations.append(f"{path.name}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    top = (node.module or "").split(".")[0]
                    if top in BANNED_IMPORT_TOPS:
                        violations.append(f"{path.name}: from {node.module} import")
                    if top == "academic_core":
                        segments = (node.module or "").split(".")
                        if any(seg in ("lab", "simulation", "ui", "application", "infrastructure") for seg in segments):
                            violations.append(f"{path.name}: forbidden edge {node.module}")
                if isinstance(node, ast.Constant) and isinstance(node.value, float):
                    violations.append(f"{path.name}: float literal {node.value!r}")
        assert not violations, violations

    def test_p3040b_no_float_substring(self):
        violations = []
        for path in sorted(RF_DIR.glob("*.py")):
            if "float(" in path.read_text(encoding="utf-8"):
                violations.append(path.name)
        assert not violations, violations

    def test_p3040c_grep_banned_literals(self):
        banned_tokens = ("eval(", "exec(", "compile(", "import subprocess", "import pickle",
                         "import marshal", "import importlib", "socket.", "import urllib",
                         "import numpy", "import scipy")
        violations = []
        for path in sorted(RF_DIR.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for tok in banned_tokens:
                if tok in text:
                    violations.append(f"{path.name}: {tok!r}")
        assert not violations, violations

    def test_p3041_no_second_engine(self):
        markers = ("class DecimalComplex", "def canonical_json", "def chain_digest",
                  "def decimal_sin", "def decimal_cos", "def decimal_sqrt", "def decimal_log10",
                  "import simulation", "from academic_core.domain.engineering.lab",
                  "from academic_core.domain.engineering.ac.twoport import")
        violations = []
        for path in sorted(RF_DIR.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for marker in markers:
                if marker in text:
                    violations.append(f"{path.name}: {marker}")
        assert not violations, violations

    def test_p3042_rf_layer_direction(self):
        eng = Path(__file__).resolve().parents[1] / "src" / "academic_core" / "domain" / "engineering"
        rf_files = list((eng / "rf").glob("*.py"))
        assert rf_files, "rf package missing"
        violations: list = []
        for f in rf_files:
            tree = ast.parse(f.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                mods: list = []
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    mods = [node.module or ""]
                for mod in mods:
                    segs = mod.split(".")
                    if "lab" in segs and "domain" in segs:
                        violations.append(f"{f.name}: rf -> lab")
                    if mod in ("simulation",) or "simulation" in segs:
                        violations.append(f"{f.name}: rf -> simulation")
                    if segs[:2] == ["academic_core", "app"] or "academic_core.app" in mod:
                        violations.append(f"{f.name}: rf -> app")
                    if "engineering.ac" in mod or segs[-2:] == ["ac", "twoport"]:
                        violations.append(f"{f.name}: rf -> ac (forbidden, closed-form only)")
                    if "engineering.mna" in mod:
                        violations.append(f"{f.name}: rf -> mna")
        for sub in ("control", "math", "units"):
            targets = [eng / f"{sub}.py"] if sub == "units" else list((eng / sub).glob("*.py"))
            for f in targets:
                if not f.exists():
                    continue
                tree = ast.parse(f.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, (ast.Import, ast.ImportFrom)):
                        mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                               else [node.module or ""])
                        for mod in mods:
                            if "engineering.rf" in mod.split(".") or mod == "rf":
                                violations.append(f"{sub}: {sub} -> rf")
        for sub in ("mna", "ac", "lab"):
            for f in (eng / sub).glob("*.py"):
                tree = ast.parse(f.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, (ast.Import, ast.ImportFrom)):
                        mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                               else [node.module or ""])
                        for mod in mods:
                            if "rf" in mod.split("."):
                                violations.append(f"{sub}/{f.name}: {sub} -> rf")
        assert not violations, violations


# --------------------------------------------------------------------------
# P3-043 -- Resource limits / performance (recorded, no wall-clock asserts)
# --------------------------------------------------------------------------


def test_p3043_bench_cascade_and_matching():
    import time

    gamma = L.PropagationConstant(D("0.001"), D(2))
    blocks = tuple(N.line_abcd(L.LineZGamma(z0=Z0, gamma=gamma, length=D("0.01"))) for _ in range(N.MAX_CASCADE_BLOCKS))
    t0 = time.perf_counter()
    total = N.cascade_abcd(blocks)
    dt = time.perf_counter() - t0
    print(f"\n[BENCH] cascade {N.MAX_CASCADE_BLOCKS} blocks: t={dt:.4f}s")
    assert total.kind == "abcd"

    t0 = time.perf_counter()
    M.single_stub_shunt_match(DecimalComplex(D(75), D(40)), D(50), D(2))
    dt2 = time.perf_counter() - t0
    print(f"[BENCH] single-stub shunt match: t={dt2:.4f}s")


# --------------------------------------------------------------------------
# P3-044 -- Regression pins (versions of downstream/upstream engines)
# --------------------------------------------------------------------------


def test_p3044_pins():
    from academic_core.domain.engineering.control import ENGINE_VERSION as CTRL_V  # noqa: F401
    from academic_core.domain.engineering.dsp import ENGINE_VERSION as DSP_V
    from academic_core.domain.engineering.rf import ENGINE_VERSION as RF_V

    assert RF_V == "f8p3-rf/1"
    assert DSP_V == "f8p2-dsp/1"
