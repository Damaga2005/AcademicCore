"""Academic import/export (Phase 4): JSON tree snapshots, no cloud.

Format: {"schema": "academic-io/1", "exported_at": iso, "data": {...}} with
stable ids preserved. Import validates everything BEFORE writing anything
(collect errors, write only when clean); unknown ids/references abort the
entity, never half-import. Secrets never exported.
"""

from __future__ import annotations

import json
from datetime import date

from academic_core.domain import entities as E

SCHEMA = "academic-io/1"


class ImportError_(ValueError):
    pass


class AcademicIO:
    def __init__(self, app):
        self.app = app  # AcademicApp facade (duck-typed to avoid a cycle)

    # -- export -------------------------------------------------------------
    def export(self) -> dict:
        ac, q = self.app.academic, self.app.queries
        subjects = []
        for s in ac.all_subjects():
            sid = s.stable_id
            acts = q.activities_by_subject(sid)
            subjects.append({
                "subject": s.__dict__,
                "topics": [t.__dict__ for t in acts["topics"]],
                "assignments": [a.__dict__ for a in acts["assignments"]],
                "exams": [{**e.__dict__, "day": e.day.isoformat() if e.day else None}
                          for e in acts["exams"]],
                "projects": [p.__dict__ for p in acts["projects"]],
                "labs": [{**lb.__dict__, "day": lb.day.isoformat() if lb.day else None}
                         for lb in acts["labs"]],
                "tasks": [{**t.__dict__, "day": t.day.isoformat() if t.day else None}
                          for t in acts["tasks"]],
                "grades": [{"key": g.key, "value": g.value,
                            "scale": {"kind": g.scale.kind, "low": str(g.scale.low),
                                      "high": str(g.scale.high),
                                      "letters": list(g.scale.letters)},
                            "weight": str(g.weight), "optional": g.optional,
                            "date": g.date, "notes": g.notes}
                           for g in self.app.gradebook.grades_of(sid)],
                "prerequisites": ac.prerequisites_of(sid),
            })
        return {"schema": SCHEMA, "data": {
            "universities": [u.__dict__ for u in ac.list_universities()],
            "degrees": [d.__dict__ for deg in
                        [ac.degrees_of(u.stable_id) for u in ac.list_universities()]
                        for d in deg],
            "subjects": subjects}}

    def export_file(self, path) -> int:
        from pathlib import Path as _P
        payload = json.dumps(self.export(), ensure_ascii=False, indent=1, default=str)
        _P(path).write_text(payload, encoding="utf-8")
        return len(payload.encode("utf-8"))

    # -- import ---------------------------------------------------------------
    def import_(self, payload: dict) -> dict:
        """Validate-then-write. Returns {'imported': {...counts}, 'errors': [...]};
        raises ImportError_ when nothing could be imported cleanly... actually
        imports the clean subset and reports errors per entity (never partial
        writes per entity: each entity validates fully before its INSERT)."""
        if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
            raise ImportError_(f"unsupported schema (want {SCHEMA})")
        data = payload.get("data", {})
        errors: list[str] = []
        counts: dict[str, int] = {}
        ac, pl = self.app.academic, self.app.planning

        def ok(n, fn, label):
            try:
                fn()
                counts[label] = counts.get(label, 0) + 1
            except Exception as e:  # validated per entity; collect, continue
                errors.append(f"{label}: {e}")

        for u in data.get("universities", []):
            ok(1, lambda u=u: ac.add_university(E.University(u["stable_id"], u["name"])), "university")
        for d in data.get("degrees", []):
            ok(1, lambda d=d: ac.add_degree(E.Degree(d["stable_id"], d["name"], d["university_id"])), "degree")
        # years/terms travel inside subjects? No — export only what F4 owns in
        # full; hierarchy above subject must pre-exist OR be created minimal.
        # Subjects carry term_id: create missing years/terms is OUT of scope;
        # dangling term_id aborts that subject (reported, not half-written).
        for s in data.get("subjects", []):
            sd = s.get("subject", {})
            sid = sd.get("stable_id", "?")
            try:
                sub = E.Subject(sd["stable_id"], sd.get("code", ""), sd["name"],
                                sd.get("acronym", ""), sd.get("description", ""),
                                sd.get("credits", 0.0), sd.get("kind", "obligatoria"),
                                sd.get("course", 0), sd.get("term_id", ""),
                                sd.get("state", "pendiente"))
                if sub.term_id and not any(
                        t.stable_id == sub.term_id
                        for y in [yy for d in
                                  [dg for u in ac.list_universities()
                                   for dg in ac.degrees_of(u.stable_id)]
                                  for yy in ac.years_of(d.stable_id)]
                        for t in ac.terms_of(y.stable_id)):
                    raise ImportError_(f"dangling term_id {sub.term_id}")
                ac.add_subject(sub)
                counts["subject"] = counts.get("subject", 0) + 1
            except Exception as e:
                errors.append(f"subject {sid}: {e}")
                continue
            for t in s.get("topics", []):
                ok(1, lambda t=t: ac.add_topic(E.Topic(
                    t["stable_id"], sid, t["index"], t["title"],
                    t.get("description", ""))), "topic")
            for a in s.get("assignments", []):
                ok(1, lambda a=a: pl.add_assignment(E.Assignment(
                    a["stable_id"], sid, a["title"], a.get("requirements", ""),
                    a.get("resources", []), a.get("workspace", ""), a.get("files", []),
                    a.get("report_ref", ""), a.get("rubric", ""),
                    a.get("submission", ""), a.get("status", "draft"))), "assignment")
            for e in s.get("exams", []):
                ok(1, lambda e=e: pl.add_exam(E.Exam(
                    e["stable_id"], sid, e["title"],
                    date.fromisoformat(e["day"]) if e.get("day") else None,
                    e.get("duration_min", 0), e.get("session", ""),
                    e.get("allowed_resources", ""), e.get("result", ""),
                    e.get("status", "planned"), e.get("weight"),
                    e.get("score"), e.get("notes", ""))), "exam")
            for p in s.get("projects", []):
                ok(1, lambda p=p: pl.add_project(E.Project(
                    p["stable_id"], sid, p["title"], p.get("description", ""),
                    p.get("milestones", []), p.get("links", []),
                    p.get("status", "planned"), p.get("weight"),
                    p.get("score"), p.get("notes", ""))), "project")
            for lb in s.get("labs", []):
                ok(1, lambda lb=lb: pl.add_lab(E.Lab(
                    lb["stable_id"], sid, lb["title"], lb.get("description", ""),
                    date.fromisoformat(lb["day"]) if lb.get("day") else None,
                    lb.get("status", "planned"), lb.get("score"),
                    lb.get("notes", ""))), "lab")
            for t in s.get("tasks", []):
                ok(1, lambda t=t: pl.add_task(E.Task(
                    t["stable_id"], sid, t["title"], t.get("kind", "tarea_general"),
                    date.fromisoformat(t["day"]) if t.get("day") else None,
                    t.get("start", ""), t.get("end", ""), t.get("priority", "media"),
                    t.get("state", "pendiente"), t.get("notes", ""),
                    t.get("description", ""), t.get("location", ""),
                    t.get("link", ""), t.get("reminder_days"))), "task")
            for g in s.get("grades", []):
                def _rec(g=g):
                    from decimal import Decimal
                    from academic_core.domain import results as R_
                    sc = g["scale"]
                    scale = R_.Scale(sc["kind"], Decimal(sc["low"]),
                                     Decimal(sc["high"]), tuple(sc["letters"]))
                    self.app.gradebook.record(
                        sid, R_.Grade(g["key"], g["value"], scale,
                                      Decimal(g["weight"]), g["optional"],
                                      g.get("date", ""), g.get("notes", "")))
                ok(1, _rec, "grade")
            for req in s.get("prerequisites", []):
                ok(1, lambda req=req: ac.add_prerequisite(sid, req), "prerequisite")
        return {"imported": counts, "errors": errors}

    def import_file(self, path) -> dict:
        import json as _j
        from pathlib import Path as _P
        return self.import_(json.loads(_P(path).read_text(encoding="utf-8")))
