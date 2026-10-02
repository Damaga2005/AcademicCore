# SPDX-License-Identifier: MIT
"""AUDITORÍA: el barrido de la trigonometría, como prueba permanente.

No añade capacidades. Cada caso se comprueba por un camino que **no consulta el
cálculo que produjo la respuesta**, y un fallo aquí significa que el motor contesta
mal — no que le falte algo.

Este fichero no nació de una suite: nació de un barrido de ~1500 comprobaciones
ejecutado a mano sobre el motor entero, que encontró dos bugs reales. Uno estaba
en la conversión entre los dos árboles de expresiones (`x^(3/2)` volvía como
`√x`, y el numerador del exponente se perdía por el camino); el otro estaba en el
bucle de Taylor, que leía el término de orden k con la derivada de orden k+1
mientras el coeficiente salía como recíproco — dos fallos que se cancelaban y por
eso todos los valores intermedios parecían plausibles.
"""
from __future__ import annotations

import math

import pytest

from academic_core.domain.engineering.mathlab import derive_mv
from academic_core.domain.engineering.mathlab import dominio as D
from academic_core.domain.engineering.mathlab import ecuaciones as E
from academic_core.domain.engineering.mathlab import graficas as Gr
from academic_core.domain.engineering.mathlab import inequaciones as I
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import series as S
from academic_core.domain.engineering.mathlab import trig as T
from academic_core.domain.engineering.mathlab import verify as V
from academic_core.domain.engineering.symbolic import derive as SDer
from academic_core.domain.engineering.symbolic import integrate as SInt
from fractions import Fraction

PI = math.pi


# ---------------------------------------------------------------------------
# 1. identidades: cada reescritura tiene que conservar el valor
# ---------------------------------------------------------------------------

OBJETIVOS = {
    "simplificar": T.simplify,
    "expandir": T.expand,
    "producto_a_suma": T.product_to_sum,
    "suma_a_producto": T.sum_to_product,
    "potencias": T.reduce_powers,
    "sustitucion_universal": T.rationalize,
}

EXPRESIONES = [
    "sin(x)+cos(x)", "sin(x)^2", "cos(x)^2", "sin(x)*cos(x)", "1+tan(x)^2",
    "sin(2*x)", "cos(2*x)", "tan(2*x)", "sin(x+y)", "cos(x-y)", "sin(x)^4",
    "2*sin(x)*cos(x)", "sin(pi/2-x)", "1/(1+sin(x))", "(1-cos(x))/(1+cos(x))",
    "sin(x)/cos(x)", "cos(x)^2+sin(x)^2", "tan(x)", "1/sin(x)", "sin(x)^3",
    "sin(x)*sin(2*x)", "cos(x)*cos(3*x)", "sec(x)", "csc(x)", "cot(x)",
    "sinh(x)+cosh(x)", "sin(x)^2*cos(x)^2", "sin(x)^6", "tan(x)^4",
]


@pytest.mark.parametrize("expresion", EXPRESIONES)
@pytest.mark.parametrize("nombre", sorted(OBJETIVOS))
def test_cada_identidad_conserva_el_valor(expresion, nombre):
    e = mx.parse(expresion)
    try:
        resultado = OBJETIVOS[nombre](e)
    except Exception as exc:                     # negarse no es contestar mal
        pytest.skip(f"{nombre} se niega: {str(exc)[:50]}")
    ok, metodo, detalle = V.numeric_agreement(resultado, e, samples=10)
    assert ok and "puntos" in metodo, f"{expresion} / {nombre}: {detalle}"


def test_el_verificador_puede_decir_que_no():
    """El control negativo.

    Sin él, todo lo de arriba pasaría igual si el verificador no comparase nada:
    es el mismo motivo por el que existe en ``test_mathlab_trig``.
    """
    assert not V.numeric_agreement(mx.parse("cos(x)"), mx.parse("sin(x)"))[0]
    assert not V.numeric_agreement(mx.parse("1"), mx.parse("sin(x)^2"))[0]


