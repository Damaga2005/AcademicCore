"""F8-D1 complex numeric foundation: pure, deterministic math package.

Two canonical immutable types with a strict exactness boundary:

* :class:`RationalComplex` — exact Gaussian rationals ``Q(j)`` on
  ``Fraction`` components. No float, no Decimal, no tolerance.
* :class:`DecimalComplex` — high-precision ``Decimal`` complex numbers
  under an explicit 50-digit working context. Approximations, never
  exact claims.

One-way promotion: ``RationalComplex -> DecimalComplex`` is allowed;
``DecimalComplex -> RationalComplex`` is forbidden (no such API exists
anywhere in this package, by design).

This package is circuit-agnostic: it imports nothing from
``circuit``, ``Component``, ``Quantity``, ngspice adapters, Qt or
SQLite, so F8-D2 (complex linear algebra) through F8-D5 can reuse it
without dragging the circuit domain along.

Security: pure math only — no eval/exec/compile/dynamic imports,
no child processes or shell, no filesystem/network access, no pickle/marshal.
"""

from academic_core.domain.engineering.math.decimal_complex import (
    DecimalComplex,
    complex_from_polar,
    decimal_modulus_of_fractions,
    decimal_pi_value,
)
from academic_core.domain.engineering.math.logarithm import (
    decimal_ln10,
    decimal_log10,
    decimal_nth_root,
)
from academic_core.domain.engineering.math.rational import RationalComplex
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
    "RationalComplex",
    "DecimalComplex",
    "complex_from_polar",
    "decimal_modulus_of_fractions",
    "decimal_pi_value",
    "decimal_atan2",
    "decimal_cos",
    "decimal_pi",
    "decimal_sin",
    "decimal_sqrt",
    "make_context",
    "decimal_ln10",
    "decimal_log10",
    "decimal_nth_root",
]
