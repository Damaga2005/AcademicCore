# SPDX-License-Identifier: MIT
"""F15 Virtual Lab view (F15 §§11-17).

Surface over the REAL F8-N engine through ``LabService``:

Lab Session -> Experiment -> Stimuli -> Probes -> Run -> Measurements,
plus Replay / Serialization (``f8n-lab/1``). Instruments (DC source via
stimuli, multimeter/voltmeter, oscilloscope, function generator via
``function_generator``, logic display of digital-free analog values)
render ``Measurement``/waveform value-tuples and send commands; zero
solver code in this file.

Unsupported combinations are refused by the engine and shown as
UI-safe limitations, never invented.
"""

from __future__ import annotations

import uuid
from decimal import Decimal as _D

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTextEdit, QVBoxLayout, QWidget,
)

from academic_core.ui.errors import show_ui_error, show_value
from academic_core.ui.state import UiState, set_busy
from academic_core.ui.theme import apply_status_style
from academic_core.ui.workers import ServiceWorker


class VirtualLabPanel(QWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.lab = app.lab
        self.session = None
        self.last_run_id: str | None = None
        self.state = UiState.IDLE
        self.pool = QThreadPool(self)

        from PySide6.QtWidgets import QFormLayout
        from academic_core.ui.lab_view import LabKit
        self.output = QTextEdit(readOnly=True)
        self.output.setObjectName("Output")
        self.output.setToolTip("Ejecuciones, medidas, instrumentos, repetición")
        self.kit = LabKit(self, self.output)

        # -- Experiment: the session and the circuit under study --------------------------
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        form.setVerticalSpacing(6)
        self.session_id = QLineEdit("lab-demo")
        self.session_id.setToolTip("Id de sesión [A-Za-z0-9_.-]{1,64}")
        self.session_id.setAccessibleName("Id de sesión")
        self.circuit = QComboBox()
        self.circuit.setToolTip("Circuito de ejemplo certificado de la sesión")
        self.circuit.setAccessibleName("Circuito")
        self.circuit.addItems(["divisor (OP/DC_SWEEP)", "rc-escalón (TRANSIENT)",
                               "rc-ac (AC_POINT/AC_SWEEP)"])
        form.addRow("Sesión", self.session_id)
        form.addRow("Circuito", self.circuit)
        # Entries after the three demos are the student's own circuits (Engineering > Circuits).
        self.node = QComboBox()
        self.node.setAccessibleName("Nodo de salida")
        self.source = QComboBox()
        self.source.setAccessibleName("Fuente de entrada")
        self._node_label, self._source_label = QLabel("Nodo de salida"), QLabel("Fuente de entrada")
        form.addRow(self._node_label, self.node)
        form.addRow(self._source_label, self.source)
        self._circuits: list[tuple[str, str]] = []
        self.circuit.currentIndexChanged.connect(self._sync_project)
        self.kit.experiment.body.addLayout(form)

        # -- Setup: analysis and stimuli ------------------------------------------------------
        setup = QFormLayout()
        setup.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        setup.setVerticalSpacing(6)
        self.analysis = QComboBox()
        self.analysis.setToolTip("Tipo de análisis certificado F8-N")
        self.analysis.setAccessibleName("Análisis")
        self.analysis.addItems(["OP", "TRANSIENT", "AC_POINT", "AC_SWEEP", "DC_SWEEP"])
        self.dc_value = QLineEdit("5 V")
        self.dc_value.setToolTip("Estímulo DC para V1, p. ej. '5 V' (solo OP/DC). Vacío = valor del circuito")
        self.dc_value.setAccessibleName("V1 DC (vacío = valor por defecto)")
        self.sine_freq = QLineEdit("")
        self.sine_freq.setToolTip(
            "Frecuencia senoidal opcional del generador, p. ej. '1 kHz' (TRANSIENT/AC)")
        self.sine_freq.setAccessibleName("Frecuencia senoidal (TRANSIENT/AC)")
        setup.addRow("Análisis", self.analysis)
        setup.addRow("V1 DC (OP / barrido DC)", self.dc_value)
        setup.addRow("f senoidal (TRANSIENT / AC)", self.sine_freq)
        self.kit.setup.body.addLayout(setup)

        # -- Tools: session and run actions -------------------------------------------------------
        self.btn_new = QPushButton("Nueva sesión")
        self.btn_new.setToolTip("Crea una sesión de laboratorio sobre el circuito de ejemplo")
        self.btn_save = QPushButton("Guardar…")
        self.btn_save.setToolTip("Guarda la sesión como JSON f8n-lab/1")
        self.btn_load = QPushButton("Cargar…")
        self.btn_load.setToolTip("Carga un archivo de sesión f8n-lab/1")
        self.btn_run = QPushButton("Añadir y ejecutar")
        self.btn_run.setProperty("class", "primary")
        self.btn_run.setToolTip("Valida, ejecuta y mide (motor real)")
        self.btn_replay = QPushButton("Repetir el último")
        self.btn_replay.setToolTip("Repetición determinista y comparación de digest")
        self.btn_explain = QPushButton("Explicar último")
        self.btn_explain.setToolTip("Explicación paso a paso del último run, desde el resultado certificado (E0.2)")
        self.btn_explain_detail = QPushButton("Explicar en detalle")
        self.btn_explain_detail.setToolTip(
            "Paso a paso con los datos internos del motor (matriz AC, iteraciones por punto, pasos del "
            "integrador), observados al re-ejecutar el run (E0.3)")
        self.status = QLabel("LISTO")
        apply_status_style(self.status, UiState.IDLE)
        tb = self.kit.toolbar
        for b in (self.btn_new, self.btn_save, self.btn_load):
            tb.addWidget(b)
        tb.addSpacing(16)
        for b in (self.btn_run, self.btn_replay):
            tb.addWidget(b)
        tb.addStretch(1)
        tb.addWidget(self.status)
        explain_row = QHBoxLayout()  # they explain the last run, so they live with its result
        explain_row.setSpacing(6)
        for b in (self.btn_explain, self.btn_explain_detail):
            b.setProperty("class", "subtle")
            explain_row.addWidget(b)
        explain_row.addStretch(1)
        self.kit.results.body.insertLayout(1, explain_row)

        self.btn_new.clicked.connect(self._new_session)
        self.btn_explain.clicked.connect(self._explain)
        self.btn_explain_detail.clicked.connect(self._explain_detail)
        self.btn_save.clicked.connect(self._save)
        self.btn_load.clicked.connect(self._load)
        self.btn_run.clicked.connect(self._add_run)
        self.kit.presenter.run_action = ("Añadir y ejecutar", self._add_run)
        self.kit.presenter.clear()
        self.btn_replay.clicked.connect(self._replay)
        self.refresh_circuits()

    # -- project circuits ---------------------------------------------------------------
    DEMOS = 3

    def refresh_circuits(self) -> None:
        repo = self.app.engineering.repo
        self._circuits = [(p.name, c) for p in repo.list_projects() for c in repo.circuits_of(p.name)]
        keep = self.circuit.currentText()
        self.circuit.blockSignals(True)
        while self.circuit.count() > self.DEMOS:
            self.circuit.removeItem(self.circuit.count() - 1)
        self.circuit.addItems([f"{p} · {c}" for p, c in self._circuits])
        self.circuit.setCurrentIndex(max(self.circuit.findText(keep), 0))
        self.circuit.blockSignals(False)
        self._sync_project()

    def _sync_project(self, *_args) -> None:
        mine = self.circuit.currentIndex() >= self.DEMOS
        for w in (self.node, self._node_label, self.source, self._source_label):
            w.setVisible(mine)
        if not mine:
            return
        nets, sources = self.app.simulation.circuit_info(self._circuit_for(self.circuit.currentIndex()))
        self.node.clear()
        self.node.addItems(nets)
        if nets:
            self.node.setCurrentIndex(len(nets) - 1)
        self.source.clear()
        self.source.addItems(sources)

    def showEvent(self, event) -> None:  # noqa: N802 — Qt override
        super().showEvent(event)
        self.refresh_circuits()

    # -- session ----------------------------------------------------------
    def _circuit_for(self, index: int):
        if index >= self.DEMOS:
            project, name = self._circuits[index - self.DEMOS]
            return self.app.engineering.repo.load_circuit(project, name)
        if index == 1:
            return self.app.simulation.demo_rc_step()
        if index == 2:
            return self.app.simulation.demo_rc_ac()
        return self.app.simulation.demo_divider()

    def _probe_net(self, index: int) -> str:
        return "out" if index in (1, 2) else "n2"

    def _new_session(self) -> None:
        try:
            circuit = self._circuit_for(self.circuit.currentIndex())
            self.session = self.lab.create_session(
                self.session_id.text().strip() or
                f"lab-{uuid.uuid4().hex[:8]}", circuit)
            self.last_run_id = None
        except Exception as exc:
            show_ui_error(self, exc, "Sesión")
            return
        self.kit.presenter.clear()
        self._set_state(UiState.IDLE, "LISTO — sesión abierta")
        self._render("sesión abierta: "
                     f"{self.session.session_id} ({circuit.name})")

    # -- experiment buildup (plain values -> certified specs) -------------
    def _build_definition(self):
        from academic_core.domain.engineering.lab import function_generator
        from academic_core.domain.engineering.lab.model import (
            AnalysisKind,
            AnalysisSpec,
            ExperimentDefinition,
            InstrumentKind,
            InstrumentSpec,
            MeasurementKind,
            MeasurementSpec,
            ScopeChannel,
            StimulusKind,
            StimulusSpec,
            VoltageProbe,
        )
        from academic_core.domain.engineering.units import parse_quantity
        kind = self.analysis.currentText()
        cidx = self.circuit.currentIndex()
        if cidx >= self.DEMOS:
            return self._build_project_definition(kind), kind
        net = self._probe_net(cidx)
        circuit_kind = ["divider", "rc-step", "rc-ac"][cidx]
        compat = {"OP": ("divider",), "DC_SWEEP": ("divider",),
                  "TRANSIENT": ("rc-step",), "AC_POINT": ("rc-ac",),
                  "AC_SWEEP": ("rc-ac",)}
        if circuit_kind not in compat[kind]:
            raise ValueError(
                f"{kind} necesita el circuito {compat[kind][0]} "
                f"(elegido {circuit_kind})")

        stimuli = []
        dc_raw = self.dc_value.text().strip()
        sine_raw = self.sine_freq.text().strip()
        if kind in ("OP", "DC_SWEEP"):
            if dc_raw:
                stimuli.append(StimulusSpec(
                    "V1", StimulusKind.DC.value,
                    value=parse_quantity(dc_raw)))
        elif sine_raw:
            freq = self.app.simulation.decimal(sine_raw)
            stimuli.append(function_generator(
                "V1", "sine", amplitude=parse_quantity("1 V"),
                offset=parse_quantity("0 V"), frequency=freq))

        probes = (("vout", VoltageProbe(net, "0")),)
        instruments: tuple = ()
        measurements: tuple = ()
        if kind == "OP":
            instruments = (("meter", InstrumentSpec(
                InstrumentKind.VOLTMETER.value, probe="vout")),)
            measurements = (("vdc", MeasurementSpec(
                kind=MeasurementKind.DC_VALUE.value, probe="vout")),)
        elif kind == "TRANSIENT":
            instruments = (
                ("meter", InstrumentSpec(
                    InstrumentKind.VOLTMETER.value, probe="vout")),
                ("scope", InstrumentSpec(
                    InstrumentKind.OSCILLOSCOPE.value,
                    channels=(ScopeChannel("vout"),),
                    window=(_D("0"), _D("0.005")))),)
            measurements = (("vmax", MeasurementSpec(
                kind=MeasurementKind.MAX.value, probe="vout")),)
        elif kind == "AC_POINT":
            instruments = (("meter", InstrumentSpec(
                InstrumentKind.VOLTMETER.value, probe="vout")),)
            measurements = (("gain", MeasurementSpec(
                kind=MeasurementKind.AC_GAIN.value, probe="vout")),)
        elif kind == "AC_SWEEP":
            instruments = (("bode", InstrumentSpec(
                InstrumentKind.FREQUENCY_RESPONSE.value)),)
            measurements = (("bw", MeasurementSpec(
                kind=MeasurementKind.BANDWIDTH.value, probe="vout")),)
        elif kind == "DC_SWEEP":
            from academic_core.domain.engineering.mna.analysis import (
                GridSpec,
                ObservableSpec,
                ParamAddress,
                SweepConfig,
            )
            analysis = AnalysisSpec(
                kind=AnalysisKind.DC_SWEEP.value,
                sweep=SweepConfig(
                    ParamAddress("V1", "value"),
                    GridSpec.linear(_D("0"), _D("5"), _D("1")),
                    observables=(ObservableSpec("node_voltage", net),)))
            return (ExperimentDefinition(analysis=analysis, stimuli=tuple(stimuli),
                                         probes=probes, instruments=instruments,
                                         measurements=measurements), kind)
        if kind == "TRANSIENT":
            from academic_core.domain.engineering.mna.transient import (
                TransientConfig,
            )
            analysis = AnalysisSpec(
                kind=AnalysisKind.TRANSIENT.value,
                transient=TransientConfig("TR", _D("0.005"), _D("0.00005"),
                                          _D("1E-12"), _D("0.0005"),
                                          _D("1E-4"), _D("1E-6")))
        elif kind == "AC_POINT":
            analysis = AnalysisSpec(kind=AnalysisKind.AC_POINT.value,
                                    frequency=parse_quantity("1 kHz"))
        elif kind == "AC_SWEEP":
            analysis = AnalysisSpec(
                kind=AnalysisKind.AC_SWEEP.value,
                frequencies=(parse_quantity("100 Hz"),
                             parse_quantity("1 kHz"),
                             parse_quantity("10 kHz")),
                input_source="V1", output_p=net, output_n="0")
        else:
            analysis = AnalysisSpec(kind=AnalysisKind.OP.value)
        return (ExperimentDefinition(analysis=analysis, stimuli=tuple(stimuli),
                                     probes=probes, instruments=instruments,
                                     measurements=measurements), kind)

    def _build_project_definition(self, kind: str):
        """The experiment for one of the student's circuits: probe a node, drive a source."""
        from academic_core.domain.engineering.lab import function_generator
        from academic_core.domain.engineering.lab.model import (
            ExperimentDefinition, StimulusKind, StimulusSpec,
        )
        from academic_core.domain.engineering.units import parse_quantity
        source = self.source.currentText()
        plan = self.app.simulation.plan_project(self._circuit_for(self.circuit.currentIndex()), kind,
                                                self.node.currentText(), source, "0.005 s")
        plan.pop("circuit")  # the session already holds it
        stimuli = list(plan.pop("stimuli"))
        dc_raw, sine_raw = self.dc_value.text().strip(), self.sine_freq.text().strip()
        if source and kind in ("OP", "DC_SWEEP") and dc_raw:
            stimuli.append(StimulusSpec(source, StimulusKind.DC.value, value=parse_quantity(dc_raw)))
        elif source and kind == "TRANSIENT" and sine_raw:
            stimuli.append(function_generator(source, "sine", amplitude=parse_quantity("1 V"),
                                              offset=parse_quantity("0 V"),
                                              frequency=self.app.simulation.decimal(sine_raw)))
        return ExperimentDefinition(analysis=plan["analysis"], stimuli=tuple(stimuli),
                                    probes=plan["probes"], instruments=plan["instruments"],
                                    measurements=plan["measurements"])

    def _add_run(self) -> None:
        if self.session is None:
            show_ui_error(self, ValueError("crea primero una sesión"), "Ejecutar")
            return
        try:
            definition, _kind = self._build_definition()
        except Exception as exc:
            show_ui_error(self, exc, "Experimento")
            return
        self._set_state(UiState.RUNNING, "EJECUTANDO…")
        worker = ServiceWorker(self._execute, self.session, definition)
        worker.signals.finished.connect(self._on_result)
        worker.signals.failed.connect(self._on_error)
        self.pool.start(worker)

    def _execute(self, session, definition):
        from academic_core.domain.engineering.lab.serialize import experiment_id
        session, report = self.lab.add_experiment(session, definition)
        if not report.ok:
            first = report.errors[0]
            raise ValueError(f"{first[0]}: {first[1]}")
        exp_id = experiment_id(definition, session.circuit)
        session, summary = self.lab.run_experiment(session, exp_id)
        return session, self.lab.verify_with_ngspice(session, summary)  # OP only; else unchanged

    def _on_result(self, payload) -> None:
        session, summary = payload  # (LaboratorySession, LabRunSummary)
        self.session = session
        self.last_run_id = summary.run_id
        lines = [f"ejecución: {summary.run_id}",
                 f"estado: {summary.status} "
                 f"engine={summary.engine_status}",
                 f"digest: {summary.result_digest[:16]}"]
        for m in summary.measurements:
            lines.append(f"• medida {m.key} [{m.status}] {m.value}")
        for r in summary.readings:
            lines.append(f"• instrumento {r.key} ({r.kind}) [{r.status}] "
                         f"{self._reading_brief(r)}")
        self.output.setPlainText("\n".join(lines))
        self.kit.notice.setText("")
        self.kit.presenter.show_run(summary)
        self._set_state(UiState.SUCCESS, "ÉXITO")

    @staticmethod
    def _reading_brief(reading) -> str:
        data = reading.data
        if data is None:
            return reading.reason or "sin datos"
        kind = type(data).__name__
        if kind == "ScopeData":
            n = sum(len(ch.times) for ch in data.channels)
            return f"{len(data.channels)}ch {n}pts ventana={data.window}"
        if kind == "BodeData":
            return f"{len(data.points)}pts"
        if kind == "SweepData":
            return f"{len(data.axis)}pts"
        return str(data)[:160]

    def _on_error(self, exc) -> None:
        ui = show_ui_error(self, exc, "Ejecutar")
        self._render(f"{ui.error_code}: {ui.safe_message}")
        self._set_state(UiState.ERROR, f"ERROR {ui.error_code}")

    # -- E0.2 explanation ----------------------------------------------------
    def _explain(self) -> None:
        """Render the ExecutionTrace explanation of the last run (built by the application service)."""
        if self.session is None or self.last_run_id is None:
            show_ui_error(self, ValueError("aún no hay nada que explicar"), "Explicar")
            return
        self._set_state(UiState.RUNNING, "CALCULANDO…")
        worker = ServiceWorker(self.app.explain.explain_lab_run, self.session, self.last_run_id)
        worker.signals.finished.connect(self._on_explanation)
        worker.signals.failed.connect(self._on_error)
        self.pool.start(worker)

    def _explain_detail(self) -> None:
        """E0.3: the last run re-observed with the engine observer (the service checks it is the same result)."""
        if self.session is None or self.last_run_id is None:
            show_ui_error(self, ValueError("aún no hay nada que explicar"), "Explicar en detalle")
            return
        self._set_state(UiState.RUNNING, "CALCULANDO…")
        worker = ServiceWorker(self.app.explain.explain_lab_run_detail, self.session, self.last_run_id)
        worker.signals.finished.connect(self._on_explanation)
        worker.signals.failed.connect(self._on_error)
        self.pool.start(worker)

    def _on_explanation(self, view) -> None:
        self.explanation = view
        self.output.setPlainText(self.app.explain.text(view))
        self.kit.notice.setText("")
        self.kit.show_log()
        self._set_state(UiState.SUCCESS if view.outcome == "SUCCESS" else UiState.WARNING,
                        f"{view.outcome} · verificación {view.verification}")

    # -- replay -------------------------------------------------------------
    def _replay(self) -> None:
        if self.session is None or self.last_run_id is None:
            show_ui_error(self, ValueError("aún no hay nada que repetir"), "Repetir")
            return
        try:
            result = self.lab.replay(self.session, self.last_run_id)
        except Exception as exc:
            show_ui_error(self, exc, "Repetir")
            return
        from academic_core.errors import ui_error_for_code
        show_value(self, ui_error_for_code(
            result.status, severity="INFO" if result.status == "EQUIVALENT"
            else "WARNING",
            action="La comparación de digest es exacta; si cambia la versión se rechaza la repetición."),
            "Repetir")
        self._render(f"repetición {result.run_id}: {result.status} "
                     f"{result.detail or result.first_difference}")

    # -- serialization --------------------------------------------------------
    def _save(self) -> None:
        if self.session is None:
            show_ui_error(self, ValueError("aún no hay nada que guardar"), "Guardar")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Guardar sesión de laboratorio", "",
                                              "JSON de laboratorio (*.json)")
        if not path:
            return
        try:
            text = self.lab.save_text(self.session)
        except Exception as exc:
            show_ui_error(self, exc, "Guardar")
            return
        from pathlib import Path
        Path(path).write_text(text, encoding="utf-8")
        self._render(f"guardados {len(text)} bytes en {path}")

    def _load(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Cargar sesión de laboratorio", "",
                                              "JSON de laboratorio (*.json)")
        if not path:
            return
        from pathlib import Path
        try:
            result = self.lab.load_text(
                Path(path).read_text(encoding="utf-8"))
        except Exception as exc:
            show_ui_error(self, exc, "Cargar")
            return
        if result.session is None:
            show_ui_error(
                self, ValueError(f"{result.status}: {result.detail}"), "Cargar")
            return
        self.session = result.session
        self.last_run_id = None
        self.kit.presenter.clear()
        self._render(f"cargado {path}: {len(self.session.experiments)} "
                     f"experimentos, estado={result.status}")

    # -- helpers --------------------------------------------------------------
    def _render(self, text: str) -> None:
        self.output.setPlainText(text)
        self.kit.notice.setText(text if len(text) < 240 else text[:237] + "…")

    def _set_state(self, state: UiState, text: str) -> None:
        self.state = state
        self.status.setText(text)
        apply_status_style(self.status, state)
        set_busy(state, self.btn_new, self.btn_run, self.btn_explain, self.btn_explain_detail)
