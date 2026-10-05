# SPDX-License-Identifier: MIT
"""MATH_LAB T-01 (angle units, quadrants) and T-19 (series)."""

from __future__ import annotations

import math
from fractions import Fraction as Fr

import pytest

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import series as S
from academic_core.domain.engineering.mathlab import trig as T
from academic_core.errors import UnsupportedError

PI = math.pi


# ---------------------------------------------------------------------------
# T-01: units of angle
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("valor,unidad,radianes", [
    (180, "deg", Fr(1)),
    (90, "deg", Fr(1, 2)),
    (30, "deg", Fr(1, 6)),
    (45, "deg", Fr(1, 4)),
    (400, "grad", Fr(2)),
    (100, "grad", Fr(1, 2)),
    (1, "turn", Fr(1, 2)),
    (2, "turn", Fr(1)),
    (1, "rad", Fr(1)),
])
def test_las_unidades_de_angulo_son_la_misma_racion_exacta(valor, unidad, radianes):
    assert T.a_radianes(Fr(valor), unidad) == radianes


@pytest.mark.parametrize("unidad", ["rad", "deg", "grad", "turn"])
def test_la_conversion_por_ida_y_vuelta_es_la_identidad(unidad):
    for valor in (0, 1, 7, 90, 180, 360):
        radianes = T.a_radianes(Fr(valor), unidad)
        assert T.de_radianes(radianes, unidad) == Fr(valor), (valor, unidad)


def test_una_unidad_desconocida_se_rechaza_diciendo_cuales_hay():
    with pytest.raises(UnsupportedError) as exc:
        T.a_radianes(Fr(1), "radianes")
    assert "deg" in str(exc.value)


def test_treinta_grados_es_un_sexto_de_pi_y_no_un_decimal():
    """The point of keeping degrees in rational arithmetic.

    ``sin(30 grados)`` is 1/2 exactly. Through a float it is 0.49999999999999994,
    and every comparison afterwards inherits the error.
    """
    medio_pi = mx.Mul(mx.Num(T.a_radianes(Fr(30), "deg")), mx.PI)
    assert mx.text(T.simplify(mx.Call("sin", (medio_pi,)))) == "1/2"


# ---------------------------------------------------------------------------
# T-01: quadrants
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("k,cuadrante", [
    (Fr(1, 4), 1), (Fr(3, 4), 2), (Fr(5, 4), 3), (Fr(7, 4), 4),
    (Fr(9, 4), 1), (Fr(11, 4), 2), (Fr(13, 4), 3), (Fr(15, 4), 4),
])
def test_cada_cuadrante_se_reconoce(k, cuadrante):
    assert T.cuadrante(k) == cuadrante


@pytest.mark.parametrize("k", [Fr(0), Fr(1, 2), Fr(1), Fr(3, 2), Fr(2)])
def test_los_ejes_no_tienen_cuadrante(k):
    """0, pi/2, pi and 3pi/2 are the four angles a sign chart is full of.

    Returning a quadrant for one of them gives a sign, and the sign would be
    false: there is a whole half-line of answers it cannot distinguish.
    """
    with pytest.raises(UnsupportedError) as exc:
        T.cuadrante(k)
    assert "eje" in str(exc.value)


@pytest.mark.parametrize("k,seno,coseno", [
    (Fr(1, 4), "+", "+"), (Fr(3, 4), "+", "-"),
    (Fr(5, 4), "-", "-"), (Fr(7, 4), "-", "+"),
])
def test_los_signos_por_cuadrante(k, seno, coseno):
    assert T.signos_en_cuadrantes(k) == (seno, coseno)


@pytest.mark.parametrize("k", [Fr(1, 4), Fr(3, 4), Fr(5, 4), Fr(7, 4)])
def test_los_signos_por_cuadrante_coinciden_con_el_valor_real(k):
    import cmath

    seno, coseno = T.signos_en_cuadrantes(k)
    z = cmath.exp(1j * float(k) * PI)
    assert (seno == "+") == (z.imag > 0)
    assert (coseno == "+") == (z.real > 0)


# ---------------------------------------------------------------------------
# T-01: quadrant reduction keeps the sign
# ---------------------------------------------------------------------------


REDUCCIONES = [
    ("sin(200*pi/180)", "-sin(8/9*pi)"),
    ("sin(7*pi/6)", "-sin(5/6*pi)"),
    ("cos(4*pi/3)", "cos(2/3*pi)"),
    ("sin(-pi/6)", "-sin(1/6*pi)"),
    ("sin(11*pi/6)", "-sin(1/6*pi)"),
]


@pytest.mark.parametrize("original,esperado", REDUCCIONES)
def test_la_reduccion_por_cuadrantes_conserva_el_signo(original, esperado):
    """sin(200 grados) is -sin(8pi/9) and not sin(8pi/9).

    Dropping the sign is the classic error, and it produces an answer that is
    right on half the circle.
    """
    assert mx.text(T.reduccion_por_cuadrantes(mx.parse(original))) == esperado


