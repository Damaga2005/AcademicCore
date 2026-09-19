# GATE-F8M: Certification Report — Advanced Analysis (Sweeps, Worst Case, Sensitivity, Monte Carlo)

Baseline: `f9b9a6e` (design gate `GATE-F8M-DESIGN.md` = `F8-M DESIGN READY`; origin/main `73232f9`).

## 1. Scope

Implemented exactly M1 DC sweep, M2 parameter sweep, M3 worst-case corners, M4 DC sensitivity,
M4-AC (linear elements), M5 native Monte Carlo (DC-op base). Nothing marked OUT OF SCOPE in the
design gate was implemented (no continuation/homotopy, pseudo-arclength, bifurcation, noise,
transient sensitivity, transient-base sweep/MC, AC device-parameter sensitivity, poles/zeros,
transmission lines, GUM, non-numeric sweepables, no F8-N).

## 2. Implementation

| File | Role |
|:---|:---|
| `mna/analysis.py` (new) | `ParamAddress` + closed `PARAM_REGISTRY`, `ObservableSpec`, grids, shared point driver (warm start + recorded fallback), M1/M2/M3/M5, native statistics, provenance/digests |
| `mna/sensitivity.py` (new) | M4 (`dx/dp = -J^-1 dF/dp`, analytic dF/dp tables), M4-AC (`dX/dp = A^-1(db/dp - dA/dp X)`), chain rules |
| `mna/nonlinear.py` (additive) | R-02 `x_init`; R-01 `NewtonState` + `solve_nonlinear_dc_state` |

## 3. API

`solve_dc_sweep(circuit, SweepConfig)`, `solve_param_sweep(circuit, ParamSweepConfig)`,
`solve_worst_case(circuit, WorstCaseConfig)`, `solve_dc_sensitivity(circuit, SensitivityConfig)`,
`solve_ac_sensitivity(circuit, ACSensitivityConfig)`, `run_monte_carlo_native(circuit, MCConfig)`.
Frozen dataclasses, Decimal-native, status enums (`SweepStatus`, `WorstCaseStatus`, `MCStatus`,
`SensitivityStatus`); config errors are in-band `INVALID`/`UNSUPPORTED`; inputs never mutated.
Budgets are rejections (`INVALID`), never truncation: `MAX_SWEEP_POINTS=2000`,
`MAX_MC_ITERATIONS=10000`, `MAX_WORST_PARAMS=10`.

## 4. Algorithms / mathematics

* Every point is a native DC solve of the DC equivalent (C removed, L -> 0 V short, F8-J precedent)
  through the certified damped Newton (Q1 tolerances unchanged). Linear circuits use the same path.
* Warm start (R-02): point k starts from k-1 only if it converged; a failed warm attempt is
  re-solved from zero and recorded (`init_mode`, `warm_start_used`, `fallback_used`, status,
  Newton digest). A failed predecessor forces a cold start (`cold-after-failure`).
* Grids: linear `n=floor((stop-start)/step)+1`, stop appended iff within half a step; log with exact
  endpoints; list order preserved. Direction/sign/domain errors -> `INVALID`.
* M3: all 2^k corners, sorted-address order, low before high; per-observable min/max, arg-corner,
  first-wins ties (all tied indices listed). Result states "corner extremum ... NOT a proven global
  optimum".
* M4: `J(x*) s = -dF/dp` with the certified `J`; closed-form `dF/dp` for R/V/I/E/G/H/F/T (incl.
  control-target chain), diode kinds (Shockley/LED/Schottky/Zener/photo), Ebers-Moll BJT (NPN/PNP),
  MOSFET L1 (Kp, Vto, Lambda, Gamma, Phi), JFET (Idss, Vp, Lambda). Branch-consistent: the branch
  the certified model selects (MOS cutoff `Vov<=0`, triode `VDS<Vov`; JFET analogous; Zener forward
  at `Vd>=0`); no smoothing. Singular `J` -> `SINGULAR_JACOBIAN` (no pseudo-inverse). Observables:
  node voltage, aux current, resistor current/power, device terminal current (chain rule);
  normalized `(p/o)(do/dp)` (`o=0` -> `null`); dimensions via `dim_sub`.
* M4-AC: F8-D3 HP complex system; `dA/dp`, `db/dp` analytic for R/L/C/E/G/H/F/T; `d|H|`, `dphi`
  (rad, deg), `dB` chain rules (guard `|H|=0` -> `null`).
* M5: master `Random(seed)` (seed required, int >= 0) -> 64-bit sub-seeds per (iteration, sorted
  address); `getrandbits(53)/2^53` exact Decimal fractions; uniform; normal via Decimal Box-Muller
  (`ln`, `sqrt`, `decimal_cos`); cold solve per iteration; failures recorded (count, indices,
  statuses); native Decimal statistics (mean, sample variance, std, min, max, p5/25/50/75/95).

