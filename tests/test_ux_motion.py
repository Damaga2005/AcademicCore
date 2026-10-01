"""UX 2026 prompt 10: functional motion and honest states."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QLabel, QPushButton, QWidget

from academic_core.ui import motion
from academic_core.ui.state import UiState, set_busy
from academic_core.ui.theme import apply_status_style


@pytest.fixture()
def motion_on(monkeypatch):
    monkeypatch.delenv("ACORE_REDUCE_MOTION", raising=False)
    monkeypatch.setattr(motion, "reduced_motion", lambda: False)


def test_durations_stay_inside_the_motion_budget():
    assert 100 <= motion.FAST <= motion.BASE <= motion.SLOW <= 180


def test_reduced_motion_removes_every_animation(qtbot, monkeypatch):
    monkeypatch.setenv("ACORE_REDUCE_MOTION", "1")
    w = QWidget()
    qtbot.addWidget(w)
    assert motion.fade_in(w) is None and motion.flash(w) is None and w.graphicsEffect() is None
    assert motion.pop_in(w).duration() == 0


def test_fade_in_is_one_shot_and_cleans_up(qtbot, motion_on):
    w = QWidget()
    qtbot.addWidget(w)
    anim = motion.fade_in(w)
    assert anim is not None and anim.duration() == motion.SLOW and anim.loopCount() == 1
    assert w.graphicsEffect() is not None
    qtbot.waitUntil(lambda: w.graphicsEffect() is None, timeout=2000)  # no idle effect left behind


def test_status_pill_flashes_only_when_the_state_changes(qtbot, motion_on):
    lab = QLabel("LISTO")
    qtbot.addWidget(lab)
    lab.show()
    apply_status_style(lab, UiState.IDLE)
    assert not hasattr(lab, "_fade_anim")  # first paint is not a change
    apply_status_style(lab, UiState.IDLE)
    assert not hasattr(lab, "_fade_anim")  # same state: nothing to say
    apply_status_style(lab, UiState.SUCCESS)
    assert hasattr(lab, "_fade_anim") and lab._fade_anim.duration() == motion.BASE


def test_running_locks_only_what_it_disabled(qtbot):
    a, b = QPushButton("run"), QPushButton("replay")
    b.setEnabled(False)  # disabled for its own reason: aún no hay nada que repetir
    set_busy(UiState.RUNNING, a, b)
    assert not a.isEnabled() and not b.isEnabled()
    set_busy(UiState.SUCCESS, a, b)
    assert a.isEnabled() and not b.isEnabled()


def test_a_run_cannot_be_started_twice(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("ACORE_DATA_DIR", str(tmp_path / "db"))
    from academic_core.application import AcademicApp
    from academic_core.config import Settings
    from academic_core.ui.exercises import ExercisePanel
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    panel = ExercisePanel(core)
    qtbot.addWidget(panel)
    panel._set_state(UiState.RUNNING, "CALCULANDO…")
    assert not panel.btn_run.isEnabled() and not panel.btn_explain.isEnabled()
    panel._set_state(UiState.SUCCESS, "ÉXITO")
    assert panel.btn_run.isEnabled() and panel.btn_explain.isEnabled()


def test_changing_page_eases_in_the_new_context(qtbot, tmp_path, monkeypatch, motion_on):
    monkeypatch.setenv("ACORE_DATA_DIR", str(tmp_path / "db"))
    from academic_core.application import AcademicApp
    from academic_core.config import Settings
    from academic_core.ui.main_window import AcademicMainWindow
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    win = AcademicMainWindow(core)
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    win.navigate_to("engineering/circuits")
    page = win.tabs.currentWidget()
    assert hasattr(page, "_fade_anim")
