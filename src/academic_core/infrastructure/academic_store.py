# SPDX-License-Identifier: MIT
"""F4.1 repositories: explicit row <-> domain mapping (no ORM, no Qt).

Every write method accepts an optional open connection ``cx`` so a use
case (e.g. the Gestion migration) can compose many writes into ONE
transaction; without ``cx`` each call is its own committed unit.
Reads are ordered deterministically (explicit ORDER BY on stable keys).
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date
from decimal import Decimal

from academic_core.domain import course_material as CM
from academic_core.domain import evaluation as EV
from academic_core.domain import planning as PL
from academic_core.domain.entities import StudySpace
from academic_core.infrastructure.database import Database
from academic_core.infrastructure.repositories import IntegrityError


def _j(v) -> str:
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


def _s(v: Decimal | None) -> str | None:
    return None if v is None else str(v)


class _Base:
    def __init__(self, db: Database):
        self.db = db

    @contextmanager
    def _tx(self, cx=None):
        if cx is not None:
            yield cx
            return
        own = self.db.connect()
        try:
            own.execute("BEGIN IMMEDIATE")
            yield own
            own.execute("COMMIT")
        except BaseException:
            own.execute("ROLLBACK")
            raise
        finally:
            own.close()

    @contextmanager
    def _read(self):
        cx = self.db.connect()
        try:
            yield cx
        finally:
            cx.close()

    @contextmanager
    def unit_of_work(self):
        """One transaction shared by several repository calls."""
        with self._tx() as cx:
            yield cx


# ------------------------------------------------------------------ evaluation

class EvaluationRepository(_Base):
    def save_scheme(self, scheme: EV.AssessmentScheme, cx=None) -> None:
        """Replace one scheme with its blocks and components atomically."""
        with self._tx(cx) as c:
            if not c.execute("SELECT 1 FROM subjects WHERE stable_id=?",
                             (scheme.subject_id,)).fetchone():
                raise IntegrityError(f"unknown subject: {scheme.subject_id}")
            c.execute("DELETE FROM assessment_components WHERE scheme_id=?", (scheme.stable_id,))
            c.execute("DELETE FROM assessment_blocks WHERE scheme_id=?", (scheme.stable_id,))
            c.execute("INSERT OR REPLACE INTO assessment_schemes(stable_id, subject_id, name, ord)"
                      " VALUES (?,?,?,?)", (scheme.stable_id, scheme.subject_id,
                                            scheme.name, scheme.order))
            for b in scheme.blocks:
                c.execute("INSERT INTO assessment_blocks(stable_id, scheme_id, name, weight, ord)"
                          " VALUES (?,?,?,?,?)", (b.stable_id, scheme.stable_id, b.name,
                                                  str(b.weight), b.order))
                for m in b.components:
                    self._component(c, scheme, m, b.stable_id)
            for m in scheme.components:
                self._component(c, scheme, m, "")

    @staticmethod
    def _component(c, scheme, m: EV.AssessmentComponent, block_id: str) -> None:
        c.execute("INSERT INTO assessment_components(stable_id, subject_id, scheme_id, block_id,"
                  " name, kind, weight, score, min_grade, ord) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (m.stable_id, scheme.subject_id, scheme.stable_id, block_id, m.name, m.kind,
                   str(m.weight), _s(m.score), _s(m.min_grade), m.order))

    def schemes_of(self, subject_id: str) -> list[EV.AssessmentScheme]:
        with self._read() as cx:
            srows = cx.execute("SELECT * FROM assessment_schemes WHERE subject_id=?"
                               " ORDER BY ord, stable_id", (subject_id,)).fetchall()
            out = []
            for s in srows:
                comps = cx.execute("SELECT * FROM assessment_components WHERE scheme_id=?"
                                   " ORDER BY ord, stable_id", (s["stable_id"],)).fetchall()
                blocks = cx.execute("SELECT * FROM assessment_blocks WHERE scheme_id=?"
                                    " ORDER BY ord, stable_id", (s["stable_id"],)).fetchall()
                by_block: dict[str, list] = {}
                for r in comps:
                    by_block.setdefault(r["block_id"], []).append(EV.AssessmentComponent(
                        r["stable_id"], r["name"], r["weight"], r["kind"], r["score"],
                        r["min_grade"], r["ord"]))
                out.append(EV.AssessmentScheme(
                    s["stable_id"], s["subject_id"], s["name"], by_block.pop("", []),
                    [EV.AssessmentBlock(b["stable_id"], b["name"], b["weight"],
                                        by_block.pop(b["stable_id"], []), b["ord"])
                     for b in blocks], s["ord"]))
                if by_block:  # component points at a block that does not exist
                    raise IntegrityError(f"orphan block reference in {s['stable_id']}")
            return out

    def set_score(self, component_id: str, score: Decimal | None) -> None:
        with self._tx() as c:
            cur = c.execute("UPDATE assessment_components SET score=? WHERE stable_id=?",
                            (_s(score), component_id))
            if cur.rowcount != 1:
                raise IntegrityError(f"unknown component: {component_id}")

    def delete_scheme(self, scheme_id: str) -> None:
        with self._tx() as c:
            c.execute("DELETE FROM assessment_components WHERE scheme_id=?", (scheme_id,))
            c.execute("DELETE FROM assessment_blocks WHERE scheme_id=?", (scheme_id,))
            c.execute("DELETE FROM assessment_schemes WHERE stable_id=?", (scheme_id,))


# ------------------------------------------------------------- course material

class CourseMaterialRepository(_Base):
    # groups ---------------------------------------------------------------
    def add_group(self, g: CM.DocumentGroup, cx=None) -> None:
        with self._tx(cx) as c:
            dup = c.execute("SELECT stable_id FROM document_groups WHERE subject_id=? AND"
                            " category=? AND name=? AND stable_id<>?",
                            (g.subject_id, g.category, g.name, g.stable_id)).fetchone()
            if dup:
                raise IntegrityError(f"duplicate group name in category: {g.name!r}")
            c.execute("INSERT OR REPLACE INTO document_groups(stable_id, subject_id, category,"
                      " name, ord) VALUES (?,?,?,?,?)",
                      (g.stable_id, g.subject_id, g.category, g.name, g.order))

    def groups_of(self, subject_id: str) -> list[CM.DocumentGroup]:
        with self._read() as cx:
            rows = cx.execute("SELECT * FROM document_groups WHERE subject_id=?"
                              " ORDER BY category, ord, name, stable_id", (subject_id,)).fetchall()
        return [CM.DocumentGroup(r["stable_id"], r["subject_id"], r["category"], r["name"],
                                 r["ord"]) for r in rows]

    def delete_group(self, group_id: str) -> None:
        with self._tx() as c:
            n = c.execute("SELECT COUNT(*) FROM course_documents WHERE group_id=?",
                          (group_id,)).fetchone()[0]
            if n:
                raise IntegrityError(f"group still holds {n} document(s)")
            c.execute("DELETE FROM document_groups WHERE stable_id=?", (group_id,))

    # documents ------------------------------------------------------------
    def link(self, d: CM.CourseDocument, cx=None) -> None:
        with self._tx(cx) as c:
            if not c.execute("SELECT 1 FROM resources WHERE stable_id=?",
                             (d.resource_id,)).fetchone():
                raise IntegrityError(f"unknown resource: {d.resource_id}")
            if d.group_id:
                g = c.execute("SELECT subject_id, category FROM document_groups WHERE"
                              " stable_id=?", (d.group_id,)).fetchone()
                if not g or g["subject_id"] != d.subject_id:
                    raise IntegrityError(f"group {d.group_id} not in {d.subject_id}")
            c.execute("INSERT OR REPLACE INTO course_documents(subject_id, resource_id, category,"
                      " group_id, filename, tags, added_at, legacy) VALUES (?,?,?,?,?,?,?,?)",
                      (d.subject_id, d.resource_id, d.category, d.group_id, d.filename,
                       _j(list(d.tags)), d.added_at, _j(d.legacy)))
            # keep the F2 academic link (subject -> resource) in sync
            c.execute("INSERT OR IGNORE INTO resource_refs(resource_id, subject_id,"
                      " relationship, title, url) VALUES (?,?,?,?,?)",
                      (d.resource_id, d.subject_id, "material", d.filename, ""))

    @staticmethod
    def _doc(r) -> CM.CourseDocument:
        return CM.CourseDocument(r["subject_id"], r["resource_id"], r["category"], r["group_id"],
                                 r["filename"], tuple(json.loads(r["tags"])), r["added_at"],
                                 json.loads(r["legacy"]))

    def documents_of(self, subject_id: str, category: str = "") -> list[CM.CourseDocument]:
        q = "SELECT * FROM course_documents WHERE subject_id=?"
        args: tuple = (subject_id,)
        if category:
            q += " AND category=?"
            args += (category,)
        with self._read() as cx:
            rows = cx.execute(q + " ORDER BY category, group_id, filename, resource_id",
                              args).fetchall()
        return [self._doc(r) for r in rows]

    def subjects_of_resource(self, resource_id: str) -> list[str]:
        with self._read() as cx:
            rows = cx.execute("SELECT subject_id FROM course_documents WHERE resource_id=?"
                              " ORDER BY subject_id", (resource_id,)).fetchall()
        return [r["subject_id"] for r in rows]

    def unlink(self, subject_id: str, resource_id: str) -> None:
        """Removes the relation only; the Resource/CAS bytes are untouched."""
        with self._tx() as c:
            c.execute("DELETE FROM course_documents WHERE subject_id=? AND resource_id=?",
                      (subject_id, resource_id))

    def set_progress(self, p: CM.ReadingProgress, cx=None) -> None:
        with self._tx(cx) as c:
            c.execute("INSERT OR REPLACE INTO reading_progress VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (p.resource_id, p.last_page, p.percent, p.zoom, p.view_mode, p.scroll,
                       p.first_opened, p.last_opened, p.total_seconds, p.sessions))

    def progress_of(self, resource_id: str) -> CM.ReadingProgress | None:
        with self._read() as cx:
            r = cx.execute("SELECT * FROM reading_progress WHERE resource_id=?",
                           (resource_id,)).fetchone()
        if not r:
            return None
        return CM.ReadingProgress(r["resource_id"], r["last_page"], r["percent"], r["zoom"],
                                  r["view_mode"], r["scroll"], r["first_opened"],
                                  r["last_opened"], r["total_seconds"], r["sessions"])

    def recent(self, limit: int = 10) -> list[CM.ReadingProgress]:
        with self._read() as cx:
            rows = cx.execute("SELECT resource_id FROM reading_progress WHERE last_opened<>''"
                              " ORDER BY last_opened DESC, resource_id LIMIT ?",
                              (limit,)).fetchall()
        return [self.progress_of(r["resource_id"]) for r in rows]

    # pages ------------------------------------------------------------------
    def set_pages(self, resource_id: str, pages: list[tuple[int, str]], cx=None) -> None:
        with self._tx(cx) as c:
            c.execute("DELETE FROM document_pages WHERE resource_id=?", (resource_id,))
            c.executemany("INSERT INTO document_pages(resource_id, page, text) VALUES (?,?,?)",
                          [(resource_id, n, t) for n, t in pages])

    def pages_of(self, resource_id: str) -> list[tuple[int, str]]:
        with self._read() as cx:
            rows = cx.execute("SELECT page, text FROM document_pages WHERE resource_id=?"
                              " ORDER BY page", (resource_id,)).fetchall()
        return [(r["page"], r["text"]) for r in rows]

    def search_context(self, resource_ids: list[str]) -> dict[str, tuple[list[str],
                                                                          list[tuple[int, str]]]]:
        """Batch lookup for search hits: resource -> (subjects, pages), one
        connection, two queries (avoids N+1 round trips)."""
        out: dict[str, tuple[list[str], list[tuple[int, str]]]] = {
            r: ([], []) for r in resource_ids}
        if not resource_ids:
            return out
        marks = ",".join("?" * len(resource_ids))
        with self._read() as cx:
            for r in cx.execute(f"SELECT resource_id, subject_id FROM course_documents WHERE"
                                f" resource_id IN ({marks}) ORDER BY resource_id, subject_id",
                                tuple(resource_ids)):
                out[r["resource_id"]][0].append(r["subject_id"])
            for r in cx.execute(f"SELECT resource_id, page, text FROM document_pages WHERE"
                                f" resource_id IN ({marks}) ORDER BY resource_id, page",
                                tuple(resource_ids)):
                out[r["resource_id"]][1].append((r["page"], r["text"]))
        return out

    # external resources -------------------------------------------------------
    def add_external(self, x: CM.ExternalResource, cx=None) -> None:
        with self._tx(cx) as c:
            c.execute("INSERT OR REPLACE INTO external_resources(stable_id, subject_id, name, url,"
                      " kind, provider, ord, provenance) VALUES (?,?,?,?,?,?,?,?)",
                      (x.stable_id, x.subject_id, x.name, x.url, x.kind, x.provider, x.order,
                       _j(x.provenance)))

    def externals_of(self, subject_id: str) -> list[CM.ExternalResource]:
        with self._read() as cx:
            rows = cx.execute("SELECT * FROM external_resources WHERE subject_id=?"
                              " ORDER BY ord, stable_id", (subject_id,)).fetchall()
        return [self._ext(r) for r in rows]

    def all_externals(self) -> list[CM.ExternalResource]:
        with self._read() as cx:
            rows = cx.execute("SELECT * FROM external_resources"
                              " ORDER BY subject_id, ord, stable_id").fetchall()
        return [self._ext(r) for r in rows]

    @staticmethod
    def _ext(r) -> CM.ExternalResource:
        return CM.ExternalResource(r["stable_id"], r["subject_id"], r["name"], r["url"],
                                   r["kind"], r["ord"], json.loads(r["provenance"]))

    def delete_external(self, stable_id: str) -> None:
        with self._tx() as c:
            c.execute("DELETE FROM external_resources WHERE stable_id=?", (stable_id,))


# ----------------------------------------------------------------- study spaces

class StudySpaceRepository(_Base):
    def create(self, stable_id: str, space: StudySpace, created: str = "", cx=None) -> str:
        """Idempotent per exam task (Gestion 1:1 tarea<->espacio)."""
        with self._tx(cx) as c:
            row = c.execute("SELECT stable_id FROM study_spaces WHERE exam_task_id=?"
                            " AND stable_id<>'' ORDER BY id LIMIT 1",
                            (space.exam_task_id,)).fetchone()
            if row:
                return row["stable_id"]
            c.execute("INSERT INTO study_spaces(subject_id, exam_task_id, title, refs, stable_id,"
                      " created) VALUES (?,?,?,?,?,?)",
                      (space.subject_id, space.exam_task_id, space.title, "[]", stable_id,
                       created))
            return stable_id

    def get(self, stable_id: str) -> tuple[StudySpace, str] | None:
        with self._read() as cx:
            r = cx.execute("SELECT * FROM study_spaces WHERE stable_id=?", (stable_id,)).fetchone()
        if not r:
            return None
        return StudySpace(r["subject_id"], r["exam_task_id"], r["title"],
                          json.loads(r["refs"] or "[]")), r["created"]

    def of_task(self, task_id: str) -> str | None:
        with self._read() as cx:
            r = cx.execute("SELECT stable_id FROM study_spaces WHERE exam_task_id=?"
                           " AND stable_id<>'' ORDER BY id LIMIT 1", (task_id,)).fetchone()
        return r["stable_id"] if r else None

    def ids_of_subjects(self, subject_ids: list[str]) -> list[str]:
        if not subject_ids:
            return []
        marks = ",".join("?" * len(subject_ids))
        with self._read() as cx:
            rows = cx.execute(f"SELECT stable_id FROM study_spaces WHERE stable_id<>'' AND"
                              f" subject_id IN ({marks}) ORDER BY stable_id",
                              tuple(subject_ids)).fetchall()
        return [r["stable_id"] for r in rows]

    def all_ids(self) -> list[str]:
        with self._read() as cx:
            rows = cx.execute("SELECT stable_id FROM study_spaces WHERE stable_id<>''"
                              " ORDER BY stable_id").fetchall()
        return [r["stable_id"] for r in rows]

    def add_document(self, d: CM.StudySpaceDocument, cx=None) -> None:
        with self._tx(cx) as c:
            if not c.execute("SELECT 1 FROM study_spaces WHERE stable_id=?",
                             (d.space_id,)).fetchone():
                raise IntegrityError(f"unknown study space: {d.space_id}")
            if not c.execute("SELECT 1 FROM resources WHERE stable_id=?",
                             (d.resource_id,)).fetchone():
                raise IntegrityError(f"unknown resource: {d.resource_id}")
            c.execute("INSERT OR REPLACE INTO study_space_documents(space_id, resource_id,"
                      " section, read, highlighted, ord) VALUES (?,?,?,?,?,?)",
                      (d.space_id, d.resource_id, d.section, int(d.read),
                       int(d.highlighted), d.order))

    def documents(self, space_id: str) -> list[CM.StudySpaceDocument]:
        with self._read() as cx:
            rows = cx.execute("SELECT * FROM study_space_documents WHERE space_id=?"
                              " ORDER BY ord, resource_id", (space_id,)).fetchall()
        return [CM.StudySpaceDocument(r["space_id"], r["resource_id"], r["section"],
                                      bool(r["read"]), bool(r["highlighted"]), r["ord"])
                for r in rows]

    def remove_document(self, space_id: str, resource_id: str) -> None:
        with self._tx() as c:
            c.execute("DELETE FROM study_space_documents WHERE space_id=? AND resource_id=?",
                      (space_id, resource_id))

    def set_goals(self, space_id: str, goals: list[CM.StudySpaceGoal], cx=None) -> None:
        with self._tx(cx) as c:
            c.execute("DELETE FROM study_space_goals WHERE space_id=?", (space_id,))
            for i, g in enumerate(sorted(goals, key=lambda g: g.order)):
                c.execute("INSERT INTO study_space_goals(space_id, ord, text, done)"
                          " VALUES (?,?,?,?)", (space_id, i, g.text, int(g.done)))

    def goals(self, space_id: str) -> list[CM.StudySpaceGoal]:
        with self._read() as cx:
            rows = cx.execute("SELECT * FROM study_space_goals WHERE space_id=? ORDER BY ord",
                              (space_id,)).fetchall()
        return [CM.StudySpaceGoal(r["space_id"], r["text"], bool(r["done"]), r["ord"])
                for r in rows]


# ------------------------------------------------------------------ calendar

class SeriesRepository(_Base):
    """Stable-id view over `schedule_series` (F1 table, F4.1 columns)."""

    def add(self, stable_id: str, subject_id: str, kind: str, weekday: int, start: str,
            end: str, first_day: date, last_day: date, interval_weeks: int = 1,
            room: str = "", notes: str = "", cx=None) -> None:
        with self._tx(cx) as c:
            if c.execute("SELECT 1 FROM schedule_series WHERE stable_id=?",
                         (stable_id,)).fetchone():
                raise IntegrityError(f"series exists: {stable_id}")
            c.execute("INSERT INTO schedule_series(subject_id, kind, weekday, start, end,"
                      " first_day, last_day, interval_weeks, room, stable_id, notes)"
                      " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      (subject_id, kind, weekday, start, end, first_day.isoformat(),
                       last_day.isoformat(), interval_weeks, room, stable_id, notes))

    def all(self) -> list[dict]:
        with self._read() as cx:
            rows = cx.execute("SELECT * FROM schedule_series"
                              " ORDER BY weekday, start, subject_id, stable_id, id").fetchall()
        return [dict(r) for r in rows]


# ------------------------------------------------------------------ personal

class PersonalRepository(_Base):
    def add_milestone(self, m: PL.Milestone, cx=None) -> None:
        with self._tx(cx) as c:
            c.execute("INSERT OR REPLACE INTO milestones VALUES (?,?,?,?,?,?)",
                      (m.stable_id, m.name, m.state, m.day.isoformat() if m.day else None,
                       m.order, m.subject_id))

    def milestones(self, subject_id: str | None = None) -> list[PL.Milestone]:
        q, args = "SELECT * FROM milestones", ()
        if subject_id is not None:
            q, args = q + " WHERE subject_id=?", (subject_id,)
        with self._read() as cx:
            rows = cx.execute(q + " ORDER BY ord, stable_id", args).fetchall()
        return [PL.Milestone(r["stable_id"], r["name"], r["state"],
                             date.fromisoformat(r["day"]) if r["day"] else None, r["ord"],
                             r["subject_id"]) for r in rows]

    def delete_milestone(self, stable_id: str) -> None:
        with self._tx() as c:
            c.execute("DELETE FROM milestones WHERE stable_id=?", (stable_id,))

    def add_note(self, n: PL.QuickNote, cx=None) -> None:
        with self._tx(cx) as c:
            c.execute("INSERT OR REPLACE INTO quick_notes VALUES (?,?,?)",
                      (n.stable_id, n.text, n.created))

    def notes(self) -> list[PL.QuickNote]:
        with self._read() as cx:
            rows = cx.execute("SELECT * FROM quick_notes ORDER BY created DESC, stable_id DESC"
                              ).fetchall()
        return [PL.QuickNote(r["stable_id"], r["text"], r["created"]) for r in rows]

    def delete_note(self, stable_id: str) -> None:
        with self._tx() as c:
            c.execute("DELETE FROM quick_notes WHERE stable_id=?", (stable_id,))

    def add_concept(self, k: PL.StudyConcept, cx=None) -> None:
        with self._tx(cx) as c:
            c.execute("INSERT OR REPLACE INTO study_concepts VALUES (?,?,?,?,?,?)",
                      (k.stable_id, k.subject_id, k.name, k.state,
                       k.last_review.isoformat() if k.last_review else None,
                       k.next_review.isoformat() if k.next_review else None))

    def concepts(self, subject_id: str | None = None) -> list[PL.StudyConcept]:
        q, args = "SELECT * FROM study_concepts", ()
        if subject_id is not None:
            q, args = q + " WHERE subject_id=?", (subject_id,)
        with self._read() as cx:
            rows = cx.execute(q + " ORDER BY stable_id", args).fetchall()
        return [PL.StudyConcept(r["stable_id"], r["subject_id"], r["name"], r["state"],
                                date.fromisoformat(r["last_review"]) if r["last_review"] else None,
                                date.fromisoformat(r["next_review"]) if r["next_review"] else None)
                for r in rows]

    def add_activity_day(self, day: date, cx=None) -> None:
        with self._tx(cx) as c:
            c.execute("INSERT OR IGNORE INTO activity_days(day) VALUES (?)", (day.isoformat(),))

    def activity_days(self) -> list[date]:
        with self._read() as cx:
            rows = cx.execute("SELECT day FROM activity_days ORDER BY day").fetchall()
        return [date.fromisoformat(r["day"]) for r in rows]

    def set_setting(self, key: str, value: str, cx=None) -> None:
        with self._tx(cx) as c:
            c.execute("INSERT OR REPLACE INTO app_settings(key, value) VALUES (?,?)", (key, value))

    def setting(self, key: str, default: str | None = None) -> str | None:
        with self._read() as cx:
            r = cx.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default

    def settings(self) -> dict[str, str]:
        with self._read() as cx:
            rows = cx.execute("SELECT key, value FROM app_settings ORDER BY key").fetchall()
        return {r["key"]: r["value"] for r in rows}


# ------------------------------------------------------------------ migration

class LegacyRepository(_Base):
    """legacy_map / legacy_payloads / migration_runs bookkeeping."""

    def mapped(self, system: str, table: str, source_id, cx=None) -> str | None:
        c = cx or self.db.connect()
        try:
            r = c.execute("SELECT target_id FROM legacy_map WHERE source_system=? AND"
                          " source_table=? AND source_id=?",
                          (system, table, str(source_id))).fetchone()
            return r["target_id"] if r else None
        finally:
            if cx is None:
                c.close()

    def all_mapped(self, system: str) -> dict[tuple[str, str], str]:
        with self._read() as cx:
            rows = cx.execute("SELECT source_table, source_id, target_id FROM legacy_map"
                              " WHERE source_system=?", (system,)).fetchall()
        return {(r["source_table"], r["source_id"]): r["target_id"] for r in rows}

    def map(self, system: str, table: str, source_id, target_id: str, cx=None) -> None:
        with self._tx(cx) as c:
            c.execute("INSERT OR IGNORE INTO legacy_map VALUES (?,?,?,?)",
                      (system, table, str(source_id), target_id))

    def keep(self, system: str, table: str, source_id, payload: dict, *, target_id: str = "",
             deferred_to: str = "", reason: str = "", cx=None) -> None:
        with self._tx(cx) as c:
            c.execute("INSERT OR IGNORE INTO legacy_payloads VALUES (?,?,?,?,?,?,?)",
                      (system, table, str(source_id), target_id, deferred_to, reason,
                       _j(payload)))

    def payloads(self, system: str, table: str = "") -> list[dict]:
        q, args = "SELECT * FROM legacy_payloads WHERE source_system=?", (system,)
        if table:
            q, args = q + " AND source_table=?", args + (table,)
        with self._read() as cx:
            rows = cx.execute(q + " ORDER BY source_table, CAST(source_id AS INTEGER),"
                              " source_id", args).fetchall()
        return [dict(r) | {"payload": json.loads(r["payload"])} for r in rows]

    def counts(self, system: str) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        with self._read() as cx:
            for r in cx.execute("SELECT source_table, COUNT(*) n FROM legacy_map"
                                " WHERE source_system=? GROUP BY source_table", (system,)):
                out.setdefault(r["source_table"], {})["mapped"] = r["n"]
            for r in cx.execute("SELECT source_table, COUNT(*) n FROM legacy_payloads"
                                " WHERE source_system=? GROUP BY source_table", (system,)):
                out.setdefault(r["source_table"], {})["preserved"] = r["n"]
        return out

    def record_run(self, run_id: str, system: str, source_digest: str, report_digest: str,
                   mode: str, started: str, finished: str, report: dict) -> None:
        with self._tx() as c:
            c.execute("INSERT OR REPLACE INTO migration_runs VALUES (?,?,?,?,?,?,?,?)",
                      (run_id, system, source_digest, report_digest, mode, started, finished,
                       _j(report)))

    def runs(self, system: str) -> list[dict]:
        with self._read() as cx:
            rows = cx.execute("SELECT run_id, mode, source_digest, report_digest, started,"
                              " finished FROM migration_runs WHERE source_system=?"
                              " ORDER BY started, run_id", (system,)).fetchall()
        return [dict(r) for r in rows]


# ------------------------------------------------------------- bulk writer

class TargetWriter:
    """Row writer bound to ONE open transaction (used by the Gestion
    migration so a run is all-or-nothing). Explicit columns, parameters
    only; validation already happened in the domain objects."""

    def __init__(self, cx):
        self.cx = cx

    def university(self, u) -> None:
        self.cx.execute("INSERT OR IGNORE INTO universities VALUES (?,?)", (u.stable_id, u.name))

    def degree(self, d) -> None:
        self.cx.execute("INSERT OR IGNORE INTO degrees VALUES (?,?,?)",
                        (d.stable_id, d.name, d.university_id))

    def year(self, y) -> None:
        self.cx.execute("INSERT INTO academic_years(stable_id, label, degree_id, state)"
                        " VALUES (?,?,?,?)", (y.stable_id, y.label, y.degree_id, y.state))

    def term(self, t) -> None:
        self.cx.execute("INSERT INTO terms(stable_id, label, kind, idx, academic_year_id,"
                        " start, end, state) VALUES (?,?,?,?,?,?,?,?)",
                        (t.stable_id, t.label, t.kind, t.index, t.academic_year_id,
                         t.start.isoformat() if t.start else None,
                         t.end.isoformat() if t.end else None, t.state))

    def subject(self, s) -> None:
        from academic_core.infrastructure.repositories import SUBJECT_UPSERT, subject_params
        if self.cx.execute("SELECT 1 FROM subjects WHERE stable_id=?",
                           (s.stable_id,)).fetchone():
            raise IntegrityError(f"subject id already taken: {s.stable_id}")
        self.cx.execute(SUBJECT_UPSERT, subject_params(s))

    def prerequisite(self, subject_id: str, requires_id: str) -> None:
        self.cx.execute("INSERT OR IGNORE INTO prerequisites VALUES (?,?)",
                        (subject_id, requires_id))

    def professor(self, p) -> None:
        self.cx.execute("INSERT OR IGNORE INTO professors(stable_id, name, email, office,"
                        " virtual_classroom) VALUES (?,?,?,?,?)",
                        (p.stable_id, p.name, p.email, p.office, p.virtual_classroom))

    def staff(self, link) -> None:
        self.cx.execute("INSERT INTO subject_staff(subject_id, professor_id, role, groups, ord,"
                        " email, office, virtual_url) VALUES (?,?,?,?,?,?,?,?)",
                        (link.subject_id, link.professor_id, link.role, link.groups,
                         link.order, link.email, link.office, link.virtual_url))

    def task(self, t) -> None:
        self.cx.execute("INSERT INTO tasks(stable_id, subject_id, title, kind, day, start, end,"
                        " priority, state, notes, description, location, link, reminder_days,"
                        " room, document_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (t.stable_id, t.subject_id, t.title, t.kind,
                         t.day.isoformat() if t.day else None, t.start, t.end, t.priority,
                         t.state, t.notes, t.description, t.location, t.link,
                         t.reminder_days, t.room, t.document_id))

    def session(self, s) -> None:
        self.cx.execute("INSERT INTO study_sessions(subject_id, day, minutes, notes)"
                        " VALUES (?,?,?,?)", (s.subject_id, s.day.isoformat(), s.minutes,
                                              s.notes))

    def counters(self, counters: dict[str, int]) -> None:
        for k in sorted(counters):
            self.cx.execute("INSERT OR REPLACE INTO id_counters VALUES (?,?)", (k, counters[k]))

    def load_counters(self) -> dict[str, int]:
        return {r["kind"]: r["last_n"]
                for r in self.cx.execute("SELECT kind, last_n FROM id_counters")}
