"""Tests for the phase-shift and period fixes (T-12 and T-13).

Appended, not merged into the existing cases: every one of these was a bug and
each carries the reason it was there.
"""
from __future__ import annotations

from fractions import Fraction

import pytest

from academic_core.domain.engineering.mathlab import dominio as D
from academic_core.domain.engineering.mathlab import ecuaciones as E
from academic_core.domain.engineering.mathlab import inequaciones as I
from academic_core.domain.engineering.mathlab import mvexpr as mx

PI = 3.141592653589793


# ---------------------------------------------------------------------------
# _afine: the shift was invisible
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("texto,coeficiente,constante", [
    ("x", 1, "0"),
    ("2*x", 2, "0"),
    ("x/2", Fraction(1, 2), "0"),
    ("(2*x + 1)/3", Fraction(2, 3), "1/3"),
    ("x + pi/3", 1, "pi/3"),
    ("2*x + pi/3", 2, "pi/3"),
    ("x - pi/2", 1, "-pi/2"),
    ("x + 1", 1, "1"),
])
def test_lo_afine_seve_la_parte_constante(texto, coeficiente, constante):
    """``x + pi/3`` is ``(1, pi/3)`` and not «not affine».

    ``trig._factores`` splits products and never splits a sum, so it handed the
    whole shifted argument back as ONE factor and every phase shift came out as
    «not affine». That is what made ``sen(x + pi/3) = 0`` unsolvable.
    """
    a, b = E._afine(mx.parse(texto), "x")
    assert a == coeficiente, texto
    assert mx.text(b) == constante, texto


@pytest.mark.parametrize("texto", ["pi/3", "3", "sin(x)", "x^2", "1/x", "x*(x+1)"])
def test_lo_no_afino_no_declara_escala(texto):
    """``1/x`` is not ``a·x``: inverting it gives ``x = 1/u``, not ``(base-b)/a``.

    Treating it as affine answers ``x = base``, which is a wrong number with the
    right shape and therefore the most dangerous kind.
    """
    assert E._afine(mx.parse(texto), "x")[0] is None, texto


# ---------------------------------------------------------------------------
# the solver: a shift is the commonest case there is
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ecuacion,base,paso", [
    ("sin(x + pi/3) = 0", "-1/3*pi", "2*pi"),
    ("sin(x + pi/3) = 0", "2/3*pi", "2*pi"),
    ("sin(2*x + pi/3) = 0", "-1/6*pi", "pi"),
    ("cos(x + pi/4) = 0", "1/4*pi", "2*pi"),
    ("cos(x + pi/4) = 0", "-3/4*pi", "2*pi"),
    ("tan(x + pi/2) = 0", "-1/2*pi", "pi"),
    ("cos(x - pi/2) = 0", "pi", "2*pi"),
    ("sin(x/2) = 1", "pi", "4*pi"),
    ("tan(2*x + 1) = 0", "-1/2", "1/2*pi"),
])
def test_la_fase_se_deshace_en_x_y_no_solo_en_la_variable_sustituida(ecuacion,
                                                                   base, paso):
    r = E.resolver(ecuacion)
    pares = {(mx.text(f.base), mx.text(f.paso)) for f in r.familias}
    assert (base, paso) in pares, (ecuacion, pares)


@pytest.mark.parametrize("ecuacion", [
    "sin(x + pi/3) = 0", "sin(2*x + pi/3) = 0", "cos(x + pi/4) = 0",
    "tan(x + pi/2) = 0", "sin(x + 1) = 0",
])
def test_una_familia_deshecha_en_x_lo_dice_con_una_bandera(ecuacion):
    """``en_x`` is what stops a caller reading a ``u`` value as an ``x`` value."""
    for familia in E.resolver(ecuacion).familias:
        assert familia.en_x is True, familia.texto("x")


