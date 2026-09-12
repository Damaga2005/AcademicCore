"""Engineering / Simulation / Lab / Measurement stubs (Phase 0 boundaries).

Canonical Circuit model is backend-agnostic (ADR-0008):
Circuit -> Netlist Generator -> Backend (ngspice/LTspice/KiCad) -> Result -> Analysis.
No per-backend circuit models. Certification states in domain.status.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Component:
    ref: str  # R1, C3, Q2...
    kind: str
    value: str
    nodes: tuple[str, ...] = ()


@dataclass
class Circuit:
    stable_id: str
    components: list[Component] = field(default_factory=list)
    parameters: dict = field(default_factory=dict)

    def to_netlist(self) -> str:
        lines = [f"* {self.stable_id}"]
        for c in self.components:
            lines.append(f"{c.ref} {' '.join(c.nodes)} {c.value}")
        lines.append(".end")
        return "\n".join(lines)


@dataclass
class Measurement:
    quantity: str
    value: float
    unit: str
    uncertainty: float = 0.0
    provenance: dict = field(default_factory=dict)


@dataclass
class Experiment:
    stable_id: str
    circuit_id: str = ""
    measurements: list[Measurement] = field(default_factory=list)
    dataset_ref: str = ""
    report_ref: str = ""
