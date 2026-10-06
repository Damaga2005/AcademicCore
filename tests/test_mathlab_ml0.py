"""MATH_LAB ML-0 — the foundations of the mathematics laboratory.

Follows the project's convention: domain tests with **no Qt**, deterministic
generation only (an explicit LCG, never the ``random`` module), and seeded
properties alongside golden examples (§11.1).

What is tested, and why each group exists:

- **parsing** — the text input of §8.1 (``x^2``, ``sen``, ``0,5``, ``2x``), the
  round trip ``parse(text(e)) == e``, and Spanish errors that say *where* the
  problem is;
- **exactness** — fractions, roots and ``pi``/``e``/``i`` stay exact, and what
  is *not* exact is reported as such instead of being quietly rounded;
- **calculus objects** — ``integral``/``limite``/``suma``/``derivada`` are
  first-class and their bound variable is not a free one;
- **equivalence** — the corrector of §7: ``2x+2x`` matches ``4x``, ``(x²−1)/(x−1)``
  matches ``x+1`` *and reports the excluded value*, and ``cos(2x)`` does not
  match ``2cos(x)``;
- **the trace** — the three levels of §5.2, the mandatory «por qué este método»
  of §5.5b, and the versioned serialisation of §5.9;
- **verification** — the three seals of §8.1, and the seeded property that a
  derivative agrees with a central difference;
- **the contract** — one entry point, plug-in registration, and the honest
  downgrade when no external verifier exists;
- **the boundary** — the laboratory never touches Qt, the filesystem or a
  third-party library, and it does not rewrite the E0.1 engine.
"""

from __future__ import annotations

import ast
import pathlib
import sys

import pytest

from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import derive_mv as D
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import poly as P
from academic_core.domain.engineering.mathlab import trace as TR
from academic_core.domain.engineering.mathlab import verify as V

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "academic_core"
ML = SRC / "domain" / "engineering" / "mathlab"


# ===========================================================================
# parsing and text input (§8.1)
# ===========================================================================


@pytest.mark.parametrize("source,esperado", [
    ("x^2+1", "x^2 + 1"),
    ("2x", "2*x"),
    ("3pi", "3*pi"),
    ("2sin(x)", "2*sin(x)"),
    ("(x+1)(x-1)", "(x + 1)*(x - 1)"),
    ("x y", "x*y"),
    ("2^0.5", "sqrt(2)"),
    ("x^(1/3)", "raiz(x, 3)"),
    ("1/2", "1/2"),
    ("0,5", "1/2"),
    ("abs(x-1)", "abs(x - 1)"),
    ("sen(pi/2)", "sin(pi/2)"),
    ("e^x", "e^x"),
    ("i^2", "i^2"),
    ("log(2,8)", "log(2, 8)"),
])
def test_parse_acepta_la_entrada_de_la_spec(source, esperado):
    assert mx.text(mx.parse(source)) == esperado


@pytest.mark.parametrize("source", [
    "x^2+1", "2x", "3pi", "(x+1)(x-1)", "sqrt(2)^2", "0,5", "abs(x-1)",
    "e^x", "i^2", "log(2,8)", "1/(x+1)", "-x^2", "2^(1/3)", "x*y*z",
    "x^2/(3y)", "a/b/c",
])
def test_text_vuelta_al_analizador(source):
    """``parse(text(e)) == e``: the canonical form must round-trip (§5.1)."""
    e = mx.parse(source)
    assert mx.text(mx.parse(mx.text(e))) == mx.text(e)


def test_la_coma_decimal_y_el_separador_de_argumentos_no_se_confunden():
    """``0,5`` is one half; ``raiz(8,3)`` is the third root of 8, not 8.3."""
    assert mx.exact_value(mx.parse("0,5")) == mx.exact_value(mx.parse("1/2"))
    raiz = mx.parse("raiz(8,3)")
    assert isinstance(raiz, mx.Root) and raiz.degree == 3
    assert mx.exact_value(raiz) == 2


