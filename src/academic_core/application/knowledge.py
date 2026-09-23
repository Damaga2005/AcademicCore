# SPDX-License-Identifier: MIT
"""F4.1 knowledge use cases: teaching-guide extraction + subject knowledge.

Teaching guide flow (no new parser, no network):

    Resource (CAS, provenance)
      -> DocumentService.load_ast   (F3/F3.1 importers: pdf/html/md/docx...)
      -> documents.syllabus.analyze (heuristic proposal, needs_review flags)
      -> human confirmation         (apply_syllabus(..., confirmed=True))
      -> Professor/SubjectStaff + AssessmentScheme/Block/Component

Subject knowledge reuses the F3.1 extractors (formulas / problems / terms)
over the subject's documents; every item keeps its source resource id.
"""

from __future__ import annotations

from dataclasses import dataclass

from academic_core.application.academic_mgmt import EvaluationService
from academic_core.domain.entities import DomainError, Professor, SubjectStaff
from academic_core.domain.identity import make, slugify
from academic_core.documents import syllabus as SY
from academic_core.errors import AcademicManagementError

EXTRACTOR = "syllabus/1"


def _err(msg: str, code: str = "AC-ACD-001") -> AcademicManagementError:
    return AcademicManagementError(msg, code=code)


@dataclass(frozen=True)
class ApplyReport:
    professors_created: int
    professors_linked: int
    schemes_created: int
    skipped_for_review: int


@dataclass(frozen=True)
class SubjectKnowledge:
    subject_id: str
    formulas: tuple
    problems: tuple
    terms: tuple
    sources: tuple[str, ...]
    skipped: tuple[tuple[str, str], ...]  # (resource_id, reason)


class KnowledgeService:
    def __init__(self, academic, documents, records, material, evaluation: EvaluationService):
        self.academic = academic
        self.documents = documents
        self.records = records
        self.material = material
        self.evaluation = evaluation

    def _ast(self, resource_id: str):
        res = self.records.get(resource_id)
        if res is None:
            raise _err(f"unknown resource: {resource_id}", "AC-ACD-002")
        doc, parser, parser_version = self.documents.load_ast(resource_id)
        cur = res.current()
        prov = {"resource_id": resource_id, "version": cur.version,
                "content_hash": cur.content_hash, "parser": parser,
                "parser_version": parser_version, "extractor": EXTRACTOR}
        return doc, prov

    def analyze_syllabus(self, resource_id: str) -> SY.SyllabusProposal:
        doc, prov = self._ast(resource_id)
        return SY.analyze(SY.document_lines(doc), provenance=prov)

    def analyze_syllabus_text(self, text: str, source: str = "") -> SY.SyllabusProposal:
        return SY.analyze(text, provenance={"source": source, "extractor": EXTRACTOR})

    def apply_syllabus(self, subject_id: str, proposal: SY.SyllabusProposal, *,
                       confirmed: bool = False) -> ApplyReport:
        """Write a (possibly user-edited) proposal. Refuses without explicit
        confirmation — the heuristic never writes on its own (Gestion rule).
        Schemes with no components (unparsed text) are skipped, counted."""
        if not confirmed:
            raise _err("teaching-guide data needs explicit confirmation", "AC-ACD-001")
        if self.academic.get_subject(subject_id) is None:
            raise _err(f"unknown subject: {subject_id}", "AC-ACD-002")
        created = linked = 0
        staff = self.academic.staff_of(subject_id)
        by_name = {slugify(p.name): p.stable_id for p, _ in staff}
        for i, p in enumerate(proposal.professors):
            try:
                key = slugify(p.name)
                if key in by_name:
                    continue  # already on this subject's staff: idempotent
                # Same name elsewhere is NOT evidence of the same person
                # (F4.1 closure): never attach another subject's professor.
                pid, n = make("professor", key), 1
                while self.academic.get_professor(pid) is not None:
                    n += 1
                    pid = make("professor", f"{key}-{n}")
                self.academic.add_professor(Professor(pid, p.name.strip()))
                created += 1
                self.academic.attach_staff(SubjectStaff(subject_id, pid, p.role or "docente",
                                                        "", i))
                by_name[key] = pid
                linked += 1
            except (DomainError, ValueError) as e:
                raise _err(str(e), "AC-ACD-004") from e
        schemes = skipped = 0
        for j, s in enumerate(proposal.schemes):
            if not s.components and not s.blocks:
                skipped += 1
                continue
            self.evaluation.create_scheme(
                subject_id, s.name, order=j,
                components=[{"name": c.name, "weight": c.weight, "kind": c.kind}
                            for c in s.components],
                blocks=[{"name": b.name, "weight": b.weight,
                         "components": [{"name": c.name, "weight": c.weight, "kind": c.kind}
                                        for c in b.components]} for b in s.blocks])
            schemes += 1
        return ApplyReport(created, linked, schemes, skipped)

    def subject_knowledge(self, subject_id: str, limit_docs: int = 200) -> SubjectKnowledge:
        """F3.1 extractors over the subject's documents (reuse, no new parser)."""
        from academic_core.documents import formulas as F, problems as P, render_markdown as RM
        from academic_core.documents import terms as T
        forms, probs, terms, sources, skipped = [], [], [], [], []
        for d in self.material.documents_of(subject_id)[:limit_docs]:
            try:
                doc, _ = self._ast(d.resource_id)
            except (ValueError, KeyError) as e:
                skipped.append((d.resource_id, str(e)[:120]))
                continue
            sources.append(d.resource_id)
            forms.extend(F.extract_from_document(doc, source=d.resource_id))
            probs.extend(P.extract_problems_from_document(doc, source=d.resource_id))
            terms.extend(T.extract_terms(RM.render(doc), source=d.resource_id))
        return SubjectKnowledge(subject_id, tuple(F.deduplicate(forms)), tuple(probs),
                                tuple(terms), tuple(sources), tuple(skipped))
