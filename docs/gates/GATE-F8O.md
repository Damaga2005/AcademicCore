# F8-O Certification Gate

## Baseline

- Repository `Damaga2005/AcademicCore`, branch `main`.
- Design baseline `dd806eb`; design gate commit `1fbfc23`
  (`docs(gates): add F8-O mathematical design gate`, verdict `F8-O DESIGN READY`).
- Preconditions verified at implementation start: `HEAD = 1fbfc23`,
  `origin/main = dd806eb`, branch `main`, working tree clean, no foreign
  changes (no `reset`/`clean`/`restore` used at any point).

## Design Gate

`docs/gates/GATE-F8O-DESIGN.md` (428 lines, `F8-O DESIGN READY`) is the
contract. No `DESIGN CONFLICT` was found during implementation: every
equation, tolerance, status, limit and interface in the gate mapped onto a
real certified API. Three sub-design resolutions were recorded explicitly
(not silent improvisations — see §Deviations):
D-R4 (structural Waveform adapter, no `lab/` import edge — certified test
N-110 outranks the gate's `metrology → lab` edge), replay-vocabulary
aliases (`VALID`/`RESULT_DIFFERENT`, mandate §23 wording), O-011 pole FD
fallback (ADAPT through certified `model.evaluate`, tagged `NUMERICAL`).

## Implemented Scope

| Gate ID | Component | File | Classification | Status |
|:---|:---|:---|:---|:---|
| O1/O7/O8 | Type A/B inputs + Waveform adapter | `metrology/o1_inputs.py` | WRAP gum / ADAPT Waveform | PASS |
| O2/O3/O5/O7/O8/O11 | Analytic propagation `u_c → ν_eff → k → U` | `metrology/o2_propagate.py` | WRAP `gum.evaluate_gum` | PASS |
| O3/O4/O12 | Circuit sensitivities + MC + copula | `metrology/o3_circuit.py` | REUSE F8-M / NEW copula+verdict | PASS |
| O4 | Significant figures (GUM §7 view) | `metrology/o4_significant.py` | NEW (pure view) | PASS |
| O5 | Traceability DAG + digests | `metrology/o5_traceability.py` | NEW (data only) | PASS |
| O6/O9/O10 | Report + `f8o-metrology/1` + replay | `metrology/report.py` | NEW envelope | PASS |
| — | Error model | `metrology/errors.py` | NEW (thin) | PASS |
| — | Public API | `metrology/__init__.py` | REUSE surface | PASS |

No new solver, device model, sampler core, sensitivity engine, UI,
filesystem, network, subprocess, clock, global random, `eval`/`exec`,
`pickle`, `float` value conversions, or second GUM implementation.

## Mathematical Implementation

- `Y = f(X)` via wrapped `MeasurementModel` (equation string through the
  safe parser, or `Quantity → Quantity` evaluator — F7-B7 closure kept).
- `u_c² = Σ c_i²u_i² + 2ΣΣ c_i c_j cov_ij`, `cov = r·u_i·u_j` — certified
  engine; `total_var < 0` → `NUMERIC_ERROR` (quantified case `-6E-9`,
  O-026), never `abs()`/clamp.
- Sensitivity order EXPLICIT > ANALYTIC > NUMERICAL delegated to
  `model.get_sensitivity`; gate step `h = max(|x|·1e-6, 1e-9)` bilateral
  central FD; analytic-pole fallback (O-011, `4E+18` tagged NUMERICAL).
- Type A `x̄/s/√n/ν=n−1`; Type B `a/√3`, `a/√6`, `U/k`; all-`u=0` exact
  degenerate (`u_c=U=0`, `ν=∞`).
- Welch–Satterthwaite hand-verified (`ν_eff = 125` for the mixed fixture,
  rel `<1e-9`); all-`∞` → `∞`; `k = t_{(1+p)/2}(ν)` with 6dp boundary
  rounding exactly once (`t₅ = 2.570582`, normal limit `1.959964`).
- MC propagation composes F8-M native (seed mandatory); correlated
  sampling via NEW Decimal Cholesky + Box–Muller (certified
  `trig`/`logarithm` helpers, local `Random(seed)` stream).
- Significant figures: `U` → 2 s.f. (`ROUND_HALF_UP`), `y` → `U` decade;
  display strings never feed back (O-043b).
- Traceability DAG with `sha256(tag‖0x00‖canonical)` digests; reports
  with schema `f8o-metrology/1`, same digest construction.

## Numerical Validation

- `Decimal` at every boundary; `float()` confined to dof/coverage/seed
  scalars at the wrapped-API boundary (O-060 allowlist; no `float` on any
  measurement value, no `math`/`statistics`/`numpy`/`scipy` in new code).
- Reference/Type A-B identities verified as squares (`u² = 1/2, 1/3, 1/6`
  within `1e-15`), divider closed forms `<1e-30`/`1e-12`, FD oracles
  `<1e-4` (model) / `<1e-4` (nonlinear circuits D/Q/M) / `<1e-3` (AC
  magnitude chain).
- MC-vs-analytic: `M = 10000`, seed 42, divider fixture —
  `|u_MC − u_c|/u_c ≤ 5 %` agreement `True` (diagnostic criterion).
- Bit-identity pin `uc = 0.22360679774997896`, `k = 1.959964` (O-062).

## Type A

O-001 canonical (`x̄=10, u=0, ν=4`), O-002 dispersed (`x̄=3, u²=0.5 ±1e-15`),
O-003 `n<2` INVALID, order-invariance property, `n=2` minimal, Waveform
adapter bit-equal to direct observations (O-059, no engine re-solve).

## Type B

O-004 rectangular, O-005 triangular, O-006 normal (`U/k`, `k≤0` INVALID),
O-007 negative half-width INVALID, explicit path, hostile battery
(NaN/Inf/bool/non-numeric → INVALID).

## Propagation

O-014 uncorrelated exact (`√0.05`), O-015 `r=+1` (`0.3 ±1e-15`), O-016
`r=−1` (`0.1 ±1e-15`), O-017 PSD 3×3 accepted, single/multi-input,
budget shares sum `100 ± 0.01` (O-048).

## Sensitivities

O-008…O-012 analytic patterns exact; O-013 FD `exp` vs in-test series
`<1e-4`; O-034 divider M4 vs closed form `<1e-12`; O-035/036/037 diode/BJT/
MOSFET M4 vs independent FD-of-`solve_point` `<1e-4`; O-038 AC
`d|H|` vs FD-of-`solve_small_signal_ac` `<1e-3`.

## Covariance

`cov = r·u_i·u_j` via wrapped matrix; `r ∈ {−1, 0, +1}` + interior values;
out-of-range/asymmetric/diagonal violations → INVALID at construction;
non-PSD → SINGULAR (construction or budget time, never silent).

## Welch-Satterthwaite

Finite/infinite/degenerate/zero-denominator cases per gate; hand reference
`ν_eff = 125`; `u_c = 0` → exact degenerate branch.

## Student-t

`ν = 5` table `2.570582`; normal limit `1.959964`; `p ∉ (0,1)`/`ν ≤ 0`/
NaN → INVALID; `explicit_k` validated (`> 0`, finite) with
`explicit_user` provenance.

## Monte Carlo

Seed required (None/negative/bool → INVALID); determinism (same seed ×2 →
same digest; triple-run ×3 → one digest); seed separation (42 vs 43);
`M = 10000` analytic agreement; copula `r = 0/±0.9/degenerate`, sorted-order
invariance, marginal stats via native statistics.

## Significant Figures

O-043 (`1.235 ± 0.023`), O-044 (leading-one `3.14 ± 0.14`, zero `0`),
decade helper, no-feedback property.

## Traceability

3-link chain stable + order-invariant digest + `verify() == OK`; broken
link → INCONSISTENT; cycle/self-link/dup-id → INVALID; `str()`-Decimals,
`"inf"` canonical, no timestamps/UUIDs.

## Serialization

`f8o-metrology/1`: deterministic dumps, `≤ 64 MiB` guard, unknown-field /
bad-type / bad-JSON rejection, digest recompute (tamper →
INCONSISTENT/INVALID_SERIALIZATION), `str()` (never `normalize()`).

## Replay

`EQUIVALENT` (alias `VALID`), `RESULT_DIFFERS` (alias `RESULT_DIFFERENT`),
`VERSION_MISMATCH`, `SCHEMA_MISMATCH`, `INVALID_SERIALIZATION` — all
exercised; same-version deterministic replay byte-identical.

## Determinism

Triple-run single digest; insertion-order invariance (budget + report);
seeded MC; canonical JSON; no clock/locale/parallelism in digests.

## Security

AST + substring audit (O-033/O-058/O-060/O-064, plus `test_eng_security.py`
green): 0 `eval/exec/open/getattr/setattr/compile/__import__/subprocess/
pickle/marshal/importlib/socket/urllib` calls, 0 `math/numpy/scipy/
statistics` usage, 0 float on values, 0 `global` statements in
`metrology/`; `re.compile` correctly distinguished from builtin
`compile()` (neither present in new code); deserialization is
typed/allowlisted, size-guarded, digest-verified.

## Architecture

`metrology → {gum, mna.analysis, mna.sensitivity, math.trig,
math.logarithm, units, equations(via gum)}`; engines never import
metrology; **no** `metrology → lab` import edge (structural Waveform
adapter — N-110 clean); no UI/application/infrastructure/filesystem/
network/process imports (`test_architecture.py` green).

## Resource Limits

`N ≤ 64`, `MAX_MC_ITERATIONS = 10000`, `MAX_SWEEP_POINTS = 2000`,
`MAX_SERIALIZED = 64 MiB` — all enforced with deterministic INVALID;
t-quantile 60 iters / Jacobi 50 sweeps inherited (wrapped); budgets are
rejections, never truncations (O-055 + batteries).

## Test Matrix

`tests/test_f8o_metrology.py`: **70 tests, 70 PASS, 0 FAIL** (O-001…O-064
per gate matrix plus copula-determinism, alias-contract and boundary
batteries; every comparison records reference/actual/abs/rel/tolerance).
Types covered: UNIT, ANALYTICAL, NUMERICAL, PROPERTY, BOUNDARY, ERROR,
SECURITY, DETERMINISM, SERIALIZATION, REGRESSION, PERFORMANCE (recorded,
no wall-clock asserts).

## Regression Results

- F8-O new: 70/70 PASS.
- F7-B7 (79) + architecture + F8-H (69): PASS.
- F8-I (33+41) + F8-J (23+bench): PASS.
- F8-K (110) + F8-M (87): PASS.
- F8-N (125, incl. N-110 direction — failed once pre-fix, green after the
  structural adapter; no test modified): PASS.
- Full `pytest -q`: PASS, 0 failed, 2 skipped (pre-existing reportlab
  environment skips, unrelated).
- Transient suites F7-B3 + F8-L (58): PASS.

## Performance

Recorded (O-061, no wall asserts): small budget, N=64 budget, 8-var
correlation build, MC M=200, serde, replay — all seconds-scale; MC
M=10000 ≈ 16 s on the divider fixture. Priority respected:
correctness > determinism > numerical integrity > performance.

## Known Limitations

Inherited, unchanged: wrapped `gum.py` float kernels (`sqrt`, t-quantile,
Jacobi, W-S accumulation, `round(k,6)`, `inf` dof) stay inside the wrapped
boundary (D-R2); Decimal rewrite of those kernels is explicit future work,
not hidden debt. MC-vs-analytic 5 % is a diagnostic band, not a proof.
Pole FD (O-011) is tagged NUMERICAL and propagates honestly — consumers
must inspect budget contributions near singularities.

## Deviations

- **D-R4 (test over design)**: the gate allowed a `metrology → lab`
  import edge; certified test N-110 forbids any non-lab module importing
  `lab/`. The test wins: `waveform_to_observations`/`type_a_from_waveform`
  are structural (duck-typed, `try/except AttributeError`), with zero
  import edge. No certified test was modified.
- **Replay vocabulary**: canonical `EQUIVALENT`/`RESULT_DIFFERS` (gate);
  `VALID`/`RESULT_DIFFERENT` (mandate §23) are tested constant aliases.
- **O-011 pole fallback**: ADAPT — gate step rule through certified
  `model.evaluate`, result tagged `NUMERICAL`; no second FD engine.

## Evidence

- Code: `src/academic_core/domain/engineering/metrology/` (8 files, no
  banned constructs per §Security audit).
- Tests: `tests/test_f8o_metrology.py` (70 tests).
- Runs: F8-O suite, F7-B7/arch/H/I/J/K/M/N suites, full `pytest -q`,
  transient suites — all recorded above, 0 failures.
- Pins: `uc = 0.22360679774997896`, `k = 1.959964`, `t₅ = 2.570582`,
  divider `c = -0.0025`, `ν_eff = 125`, `4E+18` pole FD, `-6E-9`
  negative-variance case.

## Final Verdict

F8-O CERTIFIED
