"""Structural circuit analysis and topology recognition (Phase 7-B8).

Provides graph analysis, fundamental topology recognition, KCL/KVL applicability,
power analysis, dynamic classification, abstention protocols, and deterministic planning.
"""

from __future__ import annotations

from academic_core.domain.engineering.structural.analyzer import (
    StructuralCircuitAnalyzer,
)
from academic_core.domain.engineering.structural.elements import (
    CircuitGraph,
    StructuralBranch,
    StructuralNode,
)
from academic_core.domain.engineering.structural.planning import (
    PLAN_ENGINE_VERSION,
    AnalysisClassifier,
    AnalysisPlan,
    AnalysisStep,
)
from academic_core.domain.engineering.structural.rules import (
    CurrentDividerRule,
    DynamicNetworkRule,
    IndependentSourcesRule,
    ParallelResistorsRule,
    RecognitionMatch,
    RecognitionRule,
    ResistiveBridgeRule,
    RuleRegistry,
    SeriesParallelReducibleRule,
    SeriesResistorsRule,
    SingleResistorRule,
    VoltageDividerRule,
)
from academic_core.domain.engineering.structural.types import (
    AnalysisType,
    ApplicabilityStatus,
    ConfidenceLevel,
    TopologyType,
)

__all__ = [
    "StructuralCircuitAnalyzer",
    "CircuitGraph",
    "StructuralNode",
    "StructuralBranch",
    "AnalysisPlan",
    "AnalysisStep",
    "AnalysisClassifier",
    "PLAN_ENGINE_VERSION",
    "RecognitionMatch",
    "RecognitionRule",
    "RuleRegistry",
    "SingleResistorRule",
    "SeriesResistorsRule",
    "ParallelResistorsRule",
    "VoltageDividerRule",
    "CurrentDividerRule",
    "ResistiveBridgeRule",
    "SeriesParallelReducibleRule",
    "IndependentSourcesRule",
    "DynamicNetworkRule",
    "TopologyType",
    "AnalysisType",
    "ApplicabilityStatus",
    "ConfidenceLevel",
]
