# SPDX-License-Identifier: MIT
"""La familia de quince que `engcalc` 6.1 anadio al evaluador certificado.

Estas quince no se escribieron aqui: se cierran sobre `sin`, `cos`, `exp` y
`ln`, que ya estaban. Lo que se comprueba en este fichero no es que devuelvan
«algo plausible», sino tres cosas concretas.

**Que el numero sea el que dice ser.** Un valor transcendental no se comprueba
contra `math`, porque `math` es `float` y sus dieciseis digitos no son la
referencia: se comparan contra literales exactos y contra identidades. Durante
el desarrollo, comparar contra `math` dio «errores» de 1e-16 relativo que eran
el error de la referencia y no del kernel — `acosh(1.0001)`, donde la derivada
`1/sqrt(x^2-1)` amplifica el error del argumento float unas 250 veces. El
invariante `cosh(acosh(x)) == x`, en cambio, se sostiene a 1e-43.

**Que el dominio se niegue, y se niegue NOMBRANDO la funcion que se llamo.**
`acos` se construye sobre `asin`, asi que un mensaje que nombrara la funcion
intermedia habria mandado al lector a buscar el error en una funcion que nunca
nombro.

**Que los tres registros que tienen que cuadrar entre si, quadren.** La
whitelist del evaluador, la tabla de kernels y la gramatica del lenguaje
simbolico son tres listas escritas en tres sitios distintos. Si una crece y las
otras no, el motor vuelve a poder imprimir algo que no sabe leer, que es
exactamente el fallo que 6.1 vino a cerrar.
"""

from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from academic_core.domain.engineering import equations as EQ
from academic_core.domain.engineering.math import trig as T

SRC = Path(EQ.__file__).with_name("math").joinpath("trig.py")

#: 1e-40 absolute on values of order one. That is forty digits against a working
#: precision of fifty: it asks the kernel to be right to the last digit it
#: claims, and no further.
ATOL = Decimal(1).scaleb(-40)

PI_4 = Decimal("0.78539816339744830961566084581987572104929234984378")
PI_6 = Decimal("0.52359877559829887307710723054658381403286156656252")
PI_3 = Decimal("1.0471975511965977461542144610931676280657231331250")
PI_2 = Decimal("1.5707963267948966192313216916397514420985846996876")
PI = Decimal("3.1415926535897932384626433832795028841971693993751")
LN_3 = Decimal("1.0986122886681096913952452369225257046474905578227")

#: Every name the 6.1 family added, and the kernel behind each. Written out here
#: on purpose: this is the list a reader diffs against `_family_table`, and
#: `test_la_whitelist_y_la_tabla_de_kernels_no_se_despistan` is what makes the
#: two worth diffing.
FAMILY = (
    "sec", "csc", "cot", "asin", "acos", "atan",
    "sinh", "cosh", "tanh", "coth", "sech", "csch",
    "asinh", "acosh", "atanh",
)

#: The eight that were already there. Named explicitly so the new ones can be
#: recovered by subtraction, and so a rename of an inherited name is visible as
#: a rename rather than as an addition.
PREEJISTENTES = ("sqrt", "exp", "log", "log10", "sin", "cos", "tan", "abs")

#: Negation goes through an explicit context, never through unary minus on a
#: bare ``Decimal``.
#:
#: ``-PI_4`` evaluates under the AMBIENT global context, whose default
#: precision is 28 digits, and quietly rounds a 50-digit constant to 28 before
#: it ever reaches the kernel under test. The symptom is a failure that looks
#: like the kernel losing precision in its last 22 digits — the same bug class
#: `math/trig.py` spends its module docstring warning about, committed here in
#: the test that was written to catch it.
_CTX = T.make_context()

#: The poles, as 50-digit literals. Typed out rather than computed from
#: `decimal_pi` so that the test's own arithmetic never shares a code path with
#: the code under test: a bug in `decimal_pi` must not be able to move the pole
#: out from under the guard that is being tested.
POLOS = {"PI": str(PI), "PI_2": str(PI_2)}


def _neg(valor):
    return _CTX.minus(valor)