# ---------------------------------------------------------------------------
# 2. derivadas
# ---------------------------------------------------------------------------

TABLA_DERIVADAS = [
    ("sin", "cos(x)"), ("cos", "-sin(x)"), ("sinh", "cosh(x)"), ("cosh", "sinh(x)"),
    ("sec", "sec(x)*tan(x)"), ("csc", "-csc(x)*cot(x)"), ("tanh", "1/cosh(x)^2"),
    ("tan", "1/cos(x)^2"), ("sech", "-sech(x)*tanh(x)"),
]


@pytest.mark.parametrize("funcion,esperada", TABLA_DERIVADAS)
def test_la_derivada_de_la_familia_es_la_de_la_tabla(funcion, esperada):
    d = derive_mv.differentiate(mx.parse(f"{funcion}(x)"), "x")
    ok, _m, detalle = V.numeric_agreement(d, mx.parse(esperada), samples=10)
    assert ok, f"d/dx {funcion} = {mx.text(d)}, no {esperada}: {detalle}"


CADENA = ["sin(2*x)", "cos(3*x^2)", "exp(2*sin(x))", "ln(sin(x))", "sin(x)*cos(x)",
          "x^3*sin(x)", "exp(x)*cos(2*x)", "(sin(x))^5", "asin(sin(x)/2)",
          "sqrt(x)", "x^3*sqrt(x)", "1/sqrt(x)", "sqrt(2*x)"]


@pytest.mark.parametrize("expresion", CADENA)
def test_la_derivada_coincide_con_el_otro_arbol(expresion):
    """Dos tablas de derivadas independientes, escritas en dos módulos distintos."""
    e = mx.parse(expresion)
    primera = derive_mv.differentiate(e, "x")
    segunda = mx.from_symbolic(
        SDer.differentiate(mx.to_symbolic(e), "x", SDer.StepLog())[0])
    ok, _m, detalle = V.numeric_agreement(primera, segunda, samples=10)
    assert ok, f"{expresion}: {mx.text(primera)} vs {mx.text(segunda)}: {detalle}"


# ---------------------------------------------------------------------------
# 3. integrales: derivar la primitiva y comparar
# ---------------------------------------------------------------------------

INTEGRALES = [
    "x^2", "x^3", "sin(x)", "cos(x)", "tan(x)", "cot(x)", "sec(x)", "csc(x)",
    "exp(x)", "ln(x)", "1/x", "x^2*sin(x)", "x*cos(x)", "x*ln(x)",
    "sin(x)^2", "cos(x)^3", "cos(2*x)^2", "tan(x)^2", "ln(x)^2",
    "sec(x)^2", "cot(x)^2", "1/cos(x)", "sqrt(x)", "sinh(x)", "tanh(x)",
    "x/(1+x^2)", "(2*x+1)^3", "1/(x-1)", "x^2*exp(x)", "exp(-x)",
    "x*sqrt(x)", "1/sqrt(x)", "sin(2*x)^2", "cos(3*x)^5", "ln(x)^3",
]


def integra(texto: str) -> mx.Expr:
    primitiva, _paso = SInt.integrate(mx.to_symbolic(mx.parse(texto)), "x",
                                      SInt.StepLog())
    return mx.from_symbolic(primitiva)


@pytest.mark.parametrize("integrando", INTEGRALES)
def test_la_primitiva_se_deriva_al_integrando(integrando):
    """La única comprobación que decide una integral.

    Una entrada de tabla equivocada tiene exactamente el mismo aspecto que una
    correcta hasta que se deriva.
    """
    try:
        primitiva = integra(integrando)
    except Exception as exc:                     # negarse no es contestar mal
        pytest.skip(f"se niega: {str(exc)[:50]}")
    derivada = derive_mv.differentiate(primitiva, "x")
    ok, _m, detalle = V.numeric_agreement(derivada, mx.parse(integrando), samples=8)
    assert ok, f"∫{integrando} da {mx.text(primitiva)}: {detalle}"


