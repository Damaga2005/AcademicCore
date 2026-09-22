# GATE F8-Q.5 — Digital Logic Analyzer

Design authority: [GATE-DIGITAL-ENGINE-DESIGN.md](GATE-DIGITAL-ENGINE-DESIGN.md),
§§22–26 (Logic Analyzer contract, trigger, capture, sampling,
aliasing). Implementation log of the earlier sub-phases:
[GATE-F8Q-DIGITAL-ENGINE.md](GATE-F8Q-DIGITAL-ENGINE.md).

## Baseline

- Starting point: `38e34a09c6976436fa8a3778647d16975587309f`
  (`feat(engineering): serialize and replay digital traces`, F8-Q.4) on
  branch `main`. The tree was clean and `HEAD == origin/main`.
- Tests before the change, all green:

  | Suite | Passed |
  |:---|---:|
  | Q1 | 85 |
  | Q2 | 70 |
  | Q2R | 43 |
  | Q3R | 99 |
  | Q4 | 144 |

## Scope

- **Added:** a domain-level, event-native Logic Analyzer. It selects
  channels, applies a single-channel edge trigger (RISING / FALLING /
  BOTH) with pre/post-trigger, captures a Decimal window, returns an
  immutable result, and ties into Q4 replay.
- **Not added:**
  - UI or F15 wiring (that is F8-Q.6)
  - sampling or decimation
  - pattern or level triggers
  - sequential logic, X/Z, mixed-signal

## Architecture

```text
LogicAnalyzer.capture(circuit, config)        LogicAnalyzer.analyze(trace, config)
  │ DigitalSimulator.run_until(horizon)          ▲ (e.g. trace loaded from digital-trace/1)
  ▼                                              │
DigitalTrace (Q3R capture, Q4 value) ────────────┘
  │ select channels → trigger search → window cut
  ▼
CaptureResult (frozen) ── .trace is a DigitalTrace ──► Q4 to_json / from_json / verify_replay
```

- **Files.**
  - New `domain/engineering/digital/analyzer.py`.
  - `core.py` gains one additive method, `DigitalSimulator.run_until`.
  - `__init__.py` gains the new exports.
- **What `run_until` does.** `DigitalSimulator.run_until(limit)` is
  `run` restricted to events with `time <= limit`, processed in the same
  canonical `(time, sequence, stable_id)` order. No Q1–Q4 behaviour
  changes.
- **What the analyzer reuses.** It never evaluates gates. The
  incremental Q3R evaluators, fanout, queue, probes and trace are used
  unchanged. An AST test checks that `analyzer.py` doesn't import
  `components` or touch any evaluator attribute.
- **Single implementation.** There is exactly one `LogicAnalyzer` class
  in the source tree (AST test).
- **Purity.** The module is pure domain code. The Q1 purity test (no
  logging, os, sys, time, random, pickle, importlib or PySide6; no
  `eval`, `exec`, `compile`, `id` or `hash`) now also covers
  `analyzer.py`.

## API (re-exported by `digital/__init__.py`)

| Name | Kind | Contract |
|:---|:---|:---|
| `TriggerEdge` | `str` Enum | `RISING`, `FALLING`, `BOTH` |
| `CaptureStatus` | `str` Enum | `CAPTURED` (no trigger configured), `TRIGGERED`, `NOT_TRIGGERED` |
| `TriggerConfig(channel, edge, pre_trigger, post_trigger)` | frozen | all fields required; `edge` must be a `TriggerEdge`; durations are exact Decimal, `0 ≤ d ≤ MAX_TIME` |
| `CaptureConfig(channels, start, end, trigger=None)` | frozen | 1..32 unique probe ids, stored sorted as a new tuple; `start ≤ end`; the trigger channel must be selected; `horizon = min(end + post, MAX_TIME)` |
| `LogicAnalyzer(max_events=MAX_EVENTS)` | stateless | `capture(circuit, config)` and `analyze(trace, config)` |
| `CaptureResult` | frozen | `config`, `status`, `source`, `trace`, `requested_window`, `trigger_time`, `trigger_edge`, `trigger_index`; properties `triggered`, `trigger_channel`, `window` |
| `verify_capture(result)` | function | Q4-replays the source and captured trace, re-analyzes, and requires equality (`IntegrationError REPLAY_MISMATCH` otherwise) |
| `MAX_CAPTURE_CHANNELS`, `MAX_CAPTURE_SAMPLES` | constants | 32; 200 000 (= Q4 `MAX_TRACE_SAMPLES`) |

## Trigger semantics

- An edge is a recorded **transition**, i.e. a trace sample: LOW→HIGH is
  RISING, HIGH→LOW is FALLING, and BOTH accepts either.
