# SPDX-License-Identifier: MIT
"""F4.2 notifications: the four rules, boundaries, omission cases, purity."""
import hashlib
import os
import sqlite3
from dataclasses import replace
from datetime import date
from pathlib import Path

from academic_core.application import AcademicApp
from academic_core.config import Settings
from academic_core.domain import entities as E

_SRC = Path(__file__).resolve().parents[1] / "src"

TODAY = date(2026, 9, 24)


def _app(tmp_path, tag="data"):
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / tag)
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    ac = core.academic
    ac.add_university(E.University("university:u", "U"))
    ac.add_degree(E.Degree("degree:g", "G", "university:u"))
    ac.add_year(E.AcademicYear("year:y1", "Curso 1", "degree:g"))
    ac.add_term(E.Term("term:q1", "Q1", "cuatrimestre", 1, "year:y1", state="actual"))
    core.svc.create_subject("Diseño Digital", "term:q1", acronym="DD", credits=6.0)
    core.career.change_status("subject:dd", "cursando")
    return core


def _task(core, title, day, kind="entrega", **kw):
    return core.calendar.create_task(title, day, subject_id="subject:dd",
                                     kind=kind, **kw)


def _space_for(core, res):
    return res.study_space_id


def _db_hash(core):
    cx = sqlite3.connect(core.db.path)
    h = hashlib.sha256()
    tables = [r[0] for r in cx.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE"
        " 'sqlite_%' ORDER BY name")]
    for t in tables:
        rows = sorted(repr(r) for r in cx.execute(f'SELECT * FROM "{t}"'))
        h.update(f"{t}:{len(rows)}:{'|'.join(rows)}".encode())
    cx.close()
    return h.hexdigest()


def _kinds(result):
    return [(v.kind, v.level) for v in result]


def test_overdue_and_boundaries(tmp_path):
    core = _app(tmp_path)
    _task(core, "Atrasada", date(2026, 9, 20))
    _task(core, "Hoy", TODAY)
    _task(core, "Umbral", date(2026, 10, 1))  # days == 7 == default threshold
    _task(core, "Fuera", date(2026, 10, 2))  # days == 8 > 7
    got = core.notify.compute(TODAY)
    by_title = {v.title: v for v in got}
    assert (by_title["Atrasada"].kind, by_title["Atrasada"].level) == (
        "tarea_atrasada", "rojo")
    assert "desde hace 4 día(s)" in by_title["Atrasada"].message
    assert (by_title["Hoy"].kind, by_title["Hoy"].level) == ("tarea_inminente", "rojo")
    assert " hoy " in by_title["Hoy"].message
    assert by_title["Umbral"].kind == "tarea_inminente"
    assert "Fuera" not in by_title


def test_red_orange_boundary_and_custom_reminder(tmp_path):
    core = _app(tmp_path)
    _task(core, "Dos", date(2026, 9, 26))  # days == 2 -> rojo
    _task(core, "Tres", date(2026, 9, 27))  # days == 3 -> naranja
    _task(core, "Custom", date(2026, 10, 20), reminder_days=30)
    got = {v.title: v for v in core.notify.compute(TODAY)}
    assert got["Dos"].level == "rojo"
    assert got["Tres"].level == "naranja"
    assert got["Custom"].kind == "tarea_inminente"  # override wins over default 7


def test_done_cancelled_dateless_skipped_and_past_exam_omitted(tmp_path):
    core = _app(tmp_path)
    t1 = _task(core, "Hecha", date(2026, 9, 20))
    core.calendar.complete(t1.task.stable_id)
    t2 = _task(core, "Vieja", date(2026, 9, 20), kind="tarea_general")
    cancelled = replace(t2.task, state="cancelada")
    core.planning.add_task(cancelled)
    core.calendar.create_task("Sin fecha", None, subject_id="subject:dd")
    _task(core, "Examen pasado", date(2026, 9, 10), kind="examen_final")
    before = _db_hash(core)
    got = core.notify.compute(TODAY)
    assert [v.title for v in got] == []
    assert _db_hash(core) == before  # compute() never writes (no autocompletar)


def test_space_rules(tmp_path):
    core = _app(tmp_path)
    day = date(2026, 9, 25)  # 1 day -> rojo
    res = _task(core, "Parcial", day, kind="examen_final")
    sid = _space_for(core, res)
    spaces_only = lambda: [v for v in core.notify.compute(TODAY)
                           if v.kind == "espacio_sin_empezar"]
    assert spaces_only() == []  # no material -> omit
    doc = core.material.add_document("subject:dd", b"contenido", "tema.pdf")
    core.material.select_for_space(sid, doc.resource_id)
    got = spaces_only()
    assert [(v.kind, v.level) for v in got] == [("espacio_sin_empezar", "rojo")]
    assert "0% leído" in got[0].message
    core.material.mark_read(sid, doc.resource_id)
    assert spaces_only() == []  # progress != 0 -> omit


