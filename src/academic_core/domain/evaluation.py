# SPDX-License-Identifier: MIT
"""Subject assessment model (F4.1, pure): schemes, blocks, components.

Canonical records for Gestion-Academica `EsquemaEvaluacion` /
`BloqueEvaluacion` / `ComponenteEvaluacion` (+ `nota_minima`), evaluated
with the pure Decimal math of `domain/grading.py` (ADR-0011, ROUND_HALF_UP).

Semantics preserved from Gestion (golden-tested in tests/test_f4_evaluation.py):
- A scheme's result aggregates its *effective* items: loose components
  (no block) + one virtual item per block carrying the block weight and the
  block's own weighted mean (None while the block has no score).
- Block member weights are relative to the block (one nesting level).
- Multi-scheme rule "maximo": the applied scheme is the one with the
  highest current weighted mean among schemes with at least one score
  (first one wins on ties, stable by order); a single scheme always applies.
- `evaluate_subject` == Gestion `calcular_estado_notas`:
  * a manual final grade overrides everything (evaluated, 100 %);
  * otherwise the best scheme counts; it is *evaluated* only when the
    evaluated weight covers the total weight (raw comparison, not the
    rounded percentage);
  * any component of the applied scheme scored below its minimum grade
    forces "suspendida" even with a passing mean (MinGrade).
- States: aprobada | suspendida | en_progreso | sin_evaluar.

No Qt. No SQLite. No I/O. No floats: weights/scores are Decimal (or text).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from academic_core.domain.entities import DomainError
from academic_core.domain.grading import PASS_MARK, SCHEME_RULES, Aggregate, Scored, aggregate
from academic_core.domain.identity import validate

COMPONENT_KINDS = ("teoria", "parcial", "examen_final", "laboratorio", "otro")
GRADE_STATES = ("aprobada", "suspendida", "en_progreso", "sin_evaluar")


def to_decimal(value, field_name: str, *, low: int, high: int,
               optional: bool = False) -> Decimal | None:
    """Parse a weight/score from text/int/Decimal. Floats are refused at
    this boundary (binary artefacts); the migration converts them via
    ``str(float)`` which yields the shortest round-tripping literal."""
    if value is None or value == "":
        if optional:
            return None
        raise DomainError(f"{field_name} is required")
    if isinstance(value, float):
        raise DomainError(f"{field_name}: floats are not accepted, pass text")
    try:
        d = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise DomainError(f"{field_name} must be a decimal") from None
    if not d.is_finite() or not (Decimal(low) <= d <= Decimal(high)):
        raise DomainError(f"{field_name} must be within {low}..{high}")
    return d


def legacy_float_text(v) -> str | None:
    """Legacy REAL (e.g. Gestion SQLite FLOAT) -> exact decimal text.
    ``str(float)`` is the shortest literal that round-trips, so 33.33 stays
    "33.33" (never 33.329999...). Integers lose the trailing ".0"."""
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        raise DomainError("boolean where a number was expected")
    d = Decimal(str(v))
    if not d.is_finite():
        raise DomainError("non-finite legacy number")
    if d == d.to_integral_value():
        return str(d.quantize(Decimal(1)))
    return format(d.normalize(), "f")


@dataclass(frozen=True)
class MinGrade:
    """Minimum mark required in one component to be able to pass."""
    value: Decimal

    def violated_by(self, score: Decimal | None) -> bool:
        return score is not None and score < self.value


@dataclass
class AssessmentComponent:
    stable_id: str  # component:<s>:cmp:NNNNN
    name: str
    weight: Decimal  # 0..100, relative to scheme (loose) or block (member)
    kind: str = "otro"
    score: Decimal | None = None  # 0..10, None = not evaluated yet
    min_grade: Decimal | None = None  # 0..10
    order: int = 0

    def __post_init__(self) -> None:
        if validate(self.stable_id) != "component":
            raise DomainError(f"bad id: {self.stable_id}")
        if not self.name.strip():
            raise DomainError("AssessmentComponent.name is required")
        if self.kind not in COMPONENT_KINDS:
            raise DomainError(f"AssessmentComponent.kind must be one of {COMPONENT_KINDS}")
        self.weight = to_decimal(self.weight, "weight", low=0, high=100)
        self.score = to_decimal(self.score, "score", low=0, high=10, optional=True)
        self.min_grade = to_decimal(self.min_grade, "min_grade", low=0, high=10,
                                    optional=True)

    @property
    def minimum(self) -> MinGrade | None:
        return MinGrade(self.min_grade) if self.min_grade is not None else None

    def below_minimum(self) -> bool:
        m = self.minimum
        return bool(m and m.violated_by(self.score))


@dataclass
class AssessmentBlock:
    stable_id: str  # block:<s>:blk:NNNNN
    name: str
    weight: Decimal  # 0..100 of the scheme
    components: list[AssessmentComponent] = field(default_factory=list)
    order: int = 0

    def __post_init__(self) -> None:
        if validate(self.stable_id) != "block":
            raise DomainError(f"bad id: {self.stable_id}")
        if not self.name.strip():
            raise DomainError("AssessmentBlock.name is required")
        self.weight = to_decimal(self.weight, "weight", low=0, high=100)

    def members(self) -> list[AssessmentComponent]:
        return sorted(self.components, key=lambda c: (c.order, c.stable_id))

    def result(self) -> Aggregate:
        return aggregate([Scored(c.weight, c.score) for c in self.members()])


@dataclass
class AssessmentScheme:
    stable_id: str  # scheme:<s>:sch:NNNNN
    subject_id: str
    name: str
    components: list[AssessmentComponent] = field(default_factory=list)  # loose
    blocks: list[AssessmentBlock] = field(default_factory=list)
    order: int = 0

    def __post_init__(self) -> None:
        if validate(self.stable_id) != "scheme":
            raise DomainError(f"bad id: {self.stable_id}")
        if validate(self.subject_id) != "subject":
            raise DomainError(f"bad subject_id: {self.subject_id}")
        if not self.name.strip():
            raise DomainError("AssessmentScheme.name is required")

    def loose(self) -> list[AssessmentComponent]:
        return sorted(self.components, key=lambda c: (c.order, c.stable_id))

    def ordered_blocks(self) -> list[AssessmentBlock]:
        return sorted(self.blocks, key=lambda b: (b.order, b.stable_id))

    def all_components(self) -> list[AssessmentComponent]:
        out = self.loose()
        for b in self.ordered_blocks():
            out.extend(b.members())
        return out

    def effective(self) -> list[Scored]:
        """What actually weighs on 100 % of the scheme."""
        items = [Scored(c.weight, c.score) for c in self.loose()]
        items += [Scored(b.weight, b.result().media_ponderada) for b in self.ordered_blocks()]
        return items

    def result(self) -> "WeightedResult":
        return WeightedResult.of(self)


@dataclass(frozen=True)
class WeightedResult:
    """Aggregate of one scheme + its min-grade status."""
    scheme_id: str
    aggregate: Aggregate
    min_grade_violated: bool
    evaluated_items: int
    pending_items: int

    @property
    def complete(self) -> bool:
        a = self.aggregate
        return a.peso_total > 0 and a.peso_evaluado >= a.peso_total

    @classmethod
    def of(cls, scheme: AssessmentScheme) -> "WeightedResult":
        eff = scheme.effective()
        return cls(scheme.stable_id, aggregate(eff),
                   any(c.below_minimum() for c in scheme.all_components()),
                   sum(1 for i in eff if i.score is not None),
                   sum(1 for i in eff if i.score is None))


@dataclass(frozen=True)
class SchemeOutcome:
    scheme_id: str
    name: str
    result: WeightedResult
    applied: bool


def rank_schemes(schemes: list[AssessmentScheme], rule: str = "maximo") -> list[SchemeOutcome]:
    """Gestion `esquemas_con_ganador`."""
    if rule not in SCHEME_RULES:
        raise DomainError(f"rule must be one of {SCHEME_RULES}")
    ordered = sorted(schemes, key=lambda s: (s.order, s.stable_id))
    results = [(s, s.result()) for s in ordered]
    if len(results) <= 1:
        return [SchemeOutcome(s.stable_id, s.name, r, True) for s, r in results]
    winner = None
    best = None
    for s, r in results:
        m = r.aggregate.media_ponderada
        if m is not None and (best is None or m > best):
            best, winner = m, s.stable_id
    return [SchemeOutcome(s.stable_id, s.name, r, s.stable_id == winner) for s, r in results]


@dataclass(frozen=True)
class SubjectEvaluation:
    """Gestion `calcular_estado_notas` result."""
    state: str  # GRADE_STATES
    grade: Decimal | None
    evaluated: bool
    evaluated_items: int
    pending_items: int
    percent_evaluated: Decimal
    min_grade_violated: bool
    applied_scheme_id: str | None
    schemes: tuple[SchemeOutcome, ...]


def evaluate_subject(schemes: list[AssessmentScheme], final_override=None,
                     rule: str = "maximo") -> SubjectEvaluation:
    final = to_decimal(final_override, "final_grade", low=0, high=10, optional=True)
    ranked = rank_schemes(schemes, rule)
    violated = False
    applied_id = None
    if final is not None:
        grade, evaluated = final, True
        eff = [i for s in sorted(schemes, key=lambda s: (s.order, s.stable_id))
               for i in s.effective()]
        done = sum(1 for i in eff if i.score is not None)
        pending = sum(1 for i in eff if i.score is None)
        percent = Decimal("100.00")
    else:
        grade, evaluated = None, False
        done = pending = 0
        percent = Decimal("0.00")
        best = None
        for o in ranked:  # max by mean; first wins on ties (Python max semantics)
            m = o.result.aggregate.media_ponderada
            if m is not None and (best is None or m > best.result.aggregate.media_ponderada):
                best = o
        if best is not None:
            r = best.result
            applied_id = best.scheme_id
            percent = r.aggregate.porcentaje_evaluado
            violated = r.min_grade_violated
            done, pending = r.evaluated_items, r.pending_items
            if r.complete:
                grade, evaluated = r.aggregate.media_ponderada, True
    if evaluated:
        state = "aprobada" if grade >= PASS_MARK and not violated else "suspendida"
    elif done > 0:
        state = "en_progreso"
    else:
        state = "sin_evaluar"
    return SubjectEvaluation(state, grade, evaluated, done, pending, percent,
                             violated, applied_id, tuple(ranked))


def required_score(scheme: AssessmentScheme, target: Decimal = PASS_MARK) -> Decimal | None:
    """Uniform score needed on every still-unscored effective item of the
    scheme to reach ``target`` ("¿qué nota necesito?"). None when nothing is
    pending or weights are zero. Not clamped: > 10 means unreachable."""
    eff = scheme.effective()
    total = sum((i.weight for i in eff), Decimal(0))
    pending = sum((i.weight for i in eff if i.score is None), Decimal(0))
    if total <= 0 or pending <= 0:
        return None
    points = sum((i.weight * i.score for i in eff if i.score is not None), Decimal(0))
    from academic_core.domain.grading import _q2
    return _q2((Decimal(target) * total - points) / pending)
