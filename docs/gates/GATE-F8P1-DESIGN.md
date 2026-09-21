# F8-P1 Design Gate

Design gate for **F8-P1 — Sistemas y Control (SISO LTI)**. Documentation
only: no code under `src/` was created or modified, no tests were written,
no engine was altered. The only output of this phase is this file plus one
local commit (no push).

## Baseline

- Repository `Damaga2005/AcademicCore`, branch `main`, baseline **`56136f7`**
  (`feat(engineering): certify F8-O metrology layer`), `HEAD == origin/main`
  (verified after `git fetch` at audit time).
- Certified at baseline: F0–F7 (incl. F7-B7 GUM, 79 tests), F8-A … F8-O
  (gates on disk through `GATE-F8O.md`; roadmap §6.1 lists F8-O CERTIFICADO
  and marks **F8-P1 (NEXT)** per §5.1).
- Working tree clean at audit time (`git status --short --branch` →
  `## main...origin/main`, no entries).

## Scope

F8-P1 is the **SISO linear time-invariant control layer** over the
certified engines. It adds **no circuit solver, no Bode engine, no
transient integrator, no sampler, no GUM math**. It adds:

| ID | Capability |
|:---|:---|
| C1 | Polynomial core: `Decimal`/`DecimalComplex` coefficient vectors, Horner evaluation, exact TF algebra support |
| C2 | Rational transfer function `H(s) = N(s)/D(s)` (SISO, proper) + series/parallel/feedback algebra (exact) |
| C3 | ZPK form + conversions TF ↔ ZPK ↔ state-space (controllable canonical, exact) |
| C4 | Pole/zero computation (Durand–Kerner in `DecimalComplex` with explicit contract) + Routh–Hurwitz exact cross-check |
| C5 | Root locus: Evans angle/magnitude conditions, real-axis segments, asymptotes, breakaway points, jω-axis crossings |
| C6 | Frequency-domain margins: gain/phase/delay margins over certified Bode (bisection refinement, never table interpolation) |
| C7 | PID compensators (parallel/series/ideal forms as TFs) + Ziegler–Nichols tuning via ultimate gain |
| C8 | State-space `(A,B,C,D)`: conversions, controllability/observability exact rank, `C(sI−A)⁻¹B+D` identity |
| C9 | Analytic step/impulse responses (partial fractions, real-signal pairing) cross-checked vs F8-L transient |
| C10 | Canonical serialization `f8p1-control/1` + digests + replay/compare (F8-N/F8-O pattern) |

## Non-Scope

| Item | Reason | Future home |
|:---|:---|:---|
| MIMO systems | Needs matrix-Fraction machinery; unbounded scope | later control phase |
| Nonlinear control (saturation, anti-windup, describing functions) | No certified saturation model; would fake physics | future nonlinear phase |
| Time delays / Padé approximants | No delay engine; delay *margin* (seconds) is still reported | future |
| Sampled-data / Z-transform / FIR/IIR | Explicitly F8-P2 DSP per roadmap:209 | F8-P2 |
| S-parameters / Smith chart / RF | Explicitly F8-P3 per roadmap:210 | F8-P3 |
| Optimal/adaptive/robust control | Needs machinery far beyond SISO LTI | never in P1 |
| New Bode/sweep/transient/sampler/GUM math | Certified in F8-D5/D6, F8-L, F8-M, F7-B7 | reused, never rewritten |
| Plots/GUI/hardware | Domain stays UI/hardware-free (`test_architecture.py`) | presentation layer |

## Repository Evidence

1. **Git**: `main`, `HEAD == origin/main == 56136f7`; log head `56136f7`
   (F8-O certification), `1fbfc23` (F8-O design gate), `dd806eb` (F8-N).
   Remote `origin https://github.com/Damaga2005/AcademicCore.git`.
2. **F8-P1 definition** (roadmap only; zero `src/`/`tests/` hits for
   PID/locus/state-space/FFT):
   - `ROADMAP.md:169`: `F8-P1 Sistemas y Control [7º] (NEXT)`.
   - `ROADMAP.md:208`: deps `F8-D6 (Bode ya certificado)`; scope
     “Función de transferencia, Bode, lugar de raíces, PID, espacio de
     estados”.
   - `ROADMAP.md:270`: F8-O certified, **F8-P1 (NEXT)**.
