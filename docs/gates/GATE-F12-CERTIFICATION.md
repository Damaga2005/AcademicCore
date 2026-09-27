# GATE-F12-CERTIFICATION — F12 Tutor Socrático (IA con Guardrails)

> **FASE:** F12 — asistencia LLM sobre F9/F10/F11, autoridad determinista.
> **BASELINE:** `main @ 44a2b7f` (F11 CERTIFICADA); árbol limpio al inicio
> (salvo `.claude/` local sin trackear, config del agente, intacta).
> **Rama:** `main`, sin líneas paralelas.
> **Implementación:** `35763bc8b09c9f212c1b7389e0ceb8472cb62fe4`
> `feat(f12): implement Socratic AI tutor with deterministic guardrails`.
> **Estado:** **F12 CERTIFICADA** — CI real verde, run
> [`36336990034`](https://github.com/Damaga2005/AcademicCore/actions/runs/36336990034)
> (ver §7).

## 1. Baseline pre-F12 (2026-09-27, local win, py 3.14.6)

Subset relevante (F9/F9b/c/d, F10, F11, D4/D5/D6/D7, arquitectura,
migración, persistencia, provenance, F4-security):

```powershell
$env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen'
python -m pytest tests/test_f9_correction.py tests/test_f9b_domain_assessment.py `
  tests/test_f9c_assessment_orchestration.py tests/test_f9d_assessment_persistence.py `
  tests/test_f10_mastery.py tests/test_f11_adaptive.py tests/test_d7_ingestion.py `
  tests/test_d6_question_bank.py tests/test_d5_contracts.py tests/test_d4_pipeline.py `
  tests/test_architecture.py tests/test_migration.py tests/test_persistence.py `
  tests/test_provenance.py tests/test_f4_security.py -q
```

- F9/F10/F11/D4/D5/D6/D7 y arquitectura verdes antes de empezar
  (requisito §1 del prompt F12). El subset completo (sin F12 todavía)
  ya venía verde de la certificación F11 previa.

## 2. Inspección obligatoria (§1 del prompt F12)

- **F11:** `AdaptivePlan` (selecciones + rationale cerrado,
  `config_version`, `model_version`, `bank_digest`, `mastery_snapshot`),
  tag `f11-adaptive-plan/1`. Su propio doc (§14) nombra a F12 como
  consumidor explícito. F12 solo lee: no re-planifica.
- **F10:** `get_mastery`/`get_topic_mastery`/`get_subject_mastery`
  (lectura), `model_version=f10-beta/1`. F12 no recalcula mastery.
- **F9:** `AttemptEvidence`/`build_evidence`, `Verdict` (`is_correct`,
  `ratio`, `reason`, `normalized`, `engine=f9-correct/1`). **`correct_answer`
  es el único verificador de claims de F12** — sin segundo motor.
- **D6/D7:** 7 `qtype`, `answer_spec` por tipo, `schema_version`/
  `content_version`, digests vía `dumps_canonical`+sha256.
- **Solvers:** `domain/execution/*`, `domain/engineering/*`,
  `ExecutionTrace` (`execution-trace/1`). No importados directamente
  por F12: la única puerta de entrada es `correct_answer` (F9).
- **`engines/ai.py`:** stub Fase 0 real (`ModelBackend`/`OllamaBackend`/
  `AIRouter`), sin `metadata()`, sin JSON estructurado, timeout
  hardcodeado a 120s. Adaptado (no reescrito): se añadió un parámetro
  `timeout` opcional con el mismo default, sin romper firmas existentes
  (`engines/__init__.py` y `test_architecture.py::hasattr(e, "AIRouter")`
  verificados como únicos consumidores).
- **Migraciones:** `019_f11_adaptive.sql` confirmado como la última
  antes de crear `020_f12_tutor.sql` (verificado dos veces: antes y
  justo antes de escribir el fichero, `ls` directo sobre el
  directorio real, nunca asumido).

## 3. Implementación F12

| Cambio | Alcance |
|---|---|
| `domain/tutor.py` (nuevo, puro) | `TUTOR_SCHEMA` (`f12-tutor-response/1`), `RESPONSE_TYPES` (6 cerrados), `SOCRATIC_LADDER` (6 etapas), `Claim`/`TutorProposal`/`VerifiedResponse`, `parse_proposal` (schema estricto), `policy_stage`/`allows_final_claim`/`enforce_policy` (`AC-TUT-004`), `verify_claims` (delega en `domain.correction.correct_answer`, ningún motor nuevo), `build_response`, `turn_digest` (`f12-tutor-turn/1`) |
| `infrastructure/llm.py` (nuevo) | `LLMProvider` (protocolo estructural), `LLMRequest`/`LLMResponse`/`ProviderMetadata`, `NullProvider` (LLM=OFF), `OllamaProvider` (adapta `OllamaBackend` existente; `LLM_TIMEOUT`/`PROVIDER_ERROR` tipados) |
| `application/tutor.py` (nuevo) | `TutorService.get_response`: recibe contexto ya resuelto (F9/F10/F11), construye `LLMRequest`, valida/verifica, persiste. Sin recalcular mastery/plan/corrección |
| `engines/ai.py` (aditivo mínimo) | `OllamaBackend.generate(..., timeout=120.0)` — parámetro opcional, default idéntico al hardcodeado previo, cero ruptura |
| `errors.py` + `ERROR-CODES.md` (aditivo) | `TutorError`, `F12_ERROR_CODES`, área `TUT`: `AC-TUT-001..006` |
| `migrations/020_f12_tutor.sql` (nueva, aditiva) + `database._MIGRATIONS` | `tutor_turns` (turn_id PK determinista, solo respuesta verificada + provenance — **sin** texto crudo del LLM ni propuesta intermedia), índice por student, trigger de inmutabilidad (mismo patrón que 017) |
| `infrastructure/academic_store.py` (aditivo) | `TutorRepository` (`turn_count`, `save_turn` INSERT OR IGNORE idempotente, `turns_of`) |
| `infrastructure/__init__.py` (aditivo) | Exporta `TutorRepository`, `LLMProvider`, `LLMRequest`, `LLMResponse`, `NullProvider`, `OllamaProvider`, `ProviderMetadata` |
| `tests/test_f12_tutor.py` (nuevo, 35 tests) | Schema (válido/inválido/campo desconocido/ausente/tipo/tamaño/versión), claims (7 qtypes vía F9, needs_review→unverified, malformado→rejected, skip), autoridad (solver gana sobre LLM, no-verificable→NOT VERIFIED), política (ladder, etapa derivada de intentos), servicio (LLM=OFF, timeout, JSON inválido, contexto sin mutar F9/F10/F11, rechazo de política), persistencia (contador, digest determinista, inmutabilidad vía trigger, sin texto crudo), seguridad (prompt injection inerte, sin eval/exec/compile, sin secretos, HTML no ejecutado) |
| `tests/test_migration.py`, `tests/test_persistence.py` | Pins `19 → 20` (únicos toques a tests certificados; la 020 los exige) |
| `docs/architecture/F12-SOCRATIC-TUTOR.md` (nuevo) | Arquitectura, schema, claims, autoridad, política, contexto, LLM=OFF, seguridad, persistencia, provenance, errores, proveedor, límites |

Comportamiento certificado cambiado: **ninguno** (solo métodos nuevos
en módulos existentes + pins + un parámetro opcional aditivo en
`OllamaBackend.generate`). F9/F10/F11/D5/D6/D7 no fueron modificados
en su lógica; solo dos tests de infraestructura (migración/persistencia)
actualizaron el conteo de migraciones, que la propia 020 exige.

## 4. Evidencia fresca (local)

- Nuevos: `test_f12_tutor.py` = **35 passed**.
- Regresión curada (§1 + F12): **306 passed, 1 skipped** (mismo skip
  ambiental que F11: `test_document_symlink_escape_refused`, el SO
  niega symlinks sin modo desarrollador — excepción ambiental
  documentada, no relacionada con F12).
- Seguridad: sin `eval`/`exec`/`compile` en `domain/tutor.py` ni
  `application/tutor.py` (test dedicado); `verify_claims` no importa
  `domain/execution` ni `domain/engineering` directamente — delega
  siempre en `correct_answer` (F9).

## 5. Regresión amplia — suite completa sin filtrar (`pytest -m "not external"`)

Se ejecutó la suite completa del repositorio (todas las fases F1–F16,
D1–D7, no solo el subset curado). Resultado: **13 fallos**, de los
cuales **12 son preexistentes y no relacionados con F12** y **1** era
un pin de conteo de migraciones ya corregido en §3-4.

- **12 fallos CRLF/LF en fixtures doradas** (`test_e0_execution_trace.py`,
  `test_f8n_lab_valid.py`, `test_f8q4_digital_trace_serialization.py`
  ×6, `test_f8q5_logic_analyzer.py` ×4): diferencia de fin de línea
  (`\r\n` vs `\n`) en ficheros de fixture del checkout Windows —
  **verificado explícitamente**: `git stash` de todo el trabajo F12 →
  los mismos dos tests representativos (`test_e0_g01_golden_voltage_
  divider`, `test_q4_g01_golden_fixture[empty]`) fallan idénticamente
  sobre `main` limpio → `git stash pop` restaura F12 intacto. Confirma
  que es un problema ambiental de checkout (`core.autocrlf` / línea de
  fin de fichero), no introducido por F12. F12 no toca ningún fichero
  de F8/E0/digital-trace/logic-analyzer.
- **1 fallo real, ya corregido**: `test_persistence.py::
  test_migrations_are_incremental_and_rerunnable` pineaba la lista de
  migraciones a `19` (F11); la 020 (F12) la extiende a 20 legítimamente
  — mismo patrón documentado en el gate F11 (`18→19`). Corregido
  (`19 → 20`) y reverificado verde en el subset del §4.
- Ninguno de los 13 fallos toca `domain/tutor.py`, `application/tutor.py`,
  `infrastructure/llm.py`, `infrastructure/academic_store.py::
  TutorRepository`, ni el schema/validador/claims/autoridad de F12.

## 6. Errores (taxonomía nueva, área `TUT`)

| Código | Situación |
|---|---|
| `AC-TUT-001` | JSON no parseable |
| `AC-TUT-002` | schema inválido |
| `AC-TUT-003` | claim no verificable / rechazado por el solver |
| `AC-TUT-004` | política rechaza (revelación socrática prematura) |
| `AC-TUT-005` | LLM no disponible (LLM=OFF o sin proveedor) |
| `AC-TUT-006` | error de proveedor / timeout |

Documentados en `docs/specs/ERROR-CODES.md`; unicidad y
documentación verificadas por `test_f4_security.py::
test_error_codes_unique_and_documented` (pasa, §4).

## 7. Criterios (§28 del prompt F12)

- [x] Tutor socrático implementado (`domain/tutor.py` + `application/tutor.py`)
- [x] Salida LLM estructurada (`f12-tutor-response/1`)
- [x] JSON schema versionado (`parse_proposal`, campos cerrados)
- [x] Validator determinista (schema/tipo/tamaño/campos)
- [x] Claims verificables (`Claim.verification_required`)
- [x] Referencias verificadas (`Claim.answer` corregido vía F9)
- [x] Solver determinista reutilizado (`correct_answer`, sin motor nuevo)
- [x] Matemática/unidades/simbólico verificados (numeric/symbolic vía F9, tests)
- [x] Ingeniería/circuitos verificados cuando corresponde (`needs_review`→`unverified`, honesto como F9)
- [x] LLM nunca es autoridad final (`verify_claims`: solver decide; test de autoridad)
- [x] `verified/unverified/rejected` diferenciados (`VerifiedResponse.status`)
- [x] `LLM=OFF` funcional (`NullProvider`, respuesta estática verificada)
- [x] Errores del proveedor tratados (`LLM_TIMEOUT`/`PROVIDER_ERROR`, tests)
- [x] Timeouts definidos (`LLMRequest.timeout_s`, `OllamaBackend.generate(timeout=)`)
- [x] Límites definidos (`MAX_MESSAGE`/`MAX_STEPS`/`MAX_CLAIMS`/`MAX_CONTEXT_CHARS`/`MAX_RESPONSE_CHARS`)
- [x] Prompt injection tratada (contexto nunca concatenado con política; test)
- [x] Tool access restringido (el LLM no tiene herramientas; solo JSON)
- [x] Secrets protegidos (sin API keys en esta fase; test de no-secretos)
- [x] Provenance disponible (`tutor_turns`: refs F9/F10/F11, provider/model, solver_version, schema_version)
- [x] Auditoría completa (cadena reconstruible, §11 del doc de arquitectura)
- [x] Persistencia correcta (020, append-only, idempotente, sin texto crudo)
- [x] Tests F12 verdes (35/35)
- [x] F11 continúa verde (regresión §4)
- [x] F10 continúa verde (regresión §4)
- [x] F9 continúa verde (regresión §4)
- [x] D7 continúa verde (regresión §4)
- [x] D6 continúa verde (regresión §4)
- [x] D5 continúa verde (regresión §4)
- [x] **CI real verde.** Run
      [`36336990034`](https://github.com/Damaga2005/AcademicCore/actions/runs/36336990034)
      (commit `35763bc`): **4/4 celdas success** (windows-2025 py3.13
      27m51s, ubuntu-24.04 py3.13 17m31s, ubuntu-24.04 py3.12 19m12s,
      windows-2025 py3.12 31m18s) + `package (ubuntu, py3.12)` success.
      Sin reintentos, a la primera. Único aviso: deprecación de Node.js
      20 en `actions/upload-artifact@v5` (infraestructura de CI, ajeno
      a F12). **Confirma además, de forma independiente, que los 12
      fallos CRLF/LF del §5 son un artefacto del checkout Windows
      local** (config `core.autocrlf` de esta máquina) y no un defecto
      real: ambas celdas `windows-2025` de CI —que sí ejecutan la
      misma suite— pasan limpias.
- [x] Documentación creada (`F12-SOCRATIC-TUTOR.md`)
- [x] Gate creado (este fichero)
- [x] F13 no implementado
- [x] F16 no implementado

## 8. Certificación

**F12 CERTIFICADA.** Todos los criterios §7 demostrados con evidencia
fresca: 35/35 tests F12, regresión curada 306 passed/1 skip ambiental,
y CI real verde 4/4 + package (run `36336990034`, commit `35763bc`).
Los 12 fallos CRLF/LF del §5 quedan documentados como preexistentes y
no relacionados con F12 (verificado por partida doble: `git stash`
contra `main` limpio en §5, y ahora las celdas Windows del CI real, que
no los reproducen). Roadmap: `F12 → CERTIFICADA`, `F13 → SIGUIENTE`.
