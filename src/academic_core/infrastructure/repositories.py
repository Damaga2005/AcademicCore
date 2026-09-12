"""Repositories: explicit row <-> domain mapping. No ORM, no Qt."""

from __future__ import annotations

import json
from datetime import date, datetime

from academic_core.domain import entities as E
from academic_core.domain.identity import IdAllocator
from academic_core.infrastructure.database import Database


def _j(v) -> str:
    return json.dumps(v, ensure_ascii=False)


def _u(v, default):
    return json.loads(v) if v else default


class AcademicRepository:
    """Hierarchy + people + topics + stable-id counters."""

    def __init__(self, db: Database):
        self.db = db

    # -- universities / degrees / years / terms / subjects -----------------
    def add_university(self, u: E.University) -> None:
        cx = self.db.connect()
        cx.execute("INSERT OR REPLACE INTO universities VALUES (?,?)", (u.stable_id, u.name))
        cx.commit(); cx.close()

    def list_universities(self) -> list[E.University]:
        cx = self.db.connect()
        rows = cx.execute("SELECT * FROM universities ORDER BY name").fetchall(); cx.close()
        return [E.University(r["stable_id"], r["name"]) for r in rows]

    def add_degree(self, d: E.Degree) -> None:
        cx = self.db.connect()
        cx.execute("INSERT OR REPLACE INTO degrees VALUES (?,?,?)",
                   (d.stable_id, d.name, d.university_id))
        cx.commit(); cx.close()

    def degrees_of(self, university_id: str) -> list[E.Degree]:
        cx = self.db.connect()
        rows = cx.execute("SELECT * FROM degrees WHERE university_id=? ORDER BY name",
                          (university_id,)).fetchall(); cx.close()
        return [E.Degree(r["stable_id"], r["name"], r["university_id"]) for r in rows]

    def add_year(self, y: E.AcademicYear) -> None:
        cx = self.db.connect()
        cx.execute("INSERT OR REPLACE INTO academic_years VALUES (?,?,?)",
                   (y.stable_id, y.label, y.degree_id))
        cx.commit(); cx.close()

    def years_of(self, degree_id: str) -> list[E.AcademicYear]:
        cx = self.db.connect()
        rows = cx.execute("SELECT * FROM academic_years WHERE degree_id=? ORDER BY label",
                          (degree_id,)).fetchall(); cx.close()
        return [E.AcademicYear(r["stable_id"], r["label"], r["degree_id"]) for r in rows]

    def add_term(self, t: E.Term) -> None:
        cx = self.db.connect()
        cx.execute("INSERT OR REPLACE INTO terms VALUES (?,?,?,?,?,?,?)",
                   (t.stable_id, t.label, t.kind, t.index, t.academic_year_id,
                    t.start.isoformat() if t.start else None,
                    t.end.isoformat() if t.end else None))
        cx.commit(); cx.close()

    def terms_of(self, year_id: str) -> list[E.Term]:
        cx = self.db.connect()
        rows = cx.execute("SELECT * FROM terms WHERE academic_year_id=? ORDER BY idx",
                          (year_id,)).fetchall(); cx.close()
        return [E.Term(r["stable_id"], r["label"], r["kind"], r["idx"], r["academic_year_id"],
                       date.fromisoformat(r["start"]) if r["start"] else None,
                       date.fromisoformat(r["end"]) if r["end"] else None) for r in rows]

    def add_subject(self, s: E.Subject) -> None:
        cx = self.db.connect()
        cx.execute("INSERT OR REPLACE INTO subjects VALUES (?,?,?,?,?,?,?,?,?,?)",
                   (s.stable_id, s.code, s.name, s.acronym, s.description,
                    s.credits, s.kind, s.course, s.term_id, s.state))
        cx.commit(); cx.close()

    def get_subject(self, stable_id: str) -> E.Subject | None:
        cx = self.db.connect()
        r = cx.execute("SELECT * FROM subjects WHERE stable_id=?", (stable_id,)).fetchone()
        cx.close()
        if not r:
            return None
        return E.Subject(r["stable_id"], r["code"], r["name"], r["acronym"], r["description"],
                         r["credits"], r["kind"], r["course"], r["term_id"], r["state"])

    def subjects_of_term(self, term_id: str) -> list[E.Subject]:
        cx = self.db.connect()
        rows = cx.execute("SELECT * FROM subjects WHERE term_id=? ORDER BY name",
                          (term_id,)).fetchall(); cx.close()
        return [self.get_subject(r["stable_id"]) for r in rows]

    def all_subjects(self) -> list[E.Subject]:
        cx = self.db.connect()
        rows = cx.execute("SELECT stable_id FROM subjects ORDER BY name").fetchall(); cx.close()
        return [self.get_subject(r["stable_id"]) for r in rows]

    # -- people -------------------------------------------------------------
    def add_professor(self, p: E.Professor) -> None:
        cx = self.db.connect()
        cx.execute("INSERT OR REPLACE INTO professors VALUES (?,?,?,?)",
                   (p.stable_id, p.name, p.email, p.office))
        cx.commit(); cx.close()

    def attach_staff(self, link: E.SubjectStaff) -> None:
        cx = self.db.connect()
        cx.execute("INSERT OR REPLACE INTO subject_staff VALUES (?,?,?,?)",
                   (link.subject_id, link.professor_id, link.role, link.groups))
        cx.commit(); cx.close()

    def staff_of(self, subject_id: str) -> list[tuple[E.Professor, E.SubjectStaff]]:
        cx = self.db.connect()
        rows = cx.execute(
            "SELECT p.*, s.role, s.groups FROM professors p JOIN subject_staff s "
            "ON s.professor_id=p.stable_id WHERE s.subject_id=?", (subject_id,)).fetchall()
        cx.close()
        return [(E.Professor(r["stable_id"], r["name"], r["email"], r["office"]),
                 E.SubjectStaff(subject_id, r["stable_id"], r["role"], r["groups"])) for r in rows]

    # -- topics --------------------------------------------------------------
    def add_topic(self, t: E.Topic) -> None:
        cx = self.db.connect()
        cx.execute("INSERT OR REPLACE INTO topics VALUES (?,?,?,?)",
                   (t.stable_id, t.subject_id, t.index, t.title))
        cx.commit(); cx.close()

    def topics_of(self, subject_id: str) -> list[E.Topic]:
        cx = self.db.connect()
        rows = cx.execute("SELECT * FROM topics WHERE subject_id=? ORDER BY idx",
                          (subject_id,)).fetchall(); cx.close()
        return [E.Topic(r["stable_id"], r["subject_id"], r["idx"], r["title"]) for r in rows]

    # -- id counters ----------------------------------------------------------
    def load_counters(self) -> dict[str, int]:
        cx = self.db.connect()
        rows = cx.execute("SELECT kind, last_n FROM id_counters").fetchall(); cx.close()
        return {r["kind"]: r["last_n"] for r in rows}

    def save_counters(self, counters: dict[str, int]) -> None:
        cx = self.db.connect()
        for k, n in counters.items():
            cx.execute("INSERT OR REPLACE INTO id_counters VALUES (?,?)", (k, n))
        cx.commit(); cx.close()

    def allocator(self) -> IdAllocator:
        return IdAllocator(self.load_counters())


