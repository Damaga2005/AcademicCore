# SPDX-License-Identifier: MIT
"""Engineering module index contracts: real modules only, no invented capabilities."""

from __future__ import annotations

import os


def _core(tmp_path):
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / "db")
    from academic_core.application import AcademicApp
    from academic_core.config import Settings
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    return core


def test_modules_come_from_real_services(qtbot, tmp_path):
    from academic_core.ui.modules import module_index
    core = _core(tmp_path)
    mods = module_index(core)
    by_id = {m["id"]: m for m in mods}
    assert set(by_id) == {"digital-logic", "electronics", "aerospace"}
    assert by_id["digital-logic"]["entries"] == [d.key for d in core.digital.demos()]
    assert by_id["electronics"]["entries"] == list(core.exercises.library_keys())
    assert all(len(m["entries"]) > 0 for m in mods)


def test_modules_dialog_navigates(qtbot, tmp_path):
    from academic_core.ui.main_window import AcademicMainWindow
    from academic_core.ui.modules import ModulesDialog
    core = _core(tmp_path)
    win = AcademicMainWindow(core)
    qtbot.addWidget(win)
    dlg = ModulesDialog(core, win.navigate_to)
    qtbot.addWidget(dlg)
    assert dlg.entry_list.count() > 0
    dlg.navigate("digital-logic")
    assert win.tabs.currentWidget() is win.logic_analyzer_panel