def test_un_nombre_de_letras_se_descompone_y_uno_indexado_no():
    """``2xy`` is ``2·x·y``; ``x1`` and ``t_0`` are single variables.

    The rule is the one a student expects: a run of plain letters is a product,
    a name with a digit or an underscore is one variable.
    """
    assert mx.variables(mx.parse("2xy")) == {"x", "y"}
    assert mx.variables(mx.parse("x1")) == {"x1"}
    assert mx.variables(mx.parse("t_0")) == {"t_0"}
    assert mx.variables(mx.parse("x2y3")) == {"x2y3"}
    # the reserved names always win over the split
    assert mx.variables(mx.parse("pi")) == set()
    assert mx.variables(mx.parse("2sin(x)")) == {"x"}
    assert mx.variables(mx.parse("sen(pi/2)")) == set()


@pytest.mark.parametrize("source,fragmento", [
    ("x+", "termina antes"),
    ("(x+1", "falta"),
    ("x=3", "igualdad"),
    ("raiz(8,x)", "índice"),
    ("desconocida(x)", "no es una función conocida"),
    ("x^^2", "no se esperaba"),
    ("2 sin x", "sobra"),
])
def test_los_errores_dicen_donde_esta_el_problema(source, fragmento):
    """Spanish errors, and they must locate the problem (§5.1)."""
    with pytest.raises(Exception) as exc:
        mx.parse(source)
    mensaje = str(exc.value)
    assert fragmento in mensaje, mensaje
    # the message must locate the problem, either by offset or by saying where
    # the expression ran out
    assert ("posición" in mensaje or "final de la expresión" in mensaje
            or "termina" in mensaje), mensaje


def test_preview_no_lanza_excepcion():
    """The editor shows the message under the field; it must never crash."""
    assert mx.preview("x^2+1") == "x² + 1"
    assert mx.preview("x+").startswith("⚠")
    assert mx.preview("") != ""


def test_los_limites_de_entrada_se_cumplen():
    from academic_core.errors import ValidationError

    with pytest.raises(ValidationError):
        mx.parse("x" * (mx.MAX_SOURCE + 1))
    with pytest.raises(ValidationError):
        mx.parse("x" * mx.MAX_SOURCE)  # fine, but too deep when parenthesised
    with pytest.raises(ValidationError):
        mx.parse("(" * (mx.MAX_DEPTH + 5) + "x" + ")" * (mx.MAX_DEPTH + 5))


# ===========================================================================
# exactness (§5.1, §5.4)
# ===========================================================================


@pytest.mark.parametrize("source,esperado", [
    ("1/2", "1/2"),
    ("0,5", "1/2"),
    ("0.5", "1/2"),
    ("1/2+1/2", "1"),
    ("2/4", "1/2"),
    ("sqrt(4)", "2"),
    ("sqrt(9/4)", "3/2"),
    ("raiz(8,3)", "2"),
    ("-2+2", "0"),
])
def test_los_racionales_y_las_raices_exactas_lo_son(source, esperado):
    valor = mx.exact_value(mx.parse(source))
    assert valor is not None, source
    assert mx.text(valor) == esperado


@pytest.mark.parametrize("source", ["sqrt(2)", "pi", "e", "i", "sin(1)", "x/2"])
def test_lo_que_no_es_exacto_no_se_inventa(source):
    """No exact rational means ``None`` — never a rounded impostor (§5.4)."""
    assert mx.exact_value(mx.parse(source)) is None


def test_la_raiz_cuadrada_se_convierte_en_raiz_exacta():
    """``x^(1/2)`` is a root node, so ``sqrt(x)^2`` is exactly ``x``."""
    e = mx.parse("x^(1/2)")
    assert isinstance(e, mx.Root) and e.degree == 2
    assert isinstance(mx.parse("2^0.5"), mx.Root)
    assert isinstance(mx.parse("x^(1/3)"), mx.Root)


def test_la_evaluacion_numerica_es_solo_para_comprobar():
    assert abs(mx.evaluate(mx.parse("sen(pi/2)")) - 1) < 1e-12
    assert mx.evaluate(mx.parse("1/0")) is None          # honest: undefined
    assert mx.evaluate(mx.parse("x")) is None            # a free variable
    assert mx.evaluate(mx.parse("i^2")).real == -1


# ===========================================================================
# calculus objects as first-class data (§5.1)
# ===========================================================================


