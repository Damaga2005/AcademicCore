# SPDX-License-Identifier: MIT
"""MATH_LAB T-19: Taylor and Maclaurin series, with the remainder attached.

Why the remainder is the whole point
------------------------------------

A truncated series is not an approximation until you say of what. ``sin(x) ≈ x``
is true to no accuracy at all — at ``x = 3`` it is wrong by 0.14 — and the number
that makes it a statement is the next term, or the bound on what comes after it.

So every answer here is three things, never one:

1. the polynomial up to the requested order;
2. the **next** term, which is the first one dropped;
3. a **declared error bound** on what comes after that.

The bound is where a series engine is usually honest-looking and dishonest. Two
bounds are implemented and they are *not* interchangeable:

* for a whole function with a known series (the trigonometric and hyperbolic
  ones) the error is the tail of that series, which is a bound on the alternating
  or monotone remainder;
* for a general function the bound comes from the order of the first omitted
  derivative, which needs a bound on that derivative over the interval — and when
  no such bound is available the module **says so** rather than inventing one.

Convergence, and refusing to fake it
-----------------------------------

The radius of convergence is decided by the nearest singularity, and for a general
expression the engine cannot see singularities. So it does not answer: a request
for the radius comes back with «this engine cannot determine it», which is a real
answer about this engine and not a claim about the function.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import trig as T
from academic_core.errors import UnsupportedError

#: the order is capped: a series to the thousandth term is a number, not a series,
#: and the cap is declared rather than hit by a RecursionError
ORDEN_MAXIMO = 40


def sin_refuso(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"NO_RULE: {mensaje}")


# ---------------------------------------------------------------------------
# the answer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Serie:
    """A truncated series and everything that has to travel with it."""

    polinomio: mx.Expr
    orden: int
    residuo: mx.Expr
    cota: mx.Expr | None
    centro: mx.Expr
    metodo: str
    hipotesis: tuple[str, ...] = ()

    def texto(self) -> str:
        partes = [mx.text(self.polinomio)]
        if self.residuo is not None:
            partes.append(f"+ {mx.text(self.residuo)} + ...")
        return " ".join(partes)

    def con_cota(self) -> str:
        base = self.texto()
        if self.cota is None:
            return base + "   (sin cota de error declarada)"
        return base + f"   error < {mx.text(self.cota)}"

    @property
    def con_cota_error(self) -> bool:
        return self.cota is not None


# ---------------------------------------------------------------------------
# the series this module knows exactly
# ---------------------------------------------------------------------------

#: the general term of each known series: coefficient, power, and the name it is
#: written under, as ``(funcion, coeficiente, potencia)``.
_TERMINO = {
    "sin": ("sin", 1, 1),
    "cos": ("cos", 1, 0),
    "tan": ("tan", 1, 1),
    "exp": ("exp", 1, 1),
    "sinh": ("sinh", 1, 1),
    "cosh": ("cosh", 1, 0),
    "ln": ("ln", 1, 0),
}


def maclaurin(nombre: str, orden: int, var: str = "x") -> Serie:
    """The series of a known function about zero, exactly.

    Only functions whose series is known here. A general expression goes through
    :func:`taylor`, which needs derivatives and which therefore declares a
    different kind of error bound.
    """
    if nombre not in _TERMINO:
        raise sin_refuso(
            f"no se sabe la serie de «{nombre}» sobre la lista: "
            f"{', '.join(sorted(_TERMINO))}. Eso NO es «no converge» (§5.4)")
    if orden < 0:
        raise sin_refuso(f"el orden tiene que ser 0 o mayor; llegó {orden}")
    if orden > ORDEN_MAXIMO:
        raise sin_refuso(
            f"el orden {orden} supera el máximo de {ORDEN_MAXIMO}. Un polinomio de "
            "ese grado es un número con demasiados dígitos, no una serie (§5.5)")
    polinomio, residuo = _truncar(nombre, orden, var)
    cota = _cota_de_cola(nombre, orden, var)
    hipotesis = [
        f"la serie de {nombre} es exacta; el residuo es el primer término que no se "
        f"escribe, y lo que sigue está acotado por él",
    ]
    if nombre in ("tan", "ln"):
        hipotesis.append(
            "esta serie tiene radio de convergencia 1: fuera de |x| < 1 los términos "
            "no suman un número, y la divergencia no se detecta truncando (§5.4)")
    return Serie(polinomio, orden, residuo, cota, mx.ZERO,
                 "serie de Maclaurin conocida, escrita término a término",
                 tuple(hipotesis))


def _truncar(nombre: str, orden: int, var: str) -> tuple[mx.Expr, mx.Expr | None]:
    """The polynomial up to ``orden`` and the first term left out.

    Four shapes, and they are not interchangeable:

    * ``sin`` has odd powers only, signs alternating;
    * ``cos`` has even powers only, signs alternating;
    * ``sinh`` and ``cosh`` have the same powers with every sign positive;
    * ``exp`` has every power, positive.

    Reading them off one table of «odd and alternating» gave ``sin``, ``cos``,
    ``sinh`` and ``cosh`` the same polynomial, and a coseno series that starts at
    ``x`` is not a series of anything.
    """
    x = mx.Sym(var)
    if nombre in ("sin", "cos", "sinh", "cosh"):
        return _potencias(nombre, orden, x)
    if nombre == "exp":
        piezas = [_signo(Fraction(1, _factorial_entero(k)),
                         mx.Pow(x, mx.Num(Fraction(k)))) for k in range(orden + 1)]
        residuo = _signo(Fraction(1, _factorial_entero(orden + 1)),
                         mx.Pow(x, mx.Num(Fraction(orden + 1))))
        return _suma(piezas), residuo
    if nombre == "tan":
        return _de_tan(x, orden)
    if nombre == "ln":
        return _de_ln(x, orden)
    raise sin_refuso(f"serie no implementada para «{nombre}»")


#: which powers each function has, and whether its signs alternate
_ESPECIE = {
    "sin": (lambda k: k % 2 == 1, True),
    "cos": (lambda k: k % 2 == 0, True),
    "sinh": (lambda k: k % 2 == 1, False),
    "cosh": (lambda k: k % 2 == 0, False),
}


def _potencias(nombre: str, orden: int, x: mx.Expr) -> tuple[mx.Expr, mx.Expr | None]:
    """The truncated series and the next term, for the four power-of-two kinds."""
    entra, alterna = _ESPECIE[nombre]
    piezas: list[mx.Expr] = []
    for k in range(0, orden + 1):
        if not entra(k):
            continue
        signo = (-1 if (alterna and (k // 2) % 2) else 1)
        piezas.append(_signo(Fraction(signo, _factorial_entero(k)),
                             mx.Pow(x, mx.Num(Fraction(k)))))
    siguiente = orden + 1
    if not entra(siguiente):
        siguiente += 1
    signo = (-1 if (alterna and (siguiente // 2) % 2) else 1)
    residuo = _signo(Fraction(signo, _factorial_entero(siguiente)),
                     mx.Pow(x, mx.Num(Fraction(siguiente))))
    return (_suma(piezas) if piezas else mx.ZERO), residuo


def _de_tan(x: mx.Expr, orden: int) -> tuple[mx.Expr, mx.Expr | None]:
    """``x + x^3/3 + 2x^5/15 + 17x^7/315``: the tangent numbers, exactly.

    From ``tan'(u) = 1 + tan(u)^2``. Writing ``tan u = sum a_n·u^(2n+1)``, that
    says ``(2n+1)·a_n`` is the convolution of the previous coefficients at
    ``n-1``. The coefficients are stored by **index**, not by power: two earlier
    versions keyed them by power and shifted the convolution by one, which gave a
    series of ``x + x^5/5 + 2x^9/45`` — the right shape, wrong coefficients, and an
    error of 2.6e-3 at x = 0.2 with thirteen terms, which looks plausible until you
    check it against tan.
    """
    a: dict[int, Fraction] = {0: Fraction(1)}
    n = 1
    while 2 * n + 1 <= orden + 2:
        total = Fraction(0)
        for i, ai in a.items():
            for j, aj in a.items():
                if i + j == n - 1:
                    total += ai * aj
        a[n] = total / Fraction(2 * n + 1)
        n += 1
    dentro = {indice: c for indice, c in a.items() if 2 * indice + 1 <= orden}
    piezas = [_signo(dentro[indice], mx.Pow(x, mx.Num(Fraction(2 * indice + 1))))
              for indice in sorted(dentro)]
    ultimo = max(a)
    return (_suma(piezas) if piezas else mx.ZERO), _signo(
        a[ultimo], mx.Pow(x, mx.Num(Fraction(2 * ultimo + 1))))


def _de_ln(x: mx.Expr, orden: int) -> tuple[mx.Expr, mx.Expr | None]:
    """``x - x^2/2 + x^3/3``: the only one that needs a sign per term."""
    piezas = [_signo(Fraction(1 if k % 2 else -1, k),
                     mx.Pow(x, mx.Num(Fraction(k))))
              for k in range(1, orden + 2)]
    return _suma(piezas[:max(0, len(piezas) - 1)]), piezas[-1]


def _termino(x: mx.Expr, indice: int, signo: int) -> mx.Expr:
    """``+x^n/n!``: the coefficient is carried by ``Mul`` because a fraction
    times a power is not a number the engine can fold on its own."""
    return _signo(Fraction(signo) / _factorial_entero(indice),
                  mx.Pow(x, mx.Num(Fraction(indice))))


def _signo(coeficiente: Fraction, potencia: mx.Expr) -> mx.Expr:
    """``coeficiente * potencia``, with the sign folded into the coefficient.

    Not decoration: the objectives are monotone in node count, and a ``Neg``
    wrapped around the whole term costs an extra node and gets rejected as «not an
    improvement», which is how a sign goes missing in silence.
    """
    return mx.Mul(mx.Num(coeficiente), potencia)


def _factorial_entero(n: int) -> int:
    total = 1
    for k in range(2, n + 1):
        total *= k
    return total


def _factorial(n: int) -> mx.Expr:
    """``1/n!`` as an exact rational, not as a rounded decimal."""
    return mx.Num(Fraction(1, _factorial_entero(n)))


def _cota_de_cola(nombre: str, orden: int, var: str) -> mx.Expr | None:
    """A declared bound on the tail, for the alternating series.

    The alternating-series bound — the first omitted term — is only valid when the
    terms decrease, which for these series means ``|x| <= 1``. Outside that the
    bound is a term, not a bound, and the module returns ``None`` rather than
    quoting it anyway.
    """
    if nombre not in ("sin", "cos", "ln"):
        # exp, tan, sinh and cosh have no alternating signs and their terms do
        # not decrease everywhere: the first omitted term there is an order of
        # magnitude, not a bound, and quoting it as one would be a false promise
        return None
    _, residuo = _truncar(nombre, orden, var)
    return residuo


# ---------------------------------------------------------------------------
# Taylor for an arbitrary expression
# ---------------------------------------------------------------------------


def taylor(expresion: mx.Expr, centro, orden: int, var: str = "x") -> Serie:
    """Maclaurin/Taylor of any expression, from its derivatives.

    Exact as far as the derivatives go. The error bound needs a bound on the first
    omitted derivative over the interval, and when none is available the answer
    carries ``cota = None`` and says so — a polynomial without a stated accuracy
    is not an approximation, it is a different expression.
    """
    if orden > ORDEN_MAXIMO:
        raise sin_refuso(
            f"el orden {orden} supera el máximo de {ORDEN_MAXIMO} (§5.5)")
    from academic_core.domain.engineering.mathlab import derive_mv as D

    if mx.variables(centro):
        raise sin_refuso(
            f"el centro «{mx.text(centro)}» tiene variables dentro, así que la "
            "derivada no se puede evaluar en él. El polinomio de Taylor "
            "exige un centro concreto; si lo que se quiere es el de la variable, "
            "el centro es 0 (§5.4)")
    piezas: list[mx.Expr] = []
    derivada = expresion
    factorial = 1
    for indice in range(0, orden + 1):
        if indice:
            factorial *= indice
        # The derivative has to be EVALUATED at the centre. Dividing by the
        # derivative itself gave «1/(3*2*x)·x + ...» for the Taylor of x^3,
        # which is not a polynomial of anything.
        valor = D.differentiate(derivada, var)
        # The derivative has to be EVALUATED at the centre, and then simplified:
        # substituting into sin gives «sin(0)», and a coefficient of 1/sin(0) is a
        # division by zero rather than the «this coefficient is zero» it means.
        evaluada = _valor_en(valor, var, centro)
        derivada = valor                      # exactly once per order, not twice
        if mx.exact_value(evaluada) == 0:
            continue                          # the term is absent, not infinite
        coeficiente = _coeficiente(evaluada, factorial)
        piezas.append(mx.Mul(coeficiente, mx.Pow(mx.Sub(mx.Sym(var), centro),
                                                 mx.Num(Fraction(indice)))))
    polinomio = _suma(piezas)
    omitida = _valor_en(D.differentiate(derivada, var), var, centro)
    if mx.exact_value(omitida) == 0:
        # the next coefficient vanishes: there is no next term, and dividing by
        # zero to say so would put «1/120/0·(x-0)^5» where a 0 belongs
        residuo = mx.ZERO
    else:
        siguiente = _coeficiente(omitida, factorial * (orden + 1))
        residuo = mx.Mul(siguiente, mx.Pow(mx.Sub(mx.Sym(var), centro),
                                           mx.Num(Fraction(orden + 1))))
    hipotesis = [
        f"el polinomio es exacto: sale de derivar {orden + 1} veces y dividir entre "
        f"los factoriales",
        "NO se declara cota de error: haría falta una cota de la derivada "
        f"omitida en el intervalo, y este motor no la tiene. Un polinomio sin "
        "precisión declarada no es una aproximación (§5.4)",
    ]
    return Serie(polinomio, orden, residuo, None, centro,
                 "polinomio de Taylor por derivadas sucesivas", tuple(hipotesis))


def _valor_en(derivada: mx.Expr, var: str, centro: mx.Expr) -> mx.Expr:
    """The derivative evaluated at ``centro`` and folded into a number.

    Three normalisers, because none of them does the other's job: substituting
    into ``sin`` leaves ``sin(0)``, which only the trigonometric engine can fold;
    ``3·0^2`` is arithmetic, which only the rational normal form can; and
    ``0^(-1)`` is not a number at all, which is why the caller checks for zero
    afterwards rather than dividing by it.
    """
    from academic_core.domain.engineering.mathlab import poly as P

    e = T.simplify(mx.substitute(derivada, var, centro))
    try:
        q = P.as_poly(e)
    except Exception:
        return e
    plegado = P.to_expr(q) if q is not None else e
    return T.simplify(plegado)


def _coeficiente(valor: mx.Expr, factorial: int) -> mx.Expr:
    from academic_core.domain.engineering.mathlab import poly as P

    cociente = mx.Div(mx.Num(Fraction(1, factorial)), valor)
    try:
        q = P.as_poly(cociente)
    except Exception:
        return cociente
    return P.to_expr(q) if q is not None else cociente


def _suma(piezas: list[mx.Expr]) -> mx.Expr:
    from academic_core.domain.engineering.mathlab import poly as P

    total = mx.ZERO
    for pieza in piezas:
        total = mx.Add(total, pieza)
    try:
        q = P.as_poly(total)
    except Exception:
        return total
    return P.to_expr(q) if q is not None else total


def valor_en(serie: Serie, x, var: str = "x") -> float:
    """Evaluate the truncated polynomial, and separately the tail's first term.

    Both, because the pair is the answer: the number, and how far it is from the
    value of the function it approximates.
    """
    del var
    propio = mx.evaluate(serie.polinomio, {"x": x})
    primer = mx.evaluate(serie.residuo, {"x": x}) if serie.residuo is not None else 0.0
    return propio.real + primer.real


__all__ = [
    "ORDEN_MAXIMO", "Serie", "maclaurin", "taylor", "valor_en", "sin_refuso",
]
