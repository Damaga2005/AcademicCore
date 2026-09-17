"""Tests for Phase F9-B Assessment Domain Models.

Validates:
1. Identity validation for assessment and session kinds.
2. Invariants for Assessment, AssessmentItem, and GradingPolicy.
3. Pure Decimal mathematics in GradingPolicy (partial credit, negative marking, pass/fail).
4. AssessmentSession lifecycle state transitions, timeout/expiration, and responses.
5. Deterministic item ordering and shuffling.
6. Final evaluation result computation.
7. AST security: zero eval, exec, subprocess, or floats.
"""

from __future__ import annotations

import ast
from datetime import datetime, timedelta
from decimal import Decimal
import inspect
from pathlib import Path

import pytest

from academic_core.domain.assessment import (
    Assessment,
    AssessmentItem,
    AssessmentResult,
    AssessmentSession,
    GradingPolicy,
    SessionStatus,
    StudentResponse,
)
import academic_core.domain.assessment.policy as policy_module
from academic_core.domain.entities import DomainError
from academic_core.domain.identity import validate, make


# -----------------------------------------------------------------------------
# 1. Identity & Registration
# -----------------------------------------------------------------------------

def test_assessment_identity_grammar():
    as_id = "assessment:sdm:as:00001"
    sess_id = "session:sdm:sess:00042"
    assert validate(as_id) == "assessment"
    assert validate(sess_id) == "session"

    # Generated via make()
    assert make("assessment", "sdm", "00005") == "assessment:sdm:as:00005"
    assert make("session", "sdm", "00009") == "session:sdm:sess:00009"

    # Malformed IDs rejected
    with pytest.raises(ValueError):
        validate("assessment:sdm:00001")
    with pytest.raises(ValueError):
        validate("session:sdm:s:00001")


# -----------------------------------------------------------------------------
# 2. Assessment & AssessmentItem Invariants
# -----------------------------------------------------------------------------

def _sample_items() -> tuple[AssessmentItem, ...]:
    return (
        AssessmentItem(item_id="q1", question_id="q:sdm:001", topic_id="topic:sdm:t01", weight=Decimal("2.0")),
        AssessmentItem(item_id="q2", question_id="q:sdm:002", topic_id="topic:sdm:t01", weight=Decimal("3.0")),
        AssessmentItem(item_id="q3", question_id="q:sdm:003", topic_id="topic:sdm:t02", weight=Decimal("5.0")),
    )


def test_assessment_item_invariants():
    # Valid item
    it = AssessmentItem(item_id="q1", question_id="q:1", topic_id="topic:t1", weight=Decimal("2.5"))
    assert it.weight == Decimal("2.5")

    # Empty item_id
    with pytest.raises(DomainError, match="item_id cannot be empty"):
        AssessmentItem(item_id="  ", question_id="q:1", topic_id="topic:t1")

    # Empty question_id
    with pytest.raises(DomainError, match="question_id cannot be empty"):
        AssessmentItem(item_id="q1", question_id="", topic_id="topic:t1")

    # Empty topic_id
    with pytest.raises(DomainError, match="topic_id cannot be empty"):
        AssessmentItem(item_id="q1", question_id="q:1", topic_id="")

    # Non-positive weight
    with pytest.raises(DomainError, match="weight must be > 0"):
        AssessmentItem(item_id="q1", question_id="q:1", topic_id="topic:t1", weight=Decimal("0"))
    with pytest.raises(DomainError, match="weight must be > 0"):
        AssessmentItem(item_id="q1", question_id="q:1", topic_id="topic:t1", weight=Decimal("-1.0"))


