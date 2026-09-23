# SPDX-License-Identifier: MIT
"""F4.1 calendar / schedule use cases: tasks, class series, conflicts, ICS.

Calendar is cross-cutting: a task may belong to a subject or to none.
Exam-kind tasks auto-create their study space (Gestion parity, idempotent).
Conflicts warn, never block (domain/conflicts.py). ICS import is two-step
(preview -> apply of the rows the user kept), mirroring Gestion.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher

from academic_core.application.ids import allocate
from academic_core.domain import schedule as S
from academic_core.domain.conflicts import Conflict, TimedItem, detect
from academic_core.domain.entities import EXAM_TASK_TYPES, DomainError, StudySpace, Task
from academic_core.errors import AcademicManagementError
from academic_core.infrastructure.ics import ExportSeries, ExportTask, export_calendar, parse_calendar

SUBJECT_MATCH_THRESHOLD = 0.6


def _err(msg: str, code: str = "AC-ACD-001") -> AcademicManagementError:
    return AcademicManagementError(msg, code=code)


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFD", text or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9 ]", "", t).strip()


@dataclass(frozen=True)
class TaskResult:
    task: Task
    conflicts: tuple[Conflict, ...]
    study_space_id: str | None


@dataclass(frozen=True)
class IcsProposal:
    title: str
    day: date
    end: str | None
    kind: str
    course: str
    subject_id: str  # "" when no confident guess
    confidence: float
    needs_review: bool
    duplicate: bool


class CalendarService:
    def __init__(self, academic, planning, series, spaces):
        self.academic = academic
        self.planning = planning
        self.series = series
        self.spaces = spaces

    # -- tasks ---------------------------------------------------------------
    def create_task(self, title: str, day: date, *, subject_id: str = "",
                    kind: str = "tarea_general", start: str = "", end: str = "",
                    priority: str = "media", **extra) -> TaskResult:
        if subject_id and self.academic.get_subject(subject_id) is None:
            raise _err(f"unknown subject: {subject_id}", "AC-ACD-002")
        try:
            t = Task(allocate(self.academic, "task", subject_id), subject_id, title.strip(),
                     kind, day, start, end, priority, **extra)
        except (DomainError, TypeError) as e:
            raise _err(str(e), "AC-ACD-004") from e
        conflicts = tuple(self.conflicts(day, start, end, exclude=t.stable_id)) if start else ()
        self.planning.add_task(t)
        space = None
        if t.kind in EXAM_TASK_TYPES:
            space = self.ensure_space(t)
        return TaskResult(t, conflicts, space)

    def ensure_space(self, t: Task) -> str:
        existing = self.spaces.of_task(t.stable_id)
        if existing:
            return existing
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        return self.spaces.create(allocate(self.academic, "space", t.subject_id),
                                  StudySpace(t.subject_id, t.stable_id, t.title), now)

    def complete(self, task_id: str, done: bool = True) -> Task:
        t = self._task(task_id)
        t = replace(t, state="hecha" if done else "pendiente")
        self.planning.add_task(t)
        return t

    def postpone(self, task_id: str, days: int) -> Task:
        t = self._task(task_id)
        if t.day is None:
            raise _err("task has no date", "AC-ACD-004")
        t = replace(t, day=t.day + timedelta(days=days))
        self.planning.add_task(t)
        return t

    def _task(self, task_id: str) -> Task:
        t = self.planning.get_task(task_id)
        if t is None:
            raise _err(f"unknown task: {task_id}", "AC-ACD-002")
        return t

    # -- class series ------------------------------------------------------------
    def add_series(self, subject_id: str, kind: str, weekday: int, start: str, end: str,
                   first_day: date, last_day: date, interval_weeks: int = 1,
                   room: str = "", notes: str = "") -> tuple[str, list[date]]:
        if self.academic.get_subject(subject_id) is None:
            raise _err(f"unknown subject: {subject_id}", "AC-ACD-002")
        try:
            ser = S.Series(subject_id, kind, weekday, start, end, first_day, last_day,
                           interval_weeks, room)
        except ValueError as e:
            raise _err(str(e), "AC-ACD-004") from e
        sid = allocate(self.academic, "series", subject_id)
        self.series.add(sid, subject_id, kind, weekday, start, end, first_day, last_day,
                        interval_weeks, room, notes)
        return sid, S.expand_sessions(ser)

    def _series(self) -> list[tuple[dict, S.Series]]:
        out = []
        for r in self.series.all():
            out.append((r, S.Series(r["subject_id"], r["kind"], r["weekday"], r["start"],
                                    r["end"], date.fromisoformat(r["first_day"]),
                                    date.fromisoformat(r["last_day"]), r["interval_weeks"],
                                    r["room"])))
        return out

    def conflicts(self, day: date, start: str, end: str, exclude: str = "") -> list[Conflict]:
        if not (start and end):
            return []
        tasks = [TimedItem("task", t.stable_id, t.title, t.day.isoformat(), t.start, t.end)
                 for t in self.planning.all_tasks()
                 if t.day and t.start and t.end and t.stable_id != exclude]
        series = [(TimedItem("series", r["stable_id"] or str(r["id"]), r["kind"], "",
                             r["start"], r["end"]), s) for r, s in self._series()]
        return detect(day.isoformat(), start, end, tasks, series)

    # -- ICS -------------------------------------------------------------------
    def export_ics(self, dtstamp: str | None = None) -> str:
        dtstamp = dtstamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        subjects = {s.stable_id: s for s in self.academic.all_subjects()}

        def prefix(sid: str) -> str:
            s = subjects.get(sid)
            return (s.acronym or s.name) if s else ""

        tasks = [ExportTask(t.stable_id, t.title, t.day, t.start if t.end else "", t.end,
                            " · ".join(p for p in (t.room, t.location) if p), t.description,
                            prefix(t.subject_id))
                 for t in self.planning.all_tasks() if t.day is not None]
        series = []
        for r, s in self._series():
            sessions = S.expand_sessions(s)
            series.append(ExportSeries(r["stable_id"] or f"series-{r['id']}", r["kind"],
                                       s.weekday, s.start, s.end,
                                       sessions[0] if sessions else None, s.last_day,
                                       s.interval_weeks, s.room, prefix(s.subject_id)))
        return export_calendar(tasks, series, dtstamp=dtstamp)

    def _guess_subject(self, course: str, subjects) -> tuple[str, float]:
        clean = _norm(re.sub(r"\(.*?\)|^\s*\d{4,}\s*-?", "", course))
        best, ratio = "", 0.0
        for s in subjects:
            r = SequenceMatcher(None, clean, _norm(s.name)).ratio()
            if r > ratio or (r == ratio and s.stable_id < best):
                best, ratio = s.stable_id, r
        return (best, round(ratio, 4)) if ratio >= SUBJECT_MATCH_THRESHOLD else ("", round(ratio, 4))

    @staticmethod
    def _kind(url: str, title: str, description: str) -> str:
        if "/mod/quiz/" in url:
            return "tarea_general"
        if "/mod/assign/" in url:
            return "entrega"
        text = _norm(f"{title} {description}")
        return "entrega" if re.search(r"entrega|lliurament|tasca|assign", text) else "tarea_general"

    def _exists(self, title: str, day: date) -> bool:
        low = title.strip().lower()
        return any(t.title.strip().lower() == low and t.day == day
                   for t in self.planning.all_tasks())

    def ics_preview(self, raw: bytes) -> list[IcsProposal]:
        subjects = [s for s in self.academic.all_subjects() if s.state != "no_elegida"]
        out = []
        for ev in parse_calendar(raw):
            sid, conf = self._guess_subject(ev.course, subjects) if ev.course else ("", 0.0)
            out.append(IcsProposal(ev.summary, ev.day, ev.time,
                                   self._kind(ev.url, ev.summary, ev.description), ev.course,
                                   sid, conf, not sid, self._exists(ev.summary, ev.day)))
        return out

    def ics_apply(self, proposals: list[IcsProposal]) -> dict[str, int]:
        created = skipped = 0
        for p in proposals:
            if self._exists(p.title, p.day):
                skipped += 1
                continue
            self.create_task(p.title, p.day, subject_id=p.subject_id, kind=p.kind,
                             end=p.end or "")
            created += 1
        return {"created": created, "skipped": skipped}