def test_una_familia_que_no_se_puede_deshacer_lo_declara():
    """``sen(sen(x)) = 0`` has no change of variable to undo.

    The solver says so AND marks the family, because a hypothesis in a string is
    easy to drop and a boolean in a dataclass is not.
    """
    familias = E.resolver("sin(sin(x)) = 0").familias
    assert familias and all(f.en_x is False for f in familias)


def test_la_solucion_de_un_desplazamiento_satisface_la_ecuacion_original():
    """Substitution in the ORIGINAL equation, which is the only thing that
    catches a spurious member."""
    for ecuacion in ("sin(x + pi/3) = 0", "sin(2*x + pi/3) = 0",
                     "cos(x + pi/4) = 0", "tan(x + pi/2) = 0",
                     "cos(x - pi/2) = 0", "sin(x/2) = 1"):
        izquierda, derecha = ecuacion.split(" = ")
        f, cte = mx.parse(izquierda), mx.parse(derecha)
        for familia in E.resolver(ecuacion).familias:
            for k in (-2, -1, 0, 1, 2, 3):
                x = familia.miembro(k, "x")
                a, b = mx.evaluate(f, {"x": mx.evaluate(x)}), mx.evaluate(cte)
                if a is None:
                    continue
                assert abs(a.real - b.real) < 1e-9, (ecuacion, mx.text(x))


# ---------------------------------------------------------------------------
# periodo: asked of the whole expression
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("texto", [
    "sin(x)/x", "x + sin(x)", "sin(x)*x", "x^2", "sin(sin(x))", "sinh(x)",
    "exp(x)", "5",
])
def test_una_expresion_que_no_es_periodica_no_declara_periodo(texto):
    """Periodicity survives sums, products and quotients — so one aperiodic part
    settles the whole.

    ``sin(x)/x`` used to answer 2·pi, read off the seno's period without asking
    whether the quotient around it was periodic too. It decays to zero, so
    ``f(x + T) = f(x)`` fails for every ``T``.
    """
    assert D.periodo(mx.parse(texto)) is None, texto
    assert D.periodo_minimo(mx.parse(texto)) is None, texto


@pytest.mark.parametrize("texto,esperado", [
    ("sin(x)", Fraction(2)),
    ("sin(2*x)", Fraction(1)),
    ("tan(x)", Fraction(1)),
    ("1/tan(x)", Fraction(1)),          # cotangent, period pi
    ("sin(x/2)", Fraction(4)),
    ("sin(3*x)", Fraction(2, 3)),
    ("sin(x + pi/3)", Fraction(2)),      # a shift does not change the period
    ("5*sin(x + pi/3)", Fraction(2)),
    ("sin(2x)*cos(3x)", Fraction(2)),   # the lcm, not the smallest
    ("sin(x) + cos(x)", Fraction(2)),
    ("sin(x)^2", Fraction(2)),          # a valid period; periodo_minimo shortens
])
def test_el_periodo_de_un_senoide_sigue_siendo_el_que_es(texto, esperado):
    assert D.periodo(mx.parse(texto)) == esperado, texto


def test_el_periodo_minimo_afecta_a_un_senoide_desfasado():
    """The halving search is a second path and it has to agree with the first."""
    assert D.periodo_minimo(mx.parse("sin(x + pi/3)")) == Fraction(2)


def test_la_hiperbolica_no_tiene_periodo_y_sigue_diciendolo():
    """``sinh`` has no real period: a solver assuming one would emit x + 2k·pi."""
    assert D.periodo(mx.parse("sinh(x)")) is None
    assert D.periodo(mx.parse("cosh(x)")) is None


# ---------------------------------------------------------------------------
# ceros: inexistent points are not zeros
# ---------------------------------------------------------------------------


def test_un_cero_inexistente_no_se_declara_cero():
    """0/0 is not a zero of sin(x)/x; it is a point where nothing is defined.

    The zeros of a quotient are those of its numerator ALONE — which is why
    1/tan(x) has none and that is a fact — but a point where the denominator
    vanishes is a pole, and publishing it as a zero put 0 on the sign chart.
    """
    ceros = I.ceros(mx.parse("sin(x)/x"), "x")
    assert [mx.text(v) for v in ceros] == ["1*pi"]


