"""Small Qt dialogs (Phase 4): generic form prompt + confirm. No logic."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLineEdit,
    QMessageBox, QSpinBox,
)


def prompt_form(parent, title: str, fields: list) -> dict | None:
    """fields: [(key, label, default, kind)] kind=text|float|int|date|combo(list[(label,data)]).
    Returns {key: value} with dates as date|None, or None when cancelled."""
    from PySide6.QtWidgets import QDateEdit
    from PySide6.QtCore import QDate
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    form = QFormLayout(dlg)
    widgets = {}
    for key, label, default, kind in fields:
        if kind == "combo":
            w = QComboBox()
            for lab, data in default:
                w.addItem(lab, data)
        elif kind == "date":
            w = QDateEdit()
            w.setCalendarPopup(True)
            w.setSpecialValueText("(none)")
            if default:
                w.setDate(QDate(default.year, default.month, default.day))
            else:
                w.clearMinimumDate()
                w.setDate(w.minimumDate())
        elif kind == "int":
            w = QSpinBox()
            w.setRange(-1000000, 1000000)
            w.setValue(int(default or 0))
        else:
            w = QLineEdit(str(default or ""))
        form.addRow(label, w)
        widgets[key] = (w, kind)
    btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                            | QDialogButtonBox.StandardButton.Cancel)
    btns.accepted.connect(dlg.accept)
    btns.rejected.connect(dlg.reject)
    form.addRow(btns)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None
    out = {}
    for key, (w, kind) in widgets.items():
        if kind == "combo":
            out[key] = w.currentData()
        elif kind == "date":
            qd = w.date()
            out[key] = None if qd == w.minimumDate() else qd.toPython()
        elif kind == "int":
            out[key] = w.value()
        else:
            out[key] = w.text()
    return out


def confirm(parent, text: str) -> bool:
    return QMessageBox.question(parent, "Confirm", text) == QMessageBox.StandardButton.Yes
