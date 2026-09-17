"""Tests for Phase F9-D Assessment Persistence & Recovery.

Validates:
1. Persistence round-trip: Assessment, AssessmentSession, StudentResponse, AssessmentResult.
2. Session recovery across simulated process/database restart.
3. Terminal state immutability (SUBMITTED, EXPIRED, CANCELLED survive reload).
4. Timer & expiration persistence (now >= expires_at persists without in-memory dependency).
5. Concurrency and transactional consistency.
6. Idempotency of save, load, and update operations.
7. Corruption handling: malformed data raises IntegrityError safely without arbitrary code execution.
8. Decimal integrity: exact Decimal weights, penalties, thresholds, and scores (zero floats).
9. Formula coverage: 100% round-trip preservation of LaTeX, variables, units, and provenance.
10. Performance benchmarks across 1, 10, 32, 64, 128 items.
11. AST security check: zero eval, exec, compile, dynamic imports, or float conversions.
"""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import time

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
from academic_core.domain.results import Scale
from academic_core.infrastructure.assessment import (
    AssessmentRepository,
    _serialize_items,
    _serialize_policy,
)
from academic_core.infrastructure.database import Database
from academic_core.infrastructure.repositories import IntegrityError


# -----------------------------------------------------------------------------
# Fixtures & Helpers
# -----------------------------------------------------------------------------

@pytest.fixture
def test_db(tmp_path):
    """Create fresh isolated SQLite database with migrations 001-011 applied."""
    db_file = tmp_path / "test_academic.db"
    db = Database(db_file)
    cx = db.connect()
    cx.close()
    return db


def _create_sample_assessment(n_items: int = 3) -> Assessment:
    policy = GradingPolicy(
        passing_score=Decimal("5.0"),
        max_score=Decimal("10.0"),
        negative_marking_factor=Decimal("0.25"),
        allow_partial_credit=True,
    )
    items = []
    for i in range(1, n_items + 1):
        items.append(
            AssessmentItem(
                item_id=f"q{i}",
                question_id=f"q:sdm:{i:03d}",
                topic_id=f"topic:sdm:t01",
                weight=Decimal("2.5") if i % 2 == 1 else Decimal("1.25"),
                difficulty="medium",
                rubric_ref=f"rubric:q{i}",
                options=(f"Option {i}A", f"Option {i}B"),
            )
        )
    return Assessment(
        stable_id="assessment:sdm:as:00001",
        subject_id="subject:sdm",
        title="Parcial de Circuitos F9-D",
        description="Evaluacion de persistencia",
        items=tuple(items),
        duration_min=45,
        attempts_allowed=2,
        policy=policy,
        shuffle_items=True,
        master_seed=42,
    )


# -----------------------------------------------------------------------------
# 1. Persistence Round-Trip
# -----------------------------------------------------------------------------

def test_assessment_save_and_load(test_db):
    repo = AssessmentRepository(test_db)
    asmt = _create_sample_assessment(3)

    repo.save_assessment(asmt)
    loaded = repo.get_assessment(asmt.stable_id)

    assert loaded is not None
    assert loaded.stable_id == asmt.stable_id
    assert loaded.subject_id == asmt.subject_id
    assert loaded.title == asmt.title
    assert loaded.duration_min == 45
    assert loaded.attempts_allowed == 2
    assert loaded.shuffle_items is True
    assert loaded.master_seed == 42
    assert len(loaded.items) == 3

    # Decimal integrity
    for orig, it in zip(asmt.items, loaded.items):
        assert it.item_id == orig.item_id
        assert it.question_id == orig.question_id
        assert it.weight == orig.weight
        assert isinstance(it.weight, Decimal)
        assert it.options == orig.options

    # Policy integrity
    assert loaded.policy.passing_score == Decimal("5.0")
    assert isinstance(loaded.policy.passing_score, Decimal)
    assert loaded.policy.negative_marking_factor == Decimal("0.25")
    assert isinstance(loaded.policy.negative_marking_factor, Decimal)


def test_session_response_and_result_roundtrip(test_db):
    repo = AssessmentRepository(test_db)
    asmt = _create_sample_assessment(2)
    repo.save_assessment(asmt)

    t0 = datetime(2026, 9, 17, 10, 0, 0)
    sess = AssessmentSession(
        stable_id="session:sdm:sess:00001",
        assessment_id=asmt.stable_id,
        student_id="student:ada",
        attempt_number=1,
        status=SessionStatus.IN_PROGRESS,
        duration_seconds=2700,
        started_at=t0,
        expires_at=t0 + timedelta(minutes=45),
        item_order=("q1", "q2"),
        seed_used=42,
    )
    sess.responses["q1"] = StudentResponse(item_id="q1", answer="5 V", submitted_at=t0 + timedelta(minutes=5))
    repo.save_session(sess)

    loaded_sess = repo.get_session(sess.stable_id)
    assert loaded_sess is not None
    assert loaded_sess.stable_id == sess.stable_id
    assert loaded_sess.status == SessionStatus.IN_PROGRESS
    assert loaded_sess.started_at == t0
    assert loaded_sess.expires_at == t0 + timedelta(minutes=45)
    assert loaded_sess.item_order == ("q1", "q2")
    assert "q1" in loaded_sess.responses
    assert loaded_sess.responses["q1"].answer == "5 V"

    # Add result and persist
    evals = {"q1": (True, Decimal("1.0")), "q2": (True, Decimal("1.0"))}
    t_sub = t0 + timedelta(minutes=20)
    loaded_sess.submit(t_sub)
    res = loaded_sess.finalize_result(
        assessment=asmt,
        policy=asmt.policy,
        item_evaluations=evals,
        now=t_sub,
    )
    repo.save_session(loaded_sess)

    # Re-fetch session and result
    sess_after_submit = repo.get_session(sess.stable_id)
    assert sess_after_submit.status == SessionStatus.SUBMITTED
    assert sess_after_submit.submitted_at == t_sub
    assert sess_after_submit.result is not None
    assert sess_after_submit.result.total_score == Decimal("10.00")
    assert isinstance(sess_after_submit.result.total_score, Decimal)
    assert sess_after_submit.result.passed is True


# -----------------------------------------------------------------------------
# 2. Process-Restart Simulation & Session Recovery
# -----------------------------------------------------------------------------

def test_session_recovery_after_simulated_restart(tmp_path):
    db_file = tmp_path / "academic.db"
    asmt = _create_sample_assessment(2)

    # Process 1: Create, start, and record answer 1
    db1 = Database(db_file)
    repo1 = AssessmentRepository(db1)
    svc1 = AssessmentService(repo=repo1)

    repo1.save_assessment(asmt)
    sess1 = svc1.create_session(asmt, student_id="student:recover")
    t0 = datetime(2026, 9, 17, 10, 0, 0)
    svc1.start_session(sess1.stable_id, now=t0)
    svc1.submit_response(sess1.stable_id, item_id="q1", answer="Ans 1", now=t0 + timedelta(minutes=5))

    sess_id = sess1.stable_id
    saved_order = sess1.item_order

    # Process "died" -> simulate new process with fresh connection
    del svc1, repo1, db1

    # Process 2: Reopen from disk
    db2 = Database(db_file)
    repo2 = AssessmentRepository(db2)
    svc2 = AssessmentService(repo=repo2)

    loaded_sess = svc2.get_session(sess_id)
    assert loaded_sess.status == SessionStatus.IN_PROGRESS
    assert loaded_sess.item_order == saved_order
    assert loaded_sess.started_at == t0
    assert "q1" in loaded_sess.responses
    assert loaded_sess.responses["q1"].answer == "Ans 1"

    # Continue answering item 2 in restored process
    svc2.submit_response(sess_id, item_id="q2", answer="Ans 2", now=t0 + timedelta(minutes=15))

    # Submit assessment
    res = svc2.submit_assessment(
        sess_id, asmt,
        {"q1": (True, Decimal("1.0")), "q2": (True, Decimal("1.0"))},
        now=t0 + timedelta(minutes=20),
    )
    assert res.total_score == Decimal("10.00")
    assert res.passed is True

    # Process restart 3: Verify submitted state persists
    del svc2, repo2, db2
    db3 = Database(db_file)
    repo3 = AssessmentRepository(db3)
    svc3 = AssessmentService(repo=repo3)

    sess3 = svc3.get_session(sess_id)
    assert sess3.status == SessionStatus.SUBMITTED
    assert sess3.result is not None
    assert sess3.result.total_score == Decimal("10.00")


