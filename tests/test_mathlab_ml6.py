# SPDX-License-Identifier: MIT
"""ML-6: integración múltiple (Fubini, jacobianos, cambio de orden, masa y centro)."""

from __future__ import annotations

import math
from fractions import Fraction

import pytest

from academic_core.domain.engineering.mathlab import multiple as M
from academic_core.domain.engineering.mathlab import mvexpr as mx


def _val(r):
    return float(mx.valor_real(r.exacto, {}))


def test_iteradas_exactas():
    assert M.iterada("x+y", [["y", 0, "x"], ["x", 0, 1]]).exacto == mx.Num(Fraction(1, 2))
    r = M.iterada("1", [["z", 0, "1-x-y"], ["y", 0, "1-x"], ["x", 0, 1]])
    assert mx.exact_value(r.exacto) == Fraction(1, 6) and r.coincide
    r = M.iterada("1", [["y", 0, "sqrt(1-x^2)"], ["x", -1, 1]])   # singular en ±1
    assert abs(_val(r) - math.pi / 2) < 1e-12


def test_coordenadas_con_jacobiano():
    r = M.en_coordenadas("exp(-x^2-y^2)", "polares", [["r", 0, 1], ["t", 0, "2*pi"]])
    assert abs(_val(r) - math.pi * (1 - math.exp(-1))) < 1e-12
    r = M.en_coordenadas("1", "esfericas", [["rho", 0, 2], ["phi", 0, "pi"],
                                            ["theta", 0, "2*pi"]])
    assert abs(_val(r) - 32 * math.pi / 3) < 1e-10
    r = M.en_coordenadas("x^2+y^2+z^2", "esfericas", [["rho", 0, 1], ["phi", 0, "pi"],
                                                      ["theta", 0, "2*pi"]])
    assert abs(_val(r) - 4 * math.pi / 5) < 1e-12
    r = M.en_coordenadas("z", "cilindricas", [["z", "r", 1], ["r", 0, 1], ["t", 0, "2*pi"]])
    assert abs(_val(r) - math.pi / 4) < 1e-12


def test_cambio_de_orden():
    # ∫₀¹∫ₓ¹ sin(y²) dy dx no tiene primitiva en y; en el otro orden sí
    franjas, orig, nuevo = M.cambio_orden("sin(y^2)", "x", 0, 1, "y", "x", 1)
    assert orig.exacto is None and nuevo.exacto is not None
    assert abs(_val(nuevo) - (1 - math.cos(1)) / 2) < 1e-12
    franjas, _, nuevo = M.cambio_orden("1", "x", 0, 4, "y", "0", "sqrt(x)")
    assert [f.texto("x", "y") for f in franjas] == ["0 ≤ y ≤ 2, y^2 ≤ x ≤ 4"]
    assert mx.exact_value(nuevo.exacto) == Fraction(16, 3)
    with pytest.raises(Exception, match="monótona"):
        M.cambio_orden("1", "x", -1, 1, "y", "x^2", "2")


def test_masa_y_centro():
    Mm, c = M.centro_masas("1", [["y", 0, "1-x"], ["x", 0, 1]])
    assert mx.exact_value(Mm.exacto) == Fraction(1, 2)
    assert [mx.exact_value(r.exacto) for r in c] == [Fraction(1, 3), Fraction(1, 3)]


def test_rechazos():
    with pytest.raises(Exception, match="dependen de"):
        M.iterada("1", [["x", 0, 1], ["y", 0, "x"]])
    with pytest.raises(Exception, match="sin integrar"):
        M.iterada("a*x", [["x", 0, 1]])
    r = M.iterada("exp(x^2)", [["x", 0, 1]])           # sin primitiva elemental
    assert r.exacto is None and abs(r.numerico - 1.4626517459071817) < 1e-10


def test_calculadora_multiple():
    import academic_core.domain.engineering.mathlab as ML

    r = ML.calcular(ML.Peticion("multiple", {"calculo": "coordenadas", "sistema": "polares",
                                             "expr": "1", "limites": [["r", 0, 1],
                                                                      ["t", 0, "2*pi"]]}))
    assert r.sello.verdict == "verificado" and "pi" in r.exacto
    r = ML.calcular(ML.Peticion("multiple", {"calculo": "cambio_orden", "expr": "sin(y^2)",
                                             "x": "x", "a": 0, "b": 1, "y": "y",
                                             "g1": "x", "g2": "1"}))
    assert r.sello.verdict == "verificado" and "cos(1)" in r.exacto
    r = ML.calcular(ML.Peticion("multiple", {"calculo": "iterada", "expr": "exp(x^2)",
                                             "limites": [["x", 0, 1]]}))
    assert r.sello.verdict == "solo_numerico"
