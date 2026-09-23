# GATE E0.3 — Explainable Engineering Completeness — DESIGN

- **Baseline:** `69143fb` (E0.2 COMPLETE / CERTIFIED), with
  `HEAD == origin/main` and a clean tree.
- **Principle:** REAL ENGINE EXECUTION → REAL OBSERVATIONS → ExecutionTrace
  → PEDAGOGICAL STEPS → VERIFICATION.
  - There is never a second solver.
  - Every E0.3 trace is one execution of a certified engine with its
    optional observer attached.

## 1. Audit and classification

| Engine | Module | Before E0.3 | After E0.3 |
|---|---|---|---|
| AC (F8-D3) | `ac/solver.py` `solve_ac` / `solve_ac_problem` | CERTIFIED + PARTIALLY OBSERVABLE (result level; "MNA matrix unavailable") | **CERTIFIED + FULLY OBSERVABLE**: `ac_system(unknowns, A, b, kind, f, ω)` is the matrix/RHS exactly as passed to the F8-D2 complex solver; `ac_outcome(status, mode, rank, x, residual_norm, backward_error)` |
| AC_POINT (Virtual Lab) = small-signal AC (F8-J) | `ac/small_signal.py` `solve_small_signal_ac` | CERTIFIED + PARTIALLY OBSERVABLE | **CERTIFIED + FULLY OBSERVABLE** for the linearised complex system (same protocol). The DC bias point comes from F8-H (traced separately). |
| AC_SWEEP (F8-D5) | `ac/response.py` `frequency_response` (+ `analyze_bode` in the lab) | Lab explanation UNSUPPORTED | **CERTIFIED + OBSERVABLE at point level**: frequency → independent D3 solve → H, |H|, ∠H, status. A per-point solve is direct (no iterations); its matrix is available through `engineering.ac-mna` at that frequency. |
| DC_SWEEP (F8-M) | `mna/analysis.py` `solve_dc_sweep` → `_drive_points` → `solve_point` → `solve_nonlinear_dc_state` | CERTIFIED + PARTIALLY OBSERVABLE (per-point counts only) | **CERTIFIED + FULLY OBSERVABLE**: `sweep_attempt(index, label, parameters, attempt, x_init)` with the exact initial guess handed to Newton, then that attempt's Newton calls (F8-H contract), then `sweep_attempt_end(index, attempt, status, iterations, x_final)` |
| TRANSIENT (F8-L) | `mna/transient.py` `solve_transient` | CERTIFIED + PARTIALLY OBSERVABLE (aggregates) | **CERTIFIED + OBSERVABLE per step** (see below). The per-iteration J/Δx inside a step is not exposed (§6). |
| TransferFunctionTF (F8-P) | `control/tf.py` | CERTIFIED + OBSERVABLE (evaluation) | unchanged engine; the trace adds the engine's own `tf_to_zpk` (gain, zeros, poles, Durand–Kerner) and `ZPK.evaluate` |
| BJT / Ebers-Moll (F8-I) | `mna/bjt.py`, `mna/nonlinear.py` | **F8-I IMPLEMENTED: yes; CERTIFIED: yes** (ROADMAP "F8-I — CERTIFICADO", `GATE-F8I.md`). Internals not exposed ("Detalle de dispositivo no expuesto"); `polarity` could not be written as text | **CERTIFIED + FULLY OBSERVABLE**: V_F/V_R, I_F, I_R, I_C, I_B, I_E, g_F, g_R and the 3×3 Jacobian block captured *inside* `bjt_terminal_currents` / `bjt_jacobian`; α_F, α_R and every parameter from `BJTParams` |
| Linear MNA | `mna/solver.py` | CERTIFIED + FULLY OBSERVABLE (E0.2) | unchanged |
| F8-H nonlinear DC | `mna/nonlinear.py` | CERTIFIED + OBSERVABLE (E0.2) | extended with BJT logs; the E0.2 contract is unchanged |
| SimulationService / Virtual Lab (F8-N/F15) | `lab/run.py`, `LabService`, `ui/virtual_lab.py` | CERTIFIED; E0.2 "Explicar último" (result level) | + `working_circuit(session_circuit, definition)` (pure extraction of the run snapshot) + «Explicar en detalle» |
| ExecutionTrace | `domain/execution/model.py`, `codec.py` | `execution-trace/1` | **unchanged** (no schema extension) |
| ExplainService | `application/explain_service.py` | fixed registry (E0.2) | fixed registry extended (§4) |

