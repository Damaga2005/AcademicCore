# SPDX-License-Identifier: MIT
"""MATH_LAB T-11: inverse functions, compositions and their branches.

The rule this module exists to enforce
--------------------------------------

``asin(sin(x))`` is **not** ``x``. It is ``x`` on ``[-pi/2, pi/2]``, and outside
that interval it is something else entirely: at ``x = 3pi/2`` it is ``-pi/2``,
and a simplifier that says ``x`` there is teaching a false identity with the same
confidence as a true one. T-11 names the requirement — «evitar identidades
globales falsas» — and this module is how it is kept.

So there are two directions and they are not symmetric:

- ``sin(asin(u)) = u`` is true wherever it is defined, and the engine reduces it;
- ``asin(sin(x))`` is *piecewise*, so the engine refuses to rewrite it and
  :func:`ramas` hands over every branch with the interval it holds on.

Both facts are tests, not comments: ``test_el_motor_no_se_traga_la_identidad_falsa``
pins the refusal and ``test_cada_rama_se_verifica_sustituyendo`` checks every
branch numerically, because a wrong branch here is indistinguishable from a
right one by looking at it.

Domains
-------

The inverses have domains that are not the whole line, and they are not all the
same kind of interval: ``asin`` and ``acos`` need the **closed** ``[-1, 1]``,
``atanh`` needs the **open** ``(-1, 1)``, ``acosh`` needs the closed ``[1, ∞)``.
:mod:`dominio` grew its two openness flags for exactly this, and
:func:`dominios` is the single place that knows the difference.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import dominio as D
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import trig

#: the direct functions that have an inverse here, and the name of that inverse
INVERSAS = {"sin": "asin", "cos": "acos", "tan": "atan",
            "sinh": "asinh", "cosh": "acosh", "tanh": "atanh"}


# ---------------------------------------------------------------------------
# domains of the inverses
# ---------------------------------------------------------------------------


def _cerrado(izq: Fraction | None, der: Fraction | None) -> D.Intervalo:
    return D.Intervalo(None if izq is None else D.punto_pi(izq),
                       None if der is None else D.punto_pi(der),
                       False, False)


#: the domain of an inverse, in the *value* variable rather than in pi. They are
#: not all the same kind of interval: ``asin``/``acos`` need the closed
#: ``[-1,1]``, ``atanh`` the open ``(-1,1)`` — where it exists at all — and
#: ``acosh`` the closed ``[1, ∞)``. Reading them as one object is what makes an
#: engine accept ``atanh(1)``.
_DOMINIO_VALOR: dict[str, D.Conjunto] = {
    "asin": D.desde_intervalos([D.Intervalo(D.punto(Fraction(-1)),
                                           D.punto(Fraction(1)), False, False)]),
    "acos": D.desde_intervalos([D.Intervalo(D.punto(Fraction(-1)),
                                           D.punto(Fraction(1)), False, False)]),
    "atan": D.REALES,
    "asinh": D.REALES,
    "acosh": D.desde_intervalos([D.Intervalo(D.punto(Fraction(1)), None, False, True)]),
    "atanh": D.desde_intervalos([D.Intervalo(D.punto(Fraction(-1)),
                                            D.punto(Fraction(1)), True, True)]),
}


def dominio_de(nombre: str) -> D.Conjunto:
    """The domain of the inverse named ``nombre``; ``ℝ`` when it is all of it."""
    conjunto = _DOMINIO_VALOR.get(nombre)
    return conjunto if conjunto is not None else D.REALES


# ---------------------------------------------------------------------------
# the safe direction: f(f⁻¹(u)) = u
# ---------------------------------------------------------------------------


    """``sin(asin(u)) = u`` and its sisters, where they hold everywhere (T-11).

    Only the direction that is true wherever it is defined, and only in **that**
    direction: ``sin(asin(u)) = u`` holds, but ``asin(sin(x)) = x`` is false
    outside ``[-pi/2, pi/2]``. Matching the pair symmetrically is precisely how
    the second one slips through, so the outer call must be the direct function
    and the inner one its inverse — never the other way round.
    """
    if not (isinstance(e, mx.Call) and len(e.args) == 1):
        return None
    inversa = INVERSAS.get(e.name)
    if inversa is None or not _is_call(e.args[0], inversa):
        return None
    return e.args[0].args[0]


#: what each composition needs, in Spanish, for the step log (§5.7)
HIPOTESIS_INVERSAS = {
    "sin": "sin(arcsen(u)) = u para |u| ≤ 1, que es el dominio del arcsen",
    "cos": "cos(arccos(u)) = u para |u| ≤ 1, que es el dominio del arccos",
    "tan": "tan(arctan(u)) = u para todo u, porque la arctangente no tiene dominio",
    "sinh": "senh(arcsenh(u)) = u en toda la recta: las hiperbólicas son "
            "inyectivas y no hay rama que elegir",
    "cosh": "cosh(arccosh(u)) = u para u ≥ 1, que es el dominio del arccosh",
    "tanh": "tanh(arctanh(u)) = u para |u| < 1, y en u = ±1 no existe",
}


#: the compositions that are ``x`` on the whole line, because the function is
#: one-to-one and there is no branch to choose
INYECTIVAS = ("asinh(sinh)", "atanh(tanh)")

HIPERBOLICAS = frozenset({"sinh", "cosh", "tanh", "asinh", "acosh", "atanh"})


# ---------------------------------------------------------------------------
# the dangerous direction, piece by piece
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rama:
    """One branch of an inverse composition, with the interval it holds on."""

    expresion: mx.Expr
    intervalo: D.Intervalo
    nota: str = ""

    def texto(self, var: str) -> str:
        return (f"{mx.pretty(self.expresion)}   si   "
                f"{var} ∈ {self.intervalo.texto()}")


def _medio_pi(media: Fraction) -> mx.Expr:
    return mx.Mul(mx.Num(media), mx.PI)


def _c(x: mx.Expr) -> D.Intervalo:
    """``[a, b]`` closed, the usual shape of an inverse's principal range."""
    return D.Intervalo(D.punto_pi(x[0]), D.punto_pi(x[1]), False, False)


