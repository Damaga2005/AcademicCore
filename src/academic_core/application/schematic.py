# SPDX-License-Identifier: MIT
"""Schematic editing as pure operations on a ``Circuit`` (no Qt, no persistence).

There is no separate wire model. Two pins are connected exactly when they carry the same net name,
so the drawing and the netlist cannot disagree. A component's placement lives in its
``metadata`` (``x``, ``y`` in grid units, ``rot`` in degrees); storage already keeps metadata.

Every operation returns a new ``Circuit``; the caller saves it. Nothing here touches the engines.
"""

from __future__ import annotations

import re
from dataclasses import replace

from academic_core.domain.engineering.circuit import COMPONENT_PINS, Circuit, Component
from academic_core.domain.engineering.units import parse_quantity

GROUND = "0"
_AUTO_NET = re.compile(r"^n\d+$")

# Pin positions in grid units, before rotation: x to the right, y down. Two-terminal parts are
# 4 units long so symbols stay readable; sources stand upright as on paper.
PIN_OFFSETS: dict[str, dict[str, tuple[int, int]]] = {
    "R": {"1": (-2, 0), "2": (2, 0)}, "C": {"1": (-2, 0), "2": (2, 0)}, "L": {"1": (-2, 0), "2": (2, 0)},
    "V": {"+": (0, -2), "-": (0, 2)}, "I": {"+": (0, -2), "-": (0, 2)},
    "D": {"A": (-2, 0), "K": (2, 0)},
    "Q": {"C": (1, -2), "B": (-2, 0), "E": (1, 2)},
    "M": {"D": (1, -2), "G": (-2, 0), "S": (1, 2), "B": (2, 0)},
    "J": {"D": (1, -2), "G": (-2, 0), "S": (1, 2)},
    "E": {"+": (0, -2), "-": (0, 2)}, "G": {"+": (0, -2), "-": (0, 2)},
    "H": {"+": (0, -2), "-": (0, 2)}, "F": {"+": (0, -2), "-": (0, 2)},
    "O": {"+": (-2, -1), "-": (-2, 1), "o": (2, 0)},
    "T": {"1": (-2, -1), "2": (-2, 1), "3": (2, -1), "4": (2, 1)},
}
assert all(set(PIN_OFFSETS[t]) == set(COMPONENT_PINS[t]) for t in COMPONENT_PINS), "pin map out of sync"


