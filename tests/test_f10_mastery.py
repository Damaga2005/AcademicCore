# SPDX-License-Identifier: MIT
"""F10 mastery contracts: Beta-Binomial model over F9 evidence.

Covers prompt sections 27-33: model, evidence, idempotence,
reproducibility, hierarchy, versioning, persistence (tx/rollback/
concurrent), security, regression pointers. F9/D7/D6/D5 regression runs
in the gate suite.
"""

from __future__ import annotations

import ast
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from academic_core.application.bank_ingest import BankIngestionService
from academic_core.application.correction import CorrectionService
from academic_core.application.mastery import MasteryService
from academic_core.domain import mastery as M
from academic_core.domain import question_bank as QB
from academic_core.domain import entities as E
from academic_core.domain.assessment import Assessment, AssessmentItem, GradingPolicy
from academic_core.domain.planning import StudyConcept
from academic_core.errors import AcademicManagementError
from academic_core.infrastructure.academic_store import (
    MasteryRepository,
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


def _q(n, concepts=(), **kw):
    specs = {
        1: ("multiple_choice", {"options": ["3", "4"], "correct": [1]}),
        2: ("true_false", {"answer": True}),
        3: ("short_text", {"expected": "Paris"}),
        4: ("short_text", {}),
    }
    t, spec = specs[n]
    d = dict(question_id=f"question:demo:q:{n:05d}", statement=f"S{n}?",
             qtype=t, answer_spec=spec, owner_slug="demo")
    if concepts:
        d["concepts"] = list(concepts)
    d.update(kw)
    return QB.Question(**d)


def _bank(concepts1=("concept:al:c:00001",), version=1):
    return QB.Bank(bank_id="bank:demo", title="Demo",
                   content_version=version,
                   questions=(_q(1, concepts1), _q(2), _q(3)))


ANS = {"i1": {"selected": [1]}, "i2": {"answer": True},
       "i3": {"text": "Paris"}}


def _stack(tmp_path):
    db = Database(tmp_path / "f10.db")
    ac = AcademicRepository(db)
    ac.add_subject(E.Subject("subject:al", "ALG", "Algebra", "ALG"))
    ac.add_topic(E.Topic("topic:al:t01", "subject:al", "01", "T1"))
    pe, qb = PersonalRepository(db), QBankRepository(db)
    for ref, name in (("concept:al:c:00001", "Derivada"),
                      ("concept:al:c:00002", "Integral")):
        pe.add_concept(StudyConcept(ref, "subject:al", name))
    BankIngestionService(ac, pe, qb).ingest(
        QB.dumps_bank(_bank()), now_ms=MS)
    repo = AssessmentRepository(db)
    asmt = Assessment(stable_id="assessment:al:as:00001",
                      subject_id="subject:al", title="T",
                      items=tuple(AssessmentItem(
                          f"i{i}", f"question:demo:q:{i:05d}",
                          "topic:al:t01", Decimal("1.0"))
                          for i in range(1, 4)),
                      attempts_allowed=5, policy=GradingPolicy())
    repo.save_assessment(asmt)
    m10 = MasteryService(MasteryRepository(db), ac, pe)
    return db, repo, qb, asmt, m10, pe, ac


def _evidence(repo, qb, svc_f9, asmt, student="stu1", answers=None):
    sess = svc_f9.create_attempt(asmt, student)
    svc_f9.prepare(sess.stable_id, asmt)
    svc_f9.sessions.start_session(sess.stable_id, NOW)
    done = svc_f9.submit_with_correction(
        sess.stable_id, asmt, dict(answers if answers is not None else ANS),
        NOW)
    return svc_f9.build_evidence(done.stable_id, asmt)


# -- model -------------------------------------------------------------------

def test_model_update_and_probability():
    cfg = M.MasteryConfig()
    s = M.prior_state("concept:al:c:00001", cfg)
    assert s.probability() == Decimal("0.5")  # Beta(1,1)
    obs = M.Observation("stu1", "sess", "item", "concept:al:c:00001",
                        "topic:al:t01", "subject:al", True,
                        Decimal(1), Decimal(0), "d", "f9-correct/1")
    s1 = M.apply_observation(s, obs)
    assert s1.alpha == 2 and s1.beta == 1 and s1.obs_count == 1
    assert 0 <= s1.probability() <= 1
    obs2 = M.Observation("stu1", "sess", "item", "concept:al:c:00001",
                         "topic:al:t01", "subject:al", False,
                         Decimal(0), Decimal(1), "d", "f9-correct/1")
    s2 = M.apply_observation(s1, obs2)
    assert s2.alpha == 2 and s2.beta == 2 and s2.variance() > 0


def test_model_boundaries_and_invalid():
    cfg = M.MasteryConfig()
    with pytest.raises(Exception):
        M.MasteryConfig(prior_alpha=Decimal("-1"))
    with pytest.raises(Exception):
        M.MasteryConfig(weight_precision=13)
    state = M.ConceptState("r", Decimal(1), Decimal(1))
    assert 0 <= state.probability() <= 1
    assert state.variance() > 0


def test_fold_and_pool():
    cfg = M.MasteryConfig()
    o1 = M.Observation("s", "x", "i", "c", "t", "sub", True,
                       Decimal(1), Decimal(0), "d", "e")
    o2 = M.Observation("s", "y", "i", "c", "t", "sub", False,
                       Decimal(0), Decimal(1), "d", "e")
    assert M.fold_observations("c", [o2, o1], cfg) == \
        M.fold_observations("c", [o1, o2], cfg)  # order-free
    m1 = M.ConceptState("c", Decimal(2), Decimal(1))
    m2 = M.ConceptState("c", Decimal(1), Decimal(2))
    pooled = M.pool_states("c", [m1, m2])
    assert pooled.alpha == 3 and pooled.beta == 3
    assert M.observation_digest(o1) == M.observation_digest(
        M.Observation("s", "x", "i", "c", "t", "sub", True,
                      Decimal(1), Decimal(0), "d", "e"))
    assert M.observation_digest(o1) != M.observation_digest(o2)


# -- evidence → mastery -----------------------------------------------------------

def test_apply_evidence_updates_states(tmp_path):
    _, repo, qb, asmt, m10, _, _ = _stack(tmp_path)
    f9 = CorrectionService(repo, qb)
    ev = _evidence(repo, qb, f9, asmt)
    res = m10.apply_evidence(ev)
    assert res["applied"] == 1  # only i1 carries a concept (no_update else)
    state = m10.get_mastery("stu1", "concept:al:c:00001")
    assert state is not None and state.obs_count == 1
    assert 0 <= state.probability() <= 1
    subj = m10.get_subject_mastery("stu1", "subject:al")
    assert subj is not None and subj.state.alpha > 1
    top = m10.get_topic_mastery("stu1", "topic:al:t01")
    assert top is not None


def test_multiple_concepts_split_weight(tmp_path):
    db, repo, qb, asmt, m10, pe, ac = _stack(tmp_path)
    BankIngestionService(ac, pe, qb).ingest(
        QB.dumps_bank(_bank(concepts1=("concept:al:c:00001",
                                        "concept:al:c:00002"), version=2)),
        now_ms=MS)
    f9 = CorrectionService(repo, qb)
    ev = _evidence(repo, qb, f9, asmt)
    res = m10.apply_evidence(ev)
    assert res["applied"] == 2  # q1 has 2 concepts; q2/q3 unmapped (no_update)
    s1 = m10.get_mastery("stu1", "concept:al:c:00001")
    s2 = m10.get_mastery("stu1", "concept:al:c:00002")
    assert s1.alpha == Decimal("1.5") and s2.alpha == Decimal("1.5")


def test_unknown_concept_rejected_no_writes(tmp_path):
    db, repo, qb, asmt, m10, pe, ac = _stack(tmp_path)
    q4 = _q(4, concepts=("concept:al:c:00009",))
    asmt4 = Assessment(stable_id="assessment:al:as:00001",
                       subject_id="subject:al", title="T",
                       items=asmt.items + (
                           AssessmentItem("i4", "question:demo:q:00004",
                                          "topic:al:t01", Decimal("1")),),
                       attempts_allowed=5, policy=GradingPolicy())
    repo.save_assessment(asmt4)  # replaces by stable_id
    f9 = CorrectionService(repo, qb)
    sess = f9.create_attempt(asmt4, "stu1")
    with pytest.raises(AcademicManagementError) as e:
        f9.prepare(sess.stable_id, asmt4)
    assert e.value.code == "AC-ACD-002"
    assert m10.get_mastery("stu1", "concept:al:c:00001") is None


# -- idempotence ----------------------------------------------------------------------

def test_apply_twice_idempotent(tmp_path):
    _, repo, qb, asmt, m10, _, _ = _stack(tmp_path)
    f9 = CorrectionService(repo, qb)
    ev = _evidence(repo, qb, f9, asmt)
    m10.apply_evidence(ev)
    before = m10.get_mastery("stu1", "concept:al:c:00001")
    res2 = m10.apply_evidence(ev)
    after = m10.get_mastery("stu1", "concept:al:c:00001")
    assert res2["applied"] == 0
    assert before.alpha == after.alpha and before.obs_count == after.obs_count


def test_rebuild_equals_incremental(tmp_path):
    _, repo, qb, asmt, m10, _, _ = _stack(tmp_path)
    f9 = CorrectionService(repo, qb)
    ev = _evidence(repo, qb, f9, asmt)
    m10.apply_evidence(ev)
    inc = m10.get_mastery("stu1", "concept:al:c:00001")
    m10.rebuild("stu1")
    reb = m10.get_mastery("stu1", "concept:al:c:00001")
    assert (inc.alpha, inc.beta, inc.obs_count) == \
        (reb.alpha, reb.beta, reb.obs_count)
    subj = m10.get_subject_mastery("stu1", "subject:al").state
    assert subj.alpha > 1 and subj.beta >= 1


# -- determinism -------------------------------------------------------------------------

def test_deterministic_across_inputs(tmp_path):
    outs = []
    for sub in ("a", "b"):
        _, repo, qb, asmt, m10, _, _ = _stack(tmp_path / sub)
        f9 = CorrectionService(repo, qb)
        ev = _evidence(repo, qb, f9, asmt)
        m10.apply_evidence(ev)
        s = m10.get_mastery("stu1", "concept:al:c:00001")
        outs.append((str(s.alpha), str(s.beta), s.probability(),
                     s.variance()))
    assert outs[0] == outs[1]


# -- persistence: tx / rollback / concurrent ----------------------------------------------

def test_failed_apply_rolls_back(tmp_path, monkeypatch):
    db, repo, qb, asmt, m10, pe, ac = _stack(tmp_path)
    # v2: q1 references two concepts so the plan carries two observations
    BankIngestionService(ac, pe, qb).ingest(
        QB.dumps_bank(_bank(concepts1=("concept:al:c:00001",
                                        "concept:al:c:00002"), version=2)),
        now_ms=MS)
    f9 = CorrectionService(repo, qb)
    ev = _evidence(repo, qb, f9, asmt)
    mrepo = m10.repo  # the repository the service writes through
    real = mrepo.save_observation
    calls = {"n": 0}

    def flaky(o, d, ms, cx=None):
        calls["n"] += 1
        if calls["n"] > 1:
            raise RuntimeError("boom")
        return real(o, d, ms, cx=cx)

    monkeypatch.setattr(mrepo, "save_observation", flaky)
    with pytest.raises(RuntimeError):
        m10.apply_evidence(ev)
    assert m10.get_mastery("stu1", "concept:al:c:00001") is None
    assert mrepo.states_of("stu1", "concept") == []


def test_concurrent_double_apply_is_safe(tmp_path):
    _, repo, qb, asmt, m10, _, _ = _stack(tmp_path)
    f9 = CorrectionService(repo, qb)
    ev = _evidence(repo, qb, f9, asmt)
    mrepo = MasteryRepository(repo.db)
    o = M.Observation("stu1", ev.session_id, "question:demo:q:00001",
                      "concept:al:c:00001", "topic:al:t01", "subject:al",
                      True, Decimal(1), Decimal(0), "d", "f9-correct/1")
    d = M.observation_digest(o)
    with mrepo.unit_of_work() as cx:
        mrepo.save_observation(o, d, 0, cx=cx)
    assert mrepo.save_observation(o, d, 0) is False  # no duplicate
    rows = mrepo.observations_of("stu1")
    assert len(rows) == 1


def test_round_trip_and_corrupt_state_rejected(tmp_path):
    _, repo, qb, asmt, m10, _, _ = _stack(tmp_path)
    f9 = CorrectionService(repo, qb)
    ev = _evidence(repo, qb, f9, asmt)
    m10.apply_evidence(ev)
    assert m10.get_mastery("stu1", "concept:al:c:00001") is not None
    cx = sqlite3.connect(tmp_path / "f10.db")
    cx.execute("UPDATE mastery_states SET alpha='NaN'")
    cx.commit()
    cx.close()
    with pytest.raises(Exception):
        m10.get_mastery("stu1", "concept:al:c:00001")


# -- security ----------------------------------------------------------------------------------

def test_mastery_files_have_no_dynamic_execution():
    for rel in ("domain/mastery.py", "application/mastery.py"):
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
    for rel in ("domain/mastery.py", "application/mastery.py"):
        for n in ast.walk(ast.parse((SRC / rel).read_text(
                encoding="utf-8"))):
            if isinstance(n, ast.Import):
                mods.update(x.name.split(".")[0] for x in n.names)
            elif isinstance(n, ast.ImportFrom):
                mods.add((n.module or "").split(".")[0])
    assert mods <= {"__future__", "dataclasses", "decimal", "hashlib",
                    "json", "academic_core"}, mods


def test_f10_never_re_corrects():
    src = (SRC / "application" / "mastery.py").read_text(encoding="utf-8")
    assert "correct_answer" not in src  # F10 consumes verdicts, never re-corrects
