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

GRADE_STATE = {"aprobada": "Aprobada", "suspendida": "Suspendida", "en_progreso": "En curso",
               "sin_evaluar": "Sin evaluar"}


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
        self._text = "Elige una asignatura en el árbol"
        empty = EmptyState("Elige una asignatura", "Elígela en el árbol académico para verla aquí.")
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
        super().__init__("Resumen de la asignatura", parent)

    def show_subject(self, *, name: str, code: str, topics: int, refs: int, staff: str, prerequisites: str,
                     practice: tuple | None) -> None:
        """``practice`` is (mastery ratio, observations) or None when there are no attempts yet."""
        self._clear()
        title = f"{name} ({code})" if code else name
        facts = Panel("Asignatura")
        kv = KeyValueList()
        kv.set_rows([("Nombre", title), ("Temas", str(topics)), ("Recursos", str(refs)),
                     ("Profesorado", staff or "Sin asignar"),
                     ("Requisitos previos", prerequisites or "Ninguno")])
        facts.add(kv)
        self._lay.addWidget(facts)
        prac = Panel("Práctica")
        lines = [f"Asignatura: {title}", f"Temas: {topics}", f"Recursos: {refs}",
                 f"Profesorado: {staff or 'Sin asignar'}", f"Requisitos previos: {prerequisites or 'Ninguno'}"]
        if practice is None:
            note = QLabel("Aún no hay intentos. Responde unas preguntas y aquí aparece tu dominio de esta asignatura.")
            note.setObjectName("CardStatus")
            note.setWordWrap(True)
            prac.add(note)
            btn = QPushButton("Abrir Sesiones")
            btn.setProperty("class", "subtle")
            btn.clicked.connect(self.open_sessions)
            prac.actions.addWidget(btn)
            lines.append("Práctica: aún sin intentos (Practicar > Sesiones)")
        else:
            ratio, n = practice
            m = Metric("Dominio", f"en {n} observación{'es' if n != 1 else ''}")
            m.set_value(f"{ratio:.0%}")
            prac.add(m)
            lines.append(f"Práctica: dominio {ratio:.0%} en {n} observaciones")
        self._lay.addWidget(prac)
        self._finish(lines)


class ActivitiesView(SubjectView):
    KINDS = ("assignments", "exams", "projects", "labs", "tasks", "topics")
    LABEL = {"assignments": "Entregas", "exams": "Exámenes", "projects": "Proyectos",
             "labs": "Laboratorios", "tasks": "Tareas", "topics": "Temas"}

    def __init__(self, parent=None):
        super().__init__("Actividades de la asignatura", parent)

    def show_activities(self, groups: dict) -> None:
        """``groups``: kind -> [(title, state)]."""
        self._clear()
        tiles = []
        lines = []
        for kind in self.KINDS:
            rows = groups.get(kind, [])
            m = Metric(self.LABEL[kind])
            m.set_value(str(len(rows)))
            tiles.append(m)
            lines.append(f"{self.LABEL[kind]}: {len(rows)}")
        self._lay.addWidget(_metrics(tiles))
        if not any(groups.get(k) for k in self.KINDS):
            self._lay.addWidget(EmptyState("Aún no hay actividades",
                                           "Usa Nuevo para añadir un tema, una entrega, una tarea o un examen."))
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
        super().__init__("Notas de la asignatura", parent)

    def show_grades(self, *, grade, evaluated: bool, state: str, ratio, evaluated_weight, total_weight,
                    gradebook_state: str, complete: bool) -> None:
        self._clear()
        final = Metric("Nota final", "/ 10")
        final.set_value("—" if grade is None else str(grade))
        weight = Metric("Peso evaluado")
        weight.set_value(f"{evaluated_weight} / {total_weight}")
        self._lay.addWidget(_metrics([final, weight]))
        panel = Panel("Detalle")
        kv = KeyValueList()
        rows = [("Resultado del esquema", human(state)), ("Totalmente evaluada", "Sí" if evaluated else "No"),
                ("Resultado del cuaderno", human(gradebook_state)),
                ("Proporción del cuaderno", "—" if ratio is None else str(ratio)),
                ("Completa", "Sí" if complete else "No")]
        kv.set_rows(rows)
        panel.add(kv)
        self._lay.addWidget(panel)
        self._finish([f"Nota final: {'—' if grade is None else grade}", f"Resultado del esquema: {human(state)}",
                      f"Peso evaluado: {evaluated_weight} / {total_weight}",
                      f"Resultado del cuaderno: {human(gradebook_state)}", f"Completa: {'Sí' if complete else 'No'}"])


class PlanningView(SubjectView):
    def __init__(self, parent=None):
        super().__init__("Planificación de la asignatura", parent)

    def show_planning(self, upcoming: list, overdue: list) -> None:
        """Each row is (title, kind, due)."""
        self._clear()
        grid = QGridLayout()
        grid.setSpacing(12)
        lines = []
        for col, (title, rows, empty) in enumerate((("Próximos", upcoming, "Nada próximo."),
                                                    ("Vencidos", overdue, "Nada vencido."))):
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