def rotate_offset(offset: tuple[int, int], rot: int) -> tuple[int, int]:
    """Rotate a grid offset clockwise by a multiple of 90 degrees."""
    x, y = offset
    for _ in range((rot // 90) % 4):
        x, y = -y, x
    return x, y


def placement(comp: Component) -> tuple[int, int, int] | None:
    m = comp.metadata or {}
    if "x" in m and "y" in m:
        return int(m["x"]), int(m["y"]), int(m.get("rot", 0))
    return None


def pin_positions(comp: Component, pos: tuple[int, int, int]) -> dict[str, tuple[int, int]]:
    """Absolute grid position of every pin of ``comp`` placed at ``pos``."""
    x, y, rot = pos
    return {pin: (x + dx, y + dy)
            for pin, off in PIN_OFFSETS[comp.type.upper()].items()
            for dx, dy in [rotate_offset(off, rot)]}


def layout(circuit: Circuit) -> dict[str, tuple[int, int, int]]:
    """Placement of every component: the stored one, else a tidy default on a grid of free cells."""
    out, taken = {}, set()
    for c in circuit.components:
        p = placement(c)
        if p:
            out[c.ref.upper()] = p
            taken.add((p[0], p[1]))
    col = row = 0
    for c in sorted(circuit.components, key=lambda c: c.ref.upper()):
        if c.ref.upper() in out:
            continue
        while (col * 8 + 4, row * 8 + 4) in taken:
            col += 1
        out[c.ref.upper()] = (col * 8 + 4, row * 8 + 4, 0)
        taken.add((col * 8 + 4, row * 8 + 4))
        col += 1
        if col >= 5:
            col, row = 0, row + 1
    return out


def _rebuild(circuit: Circuit, components: list[Component]) -> Circuit:
    out = Circuit(circuit.name)
    out.notes = circuit.notes
    for c in components:
        out.add(c)
    return out


def _swap(circuit: Circuit, ref: str, new: Component | None) -> Circuit:
    ref = ref.upper()
    if not any(c.ref.upper() == ref for c in circuit.components):
        raise ValueError(f"no existe el componente {ref}")
    return _rebuild(circuit, [new if c.ref.upper() == ref and new is not None else c
                              for c in circuit.components if not (new is None and c.ref.upper() == ref)])


def _get(circuit: Circuit, ref: str) -> Component:
    for c in circuit.components:
        if c.ref.upper() == ref.upper():
            return c
    raise ValueError(f"no existe el componente {ref}")


def fresh_net(circuit: Circuit) -> str:
    n = 1
    while f"n{n}" in circuit.nets:
        n += 1
    return f"n{n}"


def next_ref(circuit: Circuit, ctype: str) -> str:
    used = {c.ref.upper() for c in circuit.components}
    n = 1
    while f"{ctype.upper()}{n}" in used:
        n += 1
    return f"{ctype.upper()}{n}"


# -- operations -------------------------------------------------------------------------------------
def place(circuit: Circuit, spec, x: int, y: int, parameters: dict, ref: str = "") -> Circuit:
    """Add a component of ``spec`` at grid (x, y); every pin starts on its own fresh net."""
    used = set(circuit.nets)
    pins = {}
    for pin in COMPONENT_PINS[spec.type]:
        n = 1
        while f"n{n}" in used:
            n += 1
        used.add(f"n{n}")
        pins[pin] = f"n{n}"
    value = parse_quantity(spec.value_default) if spec.value_label and spec.value_default else None
    comp = Component((ref or next_ref(circuit, spec.type)).upper(), spec.type, value, pins, dict(parameters),
                     {"x": int(x), "y": int(y), "rot": 0})
    return _rebuild(circuit, [*circuit.components, comp])


def move(circuit: Circuit, ref: str, x: int, y: int) -> Circuit:
    c = _get(circuit, ref)
    return _swap(circuit, ref, replace(c, metadata={**c.metadata, "x": int(x), "y": int(y),
                                                     "rot": int((c.metadata or {}).get("rot", 0))}))


def rotate(circuit: Circuit, ref: str) -> Circuit:
    c = _get(circuit, ref)
    p = placement(c) or layout(circuit)[c.ref.upper()]
    return _swap(circuit, ref, replace(c, metadata={**c.metadata, "x": p[0], "y": p[1], "rot": (p[2] + 90) % 360}))


def delete(circuit: Circuit, ref: str) -> Circuit:
    return _swap(circuit, ref, None)


def set_value(circuit: Circuit, ref: str, text: str) -> Circuit:
    c = _get(circuit, ref)
    if c.type.upper() not in ("R", "C", "L", "V", "I", "E", "G", "H", "F", "T"):
        raise ValueError(f"{c.ref} no tiene un valor que editar (su modelo está en sus parámetros)")
    return _swap(circuit, ref, replace(c, value=parse_quantity(text)))


def _net_of(circuit: Circuit, ref: str, pin: str) -> str:
    return _get(circuit, ref).pins[pin]


def _merge(circuit: Circuit, keep: str, drop: str) -> Circuit:
    if keep == drop:
        return circuit
    return _rebuild(circuit, [replace(c, pins={p: (keep if n == drop else n) for p, n in c.pins.items()})
                              for c in circuit.components])


def connect(circuit: Circuit, a: tuple[str, str], b: tuple[str, str]) -> Circuit:
    """Join two pins: they end up on one net. Ground wins, then a name the student chose over n1, n2..."""
    na, nb = _net_of(circuit, *a), _net_of(circuit, *b)
    if na == nb:
        return circuit
    if GROUND in (na, nb):
        keep = GROUND
    elif _AUTO_NET.match(na) and not _AUTO_NET.match(nb):
        keep = nb
    else:
        keep = na
    return _merge(circuit, keep, nb if keep == na else na)


def ground(circuit: Circuit, ref: str, pin: str) -> Circuit:
    """Tie a pin (and everything already wired to it) to the reference node 0."""
    return _merge(circuit, GROUND, _net_of(circuit, ref, pin))


def detach(circuit: Circuit, ref: str, pin: str) -> Circuit:
    """Move one pin onto a fresh net, leaving the rest of its old net connected."""
    c = _get(circuit, ref)
    return _swap(circuit, ref, replace(c, pins={**c.pins, pin: fresh_net(circuit)}))


def rename_net(circuit: Circuit, old: str, new: str) -> Circuit:
    new = new.strip()
    if not new or not re.fullmatch(r"[A-Za-z0-9_]+", new):
        raise ValueError("el nombre del nodo solo puede usar letras, números y _")
    return _merge(circuit, new, old)  # naming a net after an existing one joins the two


def freeze_layout(circuit: Circuit) -> Circuit:
    """Write the placement of every component into its metadata, so later edits never shuffle the drawing."""
    lay = layout(circuit)
    return _rebuild(circuit, [c if placement(c) else replace(c, metadata={
        **c.metadata, "x": lay[c.ref.upper()][0], "y": lay[c.ref.upper()][1], "rot": lay[c.ref.upper()][2]})
        for c in circuit.components])


def set_parameters(circuit: Circuit, ref: str, parameters: dict) -> Circuit:
    c = _get(circuit, ref)
    return _swap(circuit, ref, replace(c, parameters=dict(parameters)))


def nets_of(circuit: Circuit) -> dict[str, list[tuple[str, str]]]:
    """``{net: [(ref, pin), ...]}``: what is wired together, from the netlist itself."""
    out: dict[str, list[tuple[str, str]]] = {}
    for c in circuit.components:
        for pin, net in c.pins.items():
            out.setdefault(net, []).append((c.ref.upper(), pin))
    return out


def is_auto_net(name: str) -> bool:
    return bool(_AUTO_NET.match(name))
