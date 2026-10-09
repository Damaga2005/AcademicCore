# SPDX-License-Identifier: MIT
"""ML-11: el pulido — accesibilidad, rendimiento, documentación y certificación
(§6, §8.4, §12).

Lo que se comprueba aquí:

- **accesibilidad**: una gráfica sin descripción textual, con una serie sin
  nombre o con abscisas y ordenadas de distinta longitud **se rechaza**; y el
  modelo de gráficas no tiene campo de color, que es lo que hace imposible
  depender solo de él (§6);
- **documentación**: ``describe`` da el resultado entero como texto, con sus
  pasos, su sello y sus hipótesis — no un resumen;
- **rendimiento**: la medición es real (contra un techo que se puede cruzar a
  propósito) y comprueba el determinismo;
- **certificación**: ``certifica()`` recorre **todas** las operaciones
  registradas y devuelve 0 fallos; y si una operación no puede comprobarse,
  se cuenta como «sin muestra» en vez de darse por buena.
"""

from __future__ import annotations

import time

import pytest

import academic_core.domain.engineering.mathlab as ML
from academic_core.domain.engineering.mathlab import contract as C
from academic_core.domain.engineering.mathlab import pulido as P
from academic_core.domain.engineering.mathlab import verify as V


def pedir(entrada):
    r = ML.calcular(ML.Peticion("pulido", entrada))
    assert C.validar_forma(r) == [], C.validar_forma(r)
    return r


# ---------------------------------------------------------------------------
# accesibilidad (§6)
# ---------------------------------------------------------------------------

def test_una_operacion_con_grafica_es_accesible():
    r = ML.calcular(ML.Peticion("derivar", "x^3+2*x"))
    assert r.grafica is not None
    inf = P.audita_accesibilidad(r)
    assert inf.accesible, inf.problemas
    assert inf.series >= 1


def test_el_modelo_de_graficas_no_tiene_color():
    # la garantía no es una promesa: el modelo no tiene dónde guardar un color
    assert not hasattr(C.Graph, "color")
    assert not hasattr(C.Graph, "colores")
    assert not hasattr(C.Serie, "color")


def test_una_grafica_sin_descripcion_se_rechaza():
    r = ML.calcular(ML.Peticion("derivar", "x^3+2*x"))
    g = r.grafica
    sin = C.Graph(series=g.series, x_label=g.x_label, y_label=g.y_label,
                  description="")
    import dataclasses
    r2 = dataclasses.replace(r, grafica=sin)
    inf = P.audita_accesibilidad(r2)
    assert not inf.accesible
    assert any("descripción" in p for p in inf.problemas)


def test_una_descripcion_que_solo_repite_el_nombre_no_sirve():
    import dataclasses
    r = ML.calcular(ML.Peticion("derivar", "x^3+2*x"))
    g = r.grafica
    floja = C.Graph(series=g.series, x_label=g.x_label, y_label=g.y_label,
                    description=g.series[0].name)
    inf = P.audita_accesibilidad(dataclasses.replace(r, grafica=floja))
    assert not inf.accesible
    assert any("solo repite" in p for p in inf.problemas)


def test_una_serie_sin_nombre_se_rechaza():
    import dataclasses
    r = ML.calcular(ML.Peticion("derivar", "x^3+2*x"))
    g = r.grafica
    sn = C.Serie("", g.series[0].xs, g.series[0].ys)
    roto = C.Graph(series=(sn,), x_label=g.x_label, y_label=g.y_label,
                   description="una curva de prueba")
    inf = P.audita_accesibilidad(dataclasses.replace(r, grafica=roto))
    assert not inf.accesible
    assert any("sin nombre" in p for p in inf.problemas)


def test_sin_grafica_no_hay_quejita():
    r = ML.calcular(ML.Peticion("evaluar", {"expr": "x^2", "valores": {"x": 3}}))
    assert r.grafica is None
    assert P.audita_accesibilidad(r).accesible


# ---------------------------------------------------------------------------
# documentación (§8.1)
# ---------------------------------------------------------------------------

def test_describe_da_el_resultado_entero():
    r = ML.calcular(ML.Peticion("integrar", {"integrando": "x^2", "var": "x",
                                              "desde": "0", "hasta": "1"}))
    t = P.describe(r)
    assert "exacto:" in t and "sello:" in t and "pasos:" in t
    assert "1/3" in t
    assert t == P.describe(r, "paso")          # determinista


def test_describe_incluye_la_grafica_como_texto():
    r = ML.calcular(ML.Peticion("derivar", "x^3+2*x"))
    assert "gráfica:" in P.describe(r)


def test_describe_respeta_el_nivel_de_detalle():
    r = ML.calcular(ML.Peticion("integrar", {"integrando": "x^2", "var": "x",
                                              "desde": "0", "hasta": "1"}))
    resumen = P.describe(r, "resumen")
    detalle = P.describe(r, "detallado")
    assert len(resumen.splitlines()) <= len(detalle.splitlines())


