# D6 — Esquema neutro y versionado para bancos de preguntas

> **Fase:** D6 — contrato neutro de banco de preguntas.
> **Estado:** implementada en `main`, pendiente de gate/CI para certificar.
> **No implementa:** D7 (ingesta), F9 (evaluación), F10/F11/F12.

## 1. Qué es D6

Representación canónica de un banco de preguntas académicas sin depender
de ninguna asignatura, disciplina o motor de corrección:

```text
Banco de preguntas
        ↓
Esquema neutro (este documento)
        ↓
Validación determinista
        ↓
Normalización canónica
        ↓
Versionado + digest
        ↓
D7 (ingesta → Knowledge Core)
```

Separación de responsabilidades:

```text
D6 → banco de preguntas (datos + contrato + validación + versionado)
D7 → ingesta → Knowledge Core
F9 → assessment / intentos / corrección
```

## 2. Modelo

Módulo puro: `src/academic_core/domain/question_bank.py`
(stdlib + `DomainError` + `identity.slugify`; sin Qt/SQL/red/reloj).

```text
Bank
 ├── bank_id            bank:<slug>            (estable, neutro, sin asignatura)
 ├── title              1..400 chars
 ├── content_version    entero >= 1            (revisión del contenido)
 ├── questions          0..1000 Question
 ├── description        0..2000 chars
 ├── language           "" | BCP-47 corto
 ├── domain             0..120 chars (etiqueta libre, p.ej. "physics")
 ├── extensions         solo claves x-<slug>
 └── provenance         forma ResourceProvenance (subset, §6)

Question
 ├── question_id        question:<bank>:q:NNNNN (slug == banco dueño)
 ├── statement          1..8000 chars
 ├── qtype              1 de 7 (§3)
 ├── answer_spec        según qtype (§4, sin algoritmo de corrección)
 ├── knowledge_refs     [{kind, ref}] kind ∈ concept/formula/section/document/topic
 ├── concepts           [refs]  (consumo D7)
 ├── formulas           [refs]  (consumo D7)
 ├── unit               símbolo (chequeo estructural; §5)
 ├── difficulty         easy/medium/hard/unspecified
 ├── estimated_time_s   1..86400 | null
 ├── tags               0..16 slugs únicos
 ├── language           "" | BCP-47 corto
 ├── provenance         como Bank (§6)
 └── extensions         solo claves x-<slug>
```

No existe `metadata` genérica: los hints de presentación viajan como
extensiones explícitas (`x-hint`, …). No hay timestamps, paths, hostnames
ni orden de filesystem en ninguna parte del modelo.

## 3. Tipos (`qtype`)

Conjunto inicial, pequeño y estable. El tipo describe qué representa la
pregunta, **no** cómo F9 la evalúa:

| qtype | Representa |
|---|---|
| `multiple_choice` | opciones + índices correctos |
| `true_false` | booleano |
| `numeric` | valor decimal + unidad/tolerancia/precisión |
| `symbolic` | expresión (dato inerte) + variables |
| `short_text` | esperado opcional + longitud + case flag |
| `structured` | esquema `{campo: text/integer/decimal/boolean}` |
| `circuit` | referencia a netlist + magnitudes |

## 4. `answer_spec` por tipo (claves cerradas)

- `multiple_choice`: `{options: [2..12 únicas, 1..2000 chars],
  correct: [índices válidos únicos]}`.
- `true_false`: `{answer: bool}` (bool exacto, `1` no vale).
- `numeric`: `{value: decimal-str, unit?: símbolo,
  tolerance?: decimal-str ≥ 0, precision?: int 1..28}`.
  `tolerance` XOR `precision`, nunca ambos.
- `symbolic`: `{expression: 1..4000 chars, variables?: [0..32 identificadores]}`.
  La expresión es **dato/AST futuro, nunca código ejecutable**.
- `short_text`: `{expected?: 1..2000 chars, max_length?: 1..8000,
  case_sensitive: bool=false}`.
- `structured`: `{schema: {1..32 campo-identificador: tipo}}`.
- `circuit`: `{netlist_ref: 1..2000 chars,
  quantities?: [{name: identificador, unit?: símbolo}]}`.

Los decimales viajan como **strings** (política cero-floats) y se preservan
verbatim: la equivalencia numérica (`1.50 == 1.5`) la define F9, no D6.

## 5. Unidades

`unit` se valida estructuralmente (1..32 chars del alfabeto de símbolos).
La resolución semántica es contrato de D7/F9 vía
`engineering.units.parse_unit`; los tests D6 fijan que los símbolos de
ejemplo (`V, mV, kohm, Hz, A`) resuelven en el sistema existente.
D6 no crea un segundo sistema de unidades.

## 6. Provenance y knowledge references

