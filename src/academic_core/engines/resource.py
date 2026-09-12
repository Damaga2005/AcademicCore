"""Resource Engine pipeline (Phase 0 interfaces).

SOURCE -> INGEST -> EXTRACT -> NORMALIZE -> STRUCTURE -> IDENTIFY -> LINK -> INDEX -> ACADEMIC RESOURCE
Each stage has a stable interface; Phase 1+ provides format adapters.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

SUPPORTED_KINDS = ("pdf", "html", "md", "latex", "docx", "pptx", "image",
                   "csv", "json", "zip", "dataset")


@dataclass
class IngestResult:
    cas_hash: str
    kind: str
    stable_id: str
    provenance: dict


class ResourceAdapter(ABC):
    kind: str = ""

    @abstractmethod
    def extract(self, raw: bytes) -> str:
        """Raw bytes -> normalized intermediate text/AST payload."""


class ResourceEngine:
    def __init__(self, store):
        self.store = store
        self.adapters: dict[str, ResourceAdapter] = {}

    def register(self, adapter: ResourceAdapter) -> None:
        self.adapters[adapter.kind] = adapter

    def ingest(self, data: bytes, kind: str, stable_id: str, subject: str,
               provenance: dict | None = None) -> IngestResult:
        if kind not in SUPPORTED_KINDS:
            raise ValueError(f"unsupported kind: {kind}")
        h = self.store.put_bytes(data)
        self.store.put_entity(stable_id, "resource", subject, "{}", h)
        return IngestResult(cas_hash=h, kind=kind, stable_id=stable_id,
                            provenance=provenance or {})