@pytest.mark.parametrize("original,_esperado", REDUCCIONES)
def test_la_reduccion_no_cambia_el_valor_ni_un_solo_punto(original, _esperado):
    reducido = T.reduccion_por_cuadrantes(mx.parse(original))
    for x in (0.3, 1.7, -2.2, 4.9):
        antes = mx.evaluate(mx.parse(original), {"x": x})
        despues = mx.evaluate(reducido, {"x": x})
        assert abs(antes - despues) < 1e-12, (original, x)


def test_la_reduccion_no_toca_lo_que_no_uede_reducirse():
    for texto in ("sin(x)", "sin(2*x)", "sin(x) + cos(x)", "cos(2*pi + 0.7)"):
        reducido = T.reduccion_por_cuadrantes(mx.parse(texto))
        for x in (0.4, 2.1):
            assert abs(mx.evaluate(mx.parse(texto), {"x": x})
                       - mx.evaluate(reducido, {"x": x})) < 1e-12, texto


# ---------------------------------------------------------------------------
# T-19: the series themselves
# ---------------------------------------------------------------------------


SERIES_CONOCIDAS = ["sin", "cos", "exp", "tan", "ln", "sinh", "cosh"]


@pytest.mark.parametrize("nombre", SERIES_CONOCIDAS)
def test_cada_serie_conocida_tiene_terminos_exactos(nombre):
    serie = S.maclaurin(nombre, 7)
    assert serie.polinomio is not None
    assert serie.residuo is not None
    texto = serie.texto()
    assert "." not in texto.split("...")[0], texto


@pytest.mark.parametrize("nombre,esperado", [
    ("sin", "x + -1/6*x^3 + 1/120*x^5 + -1/5040*x^7"),
    ("sinh", "x + 1/6*x^3 + 1/120*x^5 + 1/5040*x^7"),
])
def test_sen_y_senh_coinciden_hasta_el_quinto_termino_y_no_mas(nombre, esperado):
    """cosh and cos differ at the second term; sin and sinh at the third.

    Reading all four off one table of «odd and alternating» gave them the same
    polynomial, and a coseno series that starts at x is not a series of anything.
    """
    assert mx.text(S.maclaurin(nombre, 7).polinomio) == esperado


def test_cos_y_cosh_empiezan_en_el_termino_constante():
    coseno = mx.text(S.maclaurin("cos", 7).polinomio)
    cosh = mx.text(S.maclaurin("cosh", 7).polinomio)
    for serie in (coseno, cosh):
        assert "x^3" not in serie, serie          # no odd powers at all
        assert "1/24*x^4" in serie, serie
    # and the difference between them is the sign of every non-constant term
    assert "-1/2*x^2" in coseno and "1/2*x^2" in cosh
    assert "-1/720*x^6" in coseno and "1/720*x^6" in cosh


def test_los_numeros_tangentes_son_los_conocidos():
    """x + x^3/3 + 2x^5/15 + 17x^7/315 + 62x^9/2835.

    Two earlier indexings of the convolution gave a series of x alone and then
    x + x^5/5 + 2x^9/45: right shape, wrong numbers, and an error of 2.6e-3 at
    x = 0.2 with thirteen terms, which looks believable until you check it.
    """
    texto = mx.text(S.maclaurin("tan", 9).polinomio)
    for coeficiente in ("1/3*x^3", "2/15*x^5", "17/315*x^7", "62/2835*x^9"):
        assert coeficiente in texto, texto


def test_la_serie_de_logaritmo_es_la_de_logaritmo_de_uno_mas_x():
    """ln(1 + x) = x - x^2/2 + x^3/3 - ...: not the series of ln(x)."""
    texto = mx.text(S.maclaurin("ln", 5).polinomio)
    assert texto == "x + -1/2*x^2 + 1/3*x^3 + -1/4*x^4 + 1/5*x^5"


# ---------------------------------------------------------------------------
# T-19: the approximation is checked against the function
# ---------------------------------------------------------------------------


VALORES_REALES = {"sin": math.sin, "cos": math.cos, "exp": math.exp,
                  "tan": math.tan, "sinh": math.sinh, "cosh": math.cosh}


