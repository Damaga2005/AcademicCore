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
from fractions import Fraction

import pytest

from academic_core.domain.engineering.mathlab import complejos as K
from academic_core.domain.engineering.mathlab import derive_mv
from academic_core.domain.engineering.mathlab import dominio as D
from academic_core.domain.engineering.mathlab import ecuaciones as E
from academic_core.domain.engineering.mathlab import graficas as Gr
from academic_core.domain.engineering.mathlab import inequaciones as I
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import ramas as R
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
    ("cos(x)/sin(x)", ["(-∞, 0)", "(0, π)", "(π, 2·π)", "(2·π, ∞)"]),
    ("1/tan(x)", ["(-∞, 0)", "(0, 1/2·π)", "(1/2·π, π)", "(π, 3/2·π)",
                  "(3/2·π, ∞)"]),
]


@pytest.mark.parametrize("expresion,esperado", DOMINIOS)
def test_el_dominio_excluye_exactamente_los_puntos_que_no_existen(expresion,
                                                                 esperado):
    """The holes are exactly the points where the expression does not exist.

    ``cos(x)/sin(x)`` and ``1/tan(x)`` used to be published WITHOUT a hole at
    ``pi``, and these expectations pinned that: at ``pi`` they are ``-1/0`` and
    ``1/0``, which are not numbers. The omission came from ``ceros`` answering
    with ONE period, so the denominator ``tan(x)`` reported its zero at 0 and not
    at ``pi`` — the same point, which is the rule the sign chart already
    followed and the domain did not.

    A test that pins an output is a test that pins a bug. These are checked
    against what the expressions ARE, not against what they used to print.
    """
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


# ---------------------------------------------------------------------------
# 9. T-13: el conjunto publicado, en aritmética exacta
#
# La comprobación recorre coeficientes racionales de pi y compara lo que dice
# `Solucion.contiene` con la verdad evaluada en ESE punto. Un conjunto que fuese
# solo un subconjunto de la verdad pasaría esta dirección y fallaría en la otra,
# por eso se comprueban las dos: cada punto tiene que estar dentro exactamente
# cuando la desigualdad se cumple.
#
# Y el tercer bloque fija los TRES bugs que encontró esta auditoría, que son
# son respuestas FALSAS y no capacidades: `sen(x) >= 1` publicaba ∅, `tg(x) < 0` publicaba
# `pi` dentro, y `contiene(0)` y `contiene(periodo)` se contradecían siendo el
# mismo punto.

INEQ_MUESTREADAS = [
    "sin(x) > 0", "sin(x) < 0", "sin(x) >= 1/2", "sin(x) <= -1/2",
    "cos(x) > 0", "cos(x) < 0", "cos(x) >= 1/2", "cos(x) >= -1/2",
    "cos(x) <= 0", "tan(x) < 1", "tan(x) > -1", "tan(x) <= 0", "tan(x) >= 0",
    "cot(x) > 1", "cot(x) <= 1", "sin(x)^2 > 1/2", "sin(x)^2 <= 1/4",
    "cos(2*x) > 1/2", "sin(x)*cos(x) > 0", "sin(x)*cos(x) < 0",
    "sin(x)/cos(x) > 1", "1/tan(x) > 0", "1/tan(x) < 0",
    "cos(x)^2 >= 1/2", "tan(2*x) < 0", "cos(x) - sin(x) > 0",
    "sin(x) + cos(x) > 0", "2*sin(x) > 1",
    "-sin(x) > 1/2", "tan(x)*tan(x) <= 1",
]

#: Las que el motor se niega, con el motivo escrito, y aqui solo se comprueba
#: que el motivo sea el de verdad. Un rechazo sin motivo es un rechazo que no
#: dice nada, asi que la afirmacion se comprueba contra el texto del motivo.
# `csc(x)^2 > 9` estuvo en esta lista hasta que los ceros fuera de la
# rejilla de pi se pudieron colocar: los suyos son `arcsen(1/3)` y
# `pi - arcsen(1/3)`, y el solucionador de ecuaciones ya los escribia.
# Lo que no habia era una carta de signos que los aceptara, que es otra
# cosa distinta de no saberlos.
CON_MOTIVO = [("sin(x)^2 + cos(x)^2 > 1/2", "periódica"),
               # `cos(x)/sec(x) > 1/2` was here; it is cos(x)^2 > 1/2 and is solved
               # since 2026-10-06. A quintic-like one takes its place.
               ("sin(x)^5 + cos(x)^3 > 0.1234567", "ceros")]


@pytest.mark.parametrize("texto,palabra", CON_MOTIVO)
def test_una_inequacidad_que_no_se_resuelve_dice_por_que(texto, palabra):
    """Negarse es correcto; negarse sin motivo escrito, no."""
    with pytest.raises(Exception) as exc:
        I.resolver_inequidad(texto)
    assert palabra in str(exc.value), f"{texto}: {str(exc.value)[:90]}"


def _real(v):
    """El valor como real, o ``None`` si no lo es.

    El evaluador devuelve complejo para lo que toca una raíz, y en una
    desigualdad real un resultado imaginario no es verdad ni mentira: es fuera
    del dominio, que es lo que hay que responder.
    """
    if v is None:
        return None
    if isinstance(v, complex):
        return v.real if abs(v.imag) < 1e-12 else None
    return float(v)


