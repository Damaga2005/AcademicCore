"""Electronics knowledge model: shared enums and constants (Phase 8-A).

Deliberately does NOT redefine B8's `TopologyType`/`AnalysisType` (structural
truth stays B8's alone) — only adds vocabulary the knowledge layer needs on
top: relation kinds between concepts, and a richer applicability status that
distinguishes "needs more information" from "not applicable" (B8's own
`ApplicabilityStatus` conflates both into UNKNOWN/NEEDS_TARGET_TERMINALS).
"""

from __future__ import annotations

from enum import Enum

INTERNAL_SOURCE = "academic-core-internal"
KNOWLEDGE_VERSION = "f8a-knowledge/1.0"


class RelationType(str, Enum):
    """Explicit relation kinds between knowledge-model entities."""

    REQUIRES = "requires"
    RELATED_TO = "related_to"
    IS_A = "is_a"
    CONTAINS = "contains"
    USES_MODEL = "uses_model"
    USES_EQUATION = "uses_equation"
    USES_ANALYSIS = "uses_analysis"
    PRECEDES = "precedes"


class ConceptCategory(str, Enum):
    """Coarse classification of an ElectronicsConcept."""

    CIRCUIT_LAW = "CIRCUIT_LAW"
    CIRCUIT_ANALYSIS = "CIRCUIT_ANALYSIS"
    NETWORK_THEOREM = "NETWORK_THEOREM"


class ApplicabilityStatus(str, Enum):
    """Structured applicability verdict for concept/analysis recognition.

    Never a bare bool (section 13): always paired with reason/evidence/
    confidence/prerequisites/provenance by the callers that produce it.
    """

    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NEEDS_INFORMATION = "NEEDS_INFORMATION"
    ABSTAINED = "ABSTAINED"


def provenance(stable_id: str, version: str = KNOWLEDGE_VERSION) -> dict:
    """Internal, versioned provenance stamp. Never fabricates external sources."""
    return {"source": INTERNAL_SOURCE, "version": version, "stable_id": stable_id}
