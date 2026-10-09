# SPDX-License-Identifier: MIT
"""ML-21 (bloque 14, G): interés, VAN/TIR, bonos, futuros, opciones, cartera.

Propiedades de §11.3: TAE = capitalización; VAN(TIR) = 0; saldo 0 tras n
cuotas; duración = −P′/P; paridad put-call; CRR → BS con n grande; vega > 0
⇒ σ implícita única; Σ definida positiva (Sylvester); 2Σw ortogonal al
espacio factible; MC dentro del intervalo exacto.
"""

from __future__ import annotations

import math

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import finanzas as F
from academic_core.domain.engineering.mathlab import verify as V


def pedir(entrada):
    r = ML.calcular(ML.Peticion("finanzas", entrada))
    assert C.validar_forma(r) == [], C.validar_forma(r)
    return r


def test_interes_y_tae():
    # r es la tasa NOMINAL anual repartida en m capitalizaciones (§4.14):
    # r = 12% anual con m = 12 → 1% mensual, C = 1000·1.01¹²
    r = F.interes(1000, "0.12", 1, "compuesto", 12)
    assert r["C"] == pytest.approx(1000 * 1.01 ** 12)
    assert r["TAE"] == pytest.approx(1.01 ** 12 - 1)
    assert F.interes(1000, "0.05", 1, "continuo")["C"] == pytest.approx(
        1000 * math.exp(0.05))
    assert F.interes(1000, "0.1", 2, "simple")["C"] == pytest.approx(1200.0)
    # en simple la TAE efectiva de un año es la propia tasa, no e^r − 1
    assert F.interes(1000, "0.1", 2, "simple")["TAE"] == pytest.approx(0.1)
    assert F.interes(1000, "0.1", 10, "compuesto")["regla72"] == pytest.approx(7.2)


def test_despejar_tiempo():
    t = F.despejar_tiempo(1000, 2000, "0.05")["t"]
    assert t == pytest.approx(math.log(2) / math.log(1.05))
    assert F.interes(1000, "0.05", t)["C"] == pytest.approx(2000.0, rel=1e-9)


def test_van_y_tir():
    F_ = [-1000, 500, 500, 500]
    assert F.van(F_, "0.05")["VAN"] == pytest.approx(
        sum(f / 1.05 ** t for t, f in enumerate(F_)))
    r = F.tir(F_)
    assert F.van(F_, r["TIR"])["VAN"] == pytest.approx(0.0, abs=1e-6)
    assert r["cambios"] == 1
    # sin cambio de signo no hay TIR que encerrar: se niega con motivo
    with pytest.raises(Exception) as exc:
        F.tir([100, 200, 300])
    assert "UNSUPPORTED" in str(exc.value)


def test_anualidad():
    r = F.anualidad(10000, "0.05", 10)
    c = r["cuota"]
    # segundo camino: el saldo tras n cuotas es 0
    saldo = 10000.0
    for _ in range(10):
        saldo = saldo * 1.05 - c
    assert abs(saldo) < 1e-6
    assert r["total"] == pytest.approx(c * 10)


def test_bono():
    F_ = [100, 0, 0, 110]
    r = F.bono(F_, "0.05")
    P = sum(f / 1.05 ** t for t, f in enumerate(F_))
    assert r["P"] == pytest.approx(P)
    h = 1e-6
    P2 = sum(f / (1.05 + h) ** t for t, f in enumerate(F_))
    assert r["modificada"] == pytest.approx(-(P2 - P) / h / P, rel=1e-4)


def test_bono_sin_precio_se_rechaza():
    # con flujos vacíos o de precio 0 no hay duración: se dice con motivo en
    # vez de dividir por cero (ZeroDivisionError) o devolver ceros
    with pytest.raises(Exception) as exc:
        F.bono([], "0.05")
    assert "BAD_INPUT" in str(exc.value)
    # precio exactamente 0: 100/(1+y) − 100/(1+y)³ es 0 con y = 0 (2 plazos)
    with pytest.raises(Exception) as exc:
        F.bono([0, 100, -100], "0")
    assert "BAD_INPUT" in str(exc.value)
    with pytest.raises(Exception) as exc:
        F.bono([100, 0, 0, 110], "-1")
    assert "BAD_INPUT" in str(exc.value)


def test_futuro_y_payoff():
    assert F.futuro(100, "0.05", 3)["F"] == pytest.approx(100 * math.exp(0.15))
    assert F.payoff(120, 100, "call")["payoff"] == 20
    assert F.payoff(80, 100, "put")["payoff"] == 20
    assert F.payoff(120, 100, "put")["payoff"] == 0


