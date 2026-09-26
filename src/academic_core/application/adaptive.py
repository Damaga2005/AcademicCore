# SPDX-License-Identifier: MIT
"""F11 adaptive service (application): build deterministic practice plans.

Loads certified artifacts (F10 states, D6 questions via the D7 store,
F10 observation history) and runs the pure engine in `domain/adaptive.py`:

```text
eligible → filter → score → rank → constraints → route → plan → persist
```

LLM=OFF: no AI import, no LLM authority anywhere. A future
`AdaptiveEnhancer` (not implemented) would pass LLM output through
validation → deterministic constraints → accept/reject.
"""

from __future__ import annotations

import json
from decimal import Decimal

from academic_core.domain import adaptive as AD
from academic_core.errors import AcademicManagementError


def _err(msg: str, code: str) -> AcademicManagementError:
    return AcademicManagementError(msg, code=code)


class AdaptiveService:
    """F11 adaptive engine over F10 mastery + D6/D7 knowledge."""

    def __init__(self, qbank, mastery_repo, academic_repo,
                 config: AD.AdaptiveConfig | None = None):
        self.qbank = qbank
        self.mastery = mastery_repo
        self.academic = academic_repo
        self.config = config or AD.AdaptiveConfig()

    # -- plan ----------------------------------------------------------------
    def build_plan(self, student_id: str,
                   context: AD.AdaptiveContext) -> AD.AdaptivePlan:
        """Deterministic plan; NO_ELIGIBLE_EXERCISES if nothing qualifies."""
        plan = self._build_plan(student_id, context)
        self._persist(plan, context)
        return plan

    def _build_plan(self, student_id: str,
                    context: AD.AdaptiveContext) -> AD.AdaptivePlan:
        questions = self._load_questions(context)
        observations = self.mastery.observations_of(student_id)
        done_qids = {o["item_id"] for o in observations}
        erred = {o["concept_ref"] for o in observations
                 if Decimal(o["alpha_delta"]) == 0}
        practiced_subjects = {o["subject_id"] for o in observations}
        mastery_rows = self.mastery.states_of(student_id, "concept")
        states = {r["ref_id"]: self._state_p(r) for r in mastery_rows}
        prereq_ok = self._prerequisites_ok(practiced_subjects,
                                            {context.subject_id})

        candidates = []
        for qid, raw in questions.items():
            if (context.allowed_types
                    and raw["qtype"] not in context.allowed_types):
                continue
            d = raw["difficulty"]
            if d == "unspecified" and not self.config.allow_unspecified_difficulty:
                continue
            if d != "unspecified":
                if context.difficulty_min and d < context.difficulty_min:
                    continue
                if context.difficulty_max and d > context.difficulty_max:
                    continue
            concepts = raw["concepts"]
            if context.concept_ref and context.concept_ref not in concepts:
                continue
            if raw["subject_id"] != context.subject_id:
                continue
            if not prereq_ok.get(raw["subject_id"], True):
                continue  # prerequisite subject not satisfied: never recommend
            refs = [c for c in concepts if c in states]
            ps = [states[c] for c in refs if states[c] is not None]
            p = (sum(ps, Decimal(0)) / len(ps)) if ps else None
            candidates.append(AD.Candidate(
                question_id=qid, qtype=raw["qtype"], difficulty=d,
                concepts=tuple(concepts), topic_ref=raw["topic_ref"],
                subject_id=raw["subject_id"],
                content_version=raw["content_version"],
                question_digest=raw["question_digest"], mastery_p=p,
                mastery_refs=tuple(refs), done=qid in done_qids,
                recent_error=bool(set(concepts) & erred),
                prerequisite_ok=prereq_ok.get(raw["subject_id"], True)))
        if self.config.exclude_done:
            candidates = [c for c in candidates if not c.done]
        bank_digest = AD.bank_digest_of(sorted(questions))
        snapshot = tuple(sorted(
            (k, r["alpha"], r["beta"], str(states[k] or ""))
            for k, r in ((row["ref_id"], row) for row in mastery_rows)))
        if not candidates:
            unmet = (context.subject_id
                     and not prereq_ok.get(context.subject_id, True))
            return AD.AdaptivePlan(
                student_id=student_id, selections=(),
                rationale_codes=("PREREQUISITE_UNMET",) if unmet else (
                    "NO_ELIGIBLE_EXERCISES",),
                config_version=self.config.config_version,
                model_version=self.config.engine_version,
                bank_digest=bank_digest, mastery_snapshot=snapshot)
        ranked = AD.rank_candidates(candidates, self.config)
        picks = AD.build_route(ranked, limit=context.exercise_count,
                               max_per_concept=self.config.max_per_concept)
        codes = {r for sc in picks for r in sc.rationale}
        return AD.AdaptivePlan(
            student_id=student_id, selections=picks,
            rationale_codes=tuple(sorted(codes)),
            config_version=self.config.config_version,
            model_version=self.config.engine_version,
            bank_digest=bank_digest, mastery_snapshot=snapshot)

    def _persist(self, plan: AD.AdaptivePlan,
                 context: AD.AdaptiveContext) -> str:
        plan_id = AD.plan_digest(plan)
        self.mastery.save_plan(
            plan_id, student_id=plan.student_id,
            subject_id=context.subject_id,
            config_version=plan.config_version,
            model_version=plan.model_version, bank_digest=plan.bank_digest,
            selections=[{"question_id": s.candidate.question_id,
                         "score": str(s.adaptive_score),
                         "rationale": list(s.rationale)}
                        for s in plan.selections],
            rationale=list(plan.rationale_codes),
            mastery_snapshot=[list(m) for m in plan.mastery_snapshot],
            context={"subject_id": context.subject_id,
                     "topic_ref": context.topic_ref,
                     "concept_ref": context.concept_ref,
                     "exercise_count": context.exercise_count,
                     "allowed_types": list(context.allowed_types)},
            plan_digest=plan_id, created_at_ms=0)
        return plan_id

    # -- internals --------------------------------------------------------------
    def _load_questions(self, context: AD.AdaptiveContext) -> dict:
        """Questions scoped by the context's subject (D7 store)."""
        rows = (self.qbank.questions_of_subject(context.subject_id)
                if context.subject_id else self.qbank.all_questions())
        out = {}
        for r in rows:
            try:
                canon = json.loads(r["canonical_json"])
            except (json.JSONDecodeError, TypeError, ValueError):
                raise _err(f"corrupt canonical_json: {r['question_id']}",
                           "AC-ACD-004") from None
            concepts = list(canon.get("concepts", []))
            out[r["question_id"]] = {
                "qtype": canon.get("qtype", ""),
                "difficulty": canon.get("difficulty", "unspecified"),
                "concepts": concepts,
                # Topic is not part of the D6/F9 snapshot contract; the
                # context topic labels candidates of its subject.
                "topic_ref": (context.topic_ref
                              if context.subject_id else ""),
                "subject_id": _subject_of(concepts),
                "content_version": r["content_version"],
                "question_digest": r["digest"],
            }
        return out

    def _state_p(self, r):
        try:
            a = Decimal(r["alpha"])
            b = Decimal(r["beta"])
            if not (a.is_finite() and b.is_finite()):
                raise ValueError("non-finite")
        except Exception:
            raise _err(f"corrupt mastery state: {r['ref_id']}",
                       "AC-ACD-004") from None
        if a + b <= 0:
            raise _err(f"mastery state without mass: {r['ref_id']}",
                       "AC-ACD-004")
        return a / (a + b)

    def _prerequisites_ok(self, practiced_subjects,
                           subjects_to_check) -> dict:
        """Subject-level prerequisites (the only kind D7 defines).

        A subject is OK when every prerequisite subject has F10 evidence.
        """
        out = {}
        for subject in sorted(set(practiced_subjects) | subjects_to_check):
            prereqs = self.academic.prerequisites_of(subject)
            out[subject] = all(p in practiced_subjects for p in prereqs)
        return out


def _subject_of(concepts) -> str:
    for c in concepts:
        parts = c.split(":")
        if len(parts) == 4 and parts[0] == "concept":
            return f"subject:{parts[1]}"
    return ""
