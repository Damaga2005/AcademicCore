"""Analysis classification and execution planning (Phase 7-B8).

Generates structured, deterministic analysis plans, identifying applicable analyses
(KCL, KVL, Ohm's law, Power, Thévenin, Norton, DC, Transient, AC) and enforcing
the mandatory ambiguity and abstention protocol.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from academic_core.domain.engineering.structural.elements import CircuitGraph
from academic_core.domain.engineering.structural.rules import RecognitionMatch
from academic_core.domain.engineering.structural.types import (
    AnalysisType,
    ApplicabilityStatus,
    ConfidenceLevel,
    TopologyType,
)

PLAN_ENGINE_VERSION = "f7b8-planner/1.0"


@dataclass(frozen=True)
class AnalysisStep:
    """An individual step in the deterministic analysis plan."""

    step_number: int
    title: str
    description: str
    equation_reference: str | None = None


@dataclass
class AnalysisPlan:
    """A formal, structured, deterministic electrical analysis plan."""

    circuit_id: str
    classification: str
    recognized_topologies: list[RecognitionMatch]
    primary_analysis: AnalysisType | None
    applicable_analyses: dict[str, str]  # AnalysisType.value -> ApplicabilityStatus.value
    kcl_nodes: list[str]
    kvl_loops: list[list[str]]
    prerequisites: list[str]
    steps: list[AnalysisStep]
    confidence: ConfidenceLevel
    warnings: list[str]
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert plan to deterministic dictionary representation."""
        return {
            "circuit_id": self.circuit_id,
            "classification": self.classification,
            "recognized_topologies": [
                {
                    "topology": m.topology.value,
                    "elements": list(m.elements),
                    "reason": m.reason,
                    "metadata": m.metadata,
                }
                for m in self.recognized_topologies
            ],
            "primary_analysis": self.primary_analysis.value if self.primary_analysis else None,
            "applicable_analyses": dict(self.applicable_analyses),
            "kcl_nodes": list(self.kcl_nodes),
            "kvl_loops": [list(loop) for loop in self.kvl_loops],
            "prerequisites": list(self.prerequisites),
            "steps": [asdict(s) for s in self.steps],
            "confidence": self.confidence.value,
            "warnings": list(self.warnings),
            "provenance": dict(self.provenance),
        }

    def to_json(self, indent: int = 2) -> str:
        """Deterministic JSON serialization."""
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


