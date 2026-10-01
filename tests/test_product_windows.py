# SPDX-License-Identifier: MIT
"""Windows shell contracts: resize robustness, keyboard, focus.

Pins verified behavior: panels stay non-degenerate across window sizes,
Ctrl+K is bound and enabled, search autofocuses, Go menu is complete.
"""

from __future__ import annotations

import os


def _win(qtbot, tmp_path):
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / "db")
    from academic_core.application import AcademicApp
    from academic_core.config import Settings
    from academic_core.ui.main_window import AcademicMainWindow
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    win = AcademicMainWindow(core)
    qtbot.addWidget(win)
    return win


def test_panels_survive_resizes(qtbot, tmp_path):
    from PySide6.QtWidgets import QApplication
    win = _win(qtbot, tmp_path)
    win.show()
    QApplication.instance().processEvents()
    for size in ((800, 600), (1250, 780), (1600, 900), (1920, 1080)):
        win.resize(*size)
        QApplication.instance().processEvents()
        for attr in ("tree", "tabs", "dashboard_panel", "simulation_panel",
                     "virtual_lab_panel", "logic_analyzer_panel", "exercise_panel"):
            w = getattr(win, attr)
            assert w.size().width() >= 10 and w.size().height() >= 10, (size, attr)


def test_ctrl_k_bound_and_search_autofocuses(qtbot, tmp_path):
    from PySide6.QtWidgets import QApplication
    from academic_core.ui.search import SearchDialog
    win = _win(qtbot, tmp_path)
    assert win._search_shortcut.key().toString() == "Ctrl+K"
    assert win._search_shortcut.isEnabled()
    win.show()
    QApplication.instance().processEvents()
    dlg = SearchDialog(win.app, win)
    qtbot.addWidget(dlg)
    dlg.show()
    QApplication.instance().processEvents()
    assert dlg.search_box.hasFocus()


def test_go_menu_complete(qtbot, tmp_path):
    win = _win(qtbot, tmp_path)
    actions = [a.text() for a in win.go_menu.actions() if not a.isSeparator()]
    assert len(actions) == 10
    assert any("Módulos" in t for t in actions)
