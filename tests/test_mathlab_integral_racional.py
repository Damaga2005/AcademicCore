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


#: What it must NOT answer. Two different reasons, two different lists, because a
#: single list would make the two indistinguishable refusals look like one gap.
NIEGA_ARCTAN = [
    "1/(1+u^2)",                 # irreducible quadratic, NEGATIVE discriminant
    "1/(4*u^2+4*u+2)",           # same
    "1/(u^2+u+1)",               # same: 1 - 4 = -3
    "(2*u+1)/(u^2+1)",           # same, with a numerator that is not the derivative
    "1/(2+cos(x))",              # the substitution lands on `2/(3+u²)`: same
]
NIEGA_CUARTICO = [
    "1/(u^4+1)",                 # no rational root: a quartic left over
    "1/(u^4+u^2+1)",             # same
    "(u+1)/(u^2+1)^2",           # `(u²+1)²` is a quartic with no rational root
    "1/(cos(x)*cos(2*x))",       # the substitution lands on a quartic
]


@pytest.mark.parametrize("integrando", NIEGA_ARCTAN)
def test_una_cuadratica_irreducible_de_discriminante_negativo_no_se_integra(integrando):
    """The refusal is a boundary, not a gap in the method.

    `∫du/(u²+1)` is `arctg(u)`, and the symbolic language has no inverse tangent:
    it is not in the parser's function list, nor in the derivative table, nor in the
    numeric evaluator. mathlab differentiates and evaluates it without trouble, so
    an `Fn('atan', u)` would PRINT and could not be PARSED back — and a step trace
    the reader cannot retype is not a step trace.
    """
    var = "u" if "u" in integrando else "x"
    with pytest.raises(Exception):
        I.integrate(SE.parse(integrando), var, I.StepLog())


@pytest.mark.parametrize("integrando", NIEGA_CUARTICO)
def test_un_denominador_sin_raiz_racional_no_se_factorea(integrando):
    """Splitting a quartic into two quadratics is a system to solve, and this
    engine does not solve it. Doing it half way is how a rational integrator
    starts answering sometimes."""
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


def test_la_respuesta_se_puede_volver_a_leer():
    """What it prints, it can parse.

    The reason `atan` is not emitted even though mathlab could carry it: a printed
    answer the reader cannot type back is not an answer.
    """
    primitiva, _paso = I.integrate(SE.parse("1/(1+cos(x))"), "x", I.StepLog())
    texto = SE.text(primitiva)
    assert SE.parse(texto) is not None, texto