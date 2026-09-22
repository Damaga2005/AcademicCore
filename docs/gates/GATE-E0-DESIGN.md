# GATE E0 — Explainable Execution / Pedagogical Trace (design)

Roadmap: 15b, transversal, after F8-Q
([ROADMAP.md](../roadmap/ROADMAP.md)).

- Baseline: `0cf3554e74113349b34d13b9544220856d8bf9e3` (F8-Q certified).
- The Virtual Lab fix `fdb85c8` landed before E0 work started.

Principle: **the explanation is not a second solution.** The real solver
produces a trace, and the explanation only renders that trace.

## 1. Audit (what exists, what is reused)

| Area | Found | E0 decision |
|:---|:---|:---|
| D1 layers | `ui → application (AcademicApp facade, services) → domain / ports ← infrastructure` | E0 core in `domain/execution/`; renderer and service in `application/`; one UI button. No new layer. |
| D2 errors | `AcademicCoreError(ValueError)` root, `AC-<AREA>-<NNN>`, single `to_ui_error` | Reused. Invalid traces raise `ValidationError`, the JSON layer `SerializationError`, the version `VersionMismatchError`, and a replay mismatch `IntegrationError`. Traced failures keep the engine's own D2 code. No new codes. |
| D3 | MIT, no new dependency | stdlib only. SPDX headers. `pyproject`/`requirements` unchanged. |
| Units | `units.Quantity` (Decimal value in the stated unit), `Unit.display`, 7-exponent SI dimension | `TraceValue.of_quantity` stores exactly these. No second unit system. |
| Equation resolver | `equations.parse_equation` (own parser, no eval) + `_Eval` recursive descent + `calc.calculate` (certified entry) | Integration target #1. A new **optional observer hook** in `_Eval` exposes the real evaluation order (`None` by default = unchanged behaviour). |
| F8-Q | `LogicAnalyzer.capture` / `CaptureResult` / Q4 `verify_replay` / `verify_capture` | Integration target #2. It calls the certified path exactly once. **No F8-Q file is modified.** |
| Serialization | Q4 `digital-trace/1` conventions (canonical JSON, strict decode, limits) | Same conventions, **new** schema `execution-trace/1`. The digital schema is never reused. |
| Replay | F8-N/F8-Q `EQUIVALENT / RESULT_DIFFERS` | Same vocabulary. Replay re-runs the real resolver, so there is no second replay engine. |
| F15 | worker, `show_ui_error`, panels | `app.explain` service. The exercises panel gets an "Explicar" button that shows service-rendered text. |

## 2. Architecture and dependency direction

```text
Input ─▶ Resolver (certified engine) ─▶ TraceRecorder ─▶ ExecutionTrace (frozen)
                                                         ├─▶ codec: execution-trace/1 ─▶ replay (re-run) ─▶ compare / digest
                                                         └─▶ application.explain_render ─▶ ExplanationView ─▶ text / Markdown / UI
```

| Module | Imports | Imported by |
|:---|:---|:---|
| `domain/execution/{model,codec,replay}.py` (core) | stdlib, `academic_core.errors` | integrations, application |
| `domain/execution/equation.py` | core + `engineering.{equations,calc,units}` | application |
| `domain/execution/digital.py` | core + `engineering.digital` (public API) | application |
| `application/explain_render.py` | core only (it renders; it never solves) | service, tests |
| `application/explain_service.py` | integrations, renderer, `digital_service` | facade (`app.explain`), UI |
| `ui/exercises.py` | nothing new (uses `app.explain`) | — |

- **No cycles.** Engines never import `domain.execution`, and the core
  imports no engine. The one engine change is the observer hook, which
  is duck-typed and imports nothing.
- **The UI creates no execution facts.** The domain imports no Qt, UI or
  application code.
- These points are enforced by AST tests (`test_e0_x02`).

## 3. Model (`execution-trace/1`)

```text
ExecutionTrace
  schema "execution-trace" · version 1
  operation      "engineering.equation" | "digital.logic-analyzer" | …
  inputs         ((name, TraceValue), …)          replay inputs, emission order
  events         (TraceEvent e1 … eN)             emission order = causal order
  result         TraceValue | None                = the RESULT event's result
  outcome        SUCCESS | FAILED
  verification   {status PASS|FAIL|NONE, checks, failed}   derived from CHECK events
  metadata       ((key, text), …)                 diagnostic only — NOT digested
```

- **Event kinds** (only what the integrations need):
  - `INPUT`, `NORMALIZATION`, `VALUE`, `STEP`, `DECISION`
  - `CHECK`, `RESULT`, `WARNING`, `ERROR`
- **`TraceEvent` fields:**
  - `event_id`, `kind`, `title`
  - `refs` (earlier ids = causality)
  - `formula` (text) and `why` (reason)
  - `values` ((name, TraceValue)…) and `result`
  - `check` (`TraceCheck`: what / actual / expected / tolerance / status
    / detail) and `error` (`TraceError`: D2 code / reason token /
    UI-safe message)