def _verdad(texto: str, x: float) -> bool:
    """La desigualdad en el punto, sin pasar por el solucionador.

    Un polo se devuelve como ``False`` cuando el valor es enorme: ahi la tabla
    simbólica es la autoridad y el punto flotante solo ve un numero grande. Es la
    unica concession que hace esta comprobacion, y sin ella marcaria como error
    una respuesta que es correcta — el motor diciendo que ``pi/2`` no es solucion
    de ``tg(x) > -1``, que es lo que tiene que decir.
    """
    for op in (">=", "<=", ">", "<", "="):
        i = texto.find(op)
        if i >= 0:
            break
    cuerpo, lado = texto[:i].strip(), texto[i + len(op):].strip()
    v = _real(mx.evaluate(mx.parse(cuerpo), {"x": x}))
    d = _real(mx.evaluate(mx.parse(lado), {"x": x}))
    if v is None or d is None or abs(v) > 1e12:
        return False
    tol = 1e-9
    return {">=": v >= d - tol, "<=": v <= d + tol,
            ">": v > d + tol, "<": v < d - tol,
            "=": abs(v - d) < tol}[op]


@pytest.mark.parametrize("texto", INEQ_MUESTREADAS)
def test_el_conjunto_de_una_inequacidad_coincide_con_la_funcion(texto):
    """Cada punto racional de pi, dentro exactamente cuando se cumple."""
    s = I.resolver_inequidad(texto)
    if s.periodo is None:
        pytest.skip("aperiodica: el conjunto no es un patron")
    for i in range(16):
        k = Fraction(i * s.periodo, 16)
        esperado = _verdad(texto, float(k) * math.pi)
        assert s.contiene(k) is esperado, (
            f"{texto} en {k}·pi: el conjunto dice {s.contiene(k)} y la funcion "
            f"dice {esperado}; publicado «{s.conjunto.texto()}»")


def test_el_verificador_de_inequaciones_puede_decir_que_no():
    """Control negativo: sin el, la comprobación de arriba no compararía nada."""
    s = I.resolver_inequidad("sin(x) > 0")
    assert s.contiene(Fraction(1, 4)) is True
    assert s.contiene(Fraction(3, 4)) is True
    assert s.contiene(Fraction(5, 4)) is False
    assert s.contiene(Fraction(7, 4)) is False


# --- bug 1: una solucion SIN INTERIOR no tiene ningun hueco que quedarse ------

NIVEL_PROPIO = ["sin(x) >= 1", "sin(x) <= -1", "cos(x) >= 1", "cos(x) <= -1"]


@pytest.mark.parametrize("texto", NIVEL_PROPIO)
def test_una_inequacidad_que_solo_se_cumple_en_un_punto_no_puede_salir_vacia(texto):
    """``sen(x) >= 1`` se cumple en ``pi/2`` y en ``3pi/2``.

    La carta de signos recorre HUECOS y se queda con los que cumplen. Una
    solucion sin interior no tiene ninguno que quedarse —el maximo es tangente,
    no un cambio de signo— y la respuesta salia ``∅``: un «no hay soluciones»
    falso sobre una expresion llena de ellos. El caso no tangente, ``sen(x) <= 1``,
    si salia bien, que es lo que lo escondia.
    """
    s = I.resolver_inequidad(texto)
    assert not s.conjunto.vacio, f"{texto} publica ∅ y tiene soluciones: {s.texto()}"


@pytest.mark.parametrize("texto,donde", [("sin(x) >= 1", Fraction(1, 2)),
                                         ("cos(x) >= 1", Fraction(0)),
                                         ("sin(x) <= -1", Fraction(3, 2)),
                                         ("cos(x) <= -1", Fraction(1))])
def test_el_punto_de_tangencia_esta_en_su_conjunto(texto, donde):
    s = I.resolver_inequidad(texto)
    assert s.contiene(donde), f"{texto} no contiene {donde}·pi: {s.conjunto.texto()}"


# --- bug 2: <= y < no pueden publicar el mismo conjunto ----------------------

IGUALES_QUE_NO_DEBEN = [
    ("tan(x) <= 0", "tan(x) < 0"), ("sin(x) <= 0", "sin(x) < 0"),
    ("cos(x) <= 0", "cos(x) < 0"), ("sin(x) <= 1", "sin(x) < 1"),
    ("tan(x) <= 1", "tan(x) < 1"),
]


@pytest.mark.parametrize("cerrada,abierta", IGUALES_QUE_NO_DEBEN)
def test_la_version_cerrada_y_la_abierta_no_publican_lo_mismo(cerrada, abierta):
    """``tg(x) <= 0`` y ``tg(x) < 0`` publicaban las dos ``(pi/2, pi]``.

    El extremo del periodo se decidia comparando el punto SIN doblar contra un
    conjunto de ceros YA doblado, asi que el cero del final de periodo no se
    reconocia como cero y se decidia por el valor numerico: ahi ``tg(pi)`` vale
    -1e-16, que pasa cualquier ``< 0``.
    """
    a = I.resolver_inequidad(cerrada)
    b = I.resolver_inequidad(abierta)
    assert a.conjunto.texto() != b.conjunto.texto(), (
        f"«{cerrada}» y «{abierta}» publican lo mismo: {a.conjunto.texto()}")


# --- bug 3: el mismo punto con dos nombres -----------------------------------

CON_PARIDAD = [
    "sin(x) <= 0", "sin(x) >= 0", "sin(x) < 0", "sin(x) > 0",
    "cos(x) <= 0", "cos(x) >= 0", "cos(x) < 0", "cos(x) > 0",
    "tan(x) <= 0", "tan(x) >= 0", "tan(x) < 0", "tan(x) > 0",
]


