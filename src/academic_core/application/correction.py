# SPDX-License-Identifier: MIT
"""F9 correction service (application): attempts, atomic submit, evidence.

Layers over the certified F9-B/C stack without changing its behavior:

- ``create_attempt`` enforces ``attempts_allowed`` (monotonic attempt
  numbers; cancelled attempts don't consume quota) and delegates session
  creation to ``AssessmentService``.
- ``prepare`` freezes D6 questions per session (snapshots); later bank
  edits never rewrite history. Unknown questions fail deterministically.
- ``submit_with_correction`` runs ``submit -> correct -> persist
  result/evidence -> commit`` inside ONE transaction; any failure rolls
  back to zero writes (the in-memory session is discarded by the caller).
- ``build_evidence`` produces the structured ``AttemptEvidence`` DTO
  consumed by F10 (question, version/digest, raw + normalized answer,
  spec outcome, correction, score, concept/formula refs, verified flag,
  provenance).

Raw answers are stored as canonical JSON of the F9 answer payload
(values intact, key order normalized); nothing is overwritten.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from academic_core.application.assessment import AssessmentService
from academic_core.domain import ingestion as IN
from academic_core.domain import question_bank as QB
from academic_core.domain.assessment import (
    Assessment,
    AssessmentSession,
    SessionStatus,
    StudentResponse,
)
from academic_core.domain.correction import (
    CORRECTION_ENGINE,
    Verdict,
    correct_answer,
)
from academic_core.domain.entities import DomainError
from academic_core.errors import AcademicManagementError


def _err(msg: str, code: str) -> AcademicManagementError:
    return AcademicManagementError(msg, code=code)


@dataclass(frozen=True)
class ItemEvidence:
    question_id: str
    qtype: str
    content_version: int
    question_digest: str
    topic_ref: str = ""
    given_raw: str | None = None
    given_normalized: str | None = None
    is_correct: bool | None = None
    ratio: Decimal | None = None
    score: Decimal = Decimal(0)
    reason: str = "omitted"
    engine: str = CORRECTION_ENGINE
    concepts: tuple = ()
    formulas: tuple = ()
    provenance: dict = field(default_factory=dict, compare=False)
    verified: bool = True


@dataclass(frozen=True)
class AttemptEvidence:
    session_id: str
    assessment_id: str
    student_id: str
    attempt_number: int
    outcome: str
    total_score: Decimal
    max_possible: Decimal
    percentage: Decimal
    passed: bool
    items: tuple = ()


class CorrectionService:
    """F9 attempt lifecycle with deterministic correction."""

    def __init__(self, repo, qbank, assessment_service=None):
        self.repo = repo
        self.qbank = qbank
        self.sessions = assessment_service or AssessmentService(repo=repo)

    # -- attempts ---------------------------------------------------------
    def create_attempt(self, assessment: Assessment, student_id: str,
                       seed: int | None = None) -> AssessmentSession:
        if not isinstance(student_id, str) or not student_id.strip():
            raise _err("student_id is required", "AC-ACD-004")
        prior = self.repo.sessions_of(assessment.stable_id, student_id)
        live = [p for p in prior
                if p["status"] != SessionStatus.CANCELLED.value]
        if len(live) >= assessment.attempts_allowed:
            raise _err(f"attempts exhausted ({assessment.attempts_allowed})",
                       "AC-ACD-003")
        # Cancelled attempts never happened: reuse the smallest free number
        # so attempt_number stays within attempts_allowed by construction.
        used = {p["attempt_number"] for p in live}
        attempt = next(n for n in range(1, assessment.attempts_allowed + 1)
                       if n not in used)
        return self.sessions.create_session(assessment, student_id,
                                            attempt_number=attempt, seed=seed)

    def prepare(self, session_id: str, assessment: Assessment) -> int:
        """Freeze D6 questions for this session (idempotent)."""
        sess = self.repo.get_session(session_id)
        if sess is None:
            raise _err(f"unknown session: {session_id}", "AC-ACD-002")
        if sess.assessment_id != assessment.stable_id:
            raise _err("session does not belong to this assessment",
                       "AC-ACD-004")
        snaps = []
        for item in assessment.items:
            row = self.qbank.get_question(item.question_id)
            if row is None:
                raise _err(f"unknown question (ingest the bank first): "
                           f"{item.question_id}", "AC-ACD-002")
            snaps.append({"item_id": item.item_id,
                          "question_id": item.question_id,
                          "content_version": row["content_version"],
                          "question_digest": row["digest"],
                          "canonical_json": row["canonical_json"],
                          "provenance": json.loads(row["provenance"])})
        self.repo.save_snapshot_batch(session_id, snaps)
        return len(snaps)

    # -- submit ------------------------------------------------------------
    def submit_with_correction(self, session_id: str, assessment: Assessment,
                               answers: dict, now: datetime):
        """Correct every answered item and persist result + evidence atomically."""
        if not isinstance(answers, dict):
            raise _err("answers must be a dict item_id -> payload",
                       "AC-ACD-004")
        sess = self.repo.get_session(session_id)
        if sess is None:
            raise _err(f"unknown session: {session_id}", "AC-ACD-002")
        if sess.assessment_id != assessment.stable_id:
            raise _err("session does not belong to this assessment",
                       "AC-ACD-004")
        if sess.status != SessionStatus.IN_PROGRESS:
            raise _err(f"session is {sess.status.value}, not submittable",
                       "AC-ACD-003")
        if sess.is_expired(now):
            sess.expire(now)
            self.repo.save_session(sess)
            raise _err("session expired at submit", "AC-ACD-003")
        snaps = {s["item_id"]: s
                 for s in self.repo.get_snapshots(session_id)}
        missing = [i.item_id for i in assessment.items if i.item_id not in snaps]
        if missing:
            raise _err(f"session not prepared (call prepare first): {missing}",
                       "AC-ACD-002")
        for item_id in answers:
            if item_id not in snaps:
                raise _err(f"unknown item_id: {item_id}", "AC-ACD-004")

        payloads: dict[str, dict] = {}
        for item_id, resp in sess.responses.items():
            try:
                payloads[item_id] = json.loads(resp.answer)
            except (json.JSONDecodeError, TypeError, ValueError):
                raise _err(f"stored answer is not an F9 payload: {item_id}",
                           "AC-ACD-004") from None
            if not isinstance(payloads[item_id], dict):
                raise _err(f"stored answer is not an F9 payload: {item_id}",
                           "AC-ACD-004")
        for item_id, payload in answers.items():
            if not isinstance(payload, dict):
                raise _err(f"answer payload must be a dict: {item_id}",
                           "AC-ACD-004")
            payloads[item_id] = payload

        verdicts: dict[str, Verdict] = {}
        evaluations: dict[str, tuple] = {}
        evidence_rows = []
        for item in assessment.items:
            if item.item_id not in payloads:
                continue  # omitted -> GradingPolicy scores 0, no evidence row
            question = _question_from_snapshot(snaps[item.item_id])
            try:
                verdict = correct_answer(question, payloads[item.item_id])
            except DomainError as e:
                raise _err(f"answer rejected for {item.item_id}: {e} "
                           f"[{e.code}]", "AC-ACD-004") from None
            verdicts[item.item_id] = verdict
            score = assessment.policy.score_item(
                is_correct=verdict.is_correct, raw_ratio=verdict.ratio,
                weight=item.weight)
            evaluations[item.item_id] = (verdict.is_correct, verdict.ratio)
            if item.item_id not in sess.responses:
                sess.record_response(
                    item_id=item.item_id,
                    answer=QB.dumps_canonical(payloads[item.item_id]), now=now)
            evidence_rows.append({
                "session_id": session_id, "item_id": item.item_id,
                "question_id": item.question_id,
                "qtype": verdict.qtype,
                "is_correct": (None if verdict.is_correct is None
                               else int(verdict.is_correct)),
                "ratio": (None if verdict.ratio is None
                          else str(verdict.ratio)),
                "score": str(score), "reason": verdict.reason,
                "engine": verdict.engine,
                "given_normalized": verdict.normalized,
                "evaluated_at": now.isoformat()})

        sess.submit(now)
        sess.finalize_result(assessment=assessment, policy=assessment.policy,
                             item_evaluations=evaluations, now=now)
        with self.repo.unit_of_work() as cx:
            self.repo.save_session_cx(sess, cx)
            if evidence_rows:
                self.repo.save_evidence_batch(evidence_rows, cx=cx)
        return self.repo.get_session(session_id)

    # -- evidence -----------------------------------------------------------
    def build_evidence(self, session_id: str, assessment=None) -> AttemptEvidence:
        sess = self.repo.get_session(session_id)
        if sess is None or sess.result is None:
            raise _err(f"no evaluated attempt: {session_id}", "AC-ACD-002")
        snaps = {s["item_id"]: s for s in self.repo.get_snapshots(session_id)}
        rows = {r["item_id"]: r for r in self.repo.get_evidence(session_id)}
        topic_of = ({i.item_id: i.topic_id for i in assessment.items}
                    if assessment is not None else {})
        items = []
        for item_id in sess.item_order:
            snap = snaps.get(item_id)
            row = rows.get(item_id)
            resp = sess.responses.get(item_id)
            if snap is None:
                continue
            try:
                raw = json.loads(snap["canonical_json"])
            except (json.JSONDecodeError, TypeError, ValueError):
                raw = {}
            try:
                verified = IN.question_digest(
                    _question_from_snapshot(snap)) == snap["question_digest"]
            except (AcademicManagementError, DomainError):
                verified = False
            topic_ref = topic_of.get(item_id, "")
            if row is None:
                items.append(ItemEvidence(
                    question_id=snap["question_id"],
                    qtype=raw.get("qtype", ""),
                    content_version=snap["content_version"],
                    question_digest=snap["question_digest"],
                    topic_ref=topic_ref,
                    given_raw=None, given_normalized=None,
                    is_correct=None, ratio=None, score=Decimal(0),
                    reason="omitted", engine=CORRECTION_ENGINE,
                    concepts=tuple(raw.get("concepts", [])),
                    formulas=tuple(raw.get("formulas", [])),
                    provenance=dict(json.loads(snap.get("provenance", "{}"))
                                    if isinstance(snap.get("provenance"), str)
                                    else snap.get("provenance", {})),
                    verified=verified))
                continue
            items.append(ItemEvidence(
                question_id=row["question_id"], qtype=row["qtype"],
                content_version=snap["content_version"],
                question_digest=snap["question_digest"],
                topic_ref=topic_ref,
                given_raw=resp.answer if resp else None,
                given_normalized=row["given_normalized"],
                is_correct=(None if row["is_correct"] is None
                            else bool(row["is_correct"])),
                ratio=(None if row["ratio"] is None
                       else Decimal(str(row["ratio"]))),
                score=Decimal(str(row["score"])), reason=row["reason"],
                engine=row["engine"],
                concepts=tuple(raw.get("concepts", [])),
                formulas=tuple(raw.get("formulas", [])),
                provenance=dict(json.loads(snap.get("provenance", "{}"))
                                if isinstance(snap.get("provenance"), str)
                                else snap.get("provenance", {})),
                verified=verified))
        return AttemptEvidence(
            session_id=sess.stable_id, assessment_id=sess.assessment_id,
            student_id=sess.student_id, attempt_number=sess.attempt_number,
            outcome=sess.status.value, total_score=sess.result.total_score,
            max_possible=sess.result.max_possible,
            percentage=sess.result.percentage, passed=sess.result.passed,
            items=tuple(items))


def _question_from_snapshot(snap: dict) -> QB.Question:
    """Rebuild the frozen D6 question (owner slug from its own id)."""
    try:
        raw = json.loads(snap["canonical_json"])
    except (json.JSONDecodeError, TypeError, ValueError):
        raise _err("snapshot canonical_json is corrupt", "AC-ACD-001") from None
    qid = snap.get("question_id", "")
    m = re.match(r"^question:([a-z0-9]+(?:-[a-z0-9]+)*):q:\d{5}$", qid or "")
    if not m:
        raise _err(f"bad snapshot question_id: {qid!r}", "AC-ACD-001")
    return QB.question_from_dict(m.group(1), raw)
