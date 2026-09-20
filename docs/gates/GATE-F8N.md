# GATE-F8N

Certification gate for **F8-N — Virtual Laboratory** (implementation,
validation, certification). Implements `docs/gates/GATE-F8N-DESIGN.md`
(`F8-N DESIGN READY`) exactly, except the documented deviations below
(none contradicts a certified guarantee).

## Baseline

- Repository `Damaga2005/AcademicCore`, branch `main`.
- Certified baseline: `F8-M = c43483b` (`docs: certify F8-M`).
- Design gate (local): `14b6c2f` (`docs: add F8-N virtual laboratory
  design gate`), verdict `F8-N DESIGN READY`.
- Preconditions verified before any code: branch `main`, clean tree,
  `HEAD = 14b6c2f`, `origin/main = c43483b`. No reset / rebase / force.

## Design Gate

`docs/gates/GATE-F8N-DESIGN.md` read in full (890 lines). Verdict:
`F8-N DESIGN READY`. Implemented module-by-module per its Laboratory /
Session / Experiment / Run / Instrument / Probe / Measurement /
Stimulus / Serialization / Replay / Provenance / Determinism / Error /
Security / Budgets models. Deviations from the gate are listed under
Deviations (all are interpretations or forced findings, none changes a
certified engine).

## Implementation

New package `src/academic_core/domain/engineering/lab/` (stdlib +
certified-engine imports only; Decimal only; no I/O; no global state):

| Module | Lines | Responsibility (per design gate) |
|:---|---:|:---|
| `model.py` | 1118 | entities, enums, budgets, errors, data types, specs |
| `stimulus.py` | 196 | `StimulusSpec`, `function_generator`, run-copy application |
| `run.py` | 690 | analysis dispatch (allowlist), readings, measurements, digest, provenance |
| `waveform.py` | 219 | `Waveform`, exact PL-signal math |
| `measure.py` | 320 | measurement functions (exact definitions) |
| `instruments.py` | 924 | probes + ideal instrument readings |
| `session.py` | 405 | session operations + static validation |
| `serialize.py` | 1306 | canonical JSON/CSV, digests, documents, loading |
| `replay.py` | 112 | load/replay/compare |
| `__init__.py` | 96 | public API surface |

Tests: `tests/f8n_lab_common.py` (builders) plus

| File | Tests | Coverage |
|:---|---:|:---|
| `tests/test_f8n_lab.py` | 40 | N-001..N-036 + aliasing attacks |
| `tests/test_f8n_lab_measure.py` | 22 | N-037..N-058 |
| `tests/test_f8n_lab_engines.py` | 16 | N-059..N-074 |
| `tests/test_f8n_lab_serde.py` | 30 | N-075..N-107 (N-110 has two tests) |
| `tests/test_f8n_lab_valid.py` | 17 | VLAB-001..006, references, N-088..N-090, N-108..N-110, benchmarks |

Total: **125 tests, 125 passed, 0 failed, 0 skipped.**

## Architecture

```text
Circuit -> (F8-M substitute / stimulus override: fresh copy) -> Problem
        -> Analysis (nonlinear | small_signal | response | transient | analysis)
        -> Solver (Newton / linsolve / implicit integration)
        -> Result (NonlinearResult | SmallSignalACResult | SweepResult |
                   TransientResult | F8-M results)
        -> Reporting / provenance (digests, to_dict)
                         ^
                         |  read-only (typed adapters, no re-solve)
        +----------------┴--------------------------------------------------+
        | NEW: domain/engineering/lab/                                       |
        |   model.py       entities, enums, budgets                          |
        |   stimulus.py    StimulusSpec, function_generator                  |
        |   run.py         analysis dispatch (allowlist)                     |
        |   waveform.py    Waveform, PL-signal math                          |
        |   measure.py     measurement functions                             |
        |   instruments.py probes + instrument readings                      |
        |   session.py     session operations                                |
        |   serialize.py   canonical JSON/CSV, digests                       |
        |   replay.py      load/replay/compare                               |
        +-------------------------------------------------------------------+
```

