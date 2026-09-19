# GATE-F8N-DESIGN

Design gate for **F8-N — Virtual Laboratory**. Documentation only: no code under `src/` was
created or modified, no experimental code was written to "test" the design.

## Baseline

- Repository `Damaga2005/AcademicCore`, branch `main`, baseline **`c43483b`**
  (`docs: certify F8-M`), as expected by the mandate.
- Certified: F0–F7, F8-A … F8-M (gates on disk through `GATE-F8M.md`; roadmap §6.1 lists F8-M
  CERTIFICADO and marks **F8-N (Siguiente Fase)**).
- Auditable facts (read from the code, not from documentation) that drive the design are collected
  in *Certified Dependencies → Audit findings*.

## Git State

`git status --short` empty; branch `main`; `HEAD == origin/main == c43483b` (after `git fetch`);
working tree clean at audit time. No commits newer than the F8-M certification were found, so the
F8-N preconditions are unchanged. The only output of this phase is this file plus one local commit.

## Certified Dependencies

| Layer | Entry points reused (all read-only, none modified by F8-N) | Contract inherited |
|:---|:---|:---|
| `circuit.py` | `Circuit`, `Component`, `COMPONENT_PINS`; `parameters["wave"]` on V/I | refs `^[RCLVIDQEGHFOTMJ]\d+$`, pins, nets; frozen-shallow `Component` (dicts are mutable → F8-N copies) |
| `units.py` | `Quantity`, `Unit`, dimension tuples (`VOLTAGE`, `CURRENT`, `RESISTANCE`, `FREQUENCY`, `TIME`, …) | `Decimal` values, integer-exponent dimension tuples; no dB/rad/deg units |
| F8-H/I/K DC | `mna.nonlinear.solve_nonlinear_dc`, `solve_nonlinear_dc_state`, `NonlinearResult/Status` | Q1 (RTOL 1E-9, ATOL 1E-12, STOL 1E-12, MAX_ITER 50, MAX_BACKTRACK 10), zero-vector start, statuses CONVERGED/MAX_ITERATIONS/DIVERGED/SINGULAR_JACOBIAN/INVALID/UNSUPPORTED |
| F8-J AC | `ac.small_signal.solve_small_signal_ac`, `SmallSignalACResult.voltage_of/current_of`, `ACStatus` | `e^{+jωt}`, PEAK phasors, phase in (−π, π], `DecimalComplex`, HP mode |
| F8-D5/D6 | `ac.response.frequency_response`, `ResponseDefinition`, `SweepResult`; `ac.bode.analyze_bode`, `magnitude_db`, `unwrap_phases`, `half_power_threshold_db`, `crossing_brackets`, `threshold_bands` | per-point independent solves, failed points recorded, dB with explicit −∞ category, brackets never interpolated, bandwidth as an interval |
| F8-L transient | `mna.transient.solve_transient`, `TransientConfig`, `TransientResult`, `TransientStatus`, `MAX_TRANSIENT_STEPS = 100000`; waves `dc/step/pulse/sine` in `parameters["wave"]` | Decimal seconds, adaptive LTE steps ⇒ **non-uniform committed time grid**, history committed only |
| F8-M | `mna.analysis`: `solve_dc_sweep`, `solve_param_sweep`, `solve_worst_case`, `run_monte_carlo_native`, `ParamAddress`, `ObservableSpec`, `GridSpec`, `substitute`, `circuit_digest`, `solve_point`, `MAX_*`; `mna.sensitivity`: `solve_dc_sensitivity`, `solve_ac_sensitivity` | closed parameter registry, seed required, failed points/iterations recorded, `digest` per result, bit-for-bit determinism |

### Audit findings (each one constrains the design)

1. **No lab/session/instrument/oscilloscope code exists** in `domain/engineering/` (the only grep
   hits for "session/laborator" are unrelated text in `gum.py`). F8-N is greenfield; there is no
   double source of truth to reconcile.
2. `TransientResult` exposes **node voltages and inductor currents only**; R/C/V/I/D/Q/M/J branch
   currents are not stored. Resistor current is exactly derivable `(V1−V2)/R`; capacitor current,
   source aux currents and device currents are **not** available without changing F8-L (forbidden).
3. `TransientResult.value_at(net, t)` returns the **nearest committed sample** (no interpolation).
   It must not be used for measurements or display resampling (it would silently quantise time).
4. Committed transient samples are **non-uniform** (adaptive steps). "Samples per screen" and
   "solver timestep" are unrelated quantities and must stay decoupled (§ Instrument/Oscilloscope).
5. The wave spec is a validated `dict` in `Component.parameters["wave"]`
   (`dc/step/pulse/sine`; validation is private to `transient.py`). The sine has **no phase and no
   pre-delay hold**: `v = vo + va·sin(2πf(t−td))` for every `t` (delay = time shift, `td ≥ 0`).
6. Engines expose **no cooperative-cancellation hooks or progress callbacks**; each `solve_*` runs
   to completion. Mid-run cancellation would require threads/process isolation, which F8-N does not
   introduce (§ Error Model).
7. `ac.response.frequency_response` (F8-D5) is defined for the linear AC domain (R/L/C/V/I/E/G/H/F/
   O/T); F8-J handles nonlinear devices at one frequency. There is **no nonlinear AC sweep** engine.
8. `test_architecture.py` enforces: `domain/` imports no UI/application/infrastructure, stdlib-only
   AST rules, no engine cycles. F8-N core must live in `domain/engineering/` and satisfy these.
9. F8-M results already carry `digest` and `provenance`; F8-L/F8-H results carry
   `provenance` (`topology_digest`, `solver_digest`). The lab reuses these digests, never recomputes
   solver internals.
10. Certified `float(` is absent from `mna/` and `ac/small_signal.py`; `simulation.py` (F7, ngspice
    backend, float-mediated) is a different, netlist-oriented world and is **not** an F8-N dependency.

## F8-N Scope

F8-N is the **orchestration and experimentation layer** on top of the certified engines. It adds
*no solver, no device model, no waveform generator, no sweep/MC/sensitivity engine*. It adds:

| ID | Capability |
|:---|:---|
| L1 | `LaboratorySession`: immutable, value-semantics container of a circuit, experiment definitions and run records |
| L2 | `ExperimentDefinition`: typed, serialisable, content-addressed description (circuit overrides, analysis, stimuli, probes, instruments, measurements, seed, tolerances) |
| L3 | `Run`: one deterministic execution of a definition through an existing engine, with status, result and provenance |
| L4 | Probes (`VoltageProbe`, `CurrentProbe`, `ParameterProbe`) and ideal virtual instruments (voltmeter, ammeter, oscilloscope, frequency-response viewer, sweep viewer) as **pure views** over run results |
| L5 | Measurement functions on waveforms / phasors / sweeps with exact mathematical definitions |
| L6 | `StimulusSpec` + `function_generator(...)` factory that *configures existing* V/I waveforms |
| L7 | Canonical serialisation (JSON schema `f8n-lab/1`), CSV export of tables/waveforms, digests |
| L8 | Same-version deterministic replay and structured comparison |
| L9 | Experiment records with annotations (objectives, notes, reference values) kept outside the mathematical digests |

Supported analyses (closed enum `AnalysisKind`): `OP`, `DC_SWEEP` (M1), `PARAM_SWEEP` (M2),
`CORNERS` (M3), `SENS_DC` (M4), `SENS_AC` (M4-AC), `MONTE_CARLO` (M5), `AC_POINT` (F8-J),
`AC_SWEEP` (F8-D5/D6, linear circuits only), `TRANSIENT` (F8-L).

## Out of Scope

Each item: **OUT OF SCOPE**, reason, possible future home.

| Item | Reason | Future home |
|:---|:---|:---|
| GUI, web frontend, mobile app, CLI, notebooks | Presentation layer; domain must stay UI-free (`test_architecture`) | `ui/` / a later presentation phase consuming the lab API |
| Plot rendering | Needs float/graphics libraries; F8-N only produces *reading view-models* | presentation layer (float boundary documented there) |
| Real-time hardware, physical DAQ | No hardware model | never in AcademicCore core |
| SPICE netlist import/export | Netlists do not carry device parameters (F8-H Q3); would create a second circuit source of truth | future interoperability phase |
| Cloud execution, network service, distributed simulation, multi-user collaboration, authentication | Network/concurrency out of policy | infrastructure layer, F9+ |
| Automatic grading, AI tutor | Pedagogy ≠ simulation; F8-N only *stores* reference values and computes `Comparison` arithmetic | `documents/`/tutoring layer |
| Instrument error/noise/loading models (gain error, offset, probe capacitance, finite input impedance, bandwidth limits) | No certified noise/probe models; would fake physics | future "non-ideal instruments" phase |
| Nonlinear AC sweeps | No engine (finding 7); composing one would be a second frequency solver | F8-J extension |
| Transient branch currents other than R and L | Not in `TransientResult` (finding 2); changing F8-L is forbidden | F8-L extension phase |
| Topology editing inside a session | Circuit is fixed per session; only registry-parameter overrides and stimuli are editable | new session / future editor phase |
| Mid-run cancellation | No engine hooks, no threads (finding 6) | process-isolating runner in an infrastructure layer |
| Power/energy measurements, FFT/THD, XY mode, math channels | Not required for the certified experiment set; each needs its own definition and validation | later lab-measurements phase |
| F8-O (GUM/metrology) | Explicitly excluded | F8-O |

