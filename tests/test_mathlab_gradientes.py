# SPDX-License-Identifier: MIT
"""ML-12: verificador numérico de gradientes (diferencias centrales + Richardson)."""
from __future__ import annotations

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import derive_mv as D
from academic_core.domain.engineering.mathlab import gradientes as G
from academic_core.domain.engineering.mathlab import mvexpr as mx

FUNCIONES = ["x*y^2", "sin(x)*cos(y)", "exp(x*y)/(1+x^2)", "sqrt(x^2+y^2+1)",
             "ln(1+exp(x-y))", "x^3-3*x*y^2", "atan(y/(x^2+1))", "1/(1+exp(-(2*x-y)))",
             "x*ln(y^2+1)", "tanh(x+y)"]


@pytest.mark.parametrize("texto", FUNCIONES)
def test_gradiente_correcto_pasa_y_alterado_un_0_1_por_ciento_no(texto):
    f = mx.parse(texto)
    g = D.gradient(f)
    assert G.comprobar_expresion(f, g).ok
    v = sorted(g)[0]
    malo = {**g, v: mx.Mul(mx.num(1.001), g[v])}
    assert not G.comprobar_expresion(f, malo).ok


def test_pico_de_relu_no_es_falsa_discrepancia():
    f = lambda w: max(0.0, w[0]) * w[1]            # noqa: E731
    g = lambda w: [(1.0 if w[0] > 0 else 0.0) * w[1], max(0.0, w[0])]   # noqa: E731
    informe = G.comprobar(f, g, [[0.0, 2.0], [1.0, 3.0], [-1.0, 2.0]], ["a", "b"])
    assert informe.ok
    assert not informe.componentes[0].fiable      # ∂/∂a at a = 0: no derivative


def test_calculadora():
    r = ML.calcular(ML.Peticion("comprobar_gradiente",
                                {"f": "x^2*y", "gradiente": {"x": "2*x*y", "y": "x^2"}}))
    assert r.sello.verdict == "verificado"
    r = ML.calcular(ML.Peticion("comprobar_gradiente",
                                {"f": "x^2*y", "gradiente": {"x": "2*x", "y": "x^2"}}))
    assert r.sello.verdict == "discrepa" and "NO coincide" in r.avisos[0]
    r = ML.calcular(ML.Peticion("comprobar_gradiente", {"f": "exp(x)*sin(y)"}))
    assert r.sello.verdict == "verificado"