3. **Explicit boundary markers** (the certified code says what it is not):
   - `ac/response.py:26`: “no poles/zeros — the H tables produced here are
     their future input”.
   - `ac/bode.py:24`: “resonance verdicts, Q, poles/zeros, filters, Bode
     plots: NOT HERE”.
   - `TransferFunction` (`response.py:98-107`) is a *single-frequency
     phasor ratio* (endpoints + one phasor), not a rational `H(s)`.
4. **Reuse surface (audited signatures)**:
   - F8-D5: `frequency_response(circuit, definition)` → per-frequency
     certified solves; `linear_frequencies`, `TransferFunction`,
     `network_transfer`/`analyze_transfer`.
   - F8-D6: `analyze_bode(sweep)`, `magnitude_db`, `unwrap_phases`,
     `half_power_threshold_db`, `crossing_brackets` (brackets never
     interpolated), `threshold_bands`, `observed_extrema`,
     `canonical_frequency_key`.
   - F8-E/F/G: `E/G/H/F` dependent sources + `CircularControlError`;
     nullor op-amp; Z/Y/H/ABCD two-ports.
   - F8-L: `solve_transient(circuit, TransientConfig)` (BE/TR/BDF2, LTE
     adaptive, `MAX_TRANSIENT_STEPS = 100000`) — step-response oracle.
   - F8-M: `solve_dc/ac_sensitivity`, `run_monte_carlo_native`
     (seed-required), closed `PARAM_REGISTRY` — gain-sweep/margin
     robustness reuse.
   - F8-N: `Scalar/Waveform`, `sha256(tag‖0x00‖canonical)` digests,
     session/report/replay pattern (N-110: no non-lab module imports
     `lab/` — P1 follows the F8-O structural precedent).
   - F8-O: `evaluate_budget`, `format_result`, `TraceChain`,
     `MetrologyReport` — parametric margin uncertainty (ADAPT).
   - Math: `RationalComplex` (exact `Fraction` complex),
     `math.linsolve.solve` (HP), `decimal_sqrt/sin/cos/pi`,
     `decimal_log10/ln10`, `DecimalComplex` (incl. `modulus()`),
     `Quantity`/`parse_unit` (Hz, s, dimensionless dB/rad/deg labels),
     safe `equations.py` (no eval).
   - `gum.py` Jacobi eigensolver handles **symmetric** matrices only —
     general pole computation is genuinely NEW (no duplication).
5. **No-duplication grep**: no `pole/zero/PID/locus/state-space/FFT/
   margin/Nyquist/Padé/ Ackermann/Lyapunov` solvers in `src/`; `TODO/
   FIXME` only in unrelated tracks; `models.py` ideal placeholders
   superseded by certified extractors.

## Motivation

Control synthesis is the first certified consumer of the AC/transient
stack that reasons about *families* of closed-loop behaviours (locus,
margins, PID tables) rather than single solves. The roadmap orders it
first among the P-phases because F8-P2 (DSP) needs P1 transfer
vocabulary, F8-P3 needs frequency-domain maturity, and F8-P5 integrates
P1…P4. Every P1 computation bottoms out in certified solves; P1 itself
contributes only the LTI-rational mathematics that the repo provably
lacks (§Repository Evidence 3, 5).

## Existing Infrastructure

See reuse surface above. Structural rule inherited: `control/` may import
`ac/`, `mna.*`, `math.*`, `units`, `gum` (Jacobi-symmetric only),
`metrology` (envelope reuse); it may **not** import `lab/` (N-110),
`simulation.py` (float world), UI/application/infrastructure, or any
network/filesystem/process module.

## Mathematical Specification

### Domain

- **Objects**: SISO LTI systems. `H(s) = N(s)/D(s)`, `N,D` real
  coefficient polynomials (`Decimal`, finite), `deg D = n ≥ 1`,
  `deg N = m ≤ n` (proper; `m > n` → `INVALID`). State-space
  `(A,B,C,D)` real `Decimal` matrices, `A: n×n`, `n ≥ 1`.
- **Variables**: `s ∈ ℂ` (Laplace; evaluated as `DecimalComplex`),
  `ω ∈ ℝ_{>0}` (Hz→rad/s via `2π`, certified trig), loop gain
  `K ∈ ℝ_{>0}` (locus parameter), PID gains `(Kp,Ki,Kd)` real.
