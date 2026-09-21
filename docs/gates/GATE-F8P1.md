# F8-P1 Certification Gate

## Baseline

- Repository `Damaga2005/AcademicCore`, branch `main`.
- Design baseline `f762ccb` (`docs(gates): add F8-P1 mathematical design gate`,
  verdict `F8-P1 DESIGN READY`).
- Preconditions verified at implementation start: `HEAD = f762ccb`,
  `origin/main = f762ccb`, branch `main`, working tree clean, no foreign
  changes (no `reset`/`clean`/`restore` used at any point).

## Design Gate

`docs/gates/GATE-F8P1-DESIGN.md` (517 lines, `F8-P1 DESIGN READY`) is the
contract. No `DESIGN CONFLICT` was found during implementation: every
equation, tolerance, status, limit and interface in the gate mapped onto
real certified APIs plus the new SISO LTI mathematics the repo provably
lacked. Five sub-design resolutions were recorded explicitly (not silent
improvisations — see §Deviations): D-R1 (pure-derivative PID lives in an
exact `PIDController` type, never in the proper-only TF type), D-R2
(unity feedback is a static gain, not a degree-0 TF), D-R3 (exact
cancellation decided by a Fraction GCD, `ρ_cancel` kept for the near
case), D-R4 (multiple-root DK plateau accepted only through the
backward-error gate, explicitly tagged), replay-vocabulary aliases
(`VALID`/`RESULT_DIFFERENT`, mandate wording, F8-O precedent).

## Implemented Scope

| Gate ID | Component | File | Classification | Status |
|:---|:---|:---|:---|:---|
| C1 | Polynomial core: Horner, exact algebra, DK roots | `control/poly.py` | NEW | PASS |
| C2 | Rational `H(s)`, series/parallel/feedback, S+T | `control/tf.py` | NEW | PASS |
| C3 | ZPK + TF↔ZPK conversions, cancellation policy | `control/tf.py` | NEW | PASS |
| C4 | Durand–Kerner DecimalComplex + backward gate | `control/poly.py` | NEW | PASS |
| C4 | Routh–Hurwitz exact + pole inventory | `control/stability.py` | NEW | PASS |
| C5 | Evans locus: angle/magnitude, asymptotes, breakaway, jw | `control/locus.py` | NEW | PASS |
| C6 | GM/PM/Tdm via direct evaluation + bisection | `control/margins.py` | NEW | PASS |
| C7 | PID forms + Ziegler–Nichols + closed loop | `control/pid.py` | NEW | PASS |
| C8 | State-space, Faddeeva SS→TF, exact ranks, eigenvalues | `control/statespace.py` | NEW | PASS |
| C9 | Analytic step/impulse + metrics | `control/response.py` | NEW | PASS |
| C10 | `f8p1-control/1` docs + digests + replay | `control/report.py` | NEW | PASS |
| — | Error model | `control/errors.py` | NEW (thin) | PASS |
| — | Public API | `control/__init__.py` | NEW surface | PASS |

No new circuit solver, Bode engine, transient integrator, sampler, GUM
math, plot, UI, filesystem, network, subprocess, clock, global random,
`eval`/`exec`, `pickle`, or second eigensolver. `gum.py` Jacobi is not
reused (symmetric-only; documented non-applicability).

## Mathematical Implementation

- `H(s) = N(s)/D(s)` proper only (`m > n` → `INVALID`, `deg D ≥ 1`,
  `MAX_TF_DEGREE = 32`); Horner evaluation under an explicit precision-50
  context; `D(s) = 0` at the point → `SINGULAR`.
- Series `H1·H2` (convolution), parallel `H1+H2` (common denominator),
  negative feedback `Nf·Dr/(Df·Dr+Nf·Nr)` with the unity static-gain path
  (D-R2); positive feedback explicitly tagged `feedback_positive`.
- `S = D/(D+N)`, `T = N/(D+N)` share one denominator object, so `S+T ≡ 1`
  holds symbolically (coefficient identity), numerically, and for the
  degenerate `L = 0` loop.
- ZPK `H(s) = k Π(s−z)/Π(s−p)`; TF→ZPK via the pole core, ZPK→TF by exact
  complex expansion collapsed to real within `1e-24·(1+|re|)`.
