# SPDX-License-Identifier: MIT
"""El integrador racional: fracciones parciales sobre Q, derivando para decidir.

Lo que se comprueba aquí no es el texto de la respuesta sino que **derivable da el
integrando**, en cuarenta y un puntos de la recta real. Un texto puede tener todos
los términos bien escritos y el signo de todos invertido — durante la escritura de
esto pasó, y el rechazo que produjo era el mismo que el de un caso que de verdad
no se sabe.

El otro lado de la prueba es igual de importante: lo que este integrador NO debe
contestar. Un integrador racional que responde «a veces» es peor que uno que no
responde, porque el fallo aparece donde ya no se está mirando.
"""

from __future__ import annotations

import pytest

from academic_core.domain.engineering.mathlab import derive_mv
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.symbolic import expr as SE
from academic_core.domain.engineering.symbolic import integrate as I


def _deriva_y_comprueba(integrando: str, var: str) -> str:
    """The antiderivative, checked the only way that decides."""
    primitiva, _paso = I.integrate(SE.parse(integrando), var, I.StepLog())
    diferencia = derive_mv.differentiate(mx.from_symbolic(primitiva), var)
    comprobados = 0
    for j in range(-20, 21):
        x = j * 0.23
        valor_derivada = mx.valor_real(diferencia, {var: x})
        valor_integrando = mx.valor_real(mx.parse(integrando), {var: x})
        if valor_derivada is None or valor_integrando is None:
            continue        # a pole: the integrand is not posed there
        comprobados += 1
        escala = max(1.0, abs(valor_integrando))
        assert abs(valor_derivada - valor_integrando) < 1e-8 * escala, (
            f"int {integrando} d{var} came out as {SE.text(primitiva)}; "
            f"its derivative at {var}={x} is {valor_derivada!r} and the "
            f"integrand is {valor_integrando!r}")
    assert comprobados >= 8, (integrando, comprobados)
    return SE.text(primitiva)


#: Polinomios, potencias negativas, factores lineales con y sin multiplicidad, y
#: cuadráticas irreducibles con discriminante positivo.
RACIONES = [
    "1/u",
    "u",
    "u^2",
    "u^3",
    "1/u^2",
    "1/u^3",
    "1/(u+1)",
    "1/(2*u+1)",
    "u/(1+u^2)",
    "1/(u^2-1)",
    "1/(1-3*u^2)",
    "1/(3*u^2-1)",
    "1/(u^2-1)^2",
    "1/(u+1)^2",
    "1/u^4",
    "(1+u^2)/(1-3*u^2)",
    "1/(2*u^3-3*u)",
    "(u^2+1)/(u*(u^2-1))",
    "u/(u^2-1)^2",
    "(3*u+2)/(u^2+3*u-4)",
    "u^2/(u+1)^2",
    "1/(4*u^2-1)",
]


@pytest.mark.parametrize("integrando", RACIONES)
def test_la_primitiva_deriva_al_integrando(integrando):
    """Soundness. The derivative, not the spelling."""
    assert _deriva_y_comprueba(integrando, "u")


#: The two that were T-18's open point, plus what the substitution opens around
#: them. `?1/(1+cos x)` is `tg(x/2)`: with `u = tg(x/2)`, `1 + cos x` is
#: `2/(1+u²)` and the Jacobian `2du/(1+u²)` cancels exactly what is left over.
ANGULO_MEDIO = [
    "1/(1+cos(x))",
    "1/(cos(x)+cos(2*x))",
    "1/(1+cos(x))^2",
    "1/(1+cos(2*x))",
    "1/(1-sin(x)^2)",
    "1/cos(x)",
    "cos(x)^3",
    "1/(cos(x)*cos(2*x))^0",
]


@pytest.mark.parametrize("integrando", ANGULO_MEDIO)
def test_la_sustitucion_del_angulo_medio_deriva_al_integrando(integrando):
    """Soundness on the trigonometric half, which is the half that is new."""
    assert _deriva_y_comprueba(integrando, "x")


