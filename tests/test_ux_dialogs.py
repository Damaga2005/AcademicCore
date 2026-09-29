"""UX 2026 prompt 9: contextual dialogs (title, context, primary/secondary, Escape, focus, keyboard)."""

from __future__ import annotations

import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit

from academic_core.ui import dialogs

UI = Path(__file__).resolve().parents[1] / "src" / "academic_core" / "ui"


def _shown(qtbot, build):
    dlg = build()
    qtbot.addWidget(dlg)
    dlg.show()
    qtbot.waitExposed(dlg)
    return dlg


def test_frame_has_title_context_and_two_actions(qtbot):
    dlg = _shown(qtbot, lambda: dialogs.DialogFrame(None, "Delete term", "Removes its subjects.",
                                                    primary="Delete", secondary="Keep"))
    assert dlg.windowTitle() == "Delete term" and dlg.title_label.text() == "Delete term"
    assert not dlg.context_label.isHidden() and dlg.btn_primary.text() == "Delete"
    assert dlg.btn_secondary.text() == "Keep" and dlg.btn_primary.isDefault()


def test_escape_cancels_and_enter_accepts(qtbot):
    dlg = _shown(qtbot, lambda: dialogs.DialogFrame(None, "X"))
    QTest.keyClick(dlg, Qt.Key.Key_Escape)
    assert dlg.result() == QDialog.DialogCode.Rejected
    dlg = _shown(qtbot, lambda: dialogs.DialogFrame(None, "X"))
    QTest.keyClick(dlg.btn_primary, Qt.Key.Key_Return)
    assert dlg.result() == QDialog.DialogCode.Accepted


def test_initial_focus_is_primary_and_destructive_starts_on_cancel(qtbot):
    safe = _shown(qtbot, lambda: dialogs.DialogFrame(None, "X"))
    assert safe.focusWidget() is safe.btn_primary
    risky = _shown(qtbot, lambda: dialogs.DialogFrame(None, "X", destructive=True))
    assert risky.focusWidget() is risky.btn_secondary and risky.btn_primary.property("class") == "danger"


def test_confirm_returns_the_choice(qtbot):
    def press(key):
        def go():
            dlg = QApplication.activeModalWidget()
            QTest.keyClick(dlg.focusWidget(), key)
        QTimer.singleShot(50, go)
    press(Qt.Key.Key_Space)  # focus starts on the primary button
    assert dialogs.confirm(None, "Go?", confirm_text="Go") is True
    press(Qt.Key.Key_Space)  # destructive: focus starts on Cancel, so Space cancels
    assert dialogs.confirm(None, "Delete?", destructive=True) is False


def test_message_splits_the_safe_message_from_the_next_step(qtbot):
    dlg = _shown(qtbot, lambda: dialogs.MessageDialog(None, "warning", "Import", "It failed.\n\nTry another file."))
    assert dlg.message_label.text() == "It failed." and dlg.action_label.text() == "Try another file."
    assert dlg.level_label.property("state") == "WARNING" and dlg.focusWidget() is dlg.btn_primary
    plain = _shown(qtbot, lambda: dialogs.MessageDialog(None, "critical", "X", "Boom"))
    assert plain.action_label.isHidden() and plain.level_label.property("state") == "ERROR"


def test_prompt_form_focuses_first_field_labels_it_and_returns_values(qtbot):
    def fill():
        dlg = QApplication.activeModalWidget()
        assert isinstance(dlg.focusWidget(), QLineEdit) and dlg.title_label.text() == "New university"
        assert dlg.btn_primary.text() == "Create"
        dlg.focusWidget().setText("UPM")
        QTest.keyClick(dlg.focusWidget(), Qt.Key.Key_Return)  # Enter submits from a field
    QTimer.singleShot(50, fill)
    assert dialogs.prompt_form(None, "University", [("name", "Name", "", "text")]) == {"name": "UPM"}
    QTimer.singleShot(50, lambda: QTest.keyClick(QApplication.activeModalWidget(), Qt.Key.Key_Escape))
    assert dialogs.prompt_form(None, "University", [("name", "Name", "", "text")]) is None


def test_every_form_the_app_opens_has_copy():
    used = set()
    for py in UI.glob("*.py"):
        used |= set(re.findall(r'prompt_form\(self, "([^"]+)"', py.read_text(encoding="utf-8")))
    assert used and used <= set(dialogs.FORM_COPY), used - set(dialogs.FORM_COPY)


def test_no_generic_message_boxes_and_no_raw_exception_text_in_the_ui():
    for py in UI.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        if py.name != "dialogs.py":
            assert "QMessageBox" not in text, py.name
        assert "{type(e).__name__}: {e}" not in text, py.name


def test_modules_dialog_is_keyboard_complete(qtbot, tmp_path, monkeypatch):
    from academic_core.application import AcademicApp
    from academic_core.config import Settings
    from academic_core.ui.modules import ModulesDialog
    monkeypatch.setenv("ACORE_DATA_DIR", str(tmp_path / "db"))
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    opened = []
    dlg = _shown(qtbot, lambda: ModulesDialog(core, opened.append))
    assert dlg.focusWidget() is dlg.entry_list and dlg.btn_open.isDefault()
    QTest.keyClick(dlg, Qt.Key.Key_Escape)
    assert dlg.result() == QDialog.DialogCode.Rejected