#: Where each declared bound is claimed to hold, and inside those claims the points
#: that broke the previous rule.
#:
#: The negatives are the load-bearing entries. Both failures of the old "first
#: omitted term" bound were on ``x < 0``, where a series that alternates for
#: positive arguments stops alternating: at ``x = -0.9`` every term of Mercator is
#: negative, the tail is monotone, and a first omitted term is a floor, not a
#: ceiling.
PUNTOS_DE_COTA = {
    "sin": (-9.0, -3.0, -0.5, 0.2, 1.0, 3.0, 9.0),
    "cos": (-9.0, -3.0, -0.5, 0.2, 1.0, 3.0, 9.0),
    "exp": (-6.0, -1.0, -0.2, 0.3, 1.0, 4.0),
    "sinh": (-6.0, -1.0, -0.2, 0.3, 1.0, 4.0),
    "cosh": (-6.0, -1.0, -0.2, 0.3, 1.0, 4.0),
    # tan's bound is declared for |x| < sqrt(2), which is inside its radius pi/2
    "tan": (-1.2, -0.6, -0.1, 0.2, 0.7, 1.3),
    # ln's for |x| < 1, and 0.9 is the far end of that: at 1 the majorisation
    # diverges, which test_la_cota_de_ln_no_es_un_numero_en_el_borde_de_su_dominio
    # pins down rather than hides
    "ln": (-0.9, -0.5, -0.1, 0.3, 0.9),
}


@pytest.mark.parametrize("nombre", ["sin", "cos", "exp", "tan"])
@pytest.mark.parametrize("orden", [7, 11, 15, 19])
def test_mas_terminos_significa_un_error_menor(nombre, orden):
    """The property that makes a series worth having.

    Monotone in the order, and not merely "an error that happens to be small":
    halving the step has to halve the error, or the series is not converging.
    """
    serie = S.maclaurin(nombre, orden)
    real = VALORES_REALES[nombre]
    con_menos = [(abs(real(x) - mx.evaluate(serie.polinomio, {"x": x}).real), x)
                 for x in (0.3, 0.7)]
    con_mas = [(abs(real(x) - mx.evaluate(S.maclaurin(nombre, orden + 4).polinomio,
                                         {"x": x}).real), x)
               for x in (0.3, 0.7)]
    for (menor, x), (mayor, _) in zip(con_menos, con_mas):
        assert menor >= mayor - 1e-18, (nombre, orden, x, menor, mayor)


@pytest.mark.parametrize("nombre", ["sin", "cos", "tan"])
def test_la_serie_aproxima_en_todo_su_radio(nombre):
    """sin and cos converge everywhere; tan has radius pi/2.

    Checking only near the origin would miss a radius stated too generously, and
    a radius stated too generously is how a series gets used outside itself.
    """
    real = VALORES_REALES[nombre]
    for x in (0.2, 1.0, 2.0):
        if nombre == "tan" and abs(x) >= PI / 2:
            # fuera del radio de convergencia la serie no converge, y eso es un
            # dato sobre la serie, no un fallo del motor
            continue
        # 25 terms of the tangent series at x = 1 land near 1e-5, not 1e-9: its
        # radius is pi/2 and it converges slowly near the edge of it. The claim
        # being made is «it converges», not «to a tolerance the test invented».
        serie = S.maclaurin(nombre, 25)
        propio = mx.evaluate(serie.polinomio, {"x": x}).real
        assert abs(real(x) - propio) < 1e-4, (nombre, x)


def test_la_convergencia_se_declara_y_no_se_infiere_del_truncamiento():
    """A truncated series never fails; it just gets worse.

    ``tan`` and ``ln`` have radius 1, and the hypothesis says so, because
    divergence is not something truncation can detect.
    """
    for nombre in ("tan", "ln"):
        serie = S.maclaurin(nombre, 7)
        assert any("radio de convergencia" in h for h in serie.hipotesis), nombre


def test_una_serie_desconocida_se_rechaza_diciendo_que_no_converge():
    with pytest.raises(UnsupportedError) as exc:
        S.maclaurin("bessel", 3)
    assert "NO es «no converge»" in str(exc.value)


def test_un_orden_absurdo_se_rechaza_antes_de_calcular():
    with pytest.raises(UnsupportedError) as exc:
        S.maclaurin("sin", 5000)
    assert "máximo" in str(exc.value)


def test_un_orden_negativo_se_rechaza():
    with pytest.raises(UnsupportedError):
        S.maclaurin("sin", -1)


# ---------------------------------------------------------------------------
# T-19: the remainder, which is the whole point
# ---------------------------------------------------------------------------


def test_la_respuesta_trae_residuo_y_lo_dice():
    serie = S.maclaurin("sin", 5)
    assert serie.residuo is not None
    assert "..." in serie.texto()


