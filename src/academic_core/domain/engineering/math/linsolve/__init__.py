"""F8-D2 complex linear solver: generic ``A x = b`` over D1 complex numbers.

EXACT mode eliminates over ``RationalComplex`` (no tolerances); the
HIGH_PRECISION mode equilibrates and eliminates over ``DecimalComplex``
under the explicit D1 working context with an explicit uncertainty
policy. Statuses: SOLVED, SINGULAR, INCONSISTENT, NUMERICALLY_UNCERTAIN.

Circuit-agnostic: no Circuit, Component, Quantity, ngspice, Qt, SQLite.
Coexists with F8-B (which is untouched); F8-D3 reuses this package.
"""

from academic_core.domain.engineering.math.linsolve.errors import (
    ComplexLinearError,
    DimensionMismatchError,
    EmptySystemError,
    InvalidEntryError,
    InvalidModeError,
    NonSquareError,
)
from academic_core.domain.engineering.math.linsolve.problem import (
    ComplexLinearProblem,
    ComplexMatrix,
    NumericMode,
)
from academic_core.domain.engineering.math.linsolve.result import (
    LinearSolveResult,
    SolveStatus,
)
from academic_core.domain.engineering.math.linsolve.solver import (
    SOLVER_VERSION,
    conjugate_system,
    matvec,
    solve,
)

__all__ = [
    "SOLVER_VERSION",
    "ComplexLinearError",
    "DimensionMismatchError",
    "EmptySystemError",
    "InvalidEntryError",
    "InvalidModeError",
    "NonSquareError",
    "ComplexLinearProblem",
    "ComplexMatrix",
    "NumericMode",
    "LinearSolveResult",
    "SolveStatus",
    "conjugate_system",
    "matvec",
    "solve",
]
