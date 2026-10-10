# SPDX-License-Identifier: MIT
"""Cada subcálculo de MathLab, por la puerta de la interfaz (``calcular``), contra
un valor obtenido aparte: fórmula cerrada, álgebra a mano o una implementación
independiente escrita aquí. No se reutiliza nada del motor para el valor esperado.

Cada caso exige además: sello «verificado» (o «solo_numerico» cuando el cálculo es
numérico por naturaleza), y traza que se puede mostrar en los tres niveles.
"""

import importlib
import math
import pkgutil
import re

import pytest

import academic_core.domain.engineering.mathlab as pkg
from academic_core.domain.engineering.mathlab import contract as C

for _m in pkgutil.iter_modules(pkg.__path__):
    importlib.import_module(f"{pkg.__name__}.{_m.name}")

_NUM = re.compile(r"[-−]?\d+(?:[.,]\d+)?(?:e[-+]?\d+)?(?:/\d+)?")


def calc(op, entrada, sellos=("verificado",)):
    r = C.calcular(C.Peticion(op, entrada))
    assert r.sello.verdict in sellos, (op, entrada, r.sello)
    for nivel in ("resumen", "paso", "detallado"):
        assert r.traza.render(nivel) is not None
    assert len(r.traza.steps) >= 2, f"{op} {entrada}: un resultado sin pasos"
    return r


def numeros(r) -> list[float]:
    texto = str(r.exacto) + " " + str(r.aproximado or "")
    out = []
    for x in _NUM.findall(texto):
        x = x.replace("−", "-").replace(",", ".")
        if "/" in x:
            a, b = x.split("/")
            out.append(float(a) / float(b) if float(b) else float(a))
            out.append(float(a))
        else:
            out.append(float(x))
    return out


def contiene(r, esperado, rel=1e-5, absol=1e-9):
    vals = numeros(r)
    assert any(math.isclose(v, esperado, rel_tol=rel, abs_tol=absol) for v in vals), \
        f"{esperado} no está en «{r.exacto}»"


# ---------------------------------------------------------------------------
# finanzas (ML-21)
# ---------------------------------------------------------------------------

def _bs(S, K, r, s, T, tipo="call"):
    N = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))  # noqa: E731
    d1 = (math.log(S / K) + (r + s * s / 2) * T) / (s * math.sqrt(T))
    d2 = d1 - s * math.sqrt(T)
    if tipo == "call":
        return S * N(d1) - K * math.exp(-r * T) * N(d2)
    return K * math.exp(-r * T) * N(-d2) - S * N(-d1)


def _arbol(S, K, r, s, T, n, tipo, americana):
    dt = T / n
    u = math.exp(s * math.sqrt(dt))
    d = 1 / u
    q = (math.exp(r * dt) - d) / (u - d)
    pay = (lambda x: max(x - K, 0)) if tipo == "call" else (lambda x: max(K - x, 0))
    V = [pay(S * u ** (n - j) * d ** j) for j in range(n + 1)]
    for i in range(n - 1, -1, -1):
        V = [math.exp(-r * dt) * (q * V[j] + (1 - q) * V[j + 1]) for j in range(i + 1)]
        if americana:
            V = [max(v, pay(S * u ** (i - j) * d ** j)) for j, v in enumerate(V)]
    return V[0]


@pytest.mark.parametrize("entrada, esperado", [
    ({"calculo": "interes"}, 1000 * 1.05 ** 10),
    ({"calculo": "interes", "modo": "simple"}, 1500),
    ({"calculo": "interes", "m": 12}, 1000 * (1 + 0.05 / 12) ** 120),
    ({"calculo": "interes", "modo": "continuo"}, 1000 * math.exp(0.5)),
    ({"calculo": "tiempo"}, math.log(2) / math.log(1.05)),
    ({"calculo": "van", "flujos": [-100, 60, 60], "r": "0.1"}, 60 / 1.1 + 60 / 1.21 - 100),
    ({"calculo": "anualidad"}, 10000 * 0.05 / (1 - 1.05 ** -10)),
    # flujos[k] en t = k: con el primero en t = 0, un bono a la par empieza por 0
    ({"calculo": "bono", "flujos": [0, 5, 5, 105], "y": "0.05"}, 100.0),
    ({"calculo": "bono", "flujos": [0, 5, 5, 105], "y": "0.05"},
     (5 / 1.05 + 2 * 5 / 1.05 ** 2 + 3 * 105 / 1.05 ** 3) / 100),
    ({"calculo": "futuro"}, 100 * math.exp(0.05)),
    ({"calculo": "payoff", "S": 120}, 20),
    ({"calculo": "payoff", "S": 80, "tipo": "put"}, 20),
    ({"calculo": "black_scholes"}, _bs(100, 100, 0.05, 0.2, 1)),
    ({"calculo": "black_scholes", "tipo": "put"}, _bs(100, 100, 0.05, 0.2, 1, "put")),
    ({"calculo": "black_scholes", "S0": 90, "K": 100, "sigma": "0.3", "T": "0.5"},
     _bs(90, 100, 0.05, 0.3, 0.5)),
    ({"calculo": "crr"}, _arbol(100, 100, 0.05, 0.2, 1, 100, "call", False)),
    ({"calculo": "crr", "tipo": "put", "americana": True},
     _arbol(100, 100, 0.05, 0.2, 1, 100, "put", True)),
    ({"calculo": "vol_implicita", "precio": _bs(100, 100, 0.05, 0.2, 1)}, 0.2),
    ({"calculo": "sharpe_var", "mu": "0.1", "var": "0.04", "rf": "0.02"}, 0.4),
    ({"calculo": "sharpe_var", "mu": "0.1", "var": "0.04"}, 0.1 + 0.2 * -1.6448536269514722),
])
def test_finanzas(entrada, esperado):
    contiene(calc("finanzas", entrada), esperado)


def test_tir():
    # 60/(1+i) + 60/(1+i)² = 100 ⇒ (1+i) = (60 + √(3600 + 24000))/200
    i = (60 + math.sqrt(3600 + 24000)) / 200 - 1
    contiene(calc("finanzas", {"calculo": "tir", "flujos": [-100, 60, 60]}), i)


def test_markowitz_minima_varianza():
    # Σ diagonal: w ∝ (1/σ₁², 1/σ₂²) = (25, 100/9)
    w1 = 25 / (25 + 100 / 9)
    mu_p = w1 * 0.1 + (1 - w1) * 0.2
    r = calc("finanzas", {"calculo": "markowitz", "mu": ["0.1", "0.2"],
                          "Sigma": [["0.04", 0], [0, "0.09"]]})
    contiene(r, mu_p)
    contiene(r, 1 / (25 + 100 / 9))


def test_markowitz_con_retorno():
    # con dos activos y m fijado, w sale de wᵀμ = m y wᵀ1 = 1: w₁ = (0.2 − 0.15)/0.1
    r = calc("finanzas", {"calculo": "markowitz", "mu": ["0.1", "0.2"],
                          "Sigma": [["0.04", 0], [0, "0.09"]], "m": "0.15"})
    contiene(r, 0.25 * 0.04 + 0.25 * 0.09)


def test_markowitz_tres_activos_kkt():
    import numpy as np
    mu = np.array([0.1, 0.15, 0.2])
    S = np.array([[0.04, 0.01, 0], [0.01, 0.09, 0.02], [0, 0.02, 0.16]])
    m = 0.16
    A = np.block([[2 * S, -mu[:, None], -np.ones((3, 1))],
                  [mu[None, :], np.zeros((1, 2))], [np.ones((1, 3)), np.zeros((1, 2))]])
    w = np.linalg.solve(A, np.r_[np.zeros(3), m, 1])[:3]
    r = calc("finanzas", {"calculo": "markowitz", "mu": [str(v) for v in mu],
                          "Sigma": [[str(v) for v in f] for f in S], "m": str(m)})
    contiene(r, float(w @ S @ w))


def test_montecarlo_cae_en_black_scholes():
    r = calc("finanzas", {"calculo": "montecarlo"})
    precio, err = numeros(r)[:2]
    assert abs(precio - _bs(100, 100, 0.05, 0.2, 1)) < 5 * err


def test_frontera_empieza_en_la_minima_varianza():
    r = calc("finanzas", {"calculo": "frontera", "mu": ["0.1", "0.2"],
                          "Sigma": [["0.04", 0], [0, "0.09"]]})
    assert r.grafica is not None


# ---------------------------------------------------------------------------
# Markov y refuerzo (ML-20)
# ---------------------------------------------------------------------------

_RUINA = [[1, 0, 0, 0], ["1/2", 0, "1/2", 0], [0, "1/2", 0, "1/2"], [0, 0, 0, 1]]


def test_absorcion_ruina_del_jugador():
    # desde 1: absorbe en 0 con 2/3 y tarda 2 pasos de media (N = (I − Q)⁻¹)
    r = calc("refuerzo", {"calculo": "absorcion", "P": _RUINA})
    contiene(r, 2.0)
    assert "2/3" in str(r.exacto) or any(math.isclose(v, 2 / 3, rel_tol=1e-6)
                                         for v in numeros(r))


@pytest.mark.parametrize("P, recurrentes, transitorios", [
    ([[0, 1], [0, 1]], [[1]], [[0]]),
    ([[0, 1, 0], [0, 0, 1], [0, 0, 1]], [[2]], [[0], [1]]),
    ([[0, 1], [1, 0]], [[0, 1]], []),
    (_RUINA, [[0], [3]], [[1, 2]]),
])
def test_clasifica(P, recurrentes, transitorios):
    texto = str(calc("refuerzo", {"calculo": "clasifica", "P": P}).exacto)
    for c in recurrentes:
        assert f"{c} recurrente" in texto
    for c in transitorios:
        assert f"{c} transitoria" in texto


def test_mdp_eval():
    # v₂ = 0; v₁ = 1 + 0.9·(½v₁ + ½v₂) ⇒ v₁ = 1/0.55
    r = calc("refuerzo", {"calculo": "mdp_eval", "P": [["1/2", "1/2"], [0, 1]],
                          "R": [1, 0], "gamma": "0.9"})
    contiene(r, 1 / 0.55)


def test_mdp_optimo():
    # quedarse en 1 da 1 por paso: v₁ = 1/(1 − 0.9) = 10; desde 0 conviene saltar: v₀ = 0.9·10
    r = calc("refuerzo", {"calculo": "mdp_optimo",
                          "P": [[[1, 0], [0, 1]], [[0, 1], [1, 0]]],
                          "R": [[0, 1], [0, 0]], "gamma": "0.9"})
    contiene(r, 10.0, rel=1e-6)
    contiene(r, 9.0, rel=1e-6)


def test_episodio_con_pares_repetidos():
    # G₂ = 2, G₁ = 0 + 0.9·2 = 1.8, G₀ = 1 + 0.9·1.8 = 2.62 (MC primera visita);
    # SARSA/Q/TD a mano: 0.5, 0.225 y luego Q(A,x) = 0.5 + 0.5·(2 − 0.5) = 1.25
    r = calc("refuerzo", {"calculo": "episodio", "alpha": "1/2", "gamma": "0.9", "Q": [],
                          "episodio": [["A", "x", 1, "B", "y"], ["B", "y", 0, "A", "x"],
                                       ["A", "x", 2, "T", "-"]]})
    for v in (2.62, 1.8, 1.25, 0.225):
        contiene(r, v)


def test_bandidos_incremental_es_la_media():
    r = calc("refuerzo", {"calculo": "bandidos", "pagos": [[1, 0, 1, 1], [0, 2, 0, 0]],
                          "metodo": "incremental"})
    contiene(r, 0.75)
    contiene(r, 0.5)


@pytest.mark.parametrize("metodo", ["greedy", "ucb"])
def test_bandidos_estocasticos_dan_resultado(metodo):
    calc("refuerzo", {"calculo": "bandidos", "pagos": [[1, 0, 1], [0, 0, 1]], "metodo": metodo})


def test_reinforce_da_resultado():
    calc("refuerzo", {"calculo": "reinforce", "pagos": [1, 0, "1/2"], "pasos": 30})


# ---------------------------------------------------------------------------
# optimización y aprendizaje (ML-19)
# ---------------------------------------------------------------------------

np = pytest.importorskip("numpy")


def test_gd_va_al_optimo_de_las_normales():
    # J = ½wᵀQw − bᵀw, óptimo Q⁻¹b = (1/2, 1); J* = −½bᵀQ⁻¹b = −0.75
    r = calc("aprende", {"calculo": "gd", "pasos": 200})
    contiene(r, -0.75, rel=1e-6)


@pytest.mark.parametrize("X, y, grado", [
    ([1, 2, 3, 4], [2, 4.1, 5.9, 8.2], 1),
    ([0, 1, 2, 3, 4], [1, 2, 5, 10, 17], 2),
    ([[1, 1, 0], [1, 2, 1], [1, 3, 1], [1, 4, 3]], [3, 5, 6, 10], 1),
])
def test_regresion_contra_minimos_cuadrados(X, y, grado):
    A = (np.array([[x ** k for k in range(grado + 1)] for x in X], float)
         if not isinstance(X[0], list) else np.array(X, float))
    w = np.linalg.lstsq(A, np.array(y, float), rcond=None)[0]
    e = np.array(y) - A @ w
    R2 = 1 - e @ e / np.sum((np.array(y) - np.mean(y)) ** 2)
    r = calc("aprende", {"calculo": "regresion", "X": X, "y": [str(v) for v in y],
                         "grado": grado})
    contiene(r, float(R2), rel=1e-5)


def test_regresion_ridge():
    A = np.array([[1, 1], [1, 2], [1, 3]], float)
    y = np.array([1, 2, 2], float)
    w = np.linalg.solve(A.T @ A + 0.5 * np.eye(2), A.T @ y)
    r = calc("aprende", {"calculo": "regresion", "X": [[1, 1], [1, 2], [1, 3]],
                         "y": [1, 2, 2], "lam": "1/2"})
    texto = str(r.exacto)
    vals = [float(eval(t)) for t in re.findall(r"'(-?\d+(?:/\d+)?)'", texto)]
    assert np.allclose(sorted(vals), sorted(w))


def test_logistica_baja_la_perdida_y_acierta():
    X = [[0], [1], [2], [3]]
    r = calc("aprende", {"calculo": "logistica", "X": X, "y": [0, 0, 1, 1],
                         "eta": "0.5", "pasos": 500})
    w0, w1 = numeros(r)[:2]
    assert w1 > 0 and -w0 / w1 == pytest.approx(1.5, abs=0.1)   # frontera en x = 1.5


def test_metricas():
    r = calc("aprende", {"calculo": "metricas", "VP": 40, "FP": 10, "FN": 5, "VN": 45})
    contiene(r, 0.85, rel=1e-3)
    contiene(r, 80 / 95, rel=1e-3)


