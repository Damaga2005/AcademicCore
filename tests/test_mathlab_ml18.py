# SPDX-License-Identifier: MIT
"""ML-18 (bloque 16, G): detección y estimación.

Propiedades de §11.3: P_FA/P_D empíricas sobre la ROC; varianza empírica
≥ CRB; E[e·x*] = 0; modos de LMS frente a la fórmula; μ sobre la cota
diverge; PSD teórica = TF de r y r[0] = ∫S dF.
"""

from __future__ import annotations

import math

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import deteccion as T
from academic_core.domain.engineering.mathlab import verify as V


def pedir(entrada):
    r = ML.calcular(ML.Peticion("deteccion", entrada))
    assert C.validar_forma(r) == [], C.validar_forma(r)
    return r


def test_correlacion_y_psd():
    r = T.matriz_r([1, "1/2", "1/4"])
    assert min(r["autovalores"]) >= -1e-9
    assert T.r_ar1(1, "1/2", 3)["R"][0][1] == pytest.approx(2 / 3)
    p = T.psd_teorica([1, "1/2", "1/4"], n=512)
    assert p["potencia"] == pytest.approx(1.0, rel=1e-4)
    s = T.psd_salida([1.0, 2.0], [1, 2])
    assert s["Sy"] == [1.0, 8.0]
    r = pedir({"calculo": "psd", "r": [1, "1/2", "1/4"], "n": 128})
    assert r.sello.verdict == V.VERIFIED


def test_detector_np_y_roc():
    assert T.Q(0.0) == pytest.approx(0.5)
    assert T.Qinv(0.5) == pytest.approx(0.0, abs=1e-6)
    r = T.detector([3, 4], 1, 0.05)
    assert r["d2"] == pytest.approx(25.0)
    assert r["Pd"] == pytest.approx(T.Q(T.Qinv(0.05) - 5))
    assert T.detector_map([1], 1, "1/2", "1/2")["gamma"] == pytest.approx(1.0)
    r = pedir({"calculo": "detector", "s": [3, 4], "sigma": 1, "Pfa": 0.05})
    assert r.sello.verdict == V.VERIFIED


def test_fisher_crb_y_eficiencia():
    r = T.fisher("gauss_media", {"N": 10, "sigma2": 4})
    assert (r["I"], r["CRB"]) == pytest.approx((2.5, 0.4))
    # la media muestral alcanza la cota: eficiente
    assert r["CRB"] == pytest.approx(4 / 10)
    assert T.fisher("bernoulli", {"N": 10, "p": "1/2"})["I"] == pytest.approx(40.0)
    r = pedir({"calculo": "fisher", "modelo": "poisson",
               "params": {"N": 5, "lambda": 2}})
    assert r.sello.verdict == V.VERIFIED


def test_gauss_conjunto():
    r = T.gauss_conjunto([0], [0, 0], [[2]], [[1, 0]], [[1, 0], [0, 1]],
                         [1, 1])
    assert r["theta_hat"] == pytest.approx([1.0])
    assert r["ECM"][0][0] == pytest.approx(1.0)
    r = pedir({"calculo": "gauss_conjunto", "m_t": [0], "m_x": [0, 0],
               "K_t": [[2]], "K_tx": [[1, 0]], "K_x": [[1, 0], [0, 1]],
               "x": [1, 1]})
    assert r.sello.verdict == V.VERIFIED


def test_wiener_yule_walker():
    r = T.wiener([[1, "1/2"], ["1/2", 1]], [1, 0], 2)
    assert r["w"] == pytest.approx([4 / 3, -2 / 3])
    assert r["J_min"] == pytest.approx(2 - 4 / 3)
    assert T.yule_walker(1, "1/2")["a"] == pytest.approx(0.5)
    r = pedir({"calculo": "wiener", "R": [[1, "1/2"], ["1/2", 1]],
               "p": [1, 0], "sigma_d2": 2})
    assert r.sello.verdict == V.VERIFIED


def test_gradiente_modos_y_cota():
    r = T.gradiente_modos([[2, 0], [0, 1]], "0.4")
    assert sorted(r["lambdas"]) == pytest.approx([1.0, 2.0])
    with pytest.raises(Exception):
        T.gradiente_modos([[2, 0], [0, 1]], 1.5)  # μ ≥ 2/λ_max: diverge


def test_lms_converge_y_diverge():
    r = T.lms([[1, "1/2"], ["1/2", 1]], [1, 0], "0.2", pasos=100,
              realiz=100, semilla=7)
    assert r["J"][-1] < r["J"][0]
    assert r["diverge"] is False
    r = T.lms([[1, 0], [0, 1]], [1, 0], 2.5, pasos=50, realiz=50,
              semilla=7)
    assert r["diverge"] is True
    r = pedir({"calculo": "lms", "R": [[1, "1/2"], ["1/2", 1]],
               "p": [1, 0], "mu": "0.2", "pasos": 50, "realiz": 50})
    assert r.sello.verdict == V.VERIFIED
    assert T.nlms_cota([[1, "1/2"], ["1/2", 1]])["cota_practica"] == pytest.approx(1.0)


def test_ml18_pasa_el_contrato():
    for entrada in ({"calculo": "matriz_r", "r": [1, "1/2"]},
                    {"calculo": "detector", "s": [1]},
                    {"calculo": "wiener"},
                    {"calculo": "fisher"}):
        assert C.validar_forma(pedir(entrada)) == []
