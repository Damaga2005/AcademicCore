# SPDX-License-Identifier: MIT
"""F4.1 M1 — academic domain: statuses, career partition, entities, ids."""
from datetime import date
from decimal import Decimal

import pytest

from academic_core.domain import career as CR
from academic_core.domain import course_material as CM
from academic_core.domain import planning as PL
from academic_core.domain.entities import (
    DomainError, Professor, StudySpace, Subject, SubjectStaff, Task, Term,
)
from academic_core.domain.identity import IdAllocator, KINDS, make, validate


def _s(sid, state, term="term:q1", kind="obligatoria", credits=6.0, name=None):
    return Subject(f"subject:{sid}", "", name or sid.upper(), sid.upper(), credits=credits,
                   kind=kind, term_id=term, state=state)


def _terms():
    return [Term("term:q1", "Q1", "cuatrimestre", 1, "year:y1", state="superado"),
            Term("term:q2", "Q2", "cuatrimestre", 2, "year:y1", state="actual"),
            Term("term:q3", "Q3", "cuatrimestre", 1, "year:y2", state="actual")]


# ---------------------------------------------------------------- statuses

@pytest.mark.parametrize("state,status", [
    ("cursando", "CURSANDO"), ("superada", "APROBADA"), ("no_superada", "SUSPENDIDA"),
    ("pendiente", "NO_CURSANDO"), ("no_elegida", "NO_CURSANDO")])
def test_classification(state, status):
    assert CR.classify(state) is CR.AcademicStatus(status)


def test_resolve_state_accepts_fine_or_coarse():
    assert CR.resolve_state("APROBADA") == "superada"
    assert CR.resolve_state("no_elegida") == "no_elegida"
    with pytest.raises(DomainError):
        CR.resolve_state("aprobado")


def test_status_change_keeps_same_entity_and_leaves_current_view():
    subjects = [_s("dd", "cursando", "term:q2"), _s("al", "superada")]
    before = CR.partition(subjects, _terms())
    assert [s.stable_id for s in before.current] == ["subject:dd"]
    same, change = CR.change_state(subjects[0], "APROBADA")
    assert same is subjects[0] and change.changed and change.after == "superada"
    after = CR.partition(subjects, _terms())
    assert after.current == () and "subject:dd" in [s.stable_id for s in after.approved]
    _, again = CR.change_state(subjects[0], "superada")
    assert not again.changed  # idempotent


def test_partition_is_a_true_partition_and_multi_current_terms():
    subjects = [_s("a", "cursando", "term:q2"), _s("b", "cursando", "term:q3"),
                _s("c", "cursando", "term:q1"), _s("d", "superada"), _s("e", "no_superada"),
                _s("f", "pendiente"), _s("g", "no_elegida", kind="optativa")]
    p = CR.partition(subjects, _terms())
    assert p.current_term_ids == ("term:q2", "term:q3")
    assert [s.stable_id for s in p.current] == ["subject:a", "subject:b"]
    assert [s.stable_id for s in p.in_progress_elsewhere] == ["subject:c"]
    ids = p.all_ids()
    assert sorted(ids) == sorted(s.stable_id for s in subjects) and len(ids) == len(set(ids))


def test_averages_and_target():
    items = [CR.GradedCredit("subject:a", Decimal(6), Decimal("8"), "aprobada"),
             CR.GradedCredit("subject:b", Decimal("4.5"), Decimal("4"), "suspendida"),
             CR.GradedCredit("subject:c", Decimal(6), None, "en_progreso")]
    s = CR.summarize(items)
    assert s.weighted_by_credits == Decimal("6.29") and s.plain_mean == Decimal("6.00")
    assert (s.total, s.approved, s.failed, s.pending) == (3, 1, 1, 1)
    t = CR.target_average(items, Decimal("7"))
    # (7*16.5 - 66) / 6 = 8.25
    assert t.required == Decimal("8.25") and t.reachable is True
    assert CR.target_average(items, None).required is None


def test_degree_progress_uses_configured_total():
    subjects = [_s("a", "superada", credits=6), _s("b", "cursando", credits=6),
                _s("o", "superada", kind="optativa", credits=3),
                _s("x", "no_elegida", kind="optativa", credits=3),
                _s("tfg", "pendiente", credits=12, name="Trabajo de Fin de Grado")]
    p = CR.degree_progress(subjects, Decimal(240), ("Trabajo de Fin de Grado",))
    assert p.approved_credits == Decimal(9)
    assert p.mandatory.total == Decimal(12) and p.final_project.total == Decimal(12)
    assert p.elective.total == Decimal(216) and p.percent == Decimal("3.75")


