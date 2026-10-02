# SPDX-License-Identifier: MIT
"""MATH_LAB: exact trigonometric identities and canonical transformations.

This module is deliberately rule-based: identities are structural rewrites on
the expression AST, never numerical guesses. It is the trigonometric sub-engine
used by simplification, and the same exact rules can be reused by calculus and
by the independent verification of §5.3.

Why every rule declares an objective (T-20, and §5.5b)
-------------------------------------------------------

An engine that mixes both directions of every identity cannot terminate:
``sin(2x)`` expands to ``2·sin(x)·cos(x)`` and collapses straight back. So each
transformation belongs to exactly one objective, and each objective only accepts
a rewrite that moves *strictly* in its own direction, measured by
``(número de nodos, longitud del texto canónico)``:

- :func:`simplify` accepts only **cheaper** rewrites;
- :func:`expand` (T-04, T-05), :func:`product_to_sum` (T-08),
  :func:`sum_to_product` (T-09) and :func:`reduce_powers` (T-10) accept only
  **more expensive** ones.

That measure is a well-founded order on expressions, so every objective
terminates and its result is by construction a fixed point: no further rewrite
*of that objective* is accepted. This is the concrete form of T-20 («el motor
debe seleccionar transformaciones según el objetivo»), and it is why
:func:`simplify` can promise a reduced expression without risking an
oscillation.

Two rewrites are *not* cost-governed: the parity of §T-03 and the sign outside a
power are canonicalisations, they have no inverse, and every later rule assumes
them. They are listed apart in :func:`identities` so that the inventory stays
honest: a family cannot appear there without a rule behind it.

Nothing here is asserted to be sound, it is tested: every family is checked
against a seeded independent numeric path, because §11.2 criterion 2 forbids
presenting a result that no second check agreed with.

Families that are still pending (T-06 triple angle, T-07 ``t = tan(x/2)``,
T-11 inverse composition and its branches, T-14 hyperbolic, T-15 Euler) are
documented as such in ``docs/labs/MATH_LAB.md``: documenting is not
implementing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx

#: bound on the rewrite passes. Termination is already guaranteed by the cost
#: order; this only bounds pathological input (§5.4 honesty).
MAX_PASSES = 12

#: bound on the recursion of the rewrite traversal. ``mvexpr`` already caps text
#: input at 512 characters and evaluation at ``MAX_DEPTH``, so nothing a student
#: can type comes near this; it exists for trees that arrive already built (a
#: chain of ``substitute``, the E0.1 bridge). Two Python frames are used per
#: level of expression, hence 200 rather than a bigger number: the point is to
#: refuse in Spanish (§5.4, D2) instead of letting a ``RecursionError`` escape.
MAX_REWRITE_DEPTH = 200


# ---------------------------------------------------------------------------
# vocabulary
# ---------------------------------------------------------------------------

#: the four primitives and their period, in units of ``pi``. ``sec`` and ``csc``
#: are deliberately absent: they are the reciprocals of ``cos`` and ``sin``, so
#: they need no rule of their own. §5.5b — one family fewer to keep correct.
_PERIODO: dict[str, Fraction] = {
    "sin": Fraction(2),
    "cos": Fraction(2),
    "tan": Fraction(1),
    "cot": Fraction(1),
}

#: the functions whose exact value at a notable angle this engine knows
_CON_NOTABLES = frozenset({"sin", "cos", "tan", "cot", "sec", "csc"})

#: odd under ``x → -x``
_IMPARES = frozenset({"sin", "tan", "cot", "csc", "asin", "atan",
                      "sinh", "tanh", "coth", "csch", "asinh", "atanh"})

#: even under ``x → -x``; the rewrite is the same one with an empty sign
_PARES = frozenset({"cos", "sec", "acos", "cosh", "sech", "acosh"})


# ---------------------------------------------------------------------------
# small builders
# ---------------------------------------------------------------------------


def _num(n) -> mx.Num:
    return mx.Num(Fraction(n))


def _fn(name: str, arg: mx.Expr) -> mx.Call:
    return mx.Call(name, (arg,))


def _is_call(e: mx.Expr, name: str) -> bool:
    return isinstance(e, mx.Call) and e.name == name and len(e.args) == 1


def _arg(e: mx.Expr, name: str) -> mx.Expr | None:
    return e.args[0] if _is_call(e, name) else None


def _doble(u: mx.Expr) -> mx.Expr:
    return mx.Mul(_num(2), u)


def _signo(s: int, e: mx.Expr) -> mx.Expr:
    return e if s >= 0 else mx.Neg(e)


def _escalar(v: mx.Expr, k: int) -> mx.Expr:
    """``k·v`` with an exact integer ``k``, without a factor of 1 showing up."""
    if k < 0:
        return mx.Neg(_escalar(v, -k))
    if k == 1:
        return v
    return mx.Mul(_num(k), v)


def _entero(e: mx.Expr) -> int | None:
    """The exact integer value of ``e``, or ``None`` when it is not one."""
    return mx.exact_integer(e)


# ---------------------------------------------------------------------------
# flattened views of the AST
#
# The rewrites below must see *through* the association the parser happened to
# produce: ``2·sin·cos`` may be ``Mul(Mul(2,sin),cos)`` or ``Mul(2,Mul(sin,cos))``
# and both have to match the same rule. Two views are enough for every family.
# ---------------------------------------------------------------------------


def _terminos(e: mx.Expr) -> list[tuple[int, mx.Expr]]:
    """The summands of ``e`` as ``(sign, term)`` pairs, the sign being ±1."""
    if isinstance(e, mx.Add):
        return _terminos(e.left) + _terminos(e.right)
    if isinstance(e, mx.Sub):
        return _terminos(e.left) + [(-s, t) for s, t in _terminos(e.right)]
    if isinstance(e, mx.Neg):
        return [(-s, t) for s, t in _terminos(e.arg)]
    return [(1, e)]


def _factores(e: mx.Expr) -> tuple[Fraction, list[mx.Expr]]:
    """The numeric coefficient of ``e`` and its non-numeric factors."""
    if isinstance(e, mx.Mul):
        c1, f1 = _factores(e.left)
        c2, f2 = _factores(e.right)
        return c1 * c2, f1 + f2
    if isinstance(e, mx.Num):
        return e.value, []
    return Fraction(1), [e]


def _desde_factores(coef: Fraction, factores: list[mx.Expr]) -> mx.Expr:
    """Rebuild ``c·f1·f2…`` without leaving a factor of 1 lying around."""
    if not factores:
        return mx.Num(coef)
    out = factores[0]
    for f in factores[1:]:
        out = mx.Mul(out, f)
    if coef == 1:
        return out
    if coef > 0:
        return mx.Mul(mx.Num(coef), out)
    return mx.Neg(mx.Mul(mx.Num(-coef), out))


def _coef_de_pi(termino: mx.Expr) -> Fraction | None:
    """How many times ``pi`` this summand is, or ``None`` when it is not one.

    Recognises ``pi``, ``n·pi``, ``pi/n`` and their negations exactly. A summand
    that merely *contains* a ``pi`` (``pi·x``) gives ``None``, so it counts as
    part of the variable argument and no periodicity rule is applied to it.
    """
    if isinstance(termino, mx.Neg):
        k = _coef_de_pi(termino.arg)
        return None if k is None else -k
    if isinstance(termino, mx.Const):
        return Fraction(1) if termino.name == "pi" else None
    if isinstance(termino, mx.Num):
        return None
    if isinstance(termino, mx.Mul):
        coeficiente, factores = _factores(termino)
        return coeficiente if factores == [mx.Const("pi")] else None
    if isinstance(termino, mx.Div):
        arriba = _coef_de_pi(termino.left)
        if arriba is not None and isinstance(termino.right, mx.Num):
            return None if termino.right.value == 0 else arriba / termino.right.value
        return None
    return None


# ---------------------------------------------------------------------------
# exact values of the notable angles (T-21, the part this engine needs)
# ---------------------------------------------------------------------------

_TWO = mx.Num(Fraction(2))
_RAIZ2 = mx.Root(2, mx.Num(Fraction(2)))
_RAIZ3 = mx.Root(2, mx.Num(Fraction(3)))


def _medio(v: mx.Expr) -> mx.Expr:
    return mx.Div(v, _TWO)


#: ``k·pi`` → the exact value of each of the six circular functions, for the
#: angles a technical course uses: 0°, 30°, 45°, 60°, 90°, 120°, 135°, 150° and
#: 180°. Anything else is left as a symbol, which §5.4 asks for in place of a
#: decimal pretending to be exact.
#:
#: The six values are written out rather than derived by dividing: a table that
#: can be read is worth more here than an algebra that could be wrong, and a
#: ``None`` is exactly the angle where the function does not exist.
_NOTABLES: dict[Fraction, dict[str, mx.Expr | None]] = {
    Fraction(0): {"sin": mx.ZERO, "cos": mx.ONE, "tan": mx.ZERO,
                  "cot": None, "sec": mx.ONE, "csc": None},
    Fraction(1, 6): {"sin": _medio(mx.ONE), "cos": _medio(_RAIZ3),
                     "tan": mx.Div(mx.ONE, _RAIZ3), "cot": _RAIZ3,
                     "sec": mx.Div(_TWO, _RAIZ3), "csc": _TWO},
    Fraction(1, 4): {"sin": _medio(_RAIZ2), "cos": _medio(_RAIZ2),
                     "tan": mx.ONE, "cot": mx.ONE,
                     "sec": _RAIZ2, "csc": _RAIZ2},
    Fraction(1, 3): {"sin": _medio(_RAIZ3), "cos": _medio(mx.ONE),
                     "tan": _RAIZ3, "cot": mx.Div(mx.ONE, _RAIZ3),
                     "sec": _TWO, "csc": mx.Div(_TWO, _RAIZ3)},
    Fraction(1, 2): {"sin": mx.ONE, "cos": mx.ZERO, "tan": None,
                     "cot": mx.ZERO, "sec": None, "csc": mx.ONE},
    Fraction(2, 3): {"sin": _medio(_RAIZ3), "cos": mx.Neg(_medio(mx.ONE)),
                     "tan": mx.Neg(_RAIZ3), "cot": mx.Neg(mx.Div(mx.ONE, _RAIZ3)),
                     "sec": mx.Num(Fraction(-2)), "csc": mx.Div(_TWO, _RAIZ3)},
    Fraction(3, 4): {"sin": _medio(_RAIZ2), "cos": mx.Neg(_medio(_RAIZ2)),
                     "tan": mx.Num(Fraction(-1)), "cot": mx.Num(Fraction(-1)),
                     "sec": mx.Neg(_RAIZ2), "csc": _RAIZ2},
    Fraction(5, 6): {"sin": _medio(mx.ONE), "cos": mx.Neg(_medio(_RAIZ3)),
                     "tan": mx.Neg(mx.Div(mx.ONE, _RAIZ3)), "cot": mx.Neg(_RAIZ3),
                     "sec": mx.Neg(mx.Div(_TWO, _RAIZ3)), "csc": _TWO},
    Fraction(1): {"sin": mx.ZERO, "cos": mx.Num(Fraction(-1)), "tan": mx.ZERO,
                  "cot": None, "sec": mx.Num(Fraction(-1)), "csc": None},
}


def _valor_notable(nombre: str, k: Fraction) -> mx.Expr | None:
    """The exact value of ``nombre(k·pi)``, or ``None`` when it is not known.

    ``None`` also covers the angles where the function does not exist —
    ``tan(pi/2)``, ``sec(pi/2)``: the engine then leaves the expression alone
    instead of inventing a value, which is what §5.4 asks for.
    """
    valores = _NOTABLES.get(k)
    return None if valores is None else valores[nombre]


# ---------------------------------------------------------------------------
# canonicalisation (applied unconditionally, and not cost-governed)
# ---------------------------------------------------------------------------


def _r_paridad(e: mx.Expr) -> mx.Expr | None:
    """T-03: ``sin(-x) = -sin(x)`` and ``cos(-x) = cos(x)``.

    A negated argument hides the parity behind a quotient, so the sign is taken
    out of the call. This is a canonicalisation and not a reduction — it costs
    one character more — but it has no inverse, which is what makes it safe.
    """
    if not (isinstance(e, mx.Call) and len(e.args) == 1):
        return None
    if not isinstance(e.args[0], mx.Neg):
        return None
    if e.name in _IMPARES:
        return mx.Neg(mx.Call(e.name, (e.args[0].arg,)))
    if e.name in _PARES:
        return mx.Call(e.name, (e.args[0].arg,))
    return None


def _r_signo_fuera(e: mx.Expr) -> mx.Expr | None:
    """``(-u)^n`` → ``u^n`` or ``-(u^n)``: the sign belongs outside the power.

    Without this the Pythagorean and reciprocal rules below would never see a
    ``sin`` under a ``sin(-x)`` that arrived as ``(-sin(x))`` squared.
    """
    if not (isinstance(e, mx.Pow) and isinstance(e.base, mx.Neg)):
        return None
    n = _entero(e.exponent)
    if n is None:
        return None
    if n % 2 == 0:
        return mx.Pow(e.base.arg, e.exponent)
    return mx.Neg(mx.Pow(e.base.arg, e.exponent))


_NORMALIZACIONES: tuple[tuple[str, str, object], ...] = (
    ("paridad",
     "el signo se saca de la función: sin(-x) = -sin(x) y cos(-x) = cos(x), "
     "porque un argumento negativo esconde la paridad detrás de un cociente",
     _r_paridad),
    ("signo_fuera_potencia",
     "el signo de una potencia se escribe fuera: (-sin(x))² es sin(x)², y así "
     "las reglas pitagóricas ven un seno y no una negación de un seno",
     _r_signo_fuera),
)


def _reconstruir(e: mx.Expr, hijo) -> mx.Expr:
    """Rebuild ``e`` after mapping every child through ``hijo``.

    The two canonicalisations are applied here and nowhere else, so they hold for
    every node of the tree instead of only for the one being rewritten.
    """
    if isinstance(e, mx.Neg):
        arg = hijo(e.arg)
        return arg if isinstance(arg, mx.Neg) else mx.Neg(arg)
    if isinstance(e, mx.Pow):
        base, exponente = hijo(e.base), hijo(e.exponent)
        signo = _r_signo_fuera(mx.Pow(base, exponente))
        return mx.Pow(base, exponente) if signo is None else signo
    if isinstance(e, mx.Call):
        argumentos = tuple(hijo(a) for a in e.args)
        llamada = mx.Call(e.name, argumentos)
        paridad = _r_paridad(llamada)
        return llamada if paridad is None else paridad
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return type(e)(hijo(e.left), hijo(e.right))
    if isinstance(e, mx.Root):
        return mx.Root(e.degree, hijo(e.radicand))
    if isinstance(e, mx.Integral):
        return mx.Integral(hijo(e.integrand), e.var, e.lower, e.upper)
    if isinstance(e, mx.Limit):
        return mx.Limit(hijo(e.expr), e.var, e.point, e.side)
    if isinstance(e, mx.Sum):
        return mx.Sum(hijo(e.body), e.var, e.lower, e.upper)
    if isinstance(e, mx.Derivative):
        return mx.Derivative(hijo(e.expr), e.var, e.order)
    return e


# ---------------------------------------------------------------------------
# T-03 and T-21: what the argument itself says
# ---------------------------------------------------------------------------


def _TABLA_ARGUMENTO() -> dict[tuple[str, Fraction], object]:
    """``(función, k·pi)`` → construction, for an argument written ``k·pi + s·u``.

    ``s`` is the sign of the summand that is not a multiple of ``pi`` and ``u``
    its body, so a single row per quadrant covers both signs: ``sin(pi - u)`` and
    ``sin(pi + u)`` are the same identity read with ``s = -1`` and ``s = 1``.
    Every identity here holds for an arbitrary real ``u``, never only for a
    principal value — the difference between a true identity and a false one.
    """
    return {
        ("sin", Fraction(0)): lambda s, u: _signo(s, _fn("sin", u)),
        ("sin", Fraction(1, 2)): lambda s, u: _fn("cos", u),
        ("sin", Fraction(1)): lambda s, u: _signo(-s, _fn("sin", u)),
        ("sin", Fraction(3, 2)): lambda s, u: _signo(-s, _fn("cos", u)),
        ("cos", Fraction(0)): lambda s, u: _fn("cos", u),
        ("cos", Fraction(1, 2)): lambda s, u: _signo(-s, _fn("sin", u)),
        ("cos", Fraction(1)): lambda s, u: mx.Neg(_fn("cos", u)),
        ("cos", Fraction(3, 2)): lambda s, u: _signo(s, _fn("sin", u)),
        ("tan", Fraction(0)): lambda s, u: _signo(s, _fn("tan", u)),
        ("tan", Fraction(1, 2)): lambda s, u: _signo(-s, _fn("cot", u)),
        ("cot", Fraction(0)): lambda s, u: _signo(s, _fn("cot", u)),
        ("cot", Fraction(1, 2)): lambda s, u: _signo(-s, _fn("tan", u)),
    }


_TABLA = _TABLA_ARGUMENTO()


def _r_reducir_argumento(e: mx.Expr) -> mx.Expr | None:
    """Periodicity, opposite, supplementary and complementary angles (T-03)."""
    if not (isinstance(e, mx.Call) and len(e.args) == 1 and e.name in _PERIODO):
        return None
    k, resto = Fraction(0), []
    for signo, termino in _terminos(e.args[0]):
        coeficiente = _coef_de_pi(termino)
        if coeficiente is not None:
            k += signo * coeficiente
        elif isinstance(termino, mx.Neg):
            resto.append((-signo, termino.arg))
        else:
            resto.append((signo, termino))
    if len(resto) != 1:
        return None  # nothing to fold, or an argument that is not a sum of angles
    regla = _TABLA.get((e.name, k % _PERIODO[e.name]))
    return None if regla is None else regla(resto[0][0], resto[0][1])


def _r_valores_notables(e: mx.Expr) -> mx.Expr | None:
    """T-21: the exact value at a notable angle, or nothing at all."""
    if not (isinstance(e, mx.Call) and len(e.args) == 1 and e.name in _CON_NOTABLES):
        return None
    k = _coef_de_pi(e.args[0])
    if k is None:
        return None
    return _valor_notable(e.name, k % _PERIODO.get(e.name, Fraction(2)))


# ---------------------------------------------------------------------------
# T-02: the fundamental relations
# ---------------------------------------------------------------------------


def _potencia_de(e: mx.Expr, nombre: str, n: int) -> mx.Expr | None:
    """``f(u)^n`` → ``u``, when ``e`` is exactly that."""
    if not (isinstance(e, mx.Pow) and e.exponent == _num(n)):
        return None
    return _arg(e.base, nombre)


def _r_pitagoras(e: mx.Expr) -> mx.Expr | None:
    """``sin²+cos² = 1`` and its solved forms, recognised by structure (T-02)."""
    if isinstance(e, mx.Add):
        izquierda, derecha = e.left, e.right
        for a, b in ((izquierda, derecha), (derecha, izquierda)):
            x, y = _potencia_de(a, "sin", 2), _potencia_de(b, "cos", 2)
            if x is not None and y is not None and x == y:
                return mx.ONE
        for constante, nombre, recíproca in ((izquierda, "tan", "sec"),
                                            (izquierda, "cot", "csc"),
                                            (derecha, "tan", "sec"),
                                            (derecha, "cot", "csc")):
            otro = derecha if constante is izquierda else izquierda
            if constante != mx.ONE:
                continue
            x = _potencia_de(otro, nombre, 2)
            if x is not None:
                return mx.Pow(_fn(recíproca, x), _num(2))
    elif isinstance(e, mx.Sub):
        izquierda, derecha = e.left, e.right
        if izquierda == mx.ONE:  # 1 - sin² = cos² ; 1 - cos² = sin²
            for nombre, resto in (("sin", "cos"), ("cos", "sin")):
                x = _potencia_de(derecha, nombre, 2)
                if x is not None:
                    return mx.Pow(_fn(resto, x), _num(2))
        if derecha == mx.ONE:  # sec² - 1 = tan² ; csc² - 1 = cot²
            for nombre, resto in (("sec", "tan"), ("csc", "cot")):
                x = _potencia_de(izquierda, nombre, 2)
                if x is not None:
                    return mx.Pow(_fn(resto, x), _num(2))
        for nombre, resto in (("sec", "tan"), ("csc", "cot")):
            # sec² - tan² = 1 ; csc² - cot² = 1
            x, y = _potencia_de(izquierda, nombre, 2), _potencia_de(derecha, resto, 2)
            if x is not None and y is not None and x == y:
                return mx.ONE
    return None


def _r_reciprocas(e: mx.Expr) -> mx.Expr | None:
    """``tan = sin/cos`` and every reciprocal form of the same relation (T-02)."""
    if isinstance(e, mx.Div):
        izquierda, derecha = e.left, e.right
        for numerador, denominador, nombre in (("sin", "cos", "tan"),
                                              ("cos", "sin", "cot")):
            a, b = _arg(izquierda, numerador), _arg(derecha, denominador)
            if a is not None and b is not None and a == b:
                return _fn(nombre, a)
        if izquierda == mx.ONE:  # 1/cos = sec ; 1/sin = csc ; 1/tan = cot
            for fuente, destino in (("cos", "sec"), ("sin", "csc"), ("tan", "cot")):
                u = _arg(derecha, fuente)
                if u is not None:
                    return _fn(destino, u)
    elif isinstance(e, mx.Mul):
        coeficiente, factores = _factores(e)
        if coeficiente == 1 and len(factores) == 2:  # cos·sec = 1 and its two kin
            for p, q in (("cos", "sec"), ("sin", "csc"), ("tan", "cot")):
                u, v = _arg(factores[0], p), _arg(factores[1], q)
                if u is not None and v is not None and u == v:
                    return mx.ONE
                u, v = _arg(factores[0], q), _arg(factores[1], p)
                if u is not None and v is not None and u == v:
                    return mx.ONE
    return None


# ---------------------------------------------------------------------------
# T-04 and T-05 read the other way: folding an expansion back into one call
# ---------------------------------------------------------------------------


def _escala_potencia(e: mx.Expr, coeficiente: Fraction,
                     nombre: str, n: int) -> mx.Expr | None:
    """``c·f(u)^n`` → ``u``, which is how ``1 - 2·sin²(x)`` gets recognised."""
    c, factores = _factores(e)
    if c != coeficiente or len(factores) != 1:
        return None
    factor = factores[0]
    if isinstance(factor, mx.Pow):
        return _arg(factor.base, nombre) if factor.exponent == _num(n) else None
    return _arg(factor, nombre) if n == 1 else None


def _r_doble_doblado(e: mx.Expr) -> mx.Expr | None:
    """Fold a double angle written as products back into one call (T-05)."""
    if isinstance(e, mx.Sub):
        izquierda, derecha = e.left, e.right
        if izquierda == mx.ONE:  # 1 - 2·sin²(x) = cos(2x)
            x = _escala_potencia(derecha, Fraction(2), "sin", 2)
            if x is not None:
                return _fn("cos", _doble(x))
        if derecha == mx.ONE:  # 2·cos²(x) - 1 = cos(2x)
            x = _escala_potencia(izquierda, Fraction(2), "cos", 2)
            if x is not None:
                return _fn("cos", _doble(x))
        for primero, segundo, signo in (("cos", "sin", 1), ("sin", "cos", -1)):
            # cos²-sin² = cos(2x) ; sin²-cos² = -cos(2x)
            x = _potencia_de(izquierda, primero, 2)
            y = _potencia_de(derecha, segundo, 2)
            if x is not None and y is not None and x == y:
                return _signo(signo, _fn("cos", _doble(x)))
    elif isinstance(e, mx.Mul):  # 2·sin(x)·cos(x) = sin(2x)
        coeficiente, factores = _factores(e)
        if coeficiente == 2 and len(factores) == 2:
            a, b = _arg(factores[0], "sin"), _arg(factores[1], "cos")
            if a is None or b is None or a != b:
                a, b = _arg(factores[0], "cos"), _arg(factores[1], "sin")
            if a is not None and b is not None and a == b:
                return _fn("sin", _doble(a))
    elif isinstance(e, mx.Div):  # 2·tan(x)/(1 - tan²(x)) = tan(2x)
        denominador = e.right
        if not (isinstance(denominador, mx.Sub) and denominador.left == mx.ONE):
            return None
        x = _escala_potencia(e.left, Fraction(2), "tan", 1)
        y = _potencia_de(denominador.right, "tan", 2)
        return _fn("tan", _doble(x)) if x is not None and y == x else None
    return None


def _dos_trigonometricas(termino: mx.Expr) -> tuple[str, mx.Expr, str, mx.Expr] | None:
    """``sin(a)·cos(b)`` → ``("sin", a, "cos", b)``; anything else → ``None``."""
    if not isinstance(termino, mx.Mul):
        return None
    coeficiente, factores = _factores(termino)
    if coeficiente != 1 or len(factores) != 2:
        return None
    a, b = factores
    if not (isinstance(a, mx.Call) and isinstance(b, mx.Call)):
        return None
    if a.name not in {"sin", "cos"} or b.name not in {"sin", "cos"}:
        return None
    return a.name, a.args[0], b.name, b.args[0]


def _r_suma_diferencia_inversa(e: mx.Expr) -> mx.Expr | None:
    """Recognise the expansion of ``sin(a±b)`` and ``cos(a±b)`` (T-04 inverso).

    It is a *reduction*: four calls and two products collapse into one call,
    which is why it belongs to ``simplify`` and not to ``expand``.
    """
    if not isinstance(e, (mx.Add, mx.Sub)):
        return None
    terminos = _terminos(e)
    if len(terminos) != 2:
        return None
    (s1, t1), (s2, t2) = terminos
    p1, p2 = _dos_trigonometricas(t1), _dos_trigonometricas(t2)
    if p1 is None or p2 is None:
        return None
    for (f1, u1, f2, u2), (f3, u3, f4, u4) in ((p1, p2), (p2, p1)):
        if u1 != u3 or u2 != u4:
            continue
        if (f1, f2, f3, f4) == ("sin", "cos", "cos", "sin"):
            if u1 == u2:
                return _fn("sin", _doble(u1))
            return _fn("sin", mx.Add(u1, u2) if s2 >= 0 else mx.Sub(u1, u2))
        if (f1, f2, f3, f4) == ("cos", "cos", "sin", "sin"):
            return mx.ONE if u1 == u2 else _fn(
                "cos", mx.Sub(u1, u2) if s2 >= 0 else mx.Add(u1, u2))
    return None


#: ``función → {exponente: coeficiente con signo}`` del ángulo triple:
#: sin(3x) = 3·sin(x) − 4·sin(x)³ y cos(3x) = 4·cos(x)³ − 3·cos(x).
_TERCIO = {"sin": {1: 3, 3: -4}, "cos": {1: -3, 3: 4}}


def _termino_potencia(signo: int, termino: mx.Expr, nombre: str):
    """``(coeficiente con signo, exponente, argumento)`` de un término ``c·f(u)^n``.

    The sign travels *with* the coefficient: ``− 4·sin(x)³`` arrives as sign
    ``−1`` and coefficient ``4``, and confusing the two is exactly how a rule
    ends up accepting ``3·sin(x) − 4·cos(x)³`` as a triple angle.
    """
    coeficiente, factores = _factores(termino)
    if len(factores) != 1:
        return None
    factor = factores[0]
    if isinstance(factor, mx.Pow):
        n = _entero(factor.exponent)
        u = _arg(factor.base, nombre)
        return None if (n is None or u is None) else (signo * coeficiente, n, u)
    u = _arg(factor, nombre)
    return None if u is None else (signo * coeficiente, 1, u)


def _r_triple_doblado(e: mx.Expr) -> mx.Expr | None:
    """Recognise the triple angle written in powers (T-06 inverso).

    ``3·sin(x) − 4·sin(x)³`` and ``4·cos(x)³ − 3·cos(x)`` are ``sin(3x)`` and
    ``cos(3x)``, so folding them back *is* a reduction, while the other way round
    is not. That asymmetry is why T-06 lives half in each objective.
    """
    if not isinstance(e, (mx.Add, mx.Sub)):
        return None
    terminos = _terminos(e)
    if len(terminos) != 2:
        return None
    for nombre, esperado in _TERCIO.items():
        Powers: dict[int, mx.Expr] = {}
        for signo, termino in terminos:
            medido = _termino_potencia(signo, termino, nombre)
            if medido is None:
                continue
            coeficiente, n, u = medido
            if esperado.get(n) == coeficiente and n not in Powers:
                Powers[n] = u
        if len(Powers) == 2 and Powers[1] == Powers[3]:
            return _fn(nombre, mx.Mul(_num(3), Powers[1]))
    return None


def _medio_angulo(x: mx.Expr) -> mx.Expr:
    """``x/2``, written the way it is written in the half-angle identities."""
    return mx.Div(x, _TWO)


def _uno_mas_f(e: mx.Expr, nombre: str) -> tuple[mx.Expr, int] | None:
    """``1 ± cos(u)`` → ``(u, signo)``, where the sign belongs to the ``f(u)``.

    The sign comes from the *node*, not from a ``Neg`` inside it: ``1 - cos(x)``
    is a ``Sub``, and the coseno that comes out of it carries ``−1``. Reading the
    sign off a ``Neg`` instead gets ``1 − cos(x)`` confused with ``1 + cos(x)``
    and silently swaps ``sin²(x/2)`` for ``cos²(x/2)``.
    """
    if isinstance(e, mx.Sub):
        if e.left != mx.ONE:
            return None
        if isinstance(e.right, mx.Neg):  # 1 - (-cos u) written out: really a sum
            u = _arg(e.right.arg, nombre)
            return None if u is None else (u, +1)
        u = _arg(e.right, nombre)
        return None if u is None else (u, -1)
    if isinstance(e, mx.Add):
        if isinstance(e.left, mx.Num) and e.left.value == 1:
            u = _arg(e.right, nombre)
            return None if u is None else (u, +1)
        if isinstance(e.right, mx.Num) and e.right.value == 1:
            u = _arg(e.left, nombre)
            return None if u is None else (u, +1)
    return None


def _r_medio_angulo_doblado(e: mx.Expr) -> mx.Expr | None:
    """Recognise the half angle written in full angles (T-07 inverso).

    ``(1−cos x)/2``, ``(1+cos x)/2`` and ``(1−cos x)/(1+cos x)`` are
    ``sin²(x/2)``, ``cos²(x/2)`` and ``tan²(x/2)``. Only the *squares* are folded
    back, never a bare square root: ``√((1−cos x)/2) = sin(x/2)`` holds on
    ``[0, 2π]`` and fails outside it, and §5.7 wants that hypothesis written down
    rather than assumed away.
    """
    if not isinstance(e, mx.Div):
        return None
    numerador, denominador = e.left, e.right
    if denominador == _TWO:  # (1 ∓ cos x)/2
        for nombre, signo in (("cos", -1), ("cos", 1)):
            pareja = _uno_mas_f(numerador, nombre)
            if pareja is not None and pareja[1] == signo:
                destino = "sin" if signo < 0 else "cos"
                return mx.Pow(_fn(destino, _medio_angulo(pareja[0])), _num(2))
        return None
    arriba = _uno_mas_f(numerador, "cos")
    abajo = _uno_mas_f(denominador, "cos")
    if arriba is None or abajo is None or arriba[0] != abajo[0] or arriba[1] == abajo[1]:
        return None
    destino = "tan" if arriba[1] < 0 else "cot"
    return mx.Pow(_fn(destino, _medio_angulo(arriba[0])), _num(2))


# ---------------------------------------------------------------------------
# T-14: trigonometría hiperbólica
#
# The hyperbolic identities are the circular ones with a sign changed, which is
# exactly why they belong in the same engine: ``cos²−sin² = 1`` becomes
# ``cosh²−sinh² = 1``, ``1+tan² = sec²`` becomes ``1−tanh² = sech²``, and the sum
# formulas swap the signs on one of the two terms. Same machinery, separate
# families, so that the step log says which one fired.
# ---------------------------------------------------------------------------

#: the three that generate the rest, as in the circular case
_HIPERBOLICAS = ("sinh", "cosh", "tanh")


#: ``f²(u) − 1 = g²(u)``. Only two pairs have this shape: ``cosh²−1 = sinh²`` and
#: ``coth²−1 = csch²``. ``tanh`` is *not* one of them (``1+tanh² = sech²+2``), and
#: neither is ``sinh`` — writing ``sinh²−1 = cosh²`` is a false identity, which is
#: exactly the sort of thing T-14 warns about and that the numeric check rejects.
_CUADRADO_MENOS_UNO = (("cosh", "sinh"), ("coth", "csch"))

#: ``1 − f²(u) = ±g²(u)``. The sign is hyperbolic, not cosmetic: ``1 − coth²`` is
#: ``−csch²``, and writing it as ``+csch²`` would be a false identity.
_UNO_MENOS_CUADRADO = (("tanh", "sech", 1), ("coth", "csch", -1))


def _r_hiberbolicas_relaciones(e: mx.Expr) -> mx.Expr | None:
    """``cosh²−sinh²=1``, ``1−tanh²=sech²`` and the reciprocals (T-14).

    There is deliberately no ``1 + f² = g²`` rule: no hyperbolic pair has that
    shape, and the only way to find out is to check.
    """
    if isinstance(e, mx.Sub):
        izquierda, derecha = e.left, e.right
        for nombre, recíproca, signo in _UNO_MENOS_CUADRADO:
            if izquierda == mx.ONE:
                x = _potencia_de(derecha, nombre, 2)
                if x is not None:
                    return _signo(signo, mx.Pow(_fn(recíproca, x), _num(2)))
        for nombre, recíproca in _CUADRADO_MENOS_UNO:
            if derecha == mx.ONE:
                x = _potencia_de(izquierda, nombre, 2)
                if x is not None:
                    return mx.Pow(_fn(recíproca, x), _num(2))
        # cosh²(u) − sinh²(u) = 1
        x, y = _potencia_de(izquierda, "cosh", 2), _potencia_de(derecha, "sinh", 2)
        if x is not None and y is not None and x == y:
            return mx.ONE
        # sinh²(u) − cosh²(u) = −1
        x, y = _potencia_de(izquierda, "sinh", 2), _potencia_de(derecha, "cosh", 2)
        if x is not None and y is not None and x == y:
            return mx.Num(Fraction(-1))
    elif isinstance(e, mx.Div):
        izquierda, derecha = e.left, e.right
        for numerador, denominador, nombre in (("sinh", "cosh", "tanh"),
                                              ("cosh", "sinh", "coth")):
            a, b = _arg(izquierda, numerador), _arg(derecha, denominador)
            if a is not None and b is not None and a == b:
                return _fn(nombre, a)
        if izquierda == mx.ONE:
            for fuente, destino in (("cosh", "sech"), ("sinh", "csch"),
                                    ("tanh", "coth")):
                u = _arg(derecha, fuente)
                if u is not None:
                    return _fn(destino, u)
    elif isinstance(e, mx.Mul):
        coeficiente, factores = _factores(e)
        if coeficiente == 1 and len(factores) == 2:
            for p, q in (("cosh", "sech"), ("sinh", "csch"), ("tanh", "coth")):
                u, v = _arg(factores[0], p), _arg(factores[1], q)
                if u is not None and v is not None and u == v:
                    return mx.ONE
                u, v = _arg(factores[0], q), _arg(factores[1], p)
                if u is not None and v is not None and u == v:
                    return mx.ONE
    return None


def _r_hiberbolicas_doble_doblado(e: mx.Expr) -> mx.Expr | None:
    """``cosh²+sinh² = cosh(2x)``, ``1+2·sinh² = cosh(2x)`` (T-14 inverso)."""
    if isinstance(e, mx.Add):
        for a, b in ((e.left, e.right), (e.right, e.left)):
            x = _potencia_de(a, "cosh", 2)
            y = _potencia_de(b, "sinh", 2)
            if x is not None and x == y:
                return _fn("cosh", _doble(x))
            x = _potencia_de(a, "sinh", 2)
            y = _potencia_de(b, "cosh", 2)
            if x is not None and x == y:
                return _fn("cosh", _doble(x))
        # 1 + 2·sinh²(u) = cosh(2u). It is a *sum*, not a difference: cosh(2x) =
        # cosh²+sinh² and cosh² = 1 + sinh², so the two 1's cancel in the middle.
        for uno, resto in ((e.left, e.right), (e.right, e.left)):
            if uno != mx.ONE:
                continue
            u = _escala_potencia(resto, Fraction(2), "sinh", 2)
            if u is not None:
                return _fn("cosh", _doble(u))
    elif isinstance(e, mx.Mul):
        coeficiente, factores = _factores(e)
        if coeficiente == 2 and len(factores) == 2:
            a, b = _arg(factores[0], "sinh"), _arg(factores[1], "cosh")
            if a is None or b is None or a != b:
                a, b = _arg(factores[0], "cosh"), _arg(factores[1], "sinh")
            if a is not None and b is not None and a == b:
                return _fn("sinh", _doble(a))
    return None


def _r_hiberbolicas_inversa(e: mx.Expr) -> mx.Expr | None:
    """``sinh(asinh(x)) = x`` and its two sisters (T-14).

    These are safe in *every* direction, unlike the circular ones: the hyperbolic
    functions are one-to-one on the whole real line, so there is no branch to
    get wrong. T-11 is exactly about the circular case where there is.
    """
    if not (isinstance(e, mx.Call) and len(e.args) == 1):
        return None
    for directa, inversa in (("sinh", "asinh"), ("cosh", "acosh"), ("tanh", "atanh")):
        if e.name == directa and _is_call(e.args[0], inversa):
            return e.args[0].args[0]
    return None


def _r_hiberbolicas_cero(e: mx.Expr) -> mx.Expr | None:
    """``sinh(0)=0``, ``cosh(0)=1``, ``tanh(0)=0`` — the only exact ones at zero."""
    if not (isinstance(e, mx.Call) and len(e.args) == 1 and e.args[0] == mx.ZERO):
        return None
    if e.name in {"sinh", "tanh"}:
        return mx.ZERO
    if e.name == "cosh":
        return mx.ONE
    return None


def _r_inversa_directa(e: mx.Expr) -> mx.Expr | None:
    """``sin(asin(u)) = u`` and its sisters, where they hold everywhere (T-11).

    Only the direction that is true wherever it is defined. The other one,
    ``asin(sin(x))``, is piecewise and the engine refuses it on purpose: the
    branches and their intervals live in :mod:`ramas`, with the reason in Spanish
    for the student (§5.4, §5.7).
    """
    from academic_core.domain.engineering.mathlab.ramas import INVERSAS

    if not (isinstance(e, mx.Call) and len(e.args) == 1):
        return None
    inversa = INVERSAS.get(e.name)
    if inversa is None or not _is_call(e.args[0], inversa):
        return None
    return e.args[0].args[0]


def _r_invierte(e: mx.Expr) -> mx.Expr | None:
    """``1/(1/u) = u`` and ``u/(1/u) = u²``: a quotient of quotients.

    Not a rare shape. It is what appears the moment a reciprocal is written the
    long way — ``sec(x)`` as ``1/cos(x)``, or ``cos(x) = 1/sec(x)`` — and left
    unfolded it hides the very structure the equation solver looks for.
    """
    if not isinstance(e, mx.Div):
        return None
    if not (isinstance(e.right, mx.Div) and e.right.left == mx.ONE):
        return None
    u = e.right.right
    if e.left == mx.ONE:
        return u
    if e.left == u:
        return mx.Pow(u, _num(2))
    return None


def _r_unidad(e: mx.Expr) -> mx.Expr | None:
    """Fold ``1·u`` and ``u·1``, so a simplification is shown in its plain form.

    ``0`` is deliberately *not* folded: ``0·tan(x)`` is undefined wherever
    ``tan`` is, while the product is not, and §5.7 asks for the hypotheses of a
    step to be checked rather than assumed away.
    """
    if not isinstance(e, mx.Mul):
        return None
    if e.left == mx.ONE:
        return e.right
    if e.right == mx.ONE:
        return e.left
    return None


_REGLAS: tuple[tuple[str, str, object], ...] = (
    ("reduccion_argumento",
     "el argumento se baja a un cuadrante: periodicidad, ángulos opuestos, "
     "suplementarios y complementarios salen de una sola tabla en lugar de una "
     "regla por signo, y así ninguno de ellos depende de un ángulo principal",
     _r_reducir_argumento),
    ("valores_notables",
     "en un ángulo notable el valor exacto es un racional o una raíz, y una "
     "expresión exacta vale más que un decimal (§5.1)",
     _r_valores_notables),
    ("pitagoras",
     "sin²+cos² = 1 y sus formas despejadas se reconocen por la estructura de "
     "la suma o la resta, nunca por evaluación numérica",
     _r_pitagoras),
    ("reciprocas",
     "tan = sin/cos, y sec, csc y cot son recíprocas: una sola familia cubre "
     "las seis formas en que la misma relación puede escribirse",
     _r_reciprocas),
    ("doble_doblado",
     "1-2·sin², 2·cos²-1, cos²-sin² y 2·sin·cos son el ángulo doble escrito al "
     "revés, así que volver a cos(2x) o sin(2x) sí reduce",
     _r_doble_doblado),
    ("suma_diferencia_inversa",
     "sin·cos + cos·sin es un sin(a+b) disfrazado: reconocerlo quita dos "
     "productos, que es lo que T-04 pide en sentido inverso",
     _r_suma_diferencia_inversa),
    ("unidad",
     "el factor 1 se pliega: sin él el resultado se mostraría como «x·1», que "
     "es cierto y aun así está mal escrito (§5.1)",
     _r_unidad),
    ("triple_doblado",
     "3·sin − 4·sin³ y 4·cos³ − 3·cos son el ángulo triple escrito en potencias: "
     "reconocerlo lo reduce, al revés de lo que hace el desarrollo (T-06)",
     _r_triple_doblado),
    ("medio_angulo_doblado",
     "(1∓cos x)/2 y (1∓cos x)/(1±cos x) son el medio ángulo al cuadrado: al "
     "cuadrado no hay problema de signo, y sin cuadrado sí lo habría (T-07)",
     _r_medio_angulo_doblado),
    ("hiperbolicas_relaciones",
     "cosh²−sinh²=1 y 1−tanh²=sech² son las de T-02 con un signo cambiado; las "
     "recíprocas y los cocientes se reconocen igual que en el caso circular",
     _r_hiberbolicas_relaciones),
    ("hiperbolicas_doble_doblado",
     "cosh²+sinh² y 2·sinh·cosh son el ángulo doble hiperbólico al revés: "
     "plegarlos vuelve a cosh(2x) y sinh(2x), que sí reduce (T-14)",
     _r_hiberbolicas_doble_doblado),
    ("hiperbolicas_inversa",
     "sinh(asinh(x)) = x sin condición de intervalo, porque las hiperbólicas son "
     "inyectivas en toda la recta: es justo lo que en el caso circular falla (T-11)",
     _r_hiberbolicas_inversa),
    ("hiperbolicas_cero",
     "en el origen el valor exacto se conoce: sinh(0)=0, cosh(0)=1, tanh(0)=0, "
     "y un decimal no mejora nada (T-21, §5.1)",
     _r_hiberbolicas_cero),
    ("inversa_directa",
     "sin(arcsen(u)) = u es cierta allí donde está definida, sin condición de "
     "rama: al revés, arcsen(sen x) = x NO lo es, y ese caso se rehúsa (T-11)",
     _r_inversa_directa),
    ("invierte",
     "1/(1/u) se desenrolla a u: es la forma que aparece en cuanto una recíproca "
     "se escribe larga, y sin esto el solucionador no ve la estructura (T-12)",
     _r_invierte),
)


# ---------------------------------------------------------------------------
# T-04 and T-05 the other way: spelling the identity out
# ---------------------------------------------------------------------------


def _doble_argumento(argumento: mx.Expr) -> mx.Expr | None:
    """``2·x`` written as ``2*x`` → ``x``."""
    coeficiente, factores = _factores(argumento)
    if coeficiente != 2 or len(factores) != 1:
        return None
    return factores[0]


def _dos_angles(a: mx.Expr, b: mx.Expr) -> tuple[mx.Expr, mx.Expr]:
    return mx.Div(mx.Add(a, b), _TWO), mx.Div(mx.Sub(a, b), _TWO)


def _por_dos(primero: mx.Expr, segundo: mx.Expr) -> mx.Expr:
    """``2·primero·segundo``, written so that a factor of 1 does not show up."""
    if segundo == mx.ONE:
        return _escalar(primero, 2)
    return mx.Mul(_num(2), mx.Mul(primero, segundo))


def _r_suma_diferencia(e: mx.Expr) -> mx.Expr | None:
    """``sin(a±b)``, ``cos(a±b)``, ``tan(a±b)`` written out (T-04)."""
    if not (isinstance(e, mx.Call) and len(e.args) == 1):
        return None
    argumento = e.args[0]
    if not isinstance(argumento, (mx.Add, mx.Sub)):
        return None
    a, b = argumento.left, argumento.right
    diferencia = isinstance(argumento, mx.Sub)
    if e.name == "sin":
        # sin(a±b) = sin(a)·cos(b) ± cos(a)·sin(b)
        primero = mx.Mul(_fn("sin", a), _fn("cos", b))
        segundo = mx.Mul(_fn("cos", a), _fn("sin", b))
        return mx.Sub(primero, segundo) if diferencia else mx.Add(primero, segundo)
    if e.name == "cos":
        # cos(a±b) = cos(a)·cos(b) ∓ sin(a)·sin(b)
        primero = mx.Mul(_fn("cos", a), _fn("cos", b))
        segundo = mx.Mul(_fn("sin", a), _fn("sin", b))
        return mx.Add(primero, segundo) if diferencia else mx.Sub(primero, segundo)
    if e.name == "tan":
        # tan(a±b) = (tan(a) ± tan(b)) / (1 ∓ tan(a)·tan(b))
        numerador = mx.Sub(_fn("tan", a), _fn("tan", b)) if diferencia else \
            mx.Add(_fn("tan", a), _fn("tan", b))
        producto = mx.Mul(_fn("tan", a), _fn("tan", b))
        denominador = mx.Add(mx.ONE, producto) if diferencia else mx.Sub(mx.ONE, producto)
        return mx.Div(numerador, denominador)
    return None


def _r_doble_directo(e: mx.Expr) -> mx.Expr | None:
    """``sin(2x)``, ``cos(2x)``, ``tan(2x)`` written out (T-05)."""
    if not (isinstance(e, mx.Call) and len(e.args) == 1):
        return None
    x = _doble_argumento(e.args[0])
    if x is None:
        return None
    if e.name == "sin":
        return _por_dos(_fn("sin", x), _fn("cos", x))
    if e.name == "cos":
        return mx.Sub(mx.Pow(_fn("cos", x), _num(2)), mx.Pow(_fn("sin", x), _num(2)))
    if e.name == "tan":
        return mx.Div(_escalar(_fn("tan", x), 2),
                      mx.Sub(mx.ONE, mx.Pow(_fn("tan", x), _num(2))))
    return None


def _r_triple_directo(e: mx.Expr) -> mx.Expr | None:
    """``sin(3x)``, ``cos(3x)``, ``tan(3x)`` in powers (T-06, the other way)."""
    if not (isinstance(e, mx.Call) and len(e.args) == 1):
        return None
    x = _triple_argumento(e.args[0])
    if x is None:
        return None
    if e.name in {"sin", "cos"}:
        return _en_potencias(e.name, x, 3)
    if e.name == "tan":
        t = _fn("tan", x)
        numerador = mx.Sub(_escalar(t, 3), mx.Pow(t, _num(3)))
        denominador = mx.Sub(mx.ONE, _escalar(mx.Pow(t, _num(2)), 3))
        return mx.Div(numerador, denominador)
    return None


def _triple_argumento(argumento: mx.Expr) -> mx.Expr | None:
    coeficiente, factores = _factores(argumento)
    if coeficiente != 3 or len(factores) != 1:
        return None
    return factores[0]


def _producto(factores: list[mx.Expr]) -> mx.Expr:
    """``Mul`` is binary, so a list of factors is folded left-associatively."""
    if not factores:
        return mx.ONE
    out = factores[0]
    for f in factores[1:]:
        out = mx.Mul(out, f)
    return out


# --- exact integer polynomials, {exponente: coeficiente} ---------------------
#
# The multiple angles are built here rather than as nested calls, because the
# textbook form of ``cos(4x)`` is ``8·cos⁴(x) − 8·cos²(x) + 1`` and not a Chebyshev
# recurrence spelled out four levels deep. Every coefficient stays an exact
# rational, so nothing is rounded on the way (§5.1).


def _poly_suma(a: dict[int, Fraction], b: dict[int, Fraction]) -> dict[int, Fraction]:
    out = dict(a)
    for grado, coeficiente in b.items():
        out[grado] = out.get(grado, Fraction(0)) + coeficiente
        if out[grado] == 0:
            del out[grado]
    return out


def _poly_resta(a: dict[int, Fraction], b: dict[int, Fraction]) -> dict[int, Fraction]:
    return _poly_suma(a, {g: -c for g, c in b.items()})


def _poly_producto(a: dict[int, Fraction],
                   b: dict[int, Fraction]) -> dict[int, Fraction]:
    out: dict[int, Fraction] = {}
    for g1, c1 in a.items():
        for g2, c2 in b.items():
            out[g1 + g2] = out.get(g1 + g2, Fraction(0)) + c1 * c2
    return {g: c for g, c in out.items() if c != 0}


def _poly_potencia(a: dict[int, Fraction], n: int) -> dict[int, Fraction]:
    out = {0: Fraction(1)}
    for _ in range(n):
        out = _poly_producto(out, a)
    return out


def _chebyshev_polinomio(n: int) -> dict[int, Fraction]:
    """``T_n`` as a polynomial: ``T_{k+1} = 2·t·T_k − T_{k−1}``."""
    anterior, actual = {0: Fraction(1)}, {1: Fraction(1)}
    for _k in range(1, n):
        anterior, actual = actual, _poly_resta(
            _poly_producto({1: Fraction(2)}, actual), anterior)
    return actual


def _seno_polinomio(n: int) -> dict[int, Fraction] | None:
    """``sin(nx)`` in powers of ``sin(x)`` alone — only possible for odd ``n``.

    ``sin(nx) = Σ (−1)ʲ C(n,2j+1)·cos^(n−2j−1)(x)·sin^(2j+1)(x)``; for odd ``n``
    every cosine power is even, so ``cos²=1−sin²`` turns the whole thing into a
    polynomial in ``sin(x)``. For even ``n`` this returns ``None`` rather than
    inventing a form that does not exist.
    """
    if n % 2 == 0:
        return None
    total: dict[int, Fraction] = {}
    uno_menos_s2 = {0: Fraction(1), 2: Fraction(-1)}
    for j in range((n + 1) // 2):
        m = (n - 2 * j - 1) // 2
        coeficiente = Fraction(_binomial(n, 2 * j + 1) * (-1) ** j)
        termino = _poly_producto(_poly_potencia(uno_menos_s2, m),
                                 {2 * j + 1: coeficiente})
        total = _poly_suma(total, termino)
    return total


def _termino_escalar(base: mx.Expr, coeficiente: Fraction) -> mx.Expr:
    """``c·base``, with the sign outside so it prints ``-4·x³`` and not ``(-4)·x³``."""
    if coeficiente == 1:
        return base
    if coeficiente < 0:
        return mx.Neg(_termino_escalar(base, -coeficiente))
    return _producto([mx.Num(coeficiente), base])


def _desde_polinomio(polinomio: dict[int, Fraction], base: mx.Expr) -> mx.Expr:
    """Build ``3·base − 4·base³`` out of a coefficient dictionary."""
    partes = [_termino_escalar(_potencia(base, g), polinomio[g])
              for g in sorted(polinomio, reverse=True)]
    if not partes:
        return mx.ZERO
    total = partes[0]
    for parte in partes[1:]:
        total = (mx.Sub(total, parte.arg) if isinstance(parte, mx.Neg)
                 else mx.Add(total, parte))
    return total


def _en_potencias(nombre: str, x: mx.Expr, n: int) -> mx.Expr:
    """``sin(nx)`` / ``cos(nx)`` in powers of a *single* function where possible.

    ``cos(nx)`` is ``T_n(cos x)`` for every ``n``, and ``sin(nx)`` is a
    polynomial in ``sin(x)`` for odd ``n``. The cosine form is what makes the
    round trip with :func:`simplify` work: ``expand`` hands back
    ``4·cos³(x) − 3·cos(x)`` and ``simplify`` folds it into ``cos(3x)``.
    """
    if nombre == "cos":
        return _desde_polinomio(_chebyshev_polinomio(n), _fn("cos", x))
    if n % 2 == 1:
        polinomio = _seno_polinomio(n)
        if polinomio is not None:
            return _desde_polinomio(polinomio, _fn("sin", x))
    # even n: no single-function polynomial exists in sin, so the binomial form
    # stands: sin(nx) = Σ (−1)ʲ C(n,2j+1)·cos^(n−2j−1)(x)·sin^(2j+1)(x)
    seno, coseno = _fn("sin", x), _fn("cos", x)
    total: mx.Expr | None = None
    for j in range((n + 1) // 2):
        coeficiente = _binomial(n, 2 * j + 1) * (-1) ** j
        factores = [_potencia(coseno, n - 2 * j - 1), _potencia(seno, 2 * j + 1)]
        total = _suma(total, coeficiente, factores)
    return total if total is not None else mx.ZERO


def _suma(total: mx.Expr | None, coeficiente: int, factores: list[mx.Expr]) -> mx.Expr:
    """One term of a binomial sum, with a coefficient of ±1 and factors of 1 folded."""
    piezas = [f for f in factores if f != mx.ONE]
    if not piezas:
        piezas = [mx.ONE]
    termino = _termino_escalar(_producto(piezas), Fraction(coeficiente))
    if total is None:
        return termino
    return mx.Sub(total, termino.arg) if isinstance(termino, mx.Neg) \
        else mx.Add(total, termino)


def _potencia(base: mx.Expr, n: int) -> mx.Expr:
    """``base^n`` — a power, not ``n·base``: the two are easy to confuse here."""
    if n == 0:
        return mx.ONE
    if n == 1:
        return base
    return mx.Pow(base, _num(n))


def _binomial(n: int, k: int) -> int:
    if k < 0 or k > n:
        return 0
    return math.comb(n, k)


def _r_multiplo_directo(e: mx.Expr) -> mx.Expr | None:
    """``f(n·x)`` for ``n ≥ 4``, in the closed form T-06 asks for.

    ``n = 2`` and ``n = 3`` are left to the two dedicated rules above, which
    produce the textbook product and power forms (``cos²−sin²``,
    ``3·sin−4·sin³``); this one takes over from ``n = 4``, where no other rule
    applies and ``expand`` would otherwise do nothing at all.
    """
    if not (isinstance(e, mx.Call) and len(e.args) == 1):
        return None
    coeficiente, factores = _factores(e.args[0])
    if coeficiente < 4 or coeficiente.denominator != 1 or len(factores) != 1:
        return None
    if e.name not in {"sin", "cos"}:
        return None
    return _en_potencias(e.name, factores[0], int(coeficiente))


def _r_medio_angulo_directo(e: mx.Expr) -> mx.Expr | None:
    """``sin²(x/2)``, ``cos²(x/2)``, ``tan²(x/2)`` in full angles (T-07)."""
    if not (isinstance(e, mx.Pow) and e.exponent == _num(2)):
        return None
    nombre = None
    if _is_call(e.base, "sin"):
        nombre = "sin"
    elif _is_call(e.base, "cos"):
        nombre = "cos"
    elif _is_call(e.base, "tan"):
        nombre = "tan"
    if nombre is None:
        return None
    x = _medio_argumento(e.base.args[0])
    if x is None:
        return None
    coseno = _fn("cos", x)
    if nombre == "sin":
        return mx.Div(mx.Sub(mx.ONE, coseno), _TWO)
    if nombre == "cos":
        return mx.Div(mx.Add(mx.ONE, coseno), _TWO)
    return mx.Div(mx.Sub(mx.ONE, coseno), mx.Add(mx.ONE, coseno))


def _medio_argumento(argumento: mx.Expr) -> mx.Expr | None:
    """``x/2`` → ``x``."""
    if not (isinstance(argumento, mx.Div) and argumento.right == _TWO):
        return None
    return argumento.left


def _r_sustitucion_universal(e: mx.Expr) -> mx.Expr | None:
    """Write ``sin x``, ``cos x``, ``tan x`` through ``t = tan(x/2)`` (T-07).

    Rationalising with the universal substitution is what turns an integral of
    a rational-looking trigonometric expression into one of a rational function,
    and that is the whole point of it (§5.5b).

    ``tan(x/2)`` itself is left alone: it *is* the new variable ``t``, and
    substituting it again would make the expression grow without bound.
    """
    if not (isinstance(e, mx.Call) and len(e.args) == 1):
        return None
    if _medio_argumento(e.args[0]) is not None:
        return None
    t = _fn("tan", _medio_angulo(e.args[0]))
    if e.name == "sin":
        return mx.Div(_escalar(t, 2), mx.Add(mx.ONE, mx.Pow(t, _num(2))))
    if e.name == "cos":
        return mx.Div(mx.Sub(mx.ONE, mx.Pow(t, _num(2))),
                      mx.Add(mx.ONE, mx.Pow(t, _num(2))))
    if e.name == "tan":
        return mx.Div(_escalar(t, 2), mx.Sub(mx.ONE, mx.Pow(t, _num(2))))
    return None


def half_angle_forms(x: mx.Expr) -> tuple[tuple[mx.Expr, str], ...]:
    """Every half-angle form of T-07 with the interval it is valid on.

    The interval is not decoration: ``√(1−cos x) = √2·|sin(x/2)|``, so the
    square root only equals the half angle where ``x/2 ≥ 0``. Returning the
    hypothesis with the identity is what §5.7 asks for, and it is why the engine
    itself refuses to do this rewrite.
    """
    medio = _medio_angulo(x)
    coseno = _fn("cos", x)
    seno_cuadrado = mx.Div(mx.Sub(mx.ONE, coseno), _TWO)
    coseno_cuadrado = mx.Div(mx.Add(mx.ONE, coseno), _TWO)
    tangente_cuadrada = mx.Div(mx.Sub(mx.ONE, coseno), mx.Add(mx.ONE, coseno))
    return (
        (seno_cuadrado, "siempre: es un cuadrado, no hay signo que decidir"),
        (coseno_cuadrado, "siempre: es un cuadrado, no hay signo que decidir"),
        (tangente_cuadrada, "siempre que 1+cos(x) ≠ 0, es decir x ≠ (2k+1)·pi"),
        (mx.Root(2, seno_cuadrado), "x/2 ≥ 0: fuera de ahí es |sin(x/2)|"),
        (mx.Root(2, coseno_cuadrado), "x/2 ≤ 0: fuera de ahí es |cos(x/2)|"),
        (mx.Root(2, mx.Call("abs", (tangente_cuadrada,))),
         "siempre, pero como valor absoluto"),
        (_fn("sin", medio), "definición; sin él no hay nada que decidir"),
        (_fn("cos", medio), "definición; sin él no hay nada que decidir"),
    )


_REGLAS_EXPANDIR: tuple[tuple[str, str, object], ...] = (
    ("suma_diferencia",
     "sin(a±b), cos(a±b) y tan(a±b) se desarrollan porque la forma desarrollada "
     "es la que pide una integral o una demostración, no la que se simplifica",
     _r_suma_diferencia),
    ("doble_directo",
     "el ángulo doble se desarrolla a productos porque 2·sin(x)·cos(x) se "
     "integra y cos(2x) no: la forma útil depende del objetivo (§5.5b)",
     _r_doble_directo),
    ("triple_directo",
     "el ángulo triple se baja a potencias porque de ahí salen las series de "
     "T-19 y porque 3·sin − 4·sin³ es la forma que se integra por partes",
     _r_triple_directo),
    ("multiplo_directo",
     "a partir de 4·x el ángulo múltiple se baja al polinomio cerrado en una "
     "sola función, que es la única forma que se integra o se resuelve",
     _r_multiplo_directo),
    ("medio_angulo_directo",
     "sin²(x/2) y cos²(x/2) se suben a ángulo completo porque el cuadrado quita "
     "el problema de signo que el seno y el coseno por sí solos sí tienen (T-07)",
     _r_medio_angulo_directo),
)


def _r_hiberbolicas_suma_diferencia(e: mx.Expr) -> mx.Expr | None:
    """``sinh(a±b)``, ``cosh(a±b)``, ``tanh(a±b)`` written out (T-14)."""
    if not (isinstance(e, mx.Call) and len(e.args) == 1):
        return None
    argumento = e.args[0]
    if not isinstance(argumento, (mx.Add, mx.Sub)):
        return None
    a, b = argumento.left, argumento.right
    diferencia = isinstance(argumento, mx.Sub)
    if e.name == "sinh":
        # sinh(a±b) = sinh(a)·cosh(b) ± cosh(a)·sinh(b)
        primero = mx.Mul(_fn("sinh", a), _fn("cosh", b))
        segundo = mx.Mul(_fn("cosh", a), _fn("sinh", b))
        return mx.Sub(primero, segundo) if diferencia else mx.Add(primero, segundo)
    if e.name == "cosh":
        # cosh(a±b) = cosh(a)·cosh(b) ± sinh(a)·sinh(b), with the SAME sign
        primero = mx.Mul(_fn("cosh", a), _fn("cosh", b))
        segundo = mx.Mul(_fn("sinh", a), _fn("sinh", b))
        return mx.Sub(primero, segundo) if diferencia else mx.Add(primero, segundo)
    if e.name == "tanh":
        numerador = mx.Sub(_fn("tanh", a), _fn("tanh", b)) if diferencia else \
            mx.Add(_fn("tanh", a), _fn("tanh", b))
        producto = mx.Mul(_fn("tanh", a), _fn("tanh", b))
        denominador = mx.Sub(mx.ONE, producto) if diferencia else mx.Add(mx.ONE, producto)
        return mx.Div(numerador, denominador)
    return None


def _r_hiberbolicas_doble_directo(e: mx.Expr) -> mx.Expr | None:
    """``sinh(2x)``, ``cosh(2x)``, ``tanh(2x)`` written out (T-14)."""
    if not (isinstance(e, mx.Call) and len(e.args) == 1):
        return None
    x = _doble_argumento(e.args[0])
    if x is None:
        return None
    if e.name == "sinh":
        return _por_dos(_fn("sinh", x), _fn("cosh", x))
    if e.name == "cosh":
        return mx.Add(mx.Pow(_fn("cosh", x), _num(2)), mx.Pow(_fn("sinh", x), _num(2)))
    if e.name == "tanh":
        return mx.Div(_escalar(_fn("tanh", x), 2),
                      mx.Add(mx.ONE, mx.Pow(_fn("tanh", x), _num(2))))
    return None


def _r_hiberbolicas_exponencial(e: mx.Expr) -> mx.Expr | None:
    """``sinh(x)`` and ``cosh(x)`` through ``e`` (T-14, conexión exponencial).

    Its own objective: inside ``expand`` this rule would drag every hyperbolic
    angle into exponentials that then have to be simplified back, and the student
    asked for a sum formula and got a change of base instead.
    """
    if not (isinstance(e, mx.Call) and len(e.args) == 1):
        return None
    x = e.args[0]
    if e.name == "sinh":
        return mx.Div(mx.Sub(mx.Call("exp", (x,)), mx.Call("exp", (mx.Neg(x),))), _TWO)
    if e.name == "cosh":
        return mx.Div(mx.Add(mx.Call("exp", (x,)), mx.Call("exp", (mx.Neg(x),))), _TWO)
    return None


_REGLAS_HIPERBOLICAS: tuple[tuple[str, str, object], ...] = (
    ("hiperbolicas_suma_diferencia",
     "las sumas hiperbólicas se desarrollan con las mismas fórmulas que las "
     "circulares pero con el signo del segundo término cambiado (T-14)",
     _r_hiberbolicas_suma_diferencia),
    ("hiperbolicas_doble_directo",
     "el ángulo doble hiperbólico se desarrolla a productos porque es la forma "
     "que se integra: ∫sinh² se hace con cosh(2x) (§5.5b)",
     _r_hiberbolicas_doble_directo),
)


_REGLAS_EXPONENCIAL: tuple[tuple[str, str, object], ...] = (
    ("hiperbolicas_exponencial",
     "sinh y cosh son la diferencia y la suma de dos exponenciales: es lo que "
     "convierte una ecuación diferencial hiperbólica en una de primer orden",
     _r_hiberbolicas_exponencial),
)


#: ``t = tan(x/2)`` lives in its own objective and never shares one with the
#: identities. It is a change of variable (§5.6), not an identity, and mixing the
#: two is not a matter of taste: the substitution *creates* ``tan(x/2)`` and the
#: half-angle rule *consumes* ``tan(x/2)²``, so inside a single loop they feed
#: each other and the expression grows without bound.
_REGLAS_SUSTITUCION: tuple[tuple[str, str, object], ...] = (
    ("sustitucion_universal",
     "con t = tan(x/2) toda expresión trigonométrica se vuelve racional, y una "
     "integral racional se sabe hacer: ese es el motivo del cambio de variable",
     _r_sustitucion_universal),
)


# ---------------------------------------------------------------------------
# T-08 product to sum
# ---------------------------------------------------------------------------


def _r_producto_a_suma(e: mx.Expr) -> mx.Expr | None:
    if not isinstance(e, mx.Mul):
        return None
    coeficiente, factores = _factores(e)
    if coeficiente != 1 or len(factores) != 2:
        return None
    a, b = factores
    if not (isinstance(a, mx.Call) and isinstance(b, mx.Call)):
        return None
    if a.name not in {"sin", "cos"} or b.name not in {"sin", "cos"}:
        return None
    u, v = a.args[0], b.args[0]
    if (a.name, b.name) == ("sin", "sin"):
        # sin(u)·sin(v) = (cos(u-v) - cos(u+v)) / 2
        numerador = mx.Sub(_fn("cos", mx.Sub(u, v)), _fn("cos", mx.Add(u, v)))
    elif (a.name, b.name) == ("cos", "cos"):
        # cos(u)·cos(v) = (cos(u-v) + cos(u+v)) / 2
        numerador = mx.Add(_fn("cos", mx.Sub(u, v)), _fn("cos", mx.Add(u, v)))
    elif a.name == "sin":  # sin(u)·cos(v) = (sin(u+v) + sin(u-v)) / 2
        numerador = mx.Add(_fn("sin", mx.Add(u, v)), _fn("sin", mx.Sub(u, v)))
    else:  # cos(u)·sin(v) = (sin(u+v) - sin(u-v)) / 2
        numerador = mx.Sub(_fn("sin", mx.Add(u, v)), _fn("sin", mx.Sub(u, v)))
    return mx.Div(numerador, _TWO)


_REGLAS_PRODUCTO: tuple[tuple[str, str, object], ...] = (
    ("producto_a_suma",
     "sin·sin, cos·cos y sin·cos se escriben como suma o resta de senos o "
     "cosenos: es la forma que suma integrales y que deja cancelar (§5.5b)",
     _r_producto_a_suma),
)


# ---------------------------------------------------------------------------
# T-09 sum to product
# ---------------------------------------------------------------------------


def _r_suma_a_producto(e: mx.Expr) -> mx.Expr | None:
    if not isinstance(e, (mx.Add, mx.Sub)):
        return None
    izquierda, derecha = e.left, e.right
    suma = isinstance(e, mx.Add)
    a, b = _arg(izquierda, "sin"), _arg(derecha, "sin")
    if a is not None and b is not None:
        semisuma, semiresta = _dos_angles(a, b)
        if suma:  # sin(u)+sin(v) = 2·sin((u+v)/2)·cos((u-v)/2)
            return _por_dos(_fn("sin", semisuma), _fn("cos", semiresta))
        return _por_dos(_fn("cos", semisuma), _fn("sin", semiresta))
    a, b = _arg(izquierda, "cos"), _arg(derecha, "cos")
    if a is not None and b is not None:
        semisuma, semiresta = _dos_angles(a, b)
        if suma:  # cos(u)+cos(v) = 2·cos((u+v)/2)·cos((u-v)/2)
            return _por_dos(_fn("cos", semisuma), _fn("cos", semiresta))
        # cos(u)-cos(v) = -2·sin((u+v)/2)·sin((u-v)/2)
        return mx.Neg(_por_dos(_fn("sin", semisuma), _fn("sin", semiresta)))
    return None


_REGLAS_SUMA: tuple[tuple[str, str, object], ...] = (
    ("suma_a_producto",
     "sin±sin y cos±cos se factorizan en un producto de la semisuma y la "
     "semiresta, que es la forma en que una integral por partes avanza",
     _r_suma_a_producto),
)


# ---------------------------------------------------------------------------
# T-10 reduction of powers
# ---------------------------------------------------------------------------


def _medio_angulo_cuadrado(nombre: str, x: mx.Expr) -> mx.Expr:
    """``sin²x`` and ``cos²x`` in terms of ``cos(2x)``."""
    coseno = _fn("cos", _doble(x))
    if nombre == "sin":
        return mx.Div(mx.Sub(mx.ONE, coseno), _TWO)
    return mx.Div(mx.Add(mx.ONE, coseno), _TWO)


def _potencia_reducida(nombre: str, x: mx.Expr, n: int) -> mx.Expr:
    """``f(x)^n`` with every power of ``f`` below one, in factorised form."""
    if n == 1:
        return _fn(nombre, x)
    if n == 2:
        return _medio_angulo_cuadrado(nombre, x)
    if n % 2 == 1:
        return mx.Mul(_fn(nombre, x), _potencia_reducida(nombre, x, n - 1))
    return mx.Mul(_potencia_reducida(nombre, x, n // 2),
                  _potencia_reducida(nombre, x, n // 2))


def _r_reducir_potencias(e: mx.Expr) -> mx.Expr | None:
    if not isinstance(e, mx.Pow):
        return None
    n = _entero(e.exponent)
    if n is None or n < 2:
        return None
    u, nombre = _arg(e.base, "sin"), "sin"
    if u is None:
        u, nombre = _arg(e.base, "cos"), "cos"
    return None if u is None else _potencia_reducida(nombre, u, n)


_REGLAS_POTENCIAS: tuple[tuple[str, str, object], ...] = (
    ("reduccion_potencias",
     "sin², cos² y sus potencias superiores se bajan a cos(2x): es la única "
     "forma en que una potencia par se integra sin factorizar primero (§5.5b)",
     _r_reducir_potencias),
)


# ---------------------------------------------------------------------------
# the objective loop
# ---------------------------------------------------------------------------


def _coste(e: mx.Expr) -> tuple[int, int]:
    """``(nodos, longitud del texto canónico)``: a well-founded size measure."""
    nodos, pila = 0, [e]
    while pila:
        actual = pila.pop()
        nodos += 1
        if isinstance(actual, mx.Neg):
            pila.append(actual.arg)
        elif isinstance(actual, mx.Pow):
            pila.extend((actual.base, actual.exponent))
        elif isinstance(actual, mx.Call):
            pila.extend(actual.args)
        elif isinstance(actual, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
            pila.extend((actual.left, actual.right))
        elif isinstance(actual, mx.Root):
            pila.append(actual.radicand)
    return nodos, len(mx.text(e))


def _mejor_rewrite(e: mx.Expr, registro, reducir: bool
                   ) -> tuple[mx.Expr | None, str]:
    """The best rewrite ``e`` admits, strictly in ``registro``'s direction."""
    mejor, familia, coste = None, "", None
    for nombre, _por_que, aplicar in registro:
        candidato = aplicar(e)
        if candidato is None or candidato == e:
            continue
        nuevo = _coste(candidato)
        if coste is None or ((nuevo < coste) if reducir else (nuevo > coste)):
            mejor, familia, coste = candidato, nombre, nuevo
    return mejor, familia