- **Units**: `H` dimensionless-per-endpoint (V/V, A/A, V/A, A/V carried
  from the originating `TransferKind`); `s, ω`: `1/s`, `Hz`; PID gains
  carry `[u_out]/[e]` powers; time responses carry endpoint units via
  `Quantity`. dB/rad/deg are labels on dimensionless (F8-N precedent).
- **Representation**: polynomials as coefficient tuples (descending),
  exact `Decimal`; complex arithmetic as `DecimalComplex`; exact side
  computations as `Fraction`/`RationalComplex` where specified.

### Core definitions

1. **Transfer evaluation** (Horner, exact, no iteration):
   `H(s) = (Σ_{i=0}^{m} b_i s^{m-i}) / (Σ_{i=0}^{n} a_i s^{n-i})`,
   `D(s) = 0` → `SINGULAR` (pole evaluation), never Inf-propagated.
2. **TF algebra** (exact coefficient arithmetic): series
   `H = H1·H2` (convolution); parallel `H = H1+H2` (common denominator);
   feedback `H_cl = H_fwd / (1 + H_fwd·H_ret)` with `1+L = 0` check
   (algebraic loop at the evaluation point → `SINGULAR`).
3. **ZPK**: `H(s) = k·Π(s−z_i)/Π(s−p_j)`; conversions TF→ZPK via the
   pole core (§Convergence), ZPK→TF exact expansion.
4. **Root locus** (Evans): branches satisfy `∠L(s) = ±180°·(2q+1)`
   (negative feedback; `0°` form explicitly tagged if used) and
   `|K| = 1/|L(s)|`, `L(s)` the loop TF. Real-axis segments, asymptote
   angles `φ_q = ±180°(2q+1)/(n−m)`, centroid
   `σ_c = (Σp − Σz)/(n−m)`, breakaway `dK/ds = 0` on the real axis,
   jω crossings with gain (Routh cross-check, §Analytical).
5. **Routh–Hurwitz** (exact `Fraction` table, no iteration): first-column
   sign changes = RHP pole count; auxiliary-polynomial + `d/ds` row for
   zero rows (honest, specified); `ε`-substitution explicitly tagged when
   used. Stability verdict `STABLE/MARGINAL/UNSTABLE`.
6. **Margins** (over certified Bode): gain margin
   `GM = 1/|L(jω_pc)|` at phase-crossover `∠L = −180°`; phase margin
   `PM = 180° + ∠L(jω_gc)` at gain-crossover `|L| = 1`; delay margin
   `T_dm = PM[rad]/ω_gc`. Crossovers located by **bisection refinement
   on certified point evaluations** (each a full `frequency_response`
   solve), never by interpolating stored tables (D6 precedent); bracket
   intervals always reported alongside refined points.
7. **PID**: parallel `C(s) = Kp + Ki/s + Kd·s`, ideal
   `C(s) = Kp(1 + 1/(Ti·s) + Td·s)`, series form; conversions exact.
   Ziegler–Nichols ultimate: `Ku` from Routh jω-row (or locus crossing —
   both specified, cross-checked), `Tu = 2π/ω_u`; classic P/PI/PID table
   (documented constants, not magic).
8. **State-space**: `ẋ = Ax + Bu`, `y = Cx + Du`; TF↔SS via controllable
   canonical form (exact); `H(s) = C(sI−A)⁻¹D… ` i.e.
   `C·adj(sI−A)·B/det(sI−A) + D` with `det`/`adj` in `Decimal`
   (Bareiss exact-integer path on scaled Decimals — specified, tested);
   controllability/observability ranks exact over `Fraction`
   (`Decimal→Fraction` is exact); eigenvalues of `A` via the
   characteristic polynomial + the same pole core (no second eigensolver).
9. **Time responses**: partial-fraction expansion (distinct poles;
   repeated poles via specified multiplicity handling; complex pairs
   combined to real damped sinusoids so outputs stay real);
   `y_step(t)`, `y_impulse(t)` closed forms; metrics (overshoot, peak
   time, 2 % settling, steady-state value via final-value theorem with
   its applicability check `s·Y(s)` pole condition).

## Equations

