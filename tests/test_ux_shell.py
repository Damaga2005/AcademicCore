# SPDX-License-Identifier: MIT
"""Product shell contracts (UX IA 2026): rail, top bar, sections, history, state."""

from __future__ import annotations

import os
import re
from pathlib import Path


def _core(tmp_path):
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / "db")
    from academic_core.application import AcademicApp
    from academic_core.config import Settings
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    return core


def _win(qtbot, core):
    from academic_core.ui.main_window import AcademicMainWindow
    win = AcademicMainWindow(core)
    qtbot.addWidget(win)
    return win


def _pick_subject(win):
    from PySide6.QtWidgets import QTreeWidgetItemIterator
    term = next(sid for kind, sid in win._index.values() if kind == "term")
    win.app.svc.create_subject("Circuitos I", term, code="CIR1", acronym="C1", credits=6.0)
    win._refresh_tree()
    it = QTreeWidgetItemIterator(win.tree)
    while it.value():
        item = it.value()
        if win._index.get(id(item), ("", ""))[0] == "subject":
            win.tree.setCurrentItem(item)
            return item
        it += 1
    return None


def test_pages_stay_pinned_and_tab_strip_is_hidden(qtbot, tmp_path):
    win = _win(qtbot, _core(tmp_path))
    assert win.tabs.count() == 13
    assert win.tabs.tabBar().isHidden()
    assert win.tabs.currentWidget() is win.dashboard_panel  # starts on Home


def test_every_route_shows_its_page(qtbot, tmp_path):
    from academic_core.ui import routes
    win = _win(qtbot, _core(tmp_path))
    for r in routes.ROUTES:
        win.navigate_to(r.id)
        assert win.tabs.currentWidget() is win._pages[r.target], r.id
        assert win.rail.buttons[r.area].isChecked(), r.id
    win.navigate_to("does-not-exist")  # ignored, no crash
    assert win.tabs.currentWidget() is win.settings_panel


def test_aerospace_module_lands_on_orbit_not_simulation(qtbot, tmp_path):
    from academic_core.ui.modules import ModulesDialog
    core = _core(tmp_path)
    win = _win(qtbot, core)
    dlg = ModulesDialog(core, win.navigate_to)
    qtbot.addWidget(dlg)
    dlg.navigate("aerospace")
    assert win.tabs.currentWidget() is win.engineering_panel
    assert win.tabs.currentWidget() is not win.simulation_panel
    assert win._route.id == "engineering/aerospace"


def test_sections_context_panel_and_actions_follow_the_area(qtbot, tmp_path):
    win = _win(qtbot, _core(tmp_path))
    win.show()
    win.navigate_to("home")
    assert win.section_bar.isHidden() and win.context_panel.isHidden() and win.actions_bar.isHidden()
    win.navigate_to("learn/subject/grades")
    assert len(win.section_bar.buttons) == 6 and win.section_bar.buttons["learn/subject/grades"].isChecked()
    assert win.context_panel.isVisible() and win.actions_bar.isVisible()
    win.navigate_to("learn/library")
    assert win.context_panel.isVisible() and win.actions_bar.isHidden()
    win.navigate_to("engineering/lab")
    assert len(win.section_bar.buttons) == 5 and win.context_panel.isHidden()
    win.navigate_to("practice/exercises")
    assert win.section_bar.isHidden()  # one section: no bar


def test_rail_returns_to_last_visited_section(qtbot, tmp_path):
    win = _win(qtbot, _core(tmp_path))
    win.navigate_to("engineering/digital-logic")
    win.navigate_to("home")
    win.rail.buttons["engineering"].click()
    assert win._route.id == "engineering/digital-logic"


def test_history_back_and_forward(qtbot, tmp_path):
    win = _win(qtbot, _core(tmp_path))
    win.navigate_to("engineering/lab")
    win.navigate_to("settings")
    win.go_back()
    assert win.tabs.currentWidget() is win.virtual_lab_panel
    win.go_forward()
    assert win.tabs.currentWidget() is win.settings_panel
    win.go_back(); win.go_back(); win.go_back()  # past the start: stays on Home
    assert win.tabs.currentWidget() is win.dashboard_panel


