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