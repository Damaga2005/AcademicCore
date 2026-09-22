# SPDX-License-Identifier: MIT
"""E0 application service: explanations built from REAL execution traces.

    UI -> AcademicApp.explain (ExplainService) -> domain integration
       (execution.equation / execution.digital) -> ExecutionTrace
       -> explain_render.build_view -> ExplanationView -> UI text

The service coordinates:

- it resolves library keys and demo circuits
- it calls the tracing integrations, which run the certified engines
- it builds view models and handles ``execution-trace/1`` text in and out

It never computes a solution or an explanation itself, and it never
imports Qt.

Replay uses a fixed, explicit registry (operation → replayer), with no
dynamic discovery:

- ``engineering.equation``: domain replay from the recorded inputs
- ``digital.logic-analyzer``: domain replay with a fresh demo circuit
  from the recorded ``demo`` context

An unknown operation is refused (``UNSUPPORTED_OPERATION``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from academic_core.application.digital_service import AnalyzerRequest, DigitalAnalysisService
from academic_core.application.explain_render import ExplanationView, build_view, render_markdown, render_text
from academic_core.domain.execution import ExecutionTrace, compare
from academic_core.domain.execution import digital as digital_trace
from academic_core.domain.execution import equation as equation_trace
from academic_core.errors import ConfigurationError, ValidationError
from academic_core.logging_config import get_logger, log_event, new_correlation_id

logger = get_logger("academic_core.application.explain")


@dataclass(frozen=True)
class ExplainReplayView:
    status: str  # EQUIVALENT / RESULT_DIFFERS
    first_difference: str
    original_digest: str
    replayed_digest: str


class ExplainService:
    def __init__(self, engineering, digital: DigitalAnalysisService | None = None):
        self.engineering = engineering
        self.digital = digital or DigitalAnalysisService()

    # -- traces (domain values) -------------------------------------------------
    def exercise_trace(self, key: str, inputs: dict[str, str]) -> ExecutionTrace:
        entry = self.engineering.library().get(key)
        if entry is None:
            raise ConfigurationError(f"unknown exercise: {key}")
        if not isinstance(inputs, dict):
            raise ValidationError("INVALID_INPUT: inputs must be VAR=value pairs")
        return equation_trace.explain_equation(dict(inputs), entry["source"], entry.get("dim") or None)

    def capture_trace(self, request: AnalyzerRequest) -> ExecutionTrace:
        config = self.digital.build_config(request)
        circuit = self.digital.new_circuit(request.demo)
        return digital_trace.explain_capture(circuit, config, context=(("demo", request.demo),))

    # -- views --------------------------------------------------------------------
    def explain_exercise(self, key: str, inputs: dict[str, str]) -> ExplanationView:
        cid = new_correlation_id()
        view = build_view(self.exercise_trace(key, inputs))
        log_event(logger, logging.INFO, "AC-OK-001", "application.explain", "explain_exercise",
                  f"{key} {view.outcome}/{view.verification} [cid={cid}]")
        return view

    def explain_capture(self, request: AnalyzerRequest) -> ExplanationView:
        cid = new_correlation_id()
        view = build_view(self.capture_trace(request))
        log_event(logger, logging.INFO, "AC-OK-001", "application.explain", "explain_capture",
                  f"{request.demo} {view.outcome}/{view.verification} [cid={cid}]")
        return view

    def load(self, text: object) -> ExplanationView:
        """Render a saved execution-trace/1 document (nothing is re-run)."""
        return build_view(ExecutionTrace.from_json(text))

    @staticmethod
    def text(view: ExplanationView) -> str:
        return render_text(view)

    @staticmethod
    def markdown(view: ExplanationView) -> str:
        return render_markdown(view)

    # -- replay ---------------------------------------------------------------------
    def _replayer(self, operation: str):
        if operation == equation_trace.OPERATION:
            return equation_trace.replay_equation
        if operation == digital_trace.OPERATION:
            def replay_digital(trace):
                return digital_trace.replay_capture(trace, lambda ctx: self.digital.new_circuit(ctx.get("demo", "")))
            return replay_digital
        raise ValidationError(f"UNSUPPORTED_OPERATION: no replayer for {operation[:64]!r}")

    def replay(self, text: object) -> ExplainReplayView:
        """Decode, re-execute from the recorded inputs, compare (EQUIVALENT / RESULT_DIFFERS)."""
        trace = ExecutionTrace.from_json(text)
        report = compare(trace, self._replayer(trace.operation)(trace))
        if not report.equivalent:
            log_event(logger, logging.WARNING, "AC-INT-001", "application.explain", "replay",
                      f"replay differs at {report.first_difference}")
        return ExplainReplayView(report.status, report.first_difference, report.original_digest,
                                 report.replayed_digest)
