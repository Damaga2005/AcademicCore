"""Engineering application service (Phase 6): projects, circuits, calculations.

Coordinates domain + EngineeringRepository + doc links. Simulation backends
are exposed read-only (detect/validate/mock) — never executed here. No Qt.
"""

from __future__ import annotations

from academic_core.domain.engineering import calc as C
from academic_core.domain.engineering import simulation as S
from academic_core.domain.engineering.circuit import (
    Circuit, CircuitError, Component, EngineeringProject,
)
from academic_core.domain.engineering.units import Quantity, parse_quantity


class EngineeringService:
    def __init__(self, repo, authoring_store=None):
        self.repo = repo
        self.authoring_store = authoring_store
        self.backend: S.SimulationBackend = S.NullSimulationBackend()

    # -- projects --------------------------------------------------------------
    def create_project(self, name: str, subject_id: str = "",
                       topic_id: str = "", description: str = "") -> EngineeringProject:
        p = EngineeringProject(name.strip(), subject_id, topic_id, description)
        if self.repo.get_project(p.name) is not None:
            raise ValueError(f"project exists: {p.name}")
        self.repo.save_project(p)
        return p

    def use_mock_backend(self, payload: dict | None = None) -> None:
        self.backend = S.MockSimulationBackend(payload)

    # -- circuits ------------------------------------------------------------------
    def save_circuit(self, project: str, circuit: Circuit, notes: str = "") -> list[str]:
        if self.repo.get_project(project) is None:
            raise ValueError(f"unknown project: {project}")
        warnings = circuit.validate()
        self.repo.save_circuit(project, circuit, notes)
        return warnings

    def add_component(self, project: str, circuit_name: str, type: str, ref: str,
                      value: str, pins: dict, parameters: dict | None = None) -> Circuit:
        circuit = self.repo.load_circuit(project, circuit_name)
        if circuit is None:
            circuit = Circuit(circuit_name)
        qty = parse_quantity(value) if value.strip() else None
        circuit.add(Component(ref.strip().upper(), type.strip().upper(), qty,
                              dict(pins), dict(parameters or {})))
        self.repo.save_circuit(project, circuit)
        return circuit

    def netlist(self, project: str, circuit_name: str) -> str:
        circuit = self.repo.load_circuit(project, circuit_name)
        if circuit is None:
            raise ValueError(f"unknown circuit: {circuit_name}")
        return circuit.to_netlist()

    # -- calculations ------------------------------------------------------------------
    def calculate(self, inputs: dict[str, str], source: str, project: str = "",
                  circuit: str = "", name: str = "") -> C.CalculationResult:
        qtys = {k: parse_quantity(v) for k, v in inputs.items()}
        result = C.calculate(qtys, source)
        self.repo.save_calculation(result, project, circuit)
        return result

    def library(self) -> dict:
        return dict(C.LIBRARY)

    def calculate_library(self, key: str, inputs: dict[str, str],
                          project: str = "") -> C.CalculationResult:
        entry = C.LIBRARY.get(key)
        if entry is None:
            raise ValueError(f"unknown library entry: {key}")
        return self.calculate(inputs, entry["source"], project, entry["dim"])

    # -- authoring links -------------------------------------------------------------------
    def link_to_document(self, resource_id: str, kind: str, ref: str) -> None:
        if self.authoring_store is None:
            raise ValueError("authoring store not wired")
        if kind not in ("calculation", "circuit"):
            raise ValueError(f"engineering link kind: {kind}")
        if not ref:
            raise ValueError("empty link reference")
        self.authoring_store.add_link(resource_id, kind, ref)
