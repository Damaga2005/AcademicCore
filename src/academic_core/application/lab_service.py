# SPDX-License-Identifier: MIT
"""F15 Virtual Lab application service (D1 §20, F15 §46).

Coordinates F8-N session/experiment/stimuli/run/probes/measurements/
replay/serialization through the REAL certified lab APIs. No solver math
here, no Qt, no filesystem: the UI passes values in, files go through
the caller-provided text (dialogs live in ``ui/`` but read/write only
the strings this service produces). Testable without Qt.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from academic_core.domain.engineering.circuit import Circuit
from academic_core.domain.engineering.lab import (
    add_experiment,
    create_session,
    run_experiment,
)
from academic_core.domain.engineering.lab.model import (
    ExperimentDefinition,
    LaboratorySession,
)
from academic_core.domain.engineering.lab.replay import replay_run
from academic_core.domain.engineering.lab.serialize import (
    dumps_session,
    loads_document,
    stable_result_payload,
)
from academic_core.errors import AcademicCoreError, ConfigurationError
from academic_core.logging_config import get_logger, log_event, new_correlation_id

logger = get_logger("academic_core.application.lab")


@dataclass(frozen=True)
class ConservationView:
    """Plain-string view of the engine's conservation checks (KCL / KVL / Tellegen).

    ``passed`` is ``None`` when the engine recorded residuals without a verdict.
    """
    kcl: str
    kvl: str
    power_balance: str
    tolerance: str
    passed: bool | None
    points: int = 1  # how many solved points the figures cover (sweeps have many)


@dataclass(frozen=True)
class LabRunSummary:
    run_id: str
    status: str
    engine_status: str
    measurements: tuple
    readings: tuple
    result_digest: str
    conservation: ConservationView | None = None
    oracle: object = None  # OracleView from an optional ngspice cross-check (OP only), else None


def _worst(values) -> str:
    """Largest magnitude as the engine's own string (no float conversion)."""
    from decimal import Decimal
    vals = [v for v in values if v not in (None, "")]
    return str(max(vals, key=lambda v: abs(Decimal(str(v))))) if vals else "—"


def conservation_of(result) -> ConservationView | None:
    """Read the engine's conservation figures from a live result, or ``None`` if it has none."""
    checks = getattr(result, "conservation_checks", None)
    if checks is not None:
        return ConservationView(str(checks.kcl_max_residual), str(checks.kvl_max_residual or "—"),
                                str(checks.power_balance_residual), str(checks.tolerance),
                                bool(checks.passed))
    points = getattr(result, "points", None)  # DC sweep: one nonlinear solve per point
    if points:
        per_point = [getattr(getattr(p, "result", None), "conservation_checks", None) for p in points]
        if all(c is not None for c in per_point):
            return ConservationView(_worst(c.kcl_max_residual for c in per_point),
                                    _worst(c.kvl_max_residual for c in per_point),
                                    _worst(c.power_balance_residual for c in per_point),
                                    str(per_point[0].tolerance),
                                    all(bool(c.passed) for c in per_point), len(per_point))
    if hasattr(result, "kcl_max_residual"):  # small-signal AC point: residuals, no verdict
        return ConservationView(str(result.kcl_max_residual), str(getattr(result, "kvl_max_residual", "—")),
                                "—", "", None)
    return None


def _summarize(run) -> LabRunSummary:
    return LabRunSummary(
        run_id=run.run_id,
        status=run.status,
        engine_status=str(run.engine_status or ""),
        measurements=tuple(run.measurements),
        readings=tuple(run.readings),
        result_digest=run.result_digest,
        conservation=conservation_of(run.result),
    )


