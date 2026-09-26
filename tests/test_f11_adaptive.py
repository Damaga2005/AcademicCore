# SPDX-License-Identifier: MIT
"""F11 adaptive contracts: deterministic practice plans, LLM=OFF.

Covers prompt sections 25-27: eligibility, mastery priority, ranking,
history, route, reproducibility, idempotency, edge cases, security.
F10/F9/D7/D6/D5 regression runs in the gate suite.
"""

from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from academic_core.application.adaptive import AdaptiveService
from academic_core.application.bank_ingest import BankIngestionService
from academic_core.application.mastery import MasteryService
from academic_core.domain import adaptive as AD
from academic_core.domain import mastery as M
from academic_core.domain import question_bank as QB
from academic_core.domain import entities as E
from academic_core.domain.planning import StudyConcept
from academic_core.errors import AcademicManagementError
from academic_core.infrastructure.academic_store import (
    MasteryRepository,
    PersonalRepository,
    QBankRepository,
)
from academic_core.infrastructure.database import Database
from academic_core.infrastructure.repositories import AcademicRepository

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "academic_core"
NOW = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)
MS = 1758792000000


def _q(n, concepts, difficulty, qtype, spec):
    return QB.Question(
        question_id=f"question:demo:q:{n:05d}",
        statement=f"S{n}?", qtype=qtype, answer_spec=spec,
        owner_slug="demo", concepts=list(concepts),
        difficulty=difficulty)


def _bank():
    return QB.Bank(
        bank_id="bank:demo", title="Demo", content_version=1,
        questions=(
            _q(1, ("concept:al:c:00001",), "easy", "multiple_choice",
               {"options": ["3", "4"], "correct": [1]}),
            _q(2, ("concept:al:c:00001",), "medium", "true_false",
               {"answer": True}),
            _q(3, ("concept:al:c:00002",), "hard", "numeric",
               {"value": "4.0", "unit": "V"}),
            _q(4, ("concept:al:c:00002",), "easy", "short_text",
               {"expected": "Paris"}),
            _q(5, ("concept:al:c:00003",), "medium", "multiple_choice",
               {"options": ["a", "b"], "correct": [0]}),
        ))


def _stack(tmp_path):
    db = Database(tmp_path / "f11.db")
    ac = AcademicRepository(db)
    ac.add_subject(E.Subject("subject:al", "ALG", "Algebra", "ALG"))
    pe, qb = PersonalRepository(db), QBankRepository(db)
    for ref, name in (("concept:al:c:00001", "Derivada"),
                      ("concept:al:c:00002", "Integral"),
                      ("concept:al:c:00003", "Límite")):
        pe.add_concept(StudyConcept(ref, "subject:al", name))
    BankIngestionService(ac, pe, qb).ingest(QB.dumps_bank(_bank()),
                                            now_ms=MS)
    mrepo = MasteryRepository(db)
    svc = AdaptiveService(qb, mrepo, ac)
    m10 = MasteryService(mrepo, ac, pe)
    return db, qb, mrepo, svc, m10


# -- eligibility ---------------------------------------------------------------

def test_eligible_and_ineligible_filters(tmp_path):
    db, qb, mrepo, svc, _ = _stack(tmp_path)
    ctx = AD.AdaptiveContext(subject_id="subject:al", exercise_count=5)
    plan = svc._build_plan("stu1", ctx)
    assert {s.candidate.question_id for s in plan.selections} == {
        "question:demo:q:00001", "question:demo:q:00002",
        "question:demo:q:00003", "question:demo:q:00004",
        "question:demo:q:00005"}
    ctx_t = AD.AdaptiveContext(subject_id="subject:al",
                               allowed_types=("true_false",),
                               exercise_count=5)
    plan_t = svc._build_plan("stu1", ctx_t)
    assert {s.candidate.qtype for s in plan_t.selections} == {"true_false"}
    ctx_d = AD.AdaptiveContext(subject_id="subject:al",
                               difficulty_min="medium",
                               difficulty_max="hard", exercise_count=5)
    plan_d = svc._build_plan("stu1", ctx_d)
    assert {s.candidate.difficulty for s in plan_d.selections} <= {
        "medium", "hard"}
    ctx_c = AD.AdaptiveContext(subject_id="subject:al",
                               concept_ref="concept:al:c:00001",
                               exercise_count=5)
    plan_c = svc._build_plan("stu1", ctx_c)
    assert all("concept:al:c:00001" in s.candidate.concepts
               for s in plan_c.selections)
    # empty bank → structured empty plan, never a fake one
    ctx_none = AD.AdaptiveContext(subject_id="subject:ghost",
                                  exercise_count=5)
    plan_none = svc._build_plan("stu1", ctx_none)
    assert plan_none.selections == ()
    assert plan_none.rationale_codes == ("NO_ELIGIBLE_EXERCISES",)


