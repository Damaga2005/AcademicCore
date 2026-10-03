# SPDX-License-Identifier: MIT
"""Las identidades de un mismo argumento, y por que NO estan en la simplificacion."""

from __future__ import annotations

import math

import pytest

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import trig as T

#: ``(expresion, lo que queda)``. Las seis escrituras de ``tg = sen/cos`` mas el
#: coeficiente delante, que es como se escribe de verdad.
RAZONES = [
    ("sin(x)/tan(x)", "cos(x)"),
    ("cos(x)/sec(x)", "cos(x)^2"),
    ("tan(x)/sin(x)", "1/cos(x)"),
    ("sec(x)/cos(x)", "1/cos(x)^2"),
    ("sin(x)*cot(x)", "cos(x)"),
    ("cos(x)*csc(x)", "cot(x)"),
    ("tan(x)*csc(x)", "1/cos(x)"),
    ("2*sin(x)/tan(x) + 1", "2*cos(x) + 1"),
    ("sin(x)/tan(x) + cos(x)/sec(x)", "cos(x) + cos(x)^2"),
    ("sin(2*x)/tan(2*x)", "cos(2*x)"),
    ("3*cos(x)/sec(x)", "3*cos(x)^2"),
]


@pytest.mark.parametrize("expresion,esperado", RAZONES)
def test_la_identidad_se_escribe_como_el_libro(expresion, esperado):
    assert mx.text(T.razones(mx.parse(expresion)).expresion) == esperado


@pytest.mark.parametrize("expresion,esperado", RAZONES)
def test_la_identidad_es_cierta_donde_ambas_existen(expresion, esperado):
    """Where both sides exist, they are the same number. Sampled, not asserted.

    This is the check that caught a false identity: a rule derived «the product
    spelling is the quotient with the denominator inverted», and inverting ``sec``
    gives ``csc``, so ``cos·csc`` came out as ``cos^2``. It is
    ``cosec(x)·cos(x)``'s cotangent. Every test above passed on that version — they
    asserted the answer the code was giving, which was the wrong answer.
    """
    e = mx.parse(expresion)
    r = T.razones(e).expresion
    distintos = 0
    for j in range(1, 400):
        x = j * math.pi / 400 * 7
        antes, despues = mx.evaluate(e, {"x": x}), mx.evaluate(r, {"x": x})
        if antes is None or despues is None:
            continue
        if abs(antes) > 1e11 or abs(despues) > 1e11:
            continue          # a pole: the float sees a number, not an absence
        if abs(antes - despues) > 1e-9 * max(1.0, abs(antes)):
            distintos += 1
    assert distintos == 0, f"{expresion}: {distintos} puntos con valores distintos"


def test_no_toca_argumentos_distintos():
    """``sen(x)/tg(y)`` is not a relation between anything and anything."""
    assert mx.text(T.razones(mx.parse("sin(x)/tan(y)")).expresion) == "sin(x)/tan(y)"
    assert mx.text(T.razones(mx.parse("cos(x)/cos(x)")).expresion) == "cos(x)/cos(x)"


# ---------------------------------------------------------------------------
# por que es un objetivo aparte


@pytest.mark.parametrize("expresion", ["sin(x)/tan(x)", "cos(x)/sec(x)",
                                       "cos(x)*csc(x)"])
def test_simplificar_no_toca_estas_identidades(expresion):
    """The default simplification leaves them alone, on purpose.

    ``sen(x)/tg(x)`` and ``cos(x)`` agree wherever both exist and disagree
    everywhere else: the first does not exist at ``pi/2`` and the second does. The
    solvers read the domain of what ``simplify`` returns, so merging them there
    moves the domain — measured, it put 193 of 383 answers on the wrong side of an
    inequality. The rule exists, and it is not in the way.
    """
    assert mx.text(T.simplify(mx.parse(expresion))) == expresion


def test_el_paso_dice_donde_vale():
    """A trigonometric step that hides its hypothesis is a step that misleads."""
    paso = T.razones(mx.parse("sin(x)/tan(x)")).familias
    assert paso == ("razones_de_un_mismo_argumento",)
    descripcion = " ".join(
        d for nombre, d, _ in T._REGLAS_RAZONES if nombre == paso[0])
    assert "dominio del cociente" in descripcion, descripcion