class PlanningRepository:
    def __init__(self, db: Database):
        self.db = db

    # assignments ------------------------------------------------------------
    def add_assignment(self, a: E.Assignment) -> None:
        cx = self.db.connect()
        cx.execute("INSERT OR REPLACE INTO assignments VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   (a.stable_id, a.subject_id, a.title, a.requirements, _j(a.resources),
                    a.workspace, _j(a.files), a.report_ref, a.rubric, a.submission, a.status))
        cx.commit(); cx.close()

    def assignments_of(self, subject_id: str) -> list[E.Assignment]:
        cx = self.db.connect()
        rows = cx.execute("SELECT * FROM assignments WHERE subject_id=? ORDER BY title",
                          (subject_id,)).fetchall(); cx.close()
        return [E.Assignment(r["stable_id"], r["subject_id"], r["title"], r["requirements"],
                             _u(r["resources"], []), r["workspace"], _u(r["files"], []),
                             r["report_ref"], r["rubric"], r["submission"], r["status"]) for r in rows]

    def get_assignment(self, stable_id: str) -> E.Assignment | None:
        cx = self.db.connect()
        r = cx.execute("SELECT * FROM assignments WHERE stable_id=?", (stable_id,)).fetchone()
        cx.close()
        if not r:
            return None
        return E.Assignment(r["stable_id"], r["subject_id"], r["title"], r["requirements"],
                            _u(r["resources"], []), r["workspace"], _u(r["files"], []),
                            r["report_ref"], r["rubric"], r["submission"], r["status"])

    # exams / projects / labs --------------------------------------------------
    def add_exam(self, e: E.Exam) -> None:
        cx = self.db.connect()
        cx.execute("INSERT OR REPLACE INTO exams VALUES (?,?,?,?,?,?,?,?)",
                   (e.stable_id, e.subject_id, e.title, e.day.isoformat() if e.day else None,
                    e.duration_min, e.session, e.allowed_resources, e.result))
        cx.commit(); cx.close()

    def exams_of(self, subject_id: str) -> list[E.Exam]:
        cx = self.db.connect()
        rows = cx.execute("SELECT * FROM exams WHERE subject_id=? ORDER BY day",
                          (subject_id,)).fetchall(); cx.close()
        return [E.Exam(r["stable_id"], r["subject_id"], r["title"],
                       date.fromisoformat(r["day"]) if r["day"] else None,
                       r["duration_min"], r["session"], r["allowed_resources"], r["result"]) for r in rows]

    def add_project(self, p: E.Project) -> None:
        cx = self.db.connect()
        cx.execute("INSERT OR REPLACE INTO projects VALUES (?,?,?,?,?,?)",
                   (p.stable_id, p.subject_id, p.title, p.description,
                    _j(p.milestones), _j(p.links)))
        cx.commit(); cx.close()

    def projects_of(self, subject_id: str) -> list[E.Project]:
        cx = self.db.connect()
        rows = cx.execute("SELECT * FROM projects WHERE subject_id=?", (subject_id,)).fetchall()
        cx.close()
        return [E.Project(r["stable_id"], r["subject_id"], r["title"], r["description"],
                          _u(r["milestones"], []), _u(r["links"], [])) for r in rows]

    def add_lab(self, lab: E.Lab) -> None:
        cx = self.db.connect()
        cx.execute("INSERT OR REPLACE INTO labs VALUES (?,?,?,?)",
                   (lab.stable_id, lab.subject_id, lab.title, lab.description))
        cx.commit(); cx.close()

    # tasks / deadlines ---------------------------------------------------------
    def add_task(self, t: E.Task) -> None:
        cx = self.db.connect()
        cx.execute("INSERT OR REPLACE INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?)",
                   (t.stable_id, t.subject_id, t.title, t.kind, t.day.isoformat() if t.day else None,
                    t.start, t.end, t.priority, t.state, t.notes))
        cx.commit(); cx.close()

    def tasks_of(self, subject_id: str) -> list[E.Task]:
        cx = self.db.connect()
        rows = cx.execute("SELECT * FROM tasks WHERE subject_id=? ORDER BY day", (subject_id,)).fetchall()
        cx.close()
        return [E.Task(r["stable_id"], r["subject_id"], r["title"], r["kind"],
                       date.fromisoformat(r["day"]) if r["day"] else None,
                       r["start"], r["end"], r["priority"], r["state"], r["notes"]) for r in rows]

    def all_tasks(self) -> list[E.Task]:
        cx = self.db.connect()
        rows = cx.execute("SELECT * FROM tasks ORDER BY day").fetchall(); cx.close()
        return [E.Task(r["stable_id"], r["subject_id"], r["title"], r["kind"],
                       date.fromisoformat(r["day"]) if r["day"] else None,
                       r["start"], r["end"], r["priority"], r["state"], r["notes"]) for r in rows]

    def add_deadline(self, target_id: str, due: datetime, label: str = "") -> int:
        cx = self.db.connect()
        cur = cx.execute("INSERT INTO deadlines(target_id, due, label) VALUES (?,?,?)",
                         (target_id, due.isoformat(), label))
        cx.commit(); cx.close()
        return cur.lastrowid

    def deadlines_of(self, target_id: str) -> list[E.Deadline]:
        cx = self.db.connect()
        rows = cx.execute("SELECT * FROM deadlines WHERE target_id=? ORDER BY due",
                          (target_id,)).fetchall(); cx.close()
        return [E.Deadline(r["target_id"], datetime.fromisoformat(r["due"]), r["label"]) for r in rows]

    # schedule series -------------------------------------------------------------
    def add_series(self, subject_id: str, kind: str, weekday: int, start: str, end: str,
                   first_day: date, last_day: date, interval_weeks: int = 1, room: str = "") -> int:
        cx = self.db.connect()
        cur = cx.execute(
            "INSERT INTO schedule_series(subject_id, kind, weekday, start, end,"
            " first_day, last_day, interval_weeks, room) VALUES (?,?,?,?,?,?,?,?,?)",
            (subject_id, kind, weekday, start, end, first_day.isoformat(),
             last_day.isoformat(), interval_weeks, room))
        cx.commit(); cx.close()
        return cur.lastrowid

    def series_of(self, subject_id: str) -> list[dict]:
        cx = self.db.connect()
        rows = cx.execute("SELECT * FROM schedule_series WHERE subject_id=? ORDER BY weekday, start",
                          (subject_id,)).fetchall(); cx.close()
        return [dict(r) for r in rows]

    def all_series(self) -> list[dict]:
        cx = self.db.connect()
        rows = cx.execute("SELECT * FROM schedule_series ORDER BY weekday, start").fetchall()
        cx.close()
        return [dict(r) for r in rows]

    # resource refs -----------------------------------------------------------------
    def add_ref(self, ref: E.ResourceReference) -> None:
        cx = self.db.connect()
        cx.execute("INSERT OR REPLACE INTO resource_refs VALUES (?,?,?,?,?)",
                   (ref.resource_id, ref.subject_id, ref.relationship, ref.title, ref.url))
        cx.commit(); cx.close()

    def refs_of(self, subject_id: str) -> list[E.ResourceReference]:
        cx = self.db.connect()
        rows = cx.execute("SELECT * FROM resource_refs WHERE subject_id=?", (subject_id,)).fetchall()
        cx.close()
        return [E.ResourceReference(r["resource_id"], r["subject_id"], r["relationship"],
                                    r["title"], r["url"]) for r in rows]


