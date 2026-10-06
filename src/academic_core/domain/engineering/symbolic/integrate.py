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
from math import comb, gcd, isqrt

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
    # T-18: reciprocas e hiperbolicas. Cada entrada es la derivada de algo
    # que ya esta en la tabla de derivadas, escrita asi para que se vea:
    # la derivada de cosec es -cosec*cotg, luego esa integral es -cosec.
    "sec": ("tabla: ∫sec(u) du = log(abs(sec(u) + tan(u)))",
            lambda u: Fn("log", Fn("abs", Add(Fn("sec", u), Fn("tan", u))))),
    "csc": ("tabla: ∫cosec(u) du = log(abs(tan(u/2)))",
            lambda u: Fn("log", Fn("abs", Fn("tan", Div(u, Num(Fraction(2))))))),
    "sinh": ("tabla: ∫senh(u) du = cosh(u)", lambda u: Fn("cosh", u)),
    "cosh": ("tabla: ∫cosh(u) du = senh(u)", lambda u: Fn("sinh", u)),
    "tanh": ("tabla: ∫tanh(u) du = log(cosh(u))", lambda u: Fn("log", Fn("cosh", u))),
    "coth": ("tabla: ∫cotanh(u) du = log(abs(senh(u)))",
             lambda u: Fn("log", Fn("abs", Fn("sinh", u)))),
    # The last two of the family. Neither is the derivative of something already in
    # the table, which is why they were missing: `d/du arctg(senh u) = cosh/(1+sinh²)
    # = cosh/cosh² = 1/cosh = sech`, and `d/du log|tanh(u/2)| = 1/(2·sinh(u/2)·cosh(u/2))
    # = 1/senh u = cosecante hiperbolica`. Both written as the derivative of a
    # readable antiderivative, so the table entry can be checked by differentiating.
    "sech": ("tabla: ∫sech(u) du = arctg(senh(u))",
             lambda u: Fn("atan", Fn("sinh", u))),
    "csch": ("tabla: ∫cosecH(u) du = log(abs(tanh(u/2)))",
             lambda u: Fn("log", Fn("abs", Fn("tanh", Div(u, Num(Fraction(2))))))),
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


#: how each circular function reduces its own powers. The base cases are the
#: two entries of the table; everything above them is a recursion that ends.
_REDUCCION = {
    "cos": ("sin", True),
    "sin": ("cos", False),
}

#: functions whose derivative does not bring them back, where the tabular
#: formula lowers the exponent instead of raising it. The names are the ones this
#: tree uses internally, and they are not the ones the student writes: ``ln`` is
#: ``log`` here, which is why a first attempt at this list with «ln» in it never
#: fired and ``∫ln(x)^2`` kept being refused.
_TABULAR = frozenset({"log", "exp", "sinh", "cosh"})


def _potencia_de_uno(e: Expr, var: str) -> tuple[Fraction, str, Expr, int] | None:
    """``(c, nombre, argumento, n)`` for ``c·f(arg)^n`` with n an integer >= 2.

    Only a single power of ONE function. A product like sen(x)·cos(x) is not
    a power and belongs to the substitution case, which already gets it right;
    the two rules overlap here on purpose, because reducing a product is not
    the reduction of the product.
    """
    constante = Fraction(1)
    potencia = e
    if isinstance(e, Mul) and not depends(e.left, var):
        valor = exact_value(e.left)
        if valor is None:
            return None
        constante, potencia = valor, e.right
    if not isinstance(potencia, Pow) or not isinstance(potencia.base, Fn):
        return None
    base = potencia.base
    if not depends(base.arg, var):
        return None                      # the power is of a constant
    n = exact_value(potencia.exponent)
    if n is None or n < 2 or n.denominator != 1:
        return None
    return constante, base.name, base.arg, int(n)


def _escala_del_argumento(g: Expr, var: str) -> Fraction | None:
    """The constant derivative of the inner function, or ``None``.

    The reduction formulas are stated for d/dx, so they carry a factor 1/g
    for the base cases and 1/(n·1/g) for the recursion. Reading x for the
    argument is what made ∫cos(2x)^2 dx come out as cos·sen/2 + x/2: right
    for cos(x)^2 and wrong by a factor of four for this one, which is the kind
    of error that verifies against nothing.
    """
    scratch = StepLog()
    derivada, _paso, _s = derivative(g, var, scratch)
    return exact_value(derivada)


def _potencia_producto(e: Expr, var: str, log: StepLog, depth: int
                       ) -> tuple[Expr, int] | None:
    """``\u222bsen^m\u00b7cos^n`` when BOTH powers are present.

    :func:`_potencia_trig` only ever looks at ONE function raised to a power, so
    ``sen(x)^3\u00b7cos(x)^2`` had nothing to reduce and was refused \u2014 not because
    it is hard, but because no rule was reading the second factor.

    The three classical cases each turn the product into a SUM of single powers,
    which is the one thing that was already there:

    * ``m`` odd: ``sen^m\u00b7cos^n = sen\u00b7\u03a3_j C((m-1)/2, j)(-1)^j\u00b7cos^(n+2j)``
    * ``n`` odd: the same with the two exchanged
    * both even: ``sen^(2a)\u00b7cos^(2b) = 4^-(a+b)\u00b7(1-cos(2g))^a\u00b7(1+cos(2g))^b``

    Every term on the right is either a product ``sen\u00b7cos^p`` \u2014 which the
    substitution case has always done \u2014 or a single power ``cos(2g)^k``, which
    is :func:`_potencia_trig` with the chain factor. So this rule adds no new
    primitive, only the reading of the integrand that finds the existing ones.
    """
    if depth > MAX_DEPTH:
        return None
    leido = _potencias_hermanas(e, var)
    if leido is None:
        return None
    constante, g, m, n = leido
    terminos = _desdoblar(m, n, g)
    if terminos is None:
        return None
    scratch = StepLog()
    salidas: list[Expr] = []
    pasos: list[int] = []
    for coeficiente, factor in terminos:
        integrando = factor if coeficiente == 1 else Mul(_k(coeficiente), factor)
        got = _attempt(scratch, lambda sc, i=integrando: integrate(i, var, sc, depth + 1))
        if got is None:
            return None
        salidas.append(got[0])
        pasos.append(got[1])
    cuerpo = salidas[0]
    for otra in salidas[1:]:
        cuerpo = Add(cuerpo, otra)
    salida = cuerpo if constante == 1 else Mul(_k(constante), cuerpo)
    desglose = " ; ".join(text(i) for _c, i in terminos)
    s0 = scratch.add(OP, "desdoblar sen^m\u00b7cos^n", _integral(e, var),
                     f"{len(terminos)} t\u00e9rminos", uses=())
    paso = scratch.add(
        OP, "sumar las primitivas de cada t\u00e9rmino", desglose, text(salida),
        explanation=("El producto de dos potencias se convierte en una suma de potencias simples, que es lo que ya sab\u00eda integrar; la constante del factor se saca fuera al final."),
        uses=(s0, *pasos))
    offset = log.merge(scratch)
    return salida, paso + offset


def _potencias_hermanas(e: Expr, var: str) -> tuple[Fraction, Expr, int, int] | None:
    """``(constant, g, m, n)`` for ``sen(g)^m \u00b7cos(g)^n`` and for nothing else.

    Only ONE argument, and only sine and cosine. A product that also carries a
    tangent is a different formula, and refusing it beats guessing one.
    """
    if not isinstance(e, Mul):
        return None
    constante = Fraction(1)
    g: Expr | None = None
    m = 0
    n = 0
    for factor, signo in _factors(e):
        if signo < 0:
            return None
        if isinstance(factor, Num):
            valor = exact_value(factor)
            if valor is None:
                return None
            constante *= valor
            continue
        base, exponente = _base_y_exponente(factor)
        if not isinstance(base, Fn) or base.name not in ("sin", "cos"):
            return None
        valor = exact_value(exponente)
        if valor is None or valor.denominator != 1 or valor < 0:
            return None
        if g is None:
            g = base.arg
        elif text(g) != text(base.arg):
            return None
        if base.name == "sin":
            m += int(valor)
        else:
            n += int(valor)
    if g is None or m == 0 or n == 0:
        return None          # a single power is _potencia_trig's job, and an
                                 # empty product is nothing to reduce
    if _escala_del_argumento(g, var) in (None, 0):
        return None          # a non-affine inner function is another formula
    return constante, g, m, n


def _base_y_exponente(factor: Expr) -> tuple[Expr, Expr]:
    """``(base, exponent)`` for ``f`` and ``f^n`` alike; a bare f is f^1."""
    if isinstance(factor, Pow):
        return factor.base, factor.exponent
    return factor, Num(Fraction(1))


def _potencia_de(base: Expr, n: int) -> Expr:
    """``base^n``, without writing ``base^0``."""
    if n == 0:
        return ONE
    return base if n == 1 else Pow(base, Num(Fraction(n)))


def _desdoblar(m: int, n: int, g: Expr) -> list[tuple[Fraction, Expr]] | None:
    """The single-power terms ``sen(g)^m \u00b7cos(g)^n`` breaks into."""
    if m % 2:
        a = m // 2
        salida = []
        for j in range(a + 1):
            coeficiente = Fraction(comb(a, j)) * Fraction(-1) ** j
            factor = Mul(Fn("sin", g), _potencia_de(Fn("cos", g), n + 2 * j))
            salida.append((coeficiente, factor))
        return salida
    if n % 2:
        b = n // 2
        salida = []
        for j in range(b + 1):
            coeficiente = Fraction(comb(b, j)) * Fraction(-1) ** j
            factor = Mul(Fn("cos", g), _potencia_de(Fn("sin", g), m + 2 * j))
            salida.append((coeficiente, factor))
        return salida
    a, b = m // 2, n // 2
    doble = Fn("cos", Mul(_k(Fraction(2)), g))
    escala = Fraction(1, 2 ** (a + b))
    grados: dict[int, Fraction] = {}
    for j in range(a + 1):
        for i in range(b + 1):
            coeficiente = Fraction(comb(a, j) * comb(b, i)) * Fraction(-1) ** j
            grados[j + i] = grados.get(j + i, Fraction(0)) + coeficiente
    salida = []
    for grado in sorted(grados):
        coeficiente = grados[grado] * escala
        if coeficiente == 0:
            continue
        salida.append((coeficiente, _potencia_de(doble, grado)))
    return salida or None


def _potencia_trig(e: Expr, var: str, log: StepLog, depth: int
                   ) -> tuple[Expr, int] | None:
    """Integral of a power of the sine, the cosine or the tangent.

    Reducing the power was never done at all, so ∫sen(x)^2 dx was refused.
    What the substitution case would do instead —take u = sen(x)— is wrong
    on its own, because du = cos(x) dx and no cosine is present; it was guarded
    against only by accident.

        ∫cos^n = cos^(n-1)·sen/(n·k) + ((n-1)/(n·k^2))·∫cos^(n-2)
        ∫sen^n = -sen^(n-1)·cos/(n·k) + ((n-1)/(n·k^2))·∫sen^(n-2)
        ∫tg^n  = tg^(n-1)/((n-1)·k) - ∫tg^(n-2)

    with k = g′(x), the chain factor. Checked at n = 2 against the
    derivative, which is the only check that decides any of this.
    """
    if depth > MAX_DEPTH:
        return None
    parsed = _potencia_de_uno(e, var)
    if parsed is None or parsed[1] not in ("sin", "cos", "tan"):
        return None
    constante, nombre, arg, n = parsed
    k = _escala_del_argumento(arg, var)
    if k is None or k == 0:
        return None          # a non-constant inner function: not this formula
    cuerpo = _reducir(nombre, arg, n, k, var, log, depth)
    if cuerpo is None:
        return None
    salida = cuerpo if constante == 1 else Mul(_k(constante), cuerpo)
    return salida, log.add(
        OP, f"reducir potencias de {nombre}", _integral(e, var), text(salida),
        substitution=f"n = {n} → n - 2",
        explanation=(f"La integral de {nombre}^n se reduce a la de {nombre}^(n-2) más un término exacto, y se repite hasta la tabla."),
        uses=())


