# SPDX-License-Identifier: MIT
"""D7 ingestion planner (domain, pure): D6 bank -> Knowledge Core plan.

Pure planning layer. Takes an already-validated D6 ``Bank`` plus explicit
read-only snapshots of the stores and explicit caller catalogs, and emits
a deterministic ``IngestionPlan`` (validate -> plan -> apply -> verify;
the apply/verify steps live in ``application.bank_ingest``).

Policies (binding, see D7-INGESTION.md):

- D6 is the authority on the bank representation; the Knowledge Core owns
  its entities; this module is only the bridge. No second models/IDs.
- References resolve deterministically: existing -> reuse, missing +
  explicit catalog entry -> create, missing without catalog -> structured
  rejection (never silent invention). A ref used as *both* concept and
  formula is ambiguous -> deterministic rejection.
- Reuse never overwrites: existing concept/formula rows are left intact.
  A stored formula whose latex differs from the catalog is a conflict,
  never a silent overwrite.
- ``ingest(X); ingest(X) == ingest(X)``: same digest -> ``unchanged``
  (zero writes); higher ``content_version`` -> ``update``; same version
  with a different digest -> conflict; lower version -> stale rejection.
- No timestamps, no random, no hostnames, no filesystem order in the
  plan. The plan digest covers the semantic ops only.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from academic_core.domain import question_bank as QB
from academic_core.domain.entities import DomainError
from academic_core.domain.identity import validate as validate_id

PLAN_TAG = "d7-ingest-plan/1"
QUESTION_TAG = "d6-question/1"
IMPORTER = "d7-ingest/1"

OUTCOMES = ("create", "unchanged", "update")
Q_ACTIONS = ("create", "keep", "update")
E_ACTIONS = ("reuse", "create")

_CONCEPT_REF_RE = re.compile(
    r"^concept:([a-z0-9]+(?:-[a-z0-9]+)*):c:(\d{5})$"
)


def _dom(msg: str) -> DomainError:
    return DomainError(msg, code="AC-DOM-001")


def question_digest(q: QB.Question) -> str:
    """Per-question digest (change detection).

    NOTE: different semantics from the D6 *bank* digest (which covers the
    whole bank under ``d6-question-bank/1``). This tag covers one
    canonical question dict. Both are preserved; never mixed (D7 prompt
    section 9).
    """
    raw = QB.dumps_canonical(QB.question_to_dict(q)).encode("utf-8")
    return hashlib.sha256(QUESTION_TAG.encode("utf-8") + b"\x00" + raw).hexdigest()


def import_provenance(base: dict, bank_id: str, bank_digest: str) -> dict:
    """Merge D6 provenance with the deterministic import stamp."""
    merged = dict(base)
    merged["imported_by"] = IMPORTER
    merged["bank"] = bank_id
    merged["bank_digest"] = bank_digest
    return merged


def _is_plain(v: object) -> bool:
    if v is None or isinstance(v, (bool, int, str)):
        return not isinstance(v, float)
    if isinstance(v, float):
        return False
    if isinstance(v, (list, tuple)):
        return all(_is_plain(i) for i in v)
    if isinstance(v, dict):
        return all(isinstance(k, str) and _is_plain(i) for k, i in v.items())
    return False


def _concept_subject(ref: str) -> tuple[str, int]:
    m = _CONCEPT_REF_RE.match(ref)
    if not m:
        raise _dom(f"bad concept ref (need concept:<subject>:c:NNNNN): {ref!r}")
    return m.group(1), int(m.group(2))


@dataclass(frozen=True)
class PlannedQuestion:
    question_id: str
    action: str  # create | keep | update
    qdigest: str
    qtype: str
    canonical_json: str = field(compare=False)
    provenance: dict = field(compare=False)


@dataclass(frozen=True)
class PlannedConcept:
    ref: str
    action: str  # reuse | create
    subject_id: str
    name: str = field(compare=False)


@dataclass(frozen=True)
class PlannedFormula:
    ref: str
    action: str  # reuse | create
    latex: str = field(compare=False)
    topic_id: str = field(default="", compare=False)
    concept_ids: tuple = ()
    variables: tuple = ()
    units: tuple = ()
    provenance: dict = field(default_factory=dict, compare=False)


@dataclass(frozen=True)
class CarriedRef:
    """knowledge_ref kept opaquely (section/document/topic: no D7 store)."""

    question_id: str
    kind: str
    ref: str


@dataclass(frozen=True)
class IngestionPlan:
    bank_id: str
    title: str
    content_version: int
    bank_digest: str
    outcome: str  # create | unchanged | update
    questions: tuple = ()
    concepts: tuple = ()
    formulas: tuple = ()
    deletes: tuple = ()
    carried_refs: tuple = ()
    counters_bump: dict = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        if self.outcome not in OUTCOMES:
            raise _dom(f"bad outcome: {self.outcome!r}")


def plan_to_dict(plan: IngestionPlan) -> dict:
    """Lossless plain-dict view (no volatile fields exist by construction)."""
    return {
        "bank_id": plan.bank_id,
        "title": plan.title,
        "content_version": plan.content_version,
        "bank_digest": plan.bank_digest,
        "outcome": plan.outcome,
        "questions": [
            {"question_id": q.question_id, "action": q.action,
             "qdigest": q.qdigest, "qtype": q.qtype,
             "canonical_json": q.canonical_json, "provenance": q.provenance}
            for q in plan.questions
        ],
        "concepts": [
            {"ref": c.ref, "action": c.action,
             "subject_id": c.subject_id, "name": c.name}
            for c in plan.concepts
        ],
        "formulas": [
            {"ref": f.ref, "action": f.action, "latex": f.latex,
             "topic_id": f.topic_id, "concept_ids": list(f.concept_ids),
             "variables": [dict(v) if isinstance(v, dict) else v
                           for v in f.variables],
             "units": list(f.units), "provenance": f.provenance}
            for f in plan.formulas
        ],
        "deletes": list(plan.deletes),
        "carried_refs": [
            {"question_id": r.question_id, "kind": r.kind, "ref": r.ref}
            for r in plan.carried_refs
        ],
        "counters_bump": dict(plan.counters_bump),
    }


def plan_digest(plan: IngestionPlan) -> str:
    """Reproducible digest of the semantic ops (timestamps cannot leak:
    the plan holds none)."""
    raw = QB.dumps_canonical(plan_to_dict(plan)).encode("utf-8")
    return hashlib.sha256(PLAN_TAG.encode("utf-8") + b"\x00" + raw).hexdigest()


def _check_catalog_concepts(catalog: object) -> dict:
    if catalog is None:
        return {}
    if not isinstance(catalog, dict):
        raise _dom("catalog_concepts must be a dict ref -> name")
    out = {}
    for ref, name in catalog.items():
        _concept_subject(ref)
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 400:
            raise _dom(f"catalog concept name must be 1..400 chars: {ref!r}")
        out[ref] = name.strip()
    return out


def _check_catalog_formulas(catalog: object) -> dict:
    if catalog is None:
        return {}
    if not isinstance(catalog, dict):
        raise _dom("catalog_formulas must be a dict ref -> spec")
    out = {}
    for ref, spec in catalog.items():
        if not isinstance(ref, str) or not ref.strip() or len(ref) > 256:
            raise _dom(f"bad catalog formula ref: {ref!r}")
        if not isinstance(spec, dict):
            raise _dom(f"catalog formula spec must be a dict: {ref!r}")
        unknown = set(spec) - {"latex", "topic_id", "concept_ids",
                               "variables", "units"}
        if unknown:
            raise _dom(f"unknown formula spec keys {sorted(unknown)}: {ref!r}")
        latex = spec.get("latex")
        if not isinstance(latex, str) or not 1 <= len(latex.strip()) <= 4000:
            raise _dom(f"catalog formula latex must be 1..4000 chars: {ref!r}")
        topic_id = spec.get("topic_id", "")
        if not isinstance(topic_id, str) or len(topic_id) > 256:
            raise _dom(f"catalog formula topic_id limited to 256 chars: {ref!r}")
        concept_ids = spec.get("concept_ids", [])
        if (not isinstance(concept_ids, list)
                or not all(isinstance(c, str) for c in concept_ids)):
            raise _dom(f"catalog formula concept_ids must be [str]: {ref!r}")
        variables = spec.get("variables", [])
        if not isinstance(variables, list) or not _is_plain(variables):
            raise _dom(f"catalog formula variables must be plain JSON: {ref!r}")
        units = spec.get("units", [])
        if (not isinstance(units, list)
                or not all(isinstance(u, str) for u in units)):
            raise _dom(f"catalog formula units must be [str]: {ref!r}")
        out[ref] = {"latex": latex.strip(), "topic_id": topic_id,
                    "concept_ids": list(concept_ids),
                    "variables": [dict(v) if isinstance(v, dict) else v
                                  for v in variables],
                    "units": list(units)}
    return out


def plan_bank(bank: QB.Bank, *, existing_bank: dict | None,
              existing_concepts: dict, existing_formulas: dict,
              known_subjects: set | frozenset,
              catalog_concepts=None, catalog_formulas=None) -> IngestionPlan:
    """Build the deterministic ingestion plan for a validated D6 bank."""
    if not isinstance(bank, QB.Bank):
        raise _dom("plan_bank needs a validated question_bank.Bank")
    if existing_bank is not None and not isinstance(existing_bank, dict):
        raise _dom("existing_bank must be None or a dict")
    if not isinstance(existing_concepts, dict) or not isinstance(
            existing_formulas, dict):
        raise _dom("existing_concepts/formulas must be dicts")
    known_subjects = set(known_subjects)
    cat_c = _check_catalog_concepts(catalog_concepts)
    cat_f = _check_catalog_formulas(catalog_formulas)

    digest = QB.bank_digest(bank)

    same_digest = False
    if existing_bank is not None:
        stored_version = existing_bank.get("content_version")
        stored_digest = existing_bank.get("digest")
        if not isinstance(stored_version, int) or not isinstance(
                stored_digest, str):
            raise _dom("existing_bank needs {content_version: int, digest: str}")
        if stored_digest == digest:
            # Same content: outcome stays ``unchanged`` (zero writes), but
            # refs are still resolved so the plan carries the full picture
            # and any externally-removed entity surfaces deterministically.
            same_digest = True
            outcome = "unchanged"
        elif bank.content_version <= stored_version:
            raise _dom(
                f"bank {bank.bank_id!r} conflict: stored v{stored_version} "
                f"vs incoming v{bank.content_version} with a different digest "
                "(no silent overwrite; bump content_version for a new version)")
        else:
            outcome = "update"
        stored_q = existing_bank.get("questions", {})
        if not isinstance(stored_q, dict):
            raise _dom("existing_bank questions must be a dict")
    else:
        outcome = "create"
        stored_q = {}

    # -- collect reference usage --------------------------------------
    concept_uses: dict[str, list[str]] = {}
    formula_uses: dict[str, list[str]] = {}
    carried: list[CarriedRef] = []
    for q in bank.questions:
        for ref in q.concepts:
            concept_uses.setdefault(ref, []).append(q.question_id)
        for ref in q.formulas:
            formula_uses.setdefault(ref, []).append(q.question_id)
        for e in q.knowledge_refs:
            if e["kind"] == "concept":
                concept_uses.setdefault(e["ref"], []).append(q.question_id)
            elif e["kind"] == "formula":
                formula_uses.setdefault(e["ref"], []).append(q.question_id)
            else:
                carried.append(CarriedRef(q.question_id, e["kind"], e["ref"]))
    ambiguous = sorted(set(concept_uses) & set(formula_uses))
    if ambiguous:
        raise _dom(f"ambiguous refs used as concept and formula: {ambiguous}")

    # -- concepts ------------------------------------------------------
    planned_concepts: list[PlannedConcept] = []
    max_concept_n = 0
    for ref in sorted(concept_uses):
        subject_id, number = _concept_subject(ref)
        known = existing_concepts.get(ref)
        if known is not None:
            planned_concepts.append(PlannedConcept(
                ref, "reuse", known.get("subject_id", subject_id),
                known.get("name", "")))
            continue
        name = cat_c.get(ref)
        if name is None:
            raise _dom(
                f"unresolved concept {ref!r} used by {concept_uses[ref]}: "
                "no store row and no catalog_concepts entry (never invented)")
        if validate_id(f"subject:{subject_id}") != "subject":
            raise _dom(f"bad concept subject scope: {ref!r}")
        if f"subject:{subject_id}" not in known_subjects:
            raise _dom(
                f"unknown subject 'subject:{subject_id}' for concept {ref!r}")
        planned_concepts.append(PlannedConcept(
            ref, "create", f"subject:{subject_id}", name))
        max_concept_n = max(max_concept_n, number)

    # -- formulas ------------------------------------------------------
    planned_formulas: list[PlannedFormula] = []
    for ref in sorted(formula_uses):
        stored = existing_formulas.get(ref)
        spec = cat_f.get(ref)
        if stored is not None:
            if spec is not None and spec["latex"] != stored.get("latex"):
                raise _dom(
                    f"formula {ref!r} modified (stored latex differs from "
                    "catalog): refusing silent overwrite")
            planned_formulas.append(PlannedFormula(
                ref, "reuse", stored.get("latex", ""), "",
                (), (), (), {}))
            continue
        if spec is None:
            raise _dom(
                f"unresolved formula {ref!r} used by {formula_uses[ref]}: "
                "no store row and no catalog_formulas entry (never invented)")
        planned_formulas.append(PlannedFormula(
            ref, "create", spec["latex"], spec["topic_id"],
            tuple(spec["concept_ids"]),
            tuple(spec["variables"]), tuple(spec["units"]),
            import_provenance(bank.provenance, bank.bank_id, digest)))

    # -- questions -----------------------------------------------------
    planned_questions: list[PlannedQuestion] = []
    for q in bank.questions:
        qd = question_digest(q)
        if same_digest:
            if stored_q.get(q.question_id) != qd:
                raise _dom(
                    f"stored state diverged for unchanged bank {bank.bank_id!r}:"
                    f" {q.question_id!r} (re-ingest the owning version first)")
            action = "keep"
        elif outcome == "create":
            action = "create"
        elif stored_q.get(q.question_id) == qd:
            action = "keep"
        else:
            action = "create" if q.question_id not in stored_q else "update"
        planned_questions.append(PlannedQuestion(
            q.question_id, action, qd, q.qtype,
            QB.dumps_canonical(QB.question_to_dict(q)),
            import_provenance(q.provenance, bank.bank_id, digest)))
    planned_questions.sort(key=lambda p: p.question_id)

    new_ids = {q.question_id for q in bank.questions}
    if same_digest and set(stored_q) != new_ids:
        raise _dom(
            f"stored state diverged for unchanged bank {bank.bank_id!r} "
            "(question set differs; re-ingest the owning version first)")
    deletes = tuple(sorted(qid for qid in stored_q if qid not in new_ids))

    counters_bump = {"concept": max_concept_n} if max_concept_n else {}

    return IngestionPlan(
        bank_id=bank.bank_id, title=bank.title,
        content_version=bank.content_version, bank_digest=digest,
        outcome=outcome, questions=tuple(planned_questions),
        concepts=tuple(planned_concepts), formulas=tuple(planned_formulas),
        deletes=deletes, carried_refs=tuple(sorted(
            carried, key=lambda r: (r.question_id, r.kind, r.ref))),
        counters_bump=counters_bump)