Rules enforced: (a) `lab/` imports engines; engines never import
`lab/` (N-110 AST scan over `domain/engineering`, 0 offenders);
(b) every run is exactly one certified call (or the documented
`frequency_response` + `analyze_bode` composition); (c) instruments and
measurements are pure functions of run results; (d) no global state, no
I/O (CSV/JSON produced as `str`, file I/O belongs to callers);
(e) stdlib + certified-engine imports only (N-091/N-092 AST scans).

Dependency-direction audit (N-110): static import scan of all of
`domain/engineering` outside `lab/` — no module imports `lab`.
`git status` on `mna/`, `ac/`, `circuit.py`, `units.py` is empty
(N-110): certified modules byte-unchanged.

## Session

`LaboratorySession` is an immutable value: `create_session`,
`add_experiment`, `run_experiment`, `annotate`, `reset`,
`clone_session`, `branch_experiment`, `close_session` all return new
sessions; failures return the unchanged session object (identity, N-003
aliasing test asserts `is`). `session_id` is caller-supplied
(`^[A-Za-z0-9_.-]{1,64}$`), never generated (no uuid/timestamp/random
anywhere in `lab/`). `reset` keeps circuit + definitions, drops
runs/annotations. `clone` records `cloned_from` in metadata (not
digested). `branch` applies an explicit edit set, records
`derived_from`, leaves the original definition untouched. `close`
blocks every later operation except `to_document` (`SESSION_CLOSED`).
Caller circuits are deep-copied at creation (N-001: later caller
mutation, including pins/parameters/metadata dicts, does not leak in).

## Experiment

Content-addressed `exp-<digest16>` over (analysis, circuit, overrides,
stimuli, probes, instruments, measurements, seed). Labels excluded
(N-009: label-only change keeps the id; N-010: any semantic change
moves it). `add_experiment` is idempotent (N-011) and runs full static
validation with no solve (N-012..N-015: bad registry address, domain
violation, seed rules — MC required, elsewhere forbidden — duplicate
keys, unknown probe refs, stimulus on non-V/I or twice on one source).
Insertion-order invariance (N-089): overrides sorted by key, stimuli by
source, probes/instruments/measurements by key — permutations give the
same id. Definitions survive runs byte-equal (N-016, deepcopy attack).

## Run

`run_id = exp#n` (1-based per experiment per session). `Run` carries
`RunStatus`, verbatim `engine_status`, wrapped result, measurements,
readings, diagnostics, provenance, `result_digest`. Status mapping
(N-021, unit-tested per verdict): converged/completed/solved ->
COMPLETED; completed_with_*failures -> COMPLETED_WITH_FAILURES;
invalid -> INVALID_CIRCUIT; unsupported -> UNSUPPORTED; everything else
(diverged, max_iterations, singular_jacobian, max_steps,
timestep_too_small, singular, inconsistent, numerically_uncertain) ->
SOLVER_FAILURE. Failed runs are appended as failed runs (N-019);
unknown engine exceptions propagate loudly (never masked).
Execution snapshot is transactional (clone -> normalize display units
-> substitute -> stimuli -> one engine call); session and caller
circuits are digest-identical after runs (N-018). Repeated runs are
bit-identical (N-020).

Display-unit normalization (audited behaviour): engine digests are
display-unit sensitive while lab documents keep base units only, so the
execution snapshot is normalized to base display units (numbers
untouched). Save/load round trips therefore stay bit-identical
(replay `EQUIVALENT`).

## Instruments

