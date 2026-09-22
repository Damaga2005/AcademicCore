# GATE F8-Q — Digital Engine (implementation log)

Design authority: [GATE-DIGITAL-ENGINE-DESIGN.md](GATE-DIGITAL-ENGINE-DESIGN.md)
(`FINAL VERDICT: DIGITAL ENGINE DESIGN READY`, commit `9a758b4`).
F8-Q is implemented in sub-phases; this file records each. **F8-Q is
NOT certified**; no sub-phase below claims it.

## F8-Q.1 — Digital core

Baseline `9a758b4`, branch `main`, clean tree. Scope: the deterministic
core only. No gates/components, stimuli, clock, sequential logic,
probes, trace, Logic Analyzer, UI, serialization/replay, F15
integration, mixed-signal, X/Z (all deferred to F8-Q.2+).

### Implemented scope

New package `src/academic_core/domain/engineering/digital/` (pure
domain, stdlib + `academic_core.errors` + `domain.entities.DomainError`
only). No existing file modified.

### API (`digital/core.py`, re-exported by `digital/__init__.py`)

| Name | Kind | Contract |
|:---|:---|:---|
| `LogicState` | `IntEnum` | `LOW=0`, `HIGH=1`; immutable, hashable, ordered; X/Z absent |
| `DigitalNet(net_id, name, state)` | frozen dataclass | validated id/name/state; `with_state()` returns a new net |
| `DigitalEvent(time, sequence, stable_id, net_id, state)` | frozen, ordered dataclass | `key = (time, sequence, stable_id)`; field order = sort order |
| `EventQueue(max_events)` | heap | `push / peek / pop / empty / size / len`; duplicate key refused; bounded |
| `DigitalCircuit(max_nets)` | registry | `add_net(id, initial, name?) / net / state / nets / states / apply` |
| `DigitalSimulator(circuit, max_events)` | scheduler | `schedule / step / run / now / processed`; sole sequence source |
| `check_time / check_state / check_id / check_sequence` | validators | raise D2 `ValidationError` |

### Models

- **Time**: `Decimal` seconds, finite, `0 ≤ t ≤ MAX_TIME`. `int` is
  converted exactly; `float`/`bool`/`str` are refused. Representation is
  preserved (`"10.000000"` stays as written); equality follows Decimal
  (`0.1 == 0.10`). No arithmetic is done on time in Q.1, so no Decimal
  context is needed. `Quantity` is not used: the design stores bare
  Decimal in the engine, with unit conversion at future service
  boundaries.
- **Ordering**: `(time, sequence, stable_id)` ascending. It is total
  because `net_id`/`state` follow in field order, and ties on the full key
  are refused anyway.
- **Sequence policy**: only `DigitalSimulator.schedule` assigns
  sequences, starting at 0 and adding 1 per successfully scheduled event.
  Hand-built events must carry an explicit `int ≥ 0`.
- **Duplicate policy**: an identical canonical key already in the queue
  is rejected as `DUPLICATE_EVENT`. It is never resolved by insertion
  order. Decimal-equal times (`1.0`/`1.00`) count as the same key.
- **Zero-delay**: an event applies at exactly its timestamp, and `now`
  advances to it. Scheduling before `now` is refused (`CAUSALITY`).
  Scheduling at `t == now` is allowed.
- **Mutation**: nets are immutable values. The only state change path is
  `DigitalCircuit.apply(event)`, which is driven by `DigitalSimulator.step`.
- **Determinism**: no dict/set iteration on semantic paths (`nets()` is
  sorted by id; the key set is membership-only). There is no clock, RNG,
  `id()`, `hash()`-ordering, threading or logging.

### Limits

| Constant | Value | Failure |
|:---|:---|:---|
| `MAX_NETS` | 1024 | `DomainError NET_LIMIT` |
| `MAX_EVENTS` | 1 000 000 (queue size AND total per simulator) | `DomainError EVENT_LIMIT` |
| `MAX_TIME` | 3600 s | `ValidationError TIME_LIMIT` |
| id | `[A-Za-z_][A-Za-z0-9_.-]{0,63}` | `ValidationError INVALID_ID` |