@pytest.mark.parametrize("nombre", ["sin", "cos", "exp", "sinh", "cosh", "tan", "ln"])
def test_la_cota_declarada_acota_el_error_real(nombre):
    """``|exacta - polinomio| <= cota`` — measured, on both signs.

    This is the test T-19 was missing. The old one asserted that the first omitted
    term is a bound for three functions and that four others declare none, and both
    halves were wrong on the negative axis:

    * the alternating estimate needs the terms to DECREASE, and ``x^9/9!`` stops
      decreasing past ``x ~ 8``, so for a large argument the declared ``cota`` was
      smaller than the error while still being printed as an upper bound;
    * ``ln``'s series alternates only for ``x > 0``. At ``x < 0`` every term is
      negative, the tail is monotone, and the first omitted term is a *lower* bound
      on it — at ``x = -0.9``, order 5, the module declared ``0.0886`` for an error
      of ``0.4725``.

    Sampling only positive ``x`` is what hid both. Every point below is chosen to
    include the negatives that broke the previous rule.
    """
    serie = S.maclaurin(nombre, 9)
    assert serie.cota is not None, nombre
    for x in PUNTOS_DE_COTA[nombre]:
        propio = mx.evaluate(serie.polinomio, {"x": x}).real
        cota = abs(mx.evaluate(serie.cota, {"x": x}).real)
        # the Maclaurin series of ln is the one of ln(1 + x): comparing it against
        # log(x) is comparing against a different function, and the "failure" would
        # have been the test's, not the series'
        exacto = math.log(1 + x) if nombre == "ln" else VALORES_REALES[nombre](x)
        assert abs(exacto - propio) <= cota + 1e-15, (nombre, x, exacto, propio, cota)


def test_la_cota_no_es_una_cota_vacia():
    """A bound that is 10^30 times the error bounds as well as one that is.

    This is the difference between an estimate a reader can use and a shrug that
    technically satisfies ``error <= cota``. The factor is loose on purpose; the
    point is that the bound tracks the error rather than merely exceeding it.
    """
    for nombre, puntos in PUNTOS_DE_COTA.items():
        serie = S.maclaurin(nombre, 11)
        for x in puntos:
            propio = mx.evaluate(serie.polinomio, {"x": x}).real
            exacto = math.log(1 + x) if nombre == "ln" else VALORES_REALES[nombre](x)
            error = abs(exacto - propio)
            cota = abs(mx.evaluate(serie.cota, {"x": x}).real)
            assert error == 0 or cota < 1e6 * error + 1e-12, (nombre, x, error, cota)


def test_las_siete_series_declaran_cota_y_dicen_donde_vale():
    """No function is left without one, and none travels without its domain.

    The absence of a bound was never the honest answer here — it was the absence of
    the argument. What is honest is refusing when the argument does not exist, which
    is what ``taylor`` still does for an expression it cannot recognise.
    """
    for nombre in PUNTOS_DE_COTA:
        serie = S.maclaurin(nombre, 7)
        assert serie.cota is not None, nombre
        dominios = [h for h in serie.hipotesis if "cota de error:" in h]
        assert dominios, (nombre, serie.hipotesis)
        # the domain sentence must name how the bound was built, not only that it
        # exists: a reader who cannot see the argument has to take the number on faith
        assert "progresión geométrica" in dominios[0], (nombre, dominios[0])


def test_la_cota_de_ln_no_es_un_numero_en_el_borde_de_su_dominio():
    """``|x| = 1`` is outside ``ln``'s declared domain, and the expression says so.

    The absolute majorisation of the Mercator tail is ``|x|^m/(m·(1 - |x|))``, which
    diverges as ``|x| → 1``: at the boundary the tail still converges but so slowly
    that no geometric bound is finite. So the bound is undefined exactly where its
    declared domain stops, and that is the honest shape of the thing — the previous
    rule covered ``x = 1`` and got ``x < 0`` wrong, which is the worse trade.
    """
    serie = S.maclaurin("ln", 7)
    assert any("|x| < 1" in h for h in serie.hipotesis), serie.hipotesis
    assert mx.evaluate(serie.cota, {"x": 1.0}) is None
    assert mx.evaluate(serie.cota, {"x": -1.0}) is None
    # and just inside the edge it is a number again
    assert mx.evaluate(serie.cota, {"x": 0.99}) is not None


def test_taylor_de_una_funcion_conocida_ya_declara_cota():
    """``taylor(exp(x), 0, 6)`` used to refuse a bound its own tail could bound.

    The series of ``f`` about ``a`` is the series of ``u ↦ f(a + u)`` about the
    origin, so the bound is built at 0 and the variable is replaced by ``x - a``.
    For ``a = 0`` that is the same expression ``maclaurin`` produces.
    """
    serie = S.taylor(mx.parse("exp(x)"), mx.ZERO, 6)
    assert serie.cota is not None
    assert any("cota de error" in h for h in serie.hipotesis)
    for x in (0.1, 0.5, 1.0, 2.0, -0.5, -1.5):
        propio = mx.evaluate(serie.polinomio, {"x": x}).real
        cota = abs(mx.evaluate(serie.cota, {"x": x}).real)
        assert abs(math.exp(x) - propio) <= cota + 1e-15, (x, propio, cota)