def test_space_boundary_data_gaps_and_past(tmp_path):
    core = _app(tmp_path)
    res = _task(core, "Lejos", date(2026, 9, 27), kind="examen_final")  # 3 days
    sid = _space_for(core, res)
    doc = core.material.add_document("subject:dd", b"x", "a.pdf")
    core.material.select_for_space(sid, doc.resource_id)
    assert core.notify.compute(TODAY)[0].level == "naranja"  # exactly 3
    t2 = _task(core, "Ayer", date(2026, 9, 23), kind="examen_final")
    sid2 = _space_for(core, t2)
    doc2 = core.material.add_document("subject:dd", b"y", "b.pdf")
    core.material.select_for_space(sid2, doc2.resource_id)
    kinds = [v.kind for v in core.notify.compute(TODAY)]
    assert "espacio_sin_empezar" in kinds  # only the 3-day one
    assert len([k for k in kinds if k == "espacio_sin_empezar"]) == 1


def test_subject_activity(tmp_path):
    core = _app(tmp_path)
    assert core.notify.compute(TODAY) == []  # no activity base -> omit
    s = core.academic.get_subject("subject:dd")
    core.svc.update_subject(replace(s, notes_updated_at="2026-09-01T10:00:00"))
    got = core.notify.compute(TODAY, abandoned_subject_days=14)
    assert [(v.kind, v.level) for v in got] == [("asignatura_inactiva", "gris")]
    assert "desde hace 23 días" in got[0].message
    assert core.notify.compute(TODAY, abandoned_subject_days=30) == []
    core.svc.update_subject(replace(s, notes_updated_at="2026-09-24T10:00:00"))
    assert core.notify.compute(TODAY) == []  # recent -> omit
    core.career.change_status("subject:dd", "superada")
    assert core.notify.compute(TODAY) == []  # not cursando -> omit


def test_activity_from_documents_and_reading(tmp_path):
    core = _app(tmp_path)
    doc = core.material.add_document("subject:dd", b"z", "c.pdf")
    core.material.record_reading(doc.resource_id, when="2026-09-20T10:00:00")
    got = core.notify.compute(date(2026, 10, 10), abandoned_subject_days=14)
    assert [v.kind for v in got] == ["asignatura_inactiva"]
    assert core.notify.last_subject_activity("subject:nope") is None


def test_order_is_deterministic(tmp_path):
    core = _app(tmp_path)
    _task(core, "Z gris", date(2026, 9, 20))  # wait: overdue -> rojo, not gris
    s = core.academic.get_subject("subject:dd")
    core.svc.update_subject(replace(s, notes_updated_at="2026-01-01T00:00:00"))
    _task(core, "A naranja", date(2026, 9, 29))  # 5 days, default 7
    first = core.notify.compute(TODAY)
    second = core.notify.compute(TODAY)
    assert [(v.level, v.due, v.entity) for v in first] == [
        (v.level, v.due, v.entity) for v in second]
    assert [v.level for v in first] == ["rojo", "naranja", "gris"]
    assert first[0].title == "Z gris"


def test_compute_never_calls_notify_table(tmp_path):
    core = _app(tmp_path)
    _task(core, "Atrasada", date(2026, 9, 20))
    core.notify.compute(TODAY)
    assert core.study.pending_notifications() == []


_SEED_SCRIPT = r"""
import json, os, sys
from datetime import date
from academic_core.application import AcademicApp
from academic_core.config import Settings
core = AcademicApp(Settings.load())
core.settings.ensure_dirs()
from academic_core.domain import entities as E
core.academic.add_university(E.University("university:u", "U"))
core.academic.add_degree(E.Degree("degree:g", "G", "university:u"))
core.academic.add_year(E.AcademicYear("year:y1", "Curso 1", "degree:g"))
core.academic.add_term(E.Term("term:q1", "Q1", "cuatrimestre", 1, "year:y1", state="actual"))
core.svc.create_subject("Diseno Digital", "term:q1", acronym="DD", credits=6.0)
core.career.change_status("subject:dd", "cursando")
core.calendar.create_task("B", date(2026, 9, 27), subject_id="subject:dd")
core.calendar.create_task("A", date(2026, 9, 20), subject_id="subject:dd")
got = core.notify.compute(date(2026, 9, 24))
print(json.dumps([(v.kind, v.level, v.title, v.message, str(v.due), v.entity)
                  for v in got], ensure_ascii=False))
"""


def test_compute_stable_across_hash_seeds(tmp_path):
    import os
    import subprocess
    import sys
    outs = []
    for seed in ("0", "11", "2024", "random"):
        env = dict(os.environ, PYTHONHASHSEED=seed,
                   PYTHONPATH=str(_SRC),
                   ACORE_DATA_DIR=str(tmp_path / f"seed-{seed}"))
        r = subprocess.run([sys.executable, "-c", _SEED_SCRIPT], env=env,
                           capture_output=True, text=True, timeout=300, check=True)
        outs.append(r.stdout.strip().splitlines()[-1])
    assert len(set(outs)) == 1
