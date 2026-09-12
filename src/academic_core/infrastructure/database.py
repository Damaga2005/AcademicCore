"""SQLite infrastructure (Phase 1): stdlib sqlite3 only.

Deliberately NO SQLAlchemy (see ADR-0012): single-user desktop, gate
requires Domain free of ORM, zero new runtime dependencies. ORM lives
nowhere — repositories map rows to domain dataclasses explicitly.
Migrations are forward-only, one concern per file, tracked in
`schema_version`. Large blobs never enter SQLite (entities carry refs;
bytes belong to CAS, Phase 0 Store).
"""

from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path

_MIGRATIONS = ("001_academic.sql", "002_grading.sql",
               "003_planning.sql", "004_study.sql",
               "005_resources.sql", "006_fts.sql",
               "007_documents.sql", "008_academic_f4.sql",
               "009_authoring.sql", "010_engineering.sql")


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        cx = sqlite3.connect(self.path)
        cx.row_factory = sqlite3.Row
        cx.execute("PRAGMA foreign_keys=ON")
        cx.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")
        applied = {r[0] for r in cx.execute("SELECT version FROM schema_version")}
        for i, name in enumerate(_MIGRATIONS, start=1):
            if i not in applied:
                sql = resources.files("academic_core.infrastructure.migrations").joinpath(name).read_text(encoding="utf-8")
                cx.executescript(sql)
                cx.execute("INSERT INTO schema_version(version) VALUES (?)", (i,))
        cx.commit()
        return cx