def test_la_serie_desplazada_coincide_con_la_cota_desplazada():
    """``_cota_de_taylor`` is the specification, and the engine is measured on it.

    That helper is no longer called by ``taylor`` — once a known function is written
    instead of derived, every ``taylor`` call it could have answered is answered
    earlier. It is kept as the statement of what a shift does to a bound, and this
    is what stops it from quietly becoming a second, divergent truth.
    """
    for nombre in ("sin", "cos", "tan", "exp", "sinh", "cosh"):
        nodo = mx.Call(nombre, (mx.Sym("x"),))
        for orden in (5, 9, 15):
            serie = S.taylor(nodo, 0, orden, "x")
            assert mx.text(serie.cota) == mx.text(S._cota_de_taylor(nodo, orden, mx.ZERO, "x"))
    # and the shifted case, which is the one the specification exists for
    nodo = mx.Call("ln", (mx.Sym("x"),))
    serie = S.taylor(nodo, 1, 11, "x")
    assert mx.text(serie.cota) == mx.text(S._cota_de_taylor(nodo, 11, mx.Num(1), "x"))


def test_la_ruta_de_derivadas_no_declara_cota_para_nada():
    """Who declares a bound, after the formal route (2026-10-05).

    Until then every centre of a transcendental other than its known one refused,
    «because sin(1) is not a number this engine can hold». That was the engine's
    limit, not the function's: the formal route now writes ``sin(1)``, ``e²``… as
    exact constants. So the rule this test pins is the honest one:

    * ``sin``, ``cos``, ``exp``, ``sinh``, ``cosh`` about any centre carry a bound
      (the known series at the origin, a Lagrange remainder elsewhere);
    * ``tan`` and ``ln`` away from their known centre carry none, and say so;
    * an arbitrary expression carries none, and says so.
    """
    for nombre in ("sin", "cos", "tan", "exp", "sinh", "cosh", "ln"):
        nodo = mx.Call(nombre, (mx.Sym("x"),))
        for centro in range(-3, 4):
            try:
                serie = S.taylor(nodo, centro, 4, "x")
            except UnsupportedError:
                continue
            conocida = S._serie_por_nombre(nodo, 4, mx.Num(centro), "x") is not None
            if conocida or nombre in ("sin", "cos", "exp", "sinh", "cosh"):
                assert serie.cota is not None, (nombre, centro)
            else:
                assert serie.cota is None, (nombre, centro)
                assert any("NO se declara cota de error" in h
                           for h in serie.hipotesis), (nombre, centro)
    serie = S.taylor(mx.parse("x^2*exp(x)"), 0, 4, "x")
    assert serie.cota is None
    assert any("NO se declara cota de error" in h for h in serie.hipotesis)


def test_taylor_desplazado_traslada_la_cota_y_no_el_argumento():
    """The bound about ``a`` lives in ``|x - a|``, and is checked there."""
    serie = S.taylor(mx.parse("ln(x)"), mx.Num(1), 4)
    assert serie.cota is not None
    for d in (-0.8, -0.4, -0.1, 0.05, 0.3, 0.8):
        x = 1 + d
        propio = mx.evaluate(serie.polinomio, {"x": x}).real
        cota = abs(mx.evaluate(serie.cota, {"x": x}).real)
        assert abs(math.log(x) - propio) <= cota + 1e-15, (x, propio, cota)


def test_taylor_arma_solo_una_llamada_sola():
    """``exp(x) + 1`` is not covered, because its tail is not ``exp``'s tail.

    Majorising one does not majorise the other, and claiming the same bound for both
    would hand out a number the derivation never supported.
    """
    with_bound = S.taylor(mx.parse("exp(x)"), mx.ZERO, 6)
    assert with_bound.cota is not None
    sin_bound = S.taylor(mx.parse("exp(x) + 1"), mx.ZERO, 6)
    assert sin_bound.cota is None


def test_taylor_no_declara_precision_que_no_puede_sostener():
    """``x^2·exp(x)`` gets no bound, and the reason is measured, not asserted.

    This is the refusal that remains after T-19, and it is a real one rather than a
    leftover. The naive move — see ``exp`` inside, reuse ``exp``'s bound — is
    available, tempting, and wrong: the error here runs 20 to 26 times LARGER than
    the bound that move would attach, at every argument tried. The polynomial is
    exact, no number is claimed, and the absence is explained in words.
    """
    serie = S.taylor(mx.parse("x^2*exp(x)"), 0, 4)
    assert serie.cota is None
    assert any("NO se declara cota de error" in h for h in serie.hipotesis)
    assert "sin cota" in serie.con_cota()

    cota_ingenua = S.maclaurin("exp", 4).cota
    fallos = 0
    for x in (0.5, 1.0, 2.0, 3.0, 4.0, 5.0):
        propio = mx.evaluate(serie.polinomio, {"x": x}).real
        error = abs(x * x * math.exp(x) - propio)
        cota = abs(mx.evaluate(cota_ingenua, {"x": x}).real)
        if error > cota:
            fallos += 1
            assert error > 10 * cota, (x, error, cota)
    assert fallos == 6, "la cota ingenua de exp dejó de fallar: revisa el rechazo"


