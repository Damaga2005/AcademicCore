# SPDX-License-Identifier: MIT
"""F4.1 M3/M9 — Gestion-Academica migration: dry-run, snapshot, apply,
post-validation, idempotency, determinism, cancellation, safety.

Source DB = REAL Gestion schema (fixtures/gestion/schema.sql) + synthetic
rows covering all 29 tables (gestion_legacy_fixture.py).
"""
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

import gestion_legacy_fixture as G
from academic_core.application import AcademicApp
from academic_core.application.gestion_migration import MigrationOptions
from academic_core.config import Settings
from academic_core.errors import MigrationError

SRC = Path(__file__).resolve().parents[1] / "src"


def _app(tmp_path, tag="data"):
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / tag)
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    return core


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _db_digest(core) -> str:
    """Content digest of every table of the target (order-independent)."""
    cx = sqlite3.connect(core.db.path)
    h = hashlib.sha256()
    tables = [r[0] for r in cx.execute("SELECT name FROM sqlite_master WHERE type='table'"
                                       " AND name NOT LIKE 'sqlite_%' AND name NOT LIKE"
                                       " 'resources_fts%' ORDER BY name")]
    for t in tables:
        rows = sorted(repr(r) for r in cx.execute(f'SELECT * FROM "{t}"'))
        h.update(f"{t}:{len(rows)}:{'|'.join(rows)}".encode())
    cx.close()
    return h.hexdigest()


@pytest.fixture
def legacy(tmp_path):
    return G.build(tmp_path / "legacy")


def _opts(root, **kw):
    return MigrationOptions(documents_dir=str(root), degree_total_credits="240",
                            final_project_names=("Trabajo de Fin de Grado",), **kw)


# ------------------------------------------------------------------ dry-run

def test_dry_run_writes_nothing_and_reports_everything(tmp_path, legacy):
    db, root = legacy
    core = _app(tmp_path)
    before, src_sha = _db_digest(core), _sha(db)
    rep = core.migration.dry_run(db, _opts(root))
    assert _db_digest(core) == before and _sha(db) == src_sha
    assert rep.mode == "dry-run" and rep.lossless and rep.source_revision == "e5a7c9b1d3f4"
    assert {t: c["source"] for t, c in rep.counts.items()} == G.TOTAL_ROWS
    assert sorted(rep.errors) == ["documento#5: file missing under documents_dir",
                                  "documento#6: unsafe path refused: parent traversal refused"]
    assert rep.evaluation_check["mismatches"] == 0
    assert rep.evaluation_check["subjects_checked"] == 6
    assert any("codigo.zip" in w and "opaque" in w for w in rep.warnings)


@pytest.mark.parametrize("content,code", [(b"not sqlite at all", "AC-MIG-002"),
                                          (None, "AC-MIG-003")])
def test_invalid_sources_rejected(tmp_path, content, code):
    core = _app(tmp_path)
    p = tmp_path / "x.db"
    if content is None:  # valid SQLite, not a Gestion DB
        sqlite3.connect(p).execute("CREATE TABLE t(x)").connection.commit()
    else:
        p.write_bytes(content)
    with pytest.raises(MigrationError) as e:
        core.migration.dry_run(p)
    assert e.value.code == code


def test_unknown_revision_rejected(tmp_path, legacy):
    db, _ = legacy
    cx = sqlite3.connect(db)
    cx.execute("UPDATE alembic_version SET version_num='ffffffffffff'")
    cx.commit()
    cx.close()
    with pytest.raises(MigrationError) as e:
        _app(tmp_path).migration.dry_run(db)
    assert e.value.code == "AC-MIG-003"


def test_apply_requires_snapshot(tmp_path, legacy):
    db, root = legacy
    with pytest.raises(MigrationError) as e:
        _app(tmp_path).migration.apply(db, _opts(root), snapshot_dir=None)
    assert e.value.code == "AC-MIG-004"


# ------------------------------------------------------------------ apply

@pytest.fixture
def migrated(tmp_path, legacy):
    db, root = legacy
    core = _app(tmp_path)
    src_sha = _sha(db)
    rep = core.migration.apply(db, _opts(root), snapshot_dir=tmp_path / "snap")
    assert _sha(db) == src_sha, "legacy database must never be modified"
    return core, rep, db, root, tmp_path


