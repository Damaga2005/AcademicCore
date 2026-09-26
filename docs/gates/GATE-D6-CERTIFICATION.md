# GATE-D6-CERTIFICATION — D6 Esquema neutro de banco de preguntas

> **FASE:** D6 — contrato neutro, versionado, determinista y extensible.
> **BASELINE:** `main @ 0d821c7` (D5 CERTIFICADA); árbol limpio al inicio
> (salvo `.claude/` local sin trackear, config del agente, intacta).
> **Rama:** `main`, sin líneas paralelas.
> **Implementación:** `07b3136`
> `feat(d6): esquema neutro versionado de banco de preguntas`.

## 1. Baseline pre-D6 (2026-09-26, local win, py 3.14.6)

Subset relevante (= CI canónico sobre las áreas tocadas/vecinas):

```powershell
$env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen'
python -m pytest tests/test_d6_question_bank.py tests/test_d5_contracts.py `
  tests/test_d4_pipeline.py tests/test_architecture.py tests/test_f4_security.py `
  tests/test_f13ext_sync.py tests/test_f13ext_service.py `
  tests/test_f9b_domain_assessment.py tests/test_f9c_assessment_orchestration.py `
  tests/test_f9d_assessment_persistence.py -q
```

- Resultado: **189 passed, 1 skipped**, 0 failed.
  (1 skip = `test_document_symlink_escape_refused`: el SO niega symlinks;
  excepción ambiental §14, fijada por `conftest.py` + `test_d4_pipeline.py`.)
- Multiseed (`PYTHONHASHSEED=0/1/42`):
  `test_d6_question_bank + test_d5_contracts + test_architecture` →
  **36 passed × 3**.
- D5 permanece verde antes de empezar (requisito §2 del prompt D6).

## 2. Inspección obligatoria (§1 del prompt D6)

Tres lecturas paralelas del `main` real + verificación directa:

- **Modelo F4/F4.1/F4.2:** jerarquía `entities.py` (`subject→topic→…`),
  `career/evaluation/course_material/planning`, servicios en
  `application/academic_mgmt.py`, F9 en `domain/assessment/` +
  `application/assessment.py`. **No existe banco de preguntas**
  (0 hits `QuestionBank|question_bank` en `src`); `AssessmentItem`
  solo guarda `question_id` opaco sin tabla que lo respalde.
- **Serialización/digests:** patrón dominante
  `sha256(tag + 0x00 + canonical_json)` en `lab/serialize.py:91-152`
  (+ `control/report.py`, `metrology/o5_traceability.py`, `codec.py`,
  `documents/ast.py`). D6 lo copia, no lo duplica.
- **Unidades/provenance/E0:** `engineering/units.py`
  (`parse_unit`, `Quantity` Decimal); provenance F2
  (`ResourceProvenance`) + sello interno electrónico; E0
  (`domain/execution/*`, observer inerte). D6 reutiliza formas y
  contratos sin crear segundos sistemas.
- **Persistencia/D5:** `Database` 001..015 forward-only; D5 certificada
  en `c14c317` (run `36232344763` 4/4 + package).

## 3. Implementación D6 (`07b3136`, +1268 líneas, 3 ficheros nuevos)

| Cambio | Alcance |
|---|---|
| `src/academic_core/domain/question_bank.py` (nuevo) | `Bank`/`Question` frozen, 7 `qtype`, `answer_spec` por tipo con claves cerradas, IDs `bank:<slug>` / `question:<slug>:q:NNNNN` (vía `identity.slugify`), `schema d6-question-bank/1` + `content_version`, canonicalización `sort_keys/separators/ensure_ascii/allow_nan=False`, `bank_digest`, envelope con `integrity`, `parse_bank` estricto, límites (1 MiB/1000/6), errores D2 existentes (`AC-DOM/ SER/VER/SEC-001`), cero floats, fórmulas como dato inerte |
| `tests/test_d6_question_bank.py` (nuevo, 16 tests) | Los 18 puntos del §14 del prompt en 16 tests contractuales (tipos parametrizados en 1 test, answer_specs inválidos en 1 test): banco/pregunta mínimos, tipos, obligatorios, IDs estables, schema + rechazo `AC-VER-001`, canonicalización, digest semántico, round-trip, provenance, knowledge_refs, answer_spec, unidades (+ cross-check `parse_unit`), extensiones `x-`, estructuras inválidas/tamper, determinismo, seguridad AST + límites |
| `docs/architecture/D6-QUESTION-BANK.md` (nuevo) | Referencia única: modelo, tipos, answer_specs, unidades, provenance, identidad/versionado, canonicalización/digest, serialización, validación/errores, seguridad, límites, decisión sin-persistencia, contratos D7 y F9, no-objetivos |