def _close(got, expected, atol=ATOL):
    """Do the subtraction under an EXPLICIT context.

    `abs(got - expected)` on two 50-digit values evaluates under the ambient
    global context, whose default precision is 28 — so the difference is
    rounded before it is ever compared, and a comparison that silently cannot
    see the last 22 digits is not a comparison at 1e-40. This helper was the
    third place in this file to fall into that trap, which is why it now takes
    the context instead of assuming one.
    """
    return abs(_CTX.subtract(got, expected)) <= atol


# ------------------------------------------------------------------- los valores

@pytest.mark.parametrize("argumento,esperado", [
    (Decimal(1), PI_4),          # atan(1) = pi/4
    (Decimal(0), Decimal(0)),
    (Decimal(-1), _neg(PI_4)),
])
def test_atan_toma_los_valores_que_son_angulos_exactos(argumento, esperado):
    assert _close(T.decimal_atan(argumento), esperado)


@pytest.mark.parametrize("argumento,esperado", [
    (Decimal("0.5"), PI_6),      # asin(1/2) = pi/6
    (Decimal("-0.5"), _neg(PI_6)),
    (Decimal(1), PI_2),
    (Decimal(-1), _neg(PI_2)),
])
def test_asin_toma_los_valores_que_son_angulos_exactos(argumento, esperado):
    assert _close(T.decimal_asin(argumento), esperado)


@pytest.mark.parametrize("argumento,esperado", [
    (Decimal("0.5"), PI_3),      # acos(1/2) = pi/3
    (Decimal(1), Decimal(0)),
    (Decimal(-1), PI),
])
def test_acos_toma_los_valores_que_son_angulos_exactos(argumento, esperado):
    assert _close(T.decimal_acos(argumento), esperado)


def test_las_inversas_circulares_dESHacen_a_su_funcion():
    """La definicion, comprobada como composicion y no como tabla.

    Casi circular para `asin` y `acos`, que se construyen sobre `atan2`, y esa
    es justamente la gracia: el riesgo de estas tres no es la serie, es una
    reduccion de argumento en el cuadrante equivocado, y solo una vuelta por la
    circunferencia lo detecta.
    """
    ctx = T.make_context()
    for u in ("0.25", "0.5", "-0.5", "-0.9", "0.99", "-0.99"):
        x = Decimal(u)
        assert _close(T.decimal_sin(T.decimal_asin(x)), x), u
        assert _close(T.decimal_cos(T.decimal_asin(x)),
                      ctx.sqrt(ctx.subtract(1, ctx.multiply(x, x)))), u
        assert _close(T.decimal_cos(T.decimal_acos(x)), x), u
        # `tan` no tiene kernel propio: se calcula como seno sobre coseno
        # dentro de `_apply_func`. La vuelta se comprueba por el evaluador.
        tan_de_atan = EQ.evaluate(
            EQ.parse_equation(f"X = tan(atan({u}))"), {}).value
        assert _close(tan_de_atan, x), u
        # el cuadrante que eligio atan2 tiene que ser el del argumento
        assert T.decimal_asin(x).copy_abs() <= ctx.divide(T.decimal_pi(ctx), 2), u
        assert Decimal(0) <= T.decimal_acos(x) <= T.decimal_pi(ctx), u