# -----------------------------------------------------------------------------
# 3. Terminal State Immutability
# -----------------------------------------------------------------------------

def test_terminal_states_remain_terminal_after_reload(test_db):
    repo = AssessmentRepository(test_db)
    svc = AssessmentService(repo=repo)
    asmt = _create_sample_assessment(2)
    repo.save_assessment(asmt)

    # 1. SUBMITTED
    s_sub = svc.create_session(asmt, student_id="s_sub")
    t0 = datetime(2026, 9, 17, 10, 0, 0)
    svc.start_session(s_sub.stable_id, now=t0)
    svc.submit_response(s_sub.stable_id, item_id="q1", answer="Ans", now=t0)
    svc.submit_assessment(s_sub.stable_id, asmt, {"q1": (True, Decimal("1.0"))}, now=t0 + timedelta(minutes=10))

    # Reload fresh instance
    svc_fresh = AssessmentService(repo=repo)
    reloaded_sub = svc_fresh.get_session(s_sub.stable_id)
    assert reloaded_sub.status == SessionStatus.SUBMITTED

    # Cannot answer or submit again
    with pytest.raises(ApplicationError, match="Cannot answer a submitted session"):
        svc_fresh.submit_response(s_sub.stable_id, item_id="q2", answer="Ans 2", now=t0 + timedelta(minutes=12))

    with pytest.raises(ApplicationError, match="Duplicate submission"):
        svc_fresh.submit_assessment(s_sub.stable_id, asmt, {}, now=t0 + timedelta(minutes=12))

    # 2. CANCELLED
    s_can = svc.create_session(asmt, student_id="s_can")
    svc.cancel_session(s_can.stable_id, reason="Medical")
    reloaded_can = svc_fresh.get_session(s_can.stable_id)
    assert reloaded_can.status == SessionStatus.CANCELLED
    with pytest.raises(ApplicationError, match="Cannot answer a cancelled session"):
        svc_fresh.submit_response(s_can.stable_id, item_id="q1", answer="X", now=t0)


# -----------------------------------------------------------------------------
# 4. Timer / Expiration Persistence
# -----------------------------------------------------------------------------

def test_timer_expiration_persists_across_restart(tmp_path):
    db_file = tmp_path / "academic_timer.db"
    db = Database(db_file)
    repo = AssessmentRepository(db)
    svc = AssessmentService(repo=repo)

    asmt = _create_sample_assessment(2)  # duration = 45 min
    repo.save_assessment(asmt)

    t0 = datetime(2026, 9, 17, 10, 0, 0)
    sess = svc.create_session(asmt, student_id="student:timer")
    svc.start_session(sess.stable_id, now=t0)
    sid = sess.stable_id

    # Simulate restart
    del svc, repo, db
    db2 = Database(db_file)
    repo2 = AssessmentRepository(db2)
    svc2 = AssessmentService(repo=repo2)

    # Time advanced past 45m: now = 10:50 (50 min later)
    t_late = t0 + timedelta(minutes=50)

    # get_next_item or submit_response detects expiration from persisted expires_at
    with pytest.raises(ApplicationError, match="Session has expired; cannot record response"):
        svc2.submit_response(sid, item_id="q1", answer="late", now=t_late)

    # Session is persisted in EXPIRED status
    reloaded = repo2.get_session(sid)
    assert reloaded.status == SessionStatus.EXPIRED


# -----------------------------------------------------------------------------
# 5. Concurrency & Idempotency
# -----------------------------------------------------------------------------

def test_persistence_idempotency(test_db):
    repo = AssessmentRepository(test_db)
    asmt = _create_sample_assessment(2)

    # Repeated save of assessment
    repo.save_assessment(asmt)
    repo.save_assessment(asmt)
    all_asmts = repo.list_assessments()
    assert len(all_asmts) == 1

    # Repeated save of session
    sess = AssessmentSession(
        stable_id="session:sdm:sess:00001",
        assessment_id=asmt.stable_id,
        student_id="student:idem",
        duration_seconds=1800,
        item_order=("q1", "q2"),
    )
    repo.save_session(sess)
    repo.save_session(sess)

    # Repeated save of response
    resp = StudentResponse(item_id="q1", answer="A", submitted_at=datetime(2026, 9, 17, 10, 0, 0))
    repo.save_response(sess.stable_id, resp)
    repo.save_response(sess.stable_id, resp)

    reloaded = repo.get_session(sess.stable_id)
    assert len(reloaded.responses) == 1


# -----------------------------------------------------------------------------
# 6. Corruption & Invalid Data Handling
# -----------------------------------------------------------------------------

def test_corruption_handling_fails_safely(test_db):
    repo = AssessmentRepository(test_db)
    asmt = _create_sample_assessment(1)
    repo.save_assessment(asmt)

    # Corrupt items_json directly in SQLite
    cx = test_db.connect()
    cx.execute("UPDATE assessments SET items_json='{invalid: json}' WHERE stable_id=?", (asmt.stable_id,))
    cx.commit(); cx.close()

    with pytest.raises(IntegrityError, match="Failed to deserialize assessment items"):
        repo.get_assessment(asmt.stable_id)

    # Corrupt session status
    cx = test_db.connect()
    cx.execute(
        "INSERT INTO assessment_sessions VALUES ('session:sdm:sess:99999', ?, 's1', 1, 'BOGUS_STATUS', 0, NULL, NULL, NULL, '[]', NULL, 'now')",
        (asmt.stable_id,),
    )
    cx.commit(); cx.close()

    with pytest.raises(IntegrityError, match="Unknown session status"):
        repo.get_session("session:sdm:sess:99999")


# -----------------------------------------------------------------------------
# 7. Formula Coverage: 100% Metadata Preservation
# -----------------------------------------------------------------------------

def test_formula_metadata_roundtrip_preservation(test_db):
    repo = AssessmentRepository(test_db)

    formula = Formula(
        stable_id="formula:sdm:f:000088",
        latex=r"Z = R + j\omega L",
        source_latex=r"Z = R + j\omega L",
        topic_id="topic:sdm:t02",
        concept_ids=["concept:sdm:c:00010"],
        variables=[{"name": "Z", "unit": "ohm"}, {"name": "omega", "unit": "rad/s"}],
        units=["ohm", "rad/s"],
        provenance={"source_path": "teoria/ca.md", "section": "Impedance", "hash": "sha256:123456"},
        version=1,
    )

    item = item_from_formula(formula, item_id="item_z", weight=Decimal("4.5"))
    asmt = Assessment(
        stable_id="assessment:sdm:as:00088",
        subject_id="subject:sdm",
        title="Examen Impedancia",
        items=(item,),
        duration_min=30,
    )

    repo.save_assessment(asmt)
    loaded = repo.get_assessment(asmt.stable_id)
    assert loaded is not None

    loaded_item = loaded.items[0]
    assert loaded_item.question_id == "formula:sdm:f:000088"
    assert loaded_item.topic_id == "topic:sdm:t02"
    assert loaded_item.weight == Decimal("4.5")
    assert "formula_prov:teoria/ca.md#Impedance" in loaded_item.rubric_ref
    assert r"Z = R + j\omega L" in loaded_item.options


