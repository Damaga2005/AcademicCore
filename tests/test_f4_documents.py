# SPDX-License-Identifier: MIT
"""F4.1 M4/M7 — documents in the subject context (CAS + provenance + FTS),
study-space selection, external links, unified search, backup archive."""
import hashlib
import os
import zipfile
from datetime import date

import pytest

from academic_core.application import AcademicApp
from academic_core.application.backup import ArchiveRejected, BackupService
from academic_core.config import Settings
from academic_core.domain import entities as E
from academic_core.errors import AcademicManagementError
from academic_core.infrastructure import IntegrityError


@pytest.fixture
def core(tmp_path):
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / "data")
    c = AcademicApp(Settings.load())
    c.settings.ensure_dirs()
    ac = c.academic
    ac.add_university(E.University("university:u", "U"))
    ac.add_degree(E.Degree("degree:g", "G", "university:u"))
    ac.add_year(E.AcademicYear("year:y1", "Y1", "degree:g"))
    ac.add_term(E.Term("term:q1", "Q1", "cuatrimestre", 1, "year:y1", state="actual"))
    c.svc.create_subject("Diseño Digital", "term:q1", acronym="DD")
    c.svc.create_subject("Señales", "term:q1", acronym="SS")
    return c


MD = "# Máquinas de estados\n\nUna **FSM**: modelo con estados y transiciones.\n".encode()


def test_add_document_goes_through_cas_with_provenance(core):
    d = core.material.add_document("subject:dd", MD, "fsm.md", category="apuntes",
                                   tags=("fsm",))
    res = core.records.get(d.resource_id)
    cur = res.current()
    assert cur.content_hash == hashlib.sha256(MD).hexdigest()
    assert core.blobs.get_bytes(cur.content_hash) == MD
    assert cur.provenance.original_filename == "fsm.md" and res.kind == "markdown"
    assert core.material.documents("subject:dd", "apuntes")[0].tags == ("fsm",)
    assert [r.resource_id for r in core.planning.refs_of("subject:dd")] == [d.resource_id]
    # same bytes again -> deduplicated, same resource, no second document
    d2 = core.material.add_document("subject:dd", MD, "copia.md", category="apuntes")
    assert d2.resource_id == d.resource_id
    assert len(core.material.documents("subject:dd")) == 1


def test_same_resource_in_two_subjects_and_move(core):
    d = core.material.add_document("subject:dd", MD, "fsm.md", category="teoria")
    core.material.link("subject:ss", d.resource_id, category="otros", filename="fsm.md")
    assert sorted(core.course_material.subjects_of_resource(d.resource_id)) == [
        "subject:dd", "subject:ss"]
    h = core.records.get(d.resource_id).current().content_hash
    core.course_material.unlink("subject:ss", d.resource_id)
    moved = core.material.move(d.resource_id, "subject:dd", "subject:ss", category="apuntes")
    assert moved.subject_id == "subject:ss" and moved.category == "apuntes"
    assert core.material.documents("subject:dd") == []
    assert core.records.get(d.resource_id).current().content_hash == h  # bytes untouched
    with pytest.raises(AcademicManagementError):
        core.material.move(d.resource_id, "subject:dd", "subject:ss")


def test_groups_are_unique_per_category_and_guarded(core):
    g = core.material.create_group("subject:dd", "teoria", "Tema  1")
    with pytest.raises(IntegrityError):
        core.material.create_group("subject:dd", "teoria", "Tema 1")
    core.material.create_group("subject:dd", "examenes", "Tema 1")  # other category ok
    d = core.material.add_document("subject:dd", MD, "fsm.md", category="teoria",
                                   group_id=g.stable_id)
    assert d.group_id == g.stable_id
    with pytest.raises(IntegrityError):
        core.course_material.delete_group(g.stable_id)
    with pytest.raises(IntegrityError):
        core.material.link("subject:ss", d.resource_id, group_id=g.stable_id)
    with pytest.raises(AcademicManagementError):
        core.material.create_group("subject:dd", "musica", "x")


def test_link_requires_existing_resource_and_subject(core):
    with pytest.raises(IntegrityError):
        core.material.link("subject:dd", "resource:dd:r:09999")
    with pytest.raises(AcademicManagementError):
        core.material.link("subject:nope", "resource:dd:r:00001")


def test_study_space_selection_progress(core):
    d = core.material.add_document("subject:dd", MD, "fsm.md", category="teoria")
    r = core.calendar.create_task("Parcial", date(2026, 10, 20), subject_id="subject:dd",
                                  kind="examen_parcial")
    sid = r.study_space_id
    assert sid and core.material.ensure_space(r.task.stable_id) == sid  # idempotent
    core.material.select_for_space(sid, d.resource_id, "teoria", highlighted=True)
    core.material.set_goals(sid, [("Leer FSM", False), ("Problemas", True)])
    core.material.mark_read(sid, d.resource_id)
    sp = core.material.space(sid)
    assert sp["progress"].percent == 100 and sp["progress"].goals_done == 1
    assert [x.resource_id for x in sp["highlighted"]] == [d.resource_id]
    with pytest.raises(AcademicManagementError):
        core.material.select_for_space(sid, d.resource_id, "cocina")
    with pytest.raises(IntegrityError):
        core.material.select_for_space(sid, "resource:dd:r:09999")


