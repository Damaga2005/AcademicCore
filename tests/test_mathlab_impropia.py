# SPDX-License-Identifier: MIT
"""ML-2 (T10): integrales impropias — convergencia por comparación en el límite (también
con parámetro) y valor por Barrow con límites exactos; contrastado con SymPy."""
from __future__ import annotations

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import impropia as I
from academic_core.domain.engineering.mathlab import mvexpr as mx

sp = pytest.importorskip("sympy")


@pytest.mark.parametrize("f,a,b", [
    ("1/x^2", "1", "oo"), ("exp(-x)", "0", "oo"), ("1/sqrt(x)", "0", "1"), ("1/x", "1", "oo"),
    ("ln(x)", "0", "1"), ("1/(1+x^2)", "-oo", "oo"), ("x*exp(-x^2)", "0", "oo"),
    ("1/(x*ln(x))", "2", "oo"), ("1/x^2", "-1", "1"), ("1/sqrt(1-x^2)", "-1", "1"),
    ("x^2*exp(-x)", "0", "oo"), ("1/(x^2-1)", "2", "oo"), ("1/x^3", "0", "1"),
    ("exp(x)", "-oo", "0"), ("x/(1+x^2)", "0", "oo"),
])
def test_contra_sympy(f, a, b):
    x = sp.Symbol("x")
    lim = {"oo": sp.oo, "-oo": -sp.oo}
    ref = sp.integrate(sp.sympify(f.replace("^", "**").replace("ln", "log")), (x, lim.get(a, sp.sympify(a)),
                                                                             lim.get(b, sp.sympify(b))))
    r = I.convergencia(mx.parse(f), "x", a, b)
    if ref in (sp.oo, -sp.oo) or ref.has(sp.nan) or ref == sp.zoo:
        assert not r.converge
    else:
        assert r.converge
        if r.valor is not None:
            assert abs(mx.valor_real(r.valor, {}) - float(ref)) < 1e-10


@pytest.mark.parametrize("f,texto", [
    ("x^a/(1+x^2)", "converge si a ∈ (-1, 1)"),
    ("1/x^a", "converge si a ∈ (1, +∞)"),
    ("1/(x^a*(1+x))", "converge si a ∈ (0, 1)"),
    ("x^(a-1)*exp(-x)", "converge si a ∈ (0, +∞)"),
])
def test_con_parametro(f, texto):
    a = "1" if f == "1/x^a" else "0"
    assert I.con_parametro(mx.parse(f), "x", a, "oo", "a").texto() == texto


def test_calculadora_y_segundo_camino():
    r = ML.calcular(ML.Peticion("impropia", {"expr": "x*exp(-x^2)", "a": "0", "b": "oo"}))
    assert r.exacto == "converge y vale 1/2" and r.sello.verdict == "verificado"
    r = ML.calcular(ML.Peticion("impropia", {"expr": "1/(x*ln(x)^2)", "a": "2", "b": "oo"}))
    assert r.exacto == "converge y vale 1/ln(2)"
    assert r.sello.verdict == "solo_numerico"       # the log tail defeats the quadrature
    r = ML.calcular(ML.Peticion("impropia", {"expr": "1/x", "a": "1", "b": "oo"}))
    assert r.exacto.startswith("diverge")


def test_no_impropia_y_oscilante():
    with pytest.raises(Exception, match="NOT_IMPROPER"):
        I.convergencia(mx.parse("x^2"), "x", "0", "1")
    # Cerrado: sin(x)/x converge condicionalmente por Dirichlet (ML-3/ML-2 hueco 2)
    r = I.convergencia(mx.parse("sin(x)/x"), "x", "1", "oo", con_valor=False)
    assert r.converge and any("Dirichlet" in loc.razon for loc in r.locales)
    # Lo que sigue sin decidirse: oscilación no afín (sin primitiva acotada
    # demostrable), con su motivo
    with pytest.raises(Exception, match="Dirichlet|oscila|comportamiento"):
        I.convergencia(mx.parse("sin(x^2)/x"), "x", "1", "oo")