# ---------------------------------------------------------------- entities

def test_subject_f41_fields_validate():
    s = Subject("subject:dd", "", "DD", "DD", final_grade="7.5",
                virtual_classroom="https://aula.example.edu", extra={"legacy": 1})
    assert s.final_grade == "7.5"
    for bad in ({"final_grade": "11"}, {"final_grade": "x"}, {"scheme_rule": "media"},
                {"virtual_classroom": "javascript:alert(1)"}):
        with pytest.raises(DomainError):
            Subject("subject:dd", "", "DD", "DD", **bad)


def test_task_without_subject_and_due_time_only():
    t = Task("task:general:task:00001", "", "Tutoría", "evento", date(2026, 9, 25))
    assert t.subject_id == ""
    Task("task:general:task:00002", "", "Entrega", "entrega", date(2026, 9, 25), end="23:59")
    with pytest.raises(DomainError):
        Task("task:general:task:00003", "", "x", start="10:00")
    with pytest.raises(DomainError):
        Task("task:general:task:00004", "", "x", document_id="subject:x")


def test_people_and_links():
    Professor("professor:ana", "Ana", virtual_classroom="https://x.example.edu")
    with pytest.raises(DomainError):
        Professor("professor:ana", "Ana", virtual_classroom="ftp://x")
    link = SubjectStaff("subject:dd", "professor:ana", "Responsable", "", 2, "a@b.c")
    assert link.order == 2
    StudySpace("", "task:general:task:00001", "sin asignatura")


def test_course_material_entities():
    g = CM.DocumentGroup("docgroup:dd:grp:00001", "subject:dd", "teoria", "  Tema   1 ")
    assert g.name == "Tema 1"
    with pytest.raises(DomainError):
        CM.DocumentGroup("docgroup:dd:grp:00001", "subject:dd", "musica", "x")
    d = CM.CourseDocument("subject:dd", "resource:dd:r:00001", "apuntes",
                          tags=(" vhdl", "fsm", "vhdl", ""))
    assert d.tags == ("vhdl", "fsm")
    x = CM.ExternalResource("link:dd:lnk:00001", "subject:dd", "W",
                            "https://es.wuolah.com/apuntes")
    assert x.provider == "wuolah"
    assert CM.provider_of("https://www.studocu.com/x") == "studocu"
    assert CM.provider_of("https://evil.com/?studocu.com") == "other"
    assert CM.provider_of("https://studocu.com.evil.net/") == "other"
    for bad in ("file:///etc/passwd", "javascript:alert(1)", "http://", ""):
        with pytest.raises(DomainError):
            CM.ExternalResource("link:dd:lnk:00001", "subject:dd", "W", bad)
    docs = [CM.StudySpaceDocument("space:dd:sp:00001", f"resource:dd:r:0000{i}",
                                  read=i < 2) for i in range(1, 4)]
    goals = [CM.StudySpaceGoal("space:dd:sp:00001", "leer", True)]
    p = CM.space_progress(docs, goals)
    assert (p.total, p.read, p.percent, p.goals_done) == (3, 1, 33, 1)


def test_planning_entities():
    m = PL.Milestone("milestone:00001", " B2 ", "pendiente")
    assert m.name == "B2" and m.cycled().state == "en_progreso"
    assert m.cycled().cycled().cycled().state == "pendiente"
    with pytest.raises(DomainError):
        PL.QuickNote("note:00001", "x" * 1001)
    k = [PL.StudyConcept("concept:dd:c:00001", "subject:dd", "FSM", "flojo",
                         next_review=date(2026, 9, 1)),
         PL.StudyConcept("concept:dd:c:00002", "subject:dd", "VHDL",
                         next_review=date(2026, 12, 1))]
    assert [c.name for c in PL.due_concepts(k, date(2026, 9, 23))] == ["FSM"]


def test_new_identity_kinds():
    for k in ("milestone", "note", "scheme", "block", "component", "link", "docgroup",
              "series", "space"):
        assert k in KINDS
    a = IdAllocator()
    assert a.allocate("scheme", "dd") == "scheme:dd:sch:00001"
    assert a.allocate("milestone") == "milestone:00001"
    assert validate(make("space", "general", "00007")) == "space"
    with pytest.raises(ValueError):
        validate("scheme:DD:sch:1")
