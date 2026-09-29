"""Contextual dialogs (UX 2026, prompt 9): one frame, no generic message boxes.

Every dialog built here has a title, one line of context, minimal content, a primary and a
secondary action, Escape to cancel, an explicit initial focus and full keyboard operation
(Enter = primary, Tab order = fields then buttons). ``show_message`` is the single place a
notice reaches the screen (errors.py routes through it), so tests replace one function.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)

from academic_core.ui.theme import apply_status_style

# level -> (pill state, pill text). "question" has no pill: it is the user's own action.
_LEVELS = {"critical": ("ERROR", "Error"), "warning": ("WARNING", "Needs attention"),
           "information": ("SUCCESS", "Done")}


class DialogFrame(QDialog):
    """Title + context on top, content in the middle, secondary/primary buttons at the bottom."""

    def __init__(self, parent, title: str, context: str = "", primary: str = "OK",
                 secondary: str | None = "Cancel", destructive: bool = False, min_width: int = 420):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(min_width)
        self.setModal(True)
        self.setSizeGripEnabled(False)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("DialogTitle")
        self.title_label.setWordWrap(True)
        root.addWidget(self.title_label)
        self.context_label = QLabel(context)
        self.context_label.setObjectName("DialogContext")
        self.context_label.setWordWrap(True)
        self.context_label.setVisible(bool(context))
        root.addWidget(self.context_label)
        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        root.addLayout(self.body)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch(1)
        self.btn_secondary = None
        if secondary:
            self.btn_secondary = QPushButton(secondary)
            self.btn_secondary.clicked.connect(self.reject)
            row.addWidget(self.btn_secondary)
        self.btn_primary = QPushButton(primary)
        self.btn_primary.setProperty("class", "danger" if destructive else "primary")
        self.btn_primary.setDefault(True)
        self.btn_primary.setAutoDefault(True)
        self.btn_primary.clicked.connect(self.accept)
        row.addWidget(self.btn_primary)
        root.addLayout(row)
        # A destructive action must not be one accidental Enter away.
        self.initial_focus: QWidget = self.btn_secondary if (destructive and self.btn_secondary) \
            else self.btn_primary

    def showEvent(self, event) -> None:  # noqa: N802 — Qt override
        from academic_core.ui.motion import pop_in
        super().showEvent(event)
        self.initial_focus.setFocus()
        pop_in(self)


class MessageDialog(DialogFrame):
    """A notice: level pill, the safe message, one acknowledging action."""

    def __init__(self, parent, level: str, title: str, message: str):
        super().__init__(parent, title, primary="OK", secondary=None)
        state, text = _LEVELS.get(level, _LEVELS["information"])
        self.level_label = QLabel(text)
        apply_status_style(self.level_label, state)
        self.body.addWidget(self.level_label, 0, Qt.AlignmentFlag.AlignLeft)
        lead, _sep, rest = message.partition("\n\n")  # UiError: safe message, then what to do next
        self.message_label = QLabel(lead)
        self.message_label.setWordWrap(True)
        self.message_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.body.addWidget(self.message_label)
        self.action_label = QLabel(rest)
        self.action_label.setObjectName("CardStatus")
        self.action_label.setWordWrap(True)
        self.action_label.setVisible(bool(rest))
        self.body.addWidget(self.action_label)
        self.initial_focus = self.btn_primary


def show_message(parent, level: str, title: str, message: str) -> None:
    """The one path by which a notice is shown. ``level``: information | warning | critical."""
    MessageDialog(parent, level, title, message).exec()


def information(parent, title: str, message: str) -> None:
    show_message(parent, "information", title, message)


def warning(parent, title: str, message: str) -> None:
    show_message(parent, "warning", title, message)


def critical(parent, title: str, message: str) -> None:
    show_message(parent, "critical", title, message)


def confirm(parent, text: str, *, title: str = "Confirm", confirm_text: str = "Confirm",
            cancel_text: str = "Cancel", destructive: bool = False, context: str = "") -> bool:
    """Ask before acting. Name the action on the button; destructive ones start on Cancel."""
    dlg = DialogFrame(parent, title, context, primary=confirm_text, secondary=cancel_text,
                      destructive=destructive)
    label = QLabel(text)
    label.setWordWrap(True)
    dlg.body.addWidget(label)
    return dlg.exec() == QDialog.DialogCode.Accepted


# Copy for the forms the app opens: window title, one line of context, primary action.
FORM_COPY = {
    "University": ("New university", "Top of your academic tree.", "Create"),
    "Degree": ("New degree", "Added under the selected university.", "Create"),
    "Academic year": ("New academic year", "Added under the selected degree.", "Create"),
    "Term": ("New term", "Added under the selected year.", "Create"),
    "Subject": ("New subject", "Added under the selected term.", "Create"),
    "Topic": ("New topic", "Added to the selected subject.", "Add topic"),
    "Assignment": ("New assignment", "Added to the selected subject.", "Add assignment"),
    "Task": ("New task", "Added to the selected subject.", "Add task"),
    "Exam": ("New exam", "Added to the selected subject.", "Add exam"),
    "Grade": ("Record a grade", "Recorded for the selected subject.", "Record"),
    "New document": ("New document", "Start from a template; you can edit everything afterwards.", "Create"),
    "Academic link": ("Link to your studies", "Connect this document to a subject, topic or task.", "Link"),
    "Lifecycle": ("Change document state", "Moves the document through draft, review and publication.", "Apply"),
    "Project": ("New project", "Holds the circuits you draw.", "Create"),
    "Circuit": ("New circuit", "Added to the selected project.", "Create"),
    "Component": ("Add component", "Placed in the selected circuit.", "Add"),
    "Calculate": ("Calculate", "Solves the equation with the inputs you give.", "Calculate"),
}


def prompt_form(parent, title: str, fields: list, *, context: str = "", primary: str = "") -> dict | None:
    """fields: [(key, label, default, kind)] kind=text|float|int|date|combo(list[(label,data)]).
    Returns {key: value} with dates as date|None, or None when cancelled."""
    from PySide6.QtCore import QDate
    from PySide6.QtWidgets import QDateEdit
    copy = FORM_COPY.get(title, (title, "", "Save"))
    dlg = DialogFrame(parent, copy[0], context or copy[1], primary=primary or copy[2])
    form = QFormLayout()
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
    form.setVerticalSpacing(10)
    dlg.body.addLayout(form)
    widgets = {}
    first = None
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
        w.setAccessibleName(label)
        cap = QLabel(label)
        cap.setBuddy(w)  # the label names the field for screen readers and click-to-focus
        form.addRow(cap, w)
        widgets[key] = (w, kind)
        first = first or w
    if first is not None:
        dlg.initial_focus = first  # start typing straight away; Enter still submits
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
