# SPDX-License-Identifier: MIT
"""ML-14 (§4.15): señales y sistemas deterministas.

Propiedades de §11.3 (bloque 15): ∫y = ∫x·∫h; Σy = Σx·Σh; Parseval en
tiempo y frecuencia; Wiener-Khinchin; circular = lineal con N ≥ L1+L2−1;
la cascada eco + inverso devuelve la entrada; tres señales base distintas
dan los mismos c_k.
"""

from __future__ import annotations

import cmath
import math
from fractions import Fraction

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import senales as S
from academic_core.domain.engineering.mathlab import verify as V


def pedir(entrada):
    r = ML.calcular(ML.Peticion("senales", entrada))
    assert C.validar_forma(r) == [], C.validar_forma(r)
    return r


# ---------------------------------------------------------------------------
# biblioteca y eje
# ---------------------------------------------------------------------------

def test_biblioteca_rect_tri_exp():
    r = S.biblioteca([{"tipo": "rect", "A": 2, "t0": 0, "T": 3}])
    assert r["integral"] == Fraction(6) and r["energia"] == Fraction(12)
    r = S.biblioteca([{"tipo": "tri", "A": 3, "t0": 1, "T": 2}])
    assert r["integral"] == Fraction(6) and r["energia"] == Fraction(12)
    r = S.biblioteca([{"tipo": "exp", "A": 2, "t0": 0, "T": 3}])
    assert r["integral"] == Fraction(6) and r["energia"] == Fraction(6)


def test_biblioteca_avisa_solape():
    r = S.biblioteca([{"tipo": "rect", "A": 1, "t0": 0, "T": 2},
                      {"tipo": "rect", "A": 1, "t0": 0, "T": 2}])
    assert r["solapan"] is True


def test_eje_escala_energia():
    out = S.transforma_eje({"tipo": "rect", "A": 2, "t0": 1, "T": 4}, 2, 0)
    assert out["t0"] == Fraction(1, 2) and out["T"] == Fraction(2)
    with pytest.raises(Exception):
        S.transforma_eje({"tipo": "rect"}, 0, 0)


def test_tf_rect_y_tri_en_cero():
    assert abs(S.tf_rect(0.0, 2, 0, 3) - 6.0) < 1e-12
    assert abs(S.tf_tri(0.0, 1, 0, 2) - 2.0) < 1e-12
    assert abs(S.tf_exp(0.0, 1, 0, 2) - 2.0) < 1e-12


# ---------------------------------------------------------------------------
# convolución analógica: ∫y = ∫x·∫h
# ---------------------------------------------------------------------------

def test_conv_rect_rect_da_triangulo():
    r = S.convolucion([S.rect(-1, 1, 1)], [S.rect(-1, 1, 1)])
    assert r["rupturas"] == [Fraction(-2), Fraction(0), Fraction(2)]
    assert r["integral"] == Fraction(4)
    assert r["tramos"][0]["expr"] == "2 + 1·t"
    assert r["tramos"][1]["expr"] == "2 + -1·t"


def test_conv_rect_exp_integral():
    r = S.convolucion([S.rect(0, 1, 1)], [S.exp_causal(0, 2, 1)])
    assert r["integral"] == Fraction(2)


def test_conv_exp_exp_integral():
    r = S.convolucion([S.exp_causal(0, 1, 1)], [S.exp_causal(0, 2, 1)])
    assert r["integral"] == Fraction(2)


def test_conv_delta_desplaza_y_escala():
    r = S.convolucion([{"delta": 3, "t0": 5}], [S.rect(0, 1, 2)])
    assert r["integral"] == Fraction(6)
    assert r["desplazamiento_deltas"] == Fraction(5)


def test_conv_ventana_conserva_integral():
    r = S.ventana_movil([S.rect(0, 2, 1)], 1)
    assert r["integral"] == Fraction(2)


def test_conv_calculadora_verificada():
    r = pedir({"calculo": "convolucion", "x": {"trozos": [[-1, 1, 1]]},
               "h": {"trozos": [[-1, 1, 1]]}})
    assert r.sello.verdict == V.VERIFIED and "4" in str(r.exacto)


