"""ElectronicsAnalysis registry (Phase 8-A).

Describes *what is done mathematically* (section 9), as distinct from a
concept (*what the circuit is*). Reuses B8's `AnalysisType` as the link back
to structural applicability — no parallel analysis-kind enum is invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from academic_core.domain.engineering.structural.types import AnalysisType
from academic_core.domain.electronics.types import ImplementationStatus, provenance


@dataclass(frozen=True)
class ElectronicsAnalysis:
    """A structured, traceable description of an analysis method (section 8)."""

    stable_id: str  # "analysis:<name>"
    name: str
    analysis_type: AnalysisType  # link to B8's structural applicability classification
    prerequisites: tuple[str, ...]  # concept stable_ids
    required_inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    equations: tuple[str, ...]  # equation stable_ids
    simulation: str | None  # SPICE directive family, e.g. ".op"
    limitations: str
    laws: tuple[str, ...] = ()  # GeneralLaw stable_ids (general N-ary computation)
    implementation_status: ImplementationStatus = ImplementationStatus.IMPLEMENTED
    provenance: dict = field(default_factory=dict)


def _analysis(stable_id, name, analysis_type, prerequisites, required_inputs,
              outputs, equations, simulation, limitations, laws=(),
              implementation_status=ImplementationStatus.IMPLEMENTED) -> ElectronicsAnalysis:
    return ElectronicsAnalysis(
        stable_id, name, analysis_type, prerequisites, required_inputs,
        outputs, equations, simulation, limitations, laws, implementation_status,
        provenance(stable_id))


ANALYSES: dict[str, ElectronicsAnalysis] = {
    a.stable_id: a for a in (
        _analysis(
            "analysis:dc", "DC operating point analysis", AnalysisType.DC_OPERATING_POINT,
            (), ("component values", "source values"), ("node voltages", "branch currents"),
            ("equation:ohm-v", "equation:ohm-i"), ".op",
            "Resistive/source-only networks; no reactive steady-state transients modeled.",
        ),
        _analysis(
            "analysis:kcl", "Kirchhoff's Current Law", AnalysisType.KCL,
            (), ("branch currents at a node",), ("node current balance",),
            (), None, "Requires at least one non-reference node with 2+ incident branches.",
        ),
        _analysis(
            "analysis:kvl", "Kirchhoff's Voltage Law", AnalysisType.KVL,
            (), ("branch voltages around a loop",), ("loop voltage balance",),
            (), None, "Requires at least one fundamental loop (graph cycle).",
        ),
        _analysis(
            "analysis:ohms-law", "Ohm's law", AnalysisType.OHMS_LAW,
            (), ("two of {V, I, R}",), ("the third of {V, I, R}",),
            ("equation:ohm-v", "equation:ohm-i", "equation:ohm-r"), None,
            "Ideal linear resistor only.",
        ),
        _analysis(
            "analysis:voltage-divider", "Voltage divider analysis", AnalysisType.VOLTAGE_DIVIDER,
            ("concept:series-resistors",), ("Vin", "R1..Rn"), ("Vout",),
            (), ".op",
            "Unloaded tap only (no current drawn from the output node); chain of any length N >= 1.",
            laws=("law:voltage-divider",),
        ),
        _analysis(
            "analysis:current-divider", "Current divider analysis", AnalysisType.CURRENT_DIVIDER,
            ("concept:parallel-resistors",), ("Itot", "R1..Rn"), ("I1..In",),
            (), ".op",
            "Resistive branches only (no sources/reactive elements in a branch); any N >= 2 branches.",
            laws=("law:current-divider",),
        ),
        _analysis(
            "analysis:power", "Power dissipation/delivery analysis", AnalysisType.POWER,
            (), ("V and I, or I and R, or V and R",), ("dissipated/delivered power",),
            ("equation:power-vi", "equation:power-i2r", "equation:power-v2r"), None,
            "Instantaneous power for resistive/DC networks.",
        ),
        _analysis(
            "analysis:thevenin", "Thevenin equivalent", AnalysisType.THEVENIN,
            (), ("target terminal pair",), ("Vth", "Rth"),
            (), None,
            "Linear resistive one-port only; explicit target terminals required "
            "(section 6 of B8's port rule). Vth/Rth computation is GENERAL (any N of "
            "resistors, any depth) for port sub-networks that reduce via series/parallel "
            "combination; a port needing a full linear-network solve (e.g. an unbalanced "
            "bridge in the port) is NOT_IMPLEMENTED, not silently approximated.",
            laws=("law:series-resistors", "law:parallel-resistors", "law:voltage-divider"),
            implementation_status=ImplementationStatus.PARTIAL,
        ),
        _analysis(
            "analysis:norton", "Norton equivalent", AnalysisType.NORTON,
            (), ("target terminal pair",), ("In", "Rn"),
            ("equation:ohm-i",), None,
            "Same domain and same PARTIAL status as analysis:thevenin (In = Vth/Rth, Rn = Rth).",
            laws=("law:series-resistors", "law:parallel-resistors", "law:voltage-divider"),
            implementation_status=ImplementationStatus.PARTIAL,
        ),
    )
}


def get(stable_id: str) -> ElectronicsAnalysis:
    return ANALYSES[stable_id]


__all__ = ["ElectronicsAnalysis", "ANALYSES", "get"]