def test_los_objetos_de_calculo_se_declaran():
    integral = mx.parse_calculus("integral(sin(x), x, 0, pi)")
    assert isinstance(integral, mx.Integral)
    assert integral.var == "x"
    limite = mx.parse_calculus("limite((x^2-1)/(x-1), x, 1)")
    assert isinstance(limite, mx.Limit) and limite.side == ""
    lateral = mx.parse_calculus("limite(sin(x)/x, x, 0, '+')")
    assert lateral.side == "+"
    assert isinstance(mx.parse_calculus("suma(k^2, k, 1, n)"), mx.Sum)
    assert isinstance(mx.parse_calculus("derivada(x^3, x)"), mx.Derivative)


def test_la_entrada_de_calculo_acepta_las_formas_de_la_spec():
    """§5.1 writes ``int(x^2*sin(x), x, 0, pi)``; that exact spelling works."""
    e = mx.parse_calculus("int(x^2*sin(x), x, 0, pi)")
    assert isinstance(e, mx.Integral) and e.var == "x"
    assert mx.pretty(e) == "∫[0,π] x²·sen(x) dx"
    # and it reaches the calculator through the contract
    r = C.calcular(C.Peticion("integrar", "int(x^2, x, 0, 1)"))
    assert r.exacto == "1/3"


def test_la_variable_de_integracion_no_es_libre():
    """``x`` in ``∫x²dx`` is bound: the result has no free variable."""
    assert mx.variables(mx.parse_calculus("integral(x^2, x)")) == set()
    assert mx.variables(mx.parse_calculus("integral(y*x^2, x, 0, a)")) == {"y", "a"}
    assert mx.variables(mx.parse_calculus("suma(k^2, k, 1, n)")) == {"n"}


def test_sustituir_no_toca_el_binding():
    e = mx.parse_calculus("integral(y*x^2, x)")
    assert mx.pretty(mx.substitute(e, "y", mx.parse("3"))) == "∫ 3·x² dx"
    assert mx.pretty(mx.substitute(e, "x", mx.parse("3"))) == "∫ y·x² dx"


def test_la_integral_no_se_evalua_como_si_fuera_un_valor():
    from academic_core.errors import UnsupportedError

    e = mx.parse_calculus("integral(x^2, x)")
    assert mx.exact_value(e) is None
    assert mx.evaluate(e) is None   # the engine solves it; it is not a number


# ===========================================================================
# equivalence: the corrector (§7)
# ===========================================================================


@pytest.mark.parametrize("a,b", [
    ("2x+2x", "4x"),
    ("1/2", "0.5"),
    ("x^2+1+2x", "(x+1)^2"),
    ("x*sin(x)", "sin(x)*x"),
    ("x*y+x*y", "2*x*y"),
    ("(x+1)^2", "1+2x+x^2"),
    ("3.14*x^2", "314*x^2/100"),
])
def test_las_formas_equivalentes_se_aceptan(a, b):
    iguales, metodo, _ = V.check_equivalence(mx.parse(a), mx.parse(b))
    assert iguales, f"{a} = {b} no se reconocieron ({metodo})"


@pytest.mark.parametrize("a,b", [
    ("cos(2x)", "2cos(x)"),
    ("x^2+1", "x^2+2"),
    ("sin(x)", "cos(x)"),
    ("x+1", "x-1"),
    ("x*y", "y*x+0.5"),
])
def test_las_expresiones_distintas_se_rechazan(a, b):
    iguales, _, _ = V.check_equivalence(mx.parse(a), mx.parse(b))
    assert not iguales, f"{a} y {b} se'oeilieron como iguales"


def test_la_forma_racional_cancela_y_conserva_el_dominio():
    """``(x²−1)/(x−1) = x+1``, but ``x = 1`` is removed: the hypothesis (§5.7)."""
    r = P.as_ratio(mx.parse("(x^2-1)/(x-1)"), "x")
    assert r is not None
    assert P.same_ratio(r, P.as_ratio(mx.parse("x+1"), "x"))
    assert r.excluded_values() == {1}  # printed by the UI, not lost


