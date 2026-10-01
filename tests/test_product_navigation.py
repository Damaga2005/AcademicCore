# SPDX-License-Identifier: MIT
"""Product navigation contracts: grouped Go-menu over existing tabs.

The 13-tab structure is pinned by UI tests; this shell only ADDS a
grouped navigation layer (Home/Learn/Practice/Engineering/Settings)
that maps onto the existing _navigate() keys. No tab is touched.
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


def test_go_menu_exists_with_groups(qtbot, tmp_path):
    win = _win(qtbot, tmp_path)
    names = [a.text() for a in win.menuBar().actions()]
    assert "Ir" in names
    actions = [a.text() for a in win.go_menu.actions() if not a.isSeparator()]
    for expected in ("Inicio", "Aprender", "Practicar", "Circuitos electrónicos", "Ajustes"):
        assert any(expected in t for t in actions), actions


def test_go_menu_navigates_without_touching_tabs(qtbot, tmp_path):
    win = _win(qtbot, tmp_path)
    before = win.tabs.count()
    win.navigate_to("simulation")
    assert win.tabs.currentWidget() is win.simulation_panel
    assert win.tabs.count() == before == 14
    win.navigate_to("lab")
    assert win.tabs.currentWidget() is win.virtual_lab_panel
