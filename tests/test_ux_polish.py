"""UX 2026 final-audit corrections (docs/ux/UX-REVIEW-2026-FINAL.md): F-01..F-05, F-07..F-11, F-13..F-18."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(autouse=True)
def _no_motion(monkeypatch):
    """Static checks: no fades in flight. Scoped to this file so other tests still see real motion."""
    monkeypatch.setenv("ACORE_REDUCE_MOTION", "1")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHeaderView, QLineEdit, QListWidget, QTextEdit, QTreeWidget, QWidget

from academic_core.ui import theme


def _win(qtbot, tmp_path, monkeypatch, subject=True):
    monkeypatch.setenv("ACORE_DATA_DIR", str(tmp_path / "db"))
    from academic_core.application import AcademicApp
    from academic_core.config import Settings
    from academic_core.ui.main_window import AcademicMainWindow
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    win = AcademicMainWindow(core)
    qtbot.addWidget(win)
    if subject:
        core.svc.create_subject("Circuitos I", "term:demo-c1", acronym="C1")
        win._refresh_tree()
        for item in win.tree.findItems("Circuitos I", Qt.MatchFlag.MatchRecursive):
            win.tree.setCurrentItem(item)
    return win, core


def test_subject_pages_are_structured_not_debug_dumps(qtbot, tmp_path, monkeypatch):
    from academic_core.ui.workspace import Metric, Panel
    win, _ = _win(qtbot, tmp_path, monkeypatch)
    for view in (win.tab_overview, win.tab_activities, win.tab_grades, win.tab_planning):
        assert view.findChildren(Panel) or view.findChildren(Metric)
        text = view.toPlainText()
        for raw in ("== ", "grade=", "evaluated=", "state=sin_", "subject:", "refs:"):
            assert raw not in text, (view.accessibleName(), raw)
        assert view.focusPolicy() == Qt.FocusPolicy.StrongFocus  # reachable by keyboard
    assert "Sin evaluar" in win.tab_grades.toPlainText()  # the Spanish domain code, translated
    win.show()
    win.navigate_to("learn/subject/summary")
    assert win.actions_bar.isHidden()  # nothing to add from a summary
    win.navigate_to("learn/subject/activities")
    assert not win.actions_bar.isHidden()


def test_no_subject_says_what_to_do(qtbot, tmp_path, monkeypatch):
    win, _ = _win(qtbot, tmp_path, monkeypatch, subject=False)
    win.tree.clearSelection()
    win._refresh_detail()
    assert "Elige una asignatura" in win.tab_overview.toPlainText()


def test_documents_fit_a_normal_window(qtbot, tmp_path, monkeypatch):
    win, _ = _win(qtbot, tmp_path, monkeypatch, subject=False)
    assert win.authoring_panel.minimumSizeHint().width() < 900  # was 1164: horizontal scroll at 1250


def test_settings_is_grouped_and_has_no_internal_jargon(qtbot, tmp_path, monkeypatch):
    from academic_core.ui.workspace import Panel
    win, _ = _win(qtbot, tmp_path, monkeypatch, subject=False)
    titles = {p.title_label.text() for p in win.settings_panel.findChildren(Panel)}
    assert {"Apariencia", "Datos", "Acerca de", "Diagnóstico"} <= titles
    about = dict(win.about_list.rows)
    assert about["Versión"].startswith("v") and about["Licencia"] == "MIT"
    assert win.appearance_box.maximumWidth() == 220
    assert "GREELEC" in win.config_label.text()  # the explicit limitation stays visible


def test_library_hides_the_backend_url_and_says_when_empty(qtbot, tmp_path, monkeypatch):
    win, _ = _win(qtbot, tmp_path, monkeypatch, subject=False)
    assert "127.0.0.1" not in win.stirling_label.text() and "NOT_INSTALLED" not in win.stirling_label.text()
    win._refresh_resources()
    assert not win.res_empty.isHidden() and win.res_list.isHidden()


def test_every_control_has_an_accessible_name(qtbot, tmp_path, monkeypatch):
    win, _ = _win(qtbot, tmp_path, monkeypatch)
    missing = []
    for route in ("learn/library", "learn/documents", "settings", "practice/sessions", "engineering/circuits"):
        win.navigate_to(route)
        page = win.tabs.currentWidget()
        for w in page.findChildren(QWidget):
            if isinstance(w.parent(), QComboBox) or w.objectName().startswith("qt_"):
                continue
            if isinstance(w, (QLineEdit, QComboBox, QTextEdit, QListWidget, QTreeWidget)) and not (
                    w.accessibleName() or w.toolTip()):
                missing.append((route, type(w).__name__))
    assert missing == []


def test_empty_lists_and_tables_explain_themselves(qtbot, tmp_path, monkeypatch):
    win, _ = _win(qtbot, tmp_path, monkeypatch, subject=False)
    eng = win.engineering_panel
    assert "Aún no hay proyectos" in eng.projects._hint and "proyecto" in eng.circuits._hint
    assert eng.calc_table.horizontalHeader().sectionResizeMode(0) == QHeaderView.ResizeMode.Stretch
    assert win.practice_panel.plan_snapshot.rows[0][1].startswith("Crea un plan")


def test_lab_notice_takes_no_room_when_empty(qtbot, tmp_path, monkeypatch):
    win, _ = _win(qtbot, tmp_path, monkeypatch, subject=False)
    kit = win.virtual_lab_panel.kit
    assert kit.notice.isHidden()
    kit.notice.setText("hello")
    assert not kit.notice.isHidden()
    kit.notice.setText("")
    assert kit.notice.isHidden()


def _lum(h):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _contrast(a, b):
    hi, lo = max(_lum(a), _lum(b)), min(_lum(a), _lum(b))
    return (hi + 0.05) / (lo + 0.05)


def test_theme_draws_its_own_arrows_and_tick_and_fixes_contrast(qtbot):
    for t in (theme.LIGHT, theme.DARK):
        assert _contrast(t.secondary, t.hover) >= 4.5, "secondary text on hover"
        assert _contrast(t.secondary, t.ground) >= 3.0 and _contrast(t.secondary, t.card) >= 3.0, "scrollbar thumb"
        css = theme.stylesheet(t)
        assert "QComboBox::down-arrow" in css and "academiccore-glyphs" in css
        assert "QTreeWidget::branch:selected" in css and t.selection in css and "QSpinBox::up-arrow" in css
        assert "QCheckBox::indicator:checked" in css and "check-" in css


def test_mastery_is_a_bar_and_the_sessions_list_elides(qtbot, tmp_path, monkeypatch):
    win, _ = _win(qtbot, tmp_path, monkeypatch, subject=False)
    p = win.practice_panel
    assert p.question_list.textElideMode() == Qt.TextElideMode.ElideRight
    assert p.concept_table.itemDelegateForColumn(1).__class__.__name__ == "MasteryBarDelegate"