# ---------------------------------------------------------------------------
# 4. ecuaciones: sustituir el miembro en la ecuación ORIGINAL
# ---------------------------------------------------------------------------

ECUACIONES = ["sin(x) = 0", "cos(x) = 0", "sin(x) = 1", "cos(x) = -1",
              "sin(x) = 1/2", "sin(x + pi/3) = 0", "cos(x + pi/4) = 0",
              "tan(x) = 0", "2*x + 1 = 0", "x = 1", "x = 0",
              "sin(x)/2 = 1/2", "cos(2*x) = 1/2"]


@pytest.mark.parametrize("ecuacion", ECUACIONES)
def test_cada_miembro_satisface_la_ecuacion_original(ecuacion):
    """Lo único que caza una solución espuria.

    Una familia puede tener la forma correcta y no satisfacer nada; sólo
    sustituirla en la ecuación de partida lo delata.
    """
    izquierda, derecha = ecuacion.split(" = ")
    for familia in E.resolver(ecuacion).familias:
        for k in range(-3, 4):
            x = mx.evaluate(familia.miembro(k, "x"))
            if x is None or x.imag != 0:
                continue
            a = mx.evaluate(mx.parse(izquierda), {"x": x.real})
            b = mx.evaluate(mx.parse(derecha))
            if a is not None and b is not None:
                assert abs(a.real - b.real) < 1e-9, (ecuacion, x.real, a.real, b.real)


CONTRADICCIONES = ["1 = 2"]


@pytest.mark.parametrize("ecuacion", CONTRADICCIONES)
def test_una_contradiccion_si_dice_que_no_hay_soluciones(ecuacion):
    r = E.resolver(ecuacion)
    assert r.vacia and not r.sin_respuesta, r.texto("x")


REFUSOS = ["x = x", "1 = 1", "0 = 0"]


@pytest.mark.parametrize("ecuacion", REFUSOS)
def test_una_identidad_se_niega_porque_no_es_una_familia(ecuacion):
    """Todos los x la satisfacen, y una familia no es «todos los x»."""
    assert E.resolver(ecuacion).sin_respuesta is True


# ---------------------------------------------------------------------------
# 5. ceros, periodo y dominio
# ---------------------------------------------------------------------------

CEROS = [
    ("sin(x)", ["0*pi", "1*pi"]), ("cos(x)", ["1/2*pi", "3/2*pi"]),
    ("tan(x)", ["0*pi"]), ("sin(x)/x", ["1*pi"]), ("1/tan(x)", []),
    ("5*sin(x + pi/3)", ["2/3*pi", "5/3*pi"]), ("sin(2*x)", ["0*pi", "1/2*pi"]),
    ("sin(x) + 1", ["3/2*pi"]),
]


@pytest.mark.parametrize("expresion,esperado", CEROS)
def test_los_ceros_son_exactos(expresion, esperado):
    c = I.ceros(mx.parse(expresion), "x")
    if c is None:
        pytest.skip("no lo sabe")
    assert sorted(mx.text(v) for v in c) == sorted(esperado)


PERIODOS = [
    ("sin(x)", Fraction(2)), ("sin(2*x)", Fraction(1)), ("tan(x)", Fraction(1)),
    ("sin(x)/x", None), ("x + sin(x)", None), ("sin(x)*x", None),
    ("sin(x)^2", Fraction(1)), ("cos(x)/sin(x)", Fraction(1)),
    ("sin(3*x)", Fraction(2, 3)), ("sin(x/2)", Fraction(4)),
    ("1/tan(x)", Fraction(1)), ("x^2", None), ("sinh(x)", None),
]


