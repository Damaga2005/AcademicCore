# SPDX-License-Identifier: MIT
"""ML-13: operadores ∇ con factores de escala, Poisson, bases, V dado y cinemática."""

from __future__ import annotations

import pytest

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import operadores as O


def _t(v):
    return [mx.text(c) for c in v]


def test_operadores_esfericas_y_cilindricas():
    assert _t(O.gradiente("1/r", "esfericas")) == ["-1/r^2", "0", "0"]
    assert mx.text(O.laplaciano("1/r", "esfericas")) == "0"
    assert mx.text(O.laplaciano("r^2", "esfericas")) == "6"
    assert mx.text(O.divergencia(["r^3", "0", "0"], "esfericas")) == "5*r^2"
    assert _t(O.rotacional(["0", "r^2", "0"], "cilindricas")) == ["0", "0", "3*r"]
    assert _t(O.rotacional(["0", "0", "r*sin(theta)"], "esfericas")) == [
        "2*cos(theta)", "-2*sin(theta)", "0"]
    assert mx.text(O.laplaciano("r^2*cos(2*phi)", "cilindricas")) == "0"


def test_poisson_y_controles():
    assert mx.text(O.poisson("r^2", "esfericas")) == "-6*eps0"
    O.controles(["r*z", "r^2*sin(phi)", "z"], "r^2*z", "cilindricas")


def test_cambio_de_base():
    v = O.cambio_base(["1", "0", "0"], "esfericas", "cartesianas",
                      {"r": 2, "theta": "pi/4", "phi": 3})
    assert abs(float(mx.valor_real(v[2], {})) - 2 ** -0.5) < 1e-12
    assert _t(O.cambio_base(["x", "y", "0"], "cartesianas", "cilindricas")) == ["r", "0", "0"]


def test_electrostatica_caja_por_los_dos_lados():
    r = O.electrostatica("x^2*y+z^3", "cartesianas", [0, 1, 0, 1, 0, 1])
    assert _t(r.E) == ["-2*x*y", "-x^2", "-3*z^2"]
    assert r.carga_volumen.exacto == r.carga_flujo.exacto


def test_intrinseca():
    h = O.intrinseca(["cos(t)", "sin(t)", "t"])
    assert mx.text(h.kappa) == "1/2" and mx.text(h.a_t) == "0" and mx.text(h.a_n) == "1"
    c = O.intrinseca(["3*cos(2*t)", "3*sin(2*t)"], t0=0)
    assert mx.text(c.radio) == "3" and mx.text(c.a_n) == "12"
    with pytest.raises(Exception, match="v = 0"):
        O.intrinseca(["t^2", "t^3"], t0=0)        # cúspide: no regular


def test_calculadora_operadores():
    import academic_core.domain.engineering.mathlab as ML

    r = ML.calcular(ML.Peticion("operadores", {"calculo": "laplaciano", "V": "1/r",
                                               "sistema": "esfericas"}))
    assert r.sello.verdict == "verificado" and r.exacto == "∇²V = 0"