## 2. Engine changes (optional, read-only, inert with `observer=None`)

Every value an observer receives is an immutable snapshot: tuples of
Decimal, Fraction, str, bool or int, or frozen DecimalComplex /
RationalComplex. With `observer=None`, no log is allocated, no snapshot
is built and no call is made.

- **`ac/solver.py`**
  - `solve_ac(..., observer=None)` and `solve_ac_problem(..., observer=None)`.
  - `ac_system` is called before `solve`; `ac_outcome` is called after it.
  - Unknown labels come from `mna.problem.unknown_labels` (the certified
    index maps).
- **`ac/small_signal.py`**
  - `solve_small_signal_ac(..., observer=None)`, with the same two calls
    around its `linsolve`.
  - Labels come from its own `node_index` / `vsource_index`.
- **`mna/bjt.py`**
  - `bjt_injection_currents`, `bjt_terminal_currents`, `bjt_conductances`
    and `bjt_jacobian` accept an optional `trace` list.
  - When the list is given, it receives `(V_F, V_R, I_F, I_R)` or
    `(V_F, V_R, g_F, g_R)` exactly as computed inside the function.
  - `None` is the default and is inert.
- **`mna/nonlinear.py`**
  - `_NewtonSystem.bjt_log` / `bjt_jac_log` are `None` unless an observer
    is attached. They are reset at the top of `residual()` / `jacobian()`.
  - `newton_start` gains `bjt_parameters`, `bjt_devices`.
  - `newton_iteration` gains `bjt_devices` (at x_(k+1)) and
    `bjt_jacobians` (at x_k).
  - `solve_nonlinear_dc_state(..., observer=None)`.
- **`mna/analysis.py`**
  - `solve_point(circuit, x_init=None, observer=None)`.
  - `_drive_points(..., observer=None)`, `_finish_sweep(..., observer=None)`
    and `solve_dc_sweep(circuit, config, observer=None)`.
  - The sweep's warm/cold policy is untouched. The observer sees the very
    `x_init` handed over.
- **`mna/transient.py`** — `solve_transient(circuit, config, observer=None)`:
  - `transient_start(method, order, lte_constant, adaptive, unknowns, x0,
    dynamic, tstop, h_init, h_min, h_max, reltol, abstol)`
  - `transient_accept(index_of_t_next, t_n, h, t_next, x_n, predictor,
    x_next, newton_iterations, kcl, aux, e_max, lte, methods, next_h,
    forced, dynamic, newton=…)`
  - `transient_reject(cause, t_n, h, t_next, retry_h, e_max, lte,
    newton_iterations, newton=…)`
    - Causes: `residual_nonfinite`, `newton_failed`, `lte_nonfinite`,
      `lte`, `singular_jacobian`.
    - `retry_h = None` marks the attempt that stops the integrator.
  - `lte` rows are `(ref, C|L, y_old, y_pred, y_new, E)`, the predictor
    and corrector values of the controller.
  - `newton` rows are `(k, α, ‖αΔx‖∞, ‖F_KCL‖, ‖F_aux‖, res_ok, step_ok)`.
- **`lab/run.py`**
  - `working_circuit(session_circuit, definition)` is the pure extraction
    of the snapshot lines of `execute_run`, which now calls it.
  - Behaviour is identical (all F8-N tests pass).

## 3. Traces (new operations; the E0.2 traces are unchanged)

