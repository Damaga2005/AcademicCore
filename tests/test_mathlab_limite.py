# SPDX-License-Identifier: MIT
"""ML-2 (T3): límites — término principal en la escala potencia·exp·ln, series de
Laurent exactas en las cancelaciones; contrastado con SymPy."""
from __future__ import annotations

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import limite as L
from academic_core.domain.engineering.mathlab import mvexpr as mx

sp = pytest.importorskip("sympy")

CASOS = [
    ("sin(x)/x", "0", ""), ("(1-cos(x))/x^2", "0", ""), ("(exp(x)-1-x)/x^2", "0", ""),
    ("x*ln(x)", "0", "+"), ("ln(x)/x", "oo", ""), ("x^2/exp(x)", "oo", ""),
    ("(2*x^2+1)/(x^2-3)", "oo", ""), ("sqrt(x^2+x)-x", "oo", ""), ("(1+1/x)^x", "oo", ""),
    ("(1+2/x)^(3*x)", "oo", ""), ("x^x", "0", "+"), ("1/x", "0", ""), ("1/x^2", "0", ""),
    ("1/x-1/sin(x)", "0", ""), ("(tan(x)-sin(x))/x^3", "0", ""), ("sin(x)/x", "oo", ""),
    ("x*sin(1/x)", "oo", ""), ("(x^3-8)/(x-2)", "2", ""), ("exp(-1/x)", "0", "+"),
    ("exp(-1/x)", "0", "-"), ("atan(x)", "-oo", ""), ("(cos(x))^(1/x^2)", "0", ""),
    ("(sqrt(1+x)-1)/x", "0", ""), ("x^(1/x)", "oo", ""), ("(3*x^2-x)/(5-x^2)", "-oo", ""),
    ("x-ln(x)", "oo", ""), ("exp(x)/x^10", "oo", ""), ("(x^2-1)/(x-1)^2", "1", ""),
    ("ln(cos(x))/x^2", "0", ""), ("sqrt(x^2+1)-sqrt(x^2-1)", "oo", ""), ("(x+1)/(x-1)", "1", ""),
    ("ln(x)^2/sqrt(x)", "oo", ""), ("(1+sin(x))^(1/x)", "0", ""), ("x^2*sin(1/x)", "0", ""),
    ("(1-1/x)^(x^2)", "oo", ""), ("2^x/x^3", "oo", ""), ("x*(exp(1/x)-1)", "oo", ""),
    ("(asin(x)-x)/x^3", "0", ""), ("(x-sin(x))/(x-tan(x))", "0", ""), ("sinh(x)/exp(x)", "oo", ""),
    ("ln(1+exp(x))/x", "oo", ""), ("(x^3+1)^(1/3)-x", "oo", ""), ("tan(x)", "pi/2", ""),
    ("(1+x)^(1/x)", "0", ""), ("x^sin(x)", "0", "+"), ("(ln(x)-1)/(x-exp(1))", "exp(1)", ""),
    ("abs(x)/x", "0", ""),
]


def _sympy(e, p, lado):
    x = sp.Symbol("x")
    sx = sp.sympify(e.replace("^", "**").replace("ln", "log"))
    sp_p = sp.oo if p == "oo" else -sp.oo if p == "-oo" else sp.sympify(p.replace("exp(1)", "E"))
    if lado or p in ("oo", "-oo"):
        return sp.limit(sx, x, sp_p, lado or "+" if p != "-oo" else "+")
    a, b = sp.limit(sx, x, sp_p, "+"), sp.limit(sx, x, sp_p, "-")
    return a if a == b else "NE"


@pytest.mark.parametrize("e,p,lado", CASOS)
def test_contra_sympy(e, p, lado):
    ref = _sympy(e, p, lado)
    r = L.limite(mx.parse(e), "x", p, lado)
    if ref == "NE":
        assert r.valor.startswith("no existe")
    elif ref == sp.oo:
        assert r.valor == "+∞"
    elif ref == -sp.oo:
        assert r.valor == "−∞"
    else:
        assert abs(complex(mx.evaluate(r.expr)) - complex(sp.N(ref))) < 1e-10, r.texto()


def test_oscilacion_sin_limite():
    assert L.limite(mx.parse("sin(x)"), "x", "oo").valor.startswith("no existe")
    assert L.limite(mx.parse("x*cos(x)"), "x", "oo").valor.startswith("no existe")


@pytest.mark.parametrize("e,p,tipo", [("sin(x)/x", "0", "0/0"), ("ln(x)/x", "oo", "∞/∞"),
                                      ("(1+1/x)^x", "oo", "1^∞"), ("x*ln(x)", "0", "0·∞")])
def test_nombra_la_indeterminacion(e, p, tipo):
    assert L.limite(mx.parse(e), "x", p, "+").indeterminacion == tipo


def test_calculadora_con_segundo_camino():
    r = ML.calcular(ML.Peticion("limite", {"expr": "(cos(x))^(1/x^2)", "punto": "0"}))
    assert r.exacto == "exp(-1/2)" and r.sello.verdict == "verificado"
    r = ML.calcular(ML.Peticion("limite", {"expr": "exp(x)/x^10", "punto": "oo"}))
    assert r.exacto == "+∞" and r.sello.verdict == "verificado"
    r = ML.calcular(ML.Peticion("limite", {"expr": "1/x", "punto": "0"}))
    assert r.exacto == "no existe: por la derecha +∞, por la izquierda −∞"