Pipeline:
`circuit/TF-spec → H(s) → poles/Routh → locus/margins → PID/closed-loop → time response → report`.

- Closed loop: `T(s) = C(s)P(s) / (1 + C(s)P(s))`.
- Sensitivity/complementary: `S = 1/(1+L)`, `T = L/(1+L)`, invariant
  `S + T ≡ 1` (tested identity).
- Second-order canonical (prime analytical reference):
  `H(s) = ωn²/(s² + 2ζωn s + ωn²)`, poles
  `−ζωn ± jωn√(1−ζ²)`, overshoot `PO = exp(−πζ/√(1−ζ²))`,
  `t_p = π/(ωn√(1−ζ²))`, `t_s(2%) ≈ 4/(ζωn)` (documented approximation
  with its `ζ ≪ 1` validity band — the only sanctioned “≈”, bounded).
- First-order `K/(τs+1)`: step `K(1−e^{−t/τ})`, bandwidth `1/τ`.

## Invariants

KCL/KVL/Tellegen on underlying solves (inherited); `S+T ≡ 1`;
real-coefficient root pairing (`p ⇒ conj(p)`, real time responses);
pole-count conservation (`n` finite poles counted with multiplicity);
Routh first-column ↔ root-core RHP count agreement; TF↔SS round-trip
identity (`‖H_TF − H_SS‖ = 0` exactly on canonical forms); ZPK↔TF
round-trip; closed-loop characteristic `1+L = 0` on every locus point
(residual-checked); dimensional consistency (`V/Ω=A`, `H` units from
`TransferKind`); insertion-order invariance; immutability; content
addressing; no wall-clock/UUID in digests.

## Dimensional Analysis

| Entrada | Operación | Resultante | Esperada |
|:---|:---|:---|:---|
| `H₁,H₂` (V/V) | serie `·` | V/V | V/V ✓ |
| `H_fwd, H_ret` | `H/(1+L)` | endpoint units | endpoint units ✓ |
| `s` (1/s), `a_i` | Horner | `[H]` | `[H]` ✓ |
| `Kp,Ki,Kd` | `Kp+Ki/s+Kd·s` | `[u]/[e]` | `[u]/[e]` ✓ |
| `ω` (Hz) | `·2π` | rad/s | rad/s ✓ |
| `PM` (rad), `ω_gc` | `/` | s | s (delay margin) ✓ |
| `t` (s), `y` | step | endpoint unit | endpoint unit ✓ |
| dB/rad/deg | display | dimensionless label | ✓ (precedent) |

Incompatible endpoint combinations (e.g. closing a loop around
mismatched units) → `INVALID`. `Quantity` at every boundary.

## Numerical Precision

- `Decimal` working precision **50** (F8-J/F8-L/F8-M/lab precedent);
  `DecimalComplex` for `s`-plane; `Fraction`/`RationalComplex` for exact
  side rails (Routh table, TF↔SS canonical, rank tests).
- `Decimal→Fraction` exact; `float` **forbidden** in the new core
  (no heredity claim: unlike F8-O, no wrapped float kernel is needed —
  DK/Jacobi-symmetric wording does not apply; Jacobi is not reused).
- Constants (`π`, `e`-adjacent) via certified `decimal_pi` etc.; no
  literals beyond exact coefficients.
- Overflow/underflow/NaN/Inf: non-finite ingress → `INVALID`;
  `D(s) = 0` evaluation → `SINGULAR`; DK non-convergence →
  `MAX_ITERATIONS`/`DIVERGED` (never a silent root set).
- Cancellation: near-cancelling pole-zero pairs handled by an explicit
  **cancellation radius** `ρ_cancel` (documented, tested both sides);
  Routh `ε`-rows explicitly tagged; `0/0` forms → `INVALID`/`SINGULAR`,
  never `0`.

## Error Analysis

- `E_a = |x − x_ref|`; `E_r = |x−x_ref|/max(|x_ref|, ε)`,
  `ε = 1e-30` (pole/residual scale; justified: working precision 50 →
  display needs ≤ 12 digits, `ε` sits 18 orders below any tolerance).
