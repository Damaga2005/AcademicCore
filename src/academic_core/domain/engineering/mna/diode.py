"""Shockley diode model for F8-H nonlinear DC operating point.

Single certified nonlinear element:

    I = Is * (exp(Vd / (n * Vt)) - 1)

with ``Vd = V(A) - V(K)`` (anode minus cathode), ``Is > 0`` (ampere),
``n > 0`` (dimensionless), ``Vt > 0`` (volt). No defaults: all three
parameters are required explicitly as ``Quantity`` objects in the
component's ``parameters`` dict (``{"Is": ..., "n": ..., "Vt": ...}``),
validated by :func:`extract_diode_params` (dimension, finiteness,
positivity). The component carries no ``value`` (``None``, mirroring
the ideal op-amp precedent); netlist ``parameters`` are NOT serialized
(declared F8-H limitation, same AUDIT-002 class as E/G/H/F control
data — structural roundtrip only).

All numerics are ``Decimal`` under an explicit working context
(``trig.make_context``, 50 digits); ``float`` never appears. The
exponential can overflow to ``Infinity`` for extreme arguments —
evaluation helpers return the raw ``Decimal`` and callers MUST check
``is_finite()`` (see ``mna.nonlinear``: non-finite evaluation is a
``DIVERGED`` verdict, never a silent value). No clipping is applied:
limiting ``Vd`` would change the mathematics without declaration.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, Overflow

from academic_core.domain.engineering.circuit import Component
from academic_core.domain.engineering.mna.errors import InvalidCircuitError
from academic_core.domain.engineering.units import (
    CURRENT,
    DIMENSIONLESS,
    VOLTAGE,
    Quantity,
)

# Parameter keys in ``Component.parameters``.
PARAM_IS = "Is"
PARAM_N = "n"
PARAM_VT = "Vt"


@dataclass(frozen=True)
class DiodeParams:
    """Validated Shockley parameters as base-unit ``Decimal`` values."""

    Is: Decimal  # ampere, > 0
    n: Decimal  # dimensionless, > 0
    Vt: Decimal  # volt, > 0


def extract_diode_params(comp: Component) -> DiodeParams:
    """Validate and extract ``Is``/``n``/``Vt`` from a ``D`` component.

    Raises ``InvalidCircuitError`` for: missing/extra parameters,
    non-``Quantity`` values, wrong dimensions, non-finite values, or
    non-positive values. Never invents defaults.
    """
    if comp.type.upper() != "D":
        raise InvalidCircuitError(
            f"{comp.ref}: extract_diode_params needs a D component, "
            f"got {comp.type!r}")
    params = dict(comp.parameters or {})
    if set(params) != {PARAM_IS, PARAM_N, PARAM_VT}:
        raise InvalidCircuitError(
            f"{comp.ref}: diode needs exactly parameters "
            f"{sorted([PARAM_IS, PARAM_N, PARAM_VT])}, got {sorted(params)}")
    expected = {PARAM_IS: CURRENT, PARAM_N: DIMENSIONLESS, PARAM_VT: VOLTAGE}
    base: dict[str, Decimal] = {}
    for key in (PARAM_IS, PARAM_N, PARAM_VT):
        raw = params[key]
        if not isinstance(raw, Quantity):
            raise InvalidCircuitError(
                f"{comp.ref}: diode parameter {key!r} must be a Quantity, "
                f"got {type(raw).__name__}")
        if raw.dimension != expected[key]:
            raise InvalidCircuitError(
                f"{comp.ref}: diode parameter {key!r} has wrong dimension "
                f"(got {raw.format()}, need {expected[key]})")
        val = raw.to_base()
        if not val.is_finite():
            raise InvalidCircuitError(
                f"{comp.ref}: diode parameter {key!r} is non-finite "
                f"({raw.format()})")
        if val <= 0:
            raise InvalidCircuitError(
                f"{comp.ref}: diode parameter {key!r} must be > 0, "
                f"got {raw.format()}")
        base[key] = val
    return DiodeParams(Is=base[PARAM_IS], n=base[PARAM_N], Vt=base[PARAM_VT])


def shockley_current(vd: Decimal, p: DiodeParams, ctx) -> Decimal:
    """Diode current ``I = Is*(exp(Vd/(n*Vt)) - 1)`` (ampere).

    May return non-finite ``Decimal`` (``Infinity`` on exp overflow);
    the caller MUST check ``is_finite()``. No clipping is applied.
    """
    try:
        arg = ctx.divide(vd, ctx.multiply(p.n, p.Vt))
        return ctx.multiply(p.Is, ctx.subtract(ctx.exp(arg), Decimal(1)))
    except (Overflow, InvalidOperation):
        return Decimal("Infinity")


def shockley_conductance(vd: Decimal, p: DiodeParams, ctx) -> Decimal:
    """Small-signal conductance ``g = dI/dV = Is/(n*Vt)*exp(Vd/(n*Vt))``.

    Same overflow contract as :func:`shockley_current`.
    """
    try:
        arg = ctx.divide(vd, ctx.multiply(p.n, p.Vt))
        return ctx.multiply(
            ctx.divide(p.Is, ctx.multiply(p.n, p.Vt)), ctx.exp(arg))
    except (Overflow, InvalidOperation):
        return Decimal("Infinity")


def companion(vd: Decimal, p: DiodeParams, ctx
              ) -> tuple[Decimal, Decimal, Decimal]:
    """Linearized companion model ``I ~= g*Vd + Ieq`` at ``vd``.

    Returns ``(I, g, Ieq)`` with ``Ieq = I - g*Vd``. Any entry may be
    non-finite on exp overflow; the caller MUST check all three with
    ``is_finite()`` before stamping.
    """
    i_val = shockley_current(vd, p, ctx)
    g_val = shockley_conductance(vd, p, ctx)
    if not (i_val.is_finite() and g_val.is_finite()):
        inf = Decimal("Infinity")
        return (inf, inf, inf)
    try:
        ieq = ctx.subtract(i_val, ctx.multiply(g_val, vd))
    except (Overflow, InvalidOperation):
        inf = Decimal("Infinity")
        return (inf, inf, inf)
    return i_val, g_val, ieq
