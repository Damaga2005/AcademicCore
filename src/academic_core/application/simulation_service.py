# SPDX-License-Identifier: MIT
"""F15 simulation application service (F15 §48).

configure simulation -> execute -> collect result -> translate
result/error. Runs entirely through ``LabService`` + the certified
F8-N engine (OP / TRANSIENT / AC_POINT / AC_SWEEP / DC_SWEEP); no MNA
internals here, no Qt. Testable without Qt.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.lab.model import (
    AnalysisKind,
    AnalysisSpec,
    ExperimentDefinition,
)
from academic_core.domain.engineering.units import Quantity, parse_quantity
from academic_core.errors import ConfigurationError
from academic_core.logging_config import get_logger, log_event, new_correlation_id

from .lab_service import LabRunSummary, LabService

logger = get_logger("academic_core.application.simulation")

SUPPORTED = ("OP", "TRANSIENT", "AC_POINT", "AC_SWEEP", "DC_SWEEP")


@dataclass(frozen=True)
class SimulationResult:
    session_id: str
    experiment_id: str
    run: LabRunSummary
    digest: str


class SimulationService:
    def __init__(self, lab: LabService | None = None):
        self.lab = lab or LabService()

    # -- circuit construction from UI plain data ---------------------------
    def build_circuit(self, name: str, components: list[dict]) -> Circuit:
        from academic_core.domain.engineering.circuit import COMPONENT_PINS
        circuit = Circuit(name or "sim")
        for spec in components:
            ctype = str(spec.get("type", "")).upper()
            ref = str(spec.get("ref", "")).upper()
            raw_value = str(spec.get("value", "") or "").strip()
            pins = dict(spec.get("pins", {}))
            params = dict(spec.get("parameters", {}) or {})
            if ctype not in COMPONENT_PINS:
                raise ConfigurationError(f"unknown component type: {ctype}")
            qty = parse_quantity(raw_value) if raw_value else None
            circuit.add(Component(ref, ctype, qty, pins, params))
        warnings = circuit.validate()
        return circuit, warnings

    def demo_divider(self) -> Circuit:
        """Canonical voltage-divider demo (R1/R2 + V1, DC OP)."""
        circuit = Circuit("divider")
        circuit.add(Component("V1", "V", parse_quantity("5 V"), {"+": "n1", "-": "0"}, {}))
        circuit.add(Component("R1", "R", parse_quantity("1 kohm"), {"1": "n1", "2": "n2"}, {}))
        circuit.add(Component("R2", "R", parse_quantity("1 kohm"), {"1": "n2", "2": "0"}, {}))
        return circuit

    def demo_rc_step(self) -> Circuit:
        """RC step demo for TRANSIENT (certified rc_step shape)."""
        from decimal import Decimal as _D
        circuit = Circuit("rc")
        circuit.add(Component("V1", "V", parse_quantity("0 V"), {"+": "in", "-": "0"},
                              {"wave": {"type": "step",
                                        "v1": parse_quantity("0 V"),
                                        "v2": parse_quantity("1 V"),
                                        "t0": _D("0.001")}}))
        circuit.add(Component("R1", "R", parse_quantity("1 kohm"),
                              {"1": "in", "2": "out"}, {}))
        circuit.add(Component("C1", "C", parse_quantity("1 uF"),
                              {"1": "out", "2": "0"}, {}))
        return circuit

    def demo_rc_ac(self) -> Circuit:
        """RC demo for AC_POINT/AC_SWEEP (certified rc_ac shape)."""
        circuit = Circuit("rcac")
        circuit.add(Component("V1", "V", parse_quantity("1 V"), {"+": "in", "-": "0"},
                              {"ac_mag": parse_quantity("1 V")}))
        circuit.add(Component("R1", "R", parse_quantity("1 kohm"),
                              {"1": "in", "2": "out"}, {}))
        circuit.add(Component("C1", "C", parse_quantity("1 uF"),
                              {"1": "out", "2": "0"}, {}))
        return circuit

    # -- execution ----------------------------------------------------------
    def run_op(self, session_id: str, circuit: Circuit,
               probes: tuple = (), instruments: tuple = (),
               measurements: tuple = ()) -> SimulationResult:
        return self._run(session_id, circuit,
                         AnalysisSpec(kind=AnalysisKind.OP.value),
                         probes, instruments, measurements)

    def run_analysis(self, session_id: str, circuit: Circuit,
                     analysis: AnalysisSpec, probes: tuple = (),
                     instruments: tuple = (),
                     measurements: tuple = ()) -> SimulationResult:
        if analysis.kind not in SUPPORTED:
            raise ConfigurationError(f"unsupported analysis: {analysis.kind}")
        return self._run(session_id, circuit, analysis,
                         probes, instruments, measurements)

    def _run(self, session_id, circuit, analysis, probes, instruments,
             measurements) -> SimulationResult:
        cid = new_correlation_id()
        log_event(logger, logging.INFO, "AC-OK-001", "application.simulation",
                  "run", f"{analysis.kind} on {session_id} [cid={cid}]")
        session = self.lab.create_session(session_id, circuit)
        definition = ExperimentDefinition(analysis=analysis, probes=probes,
                                          instruments=instruments,
                                          measurements=measurements)
        session, report = self.lab.add_experiment(session, definition)
        if not report.ok:
            first = report.errors[0] if report.errors else ("AC-CFG-001", "invalid")
            raise ConfigurationError(f"{first[0]}: {first[1]}")
        from academic_core.domain.engineering.lab.serialize import experiment_id
        exp_id = experiment_id(definition, session.circuit)
        session, summary = self.lab.run_experiment(session, exp_id)
        return SimulationResult(session_id=session_id, experiment_id=exp_id,
                                run=summary, digest=summary.result_digest)

    # -- unit helpers the UI needs without importing domain ------------------
    @staticmethod
    def quantity(text: str) -> Quantity:
        return parse_quantity(text)

    @staticmethod
    def decimal(text: str) -> Decimal:
        raw = str(text).strip()
        try:
            qty = parse_quantity(raw)
            return qty.to_base()
        except ValueError:
            pass
        try:
            return Decimal(raw)
        except Exception as exc:
            raise ConfigurationError(f"invalid decimal: {text!r}") from exc