- Cancellation: exact verdict by exact Fraction GCD of `(N, D)` (D-R3);
  near-cancellation by the documented radius `ρ_cancel = 1e-9` on
  DK-derived distances; both sides of the gate tested.
- Routh over exact `Fraction` (from exact `Decimal→Fraction`): zero rows
  → auxiliary polynomial + derivative row (tagged); zero first-column
  pivots → `ε = 1/1000000` substitution (tagged); first-column sign
  changes = RHP count; `STABLE/MARGINAL/UNSTABLE`.
- Evans: angle `∠L = ±180°(2q+1)` checked within `1e-9` deg,
  `K = 1/|L(s)|`, real-axis rule, asymptotes
  `φ_q = 180°(2q+1)/(n−m)`, `σ_c = (Σp−Σz)/(n−m)`, breakaway from
  `D′N − DN′ = 0` filtered by locus membership + `K > 0`, jω crossings by
  phase bisection with Routh cross-check.
- Margins from direct `L(jω)` evaluations only: gain crossovers bisect
  `|L|−1`, phase crossovers bisect `Im(L)` with the `Re < 0` gate;
  `GM = 1/|L(jω_pc)|`, `PM = 180° + ∠L(jω_gc)` (phase normalised into
  `(−360°, 0]`), `T_dm = PM[rad]/ω_gc`; brackets always reported;
  refinement to `≤ 1e-12` relative width in `ω`; absent crossovers →
  `UNSUPPORTED`, never a silent infinite gain.
- PID exact parallel parameters `(Kp, Ki, Kd)`; ideal/series forms stored
  as their exact parallel equivalents; Z-N classic table
  (`0.5 / 0.45,Tu/1.2 / 0.6,Tu/2,Tu/8`); `Ku` from the first phase
  crossover (`Tu = 2π/ωu`); loop formation exact, re-validated proper.
- State-space SISO `(A,B,C,D)`; TF→SS controllable canonical exact
  (ascending-numerator read); SS→TF by the Faddeeva recurrence in Decimal
  (`M_k = A·M_{k−1} + p_{k−1}·I`, `p_k = −tr(A·M_k)/k`); ranks exact over
  `Fraction`; eigenvalues via characteristic polynomial + pole core.
- Time responses by collocation partial fractions (simple and repeated
  poles uniformly, complex pairs to real damped sinusoids,
  `e^{(a+jb)t} = e^{at}(cos bt + j sin bt)` in pure Decimal);
  first-order `K(1−e^{−t/τ})`, second-order canonical metrics
  (`PO = exp(−πζ/√(1−ζ²))`, `t_p = π/(ωn√(1−ζ²))`,
  `t_s(2%) ≈ 4/(ζωn)` as the single sanctioned approximation);
  final-value theorem gated on strict LHP poles.

## Numerical Validation

- `Decimal` at every boundary; `Fraction`/`RationalComplex`-style exact
  side rails (Routh table, GCD, ranks, canonical forms); `DecimalComplex`
  for the `s`-plane; working precision 50 inherited from certified
  `make_context`.
- DK stop `max|Δz| ≤ 1e-30·(1+max|z|)`, budget `500·n`, stagnation window
  20; backward gate `|p(z)| ≤ 1e-30·(1+‖coeff‖∞)` per root; monic
  normalisation before iteration (same roots); deterministic spiral init
  (distinct radii, 0.5 rad offset) + deterministic Cauchy-scaled retry;
  multiple-root plateau accepted only with all backward errors PASS and
  steps `≤ 1e-6`, explicitly tagged (D-R4).
- Locus residual `|1+KL| ≤ 1e-24 + 1e-9·max(1,|L|)` re-checked on every
  reported branch point.
- Crossover bisection `≤ 1e-12` relative in `ω` (12 certified digits);
  step-vs-F8-L agreement `≤ 1 %` on the RC oracle.

## Polynomial Validation

Horner exact (`1/(s+1)` at `j1` is exactly `0.5−0.5j`); degree
0/1/2/32 battery vs direct power sums; zero/large (`1e30`)/small
(`1e-30`)/complex cases; derivative/add/multiply/scale/monic/equality;
degree 33 → `INVALID`; zero polynomial evaluable but rootless
(`INVALID` for roots/Routh/ZPK).

## TF Validation

