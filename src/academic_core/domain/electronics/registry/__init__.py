"""Deterministic Topology -> Concept registry and cross-registry validation
(Phase 8-A, sections 4 and 24).

`TOPOLOGY_TO_CONCEPTS` is the one place topology-to-concept association is
declared — the recognizer (see `electronics.recognition`) looks candidates
up here instead of hard-coding an if/elif chain per topology.
"""

from __future__ import annotations

from academic_core.domain.engineering.structural.types import TopologyType
from academic_core.domain.electronics.analyses import ANALYSES
from academic_core.domain.electronics.concepts import CONCEPTS
from academic_core.domain.electronics.equations import EQUATIONS, GENERAL_LAWS
from academic_core.domain.electronics.models import MODELS
from academic_core.domain.electronics.procedures import PROCEDURES
from academic_core.domain.electronics.types import Generality, RelationType

# Deterministic mapping: a matched B8 topology -> ordered concept candidates.
# Built from each concept's declared `topologies` (single source of truth),
# never duplicated by hand, so registry and concepts can't drift apart.
TOPOLOGY_TO_CONCEPTS: dict[TopologyType, tuple[str, ...]] = {}
for _concept in sorted(CONCEPTS.values(), key=lambda c: c.stable_id):
    for _topo_name in _concept.topologies:
        _topo = TopologyType(_topo_name)
        TOPOLOGY_TO_CONCEPTS.setdefault(_topo, ())
        TOPOLOGY_TO_CONCEPTS[_topo] = TOPOLOGY_TO_CONCEPTS[_topo] + (_concept.stable_id,)


def validate_registries() -> list[str]:
    """Check the invariants required by section 24. Returns a list of
    violations (empty = clean). Never raises — callers/tests decide."""
    problems: list[str] = []

    def _dangling(prefix: str, ids: set[str], targets: set[str], where: str) -> None:
        for t in sorted(targets - ids):
            if t.startswith(prefix):
                problems.append(f"{where}: dangling reference {t!r}")

    concept_ids = set(CONCEPTS)
    equation_ids = set(EQUATIONS)
    law_ids = set(GENERAL_LAWS)
    model_ids = set(MODELS)
    analysis_ids = set(ANALYSES)
    procedure_ids = set(PROCEDURES)

    # no duplicate stable IDs across registries (each dict key is already
    # unique within its own registry; check no cross-registry collision)
    all_ids = [*concept_ids, *equation_ids, *law_ids, *model_ids, *analysis_ids, *procedure_ids]
    if len(all_ids) != len(set(all_ids)):
        seen: set[str] = set()
        for i in all_ids:
            if i in seen:
                problems.append(f"duplicate stable_id across registries: {i!r}")
            seen.add(i)

    for concept in CONCEPTS.values():
        if not concept.stable_id.startswith("concept:"):
            problems.append(f"concept {concept.stable_id!r}: bad id prefix")
        targets = {r.target for r in concept.relations}
        _dangling("concept:", concept_ids, targets, concept.stable_id)
        _dangling("equation:", equation_ids, targets, concept.stable_id)
        _dangling("law:", law_ids, targets, concept.stable_id)
        _dangling("model:", model_ids, targets, concept.stable_id)
        _dangling("analysis:", analysis_ids, targets, concept.stable_id)
        for topo_name in concept.topologies:
            try:
                TopologyType(topo_name)
            except ValueError:
                problems.append(f"{concept.stable_id}: unknown topology {topo_name!r}")
        if concept.generality == Generality.SPECIAL_CASE:
            if concept.parent not in concept_ids:
                problems.append(f"{concept.stable_id}: SPECIAL_CASE parent {concept.parent!r} not a known concept")

    for law in GENERAL_LAWS.values():
        if not law.stable_id.startswith("law:"):
            problems.append(f"law {law.stable_id!r}: bad id prefix")
        if law.special_case_equation is not None and law.special_case_equation not in equation_ids:
            problems.append(f"{law.stable_id}: dangling special_case_equation {law.special_case_equation!r}")

    for equation in EQUATIONS.values():
        if equation.generality == Generality.SPECIAL_CASE and equation.parent not in law_ids:
            problems.append(f"{equation.stable_id}: SPECIAL_CASE parent {equation.parent!r} not a known law")

    for analysis in ANALYSES.values():
        if not analysis.stable_id.startswith("analysis:"):
            problems.append(f"analysis {analysis.stable_id!r}: bad id prefix")
        _dangling("concept:", concept_ids, set(analysis.prerequisites), analysis.stable_id)
        _dangling("equation:", equation_ids, set(analysis.equations), analysis.stable_id)
        for law_ref in analysis.laws:
            if law_ref not in law_ids:
                problems.append(f"{analysis.stable_id}: dangling law ref {law_ref!r}")

    for equation in EQUATIONS.values():
        if not equation.stable_id.startswith("equation:"):
            problems.append(f"equation {equation.stable_id!r}: bad id prefix")
        from academic_core.domain.engineering.units import DIM_NAMES
        if equation.dimension not in DIM_NAMES.values():
            problems.append(f"{equation.stable_id}: unknown dimension {equation.dimension!r}")

    for model in MODELS.values():
        if not model.stable_id.startswith("model:"):
            problems.append(f"model {model.stable_id!r}: bad id prefix")
        _dangling("equation:", equation_ids, set(model.equations), model.stable_id)

    for procedure in PROCEDURES.values():
        if not procedure.stable_id.startswith("procedure:"):
            problems.append(f"procedure {procedure.stable_id!r}: bad id prefix")
        if procedure.concept not in concept_ids:
            problems.append(f"{procedure.stable_id}: dangling concept ref {procedure.concept!r}")
        if procedure.analysis not in analysis_ids:
            problems.append(f"{procedure.stable_id}: dangling analysis ref {procedure.analysis!r}")
        for step in procedure.steps:
            if step.equation is not None and step.equation not in equation_ids:
                problems.append(
                    f"{procedure.stable_id} step {step.order}: dangling equation ref {step.equation!r}")
            if step.law is not None and step.law not in law_ids:
                problems.append(
                    f"{procedure.stable_id} step {step.order}: dangling law ref {step.law!r}")

    return problems


__all__ = ["TOPOLOGY_TO_CONCEPTS", "validate_registries"]
