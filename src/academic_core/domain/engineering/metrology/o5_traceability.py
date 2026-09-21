"""F8-O O5 traceability chain (NEW data model, no hardware).

Calibration DAG as pure data::

    inputs -> derived quantities -> sensitivities -> uncertainties
             -> combined uncertainty -> coverage -> expanded uncertainty
             -> report

Every node is deterministically addressable; the chain digest is
``sha256(tag || 0x00 || canonical_json)`` with canonical JSON
(sorted keys, ``Decimal`` via ``str()`` — never ``normalize()`` —,
``inf`` as ``"inf"``). Digests never depend on timestamp, UUID, object
address, accidental order or environment.

Reuse: NEW (grep-proven: no traceability implementation exists). The
digest construction mirrors the F8-N lab convention (tag-separated
SHA-256 over canonical JSON).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping, Sequence

from academic_core.domain.engineering.metrology.errors import (
    MetrologyError,
    MetrologyStatus,
)

TRACE_TAG = "f8o-trace/1"


def _canonical(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, float):
        if value == float("inf"):
            return "inf"
        if value == float("-inf"):
            return "-inf"
        if value != value:
            raise MetrologyError(MetrologyStatus.INVALID, "NaN has no canonical form")
        return repr(value)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, str)) or value is None:
        return value
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _canonical(value[key]) for key in sorted(value.keys(), key=str)}
    raise MetrologyError(
        MetrologyStatus.INVALID, f"uncanonizable type {type(value).__name__}"
    )


def canonical_json(payload: Mapping[str, object]) -> str:
    """Canonical JSON: sorted keys, compact separators, Decimal via ``str()``."""
    if not isinstance(payload, dict):
        raise MetrologyError(MetrologyStatus.INVALID, "canonical payload must be a dict")
    try:
        return json.dumps(_canonical(payload), sort_keys=True, separators=(",", ":"))
    except MetrologyError:
        raise
    except Exception as exc:
        raise MetrologyError(MetrologyStatus.INVALID, f"uncanonicalizable payload: {exc}") from exc


def chain_digest(payload: Mapping[str, object], tag: str = TRACE_TAG) -> str:
    """``sha256(tag || 0x00 || canonical_json)`` hex digest."""
    if not isinstance(tag, str) or not tag:
        raise MetrologyError(MetrologyStatus.INVALID, "digest tag must be a non-empty string")
    body = canonical_json(payload).encode("utf-8")
    return hashlib.sha256(tag.encode("utf-8") + b"\x00" + body).hexdigest()


def _clean_text(value: str, label: str) -> str:
    cleaned = value.strip() if isinstance(value, str) else ""
    if not cleaned:
        raise MetrologyError(MetrologyStatus.INVALID, f"trace node {label} cannot be empty")
    return cleaned


@dataclass(frozen=True)
class TraceNode:
    """One link of the calibration chain (immutable value object).

    Validation-only ``__post_init__`` (raises, never mutates — no
    ``setattr`` anywhere in this package). Normalise inputs through
    :meth:`create` before constructing.
    """

    node_id: str
    kind: str
    value: Decimal
    uncertainty: Decimal
    unit: str
    parents: tuple[str, ...] = ()
    standard_id: str = ""
    procedure: str = ""
    metadata: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.node_id.strip():
            raise MetrologyError(MetrologyStatus.INVALID, "trace node id cannot be empty")
        if not self.kind.strip():
            raise MetrologyError(MetrologyStatus.INVALID, "trace node kind cannot be empty")
        for label, item in (("value", self.value), ("uncertainty", self.uncertainty)):
            if isinstance(item, bool) or not isinstance(item, Decimal) or not item.is_finite():
                raise MetrologyError(
                    MetrologyStatus.INVALID, f"trace node {label} must be finite Decimal"
                )
        if self.uncertainty < 0:
            raise MetrologyError(MetrologyStatus.INVALID, "trace node uncertainty >= 0 required")
        for parent in self.parents:
            if not parent.strip():
                raise MetrologyError(MetrologyStatus.INVALID, "trace parent ids cannot be empty")
        if len(set(self.parents)) != len(self.parents):
            raise MetrologyError(MetrologyStatus.INVALID, "trace parent ids must be unique")

    @staticmethod
    def create(
        node_id: str,
        kind: str,
        value: Decimal | int | str,
        uncertainty: Decimal | int | str,
        unit: str = "",
        parents: Sequence[str] = (),
        standard_id: str = "",
        procedure: str = "",
        metadata: Mapping[str, str] | None = None,
    ) -> "TraceNode":
        """Normalising factory (all coercion happens before construction)."""
        try:
            value_dec = Decimal(str(value)) if not isinstance(value, Decimal) else value
            unc_dec = Decimal(str(uncertainty)) if not isinstance(uncertainty, Decimal) else uncertainty
        except Exception as exc:
            raise MetrologyError(MetrologyStatus.INVALID, "trace value/uncertainty must be numeric") from exc
        meta = tuple(sorted((dict(metadata) if metadata else {}).items(), key=lambda kv: kv[0]))
        return TraceNode(
            node_id=_clean_text(node_id, "id"),
            kind=_clean_text(kind, "kind"),
            value=value_dec,
            uncertainty=unc_dec,
            unit=unit.strip() if isinstance(unit, str) else "",
            parents=tuple(parents),
            standard_id=standard_id.strip() if isinstance(standard_id, str) else "",
            procedure=procedure.strip() if isinstance(procedure, str) else "",
            metadata=meta,
        )

    def to_dict(self) -> dict:
        """Canonical-ordered node document."""
        return {
            "node_id": self.node_id,
            "kind": self.kind,
            "value": str(self.value),
            "uncertainty": str(self.uncertainty),
            "unit": self.unit,
            "parents": list(self.parents),
            "standard_id": self.standard_id,
            "procedure": self.procedure,
            "metadata": {key: val for key, val in self.metadata},
        }


@dataclass(frozen=True)
class TraceChain:
    """Closed DAG of :class:`TraceNode` with a stable digest."""

    nodes: tuple[TraceNode, ...]

    def __post_init__(self) -> None:
        ids = [node.node_id for node in self.nodes]
        if len(set(ids)) != len(ids):
            raise MetrologyError(MetrologyStatus.INVALID, "trace node ids must be unique")
        known = set(ids)
        for node in self.nodes:
            for parent in node.parents:
                if parent not in known:
                    raise MetrologyError(
                        MetrologyStatus.INCONSISTENT,
                        f"trace node {node.node_id!r} links unknown parent {parent!r}",
                    )
            if node.node_id in node.parents:
                raise MetrologyError(MetrologyStatus.INVALID, "trace self-link rejected")
        if _has_cycle({node.node_id: tuple(node.parents) for node in self.nodes}):
            raise MetrologyError(MetrologyStatus.INVALID, "trace cycle rejected")

    def to_dict(self) -> dict:
        """Nodes sorted by id (canonical order)."""
        ordered = sorted(self.nodes, key=lambda node: node.node_id)
        return {"tag": TRACE_TAG, "nodes": [node.to_dict() for node in ordered]}

    def digest(self) -> str:
        """Stable chain digest (order-invariant by construction)."""
        return chain_digest(self.to_dict())

    def verify(self) -> str:
        """Recompute and confirm structural closure: ``OK`` or raise."""
        self.__post_init__()
        digest_first = self.digest()
        if digest_first != self.digest():
            raise MetrologyError(MetrologyStatus.INCONSISTENT, "trace digest unstable")
        return "OK"


def _has_cycle(edges: dict[str, tuple[str, ...]]) -> bool:
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(node: str) -> bool:
        if node in done:
            return False
        if node in visiting:
            return True
        visiting.add(node)
        for parent in edges.get(node, ()):
            if visit(parent):
                return True
        visiting.discard(node)
        done.add(node)
        return False

    for root in edges:
        if visit(root):
            return True
    return False