@pytest.mark.parametrize("texto", CON_PARIDAD)
def test_el_punto_del_periodo_y_el_cero_no_se_contradicen(texto):
    """La respuesta DECLARA «se repite cada P·pi», luego 0·pi y P·pi son el mismo.

    Antes, ``contiene(0)`` era falso y ``contiene(P)`` verdadero para ``tg(x) <= 0``
    — y la verdad numerica decia que 0 si es solucion. Un conjunto que pone un
    punto dentro y el mismo punto fuera no es la solucion de nada.
    """
    s = I.resolver_inequidad(texto)
    assert s.periodo is not None
    assert s.contiene(Fraction(0)) == s.contiene(Fraction(s.periodo)), (
        f"{texto}: contiene(0)={s.contiene(Fraction(0))} pero "
        f"contiene({s.periodo})={s.contiene(Fraction(s.periodo))}; "
        f"publicado «{s.conjunto.texto()}»")


@pytest.mark.parametrize("texto,coeficiente", [("tan(x) <= 0", Fraction(0)),
                                               ("sin(x) <= 0", Fraction(0)),
                                               ("tan(x) >= 0", Fraction(0)),
                                               ("sin(x) >= 0", Fraction(0))])
def test_el_cero_del_periodo_se_responde_como_tal(texto, coeficiente):
    """``tg(0) = 0``, asi que ``tg(x) <= 0`` y ``tg(x) >= 0`` se cumplen ahi."""
    s = I.resolver_inequidad(texto)
    assert s.contiene(coeficiente), f"{texto} en 0·pi: {s.conjunto.texto()}"
    assert _verdad(texto, 0.0)


# ---------------------------------------------------------------------------
# 10. T-11: cada rama vale DENTRO de su intervalo y falla en el siguiente
#
# La identidad se calcula aqui, con `math`, que no comparte una linea con el
# motor. Y el control negativo importa: si la misma formula sirviera en las dos
# ramas, no distinguiría nada y la comprobación pasaría sin comprobar.

IDENTIDAD_RAMAS = {
    "asin(sin)": lambda x: math.asin(math.sin(x)),
    "acos(cos)": lambda x: math.acos(math.cos(x)),
    "atan(tan)": lambda x: math.atan(math.tan(x)),
    "asinh(sinh)": lambda x: math.asinh(math.sinh(x)),
    "acosh(cosh)": lambda x: math.acosh(math.cosh(x)),
    "atanh(tanh)": lambda x: math.atanh(math.tanh(x)),
}


@pytest.mark.parametrize("nombre", sorted(IDENTIDAD_RAMAS))
def test_cada_rama_declara_una_identidad_que_se_cumple_en_su_intervalo(nombre):
    """``acosh(cosh(x)) = |x|``, y sus dos filas estaban cambiadas de sitio.

    El motor publicaba ``x`` en ``(-inf, 0]`` y ``-x`` en ``[0, inf)``, que es
    justo al reves: en la izquierda vale ``-x``. Y lo publicaba dos veces igual,
    porque la NOTA de cada fila describia el lado correcto y la expresion no — el
    motor se contradecía a si mismo y las dos frases decian la misma cosa falsa.
    """
    identidad = IDENTIDAD_RAMAS[nombre]
    rs = R.ramas(nombre)
    for rama in rs:
        iv = rama.intervalo
        izq = None if iv.izq is None else iv.izq.coeficiente * math.pi
        der = None if iv.der is None else iv.der.coeficiente * math.pi
        if izq is None and der is None:
            puntos = [-2.0, 0.0, 2.0]
        elif izq is None:
            puntos = [der - 0.3, der - 1.0, der - 2.0]
        elif der is None:
            puntos = [izq + 0.3, izq + 1.0, izq + 2.0]
        else:
            ancho = (der - izq) / 4
            puntos = [izq + ancho, (izq + der) / 2, der - ancho]
        for x in puntos:
            try:
                verdad = identidad(x)
            except (ValueError, OverflowError):
                continue
            obtenido = _real(mx.evaluate(rama.expresion, {"x": x}))
            if obtenido is None:
                continue
            assert abs(obtenido - verdad) < 1e-9, (
                f"{nombre} en x={x}: la identidad da {verdad} y la rama dice "
                f"{obtenido} (intervalo {iv.texto()})")


@pytest.mark.parametrize("nombre", sorted(IDENTIDAD_RAMAS))
def test_una_rama_no_sirve_tambien_en_la_siguiente(nombre):
    """Si la misma formula valiera en las dos ramas, no distinguirian nada."""
    identidad = IDENTIDAD_RAMAS[nombre]
    rs = R.ramas(nombre)
    for i, rama in enumerate(rs[:-1]):
        siguiente = rs[i + 1].intervalo
        a = None if siguiente.izq is None else siguiente.izq.coeficiente * math.pi
        b = None if siguiente.der is None else siguiente.der.coeficiente * math.pi
        if a is None or b is None or b <= a:
            continue
        x = (a + b) / 2
        try:
            verdad = identidad(x)
        except (ValueError, OverflowError):
            continue
        obtenido = _real(mx.evaluate(rama.expresion, {"x": x}))
        if obtenido is None:
            continue
        assert abs(obtenido - verdad) > 1e-9, (
            f"{nombre}: la rama {i} tambien vale en x={x}, que es de la rama "
            f"{i + 1}")


def test_la_justificacion_de_una_rama_no_describe_otra_rama():
    """La frase «llega hasta el infinito por la izquierda» la dizia toda familia.

    ``acosh(cosh)`` es no acotada por la DERECHA, asi que la justificacion
    describia una rama distinta de la que explicaba. Una justificacion que
    describe otra rama lee bien y argumenta mal, que es lo peor de las dos.
    """
    texto = R.evidencia_global("acosh(cosh)")
    principal = R.rama_principal("acosh(cosh)")
    iv = principal.intervalo
    if iv.izq is None:
        assert "por la izquierda" in texto
    else:
        assert "por la izquierda" not in texto


