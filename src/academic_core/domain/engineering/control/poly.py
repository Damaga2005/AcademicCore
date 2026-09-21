"""F8-P1 polynomial core (NEW).

Representation:
    P(s) = a_0 s^n + a_1 s^{n-1} + ... + a_n
coefficients descending, exact Decimal entries.

Evaluation uses Horner:
    P(s) = (...((a_0 s + a_1) s + a_2) ...) s + a_n
with an explicit working context (precision 50). Exactness is kept
whenever the coefficient arithmetic is exact under that context.

Roots use Durand-Kerner simultaneous iteration over DecimalComplex
with deterministic Aberth-style circle-packing init, an explicit
iteration budget and a backward-error gate per root.

Limits: MAX_POLY_DEGREE = 32, MAX_DK_ITER = 500 * n.
Tolerances: DK_STEP_TOL = 1e-30 scale, DK_BACKWARD_TOL = 1e-30 * (1 + norm).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction
from typing import Sequence

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.math import (
    DecimalComplex,
    decimal_cos,
    decimal_pi,
    decimal_sin,
    make_context,
)

MAX_POLY_DEGREE = 32
MAX_DK_ITER_FACTOR = 500
DK_STEP_TOL = Decimal("1e-30")
DK_BACKWARD_TOL = Decimal("1e-30")
DK_STAGNATION_WINDOW = 20


def _reject_bool(value: object, label: str) -> None:
    if isinstance(value, bool):
        raise ControlError(ControlStatus.INVALID, label + " rejects bool")


def to_decimal_coefficient(value: object) -> Decimal:
    """Normalise one coefficient to Decimal (exact for int/str/Fraction)."""
    if isinstance(value, bool):
        raise ControlError(ControlStatus.INVALID, "coefficient rejects bool")
    if isinstance(value, Decimal):
        out = value
    elif isinstance(value, int):
        out = Decimal(value)
    elif isinstance(value, Fraction):
        ctx = make_context()
        out = ctx.divide(Decimal(value.numerator), Decimal(value.denominator))
    elif isinstance(value, str):
        try:
            out = Decimal(value.strip())
        except Exception as exc:
            raise ControlError(ControlStatus.INVALID, "bad coefficient string") from exc
    else:
        raise ControlError(
            ControlStatus.INVALID,
            "coefficient must be Decimal/int/Fraction/str, got " + type(value).__name__,
        )
    if not out.is_finite():
        raise ControlError(ControlStatus.INVALID, "coefficient must be finite")
    return out


def _check_coeff_tuple(coeffs: tuple) -> None:
    if not isinstance(coeffs, tuple) or len(coeffs) == 0:
        raise ControlError(ControlStatus.INVALID, "polynomial needs a non-empty tuple")
    if len(coeffs) - 1 > MAX_POLY_DEGREE:
        raise ControlError(ControlStatus.INVALID, "degree exceeds 32")
    for item in coeffs:
        if isinstance(item, bool) or not isinstance(item, Decimal):
            raise ControlError(ControlStatus.INVALID, "coefficients must be Decimal")
        if not item.is_finite():
            raise ControlError(ControlStatus.INVALID, "coefficients must be finite")
    if len(coeffs) == 1 and coeffs[0] == 0:
        return  # The zero polynomial: valid value, undefined roots.
    if coeffs[0] == 0:
        raise ControlError(ControlStatus.INVALID, "leading coefficient must be nonzero")


def is_zero_poly(coeffs: tuple) -> bool:
    return len(coeffs) == 1 and coeffs[0] == 0


def make_polynomial(values: Sequence[object]) -> "Polynomial":
    """Normalising factory: int/Fraction/str/Decimal -> Polynomial."""
    if not isinstance(values, (tuple, list)) or len(values) == 0:
        raise ControlError(ControlStatus.INVALID, "polynomial needs non-empty coefficients")
    if len(values) - 1 > MAX_POLY_DEGREE:
        raise ControlError(ControlStatus.INVALID, "degree exceeds 32")
    decs = tuple(to_decimal_coefficient(v) for v in values)
    return Polynomial(coeffs=decs)


@dataclass(frozen=True)
class Polynomial:
    """Descending-coefficient real polynomial (validation-only post-init)."""

    coeffs: tuple

    def __post_init__(self) -> None:
        _check_coeff_tuple(self.coeffs)

    @property
    def degree(self) -> int:
        return len(self.coeffs) - 1

    @property
    def order(self) -> int:
        return len(self.coeffs) - 1

    @property
    def leading(self) -> Decimal:
        return self.coeffs[0]

    @property
    def coefficients(self) -> tuple:
        return self.coeffs

    def evaluate(self, s: object) -> DecimalComplex:
        """Horner evaluation at a DecimalComplex/int/Decimal point."""
        ctx = make_context()
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
        acc = DecimalComplex(point.re, point.im).__class__(Decimal(0), Decimal(0))
        # Horner: acc = (...((a0) s + a1) s + a2 ...) s + an ; start from zero
        # acc = acc * s + a_i with DecimalComplex arithmetic under the hood.
        first = True
        for coeff in self.coeffs:
            if first:
                acc = DecimalComplex(coeff, Decimal(0))
                first = False
            else:
                acc = acc * point + DecimalComplex(coeff, Decimal(0))
        _ = ctx
        return acc

    def evaluate_decimal(self, x: Decimal) -> Decimal:
        """Horner evaluation on the real line (exact Decimal path)."""
        ctx = make_context()
        if isinstance(x, bool) or not isinstance(x, Decimal):
            raise ControlError(ControlStatus.INVALID, "real evaluation needs Decimal")
        if not x.is_finite():
            raise ControlError(ControlStatus.INVALID, "real evaluation needs finite x")
        acc = self.coeffs[0]
        for coeff in self.coeffs[1:]:
            acc = ctx.add(ctx.multiply(acc, x), coeff)
        return acc

    def derivative(self) -> "Polynomial":
        n = self.degree
        if n == 0:
            return Polynomial(coeffs=(Decimal(0),))
        ctx = make_context()
        out: list = []
        for index, coeff in enumerate(self.coeffs[:-1]):
            power = Decimal(n - index)
            out.append(ctx.multiply(coeff, power))
        return Polynomial(coeffs=tuple(out))

    def scale(self, factor: object) -> "Polynomial":
        alpha = to_decimal_coefficient(factor)
        ctx = make_context()
        return Polynomial(coeffs=tuple(ctx.multiply(c, alpha) for c in self.coeffs))

    def add(self, other: "Polynomial") -> "Polynomial":
        if not isinstance(other, Polynomial):
            raise ControlError(ControlStatus.INVALID, "add needs a Polynomial")
        ctx = make_context()
        a = self.coeffs
        b = other.coeffs
        width = len(a) if len(a) >= len(b) else len(b)
        pa = (Decimal(0),) * (width - len(a)) + a
        pb = (Decimal(0),) * (width - len(b)) + b
        summed = tuple(ctx.add(x, y) for x, y in zip(pa, pb))
        # Strip leading zeros (keep at least one entry).
        start = 0
        while start < len(summed) - 1 and summed[start] == 0:
            start += 1
        return Polynomial(coeffs=tuple(summed[start:]))

    def multiply(self, other: "Polynomial") -> "Polynomial":
        if not isinstance(other, Polynomial):
            raise ControlError(ControlStatus.INVALID, "multiply needs a Polynomial")
        ctx = make_context()
        a = self.coeffs
        b = other.coeffs
        if len(a) + len(b) - 1 > MAX_POLY_DEGREE + 1:
            raise ControlError(ControlStatus.INVALID, "product degree exceeds 32")
        out = [Decimal(0)] * (len(a) + len(b) - 1)
        for i, ca in enumerate(a):
            for j, cb in enumerate(b):
                out[i + j] = ctx.add(out[i + j], ctx.multiply(ca, cb))
        # Collapse an identically-zero product to the zero polynomial.
        start = 0
        while start < len(out) - 1 and out[start] == 0:
            start += 1
        return Polynomial(coeffs=tuple(out[start:]))

    def normalize_monic(self) -> "Polynomial":
        """Divide by the leading coefficient (leading-denominator-1 form)."""
        if is_zero_poly(self.coeffs):
            raise ControlError(ControlStatus.INVALID, "zero polynomial has no monic form")
        ctx = make_context()
        lead = self.coeffs[0]
        return Polynomial(coeffs=tuple(ctx.divide(c, lead) for c in self.coeffs))

    def to_dict(self) -> dict:
        return {
            "degree": self.degree,
            "coeffs": [str(c) for c in self.coeffs],
        }

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Polynomial):
            return NotImplemented
        return self.coeffs == other.coeffs

    def __hash__(self) -> int:
        return hash(self.coeffs)


@dataclass(frozen=True)
class RootResult:
    roots: tuple
    status: ControlStatus
    iterations: int
    backward_errors: tuple
    max_step: str
    diagnostic: str = ""


def _poly_eval_complex(coeffs: tuple, z: DecimalComplex) -> DecimalComplex:
    acc = DecimalComplex(Decimal(0), Decimal(0))
    first = True
    for coeff in coeffs:
        if first:
            acc = DecimalComplex(coeff, Decimal(0))
            first = False
        else:
            acc = acc * z + DecimalComplex(coeff, Decimal(0))
    return acc


def _aberrth_init(n: int, scale: Decimal = Decimal(1)) -> list:
    """Deterministic Aberth-style spiral packing (no RNG, no seed needed).

    Distinct radii per root (r_k grows with k) break the circular
    symmetry that can trap simultaneous iteration in cycles for
    real-root polynomials; the fixed 0.5 rad angular offset avoids
    axis-symmetric starts. ``scale`` recentres the spiral (unit or
    Cauchy-bound), keeping every retry deterministic.
    """
    ctx = make_context()
    pi = decimal_pi(ctx)
    two_pi = ctx.multiply(pi, Decimal(2))
    offset = Decimal("0.5")
    out: list = []
    for k in range(n):
        frac = ctx.divide(Decimal(k), Decimal(n))
        angle = ctx.add(ctx.multiply(two_pi, frac), offset)
        radius = ctx.multiply(scale, ctx.add(Decimal("0.6"), ctx.multiply(Decimal("0.8"), frac)))
        c = decimal_cos(angle, ctx)
        s = decimal_sin(angle, ctx)
        out.append(DecimalComplex(ctx.multiply(radius, c), ctx.multiply(radius, s)))
    return out


def _cauchy_scale(coeffs: tuple) -> Decimal:
    """Cauchy bound 1 + max|a_i / a_0| (all-positive Decimal, >= 1)."""
    ctx = make_context()
    lead = coeffs[0].copy_abs()
    if lead == 0:
        return Decimal(1)
    best = Decimal(0)
    for c in coeffs[1:]:
        ratio = ctx.divide(c.copy_abs(), lead)
        if ratio > best:
            best = ratio
    return ctx.add(Decimal(1), best)


def _dk_run(coeffs: tuple, current: list, max_iter: int,
            tol_step_base: Decimal) -> tuple:
    """One deterministic DK run; returns (roots, status, iters, last_step)."""
    n = len(current)
    status = ControlStatus.DIVERGED
    iters = 0
    last_step = Decimal(0)
    prev_best_step: Decimal | None = None
    stagnant = 0
    ctx = make_context()
    for iteration in range(1, max_iter + 1):
        iters = iteration
        radius = Decimal(0)
        for z in current:
            m = z.modulus()
            if m > radius:
                radius = m
        threshold = ctx.multiply(tol_step_base, ctx.add(Decimal(1), radius))
        nxt: list = []
        worst = Decimal(0)
        failed = False
        for i in range(n):
            zi = current[i]
            pz = _poly_eval_complex(coeffs, zi)
            denom = DecimalComplex(Decimal(1), Decimal(0))
            for j in range(n):
                if j == i:
                    continue
                diff = zi - current[j]
                if diff.is_zero_exact():
                    failed = True
                    break
                denom = denom * diff
            if failed:
                break
            try:
                correction = pz / denom
            except ZeroDivisionError:
                failed = True
                break
            updated = zi - correction
            step = (updated - zi).modulus()
            if step > worst:
                worst = step
            nxt.append(updated)
        if failed:
            status = ControlStatus.DIVERGED
            break
        current = nxt
        last_step = worst
        if prev_best_step is None or worst < prev_best_step:
            prev_best_step = worst
            stagnant = 0
        else:
            stagnant += 1
        if worst <= threshold:
            status = ControlStatus.COMPLETED
            break
        if stagnant >= DK_STAGNATION_WINDOW and prev_best_step is not None:
            if worst >= prev_best_step:
                status = ControlStatus.DIVERGED
                break
    else:
        status = ControlStatus.MAX_ITERATIONS
    return current, status, iters, last_step


def durand_kerner_roots(poly: Polynomial) -> RootResult:
    """Durand-Kerner roots with backward-error gate (observed convergence)."""
    if not isinstance(poly, Polynomial):
        raise ControlError(ControlStatus.INVALID, "roots need a Polynomial")
    if is_zero_poly(poly.coeffs):
        raise ControlError(ControlStatus.INVALID, "zero polynomial has undefined roots")
    n = poly.degree
    if n == 0:
        return RootResult(roots=(), status=ControlStatus.COMPLETED, iterations=0,
                          backward_errors=(), max_step="0", diagnostic="constant")
    coeffs = poly.coeffs
    ctx = make_context()
    norm = Decimal(0)
    for c in coeffs:
        mag = c.copy_abs()
        if mag > norm:
            norm = mag
    scale = ctx.add(Decimal(1), norm)
    tol_step_base = DK_STEP_TOL
    tol_back = ctx.multiply(DK_BACKWARD_TOL, scale)
    # Durand-Kerner assumes a monic polynomial: normalise exactly once and
    # iterate on the monic image (same roots). Backward errors below are
    # evaluated on the ORIGINAL coefficients with the scale-aware tolerance.
    lead = coeffs[0]
    monic = tuple(ctx.divide(c, lead) for c in coeffs)
    max_iter = MAX_DK_ITER_FACTOR * n
    # Attempt 1: unit spiral. Attempt 2 (deterministic fallback): Cauchy-scaled
    # spiral for far-from-unit or cycle-trapped spectra. No randomness anywhere.
    attempts = [Decimal(1)]
    cauchy = _cauchy_scale(coeffs)
    if cauchy > Decimal("1.5") or cauchy < Decimal("0.5"):
        attempts.append(cauchy)
    else:
        attempts.append(ctx.multiply(cauchy, Decimal(2)))
    current: list = []
    status = ControlStatus.DIVERGED
    iters = 0
    last_step = Decimal(0)
    for attempt_scale in attempts:
        current = _aberrth_init(n, attempt_scale)
        current, status, iters, last_step = _dk_run(monic, current, max_iter, tol_step_base)
        if status == ControlStatus.COMPLETED:
            break
    # Backward-error gate per root.
    errors: list = []
    gate_ok = True
    for z in current:
        pz = _poly_eval_complex(coeffs, z)
        err = pz.modulus()
        errors.append(err)
        if err > tol_back:
            gate_ok = False
    # Sort roots deterministically (by re, then im string order).
    order = sorted(range(n), key=lambda i: (str(current[i].re), str(current[i].im)))
    ordered = tuple(current[i] for i in order)
    ordered_err = tuple(errors[i] for i in order)
    diag = "converged"
    if status == ControlStatus.COMPLETED and not gate_ok:
        status = ControlStatus.DIVERGED
        diag = "non-converged"
    elif status != ControlStatus.COMPLETED and gate_ok:
        # Multiple-root plateau: the step stagnated above the 1e-30 stop
        # rule (attainable accuracy for an m-fold root scales as
        # eps**(1/m)) while every backward error passes. Accepted as
        # COMPLETED through the backward-error gate, explicitly tagged.
        try:
            plateau = Decimal(str(last_step)) <= Decimal("1e-6")
        except Exception:
            plateau = False
        if plateau:
            status = ControlStatus.COMPLETED
            diag = "plateau-accepted via backward-error gate (multiple-root slowdown)"
        else:
            diag = "non-converged"
    return RootResult(
        roots=ordered,
        status=status,
        iterations=iters,
        backward_errors=ordered_err,
        max_step=str(last_step),
        diagnostic=diag,
    )


@dataclass(frozen=True)
class RootValidation:
    n_roots: int
    n_degree: int
    count_ok: bool
    pairing_ok: bool
    pairing_tol: str
    residuals_ok: bool
    detail: str = ""


def validate_roots(poly: Polynomial, result: RootResult,
                   pairing_tol: Decimal = Decimal("1e-24")) -> RootValidation:
    """Count, residual and conjugate-pairing checks for real-coefficient polys."""
    n = poly.degree
    count_ok = len(result.roots) == n
    ctx = make_context()
    norm = Decimal(0)
    for c in poly.coeffs:
        mag = c.copy_abs()
        if mag > norm:
            norm = mag
    tol_back = ctx.multiply(DK_BACKWARD_TOL, ctx.add(Decimal(1), norm))
    residuals_ok = True
    for err in result.backward_errors:
        if err > tol_back:
            residuals_ok = False
    pairing_ok = True
    if n > 0:
        remaining = list(result.roots)
        while remaining:
            z = remaining.pop(0)
            if z.im.copy_abs() <= pairing_tol:
                continue
            mate = None
            for k, w in enumerate(remaining):
                dr = (z.re - w.re).copy_abs()
                di = (z.im + w.im).copy_abs()
                if dr <= pairing_tol and di <= pairing_tol:
                    mate = k
                    break
            if mate is None:
                pairing_ok = False
                break
            remaining.pop(mate)
    detail = "ok" if (count_ok and residuals_ok and pairing_ok) else "mismatch"
    return RootValidation(
        n_roots=len(result.roots),
        n_degree=n,
        count_ok=count_ok,
        pairing_ok=pairing_ok,
        pairing_tol=str(pairing_tol),
        residuals_ok=residuals_ok,
        detail=detail,
    )