def test_la_cota_impresa_trae_su_dominio():
    """The line a reader takes away carries the interval it holds on.

    ``con_cota`` is what gets shown; a bound whose domain is one scroll away in
    ``hipotesis`` is, in practice, a bound claimed for every argument. This is the
    same sentence the hypothesis declares, pulled from there rather than written
    twice, so the two cannot drift.
    """
    for nombre in PUNTOS_DE_COTA:
        linea = S.maclaurin(nombre, 7).con_cota()
        assert "error <" in linea, (nombre, linea)
        dominio = next(h.split("cota de error:", 1)[1].strip()
                       for h in S.maclaurin(nombre, 7).hipotesis
                       if "cota de error:" in h)
        assert dominio in linea, (nombre, linea)
    # and the refusal still prints as a refusal, without a number to qualify
    negada = S.taylor(mx.parse("x^2*exp(x)"), 0, 4).con_cota()
    assert "sin cota" in negada and "error <" not in negada, negada


def test_las_dos_tablas_de_la_cota_no_pueden_separarse():
    """A name declared boundable must be boundable, and the reverse.

    ``_DOMINIO_DE_LA_COTA`` decides what gets announced and ``_cota_de_cola``
    decides what gets built. A name in the first and not the second would print a
    domain for a bound that does not exist — the exact failure this whole change
    exists to stop, moved from a table to another table.
    """
    declarables = set(S._DOMINIO_DE_LA_COTA)
    assert declarables == set(S._TERMINO), (declarables, set(S._TERMINO))
    for nombre in declarables:
        assert S._cota_de_cola(nombre, 7, "x") is not None, nombre
        assert S.maclaurin(nombre, 7).cota is not None, nombre
        # and taylor of the bare call must reach the same bound
        assert S._cota_de_taylor(mx.Call(nombre, (mx.Sym("x"),)), 7, mx.ZERO, "x") is not None, nombre


def test_la_cota_no_es_un_numero_fuera_de_su_dominio():
    """Past the declared radius the expression stops being a bound, and says so.

    Every majorisation here is ``primer_término / (1 - razón)``, so past the radius
    the denominator turns non-positive and the cota is no longer a number a reader
    could compare against an error. The domain sentence names that radius, and this
    checks the sentence against the expression rather than trusting it.
    """
    orden = 9
    for nombre, fuera in (("sin", 40.0), ("cos", 40.0), ("sinh", 40.0),
                          ("cosh", 40.0), ("exp", 30.0), ("tan", 2.0), ("ln", 1.5)):
        serie = S.maclaurin(nombre, orden)
        valor = mx.evaluate(serie.cota, {"x": fuera})
        assert valor is None or valor.real <= 0, (nombre, fuera, valor)
        # and just inside its declared radius it is a real bound again
        dentro = fuera / 10
        valor_dentro = mx.evaluate(serie.cota, {"x": dentro})
        assert valor_dentro is not None and valor_dentro.real > 0, (nombre, dentro)


def test_el_centro_admite_un_entero_desnudo():
    """``taylor(poli, 0, 9)`` is how a person writes it, so it has to work.

    Before this the bare ``int`` travelled into ``as_poly`` and surfaced as «no se
    sabe imprimir int» from four frames of code that never touched a number. The
    centre is a number by definition and ``0`` is the common case, so it is wrapped
    in ``Num`` at the boundary rather than refused.
    """
    serie = S.taylor(mx.parse("x^3 - 2*x + 1"), 0, 9)
    assert serie.polinomio is not None
    assert serie.cota is None          # a polynomial's tail is exactly zero
    assert serie.residuo is not None
    assert S.taylor(mx.parse("x^3 - 2*x + 1"), Fr(0), 9).polinomio == serie.polinomio
    with pytest.raises(Exception):
        S.taylor(mx.parse("x^3"), "a", 3)


# ---------------------------------------------------------------------------
# T-19: Taylor of an arbitrary expression
# ---------------------------------------------------------------------------


def test_las_dos_puertas_rechazan_el_mismo_orden():
    """``taylor`` accepted an order of ``-1`` and answered with a polynomial of ``0``.

    ``maclaurin`` has always refused it with «el orden tiene que ser 0 o mayor».
    Returning ``0`` and a residual of ``1`` is defensible as arithmetic and useless
    as an answer, and it was a second answer to the same question. Both doors now
    say the same words, which is what makes them one door.
    """
    for orden in (-1, S.ORDEN_MAXIMO + 1):
        with pytest.raises(UnsupportedError):
            S.maclaurin("exp", orden)
        with pytest.raises(UnsupportedError):
            S.taylor(mx.Call("exp", (mx.Sym("x"),)), 0, orden, "x")
    # and a legal order still works on both sides
    assert S.taylor(mx.Call("exp", (mx.Sym("x"),)), 0, 0).polinomio is not None


