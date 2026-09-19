"""JFET square-law model (N-channel and P-channel) for F8-K.

Transistor element: J with pins ("D", "G", "S") (drain, gate, source).

Model parameters (via ``Component.parameters``, all required, no defaults):
    - polarity: "NCHAN" | "PCHAN" (string)
    - Idss: zero-gate saturation current (Quantity in amperes, > 0)
    - Vp: pinch-off voltage magnitude (Quantity in volts, > 0)
    - Lambda: channel-length modulation (Quantity in 1/V, >= 0;
      ``Lambda = 0`` honestly disables it)

Physics (per DESIGN §6.2). With s = +1 (NCHAN) / -1 (PCHAN):

    VGS = s*(VG - VS),  VDS = s*(VD - VS)

    cutoff:     VGS <= -Vp              -> ID = 0
    triode:     VGS > -Vp, VDS < VGS+Vp -> ID = Idss*(2*(1+VGS/Vp)*(VDS/Vp) - (VDS/Vp)^2)*(1 + Lambda*VDS)
    saturation: VGS > -Vp, VDS >= VGS+Vp-> ID = Idss*(1 + VGS/Vp)^2*(1 + Lambda*VDS)

``ID`` is the signed channel current (entering the drain); the gate draws
no DC current. The region predicate keeps the model C0-continuous at the
cutoff boundary (near ``VGS = -Vp`` any macroscopic ``VDS > 0`` falls in
saturation, where ``ID -> 0``). ``VDS <= 0`` with ``VGS > -Vp`` is routed to
the triode branch (reverse conduction, symmetric evaluation).

No ``exp`` is used: the only non-finite hazards are Decimal overflow on
extreme products (standard ``Infinity`` / ``None`` contract, never clipped).
All calculations use ``decimal.Decimal`` under explicit contexts. Float is
strictly forbidden.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, Overflow

from academic_core.domain.engineering.circuit import Component
from academic_core.domain.engineering.mna.errors import InvalidCircuitError
from academic_core.domain.engineering.math.trig import make_context
from academic_core.domain.engineering.units import (
    CURRENT,
    DIMENSIONLESS,
    VOLTAGE,
    Quantity,
)

PARAM_POLARITY = "polarity"
PARAM_IDSS = "Idss"
PARAM_VP = "Vp"
PARAM_LAMBDA = "Lambda"

REQUIRED_PARAMS = frozenset({
    PARAM_POLARITY,
    PARAM_IDSS,
    PARAM_VP,
    PARAM_LAMBDA,
})

# Lambda: 1 / V (integer SI exponents).
LAMBDA_DIM = (-1, -2, 3, 1, 0, 0, 0)

REGION_CUTOFF = "cutoff"
REGION_TRIODE = "triode"
REGION_SATURATION = "saturation"


@dataclass(frozen=True)
class JFETParams:
    """Validated JFET square-law parameters as base-unit Decimal values."""

    polarity: str  # "NCHAN" | "PCHAN"
    Idss: Decimal  # A, > 0
    Vp: Decimal    # V, > 0 (magnitude)
    Lambda: Decimal  # 1/V, >= 0


def _sign(polarity: str) -> Decimal:
    return Decimal(1) if polarity == "NCHAN" else Decimal(-1)


def extract_jfet_params(comp: Component) -> JFETParams:
    """Validate and extract JFET parameters from a J component.

    Raises ``InvalidCircuitError`` for: wrong type, non-None value,
    missing/unexpected parameters, non-Quantity values (except polarity),
    wrong dimensions, non-finite values, out-of-domain values, or a
    polarity other than NCHAN/PCHAN. Never invents defaults.
    """
    if comp.type.upper() != "J":
        raise InvalidCircuitError(
            f"{comp.ref}: extract_jfet_params requires a J component, "
            f"got {comp.type!r}")
    if comp.value is not None:
        raise InvalidCircuitError(
            f"{comp.ref}: JFET component takes no value (must be None), "
            f"got {comp.value.format()}")

    params = dict(comp.parameters or {})
    if set(params) != REQUIRED_PARAMS:
        raise InvalidCircuitError(
            f"{comp.ref}: JFET needs exactly parameters "
            f"{sorted(REQUIRED_PARAMS)}, got {sorted(params)}")

    raw_pol = params[PARAM_POLARITY]
    if not isinstance(raw_pol, str) or raw_pol.upper() not in ("NCHAN", "PCHAN"):
        raise InvalidCircuitError(
            f"{comp.ref}: polarity must be 'NCHAN' or 'PCHAN', "
            f"got {raw_pol!r}")
    polarity = raw_pol.upper()

    expected_dims = {
        PARAM_IDSS: CURRENT,
        PARAM_VP: VOLTAGE,
        PARAM_LAMBDA: LAMBDA_DIM,
    }
    strict = {PARAM_IDSS: True, PARAM_VP: True, PARAM_LAMBDA: False}
    base: dict[str, Decimal] = {}
    for key, dim in expected_dims.items():
        raw = params[key]
        if not isinstance(raw, Quantity):
            raise InvalidCircuitError(
                f"{comp.ref}: JFET parameter {key!r} must be a Quantity, "
                f"got {type(raw).__name__}")
        if raw.dimension != dim:
            raise InvalidCircuitError(
                f"{comp.ref}: JFET parameter {key!r} has wrong dimension "
                f"(got {raw.format()}, need dimension {dim})")
        val = raw.to_base()
        if not val.is_finite():
            raise InvalidCircuitError(
                f"{comp.ref}: JFET parameter {key!r} is non-finite "
                f"({raw.format()})")
        if strict[key] and val <= 0:
            raise InvalidCircuitError(
                f"{comp.ref}: JFET parameter {key!r} must be > 0, "
                f"got {raw.format()}")
        if not strict[key] and val < 0:
            raise InvalidCircuitError(
                f"{comp.ref}: JFET parameter {key!r} must be >= 0, "
                f"got {raw.format()}")
        base[key] = val

    return JFETParams(
        polarity=polarity,
        Idss=base[PARAM_IDSS],
        Vp=base[PARAM_VP],
        Lambda=base[PARAM_LAMBDA],
    )


def jfet_operating_point(
    vd: Decimal, vg: Decimal, vs: Decimal,
    p: JFETParams, ctx,
) -> tuple[str, Decimal, Decimal, Decimal] | None:
    """Region, unsigned channel current and small-signal pair at a bias point.

    Returns ``(region, IDM, gm_mag, gds_mag)`` with ``gm_mag = dIDM/dVGS``
    and ``gds_mag = dIDM/dVDS``. ``None`` if any term is non-finite.
    """
    try:
        s = _sign(p.polarity)
        vgs = ctx.multiply(s, ctx.subtract(vg, vs))
        vds = ctx.multiply(s, ctx.subtract(vd, vs))
        neg_vp = ctx.minus(p.Vp)
        if vgs <= neg_vp:
            zero = Decimal(0)
            return (REGION_CUTOFF, zero, zero, zero)
        a = ctx.add(Decimal(1), ctx.divide(vgs, p.Vp))
        grow = ctx.add(Decimal(1), ctx.multiply(p.Lambda, vds))
        edge = ctx.add(vgs, p.Vp)
        if vds < edge:
            region = REGION_TRIODE
            b = ctx.divide(vds, p.Vp)
            core = ctx.subtract(
                ctx.multiply(ctx.multiply(Decimal(2), a), b),
                ctx.multiply(b, b))
            idm = ctx.multiply(ctx.multiply(p.Idss, core), grow)
            gm_m = ctx.multiply(
                ctx.multiply(p.Idss, ctx.divide(
                    ctx.multiply(Decimal(2), b), p.Vp)), grow)
            # d/dVDS of Idss*(2*a*b - b^2)*grow with a VDS-independent:
            # Idss*(2*(a-b)/Vp)*grow + Idss*core*Lambda.
            two_a_minus_b = ctx.multiply(Decimal(2), ctx.subtract(a, b))
            gds_m = ctx.add(
                ctx.multiply(ctx.multiply(p.Idss, ctx.divide(two_a_minus_b,
                                                             p.Vp)),
                             grow),
                ctx.multiply(ctx.multiply(p.Idss, core), p.Lambda))
        else:
            region = REGION_SATURATION
            a2 = ctx.multiply(a, a)
            idm = ctx.multiply(ctx.multiply(p.Idss, a2), grow)
            gm_m = ctx.multiply(
                ctx.multiply(p.Idss, ctx.divide(
                    ctx.multiply(Decimal(2), a), p.Vp)), grow)
            gds_m = ctx.multiply(ctx.multiply(p.Idss, a2), p.Lambda)
        if not all(v.is_finite() for v in (idm, gm_m, gds_m)):
            return None
        return (region, idm, gm_m, gds_m)
    except (Overflow, InvalidOperation):
        return None


def jfet_terminal_currents(
    vd: Decimal, vg: Decimal, vs: Decimal,
    p: JFETParams, ctx,
) -> tuple[Decimal, Decimal, Decimal]:
    """Terminal currents entering the device ``(ID, IG, IS)``.

    The gate draws no DC current. Non-finite evaluation yields
    ``Decimal('Infinity')`` entries (caller MUST check finiteness).
    """
    op = jfet_operating_point(vd, vg, vs, p, ctx)
    if op is None:
        inf = Decimal("Infinity")
        return inf, inf, inf
    _, idm, _, _ = op
    s = _sign(p.polarity)
    try:
        idc = ctx.multiply(s, idm)
        return idc, Decimal(0), ctx.minus(idc)
    except (Overflow, InvalidOperation):
        inf = Decimal("Infinity")
        return inf, inf, inf


def jfet_conductances(
    vd: Decimal, vg: Decimal, vs: Decimal,
    p: JFETParams, ctx,
) -> tuple[Decimal, Decimal] | None:
    """Small-signal pair ``(gm, gds)`` with actual-terminal meaning.

    ``gm = dID/dVG``, ``gds = dID/dVD`` (others held). ``None`` if
    non-finite.
    """
    op = jfet_operating_point(vd, vg, vs, p, ctx)
    if op is None:
        return None
    _, _, gm_m, gds_m = op
    # s^2 = 1 folds the polarity out of both derivatives.
    if not (gm_m.is_finite() and gds_m.is_finite()):
        return None
    return gm_m, gds_m


def jfet_jacobian(
    vd: Decimal, vg: Decimal, vs: Decimal,
    p: JFETParams, ctx,
) -> tuple[tuple[Decimal, Decimal, Decimal], ...] | None:
    """Analytic 3x3 Jacobian for ``(ID, IG, IS)`` w.r.t. ``(VD, VG, VS)``.

    Row order (D, G, S); the gate row is identically zero; the source row
    is -(drain row) by KCL. ``None`` when non-finite.
    """
    op = jfet_operating_point(vd, vg, vs, p, ctx)
    if op is None:
        return None
    try:
        _, _, gm_m, gds_m = op
        j_d = (gds_m, gm_m, ctx.minus(ctx.add(gm_m, gds_m)))
        j_s = tuple(ctx.minus(v) for v in j_d)
        zero3 = (Decimal(0), Decimal(0), Decimal(0))
        for row in (j_d, j_s):
            for val in row:
                if not val.is_finite():
                    return None
        return (j_d, zero3, j_s)
    except (Overflow, InvalidOperation):
        return None


def jfet_region(
    vd: Decimal, vg: Decimal, vs: Decimal,
    p: JFETParams, ctx,
) -> str | None:
    """Operating region name at a bias point (``None`` when non-finite)."""
    op = jfet_operating_point(vd, vg, vs, p, ctx)
    return None if op is None else op[0]


def jfet_companion(
    vd: Decimal, vg: Decimal, vs: Decimal,
    p: JFETParams, ctx,
) -> tuple[
    tuple[Decimal, Decimal, Decimal],
    tuple[tuple[Decimal, Decimal, Decimal], ...] | None,
    tuple[Decimal, Decimal, Decimal] | None,
]:
    """Linearized companion model at an operating point.

    ``I_k^(k+1) ~= sum_m (J_km * V_m^(k+1)) + I_k,eq`` with
    ``I_k,eq = I_k^(k) - sum_m (J_km * V_m^(k))``.
    """
    currents = jfet_terminal_currents(vd, vg, vs, p, ctx)
    jac = jfet_jacobian(vd, vg, vs, p, ctx)
    if not (all(i.is_finite() for i in currents) and jac is not None):
        return currents, None, None
    v_vec = (vd, vg, vs)
    eq_list: list[Decimal] = []
    try:
        for row, i_curr in zip(jac, currents):
            lin = Decimal(0)
            for j_val, v_val in zip(row, v_vec):
                lin = ctx.add(lin, ctx.multiply(j_val, v_val))
            eq_list.append(ctx.subtract(i_curr, lin))
        return currents, jac, (eq_list[0], eq_list[1], eq_list[2])
    except (Overflow, InvalidOperation):
        return currents, jac, None
