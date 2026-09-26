# GATE-F11-CERTIFICATION — F11 Aprendizaje Adaptativo

> **FASE:** F11 — motor adaptista determinista sobre mastery F10.
> **BASELINE:** `main @ 6605242` (F10 CERTIFICADA); árbol limpio al inicio
> (salvo `.claude/` local sin trackear, config del agente, intacta).
> **Rama:** `main`, sin líneas paralelas.
> **Implementación:** `c1da8dc`
> `feat(f11): adaptive engine determinista (LLM=OFF) sobre mastery F10`.

## 1. Baseline pre-F11 (2026-09-26, local win, py 3.14.6)

Subset relevante (F10/F9/D7/D6/D5/arquitectura/migración):

```powershell
$env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen'
python -m pytest tests/test_f10_mastery.py tests/test_f9_correction.py `
  tests/test_d7_ingestion.py tests/test_d6_question_bank.py `
  tests/test_d5_contracts.py tests/test_d4_pipeline.py `
  tests/test_architecture.py tests/test_migration.py -q
```

- Resultado: **96 passed**, 0 failed.
- D5, D6, D7, F9 y F10 verdes antes de empezar (requisito §2 del prompt F11).

## 2. Inspección obligatoria (§1 del prompt F11)

- **F10:** `ConceptState.probability()` (P=α/(α+β)), `states_of(student,
  concept)`, `observations_of(student)` (historial: item_id=question_id,
  concept_ref, subject_id, alpha/beta deltas), `MasteryConfig`
  (f10-beta/1). F11 consume exactamente eso; no hay segundo modelo.
- **F9:** tipos D6, difficulty (en canonical_json), snapshots con
  question_digest/content_version. F11 selecciona; F9 sigue siendo la
  autoridad de corrección.
- **D7:** jerarquía real subject→topic→concept; prerequisitos
  **solo subject-level** (`prerequisites_of`, BFS cycle check). No
  existe prerequisito por concept/topic → no inventado.
- **D6:** banco con `concepts[]`, difficulty, qtype, versionado.

## 3. Implementación F11 (`c1da8dc`, +1107/−3, 9 ficheros)

| Cambio | Alcance |
|---|---|
| `domain/adaptive.py` (nuevo, puro) | `AdaptiveConfig` (engine `f11-adaptive/1`, config v1, pesos 60/20/15/5, umbrales 0.40/0.70, max_per_concept 2, exclude_done), `AdaptiveContext` (subject/topic/concept/count/types/difficulty range), `Candidate`, `ScoredCandidate`, `AdaptivePlan` (rationale cerrado + `NO_ELIGIBLE_EXERCISES`/`PREREQUISITE_UNMET`), `target_difficulty`, `difficulty_fit`, `score_candidate`, `rank_candidates` (score DESC, question_id ASC, version ASC), `build_route` (cap por concepto), `plan_digest` (`f11-adaptive-plan/1`), `bank_digest_of` |
| `application/adaptive.py` (nuevo) | `AdaptiveService.build_plan` (eligible→filter→score→rank→route→persist), `_load_questions` (scope por subject vía `questions_of_subject` con `json_each`), `_state_p` (NaN→`AC-ACD-004`), `_prerequisites_ok` (subject-level), `_persist` (plan_id = plan_digest) |
| `migrations/019_f11_adaptive.sql` (nueva, aditiva) + `database._MIGRATIONS` | `adaptive_plans` (plan_id PK determinista, snapshots JSON, índice por student). Ninguna tabla certificada tocada |
| `infrastructure/academic_store` (aditivo) | `QBankRepository.all_questions` + `questions_of_subject` (json_each), `MasteryRepository.save_plan/get_plan/plans_of` (INSERT OR REPLACE idempotente) |
| `tests/test_f11_adaptive.py` (nuevo, 22 tests) | Elegibilidad (válido/inválido, filtros subject/tipo/difficulty/concept, banco vacío→estructurado), prioridad mastery (low/high, UNMAPPED), ranking (determinista, tie-break, difficulty fit), historial (exclusión, cap por concepto, all-done), route (límite, orden, rationale), reproducibilidad (mismo input→mismo plan, config→distinto), idempotencia (persist sin duplicados), prerequisitos (unmet bloquea, satisfied tras práctica), edge cases (config inválida, estado NaN), LLM=OFF (plan completo, sin imports IA), seguridad AST |
| `tests/test_migration.py`, `tests/test_persistence.py` | Pins `18 → 19` (únicos toques a tests certificados; la 019 los exige) |
| `docs/architecture/F11-ADAPTIVE.md` (nuevo) | Engine, elegibilidad, mastery, difficulty, historial, score, desempate, route, versionado, idempotencia, persistencia, determinismo/seguridad, contrato F12, límites |

Comportamiento certificado cambiado: **ninguno** (solo métodos nuevos
en repos existentes + pins).

## 4. Evidencia fresca (local)

- Nuevos: `test_f11_adaptive.py` = **22 passed** (bugs reales cazados en
  desarrollo: clave `digest` vs `question_digest`, Observation en módulo
  correcto, SQL 11→12 placeholders, NaN finito, rebuild de estados en
  tests, tests sin tmp_path — todos con fix en producto o test según
  correspondiera).
- Seguridad AST: sin `eval/exec/compile/__import__/shell=True`; imports
  ⊆ `{__future__, decimal, hashlib, json, academic_core}`; sin imports
  de IA (test); `correct_answer` no referenciado.

## 5. Regresión amplia (2026-09-26, local win, py 3.14.6)

Set §1 + `f9b/c/d` + `f4_security`:

- Resultado: **217 passed, 1 skipped** (skip = `test_document_symlink_
  escape_refused`: el SO niega symlinks; excepción ambiental §14).
- Multiseed (`PYTHONHASHSEED=0/1/42`):
  `f11 + migration + persistence` → **36 passed × 3**.

## 6. Criterios (§31 del prompt F11)

- [x] Adaptive Engine implementado (dominio puro + servicio)
- [x] consume el Student Model real de F10 (states + observations)
- [x] utiliza Knowledge Core real de D7 (subjects, prerequisitos)
- [x] utiliza Question Bank real de D6 (preguntas vía store D7)
- [x] selección determinista (score + rank + desempate estables)
- [x] elegibilidad determinista (filtros contractuales; no elegible nunca aparece)
- [x] ranking determinista (fórmula versionada 60/20/15/5)
- [x] desempate estable (score DESC, question_id ASC, version ASC)
- [x] prioridad basada en mastery (1−P, LOW_MASTERY < 0.40)
- [x] difficulty usada solo si existe contractualmente (D6; fit 1/0.5/0)
- [x] prerequisitos respetados (subject-level, único tipo en D7)
- [x] historial tratado explícitamente (exclude_done, RECENT_ERROR)
- [x] repetición controlada (exclude_done + max_per_concept)
- [x] diversidad controlada (cap por concepto en route)
- [x] Learning Route implementada (AdaptivePlan + rationale cerrado)
- [x] rationale estructurado (códigos reales, nada ficticio)
- [x] snapshot/versionado del plan (plan_digest + bank_digest + mastery_snapshot)
- [x] reproducibilidad (mismo input → mismo plan, test cross-fixture)
- [x] idempotencia (plan_id = plan_digest; INSERT OR REPLACE, test)
- [x] `LLM=OFF` produce planes funcionales (test completo)
- [x] ningún LLM es autoridad (sin imports de IA; test)
- [x] persistencia correcta (019, round-trip, sin duplicados)
- [x] integridad validada (config/estado/corruptos rechazados)
- [x] seguridad validada (AST + allowlist)
- [x] tests F11 verdes (22/22)
- [x] F10/F9/D7/D6/D5 verdes (§5: 217 passed / 1 skip ambiental)
- [ ] CI real verde — run pendiente tras push (ver §7)
- [x] documentación creada (`F11-ADAPTIVE.md` + este gate)
- [x] gate creado (este fichero)
- [ ] roadmap actualizado a `F11 CERTIFICADA` / `F12 SIGUIENTE` **solo
      después del CI verde** (prohibido adelantar; ver §7)
- [x] no se implementó F12/F13/F16 (límites §15 del doc)

## 7. Certificación pendiente

F11 queda **IMPLEMENTADA, NO CERTIFICADA** hasta CI real verde sobre el
commit de certificación. Secuencia de cierre obligatoria:

1. push `main` (dispara CI D4: 4 celdas + package);
2. run verde 4/4 + package → completar §6/§7 con el run id;
3. solo entonces: roadmap `F11 → CERTIFICADA`, `F12 → SIGUIENTE`,
   CHANGELOG de certificación y commit `docs(f11): certificar …`.

**Prohibido marcar F11 CERTIFICADA con evidencia solo-local**
(roadmap §5.5.4 + prompt F11 §31: `CI real verde`).
