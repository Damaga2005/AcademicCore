# SPDX-License-Identifier: MIT
"""Practice page (UX 2026 prompt 8): sessions, plan and mastery in one flow.

    Problem -> your work -> feedback -> result -> plan -> mastery

The page hosts three workspaces (routes ``practice/sessions``,
``practice/plan`` and ``learn/mastery``) over ``AcademicApp.practice``.
Grading, mastery, planning and tutoring are the certified F9-F12 engines;
this file only collects answers and shows results. The tutor is part of the
question flow, not a chat: it answers about one corrected question and every
reply arrives as an F12 ``VerifiedResponse`` (validated, checked, never
authority). Correct answers are never sent to this layer.
"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton, QRadioButton, QSpinBox,
    QHeaderView, QStackedWidget, QStyledItemDelegate, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from academic_core.ui.errors import show_ui_error
from academic_core.ui.state import UiState
from academic_core.ui.theme import apply_status_style
from academic_core.ui.workspace import EmptyState, KeyValueList, Metric, Notice, Panel

RATIONALE_TEXT = {
    "LOW_MASTERY": "tu dominio de este concepto es bajo",
    "DIFFICULTY_FIT": "la dificultad encaja con tu nivel",
    "CONCEPT_RELEVANCE": "relevante para la asignatura elegida",
    "RECENT_ERROR": "fallaste este concepto hace poco",
    "PREREQUISITE_OK": "los requisitos previos están cubiertos",
    "PREREQUISITE_UNMET": "aún no has practicado una asignatura previa",
    "REPETITION_AVOIDED": "no se repite de intentos anteriores",
    "DIVERSITY": "aporta variedad al conjunto",
    "UNMAPPED": "aún no está vinculada a un concepto",
    "NO_ELIGIBLE_EXERCISES": "ninguna pregunta cumple ahora los criterios",
}
REASON_TEXT = {
    "selected_match": "coincide con las opciones correctas", "selected_mismatch": "no coincide con las opciones correctas",
    "boolean_match": "coincide con la respuesta correcta", "boolean_mismatch": "no coincide con la respuesta correcta",
    "tolerance_match": "dentro de la tolerancia", "symbolic_equivalent": "expresión equivalente",
    "text_match": "coincide con el texto esperado", "omitted": "sin responder",
    "needs_review": "no se puede corregir automáticamente; se conserva como evidencia",
}
REJECTED_TEXT = {
    "INVALID_LLM_OUTPUT": "La respuesta del tutor no era válida, así que no se muestra nada de ella.",
    "SCHEMA_VALIDATION_FAILED": "La respuesta del tutor no pasó la validación, así que no se muestra nada de ella.",
    "SAFETY_REJECTED": "Las reglas de seguridad bloquearon la respuesta del tutor, así que no se muestra nada de ella.",
}
QTYPE_LABEL = {"multiple_choice": "Opción múltiple", "true_false": "Verdadero / falso", "numeric": "Numérica",
               "symbolic": "Simbólica", "short_text": "Texto corto", "structured": "Estructurada",
               "circuit": "Magnitudes del circuito"}
HINT_STATE = {"verified": UiState.SUCCESS, "unverified": UiState.WARNING, "rejected": UiState.ERROR}


def verdict_label(is_correct, reason: str) -> str:
    if is_correct is True:
        return "Correcta"
    if is_correct is False:
        return "Incorrecta"
    return "Sin responder" if reason == "omitted" else "Requiere revisión"


class AnswerForm(QWidget):
    """The answer inputs for one question, by type. ``payload()`` is the F9 payload."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self._question = None
        self._widgets: dict = {}
        self._editable = True

    def _clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
            elif item.layout() is not None:
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget() is not None:
                        sub.widget().deleteLater()
        self._widgets = {}

    def _line(self, placeholder: str = "", name: str = "") -> QLineEdit:
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        edit.setAccessibleName(name or placeholder or "Respuesta")
        return edit

    def set_question(self, q, saved: dict | None = None) -> None:
        self._clear()
        self._question = q
        w = self._widgets
        t = q.qtype
        if t == "multiple_choice":
            hint = QLabel("Marca todas las opciones que correspondan.")
            hint.setObjectName("CardStatus")
            self._layout.addWidget(hint)
            w["options"] = []
            for i, text in enumerate(q.options):
                box = QCheckBox(text)
                w["options"].append(box)
                self._layout.addWidget(box)
        elif t == "true_false":
            w["true"], w["false"] = QRadioButton("Verdadero"), QRadioButton("Falso")
            self._layout.addWidget(w["true"])
            self._layout.addWidget(w["false"])
        elif t == "numeric":
            row = QHBoxLayout()
            w["value"] = self._line("value", "Valor")
            w["unit"] = self._line("unit", "Unidad")
            w["unit"].setText(q.unit)
            w["unit"].setMaximumWidth(110)
            row.addWidget(w["value"], 1)
            row.addWidget(w["unit"])
            self._layout.addLayout(row)
        elif t == "symbolic":
            w["expression"] = self._line("expresión, p. ej. 2*x + 1", "Expresión")
            self._layout.addWidget(w["expression"])
        elif t == "short_text":
            w["text"] = self._line("tu respuesta", "Texto de la respuesta")
            self._layout.addWidget(w["text"])
        elif t == "structured":
            form = QFormLayout()
            w["fields"] = {}
            for name, kind in q.fields:
                if kind == "boolean":
                    w["fields"][name] = (kind, QCheckBox())
                else:
                    edit = self._line(kind, name)
                    w["fields"][name] = (kind, edit)
                form.addRow(name, w["fields"][name][1])
            self._layout.addLayout(form)
        elif t == "circuit":
            form = QFormLayout()
            w["quantities"] = {}
            for name, unit in q.fields:
                row = QHBoxLayout()
                value, u = self._line("value", f"{name} valor"), self._line("unit", f"{name} unidad")
                u.setText(unit)
                u.setMaximumWidth(90)
                row.addWidget(value, 1)
                row.addWidget(u)
                w["quantities"][name] = (value, u)
                form.addRow(name, row)
            self._layout.addLayout(form)
        self._layout.addStretch(1)
        if saved:
            self._restore(saved)
        self.set_editable(self._editable)

    def _restore(self, p: dict) -> None:
        w = self._widgets
        if "selected" in p:
            for i in p["selected"]:
                if 0 <= i < len(w.get("options", ())):
                    w["options"][i].setChecked(True)
        elif "answer" in p:
            w["true" if p["answer"] else "false"].setChecked(True)
        elif "value" in p:
            w["value"].setText(str(p["value"]))
            w["unit"].setText(str(p.get("unit", "")))
        elif "expression" in p:
            w["expression"].setText(p["expression"])
        elif "text" in p:
            w["text"].setText(p["text"])
        elif "fields" in p:
            for name, (kind, widget) in w["fields"].items():
                v = p["fields"].get(name)
                (widget.setChecked(bool(v)) if kind == "boolean" else widget.setText("" if v is None else str(v)))
        elif "quantities" in p:
            for name, (value, u) in w["quantities"].items():
                entry = p["quantities"].get(name, {})
                value.setText(str(entry.get("value", "")))
                u.setText(str(entry.get("unit", "")))

    def set_editable(self, editable: bool) -> None:
        self._editable = editable
        self.setEnabled(editable)

    def payload(self) -> dict | None:
        """F9 payload, or None while the question is unanswered/incomplete."""
        w, t = self._widgets, getattr(self._question, "qtype", "")
        if t == "multiple_choice":
            sel = [i for i, box in enumerate(w["options"]) if box.isChecked()]
            return {"selected": sel} if sel else None
        if t == "true_false":
            if w["true"].isChecked() or w["false"].isChecked():
                return {"answer": w["true"].isChecked()}
            return None
        if t == "numeric":
            value = w["value"].text().strip()
            unit = w["unit"].text().strip()
            if not value:
                return None
            return {"value": value, "unit": unit} if unit else {"value": value}
        if t == "symbolic":
            text = w["expression"].text().strip()
            return {"expression": text} if text else None
        if t == "short_text":
            text = w["text"].text().strip()
            return {"text": text} if text else None
        if t == "structured":
            out = {}
            for name, (kind, widget) in w["fields"].items():
                if kind == "boolean":
                    out[name] = widget.isChecked()
                    continue
                text = widget.text().strip()
                if not text:
                    return None
                out[name] = text
            return {"fields": out} if out else None
        if t == "circuit":
            out = {}
            for name, (value, u) in w["quantities"].items():
                if not value.text().strip():
                    return None
                entry = {"value": value.text().strip()}
                if u.text().strip():
                    entry["unit"] = u.text().strip()
                out[name] = entry
            return {"quantities": out} if out else None
        return None


