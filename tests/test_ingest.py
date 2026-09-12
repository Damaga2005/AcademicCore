"""Ingestion pipeline: import, idempotent dupes, versions, rollback, links."""
from datetime import date

import pytest

from academic_core.application.ingest import IngestionService
from academic_core.domain import entities as E
from academic_core.infrastructure import (
    AcademicRepository, Database, FileBlobStore, FtsResourceIndexer,
    PlanningRepository, SqliteResourceRecords, StudyRepository,
)
from academic_core.resources.adapters import UnsupportedType


def _stack(tmp_path, max_bytes=10 << 20):
    db = Database(tmp_path / "a.db")
    ac, pl = AcademicRepository(db), PlanningRepository(db)
    ac.add_university(E.University("university:u", "U"))
    ac.add_degree(E.Degree("degree:g", "G", "university:u"))
    ac.add_year(E.AcademicYear("year:2025-26", "2025-26", "degree:g"))
    ac.add_term(E.Term("term:c1", "C1", "cuatrimestre", 1, "year:2025-26"))
    ac.add_subject(E.Subject("subject:sdm", "230", "Sistemes", "SDM", term_id="term:c1"))
    svc = IngestionService(FileBlobStore(tmp_path / "cas"),
                           SqliteResourceRecords(db), FtsResourceIndexer(db),
                           ac, pl, max_bytes=max_bytes)
    return svc, ac, pl, db


def test_import_and_duplicate_is_idempotent(tmp_path):
    svc, _, _, db = _stack(tmp_path)
    f = tmp_path / "tema.md"
    f.write_text("# Tema 1\n\nContenido", encoding="utf-8")
    r1 = svc.import_file(f, subject_id="subject:sdm")
    assert (r1.outcome, r1.version) == ("imported", 1)
    r2 = svc.import_file(f, subject_id="subject:sdm")
    assert r2.outcome == "duplicate" and r2.stable_id == r1.stable_id
    res = SqliteResourceRecords(db).get(r1.stable_id)
    assert len(res.versions) == 1  # no artificial version
    assert FileBlobStore(tmp_path / "cas").exists(r1.content_hash)


def test_modified_content_new_version_history_kept(tmp_path):
    svc, _, _, db = _stack(tmp_path)
    f = tmp_path / "tema.md"
    f.write_text("v1", encoding="utf-8")
    r1 = svc.import_file(f)
    f.write_text("v2 extended", encoding="utf-8")
    r2 = svc.import_file(f)
    assert (r2.outcome, r2.stable_id, r2.version) == ("new_version", r1.stable_id, 2)
    res = SqliteResourceRecords(db).get(r1.stable_id)
    assert [v.version for v in res.versions] == [1, 2]
    assert res.current().content_hash == r2.content_hash
    assert res.versions[0].content_hash == r1.content_hash  # history intact


def test_same_bytes_different_path_is_duplicate(tmp_path):
    svc, _, _, _ = _stack(tmp_path)
    a, b = tmp_path / "a.md", tmp_path / "sub"
    b.mkdir()
    c = b / "b.md"
    a.write_text("identical", encoding="utf-8")
    c.write_text("identical", encoding="utf-8")
    assert svc.import_file(a).stable_id == svc.import_file(c).stable_id


def test_import_links_subject_reference(tmp_path):
    svc, _, pl, _ = _stack(tmp_path)
    f = tmp_path / "x.txt"
    f.write_text("hello", encoding="utf-8")
    rep = svc.import_file(f, subject_id="subject:sdm")
    assert [r.resource_id for r in pl.refs_of("subject:sdm")] == [rep.stable_id]


def test_failed_import_leaves_no_records(tmp_path):
    svc, _, _, db = _stack(tmp_path)
    z = tmp_path / "evil.zip"
    z.write_bytes(b"PK\x03\x04 fake")
    with pytest.raises(UnsupportedType):
        svc.import_file(z)
    assert SqliteResourceRecords(db).all_ids() == []


def test_explicit_resource_id_versioning(tmp_path):
    svc, _, _, db = _stack(tmp_path)
    r1 = svc.import_bytes(b"one", "n.txt", origin="manual")
    r2 = svc.import_bytes(b"two", "n.txt", origin="manual", resource_id=r1.stable_id)
    assert r2.outcome == "new_version"
    assert len(SqliteResourceRecords(db).get(r1.stable_id).versions) == 2


def test_reindex_preserves_identity(tmp_path):
    svc, _, _, db = _stack(tmp_path)
    f = tmp_path / "t.md"
    f.write_text("# T\n\ncuerpo-indexable-xyz", encoding="utf-8")
    rep = svc.import_file(f)
    n = svc.reindex()
    assert n == 1
    res = SqliteResourceRecords(db).get(rep.stable_id)
    assert res.current().content_hash == rep.content_hash
    assert FtsResourceIndexer(db).search("cuerpo-indexable-xyz")[0]["stable_id"] == rep.stable_id
