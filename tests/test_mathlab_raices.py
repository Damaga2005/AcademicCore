# SPDX-License-Identifier: MIT
"""ML-2: ceros reales — exactos cuando se puede, aislados por Sturm cuando no."""
from __future__ import annotations

import random
from fractions import Fraction

import pytest

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import raices as R

sp = pytest.importorskip("sympy")


def test_polinomios_contra_sympy_real_roots():
    x = sp.Symbol("x")
    rng = random.Random(5)
    for _ in range(200):
        d = rng.randint(1, 6)
        if rng.random() < 0.4:
            p = sp.Integer(rng.choice([1, 2, -3]))
            for _ in range(d):
                p *= (x - sp.Rational(rng.randint(-4, 4), rng.choice([1, 2]))) ** rng.choice([1, 2])
            if rng.random() < 0.5:
                p *= x ** 2 - rng.choice([2, 3, 5])
            p = sp.expand(p)
        else:
            p = sum(rng.randint(-5, 5) * x ** k for k in range(d + 1))
            if sp.degree(p, x) < 1:
                continue
        cs = [Fraction(int(c.p), int(c.q)) for c in reversed(sp.Poly(p, x).all_coeffs())]
        r = R.raices_polinomio(cs)
        ref = sorted(float(v) for v in sp.real_roots(sp.Poly(p, x)))
        ours = sorted(v for q in r.raices for v in [q.x] * q.multiplicidad)
        assert len(ref) == len(ours), p
        assert all(abs(a - b) < 1e-6 * max(1, abs(a)) for a, b in zip(ref, ours)), p
        for q in r.raices:
            if q.exacta:
                assert abs(mx.valor_real(q.valor, {}) - q.x) < 1e-9, (p, mx.text(q.valor))


@pytest.mark.parametrize("e,texto,completo", [
    ("(1-ln(x))/x^2", "exp(1)", True),
    ("exp(2*x)-3", "1/2*ln(3)", True),
    ("2-sqrt(x+1)", "3", True),
    ("x^3-3*x", "-sqrt(3), 0, sqrt(3)", True),
    ("x^4-10*x^2+1", "-sqrt(5 + 2*sqrt(6)), -sqrt(5 - 2*sqrt(6)), sqrt(5 - 2*sqrt(6)), "
                     "sqrt(5 + 2*sqrt(6))", True),
    ("x^2*exp(x)*(x+2)", "-2, 0 (multiplicidad 2)", True),
    ("exp(x)+1", "ninguno", True),
    ("x/(x-1)", "0", True),
    ("ln(x^2)-1", "-sqrt(exp(1)), sqrt(exp(1))", True),
    ("cos(x)-x", "≈ 0.739085133215", False),
])
def test_ceros(e, texto, completo):
    r = R.ceros(mx.parse(e), "x")
    assert r.texto() == texto and r.completo == completo
