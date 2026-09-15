"""Linear dependent-source control semantics shared by DC and AC (F8-E).

This module owns everything both engines must agree on, so the two
stamps cannot diverge:

* the dependent type sets and gain-dimension map;
* structural validation (control presence/shape, net and ref membership);
* the current-control dependency graph, cycle detection
  (`CircularControlError`) and a deterministic resolution order;
* the public provenance descriptor (`describe_dependents`).

Number-type-specific work (Fraction vs D1 complex) lives in the
engines (`mna.problem`, `ac.problem`, `ac.solution`); the symbolic
rules here (which branch kinds resolve to what) are engine-agnostic.

Control model (no heuristics, no name search, no list positions):

* voltage control (E/G): an explicit node pair ``cp``/``cn`` from
  ``parameters``; any two nets of the circuit (ground allowed, output
  nets allowed, ``cp == cn`` allowed and means zero control). Node
  pairs stamp directly, so voltage control never recurses and can
  never cycle.
* current control (H/F): ``control_ref`` naming exactly one component
  (case-insensitive, multigraph-safe edge identity via ref).
  ``Icontrol`` is the D3/F8-B reconstructed branch current:
  pin1->pin2 for R/L/C, +->- aux unknown for V/E/H outputs, ``-Is``
  for independent I, ``gm·ΔV`` for G outputs, ``β·Ictrl`` for F
  outputs. Resolution recurses only through F outputs; a revisit is
  a genuine dependency cycle and raises `CircularControlError`.
  Self-current-control of an F output is the length-1 case of this.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.mna.errors import (
    CircularControlError,
    InvalidCircuitError,
)
from academic_core.domain.engineering.units import (
    ADMITTANCE,
    DIMENSIONLESS,
    RESISTANCE,
)

DEPENDENT_TYPES = frozenset({"E", "G", "H", "F"})

#: Component types whose branches carry an MNA auxiliary current
#: unknown (independent V plus dependent E/H outputs).
VOLTAGE_BRANCH_TYPES = frozenset({"V", "E", "H"})

#: Kind -> SPICE-style role.
DEPENDENT_KIND = {"E": "VCVS", "G": "VCCS", "H": "CCVS", "F": "CCCS"}

#: Output kinds needing an MNA auxiliary current unknown (like V).
VOLTAGE_OUTPUT_TYPES = frozenset({"E", "H"})

#: Output kinds stamped Norton-style, needing no new unknown (like I).
CURRENT_OUTPUT_TYPES = frozenset({"G", "F"})

VOLTAGE_CONTROLLED = frozenset({"E", "G"})
CURRENT_CONTROLLED = frozenset({"H", "F"})

#: Gain dimension per kind (E/F dimensionless, G Siemens, H Ohm).
GAIN_DIMENSION = {
    "E": DIMENSIONLESS,
    "G": ADMITTANCE,
    "H": RESISTANCE,
    "F": DIMENSIONLESS,
}


def _params(c) -> dict:
    return dict(c.parameters or {})


def validate_dependent_structure(circuit) -> None:
    """Structural validation of every E/G/H/F component.

    Checks control presence/shape and membership (nets/refs exist).
    Gain dimensions/values are checked by the engines against their
    own dimension maps (same rule, engine-native numbers).
    """
    nets = set(circuit.nets)
    refs = {c.ref.upper(): c for c in circuit.components}
    for c in circuit.components:
        t = c.type.upper()
        if t not in DEPENDENT_TYPES:
            continue
        p = _params(c)
        if t in VOLTAGE_CONTROLLED:
            cp, cn = p.get("cp"), p.get("cn")
            for label, net in (("cp", cp), ("cn", cn)):
                if not isinstance(net, str) or not net.strip():
                    raise InvalidCircuitError(
                        f"{c.ref}: {t} needs control nets 'cp'/'cn', got "
                        f"{label}={net!r}")
                if net not in nets:
                    raise InvalidCircuitError(
                        f"{c.ref}: control net {net!r} is not a net of "
                        f"circuit {circuit.name!r}")
        else:
            ctrl = p.get("control_ref")
            if not isinstance(ctrl, str) or not ctrl.strip():
                raise InvalidCircuitError(
                    f"{c.ref}: {t} needs 'control_ref', got {ctrl!r}")
            if ctrl.upper() not in refs:
                raise InvalidCircuitError(
                    f"{c.ref}: control_ref {ctrl!r} names no component of "
                    f"circuit {circuit.name!r}")


def control_graph(circuit) -> dict[str, str]:
    """control_ref edges for H/F (REF-UPPER -> CTRL-REF-UPPER), sorted."""
    graph = {}
    for c in circuit.components:
        if c.type.upper() in CURRENT_CONTROLLED:
            graph[c.ref.upper()] = str(
                _params(c).get("control_ref", "")).upper()
    return dict(sorted(graph.items()))


def check_control_cycles(circuit) -> None:
    """Raise `CircularControlError` on any current-control dependency cycle.

    Only F outputs force recursion (their current has no MNA unknown of
    its own); every other control-target kind terminates resolution
    (aux unknown, constant, or inline expression), so only paths
    through F matter. A self-controlled F output is the length-1 cycle.
    NOTE (pre-F8-F audit fix): an H output controlling itself is NOT a
    cycle — its own auxiliary unknown exists directly, resolution never
    recurses. The check below therefore follows an edge only into F
    targets, exactly mirroring the resolver.
    """
    refs = {c.ref.upper(): c.type.upper() for c in circuit.components}
    graph = control_graph(circuit)

    def target_kind(ref_upper: str) -> str | None:
        return refs.get(ref_upper)

    def visit(node: str, stack: tuple[str, ...]) -> None:
        ctrl = graph.get(node)
        if ctrl is None:
            return
        if target_kind(ctrl) != "F":
            return  # terminal: aux unknown, constant, or inline form
        if ctrl in stack:
            cycle = " -> ".join(stack + (ctrl,))
            raise CircularControlError(
                f"circular current control: {cycle} (control-current "
                f"resolution by substitution cannot represent the loop)")
        visit(ctrl, stack + (ctrl,))

    for ref in sorted(graph):
        visit(ref, (ref,))


def resolution_order(circuit) -> tuple[str, ...]:
    """Deterministic order in which H/F controls resolve ( callees first).

    Valid only after `check_control_cycles` (acyclic graph guaranteed).
    """
    refs = {c.ref.upper(): c.type.upper() for c in circuit.components}
    graph = control_graph(circuit)
    order: list[str] = []
    done: set[str] = set()

    def emit(node: str) -> None:
        if node in done:
            return
        done.add(node)
        ctrl = graph.get(node)
        if ctrl is not None and refs.get(ctrl) == "F" and ctrl in graph:
            emit(ctrl)
        order.append(node)

    for ref in sorted(graph):
        emit(ref)
    return tuple(order)


def gain_fraction(value) -> Fraction:
    """Exact gain for the DC engine (finite Decimal -> exact Fraction)."""
    base = value.to_base()
    if not base.is_finite():
        raise InvalidCircuitError(
            f"non-finite gain {value.format()}")
    return Fraction(base)


@dataclass(frozen=True)
class DependentEntry:
    ref: str
    kind: str  # VCVS | VCCS | CCVS | CCCS
    gain: str  # base-unit value string
    control: str  # "cp=X,cn=Y" | "control_ref=Z"

    def to_dict(self) -> dict:
        return {"ref": self.ref, "kind": self.kind, "gain": self.gain,
                "control": self.control}


@dataclass(frozen=True)
class DependentGraph:
    """Provenance descriptor for a circuit's dependents (F8-E §34)."""

    entries: tuple[DependentEntry, ...]
    edges: tuple[tuple[str, str], ...]  # (controller, control_ref)
    digest: str

    def to_dict(self) -> dict:
        return {
            "engine": "f8e-dependent-sources",
            "version": "1.0",
            "entries": [e.to_dict() for e in self.entries],
            "edges": [list(e) for e in self.edges],
        }


def describe_dependents(circuit) -> DependentGraph:
    """Canonical, timestamp-free description of a circuit's dependents."""
    entries: list[DependentEntry] = []
    for c in sorted(circuit.components, key=lambda e: e.ref.upper()):
        t = c.type.upper()
        if t not in DEPENDENT_TYPES:
            continue
        p = _params(c)
        if t in VOLTAGE_CONTROLLED:
            control = f"cp={p.get('cp')},cn={p.get('cn')}"
        else:
            control = f"control_ref={str(p.get('control_ref', '')).upper()}"
        gain = str(c.value.to_base()) if c.value is not None else "none"
        entries.append(DependentEntry(c.ref.upper(), DEPENDENT_KIND[t],
                                      gain, control))
    graph = control_graph(circuit)
    edges = tuple((k, v) for k, v in sorted(graph.items()))
    digest = hashlib.sha256(json.dumps({
        "engine": "f8e-dependent-sources/1.0",
        "entries": [e.to_dict() for e in entries],
        "edges": [list(e) for e in edges],
    }, sort_keys=True, default=str).encode()).hexdigest()
    return DependentGraph(tuple(entries), edges, digest)
