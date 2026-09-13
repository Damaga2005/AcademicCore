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
    USES_LAW = "uses_law"
    USES_ANALYSIS = "uses_analysis"
    PRECEDES = "precedes"


class ConceptCategory(str, Enum):
    """Coarse classification of an ElectronicsConcept."""

    CIRCUIT_LAW = "CIRCUIT_LAW"
    CIRCUIT_ANALYSIS = "CIRCUIT_ANALYSIS"
    NETWORK_THEOREM = "NETWORK_THEOREM"


class Generality(str, Enum):
    """Section 5 contract: does an entry represent a general rule over its
    whole mathematical domain, or a named special case of one?

    A SPECIAL_CASE must declare `parent` (the GENERAL entry it specializes)
    wherever this enum is used (concepts, equations, general laws) — the
    docstring/description alone is not a substitute for a checkable field.
    """

    GENERAL = "GENERAL"
    SPECIAL_CASE = "SPECIAL_CASE"


class ImplementationStatus(str, Enum):
    """Section 36: honest capability declaration for a computation. Never
    claim IMPLEMENTED for a domain the calculation engine cannot actually
    cover — declare PARTIAL/NOT_IMPLEMENTED/OUT_OF_SCOPE instead."""

    IMPLEMENTED = "IMPLEMENTED"
    PARTIAL = "PARTIAL"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


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
