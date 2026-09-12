"""Import/export: round-trip, id preservation, validation, error reporting."""
import json

import pytest

from academic_core.application import AcademicApp
from academic_core.config import Settings
from academic_core.domain import entities as E


def _app(tmp_path, tag="data"):
    import os
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / tag)
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    return core


def _seed(core):
    ac = core.academic
    ac.add_university(E.University("university:u", "U"))
    ac.add_degree(E.Degree("degree:g", "G", "university:u"))
    ac.add_year(E.AcademicYear("year:2025-26", "2025-26", "degree:g"))
    ac.add_term(E.Term("term:c1", "C1", "cuatrimestre", 1, "year:2025-26"))
    core.svc.create_subject("Sistemes", "term:c1", code="230", acronym="SDM")
    core.svc.create_topic("subject:sdm", "01", "Tema 1", "desc")
    core.svc.create_task(core.planning, core.study, "subject:sdm", "P",
                         kind="entrega", description="haz esto",
                         link="https://example.test/x", reminder_days=3)


def test_export_import_roundtrip(tmp_path):
    src = _app(tmp_path, "a")
    _seed(src)
    path = tmp_path / "acad.json"
    assert src.io.export_file(path) > 100
    dst = _app(tmp_path, "b")
    # hierarchy above subject must pre-exist (documented scope)
    for u in src.academic.list_universities():
        dst.academic.add_university(u)
    for d in src.academic.degrees_of("university:u"):
        dst.academic.add_degree(d)
    for y in src.academic.years_of("degree:g"):
        dst.academic.add_year(y)
    for t in src.academic.terms_of("year:2025-26"):
        dst.academic.add_term(t)
    rep = dst.io.import_file(path)
    assert rep["errors"] == []
    assert dst.academic.get_subject("subject:sdm").code == "230"
    assert dst.academic.topics_of("subject:sdm")[0].description == "desc"
    t = dst.planning.tasks_of("subject:sdm")[0]
    assert (t.link, t.reminder_days) == ("https://example.test/x", 3)


def test_import_rejects_schema_and_reports_bad_entities(tmp_path):
    core = _app(tmp_path)
    with pytest.raises(Exception):
        core.io.import_( {"schema": "nope/0", "data": {}})
    payload = {"schema": "academic-io/1", "data": {
        "universities": [{"stable_id": "university:u", "name": "U"}],
        "degrees": [],
        "subjects": [
            {"subject": {"stable_id": "subject:ok", "name": "Ok",
                         "term_id": "term:missing"},
             "topics": []},
            {"subject": {"stable_id": "bad id!!", "name": "Bad", "term_id": ""},
             "topics": []},
        ]}}
    rep = core.io.import_(payload)
    assert rep["imported"] == {"university": 1}
    assert len(rep["errors"]) == 2  # dangling term + manipulated id, nothing half-written
    assert core.academic.get_subject("subject:ok") is None


def test_malicious_strings_stored_safely(tmp_path):
    core = _app(tmp_path)
    _seed(core)
    evil = "'; DROP TABLE subjects; --"
    core.svc.create_topic("subject:sdm", "02", evil)
    assert core.academic.topics_of("subject:sdm")[1].title == evil
    assert core.academic.get_subject("subject:sdm") is not None  # table intact
    payload = core.io.export()
    assert evil in json.dumps(payload)  # escaped by JSON, no SQL smuggling
