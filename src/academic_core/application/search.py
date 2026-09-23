"""SearchService interface (Phase 1 boundary; full FTS5 lands later).

Searches subjects, assignments, tasks and projects by normalized substring.
Normalization mirrors Gestion `normalizar_busqueda` (NFKD, casefold).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from unicodedata import combining, normalize


def norm(text: str) -> str:
    # F4.1 fix: the former ``c.iscombining()`` does not exist on str, so every
    # non-empty query raised AttributeError (pre-existing defect, untested).
    return "".join(c for c in normalize("NFKD", text.casefold()) if not combining(c))


@dataclass(frozen=True)
class Hit:
    kind: str
    ref: str
    title: str


class SearchService(ABC):
    @abstractmethod
    def search(self, query: str, limit: int = 20) -> list[Hit]: ...


class SimpleSearchService(SearchService):
    def __init__(self, academic, planning):
        self.academic = academic
        self.planning = planning

    def search(self, query: str, limit: int = 20) -> list[Hit]:
        q = norm(query)
        hits: list[Hit] = []
        for s in self.academic.all_subjects():
            if q in norm(f"{s.name} {s.acronym} {s.code}"):
                hits.append(Hit("subject", s.stable_id, s.name))
        for t in self.planning.all_tasks():
            if q in norm(t.title):
                hits.append(Hit("task", t.stable_id, t.title))
        for s in self.academic.all_subjects():
            for a in self.planning.assignments_of(s.stable_id):
                if q in norm(a.title):
                    hits.append(Hit("assignment", a.stable_id, a.title))
            for p in self.planning.projects_of(s.stable_id):
                if q in norm(p.title):
                    hits.append(Hit("project", p.stable_id, p.title))
        return hits[:limit]


# ---------------------------------------------------------------------------
# F4.1: unified search (subjects, professors, tasks, milestones, notes,
# external resources, documents + page). Documents go through the EXISTING
# FTS5 index (resources_fts); entities are small and matched by normalized
# substring (same normalization as Gestion `busqueda.py`). No second engine.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class UnifiedHit:
    kind: str  # subject|professor|task|milestone|note|link|document
    ref: str
    title: str
    subject_id: str = ""
    snippet: str = ""
    page: int | None = None


class UnifiedSearchService:
    def __init__(self, academic, planning, material, personal, fts):
        self.academic = academic
        self.planning = planning
        self.material = material
        self.personal = personal
        self.fts = fts

    @staticmethod
    def _page_of(pages: list[tuple[int, str]], q: str) -> tuple[int | None, str]:
        for page, text in pages:
            n = norm(text)
            i = n.find(q)
            if i >= 0:
                # NFKD+drop-combining keeps base-char positions for Latin text
                return page, text[max(0, i - 60): i + len(q) + 60].strip()
        return None, ""

    def search(self, query: str, limit: int = 50, subject_id: str = "") -> list[UnifiedHit]:
        q = norm(query.strip())
        if len(q) < 2:
            return []
        hits: list[UnifiedHit] = []
        subjects = self.academic.all_subjects()
        for s in subjects:
            if subject_id and s.stable_id != subject_id:
                continue
            if q in norm(f"{s.name} {s.acronym} {s.code}"):
                hits.append(UnifiedHit("subject", s.stable_id, s.name, s.stable_id))
        for p in self.academic.all_professors():
            if q in norm(f"{p.name} {p.email} {p.office}"):
                subs = self.academic.subjects_of_professor(p.stable_id)
                if not subject_id or subject_id in subs:
                    hits.append(UnifiedHit("professor", p.stable_id, p.name,
                                           subs[0] if subs else ""))
        for t in self.planning.all_tasks():
            if (not subject_id or t.subject_id == subject_id) and q in norm(
                    f"{t.title} {t.description}"):
                hits.append(UnifiedHit("task", t.stable_id, t.title, t.subject_id))
        for m in self.personal.milestones():
            if (not subject_id or m.subject_id == subject_id) and q in norm(m.name):
                hits.append(UnifiedHit("milestone", m.stable_id, m.name, m.subject_id))
        if not subject_id:
            for n in self.personal.notes():
                if q in norm(n.text):
                    hits.append(UnifiedHit("note", n.stable_id, n.text[:80]))
        for x in self.material.all_externals():
            if (not subject_id or x.subject_id == subject_id) and q in norm(
                    f"{x.name} {x.kind} {x.provider}"):
                hits.append(UnifiedHit("link", x.stable_id, x.name, x.subject_id))
        docs = self.fts.search(query, subject=subject_id, limit=limit)
        ctx = self.material.search_context([d["stable_id"] for d in docs])
        for d in docs:
            subs, pages = ctx[d["stable_id"]]
            page, snippet = self._page_of(pages, q)
            hits.append(UnifiedHit("document", d["stable_id"], d["title"],
                                   subs[0] if subs else "", snippet or d["snippet"], page))
        return hits[:limit]
