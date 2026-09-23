# SPDX-License-Identifier: MIT
# F4.1 — Delta map Gestion-Academica → AcademicCore

> Fase B del protocolo F4.1 (diseño de delta, previo a implementación).
> Fuente auditada: `Damaga2005/Gestion-Academica@187a614` (`master`, clon de solo lectura).
> Destino: AcademicCore (rama `claude/new-session-wn0twl`, base `31ad044`).
> Regla: Gestion aporta **capacidades, datos, reglas y relaciones**; nunca Flask,
> SQLAlchemy, blueprints, Jinja ni el ActiveRecord de `models.py`.

## 1. Verificación de datos de referencia (no inventados)

Los datos reales de Gestion (`academico.db`, `documentos/`) están en su
`.gitignore` y **no están disponibles** en el entorno de F4.1. Para no certificar
números de memoria, se generó una BD Gestion **auténtica** ejecutando su propio
código (Alembic `e5a7c9b1d3f4` + `seed.poblar_datos_iniciales` +
`cargar_guias_docentes{,_2}` + `cargar_studocu` + `cargar_wuolah`) en un venv aislado:

| Entidad | Doc F4.0 / FUNCIONALIDADES.md | Reproducido desde el código Gestion | Estado |
|---|---:|---:|---|
| asignaturas | 54 | 54 | VERIFICADO |
| asignaturas con siglas | 53 | 53 | VERIFICADO |
| profesores | 61 | 61 | VERIFICADO |
| esquemas de evaluación | 65 | 65 | VERIFICADO |
| componentes | 168 | 164 | DIFIERE (+4 = bloque *Laboratorio* de Diseño Digital añadido a mano, no en scripts) |
| recursos externos | 81 | 81 | VERIFICADO |
| documentos | ~676 | 0 | NO VERIFICABLE (datos personales fuera del repo) |
| grupos de documentos | 185 | 0 | NO VERIFICABLE |
| páginas indexadas | ~7400 | 0 | NO VERIFICABLE |
| clases (horario) / tareas / espacios | 9 / 15 / 7 | 0 / 0 / 0 | NO VERIFICABLE |

Consecuencia: la migración se implementa y se prueba sobre (a) el **esquema real**
de Gestion (DDL volcado de la BD generada, `tests/fixtures/gestion_schema.sql`) con
datos sintéticos que cubren todas las tablas, y (b) la BD de referencia generada
desde el código de Gestion. La migración de la BD personal del usuario queda
**pendiente de ejecución por el usuario** (dry-run → snapshot → apply → validate).

## 2. Mapa de capacidades