@pytest.mark.parametrize("texto,ceros", [
    ("sin(x)/x", ["1*pi"]),
    ("cos(x)/x", ["1/2*pi", "3/2*pi"]),
    ("sin(x)/cos(x)", ["0*pi", "1*pi"]),
    ("sin(x)^2/x", ["1*pi"]),
    ("1/tan(x)", []),
    ("1/x", []),
    ("sin(x)", ["0*pi", "1*pi"]),
    ("cos(x)", ["1/2*pi", "3/2*pi"]),
])
def test_los_ceros_de_un_cociente_son_los_de_su_numerador_menos_los_polos(texto,
                                                                      ceros):
    c = I.ceros(mx.parse(texto), "x")
    assert [mx.text(v) for v in c] == ceros, texto


def test_los_puntos_inexistentes_son_los_extremos_abiertos_y_no_los_cerrados():
    """A closed end is a point where the expression IS defined.

    arcsen(2·sen x) has domain [0, pi/6] ∪ ..., and 0 belongs to it. Calling
    every endpoint a discontinuity invents one wherever a function happens to
    stop at a finite bound.
    """
    inexistentes = {p.texto() for p in
                    I.puntos_inexistentes(mx.parse("asin(2*sin(x))"), "x")}
    assert "0" not in inexistentes, inexistentes
    assert "1/2·π" in {p.texto() for p in
                       I.puntos_inexistentes(mx.parse("tan(x)"), "x")}


def test_un_cero_de_pi_se_reconoce_venga_como_venga():
    """``pi/3`` is a multiple of pi and ``_factores`` does not split it.

    Every value that reaches the period reduction is written this way once it has
    been shifted, so a reader that missed it reported «no zeros» for a function
    full of them.
    """
    from academic_core.domain.engineering.mathlab import trig

    for texto, esperado in [("pi/3", Fraction(1, 3)), ("2*pi", Fraction(2)),
                            ("-pi/2", Fraction(-1, 2)), ("pi", Fraction(1)),
                            ("3*pi/4", Fraction(3, 4)), ("0", Fraction(0)),
                            ("x", None), ("1", None), ("pi + 1", None)]:
        assert trig._multiplo_de_pi(mx.parse(texto)) == esperado, texto


def test_el_cero_de_un_senoide_desfasado_cae_donde_toca():
    """5·sen(x + pi/3) is zero at x = -pi/3 + k·pi, and never at 0.

    Reading the zero off the function instead of off the shifted argument was the
    whole error, and it was the same error for every phase.
    """
    ceros = I.ceros(mx.parse("5*sin(x + pi/3)"), "x")
    assert {mx.text(v) for v in ceros} == {"2/3*pi", "5/3*pi"}, ceros
    for v in ceros:
        x = float(I._coeficiente_pi(v)) * PI
        valor = mx.evaluate(mx.parse("5*sin(x + pi/3)"), {"x": x})
        assert abs(valor.real) < 1e-9, (mx.text(v), valor)
    # and 0 is not one of them, which is what the engine used to say
    assert abs(mx.evaluate(mx.parse("5*sin(x + pi/3)"), {"x": 0.0}).real) > 1.0

