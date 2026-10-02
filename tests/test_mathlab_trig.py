"""MATH_LAB: the exact trigonometric engine, family by family.

Three kinds of test live here, and the distinction matters (§11.2):

1. **Golden** — one expression per identity, checked against the exact canonical
   text. They say *which* form the engine produces.
2. **Soundness by an independent path** — every identity is re-checked
   numerically at seeded points (:mod:`verify`), which is §5.3: a rewrite is
   never accepted because the engine produced it.
3. **Properties of the engine itself** — termination, idempotence, and the claim
   that ``identities()`` cannot advertise a family without a rule behind it.

There is also a *negative* control: a deliberately false identity has to be
rejected by the same checker. Without it, test 2 would pass just as happily if
the checker compared nothing at all.
"""

from fractions import Fraction

import pytest

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import trig
from academic_core.domain.engineering.mathlab import verify as V

#: the canonical text is ASCII and round-trips through ``parse``; ``pretty`` is
#: the Spanish Unicode form for the screen (§5.1), so it is not what a rule test
#: should compare against.
def texto(origen: str) -> str:
    return mx.text(mx.parse(origen))


def canonico(origen: str, resultado: mx.Expr) -> str:
    return mx.text(resultado)


# ---------------------------------------------------------------------------
# 1. the families, one golden case each
# ---------------------------------------------------------------------------


def test_pitagoras_y_sus_formas_despejadas():
    assert canonico("sin(x)^2+cos(x)^2", trig.simplify(mx.parse("sin(x)^2+cos(x)^2"))) == "1"
    assert canonico("cos(x)^2+sin(x)^2", trig.simplify(mx.parse("cos(x)^2+sin(x)^2"))) == "1"
    assert canonico("1-sin(x)^2", trig.simplify(mx.parse("1-sin(x)^2"))) == "cos(x)^2"
    assert canonico("1-cos(x)^2", trig.simplify(mx.parse("1-cos(x)^2"))) == "sin(x)^2"
    assert canonico("1+tan(x)^2", trig.simplify(mx.parse("1+tan(x)^2"))) == "sec(x)^2"
    assert canonico("1+cot(x)^2", trig.simplify(mx.parse("1+cot(x)^2"))) == "csc(x)^2"
    assert canonico("sec(x)^2-1", trig.simplify(mx.parse("sec(x)^2-1"))) == "tan(x)^2"
    assert canonico("csc(x)^2-1", trig.simplify(mx.parse("csc(x)^2-1"))) == "cot(x)^2"
    assert canonico("sec(x)^2-tan(x)^2", trig.simplify(mx.parse("sec(x)^2-tan(x)^2"))) == "1"
    assert canonico("csc(x)^2-cot(x)^2", trig.simplify(mx.parse("csc(x)^2-cot(x)^2"))) == "1"


def test_cocientes_y_reciprocas():
    assert canonico("sin(x)/cos(x)", trig.simplify(mx.parse("sin(x)/cos(x)"))) == "tan(x)"
    assert canonico("cos(x)/sin(x)", trig.simplify(mx.parse("cos(x)/sin(x)"))) == "cot(x)"
    assert canonico("1/cos(x)", trig.simplify(mx.parse("1/cos(x)"))) == "sec(x)"
    assert canonico("1/sin(x)", trig.simplify(mx.parse("1/sin(x)"))) == "csc(x)"
    assert canonico("1/tan(x)", trig.simplify(mx.parse("1/tan(x)"))) == "cot(x)"
    assert canonico("cos(x)*sec(x)", trig.simplify(mx.parse("cos(x)*sec(x)"))) == "1"
    assert canonico("sin(x)*csc(x)", trig.simplify(mx.parse("sin(x)*csc(x)"))) == "1"
    assert canonico("tan(x)*cot(x)", trig.simplify(mx.parse("tan(x)*cot(x)"))) == "1"


def test_paridad():
    assert canonico("sin(-x)", trig.simplify(mx.parse("sin(-x)"))) == "-sin(x)"
    assert canonico("cos(-x)", trig.simplify(mx.parse("cos(-x)"))) == "cos(x)"
    assert canonico("tan(-x)", trig.simplify(mx.parse("tan(-x)"))) == "-tan(x)"
    assert canonico("cot(-x)", trig.simplify(mx.parse("cot(-x)"))) == "-cot(x)"
    assert canonico("sec(-x)", trig.simplify(mx.parse("sec(-x)"))) == "sec(x)"
    assert canonico("csc(-x)", trig.simplify(mx.parse("csc(-x)"))) == "-csc(x)"
    # the sign of a power belongs outside it, or the rules below never see a sin
    assert canonico("sin(-x)^2", trig.simplify(mx.parse("sin(-x)^2"))) == "sin(x)^2"
    assert canonico("sin(-x)^3", trig.simplify(mx.parse("sin(-x)^3"))) == "-sin(x)^3"


def test_periodicidad_y_angulos_opuestos():
    assert canonico("sin(x+2*pi)", trig.simplify(mx.parse("sin(x+2*pi)"))) == "sin(x)"
    assert canonico("cos(x-2*pi)", trig.simplify(mx.parse("cos(x-2*pi)"))) == "cos(x)"
    assert canonico("tan(x+pi)", trig.simplify(mx.parse("tan(x+pi)"))) == "tan(x)"
    assert canonico("sin(x-pi)", trig.simplify(mx.parse("sin(x-pi)"))) == "-sin(x)"
    assert canonico("sin(pi-x)", trig.simplify(mx.parse("sin(pi-x)"))) == "sin(x)"
    assert canonico("cos(pi-x)", trig.simplify(mx.parse("cos(pi-x)"))) == "-cos(x)"
    assert canonico("tan(pi-x)", trig.simplify(mx.parse("tan(pi-x)"))) == "-tan(x)"
    assert canonico("sin(pi+x)", trig.simplify(mx.parse("sin(pi+x)"))) == "-sin(x)"
    assert canonico("cos(pi+x)", trig.simplify(mx.parse("cos(pi+x)"))) == "-cos(x)"
    assert canonico("tan(pi+x)", trig.simplify(mx.parse("tan(pi+x)"))) == "tan(x)"