@pytest.mark.parametrize("cociente,resultado", [
    # (x^3 - 1)/(x - 1)  and friends: the constant term is NEGATIVE, which is the
    # whole point. Python's modulo on Fractions lands on the sign of the divisor,
    # so `Fraction(-1, 2) % 1` is `Fraction(1, 2)` and not zero — the old test
    # `coeff % a != 0` therefore declared these INEXACT and left them uncancelled.
    ("(x^3-1)/(x-1)", "x^2+x+1"),
    ("(x^3-8)/(x-2)", "x^2+2x+4"),
    ("(x^2-1/4)/(x-1/2)", "x+1/2"),
])
def test_una_division_exacta_no_se_toma_por_inexacta(cociente, resultado):
    """Cancelar es un acto, y un acto mal hecho cambia la respuesta.

    ``_divide_linear`` comprobaba la divisibilidad con ``coeff % a != 0``, que en
    ``Fraction`` no es la pregunta correcta: ``Fraction(-1, 2) % 1`` vale
    ``Fraction(1, 2)``. Toda división exacta con término constante negativo se
    declaraba inexacta y el cociente se quedaba sin simplificar.

    No se nota mirando el resultado — un cociente sin simplificar sigue siendo la
    misma función — y por eso hace falta una afirmación que lo compruebe. Y no
    solo para estos tres: ``as_ratio`` comparte esa función con el dominio y con la
    carta de signos, y una cancelación de más o de menos cambia los dos.
    """
    ra = P.as_ratio(mx.parse(cociente), "x")
    rb = P.as_ratio(mx.parse(resultado), "x")
    assert ra is not None and rb is not None
    assert P.same_ratio(ra, rb), (cociente, P.to_expr(ra.numerator),
                                  P.to_expr(ra.denominator))


@pytest.mark.parametrize("a,b,igual", [
    ("(x^2-1)/(x-1)", "x+1", True),
    ("(x^3-1)/(x-1)", "x^2+x+1", True),
    ("(x^3+1)/(x+1)", "x^2-x+1", True),
    ("(x+2)(x+3)/(x+3)", "x+2", True),
    ("x/(x+1)", "1-1/(x+1)", True),
    ("1/x+1/y", "(x+y)/(x*y)", True),
    ("(x^2-1)/(x-1)", "x+2", False),
    ("1/(2x)", "1/(3x)", False),
    ("(x+1)/(x-1)", "1+1/(x-1)", False),
])
def test_identidades_racionales(a, b, igual):
    ra, rb = P.as_ratio(mx.parse(a), "x"), P.as_ratio(mx.parse(b), "x")
    assert ra is not None and rb is not None
    assert P.same_ratio(ra, rb) is igual


def test_los_atomos_no_se_confunden_con_numeros():
    """``pi`` is an atom, so ``pi*x^2`` is *not* ``3.14*x^2``: they differ."""
    a, b = P.as_poly(mx.parse("x^2*pi")), P.as_poly(mx.parse("3.14*x^2"))
    assert a != b
    assert P.atoms_of(a) == {"pi"}


def test_la_comprobacion_numerica_es_determinista():
    """Same input, same verdict, every time (§11.2 criterion 7)."""
    puntos = V.sampled_points(["x"], count=12)
    assert puntos == V.sampled_points(["x"], count=12)
    a, b = mx.parse("sin(x)"), mx.parse("sin(x)")
    assert V.numeric_agreement(a, b)[0] is True


# ===========================================================================
# the trace (§5.2, §5.5b, §5.9)
# ===========================================================================


def test_todo_paso_de_metodo_lleva_su_por_que():
    """§5.5b: an unjustified method step must be refused, not accepted."""
    from academic_core.errors import ValidationError

    t = TR.Trace()
    t.metodo("prueba.metodo", "se elige este método", why="porque sí")
    with pytest.raises(ValidationError):
        t.metodo("prueba.sin_por_que", "sin explicación", why="  ")


def test_los_tres_niveles_de_detalle():
    t = TR.Trace()
    t.regla("p1", "regla de detalle resumen", detail=TR.RESUMEN)
    t.regla("p2", "regla de detalle paso")
    t.regla("p3", "regla de detalle detallado", detail=TR.DETALLADO,
            alternatives=(("otro método", "no concluía"),))
    # detail is cumulative: a coarse level shows fewer steps, never more
    assert len(t.at(TR.RESUMEN)) == 1
    assert len(t.at(TR.PASO)) == 2
    assert len(t.at(TR.DETALLADO)) == 3
    assert "no se eligió" in t.render(TR.DETALLADO)
    assert "no se eligió" not in t.render(TR.PASO)


