"""Validation + Modified Nodal Analysis matrix assembly.

Converts a canonical `Circuit` (F6) into an `MNAProblem`: the deterministic
`A x = z` system, plus enough bookkeeping (node/branch index maps) to later
recover node voltages, branch currents and element powers. Construction is
separated from the numeric solve (`linear.solve_exact`) so each layer is
independently testable/auditable (spec section 33).

Unknowns: one node-voltage variable per non-reference net (sorted by net
name for determinism), followed by one branch-current variable per ideal
voltage source (sorted by component ref).

Sign conventions (documented once, used consistently everywhere in F8-B):
  * Resistor: current flows from pin "1" to pin "2"; I = (V1 - V2) / R.
  * Voltage source: the MNA unknown current I_V is defined flowing from
    pin "+" to pin "-" through the source. KCL row for "+" gets +I_V, KCL
    row for "-" gets -I_V; the source's own constraint row is
    V(+) - V(-) = Vs.
  * Current source: Is is defined flowing out of pin "-" and into pin "+"
    of the external circuit (i.e. delivered into the circuit at "+"),
    contributing +Is to node "+"'s injected-current term and -Is to node
    "-"'s. For *reporting* (branch current / power), the same "+ -> -"
    through-the-element direction used by every other element is applied,
    so the reported branch current is -Is (opposite of the delivered
    direction) — see `mna.solver` for the derivation.
  * Power for every element uses the passive sign convention with the same
    "pin1 -> pin2" (or "+ -> -") direction as its branch current:
    P = (V(pin1) - V(pin2)) * I(pin1->pin2). Positive = absorbed. This
    convention is what makes total power sum to exactly zero (Tellegen's
    theorem) for a consistent DC solve.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.mna.errors import (
    DimensionalityError,
    FloatingCircuitError,
    InvalidCircuitError,
    MissingReferenceError,
    UnsupportedElementError,
)
from academic_core.domain.engineering.units import CURRENT, RESISTANCE, VOLTAGE, Quantity

SUPPORTED_TYPES = frozenset({"R", "V", "I"})

_EXPECTED_DIMENSION = {"R": RESISTANCE, "V": VOLTAGE, "I": CURRENT}


def _to_fraction(q: Quantity) -> Fraction:
    return Fraction(q.to_base())


def _reference_net(circuit: Circuit) -> str:
    candidates = sorted({net for net in circuit.nets if net.strip().upper() in ("0", "GND")})
    if not candidates:
        raise MissingReferenceError(
            f"circuit {circuit.name!r} has no reference node "
            f"(expected a net named '0' or 'GND', case-insensitive)"
        )
    if len(candidates) > 1:
        raise MissingReferenceError(
            f"circuit {circuit.name!r} has ambiguous/incompatible reference "
            f"nodes: {candidates!r} (only one '0'/'GND' net is allowed)"
        )
    return candidates[0]


def _validate_components(circuit: Circuit) -> None:
    if not circuit.components:
        raise InvalidCircuitError(f"circuit {circuit.name!r} has no components")
    seen_refs: set[str] = set()
    for c in circuit.components:
        if c.ref.upper() in seen_refs:
            raise InvalidCircuitError(f"duplicate reference: {c.ref}")
        seen_refs.add(c.ref.upper())
        if c.type.upper() not in SUPPORTED_TYPES:
            raise UnsupportedElementError(
                f"{c.ref}: component type {c.type!r} is NOT_SUPPORTED by the "
                f"F8-B linear DC solver (domain: R, V, I only)"
            )
        if c.value is None:
            raise InvalidCircuitError(f"{c.ref}: missing required value")
        expected_dim = _EXPECTED_DIMENSION[c.type.upper()]
        if c.value.dimension != expected_dim:
            raise DimensionalityError(
                f"{c.ref}: value {c.value.format()} has the wrong dimension "
                f"for a {c.type.upper()} component"
            )
        if c.type.upper() == "R" and c.value.to_base() <= 0:
            raise InvalidCircuitError(f"{c.ref}: resistance must be > 0, got {c.value.format()}")


def _connected_nets(circuit: Circuit) -> dict[str, set[str]]:
    """Union-find over nets, edges from every component's own pins."""
    parent: dict[str, str] = {net: net for net in circuit.nets}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for c in circuit.components:
        pin_nets = list(c.pins.values())
        for other in pin_nets[1:]:
            union(pin_nets[0], other)

    groups: dict[str, set[str]] = {}
    for net in circuit.nets:
        groups.setdefault(find(net), set()).add(net)
    return groups


