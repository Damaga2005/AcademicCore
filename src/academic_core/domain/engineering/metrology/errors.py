"""F8-O metrology error model (NEW, thin).

Defines the deterministic terminal states for the metrology layer and the
typed exception that carries them. No physics, no I/O, no randomness.

Reuse classification: NEW (no existing metrology status enum; engine
statuses pass through verbatim in ``engine_status`` fields elsewhere).
"""

from __future__ import annotations

from enum import Enum


class MetrologyStatus(str, Enum):
    """Terminal states of an F8-O metrology operation."""

    COMPLETED = "completed"
    COMPLETED_WITH_FAILURES = "completed_with_failures"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"
    SINGULAR = "singular"
    DIVERGED = "diverged"
    MAX_ITERATIONS = "max_iterations"
    NUMERIC_ERROR = "numeric_error"
    INCONSISTENT = "inconsistent"
    SOLVER_FAILURE = "solver_failure"


class MetrologyError(ValueError):
    """Typed failure with a deterministic :class:`MetrologyStatus`.

    ``INVALID`` = bad ingress; ``UNSUPPORTED`` = out-of-scope physics;
    ``SINGULAR`` = non-PSD correlation / singular Jacobian surfaced here;
    ``DIVERGED`` = wrapped iterator non-convergence; ``NUMERIC_ERROR`` =
    negative variance / NaN / Inf; ``INCONSISTENT`` = digest / chain /
    dimension mismatch. Invalid input, unsolvable problem and
    non-converged algorithm are never conflated.
    """

    def __init__(self, status: MetrologyStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