- Tolerances: Horner exact (no tol); TF algebra exact (no tol);
  Routh/rank/canonical exact (no tol); DK backward error
  `|p(z)| ≤ 1e-30·(1+‖coeff‖∞)` (justified: 20 orders above `1e-50`
  unit roundoff, 18 below display); locus residual `|1+L| ≤ 1e-24 +
  1e-9·max(1,|L|)` (Q1-family scaling, inherited shape); crossover
  bisection width `≤ 1e-12` relative in `ω` (12 certified digits);
  step-vs-transient agreement `≤ 1 %` (LTE-controlled oracle, F8-L
  precedent band); MC/sweep reuse keeps native tolerances (Q1).
- No invented tolerances: every number above derives from precision 50,
  Q1 precedent, or oracle bands.

## Stability

- Ill-conditioned polynomials (Wilkinson-type): detected via backward
  error + Routh cross-check disagreement → `DIVERGED`/`INCONSISTENT`
  (specified, tested with a documented Wilkinson-like case).
- High relative degree / stiff time scales: step sampling bounded by
  `MAX_TIME_POINTS`; F8-L cross-check flags divergence honestly.
- Division by zero (`D(s)=0`, `1+L=0`, `s=0` in `Ki/s`): `SINGULAR`.
- Extreme `K` (locus tails): asymptotic rules take over by explicit
  degree/centroid formulas; numeric tracing capped by budgets.
- Repeated/jω-axis poles in partial fractions: multiplicity path +
  marginal-stability tagging; final-value theorem gated on its pole
  condition.
- For each: detection → status → behaviour → guarantee (tables in Prompt-2
  implementation, contracts fixed here).

## Convergence

Only iterative kernel: **Durand–Kerner** simultaneous iteration
`z_i ← z_i − p(z_i)/Π_{j≠i}(z_i − z_j)` in `DecimalComplex`.
- Init: deterministic Aberth-style circle packing (specified radii/
  angles, no randomness, no seed needed — determinism by construction).
- Stop: `max|Δz| ≤ 1e-30·(1+max|z|)` → `CONVERGED`; `MAX_DK_ITER`
  (documented, e.g. 500·n) → `MAX_ITERATIONS`; stagnation
  (no `‖Δ‖` decrease over a full window) → `DIVERGED`.
- Post: backward-error gate per root; Routh-count agreement gate.
- Documented as **observed convergence** (linear→quadratic near simple
  roots; known slowdown on multiple roots — the multiplicity path and
  Routh gate exist precisely for this); no theorem claimed.
- All other P1 math is closed-form/exact (Routh, algebra, canonical
  forms, margins bisection — the latter linear-convergent by
  construction on bracketed monotone segments, with bracket fallback).

## Determinism

Same inputs + config + version = same result: sorted iteration, Aberth
init (no RNG anywhere in P1), required seeds only inside reused F8-M MC,
no clock/uuid/locale/parallelism in digests, canonical JSON
(`str()` Decimals per F8-N D-R1, `normalize()` forbidden),
`sha256(tag‖0x00‖canonical)`.

## Reproducibility

Inputs (TF coeffs / circuit + derivation recipe / PID table entry),
config (tolerances inherited Q1 + P1 constants above), engine versions,
seed (only for MC-backed robustness checks), canonical serialization +
digest. No hidden environment dependence.

## Serialization

Schema `f8p1-control/1`: TF/ZPK/SS/locus/margins/PID-response documents;
deterministic, closed, size-guarded (`≤ 64 MiB` inherited bound),
digest-recomputed, tamper-evident; replay states
`EQUIVALENT/RESULT_DIFFERS/VERSION_MISMATCH/SCHEMA_MISMATCH/
INVALID_SERIALIZATION` (F8-N/F8-O vocabulary); no pickle/eval/dynamic
imports/class-name reconstruction.

## Security

New code: 0 `eval/exec/compile(builtin)/__import__/getattr/setattr/open/
subprocess/pickle/marshal/importlib/socket/urllib/numpy/scipy/math`
(`re.compile` distinguished from builtin `compile()` in review/tests);
frozen-dataclass discipline per F8-O (validation-only `__post_init__`,
no `setattr`); equation input only through the safe parser; hostile
tests (malformed TFs, pole-zero pileups, tampered docs, invalid seeds).

## Architecture

