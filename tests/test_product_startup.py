# SPDX-License-Identifier: MIT
"""Product startup contracts: splash content + first-run flag.

Flag storage is injected (QSettings), so tests never touch the real
registry/config location.
"""

from __future__ import annotations

from PySide6.QtCore import Qt


def _settings(tmp_path):
    from PySide6.QtCore import QSettings
    return QSettings(str(tmp_path / "test.ini"), QSettings.Format.IniFormat)


def test_first_run_flag_roundtrip(qtbot, tmp_path):
    from academic_core.ui.startup import is_first_run, mark_seen
    s = _settings(tmp_path)
    assert is_first_run(s) is True
    mark_seen(s)
    assert is_first_run(s) is False


def test_first_run_dialog_accepts(qtbot, tmp_path):
    from academic_core.ui.startup import FirstRunDialog, is_first_run
    s = _settings(tmp_path)
    dlg = FirstRunDialog(s)
    assert "AcademicCore" in dlg.windowTitle()
    qtbot.mouseClick(dlg.continue_button, Qt.MouseButton.LeftButton)
    assert dlg.result() != 0
    assert is_first_run(s) is False


def test_splash_shows_version(qtbot):
    from academic_core import __version__
    from academic_core.ui.startup import make_splash
    from PySide6.QtWidgets import QApplication
    splash = make_splash(QApplication.instance())
    assert __version__ in splash.message()
    splash.close()
