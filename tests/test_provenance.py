"""Provenance: origin/hash/adapter/timestamp persisted and reopenable."""
from academic_core.application.ingest import IngestionService
from academic_core.domain import entities as E
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


def test_file_provenance_complete(tmp_path):
    svc, _ = _svc(tmp_path)
    f = tmp_path / "apuntes.md"
    f.write_text("# Apuntes", encoding="utf-8")
    rep = svc.import_file(f, subject_id=None)
    prov = SqliteResourceRecords(Database(tmp_path / "a.db")).get(rep.stable_id).current().provenance
    assert prov.origin == "file"
    assert prov.source == str(f) and prov.original_filename == "apuntes.md"
    assert prov.content_hash == rep.content_hash and len(prov.content_hash) == 64
    assert prov.adapter == "markdown" and prov.adapter_version == "1"
    assert prov.imported_at and prov.extraction_status == "ok"
    assert prov.parent_version == 0


def test_origins_distinguishable(tmp_path):
    svc, db = _svc(tmp_path)
    m = svc.import_bytes(b"a", "a.txt", origin="manual").stable_id
    g = svc.import_bytes(b"b", "b.txt", origin="generated").stable_id
    rec = SqliteResourceRecords(db)
    assert rec.get(m).current().provenance.origin == "manual"
    assert rec.get(g).current().provenance.origin == "generated"


def test_version_chain_links_parents(tmp_path):
    svc, db = _svc(tmp_path)
    r1 = svc.import_bytes(b"one", "n.txt", origin="manual")
    r2 = svc.import_bytes(b"two", "n.txt", origin="manual", resource_id=r1.stable_id)
    prov = SqliteResourceRecords(db).get(r1.stable_id).current().provenance
    assert (r2.version, prov.parent_version) == (2, 1)
