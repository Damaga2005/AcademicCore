# SPDX-License-Identifier: MIT
"""Los huecos declarados en la documentación, aflojados para que avisen.

Tres etiquetas de `MATH_LAB.md` llevaban meses diciendo que faltaba algo que ya
existía, y se contradecían con su propio fichero: `T-18` figuraba como cerrado
cuatro líneas después de la línea que lo declaraba parcial. Corregidas el
2026-10-04 contra el motor, no contra la memoria.

Lo que queda está aquí, y es poco: las integrales hiperbólicas de T-14, la
sustitución ``t = tg(x/2)``, el discriminante negativo de T-18, y **un solo**
punto donde la descomposición en fracciones parciales se topa con algo que no es
una división —el cuartico sin raíz racional, que no se sabe partir en dos
cuadráticas sobre ℚ.

Estas pruebas existen para que, el día que se cierren, **fallen**. Un hueco
documentado que nadie puede ver cerrarse es un hueco que acaba mintiendo solo otra
vez, y esta vez por escrito y con la fecha al lado. Han saltado cuatro veces en un
solo día, y en las cuatro la lista estaba diciendo la verdad mientras el motor ya
había cambiado.
"""

from __future__ import annotations

from fractions import Fraction

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

#: T-18, cierre del 2026-10-04. Antes eran un rechazo y el rechazo era honesto: la
#: descomposición en fracciones parciales llegaba hasta el final y lo que salía era
#: `arctg(u)`, una función que la capa `symbolic` no tenía —ni en el parser, ni en el
#: evaluador—, así que el motor la IMPRIMÍA y no podía VOLVER A LEERLA.
#:
#: Lo que se añadió no fue una función nueva sino un nombre que ya existía: `atan` (y
#: las quince de su familia) estaban en la tabla de DERIVADAS desde T-17, de modo que
#: el motor sabía derivar `arctg` que no sabía escribir. Cerrado, y cerrado por la
#: única comprobación que decide: derivar la primitiva y compararla con el integrando.
CUADRATICA_NEGATIVA_CERRADAS = [
    "1/(1+u^2)",
    "1/(2+cos(x))",
    "(2*u+1)/(u^2+1)",
    "1/(4*u^2+4*u+2)",
    "1/(u^2+u+1)",
]

#: T-18, segundo cierre del 2026-10-04. La cuadrática irreducible **al cuadrado**
#: se negaba porque `_como_racional` escribe `(u²+1)²` como `u⁴ + 2u² + 1`, un
#: grado 4 sin raíz racional, y `_factores` solo miraba raíces racionales: veía un
#: cuartico y el cuartico sin raíz racional es la parte sin resolver de este módulo.
#: Pero el polinomio que llegaba nunca fue un cuartico, era una cuadrática escrita dos
#: veces, y nadie miró a ver si lo era.
#:
#: Ahora `_factores` hace la descomposición squarefree (Musser) antes de negarse.
CUADRATICA_AL_CUADRADO_CERRADAS = [
    "1/(u^2+1)^2",
    "(u+1)/(u^2+1)^2",
    "(2*u+1)/(u^2+1)^2",
    "u/(u^2+1)^2",
    "1/(u^2+1)^3",
    "1/(u^2+1)^4",
    "sin(x)^2/(1+cos(x))",
    "cos(x)^2/(1+sin(x))",
]

#: T-18, tercer cierre del 2026-10-04. El cuartico sin raíz racional, el último
#: límite declarado de la lista.
#:
#: No era un problema de método sino de clase: `∫du/(u⁴+1)` se negaba porque el
#: denominador no tiene raíz racional, y `_factores` solo miraba raíces racionales.
#: La salida existe y es exacta —un biquadrático se parte como
#: `(u²+pu+q)(u²-pu+q)` con `q = √c` y `p² = 2q-a`—, pero había que llevarla.
#:
#: El detalle que la hace posible sin aritmética de cuerpos: `q` se exige racional,
#: así que el único irracional es `p`, y en la respuesta **solo un coeficiente lo
#: necesita**. Con `(Au²+C)/B` salen `α = (C/q - A)/(2p)` y `β = C/(2q)`, y
#: `β - α·p/2` se simplifica a `(A + C/q)/4`, que es **racional**. Un radical, y
#: `√(p²)·t` es un producto, no un tipo nuevo.
CUARTICO_BIQUADRATICO_CERRADAS = [
    "1/(u^4+1)",
    "1/(u^4+u^2+1)",
    "1/(u^4-6*u^2+1)",
    "1/(u^4-u^2+1)",
    "1/(u^4+4)",
    "1/(u^4+u^2)",
    "u^2/(u^4+1)",
    "(u^2+1)/(u^4+1)",
    "(3*u^2+2)/(u^4+1)",
    "5/(u^4+1)",
    "1/(cos(x)*cos(2*x))",   # con u = tg(x/2) llega a (u²-1)(u⁴-6u²+1)
]