def _visita(e: mx.Expr, registro, reducir: bool, pasos: list[str],
            profundidad: int = 0) -> mx.Expr:
    """Reduce bottom-up: the children are canonicalised and reduced first.

    Working upwards is what lets ``x·(sin(x)² + cos(x)²)`` reach ``x``: the
    Pythagorean rule matches at the inner sum, not at the outer product.
    """
    if profundidad > MAX_REWRITE_DEPTH:
        raise mx.invalid(
            "EXPRESSION_LIMIT",
            f"expresión de más de {MAX_REWRITE_DEPTH} niveles: el motor no la "
            "recorre entera y no va a adivinar el resultado")

    def hijo(child: mx.Expr) -> mx.Expr:
        return _visita(child, registro, reducir, pasos, profundidad + 1)

    actual = _reconstruir(e, hijo)
    candidato, familia = _mejor_rewrite(actual, registro, reducir)
    if candidato is None:
        return actual
    pasos.append(familia)
    return candidato


def _bucle(e: mx.Expr, registro, *, reducir: bool,
           max_passes: int) -> tuple[mx.Expr, list[str]]:
    pasos: list[str] = []
    actual = e
    for _pase in range(max_passes):
        siguiente = _visita(actual, registro, reducir, pasos)
        if siguiente == actual:
            break
        actual = siguiente
    return actual, pasos


