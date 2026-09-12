"""Application services (Phase 1): use-cases orchestrating domain + repos.

No business logic in UI. No Qt. No SQLAlchemy. Services raise ApplicationError
on misuse; domain invariants raise DomainError.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from academic_core.domain import entities as E
from academic_core.domain import grading as G
from academic_core.domain import schedule as S
from academic_core.domain.identity import make, slugify
from academic_core.infrastructure.repositories import (
    AcademicRepository, GradingRepository, PlanningRepository, StudyRepository,
)


class ApplicationError(ValueError):
    pass


def _need(cond: bool, msg: str) -> None:
    if not cond:
        raise ApplicationError(msg)


class AcademicService:
    def __init__(self, repo: AcademicRepository):
        self.repo = repo

    def create_subject(self, name: str, term_id: str, code: str = "",
                       acronym: str = "", credits: float = 0.0,
                       kind: str = "obligatoria", course: int = 0) -> E.Subject:
        slug = slugify(acronym or name)
        s = E.Subject(f"subject:{slug}", code, name.strip(),
                      (acronym or "").upper(), "", credits, kind, course, term_id)
        _need(self.repo.get_subject(s.stable_id) is None,
              f"subject already exists: {s.stable_id}")
        self.repo.add_subject(s)
        return s

    def update_subject(self, s: E.Subject) -> E.Subject:
        _need(self.repo.get_subject(s.stable_id) is not None, "unknown subject")
        self.repo.add_subject(s)  # INSERT OR REPLACE
        return s

    def create_assignment(self, plan: PlanningRepository, subject_id: str,
                          title: str, **kw) -> E.Assignment:
        _need(self.repo.get_subject(subject_id) is not None, "unknown subject")
        alloc = self.repo.allocator()
        n = self.repo.load_counters().get("assignment", 0) + 1
        a = E.Assignment(make("assignment", subject_id.split(":", 1)[1], f"{n:05d}"),
                         subject_id, title.strip(), **kw)
        plan.add_assignment(a)
        alloc.counters["assignment"] = n
        self.repo.save_counters(alloc.snapshot())
        return a

    def schedule_assignment(self, plan: PlanningRepository, assignment_id: str,
                            due: datetime, label: str = "") -> int:
        a = plan.get_assignment(assignment_id)
        _need(a is not None, "unknown assignment")
        E.Deadline(assignment_id, due, label)  # validates target id shape
        return plan.add_deadline(assignment_id, due, label)

    def create_exam(self, plan: PlanningRepository, subject_id: str,
                    title: str, **kw) -> E.Exam:
        _need(self.repo.get_subject(subject_id) is not None, "unknown subject")
        n = self.repo.load_counters().get("exam", 0) + 1
        e = E.Exam(make("exam", subject_id.split(":", 1)[1], f"{n:05d}"),
                   subject_id, title.strip(), **kw)
        plan.add_exam(e)
        self.repo.save_counters({"exam": n, **self.repo.load_counters()})
        return e

    def create_project(self, plan: PlanningRepository, subject_id: str,
                       title: str, **kw) -> E.Project:
        _need(self.repo.get_subject(subject_id) is not None, "unknown subject")
        n = self.repo.load_counters().get("project", 0) + 1
        p = E.Project(make("project", subject_id.split(":", 1)[1], f"{n:05d}"),
                      subject_id, title.strip(), **kw)
        plan.add_project(p)
        self.repo.save_counters({"project": n, **self.repo.load_counters()})
        return p

    def create_task(self, plan: PlanningRepository, study: StudyRepository,
                    subject_id: str, title: str, kind: str = "tarea_general",
                    **kw) -> E.Task:
        _need(self.repo.get_subject(subject_id) is not None, "unknown subject")
        n = self.repo.load_counters().get("task", 0) + 1
        t = E.Task(make("task", subject_id.split(":", 1)[1], f"{n:05d}"),
                   subject_id, title.strip(), kind, **kw)
        plan.add_task(t)
        self.repo.save_counters({"task": n, **self.repo.load_counters()})
        if t.is_exam:
            # Exam tasks auto-create their StudySpace (refs, never copies).
            study.ensure_study_space(E.StudySpace(subject_id, t.stable_id,
                                                  f"Estudio — {title.strip()}"))
        return t

    # -- academic structure --------------------------------------------------
    def create_university(self, name: str) -> E.University:
        from academic_core.domain.identity import slugify as _slug
        u = E.University(f"university:{_slug(name)}", name.strip())
        self.repo.add_university(u)
        return u

    def create_degree(self, university_id: str, name: str) -> E.Degree:
        from academic_core.domain.identity import slugify as _slug
        d = E.Degree(f"degree:{_slug(name)}", name.strip(), university_id)
        self.repo.add_degree(d)
        return d

    def create_year(self, degree_id: str, label: str) -> E.AcademicYear:
        y = E.AcademicYear(f"year:{label.strip()}", label.strip(), degree_id)
        self.repo.add_year(y)
        return y

    def create_term(self, year_id: str, label: str, kind: str, index: int,
                    start=None, end=None) -> E.Term:
        from academic_core.domain.identity import slugify as _slug
        t = E.Term(f"term:{_slug(label)}", label.strip(), kind, index,
                   year_id, start, end)
        self.repo.add_term(t)
        return t

    def create_topic(self, subject_id: str, index: str, title: str,
                     description: str = "") -> E.Topic:
        _need(self.repo.get_subject(subject_id) is not None, "unknown subject")
        t = E.Topic(f"{subject_id.replace('subject:', 'topic:')}:t{index}",
                    subject_id, index, title.strip(), description)
        self.repo.add_topic(t)
        return t

    def create_professor(self, name: str, email: str = "",
                         office: str = "") -> E.Professor:
        from academic_core.domain.identity import slugify as _slug
        p = E.Professor(f"professor:{_slug(name)}", name.strip(), email, office)
        self.repo.add_professor(p)
        return p

    def attach_professor(self, subject_id: str, professor_id: str,
                         role: str = "docente", groups: str = "") -> None:
        self.repo.attach_staff(E.SubjectStaff(subject_id, professor_id, role, groups))

    # -- safe delete (delegates to repository guards) --------------------------
    def delete_university(self, stable_id: str) -> None:
        self.repo.delete_university(stable_id)

    def delete_degree(self, stable_id: str) -> None:
        self.repo.delete_degree(stable_id)

    def delete_year(self, stable_id: str) -> None:
        self.repo.delete_year(stable_id)

    def delete_term(self, stable_id: str) -> None:
        self.repo.delete_term(stable_id)

    def delete_subject(self, stable_id: str) -> None:
        self.repo.delete_subject(stable_id)

    def delete_topic(self, plan, stable_id: str) -> None:
        self.repo.delete_topic(stable_id)

    def delete_assignment(self, plan: PlanningRepository, stable_id: str) -> None:
        plan.delete_assignment(stable_id)

    def delete_exam(self, plan: PlanningRepository, stable_id: str) -> None:
        plan.delete_exam(stable_id)

    def delete_project(self, plan: PlanningRepository, stable_id: str) -> None:
        plan.delete_project(stable_id)

    def delete_lab(self, plan: PlanningRepository, stable_id: str) -> None:
        plan.delete_lab(stable_id)

    def delete_task(self, plan: PlanningRepository, stable_id: str) -> None:
        plan.delete_task(stable_id)


class GradingService:
    def __init__(self, repo: GradingRepository):
        self.repo = repo

    def record_scheme(self, subject_id: str, scheme: str,
                      components: list[E.GradeComponent], final: str | None = None,
                      blocks: dict[str, str] | None = None) -> None:
        if final is not None:
            Decimal(final)  # validates
        self.repo.save_scheme(subject_id, scheme, components, final, blocks)

    def calculate(self, subject_id: str, rule: str = "maximo") -> G.FinalVerdict:
        data = self.repo.load_schemes(subject_id)
        if not data:
            return G.FinalVerdict(None, False, "sin_evaluar")
        by_block: dict[str, list[G.Scored]] = {}
        schemes: list[tuple[str, G.Aggregate]] = []
        override: Decimal | None = None
        for name, (comps, final, blocks) in data.items():
            if final is not None and override is None:
                override = Decimal(final)
            loose = [G.Scored(Decimal(c.weight), Decimal(c.score) if c.score else None)
                     for c in comps if c.name not in (blocks or {})]
            for c in comps:
                if c.name in (blocks or {}):
                    by_block.setdefault(blocks[c.name], []).append(
                        G.Scored(Decimal(c.weight), Decimal(c.score) if c.score else None))
            # NOTE: block weights live on the block record in the original model;
            # F1 stores member weights only, so a block weighs the sum of its
            # members (documented in CONFLICTS.md §B). Block-level weight % of
            # the scheme arrives with the Phase 4 grading UI.
            items = list(loose)
            for bname, members in by_block.items():
                bw = sum((m.weight for m in members), Decimal(0))
                items.append(G.aggregate_block(bw, members))
            by_block.clear()
            schemes.append((name, G.aggregate(items)))
        return G.final_verdict(schemes, override, rule)


class ScheduleService:
    def __init__(self, plan: PlanningRepository):
        self.plan = plan
    def add_series(self, subject_id: str, **kw) -> tuple[int, list[dict]]:
        s = S.Series(subject_id=subject_id, **kw)  # validates coherence
        key = self.plan.add_series(subject_id, kw["kind"], kw["weekday"], kw["start"],
                                   kw["end"], kw["first_day"], kw["last_day"],
                                   kw.get("interval_weeks", 1), kw.get("room", ""))
        sessions = S.expand_sessions(s)
        # warn-only conflicts against same-subject tasks on those dates
        return key, [{"day": d.isoformat()} for d in sessions]

    def check(self, day: date, start: str, end: str) -> list[dict]:
        from academic_core.domain.conflicts import TimedItem, detect
        tasks = [TimedItem("task", t.stable_id, t.title,
                           t.day.isoformat() if t.day else "", t.start, t.end)
                 for t in self.plan.all_tasks() if t.start and t.day]
        series = [(TimedItem("series", str(r["id"]), r["kind"], "", r["start"], r["end"]),
                   S.Series(r["subject_id"], r["kind"], r["weekday"], r["start"], r["end"],
                            date.fromisoformat(r["first_day"]),
                            date.fromisoformat(r["last_day"]), r["interval_weeks"], r["room"]))
                  for r in self.plan.all_series()]
        return [c.__dict__ for c in detect(day.isoformat(), start, end, tasks, series)]


class ResultsService:
    """Generic gradebook (Phase 4): record grades, compute SubjectResult."""

    def __init__(self, gradebook):
        self.gradebook = gradebook

    def record(self, subject_id: str, grade) -> None:
        from academic_core.domain import results as _R
        if not isinstance(grade, _R.Grade):
            raise ApplicationError("expected results.Grade")
        self.gradebook.record(subject_id, grade)

    def result(self, subject_id: str, planned_required_weight=None,
               pass_ratio=None) -> object:
        from academic_core.domain import results as _R
        from decimal import Decimal
        grades = self.gradebook.grades_of(subject_id)
        kw = {}
        if planned_required_weight is not None:
            kw["planned_required_weight"] = Decimal(planned_required_weight)
        if pass_ratio is not None:
            kw["pass_ratio"] = Decimal(pass_ratio)
        return _R.compute(grades, **kw)
