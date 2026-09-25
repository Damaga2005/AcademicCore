# SPDX-License-Identifier: MIT
"""F4.1 M5 — calendar/schedule: tasks, exam study spaces, class series,
conflicts, ICS export (deterministic, RFC 5545) and import (bounded)."""
import os
from datetime import date, datetime

import pytest

from academic_core.application import AcademicApp
from academic_core.config import Settings
from academic_core.domain import entities as E
from academic_core.errors import AcademicManagementError
from academic_core.infrastructure.ics import (
    ExportSeries, ExportTask, IcsError, export_calendar, parse_calendar, utc_to_madrid,
)


@pytest.fixture
def core(tmp_path):
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / "data")
    c = AcademicApp(Settings.load())
    c.settings.ensure_dirs()
    ac = c.academic
    ac.add_university(E.University("university:u", "U"))
    ac.add_degree(E.Degree("degree:g", "G", "university:u"))
    ac.add_year(E.AcademicYear("year:y1", "Y1", "degree:g"))
    ac.add_term(E.Term("term:q1", "Q1", "cuatrimestre", 1, "year:y1", state="actual"))
    c.svc.create_subject("Diseño Digital", "term:q1", acronym="DD")
    c.svc.create_subject("Señales y Sistemas", "term:q1", acronym="SS")
    return c


def test_task_without_subject_and_exam_space_autocreation(core):
    g = core.calendar.create_task("Tutoría", date(2026, 9, 25), kind="evento")
    assert g.task.stable_id.startswith("task:general:task:") and g.study_space_id is None
    ex = core.calendar.create_task("Final DD", date(2027, 1, 15), subject_id="subject:dd",
                                   kind="examen_final", start="09:00", end="12:00")
    assert ex.study_space_id and core.study_spaces.of_task(ex.task.stable_id) == ex.study_space_id
    assert core.calendar.ensure_space(ex.task) == ex.study_space_id  # idempotent
    with pytest.raises(AcademicManagementError):
        core.calendar.create_task("x", date(2026, 1, 1), subject_id="subject:nope")
    with pytest.raises(AcademicManagementError):
        core.calendar.create_task("x", date(2026, 1, 1), kind="fiesta")


def test_complete_and_postpone(core):
    t = core.calendar.create_task("Entrega", date(2026, 9, 30), subject_id="subject:ss",
                                  kind="entrega", end="23:59").task
    assert core.calendar.postpone(t.stable_id, 3).day == date(2026, 10, 3)
    assert core.calendar.complete(t.stable_id).state == "hecha"
    home = core.career.home(date(2026, 9, 23))
    assert t.stable_id not in [i.ref for i in home.upcoming]


def test_series_sessions_and_conflicts_warn_never_block(core):
    sid, sessions = core.calendar.add_series("subject:dd", "laboratorio", 2, "15:00", "17:00",
                                             date(2026, 9, 7), date(2026, 10, 5),
                                             interval_weeks=2, room="L1")
    assert sid.startswith("series:dd:ser:")
    assert sessions == [date(2026, 9, 8), date(2026, 9, 22)]
    r = core.calendar.create_task("Tutoría DD", date(2026, 9, 22), subject_id="subject:dd",
                                  kind="tutoria", start="16:00", end="16:30")
    assert [c.ref for c in r.conflicts] == [sid]  # warned, and still created
    assert core.planning.get_task(r.task.stable_id) is not None
    assert core.calendar.conflicts(date(2026, 9, 15), "16:00", "16:30") == []  # off-week
    t2 = core.calendar.create_task("Otra", date(2026, 9, 22), kind="evento",
                                   start="16:15", end="17:30")
    assert {c.kind for c in t2.conflicts} == {"series", "task"}
    with pytest.raises(AcademicManagementError):
        core.calendar.add_series("subject:dd", "teoria", 8, "09:00", "10:00",
                                 date(2026, 9, 7), date(2026, 10, 5))
    agenda = core.career.agenda(date(2026, 9, 21), date(2026, 9, 27))
    assert [(i.kind, i.day) for i in agenda][:1] == [("session", date(2026, 9, 22))]


# ------------------------------------------------------------------- ICS

