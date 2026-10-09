# SPDX-License-Identifier: MIT
"""ML-19 (bloque 13, G): optimización y aprendizaje automático.

Propiedades de §11.3: gradiente analítico = diferencias centrales;
la pérdida baja tras un paso con η pequeño; Xᵀe = 0; PCA = SVD salvo
signo; Σλ = traza.
"""

from __future__ import annotations

import math

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import aprende as A
from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import verify as V


def pedir(entrada):
    r = ML.calcular(ML.Peticion("aprende", entrada))
    assert C.validar_forma(r) == [], C.validar_forma(r)
    return r


def test_gd_converge_y_optimo():
    r = A.gd_cuadratica([[2, 0], [0, 1]], [1, 1], "0.4", pasos=30)
    assert r["trayectoria_J"][-1] < r["trayectoria_J"][0]
    assert r["w_final"][0] == pytest.approx(0.5, rel=1e-3)
    assert r["w_final"][1] == pytest.approx(1.0, rel=1e-3)
    r = pedir({"calculo": "gd", "Q": [[2, 0], [0, 1]], "b": [1, 1],
               "eta": "0.4", "pasos": 30})
    assert r.sello.verdict == V.VERIFIED


def test_regresion_y_ridge():
    X = [[1, 1], [1, 2], [1, 3]]
    r = A.regresion(X, [2, 4, 5])
    assert r["w"][0] == pytest.approx(2 / 3) and r["w"][1] == pytest.approx(1.5)
    r = A.regresion(X, [2, 4, 5], lam="1")
    assert r["w"][1] < 1.5  # ridge encoge
    assert A.lasso_1d([1, 2, 3], [1, 2, 3], 100)["w"] == 0.0
    r = pedir({"calculo": "regresion", "X": X, "y": [2, 4, 5]})
    assert r.sello.verdict == V.VERIFIED and "R²" in r.exacto


def test_logistica_metricas_roc():
    X = [[0], [1], [2], [3]]
    r = A.logistica(X, [0, 0, 1, 1], "0.5", pasos=100)
    assert r["w"][1] > 0
    m = A.metricas(8, 2, 1, 9)
    assert (m["acc"], m["F1"]) == pytest.approx((0.85, 16 / 19))
    r = A.roc_auc([(0.9, 1), (0.8, 1), (0.7, 0), (0.1, 0)])
    assert r["AUC"] == pytest.approx(1.0)
    r = pedir({"calculo": "roc",
               "pares": [[0.9, 1], [0.8, 1], [0.7, 0], [0.1, 0]]})
    assert r.sello.verdict == V.VERIFIED


def test_kmedias_em_arbol():
    X = [[0], [1], [9], [10]]
    r = A.kmedias(X, 2, inicios=[0, 3])
    assert r["SSE"] == pytest.approx(1.0)
    assert -1 <= r["silueta"] <= 1
    r = A.em_1d([0, 0.1, 9.9, 10], inicios=[0, 10], iters=50)
    assert r["mus"][0] < 1 and r["mus"][1] > 9
    r = A.arbol([1, 2, 3, 4], [0, 0, 1, 1])
    assert r["ganancia"] == pytest.approx(1.0)
    assert r["umbral"] == 2
    r = pedir({"calculo": "kmedias", "puntos": X, "k": 2,
               "inicios": [0, 3]})
    assert r.sello.verdict == V.VERIFIED


def test_pca_svd():
    X = [[1, 0], [0, 1], [-1, 0], [0, -1]]
    r = A.pca(X)
    assert sum(r["var_explicada"]) == pytest.approx(1.0)
    assert r["autovalores"][0] == pytest.approx(r["autovalores"][1])
    s = A.svd_2d([[3, 0], [0, 4]])
    assert s["sigma"] == pytest.approx([4.0, 3.0])
    r = pedir({"calculo": "pca", "X": X})
    assert r.sello.verdict == V.VERIFIED


def test_red_retroprop_atencion():
    capas = [{"W": [[1.0, -1.0]], "b": [0.0]}]
    r = A.red_mlp([2, 1], capas, ["relu"])
    assert r["a"][-1] == pytest.approx([1.0])
    g = A.retroprop([2, 1], 1.0, capas, ["relu"])
    assert g["grads"][0][1] == pytest.approx([0.0])
    r = A.atencion([[1, 0]], [[1, 0], [0, 1]], [[1, 2], [3, 4]])
    assert sum(r["P"][0]) == pytest.approx(1.0)
    assert A.rnn_pasos([1, 0], [[1.0]], [[0.5]], [0.0])["hs"][0][0] == pytest.approx(
        math.tanh(1.0))
    r = pedir({"calculo": "retroprop", "x": [2, 1], "y": 1.0,
               "capas": capas, "acts": ["relu"]})
    assert r.sello.verdict == V.VERIFIED


def test_svm_lstm():
    r = A.svm_margen([1, 0], 0, [([1, 0], 1), ([-1, 0], -1)])
    assert r["margen"] == pytest.approx(2.0)
    W = {"Wf": [[0.0, 0.0]], "bf": [10.0], "Wi": [[0.0, 0.0]], "bi": [10.0],
         "Wg": [[1.0, 0.0]], "bg": [0.0], "Wo": [[0.0, 0.0]], "bo": [10.0]}
    r = A.lstm_pasos(1.0, W)
    assert r["c"][0] == pytest.approx(math.tanh(1.0), rel=1e-3)
    r = pedir({"calculo": "svm", "w": [1, 0], "b": 0,
               "puntos": [[[1, 0], 1], [[-1, 0], -1]]})
    assert r.sello.verdict == V.VERIFIED


def test_ml19_pasa_el_contrato():
    for entrada in ({"calculo": "gd"},
                    {"calculo": "regresion", "X": [[1, 0], [1, 1]],
                     "y": [1, 2]},
                    {"calculo": "metricas", "VP": 1, "FP": 0, "FN": 0,
                     "VN": 1}):
        assert C.validar_forma(pedir(entrada)) == []
