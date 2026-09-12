"""Resource domain (Phase 2): content managed by the Resource Engine.

Separation (ADR-0013):
- ResourceReference (entities.py, F1): ACADEMIC link subject->resource.
  Unchanged; it points at Resource.stable_id.
- Resource: managed content with a STABLE id (`resource:<scope>:r:NNNNN`).
  Scope defaults to the first linked subject, else "general". The id never
  changes across reindex, moves, or reimports.
- ResourceVersion: one row per distinct content_hash. Same bytes reimported
  -> same version (idempotent). Changed bytes -> NEW version; history kept,
  never silently destroyed.
- ResourceProvenance: how/when/where/by-which-adapter. Path is metadata,
  never identity.

No filesystem. No SQLite. No FTS5. No Qt.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from academic_core.domain.entities import DomainError
from academic_core.domain.identity import validate

RESOURCE_KINDS = ("file", "text", "markdown", "html", "pdf")
RESOURCE_ORIGINS = ("file", "url", "generated", "manual", "migration")


@dataclass
class ResourceProvenance:
    origin: str  # one of RESOURCE_ORIGINS
    source: str = ""  # original path/URI/label (metadata only, may go stale)
    original_filename: str = ""
    content_hash: str = ""
    imported_at: str = ""  # ISO timestamp, set by the pipeline
    adapter: str = ""
    adapter_version: str = ""
    extraction_status: str = "ok"  # ok|deferred|failed
    parent_version: int = 0  # 0 = first version
    note: str = ""

    def __post_init__(self) -> None:
        if self.origin not in RESOURCE_ORIGINS:
            raise DomainError(f"origin must be one of {RESOURCE_ORIGINS}")
        if self.content_hash and (
                len(self.content_hash) != 64
                or any(c not in "0123456789abcdef" for c in self.content_hash)):
            raise DomainError("content_hash must be sha256 hex")


@dataclass
class ResourceVersion:
    stable_id: str  # resource id this version belongs to
    version: int  # 1-based, append-only
    content_hash: str
    size: int
    provenance: ResourceProvenance

    def __post_init__(self) -> None:
        if validate(self.stable_id) != "resource":
            raise DomainError(f"bad id: {self.stable_id}")
        if self.version < 1:
            raise DomainError("version is 1-based")
        if self.size < 0:
            raise DomainError("size must be >= 0")


@dataclass
class Resource:
    stable_id: str
    kind: str  # one of RESOURCE_KINDS
    title: str = ""
    current_version: int = 1
    versions: list[ResourceVersion] = field(default_factory=list)

    def __post_init__(self) -> None:
        if validate(self.stable_id) != "resource":
            raise DomainError(f"bad id: {self.stable_id}")
        if self.kind not in RESOURCE_KINDS:
            raise DomainError(f"kind must be one of {RESOURCE_KINDS}")

    def current(self) -> ResourceVersion | None:
        for v in self.versions:
            if v.version == self.current_version:
                return v
        return None