def test_las_hiperbolicas_cumplen_sus_identidades():
    """`cosh^2 - sinh^2 = 1` y el resto: las identidades pitagoricas.

    Comprobadas sobre las funciones y no sobre una serie, porque una identidad
    que se sostiene es la unica prueba de que dos kernels salieron de la misma
    idea y no de dos bucles parecidos.
    """
    ctx = T.make_context()
    for u in ("0", "0.5", "-0.5", "2", "-2", "7.5", "-7.5"):
        x = Decimal(u)
        cosh2 = ctx.multiply(T.decimal_cosh(x), T.decimal_cosh(x))
        sinh2 = ctx.multiply(T.decimal_sinh(x), T.decimal_sinh(x))
        assert _close(ctx.subtract(cosh2, sinh2), Decimal(1)), u
        tanh2 = ctx.multiply(T.decimal_tanh(x), T.decimal_tanh(x))
        assert _close(ctx.multiply(T.decimal_sech(x), T.decimal_sech(x)),
                      ctx.subtract(1, tanh2)), u
        if x != 0:
            # `coth` y `csch` no estan definidas en el 0, y que se nieguen es
            # justo lo que comprueba `test_el_dominio_se_niega`; aqui se omiten
            # para que la identidad se pueda comprobar en el resto.
            assert _close(ctx.multiply(T.decimal_tanh(x), T.decimal_coth(x)), Decimal(1)), u
            assert _close(ctx.multiply(T.decimal_sinh(x), T.decimal_csch(x)), Decimal(1)), u
        assert _close(ctx.multiply(T.decimal_cosh(x), T.decimal_sech(x)), Decimal(1)), u
        # cosh par; sinh y tanh impares. La negacion va por `_neg`: el menos
        # unario sobre un Decimal de 50 digitos pasa por el contexto global.
        assert _close(T.decimal_cosh(x), T.decimal_cosh(_neg(x))), u
        assert _close(T.decimal_sinh(x), _neg(T.decimal_sinh(_neg(x)))), u
        assert _close(T.decimal_tanh(x), _neg(T.decimal_tanh(_neg(x)))), u


def test_las_reciprocas_circulares_cumplen_su_definicion():
    ctx = T.make_context()
    for u in ("0", "0.5", "-0.5", "1", "-1", "2.5", "-2.5"):
        x = Decimal(u)
        sin_x, cos_x = T.decimal_sin(x), T.decimal_cos(x)
        if not T._is_zero(sin_x):
            assert _close(T.decimal_csc(x), ctx.divide(1, sin_x)), u
            assert _close(T.decimal_cot(x), ctx.divide(cos_x, sin_x)), u
        if not T._is_zero(cos_x):
            assert _close(T.decimal_sec(x), ctx.divide(1, cos_x)), u
    x = Decimal("0.7")
    # `tan` otra vez por el evaluador: no hay kernel que llamar.
    tan_x = EQ.evaluate(EQ.parse_equation("X = tan(0.7)"), {}).value
    tan2 = ctx.multiply(tan_x, tan_x)
    assert _close(ctx.subtract(ctx.multiply(T.decimal_sec(x), T.decimal_sec(x)), tan2),
                  Decimal(1))
    cot2 = ctx.multiply(T.decimal_cot(x), T.decimal_cot(x))
    assert _close(ctx.subtract(ctx.multiply(T.decimal_csc(x), T.decimal_csc(x)), cot2),
                  Decimal(1))


def test_las_inversas_hiberbolicas_dESHacen_a_su_funcion():
    """`sinh(asinh(u)) == u`: la vuelta completa, en los dos signos.

    Esta es la prueba que encontro el fallo real de `asinh`. Escrita al pie de
    la letra como `ln(x + sqrt(x^2+1))`, esa formula devuelve CERO EXACTO para
    todo x negativo suficientemente grande, porque los dos terminos se cancelan
    hasta la precision de trabajo: una respuesta plausible de 0 donde la
    respuesta verdadera es grande y negativa. Sacar el signo fuera es toda la
    diferencia, y solo una vuelta por la mitad negativa lo ve.
    """
    ctx = T.make_context()
    for u in ("-40.5", "-12.25", "-3", "-1", "-0.001", "0.001", "1", "3", "12.25", "40.5"):
        x = Decimal(u)
        assert _close(T.decimal_sinh(T.decimal_asinh(x)), x), u
        assert _close(T.decimal_cosh(T.decimal_asinh(x)),
                      ctx.sqrt(ctx.add(ctx.multiply(x, x), 1))), u
    for u in ("1", "1.0001", "2", "12.25"):
        x = Decimal(u)
        assert _close(T.decimal_sinh(T.decimal_acosh(x)),
                      ctx.sqrt(ctx.subtract(ctx.multiply(x, x), 1))), u
    for u in ("-0.9", "-0.5", "0.5", "0.9"):
        x = Decimal(u)
        assert _close(T.decimal_tanh(T.decimal_atanh(x)), x), u
        assert _close(T.decimal_cosh(T.decimal_atanh(x)),
                      ctx.divide(1, ctx.sqrt(ctx.subtract(1, ctx.multiply(x, x))))), u


