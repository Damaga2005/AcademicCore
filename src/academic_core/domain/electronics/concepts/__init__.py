"""ElectronicsConcept registry (Phase 8-A).

The initial circuit-theory core (section 17): Ohm's law, KCL, KVL, series/
parallel resistors, voltage/current divider, Thevenin/Norton, resistive
bridge, and the general DC resistive network. Stable string IDs only —
never a numeric index (section 5).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from academic_core.domain.electronics.types import ConceptCategory, RelationType, provenance


@dataclass(frozen=True)
class ConceptRelation:
    kind: RelationType
    target: str  # target stable_id (concept:/model:/equation:/analysis:)


@dataclass(frozen=True)
class ElectronicsConcept:
    """A deterministic conceptual entity describing what a circuit *is* (section 3)."""

    stable_id: str  # "concept:<name>"
    name: str
    category: ConceptCategory
    description: str
    components: tuple[str, ...]  # component type letters, e.g. ("R",)
    topologies: tuple[str, ...]  # B8 TopologyType values this concept binds to
    level: str  # "introductory" | "intermediate" | "advanced"
    relations: tuple[ConceptRelation, ...] = ()
    common_errors: tuple[str, ...] = ()
    simulation_mapping: tuple[str, ...] = ()  # SPICE directive families
    provenance: dict = field(default_factory=dict)

    def targets(self, kind: RelationType) -> tuple[str, ...]:
        return tuple(r.target for r in self.relations if r.kind == kind)

    @property
    def prerequisites(self) -> tuple[str, ...]:
        return self.targets(RelationType.REQUIRES)

    @property
    def related(self) -> tuple[str, ...]:
        return self.targets(RelationType.RELATED_TO)


def _rel(kind: RelationType, *targets: str) -> tuple[ConceptRelation, ...]:
    return tuple(ConceptRelation(kind, t) for t in targets)


def _concept(stable_id, name, category, description, components, topologies,
             level, relations=(), common_errors=(), simulation_mapping=()) -> ElectronicsConcept:
    return ElectronicsConcept(
        stable_id, name, category, description, components, topologies, level,
        relations, common_errors, simulation_mapping, provenance(stable_id))


CONCEPTS: dict[str, ElectronicsConcept] = {
    c.stable_id: c for c in (
        _concept(
            "concept:ohms-law", "Ohm's law", ConceptCategory.CIRCUIT_LAW,
            "Linear relation V = I * R for an ideal resistor.",
            ("R",), ("SINGLE_RESISTOR", "RESISTIVE"), "introductory",
            relations=_rel(RelationType.USES_EQUATION, "equation:ohm-v", "equation:ohm-i", "equation:ohm-r")
            + _rel(RelationType.USES_MODEL, "model:resistor-ideal")
            + _rel(RelationType.USES_ANALYSIS, "analysis:ohms-law"),
            common_errors=("confusing V, I, R units", "sign convention on I"),
            simulation_mapping=(".op",),
        ),
        _concept(
            "concept:kcl", "Kirchhoff's Current Law", ConceptCategory.CIRCUIT_LAW,
            "Sum of currents into a node is zero.",
            (), (), "introductory",
            relations=_rel(RelationType.USES_ANALYSIS, "analysis:kcl"),
            common_errors=("inconsistent current reference direction",),
            simulation_mapping=(".op",),
        ),
        _concept(
            "concept:kvl", "Kirchhoff's Voltage Law", ConceptCategory.CIRCUIT_LAW,
            "Sum of voltages around a closed loop is zero.",
            (), (), "introductory",
            relations=_rel(RelationType.USES_ANALYSIS, "analysis:kvl"),
            common_errors=("inconsistent loop traversal direction",),
            simulation_mapping=(".op",),
        ),
        _concept(
            "concept:series-resistors", "Series resistors", ConceptCategory.CIRCUIT_ANALYSIS,
            "Two or more resistors sharing a single current path (degree-2 intermediate nodes).",
            ("R",), ("SERIES_RESISTORS",), "introductory",
            relations=_rel(RelationType.REQUIRES, "concept:ohms-law", "concept:kvl")
            + _rel(RelationType.USES_EQUATION, "equation:series-resistors")
            + _rel(RelationType.USES_MODEL, "model:resistor-ideal"),
            common_errors=("mistaking a shared node with 3+ branches for series",),
            simulation_mapping=(".op",),
        ),
        _concept(
            "concept:parallel-resistors", "Parallel resistors", ConceptCategory.CIRCUIT_ANALYSIS,
            "Two or more resistors sharing both terminal nodes.",
            ("R",), ("PARALLEL_RESISTORS",), "introductory",
            relations=_rel(RelationType.REQUIRES, "concept:ohms-law", "concept:kcl")
            + _rel(RelationType.USES_EQUATION, "equation:parallel-resistors")
            + _rel(RelationType.USES_MODEL, "model:resistor-ideal"),
            common_errors=("adding parallel resistances directly instead of reciprocals",),
            simulation_mapping=(".op",),
        ),
        _concept(
            "concept:voltage-divider", "Voltage divider", ConceptCategory.CIRCUIT_ANALYSIS,
            "Series resistor chain across a voltage source with an explicit output tap.",
            ("R", "V"), ("VOLTAGE_DIVIDER",), "introductory",
            relations=_rel(RelationType.REQUIRES, "concept:series-resistors")
            + _rel(RelationType.USES_EQUATION, "equation:voltage-divider", "equation:ohm-i")
            + _rel(RelationType.USES_ANALYSIS, "analysis:dc", "analysis:voltage-divider"),
            common_errors=("assuming the tap is loaded when nothing draws current from it",
                           "picking the wrong intermediate node as Vout"),
            simulation_mapping=(".op",),
        ),
        _concept(
            "concept:current-divider", "Current divider", ConceptCategory.CIRCUIT_ANALYSIS,
            "Parallel resistor branches sharing an injected total current.",
            ("R", "I"), ("PARALLEL_RESISTORS", "CURRENT_DIVIDER"), "introductory",
            relations=_rel(RelationType.REQUIRES, "concept:parallel-resistors")
            + _rel(RelationType.USES_EQUATION, "equation:current-divider")
            + _rel(RelationType.USES_ANALYSIS, "analysis:dc", "analysis:current-divider"),
            common_errors=("using the divider ratio the wrong way round (larger R gets less current)",),
            simulation_mapping=(".op",),
        ),
        _concept(
            "concept:resistive-bridge", "Resistive (Wheatstone) bridge", ConceptCategory.NETWORK_THEOREM,
            "Four resistors in a bridge arrangement, balanced when R1*R4 == R2*R3.",
            ("R",), ("RESISTIVE_BRIDGE",), "intermediate",
            relations=_rel(RelationType.REQUIRES, "concept:kcl", "concept:kvl")
            + _rel(RelationType.USES_EQUATION, "equation:bridge-balance"),
            common_errors=("assuming balance without checking the ratio",),
            simulation_mapping=(".op",),
        ),
        _concept(
            "concept:thevenin", "Thevenin equivalent", ConceptCategory.NETWORK_THEOREM,
            "Any linear resistive one-port reduced to a series source Vth and resistance Rth.",
            ("R", "V", "I"), (), "intermediate",
            relations=_rel(RelationType.REQUIRES, "concept:series-resistors", "concept:parallel-resistors")
            + _rel(RelationType.RELATED_TO, "concept:norton")
            + _rel(RelationType.USES_ANALYSIS, "analysis:thevenin"),
            common_errors=("forgetting to zero independent sources when computing Rth",),
            simulation_mapping=(".op",),
        ),
        _concept(
            "concept:norton", "Norton equivalent", ConceptCategory.NETWORK_THEOREM,
            "Any linear resistive one-port reduced to a parallel source In and resistance Rn.",
            ("R", "V", "I"), (), "intermediate",
            relations=_rel(RelationType.REQUIRES, "concept:thevenin")
            + _rel(RelationType.RELATED_TO, "concept:thevenin")
            + _rel(RelationType.USES_ANALYSIS, "analysis:norton"),
            common_errors=("mixing up Rn with Rth's dual instead of reusing the same value",),
            simulation_mapping=(".op",),
        ),
        _concept(
            "concept:dc-resistive-network", "DC resistive network", ConceptCategory.CIRCUIT_ANALYSIS,
            "General resistors-and-sources network under DC excitation, no reactive elements.",
            ("R", "V", "I"), ("RESISTIVE",), "introductory",
            relations=_rel(RelationType.REQUIRES, "concept:ohms-law", "concept:kcl", "concept:kvl")
            + _rel(RelationType.USES_ANALYSIS, "analysis:dc", "analysis:power"),
            common_errors=("forgetting to pick a reference (ground) node",),
            simulation_mapping=(".op",),
        ),
    )
}


def get(stable_id: str) -> ElectronicsConcept:
    return CONCEPTS[stable_id]


__all__ = ["ElectronicsConcept", "ConceptRelation", "CONCEPTS", "get"]
