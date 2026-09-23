# SPDX-License-Identifier: MIT
"""Career / academic-status rules (F4.1, pure).

One subject is ONE entity. Where it is shown (Home "current term",
Career "approved", ...) is a *classification* of that entity, never a copy.

Canonical classification (F4.1 contract, Gestion-Academica parity):

    CURSANDO      <- state "cursando"
    APROBADA      <- state "superada"
    SUSPENDIDA    <- state "no_superada"
    NO_CURSANDO   <- state "pendiente" | "no_elegida"

The fine-grained ``Subject.state`` is kept verbatim (lossless): "pendiente"
(planned, not started) and "no_elegida" (catalogue elective not chosen) both
classify as NO_CURSANDO but remain distinguishable.

Averages mirror Gestion `media_curso` / `media_por_cuatrimestre` /
`objetivo_media` with Decimal + ROUND_HALF_UP (ADR-0011) instead of float.

No Qt. No SQLite. No I/O. No clock: "today" is always a parameter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum

from academic_core.domain.entities import DomainError, SUBJECT_STATES, Subject, Term


class AcademicStatus(str, Enum):
    CURSANDO = "CURSANDO"
    APROBADA = "APROBADA"
    SUSPENDIDA = "SUSPENDIDA"
    NO_CURSANDO = "NO_CURSANDO"


STATE_TO_STATUS: dict[str, AcademicStatus] = {
    "cursando": AcademicStatus.CURSANDO,
    "superada": AcademicStatus.APROBADA,
    "no_superada": AcademicStatus.SUSPENDIDA,
    "pendiente": AcademicStatus.NO_CURSANDO,
    "no_elegida": AcademicStatus.NO_CURSANDO,
}
# Default fine state when a caller sets a coarse status.
STATUS_TO_STATE: dict[AcademicStatus, str] = {
    AcademicStatus.CURSANDO: "cursando",
    AcademicStatus.APROBADA: "superada",
    AcademicStatus.SUSPENDIDA: "no_superada",
    AcademicStatus.NO_CURSANDO: "pendiente",
}
assert set(STATE_TO_STATUS) == set(SUBJECT_STATES)

CURRENT_TERM_STATE = "actual"


def classify(state: str) -> AcademicStatus:
    try:
        return STATE_TO_STATUS[state]
    except KeyError:
        raise DomainError(f"unknown subject state: {state!r}") from None


def resolve_state(target: str) -> str:
    """Accept either a fine state ("superada") or a coarse status
    ("APROBADA") and return the fine state to persist."""
    if target in STATE_TO_STATUS:
        return target
    try:
        return STATUS_TO_STATE[AcademicStatus(target)]
    except ValueError:
        raise DomainError(f"unknown subject state/status: {target!r}") from None


def _order_key(s: Subject) -> tuple:
    return (s.course, s.term_id, s.name.casefold(), s.stable_id)


@dataclass(frozen=True)
class CareerPartition:
    """Every subject lands in exactly one bucket (tests assert the union)."""
    current_term_ids: tuple[str, ...]
    current: tuple[Subject, ...]  # CURSANDO in a current term
    in_progress_elsewhere: tuple[Subject, ...]  # CURSANDO, term not current
    approved: tuple[Subject, ...]
    failed: tuple[Subject, ...]
    not_taken: tuple[Subject, ...]  # pendiente
    not_chosen: tuple[Subject, ...]  # no_elegida (catalogue electives)

    def all_ids(self) -> list[str]:
        out: list[str] = []
        for bucket in (self.current, self.in_progress_elsewhere, self.approved,
                       self.failed, self.not_taken, self.not_chosen):
            out.extend(s.stable_id for s in bucket)
        return out


def current_terms(terms: list[Term]) -> list[Term]:
    """Terms flagged "actual". Several may be current at once (e.g. a
    pending subject of an earlier term retaken alongside the new term)."""
    return sorted((t for t in terms if t.state == CURRENT_TERM_STATE),
                  key=lambda t: (t.academic_year_id, t.index, t.stable_id))


def partition(subjects: list[Subject], terms: list[Term]) -> CareerPartition:
    cur_ids = tuple(t.stable_id for t in current_terms(terms))
    buckets: dict[str, list[Subject]] = {k: [] for k in (
        "current", "elsewhere", "approved", "failed", "not_taken", "not_chosen")}
    for s in sorted(subjects, key=_order_key):
        st = classify(s.state)
        if st is AcademicStatus.CURSANDO:
            buckets["current" if s.term_id in cur_ids else "elsewhere"].append(s)
        elif st is AcademicStatus.APROBADA:
            buckets["approved"].append(s)
        elif st is AcademicStatus.SUSPENDIDA:
            buckets["failed"].append(s)
        elif s.state == "no_elegida":
            buckets["not_chosen"].append(s)
        else:
            buckets["not_taken"].append(s)
    return CareerPartition(cur_ids, *(tuple(buckets[k]) for k in (
        "current", "elsewhere", "approved", "failed", "not_taken", "not_chosen")))


# ----------------------------------------------------------------- averages

def _d(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _q2(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class GradedCredit:
    """(credits, current grade or None) for one chosen subject."""
    subject_id: str
    credits: Decimal
    grade: Decimal | None
    grade_state: str  # aprobada|suspendida|en_progreso|sin_evaluar


@dataclass(frozen=True)
class AverageSummary:
    """Gestion `media-curso` card."""
    weighted_by_credits: Decimal | None
    plain_mean: Decimal | None
    total: int
    approved: int
    failed: int
    pending: int
    highest: Decimal | None
    lowest: Decimal | None


def weighted_mean(pairs: list[tuple[Decimal, Decimal]]) -> Decimal | None:
    credits = sum((c for c, _ in pairs), Decimal(0))
    if credits <= 0:
        return None
    return _q2(sum((c * g for c, g in pairs), Decimal(0)) / credits)


def summarize(items: list[GradedCredit]) -> AverageSummary:
    graded = [i for i in items if i.grade is not None]
    grades = [i.grade for i in graded]
    return AverageSummary(
        weighted_by_credits=weighted_mean([(i.credits, i.grade) for i in graded]),
        plain_mean=_q2(sum(grades, Decimal(0)) / len(grades)) if grades else None,
        total=len(items),
        approved=sum(1 for i in items if i.grade_state == "aprobada"),
        failed=sum(1 for i in items if i.grade_state == "suspendida"),
        pending=sum(1 for i in items if i.grade_state in ("en_progreso", "sin_evaluar")),
        highest=max(grades) if grades else None,
        lowest=min(grades) if grades else None,
    )


@dataclass(frozen=True)
class TargetAverage:
    """Gestion `objetivo-media`: mean needed on still-ungraded credits."""
    target: Decimal | None
    current: Decimal | None
    pending_credits: Decimal
    required: Decimal | None  # clamped at 0
    reachable: bool | None  # required <= 10


def target_average(items: list[GradedCredit], target: Decimal | None) -> TargetAverage:
    graded = [(i.credits, i.grade) for i in items if i.grade is not None]
    pending = sum((i.credits for i in items if i.grade is None), Decimal(0))
    done = sum((c for c, _ in graded), Decimal(0))
    required = None
    if target is not None and pending > 0:
        points = sum((c * g for c, g in graded), Decimal(0))
        required = _q2((_d(target) * (done + pending) - points) / pending)
    return TargetAverage(
        target=_d(target) if target is not None else None,
        current=weighted_mean(graded),
        pending_credits=pending,
        required=None if required is None else max(required, Decimal("0.00")),
        reachable=None if required is None else required <= Decimal(10),
    )


# ----------------------------------------------------------- degree progress

@dataclass(frozen=True)
class ProgressBucket:
    approved: Decimal
    total: Decimal


@dataclass(frozen=True)
class DegreeProgress:
    total_credits: Decimal  # degree plan total (configured, not inferred)
    approved_credits: Decimal
    mandatory: ProgressBucket
    elective: ProgressBucket
    final_project: ProgressBucket

    @property
    def percent(self) -> Decimal:
        if self.total_credits <= 0:
            return Decimal("0.00")
        return _q2(self.approved_credits / self.total_credits * 100)


def degree_progress(subjects: list[Subject], total_credits: Decimal,
                    final_project_names: tuple[str, ...] = ()) -> DegreeProgress:
    """Gestion dashboard progress card. The plan total is data (degree
    setting), never hardcoded. The final project is ``kind == "tfg"/"tfm"``
    or a subject whose name is listed in ``final_project_names``."""
    names = {n.casefold() for n in final_project_names}

    def is_fp(s: Subject) -> bool:
        return s.kind in ("tfg", "tfm") or s.name.casefold() in names

    def credits(lst) -> Decimal:
        return sum((_d(s.credits) for s in lst), Decimal(0))

    def approved(lst) -> Decimal:
        return credits([s for s in lst if s.state == "superada"])

    fp = [s for s in subjects if is_fp(s)]
    mandatory = [s for s in subjects if s.kind == "obligatoria" and not is_fp(s)]
    electives = [s for s in subjects if s.kind == "optativa" and not is_fp(s)
                 and s.state != "no_elegida"]
    total = _d(total_credits)
    elective_total = max(total - credits(mandatory) - credits(fp), Decimal(0))
    approved_all = approved(mandatory) + approved(electives) + approved(fp)
    return DegreeProgress(total, approved_all,
                          ProgressBucket(approved(mandatory), credits(mandatory)),
                          ProgressBucket(approved(electives), elective_total),
                          ProgressBucket(approved(fp), credits(fp)))


@dataclass(frozen=True)
class StatusChange:
    subject_id: str
    before: str
    after: str
    changed: bool
    status_before: AcademicStatus = field(default=AcademicStatus.NO_CURSANDO)
    status_after: AcademicStatus = field(default=AcademicStatus.NO_CURSANDO)


def change_state(subject: Subject, target: str) -> tuple[Subject, StatusChange]:
    """Return the SAME entity (same stable_id) with a new state. Idempotent."""
    new_state = resolve_state(target)
    before = subject.state
    subject.state = new_state
    subject.__post_init__()  # re-validate invariants
    return subject, StatusChange(subject.stable_id, before, new_state,
                                 before != new_state, classify(before),
                                 classify(new_state))