def test_apply_is_lossless_and_validated(migrated):
    core, rep, *_ = migrated
    assert rep.lossless and rep.validation_failures == []
    for t, c in rep.counts.items():
        assert c["migrated"] + c["preserved"] + c["already_migrated"] == c["source"], t
    snap = Path(rep.snapshot["path"])
    assert snap.is_file() and _sha(snap) == rep.snapshot["sha256"]
    runs = core.migration.legacy.runs("gestion-academica")
    assert len(runs) == 1 and runs[0]["report_digest"] == rep.digest


def test_hierarchy_statuses_and_home(migrated):
    core, *_ = migrated
    subjects = {s.acronym or s.name: s for s in core.academic.all_subjects()}
    assert len(subjects) == 6
    dd = subjects["DD"]
    assert (dd.stable_id, dd.state, dd.course, dd.term_id) == (
        "subject:dd", "cursando", 1, "term:gestion-q2")
    assert dd.virtual_classroom == "https://aula.example.edu/dd"
    assert dd.extra["legacy_contact"]["correo_profesor"] == "lc@example.edu"
    assert subjects["AL"].final_grade == "7.25"
    assert subjects["Física"].stable_id == "subject:fisica"
    assert subjects["OX"].catalog_origin and subjects["OX"].state == "no_elegida"
    home = core.career.home(date(2026, 9, 23))
    assert home.current_term_ids == ("term:gestion-q2", "term:gestion-q3")
    assert [s.acronym for s in home.current_subjects] == ["DD", "SS"]
    assert home.progress.total_credits == Decimal(240)
    assert home.progress.final_project.total == Decimal(12)
    career = core.career.career()
    assert [s.acronym for s in career.partition.approved] == ["AL"]
    assert [s.name for s in career.partition.failed] == ["Física"]
    assert career.target.target == Decimal("7.5")
    assert core.academic.prerequisites_of("subject:ss") == ["subject:al"]


def test_people_evaluation_and_relations(migrated):
    core, rep, *_ = migrated
    staff = core.academic.staff_of("subject:dd")
    assert [(p.stable_id, l.role, l.order) for p, l in staff] == [
        ("professor:ana-perez", "Responsable", 0), ("professor:luis-gil", "docente", 1)]
    assert [p.stable_id for p, _ in core.academic.staff_of("subject:ss")] == [
        "professor:ana-perez"]  # homonym = one identity, two links
    kept = core.migration.legacy.payloads("gestion-academica", "profesor")
    assert [p["source_id"] for p in kept] == ["4"]  # duplicate link preserved verbatim
    detail = core.career.course("subject:dd")
    assert [s.name for s in detail.schemes] == ["Continua", "Solo final"]
    lab = detail.schemes[0].blocks[0]
    assert (lab.name, lab.weight, len(lab.components)) == ("Laboratorio", Decimal(40), 2)
    assert detail.evaluation.state == "suspendida" and detail.evaluation.min_grade_violated
    assert detail.evaluation.grade == Decimal("6.3333")  # .3*6.5+.3*3.5+.4*8.3333
    assert [x.provider for x in detail.external_resources] == ["wuolah", "studocu"]
    assert rep.evaluation_check == {"subjects_checked": 6, "mismatches": 0, "diffs": []}


def test_documents_cas_provenance_fts_and_dedup(migrated):
    core, rep, db, root, _ = migrated
    docs = core.material.documents("subject:dd")
    by_name = {d.filename: d for d in docs}
    assert set(by_name) == {"tema1.pdf", "notas.txt", "codigo.zip"}
    tema = by_name["tema1.pdf"]
    assert tema.category == "teoria" and tema.tags == ("vhdl", "fsm")
    assert tema.legacy["apartado"] == "Teoría" and tema.group_id.startswith("docgroup:dd:grp:")
    res = core.records.get(tema.resource_id)
    cur = res.current()
    assert cur.content_hash == hashlib.sha256(G.PDF).hexdigest()
    assert core.blobs.get_bytes(cur.content_hash) == G.PDF
    assert cur.provenance.origin == "migration"
    assert cur.provenance.source == "gestion-academica:documento/1"
    # same bytes in another subject -> same resource, two relations, no copy
    ss = core.material.documents("subject:ss")
    assert [d.resource_id for d in ss] == [tema.resource_id]
    assert sorted(core.course_material.subjects_of_resource(tema.resource_id)) == [
        "subject:dd", "subject:ss"]
    dup = core.migration.legacy.payloads("gestion-academica", "documento")
    assert {p["source_id"]: p["target_id"] for p in dup}["4"] == tema.resource_id
    # opaque zip: stored, never extracted
    z = core.records.get(by_name["codigo.zip"].resource_id).current()
    assert z.provenance.extraction_status == "deferred"
    assert core.records.get(by_name["codigo.zip"].resource_id).kind == "file"
    # progress + pages + FTS with page deep link
    prog = core.course_material.progress_of(tema.resource_id)
    assert (prog.last_page, prog.percent, prog.total_seconds, prog.sessions) == (3, "42.5", 600, 2)
    assert [n for n, _ in core.course_material.pages_of(tema.resource_id)] == [1, 2]
    hits = [h for h in core.unified_search.search("síntesis") if h.kind == "document"]
    assert {h.ref for h in hits} >= {tema.resource_id}
    assert next(h for h in hits if h.ref == tema.resource_id).page == 2


