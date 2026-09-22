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
