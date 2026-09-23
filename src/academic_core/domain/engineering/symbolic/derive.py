# SPDX-License-Identifier: MIT
"""E0.1 symbolic differentiation that records every rule it applies.

``differentiate(expr, var, log)`` walks the expression as written. At
each node it applies exactly one registered rule and appends it to the
``StepLog``. Composite rules are recorded in their pedagogical sub-steps,
because the engine really performs them in that order:

- **Product:** identify u and v → u' → v' → substitute into u'v + uv'.
- **Quotient:** identify u and v → u' → v' → substitute into
  (u'v − uv')/v².
- **Chain:** identify the outer and inner functions → differentiate the
  outer → differentiate the inner → substitute f'(u)·u'.
- **Power:** d/dx xⁿ = n·xⁿ⁻¹, applied directly or through the chain
  rule.

The table covers sin, cos, tan, exp, log (ln) and sqrt, plus constants,
the identity, sums and differences, constant factors and negation.
Anything outside the table (e.g. u(x)^v(x)) raises
``UnsupportedError NO_RULE``; no step is ever invented.
"""

from __future__ import annotations

from fractions import Fraction

from academic_core.domain.engineering.symbolic.expr import (
    ONE,
    ZERO,
    Add,
    Div,
    Expr,
    Fn,
    Mul,
    Neg,
    Num,
    Pow,
    Sub,
    Sym,
    depends,
    exact_value,
    no_rule,
    text,
)
from academic_core.domain.engineering.symbolic.steps import StepLog

OP = "derivada"

# d/du f(u) for the table, as data: (rule name, derivative builder, statement)
_TABLE = {
    "sin": ("tabla: d/du sin(u) = cos(u)", lambda u: Fn("cos", u)),
    "cos": ("tabla: d/du cos(u) = -sin(u)", lambda u: Neg(Fn("sin", u))),
    "tan": ("tabla: d/du tan(u) = 1/cos(u)^2", lambda u: Div(ONE, Pow(Fn("cos", u), Num(Fraction(2))))),
    "exp": ("tabla: d/du exp(u) = exp(u)", lambda u: Fn("exp", u)),
    "log": ("tabla: d/du log(u) = 1/u", lambda u: Div(ONE, u)),
    "sqrt": ("tabla: d/du sqrt(u) = 1/(2*sqrt(u))", lambda u: Div(ONE, Mul(Num(Fraction(2)), Fn("sqrt", u)))),
    "abs": ("tabla: d/du abs(u) = u/abs(u) (u ≠ 0)", lambda u: Div(u, Fn("abs", u))),
}


def differentiate(e: Expr, var: str, log: StepLog) -> tuple[Expr, int]:
    """Return (unsimplified derivative, index of the step that produced it)."""
    if not depends(e, var):
        return ZERO, log.add(OP, "derivada de una constante", f"d/d{var}[{text(e)}]", "0",
                             explanation="La derivada de una constante es 0.")
    if isinstance(e, Sym):
        return ONE, log.add(OP, "derivada de la variable", f"d/d{var}[{var}]", "1",
                            explanation=f"d/d{var} {var} = 1.")
    if isinstance(e, Neg):
        d, s = differentiate(e.arg, var, log)
        out = Neg(d)
        return out, log.add(OP, "cambio de signo", f"d/d{var}[{text(e)}]", text(out),
                            explanation="(-u)' = -u'.", uses=(s,))
    if isinstance(e, (Add, Sub)):
        dl, sl = differentiate(e.left, var, log)
        dr, sr = differentiate(e.right, var, log)
        out = Add(dl, dr) if isinstance(e, Add) else Sub(dl, dr)
        rule = "regla de la suma" if isinstance(e, Add) else "regla de la resta"
        return out, log.add(OP, rule, f"d/d{var}[{text(e)}]", text(out),
                            explanation="(u ± v)' = u' ± v': se deriva término a término.", uses=(sl, sr))
    if isinstance(e, Mul):
        return _product(e, var, log)
    if isinstance(e, Div):
        return _quotient(e, var, log)
    if isinstance(e, Pow):
        return _power(e, var, log)
    if isinstance(e, Fn):
        return _function(e, var, log)
    raise no_rule(f"no hay regla de derivación para {text(e)}")  # pragma: no cover


def _product(e: Mul, var: str, log: StepLog) -> tuple[Expr, int]:
    u, v = e.left, e.right
    if not depends(u, var) or not depends(v, var):
        const, fx = (u, v) if not depends(u, var) else (v, u)
        d, s = differentiate(fx, var, log)
        out = Mul(const, d)
        return out, log.add(OP, "factor constante", f"d/d{var}[{text(e)}]", text(out),
                            substitution=f"c = {text(const)}",
                            explanation="(c·u)' = c·u': la constante sale de la derivada.", uses=(s,))
    s0 = log.add(OP, "regla del producto: identificar factores", text(e), f"u = {text(u)}, v = {text(v)}",
                 explanation="(u·v)' = u'·v + u·v'")
    du, s1 = differentiate(u, var, log)
    dv, s2 = differentiate(v, var, log)
    out = Add(Mul(du, v), Mul(u, dv))
    return out, log.add(OP, "regla del producto: sustituir", "u'·v + u·v'", text(out),
                        substitution=f"u' = {text(du)}, v' = {text(dv)}",
                        explanation="Se sustituyen u, v, u' y v' en u'·v + u·v'.", uses=(s0, s1, s2))


