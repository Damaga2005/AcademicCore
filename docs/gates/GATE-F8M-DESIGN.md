# GATE-F8M-DESIGN

## Baseline

- Repository: `Damaga2005/AcademicCore`, branch `main`.
- HEAD == origin/main == `73232f9`, working tree clean at audit time.
- Certified: F0–F7, F8-A → F8-L (gates on disk through `GATE-F8L.md`).
- Roadmap binding order (§5.1): F8-M = "Análisis Avanzados (Sweep,
  Sensibilidad, MC)" [4º], depending on F8-L; row 4: "DC Sweep, Parameter
  Sweep, sensibilidad, Monte Carlo, Worst Case"; §6.2: F8-M is NEXT.

## Git State

 main, `73232f9`, clean, in sync. No implementation in this phase
 (absolute rule); this document is the only permitted functional output
 (+ at most a strictly necessary doc touch-up and one local commit).

## Existing Certified Capabilities

- **F8-H**: Shockley diode DC op-point. `solve_nonlinear_dc`, damped
  Newton + strict-decrease bisection backtracking, frozen Q1
  (RTOL=1E-9, ATOL=1E-12, STOL=1E-12, MAX_ITER=50, MAX_BACKTRACK=10),
  zero-vector init, `NonlinearStatus` (CONVERGED / MAX_ITERATIONS /
  DIVERGED / SINGULAR_JACOBIAN / INVALID / UNSUPPORTED).
- **F8-I**: Ebers-Moll BJT (NPN/PNP), analytic 3×3 Jacobian, no new unknowns.
- **F8-J**: `solve_small_signal_ac` around frozen DC points; `DecimalComplex`
  HP linear solves (`ComplexLinearProblem`, `NumericMode.HIGH_PRECISION`);
  `ACStatus`; native frequency sweep already exists (`ac/response.py`
  `SweepPoint/SweepResult`, F8-D5) — F8-M must NOT duplicate it.
- **F8-K**: MOSFET L1 (`M`, 4×4), JFET (`J`, 3×3), diode kinds
  (`D`+`kind`); SOLVER-EXT-01 tolerance-level standstill acceptance.
- **F8-L**: `solve_transient` (BE/TR/BDF2, LTE adaptive, rollback);
  C↔open / L↔short DC-equivalent pattern; fixed-step verification mode.
- Numerics: `Decimal` prec-50 explicit contexts (`make_context()` fresh per
  call post-P1); `float(` count = 0 in `mna/` + `ac/small_signal.py`
  (verified by grep in this audit); no `eval/exec/__import__/subprocess`;
  `make_context`, `decimal_sin/cos/pi`, `Decimal.ln/exp` (context-explicit)
  available; `random.Random` (seeded) used only in `simulation.py` MC.
