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
def r_comp(ref: str, value: str, n1: str, n2: str) -> Component:
    return Component(ref, "R", parse_quantity(value), {"1": n1, "2": n2})


def c_comp(ref: str, value: str, n1: str, n2: str) -> Component:
    return Component(ref, "C", parse_quantity(value), {"1": n1, "2": n2})


def l_comp(ref: str, value: str, n1: str, n2: str) -> Component:
    return Component(ref, "L", parse_quantity(value), {"1": n1, "2": n2})


def v_comp(ref: str, value: str, np: str, nm: str, params: dict | None = None) -> Component:
    return Component(ref, "V", parse_quantity(value), {"+": np, "-": nm}, parameters=params or {})


def i_comp(ref: str, value: str, np: str, nm: str) -> Component:
    return Component(ref, "I", parse_quantity(value), {"+": np, "-": nm})


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
    """RLC with DC excitation should have primary TRANSIENT and AC applicable."""
    ckt = Circuit("rlc_ckt")
    ckt.add(v_comp("V1", "10 V", "in", "0"))
    ckt.add(r_comp("R1", "50 ohm", "in", "1"))
    ckt.add(l_comp("L1", "1 mH", "1", "out"))
    ckt.add(c_comp("C1", "100 nF", "out", "0"))
    plan = StructuralCircuitAnalyzer().analyze(ckt)

    assert plan.classification == TopologyType.RLC.value
    assert plan.primary_analysis == AnalysisType.TRANSIENT
    assert plan.applicable_analyses[AnalysisType.TRANSIENT.value] == ApplicabilityStatus.PRIMARY.value
    assert plan.applicable_analyses[AnalysisType.AC.value] == ApplicabilityStatus.APPLICABLE.value


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
    """Verify that canonical F6 model only supports R, C, L, V, I, D, Q (no dependent sources)."""
    from academic_core.domain.engineering.circuit import COMPONENT_PINS, CircuitError

    # Independent sources V and I are supported
    assert "V" in COMPONENT_PINS
    assert "I" in COMPONENT_PINS

    # Dependent source letters (E, G, F, H) are not in canonical F6
    for dep_type in ("E", "G", "F", "H"):
        assert dep_type not in COMPONENT_PINS
        with pytest.raises(CircuitError):
            Component(f"{dep_type}1", dep_type, None, {"1": "in", "2": "out"})

