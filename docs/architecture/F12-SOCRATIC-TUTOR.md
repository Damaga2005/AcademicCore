# F12 — Tutor Socrático (IA con Guardrails)

> **Fase:** F12 — asistencia LLM sobre F9/F10/F11, autoridad determinista.
> **No implementa:** F13 (cloud sync), F16 (aeroespacial).
> **Axioma:** `LLM = asistencia | Validator = control | Solver = autoridad | Verification = verdad académica`.

## 1. Arquitectura

```text
LLM proposal (JSON)
      ↓
Schema/type/size validator (domain.tutor.parse_proposal)
      ↓
Policy validator (domain.tutor.enforce_policy — socratic ladder)
      ↓
Solver reutilizado: domain.correction.correct_answer (F9, 7 qtypes)
      ↓
Verification (verdict.is_correct → verified/unverified/rejected)
      ↓
VerifiedResponse
```

**El LLM nunca es autoridad final.** No crea un segundo motor de
corrección: `verify_claims` llama exactamente al mismo `correct_answer`
que F9 usa para calificar a un estudiante — un `Claim` se corrige como
si fuera una respuesta más.

## 2. Módulos

| Módulo | Rol |
|---|---|
| `domain/tutor.py` | Puro: schema (`TutorProposal`), `Claim`, ladder socrático, validador, verificación de claims, `VerifiedResponse`. |
| `infrastructure/llm.py` | `LLMProvider` (protocolo), `LLMRequest`/`LLMResponse`, `NullProvider` (LLM=OFF), `OllamaProvider` (adapta `engines.ai.OllamaBackend`, sin dependencia nueva). |
| `application/tutor.py` | `TutorService`: orquesta, nunca autoriza. Construye contexto ya resuelto por el llamador (no recalcula F9/F10/F11), llama al provider, valida, persiste. |

## 3. Schema (`f12-tutor-response/1`)

Campos cerrados: `schema_version`, `response_type` (uno de
`hint, question, explanation, verification_request,
correction_guidance, refusal`), `message` (≤2000 chars), `steps`
(≤20 × ≤500 chars, opcional), `claims` (≤10, opcional). Campo
desconocido, tipo incorrecto, campo obligatorio ausente o tamaño
excesivo → rechazo inmediato (`parse_proposal` lanza `DomainError`); el
JSON no se interpreta parcialmente.

## 4. Claims

Un `Claim` tiene `claim_type` (solo `"final_answer"` en esta fase),
`qtype` (uno de los 7 D6), `answer` (con la forma exacta que
`correct_answer` espera para ese qtype) y `verification_required`
(default `True`). `verify_claims` llama `correct_answer(question,
claim.answer)`:

| `Verdict.is_correct` | Estado del claim |
|---|---|
| `True` | `verified` |
| `False` | `rejected` |
| `None` (needs_review: `structured`/`circuit` sin contenido esperado) | `unverified` |

El peor estado entre todos los claims decide el estado de la
respuesta completa. Una respuesta sin claims (una pregunta socrática
pura) es trivialmente `verified`.

## 5. Autoridad — reglas obligatorias verificadas por test

```text
LLM dice X + solver prueba Y → resultado final = Y (rejected si X≠Y)
LLM asume verificado + solver no puede decidir → unverified (nunca verified)
JSON inválido → rejected inmediato
LLM no disponible → estado estructurado, nunca respuesta inventada
```

## 6. Política socrática (ladder)

```text
question → hint → smaller_hint → targeted_question
  → partial_explanation → full_solution
```

La etapa se deriva del número de turnos previos para ese
`(student_id, question_digest)` (`policy_stage`, sobre
`TutorRepository.turn_count`) — no existe un store de estado de
política separado. Un claim `final_answer` antes de
`partial_explanation` se rechaza (`AC-TUT-004`,
`enforce_policy`), nunca se revela la solución completa fuera de
etapa.

## 7. Contexto (minimización)

`TutorService.get_response` recibe el contexto **ya resuelto** por el
llamador: `attempt_evidence` (F9), `mastery_snapshot` (F10),
`adaptive_plan` (F11). F12 nunca vuelve a corregir, nunca recalcula
mastery, nunca regenera el Adaptive Plan — solo lee lo que ya existe.
El prompt separa `system_policy | context | task`; nada del contenido
no confiable (pregunta, respuesta del estudiante, texto recuperado) se
concatena con la política privilegiada.