## Architecture

Real map (audited) and F8-N placement:

```text
Circuit ─► (F8-M substitute / stimulus override: fresh copy) ─► Problem (build_mna_problem*)
        ─► Analysis (nonlinear | small_signal | response | transient | analysis(F8-M))
        ─► Solver (Newton / linsolve / implicit integration)
        ─► Result (NonlinearResult | SmallSignalACResult | SweepResult | TransientResult | F8-M results)
        ─► Reporting / provenance (digests, to_dict)
                         ▲
                         │  read-only (typed adapters, no re-solve)
        ┌────────────────┴───────────────────────────────┐
        │ NEW: domain/engineering/lab/                    │
        │   model.py       entities, enums, budgets       │
        │   stimulus.py    StimulusSpec, function_generator│
        │   run.py         analysis dispatch (allowlist)  │
        │   waveform.py    Waveform, PL-signal math       │
        │   measure.py     measurement functions          │
        │   instruments.py probes + instrument readings   │
        │   session.py     session operations             │
        │   serialize.py   canonical JSON/CSV, digests    │
        │   replay.py      load/replay/compare            │
        └─────────────────────────────────────────────────┘
```

Rules: (a) `lab/` imports engines; engines never import `lab/`. (b) The lab never re-implements
Newton, MNA, transient, AC, sweep, sensitivity or MC; each run is exactly one call (or the
documented composition) of a certified entry point. (c) Instruments and measurements are **pure
functions of a run result**; they cannot trigger solves. (d) The lab layer has no global state, no
I/O except explicit `to_document`/`from_document`/CSV string production (file I/O belongs to callers).
(e) `lab/` stays stdlib + certified-engine only.

## Laboratory Model

Formal entities. "Ser." = serialised in schema `f8n-lab/1`; "Digest" = enters the reproducibility
digest.

| Entity | Identity | Lifecycle | Inputs → Outputs | Mutability | Ser. | Digest | Owner | Errors |
|:---|:---|:---|:---|:---|:---:|:---:|:---|:---|
| **Laboratory** | none (no object): the *API surface* = module-level pure functions of `lab/` | n/a | — | stateless | — | — | — | — |
| **LaboratorySession** | `session_id` (caller-supplied validated string; the lab never generates ids) | OPEN → CLOSED | circuit + operations → new session value | **immutable value**: every operation returns a new session | ✓ | circuit only (via experiments) | caller | `LabConfigError` |
| **CircuitSpec** | `circuit_digest` (F8-M helper) | created with session | `Circuit` → canonical typed snapshot | immutable (deep copy at creation) | ✓ | ✓ | session | `LabConfigError(INVALID_CIRCUIT)` |
| **ExperimentDefinition** | `experiment_id = "exp-" + digest[:16]` (content-addressed) | DEFINED (never edited; a change = new definition) | see Experiment Model | immutable | ✓ | ✓ | session | `LabConfigError` |
| **Run** | `run_id = f"{experiment_id}#{n}"`, `n` = 1-based count of previous runs of that experiment in the session | created complete (no in-flight state exposed) | definition → result | immutable | ✓ | result part | session | status field |
| **Measurement** (spec) | position + key in the definition | part of definition | spec → `MeasurementResult` | immutable | ✓ | ✓ | definition | `INVALID_MEASUREMENT` |
| **MeasurementResult** | `(run_id, measurement key)` | computed with the run | waveform/phasor/sweep → `Scalar`/`None`+status | immutable | ✓ | ✓ | run | status |
| **Instrument** | key in the definition | part of definition | probes+config → `InstrumentReading` | immutable config | ✓ | ✓ | definition | `LabConfigError` |
| **Probe** | key in the definition | part of definition | source ref → signal | immutable | ✓ | ✓ | definition | `LabConfigError` |
| **Stimulus** | `(source_ref)` | part of definition | wave/phasor override on a V/I source | immutable | ✓ | ✓ | definition | `LabConfigError` |
| **Observation / Annotation** | `(run_id, index)` append-only | appended | text/reference values → record | append-only (new session value) | ✓ | **✗** | record | `LabConfigError` |
| **ExperimentRecord** | `(experiment_id)` | grows with runs/annotations | definition + runs + annotations | immutable value | ✓ | reproducibility part only | session | — |

## Session Model

`LaboratorySession` fields (derived from the architecture: circuit fixed, definitions
content-addressed, runs append-only):

`session_id: str`, `circuit: CircuitSpec`, `experiments: tuple[ExperimentDefinition, ...]`
(insertion order kept, unique by `experiment_id`), `records: tuple[ExperimentRecord, ...]` (one per
experiment that has runs/annotations), `metadata: tuple[tuple[str,str],...]` (sorted, never digested),
`state: OPEN|CLOSED`, `schema: "f8n-lab/1"`.

Operations (all pure; each returns a **new** session; failures return the *unchanged* session plus
a typed status — nothing is half-applied):

| Operation | Signature (Prompt-2 contract) | Semantics |
|:---|:---|:---|
| create | `create_session(session_id, circuit, *, metadata=()) -> LaboratorySession` | validates id (`^[A-Za-z0-9_.-]{1,64}$`), builds `CircuitSpec` (deep copy), structural DC/AC precheck deferred to run |
| modify | `add_experiment(session, definition) -> (LaboratorySession, ValidationReport)` | full static validation (no solve); duplicates by digest are idempotent (same id) |
| execute | `run_experiment(session, experiment_id) -> (LaboratorySession, Run)` | builds immutable execution snapshot, dispatches, appends the `Run` |
| annotate | `annotate(session, run_id, Annotation) -> LaboratorySession` | append-only, not digested |
| reset | `reset(session) -> LaboratorySession` | drops runs/annotations, keeps circuit and definitions |
| snapshot | `to_document(session) -> dict` | canonical JSON-safe document (the session *is* its own snapshot value) |
| clone | `clone_session(session, new_session_id) -> LaboratorySession` | same content, new id; recorded in `metadata["cloned_from"]` |
| branch | `branch_experiment(session, experiment_id, edits) -> (LaboratorySession, str)` | new definition = old + explicit edit set; records `derived_from` in metadata (not digested); the original definition is untouched |
| replay | see *Replay* | |
| close | `close_session(session) -> LaboratorySession` (state CLOSED) | every later operation except `to_document` raises `LabConfigError(SESSION_CLOSED)` |

No session-level mutable state exists, so one session cannot contaminate another (they share
nothing but immutable values).

## Experiment Model

`ExperimentDefinition` (frozen dataclass, all typed, no free-form Python):

| Field | Type | Meaning / validation |
|:---|:---|:---|
| `label` | `str` (≤ 128) | display only, **not digested** |
| `analysis` | typed union below | exactly one analysis |
| `overrides` | `tuple[(ParamAddress, Decimal\|Quantity), ...]` | applied with F8-M `substitute` (closed registry, domain-checked); sorted by key; duplicates → error |
| `stimuli` | `tuple[StimulusSpec, ...]` | at most one per source; sorted by `source_ref` |
| `probes` | `tuple[(key, Probe), ...]` | unique keys |
| `instruments` | `tuple[(key, Instrument), ...]` | reference probe keys |
| `measurements` | `tuple[(key, MeasurementSpec), ...]` | reference probe keys |
| `seed` | `int \| None` | **required** (int ≥ 0) iff analysis is `MONTE_CARLO`; forbidden otherwise (a seed on a deterministic analysis is a config error: no silent unused seed) |
| `tolerances` | derived, **not user-editable** | recorded from certified constants (Q1, `TransientConfig` reltol/abstol) in provenance; the lab never overrides Q1 |

Analysis union (each wraps the *certified config object* — no re-invention):

| `AnalysisKind` | Payload | Engine call |
|:---|:---|:---|
| `OP` | — | `solve_nonlinear_dc_state(dc_equivalent(circuit))` via F8-M `solve_point` semantics |
| `DC_SWEEP` | `SweepConfig` | `solve_dc_sweep` |
| `PARAM_SWEEP` | `ParamSweepConfig` | `solve_param_sweep` |
| `CORNERS` | `WorstCaseConfig` | `solve_worst_case` |
| `SENS_DC` | `SensitivityConfig` | `solve_dc_sensitivity` |
| `SENS_AC` | `ACSensitivityConfig` | `solve_ac_sensitivity` |
| `MONTE_CARLO` | `MCConfig` (seed injected from `seed`) | `run_monte_carlo_native` |
| `AC_POINT` | `frequency: Quantity(Hz)` | `solve_small_signal_ac` |
| `AC_SWEEP` | `frequencies` (`GridSpec`-like: list / log / linear via F8-D5/D6 generators), `input_source`, `output (voltage_between)` | `frequency_response` + `analyze_bode` |
| `TRANSIENT` | `TransientConfig` | `solve_transient` |

Independence from global state: a definition contains everything needed to run; the run reads no
environment, clock, locale, random source or process state.

## Run Model

`Run` (frozen): `run_id`, `experiment_id`, `session_id` *(identity, not digested)*,
`experiment_digest` (input digest), `analysis_kind`, `seed`, `status: RunStatus`,
`engine_status: str | None` (verbatim engine status, e.g. `diverged`, `singular_jacobian`),
`result: RunResult | None`, `measurements: tuple[MeasurementResult, ...]`,
`readings: tuple[InstrumentReading, ...]`, `diagnostics: tuple[str,...]`,
`provenance: dict`, `result_digest: str`.

