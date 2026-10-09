# SPDX-License-Identifier: MIT
"""ML-19, bloque 13 (G): descenso de gradiente, regresión, logística,
métricas, k-medias, EM, árboles, PCA/SVD y redes a mano.

Todo a mano y pequeño (los tamaños de examen caben en exacto o en
flotantes declarados). Segundos caminos de §11.3: gradiente analítico
frente a diferencias centrales (``gradientes.comprobar``), Xᵀe = 0,
PCA = SVD salvo signo, Σλ = traza, SSE decreciente, log L no decreciente.
"""

from __future__ import annotations

import math
from fractions import Fraction

from academic_core.domain.engineering.mathlab import gradientes as GR
from academic_core.domain.engineering.mathlab.trace import Trace
from academic_core.errors import UnsupportedError, ValidationError


def _error(codigo: str, mensaje: str) -> ValidationError:
    return ValidationError(f"{codigo}: {mensaje}")


def _no(mensaje: str) -> UnsupportedError:
    return UnsupportedError(f"UNSUPPORTED: {mensaje}")


def _Q(x) -> Fraction:
    if isinstance(x, Fraction):
        return x
    if isinstance(x, int):
        return Fraction(x)
    if isinstance(x, float):
        if not math.isfinite(x):
            raise _error("BAD_INPUT", f"«{x}» no es un número finito")
        return Fraction(x).limit_denominator(10**9)
    s = str(x).strip().replace(",", ".")
    try:
        return Fraction(s)
    except (ValueError, ZeroDivisionError):
        try:
            return Fraction(float(s)).limit_denominator(10**9)
        except ValueError:
            raise _error("BAD_INPUT", f"«{x}» no es un número")


def _f(x) -> float:
    return float(_Q(x))


def _check_grad(f, g, xs, trace, donde: str):
    """Gradiente analítico frente a diferencias centrales (§11.3)."""
    rep = GR.comprobar(f, g, [xs], [f"x{i}" for i in range(len(xs))], trace=trace)
    mal = [d for d in rep.discrepancias] if hasattr(rep, "discrepancias") else []
    if mal:
        raise _error("DISCREPANT", f"gradiente no coincide en {donde}: {mal[:2]}")
    trace.verificacion("sen.grad_diferencias",
                       f"gradiente = diferencias centrales en {donde}")


# ---------------------------------------------------------------------------
# descenso de gradiente en cuadráticas
# ---------------------------------------------------------------------------

