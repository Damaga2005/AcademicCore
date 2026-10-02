# SPDX-License-Identifier: MIT
"""MATH_LAB: intervals, domains and restrictions, shared by T-11, T-12 and T-13.

Three families need the same thing and none of them had it: which points an
expression is defined on (§5.7), where it vanishes (T-12), and on which
interval an identity is true (T-11). Building it once, here, is why those three
are implemented in that order and not in the order they were written down.

Exact points
------------

Endpoints of a trigonometric domain are rational multiples of ``pi`` — ``pi/2``,
``3pi/4``, ``2pi`` — so a point is a :class:`Punto` of an exact rational and a
flag saying whether it is measured in units of ``pi``. Comparing two points is
then exact arithmetic and not a floating-point ``<``; §5.1 wants an exact answer
and §5.4 wants a refusal rather than a guess.

Solving is injected
-------------------

Finding the zeros of a denominator needs a solver, and the solver needs this
module to describe intervals. Rather than a circular import, :func:`dominio_de`
takes a ``resolver`` callback — the same shape as ``verify.verify_by_derivative``
already uses — so this module depends on nothing and everything can use it.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mathlab import mvexpr as mx

#: how many samples to take per period when a sign has to be decided numerically
MUESTRAS_POR_PERIODO = 24

#: how many periods a periodic set is repeated over before it is described as
#: "all of them" — §5.4: bounded work, and the bound is written down
MAX_PERIODOS = 8


def invalid(reason: str, message: str):
    from academic_core.errors import ValidationError
    return ValidationError(f"{reason}: {message}")


# ---------------------------------------------------------------------------
# exact points
# ---------------------------------------------------------------------------


#: A rational bracket for ``pi``, used to compare a multiple of ``pi`` with a
#: plain rational exactly. Sorting ``3`` and ``pi/2`` by comparing their
#: coefficients would put every rational before every multiple of ``pi``, which
#: is nonsense — 3 > pi/2 — and it silently corrupts every interval built on top.
PI_BAJO = Fraction(3141592653589793, 10 ** 15)
PI_ALTO = Fraction(3141592653589794, 10 ** 15)


def _comparacion_exacta(a: "Punto", b: "Punto") -> int:
    """``-1``, ``0`` or ``1`` for ``a`` against ``b``, decided exactly.

    Same kind of point on both sides is rational arithmetic. Across kinds, the
    bracket above decides it; if the bracket straddles, the two are within
    10⁻¹⁵ of each other and a float is honest enough — and it says so.
    """
    if a.es_pi == b.es_pi:
        return (a.coeficiente > b.coeficiente) - (a.coeficiente < b.coeficiente)
    if a.es_pi:
        pi, otro = a.coeficiente, b.coeficiente
        signo = 1
    else:
        pi, otro = b.coeficiente, a.coeficiente
        signo = -1
    if pi == 0:
        return -signo if otro > 0 else signo
    bajo, alto = pi * PI_BAJO, pi * PI_ALTO
    if bajo > otro:
        return signo
    if alto < otro:
        return -signo
    if bajo == alto == otro:
        return 0
    return -signo if float(pi) * 3.141592653589793 < float(otro) else signo


@dataclass(frozen=True, order=False)
class Punto:
    """An exact real point: ``coeficiente`` in units of ``pi`` when ``es_pi``."""

    coeficiente: Fraction
    es_pi: bool = False

    def expr(self) -> mx.Expr:
        if self.es_pi:
            if self.coeficiente == 1:
                return mx.PI
            if self.coeficiente == -1:
                return mx.Neg(mx.PI)
            return mx.Mul(mx.Num(self.coeficiente), mx.PI)
        return mx.Num(self.coeficiente)

    def texto(self) -> str:
        # written by hand rather than through ``mx.pretty``, which parenthesises
        # a negative coefficient and would print the interval as «([(-1/2)·π, …]»
        if not self.es_pi:
            return str(self.coeficiente)
        if self.coeficiente == 0:
            return "0"          # «0·pi» is noise, and 0 is what a student writes
        if self.coeficiente == 1:
            return "π"
        if self.coeficiente == -1:
            return "-π"
        return f"{self.coeficiente}·π"

    def valor(self) -> float:
        return float(self.coeficiente) * (3.141592653589793 if self.es_pi else 1.0)

    def __lt__(self, other: "Punto") -> bool:
        return _comparacion_exacta(self, other) < 0

    def __le__(self, other: "Punto") -> bool:
        return _comparacion_exacta(self, other) <= 0

    def __gt__(self, other: "Punto") -> bool:
        return _comparacion_exacta(self, other) > 0

    def __ge__(self, other: "Punto") -> bool:
        return _comparacion_exacta(self, other) >= 0

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Punto) and _comparacion_exacta(self, other) == 0

    def __hash__(self) -> int:
        return hash((self.es_pi, self.coeficiente))


def _exige_punto(p) -> None:
    """Refuse a bare coefficient where a point belongs, and say which it is.

    A ``Fraction`` reaching the comparison would fail a long way from the mistake,
    with an attribute error about ``es_pi``, and the reader would have to work
    backwards to find the call that was wrong. The bare coefficient is a plausible
    thing to write, so it is worth naming.
    """
    if not isinstance(p, Punto):
        raise invalid(
            "tipo de punto",
            f"se esperaba un Punto (por ejemplo punto_pi(1/2)) y lleg\u00f3 "
            f"{type(p).__name__}; si lo que tienes es el coeficiente de pi, "
            f"envu\u00f3lvelo con punto_pi(...)")


def punto_pi(coeficiente: Fraction) -> Punto:
    return Punto(coeficiente, True)


def punto(coeficiente: Fraction) -> Punto:
    return Punto(coeficiente, False)


# ---------------------------------------------------------------------------
# intervals and sets
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Intervalo:
    """An interval; ``None`` means unbounded on that side.

    Open by default, because the points that matter for a *domain* are exactly
    the excluded ones: a denominator that vanishes is not in its own domain.

    The two ``abierto_*`` flags exist for the other kind of set — where an
    identity *holds*. ``arcsin(sin(x)) = x`` is true on the **closed** interval
    ``[-pi/2, pi/2]`` and false immediately outside it, and a representation that
    could only say "open" would force the answer to be stated wrongly at both
    ends (§5.7).
    """

    izq: Punto | None
    der: Punto | None
    abierto_izq: bool = True
    abierto_der: bool = True

    def contiene(self, p: Punto) -> bool:
        if self.izq is not None:
            if (p < self.izq) or (self.izq == p and self.abierto_izq):
                return False
        if self.der is not None:
            if (p > self.der) or (self.der == p and self.abierto_der):
                return False
        return True

    @property
    def vacio(self) -> bool:
        if self.izq is None or self.der is None:
            return False
        if self.izq == self.der:
            return self.abierto_izq or self.abierto_der
        return self.der < self.izq

    @property
    def longitud(self) -> float | None:
        """Numeric length, for reporting. ``None`` when a side is unbounded."""
        if self.izq is None or self.der is None:
            return None
        a = _valor(self.izq)
        b = _valor(self.der)
        return None if a is None or b is None else b - a

    def texto(self) -> str:
        izquierda = "-∞" if self.izq is None else self.izq.texto()
        derecha = "∞" if self.der is None else self.der.texto()
        return f"{'(' if self.abierto_izq else '['}{izquierda}, " \
               f"{derecha}{')' if self.abierto_der else ']'}"

    def abierto(self) -> "Intervalo":
        return Intervalo(self.izq, self.der)


def _valor(p: Punto | None) -> float | None:
    if p is None:
        return None
    v = p.coeficiente * (3.141592653589793 if p.es_pi else 1)
    return float(v)


@dataclass(frozen=True)
class Conjunto:
    """A finite union of open intervals, sorted, disjoint and merged."""

    intervalos: tuple[Intervalo, ...] = ()

    @property
    def vacio(self) -> bool:
        return not any(not i.vacio for i in self.intervalos)

    def contiene(self, p: Punto) -> bool:
        _exige_punto(p)
        return any(i.contiene(p) for i in self.intervalos)

    def texto(self) -> str:
        if not self.intervalos:
            return "∅"
        partes = []
        for i in self.intervalos:
            if i.izq is None and i.der is None:
                partes.append("ℝ")
            else:
                partes.append(i.texto())
        return " ∪ ".join(partes)

    def interseccion(self, otro: "Conjunto") -> "Conjunto":
        piezas: list[Intervalo] = []
        for a in self.intervalos:
            for b in otro.intervalos:
                izq = a.izq if (b.izq is None or (a.izq is not None and a.izq >= b.izq)) else b.izq
                der = a.der if (b.der is None or (a.der is not None and a.der <= b.der)) else b.der
                intervalo = Intervalo(izq, der)
                if not intervalo.vacio:
                    piezas.append(intervalo)
        return Conjunto(_normaliza(piezas))

    def complemento(self) -> "Conjunto":
        piezas: list[Intervalo] = []
        anterior: Punto | None = None
        for i in self.intervalos:
            if i.izq is not None and (anterior is None or i.izq > anterior):
                piezas.append(Intervalo(anterior, i.izq))
            if i.der is not None:
                anterior = i.der
        if self.intervalos and (self.intervalos[-1].der is not None):
            piezas.append(Intervalo(self.intervalos[-1].der, None))
        return Conjunto(_normaliza(piezas))

    def puntos(self) -> tuple[Punto, ...]:
        """Every finite endpoint, which is where zeros and poles live."""
        vistos: list[Punto] = []
        for i in self.intervalos:
            for extremo in (i.izq, i.der):
                if extremo is not None and extremo not in vistos:
                    vistos.append(extremo)
        return tuple(sorted(vistos))


def _normaliza(intervalos: list[Intervalo], *,
               mergir_tocados: bool = True) -> tuple[Intervalo, ...]:
    """Sort, drop the empty ones and merge the ones that overlap.

    Sorted by left endpoint, two consecutive intervals merge only when the
    second starts before the first ends — strictly, unless ``mergir_tocados``
    says otherwise. Comparing with ``>=`` would merge ``(-∞,-pi)`` with
    ``(pi/2, ∞)`` into ``ℝ``, silently deleting the gap.

    Only open intervals are merged, and only when both sides are open: two
    intervals that meet at a point they both include still exclude that point
    from their union's interior, and folding them into one would add it back.
    """
    def clave(intervalo: Intervalo):
        # an interval without a left bound starts at -infinity and therefore
        # sorts *first*; sorting it last silently reorders the union
        return (0, Punto(Fraction(0))) if intervalo.izq is None \
            else (1, intervalo.izq)

    vivos = sorted((i for i in intervalos if not i.vacio), key=clave)
    fusionados: list[Intervalo] = []
    for intervalo in vivos:
        if not fusionados:
            fusionados.append(intervalo)
            continue
        anterior = fusionados[-1]
        if intervalo.izq is None or anterior.der is None:
            se_juntan = True
        elif intervalo.izq < anterior.der:
            se_juntan = True
        else:
            se_juntan = (mergir_tocados and intervalo.izq == anterior.der
                         and intervalo.abierto_izq and anterior.abierto_der)
        if se_juntan:
            nuevo_der = intervalo.der if (intervalo.der is not None
                                          and (anterior.der is None
                                               or intervalo.der > anterior.der)) \
                else anterior.der
            fusionados[-1] = Intervalo(anterior.izq, nuevo_der,
                                       anterior.abierto_izq, intervalo.abierto_der)
        else:
            fusionados.append(intervalo)
    return tuple(fusionados)


REALES = Conjunto((Intervalo(None, None),))


def desde_intervalos(intervalos: list[Intervalo], *,
                     mergir_tocados: bool = True) -> Conjunto:
    """A set from a list of intervals, sorted and without overlaps.

    ``mergir_tocados=False`` is what :func:`quita_puntos` needs: ``(a,b)`` and
    ``(b,c)`` touch, but merging them would put ``b`` back into the set — the one
    point the caller just removed.
    """
    return Conjunto(_normaliza(list(intervalos), mergir_tocados=mergir_tocados))


def quita_puntos(conjunto: Conjunto, excluidos: tuple[Punto, ...]) -> Conjunto:
    """``conjunto`` minus the listed points, split into open intervals."""
    piezas: list[Intervalo] = []
    for intervalo in conjunto.intervalos:
        dentro = sorted((p for p in excluidos if intervalo.contiene(p)))
        if not dentro:
            piezas.append(intervalo)
            continue
        izq = intervalo.izq
        for p in dentro:
            if izq is None or izq < p:
                piezas.append(Intervalo(izq, p))
            izq = p
        # the tail after the last removed point; ``der is None`` means +infinity,
        # and breaking out of the loop there used to drop it on the floor
        piezas.append(Intervalo(izq, intervalo.der))
    return desde_intervalos(piezas, mergir_tocados=False)


# ---------------------------------------------------------------------------
# periodic structure
# ---------------------------------------------------------------------------

#: the period of each circular function, in units of pi
PERIODO_FUNCIÓN = {"sin": Fraction(2), "cos": Fraction(2), "tan": Fraction(1),
                   "cot": Fraction(1), "sec": Fraction(2), "csc": Fraction(2)}
PERIODO_HIPERBOLICO = {"sinh": None, "cosh": None, "tanh": None,
                       "coth": None, "sech": None, "csch": None}


def periodo(e: mx.Expr) -> Fraction | None:
    """The period of ``e`` in units of ``pi``, or ``None`` when it has none.

    ``None`` is the honest answer for the hyperbolic functions, and it is the
    answer that matters: ``sinh`` has no real period, so a solver that assumed
    one would emit ``x + 2k·pi`` as a family of solutions to an equation that has
    none (§5.4).

    Products and sums take the *least common* multiple of the periods involved,
    not the smallest one: ``sin(2x)·cos(3x)`` has period ``2pi``, even though
    ``sin(2x)`` alone has period ``pi``.
    """
    for _llamada, funcion in _llamadas(e):
        if funcion in PERIODO_HIPERBOLICO:
            return None
    periodos: list[Fraction] = []
    for llamada, funcion in _llamadas(e):
        p = PERIODO_FUNCIÓN.get(funcion)
        if p is None:
            continue
        escala = _escala_del_argumento(llamada)
        periodos.append(p / abs(escala) if escala else p)
    if not periodos:
        return None
    resultado = periodos[0]
    for p in periodos[1:]:
        resultado = _mcm_racional(resultado, p)
    return resultado


def periodo_minimo(e: mx.Expr, var: str = "x") -> Fraction | None:
    """The *smallest* period, in units of ``pi``, or ``None`` when there is none.

    :func:`periodo` is a sound period but not always the smallest one: it takes
    the least common multiple of the periods of the functions it sees, so
    ``sin(x)^2`` comes out as ``2pi`` when its real period is ``pi``. Reporting a
    valid-but-loose period is not wrong, but it doubles every interval in the
    answer and makes the sign chart twice as long as it needs to be.

    So the candidate is halved for as long as the halved version still holds. The
    check is numeric, at points that avoid the poles, and it is a check in the
    same sense the sign chart is: a period that fails anywhere is rejected, and one
    that survives at many points spread across a period is accepted. The search
    only ever halves, which is enough because trigonometric periods are always a
    power-of-two multiple of the base one.
    """
    candidato = periodo(e)
    if candidato is None:
        return None
    while candidato / 2 > 0:
        mitad = candidato / 2
        if not _es_periodo(e, var, mitad):
            break
        candidato = mitad
    return candidato


def _es_periodo(e: mx.Expr, var: str, periodo_pi: Fraction) -> bool:
    """Whether ``e`` repeats after ``periodo_pi * pi``, checked where it exists."""
    paso = float(periodo_pi) * 3.141592653589793
    for x in _muestras_para_periodo(paso):
        valor = mx.evaluate(e, {var: x})
        if valor is None or abs(valor.imag) > 1e-9:
            continue          # a pole says nothing about the period
        if abs(valor) > 1e12:
            continue          # numerically infinite: the same, one point over
        referencia = mx.evaluate(e, {var: x + paso})
        if referencia is None or abs(referencia.imag) > 1e-9:
            continue
        escala = max(1.0, abs(valor.real))
        if abs(referencia.real - valor.real) > 1e-9 * escala:
            return False
    return True


def _muestras_para_periodo(paso: float) -> list[float]:
    """Points inside one period, away from its ends, deterministic."""
    cuantos = 24
    ancho = paso / 2
    return [ancho * (2 * i + 1) / (2 * cuantos) for i in range(cuantos)]


def _mcm_racional(a: Fraction, b: Fraction) -> Fraction:
    """Least common multiple of two rationals, exact."""
    from math import gcd
    return Fraction((a.numerator * b.numerator) // gcd(a.numerator, b.numerator),
                    gcd(a.denominator, b.denominator))


def _llamadas(e: mx.Expr) -> list[tuple[mx.Expr, str]]:
    salida: list[tuple[mx.Expr, str]] = []
    pila = [e]
    while pila:
        actual = pila.pop()
        if isinstance(actual, mx.Call):
            salida.append((actual, actual.name))
            pila.extend(actual.args)
        elif isinstance(actual, mx.Neg):
            pila.append(actual.arg)
        elif isinstance(actual, mx.Pow):
            pila.extend((actual.base, actual.exponent))
        elif isinstance(actual, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
            pila.extend((actual.left, actual.right))
    return salida


def _escala_del_argumento(llamada: mx.Call) -> Fraction | None:
    """How much the argument is scaled: ``2`` for ``sin(2x)``, ``1/2`` for ``sin(x/2)``.

    ``None`` when the argument is not a plain scaling (``sin(x+3)``, ``sin(y)``),
    because the period does not simply divide there.
    """
    if len(llamada.args) != 1:
        return None
    argumento = llamada.args[0]
    if (isinstance(argumento, mx.Div) and isinstance(argumento.right, mx.Num)
            and argumento.right.value != 0):
        return Fraction(1) / argumento.right.value
    from academic_core.domain.engineering.mathlab.trig import _factores
    coeficiente, _factores_ = _factores(argumento)
    return coeficiente if coeficiente != 1 else None


# ---------------------------------------------------------------------------
# denominators: where the expression stops existing
# ---------------------------------------------------------------------------


def denominadores(e: mx.Expr) -> list[mx.Expr]:
    """Every sub-expression that must not vanish for ``e`` to be defined.

    The arguments of ``ln`` count too, for the same reason: ``ln(0)`` and ``1/0``
    are the same mistake dressed differently, and a domain that reported only the
    quotients would be wrong in a way the student cannot see.

    Radicals do **not** appear here on purpose. ``sqrt(1-x)`` needs ``x <= 1``,
    which is a closed half-line; :class:`Intervalo` is open, because the points
    it removes are exactly the poles. Representing that restriction here would
    mean either lying about the open side or inventing a second interval type,
    so it is left out and said out loud instead (§5.4).
    """
    salida: list[mx.Expr] = []
    pila = [e]
    while pila:
        actual = pila.pop()
        if isinstance(actual, mx.Div):
            salida.append(actual.right)
            pila.extend((actual.left, actual.right))
        elif isinstance(actual, mx.Call):
            if actual.name in {"ln", "log10"} and len(actual.args) == 1:
                salida.append(actual.args[0])
            if actual.name == "log" and len(actual.args) == 2:
                salida.extend(actual.args)
            pila.extend(actual.args)
        elif isinstance(actual, mx.Root):
            pila.append(actual.radicand)
        elif isinstance(actual, mx.Neg):
            pila.append(actual.arg)
        elif isinstance(actual, mx.Pow):
            pila.extend((actual.base, actual.exponent))
        elif isinstance(actual, (mx.Add, mx.Sub, mx.Mul)):
            pila.extend((actual.left, actual.right))
    return salida


def dominio_de(e: mx.Expr, var: str, resolver=None) -> Conjunto:
    """Where ``e`` is defined, as an exact set of intervals.

    ``resolver`` maps a sub-expression to the :class:`Conjunto` where it
    vanishes. Without it only the constant cases are settled and everything else
    is *said* to be unknown rather than guessed — §5.4. That is why this returns
    a set and not a boolean.
    """
    if not mx.depends(e, var):
        return REALES
    if e == mx.ZERO:
        return Conjunto()  # nowhere: the expression is constant and undefined
    if not mx.variables(e):
        return Conjunto() if mx.evaluate(e) is None else REALES
    if resolver is None:
        return REALES
    conjunto = REALES
    for denominador in denominadores(e):
        ceros = resolver(denominador, var)
        if ceros is None or ceros.vacio:
            continue
        conjunto = conjunto.interseccion(ceros.complemento())
    return conjunto


# ---------------------------------------------------------------------------
# sign, the other half of T-13
# ---------------------------------------------------------------------------


def signo_en(e: mx.Expr, var: str, valores: list[float]) -> list[int]:
    """``+1``, ``-1`` or ``0`` at each value, decided numerically.

    A value where the expression is undefined comes back as ``0`` as well: the
    caller cannot tell the two apart from here, and pretending otherwise is how a
    sign chart claims a crossing that is a pole.
    """
    salida: list[int] = []
    for v in valores:
        valor = mx.evaluate(e, {var: v})
        if valor is None:
            salida.append(0)
        elif valor.real > 0:
            salida.append(1)
        elif valor.real < 0:
            salida.append(-1)
        else:
            salida.append(0)
    return salida


def puntos_de_muestra(periodo_pi: Fraction, cuantos: int = MUESTRAS_POR_PERIODO
                      ) -> list[float]:
    """``periodo_pi`` samples spread over one period, in radians."""
    paso = 2 * 3.141592653589793 * float(periodo_pi) / 2
    largo = 2 * 3.141592653589793 * float(periodo_pi)
    inicio = paso / 2
    return [inicio + i * paso for i in range(cuantos) if inicio + i * paso < largo]
