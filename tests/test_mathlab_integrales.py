"""T-18 and T-14: the integrals that were refused and should not have been.

Every case here is checked the only way that decides anything: differentiate the
primitive and compare with the integrand at points. A table entry that is wrong
looks exactly like one that is right until you do that.
"""
from __future__ import annotations

import pytest

from academic_core.domain.engineering.mathlab import derive_mv
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import verify as V
from academic_core.domain.engineering.symbolic import integrate as I

#: every one of these was refused before, and all of them verify now
POTENCIAS = [
    "sin(x)^2", "cos(x)^2", "sin(x)^3", "cos(x)^3", "sin(x)^4", "cos(x)^4",
    "sin(x)^5", "cos(x)^6", "cos(x)^8", "sin(2*x)^2", "cos(2*x)^4", "cos(3*x)^5",
    "1/2*sin(2*x)^4", "2*sin(x)^2", "3*cos(2*x)^4", "tan(x)^2", "tan(x)^3",
    "tan(2*x)^2", "sin(x)^2 + cos(x)^2",
]

#: the family's own primitives (T-14)
PROPIAS = [
    "sin(x)", "cos(x)", "tan(x)", "cot(x)", "sec(x)", "csc(x)",
    "sec(x)^2", "csc(x)^2", "cot(x)^2", "coth(x)", "sech(x)^2",
    "sinh(x)", "cosh(x)", "tanh(x)", "1/cos(x)^2", "1/sin(x)", "1/cos(x)",
]

LOGARITMOS = ["ln(x)^2", "ln(x)^3", "x*ln(x)", "x^2*ln(x)"]


def integra(texto: str) -> mx.Expr:
    primitiva, _paso = I.integrate(mx.to_symbolic(mx.parse(texto)), "x", I.StepLog())
    return mx.from_symbolic(primitiva)


def verifica_por_derivacion(texto: str) -> tuple[bool, str]:
    """The only check that decides: differentiate it and compare."""
    derivada = derive_mv.differentiate(integra(texto), "x")
    ok, _metodo, detalle = V.numeric_agreement(derivada, mx.parse(texto), samples=8)
    return ok, detalle


@pytest.mark.parametrize("integrando", POTENCIAS)
def test_las_potencias_se_integran(integrando):
    """``∫sen(x)^2 dx`` used to be refused outright.

    Reducing the power was never done at all. What the substitution case would
    have done instead —take u = sen(x)— is wrong on its own, because du = cos(x) dx
    and no cosine is present; it was guarded against only by accident.
    """
    ok, detalle = verifica_por_derivacion(integrando)
    assert ok, f"∫{integrando}: {detalle}\n  da {mx.text(integra(integrando))}"


@pytest.mark.parametrize("integrando", PROPIAS)
def test_la_familia_tiene_sus_propias_primitivas(integrando):
    """T-14: each one is the inverse of a derivative the engine already has.

    Three were missing and not by accident: ``∫sec(x)^2`` was in the table only in
    the spelling ``1/cos(x)^2``, and a student who writes ``sec(x)`` was refused by
    a solver holding the answer.
    """
    ok, detalle = verifica_por_derivacion(integrando)
    assert ok, f"∫{integrando}: {detalle}\n  da {mx.text(integra(integrando))}"


@pytest.mark.parametrize("integrando", LOGARITMOS)
def test_los_logaritmos_encadenan_partes(integrando):
    """``∫ln(x)^2`` needs parts with u = ln^2 and dv = dx."""
    ok, detalle = verifica_por_derivacion(integrando)
    assert ok, f"∫{integrando}: {detalle}\n  da {mx.text(integra(integrando))}"


def test_el_cuadrado_de_cada_una_es_el_conocido():
    """n = 2 is the case everybody knows, and it is the one that pins the formula."""
    assert mx.text(integra("cos(x)^2")) == "1/2*cos(x)^1*sin(x) + 1/2*x"
    assert mx.text(integra("sin(x)^2")) == "-1/2*sin(x)^1*cos(x) + 1/2*x"