- **`engineering.ac-mna`** (`explain_ac_mna(spec, frequency, engine="ac"|"small-signal")`):
  - Steps:
    1. unknowns
    2. **A(jω)**: FULL entry by entry up to 8×8. Above that it is
       OMITTED, and a "Matriz: metadatos" event gives
       `matrix_detail`, size, non-zero count and the SHA-256 digest of
       the observed A.
    3. **b(jω)**
    4. the observed equation of each row (only the non-zero observed
       coefficients)
    5. resolution (status, mode, rank, residual norm, backward error)
    6. **x(jω)** (Re, Im)
    7. |x| via `phasors.magnitude`
    8. ∠x via `phasors.phase`
    9. CHECKs
  - CHECKs:
    - **A·x = b**: SYMBOLIC in exact rational mode, NUMERIC (80 digits,
      ≤ 1e-30) in HIGH_PRECISION.
    - **|x|² = Re² + Im²**: NUMERIC, ≤ 1e-40.
    - **observed x = published phasors**: SYMBOLIC.
    - The engine's KCL/KVL residuals: NUMERIC.
  - If the engine refuses before assembling: WARNING "MNA matrix
    unavailable" and the engine's status as ERROR. Nothing is
    reconstructed.
- **`engineering.dc-sweep-detail`**:
  - Per point:
    - every attempt ("arranque en caliente": x₀ = the observed x₀
      values; "arranque en frío": x₀ = 0)
    - each Newton iteration (α, halvings, ‖αΔx‖∞, ‖F‖ by block,
      res_ok, step_ok, V)
    - the point summary (status, init mode, iterations, parameter,
      voltages, observables)
  - CHECKs (all SYMBOLIC):
    - all points kept
    - warm x₀ = the previous observed solution (NOT_APPLICABLE when
      there is no warm start)
    - observed iterations = the sweep's count
    - all points converged
  - Grids above 500 points are refused before solving (`INVALID_LIMIT`),
    so a point is never dropped.
- **`engineering.transient-detail`**:
  - "Método de integración: …": BE / TR / BDF2 as exposed, order, LTE
    constant, adaptive or fixed, step bounds, tolerances.
  - Initial state x(0) with (v_C, i_C) / (i_L, v_L).
  - Every attempt, in order:
    - "Paso k" for each accepted step: t_n, Δt, t_(n+1), methods used
      (BE startup inside TR/BDF2), Newton α and ‖F‖ per iteration,
      x_n, predictor, x_(n+1), LTE per dynamic state, committed dynamic
      states, E_max, decision, next Δt.
    - "Intento rechazado …" (DECISION) for each rejection.
    - "Intento fallido …" for the stopping attempt.
  - CHECKs (SYMBOLIC):
    - observed t_(n+1) = `result.times`
    - observed states = trajectories
    - continuity
    - rejections = `stats.rejected`
    - Newton iterations = `stats.newton_total`
    - accepted ⇒ E ≤ 1 and LTE-rejected ⇒ E > 1 (adaptive mode only)
    - strictly increasing times with t_final = tstop
  - When the engine stops before integrating: "integration method
    details unavailable".
  - The derivative is not a separate engine quantity. What exists, and
    is shown, is the capacitor current i_C, which the integrator stores
    as C·dv/dt.
- **`engineering.ac-sweep`**:
  - Per frequency: f, status, Re/Im H, |H| and ∠H (the engine's
    `TransferFunction.magnitude/phase`).
  - WARNING "internal iteration details unavailable": each point is a
    direct solve.
  - CHECKs:
    - frequency sequence (SYMBOLIC)
    - |H|² = Re² + Im² (NUMERIC)
    - all points solved (SYMBOLIC)
