"""Migration gate placeholder: formula coverage must stay 100% (Sistemes-de-Mesura).

Phase 0: pins the contract (2896 formulas benchmark shape). Phase 12 runs the
real gate: every source formula retrievable top-k with provenance intact.
"""
import sqlite3
from importlib import resources

import pytest

EXPECTED_FORMULA_COUNT = 2896  # audited in Sistemes-de-Mesura knowledge.sqlite

from academic_core.domain.identity import validate


@pytest.mark.migration
def test_formula_identity_contract():
    # Every migrated formula MUST carry a stable formula: ID + source latex + provenance.
    from academic_core.domain.academic import Formula
    f = Formula(stable_id="formula:sistemes-de-mesura:f:002847",
                latex=r"U=R\\cdot I", source_latex=r"U=R\\cdot I",
                provenance={"source_path": "Tema 3/x.html", "hash": "abc"})
    assert validate(f.stable_id) == "formula"
    assert f.source_latex == f.latex  # original preserved in Phase 0
    assert "source_path" in f.provenance


@pytest.mark.migration
def test_expected_corpus_size_pinned():
    assert EXPECTED_FORMULA_COUNT == 2896


@pytest.mark.migration
def test_concurrent_first_connect_is_race_free(tmp_path):
    """Two connections racing to open the SAME brand-new sqlite file must
    both succeed with no unhandled exception, and the on-disk schema must
    end up fully and exactly migrated (no duplicate/missing schema_version
    rows).

    Regression test for a TOCTOU in Database.connect(): the pre-loop
    `applied` set is read once, before the per-migration loop, so a
    connection that loses the BEGIN IMMEDIATE lock race for a given
    migration used to re-run that migration's INSERT INTO schema_version
    unconditionally after finally acquiring the lock, raising an unhandled
    sqlite3.IntegrityError (PRIMARY KEY collision) or, transiently,
    sqlite3.OperationalError: database is locked. Fixed by re-checking
    schema_version for that specific version under the lock before running
    the migration's statements.
    """
    import sqlite3
    import threading

    from academic_core.infrastructure.database import Database, _MIGRATIONS

    n_iterations = 20
    for it in range(n_iterations):
        db_path = tmp_path / f"race_{it}.db"
        barrier = threading.Barrier(2)
        results: dict[int, BaseException | None] = {}

        def worker(idx):
            try:
                barrier.wait()
                cx = Database(db_path).connect()
                cx.close()
                results[idx] = None
            except BaseException as exc:  # noqa: BLE001 - must observe every failure
                results[idx] = exc

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        failures = {k: v for k, v in results.items() if v is not None}
        assert not failures, f"iteration {it}: unhandled exception(s) racing to connect(): {failures}"

        cx = sqlite3.connect(db_path)
        try:
            versions = [r[0] for r in cx.execute(
                "SELECT version FROM schema_version ORDER BY version")]
        finally:
            cx.close()
        assert versions == list(range(1, len(_MIGRATIONS) + 1)), (
            f"iteration {it}: schema_version rows are {versions!r}, "
            f"expected exactly one row per migration with no duplicates")


class _FakeMigrationFile:
    """Stand-in for the ``importlib.resources`` Traversable returned by
    ``.joinpath(name)``, exposing only the ``.read_text()`` the migration
    loader actually calls."""

    def __init__(self, sql: str):
        self._sql = sql

    def read_text(self, encoding: str = "utf-8") -> str:
        return self._sql


class _FakeMigrationsDir:
    """Wraps the real migrations package Traversable, but serves a
    synthetic in-memory SQL script for one extra, test-only migration
    name instead of hitting the filesystem for it."""

    def __init__(self, real, extra_name: str, extra_sql: str):
        self._real = real
        self._extra_name = extra_name
        self._extra_sql = extra_sql

    def joinpath(self, name: str):
        if name == self._extra_name:
            return _FakeMigrationFile(self._extra_sql)
        return self._real.joinpath(name)


_BAD_MIGRATION_SQL = """\
CREATE TABLE A (id INTEGER PRIMARY KEY);
CREATE TABLE B (id INTEGER PRIMARY KEY);
THIS IS NOT VALID SQL AT ALL;
CREATE TABLE C (id INTEGER PRIMARY KEY);
"""