def _check_reachability(circuit: Circuit, ground: str) -> None:
    groups = _connected_nets(circuit)
    ground_group = next(g for g in groups.values() if ground in g)
    unreachable = sorted(net for net in circuit.nets if net not in ground_group)
    if unreachable:
        raise FloatingCircuitError(
            f"circuit {circuit.name!r} has node(s) with no path to the "
            f"reference node {ground!r}: {unreachable!r}"
        )


@dataclass(frozen=True)
class MNAProblem:
    circuit: Circuit
    ground: str
    nodes: tuple[str, ...]  # non-reference nets, sorted
    node_index: dict
    vsource_refs: tuple[str, ...]  # sorted refs of V components
    vsource_index: dict
    matrix: tuple
    rhs: tuple

    @property
    def size(self) -> int:
        return len(self.nodes) + len(self.vsource_refs)


def build_mna_problem(circuit: Circuit) -> MNAProblem:
    """Validate `circuit` and assemble its MNA `A x = z` system.

    Raises `InvalidCircuitError`, `UnsupportedElementError`,
    `DimensionalityError`, `MissingReferenceError` or `FloatingCircuitError`
    for any circuit outside F8-B's declared domain. Never proceeds silently.
    """
    _validate_components(circuit)
    ground = _reference_net(circuit)
    _check_reachability(circuit, ground)

    nodes = tuple(sorted(n for n in circuit.nets if n != ground))
    node_index = {n: i for i, n in enumerate(nodes)}

    vsource_refs = tuple(sorted(c.ref for c in circuit.components if c.type.upper() == "V"))
    n_nodes = len(nodes)
    vsource_index = {ref: n_nodes + j for j, ref in enumerate(vsource_refs)}

    size = n_nodes + len(vsource_refs)
    matrix = [[Fraction(0) for _ in range(size)] for _ in range(size)]
    rhs = [Fraction(0) for _ in range(size)]

    def idx(net: str) -> int | None:
        return node_index.get(net)

    for c in circuit.components:
        t = c.type.upper()
        if t == "R":
            g = Fraction(1) / _to_fraction(c.value)
            i1, i2 = idx(c.pins["1"]), idx(c.pins["2"])
            if i1 is not None:
                matrix[i1][i1] += g
            if i2 is not None:
                matrix[i2][i2] += g
            if i1 is not None and i2 is not None:
                matrix[i1][i2] -= g
                matrix[i2][i1] -= g
        elif t == "I":
            is_val = _to_fraction(c.value)
            ip, im = idx(c.pins["+"]), idx(c.pins["-"])
            if ip is not None:
                rhs[ip] += is_val
            if im is not None:
                rhs[im] -= is_val
        elif t == "V":
            vs_val = _to_fraction(c.value)
            ip, im = idx(c.pins["+"]), idx(c.pins["-"])
            k = vsource_index[c.ref]
            if ip is not None:
                matrix[ip][k] += 1
                matrix[k][ip] += 1
            if im is not None:
                matrix[im][k] -= 1
                matrix[k][im] -= 1
            rhs[k] += vs_val

    return MNAProblem(
        circuit=circuit,
        ground=ground,
        nodes=nodes,
        node_index=node_index,
        vsource_refs=vsource_refs,
        vsource_index=vsource_index,
        matrix=tuple(tuple(row) for row in matrix),
        rhs=tuple(rhs),
    )