def test_no_eligible_is_structured(tmp_path):
    _, _, _, svc, _ = _stack(tmp_path)
    ctx = AD.AdaptiveContext(subject_id="subject:al",
                             allowed_types=("circuit",), exercise_count=5)
    plan = svc._build_plan("stu1", ctx)
    assert plan.selections == ()
    assert plan.rationale_codes == ("NO_ELIGIBLE_EXERCISES",)


# -- mastery priority -------------------------------------------------------------

def test_low_mastery_gets_priority(tmp_path):
    db, qb, mrepo, svc, m10 = _stack(tmp_path)
    mrepo.save_observation(
        M.Observation("stu1", "sess", "question:demo:q:00001",
                       "concept:al:c:00001", "topic:al:t01", "subject:al",
                       True, Decimal(1), Decimal(0), "d1", "f9-correct/1"),
        "d1", 0)
    mrepo.save_observation(
        M.Observation("stu1", "sess", "question:demo:q:00003",
                       "concept:al:c:00002", "topic:al:t01", "subject:al",
                       False, Decimal(0), Decimal(1), "d2", "f9-correct/1"),
        "d2", 0)
    m10.rebuild("stu1")  # rebuild states from observations
    ctx = AD.AdaptiveContext(subject_id="subject:al", exercise_count=2)
    plan = svc._build_plan("stu1", ctx)
    picked = [s.candidate for s in plan.selections]
    assert any("concept:al:c:00002" in c.concepts for c in picked)
    assert any("concept:al:c:00001" not in c.concepts
               for c in picked) or plan.selections == ()
    codes = set(plan.rationale_codes)
    assert "LOW_MASTERY" in codes or "RECENT_ERROR" in codes


def test_mastery_levels_rank():
    cfg = AD.AdaptiveConfig()
    low = AD.Candidate("q1", "multiple_choice", "easy", ("c1",),
                       "t", "s", 1, "d", mastery_p=Decimal("0.1"))
    high = AD.Candidate("q2", "multiple_choice", "easy", ("c2",),
                        "t", "s", 1, "d", mastery_p=Decimal("0.9"))
    ranked = AD.rank_candidates([high, low], cfg)
    assert ranked[0].candidate.question_id == "q1"
    assert "LOW_MASTERY" in ranked[0].rationale
    assert "LOW_MASTERY" not in ranked[1].rationale


# -- ranking -------------------------------------------------------------------------

def test_ranking_deterministic_and_tiebreak():
    cfg = AD.AdaptiveConfig()
    a = AD.Candidate("q2", "multiple_choice", "easy", ("c",), "t", "s",
                     1, "d", mastery_p=Decimal("0.5"))
    b = AD.Candidate("q1", "multiple_choice", "easy", ("c",), "t", "s",
                     1, "d", mastery_p=Decimal("0.5"))
    r1 = AD.rank_candidates([a, b], cfg)
    r2 = AD.rank_candidates([b, a], cfg)
    assert [s.candidate.question_id for s in r1] == [
        s.candidate.question_id for s in r2]
    assert [s.candidate.question_id for s in r1] == ["q1", "q2"]


def test_difficulty_fit_policy():
    cfg = AD.AdaptiveConfig()
    assert AD.difficulty_fit("easy", "easy", False) == 1
    assert AD.difficulty_fit("medium", "easy", False) == Decimal("0.5")
    assert AD.difficulty_fit("hard", "easy", False) == 0
    assert AD.difficulty_fit("unspecified", "medium", False) == 0
    assert AD.difficulty_fit("unspecified", "medium", True) == 1
    assert AD.target_difficulty(Decimal("0.2"), cfg) == "easy"
    assert AD.target_difficulty(Decimal("0.5"), cfg) == "medium"
    assert AD.target_difficulty(Decimal("0.9"), cfg) == "hard"
    assert AD.target_difficulty(None, cfg) == "unspecified"


# -- history -----------------------------------------------------------------------------

