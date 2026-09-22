"""F8-P5 loss ledger (NEW).

Losses are explicit labelled inputs (dB >= 0), never physical models:
atmospheric/rain/polarization/pointing/implementation/miscellaneous/
feed entries are tags on caller-supplied values. Unknown kinds
(orbital, fading, multipath, coding-gain, availability, …) are rejected
— this ledger is the scope-smuggling guard. At most 16 entries per leg.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from academic_core.domain.engineering.control.errors import ControlError, ControlStatus
from academic_core.domain.engineering.math import make_context

MAX_LOSSES = 16

ALLOWED_LOSS_KINDS = (
    "atmospheric",
    "rain",
    "polarization",
    "pointing",
    "implementation",
    "miscellaneous",
    "feed",
    "free_space_margin",
)


def _fail(status: ControlStatus, message: str) -> ControlError:
    return ControlError(status, message)


@dataclass(frozen=True)
class LossEntry:
    """One explicit loss (validation-only post-init)."""

    kind: str
    value_db: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or self.kind.strip() not in ALLOWED_LOSS_KINDS:
            raise _fail(ControlStatus.INVALID,
                        "loss kind must be one of " + ",".join(ALLOWED_LOSS_KINDS))
        if isinstance(self.value_db, bool) or not isinstance(self.value_db, Decimal):
            raise _fail(ControlStatus.INVALID, "loss value must be Decimal dB")
        if not self.value_db.is_finite() or self.value_db < 0:
            raise _fail(ControlStatus.INVALID, "loss value must be finite dB >= 0")

    @staticmethod
    def create(kind: str, value_db: object) -> "LossEntry":
        if not isinstance(kind, str):
            raise _fail(ControlStatus.INVALID, "loss kind must be a string")
        if isinstance(value_db, bool):
            raise _fail(ControlStatus.INVALID, "loss value rejects bool")
        if isinstance(value_db, Decimal):
            val = value_db
        elif isinstance(value_db, int):
            val = Decimal(value_db)
        elif isinstance(value_db, str):
            try:
                val = Decimal(value_db.strip())
            except Exception as exc:
                raise _fail(ControlStatus.INVALID, "bad loss string") from exc
        else:
            raise _fail(ControlStatus.INVALID, "loss value must be Decimal/int/str")
        return LossEntry(kind=kind.strip(), value_db=val)


def total_loss_db(entries: object) -> Decimal:
    """Exact sum of a loss ledger (tuple/list, 0..16 entries)."""
    if not isinstance(entries, (tuple, list)):
        raise _fail(ControlStatus.INVALID, "loss ledger must be a tuple/list")
    if len(entries) > MAX_LOSSES:
        raise _fail(ControlStatus.INVALID, "loss budget exceeded (16 max)")
    ctx = make_context()
    total = Decimal(0)
    for entry in entries:
        if not isinstance(entry, LossEntry):
            raise _fail(ControlStatus.INVALID, "ledger entries must be LossEntry")
        total = ctx.add(total, entry.value_db)
    return total
