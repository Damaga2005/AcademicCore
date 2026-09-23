# GATE E0.2 — Explainable Engineering Expansion (analog) — FINAL

Design: [GATE-E0.2-DESIGN.md](GATE-E0.2-DESIGN.md).

```text
E0.2 FINAL REPORT
```

## Baseline

- **Start:** `453014a` (E0.1-R+ certified), with `HEAD == origin/main`
  and a clean tree.
- **Implementation:** `28d8182` `feat: extend explainable execution to
  analog engineering`.
- **Certification:** this commit.

## F8-H

- **Status:** CERTIFIED + OBSERVABLE. The optional observer was extended,
  and it is inert when `None`.
- **Trace:**
  - "Modelo de Shockley" per diode, with the solver's own DiodeParams (Is,
    n, Vt) and `I = Is·(exp(Vd/(n·Vt)) − 1)`.
  - x₀.
  - Per iteration: x_k, F(x_k), the real J(x_k), Δx, α, x_(k+1), ‖F‖ by
    blocks, ‖αΔx‖∞, res_ok and step_ok.
  - The Shockley evaluations the solver computed: g at x_k, I at
    x_(k+1).
  - Every real backtracking trial: α, trial residual, the residual to
    beat, accepted/rejected.
  - "Iteración k fallida" for in-loop failures.
  - Per-node KCL residual rows, without an invented element split.
  - Other nonlinear devices are declared "detalle no expuesto".
- **Iterations:**
  - The count equals `provenance["iterations"]`.
  - Trial events = Σ(halvings + 1) over iterations with backtracking.
  - α halves from 1, and only the last trial is accepted.
  - DIVERGED shows its 11 real rejected halvings.
  - SINGULAR_JACOBIAN and INVALID are ERRORs, never success.
- **Verification:**
  - conservation (NUMERIC)
  - iteration count (SYMBOLIC)
  - continuity (SYMBOLIC)
  - **J·Δx + F = 0 on the observed data (NUMERIC, ~1e-50)**
  - Tests recompute I and g with the engine's own Shockley functions from
    the recorded Vd: identical.

## Linear MNA

- **Status:** CERTIFIED + OBSERVABLE. New optional observer on
  `solve_linear_dc`, plus `unknown_labels(problem)`.
- **Observability:**
  - The real A and b (Fraction) are identical to `build_mna_problem`.
  - Unknown labels come from the certified index maps.
  - Gauss–Jordan status and rank, and the exact x.
  - KCL rows are exactly the observed nonzero matrix entries, with
    residual 0.
  - Exact A·x = b (SYMBOLIC).
- **"detalle omitido"** above 6×6.
- **Statuses:**
  - INCONSISTENT, SINGULAR, INVALID and UNSUPPORTED are ERRORs.
  - A diode gives UNSUPPORTED plus "MNA matrix unavailable". The matrix
    is never reconstructed.

## AC

- **Status:** CERTIFIED + PARTIALLY OBSERVABLE, traced at result level.
- **Traced:** f, ω, phasors, and |V| / ∠V via `phasors.magnitude/phase`.
  Tests check they are identical to the engine's.
- **Checks:** the solver's KCL/KVL residuals.
- **Declared:** "MNA matrix unavailable".

## DC sweep

- **Status:** CERTIFIED + PARTIALLY OBSERVABLE, traced at result level.
- **Traced per point:** status, iterations, init mode, voltages and
  observables, identical to `solve_dc_sweep`.
- **Declared:** the per-point Newton internals are not exposed.

## Transient

- **Status:** CERTIFIED + PARTIALLY OBSERVABLE, traced at result level.
- **Traced:** committed times and states, identical to
  `solve_transient`, and the aggregate statistics.
- **Declared:** per-step internals are aggregates only.
- **Errors:** TIMESTEP_TOO_SMALL is reported as an ERROR.

## TransferFunction

- **Status:** CERTIFIED + OBSERVABLE.
- **Traced:** `evaluate(jω)` → Re/Im, `modulus()`, and the engine phase
  in degrees.
- **Check:** |H|² = Re² + Im² (NUMERIC).

## F15

- **Status:** Integrated.
  - Fixed `ExplainService` registry: `analog_trace` / `explain_analog`
    and replay of linear-dc, dc-sweep, ac, transient and tf-point.
  - `explain_lab_run`.
  - Virtual Lab «Explicar último».
- **Virtual Lab kinds:**
  - OP, DC_SWEEP, TRANSIENT and AC_POINT are explained in detail.
  - AC_SWEEP (and PARAM_SWEEP, CORNERS, SENS_*, MONTE_CARLO) are
    declared UNSUPPORTED for detail.
- **Replay:**
  - The lab replays its own runs (EQUIVALENT by result digest), and the
    explanation is identical when rebuilt.
  - Explanation replay of `lab.run` is refused with UNSUPPORTED_OPERATION.
- **Contracts:** UI → AcademicApp → Service → Domain → Engine →
  ExecutionTrace → Renderer, with no domain→UI or domain→application
  edge (AST test).

## Anti-fake-step

Tests `e02_a01` to `e02_a04`:

- No Jacobian above the display bound ("detalle omitido"), and no A/J
  values in AC or transient traces.
- No conversion step in analog traces.
- No auxiliary current when no voltage-type element exists (a current
  source adds none).
- No invented iteration: counts equal the engine's.
- No backtracking beyond the solver's own trials.
- No KCL decomposition in F8-H. Linear KCL terms are the observed row.
- BJT internals are declared, not invented.

## Observer compatibility

- **Identical with and without observer:**
  - F8-H: 4 circuits, including DIVERGED and SINGULAR. Result,
    diagnostics and status are identical.
  - Linear DC: 3 circuits. The comparison excludes the certified
    wall-clock timestamp in provenance.
- **Immutable:** every observed value is an immutable snapshot.
- **E0.1-R+ hardening:** 25/25 still pass.

## Determinism

The digests of 6 new traces (F8-H, linear DC, AC, DC sweep, TF, transient)
are identical across `PYTHONHASHSEED` = 0 / 11 / 2024 / random in separate
processes.

## Security

- **AST:** the new modules have no eval, exec, compile, open, pickle,
  marshal, importlib, subprocess, os or sys.
- **Engines:** no `float(` in the modified engine files.
- **Inputs** are bounded (F8-H netlist limits), typed and validated.

## E0

71/71. The golden fixture is unchanged.

## E0.1

113/113.

## E0.1-R+

- 74/74 (25 hardening + 49 limitations).
- Compatibility was preserved:
  - Backtracking events are titled "Backtracking (iteración k)", so
    iteration counts are unchanged.
  - Node columns keep their plain names in F8-H value names.

## New tests

`tests/test_e02_explainable_analog.py`: 31.

## Full suite

- **passed:** 3306
- **failed:** 0
- **skipped:** 134 (environment-only)
- **time:** 21 min 30 s, on the committed implementation `28d8182`

## Commit

- Implementation: `28d8182`
- Certification: this commit

## origin/main

`HEAD == origin/main`, verified after the push.

## Tree

clean

## Final verdict

```text
E0.2 COMPLETE / CERTIFIED
```