## 8. LLM=OFF y fallos del proveedor

`NullProvider.metadata().available == False` → `TutorService` nunca
llama a `generate()`; construye una `VerifiedResponse` estática y
verificada (`status="verified"`, `provider_error="LLM_UNAVAILABLE"`) a
partir de la evidencia F9 disponible (p. ej. el motivo del intento
anterior). Un fallo de un proveedor normalmente disponible (timeout,
error de red, JSON roto) produce el mismo tipo de respuesta segura con
`provider_error` = `LLM_TIMEOUT` / `PROVIDER_ERROR`. Nunca se inventa
contenido para ocultar la ausencia del proveedor.

## 9. Herramientas / seguridad

El LLM no tiene acceso a filesystem, shell, red ni base de datos: solo
emite JSON. La aplicación decide si invoca un solver — el LLM no llama
herramientas directamente, lo que colapsa el problema de "tool
allowlist" a "no hay herramientas". Contenido no confiable (pregunta,
respuesta, texto recuperado) vive en `context`, nunca se concatena con
`system_policy`; nada que el LLM emita puede cambiar validador, schema,
solver ni autoridad — solo el contenido de sus propios campos. Sin
`eval`/`exec`/`compile` en ningún módulo F12 (test de seguridad).

## 10. Persistencia (`020_f12_tutor.sql`, aditiva)

`tutor_turns(turn_id PK, student_id, question_digest, turn_index,
response_type, status, solver_version, schema_version, provider_name,
provider_model, provider_error, created_at_ms)`. Solo la respuesta
verificada + referencias de provenance — **nunca** el texto crudo del
LLM ni la propuesta intermedia (decisión explícita: auditar "qué pasó y
por qué", no guardar la conversación completa). Append-only vía
trigger (`trg_tutor_turns_immutable`), igual que `assessment_evidence`
(017). `turn_id` es un digest determinista (`f12-tutor-turn/1`) —
idempotente ante reintento.

## 11. Provenance

Reconstruible: `student request → question_digest → attempt_evidence/
mastery_snapshot/adaptive_plan (referencias, no copias) → provider/model
→ schema_version → solver_version (f9-correct/1) → status`. Sin
secretos almacenados (no hay API keys en esta fase: proveedor local
Ollama o `NullProvider`).

## 12. Errores (nuevo área `TUT`)

| Código | Situación |
|---|---|
| `AC-TUT-001` | JSON no parseable |
| `AC-TUT-002` | schema inválido |
| `AC-TUT-003` | claim no verificable / rechazado por el solver |
| `AC-TUT-004` | política rechaza (revelación socrática prematura) |
| `AC-TUT-005` | LLM no disponible (LLM=OFF o sin proveedor) |
| `AC-TUT-006` | error de proveedor / timeout |

## 13. Proveedor (`infrastructure/llm.py`)

`LLMProvider` (protocolo estructural): `generate(request) ->
LLMResponse`, `metadata() -> ProviderMetadata`. `OllamaProvider` adapta
`engines.ai.OllamaBackend` existente (mismo transporte HTTP stdlib,
ahora con `timeout` configurable por request; cero reintentos
automáticos). `NullProvider` es LLM=OFF puro, determinista, sin red. El
dominio académico no conoce ningún proveedor concreto ni ningún nombre
de modelo.

**Fuera de alcance en esta fase (decisión documentada):** un backend
Anthropic/OpenAI concreto no se implementa — requeriría manejo de API
keys, egress de red y control de coste/rate-limit que no existen hoy en
el repositorio. La interfaz `LLMProvider` ya permite añadir uno
después sin tocar el dominio académico.

## 14. Determinismo y no-duplicación

Sin reloj dentro de los digests (`created_at_ms` inyectable, fuera de
`turn_digest`). Sin random. `verify_claims` no importa nada de
`domain/execution` ni `domain/engineering` directamente: delega
siempre en `correct_answer` (F9), que ya despacha los 7 qtypes —
ningún segundo motor matemático/simbólico/de unidades/circuitos.

## 15. Límites / no-objetivos

F13, F16; segundo Knowledge Core/Question Bank/Evaluation
Engine/Student Model/Adaptive Engine/solver; proveedor Anthropic/OpenAI
concreto (ver §13); acceso a herramientas por el LLM; reintentos
automáticos; rate limiting (proveedor local single-user).