class GradingRepository:
    def __init__(self, db: Database):
        self.db = db

    def save_scheme(self, subject_id: str, scheme: str,
                    components: list[E.GradeComponent], final: str | None = None,
                    blocks: dict[str, str] | None = None) -> None:
        """blocks: {component_name: block_name} membership for block aggregation."""
        cx = self.db.connect()
        cx.execute("INSERT OR REPLACE INTO grade_schemes VALUES (?,?,?)", (subject_id, scheme, final))
        cx.execute("DELETE FROM grade_components WHERE subject_id=? AND scheme=?", (subject_id, scheme))
        for c in components:
            cx.execute(
                "INSERT INTO grade_components(subject_id, scheme, name, kind, weight, score, block)"
                " VALUES (?,?,?,?,?,?,?)",
                (subject_id, scheme, c.name, c.kind, c.weight, c.score,
                 (blocks or {}).get(c.name)))
        cx.commit(); cx.close()

    def load_schemes(self, subject_id: str) -> dict[str, tuple[list[E.GradeComponent], str | None, dict]]:
        cx = self.db.connect()
        schemes = cx.execute("SELECT scheme, final FROM grade_schemes WHERE subject_id=?",
                             (subject_id,)).fetchall()
        out = {}
        for s in schemes:
            rows = cx.execute(
                "SELECT name, kind, weight, score, block FROM grade_components"
                " WHERE subject_id=? AND scheme=? ORDER BY id", (subject_id, s["scheme"])).fetchall()
            comps = [E.GradeComponent(r["name"], r["kind"], r["weight"], r["score"]) for r in rows]
            blocks = {r["name"]: r["block"] for r in rows if r["block"]}
            out[s["scheme"]] = (comps, s["final"], blocks)
        cx.close()
        return out


