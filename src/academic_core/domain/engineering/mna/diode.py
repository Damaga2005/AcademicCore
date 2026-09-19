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


# ---------------------------------------------------------------------------
# F8-K diode-kind variants (Zener, LED, Schottky, photodiode).
#
# All variants reuse the letter ``D`` (SPICE convention: every two-terminal
# junction is a diode with a distinct model card) and are discriminated by a
# required string parameter ``kind``. RECT is the F8-H Shockley diode
# bit-for-bit: ``variant_current``/``variant_conductance`` with kind RECT
# delegate to :func:`shockley_current`/:func:`shockley_conductance`.
#
# DESIGN DEVIATION-01 (documented in GATE-F8K.md): the Zener reverse branch
# is formulated as
#     I = Is*(exp(Vd/(n*Vt)) - 1) - Iz*(exp(-(Vd+Vz)/(nz*Vt)) - exp(-Vz/(nz*Vt)))
# for Vd < 0 (pure Shockley for Vd >= 0), instead of the design draft
# ``-Is - Iz*(exp(-(Vd+Vz)/(nz*Vt)) - 1)``. The draft jumps by ~Iz at Vd = 0
# (its reverse limit is ``-Is + Iz`` while forward gives exactly 0); the
# implemented form is C0-continuous (both branches give exactly 0 at Vd = 0)
# and C1-continuous up to the negligible ``exp(-Vz/(nz*Vt))`` term, while
# keeping identical parameters, regions, breakdown growth and emergent
# dynamic resistance. Same overflow contract (non-finite on exp overflow).
# ---------------------------------------------------------------------------

PARAM_KIND = "kind"

KIND_RECT = "RECT"
KIND_ZENER = "ZENER"
KIND_LED = "LED"
KIND_SCHOTTKY = "SCHOTTKY"
KIND_PHOTO = "PHOTO"

DIODE_KINDS = frozenset({KIND_RECT, KIND_ZENER, KIND_LED, KIND_SCHOTTKY,
                         KIND_PHOTO})

PARAM_VZ = "Vz"
PARAM_NZ = "nz"
PARAM_IZ = "Iz"
PARAM_IPH = "Iph"


@dataclass(frozen=True)
class DiodeVariantParams:
    """Validated diode-kind parameters as base-unit ``Decimal`` values."""

    kind: str  # one of DIODE_KINDS
    Is: Decimal  # ampere, > 0
    n: Decimal  # dimensionless, > 0
    Vt: Decimal  # volt, > 0
    Vz: Decimal | None = None  # volt, > 0 (ZENER only)
    nz: Decimal | None = None  # dimensionless, > 0 (ZENER only)
    Iz: Decimal | None = None  # ampere, > 0 (ZENER only)
    Iph: Decimal | None = None  # ampere, >= 0 (PHOTO only)

    def as_shockley(self) -> DiodeParams:
        """Shared Shockley triple (every kind carries it)."""
        return DiodeParams(Is=self.Is, n=self.n, Vt=self.Vt)


def _validate_base_quantity(comp: Component, key: str, dim) -> Decimal:
    raw = comp.parameters[key]
    if not isinstance(raw, Quantity):
        raise InvalidCircuitError(
            f"{comp.ref}: diode parameter {key!r} must be a Quantity, "
            f"got {type(raw).__name__}")
    if raw.dimension != dim:
        raise InvalidCircuitError(
            f"{comp.ref}: diode parameter {key!r} has wrong dimension "
            f"(got {raw.format()}, need {dim})")
    val = raw.to_base()
    if not val.is_finite():
        raise InvalidCircuitError(
            f"{comp.ref}: diode parameter {key!r} is non-finite "
            f"({raw.format()})")
    return val


def extract_diode_variant_params(comp: Component) -> DiodeVariantParams:
    """Validate and extract diode-kind parameters from a ``D`` component.

    Requires an exact per-kind parameter set (plus ``kind`` itself):

    * RECT / LED / SCHOTTKY: ``{kind, Is, n, Vt}``
    * ZENER: ``{kind, Is, n, Vt, Vz, nz, Iz}``
    * PHOTO: ``{kind, Is, n, Vt, Iph}``

    LED and SCHOTTKY share the Shockley positivity/domain validation with
    RECT (they ARE Shockley physics with application domains); the ``kind``
    tag records the intended application. No silent defaults, no magic
    ranges. Raises ``InvalidCircuitError`` otherwise.
    """
    if comp.type.upper() != "D":
        raise InvalidCircuitError(
            f"{comp.ref}: extract_diode_variant_params needs a D component, "
            f"got {comp.type!r}")
    params = dict(comp.parameters or {})
    raw_kind = params.get(PARAM_KIND)
    if not isinstance(raw_kind, str) or raw_kind.upper() not in DIODE_KINDS:
        raise InvalidCircuitError(
            f"{comp.ref}: diode parameter 'kind' must be one of "
            f"{sorted(DIODE_KINDS)}, got {raw_kind!r}")
    kind = raw_kind.upper()

    want = {PARAM_KIND, PARAM_IS, PARAM_N, PARAM_VT}
    if kind == KIND_ZENER:
        want |= {PARAM_VZ, PARAM_NZ, PARAM_IZ}
    elif kind == KIND_PHOTO:
        want |= {PARAM_IPH}
    if set(params) != want:
        raise InvalidCircuitError(
            f"{comp.ref}: diode kind {kind} needs exactly parameters "
            f"{sorted(want)}, got {sorted(params)}")

    is_v = _validate_base_quantity(comp, PARAM_IS, CURRENT)
    n_v = _validate_base_quantity(comp, PARAM_N, DIMENSIONLESS)
    vt_v = _validate_base_quantity(comp, PARAM_VT, VOLTAGE)
    if is_v <= 0 or n_v <= 0 or vt_v <= 0:
        raise InvalidCircuitError(
            f"{comp.ref}: diode parameters Is/n/Vt must be > 0")

    vz_v: Decimal | None = None
    nz_v: Decimal | None = None
    iz_v: Decimal | None = None
    iph_v: Decimal | None = None
    if kind == KIND_ZENER:
        vz_v = _validate_base_quantity(comp, PARAM_VZ, VOLTAGE)
        nz_v = _validate_base_quantity(comp, PARAM_NZ, DIMENSIONLESS)
        iz_v = _validate_base_quantity(comp, PARAM_IZ, CURRENT)
        if vz_v <= 0 or nz_v <= 0 or iz_v <= 0:
            raise InvalidCircuitError(
                f"{comp.ref}: Zener parameters Vz/nz/Iz must be > 0")
    if kind == KIND_PHOTO:
        iph_v = _validate_base_quantity(comp, PARAM_IPH, CURRENT)
        if iph_v < 0:
            raise InvalidCircuitError(
                f"{comp.ref}: photodiode parameter Iph must be >= 0")

    return DiodeVariantParams(kind=kind, Is=is_v, n=n_v, Vt=vt_v,
                              Vz=vz_v, nz=nz_v, Iz=iz_v, Iph=iph_v)


