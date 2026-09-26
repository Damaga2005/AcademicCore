# F9 — Assessment y Evaluación Formal

> **Fase:** F9 — corrección determinista y evidencia sobre D6/D7.
> **No implementa:** F10 (mastery), F11/F12, ni cambios de scoring.

## 1. Modelo

```text
Question (D6, congelada en snapshot)
Assessment (agregado F9-B: items + policy + intentos)
Attempt (sesión F9-B/C + snapshots F9)
Answer (payload F9 por tipo, §4)
Correction (motor f9-correct/1, §5)
EvaluationResult (GradingPolicy certificada, sin cambios)
Evidence (filas assessment_evidence + DTO AttemptEvidence para F10)
```

Separación: el motor devuelve veredicto + ratio; el scoring vive en
`GradingPolicy`; el servicio orquesta; el repositorio persiste.

## 2. Assessment y Attempt

- `Assessment`: identidad `assessment:<s>:as:NNNNN`, items ordenados
  (`question_id` opaco + peso Decimal), `attempts_allowed`, `policy`,
  orden determinista por seed. Sin cambios (F9-B certificado).
- `Attempt`: `AssessmentSession` + **snapshots** (`assessment_item_
  snapshots`: `question_id, content_version, question_digest,
  canonical_json, provenance`). El snapshot congela lo examinado: un
  cambio posterior del banco no reescribe la historia.
- `create_attempt` hace cumplir `attempts_allowed` (los intentos
  cancelados no consumen cupo: se reutiliza el número libre más bajo).
- Estados `NOT_STARTED → IN_PROGRESS → SUBMITTED|EXPIRED|CANCELLED`
  (F9-B/C). Un intento evaluado es inmutable (triggers + guardas).

## 3. Snapshot y versionado

Cada resultado queda vinculado a:

```text
assessment_version  = fila assessments (título/items/policy del intento)
question_version    = snapshot.content_version (D7)
question_digest     = snapshot.question_digest (tag d6-question/1)
correction_engine   = f9-correct/1 (evidence.engine)
evaluation_config   = policy serializada del assessment
```

Sin versionado paralelo. `build_evidence` recomputa el digest del
snapshot y expone `verified` (un snapshot manipulado da `False`, no
rompe).

## 4. Respuestas (payloads F9 por tipo)

La respuesta se conserva como JSON canónico del payload (valores
intactos). Formas estrictas (claves exactas, resto → `AC-ACD-004`):

| tipo | payload |
|---|---|
| `multiple_choice` | `{selected: [índices únicos válidos]}` |
| `true_false` | `{answer: bool}` |
| `numeric` | `{value: decimal-str, unit?: str}` |
| `symbolic` | `{expression: str}` |
| `short_text` | `{text: str}` |
| `structured` | `{fields: {nombre: valor}}` |
| `circuit` | `{quantities: {nombre: {value, unit?}}}` |

## 5. Corrección determinista (`domain/correction.py`, motor `f9-correct/1`)

`Question + Answer + AnswerSpec → Verdict(is_correct|None, ratio,
reason, normalized)`. Solo tipos D6. Razones cerradas en `REASONS`.

- `multiple_choice`/`true_false`: comparación exacta de conjuntos/bool.
  Binario, sin parcial inventado.
- `numeric`: aritmética `Decimal` exacta sobre `engineering.units`
  (conversión + dimensiones). `tolerance`: `|dif| ≤ tol` en la unidad
  esperada (unidad ausente = asumida, documentado). `precision`: cifras
  significativas con `ROUND_HALF_UP`. Dimensión incompatible →
  `dimension_mismatch` (incorrecto, no excepción).
- `symbolic`: motor `symbolic` certificado. Una variable →
  `equivalent` (prueba `symbolic_equivalent`); si no, acuerdo numérico
  `Decimal` exacto en puntos fijos (`symbolic_numeric_agreement`,
  honesto: acuerdo, no prueba). Símbolos distintos → `symbol_mismatch`.
  Expresiones no parseables (límite 256 del motor) → error estructurado.
- `short_text`: con `expected` → coincidencia exacta (`case_sensitive`
  del spec); sin `expected` → `needs_review` (nunca puntuación inventada).