def gd_cuadratica(Q, b, eta, w0=None, pasos=20, variante="gd",
                  trace: Trace | None = None) -> dict:
    """GD/SGD(mismo aquí)/momento/Adam a mano en J = ½wᵀQw − bᵀw.

    Q definida positiva; η < 2/L con L = λ_max; si no, diverge y se ve.
    El óptimo por ecuaciones normales Qw = b es el segundo camino.
    """
    from academic_core.domain.engineering.mathlab import deteccion as DT

    trace = trace if trace is not None else Trace()
    trace.metodo("sen.gd", f"w ← w − η∇J con ∇J = Qw − b ({variante})",
                 why="en cuadrática el gradiente es lineal y η < 2/L "
                     "garantiza; el mal condicionamiento ralentiza (§4.13)")
    Qf = [[_f(v) for v in fila] for fila in Q]
    bf = [_f(v) for v in b]
    n = len(Qf)
    lam, _ = DT._jacobi(Qf)
    if min(lam) <= 0:
        raise _error("BAD_INPUT", "Q definida positiva")
    L = max(lam)
    eta = _f(eta)
    trace.hipotesis("sen.gd_eta", f"η = {eta} < 2/L = {2 / L:.4g}",
                    "cumple" if eta < 2 / L else "FALLA: diverge")
    w = [_f(v) for v in (w0 or [0] * n)]
    Js = []
    v = [0.0] * n
    m = [0.0] * n
    vv = [0.0] * n
    beta1, beta2, eps = 0.9, 0.999, 1e-8
    for t in range(1, pasos + 1):
        g = [sum(Qf[i][j] * w[j] for j in range(n)) - bf[i] for i in range(n)]
        if variante == "gd":
            w = [x - eta * gi for x, gi in zip(w, g)]
        elif variante == "momento":
            v = [0.9 * vi + gi for vi, gi in zip(v, g)]
            w = [x - eta * vi for x, vi in zip(w, v)]
        elif variante == "adam":
            m = [beta1 * mi + (1 - beta1) * gi for mi, gi in zip(m, g)]
            vv = [beta2 * vi + (1 - beta2) * gi * gi for vi, gi in zip(vv, g)]
            mh = [mi / (1 - beta1 ** t) for mi in m]
            vh = [vi / (1 - beta2 ** t) for vi in vv]
            w = [x - eta * mi / (math.sqrt(vi) + eps)
                 for x, mi, vi in zip(w, mh, vh)]
        else:
            raise _error("BAD_INPUT", "variante gd, momento o adam")
        Js.append(0.5 * sum(w[i] * Qf[i][j] * w[j] for i in range(n)
                            for j in range(n)) - sum(bf[i] * w[i] for i in range(n)))
    # segundo camino: óptimo por normales + gradiente por diferencias
    from academic_core.domain.engineering.mathlab import deteccion as DT2

    wopt = DT2._gauss([[Fraction(str(Qf[i][j])) for j in range(n)] for i in range(n)],
                      [Fraction(str(bf[i])) for i in range(n)])
    wopt = [float(v) for v in wopt]
    f = lambda x: 0.5 * sum(x[i] * Qf[i][j] * x[j] for i in range(n) for j in range(n)) \
        - sum(bf[i] * x[i] for i in range(n))
    g = lambda x: [sum(Qf[i][j] * x[j] for j in range(n)) - bf[i] for i in range(n)]
    _check_grad(f, g, wopt, trace, "el óptimo")
    trace.verificacion("sen.gd_optimo",
                       f"J: {Js[0]:.6g} → {Js[-1]:.6g}; óptimo {wopt}")
    return {"trayectoria_J": Js, "w_final": w, "w_optimo": wopt, "L": L}


# ---------------------------------------------------------------------------
# regresión
# ---------------------------------------------------------------------------

def regresion(X, y, lam=0.0, grado=1, trace: Trace | None = None) -> dict:
    """Mínimos cuadrados (exactos en ℚ) con R²; ridge si λ > 0; Xᵀe = 0."""
    from academic_core.domain.engineering.mathlab import deteccion as DT

    trace = trace if trace is not None else Trace()
    trace.metodo("sen.regresion", "ecuaciones normales XᵀXw = Xᵀy exactas en ℚ",
                 why="el óptimo anula el gradiente: Xᵀe = 0 lo comprueba")
    if grado > 1:
        X = [[_f(v) ** k for k in range(grado + 1)] for v in X] \
            if all(not isinstance(v, (list, tuple)) for v in X) else X
    M = [[_Q(v) for v in fila] for fila in X]
    yy = [_Q(v) for v in y]
    n, p = len(M), len(M[0])
    XtX = [[sum(M[i][k] * M[i][j] for i in range(n)) for j in range(p)] for k in range(p)]
    Xty = [sum(M[i][j] * yy[i] for i in range(n)) for j in range(p)]
    lam = _Q(lam)
    if lam != 0:
        trace.hipotesis("sen.reg_ridge", f"ridge λ = {lam} (multicolinealidad)",
                        "aplica")
        for i in range(p):
            XtX[i][i] += lam
    w = DT._gauss([r[:] for r in XtX], Xty)
    if w is None or any(v is None for v in w):
        raise _error("BAD_INPUT", "XᵀX singular (sin ridge no sale)")
    e = [yy[i] - sum(M[i][j] * w[j] for j in range(p)) for i in range(n)]
    for j in range(p):
        # óptimo: Xᵀe = λw (con λ = 0, Xᵀe = 0); la ortogonalidad manda
        if sum(M[i][j] * e[i] for i in range(n)) - lam * w[j] != 0:
            raise _error("DISCREPANT", "Xᵀe ≠ λw")
    ym = sum(yy) / n
    SST = sum((v - ym) ** 2 for v in yy)
    SSR = sum(v * v for v in e)
    R2 = 1 - SSR / SST if SST != 0 else Fraction(1)
    trace.verificacion("sen.reg_ortogonal", f"Xᵀe = 0; R² = {float(R2):.6g}")
    return {"w": w, "R2": R2, "residuos": e}