Both limits can be lowered per instance (`max_events`, `max_nets`) but
never raised above the constants. `run()` always terminates because the
total number of events is capped.

### Error model (D2)

No new codes and no `AC-DIG-*` area (design §32 / OQ-002). Messages start
with a stable reason token.

| Code | Class | Reasons |
|:---|:---|:---|
| `AC-VAL-001` | `academic_core.errors.ValidationError` | `INVALID_STATE, INVALID_TIME, NEGATIVE_TIME, TIME_LIMIT, INVALID_SEQUENCE, INVALID_ID, INVALID_NAME, INVALID_EVENT, INVALID_LIMIT, INVALID_CIRCUIT, DUPLICATE_NET, DUPLICATE_EVENT` |
| `AC-DOM-001` | `academic_core.domain.entities.DomainError` | `UNKNOWN_NET, EVENT_LIMIT, NET_LIMIT, EMPTY_QUEUE, CAUSALITY` |

Both are `AcademicCoreError` and `ValueError` subclasses, and both convert
through `to_ui_error` while keeping their code (Q1-020).

### Tests — `tests/test_f8q1_digital_core.py`

Q1-001…Q1-020 follow the phase brief. Extra checks:
- invalid sequence and ids
- duplicate-key policy
- net limit
- simulator total bound
- causality
- Q1-P01/P02: seeded-permutation property tests (`queue pops the minimum`,
  `insertion order irrelevant`). They use no `hypothesis` dependency.
- Q1-P03: medium bounded run (19 968 events)
- Q1-S01: AST purity. No logging/os/io/threads/RNG/uuid/time/pickle/
  importlib/PySide6 imports; no F8-N/MNA imports; no `eval/exec/compile/
  open/print/id/hash` calls.

### Known limitations (by design, deferred)

- No components, truth tables, propagation, fixed-point loop detection
  (Q.2).
- No stimuli, clock, pattern, probes, `DigitalTrace`, Logic Analyzer,
  `digital-circuit/1` / `digital-trace/1`, replay, or `DigitalService`.
- Events are plain frozen values with `str(Decimal)`-stable fields, ready
  for Q.x serialization. No wire format exists yet.
- Applying an event whose state equals the current one is a no-op
  (`apply` returns `False`). It is still recorded in `processed`, so the
  future trace layer must filter out non-transitions.
- Roadmap placement (design OQ-001) is not edited here; the phase name
  F8-Q comes from the owner's phase brief.

F8-Q.1 status: **DIGITAL CORE READY** (sub-phase only; F8-Q not certified).

## F8-Q.2 — Digital components + stimuli

Baseline `49752cc`, branch `main`, clean tree. Scope: the NOT/AND/OR/XOR
gates and the constant/toggle/pulse/pattern stimuli, running on the Q1
queue. Still deferred: trace, probes, Logic Analyzer, serialization/replay,
application service, UI, F15, sequential logic, X/Z, tri-state, and
mixed-signal.

### Files

- New: `digital/components.py`, `digital/stimuli.py`,
  `tests/test_f8q2_digital_components.py`.
- Modified: `digital/core.py` (`DigitalCircuit` and `DigitalSimulator` were
  extended; see compatibility below) and `digital/__init__.py` (exports).
  No file outside `digital/` or the docs was touched.

### Component API (`components.py`)

| Name | Contract |
|:---|:---|
| `GateKind` | `NOT / AND / OR / XOR` (closed `str` enum) |
| `TRUTH_TABLES` | read-only `MappingProxyType`, keyed by tuples of `LogicState`, covering every input combination (2^n rows). This is data only (design §50). |
| `ARITY` | derived from the tables: NOT=1, AND/OR/XOR=2 |
| `PinDirection`, `Pin(name, direction, net_id)` | frozen; input pins are `in0..in{n-1}`, the output pin is `out` |
| `DigitalComponent(component_id, kind, inputs: tuple, output)` | frozen; `.pins`, `.pin(name)` (unknown → `UNKNOWN_PIN`), `.evaluate(states)` (table lookup) |

