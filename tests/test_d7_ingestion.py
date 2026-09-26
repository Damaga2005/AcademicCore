# SPDX-License-Identifier: MIT
"""D7 ingestion contracts: D6 bank -> Knowledge Core (plan/apply/verify).

Small contractual tests over tmp_path databases. Covers prompt section 17:
minimal bank, valid question, new ingestion, idempotence, reingest,
new version, existing/missing/ambiguous refs, provenance, digest,
mapping, concept/formula create+reuse, relationships, rollback,
dry-run, determinism, invalid inputs, security. D5/D6 regression runs
in the gate suite (no duplicate coverage here).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from academic_core.application.bank_ingest import BankIngestionService
from academic_core.domain import ingestion as IN
from academic_core.domain import question_bank as QB
from academic_core.domain import entities as E
from academic_core.errors import AcademicManagementError, IntegrationError
from academic_core.infrastructure.academic_store import (
    PersonalRepository,
    QBankRepository,
)
from academic_core.infrastructure.database import Database
from academic_core.infrastructure.repositories import AcademicRepository

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "academic_core"
NOW = 1758792000000


def _svc(tmp_path):
    db = Database(tmp_path / "d7.db")
    ac, pe, qb = (AcademicRepository(db), PersonalRepository(db),
                  QBankRepository(db))
    ac.add_subject(E.Subject("subject:al", "ALG", "Algebra", "ALG"))
    return db, BankIngestionService(ac, pe, qb), ac, pe, qb


def _q(n, slug="demo", **kw):
    d = dict(question_id=f"question:{slug}:q:{n:05d}",
             statement=f"Statement {n}?", qtype="short_text",
             answer_spec={"max_length": 200}, owner_slug=slug)
    d.update(kw)
    return QB.Question(**d)


def _bank(slug="demo", questions=None, version=1, **kw):
    d = dict(bank_id=f"bank:{slug}", title="Demo", content_version=version,
             questions=tuple(questions if questions is not None
                             else [_q(1, slug)]))
    d.update(kw)
    return QB.Bank(**d)


def _env(bank):
    return QB.dumps_bank(bank)


def _counts(qb, bank_id="bank:demo"):
    return (qb.get_bank(bank_id), qb.question_digests(bank_id))


# -- 1-3: minimal bank, valid question, new ingestion ---------------------

def test_minimal_bank_ingest_creates(tmp_path):
    _, svc, _, _, qb = _svc(tmp_path)
    rep = svc.ingest(_env(_bank()), now_ms=NOW)
    assert rep.outcome == "create" and rep.verified is True
    assert rep.counts["questions_created"] == 1
    row, digests = _counts(qb)
    assert row["content_version"] == 1 and row["question_count"] == 1
    assert set(digests) == {"question:demo:q:00001"}


def test_question_mapping_and_digest_preserved(tmp_path):
    _, svc, _, _, qb = _svc(tmp_path)
    bank = _bank(questions=[_q(1, concepts=["concept:al:c:00001"],
                               knowledge_refs=[{"kind": "section",
                                                "ref": "sec:1"}])])
    rep = svc.ingest(_env(bank),
                     catalog_concepts={"concept:al:c:00001": "Límite"},
                     now_ms=NOW)
    assert rep.bank_digest == QB.bank_digest(bank)
    stored = qb.get_bank("bank:demo")
    assert stored["digest"] == QB.bank_digest(bank)
    qrow = qb.get_question("question:demo:q:00001")
    assert json.loads(qrow["canonical_json"])["statement"] == "Statement 1?"
    assert ("question:demo:q:00001", "concept", "concept:al:c:00001",
            "create") in rep.resolved
    assert ("question:demo:q:00001", "section", "sec:1",
            "carried") in rep.resolved


# -- 4-6: idempotence, reingest, new version -------------------------------

def test_idempotent_reingest_writes_nothing(tmp_path):
    _, svc, _, _, qb = _svc(tmp_path)
    env = _env(_bank())
    r1 = svc.ingest(env, now_ms=NOW)
    before = (qb.get_bank("bank:demo")["updated_at_ms"],
              qb.question_digests("bank:demo"))
    r2 = svc.ingest(env, now_ms=NOW + 999)
    assert r1.bank_digest == r2.bank_digest == QB.bank_digest(_bank())
    assert r2.outcome == "unchanged"
    after = (qb.get_bank("bank:demo")["updated_at_ms"],
             qb.question_digests("bank:demo"))
    assert before == after


def test_new_version_updates_adds_removes(tmp_path):
    _, svc, _, _, qb = _svc(tmp_path)
    svc.ingest(_env(_bank()), now_ms=NOW)
    v2 = _bank(version=2, questions=[
        _q(1, statement="Statement 1 revised?"),
        _q(2)])
    rep = svc.ingest(_env(v2), now_ms=NOW + 1)
    assert rep.outcome == "update"
    assert rep.counts == {"questions_created": 1, "questions_kept": 0,
                          "questions_updated": 1, "questions_deleted": 0,
                          "concepts_reused": 0, "concepts_created": 0,
                          "formulas_reused": 0, "formulas_created": 0}, rep.counts
    v3 = _bank(version=3, questions=[_q(2)])
    rep3 = svc.ingest(_env(v3), now_ms=NOW + 2)
    assert rep3.counts["questions_deleted"] == 1
    assert qb.get_question("question:demo:q:00001") is None
    assert qb.get_bank("bank:demo")["content_version"] == 3


# -- 7-9: existing / missing / ambiguous references ------------------------

def test_existing_concept_and_formula_reused(tmp_path):
    db, svc, ac, pe, qb = _svc(tmp_path)
    bank = _bank(questions=[_q(1, concepts=["concept:al:c:00001"],
                               formulas=["formula:al:f:000001"])])
    rep = svc.ingest(
        _env(bank),
        catalog_concepts={"concept:al:c:00001": "Límite"},
        catalog_formulas={"formula:al:f:000001": {"latex": "a+b"}},
        now_ms=NOW)
    assert rep.counts["concepts_created"] == 1
    assert rep.counts["formulas_created"] == 1
    rep2 = svc.ingest(
        _env(_bank(version=2, questions=[_q(
            1, concepts=["concept:al:c:00001"],
            formulas=["formula:al:f:000001"],
            statement="Statement 1 revised?")])),
        now_ms=NOW + 1)
    assert rep2.counts["concepts_reused"] == 1
    assert rep2.counts["formulas_reused"] == 1
    assert rep2.counts["concepts_created"] == 0
    assert len(pe.concepts("subject:al")) == 1  # no duplicates


def test_missing_ref_without_catalog_rejected_with_zero_writes(tmp_path):
    _, svc, _, _, qb = _svc(tmp_path)
    bank = _bank(questions=[_q(1, concepts=["concept:al:c:00009"])])
    with pytest.raises(AcademicManagementError) as e:
        svc.ingest(_env(bank), now_ms=NOW)
    assert e.value.code == "AC-ACD-002"
    assert qb.get_bank("bank:demo") is None
    assert qb.question_digests("bank:demo") == {}


def test_ambiguous_ref_rejected(tmp_path):
    _, svc, _, _, qb = _svc(tmp_path)
    bank = _bank(questions=[_q(1, concepts=["concept:al:c:00001"],
                               formulas=["concept:al:c:00001"])])
    with pytest.raises(AcademicManagementError) as e:
        svc.ingest(_env(bank),
                   catalog_concepts={"concept:al:c:00001": "X"},
                   now_ms=NOW)
    assert e.value.code == "AC-ACD-003"
    assert qb.get_bank("bank:demo") is None


# -- 10-12: provenance, digest, mapping -------------------------------------

def test_provenance_end_to_end(tmp_path):
    _, svc, _, _, qb = _svc(tmp_path)
    bank = _bank(provenance={"source": "dept", "version": "2026.1"})
    rep = svc.ingest(_env(bank), now_ms=NOW)
    assert rep.verified is True
    brow = qb.get_bank("bank:demo")
    bprov = json.loads(brow["provenance"])
    assert bprov["imported_by"] == "d7-ingest/1"
    assert bprov["bank_digest"] == QB.bank_digest(bank)
    qrow = qb.get_question("question:demo:q:00001")
    qprov = json.loads(qrow["provenance"])
    assert qprov["bank"] == "bank:demo"


def test_reuse_never_overwrites_concept(tmp_path):
    _, svc, _, pe, _ = _svc(tmp_path)
    bank = _bank(questions=[_q(1, concepts=["concept:al:c:00001"])])
    svc.ingest(_env(bank),
               catalog_concepts={"concept:al:c:00001": "Original"},
               now_ms=NOW)
    v2 = _bank(version=2, questions=[_q(
        1, concepts=["concept:al:c:00001"], statement="rev?")])
    svc.ingest(_env(v2),
               catalog_concepts={"concept:al:c:00001": "Renamed"},
               now_ms=NOW + 1)
    assert pe.concepts("subject:al")[0].name == "Original"


def test_modified_formula_is_conflict(tmp_path):
    _, svc, _, _, qb = _svc(tmp_path)
    bank = _bank(questions=[_q(1, formulas=["formula:al:f:000001"])])
    svc.ingest(_env(bank),
               catalog_formulas={"formula:al:f:000001": {"latex": "a+b"}},
               now_ms=NOW)
    v2 = _bank(version=2, questions=[_q(
        1, formulas=["formula:al:f:000001"], statement="rev?")])
    with pytest.raises(AcademicManagementError) as e:
        svc.ingest(_env(v2),
                   catalog_formulas={"formula:al:f:000001": {"latex": "a-b"}},
                   now_ms=NOW + 1)
    assert e.value.code == "AC-ACD-003"
    assert qb.get_formula("formula:al:f:000001").latex == "a+b"


# -- 16-17: rollback, dry-run ------------------------------------------------

def test_failed_apply_leaves_zero_writes(tmp_path, monkeypatch):
    _, svc, _, pe, qb = _svc(tmp_path)
    bank = _bank(questions=[_q(1, concepts=["concept:al:c:00001"]),
                            _q(2, concepts=["concept:al:c:00002"])])
    real = pe.add_concept
    calls = {"n": 0}

    def flaky(concept, cx=None):
        calls["n"] += 1
        if calls["n"] > 1:
            raise RuntimeError("boom mid-transaction")
        return real(concept, cx=cx)

    monkeypatch.setattr(pe, "add_concept", flaky)
    with pytest.raises(RuntimeError):
        svc.ingest(_env(bank),
                   catalog_concepts={"concept:al:c:00001": "A",
                                     "concept:al:c:00002": "B"},
                   now_ms=NOW)
    assert qb.get_bank("bank:demo") is None
    assert qb.question_digests("bank:demo") == {}
    assert pe.concepts("subject:al") == []


def test_dry_run_shows_ops_without_writes(tmp_path):
    _, svc, _, pe, qb = _svc(tmp_path)
    bank = _bank(questions=[_q(1, concepts=["concept:al:c:00001"])])
    plan = svc.dry_run(_env(bank),
                       catalog_concepts={"concept:al:c:00001": "Límite"})
    assert plan.outcome == "create"
    assert [q.action for q in plan.questions] == ["create"]
    assert qb.get_bank("bank:demo") is None
    assert pe.concepts("subject:al") == []


# -- 18: determinism ----------------------------------------------------------

def test_plan_and_state_deterministic(tmp_path):
    _, svc, _, _, qb = _svc(tmp_path)
    bank = _bank(questions=[_q(2), _q(1)])
    p1 = svc.dry_run(_env(bank))
    p2 = svc.dry_run(_env(bank))
    assert IN.plan_digest(p1) == IN.plan_digest(p2)
    assert [q.question_id for q in p1.questions] == [
        "question:demo:q:00001", "question:demo:q:00002"]

    def fresh_state(seed_dir):
        _, s2, _, _, q2 = _svc(seed_dir)
        r = s2.ingest(_env(bank), now_ms=NOW)
        return r, q2.get_bank("bank:demo"), q2.question_digests("bank:demo")

    r1, brow1, dig1 = fresh_state(tmp_path / "a")
    (tmp_path / "b").mkdir()
    r2, brow2, dig2 = fresh_state(tmp_path / "b")
    assert r1.bank_digest == r2.bank_digest
    assert dig1 == dig2
    assert {k: brow1[k] for k in ("digest", "question_count")} == \
        {k: brow2[k] for k in ("digest", "question_count")}
    assert qb.get_bank("bank:demo") is None  # main fixture DB untouched


# -- 19: invalid inputs / versions ---------------------------------------------

def test_invalid_bank_rejected(tmp_path):
    _, svc, _, _, qb = _svc(tmp_path)
    with pytest.raises(AcademicManagementError) as e:
        svc.ingest('{"bank": 1}', now_ms=NOW)
    assert e.value.code == "AC-ACD-004"
    env = json.loads(_env(_bank()))
    env["schema_version"] = 999
    with pytest.raises(AcademicManagementError) as e2:
        svc.ingest(env, now_ms=NOW)
    assert e2.value.code == "AC-ACD-004"
    assert qb.get_bank("bank:demo") is None


def test_same_version_new_digest_is_conflict_and_stale_rejected(tmp_path):
    _, svc, _, _, qb = _svc(tmp_path)
    svc.ingest(_env(_bank()), now_ms=NOW)
    same_v = _bank(version=1, questions=[_q(1, statement="changed?")])
    with pytest.raises(AcademicManagementError) as e:
        svc.ingest(_env(same_v), now_ms=NOW + 1)
    assert e.value.code == "AC-ACD-003"
    assert qb.get_bank("bank:demo")["content_version"] == 1


def test_unknown_subject_for_new_concept_rejected(tmp_path):
    db = Database(tmp_path / "nosub.db")
    svc = BankIngestionService(AcademicRepository(db),
                               PersonalRepository(db), QBankRepository(db))
    bank = _bank(questions=[_q(1, concepts=["concept:ghost:c:00001"])])
    with pytest.raises(AcademicManagementError) as e:
        svc.ingest(_env(bank),
                   catalog_concepts={"concept:ghost:c:00001": "X"},
                   now_ms=NOW)
    assert e.value.code == "AC-ACD-002"


# -- 20: security -----------------------------------------------------------------

def test_ingestion_files_have_no_dynamic_execution():
    for rel in ("domain/ingestion.py", "application/bank_ingest.py"):
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
    for rel in ("domain/ingestion.py", "application/bank_ingest.py"):
        for n in ast.walk(ast.parse((SRC / rel).read_text(
                encoding="utf-8"))):
            if isinstance(n, ast.Import):
                mods.update(a.name.split(".")[0] for a in n.names)
            elif isinstance(n, ast.ImportFrom):
                mods.add((n.module or "").split(".")[0])
    assert mods <= {"__future__", "dataclasses", "hashlib", "json", "re",
                    "time", "academic_core"}, mods
    assert "import_module" not in (SRC / "application" / "bank_ingest.py"
                                   ).read_text(encoding="utf-8")


def test_formula_latex_never_executed(tmp_path):
    _, svc, _, _, qb = _svc(tmp_path)
    evil = "__import__('os').system('x')"
    bank = _bank(questions=[_q(1, formulas=["formula:al:f:000001"])])
    svc.ingest(_env(bank),
               catalog_formulas={"formula:al:f:000001": {"latex": evil}},
               now_ms=NOW)
    assert qb.get_formula("formula:al:f:000001").latex == evil