```text
domain
  ↓
engineering
  ↓
control/                NEW (F8-P1, SISO LTI layer)
  ├─ poly.py            polynomial core (Horner, exact algebra support, DK roots)
  ├─ tf.py              rational H(s), series/parallel/feedback, ZPK
  ├─ stability.py       Routh–Hurwitz exact + pole inventory
  ├─ locus.py           Evans conditions, asymptotes, breakaway, jω crossings
  ├─ margins.py         GM/PM/Tdm over certified Bode (bisection refinement)
  ├─ pid.py             forms + Z-N tuning + closed-loop formation
  ├─ statespace.py      (A,B,C,D), exact conversions, exact rank tests
  ├─ response.py        analytic step/impulse + metrics (F8-L cross-check)
  └─ report.py          f8p1-control/1 docs + digests + replay/compare
  ↓ (depends downward only)
certified: ac.bode/ac.response, mna.transient, mna.analysis/sensitivity,
           math.*, units, equations(via reuse), gum(Jacobi NOT used),
           metrology(envelope/uncertainty ADAPT)
```

Engines never import `control/`; `control/` never imports `lab/`
(N-110), `simulation.py`, UI/application/infrastructure, or I/O/network.
Import DAG documented above; verified by AST test in Prompt 2.

## API Contract

- `TransferFunctionTF(num, den)` — pre: finite Decimals, `den ≠ 0`,
  `deg den ≥ 1`, `deg num ≤ deg den`; post: frozen proper TF;
  errors `INVALID/SINGULAR`; complexity O(n) eval.
- `series/parallel/feedback(H1, H2)` — exact; post: minimal documented
  normalization (leading-denominator-1); O(n·m).
- `poles(H)/zeros(H)` — post: `DecimalComplex` tuples + method tags
  (`ROUTH count` attached); `DIVERGED/MAX_ITERATIONS` honest.
- `routh(H)` — exact table + `STABLE/MARGINAL/UNSTABLE` + RHP count.
- `locus(L, gains)` — pre: `K > 0` sorted tuple; post: branch points
  with `|1+L| residual ≤ tol`; O(G·n²·iters).
- `margins(L, bode_sweep)` — post: `(GM, ω_pc, PM, ω_gc, T_dm)` +
  bracket intervals + refinement proofs; `UNSUPPORTED` when crossovers
  absent (no fake ∞ dB claims beyond documented convention).
- `pid_parallel/series/ideal(...)`, `ziegler_nichols(Ku, Tu, kind)` —
  documented table constants; post: compensator TF.
- `StateSpace(A,B,C,D)`, `tf_to_ss/ss_to_tf`, `ctrb/obsv_rank` (exact),
  `ss_eigenvalues` (via char-poly + pole core).
- `step_response/impulse_response(H, times)` — real outputs; metrics
  `(PO, t_p, t_s, y_ss)` with applicability tags.
- `to_document/from_document/replay/compare` — schema `f8p1-control/1`.
All deterministic; no floats, paths, sockets, callbacks.

## Error Model

`COMPLETED | COMPLETED_WITH_FAILURES | INVALID | UNSUPPORTED |
SINGULAR | DIVERGED | MAX_ITERATIONS | NUMERIC_ERROR | INCONSISTENT |
SOLVER_FAILURE` (+ serialization `SCHEMA/VERSION_MISMATCH`). Engine
statuses pass through verbatim. Invalid-input vs impossible-problem
(`m>n`, non-PSD-style degeneracy) vs non-converged-algorithm kept
distinct. Missing crossovers → `UNSUPPORTED` (explicit), never `GM = ∞`
silently.

## Resource Limits

| Limit | Value | Justification |
|:---|:---|:---|
| `MAX_TF_DEGREE` | 32 | DK O(n²)/iter at prec 50; 32 keeps worst case seconds-scale |
| `MAX_DK_ITER` | 500·n | linear scaling with system size |
| `MAX_LOCUS_GAINS` | 2000 | inherits F8-M sweep bound |
| `MAX_TIME_POINTS` | 10001 | display-grade + digest-stable trajectories |
| `MAX_TRANSIENT_STEPS` | 100000 | inherits F8-L (oracle ceiling) |
| `MAX_MC_ITERATIONS` | 10000 | inherits F8-M |
| `MAX_SERIALIZED` | 64 MiB | inherits F8-N (DoS guard) |
| Cancellation radius `ρ_cancel` | documented const | pole-zero pileup gate |

