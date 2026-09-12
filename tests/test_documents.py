"""Document service: Resource(+Version) -> stored derivation + provenance."""
from academic_core.application.documents import DocumentService
from academic_core.application.ingest import IngestionService
from academic_core.domain import entities as E
from academic_core.infrastructure import (
    AcademicRepository, Database, FileBlobStore, FtsResourceIndexer,
    PlanningRepository, SqliteResourceRecords,
)


def _stack(tmp_path):
    db = Database(tmp_path / "a.db")
    ac = AcademicRepository(db)
    ac.add_university(E.University("university:u", "U"))
    blobs = FileBlobStore(tmp_path / "cas")
    recs = SqliteResourceRecords(db)
    ingest = IngestionService(blobs, recs, FtsResourceIndexer(db), ac,
                              PlanningRepository(db))
    return DocumentService(blobs, recs, db), ingest


def test_html_build_lists_and_provenance(tmp_path):
    docs, ingest = _stack(tmp_path)
    f = tmp_path / "t.html"
    f.write_text("<html><head><title>T</title></head><body><h1>H</h1><p>x</p></body></html>",
                 encoding="utf-8")
    rep = ingest.import_file(f)
    summary = docs.build(rep.stable_id)
    assert summary["parser"] == "html-parser" and summary["blocks"] == 2
    got = docs.get(rep.stable_id, 1, "html-parser")
    assert got.meta.title == "T"
    assert got.history[0]["parser"] == "html-parser"  # transformation chain
    rows = docs.list(rep.stable_id)
    assert rows[0]["resource_version"] == 1 and rows[0]["parser"] == "html-parser"


def test_markdown_build_and_reparse_stable(tmp_path):
    docs, ingest = _stack(tmp_path)
    f = tmp_path / "n.md"
    f.write_text("# N\n\ncuerpo", encoding="utf-8")
    rep = ingest.import_file(f)
    docs.build(rep.stable_id)
    assert docs.get(rep.stable_id, 1, "markdown-parser").meta.title == "N"


def test_versioned_derivations_coexist(tmp_path):
    docs, ingest = _stack(tmp_path)
    f = tmp_path / "v.md"
    f.write_text("# v1", encoding="utf-8")
    r1 = ingest.import_file(f)
    f.write_text("# v2", encoding="utf-8")
    ingest.import_file(f)
    docs.build(r1.stable_id, version=1)
    docs.build(r1.stable_id, version=2)
    assert len(docs.list(r1.stable_id)) == 2
    assert docs.get(r1.stable_id, 1, "markdown-parser").meta.title == "v1"