Código certificado tocado: **nada**. Ni motores, ni migraciones,
ni `identity.py`/`errors.py`/gates/tests certificados. Códigos de error
reutilizados (todos en `ERROR-CODES.md`; `used ⊆ table` verde en
`test_error_codes_unique_and_documented`).

## 4. Evidencia fresca (local)

- Nuevos: `test_d6_question_bank.py` = **16 passed**
  (2 fallos iniciales durante el desarrollo — `%` no resuelve en
  `parse_unit` — confirmaron que los tests muerden antes del fix;
  fix solo-test: símbolos `V/mV/kohm/Hz/A`).
- Regresión áreas vecinas: `d5_contracts, d4_pipeline, architecture,
  f4_security, f13ext_sync/service, f9b/c/d` → verdes (§1).
- Arquitectura: `test_domain_is_pure`, `test_domain_knows_no_backends`,
  `test_no_flask_or_web_stack_anywhere` verdes con el fichero nuevo
  (imports ⊆ `{__future__, dataclasses, decimal, hashlib, json, re,
  academic_core}`).
- Seguridad AST: sin `eval/exec/compile/__import__/shell=True`,
  sin red/subprocess/pickle/os/pathlib/sqlite3 (test propio +
  suite D5 intacta).

## 5. Criterios (§21 del prompt D6)

- [x] esquema neutro y no dependiente de asignatura
- [x] schema version explícita (`d6-question-bank/1`, `SCHEMA_VERSION=1`)
- [x] identidad estable (`bank:` / `question::q:`, slug determinista)
- [x] validación determinista (pura, sin LLM, sin reloj/red/paths)
- [x] canonicalización (orden de campos, Unicode, listas/mapas,
      null/opcionales, IDs, sin floats)
- [x] digest reproducible (cambia ⟺ cambia lo semántico)
- [x] extensiones explícitas (`x-`, `strict core + explicit extensions`)
- [x] provenance reutilizable (forma F2, `content_hash` sha256)
- [x] referencias a Knowledge Core sin implementar D7
- [x] answer_spec separado de corrección (F9 pendiente)
- [x] unidades reutilizadas (chequeo estructural + `parse_unit` en tests)
- [x] serialización y round-trip deterministas
- [x] casos inválidos rechazados estructuradamente (`AC-DOM/SER/VER/SEC`)
- [x] seguridad cubierta (AST + límites + dup-keys + NaN + oversize)
- [x] tests D6 verdes (16/16 local)
- [x] regresión D5 verde (§1)
- [x] CI real verde — run `36236406471` (`86f105d`): 4/4 celdas
  success (windows/ubuntu × 3.12/3.13: win-3.12 23m49s, ubuntu-3.12 28m58s,
  ubuntu-3.13 30m48s, win-3.13 32m48s) + package success (ver §6)
- [x] documentación creada (`D6-QUESTION-BANK.md` + este gate)
- [x] gate creado (este fichero)
- [x] roadmap actualizado a `D6 CERTIFICADA` / `D7 SIGUIENTE` tras el CI verde

## 6. Certificación

**D6 CERTIFICADA.** Todos los criterios §21 demostrados con evidencia
fresca del proveedor (run `36236406471`, commit `86f105d`). Roadmap:
`D6 → CERTIFICADA`, `D7 → SIGUIENTE`.
