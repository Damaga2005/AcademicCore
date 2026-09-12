"""Queries: hierarchy, planning, grades — no SQL in callers."""
from datetime import date, datetime

from academic_core.application import AcademicApp
from academic_core.config import Settings
from academic_core.domain import entities as E
from academic_core.domain import results as R
from decimal import Decimal


def _app(tmp_path):
    import os
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / "data")
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    ac = core.academic
    ac.add_university(E.University("university:u", "U"))
    ac.add_degree(E.Degree("degree:g", "G", "university:u"))
    ac.add_year(E.AcademicYear("year:2025-26", "2025-26", "degree:g"))
    ac.add_term(E.Term("term:c1", "C1", "cuatrimestre", 1, "year:2025-26"))
    ac.add_subject(E.Subject("subject:sdm", "230", "Sistemes", "SDM", term_id="term:c1"))
    return core


def test_tree_and_activities(tmp_path):
    core = _app(tmp_path)
    tree = core.queries.tree()
    assert tree[0]["degrees"][0]["years"][0]["terms"][0]["subjects"][0].name == "Sistemes"
    acts = core.queries.activities_by_subject("subject:sdm")
    assert set(acts) == {"assignments", "exams", "projects", "labs", "tasks",
                         "topics", "refs"}


def test_deadlines_upcoming_overdue(tmp_path):
    core = _app(tmp_path)
    core.svc.create_assignment(core.planning, "subject:sdm", "P1", status="active")
    a = core.planning.assignments_of("subject:sdm")[0]
    core.planning.add_deadline(a.stable_id, datetime(2025, 1, 1, 23, 59), "vieja")
    core.svc.create_task(core.planning, core.study, "subject:sdm", "T",
                         kind="entrega", day=date(2026, 6, 1))
    up = core.queries.upcoming_deadlines(date(2026, 1, 1))
    over = core.queries.overdue_deadlines(date(2026, 1, 1))
    assert [d.kind for d in up] == ["task"] and up[0].due.startswith("2026-06-01")
    assert [d.kind for d in over] == ["assignment"]
    # completed activities disappear from both lists
    a2 = core.planning.get_assignment(a.stable_id)
    a2.status = "graded"
    core.planning.add_assignment(a2)
    assert core.queries.overdue_deadlines(date(2026, 1, 1)) == []


def test_pending_and_exams_and_grades(tmp_path):
    core = _app(tmp_path)
    core.svc.create_assignment(core.planning, "subject:sdm", "P1")
    core.svc.create_exam(core.planning, "subject:sdm", "Final",
                         day=date(2026, 1, 15), status="planned")
    assert len(core.queries.pending_assignments("subject:sdm")) == 1
    assert len(core.queries.pending_assignments("subject:nope")) == 0
    assert core.queries.upcoming_exams(date(2026, 1, 1))[0].title == "Final"
    assert core.queries.upcoming_exams(date(2026, 2, 1)) == []
    core.results.record("subject:sdm", R.Grade("p", "8", R.N_10, Decimal(100)))
    assert core.queries.grades_by_subject("subject:sdm")[0].value == "8"
    assert core.results.result("subject:sdm").state == "aprobada"