# ---------------------------------------------------------------------------
# 11. T-15: el argumento de un complejo, contra `atan2`
#
# `atan2` es la autoridad: no comparte una linea con el motor. Y hay dos
# cuadrantes con parte real negativa que se doblan en direcciones OPUESTAS, que
# es donde se escondia el fallo.

CUADRANTES = [(3, 4), (-3, 4), (3, -4), (-3, -4), (1, 1), (1, -1), (-1, 1),
              (-1, -1), (7, 1), (-7, 1), (1, 7), (1, -7)]


@pytest.mark.parametrize("re,im", CUADRANTES)
def test_el_argumento_principal_coincide_con_atan2(re, im):
    """``(-pi, pi]`` en los cuatro cuadrantes.

    La real negativa se dobla una y otra vez hacia el mismo lado, y eso solo es
    correcto en el TERCER cuadrante, donde ``y/x`` es positivo. En el segundo
    ``y/x`` es negativo y hay que sumar ``pi``, no restarlo: ``arg(-3+4i)`` salia
    en -4.069, fuera del rango que el propio modulo declara.
    es correcto en el tercer cuadrante, donde ``y/x`` es positivo. En el segundo
    ``y/x`` es negativo y hay que sumar ``pi``, no restarlo: ``arg(-3+4i)`` salia
    en -4.069, fuera del rango que el propio modulo declara.
    """
    zc = K.Complejo(mx.Num(Fraction(re)), mx.Num(Fraction(im)))
    a = _real(mx.evaluate(zc.argumento()))
    assert a is not None
    assert abs(a - math.atan2(im, re)) < 1e-12, (re, im)
    assert -math.pi <= a <= math.pi, (re, im)


@pytest.mark.parametrize("re,im", CUADRANTES)
def test_el_argumento_no_principal_gana_exactamente_una_vuelta(re, im):
    """Y reconstruye el MISMO numero, que es lo que lo hace la misma fase.

    Comparar los dos angulos no basta: un angulo con el signo del coseno
    equivocado esta una vuelta entera de nada.
    """
    zc = K.Complejo(mx.Num(Fraction(re)), mx.Num(Fraction(im)))
    principal = _real(mx.evaluate(zc.argumento()))
    otro = _real(mx.evaluate(zc.argumento(principal=False)))
    assert otro is not None and principal is not None
    assert abs(abs(otro - principal) - 2 * math.pi) < 1e-12, (re, im)
    modulo = _real(mx.evaluate(zc.modulo()))
    reconstruido = complex(modulo * math.cos(otro), modulo * math.sin(otro))
    assert abs(reconstruido - complex(re, im)) < 1e-9, (re, im)


@pytest.mark.parametrize("re,im", [(3, 4), (-3, 4), (3, -4), (-3, -4), (1, 1)])
def test_el_argumento_tiene_que_poder_ser_no_principal(re, im):
    """Control negativo del anterior: si las dos vias dieran lo mismo, no dirian nada."""
    zc = K.Complejo(mx.Num(Fraction(re)), mx.Num(Fraction(im)))
    a = _real(mx.evaluate(zc.argumento()))
    b = _real(mx.evaluate(zc.argumento(principal=False)))
    assert a != b, (re, im)


# ---------------------------------------------------------------------------
# 12. T-23: los hechos declarados contra la funcion recorrida
#
# La amplitud es la MITAD del recorrido —no el máximo, no el recorrido— y el
# recorrido lo mide esta comprobacion, no el motor. Comparar el número del motor
# contra si mismo no haria falta; compararloaria falta; compararlo contra el recorrido, que se calcula
# aqui muestreando, si.

SENOIDES = [("3*sin(2*x)", 3.0), ("sin(x)", 1.0), ("5*cos(x)", 5.0),
            ("sin(x) + 1", 1.0), ("2*cos(3*x) - 4", 2.0), ("3*cos(x) + 2", 3.0),
            ("2*sin(x + pi/3)", 2.0), ("5*sin(x + pi/3)", 5.0),
            ("sin(5*x)", 1.0), ("cos(x)", 1.0), ("-sin(x)", 1.0)]


@pytest.mark.parametrize("expresion,amplitud", SENOIDES)
def test_la_amplitud_es_la_mitad_del_recorrido(expresion, amplitud):
    e = mx.parse(expresion)
    valores = []
    for i in range(720):
        v = _real(mx.evaluate(e, {"x": 2 * math.pi * i / 720}))
        if v is not None:
            valores.append(v)
    mitad = (max(valores) - min(valores)) / 2
    declarada = Gr.caracteristicas(e).amplitud
    assert declarada is not None, f"{expresion} no declara amplitud"
    assert abs(mitad - amplitud) < 1e-3, f"{expresion}: recorrido/2 = {mitad}"
    assert abs(declarada - amplitud) < 1e-9, f"{expresion}: declara {declarada}"


@pytest.mark.parametrize("expresion,coeficiente", [
    ("3*sin(2*x)", Fraction(1)), ("sin(x)", Fraction(2)), ("cos(x)", Fraction(2)),
    ("sin(2*x)", Fraction(1)), ("2*cos(3*x) - 4", Fraction(2, 3)),
    ("sin(5*x)", Fraction(2, 5)), ("sin(x + pi/3)", Fraction(2)),
])
def test_el_periodo_y_la_frecuencia_dicen_lo_mismo(expresion, coeficiente):
    """``periodo`` viene en unidades de pi y ``frecuencia`` es ``1/periodo``.

    Un periodo por cada pi, que es lo mismo que decir un ciclo cada ``2·pi``.
    Los dos numeros se declaran a la vez y tienen que cuadrar entre si: si
    uno de los dos se equivoca, el otro lo compensa y ninguno se delata solo.
    """
    c = Gr.caracteristicas(mx.parse(expresion))
    assert c.periodo == coeficiente, (expresion, c.periodo)
    assert abs(float(c.frecuencia) * float(coeficiente) - 1.0) < 1e-12, expresion


