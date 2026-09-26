# GATE-F10-CERTIFICATION — F10 Mastery y Modelado del Estudiante

> **FASE:** F10 — modelo probabilístico del dominio desde evidencia F9.
> **BASELINE:** `main @ 8dbd961` (F9 CERTIFICADA); árbol limpio al inicio
> (salvo `.claude/` local sin trackear, config del agente, intacta).
> **Rama:** `main`, sin líneas paralelas.
> **Implementación:** `feat(f10): modelo beta-binomial de mastery sobre evidencia F9`.

## 1. Baseline pre-F10 (2026-09-26, local win, py 3.14.6)

Subset relevante (F9/D7/D6/D5/arquitectura/migración):

```powershell
$env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen'
python -m pytest tests/test_f9_correction.py tests/test_f9b_domain_assessment.py `
  tests/test_f9c_assessment_orchestration.py tests/test_d7_ingestion.py `
  tests/test_d6_question_bank.py tests/test_d5_contracts.py `
  tests/test_d4_pipeline.py tests/test_architecture.py tests/test_migration.py -q
```

- Resultado: **117 passed**, 0 failed.
- D5, D6, D7 y F9 verdes antes de empezar (requisito §2 del prompt F10).

## 2. Inspección obligatoria (§1 del prompt F10)

- **F9:** `AttemptEvidence`/`ItemEvidence` (question_id, qtype,
  content_version, question_digest, concepts, provenance, verified,
  is_correct, ratio, score, reason, engine). F10 consume exactamente eso.
- **D7:** jerarquía real `subject → topic → concept` (IDs estables),
  `study_concepts` (PersonalRepository), `topics_of` (AcademicRepository).
- **D6:** banco/preguntas con `concepts[]` y `knowledge_refs`.
- **Infraestructura:** `Database` 001..017, `_Base._tx(cx)` +
  `unit_of_work`, JSON canónico `_j`, errores D2, tests/CI D4/D5.

## 3. Implementación F10

| Cambio | Alcance |
|---|---|
| `domain/mastery.py` (nuevo, puro) | `MasteryConfig` (model `f10-beta/1`, config v1, prior Beta(1,1), weight_precision 1..12), `ConceptState` (alpha/beta Decimal, P=m/(m+n), varianza Beta), `Observation` (deltas + engine + question_digest), `observation_digest` (`f10-observation/1`), `apply_observation`, `fold_observations` (rebuild por concepto), `fold_deltas` (agregados topic/subject), `pool_states`, `split_weight` (reparto exacto), `state_digest` (`f10-state/1`), `AggregateView` |
| `application/mastery.py` (nuevo) | `MasteryService`: `apply_evidence` (validate→plan→1 tx→states; `no_update` para omitidas/sin-concepto; `AC-ACD-002` concepto desconocido; `AC-ACD-003` tamper), `get_mastery/get_topic_mastery/get_subject_mastery`, `rebuild` (fold en orden fijo) |
| `migrations/018_f10_mastery.sql` (nueva, aditiva) + `database._MIGRATIONS` | `mastery_states(student, level, ref, members_json…)` + `mastery_observations` (PK = idempotencia). Ninguna tabla certificada tocada |
| `infrastructure/academic_store.MasteryRepository` (nuevo, `cx` componible) + export | save_observation (`INSERT OR IGNORE` → bool), observations_of, save/get_state(s), delete_states |
| `application/correction.py` (extensión aditiva del DTO) | `ItemEvidence.topic_ref` (default `""`) + `build_evidence(session_id, assessment=None)` enriquece con `item.topic_id` (D7 real). Motor F9 intacto |
| `tests/test_f10_mastery.py` (nuevo, 14 tests) | Modelo (prior, correct/incorrect, límites, varianza, fold/pool/digests), evidencia (apply, split multi-concepto, unknown-concept sin writes), idempotencia (doble apply, doble-insert concurrente), rebuild==incremental, determinismo cross-fixture, jerarquía (concept/topic/subject), rollback inyectado, round-trip + estado corrupto NaN, seguridad AST + `correct_answer` no importado |
| `tests/test_migration.py`, `tests/test_persistence.py` | Pins `17 → 18` (únicos toques a tests certificados; la 018 los exige) |
| `docs/architecture/F10-MASTERY.md` (nuevo) | Modelo, evidencia, idempotencia, rebuild, versionado, agregaciones, provenance, invariantes, persistencia, tx, determinismo/seguridad, API, contrato F11, límites |

Comportamiento certificado cambiado: **ninguno** (solo campo aditivo con
default en el DTO F10 + parámetro opcional en `build_evidence`).

## 4. Evidencia fresca (local)

- Nuevos: `test_f10_mastery.py` = **14 passed** (bugs reales cazados en
  desarrollo: validación de refs de 4 partes, política `no_update` vs
  rechazo, frozen assessment, read-your-writes dentro de la tx, dicts
  normalizados incompletos, `fold_observations` vs agregados →
  `fold_deltas`, monkeypatch en la instancia correcta — todos con fix en
  producto o en el test según correspondiera).
- Regresión: F10 + F9(+correction) + F9-B/C/D + D7 + D6 + D5 + arquitectura +
  migraciones + persistencia + F4-seguridad → **verde** (ver §5).
- Multiseed (`PYTHONHASHSEED=0/1/42`):
  `f10 + migration + persistence` → **28 passed × 3**.
- Seguridad AST: sin `eval/exec/compile/__import__/shell=True`; imports
  nuevos ⊆ `{__future__, decimal, hashlib, json, academic_core}`;
  `correct_answer` jamás referenciado en F10 (test).

## 5. Regresión amplia (2026-09-26, local win, py 3.14.6)

Set §1 + `f9d_assessment_persistence` + `f4_security`:

- Resultado: **281 passed, 1 skipped** (skip = `test_document_symlink_
  escape_refused`: el SO niega symlinks; excepción ambiental §14).
- Multiseed (`PYTHONHASHSEED=0/1/42`):
  `f10 + migration + persistence` → **28 passed × 3**.

## 6. Criterios (§33 del prompt F10)

- [x] Student Model implementado
- [x] concept mastery (Beta por concepto)
- [x] tema/asignatura con jerarquía real D7 (topic_id del ítem, subject del concepto)
- [x] modelo probabilístico explícito y documentado (Beta-Binomial conjugado)
- [x] prior explícito (Beta(1,1), configurable, versionado)
- [x] actualización determinista (sumas conmutativas)
- [x] evidencia F9 consumida sin reinterpretarla (veredictos intactos)
- [x] mapping question→concept determinista (concepts + knowledge_refs; no_update si falta)
- [x] evidencia duplicada idempotente (PK + INSERT OR IGNORE, test concurrente)
- [x] rebuild reproducible (incremental == rebuild, test)
- [x] model_version y config_version explícitas
- [x] provenance conservada (obs_digest/state_digest, engine, question_digest)
- [x] invariantes matemáticos (0≤P≤1, NaN/Infinity rechazados)
- [x] persistencia correcta (018, round-trip)
- [x] transacciones correctas (1 tx, rollback verificado)
- [x] concurrencia tratada (doble-apply seguro)
- [x] tests F10 verdes (14/14)
- [x] D5/D6/D7/F9 verdes (§4-§5: 281 passed / 1 skip ambiental)
- [ ] CI real verde — run pendiente tras push (ver §7)
- [x] documentación creada (`F10-MASTERY.md` + este gate)
- [x] gate creado (este fichero)
- [ ] roadmap actualizado a `F10 CERTIFICADA` / `F11 SIGUIENTE` **solo
      después del CI verde** (prohibido adelantar; ver §7)
- [x] no se implementó F11/F12/F13/F16 (límites §16 del doc)

## 7. Certificación pendiente

F10 queda **IMPLEMENTADA, NO CERTIFICADA** hasta CI real verde sobre el
commit de certificación. Secuencia de cierre obligatoria:

1. push `main` (dispara CI D4: 4 celdas + package);
2. run verde 4/4 + package → completar §5/§6/§7 con el run id;
3. solo entonces: roadmap `F10 → CERTIFICADA`, `F11 → SIGUIENTE`,
   CHANGELOG de certificación y commit `docs(f10): certificar …`.

**Prohibido marcar F10 CERTIFICADA con evidencia solo-local**
(roadmap §5.5.4 + prompt F10 §33: `CI real verde`).
