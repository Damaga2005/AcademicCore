"""Electronics knowledge & analysis foundation (Phase 8-A).

Connects B8's certified structural recognition to a deterministic knowledge
layer: concepts, models, analyses, equations, and procedures, plus a
recognizer and applicability checker that consume B8's `AnalysisPlan`
without modifying it. See docs/migration/ENGINEERING-F8A-ELECTRONICS-KNOWLEDGE.md.
"""

from __future__ import annotations

from academic_core.domain.electronics import (
    analyses, calc, concepts, equations, models, procedures, registry,
)
from academic_core.domain.electronics.applicability import (
    AnalysisApplicabilityResult,
    check_analysis_applicability,
)
from academic_core.domain.electronics.recognition import ConceptCandidate, ElectronicsConceptRecognizer
from academic_core.domain.electronics.types import (
    ApplicabilityStatus, Generality, ImplementationStatus, RelationType,
)

__all__ = [
    "concepts", "models", "analyses", "equations", "procedures", "registry", "calc",
    "ApplicabilityStatus", "RelationType", "Generality", "ImplementationStatus",
    "ConceptCandidate", "ElectronicsConceptRecognizer",
    "AnalysisApplicabilityResult", "check_analysis_applicability",
]