SIN_CERO_EXACTO = ["sin(x)", "cos(x)", "sin(2*x)", "cos(3*x)", "sin(x) + 1",
                   "2*cos(x) - 1", "sin(x)/cos(x)", "sin(x)*cos(x)"]


@pytest.mark.parametrize("expresion", SIN_CERO_EXACTO)
def test_los_ceros_declarados_anulan_la_funcion(expresion):
    e = mx.parse(expresion)
    for p in Gr.caracteristicas(e).ceros:
        v = _real(mx.evaluate(e, {"x": p.valor()}))
        assert v is not None, f"{expresion}: {p.texto()} no existe"
        assert abs(v) < 1e-6, f"{expresion}: en {p.texto()} vale {v}"


# ---------------------------------------------------------------------------
# 13. un bucle sin suelo: `sin(x)^2 + cos(x)^2 > 1/2` colgaba el motor
#
# `periodo_minimo` partia el candidato por la mitad mientras la mitad siguiera
# valiendo, con la condicion `candidato / 2 > 0`. Un `Fraction` positivo
# partido por dos es otro `Fraction` positivo: NUNCA llega a cero. Para una
# funcion que repite tras CUALQUIER desplazamiento el bucle no terminaba, y
# `sin(x)^2 + cos(x)^2 - 1/2` es la constante 1/2 escrita mas larga: repite tras
# cualquier desplazamiento. El motor se colgaba hasta que lo mataban.
#
# La respuesta correcta no es un periodo mas pequeno, es que no hay periodo
# minimo — y un periodo sin minimo no es un periodo que una carta de signos pueda
# usar. `1 > 1/2` ya decia exactamente eso.

SIN_PERIODO_MINIMO = ["sin(x)/x", "x + sin(x)", "sin(x)*x",
                      "sin(x)^2 + cos(x)^2 - 1/2", "sin(x)^2 + cos(x)^2",
                      "sin(x)^2 + cos(x)^2 + 3", "exp(x)", "1"]


@pytest.mark.parametrize("expresion", SIN_PERIODO_MINIMO)
def test_una_expresion_sin_periodo_minimo_no_cuelga(expresion):
    """Con el suelo puesto: termina, y dice que no hay periodo."""
    assert D.periodo_minimo(mx.parse(expresion), "x") is None


@pytest.mark.parametrize("expresion", ["sin(x)^2 + cos(x)^2 > 1/2",
                                      "sin(x)^2 + cos(x)^2 > 2",
                                      "sin(x)^2 + cos(x)^2 = 1"])
def test_la_identidad_fundamental_es_no_periodica_para_la_carta_de_signos(expresion):
    """`sen^2 + cos^2 = 1`, asi que `> 1/2` es cierto en todas partes.

    La carta de signos necesita un periodo; no hay ninguno que valga, asi que la
    respuesta honesta es negarse con el motivo. Lo que no puede es colgarse.
    """
    with pytest.raises(Exception) as exc:
        I.resolver_inequidad(expresion)
    assert "periódica" in str(exc.value)


# Los periodos minimos de verdad, que el cambio del bucle no puede tocar. Un
# recorte mal puesto baja un sineide a un cuarto de su periodo y ningun test
# numerico lo nota, porque el periodo mas pequeño tambien es un periodo.
PERIODOS_MINIMOS = [
    ("sin(x)", Fraction(2)), ("cos(x)", Fraction(2)), ("tan(x)", Fraction(1)),
    ("cot(x)", Fraction(1)), ("sec(x)", Fraction(2)), ("csc(x)", Fraction(2)),
    ("sin(2*x)", Fraction(1)), ("cos(2*x)", Fraction(1)), ("tan(2*x)", Fraction(1, 2)),
    ("sin(x)^2", Fraction(1)), ("cos(x)^2", Fraction(1)), ("sin(x)^3", Fraction(2)),
    ("cos(x)^3", Fraction(2)), ("sin(x)^4", Fraction(1)), ("sin(x)^6", Fraction(1)),
    ("sin(5*x)", Fraction(2, 5)), ("cos(4*x)", Fraction(1, 2)),
]


@pytest.mark.parametrize("expresion,esperado", PERIODOS_MINIMOS)
def test_el_periodo_minimo_no_se_ha_encogido_de_mas(expresion, esperado):
    """`sin(x)^6` tiene periodo `pi`, NO `pi/6`.

    La sexta potencia no sube la frecuencia: `sin(x + pi) = -sin(x)` y una
    potencia par se lo come. Bajarlo a `pi/6` seria un periodo VALIDO que
    duplica cada intervalo de la respuesta sin motivo, y ningun muestreo lo
    detecta porque lo mas pequeño tambien vale. Un recorte mal puesto no se ve
    como un error de calculo: se ve como una respuesta mas larga.
    """
    assert D.periodo_minimo(mx.parse(expresion), "x") == esperado


# ---------------------------------------------------------------------------
# 14. la misma pregunta escrita de dos maneras, y dos respuestas distintas
#
# El motor tenia la respuesta y se negaba a darla. `sec(x)^2 > 4` se rechazaba
# mientras `1/cos(x)^2 > 4` se resolvia, que es la misma pregunta: el recíproco
# reescrito daba `(1/cos)^2`, un arbol que nada de lo que viene despues
# reconoce, en vez de `1/cos^2`, que es como lo escribe el estudiante. La potencia
# va DENTRO del cociente, y solo para un entero positivo, que es donde la
# identidad es exacta.
#
# Y dos ceros FALSOS, que es peor que un rechazo: un producto es cero donde lo sea
# un factor, pero solo donde el producto EXISTE.

