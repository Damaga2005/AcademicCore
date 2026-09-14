"""Comprehensive test suite for F7-B8 Structural Circuit Analysis.

Covers all 24 mandatory test areas from the F7-B8 specification:
- Resistive topologies (single, series, parallel, voltage divider, current divider, mixed, bridge, non-reducible)
- Sources (independent voltage, independent current)
- Dynamic circuits (RC, RL, RLC, multiple energy storage)
- Topology anomalies and abstention (empty, disconnected, floating, missing GND, short, unsupported components)
- Analysis applicability (KCL, KVL, Power, Thévenin, Norton, DC, Transient, AC)
- Determinism and insertion-order invariance
- Real benchmark test cases (Casos A, B, C, D)
- Explainability
"""

import json
import pytest

from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.structural import (
    AnalysisClassifier,
    AnalysisPlan,
    AnalysisType,
    ApplicabilityStatus,
    CircuitGraph,
    ConfidenceLevel,
    StructuralCircuitAnalyzer,
    TopologyType,
)
from academic_core.domain.engineering.units import parse_quantity


# ==============================================================================
# Helpers
# ==============================================================================
def r_comp(ref: str, value: str, n1: str, n2: str, params: dict | None = None, metadata: dict | None = None) -> Component:
    return Component(ref, "R", parse_quantity(value), {"1": n1, "2": n2}, parameters=params or {}, metadata=metadata or {})


def c_comp(ref: str, value: str, n1: str, n2: str, params: dict | None = None, metadata: dict | None = None) -> Component:
    return Component(ref, "C", parse_quantity(value), {"1": n1, "2": n2}, parameters=params or {}, metadata=metadata or {})


def l_comp(ref: str, value: str, n1: str, n2: str, params: dict | None = None, metadata: dict | None = None) -> Component:
    return Component(ref, "L", parse_quantity(value), {"1": n1, "2": n2}, parameters=params or {}, metadata=metadata or {})


def v_comp(ref: str, value: str, np: str, nm: str, params: dict | None = None, metadata: dict | None = None) -> Component:
    return Component(ref, "V", parse_quantity(value), {"+": np, "-": nm}, parameters=params or {}, metadata=metadata or {})


def i_comp(ref: str, value: str, np: str, nm: str, params: dict | None = None, metadata: dict | None = None) -> Component:
    return Component(ref, "I", parse_quantity(value), {"+": np, "-": nm}, parameters=params or {}, metadata=metadata or {})


# ==============================================================================
# 1. Resistive Topologies
# ==============================================================================
def test_resistive_single_resistor():
    """1. Single resistor recognition."""
    ckt = Circuit("single_r")
    ckt.add(r_comp("R1", "1 kohm", "1", "0"))
    analyzer = StructuralCircuitAnalyzer()
    plan = analyzer.analyze(ckt)

    assert plan.classification == TopologyType.RESISTIVE.value
    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.SINGLE_RESISTOR in topos
    assert plan.applicable_analyses[AnalysisType.OHMS_LAW.value] == ApplicabilityStatus.APPLICABLE.value


def test_resistive_two_resistors_in_series():
    """2. Two resistors in series."""
    ckt = Circuit("series_r")
    ckt.add(r_comp("R1", "1 kohm", "in", "mid"))
    ckt.add(r_comp("R2", "2 kohm", "mid", "0"))
    analyzer = StructuralCircuitAnalyzer()
    plan = analyzer.analyze(ckt)

    assert plan.classification == TopologyType.RESISTIVE.value
    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.SERIES_RESISTORS in topos
    match = next(m for m in plan.recognized_topologies if m.topology == TopologyType.SERIES_RESISTORS)
    assert set(match.elements) == {"R1", "R2"}
    assert "degree 2" in match.reason


def test_resistive_two_resistors_in_parallel():
    """3. Two resistors in parallel."""
    ckt = Circuit("parallel_r")
    ckt.add(r_comp("R1", "1 kohm", "1", "0"))
    ckt.add(r_comp("R2", "1 kohm", "1", "0"))
    analyzer = StructuralCircuitAnalyzer()
    plan = analyzer.analyze(ckt)

    assert plan.classification == TopologyType.RESISTIVE.value
    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.PARALLEL_RESISTORS in topos
    match = next(m for m in plan.recognized_topologies if m.topology == TopologyType.PARALLEL_RESISTORS)
    assert set(match.elements) == {"R1", "R2"}
    assert "parallel" in match.reason


def test_resistive_voltage_divider():
    """4. Voltage divider with intermediate tap."""
    ckt = Circuit("v_divider")
    ckt.add(v_comp("V1", "10 V", "in", "0"))
    ckt.add(r_comp("R1", "1 kohm", "in", "out"))
    ckt.add(r_comp("R2", "1 kohm", "out", "0"))
    analyzer = StructuralCircuitAnalyzer()
    plan = analyzer.analyze(ckt)

    assert plan.classification == TopologyType.RESISTIVE.value
    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.VOLTAGE_DIVIDER in topos
    assert plan.applicable_analyses[AnalysisType.VOLTAGE_DIVIDER.value] == ApplicabilityStatus.APPLICABLE.value
    assert plan.primary_analysis == AnalysisType.DC_OPERATING_POINT


def test_resistive_current_divider():
    """5. Current divider with parallel branches."""
    ckt = Circuit("i_divider")
    ckt.add(i_comp("I1", "2 mA", "1", "0"))
    ckt.add(r_comp("R1", "1 kohm", "1", "0"))
    ckt.add(r_comp("R2", "2 kohm", "1", "0"))
    analyzer = StructuralCircuitAnalyzer()
    plan = analyzer.analyze(ckt)

    assert plan.classification == TopologyType.RESISTIVE.value
    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.CURRENT_DIVIDER in topos
    assert plan.applicable_analyses[AnalysisType.CURRENT_DIVIDER.value] == ApplicabilityStatus.APPLICABLE.value


def test_resistive_series_parallel_mixed():
    """6. Mixed series/parallel reducible network."""
    ckt = Circuit("mixed_sp")
    ckt.add(v_comp("V1", "12 V", "in", "0"))
    ckt.add(r_comp("R1", "1 kohm", "in", "mid"))
    ckt.add(r_comp("R2", "2 kohm", "mid", "0"))
    ckt.add(r_comp("R3", "2 kohm", "mid", "0"))
    analyzer = StructuralCircuitAnalyzer()
    plan = analyzer.analyze(ckt)

    assert plan.classification == TopologyType.RESISTIVE.value
    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.SERIES_PARALLEL_REDUCIBLE in topos
    assert TopologyType.SERIES_PARALLEL_MIXED in topos


def test_resistive_bridge():
    """7. Resistive bridge (Wheatstone)."""
    ckt = Circuit("wheatstone")
    ckt.add(v_comp("V1", "10 V", "top", "bot"))
    ckt.add(r_comp("R1", "1 kohm", "top", "left"))
    ckt.add(r_comp("R2", "1 kohm", "top", "right"))
    ckt.add(r_comp("R3", "1 kohm", "left", "bot"))
    ckt.add(r_comp("R4", "1 kohm", "right", "bot"))
    analyzer = StructuralCircuitAnalyzer()
    plan = analyzer.analyze(ckt)

    assert plan.classification == TopologyType.RESISTIVE.value
    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.RESISTIVE_BRIDGE in topos


def test_resistive_non_reducible():
    """8. Non-reducible bridge network with detector resistor."""
    ckt = Circuit("bridge_mesh")
    ckt.add(v_comp("V1", "10 V", "top", "bot"))
    ckt.add(r_comp("R1", "1 kohm", "top", "left"))
    ckt.add(r_comp("R2", "2 kohm", "top", "right"))
    ckt.add(r_comp("R3", "3 kohm", "left", "bot"))
    ckt.add(r_comp("R4", "4 kohm", "right", "bot"))
    ckt.add(r_comp("R5", "5 kohm", "left", "right"))
    analyzer = StructuralCircuitAnalyzer()
    plan = analyzer.analyze(ckt)

    assert plan.classification == TopologyType.RESISTIVE.value
    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.NON_REDUCIBLE_RESISTIVE in topos


