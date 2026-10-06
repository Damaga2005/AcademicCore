# SPDX-License-Identifier: MIT
"""ML-2 (T1): desigualdades no periódicas por tabla de signos exacta."""
from __future__ import annotations

import pytest

import academic_core.domain.engineering.mathlab as ML


@pytest.mark.parametrize("q,esperado", [
    ("x^2-1>0", "(−∞, -1) ∪ (1, +∞)"), ("x^2-1<=0", "[-1, 1]"),
    ("(x-1)/(x+2)>=0", "(−∞, -2) ∪ [1, +∞)"), ("abs(x-1)<2", "(-1, 3)"),
    ("abs(2*x-3)>=1", "(−∞, 1] ∪ [2, +∞)"), ("x^3-x<0", "(−∞, -1) ∪ (0, 1)"),
    ("ln(x)>1", "(exp(1), +∞)"), ("exp(x)<=2", "(−∞, ln(2)]"),
    ("(x^2-4)/(x-1)<0", "(−∞, -2) ∪ (1, 2)"), ("sqrt(x-1)<2", "[1, 5)"),
    ("1/x>1", "(0, 1)"), ("x^2+1>0", "ℝ"), ("x^2<0", "∅"), ("x^2<=0", "{0}"),
])
def test_desigualdad(q, esperado):
    r = ML.calcular(ML.Peticion("resolver_inequidad", q))
    assert r.exacto == esperado and r.sello.verdict == "verificado"
