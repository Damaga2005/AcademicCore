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

E0.1 step-by-step lessons (``ExplanationView.lessons``). Each lesson is
exactly one recorded event, never a merge, a split or an addition:

    Paso N / Tipo / Regla / Entrada / Transformación / Salida / Explicación / Verificación

- **Tipo**: the recorded ``operation`` of a symbolic step, else the
  phase of the event (Datos, Fórmula, Conversión de unidades,
  Sustitución, Cálculo, Decisión, Aviso, Resultado, Verificación).
- **Regla**: the recorded ``rule``, else the event title.
- **Entrada**: the recorded ``before``, else the values of the facts the
  event consumed (its refs).
- **Transformación**: the recorded ``substitution``, else the formula.
- **Salida**: the recorded ``after`` or result, else its values.
- **Explicación**: the recorded ``why``.
- **Verificación**: the CHECK events whose refs reach this event through
  the recorded causal chain, with their status. A step no check depends
  on says so ("sin comprobación que dependa de este paso").

Lessons exist for the E0.1 operations and for traces recorded in
pedagogical mode. For E0 traces the list is empty and the text output is
unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

from academic_core.domain.execution import EventKind, ExecutionTrace, TraceValue, canonical_decimal, verification_kind

KIND_TEXT = {"SYMBOLIC": "verificación simbólica/exacta", "NUMERIC": "verificación numérica, no es una demostración",
             "NONE": "sin verificación"}
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
    kind: str = ""  # E0.1-R+: SYMBOLIC / NUMERIC / NONE for labelled equivalence checks, "" otherwise


@dataclass(frozen=True)
class ExplanationSection:
    key: str
    question: str
    lines: tuple[str, ...]


@dataclass(frozen=True)
class LessonView:
    number: int
    event_id: str
    kind: str  # Tipo
    rule: str  # Regla
    input: str  # Entrada
    transformation: str  # Transformación
    output: str  # Salida
    explanation: str  # Explicación
    verification: str  # Verificación


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
    lessons: tuple[LessonView, ...] = ()


LESSON_OPERATIONS = ("math.derivative", "math.integral", "math.linear-equation", "math.simplify",
                     "engineering.gum", "engineering.nonlinear-dc", "control.margins",
                     # E0.2 analog engineering
                     "engineering.linear-dc", "engineering.dc-sweep", "engineering.ac", "engineering.transient",
                     "control.tf-point", "lab.run")
LESSON_FIELDS = ("Paso", "Tipo", "Regla", "Entrada", "Transformación", "Salida", "Explicación", "Verificación")
MAX_LESSON_TEXT = 400


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
                                    c.detail, verification_kind(c)))
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
                           sections, tuple(steps), tuple(checks), trace.to_json(), _lessons(trace))


def wants_lessons(trace: ExecutionTrace) -> bool:
    modes = {name: v.text for name, v in trace.inputs if name in ("e0.mode", "mode")}
    return trace.operation in LESSON_OPERATIONS or "pedagogical" in modes.values()


def _clip(text: str) -> str:
    return text if len(text) <= MAX_LESSON_TEXT else text[:MAX_LESSON_TEXT - 1] + "…"


def _phase(e) -> str:
    names = dict(e.values)
    if "operation" in names and "rule" in names:
        return show_value(names["operation"])
    if e.kind is EventKind.NORMALIZATION:
        return "Datos"
    if e.kind is EventKind.VALUE:
        return "Dato"
    if e.kind is EventKind.CHECK:
        return "Verificación"
    if e.kind is EventKind.RESULT:
        return "Resultado"
    if e.kind is EventKind.DECISION:
        return "Decisión"
    if e.kind is EventKind.WARNING:
        return "Aviso"
    if e.kind is EventKind.ERROR:
        return "Error"
    title = e.title.lower()
    if title.startswith("analizar") or title in ("modelo de medida", "función de lazo", "leer el circuito"):
        return "Fórmula"
    if title.startswith("conversión"):
        return "Conversión de unidades"
    if title.startswith("sustitución"):
        return "Sustitución"
    return "Cálculo"