# ==============================================================================
# 2. Sources
# ==============================================================================
def test_independent_voltage_source():
    ckt = Circuit("v_src")
    ckt.add(v_comp("V1", "5 V", "1", "0"))
    ckt.add(r_comp("R1", "100 ohm", "1", "0"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.INDEPENDENT_VOLTAGE_SOURCE in topos


def test_independent_current_source():
    ckt = Circuit("i_src")
    ckt.add(i_comp("I1", "1 A", "1", "0"))
    ckt.add(r_comp("R1", "10 ohm", "1", "0"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.INDEPENDENT_CURRENT_SOURCE in topos


# ==============================================================================
# 3. Dynamic Topologies (RC, RL, RLC)
# ==============================================================================
def test_dynamic_rc():
    ckt = Circuit("rc_ckt")
    ckt.add(v_comp("V1", "5 V", "in", "0"))
    ckt.add(r_comp("R1", "1 kohm", "in", "out"))
    ckt.add(c_comp("C1", "1 uF", "out", "0"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)

    assert plan.classification == TopologyType.RC.value
    assert plan.primary_analysis == AnalysisType.TRANSIENT
    assert plan.applicable_analyses[AnalysisType.TRANSIENT.value] == ApplicabilityStatus.PRIMARY.value
    assert plan.applicable_analyses[AnalysisType.DC_STEADY_STATE.value] == ApplicabilityStatus.APPLICABLE.value


def test_dynamic_rl():
    ckt = Circuit("rl_ckt")
    ckt.add(v_comp("V1", "12 V", "in", "0"))
    ckt.add(r_comp("R1", "100 ohm", "in", "out"))
    ckt.add(l_comp("L1", "10 mH", "out", "0"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)

    assert plan.classification == TopologyType.RL.value
    assert plan.primary_analysis == AnalysisType.TRANSIENT
    assert plan.applicable_analyses[AnalysisType.TRANSIENT.value] == ApplicabilityStatus.PRIMARY.value


def test_dynamic_rlc_without_ac_source():
    """RLC with pure DC excitation should have primary TRANSIENT and AC NOT_APPLICABLE."""
    ckt = Circuit("rlc_ckt")
    ckt.add(v_comp("V1", "10 V", "in", "0"))
    ckt.add(r_comp("R1", "50 ohm", "in", "1"))
    ckt.add(l_comp("L1", "1 mH", "1", "out"))
    ckt.add(c_comp("C1", "100 nF", "out", "0"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)

    assert plan.classification == TopologyType.RLC.value
    assert plan.primary_analysis == AnalysisType.TRANSIENT
    assert plan.applicable_analyses[AnalysisType.TRANSIENT.value] == ApplicabilityStatus.PRIMARY.value
    assert plan.applicable_analyses[AnalysisType.AC.value] == ApplicabilityStatus.NOT_APPLICABLE.value


def test_multiple_storage_elements():
    ckt = Circuit("multi_storage")
    ckt.add(c_comp("C1", "1 uF", "1", "0"))
    ckt.add(c_comp("C2", "2.2 uF", "1", "0"))
    ckt.add(r_comp("R1", "1 kohm", "1", "0"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)

    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.ENERGY_STORAGE in topos


# ==============================================================================
# 4. Topology Anomalies & Mandatory Abstention
# ==============================================================================
def test_empty_circuit_abstention():
    ckt = Circuit("empty")
    plan = StructuralCircuitAnalyzer().analyze(ckt)

    assert plan.classification == TopologyType.UNKNOWN_TOPOLOGY.value
    assert plan.confidence == ConfidenceLevel.ABSTAINED
    assert any("empty" in w for w in plan.warnings)


def test_disconnected_circuit_abstention():
    ckt = Circuit("disconnected")
    ckt.add(r_comp("R1", "1 kohm", "1", "2"))
    ckt.add(r_comp("R2", "1 kohm", "3", "4"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)

    assert plan.classification == TopologyType.UNKNOWN_TOPOLOGY.value
    assert plan.confidence == ConfidenceLevel.ABSTAINED
    assert any("disconnected" in w for w in plan.warnings)


def test_floating_node_warning():
    ckt = Circuit("floating")
    ckt.add(v_comp("V1", "5 V", "1", "0"))
    ckt.add(r_comp("R1", "1 kohm", "1", "0"))
    ckt.add(r_comp("R2", "1 kohm", "1", "floating_pin"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)

    assert any("floating" in w for w in plan.warnings)


def test_missing_gnd_reference_warning():
    ckt = Circuit("no_gnd")
    ckt.add(v_comp("V1", "5 V", "a", "b"))
    ckt.add(r_comp("R1", "1 kohm", "a", "b"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)

    assert any("no reference node" in w for w in plan.warnings)


def test_invalid_short_circuit_abstention():
    ckt = Circuit("shorted_v")
    ckt.add(v_comp("V1", "10 V", "0", "0"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)

    assert plan.classification == TopologyType.UNKNOWN_TOPOLOGY.value
    assert plan.confidence == ConfidenceLevel.ABSTAINED
    assert any("short circuit" in w for w in plan.warnings)


def test_unsupported_component_abstention():
    ckt = Circuit("unsupported_diode")
    ckt.add(v_comp("V1", "5 V", "1", "0"))
    ckt.add(Component("D1", "D", None, {"A": "1", "K": "0"}))
    plan = StructuralCircuitAnalyzer().analyze(ckt)

    assert plan.classification == TopologyType.UNKNOWN_TOPOLOGY.value
    assert plan.confidence == ConfidenceLevel.ABSTAINED
    assert any("unsupported" in w for w in plan.warnings)


# ==============================================================================
# 5. Analysis Applicability (KCL, KVL, Power, Thévenin, Norton)
# ==============================================================================
def test_kcl_kvl_power_applicability():
    ckt = Circuit("linear_network")
    ckt.add(v_comp("V1", "10 V", "1", "0"))
    ckt.add(r_comp("R1", "1 kohm", "1", "2"))
    ckt.add(r_comp("R2", "2 kohm", "2", "0"))
    ckt.add(r_comp("R3", "3 kohm", "2", "0"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)

    assert plan.applicable_analyses[AnalysisType.KCL.value] == ApplicabilityStatus.APPLICABLE.value
    assert plan.applicable_analyses[AnalysisType.KVL.value] == ApplicabilityStatus.APPLICABLE.value
    assert plan.applicable_analyses[AnalysisType.POWER.value] == ApplicabilityStatus.APPLICABLE.value
    assert "2" in plan.kcl_nodes
    assert len(plan.kvl_loops) >= 2


def test_thevenin_norton_with_and_without_target_terminals():
    ckt = Circuit("thevenin_test")
    ckt.add(v_comp("V1", "10 V", "in", "0"))
    ckt.add(r_comp("R1", "1 kohm", "in", "out"))
    ckt.add(r_comp("R2", "1 kohm", "out", "0"))

    # Without target terminals -> NEEDS_TARGET_TERMINALS
    plan_no_port = StructuralCircuitAnalyzer().analyze(ckt)
    assert plan_no_port.applicable_analyses[AnalysisType.THEVENIN.value] == ApplicabilityStatus.NEEDS_TARGET_TERMINALS.value
    assert plan_no_port.applicable_analyses[AnalysisType.NORTON.value] == ApplicabilityStatus.NEEDS_TARGET_TERMINALS.value

    # With target terminals ("out", "0") -> APPLICABLE
    plan_port = StructuralCircuitAnalyzer().analyze(ckt, target_terminals=("out", "0"))
    assert plan_port.applicable_analyses[AnalysisType.THEVENIN.value] == ApplicabilityStatus.APPLICABLE.value
    assert plan_port.applicable_analyses[AnalysisType.NORTON.value] == ApplicabilityStatus.APPLICABLE.value


# ==============================================================================
# 6. Determinism & Invariance to Insertion Order
# ==============================================================================
def test_determinism_multi_run():
    ckt = Circuit("det_ckt")
    ckt.add(v_comp("V1", "10 V", "in", "0"))
    ckt.add(r_comp("R1", "1 kohm", "in", "out"))
    ckt.add(r_comp("R2", "2 kohm", "out", "0"))

    analyzer = StructuralCircuitAnalyzer()
    plan1 = analyzer.analyze(ckt, at="2026-09-13T00:00:00Z")
    plan2 = analyzer.analyze(ckt, at="2026-09-13T00:00:00Z")

    assert plan1.to_json() == plan2.to_json()


def test_invariance_to_component_insertion_order():
    ckt_forward = Circuit("order_fwd")
    ckt_forward.add(v_comp("V1", "10 V", "in", "0"))
    ckt_forward.add(r_comp("R1", "1 kohm", "in", "out"))
    ckt_forward.add(r_comp("R2", "2 kohm", "out", "0"))

    ckt_reverse = Circuit("order_rev")
    ckt_reverse.add(r_comp("R2", "2 kohm", "out", "0"))
    ckt_reverse.add(r_comp("R1", "1 kohm", "in", "out"))
    ckt_reverse.add(v_comp("V1", "10 V", "in", "0"))

    analyzer = StructuralCircuitAnalyzer()
    plan_fwd = analyzer.analyze(ckt_forward, at="2026-09-13T00:00:00Z")
    plan_rev = analyzer.analyze(ckt_reverse, at="2026-09-13T00:00:00Z")

    # Topological classifications, primary analyses, and steps must be identical
    assert plan_fwd.classification == plan_rev.classification
    assert plan_fwd.primary_analysis == plan_rev.primary_analysis
    assert plan_fwd.applicable_analyses == plan_rev.applicable_analyses
    assert [m.topology.value for m in plan_fwd.recognized_topologies] == [
        m.topology.value for m in plan_rev.recognized_topologies
    ]


# ==============================================================================
# 7. Real Circuit Test Cases (Casos A, B, C, D from Spec)
# ==============================================================================
def test_caso_a_voltage_divider():
    """Caso A from spec page 14:
    V1 = 10 V
    R1 = 1 kΩ
    R2 = 1 kΩ
    Esperado:
    RESISTIVE
    VOLTAGE_DIVIDER
    DC_OPERATING_POINT
    POWER
    KCL
    KVL
    """
    ckt = Circuit("caso_a")
    ckt.add(v_comp("V1", "10 V", "1", "0"))
    ckt.add(r_comp("R1", "1 kohm", "1", "2"))
    ckt.add(r_comp("R2", "1 kohm", "2", "0"))

    plan = StructuralCircuitAnalyzer().analyze(ckt)

    assert plan.classification == TopologyType.RESISTIVE.value
    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.VOLTAGE_DIVIDER in topos
    assert plan.primary_analysis == AnalysisType.DC_OPERATING_POINT
    assert plan.applicable_analyses[AnalysisType.DC_OPERATING_POINT.value] == ApplicabilityStatus.PRIMARY.value
    assert plan.applicable_analyses[AnalysisType.POWER.value] == ApplicabilityStatus.APPLICABLE.value
    assert plan.applicable_analyses[AnalysisType.KCL.value] == ApplicabilityStatus.APPLICABLE.value
    assert plan.applicable_analyses[AnalysisType.KVL.value] == ApplicabilityStatus.APPLICABLE.value


def test_caso_b_rc():
    """Caso B from spec page 14:
    V1 = 5 V
    R = 1 kΩ
    C = 1 µF
    Esperado:
    RC
    TRANSIENT
    DC_STEADY_STATE
    """
    ckt = Circuit("caso_b")
    ckt.add(v_comp("V1", "5 V", "1", "0"))
    ckt.add(r_comp("R1", "1 kohm", "1", "2"))
    ckt.add(c_comp("C1", "1 uF", "2", "0"))

    plan = StructuralCircuitAnalyzer().analyze(ckt)

    assert plan.classification == TopologyType.RC.value
    assert plan.primary_analysis == AnalysisType.TRANSIENT
    assert plan.applicable_analyses[AnalysisType.TRANSIENT.value] == ApplicabilityStatus.PRIMARY.value
    assert plan.applicable_analyses[AnalysisType.DC_STEADY_STATE.value] == ApplicabilityStatus.APPLICABLE.value


def test_caso_c_rl():
    """Caso C from spec page 14-15:
    V1
    R
    L
    Esperado:
    RL
    TRANSIENT
    DC_STEADY_STATE
    """
    ckt = Circuit("caso_c")
    ckt.add(v_comp("V1", "10 V", "1", "0"))
    ckt.add(r_comp("R1", "100 ohm", "1", "2"))
    ckt.add(l_comp("L1", "10 mH", "2", "0"))

    plan = StructuralCircuitAnalyzer().analyze(ckt)

    assert plan.classification == TopologyType.RL.value
    assert plan.primary_analysis == AnalysisType.TRANSIENT
    assert plan.applicable_analyses[AnalysisType.TRANSIENT.value] == ApplicabilityStatus.PRIMARY.value
    assert plan.applicable_analyses[AnalysisType.DC_STEADY_STATE.value] == ApplicabilityStatus.APPLICABLE.value


def test_caso_d_rlc():
    """Caso D from spec page 15:
    RLC
    TRANSIENT
    AC (with AC excitation)
    """
    ckt = Circuit("caso_d")
    ckt.add(v_comp("V1", "1 V", "1", "0", params={"ac": "1"}))
    ckt.add(r_comp("R1", "50 ohm", "1", "2"))
    ckt.add(l_comp("L1", "1 mH", "2", "3"))
    ckt.add(c_comp("C1", "10 nF", "3", "0"))

    plan = StructuralCircuitAnalyzer().analyze(ckt)

    assert plan.classification == TopologyType.RLC.value
    assert plan.primary_analysis == AnalysisType.TRANSIENT
    assert plan.applicable_analyses[AnalysisType.AC.value] == ApplicabilityStatus.APPLICABLE.value


# ==============================================================================
# 8. Not Confusing Component with Analysis (Spec Page 15)
# ==============================================================================
def test_isolated_capacitor_not_classified_as_rc():
    """An isolated capacitor without resistors should not be classified as RC."""
    ckt = Circuit("pure_c")
    ckt.add(v_comp("V1", "5 V", "1", "0"))
    ckt.add(c_comp("C1", "10 uF", "1", "0"))

    plan = StructuralCircuitAnalyzer().analyze(ckt)

    assert plan.classification != TopologyType.RC.value
    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.RC not in topos
    assert TopologyType.ENERGY_STORAGE in topos


def test_single_resistor_not_classified_as_voltage_divider():
    """A single resistor across a voltage source is not a voltage divider."""
    ckt = Circuit("pure_r")
    ckt.add(v_comp("V1", "5 V", "1", "0"))
    ckt.add(r_comp("R1", "1 kohm", "1", "0"))

    plan = StructuralCircuitAnalyzer().analyze(ckt)

    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.VOLTAGE_DIVIDER not in topos
    assert plan.applicable_analyses[AnalysisType.VOLTAGE_DIVIDER.value] == ApplicabilityStatus.NOT_APPLICABLE.value


# ==============================================================================
# 9. Application Service Integration
# ==============================================================================
def test_engineering_service_integration(tmp_path):
    from academic_core.application.engineering import EngineeringService
    from academic_core.infrastructure.database import Database
    from academic_core.infrastructure.engineering import EngineeringRepository

    db = Database(tmp_path / "test.db")
    repo = EngineeringRepository(db)
    svc = EngineeringService(repo)


    svc.create_project("p1")
    ckt = Circuit("ckt_div")
    ckt.add(v_comp("V1", "10 V", "in", "0"))
    ckt.add(r_comp("R1", "1 kohm", "in", "out"))
    ckt.add(r_comp("R2", "1 kohm", "out", "0"))
    svc.save_circuit("p1", ckt)

    plan = svc.analyze_circuit_structure("p1", "ckt_div", target_terminals=("out", "0"))
    assert plan.classification == TopologyType.RESISTIVE.value
    assert plan.applicable_analyses[AnalysisType.THEVENIN.value] == ApplicabilityStatus.APPLICABLE.value


# ==============================================================================
# 10. Extensibility & Scope Constraints
# ==============================================================================
def test_extensibility_custom_rule():
    """Verify that new recognition rules can be plugged into RuleRegistry without modifying analyzer."""
    from academic_core.domain.engineering.structural import (
        RecognitionMatch,
        RecognitionRule,
        RuleRegistry,
    )

    class CustomHighResistanceRule(RecognitionRule):
        @property
        def rule_name(self) -> str:
            return "CustomHighResistanceRule"

        def evaluate(self, graph):
            matches = []
            for c in graph.components.values():
                if c.type == "R" and c.value and c.value.to_base() >= 1000000:
                    matches.append(
                        RecognitionMatch(
                            topology=TopologyType.RESISTIVE,
                            elements=(c.ref,),
                            reason=f"High-value megohm resistor {c.ref}.",
                        )
                    )
            return matches

    registry = RuleRegistry(default_rules=True)
    registry.register(CustomHighResistanceRule())
    analyzer = StructuralCircuitAnalyzer(registry=registry)

    ckt = Circuit("mega")
    ckt.add(r_comp("R1", "10 Mohm", "1", "0"))
    plan = analyzer.analyze(ckt)

    reasons = [m.reason for m in plan.recognized_topologies]
    assert any("High-value megohm resistor R1" in r for r in reasons)


def test_dependent_sources_canonical_scope():
    """F6/F7-B8 scope for R/C/L/V/I/D/Q, extended by F8-E for E/G/H/F.

    F8-E (VCVS/VCCS/CCVS/CCCS) deliberately reuses the F6 `Component`
    model and registers the four dependent-source letters in
    `COMPONENT_PINS` (spec F8-E section 5: "reuse F6 Component, do not
    create a new component representation") instead of introducing a
    parallel model. This test originally asserted their absence; F8-E's
    declared scope makes that assertion obsolete, so it now asserts the
    opposite (present, with output pins "+"/"-") while still confirming
    that a malformed pin set (mixing in the R/L/C "1"/"2" pin scheme)
    is rejected exactly like every other component type.
    """
    from academic_core.domain.engineering.circuit import COMPONENT_PINS, CircuitError

    # Independent sources V and I are supported
    assert "V" in COMPONENT_PINS
    assert "I" in COMPONENT_PINS

    # Dependent source letters (E, G, F, H) are canonical as of F8-E,
    # with the same "+"/"-" output pin scheme as V/I.
    for dep_type in ("E", "G", "F", "H"):
        assert dep_type in COMPONENT_PINS
        assert COMPONENT_PINS[dep_type] == ("+", "-")
        with pytest.raises(CircuitError):
            Component(f"{dep_type}1", dep_type, None, {"1": "in", "2": "out"})


# ==============================================================================
# 11. Hardening & Adversarial Test Suite (Eliminate False Positives)
# ==============================================================================
def test_adversarial_c_clamped_across_ideal_voltage_not_rc():
    """A capacitor connected directly across an ideal voltage source is clamped, not RC."""
    ckt = Circuit("c_clamped")
    ckt.add(v_comp("V1", "5 V", "1", "0"))
    ckt.add(c_comp("C1", "1 uF", "1", "0"))
    ckt.add(r_comp("R1", "1 kohm", "1", "0"))

    plan = StructuralCircuitAnalyzer().analyze(ckt)
    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.RC not in topos
    assert plan.classification != TopologyType.RC.value


def test_adversarial_floating_reactive_elements_not_rc_rl():
    """Floating capacitor or inductor does not form RC or RL."""
    ckt_rc = Circuit("floating_c")
    ckt_rc.add(v_comp("V1", "5 V", "1", "0"))
    ckt_rc.add(r_comp("R1", "1 kohm", "1", "0"))
    ckt_rc.add(c_comp("C1", "1 uF", "float1", "float2"))

    plan_rc = StructuralCircuitAnalyzer().analyze(ckt_rc)
    topos_rc = {m.topology for m in plan_rc.recognized_topologies}
    assert TopologyType.RC not in topos_rc

    ckt_rl = Circuit("floating_l")
    ckt_rl.add(v_comp("V1", "5 V", "1", "0"))
    ckt_rl.add(r_comp("R1", "1 kohm", "1", "0"))
    ckt_rl.add(l_comp("L1", "1 mH", "float1", "float2"))

    plan_rl = StructuralCircuitAnalyzer().analyze(ckt_rl)
    topos_rl = {m.topology for m in plan_rl.recognized_topologies}
    assert TopologyType.RL not in topos_rl


def test_adversarial_uncoupled_rc_rl_loops_not_rlc():
    """Separate uncoupled RC and RL loops must not be classified as RLC."""
    ckt = Circuit("uncoupled_rc_rl")
    # Loop 1: V1 - R1 - C1
    ckt.add(v_comp("V1", "5 V", "1", "0"))
    ckt.add(r_comp("R1", "1 kohm", "1", "2"))
    ckt.add(c_comp("C1", "1 uF", "2", "0"))
    # Loop 2: V2 - R2 - L1 (completely separate nodes 3, 4, 5)
    ckt.add(v_comp("V2", "5 V", "3", "5"))
    ckt.add(r_comp("R2", "1 kohm", "3", "4"))
    ckt.add(l_comp("L1", "1 mH", "4", "5"))

    plan = StructuralCircuitAnalyzer().analyze(ckt)
    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.RLC not in topos


def test_voltage_divider_tap_nodes_and_no_vout_assumption():
    """Voltage divider must expose tap_nodes, output_node is None, and reason must not invent Vout."""
    ckt = Circuit("vdiv_clean")
    ckt.add(v_comp("V1", "10 V", "in", "0"))
    ckt.add(r_comp("R1", "1 kohm", "in", "mid"))
    ckt.add(r_comp("R2", "1 kohm", "mid", "0"))

    plan = StructuralCircuitAnalyzer().analyze(ckt)
    vdiv_matches = [m for m in plan.recognized_topologies if m.topology == TopologyType.VOLTAGE_DIVIDER]
    assert len(vdiv_matches) == 1
    match = vdiv_matches[0]
    assert match.metadata["tap_nodes"] == ["mid"]
    assert match.metadata["output_node"] is None
    assert "Vout" not in match.reason
    assert "Vout = mid" not in match.reason


def test_ac_applicability_strictness():
    """RLC circuit with pure DC source must NOT mark AC as applicable."""
    ckt_dc = Circuit("rlc_dc")
    ckt_dc.add(v_comp("V1", "10 V", "1", "0"))
    ckt_dc.add(r_comp("R1", "10 ohm", "1", "2"))
    ckt_dc.add(l_comp("L1", "1 mH", "2", "3"))
    ckt_dc.add(c_comp("C1", "1 uF", "3", "0"))

    plan_dc = StructuralCircuitAnalyzer().analyze(ckt_dc)
    assert plan_dc.applicable_analyses[AnalysisType.AC.value] == ApplicabilityStatus.NOT_APPLICABLE.value
    assert plan_dc.primary_analysis == AnalysisType.TRANSIENT

    # Now with AC source
    ckt_ac = Circuit("rlc_ac")
    ckt_ac.add(v_comp("V1", "10 V", "1", "0", params={"ac": "1"}))
    ckt_ac.add(r_comp("R1", "10 ohm", "1", "2"))
    ckt_ac.add(l_comp("L1", "1 mH", "2", "3"))
    ckt_ac.add(c_comp("C1", "1 uF", "3", "0"))

    plan_ac = StructuralCircuitAnalyzer().analyze(ckt_ac)
    assert plan_ac.applicable_analyses[AnalysisType.AC.value] == ApplicabilityStatus.APPLICABLE.value


def test_uncertainty_and_statistical_applicability_strictness():
    """Plain resistors without tolerance/uncertainty metadata must not trigger MC/GUM/Sensitivity."""
    ckt_plain = Circuit("plain")
    ckt_plain.add(v_comp("V1", "10 V", "1", "0"))
    ckt_plain.add(r_comp("R1", "1 kohm", "1", "0"))

    plan = StructuralCircuitAnalyzer().analyze(ckt_plain)
    assert plan.applicable_analyses[AnalysisType.MONTE_CARLO.value] == ApplicabilityStatus.NOT_APPLICABLE.value
    assert plan.applicable_analyses[AnalysisType.GUM_UNCERTAINTY.value] == ApplicabilityStatus.NOT_APPLICABLE.value
    assert plan.applicable_analyses[AnalysisType.SENSITIVITY.value] == ApplicabilityStatus.NOT_APPLICABLE.value

    # With tolerance metadata
    ckt_mc = Circuit("with_tol")
    ckt_mc.add(v_comp("V1", "10 V", "1", "0"))
    ckt_mc.add(r_comp("R1", "1 kohm", "1", "0", params={"tolerance": "5%"}))
    plan_mc = StructuralCircuitAnalyzer().analyze(ckt_mc)
    assert plan_mc.applicable_analyses[AnalysisType.MONTE_CARLO.value] == ApplicabilityStatus.APPLICABLE.value

    # With GUM uncertainty metadata
    ckt_gum = Circuit("with_gum")
    ckt_gum.add(v_comp("V1", "10 V", "1", "0"))
    ckt_gum.add(r_comp("R1", "1 kohm", "1", "0", params={"uncertainty": "0.01"}))
    plan_gum = StructuralCircuitAnalyzer().analyze(ckt_gum)
    assert plan_gum.applicable_analyses[AnalysisType.GUM_UNCERTAINTY.value] == ApplicabilityStatus.APPLICABLE.value

    # With sensitivity metadata
    ckt_sens = Circuit("with_sens")
    ckt_sens.add(v_comp("V1", "10 V", "1", "0"))
    ckt_sens.add(r_comp("R1", "1 kohm", "1", "0", params={"sensitivity": "true"}))
    plan_sens = StructuralCircuitAnalyzer().analyze(ckt_sens)
    assert plan_sens.applicable_analyses[AnalysisType.SENSITIVITY.value] == ApplicabilityStatus.APPLICABLE.value


def test_thevenin_norton_port_validation():
    """Thévenin/Norton requires target_terminals; invalid/degenerate terminals must return UNKNOWN."""
    ckt = Circuit("thev_test")
    ckt.add(v_comp("V1", "10 V", "1", "0"))
    ckt.add(r_comp("R1", "1 kohm", "1", "2"))
    ckt.add(r_comp("R2", "1 kohm", "2", "0"))

    analyzer = StructuralCircuitAnalyzer()

    # None specified
    plan_none = analyzer.analyze(ckt)
    assert plan_none.applicable_analyses[AnalysisType.THEVENIN.value] == ApplicabilityStatus.NEEDS_TARGET_TERMINALS.value

    # Degenerate: same node twice
    plan_degen = analyzer.analyze(ckt, target_terminals=("2", "2"))
    assert plan_degen.applicable_analyses[AnalysisType.THEVENIN.value] == ApplicabilityStatus.UNKNOWN.value
    assert any("degenerate target terminals" in w for w in plan_degen.warnings)

    # Non-existent node
    plan_nonexist = analyzer.analyze(ckt, target_terminals=("2", "99"))
    assert plan_nonexist.applicable_analyses[AnalysisType.THEVENIN.value] == ApplicabilityStatus.UNKNOWN.value
    assert any("not found in circuit" in w for w in plan_nonexist.warnings)

    # Valid distinct terminals
    plan_valid = analyzer.analyze(ckt, target_terminals=("2", "0"))
    assert plan_valid.applicable_analyses[AnalysisType.THEVENIN.value] == ApplicabilityStatus.APPLICABLE.value


def test_series_parallel_negative_checks():
    """Resistors sharing a node with a 3rd branch are NOT series; resistors with mismatched nodes are NOT parallel."""
    ckt = Circuit("not_series")
    ckt.add(v_comp("V1", "10 V", "1", "0"))
    ckt.add(r_comp("R1", "1 kohm", "1", "2"))
    ckt.add(r_comp("R2", "1 kohm", "2", "3"))
    ckt.add(r_comp("R3", "1 kohm", "2", "0"))  # degree of node 2 is 3!
    ckt.add(r_comp("R4", "1 kohm", "3", "0"))

    graph = CircuitGraph(ckt)
    series_pairs = graph.get_series_pairs()
    # R1 and R2 do NOT form a series pair because node 2 has degree 3
    assert ("R1", "R2") not in series_pairs
    assert ("R2", "R1") not in series_pairs


def test_resistive_bridge_requires_diagonal_excitation():
    """4 resistors in a ring without diagonal excitation source must NOT be recognized as bridge."""
    ckt_no_src = Circuit("ring_no_src")
    ckt_no_src.add(r_comp("R1", "1 kohm", "A", "C"))
    ckt_no_src.add(r_comp("R2", "1 kohm", "A", "D"))
    ckt_no_src.add(r_comp("R3", "1 kohm", "B", "C"))
    ckt_no_src.add(r_comp("R4", "1 kohm", "B", "D"))

    plan_no_src = StructuralCircuitAnalyzer().analyze(ckt_no_src)
    topos = {m.topology for m in plan_no_src.recognized_topologies}
    assert TopologyType.RESISTIVE_BRIDGE not in topos

    # Source on an arm instead of diagonal
    ckt_arm_src = Circuit("ring_arm_src")
    ckt_arm_src.add(v_comp("V1", "10 V", "A", "C"))  # arm AC, not diagonal AB or CD!
    ckt_arm_src.add(r_comp("R1", "1 kohm", "A", "C"))
    ckt_arm_src.add(r_comp("R2", "1 kohm", "A", "D"))
    ckt_arm_src.add(r_comp("R3", "1 kohm", "B", "C"))
    ckt_arm_src.add(r_comp("R4", "1 kohm", "B", "D"))

    plan_arm_src = StructuralCircuitAnalyzer().analyze(ckt_arm_src)
    topos_arm = {m.topology for m in plan_arm_src.recognized_topologies}
    assert TopologyType.RESISTIVE_BRIDGE not in topos_arm


def test_confidence_and_abstention_semantics():
    """Deterministic rules with warnings remain DETERMINISTIC; abstention clears recognized_topologies."""
    # Degenerate circuit causing abstention
    ckt_empty = Circuit("empty")
    plan = StructuralCircuitAnalyzer().analyze(ckt_empty)
    assert plan.classification == TopologyType.UNKNOWN_TOPOLOGY.value
    assert plan.recognized_topologies == []
    assert plan.confidence == ConfidenceLevel.ABSTAINED

    # Valid circuit with terminal warning remains DETERMINISTIC
    ckt = Circuit("warn_det")
    ckt.add(v_comp("V1", "10 V", "1", "0"))
    ckt.add(r_comp("R1", "1 kohm", "1", "0"))
    plan_warn = StructuralCircuitAnalyzer().analyze(ckt, target_terminals=("1", "1"))
    assert len(plan_warn.warnings) > 0
    assert plan_warn.confidence == ConfidenceLevel.DETERMINISTIC


def test_euler_cycle_basis():
    """Euler cycle basis satisfies M = E - V + C for planar/non-planar graphs."""
    # Wheatstone bridge with diagonal source: 4 nodes, 5 edges (4 R + 1 V)
    ckt = Circuit("euler_bridge")
    ckt.add(v_comp("V1", "10 V", "A", "B"))
    ckt.add(r_comp("R1", "1 kohm", "A", "C"))
    ckt.add(r_comp("R2", "1 kohm", "A", "D"))
    ckt.add(r_comp("R3", "1 kohm", "B", "C"))
    ckt.add(r_comp("R4", "1 kohm", "B", "D"))

    graph = CircuitGraph(ckt)
    loops = graph.get_fundamental_loops()
    # Nodes V = 4, Edges E = 5, Components C = 1 -> Loops = 5 - 4 + 1 = 2
    assert len(loops) == 2


# ==============================================================================
# 10. HARDENING SUITE (F7-B8 hardening definitivo)
# ==============================================================================

# -- 10.1 `re` import bug + textual AC detection branch -----------------------
def test_re_import_present_and_textual_ac_branch_executes():
    """planning.py must import `re` at module scope and the textual AC
    detection branch (word-boundary regex over string parameter/metadata
    values) must be reachable and correct."""
    from academic_core.domain.engineering.structural import planning as planning_mod

    assert hasattr(planning_mod, "re"), "planning.py must `import re` explicitly"

    # Valid textual AC representation (word-boundary "ac")
    ckt_txt = Circuit("textual_ac")
    ckt_txt.add(v_comp("V1", "10 V", "1", "0", params={"waveform": "AC 5V 60Hz"}))
    ckt_txt.add(r_comp("R1", "1 kohm", "1", "0"))
    plan_txt = StructuralCircuitAnalyzer().analyze(ckt_txt)
    assert plan_txt.applicable_analyses[AnalysisType.AC.value] == ApplicabilityStatus.APPLICABLE.value

    # Invalid textual representation: "ac" only as a substring of another word
    ckt_bad = Circuit("textual_not_ac")
    ckt_bad.add(v_comp("V1", "10 V", "1", "0", params={"note": "trace calibration"}))
    ckt_bad.add(r_comp("R1", "1 kohm", "1", "0"))
    plan_bad = StructuralCircuitAnalyzer().analyze(ckt_bad)
    assert plan_bad.applicable_analyses[AnalysisType.AC.value] == ApplicabilityStatus.NOT_APPLICABLE.value


# -- 10.2 AC semantic hardening -------------------------------------------------
@pytest.mark.parametrize(
    "ac_value",
    [False, None, "", 0, "false", "none", "off", "no"],
)
def test_ac_rejects_falsy_and_negated_markers(ac_value):
    ckt = Circuit("rlc_ac_falsy")
    ckt.add(v_comp("V1", "10 V", "in", "0", params={"ac": ac_value}))
    ckt.add(r_comp("R1", "50 ohm", "in", "1"))
    ckt.add(l_comp("L1", "1 mH", "1", "2"))
    ckt.add(c_comp("C1", "100 nF", "2", "0"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    assert plan.applicable_analyses[AnalysisType.AC.value] == ApplicabilityStatus.NOT_APPLICABLE.value


def test_ac_pure_dc_rlc_not_applicable():
    ckt = Circuit("rlc_pure_dc")
    ckt.add(v_comp("V1", "10 V", "in", "0"))
    ckt.add(r_comp("R1", "50 ohm", "in", "1"))
    ckt.add(l_comp("L1", "1 mH", "1", "2"))
    ckt.add(c_comp("C1", "100 nF", "2", "0"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    assert plan.applicable_analyses[AnalysisType.AC.value] == ApplicabilityStatus.NOT_APPLICABLE.value


def test_ac_unrelated_metadata_containing_substring_not_applicable():
    """A metadata key/value that happens to contain the substring 'ac' must not trigger AC."""
    ckt = Circuit("unrelated_ac_substring")
    ckt.add(v_comp("V1", "10 V", "in", "0", metadata={"package": "TO-220", "trace_width": "2mm"}))
    ckt.add(r_comp("R1", "50 ohm", "in", "0"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    assert plan.applicable_analyses[AnalysisType.AC.value] == ApplicabilityStatus.NOT_APPLICABLE.value


def test_ac_valid_amplitude_frequency_structure_applicable():
    ckt = Circuit("ac_amp_freq")
    ckt.add(v_comp("V1", "10 V", "in", "0", params={"amplitude": "5V", "frequency": "60Hz"}))
    ckt.add(r_comp("R1", "50 ohm", "in", "0"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    assert plan.applicable_analyses[AnalysisType.AC.value] == ApplicabilityStatus.APPLICABLE.value


def test_ac_valid_explicit_marker_applicable():
    ckt = Circuit("ac_valid_marker")
    ckt.add(v_comp("V1", "10 V", "in", "0", params={"ac": True}))
    ckt.add(r_comp("R1", "50 ohm", "in", "0"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    assert plan.applicable_analyses[AnalysisType.AC.value] == ApplicabilityStatus.APPLICABLE.value


def test_ac_key_only_on_non_source_component_ignored():
    """An 'ac' key on a resistor (not a V/I source) must never count as excitation evidence."""
    ckt = Circuit("ac_on_resistor")
    ckt.add(v_comp("V1", "10 V", "in", "0"))
    ckt.add(r_comp("R1", "50 ohm", "in", "0", params={"ac": True}))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    assert plan.applicable_analyses[AnalysisType.AC.value] == ApplicabilityStatus.NOT_APPLICABLE.value


# -- 10.3 RC/RL/RLC dynamic network hardening ----------------------------------
def test_rc_disconnected_r_and_c_not_recognized():
    """R and C present but wired into two disconnected subgraphs: no RC."""
    ckt = Circuit("rc_disconnected")
    ckt.add(v_comp("V1", "5 V", "a", "b"))
    ckt.add(r_comp("R1", "1 kohm", "a", "b"))
    ckt.add(c_comp("C1", "1 uF", "x", "y"))
    ckt.add(r_comp("R2", "1 kohm", "x", "y"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    # Disconnected circuits abstain entirely (structural precondition), never
    # inventing a dynamic classification out of unrelated subgraphs.
    assert plan.confidence == ConfidenceLevel.ABSTAINED
    assert TopologyType.RC.value != plan.classification


def test_rc_capacitor_clamped_by_ideal_voltage_source_not_rc():
    ckt = Circuit("rc_clamped")
    ckt.add(v_comp("V1", "5 V", "1", "0"))
    ckt.add(c_comp("C1", "1 uF", "1", "0"))
    ckt.add(r_comp("R1", "1 kohm", "1", "0"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.RC not in topos


def test_rl_inductor_clamped_by_ideal_current_source_not_rl():
    ckt = Circuit("rl_clamped")
    ckt.add(i_comp("I1", "1 A", "1", "0"))
    ckt.add(l_comp("L1", "1 mH", "1", "0"))
    ckt.add(r_comp("R1", "10 ohm", "1", "0"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.RL not in topos


def test_rl_two_independent_subnetworks_not_rl():
    ckt = Circuit("rl_two_subnets")
    ckt.add(v_comp("V1", "5 V", "a", "b"))
    ckt.add(r_comp("R1", "10 ohm", "a", "b"))
    ckt.add(l_comp("L1", "1 mH", "x", "y"))
    ckt.add(r_comp("R2", "10 ohm", "x", "y"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    assert plan.confidence == ConfidenceLevel.ABSTAINED
    assert TopologyType.RL.value != plan.classification


def test_rlc_caso_a_v_r_c():
    """Case A: V1-R-C -> RC."""
    ckt = Circuit("caso_a_rc")
    ckt.add(v_comp("V1", "5 V", "1", "2"))
    ckt.add(r_comp("R1", "1 kohm", "2", "3"))
    ckt.add(c_comp("C1", "1 uF", "3", "1"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    assert plan.classification == TopologyType.RC.value


def test_rlc_caso_b_v_r_l():
    """Case B: V1-R-L -> RL."""
    ckt = Circuit("caso_b_rl")
    ckt.add(v_comp("V1", "5 V", "1", "2"))
    ckt.add(r_comp("R1", "10 ohm", "2", "3"))
    ckt.add(l_comp("L1", "1 mH", "3", "1"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    assert plan.classification == TopologyType.RL.value


def test_rlc_caso_c_v_r_l_c():
    """Case C: V1-R-L-C -> RLC."""
    ckt = Circuit("caso_c_rlc")
    ckt.add(v_comp("V1", "5 V", "1", "2"))
    ckt.add(r_comp("R1", "10 ohm", "2", "3"))
    ckt.add(l_comp("L1", "1 mH", "3", "4"))
    ckt.add(c_comp("C1", "1 uF", "4", "1"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    assert plan.classification == TopologyType.RLC.value


def test_rlc_caso_d_independent_rc_and_rl_loops_not_rlc():
    """Case D: an RC loop and an RL loop sharing only GND -> NOT RLC (no RC/RL either,
    since the mutually-exclusive dynamic classification is deliberately conservative
    when both C and L are present but not coupled)."""
    ckt = Circuit("caso_d_rc_plus_rl")
    ckt.add(v_comp("V1", "5 V", "in", "0"))
    ckt.add(r_comp("R1", "1 kohm", "in", "capnode"))
    ckt.add(c_comp("C1", "1 uF", "capnode", "0"))
    ckt.add(r_comp("R2", "10 ohm", "in", "indnode"))
    ckt.add(l_comp("L1", "1 mH", "indnode", "0"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    assert plan.classification != TopologyType.RLC.value
    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.RLC not in topos


def test_rlc_caso_e_r_network_plus_isolated_c_and_l_not_rlc():
    """Case E: R network + isolated (floating) C + isolated L -> NOT RLC."""
    ckt = Circuit("caso_e_isolated")
    ckt.add(v_comp("V1", "5 V", "1", "0"))
    ckt.add(r_comp("R1", "1 kohm", "1", "0"))
    ckt.add(c_comp("C1", "1 uF", "2", "3"))  # floating: 2 and 3 unused elsewhere
    ckt.add(l_comp("L1", "1 mH", "4", "5"))  # floating: 4 and 5 unused elsewhere
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    # Floating C/L nodes make this disconnected overall -> abstained.
    assert plan.confidence == ConfidenceLevel.ABSTAINED
    assert plan.classification != TopologyType.RLC.value


def test_rlc_caso_g_floating_reactive_element_no_rc_rl_rlc():
    ckt = Circuit("caso_g_floating")
    ckt.add(v_comp("V1", "5 V", "1", "0"))
    ckt.add(r_comp("R1", "1 kohm", "1", "0"))
    ckt.add(c_comp("C1", "1 uF", "1", "dangling"))  # dangling has degree 1
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.RC not in topos
    assert TopologyType.RLC not in topos


def test_energy_storage_does_not_imply_rc_rl_rlc_transient():
    """ENERGY_STORAGE alone (no coherent dynamic loop demonstrated) must not
    imply RC/RL/RLC classification nor a TRANSIENT primary analysis."""
    ckt = Circuit("energy_storage_only")
    ckt.add(v_comp("V1", "5 V", "1", "0"))
    ckt.add(r_comp("R1", "1 kohm", "1", "0"))
    ckt.add(c_comp("C1", "1 uF", "1", "0"))  # clamped directly by V1: no dynamic DOF
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.ENERGY_STORAGE in topos
    assert TopologyType.RC not in topos
    assert plan.classification != TopologyType.RC.value
    assert plan.primary_analysis != AnalysisType.TRANSIENT


# -- 10.4 Voltage / current divider hardening ----------------------------------
def test_voltage_divider_never_infers_output_node():
    """V1-R1-N1-R2-GND: tap_nodes = ['N1'], output_node must stay None."""
    ckt = Circuit("no_vout_guess")
    ckt.add(v_comp("V1", "10 V", "V1P", "0"))
    ckt.add(r_comp("R1", "1 kohm", "V1P", "N1"))
    ckt.add(r_comp("R2", "1 kohm", "N1", "0"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    match = next(m for m in plan.recognized_topologies if m.topology == TopologyType.VOLTAGE_DIVIDER)
    assert match.metadata["tap_nodes"] == ["N1"]
    assert match.metadata["output_node"] is None


def test_current_divider_requires_exact_shared_node_pair():
    """Two resistors that are 'almost parallel' (one ends on a different node) is not a current divider."""
    ckt = Circuit("near_parallel_current_divider")
    ckt.add(i_comp("I1", "1 A", "1", "0"))
    ckt.add(r_comp("R1", "1 kohm", "1", "0"))
    ckt.add(r_comp("R2", "1 kohm", "1", "extra"))
    ckt.add(r_comp("R3", "1 kohm", "extra", "0"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.CURRENT_DIVIDER not in topos


def test_current_divider_rejects_voltage_source():
    """A voltage source feeding two parallel resistors is not a current divider."""
    ckt = Circuit("v_not_current_divider")
    ckt.add(v_comp("V1", "5 V", "1", "0"))
    ckt.add(r_comp("R1", "1 kohm", "1", "0"))
    ckt.add(r_comp("R2", "1 kohm", "1", "0"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.CURRENT_DIVIDER not in topos


def test_current_divider_disconnected_source_not_recognized():
    ckt = Circuit("i_disconnected")
    ckt.add(i_comp("I1", "1 A", "a", "b"))
    ckt.add(r_comp("R1", "1 kohm", "a", "b"))
    ckt.add(r_comp("R2", "1 kohm", "x", "y"))
    ckt.add(r_comp("R3", "1 kohm", "x", "y"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.CURRENT_DIVIDER not in topos


# -- 10.5 Series / Parallel audit ----------------------------------------------
def test_series_pair_requires_exact_shared_terminal():
    """R1 ends at N1, R2 starts at N2 != N1 -> not series."""
    ckt = Circuit("no_shared_terminal")
    ckt.add(v_comp("V1", "5 V", "a", "0"))
    ckt.add(r_comp("R1", "1 kohm", "a", "n1"))
    ckt.add(r_comp("R2", "1 kohm", "n2", "0"))
    ckt.add(r_comp("R5", "1 kohm", "n1", "n2"))
    graph = CircuitGraph(ckt)
    pairs = graph.get_series_pairs()
    assert ("R1", "R2") not in pairs and ("R2", "R1") not in pairs


def test_parallel_requires_exact_same_two_nodes():
    ckt = Circuit("parallel_exactness")
    ckt.add(r_comp("R1", "1 kohm", "A", "B"))
    ckt.add(r_comp("R2", "1 kohm", "A", "B"))
    ckt.add(r_comp("R3", "1 kohm", "B", "C"))
    graph = CircuitGraph(ckt)
    groups = graph.get_parallel_groups()
    assert ("R1", "R2") in groups
    assert not any("R3" in g for g in groups)


def test_parallel_order_independent():
    """R1: A-B, R2: B-A must still be recognized as parallel (order-independent)."""
    ckt = Circuit("parallel_reversed_pins")
    ckt.add(r_comp("R1", "1 kohm", "A", "B"))
    ckt.add(r_comp("R2", "1 kohm", "B", "A"))
    graph = CircuitGraph(ckt)
    groups = graph.get_parallel_groups()
    assert ("R1", "R2") in groups


def test_series_parallel_reduction_preserves_boundary_terminals():
    """A mixed series-parallel network must reduce to a single equivalent resistor
    without eliminating the two external (source-connected) boundary terminals."""
    ckt = Circuit("mixed_series_parallel")
    ckt.add(v_comp("V1", "10 V", "in", "0"))
    ckt.add(r_comp("R1", "1 kohm", "in", "mid"))
    ckt.add(r_comp("R2", "1 kohm", "mid", "0"))
    ckt.add(r_comp("R3", "1 kohm", "mid", "0"))
    graph = CircuitGraph(ckt)
    assert graph.is_resistor_network_reducible() is True
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.SERIES_PARALLEL_MIXED in topos


def test_nested_series_parallel_reducible():
    ckt = Circuit("nested_sp")
    ckt.add(v_comp("V1", "10 V", "in", "0"))
    ckt.add(r_comp("R1", "1 kohm", "in", "a"))
    ckt.add(r_comp("R2", "1 kohm", "a", "b"))
    ckt.add(r_comp("R3", "1 kohm", "a", "b"))
    ckt.add(r_comp("R4", "1 kohm", "b", "0"))
    graph = CircuitGraph(ckt)
    assert graph.is_resistor_network_reducible() is True


def test_bridge_shaped_network_is_non_reducible_not_series_parallel():
    """A network visually resembling series-parallel but structurally a bridge
    must be classified NON_REDUCIBLE_RESISTIVE, never as reducible."""
    ckt = Circuit("visually_sp_but_bridge")
    ckt.add(v_comp("V1", "10 V", "top", "bot"))
    ckt.add(r_comp("R1", "1 kohm", "top", "left"))
    ckt.add(r_comp("R2", "1 kohm", "top", "right"))
    ckt.add(r_comp("R3", "1 kohm", "left", "bot"))
    ckt.add(r_comp("R4", "1 kohm", "right", "bot"))
    ckt.add(r_comp("R5", "1 kohm", "left", "right"))
    graph = CircuitGraph(ckt)
    assert graph.is_resistor_network_reducible() is False
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.NON_REDUCIBLE_RESISTIVE in topos
    assert TopologyType.SERIES_PARALLEL_REDUCIBLE not in topos


# -- 10.6 Bridge hardening: matched_source_pair / matched_source_ref -----------
def test_bridge_stores_explicit_matched_source_metadata():
    ckt = Circuit("bridge_explicit_source")
    ckt.add(v_comp("V1", "10 V", "top", "bot"))
    ckt.add(r_comp("R1", "1 kohm", "top", "left"))
    ckt.add(r_comp("R2", "1 kohm", "top", "right"))
    ckt.add(r_comp("R3", "1 kohm", "left", "bot"))
    ckt.add(r_comp("R4", "1 kohm", "right", "bot"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    match = next(m for m in plan.recognized_topologies if m.topology == TopologyType.RESISTIVE_BRIDGE)
    assert match.metadata["matched_source_ref"] == "V1"
    assert set(match.metadata["matched_source_pair"]) == {"top", "bot"}


def test_bridge_4r_source_on_arm_not_bridge():
    ckt = Circuit("bridge_4r_arm_source")
    ckt.add(v_comp("V1", "10 V", "A", "C"))
    ckt.add(r_comp("R1", "1 kohm", "A", "C"))
    ckt.add(r_comp("R2", "1 kohm", "A", "D"))
    ckt.add(r_comp("R3", "1 kohm", "B", "C"))
    ckt.add(r_comp("R4", "1 kohm", "B", "D"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.RESISTIVE_BRIDGE not in topos


def test_bridge_4r_no_source_not_bridge():
    ckt = Circuit("bridge_4r_no_source")
    ckt.add(r_comp("R1", "1 kohm", "A", "C"))
    ckt.add(r_comp("R2", "1 kohm", "A", "D"))
    ckt.add(r_comp("R3", "1 kohm", "B", "C"))
    ckt.add(r_comp("R4", "1 kohm", "B", "D"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.RESISTIVE_BRIDGE not in topos


def test_bridge_4r_degenerate_topology_not_bridge():
    """4 resistors with only 3 distinct nodes (degenerate) must not be a bridge."""
    ckt = Circuit("bridge_4r_degenerate")
    ckt.add(v_comp("V1", "10 V", "A", "B"))
    ckt.add(r_comp("R1", "1 kohm", "A", "B"))
    ckt.add(r_comp("R2", "1 kohm", "A", "B"))
    ckt.add(r_comp("R3", "1 kohm", "A", "C"))
    ckt.add(r_comp("R4", "1 kohm", "B", "C"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.RESISTIVE_BRIDGE not in topos


def test_bridge_5r_valid():
    ckt = Circuit("bridge_5r_valid")
    ckt.add(v_comp("V1", "10 V", "A", "B"))
    ckt.add(r_comp("R1", "1 kohm", "A", "C"))
    ckt.add(r_comp("R2", "1 kohm", "A", "D"))
    ckt.add(r_comp("R3", "1 kohm", "B", "C"))
    ckt.add(r_comp("R4", "1 kohm", "B", "D"))
    ckt.add(r_comp("R5", "1 kohm", "C", "D"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.RESISTIVE_BRIDGE in topos


def test_bridge_5r_wrong_diagonal_not_bridge():
    """5th resistor placed as a duplicate arm instead of the opposite diagonal -> not a bridge."""
    ckt = Circuit("bridge_5r_wrong_diag")
    ckt.add(v_comp("V1", "10 V", "A", "B"))
    ckt.add(r_comp("R1", "1 kohm", "A", "C"))
    ckt.add(r_comp("R2", "1 kohm", "A", "D"))
    ckt.add(r_comp("R3", "1 kohm", "B", "C"))
    ckt.add(r_comp("R4", "1 kohm", "B", "D"))
    ckt.add(r_comp("R5", "1 kohm", "A", "C"))  # duplicate arm, not the C-D diagonal
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.RESISTIVE_BRIDGE not in topos


def test_bridge_5r_source_incorrect_not_bridge():
    """5R with the source across an arm, not the excitation diagonal -> not a bridge."""
    ckt = Circuit("bridge_5r_source_incorrect")
    ckt.add(v_comp("V1", "10 V", "A", "C"))  # on an arm, not a diagonal
    ckt.add(r_comp("R1", "1 kohm", "A", "C"))
    ckt.add(r_comp("R2", "1 kohm", "A", "D"))
    ckt.add(r_comp("R3", "1 kohm", "B", "C"))
    ckt.add(r_comp("R4", "1 kohm", "B", "D"))
    ckt.add(r_comp("R5", "1 kohm", "C", "D"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    topos = {m.topology for m in plan.recognized_topologies}
    assert TopologyType.RESISTIVE_BRIDGE not in topos


def test_bridge_5r_two_sources_one_valid_one_invalid():
    """One source on a valid diagonal, another on an arm: bridge must still be
    recognized deterministically using the valid excitation, ref chosen by
    sorted order (not insertion order)."""
    ckt = Circuit("bridge_5r_two_sources")
    ckt.add(v_comp("V2", "1 V", "A", "C"))  # invalid: on an arm
    ckt.add(v_comp("V1", "10 V", "A", "B"))  # valid: on excitation diagonal
    ckt.add(r_comp("R1", "1 kohm", "A", "C"))
    ckt.add(r_comp("R2", "1 kohm", "A", "D"))
    ckt.add(r_comp("R3", "1 kohm", "B", "C"))
    ckt.add(r_comp("R4", "1 kohm", "B", "D"))
    ckt.add(r_comp("R5", "1 kohm", "C", "D"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    match = next(m for m in plan.recognized_topologies if m.topology == TopologyType.RESISTIVE_BRIDGE)
    assert match.metadata["matched_source_ref"] == "V1"


def test_bridge_5r_component_insertion_order_invariant():
    def build(order):
        ckt = Circuit("bridge_5r_order")
        parts = {
            "V1": v_comp("V1", "10 V", "A", "B"),
            "R1": r_comp("R1", "1 kohm", "A", "C"),
            "R2": r_comp("R2", "1 kohm", "A", "D"),
            "R3": r_comp("R3", "1 kohm", "B", "C"),
            "R4": r_comp("R4", "1 kohm", "B", "D"),
            "R5": r_comp("R5", "1 kohm", "C", "D"),
        }
        for key in order:
            ckt.add(parts[key])
        return ckt

    plan_fwd = StructuralCircuitAnalyzer().analyze(build(["V1", "R1", "R2", "R3", "R4", "R5"]))
    plan_rev = StructuralCircuitAnalyzer().analyze(build(["R5", "R4", "R3", "R2", "R1", "V1"]))
    match_fwd = next(m for m in plan_fwd.recognized_topologies if m.topology == TopologyType.RESISTIVE_BRIDGE)
    match_rev = next(m for m in plan_rev.recognized_topologies if m.topology == TopologyType.RESISTIVE_BRIDGE)
    assert match_fwd.metadata["matched_source_ref"] == match_rev.metadata["matched_source_ref"]
    assert match_fwd.elements == match_rev.elements


def test_bridge_5r_source_insertion_order_invariant():
    def build(order):
        ckt = Circuit("bridge_5r_src_order")
        parts = {
            "V1": v_comp("V1", "10 V", "A", "B"),
            "V2": v_comp("V2", "1 V", "A", "C"),
            "R1": r_comp("R1", "1 kohm", "A", "C"),
            "R2": r_comp("R2", "1 kohm", "A", "D"),
            "R3": r_comp("R3", "1 kohm", "B", "C"),
            "R4": r_comp("R4", "1 kohm", "B", "D"),
            "R5": r_comp("R5", "1 kohm", "C", "D"),
        }
        for key in order:
            ckt.add(parts[key])
        return ckt

    plan_a = StructuralCircuitAnalyzer().analyze(build(["V1", "V2", "R1", "R2", "R3", "R4", "R5"]))
    plan_b = StructuralCircuitAnalyzer().analyze(build(["V2", "V1", "R5", "R4", "R3", "R2", "R1"]))
    match_a = next(m for m in plan_a.recognized_topologies if m.topology == TopologyType.RESISTIVE_BRIDGE)
    match_b = next(m for m in plan_b.recognized_topologies if m.topology == TopologyType.RESISTIVE_BRIDGE)
    assert match_a.metadata["matched_source_ref"] == match_b.metadata["matched_source_ref"] == "V1"


# -- 10.7 Thévenin/Norton port validation --------------------------------------
def test_thevenin_port_self_loop_rejected():
    ckt = Circuit("thev_self_loop")
    ckt.add(v_comp("V1", "10 V", "1", "0"))
    ckt.add(r_comp("R1", "1 kohm", "1", "0"))
    plan = StructuralCircuitAnalyzer().analyze(ckt, target_terminals=("1", "1"))
    assert plan.applicable_analyses[AnalysisType.THEVENIN.value] == ApplicabilityStatus.UNKNOWN.value
    assert plan.applicable_analyses[AnalysisType.NORTON.value] == ApplicabilityStatus.UNKNOWN.value


def test_thevenin_port_nonexistent_terminal_a_rejected():
    ckt = Circuit("thev_bad_t1")
    ckt.add(v_comp("V1", "10 V", "1", "0"))
    ckt.add(r_comp("R1", "1 kohm", "1", "0"))
    plan = StructuralCircuitAnalyzer().analyze(ckt, target_terminals=("nope", "0"))
    assert plan.applicable_analyses[AnalysisType.THEVENIN.value] == ApplicabilityStatus.UNKNOWN.value


def test_thevenin_port_nonexistent_terminal_b_rejected():
    ckt = Circuit("thev_bad_t2")
    ckt.add(v_comp("V1", "10 V", "1", "0"))
    ckt.add(r_comp("R1", "1 kohm", "1", "0"))
    plan = StructuralCircuitAnalyzer().analyze(ckt, target_terminals=("1", "nope"))
    assert plan.applicable_analyses[AnalysisType.THEVENIN.value] == ApplicabilityStatus.UNKNOWN.value


def test_thevenin_port_disconnected_terminals_rejected():
    """When the requested port straddles two disconnected subgraphs, the whole
    circuit is structurally disconnected and the analyzer abstains entirely
    (never claiming Thevenin/Norton applicability on an unprovable port)."""
    ckt = Circuit("thev_disconnected_port")
    ckt.add(v_comp("V1", "10 V", "1", "0"))
    ckt.add(r_comp("R1", "1 kohm", "1", "0"))
    ckt.add(r_comp("R2", "1 kohm", "x", "y"))
    plan = StructuralCircuitAnalyzer().analyze(ckt, target_terminals=("1", "x"))
    assert plan.confidence == ConfidenceLevel.ABSTAINED
    assert plan.applicable_analyses[AnalysisType.THEVENIN.value] == ApplicabilityStatus.NOT_APPLICABLE.value
    assert plan.applicable_analyses[AnalysisType.NORTON.value] == ApplicabilityStatus.NOT_APPLICABLE.value


def test_thevenin_not_applicable_when_reactive_elements_present():
    ckt = Circuit("thev_reactive")
    ckt.add(v_comp("V1", "10 V", "1", "0"))
    ckt.add(r_comp("R1", "1 kohm", "1", "2"))
    ckt.add(c_comp("C1", "1 uF", "2", "0"))
    plan = StructuralCircuitAnalyzer().analyze(ckt, target_terminals=("2", "0"))
    assert plan.applicable_analyses[AnalysisType.THEVENIN.value] == ApplicabilityStatus.NOT_APPLICABLE.value


def test_thevenin_valid_port_applicable():
    ckt = Circuit("thev_valid")
    ckt.add(v_comp("V1", "10 V", "1", "2"))
    ckt.add(r_comp("R1", "1 kohm", "1", "2"))
    plan = StructuralCircuitAnalyzer().analyze(ckt, target_terminals=("1", "2"))
    assert plan.applicable_analyses[AnalysisType.THEVENIN.value] == ApplicabilityStatus.APPLICABLE.value
    assert plan.applicable_analyses[AnalysisType.NORTON.value] == ApplicabilityStatus.APPLICABLE.value


# -- 10.8 KCL/KVL foundations ---------------------------------------------------
def test_kvl_single_loop_mu_equals_one():
    ckt = Circuit("single_loop")
    ckt.add(v_comp("V1", "10 V", "1", "0"))
    ckt.add(r_comp("R1", "1 kohm", "1", "0"))
    graph = CircuitGraph(ckt)
    loops = graph.get_fundamental_loops()
    assert len(loops) == 1


def test_kvl_two_loops_mu_equals_two():
    ckt = Circuit("two_loops")
    ckt.add(v_comp("V1", "10 V", "1", "0"))
    ckt.add(r_comp("R1", "1 kohm", "1", "2"))
    ckt.add(r_comp("R2", "1 kohm", "2", "0"))
    ckt.add(r_comp("R3", "1 kohm", "2", "0"))
    graph = CircuitGraph(ckt)
    loops = graph.get_fundamental_loops()
    assert len(loops) == 2


def test_kvl_disconnected_components_mu_matches_formula():
    """Two disconnected single-loop subgraphs: E=4, V=4, C=2 -> mu = 4-4+2 = 2."""
    ckt = Circuit("disconnected_two_loops")
    ckt.add(v_comp("V1", "10 V", "a", "b"))
    ckt.add(r_comp("R1", "1 kohm", "a", "b"))
    ckt.add(v_comp("V2", "5 V", "x", "y"))
    ckt.add(r_comp("R2", "1 kohm", "x", "y"))
    graph = CircuitGraph(ckt)
    loops = graph.get_fundamental_loops()
    e = len(graph.branches)
    v = len(graph.nodes)
    c = len(graph.get_connected_components())
    assert len(loops) == e - v + c == 2


def test_kvl_loops_reference_only_real_branches():
    ckt = Circuit("real_branches_only")
    ckt.add(v_comp("V1", "10 V", "1", "2"))
    ckt.add(r_comp("R1", "1 kohm", "1", "2"))
    ckt.add(r_comp("R2", "1 kohm", "1", "2"))
    graph = CircuitGraph(ckt)
    loops = graph.get_fundamental_loops()
    all_refs = {b.ref for b in graph.branches}
    for loop in loops:
        for ref in loop:
            assert ref in all_refs


def test_kvl_deterministic_across_repeated_calls():
    ckt = Circuit("kvl_determinism")
    ckt.add(v_comp("V1", "10 V", "top", "bot"))
    ckt.add(r_comp("R1", "1 kohm", "top", "left"))
    ckt.add(r_comp("R2", "1 kohm", "top", "right"))
    ckt.add(r_comp("R3", "1 kohm", "left", "bot"))
    ckt.add(r_comp("R4", "1 kohm", "right", "bot"))
    graph = CircuitGraph(ckt)
    assert graph.get_fundamental_loops() == graph.get_fundamental_loops()


def test_kcl_nodes_exclude_reference_and_require_degree_ge_2():
    ckt = Circuit("kcl_basic")
    ckt.add(v_comp("V1", "10 V", "1", "0"))
    ckt.add(r_comp("R1", "1 kohm", "1", "2"))
    ckt.add(r_comp("R2", "1 kohm", "2", "0"))
    graph = CircuitGraph(ckt)
    kcl = graph.get_kcl_nodes()
    assert "0" not in kcl  # reference node excluded
    assert "2" in kcl  # degree-2 node included


# -- 10.9 Provenance digest correctness -----------------------------------------
def test_provenance_digest_differs_for_materially_different_circuits():
    ckt_a = Circuit("digest_a")
    ckt_a.add(v_comp("V1", "10 V", "1", "0"))
    ckt_a.add(r_comp("R1", "1 kohm", "1", "0"))

    ckt_b = Circuit("digest_b")
    ckt_b.add(v_comp("V1", "10 V", "1", "0"))
    ckt_b.add(r_comp("R1", "2 kohm", "1", "0"))  # different value

    plan_a = StructuralCircuitAnalyzer().analyze(ckt_a, at="2026-01-01T00:00:00Z")
    plan_b = StructuralCircuitAnalyzer().analyze(ckt_b, at="2026-01-01T00:00:00Z")
    assert plan_a.provenance["digest"] != plan_b.provenance["digest"]


def test_provenance_digest_stable_under_component_insertion_order():
    ckt_fwd = Circuit("digest_order")
    ckt_fwd.add(v_comp("V1", "10 V", "1", "0"))
    ckt_fwd.add(r_comp("R1", "1 kohm", "1", "2"))
    ckt_fwd.add(r_comp("R2", "1 kohm", "2", "0"))

    ckt_rev = Circuit("digest_order")
    ckt_rev.add(r_comp("R2", "1 kohm", "2", "0"))
    ckt_rev.add(r_comp("R1", "1 kohm", "1", "2"))
    ckt_rev.add(v_comp("V1", "10 V", "1", "0"))

    plan_fwd = StructuralCircuitAnalyzer().analyze(ckt_fwd, at="2026-01-01T00:00:00Z")
    plan_rev = StructuralCircuitAnalyzer().analyze(ckt_rev, at="2026-01-01T00:00:00Z")
    assert plan_fwd.provenance["digest"] == plan_rev.provenance["digest"]


def test_provenance_digest_stable_under_metadata_dict_key_order():
    def build(meta):
        ckt = Circuit("digest_meta_order")
        ckt.add(v_comp("V1", "10 V", "1", "0"))
        ckt.add(r_comp("R1", "1 kohm", "1", "0", metadata=meta))
        return ckt

    from collections import OrderedDict
    meta_fwd = OrderedDict([("a", 1), ("b", 2)])
    meta_rev = OrderedDict([("b", 2), ("a", 1)])

    plan_fwd = StructuralCircuitAnalyzer().analyze(build(meta_fwd), at="2026-01-01T00:00:00Z")
    plan_rev = StructuralCircuitAnalyzer().analyze(build(meta_rev), at="2026-01-01T00:00:00Z")
    assert plan_fwd.provenance["digest"] == plan_rev.provenance["digest"]


def test_provenance_digest_affected_by_target_terminals():
    ckt = Circuit("digest_target_terminals")
    ckt.add(v_comp("V1", "10 V", "1", "2"))
    ckt.add(r_comp("R1", "1 kohm", "1", "2"))

    plan_none = StructuralCircuitAnalyzer().analyze(ckt, at="2026-01-01T00:00:00Z")
    plan_port = StructuralCircuitAnalyzer().analyze(ckt, target_terminals=("1", "2"), at="2026-01-01T00:00:00Z")
    assert plan_none.provenance["digest"] != plan_port.provenance["digest"]


def test_provenance_digest_affected_by_classification_context():
    """Same components, different topological arrangement -> different classification -> different digest."""
    ckt_divider = Circuit("digest_class_a")
    ckt_divider.add(v_comp("V1", "10 V", "in", "0"))
    ckt_divider.add(r_comp("R1", "1 kohm", "in", "mid"))
    ckt_divider.add(r_comp("R2", "1 kohm", "mid", "0"))

    ckt_parallel = Circuit("digest_class_b")
    ckt_parallel.add(v_comp("V1", "10 V", "in", "0"))
    ckt_parallel.add(r_comp("R1", "1 kohm", "in", "0"))
    ckt_parallel.add(r_comp("R2", "1 kohm", "in", "0"))

    plan_divider = StructuralCircuitAnalyzer().analyze(ckt_divider, at="2026-01-01T00:00:00Z")
    plan_parallel = StructuralCircuitAnalyzer().analyze(ckt_parallel, at="2026-01-01T00:00:00Z")
    assert plan_divider.provenance["digest"] != plan_parallel.provenance["digest"]


def test_provenance_digest_excludes_timestamp():
    ckt = Circuit("digest_no_timestamp_dependency")
    ckt.add(v_comp("V1", "10 V", "1", "0"))
    ckt.add(r_comp("R1", "1 kohm", "1", "0"))

    plan_t1 = StructuralCircuitAnalyzer().analyze(ckt, at="2020-01-01T00:00:00Z")
    plan_t2 = StructuralCircuitAnalyzer().analyze(ckt, at="2030-06-15T12:00:00Z")
    assert plan_t1.provenance["digest"] == plan_t2.provenance["digest"]
    assert plan_t1.provenance["timestamp"] != plan_t2.provenance["timestamp"]


def test_abstained_provenance_reflects_structural_content_not_just_name_reason():
    """Two different abstained (disconnected) circuits with the same name and
    the same abstention reason must NOT collide on digest, because the digest
    must incorporate real structural content, not just name+reason."""
    ckt_a = Circuit("same_name")
    ckt_a.add(r_comp("R1", "1 kohm", "a", "b"))
    ckt_a.add(r_comp("R2", "1 kohm", "x", "y"))

    ckt_b = Circuit("same_name")
    ckt_b.add(r_comp("R1", "2 kohm", "a", "b"))
    ckt_b.add(r_comp("R2", "2 kohm", "x", "y"))

    plan_a = StructuralCircuitAnalyzer().analyze(ckt_a, at="2026-01-01T00:00:00Z")
    plan_b = StructuralCircuitAnalyzer().analyze(ckt_b, at="2026-01-01T00:00:00Z")
    assert plan_a.confidence == ConfidenceLevel.ABSTAINED
    assert plan_b.confidence == ConfidenceLevel.ABSTAINED
    assert plan_a.provenance["digest"] != plan_b.provenance["digest"]


# -- 10.10 Determinism, serialization, rule registry ----------------------------
def test_full_plan_serialization_deterministic_across_permutations():
    def build(order):
        ckt = Circuit("full_determinism")
        parts = {
            "V1": v_comp("V1", "10 V", "in", "0"),
            "R1": r_comp("R1", "1 kohm", "in", "mid"),
            "R2": r_comp("R2", "1 kohm", "mid", "0"),
        }
        for key in order:
            ckt.add(parts[key])
        return ckt

    plan_a = StructuralCircuitAnalyzer().analyze(build(["V1", "R1", "R2"]), at="2026-01-01T00:00:00Z")
    plan_b = StructuralCircuitAnalyzer().analyze(build(["R2", "R1", "V1"]), at="2026-01-01T00:00:00Z")
    assert plan_a.to_json() == plan_b.to_json()


def test_rule_registry_order_is_stable_across_constructions():
    from academic_core.domain.engineering.structural.rules import RuleRegistry

    names_a = [r.rule_name for r in RuleRegistry(default_rules=True).rules]
    names_b = [r.rule_name for r in RuleRegistry(default_rules=True).rules]
    assert names_a == names_b
    assert len(names_a) == len(set(names_a))  # no duplicate rule names


# -- 10.11 Abstention & Security --------------------------------------------------
def test_abstains_on_ambiguous_topology_with_invalid_voltage_short():
    ckt = Circuit("short_v")
    ckt.add(v_comp("V1", "10 V", "1", "1"))  # self-loop short
    ckt.add(r_comp("R1", "1 kohm", "1", "0"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    assert plan.confidence == ConfidenceLevel.ABSTAINED


def test_abstains_on_unsupported_component():
    ckt = Circuit("unsupported")
    ckt.add(v_comp("V1", "10 V", "1", "0"))
    ckt.add(Component("D1", "D", None, {"A": "1", "K": "0"}))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    assert plan.confidence == ConfidenceLevel.ABSTAINED


def test_abstains_on_empty_circuit():
    plan = StructuralCircuitAnalyzer().analyze(Circuit("nothing"))
    assert plan.confidence == ConfidenceLevel.ABSTAINED
    assert plan.recognized_topologies == []


def test_security_no_dangerous_calls_in_structural_domain():
    """Static scan of the structural domain source for prohibited operations
    (eval/exec/subprocess/shell/network/arbitrary filesystem I/O)."""
    import pathlib

    banned = ["eval(", "exec(", "subprocess", "os.system", "shell=True", "requests", "urllib", "open(", "Path("]
    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "academic_core" / "domain" / "engineering" / "structural"
    offenders = []
    for path in root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in banned:
            if token in text:
                offenders.append((path.name, token))
    assert offenders == [], f"prohibited constructs found: {offenders}"


def test_multiple_sources_duplicate_type_does_not_break_analysis():
    ckt = Circuit("multi_sources")
    ckt.add(v_comp("V1", "10 V", "1", "0"))
    ckt.add(v_comp("V2", "5 V", "2", "0"))
    ckt.add(r_comp("R1", "1 kohm", "1", "2"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    assert plan.confidence in (ConfidenceLevel.DETERMINISTIC, ConfidenceLevel.ABSTAINED)


# -- 10.12 Property / invariant tests --------------------------------------------
def test_property_no_invented_nodes_in_recognized_metadata():
    ckt = Circuit("no_invented_nodes")
    ckt.add(v_comp("V1", "10 V", "in", "0"))
    ckt.add(r_comp("R1", "1 kohm", "in", "mid"))
    ckt.add(r_comp("R2", "1 kohm", "mid", "0"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    graph = CircuitGraph(ckt)
    for m in plan.recognized_topologies:
        for key in ("tap_nodes", "bridge_nodes"):
            if key in m.metadata:
                for node in m.metadata[key]:
                    assert node in graph.nodes


def test_property_no_invented_components_in_matches():
    ckt = Circuit("no_invented_components")
    ckt.add(v_comp("V1", "10 V", "in", "0"))
    ckt.add(r_comp("R1", "1 kohm", "in", "mid"))
    ckt.add(r_comp("R2", "1 kohm", "mid", "0"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)
    valid_refs = set(graph.components.keys()) if (graph := CircuitGraph(ckt)) else set()
    for m in plan.recognized_topologies:
        for ref in m.elements:
            assert ref in valid_refs