def test_la_traza_se_serializa_y_se_vuelve_a_leer():
    t = TR.Trace()
    t.regla("derivada.producto", "regla del producto", before="a", after="b")
    t.metodo("metodo", "se aplica la regla del producto", why="porque es un producto")
    t.hipotesis("lhopital.continuidad", "f y g son continuas en a", "se cumple")
    texto = t.to_text()
    assert texto.startswith(f"mathlab.trace {TR.TRACE_VERSION}")
    vuelta = TR.Trace.from_text(texto)
    assert len(vuelta) == len(t)
    assert [s.rule for s in vuelta] == [s.rule for s in t]
    assert vuelta.hypotheses() == [("f y g son continuas en a", "se cumple")]


def test_una_traza_de_otra_version_se_rechaza():
    from academic_core.errors import ValidationError

    with pytest.raises(ValidationError):
        TR.Trace.from_text("mathlab.trace 9.0\n-\n")
    with pytest.raises(ValidationError):
        TR.Trace.from_text("no es una traza\n")


def test_las_hipotesis_se_registran_con_su_veredicto():
    t = TR.Trace()
    t.hipotesis("gauss.continuidad", "la función es C¹ en la región", "se cumple")
    t.hipotesis("stokes.orientacion", "la orientación es coherente", "no se cumple")
    assert t.hypotheses() == [
        ("la función es C¹ en la región", "se cumple"),
        ("la orientación es coherente", "no se cumple"),
    ]


# ===========================================================================
# derivatives and the seeded property (§5.3)
# ===========================================================================


@pytest.mark.parametrize("source,var,esperado", [
    ("x^3", "x", "3*x^2"),
    ("x^3+2x", "x", "3*x^2 + 2*1"),
    ("sin(x)", "x", "cos(x)"),
    ("e^x", "x", "exp(x)"),
    ("ln(x)", "x", "1/x"),
    ("1/x", "x", None),          # no golden form: the property below checks it
])
def test_derivadas_con_ejemplos_dorados(source, var, esperado):
    t = TR.Trace()
    derivada = D.differentiate(mx.parse(source), var, t)
    if esperado is None:
        assert derivada is not None
        return
    assert mx.text(derivada) == esperado


def test_la_derivada_de_una_expresion_sin_la_variable_es_cero():
    t = TR.Trace()
    assert D.differentiate(mx.parse("y^2"), "x", t) == mx.ZERO
    assert any("no aparece" in s.why for s in t.steps if s.why)


@pytest.mark.parametrize("source,var", [
    ("x^3+2x", "x"),
    ("sin(x)*x", "x"),
    ("e^x", "x"),
    ("1/x", "x"),
    ("ln(x+3)", "x"),
    ("sqrt(x)", "x"),
])
def test_la_derivada_coincide_con_el_cociente_incremental(source, var):
    """§5.3 row 1: compare with the limit of the incremental quotient."""
    f = mx.parse(source)
    d = D.differentiate(f, var, TR.Trace())
    sello = D.verify_derivative(f, d, var)
    assert sello.verdict != V.DISCREPANT, sello.detail


def test_gradiente_de_varias_variables():
    f = mx.parse("x^2 + y^2")
    g = D.gradient(f, TR.Trace())
    assert set(g) == {"x", "y"}
    for valor in g.values():
        sello = D.verify_derivative(f, valor, "x" if valor is g["x"] else "y")
        assert sello.verdict != V.DISCREPANT


def test_el_gradiente_se_verifica_de_forma_exacta():
    """A several-variable derivative still gets a *proof*, not only samples.

    The other variables are frozen at exact rationals, which turns each
    component into a one-variable identity that E0.1 can decide exactly.
    """
    r = C.calcular(C.Peticion("gradiente", "x^2 + y^2 + 2xy"))
    assert set(r.exacto) == {"x", "y"}
    assert r.sello.verdict == V.VERIFIED
    assert r.sello.method == "forma idéntica"


def test_una_derivada_incorrecta_es_detectada():
    """A wrong derivative must produce a ``discrepa`` seal, not a pass."""
    f = mx.parse("x^3")
    mala = mx.parse("2*x")          # plainly not the derivative
    sello = D.verify_derivative(f, mala, "x")
    assert sello.verdict == V.DISCREPANT
    assert sello.mark == "✘"


# ===========================================================================
# the contract of §5.9
# ===========================================================================


def test_el_contrato_esta_registrado_y_responde():
    import academic_core.domain.engineering.mathlab as ML

    assert ML.FASE == "ML-0"
    for operacion in ("derivar", "gradiente", "simplificar", "evaluar",
                      "igualdad", "integrar"):
        assert operacion in ML.operaciones()


