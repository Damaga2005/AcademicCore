"""BackupService (Phase 1 boundary, hardened in F4.1).

- ``backup``: consistent SQLite snapshot (online-backup API, WAL-safe) +
  manifest with SHA-256. CAS bytes and derived indexes are regenerable and
  excluded by design; the manifest records the hash so restores verify.
- ``export_zip`` / ``verify_zip`` (F4.1, Gestion `routes/backup.py` parity):
  a portable archive (snapshot + manifest [+ CAS blobs]) and a validator
  that checks EVERY member before anything is extracted: Zip Slip
  (absolute/``..``/drive/backslash paths, symlinks), Zip Bomb (member count,
  per-member and total uncompressed size, compression ratio), manifest
  hashes and SQLite integrity. Nothing in an archive is ever executed.
Secrets are never included (see security.py).
"""

from __future__ import annotations

import hashlib
import json
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from academic_core.errors import AcademicCoreError
from academic_core.infrastructure.database import online_backup, sqlite_integrity

MAX_MEMBERS = 200_000
MAX_MEMBER_BYTES = 2 * 1024 ** 3
MAX_TOTAL_BYTES = 5 * 1024 ** 3
MAX_RATIO = 100
ARCHIVE_SCHEMA = "academiccore-backup/1"


class ArchiveRejected(AcademicCoreError):
    code = "AC-SEC-003"
    category = "security"


@dataclass(frozen=True)
class BackupReport:
    path: str
    sha256: str
    created: str


@dataclass(frozen=True)
class ArchiveReport:
    path: str
    sha256: str
    members: int
    db_sha256: str
    blobs: int


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_member(name: str) -> bool:
    if not name or "\x00" in name or "\\" in name:
        return False
    p = PurePosixPath(name)
    if p.is_absolute() or (len(name) > 1 and name[1] == ":"):
        return False
    return all(part not in ("..", "") for part in p.parts)


class BackupService:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def backup(self, dest_dir: str | Path) -> BackupReport:
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        target = dest / f"academic-{stamp}.db"
        online_backup(self.db_path, target)
        digest = _sha256(target)
        (dest / f"academic-{stamp}.manifest.json").write_text(
            json.dumps({"db": target.name, "sha256": digest, "created": stamp,
                        "note": "CAS/indexes regenerable; secrets excluded"},
                       indent=2), encoding="utf-8")
        return BackupReport(str(target), digest, stamp)

    # -- F4.1 portable archive ---------------------------------------------
    def export_zip(self, dest: str | Path, cas_root: str | Path | None = None) -> ArchiveReport:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / "academic.db"
            online_backup(self.db_path, snap)
            db_sha = _sha256(snap)
            blobs: list[tuple[str, Path]] = []
            if cas_root is not None:
                root = Path(cas_root)
                for p in sorted(root.rglob("*")):
                    if p.is_file() and not p.is_symlink() and len(p.name) == 64:
                        blobs.append((f"cas/{p.relative_to(root).as_posix()}", p))
            manifest = {"schema": ARCHIVE_SCHEMA, "db": "academic.db", "db_sha256": db_sha,
                        "blobs": {name: p.name for name, p in blobs}}
            with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("manifest.json", json.dumps(manifest, sort_keys=True, indent=2))
                zf.write(snap, "academic.db")
                for name, p in blobs:
                    zf.write(p, name)
        return ArchiveReport(str(dest), _sha256(dest), 2 + len(blobs), db_sha, len(blobs))

    @staticmethod
    def verify_zip(path: str | Path, *, max_members: int = MAX_MEMBERS,
                   max_member_bytes: int = MAX_MEMBER_BYTES,
                   max_total_bytes: int = MAX_TOTAL_BYTES,
                   max_ratio: int = MAX_RATIO) -> dict:
        """Validate an archive WITHOUT extracting it to its own paths.
        Raises ArchiveRejected (AC-SEC-003) on any violation."""
        try:
            zf = zipfile.ZipFile(path)
        except (zipfile.BadZipFile, OSError) as e:
            raise ArchiveRejected(f"not a valid zip: {type(e).__name__}") from e
        with zf:
            infos = zf.infolist()
            if len(infos) > max_members:
                raise ArchiveRejected("too many members")
            total = 0
            names = set()
            for info in infos:
                if not _safe_member(info.filename):
                    raise ArchiveRejected(f"unsafe member path: {info.filename!r}")
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise ArchiveRejected(f"symlink member refused: {info.filename!r}")
                if info.file_size > max_member_bytes:
                    raise ArchiveRejected(f"member too large: {info.filename!r}")
                total += info.file_size
                if total > max_total_bytes:
                    raise ArchiveRejected("archive exceeds total size limit")
                if info.compress_size and info.file_size / info.compress_size > max_ratio:
                    raise ArchiveRejected(f"suspicious compression ratio: {info.filename!r}")
                if info.filename in names:
                    raise ArchiveRejected(f"duplicate member: {info.filename!r}")
                names.add(info.filename)
            if "manifest.json" not in names or "academic.db" not in names:
                raise ArchiveRejected("manifest.json/academic.db missing")
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            if manifest.get("schema") != ARCHIVE_SCHEMA:
                raise ArchiveRejected("unknown archive schema")
            with tempfile.TemporaryDirectory() as tmp:
                db = Path(tmp) / "check.db"
                with zf.open("academic.db") as src, db.open("wb") as out:
                    for chunk in iter(lambda: src.read(1024 * 1024), b""):
                        out.write(chunk)
                if _sha256(db) != manifest.get("db_sha256"):
                    raise ArchiveRejected("database hash mismatch")
                with db.open("rb") as fh:
                    if fh.read(16) != b"SQLite format 3\x00":
                        raise ArchiveRejected("database member is not SQLite")
                if sqlite_integrity(db) != "ok":
                    raise ArchiveRejected("database integrity_check failed")
            for name, expected in sorted(manifest.get("blobs", {}).items()):
                h = hashlib.sha256()
                with zf.open(name) as fh:
                    for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                        h.update(chunk)
                if h.hexdigest() != expected:
                    raise ArchiveRejected(f"blob hash mismatch: {name}")
            return {"members": len(infos), "db_sha256": manifest["db_sha256"],
                    "blobs": len(manifest.get("blobs", {}))}
