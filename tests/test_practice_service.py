# SPDX-License-Identifier: MIT
"""Practice loop exposed through the facade (UX 2026 prompt 8).

F9 correction -> F10 mastery -> F11 plan -> F12 tutor, as plain values.
The service adds no grading/mastery/planning/tutoring logic; these tests pin
that the facade wiring gives the certified results and that the LLM is never
an authority.
"""

from __future__ import annotations

import json
import os
from dataclasses import fields
from decimal import Decimal

import pytest

from academic_core.domain import entities as E
from academic_core.domain import question_bank as QB
from academic_core.domain.planning import StudyConcept
from academic_core.infrastructure.llm import LLMResponse, ProviderMetadata


def _q(n, qtype, spec, concept, difficulty="easy", **kw):
    return QB.Question(question_id=f"question:demo:q:{n:05d}", statement=f"Statement {n}?",
                       qtype=qtype, answer_spec=spec, owner_slug="demo",
                       concepts=[concept], difficulty=difficulty, **kw)


def _bank_text(version=1):
    return QB.dumps_bank(QB.Bank(bank_id="bank:demo", title="Demo bank", content_version=version, questions=(
        _q(1, "multiple_choice", {"options": ["3", "4"], "correct": [1]}, "concept:al:c:00001"),
        _q(2, "true_false", {"answer": True}, "concept:al:c:00001", "medium"),
        _q(3, "numeric", {"value": "4.0", "unit": "V", "tolerance": "0.1"}, "concept:al:c:00002"),
        _q(4, "short_text", {"expected": "Paris"}, "concept:al:c:00002", "medium"),
    )))


RIGHT = {"question:demo:q:00001": {"selected": [1]}, "question:demo:q:00002": {"answer": True},
         "question:demo:q:00003": {"value": "4.05", "unit": "V"},
         "question:demo:q:00004": {"text": "paris"}}
WRONG = {"question:demo:q:00001": {"selected": [0]}, "question:demo:q:00002": {"answer": False},
         "question:demo:q:00003": {"value": "9", "unit": "V"},
         "question:demo:q:00004": {"text": "Rome"}}


@pytest.fixture()
def core(tmp_path):
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / "db")
    from academic_core.application import AcademicApp
    from academic_core.config import Settings
    app = AcademicApp(Settings.load())
    app.settings.ensure_dirs()
    app.academic.add_subject(E.Subject("subject:al", "ALG", "Algebra", "ALG"))
    for ref, name in (("concept:al:c:00001", "Derivadas"), ("concept:al:c:00002", "Integrales")):
        app.personal.add_concept(StudyConcept(ref, "subject:al", name))
    return app


def _loaded(core):
    core.practice.import_bank(_bank_text())
    return core.practice


class _Provider:
    def __init__(self, raw="", available=True):
        self.raw, self.available = raw, available

    def generate(self, request):
        return LLMResponse(raw_text=self.raw, provider="fake", model="fake-1", latency_ms=1,
                           available=self.available, error_code="" if self.available else "LLM_UNAVAILABLE")

    def metadata(self):
        return ProviderMetadata(provider="fake", model="fake-1", available=self.available)


# -- facade exposure ---------------------------------------------------------------------
def test_facade_exposes_the_whole_loop_with_the_llm_off(core):
    for name in ("qbank", "bank_ingest", "correction", "mastery", "adaptive", "tutor", "practice"):
        assert getattr(core, name) is not None, name
    assert core.practice.llm_available() is False  # NullProvider: LLM=OFF by default


# -- banks ---------------------------------------------------------------------------------
def test_empty_before_any_bank(core):
    assert core.practice.banks() == [] and core.practice.questions() == []


def test_import_is_idempotent_and_lists_banks_and_questions(core, tmp_path):
    path = tmp_path / "bank.json"
    path.write_text(_bank_text(), encoding="utf-8")
    first = core.practice.import_bank(path)
    again = core.practice.import_bank(_bank_text())
    assert first["outcome"] == "create" and again["outcome"] == "unchanged"
    assert core.practice.banks() == [{"bank_id": "bank:demo", "title": "Demo bank",
                                      "content_version": 1, "question_count": 4}]
    qs = core.practice.questions("bank:demo")
    assert [q.qtype for q in qs] == ["multiple_choice", "true_false", "numeric", "short_text"]
    assert qs[0].options == ("3", "4") and qs[2].unit == "V" and qs[0].subject_id == "subject:al"


def test_a_question_view_never_carries_the_answer(core):
    names = {f.name for f in fields(type(_loaded(core).questions()[0]))}
    assert not names & {"answer_spec", "correct", "expected", "answer", "value"}
    text = repr(_loaded(core).questions())
    assert "expected" not in text and "'correct'" not in text and "Paris" not in text