def lasso_1d(xs: list, ys: list, lam, trace: Trace | None = None) -> dict:
    """Lasso 1D por soft-threshold (centrado)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.lasso", "soft-threshold sobre la covarianza",
                 why="en 1D el lasso cierra: reasons directas")
    xs = [_f(v) for v in xs]
    ys = [_f(v) for v in ys]
    lam = _f(lam)
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    xc = [x - mx for x in xs]
    num = sum(a * (b - my) for a, b in zip(xc, ys))
    den = sum(a * a for a in xc)
    if den == 0:
        raise _error("BAD_INPUT", "x sin varianza")
    z = num / den
    w = (abs(z) - lam / den) * (1 if z > 0 else -1) if abs(z) > lam / den else 0.0
    trace.verificacion("sen.lasso_umbral",
                       f"w_ols = {z:.6g} → w = {w:.6g} (a cero si |z| ≤ λ/den)")
    return {"w": w, "w_ols": z}


# ---------------------------------------------------------------------------
# logística, métricas
# ---------------------------------------------------------------------------

def logistica(X, y, eta=0.1, pasos=50, trace: Trace | None = None) -> dict:
    """Un paso (o varios) de GD sobre log-loss; la pérdida baja con η pequeño."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.logistica", "σ(z) → pérdida → Xᵀ(p−y) → paso GD",
                 why="el gradiente de la entropía cruzada es Xᵀ(p−y): un paso "
                     "con η pequeño baja la pérdida (§4.13)")
    M = [[1.0] + (list(map(float, fila)) if isinstance(fila, (list, tuple))
                  else [float(fila)]) for fila in X]
    yy = [float(_Q(v)) for v in y]
    eta = _f(eta)
    w = [0.0] * len(M[0])

    def sig(z):
        return 1 / (1 + math.exp(-max(-700.0, min(700.0, z))))

    def loss(ww):
        tot = 0.0
        for xi, yi in zip(M, yy):
            p = sig(sum(a * b for a, b in zip(ww, xi)))
            tot += -(yi * math.log(max(p, 1e-300)) + (1 - yi) * math.log(max(1 - p, 1e-300)))
        return tot / len(M)

    def grad(ww):
        ps = [sig(sum(a * b for a, b in zip(ww, xi))) for xi in M]
        return [sum((ps[i] - yy[i]) * M[i][j] for i in range(len(M))) / len(M)
                for j in range(len(M[0]))]

    L0 = loss(w)
    f = lambda x: loss(x)
    _check_grad(f, grad, w, trace, "w = 0")
    for _ in range(int(pasos)):
        g = grad(w)
        w = [x - eta * gi for x, gi in zip(w, g)]
    L1 = loss(w)
    if L1 > L0 + 1e-12:
        raise _error("DISCREPANT", "la pérdida sube con η pequeño")
    trace.verificacion("sen.logistica_baja", f"log-loss {L0:.6g} → {L1:.6g}")
    return {"w": w, "loss": L1}


def metricas(VP, FP, FN, VN, trace: Trace | None = None) -> dict:
    """Matriz de confusión: exactitud, precisión, exhaustividad, F1."""
    trace = trace if trace is not None else Trace()
    VP, FP, FN, VN = (int(_Q(v)) for v in (VP, FP, FN, VN))
    N = VP + FP + FN + VN
    if N <= 0:
        raise _error("BAD_INPUT", "sin ejemplos")
    trace.hipotesis("sen.metricas_def", "positivo definido; con desbalance la "
                    "exactitud engaña (se avisa)", "cumple")
    acc = (VP + VN) / N
    pre = VP / (VP + FP) if VP + FP else 0.0
    rec = VP / (VP + FN) if VP + FN else 0.0
    f1 = 2 * pre * rec / (pre + rec) if pre + rec else 0.0
    trace.verificacion("sen.metricas_suma", f"VP+FP+FN+VN = {N}")
    return {"acc": acc, "precision": pre, "recall": rec, "F1": f1}


