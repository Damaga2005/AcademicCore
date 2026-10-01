"""Engineering application service (Phase 6): projects, circuits, calculations.

Coordinates domain + EngineeringRepository + doc links. Simulation backends
are exposed read-only (detect/validate/mock) — never executed here. No Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from academic_core.domain.engineering import calc as C
from academic_core.domain.engineering import gum as G
from academic_core.domain.engineering import simulation as S
from academic_core.domain.engineering.circuit import (
    Circuit, CircuitError, Component, EngineeringProject,
)
from academic_core.domain.engineering.units import Quantity, parse_quantity


@dataclass(frozen=True)
class ParamSpec:
    """One model parameter the student fills in: what it is, a textbook default, how to read it."""
    key: str
    label: str
    default: str
    kind: str = "qty"          # qty | kp | lambda | text | net | ref
    choices: tuple = ()        # for text parameters that are a fixed set (polarity)


@dataclass(frozen=True)
class ComponentSpec:
    type: str
    name: str                  # what the student calls it
    pins: tuple                # ((pin, label), ...)
    value_label: str = ""      # "" = this component has no value
    value_default: str = ""
    params: tuple = ()         # ParamSpec...


_VT = ParamSpec("Vt", "Tensión térmica Vt", "25.85 mV")
_POL = lambda choices: ParamSpec("polarity", "Polaridad", choices[0], "text", choices)  # noqa: E731

COMPONENT_SPECS: dict[str, ComponentSpec] = {s.type: s for s in (
    ComponentSpec("R", "Resistencia", (("1", "Nodo 1"), ("2", "Nodo 2")), "Valor", "1 kohm"),
    ComponentSpec("C", "Condensador", (("1", "Nodo 1"), ("2", "Nodo 2")), "Valor", "1 uF"),
    ComponentSpec("L", "Bobina", (("1", "Nodo 1"), ("2", "Nodo 2")), "Valor", "10 mH"),
    ComponentSpec("V", "Fuente de tensión", (("+", "Nodo +"), ("-", "Nodo −")), "Valor", "5 V"),
    ComponentSpec("I", "Fuente de corriente", (("+", "Nodo +"), ("-", "Nodo −")), "Valor", "1 mA"),
    ComponentSpec("D", "Diodo", (("A", "Ánodo"), ("K", "Cátodo")), params=(
        ParamSpec("Is", "Corriente de saturación Is", "1e-14 A"),
        ParamSpec("n", "Factor de idealidad n", "1"), _VT)),
    ComponentSpec("Q", "Transistor bipolar", (("C", "Colector"), ("B", "Base"), ("E", "Emisor")), params=(
        _POL(("NPN", "PNP")),
        ParamSpec("Is", "Corriente de saturación Is", "1e-14 A"),
        ParamSpec("Bf", "Ganancia directa Bf", "100"), ParamSpec("Br", "Ganancia inversa Br", "1"),
        ParamSpec("Nf", "Idealidad directa Nf", "1"), ParamSpec("Nr", "Idealidad inversa Nr", "1"), _VT)),
    ComponentSpec("M", "MOSFET", (("D", "Drenador"), ("G", "Puerta"), ("S", "Surtidor"), ("B", "Sustrato")),
                  params=(_POL(("NMOS", "PMOS")),
                          ParamSpec("Kp", "Transconductancia Kp (A/V²)", "0.0002", "kp"),
                          ParamSpec("Vto", "Umbral Vto", "1 V"),
                          ParamSpec("Lambda", "Modulación de canal λ (1/V)", "0.02", "lambda"),
                          ParamSpec("Phi", "Potencial de superficie Φ", "0.6 V"),
                          ParamSpec("Gamma", "Efecto de sustrato γ", "0.5"))),
    ComponentSpec("J", "JFET", (("D", "Drenador"), ("G", "Puerta"), ("S", "Surtidor")), params=(
        _POL(("NCHAN", "PCHAN")), ParamSpec("Idss", "Corriente Idss", "0.01 A"),
        ParamSpec("Vp", "Tensión de estrangulamiento Vp", "3 V"),
        ParamSpec("Lambda", "Modulación de canal λ (1/V)", "0.01", "lambda"))),
    ComponentSpec("E", "Fuente de tensión controlada por tensión", (("+", "Salida +"), ("-", "Salida −")),
                  "Ganancia", "2", (ParamSpec("cp", "Control + (nodo)", "", "net"),
                                    ParamSpec("cn", "Control − (nodo)", "0", "net"))),
    ComponentSpec("G", "Fuente de corriente controlada por tensión", (("+", "Salida +"), ("-", "Salida −")),
                  "Transconductancia", "1 mS", (ParamSpec("cp", "Control + (nodo)", "", "net"),
                                                ParamSpec("cn", "Control − (nodo)", "0", "net"))),
    ComponentSpec("H", "Fuente de tensión controlada por corriente", (("+", "Salida +"), ("-", "Salida −")),
                  "Transresistencia", "1 kohm", (ParamSpec("control_ref", "Fuente que mide (ref)", "", "ref"),)),
    ComponentSpec("F", "Fuente de corriente controlada por corriente", (("+", "Salida +"), ("-", "Salida −")),
                  "Ganancia", "2", (ParamSpec("control_ref", "Fuente que mide (ref)", "", "ref"),)),
    ComponentSpec("O", "Amplificador operacional ideal", (("+", "Entrada +"), ("-", "Entrada −"), ("o", "Salida"))),
    ComponentSpec("T", "Transformador ideal", (("1", "Primario +"), ("2", "Primario −"),
                                               ("3", "Secundario +"), ("4", "Secundario −")),
                  "Relación de vueltas n", "2"),
)}


@dataclass(frozen=True)
class OnePortView:
    """Plain-string Thevenin/Norton result for a port (widgets never see domain objects)."""
    status: str            # the engine's status: verified, solved, unsupported, invalid_port...
    v_th: str = ""
    r_th: str = ""
    i_n: str = ""
    r_n: str = ""
    equivalent: bool = False   # Vth == In * Rth, checked exactly by the engine
    loads_passed: int = 0      # test-resistor comparisons original vs equivalent
    loads_total: int = 0
    diagnostics: tuple = ()

    @property
    def ok(self) -> bool:
        return self.status in ("verified", "solved")


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

    def component_types(self) -> list[tuple[str, str]]:
        """``[(type, name)]`` in the order the picker shows them."""
        return [(t, sp.name) for t, sp in COMPONENT_SPECS.items()]

    def component_spec(self, ctype: str) -> ComponentSpec:
        try:
            return COMPONENT_SPECS[str(ctype).upper()]
        except KeyError:
            raise ValueError(f"unknown component type: {ctype}") from None

    def next_ref(self, circuit: Circuit | None, ctype: str) -> str:
        """First free reference for a type: R1, R2, ..."""
        used = {c.ref.upper() for c in (circuit.components if circuit else [])}
        n = 1
        while f"{ctype.upper()}{n}" in used:
            n += 1
        return f"{ctype.upper()}{n}"

    def make_parameters(self, ctype: str, raw: dict) -> dict:
        """Turn the text the student typed into the typed parameters the engine requires."""
        from academic_core.domain.engineering.mna.analysis import KP_DIM, LAMBDA_DIM
        from academic_core.domain.engineering.units import Unit
        out: dict = {}
        for p in self.component_spec(ctype).params:
            text = str(raw.get(p.key, "") or "").strip()
            if not text:
                raise ValueError(f"falta el parámetro {p.key}")
            if p.kind in ("text", "net", "ref"):
                out[p.key] = text.upper() if p.kind == "ref" else text
            elif p.kind in ("kp", "lambda"):
                number = parse_quantity(text).value  # a plain number: the unit is fixed by the parameter
                unit = Unit("A/V2", "A", "", KP_DIM, Decimal(1)) if p.kind == "kp" \
                    else Unit("1/V", "V", "", LAMBDA_DIM, Decimal(1))
                out[p.key] = Quantity(number, unit)
            else:
                out[p.key] = parse_quantity(text)
        return out

    def circuit_warnings(self, circuit: Circuit) -> list[str]:
        return circuit.validate()

    def one_port(self, circuit: Circuit, positive: str, negative: str) -> OnePortView:
        """Thevenin + Norton equivalents seen from two nets, from the certified F8-C engine.

        Circuits with C, L, diodes or transistors are outside its linear-DC domain: the engine
        answers ``unsupported`` with the reason and that is what the caller shows.
        """
        from academic_core.domain.engineering.thevenin.analysis import analyze_one_port
        from academic_core.domain.engineering.thevenin.errors import InvalidPortError
        from academic_core.domain.engineering.thevenin.port import TheveninPort
        try:
            port = TheveninPort(positive, negative)
        except InvalidPortError as exc:
            return OnePortView("invalid_port", diagnostics=(str(exc),))
        r = analyze_one_port(circuit, port)
        t, n = r.thevenin, r.norton

        def fmt(q):
            return q.format() if q is not None else ""

        loads = tuple(getattr(t, "load_verifications", ()) or ())
        return OnePortView(
            status=t.status.value, v_th=fmt(t.v_th), r_th=fmt(t.r_th) or t.resistance_kind.value,
            i_n=fmt(n.i_n), r_n=fmt(n.r_n) or n.resistance_kind.value, equivalent=bool(r.is_equivalent),
            loads_passed=sum(1 for v in loads if v.passed), loads_total=len(loads),
            diagnostics=tuple(t.diagnostics or r.diagnostics or ()))

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

