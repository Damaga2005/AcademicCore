"""F8-P1 Evans root locus (NEW).

Branches satisfy angle(L) = +/-180 (2q+1) deg with |K| = 1/|L(s)|
for the loop TF L(s). Real-axis segments, asymptote angles, centroid,
breakaway dK/ds = 0 on the real axis and jw-axis crossings with gain.
Closed-loop poles per gain come from the same DK core (no second solver).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.control.poly import (
    Polynomial,
    durand_kerner_roots,
    make_polynomial,
)
from academic_core.domain.engineering.control.tf import (
    TransferFunctionTF,
    tf_to_zpk,
)
from academic_core.domain.engineering.math import (
    DecimalComplex,
    decimal_atan2,
    decimal_pi,
    make_context,
)

MAX_LOCUS_GAINS = 2000
LOCUS_ABS_TOL = Decimal("1e-24")
LOCUS_REL_TOL = Decimal("1e-9")
ANGLE_TOL_DEG = Decimal("1e-9")


def _deg_of(rad: Decimal) -> Decimal:
    ctx = make_context()
    pi = decimal_pi(ctx)
    return ctx.divide(ctx.multiply(rad, Decimal(180)), pi)


def _angle_deg(value: DecimalComplex) -> Decimal:
    ctx = make_context()
    if value.is_zero_exact():
        return Decimal(0)
    rad = decimal_atan2(value.im, value.re, ctx)
    return _deg_of(rad)


def _modulus(value: DecimalComplex) -> Decimal:
    return value.modulus()


@dataclass(frozen=True)
class AsymptoteReport:
    n_minus_m: int
    centroid_re: str
    centroid_im: str
    angles_deg: tuple
    detail: str = ""


def asymptote_report(loop: TransferFunctionTF) -> AsymptoteReport:
    if not isinstance(loop, TransferFunctionTF):
        raise ControlError(ControlStatus.INVALID, "asymptotes need a loop TF")
    zpk = tf_to_zpk(loop)
    n = len(zpk.poles)
    m = len(zpk.zeros)
    rel = n - m
    ctx = make_context()
    if rel <= 0:
        return AsymptoteReport(n_minus_m=rel, centroid_re="", centroid_im="",
                               angles_deg=(), detail="no asymptotes")
    sum_p_re = Decimal(0)
    sum_p_im = Decimal(0)
    for p in zpk.poles:
        sum_p_re = ctx.add(sum_p_re, p.re)
        sum_p_im = ctx.add(sum_p_im, p.im)
    sum_z_re = Decimal(0)
    sum_z_im = Decimal(0)
    for z in zpk.zeros:
        sum_z_re = ctx.add(sum_z_re, z.re)
        sum_z_im = ctx.add(sum_z_im, z.im)
    diff_re = ctx.subtract(sum_p_re, sum_z_re)
    diff_im = ctx.subtract(sum_p_im, sum_z_im)
    centroid_re = ctx.divide(diff_re, Decimal(rel))
    centroid_im = ctx.divide(diff_im, Decimal(rel))
    angles: list = []
    for q in range(rel):
        angles.append(str(ctx.divide(Decimal(180 * (2 * q + 1)), Decimal(rel))))
    return AsymptoteReport(
        n_minus_m=rel,
        centroid_re=str(centroid_re),
        centroid_im=str(centroid_im),
        angles_deg=tuple(angles),
        detail="ok",
    )


@dataclass(frozen=True)
class AngleCheck:
    angle_deg: str
    ok: bool
    residual_deg: str


def angle_condition(loop: TransferFunctionTF, s: DecimalComplex) -> AngleCheck:
    if not isinstance(loop, TransferFunctionTF):
        raise ControlError(ControlStatus.INVALID, "angle check needs a loop TF")
    if not isinstance(s, DecimalComplex):
        raise ControlError(ControlStatus.INVALID, "angle check needs a DecimalComplex point")
    try:
        value = loop.evaluate(s)
    except ControlError as exc:
        raise ControlError(exc.status, "angle check at pole") from exc
    ang = _angle_deg(value)
    ctx = make_context()
    # Distance to the nearest odd multiple of 180 deg.
    half = ctx.divide(ang, Decimal(180))
    nearest = int(half.to_integral_value(rounding=ROUND_HALF_UP))
    nearest_dec = Decimal(nearest)
    residual = (ang - ctx.multiply(nearest_dec, Decimal(180))).copy_abs()
    ok = (nearest % 2 == 1) and residual <= ANGLE_TOL_DEG
    return AngleCheck(angle_deg=str(ang), ok=bool(ok), residual_deg=str(residual))


def magnitude_gain(loop: TransferFunctionTF, s: DecimalComplex) -> Decimal:
    if not isinstance(loop, TransferFunctionTF):
        raise ControlError(ControlStatus.INVALID, "magnitude gain needs a loop TF")
    if not isinstance(s, DecimalComplex):
        raise ControlError(ControlStatus.INVALID, "magnitude gain needs a DecimalComplex point")
    try:
        value = loop.evaluate(s)
    except ControlError as exc:
        raise ControlError(exc.status, "magnitude gain at pole") from exc
    mag = value.modulus()
    if mag == 0:
        raise ControlError(ControlStatus.SINGULAR, "zero loop magnitude")
    ctx = make_context()
    return ctx.divide(Decimal(1), mag)


@dataclass(frozen=True)
class LocusPoint:
    gain: str
    poles: tuple
    residuals: tuple
    ok: bool


def _check_residual(loop: TransferFunctionTF, gain: Decimal, root: DecimalComplex) -> Decimal:
    ctx = make_context()
    try:
        lval = loop.evaluate(root)
    except ControlError:
        return Decimal("1e30")
    kl = lval * DecimalComplex(gain, Decimal(0))
    one = DecimalComplex(Decimal(1), Decimal(0))
    res = (one + kl).modulus()
    _ = ctx
    return res


def _residual_ok(loop: TransferFunctionTF, gain: Decimal, root: DecimalComplex) -> tuple:
    try:
        lval = loop.evaluate(root)
    except ControlError:
        return False, Decimal("1e30")
    mag = lval.modulus()
    ctx = make_context()
    cap = Decimal(1) if mag < 1 else mag
    bound = ctx.add(LOCUS_ABS_TOL, ctx.multiply(LOCUS_REL_TOL, cap))
    res = _check_residual(loop, gain, root)
    return res <= bound, res


def locus_point(loop: TransferFunctionTF, gain: Decimal) -> LocusPoint:
    if not isinstance(loop, TransferFunctionTF):
        raise ControlError(ControlStatus.INVALID, "locus needs a loop TF")
    if isinstance(gain, bool) or not isinstance(gain, Decimal):
        raise ControlError(ControlStatus.INVALID, "locus gain must be Decimal")
    if not gain.is_finite() or gain <= 0:
        raise ControlError(ControlStatus.INVALID, "locus gain K > 0 required")
    ctx = make_context()
    scaled = loop.num.scale(gain)
    char = loop.den.add(scaled)
    if all(c == 0 for c in char.coeffs):
        raise ControlError(ControlStatus.SINGULAR, "locus singular (1 + K L = 0 identically)")
    res = durand_kerner_roots(char)
    if res.status != ControlStatus.COMPLETED:
        raise ControlError(res.status, "locus DK did not converge")
    ok_all = True
    residuals: list = []
    for root in res.roots:
        ok, res_val = _residual_ok(loop, gain, root)
        residuals.append(str(res_val))
        if not ok:
            ok_all = False
    _ = ctx
    return LocusPoint(gain=str(gain), poles=res.roots, residuals=tuple(residuals), ok=ok_all)


def locus(loop: TransferFunctionTF, gains: tuple) -> tuple:
    if not isinstance(loop, TransferFunctionTF):
        raise ControlError(ControlStatus.INVALID, "locus needs a loop TF")
    if not isinstance(gains, tuple) or len(gains) == 0:
        raise ControlError(ControlStatus.INVALID, "locus needs a non-empty gain tuple")
    if len(gains) > MAX_LOCUS_GAINS:
        raise ControlError(ControlStatus.INVALID, "locus gain budget exceeded")
    ordered = list(gains)
    for g in ordered:
        if isinstance(g, bool) or not isinstance(g, Decimal):
            raise ControlError(ControlStatus.INVALID, "locus gains must be Decimal")
        if not g.is_finite() or g <= 0:
            raise ControlError(ControlStatus.INVALID, "locus gains K > 0 required")
    ordered_sorted = sorted(ordered)
    return tuple(locus_point(loop, g) for g in ordered_sorted)


@dataclass(frozen=True)
class BreakawayReport:
    points: tuple
    detail: str = ""


def breakaway_points(loop: TransferFunctionTF) -> BreakawayReport:
    """Real-axis breakaway/break-in: roots of D'N - D N' with K > 0 on locus."""
    if not isinstance(loop, TransferFunctionTF):
        raise ControlError(ControlStatus.INVALID, "breakaway needs a loop TF")
    d = loop.den
    n = loop.num
    if n.degree == 0 and d.degree <= 1:
        return BreakawayReport(points=(), detail="no interior breakaway possible")
    e_poly = d.derivative().multiply(n).add(d.multiply(n.derivative()).scale(Decimal(-1)))
    if all(c == 0 for c in e_poly.coeffs):
        return BreakawayReport(points=(), detail="degenerate dK/ds")
    res = durand_kerner_roots(e_poly)
    if res.status != ControlStatus.COMPLETED:
        return BreakawayReport(points=(), detail="candidate core non-converged")
    ctx = make_context()
    imag_tol = Decimal("1e-12")
    accepted: list = []
    for cand in res.roots:
        if cand.im.copy_abs() > imag_tol:
            continue
        s_real = ctx.plus(cand.re)
        s_point = DecimalComplex(s_real, Decimal(0))
        try:
            nval = n.evaluate_decimal(s_real)
            dval = d.evaluate_decimal(s_real)
        except ControlError:
            continue
        if nval == 0:
            continue
        kval = ctx.divide(ctx.minus(dval), nval)
        if kval <= 0:
            continue
        check = angle_condition(loop, s_point)
        # Real-axis locus membership: angle must be an odd multiple of 180.
        # Breakaway candidates with tiny angle residuals pass; the gate
        # demands membership, magnitude K > 0 and the dK/ds root itself.
        ang_ok = check.ok
        if not ang_ok:
            # Allow real-axis candidates whose angle is within a relaxed but
            # still strict band (DK residue can shift the angle slightly).
            try:
                if Decimal(check.residual_deg) > Decimal("1e-6"):
                    continue
            except Exception:
                continue
        accepted.append((s_real, kval))
    accepted_sorted = tuple(sorted(accepted, key=lambda kv: str(kv[0])))
    rendered = tuple((str(s), str(k)) for s, k in accepted_sorted)
    return BreakawayReport(points=rendered, detail="ok")


@dataclass(frozen=True)
class JwCrossing:
    omega: str
    gain: str
    detail: str = ""


def jw_crossings(loop: TransferFunctionTF) -> tuple:
    """jw-axis crossings: phase(L(jw)) = -180 deg via bisection, K = 1/|L|."""
    if not isinstance(loop, TransferFunctionTF):
        raise ControlError(ControlStatus.INVALID, "crossings need a loop TF")
    from academic_core.domain.engineering.control.margins import phase_crossover_bisection
    found = phase_crossover_bisection(loop)
    if not found:
        return ()
    out: list = []
    for omega, gain in found:
        out.append(JwCrossing(omega=str(omega), gain=str(gain), detail="bisection"))
    return tuple(out)
