# SPDX-License-Identifier: MIT
"""Los huecos declarados en la documentación, aflojados para que avisen.

Tres etiquetas de `MATH_LAB.md` llevaban meses diciendo que faltaba algo que ya
existía, y se contradecían con su propio fichero: `T-18` figuraba como cerrado
cuatro líneas después de la línea que lo declaraba parcial. Corregidas el
2026-10-04 contra el motor, no contra la memoria.

Lo que queda es poco y está aquí: dos integrales hiperbólicas, la sustitución
``t = tg(x/2)`` en la integración, y los dos puntos donde la descomposición en
fracciones parciales se topa con algo que no es una división. Estas pruebas existen
para que, el día que se cierren, **fallen**. Un hueco documentado que nadie puede
ver cerrarse es un hueco que acaba mintiendo solo otra vez, y esta vez por escrito
y con la fecha al lado.
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


#: Lo que se dice que falta de T-14. VACÍO desde 2026-10-04: las dos que faltaban
#: están en HIPERBOLICAS_CERRADAS. Se deja la lista porque una lista vacía que se ve
#: vacía informa de lo mismo que una llena, y porque la alarma sigue conectada.
HIPERBOLICAS_FALTAN: list[str] = []

#: The two that were missing until 2026-10-04. Neither is the derivative of
#: something already in the table, which is why they were missing and not something
#: somebody forgot: `d/du arctg(senh u) = cosh/(1+sinh^2) = cosh/cosh^2 = 1/cosh`,
#: and `d/du log|tanh(u/2)| = 1/(2*senh(u/2)*cosh(u/2)) = 1/senh`.
HIPERBOLICAS_CERRADAS = [
    "sech(x)",
    "csch(x)",
]


@pytest.mark.parametrize("integrando", HIPERBOLICAS_CERRADAS)
def test_las_dos_integrales_que_faltaban_de_T14_ya_estan(integrando):
    """Cerradas, y cerradas por la única comprobación que decide: derivar.

    La primitiva no se comprueba como texto: se deriva y se compara con el
    integrando, porque una entrada de tabla que se lee bien y no se diferencia a su
    integrando es peor que un rechazo.
    """
    from academic_core.domain.engineering.mathlab import derive_mv

    primitiva, _paso = I.integrate(mx.to_symbolic(mx.parse(integrando)), "x",
                                   I.StepLog())
    diferencia = derive_mv.differentiate(mx.from_symbolic(primitiva), "x")
    for x in (0.7, 1.3, 2.1):
        valor_derivada = mx.valor_real(diferencia, {"x": x})
        valor_integrando = mx.valor_real(mx.parse(integrando), {"x": x})
        assert valor_derivada is not None and valor_integrando is not None
        escala = max(1.0, abs(valor_integrando))
        assert abs(valor_derivada - valor_integrando) < 1e-9 * escala, (
            integrando, valor_derivada, valor_integrando)


def test_de_T14_no_falta_ninguna_integral():
    """The hole list of T-14, asserted empty, and that is the whole point of it.

    It is not a parametrised test over an empty list — pytest does not take that, and
    rightly. It is one assertion that says what the list is for: when an integral is
    missing, it goes in the list and the list stops being empty.
    """
    assert HIPERBOLICAS_FALTAN == [], HIPERBOLICAS_FALTAN

#: T-18. La sustitución del ángulo medio, cerrada el 2026-10-04. Antes era lo único
#: que quedaba abierto de la lista y el rechazo era honesto; estas dos se integraban
#: ya por la tabla o por partes, y ninguna de las dos por lo que las integraba.
MEDIO_ANGULO_CERRADAS = [
    "1/(1+cos(x))",
    "1/(cos(x)+cos(2*x))",
]

#: Lo que la descomposición en fracciones parciales NO alcanza todavía. No son huecos
#: de este commit: son los dos sitios donde la cuenta deja de ser una división, y
#: ambos son la razón por la que la etiqueta de T-18 dice PARCIAL y no COMPLETADA.
#:
#: |hueco|por qué|
#: |---|---|
#: |`∫du/(u²+1)`|la cuadrática irreducible sale con discriminante NEGATIVO, y su primitiva es `arctg(u)` — que la capa `symbolic` no tiene: no está en la lista de funciones del parser, ni en la tabla de derivadas, ni en el evaluador. mathlab sí lo deriva y sí lo evalúa, así que un `Fn('atan', u)` se IMPRIMIRÍA y no se podría VOLVER A LEER. Una traza que el lector no puede teclear no es una traza |
#: |`∫du/(u⁴+1)`|el denominador no tiene raíz racional, así que lo que queda tras dividir es un grado 4 irreductible. Partirlo en dos cuadráticas sobre Q es un sistema que hay que resolver, y hacerlo a medias —tratar las cuadráticas que salgan y tirar el resto— es como un integrador racional empieza a responder «a veces»|
TAN_DENOMINADOR_IRREDUCIBLE = [
    "1/(1+u^2)",
    "1/(2+cos(x))",
    "(2*u+1)/(u^2+1)",
    "1/(4*u^2+4*u+2)",
    "1/(u^2+u+1)",
    "sin(x)^2/(1+cos(x))",
]

CUARTICO_SIN_FACTOR_RACIONAL = [
    "1/(u^4+1)",
    "1/(u^4+u^2+1)",
    "(u+1)/(u^2+1)^2",
    "1/(cos(x)*cos(2*x))",
]


@pytest.mark.parametrize("integrando", MEDIO_ANGULO_CERRADAS)
def test_la_sustitucion_del_angulo_medio_ya_integra(integrando):
    """Cerradas, y cerradas por la única comprobación que decide: derivar.

    `∫1/(1+cos x) dx = tg(x/2)`: con `u = tg(x/2)`, `1 + cos x` es `2/(1+u²)` y el
    jacobiano `2du/(1+u²)` cancela exactamente lo que sobra, y queda `∫du`. Es la
    misma cuenta que en el solucionador de ecuaciones, y por el mismo motivo: es la
    sustitución que no necesita una idea nueva por ecuación.

    La primitiva no se comprueba como texto, porque un texto puede tener todos los
    términos bien escritos y el signo de todos invertido.
    """
    from academic_core.domain.engineering.symbolic import expr as SE
    from academic_core.domain.engineering.symbolic.integrate import StepLog

    primitiva, _paso = I.integrate(SE.parse(integrando), "x", StepLog())
    diferencia = derive_mv.differentiate(mx.from_symbolic(primitiva), "x")
    for j in range(-30, 31):
        x = j * 0.21
        valor_derivada = mx.valor_real(diferencia, {"x": x})
        valor_integrando = mx.valor_real(mx.parse(integrando), {"x": x})
        if valor_derivada is None or valor_integrando is None:
            continue
        escala = max(1.0, abs(valor_integrando))
        assert abs(valor_derivada - valor_integrando) < 1e-8 * escala, (
            integrando, x, valor_derivada, valor_integrando)


@pytest.mark.parametrize("integrando", TAN_DENOMINADOR_IRREDUCIBLE)
def test_la_cuadratica_de_discriminante_negativo_sigue_sin_arctg(integrando):
    """Si esto falla, `atan` entró en el lenguaje: actualiza la etiqueta de T-18.

    El rechazo es el correcto y no es una carencia del método: la descomposición en
    fracciones parciales funciona, y lo que sale necesita una función que la capa
    `symbolic` no tiene.
    """
    from academic_core.domain.engineering.symbolic import expr as SE

    with pytest.raises(Exception):
        I.integrate(SE.parse(integrando), "u" if "u" in integrando else "x",
                    I.StepLog())


@pytest.mark.parametrize("integrando", CUARTICO_SIN_FACTOR_RACIONAL)
def test_un_cuadratico_sin_raiz_racional_no_se_factorea_solo(integrando):
    """Si esto falla, el denominador de grado 4 se sabe partir en dos cuadráticas.

    La frontera está donde la aritmética deja de ser una división, y se dibuja
    antes de cruzarla.
    """
    from academic_core.domain.engineering.symbolic import expr as SE

    with pytest.raises(Exception):
        I.integrate(SE.parse(integrando), "u" if "u" in integrando else "x",
                    I.StepLog())


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