All ideal, pure views (infinite bandwidth, no loading, no noise, no
gain/offset error, exact Decimal readout). Voltmeter `V(p,n) = Vp - Vn`
(N-023 exact vs direct solve). Ammeter per the availability table with
project sign conventions verbatim (N-024; resistor/L/C aux/devices; I
sources report `-Is`; C open reports exactly 0 A in DC; L via the
documented DC-short mapping; transient R derived `(V1-V2)/R`, L direct,
others `UNSUPPORTED` — N-032/N-033/N-034). Instruments never alter
circuit/result (N-025: digests before/after equal). Oscilloscope:
display grid over committed samples with PL interpolation (N-026 exact
hits + interpolated values); solver/display timesteps decoupled
(N-027: sample counts 2/10/1000 give identical measurements; N-030:
scope config changes leave `result_digest` unchanged); scale/offset/
coupling are presentation-only (N-028); AC coupling removes the window
mean (N-029). Trigger: rising/falling/either with pre/post,
hysteresis, `NO_TRIGGER` (no free-run fallback) and `OUT_OF_RANGE`
(N-058). `MAX_DISPLAY_SAMPLES = 10000` and `MAX_SCOPE_CHANNELS = 4`
are honest failures, never silent truncation (N-105).
Frequency-response viewer is a direct view over certified
`analyze_bode` (N-061 equality with direct calls). Sweep viewer wraps
M1/M2/M3/M4/M4-AC/M5 with per-point statuses, corner-extremum honesty
text verbatim, MC plan/failures/statistics (N-068..N-073).

## Probes

`VoltageProbe` (distinct nets, ground `0`/`GND` = 0), `CurrentProbe`
(closed branch grammar `R1`/`V1`/`D1`/`Q1:C`/`M1:D`/`J1:S`/`T1:1`/`L1`;
legs checked against the circuit), `ParameterProbe` (closed F8-M
registry via certified `resolve_param`). No `WaveformProbe` /
`FrequencyProbe` types exist (N-036). Existence validated at add time
(`INVALID_PROBE`, N-031/N-032/N-096); availability at run time
(`UNSUPPORTED`, never 0, N-024/N-032). Sweep configs must provide the
probe-derived observables (`node_voltage`, `aux_current`,
`resistor_current`, `device_current`); I/C/L use exact derivations
(`-Is`, 0, DC-short aux); missing coverage is an `INVALID` report
(N-074).

## Measurements

Exact per the design-gate mathematics, all Decimal under an explicit
lab context, undefined = `None` + reason (never 0, N-049/N-107):
max/min/pp (window ends interpolated, N-037), mean (exact PL integral,
ramp = 1/2, N-038), rms (exact `sqrt((1/(b-a)) integral x^2 dt)`,
ramp = `1/sqrt(3)`, constant, N-039; PL-vs-discrete documented,
N-040), crossings with trigger attribution + hysteresis (N-041/N-043),
period/frequency (`K<2` -> `UNDEFINED`, never 0 Hz, N-042), rise/fall
with required fractions and explicit-or-AUTO levels (N-044/N-045),
overshoot clipped at 0, mirrored falling, zero swing `UNDEFINED`
(N-046), settling as last band-boundary touch with endpoint policy
(never-settled `UNDEFINED`, always-inside 0, N-047), invalid specs
`INVALID_MEASUREMENT` (N-048), AC gain/dB/phase/amplitude via
certified `magnitude`/`phase`/`magnitude_db`/`rms_from_peak` with
`H = X/Xac` (unique AC source) and `H = 0` -> `UNDEFINED` (N-050/N-051),
bandwidth as the certified Bode interval only (N-052), `dc_value` on
OP (N-065/VLAB-001).

Reference validation: sine RMS over 1 period at 1000 samples/period =
`A/sqrt(2)` within the `(wh)^2`-order PL bound (rel < 1E-3, measured
far below); `H = 1/(1+jx)` gain/phase/dB closed forms; trapezoid and
triangle exactness (N-037/N-042).

## Stimuli

`StimulusSpec` (DC/STEP/PULSE/SINE/AC, closed per-kind fields)
translated into certified `parameters["wave"]` / `value` /
`ac_mag`+`ac_phase`+`phase_unit` on the run copy only.
`function_generator` is a pure factory: sine lag via
`td = delay + phase_lag/(360 f)` (lead rejected, N-055), pulse/square
duty at 50 % crossings with `width = duty period - (tr+tf)/2`
(negative rejected, N-056), dc = offset. Triangle/noise/arbitrary
rejected (no certified generator). Delay is a time shift, not a hold
(certified sine has `td >= 0`, no phase, no pre-delay hold — N-055
phase-lag-only test). Stimuli on non-V/I or twice on one source are
config errors (N-015). Waves on wave-ignoring analyses use the DC
value with a `stimulus_ignored_by_analysis` diagnostic (never silent).

