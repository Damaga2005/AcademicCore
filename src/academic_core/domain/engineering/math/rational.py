"""Exact Gaussian-rationals (F8-D1): ``RationalComplex``.

``RationalComplex`` represents ``re + j*im`` with both components as
``fractions.Fraction``. Every operation is exact: no ``float``, no
``Decimal``, no rounding, no hidden tolerance. Division by an exactly
zero denominator raises ``ZeroDivisionError`` (no epsilon policy here;
near-zero policies belong to the future solver layer).

Promotion rule (one-way only): ``RationalComplex`` may be promoted to
``DecimalComplex`` via :meth:`to_decimal`. There is intentionally no
reverse conversion anywhere in this package: an approximation must
never be turned back into a ``Fraction`` to fake exactness.

Equality is representation-exact. Cross-type ``==`` with the
approximate ``DecimalComplex`` (or with ``float``/``complex``/``str``)
is ``False`` by design, forcing explicit promotion instead of silent
mixing. Equality with real scalars (``int``, ``Fraction``) holds when
the imaginary part is zero; the hash contract is preserved by hashing
bare reals in that case.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:  # pragma: no cover - typing only, no runtime import
    from academic_core.domain.engineering.math.decimal_complex import DecimalComplex

Scalar = Union[int, Fraction]


def _reject_bool(value: object) -> None:
    if isinstance(value, bool):
        raise TypeError("bool is not an accepted operand (exactness boundary)")


@dataclass(frozen=True)
class RationalComplex:
    re: Fraction
    im: Fraction

    def __post_init__(self) -> None:
        re = self.re
        im = self.im
        _reject_bool(re)
        _reject_bool(im)
        if isinstance(re, int):
            object.__setattr__(self, "re", Fraction(re))
        if isinstance(im, int):
            object.__setattr__(self, "im", Fraction(im))
        if not isinstance(self.re, Fraction) or not isinstance(self.im, Fraction):
            raise TypeError(
                "RationalComplex components must be Fraction (or int); "
                f"got re={type(self.re).__name__}, im={type(self.im).__name__}. "
                "float/Decimal/str are rejected to protect exactness."
            )

    # -- construction helpers -------------------------------------------------
    @classmethod
    def zero(cls) -> "RationalComplex":
        return cls(Fraction(0), Fraction(0))

    @classmethod
    def one(cls) -> "RationalComplex":
        return cls(Fraction(1), Fraction(0))

    @classmethod
    def j(cls) -> "RationalComplex":
        return cls(Fraction(0), Fraction(1))

    # -- coercion ---------------------------------------------------------------
    @staticmethod
    def _as_exact(other: object) -> "RationalComplex | None":
        """Coerce real scalars; return None for non-exact foreign types."""
        if isinstance(other, RationalComplex):
            return other
        if isinstance(other, bool):
            raise TypeError("bool is not an accepted operand (exactness boundary)")
        if isinstance(other, int | Fraction):
            return RationalComplex(Fraction(other), Fraction(0))
        return None

    def _promote(self, other: object):
        """Promote self to DecimalComplex for mixed exact/approximate ops."""
        from academic_core.domain.engineering.math.decimal_complex import DecimalComplex

        if isinstance(other, DecimalComplex):
            return self.to_decimal()
        return None

    def _binary(self, other: object, op: str):
        exact = self._as_exact(other)
        if exact is not None:
            a, b, c, d = self.re, self.im, exact.re, exact.im
            if op == "+":
                return RationalComplex(a + c, b + d)
            if op == "-":
                return RationalComplex(a - c, b - d)
            if op == "*":
                return RationalComplex(a * c - b * d, a * d + b * c)
            if op == "/":
                denom = c * c + d * d
                if denom == 0:
                    raise ZeroDivisionError("RationalComplex division by exact zero")
                return RationalComplex(
                    (a * c + b * d) / denom,
                    (b * c - a * d) / denom,
                )
            raise AssertionError(f"unknown op {op}")  # pragma: no cover
        promoted = self._promote(other)
        if promoted is not None:
            return getattr(promoted, {"+": "__add__", "-": "__sub__",
                                      "*": "__mul__", "/": "__truediv__"}[op])(other)
        return NotImplemented

    def _reflected(self, other: object, op: str):
        exact = self._as_exact(other)
        if exact is not None:
            if op == "+":
                return self.__add__(exact)
            if op == "-":
                return exact.__sub__(self)
            if op == "*":
                return self.__mul__(exact)
            if op == "/":
                return exact.__truediv__(self)
            raise AssertionError(f"unknown op {op}")  # pragma: no cover
        promoted = self._promote(other)
        if promoted is not None:
            reflected = {"+": "__radd__", "-": "__rsub__",
                         "*": "__rmul__", "/": "__rtruediv__"}[op]
            return getattr(promoted, reflected)(other)
        return NotImplemented

    # -- arithmetic ---------------------------------------------------------------
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

    def __neg__(self) -> "RationalComplex":
        return RationalComplex(-self.re, -self.im)

    def __pos__(self) -> "RationalComplex":
        return self

    # -- exact operations ------------------------------------------------------------
    def conjugate(self) -> "RationalComplex":
        """conjugate(a + jb) = a - jb (exact)."""
        return RationalComplex(self.re, -self.im)

    def squared_modulus(self) -> Fraction:
        """|z|^2 = re^2 + im^2 as an exact Fraction."""
        return self.re * self.re + self.im * self.im

    def modulus(self) -> Decimal:
        """|z| = sqrt(re^2 + im^2) as an explicitly approximate Decimal.

        The squared modulus is exactly rational, but its root is
        generally irrational, so it can never inhabit ``Fraction``.
        Computed with an explicit working-precision context; the global
        Decimal context is untouched.
        """
        from academic_core.domain.engineering.math.decimal_complex import decimal_modulus_of_fractions

        return decimal_modulus_of_fractions(self.re, self.im)

    def is_zero_exact(self) -> bool:
        """True iff re == 0 and im == 0 (literally; no tolerance)."""
        return self.re == 0 and self.im == 0

    # -- promotion (allowed direction) -------------------------------------------
    def to_decimal(self) -> "DecimalComplex":
        """Promote to ``DecimalComplex`` (exact -> approximate, one-way)."""
        from academic_core.domain.engineering.math.decimal_complex import DecimalComplex

        return DecimalComplex.from_rational(self)

    # -- equality / hashing --------------------------------------------------------
    def __eq__(self, other: object) -> bool:
        if isinstance(other, RationalComplex):
            return self.re == other.re and self.im == other.im
        if isinstance(other, bool):
            return NotImplemented
        if isinstance(other, int | Fraction):
            return self.im == 0 and self.re == other
        return NotImplemented

    def __hash__(self) -> int:
        # Numeric-tower consistent: a real-valued RationalComplex hashes
        # like the bare real it equals, so z == k implies hash(z) == hash(k).
        if self.im == 0:
            return hash(self.re)
        return hash((self.re, self.im))

    # -- deterministic representation ----------------------------------------------
    def __repr__(self) -> str:
        return f"RationalComplex(re={self.re!r}, im={self.im!r})"

    def to_dict(self) -> dict:
        """Deterministic mapping for debugging/provenance/tests (no DB)."""
        return {"type": "rational_complex", "re": str(self.re), "im": str(self.im)}

    @classmethod
    def from_dict(cls, data: dict) -> "RationalComplex":
        if not isinstance(data, dict) or data.get("type") != "rational_complex":
            raise ValueError("not a rational_complex mapping")
        try:
            re = Fraction(str(data["re"]))
            im = Fraction(str(data["im"]))
        except (KeyError, ValueError, ZeroDivisionError) as exc:
            raise ValueError(f"bad rational_complex mapping: {exc}") from exc
        return cls(re, im)
