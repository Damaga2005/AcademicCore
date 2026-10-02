# SPDX-License-Identifier: MIT
"""MATH_LAB T-23: what a graph is, as exact facts."""

from __future__ import annotations

import math
from fractions import Fraction as Fr

import pytest

from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import graficas as G
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import verify as V

PI = math.pi


def k(texto: str) -> G.Caracteristicas:
    return G.caracteristicas(mx.parse(texto))


# ---------------------------------------------------------------------------
# the four numbers that ARE the curve
# ---------------------------------------------------------------------------


def test_un_senoide_tiene_periodo_amplitud_frecuencia_y_fase():
    c = k("3*sin(2*x)")
    assert c.es_sinusoidal
    assert c.periodo == Fr(1)            # sin(2x) has period pi
    assert abs(c.amplitud - 3) < 1e-9
    assert abs(c.frecuencia - 1.0) < 1e-9
    assert mx.text(c.fase) == "2*x"


def test_la_frecuencia_es_la_inversa_del_periodo():
    assert abs(k("sin(x)").frecuencia - 0.5) < 1e-12
    assert abs(k("sin(4*x)").frecuencia - 2.0) < 1e-12


def test_el_desplazamiento_vertical_no_cambia_la_amplitud():
    """sen(x) + 1 swings from 0 to 2: half the swing is 1, and half the MAXIMUM
    would be 1 too by luck, while 3·sen(2x) has maximum 3 and amplitude 3."""
    assert abs(k("sin(x) + 1").amplitud - 1) < 1e-9
    assert abs(k("3*sin(2*x)").amplitud - 3) < 1e-9
    assert abs(k("2*sin(x) + 5").amplitud - 2) < 1e-9


def test_una_funcion_sin_maximo_no_declara_amplitud():
    """1/tan(x) is unbounded, so there is no amplitude to declare.

    A number here would be a sampled height that means nothing, and reporting it
    as «the amplitude» is the worst kind of wrong: it looks like the answer.
    """
    assert k("1/tan(x)").amplitud is None
    assert any("no se declara amplitud" in h for h in k("1/tan(x)").hipotesis)


def test_una_suma_de_dos_funciones_no_es_un_senoide():
    """sin(x) + cos(x) IS one sinusoid, but only after a phase shift.

    Finding which one is a search, and a half-found answer is worse than none.
    """
    assert k("sin(x) + cos(x)").es_sinusoidal is False
    assert k("sin(x)/x").es_sinusoidal is False
    assert any("no es de la forma" in h
               for h in k("sin(x) + cos(x)").hipotesis), k("sin(x) + cos(x)").hipotesis


def test_la_tangente_no_es_un_senoide_porque_es_no_acotada():
    assert k("tan(x)").es_sinusoidal is False


def test_la_amplitud_de_un_senoide_es_exacta_y_no_un_maximo_muestreado():
    """5·sen(x + π/3) has an amplitude of 5, and sampling the maximum gives
    4.989 — which is a fact about the grid, not about the function.

    In the canonical form the coefficient in front of the call IS the amplitude,
    so the exact number is used and the answer says which of the two it is.
    """
    c = k("5*sin(x + pi/3)")
    assert c.es_sinusoidal
    assert c.amplitud == 5.0
    assert "exacta" in c.texto()
    assert any("es exacta" in h for h in c.hipotesis)


def test_la_amplitud_estimated_dice_que_lo_es():
    assert any("se estima" in h for h in k("sin(x) + cos(x)").hipotesis)


def test_un_coeficiente_negativo_se_dobla_como_fase_de_pi():
    """-sen(x) is sen(x + π), and one curve with one representation beats two
    answers that both have to be interpreted."""
    c = k("-sin(x)")
    assert c.es_sinusoidal
    assert c.amplitud == 1.0
    assert mx.text(c.fase) == "x + pi"


def test_un_desplazamiento_de_fase_no_convierte_la_expresion_en_cociente():
    """sen(x + π/3) contains a bar and a power INSIDE its argument.

    A text test for «no hay cociente» reads both of those and rejects the most
    ordinary phase shift there is; the check has to stop at the call.
    """
    c = k("5*sin(x + pi/3)")
    assert c.es_sinusoidal
    assert mx.text(c.fase) == "x + pi/3"