## F8-H Integration

`lab experiment -> certified DC engine -> result`: OP and every
sweep/MC/corner point go through `solve_point` /
`solve_nonlinear_dc_state` on the DC equivalent. No Newton/MNA/device
copy. N-064: lab OP `to_dict()` equals direct `solve_nonlinear_dc`
bit-for-bit. Q1 constants recorded in provenance (never overridden).

## F8-I Integration

Existing BJT engines only. `device_current` probes `Q:C/B/E`
(N-067: KCL over terminals sums to 0 within 1E-30; branch currents
equal direct solve). No alternate BJT; F8-I untouched (byte-identical).

## F8-J Integration

`AC_POINT` calls certified `solve_small_signal_ac` directly (any
F8-J-supported circuit, nonlinear included — N-060 equality with a
direct call on a diode circuit). `ComplexResponse` views, magnitude /
phase / dB per F8-J conventions (`e^{+jwt}`, peak phasors, phase in
(-pi, pi]). No new AC solver. AC gain uses `H = X/Xac` with the unique
AC excitation source; zero/ambiguous input is `UNDEFINED` (F8-D5
semantics).

## F8-K Integration

MOSFET/JFET/diode-kind parameters editable only through the closed
F8-M registry (`resolve_param` + `substitute`; categorical fields
rejected). N-067: diode, BJT, MOSFET OPs equal direct engines. No
arbitrary attribute access (no `getattr` anywhere in `lab/`, N-091);
no object traversal. The lab cannot bypass the F8-M allowlist.

## F8-L Integration

`TRANSIENT` is exactly one `solve_transient` call. No BE/TR/BDF2/LTE/
adaptive/Newton-DAE/rollback duplication. Step-excitation runs use
step-capable tolerances (F8-L step regime: `h_min = 1E-12`,
`reltol = 1E-4` functional / `1E-6` analytic, measured max error
7.2E-8 vs closed form). Waveforms are exact copies of committed
samples (N-054). `TransientResult.value_at()` is NEVER used for
measurements/scope (nearest-sample trap, audit finding 3):
`grep value_at lab/` is empty; all resampling is PL interpolation
with explicit tests (N-026/N-027/N-030). Failed transients carry no
waveform; measurements are `NO_DATA` (N-057).

## F8-M Integration

Every F8-M result is wrapped unchanged (`==` on `to_dict()` with
direct calls, N-068..N-073): M1 (VLAB-004 + SweepReading row equality),
M2, M3 (honesty text verbatim, `CORNER_HONESTY`), M4 (derivative table
with dimensions, normalized flag), M4-AC (magnitude/phase/dB
derivatives), M5 (seed injected from the definition; same
experiment+seed+config -> same samples/statistics/digest, VLAB-005;
different seed -> different plan). Seed contract: MC required (int >=
0), elsewhere forbidden (no silent unused seed, N-013). No sweep/MC/
sensitivity logic duplicated.

## Serialization

Schema `f8n-lab/1`, canonical JSON (UTF-8, sorted keys, compact
separators, ASCII, no NaN/Infinity). Stable across dict/insertion
orders (N-075). Decimal/Quantity/DecimalComplex/Fraction/
RationalComplex round-trip exactly (N-076). Closed per-type circuit
schema (R/C/L/T/O parameter-free; V/I wave+AC keys; D/Q/M/J exact
device sets; E/G `cp`/`cn`; H/F `control_ref`; unknown keys ->
`INVALID_SERIALIZATION`, N-077). CSV for waveforms/tables/sweeps:
deterministic, unit-aware headers, RFC-4180 quoting, `None` as empty
field plus status column (N-078, golden text). 64 MiB guard at save
(raise) and before parse (N-079). No pickle/eval path (N-080,
structural AST test).

DEVIATION D-R1: decimals are stored as exact `str(d)`, not
`str(d.normalize())`. `normalize()` is exact but not
representation-preserving (`Decimal(900)` -> `"9E+2"`), and certified
engines hash `str()` of Decimals into their digests (F8-M
plan/config digests). Normalizing would flip engine digests across a
save/load round trip and break normative same-version replay
(`EQUIVALENT`). `str(d)` round-trips bit-for-bit with no float or
precision involved; the normalize mandate's intent is fully preserved.

