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


def _comparacion_por_valor(a: "Punto", b: "Punto") -> int:
    """Order two points when at least one is an arbitrary exact expression.

    There is no exact order for ``arcsen(1/3)`` against ``pi/2`` without proving
    a transcendence result nobody has written down here, so the comparison is done
    on values and it SAYS so: when the two are within a relative 10⁻¹² of each
    other it refuses, because a wrong order here is a wrong interval and a
    refused order is only an unfinished answer.
    """
    va, vb = a.valor(), b.valor()
    escala = max(1.0, abs(va), abs(vb))
    if va == vb:
        # Equal computed values are the SAME point, and that is decidable — it is
        # the only comparison here that is. A chart asks «is this endpoint the
        # endpoint I already have?» on every critical point, and refusing that
        # question refuses every inequality whose answer has a critical point of
        # its own as a bound, which is most of the ones worth answering.
        return 0
    if abs(va - vb) <= 1e-12 * escala:
        raise invalid(
            "AMBIGUO",
            f"«{a.texto()}» y «{b.texto()}» están a {abs(va - vb):.3g} uno del otro: "
            "su orden no se puede decidir con la precisión necesaria, y un "
            "intervalo con los extremos cambiados es peor que ninguno")
    return (va > vb) - (va < vb)


def _comparacion_exacta(a: "Punto", b: "Punto") -> int:
    """``-1``, ``0`` or ``1`` for ``a`` against ``b``, decided exactly.

    Same kind of point on both sides is rational arithmetic. Across kinds, the
    bracket above decides it; if the bracket straddles, the two are within
    10⁻¹⁵ of each other and a float is honest enough — and it says so.
    """
    if a.expresion is not None or b.expresion is not None:
        return _comparacion_por_valor(a, b)
    if a.es_pi == b.es_pi:
        return (a.coeficiente > b.coeficiente) - (a.coeficiente < b.coeficiente)
    if a.es_pi:
        pi, otro = a.coeficiente, b.coeficiente
        signo = 1
    else:
        pi, otro = b.coeficiente, a.coeficiente
        signo = -1
    if pi == 0:
        # 0·pi and 0 are the SAME point, and two representations of one point
        # that do not know they are one produce an interval «(0, 0)» where there
        # is no interval at all: ln(x) came out as (0,0) ∪ (0,∞) because its
        # lower bound is a plain 0 and the zero it also excludes is a 0·pi.
        if otro == 0:
            return 0
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
    """An exact real point: a rational, a multiple of ``pi``, or an expression.

    The third form is what a point like ``arcsen(1/3)`` needs, and it exists
    because the sign chart used to be able to place a critical point ONLY on the
    grid of multiples of ``pi``. So ``cosec(x)^2 > 9`` — whose zeros are exactly
    those — was refused with «no se saben los ceros» by an engine whose equation
    solver had already written them down as ``arcsen(1/3)``.

    The price is that a point which is neither rational nor a multiple of ``pi``
    cannot be ORDERED exactly, only bracketed. The comparison is honest about
    that: it brackets with the same ``PI_BAJO``/``PI_ALTO`` discipline, and when
    the bracket straddles it says so instead of guessing.
    """

    coeficiente: Fraction = Fraction(0)
    es_pi: bool = False
    expresion: "mx.Expr | None" = None

    @property
    def es_expresion(self) -> bool:
        return self.expresion is not None

    def expr(self) -> mx.Expr:
        if self.expresion is not None:
            return self.expresion
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
        if self.expresion is not None:
            return mx.text(self.expresion)
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
        if self.expresion is not None:
            v = mx.evaluate(self.expresion, {})
            if v is None:
                raise invalid("VALOR", "el punto no se puede evaluar")
            return float(v.real if isinstance(v, complex) else v)
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


def _extremo_mayor(a: Punto | None, abierto_a: bool,
                   b: Punto | None, abierto_b: bool):
    """The larger of two bounds, and whether that bound is open."""
    if a is None:
        return b, abierto_b
    if b is None:
        return a, abierto_a
    if a > b:
        return a, abierto_a
    if b > a:
        return b, abierto_b
    return a, abierto_a and abierto_b          # same point: open only if both are