class AnalysisClassifier:
    """Evaluates applicability of analytical methods and synthesizes an AnalysisPlan."""

    def classify(
        self,
        graph: CircuitGraph,
        matches: list[RecognitionMatch],
        target_terminals: tuple[str, str] | None = None,
        at: str | None = None,
    ) -> AnalysisPlan:
        warnings: list[str] = []
        prerequisites: list[str] = []
        applicable: dict[str, str] = {a.value: ApplicabilityStatus.NOT_APPLICABLE.value for a in AnalysisType}

        matched_topos = {m.topology for m in matches}

        # 1. Validation & Abstention checks
        if not graph.components:
            warnings.append("empty circuit")
            return self._build_abstained_plan(
                graph, matches, warnings, "empty circuit", at
            )

        # Check unsupported components (e.g. semiconductor placeholders D, Q)
        unsupported = [c.ref for c in graph.components.values() if c.type in ("D", "Q")]
        if unsupported:
            warnings.append(f"unsupported active components for linear analysis: {sorted(unsupported)}")
            return self._build_abstained_plan(
                graph, matches, warnings, "unsupported components", at
            )

        # Disconnected check
        if not graph.is_connected:
            comp_count = len(graph.get_connected_components())
            warnings.append(f"circuit is disconnected into {comp_count} isolated subgraphs")
            return self._build_abstained_plan(
                graph, matches, warnings, "disconnected circuit", at
            )

        # Floating pins/nodes check
        if graph.floating_nodes:
            warnings.append(f"floating node(s) detected: {graph.floating_nodes}")

        # Missing GND check
        ref_node = graph.reference_node
        if ref_node is None:
            warnings.append("no reference node (0 or GND) identified in circuit")

        # Invalid short circuit check
        if graph.has_invalid_voltage_short():
            warnings.append("invalid ideal voltage source short circuit detected")
            return self._build_abstained_plan(
                graph, matches, warnings, "invalid short circuit", at
            )

        # 2. General Classification
        has_r = any(c.type == "R" for c in graph.components.values())
        has_c = any(c.type == "C" for c in graph.components.values())
        has_l = any(c.type == "L" for c in graph.components.values())
        has_sources = any(c.type in ("V", "I") for c in graph.components.values())

        classification: str
        if TopologyType.RLC in matched_topos:
            classification = TopologyType.RLC.value
        elif TopologyType.RC in matched_topos:
            classification = TopologyType.RC.value
        elif TopologyType.RL in matched_topos:
            classification = TopologyType.RL.value
        elif (has_c or has_l) and has_r:
            classification = TopologyType.ENERGY_STORAGE.value
        elif has_r and not has_c and not has_l:
            classification = TopologyType.RESISTIVE.value
        elif not has_r and not has_c and not has_l:
            classification = TopologyType.UNKNOWN_TOPOLOGY.value
        else:
            classification = TopologyType.MIXED.value

        # 3. KCL & KVL Applicability
        kcl_nodes = graph.get_kcl_nodes()
        kvl_loops = graph.get_fundamental_loops()

        if kcl_nodes:
            applicable[AnalysisType.KCL.value] = ApplicabilityStatus.APPLICABLE.value
        if kvl_loops:
            applicable[AnalysisType.KVL.value] = ApplicabilityStatus.APPLICABLE.value
        if has_r:
            applicable[AnalysisType.OHMS_LAW.value] = ApplicabilityStatus.APPLICABLE.value

        # 4. Divider Applicability
        if TopologyType.VOLTAGE_DIVIDER in matched_topos:
            applicable[AnalysisType.VOLTAGE_DIVIDER.value] = ApplicabilityStatus.APPLICABLE.value
        if TopologyType.CURRENT_DIVIDER in matched_topos:
            applicable[AnalysisType.CURRENT_DIVIDER.value] = ApplicabilityStatus.APPLICABLE.value

        # 5. Power Analysis Applicability
        if (has_r or has_sources) and graph.is_connected:
            applicable[AnalysisType.POWER.value] = ApplicabilityStatus.APPLICABLE.value

        # 6. Thévenin / Norton Applicability
        if has_r and not (has_c or has_l):
            if target_terminals is not None:
                t1, t2 = str(target_terminals[0]).strip(), str(target_terminals[1]).strip()
                if t1 in graph.nodes and t2 in graph.nodes and t1 != t2:
                    applicable[AnalysisType.THEVENIN.value] = ApplicabilityStatus.APPLICABLE.value
                    applicable[AnalysisType.NORTON.value] = ApplicabilityStatus.APPLICABLE.value
                else:
                    applicable[AnalysisType.THEVENIN.value] = ApplicabilityStatus.UNKNOWN.value
                    applicable[AnalysisType.NORTON.value] = ApplicabilityStatus.UNKNOWN.value
                    warnings.append(f"specified target terminals {target_terminals} are not distinct valid nodes")
            else:
                applicable[AnalysisType.THEVENIN.value] = ApplicabilityStatus.NEEDS_TARGET_TERMINALS.value
                applicable[AnalysisType.NORTON.value] = ApplicabilityStatus.NEEDS_TARGET_TERMINALS.value
        else:
            applicable[AnalysisType.THEVENIN.value] = ApplicabilityStatus.NOT_APPLICABLE.value
            applicable[AnalysisType.NORTON.value] = ApplicabilityStatus.NOT_APPLICABLE.value

        # 7. Simulation / Operating Point / Dynamic Analysis
        primary_analysis: AnalysisType | None = None

        # Check excitation: does it have AC parameters in voltage or current sources?
        has_ac_source = False
        for c in graph.components.values():
            if c.type in ("V", "I"):
                params = c.parameters or {}
                if "ac" in params or "AC" in params or (c.value and "ac" in str(c.value).lower()):
                    has_ac_source = True

        if classification == TopologyType.RESISTIVE.value:
            primary_analysis = AnalysisType.DC_OPERATING_POINT
            applicable[AnalysisType.DC_OPERATING_POINT.value] = ApplicabilityStatus.PRIMARY.value
            applicable[AnalysisType.DC_SWEEP.value] = ApplicabilityStatus.APPLICABLE.value
            applicable[AnalysisType.SENSITIVITY.value] = ApplicabilityStatus.APPLICABLE.value
            applicable[AnalysisType.MONTE_CARLO.value] = ApplicabilityStatus.APPLICABLE.value
            applicable[AnalysisType.GUM_UNCERTAINTY.value] = ApplicabilityStatus.APPLICABLE.value
        elif classification in (TopologyType.RC.value, TopologyType.RL.value, TopologyType.RLC.value):
            primary_analysis = AnalysisType.TRANSIENT
            applicable[AnalysisType.TRANSIENT.value] = ApplicabilityStatus.PRIMARY.value
            applicable[AnalysisType.DC_STEADY_STATE.value] = ApplicabilityStatus.APPLICABLE.value
            applicable[AnalysisType.DC_OPERATING_POINT.value] = ApplicabilityStatus.APPLICABLE.value
            prerequisites.append("initial conditions required if non-zero transient initial state requested")
            if has_ac_source or classification == TopologyType.RLC.value:
                applicable[AnalysisType.AC.value] = ApplicabilityStatus.APPLICABLE.value
        else:
            if has_sources:
                primary_analysis = AnalysisType.DC_OPERATING_POINT
                applicable[AnalysisType.DC_OPERATING_POINT.value] = ApplicabilityStatus.PRIMARY.value

        # 8. Confidence determination
        confidence = ConfidenceLevel.DETERMINISTIC
        if warnings:
            confidence = ConfidenceLevel.HIGH

        # 9. Step Generation
        steps = self._generate_steps(classification, matched_topos, ref_node)

        # 10. Provenance
        stamp = at or datetime.now(timezone.utc).isoformat()
        content_hash = hashlib.sha256(
            json.dumps(
                {
                    "circuit": graph.circuit_name,
                    "components": sorted(graph.components.keys()),
                    "classification": classification,
                    "engine": PLAN_ENGINE_VERSION,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()

        provenance = {
            "engine": PLAN_ENGINE_VERSION,
            "timestamp": stamp,
            "digest": content_hash,
            "reference_node": ref_node,
        }

        return AnalysisPlan(
            circuit_id=graph.circuit_name,
            classification=classification,
            recognized_topologies=matches,
            primary_analysis=primary_analysis,
            applicable_analyses=applicable,
            kcl_nodes=kcl_nodes,
            kvl_loops=kvl_loops,
            prerequisites=prerequisites,
            steps=steps,
            confidence=confidence,
            warnings=warnings,
            provenance=provenance,
        )

    def _build_abstained_plan(
        self,
        graph: CircuitGraph,
        matches: list[RecognitionMatch],
        warnings: list[str],
        reason: str,
        at: str | None,
    ) -> AnalysisPlan:
        stamp = at or datetime.now(timezone.utc).isoformat()
        digest = hashlib.sha256(f"abstained:{graph.circuit_name}:{reason}".encode()).hexdigest()
        applicable = {a.value: ApplicabilityStatus.NOT_APPLICABLE.value for a in AnalysisType}

        return AnalysisPlan(
            circuit_id=graph.circuit_name,
            classification=TopologyType.UNKNOWN_TOPOLOGY.value,
            recognized_topologies=matches,
            primary_analysis=None,
            applicable_analyses=applicable,
            kcl_nodes=[],
            kvl_loops=[],
            prerequisites=[],
            steps=[
                AnalysisStep(
                    step_number=1,
                    title="Abstain Analysis",
                    description=f"Automated structural analysis abstained: {reason}.",
                )
            ],
            confidence=ConfidenceLevel.ABSTAINED,
            warnings=warnings,
            provenance={
                "engine": PLAN_ENGINE_VERSION,
                "timestamp": stamp,
                "digest": digest,
                "abstention_reason": reason,
            },
        )

    def _generate_steps(
        self,
        classification: str,
        matched_topos: set[TopologyType],
        ref_node: str | None,
    ) -> list[AnalysisStep]:
        steps: list[AnalysisStep] = []
        step_idx = 1

        ref_str = f"node '{ref_node}'" if ref_node else "GND/datum"
        steps.append(
            AnalysisStep(
                step_number=step_idx,
                title="Identify Reference Node",
                description=f"Select and anchor reference node {ref_str} as datum (0 V).",
            )
        )
        step_idx += 1

        if TopologyType.VOLTAGE_DIVIDER in matched_topos:
            steps.append(
                AnalysisStep(
                    step_number=step_idx,
                    title="Identify Voltage Source",
                    description="Determine the excitation voltage source powering the divider network.",
                )
            )
            step_idx += 1
            steps.append(
                AnalysisStep(
                    step_number=step_idx,
                    title="Identify Divider Branch",
                    description="Locate the continuous series resistor branch connected across the source.",
                )
            )
            step_idx += 1
            steps.append(
                AnalysisStep(
                    step_number=step_idx,
                    title="Determine Vout Node",
                    description="Identify the intermediate node between resistors as the divider output.",
                )
            )
            step_idx += 1
            steps.append(
                AnalysisStep(
                    step_number=step_idx,
                    title="Apply Voltage Divider Relation",
                    description="Evaluate Vout = Vin * (R2 / (R1 + R2)) using exact closed-form relation.",
                    equation_reference="voltage-divider",
                )
            )
            step_idx += 1
            steps.append(
                AnalysisStep(
                    step_number=step_idx,
                    title="Calculate Branch Currents",
                    description="Compute continuous series current I = Vin / (R1 + R2).",
                    equation_reference="ohm-i",
                )
            )
            step_idx += 1
            steps.append(
                AnalysisStep(
                    step_number=step_idx,
                    title="Calculate Component Power",
                    description="Compute dissipation P = I^2 * R for each resistor and power supplied by source.",
                    equation_reference="power-i2r",
                )
            )
            step_idx += 1
            steps.append(
                AnalysisStep(
                    step_number=step_idx,
                    title="Validate Conservation of Power",
                    description="Verify that sum of generated power equals sum of absorbed power.",
                )
            )
            step_idx += 1
            steps.append(
                AnalysisStep(
                    step_number=step_idx,
                    title="Optionally Verify with SPICE",
                    description="Execute DC operating point (.op) simulation via ngspice to confirm nodal voltages.",
                )
            )
            return steps

        if TopologyType.CURRENT_DIVIDER in matched_topos:
            steps.append(
                AnalysisStep(
                    step_number=step_idx,
                    title="Identify Current Source",
                    description="Identify independent current source delivering total injected current Itot.",
                )
            )
            step_idx += 1
            steps.append(
                AnalysisStep(
                    step_number=step_idx,
                    title="Calculate Equivalent Parallel Resistance",
                    description="Compute equivalent resistance Req = 1 / (sum(1/Rk)).",
                )
            )
            step_idx += 1
            steps.append(
                AnalysisStep(
                    step_number=step_idx,
                    title="Apply Current Divider Formula",
                    description="Compute branch current Ik = Itot * (Req / Rk).",
                )
            )
            step_idx += 1
            steps.append(
                AnalysisStep(
                    step_number=step_idx,
                    title="Validate KCL at Junction",
                    description="Verify sum of branch currents equals total injected current.",
                )
            )
            return steps

        if classification == TopologyType.RC.value:
            steps.append(
                AnalysisStep(
                    step_number=step_idx,
                    title="Compute Time Constant",
                    description="Calculate circuit time constant tau = R * C.",
                )
            )
            step_idx += 1
            steps.append(
                AnalysisStep(
                    step_number=step_idx,
                    title="Determine Initial and Final Conditions",
                    description="Evaluate Vc(0-) and Vc(inf) in DC steady state.",
                )
            )
            step_idx += 1
            steps.append(
                AnalysisStep(
                    step_number=step_idx,
                    title="Solve Transient Response",
                    description="Evaluate natural and forced response v(t) = V_inf + (V_0 - V_inf) * exp(-t / tau).",
                )
            )
            step_idx += 1
            steps.append(
                AnalysisStep(
                    step_number=step_idx,
                    title="Optionally Verify with SPICE Transient (.tran)",
                    description="Run transient simulation over 5*tau time window.",
                )
            )
            return steps

        if classification == TopologyType.RL.value:
            steps.append(
                AnalysisStep(
                    step_number=step_idx,
                    title="Compute Time Constant",
                    description="Calculate circuit time constant tau = L / R.",
                )
            )
            step_idx += 1
            steps.append(
                AnalysisStep(
                    step_number=step_idx,
                    title="Determine Initial and Final Conditions",
                    description="Evaluate Il(0-) and Il(inf) in DC steady state.",
                )
            )
            step_idx += 1
            steps.append(
                AnalysisStep(
                    step_number=step_idx,
                    title="Solve Transient Response",
                    description="Evaluate response i(t) = I_inf + (I_0 - I_inf) * exp(-t / tau).",
                )
            )
            return steps

        if classification == TopologyType.RLC.value:
            steps.append(
                AnalysisStep(
                    step_number=step_idx,
                    title="Calculate Damping and Natural Frequency",
                    description="Compute omega_0 = 1 / sqrt(L*C) and alpha damping factor.",
                )
            )
            step_idx += 1
            steps.append(
                AnalysisStep(
                    step_number=step_idx,
                    title="Classify Damping Regime",
                    description="Determine if response is overdamped, critically damped, or underdamped.",
                )
            )
            step_idx += 1
            steps.append(
                AnalysisStep(
                    step_number=step_idx,
                    title="Formulate Differential Equation",
                    description="Setup second-order KVL/KCL differential equation and solve characteristic roots.",
                )
            )
            return steps

        # Default general analysis steps
        steps.append(
            AnalysisStep(
                step_number=step_idx,
                title="Formulate KCL at Essential Nodes",
                description="Write nodal equations for all non-reference essential nodes.",
            )
        )
        step_idx += 1
        steps.append(
            AnalysisStep(
                step_number=step_idx,
                title="Formulate KVL for Fundamental Loops",
                description="Write loop equations for the fundamental cycle basis.",
            )
        )
        step_idx += 1
        steps.append(
            AnalysisStep(
                step_number=step_idx,
                title="Solve Nodal/Branch Equations",
                description="Solve the linear circuit system for node voltages and branch currents.",
            )
        )
        return steps