MIS_ESCITURAS = [
    ("sec(x)^2 > 4", "1/cos(x)^2 > 4"),
    ("sec(x)^3 > 8", "1/cos(x)^3 > 8"),
    ("sec(x)^4 > 16", "1/cos(x)^4 > 16"),
    ("sec(x) > 2", "1/cos(x) > 2"),
    ("csc(x)^2 > 9", "1/sin(x)^2 > 9"),
]


@pytest.mark.parametrize("una,otra", MIS_ESCITURAS)
def test_las_dos_escrituras_de_la_misma_pregunta_dicen_lo_mismo(una, otra):
    """La comprobación que faltaba, y la que más fácil se olvidaba.

    Comparar una respuesta consigo misma no la verifica: hay que poner las dos
    escrituras lado a lado y ver que coinciden. `cos(x)/sec(x)` NO es lo mismo
    que `cos(x)^2` —la primera arrastra el dominio de `sec`— así que esa pareja
    compara contra el dominio, que es lo que las distingue de verdad.
    """
    try:
        a = I.resolver_inequidad(una)
    except Exception as ex:
        assert "no hay regla" not in str(ex) or "ceros" not in str(ex), \
            f"{una} se niega por no saber sus ceros, y {otra} si se resuelve"
        pytest.skip(f"{una} no se resuelve y no es por falta de ceros: {str(ex)[:60]}")
    b = I.resolver_inequidad(otra)
    assert a.conjunto.texto() == b.conjunto.texto(), (
        f"«{una}» publica {a.conjunto.texto()} y «{otra}» publica "
        f"{b.conjunto.texto()}: la misma pregunta, dos respuestas")


def test_la_potencia_del_reciproco_va_dentro_del_cociente():
    """La forma, comprobada: `sec(u)^n` es `1/cos(u)^n` y no `(1/cos(u))^n`.

    Los dos arboles son el mismo numero, asi que compararlos por valor no
    distingue nada — que es justo por lo que el fallo esquivaba la verificacion.
    Se comprueba la FORMA, que es lo que decide si las reglas de despues la
    reconocen.
    """
    for n in (2, 3, 4):
        e = I._a_cocientes(mx.parse(f"sec(x)^{n}"))
        assert mx.text(e) == f"1/cos(x)^{n}", (n, mx.text(e))
    e = I._a_cocientes(mx.parse("csc(x)^2"))
    assert mx.text(e) == "1/sin(x)^2", mx.text(e)
    # Un exponente fraccionario NO se toca, y la proteccion no es la guarda del
    # entero: `sec(x)^(1/2)` ni siquiera llega a la rama de las potencias, porque
    # el lector lo construye como RAIZ —un nodo distinto— y una raiz no se puede
    # repartir en un cociente sin decidirse el signo. En los reales
    # `(-1)^(1/2)` no existe, y doblar un signo a traves de una raiz para que dos
    # arboles se parezcan es la clase de comodidad que se vuelve respuesta falsa.
    raiz = I._a_cocientes(mx.parse("sec(x)^(1/2)"))
    assert "cos" not in mx.text(raiz), mx.text(raiz)
    entero_mas = I._a_cocientes(mx.parse("sec(x)^4"))
    assert mx.text(entero_mas) == "1/cos(x)^4", mx.text(entero_mas)


# --- los ceros de un producto, que ya no son ceros donde no existe ------------

def _ceros_coeficiente(texto: str) -> set:
    """Los ceros que publica el motor, como fracciones de pi."""
    r = I.ceros(mx.parse(texto), "x")
    if r is None:
        return set()
    salida = set()
    for v in r:
        c = I._coeficiente_pi(v)
        if c is not None:
            salida.add(c)
    return salida


def test_un_cero_onde_el_producto_no_existe_no_es_un_cero():
    """``tg(x)·cos(x)`` publicaba ``pi/2`` y ``3pi/2``, y ahi ``tg`` no existe.

    El producto es cero donde lo sea un factor —eso es cierto— pero solo donde el
    producto EXISTE. El filtro que ya tenia la rama del cociente faltaba en la
    del producto, no porque el algebra sea distinta, sino porque un factor
    compartido es donde se nota.

    Y el otro lado del mismo arreglo: el producto es `sen(x)`, de periodo 2·pi,
    mientras `tg` se dobla en pi y declara un cero, donde el segundo —pi— no se
    generaba nunca. Un cero que falta no es un cero de mas, pero deja la carta de
    signos sin un punto critico con el que explicar un cambio de signo, y el motor
    se negaba por eso. Cada factor aporta ahora sus ceros hasta el periodo del
    producto.
    """
    ceros = _ceros_coeficiente("tan(x)*cos(x)")
    assert ceros == {Fraction(0), Fraction(1)}, ceros
    d = I.dominio(mx.parse("tan(x)*cos(x)"), "x")
    for k in (Fraction(1, 2), Fraction(3, 2)):
        assert not d.contiene(D.punto_pi(k)), (k, d.texto())


def test_las_tres_formas_de_la_misma_expresion_no_se_contradicen():
    """``sen(x)·cos(x)``, ``tg(x)·cos(x)`` y sus ceros, contra la verdad a mano.

    Un producto corriente NO debe perder ceros: el filtro de existencia quita los
    que no son y deja los que son. Sin esto, arreglar el caso anterior habria
    sido tapar un cero con otro.
    """
    assert _ceros_coeficiente("sin(x)*cos(x)") == \
        {Fraction(0), Fraction(1, 2), Fraction(1), Fraction(3, 2)}
    assert _ceros_coeficiente("sin(x)/cos(x)") == {Fraction(0), Fraction(1)}
    assert _ceros_coeficiente("cos(x)/sin(x)") == \
        {Fraction(1, 2), Fraction(3, 2)}
    assert _ceros_coeficiente("cos(x)*cos(x)") == \
        {Fraction(1, 2), Fraction(3, 2)}


