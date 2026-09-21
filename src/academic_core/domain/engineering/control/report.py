"""F8-P1 canonical documents f8p1-control/1 + digests + replay (NEW).

Deterministic, closed, size-guarded envelope over control results.
Digest construction mirrors the F8-N/F8-O convention:
    sha256(tag || 0x00 || canonical_json)
with Decimal entries via str() (never normalize()). Replay states use
the gate vocabulary: EQUIVALENT / RESULT_DIFFERS / VERSION_MISMATCH /
SCHEMA_MISMATCH / INVALID_SERIALIZATION.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction
from typing import Mapping

from academic_core.domain.engineering.control.errors import (
    ControlError,
    ControlStatus,
)
from academic_core.domain.engineering.math import DecimalComplex

SCHEMA = "f8p1-control/1"
DOCUMENT_TAG = "f8p1-control/1"
ENGINE_VERSION = "f8p1-control/1"
MAX_SERIALIZED_BYTES = 64 * 1024 * 1024

EQUIVALENT = "EQUIVALENT"
RESULT_DIFFERS = "RESULT_DIFFERS"
VERSION_MISMATCH = "VERSION_MISMATCH"
SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
INVALID_SERIALIZATION = "INVALID_SERIALIZATION"
VALID = EQUIVALENT
RESULT_DIFFERENT = RESULT_DIFFERS


def _canonical(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, DecimalComplex):
        return {"re": str(value.re), "im": str(value.im)}
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, str)) or value is None:
        return value
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _canonical(value[key]) for key in sorted(value.keys(), key=str)}
    raise ControlError(ControlStatus.INVALID, "uncanonizable type " + type(value).__name__)


def canonical_json(payload: Mapping[str, object]) -> str:
    if not isinstance(payload, dict):
        raise ControlError(ControlStatus.INVALID, "canonical payload must be a dict")
    try:
        return json.dumps(_canonical(payload), sort_keys=True, separators=(",", ":"))
    except ControlError:
        raise
    except Exception as exc:
        raise ControlError(ControlStatus.INVALID, "uncanonicalizable payload") from exc


def document_digest(payload: Mapping[str, object], tag: str = DOCUMENT_TAG) -> str:
    if not isinstance(tag, str) or not tag:
        raise ControlError(ControlStatus.INVALID, "digest tag must be a non-empty string")
    body = canonical_json(payload).encode("utf-8")
    return hashlib.sha256(tag.encode("utf-8") + b"\x00" + body).hexdigest()


@dataclass(frozen=True)
class ControlDocument:
    """Closed deterministic control document (validation-only post-init)."""

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
               provenance: Mapping[str, str] | None = None) -> "ControlDocument":
        if not isinstance(kind, str) or not kind.strip():
            raise ControlError(ControlStatus.INVALID, "document kind cannot be empty")
        if not isinstance(payload, dict):
            raise ControlError(ControlStatus.INVALID, "document payload must be a dict")
        # Canonicalise eagerly so uncanonizable ingress fails fast.
        canonical_json(payload)
        items = tuple(sorted(((str(k), v) for k, v in payload.items()), key=lambda kv: kv[0]))
        prov = tuple(sorted(((str(k), str(v)) for k, v in dict(provenance or {}).items()),
                            key=lambda kv: kv[0]))
        return ControlDocument(kind=kind.strip(), payload=items, provenance=prov)

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
        return document_digest(self._body())


def dumps(document: ControlDocument) -> str:
    if not isinstance(document, ControlDocument):
        raise ControlError(ControlStatus.INVALID, "dumps needs a ControlDocument")
    text = canonical_json(document.to_dict())
    if len(text.encode("utf-8")) > MAX_SERIALIZED_BYTES:
        raise ControlError(ControlStatus.INVALID, "serialised document exceeds 64 MiB")
    return text


def loads(text: str) -> ControlDocument:
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
        rebuilt = ControlDocument.create(str(doc["kind"]), payload,
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
    if not isinstance(doc_a, ControlDocument) or not isinstance(doc_b, ControlDocument):
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
