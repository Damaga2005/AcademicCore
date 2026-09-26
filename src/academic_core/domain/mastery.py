# SPDX-License-Identifier: MIT
"""F10 mastery model (domain, pure): Beta-Binomial conjugate updates.

Explicit, auditable, deterministic probabilistic model over F9 evidence:

- Unit: one concept per student, ``Beta(alpha, beta)`` with Decimal
  arithmetic (no floats, no NaN/Infinity — rejected at the boundary).
- Observation: correct ``alpha += w``, incorrect ``beta += w``,
  review/omitted ``no_update``. ``w`` is the contracted assessment item
  weight, split equally across the item's concepts (documented; never
  invented per-observation weights).
- ``P(mastery) = alpha / (alpha + beta)``; posterior variance is the
  Beta variance (founded uncertainty, not an invented confidence).
- Aggregation: pooled posteriors (sums of member parameters), which is
  the conjugate aggregate — not a bare mean of probabilities.
- Everything folds through one code path, so incremental update ==
  rebuild from the observation set by construction.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, localcontext

MODEL_VERSION = "f10-beta/1"
CONFIG_VERSION = 1
OBS_TAG = "f10-observation/1"
STATE_TAG = "f10-state/1"

_DEFAULT_PREC = 28


def _dom(msg: str):
    from academic_core.domain.entities import DomainError
    return DomainError(msg, code="AC-DOM-001")


def _decimal(text: object, what: str) -> Decimal:
    if isinstance(text, bool) or not isinstance(text, (str, int, Decimal)):
        raise _dom(f"{what} must be a decimal")
    try:
        d = Decimal(str(text).strip() if isinstance(text, str) else text)
    except (InvalidOperation, ValueError, AttributeError):
        raise _dom(f"{what} must be a decimal") from None
    if not d.is_finite():
        raise _dom(f"{what} must be finite (no NaN/Infinity)")
    return d


def _check_prob_range(d: Decimal, what: str) -> Decimal:
    if d < 0:
        raise _dom(f"{what} must be >= 0")
    return d


@dataclass(frozen=True)
class MasteryConfig:
    """Versioned configuration (historical rows keep their own copy)."""

    model_version: str = MODEL_VERSION
    config_version: int = CONFIG_VERSION
    prior_alpha: Decimal = Decimal("1")
    prior_beta: Decimal = Decimal("1")
    weight_precision: int = 6

    def __post_init__(self) -> None:
        if self.model_version != MODEL_VERSION:
            raise _dom(f"unknown model_version: {self.model_version!r}")
        if (not isinstance(self.config_version, int)
                or isinstance(self.config_version, bool)
                or self.config_version < 1):
            raise _dom("config_version must be an integer >= 1")
        a = _check_prob_range(_decimal(self.prior_alpha, "prior_alpha"),
                              "prior_alpha")
        b = _check_prob_range(_decimal(self.prior_beta, "prior_beta"),
                              "prior_beta")
        if a + b <= 0:
            raise _dom("prior must carry positive mass (alpha+beta > 0)")
        object.__setattr__(self, "prior_alpha", a)
        object.__setattr__(self, "prior_beta", b)
        if (not isinstance(self.weight_precision, int)
                or isinstance(self.weight_precision, bool)
                or not 1 <= self.weight_precision <= 12):
            raise _dom("weight_precision must be an integer 1..12")


@dataclass(frozen=True)
class ConceptState:
    """Posterior for one (student, concept). Counters only grow."""

    ref: str
    alpha: Decimal
    beta: Decimal
    obs_count: int = 0
    model_version: str = MODEL_VERSION
    config_version: int = CONFIG_VERSION

    def __post_init__(self) -> None:
        _check_prob_range(_decimal(self.alpha, "alpha"), "alpha")
        _check_prob_range(_decimal(self.beta, "beta"), "beta")
        if (not isinstance(self.obs_count, int)
                or isinstance(self.obs_count, bool) or self.obs_count < 0):
            raise _dom("obs_count must be an integer >= 0")
        if self.model_version != MODEL_VERSION:
            raise _dom(f"unknown model_version: {self.model_version!r}")

    def probability(self) -> Decimal:
        with localcontext() as ctx:
            ctx.prec = _DEFAULT_PREC
            total = self.alpha + self.beta
            if total <= 0:
                raise _dom("state has no mass")
            return self.alpha / total

    def variance(self) -> Decimal:
        with localcontext() as ctx:
            ctx.prec = _DEFAULT_PREC
            a, b = self.alpha, self.beta
            total = a + b
            if total <= 0:
                raise _dom("state has no mass")
            return (a * b) / (total * total * (total + 1))


@dataclass(frozen=True)
class Observation:
    """One concept-directed evidence unit (idempotent by key+digest)."""

    student_id: str
    session_id: str
    item_id: str
    concept_ref: str
    topic_ref: str
    subject_id: str
    correct: bool
    alpha_delta: Decimal
    beta_delta: Decimal
    question_digest: str
    engine: str

    def __post_init__(self) -> None:
        for name in ("student_id", "session_id", "item_id", "concept_ref",
                     "topic_ref", "subject_id", "question_digest", "engine"):
            v = getattr(self, name)
            if not isinstance(v, str) or not v:
                raise _dom(f"observation.{name} is required")
        if not isinstance(self.correct, bool):
            raise _dom("observation.correct must be bool")
        _check_prob_range(_decimal(self.alpha_delta, "alpha_delta"),
                          "alpha_delta")
        _check_prob_range(_decimal(self.beta_delta, "beta_delta"),
                          "beta_delta")
        if self.alpha_delta + self.beta_delta <= 0:
            raise _dom("observation must carry positive mass")


def observation_digest(obs: Observation) -> str:
    from academic_core.domain.question_bank import dumps_canonical
    body = {"alpha_delta": str(obs.alpha_delta),
            "beta_delta": str(obs.beta_delta),
            "concept_ref": obs.concept_ref,
            "correct": obs.correct,
            "engine": obs.engine,
            "item_id": obs.item_id,
            "question_digest": obs.question_digest,
            "session_id": obs.session_id,
            "student_id": obs.student_id,
            "subject_id": obs.subject_id,
            "topic_ref": obs.topic_ref}
    raw = dumps_canonical(body).encode("utf-8")
    return hashlib.sha256(OBS_TAG.encode() + b"\x00" + raw).hexdigest()


def fold_deltas(ref: str, observations: list[Observation],
                 config: MasteryConfig) -> ConceptState:
    """Sum deltas directly (aggregation: ref is a topic/subject label).

    Used for topic/subject aggregates where member observations target
    concepts, not the aggregate id itself. Order-free, same result as
    rebuilding member states and pooling them.
    """
    alpha = config.prior_alpha
    beta = config.prior_beta
    count = 0
    for obs in observations:
        alpha += obs.alpha_delta
        beta += obs.beta_delta
        count += 1
    return ConceptState(ref, alpha, beta, count, config.model_version,
                        config.config_version)


def prior_state(ref: str, config: MasteryConfig) -> ConceptState:
    return ConceptState(ref, config.prior_alpha, config.prior_beta, 0,
                        config.model_version, config.config_version)


def apply_observation(state: ConceptState, obs: Observation) -> ConceptState:
    if obs.concept_ref != state.ref:
        raise _dom("observation targets another concept")
    return ConceptState(state.ref, state.alpha + obs.alpha_delta,
                        state.beta + obs.beta_delta,
                        state.obs_count + 1, state.model_version,
                        state.config_version)


def split_weight(weight: Decimal, n_concepts: int,
                 config: MasteryConfig) -> Decimal:
    """Split an item weight across its concepts (exact, fixed precision)."""
    if n_concepts < 1:
        raise _dom("concepts required for weight split")
    with localcontext() as ctx:
        ctx.prec = _DEFAULT_PREC
        quantum = Decimal(1).scaleb(-config.weight_precision)
        return (weight / n_concepts).quantize(quantum)


def observation_for(ref: str, *, student_id: str, session_id: str,
                    item_id: str, topic_ref: str, subject_id: str,
                    correct: bool, delta: Decimal,
                    question_digest: str, engine: str) -> Observation:
    """Build one observation from a pre-split weight delta (service splits)."""
    w = _check_prob_range(_decimal(delta, "delta"), "delta")
    if w <= 0:
        raise _dom("observation weight must be positive")
    if correct:
        return Observation(student_id, session_id, item_id, ref, topic_ref,
                           subject_id, True, w, Decimal(0), question_digest,
                           engine)
    return Observation(student_id, session_id, item_id, ref, topic_ref,
                       subject_id, False, Decimal(0), w, question_digest,
                       engine)


def fold_observations(ref: str, observations: list[Observation],
                      config: MasteryConfig) -> ConceptState:
    """Rebuild a concept state from its observation set (order-free sum)."""
    state = prior_state(ref, config)
    for obs in sorted(observations,
                      key=lambda o: (o.session_id, o.item_id, o.concept_ref)):
        state = apply_observation(state, obs)
    return state


def pool_states(ref: str, members: list[ConceptState]) -> ConceptState:
    """Pooled conjugate aggregate over member posteriors (auditable)."""
    if not members:
        raise _dom("pool needs at least one member")
    versions = {(m.model_version, m.config_version) for m in members}
    if len(versions) != 1:
        raise _dom("pool members must share model/config version")
    model_version, config_version = next(iter(versions))
    alpha = sum((m.alpha for m in members), Decimal(0))
    beta = sum((m.beta for m in members), Decimal(0))
    return ConceptState(ref, alpha, beta,
                        sum(m.obs_count for m in members),
                        model_version, config_version)


def state_digest(ref: str, state: ConceptState,
                 members: tuple = ()) -> str:
    from academic_core.domain.question_bank import dumps_canonical
    body = {"alpha": str(state.alpha), "beta": str(state.beta),
            "config_version": state.config_version,
            "members": sorted(members),
            "model_version": state.model_version,
            "obs_count": state.obs_count, "ref": ref}
    raw = dumps_canonical(body).encode("utf-8")
    return hashlib.sha256(STATE_TAG.encode() + b"\x00" + raw).hexdigest()


@dataclass(frozen=True)
class AggregateView:
    ref: str
    level: str  # topic | subject
    state: ConceptState = field(compare=False)
    members: tuple = ()