class LabService:
    """Application-level coordinator over the certified F8-N lab engine."""

    def __init__(self, ngspice_path: str = ""):
        self.ngspice_path = ngspice_path
        self._ngspice = None

    def verify_with_ngspice(self, session: LaboratorySession, summary: LabRunSummary) -> LabRunSummary:
        """Cross-check an operating point against ngspice; any other analysis is returned unchanged.

        The exact engine's result is never altered: the comparison is attached next to it.
        """
        from dataclasses import replace
        from academic_core.application import oracle
        run = next((r for rec in session.records for r in rec.runs if r.run_id == summary.run_id), None)
        if run is None or run.analysis_kind != "OP" or run.result is None:
            return summary
        nodes = getattr(run.result, "node_voltages", None)
        if not nodes:
            return summary
        from academic_core.domain.engineering.lab.serialize import experiment_id
        defn = next((d for d in session.experiments
                     if experiment_id(d, session.circuit) == run.experiment_id), None)
        overrides = {st.source_ref.upper(): st.value for st in (getattr(defn, "stimuli", ()) or ())
                     if st.kind == "DC" and st.value is not None}
        if self._ngspice is None:
            from academic_core.infrastructure.ngspice import NgSpiceBackend
            self._ngspice = NgSpiceBackend(self.ngspice_path)
        return replace(summary, oracle=oracle.compare_op(session.circuit, nodes, self._ngspice, overrides))

    def create_session(self, session_id: str, circuit: Circuit) -> LaboratorySession:
        cid = new_correlation_id()
        if not isinstance(circuit, Circuit):
            raise ConfigurationError("lab session needs a Circuit")
        log_event(logger, logging.INFO, "AC-OK-001", "application.lab",
                  "create_session", f"create session {session_id}")
        try:
            session = create_session(session_id, circuit)
        except AcademicCoreError:
            raise
        except ValueError as exc:
            raise ConfigurationError(str(exc)) from exc
        log_event(logger, logging.INFO, "AC-OK-001", "application.lab",
                  "create_session", f"session {session_id} open [cid={cid}]")
        return session

    def add_experiment(self, session: LaboratorySession,
                       definition: ExperimentDefinition):
        cid = new_correlation_id()
        if not isinstance(definition, ExperimentDefinition):
            raise ConfigurationError("lab experiment needs an ExperimentDefinition")
        session, report = add_experiment(session, definition)
        if not report.ok:
            log_event(logger, logging.WARNING, "AC-CFG-001", "application.lab",
                      "add_experiment", f"invalid definition [cid={cid}]")
        return session, report

    def run_experiment(self, session: LaboratorySession,
                       experiment_id: str) -> tuple[LaboratorySession, LabRunSummary]:
        cid = new_correlation_id()
        log_event(logger, logging.INFO, "AC-OK-001", "application.lab",
                  "run_experiment", f"run {experiment_id} [cid={cid}]")
        try:
            session, run = run_experiment(session, experiment_id)
        except AcademicCoreError:
            log_event(logger, logging.ERROR, "AC-APP-001", "application.lab",
                      "run_experiment", f"run rejected [cid={cid}]")
            raise
        except ValueError as exc:
            log_event(logger, logging.ERROR, "AC-APP-001", "application.lab",
                      "run_experiment", f"run rejected [cid={cid}]")
            raise ConfigurationError(str(exc)) from exc
        return session, _summarize(run)

    # -- persistence (text in/out; the UI owns the file dialog) ---------------
    def save_text(self, session: LaboratorySession) -> str:
        payloads = {}
        for record in session.records:
            for run in record.runs:
                if run.result is not None:
                    payloads[run.run_id] = stable_result_payload(run.result)
                else:
                    raise ConfigurationError(
                        f"run {run.run_id} has no live result (loaded sessions "
                        "replay before saving)")
        try:
            return dumps_session(session, payloads)
        except AcademicCoreError:
            raise
        except ValueError as exc:
            raise ConfigurationError(str(exc)) from exc

    def load_text(self, text: str):
        from academic_core.domain.engineering.lab.model import LoadStatus
        result = loads_document(text)
        if result.status != LoadStatus.OK.value:
            log_event(logger, logging.WARNING, "AC-SER-001", "application.lab",
                      "load_text", f"load {result.status}")
        return result

    def replay(self, session: LaboratorySession, run_id: str,
               allow_version_mismatch: bool = False):
        return replay_run(session, run_id,
                          allow_version_mismatch=allow_version_mismatch)