## 5. Validation

* Closed forms: divider sweep/sensitivity/corners, RC low-pass `d|H|/dR`, `dphi/dC`, `dB/dR`
  (rel. err < 1E-40), gain closed forms, DC equivalent of RLC.
* Finite-difference oracle (tests only): `h=max(1E-6|p|,1E-12)`, match < 1E-4 relative, for D/LED/
  Zener/photo/NPN/PNP (active + saturation)/NMOS (sat, triode, body)/PMOS/JFET/E/G/H/F/T,
  control-target chain, and AC R/L/C/E/G/H/F/T. Every case passes.
* ngspice 47: DC-sweep trace (diode) and corner `.op` spots (divider 1E-6 rel., diode Is corners
  2E-3 rel.). External validation only.

## 6. Tests

`tests/test_f8m_analysis.py`: **87 tests, 87 passed, 0 failed, 0 skipped**, covering M-001..M-060
(each id has a `test_mNNN` function) plus adversarial extras (`m060b`, `m060c`).

## 7. Regression

* F8-H (69), F8-I (74), F8-J (29), F8-K (110), F8-L (58): all green after R-01/R-02.
* Global run: **2120 tests, 0 failures, 2 skips** (pre-existing F7 ngspice-on-PATH skips,
  unchanged). No unexpected failures.

## 8. Precision / security / determinism

* `float(` in new code: 0 (grep + AST incl. float literals); 0 in all of `mna/` and
  `ac/small_signal.py`. Pre-existing `float(` only in `gum.py`, `simulation.py`, `ac/impedance.py`
  (untouched, outside F8-M). No numpy/scipy/math; bare `abs()` / ambient-context use banned by an
  AST test.
* 0 `eval/exec/compile/__import__/getattr/globals/locals`, 0 subprocess/os/sys/socket/importlib,
  no network, no deserialization.
* Determinism: 3 identical runs (M1, M2, M3, M4, M4-AC, M5) give identical digests/serialization;
  insertion-order invariance; digests contain no wall-clock data.

## 9. Benchmarks (diagnostic only, no timing assertion)

M1: 19 points, 88 Newton iterations, 0 fallbacks, 0 failures (~0.16 s). M5: 50 iterations, 0
failures (~0.16 s). M4: 3 linear solves (~0.05 s). M4-AC: 2 linear solves. M3 k=10: 1024 corners
(~4 s, 3-unknown circuit).

## 10. Deviations (all documented)

* **DEV-01** R-01 realised as `NewtonState` exposure of the certified `_NewtonSystem`
  (`residual`/`jacobian`) instead of extracting free functions: same effect, zero change to
  certified paths.
* **DEV-02** Module split `analysis.py` + `sensitivity.py` (design named one module).
* **DEV-03** FD oracle: when `p-h` would leave the domain (Is ~ 1E-14) the purely relative step
  `1E-6|p|` is used; tolerance unchanged (1E-4). An absolute floor `1E-9|o/p|` guards only
  exactly-zero derivatives.
* **DEV-04** M-053..M-056 are R-01/R-02 contract tests (default-path bit identity, `x_init`
  validation, warm start from a solution, state only when converged); the F8-H..L suites were run
  in full separately (section 7).
* **DEV-05** M3 with `k=0` -> `INVALID` (no range). M2 corners = named subset (`all-low`,
  `all-high`, one-at-a-time per address). Normal-distribution `[min,max]` are validity bounds:
  outside samples are recorded FAILED (`invalid_sample`), never clamped or resampled.
* **DEV-06** One HP linear solve per parameter (no factorisation reuse; the API has none). C/L
  `value` addresses exist only for M4-AC (DC engines reject them: no DC effect).
* **DEV-07** `Phi=0` with `Gamma>0`: `dVth/dPhi` unbounded -> honest `UNSUPPORTED`.
* **DEV-08** M4-AC/M4 dependent-source derivatives support arbitrary control chains through
  R/L/C/G/I/V/E/H/O/F (validated by FD for direct control targets).

## 11. Limitations

Corner extremum is not a global optimum; no continuation/homotopy; no pseudo-arclength; no
bifurcation; no transient-base sweep/MC; no AC device-parameter sensitivity; warm start follows
branches (hysteresis) — recorded per point, not detected; MC is sequential.

## 12. Certification checklist

All items of the F8-M certification gate pass: M1-M5/M4-AC implemented, contracts preserved,
Decimal-native, float/forbidden-dependency/security scans clean, M-001..M-060 pass,
analytical/FD/ngspice validation pass, determinism and provenance deterministic, warm-start/fallback
transparent, corner honesty and MC failure recording verified, F8-H/I/J/K/L and global regression
pass, no undocumented deviations, no scope creep, no normative timing, documentation complete,
roadmap updated.

## Final Verdict

`F8-M CERTIFIED`
