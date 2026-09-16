"""Exact complex linear solve (F8-D2, EXACT mode).

Gauss-Jordan elimination over :class:`RationalComplex`, mirroring the
proven F8-B structure (augmented matrix, deterministic pivot scan,
Rouché-Capelli classification) but operating natively on D1 complex
numbers — F8-B's ``Fraction`` solver is NOT reused, because routing
complex entries through pairs of real solves would duplicate
representation and bypass the D1 exactness boundary.

Pivot policy: first nonzero entry scanning rows in index order
(``is_zero_exact``). No magnitude pivoting is needed — or meaningful —
for exact arithmetic, and the scan order makes the result independent
of anything but the input ordering.

Ranks: ``rank(A)`` is computed on an independent copy of ``A``;
``rank([A|b])`` comes from the augmented elimination. Classification:

* ``rank(A) == rank([A|b]) == N`` → SOLVED (unique solution);
* ``rank(A) == rank([A|b]) < N`` → SINGULAR (consistent, infinite solutions);
* ``rank([A|b]) > rank(A)`` → INCONSISTENT (contradictory constraints).

No tolerance, no epsilon, no approximation anywhere. The residual of a
SOLVED system is exactly zero by construction and is verified, not
assumed: ``A x - b`` is recomputed from the returned solution.
"""

from __future__ import annotations

from academic_core.domain.engineering.math.linsolve.result import SolveStatus
from academic_core.domain.engineering.math.rational import RationalComplex


def _copy(rows: tuple[tuple[RationalComplex, ...], ...]) -> list[list[RationalComplex]]:
    return [[e for e in row] for row in rows]


def exact_rank(A: tuple[tuple[RationalComplex, ...], ...]) -> int:
    """Exact rank of a (possibly rectangular) rational-complex matrix."""
    m = [row[:] for row in _copy(A)]
    n_rows = len(m)
    n_cols = len(m[0]) if m else 0
    rank = 0
    row = 0
    for col in range(n_cols):
        pivot = None
        for r in range(row, n_rows):
            if not m[r][col].is_zero_exact():
                pivot = r
                break
        if pivot is None:
            continue
        m[row], m[pivot] = m[pivot], m[row]
        piv = m[row][col]
        m[row] = [v / piv for v in m[row]]
        for r in range(n_rows):
            if r == row:
                continue
            factor = m[r][col]
            if not factor.is_zero_exact():
                m[r] = [m[r][k] - factor * m[row][k] for k in range(n_cols)]
        rank += 1
        row += 1
    return rank


def exact_solve(
    A: tuple[tuple[RationalComplex, ...], ...],
    b: tuple[RationalComplex, ...],
) -> tuple[SolveStatus, tuple[RationalComplex, ...] | None, int, int]:
    """Solve ``A x = b`` exactly.

    Returns ``(status, solution_or_None, rank_A, rank_augmented)``.
    Both ranks are computed independently (``rank(A)`` on a copy of
    ``A``, ``rank([A|b])`` on the augmented rows) and the status follows
    Rouché-Capelli; the solution pass only runs when the ranks certify
    a unique solution. Inputs are never mutated.
    """
    n = len(A)
    rank_A = exact_rank(A)
    aug_rows = tuple(tuple(A[i]) + (b[i],) for i in range(n))
    rank_aug = exact_rank(aug_rows)
    if rank_A == rank_aug == n:
        aug: list[list[RationalComplex]] = [list(row) for row in aug_rows]
        pivot_row_of_col: dict[int, int] = {}
        row = 0
        for col in range(n):
            pivot = None
            for r in range(row, n):
                if not aug[r][col].is_zero_exact():
                    pivot = r
                    break
            if pivot is None:  # unreachable: ranks certified full rank
                raise AssertionError(
                    "internal defect: rank certificate contradicted by elimination"
                )
            aug[row], aug[pivot] = aug[pivot], aug[row]
            piv = aug[row][col]
            aug[row] = [v / piv for v in aug[row]]
            for r in range(n):
                if r == row:
                    continue
                factor = aug[r][col]
                if not factor.is_zero_exact():
                    aug[r] = [aug[r][k] - factor * aug[row][k] for k in range(n + 1)]
            pivot_row_of_col[col] = row
            row += 1
        solution = [RationalComplex.zero()] * n
        for col, r in pivot_row_of_col.items():
            solution[col] = aug[r][n]
        # Verify, don't assume: recompute A x - b exactly.
        for i in range(n):
            acc = RationalComplex.zero()
            for j in range(n):
                acc = acc + A[i][j] * solution[j]
            if acc - b[i] != RationalComplex.zero():
                raise AssertionError(
                    "internal defect: exact elimination produced a non-exact solution"
                )
        return SolveStatus.SOLVED, tuple(solution), rank_A, rank_aug
    if rank_A == rank_aug:
        return SolveStatus.SINGULAR, None, rank_A, rank_aug
    return SolveStatus.INCONSISTENT, None, rank_A, rank_aug
