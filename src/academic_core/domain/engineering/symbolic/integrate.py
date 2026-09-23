# SPDX-License-Identifier: MIT
"""E0.1 symbolic integration that records every rule it applies.

``integrate(expr, var, log)`` tries the registered strategies in a fixed
order and records the one that really produced the antiderivative:

1. constant: ∫c dx = c·x
2. linearity: ∫(u ± v) = ∫u ± ∫v, and ∫(-u) = -∫u
3. power rule: c·xⁿ, when the integrand is a monomial in x (the rewrite
   into c·xⁿ is recorded if it was written differently); n = -1 gives
   log(abs(x))
4. constant factor: ∫c·u = c·∫u, ∫u/c = (1/c)·∫u
5. table: sin, cos, tan, exp, sqrt of the variable; E0.1-R+: aˣ (a > 0,
   a ≠ 1) and 1/cos(x)²
6. change of variable u = g(x), when the rest of the integrand is a
   constant multiple k·g'(x). This covers the linear case (ax + b) and the
   general one. g' comes from the derivation engine, whose steps are
   recorded too.
7. integration by parts: log(x)·xⁿ, and xⁿ·exp/sin/cos(ax + b)
8. E0.1-R+: sqrt(u) rewritten as u^(1/2) (recorded, valid for u ≥ 0)
   when nothing above applied; then rewrite into the exact normal form
   (expanding products), recorded, and integrate that
9. otherwise ``UnsupportedError NO_RULE``

Strategies 6 and 7 are tentative: they run on a scratch ``StepLog``, and
only a strategy that succeeds has its steps merged into the real log. The
steps of failed attempts are never shown. Recursion is bounded by
``MAX_DEPTH``.

``antiderivative`` adds the final simplification and the ``+ C`` step.
``definite`` applies Barrow's rule: F(b), then F(a), then the difference.
The values are exact rationals when possible; otherwise they are
Decimals computed by the certified evaluator.
"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

from academic_core.domain.engineering.symbolic.derive import derivative
from academic_core.domain.engineering.symbolic.expr import (
    ONE,
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
    invalid,
    no_rule,
    substitute,
    text,
)
from academic_core.domain.engineering.symbolic.normal import _poly, constant_ratio, linear_parts, simplify
from academic_core.domain.engineering.symbolic.numeric import symbols, value
from academic_core.domain.engineering.symbolic.steps import StepLog
from academic_core.errors import UnsupportedError

OP = "integral"
MAX_DEPTH = 8

# ∫ f(u) du for the table: (rule name, antiderivative builder)
_TABLE = {
    "sin": ("tabla: ∫sin(u) du = -cos(u)", lambda u: Neg(Fn("cos", u))),
    "cos": ("tabla: ∫cos(u) du = sin(u)", lambda u: Fn("sin", u)),
    "exp": ("tabla: ∫exp(u) du = exp(u)", lambda u: Fn("exp", u)),
    "tan": ("tabla: ∫tan(u) du = -log(abs(cos(u)))", lambda u: Neg(Fn("log", Fn("abs", Fn("cos", u))))),
    "sqrt": ("tabla: ∫sqrt(u) du = 2*u^(3/2)/3",
             lambda u: Div(Mul(Num(Fraction(2)), Pow(u, Num(Fraction(3, 2)))), Num(Fraction(3)))),
}


def _integral(e: Expr, var: str) -> str:
    return f"∫{text(e)} d{var}"


def _k(c: Fraction) -> Num:
    return Num(c)


def _monomial(e: Expr, var: str) -> tuple[Fraction, Fraction] | None:
    """(c, n) when e is exactly c·varⁿ in normal form (n ≠ 0), else None."""
    p = _poly(e, var, None, 0)
    if len(p.terms) != 1:
        return None
    (m, c), = p.terms.items()
    if len(m) == 1 and m[0][0] == var:
        return c, m[0][1]
    return None


def _power_expr(c: Fraction, n: Fraction, var: str) -> Expr:
    x = Sym(var)
    body = x if n == 1 else Pow(x, Num(n))
    return body if c == 1 else Mul(Num(c), body)


def _power_rule(c: Fraction, n: Fraction, var: str, log: StepLog, uses=()) -> tuple[Expr, int]:
    x = Sym(var)
    written = _power_expr(c, n, var)
    if n == -1:
        out = Fn("log", Fn("abs", x))
        if c != 1:
            out = Mul(Num(c), out)
        return out, log.add(OP, "potencia n = -1: ∫x^(-1) dx = log(abs(x))", _integral(written, var), text(out),
                            substitution=f"c = {c}" if c != 1 else "",
                            explanation="La regla de la potencia no vale para n = -1; ∫1/x dx = log|x|.", uses=uses)
    m = n + 1
    out = Div(Mul(Num(c), Pow(x, Num(m))) if c != 1 else Pow(x, Num(m)), Num(m))
    return out, log.add(OP, "regla de la potencia", _integral(written, var), text(out),
                        substitution=f"n = {n}, n + 1 = {m}" + (f", c = {c}" if c != 1 else ""),
                        explanation="∫x^n dx = x^(n+1)/(n+1)  (n ≠ -1)", uses=uses)


def _factors(e: Expr) -> list[tuple[Expr, int]]:
    """Flatten a written product/quotient into (factor, ±1)."""
    if isinstance(e, Mul):
        return _factors(e.left) + _factors(e.right)
    if isinstance(e, Div):
        return _factors(e.left) + [(f, -s) for f, s in _factors(e.right)]
    return [(e, 1)]


def _product(parts: list[tuple[Expr, int]]) -> Expr:
    numer = [f for f, s in parts if s > 0]
    denom = [f for f, s in parts if s < 0]
    top: Expr = ONE
    for f in numer:
        top = f if top is ONE else Mul(top, f)
    if not denom:
        return top
    bottom = denom[0]
    for f in denom[1:]:
        bottom = Mul(bottom, f)
    return Div(top, bottom)


def _fresh(e: Expr, var: str) -> str:
    used = symbols(e) | {var}
    for name in ("u", "t", "w", "u1", "u2", "u3"):
        if name not in used:
            return name
    raise no_rule("no hay un nombre libre para el cambio de variable")  # pragma: no cover


def _attempt(log: StepLog, fn) -> tuple[Expr, int] | None:
    scratch = StepLog()
    try:
        got = fn(scratch)
    except UnsupportedError:
        return None
    if got is None:
        return None
    offset = log.merge(scratch)
    return got[0], got[1] + offset


def integrate(e: Expr, var: str, log: StepLog, depth: int = 0, normalized: bool = False) -> tuple[Expr, int]:
    """Return (antiderivative without constant, index of the step that produced it)."""
    if depth > MAX_DEPTH:
        raise no_rule(f"integral demasiado anidada (más de {MAX_DEPTH} niveles de reglas)")
    x = Sym(var)
    if not depends(e, var):
        out = x if e == ONE else Mul(e, x)
        return out, log.add(OP, "integral de una constante", _integral(e, var), text(out),
                            explanation=f"∫c d{var} = c·{var}")
    if isinstance(e, (Add, Sub)):
        s0 = log.add(OP, "linealidad: separar términos", _integral(e, var),
                     f"{_integral(e.left, var)} {'+' if isinstance(e, Add) else '-'} {_integral(e.right, var)}",
                     explanation="∫(u ± v) = ∫u ± ∫v")
        fl, sl = integrate(e.left, var, log, depth + 1)
        fr, sr = integrate(e.right, var, log, depth + 1)
        out = Add(fl, fr) if isinstance(e, Add) else Sub(fl, fr)
        return out, log.add(OP, "linealidad: sumar las primitivas", f"{text(fl)} ; {text(fr)}", text(out),
                            explanation="Se combinan las primitivas de cada término.", uses=(s0, sl, sr))
    if isinstance(e, Neg):
        f, s = integrate(e.arg, var, log, depth + 1)
        out = Neg(f)
        return out, log.add(OP, "cambio de signo", _integral(e, var), text(out),
                            explanation="∫(-u) = -∫u", uses=(s,))
    mono = _monomial(e, var)
    if mono is not None:
        c, n = mono
        written = _power_expr(c, n, var)
        uses = ()
        if text(written) != text(e):
            uses = (log.add(OP, "escribir como c·x^n", text(e), text(written),
                            substitution=f"c = {c}, n = {n}",
                            explanation="Se reescribe el integrando como una potencia de la variable (forma normal exacta)."),)
        return _power_rule(c, n, var, log, uses)
    if isinstance(e, Mul) and (not depends(e.left, var) or not depends(e.right, var)):
        const, fx = (e.left, e.right) if not depends(e.left, var) else (e.right, e.left)
        f, s = integrate(fx, var, log, depth + 1)
        out = Mul(const, f)
        return out, log.add(OP, "factor constante", _integral(e, var), text(out), substitution=f"c = {text(const)}",
                            explanation="∫c·u = c·∫u: la constante sale de la integral.", uses=(s,))
    if isinstance(e, Div) and not depends(e.right, var):
        f, s = integrate(e.left, var, log, depth + 1)
        out = Div(f, e.right)
        return out, log.add(OP, "factor constante (división por constante)", _integral(e, var), text(out),
                            substitution=f"c = 1/({text(e.right)})", explanation="∫u/c = (1/c)·∫u", uses=(s,))
    if isinstance(e, Div) and not depends(e.left, var) and e.left != ONE:
        f, s = integrate(Div(ONE, e.right), var, log, depth + 1)
        out = Mul(e.left, f)
        return out, log.add(OP, "factor constante", _integral(e, var), text(out), substitution=f"c = {text(e.left)}",
                            explanation="∫c/u = c·∫1/u", uses=(s,))
    if isinstance(e, Fn) and e.arg == x and e.name in _TABLE:
        rule, builder = _TABLE[e.name]
        out = builder(x)
        return out, log.add(OP, rule, _integral(e, var), text(out), explanation="Integral inmediata de la tabla.")
    if isinstance(e, Pow) and e.exponent == x and not depends(e.base, var):
        a = exact_value(e.base)
        if a is not None and a > 0 and a != 1:
            out = Div(e, Fn("log", e.base))
            return out, log.add(OP, "tabla: ∫a^x dx = a^x/log(a)", _integral(e, var), text(out),
                                substitution=f"a = {text(e.base)}",
                                explanation="Exponencial de base constante a > 0, a ≠ 1: la derivada de a^x es a^x·log(a).")
    if (isinstance(e, Pow) and isinstance(e.base, Fn) and e.base.name == "cos" and e.base.arg == x
            and exact_value(e.exponent) == -2) or (isinstance(e, Div) and e.left == ONE and isinstance(e.right, Pow)
                                                    and e.right.base == Fn("cos", x) and exact_value(e.right.exponent) == 2):
        out = Fn("tan", x)
        return out, log.add(OP, "tabla: ∫1/cos(u)^2 du = tan(u)", _integral(e, var), text(out),
                            explanation="Integral inmediata de la tabla (inversa de d/du tan(u)). Dominio: cos(u) ≠ 0.")
    for strategy in (_substitution, _by_parts):
        got = _attempt(log, lambda scratch, st=strategy: st(e, var, scratch, depth))
        if got is not None:
            return got
    if _has_sqrt(e):
        rewritten = _sqrt_as_power(e)
        s0 = log.add(OP, "reescribir la raíz como potencia", text(e), text(rewritten),
                     substitution="sqrt(u) = u^(1/2)", explanation="Identidad válida para u ≥ 0 (dominio de sqrt).")
        f, s = integrate(rewritten, var, log, depth + 1, normalized)
        return f, log.add(OP, "integrar la forma reescrita", _integral(rewritten, var), text(f), uses=(s0, s))
    if not normalized:
        simple, rules = simplify(e, var, expand=True)
        if text(simple) != text(e):
            s0 = log.add("simplificación", ", ".join(rules), text(e), text(simple),
                         explanation="Se reescribe el integrando en forma normal exacta (p. ej. desarrollando productos).")
            f, s = integrate(simple, var, log, depth + 1, normalized=True)
            return f, log.add(OP, "integrar la forma reescrita", _integral(simple, var), text(f), uses=(s0, s))
    raise no_rule(f"no hay regla de integración registrada para ∫{text(e)} d{var}")


def _has_sqrt(e: Expr) -> bool:
    if isinstance(e, Fn):
        return e.name == "sqrt" or _has_sqrt(e.arg)
    if isinstance(e, Neg):
        return _has_sqrt(e.arg)
    if isinstance(e, Pow):
        return _has_sqrt(e.base) or _has_sqrt(e.exponent)
    if isinstance(e, (Add, Sub, Mul, Div)):
        return _has_sqrt(e.left) or _has_sqrt(e.right)
    return False


def _sqrt_as_power(e: Expr) -> Expr:
    if isinstance(e, Fn):
        arg = _sqrt_as_power(e.arg)
        return Pow(arg, Num(Fraction(1, 2))) if e.name == "sqrt" else Fn(e.name, arg)
    if isinstance(e, Neg):
        return Neg(_sqrt_as_power(e.arg))
    if isinstance(e, Pow):
        return Pow(_sqrt_as_power(e.base), _sqrt_as_power(e.exponent))
    if isinstance(e, (Add, Sub, Mul, Div)):
        return type(e)(_sqrt_as_power(e.left), _sqrt_as_power(e.right))
    return e


def _candidates(e: Expr, var: str) -> list[tuple]:
    """(g, builder of the integrand in u, remaining factors) in written order."""
    parts = _factors(e)
    out = []
    for i, (f, sign) in enumerate(parts):
        rest = parts[:i] + parts[i + 1:]
        if isinstance(f, Fn) and depends(f.arg, var) and f.arg != Sym(var) and sign > 0:
            out.append((f.arg, lambda u, name=f.name: Fn(name, u), rest))
        if isinstance(f, Pow) and not depends(f.exponent, var) and depends(f.base, var) and f.base != Sym(var):
            n = f.exponent if sign > 0 else Neg(f.exponent)
            out.append((f.base, lambda u, n=n: Pow(u, n), rest))
        if not isinstance(f, (Num, Sym, Pow)) and depends(f, var) and f != Sym(var):
            out.append((f, (lambda u: u) if sign > 0 else (lambda u: Pow(u, Num(Fraction(-1)))), rest))
    return out


def _substitution(e: Expr, var: str, log: StepLog, depth: int) -> tuple[Expr, int] | None:
    for g, outer, rest in _candidates(e, var):
        scratch = StepLog()
        _raw, dg, _s = derivative(g, var, scratch)
        k = constant_ratio(_product(rest), dg, var)
        if k is None or k == 0:
            continue
        uname = _fresh(e, var)
        u = Sym(uname)
        lin = linear_parts(g, var)
        kind = "lineal" if lin is not None else "general"
        s0 = log.add(OP, f"cambio de variable ({kind}): elegir u", _integral(e, var), f"{uname} = {text(g)}",
                     explanation="Se busca una función interior g(x) cuya derivada aparezca, salvo constante, como factor.")
        _raw, dg, sd = derivative(g, var, log)
        s1 = log.add(OP, "cambio de variable: diferencial", f"{uname} = {text(g)}", f"d{uname} = {text(dg)} d{var}",
                     explanation=f"d{uname} = g'({var}) d{var}", uses=(s0, sd))
        integrand = outer(u)
        rewritten = _integral(integrand, uname) if k == 1 else f"{k}·{_integral(integrand, uname)}"
        s2 = log.add(OP, "cambio de variable: reescribir en u", _integral(e, var), rewritten,
                     substitution=f"{text(_product(rest))} d{var} = " + (f"d{uname}" if k == 1 else f"{k}·d{uname}"),
                     explanation="El resto del integrando es una constante por g'(x): la integral queda sólo en u.",
                     uses=(s1,))
        fu, si = integrate(integrand, uname, log, depth + 1)
        back = substitute(fu, uname, g)
        out = back if k == 1 else Mul(_k(k), back)
        return out, log.add(OP, "cambio de variable: deshacer el cambio",
                            text(fu if k == 1 else Mul(_k(k), fu)), text(out),
                            substitution=f"{uname} = {text(g)}", explanation="Se sustituye u por g(x).",
                            uses=(s2, si))
    return None


def _by_parts(e: Expr, var: str, log: StepLog, depth: int) -> tuple[Expr, int] | None:
    parts = [(f, s) for f, s in _factors(e)]
    if any(s < 0 for _f, s in parts):
        return None
    x = Sym(var)
    choice = None
    for i, (f, _s) in enumerate(parts):
        rest = _product(parts[:i] + parts[i + 1:])
        if f == Fn("log", x):
            mono = _monomial(rest, var)
            if not depends(rest, var) or (mono is not None and mono[1] != -1):
                choice = (f, rest, "u = logaritmo (LIATE)")
                break
    if choice is None:
        for i, (f, _s) in enumerate(parts):
            if isinstance(f, Fn) and f.name in ("exp", "sin", "cos") and linear_parts(f.arg, var) is not None:
                rest = _product(parts[:i] + parts[i + 1:])
                mono = _monomial(rest, var)
                if mono is not None and mono[1] > 0 and mono[1].denominator == 1:
                    choice = (rest, f, "u = potencia de x, dv = exponencial/trigonométrica (LIATE)")
                    break
    if choice is None:
        return None
    u, dv, why = choice
    if depth + 1 > MAX_DEPTH:
        return None
    s0 = log.add(OP, "integración por partes: elegir u y dv", _integral(e, var), f"u = {text(u)}, dv = {text(dv)} d{var}",
                 explanation=f"∫u dv = u·v - ∫v du; {why}.")
    _raw, du, sd = derivative(u, var, log)
    s1 = log.add(OP, "integración por partes: du", f"u = {text(u)}", f"du = {text(du)} d{var}", uses=(s0, sd))
    v_raw, sv = integrate(dv, var, log, depth + 1)
    v, _rules = simplify(v_raw, var)
    s2 = log.add(OP, "integración por partes: v = ∫dv", _integral(dv, var), text(v), uses=(s0, sv))
    w, rules = simplify(Mul(v, du), var)
    s3 = log.add(OP, "integración por partes: aplicar la fórmula", "u·v - ∫v du",
                 f"{text(Mul(u, v))} - {_integral(w, var)}",
                 substitution=f"u = {text(u)}, v = {text(v)}, du = {text(du)} d{var}",
                 explanation="Se sustituyen u, v y du en ∫u dv = u·v - ∫v du.", uses=(s1, s2))
    fw, sw = integrate(w, var, log, depth + 1)
    out = Sub(Mul(u, v), fw)
    return out, log.add(OP, "integración por partes: combinar", f"{text(Mul(u, v))} - ({text(fw)})", text(out),
                        uses=(s3, sw))


def antiderivative(e: Expr, var: str, log: StepLog) -> tuple[Expr, Expr, int]:
    """(raw antiderivative, simplified antiderivative, index of the '+ C' step)."""
    raw, top = integrate(e, var, log)
    simple, rules = simplify(raw, var)
    s = top
    if text(simple) != text(raw):
        s = log.add("simplificación", ", ".join(rules), text(raw), text(simple),
                    explanation="Forma normal exacta de la primitiva.", uses=(top,))
    return raw, simple, log.add(OP, "constante de integración", text(simple), f"{text(simple)} + C",
                                explanation="Toda primitiva está determinada salvo una constante C.", uses=(s,))


def point_value(e: Expr, var: str, at: Fraction) -> tuple[Expr, Fraction | Decimal | None]:
    """F(at): the substituted expression and its exact (Fraction) or Decimal value."""
    sub = substitute(e, var, Num(at))
    exact = exact_value(sub)
    if exact is not None:
        return sub, exact
    return sub, value(e, {var: Decimal(at.numerator) / Decimal(at.denominator)})


def _show(v) -> str:
    if isinstance(v, Fraction):
        return str(v.numerator) if v.denominator == 1 else f"{v.numerator}/{v.denominator}"
    return str(v)


def definite(e: Expr, var: str, a: Fraction, b: Fraction, log: StepLog) -> tuple[Expr, Fraction | Decimal, int]:
    """Barrow's rule: (antiderivative F, F(b) - F(a), index of the result step).

    It refuses when the integrand cannot be evaluated at a probe point of
    [a, b], which is how a possible discontinuity shows up. The rule needs
    F to be continuous on the interval."""
    _raw, F, sc = antiderivative(e, var, log)
    lo, hi = min(a, b), max(a, b)
    for i in range(17):
        t = lo + (hi - lo) * Fraction(i, 16)
        if value(e, {var: Decimal(t.numerator) / Decimal(t.denominator)}) is None:
            raise invalid("DOMAIN", f"el integrando no está definido en {var} = {_show(t)} ∈ [{_show(lo)}, {_show(hi)}]; "
                                    "no se aplica la regla de Barrow")
    sb, fb = point_value(F, var, b)
    s1 = log.add(OP, "regla de Barrow: evaluar en el límite superior", f"F({_show(b)})", _show(fb),
                 substitution=text(sb), explanation="Se sustituye el límite superior en la primitiva F.", uses=(sc,))
    sa, fa = point_value(F, var, a)
    s2 = log.add(OP, "regla de Barrow: evaluar en el límite inferior", f"F({_show(a)})", _show(fa),
                 substitution=text(sa), explanation="Se sustituye el límite inferior en la primitiva F.", uses=(sc,))
    if fa is None or fb is None:
        raise invalid("DOMAIN", "la primitiva no se puede evaluar en los límites")
    if isinstance(fa, Fraction) and isinstance(fb, Fraction):
        result = fb - fa
    else:
        da = fa if isinstance(fa, Decimal) else Decimal(fa.numerator) / Decimal(fa.denominator)
        db = fb if isinstance(fb, Decimal) else Decimal(fb.numerator) / Decimal(fb.denominator)
        result = db - da
    return F, result, log.add(OP, "regla de Barrow: restar", f"F({_show(b)}) - F({_show(a)})", _show(result),
                              substitution=f"{_show(fb)} - ({_show(fa)})",
                              explanation="∫_a^b f dx = F(b) - F(a)", uses=(s1, s2))


__all__ = ["antiderivative", "definite", "integrate", "point_value"]
