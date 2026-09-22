"""F8-P5 canonical documents f8p5-satcom/1 + digests + replay (NEW).

Deterministic, closed, size-guarded envelope over link budgets. The hash
construction is REUSEd — `canonical_json`/`chain_digest` from
`metrology.o5_traceability`; this module only pre-converts satcom values
(Decimal via `str()` — never `normalize()` — tuples/lists structurally)
into plain payloads, so no second canonicalizer or digest engine exists
here. Replay states reuse the F8-N/O/P1-P4 vocabulary verbatim.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Mapping

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.metrology.o5_traceability import (
    canonical_json,
    chain_digest,
)

SCHEMA = "f8p5-satcom/1"
DOCUMENT_TAG = "f8p5-satcom/1"
ENGINE_VERSION = "f8p5-satcom/1"
MAX_SERIALIZED_BYTES = 64 * 1024 * 1024

EQUIVALENT = "EQUIVALENT"
RESULT_DIFFERS = "RESULT_DIFFERS"
VERSION_MISMATCH = "VERSION_MISMATCH"
SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
INVALID_SERIALIZATION = "INVALID_SERIALIZATION"
VALID = EQUIVALENT
RESULT_DIFFERENT = RESULT_DIFFERS


def _plain(value: object) -> object:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ControlError(ControlStatus.INVALID, "NaN/Infinity have no document form")
        return str(value)
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, bool) or isinstance(value, (int, str)) or value is None:
        return value
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain(value[key]) for key in sorted(value.keys(), key=str)}
    raise ControlError(
        ControlStatus.INVALID, "undocumentable type " + type(value).__name__)


@dataclass(frozen=True)
class SatcomDocument:
    """Closed deterministic satcom document (validation-only post-init)."""

    kind: str
    payload: tuple
    provenance: tuple = ()
    engine: str = ENGINE_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or not self.kind.strip():
            raise ControlError(ControlStatus.INVALID, "document kind cannot be empty")
        if not isinstance(self.payload, tuple):
            raise ControlError(ControlStatus.INVALID, "document payload must be a tuple")
        if not isinstance(self.provenance, tuple):
            raise ControlError(ControlStatus.INVALID, "document provenance must be a tuple")

    @staticmethod
    def create(kind: str, payload: Mapping[str, object],
               provenance: Mapping[str, str] | None = None) -> "SatcomDocument":
        if not isinstance(kind, str) or not kind.strip():
            raise ControlError(ControlStatus.INVALID, "document kind cannot be empty")
        if not isinstance(payload, dict):
            raise ControlError(ControlStatus.INVALID, "document payload must be a dict")
        plain = _plain(payload)
        items = tuple(sorted(((str(k), v) for k, v in plain.items()), key=lambda kv: kv[0]))
        prov = tuple(sorted(((str(k), str(v)) for k, v in dict(provenance or {}).items()),
                            key=lambda kv: kv[0]))
        return SatcomDocument(kind=kind.strip(), payload=items, provenance=prov)

    def _body(self) -> dict:
        return {
            "schema": SCHEMA,
            "kind": self.kind,
            "payload": {key: val for key, val in self.payload},
            "provenance": {key: val for key, val in self.provenance},
            "engine": self.engine,
        }

    def to_dict(self) -> dict:
        doc = self._body()
        doc["digest"] = self.digest()
        return doc

    def digest(self) -> str:
        return chain_digest(self._body(), tag=DOCUMENT_TAG)


def dumps(document: SatcomDocument) -> str:
    if not isinstance(document, SatcomDocument):
        raise ControlError(ControlStatus.INVALID, "dumps needs a SatcomDocument")
    text = canonical_json(document.to_dict())
    if len(text.encode("utf-8")) > MAX_SERIALIZED_BYTES:
        raise ControlError(ControlStatus.INVALID, "serialised document exceeds 64 MiB")
    return text


def loads(text: str) -> SatcomDocument:
    if not isinstance(text, str) or not text:
        raise ControlError(ControlStatus.INVALID, "loads needs a non-empty string")
    if len(text.encode("utf-8")) > MAX_SERIALIZED_BYTES:
        raise ControlError(ControlStatus.INVALID, "serialised document exceeds 64 MiB")
    try:
        doc = json.loads(text)
    except Exception as exc:
        raise ControlError(ControlStatus.INVALID, "bad JSON") from exc
    if not isinstance(doc, dict):
        raise ControlError(ControlStatus.INVALID, "document must be an object")
    known = {"schema", "kind", "payload", "provenance", "engine", "digest"}
    unknown = sorted(set(doc.keys()) - known)
    if unknown:
        raise ControlError(ControlStatus.INVALID, "unknown document fields: " + ", ".join(unknown))
    if doc.get("schema") != SCHEMA:
        raise ControlError(ControlStatus.INVALID, "unsupported schema")
    try:
        stated = str(doc["digest"])
        payload = doc.get("payload", {})
        provenance = doc.get("provenance", {})
        if not isinstance(payload, dict) or not isinstance(provenance, dict):
            raise ControlError(ControlStatus.INVALID, "bad document sections")
        rebuilt = SatcomDocument.create(str(doc["kind"]), payload,
                                        {str(k): str(v) for k, v in provenance.items()})
        if rebuilt.engine != str(doc.get("engine", ENGINE_VERSION)):
            raise ControlError(ControlStatus.INVALID, "engine mismatch")
    except ControlError:
        raise
    except Exception as exc:
        raise ControlError(ControlStatus.INVALID, "bad document types") from exc
    if rebuilt.digest() != stated:
        raise ControlError(ControlStatus.INCONSISTENT, "document digest mismatch (tampered?)")
    return rebuilt


def compare(first: object, second: object) -> str:
    try:
        raw_a = json.loads(first) if isinstance(first, str) else None
        raw_b = json.loads(second) if isinstance(second, str) else None
    except Exception:
        return INVALID_SERIALIZATION
    if raw_a is not None or raw_b is not None:
        try:
            schema_a = raw_a["schema"] if raw_a is not None else first.to_dict()["schema"]
            schema_b = raw_b["schema"] if raw_b is not None else second.to_dict()["schema"]
        except Exception:
            return INVALID_SERIALIZATION
        if schema_a != schema_b:
            family_a = str(schema_a).split("/")[0]
            family_b = str(schema_b).split("/")[0]
            if family_a != family_b:
                return SCHEMA_MISMATCH
            return VERSION_MISMATCH
    try:
        doc_a = loads(first) if isinstance(first, str) else first
        doc_b = loads(second) if isinstance(second, str) else second
    except ControlError:
        return INVALID_SERIALIZATION
    if not isinstance(doc_a, SatcomDocument) or not isinstance(doc_b, SatcomDocument):
        return INVALID_SERIALIZATION
    if doc_a.digest() == doc_b.digest():
        return EQUIVALENT
    return RESULT_DIFFERS


def replay(text: str) -> str:
    """Reload a stored document: EQUIVALENT when intact and current."""
    try:
        doc = loads(text)
    except ControlError as exc:
        if exc.status == ControlStatus.INCONSISTENT:
            return RESULT_DIFFERS
        return INVALID_SERIALIZATION
    if doc.engine != ENGINE_VERSION:
        return VERSION_MISMATCH
    if doc.digest() == doc.digest():
        return EQUIVALENT
    return RESULT_DIFFERS
