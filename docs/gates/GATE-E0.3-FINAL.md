# GATE E0.3 — Explainable Engineering Completeness — FINAL

Design: [GATE-E0.3-DESIGN.md](GATE-E0.3-DESIGN.md).

```text
E0.3 FINAL REPORT
```

## Baseline

- **Start:** `69143fb` (E0.2 certified), with `HEAD == origin/main` and a
  clean tree.
- **Implementation:** `5c141c0` `feat: complete explainable engineering
  analysis`.
- **Certification:** this commit.

## AC

- **Status:** CERTIFIED + FULLY OBSERVABLE, for F8-D3 `solve_ac` and for
  F8-J `solve_small_signal_ac` (Virtual Lab AC_POINT).
- **Matrix:**
  - A(jω) is exactly the matrix handed to the complex solver. The test
    shows it is identical to `build_ac_problem(...).matrix`.
  - It is shown FULL up to 8×8. Above that it is OMITTED, with size,
    non-zero count and SHA-256; the ladder test uses 9 unknowns.
- **RHS:** b(jω) exactly as observed.
- **Solution:** x(jω) from the solver's outcome. Status, mode, rank,
  residual norm and backward error are shown. |x| and ∠x come from
  `phasors.magnitude/phase`.
- **Verification:**
  - A·x = b: SYMBOLIC in exact mode, NUMERIC otherwise (≤ 1e-30,
    observed about 1e-54).
  - |x|² = Re² + Im²: NUMERIC.
  - Observed x = published phasors: SYMBOLIC.
  - Engine KCL/KVL: NUMERIC.
- **Engine refusal:** "MNA matrix unavailable" plus the engine's status.
  Nothing is reconstructed.

## DC_SWEEP

- **Status:** CERTIFIED + FULLY OBSERVABLE.
- **Points:** all points are kept. Grids above 500 points are refused
  before solving, so no point is ever dropped.
- **Iterations:** the real Newton iterations of every point (α, halvings,
  ‖αΔx‖∞, ‖F‖, res_ok, step_ok, V). The count equals the sweep's count.
- **Warm/cold:**
  - Warm x₀ is the exact vector the driver handed over, and equals the
    previous observed solution (SYMBOLIC check).
  - Cold starts are stated.
  - With `warm_start=False` every point is cold, and the warm-start check
    is NOT_APPLICABLE.

## TRANSIENT

- **Status:** CERTIFIED + OBSERVABLE per step.
- **Steps:** each accepted step shows t_n, Δt, t_(n+1), x_n, the
  predictor, x_(n+1), Newton α and ‖F‖ per iteration, the LTE per dynamic
  state, the committed (v_C, i_C) / (i_L, v_L), E_max and the next Δt.
- **Attempts:** rejected attempts, and the attempt that stops the
  integrator, are shown.
- **Checks:** t, states, rejections and Newton iterations each equal the
  engine's.
- **Method:** BE, TR or BDF2 as exposed by the engine, with its order and
  LTE constant. BE startup inside BDF2 is shown per step and equals
  `be_startup_steps`.
- **Adaptive:** every real decision is shown.
  - Accepted steps have E ≤ 1.
  - LTE rejections have E > 1 and a smaller retry Δt.
  - Fixed-step mode has no controller: "next_dt" is "-" and the decision
    check is NOT_APPLICABLE.
- **Derivative:** not a separate engine quantity, so only the stored
  capacitor current is shown.

## AC_SWEEP

- **Status:** CERTIFIED + OBSERVABLE at point level. It is integrated in
  the Virtual Lab and as `engineering.ac-sweep`.
- **Points:** per frequency, f, status, H, |H| and ∠H, as the engine
  reports them.
- **Declared:** "internal iteration details unavailable". Each point is a
  direct solve with no iterations.

## TransferFunction

- **Status:** the E0.2 `control.tf-point` is unchanged.
- **New:** `control.tf-analysis` adds the engine's `tf_to_zpk` (gain,
  zeros, poles) and `ZPK.evaluate`.
- **Checks (NUMERIC):** polynomial form = ZPK form, and |H|² = Re² + Im².
- **Unavailable ZPK:** declared, e.g. for a zero transfer.

## BJT/F8-I

- **Status:** F8-I is IMPLEMENTED and CERTIFIED, so it is integrated and
  CERTIFIED + FULLY OBSERVABLE.
- **Text form:** `polarity=NPN|PNP` is accepted as text; any other value
  is INVALID_INPUT.