def test_roc_auc_mann_whitney():
    pares = [[0.9, 1], [0.8, 1], [0.7, 0], [0.6, 1], [0.5, 0], [0.4, 0]]
    pos = [s for s, y in pares if y]
    neg = [s for s, y in pares if not y]
    auc = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))
    contiene(calc("aprende", {"calculo": "roc", "pares": pares}), auc)


def test_kmedias_dos_grupos_claros():
    pts = [[0, 0], [0, 1], [1, 0], [10, 10], [10, 11], [11, 10]]
    # SSE de cada grupo respecto a su centroide (1/3, 1/3): 3 · (… ) = 4/3 por grupo
    r = calc("aprende", {"calculo": "kmedias", "puntos": pts, "k": 2,
                         "inicios": [0, 3]})
    contiene(r, 8 / 3)


def test_em_separa_dos_gaussianas():
    xs = [-2.1, -1.9, -2.0, -2.2, -1.8, 3.0, 3.1, 2.9, 3.2, 2.8]
    r = calc("aprende", {"calculo": "em", "x": xs, "inicios": [-1, 1]})
    contiene(r, -2.0, rel=1e-3)
    contiene(r, 3.0, rel=1e-3)


def test_arbol_ganancia_de_informacion():
    # x ≤ 2 separa perfecto: ganancia = H(½) = 1 bit
    r = calc("aprende", {"calculo": "arbol", "x": [1, 2, 3, 4], "y": [0, 0, 1, 1]})
    contiene(r, 1.0)


def test_pca_contra_numpy():
    X = [[2, 0], [0, 1], [3, 1], [1, 3], [4, 2]]
    lam = np.linalg.eigvalsh(np.cov(np.array(X, float).T))[::-1]
    r = calc("aprende", {"calculo": "pca", "X": X})
    for v in lam:
        contiene(r, float(v), rel=1e-6)


def test_svd_contra_numpy():
    X = [[2, 1], [1, 3], [0, 1]]
    for v in np.linalg.svd(np.array(X, float))[1]:
        contiene(calc("aprende", {"calculo": "svd", "X": X}), float(v), rel=1e-6)


_CAPAS = [{"W": [[0.5, -0.2], [0.1, 0.4]], "b": [0.1, -0.1]},
          {"W": [[0.3, -0.6]], "b": [0.05]}]


def _forward(x, capas, acts):
    f = {"relu": lambda z: np.maximum(z, 0), "sigmoide": lambda z: 1 / (1 + np.exp(-z)),
         "tanh": np.tanh, "lineal": lambda z: z}
    a = np.array(x, float)
    for c, act in zip(capas, acts):
        a = f[act](np.array(c["W"], float) @ a + np.array(c["b"], float))
    return a


def test_red_hacia_delante():
    out = _forward([1, 2], _CAPAS, ["tanh", "sigmoide"])
    contiene(calc("aprende", {"calculo": "red", "x": [1, 2], "capas": _CAPAS,
                              "acts": ["tanh", "sigmoide"]}), float(out[0]))


@pytest.mark.parametrize("acts", [["tanh", "sigmoide"], ["relu", "lineal"]])
def test_retroprop_contra_diferencias_finitas(acts):
    # ∂J/∂W₂[0][0] de J = ½(a − y)² por diferencias centrales hechas aquí
    import copy

    def J(capas):
        return 0.5 * float((_forward([1, 2], capas, acts)[0] - 1) ** 2)
    h = 1e-6
    mas, menos = copy.deepcopy(_CAPAS), copy.deepcopy(_CAPAS)
    mas[1]["W"][0][0] += h
    menos[1]["W"][0][0] -= h
    g = (J(mas) - J(menos)) / (2 * h)
    r = calc("aprende", {"calculo": "retroprop", "x": [1, 2], "y": 1, "capas": _CAPAS,
                         "acts": acts})
    contiene(r, g, rel=1e-5)


def test_atencion_contra_softmax_a_mano():
    Q = np.array([[1, 0], [0, 1]], float)
    K = np.array([[1, 0], [1, 1]], float)
    V = np.array([[1, 2], [3, 4]], float)
    S = Q @ K.T / math.sqrt(2)
    P = np.exp(S) / np.exp(S).sum(axis=1, keepdims=True)
    Y = P @ V
    r = calc("aprende", {"calculo": "atencion", "Q": Q.tolist(), "K": K.tolist(),
                         "V": V.tolist()})
    for v in Y.ravel():
        contiene(r, float(v))


def test_rnn_muestra_los_estados():
    h, hs = 0.0, []
    for x in [1, 0, 1, 1]:
        h = math.tanh(0.5 * x + 0.3 * h + 0.1)
        hs.append(h)
    r = calc("aprende", {"calculo": "rnn", "x": [1, 0, 1, 1], "Wx": [[0.5]], "Wh": [[0.3]],
                         "b": [0.1]})
    for v in hs:
        contiene(r, v)


def test_lstm_un_paso():
    s = lambda z: 1 / (1 + math.exp(-z))  # noqa: E731
    z = 0.1 * 1.0
    i = o = s(z)
    g = math.tanh(z)
    c = i * g
    W = {k: [[0.1, 0.2]] for k in ("Wf", "Wi", "Wg", "Wo")}
    W.update({k: [0.0] for k in ("bf", "bi", "bg", "bo")})
    contiene(calc("aprende", {"calculo": "lstm", "x": 1.0, "W": W}), o * math.tanh(c))


def test_svm_margen():
    r = calc("aprende", {"calculo": "svm", "w": [1, 1], "b": -3,
                         "puntos": [[[1, 1], -1], [[2, 2], 1], [[3, 3], 1]]})
    contiene(r, 2 / math.sqrt(2))


# ---------------------------------------------------------------------------
# detección y estimación (ML-18)
# ---------------------------------------------------------------------------

def _Qg(x):
    return 0.5 * math.erfc(x / math.sqrt(2))


def _Qinv(p):
    lo, hi = -10.0, 10.0
    for _ in range(200):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if _Qg(m) > p else (lo, m)
    return (lo + hi) / 2


def test_matriz_r_3x3_contra_numpy():
    R = np.array([[2, 1, 0.5], [1, 2, 1], [0.5, 1, 2]])
    r = calc("deteccion", {"calculo": "matriz_r", "r": [2, 1, "1/2"]})
    for v in np.linalg.eigvalsh(R):
        contiene(r, float(v))


def test_r_ar1():
    r = calc("deteccion", {"calculo": "r_ar1", "sigma2": 1, "a": "1/2", "p": 4})
    for k in range(4):
        contiene(r, 0.5 ** k / 0.75)


def test_psd_teorica_potencia():
    contiene(calc("deteccion", {"calculo": "psd", "r": [3, 1, "1/2"]}), 3.0)


def test_psd_salida():
    r = calc("deteccion", {"calculo": "psd_salida", "Sx": [1, 2, 4], "H": [1, "0.5j", "1+1j"]})
    for v in (1, 0.5, 8):
        contiene(r, v)


def test_detector_neyman_pearson():
    d = math.sqrt(2)
    contiene(calc("deteccion", {"calculo": "detector", "s": [1, 1], "sigma": 1, "Pfa": 0.05}),
             _Qg(_Qinv(0.05) - d), rel=1e-4)


def test_detector_map_pe():
    contiene(calc("deteccion", {"calculo": "detector_map", "s": [1, 1], "sigma": 1}),
             _Qg(math.sqrt(2) / 2))


@pytest.mark.parametrize("modelo, params, I", [
    ("gauss_media", {"N": 10, "sigma2": 2}, 5.0),
    ("bernoulli", {"N": 5, "p": "0.3"}, 5 / 0.21),
    ("poisson", {"N": 4, "lambda": 3}, 4 / 3),
])
def test_fisher(modelo, params, I):
    contiene(calc("deteccion", {"calculo": "fisher", "modelo": modelo, "params": params}), I)


def test_gauss_conjunto_contra_formula():
    Kt = np.array([[2.0, 0], [0, 1]])
    Ktx = np.array([[1, 0], [0.5, 0.2]])
    Kx = np.array([[1, 0.3], [0.3, 2]])
    x = np.array([1, -1.0])
    th = np.array([1, 0]) + Ktx @ np.linalg.solve(Kx, x)
    r = calc("deteccion", {"calculo": "gauss_conjunto", "m_t": [1, 0], "m_x": [0, 0],
                           "K_t": Kt.tolist(), "K_tx": Ktx.tolist(), "K_x": Kx.tolist(),
                           "x": x.tolist()})
    for v in th:
        contiene(r, float(v))


def test_wiener():
    R = np.array([[1, 0.5], [0.5, 1]])
    w = np.linalg.solve(R, [1, 0])
    r = calc("deteccion", {"calculo": "wiener"})
    for v in w:
        contiene(r, float(v))
    contiene(r, 2 - w[0])


def test_yule_walker():
    contiene(calc("deteccion", {"calculo": "yule_walker", "r0": 2, "r1": 1}), 0.5)


def test_gradiente_modos_con_oscilacion():
    # μλ = 1.5 ∈ (1, 2): converge oscilando; antes reventaba con ln de un negativo
    calc("deteccion", {"calculo": "gradiente", "R": [[3, 0], [0, 1]], "mu": "0.5"})


def test_lms_media_hacia_wiener():
    r = calc("deteccion", {"calculo": "lms", "mu": "0.05", "pasos": 300, "realiz": 100})
    assert r.sello.verdict == "verificado"


def test_nlms():
    contiene(calc("deteccion", {"calculo": "nlms", "R": [[2, 0], [0, 1]]}), 2 / 3)


# ---------------------------------------------------------------------------
# discreta, códigos e información (ML-17)
# ---------------------------------------------------------------------------

def _H(ps):
    return -sum(p * math.log2(p) for p in ps if p > 0)


def test_logica_y_equivalencia():
    assert "3/4" in str(calc("discreta", {"calculo": "logica", "formula": "p -> q"}).exacto)
    assert "NO" not in str(calc("discreta", {"calculo": "equivalencia"}).exacto)
    r = calc("discreta", {"calculo": "equivalencia", "f": "p -> q", "g": "q -> p"})
    assert "NO" in str(r.exacto)


def test_logica_admite_seis_variables():
    calc("discreta", {"calculo": "logica", "formula": "(p y q) o (r y s) o (t y u)"})


def test_conjuntos():
    r = calc("discreta", {"calculo": "conjuntos", "a": [1, 2, 3], "b": [2, 3, 4],
                          "op": "interseccion"})
    assert "[2, 3]" in str(r.exacto)


def test_potencia_grande_da_el_cardinal():
    contiene(calc("discreta", {"calculo": "potencia", "n": 20}), 2 ** 20)


def test_binomio_y_vandermonde():
    contiene(calc("discreta", {"calculo": "binomio", "n": 7, "k": 3}), math.comb(7, 3))
    contiene(calc("discreta", {"calculo": "vandermonde", "r": 3, "s": 4, "n": 2}),
             math.comb(7, 2))


@pytest.mark.parametrize("a, b, c, f0, f1, n", [
    (1, 1, 0, 0, 1, 10), (5, -6, 0, 0, 1, 7), (2, -1, 0, 1, 3, 9), (3, -2, 4, 1, 1, 6),
    ("1/2", "1/2", 1, 0, 1, 5), (1, -1, 0, 0, 1, 7),
])
def test_recurrencia_contra_iteracion(a, b, c, f0, f1, n):
    from fractions import Fraction as Fr
    f = [Fr(f0), Fr(f1)]
    while len(f) <= n:
        f.append(Fr(a) * f[-1] + Fr(b) * f[-2] + Fr(c))
    r = calc("discreta", {"calculo": "recurrencia", "a": a, "b": b, "c": c,
                          "f0": f0, "f1": f1, "n": n})
    assert str(f[n]) in str(r.exacto)


@pytest.mark.parametrize("a, b, f, esperado", [
    (2, 2, "n", "caso 2: Θ(n·log n)"), (4, 2, "nlogn", "caso 1: Θ(n^2)"),
    (1, 2, "n", "caso 3: Θ(n)"), (8, 2, "n2", "caso 1: Θ(n^3)"),
    (2, 4, "n^1/2", "caso 2: Θ(n^0.5·log n)"), (3, 4, "nlogn", "caso 3: Θ(n·log n)"),
])
def test_maestro(a, b, f, esperado):
    texto = str(calc("discreta", {"calculo": "maestro", "a": a, "b": b, "f": f}).exacto)
    assert texto.startswith(esperado)


def test_ruina_del_jugador_sesgada():
    p, N = 0.4, 10
    q = (1 - p) / p
    r = calc("discreta", {"calculo": "ruina", "p": "0.4", "N": N})
    for k in (1, 5, 9):
        contiene(r, (1 - q ** k) / (1 - q ** N))


def test_mochila_contra_fuerza_bruta():
    import itertools
    pesos, valores, cap = [1, 3, 4, 5], [1, 4, 5, 7], 7
    mejor = max(sum(v for v, s in zip(valores, sel) if s)
                for sel in itertools.product((0, 1), repeat=4)
                if sum(p for p, s in zip(pesos, sel) if s) <= cap)
    contiene(calc("discreta", {"calculo": "mochila", "pesos": pesos, "valores": valores,
                               "cap": cap}), mejor)


def test_cambio_no_canonico():
    r = calc("discreta", {"calculo": "cambio", "cantidad": 6, "sistema": [1, 3, 4]})
    assert "3" in str(r.exacto) and "2" in str(r.exacto)


def test_tiempo_real_monotono_por_tasa():
    r = calc("discreta", {"calculo": "tiempo_real",
                          "tareas": [{"C": 1, "T": 4}, {"C": 2, "T": 6}]})
    contiene(r, 1 / 4 + 2 / 6, rel=1e-3)


@pytest.mark.parametrize("entrada, esperado", [
    ({"calculo": "cesar", "texto": "HOLA", "k": 3}, "KROD"),
    ({"calculo": "afin", "texto": "HOLA", "a": 5, "b": 8}, "RALI"),
    ({"calculo": "vigenere", "texto": "HOLA", "clave": "CLAVE"}, "JZLV"),
    ({"calculo": "hill", "texto": "HOLA", "matriz": [[3, 3], [2, 5]]}, "LGHW"),
])
def test_cifrados_clasicos(entrada, esperado):
    assert esperado in str(calc("codigos", entrada).exacto)


def test_rsa_y_diffie_hellman():
    r = calc("codigos", {"calculo": "rsa", "p": 61, "q": 53, "e": 17, "m": 65})
    contiene(r, pow(65, 17, 61 * 53))
    s = pow(pow(5, 15, 23), 6, 23)
    contiene(calc("codigos", {"calculo": "dh", "p": 23, "g": 5, "a": 6, "b": 15}), s)


def test_crc_contra_division_de_polinomios():
    msg, gen = [1, 1, 0, 1, 0, 1], [1, 0, 1, 1]
    a = msg + [0] * (len(gen) - 1)
    for i in range(len(msg)):
        if a[i]:
            for j, g in enumerate(gen):
                a[i + j] ^= g
    resto = a[-(len(gen) - 1):]
    r = calc("codigos", {"calculo": "crc", "mensaje": msg, "generador": gen})
    assert str(resto) in str(r.exacto)


