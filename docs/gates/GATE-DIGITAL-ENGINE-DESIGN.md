# Digital Engine Design Gate — Logic Analyzer real para AcademicCore

Documentation only: no code under `src/` was created or modified, no
tests were written, no engine was altered, F15/F8-N/F8-P1…P5/D1/D2/D3
were not touched, no GREELEC integration was performed. The only output
of this phase is this file plus one local commit (no push).

## 1. Baseline

- Repository `Damaga2005/AcademicCore`, branch `main`, baseline
  **`d23ca7f`** (`docs(gates): certify F15 final application`),
  `origin/main == 91343ba` (F15 commits local, unpushed — intended per
  F15 §86), working tree clean at audit time.
- Certified at baseline: F8-P1…F8-P5, F15 (`FINAL VERDICT: F15 CERTIFIED`
  in `docs/gates/GATE-F15.md`); D1/D2/D3 DESIGN READY.
- Roadmap authority: `ROADMAP.md` §5.1 (strict order). There is NO
  `ROADMAP_orden_implementacion.md` file in-repo; §5.1 inside
  `ROADMAP.md` is the single ordering source.

## 2. Problem statement

```
F15
 └── Logic Analyzer
      └── limitation
           └── no digital engine in F8-N
```

F15 §9/GATE-F15 §20 record honestly: F8-N `InstrumentKind` offers
`voltmeter / ammeter / oscilloscope / frequency_response_viewer /
sweep_viewer` — no logic-level instrument exists, and the UI invents
none (`test_f15_011_logic_analyzer_limitation`). Forbidden resolutions:
random samples, hardcoded waveforms, fake transitions, UI-only
analyzer. A real Logic Analyzer must consume digital traces produced
by a real digital engine. This gate closes the *design* only.

## 3. Current F8-N capability audit

Verified by inspection at baseline (all paths under
`src/academic_core/domain/engineering/lab/`):

| Area | Public API | Signal types | Extensibility | Compatibility note |
|:---|:---|:---|:---|:---|
| Session | `create_session / clone_session / close_session / reset / annotate / branch_experiment` | analog `Circuit` (deep-copied) | closed; new analyses need engine work | `f8n-lab/1`, digests exclude session ids |
| Experiment | `add_experiment / validate_definition / ExperimentDefinition` | `AnalysisKind` ×10 (OP … TRANSIENT) | closed enums | digest-addressed, idempotent |
| Run | `run_experiment / execute_run` | one certified engine call per run | dispatch table | `RunStatus`, verbatim engine status |
| Stimulus | `StimulusSpec` (DC/STEP/PULSE/SINE/AC) + `function_generator` (sine/pulse/square/dc) | analog `Quantity` + Decimal times | closed kinds | triangle/noise/arbitrary out of scope |
| Probe | `VoltageProbe / CurrentProbe / ParameterProbe` | nets, branches, param addresses | closed | pure observation, never mutates |
| Measurement | `MeasurementSpec` ×18 kinds, per-analysis applicability | `Scalar / ComplexScalar / Waveform / ScopeData / BodeData / SweepData` | closed | `WAVEFORM / AC / DC` applicability sets |
| Instruments | `InstrumentSpec`: voltmeter/ammeter (OP/DC_SWEEP/AC_POINT/TRANSIENT), oscilloscope (TRANSIENT, trigger-or-window), frequency_response (AC_SWEEP), sweep_viewer (F8-M) | analog views | closed | **no logic analyzer kind exists** |
| Serialization | `to_document / dumps_session / loads_document`, schema `f8n-lab/1` | canonical JSON, `str(Decimal)`, digests | version-gated | tamper → `INVALID_SERIALIZATION` |
| Replay | `replay_run`, `EQUIVALENT / RESULT_DIFFERS / VERSION_MISMATCH / SCHEMA_MISMATCH / INVALID_SERIALIZATION` | digest compare | same-version only | engine versions recorded in provenance |

D1 §20 named "logic analyzer" among F8-N instruments — that line was
aspirational: the certified code contains no such instrument. F15
correctly downgraded it to a limitation; this gate designs the missing
engine without rewriting that history.

"Digital" elsewhere in-repo means *sampled numerics*, not logic
levels: F8-P2 (DFT/FFT, Z, FIR/IIR — `TransferFunctionZ`), F8-P4
(seeded bit streams for BER simulation — statistics, not gates).
There is NO boolean/gate/event engine, NO truth-table evaluation, NO
`LogicState` type anywhere in `src/` (verified by grep).

## 4. Roadmap placement

No roadmap phase covers logic/digital gates. `ROADMAP.md` §5.1 closes
F8 at F8-P5 and orders D1→D2→D3→F15→F3-ext→F4-ext→F13-ext→D4…→F9…→F16;
no F8-Q or digital row exists. Per the no-silent-invention rule:

- **Placement: PENDING owner decision** (open question OQ-001).
- Recommendation (not invention): a new row `F8-Q Digital Logic
  (event-driven gates + trace + analyzer contract)` placed after F15
  and before F3-ext, reusing the F8-N session/replay idioms without
  touching certified F8 code. Reusing an F8-Px number is forbidden
  (all consumed); folding into F9–F12 is rejected (assessment/adaptive/
  AI phases are disjoint concerns).
- Nothing in this gate assumes the recommendation; all contracts below
  are phase-agnostic.

## 5. Architecture alternatives

### Opción A — Extender F8-N (analog engine + digital engine)

Reuse `LaboratorySession / ExperimentDefinition / Run / serialize /
replay` by adding digital analysis kinds, digital probes, and a
`logic_analyzer` instrument kind directly in `lab/`.

| Dimension | Assessment |
|:---|:---|
| coupling | HIGH — digital semantics inside the certified analog orchestrator |
| reuse | maximal (sessions, replay, `f8n-lab/1`) |
| testing | F8-N suite becomes mixed-concern |
| serialization | schema bump `f8n-lab/1 → /2` risk; tamper vectors widen |
| performance | event traffic inside run-record machinery sized for analog runs |
| future mixed-signal | easiest joint sessions |
| certification impact | **BLOCKING-class**: F8-N is CERTIFIED; editing `model.py / run.py / serialize.py` invalidates the certification premise ("NO modificar F8-N salvo documentación") |

### Opción B — DigitalEngine paralelo a F8-N

Independent `domain/engineering/digital/` + own session/replay/serialize.

| Dimension | Assessment |
|:---|:---|
| coupling | LOW |
| reuse | LOW — duplicates session/record/digest/replay machinery (~1000 lines of proven logic re-derived) |
| testing | clean split, but two session semantics to keep aligned |
| serialization | new schema, no collision risk |
| performance | independently tunable |
| future mixed-signal | needs a third joint layer later |
| certification impact | none on F8-N |

### Opción C — DigitalDomain + application service común (SELECTED)

New `domain/engineering/digital/` module (signal/event/trace engine,
§§7–17) + a `DigitalService` in `application/` reusing LabService
*idioms* (frozen summaries, text-in/out serialization, correlation
ids) but NOT F8-N code paths. F8-N untouched. A future mixed-signal
frontera is an explicit threshold adapter (§20), designed later.

| Dimension | Assessment |
|:---|:---|
| coupling | LOW (idiom reuse, no code-path sharing) |
| reuse | medium (patterns, error codes, test shapes) |
| testing | clean; property tests per gate (§51) |
| serialization | new `digital-trace/1`, zero collision with `f8n-lab/1` |
| performance | bounded event lists, independently capped |
| future mixed-signal | explicit adapter, no premature joint sessions |
| certification impact | none (F8-N/F8-Px/F15 byte-identical) |

**Selected: C.** Justification: it is the only option with zero
certification impact (hard constraint), no machinery duplication
(vs B), and no premature mixed-signal commitment (vs A). The cost —
a second trace schema — is bounded and explicit (§17).

## 6. Selected architecture

```text
F15 UI (future LogicAnalyzer widget; renders events only)
  ↓ commands / views
DigitalService (application/; orchestration, frozen summaries,
  text-in/out serialization, correlation ids — LabService idioms)
  ↓ engine calls
DigitalEngine (domain/engineering/digital/; pure, Qt/IO/log-free)
  ↓ DigitalTrace (value)
UiError / replay verdicts (existing D2 machinery)
```

F8-N keeps serving analog; the two engines meet only in future UI
tabs and in the (future, separately gated) threshold adapter. No
F8-N file is modified by this design.

## 7. Digital signal model

- **Analog signal** (existing): dimensional `Quantity`/Decimal value
  evolving continuously; observed as `Waveform` (piecewise-linear
  committed samples) or phasors/scalars.
- **Digital signal** (new): a *dimensionless* logic state bound to a
  named net, defined only at event timestamps. Between events the
  state holds (zero-order hold is definitional, not interpolation).
- **Oscilloscope waveform** = analog voltages vs time (continuous
  semantics, `V`/`A` units).
- **Logic analyzer trace** = per-channel event lists `(t, state)`
  (discrete semantics, unit `1`).

The two are never interconverted implicitly; any crossing needs the
explicit threshold adapter (§20).

Contract (`DigitalSignal`, conceptual):

