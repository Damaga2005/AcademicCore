# SPDX-License-Identifier: MIT
"""F9 correction contracts: deterministic grading over D6/D7 + evidence.

Covers prompt sections 18-19: attempt lifecycle, snapshots, every D6
type, scoring policies, evidence/provenance/digest, persistence +
rollback, determinism, security. D5/D6/D7 regression runs in the gate
suite (no duplicate coverage here).
"""

from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from academic_core.application.assessment import AssessmentService
from academic_core.application.bank_ingest import BankIngestionService
from academic_core.application.correction import CorrectionService
from academic_core.domain import question_bank as QB
from academic_core.domain import entities as E
from academic_core.domain.assessment import (
    Assessment,
    AssessmentItem,
    GradingPolicy,
)
from academic_core.domain.correction import CORRECTION_ENGINE, correct_answer
from academic_core.errors import AcademicManagementError
from academic_core.infrastructure.academic_store import (
    PersonalRepository,
    QBankRepository,
)
from academic_core.infrastructure.assessment import AssessmentRepository
from academic_core.infrastructure.database import Database
from academic_core.infrastructure.repositories import AcademicRepository

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "academic_core"
NOW = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)
MS = 1758792000000


def _q(n, **kw):
    specs = {
        1: ("multiple_choice", {"options": ["3", "4"], "correct": [1]}),
        2: ("true_false", {"answer": True}),
        3: ("numeric", {"value": "4.0", "unit": "V", "tolerance": "0.1"}),
        4: ("symbolic", {"expression": "x+2", "variables": ["x"]}),
        5: ("short_text", {"expected": "Paris"}),
    }
    t, spec = specs[n]
    d = dict(question_id=f"question:demo:q:{n:05d}", statement=f"S{n}?",
             qtype=t, answer_spec=spec, owner_slug="demo")
    d.update(kw)
    return QB.Question(**d)


def _bank(version=1, n=5):
    return QB.Bank(bank_id="bank:demo", title="Demo",
                   content_version=version,
                   questions=tuple(_q(i + 1) for i in range(n)))


ANS = {
    "i1": {"selected": [1]},
    "i2": {"answer": True},
    "i3": {"value": "4.05", "unit": "V"},
    "i4": {"expression": "2+x"},
    "i5": {"text": "paris"},
}


def _env(tmp_path):
    db = Database(tmp_path / "f9.db")
    ac = AcademicRepository(db)
    ac.add_subject(E.Subject("subject:al", "ALG", "Algebra", "ALG"))
    repo = AssessmentRepository(db)
    qb = QBankRepository(db)
    pe = PersonalRepository(db)
    BankIngestionService(ac, pe, qb).ingest(QB.dumps_bank(_bank()),
                                            now_ms=MS)
    asmt = Assessment(
        stable_id="assessment:al:as:00001", subject_id="subject:al",
        title="T",
        items=tuple(AssessmentItem(f"i{i}", f"question:demo:q:{i:05d}",
                                   "topic:al:t01", Decimal("2.0"))
                    for i in range(1, 6)),
        attempts_allowed=2, policy=GradingPolicy())
    repo.save_assessment(asmt)
    svc = CorrectionService(repo, qb)
    return db, svc, asmt, repo, qb


def _attempt(svc, asmt, answers=ANS, now=NOW):
    sess = svc.create_attempt(asmt, "stu1")
    svc.prepare(sess.stable_id, asmt)
    svc.sessions.start_session(sess.stable_id, now)
    return svc.submit_with_correction(sess.stable_id, asmt, dict(answers),
                                      now)


# -- lifecycle ---------------------------------------------------------------

def test_full_lifecycle_scores_and_evidences(tmp_path):
    _, svc, asmt, repo, _ = _env(tmp_path)
    done = _attempt(svc, asmt)
    assert done.status.value == "SUBMITTED"
    assert done.result.total_score == Decimal("10.00")
    assert done.result.percentage == Decimal("100.00")
    assert done.result.passed is True
    ev = repo.get_evidence(done.stable_id)
    assert sorted(r["reason"] for r in ev) == [
        "boolean_match", "selected_match", "symbolic_equivalent",
        "text_match", "tolerance_match"]
    assert all(r["engine"] == CORRECTION_ENGINE for r in ev)


