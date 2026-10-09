# SPDX-License-Identifier: MIT
"""ML-16 (§4.18): campos y ondas — carga, Gauss, conductores, Maxwell por
sustitución, perfiles, Coulomb/Biot-Savart, condensadores, Poynting, Friis.

Propiedades de §11.3 (bloque 18): ∇·E = ρ/ε₀ por regiones; flujo por 6
caras = Gauss; Maxwell por sustitución; energía por dos fórmulas; análisis
dimensional (homogeneidad en a); Biot-Savart frente a Ampère y límite z ≫ R;
Friis en lineal frente a dB.
"""

from __future__ import annotations

import math
from fractions import Fraction

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import campos as F
from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import verify as V


def pedir(entrada):
    r = ML.calcular(ML.Peticion("campos", entrada))
    assert C.validar_forma(r) == [], C.validar_forma(r)
    return r


# ---------------------------------------------------------------------------
# carga total
# ---------------------------------------------------------------------------

def test_carga_arco_completo():
    # λ = a·sen(θ/2) en el círculo: Q = 4aR
    assert F.carga_arco(2, 1.5)["Q"] == pytest.approx(12.0)


def test_arco_seno_m4_con_E_y_V():
    # semicírculo λ = a·sen(θ/4): Q = 2aR(2−√2), V₀ = KQ/R
    r = F.carga_arco(1, 2, 0, math.pi, 4)
    assert r["Q"] == pytest.approx(4 * (2 - math.sqrt(2)))
    assert r["V0"] == pytest.approx(F.K0 * r["Q"] / 2, rel=1e-12)
    assert r["Ex"] == pytest.approx(0.4552 * F.K0 / 2, rel=1e-3)
    assert r["Ey"] == pytest.approx(-0.7542 * F.K0 / 2, rel=1e-3)


def test_carga_cilindro_y_limite():
    assert F.carga_cilindro(1, 0, 2, 3)["Q"] == pytest.approx(2 * math.pi * 3 * 8 / 3)
    assert F.carga_cilindro(1, 1, 2, 3)["Q"] == pytest.approx(
        2 * math.pi * 3 * (8 - 1) / 3)


def test_carga_esfera():
    assert F.carga_esfera(1, 2, 2)["Q"] == pytest.approx(4 * math.pi * 32 / 5)


def test_carga_placa():
    assert F.carga_placa(3, 0, 2, 0, 1)["Q"] == pytest.approx(3 * 1 * 8 / 3)


def test_carga_homogenea_en_a():
    assert F.carga_esfera(2, 1, 0)["Q"] == pytest.approx(2 * F.carga_esfera(1, 1, 0)["Q"])


# ---------------------------------------------------------------------------
# Gauss
# ---------------------------------------------------------------------------

def test_gauss_esfera_empalme_y_energia():
    r = F.gauss_esfera("1e-9", "0.1")
    assert "8.98755" in r["E"]["fuera"] and r["W"] == pytest.approx(4.49e-8, rel=1e-3)


def test_gauss_rho_divergencia():
    r = F.gauss_esfera_rho(1, 2, 1)
    assert r["Q"] == pytest.approx(math.pi * 2 ** 4)


def test_gauss_cilindro_avisa_referencia():
    r = F.gauss_cilindro("1e-9")
    assert "ln" in r["V"]


def test_gauss_plano_dos_caras():
    r = F.gauss_plano("1e-9")
    assert r["E_mas"] == pytest.approx(-r["E_menos"])


# ---------------------------------------------------------------------------
# conductores
# ---------------------------------------------------------------------------

def test_concentricas_reparto():
    r = F.esferas_concentricas(1, 2, 3, "1e-9", "2e-9")
    assert r["q_interior_cascara"] == Fraction(-1, 10 ** 9)
    assert r["q_exterior"] == Fraction(3, 10 ** 9)
    assert r["V_R2"] == pytest.approx(r["V_R3"])


def test_concentricas_tierra_drena():
    r = F.esferas_concentricas(1, 2, 3, "1e-9", "2e-9", tierra=True)
    assert r["q_exterior"] == Fraction(0)
    assert r["V_R3"] == pytest.approx(0.0, abs=1e-6)


def test_concentricas_tierra_interior():
    # V(R₁) = 0 con Q₂ fija: Q₁ = −Q₂/R₃/(1/R₁−1/R₂+1/R₃) ≈ −10.71 nC
    r = F.esferas_concentricas("0.02", "0.05", "0.06", "10e-9", "30e-9",
                               tierra="interior")
    assert r["V_R1"] == pytest.approx(0.0, abs=1e-3)
    Q1 = float(r["q_exterior"]) - 30e-9
    assert Q1 == pytest.approx(-10.714e-9, rel=1e-3)