```text
name:      channel/net identifier (non-empty, closed charset)
channel:   analyzer channel index (0 .. MAX_CHANNELS-1)
source:    driving component ref + output pin
domain:    "digital" (literal; mixed content rejected)
states:    LOW | HIGH (v1; §9)
timestamps: strictly increasing Decimal seconds, base unit
events:    tuple[(t, state)] — transitions only, no sampling grid
validity:  closed config required (driver, init, window); else INVALID
```

## 8. Logic states

**v1: LOW / HIGH only.** Two-valued Boolean algebra is closed under
the v1 component set, needs no resolution semantics, serializes as
`0/1`, and suffices for a real analyzer (stimuli + combinational
nets produce genuine transitions).

`UNKNOWN` / `HIGH_Z` are **deferred**, not denied. If later required,
each needs: 4-value truth tables (data), propagation rules
(`X` dominance explicit), conflict-vs-unknown disambiguation,
comparison semantics for replay (is `X` vs `0` a `RESULT_DIFFERS`?),
and UI glyphs. None of that is designed here beyond reserving the
`state` field width.

## 9. Time model

**Selected: event-driven with Decimal timestamps** (continuous event
time). Comparison:

| Criterion | Event-driven (selected) | Fixed grid | Hybrid |
|:---|:---|:---|:---|
| determinism | exact Decimal compare | exact, but grid phase is a hidden parameter | inherits event core |
| memory | O(transitions), sparse | O(duration/Δt), dense waste on quiet nets | core + view cost |
| performance | queue O(E log E) | O(steps × nets) regardless of activity | — |
| replay | canonical event list | grid + phase must both match | — |
| serialization | exact strings | exact, but bloated | — |
| UI | render events to pixels (scope precedent) | direct blit, with resampling loss risk | sampled *view* derived from events |

Fixed grids are rejected as the engine core (hidden phase parameter
+ resampling loss + memory waste). The hybrid position is adopted
*across layers*: the engine is event-native; any sampled display is
a lossy *view* that must flag decimation (§§25–26). No `float` time
anywhere: Decimal seconds, base unit, reuse of `units.TIME` and the
`lab_context` Decimal-context discipline.

## 10. Representación del tiempo

- Type: `Decimal`, seconds, base unit (`Quantity.to_base()` at
  boundaries; engine stores bare Decimal like F8-L `tstop`).
- Precision: 50-digit context precedent (`make_context`); exact
  compare, no epsilon.
- Resolution: none imposed (event times are data); ordering is
  `(t, seq, component_id)` canonical (§48).
- Equality: exact Decimal equality; `1.0` vs `1.00` compare per
  Decimal semantics — canonical form fixed at serialization
  (`str(d)`, the F8-N `decimal_string` precedent, NOT `normalize()`).
- Serialization: `str(d)` strings, sorted structures, never binary.

## 11. Digital components

Needed classification (none implemented in this gate):

| Component | Verdict |
|:---|:---|
| wire/net (implicit connectivity) | REQUIRED (model primitive) |
| constant source (tie 0/1) | REQUIRED (stimulus-adjacent) |
| NOT, AND, OR, XOR | REQUIRED first engine |
| NAND, NOR, XNOR | FUTURE (named conveniences; composable from required set) |
| clock / pulse / pattern sources | REQUIRED (stimuli, §§18–19) |
| tri-state buffer, buses | OUT OF SCOPE v1 (needs Z + resolution, §47) |
| D flip-flop, latch, counter, register | FUTURE (sequential gate, §§43–44) |

## 12. Minimal digital core

`DigitalCircuit` (new, small): nets (named set) + components
(`DigitalComponent`: ref, kind, inputs, outputs, params-data) +
stimuli + probes. Deterministic (sorted/frozen structures), extensible
(new kinds = data rows + validator entry), testable (pure functions,
no Qt/IO/log). It reuses *conventions* (ref patterns, digest idioms)
but no MNA structures.

## 13. Digital netlist

**Separate digital circuit graph** (selected). Reusing the analog
`Circuit` would force digital semantics through MNA-typed pins,
`Quantity` values, and solver-oriented validation — semantic
confusion with certification-adjacent code (§425 of the audit brief).
Duplication is avoided by sharing only: identity conventions,
`ParamAddress`-style addressing (digital equivalent:
`NetAddress(net)`), canonical-JSON/digest helpers' *shape* (not their
code paths), and the `name/N` schema convention.

## 14. Mixed signal

**First engine: digital-only** (selected). Full mixed-signal is
rejected as premature (needs co-simulation timebases, analog event
detection inside Newton loops, joint replay — all unscoped).
Analog→digital and digital→analog cross *only* via an explicit,
separately-gated **threshold adapter** (§§20, 37–39): comparator with
`V_low / V_high / hysteresis` turning `Waveform` crossings into
events (and, symmetrically, an ideal driver turning events into
piecewise-constant analog segments). The adapter is *designed as a
boundary* here, implemented never in this gate.

