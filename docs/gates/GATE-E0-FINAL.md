# GATE E0 — Explainable Execution / Pedagogical Trace — FINAL

Design: [GATE-E0-DESIGN.md](GATE-E0-DESIGN.md).

```text
E0 FINAL REPORT
```

## Baseline

- Starting point: `0cf3554e74113349b34d13b9544220856d8bf9e3` (F8-Q
  certified), with `HEAD == origin/main` and a clean tree.
- Before E0: `fdb85c8` `fix(ui): repair Virtual Lab Add + Run`.
  - It fixed a pre-existing F15 widget defect found during the F8-Q
    audit: a missing import, plus a second defect that the first one had
    been hiding.
  - It added `tests/test_f15_virtual_lab_ui.py`, 6 tests that click the
    real button through the worker for OP, DC_SWEEP, TRANSIENT, AC_POINT
    and AC_SWEEP, plus replay.

## Architecture

```text
Input ─▶ Resolver (certified engine) ─▶ TraceRecorder ─▶ ExecutionTrace (frozen)
                                                         ├─▶ execution-trace/1 ─▶ Replay (re-run) ─▶ compare/digest
                                                         └─▶ ExplanationView ─▶ text / Markdown / UI
UI ─▶ AcademicApp.explain (ExplainService) ─▶ domain/execution integrations ─▶ engines
```

- **Core** (`domain/execution/{model,codec,replay}.py`): stdlib and
  `academic_core.errors` only.
- **Integrations** (`execution/equation.py`, `execution/digital.py`)
  import the engines.
- **No cycles.** Engines never import E0 (AST test `test_e0_x02`).
- **Renderer** (`application/explain_render.py`): imports the core only;
  it renders and never solves.
- **Service** (`application/explain_service.py`): no Qt.
- **UI:** the Exercises panel has an **Explicar** button that shows
  service-rendered text. The widget has no pedagogy and no domain
  imports.
- **D1/D2/D3:** no new layer, error system, unit system, replay engine
  or dependency.

## ExecutionTrace

- **Fields:** `schema` / `version` / `operation` / `inputs` / `events`
  / `result` / `outcome` / `verification` / `metadata`.
- **Frozen dataclasses and tuples,** validated on every construction
  and every decode.
- **Invariants:**
  - `SUCCESS` means exactly one RESULT and no ERROR; `FAILED` means an
    ERROR with no result.
  - `result` equals the RESULT event.
  - Every input has exactly one INPUT event that agrees with it.
  - `verification` equals the summary derived from the CHECK events.

## Event model

- **Kinds:** `INPUT`, `NORMALIZATION`, `VALUE`, `STEP`, `DECISION`,
  `CHECK`, `RESULT`, `WARNING`, `ERROR`. Each one is produced by a real
  run (`test_e0_k01`).
- **Event fields:** id, kind, title, refs, formula, why, values, result,
  check, error.
- **Ids:** `e1…eN` in emission order.
- **`refs`:** earlier events only (a causal DAG). Variable reads
  *reference* their NORMALIZATION event and are not copied.
- **Navigation:** `event(id)` and `consumers(id)` answer who produced a
  value, who consumed it, and which check verified the result
  (`test_e0_c01`).

## Determinism

- The same inputs give the same trace and the same JSON, independent of
  input dict order (`test_e0_d01`).
- Four interpreter processes with `PYTHONHASHSEED` 0 / 1 / 777 / random
  give identical digests for an equation trace and an F8-Q trace
  (`test_e0_d02`).
- **Nothing environmental is recorded:** no wall clock (`calc.calculate`
  gets a fixed `at=`), PID, memory, `id()`/`hash()`, thread id, path or
  environment.
- **Metadata** is diagnostic only and excluded from the digest
  (`test_e0_h01`).

## Units

- Values are recorded exactly as the engine produced them.
  `TraceValue.of_quantity` stores `Quantity.value` (exact Decimal),
  `Unit.display` and the 7 SI exponents.
- Full engine precision is kept, e.g. 1 V / 3 Ω with 28 digits, equal to
  `calc.calculate` (`test_e0_u01`).
- On the wire, numbers are canonical decimal strings, so `2.50`, `2.5`
  and `25E-1` share one spelling (`test_e0_u02`).
- There are no floats anywhere; this is checked recursively on
  `to_dict`.

## Formulas

- Formulas are **data**: the token span of the parsed source (`R1 + R2`,
  `Vi * R2 / (R1 + R2)`, `exp(B * (1 / T - 1 / T0))`).
- They are never executed. A malicious formula or title is shown as text
  (Markdown-escaped), and `eval` / `exec` / `compile` are never called
  (`test_e0_v02`).

## Checks

- **Structure:** what / actual / expected / tolerance / status (PASS,
  FAIL, NOT_APPLICABLE) / detail.
- **Engineering checks:**
  - result dimension against the library's declared dimension
    (consistency of units)
  - equality with the certified `calc.calculate`