def _reducir(nombre: str, arg: Expr, n: int, k: Fraction, var: str,
             log: StepLog, depth: int) -> Expr | None:
    """``I_n`` for one circular function, recursing down to the table."""
    x = Sym(var)
    derivada, positiva = _REDUCCION.get(nombre, (nombre, True))
    if n <= 0:
        return x
    if n == 1:
        if nombre == "tan":
            # ∫tg = -ln|cos| = +ln(1/cos). Con el signo al revés, tg^3 salía
            # con +ln(1/cos) y su derivada era tg·sec^2 + tg, que no es tg^3.
            # The name is `log`, the one spelling this language has for a
            # natural logarithm (expr.FUNCTIONS). It was `ln` here, which is
            # correct English and inexpressible in this language: the answer
            # printed an `ln(1/cos(x))` that parse() rejected, so a primitive
            # the engine had computed could not be typed back in or verified.
            return Mul(_k(Fraction(1, k)), Fn("log", Div(ONE, Fn("cos", arg))))
        base = Fn(derivada, arg)
        return (Mul(_k(Fraction(1, k)), base) if positiva
                else Mul(_k(Fraction(-1, k)), base))
    if nombre == "tan":
        cociente = Fraction(1, (n - 1) * k)
        frente = (Fn("tan", arg) if cociente == 1
                  else Mul(_k(cociente), Pow(Fn("tan", arg), Num(Fraction(n - 1)))))
        resto = x if n == 2 else _reducir("tan", arg, n - 2, k, var, log, depth + 1)
        return None if resto is None else Add(frente, Neg(resto))
    potencia = Pow(Fn(nombre, arg), Num(Fraction(n - 1)))
    frente = (Mul(Fn(derivada, arg), potencia) if Fraction(1, n * k) == 1
              else Mul(Mul(_k(Fraction(1, n * k)), potencia), Fn(derivada, arg)))
    if not positiva:
        frente = Neg(frente)
    if n == 2:
        resto: Expr = x
    elif n == 3:
        base = Fn(derivada, arg)
        resto = (Mul(_k(Fraction(1, k)), base) if positiva
                 else Mul(_k(Fraction(-1, k)), base))
    else:
        resto = _reducir(nombre, arg, n - 2, k, var, log, depth + 1)
        if resto is None:
            return None
    # The chain factor k appears ONCE, in the front term. In the recursion it
    # cancels: ∫cos^(n-2)u du with u = g(x) is k·I_(n-2), and the outer 1/k undoes
    # it. Carrying a k^2 here is invisible at k = 1 — which is why every plain
    # sin^n and cos^n came out right — and wrong by a factor of four for
    # cos(2x)^2, the kind of error that verifies against nothing.
    factor = Fraction(n - 1, n)
    return Add(frente, Mul(_k(factor), resto))


def _potencia_tabulada(e: Expr, var: str, log: StepLog, depth: int
                       ) -> tuple[Expr, int] | None:
    """``∫g(x)^n`` by parts against ``dv = dx``, for a tabular function.

    ∫sen^n does NOT belong here: the derivative of the sine brings the
    cosine back and the formula stops terminating. It belongs to the reduction
    above, which is why these are two rules and not one with a longer list.

        ∫g^n = x·g^n/n - (1/n)·∫x·g′·g^(n-1)

    For g = ln that lowers the exponent and reaches the table, so
    ∫ln(x)^2 closes. For g = exp it does not, and the engine refuses rather
    than going round in circles.
    """
    if depth > MAX_DEPTH:
        return None
    parsed = _potencia_de_uno(e, var)
    if parsed is None or parsed[1] not in _TABULAR:
        return None
    constante, nombre, arg, n = parsed
    scratch = StepLog()
    derivada, _paso, _s = derivative(Fn(nombre, arg), var, scratch)
    frente = Mul(Sym(var), Pow(Fn(nombre, arg), Num(Fraction(n))))
    resto_integrando = Mul(Mul(Sym(var), derivada),
                           Pow(Fn(nombre, arg), Num(Fraction(n - 1))))
    try:
        plegado, _reglas = simplify(resto_integrando, var, expand=True)
        resto, sr = integrate(plegado, var, log, depth + 1)
    except UnsupportedError:
        return None
    cuerpo = Add(frente, Mul(_k(Fraction(-n)), resto))
    salida = cuerpo if constante == 1 else Mul(_k(constante), cuerpo)
    return salida, log.add(
        OP, f"partes contra {nombre}: bajar el exponente", _integral(e, var),
        text(salida),
        substitution=f"u = {nombre}(x)^(n-1), dv = dx",
        explanation=("Se integra por partes tomando la potencia como u; el "
                    "resto lleva un exponente menos y vuelve a entrar."),
        uses=(sr,))

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


# ---------------------------------------------------------------------------
# T-18: an integrand that is a RATIONAL FUNCTION, and the half-angle
# substitution that turns every trigonometric integrand into one.
# ---------------------------------------------------------------------------
# What was missing is not a difficult integral. What was missing is the part
# that makes rational integration a METHOD instead of a list: FACTOR THE
# DENOMINATOR over Q and split the integrand into pieces already known. The
# engine could read `1/(au+b)` and `u/(1+u^2)` — the denominator whose
# derivative happens to be in the numerator — and `int 1/(1+u^2)` was refused.
# It was not refused because it is hard. It was refused because nobody had
# written down any piece of it.

#: how far the multiple angles go before this refuses. Chebyshev coefficients
#: grow like 4^n / sqrt(n), so a cap is a real boundary and not a formality.
_MAX_ANGULO = 16


def _p_limpia(p: dict[int, Fraction]) -> dict[int, Fraction]:
    """A polynomial without zero coefficients. The empty dict is ZERO."""
    return {g: c for g, c in p.items() if c}


def _p_suma(a: dict[int, Fraction], b: dict[int, Fraction],
            signo: int = 1) -> dict[int, Fraction]:
    salida = dict(a)
    for g, c in b.items():
        salida[g] = salida.get(g, Fraction(0)) + signo * c
    return _p_limpia(salida)


def _p_producto(a: dict[int, Fraction], b: dict[int, Fraction]) -> dict[int, Fraction]:
    salida: dict[int, Fraction] = {}
    for g1, c1 in a.items():
        for g2, c2 in b.items():
            salida[g1 + g2] = salida.get(g1 + g2, Fraction(0)) + c1 * c2
    return _p_limpia(salida)


def _p_grado(p: dict[int, Fraction]) -> int:
    """-1 for the zero polynomial, which is what makes `while p and ...` work."""
    return max(p) if p else -1


def _p_derivada(p: dict[int, Fraction]) -> dict[int, Fraction]:
    return _p_limpia({g - 1: c * g for g, c in p.items() if g})


def _p_potencia(p: dict[int, Fraction], n: int) -> dict[int, Fraction]:
    salida: dict[int, Fraction] = {0: Fraction(1)}
    for _ in range(max(0, n)):
        salida = _p_producto(salida, p)
    return salida


def _p_eval(p: dict[int, Fraction], x: Fraction) -> Fraction:
    total = Fraction(0)
    for g, c in p.items():
        total += c * x ** g
    return total


def _p_mcd(a: Fraction, b: Fraction) -> Fraction:
    if a == 0:
        return abs(b)
    if b == 0:
        return abs(a)
    num = gcd(abs(a.numerator), abs(b.numerator))
    den = a.denominator * b.denominator // gcd(a.denominator, b.denominator)
    return Fraction(num, den)


def _p_parte_entera(a: dict[int, Fraction],
                    b: dict[int, Fraction]) -> tuple[dict[int, Fraction], dict[int, Fraction]]:
    """``(quotient, remainder)`` by exact division over Q."""
    cociente: dict[int, Fraction] = {}
    resto = dict(a)
    grado_b = _p_grado(b)
    while resto and _p_grado(resto) >= grado_b:
        g = _p_grado(resto) - grado_b
        c = resto[_p_grado(resto)] / b[grado_b]
        cociente[g] = cociente.get(g, Fraction(0)) + c
        for gb, cb in b.items():
            k = gb + g
            resto[k] = resto.get(k, Fraction(0)) - c * cb
        resto = _p_limpia(resto)
    return _p_limpia(cociente), resto


def _p_expresion(base: Expr, p: dict[int, Fraction]) -> Expr:
    """A polynomial in ``base``, written from the highest power down."""
    if not p:
        return Num(Fraction(0))
    partes = []
    for g in sorted(p, reverse=True):
        c = p[g]
        if g == 0:
            partes.append(Num(c))
            continue
        potencia = base if g == 1 else Pow(base, Num(Fraction(g)))
        partes.append(potencia if c == 1 else Mul(Num(c), potencia))
    salida = partes[0]
    for parte in partes[1:]:
        salida = Add(salida, parte)
    return salida


def _p_mcd_polinomios(a: dict[int, Fraction], b: dict[int, Fraction]) -> dict[int, Fraction]:
    """The polynomial gcd over Q by Euclid, monic. ``{0: 1}`` when coprime.

    The CONTENT is already out by the time this is called, so what is left to find
    is a genuine common polynomial factor — and it matters more than it looks. The
    substitution writes `1/(cos(x) + cos(2x))` without ever cancelling anything, so
    the denominator arrives carrying `(1+u²)³`: a factor with a negative
    discriminant that nothing can divide and that refuses the whole integral. With
    the common factor out, the integrand is `(1+u²)/(1-3u²)`, whose denominator has
    a positive discriminant and closes.

    It is returned MONIC, and that is not cosmetic. Normalising to the leading
    *coefficient* instead returned the constant `16/9` where the polynomial `u²+1`
    belonged, the degree test then said «no common factor», and nothing was ever
    cancelled.
    """
    while b:
        _q, r = _p_parte_entera(a, b)
        a, b = b, r
    if _p_grado(a) > 0:
        principal = a[_p_grado(a)]
        return {g: c / principal for g, c in a.items()}
    return {0: Fraction(1)}


def _p_reduce(n: dict[int, Fraction], d: dict[int, Fraction]):
    """Content and common polynomial factor out of the pair; leading sign fixed."""
    if not d:
        return None                      # dividing by zero
    comun = Fraction(0)
    for c in d.values():
        comun = _p_mcd(comun, c)
    if comun != 1:
        n = {g: c / comun for g, c in n.items()}
        d = {g: c / comun for g, c in d.items()}
    if d[_p_grado(d)] < 0:
        n = {g: -c for g, c in n.items()}
        d = {g: -c for g, c in d.items()}
    factor = _p_mcd_polinomios(n, d)
    if _p_grado(factor) > 0:
        n, _r = _p_parte_entera(n, factor)
        d, _r2 = _p_parte_entera(d, factor)
    return _p_limpia(n), d


