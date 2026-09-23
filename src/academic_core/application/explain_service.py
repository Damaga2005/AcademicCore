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
  from the recorded ``demo`` context, or (E0.1) from the
  ``digital-circuit/1`` document passed to ``replay``, whose digest must
  equal the recorded ``circuit_digest``
- E0.1: ``math.*``, ``engineering.gum``, ``engineering.nonlinear-dc`` and
  ``control.margins``: domain replay from the recorded inputs

An unknown operation is refused (``UNSUPPORTED_OPERATION``).

E0.1 adds step-by-step explanations: mathematics (derivatives,
integrals, linear equations, simplification), GUM budgets, F8-N Newton
iterations and F8-P margin bisection. It also adds pedagogical exercise
and capture modes, and the explanation of one selected Logic Analyzer
transition (``explain_transition``). That explanation is extracted from a
pedagogical capture trace; it is never recomputed. E0.1-R+: the
transition explanation uses delta-level causality (``delta=True``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from academic_core.application.digital_service import AnalyzerRequest, DigitalAnalysisService
from academic_core.application.explain_render import ExplanationView, build_view, render_markdown, render_text
from academic_core.domain.engineering import digital_circuit
from academic_core.domain.execution import EventKind, ExecutionTrace, compare
from academic_core.domain.execution import control as control_trace
from academic_core.domain.execution import digital as digital_trace
from academic_core.domain.execution import equation as equation_trace
from academic_core.domain.execution import newton as newton_trace
from academic_core.domain.execution import symbolic as symbolic_trace
from academic_core.domain.execution import uncertainty as gum_trace
from academic_core.errors import ConfigurationError, IntegrationError, ValidationError
from academic_core.logging_config import get_logger, log_event, new_correlation_id

logger = get_logger("academic_core.application.explain")


MATH_OPERATIONS = {"derivative": symbolic_trace.DERIVATIVE, "integral": symbolic_trace.INTEGRAL,
                   "linear-equation": symbolic_trace.LINEAR_EQUATION, "simplify": symbolic_trace.SIMPLIFY}
CIRCUIT_DIGEST = "circuit_digest"


@dataclass(frozen=True)
class TransitionExplanationView:
    """Why one Logic Analyzer transition happened, as recorded in a pedagogical capture trace."""

    channel: str
    index: int
    time: str
    previous: str
    new: str
    driver: str
    why: str  # the causal step's recorded explanation (or the reason it is not available)
    cause: str  # the recorded causal formula (gate evaluation) or stimulus edge
    checks: tuple[str, ...]  # "PASS: what" for the checks covering this transition's driver
    event_ids: tuple[str, ...]  # the trace events shown (transition, cause)
    available: bool


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
    def exercise_trace(self, key: str, inputs: dict[str, str], pedagogical: bool = False) -> ExecutionTrace:
        entry = self.engineering.library().get(key)
        if entry is None:
            raise ConfigurationError(f"unknown exercise: {key}")
        if not isinstance(inputs, dict):
            raise ValidationError("INVALID_INPUT: inputs must be VAR=value pairs")
        return equation_trace.explain_equation(dict(inputs), entry["source"], entry.get("dim") or None,
                                               pedagogical=pedagogical)

    def capture_trace(self, request: AnalyzerRequest, pedagogical: bool = False, delta: bool = False) -> ExecutionTrace:
        config = self.digital.build_config(request)
        circuit = self.digital.new_circuit(request.demo)
        return digital_trace.explain_capture(circuit, config, context=(("demo", request.demo),),
                                             pedagogical=pedagogical or delta, delta=delta)

    def circuit_document(self, demo: str) -> str:
        """The demo circuit as a ``digital-circuit/1`` document (explanations no longer need the demo key)."""
        return digital_circuit.circuit_to_json(self.digital.new_circuit(demo))

    def document_capture_trace(self, document: object, request: AnalyzerRequest,
                               pedagogical: bool = False, delta: bool = False) -> ExecutionTrace:
        """Capture on a ``digital-circuit/1`` document; its digest is the replay context."""
        circuit = digital_circuit.circuit_from_json(document)
        digest = digital_circuit.circuit_digest(circuit)
        return digital_trace.explain_capture(circuit, self.digital.build_config(request),
                                             context=((CIRCUIT_DIGEST, digest),), pedagogical=pedagogical or delta,
                                             delta=delta)

    def math_trace(self, kind: str, expression: str, variable: str = "x", lower: str | None = None,
                   upper: str | None = None) -> ExecutionTrace:
        if kind not in MATH_OPERATIONS:
            raise ValidationError(f"UNSUPPORTED_OPERATION: math kind must be one of {sorted(MATH_OPERATIONS)}")
        if kind == "derivative":
            return symbolic_trace.explain_derivative(expression, variable)
        if kind == "integral":
            return symbolic_trace.explain_integral(expression, variable, lower or None, upper or None)
        if kind == "linear-equation":
            return symbolic_trace.explain_linear_equation(expression, variable)
        return symbolic_trace.explain_simplify(expression, variable)

    def gum_trace(self, measurand: str, equation: str, quantities: dict[str, str], output_unit: str = "",
                  coverage_probability: str = "0.95", explicit_k: str | None = None,
                  correlations: str = "") -> ExecutionTrace:
        return gum_trace.explain_gum(measurand, equation, quantities, output_unit, coverage_probability,
                                     explicit_k, correlations)

    def nonlinear_trace(self, circuit_spec: str, **limits) -> ExecutionTrace:
        return newton_trace.explain_nonlinear_dc(circuit_spec, **limits)

    def margins_trace(self, numerator: str, denominator: str) -> ExecutionTrace:
        return control_trace.explain_margins(numerator, denominator)

    # -- views --------------------------------------------------------------------
    def explain_exercise(self, key: str, inputs: dict[str, str], pedagogical: bool = False) -> ExplanationView:
        cid = new_correlation_id()
        view = build_view(self.exercise_trace(key, inputs, pedagogical))
        log_event(logger, logging.INFO, "AC-OK-001", "application.explain", "explain_exercise",
                  f"{key} {view.outcome}/{view.verification} [cid={cid}]")
        return view

    def explain_capture(self, request: AnalyzerRequest, pedagogical: bool = False) -> ExplanationView:
        cid = new_correlation_id()
        view = build_view(self.capture_trace(request, pedagogical))
        log_event(logger, logging.INFO, "AC-OK-001", "application.explain", "explain_capture",
                  f"{request.demo} {view.outcome}/{view.verification} [cid={cid}]")
        return view

    def explain_math(self, kind: str, expression: str, variable: str = "x", lower: str | None = None,
                     upper: str | None = None) -> ExplanationView:
        cid = new_correlation_id()
        view = build_view(self.math_trace(kind, expression, variable, lower, upper))
        log_event(logger, logging.INFO, "AC-OK-001", "application.explain", "explain_math",
                  f"{kind} {view.outcome}/{view.verification} [cid={cid}]")
        return view

    def explain_gum(self, *args, **kwargs) -> ExplanationView:
        return build_view(self.gum_trace(*args, **kwargs))

    def explain_nonlinear(self, circuit_spec: str) -> ExplanationView:
        return build_view(self.nonlinear_trace(circuit_spec))

    def explain_margins(self, numerator: str, denominator: str) -> ExplanationView:
        return build_view(self.margins_trace(numerator, denominator))

    def explain_transition(self, request: AnalyzerRequest, channel: str, index: int) -> TransitionExplanationView:
        """Explain the ``index``-th transition of ``channel`` in the capture of ``request``.

        Everything comes from the events of one pedagogical capture trace:
        the transition event and the causal step or warning that refs it."""
        trace = self.capture_trace(request, delta=True)
        return transition_explanation(trace, channel, index)

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
    def _circuit_for(self, context: dict, document: object):
        if CIRCUIT_DIGEST in context:
            if document is None:
                raise ValidationError("MISSING_CIRCUIT: this trace was recorded on a digital-circuit/1 document; "
                                      "provide the same document to replay it")
            circuit = digital_circuit.circuit_from_json(document)
            if digital_circuit.circuit_digest(circuit) != context[CIRCUIT_DIGEST]:
                raise IntegrationError("CIRCUIT_MISMATCH: the document digest differs from the recorded circuit_digest")
            return circuit
        return self.digital.new_circuit(context.get("demo", ""))

    def _replayer(self, operation: str, document: object = None):
        if operation == equation_trace.OPERATION:
            return equation_trace.replay_equation
        if operation == digital_trace.OPERATION:
            def replay_digital(trace):
                return digital_trace.replay_capture(trace, lambda ctx: self._circuit_for(ctx, document))
            return replay_digital
        if operation in symbolic_trace.OPERATIONS:
            return symbolic_trace.replay_math
        if operation == gum_trace.OPERATION:
            return gum_trace.replay_gum
        if operation == newton_trace.OPERATION:
            return newton_trace.replay_nonlinear_dc
        if operation == control_trace.OPERATION:
            return control_trace.replay_margins
        raise ValidationError(f"UNSUPPORTED_OPERATION: no replayer for {operation[:64]!r}")

    def replay(self, text: object, circuit_document: object = None) -> ExplainReplayView:
        """Decode, re-execute from the recorded inputs, compare (EQUIVALENT / RESULT_DIFFERS)."""
        trace = ExecutionTrace.from_json(text)
        report = compare(trace, self._replayer(trace.operation, circuit_document)(trace))
        if not report.equivalent:
            log_event(logger, logging.WARNING, "AC-INT-001", "application.explain", "replay",
                      f"replay differs at {report.first_difference}")
        return ExplainReplayView(report.status, report.first_difference, report.original_digest,
                                 report.replayed_digest)


def transition_explanation(trace: ExecutionTrace, channel: str, index: int) -> TransitionExplanationView:
    """Extract (never compute) the explanation of one transition from a pedagogical capture trace."""
    if trace.operation != digital_trace.OPERATION:
        raise ValidationError("INVALID_TRACE: not a Logic Analyzer trace")
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise ValidationError("INVALID_INPUT: index must be a non-negative integer")
    prefix = f"{channel}: "
    transitions = [e for e in trace.events if e.kind is EventKind.STEP and e.title.startswith(prefix)
                   and {"time", "previous", "new"} <= {n for n, _ in e.values}]
    if index >= len(transitions):
        return TransitionExplanationView(channel, index, "", "", "", "", "La transición no está detallada en la traza "
                                         "(fuera de rango o por encima del límite de detalle).", "", (), (), False)
    event = transitions[index]
    values = dict(event.values)
    time = f"{values['time'].number.normalize():f}" if values["time"].number is not None else ""
    causes = [trace.event(c) for c in trace.consumers(event.event_id)
              if trace.event(c).kind in (EventKind.STEP, EventKind.WARNING)
              and "driver" in {n for n, _ in trace.event(c).values}]
    cause = causes[0] if causes else None
    driver = dict(cause.values)["driver"].text if cause is not None else ""
    why = (cause.why or "") if cause is not None else (
        "La traza no es pedagógica o no registra la causa de esta transición; no se inventa.")
    checks = []
    for c in trace.checks():
        what = c.check.what
        if (driver and driver in what) or "verify" in what or "digital-trace" in what:
            checks.append(f"{c.check.status.value}: {what}")
    return TransitionExplanationView(
        channel, index, time, values["previous"].text or "", values["new"].text or "", driver, why,
        (cause.formula or "") if cause is not None else "", tuple(checks),
        tuple(e.event_id for e in (event, cause) if e is not None), cause is not None and cause.kind is EventKind.STEP)
