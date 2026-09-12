"""Authoring UI: panel boots, template flow, block edit, undo/save (offscreen)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from academic_core.application import AcademicApp  # noqa: E402
from academic_core.config import Settings  # noqa: E402
from academic_core.ui.main_window import AcademicMainWindow  # noqa: E402


def _win(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("ACORE_DATA_DIR", str(tmp_path / "data"))
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    core.ensure_demo()
    win = AcademicMainWindow(core)
    qtbot.addWidget(win)
    return win, core


def test_authoring_tab_present_and_empty_state(qtbot, tmp_path, monkeypatch):
    win, _ = _win(qtbot, tmp_path, monkeypatch)
    assert win.tabs.count() == 6
    panel = win.authoring_panel
    assert panel.browser.count() == 0
    assert panel.status.text() == "No document open"


def test_create_edit_undo_save_flow(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    seen = []
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **k: seen.append(("info", a[1] if len(a) > 1 else "")))
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: seen.append(("warn", a[1] if len(a) > 1 else "")))
    win, core = _win(qtbot, tmp_path, monkeypatch)
    panel = win.authoring_panel
    sid = core.authoring.create_from_template("lecture-notes")
    panel.refresh_browser()
    assert panel.browser.count() == 1
    panel._open(sid)
    assert panel.outline.topLevelItemCount() == 6  # template blocks
    assert "rev 0" in panel.status.text()
    # edit first block (heading) via markdown-mediated apply
    panel.outline.setCurrentItem(panel.outline.topLevelItem(0))
    panel.block_edit.setPlainText("# Nou títol")
    panel._apply_block()
    assert "rev 1" in panel.status.text()
    assert "dirty" in panel.status.text()
    panel._hist("undo")
    assert "rev 2" in panel.status.text()
    panel._hist("redo")
    assert "Nou títol" in panel.status.text() or "rev 3" in panel.status.text()
    # validate + save through the panel
    panel._validate()  # no exception; dialog auto-accepted in offscreen? may block!
    panel._save()
    assert len(core.records.get(sid).versions) == 2