#: What it must NOT answer, as of the third T-18 closure (2026-10-04).
#:
#: The negative-discriminant list and the repeated-quadratic list are both GONE,
#: and so is the quartic one: `∫du/(u⁴+1)` and `∫du/(u⁴+u²+1)` now integrate by
#: splitting the biquadratic into two quadratics over `Q(√(p²))`. What is left is
#: a set of CLASSES, each with its own reason, and a refusal without a written
#: reason is not a boundary — it is ignorance wearing one.
#:
#: |caso|por qué|
#: |---|---|
#: |`1/(u⁴+2)`|`√c` irracional: dos radiales en vez de uno, y el reparto de coeficientes ya no cabe en una expresión|
#: |`1/(3*u⁴+2)`|no mónico: la fórmula lee `a` y `c` y supone coeficiente principal 1|
#: |`1/(u⁴+1)²`|una potencia del biquadrático: es otro sistema, no este|
#: |`u/(u⁴+1)`|numerador impar sobre denominador par: el argumento de simetría no aplica|
NIEGA_FUERA_DE_CLASE = [
    "1/(u^4+2)",
    "1/(u^4-2)",        # c < 0: tiene raíces reales, y ese caso es de `_factores`
    "1/(3*u^4+2)",
    "1/(u^4+1)^2",
    "u/(u^4+1)",
]


@pytest.mark.parametrize("integrando", NIEGA_FUERA_DE_CLASE)
def test_un_cuadratico_fuera_de_clase_no_se_integra(integrando):
    """Cada uno se niega por SU motivo, y por eso la lista los nombra.

    El modo de fallar que este cambio tenía que evitar no es «integrar de más»
    sino **integrar de más sin decirlo**: un integrador racional que empieza a
    responder «a veces» es peor que uno que se niega.
    """
    var = "u" if "u" in integrando else "x"
    with pytest.raises(Exception):
        I.integrate(SE.parse(integrando), var, I.StepLog())


def test_una_funcion_no_es_racional_y_no_se_declara_racional():
    """The substitution rewrites what it rewrote and nothing else.

    `∫(u²+1)/(u(u²-1)) du` has no trigonometric function at all, so the half-angle
    is not its business. An earlier version fired anyway, applied the Jacobian to
    nothing, and answered `-2 log|tg(u/2)| + ...` — an answer about a different
    integrand, verified against nothing.
    """
    assert "tan" not in _deriva_y_comprueba("(u^2+1)/(u*(u^2-1))", "u")


#: Every integrand whose primitive must be re-readable. Parametrised rather than
#: looped inside one test so that a failure names the integrand that broke.
IMPRIMIBLE_Y_RELEGIBLE = [
    "1/(1+cos(x))",     # the substitution, unchanged
    "1/(1+u^2)",        # closed 2026-10-04: comes out with atan
    "sinh(u)",
    "sech(u)",          # comes out with atan(sinh u)
    "1/cos(u)",
    "tan(u)^3",         # came out with a logarithm spelled `ln` until 2026-10-04
    "csch(u)",
    "1/(u^2+1)^2",      # the squarefree decomposition, and the shape that exposed a
                        # silent `1` where a reciprocal belonged
    "(u+1)/(u^2+1)^2",
    "1/(u^4+1)",         # the biquadratic split; its first answer was CORRECT and
                        # 318 characters long, which is not an answer
    "1/(cos(x)*cos(2*x))",
]


@pytest.mark.parametrize("integrando", IMPRIMIBLE_Y_RELEGIBLE)
def test_la_respuesta_se_puede_volver_a_leer(integrando):
    """What it prints, it can parse.

    This is the reason the negative-discriminant cases used to refuse, stated as
    the invariant it actually protects rather than as the hole it was: an answer
    the reader cannot type back is not an answer. It runs over the whole family
    now, because the failure it guards against was never specific to `atan` —
    `∫tan³(u)du` was printing a logarithm spelled `ln`, a name this language has
    never had, for as long as nobody wrote a test that typed the answer back in.
    """
    var = "u" if "u" in integrando else "x"
    primitiva, _paso = I.integrate(SE.parse(integrando), var, I.StepLog())
    texto = SE.text(primitiva)
    assert SE.parse(texto) is not None, (integrando, texto)


def test_el_nombre_del_logaritmo_es_uno_y_es_el_del_lenguaje():
    """`log`, never `ln`.

    A regression, not a style note. The reduction rule for odd powers of `tan`
    emitted `Fn("ln", 1/cos(u))` while the table emitted `Fn("log", abs(cos(u)))`
    for the first power — two spellings of one function inside one module, so the
    table's answer could be read back and the reduction's could not. This asserts
    the one invariant that catches it: everything this module prints parses.
    """
    for potencia in range(1, 7):
        integrando = "tan(u)" if potencia == 1 else f"tan(u)^{potencia}"
        primitiva, _paso = I.integrate(SE.parse(integrando), "u", I.StepLog())
        texto = SE.text(primitiva)
        assert "ln(" not in texto, (integrando, texto)
        assert SE.parse(texto) is not None, (integrando, texto)