@pytest.mark.parametrize("operacion,entrada,esperado", [
    ("derivar", "x^3+2x", "3·x² + 2"),
    ("derivar", "sin(x)", "cos(x)"),
    ("integrar", "x^3", "x⁴/4"),
    ("igualdad", {"a": "2x+2x", "b": "4x"}, True),
    ("igualdad", {"a": "cos(2x)", "b": "2cos(x)"}, False),
])
def test_las_calculadoras_dan_el_resultado_esperado(operacion, entrada, esperado):
    import academic_core.domain.engineering.mathlab as ML

    resultado = ML.calcular(ML.Peticion(operacion, entrada))
    assert resultado.exacto == esperado
    assert resultado.version == C.CONTRACT_VERSION


def test_el_pasillo_de_puntos_es_informativo():
    r = C.calcular(C.Peticion("derivar", "x^3+2x"))
    assert r.grafica is not None
    assert len(r.grafica.series) == 2          # function and derivative
    assert r.grafica.description               # §6: text alternative required
    assert "x³" in r.grafica.describe() or "x^3" in r.grafica.describe()


def test_una_calculadora_desconocida_se_rechaza_con_claridad():
    from academic_core.errors import UnsupportedError

    with pytest.raises(UnsupportedError) as exc:
        C.calcular(C.Peticion("no_existe", "x"))
    assert "no_existe" in str(exc.value)
    assert "derivar" in str(exc.value)   # it lists what is available


def test_una_convencion_se_declara_se_imprime_y_se_valida():
    c = C.ConvencionConjunto.of(db="20log10", valor_efectivo="V_ef")
    assert c.get("db") == "20log10"
    assert "db = 20log10" in c.as_lines()
    from academic_core.errors import ValidationError

    with pytest.raises(ValidationError):
        C.ConvencionConjunto.of(db="no_existe")
    with pytest.raises(ValidationError):
        C.ConvencionConjunto.of(convencion_inventada="x")


def test_la_convencion_aparece_en_el_resultado():
    r = C.calcular(C.Peticion("derivar", "x^2", convenciones=C.ConvencionConjunto.of(db="20log10")))
    assert r.convenciones.get("db") == "20log10"
    assert "convención: db = 20log10" in r.como_texto()
    assert r.traza.conventions()  # also recorded as a step


# ===========================================================================
# verification plug-ins (§5.9)
# ===========================================================================


def test_un_verificador_externo_que_discrepa_marca_el_sello():
    """A plug-in that disagrees must make the result *not* correct."""
    r = C.calcular(C.Peticion("derivar", "x^3+2x"))
    assert r.sello.verdict != V.DISCREPANT
    try:
        C.registrar_verificador("laboratorio_de_prueba",
                                lambda resultado: (False, "el motor dice otra cosa"))
        tras = C.calcular(C.Peticion("derivar", "x^3+2x"))
        assert tras.sello.verdict == V.DISCREPANT
        assert not tras.ok
    finally:
        C.withdraw_verificador("laboratorio_de_prueba")


def test_un_verificador_externo_que_coincide_refuerza_el_sello():
    try:
        C.registrar_verificador("otro_laboratorio",
                                lambda resultado: (True, "coincide en todos los puntos"))
        r = C.calcular(C.Peticion("derivar", "x^3+2x"))
        assert r.sello.verdict == V.VERIFIED
        assert "otro_laboratorio" in r.sello.detail
    finally:
        C.withdraw_verificador("otro_laboratorio")


def test_un_verificador_roto_no_rompe_el_calculo():
    """A plug-in that raises is a gap in the check, not a crash of the student."""
    def roto(_resultado):
        raise RuntimeError("el módulo externo no está instalado")

    try:
        C.registrar_verificador("roto", roto)
        r = C.calcular(C.Peticion("derivar", "x^3+2x"))
        assert r.exacto is not None
    finally:
        C.withdraw_verificador("roto")


def test_sin_verificadores_el_sello_no_se_inventa():
    """A numeric-only result stays numeric-only (§5.9: lower, never hide).

    ``sin(x)² + cos(x)² = 1`` has no common normal form, so the answer may only
    be reached numerically — and the seal must say so, not claim a proof.
    """
    r = C.calcular(C.Peticion("igualdad", {"a": "sin(x)^2 + cos(x)^2", "b": "1"}))
    assert r.exacto is True                 # the equivalence is decided
    assert r.sello.verdict == V.NUMERIC_ONLY  # but only numerically
    assert "sin prueba exacta" in r.sello.method


