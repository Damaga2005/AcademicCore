# SPDX-License-Identifier: MIT
"""ML-3 + cierre de los 5 huecos de ML-2 (MATH_LAB.md §ML-2 'Lo que no hace').

Huecos:
1. superexponenciales (3^n·n!/n^n, e^(x^2)·e^(-x^2)) y ln(ln x).
2. Dirichlet para integrales y series oscilantes no absolutamente convergentes.
3. Suma de series de potencias por Taylor (Σ x^n/n = -ln(1-x)).
4. Función Gamma y potencias de cuadrático irreducible en fracciones simples.
5. Parámetro en exponente: barrido ampliado y honesto fuera del rango.

ML-3 (álgebra lineal): autovalores/diagonalización, Gram-Schmidt,
mínimos cuadrados/pseudoinversa y Cramer/Sarrus con traza.
"""

from __future__ import annotations

import math
from fractions import Fraction

import pytest

from academic_core.domain.engineering.mathlab import mvexpr as mx


# ---------------------------------------------------------------------------
# 1. superexponenciales y ln(ln x)
# ---------------------------------------------------------------------------

def test_limite_exp_cuadratico_compensado():
    from academic_core.domain.engineering.mathlab import limite as LM

    r = LM.limite(mx.parse("exp(x^2)*exp(-x^2)"), "x", "oo")
    assert r.expr is not None and abs(float(mx.valor_real(r.expr, {})) - 1.0) < 1e-12


def test_limite_factorial_stirling():
    from academic_core.domain.engineering.mathlab import limite as LM
    from academic_core.domain.engineering.mathlab import series_numericas as SN

    # 3^n·n!/n^n -> +∞ porque el cociente -> 3/e > 1
    T = SN.leer("3^n*n!/n^n", "n")
    r = LM.limite(SN.cociente(T), "n", "oo")
    assert r.expr is not None
    assert float(mx.valor_real(r.expr, {})) > 1.0


def test_limite_ln_ln():
    from academic_core.domain.engineering.mathlab import limite as LM

    r = LM.limite(mx.parse("ln(ln(x))/ln(x)"), "x", "oo")
    assert r.expr is not None and abs(float(mx.valor_real(r.expr, {}))) < 1e-12


# ---------------------------------------------------------------------------
# 2. Dirichlet
# ---------------------------------------------------------------------------

def test_impropia_dirichlet_seno_sobre_x():
    from academic_core.domain.engineering.mathlab import impropia as IM

    c = IM.convergencia(mx.parse("sin(x)/x"), "x", "1", "oo", con_valor=False)
    assert c.converge
    assert any("Dirichlet" in loc.razon for loc in c.locales)


def test_serie_dirichlet_seno_sobre_n():
    from academic_core.domain.engineering.mathlab import series_numericas as SN

    T = SN.leer("sin(n)/n", "n")
    v = SN.convergencia(T, 1)
    assert v.converge


# ---------------------------------------------------------------------------
# 3. suma de potencias por Taylor
# ---------------------------------------------------------------------------

def test_suma_potencias_log():
    from academic_core.domain.engineering.mathlab import series_numericas as SN

    T = SN.leer("x^n/n", "n")
    s = SN.suma_potencias(T, "x")
    assert s is not None
    # en x=1/2: -ln(1-1/2) = ln 2
    assert abs(float(mx.valor_real(s, {"x": 0.5})) - math.log(2)) < 1e-9


# ---------------------------------------------------------------------------
# 4. Gamma y cuadrático repetido
# ---------------------------------------------------------------------------

def test_gamma_enteros_y_medios():
    from academic_core.domain.engineering.mathlab import gamma as G

    assert G.gamma(mx.Num(Fraction(5))) == mx.Num(Fraction(24))
    g = G.gamma(mx.Div(mx.Num(Fraction(1)), mx.Num(Fraction(2))))
    assert g is not None
    assert abs(float(mx.valor_real(g, {})) - math.sqrt(math.pi)) < 1e-12
    with pytest.raises(Exception):
        G.gamma(mx.Num(Fraction(0)))
    with pytest.raises(Exception):
        G.gamma(mx.parse("1/3"))