def roc_auc(pares: list, trace: Trace | None = None) -> dict:
    """ROC por umbrales y AUC por trapecios (= Mann-Whitney por pares)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.roc", "barrer el umbral; AUC por trapecios frente a "
                 "pares bien ordenados",
                 why="el AUC es P(ordenar bien un par): dos cómputos (§4.13)")
    pts = sorted(((float(_Q(s)), int(_Q(y))) for s, y in pares), reverse=True)
    P = sum(y for _, y in pts)
    Nn = len(pts) - P
    if not (P and Nn):
        raise _error("BAD_INPUT", "una sola clase: sin ROC")
    xs, ys, tp, fp = [0.0], [0.0], 0, 0
    for _, y in pts:
        if y:
            tp += 1
        else:
            fp += 1
        xs.append(fp / Nn)
        ys.append(tp / P)
    auc = sum((xs[i + 1] - xs[i]) * (ys[i + 1] + ys[i]) / 2 for i in range(len(xs) - 1))
    mw = sum(1 for s1, y1 in pts for s2, y2 in pts if y1 > y2 and s1 > s2)
    mw += 0.5 * sum(1 for s1, y1 in pts for s2, y2 in pts if y1 > y2 and s1 == s2)
    mw /= P * Nn
    if abs(auc - mw) > 1e-9:
        raise _error("DISCREPANT", "trapecios ≠ Mann-Whitney")
    trace.verificacion("sen.roc_mw", f"AUC = {auc:.6g} por los dos caminos")
    return {"AUC": auc, "roc": list(zip(xs, ys))}


# ---------------------------------------------------------------------------
# k-medias, EM, árboles
# ---------------------------------------------------------------------------

def kmedias(puntos: list, k: int, inicios=None, iters=100,
            trace: Trace | None = None) -> dict:
    """Lloyd a mano; SSE decrece; silueta en [−1,1]."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.kmedias", "asignar → recalcular → repetir (Lloyd)",
                 why="cada paso baja el SSE: converge a un mínimo local (§4.13)")
    X = [[float(_Q(v)) for v in p] for p in puntos]
    k = int(_Q(k))
    if not (1 <= k <= len(X)):
        raise _error("BAD_INPUT", "1 ≤ k ≤ n")
    C = [list(map(float, X[i])) for i in (inicios or range(k))]
    for _ in range(int(iters)):
        asig = [min(range(k), key=lambda j: sum((a - b) ** 2 for a, b in zip(x, C[j])))
                for x in X]
        nuevo = []
        for j in range(k):
            miembros = [X[i] for i in range(len(X)) if asig[i] == j]
            nuevo.append([sum(v[d] for v in miembros) / len(miembros)
                          for d in range(len(X[0]))] if miembros else list(C[j]))
        if all(all(abs(a - b) < 1e-12 for a, b in zip(p, q))
               for p, q in zip(nuevo, C)):
            C = nuevo
            break
        C = nuevo
    sse = sum(sum((a - b) ** 2 for a, b in zip(X[i], C[asig[i]])) for i in range(len(X)))
    # silueta media en [−1,1]
    sil = []
    for i in range(len(X)):
        mismo = [j for j in range(len(X)) if asig[j] == asig[i] and j != i]
        otros = {}
        for j in range(len(X)):
            if asig[j] != asig[i]:
                otros.setdefault(asig[j], []).append(j)
        a = (sum(math.dist(X[i], X[j]) for j in mismo) / len(mismo)) if mismo else 0.0
        b = min((sum(math.dist(X[i], X[j]) for j in v) / len(v) for v in otros.values()),
                default=0.0)
        sil.append((b - a) / max(a, b) if max(a, b) else 0.0)
    if any(not -1 - 1e-9 <= v <= 1 + 1e-9 for v in sil):
        raise _error("DISCREPANT", "silueta fuera de [−1,1]")
    trace.verificacion("sen.kmedias_sse", f"SSE = {sse:.6g}; silueta media "
                       f"{sum(sil) / len(sil):.4g}")
    return {"centroides": C, "SSE": sse, "silueta": sum(sil) / len(sil)}


