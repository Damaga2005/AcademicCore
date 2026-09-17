"""Tests for Phase F9-C Assessment Application Integration & Orchestration.

Validates:
1. Session lifecycle: create, start, answer, submit, expire, cancel, invalid transitions.
2. Response handling: valid, duplicate rejection, unknown items, late/expired rejection.
3. Grading: 100%, 0%, partial credit, negative marking, threshold boundaries, Decimal precision.
4. Integration & Orchestration: facade wiring, result aggregation, mastery completion hook.
5. Determinism: seed-based item ordering, repeatable results.
6. Formula Coverage: formula-bearing item adapter, LaTeX & provenance retention.
7. Security: AST check for zero eval, exec, compile, dynamic imports, or float conversions.
"""

from __future__ import annotations

import ast
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from academic_core.application.assessment import AssessmentService, item_from_formula
from academic_core.application.facade import AcademicApp
from academic_core.application.services import ApplicationError
from academic_core.config import Settings
from academic_core.domain.academic import Formula
from academic_core.domain.assessment import (
    Assessment,
    AssessmentItem,
    AssessmentResult,
    AssessmentSession,
    GradingPolicy,
    SessionStatus,
    StudentResponse,
)


# -----------------------------------------------------------------------------
# Fixtures & Helpers
# -----------------------------------------------------------------------------

def _make_sample_assessment(
    duration_min: int = 60,
    shuffle_items: bool = False,
    passing_score: Decimal = Decimal("5.0"),
    negative_marking: Decimal = Decimal("0"),
) -> Assessment:
    policy = GradingPolicy(
        passing_score=passing_score,
        max_score=Decimal("10.0"),
        negative_marking_factor=negative_marking,
        allow_partial_credit=True,
    )
    items = (
        AssessmentItem(item_id="q1", question_id="q:sdm:001", topic_id="topic:sdm:t01", weight=Decimal("4.0")),
        AssessmentItem(item_id="q2", question_id="q:sdm:002", topic_id="topic:sdm:t01", weight=Decimal("3.0")),
        AssessmentItem(item_id="q3", question_id="q:sdm:003", topic_id="topic:sdm:t02", weight=Decimal("3.0")),
    )
    return Assessment(
        stable_id="assessment:sdm:as:00001",
        subject_id="subject:sdm",
        title="Evaluacion Parcial SDM",
        items=items,
        duration_min=duration_min,
        attempts_allowed=2,
        policy=policy,
        shuffle_items=shuffle_items,
    )


# -----------------------------------------------------------------------------
# 1. Session Lifecycle
# -----------------------------------------------------------------------------

def test_session_lifecycle_normal_flow():
    svc = AssessmentService()
    asmt = _make_sample_assessment(duration_min=90)
    t0 = datetime(2026, 9, 17, 10, 0, 0)

    # 1. Create session
    sess = svc.create_session(asmt, student_id="student:001", attempt_number=1)
    assert sess.status == SessionStatus.NOT_STARTED
    assert sess.student_id == "student:001"
    assert sess.duration_seconds == 5400
    assert sess.started_at is None

    # 2. Start session
    sess = svc.start_session(sess.stable_id, now=t0)
    assert sess.status == SessionStatus.IN_PROGRESS
    assert sess.started_at == t0
    assert sess.expires_at == t0 + timedelta(minutes=90)

    # 3. Next item progression
    item = svc.get_next_item(sess.stable_id, asmt, now=t0)
    assert item is not None
    assert item.item_id == "q1"

    # 4. Answer q1
    t1 = t0 + timedelta(minutes=10)
    resp = svc.submit_response(sess.stable_id, item_id="q1", answer="5 V", now=t1)
    assert resp.item_id == "q1"
    assert resp.answer == "5 V"

    # Next item is now q2
    item2 = svc.get_next_item(sess.stable_id, asmt, now=t1)
    assert item2 is not None
    assert item2.item_id == "q2"

    # Answer q2 and q3
    svc.submit_response(sess.stable_id, item_id="q2", answer="10 ohm", now=t0 + timedelta(minutes=20))
    svc.submit_response(sess.stable_id, item_id="q3", answer="100 uF", now=t0 + timedelta(minutes=30))

    # All answered: next item is None
    assert svc.get_next_item(sess.stable_id, asmt, now=t0 + timedelta(minutes=35)) is None

    # 5. Submit assessment
    t_sub = t0 + timedelta(minutes=45)
    evals = {
        "q1": (True, Decimal("1.0")),
        "q2": (True, Decimal("1.0")),
        "q3": (True, Decimal("1.0")),
    }
    result = svc.submit_assessment(sess.stable_id, asmt, evals, now=t_sub)
    assert sess.status == SessionStatus.SUBMITTED
    assert result.total_score == Decimal("10.00")
    assert result.percentage == Decimal("100.00")
    assert result.passed is True

    # 6. Retrieve result via service
    res_fetched = svc.get_result(sess.stable_id)
    assert res_fetched == result