- The initial state is never an edge. A stimulus that re-drives the
  initial state is a no-op and does not trigger either (tested for both
  levels and all three edges). A real transition at `t=0`, including a
  gate settling at start-up, does trigger.
- The arming window is `[start, end]`, inclusive at both ends.
- The first qualifying sample in trace order wins. Trace order is the
  simulator's canonical order, so among same-time transitions the
  earliest processed one wins.
- `trigger_edge` reports the edge that actually fired. With BOTH it is
  RISING or FALLING.
- `trigger_index` is the position of the firing sample inside the
  captured trigger channel. It identifies which of several
  same-timestamp transitions fired.
- If nothing qualifies, the result is `NOT_TRIGGERED`:
  - it is a normal value, never an exception
  - `trace`, `window`, `requested_window` and the trigger
    time/edge/index are `None`
  - `source` still holds the searched channels
  - it is distinct from an empty `CAPTURED` window and from any error

## Capture semantics

- **Requested window:**
  - without a trigger: `[start, end]` (status `CAPTURED`)
  - with a trigger at `t`: `[max(t − pre, 0), t + post]`
- **Effective window:** the requested window intersected with the source
  trace window. Both windows are reported. A window entirely outside a
  loaded trace raises `ValidationError CAPTURE_WINDOW`.
- **Source window for `capture`:** `[0, horizon]`.
  - The simulator processes every event with `time ≤ horizon`, so the
    state is known to hold until the horizon, even after the last event
    (tested with a post-trigger of 100 s after a last edge at 3 s).
  - Later events stay queued. The horizon bounds processing, not
    scheduling.
- **Per channel:**
  - `initial` = the state strictly before the window start
  - `samples` = every transition with `ws ≤ time ≤ we`, in order
  - Boundaries are inclusive, and the trigger sample is always kept
    (`pre = post = 0` gives `[t, t]` with the whole same-time run).
- **Arithmetic:** exact Decimal. Window arithmetic uses a trapped exact
  context, so a sum that would need rounding raises `INVALID_TIME` and is
  never rounded. No float appears anywhere.
- **No-op counts:** `digital-trace/1` stores a count per channel, not
  times. So counts are kept only when the effective window covers the
  whole source window; otherwise they are 0. The source keeps its counts.
- **Circuits are captured once.** Simulation mutates net states, so
  `capture` refuses a circuit that already ran (`DomainError
  CIRCUIT_CHANGED`). A fresh, identical circuit gives an identical
  result.

## Same-timestamp behaviour

- XOR(A,B,C) with all three inputs rising at `t=1` gives Y =
  LOW→HIGH→LOW→HIGH at `t=1`. The three transitions are kept in simulator
  order.
  - RISING fires at index 0, FALLING at index 1, BOTH at index 0 (edge
    RISING).
  - At `t=2` (all inputs falling), a FALLING trigger armed from 1.5 fires
    at index 0 and a RISING one at index 1.
- XNOR(A,B) gives HIGH→LOW→HIGH at `t=1`.
- Multi-channel results are identical whatever order the caller lists
  the channels in.

## Determinism

- The analyzer holds no state, reads no clock or RNG, and has no
  dict/set iteration in any semantic path.
- Five repeated runs are equal, with identical canonical JSON and
  digests.
- Four separate interpreter processes (`PYTHONHASHSEED` 0 / 1 / 4242 /
  random) give byte-identical status, trigger and digest strings for
  four scenarios, one of them `NOT_TRIGGERED`.

## Bounds

| Bound | Value / mechanism |
|:---|:---|
| channels | 1..32 (`CAPTURE_LIMIT`) |
| capture duration / times | `check_time` ≤ `MAX_TIME` (3600 s); horizon clipped at `MAX_TIME` |
| simulated events | `LogicAnalyzer(max_events)` ≤ `MAX_EVENTS`, via the simulator (`EVENT_LIMIT`) |
| per-timestamp events | unchanged Q2 `MAX_DELTA_EVENTS` (`INVALID_CYCLE`) |
| captured samples | ≤ 200 000 (`CAPTURE_LIMIT`), so every capture can be serialized |
| pre/post buffers | exact durations ≤ `MAX_TIME`; the window is a slice of the bounded source, with no extra buffer |
| serialized result | Q4 limits (16 MiB, 200 000 samples) |

## Errors (D2, no new codes)

| Error | Code | Reasons |
|:---|:---|:---|
| `ValidationError` | AC-VAL-001 | `INVALID_CAPTURE`, `INVALID_TRIGGER`, `INVALID_ID`, `DUPLICATE_PROBE`, `UNKNOWN_PROBE`, `CAPTURE_LIMIT`, `CAPTURE_WINDOW`, `INVALID_TIME`, `INVALID_LIMIT`, `INVALID_CIRCUIT`, `INVALID_TRACE` |
| `DomainError` | AC-DOM-001 | `CIRCUIT_CHANGED`, `EVENT_LIMIT`, `INVALID_CYCLE` |
| `IntegrationError` | AC-INT-001 | `REPLAY_MISMATCH` |