## 15. Event propagation

```text
input transition (t, net, state)
  ↓ queue pop in (t, seq, component) order
component evaluation (truth-table lookup on current input states)
  ↓ output transition scheduled at t + delay (v1: delay = 0)
next component(s) on the driven nets
```

Mechanism: explicit priority event queue; **zero-delay v1**
(combinational fixed-point per timestamp, iteration-capped —
the cap doubles as loop detection, §17). Delta cycles are not
modelled separately: same-timestamp cascades settle by the capped
fixed point, which is deterministic given canonical ordering.
Propagation/per-gate/inertial/transport delays are future (the queue
already carries timestamps, so delays slot in without redesign).

## 16. Delay model

**v1: zero-delay deterministic** (justified: combinational-only
engine; output transitions inherit stimulus timestamps exactly;
no hidden timing parameters to certify). Reserved `delay` field on
`DigitalComponent` (must be `0` in v1 config; nonzero → г
`UNSUPPORTED`, honestly refused). Fixed/per-gate/inertial/transport
models are future work items with the queue design already
compatible.

## 17. Loops

Combinational loops, zero-delay feedback, and oscillation (e.g. NOT
ring) are detected deterministically by the per-timestamp evaluation
cap (function of net count, fixed in config, e.g. `max_passes =
nets + 1`): exceeding it → typed `INVALID_CYCLE` error carrying the
net set, run marked failed honestly. Infinite loops as a simulation
mechanism are structurally impossible (bounded queue + bounded
passes + bounded event count, §31).

## 18. Clock

**Periodic digital stimulus** (selected — minimal). No native clock
component in v1: a clock is data (`period / duty / phase / repeat`,
§19) driving nets like any stimulus. Native clock semantics (domains,
skew, gating) arrive only with sequential support, if ever.

## 19. Digital stimuli

Closed data kinds (all serializable, no callables):

```text
constant   {net, state}
pulse      {net, t_start, width, repeat?, period?}
clock      {net, period, duty, phase, t_start, repeat}
sequence   {net, t_bit, bits: "101010…" | tuple, t_start, repeat}
```

Each field validated (`period > 0`, `0 < duty < 1`, `t ≥ 0`,
sorted/unique edges); violations → `ValidationError` before any
evaluation.

## 20. Pattern generation

Explicit vectors only (`bits` string over `{0,1}` or tuple, plus
`t_bit`; optional `repeat` count, never unbounded). Deterministic
(index arithmetic, no RNG), serializable (plain string), replayable
(vector hashed into the config digest). Python functions/lambdas as
patterns are forbidden (cf. §34).

## 21. Digital probes

`DigitalProbe(net, channel?)`: binds an analyzer channel to a net.
Observation-only (never modifies the circuit; unknown net →
`INVALID_PROBE` at validation, mirroring F8-N probe discipline).
Probes are declared in the experiment definition, sorted by key.

## 22. Logic Analyzer contract

The analyzer consumes a real `DigitalTrace` (conceptual):

```text
channels:      tuple[(name, events: tuple[(t: Decimal, state: 0|1)])]
timebase:      {t_start, t_end} capture window (explicit)
trigger:       {channel, kind: rising|falling|either, position}
capture:       {pre_events, post_events} counts (bounded)
config_digest: digest of netlist + stimuli + analyzer config
engine_version: "digital-engine/1.0" (future; pinned at implementation)
provenance:    {schema, engine_versions} (replay-gated, F8-N idiom)
```

NOT implemented in this gate. The future instrument spec mirrors
`InstrumentSpec` (`logic_analyzer` kind, channels ≤ `MAX_CHANNELS`,
window-or-trigger required — the oscilloscope precedent).

## 23. Trigger

Minimum viable v1: **single-channel edge** — `rising | falling |
either` + `level` is meaningless for states (kept out deliberately).
Pattern/level triggers are future. Rationale: edge triggering exercises
the full capture path (detect → window → trace) with one predicate.

## 24. Capture

Explicit bounds, all required (no silent defaults):
`pre_events` + `post_events` counts (or explicit `t_start/t_end`
window) + `MAX_EVENTS` / `MAX_CHANNELS` / `MAX_TRACE_DURATION`
budgets (§31). Infinite buffers are unrepresentable by construction
(frozen tuples + caps checked at validation AND at capture).

## 25. Sampling

Engine event resolution and analyzer sampling are **separate layers**:
v1 capture is event-native (every transition preserved; no sampling,
hence no loss). If a future display path downsamples to pixels, it
must report `{events_total, events_shown, decimated: true}` — loss is
always flagged, never hidden. Several transitions inside one display
bin therefore cannot silently vanish: the engine holds them all; the
view annotates the bin.