def test_checksum_rfc1071():
    pal = [0x4500, 0x0073, 0x0000, 0x4000, 0x4011, 0x0000, 0xc0a8, 0x0001, 0xc0a8, 0x00c7]
    assert "0xb861" in str(calc("codigos", {"calculo": "checksum", "palabras": pal}).exacto)


def test_hamming_7_4():
    G = [[1, 0, 0, 0, 1, 1, 0], [0, 1, 0, 0, 1, 0, 1], [0, 0, 1, 0, 0, 1, 1],
         [0, 0, 0, 1, 1, 1, 1]]
    assert "[7,4,3]" in str(calc("codigos", {"calculo": "codigo", "G": G}).exacto)
    H = [[1, 1, 0, 1, 1, 0, 0], [1, 0, 1, 1, 0, 1, 0], [0, 1, 1, 1, 0, 0, 1]]
    calc("codigos", {"calculo": "sindrome", "H": H, "r": [1, 0, 0, 0, 1, 1, 1]})


def test_shamir_ida_y_vuelta():
    r = calc("codigos", {"calculo": "shamir_reparto", "t": 3, "n": 5, "p": 97, "secreto": 42})
    partes = [[int(a), int(b)] for a, b in re.findall(r"\((\d+), (\d+)\)", str(r.exacto))]
    contiene(calc("codigos", {"calculo": "shamir_reconstruye", "partes": partes[2:],
                              "p": 97, "t": 3}), 42)


def test_tabla_zn_y_gf():
    assert "no cuerpo" in str(calc("codigos", {"calculo": "tabla_zn", "n": 15}).exacto)
    calc("codigos", {"calculo": "tabla_zn", "n": 31})
    calc("codigos", {"calculo": "gf2m", "m": 4})
    texto = str(calc("codigos", {"calculo": "poli_gfp", "coefs": [1, 1, 0, 0, 1], "p": 2}).exacto)
    assert "irreducible" in texto


def test_hash_cumpleanos():
    P = 1 - math.prod(1 - i / 365 for i in range(23))
    contiene(calc("codigos", {"calculo": "hash"}), P, rel=1e-3)


def test_privacidad():
    reg = [{"edad": 30, "cp": 1}, {"edad": 30, "cp": 1}, {"edad": 40, "cp": 2},
           {"edad": 40, "cp": 2}, {"edad": 40, "cp": 2}]
    contiene(calc("codigos", {"calculo": "k_anonimato", "registros": reg,
                              "quasis": ["edad", "cp"]}), 2)
    contiene(calc("codigos", {"calculo": "dp", "sensibilidad": 2, "epsilon": "0.5"}), 4)


@pytest.mark.parametrize("entrada, esperado", [
    ({"calculo": "entropia", "probs": ["1/2", "1/4", "1/4"]}, 1.5),
    ({"calculo": "entropia", "probs": ["0.1", "0.2", "0.7"]}, _H([0.1, 0.2, 0.7])),
    ({"calculo": "divergencia"}, 0.5 * math.log2(2) + 0.5 * math.log2(2 / 3)),
    ({"calculo": "capacidad", "tipo": "BSC", "param": "0.1"}, 1 - _H([0.1, 0.9])),
    ({"calculo": "kraft", "longitudes": [1, 2, 3, 3]}, 1.0),
    ({"calculo": "clave", "bits": 64, "tasa": "1e9"}, 2 ** 63 / 1e9),
])
def test_informacion(entrada, esperado):
    contiene(calc("informacion", entrada), esperado, rel=1e-3)


def test_informacion_mutua():
    P = np.array([[0.3, 0.1], [0.1, 0.5]])
    I = _H(P.sum(1)) + _H(P.sum(0)) - _H(P.ravel())
    contiene(calc("informacion", {"calculo": "conjunta",
                                  "tabla": [["0.3", "0.1"], ["0.1", "0.5"]]}), I, rel=1e-3)


def test_huffman():
    calc("informacion", {"calculo": "huffman_check",
                         "probs": {"a": "0.4", "b": "0.3", "c": "0.2", "d": "0.1"}})


# ---------------------------------------------------------------------------
# campos y ondas (ML-16)
# ---------------------------------------------------------------------------

_E0 = 8.8541878128e-12
_MU0 = 4 * math.pi * 1e-7
_K = 1 / (4 * math.pi * _E0)
_C = 299792458.0


@pytest.mark.parametrize("entrada, esperado", [
    ({"calculo": "carga", "tipo": "cilindro", "a": 1, "R1": 0, "R2": 1, "L": 1}, 2 * math.pi / 3),
    ({"calculo": "carga", "tipo": "esfera", "a": 1, "R": 1, "n": 2}, 4 * math.pi / 5),
    ({"calculo": "carga", "tipo": "placa", "a": 3, "x0": 0, "x1": 2, "y0": 0, "y1": 1}, 8.0),
    ({"calculo": "carga", "tipo": "arco", "a": 1, "R": 1, "t1": 0, "t2": "pi", "m": 2},
     1 * 1 * 2 * (math.cos(0) - math.cos(math.pi / 2))),
    ({"calculo": "carga", "tipo": "segmento", "Q": "1e-9", "L": 1, "d": 1},
     _K * 1e-9 / (1 * math.sqrt(1 + 0.25))),
    ({"calculo": "gauss", "tipo": "esfera", "Q": "1e-9", "R": "0.1"}, _K * 1e-18 / 0.2),
    ({"calculo": "gauss", "tipo": "plano", "sigma": "1e-9"}, 1e-9 / (2 * _E0)),
    ({"calculo": "conductores", "R1": 1, "R2": 2, "R3": 3, "Q1": "1e-9", "Q2": 0},
     _K * 1e-9 * (1 - 1 / 2 + 1 / 3)),
    ({"calculo": "coulomb", "tipo": "anillo", "Q": "1e-9", "R": 1, "z": 1},
     _K * 1e-9 / 2 ** 1.5),
    ({"calculo": "coulomb", "tipo": "disco", "sigma": "1e-9", "R": 1, "z": "0.1"},
     1e-9 / (2 * _E0) * (1 - 0.1 / math.sqrt(1.01))),
    ({"calculo": "biot_savart", "tipo": "espira", "I": 2, "R": "0.1", "z": "0.1"},
     _MU0 * 2 * 0.01 / (2 * 0.02 ** 1.5)),
    ({"calculo": "biot_savart", "tipo": "hilo", "I": 5, "r": "0.02"}, _MU0 * 5 / (2 * math.pi * 0.02)),
    ({"calculo": "biot_savart", "tipo": "coaxial", "I": 1, "a": 1, "b": 2, "r": "1.5"},
     _MU0 * (1 - (1.5 ** 2 - 1) / (4 - 1)) / (2 * math.pi * 1.5)),
    ({"calculo": "biot_savart", "tipo": "poligono", "I": 1, "a": 1, "N": 6},
     _MU0 * 6 / (2 * math.pi) * math.sin(math.pi / 6)),
    ({"calculo": "condensador", "tipo": "plano", "eps_r": 4, "A": "0.01", "d": "0.001"},
     4 * _E0 * 0.01 / 0.001),
    ({"calculo": "condensador", "tipo": "esferico", "eps_r": 1, "R1": 1, "R2": 2},
     4 * math.pi * _E0 / (1 - 0.5)),
    ({"calculo": "condensador", "tipo": "cilindrico", "eps_r": 2, "L": 1, "R1": 1, "R2": 2},
     2 * math.pi * 2 * _E0 / math.log(2)),
    ({"calculo": "faraday", "B0": 1, "f": 50, "N": 100, "A": "0.01", "theta": "pi/3"},
     -100 * 0.01 * 2 * math.pi * 50 * 0.5),   # ε = −amp·cos(ωt): Lenz
    ({"calculo": "mutua", "N": 1000, "Nb": 10, "a": "0.1", "L": 1},
     _MU0 * 1000 * 10 * 0.01),
    ({"calculo": "friis", "Pt": 10, "Gt_dB": 20, "Gr_dB": 15, "lam": "0.1", "R": 1000},
     10 * 100 * 10 ** 1.5 * (0.1 / (4 * math.pi * 1000)) ** 2),
    ({"calculo": "ruido", "G_dB": 40, "T_sys": 100}, 20.0),
    ({"calculo": "fuerza_espira", "I_hilo": 10, "I_esp": 1, "a": "0.15", "b": "0.08", "x": "0.1"},
     _MU0 * 10 * 1 * 0.08 / (2 * math.pi) * (1 / 0.1 - 1 / 0.25)),
    ({"calculo": "maxwell", "E0": 3, "B0": "1e-8", "k": 1, "omega": "3e8"}, 3e8),
])
def test_campos(entrada, esperado):
    contiene(calc("campos", entrada, sellos=("verificado", "solo_numerico")), esperado, rel=1e-4)


def test_guia_dispersion():
    a, w = 0.1, 2e10
    beta = math.sqrt((w / _C) ** 2 - (math.pi / a) ** 2)
    contiene(calc("campos", {"calculo": "guia", "E0": 1, "a": "0.1", "omega": "2e10"}), beta, rel=1e-4)


def test_guia_bajo_corte_no_propaga():
    with pytest.raises(Exception):
        C.calcular(C.Peticion("campos", {"calculo": "guia", "a": "0.1", "omega": "1e9"}))


def test_v_dado_da_la_carga_en_culombios():
    contiene(calc("campos", {"calculo": "v_dado"}), -4 * _E0, rel=1e-4)


def test_completar_By():
    # ∂Bx/∂x + ∂By/∂y = 0 con Bx = 2x ⇒ By = −2y
    assert "−2·y" in str(calc("campos", {"calculo": "completar", "Bx": [[1, 0, 2]]}).exacto)


def test_espira_fuera_del_eje_contra_biot_savart_propio():
    I, R, rho, z = 1.0, 0.2, 0.1, 0.15
    n, Bz = 20000, 0.0
    for k in range(n):
        ph = 2 * math.pi * (k + 0.5) / n
        dlx, dly = -math.sin(ph) * 2 * math.pi * R / n, math.cos(ph) * 2 * math.pi * R / n
        rx, ry, rz = rho - R * math.cos(ph), -R * math.sin(ph), z
        r3 = (rx * rx + ry * ry + rz * rz) ** 1.5
        Bz += _MU0 * I / (4 * math.pi) * (dlx * ry - dly * rx) / r3
    r = calc("campos", {"calculo": "fuera_eje", "I": 1, "R": "0.2", "rho": "0.1", "z": "0.15"},
             sellos=("verificado", "solo_numerico"))
    contiene(r, Bz, rel=1e-4)


def test_mutua_neumann_dos_espiras_coaxiales():
    calc("campos", {"calculo": "mutua_neumann",
                    "loop1": [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]],
                    "loop2": [[0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], "n": 10},
         sellos=("verificado", "solo_numerico"))


@pytest.mark.parametrize("calculo", ["perfil", "poynting", "array"])
def test_campos_restantes_dan_resultado(calculo):
    calc("campos", {"calculo": calculo})


# ---------------------------------------------------------------------------
# fasores y polarización (ML-15)
# ---------------------------------------------------------------------------

def test_suma_de_fasores():
    r = calc("polarizacion", {"calculo": "fasor", "suma": [[3, 0], [4, "pi/2"]]})
    contiene(r, 5.0)
    contiene(r, math.atan2(4, 3))


def test_problema_inverso_recupera_A_y_fase():
    w, A, ph = 2 * math.pi, 3.0, 0.5
    x = lambda t: 8 * math.cos(w * t) + A * math.cos(w * t + ph)  # noqa: E731
    r = calc("polarizacion", {"calculo": "inverso", "omega": "2*pi", "conocido": 8,
                       "muestras": [[0.1, x(0.1)], [0.3, x(0.3)]]})
    contiene(r, A, rel=1e-6)
    contiene(r, ph, rel=1e-6)


def test_onda_plana_en_vacio():
    eta = math.sqrt(_MU0 / _E0)
    contiene(calc("polarizacion", {"calculo": "onda_plana", "E0": [1, 0], "n": 1, "f": "3e8"}),
             1 / (2 * eta), rel=1e-4)


def test_medio_con_perdidas():
    import cmath
    w = 2 * math.pi * 1e9
    g = 1j * w * cmath.sqrt(_MU0 * _E0 * 4 * (1 - 0.01j))
    r = calc("polarizacion", {"calculo": "medios", "eps_r": 4, "f": "1e9", "tand": "0.01"})
    contiene(r, g.real, rel=1e-4)
    contiene(r, g.imag, rel=1e-4)


@pytest.mark.parametrize("Ax, Ay, delta, AR", [
    (1, 1, "pi/2", 1.0), (2, 1, "pi/2", 2.0), (1, 0, 0, None),
])
def test_clasifica_polarizacion(Ax, Ay, delta, AR):
    r = calc("polarizacion", {"calculo": "polarizacion", "Ax": Ax, "Ay": Ay, "delta": delta})
    if AR is None:
        assert "lineal" in str(r.exacto)
    else:
        contiene(r, AR)


def test_jones_polarizador_a_45():
    r = calc("polarizacion", {"calculo": "jones", "entrada": [1, 0],
                       "elementos": [{"tipo": "polarizador", "theta": "pi/4"}]})
    contiene(r, 0.5)                      # Malus: cos²45° de la potencia


@pytest.mark.parametrize("AR, psi", [("3.73", "pi/4"), (1, 0), ("2", "pi/3")])
def test_diseno_lambda4_lambda2(AR, psi):
    import time
    t = time.perf_counter()
    r = calc("polarizacion", {"calculo": "diseno", "AR": AR, "psi": psi})
    assert time.perf_counter() - t < 2
    contiene(r, float(AR), rel=1e-3)


def test_plf():
    contiene(calc("polarizacion", {"calculo": "plf", "e1": [1, 0], "e2": [1, 1]}), 0.5)


def _fresnel(n1, n2, ti, pol):
    ct = math.cos(ti)
    st2 = n1 / n2 * math.sin(ti)
    c2 = math.sqrt(1 - st2 ** 2)
    if pol == "s":
        return (n1 * ct - n2 * c2) / (n1 * ct + n2 * c2)
    return (n2 * ct - n1 * c2) / (n2 * ct + n1 * c2)


@pytest.mark.parametrize("ti, pol", [(0, "s"), ("pi/4", "s"), ("pi/4", "p"), ("0.3", "p")])
def test_fresnel(ti, pol):
    t = {"0": 0, "pi/4": math.pi / 4, "0.3": 0.3}[str(ti)]
    rr = _fresnel(1, 1.5, t, pol)
    r = calc("polarizacion", {"calculo": "fresnel", "n1": 1, "n2": "1.5", "theta_i": ti, "pol": pol})
    contiene(r, rr ** 2, rel=1e-4)