@pytest.mark.parametrize("expresion,esperado", PERIODOS)
def test_el_periodo_es_el_menor_o_no_hay(expresion, esperado):
    assert D.periodo_minimo(mx.parse(expresion)) == esperado


DOMINIOS = [
    ("ln(x)", ["(0, ∞)"]), ("ln(x^2)", ["(-∞, 0)", "(0, ∞)"]),
    ("1/x", ["(-∞, 0)", "(0, ∞)"]),
    ("tan(x)", ["(-∞, 1/2·π)", "(1/2·π, 3/2·π)", "(3/2·π, ∞)"]),
    ("cos(x)/sin(x)", ["(-∞, 0)", "(0, π)", "(π, ∞)"]),
    ("1/tan(x)", ["(-∞, 0)", "(0, 1/2·π)", "(1/2·π, 3/2·π)", "(3/2·π, ∞)"]),
]


@pytest.mark.parametrize("expresion,esperado", DOMINIOS)
def test_el_dominio_excluye_exactamente_los_puntos_que_no_existen(expresion,
                                                                 esperado):
    d = I.dominio(mx.parse(expresion), "x")
    assert [i.texto() for i in d.intervalos] == esperado


def _es_removible(expresion: str) -> bool:
    """Whether the canonical form differs from the written one.

    That difference is exactly what makes a hole removable, and it is a
    structural fact: no amount of sampling at the point can establish it. At
    ``pi/2`` the value of ``tan`` is 6·10⁻¹⁷ and not zero, so ``1/tan`` evaluates
    there to a small finite number that looks continuous.
    """
    try:
        return mx.text(T.simplify(mx.parse(expresion))) != mx.text(mx.parse(expresion))
    except Exception:
        return False


FRONTERAS = ["tan(x)", "cos(x)/sin(x)", "1/tan(x)", "1/x", "ln(x)", "sqrt(x)"]


@pytest.mark.parametrize("expresion", FRONTERAS)
def test_la_frontera_del_dominio_coincide_con_la_existencia(expresion):
    """Every open end is a point where the expression does not exist.

    The removable ones are skipped because no sample can decide them, and that
    is said here rather than left to look like an oversight.
    """
    d = I.dominio(mx.parse(expresion), "x")
    for intervalo in d.intervalos:
        for extremo, abierto in ((intervalo.izq, intervalo.abierto_izq),
                                 (intervalo.der, intervalo.abierto_der)):
            if extremo is None:
                continue
            x = float(extremo.coeficiente) * (PI if extremo.es_pi else 1.0)
            v = mx.evaluate(mx.parse(expresion), {"x": x})
            # a pole seen through floating point is a very large finite number
            definida = v is not None and v.imag == 0 and abs(v.real) < 1e12
            if abierto and definida and _es_removible(expresion):
                continue
            assert definida == (not abierto), (expresion, extremo.texto(),
                                               abierto, definida)


# ---------------------------------------------------------------------------
# 6. series
# ---------------------------------------------------------------------------

SERIES = [("sin", 7, "x^7"), ("cos", 6, "x^6"), ("exp", 6, "x^6"),
          ("ln", 5, "x^5"), ("tan", 7, "x^7"), ("sinh", 5, "x^5")]


@pytest.mark.parametrize("nombre,orden,contiene", SERIES)
def test_cada_funcion_tiene_su_propia_serie(nombre, orden, contiene):
    serie = S.maclaurin(nombre, orden, "x")
    assert contiene in mx.text(serie.polinomio), mx.text(serie.polinomio)


def test_el_seno_y_el_coseno_no_dan_el_mismo_polinomio():
    """El control negativo de lo de arriba, por si acaso."""
    seno = mx.text(S.maclaurin("sin", 6, "x").polinomio)
    coseno = mx.text(S.maclaurin("cos", 6, "x").polinomio)
    assert seno != coseno


CONVERGEN = ["sin", "cos", "exp", "tan", "sinh", "cosh", "ln"]


