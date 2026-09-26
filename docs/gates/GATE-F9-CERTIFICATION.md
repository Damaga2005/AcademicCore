# GATE-F9-CERTIFICATION — F9 Assessment y Evaluación Formal

> **FASE:** F9 — corrección determinista y evidencia sobre D6/D7.
> **BASELINE:** `main @ 952f55f` (D7 CERTIFICADA); árbol limpio al inicio
> (salvo `.claude/` local sin trackear, config del agente, intacta).
> **Rama:** `main`, sin líneas paralelas.
> **Implementación:** `acec7ed`
> `feat(f9): assessment y evaluacion formal sobre D6/D7`.

## 1. Baseline pre-F9 (2026-09-26, local win, py 3.14.6)

Subset relevante (D7/D6/D5/arquitectura/migración/F9-B/C):

```powershell
$env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen'
python -m pytest tests/test_d7_ingestion.py tests/test_d6_question_bank.py `
  tests/test_d5_contracts.py tests/test_d4_pipeline.py `
  tests/test_architecture.py tests/test_migration.py `
  tests/test_f9b_domain_assessment.py tests/test_f9c_assessment_orchestration.py -q
```

- Resultado: **98 passed**, 0 failed.
- D5, D6 y D7 verdes antes de empezar (requisito §2 del prompt F9).

## 2. Inspección obligatoria (§1 del prompt F9)

Dos lecturas paralelas del `main` real + verificación directa:

- **Stack F9-B/C existente:** `Assessment/Item/Session/Response/Result/
  GradingPolicy`, máquina `NOT_STARTED→…`, orquestación
  create/start/respond/submit/expire/cancel, repo 011 con triggers de
  inmutabilidad. **Sin correction engine** (el llamador aporta
  `(is_correct, ratio)` a mano), **sin snapshots**, **sin evidence**.
- **Motores reutilizables:** `units.parse_quantity/convert_to`
  (exacto, sin tolerancias); `symbolic.{expr,normal,numeric}`
  (`equivalent` + acuerdo `Decimal` + l ímites 256/48);
  `execution.symbolic.explain_*` disponible; D6 `answer_spec` exacto;
  D7 `get_question` (JSON canónico). Veredicto por tipo fijado antes de
  implementar (mcq/tf directos; numeric/symbolic con motor; short/
  structured/circuit honestos según contrato).

## 3. Implementación F9 (`acec7ed`, +1478/−77, 9 ficheros)

| Cambio | Alcance |
|---|---|
| `domain/correction.py` (nuevo, puro, motor `f9-correct/1`) | `correct_answer` para los 7 tipos D6: conjuntos/bool exactos; numeric `Decimal`+unidades+tolerancia/precisión (cifras significativas); symbolic con prueba `equivalent` o acuerdo exacto etiquetado; short/structured/circuit con `needs_review` donde D6 no da criterio; malformados → `AC-DOM-001`; `Verdict` con `REASONS` cerradas |
| `application/correction.py` (nuevo) | `CorrectionService`: cupo `attempts_allowed` (cancel no consume, número libre mínimo), `prepare` (snapshots congelados, idempotente), `submit_with_correction` (1 tx: submit→correct→result+evidence), `build_evidence` (DTO F10 con `verified`), errores `AC-ACD-002/003/004` + `AC-INT-001` |
| `migrations/017_f9_attempt_evidence.sql` (nueva, aditiva) + `database._MIGRATIONS` | `assessment_item_snapshots` (+`provenance`) y `assessment_evidence` + triggers de inmutabilidad. Ninguna tabla certificada tocada |
| `infrastructure/assessment.py` (refactor mínimo + aditivo) | `save_session` extraído a `_save_session_tx` (misma semántica) + `save_session_cx`, `unit_of_work`, `sessions_of`, batches de snapshots/evidence con `cx` |
| `tests/test_f9_correction.py` (nuevo, 19 tests) | Lifecycle, cupo/cancel, doble submit, prepare (ok/desconocido/sin-preparar), historia congelada tras update del banco, mcq/tf, bordes numeric (tol exacta, conversión, dimensión), precisión, symbolic (prueba/mismatch/símbolos), inválidos, short+pending, structured/circuit, omitidas, evidence+provenance+verified, tamper (resiliente), rollback inyectado, determinismo, seguridad AST + latex/respuesta maliciosa inerte |
| `tests/test_migration.py`, `tests/test_persistence.py` | Pins `16 → 17` (únicos toques a tests certificados; la 017 los exige) |
| `docs/architecture/F9-ASSESSMENT.md` (nuevo) | Modelo, snapshots/versionado, payloads, corrección por tipo, scoring, evidence, ExecutionTrace, persistencia, tx, determinismo/seguridad, errores, contrato F10, límites |

Comportamiento certificado cambiado: **ninguno** (`save_session` idéntico,
verificado por F9-D 49 passed; `submit_assessment` manual intacto).
Decisiones: sin scoring inventado (binarios + review; ratio reservado sin
productor); sin simulación como corrección (documentada futura);
`unit` ausente con esperada presente = asumida (documentado).

## 4. Evidencia fresca (local)

- Nuevos: `test_f9_correction.py` = **19 passed** (7 bugs reales cazados
  en desarrollo — IDs, cupo-cancel, firmas keyword-only, snapshot sin
  provenance, expectativas parciales, `verified` resiliente — con fix en
  producto salvo 3 expectativas de test).
- Regresión: F9(+correction) + F9-B/C/D + D7 + D6 + D5 + arquitectura +
  migraciones + persistencia + provenance + ingest + F4-seguridad +
  F13-ext → **267 passed, 1 skipped** (skip = symlink ambiental §14).
- Multiseed (`PYTHONHASHSEED=0/1/42`):
  `f9_correction + migration + persistence` → **33 passed × 3**.
- Seguridad AST: sin `eval/exec/compile/__import__/shell=True` en rutas
  F9; imports nuevos ⊆ `{__future__, dataclasses, datetime, decimal,
  json, re, academic_core}`.

## 5. Criterios (§23 del prompt F9)

- [x] Assessment y Attempt con contratos claros (reutilizados + servicio F9)
- [x] respuestas conservadas como datos (JSON canónico, sin overwrite)
- [x] corrección determinista (`f9-correct/1`, 7 tipos D6)
- [x] solo tipos contratados por D6 (ninguno inventado)
- [x] numeric con precisión/unidades/tolerancias del contrato
- [x] symbolic con motores existentes (`symbolic.*`, `parse_unit`)
- [x] engineering vía solvers/unidades certificados (sin duplicar F8)
- [x] contenido nunca ejecutado (AST + pruebas maliciosas inertes)
- [x] scoring determinista (`GradingPolicy` intacta)
- [x] evidence estructurada + provenance (filas + DTO F10)
- [x] resultados vinculados a versiones/digests (snapshots + `verified`)
- [x] intentos reproducibles y transaccionales (1 tx + rollback verificado)
- [x] tests F9, D5, D6 y D7 verdes (§4)
- [x] CI real verde — run `36244520858` (`ef1976c`): intento 1 con 1 flake
  (`test_perf_academic_scale` 22.9s vs presupuesto 20s en win-3.13;
  clase documentada en `TEST-SUITE.md` §8, umbral intacto, cero código F9
  en ese camino); tras `rerun --failed`, intento 2: **4/4 celdas success
  + package success** (ver §6)
- [x] documentación creada (`F9-ASSESSMENT.md` + este gate)
- [x] gate creado (este fichero)
- [x] roadmap actualizado a `F9 CERTIFICADA` / `F10 SIGUIENTE` tras el CI verde

## 6. Certificación

**F9 CERTIFICADA.** Todos los criterios §23 demostrados con evidencia
fresca del proveedor (run `36244520858`, commit `ef1976c`). Roadmap:
`F9 → CERTIFICADA`, `F10 → SIGUIENTE`.