@pytest.mark.parametrize("expresion", [
    "sin(x)/x",          # a quotient: not a constant times a call
    "sin(x)^2",          # a power, not a first power
    "sin(x)*cos(x)",     # two calls, so two frequencies
    "sin(x) + cos(x)",   # the same, added
    "sin(x^2)",          # x squared is not a frequency
    "tan(x)",            # unbounded
])
def test_lo_que_no_es_un_senoide_se_declara_no_senoide(expresion):
    assert k(expresion).es_sinusoidal is False


def test_la_fase_de_un_senoide_simple_no_es_un_simbolo_de_relleno():
    """sen(x) IS the call, so a walk that only visits children never reaches it
    and the phase came back as a placeholder instead of x."""
    assert mx.text(k("sin(x)").fase) == "x"
    assert mx.text(k("cos(2*x)").fase) == "2*x"


# ---------------------------------------------------------------------------
# zeros, discontinuities, asymptotes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("expresion,ceros", [
    ("sin(x)", ["0", "π"]),
    ("cos(x)", ["1/2·π", "3/2·π"]),
    ("3*sin(2*x)", ["0", "1/2·π"]),
    ("tan(x)", ["0"]),
])
def test_los_ceros_son_exactos_y_no_una_muestra(expresion, ceros):
    assert [p.texto() for p in k(expresion).ceros] == ceros


def test_las_discontinuidades_son_los_polos():
    assert [p.texto() for p in k("tan(x)").discontinuidades] == \
        ["1/2·π", "3/2·π"]
    assert [p.texto() for p in k("1/sin(x)").discontinuidades] == \
        ["0", "π"]


def test_un_punto_del_borde_que_no_es_discontinuidad_no_se_declara():
    """arcsen(2·sen x) has domain [0, pi/6] ∪ ..., and 0 IS in the domain.

    Taking every endpoint of the domain as a discontinuity would invent one at
    every place where the function is perfectly well defined.
    """
    c = k("asin(2*sin(x))")
    assert all(p.texto() != "0" for p in c.discontinuidades), c.discontinuidades


def test_las_asintotas_verticales_coinciden_con_los_polos():
    verticales = [a for a in k("1/tan(x)").asintotas if a.startswith("x =")]
    assert verticales, k("1/tan(x)").asintotas


def test_una_funcion_sin_polo_no_declara_asintota_vertical():
    assert [a for a in k("sin(x)").asintotas if a.startswith("x =")] == []


# ---------------------------------------------------------------------------
# critical points and extrema
# ---------------------------------------------------------------------------


def test_los_extremos_se_clasifican_por_el_signo_de_la_derivada():
    """1/4·pi is a maximum of 3·sen(2x) and 7/4·pi a minimum of -3.

    Reading the stored coefficient 1/4 as the coordinate evaluates the derivative
    at 1/4 instead of at pi/4, three radians from the critical point, and every
    classification comes out «sin clasificar».
    """
    hallados = G.extremos(mx.parse("3*sin(2*x)"))
    assert [(e.punto.texto(), e.tipo) for e in hallados] == [
        ("1/4·π", "maximo"), ("7/4·π", "minimo")]
    assert abs(hallados[0].valor - 3) < 1e-9
    assert abs(hallados[1].valor + 3) < 1e-9


def test_el_valor_de_un_extremo_se_calcula_en_el_punto_y_no_en_su_indice():
    for e in G.extremos(mx.parse("3*sin(2*x)")):
        esperado = 3 * math.sin(2 * float(e.punto.coeficiente) * PI)
        assert abs(e.valor - esperado) < 1e-9


# ---------------------------------------------------------------------------
# comparison of two expressions
# ---------------------------------------------------------------------------


def test_los_puntos_de_corte_son_los_ceros_de_la_diferencia():
    c = G.comparar(mx.parse("sin(x)"), mx.parse("cos(x)"))
    assert [p.texto() for p in c.se_cortan_en] == ["1/4·π", "5/4·π"]
    assert any("ceros de la diferencia" in h for h in c.hipotesis)


