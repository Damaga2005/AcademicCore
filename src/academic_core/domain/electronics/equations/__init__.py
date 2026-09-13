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
from academic_core.domain.electronics.types import Generality, provenance

EQUATIONS_VERSION = "f8a-equations/1.0"


@dataclass(frozen=True)
class ElectronicsEquation:
    """A structured, traceable equation entry (section 10).

    F6's equation grammar (`engineering.equations.parse_equation`) only
    parses fixed named-variable expressions — it has no notion of "sum over
    N terms". So a formula written here for two named variables (R1, R2, ...)
    is *necessarily* a SPECIAL_CASE instance of the underlying general law,
    never the law itself (section 5/41). `generality`/`parent` make that
    checkable instead of leaving it implicit in the description.
    """

    stable_id: str  # "equation:<name>"
    equation: Equation
    dimension: str  # DIM_NAMES value the output must carry
    validity: str  # plain-language validity condition
    generality: Generality = Generality.GENERAL
    parent: str | None = None  # GeneralLaw stable_id this specializes, if SPECIAL_CASE
    provenance: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.generality == Generality.SPECIAL_CASE and not self.parent:
            raise ValueError(f"{self.stable_id}: SPECIAL_CASE equation must declare parent")

    @property
    def expression(self) -> str:
        return self.equation.source

    @property
    def variables(self) -> tuple:
        return self.equation.variables


@dataclass(frozen=True)
class GeneralLaw:
    """A genuinely N-ary/general mathematical law that has no fixed-arity
    string form in F6's grammar (section 5/20/41): e.g. `Req = sum(Ri)` for
    arbitrary N, or `sum(I_k) = 0` over however many branches meet a node.

    Never executed via the string equation engine. `computation` names the
    actual general (arbitrary-N) function in `electronics.calc` that
    implements it by composing F6's `Quantity` arithmetic / `calculate()`
    through associative reduction — the honest general implementation,
    instead of a second math engine.
    """

    stable_id: str  # "law:<name>"
    statement: str  # e.g. "Req = sum(Ri) for i in 1..N, N >= 1"
    domain: str  # what this law covers
    not_covered: str  # what it explicitly does NOT cover
    conditions: str
    computation: str  # dotted path: "academic_core...electronics.calc.<fn>"
    special_case_equation: str | None = None  # a 2-term ElectronicsEquation, if one exists
    provenance: dict = field(default_factory=dict)

    generality: Generality = Generality.GENERAL


def _from_f6(key: str, stable_id: str, validity: str) -> ElectronicsEquation:
    entry = _F6_LIBRARY[key]
    return ElectronicsEquation(
        stable_id=stable_id,
        equation=parse_equation(entry["source"]),
        dimension=entry["dim"],
        validity=validity,
        provenance=provenance(stable_id),
    )


def _new(stable_id: str, source: str, dimension: str, validity: str,
         generality: Generality = Generality.GENERAL, parent: str | None = None) -> ElectronicsEquation:
    return ElectronicsEquation(
        stable_id=stable_id,
        equation=parse_equation(source),
        dimension=dimension,
        validity=validity,
        generality=generality,
        parent=parent,
        provenance=provenance(stable_id),
    )


def _law(stable_id: str, statement: str, domain: str, not_covered: str, conditions: str,
         computation: str, special_case_equation: str | None = None) -> GeneralLaw:
    return GeneralLaw(stable_id, statement, domain, not_covered, conditions,
                       computation, special_case_equation, provenance(stable_id))


# -- reused verbatim from F6's curated library (never redeclared) ------------
_REUSED = (
    _from_f6("ohm-v", "equation:ohm-v", "resistor obeys Ohm's law (linear, ideal)"),
    _from_f6("ohm-i", "equation:ohm-i", "resistor obeys Ohm's law (linear, ideal)"),
    _from_f6("ohm-r", "equation:ohm-r", "resistor obeys Ohm's law (linear, ideal)"),
    _from_f6("power-vi", "equation:power-vi", "instantaneous power, any two-terminal element"),
    _from_f6("power-i2r", "equation:power-i2r", "resistive dissipation, ideal resistor"),
    _from_f6("power-v2r", "equation:power-v2r", "resistive dissipation, ideal resistor"),
)

