"""ResourceProvider abstraction — OneDrive is a provider, not a core dependency."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SyncResult:
    ingested: int = 0
    skipped: int = 0
    errors: list[str] | None = None


class ResourceProvider(ABC):
    name: str = ""

    @abstractmethod
    def sync(self, dest: Path) -> SyncResult: ...


class LocalFilesystemProvider(ResourceProvider):
    name = "local"

    def __init__(self, root: Path):
        self.root = root

    def sync(self, dest: Path) -> SyncResult:
        files = [p for p in self.root.rglob("*") if p.is_file()]
        return SyncResult(ingested=len(files))


class OneDriveProvider(ResourceProvider):
    name = "onedrive"

    def __init__(self, folder: str = "", enabled: bool = False):
        self.folder = folder
        self.enabled = enabled

    def sync(self, dest: Path) -> SyncResult:
        if not self.enabled:
            raise RuntimeError("OneDrive provider not enabled (see ADR-0009)")
        raise NotImplementedError("Phase 11 implements safe read-only ingest first")


class GitHubProvider(ResourceProvider):
    name = "github"

    def sync(self, dest: Path) -> SyncResult:
        raise NotImplementedError