def test_done_questions_excluded_and_cap_per_concept(tmp_path):
    db, qb, mrepo, svc, _ = _stack(tmp_path)
    ctx = AD.AdaptiveContext(subject_id="subject:al", exercise_count=5)
    mrepo.save_observation(
        M.Observation("stu1", "sess", "question:demo:q:00001",
                       "concept:al:c:00001", "topic:al:t01", "subject:al",
                       True, Decimal(1), Decimal(0), "d", "f9-correct/1"),
        "d", 0)
    plan = svc._build_plan("stu1", ctx)
    picked = {s.candidate.question_id for s in plan.selections}
    assert "question:demo:q:00001" not in picked
    counts = {}
    for s in plan.selections:
        for c in s.candidate.concepts:
            counts[c] = counts.get(c, 0) + 1
    assert all(v <= AD.AdaptiveConfig().max_per_concept
               for v in counts.values())


def test_all_done_yields_no_eligible(tmp_path):
    db, qb, mrepo, svc, _ = _stack(tmp_path)
    for i in range(1, 6):
        mrepo.save_observation(
            M.Observation("stu1", "sess", f"question:demo:q:{i:05d}",
                           f"concept:al:c:{(i - 1) % 3 + 1:05d}",
                           "topic:al:t01", "subject:al", True,
                           Decimal(1), Decimal(0), f"d{i}",
                           "f9-correct/1"),
            f"d{i}", 0)
    plan = svc._build_plan("stu1", AD.AdaptiveContext(
        subject_id="subject:al", exercise_count=5))
    assert plan.selections == ()
    assert plan.rationale_codes == ("NO_ELIGIBLE_EXERCISES",)


# -- route ---------------------------------------------------------------------------------

def test_route_limit_order_and_rationale(tmp_path):
    _, _, _, svc, _ = _stack(tmp_path)
    ctx = AD.AdaptiveContext(subject_id="subject:al", exercise_count=2)
    plan = svc._build_plan("stu1", ctx)
    assert len(plan.selections) == 2
    scores = [s.adaptive_score for s in plan.selections]
    assert scores == sorted(scores, reverse=True)
    codes = set(plan.rationale_codes)
    assert "REPETITION_AVOIDED" in codes
    assert "PREREQUISITE_OK" in codes


def test_single_candidate_and_underfilled(tmp_path):
    _, _, _, svc, _ = _stack(tmp_path)
    ctx = AD.AdaptiveContext(subject_id="subject:al", exercise_count=10)
    plan = svc._build_plan("stu1", ctx)
    assert 0 < len(plan.selections) <= 5
    ctx_one = AD.AdaptiveContext(subject_id="subject:al", exercise_count=1)
    assert len(svc._build_plan("stu1", ctx_one).selections) == 1


# -- reproducibility -------------------------------------------------------------------------

def test_same_inputs_same_plan(tmp_path):
    _, _, _, svc, _ = _stack(tmp_path)
    ctx = AD.AdaptiveContext(subject_id="subject:al", exercise_count=3)
    p1 = svc._build_plan("stu1", ctx)
    p2 = svc._build_plan("stu1", ctx)
    assert AD.plan_digest(p1) == AD.plan_digest(p2)
    assert [s.candidate.question_id for s in p1.selections] == [
        s.candidate.question_id for s in p2.selections]


def test_config_changes_plan(tmp_path):
    db, qb, mrepo, svc, _ = _stack(tmp_path)
    ctx = AD.AdaptiveContext(subject_id="subject:al", exercise_count=3)
    base = AD.plan_digest(svc._build_plan("stu1", ctx))
    svc.config = AD.AdaptiveConfig(mastery_weight=Decimal("1"))
    other = AD.plan_digest(svc._build_plan("stu1", ctx))
    assert base != other
    assert svc.config.config_version == 1


def test_no_random_in_engine():
    src = (SRC / "domain" / "adaptive.py").read_text(encoding="utf-8")
    assert "import random" not in src


# -- idempotency ---------------------------------------------------------------------------------

def test_persisted_plan_idempotent(tmp_path):
    db, qb, mrepo, svc, _ = _stack(tmp_path)
    ctx = AD.AdaptiveContext(subject_id="subject:al", exercise_count=3)
    plan1 = svc.build_plan("stu1", ctx)
    plan2 = svc.build_plan("stu1", ctx)
    assert AD.plan_digest(plan1) == AD.plan_digest(plan2)
    stored = mrepo.plans_of("stu1")
    assert len(stored) == 1
    assert stored[0]["plan_digest"] == AD.plan_digest(plan1)
    got = mrepo.get_plan(stored[0]["plan_id"])
    assert got["student_id"] == "stu1"
    assert json.loads(got["selections_json"])[0]["question_id"] == \
        plan1.selections[0].candidate.question_id


