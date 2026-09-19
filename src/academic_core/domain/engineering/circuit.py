"""Circuit model (Phase 6): explicit pins/nets, topology validation, netlist.

Component types: R, C, L, V (voltage source), I (current source), D (diode,
diode-kind variants Zener/LED/Schottky/photodiode via the ``kind`` parameter),
Q (BJT transistor), M (F8-K MOSFET: pins "D", "G", "S", "B"; no value,
parameters carry the Shichman-Hodges model), J (F8-K JFET: pins "D", "G",
"S"; no value, parameters carry the square-law model), E/G/H/F (F8-E linear
dependent sources), O (F8-F ideal
op-amp: pins "+", "-", "o"; no value, no parameters), T (F8-G ideal
transformer: pins "1", "2" primary +/-, "3", "4" secondary +/-, dimensionless
turns-ratio value, no parameters). Each declares its pins; nets are explicit
objects. Netlist is deterministic (sorted by reference) and parseable back
(roundtrip). No simulation here — netlist is representation only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from academic_core.domain.engineering.units import (
    Quantity, UnitError, parse_quantity,
)

CIRCUIT_VERSION = "engcircuit/6.0"

COMPONENT_PINS = {
    "R": ("1", "2"), "C": ("1", "2"), "L": ("1", "2"),
    "V": ("+", "-"), "I": ("+", "-"),
    "D": ("A", "K"), "Q": ("C", "B", "E"),
    # F8-K MOSFET (Shichman-Hodges Level 1): "D" drain, "G" gate,
    # "S" source, "B" bulk (explicit; tie B to S for 3-terminal use).
    # No value; model lives in `parameters`.
    "M": ("D", "G", "S", "B"),
    # F8-K JFET (square-law): "D" drain, "G" gate, "S" source.
    # No value; model lives in `parameters`.
    "J": ("D", "G", "S"),
    # F8-E linear dependent sources (SPICE letters): output pins "+"/"-";
    # control data lives in `parameters` (E/G: cp/cn nets, H/F: control_ref).
    "E": ("+", "-"), "G": ("+", "-"), "H": ("+", "-"), "F": ("+", "-"),
    # F8-F ideal op-amp (nullor): "+" non-inverting input, "-" inverting
    # input, "o" output. No value, no parameters — topology in pins only.
    "O": ("+", "-", "o"),
    # F8-G ideal transformer: "1"/"2" primary +/-, "3"/"4" secondary +/-.
    # Turns ratio n lives in `value` (dimensionless); no parameters.
    "T": ("1", "2", "3", "4"),
}

_REF_RE = re.compile(r"^([RCLVIDQEGHFOTMJ])(\d+)$", re.IGNORECASE)


class CircuitError(ValueError):
    pass


@dataclass(frozen=True)
class Component:
    # NOTE (pre-F8-F audit: KNOWN ARCHITECTURAL DEBT): frozen=True blocks
    # attribute reassignment, NOT mutation of the contained pins /
    # parameters / metadata dicts. Audited 2026-09: no engine in
    # src/ mutates them (every derived circuit copies via dict(...),
    # builders create new objects); Circuit.components/nets are mutated
    # only by Circuit.add during construction. Do not treat frozen=True
    # as deep immutability, and do not refactor without a demonstrated
    # functional defect.
    ref: str  # R1, C3, Q2, M1, J3, E1, G2, O1, T1… (type letter + number)
    type: str  # R|C|L|V|I|D|Q|M|J|E|G|H|F|O|T (T: ideal transformer, n in value)
    value: Quantity | None  # None for ideal/semiconductor placeholders
    pins: dict  # pin name -> net name
    parameters: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        m = _REF_RE.match(self.ref or "")
        if not m or m.group(1).upper() != self.type.upper():
            raise CircuitError(f"ref {self.ref!r} mismatches type {self.type!r}")
        if self.type.upper() not in COMPONENT_PINS:
            raise CircuitError(f"unknown component type: {self.type}")
        want = set(COMPONENT_PINS[self.type.upper()])
        if set(self.pins) != want:
            raise CircuitError(
                f"{self.ref} pins {sorted(self.pins)} != {sorted(want)}")
        for pin, net in self.pins.items():
            if not net or not str(net).strip():
                raise CircuitError(f"{self.ref}.{pin}: empty net")
        if self.value is not None and not isinstance(self.value, Quantity):
            raise CircuitError("value must be a Quantity")


@dataclass
class Circuit:
    name: str
    components: list[Component] = field(default_factory=list)
    nets: set[str] = field(default_factory=set)
    notes: str = ""

    def add(self, comp: Component) -> None:
        refs = {c.ref.upper() for c in self.components}
        if comp.ref.upper() in refs:
            raise CircuitError(f"duplicate reference: {comp.ref}")
        self.components.append(comp)
        self.nets.update(comp.pins.values())

    def validate(self) -> list[str]:
        """Topology warnings (empty = clean). Errors raise at add-time;
        this reports detectable electrical issues."""
        issues: list[str] = []
        if not self.components:
            issues.append("empty circuit")
        use: dict[str, list[str]] = {}
        for c in self.components:
            for pin, net in c.pins.items():
                use.setdefault(net, []).append(f"{c.ref}.{pin}")
        for net in sorted(self.nets):
            pins = use.get(net, [])
            if not pins:
                issues.append(f"empty net: {net}")
            elif len(pins) == 1:
                issues.append(f"floating pin: {pins[0]} (net {net})")
        return issues

    def to_netlist(self) -> str:
        lines = [f"* {self.name} [{CIRCUIT_VERSION}]"]
        for c in sorted(self.components, key=lambda c: c.ref.upper()):
            pins = " ".join(c.pins[p] for p in COMPONENT_PINS[c.type.upper()])
            value = c.value.compact() if c.value else c.type.upper()
            lines.append(f"{c.ref.upper()} {pins} {value}")
        lines.append(".end")
        return "\n".join(lines) + "\n"

    @classmethod
    def from_netlist(cls, text: str, name: str = "imported") -> "Circuit":
        for header in text.splitlines():
            if header.startswith("* "):
                name = header[2:].split(" [", 1)[0].strip() or name
                break
        circuit = cls(name)
        for lineno, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("*") or line == ".end":
                continue
            parts = line.split()
            if len(parts) < 3:
                raise CircuitError(f"line {lineno}: malformed {line!r}")
            ref, nets, value_s = parts[0], parts[1:-1], parts[-1]
            m = _REF_RE.match(ref)
            if not m:
                raise CircuitError(f"line {lineno}: bad ref {ref!r}")
            ctype = m.group(1).upper()
            want = COMPONENT_PINS.get(ctype)
            if want is None or len(nets) != len(want):
                raise CircuitError(f"line {lineno}: pin count mismatch for {ref}")
            try:
                value = parse_quantity(value_s)
            except UnitError:
                value = None
                if value_s != ctype:
                    raise CircuitError(f"line {lineno}: bad value {value_s!r}")
            circuit.add(Component(ref.upper(), ctype, value,
                                  dict(zip(want, nets))))
        return circuit


@dataclass
class EngineeringProject:
    name: str
    subject_id: str = ""
    topic_id: str = ""
    description: str = ""
    circuits: list[str] = field(default_factory=list)  # circuit names/ids
    calculations: list[str] = field(default_factory=list)  # result digests
    doc_links: list[str] = field(default_factory=list)  # authoring resource ids

    def __post_init__(self):
        if not self.name.strip():
            raise CircuitError("project name required")
        from academic_core.domain.identity import validate
        for label, value, kind in (("subject_id", self.subject_id, "subject"),
                                   ("topic_id", self.topic_id, "topic")):
            if value:
                try:
                    got = validate(value)
                except ValueError:
                    raise CircuitError(f"bad {label}: {value}") from None
                if got != kind:
                    raise CircuitError(f"bad {label}: {value}")