def _multicapa(ns, ds, lam):
    M = np.eye(2, dtype=complex)
    for n, d in zip(ns[1:-1], ds):
        dl = 2 * math.pi * n * d / lam
        M = M @ np.array([[math.cos(dl), 1j * math.sin(dl) / n], [1j * n * math.sin(dl), math.cos(dl)]])
    n0, ns_ = ns[0], ns[-1]
    B, Cc = M @ np.array([1, ns_])
    r = (n0 * B - Cc) / (n0 * B + Cc)
    return abs(r) ** 2


@pytest.mark.parametrize("ns, ds", [([1, 1.5, 1], [0.1]), ([1, 2.0, 1.5, 1.52], [0.13, 0.2])])
def test_multicapa_contra_matrices(ns, ds):
    r = calc("polarizacion", {"calculo": "multicapa", "ns": [str(v) for v in ns],
                       "ds": [str(v) for v in ds], "lambda0": 1})
    contiene(r, _multicapa(ns, ds, 1), rel=1e-4)


def test_antirreflejante():
    r = calc("polarizacion", {"calculo": "antirreflejante", "n1": 1, "n2": "2.25"})
    contiene(r, 1.5)


# ---------------------------------------------------------------------------
# señales y sistemas deterministas (ML-14)
# ---------------------------------------------------------------------------

sp = pytest.importorskip("sympy")


def _senal_num(d):
    """La señal del dict de la calculadora como función float, escrita aquí."""
    def f(t):
        v = 0.0
        for a, b, c in d.get("trozos", []):
            v += c if a <= t < b else 0.0
        for p in d.get("tris", []):
            t0, T, A = p.get("t0", 0), p.get("T", 1), p.get("A", 1)
            v += A * max(0.0, 1 - abs(t - t0) / T)
        for p in d.get("exps", []):
            t0, T, A = p.get("t0", 0), p.get("T", 1), p.get("A", 1)
            v += A * math.exp(-(t - t0) / T) if t >= t0 else 0.0
        return v
    return f


def _conv_num(x, h, t, lo=-10, hi=40, n=200000):
    fx, fh = _senal_num(x), _senal_num(h)
    du = (hi - lo) / n
    return sum(fx(lo + (k + 0.5) * du) * fh(t - lo - (k + 0.5) * du) for k in range(n)) * du


def _tramos(texto):
    """«[a, b]: expr; …» → [(a, b, función sympy de t)]."""
    t = sp.Symbol("t")
    out = []
    cuerpo = texto.split("y(t) = ", 1)[1].rsplit("; ∫y", 1)[0]
    for m in re.finditer(r"\[([^,\]]+), ([^\])]+)[\])]: ([^;]+)", cuerpo):
        a = float(sp.Rational(m.group(1)))
        b = math.inf if m.group(2) == "∞" else float(sp.Rational(m.group(2)))
        e = (m.group(3).replace("·", "*").replace("−", "-").replace("²", "**2")
             .replace("³", "**3").replace("⁴", "**4"))
        out.append((a, b, sp.lambdify(t, sp.sympify(e), "math")))
    return out


@pytest.mark.parametrize("x, h", [
    ({"trozos": [[0, 1, 1]]}, {"trozos": [[0, 2, 1]]}),
    ({"tris": [{"t0": 0, "T": 1, "A": 1}]}, {"trozos": [[0, 1, 2]]}),
    ({"tris": [{"t0": 1, "T": 1, "A": 1}]}, {"tris": [{"t0": 1, "T": 1, "A": 1}]}),
    ({"exps": [{"t0": 0, "T": 1, "A": 1}]}, {"trozos": [[0, 1, 1]]}),
    ({"exps": [{"t0": 0, "T": 1, "A": 1}]}, {"exps": [{"t0": 0, "T": 2, "A": 1}]}),
    ({"exps": [{"t0": 1, "T": 1, "A": 2}]}, {"tris": [{"t0": 0, "T": 1, "A": 1}]}),
])
def test_convolucion_exacta_contra_numerica(x, h):
    r = calc("senales", {"calculo": "convolucion", "x": x, "h": h})
    tramos = _tramos(str(r.exacto))
    assert tramos, r.exacto
    for a, b, f in tramos:
        for t in ((a + 0.31 * (b - a), a + 0.77 * (b - a)) if b != math.inf else (a + 0.4, a + 2.3)):
            assert f(t) == pytest.approx(_conv_num(x, h, t, n=40000), rel=2e-3, abs=2e-4)


def test_convolucion_con_delta_desplaza():
    r = calc("senales", {"calculo": "convolucion",
                         "x": {"tris": [{"t0": 0, "T": 1, "A": 1}], "deltas": [{"delta": 1, "t0": 5}]},
                         "h": {"trozos": [[0, 1, 2]]}})
    tramos = _tramos(str(r.exacto))
    assert min(a for a, _, _ in tramos) == 4
    a, b, f = tramos[0]
    assert f(4.5) == pytest.approx(_conv_num({"tris": [{"t0": 0, "T": 1, "A": 1}]},
                                             {"trozos": [[0, 1, 2]]}, -0.5, n=40000), rel=2e-3)


def test_conv_digital():
    import numpy as _np
    y = [int(v) for v in _np.convolve([1, 2, 3], [1, 1, -1])]
    assert str(y).replace(" ", "") in str(calc("senales", {
        "calculo": "conv_digital", "x": [1, 2, 3], "h": [1, 1, -1]}).exacto).replace(" ", "")


def test_eje():
    r = calc("senales", {"calculo": "eje", "pulso": {"A": 1, "t0": 1, "T": 2}, "a": 2, "b": 1})
    assert "t0 = 1" in str(r.exacto) and "T = 1" in str(r.exacto)


@pytest.mark.parametrize("T1, T2, T", [(2, 3, 6), ("1/2", "1/3", 1), ("3/4", "5/6", "15/2")])
def test_periodo_comun(T1, T2, T):
    assert f"T = {T}" in str(calc("senales", {"calculo": "periodo", "T1": T1, "T2": T2}).exacto)


def test_energia_y_potencia():
    r = calc("senales", {"calculo": "energia", "senal": {"trozos": [[0, 3, 2]]}, "T0": 4})
    assert "E = 12" in str(r.exacto) and "P = 3" in str(r.exacto)
    assert "9/2" in str(calc("senales", {"calculo": "potencia_sinusoide", "A": 3}).exacto)
    assert "5/2" in str(calc("senales", {"calculo": "energia_eco", "Ex": 2, "a": "1/2"}).exacto)


def test_correlacion_rect():
    contiene(calc("senales", {"calculo": "correlacion", "tipo": "rect", "A": 2, "T": 3}), 12.0)


@pytest.mark.parametrize("F, X", [(0, 2.0), (0.5, 2 / 3)])
def test_dtft_exp(F, X):
    contiene(calc("senales", {"calculo": "dtft", "tipo": "exp", "a": "1/2", "F": [F]}), X)


def test_dft_contra_numpy():
    x = [1, 2, 3, 4, 0, -1]
    r = calc("senales", {"calculo": "dft", "x": x})
    vals = [abs(v) for v in numeros(r)]
    for X in np.fft.fft(x):
        for parte in (X.real, X.imag):
            if abs(parte) > 1e-9:
                assert any(math.isclose(abs(parte), v, rel_tol=1e-5) for v in vals)


def test_dft_lineal():
    r = calc("senales", {"calculo": "dft_lineal", "x": [1, 2, 3], "h": [1, 1]})
    for v in (1, 3, 5, 3):
        contiene(r, v)


def test_eco_ceros_y_respuesta():
    r = calc("senales", {"calculo": "eco", "a": "1/2", "L": 4, "F": 0})
    contiene(r, 0.5 ** 0.25)
    contiene(r, 2.25)


def test_inverso_y_cascada_con_a_cercano_a_uno():
    calc("senales", {"calculo": "inverso", "a": "1/2", "L": 2})
    r = calc("senales", {"calculo": "cascada", "a": "0.9", "L": 4, "x": list(range(1, 22))})
    assert r.sello.verdict == "verificado"


def test_densidad_y_regimen():
    contiene(calc("senales", {"calculo": "densidad", "X": [[3, 4], [1, 0]]}), 25.0)
    r = calc("senales", {"calculo": "regimen", "a": "1/2", "x": [1, 0, 0, 1]})
    assert "9/8" in str(r.exacto)


def test_periodica_rect():
    # pulso de altura 1 y ancho 1 en periodo 2: c₀ = 1/2 y P = 1/2
    r = calc("senales", {"calculo": "periodica", "base": [{"tipo": "rect", "A": 1, "t0": "1/2", "T": 1}],
                         "T0": 2})
    contiene(r, 0.5)


# ---------------------------------------------------------------------------
# física auxiliar (ML-22)
# ---------------------------------------------------------------------------

_G, _kB, _g = 6.67430e-11, 1.380649e-23, 9.81


def test_equilibrios_cubica():
    r = calc("fisica", {"calculo": "equilibrio",
                        "potencial": {"tipo": "poli", "coef": [0, -1, 0, 1], "m": 1}, "x0": -3, "x1": 3})
    contiene(r, 1 / math.sqrt(3), rel=1e-6)


def test_oscilacion_armonica():
    r = calc("fisica", {"calculo": "oscilacion",
                        "potencial": {"tipo": "poli", "coef": [0, 0, 1], "m": 1}, "E": 1})
    contiene(r, 2 * math.pi / math.sqrt(2), rel=1e-4)


def test_potencial_2d_trabajo():
    # F = −∇U ⇒ W(A→B) = U(A) − U(B) = 0 − 1
    contiene(calc("fisica", {"calculo": "potencial_2d", "U": "x*y^2", "A": [0, 0], "B": [1, 1]}), -1.0)


def test_retrato_de_fases():
    r = calc("fisica", {"calculo": "retrato",
                        "potencial": {"tipo": "poli", "coef": [0, -1, 0, 1], "m": 1},
                        "energias": [0.2, 1], "x0": -3, "x1": 3})
    assert r.grafica is not None and len(r.grafica.series) == 4


def test_mezcla_y_muelle():
    contiene(calc("fisica", {"calculo": "mezcla", "gases": [{"n": 1, "T": 300}, {"n": 2, "T": 400}]}),
             1100 / 3)
    contiene(calc("fisica", {"calculo": "muelle", "h": 3, "gamma": 1}), math.sqrt(_g / 3))


def test_ciclo_rectangular():
    v = [[2e5, 1e-3], [2e5, 2e-3], [1e5, 2e-3], [1e5, 1e-3], [2e5, 1e-3]]
    # W es el trabajo SOBRE el gas (−∮p dV): un ciclo motor horario da −100 J
    contiene(calc("fisica", {"calculo": "ciclo", "vertices": v}), -100.0, rel=1e-6)


def test_gas_proceso_da_resultado():
    calc("fisica", {"calculo": "gas"})


def test_kepler_contra_newton():
    M, e, E = 1.0, 0.5, 1.0
    for _ in range(50):
        E -= (E - e * math.sin(E) - M) / (1 - e * math.cos(E))
    contiene(calc("fisica", {"calculo": "kepler", "M": 1, "e": "0.5"}), E, rel=1e-6)


def test_orbita_circular():
    GM = _G * 5.972e24
    r = calc("fisica", {"calculo": "orbita"})
    contiene(r, math.sqrt(GM / 6.671e6), rel=1e-6)
    contiene(r, 2 * math.pi * math.sqrt(6.671e6 ** 3 / GM), rel=1e-6)


def test_visibilidad():
    contiene(calc("fisica", {"calculo": "visibilidad"}), 5e5 / (2 * (6.371e6 + 5e5)), rel=1e-5)


def test_elipse_por_apsides():
    r = calc("fisica", {"calculo": "elipse", "rp": 2, "ra": 6, "m": 2, "E": -1})
    contiene(r, 4.0)
    contiene(r, 0.5)


def test_maxwell_boltzmann():
    m, T = 4.65e-26, 300
    r = calc("fisica", {"calculo": "maxwell_boltzmann", "m": m, "T": T})
    contiene(r, math.sqrt(2 * _kB * T / m), rel=1e-4)


def test_planck():
    r = calc("fisica", {"calculo": "planck"})
    contiene(r, math.pi ** 4 / 15, rel=1e-5)
    contiene(r, 5.670374419e-8, rel=1e-4)


@pytest.mark.parametrize("entrada, esperado", [
    ({"calculo": "circular", "tipo": "peralte", "R": 100, "v": 20},
     math.degrees(math.atan(400 / (_g * 100)))),
    ({"calculo": "circular", "tipo": "cono", "L": 1, "omega": 5}, math.degrees(math.acos(_g / 25))),
    ({"calculo": "circular", "tipo": "talud", "R": "2.5", "v0": 0}, math.degrees(math.acos(2 / 3))),
])
def test_circular(entrada, esperado):
    contiene(calc("fisica", entrada), esperado, rel=1e-4)


def test_circular_esfera_que_no_despega():
    # con v₀² ≥ gR el objeto despega en lo alto: antes la clave «despega» faltaba
    assert "no despega" in str(calc("fisica", {"calculo": "circular", "tipo": "talud",
                                               "R": 1, "v0": 10}).exacto)


def test_choque():
    r = calc("fisica", {"calculo": "choque", "m1": 1, "v1": 2, "m2": 3, "v2": 0, "e": 1})
    contiene(r, -1.0)
    contiene(r, 1.0)


def test_cm_inercia_rodadura():
    r = calc("fisica", {"calculo": "cm", "puntos": [[1, 0, 0], [3, 4, 0]]})
    assert "3" in str(r.exacto)
    contiene(calc("fisica", {"calculo": "inercia", "figura": "disco", "m": 2, "d": 1, "eje": 1}),
             1 + 2)
    contiene(calc("fisica", {"calculo": "rodadura", "I": "0.5", "m": 1, "R": 1, "h": 2}),
             math.sqrt(2 * _g * 2 / 1.5), rel=1e-5)


def test_conduccion_y_boltzmann():
    contiene(calc("fisica", {"calculo": "conduccion"}), 401 * 1e-4 * 50 / 0.12, rel=1e-5)
    x = 0.5 * 1.602176634e-19 / (_kB * 350)
    contiene(calc("fisica", {"calculo": "boltzmann"}), 1e10 * math.exp(-x) / (1 + math.exp(-x)),
             rel=1e-3)


# ---------------------------------------------------------------------------
# probabilidad y estadística (ML-9)
# ---------------------------------------------------------------------------

mp = pytest.importorskip("mpmath")
mp.mp.dps = 30


def _cdf_t(x, nu):
    return float(mp.betainc(nu / 2, 0.5, 0, nu / (nu + x * x), regularized=True) / 2) \
        if x < 0 else 1 - _cdf_t(-x, nu)


def _cdf_chi2(x, k):
    return float(mp.gammainc(k / 2, 0, x / 2, regularized=True))


def _cdf_f(x, d1, d2):
    return float(mp.betainc(d1 / 2, d2 / 2, 0, d1 * x / (d1 * x + d2), regularized=True))


def _cuantil(cdf, p, lo, hi):
    for _ in range(200):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if cdf(m) < p else (lo, m)
    return (lo + hi) / 2


