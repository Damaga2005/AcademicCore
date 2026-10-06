# SPDX-License-Identifier: MIT
"""ML-2: Taylor con resto de Lagrange, TFC, inversa, trozos con parámetros, teoremas,
Riemann y métodos numéricos."""
from __future__ import annotations

import math

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import calculo_extra as X
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import taylor_lagrange as T

P = mx.parse
sp = pytest.importorskip("sympy")


@pytest.mark.parametrize("f,a,n,x0", [("exp(x)", "0", 3, "1/2"), ("sin(x)", "0", 5, "1"),
                                      ("ln(1+x)", "0", 3, "1/10"), ("sqrt(x)", "4", 2, "9/2"),
                                      ("cos(x)", "0", 4, "1/2"), ("atan(x)", "0", 3, "1/5")])
def test_taylor_polinomio_contra_sympy_y_cota_valida(f, a, n, x0):
    x = sp.Symbol("x")
    sf = sp.sympify(f.replace("^", "**").replace("ln", "log"), locals={"x": x})
    ref = sp.series(sf, x, sp.sympify(a), n + 1).removeO()
    r = T.aproximar(P(f), "x", P(a), n, x0=P(x0))
    for xv in (0.1, 0.37, 0.9):
        assert abs(mx.valor_real(r.P, {"x": float(a) + xv}) - float(ref.subs(x, float(a) + xv))) < 1e-12
    assert T.error_real(P(f), "x", r, P(x0)) <= mx.valor_real(r.cota, {})


def test_orden_minimo():
    r = T.orden_minimo(P("exp(x)"), "x", P("0"), P("1"), 1e-6)
    assert r.n == 9      # e/10! ≈ 7.5e-7 < 1e-6 and e/9! ≈ 7.5e-6 is not


def test_tfc_contra_derivada_numerica():
    d = X.tfc(P("exp(-t^2)"), "t", P("0"), P("x^2"), "x")
    assert X.tfc_comprobacion(P("exp(-t^2)"), "t", P("0"), P("x^2"), "x", d, 0.7)[0]
    d = X.tfc(P("sin(t)/t"), "t", P("x"), P("2*x"), "x")
    assert X.tfc_comprobacion(P("sin(t)/t"), "t", P("x"), P("2*x"), "x", d, 1.3)[0]


def test_inversa():
    assert X.derivada_inversa(P("x^3+x"), "x", P("2")).texto().endswith("= 1/4")
    assert X.derivada_inversa(P("x+exp(x)"), "x", P("1")).texto().endswith("= 1/2")
    with pytest.raises(Exception, match="NOT_INJECTIVE"):
        X.derivada_inversa(P("x^2"), "x", P("4"))


def test_a_trozos():
    r = ML.calcular(ML.Peticion("a_trozos", {"izquierda": "a*x+b", "derecha": "x^2", "punto": "1",
                                             "parametros": ["a", "b"], "derivable": True}))
    assert r.exacto.endswith("{a = 2, b = -1}") and r.sello.verdict == "verificado"
    r = ML.calcular(ML.Peticion("a_trozos", {"izquierda": "alfa*x^2", "derecha": "ln(x)+1",
                                             "punto": "1", "parametros": ["alfa"]}))
    assert r.exacto.endswith("{alfa = 1}")


@pytest.mark.parametrize("teorema,f,a,b,trozo", [
    ("rolle", "x^2-4*x", "0", "4", "c = 2"),
    ("rolle", "abs(x)", "-1", "1", "f no es derivable en x = 0"),
    ("valor_medio", "x^3", "0", "2", "c = 2/3*sqrt(3)"),
    ("bolzano", "x^3+x-1", "0", "1", "c = ≈ 0.682327803828"),
    ("bolzano", "1/x", "-1", "1", "No se puede aplicar"),
])
def test_teoremas(teorema, f, a, b, trozo):
    r = ML.calcular(ML.Peticion("teorema", {"teorema": teorema, "expr": f, "a": a, "b": b}))
    assert trozo in r.exacto


def test_riemann_y_cuadraturas():
    r = X.riemann(P("x^2"), "x", P("0"), P("1"), 10)
    assert r.sumas["izquierda"] < 1 / 3 < r.sumas["derecha"]
    exacto = math.sqrt(math.pi) / 2 * math.erf(1)
    for metodo in ("trapecios", "simpson"):
        q = X.cuadratura(P("exp(-x^2)"), "x", P("0"), P("1"), 10, metodo)
        assert abs(q.resultado - exacto) <= q.cota


def test_metodos_de_raices():
    assert abs(X.biseccion(P("x^2-2"), "x", 1, 2, 1e-8).resultado - math.sqrt(2)) < 1e-8
    assert abs(X.newton(P("x^2-2"), "x", 1).resultado - math.sqrt(2)) < 1e-14
    pf = X.punto_fijo(P("cos(x)"), "x", 0.5, 0, 1)
    assert abs(pf.resultado - 0.7390851332151607) <= pf.cota + 1e-15
    with pytest.raises(Exception, match="HYPOTHESIS"):
        X.punto_fijo(P("2*x"), "x", 0.5, 0, 1)
    assert mx.text(X.lagrange([(0, 1), (1, 3), (2, 7)])) == "x^2 + x + 1"
