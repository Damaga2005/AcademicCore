# SPDX-License-Identifier: MIT
"""Integrals the engine refused or got only as decimals until 2026-10-06."""
from __future__ import annotations

import math

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import derive_mv as D
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import verify as V
from academic_core.domain.engineering.symbolic import integrate as I


def _calcula(texto):
    return ML.calcular(ML.Peticion("integrar", texto))


@pytest.mark.parametrize("texto,exacto", [
    ("int(sin(x), x, 0, pi)", "2"),
    ("int(sin(x)^2, x, 0, pi)", "1/2·π"),
    ("int(1/(1+x^2), x, -1, 1)", "1/2·π"),
    ("int(1/(1+x^2), x, 0, sqrt(3))", "1/3·π"),
    ("int(sqrt(x), x, 0, 4)", "16/3"),
    ("int(x^(1/3), x, 0, 8)", "12"),
    ("int(x^(2/3), x, -8, 8)", "192/5"),
    ("int(cos(x+pi/6), x, 0, pi/3)", "1/2"),
])
def test_valores_exactos(texto, exacto):
    r = _calcula(texto)
    assert r.exacto == exacto, (texto, r.exacto, r.aproximado)
    assert r.sello.verdict == V.VERIFIED


@pytest.mark.parametrize("texto,valor", [
    ("int(1/sqrt(x), x, 0, 1)", 2.0),
    ("int(1/x^(2/3), x, -1, 1)", 6.0),
    ("int(1/sqrt(1-x^2), x, -1, 1)", math.pi),
    ("int(ln(x), x, 0, 1)", -1.0),
])
def test_impropias_convergentes(texto, valor):
    r = _calcula(texto)
    assert abs(r.aproximado.real - valor) < 1e-9, (texto, r.aproximado)


@pytest.mark.parametrize("texto", ["int(1/x, x, 0, 1)", "int(1/x^2, x, -1, 1)",
                                   "int(tan(x), x, 0, 2)", "int(1/(x-1/10), x, 0, 1)"])
def test_impropias_divergentes(texto):
    r = _calcula(texto)
    assert r.aproximado is None and "DIVERGE" in r.sello.detail


@pytest.mark.parametrize("integrando", ["1/sqrt(1-x^2)", "1/sqrt(4-x^2)", "1/sqrt(x^2+1)",
                                        "1/sqrt(x^2-1)", "1/sqrt(2*x-x^2)", "exp(pi*x)",
                                        "cos(pi*x)", "pi^x", "x*exp(pi*x^2)"])
def test_primitivas_nuevas_derivan_en_el_integrando(integrando):
    primitiva, _ = I.integrate(mx.to_symbolic(mx.parse(integrando)), "x", I.StepLog())
    F = mx.from_symbolic(primitiva)
    puntos = (0.3, 0.6) if any(s in integrando for s in ("1-x", "4-x", "2*x-x")) else (1.7, 2.5)
    for v in puntos:
        assert abs(mx.valor_real(D.differentiate(F, "x"), {"x": v})
                   - mx.valor_real(mx.parse(integrando), {"x": v})) < 1e-9


def test_raiz_de_una_suma_lleva_parentesis():
    assert mx.pretty(mx.parse("sqrt(x^2+1)")) == "√(x² + 1)"
    assert mx.pretty(mx.parse("x^(-1)")) == "x⁻¹"


def test_una_raiz_impar_es_real_para_bases_negativas():
    assert mx.valor_real(mx.parse("x^(2/3)"), {"x": -8}) == pytest.approx(4.0)