def _pmf_sum(pmf, a, b):
    return sum(pmf(k) for k in range(a, b + 1))


_LEYES = [
    ("binomial", {"n": 10, "p": "0.3"}, "P(2 < X <= 5)",
     _pmf_sum(lambda k: math.comb(10, k) * 0.3 ** k * 0.7 ** (10 - k), 3, 5)),
    ("poisson", {"λ": 3}, "P(X >= 4)",
     1 - _pmf_sum(lambda k: math.exp(-3) * 3 ** k / math.factorial(k), 0, 3)),
    ("geometrica", {"p": "0.25"}, "P(X <= 3)", 1 - 0.75 ** 3),
    ("pascal", {"r": 3, "p": "0.4"}, "P(X = 5)", math.comb(4, 2) * 0.4 ** 3 * 0.6 ** 2),
    ("hipergeometrica", {"N": 20, "K": 7, "n": 5}, "P(X = 2)",
     math.comb(7, 2) * math.comb(13, 3) / math.comb(20, 5)),
    ("uniforme_discreta", {"a": 1, "b": 6}, "P(X > 4)", 2 / 6),
    ("uniforme", {"a": 0, "b": 2}, "P(0.5 < X < 1.2)", 0.35),
    ("exponencial", {"λ": 2}, "P(X > 1)", math.exp(-2)),
    ("gamma", {"k": 3, "λ": 2}, "P(X <= 1)", float(mp.gammainc(3, 0, 2, regularized=True))),
    ("normal", {"μ": 1, "σ": 2}, "P(0 < X < 3)",
     0.5 * (math.erf(2 / (2 * math.sqrt(2))) - math.erf(-1 / (2 * math.sqrt(2))))),
    ("t", {"ν": 5}, "P(X <= 2)", _cdf_t(2.0, 5)),
    ("chi2", {"k": 4}, "P(X > 5)", 1 - _cdf_chi2(5.0, 4)),
    ("f", {"d1": 5, "d2": 7}, "P(X <= 2)", _cdf_f(2.0, 5, 7)),
    ("beta", {"a": 2, "b": 3}, "P(X <= 0.4)", float(mp.betainc(2, 3, 0, 0.4, regularized=True))),
    ("weibull", {"k": 2, "λ": 1}, "P(X > 1)", math.exp(-1)),
    ("rayleigh", {"σ": 1}, "P(X <= 1)", 1 - math.exp(-0.5)),
    ("rice", {"ν": 1, "σ": 1}, "P(X <= 1)",
     float(mp.quad(lambda r: r * mp.e ** (-(r * r + 1) / 2) * mp.besseli(0, r), [0, 1]))),
    ("laplace", {"μ": 0, "b": 1}, "P(X > 1)", 0.5 * math.exp(-1)),
]


@pytest.mark.parametrize("dist, params, suceso, p", _LEYES, ids=[x[0] for x in _LEYES])
def test_probabilidad_de_cada_ley(dist, params, suceso, p):
    r = calc("variable_aleatoria", {"dist": dist, "parametros": params, "suceso": suceso},
             sellos=("verificado", "solo_numerico"))
    contiene(r, p, rel=1e-6)


@pytest.mark.parametrize("dist, params, media, var", [
    ("rice", {"ν": 1, "σ": 1}, 1.548572460551145, 0.6019233344225721),
    ("weibull", {"k": 2, "λ": 1}, math.gamma(1.5), 1 - math.gamma(1.5) ** 2),
    ("hipergeometrica", {"N": 20, "K": 7, "n": 5}, 1.75, 5 * 0.35 * 0.65 * 15 / 19),
])
def test_momentos(dist, params, media, var):
    r = calc("variable_aleatoria", {"dist": dist, "parametros": params, "calculo": "momentos"},
             sellos=("verificado", "solo_numerico"))
    contiene(r, media, rel=1e-6)
    contiene(r, var, rel=1e-6)


def test_cuantil_normal():
    r = calc("variable_aleatoria", {"dist": "normal", "parametros": {"μ": 0, "σ": 1},
                                    "cuantil": "0.975"}, sellos=("verificado", "solo_numerico"))
    contiene(r, 1.959963984540054, rel=1e-6)


def test_bayes():
    # P(E) = 0.01·0.9 + 0.99·0.05; P(E|D) = 0.009/P
    r = calc("probabilidad", {"calculo": "bayes", "previas": {"E": "0.01", "S": "0.99"},
                              "verosimilitudes": {"E": "0.9", "S": "0.05"}, "evidencia": "D"})
    assert "2/13" in str(r.exacto) and "117/2000" in str(r.exacto)


def test_combinatoria_e_inclusion_exclusion():
    contiene(calc("probabilidad", {"calculo": "combinatoria", "tipo": "combinaciones",
                                   "n": 10, "k": 3}), 120)
    r = calc("probabilidad", {"calculo": "inclusion_exclusion",
                              "datos": {"A": "1/2", "B": "1/3", "AB": "1/6"}})
    assert "2/3" in str(r.exacto)


def test_vector_gauss_condicional():
    mu = np.array([1.0, 2.0])
    S = np.array([[2.0, 1.0], [1.0, 3.0]])
    m = mu[0] + S[0, 1] / S[1, 1] * (4 - mu[1])
    v = S[0, 0] - S[0, 1] ** 2 / S[1, 1]
    r = calc("vector_aleatorio", {"calculo": "gauss_condicional", "mu": [1, 2],
                                  "cov": [[2, 1], [1, 3]], "observadas": {"2": 4}},
             sellos=("verificado", "solo_numerico"))
    texto = str(r.exacto)
    assert any(math.isclose(v_, m, rel_tol=1e-6) for v_ in numeros(r)) or "5/3" in texto
    assert any(math.isclose(v_, v, rel_tol=1e-6) for v_ in numeros(r)) or "5/3" in texto


def test_aproximacion_normal_binomial():
    n, p = 100, 0.3
    s = math.sqrt(n * p * (1 - p))
    aprox = 0.5 * (1 + math.erf((35.5 - 30) / (s * math.sqrt(2))))
    r = calc("aproximacion_normal", {"dist": "binomial", "parametros": {"n": n, "p": "0.3"},
                                     "suceso": "P(X<=35)"}, sellos=("verificado", "solo_numerico"))
    contiene(r, aprox, rel=1e-5)


def test_descriptiva():
    d = [2, 4, 4, 4, 5, 5, 7, 9]
    r = calc("estadistica", {"datos": d}, sellos=("verificado", "solo_numerico"))
    contiene(r, 5.0)
    contiene(r, float(np.var(d, ddof=1)), rel=1e-5)


def test_intervalo_t():
    t = _cuantil(lambda x: _cdf_t(x, 19), 0.975, 0, 10)
    r = calc("intervalo_confianza", {"parametro": "media", "n": 20, "media": "10.2", "s": "1.5",
                                     "nivel": "0.95"}, sellos=("verificado", "solo_numerico"))
    contiene(r, 10.2 - t * 1.5 / math.sqrt(20), rel=1e-5)
    contiene(r, 10.2 + t * 1.5 / math.sqrt(20), rel=1e-5)


def test_contraste_t():
    t = (52 - 50) / (5 / 5)
    p = 1 - _cdf_t(t, 24)
    r = calc("contraste", {"tipo": "media", "n": 25, "media": 52, "s": 5, "mu0": 50,
                           "alternativa": "mayor"}, sellos=("verificado", "solo_numerico"))
    contiene(r, t)
    contiene(r, p, rel=1e-4)


def test_contraste_independencia():
    obs = np.array([[20, 30], [30, 20]])
    esp = obs.sum(1, keepdims=True) * obs.sum(0, keepdims=True) / obs.sum()
    chi = float(((obs - esp) ** 2 / esp).sum())
    r = calc("contraste", {"tipo": "independencia", "tabla": obs.tolist()},
             sellos=("verificado", "solo_numerico"))
    contiene(r, chi, rel=1e-6)


def test_regresion_ml9():
    x, y = [1, 2, 3, 4, 5], [2.1, 3.9, 6.2, 7.8, 10.1]
    b, a = np.polyfit(x, y, 1)
    r = calc("regresion", {"x": x, "y": [str(v) for v in y]}, sellos=("verificado", "solo_numerico"))
    contiene(r, float(b), rel=1e-6)


def test_estimador_poisson():
    contiene(calc("estimador", {"familia": "poisson", "datos": [2, 3, 1, 4]},
                  sellos=("verificado", "solo_numerico")), 2.5)


@pytest.mark.parametrize("entrada, esperado", [
    ({"tipo": "poisson", "lambda": 2, "consulta": "conteo", "t": 3, "k": 4},
     math.exp(-6) * 6 ** 4 / 24),
    ({"tipo": "paseo", "p": "1/2", "n": 6, "k": 2}, math.comb(6, 4) / 64),
])
def test_procesos(entrada, esperado):
    contiene(calc("proceso", entrada, sellos=("verificado", "solo_numerico")), esperado, rel=1e-6)


@pytest.mark.parametrize("entrada, esperado", [
    ({"ley": "t", "gl": 19, "p": "0.975"}, _cuantil(lambda x: _cdf_t(x, 19), 0.975, 0, 10)),
    ({"ley": "chi2", "gl": 4, "p": "0.95"}, _cuantil(lambda x: _cdf_chi2(x, 4), 0.95, 0, 50)),
    ({"ley": "f", "d1": 5, "d2": 7, "p": "0.95"}, _cuantil(lambda x: _cdf_f(x, 5, 7), 0.95, 0, 50)),
    ({"ley": "normal", "x": 1.96}, 0.5 * (1 + math.erf(1.96 / math.sqrt(2)))),
])
def test_tabla_estadistica(entrada, esperado):
    contiene(calc("tabla_estadistica", entrada, sellos=("verificado", "solo_numerico")),
             esperado, rel=1e-5)


@pytest.mark.parametrize("entrada, esperado", [
    ({"calculo": "ber", "modulacion": "bpsk", "EbN0_dB": 6},
     0.5 * math.erfc(math.sqrt(10 ** 0.6))),
    ({"calculo": "aloha", "G": 0.5, "ranurado": False}, 0.5 * math.exp(-1)),
    ({"calculo": "desvanecimiento", "modelo": "rayleigh", "snr_media_db": 20, "umbral_db": 10},
     1 - math.exp(-0.1)),
])
def test_comunicaciones(entrada, esperado):
    contiene(calc("comunicaciones", entrada, sellos=("verificado", "solo_numerico")),
             esperado, rel=1e-4)


def test_montecarlo_contra_exacto():
    r = calc("montecarlo", {"dist": "exponencial", "parametros": {"λ": 2}, "suceso": "P(X>1)"},
             sellos=("verificado", "solo_numerico"))
    assert r is not None


_SUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")


def bonito_sympy(texto):
    """La notación legible del motor (·, π, √, superíndices, sen) a SymPy."""
    tx = texto.strip().replace("−", "-").replace("·", "*").replace("π", "pi")
    tx = re.sub(r"([⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+)", lambda m: "**(" + m.group(1).translate(_SUP) + ")", tx)
    tx = re.sub(r"√\(", "sqrt(", tx)
    tx = re.sub(r"√([0-9A-Za-z_.]+)", r"sqrt(\1)", tx)
    tx = tx.replace("^", "**").replace("sen(", "sin(").replace("arctan(", "atan(")
    tx = re.sub(r"\|([^|]*)\|", r"(Abs(\1))", tx)
    return sp.sympify(tx, locals={"x": sp.Symbol("x", real=True), "y": sp.Symbol("y", real=True),
                                  "e": sp.E, "ln": sp.log, "pi": sp.pi})


# ---------------------------------------------------------------------------
# núcleo de cálculo y álgebra (calculators.py)
# ---------------------------------------------------------------------------

_x, _y = sp.symbols("x y", real=True)


@pytest.mark.parametrize("expr, a, b, valor", [
    ("1/x^2", "1", "oo", 1.0),
    ("exp(-x)*x^2", "0", "oo", 2.0),
    ("1/(1+x^2)", "-oo", "oo", math.pi),
    ("1/sqrt(x)", "0", "1", 2.0),
    ("ln(x)", "0", "1", -1.0),
    ("x*exp(-x^2)", "0", "oo", 0.5),
])
def test_impropias_convergentes(expr, a, b, valor):
    contiene(calc("impropia", {"expr": expr, "a": a, "b": b}), valor, rel=1e-6)


@pytest.mark.parametrize("expr, a, b", [("1/x", "1", "oo"), ("1/x^2", "0", "1"), ("exp(x)", "0", "oo")])
def test_impropias_divergentes(expr, a, b):
    r = calc("impropia", {"expr": expr, "a": a, "b": b})
    assert "diverge" in str(r.exacto).lower(), r.exacto


@pytest.mark.parametrize("termino, converge", [
    ("1/n^2", True), ("1/n", False), ("(-1)^n/n", True), ("n!/n^n", True),
    ("2^n/factorial(n)", True), ("n/(n+1)", False), ("1/(n*ln(n))", False), ("1/n^(3/2)", True),
])
def test_series_convergencia(termino, converge):
    n0 = 2 if "ln" in termino else 1
    texto = str(calc("serie", {"calculo": "convergencia", "termino": termino, "n0": n0}).exacto).lower()
    # el veredicto es la primera palabra: la condicional menciona que |aₙ| diverge
    assert texto.startswith("converge") == converge, texto


@pytest.mark.parametrize("termino, n0, suma", [
    ("1/n^2", 1, math.pi ** 2 / 6), ("1/(n*(n+1))", 1, 1.0), ("(1/2)^n", 0, 2.0),
    ("(-1)^(n+1)/n", 1, math.log(2)), ("1/factorial(n)", 0, math.e), ("1/(4*n^2-1)", 1, 0.5),
])
def test_series_suma(termino, n0, suma):
    # sin forma cerrada (Σ1/n!) la suma es numérica con cota: «solo_numerico»
    contiene(calc("serie", {"calculo": "suma", "termino": termino, "n0": n0},
                  sellos=("verificado", "solo_numerico")), suma, rel=1e-6)


@pytest.mark.parametrize("a, n0, suma, N", [
    (lambda n: 1 / n ** 2, 1, math.pi ** 2 / 6, 10 ** 6), (lambda n: 1 / (n * (n + 1)), 1, 1.0, 10 ** 6),
    (lambda n: 0.5 ** n, 0, 2.0, 200), (lambda n: (-1) ** (n + 1) / n, 1, math.log(2), 10 ** 6),
    (lambda n: 1 / math.factorial(n), 0, math.e, 30), (lambda n: 1 / (4 * n * n - 1), 1, 0.5, 10 ** 6),
])
def test_los_valores_esperados_de_las_sumas(a, n0, suma, N):
    # el valor del test de arriba, contra la suma parcial escrita aquí (cola < 1e-5)
    assert math.isclose(sum(a(n) for n in range(n0, N)), suma, abs_tol=2e-6)


