# SPDX-License-Identifier: MIT
"""T-19: Taylor by arithmetic on truncated series, measured against SymPy and mpmath.

Hallado el 2026-10-05 al auditar `series.taylor` contra SymPy: la ruta de derivadas
moría en entradas correctas —`1/(1-x)` en orden 5, `sqrt(x)` en 1— y rechazaba
`exp(x)` en 2 diciendo que «no tiene desarrollo de Taylor», lo cual es falso.

Todo lo que aquí se afirma se mide contra una referencia externa: los coeficientes
contra `sympy.series`, la cota de Lagrange contra el error real calculado con
mpmath a 30 dígitos.
"""
from __future__ import annotations

from fractions import Fraction

import mpmath
import pytest
import sympy as sp

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import serie_formal as F
from academic_core.domain.engineering.mathlab import series as S
from academic_core.errors import UnsupportedError

x = sp.symbols("x")

CASOS = [
    ("1/(1-x)", "0"), ("sqrt(x)", "1"), ("exp(x)", "2"), ("sin(x)", "1"),
    ("tan(x)", "1"), ("x^2*exp(x)", "0"), ("sin(x)/x", "0"), ("(1-cos(x))/x^2", "0"),
    ("ln(1+sin(x))", "0"), ("atan(x)", "1"), ("asin(x)", "0"), ("acosh(x)", "2"),
    ("x^x", "1"), ("2^x", "0"), ("sec(x)", "0"), ("cot(x)", "1"), ("abs(x)", "-1"),
    ("exp(sin(x))", "0"), ("1/(x^4+1)", "1"), ("x^(1/3)", "8"), ("log10(x)", "3"),
    ("tanh(x)", "1"), ("atanh(x)", "0"), ("cosh(x)*sinh(2*x)", "1"),
    ("acos(x)", "1/2"), ("asinh(x)", "1"), ("csc(x)", "1"), ("coth(x)", "1"),
    ("sech(x)", "0"), ("ln(x)", "2"), ("1/(1+x^2)", "0"), ("x^(-2)", "1"),
    ("exp(x)/(1-x)", "0"), ("sin(x)^2", "1"), ("sec(x)", "1"), ("csch(x)", "1"),
    ("sech(x)", "2"), ("exp(-x^2)", "1"),
]


def _a_sympy(texto: str):
    return sp.sympify(texto.replace("^", "**").replace("ln(", "log(")
                      .replace("log10(x)", "log(x, 10)").replace("abs(", "Abs("))


@pytest.mark.parametrize("texto,centro", CASOS)
def test_los_coeficientes_coinciden_con_sympy(texto, centro):
    n = 8
    obtenidos = F.coeficientes(mx.parse(texto), "x", mx.parse(centro), n)
    c = sp.sympify(centro)
    serie = sp.series(_a_sympy(texto), x, c, n).removeO()
    serie = sp.expand(serie.subs(x, x + c)) if c != 0 else sp.expand(serie)
    for k, coef in enumerate(obtenidos):
        esperado = complex(sp.N(serie.coeff(x, k), 30))
        valor = mx.valor_real(coef, {})
        assert valor is not None, (texto, centro, k, mx.text(coef))
        assert abs(valor - esperado) <= 1e-10 * max(1.0, abs(esperado)), (
            texto, centro, k, mx.text(coef), esperado)


@pytest.mark.parametrize("texto,centro,orden", [
    ("1/(1-x)", 0, 5), ("1/(1-x)", 0, 40), ("sqrt(x)", 1, 5), ("sqrt(x)", 1, 30),
    ("exp(x)", 2, 6), ("sin(x)", 1, 6), ("tan(x)", 1, 6),
])
def test_lo_que_la_ruta_de_derivadas_rechazaba_ahora_se_desarrolla(texto, centro, orden):
    """The three failures of the audit, at the order where they failed and beyond."""
    serie = S.taylor(mx.parse(texto), centro, orden)
    assert mx.text(serie.polinomio)
    assert serie.metodo.startswith("serie formal") or serie.cota is not None


def test_exp_en_2_tiene_los_coeficientes_e2_entre_factorial():
    """The refusal said «no tiene desarrollo de Taylor en ese centro». It does."""
    coeficientes = F.coeficientes(mx.parse("exp(x)"), "x", mx.Num(Fraction(2)), 5)
    assert [mx.text(c) for c in coeficientes] == [
        "exp(2)", "exp(2)", "1/2*exp(2)", "1/6*exp(2)", "1/24*exp(2)"]


@pytest.mark.parametrize("texto,centro", [
    ("1/x", "0"), ("ln(x)", "0"), ("sqrt(x)", "0"), ("tan(x)", "pi/2"),
    ("ln(x)", "-1"), ("asin(x)", "1"), ("abs(x)", "0"), ("1/sin(x)", "0"),
    ("sec(x)", "pi/2"), ("cot(x)", "0"), ("csc(x)", "pi"), ("acosh(x)", "1"),
])
def test_se_niega_donde_la_funcion_no_tiene_desarrollo(texto, centro):
    """A pole, ln of 0 or of a negative, a root of 0, a non-differentiable point."""
    with pytest.raises(UnsupportedError):
        S.taylor(mx.parse(texto), mx.parse(centro), 4)


@pytest.mark.parametrize("nombre", ["sin", "cos", "exp", "sinh", "cosh"])
@pytest.mark.parametrize("centro", [-3, -1, 1, 2, 3])
@pytest.mark.parametrize("orden", [2, 5, 9])
def test_la_cota_de_lagrange_acota_el_error_real(nombre, centro, orden):
    """The declared bound against the real error, measured to 30 digits.

    Points on both sides of the centre and far from it, because a bound that only
    holds near the centre is not the bound that was declared («para todo x real»).
    """
    mpmath.mp.dps = 30
    serie = S.taylor(mx.Call(nombre, (mx.Sym("x"),)), centro, orden)
    assert serie.cota is not None
    funcion = {"sin": mpmath.sin, "cos": mpmath.cos, "exp": mpmath.exp,
               "sinh": mpmath.sinh, "cosh": mpmath.cosh}[nombre]
    for d in (-2.5, -1.0, -0.3, 0.2, 0.9, 2.0):
        punto = centro + d
        aproximado = mx.valor_real(serie.polinomio, {"x": punto})
        error = abs(float(funcion(mpmath.mpf(punto))) - aproximado)
        cota = mx.valor_real(serie.cota, {"x": punto})
        assert error <= cota * (1 + 1e-9) + 1e-12, (nombre, centro, orden, punto,
                                                     error, cota)


def test_una_serie_que_no_cabe_se_niega_al_construirla_y_no_al_imprimirla():
    """``tan`` about 1 has coefficients polynomial in tan(1) of growing degree.

    Returning a Serie that ``mx.text`` then refuses moves the error to whoever prints
    it, far from the call that caused it.
    """
    with pytest.raises(Exception) as exc:
        S.taylor(mx.parse("tan(x)"), 1, 20)
    assert "orden menor" in str(exc.value)


def test_el_residuo_es_el_primer_termino_omitido():
    serie = S.taylor(mx.parse("1/(1-x)"), 0, 4)
    assert mx.text(serie.residuo) == "x^5"
    serie = S.taylor(mx.parse("sin(x)/x"), 0, 3)
    assert mx.valor_real(serie.residuo, {"x": 1.0}) == pytest.approx(1 / 120)