- **`control.tf-analysis`**:
  - Steps: coefficients; gain, zeros and poles from `tf_to_zpk` (or the
    WARNING "Polos y ceros no disponibles" with the engine's reason);
    H(jω) polynomial; H(jω) ZPK; |H| and ∠H.
  - CHECKs (NUMERIC): |H|², and polynomial = ZPK form ≤ 1e-20 (the roots
    are iterative).
- **`engineering.nonlinear-dc` with BJTs** (F8-I):
  - `.param Q1 polarity=NPN|PNP …` is accepted. This is the only text
    parameter: any other value, or any other non-quantity, is still
    refused.
  - "Modelo de Ebers-Moll: Q1 (NPN|PNP)" gives the exact equations of
    `mna/bjt.py` for that polarity and the BJTParams values (α_F, α_R
    from the engine).
  - Per iteration, "Evaluación de Ebers-Moll: Q1 (iteración k)":
    - at x_k: V_BE/V_BC (NPN) or V_EB/V_CB (PNP), g_F, g_R, and J.C.C …
      J.E.E (the real block)
    - at x_(k+1): V_C, V_B, V_E, V_F, V_R, I_F, I_R, I_C, I_B, I_E
  - CHECK I_C + I_B + I_E = 0 per BJT (NUMERIC). The E0.2 Newton trace
    and its J·Δx + F = 0 check are reused.
- **`lab.run-detail`** (`explain_lab_run_detail(session, run_id)`):
  - Rebuilds the run's working circuit (`working_circuit`) and re-executes
    the same engine with the observer: OP → F8-H events; DC_SWEEP →
    sweep detail; AC_POINT → small-signal AC detail; TRANSIENT →
    transient detail.
  - CHECK "mismo resultado que el run" (SYMBOLIC): the engine digest, or
    the times, states and statistics for TRANSIENT, or status, voltages
    and the solver digest for OP.
  - AC_SWEEP is explained from the recorded sweep.
  - PARAM_SWEEP, CORNERS, SENS_* and MONTE_CARLO are UNSUPPORTED
    (declared WARNING + ERROR).
  - Replay stays the lab's (`LabService.replay`, result digest,
    EQUIVALENT); explanation replay of `lab.run-detail` is refused like
    `lab.run`.

## 4. Application / UI

- **`ExplainService.detail_trace(kind, …)`** has a fixed registry: ac-mna,
  ac-sweep, dc-sweep-detail, transient-detail, tf-analysis and bjt-dc
  (F8-I through the F8-H trace). There is no dynamic import.
  - Views: `explain_detail`, `lab_run_detail_trace` and
    `explain_lab_run_detail`.
  - Replay covers the five new text operations.
- **Registry coverage:** F8-H (`nonlinear_trace`), linear MNA / AC / DC
  sweep / transient / TF (E0.2 `analog_trace`), and the E0.3
  `detail_trace`.
- **Virtual Lab:** «Explicar último» (E0.2) is unchanged. The new button
  «Explicar en detalle» follows the chain UI → AcademicApp.explain →
  domain → certified engine with observer → renderer.
- **Renderer:** `LESSON_OPERATIONS` gains the six new operations.

## 5. Limits (TRACE_TRUNCATED)

| Item | Limit | Above the limit |
|---|---|---|
| A(jω) entry by entry | 8×8 (`MAX_MATRIX_FULL`) | `matrix_detail = OMITTED` + size, non-zero count, SHA-256 |
| b(jω) entry by entry | 64 | OMITTED + digest |
| x, \|x\|, ∠x per unknown | 32 | (the result CHECKs still use every entry) |
| DC sweep points | 500 (`MAX_DETAIL_POINTS`) | refused before solving (`INVALID_LIMIT`): all points are always kept |
| AC sweep frequencies | 500, and one INPUT of ≤ 512 characters | `INVALID_LIMIT` / `TRACE_LIMIT` |
| Optional detail events (sweep iterations, transient attempts) | 4000 events (`MAX_DETAIL_EVENTS`) | one WARNING `TRACE_TRUNCATED` with `omitted_events`, `event_limit`, `byte_limit`, deterministic |
| Serialized bytes | 5 MB, a conservative estimate that mandatory point events are charged to first (`MAX_DETAIL_BYTES`); the codec itself refuses anything above 8 MiB | same `TRACE_TRUNCATED` |
| Transient state per event | 6 unknowns, 4 LTE rows, 4 dynamic states | not listed (the CHECKs cover all of them) |

