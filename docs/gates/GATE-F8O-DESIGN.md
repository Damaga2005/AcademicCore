# F8-O Design Gate

Design gate for **F8-O — Metrology & Uncertainty (GUM)**. Documentation only: no code under
`src/` was created or modified, no tests were written, no engine was altered. The only output
of this phase is this file plus one local commit (no push).

## Baseline

- Repository `Damaga2005/AcademicCore`, branch `main`.
- Baseline **`dd806eb`** (`feat: implement F8-N virtual laboratory`), `HEAD == origin/main == dd806eb`
  (verified after `git fetch` at audit time).
- Certified at baseline: F0–F7 (incl. F7-B7 GUM engine, `tests/test_f7b7_gum.py` 79/79), F8-A … F8-N
  (gates on disk through `GATE-F8N.md`; roadmap §6.1 lists F8-N CERTIFICADO and marks
  **F8-O (NEXT)** per §5.1).
- Working tree clean at audit time (`git status --short --branch` → `## main...origin/main`, no entries).

## Scope

F8-O is the **metrology integration layer** over the certified engines. It adds **no solver, no device
model, no waveform generator, no sweep/MC/sensitivity engine**. It adds:

| ID | Capability |
|:---|:---|
| O1 | GUM Type A evaluation (mean, `s/√n`, `ν=n−1`) over `Decimal` observations / lab `Waveform` samples |
| O2 | GUM Type B evaluation (rectangular `a/√3`, triangular `a/√6`, normal `U/k`, explicit) |
| O3 | Analytic propagation (law of propagation of uncertainty with correlations) via wrapped F7-B7 math |
| O4 | Circuit-anchored sensitivities via F8-M (`solve_dc_sensitivity`, `solve_ac_sensitivity`) + closed `PARAM_REGISTRY` |
| O5 | Model-equation sensitivities via `MeasurementModel.get_sensitivity` (EXPLICIT / ANALYTIC / NUMERICAL) |
| O6 | Monte Carlo propagation by composing F8-M `run_monte_carlo_native` (Decimal, seeded); no new sampler |
| O7 | Coverage factor `k = t_{1−(1−p)/2}(ν_eff)` (Student-t, normal limit) + expanded uncertainty `U = k·u_c` |
| O8 | Correlation / covariance handling with PSD validation (wrapped Jacobi, `tol=1e-7`) |
| O9 | Significant-figures formatter (pure view, GUM §7 rule) — the only genuinely NEW math |
| O10 | Traceability-chain data model (calibration DAG as data + digests, no hardware) — NEW data model |
| O11 | Metrology report + canonical serialisation schema `f8o-metrology/1` + digests + replay/compare |
| O12 | Uncertainty-budget tables over wrapped `GUMResult` (renderer, no physics change) |

## Non-Scope

| Item | Reason | Future home |
|:---|:---|:---|
| New solver / device model / AC engine / transient companion | Engines F8-H…F8-L are certified and frozen | never in F8-O |
| New sampler / new RNG | F8-M native MC is the certified Decimal sampler | F8-M |
| Import of external repo `Conversor-HTML-A-MD` GUM calculator | External code + roadmap-flagged `eval()` blocker; local F7-B7 is certified and `eval`-free | never (see Deviations D-R1) |
| Reimplementation of GUM math (Type A/B, W-S, t-quantile, PSD) | Would duplicate certified F7-B7 (79 tests) | wrapped, not rewritten (D-R2) |
| Reuse of `simulation.py` (F7-A) float/netlist world | Float-mediated, netlist-bound; F8-M design precedent explicitly excludes it | never in F8-O |
| Non-ideal instrument physics (gain/offset/noise/loading/BW) | No certified models (F8-N out-of-scope table) | future “non-ideal instruments” phase |
| Transient branch currents beyond R/L | Not in `TransientResult` (F8-N finding 2); changing F8-L is forbidden | F8-L extension |
| Nonlinear AC sweep | No engine (F8-N finding 7) | F8-J extension |
| Hardware/DAQ, GUI/CLI/notebooks, network/cloud, grading/tutor | Domain must stay UI/network-free (`test_architecture.py`) | presentation / F9+ layers |
| Power/energy/FFT/THD/XY/math channels | Need own definitions; not required for GUM budgets | later lab-measurements phase |

## Repository Evidence

Auditable facts (read from code/tests, not assumed from prose):

1. **Git**: `main`, `HEAD == origin/main == dd806eb`, tree clean; log head
   `dd806eb feat: implement F8-N virtual laboratory`, `14b6c2f docs: add F8-N … design gate`,
   `c43483b docs: certify F8-M …`. Remote `origin https://github.com/Damaga2005/AcademicCore.git`.
