"""Typed input/config errors for the F8-D2 complex linear solver.

Mathematical states (SOLVED / SINGULAR / INCONSISTENT / NUMERICALLY_UNCERTAIN)
are reported in-band as :class:`SolveStatus`, never as exceptions. Exceptions
are reserved for invalid input, bad dimensions, incompatible types,
non-square systems, corrupt data, and invalid configuration.
"""

from __future__ import annotations


class ComplexLinearError(ValueError):
    """Base class for all F8-D2 solver input/configuration errors."""


class EmptySystemError(ComplexLinearError):
    """Raised for an empty matrix (N == 0) or an empty right-hand side."""


class NonSquareError(ComplexLinearError):
    """Raised when A is not square (the solver handles square systems only)."""


class DimensionMismatchError(ComplexLinearError):
    """Raised when row lengths differ or len(b) != N."""


class InvalidEntryError(ComplexLinearError):
    """Raised for entries that are not D1 complex numbers (or exact ints).

    float / complex / str / bool entries are rejected to protect the
    exactness boundary; Decimal entries belong to decimal problems only
    and Fraction entries belong to rational problems only.
    """


class InvalidModeError(ComplexLinearError):
    """Raised for an unknown mode or a mode incompatible with the data.

    In particular, EXACT mode on decimal (approximate) data is refused:
    rounding the inputs and then claiming an exact solve would fake
    exactness.
    """
