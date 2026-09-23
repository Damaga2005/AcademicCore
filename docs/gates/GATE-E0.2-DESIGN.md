# GATE E0.2 — Explainable Engineering Expansion (analog) — DESIGN

Baseline: `453014a` (E0.1-R+ certified). `HEAD == origin/main`, clean tree.

Principle: REAL ENGINE EXECUTION → REAL OBSERVATIONS → ExecutionTrace →
PEDAGOGICAL STEPS → VERIFICATION. There is never a second solver.

## 1. Audit and classification

| Engine | Module | Classification | Observed data |
|---|---|---|---|
| F8-H nonlinear DC (Shockley) | `mna/nonlinear.py` | CERTIFIED + OBSERVABLE (optional observer, extended in E0.2) | x_k, F(x_k), J(x_k), Δx, α, x_(k+1), block norms, res_ok / step_ok, every backtracking trial, Shockley (Vd, I) and (Vd, g) of each diode, DiodeParams (Is, n, Vt), in-loop failures |
| F8-H other devices (diode variants, BJT, MOSFET, JFET) | same | CERTIFIED + PARTIALLY OBSERVABLE | They take part through F and J only; their internal evaluation is **declared unavailable**. |
| Linear MNA / DC | `mna/solver.py` | CERTIFIED + OBSERVABLE (new optional observer) | Unknown labels (`problem.unknown_labels`, read from the certified index maps), exact A and b (Fraction), Gauss–Jordan status, rank and x |
| AC (sinusoidal steady state) | `ac/solver.py solve_ac` | CERTIFIED + PARTIALLY OBSERVABLE (result level) | f, ω, complex node phasors, branch currents, KCL/KVL residuals; `phasors.magnitude/phase`. The complex matrix is **unavailable**. |
| DC sweep | `mna/analysis.py solve_dc_sweep` | CERTIFIED + PARTIALLY OBSERVABLE (result level) | Per point: parameter, status, iteration count, init mode, warm start / fallback, voltages, observables. The per-iteration detail of each point is **unavailable**. |
| Transient | `mna/transient.py solve_transient` | CERTIFIED + PARTIALLY OBSERVABLE (result level) | Committed times, node trajectories, inductor currents and aggregate statistics. Per-step Newton, LTE and rejected steps are **aggregates only**. |
| Transfer function | `control/tf.py` | CERTIFIED + OBSERVABLE | `evaluate(jω)` (Re, Im), `modulus()`, `margins._wrapped_phase_deg` |
| F15 / Virtual Lab | `lab/run.py`, `LabService` | CERTIFIED + OBSERVABLE (Run wraps the engine result unchanged) | Status, engine status, readings, measurements, and the engine result for OP / DC_SWEEP / AC_POINT / TRANSIENT. PARAM_SWEEP, CORNERS, SENS_*, MONTE_CARLO and AC_SWEEP have their detailed explanation **UNSUPPORTED** (declared). |

## 2. Engine changes (optional, read-only observation)

**F8-H (`nonlinear.py`).**

- `_NewtonSystem.device_log` and `jac_log` are `None` by default, which
  makes them inert. They are set to lists only when an observer is
  attached. They record `(ref, Vd, I)` in `residual()` and
  `(ref, Vd, g)` in `jacobian()`, and never change a value.
- `newton_iteration` also receives `trials`, `reference`, `devices` and
  `device_conductances`.
- `newton_start` also receives `devices` and `diode_parameters`.
- New call `newton_failed(it, reason, trials)` before in-loop failure
  returns.
- Unknown labels now come from `unknown_labels(problem)`. This fixes an
  E0.1-R+ labelling error for transformer legs.

**Linear MNA (`solver.py`).** `solve_linear_dc(circuit,
observer=None)` gives the observer `mna_system(unknowns, A, b)` and
`linear_outcome(status, rank, x)`.

**Problem layout (`problem.py`).** New pure function
`unknown_labels(problem)`.

**What an observer receives.** Every value it receives is an immutable
snapshot (tuples of Decimal / Fraction / str / bool / int). With
`observer=None` the behaviour is byte-identical: tested on results,
diagnostics, provenance (minus the certified wall-clock timestamp),
statuses and errors.

## 3. Traces

- **`engineering.nonlinear-dc` (F8-H, extended):**
  - "Modelo de Shockley" per diode.
  - Real backtracking trials, shown when there was more than one trial.
    They are titled "Backtracking (iteración k)" so that E0.1 iteration
    counts are unchanged.
  - One "Evaluación de Shockley" per iteration.
  - "Iteración k fallida" for in-loop failures.
  - "KCL por nodo en la solución": the residual row only, with no
    invented element terms.
  - Checks, each labelled:
    - conservation (NUMERIC)
    - iteration count (SYMBOLIC)
    - continuity (SYMBOLIC)
    - **J·Δx + F = 0 on the observed data (NUMERIC)**
- **`engineering.linear-dc`:**
  - circuit and components (type, pins, value)
  - unknowns
  - A and b (up to 6×6, else "detalle omitido")
  - Gauss–Jordan status and rank
  - x
  - KCL rows as the observed matrix rows (terms A_ij·x_j)
  - checks: exact A·x = b (SYMBOLIC), result = x (NUMERIC), conservation
    (NUMERIC)
  - statuses SINGULAR / INCONSISTENT / INVALID / UNSUPPORTED reported as
    ERROR; "MNA matrix unavailable" when the solver refused before
    assembling
- **Result-level traces:**
  - `engineering.dc-sweep`
  - `engineering.ac`
  - `engineering.transient`
  - `control.tf-point`
  - `lab.run` (Virtual Lab)
- **Units:** the E0.1-R+ rule is untouched. No analog trace contains a
  conversion step, and the unit traces keep showing only executed
  conversions.

## 4. Application / UI

- **Registry:** `ExplainService` gains a fixed registry: `analog_trace`
  (linear-dc, dc-sweep, ac, transient, tf-point), `explain_lab_run`,
  and replay of the analog operations. `lab.run` is refused for replay:
  the Virtual Lab replays its own runs by result digest.
- **Virtual Lab:** a new «Explicar último» button. The chain is UI →
  AcademicApp.explain → domain → certified Run → renderer. No domain→UI
  or domain→application edge.
- **Renderer:** lessons for the new operations.

## 5. Non-observable capabilities (declared, not modified)

| Engine | Status | Missing data | Reason | Safe future extension |
|---|---|---|---|---|
| AC | PARTIAL | complex MNA matrix | `solve_ac` builds and solves internally; the result does not carry it | optional observer in `solve_ac_problem` |
| DC sweep | PARTIAL | Newton iterations per point | the sweep keeps counts, not snapshots | pass an observer through `solve_point` |
| Transient | PARTIAL | per-step Newton / LTE / rejections | the engine reports aggregates only | per-step observer in the integrator loop |
| F8-H devices other than Shockley | PARTIAL | per-device evaluation | only Shockley diodes are logged | extend the logs to variant / BJT / MOS / JFET evaluations |
| BJT/MOS/JFET netlists | NOT TRACEABLE AS TEXT | string parameters (e.g. polarity) | `.param` carries Quantities only | typed text form for string parameters |
| Virtual Lab non-OP kinds | UNSUPPORTED (explanation) | engine-specific internals | results are summaries (sweep of sweeps, statistics) | per-kind result mappers |