@pytest.mark.parametrize("a,b,se_cortan_en", [
    ("sin(x)", "sin(x)", False),
    ("sin(x)", "cos(x)", True),
    ("sin(x)", "-sin(x)", True),
    ("cos(x)", "sin(x)", True),
    # sin(x) = 2*sin(x) holds exactly where sin(x) = 0, that is at 0 and pi: the
    # two graphs cross twice and are nowhere near equal. Reading «different
    # coefficients» as «different functions» is the mistake this case is for.
    ("sin(x)", "2*sin(x)", True),
    ("sin(x)", "sin(x)^2", True),
])
def test_dos_expresiones_se_cortan_o_no(a, b, se_cortan_en):
    c = G.comparar(mx.parse(a), mx.parse(b))
    assert bool(c.se_cortan_en) == se_cortan_en
    assert c.identicas is (not se_cortan_en)


def test_dos_funciones_iguales_lo_dicen_aunque_no_haya_ceros():
    """sin(x) - sin(x) is identically zero.

    Asking the zero-solver about it gets «no lo sé» — every point is a zero and it
    declines to enumerate an infinite set — which would report two identical
    functions as unknown about whether they cross.
    """
    c = G.comparar(mx.parse("sin(x)"), mx.parse("sin(x)"))
    assert c.identicas is True
    assert c.se_cortan_en == ()
    assert any("idénticamente cero" in h for h in c.hipotesis)


def test_una_diferencia_sin_ceros_equivale_a_identicas():
    """«No zeros of f-g anywhere» is the claim, and it is a real one."""
    c = G.comparar(mx.parse("sin(x) + 1"), mx.parse("cos(x)^2 + 1"))
    assert c.se_cortan_en == ()


# ---------------------------------------------------------------------------
# the second path: does the picture agree with the numbers?
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("expresion", [
    "3*sin(2*x)", "sin(x)", "cos(2*x)", "tan(x)", "sin(x) + cos(x)",
    "1/sin(x)", "-sin(x)", "cos(x)/sin(x)", "2*sin(x) + 1",
])
def test_los_hechos_declarados_aguantan_un_muestreo_ajeno(expresion):
    sello = G.verifica(k(expresion))
    assert sello.verdict == V.VERIFIED, (expresion, sello.detail)


def test_un_sello_verificado_dice_que_es_ausencia_de_contraejemplos():
    """240 points are not a proof that a period is a period for every real x."""
    sello = G.verifica(k("sin(x)"))
    assert "ausencia de contraejemplos" in sello.detail


def test_las_muestras_junto_a_un_polo_se_saltan_y_se_cuentan():
    """tan(x) IS exactly periodic, and right next to a pole it is enormous on
    one side and a different enormous on the other.

    Testing those samples makes a periodic function look aperiodic, and hiding
    the skips would make a check that tested almost nothing read like a check
    that tested everything.
    """
    sello = G.verifica(k("tan(x)"))
    assert sello.verdict == V.VERIFIED
    assert "saltadas" in sello.method
    assert "2 saltadas" in sello.method


def test_una_constante_no_tiene_que_verificar_nada_y_lo_dice():
    sello = G.verifica(k("5"))
    assert sello.verdict == V.NUMERIC_ONLY
    assert "nada que verificar" in sello.method


# --- gaps the verifier found, documented and NOT endorsed --------------------
#
# These three assertions are about what the engine gets WRONG today. They are
# here so that the wrong answer has a test that names it: when T-12/T-13 are
# fixed they will fail, and that failure is the point.


# --- three gaps the verifier found in T-12 and T-13, now closed --------------
#
# They were written here as assertions about what the engine got WRONG, so that
# the wrong answer had a test naming it. Three are fixed; the third turned out to
# be my own wrong claim about the engine, and its test now says so.


