# SPDX-License-Identifier: MIT
"""Los huecos declarados en la documentación, aflojados para que avisen.

Tres etiquetas de `MATH_LAB.md` llevaban meses diciendo que faltaba algo que ya
existía, y se contradecían con su propio fichero: `T-18` figuraba como cerrado
cuatro líneas después de la línea que lo declaraba parcial. Corregidas el
2026-10-04 contra el motor, no contra la memoria.

Lo que queda es poco y está aquí: dos integrales hiperbólicas y la sustitución
``t = tg(x/2)`` en la integración. Estas pruebas existen para que, el día que se
cierren, **fallen**. Un hueco documentado que nadie puede ver cerrarse es un hueco
que acaba mintiendo solo otra vez, y esta vez por escrito y con la fecha al lado.
"""

from __future__ import annotations

import pytest

from academic_core.domain.engineering.mathlab import derive_mv
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.symbolic import integrate as I


def integra(texto: str):
    primitiva, _paso = I.integrate(mx.to_symbolic(mx.parse(texto)), "x",
                                   I.StepLog())
    return mx.from_symbolic(primitiva)


#: (integral, porque se dice que falta) — T-14, las dos hiperb-olicas que faltan
HIPERBOLICAS_FALTAN = [
    "sech(x)",
    "csch(x)",
]

#: T-18, el único punto abierto de la lista: la sustitución del ángulo medio
MEDIO_ANGULO_FALTA = [
    "1/(1+cos(x))",
    "1/(cos(x)+cos(2*x))",
]

#: Inequalities whose critical points are NOT rational, and where the sign chart
#: refuses. This list exists because of what happened when somebody removed the
#: refusal: the chart answered, and answered WRONG.
#:
#: The chart builds its intervals from the points it is given, and it silently
#: DISCARDED the ones that are neither a rational nor a multiple of `pi`. So it
#: drew a chart with two boundaries where there are four and reported it as a
#: solution:
#:
#: | inecuación | decía | verdad |
#: |---|---|---|
#: | `x^2 - 2 > 0` | `∅` | `(-inf, -sqrt(2)) ∪ (sqrt(2), +inf)` |
#: | `x^3 - 2x > 0` | `(-inf, 0)` | `(-sqrt(2), 0) ∪ (sqrt(2), +inf)` |
#: | `2x^3 - 3x + 1 > 0` | `(-inf, 0) ∪ (1, +inf)` | `(-inf, -0.618) ∪ (1.618, +inf)` |
#:
#: An empty answer and a half answer are both worse than «no lo sé», and the
#: refusal is what the engine does today. So `completar=False` in
#: `ceros_en_puntos` is not laziness: it is the thing standing between the chart
#: and those three rows.
INEQUIDADES_RAIZ_IRRACIONAL = [
    "x^2 - 2 > 0",
    "x^3 - 2*x > 0",
    "2*x^3 - 3*x + 1 > 0",
]


@pytest.mark.parametrize("inequidad", INEQUIDADES_RAIZ_IRRACIONAL)
def test_una_carta_de_signos_sin_todos_los_ceros_se_niega(inequidad):
    """Si esto falla, la carta ya coloca los puntos que son expresiones: bien.

    Y entonces hay que mirar lo que devuelve antes de quitar la prueba, porque las
    tres respuestas de la tabla de arriba salieron de exactamente este camino y
    ninguna se anunció como dudosa: se publican con la misma seguridad que una
    acertada. La prueba está puesta para que el día que se cierre el hueco avise.
    """
    from academic_core.domain.engineering.mathlab import inequaciones as I

    with pytest.raises(Exception):
        I.resolver_inequidad(inequidad)


@pytest.mark.parametrize("integrando", HIPERBOLICAS_FALTAN)
def test_las_dos_integrales_que_faltan_de_T14_siguen_faltando(integrando):
    """Si esto falla, `sech` y `csch` ya se integran: actualiza la etiqueta.

    Las seis **derivadas** de la familia existen desde hace tiempo y la etiqueta
    de T-14 llegó a decir que no. Lo que falta son dos integrales, y son estas.
    """
    with pytest.raises(Exception):
        integra(integrando)


@pytest.mark.parametrize("integrando", MEDIO_ANGULO_FALTA)
def test_la_sustitucion_del_angulo_medio_sigue_sin_integrar(integrando):
    """Si esto falla, `t = tg(x/2)` se integra: actualiza la etiqueta de T-18.

    Es lo último que quedaba abierto de T-18. Todo lo demás de esa familia
    responde: reducción de potencias de seno, coseno y tangente, partes
    encadenadas para logaritmos, y las recíprocas.
    """
    with pytest.raises(Exception):
        integra(integrando)


@pytest.mark.parametrize("expresion,derivada", [
    ("sinh(x)", "cosh(x)"),
    ("cosh(x)", "sinh(x)"),
    ("tanh(x)", "1/cosh(x)^2"),
    ("coth(x)", "-1/sinh(x)^2"),
    ("sech(x)", "-sech(x)*tanh(x)"),
    ("csch(x)", "-csch(x)*coth(x)"),
])
def test_las_seis_derivadas_de_T14_existen_de_verdad(expresion, derivada):
    """La mitad de T-14 que la etiqueta negaba, afirmada para que no se pueda
    volver a negar por descuido.

    Una etiqueta que dice «faltan las derivadas» es una afirmación sobre el motor
    que se puede comprobar en una línea. Comprobada, era falsa.
    """
    from academic_core.domain.engineering.mathlab import verify as V

    d = derive_mv.differentiate(mx.parse(expresion), "x")
    iguales, _, _ = V.check_equivalence(d, mx.parse(derivada))
    assert iguales, f"d/dx {expresion} = {mx.text(d)}, no {derivada}"