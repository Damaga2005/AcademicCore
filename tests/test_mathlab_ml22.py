# SPDX-License-Identifier: MIT
"""ML-22 (§4.19): física auxiliar — U(x), gas ideal (opcional), Kepler,
Maxwell-Boltzmann/Planck/Stefan (opcional).

Propiedades de §11.3 (bloque 19): periodo por RK4 = cuadratura de U(x);
Kepler por sustitución y e = 0 da el círculo; ΔS por dos caminos reversibles.
"""

from __future__ import annotations

import math

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import fisica as F
from academic_core.domain.engineering.mathlab import verify as V


def pedir(entrada):
    r = ML.calcular(ML.Peticion("fisica", entrada))
    assert C.validar_forma(r) == [], C.validar_forma(r)
    return r


# ---------------------------------------------------------------------------
# U(x)
# ---------------------------------------------------------------------------

def test_equilibrios_doble_pozo():
    r = F.equilibrios({"tipo": "poli", "coef": [0, 0, -1, 1]})
    xs = sorted(q["x"] for q in r["equilibrios"])
    assert xs == pytest.approx([0.0, 2 / 3])
    est = {round(q["x"], 6): q["estabilidad"] for q in r["equilibrios"]}
    assert est[0.0] == "inestable" and est[round(2 / 3, 6)] == "estable"


def test_omega_armonica_exacta():
    # U = 2x², m = 1: ω = 2
    r = F.oscilacion({"tipo": "poli", "coef": [0, 0, 2], "m": 1}, 3)
    assert r["omega"] == pytest.approx(2.0)
    assert r["T"] == pytest.approx(math.pi, rel=1e-3)
    assert r["T_armonico"] == pytest.approx(math.pi, rel=1e-9)


def test_periodo_cuadratura_es_rk4():
    r = F.oscilacion({"tipo": "poli", "coef": [0, 0, 2, 0, 1], "m": 1}, 3)
    assert r["T"] == pytest.approx(2.384, rel=1e-3)
    assert r["v_max"] == pytest.approx(math.sqrt(6), rel=1e-12)


def test_cos_periodica():
    r = F.oscilacion({"tipo": "cos", "U0": 2, "a": 1, "m": 1}, 1.5)
    assert r["omega"] == pytest.approx(2 * math.pi, rel=1e-9)
    assert r["T"] > r["T_armonico"]  # cerca de la barrera, el periodo crece


def test_tabla_interpola_con_aviso():
    r = F.equilibrios({"tipo": "tabla",
                       "puntos": [[0, 0], [4, 80], [8, 0], [12, -80], [16, 0]]},
                      x0=-10, x1=20)
    assert len(r["equilibrios"]) >= 1


def test_expr_racional():
    r = F.equilibrios({"tipo": "expr", "expr": "-2*x/(x^2+1)"}, x0=-5, x1=5)
    xs = sorted(q["x"] for q in r["equilibrios"])
    assert xs == pytest.approx([-1.0, 1.0], abs=1e-6)


def test_fuerza_dada():
    # F = 6x(3−x), m = 30 g: x0 = 3 estable, ω = √(18/0.03) ≈ 24.5
    r = F.oscilacion({"tipo": "fuerza", "coef": [0, 18, -6], "m": "0.03"},
                     "-20", x_eq=3)
    assert r["omega"] == pytest.approx(24.4949, rel=1e-3)


def test_pozo_doble_confinado():
    # U = 6(x⁴−2x²), m = 3: mínimos ±1 (U = −6), ω = 4, T finita bajo la barrera
    r = F.oscilacion({"tipo": "poli", "coef": [0, 0, -12, 0, 6], "m": 3},
                     "-0.5", x_eq=1)
    assert r["omega"] == pytest.approx(4.0, rel=1e-9)
    assert r["T"] > r["T_armonico"] > 0


def test_homoclinica_se_niega():
    # E = 0 en la barrera: periodo infinito, se dice (vmax y alcance sí valen)
    with pytest.raises(Exception, match="homocl"):
        F.oscilacion({"tipo": "poli", "coef": [0, 0, -12, 0, 6], "m": 3},
                     0, x_eq=1)