Serie/paralelo/feedback coefficient-exact
(`1/(s²+3s+2)`, `(2s+3)/(s²+3s+2)`, unity loop `1/(s+2)`);
`S+T ≡ 1` symbolic + numeric (3 points) + degenerate; pole evaluation →
`SINGULAR`; improper/constant/zero denominators → `INVALID`; singular
feedback (`(s+1)/(s+2)` against `−(s+2)/(s+1)`) → `SINGULAR`.

## ZPK Validation

Round-trip `K(s+2)/((s+1)(s+3))`, `K = 2`: gain exact, coefficients
`rel < 1e-12`, evaluation agreement `< 1e-24`; three cancellation
verdicts (exact via GCD, near at distance `1e-12`, none).

## Root Validation

Count conservation (`N_roots = N_degree`); residuals vs the scale-aware
gate; conjugation pairing within `1e-24`; double roots via the plateau
path (`1/(s+1)²` step matches `1−2e^{−1}` to `< 1e-9`); Wilkinson-10
`COMPLETED` (128 iters, max backward `1.3716e-39`); degree-32
`COMPLETED` (1330 iters, max backward `6.4953e-23`).

## Routh Validation

Stable `(s+1)(s+2)(s+3)`: first column exactly `1,6,10,6`, 0 changes;
unstable `(s−1)(s−2)(s+3)`: `UNSTABLE`, RHP = 2 = DK count (agreement);
marginal `(s+2)(s²+1)`: `MARGINAL` + auxiliary tag; epsilon case
`s⁴+2s³+s²+2s+1` explicitly tagged.

## Stability

`pole_inventory` fuses both rails: DK RHP count vs Routh RHP count must
agree or the result is `INCONSISTENT` (never an arbitrary pick);
`STABLE/UNSTABLE/MARGINAL` plus engine states
`SINGULAR/DIVERGED/INVALID/UNSUPPORTED` kept distinct.

## Evans Locus

Real-axis segments of `K(s+2)/(s(s+1))` (on/off/on at −3/−1.5/−0.5);
asymptotes `n−m = 2 → ±90°, σ_c = −0.5` exact, `n−m = 1 → 180°`,
`n−m = 0 → none`; breakaway `K/(s(s+1)) → s = −0.5, K = 0.25`
(`rel < 1e-9`); `K(s+2)/(s(s+1)) → s = −2±√2, K = 3∓2√2`; jω crossing
`Ku = 6, ωu² = 2` (`rel < 1e-9`); every branch point residual-checked.

## Margins

`L = 2.7/(s(s+1)(s+2))`: gain crossover `|L| = 1` to `< 1e-12`,
phase crossover `Im = 0, Re < 0`, GM/PM vs an independent in-test
bisection (`rel < 1e-9` on both frequencies); `1/(s+1)` → both
`UNSUPPORTED`; `T_dm = PM[rad]/ω_gc` to `< 1e-12`; reference pins
`GM = 6.0000000000041640…`, `ω_pc = 1.4142135623735857…` for the unity
loop.

## PID

Forms keep `(Kp,Ki,Kd,Ti,Td)` separated (no parametrisation confusion);
P/PI/PID table values exact decimals (`3`, `2.7`, `3.6/2/0.5` at
`Ku = 6, Tu = 4`); pure-D `as_tf()` → `UNSUPPORTED` (D-R1); loop with a
relative-degree-2 plant stays exact.

## Ziegler–Nichols

`Ku` from the phase crossover (Routh cross-checked: `K = 6` closes
`(s+1)(s+2)s` marginally with `ωu² = 2`); `Tu = 2π/ωu`; plants without a
phase crossover (`1/(s+1)`) → `UNSUPPORTED`; closed loop
`2(s+1)/(s²+3s+2)` Routh-`STABLE` with LHP poles.

## State Space

TF→SS→TF coefficient-exact (4 fixtures incl. biproper-zero case);
SS→TF→SS transfer-identical (pointwise exact); `ctrb/obsv` full (2) and
deficient (0) exact, including the cancellation-induced unobservable
mode; eigenvalues `−1,−2` to `< 1e-12`; the
`C(sI−A)⁻¹B+D` identity verified through an independent 2×2 inverse
(`< 1e-24`).

## Temporal Response

First-order step vs stdlib-context `exp` (`rel < 1e-9`); analytic engine
reproduces it identically; double-pole and complex-pair cases closed-form
checked; impulse real-valued (`Decimal` throughout) and consistent with
the step derivative (`< 1e-4`); second-order `PO/t_p` exact, peak within
2 %, 2 % tail settled; RC oracle vs F8-L transient `≤ 1 %`;
final-value gated (`final-value-blocked` with a pole at the origin,
`final-value-ok:1` for `1/(s+1)`).