def _quotient(e: Div, var: str, log: StepLog) -> tuple[Expr, int]:
    u, v = e.left, e.right
    if not depends(v, var):
        d, s = differentiate(u, var, log)
        out = Div(d, v)
        return out, log.add(OP, "factor constante (división por constante)", f"d/d{var}[{text(e)}]", text(out),
                            substitution=f"c = 1/({text(v)})", explanation="(u/c)' = u'/c.", uses=(s,))
    s0 = log.add(OP, "regla del cociente: identificar numerador y denominador", text(e),
                 f"u = {text(u)}, v = {text(v)}", explanation="(u/v)' = (u'·v - u·v')/v^2")
    du, s1 = differentiate(u, var, log)
    dv, s2 = differentiate(v, var, log)
    out = Div(Sub(Mul(du, v), Mul(u, dv)), Pow(v, Num(Fraction(2))))
    return out, log.add(OP, "regla del cociente: sustituir", "(u'·v - u·v')/v^2", text(out),
                        substitution=f"u' = {text(du)}, v' = {text(dv)}",
                        explanation="Se sustituyen u, v, u' y v' en (u'·v - u·v')/v^2.", uses=(s0, s1, s2))


def _power(e: Pow, var: str, log: StepLog) -> tuple[Expr, int]:
    base, exponent = e.base, e.exponent
    if depends(exponent, var):
        a = exact_value(base)
        if depends(base, var) or a is None or a <= 0:
            raise no_rule(f"no hay regla registrada para derivar {text(e)} (base y exponente variables)")
        s0 = log.add(OP, "exponencial de base constante: identificar", text(e),
                     f"a = {text(base)}, u = {text(exponent)}", explanation="(a^u)' = a^u·log(a)·u'")
        du, s1 = differentiate(exponent, var, log)
        out = Mul(Mul(e, Fn("log", base)), du)
        return out, log.add(OP, "exponencial de base constante: sustituir", "a^u·log(a)·u'", text(out),
                            substitution=f"u' = {text(du)}", uses=(s0, s1))
    n = exponent
    if isinstance(base, Sym) and base.name == var:
        out = Mul(n, Pow(base, Sub(n, ONE)))
        return out, log.add(OP, "regla de la potencia", f"d/d{var}[{text(e)}]", text(out),
                            substitution=f"n = {text(n)}", explanation=f"d/d{var} {var}^n = n·{var}^(n-1)")
    s0 = log.add(OP, "regla de la cadena: identificar función exterior e interior", text(e),
                 f"exterior: u^{text(n)}; interior: u = {text(base)}", explanation="(f(g))' = f'(g)·g'")
    outer = Mul(n, Pow(base, Sub(n, ONE)))
    s1 = log.add(OP, "derivar la exterior (regla de la potencia)", f"u^{text(n)}", f"{text(n)}*u^({text(n)} - 1)",
                 substitution=f"n = {text(n)}", explanation="d/du u^n = n·u^(n-1)")
    dg, s2 = differentiate(base, var, log)
    out = Mul(outer, dg)
    return out, log.add(OP, "regla de la cadena: sustituir", "f'(u)·u'", text(out),
                        substitution=f"u = {text(base)}, u' = {text(dg)}",
                        explanation="Se multiplica la derivada exterior, evaluada en la interior, por la derivada interior.",
                        uses=(s0, s1, s2))


def _function(e: Fn, var: str, log: StepLog) -> tuple[Expr, int]:
    rule, builder = _TABLE[e.name]
    inner = e.arg
    if isinstance(inner, Sym) and inner.name == var:
        out = builder(inner)
        return out, log.add(OP, rule, f"d/d{var}[{text(e)}]", text(out), explanation="Derivada inmediata de la tabla.")
    s0 = log.add(OP, "regla de la cadena: identificar función exterior e interior", text(e),
                 f"exterior: {e.name}(u); interior: u = {text(inner)}", explanation="(f(g))' = f'(g)·g'")
    outer = builder(inner)
    s1 = log.add(OP, f"derivar la exterior ({rule})", f"{e.name}(u)", text(builder(Sym("u"))),
                 explanation="Derivada de la función exterior respecto de u.")
    dg, s2 = differentiate(inner, var, log)
    out = Mul(outer, dg)
    return out, log.add(OP, "regla de la cadena: sustituir", "f'(u)·u'", text(out),
                        substitution=f"u = {text(inner)}, u' = {text(dg)}",
                        explanation="Se sustituye u por la función interior y se multiplica por su derivada.",
                        uses=(s0, s1, s2))


def derivative(e: Expr, var: str, log: StepLog) -> tuple[Expr, Expr, int]:
    """(raw derivative, simplified derivative, index of the last step: simplification if any)."""
    from academic_core.domain.engineering.symbolic.normal import simplify

    raw, top = differentiate(e, var, log)
    simple, rules = simplify(raw, var)
    if text(simple) == text(raw):
        return raw, simple, top  # nothing to simplify: no step is recorded
    step = log.add("simplificación", ", ".join(rules), text(raw), text(simple),
                   explanation="Forma normal exacta: se agrupan términos y se pliegan constantes.", uses=(top,))
    return raw, simple, step
