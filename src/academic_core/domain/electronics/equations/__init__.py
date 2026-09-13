"""ElectronicsEquation registry (Phase 8-A).

Reuses F6/F7's real equation engine (`academic_core.domain.engineering
.equations.parse_equation` / `evaluate`) for exact representation and
evaluation — never re-implements formula parsing. Where a formula already
exists in F6/F7's curated library (`engineering.calc.LIBRARY`), it is
referenced from there (read-only) instead of being redeclared; only formulas
absent from that library are declared here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from academic_core.domain.engineering.calc import LIBRARY as _F6_LIBRARY
from academic_core.domain.engineering.equations import Equation, parse_equation
from academic_core.domain.electronics.types import provenance

EQUATIONS_VERSION = "f8a-equations/1.0"


@dataclass(frozen=True)
class ElectronicsEquation:
    """A structured, traceable equation entry (section 10)."""

    stable_id: str  # "equation:<name>"
    equation: Equation
    dimension: str  # DIM_NAMES value the output must carry
    validity: str  # plain-language validity condition
    provenance: dict = field(default_factory=dict)

    @property
    def expression(self) -> str:
        return self.equation.source

    @property
    def variables(self) -> tuple:
        return self.equation.variables


def _from_f6(key: str, stable_id: str, validity: str) -> ElectronicsEquation:
    entry = _F6_LIBRARY[key]
    return ElectronicsEquation(
        stable_id=stable_id,
        equation=parse_equation(entry["source"]),
        dimension=entry["dim"],
        validity=validity,
        provenance=provenance(stable_id),
    )


def _new(stable_id: str, source: str, dimension: str, validity: str) -> ElectronicsEquation:
    return ElectronicsEquation(
        stable_id=stable_id,
        equation=parse_equation(source),
        dimension=dimension,
        validity=validity,
        provenance=provenance(stable_id),
    )


# -- reused verbatim from F6's curated library (never redeclared) ------------
_REUSED = (
    _from_f6("ohm-v", "equation:ohm-v", "resistor obeys Ohm's law (linear, ideal)"),
    _from_f6("ohm-i", "equation:ohm-i", "resistor obeys Ohm's law (linear, ideal)"),
    _from_f6("ohm-r", "equation:ohm-r", "resistor obeys Ohm's law (linear, ideal)"),
    _from_f6("power-vi", "equation:power-vi", "instantaneous power, any two-terminal element"),
    _from_f6("power-i2r", "equation:power-i2r", "resistive dissipation, ideal resistor"),
    _from_f6("power-v2r", "equation:power-v2r", "resistive dissipation, ideal resistor"),
    _from_f6("voltage-divider", "equation:voltage-divider",
             "two-resistor series divider, no loading at the tap"),
)

# -- new: not present in F6's library, needed for F8-A initial coverage ------
_NEW = (
    _new("equation:series-resistors", "Req = R1 + R2", "resistance",
         "two ideal resistors in series"),
    _new("equation:parallel-resistors", "Req = (R1 * R2) / (R1 + R2)", "resistance",
         "two ideal resistors in parallel"),
    _new("equation:current-divider", "I1 = Itot * R2 / (R1 + R2)", "current",
         "two-branch resistive current divider"),
    _new("equation:bridge-balance", "balance_ratio = (R1 * R4) / (R2 * R3)", "dimensionless",
         "Wheatstone bridge; balanced when ratio == 1"),
)

EQUATIONS: dict[str, ElectronicsEquation] = {
    e.stable_id: e for e in (*_REUSED, *_NEW)
}


def get(stable_id: str) -> ElectronicsEquation:
    return EQUATIONS[stable_id]


__all__ = ["ElectronicsEquation", "EQUATIONS", "EQUATIONS_VERSION", "get"]