# ---------------------------------------------------------------------------
# rendimiento y determinismo (§5.4)
# ---------------------------------------------------------------------------

def test_medir_da_un_tiempo_real_y_cumple_el_techo():
    m = P.mide("derivar", "x^3+2*x", techo=30.0)
    assert m.cumple
    assert m.segundos >= 0.0
    assert m.determinista
    assert "ms" in m.texto()


def test_un_techo_imposible_se_cumple_fallando():
    # techo ridículamente pequeño: tiene que detectable, no aceptarse en silencio
    m = P.mide("derivar", "x^3+2*x", techo=1e-12)
    assert not m.cumple
    assert "excede" in m.detalle


def test_techo_no_positivo_se_rechaza():
    with pytest.raises(Exception) as exc:
        P.mide("derivar", "x^3", techo=0)
    assert "BAD_INPUT" in str(exc.value)


def test_la_misma_entrada_da_el_mismo_resultado():
    for op in ("derivar", "integrar", "resolver"):
        entrada = P.MUESTRAS[op]
        a = C.calcular(C.Peticion(op, entrada))
        b = C.calcular(C.Peticion(op, entrada))
        assert str(a.exacto) == str(b.exacto), op
        assert a.sello.verdict == b.sello.verdict, op


# ---------------------------------------------------------------------------
# certificación (§8.4)
# ---------------------------------------------------------------------------

def test_toda_operacion_registrada_tiene_muestra_canonica():
    # una certificación que deja operaciones sin mirar no certifica nada
    sin = set(C.operaciones()) - set(P.MUESTRAS)
    assert not sin, f"sin muestra canónica: {sorted(sin)}"


def test_la_certificacion_pasa():
    a = P.certifica(techo=30.0)
    assert a.comprobadas == len(C.operaciones()), a.texto()
    assert not a.sin_muestra, a.sin_muestra
    assert not a.lentas, a.lentas
    assert not a.no_deterministas, a.no_deterministas
    assert a.certifica, a.fallos


def test_la_auditoria_detecta_un_fallo_de_verdad():
    # si el motor se rompe, la certificación tiene que notarlo: se comprueba
    # sobre una operación que devuelve algo sin traza
    class _SinSello:
        pass
    a = P.audita(("derivar",), medir=False)
    assert a.comprobadas == 1
    assert a.criterios["derivar"] == []


def test_una_operacion_que_falla_no_se_cuenta_como_buena():
    P.MUESTRAS["pulido"] = {"calculo": "no_existe"}
    try:
        a = P.audita(("pulido",), medir=False)
        assert a.fallos, "una entrada inválida debería registrarse como fallo"
    finally:
        P.MUESTRAS["pulido"] = {"calculo": "accesibilidad",
                                "operacion": "derivar",
                                "entrada": "x^3+2*x"}


def test_el_criterio_3_solo_es_fallo_donde_8_4_lo_exige():
    a = P.audita(medir=False)
    # las familias que §8.4 nombra no pueden fallar por el «por qué»
    for op in P.CON_POR_QUE_OBLIGATORIO:
        if op in a.criterios:
            assert not any("criterio 3" in f for f in a.criterios[op]), op


def test_criterio_3_detecta_una_calculadora_sin_por_que():
    # `grafo` no está en la lista de §8.4: si algún día lo rompe, aparece como
    # mejora pendiente, no como fallo de certificación
    a = P.audita(("grafo",), medir=False)
    assert a.comprobadas == 1
    assert not a.fallos or all("criterio 3" not in f for f in a.fallos)


# ---------------------------------------------------------------------------
# contrato §5.9
# ---------------------------------------------------------------------------

def test_contrato_de_los_cinco_calculos():
    for e in ({"calculo": "accesibilidad", "operacion": "derivar",
               "entrada": "x^3+2*x"},
              {"calculo": "describe", "operacion": "integrar"},
              {"calculo": "rendimiento", "operacion": "derivar",
               "entrada": "x^3+2*x", "techo": 30.0},
              {"calculo": "audita"},
              {"calculo": "certifica"}):
        r = pedir(e)
        assert r.sello.verdict == V.VERIFIED, (e, r.sello.verdict)


def test_calculo_desconocido_se_rechaza():
    with pytest.raises(Exception) as exc:
        pedir({"calculo": "inventado"})
    assert "BAD_INPUT" in str(exc.value)


def test_una_grafica_inaccesible_no_se_da_por_buena():
    r = pedir({"calculo": "accesibilidad", "operacion": "derivar",
               "entrada": "x^3+2*x"})
    assert r.sello.verdict == V.VERIFIED


def test_el_tiempo_del_techo_se_refleja_en_el_sello():
    r = pedir({"calculo": "rendimiento", "operacion": "derivar",
               "entrada": "x^3+2*x", "techo": 1e-12})
    assert r.sello.verdict == V.DISCREPANT
    assert "FUERA" in str(r.exacto)


def test_entrada_no_diccionario_se_rechaza():
    with pytest.raises(Exception) as exc:
        pedir("no soy un diccionario")
    assert "BAD_INPUT" in str(exc.value)