2. **F8-O definition** (only 4 hits in `docs/roadmap/ROADMAP.md`, zero in `src/`/`tests/`):
   - `ROADMAP.md:168`: `F8-O Metrología e Incertidumbre (GUM) [6º]`.
   - `ROADMAP.md:207`: deps `F8-N, F6`; “Reutiliza calculadora GUM del repo `Conversor-HTML-A-MD`;
     **bloqueado** hasta sustituir `eval()`”.
   - `ROADMAP.md:269,271`: F8-N certified, **F8-O (NEXT)**; scope = “GUM tipo A/B/combinada/expandida,
     propagación analítica y Monte Carlo, cifras significativas y trazabilidad metrológica”.
   - `GATE-F8N-DESIGN.md:100` explicitly excludes F8-O; `GATE-F8N.md:519` / `:883,886` confirm no F8-O content.
3. **Certified reuse surface**:
   - F8-H: Shockley DC + damped Newton, `Decimal prec=80`, KCL `rtol=1e-9/atol=1e-12`, Q1 frozen
     (`GATE-F8H.md`). F8-I: Ebers-Moll NPN/PNP, analytic 3×3, B1–B15 (`GATE-F8I.md`).
     F8-J: frozen-`x0` small-signal AC, `DecimalComplex`, prec 50 (`GATE-F8J.md`).
     F8-K: MOSFET L1/JFET/Zener/LED/Schottky/photo, SOLVER-EXT-01 flat-region accept (`GATE-F8K.md`).
     F8-L: BE/TR/BDF2 + LTE adaptive + transactional history, `MAX_TRANSIENT_STEPS=100000` (`GATE-F8L.md`).
     F8-M: M1/M2/M3/M4/M4-AC/M5, closed `PARAM_REGISTRY`, warm-start+fallback recorder,
     `MAX_SWEEP_POINTS=2000/MAX_MC_ITERATIONS=10000/MAX_WORST_PARAMS=10`, 87 tests M-001…M-060 (`GATE-F8M.md`).
     F8-N: `lab/` orchestration, `Scalar/ComplexScalar/Waveform`, canonical digests
     `sha256(tag‖0x00‖canonical_json)`, budgets, no-solver rule (`GATE-F8N.md`, `GATE-F8N-DESIGN.md`).
   - F6: `Quantity/Unit/parse_unit`, safe `equations.py` (own recursive parser, **no eval/exec**,
     `ALLOWED_FUNCS=(sqrt,exp,log,log10,sin,cos,tan,abs)`), deterministic digests (`GATE-F6.md`).
   - F7-B7: `gum.py` (1263 lines) certified PASS post-audit (evaluator bypass closed), 79/79 tests,
     full `test_f7b7_gum.py + test_architecture.py` green at audit time (exit 0). Single unit authority
     (`parse_unit`), PSD validation, numeric sensitivity unrounded, `explicit_k` validated (`GATE-F7B7.md`).
4. **Float audit** (`grep` over `domain/engineering`): `mna/` + `ac/small_signal.py` + `lab/` are
   `float(`-free (certified); `simulation.py` is the float world (excluded by precedent);
   `gum.py` retains **bounded float kernels**: `math.sqrt(float(·))` (Type A/B, `u_c`),
   `float("inf")` dof, `round(k,6)`, Jacobi/beta/Student-t float internals, W-S float accumulation
   (`gum.py:50-123,144-280,308-346,616-625,1124-1142,1191`). `equations.py` has no eval/exec/compile
   (docstring “Never eval/exec”). `getattr/setattr` hits are frozen-dataclass `object.__setattr__`
   and defensive duck-typing, classified per-module in §Security (no dynamic dispatch of physics).
5. **No-duplication grep**: `F8-O|F8O` → only roadmap + F8-N exclusion notes; `TODO|FIXME|NotImplemented`
   in engineering → only `Quantity`/`DecimalComplex`/`rational` operator-reflection `NotImplemented`
   (correct Python protocol) + `models.py` ideal placeholders (superseded by certified extractors);
   significant-figures/traceability → zero implementation (justifies O9/O10 as the only NEW items).

## Mathematical Specification

### 6.1 Domain

- **Variables**: measurand `Y ∈ ℝ` (scalar; complex GUM out of scope — AC magnitudes handled via
  `|H|/dB/phase` real projections from F8-J/F8-D6, never complex variances); inputs
  `X = (X_1…X_N) ∈ ℝ^N`, `1 ≤ N ≤ MAX_METROLOGY_INPUTS (64)`.
- **Parameters**: nominals `x_i: Decimal` finite; standard uncertainties `u(x_i): Decimal ≥ 0`;
  distributions `rectangular|triangular|normal|student_t|explicit`; dof `ν_i ∈ (0,∞]`
  (canonical `inf` string); correlations `r_ij ∈ [−1,1]`; coverage `p ∈ (0,1)` (default 0.95);
  explicit `k > 0` finite optional; MC seed `s ∈ ℤ, s ≥ 0` required for O6.
