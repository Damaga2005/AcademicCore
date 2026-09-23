# SPDX-License-Identifier: MIT
"""F4.1 closure — every migrated document: source SHA-256 == CAS bytes ==
resource version, size, name, subject relation, group, provenance."""
import pytest

from gestion_real_harness import SOURCES, certified


@pytest.mark.parametrize("source", SOURCES)
def test_document_hashes_and_relations(source):
    rep, _ = certified(source)
    d = rep["documents"]
    assert d["mismatches"] == 0 and d["problems"] == []
    assert d["migrated_verified"] + d["preserved_rows"] == d["source_rows"]
    assert d["preserved_rows"] == d["preserved_duplicates_same_subject"]  # none lost
    assert rep["source"]["documents"]["files"] >= d["resources"]
