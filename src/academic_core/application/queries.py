"""Academic queries (Phase 4): encapsulated reads for planning and overviews.

UI consumes these — never repositories or SQL. All comparisons in ISO date
strings (lexicographic == chronological). No Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DeadlineView:
    target_id: str
    kind: str  # assignment|task|exam|project|lab
    title: str
    subject_id: str
    due: str  # ISO datetime
    label: str = ""
    done: bool = False


class AcademicQueries:
    def __init__(self, academic, planning, grading, gradebook):
        self.academic = academic
        self.planning = planning
        self.grading = grading
        self.gradebook = gradebook

    # -- hierarchy ---------------------------------------------------------
    def subjects_by_term(self, term_id: str) -> list:
        return self.academic.subjects_of_term(term_id)

    def tree(self) -> list[dict]:
        """Full hierarchy as nested dicts (lazy per level; no bulk preload)."""
        out = []
        for u in self.academic.list_universities():
            du = {"university": u, "degrees": []}
            for d in self.academic.degrees_of(u.stable_id):
                dd = {"degree": d, "years": []}
                for y in self.academic.years_of(d.stable_id):
                    yy = {"year": y, "terms": []}
                    for t in self.academic.terms_of(y.stable_id):
                        yy["terms"].append(
                            {"term": t,
                             "subjects": self.academic.subjects_of_term(t.stable_id)})
                    dd["years"].append(yy)
                du["degrees"].append(dd)
            out.append(du)
        return out

    # -- activities ----------------------------------------------------------
    def activities_by_subject(self, subject_id: str) -> dict:
        pl = self.planning
        return {"assignments": pl.assignments_of(subject_id),
                "exams": pl.exams_of(subject_id),
                "projects": pl.projects_of(subject_id),
                "labs": pl.labs_of(subject_id),
                "tasks": pl.tasks_of(subject_id),
                "topics": self.academic.topics_of(subject_id),
                "refs": pl.refs_of(subject_id)}

    def _deadlines(self) -> list[DeadlineView]:
        out: list[DeadlineView] = []
        for s in self.academic.all_subjects():
            sid = s.stable_id
            for a in self.planning.assignments_of(sid):
                done = a.status in ("submitted", "graded", "archived")
                for d in self.planning.deadlines_of(a.stable_id):
                    out.append(DeadlineView(a.stable_id, "assignment", a.title,
                                            sid, d.due.isoformat(), d.label, done))
            for t in self.planning.tasks_of(sid):
                done = t.state in ("hecha", "cancelada")
                task_deadlines = self.planning.deadlines_of(t.stable_id) if t.day else []
                for d in task_deadlines:
                    out.append(DeadlineView(t.stable_id, "task", t.title,
                                            sid, d.due.isoformat(), d.label, done))
                if t.day and not task_deadlines:
                    out.append(DeadlineView(t.stable_id, "task", t.title, sid,
                                            t.day.isoformat() + "T23:59:00", "", done))
            for e in self.planning.exams_of(sid):
                if e.day:
                    time = "T09:00:00"
                    out.append(DeadlineView(e.stable_id, "exam", e.title, sid,
                                            e.day.isoformat() + time, e.session,
                                            e.status in ("graded", "archived", "cancelled")))
        return sorted(out, key=lambda d: (d.due, d.title))

    def upcoming_deadlines(self, today: date, limit: int = 20) -> list[DeadlineView]:
        now = today.isoformat() + "T00:00:00"
        return [d for d in self._deadlines() if not d.done and d.due >= now][:limit]

    def overdue_deadlines(self, today: date, limit: int = 50) -> list[DeadlineView]:
        now = today.isoformat() + "T00:00:00"
        return [d for d in self._deadlines() if not d.done and d.due < now][:limit]

    def pending_assignments(self, subject_id: str | None = None) -> list:
        subs = ([self.academic.get_subject(subject_id)]
                if subject_id else self.academic.all_subjects())
        out = []
        for s in subs:
            if s is None:
                continue
            out.extend(a for a in self.planning.assignments_of(s.stable_id)
                       if a.status in ("draft", "active"))
        return out

    def upcoming_exams(self, today: date, limit: int = 20) -> list:
        out = []
        for s in self.academic.all_subjects():
            out.extend(e for e in self.planning.exams_of(s.stable_id)
                       if e.day and e.day >= today and e.status != "cancelled")
        return sorted(out, key=lambda e: (e.day, e.title))[:limit]

    def grades_by_subject(self, subject_id: str) -> list:
        return self.gradebook.grades_of(subject_id)
