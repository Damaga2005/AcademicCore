"""Identity: stable ids independent of path, index and reimports."""
from academic_core.application.ingest import IngestionService
from academic_core.domain import entities as E
from academic_core.domain.identity import validate
from academic_core.infrastructure import (
    AcademicRepository, Database, FileBlobStore, FtsResourceIndexer,
    PlanningRepository, SqliteResourceRecords,
)


def _svc(tmp_path):
    db = Database(tmp_path / "a.db")
    ac = AcademicRepository(db)
    ac.add_university(E.University("university:u", "U"))
    return IngestionService(FileBlobStore(tmp_path / "cas"), SqliteResourceRecords(db),
                            FtsResourceIndexer(db), ac, PlanningRepository(db)), db


def test_id_stable_across_reindex_and_reopen(tmp_path):
    svc, db = _svc(tmp_path)
    f = tmp_path / "doc.md"
    f.write_text("# D\n\ntexto", encoding="utf-8")
    sid = svc.import_file(f).stable_id
    assert validate(sid) == "resource"
    svc.reindex()
    assert SqliteResourceRecords(db).get(sid).stable_id == sid
    # Reopen everything from disk: same id, same hash, same version.
    svc2, db2 = _svc(tmp_path)
    res = SqliteResourceRecords(db2).get(sid)
    assert (res.stable_id, res.current_version) == (sid, 1)
    assert svc2.import_file(f).outcome == "duplicate"


def test_id_independent_of_path_and_index(tmp_path):
    svc, db = _svc(tmp_path)
    f = tmp_path / "orig.md"
    f.write_text("same-bytes", encoding="utf-8")
    sid = svc.import_bytes(b"same-bytes", "totally/different/name.md", origin="manual").stable_id
    assert svc.import_file(f).stable_id == sid  # path never becomes identity
    FtsResourceIndexer(db).clear()  # index dropped...
    assert SqliteResourceRecords(db).get(sid) is not None  # ...identity survives
    assert svc.reindex() == 1


def test_version_identity_distinct_but_scoped(tmp_path):
    svc, _ = _svc(tmp_path)
    r1 = svc.import_bytes(b"v1", "a.txt", origin="manual")
    r2 = svc.import_bytes(b"v2", "a.txt", origin="manual", resource_id=r1.stable_id)
    assert r1.stable_id == r2.stable_id and r1.version != r2.version