Pins bind to nets. Direct pin-to-pin wiring cannot be expressed, and the
single-driver rule refuses two outputs on one net. The component has no
`delay` field: v1 is zero-delay only, so a delay cannot be expressed
(design §16).

### Stimulus API (`stimuli.py`)

All four stimuli are frozen data. Each expands through `edges()` to a
finite, strictly increasing sequence of `(Decimal time, LogicState)` pairs.

| Stimulus | Edges |
|:---|:---|
| `ConstantStimulus(id, net, state, time=0)` | one edge |
| `ToggleStimulus(id, net, first, start, period, count)` | `first, ¬first, …` at `start + i·period` |
| `PulseStimulus(id, net, start, width, level=HIGH)` | `level` at `start`, `¬level` at `start + width` |
| `PatternStimulus(id, net, start, step, states: tuple)` | `states[i]` at `start + i·step` |

Validation rules:
- Times use Q1 `check_time`.
- `period`, `step` and `width` must be greater than 0 (`INVALID_PERIOD` /
  `INVALID_WIDTH`).
- A stimulus has at most `MAX_STIMULUS_EVENTS` = 100 000 edges and no
  repeat (`STIMULUS_LIMIT`).
- The last edge must be at or before `MAX_TIME` (`TIME_LIMIT`).
- Edge times are computed in an exact 60-digit context that traps
  `Inexact`. A time that would need rounding is refused, never silently
  rounded (`INVALID_TIME`).
- A pattern must be a tuple of `LogicState`. Strings, lists and callables
  are refused.

### Circuit and propagation (additions to `core.py`)

- `DigitalCircuit` gains `add_component`, `add_stimulus`, `components`,
  `stimuli`, `fanout(net)` (sorted by component id) and `driver(net)`.
  - Each net has at most one driver, either a component output or a
    stimulus. A second driver raises `DRIVER_CONFLICT`, naming both.
  - Components and stimuli share one id namespace (`DUPLICATE_COMPONENT`).
  - A component on a net that doesn't exist raises `UNKNOWN_NET`.
  - The number of drivers is bounded by `MAX_NETS`, so no new limit is
    needed.
- `DigitalSimulator` propagates through the same Q1 `EventQueue`; there is
  no second mechanism.
  1. On the first `step`, all components are evaluated in id order and
     their outputs settle to the initial net states at `t=now`. Then
     every stimulus edge is scheduled in stimulus-id order.
  2. After an event that changes a net, the components reading that net
     are re-evaluated in id order.
  3. An output event is scheduled at the same timestamp (zero-delay, no
     artificial delta time). It is scheduled only if the new value
     differs from the output's projected state: the last state scheduled
     for that net, or its current state if nothing is pending.
  4. Comparing against the projected state prevents a stale output when
     two inputs change at the same instant (Q2-013).
  5. Any cascade at the same timestamp is ordered by `(sequence, stable_id)`.
- Loop detection (design §17): more than `max_delta_events` events
  (`MAX_DELTA_EVENTS` = 100 000, lowerable per instance) at one timestamp
  raises `DomainError INVALID_CYCLE` before the next event is popped. The
  Q1 `EVENT_LIMIT` still caps the whole run. A→NOT→A therefore fails
  deterministically, within a bounded number of events and bounded memory.
- If a component or stimulus is registered after the simulator starts,
  the next step raises `CIRCUIT_CHANGED`.

**Q1 compatibility:** every Q1 signature, default and behaviour is
unchanged. The new `max_delta_events` constructor argument is keyword-
compatible, and a circuit without components or stimuli behaves exactly
as before. The Q1 test file was not modified: all 85 tests pass, and
Q1-S01 (AST purity) now also scans `components.py` and `stimuli.py`.

### Error model (D2, no new codes)