- **Units**: every input/output carries an F6 `Unit`; dimensionless is `Unit("1",…)` — never a bare number
  in the dimensional contract. Evaluators receive `dict[str,Quantity]` and must return `Quantity`
  (F7-B7 closure); legacy dimensionless-only models keep the `Decimal→Decimal` contract.
- **Representation**: `Decimal` at every boundary; complex only as certified `DecimalComplex`
  outside the GUM variance algebra.

### 6.2 Equations

Pipeline: `Entrada → sensibilidades → varianza combinada → ν_eff → k → U → redondeo/trazabilidad`.

Measurement model: `Y = f(X_1,…,X_N)`, `f` = equation string (safe parser) or Quantity-contract evaluator.

1. **Type A** (observaciones `x_1…x_n`, `n ≥ 2`):
   `x̄ = (1/n)Σx_j`, `s² = Σ(x_j−x̄)²/(n−1)`, `u = s/√n`, `ν = n−1`.
2. **Type B**: rectangular `u = a/√3`; triangular `u = a/√6`; normal `u = U/k`;
   explicit `u` given. All with `ν = ∞` except stated-dof normal.
3. **Sensitivities**: `c_i = ∂f/∂X_i|_x`. Source priority EXPLICIT (user) > ANALYTIC (closed patterns:
   sum `1`; difference `±1`; product `x_j`; quotient `1/x_j, −x_i/x_j²`; divider
   `R_2/(R_1+R_2), −V_in·R_2/(ΣR)², V_in·R_1/(ΣR)²`; circuit Jacobians from F8-M) > NUMERICAL
   (central FD, `h = max(|x_i|·10⁻⁶, 10⁻⁹)`, full Decimal, no rounding).
4. **Combined** (law of propagation, incl. correlations):
   `u_c²(y) = Σ_i c_i²·u²(x_i) + 2·Σ_{i<j} c_i·c_j·u(x_i)·u(x_j)·r_ij`.
   `total_var < 0` → `NUMERIC_ERROR` (never clamped).
5. **Welch–Satterthwaite**: `ν_eff = u_c⁴ / Σ_{ν_i<∞} (c_i·u_i)⁴/ν_i`; all-`∞`/zero-denom → `∞`.
6. **Coverage**: two-sided `k = t_{(1+p)/2}(ν_eff)`; `ν_eff ≥ 10⁵` or `∞` → normal-limit inverse CDF.
   `explicit_k` allowed iff finite and `> 0`, recorded as `explicit_user`.
7. **Expanded**: `U = k·u_c(y)`.
8. **MC propagation** (O6): draw `M` joint samples (Gaussian copula from PSD correlation via
   deterministic Cholesky/Jacobi path under the F8-M seed plan), evaluate `f` per sample through the
   certified engine, report `ȳ, s(y), s(y)/√M`, percentiles P5/P50/P95, interval `[P2.5,P97.5]`;
   agreement check vs analytic `u_c` is statistical (see §Numerical Specification), never exact.
9. **Significant figures** (O9, GUM §7 view): round `U` to 2 significant digits (1 digit iff leading
   digit is 1 and second-digit test per JCGM 100 §7.2.2 — fixed rule, no heuristics), then round `y`
   to the decade of the rounded `U`. Pure string-level view; stored values untouched.
10. **Traceability** (O10, data): calibration DAG `node = {quantity, value, u, k, p, ν_eff, unit,
    procedure, standard_id, digest(parent…)}`; leaf standards are declared (data) with `standard_id`;
    chain digest = `sha256` over sorted children; broken link → `INCONSISTENT`, never silent.

Iteration inventory: GUM analytic path is **closed-form** (no iteration); iterative sub-kernels are
wrapped, with frozen Criteria: t-quantile Newton `|dt| < 10⁻¹²`, ≤ 60 iters, else `DIVERGED`;
Jacobi PSD `50 sweeps / 10⁻¹⁵` (wrapped); FD is 2 evaluations, no loop. MC “convergence” is
statistical (`s(y)/√M` reported; `MAX_MC_ITERATIONS=10000` inherited budget).

## Numerical Specification

- **Types**: `Decimal` I/O everywhere; `int` seeds/counts; dof canonical `float("inf")` internally
  (wrapped legacy) serialised as `"inf"`; `bool` never accepted where `Decimal` expected.
- **Contexts**: circuit solves reuse certified contexts (F8-H `prec=80`, F8-J/F8-L/F8-M/lab `prec=50`
  explicit); metrology views run under explicit `lab_context`-equivalent (fresh, no ambient reliance).
- **Constants**: `√3/√6` via `Decimal(str(math.sqrt(·)))` at boundary (wrapped legacy, documented);
  `k` rounded to 6 decimals at the wrapped boundary (`Decimal(str(round(k,6)))`) — preserved for
  F7-B7 bit-identity, and O9 applies its own display rounding afterwards (no double-rounding of stored `U`).
