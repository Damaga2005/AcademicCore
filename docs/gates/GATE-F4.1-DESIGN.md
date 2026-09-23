# GATE-F4.1-DESIGN — Integración de Gestion-Academica en AcademicCore

> Fase F4.1 (diseño de delta + plan de implementación). Base: `31ad044`
> (GATE-F4-DESIGN, F4.0). Fuente auditada: `Damaga2005/Gestion-Academica@187a614`.
> Rama: `claude/new-session-wn0twl`.

## 1. Reconocimiento (protocolo A)

| Punto | Localización en Gestion | Resultado |
|---|---|---|
| Dashboard | `routes/vistas.py::dashboard`, `static/js/dashboard.js`, `routes/asignaturas.py::{media_curso,media_por_cuatrimestre,objetivo_media}` | indicadores: progreso ECTS (240 fijo en JS), cursando, entregas/cuenta atrás, continuar leyendo, racha, medias, objetivo, semana, repaso hoy, hitos |
| Modelo asignaturas | `models.py::Asignatura` (+ `resolver_asignatura`) | ActiveRecord; siglas únicas; ECTS float |
| Estados | `ESTADOS_ASIGNATURA` (5) + `cambiar_estado_asignatura` | manual, sin transición forzada |
| Documentos | `Documento/GrupoDocumento/Apartado/PaginaTexto`, `routes/documentos.py` | FS+BD, progreso de lectura, índice de páginas |
| Selección para estudio | `EspacioEstudio/EspacioEstudioDocumento/ObjetivoEspacio` | 1:1 con examen; referencias, no copias |
| Calendario/horario | `TareaEvento`, `HorarioClase`, `fechas_sesiones_horario`, `routes/conflictos.py`, `routes/{ics,importar_ics}.py` | series recurrentes, conflictos avisan |
| `cargar_guias_docentes{,_2}` | datos GREELEC (15+38 asignaturas) + borrado/recreación | capacidad = importar guía con confirmación |
| `cargar_studocu` / `cargar_wuolah` | URLs por id de asignatura | capacidad = recurso externo URL |
| `fix_*/limpiar_*/reorganizar_*/import_apuntes` | reorganización destructiva de FS | no se portan (capacidad: mover relación) |
| Migraciones | 23 Alembic (`c73474549a28` … `e5a7c9b1d3f4`) | cadena usada como allow-list |
| Datos reales | `academico.db` y `documentos/` en `.gitignore` | **no disponibles**; se generó BD de referencia ejecutando el propio código de Gestion |

Los números del F4.0 se reverificaron: 54 asignaturas / 53 siglas / 61
profesores / 65 esquemas / 81 recursos **reproducidos**; 168 componentes → 164
reproducibles (+4 manuales); documentos/páginas/tareas **no verificables** aquí.

## 2. Mapa de delta (protocolo B)

`docs/migration/GESTION-F4.1-DELTA-MAP.md` (capacidad → destino → estrategia →
fase futura → tests), revisado y coherente antes de implementar.

## 3. Decisiones

ADR-0017 (modelo/estados), ADR-0018 (repos + transacción compartida),
ADR-0019 (documentos en contexto de asignatura, CAS), ADR-0020 (evaluación
Decimal), ADR-0021 (guía docente y conocimiento sobre F3/F3.1), ADR-0022
(ICS), ADR-0023 (no se hereda la autenticación), ADR-0024 (protocolo de
migración).

## 4. Plan M1–M9 y fronteras

| M | Contenido | Tests |
|---|---|---|
| M1 | estados, partición Home/Carrera, entidades F4.1, ids | `test_f4_domain.py` |
| M2 | esquemas/bloques/componentes/nota mínima + golden Gestion real | `test_f4_evaluation.py` |
| M3 | migración 012 aditiva, repos, lector legacy, migración dry-run/snapshot/apply/validate | `test_f4_migration_dryrun.py` |
| M4 | documentos↔asignatura, CAS, provenance, FTS, progreso, selección | `test_f4_documents.py` |
| M5 | tareas, espacios de examen, series, conflictos, ICS | `test_f4_schedule.py` |
| M6 | guía docente (golden Gestion real) + reuso F3.1 | `test_f4_knowledge.py` |
| M7 | hitos/objetivos/notas/ajustes, búsqueda unificada, backup ZIP, CSV | `test_f4_mgmt.py`, `test_f4_documents.py` |
| M8 | D2 `AC-ACD/MIG/ICS/SEC`, AST de seguridad/arquitectura | `test_f4_security.py` |
| M9 | migración golden, regresión completa, certificación | `GATE-F4.1-CERTIFICATION.md` |

Fuera de F4.1 (conservado, no eliminado): F10 sesiones/rachas/temporizador,
F11 SRS, F12 notificaciones/IA, F13 sync, F14 anotaciones PDF, F15 UI,
F4.2 favoritos/recientes/notificaciones.