# ---------------------------------------------------------------------------
# digital: Σy = Σx·Σh; tres tramos
# ---------------------------------------------------------------------------

def test_conv_digital_longitud_y_sumas():
    r = S.conv_lineal([1, 2, 3], [1, 1])
    assert r["y"] == [Fraction(1), Fraction(3), Fraction(5), Fraction(3)]
    assert sum(r["y"]) == sum([1, 2, 3]) * sum([1, 1])


def test_conv_digital_dft_con_N_suficiente():
    r = pedir({"calculo": "conv_digital", "x": [1, 2, 3], "h": [1, 1]})
    assert r.sello.verdict == V.VERIFIED


def test_regimen_geometrico():
    r = S.salida_exp("1/2", [1, 0, 0])
    assert r["y"] == [Fraction(1), Fraction(1, 2), Fraction(1, 4)]


def test_regimen_divergente_se_rechaza():
    with pytest.raises(Exception):
        S.salida_exp(2, [1])


# ---------------------------------------------------------------------------
# periódicas: base, periodo, Parseval, tres bases
# ---------------------------------------------------------------------------

def test_periodo_mcm():
    assert S.periodo_comun(2, 3) == Fraction(6)
    assert S.periodo_comun("1/2", "1/3") == Fraction(1)


def test_ck_rect_paridad():
    # Π centrado de ancho 1 en T0 = 2: c_k = (1/2)sinc(k/2); pares nulos
    r = S.ck_base([{"tipo": "rect", "A": 1, "t0": 0, "T": 1}], 2, K=4)
    assert abs(r["ck"][0] - 0.5) < 1e-12
    assert abs(r["ck"][2]) < 1e-9 and abs(r["ck"][-2]) < 1e-9
    assert 2 in r["nulos"]


def test_tres_bases_dan_los_mismos_ck():
    una = S.ck_base([{"tipo": "rect", "A": 1, "t0": 0, "T": 2}], 4, K=3)
    dos = S.ck_base([{"tipo": "rect", "A": 1, "t0": "-1/2", "T": 1},
                     {"tipo": "rect", "A": 1, "t0": "1/2", "T": 1}], 4, K=3)
    tres = S.ck_base([{"tipo": "rect", "A": 1, "t0": 0, "T": 2}], 4, K=3)
    for k in una["ck"]:
        assert abs(una["ck"][k] - dos["ck"][k]) < 1e-9
        assert abs(una["ck"][k] - tres["ck"][k]) < 1e-12


def test_periodica_parseval_no_supera_tiempo():
    r = S.ck_base([{"tipo": "tri", "A": 1, "t0": 0, "T": 1}], 2, K=6)
    assert r["potencia"] <= r["potencia_tiempo"] * (1 + 1e-6) + 1e-9


def test_periodica_calculadora():
    r = pedir({"calculo": "periodica",
               "base": [{"tipo": "rect", "A": 1, "t0": 0, "T": 1}],
               "T0": 2, "K": 3})
    assert r.sello.verdict == V.VERIFIED


# ---------------------------------------------------------------------------
# energía, potencia, correlación, densidad
# ---------------------------------------------------------------------------

def test_energia_tramos():
    assert S.energia([S.rect(0, 2, 3)])["energia"] == Fraction(18)
    assert S.energia(S.tri(0, 2, 1))["energia"] == Fraction(4, 3)
    assert S.energia([S.exp_causal(0, 2, 1)])["energia"] == Fraction(1)


def test_potencia_sinusoide_y_eco():
    assert S.potencia_sinusoide(4) == Fraction(8)
    assert S.energia_eco(10, "1/2") == Fraction(50, 4)


def test_correlacion_rect_triangulo_y_schwarz():
    r = S.correlacion_rect(2, 3)
    assert r["r"][0.0] == pytest.approx(12.0)
    assert all(v <= r["r"][0.0] * (1 + 1e-9) for v in r["r"].values())


