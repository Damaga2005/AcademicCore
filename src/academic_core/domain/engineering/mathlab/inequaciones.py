# SPDX-License-Identifier: MIT
"""MATH_LAB T-13: trigonometric inequalities, sign charts and periodic solution sets.

How an inequality is solved here
--------------------------------

An inequality ``f(x) > 0`` becomes a **sign chart**, and a sign chart is only as
good as its critical points. Those come from two places and both have to be
there:

1. the **zeros** of ``f``, where the sign can change;
2. the **singularities**, where ``f`` does not exist — and those are the zeros of
   its denominators.

Leaving out the second is the classic mistake: ``1/tan(x) > 0`` looks sign-constant
between the multiples of ``pi`` if the poles are ignored, and the answer comes out
plainly wrong.

From those points the sign on each gap is decided **numerically**, at one point per
gap. That is not a shortcut and it is not an approximation of the answer: a
continuous function with no zero and no pole in a gap cannot change sign in it.
What the sampling buys is the guarantee, not a guess.

Then the answer is *periodic*, so only one period is described and the repetition
is said rather than enumerated: there are infinitely many of them.

Closed endpoints are the other half of the story. ``sin(x) > 1/2`` gives open
intervals, because at the zeros the inequality is not satisfied; ``sin(x) ≥ 1/2``
gives closed ones, and getting that wrong is what makes a solution set look right
and not be.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import dominio as D
from academic_core.domain.engineering.mathlab import ecuaciones as E
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import trig
from academic_core.errors import UnsupportedError

#: how many sample points per gap, so a sign flip hiding in a gap is unlikely to
#: be missed. One suffices mathematically; more is cheap insurance (§5.5).
MUESTRAS_POR_HUECO = 3

def sin_refuso(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"NO_RULE: {mensaje}")


# ---------------------------------------------------------------------------
# the answer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Solucion:
    """A periodic solution set: one period, plus how it repeats.

    ``puntos`` is only ever filled for ``=``, where the answer is a set of isolated
    points rather than intervals. It exists because an equation has no interior:
    a sign chart describes the gaps *between* critical points, and for ``=`` there
    are no gaps to describe, only the points themselves.
    """

    conjunto: D.Conjunto
    periodo: Fraction | None
    operador: str
    hipotesis: tuple[str, ...] = ()
    avisos: tuple[str, ...] = ()
    puntos: tuple[D.Punto, ...] = ()

    def texto(self) -> str:
        if self.puntos:
            base = ", ".join(f"{p.texto()}" for p in self.puntos)
            base = f"x = {base}"
        elif self.conjunto.vacio:
            return "no hay soluciones"
        else:
            base = self.conjunto.texto()
        if self.periodo is None:
            return base
        return f"{base}   y se repite cada {self.periodo}·pi"

    @property
    def vacia(self) -> bool:
        return not self.puntos and self.conjunto.vacio

    def contiene(self, coeficiente_pi: Fraction) -> bool:
        """Whether ``coeficiente_pi * pi`` is in the solution, inside one period."""
        punto = D.punto_pi(coeficiente_pi)
        return punto in self.puntos or self.conjunto.contiene(punto)


# ---------------------------------------------------------------------------
# the critical points
# ---------------------------------------------------------------------------


def ceros(e: mx.Expr, var: str = "x") -> list[mx.Expr] | None:
    """Where ``e`` vanishes, or ``None`` when this engine cannot say.

    ``None`` is the answer that matters: it is «no lo sé», not «no hay ceros»,
    and the caller must not go on to draw a sign chart as if it knew.

    The order of the cases is deliberate: reciprocals become quotients *first*,
    then the harmless ``- 0`` is taken off, and only then are products and
    quotients decomposed structurally. That order is sound and the equation
    solver cannot do it on its own — the zeros of ``a*b`` are the zeros of ``a``
    together with those of ``b``, and the zeros of ``a/b`` are those of ``a``
    alone, so ``1/tan(x)`` has none and that is a fact, not a case to refuse.
    """
    if not mx.depends(e, var):
        return [] if mx.evaluate(e) != 0 else None
    e = _a_cocientes(e)
    if isinstance(e, mx.Sub) and e.right == mx.ZERO:
        return ceros(e.left, var)
    if isinstance(e, mx.Add):
        if isinstance(e.right, mx.Num) and e.right.value == 0:
            return ceros(e.left, var)
        if isinstance(e.left, mx.Num) and e.left.value == 0:
            return ceros(e.right, var)
    if isinstance(e, mx.Div):
        return ceros(e.left, var)
    if isinstance(e, mx.Mul):
        izquierda, derecha = ceros(e.left, var), ceros(e.right, var)
        if izquierda is None or derecha is None:
            return None
        return _une(izquierda, derecha)
    if isinstance(e, mx.Pow):
        n = mx.exact_integer(e.exponent)
        if n is not None and n > 1:
            # f^n = 0 exactly where f = 0, for every positive integer n. Treating
            # an even power differently would be the error of thinking that
            # squaring moves the zeros; it does not, it only makes them double.
            return ceros(e.base, var)
    try:
        resolucion = E.resolver(f"{mx.text(e)} = 0", var)
    except UnsupportedError:
        return None
    if resolucion.sin_respuesta:
        return None
    if resolucion.vacia:
        return []
    vistos: list[mx.Expr] = []
    for familia in resolucion.familias:
        base = _dentro_del_periodo(familia.base)
        if base is not None and all(mx.text(base) != mx.text(v) for v in vistos):
            vistos.append(base)
    if not vistos and resolucion.familias:
        # there ARE zeros, but they come out as arcsin(...) and cannot be placed
        # on the pi grid exactly. Saying «no zeros» here would be the exact same
        # false answer as «no solutions», one level down.
        return None
    return vistos


def _llamadas(e: mx.Expr) -> list[mx.Call]:
    salida: list[mx.Call] = []
    pila = [e]
    while pila:
        actual = pila.pop()
        if isinstance(actual, mx.Call):
            salida.append(actual)
            pila.extend(actual.args)
        elif isinstance(actual, mx.Neg):
            pila.append(actual.arg)
        elif isinstance(actual, mx.Pow):
            pila.extend((actual.base, actual.exponent))
        elif isinstance(actual, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
            pila.extend((actual.left, actual.right))
    return salida


def singularidades(e: mx.Expr, var: str = "x") -> list[mx.Expr] | None:
    """Where ``e`` does not exist, apart from its quotients.

    T-13 asks for «ceros, singularidades y denominadores», and the third one is
    not the whole story: ``tan(x)`` has a pole at ``pi/2`` with no denominator
    anywhere in the expression. Missing that pole is what makes ``tan(x) < 1``
    come out as one interval when it is two.

    The poles of ``tan`` are the zeros of ``cos``, and those of ``cot`` the zeros
    of ``sin``, so this reuses the equation solver rather than inventing a table.
    """
    salida: list[mx.Expr] = []
    for llamada in _llamadas(e):
        denominador = {"tan": "cos", "cot": "sin",
                       "sec": "cos", "csc": "sin"}.get(llamada.name)
        if denominador is None:
            continue
        ceros_del = ceros(_fn(denominador, llamada.args[0]), var)
        if ceros_del is None:
            return None
        salida = _une(salida, ceros_del)
    return salida



def _une(a: list[mx.Expr], b: list[mx.Expr]) -> list[mx.Expr]:
    salida = list(a)
    for v in b:
        if all(mx.text(v) != mx.text(u) for u in salida):
            salida.append(v)
    return salida


def _a_cocientes(e: mx.Expr) -> mx.Expr:
    """``sec(u) → 1/cos(u)`` and friends, so the solver sees through them."""
    if isinstance(e, mx.Call) and len(e.args) == 1:
        for fuente, (num, den) in (("sec", ("1", "cos")), ("csc", ("1", "sin")),
                                   ("cot", ("cos", "sin"))):
            if e.name == fuente:
                return mx.Div(mx.Num(Fraction(1)) if num == "1" else _fn(num, e.args[0]),
                              _fn(den, e.args[0]))
        return mx.Call(e.name, tuple(_a_cocientes(a) for a in e.args))
    if isinstance(e, mx.Neg):
        return mx.Neg(_a_cocientes(e.arg))
    if isinstance(e, mx.Pow):
        return mx.Pow(_a_cocientes(e.base), _a_cocientes(e.exponent))
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return type(e)(_a_cocientes(e.left), _a_cocientes(e.right))
    return e


def _fn(nombre: str, arg: mx.Expr) -> mx.Expr:
    return mx.Call(nombre, (arg,))


def _coeficiente_pi(e: mx.Expr) -> Fraction | None:
    """The coefficient of ``pi`` in ``e``, or ``None`` when it is not one.

    A single reader for both jobs the module has: placing a solution value inside
    the period, and turning it into a point of the chart. Having one reader is not
    tidiness — it is the reason ``0`` cannot be understood in one place and
    forgotten in the other, which is how ``tan(x) >= 0`` lost the endpoint where it
    equals zero.

    The sign is read through ``trig._terminos`` rather than ``trig._factores``,
    because ``_factores`` does not look inside a ``Neg``: a value written ``-pi/2``
    would come back as ``None`` and the chart would lose one of the two zeros of
    ``cos(x)``.
    """
    if e == mx.ZERO:
        return Fraction(0)          # «0» and «0*pi» are the same point
    terminos = trig._terminos(e)
    if len(terminos) != 1:
        return None
    signo, termino = terminos[0]
    coeficiente, factores = trig._factores(termino)
    return coeficiente * signo if factores == [mx.Const("pi")] else None


def _dentro_del_periodo(base: mx.Expr) -> mx.Expr | None:
    """Reduce a solution value into ``[0, 2pi)``.

    ``None`` when the value is not a multiple of ``pi``: an ``asin(c)`` cannot be
    shifted by ``2k*pi`` without evaluating it, and the caller has to know that
    rather than assume it.
    """
    coeficiente = _coeficiente_pi(base)
    return mx.Mul(mx.Num(coeficiente % 2), mx.PI) if coeficiente is not None else None


def _punto(valor: Fraction) -> D.Punto:
    return D.punto_pi(valor)


def _a_punto(e: mx.Expr) -> D.Punto | None:
    coeficiente = _coeficiente_pi(e)
    return D.punto_pi(coeficiente) if coeficiente is not None else None


def resolver_inequidad(texto_inequidad: str, var: str = "x") -> Solucion:
    """Solve ``f(x) REL 0`` and describe the answer as a periodic set."""
    operador, izquierda, derecha = _separa(texto_inequidad)
    a = _parse(izquierda, var)
    b = _parse(derecha, var)
    f = mx.Sub(a, b)
    periodo = D.periodo_minimo(f, var)
    hipotesis = list(_metodo())

    # Periodicity is checked first: an aperiodic expression cannot be answered by
    # a repeating pattern at all, and saying that is more useful than reporting
    # that its zeros are unknown — which is a different problem entirely.
    if periodo is None:
        raise sin_refuso(
            "esta expresión no es periódica, así que la solución no se puede dar "
            "como un patrón que se repite; se puede calcular por intervalos, pero "
            "eso todavía no está hecho (§5.4)")

    ceros_f = ceros(f, var)
    if ceros_f is None:
        raise sin_refuso(
            "no se saben los ceros de esta expresión, y sin ellos no hay carta de "
            "signos que sea fiable. Eso NO es «no hay soluciones»: es que este "
            "motor todavía no lo resuelve (§5.4)")

    singulares: list[mx.Expr] = []
    for denominador in D.denominadores(f):
        ceros_d = ceros(denominador, var)
        if ceros_d is None:
            raise sin_refuso(
                f"no se saben los ceros de «{mx.text(denominador)}», que es un "
                "denominador: sin ellos no se sabe dónde deja de existir la "
                "expresión (§5.4)")
        singulares = _une(singulares, ceros_d)
    # and the poles the functions bring with them, which have no denominator at all
    de_funciones = singularidades(f, var)
    if de_funciones is None:
        raise sin_refuso(
            "no se sabe dónde están los polos de las funciones que aparecen "
            "(tan y cot se anulan en ciertos puntos), así que la carta de signos "
            "no sería fiable (§5.4)")
    singulares = _une(singulares, de_funciones)
    if singulares:
        hipotesis.append(
            "los denominadores también cuentan como puntos críticos: son puntos "
            "donde la expresión no existe, y el signo puede cambiar ahí sin que "
            "haya un cero de por medio")

    period_pi = periodo  # dominio.periodo_minimo ya devuelve la razón en pi
    criticos = sorted({c for c in (_a_punto(v) for v in ceros_f + singulares)
                       if c is not None},
                      key=lambda p: p.coeficiente % period_pi)
    if len(criticos) < len([v for v in ceros_f if _a_punto(v)]) + \
            len([v for v in singulares if _a_punto(v)]):
        raise sin_refuso(
            "algún cero no es un múltiplo exacto de pi, así que el patrón "
            "periódico no se puede escribir de forma exacta (§5.4)")

    if operador == "=":
        # An equation has no interior. The sign chart describes the gaps between
        # critical points, and for "=" the answer is the critical points
        # themselves — the zeros, and not the poles, which is the one place where
        # the two are not interchangeable.
        puntos = tuple(sorted({p for p in (_a_punto(v) for v in ceros_f)
                               if p is not None},
                              key=lambda p: p.coeficiente % period_pi))
        if not puntos and ceros_f:
            raise sin_refuso(
                "los ceros existen pero no se pueden escribir como múltiplos "
                "exactos de pi, así que el conjunto de soluciones no es exacto "
                "(§5.4)")
        hipotesis.append(
            "con «=» la solución son los ceros, no los intervalos: una ecuación no "
            "tiene interior, y los polos quedan fuera porque allí la expresión no "
            "existe")
        return Solucion(D.Conjunto(), periodo, operador,
                        hipotesis=tuple(hipotesis), puntos=puntos)

    ceros_p = {p for p in (_a_punto(v) for v in ceros_f) if p is not None}
    polos_p = {p for p in (_a_punto(v) for v in singulares) if p is not None}
    piezas = _carta_de_signos(f, var, periodo, ceros_p, polos_p, operador)
    return Solucion(piezas, periodo, operador, hipotesis=tuple(hipotesis))


def _carta_de_signos(f: mx.Expr, var: str, periodo: Fraction,
                     ceros_p: set[D.Punto], polos_p: set[D.Punto],
                     operador: str) -> D.Conjunto:
    """One interval per gap, kept when the sign matches ``operador``.

    Every endpoint is decided on its own, because the three kinds of point are not
    interchangeable:

    - a **zero** is in the set for ``>=`` and out for ``>``, which is the ordinary
      business;
    - a **pole** is never in the set, for any operator, because the expression
      does not exist there — closing it would put a point in the solution at which
      the inequality cannot even be evaluated;
    - the **point where the period starts** is neither, and it has to be read off
      the value of the function. Leaving it always open silently drops a real
      solution: ``cos(x)^2 > 1/2`` holds at 0, and 0 is where the chart begins.
    """
    period_pi = periodo
    rejilla = [Fraction(0)] + sorted(
        {p.coeficiente % period_pi for p in ceros_p | polos_p} | {period_pi})
    piezas: list[D.Intervalo] = []
    for izquierda, derecha in zip(rejilla, rejilla[1:]):
        if derecha <= izquierda:
            continue
        signo = _signo_del_hueco(f, var, izquierda, derecha)
        if not _cumple(signo, operador):
            continue
        abierta_izq = not _extremo_entra(f, var, izquierda, periodo,
                                         ceros_p, polos_p, operador)
        abierta_der = not _extremo_entra(f, var, derecha, periodo,
                                         ceros_p, polos_p, operador)
        piezas.append(D.Intervalo(_punto(izquierda), _punto(derecha),
                                  abierta_izq, abierta_der))
    return D.desde_intervalos(piezas, mergir_tocados=False)


def _signo_del_hueco(f: mx.Expr, var: str, izquierda: Fraction,
                      derecha: Fraction) -> float:
    """The sign on one gap, sampled — and refused rather than guessed."""
    paso = (derecha - izquierda) / (MUESTRAS_POR_HUECO + 1)
    signos = set()
    for i in range(MUESTRAS_POR_HUECO):
        p = izquierda + paso * (i + 1)
        valor = mx.evaluate(f, {var: float(p) * 3.141592653589793})
        if valor is None or abs(valor.imag) > 1e-9:
            continue
        # the SIGN, not the value: two different magnitudes are the same sign,
        # and comparing them is what made every chart look inconsistent
        signos.add(0 if abs(valor.real) < 1e-9 else (1 if valor.real > 0 else -1))
    if len(signos) != 1:
        raise sin_refuso(
            f"el signo cambia dentro de ({izquierda}*pi, {derecha}*pi) sin que haya "
            "ningún cero ni singularidad: eso no debería pasar, y no se va a adivinar "
            f"(el valor «{mx.text(f)}» no es continuo, o el motor no ha visto todos "
            "sus ceros)")
    return next(iter(signos))


def _extremo_entra(f: mx.Expr, var: str, coeficiente: Fraction, periodo: Fraction,
                   ceros_p: set[D.Punto], polos_p: set[D.Punto],
                   operador: str) -> bool:
    """Whether the endpoint at ``coeficiente * pi`` belongs to the solution."""
    punto = D.punto_pi(coeficiente)
    if punto in _modulo(polos_p, periodo):
        return False            # a pole is never in the solution set
    if punto in _modulo(ceros_p, periodo):
        return operador.endswith("=")
    valor = mx.evaluate(f, {var: float(coeficiente) * 3.141592653589793})
    if valor is None or abs(valor.imag) > 1e-9 or abs(valor.real) > 1e12:
        return False
    return _cumple(valor.real, operador)


def _modulo(puntos: set[D.Punto], periodo: Fraction) -> set[D.Punto]:
    """The same points, folded into ``[0, periodo)``: 0 and the period are one."""
    return {D.punto_pi(p.coeficiente % periodo) for p in puntos}


def _cumple(signo: float, operador: str) -> bool:
    if operador in (">", ">="):
        return signo > 0
    if operador in ("<", "<="):
        return signo < 0
    return abs(signo) < 1e-9


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------


def _separa(texto: str) -> tuple[str, str, str]:
    """Split on the comparison operator, longest match first."""
    for operador in (">=", "<=", "=", ">", "<"):
        if operador in texto:
            izquierda, _, derecha = texto.partition(operador)
            if not izquierda.strip() or not derecha.strip():
                raise sin_refuso(f"uno de los dos lados de «{operador}» está vacío")
            return operador, izquierda.strip(), derecha.strip()
    raise sin_refuso(
        "falta el signo de comparación: la desigualdad tiene que venir como "
        "«sen(x) > 1/2» (admitidos >, <, >=, <= y =)")


def _parse(texto: str, var: str) -> mx.Expr:
    try:
        return mx.parse(texto)
    except Exception as exc:
        raise sin_refuso(f"no se pudo interpretar «{texto}»: {exc}") from exc


def _metodo() -> tuple[str, ...]:
    return (
        "se recorre un solo periodo y se repite: la solución es periódica y "
        "enumerarla sería infinito (§5.5b)",
        "el signo en cada hueco se decide numéricamente, lo cual es una prueba y "
        "no una aproximación: una función continua sin ceros ni polos en un hueco "
        "no puede cambiar de signo dentro de él",
    )
