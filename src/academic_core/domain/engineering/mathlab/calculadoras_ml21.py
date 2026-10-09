# SPDX-License-Identifier: MIT
"""ML-21: matemáticas financieras (§8.2 P).

Operación ``finanzas`` (contrato §5.9) con ``calculo``:
interes, tiempo, van, tir, anualidad, bono, futuro, payoff, crr,
black_scholes, vol_implicita, montecarlo, markowitz, frontera, sharpe_var.
"""

from __future__ import annotations

import math

from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import finanzas as F
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
def _finanzas(peticion: C.Peticion) -> C.Resultado:
    e = _dict(peticion, "finanzas")
    calculo = str(e.get("calculo", "interes"))
    trace = Trace()

    if calculo == "interes":
        r = F.interes(e.get("C0", 1000), e.get("r", "0.05"), e.get("t", 10),
                      e.get("modo", "compuesto"), e.get("m", 1), trace)
        return _ok(peticion, trace, f"C = {r['C']:.6g}; TAE = {r['TAE']:.6g}",
                   "interés", f"TAE = {r['TAE']:.6g}")
    if calculo == "tiempo":
        r = F.despejar_tiempo(e.get("C0", 1000), e.get("C", 2000),
                              e.get("r", "0.05"), e.get("modo", "compuesto"),
                              e.get("m", 1), trace)
        return _ok(peticion, trace, f"t = {r['t']:.6g}",
                   "despeje con ln", f"t = {r['t']:.6g}")
    if calculo == "van":
        r = F.van(e.get("flujos", []), e.get("r", "0.05"), trace)
        return _ok(peticion, trace, f"VAN = {r['VAN']:.6g}",
                   "VAN por línea temporal", f"VAN = {r['VAN']:.6g}")
    if calculo == "tir":
        r = F.tir(e.get("flujos", []), trace)
        return _ok(peticion, trace, f"TIR = {r['TIR']:.6g}",
                   "TIR por bisección", f"VAN(TIR) = 0")
    if calculo == "anualidad":
        r = F.anualidad(e.get("A", 10000), e.get("r", "0.05"),
                        e.get("n", 10), trace)
        return _ok(peticion, trace,
                   f"cuota = {r['cuota']:.6g}; intereses = {r['intereses']:.6g}",
                   "amortización", f"total {r['total']:.6g}")
    if calculo == "bono":
        r = F.bono(e.get("flujos", []), e.get("y", "0.05"), trace)
        return _ok(peticion, trace,
                   f"P = {r['P']:.6g}; D = {r['duracion']:.6g}",
                   "bono", f"D = {r['duracion']:.6g}")
    if calculo == "futuro":
        r = F.futuro(e.get("S0", 100), e.get("r", "0.05"), e.get("T", 1),
                     trace)
        return _ok(peticion, trace, f"F = {r['F']:.6g}",
                   "futuro por arbitraje", f"F = S₀·e^rT = {r['F']:.6g}")
    if calculo == "payoff":
        r = F.payoff(e.get("S", 100), e.get("K", 100), e.get("tipo", "call"),
                     trace)
        return _ok(peticion, trace, f"payoff = {r['payoff']:.6g}",
                   "payoff europeo", "")
    if calculo == "crr":
        r = F.crr(e.get("S0", 100), e.get("K", 100), e.get("r", "0.05"),
                  e.get("sigma", "0.2"), e.get("T", 1), e.get("n", 100),
                  e.get("tipo", "call"), bool(e.get("americana", False)),
                  trace)
        return _ok(peticion, trace, f"precio = {r['precio']:.6g}",
                   "árbol CRR", f"q = {r['q']:.6g} sin arbitraje")
    if calculo == "black_scholes":
        r = F.black_scholes(e.get("S0", 100), e.get("K", 100),
                            e.get("r", "0.05"), e.get("sigma", "0.2"),
                            e.get("T", 1), e.get("tipo", "call"), trace)
        return _ok(peticion, trace,
                   f"C = {r['precio']:.6g}; Δ = {r['delta']:.6g}",
                   "Black-Scholes", "paridad put-call comprobada")
    if calculo == "vol_implicita":
        r = F.vol_implicita(e.get("precio", 10), e.get("S0", 100),
                            e.get("K", 100), e.get("r", "0.05"),
                            e.get("T", 1), e.get("tipo", "call"), trace)
        return _ok(peticion, trace, f"σ = {r['sigma']:.6g}",
                   "volatilidad implícita", "Newton sobre vega > 0")
    if calculo == "montecarlo":
        r = F.montecarlo_opcion(e.get("S0", 100), e.get("K", 100),
                                e.get("r", "0.05"), e.get("sigma", "0.2"),
                                e.get("T", 1), int(e.get("N", 20000)),
                                int(e.get("semilla", 7)),
                                e.get("tipo", "call"), trace)
        bs = F.black_scholes(e.get("S0", 100), e.get("K", 100),
                             e.get("r", "0.05"), e.get("sigma", "0.2"),
                             e.get("T", 1), e.get("tipo", "call"), Trace())
        g = _grafica([], "", "", "")
        det = f"{r['precio']:.6g} ± {r['error']:.3g} (exacto {bs['precio']:.6g})"
        if abs(r["precio"] - bs["precio"]) > 3 * r["error"] + 1e-9:
            return _finalizar(peticion, trace, det, aproximado=r["precio"],
                              sello=V.Seal(V.DISCREPANT, "MC fuera del exacto",
                                           det), grafica=g)
        return _ok(peticion, trace, det, "Monte Carlo sembrado",
                   "cae en el intervalo exacto", grafica=g)
    if calculo == "markowitz":
        r = F.markowitz(e.get("mu", []), e.get("Sigma", []), e.get("m"),
                        trace)
        return _ok(peticion, trace,
                   f"μₚ = {float(r['mu_p']):.6g}; σₚ² = {float(r['var_p']):.6g}",
                   "Markowitz (KKT lineal)", "wᵀ1 = 1; 2Σw = λ1 + μμᵀ")
    if calculo == "frontera":
        r = F.frontera_eficiente(e.get("mu", []), e.get("Sigma", []),
                                 int(e.get("puntos", 15)), trace)
        pts = r["frontera"]
        g = _grafica([_serie("frontera eficiente",
                             [float(math.sqrt(v)) for _, v in pts],
                             [float(m) for m, _ in pts])],
                     "σₚ", "μₚ", "frontera eficiente (σ frente a μ)")
        return _ok(peticion, trace,
                   f"{len(pts)} puntos; μ de {float(pts[0][0]):.4g} a "
                   f"{float(pts[-1][0]):.4g}",
                   "frontera por barrido de m", "σ² monótona creciente", grafica=g)
    if calculo == "sharpe_var":
        r = F.sharpe_var(e.get("mu", 0), e.get("var", 1), e.get("rf", 0),
                         e.get("alpha", "0.05"), trace)
        return _ok(peticion, trace,
                   f"Sharpe = {r['sharpe']:.6g}; VaR = {r['VaR']:.6g}",
                   "Sharpe y VaR", f"VaR = {r['VaR']:.6g}")
    raise C.error("BAD_INPUT", f"cálculo desconocido: {calculo}")


C.registrar("finanzas", _finanzas)
