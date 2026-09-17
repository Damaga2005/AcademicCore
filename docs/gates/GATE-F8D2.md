# Quality Gate: F8-D2 — Complex Linear Solver

- **Phase**: F8-D2 (second step of F8-D; F8-D1 certified, F8-D3 NOT started).
- **Scope**: generic complex linear solver `A x = b` ONLY. No MNA AC, no
  power, no Thevenin/Norton AC, no second `Circuit` representation.
- **Package**: `src/academic_core/domain/engineering/math/linsolve/`
  (`errors.py`, `problem.py`, `result.py`, `scaling.py`, `exact.py`,
  `high_precision.py`, `solver.py`, `__init__.py`).
- **Tests**: `tests/test_f8d2_complex_solver.py` (65 tests).
- **Status**: implemented, self-verified, uncommitted (no commit/push by rule).

> HIGH_PRECISION provides finite-precision decimal computation with explicit
> residual/error/uncertainty criteria. It never claims exactness.

---

## 1. Architecture

```text
ComplexMatrix → ComplexLinearProblem → solve(problem, mode)
      │                                        ├── EXACT → RationalComplex
      │                                        └── HIGH_PRECISION → DecimalComplex
      ▼                                              │
validated immutable input                      LinearSolveResult
```

`ComplexLinearProblem.from_sequences(A, b)` validates (square, matching
dimensions, homogeneous D1 types with documented one-way promotion) and
freezes inputs. `solve()` dispatches on `NumericMode` (EXACT /
HIGH_PRECISION / AUTO) and returns `LinearSolveResult` with status,
solution, ranks, residual, backward error, scaling info, diagnostics,
provenance, and a deterministic digest. F8-B (`mna/`) is untouched and
coexists; F8-D3 reuses this package.

## 2. Numeric modes

- **EXACT**: `RationalComplex` only. No tolerance, zero is `is_zero_exact`,
  no scaling (exact arithmetic needs none; `Decimal` factors must never
  enter the exact path), `working_precision=None` with explanation.
  EXACT on decimal data is refused (`InvalidModeError`) — solving rounded
  data and calling it exact would fake exactness.
- **HIGH_PRECISION**: `DecimalComplex` under the explicit D1 working
  context (50 digits); rational inputs are promoted entrywise (allowed
  direction, recorded as `input_promoted`). Result records `numeric_mode`
  and `working_precision=50`.

## 3. Algorithm

Both modes use Gauss-Jordan elimination on the augmented system (conceptual
reuse of the proven F8-B structure, reimplemented natively on D1 types —
F8-B's `Fraction` solver is not imported, avoiding representation
duplication). EXACT pivots on the first nonzero in index order (deterministic;
magnitude pivoting is meaningless for exact arithmetic). HIGH_PRECISION uses
deterministic partial pivoting by maximum `squared_modulus` (monotonic with
the modulus, cheaper, root-free), ties broken by lowest row index. No
`n == 2 / n == 3` special cases exist; generality sweep covers
N = 1, 2, 3, 4, 8, 16, 32, 64 in both modes (N=64 ≈ 6 s per mode).

## 4. Exact rank

`rank(A)` is computed on an independent copy of A; `rank([A|b])` on the
augmented rows. Rouché-Capelli: N/N → SOLVED (solution pass + exact
`A x - b` re-verification), equal below N → SINGULAR, augmented strictly
greater → INCONSISTENT. F8-B's single-pass rank field counted A-pivots
only, which under-reports the augmented rank of inconsistent systems; D2
computes both ranks independently (audit finding, fixed by construction).

## 5. Numeric rank and classification

HP elimination reports pivot-count rank estimates. Exact-zero pivots/rows
in the working-precision computation give structural SINGULAR /
INCONSISTENT verdicts (documented as properties of the rounded problem).
A small-but-nonzero pivot is NEVER presented as rank deficiency — see §6.

## 6. Uncertainty policy (solver policy, not mathematical truth)

