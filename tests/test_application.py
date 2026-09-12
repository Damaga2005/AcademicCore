"""Application services: orchestration, assignment lifecycle, exam auto-space."""
from datetime import date, datetime

import pytest

from academic_core.application.services import (
    AcademicService, ApplicationError, GradingService, ScheduleService,
)
from academic_core.domain import entities as E
from academic_core.infrastructure import (
    AcademicRepository, Database, GradingRepository, PlanningRepository,
    StudyRepository,
)


def _svc(tmp_path):
    db = Database(tmp_path / "a.db")
    ac, pl, gr, st = (AcademicRepository(db), PlanningRepository(db),
                      GradingRepository(db), StudyRepository(db))
    ac.add_university(E.University("university:u", "U"))
    ac.add_degree(E.Degree("degree:g", "G", "university:u"))
    ac.add_year(E.AcademicYear("year:2025-26", "2025-26", "degree:g"))
    ac.add_term(E.Term("term:c1", "C1", "cuatrimestre", 1, "year:2025-26"))
    return AcademicService(ac), GradingService(gr), ScheduleService(pl), ac, pl, st


def test_subject_assignment_deadline_lifecycle(tmp_path):
    svc, _, _, ac, pl, _ = _svc(tmp_path)
    s = svc.create_subject("Sistemes", "term:c1", code="230", acronym="SDM")
    assert s.stable_id == "subject:sdm"
    with pytest.raises(ApplicationError):
        svc.create_subject("Sistemes Dup", "term:c1", acronym="SDM")  # duplicate
    a = svc.create_assignment(pl, s.stable_id, "Practica 1",
                              requirements="Req", status="active")
    assert a.status == "active" and a.requirements == "Req"
    rowid = svc.schedule_assignment(pl, a.stable_id, datetime(2025, 12, 1, 23, 59))
    assert rowid >= 1
    assert pl.deadlines_of(a.stable_id)[0].label == ""
    with pytest.raises(ApplicationError):
        svc.create_assignment(pl, "subject:nope", "X")


def test_exam_task_autocreates_study_space(tmp_path):
    svc, _, _, _, pl, st = _svc(tmp_path)
    s = svc.create_subject("Fisica", "term:c1")
    t = svc.create_task(pl, st, s.stable_id, "Final Fisica", kind="examen_final",
                        day=date(2026, 1, 15))
    assert t.is_exam
    # Second exam task for another subject gets its own space; same task idempotent.
    assert st.ensure_study_space(
        E.StudySpace(s.stable_id, t.stable_id, "dup")) is not None
    t2 = svc.create_task(pl, st, s.stable_id, "Hoja", kind="entrega")
    assert not t2.is_exam


def test_grading_service_end_to_end(tmp_path):
    svc, grading, _, _, _, _ = _svc(tmp_path)
    s = svc.create_subject("Mates", "term:c1")
    grading.record_scheme(s.stable_id, "continua",
                          [E.GradeComponent("P", "parcial", "40", "7.5"),
                           E.GradeComponent("F", "examen_final", "60", "5.25")])
    v = grading.calculate(s.stable_id)
    assert (str(v.grade), v.evaluated, v.state) == ("6.1500", True, "aprobada")


def test_schedule_service_warns_never_blocks(tmp_path):
    svc, _, sched, _, pl, st = _svc(tmp_path)
    s = svc.create_subject("Quimica", "term:c1")
    svc.create_task(pl, st, s.stable_id, "Parcial", kind="examen_parcial",
                    day=date(2025, 9, 2), start="09:30", end="11:30")
    _, sessions = sched.add_series(
        s.stable_id, kind="teoria", weekday=2, start="09:00", end="11:00",
        first_day=date(2025, 9, 1), last_day=date(2025, 9, 30))
    assert len(sessions) == 5
    conflicts = sched.check(date(2025, 9, 2), "09:00", "11:00")
    assert len(conflicts) == 2  # the task + the series session
    assert sched.check(date(2025, 9, 3), "09:00", "11:00") == []
