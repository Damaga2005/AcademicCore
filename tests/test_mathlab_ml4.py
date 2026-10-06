# SPDX-License-Identifier: MIT
"""ML-4: series de potencias y métodos numéricos."""

from __future__ import annotations

import math
from fractions import Fraction

import pytest

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import numericos as N


def test_radio_e_intervalo():
    assert N.radio_convergencia("1/n").intervalo == "[-1, 1)"
    assert N.radio_convergencia("1/n^2", centro=1).intervalo == "[0, 2]"
    assert N.radio_convergencia("1/n!").radio == "oo"
    assert N.radio_convergencia("n!").radio == "0"
    assert N.radio_convergencia("2^n/n", centro=3).intervalo == "[5/2, 7/2)"
    assert N.radio_convergencia("1/(4^n*(n+1))", k=2).intervalo == "(-2, 2)"
    r = N.radio_convergencia("n^n/n!")                 # extremos por Raabe
    assert r.intervalo == "[-1/exp(1), 1/exp(1))"


def test_raices():
    r = N.todas_las_raices("cos(x)", "x", 0, 10)
    assert [mx.text(e) for e, _, _ in r.raices] == ["1/2*pi", "3/2*pi", "5/2*pi"]
    r = N.todas_las_raices("(x-1)^2*exp(x)", "x", -2, 3)
    assert len(r.raices) == 1 and r.raices[0][2] == 2
    r = N.todas_las_raices("-8*sin(x)-2/3", "x", -5, 5)     # el 0.0 exacto no se pierde
    assert len(r.raices) == 3
    assert N.todas_las_raices("x^3-2*x", "x", -3, 3).metodo == "Sturm (exacto)"
    assert abs(N.secante("x^2-2", "x", 1, 2).resultado - 2 ** 0.5) < 1e-12
    assert abs(N.regula_falsi("x^3-x-2", "x", 1, 2).resultado - 1.5213797068045676) < 1e-10


def test_lambert():
    assert N.lambert_w("e")[0] == mx.Num(Fraction(1))
    assert abs(N.lambert_w("1")[1] - 0.5671432904097838) < 1e-15
    assert abs(N.lambert_w("-1/4", -1)[1] + 2.153292364110349) < 1e-12
    sols = N.resolver_x_exp(1, -1, "1/5")
    assert len(sols) == 2
    with pytest.raises(Exception, match="−1/e"):
        N.lambert_w("-1")


def test_sistemas_lineales():
    L, U, perm, x = N.lu([[2, 1, 1], [4, -6, 0], [-2, 7, 2]], [5, -2, 9])
    assert x == [Fraction(1), Fraction(1), Fraction(2)]
    t = N.iterativo([[4, 1], [2, 5]], [1, 2], "gauss_seidel")
    assert abs(t.resultado[0] - 1 / 6) < 1e-9
    with pytest.raises(Exception, match="no converge"):
        N.iterativo([[1, 2], [3, 1]], [1, 2], "jacobi")


def test_interpolacion_y_ajustes():
    assert mx.text(N.newton_divididas([(0, 1), (1, 3), (2, 7), (3, 13)])) == "x + x^2 + 1"
    a = N.ajuste_polinomico([(0, 1), (1, 3), (2, 7), (3, 13), (4, 20)], 2)
    assert a.parametros == (Fraction(32, 35), Fraction(48, 35), Fraction(6, 7))
    g = N.gauss_newton("a*exp(b*x)", ["a", "b"], [(0, 2), (1, 5.4), (2, 14.8), (3, 40.2)],
                       [2, 1])
    lin = N.ajuste_linealizado([(0, 2), (1, 5.4), (2, 14.8), (3, 40.2)], "exponencial")
    assert g.ecm <= lin.ecm                   # Gauss-Newton mejora la linealización
    assert N.minimax_recta([(0, 0), (1, 1), (2, 4), (3, 9)]).parametros == (Fraction(-1),
                                                                           Fraction(3))


def test_edo_ordenes_y_estabilidad():
    for m, o in N.ORDENES.items():
        r = N.edo("-2*y+t", "0", "1", "0.1", 10, m, exacta="t/2-1/4+5/4*exp(-2*t)")
        assert abs(r.orden_observado - o) < 0.3, m
    r = N.edo("-100*y", "0", "1", "0.05", 20, "euler")
    assert "INESTABLE" in r.estabilidad
    r = N.edo("-100*y", "0", "1", "0.05", 20, "euler_implicito")
    assert "estable" in r.estabilidad and abs(r.y[-1]) < 1e-10 and r.notas


def test_calculadora_numericos():
    import academic_core.domain.engineering.mathlab as ML

    r = ML.calcular(ML.Peticion("numericos", {"calculo": "radio", "coef": "1/n"}))
    assert r.sello.verdict == "verificado" and "[-1, 1)" in r.exacto
    r = ML.calcular(ML.Peticion("numericos", {"calculo": "edo", "f": "-2*y+t", "y0": "1",
                                              "h": "0.1", "n": 10, "metodo": "rk4"}))
    assert r.sello.verdict == "solo_numerico" and "rk4" in r.exacto