def test_calendar_spaces_and_personal(migrated):
    core, *_ = migrated
    tasks = {t.title: t for t in core.planning.all_tasks()}
    assert tasks["Tutoría general"].subject_id == ""
    assert tasks["Entrega SS"].end == "23:59" and tasks["Entrega SS"].start == ""
    assert tasks["Inicio sin fin"].start == "" and tasks["Inicio sin fin"].state == "hecha"
    raw = core.migration.legacy.payloads("gestion-academica", "tarea_evento#raw")
    assert [p["source_id"] for p in raw] == ["4"]  # dropped start kept verbatim
    parcial = tasks["Parcial DD"]
    assert (parcial.room, parcial.location, parcial.start, parcial.end) == (
        "A1", "Campus Nord", "09:00", "11:00")
    assert parcial.document_id.startswith("resource:dd:r:")
    sid = core.study_spaces.of_task(parcial.stable_id)
    space = core.material.space(sid)
    assert space["progress"].total == 2 and space["progress"].read == 1
    assert [g.text for g in space["goals"]] == ["Leer tema 1", "Hacer problemas"]
    assert len(space["highlighted"]) == 1
    series = {r["subject_id"]: r for r in core.series.all()}
    assert series["subject:ss"]["interval_weeks"] == 2 and series["subject:ss"]["notes"] == "quincenal"
    assert [m.name for m in core.personal.milestones()] == ["Certificación inglés B2"]
    assert [n.text for n in core.personal.notes()] == ["Revisar tema 3"]
    assert core.personal.concepts("subject:dd")[0].state == "flojo"
    assert core.personal.activity_days() == [date(2026, 9, 10), date(2026, 9, 11)]
    assert core.personal.setting("gestion.tema") == "oscuro"
    deferred = {p["source_table"]: p["deferred_to"]
                for p in core.migration.legacy.payloads("gestion-academica")}
    assert deferred["marcador"] == deferred["anotacion_pdf"] == "F14"
    assert deferred["aviso_descartado"] == "F12"
    assert deferred["busqueda_favorito"] == deferred["busqueda_reciente"] == "F4.2"


def test_rerun_is_idempotent(migrated):
    core, _, db, root, tmp = migrated
    before = _db_digest(core)
    rep = core.migration.apply(db, _opts(root), snapshot_dir=tmp / "snap2")
    assert rep.lossless and rep.validation_failures == []
    assert sum(c["migrated"] for c in rep.counts.values()) == 0
    assert _db_digest(core) != before  # only bookkeeping (migration_runs) grew
    cx = sqlite3.connect(core.db.path)
    n_subjects = cx.execute("SELECT COUNT(*) FROM subjects").fetchone()[0]
    n_resources = cx.execute("SELECT COUNT(*) FROM resources").fetchone()[0]
    assert (n_subjects, n_resources) == (6, 3)


def test_rerun_changes_only_bookkeeping(migrated):
    core, _, db, root, tmp = migrated

    def content():
        cx = sqlite3.connect(core.db.path)
        out = {t: cx.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in (
            "subjects", "terms", "tasks", "resources", "resource_versions", "course_documents",
            "assessment_components", "legacy_map", "legacy_payloads", "study_space_goals")}
        cx.close()
        return out
    first = content()
    core.migration.apply(db, _opts(root), snapshot_dir=tmp / "snap3")
    assert content() == first


