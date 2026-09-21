"""F8-P1 SISO LTI control P-001..P-037+ (property-first, analytical-first).

Every comparison records reference/actual/abs/rel/tolerance. Reference
hierarchy: ANALYTICAL (closed forms, exact Fraction/Routh identities) >
INDEPENDENT HIGH-PRECISION (stdlib Context exp/sqrt, in-test bisection,
F8-L oracle) > PROPERTY (invariants re-checked on outputs) > REGRESSION.
No test merely executes lines.
"""

from __future__ import annotations

import ast
import time
from decimal import Context, Decimal, localcontext
from pathlib import Path

import pytest

from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.control import locus as LOC
from academic_core.domain.engineering.control import margins as MAR
from academic_core.domain.engineering.control import pid as PID
from academic_core.domain.engineering.control import poly as POLY
from academic_core.domain.engineering.control import report as REP
from academic_core.domain.engineering.control import response as RESP
from academic_core.domain.engineering.control import stability as STAB
from academic_core.domain.engineering.control import statespace as SSP
from academic_core.domain.engineering.control import tf as TF
from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.math import (
    DecimalComplex,
    decimal_sqrt,
    make_context,
)
from academic_core.domain.engineering.math.logarithm import decimal_nth_root
from academic_core.domain.engineering.math.trig import decimal_pi, decimal_sin
from academic_core.domain.engineering.mna import (
    TransientConfig,
    TransientStatus,
    solve_transient,
)
from academic_core.domain.engineering.units import parse_quantity as Q

CTX = make_context()
REF80 = Context(prec=80)
EPS = Decimal("1e-30")