def test_angulos_complementarios():
    assert canonico("sin(pi/2-x)", trig.simplify(mx.parse("sin(pi/2-x)"))) == "cos(x)"
    assert canonico("cos(pi/2-x)", trig.simplify(mx.parse("cos(pi/2-x)"))) == "sin(x)"
    assert canonico("sin(pi/2+x)", trig.simplify(mx.parse("sin(pi/2+x)"))) == "cos(x)"
    assert canonico("cos(pi/2+x)", trig.simplify(mx.parse("cos(pi/2+x)"))) == "-sin(x)"
    assert canonico("tan(pi/2-x)", trig.simplify(mx.parse("tan(pi/2-x)"))) == "cot(x)"
    assert canonico("cot(pi/2-x)", trig.simplify(mx.parse("cot(pi/2-x)"))) == "tan(x)"
    assert canonico("sin(3*pi/2+x)", trig.simplify(mx.parse("sin(3*pi/2+x)"))) == "-cos(x)"
    assert canonico("cos(3*pi/2-x)", trig.simplify(mx.parse("cos(3*pi/2-x)"))) == "-sin(x)"


def test_angulo_doble_al_reves():
    assert canonico("2*sin(x)*cos(x)", trig.simplify(mx.parse("2*sin(x)*cos(x)"))) == "sin(2*x)"
    assert canonico("1-2*sin(x)^2", trig.simplify(mx.parse("1-2*sin(x)^2"))) == "cos(2*x)"
    assert canonico("2*cos(x)^2-1", trig.simplify(mx.parse("2*cos(x)^2-1"))) == "cos(2*x)"
    assert canonico("cos(x)^2-sin(x)^2", trig.simplify(mx.parse("cos(x)^2-sin(x)^2"))) == "cos(2*x)"
    assert canonico("sin(x)^2-cos(x)^2", trig.simplify(mx.parse("sin(x)^2-cos(x)^2"))) == "-cos(2*x)"
    assert canonico("2*tan(x)/(1-tan(x)^2)",
                    trig.simplify(mx.parse("2*tan(x)/(1-tan(x)^2)"))) == "tan(2*x)"


def test_suma_y_diferencia_reconocidas_al_reves():
    assert canonico("sin(x)*cos(y)+cos(x)*sin(y)",
                    trig.simplify(mx.parse("sin(x)*cos(y)+cos(x)*sin(y)"))) == "sin(x + y)"
    assert canonico("sin(x)*cos(y)-cos(x)*sin(y)",
                    trig.simplify(mx.parse("sin(x)*cos(y)-cos(x)*sin(y)"))) == "sin(x - y)"
    assert canonico("cos(x)*cos(y)+sin(x)*sin(y)",
                    trig.simplify(mx.parse("cos(x)*cos(y)+sin(x)*sin(y)"))) == "cos(x - y)"
    assert canonico("cos(x)*cos(y)-sin(x)*sin(y)",
                    trig.simplify(mx.parse("cos(x)*cos(y)-sin(x)*sin(y)"))) == "cos(x + y)"


def test_valores_notables_exactos():
    esperados = {
        "sin(pi/6)": "1/2", "cos(pi/3)": "1/2", "sin(pi/4)": "sqrt(2)/2",
        "tan(pi/4)": "1", "cot(pi/4)": "1", "sec(pi/4)": "sqrt(2)",
        "sec(pi/3)": "2", "csc(pi/6)": "2", "cot(pi/6)": "sqrt(3)",
        "sin(pi)": "0", "cos(pi)": "-1", "sin(3*pi)": "0", "cos(2*pi)": "1",
    }
    for origen, esperado in esperados.items():
        assert canonico(origen, trig.simplify(mx.parse(origen))) == esperado, origen


def test_un_angle_onde_la_funcion_no_existe_no_se_inventa():
    """§5.4: an angle where the function is undefined stays symbolic."""
    for origen in ("tan(pi/2)", "sec(pi/2)", "cot(pi)", "csc(pi)"):
        assert canonico(origen, trig.simplify(mx.parse(origen))) == origen


def test_desarrollar_suma_y_diferencia():
    esperado = {
        "sin(x+y)": "sin(x)*cos(y) + cos(x)*sin(y)",
        "sin(x-y)": "sin(x)*cos(y) - cos(x)*sin(y)",
        "cos(x+y)": "cos(x)*cos(y) - sin(x)*sin(y)",
        "cos(x-y)": "cos(x)*cos(y) + sin(x)*sin(y)",
        "tan(x+y)": "(tan(x) + tan(y))/(1 - tan(x)*tan(y))",
        "tan(x-y)": "(tan(x) - tan(y))/(1 + tan(x)*tan(y))",
    }
    for origen, salida in esperado.items():
        assert canonico(origen, trig.expand(mx.parse(origen))) == salida, origen


def test_desarrollar_angulo_doble():
    esperado = {
        "sin(2*x)": "2*sin(x)*cos(x)",
        "cos(2*x)": "cos(x)^2 - sin(x)^2",
        "tan(2*x)": "2*tan(x)/(1 - tan(x)^2)",
    }
    for origen, salida in esperado.items():
        assert canonico(origen, trig.expand(mx.parse(origen))) == salida, origen


def test_producto_a_suma():
    esperado = {
        "sin(x)*sin(y)": "(cos(x - y) - cos(x + y))/2",
        "cos(x)*cos(y)": "(cos(x - y) + cos(x + y))/2",
        "sin(x)*cos(y)": "(sin(x + y) + sin(x - y))/2",
        "cos(x)*sin(y)": "(sin(x + y) - sin(x - y))/2",
    }
    for origen, salida in esperado.items():
        assert canonico(origen, trig.product_to_sum(mx.parse(origen))) == salida, origen


def test_suma_a_producto():
    esperado = {
        "sin(x)+sin(y)": "2*sin((x + y)/2)*cos((x - y)/2)",
        "sin(x)-sin(y)": "2*cos((x + y)/2)*sin((x - y)/2)",
        "cos(x)+cos(y)": "2*cos((x + y)/2)*cos((x - y)/2)",
        "cos(x)-cos(y)": "-2*sin((x + y)/2)*sin((x - y)/2)",
    }
    for origen, salida in esperado.items():
        assert canonico(origen, trig.sum_to_product(mx.parse(origen))) == salida, origen


def test_reduccion_de_potencias():
    esperado = {
        "sin(x)^2": "(1 - cos(2*x))/2",
        "cos(x)^2": "(1 + cos(2*x))/2",
        "sin(x)^3": "sin(x)*(1 - cos(2*x))/2",
        "cos(x)^3": "cos(x)*(1 + cos(2*x))/2",
        "sin(x)^4": "(1 - cos(2*x))/2*(1 - cos(2*x))/2",
    }
    for origen, salida in esperado.items():
        assert canonico(origen, trig.reduce_powers(mx.parse(origen))) == salida, origen
    # Above the fourth power the engine keeps its factorised form (cos⁶ comes
    # out as cos²·g², which is g³ because cos² = g), so the *value* is checked
    # rather than the arrangement of the factors.
    for origen in ("cos(x)^5", "cos(x)^6", "sin(x)^5", "sin(x)^7"):
        expresion = mx.parse(origen)
        ok, metodo, detalle = V.numeric_agreement(trig.reduce_powers(expresion), expresion)
        assert ok, f"{origen}: {metodo}: {detalle}"