# ---------------------------------------------------------------------------
# V dado, Maxwell, completar
# ---------------------------------------------------------------------------

def test_v_dado_gauss_por_dos_lados():
    r = pedir({"calculo": "v_dado", "V": "x^2+y^2+4",
               "caja": [0, 1, 0, 1, 0, 1]})
    assert r.sello.verdict == V.VERIFIED


def test_maxwell_plana_da_c():
    r = F.maxwell_plana(3, "1e-8", 1, "3e8")
    assert r["c"] == pytest.approx(299792458.0, rel=1e-6)


def test_maxwell_plana_falsa_discrepa():
    # la solución oficial escribe c = 3,33×10⁻⁹ (= 1/c): el motor lo rechaza
    with pytest.raises(Exception):
        F.maxwell_plana(3, "1e-8", 1, "3.33e-9")
    with pytest.raises(Exception):
        F.maxwell_plana(3, "1e-8", 1, "1e8")


def test_guia_dispersion_y_corte():
    r = F.maxwell_guia(1, "0.1", "2e10")
    assert r["beta"] == pytest.approx(58.85, rel=1e-3)
    with pytest.raises(Exception):
        F.maxwell_guia(1, "0.1", "1e9")  # en corte: se dice, no se inventa


def test_completar_By():
    assert F.completar_By([[1, 0, "2"], [0, 1, "3"]])["By"] == [[0, 1, Fraction(-2)]]


# ---------------------------------------------------------------------------
# perfiles
# ---------------------------------------------------------------------------

def test_perfil_gauss_v_y_retardos():
    r = F.perfil_onda("gauss", 1, 2, 1, [0, 5])
    assert r["v"] == pytest.approx(0.5) and r["direccion"] == "+x"
    assert r["trazas"][1]["t_pico"] == pytest.approx(10.0)


def test_perfil_no_cumple_discrepa():
    with pytest.raises(Exception):
        F.perfil_onda("otra", 1, 2, 1, [0])


# ---------------------------------------------------------------------------
# Coulomb / Biot-Savart
# ---------------------------------------------------------------------------

def test_anillo_lejos_puntual():
    assert F.e_anillo("1e-9", 1, 100)["E"] == pytest.approx(
        F.K0 * 1e-9 / 100 ** 2, rel=1e-3)


def test_disco_cerca_plano():
    assert F.e_disco("1e-9", 10, "0.01")["E"] == pytest.approx(
        1e-9 / (2 * F.EPS0), rel=1e-3)


def test_espira_lejos_dipolo():
    assert F.b_espira(1, 1, 100)["B"] == pytest.approx(
        F.MU0 * math.pi / (2 * math.pi * 100 ** 3), rel=1e-3)


def test_hilo_ampere():
    assert F.b_hilo(1, 2)["B"] == pytest.approx(F.MU0 / (4 * math.pi), rel=1e-12)


def test_coaxial_corriente_parcial():
    r = F.b_coaxial(1, 1, 2, "1.5")
    assert r["I_enc"] == pytest.approx(1 - (2.25 - 1) / 3)
    assert r["B"] == pytest.approx(F.MU0 * r["I_enc"] / (2 * math.pi * 1.5))
    assert F.b_coaxial(1, 1, 2, 3)["B"] == 0.0
    assert F.b_coaxial(1, 1, 2, "0.5")["B"] == pytest.approx(F.MU0 / (2 * math.pi * 0.5))


def test_poligono_al_circulo():
    r = F.b_poligono(1, 1, 6)
    assert r["limite"] == pytest.approx(F.MU0 / 2, rel=1e-12)
    assert abs(r["B"] - r["limite"]) / r["limite"] < 0.1
    assert abs(F.b_poligono(1, 1, 1000)["B"] - r["limite"]) / r["limite"] < 1e-5


# ---------------------------------------------------------------------------
# condensadores, Faraday, Poynting
# ---------------------------------------------------------------------------

def test_condensadores():
    assert F.c_plano(1, 1, "0.01")["C"] == pytest.approx(F.EPS0 / 0.01)
    assert F.c_esferico(1, 1, 2)["C"] == pytest.approx(
        4 * math.pi * F.EPS0 / (1 - 1 / 2))
    assert F.c_cilindrico(1, 1, 1, 2)["C"] == pytest.approx(
        2 * math.pi * F.EPS0 / math.log(2))
    assert F.c_serie([1, 1])["C"] == pytest.approx(0.5)


def test_diel_plano_serie():
    r = F.diel_plano("1e-9", 2, [{"d": 1, "eps_r": 2}, {"d": 3, "eps_r": 4}])
    assert r["D"] == pytest.approx(0.5e-9)
    assert r["C"] == pytest.approx(1e-9 / (28.24 * 1 + 14.12 * 3), rel=1e-3)
    assert r["sigma_b"][0] == pytest.approx(-r["P"][0], rel=1e-12)