def _extremo_menor(a: Punto | None, abierto_a: bool,
                   b: Punto | None, abierto_b: bool):
    """The smaller of two bounds, and whether that bound is open."""
    if a is None:
        return b, abierto_b
    if b is None:
        return a, abierto_a
    if a < b:
        return a, abierto_a
    if b < a:
        return b, abierto_b
    return a, abierto_a and abierto_b


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
        # A degenerate closed interval is ONE point, and `[1/2·pi, 1/2·pi]` says
        # something no one wrote on purpose: it reads as a tiny arc when it is a
        # tangency. The set is the same; the answer reads like itself.
        if (self.izq is not None and self.der is not None
                and self.izq == self.der
                and not self.abierto_izq and not self.abierto_der):
            return self.izq.texto()
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
    """A finite union of open intervals, sorted, disjoint and merged.

    ``periodo`` is the one thing here that is not literal, and it exists because a
    set of holes can be INFINITE. ``1/sen(x)`` does not exist at ``0``, ``π``,
    ``2·π`` and every other multiple; describing that as a finite list of holes
    needs the list to be infinite, and a finite list of holes is what this used to
    be. ``dominio()`` found the holes of ONE period —``0`` and ``π``— took them
    out of the whole line, and published ``(-∞, 0) ∪ (0, π) ∪ (π, 2·π) ∪
    (2·π, ∞)`` as if ``3·π`` were in the domain. It is not: asked
    about it the set said yes and the evaluator said ``None``.

    So the period is declared, and it is declared rather than assumed because it is
    known and not chosen: if ``f(x + p) = f(x)`` then the domain of ``f`` is
    ``p``-periodic, so ``periodo_minimo`` of the expression is a period of its
    domain. ``None`` keeps the reading literal, which is what every other use of
    :class:`Conjunto` wants: the sign chart builds one period on purpose and must
    not have it folded underneath it.
    """

    intervalos: tuple[Intervalo, ...] = ()
    periodo: "Fraction | None" = None

    @property
    def vacio(self) -> bool:
        return not any(not i.vacio for i in self.intervalos)

    def contiene(self, p: Punto) -> bool:
        """Whether the point is in the set, folding by the period when there is one.

        Only a multiple of ``pi`` is folded. Every boundary of a periodic hole set
        IS a multiple of ``pi``, so a point that is not one is never one of the
        holes and reading it literally is both exact and the only thing that can
        work — ``periodo`` is in units of ``pi``, and adding ``pi`` to ``3/2`` does
        not give a point of the same lattice.
        """
        _exige_punto(p)
        if self.periodo is not None and p.expresion is None and p.es_pi:
            p = punto_pi(p.coeficiente % self.periodo)
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
        salida = " ∪ ".join(partes)
        # Only when there is something to repeat. `ℝ` already says everything, and
        # `ℝ  y se repite cada 2·π` is noise on a set that needs no
        # explaining — which is most of the sets that have a period, because most
        # expressions with one exist everywhere.
        if self.periodo is not None and not (len(self.intervalos) == 1
                                            and self.intervalos[0].izq is None
                                            and self.intervalos[0].der is None):
            repetido = "π" if self.periodo == 1 else f"{self.periodo}·π"
            salida += f"   y se repite cada {repetido}"
        return salida

    def interseccion(self, otro: "Conjunto") -> "Conjunto":
        """The overlap, with the open/closed flags carried through.

        Dropping them is the trap here. ``[0, pi/2)`` intersected with ``(-inf, 0]``
        is the single point ``0``, and building that as ``Intervalo(0, 0)`` gives an
        empty interval — the answer says nothing is in common when one thing is.

        The flag of an end is the flag of whichever bound wins, and when both sides
        carry the same bound the result is closed only if both are. ``mergir_tocados``
        is off because two pieces that touch at an open end do **not** cover that
        point, and merging them would put it back.
        """
        piezas: list[Intervalo] = []
        for a in self.intervalos:
            for b in otro.intervalos:
                izq, abierto_izq = _extremo_mayor(a.izq, a.abierto_izq,
                                                   b.izq, b.abierto_izq)
                der, abierto_der = _extremo_menor(a.der, a.abierto_der,
                                                   b.der, b.abierto_der)
                intervalo = Intervalo(izq, der, abierto_izq, abierto_der)
                if not intervalo.vacio:
                    piezas.append(intervalo)
        return Conjunto(_normaliza(piezas, mergir_tocados=False))

    def complemento(self) -> "Conjunto":
        """What is left over, and a point removed from a set joins it.

        A set that excludes ``pi/2`` has a complement that includes it, so the gap
        between ``(a, pi/2)`` and ``(pi/2, b)`` is not empty: it is ``pi/2`` alone.
        Writing a degenerate interval for it is the only way to say that, and
        merging afterwards would erase it.
        """
        piezas: list[Intervalo] = []
        anterior: Punto | None = None
        anterior_abierto = True
        for i in self.intervalos:
            if i.izq is None and i.der is None:
                return Conjunto()          # the whole line: nothing is left over
            if i.izq is not None and (anterior is None or i.izq > anterior):
                piezas.append(Intervalo(anterior, i.izq, anterior_abierto,
                                        i.abierto_izq))
            elif anterior is not None and i.izq == anterior \
                    and i.abierto_izq and anterior_abierto:
                piezas.append(Intervalo(i.izq, i.izq, False, False))
            if i.der is None:
                return Conjunto(tuple(piezas))
            anterior = i.der
            anterior_abierto = i.abierto_der
        piezas.append(Intervalo(anterior, None, anterior_abierto, True))
        return Conjunto(_normaliza(piezas, mergir_tocados=False))

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

    Two intervals that touch merge only when the point they share belongs to the
    union: ``[-1, 0] ∪ [0, 1]`` is ``[-1, 1]``. When both ends are open the point
    belongs to neither, and merging would put it back — which is how
    ``(-inf, 0) ∪ (0, inf)`` came out as ``(-inf, 0)``: a set that is not a
    superset of either of its halves and is not the answer to anything.
    """
    def clave(intervalo: Intervalo):
        # an interval without a left bound starts at -infinity and therefore
        # sorts *first*; sorting it last silently reorders the union
        return (0, Punto(Fraction(0))) if intervalo.izq is None \
            else (1, intervalo.izq)

    vivos = sorted((i for i in intervalos if not i.vacio), key=clave)
    # A degenerate interval is a single point, and a single point has no interior
    # to protect: if a neighbour already reaches it, it is covered and keeping
    # both would print «[pi/2, pi/2] ∪ [pi/2, 2pi)» for one set.
    if len(vivos) > 1:
        sin_puntos = set()
        for indice, intervalo in enumerate(vivos):
            if intervalo.izq is None or intervalo.der is None \
                    or intervalo.izq != intervalo.der:
                continue
            vecino = (vivos[indice - 1] if indice > 0 else None,
                      vivos[indice + 1] if indice + 1 < len(vivos) else None)
            if ((vecino[0] is not None and vecino[0].der is not None
                 and vecino[0].der >= intervalo.der)
                    or (vecino[1] is not None and vecino[1].izq is not None
                        and vecino[1].izq <= intervalo.izq)):
                sin_puntos.add(indice)
        if sin_puntos:
            vivos = [i for k, i in enumerate(vivos) if k not in sin_puntos]
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
            # Touching. They merge only when the point they share is INCLUDED:
            # [-1,0] ∪ [0,1] is [-1,1]. When both ends are open the point belongs
            # to neither, and folding them would add it back — (-∞,0) ∪ (0,∞)
            # came out as (-∞,0), which is not a superset of either and is not a
            # set of anything a function's solution would be.
            se_juntan = (mergir_tocados and intervalo.izq == anterior.der
                         and not (intervalo.abierto_izq and anterior.abierto_der))
        if se_juntan:
            # An unbounded end wins over any finite one. Comparing them as if they
            # were ordinary points truncated (-inf, 0] ∪ [0, inf) — which is the
            # whole real line — down to (-inf, 0].
            if intervalo.der is None:
                nuevo_der = None
            elif anterior.der is None or intervalo.der > anterior.der:
                nuevo_der = intervalo.der
            else:
                nuevo_der = anterior.der
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


#: The expression is constant, so every number is a period of it and it puts no
#: constraint on the period of whatever it is added to or multiplied by.
LIBRE = "libre"


def periodo(e: mx.Expr, var: str = "x") -> Fraction | None:
    """The period of ``e`` as a function of ``var``, in units of ``pi``.

    ``None`` is the honest answer for a function that has none, and it is the
    answer that matters. The hyperbolic functions are the obvious case:
    ``sinh`` has no real period, so a solver that assumed one would emit
    ``x + 2k·pi`` as a family of solutions to an equation that has none (§5.4).
    So is a bare ``x``: ``x + sin(x)`` tends to infinity and ``sin(x)/x`` tends to
    zero, and neither is periodic.

    The question is asked of the WHOLE expression and not of the trigonometric
    call inside it. Reading off the first sine found answers ``2·pi`` for
    ``sin(x)/x``, which is not a period of anything: the quotient decays and
    ``f(x + 2pi) ≠ f(x)``. Periodicity survives sums, products and quotients, so
    every part has to be periodic for the whole to be — and one part that is not
    settles the answer on its own.

    Products and sums take the *least common* multiple of the periods involved,
    not the smallest one: ``sin(2x)·cos(3x)`` has period ``2pi``, even though
    ``sin(2x)`` alone has period ``pi``.
    """
    p = _periodo(e, var)
    return None if p is LIBRE else p


def _periodo(e: mx.Expr, var: str):
    """``LIBRE`` for no constraint, ``None`` for aperiodic, else a period."""
    if isinstance(e, (mx.Num, mx.Const)):
        return LIBRE
    if isinstance(e, mx.Sym):
        # x itself is aperiodic; another free symbol is not a function of var
        return None if e.name == var else LIBRE
    if isinstance(e, mx.Neg):
        return _periodo(e.arg, var)
    if isinstance(e, mx.Call):
        return _periodo_de_llamada(e, var)
    if isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        return _combinar(_periodo(e.left, var), _periodo(e.right, var))
    if isinstance(e, mx.Pow):
        # sin(x)^2 is periodic with the period of sin(x); sin(x)^x is not, and
        # the exponent is what tells the two apart
        if mx.variables(e.exponent):
            return None
        return _periodo(e.base, var)
    if isinstance(e, mx.Root):
        return _periodo(e.radicand, var)
    return None


def _periodo_de_llamada(e: mx.Call, var: str):
    """The period of ``f(g(x))``, which is the period of ``g``.

    That sentence is the whole rule, and getting it wrong is what this used to do.
    ``asin`` is not a periodic function, so the code answered «not periodic» and
    stopped — for ``asin(2·sen(x))``, whose domain is exactly as periodic as its
    argument and was published as if it were not. A composition takes the period of
    its INSIDE whatever the outside does: if ``g(x + p) = g(x)`` then
    ``f(g(x + p)) = f(g(x))`` for any ``f`` at all, including ``ln``, ``raiz``,
    ``arcsen``, ``exp`` and the hyperbolic ones, none of which is periodic.

    What is left is the trig case, where the period also depends on HOW the
    argument scales: ``sen(2x)`` has period ``pi`` and ``sen(x)`` has ``2·pi``, both
    from the same inside. So those still read the coefficient.
    """
    if not e.args:
        return None
    # `PERIODO_HIPERBOLICO` no se consulta aquí: `senh(sen(x))` es periódica con
    # periodo 2·pi aunque `senh` no lo sea, y `senh(x)` no lo es. La misma regla de
    # la composición decide los dos, y decidir por el nombre de la función de
    # fuera es lo que hacía que `senh(x)` saliera periódica.
    base = PERIODO_FUNCIÓN.get(e.name)
    if base is None or len(e.args) != 1:
        # not a periodic function in itself, so the period is the argument's — and
        # the extra arguments have to be constants for that to be the whole story
        # (`ln(x, 10)` is `ln(x)` with a base)
        for otro in e.args[1:]:
            if mx.variables(otro, var):
                return None
        return _periodo(e.args[0], var)
    from academic_core.domain.engineering.mathlab.ecuaciones import _afine

    a, _b = _afine(e.args[0], var)
    if a is None or a == 0:
        # a constant argument makes a constant function, and a non-affine one
        # breaks the periodicity: sen(sen(x)) has none
        return LIBRE if not mx.variables(e.args[0]) else None
    return base / abs(a)


def _combinar(a, b):
    """The period of two parts used together: aperiodic absorbs everything."""
    if a is None or b is None:
        return None
    if a is LIBRE:
        return b
    if b is LIBRE:
        return a
    return _mcm_racional(a, b)


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
    # Halved for as long as the halved version holds — but NOT for ever. A
    # Fraction halves to a smaller positive Fraction and never reaches zero, so
    # `while candidato / 2 > 0` never ends for a function that repeats after
    # EVERY shift. `sen(x)^2 + cos(x)^2 - 1/2` is the constant 1/2 written
    # longer, so it repeats after every shift, and the engine hung on it until
    # the process was killed. The bound is the number of calls: each one can at
    # most double the number of halvings that can pay off.
    tope = len(_llamadas(e)) + 1
    for _ in range(tope):
        mitad = candidato / 2
        if not _es_periodo(e, var, mitad):
            return candidato
        candidato = mitad
    # Every halving held, which means no smallest period exists — and a period
    # with no minimum is not a period the sign chart can use. `1 > 1/2` says
    # exactly this; `sen(x)^2 + cos(x)^2 > 1/2` is the same number written
    # longer, so it has to say the same thing.
    return None


def _es_periodo(e: mx.Expr, var: str, periodo_pi: Fraction) -> bool:
    """Whether ``e`` repeats after ``periodo_pi * pi``, checked where it exists.

    Two ways this used to say yes without knowing anything, and both of them
    turned a real period into none.

    **It passed in vacuo.** Every sample that could not be compared was skipped,
    and a check that compared nothing returned ``True``. ``raiz(cos(x))`` is the
    case: half of its values are not real, most samples land there, the ones that
    survive compare fine, and a halved period that is really not one came back
    confirmed — so ``periodo_minimo`` halved ``2·pi`` down to nothing and published
    ``None`` for an expression whose period is ``2·pi``. Fewer than a handful of
    comparisons now means «not proven», and «not proven» is ``False``: the answer
    that keeps the larger candidate, which is still a valid period.

    **It only looked at half a period.** ``_muestras_para_periodo`` returned points
    in ``(0, paso/2)``. Repeating on the first half of a period does not make the
    whole thing a period — the second half is a different claim — so the samples
    now go across all of it.
    """
    paso = float(periodo_pi) * 3.141592653589793
    comparados = 0
    for x in _muestras_para_periodo(paso):
        valor = mx.evaluate(e, {var: x})
        if valor is None or abs(valor.imag) > 1e-9:
            continue          # a pole says nothing about the period
        if abs(valor) > 1e12:
            continue          # numerically infinite: the same, one point over
        referencia = mx.evaluate(e, {var: x + paso})
        if referencia is None or abs(referencia.imag) > 1e-9:
            continue
        comparados += 1
        escala = max(1.0, abs(valor.real))
        if abs(referencia.real - valor.real) > 1e-9 * escala:
            return False
    return comparados >= 4


def _muestras_para_periodo(paso: float) -> list[float]:
    """Points inside one whole period, away from its ends, deterministic.

    The whole period, not the first half: ``f(x + p) = f(x)`` on ``(0, p/2)`` is a
    different claim from the same thing on ``(p/2, p)``, and only the second one
    with the first is a period. Deterministic because a period check that samples
    differently each run cannot fail the same way twice.
    """
    cuantos = 24
    ancho = paso
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