def test_gas_isocoro():
    r = F.gas_proceso({"tipo": "isocoro", "n": 1, "V1": 2, "V2": 2,
                       "T1": 300, "T2": 400})
    assert r["W"] == 0.0
    assert r["dU"] == pytest.approx(20.785 * 100)
    assert r["dS"] == pytest.approx(20.785 * math.log(4 / 3), rel=1e-9)


def test_muelle_gas():
    assert F.muelle_gas(3, 1)["omega"] == pytest.approx(math.sqrt(9.81 / 3))
    assert F.muelle_gas(3, "1.4")["omega"] == pytest.approx(math.sqrt(1.4 * 9.81 / 3))


def test_orbita_elipse():
    r = F.orbita_elipse(2, 6, 2, E="-0.75", L=6)
    assert r["C"] == pytest.approx(6.0, rel=1e-9)
    assert r["vp"] == pytest.approx(1.5, rel=1e-9)
    assert r["va"] == pytest.approx(0.5, rel=1e-9)


def test_potencial_2d():
    r = F.potencial_2d("x*y^2", [2, 3], [2, 0])
    assert r["W"] == pytest.approx(18.0, rel=1e-6)


def test_peralte_cono_talud():
    import math as _m
    p = F.peralte(100, v=20)
    assert p["theta"] == pytest.approx(_m.atan(400 / (9.81 * 100)), rel=1e-12)
    c = F.pendulo_conico(1, omega=4)
    assert c["theta"] == pytest.approx(_m.acos(9.81 / 16), rel=1e-12)
    assert F.pendulo_conico(1, omega=1)["theta"] == 0.0
    t = F.deslice_esfera("2.5", 0)
    assert t["theta_c"] == pytest.approx(_m.acos(2 / 3), rel=1e-12)


def test_choque_cm_inercia_rodadura():
    c = F.choque_1d(1, 2, 3, 0, 1)
    assert (c["v1p"], c["v2p"]) == pytest.approx((-1.0, 1.0))
    assert c["dE"] == pytest.approx(0.0, abs=1e-12)
    g = F.centro_masas([[1, 0, 0], [1, 2, 0], [2, 0, 4]])
    assert (g["X"], g["Y"]) == (0.5, 2.0)
    assert F.inercia("esfera", 3, "0.2")["I"] == pytest.approx(0.4 * 3 * 0.04)
    assert F.steiner(1.0, 2.0, 3.0)["I"] == pytest.approx(19.0)
    v = F.rodadura("0.5", 1, 1, 2)["v"]
    assert v == pytest.approx((2 * 9.81 * 2 / 1.5) ** 0.5, rel=1e-12)


def test_conduccion_boltzmann():
    assert F.conduccion(401, "1e-4", 50, "0.12")["I"] == pytest.approx(
        401 * 1e-4 * 50 / 0.12)
    r = F.boltzmann_niveles("1e10", "0.5", 350)
    assert r["N_exc"] == pytest.approx(631.4, rel=1e-2)


def test_sin_minimo_no_hay_oscilacion():
    with pytest.raises(Exception):
        F.oscilacion({"tipo": "poli", "coef": [0, 1], "m": 1}, 5)


def test_oscilacion_calculadora():
    r = pedir({"calculo": "oscilacion",
               "potencial": {"tipo": "poli", "coef": [0, 0, 2], "m": 1},
               "E": 3})
    assert r.sello.verdict == V.VERIFIED and "2.449" in r.exacto


# ---------------------------------------------------------------------------
# gas ideal
# ---------------------------------------------------------------------------

def test_gas_lineal():
    r = F.gas_proceso({"tipo": "lineal", "n": 1, "V1": 1, "V2": 2,
                       "p0": 1e5, "p1": 2e5})
    assert r["W"] == pytest.approx(-1.5e5)
    assert r["Tmax"] >= r["T2"] >= r["T1"]


