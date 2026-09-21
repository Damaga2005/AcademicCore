"""F8-P1 rational transfer functions + ZPK (NEW).

H(s) = N(s) / D(s), real Decimal coefficient polynomials, proper only
(deg N <= deg D, deg D >= 1). Algebra is exact coefficient arithmetic.
Evaluation is Horner-based; D(s) = 0 at the point -> SINGULAR.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Sequence

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.control.poly import (
    MAX_POLY_DEGREE,
    Polynomial,
    durand_kerner_roots,
    make_polynomial,
    to_decimal_coefficient,
)
from academic_core.domain.engineering.math import DecimalComplex, make_context

RHO_CANCEL = Decimal("1e-9")
ZPK_REAL_TOL = Decimal("1e-24")


def _as_poly(value: object) -> Polynomial:
    if isinstance(value, Polynomial):
        return value
    if isinstance(value, (tuple, list)):
        return make_polynomial(value)
    raise ControlError(ControlStatus.INVALID, "polynomial input type not supported")


@dataclass(frozen=True)
class TransferFunctionTF:
    """Proper SISO rational H(s) (validation-only post-init)."""

    num: Polynomial
    den: Polynomial

    def __post_init__(self) -> None:
        if not isinstance(self.num, Polynomial) or not isinstance(self.den, Polynomial):
            raise ControlError(ControlStatus.INVALID, "TF needs Polynomial num/den")
        if len(self.den.coeffs) == 1 and self.den.coeffs[0] == 0:
            raise ControlError(ControlStatus.INVALID, "zero denominator rejected")
        if self.den.degree < 1:
            raise ControlError(ControlStatus.INVALID, "denominator degree >= 1 required")
        if self.num.degree > self.den.degree:
            raise ControlError(ControlStatus.INVALID, "improper TF (m > n) rejected")
        if self.num.degree > MAX_POLY_DEGREE or self.den.degree > MAX_POLY_DEGREE:
            raise ControlError(ControlStatus.INVALID, "degree exceeds 32")
        if self.den.leading == 0:
            raise ControlError(ControlStatus.INVALID, "zero leading coefficient")

    @staticmethod
    def create(num: Sequence[object], den: Sequence[object]) -> "TransferFunctionTF":
        return TransferFunctionTF(num=_as_poly(num), den=_as_poly(den))

    def evaluate(self, s: object) -> DecimalComplex:
        den_val = self.den.evaluate(s)
        if den_val.is_zero_exact():
            raise ControlError(ControlStatus.SINGULAR, "pole evaluation D(s) = 0")
        num_val = self.num.evaluate(s)
        try:
            return num_val / den_val
        except ZeroDivisionError as exc:
            raise ControlError(ControlStatus.SINGULAR, "pole evaluation") from exc

    def to_dict(self) -> dict:
        return {
            "num": self.num.to_dict(),
            "den": self.den.to_dict(),
        }


def make_tf(num: Sequence[object], den: Sequence[object]) -> TransferFunctionTF:
    return TransferFunctionTF.create(num, den)


def series(h1: TransferFunctionTF, h2: TransferFunctionTF) -> TransferFunctionTF:
    if not isinstance(h1, TransferFunctionTF) or not isinstance(h2, TransferFunctionTF):
        raise ControlError(ControlStatus.INVALID, "series needs two TFs")
    num = h1.num.multiply(h2.num)
    den = h1.den.multiply(h2.den)
    if num.degree > den.degree:
        raise ControlError(ControlStatus.INVALID, "series result improper")
    return TransferFunctionTF(num=num, den=den)


def parallel(h1: TransferFunctionTF, h2: TransferFunctionTF) -> TransferFunctionTF:
    if not isinstance(h1, TransferFunctionTF) or not isinstance(h2, TransferFunctionTF):
        raise ControlError(ControlStatus.INVALID, "parallel needs two TFs")
    num = h1.num.multiply(h2.den).add(h2.num.multiply(h1.den))
    den = h1.den.multiply(h2.den)
    if num.degree > den.degree:
        raise ControlError(ControlStatus.INVALID, "parallel result improper")
    # Zero-numerator edge: keep denominator, numerator may be identically zero only
    # when both paths cancel; Polynomial forbids a zero leading entry, and the
    # add() helper already strips leading zeros, so a true zero sum surfaces as
    # a zero constant which the TF contract keeps as a valid zero gain.
    return TransferFunctionTF(num=num, den=den)


def feedback(h_fwd: TransferFunctionTF, h_ret: TransferFunctionTF | None = None) -> TransferFunctionTF:
    """Negative-feedback closed loop: H_cl = Fwd / (1 + Fwd * Ret)."""
    if not isinstance(h_fwd, TransferFunctionTF):
        raise ControlError(ControlStatus.INVALID, "feedback needs a forward TF")
    nf, df = h_fwd.num, h_fwd.den
    if h_ret is None:
        # Unity return: static gain 1 (not a dynamic TF), H_cl = Nf/(Df+Nf).
        closed_den = df.add(nf)
        if all(c == 0 for c in closed_den.coeffs):
            raise ControlError(ControlStatus.SINGULAR, "feedback singular (1 + L = 0)")
        if nf.degree > closed_den.degree:
            raise ControlError(ControlStatus.INVALID, "feedback result improper")
        return TransferFunctionTF(num=nf, den=closed_den)
    if not isinstance(h_ret, TransferFunctionTF):
        raise ControlError(ControlStatus.INVALID, "feedback needs a TF return path")
    nr, dr = h_ret.num, h_ret.den
    loop_num = nf.multiply(nr)
    loop_den = df.multiply(dr)
    closed_den = loop_den.add(loop_num)
    closed_num = nf.multiply(dr)
    # Identically-zero closed denominator = algebraic loop at every point.
    if all(c == 0 for c in closed_den.coeffs):
        raise ControlError(ControlStatus.SINGULAR, "feedback singular (1 + L = 0)")
    if closed_num.degree > closed_den.degree:
        raise ControlError(ControlStatus.INVALID, "feedback result improper")
    return TransferFunctionTF(num=closed_num, den=closed_den)


def feedback_positive(h_fwd: TransferFunctionTF,
                      h_ret: TransferFunctionTF | None = None) -> TransferFunctionTF:
    """Explicitly-tagged positive feedback: H_cl = Fwd / (1 - Fwd * Ret)."""
    if not isinstance(h_fwd, TransferFunctionTF):
        raise ControlError(ControlStatus.INVALID, "feedback needs a forward TF")
    nf, df = h_fwd.num, h_fwd.den
    if h_ret is None:
        # Unity positive return: H_cl = Nf/(Df-Nf).
        closed_den = df.add(nf.scale(Decimal(-1)))
        if all(c == 0 for c in closed_den.coeffs):
            raise ControlError(ControlStatus.SINGULAR, "positive feedback singular (1 - L = 0)")
        if nf.degree > closed_den.degree:
            raise ControlError(ControlStatus.INVALID, "positive feedback result improper")
        return TransferFunctionTF(num=nf, den=closed_den)
    if not isinstance(h_ret, TransferFunctionTF):
        raise ControlError(ControlStatus.INVALID, "feedback needs a TF return path")
    nr, dr = h_ret.num, h_ret.den
    loop_num = nf.multiply(nr)
    loop_den = df.multiply(dr)
    closed_den = loop_den.add(loop_num.scale(Decimal(-1)))
    closed_num = nf.multiply(dr)
    if all(c == 0 for c in closed_den.coeffs):
        raise ControlError(ControlStatus.SINGULAR, "positive feedback singular (1 - L = 0)")
    if closed_num.degree > closed_den.degree:
        raise ControlError(ControlStatus.INVALID, "positive feedback result improper")
    return TransferFunctionTF(num=closed_num, den=closed_den)


def sensitivity(loop: TransferFunctionTF) -> TransferFunctionTF:
    """S = 1 / (1 + L) with the shared-denominator exact form."""
    if not isinstance(loop, TransferFunctionTF):
        raise ControlError(ControlStatus.INVALID, "sensitivity needs a loop TF")
    den_sum = loop.den.add(loop.num)
    one = make_polynomial((Decimal(1),))
    s_num = loop.den.multiply(one)
    return TransferFunctionTF(num=s_num, den=den_sum)


def complementary(loop: TransferFunctionTF) -> TransferFunctionTF:
    """T = L / (1 + L) with the shared-denominator exact form."""
    if not isinstance(loop, TransferFunctionTF):
        raise ControlError(ControlStatus.INVALID, "complementary needs a loop TF")
    den_sum = loop.den.add(loop.num)
    t_num = loop.num.multiply(make_polynomial((Decimal(1),)))
    return TransferFunctionTF(num=t_num, den=den_sum)


@dataclass(frozen=True)
class ZPK:
    """Zero-pole-gain form H(s) = k Pi(s - z_i) / Pj(s - p_j)."""

    gain: Decimal
    zeros: tuple
    poles: tuple

    def __post_init__(self) -> None:
        if isinstance(self.gain, bool) or not isinstance(self.gain, Decimal):
            raise ControlError(ControlStatus.INVALID, "ZPK gain must be Decimal")
        if not self.gain.is_finite() or self.gain == 0:
            raise ControlError(ControlStatus.INVALID, "ZPK gain must be finite nonzero")
        if not isinstance(self.zeros, tuple) or not isinstance(self.poles, tuple):
            raise ControlError(ControlStatus.INVALID, "ZPK zeros/poles must be tuples")
        if len(self.poles) < 1:
            raise ControlError(ControlStatus.INVALID, "ZPK needs >= 1 pole")
        if len(self.zeros) > len(self.poles):
            raise ControlError(ControlStatus.INVALID, "ZPK improper (m > n)")
        if len(self.poles) > MAX_POLY_DEGREE:
            raise ControlError(ControlStatus.INVALID, "ZPK degree exceeds 32")
        for z in list(self.zeros) + list(self.poles):
            if not isinstance(z, DecimalComplex):
                raise ControlError(ControlStatus.INVALID, "ZPK entries must be DecimalComplex")

    def evaluate(self, s: object) -> DecimalComplex:
        if isinstance(s, bool):
            raise ControlError(ControlStatus.INVALID, "evaluation point rejects bool")
        if isinstance(s, DecimalComplex):
            point = s
        elif isinstance(s, Decimal):
            point = DecimalComplex(s, Decimal(0))
        elif isinstance(s, int):
            point = DecimalComplex(Decimal(s), Decimal(0))
        else:
            raise ControlError(ControlStatus.INVALID, "evaluation point type not supported")
        num = DecimalComplex(self.gain, Decimal(0))
        for z in self.zeros:
            diff = point - z
            if diff.is_zero_exact():
                return DecimalComplex(Decimal(0), Decimal(0))
            num = num * diff
        den = DecimalComplex(Decimal(1), Decimal(0))
        for p in self.poles:
            diff = point - p
            if diff.is_zero_exact():
                raise ControlError(ControlStatus.SINGULAR, "ZPK pole evaluation")
            den = den * diff
        try:
            return num / den
        except ZeroDivisionError as exc:
            raise ControlError(ControlStatus.SINGULAR, "ZPK pole evaluation") from exc


def tf_to_zpk(h: TransferFunctionTF) -> ZPK:
    if not isinstance(h, TransferFunctionTF):
        raise ControlError(ControlStatus.INVALID, "tf_to_zpk needs a TF")
    if len(h.num.coeffs) == 1 and h.num.coeffs[0] == 0:
        raise ControlError(ControlStatus.INVALID, "zero transfer has no ZPK form")
    ctx = make_context()
    gain = ctx.divide(h.num.leading, h.den.leading)
    zres = durand_kerner_roots(h.num) if h.num.degree > 0 else None
    pres = durand_kerner_roots(h.den)
    if pres.status != ControlStatus.COMPLETED:
        raise ControlError(pres.status, "pole core did not converge")
    if zres is not None and zres.status != ControlStatus.COMPLETED:
        raise ControlError(zres.status, "zero core did not converge")
    zeros = () if zres is None else zres.roots
    # Constant numerator: no finite zeros.
    if h.num.degree == 0:
        zeros = ()
    return ZPK(gain=gain, zeros=zeros, poles=pres.roots)


def _expand_factors(roots: tuple) -> tuple:
    """Expand Pi(s - r_i) over DecimalComplex (descending)."""
    coeffs: list = [DecimalComplex(Decimal(1), Decimal(0))]
    for r in roots:
        nxt: list = [DecimalComplex(Decimal(0), Decimal(0))] * (len(coeffs) + 1)
        for i, c in enumerate(coeffs):
            nxt[i] = nxt[i] + c
            nxt[i + 1] = nxt[i + 1] - c * r
        coeffs = nxt
    return tuple(coeffs)


def _complex_poly_to_real(coeffs: tuple) -> tuple:
    ctx = make_context()
    out: list = []
    for c in coeffs:
        scale = ctx.add(Decimal(1), c.re.copy_abs())
        bound = ctx.multiply(ZPK_REAL_TOL, scale)
        if c.im.copy_abs() > bound:
            raise ControlError(ControlStatus.INCONSISTENT, "non-real expansion from ZPK")
        out.append(ctx.plus(c.re))
    return tuple(out)


def zpk_to_tf(zpk: ZPK) -> TransferFunctionTF:
    if not isinstance(zpk, ZPK):
        raise ControlError(ControlStatus.INVALID, "zpk_to_tf needs a ZPK")
    ctx = make_context()
    num_c = _expand_factors(zpk.zeros)
    den_c = _expand_factors(zpk.poles)
    num_r = _complex_poly_to_real(num_c)
    den_r = _complex_poly_to_real(den_c)
    num_scaled = tuple(ctx.multiply(c, zpk.gain) for c in num_r)
    return TransferFunctionTF(num=Polynomial(coeffs=num_scaled), den=Polynomial(coeffs=den_r))


@dataclass(frozen=True)
class CancellationReport:
    min_distance: str
    verdict: str
    pairs: tuple


def _divmod_frac(a: list, b: list) -> tuple:
    """Long division of descending Fraction rows (b has nonzero leading)."""
    rem = list(a)
    quo: list = []
    while len(rem) >= len(b) and any(v != 0 for v in rem):
        factor = rem[0] / b[0]
        quo.append(factor)
        for i in range(len(b)):
            rem[i] = rem[i] - factor * b[i]
        while rem and rem[0] == 0:
            rem.pop(0)
    return quo, rem


def _gcd_degree(num: Polynomial, den: Polynomial) -> int:
    """Exact GCD degree of num/den over Fractions (-1/0 convention below)."""
    a = [Fraction(c) for c in num.coeffs]
    b = [Fraction(c) for c in den.coeffs]
    while any(v != 0 for v in b):
        _, rem = _divmod_frac(a, b)
        a, b = b, rem
    while len(a) > 1 and a[0] == 0:
        a = a[1:]
    if len(a) == 1 and a[0] == 0:
        return -1
    return len(a) - 1


def cancellation_report(h: TransferFunctionTF) -> CancellationReport:
    """Explicit pole-zero cancellation policy.

    Exact cancellation is decided by an exact Fraction GCD of the
    numerator/denominator (no tolerance involved). Near-cancellation uses
    the documented radius RHO_CANCEL on DK-derived pole-zero distances.
    """
    exact = _gcd_degree(h.num, h.den) >= 1
    try:
        zpk = tf_to_zpk(h)
    except ControlError:
        verdict = "exact cancellation" if exact else "no cancellation"
        return CancellationReport(min_distance="", verdict=verdict, pairs=())
    if len(zpk.zeros) == 0:
        return CancellationReport(min_distance="", verdict="no cancellation", pairs=())
    best: Decimal | None = None
    pairs: list = []
    for zi in zpk.zeros:
        for pj in zpk.poles:
            dist = (zi - pj).modulus()
            pairs.append((str(zi.re), str(zi.im), str(pj.re), str(pj.im), str(dist)))
            if best is None or dist < best:
                best = dist
    if best is None:
        return CancellationReport(min_distance="", verdict="no cancellation", pairs=())
    if exact:
        verdict = "exact cancellation"
    elif best <= RHO_CANCEL:
        verdict = "numerical near-cancellation"
    else:
        verdict = "no cancellation"
    return CancellationReport(min_distance=str(best), verdict=verdict, pairs=tuple(pairs))
