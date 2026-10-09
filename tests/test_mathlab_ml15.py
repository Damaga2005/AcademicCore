# SPDX-License-Identifier: MIT
"""ML-15 (§4.17): fasores, onda plana, medios con pérdidas, polarización,
Jones, Fresnel y multicapa.

Propiedades de §11.3 (bloque 17): fasor frente a tiempo con las dos
convenciones; |E|² conservado por Jones unitaria; AR por dos fórmulas;
exacto frente a aproximado con su error relativo; Fresnel R + T = 1 y
r_p(θ_B) = 0; multicapa det = 1 por capa.
"""

from __future__ import annotations

import cmath
import math
from fractions import Fraction

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import polarizacion as P
from academic_core.domain.engineering.mathlab import verify as V


def pedir(entrada, conv=None):
    kw = {"convenciones": conv} if conv is not None else {}
    r = ML.calcular(ML.Peticion("polarizacion", entrada, **kw))
    assert C.validar_forma(r) == [], C.validar_forma(r)
    return r


# ---------------------------------------------------------------------------
# fasor ↔ tiempo y problema inverso
# ---------------------------------------------------------------------------

def test_suma_de_fasores():
    r = P.suma_fasores([(3, 0), (4, "pi/2")])
    assert r["A"] == pytest.approx(5.0) and r["phi"] == pytest.approx(math.atan2(4, 3))
    assert r["exacto"] == (Fraction(3), Fraction(4))


def test_problema_inverso():
    # x(t) = 8cos(ωt) + 5cos(ωt + 0,7): dos muestras determinan A y φ₁
    w, A0, A1, p1 = 2.4 * math.pi, 8.0, 5.0, 0.7
    x = lambda t: A0 * math.cos(w * t) + A1 * math.cos(w * t + p1)
    r = P.problema_inverso(w, [(0.0, x(0.0)), (0.2, x(0.2))], A0)
    assert r["A"] == pytest.approx(A1, rel=1e-9)
    assert r["phi"] == pytest.approx(p1, rel=1e-9)


def test_problema_inverso_muestras_medias_no_valen():
    with pytest.raises(Exception):
        P.problema_inverso(2 * math.pi, [(0.0, 1.0), (0.5, 1.0)], 0)


def test_fasor_tiempo_con_las_dos_convenciones():
    for t in (0.0, 0.1, 0.37):
        a = P.senal_tiempo(5, 0.7, 2 * math.pi, t, "cos", "+")
        b = P.senal_tiempo(5, -0.7, 2 * math.pi, t, "cos", "-")
        assert a == pytest.approx(b)
    r = pedir({"calculo": "convenciones_fasor", "A": 5, "fase": "pi/4"})
    assert r.sello.verdict == V.VERIFIED


def test_fasor_calculadora():
    r = pedir({"calculo": "fasor", "suma": [[8, 0], [2, "pi/3"]], "omega": "2*pi"})
    assert r.sello.verdict == V.VERIFIED and "9.16" in r.exacto


# ---------------------------------------------------------------------------
# onda plana
# ---------------------------------------------------------------------------

def test_onda_plana_k_eta_poynting():
    r = P.onda_plana([1, 0], 1, "3e8")
    assert r["k"] == pytest.approx(2 * math.pi * 3e8 / P.C0, rel=1e-9)
    assert r["eta"] == pytest.approx(376.73, rel=1e-4)
    assert r["S"] == pytest.approx(1 / (2 * r["eta"]), rel=1e-12)
    Hx, Hy, Hz = r["H"]
    assert (Hx, Hy, Hz) == pytest.approx((0j, 1 / r["eta"], 0j))


def test_onda_plana_sensor_circular_y_desplazado():
    r = P.onda_plana([2, 0], "1.5", "3e8",
                     sensor={"forma": "circulo", "R": 1, "desplazamiento": [3, 4]})
    assert r["P"] == pytest.approx(r["S"] * math.pi, rel=1e-12)
    assert any("desplazamiento" in a for a in r["avisos"])


