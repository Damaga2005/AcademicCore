# SPDX-License-Identifier: MIT
"""F4.1 — academic management use cases through the AcademicApp facade
(what the F15 UI will consume): Home, Carrera, subject detail, statuses,
evaluation service, milestones/notes/settings, repositories."""
import os
from datetime import date
from decimal import Decimal

import pytest

from academic_core.application import AcademicApp
from academic_core.config import Settings
from academic_core.domain import entities as E
from academic_core.domain import evaluation as EV
from academic_core.domain.career import AcademicStatus
from academic_core.errors import AcademicManagementError


def _app(tmp_path):
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / "data")
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    ac = core.academic
    ac.add_university(E.University("university:u", "U"))
    ac.add_degree(E.Degree("degree:g", "G", "university:u"))
    ac.add_year(E.AcademicYear("year:y1", "Curso 1", "degree:g"))
    ac.add_term(E.Term("term:q1", "Q1", "cuatrimestre", 1, "year:y1", state="superado"))
    ac.add_term(E.Term("term:q2", "Q2", "cuatrimestre", 2, "year:y1", state="actual"))
    core.svc.create_subject("Álgebra", "term:q1", acronym="AL", credits=6.0)
    core.svc.create_subject("Diseño Digital", "term:q2", acronym="DD", credits=6.0)
    core.svc.create_subject("Señales", "term:q2", acronym="SS", credits=4.5)
    for sid, st in (("subject:al", "superada"), ("subject:dd", "cursando"),
                    ("subject:ss", "cursando")):
        core.career.change_status(sid, st)
    return core


def test_home_shows_present_and_status_change_moves_same_entity(tmp_path):
    core = _app(tmp_path)
    home = core.career.home(date(2026, 9, 23))
    assert home.current_term_ids == ("term:q2",)
    assert [s.stable_id for s in home.current_subjects] == ["subject:dd", "subject:ss"]
    career = core.career.career()
    assert [s.stable_id for s in career.partition.current] == [
        s.stable_id for s in home.current_subjects]  # Home == Carrera current
    change = core.career.change_status("subject:dd", "APROBADA")
    assert change.changed and change.status_after is AcademicStatus.APROBADA
    home2 = core.career.home(date(2026, 9, 23))
    assert [s.stable_id for s in home2.current_subjects] == ["subject:ss"]
    assert core.academic.get_subject("subject:dd").state == "superada"
    assert len(core.academic.all_subjects()) == 3  # no duplication
    with pytest.raises(AcademicManagementError) as e:
        core.career.change_status("subject:dd", "aprobado")
    assert e.value.code == "AC-ACD-004"
    with pytest.raises(AcademicManagementError) as e:
        core.career.change_status("subject:nope", "APROBADA")
    assert e.value.code == "AC-ACD-002"


def test_evaluation_service_and_career_averages(tmp_path):
    core = _app(tmp_path)
    sch = core.evaluation.create_scheme(
        "subject:dd", "Continua",
        components=[{"name": "Parcial", "weight": "30", "score": "6", "kind": "parcial"},
                    {"name": "Final", "weight": "30", "min_grade": "4", "kind": "examen_final"}],
        blocks=[{"name": "Lab", "weight": "40",
                 "components": [{"name": "P1", "weight": "50", "score": "9"},
                                {"name": "P2", "weight": "50", "score": "7"}]}])
    ev = core.evaluation.evaluate("subject:dd")
    assert ev.state == "en_progreso" and ev.percent_evaluated == Decimal("70.00")
    final = [c for c in sch.components if c.name == "Final"][0]
    # 30*6 + 40*8 = 500 already reaches 5 over 100 -> nothing more needed
    assert core.evaluation.required_score(sch.stable_id, "subject:dd") == Decimal("0.00")
    assert core.evaluation.required_score(sch.stable_id, "subject:dd", "7") == Decimal("6.67")
    core.evaluation.set_score(final.stable_id, "5")
    ev = core.evaluation.evaluate("subject:dd")
    assert (ev.state, ev.grade) == ("aprobada", Decimal("6.5000"))
    with pytest.raises(AcademicManagementError):
        core.evaluation.set_score(final.stable_id, "12")
    with pytest.raises(AcademicManagementError):
        core.evaluation.create_scheme("subject:dd", "Bad", components=[
            {"name": "x", "weight": 30.0}])
    s = core.academic.get_subject("subject:al")
    s.final_grade = "8"
    core.academic.add_subject(s)
    core.plans.set_target_average("7")
    core.plans.set_degree_plan("240")
    career = core.career.career()
    assert career.averages.weighted_by_credits == Decimal("7.25")
    # (7 * 16.5 - (6*8 + 6*6.5)) / 4.5 pending credits (SS ungraded)
    assert career.target.required == Decimal("6.33") and career.target.reachable
    assert career.progress.approved_credits == Decimal(6)
    assert [t[0] for t in career.per_term] == ["term:q1", "term:q2"]


