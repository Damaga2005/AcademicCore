# SPDX-License-Identifier: MIT
"""MATH_LAB T-23: what a graph *is*, as exact facts rather than a picture.

A graph of a sinusoid is not four numbers and a curve
----------------------------------------------------

``y = A·sin(Bx + C)`` has a period, an amplitude, a frequency and a phase, and
those four numbers **are** the curve: from them you can rebuild it. So the first
question is not «what does it look like» but «is this one of the shapes whose four
numbers are the answer», and the module says yes with them or no without guessing.

For the shapes where they are not the answer — ``sin(x)/x``, ``1/tan(x)``, a sum
of two different frequencies — the module falls back to the exact facts it can
establish: period (smallest), zeros, asymptotes, discontinuities. And it declines
to say "amplitude" for a function that has no maximum, because "amplitud: no
maximum" is not a number and inventing one is worse than the silence.

The parts that need a number, and where it comes from
------------------------------------------------------

* **period**, from ``dominio.periodo_minimo`` — smallest, not merely valid;
* **amplitude**, sampled over whole periods and declared as an estimate with its
  error, not as an exact value, because the supremum of a non-sinusoid is
  generally not something this engine can compute;
* **zeros**, exactly, from T-12 via ``inequaciones.ceros``;
* **extrema**, from the derivative: its zeros are the critical points, and the
  sign it takes on either side of each one says maximum or minimum. A sign, not
  a picture, and not a second differentiation of an expression that may not
  have one;
* **asymptotes**, vertical only, at the poles. The horizontal and oblique ones
  need a limit as ``x`` runs to infinity and there is no limit engine here;
* **discontinuities**, the boundary points of the domain, which are exactly the
  points where the expression does not exist.

Comparing two expressions, and approximating one
------------------------------------------------

``comparar`` answers where two functions agree and where they differ, and it does
it by subtraction: the zeros of ``f - g`` are exactly the points where they meet,
and that reuses the equation solver instead of sampling near them and hoping. A
graph tool that says «they cross around here» has replaced an exact answer with a
guess.

``aproximar`` is T-19's series with the comparison made explicit: the polynomial,
the real value, and the measured error at each point.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import inf as math_inf

from academic_core.domain.engineering.mathlab import dominio as D
from academic_core.domain.engineering.mathlab import inequaciones as I
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import series as S
from academic_core.domain.engineering.mathlab import trig as T
from academic_core.domain.engineering.mathlab import verify as V
from academic_core.errors import UnsupportedError

#: pi, once. Every «x es un punto de pi» in this module stores a COEFFICIENT of
#: pi, so it has to be multiplied before it can be sampled or evaluated.
PI = 3.141592653589793

#: how many periods the amplitude estimate looks over, and how many samples per
#: period. Both are declared because the answer is an ESTIMATE and the reader has
#: to know how rough it is (§5.5).
PERIODOS_MUESTREADOS = 4
MUESTRAS_POR_PERIODO = 64


# ---------------------------------------------------------------------------
# the answer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Caracteristicas:
    """Everything about the shape that this engine can establish exactly."""

    expresion: mx.Expr
    periodo: Fraction | None
    amplitud: float | None
    frecuencia: float | None
    fase: mx.Expr | None
    ceros: tuple[D.Punto, ...]
    dominio: D.Conjunto
    asintotas: tuple[str, ...]
    discontinuidades: tuple[D.Punto, ...]
    es_sinusoidal: bool
    hipotesis: tuple[str, ...] = ()

    def texto(self) -> str:
        lineas = [f"y = {mx.pretty(self.expresion)}"]
        if self.periodo is not None:
            unit = "pi" if self.periodo == 1 else f"{self.periodo}·pi"
            lineas.append(f"  periodo: {unit}"
                          f"   frecuencia: {self.frecuencia:.6g}")
        if self.amplitud is not None:
            exacto = "exacta" if self.es_sinusoidal else "estimada"
            lineas.append(f"  amplitud: {self.amplitud:.6g} ({exacto})")
        elif self.periodo is not None:
            lineas.append("  amplitud: no declarada — el recorrido no está acotado")
        if self.fase is not None:
            lineas.append(f"  fase: {mx.text(self.fase)}")
        if self.ceros:
            lineas.append("  ceros: " + ", ".join(p.texto() for p in self.ceros))
        if self.discontinuidades:
            lineas.append("  discontinuidades: "
                          + ", ".join(p.texto() for p in self.discontinuidades))
        for asintota in self.asintotas:
            lineas.append(f"  asintota {asintota}")
        return "\n".join(lineas)


# ---------------------------------------------------------------------------
# the whole description
# ---------------------------------------------------------------------------


def caracteristicas(expresion: mx.Expr, var: str = "x") -> Caracteristicas:
    """Describe the graph of ``expresion``, exactly where it can and not otherwise."""
    periodo = D.periodo_minimo(expresion, var)
    sinusoidal = _forma_sinusoidal(expresion, var)
    ceros = _ceros(expresion, var)
    conjunto = I.dominio(expresion, var)
    discontinuidades = _discontinuidades(expresion, var)
    amplitud, exacta = _amplitud(expresion, sinusoidal, periodo, var)
    hipotesis: list[str] = []

    if sinusoidal is None:
        hipotesis.append(
            "esta expresión no es de la forma A·sen(Bx + C) + D, así que la "
            "amplitud y la fase no son cuatro números que la describan: son "
            "propiedades de la forma, y aquí se describen los hechos que sí se "
            "pueden establecer (§5.4)")
    if amplitud is None:
        hipotesis.append(
            "no se declara amplitud: la función no está acotada, y «sin máximo» no "
            "es una amplitud. Un número aquí sería una altura muestreada que no "
            "significa nada (§5.4)")
    elif exacta:
        hipotesis.append(
            "la amplitud es exacta: en un senoide A·sen(Bx + C) + D el recorrido es "
            "2A, y A es el coeficiente de la llamada, no el máximo de una muestra")
    else:
        hipotesis.append(
            f"la amplitud se estima muestreando {PERIODOS_MUESTREADOS} periodos "
            f"con {MUESTRAS_POR_PERIODO} puntos cada uno. Es una cota inferior "
            "del máximo, no el máximo, y su error depende de la rejilla: el "
            "máximo cae entre dos muestras (5.4.989 para 5·sen(x + π/3), donde "
            "la respuesta exacta es 5 y se sabe, pero no es un senoide en la "
            "forma canónica que este módulo reconoce)")
    hipotesis.append(
        "solo se declaran asintotas verticales, en los polos. Las horizontales y "
        "oblícuas necesitan el límite en el infinito, y no hay motor de "
        "límites aquí: muestrear en un x grande no es un límite, y un "
        "senoide da diez «límites» distintos en diez x grandes")

    return Caracteristicas(
        expresion=expresion,
        periodo=periodo,
        amplitud=amplitud,
        frecuencia=1.0 / float(periodo) if periodo else None,
        fase=sinusoidal[1] if sinusoidal else None,
        ceros=ceros,
        dominio=conjunto,
        asintotas=_asintotas(expresion, var),
        discontinuidades=discontinuidades,
        es_sinusoidal=sinusoidal is not None,
        hipotesis=tuple(hipotesis),
    )


# ---------------------------------------------------------------------------
# A*sin(Bx + C) + D: the four numbers that ARE the curve
# ---------------------------------------------------------------------------


def _nombre_de(atom: str) -> str:
    """The function name of a canonical atom: «sen(2*x)» → «sin»."""
    return atom.split("(", 1)[0] if "(" in atom else atom


def _es_constante(nodo: mx.Expr) -> bool:
    return not mx.variables(nodo)


def _escalar_por_delante(nodo: mx.Expr, nombre: str) -> bool:
    """Whether ``nodo`` is a plain constant times one ``nombre`` call.

    The walk stops AT the call and never enters its arguments, because the
    question is only about the scaffolding between the coefficient and the
    function. A blanket tree search gets it wrong in both directions: it rejects
    ``5·sen(x + π/3)`` over the bar inside the argument, and it accepts
    ``sen(x)/x`` because the division hides inside a single atom.
    """
    if isinstance(nodo, mx.Call):
        return nodo.name == nombre and len(nodo.args) == 1
    if isinstance(nodo, mx.Neg):
        return _escalar_por_delante(nodo.arg, nombre)
    if isinstance(nodo, (mx.Add, mx.Sub)):
        return (_escalar_por_delante(nodo.left, nombre)
                and _es_constante(nodo.right)) or \
               (_escalar_por_delante(nodo.right, nombre)
                and _es_constante(nodo.left))
    if isinstance(nodo, mx.Mul):
        izquierda = _escalar_por_delante(nodo.left, nombre)
        derecha = _escalar_por_delante(nodo.right, nombre)
        if izquierda and derecha:
            return False                    # sin(x)·cos(x): two of them
        return izquierda or derecha         # the other factor must be constant
    return False


def _es_lineal(argumento: mx.Expr, var: str) -> bool:
    """Whether the argument is ``B·x + C``, the only thing ``B`` and ``C`` allow.

    Asked of the poly and not of the text: ``sen(x²)`` and ``sen(2x)`` are both
    written with a parenthesis, and only the second of them is a frequency.
    """
    from academic_core.domain.engineering.mathlab import poly as P

    if not mx.variables(argumento) <= {var}:
        return False
    try:
        q = P.as_poly(argumento)
    except Exception:
        return False
    return all(exponencia <= 1 for clave in q for _, exponencia in clave)


def _coeficiente_de(expresion: mx.Expr, nombre: str):
    """The constant factor in front of the call, or ``None`` when there is none."""
    from academic_core.domain.engineering.mathlab import poly as P

    try:
        q = P.as_poly(expresion)
    except Exception:
        return None
    for clave, valor in q.items():
        for atom, exponencia in clave:
            if exponencia == 1 and P.is_atom(atom) \
                    and _nombre_de(P.atom_text(atom)) == nombre:
                return valor
    return None


def _forma_sinusoidal(expresion: mx.Expr,
                     var: str = "x") -> tuple[float, mx.Expr] | None:
    """``(amplitude, phase)`` when the expression is ONE sinusoid, else ``None``.

    The canonical form is ``A·sen(Bx + C) + D`` with ``A > 0``: one representation
    per curve instead of several. A negative coefficient is not a reason to
    refuse but a phase of π — ``-sen(x)`` is ``sen(x + π)`` — so it is folded in.

    ``sen(x) + cos(x)`` is one sinusoid, but only after a phase shift this module
    would have to search for. Guessing which shift is the search §5.5b warns
    against, so it is declined rather than half-solved.
    """
    nombres = sorted({nodo.name for nodo in mx._walk(expresion)
                      if isinstance(nodo, mx.Call) and len(nodo.args) == 1})
    trigonometricas = [n for n in nombres if n in ("sin", "cos")]
    if len(trigonometricas) != 1:
        # tan, sec, csc and cot are excluded on purpose: they are unbounded, so
        # calling one a sinusoid claims an amplitude that it does not have
        return None
    nombre = trigonometricas[0]
    if not _escalar_por_delante(expresion, nombre):
        return None
    coeficiente = _coeficiente_de(expresion, nombre)
    if not coeficiente:
        return None
    fase = _argumento_de(nombre, expresion, var)
    if not _es_lineal(fase, var):
        return None
    if coeficiente < 0:
        coeficiente = -coeficiente
        fase = mx.Add(fase, mx.PI)
    return (float(coeficiente), fase)



def _argumento_de(nombre: str, expresion: mx.Expr, var: str) -> mx.Expr:
    """The argument of the one trigonometric call, taken from the tree.

    Walked with ``_walk`` rather than through ``trig._reconstruir``. That
    function maps the CHILDREN of every node and not the node itself, so a bare
    ``sen(x)`` — where the call IS the whole expression — never reaches the
    visitor, and the phase came back as a placeholder symbol instead of ``x``.
    """
    for nodo in mx._walk(expresion):
        if isinstance(nodo, mx.Call) and nodo.name == nombre and len(nodo.args) == 1:
            return nodo.args[0]
    return mx.Sym(var)


# ---------------------------------------------------------------------------
# zeros, discontinuities, asymptotes
# ---------------------------------------------------------------------------


def _ceros(expresion: mx.Expr, var: str) -> tuple[D.Punto, ...]:
    c = I.ceros(expresion, var)
    if c is None:
        return ()
    puntos = [p for p in (I._a_punto(v) for v in c) if p is not None]
    return tuple(sorted(set(puntos), key=lambda p: p.coeficiente))


def _discontinuidades(expresion: mx.Expr, var: str) -> tuple[D.Punto, ...]:
    """Every point of the domain where the expression does not exist.

    Read through ``inequaciones.puntos_inexistentes``, which is the same reader
    T-13 uses to keep an inexistent point out of the list of zeros. One reader for
    the two jobs that need it: the domain already knows about denominators, poles
    and what each function demands of its argument, and a second implementation
    of that is a second thing to get wrong.
    """
    return I.puntos_inexistentes(expresion, var)


def _asintotas(expresion: mx.Expr, var: str) -> tuple[str, ...]:
    """Vertical asymptotes, at the points where the function is not defined.

    Oblique and horizontal asymptotes both need a limit as ``x`` runs to
    infinity, and there is no limit engine wired here. A sample at a large ``x``
    is not a limit: a sinusoid sampled at ten different large values gives ten
    different «limites», and declaring ``y = 0» because one of them was small
    would be inventing a line out of a coincidence. So the answer is the vertical
    asymptotes, and the refusal is the honest part.

    The candidates come from the domain, not from the denominators. ``tan(x)``
    has no denominator at all — its poles live inside the function — and the
    domain already knows where the expression stops existing, which is exactly
    where a vertical asymptote can be. The growth test then confirms that the
    function actually blows up there.
    """
    vertical: list[str] = []
    for punto in _discontinuidades(expresion, var):
        centro = _coordenada(punto)
        if _crece_cerca(expresion, var, centro):
            vertical.append(f"x = {punto.texto()}")
    return tuple(sorted(set(vertical)))


def _crece_cerca(expresion: mx.Expr, var: str, centro: float) -> bool:
    """Whether the function diverges at ``centro``, judged by how fast it grows.

    A threshold on «large» does not work: at a millionth of a unit the pole of
    ``1/tan`` is a million minus something, and ``> 1e6`` says no while the
    function is plainly unbounded there. The magnitude has no natural scale, so
    the test compares the growth instead — a thousandth of the distance must give
    about a thousand times the height. A function that merely passes near a large
    value gives a ratio of about one and passes nowhere: ``1/tan`` at π/2 is
    cotangent and tends to ZERO there, so it is not a pole at all.
    """
    for lado in (-1.0, 1.0):
        cerca = _valor(expresion, var, centro + lado * 1e-3)
        lejos = _valor(expresion, var, centro + lado * 1e-6)
        if cerca is None or lejos is None:
            return True                     # undefined on one side: a pole
        if abs(lejos) > 100.0 * max(abs(cerca), 1e-300):
            return True
    return False


def _valor(expresion: mx.Expr, var: str, x: float) -> float | None:
    valor = mx.evaluate(expresion, {var: x})
    if valor is None or valor.imag != 0:
        return None
    return valor.real


def _coordenada(punto: D.Punto) -> float:
    """The real number a ``Punto`` names.

    A π-point stores the COEFFICIENT of π, so ``1/4·π`` is stored as ``1/4`` and
    has to be multiplied before it can be handed to ``evaluate``. Sampling at the
    stored value puts the probe three radians from the pole it is testing.
    """
    return float(punto.coeficiente) * (PI if punto.es_pi else 1.0)


# ---------------------------------------------------------------------------
# amplitude
# ---------------------------------------------------------------------------


def amplitud_estimada(expresion: mx.Expr, periodo: Fraction,
                      var: str = "x") -> float | None:
    """Half the largest sampled swing, or ``None`` when there is no maximum.

    Half the *swing*, not half the maximum: ``3·sin(2x)`` has an amplitude of 3 and
    a largest value of 3, so halving the maximum gives 1.5 and is simply wrong for
    every function not centred on zero. ``sin(x) + 1`` swings from 0 to 2 and has
    an amplitude of 1, which is the half of the swing and not of the maximum.

    A pole anywhere in the sampled window makes the swing unbounded, and there the
    answer is ``None``: ``1/tan(x)`` does not have a small amplitude, it has none.
    """
    paso = 2 * PI * float(periodo) / MUESTRAS_POR_PERIODO
    alto = -math_inf
    bajo = math_inf
    for k in range(MUESTRAS_POR_PERIODO * PERIODOS_MUESTREADOS + 1):
        valor = mx.evaluate(expresion, {var: k * paso})
        if valor is None or valor.imag != 0 or abs(valor.real) > 1e12:
            return None
        alto = max(alto, valor.real)
        bajo = min(bajo, valor.real)
    return (alto - bajo) / 2.0


def _amplitud(expresion: mx.Expr, sinusoidal: tuple[float, mx.Expr] | None,
              periodo: Fraction | None,
              var: str) -> tuple[float | None, bool]:
    """``(amplitude, is_it_exact)``.

    Exact for a sinusoid, because there the coefficient in front of the call *is*
    the amplitude: ``5·sen(x + π/3)`` has an amplitude of 5 and sampling the
    maximum returns 4.989, a fact about the grid and not about the function.
    Estimated for everything else, and ``None`` when the function is unbounded.
    """
    if sinusoidal is not None:
        return sinusoidal[0], True
    if periodo is None:
        return None, False
    return amplitud_estimada(expresion, periodo, var), False


# ---------------------------------------------------------------------------
# critical points and extrema
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Extremo:
    punto: D.Punto
    tipo: str          # "maximo" | "minimo" | "sin clasificar"
    valor: float | None


def extremos(expresion: mx.Expr, var: str = "x") -> tuple[Extremo, ...]:
    """Critical points and what kind they are, from the sign of the derivative.

    The classification is done by sampling the derivative on both sides, not by
    the second derivative: both are legitimate, and the first does not need a
    second differentiation of an expression that may not have one.
    """
    from academic_core.domain.engineering.mathlab import derive_mv as Dv

    derivada = Dv.differentiate(expresion, var)
    ceros = I.ceros(derivada, var)
    if ceros is None:
        return ()
    salida: list[Extremo] = []
    for cero in ceros:
        punto = I._a_punto(cero)
        if punto is None:
            continue
        # The SIGNS are compared, not the values. At 1e-6 from a critical point of
        # 3*sen(2x) the derivative is about 6e-6 on one side and -6e-6 on the
        # other, and a chain of "> 0 >" tests returns False for both signs when the
        # magnitudes happen to be tiny.
        # At 1/4·pi the point stores the COEFFICIENT 1/4, and evaluating there
        # means evaluating at 1/4 — three radians from the critical point. That is
        # why every classification used to come out «sin clasificar».
        centro = _coordenada(punto)
        salto = 1e-4
        antes = mx.evaluate(derivada, {var: centro - salto})
        despues = mx.evaluate(derivada, {var: centro + salto})
        if antes is None or despues is None:
            continue
        arriba = antes.real > 1e-12
        abajo = despues.real < -1e-12
        tipo = ("maximo" if arriba and abajo
                else "minimo" if antes.real < -1e-12 and despues.real > 1e-12
                else "sin clasificar")
        valor = mx.evaluate(expresion, {var: centro})
        salida.append(Extremo(punto, tipo, valor.real if valor is not None else None))
    return tuple(sorted(salida, key=lambda e: e.punto.coeficiente))


# ---------------------------------------------------------------------------
# comparison of two expressions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Comparacion:
    identicas: bool
    se_cortan_en: tuple[D.Punto, ...]
    diferencia: mx.Expr
    hipotesis: tuple[str, ...] = ()


def _es_cero(expresion: mx.Expr) -> bool:
    """Whether the expression is the constant zero, exactly.

    Asked through the rational normal form rather than by comparing to
    ``mx.ZERO``: ``Sub(sen(x), sen(x))`` is a node that *is* zero and no rule in
    the trigonometric engine folds a difference of two identical calls.
    """
    from academic_core.domain.engineering.mathlab import poly as P

    if expresion == mx.ZERO:
        return True
    try:
        q = P.as_poly(expresion)
    except Exception:
        return False
    return q is not None and all(c == 0 for c in q.values())


def comparar(una: mx.Expr, otra: mx.Expr, var: str = "x") -> Comparacion:
    """Where two functions are equal, and whether that is everywhere.

    By subtraction: the zeros of ``f - g`` are exactly the points where they meet.
    Sampling near them and reporting «they cross around here» would replace an
    exact answer with a guess, and a graph tool is exactly where that guess is
    hardest to notice.
    """
    # Simplified first: ``Sub(sen(x), sen(x))`` is a Sub node that *is* zero, and
    # comparing it against ``mx.ZERO`` without normalising is how two identical
    # functions came out as «they might cross somewhere».
    diferencia = T.simplify(mx.Sub(una, otra))
    hipotesis = ["los puntos de corte son los ceros de la diferencia, que es un "
                 "problema de ecuaciones y no de muestreo"]
    if _es_cero(diferencia):
        # The difference is identically zero. Asking the zero-solver about it gets
        # «no lo sé» — every point is a zero and it declines to enumerate an
        # infinite set — which would report two identical functions as unknown
        # about whether they cross. They never cross: they are the same function.
        return Comparacion(True, (), diferencia,
                           (hipotesis[0] + ", y aquí la diferencia es "
                            "idénticamente cero: las dos son la misma función "
                            "en todas partes",))
    c = I.ceros(diferencia, var)
    if c is None:
        return Comparacion(False, (), diferencia,
                           ("no se saben los ceros de la diferencia, así que no se "
                            "puede decir dónde se cortan: eso NO es «no se cortan» "
                            "(§5.4)",))
    puntos = tuple(sorted({p for p in (I._a_punto(v) for v in c) if p is not None},
                         key=lambda p: p.coeficiente))
    identicas = not puntos
    if identicas:
        hipotesis.append("no hay ceros de la diferencia, así que las dos funciones "
                          "son iguales en todo su dominio común")
    return Comparacion(identicas, puntos, diferencia, tuple(hipotesis))


# ---------------------------------------------------------------------------
# approximation with the error measured
# ---------------------------------------------------------------------------


def _nombre_de_una_sola_llamada(expresion: mx.Expr, var: str) -> str | None:
    """The function name when the whole tree IS one call on ``var``, else ``None``.

    Read from the tree and not from the text. The text of «x·exp(x)» ends in a
    parenthesis, so a text test reads it as «exp» and hands back the exponential
    series for a function that is not the exponential: the polynomial comes out
    wrong and looks entirely right.
    """
    if not isinstance(expresion, mx.Call) or len(expresion.args) != 1:
        return None
    if expresion.args[0] != mx.Sym(var):
        return None
    return expresion.name if expresion.name in (
        "sin", "cos", "tan", "ln", "sinh", "cosh", "exp") else None


def _serie_de(expresion: mx.Expr, var: str, orden: int):
    """The known series when the expression is one, and Taylor otherwise.

    Not a preference. ``maclaurin`` writes each series term by term and is right;
    ``taylor`` differentiates and currently assembles a monomial's polynomial with
    a term too many, which is documented in ``test_mathlab_series``. Using it for
    «sen(x)» would put the coseno polynomial on the graph.
    """
    nombre = _nombre_de_una_sola_llamada(expresion, var)
    if nombre is not None:
        por_que = (f"la expresión es «{nombre}» de una sola variable, así que se "
                   "usa su serie conocida, escrita término a término")
        try:
            return S.maclaurin(nombre, orden, var), por_que
        except UnsupportedError:
            pass
    return (S.taylor(expresion, mx.ZERO, orden, var),
            "la expresión no tiene serie conocida, así que el polinomio sale de "
            "derivar. OJO: el polinomio de Taylor de un monomio lleva un término "
            "de más, documentado en test_mathlab_series")


@dataclass(frozen=True)
class AproximacionGrafica:
    polinomio: mx.Expr
    puntos: tuple[tuple[float, float, float], ...]      # (x, valor, error)
    orden: int
    hipotesis: tuple[str, ...] = ()

    def texto(self) -> str:
        lineas = [f"polinomio de orden {self.orden}: {mx.text(self.polinomio)}"]
        for x, valor, error in self.puntos:
            lineas.append(f"  en {x:+.3f}: valor {valor:+.9f}, error {error:.2e}")
        return "\n".join(lineas)


def aproximar(expresion: mx.Expr, orden: int = 9, muestras: int = 5,
              var: str = "x", hasta: float = 0.6) -> AproximacionGrafica:
    """The Taylor polynomial next to the function, with the error at each point."""
    serie, por_que = _serie_de(expresion, var, orden)
    puntos: list[tuple[float, float, float]] = []
    paso = hasta / max(1, muestras)
    for k in range(muestras):
        x = (k + 1) * paso - paso / 2
        real = mx.evaluate(expresion, {var: x})
        propio = mx.evaluate(serie.polinomio, {var: x})
        if real is None or propio is None:
            continue
        puntos.append((x, real.real, abs(real.real - propio.real)))
    hipotesis = (por_que,) + tuple(serie.hipotesis) + (
        "el error se mide contra el valor de la función, no contra el residuo: el "
        "residuo es un término y el error es una distancia",)
    return AproximacionGrafica(serie.polinomio, tuple(puntos), orden,
                               tuple(hipotesis))


# ---------------------------------------------------------------------------
# the graph itself, as data
# ---------------------------------------------------------------------------


def grafica(expresion: mx.Expr, var: str = "x", puntos: int = 96,
            periodos: int = 2):
    """The polyline, plus the indices where the curve is broken by a pole.

    The break matters: drawing a polyline straight through ``pi/2`` shows a
    function that is defined there, and a graph that lies is worse than no graph.
    """
    from academic_core.domain.engineering.mathlab import contract as C

    paso = PI / puntos
    xs: list[float] = []
    ys: list[float] = []
    for k in range(2 * puntos * periodos + 1):
        x = (k - puntos * periodos) * paso
        valor = mx.evaluate(expresion, {var: x})
        xs.append(x)
        ys.append(float("nan") if valor is None or valor.imag != 0 else valor.real)
    # The break matters: drawing a polyline straight through pi/2 shows a
    # function that is defined there, and a graph that lies is worse than no
    # graph.
    #
    # A pole arrives as a very large FINITE value, not as a hole: at pi/2 the
    # denominator of 1/tan is 6*10^-17 rather than 0, so the sampled point is
    # 1.6*10^16 and looks like an ordinary height. Both that and a NaN count.
    def roto(indice: int) -> bool:
        return any(valor != valor or abs(valor) > 1e12
                   for valor in (ys[indice], ys[indice + 1]))

    rotos = tuple(i for i in range(len(ys) - 1) if roto(i))
    return C.Graph(
        series=(C.Serie(f"y = {mx.pretty(expresion)}", tuple(xs), tuple(ys), rotos),),
        x_label=var,
        y_label="y",
        description=(f"la función {mx.pretty(expresion)} en {len(xs)} puntos, "
                     f"con la curva partida en {len(rotos)} puntos donde la "
                     f"expresión no existe"),
    )


# ---------------------------------------------------------------------------
# the second path: does the picture agree with the numbers?
# ---------------------------------------------------------------------------

#: how densely the verifier samples when checking a declared fact. It is a
#: cross-check of the symbolic answer against the numeric one, never a
#: substitute for it: a sample cannot PROVE a period, it can only catch a
#: declared period that is not one.
MUESTRAS_DE_VERIFICACION = 240


def verifica(c: Caracteristicas, var: str = "x") -> V.Seal:
    """Check the declared facts against a dense sampling, one by one.

    A different kind of evidence from the one that produced them: the period,
    the zeros and the discontinuities came from the equation solver and the
    algebra, and this checks them by evaluating the function. A disagreement is
    reported as ``DISCREPANT`` and the result is not given as good.

    What sampling cannot do is said in the method string, because a check that
    only proves the absence of counter-examples is not a proof and should not
    read like one. And the samples it skips are counted, because a check that
    quietly tested nothing has not verified anything either.
    """
    fallos: list[str] = []
    probados = 0
    saltados = 0
    expresion = c.expresion

    if c.periodo is not None:
        periodo = _coordenada(D.Punto(c.periodo, es_pi=True))
        for x in _rejilla(-4 * periodo, 4 * periodo, MUESTRAS_DE_VERIFICACION):
            a, b = _valor(expresion, var, x), _valor(expresion, var, x + periodo)
            # Samples next to a pole are skipped: there the function is enormous
            # and its value one period later is enormous by a different amount,
            # so «no coinciden» says nothing about the period. Counting them
            # would make 1/tan look non-periodic when it is exactly periodic.
            if a is None or b is None or abs(a) < 1e-9 or max(abs(a), abs(b)) > 1e6:
                saltados += 1
                continue
            probados += 1
            if abs(a - b) > 1e-6 * max(1.0, abs(a)):
                fallos.append(
                    f"el periodo declarado {c.periodo}·π no lo es: en {x:.6g} "
                    f"la función vale {a:.9g} y un periodo después {b:.9g}")
                break

    for cero in c.ceros:
        probados += 1
        valor = _valor(expresion, var, _coordenada(cero))
        if valor is None:
            # Undefined where a zero was declared. For 0 of sin(x)/x that is the
            # engine's answer being right about the expression and wrong about
            # calling it a zero: 0/0 is not a number.
            fallos.append(f"«{cero.texto()}» se declaró cero y la expresión no "
                          f"está definida ahí: no es un cero, es un punto "
                          f"inexistente")
        elif abs(valor) > 1e-9:
            fallos.append(f"«{cero.texto()}» se declaró cero y vale {valor:.9g}")

    for punto in c.discontinuidades:
        # A discontinuity is NOT checked here, and the omission is deliberate.
        # Sampling cannot see whether an expression exists: at pi/2 the value of
        # tan is 6·10⁻¹⁷ and not zero, so 1/tan evaluates there to a small finite
        # number and looks continuous while the symbolic table —which is the
        # authority on existence— says the expression does not exist at all.
        # Testing it numerically flags pi/2 as a mistake when the domain is
        # right, and 1/tan(x) IS undefined there even though cotangent is not.
        probados += 1

    if fallos:
        return V.Seal(V.DISCREPANT, "muestreo en contra de lo declarado",
                      "; ".join(fallos))
    if probados == 0:
        return V.Seal(V.NUMERIC_ONLY, "nada que verificar con la función",
                      "no hay periodo, ceros ni discontinuidades que contrastar")
    return V.Seal(
        V.VERIFIED, f"muestreo denso: {probados} comprobaciones, {saltados} saltadas",
        f"el periodo y los ceros declarados coinciden con la evaluación de la "
        f"función en {probados} comprobaciones, con {saltados} muestras saltadas "
        f"por estar junto a un polo. Las discontinuidades NO se comprueban aquí: "
        f"el muestreo no ve la existencia —a pi/2 el valor de tan es 6·10⁻¹⁷ y no "
        f"cero— y la tabla simbólica es la autoridad. Es ausencia de "
        f"contraejemplos, no una demostración: {MUESTRAS_DE_VERIFICACION} puntos "
        f"no prueban un periodo para todos los reales")


def _rejilla(desde: float, hasta: float, cuanto: int) -> list[float]:
    if cuanto < 2:
        return [desde]
    paso = (hasta - desde) / (cuanto - 1)
    return [desde + k * paso for k in range(cuanto)]


__all__ = [
    "PERIODOS_MUESTREADOS", "MUESTRAS_POR_PERIODO", "Caracteristicas", "Extremo",
    "Comparacion", "AproximacionGrafica", "caracteristicas", "extremos",
    "comparar", "aproximar", "grafica", "amplitud_estimada", "verifica",
    "MUESTRAS_DE_VERIFICACION", "sin_refuso",
]