@dataclass(frozen=True)
class Simplificacion:
    """A reduced expression and the families that fired (T-22 trazabilidad)."""

    expresion: mx.Expr
    familias: tuple[str, ...]


def simplify_ex(expr: mx.Expr, *, max_passes: int = MAX_PASSES) -> Simplificacion:
    """:func:`simplify` plus the families it used, for the step log (§5.2)."""
    resultado, pasos = _bucle(expr, _REGLAS, reducir=True, max_passes=max_passes)
    return Simplificacion(resultado, tuple(dict.fromkeys(pasos)))


def simplify(expr: mx.Expr, *, max_passes: int = MAX_PASSES) -> mx.Expr:
    """Reduce an expression using only the exact rules that make it cheaper."""
    return simplify_ex(expr, max_passes=max_passes).expresion


def expand(expr: mx.Expr, *, max_passes: int = MAX_PASSES) -> mx.Expr:
    """Write the sum/difference and double-angle identities out (T-04, T-05)."""
    return _bucle(expr, _REGLAS_EXPANDIR, reducir=False, max_passes=max_passes)[0]


def product_to_sum(expr: mx.Expr, *, max_passes: int = MAX_PASSES) -> mx.Expr:
    """``sin·sin``, ``cos·cos`` and ``sin·cos`` as sums (T-08)."""
    return _bucle(expr, _REGLAS_PRODUCTO, reducir=False, max_passes=max_passes)[0]


