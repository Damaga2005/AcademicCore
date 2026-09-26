# D7 — Ingesta estructurada → Knowledge Core

> **Fase:** D7 — puente determinista entre el esquema neutro D6 y el
> Knowledge Core real.
> **No implementa:** F9 (intentos/scoring/corrección), F10/F11/F12.

## 1. Pipeline

```text
D6 Question Bank
      ↓  parse_bank (D6 valida; entrada inválida = rechazo AC-ACD-004)
Normalize (canonical D6 + digests)
      ↓  plan_bank (dominio puro: resuelve refs contra snapshots)
Resolve references (reuse | create | rechazo determinista)
      ↓  apply en UNA transacción (validate → plan → apply → verify)
Knowledge Core entities (existentes + filas D7 mínimas)
      ↓  verify (relectura post-commit; mismatch = AC-INT-001)
Persist + provenance + digest
```

Capas:

```text
domain/ingestion.py          plan puro (sin DB, sin reloj)
application/bank_ingest.py   servicio: snapshots → plan → apply → verify
infrastructure/academic_store.QBankRepository + migración 016
```

`dry_run` es exactamente `plan`: cero escrituras por construcción.

## 2. Entrada

Solo bancos conformes a D6 (`raw → parse_bank → Bank validado`).
Todo lo que D6 rechaza, D7 lo rechaza sin reparar nada en silencio.

## 3. Mapping D6 → Knowledge Core

| D6 | Knowledge Core |
|---|---|
| `bank` | fila `qbank_banks` (source/provenance del lote) |
| `question` | fila `qbank_questions` (JSON canónico + digest + provenance) |
| `statement` | `canonical_json.statement` (fragmento estructurado; F9 lo consume) |
| `concepts` / `knowledge_refs[concept]` | `study_concepts` (existente F4.1; se reutiliza, se crea solo con catálogo) |
| `formulas` / `knowledge_refs[formula]` | `formulas` (entidad `academic.Formula` preexistente sin store; 016 le da tabla; solo con catálogo) |
| `provenance` (banco/pregunta) | fusionada con sello `d7-ingest/1` (determinista, sin timestamps) |
| `knowledge_refs[section/document/topic]` | `carried`: sin store D7; viajan opacos en el JSON para F9/futuro |
| `answer_spec` | almacenado verbatim en el JSON; **no** interpretado (corrección = F9) |

Nada de esto duplica modelos, IDs, provenance, unidades ni Knowledge Core.

## 4. Identidad y deduplicación

- Bancos/preguntas: IDs D6 estables (`bank:`, `question::q:`); el banco
  es dueño de su conjunto de preguntas.
- Conceptos: el ref D6 (`concept:<s>:c:NNNNN`) **es** el `stable_id`;
  el subject se extrae del propio ref y debe existir.
- Fórmulas: el ref D6 es el `stable_id` de `academic.Formula`.
- Dedup en dos niveles: digest de banco (lote) + digest por pregunta
  (tag `d6-question/1`, cambio fino). Reingesta del mismo digest =
  `unchanged` con cero escrituras.
- Contadores `id_counters.concept` se elevan al máximo creado
  (higiene contra colisiones futuras del `IdAllocator`); nunca se bajan.

## 5. Idempotencia

```text
ingest(X); ingest(X) == ingest(X)
```

Mismo digest → `unchanged`, sin tocar una sola fila (`updated_at_ms`
estable, verificado en tests). La reutilización nunca reescribe filas
existentes (nombres/estados SRS de conceptos y latex de fórmulas se
preservan byte a byte).

## 6. Reingesta y versiones

| Caso | Comportamiento |
|---|---|
| banco nuevo | `create`: banco + preguntas + conceptos/fórmulas de catálogo, 1 tx |
| mismo digest | `unchanged`: cero escrituras |
| `content_version` mayor | `update`: upsert por digest, borra preguntas ausentes (reportadas), actualiza banco |
| misma versión, distinto digest | conflicto `AC-ACD-003`, cero escrituras |
| versión menor | stale, `AC-ACD-003`, cero escrituras |
| ref inexistente sin catálogo | `AC-ACD-002` con la lista exacta, cero escrituras |
| ref concepto+formula a la vez | ambigüedad, `AC-ACD-003` |
| fórmula almacenada con latex distinto al catálogo | conflicto, `AC-ACD-003` (nunca overwrite) |
| subject del concepto inexistente | `AC-ACD-002` |

