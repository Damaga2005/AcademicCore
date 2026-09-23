# SPDX-License-Identifier: MIT
"""F4.1 academic management use cases (application layer).

The subject is the central entity. These services compose the pure domain
rules (career / evaluation / course_material / planning) with repositories
and return plain frozen DTOs that the F15 UI can render without touching
SQLite, CAS or FTS.

    Home     -> CareerService.home(today)          (present only)
    Carrera  -> CareerService.career()             (all subjects, classified)
    Subject  -> CareerService.course(subject_id)   (every relation of ONE entity)

No Qt. No SQL here. Errors are D2 (`AcademicManagementError`, AC-ACD-*).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from academic_core.application.ids import allocate
from academic_core.domain import career as CR
from academic_core.domain import course_material as CM
from academic_core.domain import evaluation as EV
from academic_core.domain import planning as PL
from academic_core.domain import schedule as S
from academic_core.domain.entities import DomainError, Professor, Subject, SubjectStaff, Task
from academic_core.errors import AcademicManagementError

SETTING_DEGREE_TOTAL = "degree.total_credits"
SETTING_FINAL_PROJECT_NAMES = "degree.final_project_names"
SETTING_TARGET_AVERAGE = "grades.target_average"


def _err(msg: str, code: str = "AC-ACD-001") -> AcademicManagementError:
    return AcademicManagementError(msg, code=code)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


_FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value) -> str:
    """Neutralise CSV/spreadsheet formula injection (OWASP): text cells that
    start with = + - @ TAB CR get a leading apostrophe. Plain numbers
    (including negatives) are emitted as numbers."""
    if isinstance(value, (int, Decimal)) or (isinstance(value, float)):
        return str(value)
    text = str(value)
    return "'" + text if text.startswith(_FORMULA_LEAD) else text


# =================================================================== evaluation

class EvaluationService:
    def __init__(self, academic, evaluations):
        self.academic = academic
        self.repo = evaluations

    def _subject(self, subject_id: str) -> Subject:
        s = self.academic.get_subject(subject_id)
        if s is None:
            raise _err(f"unknown subject: {subject_id}", "AC-ACD-002")
        return s

    def create_scheme(self, subject_id: str, name: str, *, order: int = 0,
                      components: list[dict] = (), blocks: list[dict] = ()) -> EV.AssessmentScheme:
        """components: [{name, weight, kind?, score?, min_grade?}],
        blocks: [{name, weight, components: [...]}]. Weights/scores as text."""
        self._subject(subject_id)
        try:
            scheme = EV.AssessmentScheme(allocate(self.academic, "scheme", subject_id),
                                         subject_id, name, order=order)
            for i, c in enumerate(components):
                scheme.components.append(self._component(subject_id, c, i))
            for j, b in enumerate(blocks):
                block = EV.AssessmentBlock(allocate(self.academic, "block", subject_id),
                                           b["name"], b["weight"], order=b.get("order", j))
                for i, c in enumerate(b.get("components", ())):
                    block.components.append(self._component(subject_id, c, i))
                scheme.blocks.append(block)
        except DomainError as e:
            raise _err(str(e), "AC-ACD-004") from e
        self.repo.save_scheme(scheme)
        return scheme

    def _component(self, subject_id: str, c: dict, i: int) -> EV.AssessmentComponent:
        return EV.AssessmentComponent(allocate(self.academic, "component", subject_id),
                                      c["name"], c["weight"], c.get("kind", "otro"),
                                      c.get("score"), c.get("min_grade"), c.get("order", i))

    def schemes(self, subject_id: str) -> list[EV.AssessmentScheme]:
        return self.repo.schemes_of(subject_id)

    def set_score(self, component_id: str, score: str | None) -> None:
        try:
            value = EV.to_decimal(score, "score", low=0, high=10, optional=True)
        except DomainError as e:
            raise _err(str(e), "AC-ACD-004") from e
        self.repo.set_score(component_id, value)

    def evaluate(self, subject_id: str) -> EV.SubjectEvaluation:
        s = self._subject(subject_id)
        return EV.evaluate_subject(self.repo.schemes_of(subject_id), s.final_grade,
                                   s.scheme_rule)

    def required_score(self, scheme_id: str, subject_id: str,
                       target: str = "5") -> Decimal | None:
        for sc in self.repo.schemes_of(subject_id):
            if sc.stable_id == scheme_id:
                return EV.required_score(sc, Decimal(target))
        raise _err(f"unknown scheme: {scheme_id}", "AC-ACD-002")


# ====================================================================== career

@dataclass(frozen=True)
class SpaceSummary:
    space_id: str
    title: str
    subject_id: str
    task_id: str
    day: date | None
    progress: CM.SpaceProgress


@dataclass(frozen=True)
class AgendaItem:
    kind: str  # task | session
    ref: str
    title: str
    subject_id: str
    day: date
    start: str
    end: str
    task_kind: str = ""
    overdue: bool = False


@dataclass(frozen=True)
class HomeView:
    today: date
    current_term_ids: tuple[str, ...]
    current_subjects: tuple[Subject, ...]
    study_spaces: tuple[SpaceSummary, ...]
    upcoming: tuple[AgendaItem, ...]
    week: tuple[AgendaItem, ...]
    continue_reading: tuple[CM.ReadingProgress, ...]
    due_concepts: int
    milestones: tuple[PL.Milestone, ...]
    progress: CR.DegreeProgress | None
    averages: CR.AverageSummary


@dataclass(frozen=True)
class CareerView:
    partition: CR.CareerPartition
    study_spaces: tuple[SpaceSummary, ...]  # of the current-term subjects
    progress: CR.DegreeProgress | None
    averages: CR.AverageSummary
    target: CR.TargetAverage
    per_term: tuple[tuple[str, Decimal | None, int, int], ...]  # term, mean, graded, total


@dataclass(frozen=True)
class CourseDetail:
    subject: Subject
    status: CR.AcademicStatus
    term_id: str
    professors: tuple[tuple[Professor, SubjectStaff], ...]
    prerequisites: tuple[str, ...]
    prerequisites_met: bool
    evaluation: EV.SubjectEvaluation
    schemes: tuple[EV.AssessmentScheme, ...]
    documents: tuple[CM.CourseDocument, ...]
    groups: tuple[CM.DocumentGroup, ...]
    external_resources: tuple[CM.ExternalResource, ...]
    series: tuple[dict, ...]
    tasks: tuple[Task, ...]
    milestones: tuple[PL.Milestone, ...]
    study_spaces: tuple[SpaceSummary, ...]
    concepts: tuple[PL.StudyConcept, ...]
    # Engineering / labs relations (F8/F15 own their content; ids only here)
    labs: tuple[str, ...] = ()
    assignments: tuple[str, ...] = ()
    exams: tuple[str, ...] = ()
    projects: tuple[str, ...] = ()
    documents_by_category: dict = field(default_factory=dict)


class CareerService:
    def __init__(self, academic, planning, evaluation: EvaluationService, material,
                 spaces, series, personal):
        self.academic = academic
        self.planning = planning
        self.evaluation = evaluation
        self.material = material
        self.spaces = spaces
        self.series = series
        self.personal = personal

    # -- status ------------------------------------------------------------
    def change_status(self, subject_id: str, target: str) -> CR.StatusChange:
        s = self.academic.get_subject(subject_id)
        if s is None:
            raise _err(f"unknown subject: {subject_id}", "AC-ACD-002")
        try:
            s, change = CR.change_state(s, target)
        except DomainError as e:
            raise _err(str(e), "AC-ACD-004") from e
        if change.changed:
            self.academic.add_subject(s)  # same stable_id: update in place
        return change

    def set_term_state(self, term_id: str, state: str) -> None:
        for t in self.academic.all_terms():
            if t.stable_id == term_id:
                t.state = state
                try:
                    t.__post_init__()
                except DomainError as e:
                    raise _err(str(e), "AC-ACD-004") from e
                self.academic.add_term(t)
                return
        raise _err(f"unknown term: {term_id}", "AC-ACD-002")

    # -- building blocks -------------------------------------------------------
    def _graded(self, subjects: list[Subject]) -> list[CR.GradedCredit]:
        out = []
        for s in subjects:
            if s.state == "no_elegida":
                continue
            ev = self.evaluation.evaluate(s.stable_id)
            out.append(CR.GradedCredit(s.stable_id, Decimal(str(s.credits)), ev.grade, ev.state))
        return out

    def _progress(self, subjects: list[Subject]) -> CR.DegreeProgress | None:
        total = self.personal.setting(SETTING_DEGREE_TOTAL)
        if not total:
            return None
        names = tuple(n for n in (self.personal.setting(SETTING_FINAL_PROJECT_NAMES) or ""
                                  ).split("|") if n)
        return CR.degree_progress(subjects, Decimal(total), names)

    def _space_summaries(self, space_ids: list[str]) -> tuple[SpaceSummary, ...]:
        out = []
        for sid in space_ids:
            got = self.spaces.get(sid)
            if not got:
                continue
            sp, _ = got
            task = self.planning.get_task(sp.exam_task_id)
            out.append(SpaceSummary(sid, sp.title, sp.subject_id, sp.exam_task_id,
                                    task.day if task else None,
                                    CM.space_progress(self.spaces.documents(sid),
                                                      self.spaces.goals(sid))))
        return tuple(sorted(out, key=lambda x: (x.day or date.max, x.space_id)))

    def agenda(self, start: date, end: date, subject_ids: set[str] | None = None,
               include_done: bool = False) -> list[AgendaItem]:
        """Tasks + expanded class sessions within [start, end]."""
        items: list[AgendaItem] = []
        for t in self.planning.all_tasks():
            if t.day is None or not (start <= t.day <= end):
                continue
            if subject_ids is not None and t.subject_id not in subject_ids:
                continue
            if t.state != "pendiente" and not include_done:
                continue
            items.append(AgendaItem("task", t.stable_id, t.title, t.subject_id, t.day,
                                    t.start, t.end, t.kind))
        for r in self.series.all():
            if subject_ids is not None and r["subject_id"] not in subject_ids:
                continue
            ser = S.Series(r["subject_id"], r["kind"], r["weekday"], r["start"], r["end"],
                           date.fromisoformat(r["first_day"]), date.fromisoformat(r["last_day"]),
                           r["interval_weeks"], r["room"])
            for d in S.expand_sessions(ser):
                if start <= d <= end:
                    items.append(AgendaItem("session", r["stable_id"] or str(r["id"]),
                                            r["kind"], r["subject_id"], d, r["start"], r["end"]))
        return sorted(items, key=lambda i: (i.day, i.start or "99:99", i.kind, i.ref))

    # -- views ----------------------------------------------------------------
    def home(self, today: date, horizon_days: int = 14) -> HomeView:
        subjects = self.academic.all_subjects()
        part = CR.partition(subjects, self.academic.all_terms())
        cur_ids = [s.stable_id for s in part.current]
        overdue = [AgendaItem("task", t.stable_id, t.title, t.subject_id, t.day, t.start,
                              t.end, t.kind, True)
                   for t in self.planning.all_tasks()
                   if t.day is not None and t.day < today and t.state == "pendiente"]
        upcoming = overdue + [i for i in self.agenda(today, today + timedelta(days=horizon_days))
                              if i.kind == "task"]
        monday = today - timedelta(days=today.weekday())
        return HomeView(
            today, part.current_term_ids, part.current,
            self._space_summaries(self.spaces.ids_of_subjects(cur_ids)),
            tuple(upcoming), tuple(self.agenda(monday, monday + timedelta(days=6))),
            tuple(p for p in self.material.recent(5) if p is not None),
            len(PL.due_concepts(self.personal.concepts(), today)),
            tuple(self.personal.milestones()), self._progress(subjects),
            CR.summarize(self._graded(subjects)))

    def career(self) -> CareerView:
        subjects = self.academic.all_subjects()
        terms = self.academic.all_terms()
        part = CR.partition(subjects, terms)
        graded = self._graded(subjects)
        target = self.personal.setting(SETTING_TARGET_AVERAGE)
        by_id = {g.subject_id: g for g in graded}
        per_term = []
        for t in sorted(terms, key=lambda t: (t.academic_year_id, t.index, t.stable_id)):
            members = [by_id[s.stable_id] for s in subjects
                       if s.term_id == t.stable_id and s.stable_id in by_id]
            if not members:
                continue
            pairs = [(g.credits, g.grade) for g in members if g.grade is not None]
            per_term.append((t.stable_id, CR.weighted_mean(pairs), len(pairs), len(members)))
        return CareerView(part,
                          self._space_summaries(self.spaces.ids_of_subjects(
                              [s.stable_id for s in part.current])),
                          self._progress(subjects), CR.summarize(graded),
                          CR.target_average(graded, Decimal(target) if target else None),
                          tuple(per_term))

    def transcript_csv(self) -> str:
        """Academic record export (Gestion `exportar_expediente_csv` parity).
        Cells are neutralised against spreadsheet formula injection."""
        import csv
        import io
        terms = {t.stable_id: t for t in self.academic.all_terms()}
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\r\n")
        w.writerow(["curso", "periodo", "siglas", "asignatura", "ects", "tipo", "estado",
                    "estado_notas", "nota"])
        for s in sorted(self.academic.all_subjects(), key=lambda s: (s.course, s.term_id,
                                                                      s.name, s.stable_id)):
            ev = self.evaluation.evaluate(s.stable_id)
            t = terms.get(s.term_id)
            w.writerow([csv_safe(v) for v in (
                s.course, t.label if t else "", s.acronym, s.name, s.credits, s.kind, s.state,
                ev.state, "" if ev.grade is None else ev.grade)])
        return buf.getvalue()

    def course(self, subject_id: str) -> CourseDetail:
        s = self.academic.get_subject(subject_id)
        if s is None:
            raise _err(f"unknown subject: {subject_id}", "AC-ACD-002")
        prereqs = tuple(self.academic.prerequisites_of(subject_id))
        met = all((p := self.academic.get_subject(x)) is not None and p.state == "superada"
                  for x in prereqs)
        docs = tuple(self.material.documents_of(subject_id))
        by_cat: dict[str, list[CM.CourseDocument]] = {c: [] for c in CM.DOC_CATEGORIES}
        for d in docs:
            by_cat[d.category].append(d)
        series = tuple(r for r in self.series.all() if r["subject_id"] == subject_id)
        return CourseDetail(
            subject=s, status=CR.classify(s.state), term_id=s.term_id,
            professors=tuple(self.academic.staff_of(subject_id)),
            prerequisites=prereqs, prerequisites_met=met,
            evaluation=self.evaluation.evaluate(subject_id),
            schemes=tuple(self.evaluation.schemes(subject_id)),
            documents=docs, groups=tuple(self.material.groups_of(subject_id)),
            external_resources=tuple(self.material.externals_of(subject_id)),
            series=series, tasks=tuple(self.planning.tasks_of(subject_id)),
            milestones=tuple(self.personal.milestones(subject_id)),
            study_spaces=self._space_summaries(self.spaces.ids_of_subjects([subject_id])),
            concepts=tuple(self.personal.concepts(subject_id)),
            labs=tuple(x.stable_id for x in self.planning.labs_of(subject_id)),
            assignments=tuple(x.stable_id for x in self.planning.assignments_of(subject_id)),
            exams=tuple(x.stable_id for x in self.planning.exams_of(subject_id)),
            projects=tuple(x.stable_id for x in self.planning.projects_of(subject_id)),
            documents_by_category={k: tuple(v) for k, v in by_cat.items()},
        )


# ============================================================= course material

class CourseMaterialService:
    """Documents in subject context + external links + study selections."""

    def __init__(self, academic, material, spaces, planning, ingest=None):
        self.academic = academic
        self.material = material
        self.spaces = spaces
        self.planning = planning
        self.ingest = ingest

    def _need_subject(self, subject_id: str) -> None:
        if self.academic.get_subject(subject_id) is None:
            raise _err(f"unknown subject: {subject_id}", "AC-ACD-002")

    def create_group(self, subject_id: str, category: str, name: str,
                     order: int = 0) -> CM.DocumentGroup:
        self._need_subject(subject_id)
        try:
            g = CM.DocumentGroup(allocate(self.academic, "docgroup", subject_id), subject_id,
                                 category, name, order)
        except DomainError as e:
            raise _err(str(e), "AC-ACD-004") from e
        self.material.add_group(g)
        return g

    def add_document(self, subject_id: str, data: bytes, filename: str, *,
                     category: str = "otros", group_id: str = "",
                     tags: tuple[str, ...] = ()) -> CM.CourseDocument:
        """Ingest bytes through the F2 pipeline (CAS + provenance + FTS) and
        place the resource in the subject's documentation."""
        self._need_subject(subject_id)
        if self.ingest is None:
            raise _err("ingestion pipeline not wired")
        report = self.ingest.import_bytes(data, filename, subject_id=subject_id)
        return self.link(subject_id, report.stable_id, category=category,
                         group_id=group_id, filename=filename, tags=tags)

    def link(self, subject_id: str, resource_id: str, *, category: str = "otros",
             group_id: str = "", filename: str = "", tags: tuple[str, ...] = ()
             ) -> CM.CourseDocument:
        """Place an EXISTING resource in a subject (no copy, no new bytes)."""
        self._need_subject(subject_id)
        try:
            d = CM.CourseDocument(subject_id, resource_id, category, group_id, filename,
                                  tuple(tags), _now())
        except DomainError as e:
            raise _err(str(e), "AC-ACD-004") from e
        self.material.link(d)
        return d

    def move(self, resource_id: str, from_subject: str, to_subject: str, *,
             category: str | None = None, group_id: str = "") -> CM.CourseDocument:
        """Gestion `fix_ciaf` capability without filesystem moves: the
        resource identity and bytes never change, only the relation."""
        current = [d for d in self.material.documents_of(from_subject)
                   if d.resource_id == resource_id]
        if not current:
            raise _err(f"{resource_id} is not in {from_subject}", "AC-ACD-002")
        src = current[0]
        moved = self.link(to_subject, resource_id, category=category or src.category,
                          group_id=group_id, filename=src.filename, tags=src.tags)
        self.material.unlink(from_subject, resource_id)
        return moved

    def documents(self, subject_id: str, category: str = "") -> list[CM.CourseDocument]:
        return self.material.documents_of(subject_id, category)

    def record_reading(self, resource_id: str, *, page: int | None = None,
                       percent: str | None = None, seconds: int = 0,
                       when: str | None = None) -> CM.ReadingProgress:
        p = self.material.progress_of(resource_id) or CM.ReadingProgress(resource_id)
        when = when or _now()
        p = CM.ReadingProgress(resource_id, page if page is not None else p.last_page,
                               percent if percent is not None else p.percent, p.zoom,
                               p.view_mode, p.scroll, p.first_opened or when, when,
                               p.total_seconds + max(seconds, 0), p.sessions + 1)
        self.material.set_progress(p)
        return p

    def add_external_resource(self, subject_id: str, name: str, url: str,
                              kind: str = "", order: int = 0,
                              source: str = "manual") -> CM.ExternalResource:
        """URL is validated and stored; it is NEVER fetched (no SSRF surface)."""
        self._need_subject(subject_id)
        try:
            x = CM.ExternalResource(allocate(self.academic, "link", subject_id), subject_id,
                                    name, url, kind, order, {"origin": source})
        except DomainError as e:
            raise _err(str(e), "AC-ACD-004") from e
        self.material.add_external(x)
        return x

    # -- study spaces (selection of documents for study; deep logic F10) ----
    def ensure_space(self, task_id: str, title: str = "") -> str:
        t = self.planning.get_task(task_id)
        if t is None:
            raise _err(f"unknown task: {task_id}", "AC-ACD-002")
        from academic_core.domain.entities import StudySpace
        sid = self.spaces.of_task(task_id)
        if sid:
            return sid
        return self.spaces.create(allocate(self.academic, "space", t.subject_id),
                                  StudySpace(t.subject_id, task_id, title or t.title), _now())

    def select_for_space(self, space_id: str, resource_id: str, section: str = "teoria",
                         highlighted: bool = False, order: int = 0) -> CM.StudySpaceDocument:
        try:
            d = CM.StudySpaceDocument(space_id, resource_id, section, False, highlighted, order)
        except DomainError as e:
            raise _err(str(e), "AC-ACD-004") from e
        self.spaces.add_document(d)
        return d

    def mark_read(self, space_id: str, resource_id: str, read: bool = True) -> None:
        for d in self.spaces.documents(space_id):
            if d.resource_id == resource_id:
                d.read = read
                self.spaces.add_document(d)
                return
        raise _err(f"{resource_id} not selected in {space_id}", "AC-ACD-002")

    def space(self, space_id: str) -> dict:
        got = self.spaces.get(space_id)
        if not got:
            raise _err(f"unknown study space: {space_id}", "AC-ACD-002")
        sp, created = got
        docs = self.spaces.documents(space_id)
        goals = self.spaces.goals(space_id)
        return {"space_id": space_id, "title": sp.title, "subject_id": sp.subject_id,
                "task_id": sp.exam_task_id, "created": created, "documents": docs,
                "goals": goals, "highlighted": [d for d in docs if d.highlighted],
                "progress": CM.space_progress(docs, goals)}

    def set_goals(self, space_id: str, goals: list[tuple[str, bool]]) -> None:
        try:
            items = [CM.StudySpaceGoal(space_id, t, done, i) for i, (t, done) in enumerate(goals)]
        except DomainError as e:
            raise _err(str(e), "AC-ACD-004") from e
        self.spaces.set_goals(space_id, items)


