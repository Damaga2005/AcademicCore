# SPDX-License-Identifier: MIT
"""Subject pages for Learn (Summary, Activities, Grades, Planning) — UX 2026 final audit F-01.

Presentation only: the same data the old text dumps showed, shaped with the workspace kit. Each view is a
keyboard-focusable scroll area (arrow keys scroll it) and keeps a plain-text rendition in ``toPlainText()``
for copy and for tests, so nothing is only visible as pixels.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from academic_core.ui.workspace import EmptyState, KeyValueList, Metric, Panel

GRADE_STATE = {"aprobada": "Passed", "suspendida": "Failed", "en_progreso": "In progress",
               "sin_evaluar": "Not evaluated"}


def human(state) -> str:
    """Domain codes are Spanish snake_case; the page speaks the interface's language."""
    text = str(state or "")
    return GRADE_STATE.get(text, text.replace("_", " ").capitalize() if text else "—")


class SubjectView(QScrollArea):
    """Base: a scroll area holding either an empty state or the panels a subclass builds."""

    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # reachable by keyboard: arrows scroll
        self.setAccessibleName(name)
        self._text = ""
        self._body = QWidget()
        self._lay = QVBoxLayout(self._body)
        self._lay.setContentsMargins(0, 4, 8, 8)
        self._lay.setSpacing(12)
        self.setWidget(self._body)

    def _clear(self) -> None:
        while self._lay.count():
            item = self._lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()

    def show_none(self) -> None:
        self._clear()
        self._text = "Select a subject in the tree"
        empty = EmptyState("Select a subject", "Choose one in the academic tree to see it here.")
        self._lay.addWidget(empty)
        self._lay.addStretch(1)

    def toPlainText(self) -> str:  # noqa: N802 — mirrors QTextEdit, which this replaced
        return self._text

    def _finish(self, lines: list[str]) -> None:
        self._lay.addStretch(1)
        self._text = "\n".join(lines)


def _metrics(items: list[Metric]) -> QWidget:
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(12)
    for m in items:
        lay.addWidget(m, 1)
    return row


class OverviewView(SubjectView):
    open_sessions = Signal()

    def __init__(self, parent=None):
        super().__init__("Subject summary", parent)

    def show_subject(self, *, name: str, code: str, topics: int, refs: int, staff: str, prerequisites: str,
                     practice: tuple | None) -> None:
        """``practice`` is (mastery ratio, observations) or None when there are no attempts yet."""
        self._clear()
        title = f"{name} ({code})" if code else name
        facts = Panel("Subject")
        kv = KeyValueList()
        kv.set_rows([("Name", title), ("Topics", str(topics)), ("Resources", str(refs)),
                     ("Teaching staff", staff or "None assigned"),
                     ("Prerequisites", prerequisites or "None")])
        facts.add(kv)
        self._lay.addWidget(facts)
        prac = Panel("Practice")
        lines = [f"Subject: {title}", f"Topics: {topics}", f"Resources: {refs}",
                 f"Teaching staff: {staff or 'None assigned'}", f"Prerequisites: {prerequisites or 'None'}"]
        if practice is None:
            note = QLabel("No attempts yet. Answer a few questions and your mastery of this subject appears here.")
            note.setObjectName("CardStatus")
            note.setWordWrap(True)
            prac.add(note)
            btn = QPushButton("Open Sessions")
            btn.setProperty("class", "subtle")
            btn.clicked.connect(self.open_sessions)
            prac.actions.addWidget(btn)
            lines.append("Practice: no attempts yet (Practice > Sessions)")
        else:
            ratio, n = practice
            m = Metric("Mastery", f"over {n} observation{'s' if n != 1 else ''}")
            m.set_value(f"{ratio:.0%}")
            prac.add(m)
            lines.append(f"Practice: mastery {ratio:.0%} over {n} observations")
        self._lay.addWidget(prac)
        self._finish(lines)


class ActivitiesView(SubjectView):
    KINDS = ("assignments", "exams", "projects", "labs", "tasks", "topics")

    def __init__(self, parent=None):
        super().__init__("Subject activities", parent)

    def show_activities(self, groups: dict) -> None:
        """``groups``: kind -> [(title, state)]."""
        self._clear()
        tiles = []
        lines = []
        for kind in self.KINDS:
            rows = groups.get(kind, [])
            m = Metric(kind.capitalize())
            m.set_value(str(len(rows)))
            tiles.append(m)
            lines.append(f"{kind.capitalize()}: {len(rows)}")
        self._lay.addWidget(_metrics(tiles))
        if not any(groups.get(k) for k in self.KINDS):
            self._lay.addWidget(EmptyState("No activities yet",
                                           "Use New to add a topic, assignment, task or exam."))
        for kind in self.KINDS:
            rows = groups.get(kind, [])
            if not rows:
                continue
            panel = Panel(kind.capitalize())
            kv = KeyValueList()
            kv.set_rows([(title, human(state)) for title, state in rows])
            panel.add(kv)
            self._lay.addWidget(panel)
            lines += [f"• {title} [{human(state)}]" for title, state in rows]
        self._finish(lines)


class GradesView(SubjectView):
    def __init__(self, parent=None):
        super().__init__("Subject grades", parent)

    def show_grades(self, *, grade, evaluated: bool, state: str, ratio, evaluated_weight, total_weight,
                    gradebook_state: str, complete: bool) -> None:
        self._clear()
        final = Metric("Final grade", "/ 10")
        final.set_value("—" if grade is None else str(grade))
        weight = Metric("Evaluated weight")
        weight.set_value(f"{evaluated_weight} / {total_weight}")
        self._lay.addWidget(_metrics([final, weight]))
        panel = Panel("Detail")
        kv = KeyValueList()
        rows = [("Scheme result", human(state)), ("Fully evaluated", "Yes" if evaluated else "No"),
                ("Gradebook result", human(gradebook_state)),
                ("Gradebook ratio", "—" if ratio is None else str(ratio)),
                ("Complete", "Yes" if complete else "No")]
        kv.set_rows(rows)
        panel.add(kv)
        self._lay.addWidget(panel)
        self._finish([f"Final grade: {'—' if grade is None else grade}", f"Scheme result: {human(state)}",
                      f"Evaluated weight: {evaluated_weight} / {total_weight}",
                      f"Gradebook result: {human(gradebook_state)}", f"Complete: {'Yes' if complete else 'No'}"])


class PlanningView(SubjectView):
    def __init__(self, parent=None):
        super().__init__("Subject planning", parent)

    def show_planning(self, upcoming: list, overdue: list) -> None:
        """Each row is (title, kind, due)."""
        self._clear()
        grid = QGridLayout()
        grid.setSpacing(12)
        lines = []
        for col, (title, rows, empty) in enumerate((("Upcoming", upcoming, "Nothing due soon."),
                                                    ("Overdue", overdue, "Nothing overdue."))):
            panel = Panel(title)
            if rows:
                kv = KeyValueList()
                kv.set_rows([(t, f"{human(kind)} · {due}") for t, kind, due in rows])
                panel.add(kv)
            else:
                note = QLabel(empty)
                note.setObjectName("CardStatus")
                panel.add(note)
            grid.addWidget(panel, 0, col)
            grid.setColumnStretch(col, 1)
            lines.append(f"{title}: " + (", ".join(f"{t} ({due})" for t, _k, due in rows) if rows else empty))
        holder = QWidget()
        holder.setLayout(grid)
        grid.setContentsMargins(0, 0, 0, 0)
        self._lay.addWidget(holder)
        self._finish(lines)