class MasteryBarDelegate(QStyledItemDelegate):
    """Mastery as a bar plus the figure, so the level reads at a glance (audit F-10)."""

    def paint(self, painter, option, index) -> None:
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor
        from academic_core.ui.theme import current_tokens
        ratio = index.data(Qt.ItemDataRole.UserRole)
        if ratio is None:
            return super().paint(painter, option, index)
        t = current_tokens()
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        r = option.rect.adjusted(8, 0, -8, 0)
        text_w = 44
        track = QRectF(r.left(), r.center().y() - 4, r.width() - text_w - 8, 8)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(t.field))
        painter.drawRoundedRect(track, 4, 4)
        painter.setBrush(QColor(t.accent))
        painter.drawRoundedRect(QRectF(track.left(), track.top(), track.width() * max(0.0, min(1.0, ratio)), 8), 4, 4)
        painter.setPen(QColor(t.ink))
        painter.drawText(r.adjusted(r.width() - text_w, 0, 0, 0), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                         index.data(Qt.ItemDataRole.DisplayRole))
        painter.restore()


class PracticePanel(QWidget):
    """Sessions, adaptive plan and mastery over the certified F9-F12 loop."""

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.svc = app.practice
        self.state = UiState.IDLE
        self.attempt = None
        self.result = None
        self._questions: dict = {}
        self._order: list[str] = []
        self._answers: dict = {}
        self._current = -1

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.workspaces = QStackedWidget()
        outer.addWidget(self.workspaces)
        self.sessions_workspace = QWidget()
        self.plan_workspace = QWidget()
        self.mastery_workspace = QWidget()
        self._build_sessions(self.sessions_workspace)
        self._build_plan(self.plan_workspace)
        self._build_mastery(self.mastery_workspace)
        for ws in (self.sessions_workspace, self.plan_workspace, self.mastery_workspace):
            self.workspaces.addWidget(ws)
        self.refresh()

    def set_workspace(self, name: str) -> None:
        """``sessions``, ``plan`` or ``mastery``."""
        self.workspaces.setCurrentWidget({"plan": self.plan_workspace, "mastery": self.mastery_workspace}
                                         .get(name, self.sessions_workspace))
        self.refresh()

    def _subjects(self):
        return list(self.app.academic.all_subjects())

    # ===================================================================== sessions
    def _build_sessions(self, host: QWidget) -> None:
        root = QVBoxLayout(host)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        tools = QHBoxLayout()
        tools.setSpacing(8)
        self.btn_import = QPushButton("Importar banco…")
        self.btn_import.setToolTip("Importa un banco de preguntas D6 (JSON). Se valida antes de guardar nada.")
        self.btn_sample = QPushButton("Cargar ejemplo")
        self.btn_sample.setToolTip("Añade un banco pequeño integrado para probar Práctica enseguida")
        self.btn_start = QPushButton("Empezar intento")
        self.btn_start.setProperty("class", "primary")
        self.btn_submit = QPushButton("Entregar intento")
        self.btn_submit.setToolTip("Corrige cada respuesta con el corrector certificado")
        self.status = QLabel("LISTO")
        apply_status_style(self.status, UiState.IDLE)
        for b in (self.btn_import, self.btn_sample, self.btn_start, self.btn_submit):
            tools.addWidget(b)
        tools.addStretch(1)
        tools.addWidget(self.status)
        root.addLayout(tools)
        self.notice = Notice("")
        root.addWidget(self.notice)

        body = QHBoxLayout()
        body.setSpacing(16)
        root.addLayout(body, 1)

        left = Panel("Preguntas")
        self.bank_box = QComboBox()
        self.bank_box.setAccessibleName("Banco de preguntas")
        left.add(self.bank_box)
        self.question_list = QListWidget()
        self.question_list.setAccessibleName("Preguntas")
        self.question_list.setTextElideMode(Qt.TextElideMode.ElideRight)  # a long statement ends in "…"
        self.question_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left.add(self.question_list, 1)
        self.selection_note = QLabel("")
        self.selection_note.setObjectName("CardStatus")
        self.selection_note.setWordWrap(True)
        left.add(self.selection_note)
        left.setFixedWidth(340)
        body.addWidget(left)

        right = QVBoxLayout()
        right.setSpacing(16)
        body.addLayout(right, 1)

        self.question_panel = Panel("Pregunta")
        self.question_stack = QStackedWidget()
        self.empty = EmptyState("", "")
        self.question_page = QWidget()
        qv = QVBoxLayout(self.question_page)
        qv.setContentsMargins(0, 0, 0, 0)
        qv.setSpacing(10)
        self.meta_label = QLabel("")
        self.meta_label.setObjectName("CardStatus")
        self.statement_label = QLabel("")
        self.statement_label.setObjectName("SectionTitle")
        self.statement_label.setWordWrap(True)
        self.statement_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.answer_form = AnswerForm()
        nav = QHBoxLayout()
        self.btn_prev, self.btn_next = QPushButton("Anterior"), QPushButton("Siguiente")
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("CardStatus")
        nav.addWidget(self.btn_prev)
        nav.addWidget(self.btn_next)
        nav.addStretch(1)
        nav.addWidget(self.progress_label)
        for w in (self.meta_label, self.statement_label):
            qv.addWidget(w)
        qv.addWidget(self.answer_form, 1)
        qv.addLayout(nav)
        self.question_stack.addWidget(self.empty)
        self.question_stack.addWidget(self.question_page)
        self.question_panel.add(self.question_stack, 1)
        right.addWidget(self.question_panel, 3)

        lower = QHBoxLayout()
        lower.setSpacing(16)
        right.addLayout(lower, 2)
        self.result_panel = Panel("Resultado")
        self.score_metric = Metric("Puntuación", "")
        self.result_panel.add(self.score_metric)
        self.verdict_list = QListWidget()
        self.verdict_list.setAccessibleName("Veredicto por pregunta")
        self.result_panel.add(self.verdict_list, 1)
        self.result_note = QLabel("Las respuestas se corrigen al entregar.")
        self.result_note.setObjectName("CardStatus")
        self.result_note.setWordWrap(True)
        self.result_panel.add(self.result_note)
        lower.addWidget(self.result_panel, 1)

        self.tutor_panel = Panel("Tutor")
        self.btn_hint = QPushButton("Pedir una pista")
        self.btn_hint.setProperty("class", "subtle")
        self.btn_hint.setEnabled(False)
        self.tutor_panel.actions.addWidget(self.btn_hint)
        self.hint_status = QLabel("")
        self.hint_message = QLabel("Corrige tu intento y luego pregunta sobre una pregunta.")
        self.hint_message.setWordWrap(True)
        self.hint_message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.hint_steps = QLabel("")
        self.hint_steps.setWordWrap(True)
        self.hint_note = QLabel("")
        self.hint_note.setObjectName("CardStatus")
        self.hint_note.setWordWrap(True)
        self.hint_status.hide()
        self.tutor_panel.body.addWidget(self.hint_status, 0, Qt.AlignmentFlag.AlignLeft)
        for w in (self.hint_message, self.hint_steps, self.hint_note):
            self.tutor_panel.add(w)
        self.tutor_panel.body.addStretch(1)
        lower.addWidget(self.tutor_panel, 1)

        self.btn_import.clicked.connect(self._import_bank)
        self.btn_sample.clicked.connect(self._import_sample)
        self.btn_start.clicked.connect(self._start)
        self.btn_submit.clicked.connect(self._submit)
        self.btn_prev.clicked.connect(lambda: self._go(self._current - 1))
        self.btn_next.clicked.connect(lambda: self._go(self._current + 1))
        self.bank_box.currentIndexChanged.connect(lambda _i: self._fill_questions())
        self.question_list.currentRowChanged.connect(self._row_changed)
        self.question_list.itemChanged.connect(lambda _i: self._sync_actions())
        self.verdict_list.currentRowChanged.connect(self._verdict_selected)
        self.btn_hint.clicked.connect(self._ask_hint)

    # -- data ---------------------------------------------------------------------------
    def refresh(self) -> None:
        current = self.bank_box.currentData()
        self.bank_box.blockSignals(True)
        self.bank_box.clear()
        for b in self.svc.banks():
            self.bank_box.addItem(f"{b['title']} ({b['question_count']})", b["bank_id"])
        if current is not None:
            i = self.bank_box.findData(current)
            if i >= 0:
                self.bank_box.setCurrentIndex(i)
        self.bank_box.blockSignals(False)
        self._fill_questions()
        self._refresh_plan_subjects()
        self._refresh_mastery()

    def _fill_questions(self) -> None:
        if self.attempt is not None:
            return  # the list belongs to the running attempt
        bank = self.bank_box.currentData()
        self._questions = {q.question_id: q for q in self.svc.questions(bank)} if bank else {}
        self.question_list.blockSignals(True)
        self.question_list.clear()
        for n, q in enumerate(self._questions.values(), start=1):
            item = QListWidgetItem(f"{n}. {self._short(q.statement)}")
            item.setData(Qt.ItemDataRole.UserRole, q.question_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setToolTip(f"{q.statement}\n\n{QTYPE_LABEL.get(q.qtype, q.qtype)} · {q.difficulty}")
            self.question_list.addItem(item)
        self.question_list.blockSignals(False)
        if not self._questions:
            self.empty.set("Aún no hay bancos de preguntas", "Importa un banco de preguntas (D6 JSON) para practicar. "
                           "No se genera nada por ti: las preguntas vienen de los bancos que importes.")
            self.empty.set_action("Cargar banco de ejemplo", self._import_sample)
            self.question_stack.setCurrentWidget(self.empty)
        else:
            self.empty.set("Listo para practicar", "Elige las preguntas de la izquierda y empieza un intento.")
            self.empty.set_action()
            self.question_stack.setCurrentWidget(self.empty)
        self._sync_actions()

    @staticmethod
    def _short(text: str, n: int = 44) -> str:
        text = " ".join(text.split())
        return text if len(text) <= n else text[: n - 1] + "…"

    def selected_ids(self) -> list[str]:
        out = []
        for i in range(self.question_list.count()):
            item = self.question_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                out.append(item.data(Qt.ItemDataRole.UserRole))
        return out

    def _sync_actions(self) -> None:
        chosen = len(self.selected_ids())
        running = self.attempt is not None and self.result is None
        self.btn_start.setEnabled(not running and chosen > 0)
        self.btn_start.setToolTip("" if chosen else "Marca al menos una pregunta")
        self.btn_submit.setEnabled(running)
        self.btn_prev.setEnabled(running and self._current > 0)
        self.btn_next.setEnabled(running and self._current < len(self._order) - 1)
        self.selection_note.setText(
            f"{chosen} de {self.question_list.count()} seleccionadas" if not running and self.question_list.count()
            else "")

    def _set_state(self, state: UiState, text: str) -> None:
        self.state = state
        self.status.setText(text)
        apply_status_style(self.status, state)

    # -- bank import ---------------------------------------------------------------------------
    def _import_bank(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importar banco de preguntas", "", "Banco de preguntas (*.json)")
        if path:
            self.import_path(path)

    def _import_sample(self) -> None:
        self.import_path(None)

    def import_path(self, path: str | None) -> None:
        """``None`` loads the built-in sample bank."""
        try:
            report = self.svc.import_sample() if path is None else self.svc.import_bank(path)
        except Exception as exc:
            ui = show_ui_error(self, exc, "Importar banco")
            self._set_state(UiState.ERROR, f"ERROR {ui.error_code}")
            return
        verb = {"create": "Importado", "update": "Actualizado", "unchanged": "Ya está al día:"}.get(
            report["outcome"], report["outcome"])
        self.notice.setText(f"{verb} {report['bank_id']} (versión {report['content_version']}).")
        self._set_state(UiState.IDLE, "LISTO")
        self.refresh()
        i = self.bank_box.findData(report["bank_id"])
        if i >= 0:
            self.bank_box.setCurrentIndex(i)

    # -- attempt -------------------------------------------------------------------------------------
    def start_with(self, question_ids) -> None:
        """Start an attempt over exactly these questions (used by the plan)."""
        self.set_workspace("sessions")
        wanted = set(question_ids)
        self.bank_box.blockSignals(True)
        for i in range(self.bank_box.count()):
            self.bank_box.setCurrentIndex(i)
            self._fill_questions()
            if wanted & set(self._questions):
                break
        self.bank_box.blockSignals(False)
        for i in range(self.question_list.count()):
            item = self.question_list.item(i)
            item.setCheckState(Qt.CheckState.Checked if item.data(Qt.ItemDataRole.UserRole) in wanted
                               else Qt.CheckState.Unchecked)
        self._start()

    def _start(self) -> None:
        ids = self.selected_ids()
        try:
            self.attempt = self.svc.start_attempt(ids, self._subject_for(ids))
        except Exception as exc:
            self.attempt = None
            ui = show_ui_error(self, exc, "Empezar intento")
            self._set_state(UiState.ERROR, f"ERROR {ui.error_code}")
            return
        self.result = None
        self._answers = {}
        self._order = list(self.attempt.question_ids)
        self.question_list.blockSignals(True)
        for i in range(self.question_list.count()):
            item = self.question_list.item(i)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            item.setHidden(item.data(Qt.ItemDataRole.UserRole) not in self._order)
        self.question_list.blockSignals(False)
        self.verdict_list.clear()
        self.score_metric.clear()
        self.result_note.setText("Las respuestas se corrigen al entregar.")
        self._reset_hint()
        self.notice.setText("")
        self._set_state(UiState.RUNNING, "EN CURSO")
        self.question_stack.setCurrentWidget(self.question_page)
        self._go(0)

    def _subject_for(self, ids) -> str:
        """Subject inferred from the questions' concepts; asks nothing when unambiguous."""
        subjects = {self._questions[q].subject_id for q in ids if self._questions[q].subject_id}
        return next(iter(subjects)) if len(subjects) == 1 else ""

    def _go(self, index: int) -> None:
        if not self._order or not 0 <= index < len(self._order):
            return
        self._store_current()
        self._current = index
        q = self._questions[self._order[index]]
        self.meta_label.setText(f"{QTYPE_LABEL.get(q.qtype, q.qtype)} · {q.difficulty}"
                                + (f" · {self._unit_note(q)}" if q.unit else ""))
        self.statement_label.setText(q.statement)
        self.answer_form.set_editable(self.result is None)
        self.answer_form.set_question(q, self._answers.get(q.question_id))
        self.progress_label.setText(f"Pregunta {index + 1} de {len(self._order)} · "
                                    f"{len(self._answers)} respondidas")
        self.question_list.blockSignals(True)
        for i in range(self.question_list.count()):
            if self.question_list.item(i).data(Qt.ItemDataRole.UserRole) == q.question_id:
                self.question_list.setCurrentRow(i)
        self.question_list.blockSignals(False)
        self._sync_actions()

    @staticmethod
    def _unit_note(q) -> str:
        return f"unidad: {q.unit}"

    def _store_current(self) -> None:
        if self._current < 0 or self.result is not None or self._current >= len(self._order):
            return
        qid = self._order[self._current]
        payload = self.answer_form.payload()
        if payload is None:
            self._answers.pop(qid, None)
        else:
            self._answers[qid] = payload

    def _row_changed(self, row: int) -> None:
        item = self.question_list.item(row) if row >= 0 else None
        if item is None or self.attempt is None:
            return
        qid = item.data(Qt.ItemDataRole.UserRole)
        if qid in self._order:
            self._go(self._order.index(qid))

    def _submit(self) -> None:
        self._store_current()
        try:
            self.result = self.svc.submit(self.attempt, dict(self._answers))
        except Exception as exc:
            ui = show_ui_error(self, exc, "Entregar intento")
            self._set_state(UiState.ERROR, f"ERROR {ui.error_code}")
            return
        r = self.result
        self.score_metric.set_value(f"{Decimal(r.total_score):.2f} / {Decimal(r.max_possible):.2f}")
        self.score_metric.unit.setText(f"{Decimal(r.percentage):.0f} %  ·  {'superado' if r.passed else 'no superado'}")
        self.verdict_list.clear()
        for n, item in enumerate(r.items, start=1):
            label = verdict_label(item.is_correct, item.reason)
            why = "" if item.reason == "omitted" else \
                f": {REASON_TEXT.get(item.reason, item.reason.replace('_', ' '))}"
            row = QListWidgetItem(f"{n}. {label}{why}")
            row.setData(Qt.ItemDataRole.UserRole, item.question_id)
            self.verdict_list.addItem(row)
        review = sum(1 for i in r.items if i.is_correct is None and i.reason != "omitted")
        self.result_note.setText(
            ("Corregido con el corrector certificado; tu perfil de dominio se actualizó."
             if r.mastery_updated else
             "Corregido con el corrector certificado. Nada aquí se pudo puntuar automáticamente, así que tu "
             "perfil de dominio no cambió.")
            + (f" {review} respuesta(s) necesitan revisión manual y no cuentan como erróneas." if review else ""))
        self._set_state(UiState.SUCCESS, "CORREGIDO")
        self.answer_form.set_editable(False)
        self.attempt_done = self.attempt
        self.attempt = None  # the list is free again for the next attempt
        self.question_list.blockSignals(True)
        for i in range(self.question_list.count()):
            item = self.question_list.item(i)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setHidden(False)
        self.question_list.blockSignals(False)
        self.verdict_list.setCurrentRow(0)
        self._sync_actions()
        self._refresh_mastery()
        self._refresh_plan_subjects()

    # -- tutor ---------------------------------------------------------------------------------------------
    def _reset_hint(self) -> None:
        self.hint_status.hide()
        self.hint_steps.setText("")
        self.hint_message.setText("Corrige tu intento y luego pregunta sobre una pregunta.")
        self.hint_note.setText("")
        self.btn_hint.setEnabled(False)

    def _verdict_selected(self, row: int) -> None:
        self.btn_hint.setEnabled(self.result is not None and row >= 0)
        if self.result is not None and row >= 0:
            qid = self.verdict_list.item(row).data(Qt.ItemDataRole.UserRole)
            if qid in self._order:
                self._go(self._order.index(qid))
                self.verdict_list.setCurrentRow(row)

    def _ask_hint(self) -> None:
        row = self.verdict_list.currentRow()
        if self.result is None or row < 0:
            return
        qid = self.verdict_list.item(row).data(Qt.ItemDataRole.UserRole)
        try:
            hint = self.svc.hint(self.result.session_id, qid)
        except Exception as exc:
            show_ui_error(self, exc, "Tutor")
            return
        self.hint_status.setText(hint.status.upper())
        apply_status_style(self.hint_status, HINT_STATE.get(hint.status, UiState.WARNING))
        self.hint_status.show()
        rejected = hint.status == "rejected"
        self.hint_message.setText(REJECTED_TEXT.get(hint.message, hint.message) if rejected else hint.message)
        self.hint_steps.setText("\n".join(f"{i}. {s}" for i, s in enumerate(hint.steps, start=1)))
        if hint.llm_available:
            self.hint_note.setText("Un modelo de lenguaje propuso esta respuesta. Se validó y se comprobó "
                                   "con el corrector certificado; el modelo nunca califica.")
        else:
            self.hint_note.setText("Modelo del tutor: desactivado. Esta orientación se construye a partir de tu intento y sigue "
                                   "las mismas reglas; nada aquí se genera libremente.")

    # ===================================================================== plan
    def _build_plan(self, host: QWidget) -> None:
        root = QHBoxLayout(host)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)
        left = Panel("Plan")
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.plan_subject = QComboBox()
        self.plan_subject.setAccessibleName("Asignatura")
        self.plan_count = QSpinBox()
        self.plan_count.setRange(1, 20)
        self.plan_count.setValue(5)
        self.plan_count.setAccessibleName("Número de ejercicios")
        form.addRow("Asignatura", self.plan_subject)
        form.addRow("Ejercicios", self.plan_count)
        left.body.addLayout(form)
        self.btn_plan = QPushButton("Crear plan")
        self.btn_plan.setProperty("class", "primary")
        left.add(self.btn_plan)
        self.plan_snapshot = KeyValueList()
        snap_title = QLabel("Dominio usado")
        snap_title.setObjectName("PanelTitle")
        left.add(snap_title)
        left.add(self.plan_snapshot)
        self.plan_snapshot.set_rows([("—", "Crea un plan para ver el dominio en que se basa.")])
        left.body.addStretch(1)
        left.setFixedWidth(340)
        root.addWidget(left)

        right = Panel("Recomendado a continuación")
        self.btn_practice_plan = QPushButton("Practicar estas")
        self.btn_practice_plan.setProperty("class", "primary")
        self.btn_practice_plan.setEnabled(False)
        right.actions.addWidget(self.btn_practice_plan)
        self.plan_list = QListWidget()
        self.plan_list.setAccessibleName("Preguntas recomendadas")
        self.plan_list.setWordWrap(True)
        self.plan_list.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.plan_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right.add(self.plan_list, 1)
        self.plan_note = QLabel("Crea un plan para ver qué recomienda el motor y por qué.")
        self.plan_note.setObjectName("CardStatus")
        self.plan_note.setWordWrap(True)
        right.add(self.plan_note)
        root.addWidget(right, 1)
        self._plan_ids: list[str] = []
        self.btn_plan.clicked.connect(self._build_plan_now)
        self.btn_practice_plan.clicked.connect(lambda: self.start_with(self._plan_ids))

    def _refresh_plan_subjects(self) -> None:
        with_questions = {q.subject_id for q in self.svc.questions() if q.subject_id}
        current = self.plan_subject.currentData()
        self.plan_subject.clear()
        for s in self._subjects():
            if s.stable_id in with_questions:
                self.plan_subject.addItem(s.name, s.stable_id)
        i = self.plan_subject.findData(current) if current else -1
        if i >= 0:
            self.plan_subject.setCurrentIndex(i)
        self.btn_plan.setEnabled(self.plan_subject.count() > 0)
        if not self.plan_subject.count():
            self.plan_note.setText("Ninguna asignatura tiene bancos de preguntas todavía. Importa un banco cuyos conceptos "
                                   "pertenezcan a una asignatura para obtener un plan.")

    def _build_plan_now(self) -> None:
        subject = self.plan_subject.currentData()
        if not subject:
            return
        try:
            plan = self.svc.plan(subject, self.plan_count.value())
        except Exception as exc:
            show_ui_error(self, exc, "Plan adaptativo")
            return
        self.plan_list.clear()
        self._plan_ids = [i.question_id for i in plan.items]
        for n, item in enumerate(plan.items, start=1):
            why = "; ".join(RATIONALE_TEXT.get(c, c) for c in item.rationale)
            row = QListWidgetItem(f"{n}. {self._short(item.statement, 60)}\n    {item.difficulty} · {why}")
            row.setData(Qt.ItemDataRole.UserRole, item.question_id)
            self.plan_list.addItem(row)
        self.btn_practice_plan.setEnabled(bool(plan.items))
        if plan.items:
            self.plan_note.setText("Determinista: la misma evidencia da siempre el mismo plan.")
        else:
            self.plan_note.setText("Nada cumple los criterios ahora: todas las preguntas de esta asignatura están "
                                   "ya hechas o fuera de las reglas de dificultad.")
        self.plan_snapshot.set_rows([(ref.split(":")[-1], f"{p:.0%}") for ref, p in plan.mastery_snapshot]
                                    or [("—", "sin evidencia todavía")])

    # ===================================================================== mastery
    def _build_mastery(self, host: QWidget) -> None:
        root = QHBoxLayout(host)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)
        left = Panel("Dominio")
        self.mastery_subject = QComboBox()
        self.mastery_subject.setAccessibleName("Asignatura")
        left.add(self.mastery_subject)
        self.subject_metric = Metric("Dominio de la asignatura", "")
        left.add(self.subject_metric)
        self.btn_rebuild = QPushButton("Recalcular desde la evidencia")
        self.btn_rebuild.setToolTip("Reconstruye cada estado desde las observaciones guardadas y compara")
        left.add(self.btn_rebuild)
        self.mastery_note = QLabel("")
        self.mastery_note.setObjectName("CardStatus")
        self.mastery_note.setWordWrap(True)
        left.add(self.mastery_note)
        left.body.addStretch(1)
        left.setFixedWidth(340)
        root.addWidget(left)

        right = Panel("Conceptos")
        self.concept_table = QTableWidget(0, 3)
        self.concept_table.setHorizontalHeaderLabels(("Concepto", "Dominio", "Observaciones"))
        self.concept_table.setAccessibleName("Dominio por concepto")
        self.concept_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.concept_table.verticalHeader().hide()
        self.concept_table.setShowGrid(False)
        head = self.concept_table.horizontalHeader()
        head.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        head.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        head.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        head.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.concept_table.setColumnWidth(1, 200)
        self.concept_table.setItemDelegateForColumn(1, MasteryBarDelegate(self.concept_table))
        self.concept_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.mastery_empty = EmptyState("Aún no hay práctica", "Corrige un intento y aquí aparece tu perfil de dominio.")
        self.concept_stack = QStackedWidget()
        self.concept_stack.addWidget(self.mastery_empty)
        self.concept_stack.addWidget(self.concept_table)
        right.add(self.concept_stack, 1)
        root.addWidget(right, 1)
        self.mastery_subject.currentIndexChanged.connect(lambda _i: self._fill_mastery())
        self.btn_rebuild.clicked.connect(self._rebuild)

    def _refresh_mastery(self) -> None:
        current = self.mastery_subject.currentData()
        self.mastery_subject.blockSignals(True)
        self.mastery_subject.clear()
        self.mastery_subject.addItem("Todas las asignaturas", "")
        for s in self._subjects():
            self.mastery_subject.addItem(s.name, s.stable_id)
        i = self.mastery_subject.findData(current) if current is not None else -1
        self.mastery_subject.setCurrentIndex(max(i, 0))
        self.mastery_subject.blockSignals(False)
        self._fill_mastery()

    def _fill_mastery(self) -> None:
        subject = self.mastery_subject.currentData() or None
        concepts = self.svc.concepts(subject)
        self.concept_table.setRowCount(len(concepts))
        for r, c in enumerate(concepts):
            for col, text in enumerate((c.name, f"{c.probability:.0%}", str(c.observations))):
                item = QTableWidgetItem(text)
                if col == 1:
                    item.setToolTip(str(c.probability))
                    item.setData(Qt.ItemDataRole.UserRole, float(c.probability))
                if col == 2:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.concept_table.setItem(r, col, item)
        self.concept_stack.setCurrentWidget(self.concept_table if concepts else self.mastery_empty)
        pooled = self.svc.subject_mastery(subject) if subject else None
        if pooled:
            self.subject_metric.set_value(f"{pooled[0]:.0%}", f"en {pooled[1]} observaciones")
        else:
            self.subject_metric.clear()
            self.subject_metric.unit.setText("" if subject else "elige una asignatura")
        self.btn_rebuild.setEnabled(bool(self.svc.concepts()))

    def _rebuild(self) -> None:
        before = [(c.ref, c.probability, c.observations) for c in self.svc.concepts()]
        self.svc.rebuild_mastery()
        after = [(c.ref, c.probability, c.observations) for c in self.svc.concepts()]
        self.mastery_note.setText("Recalculado desde las observaciones guardadas: idéntico a lo mostrado."
                                  if before == after else
                                  "Recalculado desde las observaciones guardadas: el resultado DIFIERE de lo mostrado.")
        self._fill_mastery()
