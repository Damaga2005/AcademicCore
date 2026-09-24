# SPDX-License-Identifier: MIT
"""F4.2 notification computation: pure, deterministic, never writes.

`NotificationService.compute()` derives advisories from tasks, study spaces
and subject activity. It never mutates tasks, exams, settings, payloads or
dismissals, and never calls `notify()`: computed views are transient, while
the `notifications` table stays for explicitly created user notices.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from academic_core.domain.entities import EXAM_TASK_TYPES
from academic_core.errors import AcademicManagementError

LEVEL_RANK = {"rojo": 0, "naranja": 1, "gris": 2}


@dataclass(frozen=True)
class NotificationView:
    kind: str  # tarea_atrasada | tarea_inminente | espacio_sin_empezar | asignatura_inactiva
    level: str  # rojo | naranja | gris
    title: str
    message: str
    url: str  # UI route placeholder (empty: AcademicCore has no routes)
    entity: str  # stable id of the subject/task/space it refers to
    due: date | None = None


class NotificationService:
    """Read-only computation over academic/planning/material/spaces repos."""

    def __init__(self, academic, planning, material, spaces):
        self.academic = academic
        self.planning = planning
        self.material = material
        self.spaces = spaces

    def compute(self, today: date, *, exam_reminder_days: int = 7,
                abandoned_subject_days: int = 14) -> list[NotificationView]:
        """Pure: same (data, today, config) -> same list, same order.

        Order: level rojo > naranja > gris, then due ASC (None last),
        then entity ASC.
        """
        out: list[NotificationView] = []
        out.extend(self._tasks(today, exam_reminder_days))
        out.extend(self._spaces(today))
        out.extend(self._inactive_subjects(today, abandoned_subject_days))
        out.sort(key=lambda v: (LEVEL_RANK[v.level], v.due or date.max, v.entity))
        return out

    # -- tasks -------------------------------------------------------------
    def _tasks(self, today: date, exam_reminder_days: int) -> list[NotificationView]:
        out = []
        for t in self.planning.all_tasks():
            if t.state != "pendiente" or t.day is None:
                continue
            days = (t.day - today).days
            label = t.kind.replace("_", " ")
            if days < 0:
                if t.kind in EXAM_TASK_TYPES:
                    # Occurred: Gestion auto-completed it (a write); F4.2
                    # reports nothing and mutates nothing (idempotence).
                    continue
                out.append(NotificationView(
                    "tarea_atrasada", "rojo", t.title,
                    f"{label.capitalize()} atrasada desde hace {-days} día(s)"
                    f" ({t.day.isoformat()})", "", t.stable_id, t.day))
                continue
            threshold = t.reminder_days if t.reminder_days is not None \
                else exam_reminder_days
            if days <= threshold:
                when = "hoy" if days == 0 else f"en {days} día(s)"
                out.append(NotificationView(
                    "tarea_inminente", "rojo" if days < 3 else "naranja", t.title,
                    f"{label.capitalize()} {when} ({t.day.isoformat()})",
                    "", t.stable_id, t.day))
        return out

    # -- study spaces --------------------------------------------------------
    def _spaces(self, today: date) -> list[NotificationView]:
        out = []
        for sid in self.spaces.all_ids():
            got = self.spaces.get(sid)
            if not got:
                continue
            sp, _created = got
            task = self.planning.get_task(sp.exam_task_id)
            if task is None or task.day is None:
                continue  # insufficient information: omit, never invent dates
            days = (task.day - today).days
            if days < 0 or days > 3:
                continue
            try:
                detail = self.material.space(sid)
            except AcademicManagementError:
                continue
            progress = detail.get("progress")
            total = progress.total if progress is not None else 0
            if not total or (progress.percent if progress else 0) != 0:
                continue
            when = "hoy" if days == 0 else f"en {days} día(s)"
            out.append(NotificationView(
                "espacio_sin_empezar", "rojo" if days < 2 else "naranja", sp.title,
                f"Examen {when} y todavía no has empezado a repasar (0% leído)",
                "", sid, task.day))
        return out

    # -- inactive subjects -----------------------------------------------------
    def last_subject_activity(self, subject_id: str) -> date | None:
        """Latest attributable activity date, or None when there is no base
        to measure from. Sources, all subject-bound: subject notes stamp,
        document `added_at`, reading `last_opened`. Global activity days are
        NOT converted into subject activity."""
        best: date | None = None

        def consider(value: str | None) -> None:
            nonlocal best
            if not value:
                return
            try:
                day = date.fromisoformat(str(value)[:10])
            except ValueError:
                return
            if best is None or day > best:
                best = day

        subj = self.academic.get_subject(subject_id)
        if subj is None:
            return None
        consider(subj.notes_updated_at)
        for d in self.material.documents(subject_id):
            consider(d.added_at)
            prog = self.material.progress_of(d.resource_id)
            if prog is not None:
                consider(prog.last_opened)
        return best

    def _inactive_subjects(self, today: date, abandoned_subject_days: int
                           ) -> list[NotificationView]:
        out = []
        for s in self.academic.all_subjects():
            if s.state != "cursando":
                continue
            last = self.last_subject_activity(s.stable_id)
            if last is None:
                continue
            days = (today - last).days
            if days > abandoned_subject_days:
                out.append(NotificationView(
                    "asignatura_inactiva", "gris", s.name,
                    f"Sin actividad registrada desde hace {days} días",
                    "", s.stable_id, None))
        return out