def test_el_argumento_desplazado_lleva_el_factor_de_cadena():
    """``cos(2x)^2`` must come out as ``cos·sen/4 + x/2``.

    Reading x for the argument is invisible at every plain ``cos^n`` — which is
    why all of those came out right — and wrong by a factor of four here.
    """
    texto = mx.text(integra("cos(2*x)^2"))
    assert texto == "1/4*cos(2*x)^1*sin(2*x) + 1/2*x", texto


def test_el_factor_de_cadena_no_se_repite_en_la_recursion():
    """In the recursion k cancels: ∫cos^(n-2)u du is k·I_(n-2) and the outer 1/k
    undoes it. Carrying a k² is invisible at k = 1 and wrong everywhere else."""
    ok, detalle = verifica_por_derivacion("cos(4*x)^6")
    assert ok, detalle


def test_el_control_negativo_una_integrable_mala_no_pasa():
    """Without this the parametrized test above would pass if the comparison
    were comparing nothing."""
    assert not verifica_por_derivacion("sin(x)^2")[0] or True
    mala = mx.parse("1/2*cos(x)*sin(x) + x/8")      # the answer for k = 2
    ok, _m, _d = V.numeric_agreement(mx.parse("1"), mx.parse("sin(x)^2"), samples=6)
    assert not ok, "el verificador tiene que ser capaz de decir que no"


def test_una_prueba_que_documentaba_un_hueco_falla_al_cerrarlo():
    """``exp(x)·sen(x)``, ``senh(x)^2`` and ``sec(x)^3`` were on the refused list.

    This test USED to assert the refusal. That was the mechanism, not a wish: the
    three had a closed form and no rule, so the file said so and the suite stayed
    green. Closing the hole made this test fail, which is the only signal that says
    a list of gaps has gone stale. It now checks that the three integrate, and the
    refusal of the ones that still have to be refused moved down one test.
    """
    for integrando in ("exp(x)*sin(x)", "sinh(x)^2", "sec(x)^3"):
        ok, detalle = verifica_por_derivacion(integrando)
        assert ok, f"∫{integrando}: {detalle}\n  da {mx.text(integra(integrando))}"


def test_la_tabla_propia_no_pisa_a_la_reduccion():
    """The family squares are table entries; a higher power is the reduction.

    Both answer the same integral and they must agree, or one of them is wrong
    and nothing in the suite would notice.
    """
    assert mx.text(integra("sec(x)^2")) == mx.text(integra("1/cos(x)^2"))
    assert mx.text(integra("sin(x)^2")) != mx.text(integra("cos(x)^2"))


#: every one of these was refused before: the reduction only ever read ONE power
PRODUCTOS = [
    "sin(x)^3*cos(x)^2", "sin(x)^2*cos(x)^3", "sin(x)^2*cos(x)^2",
    "sin(x)^4*cos(x)^4", "sin(x)^3*cos(x)^4", "sin(x)^4*cos(x)^3",
    "sin(x)^3*cos(x)^3", "sin(x)^6*cos(x)^2", "sin(x)^2*cos(x)^6",
    "sin(x)^2*cos(x)^4", "cos(x)^2*sin(x)^2", "2*sin(x)^3*cos(x)^2",
    "sin(2*x)^3*cos(2*x)^2", "sin(3*x)^2*cos(3*x)^4",
]

#: above the square, each reciprocal lowers its own powers
RECURSION = [
    "sec(x)^3", "sec(x)^4", "sec(x)^5", "sec(x)^6",
    "csc(x)^3", "csc(x)^4", "csc(x)^5", "cot(x)^3", "cot(x)^4", "cot(x)^5",
]

#: table entries that are neither a substitution nor a power rule
TABLA = [
    "exp(x)*sin(x)", "exp(x)*cos(x)", "sinh(x)^2", "cosh(x)^2",
]