def test_una_identidad_sin_prueba_exacta_no_se_declara_verificada():
    """The reverse case: an exact match *is* ``verificado``."""
    r = C.calcular(C.Peticion("igualdad", {"a": "(x^2-1)/(x-1)", "b": "x+1"}))
    assert r.sello.verdict == V.VERIFIED
    assert "racional" in r.sello.method


def test_la_version_del_consumidor_se_comprueba():
    from academic_core.errors import ValidationError

    C.comprobar_version(C.CONTRACT_VERSION)     # the current one is fine
    with pytest.raises(ValidationError):
        C.comprobar_version("99.0")


def test_lo_que_el_motor_no_sabe_se_dice():
    """§5.4: «no sé darte una solución exacta» — and nothing is invented.

    For an *indefinite* integral with no elementary antiderivative there is also
    no number to offer: a primitive is a function, not a value. Only the
    definite case below can fall back to a bounded numeric answer.
    """
    r = C.calcular(C.Peticion("integrar", {"integrando": "e^(x^2)", "var": "x"}))
    assert r.exacto is None
    assert r.aproximado is None
    assert r.sello.verdict == V.NUMERIC_ONLY
    assert any("no sé darte una solución exacta" in a for a in r.avisos)
    assert any(s.rule == "integral.sin_exacta" for s in r.traza.steps)


def test_una_integral_sin_exacta_cae_a_simpson_con_error_acotado():
    """§5.4: the numeric fallback, with a real bound and a stated hypothesis.

    ``∫₀¹ e^(x²)`` has no elementary antiderivative, so Simpson is the second
    path of §5.3. The reference value is ``(√π/2)·erfi(1) = 1.4626517…``.
    """
    r = C.calcular(C.Peticion("integrar", {"integrando": "e^(x^2)", "var": "x",
                                           "desde": "0", "hasta": "1"}))
    assert r.exacto is None
    assert abs(r.aproximado.real - 1.462651747) < 1e-6
    assert r.error_acotado < 1e-6
    assert r.sello.verdict == V.NUMERIC_ONLY
    hipotesis = dict(r.hipotesis)
    assert any("continuo" in k for k in hipotesis)


def test_una_integral_definida_exacta_no_lleva_error():
    """With rational limits the value is exact, so no error bound is invented."""
    r = C.calcular(C.Peticion("integrar", {"integrando": "x^2", "var": "x",
                                           "desde": "0", "hasta": "1"}))
    assert r.exacto == "1/3"
    assert r.error_acotado is None
    assert r.sello.verdict == V.VERIFIED


def test_un_limite_no_racional_no_se_redondea_a_una_fraccion():
    """A float must never be dressed up as an exact fraction (§5.1)."""
    r = C.calcular(C.Peticion("integrar", {"integrando": "e^(x^2)", "var": "x",
                                           "desde": "0", "hasta": "pi"}))
    assert r.exacto is None                 # no closed form: a decimal stays one
    assert r.error_acotado is not None
    assert r.sello.verdict == V.NUMERIC_ONLY


def test_un_limite_no_racional_con_valor_exacto_lo_da_exacto():
    """∫_0^pi sen x is exactly 2: F(pi) - F(0) simplifies, it is not rounded."""
    r = C.calcular(C.Peticion("integrar", {"integrando": "sin(x)", "var": "x",
                                           "desde": "0", "hasta": "pi"}))
    assert r.exacto == "2"
    assert r.sello.method == "Barrow con valores exactos en los límites"
    assert any(s.rule == "integral.definida.exacta" for s in r.traza.steps)


def test_una_solicitud_ambigua_pide_claridad():
    from academic_core.errors import ValidationError

    with pytest.raises(ValidationError) as exc:
        C.calcular(C.Peticion("derivar", "x^2 + y^2"))
    assert "var" in str(exc.value)


def test_una_integral_con_un_solo_limite_se_rechaza():
    from academic_core.errors import ValidationError

    with pytest.raises(ValidationError):
        C.calcular(C.Peticion("integrar", {"integrando": "x^2", "var": "x",
                                          "desde": "0"}))