def test_los_valores_notables_del_logaritmo():
    """Cuatro valores exactos: un error de reduccion se nota en ellos.

    Los dos primeros se comparan contra el LITERAL y no contra la identidad
    `ln(1+sqrt(2))` que los separa. Esa identidad es cierta, pero el kernel
    redondea a 50 digitos mientras el `ln` del test pasaria por 65, asi que se
    diferenciarian en el ultimo digito y la prueba mediria el redondeo del
    propio test en vez de la exactitud del kernel. El literal es lo que se
    quiere afirmar.

    Dos de estas cuatro se escribieron mal la primera vez —`asinh(1) = ln 2` y
    `acosh(2) = 3 ln 2 / 2`, y ninguna de las dos es cierta—. La primera
    escapaba porque la referencia en `float` coincidia con el literal erroneo
    que yo habia escrito al lado, que es justo el danger de comprobar un
    transcendental contra un `float`: los dos errores se cubren.
    """
    assert _close(T.decimal_asinh(Decimal(1)),
                  Decimal("0.88137358701954302523260932497979230902816032826164"))
    assert _close(T.decimal_acosh(Decimal(2)),
                  Decimal("1.3169578969248167086250463473079684440269819714675"))
    assert _close(_CTX.multiply(T.decimal_atanh(Decimal("0.5")), 2), LN_3)  # ln 3
    assert _close(T.decimal_asinh(Decimal(0)), Decimal(0))


def test_las_identidades_logaritmicas_exactas():
    """`acosh(2) = ln(2 + sqrt(3))`: exactamente igual, no aproximadamente.

    Aqui la identidad ES la asercion, porque sale digitada a digitada: los dos
    lados redondean desde la misma cuenta de guarda a los mismos 50 digitos. Es
    el unico sitio de este fichero donde la igualdad es la comparacion correcta.
    """
    ctx = T.make_context()
    assert T.decimal_acosh(Decimal(2)) == ctx.ln(ctx.add(2, ctx.sqrt(Decimal(3))))


# -------------------------------------------------------------------- dominios

@pytest.mark.parametrize("nombre,argumento", [
    ("asin", Decimal("1.5")), ("asin", Decimal("-1.5")),
    ("acos", Decimal("1.5")), ("acos", Decimal("-2")),
    ("atanh", Decimal(1)), ("atanh", Decimal(-1)), ("atanh", Decimal("1.5")),
    ("acosh", Decimal(0)), ("acosh", Decimal("0.5")),
    ("coth", Decimal(0)), ("csch", Decimal(0)),
])
def test_el_dominio_se_niega(nombre, argumento):
    with pytest.raises(ValueError):
        getattr(T, f"decimal_{nombre}")(argumento)


def test_el_mensaje_de_dominio_no_nombra_la_funcion_interior():
    """`acos` esta construido sobre `asin` y no debe reportar un fallo de `asin`.

    Quien pidio `acos` y recibio un mensaje sobre `asin` tiene un texto sobre
    una funcion que nunca menciono, y va a buscarla donde no esta. El mensaje
    del kernel NO lleva el nombre de ninguna funcion —solo la CONDICION— y es
    el evaluador quien lo compone con el nombre que si se llamo. Se comprueban
    las dos mitades porque el arreglo no es obvio: es mas facil dejar pasar el
    mensaje de dentro que componer uno propio, y por eso el texto del kernel
    tiene prohibido nombrar su propia funcion.
    """
    with pytest.raises(ValueError, match="outside the range") as fallo:
        T.decimal_acos(Decimal(3))
    # el cuerpo dice la condicion y nada mas: ni «asin» ni «acos»
    assert "asin" not in str(fallo.value)
    assert "acos" not in str(fallo.value)
    # y por el evaluador el nombre que aparece es el que se llamo
    with pytest.raises(EQ.EquationError, match=r"^acos domain") as por_evaluador:
        EQ.evaluate(EQ.parse_equation("X = acos(3)"), {})
    assert "asin" not in str(por_evaluador.value)


