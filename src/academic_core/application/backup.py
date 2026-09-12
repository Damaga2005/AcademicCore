"""BackupService (Phase 1 boundary): SQLite snapshot + manifest.

CAS bytes and derived indexes are regenerable and excluded by design;
the manifest records their hashes so a later phase can verify restores.
Secrets are never included (see security.py).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class BackupReport:
    path: str
    sha256: str
    created: str


class BackupService:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def backup(self, dest_dir: str | Path) -> BackupReport:
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        target = dest / f"academic-{stamp}.db"
        shutil.copy2(self.db_path, target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        (dest / f"academic-{stamp}.manifest.json").write_text(
            json.dumps({"db": target.name, "sha256": digest, "created": stamp,
                        "note": "CAS/indexes regenerable; secrets excluded"},
                       indent=2), encoding="utf-8")
        return BackupReport(str(target), digest, stamp)