- **F8-Q checks:**
  - Q4 `verify_replay` of the capture
  - JSON round-trip digest equality
  - `verify_capture`
  - truth-table consistency per observed gate (`NOT_APPLICABLE`, with
    the reason, when an input is unobserved)
- **A failed check is never hidden.** It stays visible (`FAIL: …` in the
  explanation), and editing `verification` to hide it is rejected
  (`test_e0_k02`).

## Errors

- **D2 only.**
  - `ValidationError` AC-VAL-001 for an invalid trace.
  - `SerializationError` AC-SER-001 for the JSON layer and size.
  - `VersionMismatchError` AC-VER-001 for the version.
  - `IntegrationError` AC-INT-001 for `REPLAY_MISMATCH`.
- **A failed execution still yields a trace** with outcome FAILED. Its
  ERROR event keeps the engine's code: AC-VAL-001 for
  `UnitError`/`EquationError`/`UNKNOWN_PROBE`, AC-DOM-001 for
  `EVENT_LIMIT`.
- **The ERROR says where execution stopped**: its `refs` are the values
  that were ready.
- **Messages are UI-safe:** absolute paths and control characters are
  removed, and length is bounded (`test_e0_e01`, `test_e0_e02`).

## Serialization

`execution-trace/1` follows the Q4 conventions but is its own schema:

- canonical JSON with sorted keys, compact, ASCII-escaped, no NaN, no
  trailing newline
- strict decoding: closed key sets at every level, enumerated kinds and
  statuses, canonical number strings only
- duplicate keys, floats, `NaN` / `Infinity`, huge integers and BOM are
  rejected, and so are unknown schema and version (`test_e0_s01`–`s03`)

## Digest

`sha256(canonical JSON of the document without "metadata")`.

- **Included:** schema, version, operation, inputs, every event field in
  order, result, outcome, verification.
- **Excluded:** metadata, and anything that is not in the document.
- Any change to a value, unit, title, `why` or order changes the digest
  (`test_e0_h01`).
- A golden fixture is pinned (`tests/fixtures/execution_trace/voltage_divider.json`,
  `57ec3ab4…60c7`).

## Replay

- **Re-execution.** The real resolver is re-run from the recorded inputs:
  - `equation.replay_equation`
  - `digital.replay_capture` with a fresh demo circuit supplied by the
    application
- **Verdicts.** `compare` returns `EQUIVALENT` or `RESULT_DIFFERS` with
  the first difference path:
  - a changed value: `events[9].result`
  - a changed unit: `events[10].result`
  - changed text
  - a changed input, recomputed from the new input:
    `events[8].result`
  - a lost event: `events (count 14 != 15)`
- **Rejected at decode:** reordering (`INVALID_ORDER`) and an unknown
  schema or version (`test_e0_r01`–`r03`).
- **Application.** `ExplainService.replay` has a fixed registry and
  refuses unknown operations (`UNSUPPORTED_OPERATION`).

## Renderers

- `build_view(trace)` returns a frozen `ExplanationView`: seven sections
  plus `StepView`s (with the values each step consumed, resolved from
  refs) and `CheckView`s.
- `render_text` and `render_markdown` format that view. The Markdown
  output escapes recorded text.
- The seven sections are the pedagogical questions: ¿Qué recibimos? /
  ¿Qué hicimos? / ¿Por qué? / ¿Qué fórmula usamos? / ¿Qué valores
  intermedios obtuvimos? / ¿Qué comprobamos? / ¿Qué resultado
  obtuvimos?
- It is proven not to recompute: it is tested with `evaluate` and
  `calculate` patched to raise.
- It never mutates the trace (`test_e0_v01`).

## Engineering/math integration

- `explain_equation(inputs, source, expected_dimension)` runs the
  certified resolver: `parse_equation` → `parse_quantity` →
  `equations.evaluate`, through a new **optional observer hook**.
  - With `observer=None` behaviour is identical: all existing equation,
    calc and GUM tests pass unchanged.
  - The hook reports every read and operation in real order with the
    engine's own Quantity (`test_e0_i02`).
- All 15 library equations trace, give the certified result exactly,
  PASS their checks, and replay EQUIVALENT (`test_e0_i01`).
- The "data not used" warning comes from the evaluator's real reads.

## F8-Q integration

- `explain_capture(circuit, config)` calls the certified
  `LogicAnalyzer.capture` exactly once. A counting patch verifies this;
  there is no second simulator.
- It records:
  - the declared circuit
  - the simulation window and transition counts
  - every captured transition (same-time rank `k/n`), attributed to its
    driving gate or stimulus
  - the trigger decision, referencing the exact firing transition
  - the result digest, which equals `CaptureResult.trace.digest()`
  - the checks listed above
- `NOT_TRIGGERED` is a successful result.
- Large captures are bounded, and the rest is stated in a WARNING
  (`test_e0_q01`, `q02`, `l02`).
- **No F8-Q file was modified** (`test_e0_q03` diffs `digital/` against
  `0cf3554`).

## Security

