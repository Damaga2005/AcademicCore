"""Analysis classification and execution planning (Phase 7-B8).

Generates structured, deterministic analysis plans, identifying applicable analyses
(KCL, KVL, Ohm's law, Power, Thévenin, Norton, DC, Transient, AC) and enforcing
the mandatory ambiguity and abstention protocol.
"""

from __future__ import annotations

import hashlib
import json
import re
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

# Values that must never be treated as positive evidence, regardless of which
# key they appear under (case-insensitive). Absence-of-evidence must never be
# promoted to a positive recognition (F7-B8 hardening rule 0).
_FALSE_LIKE = {"", "false", "none", "0", "no", "off", "null"}

# Word-boundary match only: a textual excitation marker like "AC 5V 60Hz" or
# "ac" is accepted, but a substring occurrence inside an unrelated word (e.g.
# "trace", "aircraft") is not.
_AC_WORD_RE = re.compile(r"\bac\b", re.IGNORECASE)


def _has_positive_evidence(value: Any) -> bool:
    """Return True only if `value` is a real, non-negated piece of evidence.

    Used to validate metadata/parameter *values* before treating the mere
    presence of a key (e.g. "ac", "tolerance", "uncertainty", "sensitivity")
    as proof of something. A key being present with a falsy/negating value
    (False, None, "", 0, "false", "none", ...) must never count as evidence.
    """
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in _FALSE_LIKE
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, dict):
        return bool(value)
    if isinstance(value, (list, tuple, set)):
        return bool(value)
    return bool(value)


def _has_valid_ac_excitation(comp: Any) -> bool:
    """Determine whether a V/I source carries unambiguous AC excitation evidence.

    Accepts (in order of precedence):
    1. An explicit "ac"/"AC" key in parameters or metadata whose *value* is
       validated (not False/None/""/0/"false"/"none").
    2. An explicit amplitude+frequency pair, both carrying real values.
    3. A textual representation containing the standalone word "ac" in any
       string-valued parameter/metadata entry (word-boundary matched, so
       "trace" or "aircraft" never match).

    Never triggered by the mere presence of RLC elements, and never by an
    unrelated metadata key that happens to contain the substring "ac".
    """
    if comp.type not in ("V", "I"):
        return False
    for source in (comp.parameters or {}, comp.metadata or {}):
        for key in ("ac", "AC"):
            if key in source and _has_positive_evidence(source[key]):
                return True
        amplitude = source.get("amplitude")
        frequency = source.get("frequency", source.get("freq"))
        if _has_positive_evidence(amplitude) and _has_positive_evidence(frequency):
            return True
        for value in source.values():
            if isinstance(value, str) and _AC_WORD_RE.search(value):
                return True
    return False


# Explicit, unambiguous metadata/parameter keys accepted as evidence for each
# statistical/uncertainty analysis. Deliberately excludes short/ambiguous
# tokens such as "u", "dev", "vary", "sens", "tol", "mc", "unc", "gum" which
# can collide with unrelated metadata and would turn absence-of-evidence into
# a false positive recognition.
_MONTE_CARLO_KEYS = ("tolerance", "distribution")
_GUM_KEYS = ("uncertainty",)
_SENSITIVITY_KEYS = ("sensitivity",)


def _has_explicit_evidence(comp: Any, keys: tuple[str, ...]) -> bool:
    for source in (comp.parameters or {}, comp.metadata or {}):
        for k, v in source.items():
            if k.lower() in keys and _has_positive_evidence(v):
                return True
    return False


def _canonical_value(value: Any) -> Any:
    """Recursively normalize a value into a JSON-stable, order-independent form."""
    if value is None:
        return None
    if hasattr(value, "compact"):
        return value.compact()
    if isinstance(value, dict):
        return {str(k): _canonical_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(v) for v in value]
    if isinstance(value, set):
        return sorted((_canonical_value(v) for v in value), key=str)
    return value


def _canonical_component(comp: Any) -> dict[str, Any]:
    return {
        "ref": comp.ref.upper(),
        "type": comp.type.upper(),
        "value": _canonical_value(comp.value),
        "pins": {str(k): str(v) for k, v in sorted(comp.pins.items())},
        "parameters": _canonical_value(dict(comp.parameters or {})),
        "metadata": _canonical_value(dict(comp.metadata or {})),
    }


