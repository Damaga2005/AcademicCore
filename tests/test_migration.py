"""Migration gate placeholder: formula coverage must stay 100% (Sistemes-de-Mesura).

Phase 0: pins the contract (2896 formulas benchmark shape). Phase 12 runs the
real gate: every source formula retrievable top-k with provenance intact.
"""
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
