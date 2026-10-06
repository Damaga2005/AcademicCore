# SPDX-License-Identifier: MIT
"""ML-12: distribuciones con área — δ, escalón, saltos, cribado y trenes."""
from __future__ import annotations

import math
from fractions import Fraction as F

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import distribuciones as D
from academic_core.domain.engineering.mathlab import mvexpr as mx


def _calc(**entrada):
    return ML.calcular(ML.Peticion("distribucion", entrada))


@pytest.mark.parametrize("texto,esperado", [
    ("3*delta(2*t-1)", "(3/2)·δ(t − 1/2)"),          # δ(at − b) = δ(t − b/a)/|a|
    ("cos(t)*delta(t)", "δ(t)"),                     # cribado
    ("t^2*delta(t-3)-delta(t-3)", "8·δ(t − 3)"),     # áreas en el mismo punto se suman
    ("u(t)-u(t-1)", "1 en (0, 1)"),
    ("-u(1-t)", "-1 en (−∞, 1)"),
])
def test_lectura(texto, esperado):
    assert D.leer(texto).texto() == esperado


def test_derivada_de_saltos_es_delta_con_area_el_salto():
    r = _calc(calculo="derivada", expr="t^2*u(t-1)+3*u(t-2)")
    assert r.exacto == "2*t en (1, +∞) + δ(t − 1) + 3·δ(t − 2)"
    assert r.sello.verdict == "verificado"


@pytest.mark.parametrize("expr", ["u(t)-u(t-1)", "t*u(t)-t*u(t-2)", "exp(-t)*u(t)",
                                  "(1-t)*u(t)+t*u(t-1)-5*u(t-3)"])
def test_integral_de_la_derivada_es_el_incremento(expr):
    d = D.leer(expr)
    dd = D.derivada(d)
    a, b = F(-1, 2), F(7, 2)
    inc = mx.evaluate(d.ordinaria(b) and mx.substitute(d.ordinaria(b), "t", mx.num(b))) - \
        mx.evaluate(mx.substitute(d.ordinaria(a), "t", mx.num(a)))
    assert abs(mx.evaluate(D.integral(dd, a, b)) - inc) < 1e-12


def test_delta_en_el_limite_exige_convencion():
    with pytest.raises(Exception, match="AMBIGUOUS"):
        _calc(calculo="integral", expr="delta(t)", desde="0", hasta="1")
    r = _calc(calculo="integral", expr="delta(t)", desde="0", hasta="1", extremo="mitad")
    assert r.exacto == "1/2"


def test_convolucion_y_tren():
    assert _calc(calculo="convolucion", expr="delta(t-1)+2*delta(t+1)",
                 f="t^2").exacto == "2*t + 3*t^2 + 3"
    assert "(1/2)·Σₖ δ(f − k/2)" in _calc(calculo="tren", periodo="2").exacto
    omega = ML.calcular(ML.Peticion("distribucion", {"calculo": "tren", "periodo": "2"},
                                    convenciones=ML.ConvencionConjunto.of(frecuencia="omega")))
    assert "π·Σₖ δ(ω − 2π·k/2)" in omega.exacto


@pytest.mark.parametrize("texto", ["delta(t)*u(t)", "sin(delta(t))", "delta((t-1)^2)",
                                   "delta(t)*delta(t-1)", "1/delta(t)"])
def test_lo_que_no_esta_definido_lo_rechaza(texto):
    with pytest.raises(Exception):
        D.leer(texto)


@pytest.mark.parametrize("texto,esperado", [
    ("delta(t^2-1)", "(1/2)·δ(t + 1) + (1/2)·δ(t − 1)"),
    ("delta(t^3-t)", "(1/2)·δ(t + 1) + δ(t) + (1/2)·δ(t − 1)"),
    ("delta(t^2-2)", "(1/4*sqrt(2))·δ(t + sqrt(2)) + (1/4*sqrt(2))·δ(t − sqrt(2))"),
    ("delta'(t^2-1)", "(-1/4)·δ′(t + 1) + (1/4)·δ(t + 1) + (1/4)·δ′(t − 1) + (1/4)·δ(t − 1)"),
    ("u(t^2-1)", "1 en (−∞, -1) + 1 en (1, +∞)"),
    ("u(t)*u(1-t)", "1 en (0, 1)"),
    ("exp(t)*delta(t-1)*u(t)", "(exp(1))·δ(t − 1)"),
    ("exp(t)*delta(t+1)*u(t)", "0"),
    ("t*delta'(t-1)", "δ′(t − 1) − δ(t − 1)"),
    ("delta'(2*t)", "(1/4)·δ′(t)"),
    ("sin(t)*delta''(t)", "-2·δ′(t)"),
])
def test_lo_que_antes_faltaba(texto, esperado):
    assert D.leer(texto).texto() == esperado