def test_assessment_invariants():
    items = _sample_items()
    asmt = Assessment(
        stable_id="assessment:sdm:as:00001",
        subject_id="subject:sdm",
        title="Parcial de Circuitos",
        items=items,
        duration_min=90,
    )
    assert asmt.total_weight == Decimal("10.0")
    assert asmt.get_item("q2").weight == Decimal("3.0")

    # Bad stable_id
    with pytest.raises(DomainError, match="bad stable_id"):
        Assessment(stable_id="exam:sdm:e:00001", subject_id="subject:sdm", title="T", items=items)

    # Bad subject_id
    with pytest.raises(DomainError, match="bad subject_id"):
        Assessment(stable_id="assessment:sdm:as:00001", subject_id="degree:telecom", title="T", items=items)

    # Empty title
    with pytest.raises(DomainError, match="title cannot be empty"):
        Assessment(stable_id="assessment:sdm:as:00001", subject_id="subject:sdm", title="  ", items=items)

    # Empty items
    with pytest.raises(DomainError, match="at least one item"):
        Assessment(stable_id="assessment:sdm:as:00001", subject_id="subject:sdm", title="T", items=())

    # Duplicate item_ids
    dup_items = (
        AssessmentItem(item_id="q1", question_id="q:1", topic_id="topic:t1"),
        AssessmentItem(item_id="q1", question_id="q:2", topic_id="topic:t1"),
    )
    with pytest.raises(DomainError, match="Duplicate item_id"):
        Assessment(stable_id="assessment:sdm:as:00001", subject_id="subject:sdm", title="T", items=dup_items)

    # Negative duration
    with pytest.raises(DomainError, match="duration_min cannot be negative"):
        Assessment(stable_id="assessment:sdm:as:00001", subject_id="subject:sdm", title="T", items=items, duration_min=-5)

    # Attempts allowed < 1
    with pytest.raises(DomainError, match="attempts_allowed must be >= 1"):
        Assessment(stable_id="assessment:sdm:as:00001", subject_id="subject:sdm", title="T", items=items, attempts_allowed=0)


def test_deterministic_item_ordering():
    items = _sample_items()
    # Unshuffled preserves original declared order
    asmt_unshuffled = Assessment(
        stable_id="assessment:sdm:as:00001",
        subject_id="subject:sdm",
        title="T",
        items=items,
        shuffle_items=False,
    )
    assert asmt_unshuffled.generate_item_order() == ("q1", "q2", "q3")
    assert asmt_unshuffled.generate_item_order(seed=12345) == ("q1", "q2", "q3")

    # Shuffled with seed produces deterministic permutation
    asmt_shuffled = Assessment(
        stable_id="assessment:sdm:as:00001",
        subject_id="subject:sdm",
        title="T",
        items=items,
        shuffle_items=True,
    )
    order1 = asmt_shuffled.generate_item_order(seed=42)
    order2 = asmt_shuffled.generate_item_order(seed=42)
    order3 = asmt_shuffled.generate_item_order(seed=999)

    assert order1 == order2
    assert set(order1) == {"q1", "q2", "q3"}
    # Different seeds yield reproducible permutations
    assert asmt_shuffled.generate_item_order(seed=999) == order3


# -----------------------------------------------------------------------------
# 3. GradingPolicy & Scoring Mathematics
# -----------------------------------------------------------------------------

def test_grading_policy_invariants():
    # Valid
    p = GradingPolicy(passing_score=Decimal("5.0"), max_score=Decimal("10.0"))
    assert p.passing_score == Decimal("5.0")

    # Negative max_score
    with pytest.raises(DomainError, match="max_score must be > 0"):
        GradingPolicy(max_score=Decimal("0"))

    # passing_score > max_score
    with pytest.raises(DomainError, match="passing_score must be between 0 and 10.0"):
        GradingPolicy(passing_score=Decimal("11.0"), max_score=Decimal("10.0"))

    # negative_marking_factor out of range
    with pytest.raises(DomainError, match="negative_marking_factor must be in"):
        GradingPolicy(negative_marking_factor=Decimal("1.5"))


