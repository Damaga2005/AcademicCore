"""Problem definition for the F8-D2 complex linear solver.

:class:`ComplexLinearProblem` is an immutable, validated container for one
square system ``A x = b``. It knows no circuits: entries are D1
:class:`RationalComplex` / :class:`DecimalComplex` (plus exact ``int``
shorthand), validated and frozen at construction so the solver can never
observe mutated inputs.

Type policy (exactness boundary):

* all-``RationalComplex`` (``int``/``Fraction`` accepted as exact reals) →
  rational problem, eligible for EXACT and HIGH_PRECISION;
* all-``DecimalComplex`` (``int``/``Decimal`` accepted as exact reals) →
  decimal problem, HIGH_PRECISION only;
* mixed ``RationalComplex`` + ``DecimalComplex`` → every exact entry is
  promoted via ``from_rational`` (the allowed direction) and the problem
  records ``input_promoted=True`` in its provenance;
* ``Fraction`` inside a decimal problem is converted under the working
  context (approximate when non-terminating) and likewise flagged;
* ``float`` / ``complex`` / ``str`` / ``bool`` / ``None`` → ``InvalidEntryError``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from typing import Union

from academic_core.domain.engineering.math.decimal_complex import DecimalComplex
from academic_core.domain.engineering.math.linsolve.errors import (
    DimensionMismatchError,
    EmptySystemError,
    InvalidEntryError,
    NonSquareError,
)
from academic_core.domain.engineering.math.rational import RationalComplex

Entry = Union[RationalComplex, DecimalComplex, int, Fraction, Decimal]


class NumericMode(Enum):
    EXACT = "exact"
    HIGH_PRECISION = "high_precision"
    AUTO = "auto"


@dataclass(frozen=True)
class ComplexMatrix:
    """Immutable validated complex matrix (any m x n, homogeneous entries)."""

    rows: tuple[tuple[RationalComplex | DecimalComplex, ...], ...]
    kind: str  # "rational" | "decimal"

    @property
    def n_rows(self) -> int:
        return len(self.rows)

    @property
    def n_cols(self) -> int:
        return len(self.rows[0]) if self.rows else 0

    def row(self, i: int) -> tuple:
        return self.rows[i]

    def augmented(self, rhs: tuple) -> tuple[tuple, ...]:
        """Return [A | b] rows without touching this matrix."""
        if len(rhs) != self.n_rows:
            raise DimensionMismatchError(
                f"rhs length {len(rhs)} != matrix rows {self.n_rows}"
            )
        return tuple(self.rows[i] + (rhs[i],) for i in range(self.n_rows))

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "n_rows": self.n_rows,
            "n_cols": self.n_cols,
            "rows": [[e.to_dict() for e in row] for row in self.rows],
        }


def _coerce_rational(value: object) -> RationalComplex:
    if isinstance(value, RationalComplex):
        return value
    if isinstance(value, bool):
        raise InvalidEntryError("bool entries are rejected (exactness boundary)")
    if isinstance(value, int):
        return RationalComplex(value, 0)
    if isinstance(value, Fraction):
        return RationalComplex(value, Fraction(0))
    raise InvalidEntryError(
        f"rational problems accept RationalComplex/int/Fraction, "
        f"got {type(value).__name__}"
    )


def _coerce_decimal(value: object) -> tuple[DecimalComplex, bool]:
    """Return (entry, was_approximate_conversion)."""
    from academic_core.domain.engineering.math.trig import make_context

    if isinstance(value, DecimalComplex):
        return value, False
    if isinstance(value, bool):
        raise InvalidEntryError("bool entries are rejected (exactness boundary)")
    if isinstance(value, RationalComplex):
        return DecimalComplex.from_rational(value), True
    if isinstance(value, int):
        return DecimalComplex(value, 0), False
    if isinstance(value, Decimal):
        return DecimalComplex(value, Decimal(0)), False
    if isinstance(value, Fraction):
        ctx = make_context()
        q = ctx.divide(Decimal(value.numerator), Decimal(value.denominator))
        return DecimalComplex(q, Decimal(0)), True
    raise InvalidEntryError(
        f"decimal problems accept DecimalComplex/RationalComplex/int/Decimal/Fraction, "
        f"got {type(value).__name__}"
    )


def _contains_decimal(values: list) -> bool:
    for v in values:
        if isinstance(v, DecimalComplex | Decimal):
            return True
        if isinstance(v, bool):
            raise InvalidEntryError("bool entries are rejected (exactness boundary)")
        if not isinstance(v, RationalComplex | int | Fraction):
            raise InvalidEntryError(
                f"unsupported entry type {type(v).__name__}: rational problems "
                f"accept RationalComplex/int/Fraction, decimal problems additionally "
                f"accept DecimalComplex/Decimal"
            )
    return False


@dataclass(frozen=True)
class ComplexLinearProblem:
    """One validated square system ``A x = b`` ready for :func:`solve`."""

    matrix: ComplexMatrix
    rhs: tuple[RationalComplex | DecimalComplex, ...]
    kind: str  # "rational" | "decimal"
    input_promoted: bool  # True if any exact->approximate conversion occurred

    @property
    def n(self) -> int:
        return self.matrix.n_rows

    @classmethod
    def from_sequences(cls, A: list, b: list) -> "ComplexLinearProblem":
        if not isinstance(A, (list, tuple)) or not isinstance(b, (list, tuple)):
            raise InvalidEntryError("A and b must be sequences")
        if len(A) == 0 or len(b) == 0:
            raise EmptySystemError("empty system (N == 0) is not solvable")
        n = len(A)
        for i, row in enumerate(A):
            if not isinstance(row, (list, tuple)):
                raise DimensionMismatchError(f"row {i} is not a sequence")
            if len(row) != n:
                raise NonSquareError(
                    f"row {i} has length {len(row)} != {n} (square systems only)"
                )
        if len(b) != n:
            raise DimensionMismatchError(f"len(b)={len(b)} != N={n}")
        flat = [v for row in A for v in row] + list(b)
        decimal = _contains_decimal(flat)
        promoted = False
        if not decimal:
            rows = tuple(
                tuple(_coerce_rational(v) for v in row) for row in A
            )
            rhs = tuple(_coerce_rational(v) for v in b)
            kind = "rational"
        else:
            new_rows: list[tuple] = []
            for row in A:
                new_row = []
                for v in row:
                    c, approx = _coerce_decimal(v)
                    promoted = promoted or approx
                    new_row.append(c)
                new_rows.append(tuple(new_row))
            rows = tuple(new_rows)
            rhs_list = []
            for v in b:
                c, approx = _coerce_decimal(v)
                promoted = promoted or approx
                rhs_list.append(c)
            rhs = tuple(rhs_list)
            kind = "decimal"
        return cls(ComplexMatrix(rows, kind), rhs, kind, promoted)

    def to_dict(self) -> dict:
        return {
            "matrix": self.matrix.to_dict(),
            "rhs": [e.to_dict() for e in self.rhs],
            "kind": self.kind,
            "input_promoted": self.input_promoted,
        }
