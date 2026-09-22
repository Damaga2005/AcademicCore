"""Ingestion pipeline (Phase 2 application service):

source -> detect -> adapter -> read -> hash -> deduplicate -> store
  -> metadata/provenance -> extract -> index

- Idempotent: same bytes -> same resource/version (duplicate report, no new
  rows, no new blob, no artificial version).
- Same logical source, changed bytes -> NEW version; history preserved.
- Failures roll back canonical records (unit of work); the FTS index is
  derived and rebuilt, never load-bearing.
- No URLs (explicit-adapter boundary), no ZIP (deferred), traversal-safe,
  size-capped, no silent overwrites (CAS immutable + versioned rows).

No Qt. No FTS/SQLite imports here beyond the injected ports/repositories.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from academic_core.domain import resources as R
from academic_core.domain.entities import ResourceReference
from academic_core.domain.identity import make
from academic_core.errors import AcademicCoreError
from academic_core.resources.adapters import UnsupportedType, adapter_for, detect_kind


class SecurityError(AcademicCoreError):
    pass


@dataclass(frozen=True)
class IngestReport:
    stable_id: str
    version: int
    content_hash: str
    kind: str
    outcome: str  # imported|duplicate|new_version
    extraction_status: str
    warnings: tuple = ()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check_filename(filename: str) -> str:
    if "\x00" in filename:
        raise SecurityError("NUL byte in filename")
    p = Path(filename)
    if ".." in p.parts and not Path(filename).is_file():
        raise SecurityError(f"path traversal refused: {filename!r}")
    return p.name or filename


class IngestionService:
    def __init__(self, blobs, records, indexer, academic, planning=None,
                 max_bytes: int = 100 * 1024 * 1024):
        self.blobs = blobs
        self.records = records
        self.indexer = indexer
        self.academic = academic
        self.planning = planning
        self.max_bytes = max_bytes

    # -- public -------------------------------------------------------------
    def import_file(self, path: str | Path, subject_id: str | None = None,
                    resource_id: str | None = None) -> IngestReport:
        p = Path(path)
        if "\x00" in str(path):
            raise SecurityError("NUL byte in path")
        if not p.is_file():
            if ".." in p.parts:
                raise SecurityError(f"path traversal refused: {path!r}")
            raise FileNotFoundError(f"not a file: {path}")
        if p.stat().st_size > self.max_bytes:
            from academic_core.infrastructure.cas import TooLarge
            raise TooLarge(f"{path} exceeds {self.max_bytes} bytes")
        head = p.open("rb").read(8)
        kind = detect_kind(p.name, head)  # may raise UnsupportedType: no rows yet
        content_hash, size = self.blobs.put_file(p, self.max_bytes)
        return self._commit(kind=kind, filename=p.name, source=str(p),
                            origin="file", subject_id=subject_id,
                            resource_id=resource_id, content_hash=content_hash,
                            size=size)

    def import_bytes(self, data: bytes, filename: str, subject_id: str | None = None,
                     origin: str = "manual",
                     resource_id: str | None = None) -> IngestReport:
        if origin == "url":
            raise UnsupportedType("url ingest needs an explicit adapter (F2 boundary)")
        name = _check_filename(filename)
        if len(data) > self.max_bytes:
            from academic_core.infrastructure.cas import TooLarge
            raise TooLarge(f"{filename} exceeds {self.max_bytes} bytes")
        kind = detect_kind(name, data[:8])
        content_hash = self.blobs.put_bytes(data)
        return self._commit(kind=kind, filename=name, source=filename,
                            origin=origin, subject_id=subject_id,
                            resource_id=resource_id, content_hash=content_hash,
                            size=len(data))

    # -- pipeline core ---------------------------------------------------------
    def _commit(self, *, kind: str, filename: str, source: str, origin: str,
                subject_id: str | None, resource_id: str | None,
                content_hash: str, size: int) -> IngestReport:
        dupes = self.records.find_by_hash(content_hash)
        if dupes:
            sid, ver = dupes[0]
            self._ensure_link(sid, subject_id, filename)
            res = self.records.get(sid)
            cur = res.current()
            return IngestReport(sid, ver, content_hash, res.kind, "duplicate",
                                cur.provenance.extraction_status,
                                ("identical content: deduplicated",))

        adapter = adapter_for(kind, filename)
        raw = self.blobs.get_bytes(content_hash)
        try:
            extracted = adapter.extract(raw, filename)
        except Exception as e:  # adapter bug must not corrupt canonical state
            from academic_core.domain.ports import ExtractedContent
            extracted = ExtractedContent(status="failed",
                                         warnings=(f"extractor crashed: {e}",))

        if resource_id is not None:
            sid = resource_id
            prev = self.records.get(sid)
            if prev is None:
                raise ValueError(f"unknown resource_id: {sid}")
            version_n = prev.current_version + 1
            parent = prev.current_version
            outcome = "new_version"
        elif origin == "file":
            known = self.records.find_latest_by_source(source)
            if known is not None:
                sid = known
                prev = self.records.get(sid)
                version_n = prev.current_version + 1
                parent = prev.current_version
                outcome = "new_version"
            else:
                sid, version_n, parent, outcome = self._fresh(
                    subject_id, "imported")
        else:
            sid, version_n, parent, outcome = self._fresh(subject_id, "imported")

        prov = R.ResourceProvenance(
            origin=origin, source=source, original_filename=filename,
            content_hash=content_hash, imported_at=_utcnow(),
            adapter=adapter.name, adapter_version=adapter.version,
            extraction_status=extracted.status, parent_version=parent)
        ver = R.ResourceVersion(sid, version_n, content_hash, size, prov)
        title = (extracted.metadata or {}).get("title", "") or filename
        with self.records.unit_of_work() as cx:
            if outcome == "imported":
                self.records.save_new(R.Resource(sid, kind, title, version_n, [ver]), cx)
            else:
                self.records.append_version(ver, cx)
        self._ensure_link(sid, subject_id, filename)
        try:
            self.indexer.index(sid, kind, title, extracted.text)
        except Exception as e:  # derived index: report, never roll back canonical
            return IngestReport(sid, version_n, content_hash, kind, outcome,
                                extracted.status,
                                tuple(extracted.warnings) + (f"index deferred: {e}",))
        return IngestReport(sid, version_n, content_hash, kind, outcome,
                            extracted.status, tuple(extracted.warnings))

    def _fresh(self, subject_id: str | None, outcome: str):
        scope = (subject_id.split(":", 1)[1] if subject_id and ":" in subject_id
                 else "general")
        counters = self.academic.load_counters()
        n = counters.get("resource", 0) + 1
        sid = make("resource", scope, f"{n:05d}")
        counters["resource"] = n
        self.academic.save_counters(counters)
        return sid, 1, 0, outcome

    def _ensure_link(self, sid: str, subject_id: str | None, filename: str) -> None:
        if subject_id is None or self.planning is None:
            return
        self.planning.add_ref(ResourceReference(sid, subject_id, "material", filename))

    # -- maintenance --------------------------------------------------------------
    def reindex(self, progress=None) -> int:
        """Drop + rebuild the derived FTS index from canonical records/blobs."""
        from academic_core.resources.adapters import adapter_for as _af
        bodies: dict[str, tuple[str, str, str]] = {}
        for sid in self.records.all_ids():
            res = self.records.get(sid)
            cur = res.current()
            try:
                raw = self.blobs.get_bytes(cur.content_hash)
                ext = _af(res.kind, cur.provenance.original_filename).extract(
                    raw, cur.provenance.original_filename)
                bodies[sid] = (res.kind, res.title, ext.text)
            except Exception:
                bodies[sid] = (res.kind, res.title, "")
            if progress:
                progress(len(bodies))
        return self.indexer.rebuild(self.records, bodies)