def test_course_detail_relates_everything(tmp_path):
    core = _app(tmp_path)
    core.academic.add_professor(E.Professor("professor:ana", "Ana"))
    core.academic.attach_staff(E.SubjectStaff("subject:dd", "professor:ana", "Responsable",
                                              order=0, email="ana@x.edu"))
    core.academic.add_prerequisite("subject:dd", "subject:al")
    core.material.add_external_resource("subject:dd", "Wuolah", "https://wuolah.com/x")
    doc = core.material.add_document("subject:dd", b"# Tema 1\n\nMealy y Moore", "tema1.md",
                                     category="apuntes")
    r = core.calendar.create_task("Parcial", date(2026, 10, 20), subject_id="subject:dd",
                                  kind="examen_parcial", start="09:00", end="11:00")
    core.calendar.add_series("subject:dd", "teoria", 2, "09:00", "11:00",
                             date(2026, 9, 7), date(2026, 12, 20))
    core.plans.add_milestone("Entregar proyecto", subject_id="subject:dd")
    d = core.career.course("subject:dd")
    assert d.status is AcademicStatus.CURSANDO and d.prerequisites_met
    assert [p.stable_id for p, _ in d.professors] == ["professor:ana"]
    assert d.professors[0][1].email == "ana@x.edu"
    assert [x.provider for x in d.external_resources] == ["wuolah"]
    assert [x.resource_id for x in d.documents_by_category["apuntes"]] == [doc.resource_id]
    assert [t.stable_id for t in d.tasks] == [r.task.stable_id]
    assert len(d.series) == 1 and d.study_spaces[0].task_id == r.task.stable_id
    assert [m.name for m in d.milestones] == ["Entregar proyecto"]
    home = core.career.home(date(2026, 9, 23), horizon_days=30)
    assert [s.task_id for s in home.study_spaces] == [r.task.stable_id]
    assert any(i.kind == "session" for i in home.week)
    assert [i.ref for i in home.upcoming] == [r.task.stable_id]


def test_milestones_notes_settings(tmp_path):
    core = _app(tmp_path)
    m = core.plans.add_milestone("B2", date(2027, 1, 1))
    assert core.plans.cycle_milestone(m.stable_id).state == "en_progreso"
    n = core.plans.add_note("  revisar  ")
    assert n.text == "revisar" and core.plans.notes()[0].stable_id == n.stable_id
    with pytest.raises(AcademicManagementError):
        core.plans.add_note("   ")
    with pytest.raises(AcademicManagementError):
        core.plans.set_target_average("11")
    with pytest.raises(AcademicManagementError):
        core.plans.add_milestone("x", subject_id="subject:nope")


def test_term_state_and_multiple_current_terms(tmp_path):
    core = _app(tmp_path)
    core.career.set_term_state("term:q1", "actual")
    assert core.career.home(date(2026, 9, 23)).current_term_ids == ("term:q1", "term:q2")
    with pytest.raises(AcademicManagementError):
        core.career.set_term_state("term:q1", "futuro")


def test_evaluation_repository_roundtrip(tmp_path):
    from academic_core.infrastructure import AcademicRepository, Database, EvaluationRepository

    def c(n, w, s=None, m=None, order=0):
        return EV.AssessmentComponent(f"component:x:cmp:{n:05d}", f"c{n}", w, "otro", s, m,
                                      order)
    db = Database(tmp_path / "a.db")
    ac = AcademicRepository(db)
    ac.add_university(E.University("university:u", "U"))
    ac.add_degree(E.Degree("degree:g", "G", "university:u"))
    ac.add_year(E.AcademicYear("year:y1", "Y1", "degree:g"))
    ac.add_term(E.Term("term:t1", "T1", "cuatrimestre", 1, "year:y1"))
    ac.add_subject(E.Subject("subject:x", "", "X", "X", term_id="term:t1"))
    repo = EvaluationRepository(db)
    blk = EV.AssessmentBlock("block:x:blk:00001", "Lab", "40", [c(1, "50", "10", "4"),
                                                                c(2, "50", "6", order=1)])
    sc = EV.AssessmentScheme("scheme:x:sch:00001", "subject:x", "s", [c(3, "60", "5")], [blk])
    repo.save_scheme(sc)
    back = repo.schemes_of("subject:x")
    assert len(back) == 1 and back[0].result() == sc.result()
    assert back[0].blocks[0].components[0].min_grade == Decimal("4")
    repo.set_score("component:x:cmp:00003", Decimal("7"))
    assert repo.schemes_of("subject:x")[0].components[0].score == Decimal("7")
    from academic_core.infrastructure import IntegrityError
    with pytest.raises(IntegrityError):
        repo.save_scheme(EV.AssessmentScheme("scheme:y:sch:00001", "subject:y", "s"))


def test_subject_extension_persists(tmp_path):
    core = _app(tmp_path)
    s = core.academic.get_subject("subject:dd")
    s.final_grade, s.notes, s.extra = "9.5", "nota", {"k": [1, 2]}
    core.academic.add_subject(s)
    back = core.academic.get_subject("subject:dd")
    assert (back.final_grade, back.notes, back.extra) == ("9.5", "nota", {"k": [1, 2]})