- **E0 modules and `equations.py`:** no `eval` / `exec` / `compile` /
  `__import__` / `getattr` / `setattr` calls, and no pickle, marshal,
  subprocess, importlib, pkgutil, ctypes, `shell=True` or `os.system`
  (`test_e0_x01`).
- **The E0 domain** imports no Qt, UI, application, infrastructure,
  logging, clock, RNG, os, sys, io or pathlib (`test_e0_x02`).
- **Malicious traces are only data** (`test_e0_v02`).
- **F15-017** (repo-wide AST) still passes.
- **Audit of the E0 diff** for TODO / FIXME / `pass` / NotImplemented /
  print / eval / exec / pickle / marshal / subprocess / os.system /
  importlib found nothing in `src`. The only matches were a docstring
  sentence stating their absence, test `subprocess` calls (argv lists,
  no shell) for the determinism child processes and a `git diff`, a
  child-script `print`, and the AST policy lists.

## Bounds

| Limit | Value |
|:---|:---|
| events | 10 000 |
| inputs | 256 |
| refs per event | 64 |
| values per event | 64 |
| strings / formulas | 512 |
| names | ≤ 96 |
| units | 64 |
| metadata | 32 |
| number | 200 digits + exponent |
| JSON document | 8 MiB, depth 7, 2·10⁶ values, integers ≤ 12 digits |
| F8-Q detail | 512 transitions, 96 described circuit elements, 64 truth-table checks |

Exceeding any limit raises a controlled D2 `TRACE_LIMIT`
(`test_e0_l01`, `l02`, `m05`).

## Tests

- **E0:** `tests/test_e0_execution_trace.py`, 71 tests: model and
  immutability, validation, event kinds, causality and references,
  formulas, Decimal/Quantity/Unit, checks, D2 errors, determinism
  (4 processes), round trip and canonical JSON, 20 malformed documents,
  versions, duplicate keys, float, NaN, Infinity, limits, digest,
  tampering, replay, renderer, no mutation, 15 library equations,
  observer, F8-Q integration, application service, UI button,
  AST/security, 80 LCG property cases, golden fixture.
- **Virtual Lab fix:** `tests/test_f15_virtual_lab_ui.py`, 6 tests.
- **Properties:** Hypothesis is not a project dependency, so the
  properties use the repository's LCG pattern (round trip, digest
  stability, ordering, refs, replay, result = engine).

## Full regression

One full run on the E0 tree, `pytest -o addopts="" -q`, offscreen Qt.
The per-group counts come from its JUnit report.

| Group | Passed |
|:---|---:|
| F8-Q.1 / Q.2 / Q.2R / Q.3R | 85 / 70 / 43 / 99 |
| F8-Q.4 / Q.5 / Q.6 / Q.7 | 144 / 87 / 37 / 12 |
| F8-N | 125 |
| F8-P1 / P2 / P3 / P4 / P5 | 51 / 34 / 52 / 40 / 44 |
| F15 (incl. Virtual Lab widget) | 33 |
| architecture / AST / domain / engineering security | 13 / 5 / 4 / 5 |
| UI (`test_ui*`) | 7 |
| **E0** | **71** |
| **Full suite** | **3088 passed, 0 failed, 134 skipped** |

- The 134 skips are the same environment-only set as the F8-Q baseline:
  the ngspice runtime, the Windows-only reference converter, and
  live-tool bootstraps.
- There are no xfails and no collection errors.
- No test was weakened, skipped or deleted.

## Known limitations

1. **Explained resolvers.** Two resolvers are explained so far: the
   engineering equation resolver and the F8-Q capture. Other engines
   (F8-N MNA / transient, F8-P, GUM) can adopt E0 by adding an
   integration. The core needs no change for that, but their traces are
   not produced yet.
2. **F8-Q replay needs a circuit factory.** A `DigitalCircuit` is not
   serializable (`digital-circuit/1` is future work), so the F8-Q trace
   replays through the application's demo key. The domain API takes any
   circuit factory.
3. **Evaluation order is the engine's.** Engineering explanations show
   the engine's own evaluation order and units. Intermediate products
   can therefore carry the engine's `derived` unit label (e.g.
   `Vi * R2 = 24000 derived`), because that is what the engine computed;
   no prettified values are invented.
4. **F8-Q explanations** list the facts of the captured window. A gate's
   inner reduction is not decomposed; the truth-table check verifies
   each observed gate against its certified function instead.
5. **Rendering and UI.** The renderer's section headings are in Spanish
   (the pedagogical audience); the view model is language-neutral data.
   The UI integration is the Exercises **Explicar** button. The Logic
   Analyzer tab does not show explanations yet, but the service method
   exists.

## Final commit

- E0 implementation: `7fc04b76174f6594403a2c9bd20de8b7a5490e61`
  (`feat(core): add explainable execution trace (E0)`).
- Certification: the commit that adds this document,
  `cert: certify E0 explainable execution`.

## origin/main

`HEAD == origin/main` after each push. This was verified with
`git fetch` and `git rev-parse` for `fdb85c8` and `7fc04b7`, and again
for the certification commit.

## Final verdict

```text
E0 COMPLETE / CERTIFIED
```
