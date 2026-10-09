# SPDX-License-Identifier: MIT
"""ML-20 (bloque 12, G): Markov absorbente, MDP y refuerzo tabular.

Propiedades de §11.3: N·(I−Q) = I; las clases forman partición cerrada y
el periodo es el retorno mínimo; residuo de Bellman 0; iteración de valor =
(I−γP)⁻¹R; MC = media muestral; Qₙ = media muestral; ∇J analítico = numérico.
"""

from __future__ import annotations

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import refuerzo as R
from academic_core.domain.engineering.mathlab import verify as V


def pedir(entrada):
    r = ML.calcular(ML.Peticion("refuerzo", entrada))
    assert C.validar_forma(r) == [], C.validar_forma(r)
    return r


def test_absorcion():
    # ruina p = 1/2, N = 4: t_2 = 2·(4−2) = 4
    P = [["1/2", "1/2", 0, 0, 0],
         [0, "1/2", "1/2", 0, 0],
         [0, 0, "1/2", "1/2", 0],
         [0, 0, 0, "1/2", "1/2"],
         [0, 0, 0, 0, 1]]
    P[0] = [1, 0, 0, 0, 0]
    r = R.absorcion(P)
    assert r["tiempos"][1] == pytest.approx(4.0)
    assert r["absorbentes"] == [0, 4]
    r = pedir({"calculo": "absorcion", "P": P})
    assert r.sello.verdict == V.VERIFIED


def test_clasifica():
    P = [[0, 1, 0], ["1/2", 0, "1/2"], [0, 0, 1]]
    r = R.clasifica(P)
    rec = [c for c in r["clases"] if c["recurrente"]]
    tra = [c for c in r["clases"] if not c["recurrente"]]
    assert [c["estados"] for c in rec] == [[2]]
    assert [c["estados"] for c in tra] == [[0, 1]]
    assert r["periodos"][0] == 2 and r["periodos"][2] == 1
    r = pedir({"calculo": "clasifica", "P": P})
    assert r.sello.verdict == V.VERIFIED


def test_mdp_eval_y_optimo():
    Pp = [["1/2", "1/2"], ["1/4", "3/4"]]
    r = R.mdp_eval(Pp, [1, 0], "1/2")
    assert [float(v) for v in r["v"]][0] == pytest.approx(10 / 7)
    P = [[["1", 0], [0, "1"]], [["1/2", "1/2"], ["1/2", "1/2"]]]
    Rr = [[1, 0], [0, 0]]
    r = R.mdp_optimo(P, Rr, "1/2")
    assert r["politica"][0] == 0
    r = pedir({"calculo": "mdp_optimo", "P": P, "R": Rr, "gamma": "1/2"})
    assert r.sello.verdict == V.VERIFIED


def test_episodio_mc_td_sarsa_q():
    ep = [("s0", "a", 1, "s1", "a"), ("s1", "a", 2, "s2", "a")]
    r = R.episodio(ep, {}, alpha="1/2", gamma=1)
    assert r["MC"] == pytest.approx({"s0,a": 3.0, "s1,a": 2.0})
    assert r["SARSA"]["s0,a"] == pytest.approx(0.5 * (1 + 0))
    r = pedir({"calculo": "episodio",
               "episodio": [["s0", "a", 1, "s1", "a"],
                            ["s1", "a", 2, "s2", "a"]],
               "Q": [], "alpha": "1/2", "gamma": 1})
    assert r.sello.verdict == V.VERIFIED


def test_bandidos():
    r = R.bandidos([[1, 1, 1], [0, 0, 0]], metodo="incremental")
    assert r["Q"][0] == pytest.approx(1.0) and r["N"] == [3, 3]
    r = R.bandidos([[1, 0], [0, 0]], metodo="ucb", semilla=3)
    assert r["N"][0] >= 1 and r["N"][1] >= 1
    r = pedir({"calculo": "bandidos", "pagos": [[1, 1], [0, 0]],
               "metodo": "incremental"})
    assert r.sello.verdict == V.VERIFIED
    # §4.12 pide la gráfica: recompensa media frente al tiempo
    assert r.grafica is not None and r.grafica.series
    ys = r.grafica.series[0].ys
    assert len(ys) == 4 and ys[-1] == pytest.approx(0.5)


def test_reinforce():
    r = R.reinforce([1, 0], eta="0.5", pasos=30, semilla=5)
    assert r["J"] > 0.5
    r = pedir({"calculo": "reinforce", "pagos": [1, 0], "eta": "0.5",
               "pasos": 30})
    assert r.sello.verdict == V.VERIFIED


def test_ml20_pasa_el_contrato():
    for entrada in ({"calculo": "absorcion",
                     "P": [[1, 0], ["1/2", "1/2"]]},
                    {"calculo": "clasifica", "P": [[1, 0], [0, 1]]},
                    {"calculo": "bandidos", "pagos": [[1], [0]]}):
        assert C.validar_forma(pedir(entrada)) == []
