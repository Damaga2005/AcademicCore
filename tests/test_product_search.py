# SPDX-License-Identifier: MIT
"""Global search (Ctrl+K) contracts: reuses UnifiedSearchService, no second engine."""

from __future__ import annotations

import os


def _core(tmp_path):
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / "db")
    from academic_core.application import AcademicApp
    from academic_core.config import Settings
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    core.ensure_demo()
    return core


def test_short_query_returns_nothing(qtbot, tmp_path):
    from academic_core.ui.search import SearchDialog
    core = _core(tmp_path)
    dlg = SearchDialog(core)
    qtbot.addWidget(dlg)
    assert dlg.run_search("x") == []


def test_demo_note_found(qtbot, tmp_path):
    from academic_core.domain import planning as PL
    from academic_core.ui.search import SearchDialog
    core = _core(tmp_path)
    core.personal.add_note(PL.QuickNote("note:demo-1", "demo note body", "2026-01-01"))
    dlg = SearchDialog(core)
    qtbot.addWidget(dlg)
    hits = dlg.run_search("demo")
    assert any(h.kind == "note" for h in hits)


def test_dialog_lists_results(qtbot, tmp_path):
    from academic_core.domain import planning as PL
    from academic_core.ui.search import SearchDialog
    core = _core(tmp_path)
    core.personal.add_note(PL.QuickNote("note:demo-1", "demo note body", "2026-01-01"))
    dlg = SearchDialog(core)
    qtbot.addWidget(dlg)
    dlg.search_box.setText("demo")
    assert dlg.result_list.count() >= 1