def test_documents_can_be_migrated_in_a_later_run(tmp_path, legacy):
    db, root = legacy
    core = _app(tmp_path)
    r1 = core.migration.apply(db, MigrationOptions(), snapshot_dir=tmp_path / "s1")
    assert r1.lossless and r1.counts["documento"]["preserved"] == 7
    r2 = core.migration.apply(db, MigrationOptions(documents_dir=str(root)),
                              snapshot_dir=tmp_path / "s2")
    assert r2.counts["documento"]["migrated"] == 4 and r2.validation_failures == []
    assert len(core.material.documents("subject:dd")) == 3


def test_existing_subject_ids_are_never_overwritten(tmp_path, legacy):
    from academic_core.domain import entities as E
    db, root = legacy
    core = _app(tmp_path)
    core.academic.add_university(E.University("university:u", "U"))
    core.academic.add_degree(E.Degree("degree:g", "G", "university:u"))
    core.academic.add_year(E.AcademicYear("year:y", "Y", "degree:g"))
    core.academic.add_term(E.Term("term:t", "T", "cuatrimestre", 1, "year:y"))
    core.academic.add_subject(E.Subject("subject:dd", "", "Mine", "DD", term_id="term:t"))
    rep = core.migration.apply(db, _opts(root), snapshot_dir=tmp_path / "s")
    assert rep.validation_failures == []
    assert core.academic.get_subject("subject:dd").name == "Mine"
    assert core.academic.get_subject("subject:dd-2").name == "Diseño Digital"


# ------------------------------------------------------------- cancellation

def test_cancel_during_write_leaves_target_unchanged(tmp_path, legacy):
    db, root = legacy
    core = _app(tmp_path)
    before = _db_digest(core)
    calls = {"n": 0}

    def cancel():
        calls["n"] += 1
        return calls["n"] > 40  # past planning, inside the SQL transaction

    rep = core.migration.apply(db, _opts(root), snapshot_dir=tmp_path / "s", cancel=cancel)
    assert rep.cancelled and not rep.lossless
    assert _db_digest(core) == before


def test_cancel_during_planning(tmp_path, legacy):
    db, root = legacy
    core = _app(tmp_path)
    before = _db_digest(core)
    rep = core.migration.dry_run(db, _opts(root), cancel=lambda: True)
    assert rep.cancelled and _db_digest(core) == before


def test_progress_is_reported(tmp_path, legacy):
    db, root = legacy
    core = _app(tmp_path)
    seen = []
    core.migration.apply(db, _opts(root), snapshot_dir=tmp_path / "s",
                         progress=lambda stage, done, total: seen.append(stage))
    assert {"read", "blobs", "write", "index"} <= set(seen)


# -------------------------------------------------------------- determinism

def test_report_digest_is_reproducible(tmp_path, legacy):
    db, root = legacy
    a = _app(tmp_path, "a").migration.apply(db, _opts(root), snapshot_dir=tmp_path / "sa")
    b = _app(tmp_path, "b").migration.apply(db, _opts(root), snapshot_dir=tmp_path / "sb")
    assert a.digest == b.digest and a.run_id != b.run_id


_SCRIPT = r"""
import json, os, sys
from academic_core.application import AcademicApp
from academic_core.application.gestion_migration import MigrationOptions
from academic_core.config import Settings
core = AcademicApp(Settings.load())
rep = core.migration.apply(sys.argv[1], MigrationOptions(documents_dir=sys.argv[2]),
                           snapshot_dir=sys.argv[3])
ids = sorted(s.stable_id for s in core.academic.all_subjects())
print(json.dumps({"digest": rep.digest, "ids": ids,
                  "res": sorted(core.records.all_ids())}))
"""


def test_migration_is_stable_across_hash_seeds(tmp_path, legacy):
    db, root = legacy
    outs = []
    for seed in ("0", "11", "2024", "random"):
        env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONPATH=str(SRC),
                   ACORE_DATA_DIR=str(tmp_path / f"seed-{seed}"))
        r = subprocess.run([sys.executable, "-c", _SCRIPT, str(db), str(root),
                            str(tmp_path / f"snap-{seed}")], env=env, capture_output=True,
                           text=True, timeout=300, check=True)
        outs.append(json.loads(r.stdout.strip().splitlines()[-1]))
    assert all(o == outs[0] for o in outs)
