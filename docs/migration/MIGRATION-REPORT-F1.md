# Migration report F1 (Gestion-Academica → Academic Core)

Method per feature: locate → document → test → implement → equivalence →
decouple. Flask UI never migrated (behavior + domain only).

| Funcionalidad origen | Destino F1 | Estado |
|---|---|---|
| Años/cuatrimestres/estados | University/Degree/AcademicYear/Term genérico | ✅ migrado (sin hardcodear 4/8 ni UPC) |
| Asignaturas + siglas + catálogo optativas | Subject + AcademicService | ✅ núcleo migrado |
| Profesores + edición inline | Professor + SubjectStaff | ✅ migrado (email sin envío acoplado) |
| Componentes/esquemas/bloques/nota final + "¿qué nota necesito?" base | domain/grading + GradingService | ✅ con divergencia doc (ADR-0011, CONFLICTS §B) |
| Horarios recurrentes + sesiones al vuelo | domain/schedule + ScheduleService | ✅ idéntico + extensión 1..7 |
| Conflictos tarea↔tarea/tarea↔clase | domain/conflicts | ✅ paridad warn-only |
| Tareas/eventos + tipos + prioridades | Task + Deadline | ✅ migrado |
| Espacios estudio (refs, autocreación) + modo examen (vista) | StudySpace + StudySession | ✅ dominio; vista en Fase 4 |
| Repaso espaciado 0/3/18 + racha + hitos | SPACED_INTERVALS + streak + Notification | ✅ dominio; delivery fuera |
| Notas al vuelo vs por asignatura | Annotation/Bookmark genéricos | ✅ sin acople a visor |
| Buscador global Ctrl+K + NFKD | SearchService (substring) | 🟡 interfaz + base; FTS5 en Fase 2 |
| Subida docs + magic-bytes | ResourceReference (puntero) | 🟡 puntero; bytes en Fase 2 |
| Backup auto + zip anti-slip/bomb | BackupService (snapshot + manifest) | 🟡 base; límites en Fase 4+ |
| Lock + CSRF propio | AppLock (salt+SHA-256, sin secretos en SQLite) | 🟡 base local; sin auth web por diseño |
| Dashboard widgets | UI validación (listas + verdict) | 🟡 validación; rediseño en Fase 4 |
| Scrapers/guías/APARTADO legacy/pdf.js | — | ⏸️ deprecados/diferidos (CONFLICTS §F) |

Nada migrado vive solo en la UI: cada fila ✅/🟡 tiene entidad + servicio +
persistencia + test.
