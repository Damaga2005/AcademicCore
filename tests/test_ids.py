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