def sum_to_product(expr: mx.Expr, *, max_passes: int = MAX_PASSES) -> mx.Expr:
    """``sin±sin`` and ``cos±cos`` as products (T-09)."""
    return _bucle(expr, _REGLAS_SUMA, reducir=False, max_passes=max_passes)[0]


def reduce_powers(expr: mx.Expr, *, max_passes: int = MAX_PASSES) -> mx.Expr:
    """Reduce the powers of ``sin`` and ``cos`` to first powers (T-10)."""
    return _bucle(expr, _REGLAS_POTENCIAS, reducir=False, max_passes=max_passes)[0]


def rationalize(expr: mx.Expr, *, max_passes: int = MAX_PASSES) -> mx.Expr:
    """Write every angle through ``t = tan(x/2)``, turning the expression rational.

    A separate objective on purpose — see :data:`_REGLAS_SUSTITUCION`. The result
    is only equal to the original where ``cos(x/2) ≠ 0``, and :func:`sustitucion_domain`
    says so.
    """
    return _bucle(expr, _REGLAS_SUSTITUCION, reducir=False, max_passes=max_passes)[0]


def half_angle_substitution(x: mx.Expr) -> mx.Expr:
    """``t = sin(x)/(1+cos(x)) = (1−cos(x))/sin(x)``, the *inverse* of the change.

    T-07 asks for the substitution and its rationalisation. This is the way back:
    it is what turns a rational function of ``t`` into the original trigonometric
    expression, and it is valid where ``sin(x) ≠ 0``.
    """
    seno = _fn("sin", x)
    coseno = _fn("cos", x)
    return mx.Div(seno, mx.Add(mx.ONE, coseno))


