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
from academic_core.ui.state import UiState, set_busy
from academic_core.ui.theme import apply_status_style
from academic_core.ui.workers import ServiceWorker


SCENARIOS = (("demo: voltage divider", "divider"), ("demo: RC step", "rc-step"),
             ("demo: RC filter (AC)", "rc-ac"))
SCENARIOS_FOR = {"OP": 0, "DC_SWEEP": 0, "TRANSIENT": 1, "AC_POINT": 2, "AC_SWEEP": 2}


class SimulationPanel(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.svc = app.simulation
        self.state = UiState.IDLE
        self.pool = QThreadPool(self)

        from PySide6.QtWidgets import QFormLayout
        from academic_core.ui.lab_view import LabKit
        self.output = QTextEdit(readOnly=True)
        self.output.setObjectName("Output")
        self.output.setToolTip("Simulation result or UI-safe error")
        self.kit = LabKit(self, self.output)

        # -- Experiment: the circuit is a consequence of the analysis, shown, not chosen --
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        form.setVerticalSpacing(6)
        self.scenario = QComboBox()
        self.scenario.setToolTip("Demo circuit used by the selected analysis (set by the analysis)")
        self.scenario.setAccessibleName("Circuit used")
        self.scenario.addItems([name for name, _ in SCENARIOS])
        self.scenario.setEnabled(False)  # derived from the analysis: not a control
        form.addRow("Circuit (set by the analysis)", self.scenario)
        self.kit.experiment.body.addLayout(form)

        # -- Setup: analysis + its parameters ------------------------------------------------
        setup = QFormLayout()
        setup.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        setup.setVerticalSpacing(6)
        self.analysis = QComboBox()
        self.analysis.setToolTip("Certified analysis kind")
        self.analysis.setAccessibleName("Analysis")
        self.analysis.addItems(["OP", "TRANSIENT", "AC_POINT", "AC_SWEEP", "DC_SWEEP"])
        setup.addRow("Analysis", self.analysis)
        self.detail = QTextEdit()
        self.detail.setToolTip("Scenario parameters (optional TRANSIENT t_stop).")
        self.detail.setAccessibleName("Parameters")
        self.detail.setMaximumHeight(72)
        self.detail.setPlainText("t_stop=0.01 s")
        self.detail_label = QLabel("Parameters (TRANSIENT)")
        setup.addRow(self.detail_label, self.detail)
        self.kit.setup.body.addLayout(setup)
        self.analysis.currentTextChanged.connect(self._sync_analysis)

        # -- Tools -----------------------------------------------------------------------------
        self.btn_run = QPushButton("Run")
        self.btn_run.setProperty("class", "primary")
        self.btn_run.setToolTip("Execute the simulation through the application service")
        self.status = QLabel("READY")
        apply_status_style(self.status, UiState.IDLE)
        self.kit.toolbar.addWidget(self.btn_run)
        self.kit.toolbar.addStretch(1)
        self.kit.toolbar.addWidget(self.status)
        self.btn_run.clicked.connect(self._run)
        self._sync_analysis(self.analysis.currentText())

    def _sync_analysis(self, kind: str) -> None:
        """The analysis decides the demo circuit and whether t_stop applies."""
        self.scenario.setCurrentIndex(SCENARIOS_FOR[kind])
        transient = kind == "TRANSIENT"
        self.detail.setVisible(transient)
        self.detail_label.setVisible(transient)

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
            InstrumentKind,
            InstrumentSpec,
            MeasurementKind,
            MeasurementSpec,
            ScopeChannel,
            VoltageProbe,
        )
        session_id = f"sim-{uuid.uuid4().hex[:8]}"
        meter = ("meter", InstrumentSpec(InstrumentKind.VOLTMETER.value, probe="vout"))
        instruments: tuple = ()
        if kind == "OP":
            circuit = self.svc.demo_divider()
            probes = (("vout", VoltageProbe("n2", "0")),)
            measurements = (("vdc", MeasurementSpec(kind=MeasurementKind.DC_VALUE.value,
                                                    probe="vout")),)
            analysis = AnalysisSpec(kind=AnalysisKind.OP.value)
            instruments = (meter,)
        elif kind == "TRANSIENT":
            from academic_core.domain.engineering.mna.transient import TransientConfig
            tstop = _D("0.005")
            for part in params_text.split(";"):
                if "=" in part and "t_stop" in part.split("=", 1)[0]:
                    tstop = self.svc.decimal(part.split("=", 1)[1].strip())
            circuit = self.svc.demo_rc_step()
            instruments = (meter, ("scope", InstrumentSpec(
                InstrumentKind.OSCILLOSCOPE.value, channels=(ScopeChannel("vout"),),
                window=(_D("0"), tstop))))
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
                instruments = (meter,)
                analysis = AnalysisSpec(kind=AnalysisKind.AC_POINT.value,
                                        frequency=parse_quantity("1 kHz"))
            else:
                instruments = (("bode", InstrumentSpec(
                    InstrumentKind.FREQUENCY_RESPONSE.value)),)
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
        return self.svc.run_analysis(session_id, circuit, analysis, probes=probes,
                                     instruments=instruments, measurements=measurements)

    def _on_result(self, result) -> None:
        lines = [f"run: {result.run.run_id}",
                 f"status: {result.run.status} engine={result.run.engine_status}",
                 f"digest: {result.digest[:16]}",
                 f"measurements: {len(result.run.measurements)}"]
        for m in result.run.measurements:
            lines.append(f"• {m.key} [{m.status}] {m.value}")
        self.output.setPlainText("\n".join(lines))
        self.kit.presenter.show_run(result.run)
        self._set_state(UiState.SUCCESS, "SUCCESS")

    def _on_error(self, exc) -> None:
        ui = show_ui_error(self, exc, "Simulation")
        self.output.setPlainText(f"{ui.error_code}: {ui.safe_message}")
        self.kit.show_log()
        self._set_state(UiState.ERROR, f"ERROR {ui.error_code}")

    def _set_state(self, state: UiState, text: str) -> None:
        self.state = state
        self.status.setText(text)
        apply_status_style(self.status, state)
        set_busy(state, self.btn_run)