- **Conversions**: `Decimal(str(v))` ingress only; `float()` confined to wrapped kernels
  (`sqrt`, t-quantile, Jacobi, W-S, `rel_pct`); `Decimal↔float` never implicit; complex never enters
  variance algebra.
- **Overflow/underflow/NaN/Inf**: non-finite `Decimal` ingress → `INVALID`; `total_var<0` →
  `NUMERIC_ERROR`; float-kernel NaN/Inf → `NUMERIC_ERROR` (never propagated); `u=0 ∀i` → `u_c=0`,
  `ν_eff=∞`, `U=0` (exact, tested).
- **Tolerances** (each justified): Q1 circuit (`RTOL=1e-9/ATOL=1e-12/STOL=1e-12/50/10`, frozen —
  inherits six phase certificates); FD step `max(|x|·1e-6,1e-9)` (relative-dominated, absolute floor
  for `x≈0`; matches F8-M oracle `<1e-4`); PSD `tol=1e-7` (rejects truly indefinite, tolerates Jacobi
  roundoff — F7-B7 certified); t-Newton `1e-12/60` (far below `k`-6dp display); Jacobi `50/1e-15`
  (symmetric-stable, certified); MC-vs-analytic agreement `|u_MC−u_c|/u_c ≤ 5%` for `M ≥ 10⁴`
  (statistical `1/√M` scaling: `M=10⁴ → ~1%` sampling noise; 5% is a 5σ-guard, mismatch → diagnostic
  flag, never silent pass); budget `%` display `round(·,4)` (display only).

## Error Model

States: `COMPLETED | COMPLETED_WITH_FAILURES | INVALID | UNSUPPORTED | SINGULAR | DIVERGED |
MAX_ITERATIONS | NUMERIC_ERROR | INCONSISTENT | SOLVER_FAILURE`. Wrapped engine statuses pass through
verbatim in `engine_status` (e.g. F8 `SINGULAR_JACOBIAN`, MC `FAILED` samples recorded, never clamped).
`INVALID` = bad ingress (empty inputs, `n<2` Type A, `a<0`, `U<0`, `k≤0`, `p∉(0,1)`, `ν≤0`, non-finite,
dimension mismatch, unknown unit, `N>budget`); `UNSUPPORTED` = complex variance, non-ideal instrument
physics, nonlinear AC sweep, topology edit, `Phi=0∧Gamma>0`-style inherited rejections;
`SINGULAR` = correlation non-PSD (`min eig < −1e-7`); `DIVERGED` = t-quantile/Jacobi non-convergence or
`total_var<0`-adjacent overflow; `NUMERIC_ERROR` = negative variance/NaN/Inf; `INCONSISTENT` =
digest mismatch / broken traceability link / version mismatch on replay. Invalid-input vs
no-solution vs non-convergence are never conflated.

## Invariants

KCL/KVL/Tellegen on every underlying circuit solve (inherited); `ΣI=0` per device; Jacobian
column/row-sum 0 (certified extractors, FD-verified `<1e-4`); variance non-negativity
(`u_c² ≥ 0` asserted before sqrt); PSD symmetry + unit diagonal + `r∈[−1,1]`; dimensional
consistency (`V/Ω=A`, `V·A=W`, `V+A` rejected, evaluator `Quantity→Quantity`); insertion-order
invariance (sorted names/keys); immutability (frozen dataclasses, failed ops return identical session);
content-addressing (`exp-<digest16>`, labels excluded); no wall-clock/UUID in digests
(F8-J `provenance.timestamp` scrubbed as in F8-N); budget shares sum to 100% within display rounding.

## Dimensional Analysis

All GUM equations carry units via F6: `c_i: [Y]/[X_i]`; `c_i·u_i: [Y]`; `u_c²: [Y]²`; `k,ν,r`: dimensionless
(explicitly documented); `U: [Y]`; Type B `a: [X]`, `U/k: [X]`. Checks: `V/Ω=A`, `V·A=W` pass;
`V+A`, `mm+s`, `1mm+1s`, `1m+100mm→1.1m` behave per F7-B7 closure; `output_unit` mismatch →
`UnitError`; scale-compatible mismatch converts exactly (`100mm→0.1m`). `dB/rad/deg/%` are labels on
dimensionless (F8-N precedent). `Gamma`-style dimensionless magnitudes documented where reused.

## Convergence

Analytic GUM: closed-form, no convergence question. Wrapped iterators: t-quantile Newton
(`Hill`-corrected normal start, PDF-guarded step, `|dt|<1e-12`, 60 iters → `DIVERGED`);
Jacobi (50 sweeps, `10⁻¹⁵` → wrapped `DIVERGED`); Newton circuit solves (Q1, per-step, inherited).
MC: no deterministic convergence; reports `s/√M` + percentiles; `M` capped by inherited budget;
stagnation (`s=0`) → exact degenerate interval, flagged. Every path returns a terminal status —
no silent plausible numbers.