#: Lo que NO se alcanza, y es una clase distinta, no un resto del mismo problema.
#: Cada uno dice por qué, porque un rechazo sin motivo no es un límite: es un «no
#: sé» disfrazado de frontera.
#:
#: |hueco|por qué|
#: |---|---|
#: |`√c` irracional|la clase necesita `q = √c` racional para que sobre un solo radical. Con `c = 2` hacen falta dos, y el reparto de coeficientes ya no cabe en una expresión|
#: |denominador no mónico|la fórmula lee `a` y `c` del denominador y supone coeficiente principal 1. `3u⁴+2` no es `u⁴+2`, y contestaría por una integral distinta|
#: |`(u²+1)²`|una potencia del biquadrático: no es el mismo reparto, es otro sistema|
#: |numerador con potencias impares|un numerador impar sobre un denominador par no se reparte en dos cuadráticas con la misma simetría|
CUARTICO_FUERA_DE_CLASE = [
    "1/(u^4+2)",        # √2 irracional
    "1/(u^4-2)",        # c < 0: tiene raíces reales y es caso de `_factores`
    "1/(3*u^4+2)",      # no mónico
    "1/(u^4+1)^2",     # potencia
    "u/(u^4+1)",        # numerador impar
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


@pytest.mark.parametrize("integrando", CUADRATICA_NEGATIVA_CERRADAS)
def test_la_cuadratica_de_discriminante_negativo_ya_integra(integrando):
    """Cerradas el 2026-10-04, y cerradas por la única comprobación que decide: derivar.

    `∫du/(u²+1)` es `arctg(u)`, y su dominio entero es una sola hoja: no hay
    intervalos que repartir, ni rama que elegir, ni `k·pi` que añadir. Se comprueba
    derivando en 81 puntos y comparando con el integrando, no comparando el texto,
    porque un texto puede tener todos los términos bien escritos y el signo de todos
    invertido.
    """
    from decimal import Decimal

    from academic_core.domain.engineering.symbolic import derive as D
    from academic_core.domain.engineering.symbolic import expr as SE
    from academic_core.domain.engineering.symbolic import numeric

    var = "u" if "u" in integrando else "x"
    integrando_parsed = SE.parse(integrando)
    primitiva, _paso = I.integrate(integrando_parsed, var, I.StepLog())
    derivada, _s = D.differentiate(primitiva, var, I.StepLog())
    for j in range(-40, 41):
        punto = Decimal(j) * Decimal("0.17")
        valor_derivada = numeric.value(derivada, {var: punto})
        valor_integrando = numeric.value(integrando_parsed, {var: punto})
        if valor_derivada is None or valor_integrando is None:
            continue
        escala = max(Decimal(1), abs(valor_integrando))
        assert abs(valor_derivada - valor_integrando) < Decimal("1e-12") * escala, (
            integrando, punto, valor_derivada, valor_integrando)


@pytest.mark.parametrize("integrando", CUADRATICA_AL_CUADRADO_CERRADAS)
def test_una_cuadratica_irreducible_al_cuadrado_ya_integra(integrando):
    """Cerradas, y cerradas por la única comprobación que decide: derivar.

    Los ocho van a parar al mismo denominador —`(u²+1)` repetido— y por eso se
    comprueban juntos: la descomposición squarefree es lo que hay que medir, y
    medirla en un solo caso sería medir un caso.
    """
    from decimal import Decimal

    from academic_core.domain.engineering.symbolic import derive as D
    from academic_core.domain.engineering.symbolic import expr as SE
    from academic_core.domain.engineering.symbolic import numeric

    var = "u" if "u" in integrando else "x"
    integrando_parsed = SE.parse(integrando)
    primitiva, _paso = I.integrate(integrando_parsed, var, I.StepLog())
    derivada, _s = D.differentiate(primitiva, var, I.StepLog())
    for j in range(-40, 41):
        punto = Decimal(j) * Decimal("0.17")
        valor_derivada = numeric.value(derivada, {var: punto})
        valor_integrando = numeric.value(integrando_parsed, {var: punto})
        if valor_derivada is None or valor_integrando is None:
            continue
        escala = max(Decimal(1), abs(valor_integrando))
        assert abs(valor_derivada - valor_integrando) < Decimal("1e-12") * escala, (
            integrando, punto, valor_derivada, valor_integrando)


def test_la_frontera_que_queda_no_es_la_de_antes():
    """La frontera se movió, y hay que decir a dónde en vez de repetirla.

    Se comprueban las dos mitades por separado a propósito, porque la forma de
    fallar de este cambio no sería «integrar de más» sino **integrar de más sin
    decirlo**: un motor que empieza a responder «a veces» es peor que uno que se
    niega. Lo que sigue negándose ya no es «el cuartico» sino clases concretas, y
    cada una con su motivo.
    """
    from academic_core.domain.engineering.symbolic import expr as SE

    # Los biquadráticos de la clase INTEGRAN, y quien se niega es el FACTORIZADOR.
    #
    # `_factores` sigue devolviendo None para un cuartico sin raíz racional,
    # porque el reparto lo hace la rutina de integral y no la factorizadora. Es
    # una distinción real y no un detalle: afirmar aquí que «se factoriza» sería
    # una afirmación sobre el código que nadie comprobó.
    for integrando in ("1/(u^4+1)", "1/(u^4+u^2+1)", "1/(u^4-6*u^2+1)"):
        _num, den = I._como_racional(SE.parse(integrando), "u")
        assert I._factores(den) is None, integrando
        _num, resto = I._p_parte_entera(_num, den)
        assert I._integral_bicuadratica_de(resto, den, SE.Sym("u")) is not None, integrando

    # y la potencia de una cuadrática sigue reagrupándose
    _num, den = I._como_racional(SE.parse("1/(u^2+1)^2"), "u")
    factores = I._factores(den)
    assert factores is not None and len(factores) == 1
    factor, multiplicidad = factores[0]
    assert multiplicidad == 2
    assert factor == {2: Fraction(1), 0: Fraction(1)}

    # lo que NO se alcanza es por CLASE, y cada clase se niega por su motivo
    for fuera_de_clase in CUARTICO_FUERA_DE_CLASE:
        with pytest.raises(Exception):
            I.integrate(SE.parse(fuera_de_clase), "u", I.StepLog())


@pytest.mark.parametrize("integrando", CUARTICO_BIQUADRATICO_CERRADAS)
def test_el_cuadratico_sin_raiz_racional_ya_integra(integrando):
    """Cerradas, y cerradas por la única comprobación que decide: derivar.

    Y por una segunda, que este casoes propio: la respuesta tiene que PODER
    RELEERSE. El primer intento daba una correcta de 318 caracteres, y
    `expr.parse` corta en 256 — una respuesta que el lector no puede teclear no
    es una respuesta, por muy exacta que sea. Se llega aquí quitando el término
    de coeficiente cero, que no acortaba nada y costaba medio texto.
    """
    from decimal import Decimal

    from academic_core.domain.engineering.symbolic import derive as D
    from academic_core.domain.engineering.symbolic import expr as SE
    from academic_core.domain.engineering.symbolic import numeric

    var = "u" if "u" in integrando else "x"
    integrando_parsed = SE.parse(integrando)
    primitiva, _paso = I.integrate(integrando_parsed, var, I.StepLog())
    derivada, _s = D.differentiate(primitiva, var, I.StepLog())
    texto = SE.text(primitiva)
    assert SE.parse(texto) is not None, (integrando, texto)
    for j in range(-40, 41):
        punto = Decimal(j) * Decimal("0.17")
        valor_derivada = numeric.value(derivada, {var: punto})
        valor_integrando = numeric.value(integrando_parsed, {var: punto})
        if valor_derivada is None or valor_integrando is None:
            continue
        escala = max(Decimal(1), abs(valor_integrando))
        assert abs(valor_derivada - valor_integrando) < Decimal("1e-12") * escala, (
            integrando, punto, valor_derivada, valor_integrando)


@pytest.mark.parametrize("integrando", CUARTICO_FUERA_DE_CLASE)
def test_un_cuadratico_fuera_de_clase_sigue_sin_integrarse(integrando):
    """Cada uno se niega por SU motivo, y por eso la lista lleva el motivo.

    Un rechazo sin motivo escrito no es una frontera, es una ignorancia con
    forma de límite. Y los motivos son distintos: uno es de clase, otro de forma
    del denominador, otro de sistema.
    """
    from academic_core.domain.engineering.symbolic import expr as SE

    with pytest.raises(Exception):
        I.integrate(SE.parse(integrando), "u", I.StepLog())


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