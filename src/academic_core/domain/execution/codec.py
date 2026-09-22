# SPDX-License-Identifier: MIT
"""E0 ``execution-trace/1``: canonical serialization, digest, strict decoding.

This follows the F8-Q.4 ``digital-trace/1`` conventions but is its own
schema; it never reuses the digital one.

Document (JSON object; every key required; unknown keys rejected at every
level)::

    {"schema": "execution-trace", "version": 1,
     "operation": "engineering.equation",
     "inputs":  [{"name": "V", "value": VALUE}, ...],        # emission order
     "events":  [EVENT, ...],                                 # emission order = ids e1..eN
     "result":  VALUE | null,
     "outcome": "SUCCESS" | "FAILED",
     "verification": {"status": "PASS"|"FAIL"|"NONE", "checks": int, "failed": int},
     "metadata": {"key": "text", ...}}                        # diagnostic, NOT digested

    VALUE = {"number": "2.5", "unit": "V", "dimension": [1,2,-3,-1,0,0,0]}  | {"text": "HIGH"}
    EVENT = {"id": "e3", "kind": "STEP", "title": ..., "refs": ["e1","e2"],
             "formula": str|null, "why": str|null,
             "values": [{"name": ..., "value": VALUE}], "result": VALUE|null,
             "check": {"what","actual","expected","tolerance","status","detail"}|null,
             "error": {"code","reason","message"}|null}

Canonical form:

- ``json.dumps`` with sorted keys, ``,`` / ``:`` separators,
  ``ensure_ascii=True`` (non-ASCII text escaped as ``\\uXXXX``, one
  deterministic spelling), ``allow_nan=False`` and no trailing newline,
  encoded as UTF-8.
- Numbers are JSON *strings* in canonical decimal form (``canonical_decimal``):
  plain positional notation, no exponent, no trailing fractional zeros,
  ``-`` only for negatives, zero is ``"0"``. Numerically equal Decimals
  therefore serialize identically. Floats never occur.

Digest = SHA-256 of the canonical JSON of the document **without**
``metadata``:

- It covers: schema, version, operation, inputs, events (every field,
  order included), result, outcome, verification.
- It excludes: metadata (diagnostics), and anything not in the document
  (wall clock, PIDs, memory, thread ids, paths, environment).

Decoding (untrusted input) runs in this order:

1. type and byte limit
2. strict UTF-8
3. a depth/value-count pre-scan
4. ``json.loads`` with hooks that reject duplicate keys, floats,
   NaN/Infinity and huge integers
5. strict structure
6. the typed model constructors, which revalidate ids, references,
   causality order, outcome and verification

There is no eval, pickle or dynamic import. Errors are D2:
``SerializationError`` for the JSON layer and size, ``VersionMismatchError``
for the version, ``ValidationError`` for the rest.
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal

from academic_core.domain.execution.model import (
    FORMAT,
    MAX_EVENTS,
    MAX_NUMBER_DIGITS,
    SCHEMA,
    VERSION,
    CheckStatus,
    EventKind,
    ExecutionTrace,
    Outcome,
    TraceCheck,
    TraceError,
    TraceEvent,
    TraceValue,
    Verification,
    VerificationStatus,
    _invalid,
)
from academic_core.errors import SerializationError, VersionMismatchError

MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_DEPTH = 7  # root > events > event > check > actual > dimension (+ values > item > value)
MAX_ITEMS = 2_000_000
_MAX_INT_DIGITS = 12

_TOP = frozenset({"schema", "version", "operation", "inputs", "events", "result", "outcome",
                  "verification", "metadata"})
_EVENT = frozenset({"id", "kind", "title", "refs", "formula", "why", "values", "result", "check", "error"})
_CHECK = frozenset({"what", "actual", "expected", "tolerance", "status", "detail"})
_ERROR = frozenset({"code", "reason", "message"})
_VERIFICATION = frozenset({"status", "checks", "failed"})
_NAMED = frozenset({"name", "value"})
_NUMBER = frozenset({"number", "unit", "dimension"})
_TEXT = frozenset({"text"})

_NUMBER_RE = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?\Z")
_STRING_RE = re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"', re.DOTALL)
_STRUCT_RE = re.compile(r"[\[\]{},]")


def _ser(reason: str, message: str) -> SerializationError:
    return SerializationError(f"{reason}: {message}")


# ---------------------------------------------------------------- encoding

def canonical_decimal(value: Decimal) -> str:
    """Unique positional text of a finite Decimal, built from its digits (no context, no rounding)."""
    if isinstance(value, bool) or not isinstance(value, Decimal) or not value.is_finite():
        raise _invalid("INVALID_VALUE", f"expected a finite Decimal, got {value!r}")
    if value.is_zero():
        return "0"
    sign, digits, exp = value.as_tuple()
    digits = list(digits)
    while exp < 0 and digits[-1] == 0:
        digits.pop()
        exp += 1
    if len(digits) + abs(exp) > MAX_NUMBER_DIGITS:
        raise _invalid("TRACE_LIMIT", f"number needs more than {MAX_NUMBER_DIGITS} digits")
    text = "".join(map(str, digits))
    point = len(text) + exp
    if exp >= 0:
        out = text + "0" * exp
    elif point > 0:
        out = f"{text[:point]}.{text[point:]}"
    else:
        out = "0." + "0" * -point + text
    return ("-" if sign else "") + out


def _value(v: TraceValue | None):
    if v is None:
        return None
    if v.text is not None:
        return {"text": v.text}
    return {"number": canonical_decimal(v.number), "unit": v.unit, "dimension": list(v.dimension)}


def _named(pairs) -> list:
    return [{"name": n, "value": _value(v)} for n, v in pairs]


def trace_to_dict(trace: ExecutionTrace, *, metadata: bool = True) -> dict:
    if not isinstance(trace, ExecutionTrace):
        raise _invalid("INVALID_TRACE", f"expected ExecutionTrace, got {type(trace).__name__}")
    events = []
    for e in trace.events:
        c = e.check
        events.append({
            "id": e.event_id, "kind": e.kind.value, "title": e.title, "refs": list(e.refs),
            "formula": e.formula, "why": e.why, "values": _named(e.values), "result": _value(e.result),
            "check": None if c is None else {"what": c.what, "actual": _value(c.actual),
                                             "expected": _value(c.expected), "tolerance": _value(c.tolerance),
                                             "status": c.status.value, "detail": c.detail},
            "error": None if e.error is None else {"code": e.error.code, "reason": e.error.reason,
                                                   "message": e.error.message},
        })
    out = {
        "schema": SCHEMA, "version": VERSION, "operation": trace.operation,
        "inputs": _named(trace.inputs), "events": events, "result": _value(trace.result),
        "outcome": trace.outcome.value,
        "verification": {"status": trace.verification.status.value, "checks": trace.verification.checks,
                         "failed": trace.verification.failed},
    }
    if metadata:
        out["metadata"] = dict(trace.metadata)
    return out


def _dumps(data: dict) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def trace_to_json(trace: ExecutionTrace) -> str:
    """Canonical ``execution-trace/1`` text (metadata included)."""
    text = _dumps(trace_to_dict(trace))
    if len(text) > MAX_JSON_BYTES:
        raise _ser("TRACE_LIMIT", f"document exceeds {MAX_JSON_BYTES} bytes")
    return text


def semantic_json(trace: ExecutionTrace) -> str:
    """Canonical text of the digested content (everything except metadata)."""
    return _dumps(trace_to_dict(trace, metadata=False))


def trace_digest(trace: ExecutionTrace) -> str:
    return hashlib.sha256(semantic_json(trace).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- decoding

def _obj(value, keys, what) -> dict:
    if not isinstance(value, dict):
        raise _invalid("INVALID_TRACE", f"{what} must be an object, got {type(value).__name__}")
    missing = sorted(keys - value.keys())
    if missing:
        raise _invalid("INVALID_TRACE", f"{what} missing field(s) {missing}")
    extra = sorted(str(k)[:64] for k in value.keys() - keys)
    if extra:
        raise _invalid("INVALID_TRACE", f"{what} has unknown field(s) {extra}")
    return value


def _list(value, what, limit) -> list:
    if not isinstance(value, list):
        raise _invalid("INVALID_TRACE", f"{what} must be an array, got {type(value).__name__}")
    if len(value) > limit:
        raise _invalid("TRACE_LIMIT", f"{what} has more than {limit} items")
    return value


def _str(value, what) -> str:
    if not isinstance(value, str):
        raise _invalid("INVALID_TRACE", f"{what} must be a string, got {type(value).__name__}")
    return value


def _opt_str(value, what):
    return None if value is None else _str(value, what)


def _int(value, what) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _invalid("INVALID_TRACE", f"{what} must be an integer")
    return value


def _enum(enum, value, what):
    if not isinstance(value, str) or value not in enum.__members__:
        raise _invalid("INVALID_TRACE", f"{what} {str(value)[:32]!r} is not one of {list(enum.__members__)}")
    return enum[value]


def _decode_value(raw, what):
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise _invalid("INVALID_VALUE", f"{what} must be an object")
    if raw.keys() == _TEXT:
        return TraceValue(text=_str(raw["text"], f"{what}.text"))
    _obj(raw, _NUMBER, what)
    text = _str(raw["number"], f"{what}.number")
    if len(text) > MAX_NUMBER_DIGITS + 2 or not _NUMBER_RE.match(text) or text == "-0":
        raise _invalid("INVALID_VALUE", f"{what}.number {text[:40]!r} is not a canonical decimal")
    dimension = _list(raw["dimension"], f"{what}.dimension", 7)
    return TraceValue(number=Decimal(text), unit=_str(raw["unit"], f"{what}.unit"),
                      dimension=tuple(_int(e, f"{what}.dimension") for e in dimension))


def _decode_named(raw, what, limit):
    out = []
    for k, item in enumerate(_list(raw, what, limit)):
        item = _obj(item, _NAMED, f"{what}[{k}]")
        value = _decode_value(item["value"], f"{what}[{k}].value")
        if value is None:
            raise _invalid("INVALID_VALUE", f"{what}[{k}].value must not be null")
        out.append((_str(item["name"], f"{what}[{k}].name"), value))
    return tuple(out)


def _decode_event(raw, k) -> TraceEvent:
    where = f"events[{k}]"
    e = _obj(raw, _EVENT, where)
    check = None
    if e["check"] is not None:
        c = _obj(e["check"], _CHECK, f"{where}.check")
        actual = _decode_value(c["actual"], f"{where}.check.actual")
        expected = _decode_value(c["expected"], f"{where}.check.expected")
        if actual is None or expected is None:
            raise _invalid("INVALID_VALUE", f"{where}.check actual/expected must not be null")
        check = TraceCheck(_str(c["what"], "check.what"), actual, expected,
                           _enum(CheckStatus, c["status"], "check.status"),
                           _decode_value(c["tolerance"], f"{where}.check.tolerance"),
                           _str(c["detail"], "check.detail"))
    error = None
    if e["error"] is not None:
        r = _obj(e["error"], _ERROR, f"{where}.error")
        error = TraceError(_str(r["code"], "error.code"), _str(r["reason"], "error.reason"),
                           _str(r["message"], "error.message"))
    refs = tuple(_str(x, f"{where}.refs") for x in _list(e["refs"], f"{where}.refs", 64))
    return TraceEvent(_str(e["id"], f"{where}.id"), _enum(EventKind, e["kind"], f"{where}.kind"),
                      _str(e["title"], f"{where}.title"), refs, _opt_str(e["formula"], "formula"),
                      _opt_str(e["why"], "why"), _decode_named(e["values"], f"{where}.values", 64),
                      _decode_value(e["result"], f"{where}.result"), check, error)


def trace_from_dict(data: object) -> ExecutionTrace:
    """Strictly validate an ``execution-trace/1`` structure and build the trace."""
    if not isinstance(data, dict):
        raise _invalid("INVALID_TRACE", f"document must be an object, got {type(data).__name__}")
    schema = data.get("schema")
    if not isinstance(schema, str) or schema != SCHEMA:
        raise _invalid("INVALID_SCHEMA", f"schema must be {SCHEMA!r}, got {repr(schema)[:64]}")
    version = data.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version != VERSION:
        raise VersionMismatchError(f"UNSUPPORTED_VERSION: {SCHEMA} version {repr(version)[:32]} "
                                   f"(supported: {VERSION}, format {FORMAT})")
    _obj(data, _TOP, "document")
    v = _obj(data["verification"], _VERIFICATION, "verification")
    metadata = data["metadata"]
    if not isinstance(metadata, dict):
        raise _invalid("INVALID_TRACE", "metadata must be an object")
    events = tuple(_decode_event(raw, k) for k, raw in enumerate(_list(data["events"], "events", MAX_EVENTS)))
    return ExecutionTrace(
        _str(data["operation"], "operation"),
        _decode_named(data["inputs"], "inputs", 256),
        events,
        _decode_value(data["result"], "result"),
        _enum(Outcome, data["outcome"], "outcome"),
        Verification(_enum(VerificationStatus, v["status"], "verification.status"),
                     _int(v["checks"], "verification.checks"), _int(v["failed"], "verification.failed")),
        tuple(sorted((str(k), _str(val, "metadata value")) for k, val in metadata.items())),
    )


def _reject_float(text: str):
    raise _ser("INVALID_JSON", f"number {text[:32]!r} is not allowed (numbers are canonical strings)")


def _reject_constant(text: str):
    raise _ser("INVALID_JSON", f"{text} is not allowed")


def _bounded_int(text: str) -> int:
    if len(text) > _MAX_INT_DIGITS:
        raise _ser("TRACE_LIMIT", f"integer with more than {_MAX_INT_DIGITS} digits")
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
                raise _ser("TRACE_LIMIT", f"nesting deeper than {MAX_DEPTH}")
        elif ch in "]}":
            depth -= 1
        if ch not in "]}":
            items += 1
            if items > MAX_ITEMS:
                raise _ser("TRACE_LIMIT", f"more than {MAX_ITEMS} JSON values")


def trace_from_json(text: object) -> ExecutionTrace:
    """Decode untrusted ``execution-trace/1`` JSON (``str`` or UTF-8 ``bytes``)."""
    if isinstance(text, (bytes, bytearray)):
        if len(text) > MAX_JSON_BYTES:
            raise _ser("TRACE_LIMIT", f"document exceeds {MAX_JSON_BYTES} bytes")
        try:
            text = bytes(text).decode("utf-8")
        except UnicodeDecodeError:
            raise _ser("INVALID_JSON", "document is not valid UTF-8") from None
    elif isinstance(text, str):
        if len(text) > MAX_JSON_BYTES or len(text.encode("utf-8", "surrogatepass")) > MAX_JSON_BYTES:
            raise _ser("TRACE_LIMIT", f"document exceeds {MAX_JSON_BYTES} bytes")
    else:
        raise _ser("INVALID_JSON", f"expected str or bytes, got {type(text).__name__}")
    _prescan(text)
    try:
        data = json.loads(text, object_pairs_hook=_unique_pairs, parse_float=_reject_float,
                          parse_int=_bounded_int, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise _ser("INVALID_JSON", f"{exc.msg} at position {exc.pos}") from None
    except RecursionError:
        raise _ser("TRACE_LIMIT", "nesting too deep") from None
    return trace_from_dict(data)