class StudyRepository:
    def __init__(self, db: Database):
        self.db = db

    def add_tag(self, t: E.Tag) -> None:
        cx = self.db.connect()
        cx.execute("INSERT OR REPLACE INTO tags VALUES (?,?)", (t.stable_id, t.label))
        cx.commit(); cx.close()

    def add_bookmark(self, b: E.Bookmark) -> int:
        cx = self.db.connect()
        cur = cx.execute("INSERT INTO bookmarks(target_id, title, locator) VALUES (?,?,?)",
                         (b.target_id, b.title, b.locator))
        cx.commit(); cx.close()
        return cur.lastrowid

    def add_annotation(self, a: E.Annotation) -> int:
        cx = self.db.connect()
        cur = cx.execute(
            "INSERT INTO annotations(target_id, body, color, locator, created) VALUES (?,?,?,?,?)",
            (a.target_id, a.body, a.color, a.locator,
             a.created.isoformat() if a.created else None))
        cx.commit(); cx.close()
        return cur.lastrowid

    def annotations_of(self, target_id: str) -> list[E.Annotation]:
        cx = self.db.connect()
        rows = cx.execute("SELECT * FROM annotations WHERE target_id=? ORDER BY id",
                          (target_id,)).fetchall(); cx.close()
        return [E.Annotation(r["target_id"], r["body"], r["color"], r["locator"],
                             datetime.fromisoformat(r["created"]) if r["created"] else None) for r in rows]

    def ensure_study_space(self, space: E.StudySpace) -> int:
        """Spaces are referenced, never copied: one row per (subject, exam task)."""
        cx = self.db.connect()
        row = cx.execute("SELECT id FROM study_spaces WHERE subject_id=? AND exam_task_id=?",
                         (space.subject_id, space.exam_task_id)).fetchone()
        if row:
            cx.close()
            return row["id"]
        cur = cx.execute(
            "INSERT INTO study_spaces(subject_id, exam_task_id, title, refs) VALUES (?,?,?,?)",
            (space.subject_id, space.exam_task_id, space.title, _j(space.refs)))
        cx.commit(); cx.close()
        return cur.lastrowid

    def add_session(self, s: E.StudySession) -> int:
        cx = self.db.connect()
        cur = cx.execute("INSERT INTO study_sessions(subject_id, day, minutes, notes) VALUES (?,?,?,?)",
                         (s.subject_id, s.day.isoformat(), s.minutes, s.notes))
        cx.commit(); cx.close()
        return cur.lastrowid

    def streak(self, today: date) -> int:
        """Consecutive active days ending today (any session or completed task
        counts — caller records sessions; pure count over stored days)."""
        cx = self.db.connect()
        days = {r[0] for r in cx.execute("SELECT DISTINCT day FROM study_sessions")}
        cx.close()
        n, d = 0, today
        while d.isoformat() in days:
            n += 1
            d = date.fromordinal(d.toordinal() - 1)
        return n

    def notify(self, n: E.Notification) -> int:
        cx = self.db.connect()
        cur = cx.execute("INSERT INTO notifications(title, body, due, read) VALUES (?,?,?,?)",
                         (n.title, n.body, n.due.isoformat() if n.due else None, int(n.read)))
        cx.commit(); cx.close()
        return cur.lastrowid

    def pending_notifications(self) -> list[E.Notification]:
        cx = self.db.connect()
        rows = cx.execute("SELECT * FROM notifications WHERE read=0 ORDER BY id").fetchall()
        cx.close()
        return [E.Notification(r["title"], r["body"],
                               datetime.fromisoformat(r["due"]) if r["due"] else None,
                               bool(r["read"])) for r in rows]