def test_subject_context_chip_and_actions(qtbot, tmp_path):
    win = _win(qtbot, _core(tmp_path))
    assert win.topbar.context_chip.text() == "No subject"
    assert not any(b.isEnabled() for b in win._subject_buttons)
    item = _pick_subject(win)
    assert item is not None
    assert win.topbar.context_chip.text() == item.text(0)
    assert all(b.isEnabled() for b in win._subject_buttons)
    win.navigate_to("learn/subject/grades")
    assert win.topbar.crumb_texts == ["Learn", item.text(0), "Grades"]


def test_keyboard_shortcuts_are_bound(qtbot, tmp_path):
    from PySide6.QtGui import QShortcut
    win = _win(qtbot, _core(tmp_path))
    keys = {sc.key().toString() for sc in win.findChildren(QShortcut)}
    assert {"Ctrl+K", "Ctrl+1", "Ctrl+2", "Ctrl+3", "Ctrl+4", "Ctrl+5", "Alt+Left",
            "Alt+Right", "Ctrl+,"} <= keys


def test_route_and_rail_state_persist(qtbot, tmp_path):
    core = _core(tmp_path)
    win = _win(qtbot, core)
    win.navigate_to("engineering/lab")
    win.rail.set_collapsed(True, animate=False)
    win.close()
    win2 = _win(qtbot, core)
    assert win2.tabs.currentWidget() is win2.virtual_lab_panel
    assert win2.rail.collapsed and win2.rail.width() == 64


def test_unknown_saved_route_falls_back_to_home(qtbot, tmp_path):
    from academic_core.ui.main_window import shell_settings
    core = _core(tmp_path)
    shell_settings().setValue("shell/route", "learn/removed-section")
    win = _win(qtbot, core)
    assert win.tabs.currentWidget() is win.dashboard_panel


def test_palette_goto_rows_and_selected_enter(qtbot, tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from academic_core.ui import routes
    from academic_core.ui.search import SearchDialog
    core = _core(tmp_path)
    dlg = SearchDialog(core, goto=routes.goto_entries())
    qtbot.addWidget(dlg)
    dlg.show()
    dlg.search_box.setText("digital")
    assert dlg.selection() == ("route", "engineering/digital-logic")
    dlg.search_box.setText("aero")
    assert dlg.selection() == ("route", "engineering/aerospace")
    dlg.search_box.setText("go to")
    first = dlg.result_list.currentRow()
    QTest.keyClick(dlg.search_box, Qt.Key.Key_Down)
    assert dlg.result_list.currentRow() == first + 1  # Down moves the selection
    chosen = dlg.selection()
    dlg.accept()
    assert dlg.selection() == chosen  # Enter keeps the selected row, not the first


def test_palette_navigates_the_window(qtbot, tmp_path, monkeypatch):
    from academic_core.ui import search
    win = _win(qtbot, _core(tmp_path))

    class Fake(search.SearchDialog):
        def exec(self):
            self.search_box.setText("lab")
            return 1

    monkeypatch.setattr(search, "SearchDialog", Fake)
    win._open_search()
    assert win.tabs.currentWidget() is win.virtual_lab_panel


def test_theme_pairs_meet_contrast_and_no_stray_hex():
    """DESIGN-SYSTEM-2026 §3.5: text/accent pairs pass WCAG AA in both modes."""
    from academic_core.ui.theme import DARK, LIGHT

    def lum(h):
        h = h.lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
        f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)

    def ratio(a, b):
        hi, lo = sorted((lum(a), lum(b)), reverse=True)
        return (hi + 0.05) / (lo + 0.05)

    for t in (LIGHT, DARK):
        for fg, bg in ((t.ink, t.ground), (t.ink, t.card), (t.secondary, t.ground),
                       (t.secondary, t.card), (t.secondary, t.field), (t.accent_text, t.card),
                       (t.accent_ink, t.accent), (t.success_ink, t.success_bg),
                       (t.warning_ink, t.warning_bg), (t.error_ink, t.error_bg),
                       (t.info_ink, t.info_bg), (t.idle_ink, t.idle_bg)):
            if bg.startswith("#"):
                assert ratio(fg, bg) >= 4.5, (t.mode, fg, bg)
        assert ratio(t.border_control, t.card) >= 3.0, t.mode  # WCAG 1.4.11
    ui = Path(__file__).resolve().parents[1] / "src" / "academic_core" / "ui"
    stray = [f.name for f in ui.glob("*.py")
             if f.name not in ("theme.py", "startup.py")  # splash is brand art, fixed on purpose
             and re.search(r"#[0-9A-Fa-f]{6}\b", f.read_text(encoding="utf-8"))]
    assert not stray, stray
