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
from math import comb

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
            return Mul(_k(Fraction(1, k)), Fn("ln", Div(ONE, Fn("cos", arg))))
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
                   _substitution, _by_parts):
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
    ("coth", lambda x: Neg(Fn("log", Div(ONE, Fn("sinh", x)))),
     "tabla: ∫coth(u) du = -ln|sinh(u)|",
     "Inversa de d/du ln|senh(u)| = cosh(u)/senh(u) = coth(u). Dominio: senh(u) ≠ 0."),
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
        clave = f"{e.base.name}^2"
        if clave not in _TABLA_DIRECTA:
            return None
    else:
        return None
    salida, etiqueta, por_que = _TABLA_DIRECTA[clave]
    return salida(x), etiqueta, por_que

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
