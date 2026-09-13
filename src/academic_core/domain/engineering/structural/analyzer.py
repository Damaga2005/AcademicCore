"""Structural Circuit Analyzer entry point (Phase 7-B8).

Coordinates graph construction, topological rule evaluation, and analysis planning.
Pure domain implementation: deterministic, extensible, zero I/O.
"""

from __future__ import annotations

from academic_core.domain.engineering.circuit import Circuit
from academic_core.domain.engineering.structural.elements import CircuitGraph
from academic_core.domain.engineering.structural.planning import (
    AnalysisClassifier,
    AnalysisPlan,
)
from academic_core.domain.engineering.structural.rules import RuleRegistry


class StructuralCircuitAnalyzer:
    """Deterministic structural circuit analyzer and topology recognizer."""

    def __init__(
        self,
        registry: RuleRegistry | None = None,
        classifier: AnalysisClassifier | None = None,
    ):
        self.registry = registry or RuleRegistry(default_rules=True)
        self.classifier = classifier or AnalysisClassifier()

    def analyze(
        self,
        circuit: Circuit,
        target_terminals: tuple[str, str] | None = None,
        at: str | None = None,
    ) -> AnalysisPlan:
        """Perform comprehensive structural analysis on a canonical Circuit.

        Parameters
        ----------
        circuit:
            The canonical F6 Circuit to analyze.
        target_terminals:
            Optional pair of node names for Thévenin/Norton port analysis.
        at:
            Optional ISO timestamp for deterministic provenance.

        Returns
        -------
        AnalysisPlan:
            Deterministic plan containing recognized topologies, applicable
            analyses, KCL nodes, KVL loops, steps, warnings, and confidence.
        """
        graph = CircuitGraph(circuit)
        matches = self.registry.evaluate_all(graph)
        return self.classifier.classify(
            graph=graph,
            matches=matches,
            target_terminals=target_terminals,
            at=at,
        )
