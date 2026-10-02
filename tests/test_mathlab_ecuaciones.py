"""MATH_LAB: intervals, domains and the T-12 equation solver.

The property that matters most here is the last one. A solver that returns
``x = pi/6`` for ``sin(x) = 1/2`` has proved nothing until that value has been
put back into the original equation, so :func:`test_toda_solucion_satisface_la_ecuacion`
does exactly that, at several members of every family, numerically.
"""

import cmath
import math
from fractions import Fraction

import pytest

from academic_core.domain.engineering.mathlab import dominio as D
from academic_core.domain.engineering.mathlab import ecuaciones as E
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.errors import UnsupportedError


# ---------------------------------------------------------------------------
# dominio: exact points
# ---------------------------------------------------------------------------


def test_los_puntos_se_ordenan_por_su_valor_real():
    """The trap: ``3`` and ``pi/2`` are different kinds of point, but 3 > pi/2."""
    puntos = [D.punto_pi(Fraction(2)), D.punto(Fraction(3)),
              D.punto_pi(Fraction(1, 2)), D.punto(Fraction(-1))]
    assert [p.texto() for p in sorted(puntos)] == ["-1", "1/2·π", "3", "2·π"]
    assert D.punto(Fraction(3)) > D.punto_pi(Fraction(1, 2))
    assert D.punto_pi(Fraction(-1)) < D.punto(Fraction(0))


def test_un_punto_se_vuelve_expresion_exacta():
    assert mx.text(D.punto_pi(Fraction(1, 2)).expr()) == "1/2*pi"
    assert mx.text(D.punto_pi(Fraction(1)).expr()) == "pi"
    assert mx.text(D.punto(Fraction(3)).expr()) == "3"


# ---------------------------------------------------------------------------
# dominio: sets
# ---------------------------------------------------------------------------


def test_union_complemento_e_interseccion():
    c = D.desde_intervalos([D.Intervalo(None, D.punto_pi(Fraction(-1))),
                            D.Intervalo(D.punto_pi(Fraction(1, 2)), None)])
    assert c.texto() == "(-∞, -π) ∪ (1/2·π, ∞)"
    assert c.contiene(D.punto(Fraction(0))) is False
    assert c.contiene(D.punto_pi(Fraction(1))) is True
    assert c.complemento().texto() == "(-π, 1/2·π)"
    izquierda = D.desde_intervalos([D.Intervalo(None, D.punto_pi(Fraction(2)))])
    derecha = D.desde_intervalos([D.Intervalo(D.punto_pi(Fraction(1)), None)])
    assert izquierda.interseccion(derecha).texto() == "(π, 2·π)"


def test_un_hueco_no_se_cierra_al_fusionar():
    """``(pi,2pi)`` and ``(3pi,4pi)`` are two intervals, not one."""
    conjunto = D.desde_intervalos([D.Intervalo(D.punto_pi(Fraction(1)),
                                              D.punto_pi(Fraction(2))),
                                   D.Intervalo(D.punto_pi(Fraction(3)),
                                               D.punto_pi(Fraction(4)))])
    assert conjunto.texto() == "(π, 2·π) ∪ (3·π, 4·π)"


def test_quitar_puntos_no_devuelve_el_punto_eliminado():
    """The subtle one: merging (a,b) and (b,c) would put b back."""
    quitar = D.quita_puntos(D.REALES, (D.punto_pi(Fraction(1, 2)),
                                       D.punto_pi(Fraction(3, 2))))
    assert quitar.texto() == "(-∞, 1/2·π) ∪ (1/2·π, 3/2·π) ∪ (3/2·π, ∞)"
    assert quitar.contiene(D.punto_pi(Fraction(1, 2))) is False


# ---------------------------------------------------------------------------
# dominio: periods and denominators
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("origen,esperado", [
    ("sin(x)", Fraction(2)), ("cos(x)", Fraction(2)), ("tan(x)", Fraction(1)),
    ("sin(2*x)", Fraction(1)), ("cos(3*x)", Fraction(2, 3)),
    ("sin(x/2)", Fraction(4)), ("tan(x/3)", Fraction(3)),
    ("sin(2*x)*cos(3*x)", Fraction(2)),   # lcm, not the smallest
])
def test_el_periodo_se_escala_y_se_combina(origen, esperado):
    assert D.periodo(mx.parse(origen)) == esperado


@pytest.mark.parametrize("origen", ["sinh(x)", "cosh(x)", "tanh(x)", "x", "ln(x)"])
def test_lo_aperiodico_no_inventa_periodo(origen):
    """``sinh`` has no real period; a fake one would produce families that are not
    solutions."""
    assert D.periodo(mx.parse(origen)) is None