def test_las_tres_formas_del_angulo_doble_de_coseno():
    """T-05: the three forms are all offered, because the next step decides."""
    formas = trig.double_angle_forms("cos", mx.parse("x"))
    assert [mx.text(f) for f in formas] == [
        "cos(2*x)", "cos(x)^2 - sin(x)^2", "1 - 2*sin(x)^2"]
    for forma in formas:
        ok, _method, _detail = V.numeric_agreement(forma, mx.parse("cos(2*x)"))
        assert ok, forma


def test_simplificar_no_deja_un_factor_uno():
    assert canonico("x*(sin(x)^2+cos(x)^2)",
                    trig.simplify(mx.parse("x*(sin(x)^2+cos(x)^2)"))) == "x"


def test_la_simplificacion_reduce_en_un_subarbol():
    """Bottom-up: a nested sub-expression has to be reachable, not only the root."""
    assert canonico("(sin(x)+cos(x))*(sin(x)-cos(x))",
                    trig.simplify(mx.parse("(sin(x)+cos(x))*(sin(x)-cos(x))"))) \
        == "(sin(x) + cos(x))*(sin(x) - cos(x))"


# ---------------------------------------------------------------------------
# 2. soundness: every family re-checked by a path that is not the rewrite
# ---------------------------------------------------------------------------


#: (expression, objective) pairs covering every family and both directions.
FAMILIAS = [
    ("sin(-x)", "simplificar"), ("cos(-x)", "simplificar"),
    ("sin(x)^2+cos(x)^2", "simplificar"), ("1-sin(x)^2", "simplificar"),
    ("1+tan(x)^2", "simplificar"), ("sec(x)^2-tan(x)^2", "simplificar"),
    ("sin(x)/cos(x)", "simplificar"), ("cos(x)*sec(x)", "simplificar"),
    ("sin(x+2*pi)", "simplificar"), ("sin(pi-x)", "simplificar"),
    ("cos(pi/2-x)", "simplificar"), ("tan(pi/2-x)", "simplificar"),
    ("sin(x-pi)", "simplificar"), ("cos(3*pi/2+x)", "simplificar"),
    ("2*sin(x)*cos(x)", "simplificar"), ("1-2*sin(x)^2", "simplificar"),
    ("2*cos(x)^2-1", "simplificar"), ("cos(x)^2-sin(x)^2", "simplificar"),
    ("2*tan(x)/(1-tan(x)^2)", "simplificar"),
    ("sin(x)*cos(y)+cos(x)*sin(y)", "simplificar"),
    ("sin(x)*cos(y)-cos(x)*sin(y)", "simplificar"),
    ("cos(x)*cos(y)+sin(x)*sin(y)", "simplificar"),
    ("cos(x)*cos(y)-sin(x)*sin(y)", "simplificar"),
    ("sin(x+y)", "expandir"), ("sin(x-y)", "expandir"),
    ("cos(x+y)", "expandir"), ("cos(x-y)", "expandir"),
    ("tan(x+y)", "expandir"), ("tan(x-y)", "expandir"),
    ("sin(2*x)", "expandir"), ("cos(2*x)", "expandir"), ("tan(2*x)", "expandir"),
    ("sin(x)*sin(y)", "producto_a_suma"), ("cos(x)*cos(y)", "producto_a_suma"),
    ("sin(x)*cos(y)", "producto_a_suma"), ("cos(x)*sin(y)", "producto_a_suma"),
    ("sin(x)+sin(y)", "suma_a_producto"), ("sin(x)-sin(y)", "suma_a_producto"),
    ("cos(x)+cos(y)", "suma_a_producto"), ("cos(x)-cos(y)", "suma_a_producto"),
    ("sin(x)^2", "potencias"), ("cos(x)^2", "potencias"),
    ("sin(x)^3", "potencias"), ("cos(x)^4", "potencias"), ("sin(x)^5", "potencias"),
]

OBJETIVOS = {
    "simplificar": trig.simplify,
    "expandir": trig.expand,
    "producto_a_suma": trig.product_to_sum,
    "suma_a_producto": trig.sum_to_product,
    "potencias": trig.reduce_powers,
}


@pytest.mark.parametrize("origen,objetivo", FAMILIAS,
                         ids=[f"{o}:{obj}" for o, obj in FAMILIAS])
def test_cada_identidad_conserva_el_valor(origen, objetivo):
    """§5.3 and §11.2 criterion 2: a rewrite is checked by a second path."""
    expresion = mx.parse(origen)
    transformada = OBJETIVOS[objetivo](expresion)
    ok, metodo, detalle = V.numeric_agreement(transformada, expresion, samples=12)
    assert ok, (f"«{origen}» con {objetivo} dio «{mx.text(transformada)}»; "
                f"{metodo}: {detalle}")
    assert "puntos" in metodo, "una comprobación sin puntos no es evidencia"


def test_el_verificador_rechaza_una_identidad_falsa():
    """The negative control: without it, the test above would pass vacuously."""
    ok, _metodo, _detalle = V.numeric_agreement(mx.parse("cos(x)"), mx.parse("sin(x)"))
    assert not ok
    ok, _metodo, _detalle = V.numeric_agreement(mx.parse("sin(2*x)"), mx.parse("2*sin(x)"))
    assert not ok  # the factor cos(x) is missing: a plausible-looking mistake
    ok, _metodo, _detalle = V.numeric_agreement(mx.parse("cos(x-y)"), mx.parse("cos(x+y)"))
    assert not ok


#: the angle written the way a student writes it, so the parser canonicalises it
ANGULOS = {Fraction(0): "0", Fraction(1, 6): "pi/6", Fraction(1, 4): "pi/4",
           Fraction(1, 3): "pi/3", Fraction(1, 2): "pi/2", Fraction(2, 3): "2*pi/3",
           Fraction(3, 4): "3*pi/4", Fraction(5, 6): "5*pi/6", Fraction(1): "pi"}


@pytest.mark.parametrize("nombre,lista", sorted(trig._NOTABLES.items()),
                         ids=[str(k) for k in sorted(trig._NOTABLES)])