Budgets are rejections, never truncations.

## Complexity

Horner O(n); TF algebra O(n·m); DK O(n²·iters) time, O(n) memory;
Routh/rank/canonical O(n³) exact Fraction ops (small n by degree cap);
bisection O(log(1/tol)) certified solves per crossover; locus
O(G·DK); step evaluation O(P·n) per time point; digests O(doc).
Bottleneck: DK at degree 32/prec 50 (bounded, recorded not asserted).

## Validation Matrix

Types: UNIT, ANALYTICAL, NUMERICAL, PROPERTY, BOUNDARY, ERROR, SECURITY,
DETERMINISM, SERIALIZATION, REGRESSION, PERFORMANCE. References:
ANALYTICAL > INDEPENDENT HIGH-PRECISION > PROPERTY > REGRESSION.

| ID | Objetivo | Entrada | Esperado / referencia / tolerancia |
|:---|:---|:---|:---|
| P-001 | TF Horner exact | `1/(s+1)`, `s=j1` | `0.5−j0.5` exacto ANALÍTICA |
| P-002 | Serie/paralelo/feedback | racionales pequeños | coeficientes exactos (Fraction) |
| P-003 | `S+T≡1` | cualquier `L` | identidad exacta PROPIEDAD |
| P-004 | Polos 2.º orden canónico | `ωn,ζ` | `−ζωn±jωn√(1−ζ²)` rel `<1e-12` |
| P-005 | Ceros + ganancia ZPK | `K(s+2)/((s+1)(s+3))` | round-trip exacto |
| P-006 | Routh estable | `(s+1)(s+2)(s+3)` | STABLE, 0 cambios |
| P-007 | Routh inestable | `s³+2s²−s+…` con 2 RHP | UNSTABLE, conteo = núcleo |
| P-008 | Fila cero (auxiliar) | caso con par jω | MARGINAL + frecuencia exacta |
| P-009 | Wilkinson-like | poli. mal condicionado | backward-error gate o DIVERGED honesto |
| P-010 | Eje real del lugar | `K(s+2)/s(s+1)` | segmentos exactos (regla) |
| P-011 | Asíntotas | `n−m=2` | `±90°`, `σ_c` exacto |
| P-012 | Breakaway | ejemplo con `dK/ds=0` cerrado | rel `<1e-9` ANALÍTICA |
| P-013 | Cruce jω + Ku | caso Routh-cruzado | `Ku,ωu` = fila de Routh `<1e-9` |
| P-014 | Residuo `1+L=0` en rama | puntos del locus | `≤ tol` del gate |
| P-015 | GM/PM circuito RC+opamp | barrido certificado | vs `analyze_bode` + bisección `<1e-12` rel ω |
| P-016 | Sin cruce → UNSUPPORTED | `1/(s+1)` GM | estado explícito, sin ∞ falso |
| P-017 | Delay margin | del P-015 | `PM/ω_gc` exacto a display |
| P-018 | Z-N PID | `Ku,Tu` del P-013 | tabla documentada exacta |
| P-019 | Lazo cerrado estable | P+C(s) | Routh STABLE + polos LHP |
| P-020 | SS↔TF round-trip | canónica controlable | identidad exacta |
| P-021 | Rango ctrb/obsv | ejemplos rango pleno/deficiente | exacto (Fraction) |
| P-022 | Autovalores = polos | `A` 2×2/3×3 | acuerdo `<1e-12` |
| P-023 | Escalón 1er orden | `K/(τs+1)` | `K(1−e^{−t/τ})` rel `<1e-9` |
| P-024 | Escalón 2.º orden | canónico `ζ<1` | PO/t_p/t_s vs fórmulas `<1%`/exactas |
| P-025 | Escalón vs F8-L | mismo circuito RC | acuerdo `≤1%` NUMÉRICA |
| P-026 | Impulso + real-valued | pares conjugados | salida real exacta (tipo) |
| P-027 | Final-value gated | polo en origen | teorema bloqueado, estado explícito |
| P-028 | Cancelación `ρ` | par casi-cancelado | ambos lados del gate testeados |
| P-029 | Grado 0/den 0/impropio | batería | INVALID/SINGULAR deterministas |
| P-030 | `K≤0`/gains vacíos | batería | INVALID |
| P-031 | Triple run + orden | cualquiera | 1 digest DETERMINISM |
| P-032 | Serialización/replay | docs | round-trip, tamper, mismatch |
| P-033 | Hostil | NaN/Inf/dims/tamper/semilla | fallo tipado explícito |
| P-034 | AST/seguridad | `control/` | 0 banned, `re.compile`≠`compile()` |
| P-035 | No-duplicación | grep | sin 2.º Bode/solver/sampler/GUM |
| P-036 | Bench | n=32, G=2000, MC | tiempos registrados |
| P-037… | Regresión F7-B7,F8-H…O | suites | verdes (ver estrategia) |

