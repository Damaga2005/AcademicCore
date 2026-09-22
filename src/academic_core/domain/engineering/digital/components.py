# SPDX-License-Identifier: MIT
"""F8-Q digital combinational components (Q.2, N-ary since Q.2R, hardened in Q.3R).

One ``GateKind`` per function, arity configurable per instance (no
AND3/NAND4 kinds). The single source of semantics is ``GATE_SEMANTICS``
(data) interpreted by ``_output(kind, highs, n)``: every gate's output is a
function of how many of its N input pins are HIGH.

- NOT: exactly 1 input, inverts it.
- AND / NAND: HIGH iff all pins are HIGH (NAND: negated).
- OR / NOR: HIGH iff at least one pin is HIGH (NOR: negated).
- XOR / XNOR: HIGH iff an odd number of pins are HIGH (XNOR: even).

Arity: NOT exactly 1; all others 2..MAX_NETS. Zero inputs, and one input
for a multi-input kind, are refused (``INVALID_ARITY``).

The same net may feed several pins of one gate (``NAND(A, A)`` is
``NOT(A)``; ``XOR(A, A, B)`` is ``B``). Each pin counts separately. This is
not a driver conflict: the single-driver rule concerns outputs.

``DigitalComponent.evaluate`` is the full evaluation (O(N)) and serves as
the oracle. ``GateEvaluator`` is the incremental per-run state used by the
simulator. It keeps the per-pin states and a HIGH counter, updates in O(1)
per pin, and computes its output through the same ``_output``, so it is not
a second source of truth. ``TRUTH_TABLES`` is a frozen NOT/2-input view
derived from ``_output`` for Q2 compatibility; no 2^N table is ever built.
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
from academic_core.errors import IntegrationError

L, H = LogicState.LOW, LogicState.HIGH


class GateKind(str, Enum):
    NOT = "NOT"
    AND = "AND"
    OR = "OR"
    XOR = "XOR"
    NAND = "NAND"
    NOR = "NOR"
    XNOR = "XNOR"


class PinDirection(str, Enum):
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"


# kind -> (reduction over the HIGH count, inverted). Data, not code.
GATE_SEMANTICS = MappingProxyType({
    GateKind.NOT: ("ANY", True),
    GateKind.AND: ("ALL", False),
    GateKind.OR: ("ANY", False),
    GateKind.XOR: ("ODD", False),
    GateKind.NAND: ("ALL", True),
    GateKind.NOR: ("ANY", True),
    GateKind.XNOR: ("ODD", True),
})

# (min, max) inputs per kind.
ARITY_RANGE = MappingProxyType({
    kind: (1, 1) if kind is GateKind.NOT else (2, MAX_NETS) for kind in GateKind
})


def _output(kind: GateKind, highs: int, n: int) -> LogicState:
    """THE gate semantics: output from the number of HIGH pins out of n."""
    reduction, inverted = GATE_SEMANTICS[kind]
    if reduction == "ALL":
        value = highs == n
    elif reduction == "ANY":
        value = highs > 0
    else:  # "ODD"
        value = highs % 2 == 1
    return H if value != inverted else L


def _reduce(kind: GateKind, states: tuple[LogicState, ...]) -> LogicState:
    return _output(kind, sum(1 for s in states if s is H), len(states))


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
        check_id(self.output, "output net_id")

    @classmethod
    def from_pins(cls, component_id: str, kind: GateKind, pins: tuple[Pin, ...]) -> "DigitalComponent":
        """Build from explicit pin bindings (any order). Requires exactly one
        ``out`` OUTPUT pin and contiguous ``in0..in{N-1}`` INPUT pins. Several
        input pins may name the same net."""
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

    def pin_indices(self, net_id: str) -> tuple[int, ...]:
        """Input pin indices bound to ``net_id``, ascending (empty if none)."""
        return tuple(i for i, n in enumerate(self.inputs) if n == net_id)

    def evaluate(self, states: tuple[LogicState, ...]) -> LogicState:
        """Full O(N) evaluation: the semantic oracle."""
        if not isinstance(states, tuple) or len(states) != self.arity:
            raise _invalid("INVALID_ARITY", f"{self.component_id} needs {self.arity} input state(s)")
        for s in states:
            check_state(s)
        return _reduce(self.kind, states)

    def evaluator(self, states: tuple[LogicState, ...]) -> "GateEvaluator":
        return GateEvaluator(self, states)


class GateEvaluator:
    """Incremental evaluation state of one component for one simulation run.

    ``initialize`` is O(N) once, ``update`` is O(1), ``update_net`` is O(k)
    for the k pins bound to the changed net, and ``output_state`` is O(1).
    Each update is validated before anything is mutated. A stale ``old``
    state means the evaluator lost track of the net states, an internal
    invariant breach, and raises ``IntegrationError`` (AC-INT-001).
    """

    def __init__(self, component: DigitalComponent, states: tuple[LogicState, ...]):
        if not isinstance(component, DigitalComponent):
            raise _invalid("INVALID_COMPONENT", f"expected DigitalComponent, got {type(component).__name__}")
        self.component = component
        index: dict[str, list[int]] = {}
        for i, net_id in enumerate(component.inputs):  # tuple order: deterministic
            index.setdefault(net_id, []).append(i)
        self._by_net = {k: tuple(v) for k, v in index.items()}
        self.initialize(states)

    def initialize(self, states: tuple[LogicState, ...]) -> None:
        if not isinstance(states, tuple) or len(states) != self.component.arity:
            raise _invalid("INVALID_ARITY", f"{self.component.component_id} needs "
                           f"{self.component.arity} input state(s)")
        for s in states:
            check_state(s)
        self._states = list(states)
        self._highs = sum(1 for s in states if s is H)

    def update(self, index: int, old: LogicState, new: LogicState) -> None:
        if isinstance(index, bool) or not isinstance(index, int) or not (
                0 <= index < self.component.arity):
            raise _invalid("UNKNOWN_PIN", f"{self.component.component_id} has no input {index!r}")
        check_state(old)
        check_state(new)
        if self._states[index] is not old:
            raise IntegrationError(f"STALE_INPUT: {self.component.component_id}.in{index} is "
                                   f"{self._states[index].name}, update claims {old.name}")
        self._states[index] = new
        self._highs += (new is H) - (old is H)

    def update_net(self, net_id: str, old: LogicState, new: LogicState) -> None:
        for i in self._by_net.get(net_id, ()):
            self.update(i, old, new)

    def output_state(self) -> LogicState:
        return _output(self.component.kind, self._highs, self.component.arity)

    @property
    def input_states(self) -> tuple[LogicState, ...]:
        return tuple(self._states)