def test_gas_isotermo_sin_dU():
    r = F.gas_proceso({"tipo": "isotermo", "n": 1, "T": 300, "V1": 1, "V2": 2})
    assert r["dU"] == pytest.approx(0.0, abs=1e-9)
    assert r["W"] == pytest.approx(-8.31446261815324 * 300 * math.log(2), rel=1e-9)


def test_gas_adiabatico_sin_entropia():
    # expansión al doble con γ = 1.4 (Cv = R/(γ−1) coherente): T₂ = T₁/2^0.4, ΔS = 0
    R = F.R_GAS
    r = F.gas_proceso({"tipo": "adiabatico", "n": 1, "T1": 400, "Cv": R / 0.4,
                       "V1": 1, "V2": 2, "gamma": "1.4"})
    assert r["T2"] == pytest.approx(400 / 2 ** 0.4, rel=1e-9)
    assert r["dS"] == pytest.approx(0.0, abs=1e-9)


def test_gas_mezcla_mono_di():
    # mismo V y p (n = pV/RT difiere): Teq = 336 K, no (3TA+5TB)/8 = 345
    R = F.R_GAS
    r = F.gas_mezcla([{"n": 1 / (R * 420), "Cv": 1.5 * R, "T": 420},
                      {"n": 1 / (R * 300), "Cv": 2.5 * R, "T": 300}])
    assert r["Teq"] == pytest.approx(336.0, rel=1e-9)


def test_gas_ciclo_clausius_y_rendimiento():
    r = F.gas_ciclo([[1e5, 1], [2e5, 1], [2e5, 2], [1e5, 2], [1e5, 1]])
    assert r["W"] == pytest.approx(-1e5)
    assert r["eta"] == pytest.approx(0.10527, rel=1e-3)


def test_gas_calculadora():
    r = pedir({"calculo": "gas",
               "proceso": {"tipo": "lineal", "n": 1, "V1": 1, "V2": 2,
                           "p0": 1e5, "p1": 2e5}})
    assert r.sello.verdict == V.VERIFIED


# ---------------------------------------------------------------------------
# Kepler y órbitas
# ---------------------------------------------------------------------------

def test_kepler_sustitucion_y_circulo():
    assert F.kepler(1, 0.5)["E"] == pytest.approx(1.4987, rel=1e-4)
    assert F.kepler(2, 0)["E"] == pytest.approx(2.0)


def test_orbita_kepler3():
    r = F.orbita("6.671e6")
    assert r["T"] == pytest.approx(5420, rel=0.02)
    assert r["T"] ** 2 / 6.671e6 ** 3 == pytest.approx(
        4 * math.pi ** 2 / (6.67430e-11 * 5.972e24), rel=1e-9)


def test_visibilidad():
    r = F.visibilidad("6.371e6", "5e5")
    assert r["theta"] == pytest.approx(math.acos(6.371e6 / 6.871e6), rel=1e-12)
    assert r["fraccion"] == pytest.approx(5e5 / (2 * 6.871e6), rel=1e-12)


# ---------------------------------------------------------------------------
# MB, Planck, Stefan
# ---------------------------------------------------------------------------

def test_maxwell_boltzmann():
    r = F.maxwell_boltzmann("9.11e-31", 300)
    assert r["v_p"] == pytest.approx(math.sqrt(2 * F.K_B * 300 / 9.11e-31),
                                    rel=1e-9)
    assert r["v_med"] < r["v_rms"] and r["v_p"] < r["v_med"]


def test_planck_y_stefan():
    r = F.planck_integral()
    assert r["integral"] == pytest.approx(math.pi ** 4 / 15, rel=1e-4)
    assert r["sigma"] == pytest.approx(5.670374419e-8, rel=1e-6)


# ---------------------------------------------------------------------------
# contrato
# ---------------------------------------------------------------------------

def test_fisica_pasa_el_contrato():
    for entrada in ({"calculo": "equilibrio"},
                    {"calculo": "kepler", "M": 1, "e": "0.1"},
                    {"calculo": "visibilidad"}):
        assert C.validar_forma(pedir(entrada)) == []