def test_el_extremo_del_periodo_tambien_es_un_hueco():
    """``1/sen(x)`` no existe en ``2pi``, y ``2pi`` es el mismo punto que 0.

    ``ceros`` contesta con UN periodo, asi que el denominador ``sen(x)`` declaraba
    su cero en 0 y no en ``pi``, y el dominio se comia un ``0/0`` y publicaba un
    cero falso ahi. La misma regla que la carta de signos ya seguia —0 y el
    final del periodo son el mismo punto— y que aqui no se seguia.
    """
    d = I.dominio(mx.parse("1/sin(x)"), "x")
    for k in (Fraction(0), Fraction(1), Fraction(2)):
        assert not d.contiene(D.punto_pi(k)), (k, d.texto())
    # y el hueco de verdad de la otra forma de escribirla
    d2 = I.dominio(mx.parse("cos(x)/sin(x)"), "x")
    assert not d2.contiene(D.punto_pi(Fraction(1))), d2.texto()


# --- el «no hay soluciones» que no lo era -------------------------------------

VACIAS_DE_VERDAD = ["cos(x)^3 > 1", "sin(x)^3 > 1", "cos(x)^3 > 2",
                    "sin(x)^2 > 2", "cos(x) > 1", "sin(x) > 1",
                    "cos(x) > 2", "sin(x) > 2", "cos(x)^2 > 4"]
# `csc(x)^2 > 9` se resolvio cuando la carta acepto puntos criticos que
# no son multiplos de pi, y su respuesta es exacta:
# `(0, arcsen(1/3)) ∪ (pi - arcsen(1/3), pi)`. `cot(x)^3 > 4` sigue aqui
# porque su cero necesita `tg(x) = 4^(-1/3)`, una raiz irracional de un
# polinomio: ahi el hueco es del SOLUCIONADOR DE ECUACIONES.
VACIAS_FALSAS = ["cot(x)^3 > 4", "cot(x)^3 < -4"]


@pytest.mark.parametrize("caso", VACIAS_DE_VERDAD)
def test_una_inequacidad_sin_solucion_dice_que_no_la_hay(caso):
    """`cos(x)^3 > 1` no tiene soluciones, y decirlo es lo correcto.

    Va al lado de la de arriba a proposito: si el motor se negara por todo, esto
    fallaria, y una prueba que obliga a negar tambien obliga a no negar.
    """
    s = I.resolver_inequidad(caso)
    assert s.vacia, f"{caso} tiene soluciones y el motor dice que no: {s.texto()}"


@pytest.mark.parametrize("caso", VACIAS_FALSAS)
def test_una_inequacidad_sin_solucion_exacta_no_puede_decir_que_no_la_hay(caso):
    """It may refuse, or answer — never answer ∅. Since 2026-10-06 it answers:
    the zero is tg(x) = 4^(-1/3), a cube root the solver now writes exactly."""
    try:
        s = I.resolver_inequidad(caso)
    except Exception:  # noqa: BLE001 - a refusal is allowed
        return
    assert not s.vacia, (caso, s.texto())


def _antigua_negativa(caso):
    """`cot(x)^3 > 4` SI tiene soluciones, y el motor publicaba «no hay soluciones».

    Sus ceros necesitan `tg(x) = 4^(-1/3)`, que no es un multiplo racional de
    `pi`, y el solucionador de ecuaciones devolvia una lista de familias vacia
    SIN registrar el rechazo. Leido tal cual, «no hay ceros». Y un `∅` sobre una
    expresion llena de soluciones es la peor respuesta posible: el propio modulo
    lleva escrito que `∅` NO es «no lo sé».

    `sec(x)^3 > 8` estuvo en esta lista hasta que se arreglo —su cero es
    `cos = 1/2`, exacto, y el motor no lo encontraba— y ahora esta unas lineas mas
    abajo, en las que se resuelve. Una lista de rechazos que no se relee es una
    lista de huecos que nadie vuelve a mirar.

    La prueba independiente es el teorema del valor intermedio: una funcion
    continua sin polo ni cero no cambia de signo. Un cambio de signo en cualquier
    punto demuestra que el cero EXISTE, y de eso basta para negarse con el motivo.
    """
    # Lo que se comprueba es que se NEGUE, y por no saber los ceros. El mensaje
    # lleva escrito «eso NO es «no hay soluciones»», asi que buscar esa frase
    # dentro del texto daria verde sobre un rechazo y sobre un ∅ indistintos: la
    # frase esta en los dos. Lo que los distingue es la excepcion.
    with pytest.raises(Exception) as exc:
        I.resolver_inequidad(caso)
    assert "ceros" in str(exc.value), f"{caso}: {str(exc.value)[:90]}"


def test_el_cambio_de_signo_demuestra_que_existe_un_cero():
    """La comprobación es una prueba, no una heurística, y por eso se prueba sola."""
    assert I._cambia_de_signo(mx.parse("1/tan(x)^3 - 4"), "x") is True
    assert I._cambia_de_signo(mx.parse("cos(x)^3 - 1"), "x") is False
    assert I._cambia_de_signo(mx.parse("sin(x)^2 + cos(x)^2 - 1/2"), "x") is False


# --- la potencia del reciproco, y el cubo de la cotangente --------------------