def test_sen_sobre_x_no_declara_periodo_porque_no_lo_tiene():
    """sen(x)/x tends to zero, so f(x + T) = f(x) fails for every T.

    The engine used to answer 2·π, read off the seno's period without asking
    whether the quotient around it was periodic too. Periodicity survives sums,
    products and quotients, so one aperiodic part — here the bare x of the
    denominator — settles the whole, and now it does.
    """
    c = k("sin(x)/x")
    assert c.periodo is None
    assert G.verifica(c).verdict == V.VERIFIED


def test_un_senoide_desfasado_da_sus_ceros_en_su_lugar_y_no_en_el_del_sin():
    """5·sen(x + π/3) is zero at x = -π/3 + kπ, and never at 0.

    Reading a zero off the function instead of off the shifted argument was the
    whole error, and it was the same error for every phase: the solver computed
    the solutions of u = 0 for the argument u and then published the base as if
    it were a value of x.
    """
    c = k("5*sin(x + pi/3)")
    assert sorted(p.texto() for p in c.ceros) == ["2/3\u00b7\u03c0", "5/3\u00b7\u03c0"]
    assert G.verifica(c).verdict == V.VERIFIED


def test_un_cero_inexistente_no_se_declara_cero():
    """0/0 is not a zero of sen(x)/x; it is a point where nothing is defined.

    The zeros of a quotient are those of its numerator ALONE, minus the points
    where the denominator also vanishes — which is what keeps 1/tan(x) having
    none while stopping 0 from being one of sen(x)/x's.
    """
    c = k("sin(x)/x")
    assert [p.texto() for p in c.ceros] == ["\u03c0"]
    assert [p.texto() for p in c.discontinuidades] == ["0"]


def test_el_reciprotico_de_tan_es_indefinido_en_pi_2_y_eso_esta_bien():
    """1/tan(x) is cotangent AND it is undefined at pi/2. Both are true.

    This test exists because T-23 claimed the opposite: that cotangent is
    defined there, so pi/2 is not a discontinuity of it. Cotangent is, as a
    function — but the EXPRESSION 1/tan(x) is not, because tan(pi/2) does not
    exist and the reciprocal of nothing is nothing. The domain is right and the
    claim was wrong; what is missing is not a discontinuity but the note that
    the hole is REMOVABLE, the limit being 0.
    """
    c = k("1/tan(x)")
    assert "1/2\u00b7\u03c0" in [p.texto() for p in c.discontinuidades]
    assert G.verifica(c).verdict == V.VERIFIED
    # and there is no asymptote there, because the limit is 0 and not infinity
    assert [a for a in c.asintotas if a == "x = 1/2\u00b7\u03c0"] == []


# ---------------------------------------------------------------------------
# approximation, with the error measured
# ---------------------------------------------------------------------------


def test_la_aproximacion_mide_el_error_contra_la_funcion():
    a = G.aproximar(mx.parse("sin(x)"), 9, muestras=5)
    for x, valor, error in a.puntos:
        assert abs(valor - math.sin(x)) < 1e-6
        assert error < 1e-6


def test_mas_orden_significa_un_error_menor_en_la_grafica():
    errors = [max(e for _, _, e in G.aproximar(mx.parse("sin(x)"), n, 5).puntos)
             for n in (3, 7, 11, 15)]
    assert errors == sorted(errors, reverse=True), errors


def test_la_aproximacion_usa_la_serie_conocida_y_no_el_taylor():
    """taylor(sen(x)) currently assembles a monomial's terms wrong and would put
    the coseno polynomial on the graph. The known series is term by term and is
    right, so it is the one that gets used — and the hypothesis says which."""
    a = G.aproximar(mx.parse("sin(x)"), 5)
    assert "-1/2*x^2" not in mx.text(a.polinomio)
    assert "-1/6*x^3" in mx.text(a.polinomio)
    assert any("serie conocida" in h for h in a.hipotesis)


def test_una_expresion_sin_serie_conocida_avisa_de_que_va_al_taylor():
    a = G.aproximar(mx.parse("exp(x)*x"), 4)
    assert any("serie conocida" in h for h in a.hipotesis), a.hipotesis
    assert any("Taylor" in h or "derivar" in h for h in a.hipotesis)


# ---------------------------------------------------------------------------
# the polyline, and where it must break
# ---------------------------------------------------------------------------