- `AC-VAL-001 ValidationError` adds these reasons: `INVALID_KIND`,
  `INVALID_INPUTS`, `INVALID_ARITY`, `UNKNOWN_PIN`, `INVALID_PIN_DIRECTION`,
  `INVALID_COMPONENT`, `DUPLICATE_COMPONENT`, `DRIVER_CONFLICT`,
  `INVALID_STIMULUS`, `INVALID_PERIOD`, `INVALID_WIDTH`, `INVALID_PATTERN`,
  `STIMULUS_LIMIT`.
- `AC-DOM-001 DomainError` adds `INVALID_CYCLE` and `CIRCUIT_CHANGED`.

### Tests — `tests/test_f8q2_digital_components.py`

- Q2-001…Q2-025 follow the brief. The gate truth tables are checked
  exhaustively over all 2^n input combinations, both by direct evaluation
  and through the full simulator, against an independent Python 0/1
  oracle.
- Extra checks:
  - gate identities and De Morgan
  - frozen tables
  - fanout order
  - projected-state race
  - XOR loop
  - default-cap loop
  - `CIRCUIT_CHANGED`
  - exact-time refusal
  - D2 conversion

### Known limitations

- Zero-delay hazards are visible. Simultaneous input edges can produce a
  same-timestamp output glitch (for example Y: H then L at t=1 in Q2-013).
  The final state is correct. The future trace layer must decide whether
  to show or collapse these zero-width pulses.
- Start-up settling can also emit events at `t=0` while outputs converge
  from explicit initial net states that are logically inconsistent.
- Loop detection is dynamic, via the per-timestamp cap. A cyclic structure
  that happens to settle is not refused statically. Only oscillation or
  over-long cascades fail.
- Q1 `DigitalSimulator.schedule` can still target any net, including a
  gate output. Single-driver validation covers registered drivers only.
- Not implemented: clock-domain semantics, NAND/NOR/XNOR, arity > 2,
  per-gate delays, stimulus `repeat`, undriven-net validation (a net with
  no driver holds its explicit initial state), trace, probes, analyzer,
  serialization, service, UI.

F8-Q.2 status: **DIGITAL COMPONENTS + STIMULI READY** (sub-phase only;
F8-Q not certified).

## F8-Q.2R — N-ary component architecture correction

Baseline `ed7df78`, branch `main`, clean tree. Before this change,
Q1 + Q2 passed 155/155. This section supersedes the Q2 `ARITY` /
`TRUTH_TABLES` rows above.

### Motivation

Q2 fixed AND/OR/XOR at exactly 2 inputs (`in0`, `in1`). AcademicCore must
be able to represent gates with N inputs using a single abstraction. Kinds
per arity (`AND3`, `AND4`, …) are ruled out.

### API

- `DigitalComponent(component_id, kind, inputs: tuple[str, ...], output)`
  is unchanged in shape. `inputs` now has length N.
  - Input pins `in0..in{N-1}` follow the order of `inputs`; the output
    pin stays `out`.
  - New `arity` property.
  - `evaluate(states)` validates that the number of states equals `arity`
    and that each one is a `LogicState`, then applies the kind's rule.
- `DigitalComponent.from_pins(component_id, kind, pins: tuple[Pin, ...])`
  builds a component from explicit pin bindings given in any order.
  - Exactly one `out` pin, with direction OUTPUT.
  - Input pins must be named `in<k>` in canonical form (`in00` is
    refused) and numbered contiguously from `in0`.
  - Errors: `UNKNOWN_PIN`, `MISSING_PIN`, `DUPLICATE_PIN`,
    `INVALID_PIN_DIRECTION`, `INVALID_INPUTS`.
- `ARITY_RANGE: {kind: (min, max)}` replaces Q2's `ARITY` mapping.
  `ARITY` was exported one phase earlier and had no users; it is removed
  because a single integer can't describe N-ary kinds.
- `DigitalCircuit.add_component`, `fanout` and the simulator have no
  arity-specific code; one change was needed. Fanout registration now
  iterates the input tuple instead of a `set` of it. Inputs are now
  distinct, and the result is sorted as before.

### Minimum arity

| Kind | Inputs |
|:---|:---|
| NOT | exactly 1 |
| AND / OR / XOR | 2 … `MAX_NETS` (1024) |

