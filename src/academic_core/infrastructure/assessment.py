"""Assessment Persistence & Recovery Infrastructure (Phase F9-D).

Explicit row <-> domain mapping for the assessment subsystem:
- Pure stdlib sqlite3 via Database.
- Strict Decimal preservation as TEXT (zero float conversion).
- Full round-trip fidelity for Assessment, AssessmentSession, StudentResponse, AssessmentResult.
- Restart-safe recovery of session timer, state, and identity counters.
- Explicit SQL without unsafe REPLACE cascades.
- Immutable response and result enforcement.
- Safe parameterization: zero SQL injection risk.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import sqlite3

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
from academic_core.domain.results import Scale
from academic_core.infrastructure.database import Database
from academic_core.infrastructure.repositories import IntegrityError


def _serialize_items(items: tuple[AssessmentItem, ...]) -> str:
    """Serialize AssessmentItems to canonical JSON preserving exact Decimal weights as TEXT."""
    data = [
        {
            "difficulty": it.difficulty,
            "item_id": it.item_id,
            "options": list(it.options),
            "question_id": it.question_id,
            "rubric_ref": it.rubric_ref,
            "topic_id": it.topic_id,
            "weight": str(it.weight),
        }
        for it in items
    ]
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _deserialize_items(raw_json: str) -> tuple[AssessmentItem, ...]:
    """Deserialize AssessmentItems with exact Decimal weights."""
    try:
        data = json.loads(raw_json)
        if not isinstance(data, list):
            raise IntegrityError("Corrupt assessment items: expected list")
        items = []
        for d in data:
            if not isinstance(d, dict):
                raise IntegrityError("Corrupt assessment item entry: expected dict")
            weight = Decimal(str(d["weight"]))
            items.append(
                AssessmentItem(
                    item_id=str(d["item_id"]),
                    question_id=str(d["question_id"]),
                    topic_id=str(d["topic_id"]),
                    weight=weight,
                    difficulty=str(d.get("difficulty", "medium")),
                    rubric_ref=str(d.get("rubric_ref", "")),
                    options=tuple(str(x) for x in d.get("options", ())),
                )
            )
        return tuple(items)
    except (json.JSONDecodeError, KeyError, InvalidOperation, TypeError, ValueError, DomainError) as err:
        raise IntegrityError(f"Failed to deserialize assessment items: {err}") from err


def _serialize_policy(policy: GradingPolicy) -> str:
    """Serialize GradingPolicy to canonical JSON with exact Decimal representations."""
    scale_dict = {
        "high": str(policy.scale.high),
        "kind": policy.scale.kind,
        "letters": [list(pair) for pair in policy.scale.letters],
        "low": str(policy.scale.low),
    }
    data = {
        "allow_partial_credit": bool(policy.allow_partial_credit),
        "max_score": str(policy.max_score),
        "negative_marking_factor": str(policy.negative_marking_factor),
        "passing_score": str(policy.passing_score),
        "scale": scale_dict,
    }
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _deserialize_policy(raw_json: str) -> GradingPolicy:
    """Deserialize GradingPolicy with exact Decimal attributes."""
    try:
        d = json.loads(raw_json)
        if not isinstance(d, dict):
            raise IntegrityError("Corrupt grading policy: expected dict")
        scale_d = d.get("scale", {})
        if not isinstance(scale_d, dict):
            raise IntegrityError("Corrupt scale in grading policy: expected dict")
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
    except (json.JSONDecodeError, KeyError, InvalidOperation, TypeError, ValueError, DomainError) as err:
        raise IntegrityError(f"Failed to deserialize grading policy: {err}") from err


class AssessmentRepository:
    """Durable persistence for Assessment, Session, Response, and Result entities."""

    def __init__(self, db: Database):
        self.db = db

    @contextmanager
    def _tx(self, immediate: bool = True):
        """Transaction context manager ensuring immediate write lock acquisition and rollback on failure."""
        cx = self.db.connect()
        cx.isolation_level = None  # Manual explicit transaction control
        try:
            if immediate:
                cx.execute("BEGIN IMMEDIATE")
            else:
                cx.execute("BEGIN")
            yield cx
            cx.execute("COMMIT")
        except sqlite3.IntegrityError as err:
            try:
                cx.execute("ROLLBACK")
            except Exception:
                pass
            raise IntegrityError(f"Database integrity violation: {err}") from err
        except Exception:
            try:
                cx.execute("ROLLBACK")
            except Exception:
                pass
            raise
        finally:
            cx.close()

    # -- Persistent Identity Allocation ---------------------------------------

    def allocate_id(self, kind: str, subject: str = "") -> str:
        """Atomically and persistently allocate a unique stable ID for kind and subject."""
        with self._tx(immediate=True) as cx:
            row = cx.execute(
                """
                INSERT INTO id_counters (kind, last_n) VALUES (?, 1)
                ON CONFLICT(kind) DO UPDATE SET last_n = last_n + 1
                RETURNING last_n
                """,
                (kind,),
            ).fetchone()
            n = row[0]
        alloc = IdAllocator({kind: n - 1})
        return alloc.allocate(kind, subject)

    def allocate_session_id(self, subject_slug: str) -> str:
        """Allocate a persistent, sequentially unique session stable ID."""
        return self.allocate_id("session", subject_slug)

    def allocate_assessment_id(self, subject_slug: str) -> str:
        """Allocate a persistent, sequentially unique assessment stable ID."""
        return self.allocate_id("assessment", subject_slug)

    # -- Assessment Specification ---------------------------------------------

    def save_assessment(self, asmt: Assessment) -> None:
        """Persist or update an Assessment specification without unsafe REPLACE."""
        items_json = _serialize_items(asmt.items)
        policy_json = _serialize_policy(asmt.policy)
        created_at = datetime.now(timezone.utc).isoformat()

        with self._tx(immediate=True) as cx:
            existing = cx.execute(
                "SELECT 1 FROM assessments WHERE stable_id = ?", (asmt.stable_id,)
            ).fetchone()
            if existing is None:
                cx.execute(
                    """
                    INSERT INTO assessments (
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
            else:
                cx.execute(
                    """
                    UPDATE assessments SET
                        subject_id = ?, title = ?, description = ?, items_json = ?,
                        duration_min = ?, attempts_allowed = ?, policy_json = ?,
                        shuffle_items = ?, master_seed = ?
                    WHERE stable_id = ?
                    """,
                    (
                        asmt.subject_id,
                        asmt.title,
                        asmt.description,
                        items_json,
                        asmt.duration_min,
                        asmt.attempts_allowed,
                        policy_json,
                        1 if asmt.shuffle_items else 0,
                        asmt.master_seed,
                        asmt.stable_id,
                    ),
                )

    def get_assessment(self, stable_id: str) -> Assessment | None:
        """Retrieve and reconstruct an Assessment domain aggregate by stable_id."""
        cx = self.db.connect()
        try:
            row = cx.execute(
                "SELECT * FROM assessments WHERE stable_id = ?", (stable_id,)
            ).fetchone()
            if not row:
                return None

            try:
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
            except (DomainError, ValueError, TypeError, KeyError) as err:
                raise IntegrityError(f"Corrupted assessment record '{stable_id}': {err}") from err
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

    def _save_response_tx(
        self, cx, session_id: str, resp: StudentResponse
    ) -> None:
        """Internal transactional response persistence with strict immutability."""
        sess_row = cx.execute(
            "SELECT status FROM assessment_sessions WHERE stable_id = ?",
            (session_id,),
        ).fetchone()
        if sess_row is None:
            raise IntegrityError(f"Cannot save response: session '{session_id}' does not exist")

        existing_resp = cx.execute(
            "SELECT answer, submitted_at FROM assessment_responses WHERE session_id = ? AND item_id = ?",
            (session_id, resp.item_id),
        ).fetchone()

        if existing_resp is None:
            if sess_row["status"] in (
                SessionStatus.SUBMITTED.value,
                SessionStatus.EXPIRED.value,
                SessionStatus.CANCELLED.value,
            ):
                raise IntegrityError(
                    f"Cannot record response: session '{session_id}' is in terminal status '{sess_row['status']}'"
                )
            cx.execute(
                """
                INSERT INTO assessment_responses (
                    session_id, item_id, answer, submitted_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    session_id,
                    resp.item_id,
                    resp.answer,
                    resp.submitted_at.isoformat(),
                ),
            )
        else:
            if existing_resp["answer"] != resp.answer:
                raise IntegrityError(
                    f"Immutable response conflict: item '{resp.item_id}' in session '{session_id}' "
                    f"already answered with '{existing_resp['answer']}', cannot overwrite with '{resp.answer}'"
                )
            # Identical answer: idempotent success, original submitted_at preserved

    def _save_result_tx(self, cx, r: AssessmentResult) -> None:
        """Internal transactional result persistence with immutability guarantee."""
        scores_json = json.dumps(
            {k: str(v) for k, v in sorted(r.item_scores.items())},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        existing = cx.execute(
            "SELECT * FROM assessment_results WHERE session_id = ?", (r.session_id,)
        ).fetchone()

        if existing is None:
            sess_row = cx.execute(
                "SELECT 1 FROM assessment_sessions WHERE stable_id = ?",
                (r.session_id,),
            ).fetchone()
            if sess_row is None:
                raise IntegrityError(f"Cannot save result: session '{r.session_id}' does not exist")

            cx.execute(
                """
                INSERT INTO assessment_results (
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
        else:
            if (
                existing["assessment_id"] != r.assessment_id
                or existing["student_id"] != r.student_id
                or Decimal(existing["total_score"]) != r.total_score
                or Decimal(existing["max_possible"]) != r.max_possible
                or Decimal(existing["percentage"]) != r.percentage
                or bool(existing["passed"]) != bool(r.passed)
                or existing["item_scores_json"] != scores_json
                or existing["evaluated_at"] != r.evaluated_at.isoformat()
            ):
                raise IntegrityError(
                    f"AssessmentResult for session '{r.session_id}' is immutable and cannot be mutated with different values"
                )

    def save_session(self, sess: AssessmentSession) -> None:
        """Atomically persist an AssessmentSession, its responses, and result without unsafe REPLACE."""
        with self._tx(immediate=True) as cx:
            self._save_session_tx(cx, sess)

    def save_session_cx(self, sess: AssessmentSession, cx) -> None:
        """Persist inside a caller-owned transaction (F9 atomic submit)."""
        self._save_session_tx(cx, sess)

    @contextmanager
    def unit_of_work(self):
        """One transaction shared by several writes (F9 submit + evidence)."""
        with self._tx(immediate=True) as cx:
            yield cx

    def _save_session_tx(self, cx, sess: AssessmentSession) -> None:
        """Session write body over an explicit connection (same semantics)."""
        item_order_json = json.dumps(list(sess.item_order), ensure_ascii=False, separators=(",", ":"))
        updated_at = datetime.now(timezone.utc).isoformat()
        started_at = sess.started_at.isoformat() if sess.started_at else None
        expires_at = sess.expires_at.isoformat() if sess.expires_at else None
        submitted_at = sess.submitted_at.isoformat() if sess.submitted_at else None

        existing = cx.execute(
            "SELECT status FROM assessment_sessions WHERE stable_id = ?",
            (sess.stable_id,),
        ).fetchone()

        if existing is None:
            cx.execute(
                """
                INSERT INTO assessment_sessions (
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
            # Persist responses safely
            for resp in sess.responses.values():
                self._save_response_tx(cx, sess.stable_id, resp)

            # Persist result safely if present
            if sess.result is not None:
                self._save_result_tx(cx, sess.result)
        else:
            old_status = existing["status"]
            terminal_states = (
                SessionStatus.SUBMITTED.value,
                SessionStatus.EXPIRED.value,
                SessionStatus.CANCELLED.value,
            )
            if old_status in terminal_states and sess.status.value != old_status:
                raise IntegrityError(
                    f"Cannot transition terminal session '{sess.stable_id}' from {old_status} to {sess.status.value}"
                )

            # If old_status was terminal, check whether caller is attempting to add late responses
            if old_status in terminal_states:
                for resp in sess.responses.values():
                    self._save_response_tx(cx, sess.stable_id, resp)
            else:
                # Session transitioning to terminal or in-progress: save responses first
                for resp in sess.responses.values():
                    self._save_response_tx(cx, sess.stable_id, resp)

            cx.execute(
                """
                UPDATE assessment_sessions SET
                    status = ?, duration_seconds = ?, started_at = ?, expires_at = ?,
                    submitted_at = ?, item_order_json = ?, seed_used = ?, updated_at = ?
                WHERE stable_id = ?
                """,
                (
                    sess.status.value,
                    sess.duration_seconds,
                    started_at,
                    expires_at,
                    submitted_at,
                    item_order_json,
                    sess.seed_used,
                    updated_at,
                    sess.stable_id,
                ),
            )

            # Persist result safely if present
            if sess.result is not None:
                self._save_result_tx(cx, sess.result)

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

                order_list = json.loads(row["item_order_json"])
                if not isinstance(order_list, list):
                    raise IntegrityError("Corrupted item_order_json: expected list")
                item_order = tuple(str(x) for x in order_list)

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
                    raw_scores = json.loads(result_row["item_scores_json"])
                    if not isinstance(raw_scores, dict):
                        raise IntegrityError("Corrupted item_scores_json: expected dict")
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
            except (DomainError, ValueError, TypeError, KeyError, json.JSONDecodeError, InvalidOperation) as err:
                raise IntegrityError(f"Corrupted session data for '{stable_id}': {err}") from err
        finally:
            cx.close()

    def save_response(self, session_id: str, response: StudentResponse) -> None:
        """Persist a single StudentResponse enforcing immutability."""
        with self._tx(immediate=True) as cx:
            self._save_response_tx(cx, session_id, response)

    def save_result(self, result: AssessmentResult) -> None:
        """Persist a single AssessmentResult enforcing immutability."""
        with self._tx(immediate=True) as cx:
            self._save_result_tx(cx, result)

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
                if not isinstance(raw_scores, dict):
                    raise IntegrityError("Corrupted item_scores_json: expected dict")
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
            except (DomainError, ValueError, TypeError, KeyError, json.JSONDecodeError, InvalidOperation) as err:
                raise IntegrityError(f"Corrupted assessment result for '{session_id}': {err}") from err
        finally:
            cx.close()

    # -- F9 snapshots & evidence (017, append-only) ---------------------------

    def sessions_of(self, assessment_id: str, student_id: str) -> list[dict]:
        """Lightweight attempt listing for attempts_allowed enforcement."""
        cx = self.db.connect()
        try:
            rows = cx.execute(
                "SELECT stable_id, attempt_number, status FROM assessment_sessions"
                " WHERE assessment_id=? AND student_id=?"
                " ORDER BY attempt_number, stable_id",
                (assessment_id, student_id),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            cx.close()

    def save_snapshot_batch(self, session_id: str, snaps: list[dict],
                            cx=None) -> None:
        """Freeze examined questions (INSERT OR IGNORE: snapshots never move)."""
        if cx is not None:
            for s in snaps:
                cx.execute(
                    "INSERT OR IGNORE INTO assessment_item_snapshots(session_id,"
                    " item_id, question_id, content_version, question_digest,"
                    " canonical_json, provenance) VALUES (?,?,?,?,?,?,?)",
                    (session_id, s["item_id"], s["question_id"],
                     s["content_version"], s["question_digest"],
                     s["canonical_json"], json.dumps(s.get("provenance", {}),
                                                     ensure_ascii=False,
                                                     sort_keys=True)))
            return
        with self._tx(immediate=True) as c:
            self.save_snapshot_batch(session_id, snaps, cx=c)

    def get_snapshots(self, session_id: str) -> list[dict]:
        cx = self.db.connect()
        try:
            rows = cx.execute(
                "SELECT * FROM assessment_item_snapshots WHERE session_id=?"
                " ORDER BY item_id", (session_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            cx.close()

    def save_evidence_batch(self, rows: list[dict], cx=None) -> None:
        """Store one CorrectionResult per submitted item (immutable)."""
        if cx is not None:
            for r in rows:
                cx.execute(
                    "INSERT INTO assessment_evidence(session_id, item_id,"
                    " question_id, qtype, is_correct, ratio, score, reason,"
                    " engine, given_normalized, evaluated_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (r["session_id"], r["item_id"], r["question_id"],
                     r["qtype"], r["is_correct"], r["ratio"], r["score"],
                     r["reason"], r["engine"], r["given_normalized"],
                     r["evaluated_at"]))
            return
        with self._tx(immediate=True) as c:
            self.save_evidence_batch(rows, cx=c)

    def get_evidence(self, session_id: str) -> list[dict]:
        cx = self.db.connect()
        try:
            rows = cx.execute(
                "SELECT * FROM assessment_evidence WHERE session_id=?"
                " ORDER BY item_id", (session_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            cx.close()