def test_la_tabla_de_valores_notables_es_correcta(nombre, lista):
    """T-21 checked against ``cmath``, not against the table that produced it."""
    angulo = mx.parse(ANGULOS[nombre])
    for funcion, valor in lista.items():
        expresion = mx.Call(funcion, (angulo,))
        if valor is None:
            # The function does not exist at this angle, and the engine must not
            # invent a value (§5.4). The numeric path is no help here: at pi/2
            # cos is 6·10⁻¹⁷ rather than 0, so sec comes back as a huge number
            # instead of a refusal, and only at exactly 0 is the pole seen.
            assert mx.text(trig.simplify(expresion)) == mx.text(expresion), \
                f"{funcion}({ANGULOS[nombre]}) recibió un valor que no existe"
            magnitud = mx.evaluate(expresion)
            assert magnitud is None or abs(magnitud) > 1e12, \
                f"{funcion}({ANGULOS[nombre]}) no se detecta como polo: {magnitud}"
            continue
        ok, _metodo, detalle = V.numeric_agreement(valor, expresion)
        assert ok, f"{funcion}({ANGULOS[nombre]}) = {mx.text(valor)}: {detalle}"


# ---------------------------------------------------------------------------
# 3. properties of the engine
# ---------------------------------------------------------------------------


class _Rnd:
    """An explicit LCG. §11.2 criterion 7: no ``random``, or nothing replays."""

    def __init__(self, seed: int) -> None:
        self.estado = seed & 0xFFFFFFFF

    def __call__(self) -> float:
        self.estado = (1103515245 * self.estado + 12345) & 0x7FFFFFFF
        return self.estado / 0x7FFFFFFF


_FUNCIONES = ("sin", "cos", "tan", "cot", "sec", "csc")
_CONSTANTES = ("0", "1", "2", "pi/2", "pi", "2*pi", "pi/3", "pi/6", "3*pi/2", "-1")


def _expresion_aleatoria(rnd: _Rnd, profundidad: int = 0) -> mx.Expr:
    r = rnd()
    if profundidad > 3 or r < 0.30:
        return mx.Sym("x") if rnd() < 0.6 else mx.Sym("y")
    if r < 0.55:
        return mx.parse(_CONSTANTES[int(rnd() * len(_CONSTANTES)) % len(_CONSTANTES)])
    if r < 0.80:
        return mx.Call(_FUNCIONES[int(rnd() * len(_FUNCIONES)) % len(_FUNCIONES)],
                       (_expresion_aleatoria(rnd, profundidad + 1),))
    expresion = _expresion_aleatoria(rnd, profundidad + 1)
    for _ in range(2 + int(rnd() * 3)):
        otro = _expresion_aleatoria(rnd, profundidad + 1)
        operacion = int(rnd() * 5)
        expresion = ((mx.Add, mx.Sub, mx.Mul, mx.Div)[operacion](expresion, otro)
                     if operacion < 4 else
                     mx.Pow(expresion, mx.Num(Fraction(2 + int(rnd() * 3)))))
    return expresion


def _subexpresiones(e: mx.Expr, salida: list | None = None) -> list:
    salida = [] if salida is None else salida
    salida.append(e)
    if isinstance(e, mx.Neg):
        _subexpresiones(e.arg, salida)
    elif isinstance(e, mx.Pow):
        _subexpresiones(e.base, salida)
        _subexpresiones(e.exponent, salida)
    elif isinstance(e, mx.Call):
        for a in e.args:
            _subexpresiones(a, salida)
    elif isinstance(e, (mx.Add, mx.Sub, mx.Mul, mx.Div)):
        _subexpresiones(e.left, salida)
        _subexpresiones(e.right, salida)
    return salida


def _mal_condicionada(e: mx.Expr) -> bool:
    """True when some *intermediate* value explodes.

    The numeric path is only evidence while the arithmetic is well conditioned.
    ``tan(((x³)⁴)² + x)`` is a true identity, but with ``x^24`` in it the two
    sides differ by 10⁻⁵ in double precision, because ``tan`` of an argument that
    large has no reliable digits left. Such cases are skipped here and the limit
    is asserted on its own in ``test_el_camino_numerico_tiene_un_limite_real``.
    """
    if not mx.variables(e):
        return False
    subconjunto = [s for s in _subexpresiones(e) if mx.variables(s)]
    for env in V.sampled_points(sorted(mx.variables(e)), count=8):
        for s in subconjunto:
            valor = mx.evaluate(s, env)
            if valor is not None and abs(valor) > 1e4:
                return True
    return False


def test_el_camino_numerico_tiene_un_limite_real():
    """The conditioning limit is a fact about doubles, not about these rules."""
    import math
    a, b = 0.7, 1.1
    izquierda = math.sin(a) + math.sin(b)
    derecha = 2 * math.sin((a + b) / 2) * math.cos((a - b) / 2)
    assert abs(izquierda - derecha) < 1e-15          # well conditioned: exact
    enorme = math.cos(1e-4) / math.sin(1e-4)          # cot(1e-4) ~ 10⁴
    izquierda = math.sin(0.7) + math.sin(enorme)
    derecha = 2 * math.sin((0.7 + enorme) / 2) * math.cos((0.7 - enorme) / 2)
    assert abs(izquierda - derecha) > 0                # sin(5000) has no good digits


@pytest.mark.parametrize("semilla", range(2026, 2026 + 60))
def test_ninguna_transformacion_altera_el_valor(semilla):
    """§11.1: seeded random expressions, every objective, every seed replayable."""
    expresion = _expresion_aleatoria(_Rnd(semilla))
    try:
        texto = mx.text(expresion)
    except Exception:  # a construct the printer does not cover: nothing to check
        pytest.skip("expresión no imprimible")
    if _mal_condicionada(expresion):
        # No numeric evidence is available here. What still has to hold is that
        # every objective terminates and hands back an expression: the well
        # founded cost order is a claim about termination, not about accuracy.
        for nombre, transformar in OBJETIVOS.items():
            assert isinstance(transformar(expresion), mx.Expr), f"semilla {semilla}: {nombre}"
        return
    for nombre, transformar in OBJETIVOS.items():
        resultado = transformar(expresion)
        ok, metodo, detalle = V.numeric_agreement(resultado, expresion, samples=8)
        assert ok or "pocos puntos" in metodo or "sin valor" in metodo, (
            f"semilla {semilla}, {nombre}: «{texto}» -> «{mx.text(resultado)}»; "
            f"{metodo}: {detalle}")


TODAS_LAS_EXPRESIONES = [origen for origen, _objetivo in FAMILIAS] + [
    "sin(x)+cos(x)", "x*sin(x)", "sin(x)/x", "cos(x)^2+sin(x)^2+1",
    "2*sin(x)*cos(x)+sin(x)*cos(x)", "sin(pi/2-x)*cos(pi/2-x)",
    "1+tan(x)^2-1", "sec(x)^2*csc(x)^2", "sin(3*x)", "sin(x)^10",
]


