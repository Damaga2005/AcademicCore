# SPDX-License-Identifier: MIT
"""ML-11: el pulido — accesibilidad, rendimiento, documentación y
certificación (§6, §8.4, §12).

Operación ``pulido`` (contrato §5.9) con ``calculo``:
accesibilidad, describe, rendimiento, audita y certifica.
"""

from __future__ import annotations

from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import pulido as P
from academic_core.domain.engineering.mathlab import verify as V
from academic_core.domain.engineering.mathlab.calculators import _finalizar, con_discrepancia
from academic_core.domain.engineering.mathlab.trace import Trace


def _dict(peticion: C.Peticion, que: str) -> dict:
    e = peticion.entrada
    if not isinstance(e, dict):
        raise C.error("BAD_INPUT", f"se espera un diccionario para «{que}»")
    return e


def _ok(peticion, trace, exacto, metodo, detalle="", avisos=()):
    return _finalizar(peticion, trace, exacto,
                      sello=V.Seal(V.VERIFIED, metodo, detalle),
                      avisos=tuple(avisos))


_con_discrepancia = con_discrepancia


@_con_discrepancia
def _pulido(peticion: C.Peticion) -> C.Resultado:
    e = _dict(peticion, "pulido")
    calculo = str(e.get("calculo", "accesibilidad"))
    trace = Trace()

    if calculo == "accesibilidad":
        op = str(e.get("operacion", "derivar"))
        entrada = e.get("entrada", "x^3+2*x")
        trace.metodo("pulido.accesibilidad",
                     "leer el resultado y comprobar que su gráfica se "
                     "entiende sin verla",
                     why="§6 pide descripción textual de cada gráfica y "
                         "prohibite depender solo del color")
        r = C.calcular(C.Peticion(op, entrada))
        inf = P.audita_accesibilidad(r)
        trace.verificacion("pulido.descripcion",
                           inf.texto(),
                           after=f"serie(s): {inf.series}")
        if not inf.accesible:
            return _finalizar(peticion, trace, inf.texto(),
                              sello=V.Seal(V.DISCREPANT, "gráfica inaccesible",
                                           "; ".join(inf.problemas)))
        return _ok(peticion, trace, inf.texto(),
                   f"accesibilidad de «{op}»", inf.texto())

    if calculo == "describe":
        op = str(e.get("operacion", "integrar"))
        entrada = e.get("entrada", {"integrando": "x^2", "var": "x",
                                    "desde": "0", "hasta": "1"})
        trace.metodo("pulido.describe",
                     "volcar el resultado entero como texto",
                     why="lo lee un lector de pantalla y es lo que se copia a "
                         "otro laboratorio (§8.1)")
        r = C.calcular(C.Peticion(op, entrada))
        texto = P.describe(r, str(e.get("nivel", "paso")))
        trace.verificacion("pulido.describe_texto",
                           f"{len(texto.splitlines())} líneas de texto")
        return _ok(peticion, trace, texto, f"descripción de «{op}»",
                   "valor + pasos + sello + hipótesis")

    if calculo == "rendimiento":
        op = str(e.get("operacion", "derivar"))
        entrada = e.get("entrada", "x^3+2*x")
        techo = float(e.get("techo", P.TECHO_S))
        trace.metodo("pulido.rendimiento",
                     f"medir la llamada contra un techo de {techo:g} s",
                     why="§5.4 pone topes de tiempo y tamaño: sin ellos una "
                         "expresión patológica se queda colgada")
        m = P.mide(op, entrada, techo=techo)
        trace.hipotesis("pulido.determinismo",
                        "la misma entrada da el mismo resultado",
                        "cumple" if m.determinista else "FALLA")
        trace.verificacion("pulido.medida", m.texto(), after=m.detalle)
        if not m.cumple:
            return _finalizar(peticion, trace, m.texto(),
                              sello=V.Seal(V.DISCREPANT, "fuera del techo",
                                           m.detalle))
        return _ok(peticion, trace, m.texto(), "medición real",
                   m.detalle)

    if calculo == "pasos":
        trace.metodo("pulido.pasos",
                     "recorrer todas las operaciones exigiendo traza no vacía, "
                     "un «por qué» y un paso de método",
                     why="§5.2 y §5.5b: el estudiante tiene que ver los pasos "
                         "y por qué se eligió ese método. Una calculadora que "
                         "devuelve el número sin explicar nada incumple, y "
                     "aquí se nota en vez de confiar en que todas lo hacen")
        fallos = P.audita_pasos()
        detalle = f"{len(fallos)} calculadoras sin los pasos completos"
        cuerpo = (f"{len(C.operaciones())} calculadoras comprobadas; "
                  f"{len(fallos)} sin pasos completos")
        if fallos:
            cuerpo += "\n" + "\n".join("  - " + f for f in fallos)
            return _finalizar(peticion, trace, cuerpo,
                              sello=V.Seal(V.DISCREPANT, "pasos incompletos",
                                           detalle))
        return _ok(peticion, trace, cuerpo, "todas muestran sus pasos", detalle)

    if calculo == "robustez":
        trace.metodo("pulido.robustez",
                     "alimentar entradas mal formadas a todas las "
                     "calculadoras y exigir un rechazo con motivo",
                     why="una petición mala debe decir qué está mal; un "
                         "TypeError o un IndexError son bugs de programación, "
                         "no mensajes para el estudiante. Merece la pena "
                         "comprobarlo porque es lo que más fácil se rompe al "
                         "tocar un cálculo")
        rotos = P.audita_robustez()
        detalle = f"{len(rotos)} errores internos"
        cuerpo = (f"{len(C.operaciones())} calculadoras alimentadas con "
                  f"basura; {len(rotos)} responden con un error interno")
        if rotos:
            cuerpo += "\n" + "\n".join("  - " + f for f in rotos)
            return _finalizar(peticion, trace, cuerpo,
                              sello=V.Seal(V.DISCREPANT, "errores internos",
                                           detalle))
        return _ok(peticion, trace, cuerpo, "ninguna revienta por dentro",
                   detalle)

    if calculo in ("audita", "certifica"):
        medir = calculo == "certifica"
        trace.metodo(
            f"pulido.{calculo}",
            "recorrer las operaciones registradas con una entrada canónica y "
            "comprobar los criterios de §8.4 uno a uno",
            why="un criterio que no se ejecuta acaba mintiendo; lo que no se "
                "puede comprobar se lista aparte y no se cuenta como bueno")
        a = P.audita(medir=medir) if not medir else P.certifica()
        trace.verificacion("pulido.recuento", a.texto(),
                           after=f"{len(a.criterios)} operaciones con detalle")
        detalle = (f"fallos: {len(a.fallos)}; sin muestra: {len(a.sin_muestra)}; "
                   f"lentas: {len(a.lentas)}; no deterministas: "
                   f"{len(a.no_deterministas)}; sin «por qué»: "
                   f"{len(a.sin_porque)}")
        cuerpo = a.texto()
        if a.sin_muestra:
            cuerpo += "\nsin muestra canónica: " + ", ".join(a.sin_muestra)
        if a.fallos:
            cuerpo += "\nfallos:\n" + "\n".join("  - " + f for f in a.fallos[:40])
        if a.lentas:
            cuerpo += "\nfuera del techo: " + ", ".join(a.lentas)
        if a.no_deterministas:
            cuerpo += "\nno deterministas: " + ", ".join(a.no_deterministas)
        if a.sin_porque:
            cuerpo += ("\nmejora pendiente (§8.4 no lo exige para estas): "
                       + ", ".join(a.sin_porque))
        if a.fallos or a.lentas or a.no_deterministas:
            return _finalizar(peticion, trace, cuerpo,
                              sello=V.Seal(V.DISCREPANT, "auditoría con fallos",
                                           detalle))
        return _ok(peticion, trace, cuerpo, "auditoría de §8.4", detalle)

    raise C.error("BAD_INPUT", f"cálculo desconocido: {calculo}")


C.registrar("pulido", _pulido)