def test_attempts_allowed_enforced_and_cancel_frees(tmp_path):
    _, svc, asmt, _, _ = _env(tmp_path)
    s1 = svc.create_attempt(asmt, "stu1")
    assert s1.attempt_number == 1
    s2 = svc.create_attempt(asmt, "stu1")
    assert s2.attempt_number == 2
    with pytest.raises(AcademicManagementError) as e:
        svc.create_attempt(asmt, "stu1")
    assert e.value.code == "AC-ACD-003"
    svc.sessions.cancel_session(s2.stable_id)
    s3 = svc.create_attempt(asmt, "stu1")
    assert s3.attempt_number == 2  # cancelled attempts never happened


def test_double_submit_refused_without_mutation(tmp_path):
    _, svc, asmt, repo, _ = _env(tmp_path)
    done = _attempt(svc, asmt)
    before = repo.get_result(done.stable_id).total_score
    with pytest.raises(AcademicManagementError) as e:
        svc.submit_with_correction(done.stable_id, asmt, dict(ANS), NOW)
    assert e.value.code == "AC-ACD-003"
    assert repo.get_result(done.stable_id).total_score == before


def test_unprepared_submit_rejected(tmp_path):
    _, svc, asmt, _, _ = _env(tmp_path)
    sess = svc.create_attempt(asmt, "stu1")
    svc.sessions.start_session(sess.stable_id, NOW)
    with pytest.raises(AcademicManagementError) as e:
        svc.submit_with_correction(sess.stable_id, asmt, dict(ANS), NOW)
    assert e.value.code == "AC-ACD-002"


def test_unknown_question_at_prepare_rejected(tmp_path):
    db = Database(tmp_path / "u.db")
    ac = AcademicRepository(db)
    ac.add_subject(E.Subject("subject:al", "ALG", "Algebra", "ALG"))
    repo = AssessmentRepository(db)
    svc = CorrectionService(repo, QBankRepository(db))
    asmt = Assessment(stable_id="assessment:al:as:00009",
                      subject_id="subject:al", title="T",
                      items=(AssessmentItem("i1", "question:no:q:00001",
                                            "topic:al:t01", Decimal("1.0")),))
    repo.save_assessment(asmt)
    sess = svc.create_attempt(asmt, "s")
    with pytest.raises(AcademicManagementError) as e:
        svc.prepare(sess.stable_id, asmt)
    assert e.value.code == "AC-ACD-002"


# -- snapshot frozen history ----------------------------------------------------

def test_bank_update_after_prepare_does_not_rewrite_history(tmp_path):
    db, svc, asmt, repo, qb = _env(tmp_path)[:5]
    from academic_core.infrastructure.academic_store import PersonalRepository
    pe = PersonalRepository(db)
    ac = AcademicRepository(db)
    sess = svc.create_attempt(asmt, "stu1")
    svc.prepare(sess.stable_id, asmt)
    v2 = _bank(version=2, n=5)
    BankIngestionService(ac, pe, qb).ingest(QB.dumps_bank(v2), now_ms=MS + 1)
    svc.sessions.start_session(sess.stable_id, NOW)
    done = svc.submit_with_correction(sess.stable_id, asmt, dict(ANS), NOW)
    assert done.result.total_score == Decimal("10.00")
    snaps = repo.get_snapshots(sess.stable_id)
    assert snaps[0]["content_version"] == 1


# -- correction per type ----------------------------------------------------------

def test_mcq_and_tf_wrong(tmp_path):
    _, svc, asmt, _, _ = _env(tmp_path)
    done = _attempt(svc, asmt, {"i1": {"selected": [0]},
                               "i2": {"answer": False},
                               "i3": {"value": "4.0", "unit": "V"},
                               "i4": {"expression": "x+2"},
                               "i5": {"text": "Paris"}})
    assert done.result.total_score == Decimal("6.00")  # i1+i2 wrong
    assert done.result.passed is True


def test_numeric_boundaries_and_units(tmp_path):
    q = _q(3)
    assert correct_answer(q, {"value": "4.1", "unit": "V"}).reason == \
        "tolerance_match"  # |diff| == tol
    assert correct_answer(q, {"value": "4.11", "unit": "V"}).reason == \
        "value_mismatch"
    assert correct_answer(q, {"value": "4005", "unit": "mV"}).reason == \
        "tolerance_match"  # conversion
    assert correct_answer(q, {"value": "4.05", "unit": "s"}).reason == \
        "dimension_mismatch"
    with pytest.raises(Exception):
        correct_answer(q, {"value": "abc", "unit": "V"})


