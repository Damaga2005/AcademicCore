# SPDX-License-Identifier: MIT
"""ML-10: ejercicios, corrección por equivalencia y pistas (§7, §8.2 S).

Operación ``ejercicio`` (contrato §5.9) con ``calculo``:
genera (plantilla sembrada con su solución), corrige (por equivalencia,
nunca por texto), pistas (graduadas) y banco (qué temas hay).
"""

from __future__ import annotations

from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import ejercicios as EJ
from academic_core.domain.engineering.mathlab import verify as V
from academic_core.domain.engineering.mathlab.calculators import _finalizar, con_discrepancia
from academic_core.domain.engineering.mathlab.trace import Trace


def _dict(peticion: C.Peticion, que: str) -> dict:
    e = peticion.entrada
    if not isinstance(e, dict):
        raise C.error("BAD_INPUT", f"se espera un diccionario para «{que}»")
    return e


def _ok(peticion, trace, exacto, metodo, detalle="", grafica=None, avisos=()):
    return _finalizar(peticion, trace, exacto,
                      sello=V.Seal(V.VERIFIED, metodo, detalle), grafica=grafica,
                      avisos=tuple(avisos))


_con_discrepancia = con_discrepancia


@_con_discrepancia
def _ejercicio(peticion: C.Peticion) -> C.Resultado:
    e = _dict(peticion, "ejercicio")
    calculo = str(e.get("calculo", "genera"))
    trace = Trace()

    if calculo == "banco":
        filas = [f"{t} ({d['asignatura']})" for t, d in sorted(EJ.TEMAS.items())]
        trace.metodo("ejercicio.banco", "listar los temas con su asignatura",
                     why="el generador es sembrado por tema (§7)")
        return _ok(peticion, trace, "; ".join(filas),
                   "catálogo de temas del banco", f"{len(filas)} temas")

    if calculo == "genera":
        ex = EJ.genera(str(e.get("tema", "limites")),
                       str(e.get("dificultad", "media")),
                       int(e.get("semilla", 1)))
        trace.metodo("ejercicio.genera",
                     f"generador sembrado de «{ex.tema}» con semilla "
                     f"{e.get('semilla', 1)}",
                     why="la solución la pide el motor, no la escribe el "
                         "generador: así enunciado y solución no pueden "
                         "desincronizarse (§7)")
        trace.hipotesis("ejercicio.planteado",
                        f"respuesta no degenerada ({ex.tipo})",
                        f"cumple: {ex.solucion!r}"[:120])
        # segundo camino: la solución generada se corrige a sí misma
        v = EJ.corrige(ex, ex.solucion)
        if not v.correcto:
            raise C.error("DISCREPANT",
                          f"la solución generada no se acepta a sí misma: {v.detalle}")
        trace.verificacion("ejercicio.autocorreccion",
                           f"la solución del ejercicio se corrige como "
                           f"correcta por {v.metodo}")
        cuerpo = (f"{ex.enunciado}\n"
                  f"tipo de entrega: {ex.tipo}; respaldo: {ex.respaldo} "
                  f"({'examen real' if ex.respaldo == 'E' else 'solo guía'}); "
                  f"dificultad: {ex.dificultad}\n"
                  f"solución: {ex.solucion!r}")
        return _ok(peticion, trace, cuerpo,
                   f"generador de {ex.tema}", f"tema {ex.tema} · {ex.id}",
                   grafica=ex.grafica)

    if calculo == "corrige":
        ex = EJ.genera(str(e.get("tema", "limites")),
                       str(e.get("dificultad", "media")),
                       int(e.get("semilla", 1)))
        respuesta = e.get("respuesta")
        trace.metodo("ejercicio.corrige",
                     "comparar formas normales, no los textos",
                     why="2x+2x y 4x son la misma respuesta; comparar textos "
                         "aceptaría una y rechazaría la otra (§7)")
        if e.get("propiedad"):
            v = EJ.comprueba_propiedad(str(e["propiedad"]), respuesta)
            trace.metodo("ejercicio.propiedad",
                         f"comprobar la propiedad «{e['propiedad']}»",
                         why="la respuesta no es única: se corrige por "
                             "propiedad, nunca por su forma (§7)")
        else:
            v = EJ.corrige(ex, respuesta)
        trace.verificacion("ejercicio.veredicto", v.metodo, after=v.detalle)
        sello = V.Seal(v.sello, v.metodo, v.detalle)
        return _finalizar(peticion, trace, v.texto(), sello=sello)

    if calculo == "pistas":
        ex = EJ.genera(str(e.get("tema", "limites")),
                       str(e.get("dificultad", "media")),
                       int(e.get("semilla", 1)))
        n = int(e.get("n", len(ex.pistas)))
        pistas = ex.pistas_hasta(n)
        trace.metodo("ejercicio.pistas",
                     f"primeras {len(pistas)} pistas, de menos a más ayuda",
                     why="pistas graduadas: la primera orienta y la última "
                         "descompone el problema (§7)")
        return _ok(peticion, trace,
                   " | ".join(f"{i + 1}. {p}" for i, p in enumerate(pistas)),
                   f"{len(pistas)} pistas de {len(ex.pistas)}",
                   f"degradación gradual")

    if calculo == "solucion":
        ex = EJ.genera(str(e.get("tema", "limites")),
                       str(e.get("dificultad", "media")),
                       int(e.get("semilla", 1)))
        trace.metodo("ejercicio.solucion",
                     "la solución paso a paso que el motor ya escribió al "
                     "generar el ejercicio",
                     why="son los mismos pasos que escribió la calculadora al "
                         "generar el ejercicio, no una redacción aparte (§7)")
        return _ok(peticion, trace,
                   ex.solucion_pasos or f"solución: {ex.solucion!r}",
                   f"solución de {ex.id}", f"respuesta {ex.solucion!r}",
                   grafica=ex.grafica)

    raise C.error("BAD_INPUT", f"cálculo desconocido: {calculo}")


C.registrar("ejercicio", _ejercicio)