def test_tan_y_ln_por_derivadas_morían_y_por_serie_no():
    """``taylor`` must not be the weaker of two doors to the same series.

    ``tan' = 1/cos²`` and ``ln^(k) = (k-1)!/x^k``: differentiating either expands
    into a product of powers, the trace records every intermediate, and the step log
    hits its 2000-character field. ``taylor(tan(x), 0, 4)`` used to raise
    ``EXPRESSION_LIMIT`` while ``maclaurin("tan", 4)`` returned the series in one go,
    and the same held for ``ln`` about 1. The known series is now written rather than
    derived, and the whole order range is reachable through both doors.
    """
    for nombre, centro in (("tan", 0), ("ln", 1)):
        tope = None
        for orden in range(1, S.ORDEN_MAXIMO + 1):
            try:
                S.taylor(mx.Call(nombre, (mx.Sym("x"),)), centro, orden, "x")
            except Exception:                      # noqa: BLE001 - looking for the cap
                tope = orden - 1
                break
        assert tope is None, (nombre, centro, tope)


@pytest.mark.parametrize("nombre", ["sin", "cos", "tan", "exp", "sinh", "cosh"])
@pytest.mark.parametrize("orden", [3, 5, 7, 11, 15, 21, 30, 40])
def test_taylor_de_una_funcion_conocida_es_su_misma_serie_que_maclaurin(nombre, orden):
    """Same polynomial, same residual, same bound — the two doors are one door.

    Delegation is only allowed to be invisible. If the known-series path ever drifts
    from ``maclaurin``, one of them is lying about the same series, and which one is
    not something a reader should have to guess.
    """
    por_derivadas = S.taylor(mx.Call(nombre, (mx.Sym("x"),)), 0, orden, "x")
    directa = S.maclaurin(nombre, orden)
    assert mx.text(por_derivadas.polinomio) == mx.text(directa.polinomio), nombre
    assert mx.text(por_derivadas.residuo) == mx.text(directa.residuo), nombre
    assert mx.text(por_derivadas.cota) == mx.text(directa.cota), nombre


def test_ln_en_el_origen_sigue_sin_serie_although_la_de_mercator_exista():
    """The trap: ``maclaurin("ln")`` is ``ln(1+x)``, and ``taylor(ln(x), 0, …)`` is not.

    Delegating the known series to ``taylor`` at the origin made this function answer
    ``x - 1/2x² + 1/3x³ - …`` to a question about ``ln``, whose Taylor series at 0
    does not exist. The series was right — of a different function. Before the
    delegation it refused, with «ln(0) no es un número», and that refusal was the
    correct answer and had to survive the fix.
    """
    with pytest.raises(UnsupportedError):
        S.taylor(mx.Call("ln", (mx.Sym("x"),)), 0, 5, "x")
    # and about 1, where the series does exist, it answers with the Mercator one
    sobre_uno = S.taylor(mx.Call("ln", (mx.Sym("x"),)), 1, 20, "x")
    mercator = mx.substitute(S.maclaurin("ln", 20).polinomio, "x",
                             mx.Sub(mx.Sym("x"), mx.Num(1)))
    assert mx.text(sobre_uno.polinomio) == mx.text(mercator)
    # the bound's interval shifts with the polynomial: the formula says |x|, and the
    # expression is |x - 1|, so the answer has to say which one it means
    assert "abs(x - 1)" in mx.text(sobre_uno.cota)
    assert any("|x - 1|" in h for h in sobre_uno.hipotesis), sobre_uno.hipotesis
    assert "x - 1" in sobre_uno.metodo


def test_el_radio_de_tan_no_es_el_de_mercator():
    """``tan`` sums on ``1 < x < 1,57``; the module used to say it could not.

    The hypothesis announced «radio de convergencia 1» for both ``tan`` and ``ln``,
    three lines below a table that correctly gave ``tan`` the radius ``pi/2``. The
    sentence was wrong in the direction that forbids a convergent series: between 1
    and ``pi/2`` the tangent series sums perfectly well.
    """
    tan = S.maclaurin("tan", 5)
    assert any("pi/2" in h for h in tan.hipotesis), tan.hipotesis
    assert not any("radio de convergencia 1" in h for h in tan.hipotesis), tan.hipotesis
    # measured: at x = 1.4 the series is still good, and 1.4 > 1
    serie = S.maclaurin("tan", 11)
    error = abs(math.tan(1.4) - mx.evaluate(serie.polinomio, {"x": 1.4}).real)
    cota = abs(mx.evaluate(serie.cota, {"x": 1.4}).real)
    assert error < 1e-6 < cota or error <= cota, (error, cota)


