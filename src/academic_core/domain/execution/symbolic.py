# SPDX-License-Identifier: MIT
"""E0.1 integration of the symbolic engine: step-by-step mathematics as ExecutionTrace.

Operations:

- ``math.derivative``
- ``math.integral`` (indefinite, or definite when both limits are given)
- ``math.linear-equation``
- ``math.simplify``

The engine (``engineering.symbolic``) appends one ``Step`` per rule it
really applies. This module maps each one to exactly one STEP event,
with no event added or left out:

- title: the rule
- ``operation``, ``rule``, ``before``, ``after`` and, when the rule bound
  something, ``substitution`` values
- ``why``: the rule statement
- refs: the events of the steps whose results it consumes (the engine's
  ``uses``); a step that consumes nothing refs the parse event
- ``result``: ``after``

The steps of a strategy that was tried and abandoned (a substitution that
did not fit) are never in the log, so they are never shown. If no rule
applies, the ERROR event carries ``NO_RULE`` (AC-UNS-001). The steps done
before the failure stay in the trace; nothing is filled in.

Verification CHECKs are computed independently of the steps:

- derivative: central difference through the certified evaluator at
  fixed points, plus the normal-form equivalence of the raw and the
  simplified derivative
- integral: differentiate F (normal-form equivalence, else numeric
  comparison at fixed points); for a definite integral, also Simpson's
  rule (n = 64) against F(b) − F(a)
- linear equation: exact substitution into the original sides; for an
  identity or a contradiction, lhs − rhs in exact normal form
- simplify: normal-form equivalence plus numeric agreement at fixed points

A point where the expression is not defined is skipped, and the check
says so. If no point is usable, the check is ``NOT_APPLICABLE``.

Replay (``replay_math``) re-runs the engine from the recorded inputs.
"""

from __future__ import annotations

import re
from decimal import Decimal, localcontext
from fractions import Fraction

from academic_core.domain.engineering.symbolic.derive import derivative
from academic_core.domain.engineering.symbolic.expr import FUNCTIONS, Expr, Sub, exact_value, invalid, parse, text
from academic_core.domain.engineering.symbolic.integrate import antiderivative, definite
from academic_core.domain.engineering.symbolic.normal import equivalent, normal_expr
from academic_core.domain.engineering.symbolic.numeric import symbols, value
from academic_core.domain.engineering.symbolic.solve import solve_linear, verify
from academic_core.domain.engineering.symbolic.steps import StepLog
from academic_core.domain.execution.model import EventKind, ExecutionTrace, TraceRecorder, TraceValue, _invalid

DERIVATIVE = "math.derivative"
INTEGRAL = "math.integral"
LINEAR_EQUATION = "math.linear-equation"
SIMPLIFY = "math.simplify"
OPERATIONS = (DERIVATIVE, INTEGRAL, LINEAR_EQUATION, SIMPLIFY)

POINTS = (Decimal("0.7"), Decimal("1.3"), Decimal("2.9"))  # fixed verification points (deterministic)
H = Decimal("1e-6")  # central-difference step
DERIVATIVE_TOL = Decimal("1e-9")  # relative, for the central difference (truncation O(h^2))
EQUAL_TOL = Decimal("1e-20")  # relative, when comparing two exact-formula evaluations
SIMPSON_N = 64
SIMPSON_TOL = Decimal("1e-6")  # relative, Simpson with n = 64 is an approximation

_VAR_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,15}\Z")


def _variable(var: object) -> str:
    if not isinstance(var, str) or not _VAR_RE.fullmatch(var) or var in FUNCTIONS:
        raise _invalid("INVALID_INPUT", "the variable must be a plain name such as x")
    return var


def _limit(textual: str, name: str) -> Fraction:
    got = exact_value(parse(textual))
    if got is None:
        raise invalid("INVALID_INPUT", f"the {name} limit must be an exact number (e.g. 0, 1/2, -3, 2.5)")
    return got