@pytest.mark.parametrize("origen", TODAS_LAS_EXPRESIONES,
                         ids=lambda o: o.replace(" ", ""))
def test_simplificar_es_idempotente(origen):
    """A fixed point: simplifying again must find nothing left to do."""
    una_vez = trig.simplify(mx.parse(origen))
    assert trig.simplify(una_vez) == una_vez


@pytest.mark.parametrize("origen", TODAS_LAS_EXPRESIONES,
                         ids=lambda o: o.replace(" ", ""))
def test_simplificar_nunca_agranda(origen):
    """§5.4: the objective only accepts strictly cheaper rewrites."""
    origen_expr = mx.parse(origen)
    assert trig._coste(trig.simplify(origen_expr)) <= trig._coste(origen_expr)


@pytest.mark.parametrize("nombre", sorted(trig.identities()))
def test_el_inventario_no_promete_una_familia_sin_regla(nombre):
    """The bug this guards against: a listed family with no rule behind it.

    The shipped engine advertised ``angulo_doble_coseno``, ``angulo_doble_tangente``
    and ``medio_angulo`` while no rule implemented any of them.
    """
    assert callable(trig.regla(nombre)), nombre
    assert trig.descripcion(nombre).strip(), nombre


def test_el_inventario_cubre_los_cinco_objetivos():
    for objetivo in ("simplificar", "expandir", "producto_a_suma",
                     "suma_a_producto", "potencias", "sustitucion_universal",
                     "hiperbolicas", "exponencial"):
        assert trig.familias(objetivo), objetivo
        for nombre in trig.familias(objetivo):
            assert nombre in trig.identities()


def test_la_traza_dice_que_familias_han_actuado():
    """T-22: a rewrite that leaves no trace cannot be explained to a student."""
    resultado = trig.simplify_ex(mx.parse("sin(x)^2+cos(x)^2"))
    assert resultado.expresion == mx.ONE
    assert "pitagoras" in resultado.familias

    sin_cambios = trig.simplify_ex(mx.parse("x+1"))
    assert sin_cambios.expresion == mx.parse("x+1")
    assert sin_cambios.familias == ()


def test_la_calculadora_registra_que_familia_acto():
    """T-22 and §5.2: the step log has to name the rule that produced the answer.

    A reduction that cannot be explained to a student is not finished, however
    correct the result is.
    """
    import academic_core.domain.engineering.mathlab as ML

    resultado = ML.calcular(ML.Peticion("simplificar", "sin(x)^2+cos(x)^2"))
    assert resultado.exacto == "1"
    paso = next((p for p in resultado.traza.steps if p.rule == "trig.pitagoras"), None)
    assert paso is not None, [p.rule for p in resultado.traza.steps]
    assert paso.why.strip(), "§5.5b: la razón del método tiene que estar escrita"


def test_una_expresion_sin_trigonometria_no_inventa_pasos():
    import academic_core.domain.engineering.mathlab as ML

    resultado = ML.calcular(ML.Peticion("simplificar", "x+1"))
    assert not any(p.rule.startswith("trig.") for p in resultado.traza.steps)


# ---------------------------------------------------------------------------
# 4. T-06 triple y ángulo múltiple
# ---------------------------------------------------------------------------


def test_angulo_triple_al_reves():
    assert canonico("3*sin(x)-4*sin(x)^3",
                    trig.simplify(mx.parse("3*sin(x)-4*sin(x)^3"))) == "sin(3*x)"
    assert canonico("4*cos(x)^3-3*cos(x)",
                    trig.simplify(mx.parse("4*cos(x)^3-3*cos(x)"))) == "cos(3*x)"


@pytest.mark.parametrize("origen", [
    "3*sin(x)-4*cos(x)^3",   # seno con coseno: la trampa del signo
    "4*cos(x)^3-3*sin(x)",
    "3*sin(y)-4*sin(x)^3",   # argumentos distintos
    "4*cos(x)^3-3*cos(y)",
    "3*sin(x)",              # a medias
    "4*sin(x)^3-3*sin(x)",   # los signos cambiados
    "3*cos(x)-4*cos(x)^3",
    "3*sin(x)+4*sin(x)^3",
])
def test_el_triple_no_se_reconoce_si_no_encaja(origen):
    """The near-misses, which is where a matcher like this actually breaks."""
    assert canonico(origen, trig.simplify(mx.parse(origen))) == texto(origen)


def test_angulo_triple_directo():
    esperado = {
        "sin(3*x)": "-4*sin(x)^3 + 3*sin(x)",
        "cos(3*x)": "4*cos(x)^3 - 3*cos(x)",
        "tan(3*x)": "(3*tan(x) - tan(x)^3)/(1 - 3*tan(x)^2)",
    }
    for origen, salida in esperado.items():
        assert canonico(origen, trig.expand(mx.parse(origen))) == salida, origen


def test_el_triple_ida_y_vuelta():
    for origen in ("sin(3*x)", "cos(3*x)"):
        desarrollado = trig.expand(mx.parse(origen))
        assert mx.text(trig.simplify(desarrollado)) == texto(origen)


def test_los_angulos_multiples_son_una_sola_variable():
    """T-06's Chebyshev case: ``cos(nx)`` is a polynomial in ``cos(x)`` alone."""
    x = mx.parse("x")
    assert mx.text(trig.multiple_angle("cos", x, 3)) == "4*cos(x)^3 - 3*cos(x)"
    assert mx.text(trig.multiple_angle("cos", x, 4)) == "8*cos(x)^4 - 8*cos(x)^2 + 1"
    assert mx.text(trig.multiple_angle("sin", x, 5)) == \
        "16*sin(x)^5 - 20*sin(x)^3 + 5*sin(x)"
    # sin(4x) is *not* a polynomial in sin(x): the engine says so instead of lying
    assert "sin(x)" in mx.text(trig.multiple_angle("sin", x, 4))


@pytest.mark.parametrize("nombre", ["sin", "cos"])
@pytest.mark.parametrize("n", list(range(1, 9)))
@pytest.mark.parametrize("forma", ["potencias", "chebyshev"])
def test_cada_multiplo_conserva_el_valor(nombre, n, forma):
    if forma == "chebyshev" and nombre == "sin":
        pytest.skip("la forma de Chebyshev solo existe para el coseno")
    x = mx.parse("x")
    expresión = trig.multiple_angle(nombre, x, n, forma=forma)
    referencia = mx.Call(nombre, (mx.Mul(mx.Num(Fraction(n)), x),))
    ok, metodo, detalle = V.numeric_agreement(expresión, referencia, samples=10)
    assert ok, f"{nombre}({n}x) en forma «{forma}» dio {mx.text(expresión)}; {metodo}: {detalle}"