## Stability

`exp/lgamma/log` confined to float t-kernel (inputs bounded: `p∈(0,1)`, `ν>0`; guards precede calls);
`sqrt` of negative → `NUMERIC_ERROR` before kernel; division by `x_j=0` in quotient ANALYTIC pattern
→ falls back to NUMERICAL FD (specified, tested); near-zero `total_var` → exact-zero branch;
`u=0` rows contribute 0% (no `0/0`); large-`N` budgets bounded by `MAX_METROLOGY_INPUTS`;
ill-conditioned correlation (`eig≈0⁻`) → `SINGULAR` below `-1e-7`, accepted above (documented);
`k` display 6dp bounds string growth; CSV/JSON size-guarded (`MAX_SERIALIZED=64MiB` inherited).

## Determinism

`sames entradas + misma configuración + misma versión = mismo resultado`: sorted iteration,
zero-vector starts, required integer seeds (`Random(seed)` → 64-bit sub-seeds per
`(iter, sorted addr)` per F8-M plan), exact `Decimal(str)` ingress, `getrandbits(53)/2⁵³` uniform +
Decimal Box–Muller (wrapped F8-M path), no clock/uuid/locale/parallelism in digests, canonical JSON
(sort_keys, `str()` Decimals per F8-N D-R1 — `normalize()` forbidden), `sha256(tag‖0x00‖canonical)`.
Triple-run digest equality + insertion-order invariance are certification tests.

## Security

New code: zero `eval/exec/compile(builtin)/__import__/getattr/setattr/open/subprocess/pickle/marshal/
importlib/socket/urllib/numpy/scipy/math`; `re.compile` explicitly distinguished from builtin
`compile()` in reviews/tests (F8-N N-091 precedent: `getattr` forbidden in new code; frozen-dataclass
`object.__setattr__` is the sole allowlisted use, confined to `__post_init__`); equation path uses the
safe recursive parser (no expression strings executed); evaluator callables are typed
`Quantity→Quantity` (dimensional bypass closed per F7-B7 §9); deserialisation is size-guarded,
schema-validated (`f8o-metrology/1`), digest-recomputed, class-name-free (no pickle/YAML tags);
hostile tests cover malformed inputs, extreme values, wrong dimensions, singular correlations,
tampered serialisations, out-of-range params, invalid seeds, contradictory configs. Wrapped `gum.py`
float kernels are audited as listed in §Repository Evidence(4) — no new dynamic surface.

## Architecture

```text
domain
  ↓
engineering
  ↓
metrology/            NEW (F8-O, thin integration layer)
  ├─ o1_inputs.py     Type A/B constructors → InputQuantity (wrap gum helpers)
  ├─ o2_propagate.py  analytic budgets → gum.evaluate_gum (wrap, no math copy)
  ├─ o3_circuit.py    circuit sensitivities/MC → F8-M (PARAM_REGISTRY, warm-start preserved)
  ├─ o4_significant.pyfigures formatter (NEW, pure view)
  ├─ o5_traceability.py chain DAG + digests (NEW, data only)
  ├─ report.py        MetrologyReport + f8o-metrology/1 serialisation + replay/compare
  └─ (engines: mna/ac/lab/gum/units/equations — untouched, dependidos, nunca dependientes)
```

Dependency direction strictly downward: `metrology → {lab, mna.analysis, mna.sensitivity, gum,
units, equations, math}`; `lab/`, engines never import `metrology`. Lives in
`domain/engineering/` (satisfies `test_architecture.py`: no UI/application/infrastructure imports,
stdlib-only). No engine→lab, solver→orchestration, domain→UI/filesystem/network edges.

## API Contract

- `MetrologyInput(name, nominal: Decimal, unit: str, u: Decimal, type: A|B, distribution, dof, source)`
  pre: finite nominal, `u ≥ 0`, known unit, `dof ∈ (0,∞]`; post: frozen `InputQuantity`-compatible.
- `build_model(measurand, equation|evaluator, output_unit, input_units)` pre: exactly one of
  equation/evaluator; dimensional evaluator `Quantity→Quantity`; post: closed `MeasurementModel`
  (wrapped). Complexity O(L) parse.
- `evaluate_budget(model, inputs, correlation?, p=0.95|explicit_k?) → UncertaintyBudget+GUMResult`
  pre: `1≤N≤64`, PSD correlations, `p∈(0,1)`; post: `u_c,U,k,ν_eff`, rows with `c_i/method/contribution/%`,
  provenance+digest; errors per §Error Model. Complexity O(N² + E·C_FD).
- `evaluate_circuit_budget(circuit, param_sweep|observable, …)` pre: params ∈ F8-M `PARAM_REGISTRY`,
  circuit solves CONVERGED; post: wrapped F8-M sensitivities + GUM budget; non-converged points recorded
  (`COMPLETED_WITH_FAILURES`), never hidden. Complexity = underlying solves + O(N²).