def test_onda_no_transversal_se_rechaza():
    with pytest.raises(Exception):
        P.onda_plana([1, 0, 1], 1, "3e8", direccion=(0, 0, 1))


# ---------------------------------------------------------------------------
# medios con pérdidas: exacto frente a aproximado
# ---------------------------------------------------------------------------

def test_medios_buen_dielectrico_con_error():
    r = P.medios("4", f="1e9", tand="0.001")
    assert r["aprox"]["cual"] == "buen dieléctrico"
    assert r["error_rel"] < 1e-3
    assert r["alfa"] == pytest.approx(r["aprox"]["alfa"], rel=1e-3)


def test_medios_buen_conductor():
    r = P.medios("1", f="1e9", sigma="5.8e7")
    assert r["aprox"]["cual"] == "buen conductor"
    assert abs(r["alfa"] - r["beta"]) / r["alfa"] < 0.05


def test_medios_intermedio_sin_aproximacion():
    r = P.medios("4", f="1e9", tand="1")
    assert r["aprox"] is None


def test_espesor_para_dB():
    assert P.espesor_para_dB(1.0, "8.685889638") == pytest.approx(1.0, rel=1e-6)


def test_medios_calculadora():
    r = pedir({"calculo": "medios", "eps_r": 4, "f": "1e9",
               "tand": "0.001", "X_dB": 20})
    assert r.sello.verdict == V.VERIFIED and "buen dieléctrico" in r.exacto


# ---------------------------------------------------------------------------
# polarización: AR por dos fórmulas, Stokes, mano
# ---------------------------------------------------------------------------

def test_lineal_circular_y_eliptica():
    assert P.clasifica(1, 0, 0)["tipo"] == "lineal"
    assert P.clasifica(2, 2, 0)["tipo"] == "lineal"
    assert P.clasifica(1, 1, "-pi/2")["tipo"].startswith("circular derecha")
    assert P.clasifica(1, 1, "pi/2")["tipo"].startswith("circular izquierda")
    e = P.clasifica(2, 1, "pi/3")
    assert e["tipo"] == "elíptica" and e["AR"] == pytest.approx(2.484, rel=1e-3)


def test_AR_por_svd_y_por_tan_chi():
    for Ax, Ay, d in ((3, 1, "pi/6"), (1, 2, "-pi/3"), (5, 5, "pi/4")):
        r = P.clasifica(Ax, Ay, d)  # discrepa si las dos fórmulas difieren
        assert r["AR"] >= 1.0


def test_stokes_totalmente_polarizada():
    s = P.stokes(1, 1j)
    assert s[1] ** 2 + s[2] ** 2 + s[3] ** 2 == pytest.approx(s[0] ** 2)


def test_campo_nulo_sin_polarizacion():
    with pytest.raises(Exception):
        P.clasifica(0, 0, 0)


# ---------------------------------------------------------------------------
# Jones: unitariedad, Malus, cascada y diseño
# ---------------------------------------------------------------------------

def test_cuarto_de_onda_lineal_a_circular():
    Q = P.retardador("pi/2", "pi/4")
    r = P.cascada([Q], (1 + 0j, 0j))
    c = P.clasifica(abs(r["salida"][0]), abs(r["salida"][1]),
                    cmath.phase(r["salida"][1]) - cmath.phase(r["salida"][0]))
    assert c["tipo"].startswith("circular")
    assert r["pot_out"] == pytest.approx(r["pot_in"], rel=1e-12)


def test_media_onda_gira_la_lineal():
    H = P.retardador("pi", "pi/8")
    r = P.cascada([H], (1 + 0j, 0j))
    assert abs(r["salida"][0]) == pytest.approx(math.cos(math.pi / 4), rel=1e-9)
    assert abs(r["salida"][1]) == pytest.approx(math.sin(math.pi / 4), rel=1e-9)


def test_malus():
    J = P.polarizador("pi/3")
    r = P.cascada([J], (1 + 0j, 0j))
    assert r["pot_out"] == pytest.approx(0.25, rel=1e-9)


