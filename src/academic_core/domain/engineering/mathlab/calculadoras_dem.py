# SPDX-License-Identifier: MIT
"""Demostraciones asistidas (§4.8 y §15.2.7): punto fijo, desigualdades en
compacto, axiomas de subespacio, invariancia e inducción.

Operación ``demuestra`` (contrato §5.9) con ``calculo``:
punto_fijo, desigualdad, subespacio, invariante, induccion.
Lo no demostrable se niega con su motivo: no hay prueba sin certificado.
"""

from __future__ import annotations

from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import demuestra as D
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


@_con_discrepancia
def _demuestra(peticion: C.Peticion) -> C.Resultado:
    e = _dict(peticion, "demuestra")
    calculo = str(e.get("calculo", "punto_fijo"))
    trace = Trace()
    var = str(e.get("var", "x"))

    if calculo == "punto_fijo":
        r = D.punto_fijo(e.get("expr", e.get("f", "x/2")), var,
                         e.get("a", 0), e.get("b", 1), trace)
        return _ok(peticion, trace, f"c = {r['texto']}",
                   "punto fijo por Bolzano", f"f(c) = c con c = {r['texto']}")
    if calculo == "desigualdad":
        r = D.desigualdad(e.get("f", "x"), e.get("g", "0"), var,
                          e.get("a", 0), e.get("b", 1), trace)
        if r["veredicto"] == "falsa":
            return _ok(peticion, trace,
                       f"FALSA en x = {r['contraejemplo']:.6g}",
                       "desigualdad refutada", f"contraejemplo x = {r['contraejemplo']:.6g}")
        return _ok(peticion, trace,
                   f"cierta: mínimo {r['min']:.6g} en x = {r['xmin']:.6g}",
                   "desigualdad probada", f"mínimo global en compacto")
    if calculo == "subespacio":
        r = D.subespacio(e.get("conds", e.get("condiciones", [])),
                         [str(v) for v in e.get("vars", ["x", "y", "z"])], trace)
        return _ok(peticion, trace,
                   "SÍ es subespacio" if r["es"] else "NO es subespacio",
                   "axiomas de subespacio", r["motivo"])
    if calculo == "invariante":
        r = D.invariante(e.get("matriz", []), e.get("F", []), trace)
        return _ok(peticion, trace,
                   "F invariante" if r["es"] else "F NO invariante",
                   "invariancia por la base",
                   "toda imagen de la base sigue en F" if r["es"]
                   else "hay testigo fuera de F")
    if calculo == "induccion":
        r = D.induccion(e.get("igualdad", "n = n"), var, e.get("base", 0),
                        e.get("termino"), trace)
        return _ok(peticion, trace, r["veredicto"],
                   "inducción", f"veredicto: {r['veredicto']}")
    raise C.error("BAD_INPUT", f"cálculo desconocido: {calculo}")


C.registrar("demuestra", _demuestra)
