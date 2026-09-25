# SPDX-License-Identifier: MIT
"""F13-ext sync persistence: sync_state + append-only sync_log (no ORM)."""

from __future__ import annotations

from contextlib import contextmanager

from academic_core.domain import sync as S
from academic_core.infrastructure.database import Database


class SyncLogRepository:
    def __init__(self, db: Database):
        self.db = db

    @contextmanager
    def _tx(self):
        cx = self.db.connect()
        try:
            cx.execute("BEGIN IMMEDIATE")
            yield cx
            cx.execute("COMMIT")
        except BaseException:
            cx.execute("ROLLBACK")
            raise
        finally:
            cx.close()

    def append(self, event: S.SyncEvent, kind: str = "") -> None:
        with self._tx() as cx:
            cx.execute(
                "INSERT OR IGNORE INTO sync_log(event_id, device_id, resource_id, kind,"
                " operation, local_version, remote_version, winner, conflict, result,"
                " timestamp_ms, digest_before, digest_after, protocol_version)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (event.event_id, event.device_id, event.resource_id, kind,
                 event.operation, event.local_version, event.remote_version,
                 event.winner, int(bool(event.conflict)), event.result,
                 int(event.timestamp_ms), event.digest_before, event.digest_after,
                 event.protocol_version))

    def events_of(self, resource_id: str) -> list[dict]:
        cx = self.db.connect()
        try:
            rows = cx.execute("SELECT * FROM sync_log WHERE resource_id=?"
                              " ORDER BY timestamp_ms, event_id",
                              (resource_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            cx.close()

    def get_state(self, resource_id: str) -> dict | None:
        cx = self.db.connect()
        try:
            r = cx.execute("SELECT * FROM sync_state WHERE resource_id=?",
                           (resource_id,)).fetchone()
            return dict(r) if r else None
        finally:
            cx.close()

    def put_state(self, record: S.SyncRecord) -> None:
        with self._tx() as cx:
            cx.execute("INSERT OR REPLACE INTO sync_state(resource_id, kind, version_ms,"
                       " version_device, digest, updated_ms) VALUES (?,?,?,?,?,?)",
                       (record.resource_id, record.kind, int(record.version_ms),
                        record.version_device, record.digest, int(record.updated_ms)))
