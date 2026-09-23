# SPDX-License-Identifier: MIT
"""E0.1 numeric evaluation of symbolic expressions through the CERTIFIED evaluator.

Verification only. The expression is printed in evaluator syntax
(``expr.code``) and run through ``equations.evaluate`` with dimensionless
Decimal quantities. There is no float and no second arithmetic engine.
Every free symbol must be bound; otherwise the value is ``None``, so a
name is never misread as a unit.

The certified evaluator only raises to integer powers. For verification a
power with a non-integer or symbolic exponent is written with the identity
``b^r = exp(r*log(b))`` (valid for b > 0; outside that domain the value is
``None``).
"""

from __future__ import annotations

from decimal import Decimal

from academic_core.domain.engineering.equations import evaluate, parse_equation
from academic_core.domain.engineering.symbolic.expr import Add, Div, Expr, Fn, Mul, Neg, Num, Pow, Sub, Sym, code, exact_value
from academic_core.domain.engineering.units import DIMENSIONLESS, Quantity, Unit

_ONE = Unit("1", "1", "", DIMENSIONLESS, Decimal(1))


def symbols(e: Expr) -> set[str]:
    if isinstance(e, Sym):
        return {e.name}
    if isinstance(e, Num):
        return set()
    if isinstance(e, (Neg, Fn)):
        return symbols(e.arg)
    if isinstance(e, Pow):
        return symbols(e.base) | symbols(e.exponent)
    if isinstance(e, (Add, Sub, Mul, Div)):
        return symbols(e.left) | symbols(e.right)
    return set()


def _evaluable(e: Expr) -> Expr:
    if isinstance(e, (Sym, Num)):
        return e
    if isinstance(e, Neg):
        return Neg(_evaluable(e.arg))
    if isinstance(e, Fn):
        return Fn(e.name, _evaluable(e.arg))
    if isinstance(e, Pow):
        base, exponent = _evaluable(e.base), _evaluable(e.exponent)
        k = exact_value(exponent)
        if k is not None and k.denominator == 1:
            return Pow(base, exponent)
        return Fn("exp", Mul(exponent, Fn("log", base)))
    return type(e)(_evaluable(e.left), _evaluable(e.right))


def value(e: Expr, env: dict[str, Decimal]) -> Decimal | None:
    """Decimal value via the certified evaluator, or None (unbound symbol / domain error)."""
    if not symbols(e) <= set(env):
        return None
    try:
        eq = parse_equation(f"y_e0 = {code(_evaluable(e))}")
        q = evaluate(eq, {k: Quantity(Decimal(v), _ONE) for k, v in env.items()})
    except (ValueError, ArithmeticError):
        return None
    return q.value if q.dimension == DIMENSIONLESS else None
