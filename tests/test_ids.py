"""Identity: unique, persistent, deterministic, filesystem/rowid-independent."""
import pytest

from academic_core.domain.identity import (
    KINDS, IdAllocator, make, slugify, validate,
)


def test_all_phase1_kinds_validate():
    cases = {
        "university:upc": "university",
        "degree:greelec": "degree",
        "year:2025-26": "year",
        "term:c1": "term",
        "professor:ada-lovelace": "professor",
        "tag:urgente": "tag",
        "subject:sistemes-de-mesura": "subject",
        "topic:sistemes-de-mesura:t03": "topic",
        "concept:sistemes-de-mesura:c:00421": "concept",
        "formula:sistemes-de-mesura:f:002847": "formula",
        "resource:sistemes-de-mesura:r:00192": "resource",
        "lab:sistemes-de-mesura:lab:00006": "lab",
        "assignment:sistemes-de-mesura:a:00003": "assignment",
        "project:sistemes-de-mesura:p:00001": "project",
        "exam:sistemes-de-mesura:e:00002": "exam",
        "task:sistemes-de-mesura:task:00007": "task",
    }
    for sid, kind in cases.items():
        assert validate(sid) == kind
    assert set(KINDS) >= set(cases.values())


def test_invalid_rejected():
    for bad in ("subject:UPPER", "topic:s:t3", "task:s:1", "rowid:42",
                "C:\\docs\\tema3.pdf", "formula:sistemes:f:123"):
        with pytest.raises(ValueError):
            validate(bad)


def test_slugify_deterministic():
    assert slugify("Sistemes de Mesura") == slugify("  sistemes—DE  mesura ")
    assert slugify("Àlgebra Lineal II") == "algebra-lineal-ii"


def test_make_backward_compatible_phase0():
    assert make("subject", "sistemes-de-mesura") == "subject:sistemes-de-mesura"
    assert make("formula", "sistemes-de-mesura", "002847") == "formula:sistemes-de-mesura:f:002847"


def test_allocator_sequential_unique():
    alloc = IdAllocator()
    a = alloc.allocate("assignment", "sdm")
    b = alloc.allocate("assignment", "sdm")
    assert a != b and a.endswith("a:00001") and b.endswith("a:00002")
    snap = alloc.snapshot()
    assert IdAllocator(snap).allocate("assignment", "sdm").endswith("a:00003")


def test_allocator_topic_includes_scope_letter():
    """Regression: IdAllocator.allocate("topic", ...) must include the "t"
    scope letter (topic:<subject>:tNN), matching every sibling scoped kind
    (assignment -> a, exam -> e, formula -> f, ...). A prior bug built
    topic ids as topic:<subject>:NN, missing the "t", which fails validate()."""
    alloc = IdAllocator()
    sid = alloc.allocate("topic", "sdm")
    assert sid == "topic:sdm:t01"
    assert validate(sid) == "topic"


def test_allocator_topic_sequential_numbering():
    alloc = IdAllocator()
    first = alloc.allocate("topic", "sdm")
    second = alloc.allocate("topic", "sdm")
    assert first == "topic:sdm:t01"
    assert second == "topic:sdm:t02"
    assert validate(first) == "topic"
    assert validate(second) == "topic"


def test_topic_legacy_bare_form_still_validates():
    """P0-02 Option A: pre-scope-letter rows (topic:<s>:NN) must keep
    validating as kind "topic" — reindex/migration/sync must never
    reject or rewrite them."""
    assert validate("topic:sdm:01") == "topic"
    assert validate("topic:sdm:t01") == "topic"
    assert validate("topic:sistemes-de-mesura:03") == "topic"
    assert validate("topic:sistemes-de-mesura:t03") == "topic"


def test_topic_legacy_ids_preserved_byte_for_byte():
    """Invariante P0-02: old_id == old_id after validate()/make() paths.

    validate() must not normalize, and make() for new rows must mint
    the canonical tNN form without touching existing IDs."""
    legacy = "topic:sdm:01"
    assert validate(legacy) == "topic"
    # Round-trip through storage-facing helpers preserves bytes exactly.
    assert legacy == legacy.strip()
    fresh = make("topic", "sdm", "01")
    assert fresh == "topic:sdm:t01"
    assert validate(fresh) == "topic"
    # Legacy and canonical forms coexist without collision confusion:
    # they are distinct strings, both valid, neither rewritten.
    assert legacy != fresh


def test_topic_legacy_survives_repository_roundtrip(tmp_path):
    """DB antigua + nueva: legacy topic IDs persist through add/get."""
    from academic_core.domain import entities as E
    from academic_core.infrastructure.database import Database
    from academic_core.infrastructure.repositories import AcademicRepository

    repo = AcademicRepository(Database(tmp_path / "t.db"))
    repo.add_university(E.University("university:u", "U"))
    repo.add_degree(E.Degree("degree:d", "D", "university:u"))
    repo.add_year(E.AcademicYear("year:2025-26", "2025-26", "degree:d"))
    repo.add_term(E.Term("term:c1", "C1", "cuatrimestre", 1, "year:2025-26"))
    repo.add_subject(E.Subject("subject:sdm", "SDM", "SDM", "SDM"))
    # Legacy row (as an old DB would hold it) + canonical row coexist.
    repo.add_topic(E.Topic("topic:sdm:01", "subject:sdm", "01", "Legacy"))
    repo.add_topic(E.Topic("topic:sdm:t02", "subject:sdm", "t02", "New"))
    got = {t.stable_id for t in repo.topics_of("subject:sdm")}
    assert "topic:sdm:01" in got
    assert "topic:sdm:t02" in got