- Zero inputs are refused for every kind (`INVALID_ARITY`), so no empty
  AND/OR/XOR semantics are invented.
- One input to AND/OR/XOR is refused as well: it would just be a wire.
- The upper bound is the existing core limit, not a new one. Inputs
  must be distinct nets (`DUPLICATE_INPUT`), so a gate can never read
  more nets than exist.

### N-ary semantics

These are static reductions in `components._reduce`: no generated code,
no tables built from executable strings.

- AND is HIGH iff all inputs are HIGH.
- OR is HIGH iff at least one input is HIGH.
- XOR is HIGH iff an odd number of inputs are HIGH (parity).
- NOT inverts its single input.

`TRUTH_TABLES` is kept for Q2 compatibility as a frozen view derived from
those rules (NOT plus the 2-input tables); it no longer defines the
semantics.

### Compatibility

- `AND(A, B)`, `OR(A, B)`, `XOR(A, B)` and `NOT(A)` behave and serialize
  their pins exactly as in Q2.
- Stimuli are unchanged, and propagation, projected output and
  same-timestamp ordering are the Q2 code paths.
- Intended behaviour changes:
  1. A 3-input OR is now valid. One Q2 parametrized case
     (`test_q2_006_invalid_arity`, `OR("a","b","c")`) asserted the old
     2-only rule. It was replaced by `OR("a")`, which is still invalid, so
     the test is no weaker; the 3-input case is tested positively in Q2R.
  2. A gate that connects the same net to two inputs (`AND(a, a)`) is now
     refused (`DUPLICATE_INPUT`). No existing test or code used this.
- The Q1 test file is unchanged.

### Tests — `tests/test_f8q2r_digital_nary.py`

- Q2R-001…Q2R-020 follow the brief.
- Every combination for N = 2, 3, 4 is checked against the mathematical
  definitions, both by direct evaluation and through the full simulator.
- N = 8 uses deterministic generated vectors: all-low, all-high, one-hot,
  one-cold, plus an LCG walk. No RNG module is used.
- N = 16/32/64 check commutativity, absorbing/identity elements and XOR
  flip sensitivity, plus one simulated run each.
- An N-ary gate is checked against a left fold of the 2-input gate for
  N = 3..6.
- Also covered:
  - `from_pins` validation matrix
  - duplicate input
  - unknown net leaves nothing half-registered
  - 3-input same-timestamp changes over all 64 start/end combinations
  - fanout to AND/OR/XOR/NOT
  - an AND4 → OR5 → XOR8 composition over all 32 inputs

### Known limitations

- NAND/NOR/XNOR are still absent. They would be negated reductions, and
  can be added as new kinds without changing the architecture.
- A single net cannot feed two pins of the same gate. Use a separate net
  if that is ever needed.
- Very wide gates re-evaluate in O(N) for each input change. There is no
  incremental counting; N is bounded by `MAX_NETS`.

F8-Q.2R status: **N-ARY ARCHITECTURE READY** (sub-phase only; F8-Q not
certified).

## F8-Q.3R — Digital Engine Hardening + DigitalTrace

Baseline `dbc9492`, branch `main`, clean tree. Before this change, Q1/Q2/Q2R
passed 85/70/40. This phase closes the three Q2R limitations (A/B/C) and adds
probes and the trace. It supersedes the Q2R "Known limitations" and the
Q2R `DUPLICATE_INPUT` rule.

### A — NAND / NOR / XNOR

- `GateKind` gains `NAND`, `NOR` and `XNOR`. They use the same
  `DigitalComponent` class and are N-ary, with arity 2..`MAX_NETS`, like
  AND/OR/XOR.
- There is a single semantic source. `GATE_SEMANTICS` is data: for each
  kind, a reduction (`ALL` / `ANY` / `ODD`) over the number of HIGH pins,
  plus an inversion flag. `_output(kind, highs, n)` interprets it.
  - Full evaluation (`DigitalComponent.evaluate`, the oracle) uses it.
  - The incremental `GateEvaluator` uses it.
  - The derived `TRUTH_TABLES` view (NOT plus 2-input rows, for Q2
    compatibility) uses it.