def test_invalid_bank_is_rejected_by_d6_not_swallowed(core):
    from academic_core.errors import AcademicManagementError
    with pytest.raises(AcademicManagementError):
        core.practice.import_bank('{"schema": "nope"}')


# -- attempt (F9) ---------------------------------------------------------------------------------
def test_correct_attempt_scores_full_and_updates_mastery(core):
    p = _loaded(core)
    attempt = p.start_attempt([q.question_id for q in p.questions()])
    assert attempt.subject_id == "subject:al"
    result = p.submit(attempt, RIGHT)
    assert Decimal(result.percentage) == Decimal("100.00") and result.passed
    assert [i.is_correct for i in result.items] == [True] * 4
    assert result.mastery_updated
    concepts = {c.ref: c for c in p.concepts("subject:al")}
    assert set(concepts) == {"concept:al:c:00001", "concept:al:c:00002"}
    assert concepts["concept:al:c:00001"].observations == 2 and concepts["concept:al:c:00001"].name == "Derivadas"
    assert p.subject_mastery("subject:al")[0] > Decimal("0.5")


def test_wrong_and_omitted_answers_are_graded_by_the_certified_checker(core):
    p = _loaded(core)
    attempt = p.start_attempt([q.question_id for q in p.questions()])
    answers = dict(WRONG)
    del answers["question:demo:q:00004"]  # left blank
    result = p.submit(attempt, answers)
    by = {i.question_id: i for i in result.items}
    assert [by[f"question:demo:q:{n:05d}"].is_correct for n in (1, 2, 3)] == [False, False, False]
    assert by["question:demo:q:00004"].reason == "omitted" and by["question:demo:q:00004"].is_correct is None
    assert Decimal(result.total_score) == 0 and not result.passed


def test_right_answers_raise_mastery_above_wrong_ones(core, tmp_path):
    p = _loaded(core)
    ids = [q.question_id for q in p.questions()]
    p.submit(p.start_attempt(ids), RIGHT)
    good = p.subject_mastery("subject:al")[0]
    os.environ["ACORE_DATA_DIR"] = str(tmp_path / "db2")
    from academic_core.application import AcademicApp
    from academic_core.config import Settings
    other = AcademicApp(Settings.load())
    other.settings.ensure_dirs()
    other.academic.add_subject(E.Subject("subject:al", "ALG", "Algebra", "ALG"))
    for ref in ("concept:al:c:00001", "concept:al:c:00002"):
        other.personal.add_concept(StudyConcept(ref, "subject:al", ref))
    other.practice.import_bank(_bank_text())
    other.practice.submit(other.practice.start_attempt(ids), WRONG)
    assert other.practice.subject_mastery("subject:al")[0] < good


def test_attempt_needs_questions_and_a_subject(core):
    p = _loaded(core)
    with pytest.raises(ValueError):
        p.start_attempt([])
    with pytest.raises(ValueError):
        p.start_attempt(["question:demo:q:99999"])


def test_grading_is_deterministic(core):
    p = _loaded(core)
    ids = [q.question_id for q in p.questions()]
    a = p.submit(p.start_attempt(ids), RIGHT)
    b = p.submit(p.start_attempt(ids), RIGHT)
    assert [(i.score, i.reason) for i in a.items] == [(i.score, i.reason) for i in b.items]


def test_rebuild_reproduces_the_stored_states(core):
    p = _loaded(core)
    p.submit(p.start_attempt([q.question_id for q in p.questions()]), RIGHT)
    before = [(c.ref, c.probability, c.observations) for c in p.concepts()]
    assert p.rebuild_mastery() == 2
    assert [(c.ref, c.probability, c.observations) for c in p.concepts()] == before


# -- plan (F11) ---------------------------------------------------------------------------------------
def test_plan_ranks_real_questions_with_rationale(core):
    p = _loaded(core)
    plan = p.plan("subject:al", 3)
    assert 1 <= len(plan.items) <= 3
    known = {q.question_id for q in p.questions()}
    assert all(i.question_id in known and i.statement and i.rationale for i in plan.items)


def test_plan_excludes_what_was_already_done(core):
    p = _loaded(core)
    ids = [q.question_id for q in p.questions()]
    p.submit(p.start_attempt(ids[:2]), {k: v for k, v in RIGHT.items() if k in ids[:2]})
    planned = {i.question_id for i in p.plan("subject:al", 5).items}
    assert planned.isdisjoint(ids[:2]) and planned <= set(ids)
    p.submit(p.start_attempt(ids[2:]), {k: v for k, v in RIGHT.items() if k in ids[2:]})
    done = p.plan("subject:al", 5)
    assert done.items == () and "NO_ELIGIBLE_EXERCISES" in done.rationale_codes
    assert done.mastery_snapshot and all(isinstance(pr, Decimal) for _ref, pr in done.mastery_snapshot)