## 26. Aliasing

N/A for v1 event-native capture (documented why: no periodic sampler
exists in the path, so aliasing is unrepresentable). Event→display
conversion renders transitions as step segments between exact
timestamps; any future sampled export (e.g. CSV at fixed Δt) must
document its transition-loss policy at its own gate.

## 27. Trace model

```text
DigitalTrace
 ├── channel   (name, source ref+pin, events)
 ├── timestamps (Decimal seconds, strictly increasing per channel)
 ├── states    (0|1 aligned with timestamps)
 ├── metadata  (labels, trigger report — never digested)
 └── provenance (schema, engine version, config digest — replay-gated)
```

Deterministic (sorted channels, canonical decimals), serializable
(`digital-trace/1`, §30), replayable (digest compare, §29).

## 28. Determinism

Same netlist + stimuli + configuration + engine version ⇒ same trace
+ same digest — independent of logging, UI, `correlation_id`, host,
Python dict order (banned from the path; sorted tuples everywhere),
and wall clock (no clock reads in the engine; `t` is simulation
time, always data).

## 29. Replay

Reuse, no parallel semantics:
`capture → save → load → replay → compare` with `EQUIVALENT /
RESULT_DIFFERS (first difference path) / VERSION_MISMATCH (refuse
unless explicitly allowed) / SCHEMA_MISMATCH / INVALID_SERIALIZATION`.
Notes/annotations excluded from digests (F8-N precedent).

## 30. Serialization

New schemas (no collision with `f8n-lab/1`):
`digital-circuit/1` (netlist doc) + `digital-trace/1` (result doc).
Deterministic content only: schema version, engine version, channels,
states, timestamps, configuration, digest. Excluded from digests and
from stored payloads: runtime timestamps, correlation ids,
host-specific values. Closed keys (unknown rejected), tamper →
`INVALID_SERIALIZATION`.

## 31. Performance y límites

Initial bounds (implementation-gate adjustable, principles fixed):

```text
MAX_NETS = 1024 · MAX_EVENTS = 1_000_000 · MAX_CHANNELS = 32
MAX_TRACE_DURATION = 3600 s (simulation time) · MAX_SAMPLES(view) = 10000
```

Strategy: bounded in-memory frozen tuples (no streaming, no ring
buffer, no compression in v1 — bounds make them unnecessary);
event queue bounded by `MAX_EVENTS` (overflow → typed failure, never
silent truncation). Memory is O(events), time O(E log E).

## 32. Error handling — D2

Reuse the existing hierarchy — no parallel taxonomy:
`AcademicCoreError / DomainError (model violations) /
ValidationError (bad input) / UnsupportedError (nonzero delay,
sequential, Z) / SerializationError / VersionMismatchError /
ApplicationError / AdapterError / InfrastructureError /
IntegrationError (internal invariant breach)`, converted at the
single `to_ui_error` boundary into `UiError`.

New codes: D2's area set is closed, so **no `AC-DIG-*` area is
created here**; digital failures map to existing areas
(`AC-VAL-*` validation, `AC-DOM-*` model/cycle, `AC-UNS-*`
deferred features, `AC-SER-*/AC-VER-*` trace wire). Whether a
dedicated sub-namespace is warranted is OQ-002 (needs a D2
amendment, out of scope for this gate).

## 33. Logging

Digital domain: **zero logging** (D2-I003 pattern; `get_logger`
refuses `academic_core.domain*` already). Application service logs
milestones only: simulation start/end, event count, capture summary,
failure + correlation id. Per-transition logging is forbidden outside
explicit DEBUG-behind-flag, rate-capped (D2 §20 precedent).

## 34. Security

Forbidden for describing or executing digital circuits: `eval`,
`exec`, `compile`, `pickle`, dynamic code, import-by-string.
Truth tables and patterns are frozen data (tuple-keyed mappings).
Future AST/static tests: no loader imports in `digital/`, closed
deserialization (allowlisted constructors, `digital-trace/1` keys),
bounded queue/capture (DoS shape), malformed/tampered-trace refusal.

## 35. UI boundary

```text
UI (future widget; renders DigitalTrace events, sends commands)
 ↓
Lab/Digital application service (validates, orchestrates, serializes)
 ↓
Digital Engine (pure; never imported by widgets)
 ↓
DigitalTrace (value) → UiError / replay verdict → UI
```

`widget → engine internals` stays forbidden (F15-018 edge-test
pattern extends to `digital` imports at implementation).

## 36. F15 compatibility

