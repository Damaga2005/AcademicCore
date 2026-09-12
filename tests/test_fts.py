"""FTS5: derived index — search, filters, deterministic rebuild."""
from academic_core.application.ingest import IngestionService
from academic_core.domain import entities as E
from academic_core.infrastructure import (
    AcademicRepository, Database, FileBlobStore, FtsResourceIndexer,
    PlanningRepository, SqliteResourceRecords,
)


def _svc(tmp_path):
    db = Database(tmp_path / "a.db")
    ac, pl = AcademicRepository(db), PlanningRepository(db)
    ac.add_university(E.University("university:u", "U"))
    ac.add_degree(E.Degree("degree:g", "G", "university:u"))
    ac.add_year(E.AcademicYear("year:2025-26", "2025-26", "degree:g"))
    ac.add_term(E.Term("term:c1", "C1", "cuatrimestre", 1, "year:2025-26"))
    for slug, name in (("sdm", "Sistemes"), ("fis", "Fisica")):
        ac.add_subject(E.Subject(f"subject:{slug}", "", name, slug.upper(), term_id="term:c1"))
    return IngestionService(FileBlobStore(tmp_path / "cas"), SqliteResourceRecords(db),
                            FtsResourceIndexer(db), ac, pl), db


def _seed(svc):
    r1 = svc.import_bytes(b"# Wheatstone\n\npuente de medida", "w.md",
                          subject_id="subject:sdm", origin="manual")
    r2 = svc.import_bytes(b"<p>puente de medida en laboratorio</p>", "l.html",
                          subject_id="subject:fis", origin="manual")
    r3 = svc.import_bytes(b"apuntes de cocina", "c.txt", origin="manual")
    return r1, r2, r3


def test_search_and_kind_filter(tmp_path):
    svc, db = _svc(tmp_path)
    r1, r2, _ = _seed(svc)
    got = {h["stable_id"] for h in FtsResourceIndexer(db).search("puente")}
    assert got == {r1.stable_id, r2.stable_id}
    md = FtsResourceIndexer(db).search("puente", kind="markdown")
    assert [h["stable_id"] for h in md] == [r1.stable_id]
    assert FtsResourceIndexer(db).search("puente")[0]["snippet"] != ""


def test_subject_filter(tmp_path):
    svc, db = _svc(tmp_path)
    r1, _, _ = _seed(svc)
    assert [h["stable_id"] for h in
            FtsResourceIndexer(db).search("puente", subject="subject:sdm")] == [r1.stable_id]
    assert FtsResourceIndexer(db).search("puente", subject="subject:fis")[0]["kind"] == "html"


def test_rebuild_is_deterministic(tmp_path):
    svc, db = _svc(tmp_path)
    _seed(svc)
    before = FtsResourceIndexer(db).search("puente")
    FtsResourceIndexer(db).clear()
    assert FtsResourceIndexer(db).search("puente") == []
    assert svc.reindex() == 3
    after = FtsResourceIndexer(db).search("puente")
    # Same functional result set (FTS5 rank ties may order rowids differently
    # after rebuild; canonical ids/kinds are what the gate pins).
    assert sorted((h["stable_id"], h["kind"]) for h in before) == \
        sorted((h["stable_id"], h["kind"]) for h in after)
    # Canonical layer untouched by the whole drop/rebuild cycle.
    assert len(SqliteResourceRecords(db).all_ids()) == 3
