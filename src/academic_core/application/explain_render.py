# SPDX-License-Identifier: MIT
"""E0 renderers: ExecutionTrace → structured view model → text / Markdown.

The renderer is presentation only. It reads the trace, resolves
references in order to *show* values that other events recorded, and
formats them. It never recomputes, never evaluates a formula (formulas
are displayed as text) and never mutates the trace. Every number shown
is the exact canonical Decimal the engine recorded.

The explanation answers seven questions, one section each:

1. ¿Qué recibimos?        INPUT and NORMALIZATION events
2. ¿Qué hicimos?          STEP / VALUE / DECISION / WARNING, in order
3. ¿Por qué?              the recorded ``why`` of each step or decision
4. ¿Qué fórmula usamos?   the ``formula`` fields
5. ¿Qué valores intermedios obtuvimos?  the results of VALUE / STEP events
6. ¿Qué comprobamos?      CHECK events: PASS / FAIL / NOT_APPLICABLE, all shown
7. ¿Qué resultado obtuvimos?  RESULT, or ERROR (code + where it stopped)

Other outputs (CLI, HTML, UI) consume the same frozen ``ExplanationView``.
"""

from __future__ import annotations

from dataclasses import dataclass

from academic_core.domain.execution import EventKind, ExecutionTrace, TraceValue, canonical_decimal
from academic_core.errors import ValidationError

QUESTIONS = (
    ("inputs", "¿Qué recibimos?"),
    ("steps", "¿Qué hicimos?"),
    ("why", "¿Por qué?"),
    ("formulas", "¿Qué fórmula usamos?"),
    ("values", "¿Qué valores intermedios obtuvimos?"),
    ("checks", "¿Qué comprobamos?"),
    ("result", "¿Qué resultado obtuvimos?"),
)


@dataclass(frozen=True)
class StepView:
    event_id: str
    kind: str
    title: str
    formula: str
    why: str
    result: str
    refs: tuple[str, ...]  # ids of the facts this one consumed
    consumed: tuple[str, ...]  # "e3 = 12 V" for each ref, as recorded by that event


@dataclass(frozen=True)
class CheckView:
    event_id: str
    what: str
    status: str
    actual: str
    expected: str
    tolerance: str
    detail: str


@dataclass(frozen=True)
class ExplanationSection:
    key: str
    question: str
    lines: tuple[str, ...]


@dataclass(frozen=True)
class ExplanationView:
    operation: str
    outcome: str
    verification: str  # PASS / FAIL / NONE
    digest: str
    sections: tuple[ExplanationSection, ...]
    steps: tuple[StepView, ...]
    checks: tuple[CheckView, ...]
    trace_json: str


def show_value(v: TraceValue | None) -> str:
    """Exact display of a recorded value (canonical Decimal + unit, or text)."""
    if v is None:
        return "—"
    if v.text is not None:
        return v.text
    return f"{canonical_decimal(v.number)} {v.unit}".rstrip()


def _event_value(e) -> str:
    if e.result is not None:
        return show_value(e.result)
    if len(e.values) == 1:
        return show_value(e.values[0][1])
    return ""


def _consumed(trace: ExecutionTrace, ref: str) -> str:
    value = _event_value(trace.event(ref))
    return f"{ref} = {value}" if value else ref


