"""ElectronicsModel registry (Phase 8-A).

Separates a concept (what the circuit *is*) from the physical/mathematical
model backing it. Only the ideal linear models needed for the initial
circuit-theory coverage are declared; semiconductor models (diode, BJT,
MOSFET, ...) are explicitly out of scope for this phase (section 7).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from academic_core.domain.electronics.types import provenance


@dataclass(frozen=True)
class ElectronicsModel:
    """A physical/mathematical model for a component or sub-network."""

    stable_id: str  # "model:<name>"
    name: str
    description: str
    equations: tuple[str, ...] = ()  # equation stable_ids this model relies on
    provenance: dict = field(default_factory=dict)


def _model(stable_id: str, name: str, description: str,
           equations: tuple[str, ...] = ()) -> ElectronicsModel:
    return ElectronicsModel(stable_id, name, description, equations,
                             provenance(stable_id))


MODELS: dict[str, ElectronicsModel] = {
    m.stable_id: m for m in (
        _model("model:resistor-ideal", "Ideal resistor",
               "Linear, temperature-independent, obeys Ohm's law exactly.",
               ("equation:ohm-v", "equation:ohm-i", "equation:ohm-r")),
        _model("model:vsource-ideal", "Ideal independent voltage source",
               "Fixed terminal voltage regardless of drawn current; zero internal resistance."),
        _model("model:isource-ideal", "Ideal independent current source",
               "Fixed terminal current regardless of terminal voltage; infinite internal resistance."),
    )
}


def get(stable_id: str) -> ElectronicsModel:
    return MODELS[stable_id]


__all__ = ["ElectronicsModel", "MODELS", "get"]