Se reutiliza la forma F2 (`ResourceProvenance`): claves cerradas
`{source, version, stable_id, resource_id, content_hash, adapter,
adapter_version}`, `content_hash` sha256-hex cuando existe.
`knowledge_refs` admite referencias estructuradas a
conceptos/fórmulas/secciones/documentos/topics **sin materializar**
entidades del Knowledge Core (eso es D7).

## 7. Identidad y versionado

- `bank:<slug>` y `question:<slug>:q:NNNNN`, con `slugify` de `identity`
  (reutilizado, no duplicado). El slug de la pregunta debe coincidir con
  el del banco dueño; los ids de pregunta son únicos dentro del banco.
- `schema_version` (contrato, hoy `1`, tag `d6-question-bank/1`) ≠
  `content_version` (revisión del contenido, `≥ 1`).
- `schema_version` desconocido → `AC-VER-001` (rechazo, sin migración
  especulativa). `schema` distinto → `AC-SER-001`.

## 8. Canonicalización y digest

Precedente reutilizado: `lab/serialize.canonical` + `digest`
(`tag || 0x00 || canonical_json`):

- dicts con claves ordenadas, listas que conservan orden,
  `Decimal → str`, `float → rechazo`, sin `set/bytes`,
  profundidad máxima 6.
- `dumps_canonical`: `sort_keys, separators=(",",":"),
  ensure_ascii, allow_nan=False`.
- `bank_digest = sha256("d6-question-bank/1" + 0x00 + canonical(bank))`.
  Cubre el contenido semántico; no hay campos volátiles que excluir
  porque el modelo no los tiene.
- El digest cambia ante cualquier cambio semántico y solo ante esos.

## 9. Serialización

```text
Bank → bank_to_dict → dumps_canonical → envelope {bank, integrity, schema, schema_version}
envelope → parse_bank → Bank validado (digest recomprobado)
```

Round-trip estable garantizado:
`serialize(parse(serialize(x))) == serialize(x)`.
Claves de envelope/contenido estrictas: cualquier campo desconocido →
`AC-SER-001`. Claves JSON duplicadas, `NaN/Infinity`, no-UTF-8 y
payloads `> 1 MiB` se rechazan (`AC-SER-001` / `AC-SEC-001`).

## 10. Validación y errores (taxonomía D2 existente)

| Situación | Código |
|---|---|
| invariante de dominio (tipos, rangos, ids, refs, answer_spec) | `AC-DOM-001` |
| serialización malformada, campos desconocidos, digest mismatch | `AC-SER-001` |
| `schema_version` no soportado | `AC-VER-001` |
| límites excedidos (tamaño, profundidad) | `AC-SEC-001` |

Sin códigos nuevos: todos existen en `docs/specs/ERROR-CODES.md`.
Nunca interviene un LLM; los errores son estructurados y reproducibles.

## 11. Seguridad

El banco es dato no confiable: prohibido `eval/exec/compile/__import__/
shell=True`/deserialización insegura (auditado por AST en
`tests/test_d6_question_bank.py::test_security_contract`, mismo patrón
que el contrato D5). Sin imports fuera de
`{__future__, dataclasses, decimal, hashlib, json, re, academic_core}`.

## 12. Límites

`1 MiB` por envelope, `1000` preguntas/banco, profundidad `6`,
`32` extensiones, `64` knowledge_refs, strings acotados por campo (§2/§4).

## 13. Sin persistencia (decisión §18)

D6 es formato + validador. Los bancos viajan como ficheros JSON
canónicos; **no** hay tablas, migraciones ni store paralelo.
Si D7/F13 necesitan almacenar bancos, reutilizarán `Database` +
migración idempotente. `delete_subject` y el resto de repositorios
certificados quedan intactos.

## 14. Contrato para D7

D7 consumirá, en este orden:

```text
Question Bank → Parser/Importer (parse_bank) → Normalization
  (canonical + digest) → Knowledge Core
```

Campos de entrada D7: `bank_id/title/content_version` (linaje),
`questions[]` con `statement/qtype/knowledge_refs/concepts/formulas/
unit/provenance`, `digest` como testigo de integridad.
D7 **no** debe reinterpretar `answer_spec` como corrección.

## 15. Preparación para F9

```text
Question → Attempt → Correction → Evidence
```

`question_id` es la referencia opaca que `AssessmentItem.question_id`
espera; `answer_spec` aporta la estructura de respuesta y `difficulty/
estimated_time_s/tags` la selección futura. Intentos, scoring, mastery
y corrección quedan explícitamente fuera.

## 16. Límites de D6 (no-objetivos)

D7, F9, F10, F11, F12, F13-cloud, F16; modelos por asignatura; segundo
Knowledge Core/unidades/provenance; scoring/mastery/corrección;
validación con LLM; ejecución de fórmulas; JSON arbitrario; tipos
especulativos; formatos múltiples/CI paralelo.
