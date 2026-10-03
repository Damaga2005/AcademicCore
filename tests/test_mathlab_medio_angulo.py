# SPDX-License-Identifier: MIT
"""La familia del medio ángulo, entera: ocho de las diez formas no estaban."""

from __future__ import annotations

import math

import pytest

from academic_core.domain.engineering.mathlab import inequaciones as I
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import trig as T

#: ``(expresion, lo que queda, objetivo, conserva el dominio)``.
#
#: The ``conserva`` column is the whole point of this file. It is ``True`` for two
#: of the eight and was measured, not assumed: the domains were computed with
#: ``dominio()`` for both sides and compared as sets. The six that change the
#: domain are not in ``simplify`` — which the solvers read — because an expression
#: that GAINS a point in its domain hands the inequality solver a solution at a
#: point where the original cannot be evaluated.
FAMILIA = [
    ("sin(x)/(1 + cos(x))", "tan(x/2)", "simplify", True),
    ("sin(x)/(1 - cos(x))", "cot(x/2)", "simplify", True),
    ("(1 - cos(x))/sin(x)", "tan(x/2)", "medio_angulo", False),
    ("(1 + cos(x))/sin(x)", "cot(x/2)", "medio_angulo", False),
    ("cos(x)/(1 + sin(x))", "(1 - tan(x/2))/(1 + tan(x/2))", "racional", False),
    ("(1 - sin(x))/cos(x)", "(1 - tan(x/2))/(1 + tan(x/2))", "racional", False),
    ("1/(1 + sin(x))", "(1 - sin(x))/cos(x)^2", "racional", False),
    ("1/(1 - sin(x))", "(1 + sin(x))/cos(x)^2", "racional", False),
]


def _aplica(texto: str, objetivo: str) -> mx.Expr:
    e = mx.parse(texto)
    if objetivo == "simplify":
        return T.simplify(e)
    if objetivo == "medio_angulo":
        return T.medio_angulo(e).expresion
    return T.medio_angulo_racional(e).expresion


def _dominio(texto: str) -> str:
    return I.dominio(mx.parse(texto)).texto() or "(todo)"


@pytest.mark.parametrize("expresion,esperado,objetivo,conserva", FAMILIA)
def test_cada_forma_del_medio_angulo_se_escribe_como_el_libro(
        expresion, esperado, objetivo, conserva):
    assert mx.text(_aplica(expresion, objetivo)) == esperado


@pytest.mark.parametrize("expresion,esperado,objetivo,conserva", FAMILIA)
def test_el_valor_coincide_donde_los_dominios_se_solapan(
        expresion, esperado, objetivo, conserva):
    """Same number wherever both are defined — sampled, and saying where it is not.

    The sampling has to skip the documented holes. A pole seen by a float is a
    very large number rather than an absence, and one of them (``x = 3·pi/2``)
    evaluates to a plain ``0`` instead, so the skip is on the DOMAIN and not on a
    magnitude threshold. Sampling ``1/(1-sin x)`` without that skip reports one
    false discrepancy out of 499 points, and it is the hole the docstring names.
    """
    e, s = mx.parse(expresion), _aplica(expresion, objetivo)
    fuera = _agujeros(expresion, mx.text(s))
    distintos = 0
    # inside one period, where `dominio()` is right; both forms have period 2·pi
    for j in range(1, 500):
        x = j * 2 * math.pi / 500
        # a sample that lands on a hole is a sample of the hole, not of the
        # identity: the two forms disagree THERE by construction, which is what
        # `conserva=False` is saying
        if round(x / math.pi * 2) in fuera:
            continue
        antes, despues = mx.evaluate(e, {"x": x}), mx.evaluate(s, {"x": x})
        if antes is None or despues is None:
            continue
        if abs(antes) > 1e11 or abs(despues) > 1e11:
            continue
        if abs(antes - despues) > 1e-9 * max(1.0, abs(antes)):
            distintos += 1
    assert distintos == 0, f"{expresion}: {distintos} puntos con valores distintos"