def _a(x: mx.Expr) -> D.Intervalo:
    """``[a, b)``: closed on the left, open on the right."""
    return D.Intervalo(D.punto_pi(x[0]), D.punto_pi(x[1]), False, True)


def _o(x: mx.Expr) -> D.Intervalo:
    """``(a, b)`` open on both sides — for the branches that end at a pole."""
    return D.Intervalo(D.punto_pi(x[0]), D.punto_pi(x[1]), True, True)


def ramas(nombre: str, var: str = "x") -> tuple[Rama, ...]:
    """Every branch of ``f⁻¹(f(x))``, each with the interval where it is true.

    Three families, and the shapes differ because the ranges differ:

    - ``arcsen(sen x)`` is ``x`` on ``[-pi/2, pi/2]`` and ``pi − x`` on
      ``[pi/2, 3pi/2]``, then repeats with period ``2pi``;
    - ``arccos(cos x)`` is ``x`` on ``[0, pi]`` and ``2pi − x`` on ``[pi, 2pi]``;
    - ``arctan(tan x)`` is ``x`` on ``(-pi/2, pi/2)`` — **open**, because the
      tangent has poles exactly at the ends.

    Only the principal period is listed. Extending it is ``x + 2k·pi``, and that
    is said rather than enumerated, because there are infinitely many.
    """
    x = mx.Sym(var)
    pi = mx.PI
    if nombre == "asin(sin)":
        return (
            Rama(x, _c((Fraction(-1, 2), Fraction(1, 2))),
                 "rama principal: aquí el arcsen deshace al seno"),
            Rama(mx.Sub(pi, x), _c((Fraction(1, 2), Fraction(3, 2))),
                 "segundo cuadrante: el seno es el mismo y el arcsen devuelve "
                 "el ángulo del primer cuadrante"),
            Rama(mx.Sub(x, mx.Mul(mx.Num(Fraction(2)), pi)),
                 _c((Fraction(3, 2), Fraction(5, 2))),
                 "el seno vuelve a ser negativo y el arcsen devuelve el ángulo "
                 "con signo: es x − 2·pi, no x − pi"),
        )
    if nombre == "acos(cos)":
        return (
            Rama(x, _c((Fraction(0), Fraction(1))),
                 "el rango del arccos es [0, pi]"),
            Rama(mx.Sub(mx.Mul(mx.Num(Fraction(2)), pi), x), _c((Fraction(1), Fraction(2))),
                 "simetría del coseno respecto de pi"),
        )
    if nombre == "atan(tan)":
        return (
            Rama(x, _o((Fraction(-1, 2), Fraction(1, 2))),
                 "abierto por los dos lados: la tangente tiene polos en ±pi/2, "
                 "así que en esos puntos el arctan no existe"),
        )
    if nombre == "asinh(sinh)":
        return (Rama(x, D.Intervalo(None, None),
                      "la hipérbole es inyectiva: una sola rama, sin condición"),)
    if nombre == "acosh(cosh)":
        return (
            Rama(x, D.Intervalo(None, D.punto_pi(Fraction(0)), True, False),
                 "el rango del arccosh es [0, ∞): por eso solo se deshace a la "
                 "derecha"),
            Rama(mx.Neg(x), D.Intervalo(D.punto_pi(Fraction(0)), None, False, True),
                 "a la izquierda del eje el coseno crece en sentido contrario"),
        )
    if nombre == "atanh(tanh)":
        return (Rama(x, D.Intervalo(None, None),
                      "la tangente hiperbólica es inyectiva: una sola rama"),)
    raise ValueError(f"no hay ramas conocidas para «{nombre}»")