# =============================================================== personal plan

class PlanningService:
    """Milestones, goals (target average), quick notes, settings."""

    def __init__(self, academic, personal):
        self.academic = academic
        self.personal = personal

    def add_milestone(self, name: str, day: date | None = None, subject_id: str = "",
                      order: int = 0) -> PL.Milestone:
        try:
            m = PL.Milestone(allocate(self.academic, "milestone"), name, "pendiente", day,
                             order, subject_id)
        except DomainError as e:
            raise _err(str(e), "AC-ACD-004") from e
        if subject_id and self.academic.get_subject(subject_id) is None:
            raise _err(f"unknown subject: {subject_id}", "AC-ACD-002")
        self.personal.add_milestone(m)
        return m

    def cycle_milestone(self, stable_id: str) -> PL.Milestone:
        for m in self.personal.milestones():
            if m.stable_id == stable_id:
                nxt = m.cycled()
                self.personal.add_milestone(nxt)
                return nxt
        raise _err(f"unknown milestone: {stable_id}", "AC-ACD-002")

    def add_note(self, text: str) -> PL.QuickNote:
        try:
            n = PL.QuickNote(allocate(self.academic, "note"), text, _now())
        except DomainError as e:
            raise _err(str(e), "AC-ACD-004") from e
        self.personal.add_note(n)
        return n

    def notes(self) -> list[PL.QuickNote]:
        return self.personal.notes()

    def set_target_average(self, value: str | None) -> None:
        if value is None or value == "":
            self.personal.set_setting(SETTING_TARGET_AVERAGE, "")
            return
        try:
            d = EV.to_decimal(value, "target_average", low=0, high=10)
        except DomainError as e:
            raise _err(str(e), "AC-ACD-004") from e
        self.personal.set_setting(SETTING_TARGET_AVERAGE, str(d))

    def set_degree_plan(self, total_credits: str,
                        final_project_names: tuple[str, ...] = ()) -> None:
        try:
            d = EV.to_decimal(total_credits, "total_credits", low=1, high=1000)
        except DomainError as e:
            raise _err(str(e), "AC-ACD-004") from e
        self.personal.set_setting(SETTING_DEGREE_TOTAL, str(d))
        if any("|" in n for n in final_project_names):
            raise _err("final project names cannot contain '|'", "AC-ACD-004")
        self.personal.set_setting(SETTING_FINAL_PROJECT_NAMES, "|".join(final_project_names))
