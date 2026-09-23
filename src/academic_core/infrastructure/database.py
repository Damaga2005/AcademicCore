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
import time
from importlib import resources
from pathlib import Path

_MIGRATIONS = ("001_academic.sql", "002_grading.sql",
               "003_planning.sql", "004_study.sql",
               "005_resources.sql", "006_fts.sql",
               "007_documents.sql", "008_academic_f4.sql",
               "009_authoring.sql", "010_engineering.sql",
               "011_assessment.sql", "012_academic_f41.sql",
               "013_legacy_payload_version.sql")


def _split_statements(script: str) -> list[str]:
    """Split a migration script into individually-executable statements.

    Naively splitting on ``;`` is unsafe: a ``CREATE TRIGGER ... BEGIN ... END;``
    body contains semicolons that do not terminate the outer statement, and a
    string literal could in principle contain one too. ``sqlite3.complete_statement``
    wraps SQLite's own ``sqlite3_complete()``, which tracks quoting, comments and
    trigger BEGIN/END nesting, so it is the only safe boundary-detector available
    without a full SQL parser. Statements are accumulated line-by-line until a
    prefix is a complete statement on its own.
    """
    statements: list[str] = []
    buf: list[str] = []
    for line in script.splitlines(keepends=True):
        buf.append(line)
        candidate = "".join(buf)
        if candidate.strip() and sqlite3.complete_statement(candidate):
            statements.append(candidate)
            buf = []
    trailing = "".join(buf).strip()
    if trailing:
        # Leftover text that never formed a complete statement (e.g. a
        # trailing comment or malformed SQL) — surface it rather than
        # silently dropping it.
        if trailing.lstrip().startswith("--"):
            pass  # trailing-comment-only remainder, safe to ignore
        else:
            raise ValueError(f"incomplete trailing SQL statement: {trailing!r}")
    return statements


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        cx = sqlite3.connect(self.path, timeout=10.0, isolation_level=None)
        # Every statement below this point can raise (locked WAL switch
        # after exhausted retries, failed PRAGMA, failed migration...).
        # The connection must never escape open on a failed init, so the
        # whole init phase runs under a success flag: any exception closes
        # the connection before propagating; only a fully initialized
        # connection is ever returned open.
        _initialized = False
        try:
            cx.row_factory = sqlite3.Row
            cx.execute("PRAGMA foreign_keys=ON")
            # busy_timeout must be set before journal_mode=WAL: switching a
            # brand-new database into WAL mode itself needs to acquire a lock,
            # and with two connections racing to open the same fresh file, the
            # loser would otherwise hit `sqlite3.OperationalError: database is
            # locked` here immediately (busy_timeout not yet in effect) instead
            # of waiting for the winner to finish.
            cx.execute("PRAGMA busy_timeout=10000")
            # Switching a brand-new file into WAL mode takes a lock of its own
            # to write the WAL header, and on some SQLite builds that specific
            # lock acquisition can return SQLITE_BUSY without going through the
            # normal busy-handler retry loop that `busy_timeout` installs (it
            # reliably backs off writes done via BEGIN IMMEDIATE below, but not
            # always this particular mode change). Retry it manually rather
            # than let a raced first-open of the file surface as an unhandled
            # "database is locked".
            _last_exc: sqlite3.OperationalError | None = None
            for _ in range(100):
                try:
                    cx.execute("PRAGMA journal_mode=WAL")
                    _last_exc = None
                    break
                except sqlite3.OperationalError as exc:
                    if "locked" not in str(exc) and "busy" not in str(exc):
                        raise
                    _last_exc = exc
                    time.sleep(0.1)
            if _last_exc is not None:
                raise _last_exc
            cx.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")
            applied = {r[0] for r in cx.execute("SELECT version FROM schema_version")}
            for i, name in enumerate(_MIGRATIONS, start=1):
                if i not in applied:
                    sql = resources.files("academic_core.infrastructure.migrations").joinpath(name).read_text(encoding="utf-8")
                    statements = _split_statements(sql)
                    # Explicit transaction (isolation_level=None puts the
                    # connection in autocommit mode, so BEGIN/COMMIT below are
                    # the only things opening/closing a transaction — unlike
                    # executescript(), which forces a commit of any pending
                    # transaction before it runs and cannot be rolled back as a
                    # unit). SQLite's DDL (CREATE/ALTER/DROP) is transactional,
                    # so either every statement in this migration lands, or, on
                    # failure, none of them do and schema_version is never
                    # updated for this version — no partially-applied migration
                    # can be left on disk to wedge a later retry.
                    cx.execute("BEGIN IMMEDIATE")
                    try:
                        # Re-check under the write lock: another connection may
                        # have raced us to this exact migration and already
                        # committed it while we were blocked acquiring the lock
                        # above (the `applied` set read before this loop started
                        # is now stale for this version). If so, this connection
                        # lost the race — skip re-running the statements and the
                        # INSERT (which would otherwise hit schema_version's
                        # PRIMARY KEY) and just fall through to COMMIT.
                        already = cx.execute(
                            "SELECT 1 FROM schema_version WHERE version = ?", (i,)
                        ).fetchone()
                        if already is None:
                            for stmt in statements:
                                cx.execute(stmt)
                            cx.execute("INSERT INTO schema_version(version) VALUES (?)", (i,))
                    except BaseException:
                        cx.execute("ROLLBACK")
                        raise
                    else:
                        cx.execute("COMMIT")
            _initialized = True
            return cx
        finally:
            if not _initialized:
                cx.close()


def online_backup(src_path: str | Path, dst_path: str | Path) -> None:
    """Consistent copy of a live SQLite database (WAL-safe), via SQLite's
    online-backup API. A plain file copy can miss committed pages that
    still live in the -wal file."""
    src = sqlite3.connect(Path(src_path), timeout=10.0)
    try:
        dst = sqlite3.connect(Path(dst_path))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def sqlite_integrity(path: str | Path) -> str:
    """``PRAGMA integrity_check`` of a file opened read-only."""
    cx = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        return cx.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        cx.close()
