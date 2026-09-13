"""ElectronicsConcept registry (Phase 8-A).

The initial circuit-theory core (section 17): Ohm's law, KCL, KVL, series/
parallel resistors, voltage/current divider, Thevenin/Norton, resistive
bridge, and the general DC resistive network. Stable string IDs only —
never a numeric index (section 5).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from academic_core.domain.electronics.types import ConceptCategory, Generality, RelationType, provenance


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
    generality: Generality = Generality.GENERAL
    parent: str | None = None  # concept stable_id this specializes, if SPECIAL_CASE
    domain_covered: str = ""  # what this concept's math actually covers (section 5)
    domain_not_covered: str = ""  # what it explicitly does NOT cover
    provenance: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.generality == Generality.SPECIAL_CASE and not self.parent:
            raise ValueError(f"{self.stable_id}: SPECIAL_CASE concept must declare parent")

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
             level, relations=(), common_errors=(), simulation_mapping=(),
             generality=Generality.GENERAL, parent=None,
             domain_covered="", domain_not_covered="") -> ElectronicsConcept:
    return ElectronicsConcept(
        stable_id, name, category, description, components, topologies, level,
        relations, common_errors, simulation_mapping, generality, parent,
        domain_covered, domain_not_covered, provenance(stable_id))


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
            "N >= 1 resistors sharing a single current path (degree-2 intermediate nodes). "
            "Req = sum(Ri); the two-resistor formula is one instance of this, not the definition.",
            ("R",), ("SERIES_RESISTORS",), "introductory",
            relations=_rel(RelationType.REQUIRES, "concept:ohms-law", "concept:kvl")
            + _rel(RelationType.USES_LAW, "law:series-resistors")
            + _rel(RelationType.USES_MODEL, "model:resistor-ideal"),
            common_errors=("mistaking a shared node with 3+ branches for series",),
            simulation_mapping=(".op",),
            domain_covered="any number (N>=1) of ideal resistors on one shared current path",
            domain_not_covered="branched topologies; non-ideal/temperature-dependent resistors",
        ),
        _concept(
            "concept:parallel-resistors", "Parallel resistors", ConceptCategory.CIRCUIT_ANALYSIS,
            "N >= 1 resistors sharing both terminal nodes. 1/Req = sum(1/Ri); the two-resistor "
            "product-over-sum formula is one instance of this, not the definition.",
            ("R",), ("PARALLEL_RESISTORS",), "introductory",
            relations=_rel(RelationType.REQUIRES, "concept:ohms-law", "concept:kcl")
            + _rel(RelationType.USES_LAW, "law:parallel-resistors")
            + _rel(RelationType.USES_MODEL, "model:resistor-ideal"),
            common_errors=("adding parallel resistances directly instead of reciprocals",),
            simulation_mapping=(".op",),
            domain_covered="any number (N>=1) of ideal resistors sharing both terminal nodes",
            domain_not_covered="branches that do not share both terminals; non-ideal resistors",
        ),
        _concept(
            "concept:voltage-divider", "Voltage divider", ConceptCategory.CIRCUIT_ANALYSIS,
            "Series resistor chain of any length across a voltage source with an explicit, "
            "never-inferred output tap. Vout = Vin * (R below tap) / (R total); unloaded only.",
            ("R", "V"), ("VOLTAGE_DIVIDER",), "introductory",
            relations=_rel(RelationType.REQUIRES, "concept:series-resistors")
            + _rel(RelationType.USES_LAW, "law:voltage-divider")
            + _rel(RelationType.USES_EQUATION, "equation:ohm-i")
            + _rel(RelationType.USES_ANALYSIS, "analysis:dc", "analysis:voltage-divider"),
            common_errors=("assuming the tap is loaded when nothing draws current from it",
                           "picking the wrong intermediate node as Vout"),
            simulation_mapping=(".op",),
            domain_covered="unloaded series chain of any length (N>=1 resistors), explicit tap node",
            domain_not_covered="a loaded tap (current drawn changes the ratio) — see analysis:voltage-divider",
        ),
        _concept(
            "concept:two-resistor-divider", "Two-resistor voltage divider",
            ConceptCategory.CIRCUIT_ANALYSIS,
            "The N=2 instance of concept:voltage-divider: Vout = Vin * R2 / (R1 + R2).",
            ("R", "V"), ("VOLTAGE_DIVIDER",), "introductory",
            relations=_rel(RelationType.IS_A, "concept:voltage-divider")
            + _rel(RelationType.USES_EQUATION, "equation:voltage-divider-pair"),
            simulation_mapping=(".op",),
            generality=Generality.SPECIAL_CASE, parent="concept:voltage-divider",
            domain_covered="exactly two series resistors, unloaded tap between them",
            domain_not_covered="N != 2; see concept:voltage-divider for the general chain",
        ),
        _concept(
            "concept:current-divider", "Current divider", ConceptCategory.CIRCUIT_ANALYSIS,
            "N >= 2 parallel resistive branches sharing an injected total current. "
            "I_k = Itot * G_k / sum(G_i); the two-branch formula is one instance of this.",
            ("R", "I"), ("PARALLEL_RESISTORS", "CURRENT_DIVIDER"), "introductory",
            relations=_rel(RelationType.REQUIRES, "concept:parallel-resistors")
            + _rel(RelationType.USES_LAW, "law:current-divider")
            + _rel(RelationType.USES_ANALYSIS, "analysis:dc", "analysis:current-divider"),
            common_errors=("using the divider ratio the wrong way round (larger R gets less current)",),
            simulation_mapping=(".op",),
            domain_covered="any number (N>=2) of resistive branches sharing an injected total current",
            domain_not_covered="branches containing sources or non-resistive elements",
        ),
        _concept(
            "concept:resistive-bridge", "Resistive bridge", ConceptCategory.NETWORK_THEOREM,
            "Four resistors in a bridge arrangement, general (may or may not be balanced). "
            "Balance (Vout == 0) is a separate, checkable condition, never assumed.",
            ("R",), ("RESISTIVE_BRIDGE",), "intermediate",
            relations=_rel(RelationType.REQUIRES, "concept:kcl", "concept:kvl")
            + _rel(RelationType.USES_EQUATION, "equation:bridge-balance"),
            common_errors=("assuming balance without checking the ratio",),
            simulation_mapping=(".op",),
            domain_covered="any 4-resistor Wheatstone-shaped bridge network, balanced or not",
            domain_not_covered="solving the unbalanced galvanometer-branch current (needs KCL/KVL system, "
                                "not a closed-form formula; see procedure:resistive-bridge step 4)",
        ),
        _concept(
            "concept:wheatstone-bridge-balanced", "Balanced Wheatstone bridge",
            ConceptCategory.NETWORK_THEOREM,
            "The special case of concept:resistive-bridge where R1*R4 == R2*R3, so Vout == 0 "
            "and no current flows through the galvanometer branch.",
            ("R",), ("RESISTIVE_BRIDGE",), "intermediate",
            relations=_rel(RelationType.IS_A, "concept:resistive-bridge")
            + _rel(RelationType.USES_EQUATION, "equation:bridge-balance"),
            simulation_mapping=(".op",),
            generality=Generality.SPECIAL_CASE, parent="concept:resistive-bridge",
            domain_covered="4-resistor bridges satisfying R1*R4 == R2*R3 exactly",
            domain_not_covered="unbalanced bridges — balance is checked via equation:bridge-balance, "
                                "never inferred from arm naming/similarity",
        ),
        _concept(
            "concept:thevenin", "Thevenin equivalent", ConceptCategory.NETWORK_THEOREM,
            "Any linear resistive one-port reduced to a series source Vth and resistance Rth, "
            "given an explicit two-terminal port.",
            ("R", "V", "I"), (), "intermediate",
            relations=_rel(RelationType.REQUIRES, "concept:series-resistors", "concept:parallel-resistors")
            + _rel(RelationType.RELATED_TO, "concept:norton")
            + _rel(RelationType.USES_ANALYSIS, "analysis:thevenin"),
            common_errors=("forgetting to zero independent sources when computing Rth",),
            simulation_mapping=(".op",),
            domain_covered="linear resistive one-ports whose port sub-network reduces via "
                            "series/parallel combination (any depth/N of resistors)",
            domain_not_covered="one-ports needing full mesh/nodal (MNA) solving, e.g. non-series-parallel "
                                "bridge networks or dependent sources — see analysis:thevenin.limitations",
        ),
        _concept(
            "concept:norton", "Norton equivalent", ConceptCategory.NETWORK_THEOREM,
            "Any linear resistive one-port reduced to a parallel source In and resistance Rn, "
            "given an explicit two-terminal port. Related to Thevenin by In = Vth/Rth, Rn = Rth.",
            ("R", "V", "I"), (), "intermediate",
            relations=_rel(RelationType.REQUIRES, "concept:thevenin")
            + _rel(RelationType.RELATED_TO, "concept:thevenin")
            + _rel(RelationType.USES_ANALYSIS, "analysis:norton"),
            common_errors=("mixing up Rn with Rth's dual instead of reusing the same value",),
            simulation_mapping=(".op",),
            domain_covered="same domain as concept:thevenin (In/Rn computed from Vth/Rth)",
            domain_not_covered="same exclusions as concept:thevenin",
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