# -- SPECIAL_CASE pairwise equations: the two-term instance F6's grammar can
#    parse. Each is the reduction primitive `electronics.calc` folds over N
#    terms — never presented standalone as "the" general law (section 41).
_PAIRWISE = (
    _new("equation:series-resistors-pair", "Req = R1 + R2", "resistance",
         "two ideal resistors in series",
         generality=Generality.SPECIAL_CASE, parent="law:series-resistors"),
    _new("equation:parallel-resistors-pair", "Req = (R1 * R2) / (R1 + R2)", "resistance",
         "two ideal resistors in parallel",
         generality=Generality.SPECIAL_CASE, parent="law:parallel-resistors"),
    _new("equation:current-divider-pair", "I1 = Itot * R2 / (R1 + R2)", "current",
         "two-branch resistive current divider",
         generality=Generality.SPECIAL_CASE, parent="law:current-divider"),
    _new("equation:voltage-divider-pair", "Vout = Vi * R2 / (R1 + R2)", "voltage",
         "two-resistor series divider, no loading at the tap",
         generality=Generality.SPECIAL_CASE, parent="law:voltage-divider"),
)

# -- other special cases / general two-terminal equations --------------------
_OTHER = (
    _new("equation:bridge-balance", "balance_ratio = (R1 * R4) / (R2 * R3)", "dimensionless",
         "four-arm resistive bridge; balanced (Vout == 0) exactly when ratio == 1"),
)

EQUATIONS: dict[str, ElectronicsEquation] = {
    e.stable_id: e for e in (*_REUSED, *_PAIRWISE, *_OTHER)
}

# -- GENERAL laws: real N-ary rules, executed by composing F6 primitives via
#    associative reduction in `electronics.calc` (never re-implementing the
#    equation/unit engine, never capped at N=2) ------------------------------
GENERAL_LAWS: dict[str, GeneralLaw] = {
    law.stable_id: law for law in (
        _law("law:series-resistors", "Req = sum(Ri) for i in 1..N, N >= 1",
             "any number of ideal resistors sharing a single current path (no branching)",
             "non-ideal/temperature-dependent resistors; branched (non-series) topology",
             "each Ri carries the same current; no intermediate node has a third branch",
             "academic_core.domain.electronics.calc.series_equivalent",
             special_case_equation="equation:series-resistors-pair"),
        _law("law:parallel-resistors", "1/Req = sum(1/Ri) for i in 1..N, N >= 1",
             "any number of ideal resistors sharing both terminal nodes",
             "non-ideal resistors; branches that do not share both terminals",
             "each Ri has the same voltage across it",
             "academic_core.domain.electronics.calc.parallel_equivalent",
             special_case_equation="equation:parallel-resistors-pair"),
        _law("law:current-divider", "I_k = Itot * G_k / sum(G_i), G_i = 1/Ri, for N >= 2 branches",
             "any number of resistive branches in parallel sharing an injected total current",
             "branches containing sources or non-resistive elements",
             "branches share both terminal nodes; Itot known",
             "academic_core.domain.electronics.calc.current_divider",
             special_case_equation="equation:current-divider-pair"),
        _law("law:voltage-divider", "Vout_k = Vin * sum(Ri for i > k) / sum(Ri for all i), N >= 1",
             "an unloaded series chain of any number of resistors across a source, "
             "tapped at any explicit intermediate node",
             "loaded taps (current drawn at the tap alters the ratio) — see analysis:voltage-divider limitations",
             "chain carries a single common current; tap node explicit, never inferred",
             "academic_core.domain.electronics.calc.voltage_divider_chain",
             special_case_equation="equation:voltage-divider-pair"),
        _law("law:kcl", "sum(I_k) = 0 over all branches incident to a node, for any number of branches",
             "any node in any circuit, signed by a consistent reference direction",
             "nothing within DC/resistive scope; holds generally",
             "at least one node with 1+ incident branches; consistent sign convention",
             "n/a — a conservation check over already-known branch currents, not a solved-for quantity"),
        _law("law:kvl", "sum(V_k) = 0 over all elements around a closed loop, for any loop length",
             "any fundamental loop (graph cycle) in any circuit, consistently oriented",
             "nothing within DC/resistive scope; holds generally",
             "at least one closed loop (graph cycle); consistent traversal direction",
             "n/a — a conservation check over already-known branch voltages, not a solved-for quantity"),
    )
}


def get(stable_id: str) -> ElectronicsEquation:
    return EQUATIONS[stable_id]


def get_law(stable_id: str) -> GeneralLaw:
    return GENERAL_LAWS[stable_id]


__all__ = [
    "ElectronicsEquation", "GeneralLaw", "EQUATIONS", "GENERAL_LAWS",
    "EQUATIONS_VERSION", "get", "get_law",
]