def test_grading_policy_scoring():
    policy = GradingPolicy(
        passing_score=Decimal("5.0"),
        max_score=Decimal("10.0"),
        negative_marking_factor=Decimal("0.25"),
        allow_partial_credit=True,
    )

    # 1. Correct full credit
    s_full = policy.score_item(is_correct=True, raw_ratio=Decimal("1.0"), weight=Decimal("4.0"))
    assert s_full == Decimal("4.0")

    # 2. Correct partial credit (e.g. 75% correct)
    s_part = policy.score_item(is_correct=True, raw_ratio=Decimal("0.75"), weight=Decimal("4.0"))
    assert s_part == Decimal("3.00")

    # 3. Incorrect with partial credit (e.g. 50% partial progress)
    s_inc_part = policy.score_item(is_correct=False, raw_ratio=Decimal("0.50"), weight=Decimal("4.0"))
    assert s_inc_part == Decimal("2.00")

    # 4. Incorrect with zero credit -> penalty applies
    s_inc_penalty = policy.score_item(is_correct=False, raw_ratio=Decimal("0"), weight=Decimal("4.0"))
    assert s_inc_penalty == Decimal("-1.00")  # -0.25 * 4.0

    # 5. Omitted -> 0 score, no penalty
    s_omitted = policy.score_item(is_correct=None, raw_ratio=None, weight=Decimal("4.0"))
    assert s_omitted == Decimal("0")


def test_grading_policy_aggregation_and_pass_fail():
    policy = GradingPolicy(passing_score=Decimal("5.0"), max_score=Decimal("10.0"))
    total_w = Decimal("10.0")

    # Exactly 5.0 passing score -> passed True
    scores_pass = {"q1": Decimal("3.0"), "q2": Decimal("2.0")}
    final, pct, passed = policy.aggregate_scores(scores_pass, total_w)
    assert final == Decimal("5.00")
    assert pct == Decimal("50.00")
    assert passed is True

    # 4.99 score -> passed False
    scores_fail = {"q1": Decimal("4.99")}
    final_f, pct_f, passed_f = policy.aggregate_scores(scores_fail, total_w)
    assert final_f == Decimal("4.99")
    assert pct_f == Decimal("49.90")
    assert passed_f is False

    # Negative marking causing net negative sum -> clamped at 0.00
    scores_neg = {"q1": Decimal("-2.5"), "q2": Decimal("-1.0")}
    final_neg, pct_neg, passed_neg = policy.aggregate_scores(scores_neg, total_w)
    assert final_neg == Decimal("0.00")
    assert pct_neg == Decimal("0.00")
    assert passed_neg is False


# -----------------------------------------------------------------------------
# 4. AssessmentSession Lifecycle & State Machine
# -----------------------------------------------------------------------------

def test_session_normal_lifecycle():
    now = datetime(2026, 9, 17, 10, 0, 0)
    sess = AssessmentSession(
        stable_id="session:sdm:sess:00001",
        assessment_id="assessment:sdm:as:00001",
        student_id="student:student01",
        duration_seconds=3600,  # 1 hour
    )
    assert sess.status == SessionStatus.NOT_STARTED
    assert sess.started_at is None
    assert sess.expires_at is None

    # Start
    sess.start(now=now, item_order=("q1", "q2", "q3"), seed_used=42)
    assert sess.status == SessionStatus.IN_PROGRESS
    assert sess.started_at == now
    assert sess.expires_at == now + timedelta(seconds=3600)
    assert sess.item_order == ("q1", "q2", "q3")

    # Record responses
    t1 = now + timedelta(minutes=10)
    sess.record_response(item_id="q1", answer="V = 5 V", now=t1)
    assert "q1" in sess.responses
    assert sess.responses["q1"].answer == "V = 5 V"

    t2 = now + timedelta(minutes=25)
    sess.record_response(item_id="q2", answer="R = 100 ohm", now=t2)
    assert len(sess.responses) == 2

    # Submit
    t_sub = now + timedelta(minutes=50)
    sess.submit(now=t_sub)
    assert sess.status == SessionStatus.SUBMITTED
    assert sess.submitted_at == t_sub

    # Cannot record responses or submit after submission
    with pytest.raises(DomainError, match="Cannot record response in status SUBMITTED"):
        sess.record_response(item_id="q3", answer="X", now=t_sub)

    with pytest.raises(DomainError, match="Cannot submit session in status SUBMITTED"):
        sess.submit(now=t_sub)