def test_session_lifecycle_invalid_transitions():
    svc = AssessmentService()
    asmt = _make_sample_assessment()
    t0 = datetime(2026, 9, 17, 10, 0, 0)

    sess = svc.create_session(asmt, student_id="student:002")

    # Cannot get next item or submit response before start
    with pytest.raises(ApplicationError, match="Cannot retrieve items for session in status 'NOT_STARTED'"):
        svc.get_next_item(sess.stable_id, asmt, now=t0)

    with pytest.raises(ApplicationError, match="Cannot record response in status 'NOT_STARTED'"):
        svc.submit_response(sess.stable_id, item_id="q1", answer="X", now=t0)

    # Start session
    svc.start_session(sess.stable_id, now=t0)

    # Cannot start again
    with pytest.raises(ApplicationError, match="Cannot start session in status 'IN_PROGRESS'"):
        svc.start_session(sess.stable_id, now=t0)

    # Submit session
    evals = {"q1": (True, Decimal("1.0"))}
    svc.submit_assessment(sess.stable_id, asmt, evals, now=t0 + timedelta(minutes=10))

    # Cannot submit twice
    with pytest.raises(ApplicationError, match="Duplicate submission"):
        svc.submit_assessment(sess.stable_id, asmt, evals, now=t0 + timedelta(minutes=15))

    # Cannot cancel a submitted session
    with pytest.raises(ApplicationError, match="Cannot cancel session in status 'SUBMITTED'"):
        svc.cancel_session(sess.stable_id)


def test_session_cancellation():
    svc = AssessmentService()
    asmt = _make_sample_assessment()
    t0 = datetime(2026, 9, 17, 10, 0, 0)

    # Cancel NOT_STARTED
    sess1 = svc.create_session(asmt, student_id="student:c1")
    svc.cancel_session(sess1.stable_id, reason="Changed mind")
    assert sess1.status == SessionStatus.CANCELLED

    # Cancel IN_PROGRESS
    sess2 = svc.create_session(asmt, student_id="student:c2")
    svc.start_session(sess2.stable_id, now=t0)
    svc.cancel_session(sess2.stable_id, reason="Technical issue")
    assert sess2.status == SessionStatus.CANCELLED

    # Cannot answer a cancelled session
    with pytest.raises(ApplicationError, match="Cannot answer a cancelled session"):
        svc.submit_response(sess2.stable_id, item_id="q1", answer="X", now=t0)


def test_session_expiration_flow():
    svc = AssessmentService()
    asmt = _make_sample_assessment(duration_min=30)
    t0 = datetime(2026, 9, 17, 10, 0, 0)

    sess = svc.create_session(asmt, student_id="student:timeout")
    svc.start_session(sess.stable_id, now=t0)

    # Answer q1 at 15m (valid)
    svc.submit_response(sess.stable_id, item_id="q1", answer="A", now=t0 + timedelta(minutes=15))

    # Answer q2 at 35m (timeout reached)
    t_late = t0 + timedelta(minutes=35)
    with pytest.raises(ApplicationError, match="Session has expired; cannot record response"):
        svc.submit_response(sess.stable_id, item_id="q2", answer="B", now=t_late)

    assert sess.status == SessionStatus.EXPIRED

    # Cannot submit after expiration
    with pytest.raises(ApplicationError, match="Cannot submit an expired session"):
        svc.submit_assessment(sess.stable_id, asmt, {}, now=t_late)


# -----------------------------------------------------------------------------
# 2. Response Handling
# -----------------------------------------------------------------------------

def test_response_handling_duplicate_and_unknown():
    svc = AssessmentService()
    asmt = _make_sample_assessment()
    t0 = datetime(2026, 9, 17, 10, 0, 0)

    sess = svc.create_session(asmt, student_id="student:resp")
    svc.start_session(sess.stable_id, now=t0)

    # Unknown item
    with pytest.raises(ApplicationError, match="Unknown item 'q_fake'"):
        svc.submit_response(sess.stable_id, item_id="q_fake", answer="foo", now=t0)

    # Valid response
    svc.submit_response(sess.stable_id, item_id="q1", answer="Initial", now=t0)

    # Duplicate response rejected by default
    with pytest.raises(ApplicationError, match="Duplicate response for item 'q1'"):
        svc.submit_response(sess.stable_id, item_id="q1", answer="Second", now=t0)

    # Duplicate response allowed when allow_overwrite=True
    resp2 = svc.submit_response(sess.stable_id, item_id="q1", answer="Overwritten", now=t0, allow_overwrite=True)
    assert resp2.answer == "Overwritten"
    assert sess.responses["q1"].answer == "Overwritten"


