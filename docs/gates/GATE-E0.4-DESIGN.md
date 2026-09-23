# GATE E0.4 — Explainable Engineering Deep Observability & Resolver Retrofit — DESIGN

- **Baseline:** `12625cf` (E0.3 COMPLETE / CERTIFIED), with
  `HEAD == origin/main`, branch `main` and a clean tree.
- **Principle:** CERTIFIED ENGINE → REAL OBSERVATION → ExecutionTrace →
  PEDAGOGICAL TRACE → VERIFICATION.
  - E0.4 is an evolution of the E0 family on `execution-trace/1`, not a
    second explanation system.

## 1. Audit (repository evidence)

| Area | Evidence | Finding |
|---|---|---|
| F8-L transient | `mna/transient.py`, inner Newton loop | `jac`, `lin.solution` (Δx), `final_f`, `x`, α and the backtracking loop all exist per iteration. E0.3 exposed only α and ‖F‖. |
| F8-D5 AC sweep | `ac/response.py frequency_response` | One `solve_ac` per frequency. `solve_ac` already has the E0.3 `ac_system` / `ac_outcome` observer, but the sweep did not forward one. |
| F8-K | `mna/mosfet.py mos_operating_point`, `mna/jfet.py jfet_operating_point`, `mna/diode.py variant_current` | Region, I_D, gm, gds, gmb, Vth, Vov and the Zener/photo branch are all computed in one function per model. The F8-H Newton system calls them through terminal-current / Jacobian wrappers. |
| F8-K text form | `execution/newton.py` | String parameters (`polarity` NMOS/PMOS/NCHAN/PCHAN, diode `kind`) and the Kp (A/V²) and λ (1/V) dimensions had no text form, so these circuits could not be traced. |
| F8-M | `mna/analysis.py` (`solve_param_sweep`, `solve_worst_case` → `_drive_points`), `mna/sensitivity.py solve_dc_sensitivity`, `run_monte_carlo_native` | Sweeps and corners share the E0.3-observed driver. Sensitivity builds dF/dp and solves `J·dx/dp = −dF/dp` with the certified J. `MCResult` records each sample's sub-seeds, parameters, status and observables. |
| F8-O | `metrology/o2_propagate.py evaluate_budget` | Ingress validation around `gum.evaluate_gum`, which already has the E0.1 observer. |
| F8-P1 | `control/stability.py routh_of_tf`, `pole_inventory` | Exact Routh table (Fraction rows, first column, ε / auxiliary flags) in `RouthResult`; independent Durand–Kerner inventory. |
| F8-P2 | `dsp/dft.py fft`, `dsp/sampling.py` | Radix-2 stages with twiddles; `nyquist_*` / `alias_of` are closed formulas. |
| F8-P3 | `rf/lines.py reflection_coefficient`, `rf/margins.py`, `rf/smith.py` | Γ → VSWR / RL / ML, each an engine call; the Smith map is an independent route. |
| F8-P4 | `comms/simulation.py simulate_bpsk` | One loop runs bit → symbol → noise → sample → decision. |
| F8-P5 | `satcom/synthesis.py forward_budget` | `BudgetResult` is documented as "every intermediate kept". |
| F15 / F8-N | `lab/run.py`, `LabService`, E0.3 `lab.run-detail` | The E0.3 test `g03` pins PARAM_SWEEP as UNSUPPORTED in `lab.run-detail`, so the F8-M lab kinds get a new operation. |

## 2. Formal retrofit matrix

The E0 classes:

- **E0-A COMPATIBLE:** the engine already exposes the data, through an
  observer or its result.
- **E0-B ADAPTABLE:** a small optional hook exposes it, with `observer=None`
  inert.
- **E0-C REQUIRES MODIFICATION:** exposing it needs structural changes.
- **E0-D REDESIGN:** the architecture prevents observing it.