def test_numeric_precision(tmp_path):
    _, _, _, _, _ = _env(tmp_path)
    qp = QB.Question(question_id="question:demo:q:00009", statement="p",
                     qtype="numeric",
                     answer_spec={"value": "1000", "unit": "mV",
                                  "precision": 3},
                     owner_slug="demo")
    assert correct_answer(qp, {"value": "1.001",
                               "unit": "V"}).reason == "precision_match"
    assert correct_answer(qp, {"value": "1.005",
                               "unit": "V"}).reason == "value_mismatch"


def test_symbolic_equivalence_and_mismatch(tmp_path):
    _, _, _, _, _ = _env(tmp_path)
    q = _q(4)
    assert correct_answer(q, {"expression": "2+x"}).reason == \
        "symbolic_equivalent"
    assert correct_answer(q, {"expression": "x+3"}).reason == \
        "symbolic_mismatch"
    assert correct_answer(q, {"expression": "2+y"}).reason == \
        "symbol_mismatch"


def test_short_text_and_pending(tmp_path):
    _, svc, asmt, _, _ = _env(tmp_path)
    assert correct_answer(_q(5), {"text": "Paris"}).reason == "text_match"
    pending = QB.Question(question_id="question:demo:q:00007",
                          statement="Why?", qtype="short_text",
                          answer_spec={}, owner_slug="demo")
    v = correct_answer(pending, {"text": "because"})
    assert (v.is_correct, v.reason) == (None, "needs_review")
    done = _attempt(svc, asmt, {"i1": {"selected": [1]},
                               "i2": {"answer": True},
                               "i3": {"value": "4.0", "unit": "V"},
                               "i4": {"expression": "x+2"},
                               "i5": {"text": "Lyon"}})
    assert done.result.total_score == Decimal("8.00")  # i5 wrong


def test_structured_and_circuit_shape(tmp_path):
    _, _, _, _, _ = _env(tmp_path)
    st = QB.Question(question_id="question:demo:q:00007", statement="F",
                     qtype="structured",
                     answer_spec={"schema": {"name": "text", "n": "integer"}},
                     owner_slug="demo")
    v = correct_answer(st, {"fields": {"name": "x", "n": "3"}})
    assert (v.is_correct, v.reason) == (None, "needs_review")
    assert correct_answer(
        st, {"fields": {"name": "x"}}).reason == "field_set_mismatch"
    with pytest.raises(Exception):
        correct_answer(st, {"fields": {"name": "x", "n": "3.5"}})
    ci = QB.Question(question_id="question:demo:q:00008", statement="C",
                     qtype="circuit",
                     answer_spec={"netlist_ref": "R1 1 0 1k",
                                  "quantities": [{"name": "v",
                                                  "unit": "V"}]},
                     owner_slug="demo")
    v2 = correct_answer(ci, {"quantities": {"v": {"value": "3.3",
                                                 "unit": "V"}}})
    assert (v2.is_correct, v2.reason) == (None, "needs_review")
    assert json.loads(v2.normalized)["quantities"]["v"]["value"] == "3.3"


# -- scoring policies ---------------------------------------------------------------

def test_omitted_scores_zero_and_percentage(tmp_path):
    _, svc, asmt, _, _ = _env(tmp_path)
    done = _attempt(svc, asmt, {"i1": {"selected": [1]},
                               "i3": {"value": "4.0", "unit": "V"}})
    assert done.result.total_score == Decimal("4.00")
    assert done.result.percentage == Decimal("40.00")
    assert done.result.passed is False


# -- evidence --------------------------------------------------------------------------

def test_evidence_structured_verified_with_provenance(tmp_path):
    _, svc, asmt, repo, _ = _env(tmp_path)
    done = _attempt(svc, asmt)
    ev = svc.build_evidence(done.stable_id)
    assert ev.total_score == Decimal("10.00") and ev.passed is True
    assert len(ev.items) == 5 and all(i.verified for i in ev.items)
    first = ev.items[0]
    assert first.question_digest == repo.get_snapshots(
        done.stable_id)[0]["question_digest"]
    assert first.given_raw == QB.dumps_canonical(ANS["i1"])
    assert first.provenance.get("imported_by") == "d7-ingest/1"
    omitted = _attempt(svc, asmt, {"i1": {"selected": [1]}})
    # second student? same student attempt 2
    ev2 = svc.build_evidence(omitted.stable_id)
    assert sum(1 for i in ev2.items if i.reason == "omitted") == 4


