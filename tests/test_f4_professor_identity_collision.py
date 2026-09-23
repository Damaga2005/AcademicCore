# SPDX-License-Identifier: MIT
"""F4.1 closure — same name is never the same person without evidence.

A Gestion `profesor` row belongs to one subject. Rows are merged into one
Professor ONLY with evidence (same normalized name AND same non-empty
e-mail); otherwise every row keeps its own identity derived from its stable
Gestion id. Existing AcademicCore professors are never reused by name alone.
"""
import os
import sqlite3

import pytest

import gestion_legacy_fixture as G
from academic_core.application import AcademicApp
from academic_core.application.gestion_migration import MigrationOptions
from academic_core.config import Settings
from academic_core.domain import entities as E


def _app(tmp_path, tag="data"):
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / tag)
    return AcademicApp(Settings.load())


def _legacy(tmp_path, profs):
    db, root = G.build(tmp_path / "legacy", docs=False)
    cx = sqlite3.connect(db)
    cx.execute("DELETE FROM profesor")
    for i, (subj, name, email) in enumerate(profs, start=101):
        cx.execute("INSERT INTO profesor(id, asignatura_id, nombre, correo, orden)"
                   " VALUES (?,?,?,?,0)", (i, subj, name, email))
    cx.commit()
    cx.close()
    return db


def _ids(core, subject):
    return [p.stable_id for p, _ in core.academic.staff_of(subject)]


def test_f4_professor_identity_collision(tmp_path):
    db = _legacy(tmp_path, [
        (2, "Juan Pérez", None),                 # DD: person A (no evidence)
        (3, "Juan Pérez", None),                 # SS: same name, NOT merged
        (2, "María López", "m.lopez@x.edu"),     # DD
        (3, "María  López", "M.Lopez@x.edu"),    # SS: same name+email -> merged
        (4, "María López", "otra@x.edu"),        # Física: same name, other email
    ])
    core = _app(tmp_path)
    rep = core.migration.apply(db, MigrationOptions(), snapshot_dir=tmp_path / "s")
    assert rep.lossless and rep.validation_failures == []
    assert _ids(core, "subject:dd") == ["professor:juan-perez", "professor:maria-lopez"]
    assert _ids(core, "subject:ss") == ["professor:juan-perez-g102", "professor:maria-lopez"]
    assert _ids(core, "subject:fisica") == ["professor:maria-lopez-g105"]
    assert len(core.academic.all_professors()) == 4
    assert rep.professor_identity == {
        "source_rows": 5, "identities": 4, "merged_by_email_evidence": 1,
        "homonym_rows_kept_separate": 2, "names_with_several_identities": 2}
    # reversible: every source row maps to exactly one identity
    mapped = core.migration.legacy.all_mapped("gestion-academica")
    assert {k[1]: v for k, v in mapped.items() if k[0] == "profesor"} == {
        "101": "professor:juan-perez", "102": "professor:juan-perez-g102",
        "103": "professor:maria-lopez", "104": "professor:maria-lopez",
        "105": "professor:maria-lopez-g105"}


def test_existing_professor_is_not_reused_by_name(tmp_path):
    db = _legacy(tmp_path, [(2, "Juan Pérez", None), (3, "Ana Ruiz", "ana@x.edu")])
    core = _app(tmp_path)
    core.academic.add_professor(E.Professor("professor:juan-perez", "Juan Pérez"))
    core.academic.add_professor(E.Professor("professor:ana-ruiz", "Ana Ruiz", "ana@x.edu"))
    rep = core.migration.apply(db, MigrationOptions(), snapshot_dir=tmp_path / "s")
    assert rep.validation_failures == []
    assert _ids(core, "subject:dd") == ["professor:juan-perez-g101"]  # no evidence
    assert _ids(core, "subject:ss") == ["professor:ana-ruiz"]  # e-mail evidence


def test_identity_is_stable_across_reruns(tmp_path):
    db = _legacy(tmp_path, [(2, "Juan Pérez", None), (3, "Juan Pérez", None)])
    core = _app(tmp_path)
    core.migration.apply(db, MigrationOptions(), snapshot_dir=tmp_path / "s1")
    before = sorted(p.stable_id for p in core.academic.all_professors())
    rep = core.migration.apply(db, MigrationOptions(), snapshot_dir=tmp_path / "s2")
    assert rep.counts["profesor"]["already_migrated"] == 2
    assert sorted(p.stable_id for p in core.academic.all_professors()) == before


def test_syllabus_apply_does_not_merge_homonyms_across_subjects(tmp_path):
    from academic_core.documents.syllabus import ProposedProfessor, SyllabusProposal
    core = _app(tmp_path)
    ac = core.academic
    ac.add_university(E.University("university:u", "U"))
    ac.add_degree(E.Degree("degree:g", "G", "university:u"))
    ac.add_year(E.AcademicYear("year:y", "Y", "degree:g"))
    ac.add_term(E.Term("term:t", "T", "cuatrimestre", 1, "year:y"))
    core.svc.create_subject("A", "term:t", acronym="A")
    core.svc.create_subject("B", "term:t", acronym="B")
    prop = SyllabusProposal((ProposedProfessor("Juan Pérez", ""),), ())
    core.knowledge.apply_syllabus("subject:a", prop, confirmed=True)
    core.knowledge.apply_syllabus("subject:b", prop, confirmed=True)
    a, b = _ids(core, "subject:a"), _ids(core, "subject:b")
    assert a == ["professor:juan-perez"] and b != a and len(b) == 1
    core.knowledge.apply_syllabus("subject:a", prop, confirmed=True)  # idempotent
    assert _ids(core, "subject:a") == a