def _rel(a: Decimal, b: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 50
        return abs(a - b) / max(Decimal(1), abs(b))


class _Steps:
    """Maps engine steps to STEP events, one for one."""

    def __init__(self, rec: TraceRecorder, anchor: str):
        self.rec, self.anchor, self.ids = rec, anchor, {}

    def emit(self, log: StepLog) -> None:
        for st in log.steps:
            if st.index in self.ids:
                continue
            values = [("operation", TraceValue.of_text(st.operation)), ("rule", TraceValue.of_text(st.rule)),
                      ("before", TraceValue.of_text(st.before)), ("after", TraceValue.of_text(st.after))]
            if st.substitution:
                values.append(("substitution", TraceValue.of_text(st.substitution)))
            refs = tuple(dict.fromkeys(self.ids[u] for u in st.uses)) or (self.anchor,)
            self.ids[st.index] = self.rec.event(
                EventKind.STEP, st.rule[:512], refs=refs, formula=f"{st.before} → {st.after}"[:512],
                why=st.explanation or None, values=tuple(values), result=TraceValue.of_text(st.after))

    def of(self, index: int) -> str:
        return self.ids[index]


def _start(operation: str, expression: str, var: str, extra=()) -> tuple[TraceRecorder, str, str]:
    rec = TraceRecorder(operation)
    src = rec.input("expression" if operation != LINEAR_EQUATION else "equation", TraceValue.of_text(expression),
                    "Enunciado recibido")
    rec.input("variable", TraceValue.of_text(var), "Variable")
    for name, v in extra:
        rec.input(name, TraceValue.of_text(v), f"Dato {name}")
    return rec, src, var


def _parse_step(rec: TraceRecorder, src: str, e: Expr, var: str) -> str:
    return rec.event(EventKind.STEP, "Analizar la expresión", refs=(src,), formula=text(e),
                     why="Analizador propio (sin eval): números exactos, nombres y funciones de la lista blanca.",
                     values=(("parsed", TraceValue.of_text(text(e))),
                             ("symbols", TraceValue.of_text(", ".join(sorted(symbols(e))) or "-"))))


def _fail(rec: TraceRecorder, steps: _Steps | None, log: StepLog | None, exc: Exception) -> None:
    if steps is not None and log is not None:
        steps.emit(log)  # the rules applied before the failure are real; they are kept, nothing is added
    rec.fail(exc, "La ejecución se detuvo", refs=tuple(r for r in (rec.last,) if r))


def _check_derivative(rec: TraceRecorder, e: Expr, d: Expr, var: str, ref: str) -> None:
    rows, worst, skipped = [], Decimal(0), []
    others = sorted((symbols(e) | symbols(d)) - {var})
    if others:
        rec.check("diferencia central en puntos fijos", TraceValue.of_text("-"), TraceValue.of_text("-"), None,
                  refs=(ref,), detail=f"no aplicable: la expresión tiene parámetros sin valor ({', '.join(others)})",
                  title="Comprobación: derivada numérica")
        return
    for p in POINTS:
        fp, fm, dp = value(e, {var: p + H}), value(e, {var: p - H}), value(d, {var: p})
        if fp is None or fm is None or dp is None:
            skipped.append(str(p))
            continue
        with localcontext() as ctx:
            ctx.prec = 50
            approx = (fp - fm) / (2 * H)
        err = _rel(dp, approx)
        worst = max(worst, err)
        rows.append(f"{var}={p}: f'={dp:.12g}, (f(x+h)-f(x-h))/2h={approx:.12g}")
    detail = "; ".join(rows) + (f"; puntos fuera del dominio: {', '.join(skipped)}" if skipped else "")
    rec.check("diferencia central en puntos fijos (h = 1e-6)", TraceValue.of_number(worst),
              TraceValue.of_number(Decimal(0)), (worst <= DERIVATIVE_TOL) if rows else None, refs=(ref,),
              tolerance=TraceValue.of_number(DERIVATIVE_TOL), detail=detail[:512] or "sin puntos evaluables",
              title="Comprobación: derivada numérica")


def _check_same(rec: TraceRecorder, a: Expr, b: Expr, var: str, what: str, ref: str, title: str) -> None:
    """Normal-form equivalence; if not provable that way, numeric agreement at fixed points."""
    if equivalent(a, b, var):
        rec.check(what, TraceValue.of_text(text(normal_expr(a, var))), TraceValue.of_text(text(normal_expr(b, var))),
                  True, refs=(ref,), detail="demostrado: la forma normal exacta de la diferencia es 0", title=title)
        return
    rows, worst = [], Decimal(0)
    others = sorted((symbols(a) | symbols(b)) - {var})
    for p in POINTS if not others else ():
        va, vb = value(a, {var: p}), value(b, {var: p})
        if va is None or vb is None:
            continue
        err = _rel(va, vb)
        worst = max(worst, err)
        rows.append(f"{var}={p}: {va:.12g} vs {vb:.12g}")
    rec.check(what, TraceValue.of_number(worst), TraceValue.of_number(Decimal(0)),
              (worst <= EQUAL_TOL) if rows else None, refs=(ref,), tolerance=TraceValue.of_number(EQUAL_TOL),
              detail=("numérica (la forma normal no basta, p. ej. identidades con abs/log): " + "; ".join(rows))[:512]
              if rows else "no aplicable: ningún punto evaluable", title=title)


def explain_derivative(expression: str, variable: str = "x") -> ExecutionTrace:
    var = _variable(variable)
    rec, src, var = _start(DERIVATIVE, expression, var)
    steps = log = None
    try:
        e = parse(expression)
        anchor = _parse_step(rec, src, e, var)
        log = StepLog()
        steps = _Steps(rec, anchor)
        raw, simple, last = derivative(e, var, log)
        steps.emit(log)
        result = rec.event(EventKind.RESULT, f"Derivada d/d{var}", refs=(steps.of(last),),
                           formula=f"d/d{var}[{text(e)}] = {text(simple)}", result=TraceValue.of_text(text(simple)))
        _check_same(rec, raw, simple, var, "la simplificación conserva la derivada", result,
                    "Comprobación: simplificación equivalente")
        _check_derivative(rec, e, simple, var, result)
    except ValueError as exc:
        _fail(rec, steps, log, exc)
    return rec.finish()


def explain_integral(expression: str, variable: str = "x", lower: str | None = None,
                     upper: str | None = None) -> ExecutionTrace:
    var = _variable(variable)
    if (lower is None) != (upper is None):
        raise _invalid("INVALID_INPUT", "a definite integral needs both limits")
    extra = (("lower", lower), ("upper", upper)) if lower is not None else ()
    rec, src, var = _start(INTEGRAL, expression, var, extra)
    steps = log = None
    try:
        e = parse(expression)
        anchor = _parse_step(rec, src, e, var)
        log = StepLog()
        steps = _Steps(rec, anchor)
        if lower is None:
            _raw, F, last = antiderivative(e, var, log)
            steps.emit(log)
            result = rec.event(EventKind.RESULT, "Primitiva", refs=(steps.of(last),),
                               formula=f"∫{text(e)} d{var} = {text(F)} + C",
                               result=TraceValue.of_text(f"{text(F)} + C"))
        else:
            a, b = _limit(lower, "lower"), _limit(upper, "upper")
            F, area, last = definite(e, var, a, b, log)
            steps.emit(log)
            shown = (str(area.numerator) if area.denominator == 1 else f"{area.numerator}/{area.denominator}") \
                if isinstance(area, Fraction) else str(area)
            result = rec.event(EventKind.RESULT, "Integral definida", refs=(steps.of(last),),
                               formula=f"∫_{lower}^{upper} {text(e)} d{var} = {shown}",
                               result=TraceValue.of_text(shown))
        scratch = StepLog()
        _r, dF, _s = derivative(F, var, scratch)
        _check_same(rec, dF, e, var, "d/dx F = integrando", result, "Comprobación: derivar la primitiva")
        if lower is not None:
            _check_simpson(rec, e, var, a, b, area, result)
    except ValueError as exc:
        _fail(rec, steps, log, exc)
    return rec.finish()


def _check_simpson(rec: TraceRecorder, e: Expr, var: str, a: Fraction, b: Fraction, area, ref: str) -> None:
    with localcontext() as ctx:
        ctx.prec = 50
        da, db = Decimal(a.numerator) / Decimal(a.denominator), Decimal(b.numerator) / Decimal(b.denominator)
        h = (db - da) / SIMPSON_N
        total = Decimal(0)
        for i in range(SIMPSON_N + 1):
            fx = value(e, {var: da + i * h})
            if fx is None:
                rec.check("Simpson compuesto (n = 64)", TraceValue.of_text("-"), TraceValue.of_text("-"), None,
                          refs=(ref,), detail="no aplicable: el integrando no es evaluable en un nodo",
                          title="Comprobación: integración numérica independiente")
                return
            total += fx * (1 if i in (0, SIMPSON_N) else 4 if i % 2 else 2)
        approx = total * h / 3
        exact = area if isinstance(area, Decimal) else Decimal(area.numerator) / Decimal(area.denominator)
        err = _rel(approx, exact)
    rec.check("Simpson compuesto (n = 64) frente a F(b) - F(a)", TraceValue.of_number(err),
              TraceValue.of_number(Decimal(0)), err <= SIMPSON_TOL, refs=(ref,),
              tolerance=TraceValue.of_number(SIMPSON_TOL),
              detail=f"Simpson ≈ {approx:.15g}; Barrow = {exact:.15g}",
              title="Comprobación: integración numérica independiente")


def explain_linear_equation(equation: str, variable: str = "x") -> ExecutionTrace:
    var = _variable(variable)
    rec, src, var = _start(LINEAR_EQUATION, equation, var)
    steps = log = None
    try:
        anchor = rec.event(EventKind.STEP, "Analizar la ecuación", refs=(src,), formula=equation.strip()[:512],
                           why="Analizador propio (sin eval): una sola igualdad, lados con números exactos.")
        log = StepLog()
        steps = _Steps(rec, anchor)
        sol = solve_linear(equation, var, log)
        steps.emit(log)
        if sol.status == "UNIQUE":
            v = sol.value
            shown = str(v.numerator) if v.denominator == 1 else f"{v.numerator}/{v.denominator}"
            result = rec.event(EventKind.RESULT, "Solución", refs=(steps.of(sol.last_step),), formula=f"{var} = {shown}",
                               result=TraceValue.of_text(f"{var} = {shown}"))
            ok, lv, rv, substituted = verify(sol, var)
            rec.check("sustitución en la ecuación original (exacta)",
                      TraceValue.of_text("-" if lv is None else str(lv)), TraceValue.of_text("-" if rv is None else str(rv)),
                      ok, refs=(result,), detail=f"{substituted}"[:512], title="Comprobación: verificar la solución")
        else:
            label = f"todo {var} es solución" if sol.status == "IDENTITY" else "sin solución"
            result = rec.event(EventKind.RESULT, "Conclusión", refs=(steps.of(sol.last_step),), formula=label,
                               result=TraceValue.of_text(label))
            diff = normal_expr(Sub(sol.lhs, sol.rhs), var)  # exact: lhs - rhs in normal form
            constant = exact_value(diff)
            ok = constant is not None and ((constant == 0) == (sol.status == "IDENTITY"))
            rec.check("lado izquierdo - lado derecho (forma normal exacta)", TraceValue.of_text(text(diff)),
                      TraceValue.of_text("0" if sol.status == "IDENTITY" else "constante distinta de 0"), ok,
                      refs=(result,), title="Comprobación: identidad o contradicción")
    except ValueError as exc:
        _fail(rec, steps, log, exc)
    return rec.finish()


def explain_simplify(expression: str, variable: str = "x") -> ExecutionTrace:
    var = _variable(variable)
    rec, src, var = _start(SIMPLIFY, expression, var)
    steps = log = None
    try:
        e = parse(expression)
        anchor = _parse_step(rec, src, e, var)
        log = StepLog()
        steps = _Steps(rec, anchor)
        simple = normal_expr(e, var, log, expand=True)
        steps.emit(log)
        last = steps.of(log.steps[-1].index) if log.steps else anchor
        result = rec.event(EventKind.RESULT, "Expresión simplificada", refs=(last,),
                           formula=f"{text(e)} = {text(simple)}", result=TraceValue.of_text(text(simple)))
        if not log.steps:
            rec.event(EventKind.DECISION, "Sin cambios", refs=(anchor,),
                      why="Ninguna regla del simplificador cambia la expresión: ya está en forma normal.")
        _check_same(rec, e, simple, var, "la expresión simplificada es equivalente a la original", result,
                    "Comprobación: equivalencia")
    except ValueError as exc:
        _fail(rec, steps, log, exc)
    return rec.finish()


def replay_math(trace: ExecutionTrace) -> ExecutionTrace:
    """Re-run the engine from the inputs recorded in ``trace``."""
    if not isinstance(trace, ExecutionTrace) or trace.operation not in OPERATIONS:
        raise _invalid("INVALID_TRACE", "not a math.* trace")
    inputs = {k: v.text for k, v in trace.inputs}
    if trace.operation == DERIVATIVE:
        return explain_derivative(inputs.get("expression", ""), inputs.get("variable", ""))
    if trace.operation == INTEGRAL:
        return explain_integral(inputs.get("expression", ""), inputs.get("variable", ""),
                                inputs.get("lower"), inputs.get("upper"))
    if trace.operation == LINEAR_EQUATION:
        return explain_linear_equation(inputs.get("equation", ""), inputs.get("variable", ""))
    return explain_simplify(inputs.get("expression", ""), inputs.get("variable", ""))
