"""Unit: stable IDs survive reindex/migration (format + preservation)."""
import pytest

from academic_core.domain.identity import make, validate


def test_all_id_shapes_valid():
    assert validate("subject:sistemes-de-mesura") == "subject"
    assert validate("topic:sistemes-de-mesura:t03") == "topic"
    assert validate("concept:sistemes-de-mesura:c:00421") == "concept"
    assert validate("formula:sistemes-de-mesura:f:002847") == "formula"
    assert validate("resource:sistemes-de-mesura:r:00192") == "resource"


def test_make_roundtrip():
    assert make("formula", "sistemes-de-mesura", "002847") == "formula:sistemes-de-mesura:f:002847"


def test_invalid_rejected():
    with pytest.raises(ValueError):
        validate("formulaSistemes123")
