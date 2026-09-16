"""Public API for the F8-D2 complex linear solver.

Conceptual use::

    problem = ComplexLinearProblem.from_sequences(A, b)
    result = solve(problem, mode=NumericMode.AUTO)

Mode dispatch:

* ``EXACT`` — rational problems only; exact Gauss-Jordan, no scaling
  (exact arithmetic needs none, and ``Decimal`` scale factors must never
  enter the exact path), ``working_precision=None`` with explanation.
* ``HIGH_PRECISION`` — decimal problems, or rational problems promoted
  explicitly at the boundary (``input_promoted`` recorded in provenance).
* ``AUTO`` — rational → EXACT, decimal → HIGH_PRECISION.
* ``EXACT`` on decimal data is refused (``InvalidModeError``): solving
  rounded data and calling it exact would fake exactness.

Provenance carries engine, version, numeric_mode, matrix_dimension,
rank_A, rank_augmented, status, precision, pivot_policy, scaling_policy,
residual_definition, and backward_error_definition. The digest is
sha256 over a canonical JSON document (sorted keys, stringified
numbers) covering inputs, mode, and policy constants — never
timestamps, memory addresses, or randomness.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from academic_core.domain.engineering.math.decimal_complex import DecimalComplex
from academic_core.domain.engineering.math.linsolve.errors import InvalidModeError
from academic_core.domain.engineering.math.linsolve.exact import exact_solve
from academic_core.domain.engineering.math.linsolve.high_precision import (
    BE_TOL,
    PIVOT_FLOOR,
    RHS_FLOOR_REL,
    hp_solve,
)
from academic_core.domain.engineering.math.linsolve.problem import (
    ComplexLinearProblem,
    NumericMode,
)
from academic_core.domain.engineering.math.linsolve.result import (
    LinearSolveResult,
    SolveStatus,
)
from academic_core.domain.engineering.math.rational import RationalComplex
from academic_core.domain.engineering.math.trig import WORKING_PRECISION

SOLVER_VERSION = "f8d2-linsolve/1.0"

PIVOT_POLICY_EXACT = (
    "first-nonzero scan in index order (is_zero_exact); no magnitude "
    "pivoting — meaningless for exact arithmetic; deterministic"
)
PIVOT_POLICY_HP = (
    "partial pivoting by maximum squared_modulus (monotonic with modulus), "
    "ties broken by lowest row index; deterministic"
)
SCALING_POLICY_EXACT = "none (exact arithmetic needs no equilibration)"
SCALING_POLICY_HP = (
    "two-sided diagonal equilibration: row_scale[i]=1/max|A[i]|, "
    "col_scale[j]=1/max|A1[][j]|, A'=D_L A D_R, b'=D_L b, x=D_R x'; "
    "factor 1 for exactly-zero rows/columns"
)
RESIDUAL_DEFINITION = (
    "r = A x - b recomputed on the original system; residual_norm = "
    "max-modulus norm max|r_i|"
)
BACKWARD_ERROR_DEFINITION = (
    "||r|| / (||A|| ||x|| + ||b||) with max-entry/modulus norms; "
    "0/0 with zero residual -> 0; never NaN/Infinity"
)


def _canonical_problem(problem: ComplexLinearProblem) -> dict:
    def _num(e):
        if isinstance(e, RationalComplex):
            return {"re": str(e.re), "im": str(e.im)}
        return {"re": format(e.re, "f"), "im": format(e.im, "f")}

    return {
        "engine": SOLVER_VERSION,
        "mode_policies": {
            "pivot_exact": PIVOT_POLICY_EXACT,
            "pivot_hp": PIVOT_POLICY_HP,
            "scaling_exact": SCALING_POLICY_EXACT,
            "scaling_hp": SCALING_POLICY_HP,
            "residual": RESIDUAL_DEFINITION,
            "backward_error": BACKWARD_ERROR_DEFINITION,
            "be_tol": str(BE_TOL),
            "pivot_floor": str(PIVOT_FLOOR),
            "rhs_floor_rel": str(RHS_FLOOR_REL),
        },
        "n": problem.n,
        "kind": problem.kind,
        "input_promoted": problem.input_promoted,
        "A": [[_num(e) for e in row] for row in problem.matrix.rows],
        "b": [_num(e) for e in problem.rhs],
    }


def _digest(canonical: dict, mode: NumericMode) -> str:
    doc = json.dumps(
        {"mode": mode.value, "problem": canonical}, sort_keys=True, default=str
    )
    return hashlib.sha256(doc.encode()).hexdigest()


def solve(
    problem: ComplexLinearProblem,
    mode: NumericMode = NumericMode.AUTO,
) -> LinearSolveResult:
    """Solve ``problem`` under ``mode`` (default AUTO)."""
    if not isinstance(problem, ComplexLinearProblem):
        raise InvalidModeError(
            f"solve needs a ComplexLinearProblem, got {type(problem).__name__}"
        )
    if not isinstance(mode, NumericMode):
        raise InvalidModeError(f"mode must be a NumericMode, got {mode!r}")
    if mode == NumericMode.AUTO:
        mode = NumericMode.EXACT if problem.kind == "rational" else NumericMode.HIGH_PRECISION
    if mode == NumericMode.EXACT and problem.kind != "rational":
        raise InvalidModeError(
            "EXACT mode requires a rational problem (decimal data cannot "
            "be solved exactly without faking exactness)"
        )
    canonical = _canonical_problem(problem)
    digest = _digest(canonical, mode)
    diagnostics: list[str] = [
        f"engine={SOLVER_VERSION}",
        f"mode={mode.value}",
        f"n={problem.n}",
        f"input_promoted={problem.input_promoted}",
    ]
    if mode == NumericMode.EXACT:
        status, solution, rank_A, rank_aug = exact_solve(
            problem.matrix.rows, problem.rhs
        )
        diagnostics.append("exact elimination over RationalComplex; no tolerances")
        if solution is not None:
            zero = RationalComplex.zero()
            residual = tuple(zero for _ in range(problem.n))
            residual_norm: Decimal | None = Decimal(0)
            backward_error: Decimal | None = Decimal(0)
        else:
            residual = None
            residual_norm = None
            backward_error = None
        provenance = {
            "engine": SOLVER_VERSION,
            "version": SOLVER_VERSION,
            "numeric_mode": mode.value,
            "matrix_dimension": problem.n,
            "rank_A": rank_A,
            "rank_augmented": rank_aug,
            "status": status.value,
            "precision": None,
            "precision_note": "exact arithmetic has no finite working precision",
            "pivot_policy": PIVOT_POLICY_EXACT,
            "scaling_policy": SCALING_POLICY_EXACT,
            "residual_definition": RESIDUAL_DEFINITION,
            "backward_error_definition": BACKWARD_ERROR_DEFINITION,
            "input_promoted": problem.input_promoted,
        }
        return LinearSolveResult(
            status=status, solution=solution, numeric_mode=mode,
            working_precision=None, rank_A=rank_A, rank_augmented=rank_aug,
            residual=residual, residual_norm=residual_norm,
            backward_error=backward_error, scaling_applied=False,
            growth_factor=Decimal(1),
            diagnostics=tuple(diagnostics), provenance=provenance, digest=digest,
        )
    out = _hp_on_decimal(problem, diagnostics)
    status = out["status"]
    diagnostics.extend(out["notes"])
    input_promoted = problem.input_promoted or out["promoted_here"]
    provenance = {
        "engine": SOLVER_VERSION,
        "version": SOLVER_VERSION,
        "numeric_mode": mode.value,
        "matrix_dimension": problem.n,
        "rank_A": out["rank_A"],
        "rank_augmented": out["rank_augmented"],
        "status": status.value,
        "precision": WORKING_PRECISION,
        "pivot_policy": PIVOT_POLICY_HP,
        "scaling_policy": SCALING_POLICY_HP,
        "residual_definition": RESIDUAL_DEFINITION,
        "backward_error_definition": BACKWARD_ERROR_DEFINITION,
        "be_tol": str(BE_TOL),
        "pivot_floor": str(PIVOT_FLOOR),
        "rhs_floor_rel": str(RHS_FLOOR_REL),
        "input_promoted": input_promoted,
    }
    return LinearSolveResult(
        status=status, solution=out["solution"], numeric_mode=mode,
        working_precision=WORKING_PRECISION, rank_A=out["rank_A"],
        rank_augmented=out["rank_augmented"], residual=out["residual"],
        residual_norm=out["residual_norm"], backward_error=out["backward_error"],
        scaling_applied=True, growth_factor=out["growth_factor"],
        diagnostics=tuple(diagnostics), provenance=provenance, digest=digest,
    )


def _hp_on_decimal(
    problem: ComplexLinearProblem, diagnostics: list[str]
) -> dict:
    """Run the HP elimination, promoting rational inputs first if needed.

    Promotion is the allowed exact -> approximate direction (each entry
    rounded once under the working context) and is recorded in
    diagnostics/provenance — never silent.
    """
    promoted_here = False
    if problem.kind == "rational":
        A = tuple(
            tuple(DecimalComplex.from_rational(e) for e in row)
            for row in problem.matrix.rows
        )
        b = tuple(DecimalComplex.from_rational(e) for e in problem.rhs)
        promoted_here = True
        diagnostics.append(
            "rational inputs promoted to DecimalComplex under the working "
            "context for HIGH_PRECISION mode (allowed direction, recorded)"
        )
    else:
        A, b = problem.matrix.rows, problem.rhs
    out = hp_solve(A, b)
    out["promoted_here"] = promoted_here
    return out


def matvec(
    A: tuple, x: tuple
) -> tuple:
    """Matrix-vector product with D1 arithmetic (also used to verify EXACT)."""
    out = []
    for row in A:
        acc = None
        for a, xi in zip(row, x):
            term = a * xi
            acc = term if acc is None else acc + term
        out.append(acc)
    return tuple(out)


def conjugate_system(problem: ComplexLinearProblem) -> ComplexLinearProblem:
    """Return the entrywise-conjugated problem (metamorphic helper)."""
    A = [[e.conjugate() for e in row] for row in problem.matrix.rows]
    b = [e.conjugate() for e in problem.rhs]
    return ComplexLinearProblem.from_sequences(A, b)
