"""Component models (Phase 6): metadata + typed parameters + validation.

Models describe components for netlists and deterministic calculations.
No physics beyond closed-form relations — simulation belongs to F7.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from academic_core.domain.engineering.circuit import COMPONENT_PINS, CircuitError
from academic_core.domain.engineering.units import Quantity


@dataclass(frozen=True)
class ComponentModel:
    type: str
    description: str
    params: dict = field(default_factory=dict)  # name -> Quantity

    def __post_init__(self):
        if self.type.upper() not in COMPONENT_PINS:
            raise CircuitError(f"unknown component type: {self.type}")
        for k, v in self.params.items():
            if not isinstance(v, Quantity):
                raise CircuitError(f"param {k} must be a Quantity")


def resistor(value: Quantity) -> ComponentModel:
    if value.dimension != (1, 2, -3, -2, 0, 0, 0):
        raise CircuitError("resistor value must be a resistance")
    if value.to_base() <= 0:
        raise CircuitError("resistance must be > 0")
    return ComponentModel("R", "resistor", {"R": value})


def capacitor(value: Quantity) -> ComponentModel:
    if value.dimension != (-1, -2, 4, 2, 0, 0, 0):
        raise CircuitError("capacitor value must be a capacitance")
    return ComponentModel("C", "capacitor", {"C": value})


def inductor(value: Quantity) -> ComponentModel:
    if value.dimension != (1, 2, -2, -2, 0, 0, 0):
        raise CircuitError("inductor value must be an inductance")
    return ComponentModel("L", "inductor", {"L": value})


def voltage_source(value: Quantity) -> ComponentModel:
    if value.dimension != (1, 2, -3, -1, 0, 0, 0):
        raise CircuitError("voltage source value must be a voltage")
    return ComponentModel("V", "voltage source", {"V": value})


def current_source(value: Quantity) -> ComponentModel:
    if value.dimension != (0, 0, 0, 1, 0, 0, 0):
        raise CircuitError("current source value must be a current")
    return ComponentModel("I", "current source", {"I": value})


def diode() -> ComponentModel:
    return ComponentModel("D", "diode (ideal placeholder)", {})


def bjt() -> ComponentModel:
    return ComponentModel("Q", "BJT transistor (placeholder)", {})


def mosfet() -> ComponentModel:
    return ComponentModel("M", "MOSFET transistor (placeholder)", {})


def jfet() -> ComponentModel:
    return ComponentModel("J", "JFET transistor (placeholder)", {})