def sustitucion_domain() -> str:
    """The hypothesis of ``t = tan(x/2)``, which T-07 and §5.7 both require."""
    return ("cos(x/2) ≠ 0, es decir x ≠ (2k+1)·pi; fuera de ese conjunto la "
            "sustitución no está definida aunque la expresión original sí lo esté")


def chebyshev(n: int, t: mx.Expr) -> mx.Expr:
    """``T_n(t)``, the Chebyshev polynomial of the first kind (T-06).

    ``cos(n·arccos(t)) = T_n(t)``. It is built with the three-term recurrence
    ``T_{n+1} = 2·t·T_n − T_{n−1}`` rather than from a closed formula, because
    the recurrence is the one that stays exact and cheap for large ``n``.
    """
    if n < 0:
        raise ValueError("el índice de Chebyshev no puede ser negativo")
    anterior, actual = mx.ONE, t
    for _k in range(1, n):
        anterior, actual = actual, mx.Sub(_escalar(mx.Mul(t, actual), 2), anterior)
    return actual


def multiple_angle(nombre: str, x: mx.Expr, n: int, *,
                   forma: str = "potencias") -> mx.Expr:
    """``sin(n·x)``, ``cos(n·x)`` or ``tan(n·x)`` in exact closed form (T-06).

    Three forms, because T-06 asks for them all and because the useful one is
    decided by the next step and not here (§5.5b):

    - ``"potencias"`` — the binomial expansion in ``sin(x)`` and ``cos(x)``,
      which is what ``expand`` applies for ``n = 3``;
    - ``"dobles"`` — the recursion ``2(n·x) = n·x + n·x``, the cheap way to any
      power of two;
    - ``"chebyshev"`` — only for the cosine, ``T_n(cos(x))``, which is the form
      that expands in *one* variable.
    """
    if n < 1:
        raise ValueError("el múltiplo tiene que ser un entero positivo")
    if nombre not in {"sin", "cos", "tan"}:
        raise ValueError(f"«{nombre}» no tiene ángulo múltiple")
    if forma == "potencias":
        return _fn(nombre, mx.Mul(_num(n), x)) if nombre == "tan" \
            else _en_potencias(nombre, x, n)
    if forma == "dobles":
        return _fn(nombre, mx.Mul(_num(n), x))
    if forma == "chebyshev":
        if nombre != "cos":
            raise ValueError("la forma de Chebyshev solo existe para el coseno")
        return chebyshev(n, _fn("cos", x))
    raise ValueError(f"forma de ángulo múltiple desconocida: {forma}")