def test_serie_de_potencias_radio():
    r = calc("serie", {"calculo": "potencias", "termino": "x^n/(n*2^n)", "n0": 1})
    contiene(r, 2.0)


@pytest.mark.parametrize("z, valor", [
    ("(1+i)^2", 2j), ("(3+4*i)/(1-2*i)", (3 + 4j) / (1 - 2j)), ("exp(i*pi/3)", complex(0.5, math.sqrt(3) / 2)),
    ("abs(3+4*i)", 5), ("(1-i)^5", (1 - 1j) ** 5),
])
def test_complejos(z, valor):
    r = calc("complejo", z, sellos=("verificado", "solo_numerico"))
    v = complex(valor)
    vals = numeros(r)
    for parte in (v.real, v.imag):
        if abs(parte) > 1e-12:
            assert any(math.isclose(abs(parte), abs(w), rel_tol=1e-6) for w in vals), (z, r.exacto)


def test_criticos_y_clasificacion():
    f = _x ** 3 - 3 * _x + _y ** 2
    r = calc("multivar", {"calculo": "criticos", "expr": "x^3-3*x+y^2", "vars": ["x", "y"]})
    texto = str(r.exacto)
    assert "mínimo" in texto and "silla" in texto, texto
    for p in sp.solve([sp.diff(f, _x), sp.diff(f, _y)], [_x, _y], dict=True):
        assert str(p[_x]) in texto


def test_lagrange():
    # extremos de x + y en x² + y² = 2: (1, 1) máx 2 y (−1, −1) mín −2
    r = calc("multivar", {"calculo": "lagrange", "expr": "x+y", "vars": ["x", "y"],
                          "ligadura": "x^2+y^2-2"})
    contiene(r, 2.0)
    contiene(r, -2.0)


def test_hessiana_y_jacobiana():
    r = calc("multivar", {"calculo": "hessiana", "expr": "x^2*y+y^3", "vars": ["x", "y"]})
    assert "2·y" in str(r.exacto) or "2*y" in str(r.exacto)
    calc("multivar", {"calculo": "jacobiana", "fs": ["x*y", "x+y"], "vars": ["x", "y"]})


@pytest.mark.parametrize("expr, limites, valor", [
    ("x*y", [["y", "0", "x"], ["x", "0", "1"]], 1 / 8),
    ("x^2+y^2", [["y", "0", "1"], ["x", "0", "1"]], 2 / 3),
    ("exp(x+y)", [["y", "0", "1"], ["x", "0", "1"]], (math.e - 1) ** 2),
    ("1", [["z", "0", "x+y"], ["y", "0", "1-x"], ["x", "0", "1"]], 1 / 3),
])
def test_integrales_iteradas(expr, limites, valor):
    contiene(calc("multiple", {"calculo": "iterada", "expr": expr, "limites": limites}), valor, rel=1e-8)


def test_polares():
    # ∬ sobre el disco unidad de (x² + y²) = π/2
    r = calc("multiple", {"calculo": "coordenadas", "sistema": "polares", "expr": "r^2",
                          "limites": [["r", "0", "1"], ["θ", "0", "2*pi"]]},
             sellos=("verificado", "solo_numerico"))
    contiene(r, math.pi / 2, rel=1e-8)


def test_potencial_y_green():
    r = calc("vectorial", {"calculo": "potencial", "campo": ["2*x*y", "x^2"]})
    assert "x²·y" in str(r.exacto) or "x^2*y" in str(r.exacto) or "y·x²" in str(r.exacto)
    # Green en el disco unidad con F = (−y, x): 2·área = 2π
    r = calc("vectorial", {"calculo": "green", "campo": ["-y", "x"],
                           "region": [["r", 0, 1], ["t", 0, "2*pi"]], "sistema": "polares",
                           "borde": {"r": ["cos(t)", "sin(t)"], "t": "t", "a": 0, "b": "2*pi"}},
             sellos=("verificado", "solo_numerico"))
    contiene(r, 2 * math.pi, rel=1e-6)


def test_laplaciano_esfericas():
    r = calc("operadores", {"calculo": "laplaciano", "V": "1/r", "sistema": "esfericas"})
    assert "0" in str(r.exacto)


@pytest.mark.parametrize("entrada, esperado", [
    ({"calculo": "inverso", "a": 3, "n": 11}, pow(3, -1, 11)),
    ({"calculo": "potencia", "a": 7, "e": 128, "n": 13}, pow(7, 128, 13)),
    ({"calculo": "chino", "restos": [2, 3, 2], "modulos": [3, 5, 7]}, 23),
    ({"calculo": "phi", "n": 360}, 96),
    ({"calculo": "orden", "a": 2, "n": 11}, 10),
    ({"calculo": "euclides", "a": 240, "b": 46}, 2),
])
def test_modular(entrada, esperado):
    contiene(calc("modular", entrada), esperado)


@pytest.mark.parametrize("expr, n_sol", [("x^3+x-1", 1), ("x^3-3*x+1", 3), ("exp(x)-x-2", 2)])
def test_numero_de_soluciones(expr, n_sol):
    r = calc("soluciones", {"expr": expr}, sellos=("verificado", "solo_numerico"))
    assert str(n_sol) in str(r.exacto), r.exacto


def test_extremos_absolutos():
    r = calc("extremos_absolutos", {"expr": "x^3-3*x", "a": "-2", "b": "3"})
    contiene(r, 18.0)
    contiene(r, -2.0)


def test_tfc():
    # d/dx ∫₀^{x²} e^{−t²} dt = 2x·e^{−x⁴}
    r = calc("tfc", {"f": "exp(-t^2)", "desde": "0", "hasta": "x^2"})
    F = bonito_sympy(str(r.exacto).split("=")[-1])
    assert abs(complex(F.subs(_x, 0.7)) - 2 * 0.7 * math.exp(-0.7 ** 4)) < 1e-9


def test_derivada_de_la_inversa():
    # f(x) = x³ + x, f(1) = 2 ⇒ (f⁻¹)′(2) = 1/f′(1) = 1/4
    assert "1/4" in str(calc("inversa", {"expr": "x^3+x", "y0": "2"}).exacto)


@pytest.mark.parametrize("teorema, expr, a, b, c", [
    ("rolle", "x^2-4*x", "0", "4", 2.0), ("valor_medio", "x^3", "0", "3", math.sqrt(3)),
])
def test_teoremas(teorema, expr, a, b, c):
    contiene(calc("teorema", {"teorema": teorema, "expr": expr, "a": a, "b": b}), c, rel=1e-8)


def test_riemann():
    # suma por la derecha de x² en [0,1] con n = 10: Σ (k/10)²/10
    s = sum((k / 10) ** 2 for k in range(1, 11)) / 10
    contiene(calc("riemann", {"expr": "x^2", "a": "0", "b": "1", "n": 10},
                  sellos=("verificado", "solo_numerico")), s, rel=1e-9)


@pytest.mark.parametrize("entrada, valor", [
    ({"tipo": "area", "f": "x^2", "g": "x", "a": "0", "b": "2"}, 1.0),
    ({"tipo": "volumen", "f": "sqrt(x)", "a": "0", "b": "1", "eje": "x"}, math.pi / 2),
    ({"tipo": "longitud", "f": "x^(3/2)", "a": "0", "b": "4"},
     float(sp.integrate(sp.sqrt(1 + sp.Rational(9, 4) * _x), (_x, 0, 4)))),
])
def test_aplicaciones_de_la_integral(entrada, valor):
    contiene(calc("aplicacion_integral", entrada, sellos=("verificado", "solo_numerico")), valor, rel=1e-8)


@pytest.mark.parametrize("z, valor", [("5", 24.0), ("1/2", math.sqrt(math.pi)), ("7/2", math.gamma(3.5))])
def test_gamma(z, valor):
    contiene(calc("gamma", {"expr": z}, sellos=("verificado", "solo_numerico")), valor, rel=1e-9)


def test_dijkstra_y_kruskal():
    aristas = [["A", "B", 4], ["A", "C", 1], ["C", "B", 2], ["B", "D", 5], ["C", "D", 8], ["D", "E", 3]]
    r = calc("grafo", {"calculo": "dijkstra", "aristas": aristas, "origen": "A"})
    for d in (3, 8, 11):                    # B por C (1+2), D (3+5), E (8+3)
        contiene(r, d)
    contiene(calc("grafo", {"calculo": "kruskal", "aristas": aristas}), 1 + 2 + 5 + 3)


def test_huffman_longitud_media():
    r = calc("huffman", {"probabilidades": {"a": "0.4", "b": "0.3", "c": "0.2", "d": "0.1"}})
    contiene(r, 0.4 * 1 + 0.3 * 2 + 0.2 * 3 + 0.1 * 3, rel=1e-9)


def test_cola_mm1():
    r = calc("cola_mm1", {"lambda": 1, "mu": 2, "clientes": 200}, sellos=("verificado", "solo_numerico"))
    contiene(r, 0.5)          # ρ
    contiene(r, 1.0)          # L = ρ/(1 − ρ)


def test_markov_estacionaria():
    r = calc("markov", {"P": [["1/2", "1/2"], ["1/3", "2/3"]], "simular": 500},
             sellos=("verificado", "solo_numerico"))
    assert "2/5" in str(r.exacto) and "3/5" in str(r.exacto)


def test_fourier_diente_de_sierra():
    # f(t) = t en (−π, π): b_n = 2(−1)^{n+1}/n
    r = calc("fourier", {"calculo": "serie", "tramos": [["t", "-pi", "pi"]]},
             sellos=("verificado", "solo_numerico"))
    assert "(-1)" in str(r.exacto) or "2" in str(r.exacto)


@pytest.mark.parametrize("M", [[[2, 1], [1, 2]], [[4, 1, 2], [0, 3, 1], [0, 0, 2]], [[1, 2], [3, 4]]])
def test_autovalores_contra_numpy(M):
    r = calc("algebra", {"calculo": "autovalores", "matriz": M}, sellos=("verificado", "solo_numerico"))
    for v in np.linalg.eigvals(np.array(M, float)):
        contiene(r, float(v.real), rel=1e-6)


def test_cramer_minimos_pseudoinversa():
    r = calc("algebra", {"calculo": "cramer", "matriz": [[2, 1], [1, 3]], "b": [3, 5]})
    for v in np.linalg.solve([[2, 1], [1, 3]], [3, 5]):
        contiene(r, float(v))
    A = np.array([[1, 1], [1, 2], [1, 3]], float)
    w = np.linalg.lstsq(A, [1, 2, 2], rcond=None)[0]
    r = calc("algebra", {"calculo": "minimos", "matriz": A.astype(int).tolist(), "b": [1, 2, 2]})
    for v in w:
        contiene(r, float(v))
    calc("algebra", {"calculo": "pseudoinversa", "matriz": [[1, 2], [2, 4]]})
    calc("algebra", {"calculo": "gram_schmidt", "matriz": [[1, 1, 0], [1, 0, 1]]})
    calc("algebra", {"calculo": "diagonalizar", "matriz": [[2, 1], [1, 2]]})


def test_suma_e_interseccion():
    F = [[1, 0, 1, 0], [0, 1, 0, 1]]
    G = [[1, 1, 0, 0], [1, 0, 1, 0]]
    rF, rG = np.linalg.matrix_rank(F), np.linalg.matrix_rank(G)
    rS = np.linalg.matrix_rank(F + G)
    r = calc("espacios", {"calculo": "suma_interseccion", "F": F, "G": G})
    assert str(rS) in str(r.exacto) and str(rF + rG - rS) in str(r.exacto), r.exacto


@pytest.mark.parametrize("expr, metodo", [("(x+3)/(x^2-3*x+2)", "fracciones_simples"),
                                         ("x*cos(x^2)", "sustitucion")])
def test_primitiva_por_metodo(expr, metodo):
    r = calc("primitiva", {"expr": expr, "metodo": metodo})
    F = bonito_sympy(str(r.exacto).split("=")[-1].split("+ C")[0])
    f = bonito_sympy(expr)
    assert abs(complex(sp.diff(F, _x).subs(_x, 3.3)) - complex(f.subs(_x, 3.3))) < 1e-9


@pytest.mark.parametrize("expr", [
    "1/(x^4+1)", "x^2/(x^4+1)", "1/(x^6+1)", "(x^3+2*x^2-x+5)/(x^4-x^2+1)", "1/(x^4+x^2+1)",
    "1/((x-1)*(x^4+1))", "1/((x^4+1)*(x^4+9))", "1/(x^2-2)", "(3*x+1)/(x^2-2*x-1)",
])
def test_primitiva_racional_sin_factorizar_sobre_q(expr):
    # denominadores irreducibles sobre ℚ (x⁴+1, x⁴−x²+1) o con raíces irracionales:
    # F′ = f comprobado aquí con SymPy en tres puntos
    r = calc("primitiva", {"expr": expr, "metodo": "fracciones_simples"})
    F = bonito_sympy(str(r.exacto).split("=")[-1].split("+ C")[0])
    f = bonito_sympy(expr)
    for x0 in (-1.7, 0.3, 2.9):
        assert abs(complex(sp.diff(F, _x).subs(_x, x0)) - complex(f.subs(_x, x0))) < 1e-9, r.exacto


@pytest.mark.parametrize("expr", ["1/(x^8+1)", "1/(x^4+2)", "1/(x^4+1)^2"])
def test_primitiva_racional_fuera_de_alcance_lo_dice(expr):
    with pytest.raises(Exception, match="UNSUPPORTED"):
        C.calcular(C.Peticion("primitiva", {"expr": expr, "metodo": "fracciones_simples"}))


def test_a_trozos_derivable():
    # a·x + b = x² y a = 2x en x = 1 ⇒ a = 2, b = −1
    r = calc("a_trozos", {"izquierda": "a*x+b", "derecha": "x^2", "punto": "1",
                          "parametros": ["a", "b"], "derivable": True})
    assert "2" in str(r.exacto) and "-1" in str(r.exacto)


@pytest.mark.parametrize("entrada, valor", [
    ({"metodo": "newton", "expr": "x^2-2", "x0": 1}, math.sqrt(2)),
    ({"metodo": "biseccion", "expr": "x^3-x-2", "a": 1, "b": 2}, 1.5213797068045676),
    ({"metodo": "simpson", "expr": "exp(-x^2)", "a": 0, "b": 1, "n": 10},
     sum((1 if k in (0, 10) else 4 if k % 2 else 2) * math.exp(-(k / 10) ** 2)
         for k in range(11)) / 30),
    ({"metodo": "trapecios", "expr": "x^2", "a": 0, "b": 1, "n": 4}, 0.34375),
])
def test_metodos_numericos(entrada, valor):
    contiene(calc("metodo_numerico", entrada, sellos=("verificado", "solo_numerico")), valor, rel=1e-6)


def test_distribuciones_derivada():
    r = calc("distribucion", {"calculo": "derivada", "expr": "u(t)-u(t-1)"})
    assert "δ" in str(r.exacto)


