"""High-precision complex linear solve (F8-D2, HIGH_PRECISION mode).

Pipeline: equilibrate (two-sided diagonal scaling, see ``scaling.py``) →
Gauss-Jordan elimination with deterministic partial pivoting (maximum
modulus, ties broken by lowest row index) → structural rank analysis →
solution recovery ``x = D_R x'`` → residual and backward error evaluated
on the ORIGINAL system → explicit status policy.

Pivot comparisons use ``squared_modulus`` (monotonic with the modulus,
cheaper, no roots): ordering is identical, and only the final reported
ratio takes a square root.

D2 solver policy (documented thresholds, not mathematical truths):

* ``BE_TOL = 1E-30`` — a computed solution is accepted as SOLVED only if
  its backward error does not exceed this. Rationale: the working floor
  is ~1E-50; O(N^3) accumulation over dozens of rows costs a handful of
  digits, so 1E-30 demands strong evidence while staying far above the
  noise floor.
* ``PIVOT_FLOOR = 1E-40`` — on the equilibrated (O(1)) system, a pivot
  smaller than this relative to the matrix scale is too close to the
  working floor to certify: the elimination may have rounded a true
  zero, or rounding may have created a fake nonzero. Either way the
  rank evidence is inconclusive → NUMERICALLY_UNCERTAIN, never a
  fabricated SINGULAR/INCONSISTENT.
* ``RHS_FLOOR_REL = 1E-40`` — a structurally zero row whose right-hand
  side is nonzero but below ``RHS_FLOOR_REL * max|b'|`` is treated as
  noise-ambiguous → NUMERICALLY_UNCERTAIN rather than INCONSISTENT.

Structural facts (exact-zero pivots / rows in the working-precision
computation) classify SINGULAR vs INCONSISTENT exactly as in the exact
mode — with the documented caveat that they describe the rounded
problem, which is precisely why the uncertainty guards above exist.

What is reported when the evidence is inconclusive: the computed
solution (when one exists), the residual, the backward error, the
pivot ratio, the growth factor, and diagnostics explaining which check
failed. NUMERICALLY_UNCERTAIN is a verdict about evidence, not a
missing value.
"""

from __future__ import annotations

from decimal import Decimal

from academic_core.domain.engineering.math.decimal_complex import DecimalComplex
from academic_core.domain.engineering.math.linsolve.result import SolveStatus
from academic_core.domain.engineering.math.linsolve.scaling import equilibrate, unscale
from academic_core.domain.engineering.math.trig import make_context

BE_TOL = Decimal("1E-30")
PIVOT_FLOOR = Decimal("1E-40")
RHS_FLOOR_REL = Decimal("1E-40")


def _max_entry_sqmod(rows: tuple[tuple[DecimalComplex, ...], ...]) -> Decimal:
    best = Decimal(0)
    for row in rows:
        for e in row:
            m = e.squared_modulus()
            if m > best:
                best = m
    return best


