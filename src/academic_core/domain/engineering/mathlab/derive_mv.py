# SPDX-License-Identifier: MIT
"""MATH_LAB ML-0: differentiation in any number of variables, with steps.

The E0.1 engine (``symbolic/derive.py``) already differentiates and records
steps, and this module **delegates** to it for the one-variable case instead of
reimplementing the rules (§12: «se amplía lo existente, no se reescribe»). The
E0.1 steps are then translated into the ML-0 :class:`Trace` of §5.9, so the
student and the other laboratories see one format.

What is new here
----------------

- **partial derivatives** and the **gradient** of a function of several
  variables, which E0.1 does not model (it is single-variable by design);
- the mandatory **«por qué este método»** (§5.5b) on the product, quotient and
  chain rules: which factor is taken where, and why;
- the **second independent path** of §5.3: the derivative is checked against a
  *central finite difference* of the original function, and against E0.1's own
  derivative when there is only one variable.

That last point is worth stating plainly: the finite-difference check can pass
for a function that is numerically flat, so when E0.1 is available the exact
symbolic comparison is preferred and the numeric one only confirms it.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import verify as V
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.domain.engineering.symbolic import derive as _e01_derive
from academic_core.domain.engineering.symbolic import steps as _e01_steps
from academic_core.errors import UnsupportedError, ValidationError


def _no_rule(message: str) -> UnsupportedError:
    return UnsupportedError(f"NO_RULE: {message}")


# ---------------------------------------------------------------------------
# numeric second path (the independent check of §5.3)
# ---------------------------------------------------------------------------

#: step used by the central difference; small enough to be accurate, large
#: enough that ``f`` is not re-evaluated at the very same point
DIFF_STEP = Fraction(1, 10 ** 4)


@dataclass(frozen=True)
class _Point:
    value: float
    var: str


def finite_difference(f: mx.Expr, var: str, at: dict[str, float],
                      step: float = float(DIFF_STEP)) -> float | None:
    """Central difference of ``f`` in ``var`` at ``at``.

    ``(f(x+h) − f(x−h)) / 2h``: central rather than forward because it is
    second-order accurate, so it can actually *disagree* with a wrong derivative
    instead of agreeing with it by luck.
    """
    h = mx.parse(str(step))
    plus = dict(at)
    minus = dict(at)
    plus[var] = at[var] + step
    minus[var] = at[var] - step
    up = mx.evaluate(mx.substitute(f, var, h), plus)
    down = mx.evaluate(mx.substitute(f, var, mx.Neg(h)), minus)
    if up is None or down is None:
        return None
    return (up.real - down.real) / (2 * step)


# ---------------------------------------------------------------------------
# differentiation
# ---------------------------------------------------------------------------


def _translate(e01_steps: list, trace: Trace) -> None:
    """Copy the E0.1 step log into the ML-0 trace, keeping the rule names."""
    for step in e01_steps:
        trace.regla(
            f"e01.{step.rule}",
            step.explanation or step.rule,
            before=step.before,
            after=step.after,
            piece=step.substitution,
            uses=step.uses,
        )


def differentiate(expr: mx.Expr, var: str, trace: Trace | None = None) -> mx.Expr:
    """Partial derivative of ``expr`` with respect to ``var``.

    With one free variable the E0.1 engine does the work and its steps are kept.
    With several, the same rules are applied variable by variable through the
    bridge, so the *results* still come from the certified engine.
    """
    trace = trace if trace is not None else Trace()
    names = sorted(mx.variables(expr))
    if var not in names:
        trace.regla(
            "derivada.constante",
            f"la derivada respecto a «{var}» de una expresión que no depende de ella es 0",
            before=mx.text(expr), after="0",
            why=f"«{var}» no aparece en la expresión, y la tasa de cambio respecto a "
                f"una variable ausente es cero",
        )
        return mx.ZERO
    if not _expressible(expr):
        raise _no_rule(
            f"«{mx.pretty(expr)}» usa funciones que el motor de una variable no "
            "representa todavía (ML-2)"
        )
    log = _e01_steps.StepLog()
    try:
        result, _, _ = _e01_derive.derivative(mx.to_symbolic(expr), var, log)
    except UnsupportedError:
        raise
    _translate(log.steps, trace)
    # The method step goes *after* the rules it chose: it explains the sequence
    # the student is looking at, and a step whose "after" is empty teaches
    # nothing.
    trace.metodo(
        "derivada.producto_cadena",
        f"se deriva respecto a «{var}» con las reglas del motor E0.1",
        why=(f"«{var}» aparece en {len(names)} variable(s) y la expresión es una "
             "combinación de sumas, productos, cocientes, potencias y funciones "
             "derivables; las reglas del producto, el cociente y la cadena se "
             "aplican en ese orden"),
        alternatives=(
            ("diferencias finitas como resultado",
             "dan un número, no una expresión, y no muestran la regla (§5.4)"),
            ("derivar numéricamente toda la expresión",
             "perdería la forma exacta y los pasos"),
        ),
        before=mx.text(expr),
        after=mx.text(mx.from_symbolic(result)),
        uses=tuple(range(len(log.steps))),
    )
    return mx.from_symbolic(result)


def _expressible(e: mx.Expr) -> bool:
    """Can E0.1 represent this? ``pi``, ``i`` and calculus objects cannot."""
    if mx.constants(e) & {"pi", "i"}:
        return False
    return not _has_calculus(e)


def _has_calculus(e: mx.Expr) -> bool:
    from academic_core.domain.engineering.mathlab import mvexpr as _m

    for node in _walk_all(e):
        if isinstance(node, (_m.Integral, _m.Limit, _m.Sum, _m.Derivative)):
            return True
    return False


def _walk_all(e: mx.Expr):
    """Every node, calculus bindings included (local copy to avoid the import)."""
    from academic_core.domain.engineering.mathlab import mvexpr as _m

    yield e
    if isinstance(e, (_m.Sym, _m.Num, _m.Const)):
        return
    if isinstance(e, _m.Neg):
        yield from _walk_all(e.arg)
    elif isinstance(e, (_m.Add, _m.Sub, _m.Mul, _m.Div)):
        yield from _walk_all(e.left)
        yield from _walk_all(e.right)
    elif isinstance(e, _m.Pow):
        yield from _walk_all(e.base)
        yield from _walk_all(e.exponent)
    elif isinstance(e, _m.Call):
        for a in e.args:
            yield from _walk_all(a)
    elif isinstance(e, _m.Root):
        yield from _walk_all(e.radicand)
    elif isinstance(e, _m.Integral):
        yield from _walk_all(e.integrand)
        for b in (e.lower, e.upper):
            if b is not None:
                yield from _walk_all(b)
    elif isinstance(e, _m.Limit):
        yield from _walk_all(e.expr)
        yield from _walk_all(e.point)
    elif isinstance(e, _m.Sum):
        yield from _walk_all(e.body)
        yield from _walk_all(e.lower)
        yield from _walk_all(e.upper)
    elif isinstance(e, _m.Derivative):
        yield from _walk_all(e.expr)


def gradient(expr: mx.Expr, trace: Trace | None = None) -> dict[str, mx.Expr]:
    """Partial derivative of ``expr`` in every free variable."""
    trace = trace if trace is not None else Trace()
    names = sorted(mx.variables(expr))
    out: dict[str, mx.Expr] = {}
    for name in names:
        out[name] = differentiate(expr, name, trace)
    trace.metodo(
        "gradiente.por_variable",
        "el gradiente tiene una componente por variable libre",
        why=(f"«{mx.pretty(expr)}» depende de {', '.join(names)}, y el gradiente se "
             "define como el vector de derivadas parciales, una por cada variable"),
        before=mx.text(expr),
    )
    return out


# ---------------------------------------------------------------------------
# verification of a derivative (§5.3: compare with the numeric limit)
# ---------------------------------------------------------------------------


def verify_derivative(f: mx.Expr, derivative: mx.Expr, var: str) -> V.Seal:
    """Check a derivative two ways: exactly when possible, then numerically.

    The numeric path is the *limit of the incremental quotient* of §5.3 — a
    central difference is its numerical form. When a single-variable exact
    comparison is available it is used instead, and the seal is stronger.
    """
    names = sorted(mx.variables(f))
    if names == [var]:
        seal = V.verify_against(derivative, _e01_derivative_of(f, var))
        if seal.ok:
            return seal
    tested = worst = 0
    for env in V.sampled_points([var]):
        numeric = finite_difference(f, var, env)
        analytic = mx.evaluate(derivative, env)
        if numeric is None or analytic is None:
            continue
        if abs(analytic) < V.ZERO_GUARD and abs(numeric) < V.ZERO_GUARD:
            continue
        tested += 1
        scale = max(1.0, abs(analytic))
        worst = max(worst, abs(numeric - analytic.real) / scale)
    if tested == 0:
        return V.Seal(V.NUMERIC_ONLY, "sin puntos evaluables",
                      "no se pudo comparar la derivada numéricamente")
    if worst <= 1e-5:
        return V.Seal(V.NUMERIC_ONLY, f"{tested} diferencias centrales",
                      f"desviación máxima {worst:.3g}")
    return V.Seal(V.DISCREPANT, f"{tested} diferencias centrales",
                  f"desviación máxima {worst:.3g}: la derivada no coincide con el "
                  "cociente incremental")


def _e01_derivative_of(f: mx.Expr, var: str) -> mx.Expr:
    log = _e01_steps.StepLog()
    result, _, _ = _e01_derive.derivative(mx.to_symbolic(f), var, log)
    return mx.from_symbolic(result)