def test_u0_declarado():
    assert D.leer("delta(t)*u(t)", u0=F(1, 2)).texto() == "(1/2)·δ(t)"
    r = _calc(calculo="leer", expr="delta(t)*u(t)", u0="1")
    assert r.exacto == "δ(t)"


def test_derivada_de_delta_y_su_integral():
    assert D.derivada(D.leer("delta(t-2)")).texto() == "δ′(t − 2)"
    assert mx.text(D.integral(D.leer("delta'(t)+delta(t-1/2)"), -1, 1)) == "1"
    with pytest.raises(Exception, match="AMBIGUOUS"):
        D.integral(D.leer("delta'(t)"), 0, 1)
    assert mx.text(D.convolucion_con_impulsos(mx.parse("t^3"), D.leer("delta'(t-1)"))) == \
        "3*(t - 1)^2"


def _gauss(x, eps):
    return math.exp(-x * x / (2 * eps * eps)) / (eps * math.sqrt(2 * math.pi))


def _simpson(f, a, b, n=200000):
    h = (b - a) / n
    s = f(a) + f(b)
    for i in range(1, n):
        s += (4 if i % 2 else 2) * f(a + i * h)
    return s * h / 3


@pytest.mark.parametrize("g,f", [("t^2-1", "exp(t)"), ("t^3-t", "cos(t)+2"),
                                 ("4*t^2-1", "t+3"), ("t^2-2", "1")])
def test_delta_de_g_contra_gaussiana_estrecha(g, f):
    """Second path: δ ≈ narrow Gaussian; ∫ f(t)·δ_ε(g(t)) dt → Σ f(tᵢ)/|g′(tᵢ)|."""
    fe, ge = mx.parse(f), mx.parse(g)
    d = D.leer(f"({f})*delta({g})")
    exacto = sum(mx.valor_real(i.area, {}) for i in d.impulsos)
    numerico = _simpson(lambda t: mx.valor_real(fe, {"t": t}) *
                        _gauss(mx.valor_real(ge, {"t": t}), 1e-3), -3, 3)
    assert abs(numerico - exacto) < 1e-4 * max(1, abs(exacto))


def test_doblete_contra_gaussiana():
    """∫ f(t)·δ′(t − 1) dt = −f′(1): with f = t³, −3."""
    d = D.leer("t^3*delta'(t-1)")
    dg = lambda x, e: -x / (e * e) * _gauss(x, e)        # noqa: E731
    numerico = _simpson(lambda t: t ** 3 * dg(t - 1, 1e-3), -2, 4)
    # the Leibniz form t³δ′(t−1) = δ′(t−1) − 3δ(t−1) integrates to −3
    areas = {i.orden: mx.valor_real(i.area, {}) for i in d.impulsos}
    assert areas == {1: 1.0, 0: -3.0} and abs(numerico + 3) < 1e-4


def _aplica(d, f):
    """⟨D, f⟩ = Σ (−1)ᵏ·área·f⁽ᵏ⁾(t₀)."""
    from academic_core.domain.engineering.mathlab import derive_mv as DM

    total = 0.0
    for imp in d.impulsos:
        fk = mx.parse(f)
        for _ in range(imp.orden):
            fk = DM.differentiate(fk, "t")
        total += (-1) ** imp.orden * mx.valor_real(imp.area, {}) * \
            mx.valor_real(fk, {"t": imp.posicion.x})
    return total


@pytest.mark.parametrize("f,g,k", [("exp(t)", "t^2-1", 1), ("cos(t)+t", "t^3-t", 1),
                                   ("t^2+1", "t^2-2", 1), ("exp(t)", "t^2-1", 2),
                                   ("1+t", "t^3-2", 0), ("t", "t^3-3*t+1", 0)])
def test_delta_k_de_g_contra_gaussiana(f, g, k):
    """δ⁽ᵏ⁾(g) by (1/g′·d/dt)ᵏ, and roots without closed form (Sturm), checked against
    ∫ f(t)·δ_ε⁽ᵏ⁾(g(t)) dt with a narrow Gaussian."""
    nucleos = {0: lambda x, e: _gauss(x, e),
               1: lambda x, e: -x / (e * e) * _gauss(x, e),
               2: lambda x, e: (x * x / e ** 4 - 1 / (e * e)) * _gauss(x, e)}
    d = D.leer(f"delta{chr(39) * k}({g})")
    fe, ge = mx.parse(f), mx.parse(g)
    numerico = _simpson(lambda t: mx.valor_real(fe, {"t": t}) *
                        nucleos[k](mx.valor_real(ge, {"t": t}), 2e-3), -3, 3, 400000)
    assert abs(_aplica(d, f) - numerico) < 1e-3 * max(1, abs(numerico))


def test_raices_sin_forma_exacta_marcan_el_resultado():
    r = _calc(calculo="leer", expr="(1+t)*delta(t^3-2)")
    assert r.exacto.startswith("≈0.4745536836·δ(t − (≈1.25992104989))")
    assert r.sello.verdict == "solo_numerico" and r.avisos
