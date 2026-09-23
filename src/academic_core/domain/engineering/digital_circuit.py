# SPDX-License-Identifier: MIT
"""E0.1 ``digital-circuit/1``: canonical serialization of a ``DigitalCircuit``.

It makes any F8-Q circuit a data document, so that an explanation can be
replayed from the document and not only from an application demo key.
The module lives outside ``engineering/digital`` on purpose: the certified
F8-Q package stays byte-for-byte unchanged. It uses only the package's
public constructors and read-only accessors.

Wire document (JSON object; every key required, no other key allowed)::

    {"gates":   [{"id": "and_c", "inputs": ["A", "B"], "kind": "AND", "output": "C"}],
     "nets":    [{"id": "A", "initial": "LOW", "name": "A"}],
     "probes":  [{"id": "a", "net": "A"}],
     "schema":  "digital-circuit",
     "stimuli": [{"count": 8, "first": "HIGH", "id": "clkA", "net": "A",
                  "period": "0.5", "start": "0.5", "type": "toggle"}],
     "version": 1}

- ``nets``, ``gates``, ``stimuli`` and ``probes`` are sorted by id, the
  same order as the circuit's accessors. Gate ``inputs`` keep pin order
  (in0, in1, …) and may repeat a net.
- Stimulus ``type`` is one of ``constant`` (state, time), ``toggle``
  (first, start, period, count), ``pulse`` (start, width, level) or
  ``pattern`` (start, step, states), with exactly those keys plus id, net
  and type.
- States are ``"LOW"``/``"HIGH"``. Times are canonical decimal strings
  (``canonical_time``), never JSON numbers.

Canonical text: sorted keys, ``,``/``:`` separators, ASCII, no NaN.
``digest = sha256(canonical bytes)``.

Decoding is strict: size, depth and item limits first, then a JSON parse
that rejects duplicate keys, floats and NaN/Infinity, then structure,
then the certified constructors (``add_net``, ``add_component``,
``add_stimulus``, ``add_probe``), which re-validate everything, including
the single-driver rule. No class is ever looked up by name: the stimulus
``type`` selects from a fixed table.

Errors (D2, no new codes): ``SerializationError`` for the JSON layer,
``VersionMismatchError`` for an unknown version, ``ValidationError`` for
the rest.
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal

from academic_core.domain.engineering.digital import (
    ConstantStimulus,
    DigitalCircuit,
    DigitalComponent,
    DigitalProbe,
    GateKind,
    LogicState,
    PatternStimulus,
    PulseStimulus,
    ToggleStimulus,
    canonical_time,
)
from academic_core.errors import SerializationError, ValidationError, VersionMismatchError

SCHEMA = "digital-circuit"
VERSION = 1
FORMAT = f"{SCHEMA}/{VERSION}"
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_DEPTH = 4  # root > list > item > inputs/states
MAX_ITEMS = 500_000
_MAX_INT_DIGITS = 9

_TOP = frozenset({"schema", "version", "nets", "gates", "stimuli", "probes"})
_NET = frozenset({"id", "name", "initial"})
_GATE = frozenset({"id", "kind", "inputs", "output"})
_PROBE = frozenset({"id", "net"})
_STIMULUS = {
    "constant": frozenset({"id", "net", "type", "state", "time"}),
    "toggle": frozenset({"id", "net", "type", "first", "start", "period", "count"}),
    "pulse": frozenset({"id", "net", "type", "start", "width", "level"}),
    "pattern": frozenset({"id", "net", "type", "start", "step", "states"}),
}
_STATES = {"LOW": LogicState.LOW, "HIGH": LogicState.HIGH}
_KINDS = {k.value: k for k in GateKind}
_TIME_RE = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?\Z")
_STRING_RE = re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"', re.DOTALL)
_STRUCT_RE = re.compile(r"[\[\]{},]")


def _ser(reason: str, message: str) -> SerializationError:
    return SerializationError(f"{reason}: {message}")


def _bad(reason: str, message: str) -> ValidationError:
    return ValidationError(f"{reason}: {message}")


# ---------------------------------------------------------------- encoding

def _stimulus_dict(s) -> dict:
    base = {"id": s.stimulus_id, "net": s.net_id}
    if isinstance(s, ConstantStimulus):
        return {**base, "type": "constant", "state": s.state.name, "time": canonical_time(s.time)}
    if isinstance(s, ToggleStimulus):
        return {**base, "type": "toggle", "first": s.first.name, "start": canonical_time(s.start),
                "period": canonical_time(s.period), "count": s.count}
    if isinstance(s, PulseStimulus):
        return {**base, "type": "pulse", "start": canonical_time(s.start), "width": canonical_time(s.width),
                "level": s.level.name}
    if isinstance(s, PatternStimulus):
        return {**base, "type": "pattern", "start": canonical_time(s.start), "step": canonical_time(s.step),
                "states": [x.name for x in s.states]}
    raise _bad("INVALID_STIMULUS", f"unsupported stimulus {type(s).__name__}")  # pragma: no cover


def circuit_to_dict(circuit: DigitalCircuit) -> dict:
    if not isinstance(circuit, DigitalCircuit):
        raise _bad("INVALID_CIRCUIT", f"expected DigitalCircuit, got {type(circuit).__name__}")
    return {
        "schema": SCHEMA,
        "version": VERSION,
        "nets": [{"id": n.net_id, "name": n.name, "initial": n.state.name} for n in circuit.nets()],
        "gates": [{"id": g.component_id, "kind": g.kind.value, "inputs": list(g.inputs), "output": g.output}
                  for g in circuit.components()],
        "stimuli": [_stimulus_dict(s) for s in circuit.stimuli()],
        "probes": [{"id": p.probe_id, "net": p.net_id} for p in circuit.probes()],
    }


def circuit_to_json(circuit: DigitalCircuit) -> str:
    text = json.dumps(circuit_to_dict(circuit), sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False)
    if len(text) > MAX_JSON_BYTES:
        raise _ser("CIRCUIT_LIMIT", f"document exceeds {MAX_JSON_BYTES} bytes")
    return text


def circuit_digest(circuit: DigitalCircuit) -> str:
    return hashlib.sha256(circuit_to_json(circuit).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- decoding

def _obj(value, keys: frozenset, what: str) -> dict:
    if not isinstance(value, dict):
        raise _bad("INVALID_CIRCUIT", f"{what} must be an object")
    missing, extra = sorted(keys - set(value)), sorted(set(value) - keys)
    if missing or extra:
        raise _bad("INVALID_CIRCUIT", f"{what}: missing {missing[:4]} / unknown {[k[:32] for k in extra[:4]]}")
    return value


def _list(value, what: str) -> list:
    if not isinstance(value, list):
        raise _bad("INVALID_CIRCUIT", f"{what} must be an array")
    return value


def _str(value, what: str) -> str:
    if not isinstance(value, str):
        raise _bad("INVALID_CIRCUIT", f"{what} must be a string")
    return value


def _state(value, what: str) -> LogicState:
    if not isinstance(value, str) or value not in _STATES:
        raise _bad("INVALID_STATE", f"{what} must be \"LOW\" or \"HIGH\"")
    return _STATES[value]


def _time(value, what: str) -> Decimal:
    if not isinstance(value, str) or not _TIME_RE.fullmatch(value) or len(value) > 128:
        raise _bad("INVALID_TIME", f"{what} must be a canonical decimal string")
    return Decimal(value)


def _count(value, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _bad("INVALID_CIRCUIT", f"{what} must be an integer")
    return value


def _sorted_ids(items: list, what: str) -> None:
    ids = [i["id"] for i in items]
    if ids != sorted(ids) or len(set(ids)) != len(ids):
        raise _bad("NON_CANONICAL", f"{what} must be sorted by unique id")


def circuit_from_dict(data: object) -> DigitalCircuit:
    if not isinstance(data, dict):
        raise _bad("INVALID_CIRCUIT", "document must be an object")
    if data.get("schema") != SCHEMA:
        raise _bad("INVALID_SCHEMA", f"schema must be {SCHEMA!r}")
    version = data.get("version")
    if version != VERSION or isinstance(version, bool):
        raise VersionMismatchError(f"UNSUPPORTED_VERSION: {FORMAT} expected, got version {str(version)[:16]!r}")
    top = _obj(data, _TOP, "document")
    nets = [_obj(n, _NET, "net") for n in _list(top["nets"], "nets")]
    gates = [_obj(g, _GATE, "gate") for g in _list(top["gates"], "gates")]
    probes = [_obj(p, _PROBE, "probe") for p in _list(top["probes"], "probes")]
    stimuli = []
    for s in _list(top["stimuli"], "stimuli"):
        kind = s.get("type") if isinstance(s, dict) else None
        if kind not in _STIMULUS:
            raise _bad("INVALID_STIMULUS", f"stimulus type must be one of {sorted(_STIMULUS)}")
        stimuli.append(_obj(s, _STIMULUS[kind], f"{kind} stimulus"))
    for items, what in ((nets, "nets"), (gates, "gates"), (stimuli, "stimuli"), (probes, "probes")):
        _sorted_ids(items, what)
    circuit = DigitalCircuit()
    for n in nets:
        circuit.add_net(_str(n["id"], "net id"), _state(n["initial"], "net initial"), _str(n["name"], "net name"))
    for g in gates:
        kind = g["kind"]
        if not isinstance(kind, str) or kind not in _KINDS:
            raise _bad("INVALID_KIND", f"gate kind must be one of {sorted(_KINDS)}")
        inputs = tuple(_str(x, "gate input") for x in _list(g["inputs"], "gate inputs"))
        circuit.add_component(DigitalComponent(_str(g["id"], "gate id"), _KINDS[kind], inputs,
                                               _str(g["output"], "gate output")))
    for s in stimuli:
        sid, net = _str(s["id"], "stimulus id"), _str(s["net"], "stimulus net")
        if s["type"] == "constant":
            stim = ConstantStimulus(sid, net, _state(s["state"], "state"), _time(s["time"], "time"))
        elif s["type"] == "toggle":
            stim = ToggleStimulus(sid, net, _state(s["first"], "first"), _time(s["start"], "start"),
                                  _time(s["period"], "period"), _count(s["count"], "count"))
        elif s["type"] == "pulse":
            stim = PulseStimulus(sid, net, _time(s["start"], "start"), _time(s["width"], "width"),
                                 _state(s["level"], "level"))
        else:
            stim = PatternStimulus(sid, net, _time(s["start"], "start"), _time(s["step"], "step"),
                                   tuple(_state(x, "pattern state") for x in _list(s["states"], "states")))
        circuit.add_stimulus(stim)
    for p in probes:
        circuit.add_probe(DigitalProbe(_str(p["id"], "probe id"), _str(p["net"], "probe net")))
    return circuit


def _reject_float(text: str):
    raise _ser("INVALID_JSON", f"number {text[:32]!r} is not allowed (no floats)")


def _reject_constant(text: str):
    raise _ser("INVALID_JSON", f"{text} is not allowed")


def _bounded_int(text: str) -> int:
    if len(text) > _MAX_INT_DIGITS:
        raise _ser("CIRCUIT_LIMIT", f"integer with more than {_MAX_INT_DIGITS} digits")
    return int(text)


def _unique_pairs(pairs) -> dict:
    out = {}
    for key, value in pairs:
        if key in out:
            raise _ser("INVALID_JSON", f"duplicate key {key[:64]!r}")
        out[key] = value
    return out


def _prescan(text: str) -> None:
    depth = items = 0
    for m in _STRUCT_RE.finditer(_STRING_RE.sub("", text)):
        ch = m.group()
        if ch in "[{":
            depth += 1
            if depth > MAX_DEPTH:
                raise _ser("CIRCUIT_LIMIT", f"nesting deeper than {MAX_DEPTH}")
        elif ch in "]}":
            depth -= 1
        if ch not in "]}":
            items += 1
            if items > MAX_ITEMS:
                raise _ser("CIRCUIT_LIMIT", f"more than {MAX_ITEMS} JSON values")


def circuit_from_json(text: object) -> DigitalCircuit:
    """Decode untrusted ``digital-circuit/1`` JSON (``str`` or UTF-8 ``bytes``)."""
    if isinstance(text, (bytes, bytearray)):
        if len(text) > MAX_JSON_BYTES:
            raise _ser("CIRCUIT_LIMIT", f"document exceeds {MAX_JSON_BYTES} bytes")
        try:
            text = bytes(text).decode("utf-8")
        except UnicodeDecodeError:
            raise _ser("INVALID_JSON", "document is not valid UTF-8") from None
    elif isinstance(text, str):
        if len(text.encode("utf-8", "surrogatepass")) > MAX_JSON_BYTES:
            raise _ser("CIRCUIT_LIMIT", f"document exceeds {MAX_JSON_BYTES} bytes")
    else:
        raise _ser("INVALID_JSON", f"expected str or bytes, got {type(text).__name__}")
    _prescan(text)
    try:
        data = json.loads(text, object_pairs_hook=_unique_pairs, parse_float=_reject_float,
                          parse_int=_bounded_int, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise _ser("INVALID_JSON", f"{exc.msg} at position {exc.pos}") from None
    except RecursionError:
        raise _ser("CIRCUIT_LIMIT", "nesting too deep") from None
    return circuit_from_dict(data)