| Engine | Capability | Observable after E0.4 | Missing | E0 class | Action |
|---|---|---|---|---|---|
| F8-L | Newton inside each transient step | x_k, F(x_k), J(x_k), Δx, α, every backtracking trial (α, norm, accepted), ‖F‖, res_ok / step_ok, the failure reason and the failing iteration's data | — | E0-B | `newton` rows extended (index-stable); `newton_failure` on rejects; `engineering.transient-newton` |
| F8-L | LTE, accept / reject, aborts | E0.3 (unchanged) | the aborts listed in the E0.3 §6 table | E0-B | reused |
| F8-D/F8-J | AC sweep matrix per frequency | f, ω, A(jω), b(jω), x(jω) of each frequency; H, \|H\|, ∠H | — | E0-B | `frequency_response(..., observer)`; `engineering.ac-sweep-mna` |
| F8-K | MOSFET L1 (NMOS / PMOS) | VGS, VDS, VSB, Vth, Vov, region, I_D, I_S, gm, gds, gmb, the 4×4 block, parameters | — | E0-B | optional `trace` in `mos_operating_point` / `mos_terminal_currents` / `mos_jacobian` |
| F8-K | JFET (N / P channel) | VGS, VDS, region, I_D, I_S, gm, gds, the 3×3 block, parameters | — | E0-B | optional `trace` in `jfet_operating_point` (+ wrappers) |
| F8-K | Zener, LED, Schottky, photodiode | branch (shockley / photo / zener-forward / zener-breakdown), Vd, I, g, parameters | — | E0-B | optional `trace` in `variant_current` / `variant_companion` |
| F8-K | small-signal parameters in AC (F8-J) | E0.3: the linearised system | per-device gm/gds inside the AC trace | E0-A | through `SmallSignalACResult`, not traced separately (§6) |
| F8-M | parameter sweep | every point: attempt, x₀, Newton iterations, final state | — | E0-B | observer through `_drive_points`; `engineering.param-sweep` |
| F8-M | worst case | every corner + engine extrema | — | E0-B | same driver; `engineering.worst-case` |
| F8-M | DC sensitivity | x*, J(x*), dF/dp, dx/dp, observable derivatives | — | E0-B | `sensitivity_system` / `sensitivity_parameter`; `engineering.dc-sensitivity` |
| F8-M | AC sensitivity | result only | dA/dp, db/dp, dX/dp | E0-C | declared (§6) |
| F8-M | Monte Carlo | seed, plan digest, per sample: sub-seeds, sampled parameters, status, iterations, observables; statistics | per-sample Newton internals | E0-A | from `MCResult` (no re-draw); `engineering.monte-carlo` |
| F8-N | Virtual Lab F8-M kinds | PARAM_SWEEP, CORNERS, SENS_DC, MONTE_CARLO re-observed + same-result CHECK | SENS_AC | E0-B | `lab.run-analysis` (service level; the UI does not offer these kinds) |
| F8-O | GUM budget | the E0.1 `engineering.gum` observation, now reachable through `evaluate_budget` | opaque callables (UNSUPPORTED, E0.1-R+) | E0-A | observer pass-through; no second GUM |
| F8-O | metrology Monte Carlo | reuses F8-M M5 | — | E0-A | through `engineering.monte-carlo` |
| F8-P1 | Routh–Hurwitz | table rows, first column, sign changes, ε / auxiliary, verdict; DK inventory | — | E0-A | `control.routh` |
| F8-P1 | margins / bisection | E0.1 `control.margins` | — | E0-A | unchanged |
| F8-P1 | PID, state space, root locus | results only | intermediate algorithm states | E0-C | declared (§6) |
| F8-P2 | FFT | bit-reversed input, each stage's twiddles and vector, X[k]; direct DFT as reference | — | E0-B | `fft(..., observer)`; `dsp.fft` |
| F8-P2 | sampling / Nyquist / alias | f_N, rate, verdict, alias | — | E0-A | `dsp.sampling` |
| F8-P2 | filters (bilinear, SOS) | results only | design steps | E0-C | declared (§6) |
| F8-P3 | reflection, VSWR, RL, ML, Smith | every engine call in the chain | — | E0-A | `rf.reflection` |
| F8-P3 | matching, S / ABCD networks | results only | intermediate transformations | E0-C | declared (§6) |
| F8-P4 | BPSK over AWGN | setup, every bit (uniform, bit, symbol, noise, sample, decision), errors, BER, 5σ | — | E0-B | `simulate_bpsk(..., observer)`; `comms.bpsk` |
| F8-P4 | other modulations / BER curves | analytic results | — | E0-A | not traced in E0.4 (§6) |
| F8-P5 | forward link budget | EIRP, FSPL, Lmisc, Grx, Pr, G/T, C/N0, C/N, Eb/N0 | — | E0-A | `satcom.link-budget` |
| F8-P5 | inverse synthesis | results only | search steps | E0-C | declared (§6) |

