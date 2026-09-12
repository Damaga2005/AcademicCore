"""SearchService interface (Phase 1 boundary; full FTS5 lands later).

Searches subjects, assignments, tasks and projects by normalized substring.
Normalization mirrors Gestion `normalizar_busqueda` (NFKD, casefold).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from unicodedata import normalize


def norm(text: str) -> str:
    return "".join(c for c in normalize("NFKD", text.casefold()) if not c.iscombining())


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