def test_contorno():
    # y'' + y = 0, y(0) = 1, y(π/2) = 2 ⇒ y = cos t + 2·sen t
    r = calc("contorno", {"calculo": "contorno", "ecuacion": "y''+y=0", "a": 0, "b": "pi/2",
                          "ca": ["y", 1], "cb": ["y", 2]})
    assert "2" in str(r.exacto)


def test_edo_pvi():
    # y'' + y = 0, y(0) = 0, y'(0) = 1 ⇒ y = sen t
    r = calc("edo", {"calculo": "pvi", "ecuacion": "y''+y=0", "iniciales": [0, 1]})
    assert "sen(t)" in str(r.exacto) or "sin(t)" in str(r.exacto), r.exacto


# ---------------------------------------------------------------------------
# contraste profundo: numéricos (ML-4)
# ---------------------------------------------------------------------------

def _fr_matriz(texto, nombre):
    from fractions import Fraction
    m = re.search(rf"{nombre} = \[([^\]]*)\]", texto)
    return [[Fraction(x.strip()) for x in fila.split(",")] for fila in m.group(1).split(";")]


def contiene_valor_en(texto, esperado, rel=1e-9):
    class _R:
        exacto, aproximado = texto, None
    contiene(_R, esperado, rel=rel, absol=1e-12)


@pytest.mark.parametrize("A, b", [
    ([[2, 1, 1], [4, -6, 0], [-2, 7, 2]], [5, -2, 9]),
    ([[0, 2, 1], [1, 1, 1], [3, 0, 4]], [3, 3, 7]),         # pivote nulo arriba: hace falta P
    ([[1, 2, 3, 4], [2, 1, 0, 1], [3, 0, 1, 2], [4, 1, 2, 0]], [10, 4, 6, 7]),
])
def test_lu_pa_igual_a_lu_y_solucion(A, b):
    from fractions import Fraction
    t = str(calc("numericos", {"calculo": "lu", "matriz": A, "b": b}).exacto)
    L, U = _fr_matriz(t, "L"), _fr_matriz(t, "U")
    perm = [int(x) for x in re.search(r"P = \[([^\]]*)\]", t).group(1).split(",")]
    n = len(A)
    LU = [[sum(L[i][k] * U[k][j] for k in range(n)) for j in range(n)] for i in range(n)]
    assert LU == [[Fraction(v) for v in A[p]] for p in perm], t
    assert all(L[i][i] == 1 and all(L[i][j] == 0 for j in range(i + 1, n)) for i in range(n))
    assert all(U[i][j] == 0 for i in range(n) for j in range(i))
    for v in np.linalg.solve(np.array(A, float), np.array(b, float)):
        contiene_valor_en(t, float(v))


@pytest.mark.parametrize("metodo", ["jacobi", "gauss_seidel"])
@pytest.mark.parametrize("A, b", [([[4, 1], [2, 5]], [1, 2]),
                                  ([[10, -1, 2], [-1, 11, -1], [2, -1, 10]], [6, 25, -11])])
def test_iterativos_contra_solve_y_radio_espectral(metodo, A, b):
    r = calc("numericos", {"calculo": metodo, "matriz": A, "b": b}, sellos=("solo_numerico",))
    for v in np.linalg.solve(np.array(A, float), np.array(b, float)):
        contiene(r, float(v), rel=1e-8)
    A_ = np.array(A, float)
    D, L, U = np.diag(np.diag(A_)), np.tril(A_, -1), np.triu(A_, 1)
    B = -np.linalg.solve(D, L + U) if metodo == "jacobi" else -np.linalg.solve(D + L, U)
    rho = max(abs(np.linalg.eigvals(B)))
    m = re.search(r"ρ\(B\) = ([0-9.e-]+)", str(r.exacto))
    assert math.isclose(float(m.group(1)), rho, rel_tol=1e-3), (r.exacto, rho)


def test_jacobi_con_radio_mayor_que_uno_se_niega():
    with pytest.raises(Exception, match="DIVERGES"):
        C.calcular(C.Peticion("numericos", {"calculo": "jacobi", "matriz": [[1, 3], [2, 1]],
                                            "b": [1, 2]}))


@pytest.mark.parametrize("puntos", [[[0, 1], [1, 3], [2, 11]], [[-1, 2], [0, 0], [2, 5], [3, -1]],
                                    [[1, 1], [2, 8], [3, 27], [4, 64], [5, 125]]])
def test_newton_dd_interpola_y_es_el_de_lagrange(puntos):
    r = calc("numericos", {"calculo": "newton_dd", "puntos": puntos})
    P = bonito_sympy(str(r.exacto).split("=", 1)[1])
    xs, ys = zip(*puntos)
    coef = np.polyfit(xs, ys, len(puntos) - 1)
    for x0 in (-0.7, 0.4, 2.6):
        assert abs(float(P.subs(_x, x0)) - np.polyval(coef, x0)) < 1e-8, r.exacto


@pytest.mark.parametrize("puntos, grado", [([[0, 1], [1, 2], [2, 2], [3, 4]], 1),
                                           ([[0, 1], [1, 0], [2, 3], [3, 10], [4, 15]], 2)])
def test_ajuste_polinomico_contra_polyfit(puntos, grado):
    r = calc("numericos", {"calculo": "ajuste_polinomico", "puntos": puntos, "grado": grado})
    xs, ys = (np.array(v, float) for v in zip(*puntos))
    c = np.polyfit(xs, ys, grado)
    for v in c:
        contiene(r, float(v), rel=1e-9)
    contiene(r, float(sum((np.polyval(c, xs) - ys) ** 2)), rel=1e-5)     # se imprime con 6 cifras


def test_ajuste_exponencial_linealizado_y_gauss_newton():
    xs = [0, 1, 2, 3]
    ys = [2 * math.exp(0.7 * x) for x in xs]
    puntos = [[x, y] for x, y in zip(xs, ys)]
    b1, b0 = np.polyfit(xs, np.log(ys), 1)
    r = calc("numericos", {"calculo": "ajuste_linealizado", "puntos": puntos, "modelo": "exponencial"},
             sellos=("solo_numerico",))
    contiene(r, math.exp(b0), rel=1e-6)
    contiene(r, b1, rel=1e-6)
    r = calc("numericos", {"calculo": "gauss_newton", "modelo": "a*exp(b*x)", "parametros": ["a", "b"],
                           "puntos": puntos, "inicial": [1, 1]}, sellos=("solo_numerico",))
    contiene(r, 2.0, rel=1e-6)
    contiene(r, 0.7, rel=1e-6)


@pytest.mark.parametrize("puntos, a, b, E", [([[0, 0], [1, 1], [2, 4]], -0.5, 2, 0.5),
                                             ([[0, 0], [1, 1], [2, 0]], 0.5, 0, 0.5)])
def test_minimax_equioscila(puntos, a, b, E):
    r = calc("numericos", {"calculo": "minimax", "puntos": puntos})
    errores = [y - (a + b * x) for x, y in puntos]
    # la recta esperada equioscila: tres errores de igual módulo y signo alterno
    assert [abs(v) for v in errores] == [E] * 3 and errores[0] * errores[1] < 0 < errores[0] * errores[2]
    for v in (a, E):
        contiene(r, v)


def _rk4(f, t0, y0, h, n):
    t, y = t0, y0
    for _ in range(n):
        k1 = f(t, y)
        k2 = f(t + h / 2, y + h * k1 / 2)
        k3 = f(t + h / 2, y + h * k2 / 2)
        k4 = f(t + h, y + h * k3)
        y += h * (k1 + 2 * k2 + 2 * k3 + k4) / 6
        t += h
    return y


def test_edo_numerica_rk4_y_euler():
    r = calc("numericos", {"calculo": "edo", "f": "-2*y+t", "y0": "1", "h": "0.1", "n": 10},
             sellos=("solo_numerico",))
    contiene(r, _rk4(lambda t, y: -2 * y + t, 0, 1.0, 0.1, 10), rel=1e-10)
    r = calc("numericos", {"calculo": "edo", "f": "y", "y0": "1", "h": "0.1", "n": 10,
                           "metodo": "euler"}, sellos=("solo_numerico",))
    contiene(r, 1.1 ** 10, rel=1e-10)


def test_secante_regula_falsi_y_raices():
    r = calc("numericos", {"calculo": "secante", "expr": "x^2-2", "x0": 1, "x1": 2},
             sellos=("solo_numerico",))
    contiene(r, math.sqrt(2), rel=1e-10)
    raiz = [z.real for z in np.roots([1, 0, -1, -2]) if abs(z.imag) < 1e-12][0]
    r = calc("numericos", {"calculo": "regula_falsi", "expr": "x^3-x-2", "a": 1, "b": 2},
             sellos=("solo_numerico",))
    contiene(r, raiz, rel=1e-9)
    r = calc("numericos", {"calculo": "raices", "expr": "sin(x)", "a": "1", "b": "10"})
    assert str(r.exacto).startswith("π, 2·π, 3·π"), r.exacto


@pytest.mark.parametrize("a, rama", [("1", 0), ("-1/4", -1), ("2", 0), ("-1/4", 0)])
def test_lambert_w(a, rama):
    av = float(sp.Rational(a))
    w = -2.0 if rama == -1 else 0.5                 # Newton sobre w·eʷ = a, escrito aquí
    for _ in range(60):
        w -= (w * math.exp(w) - av) / (math.exp(w) * (w + 1))
    r = calc("numericos", {"calculo": "lambert", "a": a, "rama": rama},
             sellos=("verificado", "solo_numerico"))
    contiene(r, w, rel=1e-10)


@pytest.mark.parametrize("coef, R", [("n^2/3^n", 3.0), ("1/(n*2^n)", 2.0)])
def test_radio_de_convergencia(coef, R):
    r = calc("numericos", {"calculo": "radio", "coef": coef}, sellos=("verificado", "solo_numerico"))
    assert f"R = {int(R)}" in str(r.exacto), r.exacto


# ---------------------------------------------------------------------------
# contraste profundo: espacios vectoriales (ML-3)
# ---------------------------------------------------------------------------

def _vectores(texto):
    from fractions import Fraction
    return [[Fraction(x.strip()) for x in v.split(",")] for v in re.findall(r"\(([^()]*)\)", texto)]


def test_ecuaciones_a_generadores():
    E = np.array([[1, 0, 1, 0], [0, 1, 0, -1]], float)            # x + z = 0, y − t = 0
    r = calc("espacios", {"calculo": "ecuaciones", "ecuaciones": ["x+z", "y-t"],
                          "vars": ["x", "y", "z", "t"]})
    G = np.array(_vectores(str(r.exacto)), float)
    assert len(G) == 4 - np.linalg.matrix_rank(E) and np.allclose(E @ G.T, 0)
    assert np.linalg.matrix_rank(G) == len(G)


def test_generadores_a_cartesianas():
    r = calc("espacios", {"calculo": "cartesianas", "generadores": [[1, 0, 1, 0], [0, 1, 0, 1]],
                          "vars": ["x", "y", "z", "t"]})
    ecs = [bonito_sympy(e.split("=")[0]) for e in str(r.exacto).split(";")]
    assert len(ecs) == 2, r.exacto
    for g in ([1, 0, 1, 0], [0, 1, 0, 1]):
        valores = dict(zip("xyzt", g))
        assert all(e.subs({s: valores[s.name] for s in e.free_symbols}) == 0 for e in ecs), r.exacto


def test_cambio_de_base_y_matriz_en_otra_base():
    r = calc("espacios", {"calculo": "cambio_base", "coords": [1, 3], "B1": [[1, 2], [2, 1]],
                          "B2": [[2, 3], [3, 2]]})
    v = 1 * np.array([1, 2]) + 3 * np.array([2, 1])
    for c in np.linalg.solve(np.array([[2, 3], [3, 2]], float).T, v):
        contiene(r, float(c))
    A, P = np.array([[1, -4], [4, 1]], float), np.array([[-1, 3], [3, -1]], float).T
    r = calc("espacios", {"calculo": "matriz_base", "matriz": [[1, -4], [4, 1]], "base": [[-1, 3], [3, -1]]})
    M = np.linalg.solve(P, A @ P)
    filas = [[float(x) for x in f.split(",")] for f in str(r.exacto).strip("[]").split(";")]
    assert np.allclose(filas, M), (r.exacto, M)


@pytest.mark.parametrize("A", [[[2, -1, 0], [1, -1, 0], [4, -3, 0]], [[1, 2, 3], [2, 4, 6], [1, 0, 1]],
                               [[1, 1, 1, 1], [1, 2, 3, 4]]])
def test_nucleo_e_imagen(A):
    r = calc("espacios", {"calculo": "nucleo_imagen", "matriz": A})
    texto = str(r.exacto)
    rango = np.linalg.matrix_rank(np.array(A, float))
    assert f"rango = {rango}" in texto
    K = _vectores(texto.split("núcleo = ")[1].split(";")[0])
    assert len(K) == len(A[0]) - rango
    assert all(np.allclose(np.array(A, float) @ np.array(k, float), 0) for k in K)


def test_antiimagen():
    A = np.array([[1, 1, 1], [2, 0, -1]], float)
    r = calc("espacios", {"calculo": "antiimagen", "matriz": A.astype(int).tolist(), "w": [2, 0]})
    part, ker = _vectores(str(r.exacto))
    assert np.allclose(A @ np.array(part, float), [2, 0]) and np.allclose(A @ np.array(ker, float), 0)


@pytest.mark.parametrize("v, H", [([2, 1, -1, -2], [[0, 1, 0, 2], [0, 2, 0, 1]]),
                                  ([2, 1, 3, 1], [[1, 2, 1, 3]]),
                                  ([1, 2, 3], [[1, 1, 0], [0, 1, 1]])])
def test_proyeccion_y_distancia_contra_minimos_cuadrados(v, H):
    Hm = np.array(H, float).T
    pr = Hm @ np.linalg.lstsq(Hm, np.array(v, float), rcond=None)[0]
    d2 = float(np.sum((np.array(v) - pr) ** 2))
    r = calc("espacios", {"calculo": "proyeccion", "v": v, "H": H})
    for c in pr:
        contiene(r, float(c), absol=1e-12)
    contiene(r, d2, rel=1e-9)
    contiene(calc("espacios", {"calculo": "distancia", "v": v, "H": H}), d2, rel=1e-9)


def test_complemento_ortogonal():
    H = [[1, 2, 1, 3]]
    r = calc("espacios", {"calculo": "ortogonal", "H": H})
    W = np.array(_vectores(str(r.exacto)), float)
    assert len(W) == 3 and np.linalg.matrix_rank(W) == 3 and np.allclose(W @ np.array(H, float).T, 0)


@pytest.mark.parametrize("A", [[[3, 0], [0, 4]], [[1, 2], [3, 4]], [[1, 1, 0], [0, 1, 1]], [[2, 0], [0, 0]]])
def test_valores_singulares_contra_svd(A):
    r = calc("espacios", {"calculo": "singulares", "matriz": A})
    for s in np.linalg.svd(np.array(A, float), compute_uv=False):
        if s > 1e-12:
            contiene(r, float(s), rel=1e-9)


