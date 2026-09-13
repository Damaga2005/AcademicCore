"""ElectronicsAnalysis registry (Phase 8-A).

Describes *what is done mathematically* (section 9), as distinct from a
concept (*what the circuit is*). Reuses B8's `AnalysisType` as the link back
to structural applicability — no parallel analysis-kind enum is invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from academic_core.domain.engineering.structural.types import AnalysisType
from academic_core.domain.electronics.types import provenance


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
    provenance: dict = field(default_factory=dict)


def _analysis(stable_id, name, analysis_type, prerequisites, required_inputs,
              outputs, equations, simulation, limitations) -> ElectronicsAnalysis:
    return ElectronicsAnalysis(
        stable_id, name, analysis_type, prerequisites, required_inputs,
        outputs, equations, simulation, limitations, provenance(stable_id))


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
            ("concept:series-resistors",), ("Vin", "R1", "R2"), ("Vout",),
            ("equation:voltage-divider",), ".op",
            "Unloaded tap only (no current drawn from the output node).",
        ),
        _analysis(
            "analysis:current-divider", "Current divider analysis", AnalysisType.CURRENT_DIVIDER,
            ("concept:parallel-resistors",), ("Itot", "R1", "R2"), ("I1", "I2"),
            ("equation:current-divider",), ".op",
            "Two-branch resistive divider only.",
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
            ("equation:voltage-divider", "equation:parallel-resistors"), None,
            "Linear resistive one-port only; explicit target terminals required "
            "(section 6 of B8's port rule).",
        ),
        _analysis(
            "analysis:norton", "Norton equivalent", AnalysisType.NORTON,
            (), ("target terminal pair",), ("In", "Rn"),
            ("equation:ohm-i", "equation:parallel-resistors"), None,
            "Linear resistive one-port only; explicit target terminals required.",
        ),
    )
}


def get(stable_id: str) -> ElectronicsAnalysis:
    return ANALYSES[stable_id]


__all__ = ["ElectronicsAnalysis", "ANALYSES", "get"]