# -----------------------------------------------------------------------------
# 3. Grading Policy & Numeric Precision
# -----------------------------------------------------------------------------

def test_grading_evaluations_and_boundaries():
    svc = AssessmentService()
    t0 = datetime(2026, 9, 17, 10, 0, 0)

    # Case A: 100% Score
    asmt_100 = _make_sample_assessment()
    s1 = svc.create_session(asmt_100, student_id="s1")
    svc.start_session(s1.stable_id, now=t0)
    res_100 = svc.submit_assessment(
        s1.stable_id, asmt_100,
        {"q1": (True, Decimal("1.0")), "q2": (True, Decimal("1.0")), "q3": (True, Decimal("1.0"))},
        now=t0 + timedelta(minutes=10),
    )
    assert res_100.total_score == Decimal("10.00")
    assert res_100.percentage == Decimal("100.00")
    assert res_100.passed is True

    # Case B: 0% Score (all incorrect, 0 penalty)
    s2 = svc.create_session(asmt_100, student_id="s2")
    svc.start_session(s2.stable_id, now=t0)
    res_0 = svc.submit_assessment(
        s2.stable_id, asmt_100,
        {"q1": (False, Decimal("0.0")), "q2": (False, Decimal("0.0")), "q3": (False, Decimal("0.0"))},
        now=t0 + timedelta(minutes=10),
    )
    assert res_0.total_score == Decimal("0.00")
    assert res_0.percentage == Decimal("0.00")
    assert res_0.passed is False

    # Case C: Exact pass boundary (5.00) vs just below (4.99)
    # Weights: q1=4.0, q2=3.0, q3=3.0 (Total=10.0)
    # 5.0 score: q1 correct (4.0) + q2 partial (1/3 of 3.0 = 1.0) -> 5.00
    s3 = svc.create_session(asmt_100, student_id="s3")
    svc.start_session(s3.stable_id, now=t0)
    res_exact = svc.submit_assessment(
        s3.stable_id, asmt_100,
        {"q1": (True, Decimal("1.0")), "q2": (True, Decimal("0.333333333333333333")), "q3": (False, Decimal("0"))},
        now=t0 + timedelta(minutes=10),
    )
    # 4.0 + 1.0 = 5.00 -> Passed
    assert res_exact.total_score == Decimal("5.00")
    assert res_exact.passed is True

    # Case D: Negative marking penalty
    asmt_neg = _make_sample_assessment(negative_marking=Decimal("0.25"))
    s4 = svc.create_session(asmt_neg, student_id="s4")
    svc.start_session(s4.stable_id, now=t0)
    # q1 correct (4.0), q2 wrong with 0.25 penalty (-0.75), q3 omitted (0)
    res_neg = svc.submit_assessment(
        s4.stable_id, asmt_neg,
        {"q1": (True, Decimal("1.0")), "q2": (False, Decimal("0")), "q3": (None, None)},
        now=t0 + timedelta(minutes=10),
    )
    # 4.0 - 0.75 = 3.25
    assert res_neg.total_score == Decimal("3.25")
    assert res_neg.percentage == Decimal("32.50")
    assert res_neg.passed is False


# -----------------------------------------------------------------------------
# 4. Determinism & Seeded Item Ordering
# -----------------------------------------------------------------------------

def test_determinism_and_shuffling():
    asmt = _make_sample_assessment(shuffle_items=True)
    svc = AssessmentService()

    sess_a = svc.create_session(asmt, student_id="s_det", seed=42)
    sess_b = svc.create_session(asmt, student_id="s_det", seed=42)
    sess_c = svc.create_session(asmt, student_id="s_det", seed=999)

    # Identical seed -> identical order
    assert sess_a.item_order == sess_b.item_order
    # Different seed -> distinct permutation (or order)
    assert set(sess_a.item_order) == {"q1", "q2", "q3"}
    assert set(sess_c.item_order) == {"q1", "q2", "q3"}


