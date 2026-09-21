"""F8-P2 DSP P2-001..P2-032+ (property-first, analytical-first).

Every comparison records reference/actual/abs/rel/tolerance. Reference
hierarchy: ANALYTICAL (hand N=4 DFT, closed Z pairs, alias formula) >
INDEPENDENT HIGH-PRECISION (in-test Taylor, stdlib Context, own
bisection re-solve) > PROPERTY (invariants re-checked on outputs) >
REGRESSION. No test merely executes lines.
"""

from __future__ import annotations

import ast
import time
from decimal import Context, Decimal, localcontext
from pathlib import Path

import pytest

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.control.tf import make_tf as make_tf_s
from academic_core.domain.engineering.dsp import dft as DFT
from academic_core.domain.engineering.dsp import filters as FIL
from academic_core.domain.engineering.dsp import margins_d as MD
from academic_core.domain.engineering.dsp import report as REP
from academic_core.domain.engineering.dsp import sampling as SMP
from academic_core.domain.engineering.dsp import sequences as SEQ
from academic_core.domain.engineering.dsp import ztrans as ZT
from academic_core.domain.engineering.math import (
    DecimalComplex,
    decimal_pi,
    make_context,
)

CTX = make_context()
REF80 = Context(prec=80)
EPS = Decimal("1e-30")


