"""Engineering application service (Phase 6): projects, circuits, calculations.

Coordinates domain + EngineeringRepository + doc links. Simulation backends
are exposed read-only (detect/validate/mock) — never executed here. No Qt.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from academic_core.domain.engineering import calc as C
from academic_core.domain.engineering import gum as G
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

    # -- F15 UI helpers: widgets must not import domain.circuit (AI-002) ---
    def new_circuit(self, name: str) -> Circuit:
        return Circuit(name)

    def component_pins(self, ctype: str) -> tuple:
        from academic_core.domain.engineering.circuit import COMPONENT_PINS
        try:
            return tuple(COMPONENT_PINS[str(ctype).upper()])
        except KeyError:
            raise ValueError(f"unknown component type: {ctype}") from None

    def circuit_warnings(self, circuit: Circuit) -> list[str]:
        return circuit.validate()

    def backend_status_lines(self) -> list[str]:
        lines = [f"null: detected={self.backend.detect()} (NOT IMPLEMENTED, F7)"]
        if isinstance(self.backend, S.MockSimulationBackend):
            lines.append("mock: active (prefixed results, tests only)")
        return lines

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

    def simulate_circuit(self, project: str, circuit_name: str,
                         analyses: tuple[Any, ...] = ("op",),
                         backend: S.SimulationBackend | None = None) -> S.SimulationResult:
        circuit = self.repo.load_circuit(project, circuit_name)
        if circuit is None:
            raise ValueError(f"unknown circuit: {circuit_name}")
        b = backend or self.backend
        netlist = circuit.to_netlist()
        return b.simulate(netlist, analyses=analyses)

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

    # -- measurement uncertainty (GUM) --------------------------------------------
    def evaluate_measurement_uncertainty(
        self,
        model: G.MeasurementModel,
        inputs: dict[str, G.InputQuantity],
        correlation: G.CorrelationMatrix | None = None,
        coverage_probability: float = 0.95,
        explicit_k: float | Decimal | None = None,
        cas_store: Any | None = None,
    ) -> G.GUMResult:
        return G.evaluate_gum(
            model=model,
            inputs=inputs,
            correlation=correlation,
            coverage_probability=coverage_probability,
            explicit_k=explicit_k,
            cas_store=cas_store,
        )

    # -- structural circuit analysis (F7-B8) --------------------------------------
    def analyze_circuit_structure(
        self,
        project: str,
        circuit_name: str,
        target_terminals: tuple[str, str] | None = None,
        at: str | None = None,
    ):
        circuit = self.repo.load_circuit(project, circuit_name)
        if circuit is None:
            raise ValueError(f"unknown circuit: {circuit_name}")
        from academic_core.domain.engineering.structural import StructuralCircuitAnalyzer
        analyzer = StructuralCircuitAnalyzer()
        return analyzer.analyze(circuit, target_terminals=target_terminals, at=at)

    def analyze_circuit(
        self,
        circuit: Circuit,
        target_terminals: tuple[str, str] | None = None,
        at: str | None = None,
    ):
        from academic_core.domain.engineering.structural import StructuralCircuitAnalyzer
        analyzer = StructuralCircuitAnalyzer()
        return analyzer.analyze(circuit, target_terminals=target_terminals, at=at)

    # -- electronics knowledge recognition (F8-A) ---------------------------------
    def recognize_electronics_concepts(
        self,
        circuit: Circuit,
        target_terminals: tuple[str, str] | None = None,
        at: str | None = None,
    ):
        """B8 structural plan -> deterministic electronics concept candidates.

        Adapter only: builds on `analyze_circuit`'s certified B8 plan, never
        re-derives or modifies structural recognition.
        """
        from academic_core.domain.electronics import ElectronicsConceptRecognizer
        plan = self.analyze_circuit(circuit, target_terminals=target_terminals, at=at)
        candidates = ElectronicsConceptRecognizer().recognize(plan)
        return plan, candidates

