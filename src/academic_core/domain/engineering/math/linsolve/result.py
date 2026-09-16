"""Result type for the F8-D2 complex linear solver.

Fields that cannot be determined rigorously are ``None`` with an
explanation in ``diagnostics`` — never invented values:

* ``working_precision`` is ``None`` in EXACT mode (exact arithmetic has
  no finite working precision);
* ``solution`` / ``residual`` are ``None`` for SINGULAR / INCONSISTENT
  (no unique solution exists to check);
* ``backward_error`` is ``None`` when no solution exists.

Norm convention (used for both residual and backward error): the
max-modulus norm — ``||v|| = max_i |v_i|`` with ``Decimal`` moduli, and
``||A|| = max entry modulus``. It is scale-aware through the explicit
``scale`` denominator, cheap, deterministic, and needs no square roots
of sums. It is NOT an operator norm and is never presented as one.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class SolveStatus(Enum):
    SOLVED = "solved"
    SINGULAR = "singular"
    INCONSISTENT = "inconsistent"
    NUMERICALLY_UNCERTAIN = "numerically_uncertain"


@dataclass(frozen=True)
class LinearSolveResult:
    status: SolveStatus
    solution: tuple | None
    numeric_mode: object  # NumericMode; object to avoid a circular import
    working_precision: int | None
    rank_A: int | None
    rank_augmented: int | None
    residual: tuple | None
    residual_norm: Decimal | None
    backward_error: Decimal | None
    scaling_applied: bool
    growth_factor: Decimal | None
    diagnostics: tuple[str, ...]
    provenance: dict
    digest: str

    def to_dict(self) -> dict:
        def _entry(e):
            return None if e is None else e.to_dict()

        return {
            "status": self.status.value,
            "solution": None if self.solution is None else [_entry(e) for e in self.solution],
            "numeric_mode": self.numeric_mode.value,
            "working_precision": self.working_precision,
            "rank_A": self.rank_A,
            "rank_augmented": self.rank_augmented,
            "residual": None if self.residual is None else [_entry(e) for e in self.residual],
            "residual_norm": None if self.residual_norm is None else str(self.residual_norm),
            "backward_error": None if self.backward_error is None else str(self.backward_error),
            "scaling_applied": self.scaling_applied,
            "growth_factor": None if self.growth_factor is None else str(self.growth_factor),
            "diagnostics": list(self.diagnostics),
            "provenance": dict(self.provenance),
            "digest": self.digest,
        }