def test_la_curva_se_parte_en_los_polos_y_no_en_otros_sitios():
    """A polyline drawn through pi/2 shows a function that is defined there.

    The break has to be found by the magnitude, not by a hole: at pi/2 the
    denominator of 1/tan is 6·10^-17 rather than 0, so the sampled point is a very
    large finite number and looks like an ordinary height.
    """
    for expresion in ("1/tan(x)", "tan(x)", "sin(x)/x"):
        g = G.grafica(mx.parse(expresion), "x", 16, 1)
        assert g.series[0].discontinuities, expresion
    for expresion in ("sin(x)", "cos(x)"):
        g = G.grafica(mx.parse(expresion), "x", 16, 1)
        assert g.series[0].discontinuities == (), expresion


def test_la_grafica_tiene_texto_alternativo():
    """§6: accessibility is part of the deliverable, not an extra."""
    g = G.grafica(mx.parse("sin(x)"), "x", 16, 1)
    assert g.description
    assert "sen(x)" in g.describe() or "sin(x)" in g.describe()
    assert g.x_label == "x"


def test_los_extremos_de_la_grafica_coinciden_con_los_de_la_funcion():
    """The numbers and the picture have to be the same function."""
    for expresion in ("3*sin(2*x)", "-2*cos(x)"):
        valores = [e.valor for e in G.extremos(mx.parse(expresion))]
        g = G.grafica(mx.parse(expresion), "x", 64, 2)
        alto = max(v for v in g.series[0].ys if v == v)
        assert abs(alto - max(abs(v) for v in valores)) < 0.05, expresion


# ---------------------------------------------------------------------------
# the operation as the laboratory calls it
# ---------------------------------------------------------------------------


def pedir(entrada) -> object:
    import academic_core.domain.engineering.mathlab as ML

    return ML.calcular(ML.Peticion("caracteristicas", entrada))


def test_la_operacion_devuelve_los_cuatro_numeros_del_senoide():
    r = pedir("3*sin(2*x)")
    assert "periodo: pi" in r.exacto
    assert "amplitud: 3 (exacta)" in r.exacto
    assert "fase: 2*x" in r.exacto
    assert r.sello.verdict == V.VERIFIED
    assert r.version == C.CONTRACT_VERSION


def test_la_operacion_trae_la_grafica_con_su_texto_alternativo():
    r = pedir("sin(x)")
    assert r.grafica is not None
    assert r.grafica.description
    assert r.grafica.series[0].name


def test_la_operacion_no_da_por_bueno_un_resultado_que_el_segundo_camino_cuestiona():
    """A seal that can never say «discrepa» is not a seal.

    Nothing in the engine contradicts the verifier any more, so the failing path
    is exercised on purpose: a description with a zero planted in it that the
    function does not have. The result must not read as a clean answer.
    """
    import dataclasses

    from academic_core.domain.engineering.mathlab import dominio as D

    sincera = G.caracteristicas(mx.parse("sin(x)"))
    plantado = dataclasses.replace(
        sincera, ceros=sincera.ceros + (D.punto_pi(Fr(7, 4)),))
    assert G.verifica(plantado).verdict == V.DISCREPANT

    # and the same through the laboratory, where the trajectory records it
    r = pedir("sin(x)")
    assert r.sello.verdict == V.VERIFIED
    reglas = [s.rule for s in r.traza]
    assert "verificacion.ok" in reglas, reglas
    assert "verificacion.discrepa" not in reglas


def test_la_operacion_declara_lo_que_no_puede_decir():
    """Every refusal travels with the answer: an amplitude that is not declared
    says why, and the estimadas say how they were estimated."""
    r = pedir("1/tan(x)")
    assert "amplitud: no declarada" in r.exacto
    assert any("no se declara amplitud" in a for a in r.avisos), r.avisos
    assert any("límites" in a for a in r.avisos), r.avisos


def test_la_operacion_acepta_un_mapa_con_la_variable():
    r = pedir({"expr": "2*sin(x)", "var": "x"})
    assert "amplitud: 2 (exacta)" in r.exacto
    assert r.grafica.x_label == "x"