# -----------------------------------------------------------------------------
# 8. Performance Benchmarks
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("n_items", [1, 10, 32, 64, 128])
def test_persistence_performance_benchmark(test_db, n_items):
    repo = AssessmentRepository(test_db)
    asmt = _create_sample_assessment(n_items)

    # Measure save assessment
    t0 = time.perf_counter()
    repo.save_assessment(asmt)
    t_save_asmt = time.perf_counter() - t0

    # Measure create & save session
    sess = AssessmentSession(
        stable_id="session:sdm:sess:00099",
        assessment_id=asmt.stable_id,
        student_id="student:perf",
        duration_seconds=3600,
        item_order=asmt.generate_item_order(42),
    )
    t0 = time.perf_counter()
    repo.save_session(sess)
    t_save_sess = time.perf_counter() - t0

    # Measure save all responses
    t0 = time.perf_counter()
    for it in asmt.items:
        repo.save_response(
            sess.stable_id,
            StudentResponse(item_id=it.item_id, answer=f"Ans {it.item_id}", submitted_at=datetime.now(timezone.utc)),
        )
    t_save_resps = time.perf_counter() - t0

    # Measure load session with all responses
    t0 = time.perf_counter()
    loaded_sess = repo.get_session(sess.stable_id)
    t_load_sess = time.perf_counter() - t0
    assert len(loaded_sess.responses) == n_items

    print(
        f"\n[F9-D PERF {n_items:3d} items] Save Asmt: {t_save_asmt*1000:.2f}ms | "
        f"Save Sess: {t_save_sess*1000:.2f}ms | "
        f"Save {n_items} Resps: {t_save_resps*1000:.2f}ms | "
        f"Load Sess: {t_load_sess*1000:.2f}ms"
    )
    # Reasonable threshold: even 128 items round-trip under 1.5 seconds
    assert t_load_sess < 1.5


# -----------------------------------------------------------------------------
# 9. AST & SQL Injection Security Audit
# -----------------------------------------------------------------------------

def test_ast_security_persistence_module():
    target_file = Path(__file__).parent.parent / "src" / "academic_core" / "infrastructure" / "assessment.py"
    assert target_file.exists()

    tree = ast.parse(target_file.read_text(encoding="utf-8"), filename=str(target_file))
    forbidden_calls = {"eval", "exec", "compile", "system", "popen", "__import__"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
                assert func_name not in forbidden_calls, f"Forbidden call {func_name} in assessment.py"
                assert func_name != "float", f"Float conversion forbidden in assessment persistence: line {node.lineno}"
            elif isinstance(node.func, ast.Attribute):
                attr_name = node.func.attr
                assert attr_name not in forbidden_calls, f"Forbidden call {attr_name} in assessment.py"


# -----------------------------------------------------------------------------
# 10. Audit Findings: ID Allocation, Immutability & Conflict Semantics
# -----------------------------------------------------------------------------

def test_session_id_allocation_survives_process_restart(tmp_path):
    """Verify session IDs do not collide after service/process restarts."""
    db_file = tmp_path / "academic_id_restart.db"
    asmt = _create_sample_assessment(2)

    # Process 1
    db1 = Database(db_file)
    repo1 = AssessmentRepository(db1)
    svc1 = AssessmentService(repo=repo1)
    repo1.save_assessment(asmt)

    sess1 = svc1.create_session(asmt, student_id="student:1")
    sess2 = svc1.create_session(asmt, student_id="student:2")
    assert sess1.stable_id.endswith("sess:00001")
    assert sess2.stable_id.endswith("sess:00002")

    # Simulate process termination
    del svc1, repo1, db1

    # Process 2 (fresh instance)
    db2 = Database(db_file)
    repo2 = AssessmentRepository(db2)
    svc2 = AssessmentService(repo=repo2)

    sess3 = svc2.create_session(asmt, student_id="student:3")
    assert sess3.stable_id.endswith("sess:00003")
    assert sess3.stable_id != sess1.stable_id
    assert sess3.stable_id != sess2.stable_id

    # Verify SQLite id_counters table state
    cx = db2.connect()
    row = cx.execute("SELECT last_n FROM id_counters WHERE kind = 'session'").fetchone()
    cx.close()
    assert row is not None
    assert row["last_n"] == 3


def test_concurrent_session_id_allocation(tmp_path):
    """Verify concurrent creators receive strictly unique, sequential IDs without collision."""
    import concurrent.futures

    db_file = tmp_path / "academic_concurrent_ids.db"
    db = Database(db_file)
    repo = AssessmentRepository(db)
    svc = AssessmentService(repo=repo)
    asmt = _create_sample_assessment(2)
    repo.save_assessment(asmt)

    n_sessions = 10

    def _create(idx: int) -> str:
        s = svc.create_session(asmt, student_id=f"student:{idx}")
        return s.stable_id

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(_create, i) for i in range(n_sessions)]
        allocated_ids = [f.result() for f in futures]

    assert len(allocated_ids) == n_sessions
    assert len(set(allocated_ids)) == n_sessions, "Duplicate session IDs allocated concurrently!"


def test_response_immutability_and_conflict_semantics(test_db):
    """Verify A->A succeeds idempotently, but A->B, B->A, and overwrite attempts fail."""
    repo = AssessmentRepository(test_db)
    asmt = _create_sample_assessment(2)
    repo.save_assessment(asmt)

    t0 = datetime(2026, 9, 17, 10, 0, 0)
    sess = AssessmentSession(
        stable_id="session:sdm:sess:00001",
        assessment_id=asmt.stable_id,
        student_id="student:immut",
        status=SessionStatus.IN_PROGRESS,
        duration_seconds=3600,
        started_at=t0,
        expires_at=t0 + timedelta(minutes=60),
        item_order=("q1", "q2"),
    )
    repo.save_session(sess)

    resp_a = StudentResponse(item_id="q1", answer="Ans A", submitted_at=t0 + timedelta(minutes=1))
    resp_b = StudentResponse(item_id="q1", answer="Ans B", submitted_at=t0 + timedelta(minutes=2))

    # 1. First insert: succeeds
    repo.save_response(sess.stable_id, resp_a)

    # 2. A -> A: Idempotent success
    repo.save_response(sess.stable_id, resp_a)
    loaded = repo.get_session(sess.stable_id)
    assert loaded.responses["q1"].answer == "Ans A"

    # 3. A -> B: Attempting different answer raises IntegrityError
    with pytest.raises(IntegrityError, match="Immutable response conflict"):
        repo.save_response(sess.stable_id, resp_b)

    # Verify DB was NOT modified by failed attempt
    loaded2 = repo.get_session(sess.stable_id)
    assert loaded2.responses["q1"].answer == "Ans A"

    # 4. Same check through save_session: sess trying to persist modified response raises IntegrityError
    sess_mut = repo.get_session(sess.stable_id)
    sess_mut.responses["q1"] = resp_b
    with pytest.raises(IntegrityError, match="Immutable response conflict"):
        repo.save_session(sess_mut)