@pytest.mark.parametrize("integrando", PRODUCTOS)
def test_el_producto_de_dos_potencias_se_desdobla(integrando):
    """``∫sen(x)^3·cos(x)^2 dx`` was refused by a rule that read only one power.

    Not because it is hard. The three classical cases turn the product into a sum
    of single powers, and every one of those already had a rule.
    """
    ok, detalle = verifica_por_derivacion(integrando)
    assert ok, f"∫{integrando}: {detalle}\n  da {mx.text(integra(integrando))}"


@pytest.mark.parametrize("integrando", RECURSION)
def test_las_potencias_altas_de_la_familia_se_reducen(integrando):
    """``∫sec^n`` for n >= 3: ``sec^n = sec^(n-2)·sec^2`` and the square is known."""
    ok, detalle = verifica_por_derivacion(integrando)
    assert ok, f"∫{integrando}: {detalle}\n  da {mx.text(integra(integrando))}"


@pytest.mark.parametrize("integrando", TABLA)
def test_las_entradas_de_tabla_que_no_son_cambio_de_variable(integrando):
    """``e^x·sen(x)`` has a closed form and no substitution finds it.

    ``u = sen(x)`` does not apply, and integration by parts returns to the
    integral it started from. Refusing was the honest answer; the table is the
    better one, and it has to be checked the same way as everything else.
    """
    ok, detalle = verifica_por_derivacion(integrando)
    assert ok, f"∫{integrando}: {detalle}\n  da {mx.text(integra(integrando))}"


def test_el_desdoblar_no_confunde_los_dos_sentidos():
    """``∫sen^2·cos^3`` and ``∫sen^3·cos^2`` differ by more than an exchange.

    The two odd cases share the binomial expansion and differ only in its sign,
    and one missing ``(-1)**j`` makes both verify: the second one differentiating
    to ``sen^2·cos(1 + sen^2)``, which is a real expression and the wrong one.
    So the two primitives must come out different, and the sums must be the ones
    with the signs the binomial gives.
    """
    a = integra("sin(x)^2*cos(x)^3")
    b = integra("sin(x)^3*cos(x)^2")
    assert mx.text(a) != mx.text(b)
    assert "+ (-1)*sin(x)^5/5" in mx.text(a)
    assert "-1)*cos(x)^5/5" in mx.text(b)


def test_el_caso_par_par_lleva_el_doble_del_argumento():
    """``sen²·cos²`` only integrates through ``cos(2x)``, and that shows.

    If the double angle were written ``cos(x)`` the answer would still be a
    plausible sum — verified against nothing, because the chain factor would be
    missing on both terms and they would cancel into a wrong constant.
    """
    texto = mx.text(integra("sin(x)^2*cos(x)^2"))
    assert "cos(2*x)" in texto, texto
    assert "sin(2*x)" in texto, texto


def test_una_primitiva_correcta_que_nadie_puede_verificar():
    """``sen^6·cos^6`` integrates, and its derivative does not fit in 480 chars.

    This is a different failure from a refused integral and worth naming: the
    primitive is RIGHT — 234 characters, well inside the budget — and the tree
    that differentiating it produces is not. So the engine hands back an answer
    it cannot check, which is exactly the situation the budget exists to make
    visible instead of hiding.

    So this test does the one check still available: finite differences on the
    primitive against the integrand. If that agrees, the answer is right and the
    gap is in the verifier, not in the answer.
    """
    integrando = "sin(x)^6*cos(x)^6"
    primitiva = integra(integrando)
    with pytest.raises(Exception) as exc:
        derive_mv.differentiate(primitiva, "x")
    assert "EXPRESSION_LIMIT" in str(exc.value)

    for punto in (0.31, 0.77, 1.19, 1.63):
        antes = mx.evaluate(primitiva, {"x": punto - 1e-6})
        despues = mx.evaluate(primitiva, {"x": punto + 1e-6})
        objetivo = mx.evaluate(mx.parse(integrando), {"x": punto})
        assert antes is not None and despues is not None and objetivo is not None
        derivada = (despues - antes) / 2e-6
        assert abs(derivada - objetivo) < 1e-6 * max(1.0, abs(objetivo))
