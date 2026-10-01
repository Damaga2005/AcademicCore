# SPDX-License-Identifier: MIT
"""Editable digital circuit (``digital-design/1``): pure data + edit operations, no Qt.

The design is what the visual editor manipulates: INPUT blocks (with a
stimulus) and gates joined by wires. ``build()`` turns it into a certified
``DigitalCircuit`` using only the F8-Q constructors, so nothing is simulated
here. Net id = element id; every element is probed under its own id.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation

from academic_core.domain.engineering.digital import (
    DigitalCircuit, DigitalComponent, DigitalProbe, GateKind, LogicState,
    PatternStimulus, ToggleStimulus,
)
from academic_core.domain.engineering.digital.components import ARITY_RANGE
from academic_core.errors import ValidationError

SCHEMA = "digital-design/1"
INPUT = "INPUT"
GATES = tuple(k.value for k in GateKind)
MAX_ELEMENTS = 64
MAX_ARITY = 8
MODES = ("const", "toggle", "pattern")
_L, _H = LogicState.LOW, LogicState.HIGH
_ID = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,31}\Z")


def _bad(msg: str) -> ValidationError:
    return ValidationError(f"INVALID_DESIGN: {msg}")


def _dec(text, what: str) -> Decimal:
    try:
        v = Decimal(str(text).strip())
    except InvalidOperation:
        raise _bad(f"{what}: '{text}' no es un número") from None
    if not v.is_finite() or v < 0:
        raise _bad(f"{what}: debe ser un número ≥ 0")
    return v


def default_stim(index: int) -> dict:
    """Distinct rates so a fresh design already shows every input combination."""
    return {"mode": "toggle", "initial": "LOW", "first": "HIGH", "start": "0.5",
            "period": str(Decimal("0.5") * (2 ** index)), "count": max(2, 8 >> index),
            "step": "1", "states": "HLH"}


class DigitalDesign:
    def __init__(self, name: str = "mi-circuito"):
        self.name = name
        self.elements: dict[str, dict] = {}
        self.wires: list[tuple[str, str, int]] = []  # (source id, gate id, input pin)

    # -- editing ---------------------------------------------------------------
    def _new_id(self, prefix: str) -> str:
        if len(self.elements) >= MAX_ELEMENTS:
            raise _bad(f"máximo {MAX_ELEMENTS} elementos")
        k = 1
        while f"{prefix}{k}" in self.elements:
            k += 1
        return f"{prefix}{k}"

    def add_input(self, x: int = 0, y: int = 0) -> str:
        n = sum(1 for e in self.elements.values() if e["type"] == INPUT)
        eid = self._new_id("in")
        self.elements[eid] = {"type": INPUT, "x": x, "y": y, **default_stim(n)}
        return eid

    def add_gate(self, kind: str, x: int = 0, y: int = 0) -> str:
        if kind not in GATES:
            raise _bad(f"puerta desconocida: {kind}")
        eid = self._new_id(kind.lower())
        self.elements[eid] = {"type": kind, "x": x, "y": y, "n": ARITY_RANGE[GateKind(kind)][0]}
        return eid

    def move(self, eid: str, x: int, y: int) -> None:
        self._el(eid).update(x=x, y=y)

    def rename(self, eid: str, new: str) -> None:
        self._el(eid)
        if not _ID.fullmatch(new or ""):
            raise _bad("el nombre usa letras, dígitos o _ (máx. 32) y no empieza por dígito")
        if new == eid:
            return
        if new in self.elements:
            raise _bad(f"ya existe '{new}'")
        self.elements = {(new if k == eid else k): v for k, v in self.elements.items()}
        self.wires = [(new if s == eid else s, new if d == eid else d, p) for s, d, p in self.wires]

    def delete(self, eid: str) -> None:
        self._el(eid)
        del self.elements[eid]
        self.wires = [w for w in self.wires if eid not in w[:2]]

    def connect(self, src: str, dst: str, pin: int) -> None:
        self._el(src)
        gate = self._el(dst)
        if gate["type"] == INPUT:
            raise _bad("una entrada no tiene pines de entrada")
        if not 0 <= pin < gate["n"]:
            raise _bad(f"{dst} no tiene el pin {pin}")
        if src == dst:
            raise _bad("una puerta no puede alimentarse a sí misma")
        self.wires = [w for w in self.wires if (w[1], w[2]) != (dst, pin)] + [(src, dst, pin)]

    def disconnect(self, dst: str, pin: int) -> None:
        self.wires = [w for w in self.wires if (w[1], w[2]) != (dst, pin)]

    def set_arity(self, gid: str, n: int) -> None:
        g = self._el(gid)
        if g["type"] == INPUT:
            raise _bad("una entrada no tiene número de pines")
        lo, hi = ARITY_RANGE[GateKind(g["type"])]
        if not lo <= n <= min(hi, MAX_ARITY):
            raise _bad(f"{g['type']} admite de {lo} a {min(hi, MAX_ARITY)} entradas")
        g["n"] = n
        self.wires = [w for w in self.wires if w[1] != gid or w[2] < n]

    def set_stimulus(self, eid: str, **fields) -> None:
        e = self._el(eid)
        if e["type"] != INPUT:
            raise _bad("solo las entradas tienen estímulo")
        new = {**e, **fields}
        if new["mode"] not in MODES:
            raise _bad(f"modo desconocido: {new['mode']}")
        for key in ("start", "period", "step"):
            if _dec(new[key], key) <= 0 and key != "start":
                raise _bad(f"{key} debe ser > 0")
        if new["mode"] == "toggle" and not 1 <= int(new["count"]) <= 1000:
            raise _bad("count debe estar entre 1 y 1000")
        if new["mode"] == "pattern" and not re.fullmatch(r"[HLhl01]{1,64}", str(new["states"])):
            raise _bad("el patrón usa H/L (o 1/0), de 1 a 64 símbolos")
        e.update(new)

    def _el(self, eid: str) -> dict:
        if eid not in self.elements:
            raise _bad(f"no existe el elemento '{eid}'")
        return self.elements[eid]

    # -- translation to the certified engine -----------------------------------
    def source_of(self, gid: str, pin: int) -> str | None:
        return next((s for s, d, p in self.wires if d == gid and p == pin), None)

    def problems(self) -> list[str]:
        out = []
        if not any(e["type"] != INPUT for e in self.elements.values()):
            out.append("añade al menos una puerta")
        for gid, g in self.elements.items():
            if g["type"] == INPUT:
                continue
            for pin in range(g["n"]):
                if self.source_of(gid, pin) is None:
                    out.append(f"{gid}: pin {pin} sin conectar")
        return out

    def build(self) -> DigitalCircuit:
        problems = self.problems()
        if problems:
            raise _bad("; ".join(problems[:4]))
        c = DigitalCircuit()
        for eid, e in self.elements.items():
            c.add_net(eid, _H if e["type"] == INPUT and e["initial"] == "HIGH" and e["mode"] == "const" else _L)
        for eid, e in self.elements.items():
            if e["type"] == INPUT:
                if e["mode"] == "toggle":
                    c.add_stimulus(ToggleStimulus(f"s_{eid}", eid, _H if e["first"] == "HIGH" else _L,
                                                  _dec(e["start"], "start"), _dec(e["period"], "period"),
                                                  int(e["count"])))
                elif e["mode"] == "pattern":
                    states = tuple(_H if ch in "Hh1" else _L for ch in e["states"])
                    c.add_stimulus(PatternStimulus(f"s_{eid}", eid, _dec(e["start"], "start"),
                                                   _dec(e["step"], "step"), states))
            else:
                ins = tuple(self.source_of(eid, p) for p in range(e["n"]))
                c.add_component(DigitalComponent(f"c_{eid}", GateKind(e["type"]), ins, eid))
            c.add_probe(DigitalProbe(eid, eid))
        return c

    # -- digital-design/1 --------------------------------------------------------
    def to_json(self) -> str:
        return json.dumps({"schema": SCHEMA, "name": self.name, "elements": self.elements,
                           "wires": [list(w) for w in self.wires]}, indent=1, sort_keys=True)

    @classmethod
    def from_json(cls, text: str | bytes) -> "DigitalDesign":
        try:
            doc = json.loads(text)
            if doc["schema"] != SCHEMA:
                raise _bad("formato desconocido (se esperaba digital-design/1)")
            d = cls(str(doc["name"])[:64])
            for eid, e in doc["elements"].items():
                if not _ID.fullmatch(eid):
                    raise _bad(f"id no válido: {eid!r}")
                d.elements[eid] = dict(e)
            d.wires = [(str(s), str(t), int(p)) for s, t, p in doc["wires"]]
        except (ValueError, KeyError, TypeError) as exc:
            if isinstance(exc, ValidationError):
                raise
            raise _bad("el archivo no es un diseño digital válido") from None
        if len(d.elements) > MAX_ELEMENTS:
            raise _bad("demasiados elementos")
        for eid, e in d.elements.items():  # re-validate through the same rules as the editor
            if e.get("type") == INPUT:
                d.set_stimulus(eid)
            elif e.get("type") in GATES:
                d.set_arity(eid, int(e["n"]))
            else:
                raise _bad(f"tipo desconocido en {eid}")
        for s, t, p in list(d.wires):
            d.wires.remove((s, t, p))
            d.connect(s, t, p)
        return d