def _lessons(trace: ExecutionTrace) -> tuple[LessonView, ...]:
    if not wants_lessons(trace):
        return ()
    # which checks depend on each event: walk every CHECK's refs back through the recorded causal chain
    covered: dict[str, list[str]] = {}
    for c in trace.checks():
        seen, stack = set(), list(c.refs)
        while stack:
            r = stack.pop()
            if r in seen:
                continue
            seen.add(r)
            stack.extend(trace.event(r).refs)
        for r in seen:
            covered.setdefault(r, []).append(f"{c.event_id} {c.check.status.value}")
    out = []
    for e in trace.events:
        if e.kind is EventKind.INPUT:
            continue
        names = dict(e.values)
        symbolic = "rule" in names and "before" in names
        if e.kind is EventKind.CHECK:
            c = e.check
            entry = show_value(c.actual)
            transformation = c.what
            output = f"{c.status.value} (esperado {show_value(c.expected)}"
            output += f", tolerancia {show_value(c.tolerance)})" if c.tolerance is not None else ")"
            kind = verification_kind(c)
            verification = f"{e.event_id} {c.status.value}" + (f" ({KIND_TEXT[kind]})" if kind else "")
            explanation = c.detail
        elif e.kind is EventKind.ERROR:
            entry = "; ".join(_consumed(trace, r) for r in e.refs)
            transformation, output = "", f"{e.error.code} {e.error.reason}"
            explanation, verification = e.error.message, "—"
        else:
            if symbolic:
                entry = show_value(names["before"])
                transformation = show_value(names["substitution"]) if "substitution" in names else ""
                output = show_value(names["after"])
            else:
                entry = "; ".join(_consumed(trace, r) for r in e.refs)
                transformation = e.formula or ""
                output = show_value(e.result) if e.result is not None else "; ".join(
                    f"{n} = {show_value(v)}" for n, v in e.values)
            explanation = e.why or ""
            cover = covered.get(e.event_id)
            verification = ("cubierto por " + ", ".join(cover)) if cover else "sin comprobación que dependa de este paso"
        rule = show_value(names["rule"]) if symbolic else (e.check.what if e.kind is EventKind.CHECK else e.title)
        out.append(LessonView(len(out) + 1, e.event_id, _phase(e), _clip(rule), _clip(entry), _clip(transformation),
                              _clip(output), _clip(explanation), _clip(verification)))
    return tuple(out)


def lesson_lines(lesson: LessonView) -> tuple[str, ...]:
    """The eight labelled lines of one lesson (empty fields shown as —)."""
    values = (f"{lesson.number} [{lesson.event_id}]", lesson.kind, lesson.rule, lesson.input, lesson.transformation,
              lesson.output, lesson.explanation, lesson.verification)
    return tuple(f"{label}: {value or '—'}" for label, value in zip(LESSON_FIELDS, values))


def render_text(view: ExplanationView) -> str:
    out = [f"Explicación de {view.operation} — resultado {view.outcome}, verificación {view.verification}"]
    for s in view.sections:
        out.append("")
        out.append(s.question)
        out.extend(f"  {line}" for line in s.lines)
    if view.lessons:
        out.append("")
        out.append("Paso a paso")
        for lesson in view.lessons:
            out.append("")
            out.extend(f"  {line}" for line in lesson_lines(lesson))
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
    if view.lessons:
        out += ["", "## Paso a paso"]
        for lesson in view.lessons:
            out += ["", f"### Paso {lesson.number}", ""]
            out += [f"- {_md(line)}" for line in lesson_lines(lesson)[1:]]
    out += ["", f"`execution-trace/1` digest: `{view.digest}`"]
    return "\n".join(out)
