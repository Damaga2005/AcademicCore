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
