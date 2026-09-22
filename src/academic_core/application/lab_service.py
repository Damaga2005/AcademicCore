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
class LabRunSummary:
    run_id: str
    status: str
    engine_status: str
    measurements: tuple
    readings: tuple
    result_digest: str


def _summarize(run) -> LabRunSummary:
    return LabRunSummary(
        run_id=run.run_id,
        status=run.status,
        engine_status=str(run.engine_status or ""),
        measurements=tuple(run.measurements),
        readings=tuple(run.readings),
        result_digest=run.result_digest,
    )


class LabService:
    """Application-level coordinator over the certified F8-N lab engine."""

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