Count derives from coverage (≥37 + regressions); Prompt 2 extends only
with justification.

## Regression Strategy

Prompt 2 runs: F7-B7 (79) → F8-H (69) → F8-I (74) → F8-J (29) → F8-K
(110) → F8-L (58) → F8-M (87) → F8-N (125) → F8-O (70) → new
`tests/test_f8p1_control.py` (P-001…) → `test_architecture.py` →
global `pytest -q` (0 failed, 0 unjustified skips). `mna/ac/lab/gum/
metrology/circuit/units/equations` byte-unchanged (P1 only adds
`control/` + tests).

## Risks

| Riesgo | Prob. | Impacto | Detección | Mitigación |
|:---|:---:|:---:|:---|:---|
| DK lento/diverge en raíces múltiples | M | M | P-009, gates backward+Routh | camino multiplicidad + Routh, estados honestos |
| Wilkinson: raíces sensibles | M | M | P-009 | gate de error + desacuerdo→INCONSISTENT |
| Cancelación polo-cero silenciosa | B | A | P-028 | `ρ_cancel` documentado, ambos lados |
| Bisección sin monotonía | B | M | P-015/016 | brackets siempre; UNSUPPORTED si no hay cruce |
| Duplicar Bode/transient/MC | B | A | P-035 + imports | allowlist; `simulation.py` prohibido |
| Float accidental (hongos `math`) | B | A | P-034 AST | 0-float en núcleo; sin kernels heredados |
| Regresión H→O | B | A | suites + `pytest -q` | solo añade paquete |
| Grado explosivo (coste DK) | B | B | P-036 | `MAX_TF_DEGREE=32`, rechazo explícito |
| Teorema valor-final mal aplicado | B | M | P-027 | gate de aplicabilidad |
| Z-N fuera de validez | B | B | P-018/019 | tabla documentada + verificación Routh |

## Open Questions

Ninguna bloqueante. Decisiones cerradas en este diseño: (Q1) alcance =
roadmap:208 literal (TF/Bode/lugar/PID/SS), sin MIMO ni retardos;
(Q2) raíces = Durand–Kerner DecimalComplex + Routh exacto (sin Jacobi:
solo vale para simétricas); (Q3) cruces = bisección sobre solves
certificados, nunca interpolación de tablas; (Q4) respuesta temporal =
fracciones parciales + oráculo F8-L; (Q5) vive en
`domain/engineering/control/`, sin importar `lab/`.

## Deviations

Ninguna respecto a repositorio (fase greenfield sobre motores
certificados). Respecto al mandato: el alias de vocabulario de replay se
hereda de F8-N/F8-O (`EQUIVALENT/…`); `m>n` es `INVALID` (no “TF
impropia soportada”); el único “≈” sancionado es `t_s ≈ 4/(ζωn)` con
banda de validez documentada.

## Final Verdict

Las diez preguntas del mandato quedan respondidas: (1) ecuaciones en
§Mathematical Specification/§Equations; (2) unidades en §Dimensional
Analysis; (3) invariantes en §Invariants; (4) errores en §Error Analysis;
(5) referencias en §Validation Matrix (ANALYTICAL-first); (6) fallos en
§Error Model; (7) determinismo en §Determinism; (8) reutilización en
§Repository Evidence/§Existing Infrastructure/§Architecture; (9) límites
en §Resource Limits; (10) test por garantía en §Validation Matrix.
Alcance inequívoco (roadmap:208), matemática cerrada, arquitectura
cerrada, sin preguntas críticas abiertas.

F8-P1 DESIGN READY