def periodo_de_ramas(nombre: str) -> Fraction | None:
    """The period to add as ``+ 2k·pi`` to extend the branches beyond one period."""
    if nombre.startswith(("asin(sin)", "acos(cos)", "atan(tan)")):
        return Fraction(2)
    return None  # the hyperbolic ones: no repetition at all


def rama_principal(nombre: str, var: str = "x") -> Rama:
    """The branch that is ``x`` itself, with the interval it holds on."""
    principal = next((r for r in ramas(nombre, var)
                       if mx.text(r.expresion) == var), None)
    if principal is None:  # pragma: no cover - every family above has one
        raise ValueError(f"«{nombre}» no tiene rama principal")
    return principal


def evidencia_global(nombre: str) -> str:
    """Why the identity is false outside its interval, with a counterexample.

    §5.7 asks for the hypotheses to be *checked*, and a counterexample is the
    shortest possible check a student can redo in their head.
    """
    principal = rama_principal(nombre)
    fuera = _contrafuera(principal.intervalo)
    if fuera is None:
        # «unbounded on the left» is not the same as «injective»: acosh(cosh) has
        # an unbounded principal branch and is still not injective, and calling it
        # injective would be the same kind of false identity this module exists to
        # refuse
        if nombre in INYECTIVAS:
            return (f"{nombre} = x en toda la recta: la función es inyectiva, así "
                    "que no hay ninguna rama que elegir")
        return (f"{nombre} = x en {principal.intervalo.texto()}, que llega hasta "
                "el infinito por la izquierda: más allá hay que elegir rama. "
                "Por eso el motor no lo reescribe por su cuenta")
    expresion = _compone(mx.Sym("x"), nombre)
    pruebas = []
    for punto in fuera:
        valor = punto.valor()
        calculado = mx.evaluate(expresion, {"x": valor})
        if calculado is None or abs(calculado.imag) > 1e-9:
            continue
        pruebas.append(f"en {punto.texto()} vale {calculado.real:.6g}, "
                       f"no {valor:.6g}")
    cuerpo = "; ".join(pruebas) if pruebas else "el intervalo queda fuera de las ramas"
    return (f"{nombre} = x SOLO en {principal.intervalo.texto()}: fuera, "
            f"{cuerpo}. Por eso el motor no lo reescribe")


def _compone(x: mx.Expr, nombre: str) -> mx.Expr:
    izquierda, derecha = nombre.split("(")
    return mx.Call(izquierda, (mx.Call(derecha[:-1], (x,)),))


def _contrafuera(intervalo: D.Intervalo):
    """A clean point on each side, or ``None`` when a side is unbounded.

    Whole multiples of ``pi`` rather than a fractional offset: ``asin(sen(2pi)) = 0``
    is a counterexample a student can check in their head, and
    ``-1.2853981633974483·pi`` is not.
    """
    if intervalo.izq is None or intervalo.der is None:
        return None
    izquierda = D.punto_pi(_piso(intervalo.izq.coeficiente) - 1)
    derecha = D.punto_pi(_techo(intervalo.der.coeficiente) + 1)
    return izquierda, derecha


def _piso(c: Fraction) -> int:
    return c.numerator // c.denominator


def _techo(c: Fraction) -> int:
    return -((-c.numerator) // c.denominator)


# ---------------------------------------------------------------------------
# what the engine will and will not do
# ---------------------------------------------------------------------------

#: the compositions the engine refuses to touch, and why. Empty strings would be
#: a lie; the value is the reason, shown to the student (§5.4).
RECHAZADAS = {
    "asin(sin)": "no vale en toda la recta: solo en el intervalo principal",
    "acos(cos)": "no vale en toda la recta: solo en el rango del arccos",
    "atan(tan)": "no vale en toda la recta: la tangente tiene periodo pi",
    "acosh(cosh)": "no vale a la izquierda del eje",
}