- `propagate_monte_carlo(…, seed!, M≤10000)` pre: seed required `int≥0`; post: `ȳ,s,P5/P50/P95`,
  seed plan + digest; invalid samples → `FAILED` recorded. Complexity O(M·solve).
- `format_significant(y, U) → (y_str, U_str)` pre: finite; post: GUM-§7 strings (view only). O(1).
- `trace(chain) → ChainDigest` pre: DAG acyclic, links resolvable; post: digest or `INCONSISTENT`. O(V+E).
- `to_document/from_document/replay/compare` pre: schema `f8o-metrology/1`, size ≤ 64MiB;
  post: canonical doc / `EQUIVALENT|RESULT_DIFFERS|VERSION_MISMATCH|SCHEMA_MISMATCH|INVALID_SERIALIZATION`.
  All deterministic; no API takes floats, paths, sockets, or callbacks.

## Resource Limits

| Limit | Value | Justification |
|:---|:---|:---|
| `MAX_METROLOGY_INPUTS` | 64 | `u_c²` is O(N²) with Decimal; matches F8-H scaling ceiling N=64 |
| `MAX_CORRELATION_PAIRS` | 2016 (=C(64,2)) | derived, never stored dense beyond pairs |
| `MAX_MC_ITERATIONS` | 10000 | inherits F8-M (statistical `1/√M≈1%` at cap) |
| `MAX_SWEEP_POINTS` | 2000 | inherits F8-M (budgets per point) |
| `MAX_WORST_PARAMS` | 10 | inherits F8-M (`2^k` corners) |
| `MAX_TRANSIENT_STEPS` | 100000 | inherits F8-L (waveform-sample Type A ceiling) |
| `MAX_EXPERIMENTS/RUNS/MEAS` | 256/1024/64 | inherits F8-N (report fan-out) |
| `MAX_SERIALIZED` | 64 MiB | inherits F8-N (DoS guard) |
| t-quantile / Jacobi | 60 iters / 50 sweeps | wrapped certified caps |
| Budgets | rejections, never truncation | overflow is explicit error |

## Validation Matrix

Types: `UNIT, ANALYTICAL, NUMERICAL, PROPERTY, BOUNDARY, ERROR, SECURITY, DETERMINISM,
SERIALIZATION, REGRESSION, PERFORMANCE`. References: `ANALÍTICA` (closed forms) preferred over
`NUMÉRICA INDEPENDIENTE` (hand calc / high-precision re-evaluation); `PROPIEDAD`; `REGRESIÓN`.

