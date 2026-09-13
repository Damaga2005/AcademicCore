"""Structured result of a General Linear Circuit Solver run.

Mirrors the repo-wide dataclass-result convention (`AnalysisPlan`,
`SimulationResult`, `CalculationResult`): a frozen dataclass with an
explicit status, never a bare `dict[str, float]`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from academic_core.domain.engineering.units import Quantity


class SolveStatus(Enum):
    SOLVED = "solved"
    SINGULAR = "singular"
    INCONSISTENT = "inconsistent"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class NodeVoltage:
    node: str
    voltage: Quantity


@dataclass(frozen=True)
class BranchCurrent:
    ref: str
    current: Quantity
    convention: str


@dataclass(frozen=True)
class ElementPower:
    ref: str
    power: Quantity
    absorbed: bool


@dataclass(frozen=True)
class ConservationChecks:
    kcl_max_residual: str  # exact value, as a string ("0" when solved exactly)
    kvl_max_residual: str | None
    power_balance_residual: str
    tolerance: str
    passed: bool


@dataclass(frozen=True)
class AnalysisResult:
    status: SolveStatus
    node_voltages: tuple[NodeVoltage, ...] = ()
    branch_currents: tuple[BranchCurrent, ...] = ()
    element_powers: tuple[ElementPower, ...] = ()
    system_summary: dict = field(default_factory=dict)
    conservation_checks: ConservationChecks | None = None
    provenance: dict = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "node_voltages": {nv.node: nv.voltage.format() for nv in self.node_voltages},
            "branch_currents": {
                bc.ref: {"current": bc.current.format(), "convention": bc.convention}
                for bc in self.branch_currents
            },
            "element_powers": {
                ep.ref: {"power": ep.power.format(), "absorbed": ep.absorbed}
                for ep in self.element_powers
            },
            "system_summary": self.system_summary,
            "conservation_checks": (
                None
                if self.conservation_checks is None
                else {
                    "kcl_max_residual": self.conservation_checks.kcl_max_residual,
                    "kvl_max_residual": self.conservation_checks.kvl_max_residual,
                    "power_balance_residual": self.conservation_checks.power_balance_residual,
                    "tolerance": self.conservation_checks.tolerance,
                    "passed": self.conservation_checks.passed,
                }
            ),
            "provenance": self.provenance,
            "diagnostics": list(self.diagnostics),
        }