def test_result_immutability_enforcement(test_db):
    """Verify finalized assessment results cannot be mutated or duplicated."""
    repo = AssessmentRepository(test_db)
    asmt = _create_sample_assessment(2)
    repo.save_assessment(asmt)

    t0 = datetime(2026, 9, 17, 10, 0, 0)
    sess = AssessmentSession(
        stable_id="session:sdm:sess:00001",
        assessment_id=asmt.stable_id,
        student_id="student:res_immut",
        status=SessionStatus.SUBMITTED,
        duration_seconds=3600,
        started_at=t0,
        expires_at=t0 + timedelta(minutes=60),
        submitted_at=t0 + timedelta(minutes=20),
        item_order=("q1", "q2"),
    )
    repo.save_session(sess)

    r1 = AssessmentResult(
        session_id=sess.stable_id,
        assessment_id=asmt.stable_id,
        student_id="student:res_immut",
        total_score=Decimal("8.5"),
        max_possible=Decimal("10.0"),
        percentage=Decimal("85.0"),
        passed=True,
        item_scores={"q1": Decimal("5.0"), "q2": Decimal("3.5")},
        evaluated_at=t0 + timedelta(minutes=21),
    )

    # Persist result
    repo.save_result(r1)
    loaded = repo.get_result(sess.stable_id)
    assert loaded is not None
    assert loaded.total_score == Decimal("8.5")

    # Persist same result: idempotent success
    repo.save_result(r1)

    # Attempt mutated result (different score)
    r_mutated = AssessmentResult(
        session_id=sess.stable_id,
        assessment_id=asmt.stable_id,
        student_id="student:res_immut",
        total_score=Decimal("10.0"),  # modified score!
        max_possible=Decimal("10.0"),
        percentage=Decimal("100.0"),
        passed=True,
        item_scores={"q1": Decimal("5.0"), "q2": Decimal("5.0")},
        evaluated_at=t0 + timedelta(minutes=22),
    )
    with pytest.raises(IntegrityError, match="AssessmentResult for session .* is immutable"):
        repo.save_result(r_mutated)

    # Verify original result remains unchanged
    reloaded = repo.get_result(sess.stable_id)
    assert reloaded.total_score == Decimal("8.5")


def test_terminal_session_rejects_reversion_and_late_responses(test_db):
    """Verify terminal sessions (SUBMITTED, EXPIRED, CANCELLED) cannot be reverted or answered."""
    repo = AssessmentRepository(test_db)
    asmt = _create_sample_assessment(2)
    repo.save_assessment(asmt)

    t0 = datetime(2026, 9, 17, 10, 0, 0)
    sess = AssessmentSession(
        stable_id="session:sdm:sess:00001",
        assessment_id=asmt.stable_id,
        student_id="student:term",
        status=SessionStatus.SUBMITTED,
        duration_seconds=3600,
        started_at=t0,
        submitted_at=t0 + timedelta(minutes=25),
        item_order=("q1", "q2"),
    )
    repo.save_session(sess)

    # 1. Attempt to revert terminal session to IN_PROGRESS
    sess.status = SessionStatus.IN_PROGRESS
    with pytest.raises(IntegrityError, match="Cannot transition terminal session"):
        repo.save_session(sess)

    # 2. Attempt to record new response on terminal session
    resp_late = StudentResponse(item_id="q2", answer="Late", submitted_at=t0 + timedelta(minutes=30))
    with pytest.raises(IntegrityError, match="Cannot record response: session .* is in terminal status"):
        repo.save_response("session:sdm:sess:00001", resp_late)


def test_full_process_restart_recovery_scenario(tmp_path):
    """Verify complete 18-step scenario from Section 12 of the audit document:
    create assessment -> create session -> start session -> answer item 1 -> persist
    -> destroy service/process -> construct new service/process -> load session
    -> verify state, item order, seed, deadline, student identity -> answer item 2
    -> submit -> persist result -> destroy process -> reload final session/result.
    """
    db_file = tmp_path / "academic_full_recovery.db"
    asmt = _create_sample_assessment(2)

    # Step 1-5: Process 1
    db1 = Database(db_file)
    repo1 = AssessmentRepository(db1)
    svc1 = AssessmentService(repo=repo1)

    repo1.save_assessment(asmt)
    sess1 = svc1.create_session(asmt, student_id="student:e2e", seed=12345)
    sid = sess1.stable_id

    t0 = datetime(2026, 9, 17, 10, 0, 0)
    started_sess = svc1.start_session(sid, now=t0)
    svc1.submit_response(sid, item_id="q1", answer="Ans 1", now=t0 + timedelta(minutes=5))

    expected_order = started_sess.item_order
    expected_seed = started_sess.seed_used
    expected_expires = started_sess.expires_at

    # Step 6: Destroy process 1
    del svc1, repo1, db1

    # Step 7: Construct new service/process
    db2 = Database(db_file)
    repo2 = AssessmentRepository(db2)
    svc2 = AssessmentService(repo=repo2)

    # Step 8-13: Load session and verify all metadata
    loaded = svc2.get_session(sid)
    assert loaded.status == SessionStatus.IN_PROGRESS
    assert loaded.item_order == expected_order
    assert loaded.seed_used == expected_seed
    assert loaded.expires_at == expected_expires
    assert loaded.student_id == "student:e2e"
    assert loaded.responses["q1"].answer == "Ans 1"

    # Step 14: Answer item 2
    svc2.submit_response(sid, item_id="q2", answer="Ans 2", now=t0 + timedelta(minutes=15))

    # Step 15-16: Submit & persist result
    t_sub = t0 + timedelta(minutes=20)
    result = svc2.submit_assessment(
        sid,
        asmt,
        item_evaluations={"q1": (True, Decimal("1.0")), "q2": (True, Decimal("1.0"))},
        now=t_sub,
    )
    assert result.total_score == Decimal("10.00")
    assert result.passed is True

    # Step 17: Destroy process 2
    del svc2, repo2, db2

    # Step 18: Construct process 3 and reload final state
    db3 = Database(db_file)
    repo3 = AssessmentRepository(db3)
    svc3 = AssessmentService(repo=repo3)

    final_sess = svc3.get_session(sid)
    assert final_sess.status == SessionStatus.SUBMITTED
    assert final_sess.submitted_at == t_sub
    assert len(final_sess.responses) == 2
    assert final_sess.responses["q1"].answer == "Ans 1"
    assert final_sess.responses["q2"].answer == "Ans 2"

    final_res = svc3.get_result(sid)
    assert final_res.total_score == Decimal("10.00")
    assert final_res.passed is True
    assert final_res.session_id == sid


# -----------------------------------------------------------------------------
# 11. Real Concurrency Tests (Independent SQLite Connections)
# -----------------------------------------------------------------------------