def multiple_angle_forms(nombre: str, x: mx.Expr, n: int) -> tuple[mx.Expr, ...]:
    """Every exact form of the multiple angle, offered rather than chosen."""
    principal = _fn(nombre, mx.Mul(_num(n), x))
    if nombre == "cos":
        return (principal, _en_potencias("cos", x, n), chebyshev(n, _fn("cos", x)))
    if nombre == "sin":
        return (principal, _en_potencias("sin", x, n))
    return (principal,)


def double_angle_forms(nombre: str, x: mx.Expr) -> tuple[mx.Expr, ...]:
    """The main forms of the double angle of T-05, all of them exact.

    They are returned rather than chosen: which one helps depends on whether the
    next step is a derivative, an integral or a proof, and that is not the
    engine's decision to make (§5.5b).
    """
    if nombre not in {"sin", "cos", "tan"}:
        raise ValueError(f"«{nombre}» no tiene ángulo doble")
    if nombre == "sin":
        return (_fn("sin", _doble(x)), _por_dos(_fn("sin", x), _fn("cos", x)))
    if nombre == "tan":
        return (_fn("tan", _doble(x)),
                mx.Div(_escalar(_fn("tan", x), 2),
                       mx.Sub(mx.ONE, mx.Pow(_fn("tan", x), _num(2)))))
    return (
        _fn("cos", _doble(x)),
        mx.Sub(mx.Pow(_fn("cos", x), _num(2)), mx.Pow(_fn("sin", x), _num(2))),
        mx.Sub(mx.ONE, _escalar(mx.Pow(_fn("sin", x), _num(2)), 2)),
    )