def variant_current(vd: Decimal, p: DiodeVariantParams, ctx) -> Decimal:
    """Diode-kind current (ampere).

    * RECT / LED / SCHOTTKY: pure Shockley.
    * ZENER: Shockley for ``Vd >= 0``; Shockley minus the breakdown term
      for ``Vd < 0`` (see DEVIATION-01 above).
    * PHOTO: Shockley minus ``Iph`` (``Iph = 0`` is exact darkness).

    May return non-finite ``Decimal`` on exp overflow; caller MUST check.
    """
    if p.kind in (KIND_RECT, KIND_LED, KIND_SCHOTTKY):
        return shockley_current(vd, p.as_shockley(), ctx)
    if p.kind == KIND_PHOTO:
        assert p.Iph is not None
        try:
            base = shockley_current(vd, p.as_shockley(), ctx)
            return ctx.subtract(base, p.Iph)
        except (Overflow, InvalidOperation):
            return Decimal("Infinity")
    if p.kind == KIND_ZENER:
        assert p.Vz is not None and p.nz is not None and p.Iz is not None
        try:
            fwd = shockley_current(vd, p.as_shockley(), ctx)
            if vd >= 0:
                return fwd
            nzv = ctx.multiply(p.nz, p.Vt)
            arg_now = ctx.divide(ctx.minus(ctx.add(vd, p.Vz)), nzv)
            arg_ref = ctx.divide(ctx.minus(p.Vz), nzv)
            brk = ctx.multiply(p.Iz, ctx.subtract(ctx.exp(arg_now),
                                                  ctx.exp(arg_ref)))
            return ctx.subtract(fwd, brk)
        except (Overflow, InvalidOperation):
            return Decimal("Infinity")
    raise InvalidCircuitError(f"unknown diode kind: {p.kind!r}")


def variant_conductance(vd: Decimal, p: DiodeVariantParams, ctx) -> Decimal:
    """Diode-kind dynamic conductance ``g = dI/dVd`` (siemens).

    Same branch structure as :func:`variant_current`. May return
    non-finite ``Decimal`` on exp overflow; caller MUST check.
    """
    if p.kind in (KIND_RECT, KIND_LED, KIND_SCHOTTKY):
        return shockley_conductance(vd, p.as_shockley(), ctx)
    if p.kind == KIND_PHOTO:
        return shockley_conductance(vd, p.as_shockley(), ctx)
    if p.kind == KIND_ZENER:
        assert p.Vz is not None and p.nz is not None and p.Iz is not None
        try:
            g_fwd = shockley_conductance(vd, p.as_shockley(), ctx)
            if vd >= 0:
                return g_fwd
            nzv = ctx.multiply(p.nz, p.Vt)
            arg_now = ctx.divide(ctx.minus(ctx.add(vd, p.Vz)), nzv)
            g_brk = ctx.multiply(ctx.divide(p.Iz, nzv), ctx.exp(arg_now))
            return ctx.add(g_fwd, g_brk)
        except (Overflow, InvalidOperation):
            return Decimal("Infinity")
    raise InvalidCircuitError(f"unknown diode kind: {p.kind!r}")


def variant_companion(vd: Decimal, p: DiodeVariantParams, ctx
                      ) -> tuple[Decimal, Decimal, Decimal]:
    """Linearized companion model ``I ~= g*Vd + Ieq`` for a diode kind.

    Returns ``(I, g, Ieq)`` with ``Ieq = I - g*Vd``. Any entry may be
    non-finite on exp overflow; the caller MUST check all three with
    ``is_finite()`` before stamping.
    """
    i_val = variant_current(vd, p, ctx)
    g_val = variant_conductance(vd, p, ctx)
    if not (i_val.is_finite() and g_val.is_finite()):
        inf = Decimal("Infinity")
        return (inf, inf, inf)
    try:
        ieq = ctx.subtract(i_val, ctx.multiply(g_val, vd))
    except (Overflow, InvalidOperation):
        inf = Decimal("Infinity")
        return (inf, inf, inf)
    return i_val, g_val, ieq
