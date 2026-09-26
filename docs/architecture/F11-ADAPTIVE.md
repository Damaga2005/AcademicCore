# F11 — Aprendizaje Adaptativo

> **Fase:** F11 — motor adaptativo determinista sobre mastery F10.
> **No implementa:** F12 (tutor), F13, F16.

## 1. Adaptive Engine

```text
Student Model (F10) + Knowledge Graph (D7) + Question Bank (D6)
  + Adaptive Configuration + Learning Context
  → Adaptive Plan
```

Pipeline: `eligible → filter → score → rank → constraints → route`.
**LLM=OFF**: sin imports de IA, sin LLM como autoridad de selección,
orden, puntuación, prioridades, restricciones ni ruta. La extensión
futura `AdaptiveEnhancer` (no implementada) pasaría output de LLM por
`validación → constraints deterministas → accept/reject`; nunca
`LLM → decisión final`.

## 2. Elegibilidad (§6)

Solo filtros contractuales. Un candidato no elegible **nunca** aparece
por fallo de ranking:

| Filtro | Fuente | Efecto |
|---|---|---|
| subject | snapshot D6 (`concepts[]` → subject) | excluye de otros subjects |
| topic | etiqueta del contexto (ver §4) | el sujeto delimita; topic-level no existe en snapshot D6 |
| concept | `concepts[]` | filtro exacto si el contexto lo pide |
| type | D6 `qtype` | restringe a `allowed_types` |
| difficulty | D6 `difficulty` | `unspecified` excluida salvo config explícita; rango min/max |
| availability | store D7 | la pregunta debe existir ingestada |
| prerequisites | D7 `prerequisites_of(subject)` (subject-level, único tipo) | subject con prerequisito sin evidencia F10 → nada elegible |
| history | F10 `mastery_observations` | `exclude_done` (default) excluye preguntas ya realizadas |

Sin candidatos → `NO_ELIGIBLE_EXERCISES` (plan vacío estructurado,
nunca plan falso).

## 3. Mastery (§7)

Usa el mastery real de F10 (probabilidad del concepto del estado
`concept`); **no lo recalcula**. Política explícita y versionada:
`P < 0.40 → LOW_MASTERY` (prioridad alta), `P ≥ 0.70 → target hard`,
resto medium. Sin evidencia → `UNMAPPED` (cuenta como necesidad, nunca
como dominio cero).

## 4. Difficulty (§8)

`difficulty_fit` determinista: target según mastery (easy/medium/hard);
fit = 1 exacto, 0.5 un paso, 0 fuera. `unspecified` excluida por defecto
(configurable). Sin escala inventada.

## 5. Historial y repetición (§10)

- `exclude_done` (default): pregunta ya observada en F10 no se repite.
- `max_per_concept` (default 2): cap por concepto en la ruta.
- `RECENT_ERROR`: concepto con observación incorrecta → boost en scoring.
- Sin planes Q1,Q1,Q1,Q1 salvo config explícita.

## 6. Adaptive Score (§11) — fórmula versionada

```text
score = mastery_weight(60) × (1 − P)
      + difficulty_weight(20) × difficulty_fit
      + relevance_weight(15) × |conceptos con estado F10| / |conceptos|
      + diversity_weight(5) × 0        # diversidad se aplica en route
      − repetition (exclusión, no descuento)
```

Pesos configurables y versionados (`AdaptiveConfig`, config v1). Sin
factores sin contrato. Determinista, testeable.

## 7. Desempate (§12)

```text
adaptive_score DESC, question_id ASC, content_version ASC
```

IDs estables reales; nunca orden accidental de BD.

## 8. Learning Route (§13)

`AdaptivePlan`: student_id, selections (en orden de ruta), rationale
codes cerrados (`LOW_MASTERY`, `DIFFICULTY_FIT`, `CONCEPT_RELEVANCE`,
`RECENT_ERROR`, `PREREQUISITE_OK`, `PREREQUISITE_UNMET`,
`REPETITION_AVOIDED`, `DIVERSITY`, `UNMAPPED`,
`NO_ELIGIBLE_EXERCISES`), config_version, model_version, bank_digest,
mastery_snapshot. Cada selección explica sus códigos; nada ficticio.

## 9. Versionado y snapshot (§17)

`plan_digest` (`f11-adaptive-plan/1`) cubre student + banco exacto
(`bank_digest` sobre el set de preguntas usado) + config + mastery
snapshot + selección. Un cambio posterior del banco no altera un plan
histórico (su digest queda firme).

## 10. Idempotencia (§18)

Mismo input → mismo `plan_id` (= `plan_digest`). Persistencia
`INSERT OR REPLACE`: regenerar no duplica.

## 11. Persistencia (§21)

`019_f11_adaptive.sql` (aditiva): `adaptive_plans(plan_id PK,
student_id, subject_id, config_version, model_version, bank_digest,
selections_json, rationale_json, mastery_snapshot_json, context_json,
plan_digest, created_at_ms)`. Reutiliza `MasteryRepository` (mismo
store) + `Database`/`_j`. Nada redundante: el plan referencia
versiones, no duplica ni mastery ni preguntas.

## 12. Determinismo y seguridad

Mismo mastery + mismo banco + misma config + mismo contexto → mismo
plan (test cross-fixture). Sin reloj (created_at_ms=0/inyectable, fuera
de digests), sin random (test: no `import random`), sin red, sin LLM.
Contenido nunca ejecutado (AST); imports ⊆ `{__future__, decimal,
hashlib, json, academic_core}`. `correct_answer` no importado (F11 no
vuelve a corregir).

## 13. Errores (taxonomía existente)

| Situación | Código |
|---|---|
| subject/contexto inválido, config inválida | `AC-DOM-001` / `AC-ACD-004` |
| estado F10 corrupto (NaN) | `AC-ACD-004` |
| canonical_json corrupto | `AC-ACD-004` |

## 14. Contrato para F12

F12 consumirá `AdaptivePlan` (selecciones ordenadas + rationale) y el
motor como autoridad de qué practicar. NO implementa: tutor
conversacional, LLM, explicación generativa, diálogo adaptativo.

## 15. Límites / no-objetivos

F12–F13, F16; segundo Student Model/Knowledge Core/Question Bank/
Evaluation Engine/Adaptive Engine; LLM como autoridad; scheduling
sistemático (spaced repetition es futura); prerequisitos por
concepto/tema (no existen en D7); topic fino por pregunta (no en el
snapshot D6).