def test_impropia_gamma_valor():
    from academic_core.domain.engineering.mathlab import impropia as IM

    r = IM.convergencia(mx.parse("x^2*exp(-x)"), "x", "0", "oo")
    assert r.converge and r.valor is not None
    assert abs(float(mx.valor_real(r.valor, {})) - 2.0) < 1e-12


def test_calculadoras_nuevas():
    import academic_core.domain.engineering.mathlab as ML

    r = ML.calcular(ML.Peticion("gamma", {"expr": "5"}))
    assert r.exacto == "24" and r.sello.verdict == "verificado"
    r = ML.calcular(ML.Peticion("algebra", {"calculo": "cramer",
                                            "matriz": [[2, 1], [1, 2]],
                                            "b": [3, 3]}))
    assert r.sello.verdict == "verificado" and "1" in r.exacto
    r = ML.calcular(ML.Peticion("serie", {"calculo": "suma_potencias",
                                          "termino": "x^n/n", "var": "n", "x": "x"}))
    assert r.sello.verdict == "verificado"


def test_primitiva_cuadratico_repetido():
    from academic_core.domain.engineering.mathlab import primitivas as PR

    f = PR.fracciones_simples([Fraction(1)], [Fraction(1), Fraction(0), Fraction(2),
                                             Fraction(0), Fraction(1)], "x")
    assert f.primitiva is not None
    ok, _ = PR.comprueba(f.primitiva, mx.parse("1/(x^2+1)^2"), "x")
    assert ok


# ---------------------------------------------------------------------------
# 5. barrido ampliado
# ---------------------------------------------------------------------------

def test_barrido_cubre_mas_de_diez():
    from academic_core.domain.engineering.mathlab import limite as LM

    e = mx.parse("x^a/(1+x^2)", nombres={"a", "x"})
    casos = LM.limite_con_parametro(e, "x", "oo", "a")
    texto = "; ".join(f"{c.condicion}: {c.valor}" for c in casos)
    assert "geométrica" in texto


# ---------------------------------------------------------------------------
# ML-3: autovalores, Gram-Schmidt, mínimos cuadrados
# ---------------------------------------------------------------------------

def test_ml3_autovalores_2x2():
    from academic_core.domain.engineering.mathlab import algebra as AL

    A = [[Fraction(2), Fraction(1)], [Fraction(1), Fraction(2)]]
    vals = AL.autovalores(A)
    assert sorted(vals) == [Fraction(1), Fraction(3)]


def test_ml3_autovalores_irracionales_reales():
    from academic_core.domain.engineering.mathlab import algebra as AL
    from academic_core.domain.engineering.mathlab import mvexpr as mx

    vals = AL.autovalores([[Fraction(2), Fraction(1)], [Fraction(1), Fraction(1)]])
    assert len(vals) == 2 and all(isinstance(v, mx.Expr) for v in vals)
    flot = sorted(float(mx.valor_real(v, {})) for v in vals)
    assert abs(flot[0] - (3 - 5 ** 0.5) / 2) < 1e-12
    assert abs(flot[1] - (3 + 5 ** 0.5) / 2) < 1e-12
    with pytest.raises(Exception, match="no racional"):
        AL.diagonalizar([[Fraction(2), Fraction(1)], [Fraction(1), Fraction(1)]])


def test_ml3_gram_schmidt():
    from academic_core.domain.engineering.mathlab import algebra as AL

    base = AL.gram_schmidt([[Fraction(1), Fraction(1)], [Fraction(1), Fraction(0)]])
    assert len(base) == 2
    # ortogonalidad exacta
    assert base[0][0] * base[1][0] + base[0][1] * base[1][1] == Fraction(0)


def test_ml3_minimos_cuadrados():
    from academic_core.domain.engineering.mathlab import algebra as AL

    x, _ = AL.minimos_cuadrados([[Fraction(1), Fraction(1)], [Fraction(1), Fraction(2)]],
                                [Fraction(2), Fraction(3)])
    assert x == [Fraction(1), Fraction(1)]