## Security

The module contains no `eval`, `exec`, `compile`, pickle, marshal,
dynamic import, `getattr`, `setattr`, I/O, logging, clock or RNG
(AST tests `test_q5_x01` and Q1 `test_q1_s01`). Configurations are
typed and frozen. Unknown or duplicate ids are refused before any
simulation.

## Replay (Q4)

- The captured `trace` is a plain `DigitalTrace`, so there is no second
  format. Checked:
  - `to_json` → `from_json` → equality and digest
  - `verify_replay`
  - analyzing the Q4-loaded `source` gives the identical `CaptureResult`
- `verify_capture` detects tampering. Tested: a changed trigger index,
  trigger time, status, or captured window each raises
  `REPLAY_MISMATCH`.
- A `NOT_TRIGGERED` result also verifies.

## Tests — `tests/test_f8q5_logic_analyzer.py` (87 tests)

- **Configuration:** valid / frozen / normalized; 10 invalid time kinds
  (float, negative, NaN, ±Infinity, str, bool, None, > MAX_TIME) on
  every Decimal field; inverted window; non-exact window arithmetic;
  12 invalid channel selections; invalid triggers; invalid limits;
  unknown channels; single-capture rule.
- **Trigger:** rising / falling / both; first qualifying edge; arming
  window; initial state does not trigger; explicit `NOT_TRIGGERED`
  versus an empty capture.
- **Capture:** inclusive boundaries; pre/post-trigger; trigger at the
  boundary (`pre = post = 0`); clipping at 0; held state beyond the last
  event; exact Decimal (0.1 steps); `run_until` horizon; no-op policy;
  window outside a loaded trace.
- **Same timestamp:** LOW→HIGH→LOW→HIGH, HIGH→LOW→HIGH, a trigger
  inside a run at the window start, multi-channel order.
- **N-ary:** AND / OR / XOR / NAND / NOR / XNOR at N = 2, 3, 8 and 64,
  compared with a closed-form oracle; a NAND with 1023 inputs
  (`MAX_NETS` nets); repeated input nets; a static check that the
  analyzer never evaluates gates.
- **Replay:** three pipelines (capture → JSON → load → replay → verify);
  tamper detection.
- **Determinism:** repeated runs; separate processes with different
  hash seeds.
- **Bounds:** event budget; horizon; capture sample limit; `MAX_TIME`
  horizon.
- **Security:** AST source policy; frozen result without live
  references.
- **Golden fixtures** (`tests/fixtures/logic_analyzer/`, pinned
  SHA-256): `rising_pre_post`, `falling_same_timestamp`,
  `high_low_high`, `window_capture`.
- **Properties** (LCG, no RNG module): 120 random circuits (all gate
  kinds, cascaded, repeated pins) × random configurations. Each case is
  checked against:
  - an independent brute-force trigger search
  - the window-slice definition
  - the Q4 round-trip
  - `analyze(loaded source) == capture`
  - `verify_capture`

  All three statuses occur.

## Regression

Run on the Q5 tree, offscreen Qt:

| Suite | Result |
|:---|:---|
| Q1 / Q2 / Q2R / Q3R / Q4 | 85 / 70 / 43 / 99 / 144 passed |
| Q5 | 87 passed |
| F8-P1..P5 | 221 passed |
| F15 | 27 passed |
| architecture / AST / domain / engineering security | 13 / 5 / 4 / 5 passed |
| F8-N | included in the full suite (125 at the Q4 baseline) |
| **Full suite** | **2962 passed, 134 skipped, 0 failed** (2875 at the Q4 baseline + 87 new) |

- There are no xfails and no collection errors.
- The 134 skips were already present at the Q4 baseline (an unchanged
  count). They are external-runtime and optional-tool tests.

## Limitations (real, v1 by design)

- **Triggers:** single-channel edge triggers only. There are no
  pattern, level or multi-channel triggers (design §23: future).
- **No-op counts:** a partial window can't attribute them, because the
  Q4 schema has no no-op times. They are reported as 0 there (see
  Capture semantics).
- **Scheduling vs horizon:** stimuli are scheduled in full at start-up
  (Q2 behaviour), so `max_events` bounds scheduled events, not only
  those inside the horizon.
- **Search cost:** the trigger search and slicing are linear in the
  selected channels' samples. That is bounded by `MAX_EVENTS` per net,
  but there is no index.

## Verdict

```text
F8-Q.5 READY
```
