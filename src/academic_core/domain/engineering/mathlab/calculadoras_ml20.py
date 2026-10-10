# SPDX-License-Identifier: MIT
"""ML-20: Markov, MDP y refuerzo (§8.2 N).

Operación ``refuerzo`` (contrato §5.9) con ``calculo``:
absorcion, clasifica, mdp_eval, mdp_optimo, episodio, bandidos, reinforce.
Lo ya cubierto por ``markov``/``cola_mm1`` (ML-12) no se duplica.
"""

from __future__ import annotations

from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import refuerzo as R
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
def _refuerzo(peticion: C.Peticion) -> C.Resultado:
    e = _dict(peticion, "refuerzo")
    calculo = str(e.get("calculo", "absorcion"))
    trace = Trace()

    if calculo == "absorcion":
        r = R.absorcion(e.get("P", []), e.get("absorbentes"), trace)
        return _ok(peticion, trace,
                   "; ".join(
                       f"desde {i}: t = {r['tiempos'][k]}, "
                       + ", ".join(f"P(→{a}) = {r['B'][k][j]}"
                                   for j, a in enumerate(r["absorbentes"]))
                       for k, i in enumerate(r["transitorios"])),
                   "absorción por (I−Q)⁻¹", f"N·(I−Q) = I exacto")
    if calculo == "clasifica":
        r = R.clasifica(e.get("P", []), trace)
        txt = "; ".join(
            f"{c['estados']} {'recurrente' if c['recurrente'] else 'transitoria'}"
            for c in r["clases"])
        return _ok(peticion, trace, txt, "clasificación de estados",
                   "periodos " + ", ".join(
                       f"{i}: {'no definido (sin retorno)' if p is None else p}"
                       for i, p in r["periodos"].items()))
    if calculo == "mdp_eval":
        r = R.mdp_eval(e.get("P", []), e.get("R", []), e.get("gamma", "0.9"),
                       trace)
        return _ok(peticion, trace,
                   f"v = {[f'{float(v):.6g}' for v in r['v']]}",
                   "evaluación de política", "residuo de Bellman 0")
    if calculo == "mdp_optimo":
        r = R.mdp_optimo(e.get("P", []), e.get("R", []),
                         e.get("gamma", "0.9"), float(e.get("tol", 1e-9)),
                         trace)
        return _ok(peticion, trace,
                   f"v* = {[f'{v:.6g}' for v in r['v']]}; π* = {r['politica']}",
                   "iteración de valor", "iteración = solución directa")
    if calculo == "episodio":
        ep = [tuple(x) for x in e.get("episodio", [])]
        Q = {(s, a): v for s, a, v in e.get("Q", [])}
        r = R.episodio(ep, Q, e.get("alpha", "1/2"), e.get("gamma", "0.9"),
                       trace)
        def _tabla(T):
            return ", ".join(f"({k}) = {v:.6g}" for k, v in T.items())
        return _ok(peticion, trace,
                   f"MC: {_tabla(r['MC'])} | TD(0) V: {_tabla(r['TD'])} | "
                   f"SARSA: {_tabla(r['SARSA'])} | Q-learning: {_tabla(r['Q'])}",
                   "episodio a mano", "retornos comprobados por Σγᵏr")
    if calculo == "bandidos":
        r = R.bandidos(e.get("pagos", []), e.get("metodo", "incremental"),
                       e.get("c", 2), e.get("epsilon", "0.1"),
                       int(e.get("semilla", 7)), trace)
        g = _grafica([_serie("recompensa media", list(range(len(r["recompensa_media"]))),
                             r["recompensa_media"])], "t", "r̄",
                     "recompensa media frente al tiempo")
        return _ok(peticion, trace,
                   f"Q = {[f'{v:.6g}' for v in r['Q']]}",
                   "bandidos", "Qₙ = media muestral", grafica=g)
    if calculo == "reinforce":
        r = R.reinforce(e.get("pagos", []), e.get("eta", "0.1"),
                        int(e.get("pasos", 50)), e.get("base", 0),
                        int(e.get("semilla", 7)), trace)
        return _ok(peticion, trace, f"J = {r['J']:.6g}",
                   "REINFORCE", "∇J analítico = diferencias finitas")
    raise C.error("BAD_INPUT", f"cálculo desconocido: {calculo}")


C.registrar("refuerzo", _refuerzo)
