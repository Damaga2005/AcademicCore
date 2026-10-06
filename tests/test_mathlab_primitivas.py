# SPDX-License-Identifier: MIT
"""ML-2 (T8): fracciones simples explícitas y cambio de variable trigonométrico."""
from __future__ import annotations

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import primitivas as PR

sp = pytest.importorskip("sympy")


@pytest.mark.parametrize("f,descomposicion", [
    ("(x+3)/(x^2-3*x+2)", "(-4)/(x − 1) + 5/(x − 2)"),
    ("(2*x^3+x)/(x^2-1)", "2*x + (3/2)/(x + 1) + (3/2)/(x − 1)"),
    ("1/(x*(x-1)^2)", "1/x + (-1)/(x − 1) + 1/(x − 1)^2"),
    ("1/(x^3-1)", "(1/3)/(x − 1) + (-1/3*x - 2/3)/(x^2 + x + 1)"),
    ("1/(x^4+5*x^2+4)", "(1/3)/(x^2 + 1) + (-1/3)/(x^2 + 4)"),
    ("x/((x+1)*(x^2+4))", "(-1/5)/(x + 1) + (1/5*x + 4/5)/(x^2 + 4)"),
])
def test_fracciones_simples_contra_sympy_apart(f, descomposicion):
    from academic_core.domain.engineering.mathlab import poly as P
    from academic_core.domain.engineering.mathlab import raices as RZ

    e = mx.parse(f)
    r = P.as_ratio(e, "x")
    fr = PR.fracciones_simples(RZ._polinomio_de(P.to_expr(r.numerator), "x"),
                               RZ._polinomio_de(P.to_expr(r.denominator), "x"), "x")
    assert fr.descomposicion("x") == descomposicion
    x = sp.Symbol("x")
    ref = sp.apart(sp.sympify(f.replace("^", "**"), locals={"x": x}), x)
    texto = fr.descomposicion("x").replace("−", "-")
    mio = sp.sympify(texto.replace("^", "**"), locals={"x": x})
    assert sp.simplify(mio - ref) == 0
    assert PR.comprueba(fr.primitiva, e, "x")[0]


@pytest.mark.parametrize("f", ["sqrt(1-x^2)", "1/sqrt(4-x^2)", "sqrt(x^2+9)", "1/sqrt(x^2-1)",
                               "sqrt(x^2+2*x+5)", "3*sqrt(5+4*x-x^2)", "1/sqrt(2*x-x^2)"])
def test_sustitucion_trigonometrica_se_deriva_de_vuelta(f):
    e = mx.parse(f)
    assert PR.comprueba(PR.sustitucion_trigonometrica(e, "x"), e, "x")[0]


def test_integrar_usa_la_sustitucion_cuando_el_motor_general_no_sabe():
    r = ML.calcular(ML.Peticion("integrar", "sqrt(1-x^2)"))
    assert r.exacto is not None and r.sello.verdict == "verificado"
