# SPDX-License-Identifier: MIT
"""F8-Q.2 combinational components: NOT / AND / OR / XOR (N-ary since F8-Q.2R).

One ``GateKind`` per function, arity configurable per instance (no
AND3/AND4 kinds). Semantics are static reductions over the input states:

- NOT: exactly 1 input, inverts it.
- AND: 2..MAX_NETS inputs; HIGH iff all inputs are HIGH.
- OR:  2..MAX_NETS inputs; HIGH iff at least one input is HIGH.
- XOR: 2..MAX_NETS inputs; HIGH iff an odd number of inputs are HIGH (parity).

The minimum of 2 for AND/OR/XOR is deliberate: a 1-input AND/OR/XOR is
just a wire, and 0 inputs have no defined value, so both are refused
(``INVALID_ARITY``). The upper bound comes from the existing core limit.
Inputs must be distinct nets, so N can never exceed the number of nets.

``TRUTH_TABLES`` is a frozen 2-input/NOT view derived from the rules for
F8-Q.2 compatibility. It is not the source of semantics.

Pins: inputs ``in0..in{N-1}`` follow the order of ``inputs``; the output is
``out``. No delay field: v1 is zero-delay only (design §16).
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from academic_core.domain.engineering.digital.core import (
    MAX_NETS,
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


# (min, max) inputs per kind.
ARITY_RANGE = MappingProxyType({
    GateKind.NOT: (1, 1),
    GateKind.AND: (2, MAX_NETS),
    GateKind.OR: (2, MAX_NETS),
    GateKind.XOR: (2, MAX_NETS),
})


def _reduce(kind: GateKind, states: tuple[LogicState, ...]) -> LogicState:
    if kind is GateKind.NOT:
        return H if states[0] is L else L
    highs = sum(1 for s in states if s is H)
    if kind is GateKind.AND:
        return H if highs == len(states) else L
    if kind is GateKind.OR:
        return H if highs > 0 else L
    return H if highs % 2 == 1 else L  # XOR: parity


TRUTH_TABLES = MappingProxyType({
    kind: MappingProxyType({
        combo: _reduce(kind, combo)
        for combo in itertools.product((L, H), repeat=1 if kind is GateKind.NOT else 2)})
    for kind in GateKind
})

OUTPUT_PIN = "out"


def input_pin_name(index: int) -> str:
    return f"in{index}"


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
    """Immutable gate instance with an ordered tuple of N input nets."""

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
        lo, hi = ARITY_RANGE[self.kind]
        if not (lo <= len(self.inputs) <= hi):
            raise _invalid("INVALID_ARITY",
                           f"{self.kind.value} takes {lo}..{hi} input(s), got {len(self.inputs)}")
        for net_id in self.inputs:
            check_id(net_id, "input net_id")
        if len(set(self.inputs)) != len(self.inputs):
            raise _invalid("DUPLICATE_INPUT", f"{self.component_id} connects one net to several inputs")
        check_id(self.output, "output net_id")

    @classmethod
    def from_pins(cls, component_id: str, kind: GateKind, pins: tuple[Pin, ...]) -> "DigitalComponent":
        """Build from explicit pin bindings (any order). Requires exactly one
        ``out`` OUTPUT pin and contiguous ``in0..in{N-1}`` INPUT pins."""
        if not isinstance(pins, tuple) or not all(isinstance(p, Pin) for p in pins):
            raise _invalid("INVALID_INPUTS", "pins must be a tuple of Pin")
        by_name: dict[str, Pin] = {}
        for p in pins:
            if p.name in by_name:
                raise _invalid("DUPLICATE_PIN", f"pin {p.name!r} bound twice")
            by_name[p.name] = p
        out = by_name.pop(OUTPUT_PIN, None)
        if out is None:
            raise _invalid("MISSING_PIN", f"{component_id} has no {OUTPUT_PIN!r} pin")
        if out.direction is not PinDirection.OUTPUT:
            raise _invalid("INVALID_PIN_DIRECTION", f"pin {OUTPUT_PIN!r} must be OUTPUT")
        for name, p in by_name.items():  # pins-tuple order: deterministic first error
            index = name[2:]
            if not (name.startswith("in") and index.isdigit() and str(int(index)) == index):
                raise _invalid("UNKNOWN_PIN", f"{component_id} has no pin {name!r}")
            if p.direction is not PinDirection.INPUT:
                raise _invalid("INVALID_PIN_DIRECTION", f"pin {name!r} must be INPUT")
        n = len(by_name)
        missing = [input_pin_name(i) for i in range(n) if input_pin_name(i) not in by_name]
        if missing:
            raise _invalid("MISSING_PIN", f"{component_id} input pins must be contiguous; missing {missing[0]!r}")
        return cls(component_id, kind, tuple(by_name[input_pin_name(i)].net_id for i in range(n)),
                   out.net_id)

    @property
    def arity(self) -> int:
        return len(self.inputs)

    @property
    def pins(self) -> tuple[Pin, ...]:
        return tuple(Pin(input_pin_name(i), PinDirection.INPUT, n) for i, n in enumerate(self.inputs)) + (
            Pin(OUTPUT_PIN, PinDirection.OUTPUT, self.output),)

    def pin(self, name: str) -> Pin:
        for p in self.pins:
            if p.name == name:
                return p
        raise _invalid("UNKNOWN_PIN", f"{self.component_id} has no pin {name!r}")

    def evaluate(self, states: tuple[LogicState, ...]) -> LogicState:
        if not isinstance(states, tuple) or len(states) != self.arity:
            raise _invalid("INVALID_ARITY", f"{self.component_id} needs {self.arity} input state(s)")
        for s in states:
            check_state(s)
        return _reduce(self.kind, states)
