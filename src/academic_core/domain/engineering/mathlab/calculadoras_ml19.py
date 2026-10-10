# SPDX-License-Identifier: MIT
"""ML-19: optimización y aprendizaje automático (§8.2 O).

Operación ``aprende`` (contrato §5.9) con ``calculo``:
gd, regresion, lasso, logistica, metricas, roc, kmedias, em, arbol,
pca, svd, red, retroprop, atencion, rnn, lstm, svm.
"""

from __future__ import annotations

import math

from academic_core.domain.engineering.mathlab import aprende as A
from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import verify as V
from academic_core.domain.engineering.mathlab.calculators import _finalizar, con_discrepancia
from academic_core.domain.engineering.mathlab.trace import Trace


def _dict(peticion: C.Peticion, que: str) -> dict:
    e = peticion.entrada
    if not isinstance(e, dict):
        raise C.error("BAD_INPUT", f"se espera un diccionario para «{que}»")
    return e


def _ok(peticion, trace, exacto, metodo, detalle="", aproximado=None, grafica=None,
        avisos=()):
    return _finalizar(peticion, trace, exacto, aproximado=aproximado,
                      sello=V.Seal(V.VERIFIED, metodo, detalle), grafica=grafica,
                      avisos=tuple(avisos))


_con_discrepancia = con_discrepancia


def _serie(nombre, xs, ys) -> C.Serie:
    return C.Serie(nombre, tuple(xs), tuple(ys), ())


def _grafica(series, xl, yl, desc):
    series = tuple(s for s in series if s.ys)
    return C.Graph(series=series, x_label=xl, y_label=yl, description=desc) if series else None


