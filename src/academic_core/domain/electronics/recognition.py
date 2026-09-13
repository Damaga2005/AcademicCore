"""ElectronicsConceptRecognizer (Phase 8-A, sections 14-16).

Consumes a B8 `AnalysisPlan` (never re-derives structure itself) and produces
deterministic concept candidates with evidence. No LLM, no free strings, no
machine learning: every candidate traces back to a `RecognitionMatch` (or, for
concepts anchored on classification rather than a specific topology match, to
the plan's own classification/applicable_analyses) already certified by B8.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from academic_core.domain.engineering.structural.planning import AnalysisPlan
from academic_core.domain.engineering.structural.types import ApplicabilityStatus as B8Status
from academic_core.domain.engineering.structural.types import TopologyType
from academic_core.domain.electronics.concepts import CONCEPTS
from academic_core.domain.electronics.registry import TOPOLOGY_TO_CONCEPTS
from academic_core.domain.electronics.types import ApplicabilityStatus


@dataclass(frozen=True)
class ConceptCandidate:
    concept: str  # concept stable_id
    status: ApplicabilityStatus
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)
    confidence: str = "DETERMINISTIC"  # mirrors plan.confidence unless abstained


class ElectronicsConceptRecognizer:
    """Deterministic B8 structural result -> concept candidates."""

    def recognize(self, plan: AnalysisPlan) -> list[ConceptCandidate]:
        if plan.confidence.value == "ABSTAINED":
            return [
                ConceptCandidate(
                    concept="concept:dc-resistive-network",
                    status=ApplicabilityStatus.ABSTAINED,
                    reason=f"B8 abstained: {plan.provenance.get('abstention_reason', 'unknown')}",
                    evidence={"plan_digest": plan.provenance.get("digest")},
                    confidence="ABSTAINED",
                )
            ]

        candidates: dict[str, ConceptCandidate] = {}
        matches_by_topology: dict[TopologyType, list] = {}
        for match in plan.recognized_topologies:
            matches_by_topology.setdefault(match.topology, []).append(match)

        for topology, matches in matches_by_topology.items():
            for concept_id in TOPOLOGY_TO_CONCEPTS.get(topology, ()):
                for match in matches:
                    candidate = self._evaluate(concept_id, topology, match, plan)
                    # Keep the strongest verdict if a concept is reachable via
                    # more than one matched topology/match (APPLICABLE wins).
                    prior = candidates.get(concept_id)
                    if prior is None or (
                        prior.status != ApplicabilityStatus.APPLICABLE
                        and candidate.status == ApplicabilityStatus.APPLICABLE
                    ):
                        candidates[concept_id] = candidate

        # Classification-anchored concepts (not tied to one specific
        # RecognitionMatch): general network laws applicable whenever B8
        # itself marked the corresponding analysis applicable.
        if plan.classification == TopologyType.RESISTIVE.value:
            candidates.setdefault("concept:dc-resistive-network", ConceptCandidate(
                concept="concept:dc-resistive-network",
                status=ApplicabilityStatus.APPLICABLE,
                reason="B8 classified the circuit as RESISTIVE.",
                evidence={"classification": plan.classification},
            ))
        if plan.kcl_nodes:
            candidates.setdefault("concept:kcl", ConceptCandidate(
                concept="concept:kcl",
                status=ApplicabilityStatus.APPLICABLE,
                reason="B8 exposed KCL-applicable node(s).",
                evidence={"kcl_nodes": list(plan.kcl_nodes)},
            ))
        if plan.kvl_loops:
            candidates.setdefault("concept:kvl", ConceptCandidate(
                concept="concept:kvl",
                status=ApplicabilityStatus.APPLICABLE,
                reason="B8 exposed KVL-applicable fundamental loop(s).",
                evidence={"kvl_loop_count": len(plan.kvl_loops)},
            ))
        if plan.applicable_analyses.get("OHMS_LAW") == B8Status.APPLICABLE.value:
            candidates.setdefault("concept:ohms-law", ConceptCandidate(
                concept="concept:ohms-law",
                status=ApplicabilityStatus.APPLICABLE,
                reason="B8 marked OHMS_LAW applicable.",
                evidence={},
            ))

        return [candidates[k] for k in sorted(candidates)]

    def _evaluate(self, concept_id: str, topology: TopologyType, match, plan: AnalysisPlan) -> ConceptCandidate:
        base_evidence = {
            "topology": topology.value,
            "elements": list(match.elements),
            "reason": match.reason,
            "metadata": dict(match.metadata or {}),
        }

        # concept:voltage-divider needs an explicit output tap node -- never
        # inferred (section 16 example): B8 records tap_nodes in metadata
        # only when they exist; empty/missing means abstain to NEEDS_INFORMATION.
        if concept_id in ("concept:voltage-divider", "concept:two-resistor-divider"):
            if concept_id == "concept:two-resistor-divider":
                # elements = sorted([v_ref, *r_chain]); exactly one V ref per
                # match, so resistor count = len(elements) - 1. Never assume
                # N==2 for the general concept above -- only this SPECIAL_CASE
                # checks it, and only from real match evidence.
                resistor_count = len(match.elements) - 1
                if resistor_count != 2:
                    return ConceptCandidate(
                        concept=concept_id, status=ApplicabilityStatus.NOT_APPLICABLE,
                        reason=f"Series chain has {resistor_count} resistors, not exactly 2.",
                        evidence=base_evidence,
                    )
            tap_nodes = (match.metadata or {}).get("tap_nodes") or []
            if not tap_nodes:
                return ConceptCandidate(
                    concept=concept_id, status=ApplicabilityStatus.NEEDS_INFORMATION,
                    reason="Series divider found but no explicit output tap node given.",
                    evidence=base_evidence,
                )
            return ConceptCandidate(
                concept=concept_id, status=ApplicabilityStatus.APPLICABLE,
                reason="Explicit output tap node present on a resistor series chain across a source.",
                evidence=base_evidence,
            )

        # concept:wheatstone-bridge-balanced requires R1*R4 == R2*R3 -- B8's
        # RESISTIVE_BRIDGE match carries structural evidence (which resistors
        # form the bridge, which nodes) but not per-arm resistance values, so
        # balance can never be inferred from topology/naming alone (section
        # 13). Without value evidence this concept must abstain, not guess.
        if concept_id == "concept:wheatstone-bridge-balanced":
            return ConceptCandidate(
                concept=concept_id, status=ApplicabilityStatus.NEEDS_INFORMATION,
                reason="Bridge structure matched, but balance (R1*R4 == R2*R3) requires arm "
                       "resistance values that structural recognition does not expose here; "
                       "never inferred from topology alone.",
                evidence=base_evidence,
            )

        return ConceptCandidate(
            concept=concept_id, status=ApplicabilityStatus.APPLICABLE,
            reason=f"B8 matched topology {topology.value} covering this concept.",
            evidence=base_evidence,
        )


__all__ = ["ConceptCandidate", "ElectronicsConceptRecognizer"]
