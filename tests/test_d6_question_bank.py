# SPDX-License-Identifier: MIT
"""D6 question-bank contracts: neutral schema, validation, digest, round-trip.

Small contractual tests only (no inflated suite). D6 implements data +
contract + validation + versioning; no D7 ingestion, no F9 correction.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from academic_core.domain.entities import DomainError
from academic_core.domain import question_bank as Q

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "academic_core"


def _mcq(n=1, slug="demo", **kw):
    d = dict(
        question_id=f"question:{slug}:q:{n:05d}",
        statement="What is 2+2?",
        qtype="multiple_choice",
        answer_spec={"options": ["3", "4"], "correct": [1]},
        owner_slug=slug,
    )
    d.update(kw)
    return Q.Question(**d)


def _bank(slug="demo", n_questions=1, **kw):
    d = dict(
        bank_id=f"bank:{slug}",
        title="Demo bank",
        content_version=1,
        questions=tuple(_mcq(i + 1, slug) for i in range(n_questions)),
    )
    d.update(kw)
    return Q.Bank(**d)


def test_minimal_bank_valid():
    b = _bank()
    assert b.bank_id == "bank:demo" and len(b.questions) == 1
    assert Q.bank_digest(b) == Q.bank_digest(_bank())


def test_minimal_question_valid_per_type():
    specs = {
        "multiple_choice": {"options": ["a", "b"], "correct": [0]},
        "true_false": {"answer": True},
        "numeric": {"value": "3.14", "unit": "V"},
        "symbolic": {"expression": "a*x+b", "variables": ["a", "x", "b"]},
        "short_text": {"max_length": 200},
        "structured": {"schema": {"name": "text", "age": "integer"}},
        "circuit": {"netlist_ref": "R1 1 0 1k"},
    }
    for i, (qt, spec) in enumerate(specs.items()):
        q = Q.Question(
            question_id=f"question:demo:q:{i + 1:05d}",
            statement=f"s{i}",
            qtype=qt,
            answer_spec=spec,
            owner_slug="demo",
        )
        assert q.qtype == qt


def test_required_fields_rejected():
    with pytest.raises(DomainError):
        Q.Bank(bank_id="", title="t", content_version=1, questions=())
    with pytest.raises(DomainError):
        Q.Bank(bank_id="bank:x", title="  ", content_version=1, questions=())
    with pytest.raises(DomainError):
        Q.Bank(bank_id="bank:x", title="t", content_version=0, questions=())
    with pytest.raises(DomainError):
        _mcq(statement="  ")


def test_invalid_qtype_and_spec_mismatch():
    with pytest.raises(DomainError):
        _mcq(qtype="essay")
    with pytest.raises(DomainError):  # numeric spec on mcq
        _mcq(answer_spec={"value": "1"})
    with pytest.raises(DomainError):  # correct index out of range
        _mcq(answer_spec={"options": ["a", "b"], "correct": [7]})
    with pytest.raises(DomainError):  # tolerance XOR precision
        _mcq(
            qtype="numeric",
            answer_spec={"value": "1", "tolerance": "0.1", "precision": 3},
        )
    with pytest.raises(DomainError):  # float value, zero-float policy
        _mcq(qtype="numeric", answer_spec={"value": 1.5})


def test_stable_ids():
    assert Q.make_bank_id("My Bank 101") == "bank:my-bank-101"
    assert Q.make_question_id("bank:demo", 7) == "question:demo:q:00007"
    with pytest.raises(DomainError):
        Q.make_question_id("bank:demo", 0)
    with pytest.raises(DomainError):
        Q.Bank(bank_id="subject:demo", title="t", content_version=1, questions=())
    with pytest.raises(DomainError):  # question owned by another bank
        _bank(questions=(_mcq(slug="other"),))
    with pytest.raises(DomainError):  # duplicate question ids
        _bank(n_questions=1, questions=(_mcq(1), _mcq(1)))


def test_schema_version_and_unknown_rejected():
    b = _bank()
    env = json.loads(Q.dumps_bank(b))
    assert env["schema"] == Q.SCHEMA_TAG and env["schema_version"] == 1
    env["schema_version"] = 999
    with pytest.raises(DomainError) as e:
        Q.parse_bank(env)
    assert e.value.code == "AC-VER-001"
    env = json.loads(Q.dumps_bank(b))
    env["schema"] = "other/9"
    with pytest.raises(DomainError):
        Q.parse_bank(env)


def test_canonical_digest_stable_and_semantic():
    b1 = _bank()
    raw = json.loads(Q.dumps_bank(b1))
    shuffled = json.dumps(raw, sort_keys=False)
    b2 = Q.parse_bank(shuffled)
    assert Q.bank_digest(b1) == Q.bank_digest(b2)
    assert Q.bank_digest(b1) == Q.bank_digest(_bank())  # across constructions
    other = _bank(
        questions=(_mcq(answer_spec={"options": ["3", "5"], "correct": [1]}),)
    )
    assert Q.bank_digest(other) != Q.bank_digest(b1)
    assert len(Q.bank_digest(b1)) == 64


def test_round_trip():
    b = _bank(n_questions=3)
    s = Q.dumps_bank(b)
    assert Q.dumps_bank(Q.parse_bank(s)) == s
    assert Q.dumps_bank(Q.parse_bank(Q.dumps_bank(Q.parse_bank(s)))) == s


def test_provenance_reused_shape():
    prov = {"source": "fuentelibro", "version": "1.0", "content_hash": "a" * 64}
    q = _mcq(provenance=prov)
    assert q.provenance["source"] == "fuentelibro"
    with pytest.raises(DomainError):
        _mcq(provenance={"bogus": "x"})
    with pytest.raises(DomainError):
        _mcq(provenance={"content_hash": "zzz"})


def test_knowledge_refs():
    q = _mcq(
        knowledge_refs=[{"kind": "concept", "ref": "concept:al:c:00001"}],
        concepts=["concept:al:c:00001"],
        formulas=["formula:al:f:000001"],
    )
    assert q.knowledge_refs[0]["kind"] == "concept"
    with pytest.raises(DomainError):
        _mcq(knowledge_refs=[{"kind": "exam", "ref": "exam:al:e:00001"}])
    with pytest.raises(DomainError):
        _mcq(knowledge_refs=[{"kind": "concept"}])


def test_answer_specs_validated():
    assert _mcq(qtype="true_false", answer_spec={"answer": False}).answer_spec == {
        "answer": False
    }
    with pytest.raises(DomainError):
        _mcq(qtype="true_false", answer_spec={"answer": 1})
    with pytest.raises(DomainError):
        _mcq(qtype="symbolic", answer_spec={"expression": " "})
    with pytest.raises(DomainError):
        _mcq(
            qtype="structured",
            answer_spec={"schema": {"f": "fuzzy"}},
        )


def test_units_structural_and_resolved_by_system():
    from academic_core.domain.engineering.units import parse_unit

    for sym in ("V", "mV", "kohm", "Hz", "A"):
        parse_unit(sym)  # contract: D6 symbols must resolve in the unit system
    q = _mcq(qtype="numeric", answer_spec={"value": "5", "unit": "mV"})
    assert q.answer_spec["unit"] == "mV"
    with pytest.raises(DomainError):
        _mcq(qtype="numeric", answer_spec={"value": "5", "unit": "vo\nlt"})


def test_extensions_explicit():
    q = _mcq(extensions={"x-hint": "read chapter 2"})
    assert q.extensions == {"x-hint": "read chapter 2"}
    with pytest.raises(DomainError):
        _mcq(extensions={"hint": "no prefix"})
    with pytest.raises(DomainError):
        _mcq(extensions={"x-f": 1.5})  # float never allowed


def test_invalid_structures_rejected():
    b = _bank()
    env = json.loads(Q.dumps_bank(b))
    env["surprise"] = 1
    with pytest.raises(DomainError):
        Q.parse_bank(env)
    env = json.loads(Q.dumps_bank(b))
    env["bank"]["questions"][0]["surprise"] = 1
    with pytest.raises(DomainError):
        Q.parse_bank(env)
    env = json.loads(Q.dumps_bank(b))
    env["integrity"]["digest"] = "0" * 64
    with pytest.raises(DomainError):
        Q.parse_bank(env)
    with pytest.raises(DomainError):
        Q.parse_bank('{"bank": 1}')


def test_deterministic_across_inputs():
    a = Q.dumps_bank(_bank())
    b = Q.dumps_bank(Q.parse_bank(json.loads(a)))
    assert a == b


def test_security_contract():
    bad_names = []
    tree = ast.parse((SRC / "domain" / "question_bank.py").read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name) and f.id in (
                "eval",
                "exec",
                "compile",
                "__import__",
            ):
                bad_names.append(f"{n.lineno}:{f.id}")
            for kw in n.keywords:
                if kw.arg == "shell" and getattr(kw.value, "value", False) is True:
                    bad_names.append(f"{n.lineno}:shell=True")
    assert bad_names == []
    forbidden = {
        "pickle",
        "marshal",
        "subprocess",
        "socket",
        "urllib",
        "http",
        "os",
        "pathlib",
        "sqlite3",
        "threading",
        "ctypes",
        "PySide6",
    }
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods.update(x.name.split(".")[0] for x in n.names)
        elif isinstance(n, ast.ImportFrom):
            mods.add((n.module or "").split(".")[0])
    assert mods <= {
        "__future__",
        "dataclasses",
        "decimal",
        "hashlib",
        "json",
        "re",
        "academic_core",
    }, mods
    with pytest.raises(DomainError):  # duplicate keys refused
        Q.parse_bank('{"schema": 1, "schema": 2}')
    with pytest.raises(DomainError):  # non-finite constants refused
        Q.parse_bank('{"v": NaN}')
    with pytest.raises(DomainError):  # oversize refused
        Q.parse_bank("x" * (Q.MAX_BANK_BYTES + 1))
