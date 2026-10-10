# SPDX-License-Identifier: MIT
"""ML-18: detección y estimación (§8.2 R).

Operación ``deteccion`` (contrato §5.9) con ``calculo``:
matriz_r, r_ar1, psd, psd_salida, detector, detector_map, fisher,
gauss_conjunto, wiener, yule_walker, gradiente, lms, nlms.
"""

from __future__ import annotations

from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import deteccion as T
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
def _deteccion(peticion: C.Peticion) -> C.Resultado:
    e = _dict(peticion, "deteccion")
    calculo = str(e.get("calculo", "matriz_r"))
    trace = Trace()

    if calculo == "matriz_r":
        r = T.matriz_r(e.get("r", [1, "1/2"]), trace)
        return _ok(peticion, trace,
                   f"autovalores {', '.join(f'{v:.6g}' for v in r['autovalores'])}",
                   "matriz de correlación", "Toeplitz hermitiana y s.d.p.")
    if calculo == "r_ar1":
        r = T.r_ar1(e.get("sigma2", 1), e.get("a", "1/2"), e.get("p", 4),
                    trace)
        return _ok(peticion, trace,
                   f"r = {[f'{complex(v).real:.6g}' for v in r['R'][0]]}",
                   "AR(1)", "Yule-Walker de orden 1")
    if calculo == "psd":
        r = T.psd_teorica(e.get("r", [1, "1/2", "1/4"]),
                          int(e.get("n", 512)), trace)
        n = len(r["S"])
        g = _grafica([_serie("S(F)", [k / n for k in range(n)], r["S"])],
                     "F", "S", "PSD teórica (D12)")
        return _ok(peticion, trace, f"r[0] = ∫S = {r['potencia']:.6g}",
                   "PSD teórica", f"r[0] = ∫S dF", grafica=g)
    if calculo == "psd_salida":
        r = T.psd_salida(e.get("Sx", []), e.get("H", []), trace)
        return _ok(peticion, trace,
                   f"S_y = {[f'{v:.6g}' for v in r['Sy']]}",
                   "PSD a la salida", "S_y = S_x·|H|²")
    if calculo == "detector":
        r = T.detector(e.get("s", [1, 1]), e.get("sigma", 1),
                       float(e.get("Pfa", 0.05)), trace)
        ps = [p for _, p in r["roc"]]
        ds = [d for d, _ in r["roc"]]
        g = _grafica([_serie("ROC", ps, ds)], "P_FA", "P_D",
                     "curva ROC del detector")
        return _ok(peticion, trace,
                   f"d² = {r['d2']:.6g}; P_D = {r['Pd']:.6g}",
                   "Neyman-Pearson", f"Monte Carlo sobre la ROC", grafica=g)
    if calculo == "detector_map":
        r = T.detector_map(e.get("s", [1, 1]), e.get("sigma", 1),
                           e.get("p0", "1/2"), e.get("p1", "1/2"),
                           e.get("costes"), trace)
        return _ok(peticion, trace,
                   f"γ = {r['gamma']:.6g}; decide H₁ si sᵀx/(σ‖s‖) > η = {r['eta']:.6g}; "
                   f"riesgo = {r['riesgo']:.6g}",
                   "MAP/Bayes", f"γ = {r['gamma']:.6g}; η = {r['eta']:.6g}")
    if calculo == "fisher":
        r = T.fisher(e.get("modelo", "gauss_media"), e.get("params", {}),
                     trace)
        return _ok(peticion, trace,
                   f"I = {r['I']:.6g}; CRB = {r['CRB']:.6g}",
                   "Fisher y Cramér-Rao", f"Var ≥ {r['CRB']:.6g}")
    if calculo == "gauss_conjunto":
        r = T.gauss_conjunto(e.get("m_t", [0]), e.get("m_x", [0, 0]),
                             e.get("K_t", [[1]]), e.get("K_tx", [[1, 0]]),
                             e.get("K_x", [[1, 0], [0, 1]]),
                             e.get("x", [1, 1]), trace)
        return _ok(peticion, trace,
                   f"θ̂ = {[f'{v:.6g}' for v in r['theta_hat']]}",
                   "ML/MAP/MMSE gaussiano", "ortogonalidad comprobada")
    if calculo == "wiener":
        r = T.wiener(e.get("R", [[1, "1/2"], ["1/2", 1]]),
                     e.get("p", [1, 0]), e.get("sigma_d2", 2), trace)
        return _ok(peticion, trace,
                   f"w = {[f'{v:.6g}' for v in r['w']]}; J = {r['J_min']:.6g}",
                   "filtro de Wiener", f"J_min = {r['J_min']:.6g}; R·w = p")
    if calculo == "yule_walker":
        r = T.yule_walker(e.get("r0", 1), e.get("r1", "1/2"), trace)
        return _ok(peticion, trace, f"a = {r['a']:.6g}",
                   "Yule-Walker", f"a = r₁/r₀ = {r['a']:.6g}")
    if calculo == "gradiente":
        r = T.gradiente_modos(e.get("R", [[2, 0], [0, 1]]),
                              e.get("mu", "0.4"), trace)
        return _ok(peticion, trace,
                   f"λ = {[f'{v:.6g}' for v in r['lambdas']]}; "
                   f"dispersión {r['dispersion']:.4g}",
                   "gradiente por modos", f"0 < μ < 2/λ_max")
    if calculo == "lms":
        r = T.lms(e.get("R", [[1, "1/2"], ["1/2", 1]]),
                  e.get("p", [1, 0]), e.get("mu", "0.2"),
                  int(e.get("pasos", 200)), int(e.get("realiz", 200)),
                  int(e.get("semilla", 7)), trace)
        js = r["J"]
        g = _grafica([_serie("J(n)", list(range(len(js))), js)], "n", "J",
                     "curva de aprendizaje LMS")
        det = f"J: {js[0]:.4g} → {js[-1]:.4g}"
        if r["diverge"]:
            return _ok(peticion, trace, det + " (DIVERGE: μ sobre la cota)",
                       "LMS", "μ ≥ 2/λ_max: se ve la divergencia",
                       grafica=g)
        return _ok(peticion, trace, det, "LMS",
                   "E[w(n)] y J(n) frente a la teoría", grafica=g)
    if calculo == "nlms":
        r = T.nlms_cota(e.get("R", [[1, "1/2"], ["1/2", 1]]), trace)
        return _ok(peticion, trace, f"μ̃ < {r['cota_practica']:.6g}",
                   "cota de NLMS", f"0 < μ̃ < 2; práctica {r['cota_practica']:.6g}")
    raise C.error("BAD_INPUT", f"cálculo desconocido: {calculo}")


C.registrar("deteccion", _deteccion)
