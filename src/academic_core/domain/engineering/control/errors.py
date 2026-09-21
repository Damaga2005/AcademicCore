"""F8-P1 control error model (NEW, thin).

Terminal states for the SISO LTI layer. No physics, no I/O, no randomness.
"""

from __future__ import annotations

from enum import Enum


class ControlStatus(str, Enum):
    """Terminal states of an F8-P1 control operation."""

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


class ControlError(ValueError):
    """Typed failure carrying a deterministic ControlStatus."""

    def __init__(self, status: ControlStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