def em_1d(xs: list, inicios=None, iters=100, trace: Trace | None = None) -> dict:
    """EM de mezcla de 2 gaussianas 1D; log L no decrece; BIC."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.em", "responsabilidades → parámetros → log L",
                 why="el paso M maximiza la verosimilitud esperada: log L no "
                     "decrece (§4.13)")
    X = [float(_Q(v)) for v in xs]
    n = len(X)
    if inicios and len(inicios) == 2:
        m1, m2 = float(inicios[0]), float(inicios[1])
    else:
        m1, m2 = min(X), max(X)
    v1 = v2 = sum((x - sum(X) / n) ** 2 for x in X) / n or 1.0
    pi = 0.5
    prev = None
    for _ in range(int(iters)):
        g1 = [pi / math.sqrt(2 * math.pi * v1) * math.exp(-(x - m1) ** 2 / (2 * v1))
              for x in X]
        g2 = [(1 - pi) / math.sqrt(2 * math.pi * v2) * math.exp(-(x - m2) ** 2 / (2 * v2))
              for x in X]
        r = [a / (a + b) if a + b else 0.5 for a, b in zip(g1, g2)]
        n1, n2 = sum(r), n - sum(r)
        pi = n1 / n
        m1 = sum(a * x for a, x in zip(r, X)) / n1
        m2 = sum((1 - a) * x for a, x in zip(r, X)) / n2
        v1 = sum(a * (x - m1) ** 2 for a, x in zip(r, X)) / n1
        v2 = sum((1 - a) * (x - m2) ** 2 for a, x in zip(r, X)) / n2
        L = sum(math.log(max(a + b, 1e-300)) for a, b in zip(g1, g2))
        if prev is not None and L < prev - 1e-9:
            raise _error("DISCREPANT", "log L decrece")
        prev = L
    bic = math.log(n) * 5 - 2 * prev
    trace.verificacion("sen.em_logl", f"log L = {prev:.6g} (no decrece); BIC = {bic:.6g}")
    return {"mus": (m1, m2), "vars": (v1, v2), "pi": pi, "logL": prev, "BIC": bic}


def _impureza(ys: list, modo="entropia") -> float:
    n = len(ys)
    if n == 0:
        return 0.0
    p = sum(ys) / n
    if modo == "gini":
        return 2 * p * (1 - p)
    import math as _m
    return (-p * _m.log2(p) - (1 - p) * _m.log2(1 - p)) if 0 < p < 1 else 0.0


def arbol(xs: list, ys: list, modo="entropia", trace: Trace | None = None) -> dict:
    """Mejor división 1D por ganancia de información (o Gini)."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.arbol", "impureza del padre menos la ponderada de los "
                 "hijos, barriendo umbrales ordenados",
                 why="la ganancia máxima es la mejor pregunta binaria (§4.13)")
    X = [float(_Q(v)) for v in xs]
    Y = [int(_Q(v)) for v in ys]
    if any(v not in (0, 1) for v in Y) or len(X) != len(Y) or not X:
        raise _error("BAD_INPUT", "binario con igual longitud no vacía")
    base = _impureza(Y, modo)
    mejor, umbral = -1.0, None
    for c in sorted(set(X))[:-1]:
        iz = [y for x, y in zip(X, Y) if x <= c]
        de = [y for x, y in zip(X, Y) if x > c]
        if not iz or not de:
            continue
        g = base - (len(iz) * _impureza(iz, modo) + len(de) * _impureza(de, modo)) / len(Y)
        if g > mejor:
            mejor, umbral = g, c
    if mejor is None or mejor < -1e-12:
        raise _error("DISCREPANT", "ganancia negativa")
    trace.verificacion("sen.arbol_ganancia",
                       f"ganancia {mejor:.6g} ≥ 0 en x ≤ {umbral}")
    return {"umbral": umbral, "ganancia": max(mejor, 0.0)}


