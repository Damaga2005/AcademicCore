"""High-precision complex numbers (F8-D1): ``DecimalComplex``.

``DecimalComplex`` represents ``re + j*im`` with both components as
``decimal.Decimal``. All arithmetic runs through an explicit working
context (``WORKING_PRECISION = 50`` significant digits); the ambient
global Decimal context is never read for rounding and never mutated.
Note that even unary ``-x`` on a ``Decimal`` would apply the *global*
context, so negation also goes through the explicit context.

Precision semantics: 50 digits is a *working precision*, not a claim
of 50 mathematically correct digits. Every value here is a
high-precision numerical approximation — the exact algebraic twin is
``RationalComplex``. The two are deliberately kept apart:

* ``RationalComplex -> DecimalComplex`` is allowed (``from_rational`` /
  ``RationalComplex.to_decimal``). Non-terminating rationals such as
  1/3 are rounded once to working precision; that rounding is the
  exactness boundary and is documented, not hidden.
* ``DecimalComplex -> RationalComplex`` is FORBIDDEN. No method, helper
  or debug hook in this package converts an approximation back into a
  ``Fraction``. ``Fraction(decimal_value)`` must never be used to fake
  recovered exactness.

Zero semantics: ``__eq__`` is representation-exact
(``DecimalComplex(1e-30, 0) != DecimalComplex(0, 0)``). Deciding that a
tiny-but-nonzero value *counts* as zero is a solver tolerance policy
and lives in a future layer, not here. The explicit opt-in is
:meth:`is_zero`, which requires the caller to pass a tolerance.
Division distinguishes an exactly-zero denominator
(``ZeroDivisionError``) from a merely small one (computed normally).

Phase semantics: :meth:`phase` returns radians in (-pi, pi] as an
explicitly approximate ``Decimal``. ``complex_from_polar`` takes an
explicitly approximate radian angle; magnitude may be ``int``,
``Fraction`` or ``Decimal``. No degrees/radians unit semantics live
here (no Hz, rad/s, deg, rad quantities); those belong to the future
OperatingPoint / AC-domain layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Union

from academic_core.domain.engineering.math.trig import (
    WORKING_PRECISION,
    decimal_atan2,
    decimal_cos,
    decimal_pi,
    decimal_sin,
    decimal_sqrt,
    make_context,
)

__all__ = [
    "WORKING_PRECISION",
    "DecimalComplex",
    "complex_from_polar",
    "decimal_modulus_of_fractions",
]

Scalar = Union[int, Decimal, Fraction]


def decimal_modulus_of_fractions(re: Fraction, im: Fraction) -> Decimal:
    """sqrt(re^2 + im^2) for exact Fraction inputs, as approximate Decimal.

    Shared by ``RationalComplex.modulus`` so the (exact -> approximate)
    root computation has a single implementation and a single precision
    story: the Fraction sum of squares is exact, its Decimal conversion
    and root are rounded under the explicit working context.
    """
    ctx = make_context()
    num = re.numerator * re.numerator + im.numerator * im.numerator
    den = re.denominator * re.denominator
    # Common denominator re^2 + im^2 = (a^2 d^2 + c^2 b^2)/(b^2 d^2);
    # recompute exactly rather than trusting component-wise assembly.
    a, b = re.numerator, re.denominator
    c, d = im.numerator, im.denominator
    num = a * a * d * d + c * c * b * b
    den = b * b * d * d
    value = ctx.divide(Decimal(num), Decimal(den))
    return ctx.sqrt(value)


@dataclass(frozen=True)
class DecimalComplex:
    re: Decimal
    im: Decimal

    def __post_init__(self) -> None:
        re = self.re
        im = self.im
        if isinstance(re, bool) or isinstance(im, bool):
            raise TypeError("bool is not an accepted component (exactness boundary)")
        if isinstance(re, int):
            object.__setattr__(self, "re", Decimal(re))
        if isinstance(im, int):
            object.__setattr__(self, "im", Decimal(im))
        if not isinstance(self.re, Decimal) or not isinstance(self.im, Decimal):
            raise TypeError(
                "DecimalComplex components must be Decimal (or int); "
                f"got re={type(self.re).__name__}, im={type(self.im).__name__}. "
                "float/complex/Fraction/str are rejected at construction: "
                "use from_rational() for the explicit exact->approximate step."
            )

    # -- construction --------------------------------------------------------
    @classmethod
    def from_rational(cls, z: "RationalComplex") -> "DecimalComplex":
        """Explicit exact -> approximate promotion (the only allowed way in).

        Each component is rounded once under the working context, so
        non-terminating rationals (1/3, 1/7, ...) become their 50-digit
        approximations. That rounding IS the exactness boundary.
        """
        from academic_core.domain.engineering.math.rational import RationalComplex as RC

        if not isinstance(z, RC):
            raise TypeError(f"from_rational needs a RationalComplex, got {type(z).__name__}")
        ctx = make_context()
        re = ctx.divide(Decimal(z.re.numerator), Decimal(z.re.denominator))
        im = ctx.divide(Decimal(z.im.numerator), Decimal(z.im.denominator))
        return cls(re, im)

    @classmethod
    def zero(cls) -> "DecimalComplex":
        return cls(Decimal(0), Decimal(0))

    @classmethod
    def one(cls) -> "DecimalComplex":
        return cls(Decimal(1), Decimal(0))

    @classmethod
    def j(cls) -> "DecimalComplex":
        return cls(Decimal(0), Decimal(1))

    # -- coercion -------------------------------------------------------------
    @staticmethod
    def _as_complex(other: object) -> tuple["DecimalComplex", bool] | None:
        """Coerce (int | Decimal | Fraction | RationalComplex | DecimalComplex).

        Returns (value, was_approximate_input). Fraction and
        RationalComplex inputs are converted under the working context
        and are therefore approximations when non-terminating.
        Returns None for foreign types (float/complex/str/...).
        """
        from academic_core.domain.engineering.math.rational import RationalComplex as RC

        if isinstance(other, DecimalComplex):
            return other, False
        if isinstance(other, bool):
            raise TypeError("bool is not an accepted operand (exactness boundary)")
        if isinstance(other, int):
            return DecimalComplex(Decimal(other), Decimal(0)), False
        if isinstance(other, Decimal):
            return DecimalComplex(other, Decimal(0)), False
        if isinstance(other, Fraction):
            ctx = make_context()
            q = ctx.divide(Decimal(other.numerator), Decimal(other.denominator))
            return DecimalComplex(q, Decimal(0)), True
        if isinstance(other, RC):
            return DecimalComplex.from_rational(other), True
        return None

    def _binary(self, other: object, op: str):
        coerced = self._as_complex(other)
        if coerced is None:
            return NotImplemented
        rhs, _ = coerced
        ctx = make_context()
        a, b, c, d = self.re, self.im, rhs.re, rhs.im
        if not b and not d:
            zero = Decimal(0)
            if op == "+":
                return DecimalComplex(ctx.add(a, c), zero)
            if op == "-":
                return DecimalComplex(ctx.subtract(a, c), zero)
            if op == "*":
                return DecimalComplex(ctx.multiply(a, c), zero)
            if op == "/":
                if c == 0:
                    raise ZeroDivisionError(
                        "DecimalComplex division by exactly zero; "
                        "near-zero denominators are NOT collapsed to zero here "
                        "(singularity policy belongs to the solver layer)"
                    )
                return DecimalComplex(ctx.divide(a, c), zero)
        if op == "+":
            return DecimalComplex(ctx.add(a, c), ctx.add(b, d))
        if op == "-":
            return DecimalComplex(ctx.subtract(a, c), ctx.subtract(b, d))
        if op == "*":
            re = ctx.subtract(ctx.multiply(a, c), ctx.multiply(b, d))
            im = ctx.add(ctx.multiply(a, d), ctx.multiply(b, c))
            return DecimalComplex(re, im)
        if op == "/":
            denom = ctx.add(ctx.multiply(c, c), ctx.multiply(d, d))
            if denom == 0:
                raise ZeroDivisionError(
                    "DecimalComplex division by exactly zero; "
                    "near-zero denominators are NOT collapsed to zero here "
                    "(singularity policy belongs to the solver layer)"
                )
            re = ctx.divide(
                ctx.add(ctx.multiply(a, c), ctx.multiply(b, d)), denom
            )
            im = ctx.divide(
                ctx.subtract(ctx.multiply(b, c), ctx.multiply(a, d)), denom
            )
            return DecimalComplex(re, im)
        raise AssertionError(f"unknown op {op}")  # pragma: no cover

    def _reflected(self, other: object, op: str):
        coerced = self._as_complex(other)
        if coerced is None:
            return NotImplemented
        lhs, _ = coerced
        if op == "+":
            return lhs.__add__(self)
        if op == "-":
            return lhs.__sub__(self)
        if op == "*":
            return lhs.__mul__(self)
        if op == "/":
            return lhs.__truediv__(self)
        raise AssertionError(f"unknown op {op}")  # pragma: no cover

    # -- arithmetic ------------------------------------------------------------
    def __add__(self, other: object):
        return self._binary(other, "+")

    def __radd__(self, other: object):
        return self._reflected(other, "+")

    def __sub__(self, other: object):
        return self._binary(other, "-")

    def __rsub__(self, other: object):
        return self._reflected(other, "-")

    def __mul__(self, other: object):
        return self._binary(other, "*")

    def __rmul__(self, other: object):
        return self._reflected(other, "*")

    def __truediv__(self, other: object):
        return self._binary(other, "/")

    def __rtruediv__(self, other: object):
        return self._reflected(other, "/")

    def __neg__(self) -> "DecimalComplex":
        # NOTE: unary -Decimal would apply the *global* context; use ours.
        ctx = make_context()
        return DecimalComplex(ctx.minus(self.re), ctx.minus(self.im))

    def __pos__(self) -> "DecimalComplex":
        return self

    # -- structure -----------------------------------------------------------------
    def conjugate(self) -> "DecimalComplex":
        """conjugate(a + jb) = a - jb (context-explicit negation)."""
        ctx = make_context()
        return DecimalComplex(ctx.plus(self.re), ctx.minus(self.im))

    def squared_modulus(self) -> Decimal:
        """|z|^2 under the working context (controlled precision)."""
        re = self.re
        im = self.im
        ctx = make_context()
        if not im:
            return ctx.multiply(re, re)
        return ctx.add(ctx.multiply(re, re), ctx.multiply(im, im))

    def modulus(self) -> Decimal:
        """|z| = sqrt(re^2 + im^2) under the working context (approximate)."""
        re = self.re
        im = self.im
        if not im:
            # copy_abs() flips the sign bit only; it performs no rounding
            # and never touches the ambient global decimal context. The
            # bare builtin abs(re) is WRONG here: for a Decimal operand it
            # implicitly rounds through decimal.getcontext() (default 28
            # significant digits), silently truncating a 50-digit working
            # value down to 28 digits whenever im is exactly zero -- e.g.
            # every purely resistive branch power. That truncation alone
            # was enough to break P/|S| power-factor equality (~1E-28
            # spurious deviation from unity) despite the numerator (P)
            # keeping its full 50-digit precision.
            return re.copy_abs()
        ctx = make_context()
        return ctx.sqrt(self.squared_modulus())

    def is_zero_exact(self) -> bool:
        """True iff both components are literally Decimal(0)."""
        return self.re == 0 and self.im == 0

    def is_zero(self, tolerance: Decimal) -> bool:
        """Explicit-tolerance zero test: |z| <= tolerance.

        The tolerance is a required argument precisely so no threshold
        can hide inside ``__eq__``. Solver-grade thresholds (tau_sing,
        tau_unc, tau_tol) must NOT be imported here; the caller owns them.
        """
        if isinstance(tolerance, bool) or not isinstance(tolerance, Decimal):
            raise TypeError("is_zero tolerance must be a Decimal passed explicitly")
        if tolerance < 0:
            raise ValueError("is_zero tolerance must be non-negative")
        return self.modulus() <= tolerance

    def sqrt(self) -> "DecimalComplex":
        """Principal square root (approximate, branch cut on (-inf, 0]).

        sqrt(-1) = +j. sqrt(0) = 0. Results are working-precision
        approximations, never exact objects.
        """
        ctx = make_context()
        if self.is_zero_exact():
            return DecimalComplex.zero()
        if self.im == 0 and self.re < 0:
            return DecimalComplex(Decimal(0), ctx.sqrt(ctx.minus(self.re)))
        r = self.modulus()
        half = Decimal(2)
        re_part = ctx.sqrt(ctx.divide(ctx.add(r, self.re), half))
        im_part = ctx.sqrt(ctx.divide(ctx.subtract(r, self.re), half))
        if self.im < 0:
            im_part = ctx.minus(im_part)
        return DecimalComplex(re_part, im_part)

    def phase(self) -> Decimal:
        """Argument in radians, (-pi, pi], explicitly approximate Decimal.

        phase(j) is conceptually pi/2; the returned Decimal is its
        50-digit approximation, and no exactness is claimed. phase(0+0j)
        returns Decimal(0) by numerical convention (undefined, no
        physical meaning is attached here).
        """
        return decimal_atan2(self.im, self.re)

    # -- equality / hashing --------------------------------------------------------
    def __eq__(self, other: object) -> bool:
        if isinstance(other, DecimalComplex):
            return self.re == other.re and self.im == other.im
        if isinstance(other, bool):
            return NotImplemented
        if isinstance(other, int | Decimal):
            return self.im == 0 and self.re == other
        # RationalComplex, Fraction, float, complex, str: never silently
        # equal; cross-representation comparison requires explicit promotion.
        return NotImplemented

    def __hash__(self) -> int:
        # Numeric-tower consistent: a real-valued DecimalComplex hashes
        # like the bare real it equals, so z == k implies hash(z)==hash(k).
        if self.im == 0:
            return hash(self.re)
        return hash((self.re, self.im))

    # -- deterministic representation ----------------------------------------------
    def __repr__(self) -> str:
        return f"DecimalComplex(re={self.re!r}, im={self.im!r})"

    def to_dict(self) -> dict:
        """Deterministic mapping for debugging/provenance/tests (no DB)."""
        return {
            "type": "decimal_complex",
            "re": format(self.re, "f"),
            "im": format(self.im, "f"),
            "precision": WORKING_PRECISION,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DecimalComplex":
        if not isinstance(data, dict) or data.get("type") != "decimal_complex":
            raise ValueError("not a decimal_complex mapping")
        if data.get("precision") != WORKING_PRECISION:
            raise ValueError(
                f"decimal_complex precision mismatch: {data.get('precision')!r} "
                f"!= WORKING_PRECISION ({WORKING_PRECISION})"
            )
        try:
            re = Decimal(str(data["re"]))
            im = Decimal(str(data["im"]))
        except (KeyError, ArithmeticError, ValueError) as exc:
            raise ValueError(f"bad decimal_complex mapping: {exc}") from exc
        return cls(re, im)


def complex_from_polar(
    magnitude: int | Fraction | Decimal,
    angle: Decimal,
) -> DecimalComplex:
    """Build DecimalComplex from polar coordinates (approximate).

    * ``magnitude``: real only (``int`` | ``Fraction`` | ``Decimal``);
      ``Fraction`` inputs are converted under the working context.
    * ``angle``: explicitly approximate radians (``Decimal``); no
      degrees/radians unit semantics are attached here — the caller
      declares the convention, and radian input is assumed.

    Returns ``magnitude * (cos(angle) + j*sin(angle))`` under the
    working context. If polar construction ever needs richer semantics
    (unit-aware angles, exact axis phases), it belongs to a future
    AC-domain layer, not D1.
    """
    from academic_core.domain.engineering.math.rational import RationalComplex as RC

    if isinstance(magnitude, bool) or isinstance(angle, bool):
        raise TypeError("bool is not an accepted input (exactness boundary)")
    if isinstance(magnitude, RC):
        raise TypeError(
            "complex_from_polar magnitude must be real (int | Fraction | Decimal); "
            "a RationalComplex magnitude is ambiguous — promote explicitly first"
        )
    if isinstance(magnitude, int):
        mag = Decimal(magnitude)
    elif isinstance(magnitude, Fraction):
        ctx0 = make_context()
        mag = ctx0.divide(Decimal(magnitude.numerator), Decimal(magnitude.denominator))
    elif isinstance(magnitude, Decimal):
        mag = magnitude
    else:
        raise TypeError(
            f"magnitude must be int | Fraction | Decimal, got {type(magnitude).__name__}; "
            "float/complex are rejected (exactness boundary)"
        )
    if not isinstance(angle, Decimal):
        raise TypeError(
            f"angle must be an explicitly approximate Decimal (radians), "
            f"got {type(angle).__name__}"
        )
    ctx = make_context()
    c = decimal_cos(angle, ctx)
    s = decimal_sin(angle, ctx)
    return DecimalComplex(ctx.multiply(mag, c), ctx.multiply(mag, s))


def decimal_pi_value() -> Decimal:
    """Pi as a working-precision Decimal approximation (documented source).

    Computed from Machin's identity (16*arctan(1/5) - 4*arctan(1/239))
    in pure Decimal; no float constant is embedded anywhere.
    """
    return decimal_pi()
