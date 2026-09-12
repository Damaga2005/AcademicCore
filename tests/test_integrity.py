"""Integrity: guards, orphans, duplicates, invalid refs/dates/weights/grades."""
from datetime import date

import pytest

from academic_core.application import AcademicApp
from academic_core.config import Settings
from academic_core.domain import entities as E
from academic_core.infrastructure import IntegrityError


def _app(tmp_path):
    import os
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / "data")
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    return core


def _chain(core):
    ac = core.academic
    ac.add_university(E.University("university:u", "U"))
    ac.add_degree(E.Degree("degree:g", "G", "university:u"))
    ac.add_year(E.AcademicYear("year:2025-26", "2025-26", "degree:g"))
    ac.add_term(E.Term("term:c1", "C1", "cuatrimestre", 1, "year:2025-26"))
    ac.add_subject(E.Subject("subject:sdm", "230", "Sistemes", "SDM", term_id="term:c1"))


def test_parent_delete_blocked_until_empty(tmp_path):
    core = _app(tmp_path)
    _chain(core)
    core.svc.create_topic("subject:sdm", "01", "T1")
    with pytest.raises(IntegrityError):
        core.svc.delete_subject("subject:sdm")
    core.svc.delete_topic(core.planning, "topic:sdm:t01")
    core.svc.delete_subject("subject:sdm")  # now empty: allowed
    with pytest.raises(IntegrityError):
        core.svc.delete_year("year:2025-26")  # term still inside
    # term holds no subjects now, so the chain can unwind bottom-up
    core.svc.delete_term("term:c1")
    core.svc.delete_year("year:2025-26")
    core.svc.delete_degree("degree:g")
    core.svc.delete_university("university:u")
    assert core.academic.list_universities() == []


def test_duplicates_and_bad_refs(tmp_path):
    core = _app(tmp_path)
    _chain(core)
    with pytest.raises(Exception):
        core.svc.create_subject("Sistemes dup", "term:c1", acronym="SDM")
    with pytest.raises(IntegrityError):
        core.academic.add_prerequisite("subject:sdm", "subject:sdm")
    with pytest.raises(IntegrityError):
        core.academic.add_prerequisite("subject:sdm", "subject:fantasma")
    core.academic.add_subject(E.Subject("subject:fis", "", "Fisica", "FIS", term_id="term:c1"))
    core.academic.add_prerequisite("subject:sdm", "subject:fis")
    with pytest.raises(IntegrityError):
        core.academic.add_prerequisite("subject:sdm", "subject:fis")
    assert core.academic.prerequisites_of("subject:sdm") == ["subject:fis"]


def test_invalid_entities_rejected(tmp_path):
    core = _app(tmp_path)
    _chain(core)
    with pytest.raises(Exception):  # bad URL link
        E.Task("task:sdm:task:00001", "subject:sdm", "T", link="ftp://x")
    with pytest.raises(Exception):  # bad exam status
        E.Exam("exam:sdm:e:00001", "subject:sdm", "E", status="cuando-se-pueda")
    with pytest.raises(Exception):  # manipulated id
        core.academic.add_subject(E.Subject("rowid:42", "", "X", "X", term_id="term:c1"))
    with pytest.raises(Exception):  # end before start
        E.Term("term:x", "X", "semestre", 1, "year:2025-26",
               date(2026, 2, 1), date(2026, 1, 1))
    with pytest.raises(Exception):  # negative reminder
        E.Task("task:sdm:task:00001", "subject:sdm", "T", reminder_days=-1)


def test_task_with_space_blocks_delete(tmp_path):
    core = _app(tmp_path)
    _chain(core)
    t = core.svc.create_task(core.planning, core.study, "subject:sdm", "Final",
                             kind="examen_final", day=date(2026, 1, 15))
    with pytest.raises(IntegrityError):
        core.svc.delete_task(core.planning, t.stable_id)


def test_reopen_after_all_operations(tmp_path):
    import os
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / "data")
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    _chain(core)
    core.svc.create_topic("subject:sdm", "01", "T1")
    core2 = AcademicApp(Settings.load())
    assert core2.academic.get_subject("subject:sdm").name == "Sistemes"
    assert core2.academic.topics_of("subject:sdm")[0].title == "T1"