@pytest.mark.parametrize("origen,esperados", [
    ("1/(x-1)", ["x - 1"]),
    ("sin(x)/cos(x)", ["cos(x)"]),
    ("1/ln(x)", ["ln(x)", "x"]),
    ("1/(sin(x)*cos(x))", ["sin(x)*cos(x)"]),
    ("sqrt(1-x)", []),      # a closed inequality, said out loud instead
    ("sin(x)", []),
])
def test_los_denominadores(origen, esperados):
    assert [mx.text(d) for d in D.denominadores(mx.parse(origen))] == esperados


def test_el_signo_se_decide_numericamente():
    assert D.signo_en(mx.parse("sin(x)"), "x", [0.5, 3.5, 5.5]) == [1, -1, -1]
    # an undefined point comes back as 0, indistinguishable from a zero, and
    # pretending otherwise is how a sign chart invents a crossing at a pole
    assert D.signo_en(mx.parse("1/x"), "x", [0.0, 1.0, -1.0]) == [0, 1, -1]


# ---------------------------------------------------------------------------
# T-12: the solver
# ---------------------------------------------------------------------------


SOLUCIONES_CONOCIDAS = {
    "sin(x) = 1/2": ["1/6·π", "5/6·π"],
    "sin(x) = 1": ["1/2·π"],
    "sin(x) = -1": ["-1/2·π"],
    "cos(x) = 1": ["0"],
    "cos(x) = 0": ["1/2·π", "-1/2·π"],
    "cos(x) = -1/2": ["2/3·π", "-2/3·π"],
    "tan(x) = 1": ["1/4·π"],
    "sin(2*x) = 1/2": ["1/12·π", "5/12·π"],
    "cos(2*x) = 0": ["1/4·π", "-1/4·π"],
    "2*cos(x) = 1": ["1/3·π", "-1/3·π"],
}


@pytest.mark.parametrize("ecuacion,esperados", sorted(SOLUCIONES_CONOCIDAS.items()))
def test_las_familias_son_las_esperadas(ecuacion, esperados):
    resolucion = E.resolver(ecuacion)
    assert resolucion.familias, resolucion.texto("x")
    bases = [mx.pretty(f.base) for f in resolucion.familias]
    assert bases == esperados, f"{ecuacion} -> {bases}"


def test_el_paso_es_el_periodo_correcto():
    """2·pi for sine and cosine, pi for tangent — the difference is the whole
    difference between the two answers."""
    assert mx.text(E.resolver("sin(x) = 1/2").familias[0].paso) == "2*pi"
    assert mx.text(E.resolver("tan(x) = 1").familias[0].paso) == "pi"


def test_el_angulo_notable_se_escribe_como_multiplo_de_pi():
    assert mx.text(E.resolver("sin(x) = 1/2").familias[0].base) == "1/6*pi"


def test_un_valor_no_notable_se_queda_exacto_y_no_decimal():
    """``arcsin(1/3)`` is an exact real number; a decimal would be a downgrade."""
    resolucion = E.resolver("sin(x) = 1/3")
    assert "asin(1/3)" in mx.text(resolucion.familias[0].base)
    assert any("no es un ángulo notable" in h for h in resolucion.hipotesis)


def test_un_valor_irracional_tambien_da_solucion_exacta():
    """sqrt(2)/2 is exact, so its arcsine is exact too.

    It is in fact a notable angle, and the table knows it: the solution comes back
    as pi/4 and 3pi/4, not as an unevaluated ``asin(sqrt(2)/2)``. The test used to
    assert the weaker thing — that the answer merely stays symbolic — and the
    improvement shows up here as a failure, which is the point of asserting it.
    """
    resolucion = E.resolver("sin(x)^2 - 1/2 = 0")
    assert len(resolucion.familias) == 4
    bases = {mx.text(f.base) for f in resolucion.familias}
    # -pi/4 and 7pi/4 are the same angle; the solver does not fold the period and
    # there is no reason it should, so both spellings are correct here
    assert bases <= {"1/4*pi", "3/4*pi", "5/4*pi", "7/4*pi", "-1/4*pi"}
    assert not any("asin(" in b for b in bases)


def test_un_surd_no_notable_se_queda_simbolico_y_no_decimal():
    """sqrt(7)/4 is not notable, and it must not be rounded into a decimal."""
    resolucion = E.resolver("sin(x) = sqrt(7)/4")
    assert resolucion.familias
    for familia in resolucion.familias:
        assert "asin(sqrt(7)/4)" in mx.text(familia.base)
        assert "." not in mx.text(familia.base)


def test_la_suma_con_una_fase_usa_el_desplazamiento():
    resolucion = E.resolver("2*sin(x)+3*cos(x) = 1")
    assert resolucion.familias
    assert any("atan2" in h or "desplazamiento de fase" in h
               for h in resolucion.hipotesis)


def test_la_sin_de_la_amplitud_determina_si_hay_solucion():
    """|c| > sqrt(a²+b²) has no solution, and that is a proof, not a shrug."""
    resolucion = E.resolver("sin(x)+cos(x) = 5")
    assert resolucion.vacia
    assert any("no llega" in h for h in resolucion.hipotesis)