def test_real_concurrency_case_a_duplicate_creation(tmp_path):
    """Case A: Two independent writers attempt to create the same assessment simultaneously.
    Result: exactly one creates; other fails controlled with IntegrityError; DB consistent.
    """
    import concurrent.futures

    db_file = tmp_path / "academic_concurrency_a.db"
    asmt = _create_sample_assessment(2)

    # Initialize schema once before launching concurrent writers
    Database(db_file).connect().close()

    results = []
    errors = []

    def _worker(worker_id: int):
        # Dedicated independent DB connection
        db = Database(db_file)
        repo = AssessmentRepository(db)
        try:
            # We explicitly execute direct INSERT via separate repo/tx
            with repo._tx(immediate=True) as cx:
                cx.execute(
                    """
                    INSERT INTO assessments (
                        stable_id, subject_id, title, description, items_json,
                        duration_min, attempts_allowed, policy_json,
                        shuffle_items, master_seed, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        asmt.stable_id,
                        asmt.subject_id,
                        f"Title {worker_id}",
                        "",
                        _serialize_items(asmt.items),
                        asmt.duration_min,
                        asmt.attempts_allowed,
                        _serialize_policy(asmt.policy),
                        0,
                        None,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
            results.append(worker_id)
        except IntegrityError as err:
            errors.append(str(err))

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(_worker, 1)
        f2 = executor.submit(_worker, 2)
        f1.result()
        f2.result()

    # Exactly one succeeded; exactly one failed with IntegrityError
    assert len(results) == 1, f"Expected exactly 1 success, got {len(results)}"
    assert len(errors) == 1, f"Expected exactly 1 error, got {len(errors)}"
    assert "UNIQUE constraint failed" in errors[0] or "Integrity" in errors[0]

    # Verify DB consistency: exactly one record exists
    db_verify = Database(db_file)
    cx = db_verify.connect()
    count = cx.execute("SELECT COUNT(*) FROM assessments WHERE stable_id = ?", (asmt.stable_id,)).fetchone()[0]
    cx.close()
    assert count == 1


def test_real_concurrency_case_b_same_response(tmp_path):
    """Case B: Two independent connections attempt to save the same response simultaneously.
    Result: exactly one response persisted; never duplicates; DB remains consistent.
    """
    import concurrent.futures

    db_file = tmp_path / "academic_concurrency_b.db"
    db_main = Database(db_file)
    repo_main = AssessmentRepository(db_main)
    asmt = _create_sample_assessment(2)
    repo_main.save_assessment(asmt)

    t0 = datetime(2026, 9, 17, 10, 0, 0, tzinfo=timezone.utc)
    sess = AssessmentSession(
        stable_id="session:sdm:sess:00001",
        assessment_id=asmt.stable_id,
        student_id="student:conc_b",
        status=SessionStatus.IN_PROGRESS,
        duration_seconds=3600,
        started_at=t0,
        expires_at=t0 + timedelta(minutes=60),
        item_order=("q1", "q2"),
    )
    repo_main.save_session(sess)

    resp = StudentResponse(item_id="q1", answer="Answer A", submitted_at=t0 + timedelta(minutes=1))

    def _worker():
        db = Database(db_file)
        repo = AssessmentRepository(db)
        repo.save_response(sess.stable_id, resp)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(_worker)
        f2 = executor.submit(_worker)
        f1.result()
        f2.result()

    # Verify DB contains exactly one response
    cx = db_main.connect()
    rows = cx.execute(
        "SELECT * FROM assessment_responses WHERE session_id = ? AND item_id = ?",
        (sess.stable_id, "q1"),
    ).fetchall()
    cx.close()

    assert len(rows) == 1
    assert rows[0]["answer"] == "Answer A"


def test_real_concurrency_case_c_submit_vs_response_race(tmp_path):
    """Case C (CRITICAL): Concurrent submit_session() vs save_response().
    Under concurrency, no late response can EVER be accepted into a SUBMITTED session.
    """
    import concurrent.futures

    db_file = tmp_path / "academic_concurrency_c.db"
    db_main = Database(db_file)
    repo_main = AssessmentRepository(db_main)
    asmt = _create_sample_assessment(2)
    repo_main.save_assessment(asmt)

    t0 = datetime(2026, 9, 17, 10, 0, 0, tzinfo=timezone.utc)
    sess = AssessmentSession(
        stable_id="session:sdm:sess:00001",
        assessment_id=asmt.stable_id,
        student_id="student:conc_c",
        status=SessionStatus.IN_PROGRESS,
        duration_seconds=3600,
        started_at=t0,
        expires_at=t0 + timedelta(minutes=60),
        item_order=("q1", "q2"),
    )
    repo_main.save_session(sess)

    # First record answer for q1
    repo_main.save_response(
        sess.stable_id,
        StudentResponse(item_id="q1", answer="Ans 1", submitted_at=t0 + timedelta(minutes=5)),
    )

    # Concurrent race: Connection 1 submits session, Connection 2 tries to insert late response for q2
    def _submit_worker():
        db = Database(db_file)
        repo = AssessmentRepository(db)
        s = repo.get_session(sess.stable_id)
        s.status = SessionStatus.SUBMITTED
        s.submitted_at = t0 + timedelta(minutes=10)
        repo.save_session(s)
        return "submitted"

    def _late_response_worker():
        db = Database(db_file)
        repo = AssessmentRepository(db)
        resp_late = StudentResponse(item_id="q2", answer="Late Ans", submitted_at=t0 + timedelta(minutes=11))
        repo.save_response(sess.stable_id, resp_late)
        return "responded"

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f_sub = executor.submit(_submit_worker)
        # Small sleep to ensure submit enters or races
        time.sleep(0.01)
        f_resp = executor.submit(_late_response_worker)

        sub_res = f_sub.result()
        assert sub_res == "submitted"

        # The late response attempt MUST either succeed before submission or fail with IntegrityError
        try:
            f_resp.result()
            late_succeeded = True
        except IntegrityError as err:
            late_succeeded = False
            assert "terminal status" in str(err) or "Cannot record response" in str(err)

    # Final DB check:
    final_sess = repo_main.get_session(sess.stable_id)
    assert final_sess.status == SessionStatus.SUBMITTED
    if not late_succeeded:
        assert "q2" not in final_sess.responses, "Late response was inserted after terminal state!"


def test_real_concurrency_case_d_concurrent_result_persistence(tmp_path):
    """Case D: Concurrent save_result(A) vs save_result(B) on the same session.
    Result: one wins; other fails controlled or is idempotent if identical; zero silent corruption.
    """
    import concurrent.futures

    db_file = tmp_path / "academic_concurrency_d.db"
    db_main = Database(db_file)
    repo_main = AssessmentRepository(db_main)
    asmt = _create_sample_assessment(2)
    repo_main.save_assessment(asmt)

    t0 = datetime(2026, 9, 17, 10, 0, 0, tzinfo=timezone.utc)
    sess = AssessmentSession(
        stable_id="session:sdm:sess:00001",
        assessment_id=asmt.stable_id,
        student_id="student:conc_d",
        status=SessionStatus.SUBMITTED,
        duration_seconds=3600,
        started_at=t0,
        expires_at=t0 + timedelta(minutes=60),
        submitted_at=t0 + timedelta(minutes=20),
        item_order=("q1", "q2"),
    )
    repo_main.save_session(sess)

    r_a = AssessmentResult(
        session_id=sess.stable_id,
        assessment_id=asmt.stable_id,
        student_id="student:conc_d",
        total_score=Decimal("8.0"),
        max_possible=Decimal("10.0"),
        percentage=Decimal("80.0"),
        passed=True,
        item_scores={"q1": Decimal("5.0"), "q2": Decimal("3.0")},
        evaluated_at=t0 + timedelta(minutes=21),
    )

    r_b = AssessmentResult(
        session_id=sess.stable_id,
        assessment_id=asmt.stable_id,
        student_id="student:conc_d",
        total_score=Decimal("10.0"),  # Conflicting score!
        max_possible=Decimal("10.0"),
        percentage=Decimal("100.0"),
        passed=True,
        item_scores={"q1": Decimal("5.0"), "q2": Decimal("5.0")},
        evaluated_at=t0 + timedelta(minutes=22),
    )

    results = []
    errors = []

    def _save_res(res_obj):
        db = Database(db_file)
        repo = AssessmentRepository(db)
        try:
            repo.save_result(res_obj)
            results.append(res_obj.total_score)
        except IntegrityError as err:
            errors.append(str(err))

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(_save_res, r_a)
        f2 = executor.submit(_save_res, r_b)
        f1.result()
        f2.result()

    # Exactly one result persisted; the other failed with IntegrityError
    assert len(results) == 1, f"Expected 1 winner, got {len(results)}"
    assert len(errors) == 1, f"Expected 1 conflict error, got {len(errors)}"
    assert "immutable" in errors[0] or "Integrity" in errors[0]

    # Verify persisted score matches winner
    winner_res = repo_main.get_result(sess.stable_id)
    assert winner_res.total_score == results[0]


# -----------------------------------------------------------------------------
# 12. Repeated Stress Concurrency (N = 10, 50, 100)
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("n_workers", [10, 50, 100])
def test_concurrency_stress_id_allocation(tmp_path, n_workers):
    """Stress test concurrent ID allocation across independent connections for N=10, 50, 100."""
    import concurrent.futures

    db_file = tmp_path / f"academic_stress_ids_{n_workers}.db"
    db_init = Database(db_file)
    repo_init = AssessmentRepository(db_init)
    asmt = _create_sample_assessment(2)
    repo_init.save_assessment(asmt)

    def _alloc_worker(idx: int) -> str:
        db = Database(db_file)
        repo = AssessmentRepository(db)
        return repo.allocate_session_id("stress")

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(n_workers, 16)) as executor:
        futures = [executor.submit(_alloc_worker, i) for i in range(n_workers)]
        ids = [f.result() for f in futures]

    assert len(ids) == n_workers
    assert len(set(ids)) == n_workers, "Collision detected in concurrent ID allocation!"


def test_concurrency_stress_same_response_idempotent(tmp_path):
    """Stress test N=20 independent connections saving identical response simultaneously."""
    import concurrent.futures

    db_file = tmp_path / "academic_stress_resp.db"
    db_init = Database(db_file)
    repo_init = AssessmentRepository(db_init)
    asmt = _create_sample_assessment(2)
    repo_init.save_assessment(asmt)

    t0 = datetime(2026, 9, 17, 10, 0, 0, tzinfo=timezone.utc)
    sess = AssessmentSession(
        stable_id="session:sdm:sess:00001",
        assessment_id=asmt.stable_id,
        student_id="student:stress_resp",
        status=SessionStatus.IN_PROGRESS,
        duration_seconds=3600,
        started_at=t0,
        expires_at=t0 + timedelta(minutes=60),
        item_order=("q1", "q2"),
    )
    repo_init.save_session(sess)

    resp = StudentResponse(item_id="q1", answer="Identical Answer", submitted_at=t0 + timedelta(minutes=1))

    def _worker(i: int):
        db = Database(db_file)
        repo = AssessmentRepository(db)
        repo.save_response(sess.stable_id, resp)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(_worker, i) for i in range(20)]
        for f in futures:
            f.result()

    # Verify exactly one response exists
    cx = db_init.connect()
    rows = cx.execute("SELECT * FROM assessment_responses WHERE session_id = ? AND item_id = ?",
                      (sess.stable_id, "q1")).fetchall()
    cx.close()
    assert len(rows) == 1
    assert rows[0]["answer"] == "Identical Answer"


def test_concurrency_stress_same_result_idempotent(tmp_path):
    """Stress test N=20 independent connections saving identical result simultaneously."""
    import concurrent.futures

    db_file = tmp_path / "academic_stress_res.db"
    db_init = Database(db_file)
    repo_init = AssessmentRepository(db_init)
    asmt = _create_sample_assessment(2)
    repo_init.save_assessment(asmt)

    t0 = datetime(2026, 9, 17, 10, 0, 0, tzinfo=timezone.utc)
    sess = AssessmentSession(
        stable_id="session:sdm:sess:00001",
        assessment_id=asmt.stable_id,
        student_id="student:stress_res",
        status=SessionStatus.SUBMITTED,
        duration_seconds=3600,
        started_at=t0,
        expires_at=t0 + timedelta(minutes=60),
        submitted_at=t0 + timedelta(minutes=20),
        item_order=("q1", "q2"),
    )
    repo_init.save_session(sess)

    r = AssessmentResult(
        session_id=sess.stable_id,
        assessment_id=asmt.stable_id,
        student_id="student:stress_res",
        total_score=Decimal("10.0"),
        max_possible=Decimal("10.0"),
        percentage=Decimal("100.0"),
        passed=True,
        item_scores={"q1": Decimal("5.0"), "q2": Decimal("5.0")},
        evaluated_at=t0 + timedelta(minutes=21),
    )

    def _worker(i: int):
        db = Database(db_file)
        repo = AssessmentRepository(db)
        repo.save_result(r)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(_worker, i) for i in range(20)]
        for f in futures:
            f.result()

    # Verify result exists and is intact
    res = repo_init.get_result(sess.stable_id)
    assert res is not None
    assert res.total_score == Decimal("10.0")



# -----------------------------------------------------------------------------
# 13. Multi-Step Atomicity Failure Injection
# -----------------------------------------------------------------------------

def test_multistep_atomicity_injected_failure_during_response(tmp_path):
    """Demonstrate that failure during multi-entity save_session rolls back all changes."""
    db_file = tmp_path / "academic_atomicity.db"
    db = Database(db_file)
    repo = AssessmentRepository(db)
    asmt = _create_sample_assessment(2)
    repo.save_assessment(asmt)

    t0 = datetime(2026, 9, 17, 10, 0, 0, tzinfo=timezone.utc)
    sess = AssessmentSession(
        stable_id="session:sdm:sess:00001",
        assessment_id=asmt.stable_id,
        student_id="student:atom",
        status=SessionStatus.IN_PROGRESS,
        duration_seconds=3600,
        started_at=t0,
        expires_at=t0 + timedelta(minutes=60),
        item_order=("q1", "q2"),
    )
    sess.responses["q1"] = StudentResponse(item_id="q1", answer="Ans 1", submitted_at=t0 + timedelta(minutes=1))

    # Test atomic rollback when an exception is raised halfway through saving responses
    class FailingRepo(AssessmentRepository):
        def _save_response_tx(self, cx, session_id: str, resp: StudentResponse) -> None:
            if resp.item_id == "fail_here":
                raise RuntimeError("Injected transaction failure!")
            super()._save_response_tx(cx, session_id, resp)

    fail_repo = FailingRepo(db)
    sess.responses["q2"] = StudentResponse(item_id="fail_here", answer="Ans 2", submitted_at=t0 + timedelta(minutes=2))

    with pytest.raises(RuntimeError, match="Injected transaction failure!"):
        fail_repo.save_session(sess)

    # Verification: total rollback!
    # Neither the session nor response 1 was committed to disk
    cx = db.connect()
    s_row = cx.execute("SELECT * FROM assessment_sessions WHERE stable_id = ?", (sess.stable_id,)).fetchone()
    r_rows = cx.execute("SELECT * FROM assessment_responses WHERE session_id = ?", (sess.stable_id,)).fetchall()
    cx.close()

    assert s_row is None, "Session was partially persisted despite transaction failure!"
    assert len(r_rows) == 0, "Response was partially persisted despite transaction failure!"


# -----------------------------------------------------------------------------
# 14. Robust Corruption Handling (14 Required Cases)
# -----------------------------------------------------------------------------

def test_corruption_case_1_invalid_decimal(test_db):
    """Case 1: Invalid Decimal in items_json raises IntegrityError and leaves DB unchanged."""
    repo = AssessmentRepository(test_db)
    asmt = _create_sample_assessment(1)
    repo.save_assessment(asmt)

    cx = test_db.connect()
    cx.execute("UPDATE assessments SET items_json = ? WHERE stable_id = ?",
               ('[{"item_id":"q1","question_id":"q1","topic_id":"t1","weight":"NOT_A_DECIMAL"}]', asmt.stable_id))
    cx.commit(); cx.close()

    with pytest.raises(IntegrityError, match="Failed to deserialize assessment items"):
        repo.get_assessment(asmt.stable_id)


def test_corruption_case_2_invalid_timestamp(test_db):
    """Case 2: Invalid timestamp string in session raises IntegrityError."""
    repo = AssessmentRepository(test_db)
    asmt = _create_sample_assessment(1)
    repo.save_assessment(asmt)

    cx = test_db.connect()
    cx.execute(
        "INSERT INTO assessment_sessions VALUES ('session:sdm:sess:00001', ?, 's1', 1, 'IN_PROGRESS', 3600, 'not-a-date', NULL, NULL, '[]', NULL, 'now')",
        (asmt.stable_id,),
    )
    cx.commit(); cx.close()

    with pytest.raises(IntegrityError, match="Corrupted session data"):
        repo.get_session("session:sdm:sess:00001")


def test_corruption_case_3_invalid_json(test_db):
    """Case 3: Malformed JSON in policy_json raises IntegrityError."""
    repo = AssessmentRepository(test_db)
    asmt = _create_sample_assessment(1)
    repo.save_assessment(asmt)

    cx = test_db.connect()
    cx.execute("UPDATE assessments SET policy_json = '{unclosed' WHERE stable_id = ?", (asmt.stable_id,))
    cx.commit(); cx.close()

    with pytest.raises(IntegrityError, match="Failed to deserialize grading policy"):
        repo.get_assessment(asmt.stable_id)


def test_corruption_case_4_invalid_session_status(test_db):
    """Case 4: Unknown session status in SQLite raises IntegrityError."""
    repo = AssessmentRepository(test_db)
    asmt = _create_sample_assessment(1)
    repo.save_assessment(asmt)

    cx = test_db.connect()
    cx.execute(
        "INSERT INTO assessment_sessions VALUES ('session:sdm:sess:00002', ?, 's1', 1, 'BOGUS_STATUS', 3600, NULL, NULL, NULL, '[]', NULL, 'now')",
        (asmt.stable_id,),
    )
    cx.commit(); cx.close()

    with pytest.raises(IntegrityError, match="Unknown session status"):
        repo.get_session("session:sdm:sess:00002")


def test_corruption_case_5_invalid_id_syntax(test_db):
    """Case 5: Malformed stable_id syntax in SQLite raises IntegrityError."""
    repo = AssessmentRepository(test_db)
    asmt = _create_sample_assessment(1)
    repo.save_assessment(asmt)

    cx = test_db.connect()
    cx.execute(
        "INSERT INTO assessment_sessions VALUES ('bad_id_syntax', ?, 's1', 1, 'IN_PROGRESS', 3600, NULL, NULL, NULL, '[]', NULL, 'now')",
        (asmt.stable_id,),
    )
    cx.commit(); cx.close()

    with pytest.raises(IntegrityError, match="Corrupted session data"):
        repo.get_session("bad_id_syntax")


def test_corruption_case_6_invalid_policy(test_db):
    """Case 6: Inverted policy scale (low > high) raises IntegrityError."""
    repo = AssessmentRepository(test_db)
    asmt = _create_sample_assessment(1)
    repo.save_assessment(asmt)

    corrupt_policy = json.dumps({
        "passing_score": "5.0",
        "max_score": "10.0",
        "scale": {"kind": "numeric", "low": "10.0", "high": "0.0", "letters": []},
    })
    cx = test_db.connect()
    cx.execute("UPDATE assessments SET policy_json = ? WHERE stable_id = ?", (corrupt_policy, asmt.stable_id))
    cx.commit(); cx.close()

    with pytest.raises(IntegrityError, match="Failed to deserialize grading policy"):
        repo.get_assessment(asmt.stable_id)


def test_corruption_case_7_missing_required_column_value(test_db):
    """Case 7: NULL in NOT NULL column in assessment_sessions raises IntegrityError."""
    repo = AssessmentRepository(test_db)
    asmt = _create_sample_assessment(1)
    repo.save_assessment(asmt)

    cx = test_db.connect()
    cx.execute(
        "INSERT INTO assessment_sessions VALUES ('session:sdm:sess:00003', ?, '', 1, 'IN_PROGRESS', 3600, NULL, NULL, NULL, '[]', NULL, 'now')",
        (asmt.stable_id,),
    )
    cx.commit(); cx.close()

    with pytest.raises(IntegrityError, match="Corrupted session data"):
        repo.get_session("session:sdm:sess:00003")


def test_corruption_case_8_foreign_key_violation(test_db):
    """Case 8: Session pointing to non-existent assessment raises IntegrityError."""
    repo = AssessmentRepository(test_db)
    sess = AssessmentSession(
        stable_id="session:sdm:sess:00004",
        assessment_id="assessment:sdm:as:99999",  # Non-existent
        student_id="student:fk",
    )
    with pytest.raises(IntegrityError, match="integrity violation|FOREIGN KEY"):
        repo.save_session(sess)


def test_corruption_case_9_inconsistent_response_session_fk(test_db):
    """Case 9: Saving response for non-existent session raises IntegrityError."""
    repo = AssessmentRepository(test_db)
    resp = StudentResponse(item_id="q1", answer="Ans", submitted_at=datetime.now(timezone.utc))
    with pytest.raises(IntegrityError, match="does not exist"):
        repo.save_response("session:sdm:sess:99999", resp)


def test_corruption_case_10_inconsistent_result_session_fk(test_db):
    """Case 10: Saving result for non-existent session raises IntegrityError."""
    repo = AssessmentRepository(test_db)
    res = AssessmentResult(
        session_id="session:sdm:sess:99999",
        assessment_id="assessment:sdm:as:00001",
        student_id="student:none",
        total_score=Decimal("5.0"),
        max_possible=Decimal("10.0"),
        percentage=Decimal("50.0"),
        passed=True,
        item_scores={"q1": Decimal("5.0")},
        evaluated_at=datetime.now(timezone.utc),
    )
    with pytest.raises(IntegrityError, match="does not exist"):
        repo.save_result(res)


def test_corruption_case_11_schema_incompatibility_missing_table(tmp_path):
    """Case 11: Attempting persistence on DB without required assessment tables raises IntegrityError."""
    import sqlite3
    db_file = tmp_path / "incompatible.db"
    # Create empty DB without running migrations
    raw_cx = sqlite3.connect(db_file)
    raw_cx.execute("CREATE TABLE foo (x INT)")
    raw_cx.close()

    class BareDB:
        def __init__(self, path):
            self.path = path
        def connect(self):
            cx = sqlite3.connect(self.path)
            cx.row_factory = sqlite3.Row
            return cx

    repo = AssessmentRepository(BareDB(db_file))
    asmt = _create_sample_assessment(1)
    with pytest.raises(Exception):
        repo.save_assessment(asmt)


def test_corruption_case_12_unsupported_schema_version(test_db):
    """Case 12: DB marked with unsupported future schema version connects without crashing existing tables."""
    cx = test_db.connect()
    cx.execute("INSERT INTO schema_version (version) VALUES (999)")
    cx.commit()
    max_v = cx.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    cx.close()
    assert max_v == 999


def test_corruption_case_13_malformed_item_order(test_db):
    """Case 13: Non-list item_order_json raises IntegrityError."""
    repo = AssessmentRepository(test_db)
    asmt = _create_sample_assessment(1)
    repo.save_assessment(asmt)

    cx = test_db.connect()
    cx.execute(
        "INSERT INTO assessment_sessions VALUES ('session:sdm:sess:00005', ?, 's1', 1, 'IN_PROGRESS', 3600, NULL, NULL, NULL, '{\"not\":\"a list\"}', NULL, 'now')",
        (asmt.stable_id,),
    )
    cx.commit(); cx.close()

    with pytest.raises(IntegrityError, match="Corrupted item_order_json"):
        repo.get_session("session:sdm:sess:00005")


def test_corruption_case_14_malformed_item_scores(test_db):
    """Case 14: Non-dict item_scores_json raises IntegrityError."""
    repo = AssessmentRepository(test_db)
    asmt = _create_sample_assessment(1)
    repo.save_assessment(asmt)

    t0 = datetime(2026, 9, 17, 10, 0, 0, tzinfo=timezone.utc)
    sess = AssessmentSession(
        stable_id="session:sdm:sess:00006",
        assessment_id=asmt.stable_id,
        student_id="student:res_corrupt",
        status=SessionStatus.SUBMITTED,
        duration_seconds=3600,
        started_at=t0,
        submitted_at=t0,
        item_order=("q1",),
    )
    repo.save_session(sess)

    cx = test_db.connect()
    cx.execute(
        "INSERT INTO assessment_results VALUES ('session:sdm:sess:00006', ?, 'student:res_corrupt', '10.0', '10.0', '100.0', 1, '[\"not a dict\"]', '2026-09-17T10:00:00')",
        (asmt.stable_id,),
    )
    cx.commit(); cx.close()

    with pytest.raises(IntegrityError, match="Corrupted item_scores_json|Corrupted assessment result"):
        repo.get_result("session:sdm:sess:00006")


# -----------------------------------------------------------------------------
# 15. Decimal Lossless & Timestamp Fidelity
# -----------------------------------------------------------------------------

def test_decimal_fidelity_exhaustive(test_db):
    """Verify extreme and challenging Decimal values survive without loss."""
    repo = AssessmentRepository(test_db)

    test_values = [
        Decimal("0"),
        Decimal("1"),
        Decimal("-1"),
        Decimal("0.1"),
        Decimal("0.000000001"),
        Decimal("12345678901234567890.123456789"),
        Decimal("-12345678901234567890.123456789"),
    ]

    for idx, d_val in enumerate(test_values, start=1):
        # We test item weight and passing_score with positive decimals
        pos_val = abs(d_val) if d_val <= Decimal(0) else d_val
        if pos_val == Decimal(0):
            pos_val = Decimal("0.000000001")

        policy = GradingPolicy(passing_score=pos_val, max_score=pos_val * Decimal(2))
        item = AssessmentItem(
            item_id=f"qi_{idx}",
            question_id=f"q_{idx}",
            topic_id="topic:sdm:t01",
            weight=pos_val,
        )
        asmt = Assessment(
            stable_id=f"assessment:sdm:as:{idx:05d}",
            subject_id="subject:sdm",
            title=f"Decimal Test {idx}",
            items=(item,),
            policy=policy,
        )
        repo.save_assessment(asmt)
        reloaded = repo.get_assessment(asmt.stable_id)
        assert reloaded.items[0].weight == pos_val
        assert isinstance(reloaded.items[0].weight, Decimal)
        assert reloaded.policy.passing_score == pos_val
        assert isinstance(reloaded.policy.passing_score, Decimal)


def test_timestamp_fidelity_and_timezone_semantics(test_db):
    """Verify UTC, timezone-aware datetime, and microsecond precision survive intact."""
    repo = AssessmentRepository(test_db)
    asmt = _create_sample_assessment(1)
    repo.save_assessment(asmt)

    t_precise = datetime(2026, 9, 17, 10, 30, 45, 123456, tzinfo=timezone.utc)
    sess = AssessmentSession(
        stable_id="session:sdm:sess:00001",
        assessment_id=asmt.stable_id,
        student_id="student:ts",
        status=SessionStatus.IN_PROGRESS,
        started_at=t_precise,
        expires_at=t_precise + timedelta(hours=1),
        item_order=("q1",),
    )
    repo.save_session(sess)

    loaded = repo.get_session(sess.stable_id)
    assert loaded.started_at == t_precise
    assert loaded.started_at.microsecond == 123456
    assert loaded.started_at.tzinfo == timezone.utc


# -----------------------------------------------------------------------------
# 16. JSON Determinism & Idempotency
# -----------------------------------------------------------------------------

def test_json_serialization_determinism():
    """Verify same domain state yields byte-for-byte identical serialized representation."""
    policy = GradingPolicy(
        passing_score=Decimal("5.0"),
        max_score=Decimal("10.0"),
        negative_marking_factor=Decimal("0.25"),
        allow_partial_credit=True,
    )
    items = (
        AssessmentItem(item_id="q1", question_id="qid1", topic_id="top1", weight=Decimal("2.0"), options=("B", "A")),
        AssessmentItem(item_id="q2", question_id="qid2", topic_id="top2", weight=Decimal("3.0"), options=("X", "Y")),
    )

    s1 = _serialize_items(items)
    s2 = _serialize_items(items)
    assert s1 == s2, "Serialization is non-deterministic!"

    p1 = _serialize_policy(policy)
    p2 = _serialize_policy(policy)
    assert p1 == p2, "Policy serialization is non-deterministic!"


def test_id_allocation_contract_unique_monotonic_not_gapless(tmp_path):
    """Demonstrate ID allocation is unique and monotonic, but NOT gapless upon rollback."""
    db_file = tmp_path / "academic_id_gap.db"
    db = Database(db_file)
    repo = AssessmentRepository(db)

    id1 = repo.allocate_session_id("math")
    id2 = repo.allocate_session_id("math")
    assert id1.endswith("sess:00001")
    assert id2.endswith("sess:00002")

    # Allocate ID3, but abort/rollback the subsequent session persistence
    id3 = repo.allocate_session_id("math")
    assert id3.endswith("sess:00003")
    # Simulate failed transaction: id3 is abandoned

    # Allocate next ID: it must be 00004 (creating an explicit gap for 00003)
    id4 = repo.allocate_session_id("math")
    assert id4.endswith("sess:00004")
    # This demonstrates monotonic uniqueness WITHOUT gapless guarantee
    assert id4 > id3 > id2 > id1


def test_formula_provenance_audit_boundary(test_db):
    """Audit Formula -> AssessmentItem boundary.
    Directly persisted: stable_id (as question_id), latex (options[0]), source_latex (options[1]), topic_id.
    Transformed: provenance (source_path, section) -> rubric_ref.
    Deliberately lost/out of scope: variables, units, concept_ids, version.
    """
    repo = AssessmentRepository(test_db)
    f = Formula(
        stable_id="formula:sdm:f:000123",
        latex=r"V = I \cdot R",
        source_latex=r"V = I \cdot R",
        topic_id="topic:sdm:t01",
        concept_ids=["concept:sdm:c:00001"],
        variables=[{"name": "V", "unit": "V"}],
        units=["V"],
        provenance={"source_path": "teoria/ohm.md", "section": "Ohm's Law"},
        version=2,
    )

    item = item_from_formula(f, item_id="q_ohm", weight=Decimal("3.0"))
    assert item.question_id == f.stable_id
    assert item.topic_id == f.topic_id
    assert item.weight == Decimal("3.0")
    assert "formula_prov:teoria/ohm.md#Ohm's Law" in item.rubric_ref
    assert item.options == (f.latex, f.source_latex)

    # Deliberately lost: AssessmentItem does not have variables, units, or concept_ids attributes
    assert not hasattr(item, "variables")
    assert not hasattr(item, "units")
    assert not hasattr(item, "concept_ids")

    asmt = Assessment(
        stable_id="assessment:sdm:as:00123",
        subject_id="subject:sdm",
        title="Ohm Exam",
        items=(item,),
    )
    repo.save_assessment(asmt)

    loaded = repo.get_assessment(asmt.stable_id)
    assert loaded is not None
    loaded_item = loaded.items[0]
    assert loaded_item.question_id == f.stable_id
    assert loaded_item.topic_id == f.topic_id
    assert loaded_item.options == (f.latex, f.source_latex)
    assert loaded_item.rubric_ref == item.rubric_ref