# -- tutor (F12) ------------------------------------------------------------------------------------------
def _corrected(p, answers=WRONG):
    attempt = p.start_attempt([q.question_id for q in p.questions()])
    return p.submit(attempt, answers).session_id


def test_tutor_with_llm_off_gives_static_verified_guidance(core):
    p = _loaded(core)
    sid = _corrected(p)
    hint = p.hint(sid, "question:demo:q:00003")
    assert hint.status == "verified" and hint.response_type == "hint"
    assert hint.llm_available is False and hint.provider_error == "LLM_UNAVAILABLE"
    assert "motivo" in hint.message and "Paris" not in hint.message


def test_hint_requires_a_corrected_attempt(core):
    p = _loaded(core)
    with pytest.raises(ValueError):
        p.hint("session:none", "question:demo:q:00001")


def test_llm_garbage_is_rejected_never_shown_as_truth(core):
    p = _loaded(core)
    core.tutor.provider = _Provider("this is not json")
    hint = p.hint(_corrected(p), "question:demo:q:00003")
    assert hint.status == "rejected" and hint.message == "INVALID_LLM_OUTPUT" and hint.llm_available


def test_llm_cannot_reveal_the_answer_early(core):
    from academic_core.domain import tutor as T
    p = _loaded(core)
    proposal = {"schema_version": T.TUTOR_SCHEMA, "response_type": "final_answer",
                "message": "La respuesta es 4 V", "claims": []}
    core.tutor.provider = _Provider(json.dumps(proposal))
    hint = p.hint(_corrected(p), "question:demo:q:00003")
    assert hint.status != "verified" or hint.response_type != "final_answer"  # policy stage 0 blocks it


def test_a_valid_hint_proposal_passes_through_verification(core):
    from academic_core.domain import tutor as T
    p = _loaded(core)
    proposal = {"schema_version": T.TUTOR_SCHEMA, "response_type": "hint",
                "message": "Revisa las unidades antes de comparar."}
    core.tutor.provider = _Provider(json.dumps(proposal))
    hint = p.hint(_corrected(p), "question:demo:q:00003")
    assert hint.status == "verified" and hint.message.startswith("Revisa")
    assert hint.llm_available and hint.provider_error == "" and hint.solver_version


# -- needs_review must not break or move mastery ---------------------------------------------------
def test_needs_review_answer_is_kept_as_evidence_and_does_not_touch_mastery(core):
    """F10's apply_evidence raises on a needs_review item (its own comment says no-update)."""
    review = QB.Question(question_id="question:rev:q:00001", statement="Explain.", qtype="structured",
                         answer_spec={"schema": {"note": "text"}}, owner_slug="rev",
                         concepts=["concept:al:c:00001"], difficulty="easy")
    core.practice.import_bank(QB.dumps_bank(QB.Bank(bank_id="bank:rev", title="Review", content_version=1,
                                                    questions=(review,))))
    attempt = core.practice.start_attempt(["question:rev:q:00001"])
    result = core.practice.submit(attempt, {"question:rev:q:00001": {"fields": {"note": "my reasoning"}}})
    item = result.items[0]
    assert item.is_correct is None and item.reason == "needs_review"
    assert result.mastery_updated is False and core.practice.concepts() == []
    # A gradable answer in the same attempt still updates mastery.
    core.practice.import_bank(_bank_text())
    mixed = core.practice.start_attempt(["question:rev:q:00001", "question:demo:q:00002"])
    done = core.practice.submit(mixed, {"question:rev:q:00001": {"fields": {"note": "x"}},
                                        "question:demo:q:00002": {"answer": True}})
    assert done.mastery_updated is True
    assert [c.observations for c in core.practice.concepts()] == [1]


def test_hint_survives_a_restart(core):
    p = _loaded(core)
    sid = _corrected(p)
    p._evidence.clear()  # a new run only has what F9 persisted
    assert p.hint(sid, "question:demo:q:00003").status == "verified"


def test_sample_bank_works_out_of_the_box_and_is_idempotent(core):
    p = core.practice
    assert p.import_sample()["outcome"] == "create"
    assert p.import_sample()["outcome"] == "unchanged"
    qs = p.questions("bank:sample")
    assert len(qs) == 4
    res = p.submit(p.start_attempt([q.question_id for q in qs]),
                   {qs[0].question_id: {"selected": [1]}, qs[1].question_id: {"answer": True},
                    qs[2].question_id: {"value": "5", "unit": "V"}, qs[3].question_id: {"text": "ohm"}})
    assert res.passed and res.mastery_updated
