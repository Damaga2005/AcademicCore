# SPDX-License-Identifier: MIT
"""F10 mastery service (application): evidence F9 → probabilistic model.

Consumes only F9 evidence (`AttemptEvidence` items). Never re-corrects
and owns no concept taxonomy: concept/topic/subject come from the D7
hierarchy already carried by the question snapshots (each F9 evidence
item lists `concepts` and a `topic_ref`).

```text
F9 evidence → Observation (Beta deltas) → ConceptState
           → pool(topic) → pool(subject)   (conjugate aggregates)
```

- Idempotency: observation PK `(student, session, item, concept)` +
  `INSERT OR IGNORE` → `apply(E1); apply(E1) == apply(E1)`, including
  concurrent double-apply (loser of the INSERT race is a no-op).
- Rebuild: fold the observation set in fixed order; incremental ==
  rebuild because every update is a commutative sum.
- Aggregation: pooled conjugate members (traceable via `members_json`),
  not a mean of probabilities.
- Atomicity: validate → posterior → persist observation + states →
  commit, per apply (failure rolls back to zero writes).
"""

from __future__ import annotations

import json
from decimal import Decimal

from academic_core.application.correction import AttemptEvidence, ItemEvidence
from academic_core.domain import mastery as M
from academic_core.errors import AcademicManagementError
from academic_core.infrastructure.academic_store import (
    MasteryRepository,
    PersonalRepository,
)


def _err(msg: str, code: str) -> AcademicManagementError:
    return AcademicManagementError(msg, code=code)


def _subject_of_concept(ref: str) -> str:
    parts = (ref or "").split(":")
    if (len(parts) != 4 or parts[0] != "concept" or not parts[1]
            or parts[2] != "c" or not parts[3]):
        raise _err(f"bad concept ref: {ref!r}", "AC-ACD-001")
    return f"subject:{parts[1]}"


