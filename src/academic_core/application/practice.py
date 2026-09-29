# SPDX-License-Identifier: MIT
"""Practice loop for the UI (UX 2026 prompt 8): F9 -> F10 -> F11 -> F12.

A thin application service over the certified engines; it adds NO grading,
mastery, planning or tutoring logic:

    question bank (D6/D7) -> attempt (F9 correct_answer) -> evidence
    -> mastery (F10) -> adaptive plan (F11) -> tutor hint (F12)

Authority stays deterministic. The tutor's LLM only *proposes*; the
response the UI receives is the F12 ``VerifiedResponse`` after validation,
policy and verification against the F9 solver. With no LLM available the
tutor answers with the static, verifiable guidance built from the attempt.

The UI never receives a correct answer: ``QuestionView`` carries only what a
student may see (statement, options, unit).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from academic_core.application.correction import _question_from_snapshot
from academic_core.domain import adaptive as AD
from academic_core.domain.assessment import AssessmentItem, GradingPolicy

STUDENT_ID = "student:local"  # single-user, offline: one local learner


@dataclass(frozen=True)
class QuestionView:
    question_id: str
    bank_id: str
    statement: str
    qtype: str
    difficulty: str
    concepts: tuple = ()
    options: tuple = ()  # multiple choice only
    unit: str = ""
    subject_id: str = ""
    fields: tuple = ()  # structured: (name, kind); circuit: (name, unit). Names only, never values.


@dataclass(frozen=True)
class Attempt:
    session_id: str
    assessment_id: str
    subject_id: str
    question_ids: tuple
    item_ids: dict = field(compare=False, default_factory=dict)  # question_id -> item_id


@dataclass(frozen=True)
class ItemResult:
    question_id: str
    qtype: str
    is_correct: bool | None  # None = not machine-decidable / omitted
    ratio: str | None
    score: str
    reason: str
    verified: bool


@dataclass(frozen=True)
class AttemptResult:
    session_id: str
    total_score: str
    max_possible: str
    percentage: str
    passed: bool
    items: tuple
    mastery_updated: bool


@dataclass(frozen=True)
class ConceptView:
    ref: str
    name: str
    probability: Decimal
    observations: int


@dataclass(frozen=True)
class PlanItem:
    question_id: str
    statement: str
    difficulty: str
    concepts: tuple
    score: Decimal
    rationale: tuple


@dataclass(frozen=True)
class PlanView:
    items: tuple
    rationale_codes: tuple
    mastery_snapshot: tuple  # (concept_ref, probability)


@dataclass(frozen=True)
class HintView:
    status: str  # verified | unverified | rejected  (F12)
    response_type: str
    message: str
    steps: tuple
    llm_available: bool
    provider_error: str
    solver_version: str


def _slug(subject_id: str) -> str:
    return subject_id.split(":", 1)[1] if ":" in subject_id else subject_id


def _subject_of_concepts(concepts) -> str:
    for ref in concepts:
        parts = str(ref).split(":")
        if len(parts) >= 3 and parts[0] == "concept":
            return f"subject:{parts[1]}"
    return ""


class PracticeService:
    """Bank -> attempt -> evidence -> mastery -> plan -> tutor, as plain values."""

    def __init__(self, *, qbank, ingest, assessments, correction, mastery, adaptive,
                 tutor, personal, student_id: str = STUDENT_ID, clock=None):
        self.qbank, self.ingest, self.assessments = qbank, ingest, assessments
        self.correction, self.mastery, self.adaptive = correction, mastery, adaptive
        self.tutor, self.personal, self.student_id = tutor, personal, student_id
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._attempts: dict[str, tuple] = {}  # session_id -> (Assessment, Attempt)
        self._evidence: dict[str, dict] = {}  # session_id -> {question_id: ItemEvidence}

    # -- banks and questions ---------------------------------------------------------
    def banks(self) -> list[dict]:
        ids = sorted({r["bank_id"] for r in self.qbank.all_questions()})
        out = []
        for bank_id in ids:
            b = self.qbank.get_bank(bank_id) or {}
            out.append({"bank_id": bank_id, "title": b.get("title", bank_id),
                        "content_version": b.get("content_version", 0),
                        "question_count": b.get("question_count", 0)})
        return out

    def questions(self, bank_id: str | None = None) -> list[QuestionView]:
        views = []
        for row in self.qbank.all_questions():
            if bank_id and row["bank_id"] != bank_id:
                continue
            raw = json.loads(row["canonical_json"])
            spec = raw.get("answer_spec", {}) or {}
            concepts = tuple(raw.get("concepts", ()))
            options = tuple(str(o) for o in spec.get("options", ())) if row["qtype"] == "multiple_choice" else ()
            if row["qtype"] == "structured":
                fields = tuple(sorted((str(k), str(v)) for k, v in (spec.get("schema") or {}).items()))
            elif row["qtype"] == "circuit":
                fields = tuple((str(e["name"]), str(e.get("unit", ""))) for e in spec.get("quantities", ()))
            else:
                fields = ()
            views.append(QuestionView(
                question_id=row["question_id"], bank_id=row["bank_id"],
                statement=raw.get("statement", ""), qtype=row["qtype"],
                difficulty=raw.get("difficulty", "unspecified"), concepts=concepts,
                options=options, unit=str(raw.get("unit", "") or spec.get("unit", "")),
                subject_id=_subject_of_concepts(concepts), fields=fields))
        return views

    def import_bank(self, source) -> dict:
        """Ingest a D6 bank from a path, JSON text or dict (D7 validates everything)."""
        data = source
        if isinstance(source, (str, Path)) and not str(source).lstrip().startswith("{"):
            data = Path(source).read_text(encoding="utf-8")
        report = self.ingest.ingest(data)
        return {"outcome": report.outcome, "bank_id": report.bank_id,
                "content_version": report.content_version, "counts": dict(report.counts)}

    # -- attempt -------------------------------------------------------------------------
    def start_attempt(self, question_ids, subject_id: str = "", title: str = "Practice") -> Attempt:
        qids = tuple(question_ids)
        rows = {q: self.qbank.get_question(q) for q in qids}
        missing = [q for q, r in rows.items() if r is None]
        if not qids or missing:
            raise ValueError(f"unknown or empty question set: {missing or 'none selected'}")
        subject = subject_id or next(
            (s for s in (_subject_of_concepts(json.loads(r["canonical_json"]).get("concepts", ()))
                         for r in rows.values()) if s), "")
        if not subject:
            raise ValueError("choose a subject: these questions have no concept to infer it from")
        slug = _slug(subject)
        items = tuple(AssessmentItem(f"i{n}", q, f"topic:{slug}:t01", Decimal("1.0"))
                      for n, q in enumerate(qids, start=1))
        asmt = self.assessments.create_assessment(
            subject, title, items, duration_min=60, attempts_allowed=1, policy=GradingPolicy())
        sess = self.correction.create_attempt(asmt, self.student_id)
        self.correction.prepare(sess.stable_id, asmt)
        self.assessments.start_session(sess.stable_id, self._clock())
        attempt = Attempt(sess.stable_id, asmt.stable_id, subject, qids,
                          {q: f"i{n}" for n, q in enumerate(qids, start=1)})
        self._attempts[attempt.session_id] = (asmt, attempt)
        return attempt

    def submit(self, attempt: Attempt, answers: dict) -> AttemptResult:
        """``answers``: question_id -> F9 payload. Unanswered questions score 0."""
        asmt, known = self._attempts[attempt.session_id]
        by_item = {known.item_ids[q]: payload for q, payload in answers.items()}
        self.correction.submit_with_correction(attempt.session_id, asmt, by_item, self._clock())
        evidence = self.correction.build_evidence(attempt.session_id, asmt)
        # A "needs_review" item carries no verdict, so it must not move mastery. F10 documents
        # that ("None -> needs_review -> no_update") but MasteryService.apply_evidence builds a
        # zero-mass Observation for it and raises. The core is not touched here; the
        # equivalent no-update is applied by not handing it that item.
        scorable = tuple(i for i in evidence.items if not (i.is_correct is None and i.reason == "needs_review"))
        applied = 0
        if scorable:
            applied = self.mastery.apply_evidence(replace(evidence, items=scorable)).get("applied", 0)
        self._attempts.pop(attempt.session_id, None)
        self._evidence[attempt.session_id] = {i.question_id: i for i in evidence.items}
        return AttemptResult(
            session_id=attempt.session_id, total_score=str(evidence.total_score),
            max_possible=str(evidence.max_possible), percentage=str(evidence.percentage),
            passed=evidence.passed, mastery_updated=applied > 0,
            items=tuple(ItemResult(i.question_id, i.qtype, i.is_correct,
                                   None if i.ratio is None else str(i.ratio), str(i.score),
                                   i.reason, i.verified) for i in evidence.items))

    # -- F10 mastery ----------------------------------------------------------------------
    def concepts(self, subject_id: str | None = None) -> list[ConceptView]:
        names = {c.stable_id: c.name for c in self.personal.concepts(subject_id)}
        prefix = f"concept:{_slug(subject_id)}:" if subject_id else ""
        out = []
        for row in self.mastery.repo.states_of(self.student_id, "concept"):
            ref = row["ref_id"]
            if prefix and not ref.startswith(prefix):
                continue
            state = self.mastery.get_mastery(self.student_id, ref)
            if state is None:
                continue
            out.append(ConceptView(ref, names.get(ref, ref), state.probability(), state.obs_count))
        return sorted(out, key=lambda c: (c.probability, c.ref))

    def subject_mastery(self, subject_id: str):
        """(probability Decimal, observations) pooled by F10, or None without evidence."""
        view = self.mastery.get_subject_mastery(self.student_id, subject_id)
        return None if view is None else (view.state.probability(), view.state.obs_count)

    def rebuild_mastery(self) -> int:
        """Recompute every state from persisted observations (deterministic)."""
        return self.mastery.rebuild(self.student_id)["concepts"]

    # -- F11 plan ---------------------------------------------------------------------------
    def plan(self, subject_id: str, count: int = 5) -> PlanView:
        ctx = AD.AdaptiveContext(subject_id=subject_id, exercise_count=count)
        plan = self.adaptive.build_plan(self.student_id, ctx)
        by_id = {q.question_id: q for q in self.questions()}
        items = tuple(PlanItem(
            s.candidate.question_id,
            by_id[s.candidate.question_id].statement if s.candidate.question_id in by_id else "",
            s.candidate.difficulty, tuple(s.candidate.concepts), s.adaptive_score,
            tuple(s.rationale)) for s in plan.selections)
        snapshot = tuple((ref, Decimal(str(p))) for ref, _a, _b, p in plan.mastery_snapshot)
        return PlanView(items, tuple(plan.rationale_codes), snapshot)

    # -- F12 tutor --------------------------------------------------------------------------
    def hint(self, session_id: str, question_id: str) -> HintView:
        """Verified tutor response for a question of an already corrected attempt."""
        item = (self._evidence.get(session_id) or {}).get(question_id)
        if item is None:
            raise ValueError("ask for a hint after the attempt has been corrected")
        row = self.qbank.get_question(question_id)
        question = _question_from_snapshot(
            {"canonical_json": row["canonical_json"], "question_id": question_id,
             "content_version": row["content_version"]})
        response = self.tutor.get_response(
            student_id=self.student_id, question=question, question_digest=row["digest"],
            attempt_evidence={"reason": item.reason, "is_correct": item.is_correct,
                              "given": item.given_normalized},
            now_ms=int(self._clock().timestamp() * 1000))
        meta = self.tutor.provider.metadata()
        return HintView(response.status, response.response_type, response.message,
                        tuple(response.steps), meta.available, response.provider_error or "",
                        response.solver_version)

    def llm_available(self) -> bool:
        return bool(self.tutor.provider.metadata().available)