def _agujeros(antes: str, despues: str) -> set[int]:
    """Half-multiples of ``pi``, in ONE period, excluded by the new domain only.

    Returned as ``k`` for the point ``k·pi/2``. The two forms disagree exactly at
    those points — that is what ``conserva=False`` means — and nowhere else.

    **Scoped to one period on purpose.** ``dominio()`` answers for the expression
    and publishes the holes it found, which are the holes of one period; asked
    about ``5·pi/2`` it says ``1/(1−sen x)`` exists there, and the evaluator says
    ``None``. That is a real and separate defect, it is not this test's business,
    and leaning on it would make this file wrong in a second way. Everything here
    stays inside ``[0, 2·pi]``, where ``dominio()`` is right.
    """
    dentro_antes = I.dominio(mx.parse(antes))
    dentro_despues = I.dominio(mx.parse(despues))
    from fractions import Fraction
    from academic_core.domain.engineering.mathlab import dominio as D
    return {k for k in range(0, 5)
            if dentro_antes.contiene(D.punto_pi(Fraction(k, 2)))
            and not dentro_despues.contiene(D.punto_pi(Fraction(k, 2)))}


@pytest.mark.parametrize("expresion,esperado,objetivo,conserva", FAMILIA)
def test_el_dominio_se_conserva_o_no_segun_medido(
        expresion, esperado, objetivo, conserva):
    """The claim in the table above, checked against ``dominio()`` and nothing else."""
    antes, despues = _dominio(expresion), _dominio(mx.text(_aplica(expresion, objetivo)))
    assert (despues == antes) is conserva, (
        f"{expresion}: el dominio pasa de {antes} a {despues} y la tabla dice "
        f"{'igual' if conserva else 'distinto'}")


# ---------------------------------------------------------------------------
# por que seis de las ocho no estan en simplify


@pytest.mark.parametrize("expresion", [
    "(1 - cos(x))/sin(x)", "(1 + cos(x))/sin(x)", "cos(x)/(1 + sin(x))",
    "(1 - sin(x))/cos(x)", "1/(1 + sin(x))", "1/(1 - sin(x))"])
def test_simplify_no_toca_lo_que_cambia_el_dominio(expresion):
    assert mx.text(T.simplify(mx.parse(expresion))) == expresion


def test_el_hueco_que_se_tapa_es_en_los_multiplos_de_pi():
    """Named, because §5.7 wants the hypothesis written and this is all of it.

    ``(1−cos x)/sen x`` is undefined at EVERY multiple of ``pi`` because the
    denominator vanishes; ``tg(x/2)`` only at the odd ones. The rewrite therefore
    invents a value at ``x = 0`` and at ``x = 2·pi``, where the original is 0/0.
    A domain that gains points is what turns into a false solution in an
    inequality, which is why this is not in ``simplify``.
    """
    assert _dominio("(1 - cos(x))/sin(x)") != _dominio("tan(x/2)")
    assert T.medio_angulo(mx.parse("(1 - cos(x))/sin(x)")).familias == (
        "medio_angulo_tapa_un_hueco",)


def test_el_paso_dice_que_tapa_un_hueco():
    paso = T.medio_angulo(mx.parse("(1 + cos(x))/sin(x)")).familias[0]
    descripcion = " ".join(
        d for nombre, d, _ in T._REGLAS_MEDIO_ANGULO if nombre == paso)
    assert "NO conservan el dominio" in descripcion, descripcion


def test_las_cuatro_caras_no_van_en_simplify_porque_cuestan_mas():
    """§5.5b: a family only moves in one direction, or the loop has no floor."""
    for expresion, _, objetivo, _ in FAMILIA:
        if objetivo != "racional":
            continue
        antes = T._coste(mx.parse(expresion))
        despues = T._coste(T.medio_angulo_racional(mx.parse(expresion)).expresion)
        assert despues > antes, (expresion, antes, despues)
