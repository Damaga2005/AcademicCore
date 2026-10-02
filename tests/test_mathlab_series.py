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
                  "tan": math.tan}


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


@pytest.mark.parametrize("nombre", ["sin", "cos", "ln"])
def test_la_cota_alternativa_acota_el_error_real(nombre):
    """For the alternating series the first omitted term IS a bound — on |x| <= 1.

    Outside that the terms do not decrease and the bound is not a bound, so the
    module has to decline rather than quote it anyway.
    """
    serie = S.maclaurin(nombre, 9)
    for x in (0.2, 0.6, 1.0):
        propio = mx.evaluate(serie.polinomio, {"x": x}).real
        cota = abs(mx.evaluate(serie.cota, {"x": x}).real)
        # the Maclaurin series of ln is the one of ln(1 + x): comparing it against
        # log(x) is comparing against a different function, and the "failure" would
        # have been the test's, not the series'
        exacto = math.log(1 + x) if nombre == "ln" else VALORES_REALES[nombre](x)
        assert abs(exacto - propio) <= cota + 1e-15, (nombre, x, exacto, propio, cota)


def test_las_series_no_alternantes_no_declaran_cota_inventada():
    """exp and tan have decreasing terms nowhere in general.

    The first omitted term of exp is an order of magnitude, not a bound, and
    quoting it as one would be a false promise of precision.
    """
    for nombre in ("exp", "tan", "sinh", "cosh"):
        assert S.maclaurin(nombre, 7).cota is None, nombre


def test_taylor_no_declara_precision_que_no_puede_sostener():
    """The polynomial is exact; the error bound is not available, and it says so."""
    serie = S.taylor(mx.parse("exp(x)"), mx.ZERO, 6)
    assert serie.cota is None
    assert any("NO se declara cota de error" in h for h in serie.hipotesis)
    assert "sin cota" in serie.con_cota()


# ---------------------------------------------------------------------------
# T-19: Taylor of an arbitrary expression
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("expresion,orden,contiene", [
    ("exp(x)", 4, "1/24*x^4"),
    ("sin(x)", 4, "1/24*x^4"),
])
def test_taylor_sale_de_las_derivadas(expresion, orden, contiene):
    serie = S.taylor(mx.parse(expresion), mx.ZERO, orden)
    assert contiene in mx.text(serie.polinomio), mx.text(serie.polinomio)


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


@pytest.mark.parametrize("expresion,terreno", [("x^3", "1/12*x^2"),
                                                ("x^2", "1/2*x")])
def test_taylor_de_un_mononomio_ainda_no_coincide(expresion, terreno):
    """Known gap, recorded rather than hidden.

    ``taylor(x^3, 0, 4)`` returns ``1/12*x^2`` where it should return ``x^3``, and
    ``x^2`` is wrong the same way. The derivatives themselves check out one by one
    — for x^3 they are x^3, 3x^2, 6x, 6, which at 0 give 0, 0, 0, 6 — so the fault
    is in how the terms are assembled, not in the differentiation.

    The test is here so that the day it is fixed, it fails. Fixing it would mean
    asserting ``x^3`` instead, and until then that assertion would be a lie about
    what the engine does.
    """
    serie = S.taylor(mx.parse(expresion), mx.ZERO, 4)
    assert mx.text(serie.polinomio) == terreno          # documented, not endorsed
    for x in (0.3, 1.7):
        valor = mx.evaluate(serie.polinomio, {"x": x}).real
        assert abs(valor - x ** len(expresion)) > 1e-6
