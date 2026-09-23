"""Canonical resource records (SQLite) + derived FTS5 index.

Records are the source of truth for metadata/provenance/versions; the FTS
table is droppable and rebuildable at any time without touching them.
"""

from __future__ import annotations

import re
from contextlib import contextmanager

from academic_core.domain import resources as R
from academic_core.infrastructure.database import Database


def _match_expr(query: str) -> str:
    """Turn free user text into a safe FTS5 MATCH expression: alphanumeric
    tokens AND-ed, each double-quoted (hyphens/quotes in input can never
    become operators or column references)."""
    tokens = re.findall(r"[\w]+", query, re.UNICODE)
    if not tokens:
        return '"__no_match_possible__"'
    return " AND ".join('"' + t.replace('"', '""') + '"' for t in tokens)


class SqliteResourceRecords:
    def __init__(self, db: Database):
        self.db = db

    @contextmanager
    def unit_of_work(self):
        cx = self.db.connect()
        try:
            yield cx
            cx.commit()
        except BaseException:
            cx.rollback()
            raise
        finally:
            cx.close()

    # -- resources -----------------------------------------------------------
    def get(self, stable_id: str) -> R.Resource | None:
        cx = self.db.connect()
        row = cx.execute("SELECT * FROM resources WHERE stable_id=?", (stable_id,)).fetchone()
        if not row:
            cx.close()
            return None
        vers = cx.execute("SELECT * FROM resource_versions WHERE stable_id=? ORDER BY version",
                          (stable_id,)).fetchall()
        cx.close()
        return R.Resource(row["stable_id"], row["kind"], row["title"], row["current_version"],
                          [self._version(v) for v in vers])

    @staticmethod
    def _version(v) -> R.ResourceVersion:
        return R.ResourceVersion(
            v["stable_id"], v["version"], v["content_hash"], v["size"],
            R.ResourceProvenance(v["origin"], v["source"], v["original_filename"],
                                 v["content_hash"], v["imported_at"], v["adapter"],
                                 v["adapter_version"], v["extraction_status"],
                                 v["parent_version"], v["note"]))

    def save_new(self, res: R.Resource, cx=None) -> None:
        close = False
        if cx is None:
            cx = self.db.connect()
            close = True
        cx.execute("INSERT INTO resources VALUES (?,?,?,?)",
                   (res.stable_id, res.kind, res.title, res.current_version))
        for v in res.versions:
            self._insert_version(cx, v)
        if close:
            cx.commit()
            cx.close()

    @staticmethod
    def _insert_version(cx, v: R.ResourceVersion) -> None:
        p = v.provenance
        cx.execute("INSERT INTO resource_versions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (v.stable_id, v.version, v.content_hash, v.size, p.origin, p.source,
                    p.original_filename, p.imported_at, p.adapter, p.adapter_version,
                    p.extraction_status, p.parent_version, p.note))

    def append_version(self, v: R.ResourceVersion, cx=None) -> None:
        close = False
        if cx is None:
            cx = self.db.connect()
            close = True
        self._insert_version(cx, v)
        cx.execute("UPDATE resources SET current_version=? WHERE stable_id=?",
                   (v.version, v.stable_id))
        if close:
            cx.commit()
            cx.close()

    def find_by_hash(self, content_hash: str) -> list[tuple[str, int]]:
        """All (stable_id, version) rows for these bytes — global dedup lookup."""
        cx = self.db.connect()
        rows = cx.execute("SELECT stable_id, version FROM resource_versions"
                          " WHERE content_hash=?", (content_hash,)).fetchall()
        cx.close()
        return [(r["stable_id"], r["version"]) for r in rows]

    def find_latest_by_source(self, source: str) -> str | None:
        """Newest resource whose CURRENT version came from this source path."""
        cx = self.db.connect()
        row = cx.execute(
            "SELECT r.stable_id FROM resources r JOIN resource_versions v"
            " ON v.stable_id=r.stable_id AND v.version=r.current_version"
            " WHERE v.source=? ORDER BY v.imported_at DESC LIMIT 1", (source,)).fetchone()
        cx.close()
        return row["stable_id"] if row else None

    def all_ids(self) -> list[str]:
        cx = self.db.connect()
        rows = cx.execute("SELECT stable_id FROM resources ORDER BY stable_id").fetchall()
        cx.close()
        return [r["stable_id"] for r in rows]

    def update_title(self, stable_id: str, title: str) -> None:
        cx = self.db.connect()
        cx.execute("UPDATE resources SET title=? WHERE stable_id=?", (title, stable_id))
        cx.commit()
        cx.close()


class FtsResourceIndexer:
    def __init__(self, db: Database):
        self.db = db

    def index(self, stable_id: str, kind: str, title: str, text: str) -> None:
        cx = self.db.connect()
        cx.execute("DELETE FROM resources_fts WHERE stable_id=?", (stable_id,))
        cx.execute("INSERT INTO resources_fts(stable_id, kind, title, body) VALUES (?,?,?,?)",
                   (stable_id, kind, title, text))
        cx.commit()
        cx.close()

    def remove(self, stable_id: str) -> None:
        cx = self.db.connect()
        cx.execute("DELETE FROM resources_fts WHERE stable_id=?", (stable_id,))
        cx.commit()
        cx.close()

    def clear(self) -> None:
        cx = self.db.connect()
        cx.execute("DELETE FROM resources_fts")
        cx.commit()
        cx.close()

    def search(self, query: str, kind: str = "", subject: str = "",
               limit: int = 20) -> list[dict]:
        cx = self.db.connect()
        # FTS5 match query passed as parameter (no string interpolation).
        # F4.1: kind/subject filters run inside SQL and snippet() is computed
        # only for the rows actually returned (previously for limit*3 rows,
        # filtered in Python, which could also drop valid hits).
        rows = cx.execute(
            "SELECT f.stable_id, f.kind, f.title,"
            " snippet(resources_fts, 3, '»', '«', '…', 12) AS snippet"
            " FROM resources_fts f WHERE resources_fts MATCH ?"
            " AND (? = '' OR f.kind = ?)"
            " AND (? = '' OR EXISTS (SELECT 1 FROM resource_refs r"
            "      WHERE r.resource_id = f.stable_id AND r.subject_id = ?))"
            " LIMIT ?",
            (_match_expr(query), kind, kind, subject, subject, limit)).fetchall()
        out = [{"stable_id": r["stable_id"], "kind": r["kind"],
                "title": r["title"], "snippet": r["snippet"]} for r in rows]
        cx.close()
        return out

    def rebuild(self, records: SqliteResourceRecords, bodies: dict[str, tuple[str, str, str]]) -> int:
        """bodies: stable_id -> (kind, title, text). Returns entries indexed."""
        self.clear()
        n = 0
        for sid, (kind, title, text) in bodies.items():
            self.index(sid, kind, title, text)
            n += 1
        return n
