"""Security: traversal, malformed input, overwrite, corrupt, ZIP, size caps."""
import pytest

from academic_core.application.ingest import IngestionService, SecurityError
from academic_core.domain import entities as E
from academic_core.infrastructure import (
    AcademicRepository, Database, FileBlobStore, FtsResourceIndexer,
    PlanningRepository, SqliteResourceRecords,
)
from academic_core.infrastructure.cas import TooLarge
from academic_core.resources.adapters import UnsupportedType


def _svc(tmp_path, max_bytes=1 << 20):
    db = Database(tmp_path / "a.db")
    ac = AcademicRepository(db)
    ac.add_university(E.University("university:u", "U"))
    return IngestionService(FileBlobStore(tmp_path / "cas"), SqliteResourceRecords(db),
                            FtsResourceIndexer(db), ac, PlanningRepository(db),
                            max_bytes=max_bytes), db


def test_traversal_refused(tmp_path):
    svc, _ = _svc(tmp_path)
    with pytest.raises((SecurityError, FileNotFoundError)):
        svc.import_file(tmp_path / ".." / ".." / "secret.md")
    with pytest.raises(SecurityError):
        svc.import_bytes(b"x", "a\x00b.md")


def test_zip_refused_as_boundary(tmp_path):
    svc, db = _svc(tmp_path)
    z = tmp_path / "pack.zip"
    z.write_bytes(b"PK\x03\x04" + b"\x00" * 100)
    with pytest.raises(UnsupportedType):
        svc.import_file(z)
    assert SqliteResourceRecords(db).all_ids() == []  # nothing persisted


def test_oversize_rejected(tmp_path):
    svc, db = _svc(tmp_path, max_bytes=16)
    big = tmp_path / "big.txt"
    big.write_bytes(b"y" * 64)
    with pytest.raises(TooLarge):
        svc.import_file(big)
    with pytest.raises(TooLarge):
        svc.import_bytes(b"y" * 64, "big.txt")
    assert SqliteResourceRecords(db).all_ids() == []


def test_no_silent_overwrite(tmp_path):
    svc, db = _svc(tmp_path)
    f = tmp_path / "doc.txt"
    f.write_bytes(b"original-bytes")
    r1 = svc.import_file(f)
    f.write_bytes(b"changed-bytes!")
    r2 = svc.import_file(f)
    rec = SqliteResourceRecords(db).get(r1.stable_id)
    assert r2.version == 2
    assert FileBlobStore(tmp_path / "cas").get_bytes(rec.versions[0].content_hash) == b"original-bytes"


def test_corrupt_pdf_does_not_break_pipeline(tmp_path):
    svc, db = _svc(tmp_path)
    f = tmp_path / "bad.pdf"
    f.write_bytes(b"%PDF-1.4 \xff\xfe broken")
    rep = svc.import_file(f)
    assert rep.extraction_status in ("ok", "failed", "deferred")
    assert SqliteResourceRecords(db).get(rep.stable_id) is not None


def test_missing_file(tmp_path):
    svc, _ = _svc(tmp_path)
    with pytest.raises(FileNotFoundError):
        svc.import_file(tmp_path / "nope.md")


def test_url_needs_explicit_adapter(tmp_path):
    svc, _ = _svc(tmp_path)
    with pytest.raises(UnsupportedType):
        svc.import_bytes(b"<p>x</p>", "http://evil/x.html", origin="url")