# ===========================================================================
# the architectural boundary (§1.2 principle 5, §12)
# ===========================================================================


def test_el_laboratorio_no_trae_qt_ni_backends():
    """Domain is stdlib only: no Qt, no filesystem, no network, no libraries."""
    from academic_core.domain.engineering.mathlab import calculators  # noqa: F401

    prohibido = {"PySide6", "sqlalchemy", "os", "pathlib", "sqlite3", "urllib",
                 "socket", "ftplib", "http", "subprocess", "random", "numpy",
                 "sympy", "scipy", "mpmath", "tkinter", "shutil"}
    Cupertino = []
    for f in ML.rglob("*.py"):
        arbol = ast.parse(f.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            modulos = []
            if isinstance(nodo, ast.Import):
                modulos = [a.name.split(".")[0] for a in nodo.names]
            elif isinstance(nodo, ast.ImportFrom):
                modulos = [(nodo.module or "").split(".")[0]]
            for m in modulos:
                if m in prohibido:
                    Cupertino.append(f"{f.name} importa {m}")
    assert not Cupertino, Cupertino


def test_el_laboratorio_no_depende_de_las_capas_superiores():
    """The math lab is a lower layer: it must not import the other labs.

    Checked with ``ast``, not with substrings: a docstring may *name* another
    laboratory (this one does, in §5.9), and prose is not a dependency.
    """
    from academic_core.domain.engineering.mathlab import calculators  # noqa: F401

    prohibido = ("dsp", "rf", "comms", "satcom", "mna", "ac", "digital", "lab",
                 "ui", "application", "infrastructure", "storage", "engines")
    problemas = []
    for f in ML.rglob("*.py"):
        arbol = ast.parse(f.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ImportFrom) and nodo.module:
                partes = nodo.module.split(".")
                if partes[0] == "academic_core" and len(partes) > 1:
                    cola = partes[2:] if partes[1] == "engineering" else partes[1:]
                    for malo in prohibido:
                        if malo in cola:
                            problemas.append(f"{f.name} importa {nodo.module}")
            elif isinstance(nodo, ast.Import):
                for a in nodo.names:
                    partes = a.name.split(".")
                    if partes[0] == "academic_core" and len(partes) > 1:
                        cola = partes[2:] if partes[1] == "engineering" else partes[1:]
                        for malo in prohibido:
                            if malo in cola:
                                problemas.append(f"{f.name} importa {a.name}")
    assert not problemas, problemas


def test_el_motor_e01_se_amplia_pero_no_se_reescribe():
    """§12: the existing engine is reused. The symbolic package must be intact."""
    simbolico = SRC / "domain" / "engineering" / "symbolic"
    for nombre in ("expr.py", "derive.py", "integrate.py", "normal.py",
                   "solve.py", "steps.py", "numeric.py"):
        assert (simbolico / nombre).exists(), nombre


def test_el_contrato_no_necesita_interfaz_para_funcionar():
    """A calculation must be possible with no Qt imported anywhere (§5.9)."""
    import academic_core.domain.engineering.mathlab as ML

    # the calculation itself pulls in nothing graphical
    antes = set(sys.modules)
    r = ML.calcular(ML.Peticion("derivar", "x^2"))
    assert r.exacto == "2·x"
    nuevos = set(sys.modules) - antes
    assert not [m for m in nuevos if m.startswith("PySide6")], nuevos


def test_el_paso_de_la_potencia_no_se_lee_como_otra_expresion():
    """«u^1/2» se lee (u^1)/2; el paso tiene que escribir u^(1/2) (2026-10-06)."""
    from academic_core.domain.engineering.symbolic import derive as Dv
    from academic_core.domain.engineering.symbolic import steps as St

    from fractions import Fraction as Fr

    from academic_core.domain.engineering.symbolic.expr import ONE, Add, Num, Pow, Sym

    log = St.StepLog()
    # built in the symbolic engine: the parser would turn ^(1/2) into sqrt
    Dv.derivative(Pow(Add(Pow(Sym("x"), Num(Fr(2))), ONE), Num(Fr(1, 3))), "x", log)
    potencias = [s for s in log.steps if "regla de la potencia" in s.rule
                 and s.before.startswith("u")]
    assert potencias
    assert all("^(" in s.before for s in potencias), [s.before for s in potencias]
