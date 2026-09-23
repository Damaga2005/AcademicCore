# SPDX-License-Identifier: MIT
"""Reference oracle: Gestion-Academica grade semantics, verbatim (float).

Line-by-line port of Gestion `models.calcular_resultado_componentes`,
`EsquemaEvaluacion.componentes_efectivos_objs` and `calcular_estado_notas`
(Gestion-Academica@187a614), operating on raw legacy rows instead of ORM
objects. It exists ONLY to prove equivalence of the canonical Decimal
implementation (domain/evaluation.py) during migration validation and in
golden tests. Never used to compute anything shown to the user.
"""

from __future__ import annotations

from types import SimpleNamespace

NOTA_MINIMA_APROBADO = 5.0


def calcular_resultado_componentes(componentes):
    con_nota = [c for c in componentes if c.nota is not None]
    peso_total = sum(c.porcentaje for c in componentes)
    peso_evaluado = sum(c.porcentaje for c in con_nota)
    porcentaje_evaluado = round((peso_evaluado / peso_total) * 100, 2) if peso_total else 0.0
    media_ponderada = None
    if con_nota and peso_evaluado > 0:
        media_ponderada = round(sum(c.porcentaje * c.nota for c in con_nota) / peso_evaluado, 4)
    return {"peso_total": peso_total, "peso_evaluado": peso_evaluado,
            "porcentaje_evaluado": porcentaje_evaluado, "media_ponderada": media_ponderada}


def _componente(r):
    return SimpleNamespace(
        id=r["id"], porcentaje=r["porcentaje"], nota=r.get("nota"),
        nota_minima=r.get("nota_minima"), bloque_id=r.get("bloque_id"),
        orden=r.get("orden") if r.get("orden") is not None else 1_000_000,
        incumple_minimo=lambda r=r: (r.get("nota") is not None and r.get("nota_minima") is not None
                                     and r["nota"] < r["nota_minima"]))


def _esquemas(asignatura_id, esquemas, bloques, componentes):
    out = []
    for e in sorted((e for e in esquemas if e["asignatura_id"] == asignatura_id),
                    key=lambda e: (e.get("orden") or 0, e["id"])):
        comps = sorted((_componente(c) for c in componentes if c.get("esquema_id") == e["id"]),
                       key=lambda c: (c.orden, c.id))
        blks = []
        for b in sorted((b for b in bloques if b["esquema_id"] == e["id"]),
                        key=lambda b: (b.get("orden") or 0, b["id"])):
            members = [c for c in comps if c.bloque_id == b["id"]]
            blks.append(SimpleNamespace(porcentaje=b["porcentaje"], componentes=members))

        def efectivos(comps=comps, blks=blks):
            sueltos = [c for c in comps if c.bloque_id is None]
            return sueltos + [SimpleNamespace(
                porcentaje=b.porcentaje,
                nota=calcular_resultado_componentes(b.componentes)["media_ponderada"])
                for b in blks]

        out.append(SimpleNamespace(id=e["id"], componentes=comps,
                                   componentes_efectivos_objs=efectivos))
    return out


def gestion_estado_notas(asignatura: dict, esquemas: list[dict], bloques: list[dict],
                         componentes: list[dict]) -> dict:
    lista = _esquemas(asignatura["id"], esquemas, bloques, componentes)
    todos = [_componente(c) for c in componentes if c["asignatura_id"] == asignatura["id"]]
    evaluaciones_realizadas = 0
    evaluaciones_pendientes = 0
    porcentaje_evaluado = 0.0
    minimo_incumplido = False
    if asignatura.get("nota_final") is not None:
        nota = asignatura["nota_final"]
        evaluada = True
        comps = [c for e in lista for c in e.componentes_efectivos_objs()] or todos
        evaluaciones_realizadas = sum(1 for c in comps if c.nota is not None)
        evaluaciones_pendientes = sum(1 for c in comps if c.nota is None)
        porcentaje_evaluado = 100.0
    else:
        nota = None
        evaluada = False
        resultados = [(e, calcular_resultado_componentes(e.componentes_efectivos_objs()))
                      for e in lista]
        candidatos = [(e, r) for e, r in resultados if r["media_ponderada"] is not None]
        if candidatos:
            esquema, resultado = max(candidatos, key=lambda par: par[1]["media_ponderada"])
            porcentaje_evaluado = resultado["porcentaje_evaluado"]
            minimo_incumplido = any(c.incumple_minimo() for c in esquema.componentes)
            efectivos = esquema.componentes_efectivos_objs()
            evaluaciones_realizadas = sum(1 for c in efectivos if c.nota is not None)
            evaluaciones_pendientes = sum(1 for c in efectivos if c.nota is None)
            if resultado["peso_total"] > 0 and resultado["peso_evaluado"] >= resultado["peso_total"]:
                nota = resultado["media_ponderada"]
                evaluada = True
    if evaluada:
        estado = "aprobada" if nota >= NOTA_MINIMA_APROBADO and not minimo_incumplido else "suspendida"
    elif evaluaciones_realizadas > 0:
        estado = "en_progreso"
    else:
        estado = "sin_evaluar"
    return {"estado_notas": estado, "nota_actual": nota,
            "evaluaciones_realizadas": evaluaciones_realizadas,
            "evaluaciones_pendientes": evaluaciones_pendientes,
            "porcentaje_evaluado": porcentaje_evaluado, "minimo_incumplido": minimo_incumplido}
