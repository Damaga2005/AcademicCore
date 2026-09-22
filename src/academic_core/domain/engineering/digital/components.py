# SPDX-License-Identifier: MIT
"""F8-Q.2 combinational components: NOT / AND / OR / XOR.

Truth tables are frozen data (tuple-keyed read-only mappings, design
§50); evaluation is a dict lookup, never generated code. v1 arity is
fixed per kind (NOT=1, AND/OR/XOR=2). Pins bind to nets; pin-to-pin
wiring is unrepresentable, and output-output sharing is refused by the
circuit's single-driver rule (design §46). No delay field: v1 is
zero-delay only (design §16), so a delay cannot be expressed at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from academic_core.domain.engineering.digital.core import (
    LogicState,
    _invalid,
    check_id,
    check_state,
)

L, H = LogicState.LOW, LogicState.HIGH


class GateKind(str, Enum):
    NOT = "NOT"
    AND = "AND"
    OR = "OR"
    XOR = "XOR"


class PinDirection(str, Enum):
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"


TRUTH_TABLES = MappingProxyType({
    GateKind.NOT: MappingProxyType({(L,): H, (H,): L}),
    GateKind.AND: MappingProxyType({(L, L): L, (L, H): L, (H, L): L, (H, H): H}),
    GateKind.OR: MappingProxyType({(L, L): L, (L, H): H, (H, L): H, (H, H): H}),
    GateKind.XOR: MappingProxyType({(L, L): L, (L, H): H, (H, L): H, (H, H): L}),
})

ARITY = MappingProxyType({kind: len(next(iter(table))) for kind, table in TRUTH_TABLES.items()})

OUTPUT_PIN = "out"


@dataclass(frozen=True)
class Pin:
    name: str
    direction: PinDirection
    net_id: str

    def __post_init__(self):
        check_id(self.name, "pin name")
        if not isinstance(self.direction, PinDirection):
            raise _invalid("INVALID_PIN_DIRECTION", f"expected PinDirection, got {self.direction!r}")
        check_id(self.net_id, "net_id")


@dataclass(frozen=True)
class DigitalComponent:
    """Immutable gate instance. Input pins are ``in0..in{n-1}``, output ``out``."""

    component_id: str
    kind: GateKind
    inputs: tuple[str, ...]
    output: str

    def __post_init__(self):
        check_id(self.component_id, "component_id")
        if not isinstance(self.kind, GateKind):
            raise _invalid("INVALID_KIND", f"expected GateKind, got {self.kind!r}")
        if not isinstance(self.inputs, tuple):
            raise _invalid("INVALID_INPUTS", "inputs must be a tuple of net ids")
        if len(self.inputs) != ARITY[self.kind]:
            raise _invalid("INVALID_ARITY",
                           f"{self.kind.value} takes {ARITY[self.kind]} input(s), got {len(self.inputs)}")
        for net_id in self.inputs:
            check_id(net_id, "input net_id")
        check_id(self.output, "output net_id")

    @property
    def pins(self) -> tuple[Pin, ...]:
        return tuple(Pin(f"in{i}", PinDirection.INPUT, n) for i, n in enumerate(self.inputs)) + (
            Pin(OUTPUT_PIN, PinDirection.OUTPUT, self.output),)

    def pin(self, name: str) -> Pin:
        for p in self.pins:
            if p.name == name:
                return p
        raise _invalid("UNKNOWN_PIN", f"{self.component_id} has no pin {name!r}")

    def evaluate(self, states: tuple[LogicState, ...]) -> LogicState:
        if not isinstance(states, tuple) or len(states) != ARITY[self.kind]:
            raise _invalid("INVALID_ARITY", f"{self.kind.value} needs {ARITY[self.kind]} input state(s)")
        for s in states:
            check_state(s)
        return TRUTH_TABLES[self.kind][states]
