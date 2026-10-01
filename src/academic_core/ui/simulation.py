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


SCENARIOS = (("ejemplo: divisor de tensión", "divider"), ("ejemplo: escalón RC", "rc-step"),
             ("ejemplo: filtro RC (AC)", "rc-ac"))
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
        self.output.setToolTip("Resultado de la simulación o error seguro para la interfaz")
        self.kit = LabKit(self, self.output)

        # -- Experiment: the circuit is a consequence of the analysis, shown, not chosen --
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        form.setVerticalSpacing(6)
        self.scenario = QComboBox()
        self.scenario.setToolTip("Circuito de ejemplo que usa el análisis elegido (lo fija el análisis)")
        self.scenario.setAccessibleName("Circuito usado")
        self.scenario.addItems([name for name, _ in SCENARIOS])
        self.scenario.setEnabled(False)  # derived from the analysis: not a control
        form.addRow("Circuito (lo fija el análisis)", self.scenario)
        # A circuit the student built in Engineering > Circuits can replace the demo.
        self.project_circuit = QComboBox()
        self.project_circuit.setToolTip("Analiza un circuito de tus proyectos en lugar del de ejemplo")
        self.project_circuit.setAccessibleName("Circuito del proyecto")
        self.node = QComboBox()
        self.node.setAccessibleName("Nodo de salida")
        self.source = QComboBox()
        self.source.setAccessibleName("Fuente de entrada")
        self._node_label, self._source_label = QLabel("Nodo de salida"), QLabel("Fuente de entrada")
        form.addRow("Circuito del proyecto", self.project_circuit)
        form.addRow(self._node_label, self.node)
        form.addRow(self._source_label, self.source)
        self.kit.experiment.body.addLayout(form)
        self._circuits: list[tuple[str, str]] = []  # (project, circuit) behind each combo entry
        self.project_circuit.currentIndexChanged.connect(self._sync_project)

        # -- Setup: analysis + its parameters ------------------------------------------------
        setup = QFormLayout()
        setup.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        setup.setVerticalSpacing(6)
        self.analysis = QComboBox()
        self.analysis.setToolTip("Tipo de análisis certificado")
        self.analysis.setAccessibleName("Análisis")
        self.analysis.addItems(["OP", "TRANSIENT", "AC_POINT", "AC_SWEEP", "DC_SWEEP"])
        setup.addRow("Análisis", self.analysis)
        self.detail = QTextEdit()
        self.detail.setToolTip("Parámetros del escenario (t_stop opcional en TRANSIENT).")
        self.detail.setAccessibleName("Parámetros")
        self.detail.setMaximumHeight(72)
        self.detail.setPlainText("t_stop=0.01 s")
        self.detail_label = QLabel("Parámetros (TRANSIENT)")
        setup.addRow(self.detail_label, self.detail)
        self.kit.setup.body.addLayout(setup)
        self.analysis.currentTextChanged.connect(self._sync_analysis)

        # -- Tools -----------------------------------------------------------------------------
        self.btn_run = QPushButton("Ejecutar")
        self.btn_run.setProperty("class", "primary")
        self.btn_run.setToolTip("Ejecuta la simulación con el servicio de aplicación")
        self.status = QLabel("LISTO")
        apply_status_style(self.status, UiState.IDLE)
        self.kit.toolbar.addWidget(self.btn_run)
        self.kit.toolbar.addStretch(1)
        self.kit.toolbar.addWidget(self.status)
        self.btn_run.clicked.connect(self._run)
        self.kit.presenter.run_action = ("Ejecutar análisis", self._run)
        self.kit.presenter.clear()
        self.refresh_circuits()
        self._sync_analysis(self.analysis.currentText())

    # -- project circuits --------------------------------------------------------------------
    def refresh_circuits(self) -> None:
        """Re-read the projects (the student may have built circuits since the last visit)."""
        keep = self.project_circuit.currentText()
        repo = self.app.engineering.repo
        self._circuits = [(p.name, c) for p in repo.list_projects() for c in repo.circuits_of(p.name)]
        self.project_circuit.blockSignals(True)
        self.project_circuit.clear()
        self.project_circuit.addItem("Demostración (según el análisis)")
        self.project_circuit.addItems([f"{p} · {c}" for p, c in self._circuits])
        i = self.project_circuit.findText(keep)
        self.project_circuit.setCurrentIndex(max(i, 0))
        self.project_circuit.blockSignals(False)
        self._sync_project()

    def _chosen_circuit(self):
        i = self.project_circuit.currentIndex() - 1
        if i < 0:
            return None
        project, name = self._circuits[i]
        return self.app.engineering.repo.load_circuit(project, name)

    def _sync_project(self, *_args) -> None:
        circuit = self._chosen_circuit()
        for w in (self.node, self._node_label, self.source, self._source_label):
            w.setVisible(circuit is not None)
        self.scenario.setEnabled(False)
        if circuit is None:
            return
        nets, sources = self.svc.circuit_info(circuit)
        self.node.clear()
        self.node.addItems(nets)
        if nets:
            self.node.setCurrentIndex(len(nets) - 1)  # usually the output sits last
        self.source.clear()
        self.source.addItems(sources)

    def showEvent(self, event) -> None:  # noqa: N802 — Qt override
        super().showEvent(event)
        self.refresh_circuits()

    def _sync_analysis(self, kind: str) -> None:
        """The analysis decides the demo circuit and whether t_stop applies."""
        self.scenario.setCurrentIndex(SCENARIOS_FOR[kind])
        transient = kind == "TRANSIENT"
        self.detail.setVisible(transient)
        self.detail_label.setVisible(transient)

    def _run(self) -> None:
        kind = self.analysis.currentText()
        self._set_state(UiState.RUNNING, "EJECUTANDO…")
        circuit = self._chosen_circuit()  # read on the UI thread
        mine = None if circuit is None else (circuit, self.node.currentText(), self.source.currentText())
        worker = ServiceWorker(self._execute, kind,
                               self.detail.toPlainText(), mine)
        worker.signals.finished.connect(self._on_result)
        worker.signals.failed.connect(self._on_error)
        self.pool.start(worker)

    def _execute(self, kind: str, params_text: str, mine=None):
        import uuid
        from decimal import Decimal as _D
        if mine is not None:  # a circuit from the student's project
            circuit, node, source = mine
            t_stop = "0.01 s"
            for part in params_text.split(";"):
                if "=" in part and "t_stop" in part.split("=", 1)[0]:
                    t_stop = part.split("=", 1)[1].strip()
            plan = self.svc.plan_project(circuit, kind, node, source, t_stop)
            return self.svc.run_analysis(f"sim-{uuid.uuid4().hex[:8]}", plan.pop("circuit"),
                                         verify=True, **plan)
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
                                     instruments=instruments, measurements=measurements, verify=True)

    def _on_result(self, result) -> None:
        lines = [f"ejecución: {result.run.run_id}",
                 f"estado: {result.run.status} engine={result.run.engine_status}",
                 f"digest: {result.digest[:16]}",
                 f"medidas: {len(result.run.measurements)}"]
        for m in result.run.measurements:
            lines.append(f"• {m.key} [{m.status}] {m.value}")
        self.output.setPlainText("\n".join(lines))
        self.kit.presenter.show_run(result.run)
        self._set_state(UiState.SUCCESS, "ÉXITO")

    def _on_error(self, exc) -> None:
        ui = show_ui_error(self, exc, "Simulación")
        self.output.setPlainText(f"{ui.error_code}: {ui.safe_message}")
        self.kit.show_log()
        self._set_state(UiState.ERROR, f"ERROR {ui.error_code}")

    def _set_state(self, state: UiState, text: str) -> None:
        self.state = state
        self.status.setText(text)
        apply_status_style(self.status, state)
        set_busy(state, self.btn_run)