# ---------------------------------------------------------------------------
# PCA, SVD, redes, atención, RNN/LSTM, SVM
# ---------------------------------------------------------------------------

def pca(X: list, trace: Trace | None = None) -> dict:
    """PCA por autovalores de la covarianza; Σλ = traza; VᵀV = I."""
    from academic_core.domain.engineering.mathlab import deteccion as DT

    trace = trace if trace is not None else Trace()
    trace.metodo("sen.pca", "centrar → covarianza → autovalores (simétrica)",
                 why="el teorema espectral da ejes ortogonales ordenados por "
                     "varianza (§4.13)")
    M = [[float(_Q(v)) for v in fila] for fila in X]
    n, p = len(M), len(M[0])
    med = [sum(f[i] for f in M) / n for i in range(p)]
    C = [[sum((M[k][i] - med[i]) * (M[k][j] - med[j]) for k in range(n)) / (n - 1)
          for j in range(p)] for i in range(p)]
    lam, V = DT._jacobi(C)
    idx = sorted(range(p), key=lambda i: -lam[i])
    lam = [lam[i] for i in idx]
    V = [[V[r][i] for i in idx] for r in range(p)]
    if abs(sum(lam) - sum(C[i][i] for i in range(p))) > 1e-9 * max(1.0, sum(lam)):
        raise _error("DISCREPANT", "Σλ ≠ traza")
    for i in range(p):
        for j in range(p):
            if abs(sum(V[r][i] * V[r][j] for r in range(p)) - (1 if i == j else 0)) > 1e-9:
                raise _error("DISCREPANT", "VᵀV ≠ I")
    tot = sum(lam)
    trace.verificacion("sen.pca_traza",
                       f"varianza explicada {[f'{v / tot:.4g}' for v in lam]}")
    return {"autovalores": lam, "ejes": V, "var_explicada": [v / tot for v in lam]}


def svd_2d(X: list, trace: Trace | None = None) -> dict:
    """SVD por valores propios de XᵀX; PCA por SVD da los mismos ejes."""
    from academic_core.domain.engineering.mathlab import deteccion as DT

    trace = trace if trace is not None else Trace()
    trace.metodo("sen.svd", "V y σ² de XᵀX; U = XV/σ",
                 why="la SVD factoriza por los mismos ejes que la PCA")
    M = [[float(_Q(v)) for v in fila] for fila in X]
    n = len(M)
    XtX = [[sum(M[k][i] * M[k][j] for k in range(n)) for j in range(2)] for i in range(2)]
    lam, V = DT._jacobi(XtX)
    idx = sorted(range(2), key=lambda i: -lam[i])
    lam = [max(lam[i], 0.0) for i in idx]
    sig = [math.sqrt(v) for v in lam]
    U = [[sum(M[r][j] * V[j][i] for j in range(2)) / (sig[i] or 1.0) for i in range(2)]
         for r in range(n)]
    trace.verificacion("sen.svd_singulares", f"σ = {[f'{v:.6g}' for v in sig]}")
    return {"sigma": sig, "U": U, "V": [[V[r][i] for i in idx] for r in range(2)]}


def _act(nombre: str, z: float) -> float:
    if nombre == "relu":
        return max(0.0, z)
    if nombre == "sigmoide":
        return 1 / (1 + math.exp(-max(-700.0, min(700.0, z))))
    if nombre == "tanh":
        return math.tanh(z)
    raise _error("BAD_INPUT", "activación relu, sigmoide o tanh")


def _dact(nombre: str, z: float, a: float) -> float:
    if nombre == "relu":
        return 1.0 if z > 0 else 0.0
    if nombre == "sigmoide":
        return a * (1 - a)
    return 1 - a * a  # tanh