@pytest.mark.parametrize("nombre,polo", [
    ("tan", "PI_2"), ("sec", "PI_2"), ("csc", "PI"), ("cot", "PI"),
])
def test_las_reciprocas_se_negian_en_su_polo_como_tan(nombre, polo):
    """Los mismos polos y la misma negativa. `tan` se niega en pi/2.

    Todo por el EVALUADOR, y no por el kernel: `tan` no tiene kernel propio —
    se calcula como seno sobre coseno dentro de `_apply_func`, con su propio
    guardia—, asi que compararlo con los otros por el kernel seria comparar
    dos caminos distintos y creer que se parecen. Por el evaluador los cuatro
    son la misma pregunta.

    Y con un argumento EXACTO de 50 digitos, no con la aproximacion float de
    pi/2: un `pi/2` de float esta 1.9e-17 lejos del polo real, asi que a 50
    digitos de trabajo su coseno esta bien determinado y dividir por el es
    aritmetica, no un fallo de dominio. Solo el argumento exacto lo ejercita,
    y por eso el umbral tiene que ser el que `tan` ya usa.
    """
    with pytest.raises(EQ.EquationError, match="domain"):
        EQ.evaluate(EQ.parse_equation(f"X = {nombre}({POLOS[polo]})"), {})


def test_un_argumento_cerca_del_polo_pero_no_en_el_no_se_niega():
    """La contraparte, y la razon de que el umbral este donde esta.

    `1.5707963267948966` se queda a 1.9e-17 del pi/2 verdadero: es la idea
    que tiene un float. A 50 digitos de trabajo el coseno de ESE numero es un
    valor real, calculable y distinto de cero, y su reciproco es la respuesta
    honesta a la pregunta que se hizo. Negarse seria contestar otra pregunta.
    """
    ctx = T.make_context()
    cerca = Decimal("1.5707963267948966")
    assert T.decimal_sec(cerca).copy_abs() > Decimal("1e15")   # enorme, no un error
    assert _close(T.decimal_sec(Decimal(0)), Decimal(1))
    assert _close(T.decimal_sec(_neg(T.decimal_pi(ctx))), Decimal(-1))


# ------------------------------------------------- los tres registros cuadran

def test_la_whitelist_y_la_tabla_de_kernels_no_se_despistan():
    """`ALLOWED_FUNCS` menos las ocho previas es exactamente la tabla de reparto.

    Por conjuntos y no por longitudes: una longitud seguiria diciendo que todo
    esta bien aunque un nombre se hubiera sustituido por otro.
    """
    assert set(EQ.ALLOWED_FUNCS) - set(PREEJISTENTES) == set(FAMILY)
    assert set(EQ._family_table()) == set(FAMILY)
    assert set(PREEJISTENTES) <= set(EQ.ALLOWED_FUNCS)


def test_la_whitelist_no_es_una_segunda_copia_de_la_lista():
    """`ALLOWED_FUNCS` se CONSTRUYE, no se reescribe.

    Durante este trabajo la lista de quince nombres estuvo escrita dos veces en
    el mismo modulo —una en la whitelist y otra dentro de `_apply_func`— y por
    eso existe `TRANSCENDENTAL`: una segunda copia en el mismo fichero es una
    lista que puede discrepar consigo misma, y en este motor una lista que
    discrepa es una expresion que se niega sin decir por que.
    """
    assert EQ.ALLOWED_FUNCS == ("sqrt", "abs") + EQ.TRANSCENDENTAL
    # y `sqrt`/`abs` NO pueden estar en el grupo adimensional: uno conserva la
    # dimension cuando el cuadrado es exacto, el otro conserva la que le den
    assert "sqrt" not in EQ.TRANSCENDENTAL
    assert "abs" not in EQ.TRANSCENDENTAL