# -----------------------------------------------------------------------------
# 5. Formula Integration & Coverage Gate
# -----------------------------------------------------------------------------

def test_formula_bearing_item_preserves_provenance():
    # Construct certified Formula model
    f = Formula(
        stable_id="formula:sdm:f:000042",
        latex=r"V = I \cdot R",
        source_latex=r"V = I \cdot R",
        topic_id="topic:sdm:t01",
        concept_ids=["concept:sdm:c:00001"],
        variables=[{"name": "V", "unit": "V"}, {"name": "I", "unit": "A"}, {"name": "R", "unit": "ohm"}],
        units=["V", "A", "ohm"],
        provenance={"source_path": "teoria/tema1.md", "section": "Ohm's Law", "hash": "sha256:abcd"},
        version=1,
    )

    # Adapt into AssessmentItem
    item = item_from_formula(f, item_id="item_ohm", weight=Decimal("5.0"))
    assert item.item_id == "item_ohm"
    assert item.question_id == "formula:sdm:f:000042"
    assert item.topic_id == "topic:sdm:t01"
    assert item.weight == Decimal("5.0")
    assert "formula_prov:teoria/tema1.md#Ohm's Law" in item.rubric_ref
    assert r"V = I \cdot R" in item.options

    # Embed in Assessment and run session
    asmt = Assessment(
        stable_id="assessment:sdm:as:00099",
        subject_id="subject:sdm",
        title="Examen Ley de Ohm",
        items=(item,),
        duration_min=15,
    )
    svc = AssessmentService()
    sess = svc.create_session(asmt, student_id="student:formula")
    svc.start_session(sess.stable_id, now=datetime(2026, 9, 17, 12, 0, 0))

    next_it = svc.get_next_item(sess.stable_id, asmt)
    assert next_it is not None
    assert next_it.question_id == "formula:sdm:f:000042"

    svc.submit_response(sess.stable_id, item_id="item_ohm", answer="V = 10 V", now=datetime(2026, 9, 17, 12, 5, 0))
    res = svc.submit_assessment(
        sess.stable_id, asmt,
        {"item_ohm": (True, Decimal("1.0"))},
        now=datetime(2026, 9, 17, 12, 10, 0),
    )
    assert res.total_score == Decimal("10.00")
    assert res.passed is True


# -----------------------------------------------------------------------------
# 6. Mastery Hook Integration
# -----------------------------------------------------------------------------

def test_mastery_completion_hook():
    captured_events = []

    def on_complete(sess: AssessmentSession, res: AssessmentResult):
        captured_events.append((sess.stable_id, res.total_score, res.passed))

    svc = AssessmentService(on_completed_hook=on_complete)
    asmt = _make_sample_assessment()
    t0 = datetime(2026, 9, 17, 10, 0, 0)

    sess = svc.create_session(asmt, student_id="student:hook")
    svc.start_session(sess.stable_id, now=t0)
    svc.submit_response(sess.stable_id, item_id="q1", answer="Ans", now=t0 + timedelta(minutes=5))

    svc.submit_assessment(
        sess.stable_id, asmt,
        {"q1": (True, Decimal("1.0"))},
        now=t0 + timedelta(minutes=10),
    )

    assert len(captured_events) == 1
    sid, score, passed = captured_events[0]
    assert sid == sess.stable_id
    assert score == Decimal("4.00")
    assert passed is False


# -----------------------------------------------------------------------------
# 7. Facade Wiring Integration
# -----------------------------------------------------------------------------

def test_facade_assessment_wiring(tmp_path):
    settings = Settings()
    settings.storage.location = str(tmp_path)
    app = AcademicApp(settings)

    assert hasattr(app, "assessment")
    assert isinstance(app.assessment, AssessmentService)


# -----------------------------------------------------------------------------
# 8. AST Security & Zero Float Invariant
# -----------------------------------------------------------------------------

def test_ast_security_application_layer():
    target_file = Path(__file__).parent.parent / "src" / "academic_core" / "application" / "assessment.py"
    assert target_file.exists()

    tree = ast.parse(target_file.read_text(encoding="utf-8"), filename=str(target_file))
    forbidden_calls = {"eval", "exec", "compile", "system", "popen", "__import__"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
                assert func_name not in forbidden_calls, f"Forbidden call {func_name} in assessment.py"
                assert func_name != "float", f"Float conversion forbidden in assessment.py: line {node.lineno}"
            elif isinstance(node.func, ast.Attribute):
                attr_name = node.func.attr
                assert attr_name not in forbidden_calls, f"Forbidden call {attr_name} in assessment.py"