@_con_discrepancia
def _aprende(peticion: C.Peticion) -> C.Resultado:
    e = _dict(peticion, "aprende")
    calculo = str(e.get("calculo", "gd"))
    trace = Trace()

    if calculo == "gd":
        r = A.gd_cuadratica(e.get("Q", [[2, 0], [0, 1]]), e.get("b", [1, 1]),
                            e.get("eta", "0.4"), e.get("w0"),
                            int(e.get("pasos", 20)), e.get("variante", "gd"),
                            trace)
        js = r["trayectoria_J"]
        g = _grafica([_serie("J", list(range(len(js))), js)], "k", "J",
                     "descenso sobre la cuadrática")
        return _ok(peticion, trace, f"J: {js[0]:.6g} → {js[-1]:.6g}",
                   "descenso de gradiente", f"óptimo {r['w_optimo']}",
                   grafica=g)
    if calculo == "regresion":
        r = A.regresion(e.get("X", []), e.get("y", []), e.get("lam", 0),
                        int(e.get("grado", 1)), trace)
        return _ok(peticion, trace,
                   f"w = {[str(v) for v in r['w']]}; R² = {float(r['R2']):.6g}",
                   "regresión por normales", f"Xᵀe = 0; R² = {float(r['R2']):.6g}")
    if calculo == "lasso":
        r = A.lasso_1d(e.get("x", []), e.get("y", []), e.get("lam", 1),
                       trace)
        return _ok(peticion, trace, f"w = {r['w']:.6g}",
                   "lasso 1D", f"w_ols = {r['w_ols']:.6g} → {r['w']:.6g}")
    if calculo == "logistica":
        r = A.logistica(e.get("X", []), e.get("y", []), e.get("eta", "0.1"),
                        int(e.get("pasos", 50)), trace)
        return _ok(peticion, trace, f"w = {[f'{v:.6g}' for v in r['w']]}",
                   "regresión logística", f"log-loss = {r['loss']:.6g}")
    if calculo == "metricas":
        r = A.metricas(e.get("VP", 0), e.get("FP", 0), e.get("FN", 0),
                       e.get("VN", 0), trace)
        return _ok(peticion, trace,
                   f"acc = {r['acc']:.4g}; F1 = {r['F1']:.4g}",
                   "métricas de clasificación", f"F1 = {r['F1']:.4g}")
    if calculo == "roc":
        r = A.roc_auc(e.get("pares", []), trace)
        xs = [x for x, _ in r["roc"]]
        ys = [y for _, y in r["roc"]]
        g = _grafica([_serie("ROC", xs, ys)], "FPR", "TPR", "curva ROC")
        return _ok(peticion, trace, f"AUC = {r['AUC']:.6g}",
                   "ROC y AUC", f"AUC = {r['AUC']:.6g}", grafica=g)
    if calculo == "kmedias":
        r = A.kmedias(e.get("puntos", []), e.get("k", 2), e.get("inicios"),
                      int(e.get("iters", 100)), trace)
        return _ok(peticion, trace,
                   f"SSE = {r['SSE']:.6g}; silueta {r['silueta']:.4g}",
                   "k-medias", f"k = {e.get('k', 2)} clusters")
    if calculo == "em":
        r = A.em_1d(e.get("x", []), e.get("inicios"),
                    int(e.get("iters", 100)), trace)
        return _ok(peticion, trace,
                   f"μ = {[f'{v:.6g}' for v in r['mus']]}; BIC = {r['BIC']:.6g}",
                   "EM gaussiano 1D", f"log L = {r['logL']:.6g}")
    if calculo == "arbol":
        r = A.arbol(e.get("x", []), e.get("y", []), e.get("modo", "entropia"),
                    trace)
        return _ok(peticion, trace,
                   f"x ≤ {r['umbral']} con ganancia {r['ganancia']:.6g}",
                   "árbol de decisión", f"ganancia {r['ganancia']:.6g}")
    if calculo == "pca":
        r = A.pca(e.get("X", []), trace)
        return _ok(peticion, trace,
                   f"λ = {[f'{v:.6g}' for v in r['autovalores']]}",
                   "PCA", f"varianza {[f'{v:.4g}' for v in r['var_explicada']]}")
    if calculo == "svd":
        r = A.svd_2d(e.get("X", []), trace)
        return _ok(peticion, trace,
                   f"σ = {[f'{v:.6g}' for v in r['sigma']]}",
                   "SVD 2D", f"σ = {[f'{v:.6g}' for v in r['sigma']]}")
    if calculo == "red":
        r = A.red_mlp(e.get("x", []), e.get("capas", []),
                      e.get("acts", []), trace)
        return _ok(peticion, trace,
                   f"salida {[f'{v:.6g}' for v in r['a'][-1]]}",
                   "propagación", f"{len(e.get('capas', []))} capas")
    if calculo == "retroprop":
        r = A.retroprop(e.get("x", []), e.get("y", 0), e.get("capas", []),
                        e.get("acts", []), e.get("perdida", "mse"), trace)
        def _m(M):
            return "[" + "; ".join(", ".join(f"{v:.6g}" for v in fila) for fila in M) + "]"
        txt = " | ".join(f"capa {l + 1}: ∂J/∂W = {_m(gW)}, ∂J/∂b = [{', '.join(f'{v:.6g}' for v in gb)}]"
                         for l, (gW, gb) in enumerate(r["grads"]))
        return _ok(peticion, trace, txt,
                   "retropropagación", "analítico = numérico")
    if calculo == "atencion":
        r = A.atencion(e.get("Q", []), e.get("K", []), e.get("V", []), trace)
        return _ok(peticion, trace,
                   "Y = [" + "; ".join(", ".join(f"{v:.6g}" for v in f) for f in r["Y"]) + "]",
                   "atención", "filas suman 1")
    if calculo == "rnn":
        r = A.rnn_pasos(e.get("x", []), e.get("Wx", []), e.get("Wh", []),
                        e.get("b", []), trace)
        return _ok(peticion, trace,
                   "; ".join(f"h{t + 1} = [{', '.join(f'{v:.6g}' for v in h)}]"
                             for t, h in enumerate(r["hs"])),
                   "RNN desenrollada", "pesos atados")
    if calculo == "lstm":
        r = A.lstm_pasos(e.get("x", 0), e.get("W", {}), e.get("h0"),
                         e.get("c0"), trace)
        return _ok(peticion, trace, f"h = {[f'{v:.6g}' for v in r['h']]}",
                   "celda LSTM", "puertas en [0,1]")
    if calculo == "svm":
        r = A.svm_margen(e.get("w", []), e.get("b", 0),
                         e.get("puntos", []), trace)
        return _ok(peticion, trace, f"margen = {r['margen']:.6g}",
                   "SVM (margen/KKT)", f"mín y·f = {r['min_yf']:.6g}")
    raise C.error("BAD_INPUT", f"cálculo desconocido: {calculo}")


C.registrar("aprende", _aprende)