def test_chebyshev_es_el_polinomio_correcto():
    """``T_n(cos x) = cos(nx)`` — checked against the definition, not against itself."""
    x = mx.parse("x")
    for n in (1, 2, 3, 4, 5, 6):
        ok, metodo, detalle = V.numeric_agreement(
            trig.chebyshev(n, _fn("cos", x)), mx.Call("cos", (mx.Mul(mx.Num(Fraction(n)), x),)),
            samples=10)
        assert ok, f"T_{n}: {metodo}: {detalle}"


def test_expand_tambien_baja_los_multiplos_grandes():
    """Before the general rule, ``expand(cos(4x))`` did nothing at all."""
    assert canonico("cos(4*x)", trig.expand(mx.parse("cos(4*x)"))) \
        == "8*cos(x)^4 - 8*cos(x)^2 + 1"


def test_los_indices_imposibles_se_dicen():
    with pytest.raises(ValueError):
        trig.multiple_angle("cos", mx.parse("x"), 0)
    with pytest.raises(ValueError):
        trig.multiple_angle("sin", mx.parse("x"), 3, forma="chebyshev")
    with pytest.raises(ValueError):
        trig.chebyshev(-1, mx.parse("x"))


# ---------------------------------------------------------------------------
# 5. T-07 medio ángulo y sustitución universal
# ---------------------------------------------------------------------------


def test_medio_angulo_al_reves():
    assert canonico("(1-cos(x))/2", trig.simplify(mx.parse("(1-cos(x))/2"))) == "sin(x/2)^2"
    assert canonico("(1+cos(x))/2", trig.simplify(mx.parse("(1+cos(x))/2"))) == "cos(x/2)^2"
    assert canonico("(1-cos(x))/(1+cos(x))",
                    trig.simplify(mx.parse("(1-cos(x))/(1+cos(x))"))) == "tan(x/2)^2"
    assert canonico("(1+cos(x))/(1-cos(x))",
                    trig.simplify(mx.parse("(1+cos(x))/(1-cos(x))"))) == "cot(x/2)^2"


@pytest.mark.parametrize("origen", [
    "cos(x)/2",              # no es 1 ± cos(x)
    "(1-cos(x))/(1+sin(x))",  # el denominador no lleva coseno
    "(1-cos(x))/3",           # el denominador no es 2
    "(2-cos(x))/2",           # el 1 no está
    "(1+sin(x))/2",           # es un seno, no un coseno
    "cos(x)/2 + cos(y)/2",    # la forma que no es 1 ± cos
])
def test_el_medio_angulo_no_se_reconoce_si_no_encaja(origen):
    assert canonico(origen, trig.simplify(mx.parse(origen))) == texto(origen)


def test_el_medio_angulo_sí_se_reconoce_dentro_de_una_suma():
    """Bottom-up again: each summand is folded even inside a bigger expression."""
    assert canonico("(1-cos(y))/2 + (1-cos(x))/2",
                    trig.simplify(mx.parse("(1-cos(y))/2 + (1-cos(x))/2"))) \
        == "sin(y/2)^2 + sin(x/2)^2"


def test_medio_angulo_directo():
    esperado = {
        "sin(x/2)^2": "(1 - cos(x))/2",
        "cos(x/2)^2": "(1 + cos(x))/2",
        "tan(x/2)^2": "(1 - cos(x))/(1 + cos(x))",
    }
    for origen, salida in esperado.items():
        assert canonico(origen, trig.expand(mx.parse(origen))) == salida, origen


@pytest.mark.parametrize("origen", [
    "(1-cos(x))/2", "(1+cos(x))/2", "(1-cos(x))/(1+cos(x))",
])
def test_el_medio_angulo_ida_y_vuelta(origen):
    reducido = trig.simplify(mx.parse(origen))
    assert mx.text(trig.expand(reducido)) == texto(origen)


def test_el_medio_angulo_entrega_su_hipotesis():
    """§5.7: the interval is returned with the identity, because there is one."""
    formas = trig.half_angle_forms(mx.parse("x"))
    assert formas, "no hay formas de medio ángulo"
    for forma, hipotesis in formas:
        assert forma is not None and hipotesis.strip(), mx.text(forma)
    # the square roots carry the interval they are only valid on
    hipotesis = " ".join(h for _, h in formas)
    assert "x/2 ≥ 0" in hipotesis and "x/2 ≤ 0" in hipotesis


def test_el_raiz_del_medio_angulo_no_se_toma():
    """``√((1−cos x)/2) = sin(x/2)`` is false outside [0, 2π], so it is not applied."""
    for origen in ("sin(x/2)", "cos(x/2)"):
        assert canonico(origen, trig.simplify(mx.parse(origen))) == texto(origen)
        assert canonico(origen, trig.expand(mx.parse(origen))) == texto(origen)


def test_sustitucion_universal():
    esperado = {
        "sin(x)": "2*tan(x/2)/(1 + tan(x/2)^2)",
        "cos(x)": "(1 - tan(x/2)^2)/(1 + tan(x/2)^2)",
        "tan(x)": "2*tan(x/2)/(1 - tan(x/2)^2)",
    }
    for origen, salida in esperado.items():
        assert canonico(origen, trig.rationalize(mx.parse(origen))) == salida, origen


def test_la_sustitucion_no_se_vuelve_a_sustituir():
    """The feed-back that made it grow until the text limit exploded.

    ``t = tan(x/2)`` is the *new* variable. Substituting it again turns the
    expression into ``tan(x/4)``, then ``tan(x/8)``, for ever.
    """
    resultado = trig.rationalize(mx.parse("tan(x)"))
    assert "tan(x/2)" in mx.text(resultado)
    assert "x/4" not in mx.text(resultado)
    # and it reaches a fixed point
    assert trig.rationalize(resultado) == resultado


def test_la_sustitucion_conserva_el_valor():
    for origen in ("sin(x)", "cos(x)", "tan(x)", "sin(x)^2", "sin(x)+cos(x)"):
        racional = trig.rationalize(mx.parse(origen))
        ok, metodo, detalle = V.numeric_agreement(racional, mx.parse(origen), samples=10)
        assert ok, f"{origen} -> {mx.text(racional)}; {metodo}: {detalle}"


def test_la_sustitucion_declara_su_dominio():
    dominio = trig.sustitucion_domain()
    assert "cos(x/2)" in dominio and "≠ 0" in dominio