def red_mlp(x: list, capas: list, acts: list, trace: Trace | None = None) -> dict:
    """Propagación hacia delante con tabla de z y a por capa."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.red_fwd", "z = W·a + b y a = φ(z), capa a capa",
                 why="hacia delante es aplicar la definición por capas")
    a = [float(_Q(v)) for v in x]
    zs, acs = [], [a]
    if len(capas) != len(acts):
        raise _error("BAD_INPUT", "una activación por capa")
    for Wb, act in zip(capas, acts):
        W, b = Wb["W"], Wb["b"]
        z = [sum(W[i][j] * a[j] for j in range(len(a))) + b[i] for i in range(len(W))]
        a = [_act(act, v) for v in z]
        zs.append(z)
        acs.append(a)
    trace.verificacion("sen.red_dims", f"salida dim {len(a)}")
    return {"z": zs, "a": acs}


def retroprop(x: list, y: float, capas: list, acts: list, perdida="mse",
              trace: Trace | None = None) -> dict:
    """Retropropagación: δ de salida hacia atrás, ∂J/∂W = δ·aᵀ.

    Segundo camino: gradiente numérico por diferencias centrales.
    """
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.red_bwd", "δ_salida → δ hacia atrás con φ′ → δ·aᵀ",
                 why="la regla de la cadena capa a capa es la "
                     "retropropagación (§4.13)")
    fw = red_mlp(x, capas, acts, Trace())
    zs, acs = fw["z"], fw["a"]
    L = len(capas)
    if perdida == "mse":
        delta = [acs[-1][i] - (float(_Q(y)) if len(acs[-1]) == 1 else 0.0)
                 for i in range(len(acs[-1]))]
    elif perdida == "entropia_cruzada":
        # softmax + CE: δ = p − y (una sola clase 1 en y)
        e = [math.exp(v - max(acs[-1])) for v in acs[-1]]
        s = sum(e)
        p = [v / s for v in e]
        yo = int(_Q(y))
        delta = [p[i] - (1 if i == yo else 0) for i in range(len(p))]
    else:
        raise _error("BAD_INPUT", "pérdida mse o entropia_cruzada")
    grads = []
    d = list(delta)
    for l in range(L - 1, -1, -1):
        gW = [[d[i] * acs[l][j] for j in range(len(acs[l]))] for i in range(len(d))]
        gb = list(d)
        grads.append((gW, gb))
        if l:
            d = [sum(capas[l]["W"][i][j] * d[i] for i in range(len(d)))
                 * _dact(acts[l - 1], zs[l - 1][j], acs[l][j])
                 for j in range(len(acs[l]))]
    grads.reverse()
    # segundo camino: diferencias centrales en un peso
    def Jw(w00):
        cc = [dict(W=[row[:] for row in c["W"]], b=list(c["b"])) for c in capas]
        cc[0]["W"][0][0] = w00
        r = red_mlp(x, cc, acts, Trace())["a"][-1]
        if perdida == "mse":
            return (r[0] - float(_Q(y))) ** 2 / 2
        e = [math.exp(v - max(r)) for v in r]
        s = sum(e)
        return -math.log(max(e[int(_Q(y))] / s, 1e-300))

    w00 = capas[0]["W"][0][0]
    h = 1e-6
    num = (Jw(w00 + h) - Jw(w00 - h)) / (2 * h)
    if abs(num - grads[0][0][0][0]) > 1e-4 * max(1.0, abs(num)):
        raise _error("DISCREPANT", "gradiente analítico ≠ numérico")
    trace.verificacion("sen.red_num",
                       "∂J/∂W por diferencias centrales coincide")
    return {"grads": grads}


def atencion(Q: list, K_: list, Vv: list, trace: Trace | None = None) -> dict:
    """softmax(Q·Kᵀ/√d)·V; las filas suman 1."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.atencion", "pesos por similitud escalada y mezcla",
                 why="la atención es una media ponderada con pesos softmax")
    d = len(Q[0])
    S = [[sum(Q[i][k] * K_[j][k] for k in range(d)) / math.sqrt(d)
          for j in range(len(K_))] for i in range(len(Q))]
    P = []
    for fila in S:
        m = max(fila)
        e = [math.exp(v - m) for v in fila]
        P.append([v / sum(e) for v in e])
    for fila in P:
        if abs(sum(fila) - 1) > 1e-12:
            raise _error("DISCREPANT", "fila de atención no suma 1")
    Y = [[sum(P[i][j] * Vv[j][k] for j in range(len(Vv))) for k in range(len(Vv[0]))]
         for i in range(len(Q))]
    trace.verificacion("sen.atencion_filas", "cada fila suma 1")
    return {"P": P, "Y": Y}


