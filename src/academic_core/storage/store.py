"""Hybrid storage: SQLite (metadata/relations/state) + Filesystem/CAS (bytes) + Indexes.

- Never store large blobs in SQLite: store sha256 + path.
- CAS layout: <cas_dir>/<sha256[0:2]>/<sha256[2:4]>/<sha256>
- Schema version table enables forward-only migrations.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS entities (
  stable_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  subject TEXT NOT NULL,
  payload TEXT NOT NULL DEFAULT '{}',
  cas_hash TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_entities_kind ON entities(kind);
CREATE INDEX IF NOT EXISTS idx_entities_subject ON entities(subject);
"""


class Store:
    def __init__(self, db_path: str | Path, cas_dir: str | Path):
        self.db_path = Path(db_path)
        self.cas_dir = Path(cas_dir)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.cas_dir.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        cx = sqlite3.connect(self.db_path)
        cx.executescript(_SCHEMA)
        row = cx.execute("SELECT version FROM schema_version").fetchone()
        if row is None:
            cx.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))
            cx.commit()
        return cx

    def put_bytes(self, data: bytes) -> str:
        self.connect().close()
        h = hashlib.sha256(data).hexdigest()
        p = self.cas_dir / h[0:2] / h[2:4] / h
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_bytes(data)
        return h

    def get_bytes(self, cas_hash: str) -> bytes:
        return (self.cas_dir / cas_hash[0:2] / cas_hash[2:4] / cas_hash).read_bytes()

    def put_entity(self, stable_id: str, kind: str, subject: str,
                   payload: str = "{}", cas_hash: str | None = None) -> None:
        cx = self.connect()
        cx.execute(
            "INSERT OR REPLACE INTO entities(stable_id, kind, subject, payload, cas_hash)"
            " VALUES (?,?,?,?,?)", (stable_id, kind, subject, payload, cas_hash))
        cx.commit()
        cx.close()

    def get_entity(self, stable_id: str) -> dict | None:
        cx = self.connect()
        row = cx.execute(
            "SELECT stable_id, kind, subject, payload, cas_hash FROM entities WHERE stable_id=?",
            (stable_id,)).fetchone()
        cx.close()
        if not row:
            return None
        return dict(zip(("stable_id", "kind", "subject", "payload", "cas_hash"), row))