Nunca se sobrescribe en silencio. Se respeta `schema_version` y
`content_version` de D6; no existe versionado paralelo.

## 7. Digest

- `qbank_banks.digest` = digest canónico D6 del banco (autoridad D6,
  preservado verbatim).
- `qbank_questions.digest` = digest por pregunta (tag `d6-question/1`).
  Semántica **distinta** del digest de banco: sirve para detectar
  cambios finos. Nunca se mezclan (§9 del prompt D6/D7).
- `plan_digest` (tag `d7-ingest-plan/1`) cubre las operaciones
  semánticas del plan; el plan no contiene timestamps, así que el
  digest es estable entre ejecuciones.

## 8. Provenance extremo a extremo

Fila de banco/pregunta/fórmula = provenance D6 original +
`{imported_by: "d7-ingest/1", bank, bank_digest}`.
Estructura siempre, nunca texto libre. La cadena completa:

```text
banco D6 → pregunta D6 → fila qbank (+ sello) → concepto/fórmula
reutilizados o creados con provenance de importación
```

## 9. Transacciones

`QBankRepository.unit_of_work()` comparte un `cx` (`BEGIN IMMEDIATE`)
entre `Personal` + `QBank` + `TargetWriter(counters)`; cualquier fallo
→ `ROLLBACK` total (test de rollback con fallo inyectado a mitad de
apply: cero filas). DDL de la 016 es transaccional como las 001..015.
FTS/índices derivados: no hay en D7 (nada que derivar fuera de tx).

## 10. Determinismo

Mismo input + mismo estado inicial + mismo `now_ms` + misma versión →
mismo plan y mismo estado final. Orden total en todo (preguntas,
refs, links del report, deletes, counters). `now_ms` inyectable
(default: reloj real, como `_now()` de F4.1). Timestamps solo en
`ingested_at_ms/updated_at_ms`, fuera de todos los digests.

## 11. Seguridad

Contenido importado = no confiable. Rutas de ingestión sin `eval/exec/
compile/__import__/shell=True`/deserialización insegura (auditado por
AST en `test_d7_ingestion.py`, patrón D5). `latex` se almacena como
texto inerte (test con payload malicioso lo fija). Imports de los
ficheros nuevos ⊆ `{__future__, dataclasses, hashlib, json, re, time,
academic_core}`.

## 12. Persistencia (016 justificada, §19)

`016_qbank_ingest.sql` (aditiva; ninguna tabla certificada tocada):

- `qbank_banks` (lote: versión, digest, conteo, provenance, tiempos).
- `qbank_questions` (registro por `question_id` para F9 + verificación;
  índice por banco).
- `formulas` (persiste la entidad `academic.Formula`, que existía sin
  store; la consume `item_from_formula` de F9).

Necesidad demostrada: la idempotencia/versionado entre procesos exige
estado durable direccionable por ID; `app_settings` (KV de prefs F4.2)
no es un registro relacional y reutilizarlo sería un hack. Conceptos
siguen en `study_concepts` (reutilización, sin tabla nueva).
`test_migration.py` pin `15 → 16` (único toque a test certificado,
documentado en el gate).

## 13. Errores (taxonomía existente, sin códigos nuevos)

| Situación | Código |
|---|---|
| banco inválido según D6 | `AC-ACD-004` (causa D6 en el mensaje) |
| ref/subject inexistente | `AC-ACD-002` |
| conflicto/stale/ambigüedad/fórmula modificada | `AC-ACD-003` |
| invariante interna del plan | `AC-DOM-001` (dominio) |
| verificación post-commit fallida | `AC-INT-001` (bug, nunca aceptado) |

## 14. Contrato para F9

```text
Question → Attempt → Correction → Evidence
```

F9 resuelve `AssessmentItem.question_id` vía
`QBankRepository.get_question()` (JSON canónico + `answer_spec` +
refs + provenance). D7 no crea intentos, scoring ni corrección.

## 15. Límites / no-objetivos

F9–F12, F13-cloud, F16; segundo Knowledge Core/provenance/IDs/
unidades; scoring/mastery/corrección; LLM; ejecución de fórmulas;
migraciones fuera de la 016; segundo CI/suite; tocar fases
certificadas por comodidad (un pin de test migrado con justificación).