def test_jones_conserva_la_energia():
    Q = P.retardador("pi/3", "pi/5")
    H = P.retardador("pi", "pi/7")
    r = P.cascada([Q, H], (complex(1, 1), complex(0, 2)))
    assert r["pot_out"] == pytest.approx(r["pot_in"], rel=1e-9)


def test_diseno_AR_373_eje_45():
    r = P.disenar_cadena("3.73", "pi/4")
    assert abs(math.log(r["AR"] / 3.73)) < 0.02
    assert min(abs(r["psi"] - math.pi / 4), math.pi - abs(r["psi"] - math.pi / 4)) < 1 / 60


def test_plf_y_malus():
    assert P.plf([1, 0], [1, 0]) == pytest.approx(1.0)
    assert P.plf([1, 0], [0, 1]) == pytest.approx(0.0)
    assert P.plf([1, 0], [math.cos(0.4), math.sin(0.4)]) == pytest.approx(
        math.cos(0.4) ** 2, rel=1e-9)


# ---------------------------------------------------------------------------
# Fresnel: R + T = 1, Brewster, incidencia normal
# ---------------------------------------------------------------------------

def test_fresnel_normal_exacta():
    r = P.fresnel(1, "1.5", 0, "s")
    assert r["r"] == pytest.approx(-0.2)
    assert r["R"] == pytest.approx(0.04) and r["T"] == pytest.approx(0.96)


def test_brewster_anula_rp():
    th_b = P.angulos(1, "1.5")["brewster"]
    assert th_b == pytest.approx(math.atan(1.5), rel=1e-12)
    assert P.fresnel(1, "1.5", th_b, "p")["R"] < 1e-12


def test_reflexion_total_evanescente():
    assert P.angulos("1.5", 1)["critico"] == pytest.approx(math.asin(1 / 1.5))
    r = P.fresnel("1.5", 1, 1.0, "s")
    assert r["evanescente"] and r["R"] == pytest.approx(1.0)
    assert r["T"] == pytest.approx(0.0)


def test_T_no_es_t_cuadrado():
    r = P.fresnel(1, "1.5", 0.5, "s")
    assert abs(r["T"] - abs(r["t"]) ** 2) > 1e-6


def test_fresnel_calculadora():
    r = pedir({"calculo": "fresnel", "n1": 1, "n2": "1.5",
               "theta_i": 0, "pol": "s"})
    assert r.sello.verdict == V.VERIFIED and "R = 0.04" in r.exacto


# ---------------------------------------------------------------------------
# multicapa: det = 1, R + T = 1, antirreflejante
# ---------------------------------------------------------------------------

def test_multicapa_una_capa_reproduce_fresnel():
    # sin capas intermedias: la pila es la interfaz directa 1 → 1.5
    m = P.multicapa([1, "1.5"], [], 1, 0.0, "s")
    f = P.fresnel(1, "1.5", 0, "s")
    assert m["R"] + m["T"] == pytest.approx(1.0)
    assert m["R"] == pytest.approx(f["R"], rel=1e-9) == pytest.approx(0.04)


def test_antirreflejante_anula_R():
    ar = P.antirreflejante(1, "2.25")
    assert ar["n_f"] == pytest.approx(1.5)
    m = P.multicapa([1, str(ar["n_f"]), "2.25"], [str(ar["d_sobre_lambda"])],
                    1, 0.0, "s")
    assert m["R"] < 1e-12 and m["T"] == pytest.approx(1.0)


def test_multicapa_calculadora():
    r = pedir({"calculo": "multicapa", "ns": [1, "1.5", 1],
               "ds": ["0.1"], "lambda0": 1})
    assert r.sello.verdict == V.VERIFIED


# ---------------------------------------------------------------------------
# contrato
# ---------------------------------------------------------------------------

def test_polarizacion_pasa_el_contrato():
    for entrada in ({"calculo": "fasor", "suma": [[1, 0]]},
                    {"calculo": "polarizacion", "Ax": 1, "Ay": 1,
                     "delta": "pi/2"},
                    {"calculo": "fresnel", "n1": 1, "n2": 2}):
        assert C.validar_forma(pedir(entrada)) == []