def test_reading_progress_accumulates(core):
    d = core.material.add_document("subject:dd", MD, "fsm.md")
    core.material.record_reading(d.resource_id, page=2, percent="10", seconds=60,
                                 when="2026-09-20T10:00:00+00:00")
    p = core.material.record_reading(d.resource_id, page=5, seconds=30,
                                     when="2026-09-21T10:00:00+00:00")
    assert (p.last_page, p.percent, p.total_seconds, p.sessions) == (5, "10", 90, 2)
    assert p.first_opened.startswith("2026-09-20") and p.last_opened.startswith("2026-09-21")
    assert core.course_material.recent(5)[0].resource_id == d.resource_id


def test_external_resources_are_validated_never_fetched(core, monkeypatch):
    import socket

    def boom(*a, **k):  # any network use during the call fails the test
        raise AssertionError("network used")
    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr(socket.socket, "connect", boom)
    x = core.material.add_external_resource("subject:dd", "Studocu",
                                            "https://www.studocu.com/es/course/x/1")
    assert x.provider == "studocu" and x.provenance == {"origin": "manual"}
    for bad in ("file:///etc/passwd", "http://127.0.0.1:22/\nX", "javascript:alert(1)"):
        with pytest.raises(AcademicManagementError):
            core.material.add_external_resource("subject:dd", "x", bad)


def test_unified_search_reuses_fts_and_entities(core):
    d = core.material.add_document("subject:dd", MD, "fsm.md")
    core.academic.add_professor(E.Professor("professor:ana-perez", "Ana Pérez"))
    core.academic.attach_staff(E.SubjectStaff("subject:dd", "professor:ana-perez"))
    core.plans.add_note("pensar en transiciones")
    kinds = {h.kind: h for h in core.unified_search.search("transiciones")}
    assert kinds["document"].ref == d.resource_id and kinds["document"].subject_id == "subject:dd"
    assert "note" in kinds
    assert [h.ref for h in core.unified_search.search("perez")] == ["professor:ana-perez"]
    assert [h.ref for h in core.unified_search.search("DISENO")] == ["subject:dd"]
    assert core.unified_search.search("x") == []  # too short
    only_ss = core.unified_search.search("transiciones", subject_id="subject:ss")
    assert [h for h in only_ss if h.kind == "document"] == []
    # legacy SimpleSearchService was broken on any non-empty query; fixed in F4.1
    assert [h.ref for h in core.search.search("señales")] == ["subject:ss"]


# ------------------------------------------------------------------ backup

def test_backup_snapshot_and_zip_roundtrip(core, tmp_path):
    core.material.add_document("subject:dd", MD, "fsm.md")
    rep = core.backup.backup(tmp_path / "b")
    assert hashlib.sha256(open(rep.path, "rb").read()).hexdigest() == rep.sha256
    arc = core.backup.export_zip(tmp_path / "a.zip", cas_root=core.blobs.root)
    info = BackupService.verify_zip(arc.path)
    assert info["blobs"] == 1 and info["db_sha256"] == arc.db_sha256


def _zip(path, members: dict, *, symlink: str | None = None):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
        if symlink:
            zi = zipfile.ZipInfo(symlink)
            zi.external_attr = 0o120777 << 16
            zf.writestr(zi, "/etc/passwd")
    return path


@pytest.mark.parametrize("members,kw", [
    ({"../evil.txt": "x"}, {}),
    ({"/abs.txt": "x"}, {}),
    ({"C:/win.txt": "x"}, {}),
    ({"a\\..\\b.txt": "x"}, {}),
    ({"manifest.json": "{}", "academic.db": "x"}, {"symlink": "link"}),
    ({"bomb.txt": "0" * 2_000_000}, {}),
])
def test_zip_slip_bomb_symlink_rejected(tmp_path, members, kw):
    p = _zip(tmp_path / "bad.zip", members, **kw)
    with pytest.raises(ArchiveRejected) as e:
        BackupService.verify_zip(p)
    assert e.value.code == "AC-SEC-003"


def test_zip_member_limits_and_tamper(core, tmp_path):
    arc = core.backup.export_zip(tmp_path / "a.zip", cas_root=core.blobs.root)
    with pytest.raises(ArchiveRejected):
        BackupService.verify_zip(arc.path, max_members=1)
    with pytest.raises(ArchiveRejected):
        BackupService.verify_zip(arc.path, max_total_bytes=10)
    tampered = tmp_path / "t.zip"
    with zipfile.ZipFile(arc.path) as src, zipfile.ZipFile(tampered, "w") as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == "academic.db":
                data = data[:-1] + bytes([data[-1] ^ 1])
            dst.writestr(info.filename, data)
    with pytest.raises(ArchiveRejected):
        BackupService.verify_zip(tampered)
    (tmp_path / "junk.zip").write_bytes(b"not a zip")
    with pytest.raises(ArchiveRejected):
        BackupService.verify_zip(tmp_path / "junk.zip")


def test_fts_subject_filter_never_drops_valid_hits(core):
    """F4.1: filters run in SQL; the former limit*3 pre-fetch could return
    fewer hits than exist when many other subjects matched first."""
    for i in range(40):
        core.material.add_document("subject:dd", f"transiciones dd {i}".encode(), f"dd{i}.txt")
    for i in range(4):
        core.material.add_document("subject:ss", f"transiciones ss {i}".encode(), f"ss{i}.txt")
    hits = core.fts.search("transiciones", subject="subject:ss", limit=4)
    assert len(hits) == 4 and all(h["title"].startswith("ss") for h in hits)
    assert len(core.fts.search("transiciones", kind="text", limit=50)) == 44