@pytest.mark.parametrize("expresion,orden,contiene", [
    ("exp(x)", 4, "1/24*x^4"),
    ("sin(x)", 4, "-1/6*x^3"),
    ("sin(x)", 4, "x"),
    ("cos(x)", 4, "-1/2*x^2"),
    ("cos(x)", 4, "1"),
])
def test_taylor_sale_de_las_derivadas(expresion, orden, contiene):
    """Each function gets its OWN polynomial.

    They all came out the same before, read off one table of «odd and
    alternating»: a sine series that starts at ``x`` is not a series of anything,
    and a coseno series that starts at ``x`` is a sino's. The cause was a pair of
    mistakes that cancelled —the loop read the term of order k with the
    derivative of order k+1, and the coefficient was taken as a reciprocal— so
    every intermediate value looked plausible.
    """
    serie = S.taylor(mx.parse(expresion), mx.ZERO, orden)
    assert contiene in mx.text(serie.polinomio), mx.text(serie.polinomio)


def test_el_seno_y_el_coseno_no_dan_el_mismo_polinomio():
    """The negative control for the test above: they must differ."""
    seno = mx.text(S.taylor(mx.parse("sin(x)"), mx.ZERO, 6).polinomio)
    coseno = mx.text(S.taylor(mx.parse("cos(x)"), mx.ZERO, 6).polinomio)
    assert seno != coseno


def test_taylor_evaluated_centre_does_not_divide_by_zero():
    """sin(0) is 0, and 1/sin(0) is not a coefficient.

    Substituting into the derivative gives «sin(0)», which only the trigonometric
    engine folds, and «3·0^2», which only the rational normal form folds. Without
    both the Taylor series of sin carries a 1/0 where a zero belongs.
    """
    texto = mx.text(S.taylor(mx.parse("sin(x)"), mx.ZERO, 4).polinomio)
    assert "/0" not in texto, texto
    assert "sin(0)" not in texto, texto


def test_taylor_needs_a_centre_that_is_a_number():
    with pytest.raises(UnsupportedError) as exc:
        S.taylor(mx.parse("exp(x)"), mx.Sym("a"), 3)
    assert "centro" in str(exc.value)


def test_taylor_around_a_centre_that_is_not_zero():
    serie = S.taylor(mx.parse("x^2"), mx.Num(Fr(2)), 2)
    texto = mx.text(serie.polinomio)
    assert "4" in texto or "x" in texto, texto


@pytest.mark.parametrize("expresion,exacto", [
    ("x^3", "x^3"), ("x^2", "x^2"), ("x", "x"), ("x^4", "x^4"),
    ("x^2 + 1", "x^2 + 1"),
])
def test_el_polinomio_de_un_monomio_coincide_con_el_monomio(expresion, exacto):
    """``taylor(x^3, 0, 4)`` returns ``x^3``.

    It used to return ``1/12*x^2`` \u2014 a term that belongs to no Taylor series of
    anything. The derivatives were always right (for x^3 they are x^3, 3x^2, 6x,
    6, which at 0 give 0, 0, 0, 6), so the fault was in how the terms are
    assembled, and there were TWO faults cancelling each other out: the loop read
    the term of order k with the derivative of order k+1, and the coefficient came
    out as a reciprocal. A cancellation between two bugs is the hardest kind to
    see, because every intermediate value looks plausible.
    """
    serie = S.taylor(mx.parse(expresion), mx.ZERO, 4)
    assert mx.text(serie.polinomio) == exacto


@pytest.mark.parametrize("expresion,grado", [("x^3", 3), ("x^2", 2), ("x^4", 4)])
def test_el_polinomio_de_un_monomio_aproxima_al_monomio(expresion, grado):
    """And it is not merely spelled right: it evaluates right."""
    serie = S.taylor(mx.parse(expresion), mx.ZERO, 6)
    for x in (0.3, 1.7, -2.5):
        valor = mx.evaluate(serie.polinomio, {"x": x}).real
        assert abs(valor - x ** grado) < 1e-9, (expresion, x)


def test_el_residuo_de_un_monomio_es_cero():
    """A polynomial has no further terms, so naming one is inventing it."""
    assert mx.exact_value(S.taylor(mx.parse("x^3"), mx.ZERO, 4).residuo) == 0


def test_taylor_en_un_centro_que_no_es_cero_da_el_mismo_polinomio():
    """At centre 2 the Taylor polynomial of x^2 is x^2 itself, which is a good
    check: a wrong assembly gives x^2 plus stray terms in (x-2)."""
    serie = S.taylor(mx.parse("x^2"), mx.Num(Fr(2)), 2)
    assert mx.text(serie.polinomio) == "x^2"
    assert mx.exact_value(serie.residuo) == 0


def test_taylor_se_niega_donde_la_funcion_no_tiene_desarrollo():
    """ln has no Taylor series at 0: its first derivative there is 1/0.

    Building a polynomial out of that writes a division by zero into every
    coefficient and calls the result an approximation.
    """
    with pytest.raises(UnsupportedError) as exc:
        S.taylor(mx.parse("ln(x)"), mx.ZERO, 4)
    assert "no es un n\u00famero" in str(exc.value)
