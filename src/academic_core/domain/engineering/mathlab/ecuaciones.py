# SPDX-License-Identifier: MIT
"""MATH_LAB T-12: solving trigonometric equations.

What this solves, and what it refuses
-------------------------------------

An equation is moved to one side (``f(x) − g(x) = 0``) and matched structurally.
The cases are the ones a technical course actually asks for:

- ``sin(u) = c``, ``cos(u) = c``, ``tan(u) = c``;
- ``a·sin(u) + b·cos(u) = c``, which is brought to a single sine by a phase
  shift — §5.5b, because it is the only form that integrates as well;
- a polynomial in ``sin(u)``, ``cos(u)`` or ``tan(u)``, whose exact roots are
  found first and then fed back into the cases above.

Anything else is **refused with a reason in Spanish** rather than guessed. That
is §5.4, and for this family it is not politeness: a solver that answers
``x = 0`` for something it does not understand is worse than one that says no.

Spurious solutions
------------------

Every family is checked by substitution into the *original* equation, which is
what T-12 asks for and the only thing that catches a root introduced by a
transformation. The rejected candidates are reported by name, not dropped: a
spurious solution that vanishes without explanation is the thing that teaches a
student to distrust the whole method.

Exactness
---------

``arcsin(1/3)`` is an exact real number, so ``x = arcsin(1/3) + 2k·pi`` is an
exact answer even though it is not a multiple of ``pi``. Only the notable angles
are rewritten in multiples of ``pi``. Where a polynomial has no exact root the
refusal says so and offers the numeric value with its error bound (§5.4).
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import dominio as D
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import poly as P
from academic_core.domain.engineering.mathlab import trig
from academic_core.errors import UnsupportedError

#: how many members of a family are substituted back to check it
MIEMBROS_COMPROBADOS = 5

#: how close to zero a substituted value has to land, relative to its size
TOLERANCIA = 1e-9


def sin_refuso(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"NO_RULE: {mensaje}")


# ---------------------------------------------------------------------------
# what a solution looks like
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Familia:
    """One family of solutions: ``variable = base + paso·k``, ``k ∈ ℤ``."""

    base: mx.Expr
    paso: mx.Expr
    metodo: str = ""
    hipotesis: str = ""

    def texto(self, var: str) -> str:
        paso = "" if mx.text(self.paso) == "1" else f" + {mx.pretty(self.paso)}·k"
        return f"{var} = {mx.pretty(self.base)}{paso},  k ∈ ℤ"

    def miembro(self, k: int, var: str) -> mx.Expr:
        return mx.Add(self.base, mx.Mul(mx.Num(Fraction(k)), self.paso))


@dataclass(frozen=True)
class Resolucion:
    """The families found, how, and what was thrown away on the way."""

    familias: tuple[Familia, ...]
    metodo: str = ""
    hipotesis: tuple[str, ...] = ()
    espurias: tuple[str, ...] = ()
    refusos: tuple[str, ...] = ()

    def texto(self, var: str) -> str:
        if self.refusos:
            return "no se resuelve todavía: " + self.refusos[0]
        if not self.familias:
            return "no hay soluciones"
        return "   ó   ".join(f.texto(var) for f in self.familias)

    @property
    def vacia(self) -> bool:
        return not self.familias

    @property
    def sin_respuesta(self) -> bool:
        """True when the engine declined, as opposed to having found nothing."""
        return bool(self.refusos) and not self.familias


# ---------------------------------------------------------------------------
# exact angles
# ---------------------------------------------------------------------------

def _indice_notable(funcion: str, valor: mx.Expr) -> Fraction | None:
    """``k`` such that ``funcion(k*pi) == valor``, or ``None``.

    Read out of the same table the simplifier uses, so the solver and the
    simplifier cannot disagree about what ``sin(pi/6)`` is.

    Two comparisons, in that order. Exact first, through ``exact_value``, which
    settles every rational. Then, for an exact **surd** such as ``sqrt(2)/2``, a
    numeric one — but only ever against a value built from roots, never a
    decimal. That restriction is the point: it is what turns
    ``arcsin(sqrt(2)/2)`` into ``pi/4`` exactly, without ever letting the engine
    decide that some decimal is close enough to a notable angle.
    """
    for k, valores in trig._NOTABLES.items():
        exacto = valores.get(funcion)
        if exacto is None:
            continue
        a, b = mx.exact_value(exacto), mx.exact_value(valor)
        # both sides must be *known*: two Nones compare equal, and that made every
        # surd look like the first notable angle in the table
        if a is not None and b is not None and a == b:
            return k
    if not _es_exacta(valor):
        return None
    objetivo = mx.evaluate(valor)
    for k, valores in trig._NOTABLES.items():
        exacto = valores.get(funcion)
        if exacto is None or not _es_exacta(exacto):
            continue
        lado = mx.evaluate(exacto)
        if (lado is not None and objetivo is not None
                and abs(lado.imag) < 1e-12 and abs(objetivo.imag) < 1e-12
                and abs(lado.real - objetivo.real) < 1e-12):
            return k
    return None


def _es_negativo(e: mx.Expr) -> bool:
    valor = mx.evaluate(e)
    return valor is not None and valor.imag == 0 and valor.real < 0


def _es_exacta(e: mx.Expr) -> bool:
    """True when ``e`` is an exact surd: numbers and roots only, never decimals."""
    if isinstance(e, mx.Num):
        return True
    if isinstance(e, mx.Root):
        return _es_exacta(e.radicand)
    if isinstance(e, mx.Neg):
        return _es_exacta(e.arg)
    if isinstance(e, mx.Pow):
        return _es_exacta(e.base)
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return _es_exacta(e.left) and _es_exacta(e.right)
    if isinstance(e, mx.Const):
        return e.name == "pi"
    if isinstance(e, mx.Call):
        return e.name == "sqrt" and len(e.args) == 1 and _es_exacta(e.args[0])
    return False


#: which inverse each family needs, by the name the expression uses
_ARC = {"sin": "asin", "cos": "acos", "tan": "atan"}


def _inversa(funcion: str, valor) -> tuple[mx.Expr, bool, str]:
    """``arcsin`` / ``arccos`` / ``arctan`` of an exact value.

    ``(angulo, es_multiplo_de_pi, nota)``. A value that is not notable is *not* a
    problem: ``arcsin(1/3)`` and ``arcsin(1/sqrt(2))`` are exact real numbers, so
    the answer stays exact and is written symbolically instead of as a decimal.
    """
    expresion = valor if isinstance(valor, mx.Expr) else mx.Num(valor)
    k = _indice_notable(funcion, expresion)
    if k is not None:
        return D.punto_pi(k).expr(), True, ""
    # the table only holds angles in [0, pi], where every sine is >= 0; a negative
    # value is the same angle reflected, so it is looked up by its modulus
    if _es_negativo(expresion):
        k_negativo = _indice_notable(funcion, mx.Neg(expresion))
        if k_negativo is not None:
            return mx.Neg(D.punto_pi(k_negativo).expr()), True, ""
    if mx.exact_value(expresion) is not None:
        nota = (f"{funcion}({mx.text(expresion)}) no es un ángulo notable: se deja "
                "como expresión exacta y no como decimal (\u00a75.4)")
    else:
        nota = (f"{funcion}({mx.text(expresion)}) no es racional, pero su inversa "
                "sigue siendo exacta: por eso la solución es exacta aunque no "
                "sea múltiplo de pi")
    return mx.Call(_ARC[funcion], (expresion,)), False, nota


def _arcoseno_exacto(c) -> tuple[mx.Expr, bool]:
    angulo, multiplo, _nota = _inversa("sin", c)
    return angulo, multiplo


def _arccoseno_exacto(c) -> tuple[mx.Expr, bool]:
    angulo, multiplo, _nota = _inversa("cos", c)
    return angulo, multiplo


def _arctangente_exacto(c) -> tuple[mx.Expr, bool]:
    angulo, multiplo, _nota = _inversa("tan", c)
    return angulo, multiplo


def _dos_pi() -> mx.Expr:
    return mx.Mul(mx.Num(Fraction(2)), mx.PI)


def _pi() -> mx.Expr:
    return mx.PI


# ---------------------------------------------------------------------------
# the solver
# ---------------------------------------------------------------------------


def separar(ecuacion: str) -> tuple[str, str]:
    """``"sin(x) = 1/2"`` → ``("sin(x)", "1/2")``."""
    if "=" not in ecuacion:
        raise sin_refuso(
            "falta el signo «=»: la ecuación tiene que venir con los dos lados, "
            "por ejemplo «sin(x) = 1/2»")
    izquierda, _, derecha = ecuacion.partition("=")
    if not izquierda.strip() or not derecha.strip():
        raise sin_refuso("uno de los dos lados de la ecuación está vacío")
    return izquierda.strip(), derecha.strip()


def resolver(ecuacion: str, var: str = "x") -> Resolucion:
    """Solve a trigonometric equation and return every solution family."""
    izquierda, derecha = separar(ecuacion)
    try:
        a, b = mx.parse(izquierda), mx.parse(derecha)
    except Exception as exc:  # a parse error already says where, in Spanish
        raise sin_refuso(f"no se pudo interpretar la ecuación: {exc}") from exc
    if sorted(mx.variables(a) | mx.variables(b)) not in ([], [var]):
        otras = sorted((mx.variables(a) | mx.variables(b)) - {var})
        raise sin_refuso(
            f"la ecuación tiene más de una incógnita ({', '.join(otras)}): "
            f"ahora mismo solo se resuelve con una, la «{var}»")
    diferencia = mx.Sub(a, b)
    familias, hipotesis, espurias = _casos(diferencia, var)
    refusos = tuple(h for h in hipotesis if MOTIVO_SIN_CASO in h)
    return Resolucion(tuple(familias), hipotesis=tuple(h for h in hipotesis
                                                       if h not in refusos),
                      espurias=tuple(espurias), refusos=refusos)


def _casos(f: mx.Expr, var: str):
    """The case analysis, in the order that avoids dividing by something."""
    directo = _caso_directo(f, var)
    if directo is not None:
        return directo
    fase = _caso_fase(f, var)
    if fase is not None:
        return fase
    racional = _caso_racional(f, var)
    if racional is not None:
        return racional
    polinomio = _caso_polinomio(f, var)
    if polinomio is not None:
        return polinomio
    # No case matched. That is *not* the same as «there is no solution»: it is
    # «this engine does not solve this», and the difference is the whole point of
    # §5.4. Saying «no solutions» here would be a false answer presented with
    # the same confidence as a solved one.
    return [], [MOTIVO_SIN_CASO], []


#: the refusal that replaces a wrong «no hay soluciones»
MOTIVO_SIN_CASO = (
    "ninguno de los casos de T-12 encaja aquí (sin/cos/tangente igual a una "
    "constante, a·sin+b·cos, o un polinomio en una de las tres). Eso NO quiere "
    "decir que no haya soluciones: quiere decir que este motor todavía no lo "
    "resuelve, y no va a devolver una respuesta inventada (§5.4)")


# --- case 1: sin(u) = c, cos(u) = c, tan(u) = c -----------------------------


def _caso_directo(f: mx.Expr, var: str):
    """``sin(u) − c``, ``cos(u) − c`` and ``tan(u) − c``, with ``u`` affine in x."""
    from academic_core.domain.engineering.mathlab.trig import _factores

    # «f(x) = 0» arrives as «f(x) - 0», and that trailing zero hides the single
    # subtraction the whole case rests on. It is unwrapped here rather than at the
    # call site: stripping it outside would delete the very Sub this reads.
    while isinstance(f, mx.Sub) and f.right == mx.ZERO and isinstance(f.left, mx.Sub):
        f = f.left
    if not isinstance(f, mx.Sub):
        return None
    cociente, resto = f.left, f.right
    # the right-hand side may be a rational *or* an exact surd: sin(x) = sqrt(2)/2
    # is a perfectly ordinary exercise, and refusing it because the value is
    # irrational would be refusing to be exact
    cte = _valor_exacto(resto)
    if cte is None:
        cociente, cte = resto, _valor_exacto(cociente)
    if cte is None:
        return None
    nombre, u = _una_trig(cociente)
    if u is None:
        return None
    if nombre == "sin":
        familias, hipotesis = _soluciones_seno(cte, u, var)
    elif nombre == "cos":
        familias, hipotesis = _soluciones_coseno(cte, u, var)
    else:
        familias, hipotesis = _soluciones_tangente(cte, u, var)
    if not familias:
        return None
    espurias = _comprobar(familias, f, var)
    return familias, hipotesis, espurias


def _valor_exacto(e: mx.Expr):
    """The exact value of ``e``: a ``Fraction``, an exact surd as an expression,
    or ``None`` when it is neither."""
    racional = _constante(e)
    if racional is not None:
        return racional
    return e if _es_exacta(e) else None


def _constante(e: mx.Expr) -> Fraction | None:
    """The exact rational value of ``e``, or ``None`` when it is not one.

    ``mx.exact_value`` is the authority on what is exactly a rational, so the
    solver and the simplifier cannot disagree about ``1/2`` or about ``pi``.
    """
    valor = mx.exact_value(e)
    return valor if valor is not None else None


def _una_trig(e: mx.Expr) -> tuple[str, mx.Expr] | tuple[None, None]:
    if isinstance(e, mx.Call) and e.name in {"sin", "cos", "tan"} and len(e.args) == 1:
        return e.name, e.args[0]
    return None, None


def _invertir(u: mx.Expr, base: mx.Expr, paso: mx.Expr, var: str
              ) -> tuple[mx.Expr, mx.Expr, str] | None:
    """Turn ``u = base + paso·k`` into ``x = ...``, when ``u`` is affine in x.

    ``u = a·x + b`` → ``x = (base − b)/a + (paso/a)·k``. When ``u`` is anything
    else the inversion is simply not available, and that is said instead of
    approximated.
    """
    a, b = _afine(u, var)
    if a is None or a == 0:
        return None
    nuevo_base = _simplifica_base(mx.Sub(base, b) if mx.text(b) != "0" else base)
    if a != 1:
        nuevo_base = _divide_por_constante(nuevo_base, a)
    nuevo_paso = paso if a == 1 else _divide_por_constante(paso, a)
    return _simplifica_base(nuevo_base), _simplifica_paso(nuevo_paso), ""


def _divide_por_constante(e: mx.Expr, a: Fraction) -> mx.Expr:
    """``2·pi`` over 2 as ``pi``, and ``-pi/2`` over 2 as ``-pi/4``.

    Folding the coefficient instead of writing a quotient is the difference
    between an answer a student recognises and one they have to re-read, and it
    is also what keeps ``1/2·(-1/2·pi)`` from ever appearing.
    """
    if isinstance(e, mx.Neg):
        return mx.Neg(_divide_por_constante(e.arg, a))
    if isinstance(e, mx.Div) and isinstance(e.right, mx.Num) and e.right.value != 0:
        acumulado = e.right.value * a
        if acumulado.denominator == 1 and acumulado != 0:
            return _divide_por_constante(e.left, acumulado)
    # sqrt(m)/k is sqrt(m/k²): writing it as a quotient leaves sqrt(12)/2 where
    # the student expects sqrt(3)
    if isinstance(e, mx.Div) and isinstance(e.left, mx.Root) \
            and e.left.degree == 2 and isinstance(e.right, mx.Num):
        dentro = mx.exact_value(e.left.radicand)
        if dentro is not None and e.right.value != 0:
            nuevo = Fraction(dentro) / (e.right.value ** 2)
            if nuevo.denominator == 1 and nuevo >= 0:
                return mx.Root(2, mx.Num(nuevo))
    coeficiente, factores = trig._factores(e)
    nuevo = coeficiente / a if a != 0 else coeficiente
    if factores:
        return trig._desde_factores(nuevo, factores)
    return mx.Div(e, mx.Num(a))


def _simplifica_base(e: mx.Expr) -> mx.Expr:
    """``pi − 0·pi`` → ``pi`` and ``pi − pi/6`` → ``5·pi/6``: the answer must read well."""
    # Recurse into children first. «pi - 0*pi - pi/4» only folds once its own
    # children have folded, and that is not obvious until it has happened once.
    if isinstance(e, mx.Sub):
        e = mx.Sub(_simplifica_base(e.left), _simplifica_base(e.right))
    elif isinstance(e, mx.Neg):
        e = mx.Neg(_simplifica_base(e.arg))
    coeficiente, factores = trig._factores(e)
    if coeficiente == 0:
        return mx.ZERO
    if isinstance(e, mx.Sub):
        izquierda, derecha = e.left, e.right
        # the sign is read through _terminos, not _factores: a negative angle is
        # written «Neg(...)», and _factores does not look inside one, so
        # «pi - -pi/4» came back unfolded and the chart lost a critical point
        t1, t2 = trig._terminos(izquierda), trig._terminos(derecha)
        if len(t1) == 1 and len(t2) == 1:
            s1, n1 = t1[0]
            s2, n2 = t2[0]
            c1, f1 = trig._factores(n1)
            c2, f2 = trig._factores(n2)
            if f1 == [mx.Const("pi")] and f2 == [mx.Const("pi")]:
                total = s1 * c1 - s2 * c2
                return mx.PI if total == 1 else _medio_pi(total)
        if derecha == mx.ZERO:
            return izquierda
        if izquierda == mx.ZERO:
            return mx.Neg(derecha)
    if coeficiente != 1 and len(factores) == 1:
        return trig._desde_factores(coeficiente, factores)
    return e


def _simplifica_paso(paso: mx.Expr) -> mx.Expr:
    """``2·pi/2`` → ``pi`` and ``1·pi`` → ``pi``: the step reads as the student writes it."""
    coeficiente, factores = trig._factores(paso)
    if factores == [mx.Const("pi")]:
        if coeficiente == 1:
            return mx.PI
        if coeficiente == -1:
            return mx.Neg(mx.PI)
        return mx.Mul(mx.Num(coeficiente), mx.PI)
    return paso


def _afine(e: mx.Expr, var: str) -> tuple[Fraction | None, mx.Expr]:
    """``(a, b)`` for ``e = a·var + b``; ``a is None`` when ``e`` is not affine.

    ``a is None`` covers two cases the caller has to tell apart: a constant
    argument (``u = 3``) and a genuinely non-affine one (``u = sin(x)``).
    Neither can be inverted, and both are reported rather than approximated.
    """
    coeficiente, factores = trig._factores(e)
    variables = [f for f in factores if isinstance(f, mx.Sym) and f.name == var]
    otros = [f for f in factores if not (isinstance(f, mx.Sym) and f.name == var)]
    if len(variables) > 1 or (variables and otros):
        return None, mx.ZERO
    if not variables:
        return None, trig._desde_factores(coeficiente, otros)
    # u = a·var exactly, so the constant term is zero — reading it as the
    # coefficient is what produced the nonsense «x = (pi/2 − 1)» for sin(x)=1
    return coeficiente, mx.ZERO


def _como_expresion(c) -> mx.Expr:
    return c if isinstance(c, mx.Expr) else mx.Num(c)


def _fuera_de_rango(c) -> bool:
    """``|c| > 1`` for sine and cosine — numerically when it is not rational."""
    racional = mx.exact_value(_como_expresion(c))
    if racional is not None:
        return racional < -1 or racional > 1
    valor = mx.evaluate(_como_expresion(c))
    return valor is not None and abs(valor.real) > 1


def _es_uno(c) -> bool:
    return mx.exact_value(_como_expresion(c)) == 1


def _es_menos_uno(c) -> bool:
    return mx.exact_value(_como_expresion(c)) == -1


def _medio_pi(media: Fraction) -> mx.Expr:
    """``pi/2`` and ``-pi/2`` written as a multiple of pi, not as a fraction."""
    return mx.Mul(mx.Num(media), mx.PI)


def _soluciones_seno(c, u: mx.Expr, var: str):
    """``sin(u) = c``: two families, one when ``c = ±1`` where they merge."""
    if _fuera_de_rango(c):
        return [], [f"|{mx.text(_como_expresion(c))}| > 1: el seno no pasa de 1, "
                    "así que no hay solución"]
    alfa, multiplo, nota = _inversa("sin", c)
    hipotesis = [nota] if nota else [
        "el valor es notable: la solución se escribe como múltiplo exacto de pi"]
    if _es_uno(c) or _es_menos_uno(c):
        # sin(u) = 1 gives u = pi/2 + 2k·pi ; sin(u) = -1 gives u = -pi/2 + 2k·pi
        media = Fraction(1, 2) if _es_uno(c) else Fraction(-1, 2)
        familias = [Familia(_medio_pi(media), _dos_pi(),
                            "sin(u)=±1 en u = ±pi/2 + 2k·pi")]
    else:
        beta = mx.Sub(_pi(), alfa)
        familias = [
            Familia(alfa, _dos_pi(), "sin(u)=c en u = arcsin(c) + 2k·pi"),
            Familia(beta, _dos_pi(), "sin(u)=c en u = pi − arcsin(c) + 2k·pi"),
        ]
    return _trasladar(familias, u, var), hipotesis


def _soluciones_coseno(c, u: mx.Expr, var: str):
    if _fuera_de_rango(c):
        return [], [f"|{mx.text(_como_expresion(c))}| > 1: el coseno no pasa de "
                    "1, así que no hay solución"]
    alfa, _multiplo, nota = _inversa("cos", c)
    familias = [
        Familia(alfa, _dos_pi(), "cos(u)=c en u = arccos(c) + 2k·pi"),
        Familia(mx.Neg(alfa), _dos_pi(), "cos(u)=c en u = −arccos(c) + 2k·pi"),
    ]
    if _es_uno(c):
        familias = familias[:1]  # both branches are the same angle at c = 1
    return _trasladar(familias, u, var), [nota] if nota else []


def _soluciones_tangente(c, u: mx.Expr, var: str):
    alfa, _multiplo, nota = _inversa("tan", c)
    hipotesis = ["la tangente tiene periodo pi, no 2pi: por eso el paso es pi"]
    if nota:
        hipotesis.append(nota)
    familias = [Familia(alfa, _pi(), "tan(u)=c en u = arctan(c) + k·pi")]
    return _trasladar(familias, u, var), hipotesis


def _trasladar(familias: list[Familia], u: mx.Expr, var: str) -> list[Familia]:
    """Invert ``u = ...`` into ``x = ...`` when possible; otherwise say so."""
    salida: list[Familia] = []
    for familia in familias:
        invertida = _invertir(u, familia.base, familia.paso, var)
        if invertida is None:
            familia = Familia(
                familia.base, familia.paso, familia.metodo,
                f"las soluciones son para «{mx.text(u)}»; deshacer ese cambio de "
                "variable no está resuelto todavía, así que no se escribe en x (§5.4)")
            salida.append(familia)
            continue
        base, paso, _ = invertida
        salida.append(Familia(base, paso, familia.metodo, familia.hipotesis))
    return salida


# --- case 2: a·sin(u) + b·cos(u) = c ---------------------------------------


def _caso_fase(f: mx.Expr, var: str):
    """``a·sin(u) + b·cos(u) = c``, brought to one sine with a phase shift."""
    from academic_core.domain.engineering.mathlab.trig import _factores

    if not isinstance(f, (mx.Add, mx.Sub)):
        return None
    terminos = trig._terminos(f)
    # At least two terms, not exactly three: the equation arrives as «f - c», so
    # the constant is usually a term of its own — but the rational case hands over
    # a bare numerator with no constant in it, and «a·sin + b·cos = 0» is the same
    # family with c = 0, not a different one.
    if len(terminos) < 2:
        return None
    a = b = None
    cte = Fraction(0)
    u = None
    for signo, termino in terminos:
        coeficiente, factores = _factores(termino)
        if not factores:
            cte = cte + signo * coeficiente
            continue
        if len(factores) != 1 or isinstance(factores[0], mx.Pow):
            return None
        funcion = factores[0]
        if not (isinstance(funcion, mx.Call) and len(funcion.args) == 1):
            return None
        if funcion.name == "sin" and a is None:
            a, u = signo * coeficiente, funcion.args[0]
        elif funcion.name == "cos" and b is None:
            b, u2 = signo * coeficiente, funcion.args[0]
            if u is None:
                u = u2
            elif u != u2:
                return None
        else:
            return None
    if a is None or b is None or u is None or (a == 0 and b == 0):
        return None
    # f = a·sin + b·cos + cte = 0, so a·sin + b·cos = −cte. Reading cte as the
    # right-hand side is what produced arcsin(−1/√13) for 2·sin+3·cos = 1.
    familias, hipotesis = _resolver_por_fase(a, b, -cte, u, var)
    espurias = _comprobar(familias, f, var)
    return familias, hipotesis, espurias


def _resolver_por_fase(a: Fraction, b: Fraction, cte: Fraction, u: mx.Expr, var: str):
    """``a·sin+b·cos = R·sin(u+phi)``, then solve the sine.

    ``R = sqrt(a²+b²)`` and ``phi = atan2(b, a)``. §5.5b: the phase shift is the
    reason this family is solvable at all, and the reason it is *only* worth
    doing when ``a² + b²`` is a square.
    """
    R2 = a * a + b * b
    if cte * cte > R2:
        return [], [f"|{cte}| > {float(math.sqrt(float(R2))):.6g}: la amplitud de "
                    "a·sin+b·cos no llega, así que no hay solución"]
    norma = _raiz_exacta(R2)
    # 0/raiz is 0: leaving the quotient there made exact_value give up and the
    # solution came out as asin(0/sqrt(2)) instead of asin(0)
    c = mx.ZERO if cte == 0 else mx.Div(mx.Num(cte), norma)
    alfa, _ = _inversa("sin", c)[:2]
    beta = mx.Sub(_pi(), alfa)
    # the phase goes through _inversa so that atan(1) comes out as pi/4 instead of
    # an unevaluated atan, which is the difference between an exact critical
    # point and one this engine cannot place
    if a != 0:
        phi, _multiplo, _nota = _inversa("tan", Fraction(b, a))
    else:
        phi = mx.Mul(mx.Num(Fraction(1, 2)), mx.PI)
    familias = [
        Familia(mx.Sub(alfa, phi), _dos_pi(),
                "a·sin(u)+b·cos(u) = R·sin(u+phi), luego u = arcsin(c) − phi"),
        Familia(mx.Sub(beta, phi), _dos_pi(),
                "la segunda rama del seno, u = pi − arcsin(c) − phi"),
    ]
    hipotesis = [
        f"R = {mx.pretty(norma)} y phi = atan2(b,a): el desplazamiento de fase es "
        "lo que convierte la suma en un solo seno (§5.5b)",
    ]
    return _trasladar(familias, u, var), hipotesis


def _raiz_exacta(valor: Fraction) -> mx.Expr:
    """``sqrt(valor)`` exactly: a rational root when there is one, else the root."""
    from academic_core.domain.engineering.mathlab.mvexpr import _exact_root
    raiz = _exact_root(valor, 2)
    if raiz is not None:
        return mx.Num(raiz)
    return mx.Root(2, mx.Num(valor))


# --- case 3: a polynomial in sin, cos or tan --------------------------------


def _caso_racional(f: mx.Expr, var: str):
    """``N/D = 0`` reduces to ``N = 0``, and that is the whole strategy (T-20).

    This is the case that makes a reciprocal equation solvable at all:
    ``sec(x) = 1`` is ``1/cos(x) - 1 = 0``, whose rational normal form is
    ``(1 - cos(x)) / cos(x)``. Its zeros are the zeros of the **numerator**, never
    the denominator's — the points where the denominator dies are poles, and a
    pole is not a solution to anything.

    The pre-pass that turns ``sec`` into ``1/cos`` lives in :func:`_a_cocientes`
    rather than here, because a rule that expands and another that shrinks cannot
    share a fixed point.
    """
    from academic_core.domain.engineering.mathlab import inequaciones as I

    f = I._a_cocientes(f)
    if not mx.depends(f, var):
        return None
    ratio = P.as_ratio(f, var)
    if ratio is None or ratio.is_constant_ratio():
        return None
    # to_expr rebuilds the expression faithfully but not canonically: it comes back
    # as «1*cos(x) + (-1)*sin(x)», and no case below recognises that shape. One pass
    # of the normaliser turns it into «cos(x) - sin(x)», which they all do.
    from academic_core.domain.engineering.mathlab import trig as T

    numerador = T.simplify(P.to_expr(ratio.numerator))
    if mx.text(numerador) == mx.text(f):
        return None                     # nothing was actually divided out
    if mx.exact_value(numerador) == 0:
        return [], ["el numerador se anula en todas partes, así que la ecuación "
                    "se cumple siempre que el denominador no se anule"], []
    hipotesis = [f"el lado izquierdo se lleva a un cociente: se multiplica por el "
                 f"denominador y queda «{mx.text(numerador)} = 0». Los puntos donde "
                 f"el denominador se anula son polos, no soluciones"]
    familias, h, espurias = _casos(numerador, var)
    return familias, hipotesis + list(h), espurias


def _caso_polinomio(f: mx.Expr, var: str):
    """``P(sin(u)) = 0`` and its sisters: exact roots first, then back up."""
    from academic_core.domain.engineering.mathlab.trig import _terminos

    if not isinstance(f, (mx.Add, mx.Sub)):
        return None
    terminos = _terminos(f)
    if len(terminos) < 2:
        return None
    for nombre in ("sin", "cos", "tan"):
        sub = mx.Sym("u")
        polinomio = _como_polinomio(f, nombre, sub)
        if polinomio is None:
            continue
        raices, motivo = _raices_reales(polinomio, sub)
        grado = P.degree_in(polinomio, sub.name)
        if not raices:
            return [], [motivo], []
        familias: list[Familia] = []
        hipotesis = [f"el lado izquierdo es un polinomio de grado {grado} en "
                     f"{nombre}(u): se buscan sus raíces exactas y luego se "
                     "deshace el cambio"]
        for raiz in raices:
            # The polynomial gave the value of ``sin(u)``, so the next equation is
            # ``sin(x) = raiz`` — not ``u = arcsin(raiz)`` with ``u`` left over.
            # Passing the variable itself as ``u`` is what makes _trasladar a
            # no-op instead of leaving a dangling change of variable.
            if nombre == "sin":
                nuevas, h = _soluciones_seno(raiz, mx.Sym(var), var)
            elif nombre == "cos":
                nuevas, h = _soluciones_coseno(raiz, mx.Sym(var), var)
            else:
                nuevas, h = _soluciones_tangente(raiz, mx.Sym(var), var)
            familias.extend(nuevas)
            hipotesis.extend(h)
        espurias = _comprobar(familias, f, var)
        return _deduplica(familias), hipotesis, espurias
    return None


def _deduplica(familias: list[Familia]) -> list[Familia]:
    """The same family twice is a bug the student would report; drop it.

    ``sin(x)³ − sin(x) = 0`` has roots 0, 1 and −1, and the root 0 reaches the
    sine case by more than one route.
    """
    vistos: dict[str, Familia] = {}
    for familia in familias:
        clave = (mx.text(familia.base), mx.text(familia.paso))
        vistos.setdefault(clave, familia)
    return list(vistos.values())


def _como_polinomio(f: mx.Expr, nombre: str, sub: mx.Expr):
    """``f`` seen as a polynomial in ``sub``, or ``None``."""
    def sustituir(e: mx.Expr) -> mx.Expr:
        if isinstance(e, mx.Call) and e.name == nombre and len(e.args) == 1:
            return sub
        if isinstance(e, mx.Neg):
            return mx.Neg(sustituir(e.arg))
        if isinstance(e, mx.Pow):
            return mx.Pow(sustituir(e.base), sustituir(e.exponent))
        if isinstance(e, mx.Call):
            return mx.Call(e.name, tuple(sustituir(a) for a in e.args))
        if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
            return type(e)(sustituir(e.left), sustituir(e.right))
        return e

    try:
        polinomio = P.as_poly(sustituir(f))
    except Exception:
        return None
    if not polinomio:
        return None
    # Anything left as an *atom* means the substitution never applied to it:
    # 2·cos(x) − 1 is not a polynomial in sin(u), and accepting it as one made
    # the solver report «no hay soluciones» for an equation with four of them.
    if P.atoms_of(polinomio):
        return None
    variables = P.real_variables(polinomio)
    if variables - {sub.name} or sub.name not in variables:
        return None
    return polinomio


def _raices_reales(polinomio: P.Polynomial, sub: mx.Expr):
    """Exact real roots, with a Spanish reason when there are none to give."""
    grado = P.degree_in(polinomio, sub.name)
    if grado < 1:
        return [], "el polinomio es constante y no se anula: no hay solución"
    if grado == 1:
        c0 = polinomio.get((), Fraction(0))
        c1 = polinomio.get(((sub.name, 1),), Fraction(0))
        if c1 == 0:
            return [], "el coeficiente de u se anula: la ecuación es degenerada"
        return [mx.Num(-c0 / c1)], ""
    if grado == 2:
        c2 = polinomio.get(((sub.name, 2),), Fraction(0))
        c1 = polinomio.get(((sub.name, 1),), Fraction(0))
        c0 = polinomio.get((), Fraction(0))
        discriminante = c1 * c1 - 4 * c2 * c0
        if discriminante < 0:
            return [], (f"el discriminante es {discriminante} < 0: no hay raíces "
                        "reales, y por tanto no hay soluciones reales")
        raiz = _raiz_exacta(discriminante)
        return [mx.Div(mx.Add(mx.Neg(mx.Num(c1)), raiz), mx.Num(2 * c2)),
                mx.Div(mx.Sub(mx.Neg(mx.Num(c1)), raiz), mx.Num(2 * c2))], ""
    exactas = [mx.Num(r) for r in _divisores_racionales(polinomio, sub.name)
               if _valor_en(polinomio, r, sub.name) == 0]
    if exactas:
        return exactas, ("solo se dan las raíces racionales exactas: el resto "
                         "depende de una cúbica o de un grado mayor y se dice (§5.4)")
    return [], (f"el polinomio es de grado {grado} y no tiene raíces racionales: "
                "este motor no resuelve ese caso y no va a devolver un decimal "
                "disfrazado de solución exacta (§5.4)")


def _divisores_racionales(polinomio: P.Polynomial, var: str) -> list[Fraction]:
    """Candidates of the rational root theorem, bounded (§5.5).

    When the constant term is zero, ``0`` is a root but the *others* are not
    found by dividing by it: ``u³ − u`` has roots 0, 1 and −1, and returning only
    ``0`` because the theorem degenerated is how half the solutions disappear.
    The polynomial is deflated by ``u`` and the theorem applied to the rest.
    """
    constante = polinomio.get((), Fraction(0))
    if constante == 0:
        desinflado: P.Polynomial = {}
        for monomio, coeficiente in polinomio.items():
            # the name must *disappear* at exponent zero, not stay as (u,0):
            # keeping it means the deflated polynomial still looks constant-free
            # and the recursion never terminates
            clave = tuple(sorted((n, g - 1) for n, g in monomio if g > 0))
            desinflado[clave] = desinflado.get(clave, Fraction(0)) + coeficiente
        if not desinflado:
            return [Fraction(0)]
        return [Fraction(0)] + _divisores_racionales(desinflado, var)
    numerador = abs(constante.numerator)
    denominador = constante.denominator
    divisores_n = _divisores(numerador)[:32]
    divisores_d = _divisores(denominador)[:32]
    salida: list[Fraction] = []
    for n in divisores_n:
        for d in divisores_d:
            for signo in (1, -1):
                valor = Fraction(signo * n, d)
                if valor not in salida:
                    salida.append(valor)
    return salida[:256]


def _divisores(n: int) -> list[int]:
    if n == 0:
        return [1]
    salida = []
    i = 1
    while i * i <= n:
        if n % i == 0:
            salida.extend({i, n // i})
        i += 1
    return sorted(salida)


def _valor_en(polinomio: P.Polynomial, valor: Fraction, var: str) -> Fraction:
    total = Fraction(0)
    for monomio, coeficiente in polinomio.items():
        grado = dict(monomio).get(var, 0)
        total += coeficiente * valor ** grado
    return total


def _deshacer(nombre: str, familias: list[Familia], var: str) -> list[Familia]:
    """Replace the ``u`` the polynomial was solved in by the real angle."""
    salida = []
    for familia in familias:
        base = _sustituir_u(familia.base, nombre)
        paso = _sustituir_u(familia.paso, nombre)
        salida.append(Familia(base, paso, familia.metodo, familia.hipotesis))
    return salida


def _sustituir_u(e: mx.Expr, nombre: str) -> mx.Expr:
    if isinstance(e, mx.Sym) and e.name == "u":
        return mx.Call(nombre, (mx.Sym("x"),))
    if isinstance(e, mx.Neg):
        return mx.Neg(_sustituir_u(e.arg, nombre))
    if isinstance(e, mx.Pow):
        return mx.Pow(_sustituir_u(e.base, nombre), _sustituir_u(e.exponent, nombre))
    if isinstance(e, mx.Call):
        return mx.Call(e.name, tuple(_sustituir_u(a, nombre) for a in e.args))
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return type(e)(_sustituir_u(e.left, nombre), _sustituir_u(e.right, nombre))
    return e


# ---------------------------------------------------------------------------
# verification: every solution goes back into the original equation
# ---------------------------------------------------------------------------


def verifica_miembro(familia: Familia, ecuacion: mx.Expr, var: str = "x") -> bool:
    """Whether one family really solves ``ecuacion``, checked by substitution.

    Public because it is the check that gives T-12 its teeth, and the calculator
    runs it as its independent path: substituting a member back into the original
    equation never looks at how the family was derived, so it cannot inherit a
    mistake from the derivation.
    """
    return not _comprobar([familia], ecuacion, var)


def _comprobar(familias: list[Familia], ecuacion: mx.Expr, var: str) -> list[str]:
    """Substitute members of each family; report the families that fail."""
    espurias: list[str] = []
    for familia in familias:
        peor = 0.0
        for k in range(-MIEMBROS_COMPROBADOS // 2, MIEMBROS_COMPROBADOS // 2 + 1):
            if k == 0:
                continue
            valor = familia.miembro(k, var)
            # No guard against a constant member: a solved family *is* a constant
            # for each k, and substituting it to get a residual is the whole
            # check. Skipping those members left _comprobar unable to flag
            # anything at all — it returned an empty list for every family,
            # including ones that do not satisfy the equation.
            resto = mx.substitute(ecuacion, var, valor)
            numerico = _evaluar(resto)
            if numerico is None:
                continue  # undefined there: not evidence either way
            escala = max(1.0, abs(numerico))
            peor = max(peor, abs(numerico) / escala)
        if peor > TOLERANCIA:
            espurias.append(f"{familia.texto(var)} no satisface la ecuación "
                            f"(residuo {peor:.3g}); se descarta como espuria")
    return espurias


def _evaluar(e: mx.Expr) -> float | None:
    """Best effort numeric value of a no-variable expression, with its error."""
    try:
        valor = mx.evaluate(e)
    except Exception:
        return None
    if valor is None:
        return None
    if abs(valor.imag) > 1e-9:
        return None
    return abs(valor.real)