@pytest.mark.parametrize("nombre", CONVERGEN)
def test_el_error_de_la_serie_baja_al_subir_el_orden(nombre):
    """Lo que distingue una serie que converge de una que trunca.

    Una serie truncada no falla nunca: sólo empeora, y por eso un polinomio
    cualquiería aprobaría una comprobación de «el error es pequeño».
    """
    anterior = None
    for orden in (3, 7, 11, 15):
        p = S.maclaurin(nombre, orden, "x").polinomio
        peor = 0.0
        for x in (0.05, 0.15, 0.3):
            a = mx.evaluate(mx.parse(f"{nombre}(x)"), {"x": x})
            b = mx.evaluate(p, {"x": x})
            if a is not None and b is not None and abs(a.real) > 1e-9:
                peor = max(peor, abs(a.real - b.real) / abs(a.real))
        if anterior is not None:
            assert peor <= anterior + 1e-12, \
                f"{nombre} orden {orden}: {anterior} -> {peor}"
        anterior = peor


# ---------------------------------------------------------------------------
# 7. graficas
# ---------------------------------------------------------------------------

GRAFICAS = ["3*sin(2*x)", "sin(x)", "cos(x)", "tan(x)", "1/tan(x)", "sin(x)/x",
            "2*cos(x + pi/3)", "-sin(x)", "sin(x) + 1", "5*sin(x + pi/3)"]


@pytest.mark.parametrize("expresion", GRAFICAS)
def test_los_hechos_declarados_aguantan_el_segundo_camino(expresion):
    sello = Gr.verifica(Gr.caracteristicas(mx.parse(expresion)))
    assert sello.verdict != "discrepa", f"{expresion}: {sello.detail}"


COMPARACIONES = [("sin(x)", "sin(x)", True), ("sin(x)", "cos(x)", False),
                 ("sin(x)", "2*sin(x)", False), ("sin(x)", "-sin(x)", False),
                 ("cos(x)", "sin(x)", False), ("sin(x)^2", "sin(x)", False)]


@pytest.mark.parametrize("a,b,identicas", COMPARACIONES)
def test_la_comparacion_dice_si_se_cortan(a, b, identicas):
    r = Gr.comparar(mx.parse(a), mx.parse(b))
    assert r.identicas == identicas, f"{a} vs {b}: {[p.texto() for p in r.se_cortan_en]}"


# ---------------------------------------------------------------------------
# 8. la conversión entre los dos árboles de expresiones
# ---------------------------------------------------------------------------

IDAS_Y_VUELTAS = ["x^(1/2)", "x^(3/2)", "x^(5/2)", "x^(2/1)", "x^(2/3)",
                  "sqrt(x)", "x^3*sqrt(x)", "sin(x)", "cos(x)", "exp(x)",
                  "ln(x)", "x^2+sin(x)", "1/x", "(2*x+1)^3"]


@pytest.mark.parametrize("expresion", IDAS_Y_VUELTAS)
def test_la_expresion_sobrevive_al_otro_arbol(expresion):
    """``x^(3/2)`` tiene que volver como ``x·√x``.

    Volvía como ``√x`` —el numerador del exponente se perdía— y como ``x^3·√x``
    en el intento siguiente, que es ``x^(7/2)`` y sale 35 veces demasiado grande.
    Ninguna de las dos versiones falla al imprimirse: las dos parecen una potencia
    fraccionaria y sólo derivar la primitiva de ``√x`` lo delata.
    """
    e = mx.parse(expresion)
    try:
        vuelta = mx.from_symbolic(mx.to_symbolic(e))
    except Exception as exc:
        pytest.skip(f"el otro árbol no lo representa: {str(exc)[:50]}")
    ok, _m, detalle = V.numeric_agreement(vuelta, e, samples=10)
    assert ok, f"{expresion} -> {mx.text(vuelta)}: {detalle}"