- Pre-existing neighbours (NOT to duplicate): `simulation.py`
  `DCSweepAnalysis` / `SensitivityAnalysis` / `MonteCarloAnalysis` /
  `UniformDistribution` / `NormalDistribution` / `compute_statistics` /
  `run_monte_carlo` — netlist-string, backend-oriented (ngspice) specs and
  executor; F8-H Q3 precedent (netlists don't serialize device parameters)
  forces Component-level native machinery instead (justified §9).
- Invariants: sorted/ref-ordered determinism, SHA-256 digests
  (`json(sort_keys=True)`), no silent defaults, no magic ranges, no
  normative wall-clock, honest error statuses, KCL/KVL/Tellegen checks.

## F8-M Scope

Closed capability set (each fully specified below; nothing else):

| ID | Capability | Contract |
|:---|:---|:---|
| M1 | Native DC sweep | Independent V/I source swept over linear/log/list grids; per-point DC op (linear or Newton); warm-start chaining with zero-vector fallback; per-point status preserved |
| M2 | Native parameter sweep | Component `value` + device model params via explicit address allowlist; grid/list/corners-sampling modes; deterministic order; warm-start; full per-point results |
| M3 | Worst-case corners | `2^k` corner enumeration (k≤10) over addressed ranges + per-observable extremum + arg-corner (corner extremum only — NOT a proven global optimum) |
| M4 | DC sensitivity (implicit-analytic) | `dx/dp = −J⁻¹·∂F/∂p` at converged points; analytic `∂F/∂p` tables; observable chain rules; normalized form; honest singular handling |
| M4-AC | AC sensitivity, linear elements only | `dX/dp = −A⁻¹·(∂A/∂p)·X` over the F8-J complex system for R/L/C/E/G/H/F/T-n; complex + magnitude/phase/dB derivatives |
| M5 | Native Monte Carlo (DC-op base) | Seeded plan, Component-level substitution, cold native DC solves, failed iterations recorded, descriptive statistics |

Capability decision table (§5 of mandate):

| Candidate | In | Out | Reason |
|:---|:---:|:---:|:---|
| DC sweep (native) | ✓ | | roadmap row 4; no native engine exists |
| Parameter sweep | ✓ | | roadmap row 4; netlist path can't carry device params |
| Worst-case corners | ✓ | | roadmap row 4; shares M2 engine, separate extremum view |
| DC sensitivity (implicit) | ✓ | | roadmap "sensibilidad"; closed math below |
| AC sensitivity (linear) | ✓ | | small new math on F8-J; Bode-design value |
| Native Monte Carlo | ✓ | | roadmap row 4; seeded, honest failures |
| Continuation/homotopy engine | | ✓ | no demonstrated need inside certified solver behaviour; warm-start (M1/M2) covers bias-stepping; speculative machinery banned by §26 |
| Pseudo-arclength/bifurcation/stability flags | | ✓ | no verifiable spec, no turning-point need |
| Poles/zeros | | ✓ | requires polynomial/eigen infra that does not exist |
| AC sensitivity to nonlinear device params | | ✓ | second-derivative machinery; deferred, documented |
| Transient/adjoint sensitivity | | ✓ | backward-integration infra absent |
| Transient-base sweeps/MC | | ✓ | cost + event complexity; composition contract specified, engine deferred |
| Noise (device models) | | ✓ | no certified noise models |
| Frequency-sweep engine | | ✓ | EXISTS (F8-D5/response.py) |
| Transmission lines/distributed | | ✓ | never in F8 scope |
| GUM metrology sensitivity | | ✓ | other domain (`gum.py`) |
| Multi-stability detection | | ✓ | branch-following documented as warm-start behaviour, detection deferred |
| Non-numeric params (polarity/kind) as sweepables | | ✓ | categorical; allowlist is numeric-only |

## Out of Scope

As the table above, each with reason + future home (mostly a future
"robustness/frequency" phase or never). F8-M implementations must not
smuggle any of these in (§26).

## Architecture

```text
Circuit (+ DC-equivalent mapping C→removed, L→0V-short, waves→DC value, IC ignored)
  ↓
Problem (build_mna_problem, existing flags; F8-M validates variants per point)
  ↓
MNA (A0/b0 Fractions→Decimal; static stamps incl. F8-K devices)
  ↓
Device stamps (F8-H/I/K math reused unmodified: currents + analytic Jacobians)
  ↓
Point solvers (solve_linear_dc / solve_nonlinear_dc [+ optional x_init, R-02])
  ↓
F8-M layer (new mna/analysis.py): sweep driver, sensitivity solver,
            worst-case enumerator, seeded MC driver
  ↓
Result / reporting (per-point results + digests, statistics, provenance)
```

F8-M accepts the full component set; internally it maps to the DC
equivalent exactly per the F8-J precedent (C removed, L→deterministic
`V9000+` 0 V short, V/I waves replaced by DC `value`, ICs ignored as
transient concepts — all documented in provenance). H/F with `control_ref`
to C/L → `INVALID` (transient pre-check precedent). O/T/E/G/H/F linear
handling unchanged.

Planned refactors (additive, regression-gated on full F8-H/I/J/K/L green):
- **R-01**: extract pure `dc_residual()` / `dc_jacobian()` helpers reused by
  both `nonlinear.py` and `analysis.py` (needed: J(x\*) + ∂F/∂p for M4).
- **R-02**: optional `x_init` in `solve_nonlinear_dc` (validated
  length/finiteness, default `None` = bit-identical current behaviour) for
  warm-start chaining.

## Mathematical Formulation

Shared unknown vector `x` (nodes + aux, §4). Converged point `x*` with
certified Jacobian `J = ∂F/∂x` (R-01). Newton Q1 reused everywhere; no new
convergence tolerances.

### M1 — DC sweep

Target: independent source ref (V|I). Grid (native, Decimal-explicit):
- linear `{start, stop, step}`: `n = floor((stop−start)/step)+1` points,
  `stop` appended iff within half-step (mirrors `DCSweepAnalysis`
  semantics); sign consistency enforced (`step≠0`, direction matches range).
- log `{start, stop, n}`: `start·(stop/start)^{k/(n−1)}`, k=0..n−1;
  requires `start,stop>0`, same sign, `n≥2` (`n==1` requires start==stop).
- list `{values[]}`: non-empty, finite; order significant (preserved,
  digested).
Per point k: substitute value → revalidate variant → solve (cold
zero-vector for k=0; warm-start `x_init=x(k−1)` if converged else cold;
init mode recorded) → store `{value, status, result, newton_iters,
init_mode, diagnostic}`. Sweep status: COMPLETED /
COMPLETED_WITH_POINT_FAILURES / INVALID / UNSUPPORTED (config errors).
`MAX_SWEEP_POINTS = 2000` (memory bound: full per-point results).

### M2 — Parameter sweep

Address: `{ref, field}` with closed numeric allowlist —
`value` (R/V/I/E/G/H/F) and per-type model params
(D:Is/n/Vt/Vz/nz/Iz/Iph; Q:Is/Bf/Br/Nf/Nr/Vt; M:Kp/Vto/Lambda/Phi/Gamma;
J:Idss/Vp/Lambda; T turns-n). Non-numeric (`polarity`/`kind`) excluded.
Modes: grid over one address (linear/log/list as M1), multi-address
cartesian list-of-dicts (explicit, order-significant), corners sampling
(`{addr: (low, high)}` → named corner subset, NOT full enumeration —
full `2^k` belongs to M3). Same solve/record/warm-start machinery as M1
(shared internal driver; one engine, two configs).

### M3 — Worst case

Config `{parameters: {addr: (low, high)}, observables: [...]}` with
k≤10 (`INVALID` beyond: exponential wall). Enumerate all `2^k` corners in
canonical (sorted-address, low-before-high) order; per corner full solve;
per observable record min/max + arg-corner (first-in-order wins ties).
Status = sweep statuses. Documented honesty: corner extremum, NOT a proven
global optimum (interior extrema invisible to corners).

### M4 — DC sensitivity

At converged `x*`, nonsingular J:
`J·(dx/dp) = −∂F/∂p`, solved via HP `linsolve` (one factorisation, one
solve per parameter). `∂F/∂p` tables (all closed-form, Decimal):
- R: `dG=−1/R²` nodal stamps; V: `−1` on constraint row; I: `±1` KCL;
  E(μ)/G(gm)/H(r)/F(β): resolved-control-form derivatives;
  T(n): constraint-row derivatives.
- D: `∂I/∂Is=I/Is`-form (`g−1`-style exact terms), `∂I/∂n`,
  `∂I/∂Vt` from `Is·e^a`, `a=Vd/(nVt)`; Zener `+∂/∂Vz,nz,Iz` of the
  breakdown term; `∂I/∂Iph=−1`.
- BJT/MOS/JFET: term-wise differentiation of the certified terminal
  expressions (pattern: injection-level derivatives × gain chain rule,
  e.g. `∂αF/∂Bf=1/(Bf+1)²`, `∂ID/∂Vto=−gm`, `∂ID/∂Kp=ID/Kp`,
  `∂ID/∂Idss=ID/Idss`); full term tables required in implementation,
  each validated by the FD oracle (below).
- Region boundaries (MOS `Vov=0`/`VDS=Vov`, JFET edges, Zener `Vd=0`):
  branch-consistent one-sided derivatives (right-continuous choice),
  documented; tests avoid exact-boundary assertions or assert the
  documented branch.
Observables: node voltage (unit vector), aux branch current (unit),
R branch current (`d[(V1−V2)/R]` product rule), element power
(product rule), device terminal currents (`J_row·dx/dp + ∂I/∂p`
explicit). Units: `dim(dx/dp)=dim(x)−dim(p)` tuple-wise (new `dim_sub`
helper); result table carries `(value, dimension)` pairs.
Normalized: `S = (p/o)·(do/dp)` (guard `o=0` → recorded null, not zero).
Singular J → `SINGULAR_JACOBIAN` (never pseudo-inverted).
FD oracle (validation ONLY, in tests): central differences,
`h=max(1E-6·|p|,1E-12)`, match `<1E-4` relative (F8-K precedent).

### M4-AC — AC sensitivity (linear elements)

At a solved F8-J point (`A·X=b`, DecimalComplex HP): for parameter p in
{R,L,C,E,G,H,F,T-n}: `dX/dp = A⁻¹·(∂b/∂p − (∂A/∂p)·X)` (here `∂b/∂p=0`;
AC source magnitudes not addressable). `∂A/∂p`: R `dG=−1/R²`; C
`∂Y/∂C=jω`; L `∂Y/∂L=+j/(ωL²)` from `Y_L=−j/(ωL)`; gains linear stamps;
T(n) constraint derivatives. Observables: complex phasors + magnitude
(`Re(conj(H)·dH)/|H|`, guard `|H|=0`), phase, dB chain rules. Nonlinear
device-param AC sensitivities explicitly OUT.

### M5 — Native Monte Carlo

Config `{iterations N (1≤N≤10000), distributions {addr: spec},
seed: int (REQUIRED — the `simulation.py` random-fallback is forbidden
here), base="dc-op"}`. Native distribution specs (new, Decimal-exact;
justified duplication-free layering — `simulation.py` specs are
float-mediated and netlist-bound):
- uniform `{low, high}` (`low<high`, finite): fraction from
  `rng.getrandbits(53)/2^53` (EXACT binary→Decimal, no float transit).
- normal `{mean, std, min, max}` (`std≥0`): Box–Muller with `Decimal.ln`
  (context-explicit), `decimal_sin/cos`, `ctx.sqrt` (exact, seeded).
Plan pre-generated (master seed → sub-seeds, sorted addresses) with plan
digest; cold zero-vector native DC solves in plan order (sequential — no
parallelism in F8-M); sampled circuits revalidated per iteration
(illegal samples → recorded FAILED iterations, never clamped, never
hidden); NATIVE descriptive statistics (mean/variance exact in Decimal,
std via context `sqrt`, percentiles via sorted-rank Decimal
interpolation — `simulation.py:compute_statistics` is NOT reused because
it is float-mediated (`math.sqrt(float(...))`) and netlist-bound; the
~40-line native version is specified here with that justification). Statuses: COMPLETED /
COMPLETED_WITH_FAILURES / INVALID.

### Shared provenance

`engine="f8m-analysis/1.0"`, method, config digest, circuit topology
digest (new tiny helper — no certified-private imports), per-point Newton
provenance links (digests, not copies), seed-plan digest (M5), grid digest
(M1/M2/M3). Warm-start/fallback mode per point recorded.

## Algorithms

- Sweep driver (shared M1/M2/M3 enumeration core): ordered point list →
  variant build → validate → solve → record. Warm-start with fallback.
- Sensitivity: refactor-exposed J (R-01) + ∂F/∂p tables → HP solves →
  observable chain rules → (normalized) tables.
- Worst-case: corner enumeration + extremum reduction (first-wins ties).
- MC: seeded plan → substitute → cold solve → aggregate.
- AC sensitivity: ∂A/∂p assembly → HP solves → phasor/derived metrics.
- Parametric AC/transient sweep: COMPOSITION CONTRACT specified
  (per-point native solves + aggregation pattern + determinism rules),
  engine deferred (OUT with reason).

## APIs

New module `mna/analysis.py` (all frozen dataclasses, Decimal-native):
`ParamAddress{ref,field}`, `ObservableSpec{kind,locator}`,
`SweepConfig/SweepPoint/SweepResult/SweepStatus`,
`SensitivityConfig/SensitivityResult/SensitivityStatus`,
`ACSensitivityConfig/ACSensitivityResult`,
`WorstCaseConfig/WorstCaseResult/WorstCaseStatus`,
`MCConfig/MCIteration/MCResult/MCStatus`,
`solve_dc_sweep / solve_param_sweep / solve_worst_case /
solve_dc_sensitivity / solve_ac_sensitivity / run_monte_carlo_native`.
Every function: typed inputs/outputs, Quantity/dimension rules, exact
exceptions (`InvalidCircuitError` config errors; status enums for solve
outcomes — never untyped generic exceptions for numerics), no side
effects (input circuits never mutated; fresh variants per point).

## Numerical Precision

Decimal-native end to end; `float(` = 0 in new code (grep + AST gate);
`numpy/scipy/math` forbidden in the engine (sine needs already go through
`decimal_sin`); ambient-context traps banned in new arithmetic
(`copy_abs`, `ctx.*` — the P1 bug class); MC fractions exact via
getrandbits; statistics reuse is Decimal-exact.

## Tolerances

No new convergence tolerances: Newton Q1 governs all point solves;
sensitivity reuses HP exactness; FD validation tol 1E-4 (relative).
Resource budgets (symbols + justification, MAX_* precedent):
`MAX_SWEEP_POINTS=2000` (per-point full results memory),
`MAX_MC_ITERATIONS=10000` (~100 s deterministic budget),
`MAX_WORST_PARAMS=10` (2^k wall). LTE n/a (no time domain).

## Convergence

Point solves: certified Q1 + `NonlinearStatus` preserved per point.
Sensitivity: linear-solve status mapping (SINGULAR→honest status).
Sweep/WC/MC: completion statuses (§Mathematical Formulation).
Stagnation/singularity/overflow/divergence detection all inherited from
the point solvers; never converted into success.

## Determinism

Same input + same config (+ same seed for M5) → same output:
sorted addresses/components/grids, sequential execution, seeded-only
randomness, Decimal-only arithmetic, `sort_keys` digests, list-order
significance documented where user order is preserved.

## Error Handling

Config errors → `InvalidCircuitError`; unsupported combinations →
`UnsupportedElementError`/status; per-point solve outcomes → native
statuses; singular sensitivity Jacobian → `SINGULAR_JACOBIAN`; illegal
samples → FAILED iterations; no clamping, no hiding, no generic
exceptions for math outcomes.

## Integration

| Capability | F8-H | F8-I | F8-J | F8-K | F8-L |
|:---|:---:|:---:|:---:|:---:|:---:|
| M1/M2/M3 | D points | Q points | — | M/J/kinds points | DC-equiv pattern reuse |
| M4 | J + ∂F/∂p | J + ∂/∂BJT | — | J + ∂/∂MOS/JFET/kinds | — |
| M4-AC | — | — | A/b reuse + ∂A/∂p | — (device params out) | — |
| M5 | cold solves | cold solves | — | cold solves | — |
| Reuse | extract/current/jac | same | linsolve HP | same | none (no transient base) |

R-01/R-02 refactors regression-gated. No engine duplication without the
documented justifications above.

## Validation

- Case A (linear closed form): divider DC sweep vs `Vout=V·R2/(R1+R2)`
  per point; Thevenin cross-check.
- Case B (scalar param): `dVout/dR` analytic vs M4 on divider.
- Case C (sweep): endpoints, monotonicity (divider), list-order
  preservation, log-grid ratios.
- Case D (corners): 2-R worst-case arg-corners vs exhaustive reasoning.
- Case E (sensitivity): analytic-vs-FD oracle per parameter class
  (validation-only FD, production implicit-analytic).
- MC: seed reproducibility (same seed → identical plan+results),
  statistics sanity vs analytic divider moments, failure recording
  (poisoned distribution → FAILED iterations, suite still completes).
- AC sensitivity: FD oracle on RC low-pass `d|H|/dR`, `d∠H/dC`.
- External: ngspice DC-sweep comparison on a diode clipper (loose,
  convention-documented); ngspice `.op` spot checks for corner extrema.

## External Oracles

ngspice 47 batch (existing binary path precedent): DC sweep trace +
corner `.op` points, loose tolerances with knee-convention notes.
External = validation only, never a production dependency.

## Security

New code: 0 `eval/exec/compile/globals/locals/__import__`,
0 `subprocess/socket/os/sys/importlib/requests`, 0 process-spawning
calls (AST suite mirroring F8-K/F8-L scans over `mna/analysis.py`).
No deserialization beyond validated config dataclasses; no network.

## Performance

Diagnostic-only (never normative wall-clock): per-sweep point counts,
Newton totals, sensitivity solve counts, MC iteration timings,
rejected/failed counts. No `assert elapsed < X` anywhere.

## Test Matrix

| ID | Capability | Test | Expected |
|:---|:---|:---|:---|
| M-001..006 | grids | linear/log/list validation, endpoint rules, sign/direction errors, empty/single/reversed | exact sequences + INVALID paths |
| M-007..010 | M1 | divider sweep closed form; warm-start iters ≤ cold; fallback recorded; point-failure tolerance | values + statuses |
| M-011..016 | M2 | value + each device-param class sweep; invalid address/field; multi-address order; corners sampling | values + INVALID paths |
| M-017..020 | M3 | 2-R corners + extrema + arg-corners; k>10 INVALID; tie first-wins | extrema + corners |
| M-021..030 | M4 | divider analytic; per-class FD-oracle match (D/Q/M/J/kinds/gains/T); normalized form; singular → status; boundary branch policy | <1E-4 vs FD |
| M-031..034 | M4-AC | RC low-pass FD-oracle; singular; unsupported device-param → INVALID | match + statuses |
| M-035..040 | M5 | seed reproducibility; moments vs analytic; failure recording; N bounds; missing seed INVALID | identical dicts |
| M-041..044 | determinism | insertion-order invariance; digest stability; sequential plan | identical |
| M-045..046 | security | AST + float scans | zero hits |
| M-047..049 | benchmarks | sweep/MC/sensitivity diagnostics | metrics only |
| M-050..052 | external | ngspice sweep trace + corner spots | loose match |
| M-053..056 | regression | F8-H/I/J/K/L suites green + new suite | 100% |
| M-057..060 | edge | zero/negative/extreme params; disconnected; degenerate/single sweeps; overflow; dup params | honest statuses |

(Tests specified only — none implemented in this phase.)

## Regression Contract

F8-M must keep green: `test_f8h_nonlinear_dc.py` (69),
`test_f8i_bjt.py` + `test_f8i_nonlinear_bjt.py` (74),
`test_f8j_small_signal_ac.py` (29), `test_f8k_*` (110),
`test_f8l_transient.py` (58), plus linear/DC/F8-D/F7 batches (all
currently green). R-01/R-02 land only with this contract verified.

## Known Risks

1. R-01 refactor touches certified `nonlinear.py` internals → mitigated by
   the regression contract + behaviour-identical default paths.
2. `x_init` warm-start could mask divergence across hysteresis branches →
   mitigated by recording init mode per point + documenting
   branch-following semantics.
3. Corner extremum mistaken for global optimum by users → mitigated by
   explicit honesty clause in result docs + gate.
4. Second-order effect: sweep point count × full-result memory →
   mitigated by MAX_SWEEP_POINTS.
5. FD oracle near device exponential overflow → validation points
   restricted to safe regimes (documented per test).

## Open Questions

None blocking. (All "determine whether" items above resolved with
reasons: continuation cut §26, AC-device-params deferred, transient
bases deferred, poles/zeros out, noise out.)

## Certification Criteria

- [ ] design gate READY (this document)
- [ ] implementation complete per §§Mathematical Formulation/Algorithms/APIs
- [ ] R-01/R-02 landed with regression contract green
- [ ] unit tests pass (M-001..006 + validation classes)
- [ ] mathematical validation pass (Cases A–E + FD oracles)
- [ ] integration pass (F8-H/I/J/K reuse, no duplication drift)
- [ ] regression pass (all baseline suites green)
- [ ] determinism pass (seed/ordering/digest tests)
- [ ] precision audit pass (0 float, context-explicit)
- [ ] security audit pass (AST zero hits)
- [ ] external validation pass where applicable (ngspice sweep/corners)
- [ ] no undocumented deviations (any deviation → gate-documented like
  F8-K DEVIATION-01)
- [ ] no normative timing assertions
- [ ] documentation complete (gate + API docs in code)
- [ ] git audit clean (no secrets, no F8-N content, no force)

## Final Verdict

`F8-M DESIGN READY`