- No table with 2^N rows is ever built; wide gates are evaluated
  algebraically.

| Kind | HIGH iff |
|:---|:---|
| NAND | not all pins HIGH |
| NOR | all pins LOW |
| XNOR | an even number of pins HIGH |

### B — Repeated input nets

- Several input pins of one gate may name the same net. Each pin counts
  separately: `NAND(A,A) = NOT A`, `XOR(A,A) = LOW`, `XOR(A,A,B) = B`.
- The Q2R `DUPLICATE_INPUT` error is removed, including from `from_pins`.
- `DigitalComponent.pin_indices(net)` returns the pins bound to a net.
- `fanout(net)` lists a component once, however many of its pins the net
  feeds.
- Still enforced:
  - duplicate pin names (`DUPLICATE_PIN`)
  - the single-driver rule on outputs (`DRIVER_CONFLICT`)
  - duplicate component ids

### C — Incremental N-ary evaluation

- `GateEvaluator(component, states)` is the per-run state of one gate:
  - `initialize(states)`: O(N), once at simulation start-up.
  - `update(index, old, new)`: O(1). Everything is validated before any
    mutation. A wrong `old` state raises `IntegrationError STALE_INPUT`
    (AC-INT-001).
  - `update_net(net, old, new)`: O(k) for the k pins on that net.
  - `output_state()`: O(1), computed through `_output`.
- It stores the per-pin states and a HIGH counter. For AND/NAND/OR/NOR the
  counter is compared with 0 or N; for XOR/XNOR its parity is used.
- The simulator keeps one evaluator per component, updates only the pins
  of the net that changed, and never runs the full reduction once started.
  A test patches the reduction to raise during a 64-input run, so any full
  evaluation would fail it.
- The incremental state is not a second source of truth.
  `DigitalSimulator.check_consistency()` (a dev/test oracle, never on the
  hot path) re-evaluates every gate from the current net states and raises
  `IntegrationError INCONSISTENT_EVALUATOR` on divergence. A test replaces
  the incremental output with full evaluation and checks the whole event
  log is identical, event for event, so no glitch is added or removed.
- Changing a net behind the simulator's back (`circuit.apply` after
  start-up) would desynchronise the evaluators. It is detected through
  `DigitalCircuit.state_revision` and raises `CIRCUIT_CHANGED`.

### DigitalProbe

- `DigitalProbe(probe_id, net_id)` binds one channel to one net.
- It is registered with `DigitalCircuit.add_probe` (`probes()` lists them
  sorted by id).
- It is observation-only: it never claims a driver, never schedules
  events, never mutates nets. The event log is identical with and without
  probes. Several probes may observe the same net.
- Errors: `INVALID_PROBE`, `DUPLICATE_PROBE`, `UNKNOWN_NET`, and
  `PROBE_LIMIT` (`MAX_PROBES` = 32 = design `MAX_CHANNELS`).
- A probe added after the simulation starts raises `CIRCUIT_CHANGED`, so a
  channel never misses the start of a run.

### DigitalTrace

- `DigitalSimulator.trace()` returns an immutable
  `DigitalTrace(start, end, channels)`. It can be called at any time. The
  window is `[start-up time, now]`.
- Channels are `TraceChannel(probe_id, net_id, initial, samples, noop_count)`,
  sorted by `probe_id`. Samples are `TraceSample(time, sequence, state)`.
- Kept vs counted:
  - Every processed event on a probed net that changes the state is a
    real transition and is stored as a sample.
  - An event that doesn't change the state is a no-op: it only increments
    `noop_count` and is never stored.
  - `initial` is the net state at start-up. Between samples the state
    holds (`state_at(t)`, `final`).
- Validation: samples must be strictly ordered by `(time, sequence)`, each
  must be a real transition from the previous state, and all must lie
  inside the window. Channel ids are unique and sorted, and there are at
  most `MAX_PROBES` channels (`INVALID_TRACE`).

### Same-timestamp semantics

