"""Assessment Persistence & Recovery Infrastructure (Phase F9-D).

Explicit row <-> domain mapping for the assessment subsystem:
- Pure stdlib sqlite3 via Database.
- Strict Decimal preservation as TEXT (zero float conversion).
- Full round-trip fidelity for Assessment, AssessmentSession, StudentResponse, AssessmentResult.
- Restart-safe recovery of session timer and state.
- Safe parameterization: zero SQL injection risk.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json

from academic_core.domain.assessment import (
    Assessment,
    AssessmentItem,
    AssessmentResult,
    AssessmentSession,
    GradingPolicy,
    SessionStatus,
    StudentResponse,
)
from academic_core.domain.results import Scale
from academic_core.infrastructure.database import Database
from academic_core.infrastructure.repositories import IntegrityError


def _serialize_items(items: tuple[AssessmentItem, ...]) -> str:
    """Serialize AssessmentItems to JSON preserving exact Decimal weights as TEXT."""
    data = [
        {
            "item_id": it.item_id,
            "question_id": it.question_id,
            "topic_id": it.topic_id,
            "weight": str(it.weight),
            "difficulty": it.difficulty,
            "rubric_ref": it.rubric_ref,
            "options": list(it.options),
        }
        for it in items
    ]
    return json.dumps(data, ensure_ascii=False)


def _deserialize_items(raw_json: str) -> tuple[AssessmentItem, ...]:
    """Deserialize AssessmentItems with exact Decimal weights."""
    try:
        data = json.loads(raw_json)
        if not isinstance(data, list):
            raise IntegrityError("Corrupt assessment items: expected list")
        items = []
        for d in data:
            weight = Decimal(str(d["weight"]))
            items.append(
                AssessmentItem(
                    item_id=str(d["item_id"]),
                    question_id=str(d["question_id"]),
                    topic_id=str(d["topic_id"]),
                    weight=weight,
                    difficulty=str(d.get("difficulty", "medium")),
                    rubric_ref=str(d.get("rubric_ref", "")),
                    options=tuple(d.get("options", ())),
                )
            )
        return tuple(items)
    except (json.JSONDecodeError, KeyError, InvalidOperation) as err:
        raise IntegrityError(f"Failed to deserialize assessment items: {err}") from err


def _serialize_policy(policy: GradingPolicy) -> str:
    """Serialize GradingPolicy with exact Decimal representations."""
    scale_dict = {
        "kind": policy.scale.kind,
        "low": str(policy.scale.low),
        "high": str(policy.scale.high),
        "letters": [list(pair) for pair in policy.scale.letters],
    }
    data = {
        "passing_score": str(policy.passing_score),
        "max_score": str(policy.max_score),
        "negative_marking_factor": str(policy.negative_marking_factor),
        "allow_partial_credit": bool(policy.allow_partial_credit),
        "scale": scale_dict,
    }
    return json.dumps(data, ensure_ascii=False)


def _deserialize_policy(raw_json: str) -> GradingPolicy:
    """Deserialize GradingPolicy with exact Decimal attributes."""
    try:
        d = json.loads(raw_json)
        scale_d = d.get("scale", {})
        letters = tuple(tuple(p) for p in scale_d.get("letters", ()))
        scale = Scale(
            kind=str(scale_d.get("kind", "numeric")),
            low=Decimal(str(scale_d.get("low", "0"))),
            high=Decimal(str(scale_d.get("high", "10"))),
            letters=letters,
        )
        return GradingPolicy(
            passing_score=Decimal(str(d["passing_score"])),
            max_score=Decimal(str(d["max_score"])),
            negative_marking_factor=Decimal(str(d.get("negative_marking_factor", "0"))),
            allow_partial_credit=bool(d.get("allow_partial_credit", True)),
            scale=scale,
        )
    except (json.JSONDecodeError, KeyError, InvalidOperation) as err:
        raise IntegrityError(f"Failed to deserialize grading policy: {err}") from err


class AssessmentRepository:
    """Durable persistence for Assessment, Session, Response, and Result entities."""

    def __init__(self, db: Database):
        self.db = db

    # -- Assessment Specification ---------------------------------------------

    def save_assessment(self, asmt: Assessment) -> None:
        """Persist or update an Assessment specification."""
        items_json = _serialize_items(asmt.items)
        policy_json = _serialize_policy(asmt.policy)
        created_at = datetime.now(timezone.utc).isoformat()

        cx = self.db.connect()
        try:
            cx.execute(
                """
                INSERT OR REPLACE INTO assessments (
                    stable_id, subject_id, title, description, items_json,
                    duration_min, attempts_allowed, policy_json,
                    shuffle_items, master_seed, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asmt.stable_id,
                    asmt.subject_id,
                    asmt.title,
                    asmt.description,
                    items_json,
                    asmt.duration_min,
                    asmt.attempts_allowed,
                    policy_json,
                    1 if asmt.shuffle_items else 0,
                    asmt.master_seed,
                    created_at,
                ),
            )
            cx.commit()
        finally:
            cx.close()

    def get_assessment(self, stable_id: str) -> Assessment | None:
        """Retrieve and reconstruct an Assessment domain aggregate by stable_id."""
        cx = self.db.connect()
        try:
            row = cx.execute(
                "SELECT * FROM assessments WHERE stable_id = ?", (stable_id,)
            ).fetchone()
            if not row:
                return None

            items = _deserialize_items(row["items_json"])
            policy = _deserialize_policy(row["policy_json"])

            return Assessment(
                stable_id=row["stable_id"],
                subject_id=row["subject_id"],
                title=row["title"],
                description=row["description"] or "",
                items=items,
                duration_min=row["duration_min"],
                attempts_allowed=row["attempts_allowed"],
                policy=policy,
                shuffle_items=bool(row["shuffle_items"]),
                master_seed=row["master_seed"],
            )
        finally:
            cx.close()

    def list_assessments(self, subject_id: str = "") -> list[Assessment]:
        """List all assessments, optionally filtered by subject_id."""
        cx = self.db.connect()
        try:
            if subject_id:
                rows = cx.execute(
                    "SELECT * FROM assessments WHERE subject_id = ? ORDER BY stable_id",
                    (subject_id,),
                ).fetchall()
            else:
                rows = cx.execute(
                    "SELECT * FROM assessments ORDER BY stable_id"
                ).fetchall()

            result = []
            for row in rows:
                items = _deserialize_items(row["items_json"])
                policy = _deserialize_policy(row["policy_json"])
                result.append(
                    Assessment(
                        stable_id=row["stable_id"],
                        subject_id=row["subject_id"],
                        title=row["title"],
                        description=row["description"] or "",
                        items=items,
                        duration_min=row["duration_min"],
                        attempts_allowed=row["attempts_allowed"],
                        policy=policy,
                        shuffle_items=bool(row["shuffle_items"]),
                        master_seed=row["master_seed"],
                    )
                )
            return result
        finally:
            cx.close()

    # -- Assessment Sessions & Responses --------------------------------------

    def save_session(self, sess: AssessmentSession) -> None:
        """Atomically persist an AssessmentSession, its responses, and result."""
        item_order_json = json.dumps(list(sess.item_order), ensure_ascii=False)
        updated_at = datetime.now(timezone.utc).isoformat()
        started_at = sess.started_at.isoformat() if sess.started_at else None
        expires_at = sess.expires_at.isoformat() if sess.expires_at else None
        submitted_at = sess.submitted_at.isoformat() if sess.submitted_at else None

        cx = self.db.connect()
        try:
            cx.execute(
                """
                INSERT OR REPLACE INTO assessment_sessions (
                    stable_id, assessment_id, student_id, attempt_number,
                    status, duration_seconds, started_at, expires_at,
                    submitted_at, item_order_json, seed_used, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sess.stable_id,
                    sess.assessment_id,
                    sess.student_id,
                    sess.attempt_number,
                    sess.status.value,
                    sess.duration_seconds,
                    started_at,
                    expires_at,
                    submitted_at,
                    item_order_json,
                    sess.seed_used,
                    updated_at,
                ),
            )

            # Persist responses
            for resp in sess.responses.values():
                cx.execute(
                    """
                    INSERT OR REPLACE INTO assessment_responses (
                        session_id, item_id, answer, submitted_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        sess.stable_id,
                        resp.item_id,
                        resp.answer,
                        resp.submitted_at.isoformat(),
                    ),
                )

            # Persist result if present
            if sess.result is not None:
                r = sess.result
                scores_json = json.dumps(
                    {k: str(v) for k, v in r.item_scores.items()},
                    ensure_ascii=False,
                )
                cx.execute(
                    """
                    INSERT OR REPLACE INTO assessment_results (
                        session_id, assessment_id, student_id, total_score,
                        max_possible, percentage, passed, item_scores_json,
                        evaluated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        r.session_id,
                        r.assessment_id,
                        r.student_id,
                        str(r.total_score),
                        str(r.max_possible),
                        str(r.percentage),
                        1 if r.passed else 0,
                        scores_json,
                        r.evaluated_at.isoformat(),
                    ),
                )

            cx.commit()
        finally:
            cx.close()

    def get_session(self, stable_id: str) -> AssessmentSession | None:
        """Reconstruct an AssessmentSession with full state, responses, and result."""
        cx = self.db.connect()
        try:
            row = cx.execute(
                "SELECT * FROM assessment_sessions WHERE stable_id = ?", (stable_id,)
            ).fetchone()
            if not row:
                return None

            try:
                status = SessionStatus(row["status"])
            except ValueError as err:
                raise IntegrityError(f"Unknown session status '{row['status']}': {err}") from err

            started_at = (
                datetime.fromisoformat(row["started_at"]) if row["started_at"] else None
            )
            expires_at = (
                datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None
            )
            submitted_at = (
                datetime.fromisoformat(row["submitted_at"])
                if row["submitted_at"]
                else None
            )

            try:
                order_list = json.loads(row["item_order_json"])
                item_order = tuple(order_list)
            except Exception as err:
                raise IntegrityError(f"Corrupted item_order_json: {err}") from err

            # Load responses
            resp_rows = cx.execute(
                "SELECT * FROM assessment_responses WHERE session_id = ? ORDER BY submitted_at",
                (stable_id,),
            ).fetchall()
            responses = {}
            for rr in resp_rows:
                responses[rr["item_id"]] = StudentResponse(
                    item_id=rr["item_id"],
                    answer=rr["answer"],
                    submitted_at=datetime.fromisoformat(rr["submitted_at"]),
                )

            # Load result if present
            result_row = cx.execute(
                "SELECT * FROM assessment_results WHERE session_id = ?", (stable_id,)
            ).fetchone()
            result = None
            if result_row:
                try:
                    raw_scores = json.loads(result_row["item_scores_json"])
                    item_scores = {k: Decimal(str(v)) for k, v in raw_scores.items()}
                    result = AssessmentResult(
                        session_id=result_row["session_id"],
                        assessment_id=result_row["assessment_id"],
                        student_id=result_row["student_id"],
                        total_score=Decimal(result_row["total_score"]),
                        max_possible=Decimal(result_row["max_possible"]),
                        percentage=Decimal(result_row["percentage"]),
                        passed=bool(result_row["passed"]),
                        item_scores=item_scores,
                        evaluated_at=datetime.fromisoformat(result_row["evaluated_at"]),
                    )
                except Exception as err:
                    raise IntegrityError(f"Corrupted assessment result data: {err}") from err

            session = AssessmentSession(
                stable_id=row["stable_id"],
                assessment_id=row["assessment_id"],
                student_id=row["student_id"],
                attempt_number=row["attempt_number"],
                status=status,
                duration_seconds=row["duration_seconds"],
                started_at=started_at,
                expires_at=expires_at,
                submitted_at=submitted_at,
                responses=responses,
                item_order=item_order,
                seed_used=row["seed_used"],
                result=result,
            )
            return session
        finally:
            cx.close()

    def save_response(self, session_id: str, response: StudentResponse) -> None:
        """Persist a single StudentResponse."""
        cx = self.db.connect()
        try:
            cx.execute(
                """
                INSERT OR REPLACE INTO assessment_responses (
                    session_id, item_id, answer, submitted_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    session_id,
                    response.item_id,
                    response.answer,
                    response.submitted_at.isoformat(),
                ),
            )
            cx.commit()
        finally:
            cx.close()

    def get_result(self, session_id: str) -> AssessmentResult | None:
        """Fetch AssessmentResult directly by session_id."""
        cx = self.db.connect()
        try:
            row = cx.execute(
                "SELECT * FROM assessment_results WHERE session_id = ?", (session_id,)
            ).fetchone()
            if not row:
                return None
            try:
                raw_scores = json.loads(row["item_scores_json"])
                item_scores = {k: Decimal(str(v)) for k, v in raw_scores.items()}
                return AssessmentResult(
                    session_id=row["session_id"],
                    assessment_id=row["assessment_id"],
                    student_id=row["student_id"],
                    total_score=Decimal(row["total_score"]),
                    max_possible=Decimal(row["max_possible"]),
                    percentage=Decimal(row["percentage"]),
                    passed=bool(row["passed"]),
                    item_scores=item_scores,
                    evaluated_at=datetime.fromisoformat(row["evaluated_at"]),
                )
            except Exception as err:
                raise IntegrityError(f"Corrupted assessment result: {err}") from err
        finally:
            cx.close()