## 3. Architecture

```text
engine(observer=None) ──▶ optional observer (execution layer, immutable snapshots)
                          ▼
execution/engineering_deep.py ──▶ ExecutionTrace (execution-trace/1)
                          ▼
application/ExplainService.deep_trace (fixed registry) ──▶ explain_render (lessons)
                          ▼
UI (Virtual Lab: existing buttons; F8-M lab kinds are service level)
```

- **Engines never import `domain.execution`, UI or Qt** (AST tests).
- **Observers** receive tuples of Decimal / Fraction / str / bool / int /
  frozen complex.
  - They never decide convergence, change tolerances or order, or mutate
    the solver.
  - With `observer=None` no log is allocated and no snapshot is built.
- **Fixed registry:** each operation declares its id, text inputs, builder
  (`deep_trace`), renderer (`LESSON_OPERATIONS`), labelled CHECKs, replay
  policy and support status.
  - Replay uses `replay_deep`.
  - `lab.run-analysis` is refused for explanation replay: the lab replays
    its own runs.

## 4. Planned changes (engines: optional and inert)

- **`transient.py`:** deep `newton` rows (x_k, F, J, Δx, trials) and
  `newton_failure`.
- **`response.py`:** `frequency_response(..., observer)`.
- **`mosfet.py` / `jfet.py` / `diode.py`:** optional `trace` lists.
- **`nonlinear.py`:** `fk_log` / `fk_jac_log`, the `fk_parameters` /
  `fk_devices` / `fk_jacobians` observer kwargs, and a deterministic KCL
  representative.
- **`analysis.py`:** `solve_param_sweep` / `solve_worst_case` take an
  observer.
- **`sensitivity.py`:** the sensitivity observer.
- **`o2_propagate.py`:** observer pass-through.
- **`dft.py`:** the FFT observer.
- **`simulation.py`:** the BPSK observer.
- **`execution/newton.py`:** the F8-K text form (closed enumerations; A/V2
  and /V suffixes) and the F8-K events.
- **`execution/analog_detail.py`:** the point renderer is extracted (same
  output), and the transient observer accepts `newton_failure`.
- **New module:** `execution/engineering_deep.py`.

## 5. Limits

| Limit | Value |
|---|---|
| MAX_EVENTS / MAX_VALUES_PER_EVENT / MAX_STRING_LENGTH | 10 000 / 64 / 512 (execution-trace/1) |
| MAX_MATRIX_DIMENSION shown | 8×8 A(jω) (OMITTED + SHA-256 above); 4×4 Newton J / Δx / x_k (digest above); 6×6 sensitivity J |
| MAX_SWEEP_POINTS | 500 DC points / frequencies (refused above) |
| Monte Carlo samples listed | 200 (`TRACE_TRUNCATED` above; statistics cover all) |
| BPSK bits listed | 64 (`TRACE_TRUNCATED` above; error count covers all) |
| Optional detail events / MAX_TRACE_BYTES | 4000 events / 5 MB conservative estimate (E0.3 budget); codec refuses > 8 MiB |

## 6. Declared limitations (none of these is invented)

