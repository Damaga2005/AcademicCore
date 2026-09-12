"""Persistence gate: create -> save -> close -> reopen -> recover identical."""
from datetime import date, datetime

from academic_core.domain import entities as E
from academic_core.infrastructure import (
    AcademicRepository, Database, GradingRepository, PlanningRepository,
    StudyRepository,
)


def _seed(db):
    ac, pl, gr, st = (AcademicRepository(db), PlanningRepository(db),
                      GradingRepository(db), StudyRepository(db))
    ac.add_university(E.University("university:u", "U"))
    ac.add_degree(E.Degree("degree:g", "G", "university:u"))
    ac.add_year(E.AcademicYear("year:2025-26", "2025-26", "degree:g"))
    ac.add_term(E.Term("term:c1", "C1", "cuatrimestre", 1, "year:2025-26"))
    ac.add_subject(E.Subject("subject:sdm", "230", "Sistemes", "SDM",
                             credits=6.0, term_id="term:c1"))
    ac.add_professor(E.Professor("professor:ada", "Ada"))
    ac.attach_staff(E.SubjectStaff("subject:sdm", "professor:ada", "coordinador"))
    pl.add_assignment(E.Assignment("assignment:sdm:a:00001", "subject:sdm", "P1",
                                   status="active"))
    pl.add_task(E.Task("task:sdm:task:00001", "subject:sdm", "Final",
                       "examen_final", date(2026, 1, 15), "09:00", "12:00"))
    pl.add_deadline("assignment:sdm:a:00001", datetime(2025, 12, 1, 23, 59), "l entrega")
    pl.add_series("subject:sdm", "teoria", 2, "09:00", "11:00",
                  date(2025, 9, 1), date(2025, 12, 19), 1, "A1")
    gr.save_scheme("subject:sdm", "continua",
                   [E.GradeComponent("Parcial", "parcial", "40", "7.5")])
    st.ensure_study_space(E.StudySpace("subject:sdm", "task:sdm:task:00001", "Estudio"))
    st.add_session(E.StudySession("subject:sdm", date(2025, 9, 2), 90))
    ac.save_counters({"assignment": 1, "task": 1})
    return ac


def test_roundtrip_across_reopen(tmp_path):
    path = tmp_path / "academic.db"
    _seed(Database(path))
    # Reopen with brand-new objects: everything must come back identical.
    db2 = Database(path)
    ac2 = AcademicRepository(db2)
    assert ac2.get_subject("subject:sdm").name == "Sistemes"
    assert ac2.get_subject("subject:sdm").credits == 6.0
    assert [s.stable_id for s in ac2.subjects_of_term("term:c1")] == ["subject:sdm"]
    assert ac2.staff_of("subject:sdm")[0][0].name == "Ada"
    assert ac2.load_counters() == {"assignment": 1, "task": 1}

    pl2 = PlanningRepository(db2)
    assigns = pl2.assignments_of("subject:sdm")
    assert [(a.stable_id, a.status) for a in assigns] == [("assignment:sdm:a:00001", "active")]
    tasks = pl2.tasks_of("subject:sdm")
    assert tasks[0].day == date(2026, 1, 15) and tasks[0].is_exam
    assert pl2.deadlines_of("assignment:sdm:a:00001")[0].due == datetime(2025, 12, 1, 23, 59)
    assert len(pl2.series_of("subject:sdm")) == 1

    gr2 = GradingRepository(db2)
    comps, final, _ = gr2.load_schemes("subject:sdm")["continua"]
    assert [(c.name, c.weight, c.score) for c in comps] == [("Parcial", "40", "7.5")]

    st2 = StudyRepository(db2)
    assert st2.streak(date(2025, 9, 2)) == 1
    assert st2.streak(date(2025, 9, 3)) == 0


def test_migrations_are_incremental_and_rerunnable(tmp_path):
    path = tmp_path / "academic.db"
    Database(path).connect().close()
    # Second open on the same file must be a no-op, never a giant re-migration.
    Database(path).connect().close()
    import sqlite3
    vers = sqlite3.connect(path).execute("SELECT version FROM schema_version ORDER BY version").fetchall()
    assert [v[0] for v in vers] == [1, 2, 3, 4, 5, 6]
