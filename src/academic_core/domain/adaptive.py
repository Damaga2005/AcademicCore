# SPDX-License-Identifier: MIT
"""F11 adaptive engine (domain, pure): mastery → practice decisions.

Fully deterministic, LLM=OFF by construction. Consumes only certified
artifacts: F10 mastery states, F9 evidence history, D6 question banks,
D7 hierarchy. Owns no Student Model, no taxonomy, no correction.

Pipeline: eligible → filter → score → rank → constraints → route.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal

from academic_core.domain import question_bank as QB

ADAPTIVE_ENGINE = "f11-adaptive/1"
CONFIG_VERSION = 1
PLAN_TAG = "f11-adaptive-plan/1"

DIFFICULTY_ORDER = ("easy", "medium", "hard")

RATIONALE_CODES = (
    "LOW_MASTERY",
    "DIFFICULTY_FIT",
    "CONCEPT_RELEVANCE",
    "RECENT_ERROR",
    "PREREQUISITE_OK",
    "PREREQUISITE_UNMET",
    "REPETITION_AVOIDED",
    "DIVERSITY",
    "UNMAPPED",
    "NO_ELIGIBLE_EXERCISES",
)


def _dom(msg: str):
    from academic_core.domain.entities import DomainError
    return DomainError(msg, code="AC-DOM-001")


def _dec(v, what: str) -> Decimal:
    if isinstance(v, bool) or not isinstance(v, (str, int, Decimal)):
        raise _dom(f"{what} must be a decimal")
    try:
        d = Decimal(str(v))
    except Exception:
        raise _dom(f"{what} must be a decimal") from None
    if not d.is_finite():
        raise _dom(f"{what} must be finite")
    return d


@dataclass(frozen=True)
class AdaptiveConfig:
    """Versioned scoring/route configuration."""

    engine_version: str = ADAPTIVE_ENGINE
    config_version: int = CONFIG_VERSION
    mastery_weight: Decimal = Decimal("60")
    difficulty_weight: Decimal = Decimal("20")
    relevance_weight: Decimal = Decimal("15")
    diversity_weight: Decimal = Decimal("5")
    mastery_threshold_low: Decimal = Decimal("0.40")
    mastery_threshold_high: Decimal = Decimal("0.70")
    max_per_concept: int = 2
    exclude_done: bool = True
    allow_unspecified_difficulty: bool = False

    def __post_init__(self) -> None:
        if self.engine_version != ADAPTIVE_ENGINE:
            raise _dom(f"unknown engine_version: {self.engine_version!r}")
        if (not isinstance(self.config_version, int)
                or isinstance(self.config_version, bool)
                or self.config_version < 1):
            raise _dom("config_version must be an integer >= 1")
        for name in ("mastery_weight", "difficulty_weight",
                     "relevance_weight", "diversity_weight"):
            _dec(getattr(self, name), name)
        lo = _dec(self.mastery_threshold_low, "mastery_threshold_low")
        hi = _dec(self.mastery_threshold_high, "mastery_threshold_high")
        if not (Decimal(0) <= lo <= hi <= 1):
            raise _dom("thresholds must satisfy 0 <= low <= high <= 1")
        if (not isinstance(self.max_per_concept, int)
                or isinstance(self.max_per_concept, bool)
                or self.max_per_concept < 1):
            raise _dom("max_per_concept must be an integer >= 1")
        if not isinstance(self.exclude_done, bool):
            raise _dom("exclude_done must be bool")
        if not isinstance(self.allow_unspecified_difficulty, bool):
            raise _dom("allow_unspecified_difficulty must be bool")


@dataclass(frozen=True)
class Candidate:
    """One question considered for the plan (contractual fields only)."""

    question_id: str
    qtype: str
    difficulty: str
    concepts: tuple
    topic_ref: str
    subject_id: str
    content_version: int
    question_digest: str
    mastery_p: Decimal | None = None
    mastery_refs: tuple = ()  # concept refs with a real F10 state
    done: bool = False
    recent_error: bool = False
    prerequisite_ok: bool = True


@dataclass(frozen=True)
class ScoredCandidate:
    candidate: Candidate
    adaptive_score: Decimal
    rationale: tuple


@dataclass(frozen=True)
class AdaptivePlan:
    student_id: str
    selections: tuple  # ScoredCandidate, route order
    rationale_codes: tuple
    config_version: int
    model_version: str
    bank_digest: str
    mastery_snapshot: tuple  # (concept_ref, alpha, beta, p) at plan time
    context_digest: str = ""

    def __post_init__(self) -> None:
        codes = set(self.rationale_codes)
        unknown = codes - set(RATIONALE_CODES)
        if unknown:
            raise _dom(f"unknown rationale codes: {sorted(unknown)}")


@dataclass(frozen=True)
class AdaptiveContext:
    """Explicit learning context (no giant config)."""

    subject_id: str = ""
    topic_ref: str = ""
    concept_ref: str = ""
    exercise_count: int = 5
    allowed_types: tuple = ()
    difficulty_min: str = ""
    difficulty_max: str = ""

    def __post_init__(self) -> None:
        if (not isinstance(self.exercise_count, int)
                or isinstance(self.exercise_count, bool)
                or self.exercise_count < 1):
            raise _dom("exercise_count must be an integer >= 1")
        for t in self.allowed_types:
            if t not in QB.QUESTION_TYPES:
                raise _dom(f"bad qtype: {t!r}")
        for d in (self.difficulty_min, self.difficulty_max):
            if d and d not in QB.DIFFICULTIES:
                raise _dom(f"bad difficulty bound: {d!r}")


def target_difficulty(p: Decimal | None, config: AdaptiveConfig) -> str:
    """Deterministic mastery→difficulty mapping (documented policy)."""
    if p is None:
        return "unspecified"
    if p < config.mastery_threshold_low:
        return "easy"
    if p >= config.mastery_threshold_high:
        return "hard"
    return "medium"


def difficulty_fit(difficulty: str, target: str,
                    allow_unspecified: bool) -> Decimal:
    """1.0 exact, 0.5 one step away, 0 otherwise; unspecified per policy."""
    if target == "unspecified":
        return Decimal(1)
    if difficulty == "unspecified":
        return Decimal(1) if allow_unspecified else Decimal(0)
    if difficulty not in DIFFICULTY_ORDER:
        raise _dom(f"bad difficulty: {difficulty!r}")
    a = DIFFICULTY_ORDER.index(target)
    b = DIFFICULTY_ORDER.index(difficulty)
    d = abs(a - b)
    return {0: Decimal(1), 1: Decimal("0.5")}.get(d, Decimal(0))


def score_candidate(c: Candidate, config: AdaptiveConfig) -> tuple[Decimal, tuple]:
    """Explicit versioned score; every factor is contractual."""
    rationales = []
    mastery_p = c.mastery_p
    if mastery_p is None:
        # No evidence yet: unknown mastery counts as need, never as zero.
        need = Decimal(1)
        rationales.append("UNMAPPED")
    else:
        need = Decimal(1) - mastery_p
        if mastery_p < config.mastery_threshold_low:
            rationales.append("LOW_MASTERY")
        elif c.recent_error:
            rationales.append("RECENT_ERROR")
    fit = difficulty_fit(c.difficulty, target_difficulty(mastery_p, config),
                         config.allow_unspecified_difficulty)
    if fit == 1:
        rationales.append("DIFFICULTY_FIT")
    relevance = (Decimal(len(c.mastery_refs)) / Decimal(len(c.concepts))
                  if c.concepts else Decimal(0))
    if relevance > 0:
        rationales.append("CONCEPT_RELEVANCE")
    if not c.done:
        rationales.append("REPETITION_AVOIDED")
    if c.prerequisite_ok:
        rationales.append("PREREQUISITE_OK")
    score = (
        config.mastery_weight * need
        + config.difficulty_weight * fit
        + config.relevance_weight * relevance
        + config.diversity_weight * Decimal(0)  # diversity applied at route time
    ).quantize(Decimal("0.0001"))
    return score, tuple(rationales)


def rank_candidates(candidates: list[Candidate],
                    config: AdaptiveConfig) -> list[ScoredCandidate]:
    """score DESC, question_id ASC, content_version ASC (stable)."""
    scored = []
    for c in candidates:
        s, why = score_candidate(c, config)
        scored.append(ScoredCandidate(c, s, why))
    return sorted(
        scored,
        key=lambda s: (-s.adaptive_score, s.candidate.question_id,
                       s.candidate.content_version),
    )


def build_route(ranked: list[ScoredCandidate], *, limit: int,
                max_per_concept: int) -> tuple:
    """Cap per concept, then take top-N in rank order (diversity-aware)."""
    if limit < 1:
        raise _dom("limit must be >= 1")
    per_concept: dict[str, int] = {}
    picks = []
    for sc in ranked:
        if any(per_concept.get(r, 0) >= max_per_concept
               for r in sc.candidate.concepts):
            continue
        picks.append(sc)
        for r in sc.candidate.concepts:
            per_concept[r] = per_concept.get(r, 0) + 1
        if len(picks) >= limit:
            break
    return tuple(picks)


def plan_digest(plan: AdaptivePlan) -> str:
    """Reproducible digest of the whole plan (no timestamps inside)."""
    from academic_core.domain.question_bank import dumps_canonical
    body = {
        "bank_digest": plan.bank_digest,
        "config_version": plan.config_version,
        "context_digest": plan.context_digest,
        "mastery_snapshot": [list(m) for m in plan.mastery_snapshot],
        "model_version": plan.model_version,
        "rationale_codes": list(plan.rationale_codes),
        "selections": [
            {"concepts": list(s.candidate.concepts),
             "difficulty": s.candidate.difficulty,
             "qtype": s.candidate.qtype,
             "question_id": s.candidate.question_id,
             "rationale": list(s.rationale),
             "score": str(s.adaptive_score)}
            for s in plan.selections
        ],
        "student_id": plan.student_id,
    }
    raw = dumps_canonical(body).encode("utf-8")
    return hashlib.sha256(PLAN_TAG.encode() + b"\x00" + raw).hexdigest()


def bank_digest_of(question_ids) -> str:
    """Digest of the exact question set used for a plan (bank snapshot)."""
    from academic_core.domain.question_bank import dumps_canonical
    raw = dumps_canonical(sorted(question_ids)).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