def hp_solve(
    A: tuple[tuple[DecimalComplex, ...], ...],
    b: tuple[DecimalComplex, ...],
) -> dict:
    """Solve ``A x = b`` in high precision.

    Returns a dict with status, solution (on the original system) or
    None, rank estimates, residual, residual_norm, backward_error,
    growth_factor, scales, and notes. Inputs are never mutated.
    """
    ctx = make_context()
    n = len(A)
    notes: list[str] = []
    a2, b2, row_scale, col_scale = equilibrate(A, b)
    notes.append(
        "scaling: two-sided diagonal equilibration A'=D_L A D_R, b'=D_L b; "
        "solution recovered as x=D_R x'"
    )
    aug: list[list[DecimalComplex]] = [list(a2[i]) + [b2[i]] for i in range(n)]
    initial_sq = _max_entry_sqmod(a2)
    growth_sq = initial_sq
    pivot_row_of_col: dict[int, int] = {}
    pivot_sqmods: list[Decimal] = []
    row = 0
    for col in range(n):
        best = None
        bestm = Decimal(0)
        for r in range(row, n):
            m = aug[r][col].squared_modulus()
            if best is None or m > bestm:
                best, bestm = r, m
        if best is None or bestm == 0:
            # Entire column remainder is exactly zero: structural rank
            # deficiency in the working-precision computation.
            continue
        aug[row], aug[best] = aug[best], aug[row]
        piv = aug[row][col]
        aug[row] = [v / piv for v in aug[row]]
        for r in range(n):
            if r == row:
                continue
            factor = aug[r][col]
            if not factor.is_zero_exact():
                aug[r] = [aug[r][k] - factor * aug[row][k] for k in range(n + 1)]
        for r in range(n):
            for k in range(n + 1):
                m = aug[r][k].squared_modulus()
                if m > growth_sq:
                    growth_sq = m
        pivot_row_of_col[col] = row
        pivot_sqmods.append(bestm)
        row += 1
    rank_aug = row
    bmax = Decimal(0)
    for e in b2:
        m = e.modulus()
        if m > bmax:
            bmax = m
    rhs_floor = RHS_FLOOR_REL * bmax
    growth = ctx.sqrt(growth_sq) if growth_sq != 0 else Decimal(0)
    amax = ctx.sqrt(initial_sq) if initial_sq != 0 else Decimal(0)

    def _base(**over):
        out = dict(
            rank_A=None, rank_augmented=None, solution=None, residual=None,
            residual_norm=None, backward_error=None, growth_factor=growth,
            row_scale=row_scale, col_scale=col_scale, notes=tuple(notes),
        )
        out.update(over)
        return out

    if rank_aug < n:
        rank_A = rank_aug
        inconsistent = False
        uncertain_rows = False
        for r in range(rank_aug, n):
            if all(aug[r][k].is_zero_exact() for k in range(n)):
                rhs_mod = aug[r][n].modulus()
                if rhs_mod == 0:
                    continue
                if rhs_mod <= rhs_floor:
                    uncertain_rows = True
                else:
                    inconsistent = True
        if inconsistent and not uncertain_rows and not pivot_sqmods_tiny(pivot_sqmods, initial_sq):
            notes.append(
                "structural inconsistency: zero row in A-part with clearly "
                "nonzero right-hand side and no conflicting uncertainty evidence"
            )
            return _base(status=SolveStatus.INCONSISTENT, rank_A=rank_A,
                         rank_augmented=rank_aug + 1, notes=tuple(notes))
        if inconsistent or uncertain_rows:
            notes.append(
                "rank-deficient elimination with contradictory or "
                "noise-level right-hand sides: cannot certify singularity "
                "vs inconsistency at working precision"
            )
            return _base(status=SolveStatus.NUMERICALLY_UNCERTAIN, rank_A=rank_A,
                         rank_augmented=rank_aug + (1 if inconsistent else 0),
                         notes=tuple(notes))
        notes.append("structural rank deficiency with consistent right-hand side")
        return _base(status=SolveStatus.SINGULAR, rank_A=rank_A,
                     rank_augmented=rank_aug, notes=tuple(notes))

    # Full rank: recover solution and check the evidence.
    x_prime = [DecimalComplex.zero()] * n
    for col, r in pivot_row_of_col.items():
        x_prime[col] = aug[r][n]
    x = unscale(tuple(x_prime), col_scale)
    residual = _residual(A, b, x)
    residual_norm = Decimal(0)
    for e in residual:
        m = e.modulus()
        if m > residual_norm:
            residual_norm = m
    backward_error = _backward_error(A, b, x, residual, residual_norm, ctx)
    pmin_sq = pivot_sqmods[0]
    for p in pivot_sqmods[1:]:
        if p < pmin_sq:
            pmin_sq = p
    pmin = ctx.sqrt(pmin_sq)
    pivot_ratio = ctx.divide(pmin, amax) if amax != 0 else Decimal(0)
    notes.append(f"pivot_ratio_min={pmin} relative to scaled matrix scale {amax}")
    notes.append(f"backward_error={backward_error} (tolerance {BE_TOL})")
    if pivot_ratio < PIVOT_FLOOR:
        notes.append(
            f"pivot ratio {pivot_ratio} below floor {PIVOT_FLOOR}: "
            "rank evidence inconclusive at working precision"
        )
        return _base(status=SolveStatus.NUMERICALLY_UNCERTAIN, solution=x,
                     rank_A=n, rank_augmented=n, residual=residual,
                     residual_norm=residual_norm, backward_error=backward_error,
                     pivot_ratio=pivot_ratio, notes=tuple(notes))
    if backward_error is None or backward_error > BE_TOL:
        notes.append(
            "backward error exceeds acceptance tolerance: solution does "
            "not check out at working precision"
        )
        return _base(status=SolveStatus.NUMERICALLY_UNCERTAIN, solution=x,
                     rank_A=n, rank_augmented=n, residual=residual,
                     residual_norm=residual_norm, backward_error=backward_error,
                     pivot_ratio=pivot_ratio, notes=tuple(notes))
    return _base(status=SolveStatus.SOLVED, solution=x, rank_A=n,
                 rank_augmented=n, residual=residual, residual_norm=residual_norm,
                 backward_error=backward_error, pivot_ratio=pivot_ratio,
                 notes=tuple(notes))


def pivot_sqmods_tiny(pivot_sqmods: list[Decimal], initial_sq: Decimal) -> bool:
    """True if any pivot is below the floor relative to matrix scale."""
    if not pivot_sqmods or initial_sq == 0:
        return False
    ctx = make_context()
    amax = ctx.sqrt(initial_sq)
    for p in pivot_sqmods:
        if ctx.divide(ctx.sqrt(p), amax) < PIVOT_FLOOR:
            return True
    return False


def _residual(A, b, x) -> tuple[DecimalComplex, ...]:
    """r = A x - b on the original system, under the working context."""
    n = len(A)
    out = []
    for i in range(n):
        acc = DecimalComplex.zero()
        for j in range(n):
            acc = acc + A[i][j] * x[j]
        out.append(acc - b[i])
    return tuple(out)


def _backward_error(A, b, x, residual, residual_norm, ctx) -> Decimal | None:
    """||r|| / (||A|| ||x|| + ||b||) with max-modulus norms.

    Dimensionless by construction. ``scale == 0`` with an exactly-zero
    residual means the computed solution solves the unperturbed problem
    exactly → 0. A nonzero residual with zero scale cannot arise from
    the elimination paths above; it yields None (never NaN/Infinity —
    no division by zero is ever executed).
    """
    n = len(A)
    a_norm = Decimal(0)
    for row in A:
        for e in row:
            m = e.modulus()
            if m > a_norm:
                a_norm = m
    x_norm = Decimal(0)
    for e in x:
        m = e.modulus()
        if m > x_norm:
            x_norm = m
    b_norm = Decimal(0)
    for e in b:
        m = e.modulus()
        if m > b_norm:
            b_norm = m
    scale = ctx.add(ctx.multiply(a_norm, x_norm), b_norm)
    if scale == 0:
        if residual_norm == 0:
            return Decimal(0)
        return None
    return ctx.divide(residual_norm, scale)
