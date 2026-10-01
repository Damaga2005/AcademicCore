# SPDX-License-Identifier: MIT
"""Home (UX IA 2026 §5.1) contracts: real data only, honest empty states."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

import pytest

NOON = datetime(2026, 10, 14, 12, 0, 0)  # naive => local time, deterministic


def _core(tmp_path):
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / "db")
    from academic_core.application import AcademicApp
    from academic_core.config import Settings
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    return core


def _with_subject(core, name="Circuitos I"):
    core.ensure_demo()
    term = core.queries.tree()[0]["degrees"][0]["years"][0]["terms"][0]["term"].stable_id
    return core.svc.create_subject(name, term, code="CIR1", acronym="C1", credits=6.0)


def _dash(qtbot, core, now=NOON):
    from academic_core.ui.dashboard import DashboardPanel
    dash = DashboardPanel(core, now=lambda: now)
    qtbot.addWidget(dash)
    return dash


def _rows(box):
    return [box.itemAt(i).widget() for i in range(box.count())]


# -- pure helpers -------------------------------------------------------------
@pytest.mark.parametrize("hour,text", [(0, "Buenos días"), (11, "Buenos días"),
                                       (12, "Buenas tardes"), (17, "Buenas tardes"),
                                       (18, "Buenas noches"), (23, "Buenas noches")])
def test_greeting_follows_the_hour(hour, text):
    from academic_core.ui.dashboard import greeting_for
    assert greeting_for(hour) == text


def test_relative_time_and_due_text():
    from academic_core.ui.dashboard import ago, due_text
    now = datetime(2026, 10, 14, 12, 0, 0, tzinfo=timezone.utc)
    iso = lambda **kw: (now - timedelta(**kw)).isoformat()
    assert ago(iso(seconds=10), now) == "ahora mismo"
    assert ago(iso(minutes=5), now) == "hace 5 min"
    assert ago(iso(hours=3), now) == "hace 3 h"
    assert ago(iso(hours=30), now) == "ayer"
    assert ago("not-a-date", now) == ""
    today = date(2026, 10, 14)
    assert due_text(today, today) == "hoy"
    assert due_text(today + timedelta(days=1), today) == "mañana"
    assert due_text(today + timedelta(days=5), today) == "en 5 días"
    assert due_text(today - timedelta(days=1), today) == "1 día de retraso"
    assert due_text(today - timedelta(days=3), today) == "3 días de retraso"


# -- header + honest empty states ------------------------------------------------
def test_greeting_uses_the_clock_not_a_constant(qtbot, tmp_path):
    core = _core(tmp_path)
    assert _dash(qtbot, core, datetime(2026, 10, 14, 9)).greeting_label.text() == "Buenos días"
    assert _dash(qtbot, core, datetime(2026, 10, 14, 20)).greeting_label.text() == "Buenas noches"


def test_first_run_offers_to_add_a_subject(qtbot, tmp_path):
    dash = _dash(qtbot, _core(tmp_path))
    got = []
    dash.navigate.connect(got.append)
    assert dash.continue_title.text() == "Crea tu primera asignatura"
    assert dash.continue_button.text() == "Añadir una asignatura"
    assert "Continúa donde lo dejaste" not in dash.greeting_sub.text()  # nothing to continue
    assert "Sin actividad reciente" in dash.recent_label.text()
    assert "Aún no hay asignaturas" in dash.deadlines_empty.text()
    dash.continue_button.click()
    assert got == ["learn/subject/summary"]


def test_subject_without_activity_says_nothing_to_continue(qtbot, tmp_path):
    core = _core(tmp_path)
    _with_subject(core)
    dash = _dash(qtbot, core)
    assert dash.continue_title.text() == "Nada que continuar todavía"
    assert dash.continue_button.text() == "Abrir Aprender"
    assert "Nada pendiente" in dash.deadlines_empty.text()
    assert "Sin actividad reciente" in dash.recent_label.text()


# -- continue + recent are real -----------------------------------------------------
def test_continue_is_the_last_opened_subject(qtbot, tmp_path):
    core = _core(tmp_path)
    subject = _with_subject(core)
    core.search_history.record_recent("asignatura", subject.stable_id, subject.name,
                                      "learn/subject/summary")
    dash = _dash(qtbot, core)
    got = []
    dash.open_subject.connect(got.append)
    assert dash.continue_title.text() == "Circuitos I"
    assert dash.continue_caption.text().startswith("Asignatura · abierta")
    assert dash.greeting_sub.text() == "Continúa donde lo dejaste."
    dash.continue_button.click()
    assert got == [subject.stable_id]


def test_continue_can_be_a_section_from_the_ui_log(qtbot, tmp_path):
    from academic_core.ui import state_store
    core = _core(tmp_path)
    state_store.push_recent_route("engineering/digital-logic", "Circuitos electrónicos › Lógica digital")
    dash = _dash(qtbot, core)
    got = []
    dash.navigate.connect(got.append)
    assert dash.continue_title.text() == "Lógica digital"
    assert dash.continue_caption.text().startswith("Circuitos electrónicos · abierta")
    dash.continue_button.click()
    assert got == ["engineering/digital-logic"]


def test_newest_activity_wins_and_recent_lists_the_rest(qtbot, tmp_path):
    from academic_core.ui import state_store
    core = _core(tmp_path)
    subject = _with_subject(core)
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(microsecond=0).isoformat()
    core.search_history.record_recent("asignatura", subject.stable_id, subject.name,
                                      "learn/subject/summary", accessed=old)
    state_store.push_recent_route("practice/exercises", "Practicar › Ejercicios")
    dash = _dash(qtbot, core, now=datetime.now().astimezone())
    assert dash.continue_title.text() == "Ejercicios"
    rows = _rows(dash.recent_box)
    assert [r.title_label.text() for r in rows] == ["Circuitos I"]
    assert rows[0].caption_label.text() == "hace 2 h"
    assert dash.recent_label.isHidden()


def test_unresolvable_recent_is_shown_but_not_clickable(qtbot, tmp_path):
    core = _core(tmp_path)
    core.search_history.record_recent("asignatura", "subject:x", "Álgebra", "subject:x")
    dash = _dash(qtbot, core)
    rows = _rows(dash.recent_box)
    assert [r.title_label.text() for r in rows] == ["Álgebra"]
    assert not rows[0].isEnabled()
    assert dash.continue_title.text() == "Crea tu primera asignatura"  # nothing real to continue


# -- coming up ------------------------------------------------------------------------
def test_deadlines_come_from_the_planning_queries(qtbot, tmp_path):
    core = _core(tmp_path)
    subject = _with_subject(core)
    today = NOON.date()
    core.svc.create_exam(core.planning, subject.stable_id, "Parcial",
                         day=today + timedelta(days=3), status="planned")
    core.svc.create_task(core.planning, core.study, subject.stable_id, "Entrega 1",
                         kind="entrega", day=today - timedelta(days=2))
    dash = _dash(qtbot, core)
    from PySide6.QtWidgets import QLabel
    rows = _rows(dash.deadlines_box)
    texts = [[lbl.text() for lbl in r.findChildren(QLabel)] for r in rows]
    assert [t[1] for t in texts] == ["Entrega 1", "Parcial"]  # overdue first
    assert "2 días de retraso" in texts[0] and "en 3 días" in texts[1]
    assert any(lbl.property("role") == "danger" for lbl in rows[0].findChildren(QLabel))
    assert not any(lbl.property("role") == "danger" for lbl in rows[1].findChildren(QLabel))
    assert dash.deadlines_empty.isHidden()


# -- tools ------------------------------------------------------------------------------
def test_tools_list_real_capabilities_and_navigate(qtbot, tmp_path):
    core = _core(tmp_path)
    dash = _dash(qtbot, core)
    assert set(dash._cards) == {"exercises", "sessions", "simulation", "lab", "logic", "aerospace",
                                "resources", "documents", "settings"}
    assert dash._cards["sessions"].caption_label.text() == "Importar un banco de preguntas"  # no bank yet, said plainly
    assert f"{len(list(core.exercises.library_keys()))} en la biblioteca" == \
        dash._cards["exercises"].caption_label.text()
    assert f"{len(tuple(core.digital.demos()))} circuitos de ejemplo" == \
        dash._cards["logic"].caption_label.text()
    got = []
    dash.navigate.connect(got.append)
    dash._cards["aerospace"].click()
    dash._cards["logic"].click()
    assert got == ["aerospace", "logic"]
    assert all(row.isEnabled() for row in dash._cards.values())


def test_no_gate_jargon_on_home(qtbot, tmp_path):
    from PySide6.QtWidgets import QLabel, QPushButton
    dash = _dash(qtbot, _core(tmp_path))
    text = " ".join(w.text() for w in dash.findChildren(QLabel))
    text += " ".join(w.text() for w in dash.findChildren(QPushButton))
    for jargon in ("F8-N", "F8-Q", "digital-trace", "GREELEC", "FTS5"):
        assert jargon not in text


# -- responsive ---------------------------------------------------------------------------
def test_columns_stack_when_narrow(qtbot, tmp_path):
    from PySide6.QtWidgets import QApplication, QBoxLayout
    dash = _dash(qtbot, _core(tmp_path))
    dash.show()
    dash.resize(1200, 800)
    QApplication.instance().processEvents()
    assert dash._columns.direction() == QBoxLayout.Direction.LeftToRight
    dash.resize(700, 900)
    QApplication.instance().processEvents()
    assert dash._columns.direction() == QBoxLayout.Direction.TopToBottom


# -- integration with the shell ---------------------------------------------------------------
def _win(qtbot, core):
    from academic_core.ui.main_window import AcademicMainWindow
    win = AcademicMainWindow(core)
    qtbot.addWidget(win)
    return win


def test_visiting_a_section_makes_it_continuable(qtbot, tmp_path):
    core = _core(tmp_path)
    win = _win(qtbot, core)
    assert win.dashboard_panel.continue_title.text() == "Crea tu primera asignatura"
    win.navigate_to("engineering/lab")
    win.navigate_to("home")
    assert win.dashboard_panel.continue_title.text() == "Laboratorio"
    win.dashboard_panel.continue_button.click()
    assert win.tabs.currentWidget() is win.virtual_lab_panel


def test_restoring_the_last_route_does_not_count_as_new_activity(qtbot, tmp_path):
    from academic_core.ui import state_store
    core = _core(tmp_path)
    win = _win(qtbot, core)
    win.navigate_to("engineering/lab")
    win.close()
    before = state_store.recent_routes()
    win2 = _win(qtbot, core)  # restores Lab
    assert win2.tabs.currentWidget() is win2.virtual_lab_panel
    assert state_store.recent_routes() == before


def test_opening_a_subject_records_it_and_home_can_reopen_it(qtbot, tmp_path):
    core = _core(tmp_path)
    subject = _with_subject(core)
    win = _win(qtbot, core)
    win._refresh_tree()
    assert win._select_subject(subject.stable_id)
    win.navigate_to("learn/subject/grades")
    assert [r.ref for r in core.search_history.list_recents()] == [subject.stable_id]
    win.navigate_to("home")
    assert win.dashboard_panel.continue_title.text() == "Circuitos I"
    win.tree.clearSelection()
    win.dashboard_panel.continue_button.click()
    assert win._route.id == "learn/subject/summary"
    assert win.topbar.context_chip.text() == "Circuitos I"