- **Identity** = `run_id`, `experiment_id`, `session_id`. **Inputs** = `experiment_digest`, `seed`.
  **Outputs** = `status`, `result`, `measurements`, `readings`, `result_digest`.
- The **reproducibility digest** of a run = `sha256("f8n/run/1" ‖ experiment_digest ‖ canonical(
  status, engine_status, result payload, measurements))`. `run_id`, `session_id`, labels, notes and
  metadata are excluded.
- `readings` (instrument views) are derived deterministically from `result`; they are serialised
  but excluded from `result_digest` (they are recomputable views; the digest covers the numerical
  payload).
- One experiment may have many runs; because everything is deterministic, repeated runs of the same
  definition have equal `result_digest` (that is a test, not an assumption).

**Execution snapshot** (definition → immutable snapshot → run → result): `run_experiment` builds a
*fresh* circuit `C_run = apply(stimuli, apply(overrides, copy(session.circuit)))` (never touches
`session.circuit` nor any caller object), freezes it with its `circuit_digest`, calls exactly one
engine, and only then constructs the `Run`. Mutations are therefore explicit (overrides/stimuli in
the definition), reproducible (digested) and recorded (provenance lists them).

## Instrument Model

All instruments are **ideal, pure views**: `read(run_result, config) -> InstrumentReading`. They
never alter a circuit, never solve, never depend on wall clock. Declared idealisations (normative):
infinite bandwidth, no loading, no noise, no gain/offset error, exact `Decimal` readout.
Presentation rounding is a presentation-layer concern (OUT OF SCOPE).

| Instrument | Valid analyses | Input | Semantics / units | Sampling / resolution | Output |
|:---|:---|:---|:---|:---|:---|
| **Voltmeter** | `OP`, `DC_SWEEP` (one reading per point), `AC_POINT` (phasor), `TRANSIENT` (final/at-time via `at` param, PL-interpolated) | one `VoltageProbe` | `V(p,n)`, V; AC: complex peak phasor, V | exact; transient reading at `t` uses piecewise-linear interpolation, `t` must lie in `[t0, t_stop]` (no extrapolation) | `ScalarReading` / `ComplexReading` |
| **Ammeter** | same | one `CurrentProbe` | branch current of a *component branch*, A, project sign convention; no series insertion, no fictitious shunt | exact | `ScalarReading` / `ComplexReading` |
| **Oscilloscope** | `TRANSIENT` only | 1–`MAX_SCOPE_CHANNELS` (4) channels of `VoltageProbe`/`CurrentProbe`(R,L) | see next section | display grid, independent of solver steps | `ScopeReading` |
| **FrequencyResponseViewer** | `AC_SWEEP` | one transfer definition | per frequency: `H`, `|H|`, dB, phase (rad, deg, unwrapped via F8-D6), bandwidth interval, failed points flagged | frequencies exactly those requested | `BodeReading` (view over `analyze_bode`) |
| **SweepViewer** | `DC_SWEEP`, `PARAM_SWEEP`, `CORNERS`, `MONTE_CARLO`(per-sample table + F8-M statistics), `SENS_*` | one probe/observable | x = swept parameter value(s), y = probe value, status per point | exact points of the F8-M result | `SweepReading` (table view; plotting out of scope) |