def test_evidence_detects_snapshot_tamper(tmp_path):
    import sqlite3
    _, svc, asmt, _, _ = _env(tmp_path)
    done = _attempt(svc, asmt)
    db_path = tmp_path / "f9.db"
    cx = sqlite3.connect(db_path)
    row = cx.execute("SELECT * FROM assessment_item_snapshots LIMIT 1"
                     ).fetchone()
    cx.execute("DELETE FROM assessment_item_snapshots WHERE session_id=?",
               (done.stable_id,))
    forged = list(row)
    forged[5] = '{"question_id":"question:demo:q:00001"}'
    cx.execute("INSERT INTO assessment_item_snapshots VALUES (?,?,?,?,?,?,?)",
               forged)
    cx.commit()
    cx.close()
    ev = svc.build_evidence(done.stable_id)
    assert any(i.verified is False for i in ev.items)


# -- persistence + rollback -----------------------------------------------------------------

def test_submit_atomic_rollback_on_evidence_failure(tmp_path, monkeypatch):
    _, svc, asmt, repo, _ = _env(tmp_path)
    sess = svc.create_attempt(asmt, "stu1")
    svc.prepare(sess.stable_id, asmt)
    svc.sessions.start_session(sess.stable_id, NOW)

    def boom(rows, cx=None):
        raise RuntimeError("boom mid-submit")

    monkeypatch.setattr(repo, "save_evidence_batch", boom)
    with pytest.raises(RuntimeError):
        svc.submit_with_correction(sess.stable_id, asmt, dict(ANS), NOW)
    fresh = repo.get_session(sess.stable_id)
    assert fresh.status.value == "IN_PROGRESS"  # submit rolled back wholesale
    assert fresh.result is None
    assert repo.get_evidence(sess.stable_id) == []


# -- determinism -------------------------------------------------------------------------------

def test_same_answers_same_evidence(tmp_path):
    _, svc, asmt, _, _ = _env(tmp_path)
    a = _attempt(svc, asmt)
    b = svc.create_attempt(asmt, "stu2")
    svc.prepare(b.stable_id, asmt)
    svc.sessions.start_session(b.stable_id, NOW)
    b = svc.submit_with_correction(b.stable_id, asmt, dict(ANS), NOW)
    ea, eb = svc.build_evidence(a.stable_id), svc.build_evidence(b.stable_id)
    assert [(i.reason, i.score) for i in ea.items] == \
        [(i.reason, i.score) for i in eb.items]


# -- security -------------------------------------------------------------------------------------

def test_correction_files_have_no_dynamic_execution():
    for rel in ("domain/correction.py", "application/correction.py"):
        tree = ast.parse((SRC / rel).read_text(encoding="utf-8"))
        bad = []
        for n in ast.walk(tree):
            if isinstance(n, ast.Call):
                f = n.func
                if isinstance(f, ast.Name) and f.id in (
                        "eval", "exec", "compile", "__import__"):
                    bad.append(f"{rel}:{n.lineno}:{f.id}")
                for kw in n.keywords:
                    if kw.arg == "shell" and getattr(kw.value, "value",
                                                     False) is True:
                        bad.append(f"{rel}:{n.lineno}:shell=True")
        assert bad == []
    mods = set()
    for rel in ("domain/correction.py", "application/correction.py"):
        for n in ast.walk(ast.parse((SRC / rel).read_text(
                encoding="utf-8"))):
            if isinstance(n, ast.Import):
                mods.update(x.name.split(".")[0] for x in n.names)
            elif isinstance(n, ast.ImportFrom):
                mods.add((n.module or "").split(".")[0])
    assert mods <= {"__future__", "dataclasses", "datetime", "decimal", "json",
                    "re", "academic_core"}, mods


def test_malicious_formula_and_answer_never_execute(tmp_path):
    _, _, _, _, _ = _env(tmp_path)
    evil = "__import__('os').system('x')"
    q = _q(4)
    with pytest.raises(Exception):
        correct_answer(q, {"expression": evil})