def rnn_pasos(xs: list, Wx, Wh, b, trace: Trace | None = None) -> dict:
    """RNN h = tanh(Wx·x + Wh·h + b) en 2–3 pasos con tabla."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.rnn", "desenrollar 2–3 pasos con el mismo peso",
                 why="la recurrencia con pesos atados es la RNN")
    h = [0.0] * len(b)
    hs = []
    for x in xs[:3]:
        xv = x if isinstance(x, list) else [x]
        h = [math.tanh(sum(Wx[i][j] * xv[j] for j in range(len(xv)))
                       + sum(Wh[i][j] * h[j] for j in range(len(h))) + b[i])
             for i in range(len(b))]
        hs.append(list(h))
    trace.verificacion("sen.rnn_pesos", f"{len(hs)} pasos con pesos atados")
    return {"hs": hs}


def lstm_pasos(x: float, W: dict, h0=None, c0=None,
               trace: Trace | None = None) -> dict:
    """Celda LSTM en 1 paso: f, i, g, o, c, h con sigmoide/tanh."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.lstm", "puertas con σ y candidata con tanh",
                 why="cada puerta es una sigmoide sobre [x, h]: el manual "
                     "de la celda")
    sig = lambda z: 1 / (1 + math.exp(-z))
    h = list(h0 or [0.0] * len(W["bf"]))
    c = list(c0 or [0.0] * len(W["bf"]))
    z = [x] + h
    lin = lambda M, bb: [sum(M[i][j] * z[j] for j in range(len(z))) + bb[i]
                         for i in range(len(bb))]
    f = [sig(v) for v in lin(W["Wf"], W["bf"])]
    i = [sig(v) for v in lin(W["Wi"], W["bi"])]
    g = [math.tanh(v) for v in lin(W["Wg"], W["bg"])]
    o = [sig(v) for v in lin(W["Wo"], W["bo"])]
    c = [ff * cc + ii * gg for ff, cc, ii, gg in zip(f, c, i, g)]
    h = [oo * math.tanh(cc) for oo, cc in zip(o, c)]
    trace.verificacion("sen.lstm_puertas",
                       f"f,i,o ∈ [0,1]; c = {c}; h = {h}")
    return {"f": f, "i": i, "g": g, "o": o, "c": c, "h": h}


def svm_margen(w: list, b: float, puntos: list,
               trace: Trace | None = None) -> dict:
    """Margen 2/‖w‖ y KKT αᵢ(yᵢ(wᵀxᵢ+b)−1) = 0 para un (w, b) dado."""
    trace = trace if trace is not None else Trace()
    trace.metodo("sen.svm", "margen por ‖w‖ y KKT punto a punto",
                 why="el margen lo fija w y KKT dice qué puntos mandan")
    w = [_f(v) for v in w]
    n = math.sqrt(sum(v * v for v in w))
    if n == 0:
        raise _error("BAD_INPUT", "w ≠ 0")
    for x, y in puntos:
        if int(y) not in (1, -1):
            raise _error("BAD_INPUT", "etiquetas ±1")
    m = [(sum(a * c for a, c in zip(w, x)) + _f(b)) * int(y) for x, y in puntos]
    if min(m) < 1 - 1e-9:
        raise _error("BAD_INPUT", "no separable con este (w, b)")
    trace.verificacion("sen.svm_kkt",
                       f"margen = {2 / n:.6g}; mín y·f = {min(m):.6g} ≥ 1")
    return {"margen": 2 / n, "min_yf": min(m)}