| ENGINE | CAPABILITY | STATUS | MISSING OBSERVATION | WHY | SAFE FUTURE EXTENSION |
|---|---|---|---|---|---|
| F8-M | AC sensitivity | UNOBSERVABLE | dA/dp, db/dp, dX/dp per parameter | `_solve_ac_sensitivity` has no observer; its results are summaries | the same `sensitivity_parameter` hook |
| F8-M | Monte Carlo per-sample Newton | UNOBSERVABLE in the MC trace | iterations inside each sample | cold `solve_point` without an observer | pass an observer to `solve_point` per sample |
| F8-J | per-device small-signal parameters inside the AC trace | PARTIAL | gm/gds rows in `engineering.ac-mna` | carried in `SmallSignalACResult`, not traced | an event from the result fields |
| F8-P1 | PID tuning, state-space conversions, root locus | UNOBSERVABLE | intermediate algorithm states | closed functions returning results | observers per algorithm |
| F8-P2 | IIR/FIR design, SOS decomposition | UNOBSERVABLE | design steps | same | same |
| F8-P3 | matching, network conversions | UNOBSERVABLE | intermediate transformations | same | same |
| F8-P4 | modulations other than BPSK, BER curves | UNOBSERVABLE (analytic) | — | only BPSK has a simulation loop | observer per simulation |
| F8-P5 | inverse synthesis | UNOBSERVABLE | search steps | closed-form / search results | observer in `synthesis` |
| Virtual Lab | SENS_AC | UNSUPPORTED | — | see F8-M AC sensitivity | — |
| F8-L | transient Newton failure path | OBSERVABLE, not exercised by a real circuit in the tests | — | every circuit tried converged inside the step | a failing fixture when one is found |

## 7. Policy: every new resolver is born E0-compatible

1. **Optional observer.** The public entry point takes `observer=None`.
   With `None` it allocates no log and makes no call, and results are
   byte-identical.
2. **Immutable snapshots.** Observers receive tuples of Decimal / Fraction
   / str / bool / int / frozen complex values, captured at the point of
   computation, never recomputed.
3. **No layering inversion.** The engine never imports
   `domain.execution`, UI or Qt.
4. **Declare, don't invent.** Every data item the resolver cannot expose
   is listed as ENGINE / CAPABILITY / STATUS / MISSING OBSERVATION / WHY /
   SAFE FUTURE EXTENSION in its gate.
5. **Trace and registry.** A trace operation with text inputs is added to
   the fixed ExplainService registry and to `LESSON_OPERATIONS`.
   - Its replay is the same builder over the recorded inputs.
   - Its bounds are explicit, and truncation is an explicit
     `TRACE_TRUNCATED`.
6. **Required tests.**
   - Observer equivalence (without vs recording, immutable).
   - Anti-fake: nothing unobserved appears.
   - Determinism across `PYTHONHASHSEED` (subprocesses).
   - AST security.
   - Measured performance.
7. **Honest labels.** CHECKs are labelled SYMBOLIC only for exact
   equality or exact arithmetic, NUMERIC for toleranced comparisons, and
   NONE when not applicable.

## 8. Security, determinism, compatibility, risks, criteria

- **Security:**
  - AST checks on the new and modified execution modules: no eval, exec,
    compile, `__import__`, getattr, setattr, open, pickle, marshal,
    importlib or subprocess, and no os, sys, shell or dynamic import.
  - The engines contain no eval, exec, compile or `__import__`, and no
    execution, UI or Qt imports.
  - Text inputs are bounded and validated; enumerations are closed.
- **Determinism:** the digests of 11 representative traces are identical
  across `PYTHONHASHSEED` = 0 / 11 / 2024 / random in separate processes.
  - The F8-H KCL representative is now deterministic (see §4).
- **Compatibility:**
  - The E0 to E0.3 traces are unchanged (their test files pass unmodified).
  - The `execution-trace/1` schema is unchanged.
  - F8-K circuits could not be traced before, so no existing trace changes.
- **Risks:**
  - Observer-only code paths in certified engines. Mitigation: equivalence
    tests per engine, plus the full suite.
  - The KCL fix changes a reported representative, not a value.
- **Criteria:** §30 of the phase specification.