def test_mutua_lineal():
    assert F.mutua_solenoide_bobina(1000, 10, "0.1", 1, 0)["M"] == pytest.approx(
        4 * math.pi * 1e-7 * 100, rel=1e-12)


def test_arco_uniforme():
    # semicírculo uniforme: Q = λπR, Ey = −2Kλ
    import math as _m
    r = F.carga_arco("2", 4, 0, "3.141592653589793", densidad="uniforme")
    assert r["Q"] == pytest.approx(2 * 4 * _m.pi)
    assert r["Ex"] == pytest.approx(0.0, abs=1e-4)  # polvo float de π literal
    assert r["Ey"] == pytest.approx(-2 * F.K0 * 2, rel=1e-9)
    assert r["V0"] == pytest.approx(F.K0 * r["Q"] / 4, rel=1e-12)


def test_segmento_finito():
    import math as _m
    Q, L, d = 1e-9, 0.02, 0.05
    r = F.segmento(Q, L, d)
    assert r["E"] == pytest.approx(
        F.K0 * Q / (d * _m.sqrt(d * d + (L / 2) ** 2)), rel=1e-9)


def test_esfera_aislada():
    assert F.c_esferico(1, "6.4e6", "oo")["C"] == pytest.approx(
        4 * math.pi * F.EPS0 * 6.4e6, rel=1e-9)


def test_coaxial_macizo():
    r = F.b_coaxial(1, 1, 2, "0.5", central="macizo")
    assert r["B"] == pytest.approx(F.MU0 * 1 * 0.5 / (2 * math.pi * 1), rel=1e-12)


def test_coaxial_tres_radios():
    # tubo entre b = 2 y c = 3: I_enc = I − I(r²−b²)/(c²−b²)
    r = F.b_coaxial(1, 1, 2, "2.5", c=3)
    assert r["I_enc"] == pytest.approx(1 - (6.25 - 4) / (9 - 4))
    assert F.b_coaxial(1, 1, 2, 4, c=3)["B"] == 0.0
    assert F.b_coaxial(1, 1, 2, "1.5", c=3)["I_enc"] == pytest.approx(1.0)


def test_fuerza_espira_y_potencia():
    import math as _m
    Ih, Ie, a, b, x = 10.0, 1.0, 0.15, 0.08, 0.1
    r = F.fuerza_espira(Ih, Ie, a, b, x)
    assert r["F"] == pytest.approx(
        Ie * b * F.MU0 * Ih / (2 * _m.pi) * (1 / x - 1 / (x + a)), rel=1e-12)


def test_fuera_eje_en_eje_coincide():
    import math as _m
    r = F.b_espira_fuera_eje(7, "0.2", 0, "0.2", n=360)
    ref = F.b_espira(7, "0.2", "0.2")["B"]
    assert r["B"][2] == pytest.approx(ref, rel=1e-6)
    assert abs(r["B"][0]) < 1e-9 and abs(r["B"][1]) < 1e-9


def test_mutua_neumann_cuadrados():
    import math as _m
    L1 = [[-1, -1, 0], [1, -1, 0], [1, 1, 0], [-1, 1, 0]]
    L2 = [[-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]]
    r = F.mutua_neumann(L1, L2, n=24)
    assert r["M"] > 0 and r["M"] < 4 * _m.pi * 1e-7 * 8


def test_faraday_lenz():
    r = F.faraday(1, 50, 100, "0.01")
    assert r["fem_amp"] == pytest.approx(100 * 0.01 * 2 * math.pi * 50)


def test_poynting_balance():
    r = F.poynting_condensador(1, "0.1", "0.01", 2)
    assert r["flujo"] == pytest.approx(r["dU_dt"], rel=1e-12)


# ---------------------------------------------------------------------------
# antenas (G)
# ---------------------------------------------------------------------------

def test_friis_lineal_dB():
    r = F.friis(10, 20, 15, "0.1", 1000)
    assert r["Pr"] == pytest.approx(10 * 100 * 10 ** 1.5 * (0.1 / (4 * math.pi * 1000)) ** 2,
                                   rel=1e-9)


def test_array_N1_es_elemento():
    assert F.array_factores(1, "0.5", 1)["AF"] == pytest.approx(1.0)
    assert F.array_factores(4, "0.5", 1)["ancho"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# contrato
# ---------------------------------------------------------------------------

def test_campos_pasa_el_contrato():
    for entrada in ({"calculo": "carga", "tipo": "arco"},
                    {"calculo": "gauss", "tipo": "esfera"},
                    {"calculo": "friis", "Pt": 1, "Gt_dB": 0, "Gr_dB": 0,
                     "lam": 1, "R": 10}):
        assert C.validar_forma(pedir(entrada)) == []