def build_view(trace: ExecutionTrace) -> ExplanationView:
    if not isinstance(trace, ExecutionTrace):
        raise ValidationError(f"INVALID_TRACE: expected ExecutionTrace, got {type(trace).__name__}")
    steps, checks = [], []
    inputs, done, why, formulas, values, check_lines, result = [], [], [], [], [], [], []
    for e in trace.events:
        consumed = tuple(_consumed(trace, r) for r in e.refs)
        steps.append(StepView(e.event_id, e.kind.value, e.title, e.formula or "", e.why or "",
                              show_value(e.result) if e.result is not None else "", e.refs, consumed))
        tag = f"[{e.event_id}]"
        if e.kind is EventKind.INPUT:
            name, value = e.values[0]
            inputs.append(f"{tag} {name} = {show_value(value)}")
        elif e.kind is EventKind.NORMALIZATION:
            inputs.append(f"{tag} {e.title}: {show_value(e.result)}")
        elif e.kind in (EventKind.STEP, EventKind.VALUE, EventKind.DECISION, EventKind.WARNING):
            line = f"{tag} {e.title}"
            if e.refs:
                line += f" (usa {', '.join(e.refs)})"
            if e.kind is EventKind.WARNING:
                line = f"{tag} AVISO: {e.title}"
            done.append(line)
            if e.why:
                why.append(f"{tag} {e.why}")
            if e.kind in (EventKind.STEP, EventKind.VALUE) and e.result is not None:
                values.append(f"{tag} {e.formula or e.title} = {show_value(e.result)}")
            for name, value in e.values if e.kind is EventKind.DECISION else ():
                values.append(f"{tag} {name} = {show_value(value)}")
        elif e.kind is EventKind.CHECK:
            c = e.check
            checks.append(CheckView(e.event_id, c.what, c.status.value, show_value(c.actual),
                                    show_value(c.expected), show_value(c.tolerance) if c.tolerance else "",
                                    c.detail))
            line = f"{tag} {c.status.value}: {c.what} — obtenido {show_value(c.actual)}, esperado {show_value(c.expected)}"
            if c.tolerance is not None:
                line += f" (tolerancia {show_value(c.tolerance)})"
            if c.detail:
                line += f"; {c.detail}"
            check_lines.append(line)
        elif e.kind is EventKind.RESULT:
            result.append(f"{tag} {e.title}: {show_value(e.result)}")
            for name, value in e.values:
                result.append(f"{tag} {name} = {show_value(value)}")
        elif e.kind is EventKind.ERROR:
            where = f" tras {', '.join(e.refs)}" if e.refs else ""
            result.append(f"{tag} ERROR {e.error.code} ({e.error.reason}){where}: {e.error.message}")
        if e.formula and e.kind is not EventKind.INPUT:
            formulas.append(f"{tag} {e.formula}")
    status = trace.verification
    check_lines.append(f"Resumen: {status.status.value} ({status.checks} comprobaciones, {status.failed} fallidas)")
    content = {"inputs": inputs, "steps": done, "why": why, "formulas": formulas, "values": values,
               "checks": check_lines, "result": result or ["(sin resultado)"]}
    sections = tuple(ExplanationSection(key, q, tuple(content[key]) or ("(nada registrado)",))
                     for key, q in QUESTIONS)
    return ExplanationView(trace.operation, trace.outcome.value, status.status.value, trace.digest(),
                           sections, tuple(steps), tuple(checks), trace.to_json())


def render_text(view: ExplanationView) -> str:
    out = [f"Explicación de {view.operation} — resultado {view.outcome}, verificación {view.verification}"]
    for s in view.sections:
        out.append("")
        out.append(s.question)
        out.extend(f"  {line}" for line in s.lines)
    out.append("")
    out.append(f"digest execution-trace/1: {view.digest}")
    return "\n".join(out)


def _md(text: str) -> str:
    """Escape Markdown/HTML-significant characters so recorded text is shown, never interpreted."""
    for ch in ("\\", "*", "_", "`", "[", "]", "<", ">", "#", "|"):
        text = text.replace(ch, "\\" + ch)
    return text


def render_markdown(view: ExplanationView) -> str:
    out = [f"# Explicación: {_md(view.operation)}", "",
           f"**Resultado:** {view.outcome} · **Verificación:** {view.verification}"]
    for s in view.sections:
        out += ["", f"## {s.question}", ""]
        out += [f"- {_md(line)}" for line in s.lines]
    out += ["", f"`execution-trace/1` digest: `{view.digest}`"]
    return "\n".join(out)
