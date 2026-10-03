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

#: Inecuaciones cuyos puntos críticos NO son racionales. Antes eran un rechazo, y el
#: rechazo era porque la carta solo sabía colocar un punto crítico en la rejilla de
#: múltiplos de `pi`.
#:
#: Quitar el rechazo la PRIMERA vez dio tres respuestas FALSAS, porque la carta corta
#: sus huecos por `Punto.coeficiente` y un punto que es una expresión tiene coeficiente
#: CERO: todos los radicales iban a parar al origen.
#:
#: | inecuación | decía (mal) | |
#: |---|---|---|
#: | `x^2 - 2 > 0` | `∅` | dos fronteras donde hay dos raíces |
#: | `x^3 - 2x > 0` | `(-∞, 0)` | los agujeros de `±√2` desaparecieron |
#: | `2x^3 - 3x + 1 > 0` | `(-∞, 0) ∪ (1, ∞)` | dos fronteras donde hay tres |
#:
#: Ninguna de las tres se anunció como dudosa. La carta ahora corta por los puntos y
#: muestrea por su VALOR, y lo que la sujeta a eso es esta prueba.
INEQUIDADES_RAIZ_IRRACIONAL = [
    "x^2 - 2 > 0", "x^2 - 2 < 0", "x^3 - 2*x > 0", "x^3 - 2*x < 0",
    "2*x^3 - 3*x + 1 > 0", "2*x^3 - 3*x + 1 < 0",
]


@pytest.mark.parametrize("inequidad", INEQUIDADES_RAIZ_IRRACIONAL)
def test_la_carta_no_inventa_ni_omite_un_punto(inequidad):
    """Sonido y completitud a la vez, comparando el conjunto publicado con el signo.

    Dos preguntas en una, porque un conjunto puede contestar solo a una de las dos: un
    intervalo publicado donde la inecuación no se cumple es una solución falsa, y un
    punto donde sí se cumple y el conjunto no contiene es una omisión. La rejilla se
    compara por los dos lados en cada punto, que es la única manera de ver un tramo
    omitido: una carta que perdió `±√2` en silencio sigue teniendo aspecto de respuesta.
    """
    import re
    from fractions import Fraction

    from academic_core.domain.engineering.mathlab import dominio as D
    from academic_core.domain.engineering.mathlab import inequaciones as I
    from academic_core.domain.engineering.mathlab import mvexpr as M

    izquierda, operador, derecha = re.split(r"(<=|>=|<|>|=)", inequidad,
                                           maxsplit=1)
    expresion = M.parse(f"({izquierda.strip()}) - ({derecha.strip()})")
    conjunto = I._carta_aperiodica(expresion, "x", operador)
    assert conjunto is not None, inequidad

    def se_cumple(x: float):
        valor = M.valor_real(expresion, {"x": x})
        if valor is None:
            return None
        return {"<": valor < 0, ">": valor > 0,
                "<=": valor <= 0, ">=": valor >= 0}[operador]

    falsos, omitidos = [], []
    for j in range(-600, 601):
        x = j * 0.02
        cumple = se_cumple(x)
        if cumple is None:
            continue
        dentro = conjunto.contiene(
            D.Punto(expresion=M.Num(Fraction(x).limit_denominator(10 ** 9))))
        if cumple and not dentro:
            omitidos.append(round(x, 3))
        if dentro and not cumple:
            falsos.append(round(x, 3))
    assert not falsos, f"{inequidad}: publica {falsos[:4]}, que no la cumplen"
    assert not omitidos, f"{inequidad}: no publica {omitidos[:4]}"


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