def D(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def JC(re: object, im: object = 0) -> DecimalComplex:
    return DecimalComplex(D(re), D(im))


def rel(actual: Decimal, ref: Decimal) -> Decimal:
    denom = ref.copy_abs()
    if denom < EPS:
        denom = EPS
    return (actual - ref).copy_abs() / denom


def cmod(value: DecimalComplex) -> Decimal:
    return value.modulus()


def seq_of(values, period="0.125"):
    return SEQ.Sequence.create(tuple(D(v) for v in values), D(period))


def indep_tan(x: Decimal) -> Decimal:
    """Independent tangent: in-test Taylor sin/cos at 80 digits (own code)."""
    with localcontext() as ctx:
        ctx.prec = 80
        x = +x
        x2 = +(x * x)
        sine, term, n = +x, +x, 1
        while True:
            term = -(term * x2) / ((2 * n) * (2 * n + 1))
            sine += term
            n += 1
            if abs(term) < Decimal(10) ** (-75) or n > 500:
                break
        cosine, term, n = Decimal(1), Decimal(1), 1
        while True:
            term = -(term * x2) / ((2 * n - 1) * (2 * n))
            cosine += term
            n += 1
            if abs(term) < Decimal(10) ** (-75) or n > 500:
                break
        return +(sine / cosine)


# --------------------------------------------------------------------------
# P2-001 DFT manual N=4 / P2-002 twiddles
# --------------------------------------------------------------------------

class TestDFTManual:
    def test_p2001_hand_n4(self):
        assert DFT.dft(seq_of((1, 0, 0, 0))) == (JC(1), JC(1), JC(1), JC(1))
        assert DFT.dft(seq_of((1, 1, 1, 1))) == (JC(4), JC(0), JC(0), JC(0))
        assert DFT.dft(seq_of((1, -1, 1, -1))) == (JC(0), JC(0), JC(4), JC(0))
        back = DFT.idft((JC(1), JC(2), JC(3), JC(4)))
        refs = (JC("2.5"), JC("-0.5", "-0.5"), JC("-0.5"), JC("-0.5", "0.5"))
        for got, ref in zip(back, refs):
            assert cmod(got - ref) == 0, (got, ref)

    def test_p2002_twiddle_unit(self):
        for size in (8, 64, 1024, 4096):
            for k in range(size):
                assert rel(DFT.twiddle(k, size).modulus(), D(1)) < D("1e-48"), (size, k)
        assert DFT.twiddle(0, 4) == JC(1)
        assert DFT.twiddle(1, 4) == JC(0, -1)
        assert DFT.twiddle(2, 4) == JC(-1)
        assert DFT.twiddle(3, 4) == JC(0, 1)
        with pytest.raises(ControlError):
            DFT.twiddle(0, 0)


# --------------------------------------------------------------------------
# P2-003 FFT=DFT / P2-004 round-trip / P2-005 Parseval
# --------------------------------------------------------------------------

class TestFFTTheorems:
    def _noise64(self):
        return seq_of(tuple(D((n * 37) % 11 - 5) / D(5) for n in range(64)))

    def test_p2003_fft_agrees(self):
        x = self._noise64()
        spec_f = DFT.fft(x.values)
        spec_d = DFT.dft(x.values)
        norm = max(cmod(v) for v in spec_d)
        for a, b in zip(spec_f, spec_d):
            assert cmod(a - b) <= D("1e-40") * (D(1) + norm), (a, b)
        inv = DFT.ifft(spec_f)
        for got, ref in zip(inv, x.values):
            assert cmod(got - JC(ref)) <= D("1e-40") * (D(1) + norm)

    def test_p2004_idft_roundtrip(self):
        for size in (4, 64):
            x = seq_of(tuple(D((n * 13) % 7 - 3) for n in range(size)))
            back = DFT.idft(DFT.dft(x.values))
            norm = max((v.copy_abs() for v in x.values), default=D(1))
            for got, ref in zip(back, x.values):
                assert cmod(got - JC(ref)) <= D("1e-40") * (D(1) + norm)

    def test_p2005_parseval(self):
        x = self._noise64()
        spec = DFT.dft(x.values)
        with localcontext() as ctx:
            ctx.prec = 60
            time_e = sum((+v * +v for v in x.values), Decimal(0))
            freq_e = sum((+(s.re * s.re + s.im * s.im) for s in spec), Decimal(0)) / 64
        assert rel(time_e, freq_e) < D("1e-40"), (time_e, freq_e)
        # Analytic pin: constant 2 (N=8) carries energy 8·4 = 32.
        xc = seq_of((2,) * 8)
        spec_c = DFT.dft(xc.values)
        energy = sum((s.re * s.re + s.im * s.im for s in spec_c), Decimal(0)) / 8
        assert energy == D(32), energy


# --------------------------------------------------------------------------
# P2-006 convolution / P2-007 shift / P2-008 symmetry
# --------------------------------------------------------------------------

class TestSpectralTheorems:
    def test_p2006_circular_convolution(self):
        x = seq_of(tuple(D((n * 3) % 5 - 2) for n in range(16)))
        h = seq_of(tuple(D((n * 7) % 5 - 2) for n in range(16)))
        conv = DFT.circular_convolve(x.values, h.values)
        prod = DFT.dft(conv)
        ref = DFT.dft(x.values)
        refh = DFT.dft(h.values)
        for got, a, b in zip(prod, ref, refh):
            assert cmod(got - a * b) < D("1e-36"), (got, a, b)
        with pytest.raises(ControlError):
            DFT.circular_convolve(x.values, seq_of((1, 2)).values)

    def test_p2007_shift_phase(self):
        x = seq_of(tuple(D((n * 5) % 9 - 4) for n in range(16)))
        ref = DFT.dft(x.values)
        table = tuple(DFT.twiddle(m, 16) for m in range(16))
        shift = 5
        moved = tuple(x.values[(n - shift) % 16] for n in range(16))
        got = DFT.dft(SEQ.Sequence.create(moved, D("0.125")))
        norm = max(cmod(v) for v in ref)
        for k in range(16):
            expect = ref[k] * table[(shift * k) % 16]
            assert cmod(got[k] - expect) <= D("1e-36") * (D(1) + norm), (k, got[k], expect)

    def test_p2008_real_symmetry(self):
        x = seq_of(tuple(D((n * 11) % 13 - 6) for n in range(32)))
        spec = DFT.dft(x.values)
        norm = max(cmod(v) for v in spec)
        for k in range(1, 32):
            assert cmod(spec[32 - k] - spec[k].conjugate()) <= D("1e-40") * (D(1) + norm)
        assert spec[0].im.copy_abs() <= D("1e-40") * (D(1) + norm)
        assert spec[16].im.copy_abs() <= D("1e-40") * (D(1) + norm)


# --------------------------------------------------------------------------
# P2-009 zero padding / P2-010 bins
# --------------------------------------------------------------------------

class TestBinsPadding:
    def test_p2009_zero_padding(self):
        x = seq_of(tuple(D((n * 3) % 7 - 3) for n in range(16)))
        ref = DFT.dft(x.values)
        padded = SEQ.Sequence.create(tuple(x.values) + (D(0),) * 48, D("0.125"))
        long = DFT.dft(padded.values)
        for m in range(16):
            assert cmod(long[4 * m] - ref[m]) < D("1e-45"), (m, long[4 * m], ref[m])
        assert len(long) == 64

    def test_p2010_bins(self):
        assert DFT.frequency_bins(D(8), 8) == tuple(D(k) for k in range(8))
        assert DFT.nyquist_index(8) == 4
        assert DFT.nyquist_index(7) is None
        s = SEQ.Sequence.create((D(1), D(2)), D("0.125"))
        assert s.sample_rate == D(8)
        with pytest.raises(ControlError):
            DFT.frequency_bins(D(-1), 8)


# --------------------------------------------------------------------------
# P2-011 Z pairs / P2-012 ROC / P2-013 H(z) / P2-014 S+T
# --------------------------------------------------------------------------

class TestZTransform:
    def test_p2011_pairs(self):
        assert ZT.z_pair("delta", {}).to_dict() == {
            "num_w": ["1"], "den_w": ["1"], "roc_radius": "0"}
        assert ZT.z_pair("step", {}).to_dict() == {
            "num_w": ["1"], "den_w": ["1", "-1"], "roc_radius": "1"}
        assert ZT.z_pair("geometric", {"a": D("0.5")}).to_dict() == {
            "num_w": ["1"], "den_w": ["1", "-0.5"], "roc_radius": "0.5"}
        assert ZT.z_pair("ramp", {"a": D("0.5")}).to_dict() == {
            "num_w": ["0", "0.5"], "den_w": ["1", "-1.0", "0.25"], "roc_radius": "0.5"}
        with pytest.raises(ControlError) as exc:
            ZT.z_pair("advance", {})
        assert exc.value.status == ControlStatus.UNSUPPORTED

    def test_p2012_roc_exterior(self):
        step = ZT.z_pair("step", {})
        assert step.roc_radius == D(1)
        assert step.evaluate(JC(2)) == JC(2)  # outside ROC: 1/(1-1/2)
        with pytest.raises(ControlError) as exc:
            step.evaluate(JC(1))  # ROC boundary pole
        assert exc.value.status == ControlStatus.SINGULAR
        with pytest.raises(ControlError) as exc:
            step.evaluate(JC(0, 0))
        assert exc.value.status == ControlStatus.SINGULAR

    def test_p2013_hz_direct_sum(self):
        fir = ZT.make_hz((D(1), D("0.5"), D("0.25")), (D(1),))
        assert fir.evaluate(JC(2)) == JC("1.3125")
        with pytest.raises(ControlError):
            ZT.make_hz((D(1), D(2), D(3)), (D(1), D(1)))  # feedback-improper
        with pytest.raises(ControlError):
            ZT.make_hz((D(1),), (D(0), D(1)))  # a_0 = 0

    def test_p2014_s_plus_t(self):
        loop = ZT.make_hz((D(0), D(1)), (D(1), D("-0.5")))
        s_tf = ZT.sensitivity_z(loop)
        t_tf = ZT.complementary_z(loop)
        assert s_tf.den_w == t_tf.den_w
        den = s_tf.den_poly()
        assert s_tf.num_poly().add(t_tf.num_poly()) == den
        for pt in (JC(0, 1), JC(1, 1), JC(-1, 0)):
            total = s_tf.evaluate(pt) + t_tf.evaluate(pt)
            assert cmod(total - JC(1)) < D("1e-40"), pt
        num_d, den_d = ZT.delay_coeffs((D(1),), (D(1), D("-0.5")), 2)
        assert num_d == (D(0), D(0), D(1))
        # Delay identity at coefficient level: w^2·B(w)/A(w) evaluated
        # through the REUSEd P1 Horner (delayed forms may exceed the
        # standalone constructor rule by design).
        from academic_core.domain.engineering.control.poly import make_polynomial
        w = JC(D("0.5"), D("0.5"))
        w0 = JC(1) / w
        num_q, _ = ZT.delay_coeffs((D(0), D(1)), (D(1), D("-0.5")), 2)
        assert num_q == (D(0), D(0), D(0), D(1))
        num_p = make_polynomial(tuple(reversed(num_q)))
        den_p = make_polynomial(tuple(reversed(den_d)))
        expect = num_p.evaluate(w0) / den_p.evaluate(w0)
        assert cmod(expect - loop.evaluate(w) * (w0 * w0)) < D("1e-40")


# --------------------------------------------------------------------------
# P2-015 bilinear preserves / P2-016 prewarp / P2-017 round-trip
# --------------------------------------------------------------------------

class TestBilinear:
    def test_p2015_lhp_to_disc(self):
        proto = make_tf_s((D(1),), (D(1), D(1)))
        res = FIL.bilinear_design(proto, D(8))
        assert res.digital.num_w == (D("0.058823529411764705882352941176470588235294117647059"),
                                     D("0.058823529411764705882352941176470588235294117647059"))
        assert res.digital.den_w[0] == D(1)
        rep = FIL.iir_stability(res.digital, D("0.125"))
        assert rep.verdict == "STABLE" and rep.agreement, rep
        assert rel(rep.poles[0].re, D(15) / D(17)) < D("1e-12"), rep.poles
        assert rep.routh_verdict == "STABLE"
        bad = make_tf_s((D(1),), (D(1), D(-1)))
        bad_d = FIL.bilinear_design(bad, D(8))
        bad_rep = FIL.iir_stability(bad_d.digital, D("0.125"))
        assert bad_rep.verdict == "UNSTABLE" and bad_rep.agreement, bad_rep
        with pytest.raises(ControlError) as exc:
            FIL.bilinear_design(make_tf_s((D(1),), (D(1), D(-16))), D(8))
        assert exc.value.status == ControlStatus.UNSUPPORTED  # pole at s = 2/T

    def test_p2016_prewarp(self):
        from academic_core.domain.engineering.math import decimal_cos as _cos
        from academic_core.domain.engineering.math import decimal_sin as _sin

        proto = make_tf_s((D(1),), (D(1), D(1)))
        omega_d = decimal_pi(CTX) / D(4)  # analog rad/s; protected θ = ω_d·T
        res = FIL.bilinear_design(
            proto, D(8), {"omega_d": omega_d, "omega_a_ref": D(1)})
        assert res.prewarp_applied != ""
        theta = omega_d * D("0.125")
        pt = DecimalComplex(_cos(theta, CTX), _sin(theta, CTX))
        mag = res.digital.evaluate(pt).modulus()
        assert rel(mag, D(1) / D(str(REF80.sqrt(2)))) < D("1e-12"), mag
        half = D("0.125") * omega_d / D(2)
        omega_0 = D(16) * indep_tan(half)
        beta = omega_0 / D(1)
        assert rel(D(dict(res.warp_record)["beta"]), beta) < D("1e-12")
        with pytest.raises(ControlError) as exc:
            FIL.bilinear_design(proto, D(8), {"omega_d": decimal_pi(CTX) / D("0.125"),
                                              "omega_a_ref": D(1)})
        assert exc.value.status == ControlStatus.UNSUPPORTED

    def test_p2017_roundtrip(self):
        proto = make_tf_s((D(1), D(0)), (D(1), D(10), D(35), D(50), D(24)))
        res = FIL.bilinear_design(proto, D(8))
        back = FIL.bilinear_back(res.digital, D("0.125"))
        assert back.den.degree == 4 and back.num.degree <= 4
        for pt in (JC(0, 1), JC(1, 2), JC(2, 1)):
            assert cmod(back.evaluate(pt) - proto.evaluate(pt)) < D("1e-40"), pt


# --------------------------------------------------------------------------
# P2-018 FIR linear phase / group delay / P2-019 IIR / P2-020 SOS
# --------------------------------------------------------------------------

class TestFilters:
    def test_p2018_linear_phase(self):
        rep = FIL.linear_phase_report((D(1), D(2), D(3), D(4), D(4), D(3), D(2), D(1)))
        assert rep.kind == "II" and rep.symmetric, rep
        assert D(rep.group_delay_samples) == D("3.5")
        rep3 = FIL.linear_phase_report((D(1), D(0), D(-1)))
        assert rep3.kind == "III" and D(rep3.group_delay_samples) == D(1)
        rep0 = FIL.linear_phase_report((D(1), D(2), D(1), D(0)))
        assert rep0.kind == "none" and not rep0.symmetric
        tau, _ = FIL.fir_group_delay_at((D(1), D(2), D(3), D(4), D(4), D(3), D(2), D(1)),
                                        D("0.5"))
        assert rel(tau, D("3.5")) < D("1e-6"), tau
        with pytest.raises(ControlError) as exc:
            FIL.fir_group_delay_at((D(1), D(-1)), D(0))
        assert exc.value.status == ControlStatus.UNSUPPORTED

    def test_p2019_iir_verdicts(self):
        stable = ZT.make_hz((D(1),), (D(1), D("-0.5")))
        rep = FIL.iir_stability(stable, D("0.125"))
        assert rep.verdict == "STABLE" and rep.agreement and rep.routh_verdict == "STABLE"
        assert rel(D(rep.roc_radius), D("0.5")) < D("1e-12")
        unstable = ZT.make_hz((D(1),), (D(1), D("-1.5")))
        rep_u = FIL.iir_stability(unstable, D("0.125"))
        assert rep_u.verdict == "UNSTABLE" and rep_u.agreement
        assert rep_u.routh_verdict == "UNSTABLE", rep_u
        from academic_core.domain.engineering.math import decimal_sqrt as _sqrt

        c = _sqrt(D(2)) / D(2)
        marginal = ZT.make_hz((D(1),), (D(1), -D(2) * c, D(1)))
        rep_m = FIL.iir_stability(marginal, D("0.125"))
        assert rep_m.verdict == "MARGINAL" and rep_m.agreement, rep_m
        assert rep_m.routh_verdict == "MARGINAL"

    def test_p2020_sos_order8(self):
        ctx = make_context()
        den_w, num_w = [D(1)], [D(1)]

        def convolve(poly, factor):
            out = [ctx.multiply(poly[0], factor[0])]
            for i in range(1, len(poly) + 1):
                head = ctx.multiply(poly[i], factor[0]) if i < len(poly) else D(0)
                tail = ctx.multiply(poly[i - 1], factor[1])
                out.append(ctx.add(head, tail))
            return out

        for root in [D(2), D(3), D(4), D(5), D(6), D(7), D(8), D(9)]:
            den_w = convolve(den_w, (D(1), ctx.minus(ctx.divide(D(1), root))))
        for index in range(8):
            zroot = ctx.minus(ctx.divide(D(index + 1), D(10)))
            num_w = convolve(num_w, (D(1), ctx.minus(zroot)))
        h = ZT.make_hz(tuple(num_w), tuple(den_w))
        assert h.order == 8
        sos = FIL.sos_decompose(h)
        assert len(sos.sections) == 4, len(sos.sections)
        norm = h.evaluate(JC(0, 1)).modulus()
        for pt in (JC(0, 1), JC(D("0.5"), D("0.5")), JC(D("-0.3"), D("0.2"))):
            diff = cmod(FIL.cascade_evaluate(sos.sections, pt) - h.evaluate(pt))
            assert diff <= D("1e-40") * (D(1) + norm), (pt, diff)


# --------------------------------------------------------------------------
# P2-021 digital margins
# --------------------------------------------------------------------------

class TestMarginsD:
    def _indep_crossings(self, loop):
        ctx = make_context()
        grid = tuple(ctx.divide(ctx.multiply(decimal_pi(ctx), D(i)), D(720))
                     for i in range(721))

        def ev(t):
            from academic_core.domain.engineering.math import decimal_cos as _c
            from academic_core.domain.engineering.math import decimal_sin as _s

            return loop.evaluate(DecimalComplex(_c(t, ctx), _s(t, ctx)))

        gc = pc = None
        prev_t, prev_v, prev_m = grid[0], ev(grid[0]), ev(grid[0]).modulus()
        for t in grid[1:]:
            v, m = ev(t), ev(t).modulus()
            if gc is None and (prev_m - 1 > 0) != (m - 1 > 0):
                lo, hi = prev_t, t
                for _ in range(200):
                    if (hi - lo) / hi <= D("1e-13"):
                        break
                    mid = (lo + hi) / 2
                    if (ev(mid).modulus() - 1 > 0) == (prev_m - 1 > 0):
                        lo = mid
                    else:
                        hi = mid
                gc = (lo + hi) / 2
            if pc is None and prev_v.re < 0 and v.re < 0 and (prev_v.im > 0) != (v.im > 0):
                lo, hi = prev_t, t
                for _ in range(200):
                    if (hi - lo) / hi <= D("1e-13"):
                        break
                    mid = (lo + hi) / 2
                    if (ev(mid).im > 0) == (prev_v.im > 0):
                        lo = mid
                    else:
                        hi = mid
                cand = (lo + hi) / 2
                if ev(cand).re < 0:
                    pc = cand
            prev_t, prev_v, prev_m = t, v, m
        return gc, pc

    def test_p2021_margins_direct(self):
        loop = ZT.make_hz((D(0), D(1)), (D(1), D("-0.5")))
        rep = MD.digital_margins(loop, D("0.125"))
        assert rep.gm_status == "COMPLETED" and rep.pm_status == "COMPLETED", rep
        assert rel(D(rep.gain_margin), D("1.5")) < D("1e-9"), rep
        assert rel(D(rep.theta_pc), decimal_pi(CTX)) < D("1e-12"), rep.theta_pc
        thc, thc_ref = D(rep.theta_gc), self._indep_crossings(loop)[0]
        assert rel(thc, thc_ref) < D("1e-9"), (thc, thc_ref)
        assert rel(D(rep.delay_margin_s),
                   D(rep.delay_margin_samples) * D("0.125")) < D("1e-12")
        assert rep.gm_bracket != () and rep.gc_bracket != ()
        flat = ZT.make_hz((D("0.5"),), (D(1),))
        rep0 = MD.digital_margins(flat, D("0.125"))
        assert rep0.gm_status == "UNSUPPORTED" and rep0.pm_status == "UNSUPPORTED"


# --------------------------------------------------------------------------
# P2-022/023 Nyquist + alias / P2-024 reconstruction
# --------------------------------------------------------------------------

class TestSampling:
    def test_p2022_nyquist(self):
        assert SMP.nyquist_verdict(D(3), D(8)) == "CLEAN"
        assert SMP.nyquist_verdict(D(4), D(8)) == "MARGINAL"
        assert SMP.nyquist_verdict(D(5), D(8)) == "ALIASED"
        assert SMP.nyquist_rate(D(3)) == D(6)
        assert SMP.nyquist_frequency(D(8)) == D(4)

    def test_p2023_alias_closed(self):
        assert SMP.alias_of(D(5), D(8)) == D(3)
        assert SMP.alias_of(D(3), D(8)) == D(3)
        assert SMP.alias_of(D(11), D(8)) == D(3)
        assert SMP.alias_of(D(13), D(8)) == D(3)
        assert SMP.alias_of(D(0), D(8)) == D(0)
        assert SMP.alias_of(D(4), D(8)) == D(4)
        assert SMP.alias_of(D(8), D(8)) == D(0)
        assert SMP.alias_of(D(12), D(8)) == D(4)

    def test_p2024_reconstruction(self):
        x = SEQ.sample_signal("sine", {"freq_hz": D(1), "amplitude": D(1),
                                       "phase_rad": D(0)}, D("0.125"), 64)
        for n in (0, 7, 63):
            t = SMP.sample_times(D("0.125"), 64)[n]
            got = SMP.reconstruct(x, t, 8)
            assert got.node_exact and got.value == str(x.values[n]), (n, got)
        imp = SEQ.sample_signal("impulse", {"index": 3}, D("0.125"), 8)
        mid = SMP.reconstruct(imp, D("0.4375"), 8)
        assert not mid.node_exact and not mid.truncated
        ref = D(2) / decimal_pi(REF80)
        assert rel(D(mid.value), ref) < D("1e-9"), (mid.value, ref)
        tight = SMP.reconstruct(imp, D("0.4375"), 1)
        assert tight.truncated
        assert (D(tight.value) - ref).copy_abs() <= D(tight.tail_bound)
        # Nontrivial truncation on a sine: tight error stays under its bound.
        full = SMP.reconstruct(x, D("0.0625"), 64)
        assert not full.truncated
        near = SMP.reconstruct(x, D("0.0625"), 2)
        assert near.truncated
        assert (D(near.value) - D(full.value)).copy_abs() <= D(near.tail_bound)


# --------------------------------------------------------------------------
# P2-025 limits / P2-026 determinism / P2-027 serde / P2-028 hostile
# --------------------------------------------------------------------------

class TestLimitsDeterminismSerde:
    def test_p2025_battery(self):
        with pytest.raises(ControlError):
            SEQ.Sequence.create((), D("0.125"))
        with pytest.raises(ControlError):
            SEQ.Sequence.create((D(1),), D(0))
        with pytest.raises(ControlError):
            SEQ.Sequence.create((D(1),), D("-1"))
        with pytest.raises(ControlError):
            SEQ.Sequence.create((D("NaN"),), D("0.125"))
        with pytest.raises(ControlError):
            SEQ.Sequence.create((True,), D("0.125"))
        with pytest.raises(ControlError):
            SEQ.Sequence.create((D(1),) * 65537, D("0.125"))
        with pytest.raises(ControlError):
            DFT.dft(SEQ.Sequence.create((D(1),) * 513, D("0.125")))
        with pytest.raises(ControlError) as exc:
            DFT.fft(seq_of((1, 2, 3)))
        assert exc.value.status == ControlStatus.INVALID
        with pytest.raises(ControlError):
            DFT.fft(SEQ.Sequence.create((D(1),) * 8192, D("0.125")))
        with pytest.raises(ControlError):
            ZT.make_hz((D(1), D(2), D(3)), (D(1), D(1)))  # feedback-improper
        fir_ok = ZT.make_hz((D(1), D(2)), (D(1),))  # D-R1: constant-den FIR
        assert fir_ok.order == 0
        with pytest.raises(ControlError):
            ZT.make_hz(tuple([D(1)] * 34), (D(1),))  # order exceeds 32
        with pytest.raises(ControlError):
            ZT.make_hz((D(1),), (D(0), D(1)))
        with pytest.raises(ControlError):
            FIL.bilinear_design(make_tf_s((D(1),), (D(1), D(1))), D(0))
        with pytest.raises(ControlError):
            SEQ.sample_signal("warp", {}, D("0.125"), 8)

    def test_p2026_determinism(self):
        x = SEQ.sample_signal("sine", {"freq_hz": D(2), "amplitude": D(1),
                                       "phase_rad": D(0)}, D("0.125"), 64)
        runs = [DFT.fft(x.values) for _ in range(3)]
        first = [(str(v.re), str(v.im)) for v in runs[0]]
        for run in runs[1:]:
            assert [(str(v.re), str(v.im)) for v in run] == first
        doc = REP.DspDocument.create("spectrum", {"n": "64"})
        assert REP.dumps(doc) == REP.dumps(doc) == REP.dumps(doc)
        a = REP.DspDocument.create("spectrum", {"b": "2", "a": "1"})
        b = REP.DspDocument.create("spectrum", {"a": "1", "b": "2"})
        assert a.digest() == b.digest()

    def test_p2027_serde_replay(self):
        doc = REP.DspDocument.create("margins", {"gm": "1.5"}, {"engine": "x"})
        assert REP.loads(REP.dumps(doc)).digest() == doc.digest()
        text = REP.dumps(doc)
        tampered = text.replace("1.5", "1.6")
        assert REP.compare(text, tampered) == REP.INVALID_SERIALIZATION
        with pytest.raises(ControlError) as exc:
            REP.loads(tampered)
        assert exc.value.status == ControlStatus.INCONSISTENT
        other = REP.DspDocument.create("margins", {"gm": "9.9"})
        assert REP.compare(doc, other) == REP.RESULT_DIFFERS
        assert REP.compare(text, text.replace("f8p2-dsp/1", "f8p2-dsp/2")) == REP.VERSION_MISMATCH
        assert REP.compare(text, text.replace("f8p2-dsp/1", "f8o-metrology/1")) == REP.SCHEMA_MISMATCH
        assert REP.compare(text, "not json") == REP.INVALID_SERIALIZATION
        assert REP.replay(text) == REP.EQUIVALENT

    def test_p2028_hostile(self):
        with pytest.raises(ControlError):
            REP.loads("")
        with pytest.raises(ControlError):
            REP.DspDocument.create("", {"a": "1"})
        with pytest.raises(ControlError):
            REP.DspDocument.create("x", {"v": D("NaN")})
        with pytest.raises(ControlError):
            SMP.reconstruct(SEQ.sample_signal(
                "sine", {"freq_hz": D(1), "amplitude": D(1), "phase_rad": D(0)},
                D("0.125"), 8), D(-1), 8)
        cseq = SEQ.Sequence.create(
            (DecimalComplex(D(1), D(1)), DecimalComplex(D(2), D(0))), D("0.125"))
        with pytest.raises(ControlError) as exc:
            SMP.reconstruct(cseq, D("0.125"), 8)
        assert exc.value.status == ControlStatus.UNSUPPORTED
        with pytest.raises(ControlError):
            FIL.sos_decompose(ZT.make_hz((D(1), D(1)), (D(1),)))
        with pytest.raises(ControlError):
            SMP.to_sequence_uniform(((D(0), D("0.2")), (D(1), D(2))), D("0.125"))


# --------------------------------------------------------------------------
# P2-029 AST security / P2-030 no-duplication / P2-031 bench / P2-032 pins
# --------------------------------------------------------------------------

DSP_DIR = Path(__file__).resolve().parents[1] / "src" / "academic_core" / "domain" / "engineering" / "dsp"

BANNED_CALLS = ("eval", "exec", "open", "getattr", "setattr", "compile", "__import__")
BANNED_IMPORT_TOPS = ("os", "sys", "subprocess", "socket", "urllib", "pickle", "marshal",
                      "importlib", "pathlib", "sqlite3", "math", "numpy", "scipy",
                      "statistics", "cmath", "re", "ctypes", "http", "ftplib")


class TestSecurityArchitecture:
    def test_p2029_ast_banned(self):
        violations: list = []
        for path in sorted(DSP_DIR.glob("*.py")):
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
                        if any(seg in ("lab", "simulation", "ui", "application",
                                       "infrastructure") for seg in segments):
                            violations.append(f"{path.name}: forbidden edge {node.module}")
                if isinstance(node, ast.Constant) and isinstance(node.value, float):
                    violations.append(f"{path.name}: float literal {node.value!r}")
        assert not violations, violations

    def test_p2029b_no_float_substring(self):
        violations = []
        for path in sorted(DSP_DIR.glob("*.py")):
            if "float(" in path.read_text(encoding="utf-8"):
                violations.append(path.name)
        assert not violations, violations

    def test_p2030_no_second_engine(self):
        markers = ("def durand_kerner_roots", "def routh_of_poly", "def canonical_json",
                   "def chain_digest", "class TransferFunctionTF", "jacobi",
                   "run_monte_carlo", "import simulation",
                   "from academic_core.domain.engineering.lab",
                   "from academic_core.domain.engineering.metrology.o2",
                   "from academic_core.domain.engineering.metrology.o3")
        violations = []
        for path in sorted(DSP_DIR.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for marker in markers:
                if marker in text:
                    violations.append(f"{path.name}: {marker}")
        assert not violations, violations

    def test_p2031_bench(self):
        for size, tag in ((64, "n64"), (1024, "n1024")):
            x = SEQ.sample_signal("sine", {"freq_hz": D(2), "amplitude": D(1),
                                           "phase_rad": D(0)}, D("0.125"), size)
            t0 = time.perf_counter()
            spec = DFT.fft(x.values)
            dt = time.perf_counter() - t0
            print(f"\n[BENCH] FFT {tag}: t={dt:.2f}s bins={len(spec)}")
            assert len(spec) == size
        proto = make_tf_s((D(1),), tuple([D(1)] + [D(0)] * 31 + [D(1)]))
        t0 = time.perf_counter()
        res = FIL.bilinear_design(proto, D(8))
        print(f"[BENCH] bilinear order 32: t={time.perf_counter() - t0:.2f}s")
        assert res.digital.order == 32
        den32 = tuple([D(1)] + [D(0)] * 31 + [D("0.5")])
        t0 = time.perf_counter()
        h32 = ZT.make_hz((D(1),), den32)
        val = h32.evaluate(JC(0, 1))
        print(f"[BENCH] TFZ order 32 direct: t={time.perf_counter() - t0:.2f}s")
        assert h32.order == 32 and val.modulus() > 0

    def test_p2031b_fft_4096(self):
        x = SEQ.sample_signal("sine", {"freq_hz": D(2), "amplitude": D(1),
                                       "phase_rad": D(0)}, D("0.125"), 4096)
        t0 = time.perf_counter()
        spec = DFT.fft(x.values)
        dt = time.perf_counter() - t0
        print(f"\n[BENCH] FFT n4096: t={dt:.1f}s")
        assert len(spec) == 4096
        assert cmod(spec[1024]) > D(1000), cmod(spec[1024])

    def test_p2032_pins(self):
        from academic_core.domain.engineering.control import ENGINE_VERSION as P1V
        from academic_core.domain.engineering.dsp import ENGINE_VERSION as P2V
        from academic_core.domain.engineering.metrology import report as OM

        assert P1V == "f8p1-control/1" and P2V == "f8p2-dsp/1"
        assert OM.SCHEMA == "f8o-metrology/1" and REP.SCHEMA == "f8p2-dsp/1"
        assert DFT.twiddle(1, 4) == JC(0, -1)
        assert SMP.alias_of(D(5), D(8)) == D(3)