@pytest.mark.parametrize("n", [2, 3, 4])
def test_cot_al_nuevo_tambien_es_el_reciproco(n):
    """``cot(u)^n`` es ``1/tan(u)^n``, no ``(cos/sin)^n``.

    El mismo-treatment que ``sec`` y ``csc``, y el mismo motivo: las dos formas
    reescriben el mismo numero y solo una la reconocen las reglas de despues. Con
    el cubo se ve el coste de no hacerlo —«no hay soluciones» falso— porque el cero
    necesita una raiz cubica que no es multiplo racional de pi.
    """
    e = I._a_cocientes(mx.parse(f"cot(x)^{n}"))
    assert mx.text(e) == f"1/tan(x)^{n}", (n, mx.text(e))
    # el cuadrado ya funciona con las dos escrituras, y con el cubo ninguna
    assert I.resolver_inequidad("cot(x)^2 > 1").conjunto.texto() == \
        I.resolver_inequidad("1/tan(x)^2 > 1").conjunto.texto()


# --- el reciproco con potencia impar, que era el unico que no resolvia --------

RECIPROCO_IMPAR = ["1/cos(x)^3 = 8", "1/cos(x)^4 = 16", "1/cos(x)^5 = 32",
                   "1/cos(x)^6 = 64", "1/sin(x)^3 = 8"]


@pytest.mark.parametrize("ecuacion", RECIPROCO_IMPAR)
def test_el_reciproco_resuelve_con_cualquier_potencia(ecuacion):
    """``1/cos(u)^3 = 8`` tiene la misma solucion que ``1/cos(u)^2 = 4``: ``cos = 1/2``.

    El teorema de la raiz racional dice «divisor del término constante SOBRE
    divisor del coeficiente PRINCIPAL», y aqui solo se usaba el constante: para
    ``-16·u^4 + 1`` eso da ±1, y la raiz es 1/2. El cuadrado se resolvia por otra
    via y el cubo no, y la unica diferencia era el grado.
    """
    r = E.resolver(ecuacion)
    assert r.familias, f"{ecuacion} no da ninguna familia"


@pytest.mark.parametrize("ecuacion", ["1/cos(x)^2 = 4", "1/cos(x)^3 = 8",
                                     "1/cos(x)^4 = 16", "cos(x)^3 = 1/8"])
def test_cada_familia_de_un_reciproco_satisface_la_ecuacion(ecuacion):
    """Las bases de cada familia se sustituyen en la ecuación original.

    Es lo único que caza una solución espuria, y el camino no consulta el
    solucionador que produjo la familia.
    """
    cuerpo, _, lado = ecuacion.partition(" = ")
    izquierda = mx.parse(cuerpo)
    valor_esperado = mx.parse(lado)
    for familia in E.resolver(ecuacion).familias:
        for k in range(0, 6):
            # `Familia` is `x = base + paso·k`, so the member is composed here:
            # there is no method for it, and writing one for a check would be a
            # second implementation of what `texto()` already says
            x = mx.evaluate(mx.Add(familia.base, mx.Mul(familia.paso,
                                                        mx.Num(Fraction(k)))))
            if x is None:
                continue
            x = float(x.real if isinstance(x, complex) else x)
            v = mx.evaluate(izquierda, {"x": x})
            d = mx.evaluate(valor_esperado, {"x": x})
            if v is None or d is None:
                continue
            if abs(v) > 1e12:
                continue                  # numerically infinite: the pole
            assert abs(v - d) < 1e-6, (ecuacion, mx.text(familia.base), k)


POTENCIAS_DEL_RECIPROCO = ["sec(x)^2 > 4", "sec(x)^3 > 8", "sec(x)^4 > 16",
                           "sec(x)^5 > 32", "sec(x)^6 > 64", "csc(x)^3 > 8",
                           "1/cos(x)^3 > 8", "tan(x)^3 > 1", "sec(x) > 2"]


@pytest.mark.parametrize("caso", POTENCIAS_DEL_RECIPROCO)
def test_la_potencia_del_reciproco_responde_lo_verdadero(caso):
    """Cada inecuación del reciprocado, punto a punto contra la función.

    Con los polos SALTADOS y DICHO: a `pi/2` el valor del coseno es 6·10⁻¹⁷ y no
    cero, así que `sec` parece enorme ahí y la comparación por punto flotante
    daría un «error» en una respuesta que es correcta. Nueve de estos casos
    fallaban en 1 de 191 puntos antes de contar los polos, y los nueve fallaban
    en el mismo: el polo. Saltarlos no es relajar la comprobación, es quitarle
    la unica fuente de falsos positivos que tiene.
    """
    import math as _math

    cuerpo, operador, lado = None, None, None
    for o in (">=", "<=", ">", "<"):
        i = caso.find(o)
        if i >= 0:
            cuerpo, operador, lado = caso[:i], o, caso[i + len(o):]
            break
    texto = (cuerpo.replace("^", "**").replace("sen", "sin").replace("tg", "tan")
             .replace("sec", "1/cos").replace("csc", "1/sin").replace("cot", "1/tan"))
    entorno = {"sin": _math.sin, "cos": _math.cos, "tan": _math.tan,
               "pi": _math.pi}
    f = eval(f"lambda x: {texto}", dict(entorno))
    d = eval(f"lambda x: {lado}", dict(entorno))

    s = I.resolver_inequidad(caso)
    periodo = s.periodo or Fraction(2)
    for i in range(1, 192):
        k = Fraction(i * periodo, 192)
        x = float(k) * _math.pi
        try:
            v = f(x)
        except (ZeroDivisionError, ValueError):
            continue
        if abs(v) > 1e12:
            continue                      # un polo no es verdad de nada
        tol = 1e-9
        real = {"<": v < d(x) - tol, ">": v > d(x) + tol,
                "<=": v <= d(x) + tol, ">=": v >= d(x) - tol}[operador]
        assert s.contiene(k) is real, (
            f"{caso} en {k}·pi: el conjunto dice {s.contiene(k)} y la funcion "
            f"dice {real}")
