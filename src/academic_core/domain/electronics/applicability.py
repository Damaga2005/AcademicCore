"""Analysis applicability (Phase 8-A, section 13).

Never returns a bare bool: always a structured result with status, reason,
evidence, confidence, prerequisites, and provenance. Delegates the actual
structural judgment to B8's `AnalysisPlan.applicable_analyses` and re-maps
its status vocabulary onto the richer one this layer needs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from academic_core.domain.engineering.structural.planning import AnalysisPlan
from academic_core.domain.engineering.structural.types import ApplicabilityStatus as B8Status
from academic_core.domain.electronics.analyses import ANALYSES, ElectronicsAnalysis
from academic_core.domain.electronics.types import ApplicabilityStatus, provenance

_B8_TO_ELECTRONICS = {
    B8Status.PRIMARY.value: ApplicabilityStatus.APPLICABLE,
    B8Status.APPLICABLE.value: ApplicabilityStatus.APPLICABLE,
    B8Status.NOT_APPLICABLE.value: ApplicabilityStatus.NOT_APPLICABLE,
    B8Status.UNKNOWN.value: ApplicabilityStatus.NEEDS_INFORMATION,
    B8Status.NEEDS_TARGET_TERMINALS.value: ApplicabilityStatus.NEEDS_INFORMATION,
}


@dataclass(frozen=True)
class AnalysisApplicabilityResult:
    analysis: str  # analysis stable_id
    status: ApplicabilityStatus
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)
    confidence: str = "DETERMINISTIC"
    prerequisites: tuple[str, ...] = ()
    provenance: dict = field(default_factory=dict)


def check_analysis_applicability(analysis_id: str, plan: AnalysisPlan) -> AnalysisApplicabilityResult:
    """Is `analysis_id` applicable to the circuit `plan` was built from?"""
    analysis: ElectronicsAnalysis = ANALYSES[analysis_id]

    if plan.confidence.value == "ABSTAINED":
        return AnalysisApplicabilityResult(
            analysis=analysis_id, status=ApplicabilityStatus.ABSTAINED,
            reason=f"B8 abstained: {plan.provenance.get('abstention_reason', 'unknown')}",
            confidence="ABSTAINED", prerequisites=analysis.prerequisites,
            provenance=provenance(analysis_id),
        )

    b8_value = plan.applicable_analyses.get(analysis.analysis_type.value)
    if b8_value is None:
        return AnalysisApplicabilityResult(
            analysis=analysis_id, status=ApplicabilityStatus.NOT_APPLICABLE,
            reason=f"B8 does not classify {analysis.analysis_type.value}.",
            prerequisites=analysis.prerequisites, provenance=provenance(analysis_id),
        )

    status = _B8_TO_ELECTRONICS[b8_value]
    return AnalysisApplicabilityResult(
        analysis=analysis_id, status=status,
        reason=f"B8 applicability for {analysis.analysis_type.value} is {b8_value}.",
        evidence={"b8_status": b8_value, "classification": plan.classification},
        prerequisites=analysis.prerequisites, provenance=provenance(analysis_id),
    )


__all__ = ["AnalysisApplicabilityResult", "check_analysis_applicability"]