def test_todo_lo_que_la_gramatica_admite_lo_evalua_el_evaluador():
    """El invariante que 6.1 vino a establecer, afirmado y no descrito.

    Toda funcion que la gramatica del lenguaje simbolico pueda contener tiene
    que ser una que el evaluador certificado sepa calcular. Antes de 6.1 esto
    fallaba para quince nombres: el lenguaje no podia LEER `atan` y la tabla de
    integracion si lo podia ESCRIBIR, de modo que el motor producia una
    primitiva que no tenia forma de comprobar.
    """
    from academic_core.domain.engineering.symbolic import expr as SE

    # `log10` pertenece al evaluador y no al lenguaje: el lenguaje tiene `log`
    # para el logaritmo natural y ningun otro nombre para el de base 10.
    sin_log10 = set(EQ.ALLOWED_FUNCS) - {"log10"}
    assert set(SE.FUNCTIONS) <= sin_log10, sorted(set(SE.FUNCTIONS) - sin_log10)


def test_la_tabla_de_derivadas_ya_conocia_las_quince():
    """Por que el fallo duraba: el motor sabia derivar lo que no sabia escribir.

    Antes de 6.1, `derive._TABLE` tenia las quince y `expr.FUNCTIONS` tenia
    siete. Un motor que deriva mejor de lo que escribe es un motor que produce
    respuestas que no puede verificar, y por eso esta aserccion mira la
    diferencia y no solo la pertenencia.
    """
    from academic_core.domain.engineering.symbolic import derive as D
    from academic_core.domain.engineering.symbolic import expr as SE

    assert set(FAMILY) <= set(D._TABLE), sorted(set(FAMILY) - set(D._TABLE))
    assert set(SE.FUNCTIONS) <= set(D._TABLE), sorted(set(SE.FUNCTIONS) - set(D._TABLE))


#: An argument inside each function's own domain. Not one shared value: `acosh`
#: needs `x >= 1` and `atanh` needs `|x| < 1`, so a single 0.5 for all fifteen
#: would put three of them outside their domain and the test would be asserting
#: the wrong thing.
ARGUMENTO = {
    "sec": "0.5", "csc": "0.5", "cot": "0.5",
    "asin": "0.5", "acos": "0.5", "atan": "0.5",
    "sinh": "0.5", "cosh": "0.5", "tanh": "0.5",
    "coth": "0.5", "sech": "0.5", "csch": "0.5",
    "asinh": "0.5", "acosh": "2.5", "atanh": "0.5",
}


@pytest.mark.parametrize("nombre", FAMILY)
def test_la_derivada_de_cada_funcion_nueva_es_la_que_dice_su_tabla(nombre):
    """La tabla de derivadas, comprobada por diferencias centrales.

    Numericamente y no comparando con el texto de la tabla: la tabla es lo que
    se esta comprobando, asi que compararla consigo misma pasaria siempre. El
    paso `h = 1e-25` a 65 digitos de_precision da al menos siete cifras por
    encima del redondeo para las quince, y las de crecimiento exponencial
    (sinh, cosh) siguen siendo lineales ahi.
    """
    from academic_core.domain.engineering.symbolic import derive as D
    from academic_core.domain.engineering.symbolic import expr as SE
    from academic_core.domain.engineering.symbolic import numeric

    ctx = T.make_context()
    x = Decimal(ARGUMENTO[nombre])
    h = Decimal("1e-25")
    kernel = getattr(T, f"decimal_{nombre}")
    numerica = ctx.divide(
        ctx.subtract(kernel(ctx.add(x, h)), kernel(ctx.subtract(x, h))),
        ctx.multiply(h, 2))
    derivada = D.differentiate(SE.Fn(nombre, SE.Sym("u")), "u", D.StepLog())[0]
    valor = numeric.value(derivada, {"u": x})
    assert valor is not None, (nombre, SE.text(derivada))
    assert abs(valor - numerica) < Decimal("1e-20"), (nombre, SE.text(derivada))