## Serialization

`f8p1-control/1`: deterministic dumps, `≤ 64 MiB` guard, unknown-field /
bad-type / bad-JSON rejection, digest recompute (tamper →
`INCONSISTENT` on load, `INVALID_SERIALIZATION` on compare), `str()`
Decimals (never `normalize()`), aliases `VALID`/`RESULT_DIFFERENT`.

## Replay

`EQUIVALENT` (byte-identical round-trip, triple-run single digest),
`RESULT_DIFFERS` (two valid distinct documents),
`VERSION_MISMATCH` (`f8p1-control/2`), `SCHEMA_MISMATCH`
(`f8o-metrology/1`), `INVALID_SERIALIZATION` (non-JSON, tampered).

## Determinism

Triple DK runs bit-identical; triple dumps/digests identical;
insertion-order-invariant digests; Aberth-spiral init (no RNG anywhere;
MC seeds only inside reused F8-M); canonical JSON; no clock/locale/
parallelism in digests.

## Security

Literal `grep -RniE` audit over `control/` (eval/exec/compile/getattr/
setattr/open/subprocess/pickle/marshal/importlib/socket/urllib/numpy/
scipy/`import math`/`float(`): 0 matches. AST audit (P-034): 0 banned
calls, 0 banned top-level imports (incl. `math`/`numpy`/`scipy`/`re`),
no `lab/`/`simulation`/UI/application/infrastructure edges, 0 float
literals, 0 `float(` substrings. Deserialization is typed/allowlisted,
size-guarded, digest-verified. `test_eng_security.py` green (chunk 1).

## Architecture

`control → {math.*, units}` only (plus stdlib `decimal`/`fractions`/
`dataclasses`/`hashlib`/`json`/`enum`); engines never import `control`;
no `control → lab` edge (N-110 clean by construction — no lab import
exists); no `simulation`/UI/application/infrastructure/filesystem/
network imports (`test_architecture.py` 9/9 green).

## Performance

Recorded (P-036, no wall asserts): DK n=2 (10 iters, <0.01 s), n=10
(128 iters, 0.76 s), n=32 (1330 iters, 133.2 s — the documented
bottleneck: DK at degree 32 / precision 50); locus G=20 (0.17 s, all
residuals ok); margins scan+bisection (0.14 s). Priority respected:
correctness > determinism > numerical integrity > performance.

## Regression Results

| Suite | Collected | Result |
|:---|---:|:---|
| F8-P1 new (`test_f8p1_control.py`, P-001…P-037+) | 51 | 51 PASS |
| Chunk 1 (app/domain/eng/unit/security/arch) | 99 | PASS |
| Chunk 2 (F7 incl. B7-79 + F8-A…D8) | 1101 | PASS |
| Chunk 3a (F8-E…K) | 560 | PASS |
| Chunk 3b (F8-L/M/N/O incl. transient) | 340 | PASS |
| Chunk 4 (F9/misc/UI/perf) | 216 | PASS, 2 pre-existing env skips |
| **Total** | **≈2367** | **0 failed** |

`git diff f762ccb -- src/academic_core/domain/engineering/` shows changes
only as the new `control/` package (untracked addition); certified
engines byte-unchanged. `test_architecture.py` green confirms no boundary
drift.

## Known Limitations

Inherited, unchanged: wrapped F8-L/F8-M oracles keep their native
tolerances (F8-L band `≤ 1 %` is diagnostic, not a proof). New and
documented: DK at degree 32 is seconds-to-minutes scale (133 s measured);
multiplicity ≥ 8 may report `DIVERGED` despite tiny backward errors
(conservative: steps above the `1e-6` plateau band are never silently
accepted); margins scan spans `1e-6…1e6` rad/s with single-wrap phase
normalisation (loops reaching below −360° need extension — outside the
certified test scope); response grouping radius `1e-6` (distinct poles
closer than that are treated as multiple — documented); `t_s ≈ 4/(ζωn)`
is the single sanctioned approximation with its validity band.

## Deviations

- **D-R1 (math over form)**: pure-derivative PID is improper and cannot
  inhabit the proper-only TF type; compensators live in the exact
  `PIDController` type with exact loop formation. No certified test
  touched.