## Replay

`save -> load -> replay -> compare` (N-081: `EQUIVALENT`, comparable).
Load recomputes experiment ids/digests and run digests over stored
documents; any mismatch (tampered digest, edited seed/value) ->
`INVALID_SERIALIZATION` (N-082). Schema mismatch and engine-version
mismatch are explicit (`VERSION_MISMATCH` without execution unless
`allow_version_mismatch`, then executed but `comparable=False`,
N-083). Differing results report the first differing JSON path
(N-084). Same-version deterministic replay only; cross-version
equivalence is not claimed. Notes/annotations never affect replay
(N-087).

## Provenance

Every run records: schema, lab/engine versions, experiment + circuit
digests, analysis kind + canonical config, sorted overrides/stimuli/
probe/instrument/measurement specs, seed, Q1 + transient tolerances,
engine result digests (`topology_digest`, `solver_digest`, F8-M
`digest`, warm-start/init counts), `dc_mapping` note, engine status,
result digest (N-085). No timestamps/uuids/addresses/wall-clock
(N-086, string scan). Volatile engine metadata (`provenance.
timestamp` embedded by F8-J) is scrubbed from the stable payload
(audited: the only volatile key across OP/TRANSIENT/AC/M1..M5), so
digests are bit-stable while certified engine digests are untouched.
`session_id`, `run_id`, labels, metadata, notes excluded from digests
(N-087, cross-session equality test).

## Determinism

Triple execution across DC, AC_POINT, TRANSIENT, M1, M2, M3, M4,
M4-AC, M5: result, measurements, serialization text and digests
identical (N-088). Insertion-order invariance (N-089). Ambient
`decimal` context (`prec=10`, `ROUND_DOWN`) and locale-independent
operation: lab arithmetic runs under an explicit fresh context;
payloads digest live exact numerics, never ambient-formatted strings
(N-090).

AUDIT FINDING (fixed during implementation): engine `to_dict()`
presentation formatting (`Quantity.format()`) rounds through the
*ambient* context, so digests must not cover `to_dict()` strings.
Lab payloads canonicalize live result objects (full precision).
Equality with direct calls (N-064..N-073) still holds because both
sides carry the same exact numerics.

## Security

AST/static scans over `lab/*.py` (N-091/N-092): 0 `eval`, 0 `exec`,
0 `compile`, 0 `__import__`, 0 `getattr`/`setattr` (bare calls;
`object.__setattr__` for frozen-dataclass normalization is an
attribute call, same idiom as the certified engines), 0 `open`,
0 `vars`/`globals`/`locals`, 0 subprocess, 0 `os`/`sys`, 0 socket,
0 `importlib`, 0 pickle/marshal, 0 urllib, 0 numpy/scipy/math.
Every user selector is a typed enum or allowlist; parameter addresses
pass the closed F8-M registry; labels/notes are inert length-bounded
strings. Deserialization is schema-validated through allowlisted
constructors with digests recomputed and compared. Hostile-input
tests N-093 (`__import__('os').system('x')` stored inert, round-trips,
hostile addresses rejected) and N-094 (non-JSON, wrong types, unknown
analysis/probe kinds, oversized) pass.

## Resource Budgets

`MAX_DISPLAY_SAMPLES = 10000`, `MAX_SCOPE_CHANNELS = 4`,
`MAX_EXPERIMENTS_PER_SESSION = 256`, `MAX_RUNS_PER_SESSION = 1024`,
`MAX_MEASUREMENTS_PER_EXPERIMENT = MAX_PROBES_PER_EXPERIMENT = 64`,
`MAX_SERIALIZED_BYTES = 64 MiB` (inherited: `MAX_TRANSIENT_STEPS+1`,
`MAX_SWEEP_POINTS`, `MAX_MC_ITERATIONS`, `MAX_WORST_PARAMS`).
Overflow is explicit (`BUDGET_EXCEEDED` / `SERIALIZATION_TOO_LARGE`),
never silent truncation (N-022/N-079/N-105). No throughput/time limit
exists anywhere.