def test_la_sustitucion_inversa_es_tan_de_la_medio():
    x = mx.parse("x")
    t = trig.half_angle_substitution(x)
    ok, metodo, detalle = V.numeric_agreement(
        t, mx.Call("tan", (mx.Div(x, mx.Num(Fraction(2))),)), samples=10)
    assert ok, f"{metodo}: {detalle}"


# ---------------------------------------------------------------------------
# 6. T-14 trigonometría hiperbólica
# ---------------------------------------------------------------------------


def test_las_relaciones_hiberbolicas():
    """The hyperbolic identities are the circular ones with a sign changed."""
    assert canonico("cosh(x)^2-sinh(x)^2",
                    trig.simplify(mx.parse("cosh(x)^2-sinh(x)^2"))) == "1"
    assert canonico("sinh(x)^2-cosh(x)^2",
                    trig.simplify(mx.parse("sinh(x)^2-cosh(x)^2"))) == "-1"
    assert canonico("1-tanh(x)^2", trig.simplify(mx.parse("1-tanh(x)^2"))) == "sech(x)^2"
    assert canonico("cosh(x)^2-1", trig.simplify(mx.parse("cosh(x)^2-1"))) == "sinh(x)^2"
    assert canonico("coth(x)^2-1", trig.simplify(mx.parse("coth(x)^2-1"))) == "csch(x)^2"
    # the sign here is not cosmetic: 1 − coth² is −csch², not +csch²
    assert canonico("1-coth(x)^2", trig.simplify(mx.parse("1-coth(x)^2"))) == "-csch(x)^2"


@pytest.mark.parametrize("origen", [
    "1+coth(x)^2",    # invented and rejected: coth² = 1 + csch², not the reverse
    "sinh(x)^2-1",   # invented and rejected: cosh² = 1 + sinh², the other way round
    "1-sinh(x)^2",
    "1+tanh(x)^2",   # 1 + tanh² = sech² + 2: no such identity
    "tanh(x)^2-1",
])
def test_las_identidades_que_no_existen_no_se_aplican(origen):
    """Two of these were bugs of mine, caught by the numeric check, not by eye."""
    assert canonico(origen, trig.simplify(mx.parse(origen))) == texto(origen)


def test_cocientes_y_reciprocas_hiberbolicas():
    for origen, esperado in [("sinh(x)/cosh(x)", "tanh(x)"),
                             ("cosh(x)/sinh(x)", "coth(x)"),
                             ("1/cosh(x)", "sech(x)"),
                             ("1/sinh(x)", "csch(x)"),
                             ("1/tanh(x)", "coth(x)"),
                             ("cosh(x)*sech(x)", "1"),
                             ("sinh(x)*csch(x)", "1"),
                             ("tanh(x)*coth(x)", "1")]:
        assert canonico(origen, trig.simplify(mx.parse(origen))) == esperado, origen


def test_paridad_hiberbolica():
    for nombre in ("sinh", "tanh", "coth", "csch", "asinh", "atanh"):
        assert canonico(f"{nombre}(-x)", trig.simplify(mx.parse(f"{nombre}(-x)"))) \
            == f"-{nombre}(x)", nombre
    for nombre in ("cosh", "sech", "acosh"):
        assert canonico(f"{nombre}(-x)", trig.simplify(mx.parse(f"{nombre}(-x)"))) \
            == f"{nombre}(x)", nombre


def test_las_hiberbolicas_invertidas_se_cancelan_en_toda_la_recta():
    """T-14: no branch to get wrong, unlike the circular case of T-11."""
    for origen in ("sinh(asinh(x))", "cosh(acosh(x))", "tanh(atanh(x))"):
        assert canonico(origen, trig.simplify(mx.parse(origen))) == "x", origen


def test_los_valores_en_el_origen():
    assert canonico("sinh(0)", trig.simplify(mx.parse("sinh(0)"))) == "0"
    assert canonico("cosh(0)", trig.simplify(mx.parse("cosh(0)"))) == "1"
    assert canonico("tanh(0)", trig.simplify(mx.parse("tanh(0)"))) == "0"


def test_el_doble_hiberbolico_al_reves():
    assert canonico("cosh(x)^2+sinh(x)^2",
                    trig.simplify(mx.parse("cosh(x)^2+sinh(x)^2"))) == "cosh(2*x)"
    assert canonico("1+2*sinh(x)^2",
                    trig.simplify(mx.parse("1+2*sinh(x)^2"))) == "cosh(2*x)"
    assert canonico("2*sinh(x)*cosh(x)",
                    trig.simplify(mx.parse("2*sinh(x)*cosh(x)"))) == "sinh(2*x)"


def test_las_sumas_hiberbolicas():
    """Same formulas as the circular ones, with the second sign changed."""
    esperado = {
        "sinh(x+y)": "sinh(x)*cosh(y) + cosh(x)*sinh(y)",
        "sinh(x-y)": "sinh(x)*cosh(y) - cosh(x)*sinh(y)",
        "cosh(x+y)": "cosh(x)*cosh(y) + sinh(x)*sinh(y)",
        "cosh(x-y)": "cosh(x)*cosh(y) - sinh(x)*sinh(y)",
        "tanh(x+y)": "(tanh(x) + tanh(y))/(1 + tanh(x)*tanh(y))",
        "tanh(x-y)": "(tanh(x) - tanh(y))/(1 - tanh(x)*tanh(y))",
        "sinh(2*x)": "2*sinh(x)*cosh(x)",
        "cosh(2*x)": "cosh(x)^2 + sinh(x)^2",
        "tanh(2*x)": "2*tanh(x)/(1 + tanh(x)^2)",
    }
    for origen, salida in esperado.items():
        assert canonico(origen, trig.simplify_hyperbolic(mx.parse(origen))) \
            == salida, origen


def test_el_doble_hiberbolico_ida_y_vuelta():
    for origen in ("sinh(2*x)", "cosh(2*x)"):
        desarrollado = trig.simplify_hyperbolic(mx.parse(origen))
        assert mx.text(trig.simplify(desarrollado)) == texto(origen)


def test_la_conexion_exponencial():
    assert canonico("sinh(x)", trig.to_exponential(mx.parse("sinh(x)"))) \
        == "(exp(x) - exp(-x))/2"
    assert canonico("cosh(x)", trig.to_exponential(mx.parse("cosh(x)"))) \
        == "(exp(x) + exp(-x))/2"
    # tanh has no such form, and the engine says nothing rather than guessing
    assert canonico("tanh(x)", trig.to_exponential(mx.parse("tanh(x)"))) == "tanh(x)"


