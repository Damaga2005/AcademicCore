# SPDX-License-Identifier: MIT
"""Synthetic Gestion-Academica database on the REAL legacy schema.

The DDL (tests/fixtures/gestion/schema.sql) was dumped from a database
created by Gestion-Academica@187a614's own Alembic migrations; the rows
below are synthetic (no personal data) and exercise every table plus the
edge cases the F4.1 migration must survive without loss.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).parent / "fixtures" / "gestion" / "schema.sql"
PDF = b"%PDF-1.4\n% synthetic, never parsed by the migration\n%%EOF\n"


def _ins(cx, table: str, **cols) -> None:
    keys = ", ".join(cols)
    marks = ", ".join("?" * len(cols))
    cx.execute(f'INSERT INTO "{table}" ({keys}) VALUES ({marks})', tuple(cols.values()))


def build(tmp: Path, *, docs: bool = True) -> tuple[Path, Path]:
    db = tmp / "academico.db"
    root = tmp / "documentos"
    tmp.mkdir(parents=True, exist_ok=True)
    cx = sqlite3.connect(db)
    cx.executescript(SCHEMA.read_text(encoding="utf-8"))
    _ins(cx, "alembic_version", version_num="e5a7c9b1d3f4")
    # hierarchy: 2 years, 3 terms (two "actual")
    _ins(cx, "anio", id=1, numero=1)
    _ins(cx, "anio", id=2, numero=2)
    _ins(cx, "cuatrimestre", id=1, anio_id=1, numero=1, estado="superado")
    _ins(cx, "cuatrimestre", id=2, anio_id=1, numero=2, estado="actual")
    _ins(cx, "cuatrimestre", id=3, anio_id=2, numero=3, estado="actual")
    base = dict(tipo="obligatoria", origen_catalogo=0, regla_esquemas="maximo")
    _ins(cx, "asignatura", id=1, cuatrimestre_id=1, nombre="Álgebra Lineal", siglas="AL",
         creditos_ects=6.0, estado="superada", nota_final=7.25, **base)
    _ins(cx, "asignatura", id=2, cuatrimestre_id=2, nombre="Diseño Digital", siglas="DD",
         creditos_ects=6.0, estado="cursando", notas="apuntes", notas_actualizado_en=
         "2026-09-01 10:00:00.000000", link_aula_virtual="https://aula.example.edu/dd",
         nombre_profesor="Legacy Contact", correo_profesor="lc@example.edu", **base)
    _ins(cx, "asignatura", id=3, cuatrimestre_id=3, nombre="Señales", siglas="SS",
         creditos_ects=4.5, estado="cursando", **base)
    _ins(cx, "asignatura", id=4, cuatrimestre_id=3, nombre="Física", siglas=None,
         creditos_ects=6.0, estado="no_superada", **base)
    _ins(cx, "asignatura", id=5, cuatrimestre_id=3, nombre="Optativa X", siglas="OX",
         creditos_ects=3.0, estado="no_elegida", tipo="optativa", origen_catalogo=1,
         regla_esquemas="maximo")
    _ins(cx, "asignatura", id=6, cuatrimestre_id=3, nombre="Trabajo de Fin de Grado",
         siglas="TFG", creditos_ects=12.0, estado="pendiente", **base)
    _ins(cx, "asignatura_prerrequisito", asignatura_id=3, prerrequisito_id=1)
    # professors: homonym across subjects, one duplicate in the same subject
    _ins(cx, "profesor", id=1, asignatura_id=2, nombre="Ana Pérez", rol="Responsable",
         correo="ana@example.edu", despacho="D-1", aula_virtual="https://x.example.edu", orden=0)
    _ins(cx, "profesor", id=2, asignatura_id=3, nombre="Ana Pérez", rol="Grupo 11",
         correo="ana@example.edu", orden=0)
    _ins(cx, "profesor", id=3, asignatura_id=2, nombre="Luis Gil", rol=None, orden=1)
    _ins(cx, "profesor", id=4, asignatura_id=2, nombre="Luis Gil", rol="Lab", orden=2)
    # evaluation: DD two schemes + block + min grade; SS one scheme; Física orphan comp
    _ins(cx, "esquema_evaluacion", id=1, asignatura_id=2, nombre="Continua", orden=0)
    _ins(cx, "esquema_evaluacion", id=2, asignatura_id=2, nombre="Solo final", orden=1)
    _ins(cx, "esquema_evaluacion", id=3, asignatura_id=3, nombre="Evaluación", orden=0)
    _ins(cx, "bloque_evaluacion", id=1, esquema_id=1, nombre="Laboratorio", porcentaje=40.0,
         orden=0)
    comp = dict(asignatura_id=2, tipo="otro")
    _ins(cx, "componente_evaluacion", id=1, esquema_id=1, nombre="Parcial", porcentaje=30.0,
         nota=6.5, tipo="parcial", asignatura_id=2, orden=0)
    _ins(cx, "componente_evaluacion", id=2, esquema_id=1, nombre="Final", porcentaje=30.0,
         nota=3.5, nota_minima=4.0, tipo="examen_final", asignatura_id=2, orden=1)
    _ins(cx, "componente_evaluacion", id=3, esquema_id=1, bloque_id=1, nombre="P1",
         porcentaje=33.33, nota=9.0, orden=0, **comp)
    _ins(cx, "componente_evaluacion", id=4, esquema_id=1, bloque_id=1, nombre="P2",
         porcentaje=66.67, nota=8.0, orden=1, **comp)
    _ins(cx, "componente_evaluacion", id=5, esquema_id=2, nombre="Final", porcentaje=100.0,
         nota=3.5, tipo="examen_final", asignatura_id=2, orden=0)
    _ins(cx, "componente_evaluacion", id=6, esquema_id=3, nombre="Examen", porcentaje=60.0,
         nota=7.0, asignatura_id=3, tipo="examen_final", orden=0)
    _ins(cx, "componente_evaluacion", id=7, esquema_id=3, nombre="Lab", porcentaje=40.0,
         nota=None, asignatura_id=3, tipo="laboratorio", orden=1)
    # external resources
    _ins(cx, "recurso_externo", id=1, asignatura_id=2, nombre="Wuolah",
         url="https://wuolah.com/apuntes/dd", orden=0)
    _ins(cx, "recurso_externo", id=2, asignatura_id=2, nombre="Studocu",
         url="https://www.studocu.com/es/course/x/1", orden=1)
    # documents
    _ins(cx, "apartado", id=1, asignatura_id=2, nombre="Teoría", orden=0)
    _ins(cx, "grupo_documento", id=1, asignatura_id=2, categoria="teoria", nombre="Tema 1",
         orden=0, created_at="2026-01-01 00:00:00", updated_at="2026-01-01 00:00:00")
    doc = dict(asignatura_id=2, fecha_subida="2026-02-01 09:00:00.000000",
               tiempo_total_lectura_segundos=0, numero_sesiones=0)
    _ins(cx, "documento", id=1, nombre_archivo="tema1.pdf", ruta_local="2_dd/teoria/1/tema1.pdf",
         categoria="teoria", grupo_documento_id=1, apartado_id=1, etiquetas="vhdl, fsm",
         ultima_pagina_vista=3, porcentaje_leido=42.5, fecha_ultima_apertura=
         "2026-09-20 18:00:00", **{**doc, "tiempo_total_lectura_segundos": 600,
                                   "numero_sesiones": 2})
    _ins(cx, "documento", id=2, nombre_archivo="notas.txt", ruta_local="2_dd/otros/notas.txt",
         categoria="otros", **doc)
    _ins(cx, "documento", id=3, nombre_archivo="codigo.zip", ruta_local="2_dd/laboratorios/c.zip",
         categoria="laboratorios", **doc)
    _ins(cx, "documento", id=4, nombre_archivo="copia.pdf", ruta_local="2_dd/teoria/copia.pdf",
         categoria="teoria", **doc)  # same bytes as id 1, same subject
    _ins(cx, "documento", id=5, nombre_archivo="falta.pdf", ruta_local="2_dd/otros/falta.pdf",
         categoria="otros", **doc)  # file missing on disk
    _ins(cx, "documento", id=6, nombre_archivo="evil.pdf", ruta_local="../../etc/passwd",
         categoria="otros", **doc)  # traversal attempt
    _ins(cx, "documento", id=7, nombre_archivo="tema1-ss.pdf", ruta_local="3_ss/t.pdf",
         categoria="teoria", **{**doc, "asignatura_id": 3})  # same bytes, other subject
    for n, text in ((1, "Máquinas de estados finitos"), (2, "Síntesis VHDL con registros")):
        _ins(cx, "pagina_texto", id=n, documento_id=1, numero_pagina=n, contenido=text,
             contenido_normalizado=text.lower())
    _ins(cx, "pagina_texto", id=3, documento_id=5, numero_pagina=1, contenido="perdida")
    _ins(cx, "marcador", id=1, documento_id=1, numero_pagina=2, titulo="FSM",
         fecha_creacion="2026-02-02 00:00:00")
    _ins(cx, "anotacion_pdf", id=1, documento_id=1, numero_pagina=1, tipo="resaltado",
         color="#ffd400", texto="estado", rects="[[0.1,0.1,0.2,0.05]]",
         fecha_creacion="2026-02-02 00:00:00")
    # calendar
    _ins(cx, "tarea_evento", id=1, asignatura_id=2, titulo="Parcial DD", fecha="2026-10-20",
         tipo="examen_parcial", completada=0, prioridad="alta", hora_inicio="09:00:00.000000",
         hora_fin="11:00:00.000000", aula="A1", ubicacion="Campus Nord", documento_id=1)
    _ins(cx, "tarea_evento", id=2, asignatura_id=None, titulo="Tutoría general",
         fecha="2026-09-25", tipo="evento", completada=0, prioridad="media")
    _ins(cx, "tarea_evento", id=3, asignatura_id=3, titulo="Entrega SS", fecha="2026-09-10",
         tipo="entrega", completada=0, prioridad="media", hora_fin="23:59:00.000000")
    _ins(cx, "tarea_evento", id=4, asignatura_id=3, titulo="Inicio sin fin", fecha="2026-11-01",
         tipo="tarea_general", completada=1, prioridad="baja", hora_inicio="10:00:00.000000")
    _ins(cx, "tarea_evento", id=5, asignatura_id=2, titulo="Repasar hoja perdida",
         fecha="2026-11-02", tipo="tarea_general", completada=0, prioridad="media",
         documento_id=5)  # linked document whose file is missing
    _ins(cx, "espacio_estudio", id=1, tarea_evento_id=1, nombre="Parcial DD",
         created_at="2026-09-01 00:00:00", updated_at="2026-09-01 00:00:00")
    _ins(cx, "espacio_estudio_documento", id=1, espacio_estudio_id=1, documento_id=1,
         seccion="teoria", leido=1, destacado=1, orden=0, fecha_referencia="2026-09-01")
    _ins(cx, "espacio_estudio_documento", id=2, espacio_estudio_id=1, documento_id=2,
         seccion="ejercicios", leido=0, destacado=0, orden=1, fecha_referencia="2026-09-01")
    _ins(cx, "objetivo_espacio", id=1, espacio_estudio_id=1, texto="Leer tema 1", completada=1,
         orden=0, created_at="2026-09-01")
    _ins(cx, "objetivo_espacio", id=2, espacio_estudio_id=1, texto="Hacer problemas",
         completada=0, orden=1, created_at="2026-09-01")
    _ins(cx, "horario_clase", id=1, asignatura_id=2, tipo="teoria", dia_semana=2,
         hora_inicio="09:00:00.000000", hora_fin="11:00:00.000000", aula="A1",
         fecha_inicio="2026-09-07", fecha_fin="2026-12-20", intervalo_semanas=1)
    _ins(cx, "horario_clase", id=2, asignatura_id=3, tipo="laboratorio", dia_semana=4,
         hora_inicio="15:00:00.000000", hora_fin="17:00:00.000000", fecha_inicio="2026-09-07",
         fecha_fin="2026-12-20", intervalo_semanas=2, notas="quincenal")
    # personal
    _ins(cx, "hito", id=1, nombre="Certificación inglés B2", estado="en_progreso",
         fecha="2027-01-15", orden=0)
    _ins(cx, "nota_rapida", id=1, texto="Revisar tema 3", fecha_creacion="2026-09-02 12:00:00")
    _ins(cx, "concepto", id=1, asignatura_id=2, nombre="Moore vs Mealy", estado="flojo",
         ultima_revision="2026-09-10", proxima_revision="2026-09-13")
    _ins(cx, "sesion_estudio", id=1, asignatura_id=2, fecha="2026-09-10", minutos=90,
         nota="VHDL")
    _ins(cx, "sesion_estudio", id=2, asignatura_id=None, fecha="2026-09-11", minutos=30)
    _ins(cx, "dia_actividad", fecha="2026-09-10")
    _ins(cx, "dia_actividad", fecha="2026-09-11")
    _ins(cx, "configuracion_app", id=1, tema="oscuro", dias_aviso_examen=7,
         dias_asignatura_abandonada=14, widgets_orden="recordatorios,calendario",
         objetivo_media=7.5)
    _ins(cx, "aviso_descartado", tipo="examen", entidad_id=1, fecha="2026-09-20")
    _ins(cx, "busqueda_favorito", id=1, tipo_entidad="asignatura", entidad_id=2,
         fecha_creacion="2026-09-01")
    _ins(cx, "busqueda_reciente", id=1, tipo_entidad="documento", entidad_id=1,
         etiqueta_mostrada="tema1.pdf", url="/vista/documentos/1", fecha_acceso="2026-09-01")
    cx.commit()
    cx.close()
    if docs:
        for rel, data in (("2_dd/teoria/1/tema1.pdf", PDF), ("2_dd/otros/notas.txt",
                                                              "Notas de síntesis VHDL".encode()),
                          ("2_dd/laboratorios/c.zip", b"PK\x03\x04opaque-never-opened"),
                          ("2_dd/teoria/copia.pdf", PDF), ("3_ss/t.pdf", PDF)):
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
    return db, root


TOTAL_ROWS = {
    "anio": 2, "cuatrimestre": 3, "asignatura": 6, "asignatura_prerrequisito": 1, "profesor": 4,
    "esquema_evaluacion": 3, "bloque_evaluacion": 1, "componente_evaluacion": 7,
    "recurso_externo": 2, "apartado": 1, "grupo_documento": 1, "documento": 7,
    "pagina_texto": 3, "marcador": 1, "anotacion_pdf": 1, "tarea_evento": 5,
    "espacio_estudio": 1, "espacio_estudio_documento": 2, "objetivo_espacio": 2,
    "horario_clase": 2, "hito": 1, "nota_rapida": 1, "concepto": 1, "sesion_estudio": 2,
    "dia_actividad": 2, "configuracion_app": 1, "aviso_descartado": 1, "busqueda_favorito": 1,
    "busqueda_reciente": 1,
}