F15 CERTIFIED is preserved byte-for-byte: dashboard, exercises,
simulation, virtual lab, oscilloscope, multimeter, DC supply,
function generator, serialization, replay — none are touched.
The DigitalEngine is purely additive: a new domain module + (future)
service + (future) widget + a new `logic_analyzer` instrument kind
gated behind engine availability. F15's limitation note
(`test_f15_011`) remains true until the implementation gate lands.

## 37. Instrument compatibility

Oscilloscope (`Waveform`, analog, units `V/A`) and Logic Analyzer
(`DigitalTrace`, states `0/1`, dimensionless) are disjoint types;
no widget renders one as the other. One physical source feeds both
only through the explicit threshold adapter (future, §14): the
crossing is recorded in provenance, never implicit.

## 38. Function generator

Analog `sine/square/pulse/DC` outputs may drive digital inputs only
via the threshold adapter: `square/pulse` + thresholds define the
crossing; `sine` + hysteresis is allowed through the same adapter
with documented slice semantics; direct float→bit coercion is a
type error. Adapter specified as boundary only — not implemented.

## 39. DC supply

A DC source represents HIGH/LOW only through an explicit mapping
owned by the threshold adapter (e.g. `V ≥ V_high → HIGH`,
`V ≤ V_low → LOW`, between → adapter policy `HOLD_LAST | ERROR`,
configured, never defaulted silently). No semantics are invented
for the supply itself: unmapped DC into a digital net is
`INVALID_CONFIGURATION`.

## 40. Architecture D1

New modules fit the D1 taxonomy without amendment: `digital.*` =
`domain-module`; `DigitalService` = `application-service`; future
widget = `ui-view`; threshold adapter = `adapter`. Manifest entry
(`d1-manifest/1` shape) declares capabilities
(`combinational, stimuli, trace`), `serialization_schemas`
(`digital-circuit/1`, `digital-trace/1`), determinism note, and
`security_policy: "domain-pure"`. Dependency edges obey D1 §9
(`ui → application → domain/ports`; `domain → math/units/stdlib`;
never `domain → Qt/filesystem/logging/subprocess`).

## 41. Extension strategy

Options A/B/C compared in §5. **Selected: C** (DigitalDomain +
common application-service idioms), for zero certification impact,
no machinery duplication, and an explicit future mixed-signal
boundary. A is rejected (F8-N certification impact); B is rejected
(session/replay duplication).

## 42. Component model

`DigitalComponent(ref, kind, inputs: tuple[nets], outputs:
tuple[nets], params: frozen data)`: pins are net bindings (no
electrical semantics); truth behavior is a frozen table per kind
(lookup evaluation); `delay` reserved (must be `0` v1);
**no state in v1** (combinational). The analog `Component` model is
not copied: no `Quantity` values, no MNA pins, no solver parameters.

## 43. Combinational vs sequential

Split is structural: combinational (output = pure function of
current inputs) vs sequential (output = function of inputs +
state + clock). **v1 = combinational + stimuli** (justified: clock
and pattern stimuli already produce genuine multi-transition
traces, so a real Logic Analyzer is exercisable with zero state
semantics to certify). Sequential enters only via its own
implementation gate with §§44–45 contracts closed first.

## 44. Stateful digital

Deferred contract points (specified, not implemented): per-element
`state` (explicit init, §45), `clock` (edge kind + source net),
`reset` (level + synchronous/asynchronous kind), `initial state`
(required). Flip-flop/latch/counter/register are named future
kinds; no behavior is assumed for them anywhere in v1.

## 45. Initial conditions

Stateful elements without an initial state → `INVALID`
configuration (explicit over magic defaults, per the roadmap's
no-silent-defaults principle). The deterministic default, if the
implementation gate ever wants one, must be a designed constant
(e.g. `LOW`) recorded in the config digest — never an ambient
Python value. Either way the outcome is reproducible by construction.

## 46. Conflicting drivers

Two outputs driving one net → `INVALID_CONFIGURATION` error naming
both drivers (v1 policy: **error**). Wired-OR/wired-AND resolution
and `X`-injection are explicitly deferred alternatives (each needs
resolution-table semantics + replay-comparison rules first).

## 47. Tri-state

`Z` is **deferred**: unnecessary for the first analyzer (no buses in
v1 component set) and load-bearing once introduced (needs driver
resolution + `X`-vs-`Z` comparison semantics). No `Z` literal exists
in v1 types.

## 48. Event ordering

Canonical order `(timestamp: Decimal, seq: int, component_id: str)`:
timestamps exact, `seq` from a per-run monotonic counter (no clock,
no RNG), `component_id` lexicographic tiebreak. All evaluation
structures are insertion-into-sorted or explicitly sorted; Python
dict/set iteration order is banned from semantic paths (testable by
reordered-input determinism test, DIG-014).

