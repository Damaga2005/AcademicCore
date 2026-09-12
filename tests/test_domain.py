"""Domain invariants: hierarchy, relationships, no-legacy-without-reason."""
from datetime import date

import pytest

from academic_core.domain.entities import (
    AcademicYear, Assignment, Deadline, Degree, DomainError, Exam, GradeComponent,
    Lab, Professor, Project, ResourceReference, StudySpace, Subject, SubjectStaff,
    Task, Term, Topic, University,
)
from academic_core.domain.identity import validate


def _chain():
    u = University("university:u", "U")
    d = Degree("degree:g", "G", "university:u")
    y = AcademicYear("year:2025-26", "2025-26", "degree:g")
    t = Term("term:c1", "C1", "cuatrimestre", 1, "year:2025-26",
             date(2025, 9, 1), date(2026, 1, 31))
    s = Subject("subject:sdm", "230", "Sistemes", "SDM", credits=6.0,
                term_id="term:c1")
    return u, d, y, t, s


def test_hierarchy_validates_and_links():
    u, d, y, t, s = _chain()
    assert validate(s.stable_id) == "subject"
    Topic("topic:sdm:t01", "subject:sdm", "01", "Tema 1")
    SubjectStaff("subject:sdm", "professor:ada")
    Professor("professor:ada", "Ada Lovelace")
    ResourceReference("resource:sdm:r:00001", "subject:sdm", "material")
    Assignment("assignment:sdm:a:00001", "subject:sdm", "Practica 1")
    Exam("exam:sdm:e:00001", "subject:sdm", "Final", date(2026, 1, 15), 150)
    Project("project:sdm:p:00001", "subject:sdm", "TFG")
    Lab("lab:sdm:lab:00001", "subject:sdm", "Lab 1")
    Task("task:sdm:task:00001", "subject:sdm", "Estudiar", "examen_final")
    StudySpace("subject:sdm", "task:sdm:task:00001", "Estudio")


def test_term_generic_not_hardcoded():
    for kind in ("semestre", "cuatrimestre", "trimestre", "anual", "otro"):
        Term("term:x", "X", kind, 1, "year:2025-26")
    with pytest.raises(DomainError):
        Term("term:x", "X", "semester-upc", 1, "year:2025-26")
    with pytest.raises(DomainError):
        Term("term:x", "X", "semestre", 1, "year:2025-26",
             date(2026, 2, 1), date(2026, 1, 1))


def test_subject_rejects_legacy_assumptions():
    with pytest.raises(DomainError):
        Subject("subject:sdm", "", "", "SDM", term_id="term:c1")  # nameless
    with pytest.raises(DomainError):
        Subject("subject:sdm", "", "S", "SDM", kind="troncal-upc", term_id="term:c1")
    with pytest.raises(DomainError):
        GradeComponent("P", "parcial", "150", "5")  # weight out of range
    with pytest.raises(DomainError):
        GradeComponent("P", "parcial", "40", "11")  # score out of range
    with pytest.raises(DomainError):
        Task("task:sdm:task:00001", "subject:sdm", "T", "examen_upc")
    with pytest.raises(DomainError):
        Task("task:sdm:task:00001", "subject:sdm", "T", start="09:00")  # half interval


def test_task_exam_subset():
    assert Task("task:s:task:00001", "subject:s", "F", "examen_final").is_exam
    assert not Task("task:s:task:00002", "subject:s", "E", "entrega").is_exam
