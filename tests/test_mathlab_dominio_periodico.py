# SPDX-License-Identifier: MIT
"""El dominio tiene que ser cierto tambien FUERA del primer periodo.

``dominio()`` encontraba los huecos de un periodo, los quitaba de la recta entera
y publicaba el resultado como si fuera todo: para ``1/sen(x)`` imprimia
``(-∞, 0) ∪ (0, π) ∪ (π, 2·π) ∪ (2·π, ∞)``, que excluye ``0``, ``π`` y ``2·π`` y
no dice nada de ``3·π``. Preguntado por ``3·π`` el conjunto respondía que el punto
existe y el evaluador respondía ``None``.

El conjunto ahora declara su periodo, y ``contiene`` lo dobla antes de mirar.

La autoridad aquí es el EVALUADOR, con las tres maneras en que un punto flotante
miente sobre una singularidad real, porque sin las tres este archivo inventa bugs
que no existen:

- un **polo** sale como un número enorme, no como una ausencia;
- un **0/0** sale como el cociente de dos números diminutos: ``sen(x)/tg(x)`` vale
  ``1.0`` en ``x = -4·π``, donde la expresión no existe y su vecina ``cos(x)`` sí,
  así que el valor es hasta ESTABLE y la prueba de estabilidad no lo ve;
- un valor que **salta** al mover la entrada una millonésima está en una
  singularidad.
"""

from __future__ import annotations

import math
from fractions import Fraction

import pytest

from academic_core.domain.engineering.mathlab import dominio as D
from academic_core.domain.engineering.mathlab import inequaciones as I
from academic_core.domain.engineering.mathlab import mvexpr as mx

#: Expressions with a periodic set of HOLES. `1/(2·sen(x) + 3)` is not
#: among them: it is periodic and its domain is all of `ℝ`, which needs no
#: note, and which is checked apart below.
PERIODICAS = ["1/sin(x)", "1/cos(x)", "1/(1 - sin(x))", "1/(1 - cos(x))",
              "1/(1 + cos(x))", "tan(x)", "cot(x)", "sec(x)", "csc(x)",
              "1/tan(x)", "cos(x)/sin(x)", "sin(x)/cos(x)",
              "1/(sin(x)*cos(x))", "1/(sin(x) - 1/2)",
              "asin(2*sin(x))", "atanh(sin(x))", "ln(sin(x))", "sqrt(cos(x))",
              "acosh(1+cos(x))", "sqrt(sin(x))"]
APERIODICAS = ["1/(x^2 - 1)", "1/(x - 1)", "asin(x)", "ln(x)", "sqrt(x-1)",
               "atan(x)", "asinh(x)"]


def _autoridad(texto: str, x: float) -> float | None:
    """The value at ``x``, or ``None`` where a float is not an authority."""
    parser = mx.parse(texto)
    for den in D.denominadores(parser):
        v = mx.evaluate(den, {"x": x})
        if v is not None and abs(v.real) < 1e-8:
            return None              # the denominator vanishes: 0/0 or a pole
        if v is not None and abs(v.real) > 1e11:
            return None              # a pole inside a function, seen as huge
    vals = [mx.evaluate(parser, {"x": x + d}) for d in (-1e-9, 0.0, 1e-9)]
    if any(v is None for v in vals):
        return None
    if any(isinstance(v, complex) and abs(v.imag) > 1e-12 for v in vals):
        return None
    reales = [float(v.real) for v in vals]
    if any(abs(v) > 1e11 for v in reales):
        return None
    if max(reales) - min(reales) > 1e-6 * max(1.0, abs(reales[1])):
        return None
    return reales[1]


@pytest.mark.parametrize("caso", PERIODICAS + APERIODICAS)
def test_el_dominio_es_cierton_en_cualquier_periodo(caso):
    """Three periods out, on the π/8 grid, against the evaluator."""
    conjunto = I.dominio(mx.parse(caso))
    fallos = []
    for k in range(-40, 41):
        x = float(Fraction(k, 8)) * math.pi
        valor = _autoridad(caso, x)
        if valor is None:
            continue
        if conjunto.contiene(D.punto_pi(Fraction(k, 8))) != (abs(valor) < 1e11):
            fallos.append(f"{Fraction(k, 8)}pi")
    assert not fallos, f"{caso}: el dominio discrepa en {fallos[:6]}"


@pytest.mark.parametrize("caso", PERIODICAS)
def test_un_conjunto_periodico_declara_su_periodo(caso):
    conjunto = I.dominio(mx.parse(caso))
    assert conjunto.periodo is not None, (
        f"{caso}: una lista finita de huecos sin periodo declarado miente sobre "
        "todos los puntos fuera del primero")
    assert "se repite cada" in conjunto.texto(), conjunto.texto()


@pytest.mark.parametrize("caso", APERIODICAS)
def test_un_conjunto_aperiodico_no_declara_ningun_periodo(caso):
    assert I.dominio(mx.parse(caso)).periodo is None, caso


def test_el_primer_hueco_del_primer_periodo_basta_para_leer_todos():
    """The old bug in one assertion, so it cannot come back quietly.

    ``3·pi`` is not in the domain of ``1/sen(x)``, and the intervals it prints do
    not say so. Before the fix this was ``True``, which is a set claiming that a
    point belongs to it when the expression cannot be evaluated there.
    """
    conjunto = I.dominio(mx.parse("1/sen(x)"))
    # multiples of `pi` only: `1/sen(x)` DOES exist at `3*pi/2`, where `sen` is -1.
    # The multiples are the ones the printed intervals leave out, and they are what
    # this test is about.
    for k in (3, 4, 5, -3, -5):
        assert not conjunto.contiene(D.punto_pi(Fraction(k))), k
    assert conjunto.contiene(D.punto_pi(Fraction(3, 2))), "3pi/2 si existe"


def test_un_conjunto_sin_periodo_se_lee_literalmente():
    """The sign chart builds one period ON PURPOSE; folding must not reach it.

    ``Conjunto.periodo`` defaults to ``None``, and that default has to mean
    «literal»: every solver answer is a set over one period and is read directly.
    """
    from academic_core.domain.engineering.mathlab import inequaciones as Iq
    solucion = Iq.resolver_inequidad("sen(x) > 1/3")
    conjunto = solucion.conjunto
    assert conjunto.periodo is None, "una respuesta de solver es de UN periodo"
    assert conjunto.contiene(D.punto_pi(Fraction(1, 2))), "sen(pi/2) = 1 > 1/3"
    assert conjunto.contiene(D.punto_pi(Fraction(3, 4))), "sen(3pi/4) > 1/3"
    assert not conjunto.contiene(D.punto_pi(Fraction(0))), "sen(0) = 0"
    assert not conjunto.contiene(D.punto_pi(Fraction(3, 2))), "sen(3pi/2) = -1"


def test_el_texto_no_anade_el_ya_a_un_conjunto_que_es_toda_la_recta():
    """`ℝ` needs no explaining, and `ℝ  y se repite cada 2·π` is noise."""
    assert I.dominio(mx.parse("sin(x)")).texto() == "\u211d"
    assert I.dominio(mx.parse("atan(x)")).texto() == "\u211d"
