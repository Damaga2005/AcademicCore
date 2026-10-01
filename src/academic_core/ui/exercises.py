# SPDX-License-Identifier: MIT
"""F15 exercise resolution view (F15 §9).

Flow: selector (real library keys) -> inputs -> execute (worker ->
``ExerciseService``) -> result / UI-safe error. No math in widgets.

E0.1: "Paso a paso" asks for the pedagogical trace (datos → fórmula →
sustitución → cálculo → resultado → verificación). "Explicar" keeps the
certified E0 behaviour unchanged. The math row
(Derivar / Integrar / Resolver ecuación / Simplificar) sends the text to
``AcademicApp.explain.explain_math`` and shows the rendered steps. The
widget never differentiates, integrates or solves anything itself.
"""

from __future__ import annotations

from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtWidgets import (
    QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QVBoxLayout,
    QWidget,
)

from academic_core.ui.errors import show_ui_error
from academic_core.ui.state import UiState, set_busy
from academic_core.ui.theme import apply_status_style
from academic_core.ui.workers import ServiceWorker


class ExercisePanel(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.svc = app.exercises
        self.state = UiState.IDLE
        self.pool = QThreadPool(self)
        self._auto_hint = ""

        from academic_core.ui.workspace import Panel
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        # -- tools: run, explain, step by step ---------------------------------------------
        tools = QHBoxLayout()
        tools.setSpacing(8)
        self.btn_run = QPushButton("Resolver")
        self.btn_run.setProperty("class", "primary")
        self.btn_run.setToolTip("Ejecuta el ejercicio con el servicio de aplicación")
        self.btn_explain = QPushButton("&Explicar")
        self.btn_explain.setToolTip("Ejecuta el ejercicio y lo explica paso a paso desde su "
                                    "traza real de ejecución (E0)")
        self.btn_steps = QPushButton("&Paso a paso")
        self.btn_steps.setToolTip("Datos → fórmula → sustitución → cálculo → resultado → verificación, "
                                  "desde la traza pedagógica real (E0.1)")
        self.status = QLabel("LISTO")
        apply_status_style(self.status, UiState.IDLE)
        for b in (self.btn_run, self.btn_explain, self.btn_steps):
            tools.addWidget(b)
        tools.addStretch(1)
        tools.addWidget(self.status)
        root.addLayout(tools)

        body = QHBoxLayout()
        body.setSpacing(16)
        root.addLayout(body, 1)

        # -- the problem and the student's work ------------------------------------------------
        left = QVBoxLayout()
        left.setSpacing(16)
        problem = Panel("Problema")
        pick = QHBoxLayout()
        self.selector = QComboBox()
        self.selector.setToolTip("Ejercicio de la biblioteca respaldado por el dominio")
        self.selector.setAccessibleName("Ejercicio")
        self.btn_refresh = QPushButton("Recargar")
        self.btn_refresh.setToolTip("Recarga la biblioteca de ejercicios")
        pick.addWidget(self.selector, 1)
        pick.addWidget(self.btn_refresh)
        problem.body.addLayout(pick)
        self.desc = QLabel("")
        self.desc.setWordWrap(True)
        self.desc.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        problem.add(self.desc)
        left.addWidget(problem)

        work = Panel("Tus datos")
        self.inputs = QTextEdit()
        self.inputs.setToolTip("Un par VAR=valor por ';'. Unidades obligatorias, p. ej. V=5 V")
        self.inputs.setAccessibleName("Datos (VAR=valor; VAR2=valor2)")
        self.inputs.setMaximumHeight(96)
        work.add(self.inputs)
        fmt = QLabel("Pares VAR=valor separados por ';', con unidades, p. ej. V=5 V; R=1 kohm")
        fmt.setObjectName("CardStatus")
        fmt.setWordWrap(True)
        work.add(fmt)
        left.addWidget(work)

        maths = Panel("Matemáticas")
        self.math_expr = QLineEdit()
        self.math_expr.setPlaceholderText("x^2*sin(x)   ·   3*x + 2 = x - 4")
        self.math_expr.setToolTip("Expresión (derivar, integrar, simplificar) o ecuación lineal con '='. "
                                  "Productos explícitos: 2*x. Funciones: sin, cos, tan, exp, log, sqrt, abs.")
        self.math_expr.setAccessibleName("Expresión")
        maths.add(self.math_expr)
        limits = QHBoxLayout()
        self.math_var = QLineEdit("x")
        self.math_var.setToolTip("Variable")
        self.math_var.setAccessibleName("Variable")
        self.math_lower = QLineEdit()
        self.math_lower.setPlaceholderText("a")
        self.math_lower.setToolTip("Límite inferior (integral definida; vacío = indefinida)")
        self.math_lower.setAccessibleName("Límite inferior")
        self.math_upper = QLineEdit()
        self.math_upper.setPlaceholderText("b")
        self.math_upper.setToolTip("Límite superior (integral definida; vacío = indefinida)")
        self.math_upper.setAccessibleName("Límite superior")
        for label, w in (("var", self.math_var), ("from", self.math_lower), ("to", self.math_upper)):
            cap = QLabel(label)
            cap.setProperty("role", "key")
            limits.addWidget(cap)
            limits.addWidget(w, 1)
        maths.body.addLayout(limits)
        actions = QGridLayout()
        actions.setSpacing(6)
        self.btn_derive = QPushButton("Derivar")
        self.btn_integrate = QPushButton("Integrar")
        self.btn_solve_eq = QPushButton("Resolver ecuación")
        self.btn_simplify = QPushButton("Simplificar")
        for i, (b, tip) in enumerate(((self.btn_derive, "Derivada paso a paso (reglas reales aplicadas)"),
                                      (self.btn_integrate, "Integral paso a paso; con límites a y b, integral definida"),
                                      (self.btn_solve_eq, "Ecuación lineal: despeje paso a paso y verificación"),
                                      (self.btn_simplify, "Simplificación: antes → regla → después"))):
            b.setToolTip(tip)
            b.setMinimumHeight(34)
            actions.addWidget(b, i // 2, i % 2)
        maths.body.addLayout(actions)
        left.addWidget(maths)
        left.addStretch(1)
        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setFixedWidth(400)
        body.addWidget(left_w)

        # -- feedback and result ---------------------------------------------------------------
        result = Panel("Resultado")
        self.output = QTextEdit(readOnly=True)
        self.output.setObjectName("Output")
        self.output.setToolTip("Resultado o error seguro para la interfaz")
        self.output.setAccessibleName("Resultado")
        self.output.setPlaceholderText("Resuelve, explica o recorre el ejercicio paso a paso para ver aquí el resultado.")
        result.add(self.output, 1)
        body.addWidget(result, 1)

        self.btn_refresh.clicked.connect(self.refresh_library)
        self.selector.currentTextChanged.connect(self._show_selected)
        self.btn_run.clicked.connect(self._solve)
        self.btn_explain.clicked.connect(lambda: self._explain())
        self.btn_steps.clicked.connect(lambda: self._explain(pedagogical=True))
        self.btn_derive.clicked.connect(lambda: self._math("derivative"))
        self.btn_integrate.clicked.connect(lambda: self._math("integral"))
        self.btn_solve_eq.clicked.connect(lambda: self._math("linear-equation"))
        self.btn_simplify.clicked.connect(lambda: self._math("simplify"))
        self.refresh_library()

    # -- data (plain values from the service; never domain objects) ----
    def refresh_library(self) -> None:
        keys = list(self.svc.library_keys())
        self.selector.clear()
        self.selector.addItems(keys)
        self._show_selected(self.selector.currentText())

    def _show_selected(self, key: str) -> None:
        if not key:
            return
        try:
            info = self.svc.describe(key)
        except Exception as exc:
            show_ui_error(self, exc, "Ejercicio")
            return
        self.desc.setText(f"{info['key']}: {info['equation']}")
        current = self.inputs.toPlainText().strip()
        if not current or current == self._auto_hint:  # never overwrite what the student typed
            self._auto_hint = self._hint_for(key)
            self.inputs.setPlainText(self._auto_hint)

    _HINTS = {
        "ohm-v": "I=0.005 A; R=1000 ohm",
        "ohm-i": "V=5 V; R=1000 ohm",
        "ohm-r": "V=5 V; I=0.005 A",
        "power-vi": "V=5 V; I=0.5 A",
        "power-i2r": "I=0.005 A; R=1000 ohm",
        "power-v2r": "V=5 V; R=1000 ohm",
        "charge-qcv": "C=10 uF; V=5 V",
        "energy-cap": "C=10 uF; V=5 V",
        "energy-ind": "L=10 mH; I=0.5 A",
        "freq-period": "T=1 ms",
        "voltage-divider": "Vi=5 V; R1=1 kohm; R2=2 kohm",
        "pt100-cvd": "R0=100 ohm; A=3.9083e-3; B=-5.775e-7; T=100",
        "ntc-beta": "R0=10 kohm; B=3950; T=298.15; T0=298.15",
        "ad620-rg": "G=10",
        "wheatstone": "Vs=5 V; K=2; eps=0.001",
    }

    @classmethod
    def _hint_for(cls, key: str) -> str:
        return cls._HINTS.get(key, "")

    # -- execution: worker -> service -> UI thread -----------------------
    def _read_inputs(self) -> dict | None:
        raw = self.inputs.toPlainText()
        try:
            inputs = {k.strip(): v.strip()
                      for part in raw.split(";") if "=" in part
                      for k, v in [part.split("=", 1)] if k.strip()}
            if not inputs:
                raise ValueError("no se dieron datos (se esperan pares VAR=valor)")
        except Exception as exc:
            show_ui_error(self, exc, "Datos")
            return None
        return inputs

    def _solve(self) -> None:
        key = self.selector.currentText()
        if not key:
            return
        inputs = self._read_inputs()
        if inputs is None:
            return
        self._set_state(UiState.RUNNING, "EJECUTANDO…")
        worker = ServiceWorker(self.svc.solve, key, inputs)
        worker.signals.finished.connect(self._on_result)
        worker.signals.failed.connect(self._on_error)
        self.pool.start(worker)

    def _explain(self, pedagogical: bool = False) -> None:
        """E0: show the explanation rendered from the real execution trace (E0.1: optionally pedagogical)."""
        key = self.selector.currentText()
        inputs = self._read_inputs() if key else None
        if inputs is None:
            return
        self._set_state(UiState.RUNNING, "CALCULANDO…")
        worker = ServiceWorker(self.app.explain.explain_exercise, key, inputs, pedagogical)
        worker.signals.finished.connect(self._on_explanation)
        worker.signals.failed.connect(self._on_error)
        self.pool.start(worker)

    def _math(self, kind: str) -> None:
        """E0.1: step-by-step mathematics from the engine's recorded rules."""
        expression = self.math_expr.text().strip()
        if not expression:
            show_ui_error(self, ValueError("escribe una expresión o una ecuación"), "Matemáticas")
            return
        lower = self.math_lower.text().strip() or None
        upper = self.math_upper.text().strip() or None
        self._set_state(UiState.RUNNING, "CALCULANDO…")
        worker = ServiceWorker(self.app.explain.explain_math, kind, expression,
                               self.math_var.text().strip() or "x", lower, upper)
        worker.signals.finished.connect(self._on_explanation)
        worker.signals.failed.connect(self._on_error)
        self.pool.start(worker)

    def _on_explanation(self, view) -> None:
        self.explanation = view
        self.output.setPlainText(self.app.explain.text(view))
        self._set_state(UiState.SUCCESS if view.outcome == "SUCCESS" else UiState.WARNING,
                        f"{view.outcome} · verificación {view.verification}")

    def _on_result(self, result) -> None:
        self.output.setPlainText(f"{result.text}\ndigest {result.digest[:16]}")
        self._set_state(UiState.SUCCESS, "ÉXITO")

    def _on_error(self, exc) -> None:
        ui = show_ui_error(self, exc, "Resolver")
        body = "\n\n".join(t for t in (ui.safe_message, ui.user_action) if t)
        self.output.setPlainText(f"{body}\n\n(código {ui.error_code})")
        self._set_state(UiState.ERROR, f"ERROR {ui.error_code}")

    def _set_state(self, state: UiState, text: str) -> None:
        self.state = state
        self.status.setText(text)
        apply_status_style(self.status, state)
        set_busy(state, self.btn_run, self.btn_explain, self.btn_steps, self.btn_derive,
                 self.btn_integrate, self.btn_solve_eq, self.btn_simplify)
