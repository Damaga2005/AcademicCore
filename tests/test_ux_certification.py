"""UX 2026 certification walk (prompt 13): one window, every area, real services, no mocks of the core.

It is an integration check of the redesigned product: navigation, the five functional areas the gate names
(modules, labs, exercises, tutor, engineering, settings) and persistence across close and reopen. The
details of each screen are pinned by the test_ux_* files; this walks them together.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt

from academic_core.ui import dialogs, routes, theme


@pytest.fixture()
def product(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("ACORE_DATA_DIR", str(tmp_path / "db"))
    monkeypatch.setenv("ACORE_REDUCE_MOTION", "1")
    from academic_core.application import AcademicApp
    from academic_core.config import Settings
    from academic_core.ui.main_window import AcademicMainWindow
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    core.ensure_demo()
    shown = []
    monkeypatch.setattr(dialogs, "show_message",
                        lambda parent, level, title, body: shown.append((level, title, body)))
    win = AcademicMainWindow(core)
    qtbot.addWidget(win)
    win.show()
    win.shown = shown
    return win, core


def _wait(qtbot, panel):
    qtbot.waitUntil(lambda: panel.state.value != "RUNNING", timeout=90000)


def test_every_route_opens_its_page_without_an_error(product):
    win, _ = product
    for route in routes.ROUTES:
        win.navigate_to(route.id)
        assert win._route.id == route.id
        assert win.tabs.currentWidget() is win._pages[route.target], route.id
    assert win.shown == []


def test_exercise_runs_and_a_bad_input_fails_safely(product, qtbot):
    win, _ = product
    win.navigate_to("practice/exercises")
    ex = win.exercise_panel
    ex.selector.setCurrentText("ohm-i")
    ex.inputs.setPlainText("V=5 V; R=1000 ohm")
    ex.btn_run.click()
    _wait(qtbot, ex)
    assert ex.state.value == "SUCCESS" and ex.output.toPlainText().strip()
    ex.inputs.setPlainText("this is not an input")
    ex.btn_run.click()
    _wait(qtbot, ex) if ex.state.value == "RUNNING" else None
    assert win.shown, "the error must reach the person"
    _level, _title, body = win.shown[-1]
    assert "Traceback" not in body and "Error(" not in body  # D2: no raw exception text


def test_virtual_lab_and_analysis_run_and_are_reproducible(product, qtbot):
    win, _ = product
    win.navigate_to("engineering/lab")
    lab = win.virtual_lab_panel
    lab.btn_new.click()
    lab.btn_run.click()
    _wait(qtbot, lab)
    assert lab.state.value == "SUCCESS", (lab.status.text(), win.shown)
    lab.btn_replay.click()
    qtbot.waitUntil(lambda: lab.state.value != "RUNNING", timeout=60000)
    assert lab.state.value == "SUCCESS"


def test_digital_logic_captures(product, qtbot):
    win, _ = product
    win.navigate_to("engineering/digital-logic")
    la = win.logic_analyzer_panel
    la.btn_run.click()
    qtbot.waitUntil(lambda: la.state.value != "RUNNING", timeout=60000)
    assert la.state.value in ("SUCCESS", "WARNING"), (la.status.text(), win.shown)


def test_aerospace_computes_a_real_orbit(product):
    win, _ = product
    win.navigate_to("engineering/aerospace")
    orbit = win.engineering_panel.orbit_panel
    orbit.altitude_km.setText("35786")
    orbit.recompute()
    from decimal import Decimal
    assert orbit.last["h_m"] == Decimal(35786000)


def test_practice_loop_and_tutor_with_the_model_off(product):
    win, core = product
    win.navigate_to("practice/sessions")
    panel = win.practice_panel
    panel.btn_sample.click()
    qs = core.practice.questions("bank:sample")
    assert len(qs) == 4 and not core.practice.llm_available()
    attempt = core.practice.start_attempt([q.question_id for q in qs])
    result = core.practice.submit(attempt, {qs[0].question_id: {"selected": [1]}})
    assert result.mastery_updated and result.passed is False  # 1 of 4 answered
    hint = core.practice.hint(result.session_id, qs[1].question_id)
    assert hint.status == "verified" and hint.provider_error == "LLM_UNAVAILABLE"  # deterministic, no model
    win.navigate_to("learn/mastery")
    panel.refresh()
    assert win.shown == []


def test_settings_theme_switch_applies_to_the_whole_window(product):
    win, _ = product
    win.navigate_to("settings")
    win._set_appearance("dark")
    assert theme.current_tokens() == theme.DARK
    win._set_appearance("light")
    assert theme.current_tokens() == theme.LIGHT


def test_state_survives_close_and_reopen(product, qtbot):
    win, core = product
    core.svc.create_subject("Circuitos I", "term:demo-c1", acronym="C1")
    win._refresh_tree()
    for item in win.tree.findItems("Circuitos I", Qt.MatchFlag.MatchRecursive):
        win.tree.setCurrentItem(item)
    win.navigate_to("engineering/lab")
    subject = win._subject_id()
    win.close()
    from academic_core.ui.main_window import AcademicMainWindow
    again = AcademicMainWindow(core)
    qtbot.addWidget(again)
    again.show()
    assert again._route.id == "engineering/lab"
    assert again._subject_id() == subject
    # the data itself is on disk: a second facade over the same folder sees the subject
    from academic_core.application import AcademicApp
    from academic_core.config import Settings
    assert AcademicApp(Settings.load()).academic.get_subject(subject) is not None
