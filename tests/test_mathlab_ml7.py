# SPDX-License-Identifier: MIT
"""ML-7: línea, superficie, potencial y Green/Stokes/Gauss por los dos lados."""

from __future__ import annotations

import math

import pytest

from academic_core.domain.engineering.mathlab import mvexpr as mx
from academic_core.domain.engineering.mathlab import vectorial as VE

CIRC = {"r": ["cos(t)", "sin(t)"], "t": "t", "a": 0, "b": "2*pi"}
HELICE = {"r": ["cos(t)", "sin(t)", "t"], "a": 0, "b": "2*pi"}
ESFERA = {"r": ["sin(u)*cos(v)", "sin(u)*sin(v)", "cos(u)"],
          "limites": [["u", 0, "pi"], ["v", 0, "2*pi"]]}


def _v(r):
    return float(mx.valor_real(r.exacto, {}))


def test_linea():
    assert abs(_v(VE.circulacion(["-y", "x"], CIRC)) - 2 * math.pi) < 1e-12
    assert abs(_v(VE.linea_escalar("1", HELICE)) - 2 * math.pi * math.sqrt(2)) < 1e-12
    assert abs(_v(VE.linea_escalar("x^2", {"r": ["2*cos(t)", "2*sin(t)"], "a": 0,
                                           "b": "2*pi"})) - 8 * math.pi) < 1e-12


def test_potencial():
    phi = VE.potencial(["2*x*y+z", "x^2", "x"])
    assert mx.text(phi) in ("x*z + x^2*y", "x^2*y + x*z")
    with pytest.raises(Exception, match="no es un gradiente"):
        VE.potencial(["-y", "x"])
    a = VE.circulacion(["2*x*y+z", "x^2", "x"], HELICE)
    b = VE.circulacion_por_potencial(["2*x*y+z", "x^2", "x"], HELICE)
    assert abs(a.numerico - b.numerico) < 1e-10 and abs(a.numerico - 2 * math.pi) < 1e-10


def test_superficie():
    assert abs(_v(VE.flujo(["x", "y", "z"], ESFERA)) - 4 * math.pi) < 1e-12
    assert abs(_v(VE.superficie_escalar("1", ESFERA)) - 4 * math.pi) < 1e-12
    par = {"r": ["u*cos(v)", "u*sin(v)", "u^2"], "limites": [["u", 0, 1], ["v", 0, "2*pi"]]}
    assert abs(_v(VE.superficie_escalar("1", par)) - math.pi / 6 * (5 ** 1.5 - 1)) < 1e-12


def test_teoremas_dos_lados():
    T = VE.green(["-y", "x"], [["r", 0, 1], ["t", 0, "2*pi"]], "polares", CIRC)
    assert T.coinciden and abs(_v(T.lado_a[1]) - 2 * math.pi) < 1e-12
    tri = [{"r": ["t", "0"], "a": 0, "b": 1}, {"r": ["1-t", "t"], "a": 0, "b": 1},
           {"r": ["0", "1-t"], "a": 0, "b": 1}]
    assert VE.green(["x*y", "x^2"], [["y", 0, "1-x"], ["x", 0, 1]], borde=tri).coinciden
    hemi = {"r": ["sin(u)*cos(v)", "sin(u)*sin(v)", "cos(u)"],
            "limites": [["u", 0, "pi/2"], ["v", 0, "2*pi"]]}
    assert VE.stokes(["-y", "x", "z"], hemi, {"r": ["cos(t)", "sin(t)", "0"], "a": 0,
                                              "b": "2*pi"}).coinciden
    lat = {"r": ["cos(v)", "sin(v)", "u"], "limites": [["u", 0, 1], ["v", 0, "2*pi"]],
           "orientacion": -1}
    tapa = {"r": ["u*cos(v)", "u*sin(v)", "1"], "limites": [["u", 0, 1], ["v", 0, "2*pi"]]}
    fondo = {"r": ["u*cos(v)", "u*sin(v)", "0"], "limites": [["u", 0, 1], ["v", 0, "2*pi"]],
             "orientacion": -1}
    T = VE.gauss(["x^3", "y^3", "z^2"], [["z", 0, 1], ["r", 0, 1], ["t", 0, "2*pi"]],
                 "cilindricas", [lat, tapa, fondo])
    assert T.coinciden and abs(_v(T.lado_a[1]) - 2.5 * math.pi) < 1e-12
    # orientación equivocada en el lateral: se detecta, no se tapa
    lat_mal = dict(lat, orientacion=1)
    T = VE.gauss(["x^3", "y^3", "z^2"], [["z", 0, 1], ["r", 0, 1], ["t", 0, "2*pi"]],
                 "cilindricas", [lat_mal, tapa, fondo])
    assert T.coinciden is False


def test_calculadora_vectorial():
    import academic_core.domain.engineering.mathlab as ML

    r = ML.calcular(ML.Peticion("vectorial", {"calculo": "green", "campo": ["-y", "x"],
                                              "region": [["r", 0, 1], ["t", 0, "2*pi"]],
                                              "sistema": "polares", "borde": CIRC}))
    assert r.sello.verdict == "verificado" and "coinciden" in r.exacto
    r = ML.calcular(ML.Peticion("vectorial", {"calculo": "potencial",
                                              "campo": ["2*x*y", "x^2"]}))
    assert r.sello.verdict == "verificado" and "x^2*y" in r.exacto
    r = ML.calcular(ML.Peticion("vectorial", {"calculo": "flujo", "campo": ["x", "y", "z"],
                                              "superficie": ESFERA}))
    assert r.sello.verdict == "verificado" and "4*pi" in r.exacto
