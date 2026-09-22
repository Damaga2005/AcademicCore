# SPDX-License-Identifier: MIT
"""F15 exercise resolution view (F15 §9).

Flow: selector (real library keys) -> inputs -> execute (worker ->
``ExerciseService``) -> result / UI-safe error. No math in widgets.
"""

from __future__ import annotations

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout,
    QWidget,
)

from academic_core.ui.errors import show_ui_error
from academic_core.ui.state import UiState
from academic_core.ui.workers import ServiceWorker


class ExercisePanel(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.svc = app.exercises
        self.state = UiState.IDLE
        self.pool = QThreadPool(self)

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("Exercise"))
        self.selector = QComboBox()
        self.selector.setToolTip("Library exercise backed by the domain")
        top.addWidget(self.selector)
        self.btn_refresh = QPushButton("Reload")
        self.btn_refresh.setToolTip("Reload the exercise library")
        top.addWidget(self.btn_refresh)
        layout.addLayout(top)

        self.desc = QLabel("")
        self.desc.setWordWrap(True)
        layout.addWidget(self.desc)

        mid = QHBoxLayout()
        mid.addWidget(QLabel("Inputs (VAR=value; VAR2=value2)"))
        self.inputs = QTextEdit()
        self.inputs.setToolTip("One VAR=value pair per ';'. Units required, e.g. V=5 V")
        self.inputs.setMaximumHeight(80)
        mid.addWidget(self.inputs)
        layout.addLayout(mid)

        row = QHBoxLayout()
        self.btn_run = QPushButton("Solve")
        self.btn_run.setToolTip("Execute the exercise through the application service")
        row.addWidget(self.btn_run)
        self.status = QLabel("IDLE")
        row.addWidget(self.status)
        layout.addLayout(row)

        self.output = QTextEdit(readOnly=True)
        self.output.setToolTip("Result or UI-safe error")
        layout.addWidget(self.output)

        self.btn_refresh.clicked.connect(self.refresh_library)
        self.selector.currentTextChanged.connect(self._show_selected)
        self.btn_run.clicked.connect(self._solve)
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
            show_ui_error(self, exc, "Exercise")
            return
        self.desc.setText(f"{info['key']}: {info['equation']}")
        if not self.inputs.toPlainText().strip():
            self.inputs.setPlainText(self._hint_for(key))

    @staticmethod
    def _hint_for(key: str) -> str:
        hints = {
            "ohm-v": "I=0.005 A; R=1000 ohm",
            "ohm-i": "V=5 V; R=1000 ohm",
            "ohm-r": "V=5 V; I=0.005 A",
            "power-vi": "V=5 V; I=0.5 A",
        }
        return hints.get(key, "V=5 V; R=1000 ohm")

    # -- execution: worker -> service -> UI thread -----------------------
    def _solve(self) -> None:
        key = self.selector.currentText()
        if not key:
            return
        raw = self.inputs.toPlainText()
        try:
            inputs = {k.strip(): v.strip()
                      for part in raw.split(";") if "=" in part
                      for k, v in [part.split("=", 1)] if k.strip()}
            if not inputs:
                raise ValueError("no inputs given (expected VAR=value pairs)")
        except Exception as exc:
            show_ui_error(self, exc, "Inputs")
            return
        self._set_state(UiState.RUNNING, "RUNNING…")
        worker = ServiceWorker(self.svc.solve, key, inputs)
        worker.signals.finished.connect(self._on_result)
        worker.signals.failed.connect(self._on_error)
        self.pool.start(worker)

    def _on_result(self, result) -> None:
        self.output.setPlainText(f"{result.text}\ndigest {result.digest[:16]}")
        self._set_state(UiState.SUCCESS, "SUCCESS")

    def _on_error(self, exc) -> None:
        ui = show_ui_error(self, exc, "Solve")
        self.output.setPlainText(f"{ui.error_code}: {ui.safe_message}")
        self._set_state(UiState.ERROR, f"ERROR {ui.error_code}")

    def _set_state(self, state: UiState, text: str) -> None:
        self.state = state
        self.status.setText(text)