def _canonical_structure(
    graph: CircuitGraph,
    matches: list[RecognitionMatch],
    classification: str,
    target_terminals: tuple[str, str] | None,
) -> dict[str, Any]:
    """Build a deterministic, insertion-order-independent structural fingerprint.

    Incorporates circuit identity, full component data (refs/types/values/
    units/parameters/metadata), pin/node connectivity, topology matches,
    classification, and target terminals -- everything the spec (section 24)
    requires so that two materially different circuits never collide and the
    same semantic circuit always produces the same digest regardless of
    component/node/metadata insertion order. Excludes timestamps, object
    identities, and any non-deterministic value.
    """
    components = [
        _canonical_component(c)
        for c in sorted(graph.components.values(), key=lambda c: c.ref.upper())
    ]
    branches = [
        {"id": b.id, "ref": b.ref, "type": b.type, "node1": b.node1, "node2": b.node2}
        for b in sorted(graph.branches, key=lambda b: b.id)
    ]
    topo_matches = [
        {
            "topology": m.topology.value,
            "elements": list(m.elements),
            "metadata": _canonical_value(dict(m.metadata or {})),
        }
        for m in sorted(matches, key=lambda m: (m.topology.value, m.elements))
    ]
    tt: list[str] | None = None
    if target_terminals is not None:
        tt = [str(target_terminals[0]).strip(), str(target_terminals[1]).strip()]
    return {
        "circuit_name": graph.circuit_name,
        "nodes": sorted(graph.nodes.keys()),
        "components": components,
        "branches": branches,
        "recognized_topologies": topo_matches,
        "classification": classification,
        "target_terminals": tt,
        "engine": PLAN_ENGINE_VERSION,
    }


