"""Assessment Session Domain Aggregate and Lifecycle State Machine (Phase F9-B).

Pure domain layer:
- Invariants raise DomainError.
- Session lifecycle: NOT_STARTED -> IN_PROGRESS -> SUBMITTED | EXPIRED | CANCELLED.
- Time limit validation and expiration enforcement.
- Deterministic response tracking and result aggregation.
- Zero float policy, pure Decimal scoring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum

from academic_core.domain.assessment.models import Assessment
from academic_core.domain.assessment.policy import GradingPolicy
from academic_core.domain.entities import DomainError
from academic_core.domain.identity import validate


class SessionStatus(str, Enum):
    """Lifecycle states of an assessment examination session."""
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class StudentResponse:
    """Individual response submitted by a student for an item in a session."""
    item_id: str
    answer: str
    submitted_at: datetime

    def __post_init__(self) -> None:
        if not self.item_id.strip():
            raise DomainError("StudentResponse.item_id cannot be empty")


@dataclass(frozen=True)
class AssessmentResult:
    """Final immutable evaluation verdict and score summary for a session."""
    session_id: str
    assessment_id: str
    student_id: str
    total_score: Decimal
    max_possible: Decimal
    percentage: Decimal
    passed: bool
    item_scores: dict[str, Decimal]
    evaluated_at: datetime


@dataclass
class AssessmentSession:
    """Domain aggregate encapsulating an active or completed assessment session."""
    stable_id: str  # session:<subject>:sess:NNNNN
    assessment_id: str  # assessment:<subject>:as:NNNNN
    student_id: str
    attempt_number: int = 1
    status: SessionStatus = SessionStatus.NOT_STARTED
    duration_seconds: int = 0
    started_at: datetime | None = None
    expires_at: datetime | None = None
    submitted_at: datetime | None = None
    responses: dict[str, StudentResponse] = field(default_factory=dict)
    item_order: tuple[str, ...] = ()
    seed_used: int | None = None
    result: AssessmentResult | None = None

    def __post_init__(self) -> None:
        if validate(self.stable_id) != "session":
            raise DomainError(f"bad session stable_id: {self.stable_id}")
        if validate(self.assessment_id) != "assessment":
            raise DomainError(f"bad assessment_id: {self.assessment_id}")
        if not self.student_id.strip():
            raise DomainError("AssessmentSession.student_id cannot be empty")
        if self.attempt_number < 1:
            raise DomainError("AssessmentSession.attempt_number must be >= 1")
        if self.duration_seconds < 0:
            raise DomainError("AssessmentSession.duration_seconds cannot be negative")

    def is_expired(self, now: datetime) -> bool:
        """Check if time limit has passed."""
        if self.expires_at is not None and now > self.expires_at:
            return True
        return False

    def start(
        self,
        *,
        now: datetime,
        item_order: tuple[str, ...],
        seed_used: int | None = None,
    ) -> None:
        """Transition session from NOT_STARTED to IN_PROGRESS."""
        if self.status != SessionStatus.NOT_STARTED:
            raise DomainError(f"Cannot start session in status {self.status.value}")
        if len(item_order) == 0:
            raise DomainError("Cannot start session with empty item_order")

        self.status = SessionStatus.IN_PROGRESS
        self.started_at = now
        self.item_order = item_order
        self.seed_used = seed_used

        if self.duration_seconds > 0:
            self.expires_at = now + timedelta(seconds=self.duration_seconds)

    def record_response(self, *, item_id: str, answer: str, now: datetime) -> None:
        """Record an answer for a specific item in the session."""
        if self.status != SessionStatus.IN_PROGRESS:
            raise DomainError(f"Cannot record response in status {self.status.value}")

        if self.is_expired(now):
            self.expire(now)
            raise DomainError("Session has expired; cannot record response")

        if item_id not in self.item_order:
            raise DomainError(f"Item '{item_id}' is not part of this session")

        self.responses[item_id] = StudentResponse(
            item_id=item_id,
            answer=answer,
            submitted_at=now,
        )

    def submit(self, now: datetime) -> None:
        """Formally submit the session for grading."""
        if self.status != SessionStatus.IN_PROGRESS:
            raise DomainError(f"Cannot submit session in status {self.status.value}")

        if self.is_expired(now):
            self.expire(now)
            raise DomainError("Session has expired; cannot submit")

        self.status = SessionStatus.SUBMITTED
        self.submitted_at = now

    def expire(self, now: datetime) -> None:
        """Force session into EXPIRED state due to timeout."""
        if self.status != SessionStatus.IN_PROGRESS:
            raise DomainError(f"Cannot expire session in status {self.status.value}")

        self.status = SessionStatus.EXPIRED
        self.submitted_at = now

    def cancel(self, reason: str = "") -> None:
        """Cancel the session before completion."""
        if self.status in (SessionStatus.SUBMITTED, SessionStatus.EXPIRED):
            raise DomainError(f"Cannot cancel finalized session in status {self.status.value}")

        self.status = SessionStatus.CANCELLED

    def finalize_result(
        self,
        *,
        assessment: Assessment,
        policy: GradingPolicy,
        item_evaluations: dict[str, tuple[bool | None, Decimal | None]],
        now: datetime,
    ) -> AssessmentResult:
        """Compute final result from item evaluations and store in self.result.
        
        Parameters
        ----------
        assessment:
            The parent Assessment aggregate.
        policy:
            Grading policy to apply.
        item_evaluations:
            Map of item_id -> (is_correct, raw_partial_ratio).
        now:
            Timestamp of evaluation.
        """
        if self.status not in (SessionStatus.SUBMITTED, SessionStatus.EXPIRED):
            raise DomainError(
                f"Cannot finalize result for session in status {self.status.value}"
            )

        item_scores: dict[str, Decimal] = {}
        for item in assessment.items:
            eval_data = item_evaluations.get(item.item_id, (None, None))
            is_correct, raw_ratio = eval_data
            score = policy.score_item(
                is_correct=is_correct,
                raw_ratio=raw_ratio,
                weight=item.weight,
            )
            item_scores[item.item_id] = score

        total_score, percentage, passed = policy.aggregate_scores(
            item_scores=item_scores,
            total_weight=assessment.total_weight,
        )

        res = AssessmentResult(
            session_id=self.stable_id,
            assessment_id=self.assessment_id,
            student_id=self.student_id,
            total_score=total_score,
            max_possible=policy.max_score,
            percentage=percentage,
            passed=passed,
            item_scores=item_scores,
            evaluated_at=now,
        )
        self.result = res
        return res