## Validation

VLAB-001 (resistive `10 V -> 1 k -> 2 k`, HP path): `V(out) = 20/3 V`
absolute error `0E-49`; `I(R1) = 10/3000 A` absolute error `0E-52`;
tolerance 1E-40 relative. PASS.

VLAB-002 (RC step `0 -> 1 V`, edge at `t0 = 1 ms`, `R = 1 kohm`,
`C = 1 uF`, TR tight, `tstop = 6 ms`; DEVIATION D-V2: the design gate
writes `t0 = 0`, but the certified engine initializes the capacitor
from the DC operating point at `t = 0`, where the source already reads
`v2` — the visible edge requires `t0 > 0`): committed waveform vs
`V(t) = Vinf + (V0 - Vinf) e^(-t/RC)` worst error 7.2E-8 (bound
1E-5); `rise_time_10_90 = RC ln 9`, `settling_time` (2 %) `= RC ln 50`,
`mean`/`rms` over `[t0, t0+5RC]` from closed-form integrals, all
within 1E-3 relative; scope reading equals PL interpolation of the
same samples at every grid point. PASS.

VLAB-003 (AC divider `R-C` at 1 kHz, HP): `|H| = 1/sqrt(1+(wRC)^2)`,
`phase = -atan(wRC)`, `dB = 20 log10|H|` within 1E-40 relative. PASS.

VLAB-004 (DC sweep lab vs direct `solve_dc_sweep`): wrapped result
`to_dict()` bit-equal; every `SweepReading` row (axis, value) equals
the direct point. PASS.

VLAB-005 (Monte Carlo seed 42 x3): identical plan digest, samples,
statistics and `result_digest`; seed 43 gives a different plan
digest. PASS.

VLAB-006 (save -> serialize -> deserialize -> run -> compare):
`EQUIVALENT`; tampered digest -> `INVALID_SERIALIZATION`; altered
`engine_versions` -> `VERSION_MISMATCH`. PASS.

Error validation (N-095..N-107): invalid circuit/node/branch/parameter/
probe/measurement/analysis/seed/serialization, divergence, singular
system, unknown ids, schema/version mismatch, budget overflow, partial
results, failed-data measurements — every one yields its honest
status; failure never becomes 0.

## Test Results

| Suite | Tests | Passed | Failed | Skipped |
|:---|---:|---:|---:|---:|
| F8-N lab (N-001..N-110, VLAB, refs, aliasing, bench) | 125 | 125 | 0 | 0 |
| F8-H/I/J/K/L/M (N-108 subprocess) | all | all | 0 | 0 |

N-001..N-110: each id has at least one named test (`test_n001` ..
`test_n110`, N-110 twice); VLAB-001..VLAB-006 each named. Measurement
references, hostile-input, serialization, replay, determinism,
provenance, float/AST/dependency scans included. Adversarial review
(phase 69) executed: session clone/branch/reset/close/failed-op,
experiment same/different content + mutation + shared-dict/list
aliasing, failed/unsupported/partial runs, empty/single-sample/
constant/monotonic/negative waveforms, no/multiple crossings,
tampered/schema-mismatched/unknown-enum/missing-field/oversized
documents, hostile strings/addresses/schemas.

## Regression

- F8-H, F8-I (x2 files), F8-J, F8-K, F8-L, F8-M suites: green
  (N-108, subprocess, `not slow`).
- Global suite: **2238 passed, 2 skipped, 1 failed** in 49 min. The
  single failure is `test_f7a_runtime.py::
  test_real_ngspice_no_orphan_processes`, which asserts no stray
  ngspice console process exists: during the global run an orphan
  `ngspice.exe` (PID 18784) was alive — leftover of the operator's own
  hung `ngspice --version` probe at session start (ngspice ignores the
  flag and waits on stdin; the harness killed the shell, not the
  console). `lab/` cannot spawn processes (N-092 AST-proven; no F8-N
  test invokes ngspice). Re-run of `tests/test_f7a_runtime.py` alone:
  exit 0 (all pass). No lab involvement; no engine modified.
