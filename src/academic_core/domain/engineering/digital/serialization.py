# SPDX-License-Identifier: MIT
"""F8-Q.4 ``digital-trace/1``: canonical serialization of ``DigitalTrace``.

Wire document (JSON object, every key required, no other key allowed)::

    {"channels": [{"initial_state": "LOW",
                   "net_id": "Y",
                   "no_op_count": 0,
                   "probe_id": "y",
                   "samples": [{"state": "HIGH", "time": "0.5"}, ...]},
                  ...],
     "schema": "digital-trace",
     "version": 1,
     "window": {"end_time": "1.75", "start_time": "0"}}

- ``channels`` are sorted by ``probe_id`` (unique). One channel per probe;
  the channel is identified by its ``probe_id`` (there is no separate
  channel id in v1). ``net_id`` may repeat: channels on the same net carry
  identical content.
- ``samples`` are the real transitions, in canonical processing order. The
  position IS the order (same-time transitions such as ``t=1 HIGH`` then
  ``t=1 LOW`` keep their order and are never collapsed). The runtime
  ``sequence`` is not serialized; decoding assigns the position.
- States are the strings ``"LOW"`` / ``"HIGH"``. Nothing else is accepted
  (no 0/1, booleans, null, lowercase, ``X`` or ``Z``).
- Times are JSON strings holding the canonical decimal form of a Decimal
  (``canonical_time``). They are never JSON numbers and never floats.

Canonical representation: ``json.dumps`` of ``trace_to_dict`` with sorted
keys, separators ``,`` / ``:``, ``ensure_ascii=True``, ``allow_nan=False``
and no trailing newline, encoded as UTF-8. Every string in the document is
ASCII by construction (ids match ``ID_RE``), so no escape ever occurs.
``digest = sha256(canonical bytes)``.

Decoding treats its input as untrusted data: size/depth/item limits first,
then a strict JSON parse (duplicate keys, floats, NaN/Infinity rejected),
then strict structural validation, then the typed constructors. No eval,
pickle, dynamic import or class lookup by name.

Errors (D2, no new codes): ``SerializationError`` (AC-SER-001) for the
JSON layer and its size limits, ``VersionMismatchError`` (AC-VER-001) for
an unknown version, ``ValidationError`` (AC-VAL-001) for everything else.
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal

from academic_core.domain.engineering.digital.core import (
    MAX_EVENTS,
    LogicState,
    _invalid,
    check_id,
    check_time,
)
from academic_core.domain.engineering.digital.trace import (
    MAX_PROBES,
    DigitalTrace,
    TraceChannel,
    TraceSample,
)
from academic_core.errors import SerializationError, VersionMismatchError

DIGITAL_TRACE_SCHEMA = "digital-trace"
DIGITAL_TRACE_VERSION = 1
DIGITAL_TRACE_FORMAT = f"{DIGITAL_TRACE_SCHEMA}/{DIGITAL_TRACE_VERSION}"

MAX_TRACE_JSON_BYTES = 16 * 1024 * 1024
MAX_TRACE_CHANNELS = MAX_PROBES
MAX_TRACE_SAMPLES = 200_000  # total over all channels (same-net channels count each)
MAX_TRACE_STRING = 128  # any string value (ids are <= 64 by ID_RE)
MAX_TRACE_DEPTH = 5  # root > channels > channel > samples > sample
MAX_TRACE_ITEMS = 1_000_000  # bound on JSON values, counted as { [ , tokens
MAX_TRACE_NOOPS = MAX_EVENTS  # per channel; a run never processes more
_MAX_INT_DIGITS = 20

_TOP_KEYS = frozenset({"schema", "version", "window", "channels"})
_WINDOW_KEYS = frozenset({"start_time", "end_time"})
_CHANNEL_KEYS = frozenset({"probe_id", "net_id", "initial_state", "samples", "no_op_count"})
_SAMPLE_KEYS = frozenset({"time", "state"})

_STATES = {"LOW": LogicState.LOW, "HIGH": LogicState.HIGH}
_TIME_RE = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?\Z")
_STRING_RE = re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"', re.DOTALL)  # unrolled: linear, no per-char alternation
_STRUCT_RE = re.compile(r"[\[\]{},]")


def _serialization(reason: str, message: str) -> SerializationError:
    return SerializationError(f"{reason}: {message}")


# ---------------------------------------------------------------- encoding

def canonical_time(value: object) -> str:
    """Unique canonical text of a valid time (``check_time``).

    Plain positional notation, no exponent, no sign, no trailing
    fractional zeros, no trailing ``.``; zero is ``"0"``. Numerically equal
    Decimals (``1``, ``1.0``, ``1.00``, ``1E+0``) give the same text, and
    ``Decimal(canonical_time(t)) == t`` exactly. Built from the digit tuple,
    so no context precision or rounding is involved.
    """
    t = check_time(value)
    if t.is_zero():
        return "0"
    _, digits, exp = t.as_tuple()
    digits = list(digits)
    while exp < 0 and digits[-1] == 0:
        digits.pop()
        exp += 1
    if len(digits) > MAX_TRACE_STRING or -exp > MAX_TRACE_STRING:  # never build a huge string
        raise _invalid("TRACE_LIMIT", f"time {t} needs more than {MAX_TRACE_STRING} characters")
    text = "".join(map(str, digits))
    point = len(text) + exp
    if exp >= 0:
        out = text + "0" * exp
    elif point > 0:
        out = f"{text[:point]}.{text[point:]}"
    else:
        out = "0." + "0" * -point + text
    if len(out) > MAX_TRACE_STRING:
        raise _invalid("TRACE_LIMIT", f"time {t} needs more than {MAX_TRACE_STRING} characters")
    return out


def trace_to_dict(trace: DigitalTrace) -> dict:
    """JSON-safe ``digital-trace/1`` structure (fresh dicts/lists, str/int only)."""
    if not isinstance(trace, DigitalTrace):
        raise _invalid("INVALID_TRACE", f"expected DigitalTrace, got {type(trace).__name__}")
    total = sum(len(c.samples) for c in trace.channels)
    if total > MAX_TRACE_SAMPLES:
        raise _invalid("TRACE_LIMIT", f"{total} samples exceed {MAX_TRACE_SAMPLES}")
    channels = []
    for c in trace.channels:
        if c.noop_count > MAX_TRACE_NOOPS:
            raise _invalid("TRACE_LIMIT", f"channel {c.probe_id!r} no_op_count exceeds {MAX_TRACE_NOOPS}")
        channels.append({
            "probe_id": c.probe_id,
            "net_id": c.net_id,
            "initial_state": c.initial.name,
            "samples": [{"time": canonical_time(s.time), "state": s.state.name} for s in c.samples],
            "no_op_count": c.noop_count,
        })
    return {
        "schema": DIGITAL_TRACE_SCHEMA,
        "version": DIGITAL_TRACE_VERSION,
        "window": {"start_time": canonical_time(trace.start), "end_time": canonical_time(trace.end)},
        "channels": channels,
    }


def _dumps(data: dict) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def trace_to_json(trace: DigitalTrace) -> str:
    """Canonical JSON text; refuses anything ``trace_from_json`` would refuse."""
    text = _dumps(trace_to_dict(trace))
    if len(text) > MAX_TRACE_JSON_BYTES:  # ASCII: characters == bytes
        raise _serialization("TRACE_LIMIT", f"document exceeds {MAX_TRACE_JSON_BYTES} bytes")
    return text


def trace_digest(trace: DigitalTrace) -> str:
    """``sha256(UTF-8 canonical JSON)`` hex (64 lowercase hex digits)."""
    return hashlib.sha256(trace_to_json(trace).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- decoding

def _object(value: object, keys: frozenset, what: str) -> dict:
    if not isinstance(value, dict):
        raise _invalid("INVALID_TRACE", f"{what} must be an object, got {type(value).__name__}")
    missing = sorted(keys - value.keys())
    if missing:
        raise _invalid("INVALID_TRACE", f"{what} missing field(s) {missing}")
    extra = sorted(str(k)[:MAX_TRACE_STRING] for k in value.keys() - keys)
    if extra:
        raise _invalid("INVALID_TRACE", f"{what} has unknown field(s) {extra}")
    return value


def _array(value: object, what: str) -> list:
    if not isinstance(value, list):
        raise _invalid("INVALID_TRACE", f"{what} must be an array, got {type(value).__name__}")
    return value


def _string(value: object, what: str) -> str:
    if not isinstance(value, str):
        raise _invalid("INVALID_TRACE", f"{what} must be a string, got {type(value).__name__}")
    if len(value) > MAX_TRACE_STRING:
        raise _invalid("TRACE_LIMIT", f"{what} longer than {MAX_TRACE_STRING} characters")
    return value


def _count(value: object, what: str, bound: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _invalid("INVALID_TRACE", f"{what} must be an integer, got {type(value).__name__}")
    if value < 0:
        raise _invalid("INVALID_TRACE", f"{what} must be >= 0, got {value}")
    if value > bound:
        raise _invalid("TRACE_LIMIT", f"{what} {value} exceeds {bound}")
    return value


def _time(value: object, what: str) -> Decimal:
    text = _string(value, what)
    if not _TIME_RE.match(text):
        raise _invalid("INVALID_TIME", f"{what} {text!r} is not a canonical decimal string")
    return check_time(Decimal(text))


def _state(value: object, what: str) -> LogicState:
    if not isinstance(value, str) or value not in _STATES:
        shown = repr(value)[:MAX_TRACE_STRING]
        raise _invalid("INVALID_STATE", f"{what} must be \"LOW\" or \"HIGH\", got {shown}")
    return _STATES[value]


def _ident(value: object, what: str) -> str:
    return check_id(_string(value, what), what)


def trace_from_dict(data: object) -> DigitalTrace:
    """Strictly validate a ``digital-trace/1`` structure and build the trace."""
    if not isinstance(data, dict):
        raise _invalid("INVALID_TRACE", f"document must be an object, got {type(data).__name__}")
    schema = data.get("schema")
    if not isinstance(schema, str) or schema != DIGITAL_TRACE_SCHEMA:
        raise _invalid("INVALID_SCHEMA", f"schema must be {DIGITAL_TRACE_SCHEMA!r}, "
                       f"got {repr(schema)[:MAX_TRACE_STRING]}")
    version = data.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version != DIGITAL_TRACE_VERSION:
        raise VersionMismatchError(f"UNSUPPORTED_VERSION: {DIGITAL_TRACE_SCHEMA} version "
                                   f"{repr(version)[:MAX_TRACE_STRING]} (supported: {DIGITAL_TRACE_VERSION})")
    _object(data, _TOP_KEYS, "document")
    window = _object(data["window"], _WINDOW_KEYS, "window")
    start = _time(window["start_time"], "window.start_time")
    end = _time(window["end_time"], "window.end_time")
    if end < start:
        raise _invalid("INVALID_TRACE", f"window end_time {end} before start_time {start}")
    raw_channels = _array(data["channels"], "channels")
    if len(raw_channels) > MAX_TRACE_CHANNELS:
        raise _invalid("TRACE_LIMIT", f"more than {MAX_TRACE_CHANNELS} channels")
    channels: list[TraceChannel] = []
    seen: set[str] = set()
    total = 0
    for k, raw in enumerate(raw_channels):
        where = f"channels[{k}]"
        ch = _object(raw, _CHANNEL_KEYS, where)
        probe_id = _ident(ch["probe_id"], f"{where}.probe_id")
        if probe_id in seen:
            raise _invalid("DUPLICATE_PROBE", f"{where}.probe_id {probe_id!r} repeated")
        if channels and probe_id < channels[-1].probe_id:
            raise _invalid("INVALID_TRACE", f"{where}: channels must be sorted by probe_id")
        seen.add(probe_id)
        net_id = _ident(ch["net_id"], f"{where}.net_id")
        initial = _state(ch["initial_state"], f"{where}.initial_state")
        noops = _count(ch["no_op_count"], f"{where}.no_op_count", MAX_TRACE_NOOPS)
        raw_samples = _array(ch["samples"], f"{where}.samples")
        total += len(raw_samples)
        if total > MAX_TRACE_SAMPLES:
            raise _invalid("TRACE_LIMIT", f"more than {MAX_TRACE_SAMPLES} samples")
        samples = []
        for j, rs in enumerate(raw_samples):
            s = _object(rs, _SAMPLE_KEYS, f"{where}.samples[{j}]")
            # position is the order; it doubles as the (non-observable) sequence
            samples.append(TraceSample(_time(s["time"], f"{where}.samples[{j}].time"), j,
                                       _state(s["state"], f"{where}.samples[{j}].state")))
        channels.append(TraceChannel(probe_id, net_id, initial, tuple(samples), noops))
    return DigitalTrace(start, end, tuple(channels))


def _reject_float(text: str):
    raise _serialization("INVALID_JSON", f"number {text[:32]!r} is not allowed (no floats)")


def _reject_constant(text: str):
    raise _serialization("INVALID_JSON", f"{text} is not allowed")


def _bounded_int(text: str) -> int:
    if len(text) > _MAX_INT_DIGITS:
        raise _serialization("TRACE_LIMIT", f"integer with more than {_MAX_INT_DIGITS} digits")
    return int(text)


def _unique_pairs(pairs: list) -> dict:
    out = {}
    for key, value in pairs:
        if key in out:
            raise _serialization("INVALID_JSON", f"duplicate key {key[:MAX_TRACE_STRING]!r}")
        out[key] = value
    return out


def _prescan(text: str) -> None:
    """Bound nesting depth and value count before ``json.loads`` builds anything.

    String literals are removed first so brackets inside strings don't
    count. On malformed input the scan is approximate; ``json.loads``
    rejects such input afterwards anyway.
    """
    depth = items = 0
    for m in _STRUCT_RE.finditer(_STRING_RE.sub("", text)):
        ch = m.group()
        if ch in "[{":
            depth += 1
            if depth > MAX_TRACE_DEPTH:
                raise _serialization("TRACE_LIMIT", f"nesting deeper than {MAX_TRACE_DEPTH}")
        elif ch in "]}":
            depth -= 1
        if ch != "]" and ch != "}":
            items += 1
            if items > MAX_TRACE_ITEMS:
                raise _serialization("TRACE_LIMIT", f"more than {MAX_TRACE_ITEMS} JSON values")


def trace_from_json(text: object) -> DigitalTrace:
    """Decode untrusted ``digital-trace/1`` JSON (``str`` or UTF-8 ``bytes``)."""
    if isinstance(text, (bytes, bytearray)):
        if len(text) > MAX_TRACE_JSON_BYTES:
            raise _serialization("TRACE_LIMIT", f"document exceeds {MAX_TRACE_JSON_BYTES} bytes")
        try:
            text = bytes(text).decode("utf-8")
        except UnicodeDecodeError:
            raise _serialization("INVALID_JSON", "document is not valid UTF-8") from None
    elif isinstance(text, str):
        if len(text) > MAX_TRACE_JSON_BYTES or len(text.encode("utf-8", "surrogatepass")) > MAX_TRACE_JSON_BYTES:
            raise _serialization("TRACE_LIMIT", f"document exceeds {MAX_TRACE_JSON_BYTES} bytes")
    else:
        raise _serialization("INVALID_JSON", f"expected str or bytes, got {type(text).__name__}")
    _prescan(text)
    try:
        data = json.loads(text, object_pairs_hook=_unique_pairs, parse_float=_reject_float,
                          parse_int=_bounded_int, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise _serialization("INVALID_JSON", f"{exc.msg} at position {exc.pos}") from None
    except RecursionError:
        raise _serialization("TRACE_LIMIT", "nesting too deep") from None
    return trace_from_dict(data)
