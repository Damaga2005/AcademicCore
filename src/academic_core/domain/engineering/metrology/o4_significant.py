"""F8-O O4 significant figures (NEW, pure presentation view).

GUM JCGM 100 §7.2 view rule implemented as a fixed deterministic rule:
the expanded uncertainty ``U`` is rounded to **2 significant figures** and
the measurand value ``y`` is rounded to the decade of the rounded ``U``.
Stored scientific values are never modified; the rounded strings must
never feed back into calculations. Pure ``Decimal`` string arithmetic —
no float, no I/O, no randomness.

Reuse: NEW (grep-proven: no significant-figures implementation exists).
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from academic_core.domain.engineering.metrology.errors import (
    MetrologyError,
    MetrologyStatus,
)

_SIGNIFICANT_DIGITS = 2


def _check_finite(value: Decimal, label: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, Decimal) or not value.is_finite():
        raise MetrologyError(MetrologyStatus.INVALID, f"{label} must be a finite Decimal")
    return value


def _quantize_to_decade(value: Decimal, decade: int) -> Decimal:
    quantum = Decimal(1).scaleb(decade)
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def format_uncertainty(expanded: Decimal) -> str:
    """Round ``U`` to 2 significant figures, returned via ``str()``.

    ``U < 0`` is INVALID; ``U == 0`` renders ``"0"`` exactly. Uses
    ``ROUND_HALF_UP`` (fixed, documented; ties never depend on context).
    """
    u = _check_finite(expanded, "expanded uncertainty")
    if u < 0:
        raise MetrologyError(MetrologyStatus.INVALID, "expanded uncertainty must be non-negative")
    if u == 0:
        return "0"
    magnitude = u.copy_abs().adjusted()
    decade = magnitude - (_SIGNIFICANT_DIGITS - 1)
    return str(_quantize_to_decade(u, decade))


def format_result(value: Decimal, expanded: Decimal) -> tuple[str, str]:
    """Round ``(y, U)`` for display: ``U`` to 2 s.f., ``y`` to ``U``'s decade.

    Returns ``(y_str, U_str)``. The first element tracks the rounded
    uncertainty decade exactly (``y`` and ``U`` share their last place —
    the GUM §7 presentation invariant, tested).
    """
    y = _check_finite(value, "measurand value")
    u = _check_finite(expanded, "expanded uncertainty")
    if u < 0:
        raise MetrologyError(MetrologyStatus.INVALID, "expanded uncertainty must be non-negative")
    if u == 0:
        return str(y), "0"
    u_str = format_uncertainty(u)
    decade = Decimal(u_str).copy_abs().adjusted() - (_SIGNIFICANT_DIGITS - 1)
    return str(_quantize_to_decade(y, decade)), u_str


def display_decade(expanded: Decimal) -> int:
    """Decade (power of ten) of the last displayed digit of rounded ``U``."""
    u = _check_finite(expanded, "expanded uncertainty")
    if u < 0:
        raise MetrologyError(MetrologyStatus.INVALID, "expanded uncertainty must be non-negative")
    if u == 0:
        return 0
    return u.copy_abs().adjusted() - (_SIGNIFICANT_DIGITS - 1)
