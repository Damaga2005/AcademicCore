"""Grading Policy and Summative Evaluation Mathematics (Phase F9-B).

Pure domain layer:
- Deterministic Decimal arithmetic (ROUND_HALF_UP).
- Zero float conversions.
- Configurable passing threshold, scale, negative marking, and partial credit.
- Invariants raise DomainError.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from academic_core.domain.entities import DomainError
from academic_core.domain.results import Scale, N_10


def _q2(v: Decimal) -> Decimal:
    """Quantize to 2 decimal places with HALF_UP."""
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _q4(v: Decimal) -> Decimal:
    """Quantize to 4 decimal places with HALF_UP."""
    return v.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class GradingPolicy:
    """Summative grading policy rules for an assessment."""
    passing_score: Decimal = Decimal("5.0")
    max_score: Decimal = Decimal("10.0")
    negative_marking_factor: Decimal = Decimal("0")
    allow_partial_credit: bool = True
    scale: Scale = N_10

    def __post_init__(self) -> None:
        if self.max_score <= Decimal(0):
            raise DomainError(f"GradingPolicy.max_score must be > 0, got {self.max_score}")
        if not (Decimal(0) <= self.passing_score <= self.max_score):
            raise DomainError(
                f"GradingPolicy.passing_score must be between 0 and {self.max_score}, got {self.passing_score}"
            )
        if not (Decimal(0) <= self.negative_marking_factor <= Decimal(1)):
            raise DomainError(
                f"GradingPolicy.negative_marking_factor must be in [0, 1], got {self.negative_marking_factor}"
            )

    def score_item(
        self,
        *,
        is_correct: bool | None,
        raw_ratio: Decimal | None,
        weight: Decimal,
    ) -> Decimal:
        """Calculate the net score for a single item attempt.
        
        Parameters
        ----------
        is_correct:
            True if answer is correct, False if incorrect, None if omitted.
        raw_ratio:
            Normalized partial credit ratio in [0.0, 1.0], or None.
        weight:
            Weight assigned to this item.
        """
        if weight <= Decimal(0):
            raise DomainError(f"Item weight must be > 0, got {weight}")

        # Omitted question: 0 score, no penalty
        if is_correct is None and raw_ratio is None:
            return Decimal(0)

        # Correct answer
        if is_correct is True:
            if raw_ratio is not None and self.allow_partial_credit:
                clamped_ratio = max(Decimal(0), min(Decimal(1), raw_ratio))
                return clamped_ratio * weight
            return weight

        # Incorrect answer with potential partial credit
        if raw_ratio is not None and raw_ratio > Decimal(0) and self.allow_partial_credit:
            clamped_ratio = max(Decimal(0), min(Decimal(1), raw_ratio))
            return clamped_ratio * weight

        # Completely incorrect: apply negative marking penalty if configured
        if self.negative_marking_factor > Decimal(0):
            return - (self.negative_marking_factor * weight)

        return Decimal(0)

    def aggregate_scores(
        self,
        item_scores: dict[str, Decimal],
        total_weight: Decimal,
    ) -> tuple[Decimal, Decimal, bool]:
        """Aggregate item scores into (final_score, percentage, passed).
        
        Negative marking deductions may reduce item scores, but overall session
        score is floored at Decimal(0).
        """
        if total_weight <= Decimal(0):
            raise DomainError(f"Total weight must be > 0, got {total_weight}")

        raw_sum = sum(item_scores.values(), Decimal(0))
        effective_sum = max(Decimal(0), raw_sum)

        fraction = effective_sum / total_weight
        final_score = _q2(fraction * self.max_score)
        percentage = _q2(fraction * Decimal("100"))
        passed = final_score >= self.passing_score

        return final_score, percentage, passed