- **D-R2**: unity feedback is a static gain, not a degree-0 TF; the
  general two-TF feedback formula is unchanged.
- **D-R3 (exactness over tolerance)**: exact cancellation decided by an
  exact Fraction GCD, not by `|a−b| < ε`; `ρ_cancel` kept for the near
  case, both sides tested.
- **D-R4 (honesty over silence)**: DK multiple-root plateau accepted
  only with all backward errors PASS and steps `≤ 1e-6`, tagged in the
  diagnostic; Routh agreement still required downstream.
- **Replay vocabulary**: canonical `EQUIVALENT`/`RESULT_DIFFERS` (gate);
  `VALID`/`RESULT_DIFFERENT` are tested constant aliases (F8-O precedent).

## Evidence Matrix

| Requisito | Implementación | Test | Referencia | Evidencia | Estado |
|:---|:---|:---|:---|:---|:---|
| Horner | `poly.evaluate` | P-001 | `0.5−0.5j` exacto | pin exacto | PASS |
| TF serie/paralelo/feedback | `tf` | P-002 | coeficientes exactos | `1/(s²+3s+2)` etc. | PASS |
| S+T=1 | `sensitivity/complementary` | P-003 | identidad simbólica | `numS+numT=den` | PASS |
| Polos 2.º orden | `tf_to_zpk` | P-004 | `−ζωn±jωn√(1−ζ²)` | rel<1e-12 | PASS |
| ZPK round-trip | `tf_to_zpk/zpk_to_tf` | P-005 | coeficientes | rel<1e-12 | PASS |
| Routh exacto | `stability` | P-006/007 | `1,6,10,6` / RHP=2 | exacto + acuerdo DK | PASS |
| Routh auxiliar/ε | `stability` | P-008 | par jω / tag | MARGINAL + tags | PASS |
| DK + backward | `poly` | P-009 | Wilk-10, grado 32 | 1.37e-39, 6.5e-23 | PASS |
| Conjugación | `validate_roots` | P-004b | pares ±j | pairing ok | PASS |
| Evans real/asi/break | `locus` | P-010/011/012 | regla, σc, dK/ds=0 | exacto / <1e-9 | PASS |
| Cruce jω + Ku | `locus/pid` | P-013 | fila Routh K=6 | rel<1e-9 | PASS |
| Residuo 1+L | `locus_point` | P-014 | cota gate | ok en ramas | PASS |
| GM/PM | `margins` | P-015 | bisección propia | rel<1e-9, 1e-12 | PASS |
| Sin cruce | `margins` | P-016 | `1/(s+1)` | UNSUPPORTED | PASS |
| Tdm | `margins` | P-017 | PM/ωgc | <1e-12 | PASS |
| Z-N | `pid` | P-018 | tabla 0.5/0.45/0.6 | decimales exactos | PASS |
| Lazo cerrado | `pid/stability` | P-019 | Routh + LHP | STABLE | PASS |
| TF/SS | `statespace` | P-020 | canónica | coef. exactos | PASS |
| Rangos | `statespace` | P-021 | Fraction | 2/0/1 exactos | PASS |
| Autovalores | `statespace` | P-022 | polos | <1e-12 | PASS |
| Escalón 1er/2.º | `response` | P-023/024 | cerradas | <1e-9 / bandas | PASS |
| Escalón vs F8-L | test+F8-L | P-025 | RC oracle | ≤1 % | PASS |
| Impulso | `response` | P-026 | cerrada + prop. | <1e-9 / <1e-4 | PASS |
| Valor final | `response` | P-027 | tags | blocked/ok | PASS |
| Cancelación ρ | `tf` | P-028 | GCD + radio | 3 veredictos | PASS |
| Hostil | todos | P-029/030/033 | estados | INVALID/… | PASS |
| Determinismo | todo+núcleo | P-031 | triple run | 1 digest | PASS |
| Serialización | `report` | P-032 | round-trip/tamper | 5 estados | PASS |
| Seguridad | auditoría | P-034/035 | grep + AST | 0 banned | PASS |
| Bench | suite | P-036 | tiempos | registrados | PASS |
| Regresión | suites | P-037 + chunks | ≈2367 | 0 failed | PASS |

## Final Verdict

F8-P1 CERTIFIED