- **`TraceValue`** is either an exact `Decimal` + unit symbol + SI
  dimension, or a text. It never holds a float.
- **Identity is deterministic.** Ids are `e1…eN` by position; there are
  no random ids, clocks, `id()` or `hash()`.

## 4. Causality and values

- **What happened first:** event order, enforced by the ids.
- **What produced a value:** that event's `refs`.
- **What consumed it:** `trace.consumers(id)`.
- **Which check verified the result:** the CHECK events that ref the
  RESULT.
- **References, not copies.** A variable read refs its NORMALIZATION
  event.
- **No cycles or forward references.** `refs` may only point to earlier
  events, so the graph is a DAG by construction. This is validated on
  every construction and every decode.
- **Values come from the engine.** Every intermediate value is the
  `Quantity` the engine computed, delivered through the observer or read
  from the engine's own result objects.

## 5. Formulas and units

- A formula is **text**: the token span of the parsed source (e.g.
  `R1 + R2`, `exp(B * (1 / T - 1 / T0))`). Nothing ever executes or
  evaluates it.
- The code base contains no `eval`, `exec` or `compile` (the F15-017 and
  E0 AST tests).
- Values keep full engine precision and unit (e.g. `3 kΩ` with SI
  exponents `(1,2,-3,-2,0,0,0)`).
- On the wire, numbers are canonical decimal strings: numerically equal
  values have one spelling.

## 6. Checks and errors

- **Checks.**
  - Structured; the status is PASS, FAIL or NOT_APPLICABLE (with the
    reason).
  - A failed check never makes the trace disappear. The `verification`
    summary is validated against the events, so editing it to hide a
    FAIL is rejected.
- **Errors.**
  - The trace is still produced, with outcome `FAILED`.
  - The ERROR event carries the engine's D2 code (`AC-VAL-001` for
    `UnitError`/`EquationError`, `AC-DOM-001` for `EVENT_LIMIT`, …), a
    reason token and a UI-safe message (paths and control characters
    removed, bounded).
  - Its `refs` are the values that were ready when execution stopped.

## 7. Determinism, digest, replay

- **Determinism.** The same inputs give the same trace (tested in-process
  and in 4 processes with different `PYTHONHASHSEED`). The engine never
  records wall clock, PIDs, memory, thread ids, paths or environment:
  `calc.calculate` gets a fixed `at=`, so it never reads the clock.
- **Digest.**
  - `sha256(canonical JSON without metadata)`.
  - Covered: schema, version, operation, inputs, all event fields in
    order, result, outcome, verification.
  - Excluded: metadata.
- **Replay.**
  - The integration's replayer re-runs the real resolver from the
    recorded inputs. For F8-Q the application supplies a fresh demo
    circuit from the recorded `demo` context.
  - `compare` returns `EQUIVALENT` or `RESULT_DIFFERS` with the first
    difference path. That covers a modified value or unit, a changed
    text, a changed input, and a lost or extra event.
  - Reordering is rejected when the trace is decoded, and an unknown
    schema or version is rejected there too.

## 8. Renderers

`application/explain_render.py` works in two steps. `build_view(trace)`
builds a frozen `ExplanationView`: sections, steps with their consumed
values, and checks. `render_text` / `render_markdown` then format it.

Each section answers one question:

1. ¿Qué recibimos?
2. ¿Qué hicimos?
3. ¿Por qué?
4. ¿Qué fórmula usamos?
5. ¿Qué valores intermedios obtuvimos?
6. ¿Qué comprobamos?
7. ¿Qué resultado obtuvimos?

The renderer only formats recorded data. It is tested with the engine
patched to raise, and it never mutates the trace. Markdown escapes
recorded text, so no HTML or links can be injected. CLI, HTML and UI can
all consume the same view model.

## 9. Limits

| Limit | Value |
|:---|:---|
| events | 10 000 |
| inputs | 256 |
| refs per event | 64 |
| values per event | 64 |
| strings / formulas | 512 characters |
| names | ≤ 96 characters |
| unit symbol | 64 |
| metadata | 32 entries |
| numbers | ≤ 200 digits + exponent |
| JSON document | 8 MiB, depth 7, 2·10⁶ values, integers ≤ 12 digits |
| F8-Q detail | 512 transitions, 96 described circuit elements, 64 truth-table checks (the rest is stated in a WARNING) |

Exceeding any limit raises a controlled D2 error: `TRACE_LIMIT`.

## 10. Verdict

The design is closed. No cycle is introduced, D1/D2/D3 are respected,
and F8-Q is untouched. Implementation and certification:
[GATE-E0-FINAL.md](GATE-E0-FINAL.md).

```text
E0 DESIGN READY
```
