# SPDX-License-Identifier: MIT
"""D7 bank ingestion service (application): plan -> apply -> verify.

Wiring over the existing stores; no new persistence framework:

- ``parse_bank`` (D6) validates the input; invalid input is rejected
  with ``AC-ACD-004`` (the D6 cause code is preserved in the message).
- ``ingestion.plan_bank`` (pure domain) resolves references against
  read-only snapshots; diagnostics map to ``AC-ACD-002`` (unknown) /
  ``AC-ACD-003`` (conflict/stale/ambiguous) / ``AC-ACD-004`` (invalid).
- Apply runs inside ONE transaction (``QBankRepository.unit_of_work``,
  shared ``cx`` across ``Personal`` + ``QBank`` writes); any failure
  rolls back to zero writes.
- Verify re-reads after commit; a mismatch is an internal bug
  (``AC-INT-001``), never silently accepted.
- ``dry_run`` is exactly ``plan``: zero writes by construction.

D7 never implements F9 (attempts/scoring/correction), mastery, adaptive
scheduling or AI tutoring.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from academic_core.domain import ingestion as IN
from academic_core.domain import question_bank as QB
from academic_core.domain import planning as PL
from academic_core.domain import academic as AC
from academic_core.domain.entities import DomainError
from academic_core.errors import (
    AcademicManagementError,
    IntegrationError,
)


def _err(msg: str, code: str) -> AcademicManagementError:
    return AcademicManagementError(msg, code=code)


def _plan_error(e: DomainError) -> AcademicManagementError:
    msg = str(e)
    if msg.startswith("unresolved") or "unknown subject" in msg:
        return _err(f"{msg} [{e.code}]", "AC-ACD-002")
    if ("conflict" in msg or "ambiguous" in msg or "modified" in msg
            or "stale" in msg or "diverged" in msg):
        return _err(f"{msg} [{e.code}]", "AC-ACD-003")
    return _err(f"{msg} [{e.code}]", "AC-ACD-004")


@dataclass(frozen=True)
class IngestionReport:
    outcome: str  # create | unchanged | update
    bank_id: str
    content_version: int
    bank_digest: str
    plan_digest: str
    counts: dict = field(compare=False)
    resolved: tuple = ()  # (question_id, kind, ref, action) sorted
    verified: bool = True


class BankIngestionService:
    """D7 ingestion over Academic/Personal/QBank repositories."""

    def __init__(self, academic, personal, qbank):
        self.academic = academic
        self.personal = personal
        self.qbank = qbank

    # -- plan / dry-run -------------------------------------------------
    def plan(self, data: object, *, catalog_concepts=None,
             catalog_formulas=None) -> IN.IngestionPlan:
        try:
            bank = QB.parse_bank(data)
        except DomainError as e:
            raise _err(f"bank rejected by D6: {e} [{e.code}]",
                       "AC-ACD-004") from None
        concepts = {c.stable_id: {"subject_id": c.subject_id, "name": c.name}
                    for c in self.personal.concepts()}
        formulas = {k: {"latex": v}
                    for k, v in self.qbank.all_formula_heads().items()}
        subjects = {s.stable_id for s in self._subjects()}
        stored = self.qbank.get_bank(bank.bank_id)
        existing = None
        if stored is not None:
            existing = {
                "content_version": stored["content_version"],
                "digest": stored["digest"],
                "questions": self.qbank.question_digests(bank.bank_id),
            }
        try:
            return IN.plan_bank(
                bank, existing_bank=existing, existing_concepts=concepts,
                existing_formulas=formulas, known_subjects=subjects,
                catalog_concepts=catalog_concepts,
                catalog_formulas=catalog_formulas)
        except DomainError as e:
            raise _plan_error(e) from None

    def dry_run(self, data: object, *, catalog_concepts=None,
                catalog_formulas=None) -> IN.IngestionPlan:
        """Validate + resolve + show ops without mutating persistence."""
        return self.plan(data, catalog_concepts=catalog_concepts,
                         catalog_formulas=catalog_formulas)

    # -- ingest ----------------------------------------------------------
    def ingest(self, data: object, *, catalog_concepts=None,
               catalog_formulas=None, now_ms: int | None = None,
               ) -> IngestionReport:
        if now_ms is None:
            now_ms = int(time.time() * 1000)
        if not isinstance(now_ms, int) or isinstance(now_ms, bool) \
                or now_ms < 0:
            raise _err(f"bad now_ms: {now_ms!r}", "AC-ACD-004")
        plan = self.plan(data, catalog_concepts=catalog_concepts,
                         catalog_formulas=catalog_formulas)
        if plan.outcome == "unchanged":
            self._verify_unchanged(plan)
            return self._report(plan, {"questions_kept": len(
                self.qbank.question_digests(plan.bank_id))})

        concept_map = {c.ref: c for c in plan.concepts}
        with self.qbank.unit_of_work() as cx:
            for c in plan.concepts:
                if c.action == "create":
                    self.personal.add_concept(PL.StudyConcept(
                        c.ref, c.subject_id, c.name, "no_visto",
                        None, None), cx=cx)
            for f in plan.formulas:
                if f.action == "create":
                    self.qbank.save_formula(AC.Formula(
                        stable_id=f.ref, latex=f.latex, source_latex=f.latex,
                        topic_id=f.topic_id, concept_ids=list(f.concept_ids),
                        variables=[dict(v) if isinstance(v, dict) else v
                                   for v in f.variables],
                        units=list(f.units), provenance=dict(f.provenance),
                        version=1), cx=cx)
            if plan.outcome == "create":
                self.qbank.save_bank_new(
                    bank_id=plan.bank_id, title=plan.title,
                    content_version=plan.content_version,
                    digest=plan.bank_digest,
                    question_count=len(plan.questions),
                    provenance=dict(self._bank_provenance(plan)),
                    now_ms=now_ms, cx=cx)
            else:
                self.qbank.save_bank_update(
                    bank_id=plan.bank_id, title=plan.title,
                    content_version=plan.content_version,
                    digest=plan.bank_digest,
                    question_count=len(plan.questions),
                    provenance=dict(self._bank_provenance(plan)),
                    now_ms=now_ms, cx=cx)
            for q in plan.questions:
                if q.action != "keep":
                    self.qbank.save_question(
                        question_id=q.question_id, bank_id=plan.bank_id,
                        content_version=plan.content_version, digest=q.qdigest,
                        qtype=q.qtype, canonical_json=q.canonical_json,
                        provenance=dict(q.provenance), cx=cx)
            removed = []
            if plan.deletes:
                removed = self.qbank.delete_bank_questions_not_in(
                    plan.bank_id, [q.question_id for q in plan.questions],
                    cx=cx)
            if plan.counters_bump:
                stored_counters = self.academic.load_counters()
                merged = {k: max(v, stored_counters.get(k, 0))
                          for k, v in plan.counters_bump.items()
                          if v > stored_counters.get(k, 0)}
                if merged:
                    from academic_core.infrastructure.academic_store import (
                        TargetWriter,
                    )
                    TargetWriter(cx).counters(merged)
        self._verify_applied(plan, set(removed) if plan.deletes else set())
        counts = {
            "questions_created": sum(1 for q in plan.questions
                                     if q.action == "create"),
            "questions_kept": sum(1 for q in plan.questions
                                  if q.action == "keep"),
            "questions_updated": sum(1 for q in plan.questions
                                     if q.action == "update"),
            "questions_deleted": len(plan.deletes),
            "concepts_reused": sum(1 for c in plan.concepts
                                   if c.action == "reuse"),
            "concepts_created": sum(1 for c in plan.concepts
                                    if c.action == "create"),
            "formulas_reused": sum(1 for f in plan.formulas
                                   if f.action == "reuse"),
            "formulas_created": sum(1 for f in plan.formulas
                                    if f.action == "create"),
        }
        return self._report(plan, counts)

    # -- internals --------------------------------------------------------
    def _subjects(self):
        return self.academic.all_subjects()

    def _bank_provenance(self, plan: IN.IngestionPlan) -> dict:
        return {"imported_by": IN.IMPORTER, "bank": plan.bank_id,
                "bank_digest": plan.bank_digest}

    def _report(self, plan: IN.IngestionPlan, counts: dict) -> IngestionReport:
        concept_map = {c.ref: c.action for c in plan.concepts}
        formula_map = {f.ref: f.action for f in plan.formulas}
        return IngestionReport(
            outcome=plan.outcome, bank_id=plan.bank_id,
            content_version=plan.content_version,
            bank_digest=plan.bank_digest,
            plan_digest=IN.plan_digest(plan), counts=dict(counts),
            resolved=self._resolved(plan, concept_map, formula_map),
            verified=True)

    def _resolved(self, plan, concept_map, formula_map) -> tuple:
        import json as _json
        links: set[tuple] = set()
        stored_q = {q.question_id: _json.loads(q.canonical_json)
                    for q in plan.questions}
        for qid, raw in stored_q.items():
            for ref in raw.get("concepts", []):
                links.add((qid, "concept", ref,
                           concept_map.get(ref, "reuse")))
            for ref in raw.get("formulas", []):
                links.add((qid, "formula", ref,
                           formula_map.get(ref, "reuse")))
            for e in raw.get("knowledge_refs", []):
                kind = e["kind"]
                if kind == "concept":
                    links.add((qid, kind, e["ref"],
                               concept_map.get(e["ref"], "reuse")))
                elif kind == "formula":
                    links.add((qid, kind, e["ref"],
                               formula_map.get(e["ref"], "reuse")))
                else:
                    links.add((qid, kind, e["ref"], "carried"))
        return tuple(sorted(links))

    def _verify_unchanged(self, plan: IN.IngestionPlan) -> None:
        stored = self.qbank.get_bank(plan.bank_id)
        if stored is None or stored["digest"] != plan.bank_digest:
            raise IntegrationError("D7 verify failed: bank row diverged")
        live = self.qbank.question_digests(plan.bank_id)
        if set(live) != {q.question_id for q in plan.questions}:
            raise IntegrationError("D7 verify failed: question set diverged")

    def _verify_applied(self, plan: IN.IngestionPlan, removed: set) -> None:
        stored = self.qbank.get_bank(plan.bank_id)
        expect_q = {q.question_id: q.qdigest for q in plan.questions}
        if (stored is None or stored["digest"] != plan.bank_digest
                or stored["content_version"] != plan.content_version
                or stored["question_count"] != len(plan.questions)):
            raise IntegrationError("D7 verify failed: bank row mismatch")
        live = self.qbank.question_digests(plan.bank_id)
        if live != expect_q:
            raise IntegrationError("D7 verify failed: question digests mismatch")
        for c in plan.concepts:
            if c.action == "create" and not any(
                    k.stable_id == c.ref for k in
                    self.personal.concepts(c.subject_id)):
                raise IntegrationError(
                    f"D7 verify failed: concept missing {c.ref}")
        for f in plan.formulas:
            if f.action == "create":
                got = self.qbank.get_formula(f.ref)
                if got is None or got.latex != f.latex:
                    raise IntegrationError(
                        f"D7 verify failed: formula missing {f.ref}")