- `structured`/`circuit`: los contratos D6 no traen valores esperados;
  solo validación de forma (conjuntos exactos, tipos, dimensiones) +
  `needs_review` con la carga normalizada como evidencia. La
  verificación por simulación (`netlist_ref`) queda documentada como
  futura.
- Respuestas malformadas → `DomainError` (`AC-DOM-001`, vía servicio
  `AC-ACD-004`); nunca se ejecutan (`eval/exec/compile…` auditados).

`needs_review` puntúa como omitido (`None,None` → 0 vía `GradingPolicy`).

## 6. Scoring

`GradingPolicy` sin cambios: `score/max/percentage`, suma exacta,
`ROUND_HALF_UP`, floor global a 0, `negative_marking`,
`allow_partial_credit`, `passing_score`. Políticas contratadas:
omitidas = 0 sin penalización, revisión pendiente = 0, penalización
negativa configurada. Sin preguntas anuladas: no hay política
contratada (no inventada).

## 7. Evidence (para F10)

Fila por ítem respondido: `question_id, qtype, is_correct, ratio,
score, reason, engine, given_normalized, evaluated_at` (inmutable).
`AttemptEvidence`: intento + resultado + por ítem (pregunta,
versión/digest, raw + normalizada, corrección, score, conceptos/
fórmulas del snapshot, provenance con sello `d7-ingest/1`, `verified`).
Omitidos: razón `omitted`, score 0. Sin mastery dentro de F9.

## 8. ExecutionTrace

La corrección es comparación directa, no ejecución de solver: no se
genera traza retrospectiva inventada. Las expresiones almacenadas
permiten replay futuro (`explain_simplify`, `explain_equation`).

## 9. Persistencia (017 justificada, §15)

`017_f9_attempt_evidence.sql` (aditiva; ninguna tabla certificada
tocada): `assessment_item_snapshots` + `assessment_evidence` +
triggers de inmutabilidad. Necesidad: el historial de intentos exige
preguntas congeladas y veredictos direccionables; ninguna tabla 001..016
los guarda. Refactor mínimo: cuerpo de `save_session` extraído a
`_save_session_tx` (misma semántica, verificada por F9-D) + `cx`
componible (`save_session_cx`, `unit_of_work`, batches con `cx`).
Pins `16 → 17` en `test_migration.py`/`test_persistence.py` (la 017 los
exige; único toque a tests certificados).

## 10. Transacciones

```text
submit → validate → correct (puro) → persist result/evidence → commit
```

`submit_with_correction` en UN `unit_of_work` (`save_session_cx` +
`save_evidence_batch`); fallo → `ROLLBACK` total (test con fallo
inyectado: sesión intacta, sin resultado ni evidencia).

## 11. Determinismo y seguridad

Misma pregunta + misma respuesta + misma config + `f9-correct/1` →
mismo veredicto (sin reloj/random/locale/red/LLM; seeds fijos en tests).
Contenido no confiable nunca ejecutado (AST + allowlist de imports).

## 12. Errores (taxonomía existente)

| Situación | Código |
|---|---|
| payload/respuesta malformada, item desconocido, sesión ajena | `AC-ACD-004` |
| sesión/intento/pregunta desconocidos, intento sin preparar | `AC-ACD-002` |
| doble submit, intentos agotados, expirada en submit | `AC-ACD-003` |
| invariante del motor | `AC-DOM-001` |
| divergencia post-commit | `AC-INT-001` |

## 13. Contrato para F10

`build_evidence(session_id) → AttemptEvidence`: pregunta,
versión/digest, respuesta (raw + normalizada), spec outcome,
corrección, score, conceptos/fórmulas, `verified`, provenance.
F10 modela mastery; F9 no lo toca.

## 14. Límites / no-objetivos

F10–F12, F13-cloud, F16; segundo Knowledge Core/unidades/provenance/
solver/CI/suite; LLM como autoridad; ejecución de fórmulas/respuestas;
tipos/scoring/tolerancias inventados; simulación de circuitos como
corrección; tocar D6/D7 o fases certificadas por comodidad.
