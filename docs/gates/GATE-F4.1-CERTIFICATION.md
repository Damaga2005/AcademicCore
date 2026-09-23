# GATE-F4.1-CERTIFICATION — Gestion-Academica integrada en AcademicCore

Fecha: 2026-09-23 · Rama `claude/new-session-wn0twl` · Base `31ad044`

## Decisión

```text
F4.1 NOT CERTIFIED
```

La implementación F4.1 está completa y verificada sobre el esquema real y la
BD de referencia generada por el propio código de Gestion, pero **dos
criterios no están demostrados**:

1. **Migración de los datos reales del usuario.** `academico.db` y
   `documentos/` de Gestion no están en ningún repositorio (`.gitignore`). No
   se han podido contar ni migrar los ~676 documentos, 185 grupos, ~7400
   páginas, 9 clases, 15 tareas, 7 espacios ni los 4 componentes añadidos a
   mano (168 vs 164). Falta: ejecutar el runbook
   (`docs/migration/GESTION-F4.1-MIGRATION.md`) → dry-run, comparar
   `counts` con esas cifras, apply con snapshot, `validation_failures == []`.
2. **«F3/F3.1 verdes».** `tests/test_f3_golden.py::TestGolden::test_html_corpus`
   (`html_cp1252`, digest distinto) falla **también en el baseline limpio
   `31ad044`** en este entorno (bs4 4.x / lxml 6.x instalados aquí): es
   preexistente y ajeno a F4.1, pero el criterio no se cumple hasta
   resolverlo o reproducir el entorno pineado (`requirements-lock.txt`).

## Regresión (suite completa `-m "not slow"`, comparada test a test por JUnit)

| Árbol | Resultado |
|---|---|
| Baseline `31ad044` (worktree limpio) | 1 failed, 3423 passed, 134 skipped, 1 deselected (20:35) |
| Final `418ec1d` | 2 failed, 4385 passed, 134 skipped, 1 deselected (21:21) |
| Tras corregir `test_migration` (este commit) | la 2.ª falla desaparece (ver abajo) |

- Tests nuevos F4.1: 963 (todos pasan; también con `PYTHONHASHSEED` 0 y 2024).
- Regresiones F4.1: 1 → `test_migration::test_real_migration_files_split_cleanly`
  fijaba `len(_MIGRATIONS) == 11`; la 012 se divide correctamente → expectativa
  actualizada a 12 (igual que `test_persistence`). **0 regresiones funcionales.**
- Skips = backends externos ausentes (ngspice, reportlab, Stirling), idénticos.

## Criterios de aceptación

| Criterio | Estado | Evidencia |
|---|---|---|
| domain sin Flask/SQLAlchemy/sqlite/Qt | ✅ | `test_architecture.py` + `test_f4_security::test_f41_domain_is_pure` |
| application sin UI, UI vía fachada | ✅ | `AcademicApp` (career/evaluation/material/calendar/plans/knowledge/unified_search/migration) |
| Estados CURSANDO/APROBADA/SUSPENDIDA/NO_CURSANDO, Home/Carrera sin duplicar | ✅ | `test_f4_domain`, `test_f4_mgmt` |
| Evaluación Decimal + equivalencia golden | ✅ | 400 casos del código real de Gestion |
| Documentos CAS/SHA-256/provenance/FTS/Course↔Resource | ✅ | `test_f4_documents`, `test_f4_migration_dryrun` |
| Schedule: horarios, conflictos, tareas, ICS | ✅ | `test_f4_schedule` |
| Migración dry-run/idempotente/snapshot/reporte reproducible | ✅ (referencia + sintético) | `test_f4_migration_dryrun`, runbook §Evidencia |
| 0 pérdidas demostradas | ✅ referencia / ❌ datos reales | ver Decisión 1 |
| 0 eval/exec/pickle/shell=True, límites, SSRF, D2 | ✅ | `test_f4_security` |
| Determinismo | ✅ | mismo digest entre targets y `PYTHONHASHSEED` 0/11/2024/random |
| F3/F3.1 verdes | ❌ preexistente | ver Decisión 2 |

## Otros hallazgos corregidos

- `application/search.py::norm` llamaba a `str.iscombining()` (inexistente):
  toda búsqueda no vacía de `SimpleSearchService` fallaba (defecto previo).
- `FtsResourceIndexer.search` podía perder hits filtrados (pre-fetch `limit*3`)
  y calculaba snippets de más; filtros en SQL: p95 305 → 109 ms.
- `BackupService.backup` copiaba el fichero con `shutil` (inseguro con WAL):
  ahora API de backup online de SQLite.

## Riesgos residuales

- Profesores homónimos se fusionan en una identidad (contacto por vínculo conservado).
- Guías en Markdown pierden saltos de línea blandos del parser F3 (PDF correcto).
- Commits M3–M7 aterrizaron juntos: la validación post-migración usa los servicios.