def _como_racional(e: Expr, var: str):
    """``(numerator, denominator)`` as polynomials in ``var``, or ``None``.

    Only the four rational operations and INTEGER powers are allowed, and a
    negative power moves to the denominator instead of being an error: ``1/u^3``
    is a rational function whose denominator is ``u^3``, not something exotic.
    A half-power does not move — ``sqrt(u)`` is not rational in ``u`` — and
    neither does anything whose value is not a rational number, which is how
    ``sqrt(2)/(u-1)`` stays out.
    """
    x = Sym(var)

    # The denominator is the polynomial ONE and never the empty dict. Those are the
    # same thing written twice, and they are not the same thing: `{}` is the ZERO
    # polynomial here, so a product of two denominators `{}` came out as `{}`, the
    # reduction saw a zero denominator and refused, and `u^2` — which the power rule
    # had already answered — stopped answering. The empty denominator is written as
    # `{0: 1}` everywhere so that multiplying it does what multiplying by one does.
    UNO = {0: Fraction(1)}

    def rec(g: Expr):
        if isinstance(g, Num):
            v = exact_value(g)
            return ({0: Fraction(v)}, UNO) if v is not None else None
        if isinstance(g, Sym):
            return ({1: Fraction(1)}, UNO) if g.name == var else None
        if isinstance(g, Neg):
            got = rec(g.arg)
            if got is None:
                return None
            return ({k: -c for k, c in got[0].items()}, got[1])
        if isinstance(g, (Add, Sub)):
            a, b = rec(g.left), rec(g.right)
            if a is None or b is None:
                return None
            n = _p_suma(_p_producto(a[0], b[1]), _p_producto(b[0], a[1]),
                        1 if isinstance(g, Add) else -1)
            return _p_reduce(n, _p_producto(a[1], b[1]))
        if isinstance(g, Mul):
            a, b = rec(g.left), rec(g.right)
            if a is None or b is None:
                return None
            return _p_reduce(_p_producto(a[0], b[0]), _p_producto(a[1], b[1]))
        if isinstance(g, Div):
            a, b = rec(g.left), rec(g.right)
            if a is None or b is None:
                return None
            nuevo = _p_producto(a[1], b[0])
            if not nuevo:
                return None              # division by zero
            return _p_reduce(_p_producto(a[0], b[1]), nuevo)
        if isinstance(g, Pow):
            v = exact_value(g.exponent)
            if v is None:
                return None              # u^u and anything not a rational power
            n = int(v)
            if n != v or abs(n) > 64:
                return None              # sqrt(u) is not rational in u
            base = rec(g.base)
            if base is None:
                return None
            if n >= 0:
                return _p_reduce(_p_potencia(base[0], n), _p_potencia(base[1], n))
            return _p_reduce(_p_potencia(base[1], -n), _p_potencia(base[0], -n))
        return None                      # a function: sin, cos, log, abs...

    return rec(e)


