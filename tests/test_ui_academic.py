"""Academic UI: tree navigation, subject workspace, CRUD smoke (offscreen)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402

from academic_core.application import AcademicApp  # noqa: E402
from academic_core.config import Settings  # noqa: E402
from academic_core.ui.main_window import AcademicMainWindow  # noqa: E402

MATCH = Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive


def _win(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("ACORE_DATA_DIR", str(tmp_path / "data"))
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    core.ensure_demo()
    win = AcademicMainWindow(core)
    qtbot.addWidget(win)
    return win, core


def test_tree_navigation_and_subject_detail(qtbot, tmp_path, monkeypatch):
    win, core = _win(qtbot, tmp_path, monkeypatch)
    assert win.tree.topLevelItemCount() == 1
    uni = win.tree.topLevelItem(0)
    assert uni.text(0) == "Universidad Demo"
    # drill to the demo term and add a subject through the service
    term_id = "term:demo-c1"
    core.svc.create_subject("Fisica", term_id, acronym="FIS")
    win._refresh_tree()
    found = win.tree.findItems("Fisica", MATCH)  # recursive match
    assert found and win._index[id(found[0])] == ("subject", "subject:fis")
    win.tree.setCurrentItem(found[0])
    assert "subject:fis" in win.tab_overview.toPlainText()


def test_grades_and_planning_tabs(qtbot, tmp_path, monkeypatch):
    win, core = _win(qtbot, tmp_path, monkeypatch)
    from decimal import Decimal
    from academic_core.domain import results as R
    core.svc.create_subject("Mates", "term:demo-c1", acronym="MAT")
    core.results.record("subject:mat", R.Grade("p", "8", R.N_10, Decimal(100)))
    win._refresh_tree()
    found = win.tree.findItems("Mates", MATCH)
    win.tree.setCurrentItem(found[0])
    assert "aprobada" in win.tab_grades.toPlainText()
    assert "complete=True" in win.tab_grades.toPlainText()


def test_facade_is_only_wiring():
    import academic_core.ui.main_window as m
    import inspect
    src = inspect.getsource(m)
    assert "import sqlite3" not in src and "from academic_core.infrastructure" not in src
