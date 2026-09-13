"""Structured error hierarchy for the F8-B general linear circuit solver.

Follows the repo-wide convention (see `circuit.CircuitError`,
`units.UnitError`, `electronics.calc.GeneralityError`): flat, message-only
`ValueError` subclasses, one per distinct failure mode, each documenting the
invariant it guards. No shared base class exists elsewhere in the codebase,
so none is introduced here.
"""

from __future__ import annotations


class InvalidCircuitError(ValueError):
    """Raised for a circuit that is structurally malformed for MNA purposes:
    empty, duplicate references bypassing `Circuit.add`, or a component
    parameter outside its valid physical range (e.g. R <= 0)."""


class UnsupportedElementError(ValueError):
    """Raised when a component's type is outside F8-B's declared domain
    (only R, V, I are supported). Never silently ignored or dropped."""


class MissingReferenceError(ValueError):
    """Raised when no net named "0"/"GND" (case-insensitive) exists, or when
    more than one distinct net name matches that convention (ambiguous
    reference). The solver never invents a ground node."""


class FloatingCircuitError(ValueError):
    """Raised when one or more nodes have no path (through any R, V or I
    branch) to the reference node, so their absolute potential cannot be
    fixed. Detected by graph reachability, independent of node/branch
    count."""


class SingularSystemError(ValueError):
    """Raised when the MNA matrix is rank-deficient but consistent: the
    physical system admits infinitely many solutions (e.g. redundant
    equations), so no unique node-voltage assignment exists."""


class InconsistentSystemError(ValueError):
    """Raised when the MNA matrix is rank-deficient and inconsistent: the
    constraints contradict each other (e.g. incompatible ideal voltage
    sources forced onto the same pair of nodes), so no solution exists."""


class DimensionalityError(ValueError):
    """Raised when a component's `Quantity` value has the wrong physical
    dimension for its role (e.g. a resistor whose value is not a
    resistance)."""


class NumericalSolveError(ValueError):
    """Raised for a solve that fails for reasons other than SINGULAR or
    INCONSISTENT classification (e.g. a malformed internal matrix shape).
    Never converts an unexpected arithmetic exception into a fabricated
    `0` result."""