def test_crr_converge_a_black_scholes():
    crr = F.crr(100, 100, "0.05", "0.2", 1, 400, "call")
    bs = F.black_scholes(100, 100, "0.05", "0.2", 1, "call")
    assert 0 < crr["q"] < 1
    assert crr["precio"] == pytest.approx(bs["precio"], abs=0.05)
    # la americana vale al menos la europea
    am = F.crr(100, 100, "0.05", "0.2", 1, 200, "call", True)["precio"]
    eu = F.crr(100, 100, "0.05", "0.2", 1, 200, "call", False)["precio"]
    assert am >= eu - 1e-9


def test_black_scholes_paridad_y_griegas():
    c = F.black_scholes(100, 110, "0.05", "0.25", 0.5, "call")
    p = F.black_scholes(100, 110, "0.05", "0.25", 0.5, "put")
    assert c["precio"] - p["precio"] == pytest.approx(100 - 110 * math.exp(-0.025))
    assert c["vega"] > 0 and c["gamma"] > 0
    assert 0 < c["delta"] < 1
    # vega de la call y de la put coinciden
    assert p["vega"] == pytest.approx(c["vega"])


def test_vol_implicita():
    ex = F.black_scholes(100, 100, "0.05", "0.3", 1, "call")["precio"]
    r = F.vol_implicita(ex, 100, 100, "0.05", 1, "call")
    assert r["sigma"] == pytest.approx(0.3, abs=1e-6)


def test_montecarlo_cae_en_el_exacto():
    ex = F.black_scholes(100, 100, "0.05", "0.2", 1, "call")["precio"]
    mc = F.montecarlo_opcion(100, 100, "0.05", "0.2", 1, N=40000, semilla=11)
    assert abs(mc["precio"] - ex) < 3 * mc["error"]


def test_markowitz_minima_varianza():
    mu = ["0.10", "0.20"]
    Sg = [[0.04, 0.01], [0.01, 0.09]]
    r = F.markowitz(mu, Sg)
    # segundo camino: el mínimo de wᵀΣw con Σ1 = 1 está en Σ⁻¹1/(1ᵀΣ⁻¹1)
    det = Sg[0][0] * Sg[1][1] - Sg[0][1] * Sg[1][0]
    w1 = [(Sg[1][1] - Sg[0][1]) / det, (Sg[0][0] - Sg[1][0]) / det]
    w1 = [x / sum(w1) for x in w1]
    assert [float(x) for x in r["w"]] == pytest.approx([float(x) for x in w1])
    assert float(sum(r["w"])) == pytest.approx(1.0)
    assert float(r["var_p"]) > 0


def test_markowitz_con_retorno_objetivo():
    mu = ["0.10", "0.20"]
    Sg = [[0.04, 0.01], [0.01, 0.09]]
    r = F.markowitz(mu, Sg, "0.15")
    assert float(sum(r["w"])) == pytest.approx(1.0)
    assert float(r["mu_p"]) == pytest.approx(0.15)
    # KKT: la solución es única salvo degeneración
    assert F.markowitz(mu, Sg, "0.15")["w"] == r["w"]


def test_markowitz_kkt_con_tres_activos():
    # con 3 activos las dos restricciones dejan una dirección factible: el
    # gradiente 2Σw debe ser ortogonal a ella (si no, se puede mejorar)
    mu = ["0.10", "0.15", "0.25"]
    Sg = [[0.04, 0.01, 0.00],
          [0.01, 0.09, 0.02],
          [0.00, 0.02, 0.16]]
    r = F.markowitz(mu, Sg, "0.18")
    assert float(sum(r["w"])) == pytest.approx(1.0)
    assert float(r["mu_p"]) == pytest.approx(0.18)
    # comprobación independiente: mover w por la d nula de {1, μ} no baja la
    # varianza a primer orden (aquí se recalcula a mano el término 2εΣw·d)
    w = [float(x) for x in r["w"]]
    d = [0.15 - 0.25, 0.25 - 0.10, 0.10 - 0.15]
    assert sum(d) == pytest.approx(0.0)
    assert sum(a * b for a, b in zip(d, [0.10, 0.15, 0.25])) == pytest.approx(0.0)
    g = sum(w[i] * Sg[i][j] * d[j] for i in range(3) for j in range(3))
    assert g == pytest.approx(0.0, abs=1e-12)


