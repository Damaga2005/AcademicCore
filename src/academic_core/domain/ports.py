"""Ports (dependency inversion): domain defines WHAT, infrastructure provides HOW.

These ABCs use only abc/typing — no filesystem, SQLite, FTS5, Qt, network.
Implementations live in infrastructure/ (BlobStore, records, indexer) and
resources/ (adapters). Tests pin: domain imports none of those backends.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractedContent:
    """Extractor output. Never mutates the canonical blob."""
    text: str = ""  # indexable text (possibly truncated, see truncation flag)
    truncated: bool = False
    is_binary: bool = False
    metadata: dict | None = None
    warnings: tuple = ()
    status: str = "ok"  # ok|deferred|failed


class BlobStore(ABC):
    """Content-addressed bytes. Implementations stream; callers never assume
    the whole blob fits comfortably in RAM twice."""

    @abstractmethod
    def put_stream(self, chunks) -> str:
        """Consume an iterable of bytes, store once, return sha256 hex."""

    @abstractmethod
    def put_bytes(self, data: bytes) -> str: ...

    @abstractmethod
    def get_bytes(self, content_hash: str) -> bytes:
        """Return bytes; raise on missing/corrupt (integrity-checked)."""

    @abstractmethod
    def exists(self, content_hash: str) -> bool: ...

    @abstractmethod
    def delete(self, content_hash: str) -> bool:
        """Remove blob; return False when absent. No silent overwrite exists
        because writes are content-addressed and immutable."""


class ResourceExtractor(ABC):
    kind: str = ""  # resource kind this extractor handles
    name: str = ""  # adapter identity recorded in provenance
    version: str = "1"

    @abstractmethod
    def supports(self, kind: str, filename: str) -> bool: ...

    @abstractmethod
    def extract(self, data: bytes, filename: str) -> ExtractedContent: ...


class ResourceIndexer(ABC):
    """Derived index over extracted text. Droppable and rebuildable; never
    the source of truth."""

    @abstractmethod
    def index(self, stable_id: str, kind: str, title: str, text: str) -> None: ...

    @abstractmethod
    def remove(self, stable_id: str) -> None: ...

    @abstractmethod
    def search(self, query: str, kind: str = "", limit: int = 20) -> list: ...

    @abstractmethod
    def rebuild(self, records) -> int:
        """Full rebuild from canonical records; returns entries indexed."""


class ResourceRecords(ABC):
    """Canonical metadata/provenance/version store (SQLite in F2)."""

    @abstractmethod
    def unit_of_work(self):
        """Context manager: commit on success, rollback on failure."""