class MasteryService:
    """F10 apply/rebuild/aggregate over the F9 evidence stream."""

    def __init__(self, repo: MasteryRepository, academic, personal,
                 config: M.MasteryConfig | None = None):
        self.repo = repo
        self.academic = academic
        self.personal = personal
        self.config = config or M.MasteryConfig()

    # -- evidence intake -----------------------------------------------------
    def apply_evidence(self, evidence: AttemptEvidence) -> dict:
        """Fold one F9 attempt into the student model (idempotent)."""
        if not evidence.items or not all(i.verified
                                        for i in evidence.items):
            raise _err("evidence not verified (snapshot tampered?)",
                       "AC-ACD-003")
        plan: list[M.Observation] = []
        for item in evidence.items:
            if item.reason in ("omitted", "field_set_mismatch",
                               "quantity_set_mismatch"):
                continue  # no scorable evidence → no_update
            concepts = self._resolve_concepts(item)
            if not concepts:
                continue  # unmappable question → no_update (never invented)
            correct = item.is_correct  # None → needs_review → no_update
            n = len(concepts)
            delta = M.split_weight(Decimal(1), n, self.config)
            for ref in concepts:
                plan.append(M.Observation(
                    student_id=evidence.student_id,
                    session_id=evidence.session_id,
                    item_id=item.question_id, concept_ref=ref,
                    topic_ref=item.topic_ref or "",
                    subject_id=_subject_of_concept(ref),
                    correct=bool(correct) if correct is not None else False,
                    alpha_delta=delta if correct else Decimal(0),
                    beta_delta=delta if (correct is False) else Decimal(0),
                    question_digest=item.question_digest,
                    engine=item.engine))
        if not plan:
            return {"applied": 0, "digests": []}
        applied: list[str] = []
        existing = self.repo.observations_of(evidence.student_id)
        with self.repo.unit_of_work() as cx:
            new_obs = []
            for obs in plan:
                digest = M.observation_digest(obs)
                if self.repo.save_observation(obs, digest, 0, cx=cx):
                    new_obs.append({
                        "student_id": obs.student_id,
                        "session_id": obs.session_id,
                        "item_id": obs.item_id, "concept_ref": obs.concept_ref,
                        "topic_ref": obs.topic_ref, "subject_id": obs.subject_id,
                        "alpha_delta": str(obs.alpha_delta),
                        "beta_delta": str(obs.beta_delta),
                        "question_digest": obs.question_digest,
                        "engine": obs.engine})
                    applied.append(digest)
            if new_obs:
                self._store_states(evidence.student_id, existing + new_obs, cx=cx)
        return {"applied": len(applied), "digests": applied}

    # -- state maintenance -----------------------------------------------------
    def _resolve_concepts(self, item: ItemEvidence) -> list[str]:
        refs = list(item.concepts)
        for r in item.provenance.get("knowledge_refs", []):
            if isinstance(r, dict) and r.get("kind") == "concept":
                refs.append(r["ref"])
        refs = sorted({r for r in refs if r.startswith("concept:")})
        for r in refs:
            if not any(c.stable_id == r
                       for c in self.personal.concepts(
                           _subject_of_concept(r))):
                raise _err(f"unknown concept: {r}", "AC-ACD-002")
        return refs

    def _store_states(self, student_id: str, obs_rows, cx) -> None:
        """Recompute concept/topic/subject states from the observation set."""
        by_ref: dict[str, list] = {}
        for r in obs_rows:
            by_ref.setdefault(r["concept_ref"], []).append(r)
        self.repo.delete_states(student_id, cx=cx)
        for ref in sorted(by_ref):
            state = M.fold_observations(
                ref, [self._row_obs(r) for r in by_ref[ref]], self.config)
            self.repo.save_state(
                student_id=student_id, level="concept", ref_id=ref,
                alpha=str(state.alpha), beta=str(state.beta),
                model_version=state.model_version,
                config_version=state.config_version,
                obs_count=state.obs_count, members=[ref],
                updated_at_ms=0, cx=cx)
        self._store_aggregates(student_id, obs_rows, cx=cx)

    def _store_aggregates(self, student_id: str, obs_rows, cx) -> None:
        """Fold observations per topic and per subject (D7 hierarchy)."""
        groups: dict[tuple[str, str], list] = {}
        for r in obs_rows:
            subject = _subject_of_concept(r["concept_ref"])
            topic = r["topic_ref"] or subject
            groups.setdefault((subject, topic), []).append(r)
        by_subject: dict[str, list] = {}
        for (subject, topic), members in sorted(groups.items()):
            by_subject.setdefault(subject, []).extend(members)
            state = M.fold_deltas(
                topic, [self._row_obs(r) for r in members], self.config)
            self.repo.save_state(
                student_id=student_id, level="topic", ref_id=topic,
                alpha=str(state.alpha), beta=str(state.beta),
                model_version=state.model_version,
                config_version=state.config_version,
                obs_count=state.obs_count,
                members=[r["concept_ref"] for r in members],
                updated_at_ms=0, cx=cx)
        for subject, members in sorted(by_subject.items()):
            state = M.fold_deltas(
                subject, [self._row_obs(r) for r in members], self.config)
            self.repo.save_state(
                student_id=student_id, level="subject", ref_id=subject,
                alpha=str(state.alpha), beta=str(state.beta),
                model_version=state.model_version,
                config_version=state.config_version,
                obs_count=state.obs_count,
                members=[r["concept_ref"] for r in members],
                updated_at_ms=0, cx=cx)

    # -- queries ---------------------------------------------------------------
    def get_mastery(self, student_id: str,
                    concept_ref: str) -> M.ConceptState | None:
        row = self.repo.get_state(student_id, "concept", concept_ref)
        return self._row_state(row) if row else None

    def get_topic_mastery(self, student_id: str,
                          topic_ref: str) -> M.AggregateView | None:
        row = self.repo.get_state(student_id, "topic", topic_ref)
        if row is None:
            return None
        members = [self._row_state(self.repo.get_state(student_id, "concept", ref))
                   for ref in json.loads(row["members_json"])]
        members = [m for m in members if m is not None]
        pooled = (M.pool_states(topic_ref, members) if members
                  else self._row_state(row))
        return M.AggregateView(topic_ref, "topic", pooled,
                               tuple(m.ref for m in members))

    def get_subject_mastery(self, student_id: str,
                            subject_id: str) -> M.AggregateView | None:
        row = self.repo.get_state(student_id, "subject", subject_id)
        if row is None:
            return None
        members = [self._row_state(r) for r in
                   self.repo.states_of(student_id, "concept")]
        pooled = (M.pool_states(subject_id, members) if members
                  else self._row_state(row))
        return M.AggregateView(subject_id, "subject", pooled,
                               tuple(m.ref for m in members))

    # -- rebuild -----------------------------------------------------------------
    def rebuild(self, student_id: str) -> dict:
        """Rebuild every state from the persisted observation set."""
        rows = self.repo.observations_of(student_id)
        self._store_states(student_id, rows, None)
        return {"concepts": len(self.repo.states_of(student_id, "concept"))}

    # -- rows ----------------------------------------------------------------------
    def _row_state(self, r) -> M.ConceptState:
        return M.ConceptState("", M._decimal(r["alpha"], "alpha"),
                              M._decimal(r["beta"], "beta"),
                              r["obs_count"], r["model_version"],
                              r["config_version"])

    def _row_obs(self, r) -> M.Observation:
        return M.Observation(
            student_id=r["student_id"], session_id=r["session_id"],
            item_id=r["item_id"], concept_ref=r["concept_ref"],
            topic_ref=r["topic_ref"], subject_id=r["subject_id"],
            correct=Decimal(r["alpha_delta"]) > 0,
            alpha_delta=Decimal(r["alpha_delta"]),
            beta_delta=Decimal(r["beta_delta"]),
            question_digest=r["question_digest"], engine=r["engine"])