def test_ics_export_is_deterministic_and_rfc_shaped(core):
    core.calendar.create_task("Parcial; DD, tema 1", date(2026, 10, 20),
                              subject_id="subject:dd", kind="examen_parcial",
                              start="09:00", end="11:00", room="A1")
    core.calendar.create_task("Entrega", date(2026, 10, 1), subject_id="subject:ss",
                              kind="entrega")
    core.calendar.add_series("subject:dd", "teoria", 3, "09:00", "11:00", date(2026, 9, 7),
                             date(2026, 12, 20), interval_weeks=2)
    a = core.calendar.export_ics("20260923T000000Z")
    b = core.calendar.export_ics("20260923T000000Z")
    assert a == b and a.startswith("BEGIN:VCALENDAR\r\n") and a.endswith("END:VCALENDAR\r\n")
    assert "SUMMARY:DD · Parcial\\; DD\\, tema 1" in a
    assert "DTSTART:20261020T090000" in a and "LOCATION:A1" in a
    assert "DTSTART;VALUE=DATE:20261001" in a and "DTEND;VALUE=DATE:20261002" in a
    assert "RRULE:FREQ=WEEKLY;BYDAY=WE;INTERVAL=2;UNTIL=20261220T235959Z" in a
    assert "DTSTART:20260909T090000" in a  # first real session, not first_day
    assert all(len(line.encode()) <= 75 for line in a.split("\r\n"))
    with pytest.raises(IcsError):
        core.calendar.export_ics("today")


def test_ics_folding_and_escaping_roundtrip():
    long = "Ñ" * 80 + ", ; \\ fin"
    out = export_calendar([ExportTask("task:x", long, date(2026, 1, 1))],
                          [ExportSeries("s", "t", 1, "09:00", "10:00", None,
                                        date(2026, 1, 1))], dtstamp="20260101T000000Z")
    assert all(len(line.encode()) <= 75 for line in out.split("\r\n"))
    ev = parse_calendar(out.encode())
    assert ev[0].summary == long  # unfold + unescape is lossless


ICS = """BEGIN:VCALENDAR\r
BEGIN:VEVENT\r
UID:1\r
SUMMARY:Entrega práctica 2\r
DTSTART:20261015T215900Z\r
URL:https://atenea.example.edu/mod/assign/view.php?id=1\r
CATEGORIES:230913 - Senyals i Sistemes (Curs 2)\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:2\r
SUMMARY:Cuestionario\r
DTSTART;VALUE=DATE:20261201\r
URL:https://atenea.example.edu/mod/quiz/view.php?id=2\r
CATEGORIES:999999 - Astrofísica (Curs 4)\r
END:VEVENT\r
BEGIN:VEVENT\r
SUMMARY:Sin fecha\r
END:VEVENT\r
BEGIN:VEVENT\r
SUMMARY:Fecha rota\r
DTSTART:2026-99-99\r
END:VEVENT\r
END:VCALENDAR\r
"""


def test_ics_import_preview_then_apply(core):
    props = core.calendar.ics_preview(ICS.encode())
    assert [p.title for p in props] == ["Entrega práctica 2", "Cuestionario"]
    e, q = props
    assert (e.day, e.end, e.kind) == (date(2026, 10, 15), "23:59", "entrega")  # UTC+2 (CEST)
    assert e.subject_id == "subject:ss" and not e.needs_review
    assert q.subject_id == "" and q.needs_review and q.kind == "tarea_general"
    res = core.calendar.ics_apply(props)
    assert res == {"created": 2, "skipped": 0}
    again = core.calendar.ics_preview(ICS.encode())
    assert all(p.duplicate for p in again)
    assert core.calendar.ics_apply(again) == {"created": 0, "skipped": 2}
    t = [t for t in core.planning.all_tasks() if t.title == "Entrega práctica 2"][0]
    assert (t.subject_id, t.start, t.end) == ("subject:ss", "", "23:59")


def test_madrid_offsets():
    assert utc_to_madrid(datetime(2026, 1, 10, 12)).hour == 13
    assert utc_to_madrid(datetime(2026, 7, 10, 12)).hour == 14
    assert utc_to_madrid(datetime(2026, 3, 29, 0, 59)).hour == 1  # before switch
    assert utc_to_madrid(datetime(2026, 3, 29, 1, 0)).hour == 3


# ids explícitos: pytest-qt exporta el node id a una variable de entorno y
# Windows limita las env vars a 32767 caracteres (los MB de X colgaban CI).
# Los inputs bajo prueba no cambian.
@pytest.mark.parametrize("raw", [b"hello", b"BEGIN:VCALENDAR\n" + b"X" * (3 * 1024 * 1024),
                                 b"BEGIN:VCALENDAR\nSUMMARY:" + b"a" * 9000 + b"\n"],
                         ids=["not-ical", "oversize-3mb", "line-too-long"])
def test_ics_limits(raw):
    with pytest.raises(IcsError) as e:
        parse_calendar(raw)
    assert e.value.code == "AC-ICS-001"


def test_ics_event_count_limit(monkeypatch):
    import academic_core.infrastructure.ics as ics
    monkeypatch.setattr(ics, "MAX_EVENTS", 3)
    body = "BEGIN:VCALENDAR\n" + "BEGIN:VEVENT\nSUMMARY:x\nDTSTART:20260101\nEND:VEVENT\n" * 4
    with pytest.raises(IcsError):
        parse_calendar(body.encode())