Frequency has no probe of its own: it is the *axis* of `AC_SWEEP` and the *parameter* of `AC_POINT`
(deviation from the mandate's candidate `FrequencyProbe`, justified in *Deviations*).

## Probe Model

| Probe | Source | Observable / units | Sampling | Validity | Error behaviour |
|:---|:---|:---|:---|:---|:---|
| `VoltageProbe(p, n)` | two nets of the circuit (`n` defaults to the reference net) | `V(p,n) = V_p − V_n`, V (AC: complex peak) | one value per analysis point / per committed transient sample | both nets exist; `p ≠ n` | unknown net → `LabConfigError(INVALID_PROBE)` at `add_experiment` |
| `CurrentProbe(branch)` | component ref (`"R1"`, `"V1"`, `"D1"`, `"Q1:C"`, `"M1:D"`, `"J1:S"`, `"T1:1"`, `"L1"`) | A, project convention (below) | as above | allowed set per analysis (below) | branch not offered by that analysis → `UNSUPPORTED` reading with reason (never 0) |
| `ParameterProbe(ParamAddress)` | closed F8-M registry | nominal parameter value, dimension from registry | constant per run; in sweeps = axis value | address resolves | invalid address → `LabConfigError(INVALID_PROBE)` |

`WaveformProbe` is **not** an entity: a probe evaluated on a transient result *is* a `Waveform`
(the domain is a property of the analysis, not of the probe). `FrequencyProbe` is not an entity
(frequency is the axis). Decision recorded as a deviation.

Current-probe availability (audited against result structures):

| Branch | OP/DC/sweeps (`NonlinearResult`, F8-M) | AC point (F8-J) | Transient (F8-L) |
|:---|:---:|:---:|:---:|
| R | ✓ `(V1−V2)/R` | ✓ | ✓ derived `(V1(t)−V2(t))/R` |
| V/E/H/O aux, T legs | ✓ MNA unknown | ✓ | ✗ UNSUPPORTED (not stored) |
| I source | ✓ (reported `−Is`) | ✓ | ✗ UNSUPPORTED |
| L | ✓ (DC short aux) | ✓ | ✓ `inductor_currents` |
| C | ✗ (open in DC: 0 A exactly, reported) | ✓ | ✗ UNSUPPORTED |
| D/Q/M/J terminals | ✓ (`device_current` observable / result branch currents) | ✓ small-signal | ✗ UNSUPPORTED |

## Measurement Semantics

**Simulator state vs measurement.** State = certified result objects (unknown vectors, histories).
Measurement = a *declared pure function* of state. A measurement never feeds back.

* Ideal voltmeter: `V(p,n) = V_p − V_n` (`V_ground = 0`), draws no current, no circuit change.
* Ideal ammeter: reads the certified branch current of a component (table above). The project
  sign conventions are inherited **verbatim**: resistor/L/C `pin1 → pin2`; V/E/H `+ → −` (MNA aux
  unknown); independent I reported `−Is` (F8-B rule); D `A → K`; Q/M/J current *entering* the named
  terminal; T legs `1→2`, `3→4`. A `sign` field is not offered (no silent flipping).
* No measurement resistor is ever inserted.

## Stimulus Model

`StimulusSpec(source_ref, kind ∈ {DC, STEP, PULSE, SINE, AC}, params)` — a **typed configuration
that is translated into the existing `parameters["wave"]` dict / `phase` parameters** of a V or I
source in the run copy; the certified `_wave_value` implementation is the only waveform generator.

| kind | params (Decimal times in s; levels are `Quantity` of the source dimension) | Existing implementation |
|:---|:---|:---|
| `DC` | `value` (replaces `Component.value`) | F8-B/H |
| `STEP` | `v1, v2, t0` | F8-L `step` |
| `PULSE` | `v1, v2, td, tr, tf, width, period` | F8-L `pulse` (one-shot iff `period = 0`) |
| `SINE` | `vo, va, freq, td` | F8-L `sine` |
| `AC` | `magnitude` (=`value`, peak), `phase`, `phase_unit ∈ {deg, rad}` | F8-D3/J `phase`/`phase_unit` |

`function_generator(source_ref, waveform, *, amplitude, offset, frequency, phase_lag, duty, delay,
rise, fall) -> StimulusSpec` is a **pure factory** (no waveform code of its own):

* `sine`: `va = amplitude`, `vo = offset`, `freq = frequency`, `td = delay + phase_lag_deg/(360·frequency)`
  (only **lag** ≥ 0 representable, since `td ≥ 0`; a phase lead → `LabConfigError`). "Delay" is a
  time *shift*, not a hold (audit finding 5) and is documented as such.
* `pulse`/square: `v1 = offset`, `v2 = offset + amplitude`, `period = 1/frequency`,
  `td = delay`, `tr = rise`, `tf = fall`, `width = duty·period − (tr+tf)/2` where `duty ∈ (0,1)` is
  defined **at the 50 % amplitude crossings**; `width < 0` → `LabConfigError`.
* `dc`: `offset`. Triangle/noise/arbitrary waves: OUT OF SCOPE (no certified generator).

Only V/I sources are stimulable. Setting a stimulus on any other component → `LabConfigError`.
A stimulus on an analysis that ignores waves (`OP`, sweeps) uses the DC `value` only and the report
states it (`stimulus_ignored_by_analysis`), it does not silently drop it.

## Analysis Integration

### F8-H → F8-L

| Engine | Laboratory use (orchestration only) |
|:---|:---|
| F8-H (Shockley Newton) | `OP`; each sweep/MC/corner point; source of Q1 constants in provenance |
| F8-I (BJT) | same paths; `device_current` probes `Q:C/B/E` |
| F8-J (small-signal AC) | `AC_POINT` (any F8-J-supported circuit, nonlinear included: DC op is computed by the engine); phasor probes |
| F8-K (MOS/JFET/diode kinds) | same paths as F8-H/I; probes `M:D/G/S/B`, `J:D/G/S`, `D`; parameters editable through the F8-M registry |
| F8-L (transient) | `TRANSIENT`: exactly one `solve_transient`; waveforms; scope/measurements; waves from `StimulusSpec` |

### F8-M

| F8-M analysis | Laboratory input | Laboratory output |
|:---|:---|:---|
| M1 DC sweep | `AnalysisKind.DC_SWEEP` + `SweepConfig` (target V/I, `GridSpec`), probes/observables | `Run.result` wraps the F8-M `SweepResult` **unchanged** (`==` equality of `to_dict()`); `SweepReading` table; per-point failures kept |
| M2 parameter sweep | `PARAM_SWEEP` + `ParamSweepConfig` | wrapped `SweepResult`; `SweepReading` |
| M3 corners | `CORNERS` + `WorstCaseConfig` | wrapped `WorstCaseResult` incl. the corner-extremum honesty text, never rephrased as "worst case is X"; `SweepReading` of corners |
| M4 sensitivity | `SENS_DC` + `SensitivityConfig` | wrapped `SensitivityResult`; measurement table of `dO/dp`, normalised, with dimension tuples |
| M4-AC | `SENS_AC` + `ACSensitivityConfig` | wrapped `ACSensitivityResult` (magnitude/phase/dB derivatives) |
| M5 Monte Carlo | `MONTE_CARLO` + `MCConfig` (seed from `definition.seed`) | wrapped `MCResult` (plan digest, failures, statistics); `SweepReading` per sample |

Observables of F8-M configs are the F8-M `ObservableSpec`s; the lab **derives them from probes**
(`VoltageProbe → node_voltage`, `CurrentProbe → aux/resistor/device_current`) and rejects probes
that F8-M cannot observe (`UNSUPPORTED`). No F8-M logic is duplicated: the lab supplies configs and
reads results.

### Transient result → waveform → measurement → visualisation

```text
TransientResult (committed, non-uniform times)
   → Waveform(times, values, dim)                     [no resampling, exact copy]
   → Measurement (defined on the committed samples,   [independent of display]
                  piecewise-linear signal model)
   → ScopeReading (display grid, PL interpolation)    [presentation only]
```

**Solver timestep vs display timestep** are separate by construction: the scope's `sample_count`,
window and scales are *reading* parameters. `TransientConfig` is part of the definition; changing
any scope field changes the reading, never the run (`result_digest` unchanged — test N-030).

### Frequency analysis
`AC_POINT` consumes `SmallSignalACResult.voltage_of` (peak phasors). `AC_SWEEP` requires a linear
circuit and calls `frequency_response(circuit, ResponseDefinition("transfer", (input_ep, output_ep,
input_source)), frequencies)` then `analyze_bode(sweep, db_threshold)`. The lab writes no
frequency solver and no phase unwrap (uses `unwrap_phases`). Nonlinear circuits in `AC_SWEEP` →
`UNSUPPORTED` (finding 7).

## Oscilloscope model

`Oscilloscope(channels, time_window | trigger, sample_count)`:

| Element | Definition |
|:---|:---|
| **Channel** `ScopeChannel(probe_key, volts_per_div, offset, coupling ∈ {DC, AC})` | signal `x_c(t)`; `volts_per_div > 0` (per-division unit = probe unit), `offset` in probe unit. Scaling is display-only: `y_div(t) = (x'_c(t) + offset)/volts_per_div` |
| **Coupling** | DC: `x' = x`. AC: `x'(t) = x(t) − mean_W(x)` over the *display window* `W` (mean per the measurement definition below) — removes the window DC component |
| **Time window** | `TimeWindow(t_start, t_end)`, `t_start < t_end`, both within `[t_0, t_stop]` (no extrapolation → `OUT_OF_RANGE`) |
| **Sample interval** | `sample_count = n ≥ 2`, `n ≤ MAX_DISPLAY_SAMPLES`; display grid `t_k = t_start + k·Δ`, `Δ = (t_end − t_start)/(n−1)`, `k = 0…n−1` (Decimal, last point exactly `t_end`) |
| **Sample values** | piecewise-linear interpolation of the *committed* samples; exact hits return the committed value unchanged |
| **Clipping flag** | `clipped_k = |y_div(t_k)| > vertical_divisions/2` with `vertical_divisions = 8` (reading constant, recorded) — flags only, values are never clipped |
| **Measurement functions** | attached via `MeasurementSpec` on the channel signal, computed on committed samples over `[t_start, t_end]` (never on the display grid) |

`ScopeReading` carries, per channel: display times, raw values, coupled values, `y_div`, clipped
flags, unit label, and the trigger record.

### Trigger

Mathematics on the (coupled) trigger-channel signal `x(t)`, level `L` (probe unit), slope `s`, treated as the
piecewise-linear signal through committed samples `(t_i, x_i)`:

* A **rising crossing** occurs in segment `i` iff `x_i < L ≤ x_{i+1}`, at
  `t_c = t_i + (L − x_i)(t_{i+1} − t_i)/(x_{i+1} − x_i)` (exact rational-Decimal formula, `x_{i+1} ≠ x_i`
  guaranteed by the strict inequality). **Falling**: `x_i > L ≥ x_{i+1}`, same formula. `EITHER` = union.
  A sample exactly equal to `L` belongs to the segment where the inequality above holds (no double
  counting: the crossing is attributed to the segment that *ends* at `L` for rising, *ends* at `L`
  for falling).
* `TriggerSpec(source_probe_key, level, slope, pre, post, hysteresis ≥ 0)`; `pre, post ≥ 0` in seconds.
  Hysteresis `h` arms the next crossing only after the signal has been `< L − h` (rising) or `> L + h`
  (falling) since the previous accepted crossing; `h = 0` (default) = plain crossing detection.
* The **trigger time** is the first accepted crossing with `t_c ≥ t_0 + pre` (so the pre-trigger
  window exists). The display window is `[t_c − pre, t_c + post]`; it must lie inside `[t_0, t_stop]`.
* No crossing found → `ScopeReading.status = NO_TRIGGER`, **no data**, no free-run fallback (mode
  "normal"; "auto" is OUT OF SCOPE). Window not inside the simulated span → `OUT_OF_RANGE`.
* `TriggerSpec = None` requires an explicit `TimeWindow` (no implicit window guessing).

## Measurement Functions

Signal model for waveform measurements: **committed samples `(t_i, x_i)`, `i = 0…N−1`, joined by
straight segments** (piecewise linear, "PL"). All integrals below are *exact* for that model; the
difference from the true continuous signal is bounded by the F8-L LTE control and is a property of
the run, not of the measurement. Window `W = [a, b]`, `t_0 ≤ a < b ≤ t_{N−1}` (default the whole
run); window ends inside a segment use the interpolated value (exact under PL). Everything is
`Decimal` under `make_context()`; undefined results are `None` with a reason — **never 0**.

| Key | Definition (per project conventions) | Input requirements | Unit | Edge cases / errors |
|:---|:---|:---|:---|:---|
| `max`, `min` | `max/min` over the samples in `W` plus interpolated window ends (extremes of a PL signal occur at breakpoints) | ≥ 1 sample, `a<b` | probe unit | `a≥b` → `INVALID_MEASUREMENT` |
| `pp` | `max − min` | as above | probe unit (**peak-to-peak, declared**) | — |
| `mean` | `(1/(b−a)) ∫ x dt = (1/(b−a)) Σ h_j (x_j + x_{j+1})/2` | window with ≥ 2 breakpoints | probe unit | — |
| `rms` | `sqrt[(1/(b−a)) ∫ x² dt]`, `∫ x² dt = Σ h_j (x_j² + x_j x_{j+1} + x_{j+1}²)/3` (exact for PL); `sqrt` via context `sqrt` | as above | probe unit (**RMS, declared; not amplitude**) | — |
| `crossings(level, slope)` | list of crossing times as in *Trigger* | ≥ 2 samples | s | none found → empty list (status OK, count 0) |
| `frequency`, `period` | with rising crossings `t_1 < … < t_K` of `level` (default `(max+min)/2` over `W`, `hysteresis` optional): `period = (t_K − t_1)/(K−1)`, `frequency = 1/period` | `K ≥ 2` | s / Hz | `K < 2` → `UNDEFINED("fewer than two rising crossings")`; period ≤ 0 impossible by strict ordering |
| `rise_time(low_frac, high_frac, v_low, v_high)` | `Δ = v_high − v_low`; `t_lo` = first rising crossing of `v_low + low_frac·Δ`, `t_hi` = first rising crossing of `v_low + high_frac·Δ` at time `≥ t_lo`; `rise = t_hi − t_lo`. `low_frac, high_frac` are **required** parameters with `0<low<high<1` (helper `rise_time_10_90` fixes 0.1/0.9 — no hidden default). `v_low, v_high` explicit, or `AUTO` = `min/max` over `W` (valid only for a single clean edge; recorded) | `Δ > 0` | s | edge not found → `UNDEFINED`; `Δ ≤ 0` → `INVALID_MEASUREMENT` |
| `fall_time(...)` | mirror image with falling crossings of `v_high − frac·Δ` | as above | s | as above |
| `overshoot_ratio(v_initial, v_final)` | `(max_{t≥t_first} x − v_final)/(v_final − v_initial)` for a rising step (`v_final > v_initial`), mirrored (`(v_final − min)/(v_initial − v_final)`) for falling; clipped at 0 from below (`max(0, …)` is the *definition*: no overshoot = 0, a true zero). `v_initial` default `x(a)`, `v_final` default `x(b)` (recorded) | `|v_final − v_initial| > 0` | dimensionless (ratio; percent = ×100, label only) | zero swing → `UNDEFINED` |
| `settling_time(v_final, band)` | `band = tol·|v_final − v_initial|` (`tol` required, relative) or `abs_band` (absolute, exactly one of the two). `t_s` = the *earliest* time such that `|x(t) − v_final| ≤ band` for **all** `t ∈ [t_s, b]`; computed exactly on the PL signal: let `t_x` be the last time with `|x − v_final| = band` on a segment leaving the band (linear interpolation); `t_s = t_x`; if the signal is in band on all of `W`, `t_s = a`. Result `t_s − a` | `b > a` | s | out of band at `b` → `UNDEFINED("not settled inside window")` |
| `ac_gain` | `|H|`, `H = V_out/V_in` phasor ratio (F8-D5 semantics: zero input ⇒ undefined) | AC | dimensionless | `H` undefined → `UNDEFINED` |
| `ac_gain_db` | `20·log10|H|` via `ac.bode.magnitude_db` (exact-zero magnitude ⇒ the certified `NEGATIVE_INFINITY_DB` category, not a stored ∞) | AC | dB (label; dimension tuple = dimensionless) | — |
| `ac_phase` | `arg(H)` in rad, `(−π, π]` via `ac.phasors.phase`; `_deg` = `rad·180/π` (`decimal_pi`); sweeps use the certified `unwrap_phases` | AC | rad / deg (labels) | `H = 0` → `UNDEFINED` |
| `ac_amplitude(basis)` | peak (`|X|`, the engine convention) or `rms = peak/√2` via `rms_from_peak`; `basis` is **required** | AC phasor | probe unit | — |
| `bandwidth(db_threshold)` | interval from `analyze_bode` (`half_power_threshold_db` default −3.0103… relative to the reference level, returned **as the certified interval**; never a single interpolated number) | AC sweep with two established boundaries | Hz | not established → `UNDEFINED` (reason from F8-D6) |
| `dc_value` | probe value at `OP`/sweep point | — | probe unit | — |

Not defined (hence not offered): power, energy, FFT, THD, duty measured on arbitrary waves,
group delay. Adding any of them requires a new definition + validation entry.

**Units.** Every `Scalar` carries `(value: Decimal, dimension: tuple, unit_label: str)`. `dB`, `rad`,
`deg`, `%` are **labels** on a dimensionless dimension tuple (the existing registry has no such
units and F8-N must not extend it). Amplitude/RMS/peak-to-peak are separate measurement keys, never
implicit. Time is `TIME`, frequency `FREQUENCY`, `V/A/Ω/F/H` per registry.

## Data Model

All values are `Decimal` (never `float`); complex = certified `DecimalComplex`.

| Type | Value | Unit | Domain | Axis | Metadata |
|:---|:---|:---|:---|:---|:---|
| `Scalar` | `Decimal` | dimension tuple + label | any | — | `source` (probe/measurement key) |
| `ComplexScalar` | `DecimalComplex` (peak, `e^{+jωt}`) | dimension + label | frequency | — | frequency (Hz) |
| `Waveform` | `tuple[Decimal]` | dimension | time | `times: tuple[Decimal]` (strictly increasing, s) | source ref, analysis, `interpolation="piecewise-linear"` |
| `ComplexResponse` | `tuple[DecimalComplex\|None]` | dimension | frequency | `frequencies` (Hz, as requested) | per-point status/diagnostic (failed = `None`, never 0) |
| `SweepTrace` | `tuple[Decimal\|None]` | dimension | parameter | `axis` values + address key | per-point status |
| `MeasurementTable` | rows `(key, Scalar\|None, status, reason)` sorted by key | per row | — | — | `run_id`, `experiment_digest` |

No implicit conversion to `float`; the only allowed conversion boundary is the future presentation
layer (out of scope), which must live outside `domain/`.

## Serialization

* **Schema** `f8n-lab/1`. Canonical JSON: UTF-8, `sort_keys=True`, separators `(",", ":")`,
  `ensure_ascii=True`, no NaN/Infinity (`allow_nan=False`), arrays keep semantic order (documented
  where order is significant: waveform samples, measurements sorted by key, experiments in insertion
  order).
* **Numbers**: every `Decimal` is the string `str(d.normalize())` (exact, round-trippable through
  `Decimal(str)`); `Quantity` = `{"v": base-unit decimal string, "d": [7 ints]}` (units are stored in
  base units; display units are not preserved — documented); `DecimalComplex` = `{"re": s, "im": s}`;
  missing = JSON `null` with an explicit `status` next to it.
* **Circuit**: components sorted by ref; each `{ref, type, value, pins(sorted), parameters}`; parameters
  follow a **closed per-type schema** (numeric → `Quantity` form; `polarity/kind/control_ref/cp/cn/
  phase_unit` → strings; `wave` → typed dict). Unknown keys → `INVALID_SERIALIZATION`.
* **Digest**: `sha256(domain_tag ‖ 0x00 ‖ canonical_json_bytes)` with tags `f8n/experiment/1`,
  `f8n/run/1`, `f8n/circuit/1`.
* **Never**: `pickle`, `eval`, `marshal`, `yaml` object tags, class-name-based reconstruction. Loading
  builds objects only through the allowlisted typed constructors (enum-validated `kind` fields).
* **Compatibility**: `schema` must equal `f8n-lab/1` exactly; a different string ⇒ `SCHEMA_MISMATCH`.
  No forward/backward promise (see Replay).
* **CSV export** (`waveform_csv`, `table_csv`, `sweep_csv`): UTF-8, LF, header row with
  `name[unit_label]`, RFC-4180 quoting, values as canonical decimal strings, `None` as empty field
  plus a `status` column. Deterministic; produced as `str`, file I/O belongs to the caller.

What is serialised: `ExperimentDefinition`, `Session`, `Run` (status, provenance, results,
measurements, readings), `MeasurementResult`, provenance. Annotations are serialised but flagged
non-digested.

## Replay

`save experiment → load experiment → execute → compare result`:

1. `to_document(session)` → dict; the caller persists it (JSON text via `dumps_canonical`).
2. `from_document(doc) -> LoadResult(status, session)`; status ∈ `OK`, `INVALID_SERIALIZATION`,
   `SCHEMA_MISMATCH`, `SERIALIZATION_TOO_LARGE`. Load recomputes `experiment_id`/digests and rejects a
   document whose stored digests disagree (tamper/corruption ⇒ `INVALID_SERIALIZATION`).
3. `replay_run(session, run_id, *, allow_version_mismatch=False) -> ReplayResult`.

**Contract (explicit): same-version deterministic replay.** Every document stores
`engine_versions = {f8h-nonlinear, f8l-transient, f8m-analysis, f8j-small-signal-ac, f8d-ac-mna,
lab}` (the `ENGINE_VERSION` strings) and `schema`. Replay requires all to equal the running
software; otherwise `VERSION_MISMATCH` (no execution) unless `allow_version_mismatch=True`, in which
case the result is executed but the report is marked `comparable=False`. Cross-version equivalence
is **not** claimed.

"Exactly" means: same canonical circuit, same overrides/stimuli, same analysis config, same Q1 /
`TransientConfig` tolerances, same seed, same schema+engine versions ⇒ **bit-identical**
`result_digest` (the certified engines are deterministic: F8-M "same input+config+seed ⇒ same
digest"; F8-L history is Decimal-deterministic). `ReplayStatus`: `EQUIVALENT` (digests equal),
`RESULT_DIFFERS` (executed, digests differ; carries the first differing JSON path), `VERSION_MISMATCH`,
`SCHEMA_MISMATCH`, `INVALID_SERIALIZATION`. Notes/annotations never affect replay.

## Provenance

`Run.provenance` (all deterministic, sorted, no timestamps/ids/addresses):

`schema`, `lab_version`, `engine_versions`, `experiment_digest`, `circuit_digest` (F8-M helper),
`analysis` (`kind`, config canonical form, config digest), `parameters` (`overrides` sorted),
`stimuli`, `probes`, `instruments`, `measurement_specs`, `seed`, `tolerances` (Q1 constants and the
`TransientConfig` reltol/abstol/h-limits as *recorded values*), `engine_result_digests`
(`solver_digest`/`topology_digest`/F8-M `digest`/F8-D5 sweep `digest`), `engine_status`,
`init/warm-start counts` (F8-M `provenance`), `dc_mapping` note, `result_digest`.

**In the digest**: schema, tags, engine versions, canonical circuit, overrides, stimuli, analysis
config, seed, measurement/probe/instrument *specs*, status, numerical results, measurement values.
**Not in the digest**: `session_id`, `run_id`, `label`, metadata, annotations, notes, reference
values, `readings` (derived), any timestamp/uuid/object id/dict-iteration order (all maps are
key-sorted).

## Determinism

| Part | Deterministic? | Mechanism |
|:---|:---:|:---|
| Experiment definition & id | ✓ | canonical form, content-addressed |
| Simulation | ✓ | inherited (Q1, F8-L, F8-M seeded) |
| Measurements | ✓ | Decimal, fixed formulas, no float |
| Instrument readings | ✓ | pure functions of results |
| Serialization & digests | ✓ | canonical JSON, sorted keys |
| Replay | ✓ (same version) | see Replay |
| `session_id` uniqueness | caller's responsibility | the lab never generates ids; ids are *identity*, outside all digests |

Single-threaded, synchronous, no shared mutable state, no environment/locale/clock access; nothing
non-deterministic exists by design, so no "allowed non-determinism" list is needed.

## Error Model

Reuse of existing taxonomies; the lab adds only what the layer itself can fail at.

`RunStatus`: `COMPLETED`, `COMPLETED_WITH_FAILURES` (partial: F8-M `completed_with_point_failures` /
`completed_with_failures`, F8-D5 point failures), `INVALID_CONFIGURATION` (lab-level static
validation), `INVALID_CIRCUIT` (engine `INVALID`), `UNSUPPORTED` (engine `UNSUPPORTED` or lab
capability gap), `SOLVER_FAILURE` (any engine failure status).
`engine_status` always preserves the certified verdict verbatim (`diverged`, `max_iterations`,
`singular_jacobian`, `max_steps`, `timestep_too_small`, `singular`, …), so `DIVERGED`/`SINGULAR` are
not redundantly re-invented as lab states.

Mapping:

| Engine verdict | `RunStatus` |
|:---|:---|
| CONVERGED / COMPLETED / SOLVED / `completed` | `COMPLETED` |
| `completed_with_*failures` | `COMPLETED_WITH_FAILURES` |
| `invalid` | `INVALID_CIRCUIT` (config was already lab-validated) |
| `unsupported` | `UNSUPPORTED` |
| `diverged`, `max_iterations`, `singular_jacobian`, `max_steps`, `timestep_too_small`, AC `singular/inconsistent/numerically_uncertain` | `SOLVER_FAILURE` |

`MeasurementStatus`: `OK`, `UNDEFINED` (mathematically undefined for this signal: reason text),
`INVALID_MEASUREMENT` (spec violates the definition), `NO_DATA` (the run has no usable payload).
`InstrumentStatus`: `OK`, `UNSUPPORTED`, `NO_TRIGGER`, `OUT_OF_RANGE`, `NO_DATA`.
`ReplayStatus` / `LoadStatus` as above. `LabConfigError(ValueError)` carries a code
(`INVALID_PROBE`, `INVALID_MEASUREMENT_SPEC`, `INVALID_STIMULUS`, `INVALID_CIRCUIT`, `INVALID_SEED`,
`BUDGET_EXCEEDED`, `SESSION_CLOSED`, `DUPLICATE`, …) raised **only** by constructors/`create_session`
(typed-schema violations), while `add_experiment` reports the same problems in a `ValidationReport`
so a bad definition never corrupts a session.

**Partial results.** A DC sweep point failure, a partial transient, an invalid AC point, an
uncomputable measurement or failed MC samples are always carried explicitly: engine per-point
statuses are preserved, failed points are `None` with a status (never 0), the run status is
`COMPLETED_WITH_FAILURES`, and any measurement that depends on a failed/absent signal is
`NO_DATA`/`UNDEFINED`. A transient that did not reach `COMPLETED` carries **no** waveform (F8-L
commits history only on completion) ⇒ `SOLVER_FAILURE`, measurements `NO_DATA`.

**Cancellation.** Not supported (finding 6): execution is synchronous and single-threaded, so there
is no interleaving in which a cancel request can be observed; a run either completes and is
appended, or fails and is appended as a failed run. Consequently no state can be left partially
mutated (sessions are immutable values; the run copy of the circuit is discarded). `CANCELLED` is
deliberately **not** a status (it would be unreachable dead taxonomy). Future home: process-isolating
runner. **Transactional execution:** `clone → apply overrides/stimuli → execute → append run`; the
definition and session circuit are never modified, a failed run cannot corrupt them.

## Security

* No `eval`, `exec`, `compile`, dynamic import, `__import__`, `getattr`-by-user-string, subprocess,
  `os`/`sys` process access, sockets, network, pickle/marshal, YAML object tags.
* Every user-controlled selector is a **typed enum or allowlist**: `AnalysisKind`, `StimulusKind`,
  `MeasurementKind`, `InstrumentKind`, `Coupling`, `Slope`; parameter addresses only through the F8-M
  closed registry; probes only by validated net/component ref; wave specs only through the typed
  `StimulusSpec` schema.
* No user text is ever interpreted as an expression; labels/notes are inert strings (length-bounded).
* Deserialization: schema-validated, allowlisted constructors, size-bounded before parsing
  (`MAX_SERIALIZED_BYTES`), digests recomputed and compared.
* AST scan (test N-091..N-094) over `lab/*.py` mirrors the F8-K/L/M scans and additionally forbids
  `getattr/setattr/open/vars/globals/locals`.

## Resource Budgets

Only bounds that follow from a documented reason; existing ones are **inherited, not redefined**.

| Budget | Value | Reason | Failure behaviour |
|:---|:---|:---|:---|
| Transient samples | `MAX_TRANSIENT_STEPS + 1` (inherited, 100001) | F8-L bound | F8-L status → `SOLVER_FAILURE` |
| Sweep / MC / corners | `MAX_SWEEP_POINTS`, `MAX_MC_ITERATIONS`, `MAX_WORST_PARAMS` (inherited) | F8-M bounds | F8-M `INVALID` → `INVALID_CONFIGURATION`, nothing executed |
| `MAX_DISPLAY_SAMPLES` | 10 000 | scope payload is a presentation artefact; the bound exceeds any realistic display width while staying far below the solver history bound | `LabConfigError(BUDGET_EXCEEDED)` / validation report |
| `MAX_SCOPE_CHANNELS` | 4 | conventional instrument size; keeps readings bounded | validation report |
| `MAX_EXPERIMENTS_PER_SESSION` | 256 | each definition is small; bound keeps `to_document` size predictable | `BUDGET_EXCEEDED`, session unchanged |
| `MAX_RUNS_PER_SESSION` | 1024 | runs retain full results in memory (a transient run can hold 10^5 samples × nodes) | `BUDGET_EXCEEDED`, session unchanged |
| `MAX_MEASUREMENTS_PER_EXPERIMENT` / probes | 64 / 64 | linear cost, bounded table size | validation report |
| `MAX_SERIALIZED_BYTES` | 64 MiB | load parses the whole document in memory; guards against decompression-bomb-style inputs | `SERIALIZATION_TOO_LARGE` at save and at load, before parsing |

Values are engineering bounds (defaults, fixed constants, not tunables) documented in the gate, like
the F8-M `MAX_*`; no throughput/time limit exists anywhere.

## Validation

End-to-end scenarios (expected values analytic; tolerances stated; comparison recorded as
`expected / actual / abs error / rel error / tolerance`):

* **VLAB-001** — `V1 = 10 V → R1 = 1 kΩ → R2 = 2 kΩ → gnd`, voltmeter `V(out,gnd)`: expected
  `20/3 V`; `|Δ| ≤ 1E-40` relative (HP path); ammeter on `R1`: `10/3000 A`.
* **VLAB-002** — RC transient (`R = 1 kΩ, C = 1 µF`, step `0 → 1 V` at `t0 = 0`, `TR`, tight
  reltol): expected `V(t) = V∞ + (V0 − V∞)e^{−t/RC}` with `V0 = 0, V∞ = 1`; check (i) waveform at
  committed samples within the F8-L certified error bound (`≤ 5·reltol`-scaled, exact bound fixed
  in the F8-L gate benchmark), (ii) measurements: `rise_time_10_90 = RC·ln 9`, `settling_time`
  (tol 2 %) `= RC·ln 50`, `mean`/`rms` over `[0, 5RC]` from the closed-form integrals; tolerance =
  PL-model error (`≤ 1E-4` relative for `reltol = 1E-8`), scope reading equals interpolation of the
  same samples.
* **VLAB-003** — AC divider (`R–C`, `1 kHz`): `|H| = 1/√(1+(ωRC)²)`, `phase = −atan(ωRC)`,
  `dB = 20 log10|H|`; tolerance `1E-40` relative (HP, no PL error).
* **VLAB-004** — DC sweep: lab run's wrapped result `to_dict()` **equals** a direct
  `solve_dc_sweep` call with the same config (bit-for-bit); `SweepReading` rows equal points.
* **VLAB-005** — Monte Carlo: same experiment (seed 42) run 3×: identical `plan_digest`, samples,
  statistics and `result_digest`; different seed ⇒ different `plan_digest`.
* **VLAB-006** — Replay: `to_document → dumps → loads → from_document → replay_run` gives
  `EQUIVALENT`; tampered document ⇒ `INVALID_SERIALIZATION`; altered `engine_versions` ⇒
  `VERSION_MISMATCH`.

### Measurement validation (references)

| Measurement | Mathematical reference signal | Expected | Tolerance |
|:---|:---|:---|:---|
| `mean` | sampled linear ramp `x=t` on `[0,1]` | `1/2` exactly | `0` (exact PL) |
| `rms` | ramp `x=t` on `[0,1]` | `1/√3` | `1E-45` relative |
| `rms` (sine, 1000 samples/period, PL) | `A sin ωt` over 1 period | `A/√2` | PL error bound derived from the sample spacing `h` (order `(ωh)²`) and fixed numerically in the test |
| `pp`, `max`, `min` | trapezoid wave | known levels | exact |
| `period`, `frequency` | PL triangle with period `T` | `T`, `1/T` | exact (crossings of PL are exact) |
| `rise_time` 10–90 | PL ramp from `0` to `1` in `T_r` | `0.8·T_r` | exact |
| `settling_time` | PL decaying staircase with known band exit | known `t_s` | exact |
| `overshoot_ratio` | PL step with peak `1.2`, final `1` | `0.2` | exact |
| `ac_gain/phase` | phasor `H = 1/(1+jx)` | closed form | `1E-40` |

### Error validation
Invalid circuit, invalid probe, invalid node, invalid branch, invalid measurement, unsupported
analysis, solver divergence, singular system, empty session, invalid serialization, schema mismatch,
invalid seed, budget overflow: each yields the honest status listed in the Error Model (tests
N-095…N-107). Security and determinism validations are tests N-091…N-094 and N-088…N-090.

## Test Matrix

(Specified only; none implemented in this phase.) Ids are contiguous; each has a technical reason.

| ID | Group | Test | Expected |
|:---|:---|:---|:---|
| N-001 | session | create with valid id/circuit | OPEN session, circuit deep-copied (mutating caller's circuit later does not change session) |
| N-002 | session | invalid ids (`""`, spaces, >64, non-str) | `LabConfigError` |
| N-003 | session | operations return new values; original unchanged | `is not`, equal digests before |
| N-004 | session | reset keeps circuit+definitions, drops runs/annotations | as stated |
| N-005 | session | clone new id, same content, `cloned_from` recorded, not digested | digests equal |
| N-006 | session | branch: new definition with explicit edits, original intact, `derived_from` recorded | as stated |
| N-007 | session | close then operate | `SESSION_CLOSED`; `to_document` still works |
| N-008 | session | two sessions from the same circuit are independent | run in A leaves B untouched |
| N-009 | experiment | content addressing: same definition ⇒ same id; label/notes changes ⇒ same id | equal |
| N-010 | experiment | any semantic change (override, stimulus, config, seed) ⇒ different id | different |
| N-011 | experiment | `add_experiment` idempotent for equal definition | one entry |
| N-012 | experiment | invalid override address / domain violation | report `INVALID`, session unchanged |
| N-013 | experiment | seed rules (required for MC, forbidden otherwise, bool/negative/float) | errors |
| N-014 | experiment | duplicate probe/measurement keys, unknown probe reference | errors |
| N-015 | experiment | stimulus on non-V/I / two stimuli on one source | errors |
| N-016 | experiment | definition never mutated by runs (deep equality before/after) | equal |
| N-017 | run | run ids `exp#1`, `exp#2` deterministic per session | as stated |
| N-018 | run | execution snapshot: session circuit and caller circuit unchanged after run (digest) | equal |
| N-019 | run | failed run appended with status, definition intact | as stated |
| N-020 | run | repeated runs equal `result_digest` | equal |
| N-021 | run | status mapping table (each engine verdict → `RunStatus`, `engine_status` verbatim) | table |
| N-022 | run | `MAX_RUNS_PER_SESSION` reached | `BUDGET_EXCEEDED`, session unchanged |
| N-023 | instrument | voltmeter on OP equals `V_p − V_n` from the result | exact |
| N-024 | instrument | ammeter on R/V/I/L/D/Q/M/J/T per availability table | values or `UNSUPPORTED`, never 0 |
| N-025 | instrument | instruments never alter circuit/result (digest) | equal |
| N-026 | instrument | oscilloscope reading = PL interpolation of committed samples | exact hits + interpolated |
| N-027 | instrument | scope `sample_count` sweep (2, 10, 1000) — measurements identical | equal |
| N-028 | instrument | vertical scale/offset/coupling only alter presentation fields | raw values equal |
| N-029 | instrument | AC coupling removes window mean (mean of coupled = 0) | `|mean| ≤ 1E-40` |
| N-030 | instrument | scope config changes leave `result_digest` unchanged | equal |
| N-031 | probe | `VoltageProbe` with ground/no ground, `p==n` invalid | as stated |
| N-032 | probe | `CurrentProbe` invalid branch / branch unavailable in transient | `INVALID_PROBE` / `UNSUPPORTED` |
| N-033 | probe | derived R current in transient `(V1−V2)/R` equals direct recomputation | exact |
| N-034 | probe | L current from `inductor_currents` | equal |
| N-035 | probe | `ParameterProbe` resolves nominal + dimension; invalid address | as stated |
| N-036 | probe | no `WaveformProbe`/`FrequencyProbe` types exist (API surface test) | absent |
| N-037 | measurement | `max/min/pp` on trapezoid, window ends inside segments | exact |
| N-038 | measurement | `mean` ramp | 1/2 exact |
| N-039 | measurement | `rms` ramp, and constant | `1/√3`, constant |
| N-040 | measurement | `rms` vs discrete-sample formula difference documented (PL exactness test) | PL formula exact |
| N-041 | measurement | `crossings` rising/falling/either; sample exactly on level attribution | as defined |
| N-042 | measurement | `period/frequency` triangle; <2 crossings | value / `UNDEFINED` |
| N-043 | measurement | hysteresis rejects noise chatter | count matches |
| N-044 | measurement | `rise_time` 10–90, custom fractions, AUTO levels, edge missing | exact / `UNDEFINED` |
| N-045 | measurement | `fall_time` mirror | exact |
| N-046 | measurement | `overshoot_ratio` rising/falling/none/zero swing | 0.2 / 0 / `UNDEFINED` |
| N-047 | measurement | `settling_time` band exit, always-in-band, never-settled | `t_s−a` / 0 / `UNDEFINED` |
| N-048 | measurement | invalid specs (window a≥b, fractions ∉ (0,1), both/neither band, missing basis) | `INVALID_MEASUREMENT` |
| N-049 | measurement | failure never becomes 0 (all UNDEFINED cases have `value None`) | `None` |
| N-050 | measurement | `ac_gain`, dB (incl. −∞ category), phase rad/deg, `H=0` | closed form / `UNDEFINED` |
| N-051 | measurement | `ac_amplitude` basis peak vs rms (required) | ratio `√2` |
| N-052 | measurement | `bandwidth` interval from `analyze_bode`; unestablished ⇒ `UNDEFINED` | as F8-D6 |
| N-053 | transient | RC step (VLAB-002): waveform vs analytic within bound | pass |
| N-054 | transient | waveform is an exact copy of `TransientResult` (no resampling) | equal |
| N-055 | transient | function-generator sine vs `_wave_value`-based analytic | equal |
| N-056 | transient | pulse duty definition at 50 % crossings | measured duty = requested |
| N-057 | transient | failed transient ⇒ no waveform, measurements `NO_DATA` | as stated |
| N-058 | transient | trigger: rising/falling/either, pre/post window, `NO_TRIGGER`, `OUT_OF_RANGE` | as defined |
| N-059 | AC | AC point divider (VLAB-003) | closed form |
| N-060 | AC | AC point with nonlinear circuit delegates to F8-J (values equal direct call) | equal |
| N-061 | AC | AC sweep RC low-pass equals direct `frequency_response`+`analyze_bode` | equal |
| N-062 | AC | AC sweep on a nonlinear circuit | `UNSUPPORTED` |
| N-063 | AC | failed frequency point kept as `None` + status; run `COMPLETED_WITH_FAILURES` | as stated |
| N-064 | DC | OP equals direct `solve_nonlinear_dc` | equal |
| N-065 | DC | VLAB-001 | closed form |
| N-066 | DC | dynamic elements map to DC equivalent (C open, L short) | equal to F8-M point |
| N-067 | DC | diode/BJT/MOS/JFET OP through lab equals direct engines | equal |
| N-068 | F8-M | DC sweep (VLAB-004) wrapped result equals direct | equal |
| N-069 | F8-M | parameter sweep equals direct | equal |
| N-070 | F8-M | corners: honesty text preserved verbatim | present |
| N-071 | F8-M | sensitivity equals direct | equal |
| N-072 | F8-M | AC sensitivity equals direct | equal |
| N-073 | F8-M | Monte Carlo (VLAB-005) equals direct; seed injected | equal |
| N-074 | F8-M | probe → observable derivation; unobservable probe rejected | as stated |
| N-075 | serialization | canonical JSON stable across dict/insertion orders | identical bytes |
| N-076 | serialization | Decimal/Quantity/DecimalComplex round trip exact | equal |
| N-077 | serialization | closed circuit schema: unknown key/type rejected | `INVALID_SERIALIZATION` |
| N-078 | serialization | CSV schema (header, quoting, `None`) | golden text |
| N-079 | serialization | size guard at save and load | `SERIALIZATION_TOO_LARGE` |
| N-080 | serialization | no pickle/eval path (structural test) | absent |
| N-081 | replay | VLAB-006 round trip | `EQUIVALENT` |
| N-082 | replay | tampered digest / edited value | `INVALID_SERIALIZATION` |
| N-083 | replay | schema mismatch / engine version mismatch (+ `allow_version_mismatch`) | statuses |
| N-084 | replay | differing result reports first differing path | path text |
| N-085 | provenance | required keys present; digests link to engine result digests | present |
| N-086 | provenance | no timestamp/uuid/address/wall-clock | absent |
| N-087 | provenance | notes/labels/session_id excluded from digests | equal |
| N-088 | determinism | same experiment ×3 (all analyses): result, measurements, serialization, digest | identical |
| N-089 | determinism | definition insertion-order invariance (probes/overrides/stimuli permutations) | same id/digest |
| N-090 | determinism | ambient `decimal` context change / locale change has no effect | identical |
| N-091 | security | AST: no eval/exec/compile/`__import__`/getattr/setattr/open/vars/globals/locals | 0 hits |
| N-092 | security | AST: no subprocess/os/sys/socket/importlib/pickle/marshal/urllib | 0 hits |
| N-093 | security | hostile strings in labels/refs/notes/addresses (`__import__('os')`, `1+1`) are inert data or rejected | no execution |
| N-094 | security | malicious document (class-name tags, extra keys, oversized) | `INVALID_SERIALIZATION` |
| N-095 | errors | invalid circuit (floating, no reference) | `INVALID_CIRCUIT` |
| N-096 | errors | invalid probe / node / branch | `INVALID_PROBE` |
| N-097 | errors | invalid measurement spec | `INVALID_MEASUREMENT` |
| N-098 | errors | unsupported analysis combination | `UNSUPPORTED` |
| N-099 | errors | solver divergence (exp overflow) | `SOLVER_FAILURE`, `engine_status=diverged` |
| N-100 | errors | singular system | `SOLVER_FAILURE`, `engine_status=singular_jacobian` |
| N-101 | errors | empty session run / unknown experiment id | `LabConfigError` |
| N-102 | errors | invalid serialization (not JSON, wrong types) | `INVALID_SERIALIZATION` |
| N-103 | errors | schema mismatch | `SCHEMA_MISMATCH` |
| N-104 | errors | invalid seed | `INVALID_SEED` |
| N-105 | errors | budget overflow (experiments, runs, display samples, channels) | `BUDGET_EXCEEDED` |
| N-106 | errors | partial results: MC with failed samples, sweep with failed point | `COMPLETED_WITH_FAILURES`, failures listed |
| N-107 | errors | measurement depending on failed data | `NO_DATA`, never 0 |
| N-108 | regression | F8-H/I/J/K/L/M suites unchanged and green | 100 % |
| N-109 | regression | global suite: no unexpected failures; `float(` = 0 in `lab/` | pass |
| N-110 | regression | certified modules byte-unchanged (`git diff` on `mna/*`, `ac/*` empty) | empty |

Diagnostic benchmarks (no timing assertion): session creation, experiment setup, run, measurement,
serialization, replay — counts (samples, solves, bytes) and wall time printed only.

## Regression Contract

F8-N must keep green: `test_f8h_nonlinear_dc.py`, `test_f8i_*`, `test_f8j_small_signal_ac.py`,
`test_f8k_*`, `test_f8l_transient.py`, `test_f8m_analysis.py` (87), architecture tests and the
global suite (2120 tests at the F8-M baseline, 2 pre-existing skips). F8-N adds **no changes** to
`mna/`, `ac/`, `circuit.py`, `units.py`; any need to change them ⇒ STOP and report
`F8-N IMPLEMENTATION BLOCKED` (Prompt 2 rule). Public F8-M/F8-L/F8-J signatures are consumed as
they are (audited above).

## Adversarial Review

| Attack | Finding | Verdict |
|:---|:---|:---|
| Double source of truth | one circuit per session; edits only via digested overrides/stimuli; no netlist import | closed |
| Duplicate solver | lab calls certified entry points only; instruments are pure views | closed |
| Shared mutable state | immutable session values, deep-copied circuits (frozen `Component` is shallow → copied) | closed |
| Non-deterministic replay | no clock/uuid/random/env; digests exclude identity fields; same-version contract stated | closed |
| Instrument altering circuit | ideal probes are read-only; no insertion of shunts; loading models out of scope | closed |
| Measurement without definition | every key defined above; anything else absent | closed |
| Unit loss | `Scalar` carries dimension + label; dB/rad/deg/% declared as labels | closed |
| Float leakage | Decimal only in `lab/`; presentation boundary out of scope | closed |
| Insecure serialization | canonical JSON, closed schemas, no class-name reconstruction | closed |
| Lost seed | seed part of the definition and digest; forbidden on deterministic analyses | closed |
| Session contamination | no cross-session state | closed |
| Plotting coupled to solver | none; readings are view-models | closed |
| UI contaminating domain | UI out of scope; `test_architecture` enforced | closed |
| F8-M / transient duplicated | wrapped results, equality tests N-068..N-073, N-054 | closed |
| Arbitrary limits | inherited limits + justified constants; no time limits | closed |
| Errors turned into zero | `None` + status; tested N-049, N-107 | closed |
| Ambiguous partial results | per-point status preserved, run `COMPLETED_WITH_FAILURES` | closed |
| `value_at` nearest-sample trap (finding 3) | forbidden for lab use; PL interpolation is specified | closed |
| Transient current probes beyond stored data | restricted to R (derived) and L; others `UNSUPPORTED` | closed |
| Scope resolution changing solver steps | separate objects, N-027/N-030 | closed |

No unresolved item prevents a deterministic implementation.

## Risks

1. PL-signal measurement error on coarse adaptive steps can exceed a user's expectation → mitigated:
   error is a documented property of the run (LTE-controlled); validation bounds are derived, not
   guessed; measurements never claim continuous exactness.
2. `rise_time`/`settling_time` AUTO levels are only valid for one clean edge → mitigated: explicit
   levels preferred; AUTO recorded in the result and provenance.
3. Same-version-only replay may disappoint users needing archives → documented; digests + version
   stamp make mismatch detection explicit rather than silent.
4. Transient current probe restrictions (R, L only) → honest `UNSUPPORTED`; a later F8-L extension can widen it without changing F8-N semantics.
5. Session memory with many transient runs → `MAX_RUNS_PER_SESSION`, immutable values share structure.
6. `Component` is only shallow-frozen → all lab constructors deep-copy `pins/parameters/metadata`.
7. Canonical decimal strings can be long for extreme exponents → `MAX_SERIALIZED_BYTES` guard.
8. F8-D5 `frequency_response` signature/return shapes are consumed by adapter code → the adapter is covered by N-061 equality tests (the design fixes *what* is called, not internal details).

## Deviations

Deviations from the mandate's *candidate* lists (not from any certified guarantee — none is
contradicted):

- **D-01** No persistent `Laboratory` object: "laboratory" = the pure API surface (a stateful object
  would create hidden state).
- **D-02** No `WaveformProbe` and `FrequencyProbe` entities (domain/axis are properties of the
  analysis); `ParameterProbe` retained.
- **D-03** `CANCELLED` omitted (unreachable in a single-threaded synchronous design); `DIVERGED` and
  `SINGULAR` preserved as `engine_status` under the coarse `SOLVER_FAILURE` rather than duplicated as
  lab states.
- **D-04** Instruments are ideal only; no loading/bandwidth/error models (no certified basis).
- **D-05** `AC_SWEEP` limited to linear circuits; transient current probes limited to R and L
  (derived from audit findings 2 and 7).
- **D-06** Rise/settling/overshoot definitions require explicit parameters (no hidden 10–90 % default);
  a `rise_time_10_90` helper fixes those numbers openly.
- **D-07** Function generator supports phase *lag* only and delay as time shift, because the
  certified sine has `td ≥ 0` and no phase parameter (finding 5).
- **D-08** Plotting/UI/CLI/notebooks entirely out of scope; readings are view-models.

## Open Questions

None blocking. Items Prompt 2 resolves *without architectural decisions*: exact class/function
spellings inside the fixed module list, the precise `frequency_response` frequency-list adapter, and
the numeric error bounds used in VLAB-002 (taken from the F8-L gate benchmarks). Everything that
could change behaviour is fixed above.

## Certification Criteria

- [ ] design gate READY (this document)
- [ ] `lab/` implemented per Laboratory/Session/Experiment/Run/Instrument/Probe/Measurement/Stimulus models
- [ ] every measurement function matches its mathematical definition (N-037…N-052)
- [ ] VLAB-001…006 pass with stated tolerances
- [ ] F8-M results wrapped without duplication (N-068…N-073, equality with direct calls)
- [ ] transient → waveform → measurement → reading path exact (N-053…N-058), solver/display timesteps decoupled (N-027, N-030)
- [ ] serialization canonical, closed-schema, size-guarded; replay `EQUIVALENT` (same version), mismatches reported
- [ ] provenance complete and free of timestamps/ids; digests exclude identity/notes
- [ ] determinism ×3 across all analyses; insertion-order and ambient-context invariance
- [ ] security AST/hostile-input tests clean; no `float(` in `lab/`; forbidden-dependency scan clean
- [ ] error/partial-result tests (N-095…N-107) honest; failure never becomes zero
- [ ] budgets enforced with stated failure behaviour
- [ ] F8-H/I/J/K/L/M and global regression green; certified modules byte-unchanged
- [ ] no undocumented deviations, no scope creep (no UI/plotting/new solver/F8-O)
- [ ] no normative wall-clock benchmarks
- [ ] documentation complete (`GATE-F8N.md`), roadmap updated only after certification
- [ ] git audit clean (no secrets, no F8-O content, no force)

## Final Verdict

`F8-N DESIGN READY`
