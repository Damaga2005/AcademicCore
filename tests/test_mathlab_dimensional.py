# SPDX-License-Identifier: MIT
"""ML-12: análisis dimensional como comprobador de fórmulas y de constantes."""
from __future__ import annotations

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import dimensional as DM

L = DM.leer
ELECTRICAS = {"P": "W", "V": "V", "R": "Ω", "t": "s", "C": "F", "I": "A", "K": "H"}


def _calc(**entrada):
    return ML.calcular(ML.Peticion("dimensional", entrada))


def test_unidades_y_base():
    assert L("kg*m/s^2") == L("N") == L("[M L T^-2]")
    assert L("V/A") == L("Ω") and L("Wb/m^2") == L("T") and L("kPa") == L("Pa")
    assert L("s^(1/2)").texto() == "T¹ᐟ²"


@pytest.mark.parametrize("ecuacion", [
    "P = V^2/R", "P = V*I", "V = V*exp(-t/(R*C))", "t = K/R", "t = sqrt(K*C)",
])
def test_formulas_homogeneas(ecuacion):
    r = _calc(ecuacion=ecuacion, dimensiones=ELECTRICAS)
    assert r.exacto.startswith("homogénea") and r.avisos


@pytest.mark.parametrize("ecuacion,trozo", [
    ("V = V*exp(-t/R)", "exp"),
    ("P = V*R", "≠"),
    ("P = V + I", "se suman"),
    ("P = V^t", "exponente"),
])
def test_formulas_que_fallan_dicen_donde(ecuacion, trozo):
    r = _calc(ecuacion=ecuacion, dimensiones=ELECTRICAS)
    assert r.exacto.startswith("NO homogénea") and trozo in r.exacto


@pytest.mark.parametrize("ecuacion,incognita,dims,esperado", [
    ("F = G*m1*m2/r^2", "G", {"F": "N", "m1": "kg", "m2": "kg", "r": "m"}, "M⁻¹·L³·T⁻²"),
    ("E = h*f", "h", {"E": "J", "f": "Hz"}, "M·L²·T⁻¹"),
    ("F = k*x", "k", {"F": "N", "x": "m"}, "M·T⁻²"),
    ("T = 2*pi*sqrt(l/g)", "g", {"T": "s", "l": "m"}, "L·T⁻²"),
])
def test_dimension_de_una_constante(ecuacion, incognita, dims, esperado):
    assert _calc(ecuacion=ecuacion, dimensiones=dims, incognita=incognita).exacto == \
        f"[{incognita}] = {esperado}"


def test_falta_una_dimension():
    with pytest.raises(Exception, match="MISSING_DIMENSION"):
        _calc(ecuacion="P = V*I", dimensiones={"P": "W", "V": "V"})


def test_nombres_de_varias_letras_no_se_parten():
    dims = {"Vcc": "V", "Rc": "Ω", "Ic": "A", "Lb": "H", "tau": "s"}
    assert _calc(ecuacion="Ic = Vcc/Rc", dimensiones=dims).exacto.startswith("homogénea")
    assert _calc(ecuacion="tau = Lb/Rc", dimensiones=dims).exacto.startswith("homogénea")
    assert _calc(ecuacion="F = G*m1*m2/r^2", incognita="G",
                 dimensiones={"F": "N", "m1": "kg", "m2": "kg", "r": "m"}).exacto == \
        "[G] = M⁻¹·L³·T⁻²"
    # undeclared, «xy» still means x·y
    import academic_core.domain.engineering.mathlab.mvexpr as mx
    assert mx.variables(mx.parse("xy")) == {"x", "y"}
