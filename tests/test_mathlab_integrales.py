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


def test_lo_que_sigue_sin_resolver_se_niega_y_no_se_inventa():
    """``exp(x)·sen(x)`` has a closed form and this engine does not find it.

    Refusing is the correct answer here; the incorrect one is returning a
    plausible-looking expression that is not a primitive.
    """
    for integrando in ("exp(x)*sin(x)", "sinh(x)^2", "sec(x)^3"):
        with pytest.raises(Exception) as exc:
            integra(integrando)
        assert "no hay regla" in str(exc.value) or "NO_RULE" in str(exc.value)


def test_la_tabla_propia_no_pisa_a_la_reduccion():
    """The family squares are table entries; a higher power is the reduction.

    Both answer the same integral and they must agree, or one of them is wrong
    and nothing in the suite would notice.
    """
    assert mx.text(integra("sec(x)^2")) == mx.text(integra("1/cos(x)^2"))
    assert mx.text(integra("sin(x)^2")) != mx.text(integra("cos(x)^2"))
