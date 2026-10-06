# SPDX-License-Identifier: MIT
"""ML-12: distribuciones con área — δ, escalón, saltos, cribado y trenes."""
from __future__ import annotations

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


@pytest.mark.parametrize("texto", ["delta(t^2-1)", "delta(t)*u(t)", "sin(delta(t))"])
def test_lo_que_no_sabe_lo_rechaza(texto):
    with pytest.raises(Exception):
        D.leer(texto)
