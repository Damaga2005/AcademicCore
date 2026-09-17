"""General Linear Circuit Solver (Phase F8-B): Modified Nodal Analysis.

Solves DC linear resistive networks with ideal independent voltage and
current sources, for arbitrary topology (not just series/parallel), using
Modified Nodal Analysis (MNA):

    A x = z

derived from KCL, resistor constitutive equations, and voltage-source
constraints. `x` holds node voltages (relative to a single reference/GND
node) and the unknown currents through ideal voltage sources.

The linear algebra is exact rational arithmetic (`fractions.Fraction`), not
floating point and not numpy/scipy: every value entering the matrix is
derived from a `Quantity` (Decimal), and `Fraction(Decimal(...))` is an
exact, lossless conversion. Gaussian elimination over exact rationals means
singularity is `pivot == 0` exactly — no numerical tolerance is needed to
tell SOLVED from SINGULAR/INCONSISTENT. Decimal rounding happens only when
converting the exact solution back to `Quantity` for presentation.

Public API:
    solve_linear_dc(circuit) -> AnalysisResult
    build_mna_problem(circuit) -> MNAProblem   (diagnostic/audit layer)

Domain covered: DC linear networks built from R (resistor), V (ideal
independent voltage source), I (ideal independent current source),
linear dependent sources E (VCVS), G (VCCS), H (CCVS), F (CCCS) and
ideal op-amps O (nullor: V+ = V-, zero input current) of
`academic_core.domain.engineering.circuit.Circuit`, with a
single GND/reference net named "0" or "GND" (case-insensitive), of
arbitrary topology and arbitrary node/branch count. Reactive elements
(C, L) and higher semiconductors (Q) are NOT_SUPPORTED and
raise `UnsupportedElementError` rather than being silently ignored.
The Shockley diode (D) is validated here but carries no linear stamp:
the linear solver reports it UNSUPPORTED and refers to
`solve_nonlinear_dc` (F8-H operating point).
"""

from __future__ import annotations

from academic_core.domain.engineering.mna.dependent import (
    DEPENDENT_TYPES,
    DependentGraph,
    describe_dependents,
)
from academic_core.domain.engineering.mna.diode import (
    DiodeParams,
    companion,
    extract_diode_params,
    shockley_conductance,
    shockley_current,
)
from academic_core.domain.engineering.mna.bjt import (
    BJTParams,
    bjt_companion,
    bjt_conductances,
    bjt_injection_currents,
    bjt_jacobian,
    bjt_terminal_currents,
    extract_bjt_params,
)
from academic_core.domain.engineering.mna.nonlinear import (
    NonlinearResult,
    NonlinearStatus,
    solve_nonlinear_dc,
)
from academic_core.domain.engineering.mna.errors import (
    CircularControlError,
    DimensionalityError,
    FloatingCircuitError,
    InconsistentSystemError,
    InvalidCircuitError,
    MissingReferenceError,
    NumericalSolveError,
    SingularSystemError,
    UnsupportedElementError,
)
from academic_core.domain.engineering.mna.problem import MNAProblem, build_mna_problem
from academic_core.domain.engineering.mna.result import (
    AnalysisResult,
    BranchCurrent,
    ConservationChecks,
    ElementPower,
    NodeVoltage,
    SolveStatus,
)
from academic_core.domain.engineering.mna.solver import (
    SOLVER_VERSION,
    fundamental_cycle_chords,
    solve_linear_dc,
)

__all__ = [
    "solve_linear_dc",
    "solve_nonlinear_dc",
    "NonlinearResult",
    "NonlinearStatus",
    "DiodeParams",
    "companion",
    "extract_diode_params",
    "shockley_conductance",
    "shockley_current",
    "BJTParams",
    "bjt_companion",
    "bjt_conductances",
    "bjt_injection_currents",
    "bjt_jacobian",
    "bjt_terminal_currents",
    "extract_bjt_params",
    "build_mna_problem",
    "MNAProblem",
    "fundamental_cycle_chords",
    "DEPENDENT_TYPES",
    "DependentGraph",
    "describe_dependents",
    "AnalysisResult",
    "NodeVoltage",
    "BranchCurrent",
    "ElementPower",
    "ConservationChecks",
    "SolveStatus",
    "SOLVER_VERSION",
    "CircularControlError",
    "DimensionalityError",
    "FloatingCircuitError",
    "InconsistentSystemError",
    "InvalidCircuitError",
    "MissingReferenceError",
    "NumericalSolveError",
    "SingularSystemError",
    "UnsupportedElementError",
]