| ID | Objetivo | Entrada | Esperado / referencia / tolerancia / invariante |
|:---|:---|:---|:---|
| O-001 | Type A canónico | obs `[10.0×5]` | `x̄=10`, `u=0`, `ν=4` ANALÍTICA exacta |
| O-002 | Type A disperso | obs `[1,2,3,4,5]` | `x̄=3`, `s/√5` rel `<1e-12` vs cálculo manual Decimal |
| O-003 | Type A `n<2` | 1 obs | `INVALID` determinista |
| O-004 | Rectangular | `a=1` | `1/√3` rel `<1e-12`, `ν=∞` |
| O-005 | Triangular | `a=1` | `1/√6` rel `<1e-12` |
| O-006 | Normal `U/k` | `U=2,k=2` | `u=1` exacto; `k≤0` → `INVALID` |
| O-007 | Half-width negativo | `a=−1` | `INVALID` |
| O-008 | Suma analítica | `Y=X1+X2` | `c=(1,1)` ANALYTIC |
| O-009 | Producto | `Y=X1·X2` | `c=(x2,x1)` ANALYTIC |
| O-010 | Cociente | `Y=X1/X2`, `X2≠0` | `c=(1/x2,−x1/x2²)` ANALYTIC |
| O-011 | Cociente `X2=0` | `x2=0` | fallback NUMERICAL, sin excepción |
| O-012 | Divisor resistivo | `Vin·R2/(R1+R2)` | `c` cerradas rel `<1e-30` ANALÍTICA |
| O-013 | FD fallback | `Y=exp(X)`-vía-ecuación | `c≈exp(x)` rel `<1e-4` NUMÉRICA INDEPENDIENTE |
| O-014 | Combinada incorrelada | 2 entradas | `u_c=√Σ(c·u)²` exacto a display |
| O-015 | Correlación `r=1` | `r12=1` | `u_c=|c1u1+c2u2|` exacto |
| O-016 | Correlación `r=−1` | `r12=−1` | cancelación exacta `u_c=|c1u1−c2u2|` |
| O-017 | PSD válida 3×3 | matriz equicorr `0.5` | eigs `≥−1e-7`, acepta |
| O-018 | No-PSD | `r12=1,r13=1,r23=−1` | `SINGULAR` |
| O-019 | Asimetría | `r12≠r21` | `INVALID` en construcción |
| O-020 | `|r|>1` | `r=1.5` | `INVALID` |
| O-021 | Welch–Satterthwaite | mixto `ν=(5,∞)` | fórmula cerrada rel `<1e-9` ANALÍTICA |
| O-022 | Todo `∞` | solo B | `ν_eff=∞`, `k`=normal `1.959964…→1.959964` (6dp) |
| O-023 | `k` p=0.95 `ν=5` | tabla G.2 | `k=2.570582` ±1e-6 NUMÉRICA (JCGM) |
| O-024 | `explicit_k=2` | — | `explicit_user`, `U=2u_c` exacto |
| O-025 | `explicit_k≤0/NaN/Inf` | — | `INVALID` (4 subcasos) |
| O-026 | Varianza negativa | correlación patológica | `NUMERIC_ERROR`, nunca clamp |
| O-027 | `u=0 ∀i` | ceros | `u_c=U=0`, `ν=∞` exacto |
| O-028 | Dimensiones `V/Ω=A` | modelo | Quantity OK |
| O-029 | `V+A` | modelo | `UnitError→INVALID` |
| O-030 | Evaluator `Decimal` con unidades | bypass auditado | `UnitError→INVALID` (regresión F7-B7 §9) |
| O-031 | Evaluator `Quantity→Quantity` | `V/R` | `0.01A` exacto |
| O-032 | Unidad desconocida | `parse_unit` | `UnitError→INVALID` |
| O-033 | Ecuación sin eval | AST | 0 `eval/exec/compile` SECURITY |
| O-034 | Circuito: divisor R | F8-B + M4 | `c` cerradas `<1e-40` ANALÍTICA |
| O-035 | Circuito: diodo Is | F8-H + M4 | FD `<1e-4` NUMÉRICA |
| O-036 | Circuito: BJT β | F8-I + M4 | FD `<1e-4` |
| O-037 | Circuito: MOS Kp | F8-K + M4 | FD `<1e-4` |
| O-038 | Circuito: AC `\|H\|` | F8-J/M4-AC | `d\|H\|` cadena `<1e-30` |
| O-039 | MC reproduce analítica | `M=10⁴`, seed 42 | `\|u_MC−u_c\|/u_c ≤ 5%` NUMÉRICA (estadística) |
| O-040 | MC determinismo | seed 42 ×3 | digests idénticos DETERMINISM |
| O-041 | MC seed distinta | 42 vs 43 | digests distintos |
| O-042 | MC sin seed | — | `INVALID` |
| O-043 | Cifras: `U=0.0231` | — | `U→0.023`, `y` al siglo correspondiente (vista) |
| O-044 | Cifras: leading-1 | `U=0.14…` | 2 dígitos (regla JCGM fija) |
| O-045 | Trazabilidad lineal | cadena 3 eslabones | digest estable |
| O-046 | Eslabón roto | id desconocido | `INCONSISTENT` |
| O-047 | Ciclo | DAG cíclica | `INVALID` |
| O-048 | Presupuesto % | cualquiera | `Σ% = 100 ± 0.01` (display) PROPIEDAD |
| O-049 | Orden inserción | permutado | mismo digest PROPIEDAD |
| O-050 | Triple run | cualquiera | 3 digests iguales DETERMINISM |
| O-051 | Serialización canónica | doc | `Decimal str()`, `inf→"inf"`, floats rechazados SERIALIZATION |
| O-052 | Replay misma versión | doc | `EQUIVALENT` |
| O-053 | Versión distinta | doc alterado | `VERSION_MISMATCH` |
| O-054 | Documento manipulado | digest roto | `INVALID_SERIALIZATION`/`RESULT_DIFFERS` |
| O-055 | Límite N=65 | 65 entradas | `INVALID` (presupuesto) BOUNDARY |
| O-056 | Cero/uno/negativo/extremos | batería | tabla §14 del mandato ERROR/BOUNDARY |
| O-057 | Hostil: NaN/Inf/dims | batería | fallo explícito determinista SECURITY |
| O-058 | `re.compile` vs `compile` | revisión | builtin `compile` ausente (AST) SECURITY |
| O-059 | Virada F8-N | sesión lab | `Scalar/Waveform` → GUM sin re-solve PROPIEDAD |
| O-060 | No-duplicación | grep | 0 segundos motores GUM/MC/sensibilidad REGRESSION-estática |
| O-061 |bench determinista | N=64 | tiempos registrados, sin asserts pared PERFORMANCE |
| O-062…O-064 | Regresión F7-B7/F6/arquitectura | suites | 79 + units + arch verdes |

Más: regresiones F8-H (69), F8-I (74+33), F8-J (29), F8-K (110), F8-L (58), F8-M (87),
F8-N (125) vía `pytest -q` global en Prompt 2 (0 fallos, 0 skips injustificados).

## Regression Strategy

