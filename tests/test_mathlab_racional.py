# SPDX-License-Identifier: MIT
"""ML-12: rational functions of several variables, checked against SymPy."""
from __future__ import annotations

import random

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import poly as P
from academic_core.domain.engineering.mathlab import racional as R

sp = pytest.importorskip("sympy")

s, a, b = sp.symbols("s a b")


def _rnd(rng, d):
    return sum(rng.randint(-3, 3) * s**i * a**j * b**k
               for i in range(d + 1) for j in range(2) for k in range(2) if rng.random() < 0.35)


def test_el_mcd_multivariable_coincide_con_sympy():
    rng = random.Random(11)
    for _ in range(80):
        f, g, h = _rnd(rng, 2), _rnd(rng, 2), _rnd(rng, 1)
        if 0 in (f, g, h):
            continue
        A, B = sp.expand(f * h), sp.expand(g * h)
        G = R.mcd(P.as_poly(mx.parse(str(A).replace("**", "^"))),
                  P.as_poly(mx.parse(str(B).replace("**", "^"))))
        cociente = sp.simplify(sp.sympify(mx.text(P.to_expr(G)).replace("^", "**")) / sp.gcd(A, B))
        assert cociente.is_number, (A, B)


def test_la_forma_normal_esta_en_terminos_minimos():
    rng = random.Random(12)
    for _ in range(60):
        f, g, h = _rnd(rng, 2), _rnd(rng, 2), _rnd(rng, 1)
        if 0 in (f, g, h):
            continue
        E = f * h / (g * h)
        forma = R.forma_normal(mx.parse(str(E).replace("**", "^")), "s")
        nuestra = sp.sympify(mx.text(forma.expresion()).replace("^", "**"))
        ref = sp.cancel(sp.together(E))
        assert sp.simplify(nuestra - ref) == 0
        assert sp.degree(sp.denom(sp.together(nuestra)), s) == sp.degree(sp.denom(ref), s)


@pytest.mark.parametrize("expr,factorizada", [
    ("(s^2-a^2)/(s-a)", "(s + a)"),
    ("K/(s*(s+a))", "K·1/(s·(s + a))"),
    ("(s+1)^2/(s*(s+1)^3)", "1/(s·(s + 1))"),
    ("1/(s^2+(a+b)*s+a*b)", "1/((s + b)·(s + a))"),
    ("1/(s^2+4)", "1/((s − 2·i)·(s + 2·i))"),
    ("(s+1)/(s^2+2*s+5)", "(s + 1)/((s − (-1 + 2·i))·(s − (-1 − 2·i)))"),
])
def test_ceros_y_polos(expr, factorizada):
    assert R.forma_normal(mx.parse(expr), "s").factorizada() == factorizada


def test_la_discusion_del_rlc_aisla_la_condicion():
    forma = R.forma_normal(mx.parse("1/(L*C*s^2+R*C*s+1)"), "s")
    assert any("C·R² − 4·L" in d for d in forma.discusion), forma.discusion


def test_la_calculadora_responde_y_verifica():
    r = ML.calcular(ML.Peticion("racional", {"expr": "(s^2-a^2)/(s-a)", "var": "s"}))
    assert r.exacto == "(s + a)" and r.sello.ok
