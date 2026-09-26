# GATE-D7-CERTIFICATION — D7 Ingesta estructurada → Knowledge Core

> **FASE:** D7 — puente determinista D6 → Knowledge Core.
> **BASELINE:** `main @ 72ff6f2` (D6 CERTIFICADA); árbol limpio al inicio
> (salvo `.claude/` local sin trackear, config del agente, intacta).
> **Rama:** `main`, sin líneas paralelas.
> **Implementación:** `18d3815`
> `feat(d7): ingesta estructurada D6 -> Knowledge Core`.

## 1. Baseline pre-D7 (2026-09-26, local win, py 3.14.6)

Subset relevante:

```powershell
$env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen'
python -m pytest tests/test_d6_question_bank.py tests/test_d5_contracts.py `
  tests/test_d4_pipeline.py tests/test_architecture.py tests/test_migration.py `
  tests/test_persistence.py tests/test_provenance.py tests/test_ingest.py `
  tests/test_f4_security.py -q
```

- Resultado: **todos verdes, 1 skip** (`test_document_symlink_escape_refused`:
  el SO niega symlinks; excepción ambiental §14).
- D6 y Knowledge Core verificados antes de empezar (requisito §2 D7).

## 2. Inspección obligatoria (§1 del prompt D7)

Dos lecturas paralelas del `main` real + verificación directa:

- **Knowledge Core:** `StudyConcept` (`planning.py:78`, `concept:<s>:c:NNNNN`,
  tabla `study_concepts`, `PersonalRepository.add_concept` con `cx`);
  `Formula` Phase-0 (`academic.py:72`, sin tabla/repo; único uso vivo:
  `assessment.item_from_formula` de F9); recursos F2 (CAS+`content_hash`);
  `CourseDocument/DocumentGroup/ExternalResource`; F3.1 efímeros;
  electrónica in-memory. **Sin banco de preguntas ni store de fórmulas.**
- **Ingesta/dry-run/tx:** `CourseMaterialService` (DTOs, `AC-ACD-*`);
  migración F4.1 (`gestion_migration.py`: PLAN determinista + `dry-run`
  sin escrituras + `_write` en UNA tx + `validate`); `_Base._tx(cx)`
  componible + `unit_of_work`; dedup `find_by_hash` + `INSERT OR
  IGNORE/REPLACE`; `TargetWriter` + `id_counters`.

## 3. Implementación D7 (`18d3815`, +1373/−5, 10 ficheros)

| Cambio | Alcance |
|---|---|
| `migrations/016_qbank_ingest.sql` (nueva, aditiva) + `database._MIGRATIONS` | `qbank_banks`, `qbank_questions` (+índice), `formulas`. Ninguna tabla certificada tocada |
| `infrastructure/academic_store.QBankRepository` (nuevo, `cx` componible) + export | bank get/save_new/save_update, question digests/get/save/prune, `all_formula_heads`/get/save |
| `domain/ingestion.py` (nuevo, puro) | `plan_bank`: reuse/create/rechazo determinista, ambigüedad concepto+formula → error, idempotencia por digest, versiones (conflict/stale), `plan_digest` sin timestamps, `question_digest` (tag `d6-question/1`, semántica documentada ≠ digest de banco) |
| `application/bank_ingest.py` (nuevo) | `plan/dry_run/ingest`: snapshots → plan → UNA tx → verify; `AC-ACD-002/003/004`, `AC-INT-001` en divergencia; `now_ms` inyectable |
| `tests/test_d7_ingestion.py` (nuevo, 18 tests) | Los 21 puntos del §17 (tipos/answer agrupados, create+reuse en 1 test): mínimo, mapping, digest, create, idempotencia (cero escrituras), update (+add+remove), reuse, unresolved `AC-ACD-002` + cero writes, ambigüedad `AC-ACD-003`, provenance E2E, no-overwrite, fórmula modificada = conflicto, rollback inyectado, dry-run, determinismo (plan + estado en 2 DBs), inválidos/versión, subject desconocido, seguridad AST + latex inerte |
| `tests/test_migration.py:338`, `tests/test_persistence.py:73` | Pins `15 → 16` (únicos toques a tests certificados; la 016 los exige) |
| `docs/architecture/D7-INGESTION.md` (nuevo) | Entrada, mapping, identidad/dedup, idempotencia, versiones, digests, provenance, tx, determinismo, seguridad, 016 justificada, errores, contrato F9, límites |

Código certificado tocado: **nada salvo los 2 pins** (justificados aquí).
Decisiones: conceptos en `study_concepts` (reuso; creación solo con
catálogo explícito + subject existente + bump de `id_counters.concept`);
fórmulas en tabla 016 para la entidad `academic.Formula` (existía sin
store; la consume F9); refs `section/document/topic` carried opacos;
`answer_spec` almacenado verbatim, jamás interpretado.

## 4. Evidencia fresca (local)

- Nuevos: `test_d7_ingestion.py` = **18 passed** (4 bugs reales cazados
  en desarrollo — slug-vs-ID, plan `unchanged` vacío, contrato de
  snapshots, subject sin prefijo — todos con fix en producto, no en tests,
  salvo el pin `%→A` heredado de D6).
- Regresión: set §1 + `f9b/c/d` + `f13ext_sync/service` →
  **todo verde salvo 1 pin** (`test_persistence` lista `[1..15]`,
  actualizada a `[1..16]`, re-verde). Tras el fix:
  `persistence + migration + d7 + d6` = **48 passed × 3 hash-seeds
  (0/1/42)**.
- Arquitectura: `test_domain_is_pure`, `test_domain_knows_no_backends`,
  `test_no_flask_or_web_stack_anywhere` verdes con los ficheros nuevos
  (imports ⊆ `{__future__, dataclasses, hashlib, json, re, time,
  academic_core}`; dominio además `identity/entities` vía `academic_core`).
- Seguridad AST: sin `eval/exec/compile/__import__/shell=True`, sin
  red/subprocess/pickle/os/pathlib/sqlite3 en rutas de ingestión.

## 5. Criterios (§23 del prompt D7)

- [x] D6 se valida antes de ingerirse (`parse_bank`; inválido → `AC-ACD-004`)
- [x] pipeline determinista (`validate → plan → apply → verify`)
- [x] mapping D6→Knowledge Core documentado (D7-INGESTION.md §3)
- [x] entidades reutilizadas (conceptos, subjects, counters, tx, digest D6)
- [x] sin duplicados por reingesta (digest banco + pregunta)
- [x] ingesta idempotente (`ingest(X);ingest(X)==ingest(X)`, cero writes)
- [x] versiones D6 respetadas (create/unchanged/update/conflict/stale)
- [x] digest D6 conservado verbatim (banco) + digest-pregunta documentado
- [x] provenance extremo a extremo (sello `d7-ingest/1`, estructurada)
- [x] referencias resueltas determinísticamente (reuse/create)
- [x] ambigüedades rechazadas (`AC-ACD-003`)
- [x] entradas inválidas rechazadas (`AC-ACD-002/003/004`)
- [x] persistencia atómica (1 tx; rollback verificado con fallo inyectado)
- [x] fallos sin estados parciales (cero filas tras rollback y rechazos)
- [x] dry-run (`plan` puro, cero escrituras por construcción)
- [x] contenido importado nunca ejecutado (AST + latex inerte)
- [x] tests D7 verdes (18/18 local)
- [x] regresión D5/D6 verde (§4)
- [x] CI real verde — run `36239628773` (`03579c0`): intento 1 con 1 flake
  (`test_perf_academic_scale` 21.47s vs presupuesto 20s en win-3.13;
  clase documentada en `TEST-SUITE.md` §8, umbral intacto, cero código D7
  en ese camino); tras `rerun --failed`, intento 2: **4/4 celdas success
  + package success** (ver §6)
- [x] documentación creada (`D7-INGESTION.md` + este gate)
- [x] gate creado (este fichero)
- [x] roadmap actualizado a `D7 CERTIFICADA` / `F9 SIGUIENTE` tras el CI verde

## 6. Certificación

**D7 CERTIFICADA.** Todos los criterios §23 demostrados con evidencia
fresca del proveedor (run `36239628773`, commit `03579c0`). Roadmap:
`D7 → CERTIFICADA`, `F9 → SIGUIENTE`.