## 49. Validation

The future engine rejects (typed, pre-evaluation): unknown pin,
missing driver (undriven net unless declared stimulus/constant),
invalid drivers (multi-driver, §46), unsupported cycle (§17),
invalid clock/pattern config, negative time, unsorted event input,
invalid state literal, over-budget nets/events/duration/channels,
nonzero delay, sequential kinds, `Z` literals.

## 50. Truth tables

Frozen data, e.g. `AND: {(0,0):0, (0,1):0, (1,0):0, (1,1):1}` as
tuple-keyed mappings in module constants; evaluation is dict lookup
on validated `0/1` ints. `eval`/`exec` for logic evaluation is
prohibited (future AST test mirrors F15-017). Tables are part of the
engine version identity (table change ⇒ version bump ⇒ replay gate).

## 51. Property testing

Per supported gate (design; implementation gate executes):
`NOT(NOT(x))=x`; `AND(x,0)=0`, `AND(x,1)=x`; `OR(x,1)=1`,
`OR(x,0)=x`; `XOR(x,x)=0`, `XOR(x,¬x)=1`; De Morgan spot checks on
composed required gates; duality smoke (`AND↔OR` under NOT push).
Exhaustive over 1-bit inputs (2–4 cases each) — no sampling needed.

## 52. Test matrix — digital engine

```text
DIG-001 logic state literals (0/1; reject others)
DIG-002 constant source drive
DIG-003 toggle stimulus edges
DIG-004 pulse stimulus timing
DIG-005 clock stimulus (period/duty/phase/repeat)
DIG-006 NOT truth table
DIG-007 AND truth table
DIG-008 OR truth table
DIG-009 XOR truth table
DIG-010 NAND/NOR composed equivalence (future-kind reference)
DIG-011 zero-delay propagation chain
DIG-012 multi-driver conflict → INVALID
DIG-013 loop/oscillation detection → INVALID_CYCLE
DIG-014 deterministic ordering (reordered-input same digest)
DIG-015 trace capture completeness (event count == transitions)
DIG-016 edge trigger capture window
DIG-017 trace serialization round-trip (digital-trace/1)
DIG-018 replay EQUIVALENT after save/load
DIG-019 tampered trace → INVALID_SERIALIZATION
DIG-020 resource limits enforced (nets/events/channels/duration)
```

## 53. Test matrix — logic analyzer

```text
LA-001 channel discovery (probes ↔ channels)
LA-002 digital capture over live stimuli
LA-003 rising-edge trigger
LA-004 falling-edge trigger
LA-005 timebase/window correctness
LA-006 multi-channel alignment (shared timestamps)
LA-007 capture limits (pre/post caps refuse overflow honestly)
LA-008 trace serialization via service text-in/out
LA-009 replay EQUIVALENT end-to-end
LA-010 deterministic digest across runs and log levels
```

## 54. Security test matrix

```text
SEC-D01 no eval/exec/compile in digital/ (AST)
SEC-D02 no pickle/marshal/dynamic import (AST + grep)
SEC-D03 truth tables are data (no callables in component defs)
SEC-D04 bounded event queue (overflow → typed failure, fuzz harness)
SEC-D05 bounded capture (oversize stimulus refused pre-run)
SEC-D06 malformed digital-trace/1 refused (schema fuzz)
SEC-D07 tampered trace refused (digest mismatch, golden vectors)
SEC-D08 no secret/host/runtime leakage in trace payloads
```

## 55. Risk matrix

| Risk | Prob. | Impact | Mitigation | Residual | Blocking? |
|:---|:---:|:---:|:---|:---|:---:|
| Architecture coupling (digital leaks into F8-N) | L | H | option C selected; F8-N untouched by construction | low | no |
| F8 regression via shared-convention drift | L | H | conventions copied as frozen constants + version pins; F8 suites re-run at implementation | low | no |
| Event explosion (fast clock × long window) | M | H | `MAX_EVENTS` + pre-run estimate refuse; overflow typed | low | no |
| Memory explosion (dense transitions) | M | M | bounded tuples; per-channel caps; no dynamic growth past caps | low | no |
| Zero-delay cycles / oscillation | M | M | iteration cap → `INVALID_CYCLE` with net set | low | no |
| Nondeterministic event ordering | L | H | canonical `(t, seq, id)`; DIG-014 reordered-input test | low | no |
| Mixed-signal complexity creep | M | H | digital-only v1 normative; adapter separately gated | low | no |
| Trace size (export/share) | M | L | `MAX_*` budgets; canonical compact JSON | low | no |
| UI blocking on large captures | M | M | worker pattern (F15 precedent); render decimation flagged | low | no |
| Serialization compatibility drift | L | M | `name/N` schemas; old loaders kept or explicit INVALID | low | no |
| Digital/analog semantic confusion | M | H | disjoint types; no implicit conversion; threshold adapter explicit | low | no |
| Roadmap placement indecision stalls implementation | M | M | OQ-001 recorded with recommendation; design phase-agnostic | low | **non-blocking for design** |