- The 2 skips are pre-existing and correctly classified
  (`tests/test_pdf.py`: reportlab absent).
- Certified modules byte-unchanged: `git status` on `mna/`, `ac/`,
  `circuit.py`, `units.py` empty (N-110).

## ngspice

- Found via PATH: `C:\Users\dmart\Documents\ngspice-47_64\Spice64\bin\
  ngspice.exe` (`shutil.which`, `where.exe` agree). Lab resolves it
  only through PATH/config (never hardcoded); ngspice is external
  validation only, never a lab runtime dependency.
- F8 tests assert ngspice version 47 and pass against it.
- F7 suite with ngspice in PATH: **302 passed, 0 skipped** — no F7
  skip remains; the only repo-wide skips are the 2 pre-existing
  reportlab ones in `test_pdf.py`. Nothing was forced: F7 tests ran
  unmodified.
- Interactive `ngspice --version` was not executed standalone (the
  Windows console build waits on stdin); version evidence comes from
  the passing F7 assertions instead.

## Benchmarks

Diagnostic only (no normative limits; wall time printed, never
asserted):

- session + OP + measurement + serialization: 0.022 s, 5674 bytes.
- transient (TR step regime, 317 committed samples): 1.623 s,
  120000 bytes serialized.
- Monte Carlo (4 iterations): 0.038 s, 5728 bytes.

## Limitations

Explicit, by design: ideal instruments only (no loading, noise,
bandwidth limits, gain/offset error); no hardware; no GUI/web/CLI/
notebooks; no network/cloud/collaboration; no cancellation
(single-threaded synchronous execution; `CANCELLED` deliberately not
a status); no non-ideal measurement loading; no nonlinear AC sweep
(`UNSUPPORTED`); transient currents only where F8-L exposes them
(R derived, L direct, else `UNSUPPORTED` — F8-L not modified); no
FFT/THD/power/energy/XY/math channels; no topology editing inside a
session (circuit fixed; registry overrides + stimuli only);
same-version deterministic replay only; no wall-clock benchmarks;
display units not preserved (base units canonical); `dc_value`
measurement on OP only (sweeps use the sweep viewer); meters on
OP/DC_SWEEP/AC_POINT/TRANSIENT, scope on TRANSIENT, FR viewer on
AC_SWEEP, sweep viewer on F8-M analyses (other combinations are
static `INVALID`, capability gaps are run-time `UNSUPPORTED`).

## Deviations

- **D-01..D-08** (from the design gate, none contradicting certified
  guarantees): no persistent `Laboratory` object (pure API surface);
  no `WaveformProbe`/`FrequencyProbe` entities; no `CANCELLED` status;
  ideal instruments only; `AC_SWEEP` linear-only + transient currents
  R/L-only; explicit rise/settling/overshoot parameters (plus an open
  `rise_time_10_90`-style explicit call); phase-lag-only generator
  with delay-as-shift; no plotting/UI/CLI/notebooks.
- **D-R1** (this phase): decimals serialized as exact `str(d)`, not
  `str(d.normalize())` — `normalize()` is not representation-
  preserving and would flip certified `str()`-based engine digests
  across save/load, breaking normative replay. Intent preserved.
- **D-V2** (this phase): VLAB-002 edge at `t0 = 1 ms` instead of
  `t0 = 0` — at `t0 = 0` the certified engine initializes the
  capacitor from the DC operating point (source already at `v2`), so
  no edge is visible. Documented with cause.
- **Run digest excludes instrument specs** (scope/meter/viewer
  configs are pure views): required by N-030 (`result_digest`
  unchanged by scope changes). Experiment identity still covers the
  full configuration. Documented in `serialize.py`.
- **`dc_value` on OP only; meters/viewers per the applicability
  tables** (§Limitations): interpretations of the design gate's valid-
  analyses columns, no certified guarantee affected.
- No scope creep: no solver, no device model, no waveform engine, no
  GUI, no hardware, no F8-O content. `git audit` (phase 75) shows only
  F8-N/test/docs/roadmap paths.

## Final Verdict

`F8-N CERTIFIED`