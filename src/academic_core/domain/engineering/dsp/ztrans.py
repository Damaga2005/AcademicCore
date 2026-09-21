"""F8-P2 unilateral Z-transform + rational H(z) (NEW).

Convention (explicit, canonical): ascending powers of ``w = z^-1``,
    H(z) = (b_0 + b_1·w + … + b_M·w^M) / (a_0 + a_1·w + … + a_N·w^N),
with ``a_0 ≠ 0`` and ``M ≤ N`` (causal properness; violation →
INVALID). Construction normalises once to descending P1 polynomials
in ``w`` (deterministic reversal) and REUSEs P1 Horner/GCD/algebra —
no second polynomial engine exists here.

Causal unilateral pairs carry their exterior ROC ``|z| > R`` (recorded
radius, ``R = 0`` for FIR/δ). Delay is a coefficient-level operation
(prepending zeros); the constructor rule guards standalone properness,
so delayed systems compose through documented coefficient helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence as _TypingSequence

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.control.poly import Polynomial, make_polynomial
from academic_core.domain.engineering.math import DecimalComplex, make_context

MAX_Z_ORDER = 32


def _as_decimal(value: object, label: str) -> Decimal:
    if isinstance(value, bool):
        raise ControlError(ControlStatus.INVALID, label + " rejects bool")
    if isinstance(value, Decimal):
        out = value
    elif isinstance(value, int):
        out = Decimal(value)
    elif isinstance(value, str):
        try:
            out = Decimal(value.strip())
        except Exception as exc:
            raise ControlError(ControlStatus.INVALID, label + " bad string") from exc
    else:
        raise ControlError(ControlStatus.INVALID, label + " must be Decimal/int/str")
    if not out.is_finite():
        raise ControlError(ControlStatus.INVALID, label + " must be finite")
    return out


def _as_ascending(values: object, label: str) -> tuple:
    if not isinstance(values, (tuple, list)) or len(values) == 0:
        raise ControlError(ControlStatus.INVALID, label + " needs a non-empty tuple/list")
    if len(values) - 1 > MAX_Z_ORDER:
        raise ControlError(ControlStatus.INVALID, "filter order exceeds 32")
    return tuple(_as_decimal(v, label) for v in values)


def _descending(ascending: tuple) -> Polynomial:
    """Ascending-in-w coefficients → descending P1 polynomial in w."""
    return make_polynomial(tuple(reversed(ascending)))


@dataclass(frozen=True)
class TransferFunctionZ:
    """Causal-proper rational H(z) in w = z^-1 (validation-only post-init).

    Sub-design resolution D-R1: a constant nonzero denominator (pure
    feedforward/FIR, H(∞) = b_0/a_0 finite) is always causal, so the
    length rule applies only when the denominator has dynamics
    (order ≥ 1). Genuinely feedback-improper forms stay INVALID.
    """

    num_w: tuple
    den_w: tuple
    roc_radius: Decimal | None

    def __post_init__(self) -> None:
        for label, item in (("num_w", self.num_w), ("den_w", self.den_w)):
            if not isinstance(item, tuple) or len(item) == 0:
                raise ControlError(ControlStatus.INVALID, label + " must be a non-empty tuple")
            for c in item:
                if isinstance(c, bool) or not isinstance(c, Decimal):
                    raise ControlError(ControlStatus.INVALID, label + " entries must be Decimal")
                if not c.is_finite():
                    raise ControlError(ControlStatus.INVALID, label + " entries must be finite")
        if len(self.num_w) - 1 > MAX_Z_ORDER or len(self.den_w) - 1 > MAX_Z_ORDER:
            raise ControlError(ControlStatus.INVALID, "filter order exceeds 32")
        if self.den_w[0] == 0:
            raise ControlError(ControlStatus.INVALID, "delay-free denominator term a_0 != 0 required")
        if len(self.den_w) > 1 and len(self.num_w) > len(self.den_w):
            raise ControlError(ControlStatus.INVALID, "non-causal/improper H(z) rejected")
        if self.roc_radius is not None:
            if isinstance(self.roc_radius, bool) or not isinstance(self.roc_radius, Decimal):
                raise ControlError(ControlStatus.INVALID, "ROC radius must be Decimal/None")
            if not self.roc_radius.is_finite() or self.roc_radius < 0:
                raise ControlError(ControlStatus.INVALID, "ROC radius >= 0 required")

    @property
    def order(self) -> int:
        return len(self.den_w) - 1

    @staticmethod
    def create(num: _TypingSequence[object], den: _TypingSequence[object],
               roc: object = None) -> "TransferFunctionZ":
        num_t = _as_ascending(num, "numerator")
        den_t = _as_ascending(den, "denominator")
        radius = None
        if roc is not None:
            radius = _as_decimal(roc, "ROC radius")
            if radius < 0:
                raise ControlError(ControlStatus.INVALID, "ROC radius >= 0 required")
        return TransferFunctionZ(num_w=num_t, den_w=den_t, roc_radius=radius)

    def num_poly(self) -> Polynomial:
        return _descending(self.num_w)

    def den_poly(self) -> Polynomial:
        # Ascending may carry trailing (high-w) zeros from delay forms;
        # strip deterministically to a valid descending polynomial.
        trimmed = list(self.den_w)
        while len(trimmed) > 1 and trimmed[-1] == 0:
            trimmed.pop()
        return _descending(tuple(trimmed))

    def evaluate(self, z: DecimalComplex) -> DecimalComplex:
        """Horner at w_0 = 1/z_0 (REUSEd P1 evaluation in w)."""
        if not isinstance(z, DecimalComplex):
            raise ControlError(ControlStatus.INVALID, "evaluation point must be DecimalComplex")
        if z.is_zero_exact():
            raise ControlError(ControlStatus.SINGULAR, "H(0) degenerate in w = 1/z")
        try:
            w0 = DecimalComplex(Decimal(1), Decimal(0)) / z
        except ZeroDivisionError as exc:
            raise ControlError(ControlStatus.SINGULAR, "w = 1/z singular") from exc
        den_val = self.den_poly().evaluate(w0)
        if den_val.is_zero_exact():
            raise ControlError(ControlStatus.SINGULAR, "pole evaluation A(w) = 0")
        num_val = self.num_poly().evaluate(w0)
        try:
            return num_val / den_val
        except ZeroDivisionError as exc:
            raise ControlError(ControlStatus.SINGULAR, "pole evaluation") from exc

    def to_dict(self) -> dict:
        return {
            "num_w": [str(c) for c in self.num_w],
            "den_w": [str(c) for c in self.den_w],
            "roc_radius": "" if self.roc_radius is None else str(self.roc_radius),
        }


def make_hz(num: _TypingSequence[object], den: _TypingSequence[object],
            roc: object = None) -> TransferFunctionZ:
    return TransferFunctionZ.create(num, den, roc)


def series_z(first: TransferFunctionZ, second: TransferFunctionZ) -> TransferFunctionZ:
    """Cascade H = H1·H2 (REUSEd P1 coefficient arithmetic in w)."""
    if not isinstance(first, TransferFunctionZ) or not isinstance(second, TransferFunctionZ):
        raise ControlError(ControlStatus.INVALID, "cascade needs two H(z)")
    num = first.num_poly().multiply(second.num_poly())
    den = first.den_poly().multiply(second.den_poly())
    num_asc = tuple(reversed(num.coeffs))
    den_asc = tuple(reversed(den.coeffs))
    if len(num_asc) > len(den_asc):
        raise ControlError(ControlStatus.INVALID, "cascade result improper")
    return TransferFunctionZ(num_w=num_asc, den_w=den_asc, roc_radius=None)


def feedback_z(loop: TransferFunctionZ) -> TransferFunctionZ:
    """Unity negative feedback T = L/(1+L) with the static-gain path."""
    if not isinstance(loop, TransferFunctionZ):
        raise ControlError(ControlStatus.INVALID, "feedback needs a loop H(z)")
    den_sum = loop.den_poly().add(loop.num_poly())
    if all(c == 0 for c in den_sum.coeffs):
        raise ControlError(ControlStatus.SINGULAR, "feedback singular (1 + L = 0)")
    num_asc = tuple(reversed(loop.num_poly().coeffs))
    den_asc = tuple(reversed(den_sum.coeffs))
    if len(num_asc) > len(den_asc):
        raise ControlError(ControlStatus.INVALID, "feedback result improper")
    return TransferFunctionZ(num_w=num_asc, den_w=den_asc, roc_radius=None)


def sensitivity_z(loop: TransferFunctionZ) -> TransferFunctionZ:
    """S = 1/(1+L) sharing one denominator object with T (S+T exact)."""
    if not isinstance(loop, TransferFunctionZ):
        raise ControlError(ControlStatus.INVALID, "sensitivity needs a loop H(z)")
    den_sum = loop.den_poly().add(loop.num_poly())
    den_asc = tuple(reversed(den_sum.coeffs))
    one = make_polynomial((Decimal(1),))
    num_asc = tuple(reversed(loop.den_poly().multiply(one).coeffs))
    # Pad the numerator view to causal length without changing its value.
    while len(num_asc) < len(den_asc):
        num_asc = num_asc + (Decimal(0),)
    return TransferFunctionZ(num_w=num_asc, den_w=den_asc, roc_radius=None)


def complementary_z(loop: TransferFunctionZ) -> TransferFunctionZ:
    """T = L/(1+L) sharing one denominator object with S (S+T exact)."""
    if not isinstance(loop, TransferFunctionZ):
        raise ControlError(ControlStatus.INVALID, "complementary needs a loop H(z)")
    den_sum = loop.den_poly().add(loop.num_poly())
    den_asc = tuple(reversed(den_sum.coeffs))
    num_asc = tuple(reversed(loop.num_poly().coeffs))
    while len(num_asc) < len(den_asc):
        num_asc = num_asc + (Decimal(0),)
    return TransferFunctionZ(num_w=num_asc, den_w=den_asc, roc_radius=None)


def delay_coeffs(num: _TypingSequence[object], den: _TypingSequence[object],
                 steps: int) -> tuple:
    """Coefficient-level delay w^k·H (prepend k zeros, exact).

    The standalone constructor rule guards properness; delay composes at
    coefficient level so the pair identity stays exact and testable.
    """
    num_t = _as_ascending(num, "numerator")
    den_t = _as_ascending(den, "denominator")
    if isinstance(steps, bool) or not isinstance(steps, int) or steps < 0:
        raise ControlError(ControlStatus.INVALID, "delay steps >= 0 required")
    if len(num_t) + steps - 1 > MAX_Z_ORDER:
        raise ControlError(ControlStatus.INVALID, "delayed order exceeds 32")
    return (Decimal(0),) * steps + num_t, den_t


def z_pair(name: str, params: dict | None = None) -> TransferFunctionZ:
    """Closed-form causal pairs (O(1), analytic, ROC recorded).

    delta{} | step{} | geometric{a} | ramp{a} with
    δ↔1 (R=0); u↔1/(1−w) (R=1); a^n·u↔1/(1−a·w) (R=|a|);
    n·a^n·u↔a·w/(1−a·w)² (R=|a|).
    """
    if not isinstance(name, str):
        raise ControlError(ControlStatus.INVALID, "pair name must be a string")
    args = dict(params or {})
    key = name.strip().lower()

    def req(field: str) -> Decimal:
        return _as_decimal(args.get(field), "pair param " + field)

    if key == "delta":
        return TransferFunctionZ.create((Decimal(1),), (Decimal(1),), Decimal(0))
    if key == "step":
        return TransferFunctionZ.create((Decimal(1),), (Decimal(1), Decimal(-1)), Decimal(1))
    if key == "geometric":
        base = req("a")
        ctx = make_context()
        return TransferFunctionZ.create(
            (Decimal(1),), (Decimal(1), ctx.minus(base)), base.copy_abs())
    if key == "ramp":
        base = req("a")
        ctx = make_context()
        two_a = ctx.multiply(Decimal(2), base)
        a_sq = ctx.multiply(base, base)
        return TransferFunctionZ.create(
            (Decimal(0), base), (Decimal(1), ctx.minus(two_a), a_sq), base.copy_abs())
    raise ControlError(ControlStatus.UNSUPPORTED, "unknown Z pair " + name.strip())
