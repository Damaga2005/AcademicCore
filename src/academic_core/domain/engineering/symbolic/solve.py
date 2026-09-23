# SPDX-License-Identifier: MIT
"""E0.1 linear equations solved by isolation, recording every transformation.

``solve_linear("3*x + 2 = x - 4", "x", log)`` performs, and records, only
the transformations that are really needed:

1. state the equation (both sides as parsed)
2. simplify each side into the exact normal form, if that changes it
3. subtract the variable term of the right-hand side from both sides
4. subtract the constant of the left-hand side from both sides
5. divide both sides by the coefficient of x; the last recorded
   transformation leaves ``x = value``
6. a zero coefficient is a recorded DECISION: identity (every
   x is a solution) or contradiction (no solution)

Only equations that are linear in the variable, with exact rational
coefficients, are accepted. Anything else raises
``UnsupportedError NO_RULE``, because there is no registered rule to
solve it step by step.

``verify`` substitutes the solution into the ORIGINAL sides and compares
them exactly (Fraction), with no tolerance.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.symbolic.expr import Expr, Num, depends, exact_value, invalid, no_rule, parse, substitute, text
from academic_core.domain.engineering.symbolic.normal import linear_parts, simplify
from academic_core.domain.engineering.symbolic.steps import StepLog

OP = "ecuación"


@dataclass(frozen=True)
class LinearSolution:
    lhs: Expr
    rhs: Expr
    status: str  # "UNIQUE" | "IDENTITY" | "NO_SOLUTION"
    value: Fraction | None
    last_step: int


def _f(v: Fraction) -> str:
    return str(v.numerator) if v.denominator == 1 else f"{v.numerator}/{v.denominator}"


def _p(v: Fraction) -> str:
    return _f(v) if v.denominator == 1 and v >= 0 else f"({_f(v)})"


def _side(a: Fraction, b: Fraction, var: str) -> str:
    """Text of a·var + b written the usual way."""
    if a == 0:
        return _f(b)
    lead = var if a == 1 else f"-{var}" if a == -1 else f"{_f(a)}*{var}"
    if b == 0:
        return lead
    return f"{lead} {'+' if b > 0 else '-'} {_f(abs(b))}"


def split_equation(source: str) -> tuple[Expr, Expr]:
    if not isinstance(source, str) or source.count("=") != 1:
        raise invalid("PARSE_ERROR", "an equation needs exactly one '='")
    left, right = source.split("=")
    return parse(left), parse(right)


def solve_linear(source: str, var: str, log: StepLog) -> LinearSolution:
    lhs, rhs = split_equation(source)
    if not depends(lhs, var) and not depends(rhs, var):
        raise invalid("DOMAIN", f"la ecuación no contiene la incógnita {var}")
    s = log.add(OP, "plantear la ecuación", source.strip(), f"{text(lhs)} = {text(rhs)}",
                explanation=f"Incógnita: {var}.")
    sides = []
    for name, side in (("izquierdo", lhs), ("derecho", rhs)):
        simple, rules = simplify(side, var, expand=True)
        if text(simple) != text(side):
            s = log.add(OP, f"simplificar el lado {name}", text(side), text(simple), substitution=", ".join(rules),
                        explanation="Forma normal exacta del lado: se agrupan términos semejantes.", uses=(s,))
        parts = linear_parts(simple, var)
        if parts is None:
            raise no_rule(f"la ecuación no es lineal en {var} con coeficientes numéricos (lado {name}: {text(simple)})")
        sides.append(parts)
    (a1, b1), (a2, b2) = sides
    current = f"{_side(a1, b1, var)} = {_side(a2, b2, var)}"
    if a2 != 0:
        a1, a2 = a1 - a2, Fraction(0)
        after = f"{_side(a1, b1, var)} = {_side(a2, b2, var)}"
        s = log.add(OP, "transponer el término en la incógnita", current, after,
                    substitution=f"restar {_side(sides[1][0], Fraction(0), var)} en ambos lados",
                    explanation="Sumar o restar lo mismo en ambos lados conserva la igualdad.", uses=(s,))
        current = after
    if b1 != 0:
        after = f"{_side(a1, Fraction(0), var)} = {_side(Fraction(0), b2 - b1, var)}"
        s = log.add(OP, "transponer el término independiente", current, after,
                    substitution=f"restar {_f(b1)} en ambos lados",
                    explanation="Sumar o restar lo mismo en ambos lados conserva la igualdad.", uses=(s,))
        b2, b1 = b2 - b1, Fraction(0)
        current = after
    if a1 == 0:
        status = "IDENTITY" if b2 == 0 else "NO_SOLUTION"
        last = log.add(OP, "decisión: coeficiente de la incógnita nulo", current,
                       f"todo {var} es solución" if status == "IDENTITY" else "sin solución",
                       substitution=f"0*{var} = {_f(b2)}",
                       explanation="0·x = 0 es una identidad; 0·x = c con c ≠ 0 es una contradicción.", uses=(s,))
        return LinearSolution(lhs, rhs, status, None, last)
    value = b2 / a1
    if a1 != 1:
        s = log.add(OP, "despejar: dividir ambos lados entre el coeficiente", current, f"{var} = {_f(value)}",
                    substitution=f"{_p(b2)} / {_p(a1)} = {_f(value)}",
                    explanation="Dividir ambos lados por el mismo número distinto de cero conserva la igualdad.",
                    uses=(s,))
    last = s  # the incógnita is isolated by the last recorded transformation
    return LinearSolution(lhs, rhs, "UNIQUE", value, last)


def verify(sol: LinearSolution, var: str) -> tuple[bool, Fraction | None, Fraction | None, str]:
    """(passed, left value, right value, substituted text) at the solution, exactly."""
    if sol.value is None:
        return False, None, None, ""
    left = substitute(sol.lhs, var, Num(sol.value))
    right = substitute(sol.rhs, var, Num(sol.value))
    lv, rv = exact_value(left), exact_value(right)
    return (lv is not None and lv == rv), lv, rv, f"{text(left)} = {text(right)}"