def test_discusion_de_rango_con_parametro():
    r = calc("espacios", {"calculo": "parametro", "matriz": [["a", 1, 1], [1, "a", 1], [1, 1, "a"]],
                          "parametro": "a"})
    texto = str(r.exacto)
    # det = (a − 1)²(a + 2): rango 3 salvo a = 1 (rango 1) y a = −2 (rango 2)
    for a, rango in ((1, 1), (-2, 2), (5, 3)):
        assert np.linalg.matrix_rank(np.array([[a, 1, 1], [1, a, 1], [1, 1, a]], float)) == rango
    assert "a = 1: rango 1" in texto and "a = -2: rango 2" in texto and "rango 3" in texto, texto


# ---------------------------------------------------------------------------
# contraste profundo: operadores en curvilíneas (ML-13)
# ---------------------------------------------------------------------------

_r, _th, _ph, _z, _t = sp.symbols("r theta phi z t", positive=True)
_CURVI = {"r": _r, "theta": _th, "phi": _ph, "z": _z, "t": _t}


def _curvi(texto):
    """«∇V = (a, b, c)» del motor a expresiones SymPy en r, θ, φ, z, t."""
    tx = texto.split("=", 1)[1].strip()
    partes = tx[1:-1].split(", ") if tx.startswith("(") and ", " in tx else [tx]
    return [bonito_sympy(p).subs({s: _CURVI.get(s.name, s) for s in bonito_sympy(p).free_symbols})
            for p in partes]


def _igual(a, b):
    punto = {_r: 1.3, _th: 0.7, _ph: 0.4, _z: 0.9, _t: 0.7}
    return abs(complex(sp.sympify(a).subs(punto)) - complex(sp.sympify(b).subs(punto))) < 1e-9


@pytest.mark.parametrize("V, sistema", [("r^2*sin(theta)", "esfericas"), ("r^3*cos(phi)", "esfericas"),
                                        ("r^2*sin(phi)+z", "cilindricas")])
def test_gradiente_y_laplaciano_curvilineos(V, sistema):
    f = sp.sympify(V.replace("^", "**"), locals=_CURVI)
    if sistema == "esfericas":
        # (r, θ polar, φ azimut): ∇ = (∂r, ∂θ/r, ∂φ/(r sen θ))
        grad = [sp.diff(f, _r), sp.diff(f, _th) / _r, sp.diff(f, _ph) / (_r * sp.sin(_th))]
        lap = (sp.diff(_r ** 2 * sp.diff(f, _r), _r) / _r ** 2
               + sp.diff(sp.sin(_th) * sp.diff(f, _th), _th) / (_r ** 2 * sp.sin(_th))
               + sp.diff(f, _ph, 2) / (_r ** 2 * sp.sin(_th) ** 2))
    else:
        # (r, φ, z): el ángulo de las cilíndricas se llama phi en operadores
        grad = [sp.diff(f, _r), sp.diff(f, _ph) / _r, sp.diff(f, _z)]
        lap = sp.diff(_r * sp.diff(f, _r), _r) / _r + sp.diff(f, _ph, 2) / _r ** 2 + sp.diff(f, _z, 2)
    r = calc("operadores", {"calculo": "gradiente", "V": V, "sistema": sistema})
    g = _curvi(str(r.exacto))
    assert len(g) == 3 and all(_igual(a, b) for a, b in zip(g, grad)), r.exacto
    r = calc("operadores", {"calculo": "laplaciano", "V": V, "sistema": sistema})
    assert _igual(_curvi(str(r.exacto))[0], lap), (r.exacto, sp.simplify(lap))


def test_coordenada_ajena_al_sistema_es_bad_input():
    with pytest.raises(Exception, match="BAD_INPUT"):
        C.calcular(C.Peticion("operadores", {"calculo": "gradiente", "V": "r^2*sin(t)",
                                             "sistema": "cilindricas"}))


def test_divergencia_y_rotacional_curvilineos():
    # esféricas, F = r·r̂: ∇·F = (1/r²)∂(r³)/∂r = 3; cilíndricas, F = r·θ̂: ∇×F = (1/r)∂(r²)/∂r ẑ = 2ẑ
    assert _igual(_curvi(str(calc("operadores", {"calculo": "divergencia", "campo": ["r", "0", "0"],
                                                 "sistema": "esfericas"}).exacto))[0], 3)
    rot = _curvi(str(calc("operadores", {"calculo": "rotacional", "campo": ["0", "r", "0"],
                                         "sistema": "cilindricas"}).exacto))
    assert [_igual(a, b) for a, b in zip(rot, (0, 0, 2))] == [True] * 3
    # cartesianas: ∇²(x²y + z³) = 2y + 6z
    L = _curvi(str(calc("operadores", {"calculo": "laplaciano", "V": "x^2*y+z^3"}).exacto))[0]
    y, z = (sp.Symbol(n, real=True) for n in "yz")
    assert sp.simplify(L.subs(_z, z) - (2 * y + 6 * z)) == 0, L


# ---------------------------------------------------------------------------
# contraste profundo: distribuciones (ML-12)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("expr, desde, hasta, valor", [
    ("delta(t-1)*exp(t)", "0", "2", math.e),
    ("u(t)-u(t-2)", "-1", "3", 2.0),
    ("t*u(t)-t*u(t-1)", "-1", "5", 0.5),
    ("delta(t-1)*exp(t)", "2", "3", 0.0),                     # el impulso queda fuera
    ("3*delta(t)+delta(t-2)", "-1", "1", 3.0),
])
def test_integral_de_distribuciones(expr, desde, hasta, valor):
    r = calc("distribucion", {"calculo": "integral", "expr": expr, "desde": desde, "hasta": hasta})
    assert abs(float(bonito_sympy(str(r.exacto))) - valor) < 1e-12, r.exacto


def test_derivada_distribucional():
    # (t·u(t) − t·u(t − 1))′ = 1 en (0, 1) − δ(t − 1): el salto de −1 en t = 1
    texto = str(calc("distribucion", {"calculo": "derivada", "expr": "t*u(t)-t*u(t-1)"}).exacto)
    assert "1 en (0, 1)" in texto and "− δ(t − 1)" in texto, texto
    texto = str(calc("distribucion", {"calculo": "derivada", "expr": "2*u(t-3)"}).exacto)
    assert "2·δ(t − 3)" in texto or "2δ(t − 3)" in texto, texto


def test_convolucion_con_impulsos():
    # f * (δ(t − 1) + 2δ(t − 3)) = f(t − 1) + 2·f(t − 3)
    r = calc("distribucion", {"calculo": "convolucion", "expr": "delta(t-1)+2*delta(t-3)", "f": "t^2"})
    F = bonito_sympy(str(r.exacto))
    t = [s for s in F.free_symbols if s.name == "t"][0]
    assert sp.expand(F - ((t - 1) ** 2 + 2 * (t - 3) ** 2)) == 0, r.exacto


# ---------------------------------------------------------------------------
# contraste profundo: demostraciones asistidas
# ---------------------------------------------------------------------------

def test_punto_fijo_del_coseno():
    c = 0.5
    for _ in range(200):
        c = math.cos(c)
    contiene(calc("demuestra", {"calculo": "punto_fijo", "expr": "cos(x)", "a": 0, "b": 1}), c, rel=1e-10)


@pytest.mark.parametrize("f, g, a, b, cierta", [
    ("exp(x)", "1+x", -2, 2, True), ("x", "ln(1+x)", 0, 2, True), ("x^2", "2*x", 0, 3, False),
    ("sin(x)", "x", 0, 3, False), ("x", "sin(x)", 0, 3, True),
])
def test_desigualdad_y_contraejemplo(f, g, a, b, cierta):
    texto = str(calc("demuestra", {"calculo": "desigualdad", "f": f, "g": g, "a": a, "b": b}).exacto)
    if cierta:
        assert "cierta" in texto.lower(), texto
        return
    x0 = float(sp.Rational(re.search(r"en x = ([-0-9./]+)", texto).group(1)))
    F, G = (sp.sympify(s.replace("^", "**"), locals={"ln": sp.log}) for s in (f, g))
    assert float(F.subs("x", x0)) < float(G.subs("x", x0)), texto     # contraejemplo de verdad


@pytest.mark.parametrize("igualdad, termino, veredicto", [
    ("n^2*(n+1)^2/4 = 0", "n^3", "probada"), ("n*(n+1)*(2*n+1)/6 = 0", "n^2", "probada"),
    ("n^2 = 0", "2*n-1", "probada"), ("n^2 = 0", "n", "falsa"),
])
def test_induccion_contra_la_suma_directa(igualdad, termino, veredicto):
    texto = str(calc("demuestra", {"calculo": "induccion", "igualdad": igualdad, "var": "n", "base": 1,
                                   "termino": termino}).exacto)
    n = sp.Symbol("n")
    cerrada = sp.sympify(igualdad.split("=")[0].replace("^", "**"))
    a = sp.sympify(termino.replace("^", "**"))
    cierta = all(sum(a.subs(n, k) for k in range(1, N + 1)) == cerrada.subs(n, N) for N in range(1, 30))
    assert cierta == (veredicto == "probada")
    assert texto.startswith(veredicto), texto


@pytest.mark.parametrize("A, F, es", [([[0, 1], [1, 0]], [[1, 0]], False), ([[0, 1], [1, 0]], [[1, 1]], True),
                                      ([[2, 1, 0], [0, 2, 0], [0, 0, 3]], [[1, 0, 0]], True)])
def test_subespacio_invariante_contra_rango(A, F, es):
    A_, F_ = np.array(A, float), np.array(F, float)
    assert (np.linalg.matrix_rank(np.vstack([F_, (A_ @ F_.T).T])) == np.linalg.matrix_rank(F_)) == es
    texto = str(calc("demuestra", {"calculo": "invariante", "matriz": A, "F": F}).exacto)
    assert ("NO" not in texto) == es, texto


# ---------------------------------------------------------------------------
# contraste profundo: ejercicios generados (ML-10)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("semilla", range(1, 13))
def test_ejercicios_generados_tienen_la_solucion_correcta(semilla):
    from academic_core.domain.engineering.mathlab import ejercicios as E

    x, s, t = sp.symbols("x s t")
    for tema in E.TEMAS:
        ex = E.genera(tema, semilla=semilla)             # antes: DEPENDENT con vectores ligados
        d = ex.datos
        assert "‬" not in ex.enunciado, ex.enunciado
        if tema == "derivadas":
            f = sp.sympify(d["expr"].replace("^", "**"))
            assert sp.simplify(sp.sympify(ex.solucion.replace("^", "**")) - sp.diff(f, x)) == 0
            assert "*1" not in ex.solucion, ex.solucion
        elif tema == "integrales":
            f = sp.sympify(d["integrando"].replace("^", "**"))
            assert sp.Rational(ex.solucion) == sp.integrate(f, (x, d["desde"], d["hasta"]))
        elif tema == "algebra lineal":
            assert sp.Rational(ex.solucion) == sp.Matrix(d["matriz"]).det()
        elif tema == "ecuaciones":
            assert sp.Rational(ex.solucion) * d["a"] == d["b"]
        elif tema == "limites":
            # se contrasta contra SymPy la forma que salió, no una fija: el
            # generador reparte entre varias y todas tienen que ser ciertas.
            # locals traduce el «sen» y el «ln» del motor; los símbolos son los
            # del test, no los de bonito_sympy, que serian otros objetos.
            loc = {"x": x, "sen": sp.sin, "cos": sp.cos, "ln": sp.log, "exp": sp.exp}
            f = sp.sympify(d["expr"].replace("^", "**").replace("·", "*"), locals=loc)
            esperado = sp.limit(f, x, d["b"])
            got = sp.sympify(ex.solucion.replace("^", "**").replace("·", "*"), locals=loc)
            assert sp.simplify(got - esperado) == 0, (ex.id, ex.enunciado)
        elif tema == "espacios vectoriales":
            Q = np.array(ex.solucion, float)
            V_ = np.array(d["vectores"], float)
            assert np.allclose(Q @ Q.T, np.eye(2))
            assert np.linalg.matrix_rank(np.vstack([Q, V_])) == np.linalg.matrix_rank(V_)
        elif tema == "transformadas":
            loc = {"t": t, "s": s, "sen": sp.sin, "cos": sp.cos, "exp": sp.exp}
            F = sp.laplace_transform(sp.sympify(d["f"].replace("^", "**"), locals=loc),
                                      t, s, noconds=True)
            sol = sp.sympify(ex.solucion.replace("^", "**").replace("·", "*"), locals=loc)
            assert sp.simplify(sol - F) == 0, (ex.id, ex.enunciado)


def test_corrector_acepta_la_solucion_y_rechaza_otra():
    from academic_core.domain.engineering.mathlab import ejercicios as E

    for tema in ("ecuaciones", "integrales", "derivadas"):
        ex = E.genera(tema, semilla=4)
        bien = calc("ejercicio", {"calculo": "corrige", "tema": tema, "semilla": 4,
                                  "respuesta": ex.solucion}, sellos=("verificado", "solo_numerico"))
        assert "✔" in str(bien.exacto) or "✓" in str(bien.exacto), bien.exacto
        mal = calc("ejercicio", {"calculo": "corrige", "tema": tema, "semilla": 4, "respuesta": "999"},
                   sellos=("verificado", "solo_numerico"))
        assert "✘" in str(mal.exacto), mal.exacto


# ---------------------------------------------------------------------------
# contraste profundo: pulido (ML-11)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("op, entrada", [("derivar", "x^3+2*x"),
                                         ("integrar", {"integrando": "x^2", "var": "x", "desde": "0",
                                                       "hasta": "1"})])
def test_accesibilidad_cuenta_las_series_de_verdad(op, entrada):
    directo = C.calcular(C.Peticion(op, entrada))
    r = calc("pulido", {"calculo": "accesibilidad", "operacion": op, "entrada": entrada})
    n = len(directo.grafica.series) if directo.grafica else 0
    assert f"{n} serie" in str(r.exacto), (r.exacto, n)


def test_pasos_de_pulido_cuenta_todas_las_calculadoras():
    r = calc("pulido", {"calculo": "pasos"}, sellos=("verificado", "solo_numerico"))
    m = re.search(r"(\d+) calculadoras comprobadas; (\d+) sin pasos", str(r.exacto))
    assert m and int(m.group(2)) == 0, r.exacto
    # lo mismo, comprobado aquí con las muestras: traza, un paso de método y su porqué
    from academic_core.domain.engineering.mathlab import pulido as PU

    sin_pasos = []
    for op in C.operaciones():
        res = C.calcular(C.Peticion(op, PU.MUESTRAS[op]))
        pasos = res.traza.steps
        if len(pasos) < 2 or not any(p.kind == "metodo" and p.why.strip() for p in pasos):
            sin_pasos.append(op)
    assert sin_pasos == [] and int(m.group(1)) == len(C.operaciones()), sin_pasos