def _divisores(n: int) -> list[int]:
    salida, d = [], 1
    while d * d <= n:
        if n % d == 0:
            salida.append(d)
            if d != n // d:
                salida.append(n // d)
        d += 1
    return sorted(salida)


def _candidatos_racionales(p: dict[int, Fraction]) -> list[Fraction]:
    """Every root the rational root theorem allows: ±p/q.

    Capped, because the theorem is quadratic in the constant term and an
    unbounded list is a quadratic blow-up on a polynomial nobody wrote by hand.
    """
    grado = _p_grado(p)
    if grado < 1:
        return []
    principal = p[grado]
    constante = p.get(0, Fraction(0))
    if constante == 0:
        return [Fraction(0)]
    salida = []
    for num in _divisores(abs(constante.numerator)):
        for den in _divisores(principal.denominator):
            for signo in (1, -1):
                salida.append(Fraction(signo * num, den))
                if len(salida) > 400:
                    return salida
    return salida


def _primera_raiz_racional(p: dict[int, Fraction]) -> Fraction | None:
    for c in _candidatos_racionales(p):
        if _p_eval(p, c) == 0:
            return c
    return None


def _factores(d: dict[int, Fraction]):
    """``[(factor, multiplicity)]`` with every factor of degree 1 or 2, or None.

    **It refuses a squarefree remainder of degree above 2.** Splitting a quartic
    into two quadratics is a system to solve, and doing it half way — handling
    whatever quadratics fall out and silently dropping the rest — is exactly how
    a rational integrator starts answering sometimes. So the boundary is drawn
    where the arithmetic stops being a division.
    """
    if _p_grado(d) < 1:
        return None
    resto = dict(d)
    salida = []
    for _ in range(_p_grado(d) + 1):
        raiz = _primera_raiz_racional(resto)
        if raiz is None:
            break
        factor = {1: Fraction(1), 0: -raiz}
        multiplicidad = 0
        # The division has to be EXACT, and what is left to factor is the QUOTIENT.
        # Asking only whether something changed made `u² - 1` come out as `(u-1)²`
        # with a remainder of 2; keeping the remainder instead of the quotient threw
        # `u+1` away, because the remainder of an exact division is nothing at all.
        while resto:
            cociente, nuevo = _p_parte_entera(resto, factor)
            if nuevo:
                break                    # this root's multiplicity ended here
            resto = cociente
            multiplicidad += 1
        salida.append((factor, multiplicidad))
    # `not resto` and not `_p_grado(resto) == 0`: the zero polynomial has degree -1
    # here, so testing for degree zero missed "factored all the way down" and
    # `u² - 1` came back as no factors at all.
    if not resto or _p_grado(resto) == 0:
        return salida
    if _p_grado(resto) == 2:
        return salida + [(resto, 1)]   # no rational root: irreducible over Q
    # `resto` has no rational root and is of degree above 2. Before refusing,
    # ask whether it is a POWER of something smaller — `(u²+1)²` arrives here
    # spelled `u⁴ + 2u² + 1` and is not a quartic. See
    # `_p_potencia_de_menor_grado`, which is where the answer lives and which
    # still refuses `u⁴+1` for the reason it always did.
    piezas = _p_potencia_de_menor_grado(resto)
    return salida + piezas if piezas is not None else None


def _integral_bicuadratica(A: Fraction, C: Fraction, a: Fraction, c: Fraction,
                           x: Sym):
    """``∫ (A·u² + C) du / (u⁴ + a u² + c)``, the BIQUADRATIC case.

    The last declared limit of T-18 was «a quartic with no rational root». That
    names three different algebraic situations and not all of them are reachable
    without a cubic root over ℚ, so this states which one it handles instead of
    pretending to handle all of them.

    **The factorisation.** A biquadratic splits as

        ``u⁴ + a u² + c = (u² + p u + q)(u² - p u + q)``  with  ``q = √c``,
        ``p² = 2q - a``

    because ``(u²+q)² - p²u² = u⁴ + (2q - p²)u² + q²`` and ``q² = c``. For
    ``u⁴+1`` that is ``q = 1``, ``p² = 2``, and the two factors carry ``√2``.

    **Why no quadratic-field arithmetic.** ``q`` is required to be a RATIONAL
    square, so the only irrational in play is ``p`` and ``p²`` is rational too.
    One radical — and it turns out that only ONE coefficient of the answer needs
    it. Writing

        ``(A u² + C)/B = (α u + β)/Q₊ + (-α u + β)/Q₋``

    and matching coefficients gives ``β = C/(2q)`` and ``α = (C/q - A)/(2p)``,
    and the integral collects to

        ``∫ = (α/2)·log|Q₊/Q₋| + (β - α·p/2)·(I₊ + I₋)``

    The surprise is the second coefficient: ``β - α·p/2`` collapses to
    ``(A + C/q)/4``, which is **rational**. So of the two coefficients one is
    rational and the other is a rational over ``√(p²)``, and neither needs an
    irrational carried through ``arctan`` or ``log``. That is the whole reason
    this fits without a field: ``√(p²)·t`` is one product, not a new type.

    Refuses — returns ``None`` — for a numerator with odd powers (a different
    routine and a different system), when ``√c`` is irrational, when ``c ≤ 0``
    (real roots: `_factores`' case), when ``2q - a ≤ 0`` (the factors carry
    complex coefficients), or when ``m = q - p²/4 = 0`` (a repeated linear
    factor). Every one of those is a refusal and not a partial answer.
    """
    if c <= 0:
        return None            # real roots: `_factores` owns this, and `_raiz`
                                # would raise on a negative argument
    raiz_c = _raiz(c)
    if not isinstance(raiz_c, Num):
        return None            # √c irrational: two radicals, another class
    q = raiz_c.value
    p2 = 2 * q - a
    if p2 <= 0:
        return None            # p imaginary: the factors are not real quadratics
    m = q - p2 / 4
    if m == 0:
        return None            # repeated linear factor, not this case
    raiz_p = _raiz(p2)         # Num when p rational, else Pow(v, 1/2)
    medio_p = Mul(Num(Fraction(1, 2)), raiz_p)

    def completa(signo: int) -> Expr:
        """``I± = ∫du/(u² ± p·u + q)``, by the shift that kills the linear term."""
        v = Add(x, medio_p) if signo > 0 else Sub(x, medio_p)
        if m > 0:
            rm = _raiz(m)
            return Mul(Div(ONE, rm), Fn("atan", Div(v, rm)))
        rm = _raiz(-m)
        # `1/2 · (1/rm)` printed as `1/2*1/1` when rm is exactly 1 is noise, and
        # noise is what pushes an answer past the length a reader can type back.
        medio = Num(Fraction(1, 2)) if (isinstance(rm, Num) and rm.value == 1) \
            else Mul(Num(Fraction(1, 2)), Div(ONE, rm))
        return Mul(medio, Fn("log", Fn("abs", Div(Sub(v, rm), Add(v, rm)))))

    def cuadratica(signo: int) -> Expr:
        return Add(Add(Pow(x, Num(Fraction(2))), Mul(raiz_p, x) if signo > 0
                       else Neg(Mul(raiz_p, x))), Num(q))

    # α/2 = (C/q - A)/(4p), and β - αp/2 = (A + C/q)/4 — the second rational.
    #
    # A piece whose coefficient is zero is DROPPED, not multiplied out. `0/4·(…)`
    # is not a shorter way of writing nothing, it is a longer one: it showed up
    # here for `∫dx/(cos x·cos 2x)`, whose leftover numerator is `(u²-5)/4`
    # with `A + C/q = 0`, and printing the vanished term is what pushed that
    # answer past `MAX_SOURCE`.
    partes: list[Expr] = []
    cociente_log = C / q - A
    cociente_I = A + C / q
    if cociente_log:
        partes.append(Mul(Div(_k(cociente_log), Mul(Num(Fraction(4)), raiz_p)),
                          Fn("log", Fn("abs", Div(cuadratica(1), cuadratica(-1))))))
    if cociente_I:
        partes.append(Mul(Div(_k(cociente_I), Num(Fraction(4))),
                          Add(completa(1), completa(-1))))
    if not partes:
        return Num(Fraction(0))
    return partes[0] if len(partes) == 1 else Add(partes[0], partes[1])


def _integral_mezcla_racional(num: dict[int, Fraction], den: dict[int, Fraction],
                              x: Sym):
    """Denominator = rational LINEAR factors (multiplicity one) × one biquadratic.

    This is the last of the three declared quartics: `∫dx/(cos x · cos 2x)`, whose
    half-angle substitution leaves ``(u²-1)(u⁴-6u²+1)`` — a degree 6 with a
    biquadratic inside it. `_factores` returns ``None`` for it, and for two
    reasons that have nothing to do with each other: the linear part it DID find
    gets thrown away with the ``None``, and the quartic needs the √ above.

    **The decomposition.** Every simple root ``r`` of the denominator gets its
    coefficient by cover-up, ``c = 1/[(den/(u-r))(r)]``, which is rational
    because ``r`` is. Subtracting those leaves a remainder over the quartic
    alone, and that remainder is what the biquadratic routine takes.

    Refuses when a rational root repeats (``_integral_pieza`` owns repeated
    linear factors, and mixing those with a √ quadratic is a third system), and
    when the leftover numerator has odd powers.
    """
    if _p_grado(den) < 4:
        return None
    resto = dict(den)
    raices: list[tuple[Fraction, dict[int, Fraction]]] = []
    for _ in range(_p_grado(den) + 2):
        raiz = _primera_raiz_racional(resto)
        if raiz is None:
            break
        factor = {1: Fraction(1), 0: -raiz}
        cociente, nuevo = _p_parte_entera(resto, factor)
        if nuevo:
            return None        # the root repeats: repeated linear × √ quadratic
        raices.append((raiz, cociente))
        resto = cociente
    if not raices:
        return None            # no rational factor: the pure branch owns it
    if _p_grado(resto) != 4:
        return None

    # cover-up coefficients, and the polynomial pieces they contribute.
    #
    # `den / (u - r)` is divided from the ORIGINAL denominator every time, and
    # not from the running remainder. That distinction is the whole correctness
    # of the step: dividing the remainder by (u+1) after already having taken out
    # (u-1) leaves the quartic, which evaluated at -1 gives -4 and a coefficient
    # of -1/4 where cover-up says +1/8. The remainder's own quotient is right for
    # its own step and wrong for this one, and it fails without saying so — the
    # leftover division then does not close, and the case refuses for a reason
    # that has nothing to do with why it should have worked.
    # Cover-up for a NUMERATOR that is not 1.
    #
    # What each simple root contributes to the ANSWER is `c·log|u-r|`, and what
    # it contributes to the ALGEBRA is `c·M` — the polynomial `den/(u-r)`,
    # scaled. Those are different things and mixing them is silent: integrating
    # the algebra polynomial gave a correct-looking degree-5 polynomial in place
    # of two logarithms, wrong by a factor of the integrand and 300 characters
    # longer than the answer that is right.
    #
    # `c = num(r) / [den/(u-r)](r)`, and `num - Σc·M`, NOT `1 - Σc·M`. Writing
    # the `1` here — which is the textbook case and what the first version did —
    # is wrong for every numerator but one, and it fails as a plausible-looking
    # answer rather than as a refusal. `∫dx/(cos x·cos 2x)` arrives here with a
    # numerator of `-2(u²+1)²`, and the `1` version was off by exactly it.
    suma: dict[int, Fraction] = {}
    logaritmos: list[Expr] = []
    for raiz, _ in raices:
        factor = {1: Fraction(1), 0: -raiz}
        cociente, nuevo = _p_parte_entera(den, factor)
        if nuevo:
            return None        # not exact: `raiz` is not a root of `den`
        valor = _p_eval(cociente, raiz)
        if valor == 0:
            return None
        c = _p_eval(num, raiz) / valor
        if c:
            # a zero cover-up coefficient is a piece that is not there; printing
            # `0*log(…)` adds characters and subtracts nothing
            logaritmos.append(Mul(Num(c), Fn("log", Fn("abs", Sub(x, Num(raiz))))))
        for g, coef in cociente.items():
            suma[g] = suma.get(g, Fraction(0)) + c * coef

    # what is left over the quartic: (num - Σ c·den/(u-r)) / Π(u-r)
    menos: dict[int, Fraction] = dict(num)
    for g, coef in suma.items():
        menos[g] = menos.get(g, Fraction(0)) - coef
    menos = _p_limpia(menos)

    # what is left over the quartic: (num - Σ c·den/(u-r)) / Π(u-r)
    producto: dict[int, Fraction] = {0: Fraction(1)}
    for raiz, _ in raices:
        producto = _p_producto(producto, {1: Fraction(1), 0: -raiz})
    Q, remanente = _p_parte_entera(menos, producto)
    if remanente or not Q:
        return None            # the algebra did not close: a refusal, not a guess
    if _p_grado(Q) >= 4:
        return None

    resto_final = _integral_bicuadratica_de(Q, resto, x)
    if resto_final is None:
        return None
    if not logaritmos:
        return resto_final
    lineales = logaritmos[0] if len(logaritmos) == 1 \
        else Add(logaritmos[0], logaritmos[1])
    return Add(lineales, resto_final)


def _integral_bicuadratica_de(num: dict[int, Fraction],
                              den: dict[int, Fraction], x: Sym):
    """``_integral_bicuadratica`` reached from the rational path, or ``None``.

    The numerator must be ``A·u² + C``: a constant is ``A = 0`` and a
    non-constant or odd numerator is a different routine with a different system,
    and answering one of the two while claiming the other is how an integrator
    starts answering «sometimes».

    The inner call's ``None`` is checked rather than multiplied through:
    ``Mul(Num(1), None)`` builds an expression tree with a hole in it, and the
    hole surfaces frames later as ``'NoneType' object has no attribute 'left'`` —
    a crash where the case called for a refusal.
    """
    if _p_grado(den) != 4 or 3 in den or 1 in den:
        return None            # not degree 4, or not biquadratic
    if den.get(4) != 1:
        # MONIC, and this is a correctness condition and not a stylistic one. The
        # formula reads `a` and `c` straight out of the denominator and assumes
        # the leading coefficient is 1. For `3u⁴ + 2` it would read `a = 0, c = 2`,
        # decide the class from THOSE, and if the class had matched, answer for
        # `u⁴ + 2` — a correct-looking answer to a different integral.
        return None
    if any(g % 2 for g in num):
        return None            # an odd power in the numerator: another case
    cuerpo = _integral_bicuadratica(num.get(2, Fraction(0)),
                                    num.get(0, Fraction(0)),
                                    den.get(2, Fraction(0)),
                                    den.get(0, Fraction(0)), x)
    if cuerpo is None:
        return None            # outside the supported class: a refusal, not a crash
    return cuerpo


def _p_potencia_de_menor_grado(d: dict[int, Fraction]):
    """``d`` has NO rational root and degree above 2: is it a POWER of something
    smaller? Musser's squarefree decomposition, exact over ``Fraction``.

    This exists because ``(u²+1)²`` used to be refused, and the reason it was
    refused was not visible from the answer. ``_como_racional`` writes that
    denominator as ``u⁴ + 2u² + 1``, a degree 4 with no rational root, and
    ``_factores`` looks at rational roots only — so it saw a quartic, and a
    quartic with no rational root is the unsolved half of this module. But the
    polynomial that arrived was never a quartic: it was a quadratic written out
    twice, and nothing had looked to see that.

    ``∫du/(u²+1)²`` and ``∫sen²x/(1+cos x) dx`` — the latter because
    ``u = tg(x/2)`` turns it into ``4u²/(1+u²)²`` — were both refused here, and
    for two years the refusal said «cuartic», which was true of the expansion
    and false of the expression.

    The boundary does NOT move. A piece that comes out of this decomposition
    squarefree and of degree above 2 is still the quartic-splitting problem, and
    this returns ``None`` for it: ``u⁴+1`` and ``u⁴+u²+1`` refuse exactly as
    before. What changes is only that ``(u⁴+1)²`` now refuses for the same
    reason ``u⁴+1`` does — because the factor inside it does — instead of
    arriving here indistinguishable from a genuinely irreducible quartic.

    Exact throughout, and verified rather than assumed: every division here is
    checked for a zero remainder, and a squarefree decomposition that did not
    divide exactly would be a wrong answer with no way back to this line.
    """
    c = _p_mcd_polinomios(d, _p_derivada(d))
    if _p_grado(c) <= 0:
        return None            # squarefree: there is no repeated factor to find
    # `w` starts at d/c, NOT at d. Starting it at d is the one-character mistake
    # this function is easy to make, and it does not fail loudly: gcd(d, c) is
    # then d's own factor rather than 1, the first quotient comes out as the
    # factor at multiplicity 1, and the answer becomes `(u²+1)·(u²+1)²` — a
    # denominator of degree 6 handed to a partial-fraction system for a degree-4
    # polynomial, with every downstream coefficient wrong.
    w, remanente = _p_parte_entera(d, c)
    if remanente:
        return None            # c divides d exactly; anything else is a defect
    salida, i = [], 1
    # `w` strictly decreases every pass (it becomes gcd(w, c), a proper divisor
    # once the constant factors run out), so this terminates; the bound is a
    # tripwire against a future edit, not a budget.
    for _ in range(_p_grado(d) + 2):
        if _p_grado(w) <= 0:
            break
        y = _p_mcd_polinomios(w, c)
        z, resto = _p_parte_entera(w, y)
        if resto:
            return None        # an inexact division is a wrong answer, not a None
        if _p_grado(z) > 0:
            # z is squarefree by construction, so this is `_factores` on a
            # polynomial with no repeated factor: it either comes apart into
            # rational roots plus one quadratic, or it does not come apart.
            piezas = _factores(z)
            if piezas is None:
                return None
            salida.extend((f, m * i) for f, m in piezas)
        w = y
        c, _r = _p_parte_entera(c, y)
        i += 1
    if _p_grado(c) > 0:
        piezas = _factores(c)
        if piezas is None:
            return None
        salida.extend((f, m * i) for f, m in piezas)
    return salida or None


def _gauss(sistema: list[list[Fraction]], n: int) -> list[Fraction] | None:
    """Gauss-Jordan over Fractions. ``None`` when the system does not solve.

    Exact arithmetic on purpose: a coefficient that is 1e-18 instead of 0 is a
    coefficient that will be a wrong answer ten steps later, where nobody can
    see that it was this one.
    """
    m = [list(fila) + [sistema[i][-1]] for i, fila in enumerate(sistema)]
    for col in range(n):
        pivote = next((r for r in range(col, n) if m[r][col] != 0), None)
        if pivote is None:
            return None
        m[col], m[pivote] = m[pivote], m[col]
        v = m[col][col]
        m[col] = [c / v for c in m[col]]
        for r in range(n):
            if r != col and m[r][col] != 0:
                f = m[r][col]
                m[r] = [a - f * bb for a, bb in zip(m[r], m[col])]
    return [m[i][n] for i in range(n)]


def _p_por_monomio(p: dict[int, Fraction], monomio: dict[int, Fraction]) -> dict[int, Fraction]:
    """``p·u^m``, where the EMPTY monomial is ``u⁰`` and not the zero.

    Everywhere else in this block ``{}`` is the zero polynomial, and multiplying by
    it gave ``{}``. So every coefficient of the partial fractions system came out as
    0, the system was singular, and `∫du/(u²-1)` was refused with the same message
    as `∫du/(1+u²)`. Two different reasons, one indistinguishable refusal.
    """
    return p if not monomio else _p_producto(p, monomio)


def _fracciones_parciales(resto: dict[int, Fraction], den: dict[int, Fraction],
                          factores):
    """``[((a, b), factor, power)]`` with ``R/D`` rebuilt out of them.

    The unknowns are the coefficients of every piece the factorisation allows:
    ``c_j/(u-r)^j`` for a linear factor of multiplicity ``m``, and
    ``(a_j u + b_j)/Q^j`` for a quadratic of multiplicity ``m``. That is as many
    unknowns as ``deg D``, so the system is square. It is built by multiplying
    each piece by ``D`` and equating coefficients — the textbook construction,
    and not a guess.
    """
    grado_den = _p_grado(den)
    incognitas: list[tuple[dict[int, Fraction], dict[int, Fraction]]] = []
    for factor, multiplicidad in factores:
        for j in range(1, multiplicidad + 1):
            comultiplo, _r = _p_parte_entera(den, _p_potencia(factor, j))
            if _p_grado(factor) == 1:
                incognitas.append((comultiplo, {}))
            else:
                incognitas.append((comultiplo, {1: Fraction(1)}))
                incognitas.append((comultiplo, {}))
    n = len(incognitas)
    if n != grado_den:
        return None                      # cannot happen; checked rather than trusted
    filas = []
    for g in range(grado_den):
        fila = [_p_por_monomio(comultiplo, monomio).get(g, Fraction(0))
                for comultiplo, monomio in incognitas]
        fila.append(resto.get(g, Fraction(0)))
        filas.append(fila)
    solucion = _gauss(filas, n)
    if solucion is None:
        return None
    piezas, i = [], 0
    for factor, multiplicidad in factores:
        for j in range(1, multiplicidad + 1):
            if _p_grado(factor) == 1:
                a, b = solucion[i], Fraction(0)
                i += 1
            else:
                a, b = solucion[i], solucion[i + 1]
                i += 2
            if a == 0 and b == 0:
                continue                  # a piece with no coefficient is not a piece
            piezas.append(((a, b), factor, j))
    return piezas


def _raiz(v: Fraction) -> Expr:
    """√v for a positive rational: exact when it is one, ``Pow(1/2)`` otherwise."""
    n, d = isqrt(v.numerator), isqrt(v.denominator)
    if n * n == v.numerator and d * d == v.denominator:
        return Num(Fraction(n, d))
    return Pow(Num(v), Num(Fraction(1, 2)))


def _integral_Q1(p: Fraction, q: Fraction, delta: Fraction, x: Sym):
    """``∫du/(u² + pu + q)`` for a MONIC quadratic of discriminant ``delta``.

    Three cases, all three of them answered:

    - ``delta > 0``: two real roots, and the answer is a logarithm of a ratio.
      This is the one T-18 needed first — ``∫1/(cos(x) + cos(2x))`` lands here.
    - ``delta = 0``: a perfect square, so the answer is rational. It should
      never arrive, since a squarefree denominator with no rational root is not
      one, but the branch is here rather than a division by zero later.
    - ``delta < 0``: an inverse tangent. It arrives as ``∫du/(u²+1)`` and was
      REFUSED until 6.1, on the grounds that this language had no ``atan``: not
      in the parser, and not in the evaluator, so the engine could print one
      and never read it back. That reason has expired — ``atan`` is in
      ``expr.FUNCTIONS`` and in the certified evaluator — and this branch is
      the whole of what T-18 was still PARTIAL for.

      With ``beta = -delta > 0`` the quadratic completes the square to
      ``(u + p/2)² + beta/4``, and ``∫dv/(v² + a²) = arctan(v/a)/a`` with
      ``a = √beta/2`` gives ``2/√beta · arctan((2u + p)/√beta)``. For ``p = 0,
      q = 1`` that is exactly ``arctan(u)``, which is the check that this is
      the identity and not merely a plausible-looking expression.
    """
    v = x if p == 0 else Add(x, Num(p / 2))
    if delta == 0:
        return Div(Num(Fraction(-1)), v)
    if delta < 0:
        raiz = _raiz(-delta)
        # The numerator is `2u + p`, written as `2u - (-p)` so it comes out in
        # ONE shape whether or not p is zero, instead of two answers to the
        # same integral differing only in how the terms were arranged.
        dos_u_mas_p = Sub(Mul(Num(Fraction(2)), x), Num(-p))
        return Mul(Div(Num(Fraction(2)), raiz), Fn("atan", Div(dos_u_mas_p, raiz)))
    raiz = _raiz(delta)
    medio = Mul(Num(Fraction(1, 2)), raiz)
    return Div(Fn("log", Fn("abs", Div(Sub(v, medio), Add(v, medio)))), raiz)


def _integral_Q(factor: dict[int, Fraction], j: int, x: Sym):
    """``∫du/Q(u)^j`` for Q of degree 2, by the recurrence on ``j``.

    ``J_j = 2(3-2j)/((j-1)Δ)·J_{j-1} - (2u + p)/((j-1)Δ·Q^(j-1))`` for a monic
    Q, with ``I_j = J_j/q2^j``. It comes from differentiating ``(2u + p)/Q^(j-1)``
    once and using ``(2u + p)² = 4Q + Δ``; checked against ``∫du/(u²-1)²``, whose
    derivative is exactly the integrand.
    """
    q2 = factor[2]
    p = factor.get(1, Fraction(0)) / q2
    q = factor.get(0, Fraction(0)) / q2
    delta = p * p - 4 * q
    cuerpo = _integral_Q1(p, q, delta, x)
    if cuerpo is None:
        return None
    monica = {2: Fraction(1), 1: p, 0: q}
    for nivel in range(2, j + 1):
        cociente = Fraction(2 * (3 - 2 * nivel), (nivel - 1)) / delta
        segundo = Div(Add(Mul(Num(Fraction(2)), x), Num(p)),
                      Mul(Num(Fraction(nivel - 1) * delta),
                          _p_expresion(x, _p_potencia(monica, nivel - 1))))
        cuerpo = Add(Mul(Num(cociente), cuerpo), Neg(segundo))
    return Div(cuerpo, Num(Fraction(q2) ** j))


def _integral_pieza(coefs: tuple[Fraction, Fraction],
                    factor: dict[int, Fraction], j: int, x: Sym):
    """``∫(a·u + b)/(u - r)^j du`` or ``∫(a·u + b)/Q(u)^j du``, whichever."""
    a, b = coefs
    if _p_grado(factor) == 1:
        # `factor` IS `u - r`, and it is stored as `u + factor[0]`. So the base is
        # `x + factor[0]` and not `x - factor[0]`, which had `u-1` integrating to
        # `+1/2 log|u+1|` and the whole answer with the sign of every term inverted.
        base = Add(x, Num(factor.get(0, Fraction(0))))
        if j == 1:
            return Mul(Num(a), Fn("log", Fn("abs", base)))
        return Mul(Num(Fraction(a, 1 - j)), Pow(base, Num(Fraction(1 - j))))
    q2 = factor[2]
    dq1 = factor.get(1, Fraction(0))
    lam = Fraction(a) / (2 * q2)
    mu = Fraction(b) - lam * dq1
    partes = []
    if lam:
        # the part of the numerator that IS the derivative of the denominator
        if j == 1:
            partes.append(Mul(Num(lam), Fn("log", Fn("abs", _p_expresion(x, factor)))))
        else:
            # `Q^(1-j)` written as `1/Q^(j-1)` and NOT as a negative power of
            # the polynomial. `_p_potencia` cannot do it: its loop is
            # `range(max(0, n))`, so every negative exponent returns the empty
            # product, which is 1 — and `∫(u+1)/(u²+1)² du` came out as
            # `(-1/2)·1 + arctan(u)/2 + …`, a `-1/(2(u²+1))` that had lost its
            # denominator. A wrong answer, not a wrong sign, and it verified as
            # long as nobody differentiated it.
            #
            # This is the only call site in the module that can pass a negative
            # exponent, so nothing else changes: the others are `n >= 0` by
            # construction.
            partes.append(Mul(Num(lam / (1 - j)),
                              Div(ONE, _p_expresion(x, _p_potencia(factor, j - 1)))))
    if mu:
        resto = _integral_Q(factor, j, x)
        if resto is None:
            return None
        partes.append(Mul(Num(mu), resto))
    if not partes:
        return Num(Fraction(0))
    salida = partes[0]
    for parte in partes[1:]:
        salida = Add(salida, parte)
    return salida


def _integral_polinio(q: dict[int, Fraction], x: Sym) -> Expr:
    return _p_expresion(x, _p_limpia({g + 1: c / (g + 1) for g, c in q.items()}))


def _integral_racional(e: Expr, var: str, log: StepLog, depth: int):
    """A rational function of the unknown, by partial fractions over Q.

    Five steps, every one of them exact:

    1. ``N/D`` with ``deg N ≥ deg D`` is divided, and the polynomial part goes to
       the power rule.
    2. ``D`` is factored over Q. Every rational root comes out with its
       multiplicity; what is left with no rational root is irreducible, and a
       squarefree remainder of degree 2 is taken as an irreducible quadratic.
    3. ``R/D`` is written as ``Σ c_j/(u-r)^j + Σ (a_j u + b_j)/Q^j`` by equating
       coefficients after multiplying each piece by ``D``.
    4. The system is solved by Gauss-Jordan over ``Fraction`` — never by a
       floating-point guess, because a coefficient that is 1e-18 instead of 0 is
       a wrong answer several steps downstream, where nothing points back here.
    5. Each piece is integrated: a logarithm for a first power, a power for the
       rest, and for a quadratic the derivative part gives a log while the
       remaining constant gives a log of a ratio.

    **The boundary was the negative discriminant, and it is gone.** ``∫du/(u²+1)``
    is ``arctg(u)``, and until 6.1 this language had no inverse tangent: it was
    not in the parser's list of functions, and neither the derivative table nor
    the numeric evaluator knew the name. mathlab differentiated and evaluated
    it without trouble, so an ``Fn('atan', x)`` PRINTED and could not be PARSED
    back — and a step trace the reader cannot retype is not a step trace. So
    that case refused, and this was what it refused on. ``atan`` is now in the
    language, so this no longer refuses. What remains declared is higher up and
    for other reasons: the denominator of degree 4 with no rational root, and the
    irreducible quadratic SQUARED, which `_como_racional` expands to a degree 4
    that `_factores` cannot reassemble.
    """
    if depth > MAX_DEPTH:
        return None
    descompuesto = _como_racional(e, var)
    if descompuesto is None:
        return None
    num, den = descompuesto
    if _p_grado(den) < 1:
        return None                      # a polynomial: the power rule has it
    factores = _factores(den)
    if factores is None:
        # The quartic that has no rational root. Before this refused
        # unconditionally, which is why `∫du/(u⁴+1)` was declared a limit: the
        # polynomial has no linear factor to find, but a BIQUADRATIC one still
        # splits into two quadratics over Q(√(p²)) — see `_integral_bicuadratica`
        # for why that needs no field arithmetic. Anything outside that class
        # still returns None, and still says so.
        cociente, resto = _p_parte_entera(num, den)
        bicuadratica = None if cociente else _integral_bicuadratica_de(resto, den, Sym(var))
        if bicuadratica is None and not cociente:
            bicuadratica = _integral_mezcla_racional(resto, den, Sym(var))
        if bicuadratica is None:
            return None
        return bicuadratica, log.add(
            OP, "cuártico biquadrático", text(e),
            text(bicuadratica),
            explanation=("el denominador no tiene raíz racional, pero es "
                         "biquadrático: se parte en dos cuadráticas sobre "
                         "Q(√(p²)), y cada una se integra completando el "
                         "cuadrado"),
            uses=())
    cociente, resto = _p_parte_entera(num, den)
    piezas = _fracciones_parciales(resto, den, factores)
    if piezas is None:
        return None
    x = Sym(var)
    terminos = []
    if cociente:
        terminos.append(_integral_polinio(cociente, x))
    for coefs, factor, j in piezas:
        trozo = _integral_pieza(coefs, factor, j, x)
        if trozo is None:
            return None                  # the degree-4 remainder, not the discriminant
        terminos.append(trozo)
    if not terminos:
        return None
    salida = terminos[0]
    for t in terminos[1:]:
        # `tan(x/2) + 0` is an answer with a piece of nothing in it, and a zero
        # that got there is a sign that something was counted twice.
        if isinstance(t, Num) and exact_value(t) == 0:
            continue
        salida = Add(salida, t)
    factored = " · ".join(
        f"{text(_p_expresion(x, factor))}^{m}" for factor, m in factores)
    return salida, log.add(
        OP, "descomposición en fracciones parciales", _integral(e, var), text(salida),
        substitution=f"el denominador se factoriza sobre Q: {factored}",
        explanation=("Se divide el cociente entero, se factoriza el denominador "
                     "sobre Q y el integrando se escribe como suma de fracciones "
                     "parciales, cada una con primitiva elemental."))


def _chebyshev(n: int) -> tuple[list, list]:
    """``(T, U)`` with ``cos(k·x) = T_k(cos x)`` and ``sen(k·x) = sen x · U_{k-1}``."""
    T = [{0: Fraction(1)}, {1: Fraction(1)}]
    U = [{0: Fraction(1)}, {1: Fraction(2)}]
    for _ in range(2, n + 1):
        T.append(_p_suma(_p_producto({1: Fraction(2)}, T[-1]), T[-2], -1))
        U.append(_p_suma(_p_producto({1: Fraction(2)}, U[-1]), U[-2], -1))
    return T, U


def _multiplo_de(arg: Expr, x: Sym) -> int | None:
    """``k`` when ``arg`` is exactly ``k·x``, and ``None`` when it is not.

    Exactly. ``sen(x²)`` is not a multiple of anything this substitution knows,
    and reading its exponent as a coefficient would substitute a DIFFERENT
    equation — which is the same mistake as reading ``sen(2x)`` as ``sen(u)``.
    """
    if arg == x:
        return 1
    if isinstance(arg, Neg):
        k = _multiplo_de(arg.arg, x)
        return None if k is None else -k
    if isinstance(arg, Mul):
        for lado, otro in ((arg.left, arg.right), (arg.right, arg.left)):
            if lado == x:
                n = exact_value(otro)
                if n is not None and int(n) == n:
                    return int(n)
    return None


def _cuadratica_bajo_raiz(e: Expr, var: str) -> tuple[Fraction, Fraction, Fraction] | None:
    """``(a, b, c)`` when ``e`` is ``1/sqrt(a·x² + b·x + c)`` in any spelling."""
    if isinstance(e, Div) and e.left == ONE and isinstance(e.right, Fn) and e.right.name == "sqrt":
        base = e.right.arg
    elif isinstance(e, Pow) and exact_value(e.exponent) == Fraction(-1, 2):
        base = e.base
    elif (isinstance(e, Div) and e.left == ONE and isinstance(e.right, Pow)
          and exact_value(e.right.exponent) == Fraction(1, 2)):
        base = e.right.base
    else:
        return None
    try:
        p = _poly(base, var, None, 0)
    except Exception:  # noqa: BLE001
        return None
    a = b = c = Fraction(0)
    for m, coef in p.terms.items():
        if m == ():
            c = Fraction(coef)
        elif m == ((var, Fraction(1)),):
            b = Fraction(coef)
        elif m == ((var, Fraction(2)),):
            a = Fraction(coef)
        else:
            return None
    return (a, b, c) if a != 0 else None


def _raiz_k(q: Fraction) -> Expr:
    """sqrt(q) for a rational q > 0: a rational when q is a perfect square."""
    num, den = isqrt(q.numerator), isqrt(q.denominator)
    if num * num == q.numerator and den * den == q.denominator:
        return _k(Fraction(num, den))
    return Fn("sqrt", _k(q))


def _raiz_de_cuadratica(e: Expr, var: str, log: StepLog, depth: int):
    """``∫ dx/sqrt(a·x² + b·x + c)``: arcsin, arsinh or the logarithm.

    The square is completed, ``a·(x + h)² + k`` with ``h = b/(2a)``, and then

    * ``a < 0, k > 0``: ``arcsen((x + h)·sqrt(-a/k))/sqrt(-a)``;
    * ``a > 0``: ``ln|sqrt(a)·(x + h) + sqrt(a·x² + b·x + c)|/sqrt(a)``, which is
      arsinh for ``k > 0`` and arcosh for ``k < 0`` written once for both.

    None of the three was in the table: ∫dx/sqrt(1 - x²) was refused (found
    2026-10-06). Each answer is differentiated by the caller's verification.
    """
    coeficientes = _cuadratica_bajo_raiz(e, var)
    if coeficientes is None:
        return None
    a, b, c = coeficientes
    x = Sym(var)
    h = b / (2 * a)
    k = c - b * b / (4 * a)
    desplazada = x if h == 0 else Add(x, _k(h))
    if a < 0:
        if k <= 0:
            return None                    # sqrt of something negative everywhere
        salida = Div(Fn("asin", Mul(desplazada, _raiz_k(-a / k))), _raiz_k(-a))
        etiqueta = "tabla: ∫du/sqrt(k - a·u²) = arcsen(u·sqrt(a/k))/sqrt(a)"
    else:
        raiz = Fn("sqrt", Add(Add(Mul(_k(a), Pow(x, Num(Fraction(2)))), Mul(_k(b), x)), _k(c)))
        salida = Div(Fn("log", Fn("abs", Add(Mul(_raiz_k(a), desplazada), raiz))),
                     _raiz_k(a))
        etiqueta = ("tabla: ∫du/sqrt(a·u² + k) = ln|sqrt(a)·u + sqrt(a·u² + k)|/sqrt(a)"
                    " (argsenh si k > 0, argcosh si k < 0)")
    simple, _r = simplify(salida, var)
    return simple, log.add(OP, etiqueta, _integral(e, var), text(simple),
                           substitution=f"u = {text(desplazada)}" if h else "",
                           explanation=("Se completa el cuadrado bajo la raíz y se lee "
                                        "la primitiva de la tabla de las inversas."))


def _producto_a_suma(e: Expr, var: str, log: StepLog, depth: int):
    """``sen(mx)·cos(nx)`` and friends, through the product-to-sum identities.

    Before this the product fell through to the universal substitution, which is
    correct and unreadable: ``∫sen(x)·cos(3x)`` came back as a polynomial of degree 8
    in ``1/(1 + tg(x/2)²)``, where the textbook answer is ``cos(2x)/4 − cos(4x)/8``.
    It also gave ``atan(tan(x/2))`` for ``∫sen(x)·sen(x)``, which is discontinuous at
    every odd multiple of π. The identities replace one product by two terms that
    are each in the table:

    * ``sen A·cos B = (sen(A+B) + sen(A−B))/2``
    * ``cos A·cos B = (cos(A−B) + cos(A+B))/2``
    * ``sen A·sen B = (cos(A−B) − cos(A+B))/2``
    """
    if depth > MAX_DEPTH or not isinstance(e, Mul):
        return None
    x = Sym(var)
    a, b = e.left, e.right
    if not (isinstance(a, Fn) and isinstance(b, Fn)
            and a.name in ("sin", "cos") and b.name in ("sin", "cos")):
        return None
    m, n = _multiplo_de(a.arg, x), _multiplo_de(b.arg, x)
    if m is None or n is None:
        return None
    if a.name == "cos" and b.name == "sin":
        a, b, m, n = b, a, n, m

    def angulo(k: int) -> Expr:
        return x if k == 1 else Mul(Num(Fraction(k)), x)

    def f(nombre: str, k: int) -> Expr:
        if k == 0:
            return ONE if nombre == "cos" else Num(Fraction(0))
        if k < 0:
            return Fn("cos", angulo(-k)) if nombre == "cos" else Neg(Fn("sin", angulo(-k)))
        return Fn(nombre, angulo(k))

    if a.name == "sin" and b.name == "cos":
        suma = Add(f("sin", m + n), f("sin", m - n))
        identidad = "sen A·cos B = (sen(A+B) + sen(A−B))/2"
    elif a.name == "cos":
        suma = Add(f("cos", m - n), f("cos", m + n))
        identidad = "cos A·cos B = (cos(A−B) + cos(A+B))/2"
    else:
        suma = Sub(f("cos", m - n), f("cos", m + n))
        identidad = "sen A·sen B = (cos(A−B) − cos(A+B))/2"
    reescrito = Div(suma, Num(Fraction(2)))
    s0 = log.add(OP, "producto a suma", text(e), text(reescrito),
                 substitution=identidad,
                 explanation=("Un producto de senos y cosenos de múltiplos de x se "
                              "escribe como suma, y cada término es inmediato."))
    primitiva, paso = integrate(reescrito, var, log, depth + 1)
    # the two table entries arrive as «1/4*-cos(4x) + -1/2*-cos(2x)»; the exact
    # normal form writes the same function the way the textbook does
    plegada, _reglas = simplify(primitiva, var, expand=True)
    return plegada, log.add(OP, "integrar la suma", _integral(reescrito, var),
                            text(plegada), uses=(s0, paso))


def _medio_angulo(e: Expr, var: str, log: StepLog, depth: int):
    """``u = tg(x/2)``: the integrand becomes rational, and then it is read.

    The universal substitution, which is the same one the equation solver uses
    for the same reason — it is the substitution that needs no new idea per
    equation:

    ``sen → 2u/(1+u²)``, ``cos → (1-u²)/(1+u²)``, ``tg → 2u/(1-u²)``, and
    ``dx → 2du/(1+u²)``.

    Multiple angles go through Chebyshev FIRST, so ``cos(2x)`` is ``2c²-1`` with
    ``c = cos x`` and never a square root. Going the other way round — writing
    ``cos(2x)`` from ``tg(2x) = 2v/(1-v²)`` — lands on ``1/sqrt(1+v²)``, which
    is not rational, and the substitution that cannot express what it has to
    substitute is not a substitution.

    ``∫1/(1+cos x)`` comes out as ``u`` and comes back as ``tg(x/2)``.
    """
    if depth > MAX_DEPTH:
        return None
    x = Sym(var)
    t = _fresh(e, "t")
    u = Sym(t)
    uno_mas = Add(ONE, Pow(u, Num(Fraction(2))))
    uno_menos = Sub(ONE, Pow(u, Num(Fraction(2))))
    coco = Div(uno_menos, uno_mas)
    seno = Div(Mul(Num(Fraction(2)), u), uno_mas)
    #: what it actually rewrote. A substitution that rewrote nothing is not a
    #: substitution: without this, `∫(u²+1)/(u(u²-1)) du` came back as
    #: `-2 log|tg(u/2)| + ...`, because the half-angle was substituted back into an
    #: integrand that had never been in `u` and the Jacobian was applied to nothing.
    trigonometricas: list[str] = []

    def en_u(g: Expr):
        """The same integrand written in ``u``, or ``None`` if it cannot be."""
        if isinstance(g, Num):
            return g if exact_value(g) is not None else None
        if isinstance(g, Sym):
            # A bare x is NOT u: under u = tg(x/2) it is 2·arctg(u), which is not
            # rational, so the substitution does not apply. Mapping it to u made
            # ∫ sin(x)/x come back as 2·atan(tan(x/2)) + …, i.e. x + sin x, whose
            # derivative is 1 + cos x (found 2026-10-05 against a quadrature).
            return None
        if isinstance(g, Neg):
            a = en_u(g.arg)
            return None if a is None else Neg(a)
        if isinstance(g, (Add, Sub)):
            a, b = en_u(g.left), en_u(g.right)
            if a is None or b is None:
                return None
            return Add(a, b) if isinstance(g, Add) else Sub(a, b)
        if isinstance(g, Mul):
            a, b = en_u(g.left), en_u(g.right)
            return None if a is None or b is None else Mul(a, b)
        if isinstance(g, Div):
            a, b = en_u(g.left), en_u(g.right)
            return None if a is None or b is None else Div(a, b)
        if isinstance(g, Pow):
            v = exact_value(g.exponent)
            a = en_u(g.base)
            if a is None or v is None or int(v) != v or not (-64 <= int(v) <= 64):
                return None
            return Pow(a, Num(Fraction(int(v))))
        if isinstance(g, Fn):
            trigonometricas.append(g.name)
            k = _multiplo_de(g.arg, x)
            if k is None or abs(k) > _MAX_ANGULO:
                return None
            if g.name == "abs":          # abs(u) is not rational in u
                return None
            if k == 1 and g.name in ("sin", "cos", "tan", "sec", "csc"):
                if g.name == "sin":
                    return seno
                if g.name == "cos":
                    return coco
                if g.name == "tan":
                    return Div(Mul(Num(Fraction(2)), u), uno_menos)
                if g.name == "sec":
                    return Div(uno_mas, uno_menos)
                return Div(uno_mas, Mul(Num(Fraction(2)), u))
            if g.name not in ("sin", "cos", "tan"):
                return None
            n = abs(k)
            T, U = _chebyshev(n)
            if g.name == "cos":
                return _p_expresion(coco, T[n])
            polinomio = Mul(seno, _p_expresion(coco, U[n - 1]))
            if g.name == "sin":
                return polinomio if k > 0 else Neg(polinomio)
            return Div(polinomio, _p_expresion(coco, T[n]))
        return None

    racional = en_u(e)
    if racional is None or not trigonometricas:
        return None
    total = Mul(racional, Div(Num(Fraction(2)), uno_mas))   # and dx = 2du/(1+u²)
    # Now that the Jacobian is in, cancel. Built as expressions the two carry
    # uncancelled factors — `1/(cos(x) + cos(2x))` arrives with `(1+u²)³` on top —
    # and an irreducible quadratic with a negative discriminant that nothing can
    # divide refuses the whole integral for a reason that has nothing to do with it.
    reducido = _como_racional(total, t)
    if reducido is not None:
        total = Div(_p_expresion(u, reducido[0]), _p_expresion(u, reducido[1]))
    s0 = log.add(
        OP, "sustitución del ángulo medio: u = tg(x/2)", text(e),
        text(Div(Num(Fraction(2)), uno_mas)) + " · " + text(racional),
        substitution="sen(x) = 2u/(1+u²), cos(x) = (1-u²)/(1+u²), dx = 2du/(1+u²)",
        explanation=("El ángulo medio vuelve racional cualquier expresión "
                     "trigonométrica; los ángulos múltiples pasan antes por "
                     "Chebyshev para no introducir raíces."))
    primitiva, paso = integrate(total, t, log, depth + 1)
    vuelta = Fn("tan", Div(x, Num(Fraction(2))))
    salida = substitute(primitiva, t, vuelta)
    return salida, log.add(OP, "volver a x: u = tg(x/2)", text(primitiva), text(salida),
                           substitution=f"u = {text(vuelta)}",
                           explanation="Se sustituye el valor de la variable auxiliar.",
                           uses=(s0, paso))

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
    # 1/cos(u) es sec(u) y 1/sen(u) es cosec(u). Sin esto la tabla solo se
    # alcanza escribiendo el nombre largo, y «int 1/cos(x) dx» se rechaza
    # aunque sea el mismo calculo que «int sec(x) dx».
    if (isinstance(e, Div) and e.left == ONE and isinstance(e.right, Fn)
            and e.right.arg == x and e.right.name in ("cos", "sin")):
        nombre = "sec" if e.right.name == "cos" else "csc"
        regla, constructor = _TABLE[nombre]
        salida = constructor(e.right.arg)
        return salida, log.add(
            OP, "1/" + e.right.name + "(u) = " + nombre + "(u): " + regla,
            _integral(e, var), text(salida),
            substitution="1/" + e.right.name + "(u) = " + nombre + "(u)",
            explanation=("El reciproco se escribe como funcion antes de "
                         "buscar en la tabla, que es donde esta la regla."))
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
    # T-18: ∫cosec(u)^2 du = -cotg(u) y ∫sec(u)^2 du = tg(u). Los dos son
    # la regla de la potencia leida de una derivada que ya esta en la tabla:
    # la del cotangente es -cosec^2 y la de la tangente 1/cos^2. Se cubren las
    # dos escrituras del cuadrado, porque "1/sen(x)^2" y "cosec(x)^2" son un
    # solo integrando escrito de dos maneras y solo una es una llamada suelta.
    _al_cuadrado = None
    if (isinstance(e, Pow) and isinstance(e.base, Fn) and e.base.arg == x
            and exact_value(e.exponent) in (2, -2)):
        # sin(u)^2 is NOT csc(u)^2. The reciprocal rule belongs to the
        # square of the reciprocal, or to a NEGATIVE power of the short
        # name, and to nothing else: reading the base alone gave
        # "integral of sin(x)^2 = -cotg(x)", which is cosec^2 and not
        # sin^2. A wrong answer that looks like a right one is worse
        # than the refusal it replaced.
        _al_cuadrado = (e.base.name if (e.base.name in ("sec", "csc")
                         or exact_value(e.exponent) < 0) else None)
    elif (isinstance(e, Div) and e.left == ONE and isinstance(e.right, Pow)
          and isinstance(e.right.base, Fn) and e.right.base.arg == x
          and exact_value(e.right.exponent) == 2):
        # here the reciprocal IS written out: 1/sin(u)^2 is cosec(u)^2
        _al_cuadrado = e.right.base.name
    if _al_cuadrado in ("csc", "sin"):
        salida = Neg(Fn("cot", x))
        return salida, log.add(
            OP, "tabla: ∫1/sen(u)^2 du = -cotg(u)", _integral(e, var),
            text(salida),
            explanation=("Es la inversa de d/du cotg(u) = -cosec(u)^2, que ya esta "
                         "en la tabla de derivadas. Dominio: sen(u) ≠ 0."))
    if _al_cuadrado in ("sec", "cos"):
        salida = Fn("tan", x)
        return salida, log.add(
            OP, "tabla: ∫1/cos(u)^2 du = tg(u)", _integral(e, var),
            text(salida),
            explanation=("Es la inversa de d/du tg(u) = 1/cos(u)^2, que ya esta "
                         "en la tabla de derivadas. Dominio: cos(u) ≠ 0."))
    # ± 1/cos(u)^2 no tiene rama propia: _PROPIAS la cubre para las dos
    # escrituras del integrando — cos(u)^-2 y 1/cos(u)^2 — con una sola
    # etiqueta. La duplicada que había aquí no la alcanzaba nada, y una
    # prueba clavó su etiqueta en vez de la que sale de verdad.
    propia = _integral_propia(e, x)
    if propia is not None:
        salida, etiqueta, por_que = propia
        return salida, log.add(OP, etiqueta, _integral(e, var), text(salida),
                                explanation=por_que)
    for strategy in (_potencia_producto, _potencia_trig, _potencia_tabulada,
                   _raiz_de_cuadratica, _substitution, _by_parts, _producto_a_suma,
                   _medio_angulo, _integral_racional):
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


def _integral_propia(e: Expr, x: Sym) -> tuple[Expr, str, str] | None:
    """The integrals of the family ITSELF, which is what T-14 asks for.

    Each one is the inverse of a derivative the engine already has, so every
    entry is checkable the same way: differentiate it and compare. Three of
    them were missing and not being missed by accident — ``∫sec(x)^2`` was in
    the table only in the spelling ``1/cos(x)^2``, and a student who writes
    ``sec(x)`` gets refused by a solver that has the answer.

    Nothing here is clever: they are the six entries every table of primitives
    has and this one did not.
    """
    def potencia_de(nombre: str, n: int) -> Expr | None:
        if isinstance(e, Pow) and isinstance(e.base, Fn) and e.base.name == nombre \
                and e.base.arg == x and exact_value(e.exponent) == n:
            return e.base.arg
        return None

    def sola(nombre: str) -> Expr | None:
        if isinstance(e, Fn) and e.name == nombre and e.arg == x:
            return e.arg
        return None

    u = sola("cot")
    if u is not None:
        # ln|sen| and NOT ln(1/sen): those two differ by a sign, and the sign is
        # the whole difference between cot and -cot. The absolute value carries
        # the domain: ln|sen| is real where sen is negative too.
        return (Fn("log", Fn("abs", Fn("sin", u))),
                "tabla: ∫cot(u) du = ln|sin(u)|",
                "Inversa de d/du ln|sen(u)| = cos(u)/sen(u) = cot(u). "
                "Dominio: sen(u) ≠ 0.")
    for nombre, salida, etiqueta, por_que in _PROPIAS:
        if potencia_de(nombre, 2) is not None:
            return salida(x), etiqueta, por_que
    recursion = _potencia_propia(e, x)
    if recursion is not None:
        cuerpo, etiqueta, por_que = recursion
        return cuerpo, etiqueta, por_que
    directa = _de_la_tabla_directa(e, x)
    if directa is not None:
        cuerpo, etiqueta, por_que = directa
        return cuerpo, etiqueta, por_que
    return None


#: ``(nombre de la función, primitiva, etiqueta, por qué)`` for the squares.
_PROPIAS = (
    ("sec", lambda x: Fn("tan", x), "tabla: ∫sec(u)^2 du = tan(u)",
     "Inversa de d/du tg(u) = 1/cos(u)^2 = sec(u)^2. Dominio: cos(u) ≠ 0."),
    ("csc", lambda x: Neg(Fn("cot", x)), "tabla: ∫cosec(u)^2 du = -cot(u)",
     "Inversa de d/du (-cot(u)) = cosec^2(u). Dominio: sen(u) ≠ 0."),
    ("cot", lambda x: Add(Neg(Fn("cot", x)), Neg(x)), "tabla: ∫cot(u)^2 du = -cot(u) - u",
     "Por partes con v = cot(u): cot^2 = cot·(cosec^2 - 1) y las dos piezas "
     "están en la tabla. Dominio: sen(u) ≠ 0."),
    # This entry used to be ∫coth(u) = -ln|1/sinh(u)| filed under the SQUARE:
    # ∫coth(x)^2 came back as ln|senh x|, which differentiates to coth and not
    # coth^2. ∫coth itself is answered elsewhere; the square is u - coth(u).
    ("coth", lambda x: Sub(x, Fn("coth", x)), "tabla: ∫coth(u)^2 du = u - coth(u)",
     "coth^2 = 1 + csch^2 y d/du coth(u) = -csch(u)^2, así que las dos piezas "
     "están en la tabla. Dominio: senh(u) ≠ 0."),
    ("tanh", lambda x: Sub(x, Fn("tanh", x)), "tabla: ∫tanh(u)^2 du = u - tanh(u)",
     "tanh^2 = 1 - sech^2 y d/du tanh(u) = sech(u)^2."),
    ("csch", lambda x: Neg(Fn("coth", x)), "tabla: ∫csch(u)^2 du = -coth(u)",
     "Inversa de d/du coth(u) = -csch(u)^2. Dominio: senh(u) ≠ 0."),
    ("sech", lambda x: Fn("tanh", x), "tabla: ∫sech(u)^2 du = tanh(u)",
     "Inversa de d/du tanh(u) = sech^2(u)."),
)


#: how each reciprocal lowers its own powers. The SQUARE is in the table above;
#: above the square, f^n = f^(n-2)·f^2 and the second half of that product is
#: already answered, so the whole recursion is one line.
#:
#:     ∫sec^n   =  sec^(n-2)·tan /(n-1) + (n-2)/(n-1)·∫sec^(n-2)
#:     ∫cosec^n = -cosec^(n-2)·cot/(n-1) + (n-2)/(n-1)·∫cosec^(n-2)
#:     ∫cot^n   = -cot^(n-1)/(n-1) - ∫cot^(n-2)
#:
#: The cotangent one is not the same shape as the other two, and pretending it
#: was is what made sec^3 come out as sec·tan - ln|sec+tan| instead of
#: sec·tan/2 + ln|sec+tan|/2 — an answer with the right pieces and the wrong
#: coefficients, which is worse than no answer because it looks finished.
def _potencia_propia(e: Expr, x: Sym) -> tuple[Expr, str, str] | None:
    """``∫sec^n``, ``∫cosec^n`` and ``∫cot^n`` for n >= 3."""
    if not isinstance(e, Pow) or not isinstance(e.base, Fn) or e.base.arg != x:
        return None
    n = exact_value(e.exponent)
    if n is None or n < 3 or n.denominator != 1:
        return None
    n = int(n)
    nombre = e.base.name
    if nombre == "sec":
        frente = Mul(_k(Fraction(1, n - 1)), Mul(Pow(Fn("sec", x), Num(Fraction(n - 2))), Fn("tan", x)))
        factor = Fraction(n - 2, n - 1)
    elif nombre == "csc":
        frente = Mul(_k(Fraction(-1, n - 1)), Mul(Pow(Fn("csc", x), Num(Fraction(n - 2))), Fn("cot", x)))
        factor = Fraction(n - 2, n - 1)
    elif nombre == "cot":
        frente = Mul(_k(Fraction(-1, n - 1)), Pow(Fn("cot", x), Num(Fraction(n - 1))))
        factor = Fraction(-1)
    else:
        return None
    etiqueta = f"tabla: ∫{nombre}(u)^{n} por reducción a {nombre}(u)^{n - 2}"
    por_que = (f"{nombre}^n = {nombre}^(n-2)·{nombre}^2 y el cuadrado ya está en la tabla; la integral se cierra en dos pasos.")
    resto = _menor_de(nombre, x, n - 2)
    cuerpo = Add(frente, resto if factor == 1 else Mul(_k(factor), resto))
    return cuerpo, etiqueta, por_que


def _menor_de(nombre: str, x: Sym, n: int) -> Expr:
    """``∫f^n`` for the exponent the recursion lands on.

    It lands on the SQUARE most of the time, and the square is a table entry —
    asking for it from the recursion, which only knows n >= 3, gave the n = 1
    primitive instead and put a logarithm where a polynomial belongs.
    """
    if n <= 0:
        return x
    if n == 1:
        return _PRIMAS[nombre](x)
    if n == 2:
        salida = _PROPIAS_POR_NOMBRE[nombre]
        return salida(x)
    propia = _potencia_propia(Pow(Fn(nombre, x), Num(Fraction(n))), x)
    return propia[0] if propia is not None else _PRIMAS[nombre](x)


#: the same squares, by name, for the recursion that lands on them
_PROPIAS_POR_NOMBRE = {nombre: salida for nombre, salida, _e, _p in _PROPIAS}

#: the n = 1 case of each of the three, which is what the recursion bottoms on.
_PRIMAS = {
    "sec": lambda x: Fn("log", Fn("abs", Add(Fn("sec", x), Fn("tan", x)))),
    "csc": lambda x: Fn("log", Fn("abs", Fn("tan", Div(x, Num(Fraction(2)))))),
    "cot": lambda x: Fn("log", Fn("abs", Fn("sin", x))),
}

#: the table lines that are neither a substitution nor a power rule. Each
#: explanation is ONE physical line: in a CRLF file a string literal cannot
#: cross the line break, because the carriage return is a terminator for the
#: tokenizer, and three explanations that spanned two lines each were a
#: SyntaxError that only appears when the file is read with its own endings.
def _p_e_x_por_sen(x: Sym) -> Expr:
    """``e^x(sen x - cos x)/2``, the primitive of ``e^x·sen x``."""
    return Mul(_k(Fraction(1, 2)),
               Mul(Fn("exp", x), Add(Fn("sin", x), Neg(Fn("cos", x)))))


def _p_e_x_por_cos(x: Sym) -> Expr:
    """``e^x(sen x + cos x)/2``, the primitive of ``e^x·cos x``."""
    return Mul(_k(Fraction(1, 2)),
               Mul(Fn("exp", x), Add(Fn("sin", x), Fn("cos", x))))


def _p_senh_2(x: Sym) -> Expr:
    """``senh(x)·cosh(x)/2 - x/2``."""
    return Add(Mul(_k(Fraction(1, 2)), Mul(Fn("sinh", x), Fn("cosh", x))),
               Mul(_k(Fraction(-1, 2)), x))


def _p_cosh_2(x: Sym) -> Expr:
    """``senh(x)·cosh(x)/2 + x/2``.

    The same as :func:`_p_senh_2` with the linear term's sign flipped, and that
    ONE character is the whole difference between the two. Differentiating is
    what tells them apart; reading them is not.
    """
    return Add(Mul(_k(Fraction(1, 2)), Mul(Fn("sinh", x), Fn("cosh", x))),
               Mul(_k(Fraction(1, 2)), x))


#: the table lines that are neither a substitution nor a power rule.
#: ``(clave, primitiva, etiqueta, por qué)``, and the key is read off the written
#: integrand so that ``exp(x)·sen(x)`` and ``exp(x)·cos(x)`` are two entries and
#: not one rule with a guess.
#:
#: Each explanation is ONE physical line. In a CRLF file a string literal cannot
#: cross the line break, because the carriage return is a terminator for the
#: tokenizer: three explanations that spanned two lines each were a SyntaxError
#: that only appears when the file is read with its own endings.
_TABLA_DIRECTA = {
    "exp*sin": (
        _p_e_x_por_sen,
        "tabla: ∫e^x·sen(x) dx = e^x(sen x - cos x)/2",
        "Inversa de d/dx de esa expresión, que es e^x·sen x. Es una entrada de tabla y no un cambio de variable: u = sen(x) no aplica, y las partes por dos veces vuelven a la integral de la que salieron.",
    ),
    "exp*cos": (
        _p_e_x_por_cos,
        "tabla: ∫e^x·cos(x) dx = e^x(sen x + cos x)/2",
        "La pareja de la anterior y la misma razón para estar en la tabla: derivarla devuelve e^x·cos x, que es lo que la hace entrada y no truco.",
    ),
    "sinh^2": (
        _p_senh_2,
        "tabla: ∫senh(x)^2 dx = senh(x)·cosh(x)/2 - x/2",
        "Por partes con v = x. El término lineal va con signo MENOS, del lado del ángulo doble de las hiperbólicas; comprobarlo derivando es lo que lo distingue del otro.",
    ),
    "cosh^2": (
        _p_cosh_2,
        "tabla: ∫cosh(x)^2 dx = senh(x)·cosh(x)/2 + x/2",
        "Por partes con v = x, y el término lineal con signo MÁS: el opuesto que en senh^2, que es donde estos dos se confunden.",
    ),
}


def _de_la_tabla_directa(e: Expr, x: Sym) -> tuple[Expr, str, str] | None:
    """``e^x·sen(x)``, ``e^x·cos(x)``, ``senh(x)^2`` and ``cosh(x)^2``.

    Table entries, and labelled as such. ``exp(x)·sen(x)`` has the closed form
    above and NO substitution finds it: u = sen(x) does not apply, and
    integration by parts returns to the integral it started from. Putting it
    in the table with its inverse stated is more honest than a trick that
    happens to work on one of the two products.

    Two shapes reach here and they are not the same shape: a PRODUCT of two
    functions, and a POWER of one. Reading them through one filter is what left
    the hyperbolic squares refusing forever with a perfectly good entry in the
    table three lines below them.
    """
    if isinstance(e, Mul):
        piezas = _factors(e)
        if len(piezas) != 2 or any(s < 0 for _f, s in piezas):
            return None
        if not all(isinstance(f, Fn) and f.arg == x for f, _s in piezas):
            return None
        nombres = sorted(f.name for f, _s in piezas)
        clave = "exp*sin" if nombres == ["exp", "sin"] else (
            "exp*cos" if nombres == ["cos", "exp"] else None)
        if clave is None:
            return None
    elif isinstance(e, Pow) and isinstance(e.base, Fn) and e.base.arg == x:
        # The EXPONENT must be 2. Reading only the base made ∫cosh(x)^5 come back
        # as the primitive of cosh(x)^2 (found 2026-10-05 by differentiating it);
        # the higher powers go through _senh_cosh_potencia instead.
        if exact_value(e.exponent) != 2:
            return _senh_cosh_potencia(e, x) or _hiperbolica_potencia(e, x)
        clave = f"{e.base.name}^2"
        if clave not in _TABLA_DIRECTA:
            return None
    else:
        return None
    salida, etiqueta, por_que = _TABLA_DIRECTA[clave]
    return salida(x), etiqueta, por_que

def _senh_cosh_potencia(e: Expr, x: Sym) -> tuple[Expr, str, str] | None:
    """``∫senh(x)^n`` and ``∫cosh(x)^n`` for an integer ``n >= 3``, by reduction.

    * ``∫senh^n = senh^(n-1)·cosh/n - (n-1)/n·∫senh^(n-2)``
    * ``∫cosh^n = cosh^(n-1)·senh/n + (n-1)/n·∫cosh^(n-2)``

    Both come from integrating by parts once with ``v' = senh`` (or ``cosh``) and
    replacing ``cosh^2 = 1 + senh^2``; the sign is the only difference, and it is
    the one that ``1 + senh^2`` against ``1 - sen^2`` puts there.
    """
    if not (isinstance(e, Pow) and isinstance(e.base, Fn)
            and e.base.name in ("sinh", "cosh") and e.base.arg == x):
        return None
    n = exact_value(e.exponent)
    if n is None or int(n) != n or not (3 <= int(n) <= 64):
        return None
    n = int(n)
    nombre = e.base.name
    otra = "cosh" if nombre == "sinh" else "sinh"
    signo = Fraction(-1) if nombre == "sinh" else Fraction(1)
    # F_0 = x, F_1 = the other function; then F_k from F_(k-2)
    previas = {0: x, 1: Fn(otra, x)}
    for k in range(2, n + 1):
        termino = Mul(_k(Fraction(1, k)),
                      Mul(Pow(Fn(nombre, x), Num(Fraction(k - 1))), Fn(otra, x)))
        previas[k] = Add(termino, Mul(_k(signo * Fraction(k - 1, k)), previas[k - 2]))
    simbolo = "-" if nombre == "sinh" else "+"
    escrito = "senh" if nombre == "sinh" else "cosh"
    return (previas[n],
            f"reducción: ∫{escrito}^n = {escrito}^(n-1)·{'cosh' if nombre == 'sinh' else 'senh'}/n "
            f"{simbolo} (n-1)/n·∫{escrito}^(n-2)",
            "Por partes una vez y cosh^2 = 1 + senh^2; se aplica hasta llegar a la "
            "potencia 0 o 1, que son inmediatas.")


def _hiperbolica_potencia(e: Expr, x: Sym) -> tuple[Expr, str, str] | None:
    """``∫tanh^n``, ``∫coth^n``, ``∫sech^n``, ``∫csch^n`` for ``n >= 3``, by reduction.

    * ``∫tanh^n = -tanh^(n-1)/(n-1) + ∫tanh^(n-2)``      (tanh² = 1 - sech²)
    * ``∫coth^n = -coth^(n-1)/(n-1) + ∫coth^(n-2)``      (coth² = 1 + csch²)
    * ``∫sech^n = sech^(n-2)·tanh/(n-1) + (n-2)/(n-1)·∫sech^(n-2)``
    * ``∫csch^n = -csch^(n-2)·coth/(n-1) - (n-2)/(n-1)·∫csch^(n-2)``

    The powers 0 and 1 are the engine's own table entries, so the bottom of each
    recursion is the same answer a student gets for ``∫sech(x)`` on its own.
    """
    if not (isinstance(e, Pow) and isinstance(e.base, Fn)
            and e.base.name in ("tanh", "coth", "sech", "csch") and e.base.arg == x):
        return None
    n = exact_value(e.exponent)
    if n is None or int(n) != n or not (3 <= int(n) <= 64):
        return None
    n, nombre = int(n), e.base.name
    f = Fn(nombre, x)
    uno, _ = integrate(f, x.name, StepLog())
    dos, _ = integrate(Pow(f, Num(Fraction(2))), x.name, StepLog())
    previas = {0: x, 1: uno, 2: dos}
    for k in range(3, n + 1):
        if nombre in ("tanh", "coth"):
            termino = Mul(_k(Fraction(-1, k - 1)), Pow(f, Num(Fraction(k - 1))))
            previas[k] = Add(termino, previas[k - 2])
        else:
            otra = Fn("tanh" if nombre == "sech" else "coth", x)
            signo = Fraction(1) if nombre == "sech" else Fraction(-1)
            termino = Mul(_k(signo * Fraction(1, k - 1)),
                          Mul(Pow(f, Num(Fraction(k - 2))), otra))
            previas[k] = Add(termino, Mul(_k(signo * Fraction(k - 2, k - 1)), previas[k - 2]))
    return (previas[n], f"reducción de potencias: ∫{nombre}^n en función de ∫{nombre}^(n-2)",
            "Por partes una vez y la identidad pitagórica hiperbólica; la recursión "
            "baja de dos en dos hasta una entrada de la tabla.")


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
        k_simbolico = None
        if k is None:
            # The ratio may be a constant that is not a NUMBER: ∫exp(pi·x) has
            # rest = 1 and g' = pi, so the factor is 1/pi. It is just as constant,
            # and refusing it refused ∫cos(pi·x) and ∫exp(y·x) (found 2026-10-06).
            cociente, _r = simplify(Div(_product(rest), dg), var)
            if depends(cociente, var) or text(cociente) in ("0",):
                continue
            k, k_simbolico = 1, cociente
        if k == 0:
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
        factor = text(k_simbolico) if k_simbolico is not None else (None if k == 1 else str(k))
        rewritten = _integral(integrand, uname) if factor is None else f"{factor}·{_integral(integrand, uname)}"
        s2 = log.add(OP, "cambio de variable: reescribir en u", _integral(e, var), rewritten,
                     substitution=f"{text(_product(rest))} d{var} = " + (f"d{uname}" if factor is None else f"{factor}·d{uname}"),
                     explanation="El resto del integrando es una constante por g'(x): la integral queda sólo en u.",
                     uses=(s1,))
        fu, si = integrate(integrand, uname, log, depth + 1)
        back = substitute(fu, uname, g)
        out = back if k == 1 else Mul(_k(k), back)
        if k_simbolico is not None:
            out = Mul(k_simbolico, out)
        antes = fu if k == 1 else Mul(_k(k), fu)
        if k_simbolico is not None:
            antes = Mul(k_simbolico, antes)
        return out, log.add(OP, "cambio de variable: deshacer el cambio",
                            text(antes), text(out),
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