def test_correlacion_exp_y_retardo():
    r = S.correlacion_exp(1, 2)
    assert r["r"][0.0] == pytest.approx(1.0)
    assert S.retardo_por_pico({-1.0: 0.5, 0.0: 2.0, 3.0: 1.0}) == 0.0


def test_densidad_es_wiener_khinchin():
    Xs = [1 + 1j, 2 + 0j]
    assert S.densidad_desde_tf(Xs) == pytest.approx([2.0, 4.0])


# ---------------------------------------------------------------------------
# DTFT
# ---------------------------------------------------------------------------

def test_dtft_pulso_maximo_y_ceros():
    assert S.dtft_pulso(0.0, 4) == 4.0
    assert abs(S.dtft_pulso(0.25, 4)) < 1e-9  # cero en k/L = 1/4
    S.comprobar_dtft("1/2", 4)


def test_dtft_exp_modulo():
    assert abs(S.dtft_exp(0.0, "1/2") - 2.0) < 1e-12
    assert abs(S.modulo_cuadrado_exp("1/2", 0.0) - 4.0) < 1e-12
    assert abs(S.dtft_delta(0.3, 2) - cmath.exp(-1j * 2 * math.pi * 0.3 * 2)) < 1e-12


def test_dtft_sin_sumar_no_converge():
    with pytest.raises(Exception):
        S.dtft_exp(0.0, 2)


# ---------------------------------------------------------------------------
# DFT: X[0], hermítica, Parseval, circular = lineal
# ---------------------------------------------------------------------------

def test_dft_propiedades():
    r = S.comprobar_dft([1.0, 2.0, 3.0, 4.0])
    assert abs(r["X"][0] - 10.0) < 1e-9
    assert abs(sum(v * v for v in [1, 2, 3, 4]) - r["energia"]) < 1e-12


def test_dft_retardo_circular_es_fase():
    x = [1.0, 0.0, 0.0, 0.0]
    X = S.dft(x)
    n0, N = 1, 4
    Y = S.dft([0.0, 1.0, 0.0, 0.0])
    for k in range(N):
        assert abs(Y[k] - X[k] * cmath.exp(-1j * 2 * math.pi * k * n0 / N)) < 1e-9


def test_circular_es_lineal_con_N_suficiente():
    r = S.lineal_vs_circular([1.0, 2.0, 3.0], [1.0, 1.0])
    assert r["N"] == 4 and r["y"] == [1.0, 3.0, 5.0, 3.0]


def test_dft_calculadora():
    r = pedir({"calculo": "dft", "x": [1, 2, 3, 4]})
    assert r.sello.verdict == V.VERIFIED


# ---------------------------------------------------------------------------
# eco, inverso y cascada
# ---------------------------------------------------------------------------

def test_eco_ceros_modulo():
    ceros = S.ceros_eco("1/2", 4)
    assert len(ceros) == 4
    assert all(abs(abs(z) - (0.5) ** 0.25) < 1e-12 for z in ceros)
    assert abs(S.modulo_eco("1/2", 4, 0.0) - 2.25) < 1e-12


def test_inverso_inestable_se_rechaza():
    with pytest.raises(Exception):
        S.inverso_eco(2, 4)


def test_cascada_devuelve_la_entrada():
    r = S.cascada_eco("1/2", 4, [1, 2, 3])
    assert r["resto"] < 1e-6
    r = pedir({"calculo": "cascada", "a": "1/2", "L": 4, "x": [1, 2, 3]})
    assert r.sello.verdict == V.VERIFIED


# ---------------------------------------------------------------------------
# contrato y convenciones
# ---------------------------------------------------------------------------

def test_senales_pasa_el_contrato():
    for entrada in ({"calculo": "biblioteca",
                     "pulsos": [{"tipo": "rect", "A": 1, "t0": 0, "T": 2}]},
                    {"calculo": "dtft", "tipo": "pulso", "L": 4,
                     "F": [0, 0.25]},
                    {"calculo": "eco", "a": "1/2", "L": 4, "F": 0}):
        r = pedir(entrada)
        assert C.validar_forma(r) == []
