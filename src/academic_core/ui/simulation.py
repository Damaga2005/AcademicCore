# SPDX-License-Identifier: MIT
"""F15 simulation view (F15 §10).

Flow: scenario (demo divider or project circuit) -> analysis kind ->
execute (worker -> ``SimulationService`` -> F8-N) -> real result.
No solver internals in widgets.
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


class SimulationPanel(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.svc = app.simulation
        self.state = UiState.IDLE
        self.pool = QThreadPool(self)

        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("Scenario"))
        self.scenario = QComboBox()
        self.scenario.setToolTip("Demo divider or a saved project circuit")
        self.scenario.addItem("demo: voltage divider")
        row.addWidget(self.scenario)
        row.addWidget(QLabel("Analysis"))
        self.analysis = QComboBox()
        self.analysis.setToolTip("Certified analysis kind")
        self.analysis.addItems(["OP", "TRANSIENT", "AC_POINT", "AC_SWEEP", "DC_SWEEP"])
        row.addWidget(self.analysis)
        self.btn_run = QPushButton("Run")
        self.btn_run.setToolTip("Execute the simulation through the application service")
        row.addWidget(self.btn_run)
        self.status = QLabel("IDLE")
        row.addWidget(self.status)
        layout.addLayout(row)

        self.detail = QTextEdit()
        self.detail.setToolTip("Scenario parameters (optional TRANSIENT t_stop).")
        self.detail.setMaximumHeight(90)
        self.detail.setPlainText("t_stop=0.01 s")
        layout.addWidget(self.detail)

        self.output = QTextEdit(readOnly=True)
        self.output.setToolTip("Simulation result or UI-safe error")
        layout.addWidget(self.output)

        self.btn_run.clicked.connect(self._run)

    def _run(self) -> None:
        kind = self.analysis.currentText()
        self._set_state(UiState.RUNNING, "RUNNING…")
        worker = ServiceWorker(self._execute, kind,
                               self.detail.toPlainText())
        worker.signals.finished.connect(self._on_result)
        worker.signals.failed.connect(self._on_error)
        self.pool.start(worker)

    def _execute(self, kind: str, params_text: str):
        import uuid
        from decimal import Decimal as _D
        from academic_core.domain.engineering.lab.model import (
            AnalysisKind,
            AnalysisSpec,
            MeasurementKind,
            MeasurementSpec,
            VoltageProbe,
        )
        session_id = f"sim-{uuid.uuid4().hex[:8]}"
        if kind == "OP":
            circuit = self.svc.demo_divider()
            probes = (("vout", VoltageProbe("n2", "0")),)
            measurements = (("vdc", MeasurementSpec(kind=MeasurementKind.DC_VALUE.value,
                                                    probe="vout")),)
            analysis = AnalysisSpec(kind=AnalysisKind.OP.value)
        elif kind == "TRANSIENT":
            from academic_core.domain.engineering.mna.transient import TransientConfig
            tstop = _D("0.005")
            for part in params_text.split(";"):
                if "=" in part and "t_stop" in part.split("=", 1)[0]:
                    tstop = self.decimal(part.split("=", 1)[1].strip())
            circuit = self.svc.demo_rc_step()
            probes = (("vout", VoltageProbe("out", "0")),)
            measurements = (("vmax", MeasurementSpec(kind=MeasurementKind.MAX.value,
                                                     probe="vout")),)
            analysis = AnalysisSpec(
                kind=AnalysisKind.TRANSIENT.value,
                transient=TransientConfig("TR", tstop, _D("0.00005"),
                                          _D("1E-12"), _D("0.0005"),
                                          _D("1E-4"), _D("1E-6")))
        elif kind in ("AC_POINT", "AC_SWEEP"):
            from academic_core.domain.engineering.units import parse_quantity
            circuit = self.svc.demo_rc_ac()
            probes = (("vout", VoltageProbe("out", "0")),)
            measurements = ()
            if kind == "AC_POINT":
                analysis = AnalysisSpec(kind=AnalysisKind.AC_POINT.value,
                                        frequency=parse_quantity("1 kHz"))
            else:
                analysis = AnalysisSpec(
                    kind=AnalysisKind.AC_SWEEP.value,
                    frequencies=(parse_quantity("100 Hz"),
                                 parse_quantity("1 kHz"),
                                 parse_quantity("10 kHz")),
                    input_source="V1", output_p="out", output_n="0")
        else:  # DC_SWEEP
            from academic_core.domain.engineering.mna.analysis import (
                GridSpec,
                ObservableSpec,
                ParamAddress,
                SweepConfig,
            )
            circuit = self.svc.demo_divider()
            probes = ()
            measurements = ()
            analysis = AnalysisSpec(
                kind=AnalysisKind.DC_SWEEP.value,
                sweep=SweepConfig(
                    ParamAddress("V1", "value"),
                    GridSpec.linear(_D("0"), _D("5"), _D("1")),
                    observables=(ObservableSpec("node_voltage", "n2"),)))
        return self.svc.run_analysis(session_id, circuit, analysis,
                                     probes=probes, measurements=measurements)

    def _on_result(self, result) -> None:
        lines = [f"run: {result.run.run_id}",
                 f"status: {result.run.status} engine={result.run.engine_status}",
                 f"digest: {result.digest[:16]}",
                 f"measurements: {len(result.run.measurements)}"]
        for m in result.run.measurements:
            lines.append(f"• {m.key} [{m.status}] {m.value}")
        self.output.setPlainText("\n".join(lines))
        self._set_state(UiState.SUCCESS, "SUCCESS")

    def _on_error(self, exc) -> None:
        ui = show_ui_error(self, exc, "Simulation")
        self.output.setPlainText(f"{ui.error_code}: {ui.safe_message}")
        self._set_state(UiState.ERROR, f"ERROR {ui.error_code}")

    def _set_state(self, state: UiState, text: str) -> None:
        self.state = state
        self.status.setText(text)