# ---------------------------------------------------------------------------
# the linear case: the most elementary equation there is, and it was missing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ecuacion,solucion", [
    ("x = 0", "x = 0"),
    ("2*x = 0", "x = 0"),
    ("x = 1", "x = 1"),
    ("x - 1 = 0", "x = 1"),
    ("2*x + 1 = 0", "x = -1/2"),
    ("x/2 = 3", "x = 6"),
    ("3*x = -6", "x = -2"),
    ("-x = 3", "x = -3"),
    ("2*x = -1", "x = -1/2"),
])
def test_una_ecuacion_lineal_tiene_una_sola_solucion(ecuacion, solucion):
    """x = 0 is not an exotic equation and it was out of reach.

    It was not cosmetic either: ``ceros`` asks the solver for the zeros of a
    denominator, and a refusal there means a point that does not exist stays in
    the list. The quotient filter asks the DOMAIN now, which is the right
    dependency, and this case closes the equation for its own sake.
    """
    r = E.resolver(ecuacion)
    assert r.texto("x") == solucion, (ecuacion, r.texto("x"))
    assert r.sin_respuesta is False, ecuacion


def test_una_solucion_aislada_se_escribe_sin_la_familia():
    """A step of 0 is one value, and printing «x = 0 + 0·k» reads as «x is
    anything». The text of a single solution must say what it is."""
    unica = E.resolver("2*x + 1 = 0").familias[0]
    assert unica.es_punto_unico
    assert unica.texto("x") == "x = -1/2"
    familia = E.resolver("sin(x) = 0").familias[0]
    assert not familia.es_punto_unico
    assert "k" in familia.texto("x")


def test_una_contradiccion_si_dice_que_no_hay_soluciones():
    """The one case where «no hay soluciones» IS the answer."""
    r = E.resolver("1 = 2")
    assert r.vacia and r.sin_respuesta is False
    assert r.texto("x") == "no hay soluciones"


def test_una_identidad_no_se_convierte_en_una_familia():
    """Every x solves x = x, and a family is not every x."""
    for ecuacion in ("x = x", "1 = 1", "0 = 0"):
        assert E.resolver(ecuacion).sin_respuesta is True, ecuacion


@pytest.mark.parametrize("ecuacion", ["x^2 = 0", "x^2 = 4", "sin(x) = x",
                                      "1/x = 0"])
def test_lo_que_el_caso_lineal_no_resuelve_lo_niega(ecuacion):
    """A refusal, never a wrong «no hay soluciones».

    x^2 = 0 has x = 0 as a solution. Reading «the left side is not affine» as
    «the left side is a constant» and answering «no solutions» is a false answer
    delivered with the same confidence as a solved one.
    """
    assert E.resolver(ecuacion).sin_respuesta is True, ecuacion


def test_la_solucion_lineal_satisface_la_ecuacion_original():
    izquierda, derecha = "3*x - 7", "-13"
    base = E.resolver(f"{izquierda} = {derecha}").familias[0].base
    a = mx.evaluate(mx.parse(izquierda), {"x": float(mx.exact_value(base))})
    b = mx.evaluate(mx.parse(derecha))
    assert abs(a.real - b.real) < 1e-12, (a, b)


# ---------------------------------------------------------------------------
# removable holes
# ---------------------------------------------------------------------------


def test_un_hueco_removible_se_distingue_de_un_polo():
    """1/tan(x) does not exist at pi/2, and its limit there is 0.

    Announcing it as a pole says the function blows up, which is the one thing it
    does not do. Decided by structure and not by sampling a limit: the reciprocal
    simplifies to cotangent, and cotangent IS defined at pi/2.
    """
    huecos = {(p.texto(), round(v, 12)) for p, v in
              I.removibles(mx.parse("1/tan(x)"), "x")}
    assert ("1/2\u00b7\u03c0", 0.0) in huecos, huecos
    assert all(p.texto() != "0" for p, _ in
               I.removibles(mx.parse("1/tan(x)"), "x")), "0 is a pole of cotangent"


def test_un_polo_no_se_declara_hueco_removible():
    for texto in ("tan(x)", "1/sin(x)", "cos(x)/sin(x)", "1/x", "sin(1/x)"):
        assert I.removibles(mx.parse(texto), "x") == (), texto