`BE_TOL=1E-30` (backward-error acceptance; working floor ~1E-50, margin
for O(N³) accumulation), `PIVOT_FLOOR=1E-40` (minimum pivot ratio on the
equilibrated O(1) system), `RHS_FLOOR_REL=1E-40` (noise-level RHS
threshold relative to max|b'|). NUMERICALLY_UNCERTAIN is returned when:
a pivot ratio falls below the floor (rounded zero vs fake nonzero
indistinguishable), a structurally-zero row carries a noise-level RHS
(singular-consistent vs noisy-inconsistent indistinguishable), or the
backward error exceeds tolerance. The computed solution, residual,
backward error, pivot ratio, and growth factor are still reported with
diagnostics naming the failed check. Evidence, not missing values.

## 7. Residual

`r = A x - b` recomputed on the ORIGINAL system. `residual_norm` is the
max-modulus norm `max|r_i|` (Decimal moduli). Scale-aware through the
backward-error denominator, never bare `max(abs(r))`. Exact mode reports
the exact zero triplet (tuple of zeros, norm 0). No-solution statuses
report `None` with explanation.

## 8. Backward error

`η = ||r|| / (||A|| ||x|| + ||b||)` with max-entry/modulus norms
(documented: not an operator norm, not a condition estimate). Scale
`0` with zero residual → `0`; nonzero residual with zero scale → `None`
(guarded division — NaN/Infinity can never appear; finiteness asserted
in adversarial tests). Dimensionless by construction; invariance under
`kA, kb` tested. A small residual is explicitly NOT presented as proof
of good conditioning — no condition estimator is claimed; insufficient
evidence yields NUMERICALLY_UNCERTAIN instead.

## 9. Scaling

Two-sided diagonal equilibration (HP only): `row_scale[i]=1/max|A[i]|`,
`col_scale[j]=1/max|A1[][j]|`, `A'=D_L A D_R`, `b'=D_L b`, `x=D_R x'`
(factor 1 for exactly-zero rows/columns, left for structural analysis).
Rank preserved because diagonal positive factors are invertible;
solution recovered by substitution; unit changes absorbed into the
factors (row×1000 invariance tested; column-scaling unknown-equivalence
tested; scaled-vs-original rank agreement tested). Factors are
working-precision approximations — harmless by design since acceptance
is judged by the backward error on the original system.

## 10. Mathematical quality answers (§29)

1. Exact singularity vs numeric uncertainty: exact-zero elimination
   structure → SINGULAR; tiny-but-nonzero pivots (< 1E-40 of scale) →
   UNCERTAIN (rounded-zero vs fake-nonzero indistinguishable).
2. Exact inconsistency vs numeric uncertainty: zero A-row with clearly
   nonzero RHS and no conflicting evidence → INCONSISTENT; noise-level
   RHS (≤ 1E-40·max|b'|) → UNCERTAIN.
3. NUMERICALLY_UNCERTAIN = evidence insufficient to certify; solution and
   error metrics still reported with the failed check named.
4. Residual norm: max-modulus norm on the original system.
5. Backward-error norm: max-entry/modulus norms, dimensionless ratio.
6. Scaling: explicit `D_L`/`D_R` equilibration as above (HP only).
7. Solution preserved by substitution `x = D_R x'` (pure algebra).
8. Rank preserved: invertible diagonal factors (mathematical fact;
   pivot *decisions* intentionally change).
9. Ill-conditioned systems: small backward error may still be reported,
   but certification requires pivot health; otherwise UNCERTAIN. No
   condition estimator is claimed.
10. Small nonzero pivots: below floor → UNCERTAIN, never fake SINGULAR.
11. Extreme magnitudes (1E±300 tested): normalized by equilibration;
    exact mode handles 10¹⁰⁰ integers natively.
12. Exact: elimination, ranks, classification, residual. Approximate:
    everything on the decimal side incl. scale factors, moduli, roots,
    trig-free (no transcendental functions used by the solver at all).
13. Independent evidence: hand-derived 1×1/2×2 (det=9j case), separately
    coded Cramer/Sarrus references, forward-product references,
    EXACT↔HP cross-agreement, metamorphic identities.

## 11. Limitations

- HP ranks are estimates; only exact-zero structure is reported as
  SINGULAR/INCONSISTENT, and only about the rounded problem.
- No condition-number estimator; residual small ≠ well-conditioned.
- Thresholds (1E-30/1E-40) are engineering policy for 50-digit work,
  not theorems; retune if working precision ever changes.
- Square systems only; rectangular MNA assembly stays in F8-D3.

## 12. Regression & boundaries

Full suite must show pre-existing tests PASS (baseline 739 passed +
48 D1 + 65 D2 expected), no file outside `math/linsolve/`,
`tests/test_f8d2_complex_solver.py`, `docs/gates/GATE-F8D2.md` touched.
No commit, no push, no PR, no remote changes. F8-D3 NOT started.
