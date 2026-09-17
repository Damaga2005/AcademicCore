"""Assessment Application Service & Orchestration (Phase F9-C).

Integrates certified F9-B domain models with application layer:
- Session lifecycle orchestration (create, start, get_next_item, respond, submit, expire, cancel).
- Pure Decimal grading policy execution.
- Deterministic seed-based item delivery.
- Persistent sequential ID allocation (no process-local collisions).
- Formula-bearing question adaptation with 100% provenance retention.
- Zero float policy, zero dynamic code execution.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
import threading

from academic_core.application.services import ApplicationError
from academic_core.domain.academic import Formula
from academic_core.domain.assessment import (
    Assessment,
    AssessmentItem,
    AssessmentResult,
    AssessmentSession,
    GradingPolicy,
    SessionStatus,
    StudentResponse,
)
from academic_core.domain.entities import DomainError
from academic_core.domain.identity import IdAllocator, make, validate
from academic_core.infrastructure.repositories import IntegrityError


def item_from_formula(
    formula: Formula,
    item_id: str,
    *,
    weight: Decimal = Decimal("1.0"),
    difficulty: str = "medium",
    rubric_ref: str = "",
) -> AssessmentItem:
    """Thin deterministic adapter mapping a certified Formula into an AssessmentItem.
    
    Preserves:
    - Formula identity (`formula.stable_id`)
    - Topic mapping (`formula.topic_id`)
    - Provenance & LaTeX reference in rubric_ref / options
    - Exact Decimal weight
    """
    if not isinstance(formula, Formula):
        raise ApplicationError("item_from_formula expects a Formula instance")
    if not formula.stable_id.strip():
        raise ApplicationError("Formula must have a valid stable_id")

    effective_rubric = rubric_ref or f"formula_prov:{formula.provenance.get('source_path', '')}#{formula.provenance.get('section', '')}"
    
    return AssessmentItem(
        item_id=item_id,
        question_id=formula.stable_id,
        topic_id=formula.topic_id or "topic:generic:t01",
        weight=weight,
        difficulty=difficulty,
        rubric_ref=effective_rubric,
        options=(formula.latex, formula.source_latex),
    )


class AssessmentService:
    """Application service orchestrating assessment examination sessions."""

    def __init__(
        self,
        repo=None,
        *,
        clock: Callable[[], datetime] | None = None,
        on_completed_hook: Callable[[AssessmentSession, AssessmentResult], None] | None = None,
    ) -> None:
        self.repo = repo
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._allocator = IdAllocator()
        self._sessions: dict[str, AssessmentSession] = {}
        self._lock = threading.Lock()
        self._on_completed = on_completed_hook

    def create_assessment(
        self,
        subject_id: str,
        title: str,
        items: tuple[AssessmentItem, ...] | list[AssessmentItem],
        *,
        duration_min: int = 60,
        attempts_allowed: int = 1,
        policy: GradingPolicy | None = None,
        description: str = "",
        shuffle_items: bool = False,
        master_seed: int | None = None,
        stable_id: str | None = None,
    ) -> Assessment:
        """Create and register a new Assessment specification."""
        subject_slug = subject_id.split(":", 1)[1] if ":" in subject_id else "gen"

        if stable_id is None:
            if self.repo is not None:
                stable_id = self.repo.allocate_assessment_id(subject_slug)
            else:
                with self._lock:
                    stable_id = self._allocator.allocate("assessment", subject_slug)

        asmt = Assessment(
            stable_id=stable_id,
            subject_id=subject_id,
            title=title,
            description=description,
            items=tuple(items),
            duration_min=duration_min,
            attempts_allowed=attempts_allowed,
            policy=policy or GradingPolicy(),
            shuffle_items=shuffle_items,
            master_seed=master_seed,
        )
        if self.repo is not None:
            self.repo.save_assessment(asmt)
        return asmt

    def create_session(
        self,
        assessment: Assessment,
        student_id: str,
        *,
        attempt_number: int = 1,
        seed: int | None = None,
    ) -> AssessmentSession:
        """Create and register a new assessment examination session."""
        if not isinstance(assessment, Assessment):
            raise ApplicationError(f"Invalid assessment: expected Assessment instance, got {type(assessment)}")
        if not student_id or not student_id.strip():
            raise ApplicationError("student_id cannot be empty")
        if attempt_number < 1:
            raise ApplicationError(f"attempt_number must be >= 1, got {attempt_number}")
        if attempt_number > assessment.attempts_allowed:
            raise ApplicationError(
                f"attempt_number {attempt_number} exceeds allowed limit {assessment.attempts_allowed}"
            )

        subject_slug = assessment.subject_id.split(":", 1)[1] if ":" in assessment.subject_id else "gen"

        if self.repo is not None:
            sess_id = self.repo.allocate_session_id(subject_slug)
        else:
            with self._lock:
                sess_id = self._allocator.allocate("session", subject_slug)

        duration_sec = assessment.duration_min * 60
        item_order = assessment.generate_item_order(seed)

        try:
            session = AssessmentSession(
                stable_id=sess_id,
                assessment_id=assessment.stable_id,
                student_id=student_id.strip(),
                attempt_number=attempt_number,
                status=SessionStatus.NOT_STARTED,
                duration_seconds=duration_sec,
                item_order=item_order,
                seed_used=seed,
            )
        except DomainError as err:
            raise ApplicationError(f"Domain invariant violation: {err}") from err

        with self._lock:
            self._sessions[sess_id] = session

        if self.repo is not None:
            self.repo.save_session(session)

        return session

    def get_session(self, session_id: str, *, now: datetime | None = None) -> AssessmentSession:
        """Retrieve a session by its stable_id, checking repository if configured."""
        if self.repo is not None:
            sess = self.repo.get_session(session_id)
            if sess is not None:
                if now is not None and sess.status == SessionStatus.IN_PROGRESS and sess.is_expired(now):
                    sess.expire(now)
                    self.repo.save_session(sess)
                with self._lock:
                    self._sessions[session_id] = sess
                return sess

        with self._lock:
            sess = self._sessions.get(session_id)
        if sess is None:
            raise ApplicationError(f"Session not found: {session_id}")
        if now is not None and sess.status == SessionStatus.IN_PROGRESS and sess.is_expired(now):
            sess.expire(now)
            if self.repo is not None:
                self.repo.save_session(sess)
        return sess

    def start_session(self, session_id: str, now: datetime) -> AssessmentSession:
        """Transition session to IN_PROGRESS and start countdown timer."""
        sess = self.get_session(session_id)
        if sess.status != SessionStatus.NOT_STARTED:
            raise ApplicationError(f"Cannot start session in status '{sess.status.value}'")

        try:
            sess.start(now=now, item_order=sess.item_order, seed_used=sess.seed_used)
            if self.repo is not None:
                self.repo.save_session(sess)
        except DomainError as err:
            raise ApplicationError(f"Cannot start session: {err}") from err

        return sess

    def get_next_item(
        self,
        session_id: str,
        assessment: Assessment,
        now: datetime | None = None,
    ) -> AssessmentItem | None:
        """Expose the next unanswered assessment item in deterministic session order."""
        sess = self.get_session(session_id)
        if sess.assessment_id != assessment.stable_id:
            raise ApplicationError(
                f"Assessment mismatch: session belongs to '{sess.assessment_id}', not '{assessment.stable_id}'"
            )

        if sess.status != SessionStatus.IN_PROGRESS:
            raise ApplicationError(f"Cannot retrieve items for session in status '{sess.status.value}'")

        if now is not None and sess.is_expired(now):
            sess.expire(now)
            if self.repo is not None:
                self.repo.save_session(sess)
            raise ApplicationError("Session has expired")

        for item_id in sess.item_order:
            if item_id not in sess.responses:
                return assessment.get_item(item_id)

        return None

    def submit_response(
        self,
        session_id: str,
        item_id: str,
        answer: str,
        now: datetime,
        *,
        allow_overwrite: bool = False,
    ) -> StudentResponse:
        """Record a student answer for a specific item in the active session."""
        sess = self.get_session(session_id)

        if sess.status == SessionStatus.SUBMITTED:
            raise ApplicationError("Cannot answer a submitted session")
        if sess.status == SessionStatus.EXPIRED:
            raise ApplicationError("Cannot answer an expired session")
        if sess.status == SessionStatus.CANCELLED:
            raise ApplicationError("Cannot answer a cancelled session")
        if sess.status != SessionStatus.IN_PROGRESS:
            raise ApplicationError(f"Cannot record response in status '{sess.status.value}'")

        if sess.is_expired(now):
            sess.expire(now)
            if self.repo is not None:
                self.repo.save_session(sess)
            raise ApplicationError("Session has expired; cannot record response")

        if item_id not in sess.item_order:
            raise ApplicationError(f"Unknown item '{item_id}' for session '{session_id}'")

        if item_id in sess.responses and not allow_overwrite:
            raise ApplicationError(f"Duplicate response for item '{item_id}'")

        try:
            sess.record_response(item_id=item_id, answer=answer, now=now)
            if self.repo is not None:
                self.repo.save_session(sess)
        except (DomainError, IntegrityError) as err:
            raise ApplicationError(str(err)) from err

        return sess.responses[item_id]

    def submit_assessment(
        self,
        session_id: str,
        assessment: Assessment,
        item_evaluations: dict[str, tuple[bool | None, Decimal | None]],
        now: datetime,
    ) -> AssessmentResult:
        """Submit the active session for formal grading and produce AssessmentResult."""
        sess = self.get_session(session_id)

        if sess.assessment_id != assessment.stable_id:
            raise ApplicationError(
                f"Assessment mismatch: session belongs to '{sess.assessment_id}', not '{assessment.stable_id}'"
            )

        if sess.status == SessionStatus.SUBMITTED:
            raise ApplicationError("Duplicate submission: session is already submitted")
        if sess.status == SessionStatus.EXPIRED:
            raise ApplicationError("Cannot submit an expired session")
        if sess.status == SessionStatus.CANCELLED:
            raise ApplicationError("Cannot submit a cancelled session")
        if sess.status != SessionStatus.IN_PROGRESS:
            raise ApplicationError(f"Cannot submit session in status '{sess.status.value}'")

        if sess.is_expired(now):
            sess.expire(now)
            if self.repo is not None:
                self.repo.save_session(sess)
            raise ApplicationError("Cannot submit: session has expired")

        try:
            sess.submit(now)
            result = sess.finalize_result(
                assessment=assessment,
                policy=assessment.policy,
                item_evaluations=item_evaluations,
                now=now,
            )
            if self.repo is not None:
                self.repo.save_session(sess)
        except (DomainError, IntegrityError) as err:
            raise ApplicationError(f"Grading failure: {err}") from err

        if self._on_completed is not None:
            try:
                self._on_completed(sess, result)
            except Exception:
                # Do not mask result on hook failure
                pass

        return result

    def expire_session(
        self,
        session_id: str,
        now: datetime,
        *,
        assessment: Assessment | None = None,
        item_evaluations: dict[str, tuple[bool | None, Decimal | None]] | None = None,
    ) -> AssessmentSession:
        """Force session into EXPIRED status due to timeout, optionally grading it."""
        sess = self.get_session(session_id)
        if sess.status != SessionStatus.IN_PROGRESS:
            raise ApplicationError(f"Cannot expire session in status '{sess.status.value}'")

        try:
            sess.expire(now)
            if assessment is not None and item_evaluations is not None:
                sess.finalize_result(
                    assessment=assessment,
                    policy=assessment.policy,
                    item_evaluations=item_evaluations,
                    now=now,
                )
                if self._on_completed is not None and sess.result is not None:
                    self._on_completed(sess, sess.result)
            if self.repo is not None:
                self.repo.save_session(sess)
        except (DomainError, IntegrityError) as err:
            raise ApplicationError(f"Expiration error: {err}") from err

        return sess

    def cancel_session(self, session_id: str, reason: str = "") -> AssessmentSession:
        """Cancel an assessment session before finalization."""
        sess = self.get_session(session_id)
        if sess.status in (SessionStatus.SUBMITTED, SessionStatus.EXPIRED):
            raise ApplicationError(f"Cannot cancel session in status '{sess.status.value}'")

        try:
            sess.cancel(reason)
            if self.repo is not None:
                self.repo.save_session(sess)
        except (DomainError, IntegrityError) as err:
            raise ApplicationError(f"Cancellation error: {err}") from err

        return sess

    def get_result(self, session_id: str) -> AssessmentResult:
        """Retrieve the finalized AssessmentResult for a submitted/expired session."""
        sess = self.get_session(session_id)
        if sess.result is not None:
            return sess.result
        if self.repo is not None:
            res = self.repo.get_result(session_id)
            if res is not None:
                sess.result = res
                return res
        raise ApplicationError(f"Assessment result not yet available for session '{session_id}'")

    def save_assessment(self, assessment: Assessment) -> None:
        """Persist an Assessment specification if a repository is configured."""
        if self.repo is not None:
            self.repo.save_assessment(assessment)

    def get_assessment(self, stable_id: str) -> Assessment | None:
        """Retrieve an Assessment specification by stable_id if a repository is configured."""
        if self.repo is not None:
            return self.repo.get_assessment(stable_id)
        return None