def D(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def TF_of(num, den):
    return TF.make_tf(tuple(D(v) for v in num), tuple(D(v) for v in den))


def rel(actual: Decimal, ref: Decimal) -> Decimal:
    denom = ref.copy_abs()
    if denom < EPS:
        denom = EPS
    return (actual - ref).copy_abs() / denom


def JC(re: object, im: object = 0) -> DecimalComplex:
    return DecimalComplex(D(re), D(im))


def indep_exp(x: Decimal) -> Decimal:
    """Independent exponential: stdlib context implementation (C code path)."""
    return +REF80.exp(+x)


def indep_sqrt(x: Decimal) -> Decimal:
    return +REF80.sqrt(+x)


def indep_pi() -> Decimal:
    """Independent pi: certified trig constant (shared convention, not the SUT)."""
    return decimal_pi(REF80)


# --------------------------------------------------------------------------
# P-001 Horner exact + polynomial battery
# --------------------------------------------------------------------------

class TestHorner:
    def test_p001_first_order_at_j(self):
        h = TF_of((1,), (1, 1))
        got = h.evaluate(JC(0, 1))
        assert got.re == D("0.5"), got
        assert got.im == D("-0.5"), got

    def test_p001b_degrees_and_shapes(self):
        # Degree 0: constant.
        p0 = POLY.make_polynomial((D(7),))
        assert p0.degree == 0
        assert p0.evaluate_decimal(D(3)) == D(7)
        # Degree 1 / 2 vs direct power-sum reference.
        for coeffs in [(2, -3), (1, 0, -4), (5, 0, 0, 1)]:
            p = POLY.make_polynomial(tuple(D(c) for c in coeffs))
            x = D("1.25")
            expect = sum(D(c) * (x ** (len(coeffs) - 1 - i)) for i, c in enumerate(coeffs))
            assert p.evaluate_decimal(x) == expect
        # Degree 32 accepted.
        p32 = POLY.make_polynomial(tuple([D(1)] + [D(0)] * 31 + [D(1)]))
        assert p32.degree == 32
        assert p32.evaluate_decimal(D(1)) == D(2)
        # Degree 33 rejected.
        with pytest.raises(ControlError) as exc:
            POLY.make_polynomial(tuple([D(1)] + [D(0)] * 33))
        assert exc.value.status == ControlStatus.INVALID

    def test_p001c_zero_large_small_complex(self):
        zero = POLY.make_polynomial((D(0),))
        assert zero.evaluate_decimal(D(5)) == D(0)
        big = POLY.make_polynomial((D("1e30"), D("1e30")))
        assert big.evaluate_decimal(D(2)) == D("3e30")
        small = POLY.make_polynomial((D("1e-30"), D("1e-30")))
        assert small.evaluate_decimal(D(2)) == D("3e-30")
        p = POLY.make_polynomial((D(1), D(2), D(1)))
        got = p.evaluate(JC(1, 1))
        # (1+j)^2 + 2(1+j) + 1 = (2j) + (2+2j) + 1 = 3 + 4j.
        assert (got.re, got.im) == (D(3), D(4)), got

    def test_p001d_poly_algebra(self):
        ctx = make_context()
        p = POLY.make_polynomial((D(1), D(2), D(1)))
        assert p.derivative().coeffs == (D(2), D(2))
        assert p.scale(D(3)).coeffs == (D(3), D(6), D(3))
        assert p.normalize_monic().coeffs == p.coeffs
        q = POLY.make_polynomial((D(1), D(1)))
        assert (p.add(q)).coeffs == (D(1), D(3), D(2))
        assert (q.multiply(q)).coeffs == (D(1), D(2), D(1))
        assert p == POLY.make_polynomial((D(1), D(2), D(1)))
        assert p.leading == D(1) and p.order == 2
        _ = ctx


# --------------------------------------------------------------------------
# P-002 TF algebra / P-003 S+T
# --------------------------------------------------------------------------

class TestTFAlgebra:
    def test_p002_series_parallel_feedback(self):
        h1 = TF_of((1,), (1, 1))
        h2 = TF_of((1,), (1, 2))
        s = TF.series(h1, h2)
        assert s.num.coeffs == (D(1),)
        assert s.den.coeffs == (D(1), D(3), D(2)), s.den.coeffs
        pl = TF.parallel(h1, h2)
        assert pl.num.coeffs == (D(2), D(3)), pl.num.coeffs
        assert pl.den.coeffs == (D(1), D(3), D(2))
        cl = TF.feedback(h1)
        assert cl.num.coeffs == (D(1),)
        assert cl.den.coeffs == (D(1), D(2)), cl.den.coeffs
        # Numeric cross-check at s = j1: series product identity.
        w = JC(0, 1)
        assert (s.evaluate(w) - h1.evaluate(w) * h2.evaluate(w)).modulus() == 0

    def test_p003_s_plus_t_identity(self):
        loop = TF_of((1,), (1, 1, 0))
        s_tf = TF.sensitivity(loop)
        t_tf = TF.complementary(loop)
        # Symbolic identity: same denominator, numerators sum to it.
        assert s_tf.den == t_tf.den
        assert s_tf.num.add(t_tf.num) == s_tf.den
        # Numeric identity at three points (evaluation rounds at prec 50).
        for pt in (JC(0, 1), JC(1, 2), JC(-3, 0)):
            total = s_tf.evaluate(pt) + t_tf.evaluate(pt)
            assert (total - DecimalComplex(D(1), D(0))).modulus() < D("1e-40"), pt
        # Degenerate loop L = 0: S = 1, T = 0.
        zero_loop = TF.TransferFunctionTF(
            num=POLY.make_polynomial((D(0),)),
            den=POLY.make_polynomial((D(1), D(1))),
        )
        assert TF.sensitivity(zero_loop).num.coeffs == (D(1), D(1))
        assert TF.complementary(zero_loop).num.coeffs == (D(0),)

    def test_p003b_eval_singular_at_pole(self):
        h = TF_of((1,), (1, 1))
        with pytest.raises(ControlError) as exc:
            h.evaluate(JC(-1, 0))
        assert exc.value.status == ControlStatus.SINGULAR


# --------------------------------------------------------------------------
# P-004 second-order poles / P-005 ZPK
# --------------------------------------------------------------------------

class TestRootsZPK:
    def test_p004_canonical_second_order(self):
        wn, zeta = D(2), D("0.25")
        h = TF_of((wn * wn,), (1, 2 * zeta * wn, wn * wn))
        zpk = TF.tf_to_zpk(h)
        assert len(zpk.poles) == 2
        re_ref = -(zeta * wn)
        im_ref = wn * indep_sqrt(D(1) - zeta * zeta)
        by_im = sorted(zpk.poles, key=lambda z: z.im)
        assert rel(by_im[0].re, re_ref) < D("1e-12")
        assert rel(-by_im[0].im, im_ref) < D("1e-12")
        assert rel(by_im[1].im, im_ref) < D("1e-12")

    def test_p004b_conjugation_pairing(self):
        h = TF_of((1,), (1, 0, 1))
        res = POLY.durand_kerner_roots(h.den)
        assert res.status == ControlStatus.COMPLETED
        val = POLY.validate_roots(h.den, res)
        assert val.count_ok and val.residuals_ok and val.pairing_ok, val
        assert val.n_roots == val.n_degree == 2

    def test_p005_zpk_roundtrip(self):
        h = TF_of((2, 4), (1, 4, 3))
        zpk = TF.tf_to_zpk(h)
        assert zpk.gain == D(2)
        assert len(zpk.zeros) == 1 and len(zpk.poles) == 2
        back = TF.zpk_to_tf(zpk)
        for got, ref in zip(back.num.coeffs, h.num.coeffs):
            assert rel(got, ref) < D("1e-12"), (got, ref)
        for got, ref in zip(back.den.coeffs, h.den.coeffs):
            assert rel(got, ref) < D("1e-12"), (got, ref)
        # ZPK evaluation agrees with TF evaluation off singularities.
        pt = JC(0, 1)
        assert (zpk.evaluate(pt) - h.evaluate(pt)).modulus() < D("1e-24")


# --------------------------------------------------------------------------
# P-006..P-008 Routh
# --------------------------------------------------------------------------

class TestRouth:
    def test_p006_stable_exact_table(self):
        h = TF_of((1,), (1, 6, 11, 6))
        r = STAB.routh_of_tf(h)
        assert r.verdict == "STABLE"
        assert r.sign_changes == 0 and r.rhp_count == 0
        assert r.first_column == ("1", "6", "10", "6"), r.first_column
        assert not r.used_auxiliary and not r.used_epsilon

    def test_p007_unstable_two_rhp(self):
        h = TF_of((1,), (1, 0, -7, 6))
        r = STAB.routh_of_tf(h)
        assert r.verdict == "UNSTABLE"
        assert r.rhp_count == 2, r
        inv = STAB.pole_inventory(h)
        assert inv.agreement and inv.rhp_dk == 2, inv
        assert inv.status == ControlStatus.COMPLETED

    def test_p008_auxiliary_marginal(self):
        h = TF_of((1,), (1, 2, 1, 2))
        r = STAB.routh_of_tf(h)
        assert r.verdict == "MARGINAL", r
        assert r.used_auxiliary, r
        inv = STAB.pole_inventory(h)
        assert inv.routh.verdict == "MARGINAL"

    def test_p008b_first_column_zero_tagged(self):
        # s^4 + 2 s^3 + s^2 + 2 s + 1: second-row pivot is zero while the
        # row is not identically zero -> explicit epsilon substitution.
        h = TF_of((1,), (1, 2, 1, 2, 1))
        r = STAB.routh_of_tf(h)
        assert r.used_epsilon is True, r
        assert "epsilon" in r.detail, r.detail


# --------------------------------------------------------------------------
# P-009 Wilkinson-like
# --------------------------------------------------------------------------

class TestWilkinson:
    def test_p009_backward_gate_honest(self):
        ctx = make_context()
        coeffs = [D(1)]
        for k in range(1, 11):
            root = D(-k)
            nxt = [D(0)] * (len(coeffs) + 1)
            for i, c in enumerate(coeffs):
                nxt[i] = ctx.add(nxt[i], c)
                nxt[i + 1] = ctx.subtract(nxt[i + 1], ctx.multiply(c, root))
            coeffs = nxt
        poly = POLY.make_polynomial(tuple(ctx.plus(c) for c in coeffs))
        res = POLY.durand_kerner_roots(poly)
        norm = max(c.copy_abs() for c in poly.coeffs)
        tol = D("1e-30") * (D(1) + norm)
        if res.status == ControlStatus.COMPLETED:
            assert all(e <= tol for e in res.backward_errors)
            assert len(res.roots) == 10
            r = STAB.routh_of_poly(poly)
            assert r.verdict == "STABLE" and r.rhp_count == 0
        else:
            assert res.status in (ControlStatus.DIVERGED, ControlStatus.MAX_ITERATIONS)
            assert res.diagnostic != ""


# --------------------------------------------------------------------------
# P-010..P-014 Evans locus
# --------------------------------------------------------------------------

class TestLocus:
    def test_p010_real_axis_segments(self):
        loop = TF_of((1, 2), (1, 1, 0))
        assert LOC.angle_condition(loop, JC(-3, 0)).ok is True
        assert LOC.angle_condition(loop, JC(D("-1.5"), 0)).ok is False
        assert LOC.angle_condition(loop, JC(D("-0.5"), 0)).ok is True

    def test_p011_asymptotes(self):
        loop = TF_of((1,), (1, 1, 0))  # n - m = 2
        rep = LOC.asymptote_report(loop)
        assert rep.n_minus_m == 2
        assert D(rep.centroid_re) == D("-0.5"), rep
        assert tuple(sorted(rep.angles_deg)) == ("270", "90"), rep.angles_deg
        # n - m = 1 -> single 180 deg asymptote, centroid -3.
        loop1 = TF_of((1, 0), (1, 3, 2))
        rep1 = LOC.asymptote_report(loop1)
        assert rep1.n_minus_m == 1 and rep1.angles_deg == ("180",), rep1
        assert D(rep1.centroid_re) == D(-3), rep1
        # n - m = 0 -> no asymptotes.
        loop0 = TF_of((1, 3, 2), (1, 5, 6))
        rep0 = LOC.asymptote_report(loop0)
        assert rep0.n_minus_m == 0 and rep0.angles_deg == ()

    def test_p012_breakaway_closed(self):
        loop = TF_of((1,), (1, 1, 0))
        rep = LOC.breakaway_points(loop)
        assert len(rep.points) == 1, rep
        s_str, k_str = rep.points[0]
        assert rel(D(s_str), D("-0.5")) < D("1e-9"), rep
        assert rel(D(k_str), D("0.25")) < D("1e-9"), rep
        # Closed form with zero: s = -2 +- sqrt(2), K = 3 -+ 2 sqrt(2).
        loop2 = TF_of((1, 2), (1, 1, 0))
        rep2 = LOC.breakaway_points(loop2)
        assert len(rep2.points) == 2, rep2
        s2 = indep_sqrt(D(2))
        refs = sorted([D(-2) + s2, D(-2) - s2], key=str)
        gots = sorted([D(s) for s, _ in rep2.points], key=str)
        for got, ref in zip(gots, refs):
            assert rel(got, ref) < D("1e-9"), (got, ref)

    def test_p013_jw_crossing_and_ku(self):
        plant = TF_of((1,), (1, 3, 2, 0))
        point = PID.ultimate_gain(plant)
        # Routh-exact reference: aux row 3 s^2 + K -> K = 6, w^2 = 2.
        assert rel(D(point.ku), D(6)) < D("1e-9"), point
        wu = D(point.omega_u)
        assert rel(wu * wu, D(2)) < D("1e-9"), point
        assert rel(D(point.period_u), D(2) * indep_pi() / wu) < D("1e-12"), point
        # Routh cross-check: K = 6 closes the loop marginally.
        char_loop = TF_of((6,), (1, 3, 2, 0))
        cl = TF.feedback(char_loop)
        assert STAB.routh_of_tf(cl).verdict == "MARGINAL"
        # Z-N table on the Routh-exact Ku.
        zn = PID.ziegler_nichols(D(6), D(point.period_u), "PID")
        assert D(zn.kp) == D("3.6"), zn
        # Divisions round under the working context: tolerance, not text equality.
        assert rel(D(zn.ti), D(point.period_u) / D(2)) < D("1e-12"), zn
        assert rel(D(zn.td), D(point.period_u) / D(8)) < D("1e-12"), zn

    def test_p014_locus_residual(self):
        loop = TF_of((1,), (1, 3, 2, 0))
        gains = tuple(D(k) for k in ("0.5", "2", "5"))
        pts = LOC.locus(loop, gains)
        assert len(pts) == 3
        for pt, k in zip(pts, gains):
            assert pt.ok is True, pt
            kk = D(pt.gain)
            assert kk == k
            for root, res_str in zip(pt.poles, pt.residuals):
                lval = loop.evaluate(root)
                bound = D("1e-24") + D("1e-9") * max(D(1), lval.modulus())
                assert D(res_str) <= bound, (root, res_str)


# --------------------------------------------------------------------------
# P-015..P-017 margins
# --------------------------------------------------------------------------

class TestMargins:
    def _indep_crossovers(self, loop):
        """Independent re-solve: bisection on |L| - 1 and Im(L) (own code)."""
        with localcontext() as ctx:
            ctx.prec = 60
            ratio = decimal_nth_root(D(10), 40, ctx)
            freqs = [D("1e-6")]
            while freqs[-1] < D("1e6"):
                nxt = freqs[-1] * ratio
                freqs.append(+nxt)
            freqs[-1] = D("1e6")
        los = freqs
        gc = pc = None
        prev_w = los[0]
        prev_v = loop.evaluate(JC(0, prev_w))
        prev_m = prev_v.modulus()
        for w in los[1:]:
            v = loop.evaluate(JC(0, w))
            m = v.modulus()
            if gc is None and (prev_m - 1 > 0) != (m - 1 > 0):
                lo, hi = prev_w, w
                for _ in range(200):
                    if (hi - lo) / hi <= D("1e-13"):
                        break
                    mid = (lo + hi) / 2
                    if (loop.evaluate(JC(0, mid)).modulus() - 1 > 0) == (prev_m - 1 > 0):
                        lo = mid
                    else:
                        hi = mid
                gc = (lo + hi) / 2
            if pc is None and prev_v.re < 0 and v.re < 0 and (prev_v.im > 0) != (v.im > 0):
                lo, hi = prev_w, w
                for _ in range(200):
                    if (hi - lo) / hi <= D("1e-13"):
                        break
                    mid = (lo + hi) / 2
                    vm = loop.evaluate(JC(0, mid))
                    if (vm.im > 0) == (prev_v.im > 0):
                        lo = mid
                    else:
                        hi = mid
                cand = (lo + hi) / 2
                if loop.evaluate(JC(0, cand)).re < 0:
                    pc = cand
            prev_w, prev_v, prev_m = w, v, m
        return gc, pc

    def test_p015_margins_direct(self):
        loop = TF_of(("2.7",), (1, 3, 2, 0))
        rep = MAR.margins(loop)
        assert rep.gm_status == "COMPLETED" and rep.pm_status == "COMPLETED", rep
        wgc, wpc = D(rep.omega_gc), D(rep.omega_pc)
        # Defining properties re-checked on the reported points.
        assert rel(loop.evaluate(JC(0, wgc)).modulus(), D(1)) < D("1e-12")
        vpc = loop.evaluate(JC(0, wpc))
        assert vpc.re < 0 and vpc.im.copy_abs() < D("1e-9"), vpc
        assert rel(D(rep.gain_margin) * vpc.modulus(), D(1)) < D("1e-9")
        # Independent re-solve agreement.
        igc, ipc = self._indep_crossovers(loop)
        assert igc is not None and ipc is not None
        assert rel(wgc, igc) < D("1e-9"), (wgc, igc)
        assert rel(wpc, ipc) < D("1e-9"), (wpc, ipc)
        assert rep.gm_bracket != () and rep.gc_bracket != ()
        lo, hi = (D(v) for v in rep.gc_bracket)
        assert lo <= wgc <= hi

    def test_p016_no_crossover_unsupported(self):
        rep = MAR.margins(TF_of((1,), (1, 1)))
        assert rep.gm_status == "UNSUPPORTED" and rep.pm_status == "UNSUPPORTED", rep
        assert rep.gain_margin == "" and rep.phase_margin_deg == ""

    def test_p017_delay_margin(self):
        loop = TF_of(("2.7",), (1, 3, 2, 0))
        rep = MAR.margins(loop)
        pm = D(rep.phase_margin_deg)
        wgc = D(rep.omega_gc)
        pm_rad = pm * indep_pi() / D(180)
        assert rel(D(rep.delay_margin_s), pm_rad / wgc) < D("1e-12"), rep


# --------------------------------------------------------------------------
# P-018 Z-N / P-019 closed loop
# --------------------------------------------------------------------------

class TestPID:
    def test_p018_table_exact(self):
        zn_p = PID.ziegler_nichols(D(6), D(4), "P")
        assert D(zn_p.kp) == D(3) and zn_p.ti == "" and zn_p.td == ""
        zn_pi = PID.ziegler_nichols(D(6), D(4), "PI")
        assert D(zn_pi.kp) == D("2.7"), zn_pi
        assert rel(D(zn_pi.ti), D(4) / D("1.2")) < D("1e-12")
        zn_pid = PID.ziegler_nichols(D(6), D(4), "PID")
        assert D(zn_pid.kp) == D("3.6") and D(zn_pid.ti) == D(2) and D(zn_pid.td) == D("0.5")
        assert D(zn_pid.ki) == D("1.8") and D(zn_pid.kd) == D("1.8")
        with pytest.raises(ControlError):
            PID.ziegler_nichols(D(6), D(4), "PD")

    def test_p018b_forms_separated(self):
        par = PID.pid_parallel(D(1), D(2), D(3))
        assert (par.kp, par.ki, par.kd) == (D(1), D(2), D(3))
        ideal = PID.pid_ideal(D(2), D(4), D(1))
        assert ideal.ki == D(2) / D(4) and ideal.kd == D(2) * D(1)
        sform = PID.pid_series(D(2), D(4), D(1))
        assert sform.ki == D(2) / D(4) and sform.kd == D(2) * D(1)
        # Derivative-free converts to TF exactly; pure-D does not.
        pi_tf = PID.pid_parallel(D(1), D(2), D(0)).as_tf()
        assert pi_tf.num.coeffs == (D(1), D(2))
        with pytest.raises(ControlError) as exc:
            par.as_tf()
        assert exc.value.status == ControlStatus.UNSUPPORTED

    def test_p019_closed_loop_stable(self):
        plant = TF_of((1,), (1, 1))
        comp = PID.pid_parallel(D(2), D(2), D(0))
        cl = PID.closed_loop(plant, comp)
        assert cl.num.coeffs == (D(2), D(2)), cl.num.coeffs
        assert cl.den.coeffs == (D(1), D(3), D(2)), cl.den.coeffs
        assert STAB.routh_of_tf(cl).verdict == "STABLE"
        inv = STAB.pole_inventory(cl)
        assert inv.status == ControlStatus.COMPLETED
        assert all(z.re < 0 for z in inv.poles)


# --------------------------------------------------------------------------
# P-020..P-022 state space
# --------------------------------------------------------------------------

class TestStateSpace:
    def test_p020_tf_ss_roundtrip(self):
        h = TF_of((1, 1), (1, 3, 2))
        ss = SSP.tf_to_ss(h)
        assert ss.order == 2
        back = SSP.ss_to_tf(ss)
        assert back.num.coeffs == h.num.coeffs, back.num.coeffs
        assert back.den.coeffs == h.den.coeffs, back.den.coeffs

    def test_p020b_ss_tf_ss_equivalence(self):
        ss = SSP.make_statespace(
            ((D(0), D(1)), (D(-2), D(-3))),
            ((D(0),), (D(1),)),
            ((D(1), D(1)),),
            ((D(0),),),
        )
        h1 = SSP.ss_to_tf(ss)
        ss2 = SSP.tf_to_ss(h1)
        h2 = SSP.ss_to_tf(ss2)
        assert h1.num.coeffs == h2.num.coeffs and h1.den.coeffs == h2.den.coeffs
        for pt in (JC(0, 1), JC(1, 0), JC(2, 3)):
            assert (h1.evaluate(pt) - h2.evaluate(pt)).modulus() == 0

    def test_p021_ranks(self):
        ss = SSP.tf_to_ss(TF_of((1,), (1, 3, 2)))
        assert SSP.ctrb_rank(ss) == 2 and SSP.obsv_rank(ss) == 2
        dead_b = SSP.make_statespace(
            ((D(-1), D(0)), (D(0), D(-2))),
            ((D(0),), (D(0),)),
            ((D(1), D(1)),),
            ((D(0),),),
        )
        assert SSP.ctrb_rank(dead_b) == 0
        blind_c = SSP.make_statespace(
            ((D(-1), D(0)), (D(0), D(-2))),
            ((D(1),), (D(1),)),
            ((D(0), D(0)),),
            ((D(0),),),
        )
        assert SSP.obsv_rank(blind_c) == 0

    def test_p022_eigenvalues(self):
        ss = SSP.make_statespace(
            ((D(0), D(1)), (D(-2), D(-3))),
            ((D(0),), (D(1),)),
            ((D(1), D(0)),),
            ((D(0),),),
        )
        eig = sorted(SSP.ss_eigenvalues(ss), key=lambda z: str(z.re))
        # String sort puts '-1...' before '-2...'; compare as a set.
        got = sorted([e.re for e in eig])
        assert rel(got[1], D(-1)) < D("1e-12") and rel(got[0], D(-2)) < D("1e-12")
        assert all(e.im.copy_abs() < D("1e-12") for e in eig)

    def test_p020c_identity_at_point(self):
        # H(s) = C (sI - A)^-1 B + D checked via 2x2 closed form (independent).
        ss = SSP.tf_to_ss(TF_of((3,), (1, 2, 1)))
        s = JC(0, 1)
        a, b, c, d = ss.a, ss.b, ss.c, ss.d
        m00 = DecimalComplex(s.re - a[0][0], s.im)
        m01 = DecimalComplex(-a[0][1], D(0))
        m10 = DecimalComplex(-a[1][0], D(0))
        m11 = DecimalComplex(s.re - a[1][1], s.im)
        det = m00 * m11 - m01 * m10
        inv00, inv01 = m11 / det, -m01 / det
        inv10, inv11 = -m10 / det, m00 / det
        x0 = inv00 * b[0][0] + inv01 * b[1][0]
        x1 = inv10 * b[0][0] + inv11 * b[1][0]
        h_val = c[0][0] * x0 + c[0][1] * x1 + DecimalComplex(d[0][0], D(0))
        ref = SSP.ss_to_tf(ss).evaluate(s)
        assert (h_val - ref).modulus() < D("1e-24"), (h_val, ref)


# --------------------------------------------------------------------------
# P-023..P-027 temporal response
# --------------------------------------------------------------------------

class TestResponse:
    def test_p023_first_order_step(self):
        k, tau, t = D(5), D(2), D(3)
        got = RESP.first_order_step(k, tau, t)
        ref = k * (D(1) - indep_exp(-t / tau))
        assert rel(got, ref) < D("1e-9"), (got, ref)
        h = TF_of((5,), (2, 1))
        curve = RESP.step_response(h, (t,))
        assert rel(curve.values[0], ref) < D("1e-9"), curve.values

    def test_p024_second_order_metrics(self):
        wn, zeta = D(5), D("0.3")
        met = RESP.second_order_metrics(wn, zeta)
        assert met.regime == "underdamped"
        disc = D(1) - zeta * zeta
        po_ref = indep_exp(-indep_pi() * zeta / indep_sqrt(disc))
        assert rel(D(met.overshoot), po_ref) < D("1e-9"), met
        tp_ref = indep_pi() / (wn * indep_sqrt(disc))
        assert rel(D(met.peak_time), tp_ref) < D("1e-9"), met
        # Settling approximation band (sanctioned approx, zeta = 0.3).
        ts_form = D(4) / (zeta * wn)
        assert rel(D(met.settling_2pct), ts_form) < D("1e-12")
        h = TF_of((wn * wn,), (1, 2 * zeta * wn, wn * wn))
        curve = RESP.step_response(h, tuple(D(i) / D(100) for i in range(401)))
        peak = max(curve.values)
        assert rel(peak - D(1), D(met.overshoot)) < D("0.02"), (peak, met)
        settle = ts_form
        tail = [v for t, v in zip(curve.times, curve.values) if t >= settle * D("1.2")]
        assert tail and all((v - D(1)).copy_abs() <= D("0.02") for v in tail)

    def test_p025_step_vs_f8l(self):
        # RC charge: R = 1k, C = 1uF, tau = 1ms, 0 -> 5V step at t0 = 1ms.
        c = Circuit("rc_chg")
        c.add(Component("V1", "V", Q("5 V"), {"+": "n1", "-": "0"},
                        parameters={"wave": {"type": "step", "v1": Q("0 V"),
                                             "v2": Q("5 V"), "t0": Decimal("0.001")}}))
        c.add(Component("R1", "R", Q("1 kohm"), {"1": "n1", "2": "out"}))
        c.add(Component("C1", "C", Q("1 uF"), {"1": "out", "2": "0"},
                        parameters={"ic": Q("0 V")}))
        sol = solve_transient(c, TransientConfig(
            method="TR", tstop=Decimal("0.006"), h_init=Decimal("0.00005"),
            h_min=Decimal("1E-12"), h_max=Decimal("0.0005"),
            reltol=Decimal("1E-4"), abstol=Decimal("1E-6")))
        assert sol.status == TransientStatus.COMPLETED, sol.status
        v = sol.node_trajectory("out")
        assert v is not None and v[-1] == v[-1]
        h = TF_of((5,), (D("0.001"), 1))
        ctrl = RESP.step_response(h, (D("0.005"),))
        assert rel(v[-1], ctrl.values[0]) <= D("0.01"), (v[-1], ctrl.values[0])

    def test_p026_impulse_real(self):
        h = TF_of((4,), (1, 1, 4))
        ts = tuple(D(i) / D(10) for i in range(11))
        res = RESP.impulse_response(h, ts)
        assert all(isinstance(v, Decimal) for v in res.values)
        # Closed form: (wn/sqrt(1-z^2)) e^{-z wn t} sin(wd t), wn=2, z=0.25,
        # with an independent in-test sine (Taylor, 80-digit context).
        wn, zeta = D(2), D("0.25")
        disc = D(1) - zeta * zeta
        wd = wn * indep_sqrt(disc)
        t = D("0.5")
        with localcontext() as ctx:
            ctx.prec = 80
            x = +(wd * t)
            total, term, n = +x, +x, 1
            x2 = +(x * x)
            while True:
                term = -(term * x2) / ((2 * n) * (2 * n + 1))
                total += term
                n += 1
                if abs(term) < Decimal(10) ** (-75) or n > 500:
                    break
            sine = +total
        ref = (wn / indep_sqrt(disc)) * indep_exp(-zeta * wn * t) * sine
        assert rel(RESP.impulse_response(h, (t,)).values[0], ref) < D("1e-9")
        # Property: impulse = time derivative of step (central differences).
        hh = D("1e-6")
        tp, tm = t + hh, t - hh
        deriv = (RESP.step_response(h, (tp,)).values[0]
                 - RESP.step_response(h, (tm,)).values[0]) / (D(2) * hh)
        assert rel(RESP.impulse_response(h, (t,)).values[0], deriv) < D("1e-4")

    def test_p027_final_value_gated(self):
        h = TF_of((1,), (1, 1, 0))  # pole at the origin
        res = RESP.step_response(h, (D(1), D(2)))
        assert "final-value-blocked" in res.tags, res.tags
        good = TF_of((1,), (1, 1))
        res2 = RESP.step_response(good, (D(1),))
        assert any(t.startswith("final-value-ok") for t in res2.tags), res2.tags

    def test_p026b_double_pole_step(self):
        h = TF_of((1,), (1, 2, 1))
        got = RESP.step_response(h, (D(1),)).values[0]
        ref = D(1) - D(2) * indep_exp(D(-1))
        assert rel(got, ref) < D("1e-9"), (got, ref)


# --------------------------------------------------------------------------
# P-028 cancellation
# --------------------------------------------------------------------------

class TestCancellation:
    def test_p028_three_verdicts(self):
        exact = TF_of((1, 1), (1, 3, 2))  # zero -1 cancels pole -1
        assert TF.cancellation_report(exact).verdict == "exact cancellation"
        near = TF.TransferFunctionTF(
            num=POLY.make_polynomial((D(1), D("1.000000000001"))),
            den=POLY.make_polynomial((D(1), D(3), D(2))),
        )
        assert TF.cancellation_report(near).verdict == "numerical near-cancellation"
        far = TF_of((1, 5), (1, 3, 2))
        assert TF.cancellation_report(far).verdict == "no cancellation"
        assert TF.RHO_CANCEL == D("1e-9")


# --------------------------------------------------------------------------
# P-029/030 hostile batteries
# --------------------------------------------------------------------------

class TestHostile:
    def test_p029_invalid_battery(self):
        with pytest.raises(ControlError):
            POLY.make_polynomial(())
        with pytest.raises(ControlError):
            POLY.make_polynomial((D(0), D(1)))
        with pytest.raises(ControlError):
            TF_of((1, 1), (1,))  # improper
        with pytest.raises(ControlError):
            TF_of((1,), (5,))  # constant denominator
        with pytest.raises(ControlError):
            TF_of((1,), (0,))  # zero denominator
        with pytest.raises(ControlError):
            POLY.make_polynomial((Decimal("NaN"), D(1)))
        with pytest.raises(ControlError):
            POLY.make_polynomial((Decimal("Infinity"), D(1)))
        with pytest.raises(ControlError):
            POLY.make_polynomial((True, D(1)))
        for bad in (None, "x", D(1)):
            with pytest.raises(ControlError):
                TF.feedback(bad)  # type: ignore[arg-type]
        # Feedback singular: Df Dr + Nf Nr = 0 identically.
        # fwd = (s+1)/(s+2), ret = -(s+2)/(s+1): closed den = 0 polynomial.
        with pytest.raises(ControlError) as exc:
            TF.feedback(TF_of((1, 1), (1, 2)), TF_of((-1, -2), (1, 1)))
        assert exc.value.status == ControlStatus.SINGULAR

    def test_p030_gain_battery(self):
        loop = TF_of((1,), (1, 1, 0))
        for bad in (D(0), D(-1)):
            with pytest.raises(ControlError) as exc:
                LOC.locus(loop, (bad,))
            assert exc.value.status == ControlStatus.INVALID
        with pytest.raises(ControlError):
            LOC.locus(loop, ())
        with pytest.raises(ControlError):
            LOC.locus_point(loop, D(-2))
        with pytest.raises(ControlError):
            RESP.step_response(loop, ())
        with pytest.raises(ControlError):
            RESP.step_response(TF_of((1,), (1, 1)), (D(-1),))
        with pytest.raises(ControlError):
            RESP.first_order_step(D(1), D(0), D(1))
        with pytest.raises(ControlError):
            SSP.make_statespace(((D(1), D(2)), (D(3),)), (((D(1),),)), (((D(1), D(0)),)), (((D(0),),)))


# --------------------------------------------------------------------------
# P-031 determinism
# --------------------------------------------------------------------------

class TestDeterminism:
    def test_p031_triple_run(self):
        h = TF_of((1,), (1, 3, 2, 0))
        runs = [POLY.durand_kerner_roots(h.den) for _ in range(3)]
        first = [(str(z.re), str(z.im)) for z in runs[0].roots]
        for run in runs[1:]:
            assert [(str(z.re), str(z.im)) for z in run.roots] == first
        doc = REP.ControlDocument.create("tf", {"num": ["1"], "den": ["1", "3", "2", "0"]})
        assert REP.dumps(doc) == REP.dumps(doc) == REP.dumps(doc)
        assert doc.digest() == REP.loads(REP.dumps(doc)).digest()
        # Insertion order invariance.
        a = REP.ControlDocument.create("tf", {"b": "2", "a": "1"})
        b = REP.ControlDocument.create("tf", {"a": "1", "b": "2"})
        assert a.digest() == b.digest()


# --------------------------------------------------------------------------
# P-032 serialization / replay
# --------------------------------------------------------------------------

class TestSerialization:
    def _doc(self):
        return REP.ControlDocument.create(
            "margins", {"gm": "2.222", "pm": "53.4"},
            {"engine": "f8p1-control/1"})

    def test_p032_roundtrip(self):
        doc = self._doc()
        assert REP.loads(REP.dumps(doc)).digest() == doc.digest()

    def test_p032_tamper(self):
        text = REP.dumps(self._doc())
        tampered = text.replace("2.222", "2.223")
        assert tampered != text
        # Tampered digest: unparsable as a trusted document (F8-O precedent).
        assert REP.compare(text, tampered) == REP.INVALID_SERIALIZATION
        with pytest.raises(ControlError) as exc:
            REP.loads(tampered)
        assert exc.value.status == ControlStatus.INCONSISTENT
        # Two valid but different documents differ honestly.
        other = REP.ControlDocument.create("margins", {"gm": "9.99", "pm": "1.0"})
        assert REP.compare(self._doc(), other) == REP.RESULT_DIFFERS

    def test_p032_mismatch(self):
        text = REP.dumps(self._doc())
        other_version = text.replace("f8p1-control/1", "f8p1-control/2")
        assert REP.compare(text, other_version) == REP.VERSION_MISMATCH
        other_family = text.replace("f8p1-control/1", "f8o-metrology/1")
        assert REP.compare(text, other_family) == REP.SCHEMA_MISMATCH
        assert REP.compare(text, "not json") == REP.INVALID_SERIALIZATION
        assert REP.compare(self._doc(), self._doc()) == REP.EQUIVALENT
        assert REP.replay(text) == REP.EQUIVALENT


# --------------------------------------------------------------------------
# P-033 hostile misc
# --------------------------------------------------------------------------

class TestHostileMisc:
    def test_p033_battery(self):
        with pytest.raises(ControlError):
            PID.pid_ideal(D(1), D(0), D(1))
        with pytest.raises(ControlError):
            PID.ziegler_nichols(D(-1), D(1), "PID")
        with pytest.raises(ControlError) as exc:
            PID.ultimate_gain(TF_of((1,), (1, 1)))
        assert exc.value.status == ControlStatus.UNSUPPORTED
        with pytest.raises(ControlError):
            TF.tf_to_zpk(TF.TransferFunctionTF(
                num=POLY.make_polynomial((D(0),)),
                den=POLY.make_polynomial((D(1), D(1)))))
        with pytest.raises(ControlError):
            STAB.routh_of_poly(POLY.make_polynomial((D(0),)))
        with pytest.raises(ControlError):
            POLY.durand_kerner_roots(POLY.make_polynomial((D(0),)))
        with pytest.raises(ControlError):
            REP.loads("")
        with pytest.raises(ControlError):
            REP.ControlDocument.create("", {"a": "1"})
        with pytest.raises(ControlError):
            TF.make_tf((D(1),), ())


# --------------------------------------------------------------------------
# P-034 security AST / P-035 no-duplication
# --------------------------------------------------------------------------

CONTROL_DIR = Path(__file__).resolve().parents[1] / "src" / "academic_core" / "domain" / "engineering" / "control"

BANNED_CALLS = ("eval", "exec", "open", "getattr", "setattr", "compile", "__import__")
BANNED_IMPORT_TOPS = ("os", "sys", "subprocess", "socket", "urllib", "pickle", "marshal",
                      "importlib", "pathlib", "sqlite3", "math", "numpy", "scipy",
                      "statistics", "cmath", "re", "ctypes", "http", "ftplib")


class TestSecurity:
    def test_p034_ast_banned(self):
        violations: list = []
        for path in sorted(CONTROL_DIR.glob("*.py")):
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

    def test_p034_no_float_substring(self):
        violations = []
        for path in sorted(CONTROL_DIR.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            if "float(" in text:
                violations.append(path.name)
        assert not violations, violations

    def test_p035_no_second_engine(self):
        markers = ("def analyze_bode", "def frequency_response", "def solve_transient",
                   "def run_monte_carlo", "def evaluate_gum", "def solve_nonlinear",
                   "jacobi", "import simulation", "from academic_core.application",
                   "from academic_core.infrastructure")
        violations = []
        for path in sorted(CONTROL_DIR.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for marker in markers:
                if marker in text:
                    violations.append(f"{path.name}: {marker}")
        assert not violations, violations


# --------------------------------------------------------------------------
# P-036 benchmarks (recorded, no wall-clock asserts)
# --------------------------------------------------------------------------

class TestBenchmarks:
    def test_p036_recorded(self):
        ctx = make_context()
        for n, tag in ((2, "n2"), (10, "n10")):
            coeffs = [D(1)]
            for k in range(1, n + 1):
                root = D(-k)
                nxt = [D(0)] * (len(coeffs) + 1)
                for i, c in enumerate(coeffs):
                    nxt[i] = ctx.add(nxt[i], c)
                    nxt[i + 1] = ctx.subtract(nxt[i + 1], ctx.multiply(c, root))
                coeffs = nxt
            t0 = time.perf_counter()
            res = POLY.durand_kerner_roots(POLY.make_polynomial(tuple(coeffs)))
            dt = time.perf_counter() - t0
            print(f"\n[BENCH] DK {tag}: status={res.status.value} iters={res.iterations} t={dt:.2f}s")
            assert res.status == ControlStatus.COMPLETED
        loop = TF_of((1,), (1, 3, 2, 0))
        t0 = time.perf_counter()
        pts = LOC.locus(loop, tuple(D(k) / D(10) for k in range(1, 21)))
        print(f"[BENCH] locus G=20: t={time.perf_counter() - t0:.2f}s ok={all(p.ok for p in pts)}")
        assert all(p.ok for p in pts)
        t0 = time.perf_counter()
        rep = MAR.margins(loop)
        print(f"[BENCH] margins: t={time.perf_counter() - t0:.2f}s gm={rep.gain_margin}")
        assert rep.gm_status == "COMPLETED"

    def test_p036_degree_32(self):
        ctx = make_context()
        coeffs = [D(1)]
        for k in range(32):
            root = -(D(1) + D(k) / D(8))
            nxt = [D(0)] * (len(coeffs) + 1)
            for i, c in enumerate(coeffs):
                nxt[i] = ctx.add(nxt[i], c)
                nxt[i + 1] = ctx.add(nxt[i + 1], ctx.multiply(c, root))
            coeffs = nxt
        t0 = time.perf_counter()
        res = POLY.durand_kerner_roots(
            POLY.make_polynomial(tuple(ctx.plus(c) for c in coeffs)))
        dt = time.perf_counter() - t0
        print(f"\n[BENCH] DK n=32: status={res.status.value} iters={res.iterations} t={dt:.1f}s")
        assert res.status == ControlStatus.COMPLETED
        assert len(res.roots) == 32


# --------------------------------------------------------------------------
# P-037 regression pins
# --------------------------------------------------------------------------

class TestRegressionPins:
    def test_p037_certified_surfaces(self):
        from academic_core.domain.engineering.math import WORKING_PRECISION
        from academic_core.domain.engineering.metrology import report as OM

        assert WORKING_PRECISION == 50
        assert OM.SCHEMA == "f8o-metrology/1"
        assert REP.SCHEMA == "f8p1-control/1"
        from academic_core.domain.engineering.mna import transient as TR

        assert TR.ENGINE_VERSION == "f8l-transient/1.0"
        assert TR.MAX_TRANSIENT_STEPS == 100000
        h = TF_of((1,), (1, 1))
        assert h.evaluate(JC(0, 1)).re == D("0.5")
