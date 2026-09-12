"""Authoring persistence: lifecycle + academic links (SQLite, additive)."""

from __future__ import annotations

from datetime import datetime, timezone


class AuthoringStore:
    def __init__(self, db):
        self.db = db

    def lifecycle_of(self, resource_id: str) -> str:
        cx = self.db.connect()
        row = cx.execute("SELECT lifecycle FROM authored WHERE resource_id=?",
                         (resource_id,)).fetchone()
        cx.close()
        return row["lifecycle"] if row else "DRAFT"

    def set_lifecycle(self, resource_id: str, state: str, template: str = "") -> None:
        from academic_core.domain.authoring import LIFECYCLE, transition
        if state not in LIFECYCLE:
            raise ValueError(f"bad lifecycle: {state}")
        current = self.lifecycle_of(resource_id)
        if state != current:
            transition(current, state)  # rejects illegal moves loudly
        cx = self.db.connect()
        cx.execute("INSERT OR REPLACE INTO authored(resource_id, lifecycle, template, updated_at)"
                   " VALUES (?,?,?,?)",
                   (resource_id, state, template,
                    datetime.now(timezone.utc).isoformat()))
        cx.commit()
        cx.close()

    def touch(self, resource_id: str) -> None:
        cx = self.db.connect()
        cx.execute("INSERT OR IGNORE INTO authored(resource_id) VALUES (?)", (resource_id,))
        cx.execute("UPDATE authored SET updated_at=? WHERE resource_id=?",
                   (datetime.now(timezone.utc).isoformat(), resource_id))
        cx.commit()
        cx.close()

    def add_link(self, resource_id: str, target_kind: str, target_id: str) -> None:
        if target_kind not in ("subject", "topic", "assignment", "project",
                               "lab", "exam"):
            raise ValueError(f"bad link kind: {target_kind}")
        cx = self.db.connect()
        cx.execute("INSERT OR REPLACE INTO doc_links VALUES (?,?,?)",
                   (resource_id, target_kind, target_id))
        cx.commit()
        cx.close()

    def remove_link(self, resource_id: str, target_kind: str, target_id: str) -> None:
        cx = self.db.connect()
        cx.execute("DELETE FROM doc_links WHERE resource_id=? AND target_kind=?"
                   " AND target_id=?", (resource_id, target_kind, target_id))
        cx.commit()
        cx.close()

    def links_of(self, resource_id: str) -> list[dict]:
        cx = self.db.connect()
        rows = cx.execute("SELECT target_kind, target_id FROM doc_links"
                          " WHERE resource_id=? ORDER BY target_kind, target_id",
                          (resource_id,)).fetchall()
        cx.close()
        return [dict(r) for r in rows]

    def authored_ids(self) -> list[str]:
        cx = self.db.connect()
        rows = cx.execute("SELECT resource_id FROM authored ORDER BY updated_at DESC").fetchall()
        cx.close()
        return [r["resource_id"] for r in rows]
