"""UX 2026 prompt 11: Windows integration (identity, sizing, single window, close/reopen)."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect

from academic_core.ui import windows

ROOT = Path(__file__).resolve().parents[1]


class _Screen:
    def __init__(self, w, h):
        self._r = QRect(0, 0, w, h)

    def availableGeometry(self):
        return self._r


class _Win:
    def __init__(self, w, h):
        self._s, self.min, self.size = _Screen(w, h), None, None

    def screen(self):
        return self._s

    def setMinimumSize(self, w, h):
        self.min = (w, h)

    def resize(self, w, h):
        self.size = (w, h)


def test_window_icon_is_a_bundled_resource_identical_to_the_installer_icon(qtbot):
    assert not windows.app_icon().isNull()
    bundled = ROOT / "src" / "academic_core" / "resources" / "academicore.ico"
    assert bundled.read_bytes() == (ROOT / "packaging" / "windows" / "academicore.ico").read_bytes()
    assert "academic_core/resources" in (ROOT / "packaging" / "windows" / "academicore.spec").read_text()


def test_window_yields_to_a_small_screen(qtbot):
    for w, h in ((960, 520), (1092, 614), (1920, 1040)):  # 200 %, 125 % of 1366x768, 100 % of 1080p
        win = _Win(w, h)
        windows.fit_to_screen(win)
        assert win.min[0] <= w and win.min[1] <= h and win.size[0] <= w and win.size[1] <= h
    big = _Win(2560, 1400)
    windows.fit_to_screen(big)
    assert big.min == (900, 600) and big.size == (1250, 780)  # nothing changes where it already fits


def test_second_launch_wakes_the_first_and_exits(qtbot):
    key = f"acore-test-{uuid.uuid4().hex}"
    first, second = windows.SingleInstance(key), windows.SingleInstance(key)
    try:
        assert first.claim() is True
        with qtbot.waitSignal(first.activated, timeout=3000):
            assert second.claim() is False
    finally:
        first.release()
    third = windows.SingleInstance(key)  # after the first closes the next launch starts normally
    try:
        assert third.claim() is True
    finally:
        third.release()


def test_taskbar_identity_never_raises():
    windows.set_app_user_model_id()


def _core(tmp_path, monkeypatch):
    monkeypatch.setenv("ACORE_DATA_DIR", str(tmp_path / "db"))
    from academic_core.application import AcademicApp
    from academic_core.config import Settings
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    return core


def test_window_geometry_and_place_survive_close_and_reopen(qtbot, tmp_path, monkeypatch):
    from academic_core.ui.main_window import AcademicMainWindow
    core = _core(tmp_path, monkeypatch)
    win = AcademicMainWindow(core)
    qtbot.addWidget(win)
    win.show()
    win.resize(820, 640)  # the offscreen screen is only 800x600: stay inside what fits
    size = (win.width(), win.height())
    win.navigate_to("engineering/circuits")
    win.close()
    again = AcademicMainWindow(core)
    qtbot.addWidget(again)
    again.show()
    assert again.height() == size[1] and again.width() <= min(size[0], again.screen().availableGeometry().width())
    assert again._route.id == "engineering/circuits"


def test_full_screen_is_reachable_from_the_keyboard(qtbot, tmp_path, monkeypatch):
    from academic_core.ui.main_window import AcademicMainWindow
    win = AcademicMainWindow(_core(tmp_path, monkeypatch))
    qtbot.addWidget(win)
    win.show()
    assert win.fullscreen_action.shortcut().toString() == "F11"
    win.fullscreen_action.setChecked(True)
    assert win.isFullScreen()
    win.fullscreen_action.setChecked(False)
    assert not win.isFullScreen()


def test_installer_registers_start_menu_uninstall_and_keeps_user_data():
    nsi = (ROOT / "packaging" / "windows" / "installer.nsi").read_text()
    assert "$SMPROGRAMS" in nsi and "UninstallString" in nsi and "DisplayIcon" in nsi
    uninstall = nsi.split('Section "Uninstall"')[1]
    assert "LOCALAPPDATA" not in uninstall  # uninstalling never deletes the student's data


def test_narrow_window_collapses_the_rail_and_a_manual_choice_is_never_fought(qtbot, tmp_path, monkeypatch):
    from academic_core.ui.main_window import AcademicMainWindow
    win = AcademicMainWindow(_core(tmp_path, monkeypatch))
    qtbot.addWidget(win)
    win.show()
    win.NARROW_WIDTH = 10_000  # any width counts as narrow (the offscreen screen is only 800 px)
    win._narrow = None
    win._adapt_rail()
    assert win.rail.collapsed and win._rail_pref is False  # automatic: not the user's choice
    assert win.context_panel.width() == 220
    win.NARROW_WIDTH = 100  # widened again: back to what the user had
    win._adapt_rail()
    assert not win.rail.collapsed and win.context_panel.width() == 280
    win.rail.set_collapsed(True, animate=False)  # the user collapses it on purpose
    assert win._rail_pref is True
    win._adapt_rail()  # same width class: nothing overrides them
    assert win.rail.collapsed