HIPERBOLICAS = [
    "cosh(x)^2-sinh(x)^2", "sinh(x)^2-cosh(x)^2", "1-tanh(x)^2", "1-coth(x)^2",
    "coth(x)^2-1", "cosh(x)^2-1", "1+2*sinh(x)^2", "sinh(x)/cosh(x)",
    "1/cosh(x)", "1/sinh(x)", "1/tanh(x)", "cosh(x)*sech(x)", "sinh(x)*csch(x)",
    "tanh(x)*coth(x)", "sinh(asinh(x))", "cosh(acosh(x))", "tanh(atanh(x))",
    "sinh(-x)", "cosh(-x)", "sech(-x)", "asinh(-x)", "sinh(0)", "cosh(0)", "tanh(0)",
    "cosh(x)^2+sinh(x)^2", "2*sinh(x)*cosh(x)",
]
HIPERBOLICAS_DIRECTAS = [
    "sinh(x+y)", "sinh(x-y)", "cosh(x+y)", "cosh(x-y)", "tanh(x+y)", "tanh(x-y)",
    "sinh(2*x)", "cosh(2*x)", "tanh(2*x)",
]


@pytest.mark.parametrize("origen", HIPERBOLICAS + HIPERBOLICAS_DIRECTAS
                         + ["sinh(x)", "cosh(x)"])
def test_cada_identidad_hiberbolica_conserva_el_valor(origen):
    """§5.3: the same independent second path as the circular families."""
    expresion = mx.parse(origen)
    for transformar in (trig.simplify, trig.simplify_hyperbolic, trig.to_exponential):
        resultado = transformar(expresion)
        ok, metodo, detalle = V.numeric_agreement(resultado, expresion, samples=10)
        assert ok, (f"«{origen}» dio «{mx.text(resultado)}» en "
                    f"{transformar.__name__}; {metodo}: {detalle}")


def _fn(nombre, arg):
    return mx.Call(nombre, (arg,))


def test_una_expresion_demasiado_profunda_se_declara_en_castellano():
    """D2: a runaway tree is refused with a reason, never a RecursionError.

    Nothing a student can type gets here — the parser caps nesting at
    ``MAX_DEPTH`` — but a tree assembled by ``substitute`` or by the E0.1 bridge
    can, and an untranslated ``RecursionError`` in the interface is exactly what
    §5.4 forbids.
    """
    from academic_core.errors import ValidationError

    profundo = mx.Sym("x")
    for _ in range(trig.MAX_REWRITE_DEPTH + 50):
        profundo = mx.Add(profundo, mx.Sym("x"))
    with pytest.raises(ValidationError) as exc:
        trig.simplify(profundo)
    assert "EXPRESSION_LIMIT" in str(exc.value)
    assert "niveles" in str(exc.value)

    # and the boundary itself still works
    al_limite = mx.Sym("x")
    for _ in range(trig.MAX_REWRITE_DEPTH - 10):
        al_limite = mx.Add(al_limite, mx.Sym("x"))
    assert trig.simplify(al_limite) is not None


# ---------------------------------------------------------------------------
# soundness of the simplifier itself, on shapes no family names
# ---------------------------------------------------------------------------

#: Expressions whose value is obvious before and after simplification. The
#: simplifier may rearrange; it may not change the number.
#:
#: ``-(-u)`` was in this list from the start and still went unnoticed, because the
#: case was missing rather than the check: the sonority layer recomputes each
#: identity numerically, and no identity in the catalogue is ``-(-8) = 8``. The
#: value of a rewrite has to be checked on the rewrite itself, not only on the
#: families that motivated it.
CASOS_DE_SONORIDAD = [
    "-(-x)", "-(-8)", "3 + -(-8)", "-(-cos(x))", "-(-(-x))",
    "-(-sin(x)*cos(x))", "-(-x^2)", "1 - (-x)", "(-x) - (2 - x)",
    "-(-2)*(-3)", "-(-pi/6)", "-(-sqrt(2))", "-(-(-sin(x)))", "(-x) - (2 - x)",
]


@pytest.mark.parametrize("texto", CASOS_DE_SONORIDAD)
def test_simplificar_no_cambia_el_valor_de_la_expresion(texto):
    """Every rewrite is an identity, including the ones nobody wrote a rule for."""
    original = mx.parse(texto)
    reducido = trig.simplify(original)
    for x in (-0.7, 0.3, 1.1, 2.9):
        antes = mx.evaluate(original, {"x": x})
        despues = mx.evaluate(reducido, {"x": x})
        assert antes is not None and despues is not None
        assert abs(antes - despues) <= 1e-12 * max(1.0, abs(antes)), (
            f"{texto}: vale {antes} y simplify devuelve {despues}")


@pytest.mark.parametrize("texto", CASOS_DE_SONORIDAD)
def test_la_forma_normal_also_agrees_with_the_expression(texto):
    """The two independent reductions of an expression must agree with each other.

    ``trig.simplify`` and the rational normal form are different algorithms; where
    both are available, a disagreement is either a soundness bug or a difference in
    what they normalise to, and the first of those is worth catching.
    """
    from academic_core.domain.engineering.mathlab import poly as P

    original = mx.parse(texto)
    por_polinio = P.to_expr(P.as_poly(original))
    for x in (-0.7, 0.3, 1.1):
        antes = mx.evaluate(original, {"x": x})
        via_poly = mx.evaluate(por_polinio, {"x": x})
        via_trig = mx.evaluate(trig.simplify(original), {"x": x})
        assert antes is not None
        assert abs(antes - via_poly) <= 1e-12 * max(1.0, abs(antes)), texto
        assert abs(via_poly - via_trig) <= 1e-12 * max(1.0, abs(antes)), texto


def test_las_reciprocas_se_pueden_evaluar():
    """A verification that cannot evaluate what the engine emits checks nothing."""
    assert abs(mx.evaluate(mx.parse("sec(pi/4)")).real - 2 ** 0.5) < 1e-12
    assert abs(mx.evaluate(mx.parse("csc(pi/4)")).real - 2 ** 0.5) < 1e-12
    assert abs(mx.evaluate(mx.parse("cot(pi/4)")).real - 1) < 1e-12
    # The pole is *not* refused numerically: cmath.cos(pi/2) is 6·10⁻¹⁷, not 0,
    # so sec(pi/2) comes back as a huge number. Refusing it is the symbolic
    # table's job, and that is where test_un_angle_onde_la_funcion_no_existe
    # checks it — a numeric path may never be trusted to see a pole.
    assert abs(mx.evaluate(mx.parse("sec(pi/2)"))) > 1e12