## 6. Non-observable (declared, not invented)

| ENGINE | CAPABILITY | STATUS | MISSING OBSERVATION | WHY | SAFE FUTURE EXTENSION |
|---|---|---|---|---|---|
| F8-L transient | Newton inside a step | PARTIAL | J(x_k), Δx, x_k per iteration inside a step (α and ‖F‖ are observed) | the transient observer reports the iteration log, not the linear systems | pass a Newton-style observer to the step's inner loop (as in F8-H) |
| F8-L transient | aborts other than LTE / Newton / singular Jacobian (non-finite companion coefficients, non-finite initial residual in fixed mode or below h_min, non-finite LTE below h_min, step budget) | PARTIAL | the stopping attempt | these sites return before an attempt event; the ERROR carries the engine diagnostic | the same `retry_h = None` call at those sites |
| F8-D5 AC sweep | per-point A(jω) inside the sweep | PARTIAL | the matrix of each frequency within the sweep trace | `frequency_response` has no observer; each point is available through `engineering.ac-mna` | pass the AC observer through `frequency_response` |
| F8-J small-signal | DC bias Newton inside AC_POINT | PARTIAL | the bias iterations inside the AC trace | a separate F8-H solve; traced with OP | chain the F8-H observer into `solve_small_signal_ac` |
| F8-H | MOSFET / JFET / diode-variant evaluation | PARTIAL | per-device currents / conductances | only Shockley diodes (E0.2) and BJTs (E0.3) are logged | the same `trace` list pattern in `mosfet.py` / `jfet.py` / variants |
| F8-H text form | MOSFET/JFET string parameters | NOT TRACEABLE AS TEXT | `.param` text for non-quantity parameters other than BJT polarity | the text form carries quantities + `polarity` only | typed text for each closed enumeration |
| Virtual Lab | PARAM_SWEEP, CORNERS, SENS_DC, SENS_AC, MONTE_CARLO detail | UNSUPPORTED | engine internals of these analyses | results are summaries (sweep of sweeps, statistics) | per-kind observers |
| F8-P TF | symbolic derivation of poles/zeros | NOT APPLICABLE | none (roots are numeric Durand–Kerner, shown as such) | the engine computes roots numerically | — |

## 7. Observer contract, determinism, security

- **Observer equivalence:**
  - `observer=None` versus a recording observer, on AC, small-signal
    AC, DC sweep (warm and cold), transient (linear and nonlinear,
    adaptive with rejections) and BJT (NPN, PNP and INVALID).
  - Results, diagnostics, statuses, iteration counts, statistics and
    digests are identical.
  - Excluded: only the certified wall-clock `timestamp` of the linear-DC
    provenance inside `SmallSignalACResult.dc_operating_point`, which
    differs between two plain calls too.
- **Determinism:** the digests of 8 new traces are identical across
  `PYTHONHASHSEED` = 0 / 11 / 2024 / random in separate processes. The
  truncated trace is deterministic.
- **Security:**
  - AST checks on `analog_detail.py` and `newton.py`: no eval, exec,
    compile, `__import__`, open, pickle, marshal, importlib or
    subprocess, and no os or sys.
  - Modified engines never import `domain.execution` or build a trace.
  - No `float(` in `nonlinear.py` or `bjt.py`.
  - Inputs are text, bounded and validated: the netlist limits, the
    frequency list, the engine name, bool flags, and `polarity` only
    NPN/PNP.
- **Schema:** `execution-trace/1` is unchanged (canonical JSON, digest,
  strict decode, replay, first difference).
