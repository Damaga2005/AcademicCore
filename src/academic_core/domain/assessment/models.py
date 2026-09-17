"""Assessment Aggregate and Item Domain Models (Phase F9-B).

Pure domain layer:
- Invariants raise DomainError.
- Deterministic item ordering and seed-based shuffling.
- Zero float policy, pure Decimal math for weights.
- No I/O, no UI, no database dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
import random

from academic_core.domain.assessment.policy import GradingPolicy
from academic_core.domain.entities import DomainError
from academic_core.domain.identity import validate


@dataclass(frozen=True)
class AssessmentItem:
    """A specific question item included in an assessment specification."""
    item_id: str
    question_id: str
    topic_id: str
    weight: Decimal = Decimal("1.0")
    difficulty: str = "medium"
    rubric_ref: str = ""
    options: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.item_id.strip():
            raise DomainError("AssessmentItem.item_id cannot be empty")
        if not self.question_id.strip():
            raise DomainError("AssessmentItem.question_id cannot be empty")
        if not self.topic_id.strip():
            raise DomainError("AssessmentItem.topic_id cannot be empty")
        if self.weight <= Decimal(0):
            raise DomainError(f"AssessmentItem.weight must be > 0, got {self.weight}")


@dataclass(frozen=True)
class Assessment:
    """Canonical multi-item summative evaluation specification aggregate."""
    stable_id: str  # assessment:<subject>:as:NNNNN
    subject_id: str  # subject:<slug>
    title: str
    description: str = ""
    items: tuple[AssessmentItem, ...] = ()
    duration_min: int = 0  # 0 = untimed
    attempts_allowed: int = 1
    policy: GradingPolicy = field(default_factory=GradingPolicy)
    shuffle_items: bool = False
    master_seed: int | None = None

    def __post_init__(self) -> None:
        if validate(self.stable_id) != "assessment":
            raise DomainError(f"bad stable_id: {self.stable_id}")
        if validate(self.subject_id) != "subject":
            raise DomainError(f"bad subject_id: {self.subject_id}")
        if not self.title.strip():
            raise DomainError("Assessment.title cannot be empty")
        if len(self.items) == 0:
            raise DomainError("Assessment must contain at least one item")
        if self.duration_min < 0:
            raise DomainError("Assessment.duration_min cannot be negative")
        if self.attempts_allowed < 1:
            raise DomainError("Assessment.attempts_allowed must be >= 1")

        # Check for unique item_ids
        seen = set()
        for it in self.items:
            if it.item_id in seen:
                raise DomainError(f"Duplicate item_id in assessment: {it.item_id}")
            seen.add(it.item_id)

    @property
    def total_weight(self) -> Decimal:
        """Sum of all item weights."""
        return sum((it.weight for it in self.items), Decimal(0))

    def get_item(self, item_id: str) -> AssessmentItem:
        """Find item by item_id or raise DomainError."""
        for it in self.items:
            if it.item_id == item_id:
                return it
        raise DomainError(f"Item not found in assessment: {item_id}")

    def generate_item_order(self, seed: int | None = None) -> tuple[str, ...]:
        """Generate deterministic item order for a session based on seed."""
        order = [it.item_id for it in self.items]
        if not self.shuffle_items:
            return tuple(order)

        effective_seed = seed if seed is not None else self.master_seed
        if effective_seed is not None:
            rng = random.Random(effective_seed)
            rng.shuffle(order)
        return tuple(order)