def _digest_for(structure: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(structure, sort_keys=True, default=str).encode()
    ).hexdigest()


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
                if t1 not in graph.nodes or t2 not in graph.nodes:
                    applicable[AnalysisType.THEVENIN.value] = ApplicabilityStatus.UNKNOWN.value
                    applicable[AnalysisType.NORTON.value] = ApplicabilityStatus.UNKNOWN.value
                    warnings.append(f"specified target terminals {target_terminals} not found in circuit")
                elif t1 == t2:
                    applicable[AnalysisType.THEVENIN.value] = ApplicabilityStatus.UNKNOWN.value
                    applicable[AnalysisType.NORTON.value] = ApplicabilityStatus.UNKNOWN.value
                    warnings.append(f"degenerate target terminals: {t1} == {t2}")
                else:
                    comps = graph.get_connected_components()
                    same_comp = any(t1 in c and t2 in c for c in comps)
                    if not same_comp:
                        applicable[AnalysisType.THEVENIN.value] = ApplicabilityStatus.UNKNOWN.value
                        applicable[AnalysisType.NORTON.value] = ApplicabilityStatus.UNKNOWN.value
                        warnings.append(f"target terminals {t1} and {t2} belong to disconnected subgraphs")
                    else:
                        applicable[AnalysisType.THEVENIN.value] = ApplicabilityStatus.APPLICABLE.value
                        applicable[AnalysisType.NORTON.value] = ApplicabilityStatus.APPLICABLE.value
            else:
                applicable[AnalysisType.THEVENIN.value] = ApplicabilityStatus.NEEDS_TARGET_TERMINALS.value
                applicable[AnalysisType.NORTON.value] = ApplicabilityStatus.NEEDS_TARGET_TERMINALS.value
        else:
            applicable[AnalysisType.THEVENIN.value] = ApplicabilityStatus.NOT_APPLICABLE.value
            applicable[AnalysisType.NORTON.value] = ApplicabilityStatus.NOT_APPLICABLE.value

        # 7. Simulation / Operating Point / Dynamic Analysis
        primary_analysis: AnalysisType | None = None

        # Check excitation: require validated, unambiguous AC evidence on a
        # voltage/current source (never inferred from RLC element presence).
        has_ac_source = any(_has_valid_ac_excitation(c) for c in graph.components.values())

        if classification == TopologyType.RESISTIVE.value:
            primary_analysis = AnalysisType.DC_OPERATING_POINT
            applicable[AnalysisType.DC_OPERATING_POINT.value] = ApplicabilityStatus.PRIMARY.value
            applicable[AnalysisType.DC_SWEEP.value] = ApplicabilityStatus.APPLICABLE.value
        elif classification in (TopologyType.RC.value, TopologyType.RL.value, TopologyType.RLC.value):
            primary_analysis = AnalysisType.TRANSIENT
            applicable[AnalysisType.TRANSIENT.value] = ApplicabilityStatus.PRIMARY.value
            applicable[AnalysisType.DC_STEADY_STATE.value] = ApplicabilityStatus.APPLICABLE.value
            applicable[AnalysisType.DC_OPERATING_POINT.value] = ApplicabilityStatus.APPLICABLE.value
            prerequisites.append("initial conditions required if non-zero transient initial state requested")
        else:
            if has_sources:
                primary_analysis = AnalysisType.DC_OPERATING_POINT
                applicable[AnalysisType.DC_OPERATING_POINT.value] = ApplicabilityStatus.PRIMARY.value

        # AC applicability requires explicit AC excitation
        if has_ac_source:
            applicable[AnalysisType.AC.value] = ApplicabilityStatus.APPLICABLE.value
        else:
            applicable[AnalysisType.AC.value] = ApplicabilityStatus.NOT_APPLICABLE.value

        # 8. Statistical & Uncertainty Analysis (Monte Carlo, GUM, Sensitivity)
        # Never mark applicable simply because resistors exist, and never on
        # ambiguous short keys ("u", "dev", "vary", "sens", ...) that could
        # mean something unrelated: require an explicit, validated key.
        has_mc_meta = any(_has_explicit_evidence(c, _MONTE_CARLO_KEYS) for c in graph.components.values())
        has_gum_meta = any(_has_explicit_evidence(c, _GUM_KEYS) for c in graph.components.values())
        has_sens_meta = any(_has_explicit_evidence(c, _SENSITIVITY_KEYS) for c in graph.components.values())

        if has_mc_meta:
            applicable[AnalysisType.MONTE_CARLO.value] = ApplicabilityStatus.APPLICABLE.value
        else:
            applicable[AnalysisType.MONTE_CARLO.value] = ApplicabilityStatus.NOT_APPLICABLE.value

        if has_gum_meta:
            applicable[AnalysisType.GUM_UNCERTAINTY.value] = ApplicabilityStatus.APPLICABLE.value
        else:
            applicable[AnalysisType.GUM_UNCERTAINTY.value] = ApplicabilityStatus.NOT_APPLICABLE.value

        if has_sens_meta:
            applicable[AnalysisType.SENSITIVITY.value] = ApplicabilityStatus.APPLICABLE.value
        else:
            applicable[AnalysisType.SENSITIVITY.value] = ApplicabilityStatus.NOT_APPLICABLE.value

        # 9. Confidence determination
        # DETERMINISTIC means derived from deterministic topological rules; warnings do not degrade this to "HIGH"
        confidence = ConfidenceLevel.DETERMINISTIC

        # 10. Step Generation
        steps = self._generate_steps(classification, matched_topos, ref_node)

        # 11. Provenance -- digest covers the full canonical structural content
        # (components, values, units, parameters, metadata, connectivity,
        # recognized topologies, classification, target terminals), is
        # insertion-order independent, and excludes the timestamp.
        stamp = at or datetime.now(timezone.utc).isoformat()
        structure = _canonical_structure(graph, matches, classification, target_terminals)
        content_hash = _digest_for(structure)

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
        # Provenance for an abstained plan must still reflect the real
        # structural content that was examined (section 25), not merely the
        # circuit name and abstention reason -- otherwise two materially
        # different abstained circuits could collide on the same digest.
        structure = _canonical_structure(graph, matches, TopologyType.UNKNOWN_TOPOLOGY.value, None)
        structure["abstention_reason"] = reason
        digest = _digest_for(structure)
        applicable = {a.value: ApplicabilityStatus.NOT_APPLICABLE.value for a in AnalysisType}

        return AnalysisPlan(
            circuit_id=graph.circuit_name,
            classification=TopologyType.UNKNOWN_TOPOLOGY.value,
            recognized_topologies=[],
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