Prompt 2 ejecuta, en orden: `tests/test_f7b7_gum.py` (79) → `tests/test_f8h…f8n*` (H69/I/MNA41+phys33/J29+bench/K110/
L58/M87/N125) → nueva suite `tests/test_f8o_metrology.py` (O-001…O-064+) → `test_architecture.py` →
`pytest -q` global. Criterio: 0 failed, 0 unjustified skips, 0 digest mismatches, 0 float-literales en
código nuevo (AST), `mna/ac/circuit.py/units.py/equations.py/gum.py` byte-idénticos salvo lo que Prompt 2
justifique (nada previsto: F8-O solo añade `metrology/` + tests).

## Risks

| Riesgo | Prob. | Impacto | Detección | Mitigación |
|:---|:---:|:---:|:---|:---|
| Deriva float de kernels envueltos (`sqrt`, t, Jacobi, W-S) | M | M | O-004/005/022/023 con cotas estrictas | Frontera documentada + cotas; sin reimplementación en esta fase |
| `round(k,6)` heredado | B | B | O-022/023 | Preservado por bit-identidad F7-B7; O9 redondea la vista después |
| MC vs analítica: falsa alarma por ruido | M | B | O-039 con 5% justificado `1/√M` | Semilla fija + banda estadística, no igualdad exacta |
| Sensibilidad numérica en singularidades (`X2=0`) | M | M | O-011 | Fallback FD especificado + test |
| Correlación casi-singular aceptada | B | M | O-017/018 | `tol=1e-7` certificada; `SINGULAR` bajo el umbral |
| Duplicación accidental de GUM/MC | B | A | O-060 + revisión imports | Allowlist de imports; `simulation.py` prohibido |
| Unidad mal declarada por usuario | M | A | O-028…032 | Contrato `Quantity→Quantity` + `UnitError→INVALID` |
| DoF `inf` serializado como float | B | M | O-051 | Canónico `"inf"` string, floats rechazados |
| Regresión F8-H…N | B | A | suites + `pytest -q` | Sin tocar motores; solo añade paquete |
| `eval()` externo | — | — | roadmap:207 | Resuelto por diseño (D-R1): no se usa el repo externo |

## Open Questions

Ninguna bloqueante. Registradas como decisiones cerradas en este diseño (no `OPEN QUESTION` vivo):
- Q1 ¿De dónde viene la calculadora GUM? → **Cerrada**: `gum.py` local F7-B7 (D-R1), no el repo externo.
- Q2 ¿Decimal puro o float heredado? → **Cerrada**: envolver con frontera justificada (D-R2); la
  reescritura Decimal del núcleo t/Jacobi queda como trabajo futuro explícito, no como deuda oculta.
- Q3 ¿MC propio? → **Cerrada**: componer F8-M nativo con semilla obligatoria.
- Q4 ¿Dónde vive? → **Cerrada**: `domain/engineering/metrology/`, solo depende hacia abajo.

## Deviations

- **D-R1 (resuelve el “bloqueado hasta sustituir `eval()`”)**: el roadmap:207 condiciona F8-O a la
  calculadora del repo externo `Conversor-HTML-A-MD`. Este diseño NO importa ese repo: reutiliza el
  motor local F7-B7 (`gum.py` + `equations.py` sin `eval`), que ya cumple la condición (parser propio,
  prohibición `eval/exec` certificada en F7-B7 y F6). El bloqueo externo queda sin objeto para F8-O.
- **D-R2 (float heredado acotado)**: `gum.py` conserva núcleos float (`sqrt`, t-Student, Jacobi, W-S,
  `round(k,6)`, dof `inf`). F8-O los envuelve sin copiarlos; la frontera está auditada en
  §Repository Evidence(4) y acotada por O-004/005/022/023/039. Reescribirlos en `Decimal` sería un
  segundo motor GUM (violaría no-duplicación) y queda como fase futura explícita.
- **D-R3 (digests)**: se hereda F8-N D-R1 — `str()` (no `normalize()`) para `Decimal` de motores en
  digests; `"inf"` canónico para dof infinito; sin timestamps/UUIDs en digests.

## Final Verdict

Las diez preguntas del mandato quedan respondidas: (1) ecuaciones en §Mathematical Specification;
(2) unidades en §Dimensional Analysis; (3) invariantes en §Invariants; (4) errores/tolerancias en
§Numerical Specification + §Error Model; (5) demostración en §Validation Matrix; (6) fallos en
§Error Model; (7) reproducibilidad en §Determinism; (8) reutilización en §Repository Evidence +
§Architecture (tabla REUTILIZAR/ENVOLVER/NUEVA/NO SOPORTADA en Scope/Non-Scope); (9) límites en
§Resource Limits; (10) test por garantía en §Validation Matrix. Alcance inequívoco, arquitectura
cerrada, sin preguntas críticas abiertas.

F8-O DESIGN READY