def test_session_expiration():
    now = datetime(2026, 9, 17, 10, 0, 0)
    sess = AssessmentSession(
        stable_id="session:sdm:sess:00002",
        assessment_id="assessment:sdm:as:00001",
        student_id="student:student02",
        duration_seconds=1800,  # 30 min
    )
    sess.start(now=now, item_order=("q1", "q2"))

    # Answering before timeout succeeds
    sess.record_response(item_id="q1", answer="Ans 1", now=now + timedelta(minutes=15))

    # Answering after timeout automatically expires session
    late_time = now + timedelta(minutes=35)
    assert sess.is_expired(late_time) is True

    with pytest.raises(DomainError, match="Session has expired; cannot record response"):
        sess.record_response(item_id="q2", answer="Ans 2", now=late_time)

    assert sess.status == SessionStatus.EXPIRED
    assert sess.submitted_at == late_time


def test_session_finalization_and_result():
    now = datetime(2026, 9, 17, 10, 0, 0)
    items = (
        AssessmentItem(item_id="q1", question_id="q:1", topic_id="topic:t1", weight=Decimal("4.0")),
        AssessmentItem(item_id="q2", question_id="q:2", topic_id="topic:t2", weight=Decimal("6.0")),
    )
    asmt = Assessment(
        stable_id="assessment:sdm:as:00001",
        subject_id="subject:sdm",
        title="Evaluacion Final",
        items=items,
        duration_min=60,
    )
    policy = GradingPolicy(passing_score=Decimal("5.0"), max_score=Decimal("10.0"))

    sess = AssessmentSession(
        stable_id="session:sdm:sess:00003",
        assessment_id=asmt.stable_id,
        student_id="student:ada",
        duration_seconds=3600,
    )
    sess.start(now=now, item_order=("q1", "q2"))
    sess.record_response(item_id="q1", answer="Correct", now=now + timedelta(minutes=10))
    sess.record_response(item_id="q2", answer="Partial", now=now + timedelta(minutes=20))
    sess.submit(now=now + timedelta(minutes=30))

    # Evaluate: q1 is fully correct, q2 gets 50% partial credit
    evaluations = {
        "q1": (True, Decimal("1.0")),
        "q2": (False, Decimal("0.5")),
    }
    result = sess.finalize_result(
        assessment=asmt,
        policy=policy,
        item_evaluations=evaluations,
        now=now + timedelta(minutes=31),
    )

    # q1: 1.0 * 4.0 = 4.0
    # q2: 0.5 * 6.0 = 3.0
    # total raw: 7.0 / 10.0 * 10 = 7.00
    assert result.total_score == Decimal("7.00")
    assert result.percentage == Decimal("70.00")
    assert result.passed is True
    assert result.item_scores["q1"] == Decimal("4.0")
    assert result.item_scores["q2"] == Decimal("3.0")
    assert sess.result == result


# -----------------------------------------------------------------------------
# 5. Security & AST Audit
# -----------------------------------------------------------------------------

def test_ast_security_and_zero_float():
    """Verify no eval, exec, subprocess, or float conversion in assessment domain."""
    pkg_dir = Path(__file__).parent.parent / "src" / "academic_core" / "domain" / "assessment"
    py_files = list(pkg_dir.glob("*.py"))
    assert len(py_files) >= 3, f"Expected at least 3 files, found: {py_files}"

    forbidden_calls = {"eval", "exec", "compile", "system", "popen"}

    for f in py_files:
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Check func name
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                    assert func_name not in forbidden_calls, f"Forbidden call {func_name} in {f.name}"
                    # Ensure no float() calls
                    assert func_name != "float", f"Float conversion forbidden in assessment domain: {f.name} line {node.lineno}"
                elif isinstance(node.func, ast.Attribute):
                    attr_name = node.func.attr
                    assert attr_name not in forbidden_calls, f"Forbidden method {attr_name} in {f.name}"
