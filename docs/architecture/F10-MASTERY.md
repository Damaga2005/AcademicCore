# F10 — Mastery y Modelado del Estudiante

> **Fase:** F10 — modelo probabilístico del dominio a partir de evidencia F9.
> **No implementa:** F11 (selección adaptativa), F12 (tutor), F13, F16.

## 1. Student Model

```text
Student  Knowledge Domain (jerarquía D7: subject → topic → concept)
Evidence (F9 AttemptEvidence, verificado)  Observation (deltas Beta)
Mastery State (Beta por concepto / tema / asignatura)
```

F10 **no vuelve a corregir**: consume veredictos F9 ya producidos.
F10 **no crea taxonomía**: concepto/tema/asignatura provienen de la
jerarquía D7 (IDs `concept:`/`topic:`/`subject:` ya existentes).

## 2. Modelo probabilístico (F10-MASTERY, Beta-Binomial conjugado)

- Unidad: `(student, concept)` → `Beta(alpha, beta)` con aritmética
  `Decimal` (precisión 28, sin floats, sin NaN/Infinity — rechazados).
- Observación: correcta `alpha += w`; incorrecta `beta += w`;
  `needs_review`/omitida → `no_update`. `w` = 1 por defecto (masa de
  evidencia contractual; F9 no provee pesos por observación), **repartida
  a partes exactas** entre los conceptos de la pregunta
  (`split_weight`, precisión de pesos configurable 1..12).
- `P(mastery) = alpha / (alpha + beta)`. Incertidumbre fundada: varianza
  Beta (no una `confidence` inventada).
- Multi-concepto: `w / n_concepts` por concepto (nunca se duplica la
  evidencia: la masa total se conserva).
- Sin LLM, sin redes neuronales, sin random: totalmente determinista.

## 3. Evidencia F9 → Observation

- Mapping `Question → concept`: `ItemEvidence.concepts[]` (del snapshot
  D7) + fallback `knowledge_refs[concept]`. Sin concepto → `no_update`
  (nunca se inventa asociación). Concepto desconocido → `AC-ACD-002`.
- Item omitido / sin veredicto (`omitted`, `needs_review`) → `no_update`.
- Cada observación guarda: student/session/item/concept/topic/subject,
  deltas, `question_digest`, `engine` (`f9-correct/1`) y digest propio
  (`f10-observation/1`).

## 4. Idempotencia

PK `(student, session, item, concept)` + `INSERT OR IGNORE`:

```text
apply(E1); apply(E1) == apply(E1)
```

Concurrente: el perdedor de la carrera INSERT es un no-op (test
doble-aplicación). Sin timestamps como mecanismo de dedup.

## 5. Reproducibilidad y rebuild

Todas las actualizaciones son sumas conmutativas →

```text
incremental update == rebuild from evidence (misma evidencia)
```

`rebuild(student)` re-plega `mastery_observations` en orden fijo
`(session, item, concept)` y reescribe concept/topic/subject (test
`test_rebuild_equals_incremental`). El orden de evidencia NO importa
(suma conmutativa); se fija solo para determinismo del log.

## 6. Versionado

- `model_version = f10-beta/1`; `config_version = 1` (prior Beta(1,1),
  precisión de pesos 6). Los estados históricos guardan su copia de
  configuración; cambiar el algoritmo exige nuevo model_version, nunca
  reinterpretación silenciosa.
- `state_digest` (`f10-state/1`) por estado; `observation_digest`
  (`f10-observation/1`) por evidencia.

## 7. Agregaciones (jerarquía real D7)

- **Concepto**: estado directo.
- **Tema**: `fold_deltas(topic_ref, observaciones del topic)` — la
  etiqueta del agregado es el `topic_id` del ítem F9 (D7 real).
- **Asignatura**: fold de todas las observaciones del subject.
- Los agregados son sumas conjugadas (equivalentes a pool de posteriores),
  no medias de probabilidades. `members_json` hace trazable cada
  agregado a sus conceptos.

## 8. Provenance y auditabilidad

Cadena: `F9 evidence → observation (obs_digest) → update → mastery
(state_digest)`. Cada estado responde: qué evidencia (sesión/ítem/
concepto), qué versiones (model/config), qué preguntas (question_digest),
qué motor (`f9-correct/1`), qué jerarquía (topic/subject). Sin IA en la
explicación del cálculo.

## 9. Invariantes matemáticos

`0 ≤ P(mastery) ≤ 1` siempre (alpha,beta ≥ 0, masa > 0). NaN/Infinity
rechazados en dominio y en lectura de estados corruptos (test con
`alpha='NaN'` → error estructurado). Evidencia inexistente no se
fabrica: `apply_evidence` exige `AttemptEvidence` verificado.

## 10. Persistencia (018 justificada, §19)

`018_f10_mastery.sql` (aditiva): `mastery_states(student, level, ref)`
con `members_json` (agregados trazables) y
`mastery_observations` append-only (PK = idempotencia). Necesidad:
maestro durable de evidencia direccionable; ninguna tabla 001..017
sirve (study_concepts es SRS, no evidencia de evaluación). Reutiliza
`Database`, `_Base._tx` + `cx`, JSON canónico `_j`. Pins `17 → 18`.

## 11. Transacciones y atomicidad

`apply_evidence`: validate (plan) → posterior → persist observation +
states en UN `unit_of_work`; fallo → `ROLLBACK` total (test con fallo
inyectado a mitad: cero estados). Rebuild: delete+reescribe en una tx.

## 12. Determinismo y seguridad

Mismo input + mismo modelo/config → mismo estado (test cross-fixture).
Sin reloj (timestamps 0/inyectables, fuera de digests), sin random, sin
locale, sin red, sin LLM. `correct_answer` jamás importado en F10
(test lo fija). AST sin `eval/exec/compile/__import__/shell=True`;
imports ⊆ `{__future__, decimal, hashlib, json, academic_core}`.

## 13. API (§22)

```text
apply_evidence(evidence) → {applied, digests}
get_mastery(student, concept) → ConceptState | None
get_topic_mastery(student, topic) → AggregateView | None
get_subject_mastery(student, subject) → AggregateView | None
rebuild(student) → {concepts}
```

## 14. Contrato para F11

F11 consumirá `get_mastery/get_topic/get_subject` + `AggregateView`
(ref, level, state, members) y los digests. NO implementa:
selección de preguntas, next-best-action, rutas, dificultad adaptativa,
scheduling, spaced repetition, recomendaciones.

## 15. Errores (taxonomía existente)

| Situación | Código |
|---|---|
| evidencia no verificada (tamper) | `AC-ACD-003` |
| concepto desconocido / sesión inexistente | `AC-ACD-002` |
| config/model inválido | `AC-DOM-001` / `AC-ACD-004` |
| estado corrupto (NaN) | error estructurado en lectura |

## 16. Límites / no-objetivos

F11–F13, F16; segundo Knowledge Core/provenance/IDs/versionado;
re-corrección; pesos arbitrarios sin contrato; LLM; scheduling;
modificar D6/D7/F9 salvo defecto demostrado con regresión de la fase.
