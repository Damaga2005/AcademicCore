# SPDX-License-Identifier: MIT
"""ML-2 (T11): series numéricas, de potencias y sumas — contrastadas con SymPy."""
from __future__ import annotations

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import series_numericas as S

sp = pytest.importorskip("sympy")


@pytest.mark.parametrize("t,esperado", [
    ("1/n^2", "converge absolutamente"), ("1/n", "diverge"),
    ("1/(n*ln(n)^2)", "converge absolutamente"), ("1/(n*ln(n))", "diverge"),
    ("(-1)^n/n", "converge condicionalmente"), ("(-1)^(n+1)/sqrt(n)", "converge condicionalmente"),
    ("n/2^n", "converge absolutamente"), ("2^n/n^3", "diverge"), ("n^2/(n^3+1)", "diverge"),
    ("(n+1)/(2*n+3)", "diverge"), ("1/n!", "converge absolutamente"), ("n!/n^2", "diverge"),
    ("2^n/n!", "converge absolutamente"), ("(n!)^2/(2*n)!", "converge absolutamente"),
    ("cos(pi*n)/n", "converge condicionalmente"), ("sin(n)/n^2", "converge absolutamente"),
    ("(n!)/(n+2)!", "converge absolutamente"), ("(-1)^(2*n)/n", "diverge"),
    ("(1+1/n)^n", "diverge"), ("(-3)^n/(n*3^n)", "converge condicionalmente"),
])
def test_convergencia(t, esperado):
    assert S.convergencia(S.leer(t), 2).tipo == esperado


def test_convergencia_contra_sympy():
    n = sp.Symbol("n", integer=True, positive=True)
    for t in ["1/n^2", "1/n", "n/2^n", "n^2/(n^3+1)", "1/(n^2+3*n)", "sqrt(n)/(n^2+1)",
              "3^n/(n^2*2^n)", "1/n^(3/2)"]:
        ref = sp.Sum(sp.sympify(t.replace("^", "**").replace("ln", "log"), locals={"n": n}),
                     (n, 1, sp.oo)).is_convergent()
        assert S.convergencia(S.leer(t)).converge == bool(ref), t


@pytest.mark.parametrize("t,texto", [
    ("x^n/n", "R = 1; converge en [-1, 1)"),
    ("x^n/n^2", "R = 1; converge en [-1, 1]"),
    ("x^n/(n*2^n)", "R = 2; converge en [-2, 2)"),
    ("(-1)^n*(x-2)^n/(n*3^n)", "R = 3; converge en (-1, 5]"),
    ("x^n/n!", "R = ∞: converge en todo ℝ"),
    ("n!*x^n", "R = 0: solo converge en x = 0"),
    ("(-1)^n*x^(2*n)/(2*n+1)", "R = 1; converge en [-1, 1]"),
])
def test_potencias(t, texto):
    assert S.potencias(S.leer(t)).texto().startswith(texto)


@pytest.mark.parametrize("t,n0,valor", [("1/(n*(n+1))", 1, "1"), ("1/(n^2-1)", 2, "3/4"),
                                        ("3/2^n", 0, "6"), ("(2/3)^n", 1, "2"),
                                        ("1/(n*(n+2))", 1, "3/4"), ("(-1)^n/3^n", 0, "3/4"),
                                        ("1/((n+1)*(n+2)*(n+3))", 0, "1/4")])
def test_sumas_y_su_segundo_camino(t, n0, valor):
    r = ML.calcular(ML.Peticion("serie", {"calculo": "suma", "termino": t, "n0": n0}))
    assert r.exacto == valor and r.sello.verdict == "verificado"