@pytest.mark.parametrize("nombre", FAMILY)
def test_el_evaluador_certificado_calcula_cada_una(nombre):
    """Las quince por el camino de verdad: el evaluador, no el kernel.

    El kernel puede ser correcto y la conexion estar mal, y esa fue exactamente
    la clase de fallo que se coló aqui: el reparto era `_family[nombre]` en
    lugar de `_family(nombre)`, de modo que los quince kernels eran correctos
    y las quince llamadas lanzaban `TypeError`. Ninguna prueba de valor lo
    habria visto; esta, que pasa por `parse_equation` -> `evaluate`, si.
    """
    cantidad = EQ.evaluate(EQ.parse_equation(f"X = {nombre}({ARGUMENTO[nombre]})"), {})
    esperado = getattr(T, f"decimal_{nombre}")(Decimal(ARGUMENTO[nombre]))
    assert _close(cantidad.value, esperado)
    assert cantidad.dimension == EQ.DIMENSIONLESS


@pytest.mark.parametrize("nombre", FAMILY)
def test_el_evaluador_certificado_exige_un_argumento_adimensional(nombre):
    with pytest.raises(EQ.EquationError, match="dimensionless"):
        EQ.evaluate(EQ.parse_equation(f"X = {nombre}(1 V)"),
                    {"V": EQ.Quantity(Decimal(1), EQ.parse_unit("V"))})


# ------------------------------------------------------------------- higiene

def test_el_modulo_no_trae_float():
    """`math/` esta bajo la regla sin-`float` de F8-K y este fichero esta en el.

    Comprobado parseando y no grepando texto, para que un `float` dentro de un
    comentario no lo dispare y uno de verdad no pueda esconderse detras de una
    concatenacion de cadenas.
    """
    arbol = ast.parse(SRC.read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name):
            assert nodo.func.id not in ("float", "complex"), (SRC.name, nodo.lineno)
        if isinstance(nodo, ast.Attribute) and nodo.attr in ("pi", "e", "tau"):
            assert not (isinstance(nodo.value, ast.Name)
                        and nodo.value.id == "math"), (SRC.name, nodo.lineno)


def test_el_evaluador_no_usa_atributo_calculado():
    """La puerta que cerro la certificacion E0, vista desde la tabla nueva.

    `_family` existe para que leer el reparto no exija
    `getattr(modulo, nombre)`. Una «simplificacion» futura de vuelta a una
    busqueda por nombre calculado pasaria todas las pruebas de valor mientras
    reabria en silencio la puerta que E0 cerro.
    """
    source = Path(EQ.__file__).read_text(encoding="utf-8")
    assert "getattr(" not in source
    assert "setattr(" not in source


def test_ningun_modulo_define_el_mismo_nombre_dos_veces():
    """Una segunda definicion pisa a la primera y no dice nada.

    Esto no es hipotetico: durante este trabajo `IMPRIMIBLE_Y_RELEGIBLE` quedo
    escrita dos veces en el mismo fichero de pruebas, la segunda con dos casos
    mas. Todo pasaba —los tests contaban lo mismo porque solo se ejecutaba la
    segunda definicion— y la primera era codigo muerto que nadie iba a leer jamas.

    Se comprueba con `ast` y no por busqueda de texto, para que un nombre
    repetido dentro de una cadena o de un comentario no lo dispare.
    """
    raices = [Path(EQ.__file__).parent, Path(EQ.__file__).parent / "symbolic",
              SRC.parent, Path(__file__).parent]
    repetidos = []
    for raiz in raices:
        for f in sorted(raiz.glob("*.py")):
            arbol = ast.parse(f.read_text(encoding="utf-8"))
            vistos: dict[str, int] = {}
            for nodo in arbol.body:
                nombres = []
                if isinstance(nodo, (ast.FunctionDef, ast.ClassDef)):
                    nombres = [nodo.name]
                elif isinstance(nodo, ast.Assign):
                    nombres = [t.id for t in nodo.targets if isinstance(t, ast.Name)]
                for nombre in nombres:
                    if nombre.startswith("__"):
                        continue
                    vistos[nombre] = vistos.get(nombre, 0) + 1
            for nombre, n in vistos.items():
                if n > 1:
                    repetidos.append((f.name, nombre, n))
    assert not repetidos, repetidos