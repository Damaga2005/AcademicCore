# SPDX-License-Identifier: MIT
"""El orden de crecimiento en el infinito, y las rectas que salen de el."""

from __future__ import annotations

import pytest

from academic_core.domain.engineering.mathlab import graficas as G
from academic_core.domain.engineering.mathlab import limites as L
from academic_core.domain.engineering.mathlab import mvexpr as mx


def k(texto: str) -> G.Caracteristicas:
    return G.caracteristicas(mx.parse(texto))

# --------------------------------------------------------------- asintotas


#: ``(expression, expected line)``. The horizontal and oblique asymptotes that a
#: textbook asks for, all of them reachable from the order of growth alone.
LINEAS = [
    ("3*sen(2*x)/x", "y = 0"),
    ("sen(x)/x", "y = 0"),
    ("cos(x)/x^3", "y = 0"),
    ("1/x", "y = 0"),
    ("1/(2*x)", "y = 0"),
    ("3/(x + 1)", "y = 0"),
    ("(x^2 - 1)/(x^2 + 1)", "y = 1"),
    ("x/(x + 1)", "y = 1"),
    ("(2*x^3 + 1)/(x^3 - 5)", "y = 2"),
    ("5", "y = 5"),
    ("1/3", "y = 1/3"),
    ("x", "y = x"),
    ("x + 1/x", "y = x"),
    ("2*x + 3", "y = 2\u00b7x + 3"),
    ("-x + 2", "y = -x + 2"),
]


@pytest.mark.parametrize("expresion,linea", LINEAS)
def test_la_asintota_de_horizonte_u_oblicua_sale_del_orden(expresion, linea):
    """The engine itself, which is the thing under test.

    Asked through ``caracteristicas`` some of these cannot be answered at all: that
    function also needs the DOMAIN, and the domain of ``(x^2 - 1)/(x^2 + 1)`` needs
    the zeros of ``x^2 + 1``, which nobody here has taught the engine to write.
    That is a different gap in a different module and it is not this one, so the
    wiring is checked separately below with expressions whose domain is known.
    """
    assert linea in L.asintotas_de_horizonte_y_oblicua(mx.parse(expresion), "x")


#: Functions that grow like a line and never reach one, or grow faster than any
#: line. Each of these got an asymptote in a version of this engine that only knew
#: the ORDER: ``x/sin(x)`` and ``x*sin(x)`` both came out as ``y = x``, which is the
#: order right and the asymptote wrong, and that is the whole reason the
#: oscillation flag exists.
SIN_ASINTOTA = ["x/sin(x)", "x*sen(x)", "x + sen(x)", "sen(x)", "cos(x)", "x^2",
                "1/3*x^2", "tan(x)"]


@pytest.mark.parametrize("expresion", SIN_ASINTOTA)
def test_crecer_no_llega_a_una_recta_y_no_se_inventa_una(expresion):
    assert L.asintotas_de_horizonte_y_oblicua(mx.parse(expresion), "x") == (), expresion


def test_el_orden_se_declara_y_no_se_muestrea():
    """The order is a NUMBER, and a number can be wrong out loud."""
    orden = L.orden_en_infinito(mx.parse("3*sen(2*x)/x"), "x")
    assert orden.grado == -1 and orden.coeficiente == 3 and not orden.oscila

    orden = L.orden_en_infinito(mx.parse("x*sen(x)"), "x")
    assert orden.grado == 1 and orden.oscila, "crece como una recta y no la alcanza"

    orden = L.orden_en_infinito(mx.parse("tan(x)"), "x")
    assert orden.grado is None and not orden.conocido, "lo que no se sabe, se dice"


def test_la_vertical_y_la_horizontal_conviven():
    """``1/tan(x)`` no tiene horizontal —es periodica— y sí verticales, una por
    periodo: x = 0, que se repite cada pi."""
    asintotas = k("1/tan(x)").asintotas
    assert asintotas == ("x = 0",), asintotas
    assert not any(a.startswith("y =") for a in asintotas), asintotas


def test_la_hipotesis_ya_no_dice_que_no_hay_motor_de_limites():
    hipotesis = " ".join(k("3*sen(2*x)/x").hipotesis)
    assert "orden de crecimiento" in hipotesis, hipotesis
    assert "no hay motor de" not in hipotesis, hipotesis


#: The wiring: the line the graph publishes has to BE the line the engine decided.
PUBLICADAS = ["3*sen(2*x)/x", "sen(x)/x", "x + 1/x", "2*x + 3", "1/x", "5",
              "1/(x + 1)", "x"]


@pytest.mark.parametrize("expresion", PUBLICADAS)
def test_la_grafica_publica_la_asintota_que_el_motor_decidio(expresion):
    lineas = L.asintotas_de_horizonte_y_oblicua(mx.parse(expresion), "x")
    assert lineas, expresion
    for linea in lineas:
        assert linea in k(expresion).asintotas, (expresion, k(expresion).asintotas)


def test_un_cociente_cuyo_dominio_no_se_sabe_no_impide_calcular_su_asintota():
    """The two gaps are separate, and saying so is cheaper than hiding one in the
    other. The asymptote of ``(x^2 - 1)/(x^2 + 1)`` is ``y = 1`` and always was;
    what is missing is where the function stops existing."""
    assert L.asintotas_de_horizonte_y_oblicua(
        mx.parse("(x^2 - 1)/(x^2 + 1)"), "x") == ("y = 1",)
    with pytest.raises(Exception, match="denominador"):
        k("(x^2 - 1)/(x^2 + 1)")
