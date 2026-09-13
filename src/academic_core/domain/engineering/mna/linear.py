"""Exact rational linear solve: Gauss-Jordan elimination over `Fraction`.

No numpy/scipy (none exist anywhere in this repo; see F8-B audit) and no
floats: every matrix/vector entry is a `fractions.Fraction`, so elimination
introduces zero rounding error and singularity is `pivot == 0` exactly.
Deterministic: for a given matrix, pivot selection always scans rows in
index order (no partial pivoting by magnitude is needed for numerical
stability with exact arithmetic), so results do not depend on insertion
order beyond how the caller ordered rows/columns.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction


class LinearSolveStatus(Enum):
    UNIQUE = "unique"
    SINGULAR = "singular"
    INCONSISTENT = "inconsistent"


@dataclass(frozen=True)
class LinearSolveOutcome:
    status: LinearSolveStatus
    solution: tuple[Fraction, ...] | None
    rank: int


def solve_exact(matrix: list[list[Fraction]], rhs: list[Fraction]) -> LinearSolveOutcome:
    """Solve `matrix @ x = rhs` over the rationals via Gauss-Jordan.

    `matrix` must be square (n x n); `rhs` must have length n. Returns
    UNIQUE with the solution when the system has full rank; SINGULAR when
    rank-deficient but consistent (infinitely many solutions); INCONSISTENT
    when rank-deficient and contradictory (no solution).
    """
    n = len(matrix)
    if any(len(row) != n for row in matrix) or len(rhs) != n:
        raise ValueError("solve_exact requires a square matrix matching rhs length")

    # augmented matrix, row-major, deep copy so caller's matrix is untouched
    aug = [[Fraction(matrix[i][j]) for j in range(n)] + [Fraction(rhs[i])] for i in range(n)]

    pivot_row_of_col: dict[int, int] = {}
    row = 0
    for col in range(n):
        pivot_row = None
        for r in range(row, n):
            if aug[r][col] != 0:
                pivot_row = r
                break
        if pivot_row is None:
            continue
        aug[row], aug[pivot_row] = aug[pivot_row], aug[row]
        pivot_val = aug[row][col]
        aug[row] = [v / pivot_val for v in aug[row]]
        for r in range(n):
            if r == row:
                continue
            factor = aug[r][col]
            if factor != 0:
                aug[r] = [aug[r][k] - factor * aug[row][k] for k in range(n + 1)]
        pivot_row_of_col[col] = row
        row += 1

    rank = row
    if rank < n:
        for r in range(rank, n):
            if all(aug[r][k] == 0 for k in range(n)) and aug[r][n] != 0:
                return LinearSolveOutcome(LinearSolveStatus.INCONSISTENT, None, rank)
        return LinearSolveOutcome(LinearSolveStatus.SINGULAR, None, rank)

    solution = [Fraction(0)] * n
    for col, r in pivot_row_of_col.items():
        solution[col] = aug[r][n]
    return LinearSolveOutcome(LinearSolveStatus.UNIQUE, tuple(solution), rank)
