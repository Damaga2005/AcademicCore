"""F8-A: Electronics Knowledge & Analysis Foundation test suite.

Covers: registry invariants, positive/negative/ambiguous concept recognition,
determinism, provenance, B8 -> concept -> analysis integration, and security
(no eval/exec/subprocess in the new domain).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.structural import StructuralCircuitAnalyzer
from academic_core.domain.engineering.units import DIM_NAMES, parse_quantity
from academic_core.domain.electronics import (
    ApplicabilityStatus,
    ConceptCandidate,
    ElectronicsConceptRecognizer,
    check_analysis_applicability,
)
from academic_core.domain.electronics.analyses import ANALYSES
from academic_core.domain.electronics.concepts import CONCEPTS
from academic_core.domain.electronics.equations import EQUATIONS
from academic_core.domain.electronics.models import MODELS
from academic_core.domain.electronics.procedures import PROCEDURES
from academic_core.domain.electronics.registry import TOPOLOGY_TO_CONCEPTS, validate_registries
from academic_core.domain.electronics.types import RelationType


# ==============================================================================
# Helpers
# ==============================================================================
def r_comp(ref, value, n1, n2):
    return Component(ref, "R", parse_quantity(value), {"1": n1, "2": n2})


def v_comp(ref, value, np, nm):
    return Component(ref, "V", parse_quantity(value), {"+": np, "-": nm})


def i_comp(ref, value, np, nm):
    return Component(ref, "I", parse_quantity(value), {"+": np, "-": nm})


def recognize(ckt: Circuit, **kw):
    plan = StructuralCircuitAnalyzer().analyze(ckt, **kw)
    return plan, ElectronicsConceptRecognizer().recognize(plan)


def candidate_map(cands: list[ConceptCandidate]) -> dict[str, ConceptCandidate]:
    return {c.concept: c for c in cands}


# ==============================================================================
# 1. Registry invariants (section 24)
# ==============================================================================
def test_registries_have_no_invariant_violations():
    assert validate_registries() == []


def test_no_duplicate_stable_ids():
    ids = [*CONCEPTS, *EQUATIONS, *MODELS, *ANALYSES, *PROCEDURES]
    assert len(ids) == len(set(ids))


def test_every_concept_has_stable_id_and_provenance():
    for c in CONCEPTS.values():
        assert c.stable_id.startswith("concept:")
        assert c.provenance["source"] == "academic-core-internal"
        assert c.provenance["stable_id"] == c.stable_id


def test_every_equation_has_valid_dimension():
    for e in EQUATIONS.values():
        assert e.dimension in DIM_NAMES.values()


def test_no_dangling_procedure_equation_refs():
    for p in PROCEDURES.values():
        for step in p.steps:
            if step.equation:
                assert step.equation in EQUATIONS


def test_initial_coverage_ids_present():
    expected_concepts = {
        "concept:ohms-law", "concept:kcl", "concept:kvl",
        "concept:series-resistors", "concept:parallel-resistors",
        "concept:voltage-divider", "concept:current-divider",
        "concept:thevenin", "concept:norton", "concept:resistive-bridge",
        "concept:dc-resistive-network",
    }
    assert expected_concepts <= set(CONCEPTS)


# ==============================================================================
# 2. Positive recognition (evidence present)
# ==============================================================================
def test_positive_series_resistors():
    ckt = Circuit("series")
    ckt.add(r_comp("R1", "1 kohm", "in", "mid"))
    ckt.add(r_comp("R2", "2 kohm", "mid", "0"))
    _, cands = recognize(ckt)
    cmap = candidate_map(cands)
    assert cmap["concept:series-resistors"].status == ApplicabilityStatus.APPLICABLE


def test_positive_parallel_resistors():
    ckt = Circuit("parallel")
    ckt.add(r_comp("R1", "1 kohm", "1", "0"))
    ckt.add(r_comp("R2", "1 kohm", "1", "0"))
    _, cands = recognize(ckt)
    cmap = candidate_map(cands)
    assert cmap["concept:parallel-resistors"].status == ApplicabilityStatus.APPLICABLE


def test_positive_voltage_divider_with_explicit_tap():
    ckt = Circuit("v_divider")
    ckt.add(v_comp("V1", "10 V", "in", "0"))
    ckt.add(r_comp("R1", "1 kohm", "in", "out"))
    ckt.add(r_comp("R2", "1 kohm", "out", "0"))
    _, cands = recognize(ckt)
    cmap = candidate_map(cands)
    assert cmap["concept:voltage-divider"].status == ApplicabilityStatus.APPLICABLE
    assert "out" in cmap["concept:voltage-divider"].evidence["metadata"]["tap_nodes"]


def test_positive_current_divider():
    ckt = Circuit("i_divider")
    ckt.add(i_comp("I1", "2 mA", "1", "0"))
    ckt.add(r_comp("R1", "1 kohm", "1", "0"))
    ckt.add(r_comp("R2", "2 kohm", "1", "0"))
    _, cands = recognize(ckt)
    cmap = candidate_map(cands)
    assert cmap["concept:current-divider"].status == ApplicabilityStatus.APPLICABLE


def test_positive_resistive_bridge():
    ckt = Circuit("wheatstone")
    ckt.add(v_comp("V1", "10 V", "top", "bot"))
    ckt.add(r_comp("R1", "1 kohm", "top", "left"))
    ckt.add(r_comp("R2", "1 kohm", "top", "right"))
    ckt.add(r_comp("R3", "1 kohm", "left", "bot"))
    ckt.add(r_comp("R4", "1 kohm", "right", "bot"))
    _, cands = recognize(ckt)
    cmap = candidate_map(cands)
    assert cmap["concept:resistive-bridge"].status == ApplicabilityStatus.APPLICABLE


def test_positive_ohms_law_single_resistor():
    ckt = Circuit("single_r")
    ckt.add(r_comp("R1", "1 kohm", "1", "0"))
    _, cands = recognize(ckt)
    cmap = candidate_map(cands)
    assert cmap["concept:ohms-law"].status == ApplicabilityStatus.APPLICABLE
    assert cmap["concept:dc-resistive-network"].status == ApplicabilityStatus.APPLICABLE


def test_positive_kcl_kvl_dc_resistive_network():
    ckt = Circuit("mixed")
    ckt.add(v_comp("V1", "12 V", "in", "0"))
    ckt.add(r_comp("R1", "1 kohm", "in", "mid"))
    ckt.add(r_comp("R2", "2 kohm", "mid", "0"))
    ckt.add(r_comp("R3", "2 kohm", "mid", "0"))
    _, cands = recognize(ckt)
    cmap = candidate_map(cands)
    assert cmap["concept:kcl"].status == ApplicabilityStatus.APPLICABLE
    assert cmap["concept:kvl"].status == ApplicabilityStatus.APPLICABLE
    assert cmap["concept:dc-resistive-network"].status == ApplicabilityStatus.APPLICABLE


def test_positive_thevenin_norton_applicability_with_target_terminals():
    ckt = Circuit("v_divider")
    ckt.add(v_comp("V1", "10 V", "in", "0"))
    ckt.add(r_comp("R1", "1 kohm", "in", "out"))
    ckt.add(r_comp("R2", "1 kohm", "out", "0"))
    plan = StructuralCircuitAnalyzer().analyze(ckt, target_terminals=("out", "0"))
    thevenin = check_analysis_applicability("analysis:thevenin", plan)
    norton = check_analysis_applicability("analysis:norton", plan)
    assert thevenin.status == ApplicabilityStatus.APPLICABLE
    assert norton.status == ApplicabilityStatus.APPLICABLE


# ==============================================================================
# 3. Negative recognition (evidence absent)
# ==============================================================================
def test_negative_no_voltage_divider_without_source():
    ckt = Circuit("series_only")
    ckt.add(r_comp("R1", "1 kohm", "in", "mid"))
    ckt.add(r_comp("R2", "2 kohm", "mid", "0"))
    _, cands = recognize(ckt)
    cmap = candidate_map(cands)
    assert "concept:voltage-divider" not in cmap


def test_negative_no_bridge_without_four_arm_structure():
    ckt = Circuit("series")
    ckt.add(r_comp("R1", "1 kohm", "in", "mid"))
    ckt.add(r_comp("R2", "2 kohm", "mid", "0"))
    _, cands = recognize(ckt)
    cmap = candidate_map(cands)
    assert "concept:resistive-bridge" not in cmap


def test_negative_thevenin_not_applicable_without_target_terminals():
    ckt = Circuit("v_divider")
    ckt.add(v_comp("V1", "10 V", "in", "0"))
    ckt.add(r_comp("R1", "1 kohm", "in", "out"))
    ckt.add(r_comp("R2", "1 kohm", "out", "0"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)  # no target_terminals
    result = check_analysis_applicability("analysis:thevenin", plan)
    assert result.status == ApplicabilityStatus.NEEDS_INFORMATION


# ==============================================================================
# 4. Ambiguous / abstention
# ==============================================================================
def test_ambiguous_series_resistors_without_source_needs_information_for_divider():
    """Two resistors in series with no source: series-resistors recognized,
    but voltage-divider must never be inferred (no source, no tap)."""
    ckt = Circuit("series_no_source")
    ckt.add(r_comp("R1", "1 kohm", "in", "mid"))
    ckt.add(r_comp("R2", "2 kohm", "mid", "0"))
    _, cands = recognize(ckt)
    cmap = candidate_map(cands)
    assert cmap["concept:series-resistors"].status == ApplicabilityStatus.APPLICABLE
    assert "concept:voltage-divider" not in cmap


def test_abstention_on_empty_circuit():
    ckt = Circuit("empty")
    _, cands = recognize(ckt)
    assert len(cands) == 1
    assert cands[0].status == ApplicabilityStatus.ABSTAINED


def test_abstention_on_disconnected_circuit():
    ckt = Circuit("disconnected")
    ckt.add(r_comp("R1", "1 kohm", "a", "b"))
    ckt.add(r_comp("R2", "1 kohm", "c", "d"))
    _, cands = recognize(ckt)
    assert cands[0].status == ApplicabilityStatus.ABSTAINED


def test_abstention_propagates_to_analysis_applicability():
    ckt = Circuit("empty")
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    result = check_analysis_applicability("analysis:dc", plan)
    assert result.status == ApplicabilityStatus.ABSTAINED


# ==============================================================================
# 5. Determinism
# ==============================================================================
def test_determinism_same_circuit_same_candidates():
    def build():
        ckt = Circuit("v_divider")
        ckt.add(v_comp("V1", "10 V", "in", "0"))
        ckt.add(r_comp("R1", "1 kohm", "in", "out"))
        ckt.add(r_comp("R2", "1 kohm", "out", "0"))
        return ckt

    _, c1 = recognize(build(), at="2026-01-01T00:00:00+00:00")
    _, c2 = recognize(build(), at="2026-01-01T00:00:00+00:00")
    assert [(c.concept, c.status, c.reason) for c in c1] == [(c.concept, c.status, c.reason) for c in c2]


def test_determinism_insertion_order_invariant():
    ckt_a = Circuit("order_a")
    ckt_a.add(r_comp("R1", "1 kohm", "1", "0"))
    ckt_a.add(r_comp("R2", "1 kohm", "1", "0"))

    ckt_b = Circuit("order_a")
    ckt_b.add(r_comp("R2", "1 kohm", "1", "0"))
    ckt_b.add(r_comp("R1", "1 kohm", "1", "0"))

    _, cands_a = recognize(ckt_a, at="2026-01-01T00:00:00+00:00")
    _, cands_b = recognize(ckt_b, at="2026-01-01T00:00:00+00:00")
    assert [(c.concept, c.status) for c in cands_a] == [(c.concept, c.status) for c in cands_b]


def test_candidate_output_sorted_by_concept_id():
    ckt = Circuit("v_divider")
    ckt.add(v_comp("V1", "10 V", "in", "0"))
    ckt.add(r_comp("R1", "1 kohm", "in", "out"))
    ckt.add(r_comp("R2", "1 kohm", "out", "0"))
    _, cands = recognize(ckt)
    ids = [c.concept for c in cands]
    assert ids == sorted(ids)


# ==============================================================================
# 6. Provenance
# ==============================================================================
def test_provenance_same_input_same_plan_digest():
    def build():
        ckt = Circuit("v_divider")
        ckt.add(v_comp("V1", "10 V", "in", "0"))
        ckt.add(r_comp("R1", "1 kohm", "in", "out"))
        ckt.add(r_comp("R2", "1 kohm", "out", "0"))
        return ckt

    plan1 = StructuralCircuitAnalyzer().analyze(build())
    plan2 = StructuralCircuitAnalyzer().analyze(build())
    assert plan1.provenance["digest"] == plan2.provenance["digest"]


# ==============================================================================
# 7. Integration: B8 -> Concept -> Analysis
# ==============================================================================
def test_integration_b8_concept_analysis_chain():
    ckt = Circuit("v_divider")
    ckt.add(v_comp("V1", "10 V", "in", "0"))
    ckt.add(r_comp("R1", "1 kohm", "in", "out"))
    ckt.add(r_comp("R2", "1 kohm", "out", "0"))
    plan, cands = recognize(ckt)

    cmap = candidate_map(cands)
    assert cmap["concept:voltage-divider"].status == ApplicabilityStatus.APPLICABLE

    concept = CONCEPTS["concept:voltage-divider"]
    analysis_ids = concept.targets(RelationType.USES_ANALYSIS)
    assert "analysis:voltage-divider" in analysis_ids

    result = check_analysis_applicability("analysis:voltage-divider", plan)
    assert result.status == ApplicabilityStatus.APPLICABLE

    procedure = PROCEDURES["procedure:voltage-divider-dc"]
    assert procedure.concept == "concept:voltage-divider"
    assert procedure.steps[0].order == 1


def test_engineering_service_recognize_electronics_concepts():
    from academic_core.application.engineering import EngineeringService

    class _StubRepo:
        pass

    svc = EngineeringService(_StubRepo())
    ckt = Circuit("v_divider")
    ckt.add(v_comp("V1", "10 V", "in", "0"))
    ckt.add(r_comp("R1", "1 kohm", "in", "out"))
    ckt.add(r_comp("R2", "1 kohm", "out", "0"))
    plan, cands = svc.recognize_electronics_concepts(ckt)
    cmap = candidate_map(cands)
    assert cmap["concept:voltage-divider"].status == ApplicabilityStatus.APPLICABLE


# ==============================================================================
# 8. Security: no eval/exec/subprocess/network in the new domain
# ==============================================================================
def test_no_eval_exec_subprocess_in_electronics_domain():
    root = Path(__file__).resolve().parents[1] / "src" / "academic_core" / "domain" / "electronics"
    banned = {"eval", "exec", "subprocess", "compile", "os", "socket"}
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in banned:
                pytest.fail(f"{path}: forbidden name {node.id!r} used")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in banned, f"{path}: forbidden import {alias.name}"
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in banned, f"{path}: forbidden import {node.module}"
