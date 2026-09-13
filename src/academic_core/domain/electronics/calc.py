"""General (arbitrary-N) circuit-law computations (F8-A hardening).

F6's equation grammar (`engineering.equations.parse_equation`) only parses
fixed named-variable expressions -- it has no "sum over N terms" construct.
So a genuinely general law like `Req = sum(Ri)` cannot be a single parsed
`Equation`. This module implements it honestly instead of faking it: by
*composing* F6's own `Quantity` arithmetic and `calculate()` over the
already-declared two-term equations via associative reduction. No new math
engine, no artificial cap on N -- reduction runs for however many terms are
given (see `GENERAL_LAWS` in `electronics.equations` for the law each
function implements).
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from academic_core.domain.engineering.calc import calculate
from academic_core.domain.engineering.units import Quantity, parse_quantity
from academic_core.domain.electronics.equations import EQUATIONS

_ONE = parse_quantity("1")


class GeneralityError(ValueError):
    """A documented generality precondition (N >= 1, N >= 2, valid tap...)
    was violated by the caller -- never silently coerced."""


def series_equivalent(resistances: Sequence[Quantity]) -> Quantity:
    """Req = sum(Ri), for any N >= 1 ideal resistors (law:series-resistors)."""
    if not resistances:
        raise GeneralityError("series_equivalent needs at least one resistance")
    eq = EQUATIONS["equation:series-resistors-pair"].expression
    acc = resistances[0]
    for r in resistances[1:]:
        acc = calculate({"R1": acc, "R2": r}, eq).value
    return acc


def parallel_equivalent(resistances: Sequence[Quantity]) -> Quantity:
    """1/Req = sum(1/Ri), for any N >= 1 ideal resistors (law:parallel-resistors)."""
    if not resistances:
        raise GeneralityError("parallel_equivalent needs at least one resistance")
    if len(resistances) == 1:
        return resistances[0]
    eq = EQUATIONS["equation:parallel-resistors-pair"].expression
    acc = resistances[0]
    for r in resistances[1:]:
        acc = calculate({"R1": acc, "R2": r}, eq).value
    return acc


def current_divider(total: Quantity, resistances: Sequence[Quantity]) -> tuple[Quantity, ...]:
    """I_k = Itot * G_k / sum(G_i), G_i = 1/Ri, for any N >= 2 branches
    (law:current-divider). Returns branch currents in input order."""
    if len(resistances) < 2:
        raise GeneralityError("current_divider needs at least two branches")
    conductances = [_ONE / r for r in resistances]
    total_g = conductances[0]
    for g in conductances[1:]:
        total_g = total_g + g
    return tuple(total * (g / total_g) for g in conductances)


def voltage_divider_chain(v_in: Quantity, resistances: Sequence[Quantity], tap_after: int) -> Quantity:
    """Vout at the node just below `resistances[tap_after]` in an unloaded
    series chain of any N >= 1 resistors across v_in (law:voltage-divider).

    `tap_after` is the 0-based index of the last resistor *above* the tap;
    tap_after == len(resistances) - 1 is the node tied to the chain's low
    side (Vout == 0).
    """
    n = len(resistances)
    if n == 0:
        raise GeneralityError("voltage_divider_chain needs at least one resistance")
    if not (0 <= tap_after < n):
        raise GeneralityError(f"tap_after {tap_after} out of range for {n} resistors")
    req_total = series_equivalent(resistances)
    remaining = resistances[tap_after + 1:]
    if not remaining:
        return Quantity(Decimal(0), v_in.unit)
    req_below = series_equivalent(remaining)
    return v_in * (req_below / req_total)


__all__ = [
    "GeneralityError", "series_equivalent", "parallel_equivalent",
    "current_divider", "voltage_divider_chain",
]