def test_frontera_eficiente():
    mu = ["0.10", "0.20"]
    Sg = [[0.04, 0.01], [0.01, 0.09]]
    r = F.frontera_eficiente(mu, Sg, puntos=9)
    pts = r["frontera"]
    assert len(pts) >= 5
    vs = [float(v) for _, v in pts]
    assert all(b >= a - 1e-15 for a, b in zip(vs, vs[1:]))
    # cada punto es de hecho una cartera: pesos que suman 1 y dan ese retorno
    for (m, v), w in zip(pts, r["pesos"]):
        assert sum(w) == pytest.approx(1.0)
        assert sum(x * y for x, y in zip(w, [0.10, 0.20])) == pytest.approx(
            float(m), abs=1e-9)
        assert sum(w[i] * Sg[i][j] * w[j] for i in range(2)
                   for j in range(2)) == pytest.approx(float(v))
    g = pedir({"calculo": "frontera", "mu": mu, "Sigma": Sg, "puntos": 9})
    assert g.sello.verdict == V.VERIFIED
    assert g.grafica is not None and g.grafica.series


def test_frontera_tres_activos_es_minima():
    # con 3 activos hay dirección factible: cada punto de la frontera debe
    # subir de riesgo al moverse por ella (si no, no era mínimo)
    mu = ["0.10", "0.15", "0.25"]
    Sg = [[0.04, 0.01, 0.00],
          [0.01, 0.09, 0.02],
          [0.00, 0.02, 0.16]]
    r = F.frontera_eficiente(mu, Sg, puntos=7)
    S = [[float(x) for x in f] for f in Sg]
    d = [0.15 - 0.25, 0.25 - 0.10, 0.10 - 0.15]
    for (m, v), w in zip(r["frontera"], r["pesos"]):
        for signo in (1, -1):
            wp = [w[i] + signo * 0.001 * d[i] for i in range(3)]
            vp = sum(wp[i] * S[i][j] * wp[j] for i in range(3) for j in range(3))
            assert vp >= float(v) - 1e-12


def test_markowitz_rechaza_sigma_no_definida_positiva():
    # sin Σ definida positiva «mínima varianza» no es un mínimo: se niega
    Sg = [[1, 2], [2, 1]]        # propia 3, real −1 → no definida positiva
    with pytest.raises(Exception) as exc:
        F.markowitz(["0.1", "0.2"], Sg)
    assert "BAD_INPUT" in str(exc.value)


def test_sharpe_y_var():
    r = F.sharpe_var(0.10, 0.04, 0.02, "0.05")
    assert r["sharpe"] == pytest.approx(0.08 / 0.2)
    assert r["VaR"] == pytest.approx(0.10 + 0.2 * -1.6448536269514722, rel=1e-6)


def test_contrato_de_todos_los_calculos():
    casos = [
        {"calculo": "interes", "C0": 1000, "r": "0.05", "t": 10},
        {"calculo": "tiempo", "C0": 1000, "C": 2000, "r": "0.05"},
        {"calculo": "van", "flujos": [-1000, 500, 500, 500], "r": "0.05"},
        {"calculo": "tir", "flujos": [-1000, 500, 500, 500]},
        {"calculo": "anualidad", "A": 10000, "r": "0.05", "n": 10},
        {"calculo": "bono", "flujos": [100, 0, 0, 110], "y": "0.05"},
        {"calculo": "futuro", "S0": 100, "r": "0.05", "T": 3},
        {"calculo": "payoff", "S": 120, "K": 100, "tipo": "call"},
        {"calculo": "crr", "S0": 100, "K": 100, "r": "0.05", "sigma": "0.2",
         "T": 1, "n": 40},
        {"calculo": "black_scholes", "S0": 100, "K": 110, "r": "0.05",
         "sigma": "0.25", "T": 0.5},
        {"calculo": "montecarlo", "S0": 100, "K": 100, "r": "0.05",
         "sigma": "0.2", "T": 1, "N": 2000},
        {"calculo": "markowitz", "mu": ["0.10", "0.20"],
         "Sigma": [[0.04, 0.01], [0.01, 0.09]]},
        {"calculo": "frontera", "mu": ["0.10", "0.20"],
         "Sigma": [[0.04, 0.01], [0.01, 0.09]], "puntos": 9},
        {"calculo": "sharpe_var", "mu": 0.1, "var": 0.04, "rf": 0.02,
         "alpha": "0.05"},
    ]
    for e in casos:
        r = pedir(e)
        assert r.sello.verdict == V.VERIFIED, (e, r.sello.verdict)


def test_vol_implicita_en_contrato():
    ex = F.black_scholes(100, 100, "0.05", "0.3", 1, "call")["precio"]
    r = pedir({"calculo": "vol_implicita", "precio": ex, "S0": 100, "K": 100,
               "r": "0.05", "T": 1})
    assert r.sello.verdict == V.VERIFIED