| Gestion (origen) | AcademicCore (destino) | Estrategia de migración | Fase / dependencia futura | Tests |
|---|---|---|---|---|
| `Anio` | `AcademicYear` (`year:<deg>-curso-N`) | 1:1, `legacy_map` | F4.1 | migration dry-run/apply |
| `Cuatrimestre` (numero 1–8, estado) | `Term` (kind `cuatrimestre`, index en el año, state) | 1:1 | F4.1 | idem |
| `Asignatura` | `Subject` extendido (acronym, credits, kind, course, state, final_grade, catalog_origin, scheme_rule, notes, virtual_classroom, extra) | 1:1, id por siglas/slug | F4.1 | domain + migration |
| estados `cursando/superada/no_superada/pendiente/no_elegida` | `AcademicStatus` CURSANDO/APROBADA/SUSPENDIDA/NO_CURSANDO + estado fino conservado | clasificación pura `career.classify` (sin pérdida) | F4.1 → Home/Carrera F15 | test_f4_domain |
| `cambiar_estado_asignatura` | `CareerService.change_status` | reimplementado (misma entidad, sin duplicar) | F4.1 | test_f4_mgmt |
| dashboard (`media-curso`, `media-por-cuatrimestre`, `objetivo-media`, progreso ECTS, cursando, entregas, semana) | `CareerService.home()` / `career()` / `averages()` / `degree_progress()` / `target_average()` | queries application, Decimal | UI F15 | test_f4_mgmt |
| `asignatura_prerrequisito` | `prerequisites` | 1:1 | F4.1 | migration |
| `Profesor` (+ campos legacy `nombre/correo/despacho_profesor`) | `Professor` (dedupe por nombre) + `SubjectStaff` (rol, orden, contacto por vínculo) | N:1 con aviso | F4.1 | migration |
| `EsquemaEvaluacion/BloqueEvaluacion/ComponenteEvaluacion` + `nota_minima` | `domain/evaluation.py` (`AssessmentScheme/Block/Component`, `MinGrade`, `WeightedResult`) | 1:1, Decimal desde texto | F4.1 | test_f4_evaluation (golden vs oráculo Gestion) |
| `calcular_resultado_componentes`, `esquemas_con_ganador`, `calcular_estado_notas` | `evaluation.aggregate/evaluate_subject` (reusa `grading.aggregate`) | reimplementado, ROUND_HALF_UP (ADR-0011) | F4.1 | golden |
| `Documento` + archivo en `DOCUMENTOS_DIR` | `Resource` + `ResourceVersion` en CAS (origin `migration`) + `course_documents` (categoría, grupo, etiquetas) | bytes → CAS SHA-256, dedup, nunca se ejecutan | F4.1 | test_f4_documents |
| `GrupoDocumento` | `DocumentGroup` (`docgroup:<s>:grp:N`) | 1:1 | F4.1 | idem |
| `Apartado` (legado) | `legacy_payloads` (+ nombre en `course_documents.legacy`) | conservado verbatim | sin uso nuevo (Gestion ya lo abandonó) | migration |
| progreso lectura (`ultima_pagina_vista`, `porcentaje_leido`, …) | `reading_progress` | 1:1 | F14 visor | migration |
| `PaginaTexto` | `document_pages` + cuerpo FTS del recurso | 1:1 + reindex FTS | F4.1 | FTS tests |
| `EspacioEstudio` / `EspacioEstudioDocumento` / `ObjetivoEspacio` | `StudySpace` + `study_space_documents` + `study_space_goals` | 1:1 (relaciones conservadas) | lógica profunda F10 | migration + mgmt |
| `TareaEvento` | `Task` (subject opcional, room, document_id, hora de fin sola) | 1:1 | F4.1 | schedule |
| autocreación Espacio al crear examen | `CalendarService.create_task` (idempotente) | reimplementado | F4.1 | schedule |
| `HorarioClase` + `fechas_sesiones_horario` | `schedule_series` (+stable_id, notes) + `domain/schedule.py` | 1:1 | F4.1 | schedule |
| `detectar_conflictos` | `domain/conflicts.detect` (reuso) | reuso | F4.1 | conflicts |
| `ics.py` / `importar_ics.py` | `infrastructure/ics.py` (export determinista + parser acotado) + `CalendarService.ics_preview/ics_apply` (revisión humana) | reimplementado | F4.1 | ICS tests |
| `Hito` | `Milestone` | 1:1 | F4.1 | mgmt |
| `NotaRapida` | `QuickNote` | 1:1 | F4.1 | mgmt |
| `ConfiguracionApp` (objetivo_media, tema, avisos, widgets) | `app_settings` (clave/valor) | 1:1 | UI F15 | migration |
| `RecursoExterno` (Wuolah/Studocu/…) | `ExternalResource` (URL validada, proveedor derivado, provenance; **sin fetch**) | 1:1 | F4.1 | security (SSRF) |
| `guia_docente.py` | `documents/syllabus.py` (heurística pura) + `KnowledgeService.analyze_syllabus` sobre AST F3/F3.1 con provenance | reimplementado; confirmación humana antes de escribir | F4.1 | test_f4_knowledge |
| `cargar_guias_docentes*.py` | datos GREELEC → fuera del código; la capacidad = `KnowledgeService.apply_syllabus` | datos llegan vía migración de la BD | — | knowledge |
| `cargar_studocu.py` / `cargar_wuolah.py` | `CourseMaterialService.add_external_resource` (URL validada, sin red) | datos vía migración | — | security |
| `fix_ciaf`, `limpiar_zips_codigo`, `reorganizar_apr_ped`, `import_apuntes` | capacidades: mover documento de asignatura/grupo (`CourseMaterialService.move`), sin borrado físico | no se portan (destructivos / rutas personales) | — | documentado |
| `Concepto` (SRS 0/3/18) | `study_concepts` (datos conservados) | 1:1 | lógica SRS F11 | migration |
| `SesionEstudio` / `DiaActividad` / racha | `study_sessions` / `activity_days` | 1:1 | temporizador/rachas F10 | migration |
| `Marcador` / `AnotacionPdf` | `legacy_payloads` (JSON verbatim, `deferred_to=F14`) | conservado | F14 | migration |
| `AvisoDescartado` / notificaciones | `legacy_payloads` (`F12`) | conservado | F12 | migration |
| `BusquedaFavorito/Reciente` | `legacy_payloads` (`F4.2`) | conservado | F4.2 | migration |
| `busqueda.py` | `UnifiedSearchService` (FTS `resources_fts` + entidades) | reuso FTS | F4.1 | search |
| `backup.py` (ZIP slip/bomb + validación SQLite) | `BackupService.export_zip/verify_zip` | reimplementado sobre F2 | F4.1 | backup |
| `auth.py` (lock-key, CSRF) | **no heredado** (app local PySide6; `AppLock` existente) | — | ADR-0024 | security |
| `errors.ApiError` | D2 `AcademicCoreError` + `AC-ACD-*` | reimplementado | F4.1 | D2 tests |
| templates/static/escritorio | UI PySide6 F15 | fuera de F4.1 | F15 | — |

## 3. Riesgos de diseño aceptados

- Profesores homónimos en asignaturas distintas se fusionan en una identidad
  (misma persona en la práctica); contacto por vínculo se conserva en `subject_staff`.
- `Task` sin asignatura: permitido (`subject_id=""`) para no perder eventos globales.
- Archivos rechazados por F2 (zip, exe…) se guardan como bytes opacos en CAS
  (`kind=file`, `extraction_status=deferred`); nunca se abren, extraen ni ejecutan.
