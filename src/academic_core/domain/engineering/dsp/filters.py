"""F8-P2 FIR/IIR filters + bilinear design + SOS (NEW).

Bilinear design is the P1→P2 bridge: a P1 continuous prototype H(s)
maps coefficient-exactly to H(z) through s = c·(1−w)/(1+w), c = 2/T,
with optional prewarp of one protected cutoff. IIR stability uses NO
second criterion: poles from the REUSEd P1 DK core with a |·| ladder,
cross-checked by the inverse bilinear map plus REUSEd exact Routh —
disagreement is INCONSISTENT (P1 inventory pattern). SOS cascades pair
conjugates canonically (REUSEd DK, deterministic order).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.control.poly import (
    Polynomial,
    durand_kerner_roots,
    make_polynomial,
)
from academic_core.domain.engineering.control.stability import routh_of_poly
from academic_core.domain.engineering.control.tf import TransferFunctionTF, make_tf
from academic_core.domain.engineering.dsp.ztrans import (
    TransferFunctionZ,
    _as_ascending,
    _as_decimal,
)
from academic_core.domain.engineering.math import (
    DecimalComplex,
    decimal_atan2,
    decimal_cos,
    decimal_pi,
    decimal_sin,
    make_context,
)

MAX_SOS_SECTIONS = 16
ON_CIRCLE_TOL = Decimal("1e-12")
MULTI_TOL = Decimal("1e-9")
SOS_REAL_TOL = Decimal("1e-24")
PAIR_TOL = Decimal("1e-24")
GROUP_TOL = Decimal("1e-6")


def _check_period(value: object) -> Decimal:
    t = _as_decimal(value, "sampling period")
    if t <= 0:
        raise ControlError(ControlStatus.INVALID, "sampling period T > 0 required")
    return t


def _pow_poly(base: Polynomial, power: int, ctx) -> Polynomial:
    result = make_polynomial((Decimal(1),))
    for _ in range(power):
        result = result.multiply(base)
    _ = ctx
    return result


def _s_to_w_coeffs(s_num: tuple, s_den: tuple, c: Decimal) -> tuple:
    """Bilinear s → w substitution (descending s-polys → descending w-polys).

    s = c·(1−w)/(1+w): term d_j·s^{n−j} becomes
    d_j·c^{n−j}·(1−w)^{n−j}·(1+w)^j, summed over j.
    """
    ctx = make_context()
    n = len(s_den) - 1
    m = len(s_num) - 1
    one_minus = make_polynomial((Decimal(-1), Decimal(1)))
    one_plus = make_polynomial((Decimal(1), Decimal(1)))

    def convert(coeffs: tuple, degree: int) -> Polynomial:
        acc: Polynomial | None = None
        for j, d_j in enumerate(coeffs):
            power_s = degree - j
            if d_j == 0:
                continue
            term = _pow_poly(one_minus, power_s, ctx).multiply(
                _pow_poly(one_plus, j, ctx))
            scale = d_j
            for _ in range(power_s):
                scale = ctx.multiply(scale, c)
            term = term.scale(scale)
            acc = term if acc is None else acc.add(term)
        if acc is None:
            return make_polynomial((Decimal(0),))
        return acc

    return convert(s_num, m), convert(s_den, n)


def _w_to_s_coeffs(w_num_asc: tuple, w_den_asc: tuple, c: Decimal) -> tuple:
    """Inverse bilinear w → s substitution (ascending w → descending s).

    w = (c−s)/(c+s): with common degree N,
    B'(s) = Σ b_k·(c−s)^k·(c+s)^{N−k} (same for A').
    """
    ctx = make_context()
    n = len(w_den_asc) - 1
    c_minus = make_polynomial((Decimal(-1), c))
    c_plus = make_polynomial((Decimal(1), c))

    def convert(asc: tuple) -> Polynomial:
        acc: Polynomial | None = None
        for k, b_k in enumerate(asc):
            if b_k == 0:
                continue
            term = _pow_poly(c_minus, k, ctx).multiply(_pow_poly(c_plus, n - k, ctx))
            term = term.scale(b_k)
            acc = term if acc is None else acc.add(term)
        if acc is None:
            return make_polynomial((Decimal(0),))
        return acc

    return convert(w_num_asc), convert(w_den_asc)


def _decimal_tan(value: Decimal, ctx) -> Decimal:
    cos_v = decimal_cos(value, ctx)
    if cos_v == 0:
        raise ControlError(ControlStatus.NUMERIC_ERROR, "tangent singular")
    return ctx.divide(decimal_sin(value, ctx), cos_v)


@dataclass(frozen=True)
class BilinearResult:
    prototype: TransferFunctionTF
    digital: TransferFunctionZ
    sample_period: str
    prewarp_applied: str
    warp_record: tuple


def bilinear_design(proto: TransferFunctionTF, rate_hz: object,
                    prewarp: dict | None = None) -> BilinearResult:
    """Coefficient-exact bilinear design from a P1 prototype.

    prewarp (optional): {"omega_d": analog rad/s target,
    "omega_a_ref": analog rad/s reference}. The scaled prototype
    H~(s) = H(s/β), β = Ω_0/Ω_a_ref, Ω_0 = c·tan(ω_d·T/2), lands Ω_a_ref
    exactly on the digital point θ = ω_d·T. Requires 0 < ω_d < π/T
    (at/above Nyquist → UNSUPPORTED: the analog image is infinite).
    """
    if not isinstance(proto, TransferFunctionTF):
        raise ControlError(ControlStatus.INVALID, "bilinear design needs a P1 prototype TF")
    fs = _as_decimal(rate_hz, "sample rate")
    if fs <= 0:
        raise ControlError(ControlStatus.INVALID, "sample rate fs > 0 required")
    ctx = make_context()
    period = ctx.divide(Decimal(1), fs)
    gain2 = ctx.divide(Decimal(2), period)
    num_s = proto.num.coeffs
    den_s = proto.den.coeffs
    warp_record: tuple = ()
    warp_note = ""
    if prewarp is not None:
        if not isinstance(prewarp, dict):
            raise ControlError(ControlStatus.INVALID, "prewarp must be a dict")
        omega_d = _as_decimal(prewarp.get("omega_d"), "prewarp omega_d")
        omega_a = _as_decimal(prewarp.get("omega_a_ref"), "prewarp omega_a_ref")
        if omega_d <= 0:
            raise ControlError(ControlStatus.INVALID, "prewarp omega_d > 0 required")
        nyquist = ctx.divide(decimal_pi(ctx), period)
        if omega_d >= nyquist:
            raise ControlError(
                ControlStatus.UNSUPPORTED, "prewarp at/above Nyquist is singular")
        if omega_a <= 0:
            raise ControlError(ControlStatus.INVALID, "prewarp omega_a_ref > 0 required")
        half = ctx.divide(ctx.multiply(omega_d, period), Decimal(2))
        omega_0 = ctx.multiply(gain2, _decimal_tan(half, ctx))
        beta = ctx.divide(omega_0, omega_a)
        num_s = tuple(ctx.divide(d, _int_pow(beta, len(num_s) - 1 - j, ctx))
                      for j, d in enumerate(num_s))
        den_s = tuple(ctx.divide(d, _int_pow(beta, len(den_s) - 1 - j, ctx))
                      for j, d in enumerate(den_s))
        warp_note = "prewarp beta=" + str(beta)
        warp_record = (("beta", str(beta)), ("omega_0", str(omega_0)),
                       ("omega_d", str(omega_d)), ("omega_a_ref", str(omega_a)))
    # Analog pole at s = c maps to z = ∞: degenerate, UNSUPPORTED.
    if proto.den.evaluate_decimal(gain2) == 0:
        raise ControlError(ControlStatus.UNSUPPORTED, "prototype pole at s = 2/T")
    num_w, den_w = _s_to_w_coeffs(num_s, den_s, gain2)
    # Common-denominator degree: the numerator lives over (1+w)^n, so it
    # carries the extra (1+w)^{n−m} factor (relative degree is physical).
    extra = len(den_s) - len(num_s)
    if extra > 0:
        num_w = num_w.multiply(
            _pow_poly(make_polynomial((Decimal(1), Decimal(1))), extra, ctx))
    if all(c == 0 for c in den_w.coeffs):
        raise ControlError(ControlStatus.INVALID, "bilinear denominator degenerate")
    # Normalise to DSP ascending with den[0] = 1 (delay-free term).
    den_desc = den_w.coeffs
    anchor = den_desc[-1]
    num_desc = tuple(ctx.divide(c, anchor) for c in num_w.coeffs)
    den_desc_n = tuple(ctx.divide(c, anchor) for c in den_desc)
    num_asc = tuple(reversed(num_desc))
    den_asc = tuple(reversed(den_desc_n))
    if len(num_asc) > len(den_asc):
        raise ControlError(ControlStatus.INVALID, "bilinear result improper")
    digital = TransferFunctionZ(num_w=num_asc, den_w=den_asc, roc_radius=None)
    return BilinearResult(
        prototype=proto, digital=digital, sample_period=str(period),
        prewarp_applied=warp_note, warp_record=warp_record)


def _int_pow(base: Decimal, exp: int, ctx) -> Decimal:
    out = Decimal(1)
    for _ in range(exp):
        out = ctx.multiply(out, base)
    return out


def bilinear_back(digital: TransferFunctionZ, period: object) -> TransferFunctionTF:
    """Exact inverse bilinear map H(z) → H(s) (evaluation-tested)."""
    if not isinstance(digital, TransferFunctionZ):
        raise ControlError(ControlStatus.INVALID, "bilinear_back needs an H(z)")
    t_step = _check_period(period)
    ctx = make_context()
    gain2 = ctx.divide(Decimal(2), t_step)
    num_s, den_s = _w_to_s_coeffs(digital.num_w, digital.den_w, gain2)
    return make_tf(num_s.coeffs, den_s.coeffs)


@dataclass(frozen=True)
class StabilityReport:
    verdict: str
    poles: tuple
    routh_verdict: str
    agreement: bool
    roc_radius: str
    status: str
    detail: str = ""


def _group_multiplicity(roots: tuple) -> list:
    groups: list = []
    ctx = make_context()
    for root in roots:
        placed = False
        for group in groups:
            if (root - group[0]).modulus() <= MULTI_TOL:
                group.append(root)
                placed = True
                break
        if not placed:
            groups.append([root])
    _ = ctx
    return groups


def iir_stability(digital: TransferFunctionZ, period: object | None = None) -> StabilityReport:
    """Pole-modulus ladder + inverse-bilinear Routh cross-check.

    STABLE: all |p| < 1. MARGINAL: simple |p| = 1 only. UNSTABLE:
    any |p| > 1 or repeated on-circle pole. DK non-convergence →
    UNDETERMINED (honest, never a guessed verdict). Ladder/Routh
    disagreement → INCONSISTENT.
    """
    if not isinstance(digital, TransferFunctionZ):
        raise ControlError(ControlStatus.INVALID, "stability needs an H(z)")
    ctx = make_context()
    den = digital.den_poly()
    if den.degree == 0:
        return StabilityReport(
            verdict="STABLE", poles=(), routh_verdict="STABLE", agreement=True,
            roc_radius="0", status="COMPLETED", detail="all-zero denominator")
    res = durand_kerner_roots(den)
    if res.status != ControlStatus.COMPLETED:
        return StabilityReport(
            verdict="UNDETERMINED", poles=(), routh_verdict="",
            agreement=False, roc_radius="", status=res.status.value,
            detail="pole core non-converged: " + res.diagnostic)
    # DK roots live in w = z^-1: invert to z-plane poles (w = 0 is
    # impossible since a_0 != 0, guarded honestly below).
    one = DecimalComplex(Decimal(1), Decimal(0))
    z_roots: list = []
    for w_root in res.roots:
        try:
            z_roots.append(one / w_root)
        except ZeroDivisionError as exc:
            raise ControlError(
                ControlStatus.NUMERIC_ERROR, "w-root at origin") from exc
    poles = tuple(z_roots)
    groups = _group_multiplicity(poles)
    verdict = "STABLE"
    for group in groups:
        radius = group[0].modulus()
        gap = ctx.subtract(radius, Decimal(1)).copy_abs()
        if radius > Decimal(1) and gap > ON_CIRCLE_TOL:
            verdict = "UNSTABLE"
            break
        if gap <= ON_CIRCLE_TOL and len(group) > 1:
            verdict = "UNSTABLE"
            break
        if gap <= ON_CIRCLE_TOL:
            verdict = "MARGINAL"
    # Routh cross-check through the inverse bilinear map (denominator only).
    t_step = _check_period(period) if period is not None else None
    if t_step is None:
        return StabilityReport(
            verdict=verdict, poles=poles, routh_verdict="", agreement=True,
            roc_radius=str(_roc_of(poles)), status="completed",
            detail="pole ladder only (no period for Routh cross-check)")
    gain2 = ctx.divide(Decimal(2), t_step)
    _, s_den = _w_to_s_coeffs((Decimal(1),), digital.den_w, gain2)
    routh = routh_of_poly(s_den)
    match = ((verdict == "STABLE" and routh.verdict == "STABLE")
             or (verdict == "MARGINAL" and routh.verdict == "MARGINAL")
             or (verdict == "UNSTABLE" and routh.verdict == "UNSTABLE"))
    if not match:
        return StabilityReport(
            verdict="INCONSISTENT", poles=poles, routh_verdict=routh.verdict,
            agreement=False, roc_radius=str(_roc_of(poles)),
            status="completed", detail="ladder/Routh disagree")
    return StabilityReport(
        verdict=verdict, poles=poles, routh_verdict=routh.verdict,
        agreement=True, roc_radius=str(_roc_of(poles)),
        status="completed", detail="ladder/Routh agree")


def _roc_of(roots: tuple) -> Decimal:
    best = Decimal(0)
    for root in roots:
        m = root.modulus()
        if m > best:
            best = m
    return best


MATE_TOL = Decimal("1e-6")
CLUSTER_IMAG_TOL = Decimal("1e-9")


def _pair_conjugates(roots: tuple) -> tuple:
    """Canonical conjugate pairing by nearest mate (deterministic).

    Roots with |im| ≤ CLUSTER_IMAG_TOL count as real: DK plateau dust
    on multiple real roots (P1 itself reports pairing_ok=False there)
    must not crash the decomposition. Each +im root pairs with the
    unused −im root minimising the conjugate distance; the section
    product is pairing-invariant (multiplication commutes), so
    plateau-split multiple roots pair honestly. No mate within
    MATE_TOL → NUMERIC_ERROR, never a silent real split.
    """
    ctx = make_context()
    reals: list = []
    upper: list = []
    lower: list = []
    for root in roots:
        if root.im.copy_abs() <= CLUSTER_IMAG_TOL:
            reals.append(root)
        elif root.im > 0:
            upper.append(root)
        else:
            lower.append(root)
    if len(upper) != len(lower):
        raise ControlError(ControlStatus.NUMERIC_ERROR, "unpaired complex spectrum")
    upper.sort(key=lambda z: (str(z.re), str(z.im.copy_abs())))
    pairs: list = []
    for up in upper:
        best = None
        best_dist = None
        for index, low in enumerate(lower):
            dist = (up - low.conjugate()).modulus()
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best = index
        if best is None or best_dist is None or best_dist > MATE_TOL:
            raise ControlError(ControlStatus.NUMERIC_ERROR, "conjugate mate not found")
        low = lower.pop(best)
        _ = ctx
        pairs.append((up, low))
    pairs.sort(key=lambda pr: (str(-pr[0].modulus()), str(pr[0].re)))
    reals.sort(key=lambda z: str(-z.modulus()))
    return tuple(pairs), tuple(reals)


def _quad_from_pair(first: DecimalComplex, second: DecimalComplex) -> tuple:
    """Ascending w-coefficients of (1 − p1·w)(1 − p2·w), real-collapsed."""
    ctx = make_context()
    trace = first + second
    prod = first * second
    c0 = Decimal(1)
    c1 = ctx.minus(trace.re)
    c2 = prod.re
    bound = ctx.multiply(SOS_REAL_TOL, ctx.add(Decimal(1), c1.copy_abs()))
    if trace.im.copy_abs() > bound or prod.im.copy_abs() > bound:
        raise ControlError(ControlStatus.NUMERIC_ERROR, "non-real SOS section")
    return (c0, ctx.plus(c1), ctx.plus(c2))


def _linear_from_root(root: DecimalComplex) -> tuple:
    ctx = make_context()
    if root.im.copy_abs() > CLUSTER_IMAG_TOL:
        raise ControlError(ControlStatus.NUMERIC_ERROR, "non-real SOS section")
    return (Decimal(1), ctx.minus(ctx.plus(root.re)))


@dataclass(frozen=True)
class SOSReport:
    sections: tuple
    gain: str
    detail: str = ""


def sos_decompose(digital: TransferFunctionZ) -> SOSReport:
    """Canonical SOS cascade (REUSEd DK, deterministic pairing).

    Complex pairs (radius descending) then real pairs, odd real leftover
    as a first-order section. Zero groups align with pole groups in
    order; overall w-gain rides on the first section. Required path for
    order > 8; valid for any order ≥ 1.
    """
    if not isinstance(digital, TransferFunctionZ):
        raise ControlError(ControlStatus.INVALID, "SOS needs an H(z)")
    if digital.den_poly().degree == 0:
        raise ControlError(
            ControlStatus.INVALID, "all-zero (FIR) systems need no SOS")
    den_res = durand_kerner_roots(digital.den_poly())
    if den_res.status != ControlStatus.COMPLETED:
        raise ControlError(den_res.status, "SOS pole core did not converge")
    num_poly = digital.num_poly()
    if num_poly.degree == 0 and num_poly.coeffs == (Decimal(0),):
        raise ControlError(ControlStatus.INVALID, "SOS needs a nonzero numerator")
    if num_poly.degree > 0:
        num_res = durand_kerner_roots(num_poly)
        if num_res.status != ControlStatus.COMPLETED:
            raise ControlError(num_res.status, "SOS zero core did not converge")
        zero_w = num_res.roots
    else:
        zero_w = ()
    pole_pairs, pole_reals = _pair_conjugates(_to_z_plane(den_res.roots))
    zero_pairs, zero_reals = _pair_conjugates(_to_z_plane(zero_w)) if zero_w else ((), ())
    ctx = make_context()
    # Section factors (1 − z_p·w) are top-monic by convention while the
    # original polynomials carry top coefficients b_top/a_top: the gain
    # absorbs (b_top/a_top)·(−1)^{M−N}·(Πv_j)/(Πw_i) with the w-plane DK
    # roots (exact algebra, same factors the sections pair).
    b_top = digital.num_poly().coeffs[0]
    a_top = digital.den_poly().coeffs[0]
    num_deg = digital.num_poly().degree
    den_deg = digital.den_poly().degree
    prod_v = DecimalComplex(Decimal(1), Decimal(0))
    for w_root in (num_res.roots if zero_w else ()):
        prod_v = prod_v * w_root
    prod_w = DecimalComplex(Decimal(1), Decimal(0))
    for w_root in den_res.roots:
        prod_w = prod_w * w_root
    try:
        ratio = prod_v / prod_w
    except ZeroDivisionError as exc:
        raise ControlError(ControlStatus.NUMERIC_ERROR, "SOS gain singular") from exc
    bound = ctx.multiply(
        Decimal("1e-9"), ctx.add(Decimal(1), ratio.re.copy_abs()))
    if ratio.im.copy_abs() > bound:
        # A real-coefficient system has exactly real gain; the bound
        # covers multiplicity-plateau dust (CLUSTER scale), never physics.
        raise ControlError(ControlStatus.NUMERIC_ERROR, "SOS gain non-real")
    sign = Decimal(1) if (num_deg - den_deg) % 2 == 0 else Decimal(-1)
    gain = ctx.multiply(ctx.multiply(ctx.divide(b_top, a_top), sign), ratio.re)
    sections: list = []
    z_paired = list(zero_pairs)
    z_reals = list(zero_reals)
    first = True
    for pair in pole_pairs:
        den_sec = _quad_from_pair(pair[0], pair[1])
        if z_paired:
            zpair = z_paired.pop(0)
            num_sec = _quad_from_pair(zpair[0], zpair[1])
        elif len(z_reals) >= 2:
            num_sec = _quad_from_pair(
                _real_as_complex(z_reals.pop(0)), _real_as_complex(z_reals.pop(0)))
        else:
            num_sec = (Decimal(1),)
        if first:
            num_sec = tuple(ctx.multiply(c, gain) for c in num_sec)
            first = False
        sections.append(TransferFunctionZ.create(num_sec, den_sec))
    for index in range(0, len(pole_reals), 2):
        chunk = pole_reals[index:index + 2]
        if len(chunk) == 2:
            den_sec = _quad_from_pair(
                _real_as_complex(chunk[0]), _real_as_complex(chunk[1]))
        else:
            den_sec = _linear_from_root(chunk[0])
        if len(z_reals) >= 2 and len(den_sec) == 3:
            num_sec = _quad_from_pair(
                _real_as_complex(z_reals.pop(0)), _real_as_complex(z_reals.pop(0)))
        elif z_reals and len(den_sec) == 2:
            num_sec = _linear_from_root(z_reals.pop(0))
        elif z_paired and len(den_sec) == 3:
            zpair = z_paired.pop(0)
            num_sec = _quad_from_pair(zpair[0], zpair[1])
        else:
            num_sec = (Decimal(1),)
        if first:
            num_sec = tuple(ctx.multiply(c, gain) for c in num_sec)
            first = False
        sections.append(TransferFunctionZ.create(num_sec, den_sec))
    # Leftover zero groups (more zeros than pole groups): fold into first section.
    while z_paired or z_reals:
        raise ControlError(ControlStatus.NUMERIC_ERROR, "SOS zero surplus")
    if len(sections) > MAX_SOS_SECTIONS:
        raise ControlError(ControlStatus.INVALID, "SOS section budget exceeded")
    return SOSReport(sections=tuple(sections), gain=str(gain), detail="canonical pairing")


def _to_z_plane(w_roots: tuple) -> tuple:
    """Invert w-roots to z-plane poles/zeros (w = 0 impossible: a_0 != 0)."""
    one = DecimalComplex(Decimal(1), Decimal(0))
    out: list = []
    for w_root in w_roots:
        try:
            out.append(one / w_root)
        except ZeroDivisionError as exc:
            raise ControlError(
                ControlStatus.NUMERIC_ERROR, "w-root at origin") from exc
    return tuple(out)


def _real_as_complex(root: DecimalComplex) -> DecimalComplex:
    return DecimalComplex(root.re, Decimal(0))


def cascade_evaluate(sections: tuple, z: DecimalComplex) -> DecimalComplex:
    """Product of section evaluations (SOS ≡ direct agreement path)."""
    if not isinstance(z, DecimalComplex):
        raise ControlError(ControlStatus.INVALID, "cascade point must be DecimalComplex")
    acc = DecimalComplex(Decimal(1), Decimal(0))
    for section in sections:
        if not isinstance(section, TransferFunctionZ):
            raise ControlError(ControlStatus.INVALID, "cascade needs H(z) sections")
        acc = acc * section.evaluate(z)
    return acc


@dataclass(frozen=True)
class LinearPhaseReport:
    kind: str
    order: int
    group_delay_samples: str
    symmetric: bool
    detail: str = ""


def linear_phase_report(num_asc: tuple) -> LinearPhaseReport:
    """Exact symmetry audit of FIR coefficients (no window design)."""
    coeffs = _as_ascending(num_asc, "FIR coefficients")
    order = len(coeffs) - 1
    ctx = make_context()
    # Explicit contexts throughout (never bare Decimal negation, which would
    # round through the ambient global context).
    if all(ctx.subtract(coeffs[k], coeffs[order - k]) == 0
           for k in range(len(coeffs))):
        kind = "I" if order % 2 == 0 else "II"
        symmetric = True
    elif all(ctx.add(coeffs[k], coeffs[order - k]) == 0
             for k in range(len(coeffs))):
        kind = "III" if order % 2 == 0 else "IV"
        symmetric = True
    else:
        return LinearPhaseReport(kind="none", order=order, group_delay_samples="",
                                 symmetric=False, detail="no exact symmetry")
    ctx = make_context()
    tau = ctx.divide(Decimal(order), Decimal(2))
    detail = "symmetric" if kind in ("I", "II") else "antisymmetric pi/2 offset"
    return LinearPhaseReport(kind=kind, order=order, group_delay_samples=str(tau),
                             symmetric=symmetric, detail=detail)


def _fir_eval_at(coeffs: tuple, theta: Decimal, ctx) -> DecimalComplex:
    """Direct FIR sum Σ b_k·e^{−jkθ} (no TF constructor: FIR is w-improper)."""
    acc = DecimalComplex(Decimal(0), Decimal(0))
    for k, b_k in enumerate(coeffs):
        angle = ctx.multiply(theta, Decimal(k))
        basis = DecimalComplex(decimal_cos(angle, ctx), ctx.minus(decimal_sin(angle, ctx)))
        acc = acc + DecimalComplex(ctx.multiply(b_k, Decimal(1)), Decimal(0)) * basis
    return acc


def fir_group_delay_at(num_asc: tuple, theta: Decimal) -> tuple:
    """Group delay τ_g(θ) = −d∠H/dθ via unwrapped central differences.

    Near magnitude zeros (|H| < 1e-12) the phase is undefined →
    UNSUPPORTED (explicit, never an ingenuous wrapped difference).
    """
    coeffs = _as_ascending(num_asc, "FIR coefficients")
    if isinstance(theta, bool) or not isinstance(theta, Decimal):
        raise ControlError(ControlStatus.INVALID, "group-delay angle must be Decimal")
    if not theta.is_finite() or theta < 0:
        raise ControlError(ControlStatus.INVALID, "group-delay angle in [0, pi] required")
    ctx = make_context()
    if theta > decimal_pi(ctx):
        raise ControlError(ControlStatus.INVALID, "group-delay angle in [0, pi] required")
    step = Decimal("1e-6")
    lo = ctx.subtract(theta, step) if theta >= step else Decimal(0)
    hi = ctx.add(theta, step)
    for probe in (lo, theta, hi):
        if _fir_eval_at(coeffs, probe, ctx).modulus() < Decimal("1e-12"):
            raise ControlError(ControlStatus.UNSUPPORTED, "phase undefined at magnitude zero")
    p_lo = _unwrapped_phase(coeffs, lo, ctx)
    p_hi = _unwrapped_phase(coeffs, hi, ctx)
    span = ctx.subtract(hi, lo)
    tau = ctx.minus(ctx.divide(ctx.subtract(p_hi, p_lo), span))
    return (tau, "central differences, unwrapped")


def _unwrapped_phase(coeffs: tuple, theta: Decimal, ctx) -> Decimal:
    steps = 720
    start = _fir_eval_at(coeffs, Decimal(0), ctx)
    prev = decimal_atan2(start.im, start.re, ctx)
    acc = Decimal(0)
    for index in range(1, steps + 1):
        probe = ctx.divide(ctx.multiply(theta, Decimal(index)), Decimal(steps))
        val = _fir_eval_at(coeffs, probe, ctx)
        raw = decimal_atan2(val.im, val.re, ctx)
        delta = ctx.subtract(raw, prev)
        half_pi = ctx.divide(decimal_pi(ctx), Decimal(2))
        full_pi = decimal_pi(ctx)
        if delta > half_pi:
            delta = ctx.subtract(delta, ctx.multiply(Decimal(2), full_pi))
        elif delta < ctx.minus(half_pi):
            delta = ctx.add(delta, ctx.multiply(Decimal(2), full_pi))
        acc = ctx.add(acc, delta)
        prev = raw
    base = decimal_atan2(start.im, start.re, ctx)
    return ctx.add(base, acc)