@pytest.mark.parametrize("texto,punto,limite", [
    ("sin(x)/x", "0", 1.0),
    ("(1-cos(x))/x^2", "0", 0.5),
    ("1/(1/2*tan(x+pi/6))", "1/3\u00b7\u03c0", 0.0),
    # a point stored as an expression: it used to be evaluated at x = 0, giving 1
    ("(x^2-1)/(x-1)", "1", 2.0),
])
def test_un_hueco_que_la_simplificacion_no_ve_tampoco_es_un_polo(texto, punto, limite):
    """sin(x)/x at 0 used to be listed here as a POLE, «the safe direction». It is
    a hole with limit 1, and calling it a pole was as false as inventing a limit.
    """
    huecos = {p.texto(): v for p, v in I.removibles(mx.parse(texto), "x")}
    assert punto in huecos, (texto, huecos)
    assert abs(huecos[punto] - limite) < 1e-6, (texto, huecos)


def test_una_expresion_sin_huecos_no_declara_ninguno():
    assert I.removibles(mx.parse("sin(x)"), "x") == ()


def test_el_hueco_aparece_en_la_descripcion_de_la_grafica():
    """The gap T-23 left open: the hole exists and its limit is shown."""
    from academic_core.domain.engineering.mathlab import graficas as G

    c = G.caracteristicas(mx.parse("1/tan(x)"))
    assert "hueco removible" in c.texto()
    assert "1/2\u00b7\u03c0" in c.texto()
    # and it is still listed as a discontinuity: it does not exist there
    assert "1/2\u00b7\u03c0" in [p.texto() for p in c.discontinuidades]


# ---------------------------------------------------------------------------
# two representations of one point
# ---------------------------------------------------------------------------


def test_un_cero_y_un_cero_por_pi_son_el_mismo_punto():
    """0 and 0·pi are one number written two ways.

    Not knowing that produced an interval «(0, 0)» where there is no interval
    at all: ln(x) came out as (0,0) ∪ (0,∞) because its lower bound is a plain 0
    and the zero it also excludes is a 0·pi.
    """
    from academic_core.domain.engineering.mathlab import dominio as D

    assert D._comparacion_exacta(D.punto_pi(Fraction(0)), D.punto(Fraction(0))) == 0
    assert [i.texto() for i in
            I.dominio(mx.parse("ln(x)"), "x").intervalos] == ["(0, \u221e)"]


def test_dos_intervalos_abiertos_en_el_punto_compartido_no_se_funden():
    """(-inf, 0) ∪ (0, inf) is R without 0, and merging would put the 0 back.

    The rule was the other way round: two intervals touching with both ends open
    were the ones being merged, which turned R without 0 into (-inf, 0).
    """
    from academic_core.domain.engineering.mathlab import dominio as D

    abiertos = D.desde_intervalos([
        D.Intervalo(None, D.punto(Fraction(0)), True, True),
        D.Intervalo(D.punto(Fraction(0)), None, True, True),
    ])
    assert [i.texto() for i in abiertos.intervalos] == \
        ["(-\u221e, 0)", "(0, \u221e)"]

    cerradas = D.desde_intervalos([
        D.Intervalo(None, D.punto(Fraction(0)), True, False),
        D.Intervalo(D.punto(Fraction(0)), None, False, True),
    ])
    assert [i.texto() for i in cerradas.intervalos] == ["(-\u221e, \u221e)"]


@pytest.mark.parametrize("texto,esperado", [
    ("ln(x)", ["(0, \u221e)"]),
    ("ln(x^2)", ["(-\u221e, 0)", "(0, \u221e)"]),
    ("ln(2*x)", ["(0, \u221e)"]),
    ("1/x", ["(-\u221e, 0)", "(0, \u221e)"]),
    ("ln(x)/x", ["(0, \u221e)"]),
])
def test_el_dominio_no_pierde_una_mitad_de_la_recta(texto, esperado):
    assert [i.texto() for i in
            I.dominio(mx.parse(texto), "x").intervalos] == esperado, texto
