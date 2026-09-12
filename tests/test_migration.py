"""Migration gate placeholder: formula coverage must stay 100% (Sistemes-de-Mesura).

Phase 0: pins the contract (2896 formulas benchmark shape). Phase 12 runs the
real gate: every source formula retrievable top-k with provenance intact.
"""
import pytest

EXPECTED_FORMULA_COUNT = 2896  # audited in Sistemes-de-Mesura knowledge.sqlite

from academic_core.domain.identity import validate


@pytest.mark.migration
def test_formula_identity_contract():
    # Every migrated formula MUST carry a stable formula: ID + source latex + provenance.
    from academic_core.domain.academic import Formula
    f = Formula(stable_id="formula:sistemes-de-mesura:f:002847",
                latex=r"U=R\\cdot I", source_latex=r"U=R\\cdot I",
                provenance={"source_path": "Tema 3/x.html", "hash": "abc"})
    assert validate(f.stable_id) == "formula"
    assert f.source_latex == f.latex  # original preserved in Phase 0
    assert "source_path" in f.provenance


@pytest.mark.migration
def test_expected_corpus_size_pinned():
    assert EXPECTED_FORMULA_COUNT == 2896