- **NPN:**
  - The trace shows V_BE and V_BC.
  - I_C, I_B and I_E are identical to `bjt_terminal_currents`.
  - The 3×3 block is identical to `bjt_jacobian`.
  - In the active region I_C > 0 and I_E < 0.
  - I_C + I_B + I_E = 0 passes (NUMERIC).
- **PNP:**
  - The trace shows V_EB and V_CB, with the exact PNP equations.
  - In the active region I_C < 0 and I_E > 0.
  - The same identities hold.
- **Newton:** the F8-H observer and trace are reused, including
  J·Δx + F = 0.
- **Errors:** a missing parameter gives the engine's INVALID and no
  Ebers-Moll event.

## F15

- **Status:** Integrated.
  - Fixed registry `detail_trace`: ac-mna, ac-sweep, dc-sweep-detail,
    transient-detail, tf-analysis and bjt-dc.
  - New Virtual Lab button «Explicar en detalle».
- **Explain:** OP, DC_SWEEP, TRANSIENT, AC_POINT and AC_SWEEP give
  SUCCESS/PASS.
  - The run is re-observed on its own working circuit.
  - CHECK "mismo resultado que el run" passes (SYMBOLIC).
  - PARAM_SWEEP is declared UNSUPPORTED.
- **Replay:**
  - The five new text operations replay EQUIVALENT.
  - `lab.run-detail`, like `lab.run`, is refused for explanation replay;
    the lab replays its own runs.
- **EQUIVALENT:** `LabService.replay` gives EQUIVALENT after every run.
  «Explicar último» (E0.2) is unchanged.

## Anti-fake-step

Tests `e03_a01` to `e03_a04`:

- No A/J values in the AC, transient or AC-sweep traces unless observed,
  and none when the engine refuses.
- Equations list only the observed non-zero coefficients.
- Iteration events equal the engine's counts.
- No derivative value names, and the method is the engine's alone.
- Rejection events equal `stats.rejected`, with none in fixed-step mode.
- No warm start when it is disabled; the first point is always cold.
- No BJT current in diode or linear traces, nor in a failed BJT.

## Observer compatibility

- **Identical with and without observer:** results, diagnostics,
  statuses, iteration counts, statistics and digests for:
  - AC and small-signal AC
  - DC sweep, warm and cold
  - transient: linear and nonlinear, adaptive with rejections
  - BJT: NPN, PNP and INVALID
- **Excluded:** only the certified wall-clock `timestamp` of the linear
  DC provenance inside small-signal AC. It differs between two plain
  calls too.
- **Immutable:** every observed value is an immutable snapshot.
- **Performance:**

  | Engine | No observer | Recording observer |
  |---|---|---|
  | AC | 0.8 ms | 1.0 ms |
  | DC sweep | 31 ms | 39 ms |
  | transient | 87 ms | 103 ms |

- **`observer=None`** builds nothing: engines never import
  `domain.execution` (AST test).

## Boundedness

- Matrix detail is FULL up to 8×8, else OMITTED with a digest.
- Sweep points are limited to 500 and are refused above that.
- Optional detail is capped at 4000 events and 5 MB (estimated,
  conservative).
- When the cap is reached, the trace carries a deterministic WARNING
  `TRACE_TRUNCATED` with the omitted count.
  - Example: 3051 transient attempts produce a 3.75 MB trace, below the
    8 MiB codec limit.
  - The CHECKs still cover the whole run.

## Determinism

The digests of 8 new traces are identical across `PYTHONHASHSEED` =
0 / 11 / 2024 / random, in separate processes.

## Security

- **Execution modules:** no eval, exec, compile, `__import__`, open,
  getattr, setattr, pickle, marshal, importlib or subprocess, and no os
  or sys.
- **Modified engines:** no eval, exec, compile or `__import__`, and no
  `domain.execution` import.
- **`float(`:** absent from `nonlinear.py` and `bjt.py`.
- **Inputs:** text, bounded and validated.

## E0

71/71. The golden fixture is unchanged, and `test_e0_x01` covers the
new module.

## E0.1

113/113.

## E0.1-R+

74/74.

## E0.2

31/31. Its traces are unchanged.

## New tests

`tests/test_e03_explainable_engineering.py`: 39.

## Full suite

- **passed:** 3345
- **failed:** 0
- **skipped:** 134 (environment-only)
- **time:** 23 min 19 s, on the committed implementation `5c141c0`

## Commits

- Implementation: `5c141c0`
- Certification: this commit

## origin/main

`HEAD == origin/main`, verified after the push.

## Tree

clean

## Final verdict

```text
E0.3 COMPLETE / CERTIFIED
```