# ---------------------------------------------------------------------------
# inventory (§5.5b: every family has to justify itself, in writing)
# ---------------------------------------------------------------------------

#: objective name → its registry. ``simplificar`` is what the calculator calls.
OBJETIVOS: dict[str, tuple[tuple[str, str, object], ...]] = {
    "simplificar": _REGLAS,
    "expandir": _REGLAS_EXPANDIR,
    "producto_a_suma": _REGLAS_PRODUCTO,
    "suma_a_producto": _REGLAS_SUMA,
    "potencias": _REGLAS_POTENCIAS,
    "sustitucion_universal": _REGLAS_SUSTITUCION,
    "hiperbolicas": _REGLAS_HIPERBOLICAS,
    "exponencial": _REGLAS_EXPONENCIAL,
}


def simplify_hyperbolic(expr: mx.Expr, *, max_passes: int = MAX_PASSES) -> mx.Expr:
    """The sum, difference and double angle of the hyperbolic functions (T-14)."""
    return _bucle(expr, _REGLAS_HIPERBOLICAS, reducir=False,
                  max_passes=max_passes)[0]


def to_exponential(expr: mx.Expr, *, max_passes: int = MAX_PASSES) -> mx.Expr:
    """``sinh`` and ``cosh`` written with ``e`` (T-14, conexión exponencial)."""
    return _bucle(expr, _REGLAS_EXPONENCIAL, reducir=False, max_passes=max_passes)[0]


def identities() -> tuple[str, ...]:
    """Every trigonometric family that really has a rule behind it.

    It is derived from the registries, never written by hand, so a family cannot
    be advertised here while its rules are missing.
    """
    return tuple(nombre for nombre, _, _ in _NORMALIZACIONES) + tuple(
        nombre for registro in OBJETIVOS.values() for nombre, _, _ in registro)


def familias(objetivo: str) -> tuple[str, ...]:
    """The families one objective uses, for the step log."""
    return tuple(nombre for nombre, _, _ in OBJETIVOS[objetivo])


def descripcion(nombre: str) -> str:
    """The «por qué este método» of a family, as §5.5b requires it written down."""
    for registro in (_NORMALIZACIONES, *OBJETIVOS.values()):
        for familia, por_que, _ in registro:
            if familia == nombre:
                return por_que
    raise KeyError(f"familia trigonométrica desconocida: {nombre}")


def regla(nombre: str):
    """The callable behind a family, so an inventory entry can be audited."""
    for registro in (_NORMALIZACIONES, *OBJETIVOS.values()):
        for familia, _por_que, aplicar in registro:
            if familia == nombre:
                return aplicar
    raise KeyError(f"familia trigonométrica desconocida: {nombre}")