@pytest.mark.migration
def test_single_connection_migration_failure_rolls_back_atomically(tmp_path, monkeypatch):
    """A mid-migration execution failure on a single connection must leave
    NO partial state on disk: none of the migration's DDL statements
    survive, schema_version is not advanced for that migration, and the
    database is left perfectly usable afterward (no wedged/half-open
    transaction).

    Regression test for the BEGIN IMMEDIATE / COMMIT / ROLLBACK-on-failure
    logic in Database.connect() that replaced a bare executescript() call
    (which cannot be rolled back as a unit and implicitly commits any
    pending transaction before running).
    """
    import academic_core.infrastructure.database as dbmod
    from academic_core.infrastructure.database import Database, _MIGRATIONS

    db_path = tmp_path / "atomic.db"

    real_files = dbmod.resources.files

    def fake_files(package):
        real = real_files(package)
        if package == "academic_core.infrastructure.migrations":
            return _FakeMigrationsDir(real, "999_bad_test_only.sql", _BAD_MIGRATION_SQL)
        return real

    monkeypatch.setattr(dbmod.resources, "files", fake_files)
    monkeypatch.setattr(dbmod, "_MIGRATIONS", _MIGRATIONS + ("999_bad_test_only.sql",))

    with pytest.raises(sqlite3.Error):
        Database(db_path).connect()

    # Inspect the on-disk file with a plain, unpatched connection: none of
    # the bad migration's tables may exist, and schema_version must stop
    # at the last real migration (the extra one never committed).
    cx = sqlite3.connect(db_path)
    try:
        tables = {r[0] for r in cx.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "A" not in tables
        assert "B" not in tables
        assert "C" not in tables
        versions = [r[0] for r in cx.execute(
            "SELECT version FROM schema_version ORDER BY version")]
        assert versions == list(range(1, len(_MIGRATIONS) + 1)), (
            f"expected exactly the real migrations applied, got {versions!r}")
        # The database itself must not be left in a broken transaction
        # state: an ordinary write must still succeed.
        cx.execute("CREATE TABLE _smoke_test (x INTEGER)")
        cx.execute("INSERT INTO _smoke_test VALUES (1)")
        cx.commit()
        assert cx.execute("SELECT x FROM _smoke_test").fetchone()[0] == 1
    finally:
        cx.close()

    # And a fresh, unpatched Database.connect() against the same file
    # (the bad migration no longer registered) must succeed cleanly,
    # proving nothing was left wedged by the failed attempt.
    monkeypatch.undo()
    cx2 = Database(db_path).connect()
    try:
        versions2 = [r[0] for r in cx2.execute(
            "SELECT version FROM schema_version ORDER BY version")]
        assert versions2 == list(range(1, len(_MIGRATIONS) + 1))
    finally:
        cx2.close()


@pytest.mark.migration
class TestSplitStatements:
    """Unit tests for Database._split_statements, the sqlite3.complete_statement
    based boundary-detector that replaced naive splitting on ``;``."""

    def test_semicolon_inside_string_literal(self):
        from academic_core.infrastructure.database import _split_statements

        sql = "INSERT INTO t(name) VALUES ('a;b;c');\nINSERT INTO t(name) VALUES ('d');\n"
        stmts = _split_statements(sql)
        assert len(stmts) == 2
        assert "a;b;c" in stmts[0]
        assert stmts[1].strip().startswith("INSERT INTO t(name) VALUES ('d')")

    def test_line_comment_with_semicolon_is_not_a_boundary(self):
        from academic_core.infrastructure.database import _split_statements

        sql = (
            "-- this comment has a semicolon; right here\n"
            "CREATE TABLE t (id INTEGER);\n"
        )
        stmts = _split_statements(sql)
        assert len(stmts) == 1
        assert "CREATE TABLE t" in stmts[0]

    def test_block_comment_with_semicolon_is_not_a_boundary(self):
        from academic_core.infrastructure.database import _split_statements

        sql = (
            "/* block comment; with a semicolon inside */\n"
            "CREATE TABLE t (id INTEGER);\n"
            "CREATE TABLE u (id INTEGER);\n"
        )
        stmts = _split_statements(sql)
        assert len(stmts) == 2
        assert "CREATE TABLE t" in stmts[0]
        assert "CREATE TABLE u" in stmts[1]

    def test_trigger_body_with_internal_semicolons_is_one_statement(self):
        from academic_core.infrastructure.database import _split_statements

        sql = (
            "CREATE TABLE t (id INTEGER, updated_at TEXT);\n"
            "CREATE TRIGGER trg_t_touch AFTER UPDATE ON t BEGIN\n"
            "  UPDATE t SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;\n"
            "  INSERT INTO t(id) VALUES (NEW.id);\n"
            "  DELETE FROM t WHERE id = -1;\n"
            "END;\n"
            "CREATE TABLE u (id INTEGER);\n"
        )
        stmts = _split_statements(sql)
        assert len(stmts) == 3
        assert stmts[0].strip().startswith("CREATE TABLE t")
        trigger_stmt = stmts[1]
        assert trigger_stmt.strip().startswith("CREATE TRIGGER trg_t_touch")
        assert trigger_stmt.count(";") == 4  # 3 internal + the terminating END;
        assert stmts[2].strip().startswith("CREATE TABLE u")

    def test_combined_pathological_script(self):
        """All hazards in one script: string-literal semicolons, both
        comment styles, and a multi-statement trigger body, mixed with
        plain statements before and after."""
        from academic_core.infrastructure.database import _split_statements

        sql = (
            "-- header comment; not a boundary\n"
            "CREATE TABLE t (id INTEGER, label TEXT);\n"
            "/* block comment;\n"
            "   spanning multiple; lines; */\n"
            "INSERT INTO t(id, label) VALUES (1, 'x;y;z');\n"
            "CREATE TRIGGER trg_t BEFORE DELETE ON t BEGIN\n"
            "  SELECT 1;\n"
            "  SELECT 2;\n"
            "END;\n"
            "CREATE TABLE done (id INTEGER);\n"
        )
        stmts = _split_statements(sql)
        assert len(stmts) == 4
        assert "CREATE TABLE t" in stmts[0]
        assert "x;y;z" in stmts[1]
        assert stmts[2].strip().startswith("CREATE TRIGGER trg_t")
        assert stmts[2].count(";") == 3
        assert stmts[3].strip().startswith("CREATE TABLE done")


@pytest.mark.migration
def test_exhausted_wal_retries_close_connection_before_propagating(tmp_path, monkeypatch):
    """If the WAL-mode switch stays locked through all retries, connect()
    must close the opened connection before propagating _last_exc — the
    connection must never escape open on a definitively failed init.

    Controlled mock: every `PRAGMA journal_mode=WAL` raises a lock
    OperationalError while all other statements succeed; sleeps are
    stubbed so the 100-iteration retry budget runs instantly.
    """
    from unittest.mock import MagicMock

    import academic_core.infrastructure.database as dbmod
    from academic_core.infrastructure.database import Database

    mock_cx = MagicMock(name="connect-spy")

    def _execute(sql, *args, **kwargs):
        if "journal_mode" in sql:
            raise sqlite3.OperationalError("database is locked")
        return MagicMock(name="cursor-spy")

    mock_cx.execute.side_effect = _execute
    monkeypatch.setattr(dbmod.sqlite3, "connect", lambda *a, **k: mock_cx)
    monkeypatch.setattr(dbmod.time, "sleep", lambda s: None)

    with pytest.raises(sqlite3.OperationalError, match="locked"):
        Database(tmp_path / "leak.db").connect()
    mock_cx.close.assert_called_once()


@pytest.mark.migration
def test_failed_pragma_closes_connection_before_propagating(tmp_path, monkeypatch):
    """Same guarantee for any other init-phase failure (here a failed
    PRAGMA before the WAL loop): close, then propagate — never leak."""
    from unittest.mock import MagicMock

    import academic_core.infrastructure.database as dbmod
    from academic_core.infrastructure.database import Database

    mock_cx = MagicMock(name="connect-spy")
    mock_cx.execute.side_effect = sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(dbmod.sqlite3, "connect", lambda *a, **k: mock_cx)
    monkeypatch.setattr(dbmod.time, "sleep", lambda s: None)

    with pytest.raises(sqlite3.OperationalError, match="locked"):
        Database(tmp_path / "leak.db").connect()
    mock_cx.close.assert_called_once()


@pytest.mark.migration
def test_real_migration_files_split_cleanly():
    """Every real migration file must be splittable by _split_statements
    without raising, and must yield at least one statement. Guards
    against the splitter regressing on the actual, more complex SQL
    (indices, triggers, FTS virtual tables) shipped in the migrations
    package, not just synthetic examples."""
    from academic_core.infrastructure.database import _MIGRATIONS, _split_statements

    assert len(_MIGRATIONS) == 17  # 017_f9_attempt_evidence (F9)
    for name in _MIGRATIONS:
        sql = resources.files("academic_core.infrastructure.migrations").joinpath(name).read_text(encoding="utf-8")
        stmts = _split_statements(sql)
        assert len(stmts) >= 1, f"{name}: expected at least one statement"
        for stmt in stmts:
            assert stmt.strip(), f"{name}: produced a blank statement"