def test_un_seno_mayor_que_uno_no_tiene_solucion():
    resolucion = E.resolver("sin(x) = 2")
    assert resolucion.vacia
    assert any("no pasa de 1" in h for h in resolucion.hipotesis)


@pytest.mark.parametrize("ecuacion", ["x = 1/2", "sin(x) = x", "sin(x)+cos(x) = 1/3",
                                      "tan(x)^2 = 2", "1/x = 1"])
def test_lo_que_no_se_sabe_resolver_se_dice_y_no_se_inventa(ecuacion):
    """The distinction that matters: «no lo sé» is not «no hay soluciones»."""
    resolucion = E.resolver(ecuacion)
    if resolucion.sin_respuesta:
        assert "NO quiere decir que no haya soluciones" in resolucion.texto("x")
    else:
        # if it did solve it, every family still has to check out
        for familia in resolucion.familias:
            assert familia.texto("x")


def test_una_ecuacion_sin_igual_se_rechaza():
    with pytest.raises(UnsupportedError) as exc:
        E.resolver("sin(x) 1/2")
    assert "falta el signo" in str(exc.value)


def test_una_ecuacion_con_dos_incongnitas_se_rechaza():
    with pytest.raises(UnsupportedError) as exc:
        E.resolver("sin(x) = cos(y)")
    assert "más de una incógnita" in str(exc.value)


# ---------------------------------------------------------------------------
# the property that makes an equation solver trustworthy
# ---------------------------------------------------------------------------


def _residuo(ecuacion: str, valor: float) -> float | None:
    izquierda, derecha = E.separar(ecuacion)
    f = mx.Sub(mx.parse(izquierda), mx.parse(derecha))
    resto = mx.substitute(f, "x", mx.Num(Fraction(valor).limit_denominator(10 ** 9))
                          if abs(valor) < 10 ** 6 else mx.Num(valor))
    calculado = mx.evaluate(resto)
    if calculado is None:
        return None
    if abs(calculado.imag) > 1e-9:
        return None
    return abs(calculado.real)


SOLUBLES = ["sin(x) = 1/2", "sin(x) = 1", "sin(x) = -1", "cos(x) = 1",
            "cos(x) = 0", "cos(x) = -1/2", "tan(x) = 1", "sin(2*x) = 1/2",
            "cos(2*x) = 0", "2*cos(x) = 1", "sin(x)^2 - 1/2 = 0",
            "sin(x)^3 - sin(x) = 0", "cos(x)^2 = 1/2", "sin(x) = 0",
            "tan(x)^2 - 3 = 0", "2*sin(x)+3*cos(x) = 1"]


@pytest.mark.parametrize("ecuacion", SOLUBLES)
def test_toda_solucion_satisface_la_ecuacion(ecuacion):
    """§5.3 applied to a solver: every member of every family goes back in.

    This is the check that separates a solver from a plausible-looking table of
    formulas, and the only reason to believe a family at all.
    """
    resolucion = E.resolver(ecuacion)
    assert resolucion.familias, f"{ecuacion}: {resolucion.texto('x')}"
    comprobados = 0
    for familia in resolucion.familias:
        for k in range(-3, 4):
            miembro = familia.miembro(k, "x")
            valor = mx.evaluate(miembro)
            if valor is None or abs(valor.imag) > 1e-9:
                continue
            comprobados += 1
            izquierda, derecha = E.separar(ecuacion)
            diferencia = mx.Sub(mx.parse(izquierda), mx.parse(derecha))
            resto = mx.substitute(diferencia, "x", miembro)
            calculado = mx.evaluate(resto)
            if calculado is None:
                continue  # undefined there: not evidence either way
            escala = max(1.0, abs(calculado.real))
            assert abs(calculado.real) / escala < 1e-9, (
                f"{ecuacion}: {familia.texto('x')} con k={k} no satisface la "
                f"ecuación (residuo {abs(calculado.real) / escala:.3g})")
    assert comprobados > 0, f"{ecuacion}: no se pudo comprobar ningún miembro"


@pytest.mark.parametrize("ecuacion", SOLUBLES)
def test_ninguna_familia_se_repite(ecuacion):
    resolucion = E.resolver(ecuacion)
    claves = [(mx.text(f.base), mx.text(f.paso)) for f in resolucion.familias]
    assert len(claves) == len(set(claves)), [f.texto("x") for f in resolucion.familias]


@pytest.mark.parametrize("ecuacion", SOLUBLES)
def test_la_respuesta_dice_de_donde_viene(ecuacion):
    """§5.5b: every family carries the method that produced it."""
    resolucion = E.resolver(ecuacion)
    for familia in resolucion.familias:
        assert familia.metodo.strip(), familia.texto("x")


def test_el_resolutor_no_declara_espurias_sin_motivo():
    """A spurious solution would be reported by name; none of these should be."""
    for ecuacion in SOLUBLES:
        assert E.resolver(ecuacion).espurias == (), ecuacion
