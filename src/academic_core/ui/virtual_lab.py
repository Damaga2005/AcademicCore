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
from academic_core.ui.state import UiState
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

        layout = QVBoxLayout(self)

        # -- session -----------------------------------------------------
        srow = QHBoxLayout()
        srow.addWidget(QLabel("Session"))
        self.session_id = QLineEdit("lab-demo")
        self.session_id.setToolTip("Session id [A-Za-z0-9_.-]{1,64}")
        srow.addWidget(self.session_id)
        srow.addWidget(QLabel("Circuit"))
        self.circuit = QComboBox()
        self.circuit.setToolTip("Certified demo circuit backing the session")
        self.circuit.addItems(["divider (OP/DC_SWEEP)", "rc-step (TRANSIENT)",
                               "rc-ac (AC_POINT/AC_SWEEP)"])
        srow.addWidget(self.circuit)
        self.btn_new = QPushButton("New session")
        self.btn_new.setToolTip("Create a lab session over the demo circuit")
        srow.addWidget(self.btn_new)
        self.btn_save = QPushButton("Save…")
        self.btn_save.setToolTip("Serialize the session to f8n-lab/1 JSON")
        srow.addWidget(self.btn_save)
        self.btn_load = QPushButton("Load…")
        self.btn_load.setToolTip("Load an f8n-lab/1 session file")
        srow.addWidget(self.btn_load)
        layout.addLayout(srow)

        # -- experiment --------------------------------------------------
        erow = QHBoxLayout()
        erow.addWidget(QLabel("Analysis"))
        self.analysis = QComboBox()
        self.analysis.setToolTip("Certified F8-N analysis kind")
        self.analysis.addItems(["OP", "TRANSIENT", "AC_POINT", "AC_SWEEP",
                                "DC_SWEEP"])
        erow.addWidget(self.analysis)
        erow.addWidget(QLabel("V1 DC (blank=default)"))
        self.dc_value = QLineEdit("5 V")
        self.dc_value.setToolTip("DC stimulus for V1, e.g. '5 V' (OP/DC only)")
        erow.addWidget(self.dc_value)
        erow.addWidget(QLabel("Sine f (TRANSIENT/AC)"))
        self.sine_freq = QLineEdit("")
        self.sine_freq.setToolTip(
            "Optional function-generator sine frequency, e.g. '1 kHz'")
        erow.addWidget(self.sine_freq)
        self.btn_run = QPushButton("Add + Run")
        self.btn_run.setToolTip("Validate, execute and measure (real engine)")
        erow.addWidget(self.btn_run)
        self.btn_replay = QPushButton("Replay last")
        self.btn_replay.setToolTip("Deterministic replay + digest compare")
        erow.addWidget(self.btn_replay)
        self.btn_explain = QPushButton("Explicar último")
        self.btn_explain.setToolTip("Explicación paso a paso del último run, desde el resultado certificado (E0.2)")
        erow.addWidget(self.btn_explain)
        self.status = QLabel("IDLE")
        erow.addWidget(self.status)
        layout.addLayout(erow)

        self.output = QTextEdit(readOnly=True)
        self.output.setToolTip("Runs, measurements, instruments, replay")
        layout.addWidget(self.output)

        self.btn_new.clicked.connect(self._new_session)
        self.btn_explain.clicked.connect(self._explain)
        self.btn_save.clicked.connect(self._save)
        self.btn_load.clicked.connect(self._load)
        self.btn_run.clicked.connect(self._add_run)
        self.btn_replay.clicked.connect(self._replay)

    # -- session ----------------------------------------------------------
    def _circuit_for(self, index: int):
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
            show_ui_error(self, exc, "Session")
            return
        self._set_state(UiState.IDLE, "IDLE — session open")
        self._render("session open: "
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
        net = self._probe_net(cidx)
        circuit_kind = ["divider", "rc-step", "rc-ac"][cidx]
        compat = {"OP": ("divider",), "DC_SWEEP": ("divider",),
                  "TRANSIENT": ("rc-step",), "AC_POINT": ("rc-ac",),
                  "AC_SWEEP": ("rc-ac",)}
        if circuit_kind not in compat[kind]:
            raise ValueError(
                f"{kind} needs circuit {compat[kind][0]} "
                f"(selected {circuit_kind})")

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

    def _add_run(self) -> None:
        if self.session is None:
            show_ui_error(self, ValueError("create a session first"), "Run")
            return
        try:
            definition, _kind = self._build_definition()
        except Exception as exc:
            show_ui_error(self, exc, "Experiment")
            return
        self._set_state(UiState.RUNNING, "RUNNING…")
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
        return self.lab.run_experiment(session, exp_id)

    def _on_result(self, payload) -> None:
        session, summary = payload  # (LaboratorySession, LabRunSummary)
        self.session = session
        self.last_run_id = summary.run_id
        lines = [f"run: {summary.run_id}",
                 f"status: {summary.status} "
                 f"engine={summary.engine_status}",
                 f"digest: {summary.result_digest[:16]}"]
        for m in summary.measurements:
            lines.append(f"• measurement {m.key} [{m.status}] {m.value}")
        for r in summary.readings:
            lines.append(f"• instrument {r.key} ({r.kind}) [{r.status}] "
                         f"{self._reading_brief(r)}")
        self._render("\n".join(lines))
        self._set_state(UiState.SUCCESS, "SUCCESS")

    @staticmethod
    def _reading_brief(reading) -> str:
        data = reading.data
        if data is None:
            return reading.reason or "no data"
        kind = type(data).__name__
        if kind == "ScopeData":
            n = sum(len(ch.times) for ch in data.channels)
            return f"{len(data.channels)}ch {n}pts window={data.window}"
        if kind == "BodeData":
            return f"{len(data.points)}pts"
        if kind == "SweepData":
            return f"{len(data.axis)}pts"
        return str(data)[:160]

    def _on_error(self, exc) -> None:
        ui = show_ui_error(self, exc, "Run")
        self._render(f"{ui.error_code}: {ui.safe_message}")
        self._set_state(UiState.ERROR, f"ERROR {ui.error_code}")

    # -- E0.2 explanation ----------------------------------------------------
    def _explain(self) -> None:
        """Render the ExecutionTrace explanation of the last run (built by the application service)."""
        if self.session is None or self.last_run_id is None:
            show_ui_error(self, ValueError("nothing to explain yet"), "Explicar")
            return
        self._set_state(UiState.RUNNING, "RUNNING…")
        worker = ServiceWorker(self.app.explain.explain_lab_run, self.session, self.last_run_id)
        worker.signals.finished.connect(self._on_explanation)
        worker.signals.failed.connect(self._on_error)
        self.pool.start(worker)

    def _on_explanation(self, view) -> None:
        self.explanation = view
        self._render(self.app.explain.text(view))
        self._set_state(UiState.SUCCESS if view.outcome == "SUCCESS" else UiState.WARNING,
                        f"{view.outcome} · verificación {view.verification}")

    # -- replay -------------------------------------------------------------
    def _replay(self) -> None:
        if self.session is None or self.last_run_id is None:
            show_ui_error(self, ValueError("nothing to replay yet"), "Replay")
            return
        try:
            result = self.lab.replay(self.session, self.last_run_id)
        except Exception as exc:
            show_ui_error(self, exc, "Replay")
            return
        from academic_core.errors import ui_error_for_code
        show_value(self, ui_error_for_code(
            result.status, severity="INFO" if result.status == "EQUIVALENT"
            else "WARNING",
            action="Digest compare is exact; version drift refuses replay."),
            "Replay")
        self._render(f"replay {result.run_id}: {result.status} "
                     f"{result.detail or result.first_difference}")

    # -- serialization --------------------------------------------------------
    def _save(self) -> None:
        if self.session is None:
            show_ui_error(self, ValueError("nothing to save yet"), "Save")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save lab session", "",
                                              "Lab JSON (*.json)")
        if not path:
            return
        try:
            text = self.lab.save_text(self.session)
        except Exception as exc:
            show_ui_error(self, exc, "Save")
            return
        from pathlib import Path
        Path(path).write_text(text, encoding="utf-8")
        self._render(f"saved {len(text)} bytes to {path}")

    def _load(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load lab session", "",
                                              "Lab JSON (*.json)")
        if not path:
            return
        from pathlib import Path
        try:
            result = self.lab.load_text(
                Path(path).read_text(encoding="utf-8"))
        except Exception as exc:
            show_ui_error(self, exc, "Load")
            return
        if result.session is None:
            show_ui_error(
                self, ValueError(f"{result.status}: {result.detail}"), "Load")
            return
        self.session = result.session
        self.last_run_id = None
        self._render(f"loaded {path}: {len(self.session.experiments)} "
                     f"experiments, status={result.status}")

    # -- helpers --------------------------------------------------------------
    def _render(self, text: str) -> None:
        self.output.setPlainText(text)

    def _set_state(self, state: UiState, text: str) -> None:
        self.state = state
        self.status.setText(text)