- Q1/Q2 ordering is unchanged: `(time, sequence, stable_id)`, zero-delay,
  projected output.
- The trace keeps every real transition, including several on one net at
  the same time (e.g. the Q2-013 hazard `t=1 HIGH`, `t=1 LOW`). They are
  kept in ascending `sequence`, never collapsed. `state_at(t)` returns the
  last one at or before `t`.
- Showing or merging zero-width pulses is left to the future
  renderer/analyzer.

### Digest (internal canonical form)

- `DigitalTrace.canonical()` produces this text:
  - the header `digital-trace-internal/0`
  - the line `window|start|end`
  - per channel in `probe_id` order, `channel|probe_id|net_id|initial`,
    followed by `sample|time|state` lines in stored order
- Times use `str(Decimal)` (design §10), and states are 0/1.
- `digest()` is its SHA-256 (stdlib `hashlib`).
- Excluded: raw `sequence` numbers (order is carried by position; an
  unrelated gate shifts sequences but not the digest), `noop_count`,
  memory, `id()`, Python `hash()`, dict/set order and wall clock.
- This is not the `digital-trace/1` wire schema. Serialization and replay
  are Q4.

### Limits

- Unchanged: `MAX_NETS` 1024, `MAX_EVENTS` 1 000 000, `MAX_TIME` 3600 s,
  `MAX_DELTA_EVENTS` 100 000, `MAX_STIMULUS_EVENTS` 100 000.
- New: `MAX_PROBES` = 32.
- Stored transitions per probed net are at most the processed events,
  which are at most `max_events`. Storage is kept once per net, not once
  per probe. Duration is bounded by `MAX_TIME`.
- Every limit uses the existing D2 codes (AC-VAL-001 / AC-DOM-001 /
  AC-INT-001). No `AC-DIG-*`.

### Compatibility

- Q1 and Q2 test files are unchanged and pass (85 / 70).
- Q2R: its zero-input test is parametrized over `GateKind`, so it now also
  covers NAND/NOR/XNOR (40 → 43 tests). Two assertions of the removed
  `DUPLICATE_INPUT` rule became positive assertions that repeated input
  nets are accepted (brief §5).
- All other public APIs are unchanged. `DigitalCircuit` gains
  `add_probe`, `probes` and `state_revision`. `DigitalSimulator` gains
  `trace` and `check_consistency`.

### Tests — `tests/test_f8q3r_digital_trace.py` (99 tests)

- **Gates:** NAND/NOR/XNOR checked on every input combination for N = 2/3/4
  (direct evaluation and full simulator); properties for all six N-ary
  kinds at N = 8/16/32/64; `MAX_NETS` and above.
- **Repeated inputs:** repeated-net gates over all input combinations.
- **Incremental:** evaluator vs full evaluation over deterministic random
  walks (N up to 64, with repeated nets); a hot-path guard; the whole
  simulation compared incremental vs full; out-of-band state changes.
- **Same timestamp:** 2/3/8 inputs and repeated nets, for all six N-ary
  kinds; cascades; loops (`NAND(A,A)→A`) and bounds.
- **Probes:** a single probe; multiple probes and several on one net;
  probes never drive; lifecycle; no-ops; validation; limit.
- **Trace:** empty; one and multiple transitions; same-timestamp glitch
  kept; digest deterministic and independent of probe order and sequence
  numbers; value validation; storage bound.

### Known limitations

- No Logic Analyzer, trigger/capture windows, sampling or decimation
  views, UI, F15 integration, `digital-trace/1` wire format or replay.
  These are later phases.
- Each probe observes exactly one net. Buses and multi-net channels are
  not modelled.
- `trace()` rebuilds the immutable snapshot each call, which is O(stored
  transitions). Call it once at the end of long runs.
- The digest follows the design's `str(Decimal)` rule, so a time written
  `1.0` and one written `1` produce different digests, though Decimal
  compares them as equal.

F8-Q.3R status: **DIGITAL HARDENING + DIGITALTRACE READY** (sub-phase only;
F8-Q not certified).