## 56. Open questions

- **OQ-001** Roadmap phase for implementation (owner decision; recommendation F8-Q after F15, §4). NON-BLOCKING for design.
- **OQ-002** Dedicated error-code sub-namespace vs existing D2 areas (needs D2 amendment if desired; design uses existing areas). NON-BLOCKING.
- **OQ-003** Mixed-signal threshold values per logic family (TTL/CMOS/LVTTL differ; adapter gate decides). NON-BLOCKING.
- **OQ-004** Minimum component set confirmation (NOT/AND/OR/XOR + sources proposed; owner/implementer confirms). NON-BLOCKING.
- **OQ-005** Sequential scope for v2 (FF/latch/counter/register named; timing model TBD at that gate). NON-BLOCKING.
- No BLOCKING questions remain for the design verdict.

## 57. Acceptance criteria

Defined (§63 prompt of the audit brief, itemized here):

```text
[x] digital signal model (§7)
[x] time model (§§9–10, event-driven selected + justified)
[x] logic state model (§8, LOW/HIGH v1, X/Z deferred with conditions)
[x] event model (§15, queue + zero-delay fixed point)
[x] deterministic ordering (§48)
[x] component boundary (§§11, 42–43)
[x] stimulus model (§§18–19)
[x] probe model (§21)
[x] trace model (§§22, 27)
[x] Logic Analyzer contract (§22, trigger/capture §§23–24)
[x] trigger/capture (§§23–24, sampling/aliasing §§25–26)
[x] serialization/replay (§§29–30, F8-N idioms reused)
[x] D2 error integration (§32, existing hierarchy + areas)
[x] D1 architecture compatibility (§40, taxonomy fits, manifest shape)
[x] F15 compatibility (§36, additive, certified bytes untouched)
[x] security (§§34, 54, no-execution architecture)
[x] resource limits (§§24, 31, bounded by construction)
[x] test strategy (§§51–54, DIG/LA/SEC matrices)
[x] extension strategy (§§5–6, 41, C selected + justified)
[x] roadmap placement (§4, pending documented, recommendation explicit)
```

## 58. Invariants

| ID | Property | Future check |
|:---|:---|:---|
| DIG-I001 | deterministic digital state (same inputs ⇒ same trace) | DIG-014/015 |
| DIG-I002 | deterministic event ordering `(t, seq, id)` | DIG-014 |
| DIG-I003 | bounded simulation (nets/events/duration/channels) | DIG-020 |
| DIG-I004 | no arbitrary execution (tables/patterns are data) | SEC-D01…D03 |
| DIG-I005 | no UI/domain coupling (service mediation) | LA-002 + edge test |
| DIG-I006 | no logging dependency in domain | static test (D2-I003 pattern) |
| DIG-I007 | no fake traces (every event from engine evaluation) | DIG-015 |
| DIG-I008 | no hidden transitions (decimation always flagged) | LA-007 |
| DIG-I009 | stable serialization (`digital-trace/1` round-trip) | DIG-017 |
| DIG-I010 | stable replay (EQUIVALENT semantics reused) | DIG-018/LA-009 |
| DIG-I011 | F8 preservation (F8-N/F8-Px untouched) | F8 suites green at implementation |
| DIG-I012 | F15 preservation (additive only) | F15 suite green at implementation |
| DIG-I013 | D2 compatibility (existing hierarchy + areas) | converter test |
| DIG-I014 | explicit init (no magic defaults for state) | validation tests (§49) |
| DIG-I015 | multi-driver is an error, never silent resolution | DIG-012 |
| DIG-I016 | loops detected deterministically, never infinite | DIG-013 |
| DIG-I017 | time is Decimal seconds, never float | static + round-trip tests |
| DIG-I018 | scope/LA types disjoint (no analog/digital confusion) | type tests |
| DIG-I019 | capture windows explicit (no infinite buffers) | LA-007/DIG-020 |
| DIG-I020 | engine version pins truth behavior (table change ⇒ bump) | replay version gate |

## 59. Final verdict

All acceptance items closed on repository evidence (§§3–4); no
implementation created; no certified file modified; no BLOCKING open
questions (OQ-001…OQ-005 fenced as non-blocking); F15/F8/D1/D2/D3
intact by construction (design-only phase, verified §60).

FINAL VERDICT: DIGITAL ENGINE DESIGN READY