# -- LLM=OFF --------------------------------------------------------------------------------------

def test_llm_off_complete_plan(tmp_path):
    _, _, _, svc, _ = _stack(tmp_path)
    ctx = AD.AdaptiveContext(subject_id="subject:al", exercise_count=4)
    plan = svc._build_plan("stu1", ctx)
    assert plan.selections
    for rel in ("domain/adaptive.py", "application/adaptive.py"):
        src = (SRC / rel).read_text(encoding="utf-8")
        low = src.lower()
        assert "openai" not in low and "anthropic" not in low
        assert "ollama" not in low and "gemini" not in low


def test_no_ai_imports_in_engine():
    for rel in ("domain/adaptive.py", "application/adaptive.py"):
        tree = ast.parse((SRC / rel).read_text(encoding="utf-8"))
        mods = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                mods.update(a.name.split(".")[0] for a in n.names)
            elif isinstance(n, ast.ImportFrom):
                mods.add((n.module or "").split(".")[0])
        assert mods <= {"__future__", "dataclasses", "decimal", "hashlib",
                        "json", "academic_core"}, mods


# -- edge cases ----------------------------------------------------------------------------------------

def test_prerequisite_subject_unmet_blocks_plan(tmp_path):
    db, qb, mrepo, svc, _ = _stack(tmp_path)
    ac = svc.academic
    ac.add_subject(E.Subject("subject:calc", "CALC", "Calculo", "CALC"))
    ac.add_prerequisite("subject:al", "subject:calc")
    # calc never practiced → 'al' prerequisite unmet → nothing eligible
    plan = svc._build_plan("stu1", AD.AdaptiveContext(
        subject_id="subject:al", exercise_count=5))
    assert plan.selections == ()
    assert "PREREQUISITE_UNMET" in plan.rationale_codes


def test_prerequisite_satisfied_after_practice(tmp_path):
    db, qb, mrepo, svc, _ = _stack(tmp_path)
    ac = svc.academic
    ac.add_subject(E.Subject("subject:calc", "CALC", "Calculo", "CALC"))
    ac.add_prerequisite("subject:al", "subject:calc")
    mrepo.save_observation(
        M.Observation("stu1", "sess", "question:demo:q:00001",
                       "concept:al:c:00001", "topic:al:t01", "subject:calc",
                       True, Decimal(1), Decimal(0), "d", "f9-correct/1"),
        "d", 0)
    plan = svc._build_plan("stu1", AD.AdaptiveContext(
        subject_id="subject:al", exercise_count=5))
    assert plan.selections
    assert "PREREQUISITE_OK" in plan.rationale_codes


def test_unknown_config_and_context_rejected():
    with pytest.raises(Exception):
        AD.AdaptiveConfig(engine_version="f9-correct/1")
    with pytest.raises(Exception):
        AD.AdaptiveConfig(mastery_threshold_low=Decimal("0.8"),
                         mastery_threshold_high=Decimal("0.2"))
    with pytest.raises(Exception):
        AD.AdaptiveContext(subject_id="subject:al", exercise_count=0)
    with pytest.raises(Exception):
        AD.AdaptiveContext(subject_id="subject:al",
                           allowed_types=("essay",))


def test_malformed_state_rejected(tmp_path):
    db, qb, mrepo, svc, _ = _stack(tmp_path)
    mrepo.save_state(student_id="stu1", level="concept",
                     ref_id="concept:al:c:00001", alpha="NaN", beta="1",
                     model_version="f10-beta/1", config_version=1,
                     obs_count=1, members=["concept:al:c:00001"],
                     updated_at_ms=0)
    with pytest.raises(AcademicManagementError):
        svc._build_plan("stu1", AD.AdaptiveContext(
            subject_id="subject:al", exercise_count=3))


# -- security -------------------------------------------------------------------------------------------

def test_adaptive_files_have_no_dynamic_execution():
    for rel in ("domain/adaptive.py", "application/adaptive.py"):
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


def test_rationale_codes_closed_set():
    with pytest.raises(Exception):
        AD.AdaptivePlan("s", (), ("MADE_UP",), 1, "m", "d", ())
