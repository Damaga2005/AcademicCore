"""MOSFET Level 1 / Shichman-Hodges model (NMOS and PMOS) for F8-K.

Transistor element: M with pins ("D", "G", "S", "B") (drain, gate, source,
bulk). The bulk is explicit: 3-terminal discrete use ties B to S in the
netlist. There is no implicit bulk.

Model parameters (via ``Component.parameters``, all required, no defaults):
    - polarity: "NMOS" | "PMOS" (string)
    - Kp: transconductance parameter (Quantity in A/V^2, > 0)
    - Vto: zero-bias threshold voltage magnitude (Quantity in volts, > 0)
    - Lambda: channel-length modulation (Quantity in 1/V, >= 0;
      ``Lambda = 0`` honestly disables it, giving infinite output resistance)
    - Phi: surface potential (Quantity in volts, >= 0)
    - Gamma: body-effect coefficient (Quantity dimensionless carrying the
      sqrt(V) magnitude, >= 0; ``Gamma = 0`` honestly disables body effect).
      The dimension registry (``units.py``) only supports integer SI
      exponent tuples, so sqrt(V) has no exact dimension entry; the
      dimensionless magnitude is validated instead (documented decision,
      see GATE-F8K-DESIGN.md).

Physics (per DESIGN §6.1). With s = +1 (NMOS) / -1 (PMOS):

    VGS = s*(VG - VS),  VDS = s*(VD - VS),  VSB = s*(VS - VB)
    Vth = Vto + Gamma*(sqrt(max(Phi + VSB, 0)) - sqrt(Phi))
    Vov = VGS - Vth                                      (overdrive)

    cutoff:     Vov <= 0                 -> ID = 0
    triode:     Vov > 0, VDS < Vov       -> ID = Kp*(Vov*VDS - VDS^2/2)*(1 + Lambda*VDS)
    saturation: Vov > 0, VDS >= Vov      -> ID = (Kp/2)*Vov^2*(1 + Lambda*VDS)

``ID`` is the signed channel current (entering the drain, leaving the
source); gate and bulk draw no DC current. VDS <= 0 with Vov > 0 is routed
to the triode branch (reverse conduction, symmetric evaluation).

All calculations use ``decimal.Decimal`` under explicit contexts. Float is
strictly forbidden. No ``exp`` is used anywhere in this model, so the only
non-finite hazards are Decimal overflow on extreme products (reported via
the standard ``Infinity`` / ``None`` contract, never clipped).
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
PARAM_KP = "Kp"
PARAM_VTO = "Vto"
PARAM_LAMBDA = "Lambda"
PARAM_PHI = "Phi"
PARAM_GAMMA = "Gamma"

REQUIRED_PARAMS = frozenset({
    PARAM_POLARITY,
    PARAM_KP,
    PARAM_VTO,
    PARAM_LAMBDA,
    PARAM_PHI,
    PARAM_GAMMA,
})

# Kp: A / V^2 = CURRENT - 2*VOLTAGE (integer SI exponents).
KP_DIM = (-2, -4, 6, 3, 0, 0, 0)
# Lambda: 1 / V.
LAMBDA_DIM = (-1, -2, 3, 1, 0, 0, 0)

REGION_CUTOFF = "cutoff"
REGION_TRIODE = "triode"
REGION_SATURATION = "saturation"


@dataclass(frozen=True)
class MOSParams:
    """Validated MOSFET Level 1 parameters as base-unit Decimal values."""

    polarity: str  # "NMOS" | "PMOS"
    Kp: Decimal    # A/V^2, > 0
    Vto: Decimal   # V, > 0 (magnitude)
    Lambda: Decimal  # 1/V, >= 0
    Phi: Decimal   # V, >= 0
    Gamma: Decimal  # sqrt(V) magnitude, dimensionless, >= 0


def _sign(polarity: str) -> Decimal:
    return Decimal(1) if polarity == "NMOS" else Decimal(-1)


def extract_mosfet_params(comp: Component) -> MOSParams:
    """Validate and extract MOSFET parameters from an M component.

    Raises ``InvalidCircuitError`` for: wrong type, non-None value,
    missing/unexpected parameters, non-Quantity values (except polarity),
    wrong dimensions, non-finite values, out-of-domain values, or a
    polarity other than NMOS/PMOS. Never invents defaults.
    """
    if comp.type.upper() != "M":
        raise InvalidCircuitError(
            f"{comp.ref}: extract_mosfet_params requires an M component, "
            f"got {comp.type!r}")
    if comp.value is not None:
        raise InvalidCircuitError(
            f"{comp.ref}: MOSFET component takes no value (must be None), "
            f"got {comp.value.format()}")

    params = dict(comp.parameters or {})
    if set(params) != REQUIRED_PARAMS:
        raise InvalidCircuitError(
            f"{comp.ref}: MOSFET needs exactly parameters "
            f"{sorted(REQUIRED_PARAMS)}, got {sorted(params)}")

    raw_pol = params[PARAM_POLARITY]
    if not isinstance(raw_pol, str) or raw_pol.upper() not in ("NMOS", "PMOS"):
        raise InvalidCircuitError(
            f"{comp.ref}: polarity must be 'NMOS' or 'PMOS', got {raw_pol!r}")
    polarity = raw_pol.upper()

    expected_dims = {
        PARAM_KP: KP_DIM,
        PARAM_VTO: VOLTAGE,
        PARAM_LAMBDA: LAMBDA_DIM,
        PARAM_PHI: VOLTAGE,
        PARAM_GAMMA: DIMENSIONLESS,
    }
    # (param, strictly-positive?): Lambda/Phi/Gamma admit exact zero.
    strict = {PARAM_KP: True, PARAM_VTO: True, PARAM_LAMBDA: False,
              PARAM_PHI: False, PARAM_GAMMA: False}
    base: dict[str, Decimal] = {}
    for key, dim in expected_dims.items():
        raw = params[key]
        if not isinstance(raw, Quantity):
            raise InvalidCircuitError(
                f"{comp.ref}: MOSFET parameter {key!r} must be a Quantity, "
                f"got {type(raw).__name__}")
        if raw.dimension != dim:
            raise InvalidCircuitError(
                f"{comp.ref}: MOSFET parameter {key!r} has wrong dimension "
                f"(got {raw.format()}, need dimension {dim})")
        val = raw.to_base()
        if not val.is_finite():
            raise InvalidCircuitError(
                f"{comp.ref}: MOSFET parameter {key!r} is non-finite "
                f"({raw.format()})")
        if strict[key] and val <= 0:
            raise InvalidCircuitError(
                f"{comp.ref}: MOSFET parameter {key!r} must be > 0, "
                f"got {raw.format()}")
        if not strict[key] and val < 0:
            raise InvalidCircuitError(
                f"{comp.ref}: MOSFET parameter {key!r} must be >= 0, "
                f"got {raw.format()}")
        base[key] = val

    return MOSParams(
        polarity=polarity,
        Kp=base[PARAM_KP],
        Vto=base[PARAM_VTO],
        Lambda=base[PARAM_LAMBDA],
        Phi=base[PARAM_PHI],
        Gamma=base[PARAM_GAMMA],
    )


def _threshold(vsb: Decimal, p: MOSParams, ctx):
    """Return ``(Vth, dVth_dVSB)``; ``None`` entries on arithmetic failure."""
    try:
        if p.Gamma == 0:
            return p.Vto, Decimal(0)
        arg = ctx.add(p.Phi, vsb)
        if arg <= 0:
            return p.Vto, Decimal(0)
        root = ctx.sqrt(arg)
        root_phi = ctx.sqrt(p.Phi) if p.Phi > 0 else Decimal(0)
        vth = ctx.add(p.Vto, ctx.multiply(p.Gamma, ctx.subtract(root, root_phi)))
        dth = ctx.divide(p.Gamma, ctx.multiply(Decimal(2), root))
        return vth, dth
    except (Overflow, InvalidOperation):
        return None, None


def mos_operating_point(
    vd: Decimal, vg: Decimal, vs: Decimal, vb: Decimal,
    p: MOSParams, ctx, trace: list | None = None,
) -> tuple[str, Decimal, Decimal, Decimal, Decimal, Decimal, Decimal] | None:
    """Region, overdrive, Vth and small-signal trio at a bias point.

    Returns ``(region, IDM, gm_mag, gds_mag, gmb_num, Vth, Vov)`` where
    ``IDM`` is the unsigned channel current, ``gm_mag = dIDM/dVGS``,
    ``gds_mag = dIDM/dVDS`` and ``gmb_num = dIDM/dVth * dVth/dVSB`` is the
    (negative) body-path numerator such that ``dId/dvb = -gmb_num``.
    ``None`` if any term is non-finite.

    E0.4: when ``trace`` is a list, ``(VGS, VDS, VSB, result)`` exactly as
    computed here is appended to it (observation only; ``None`` = inert).
    """
    try:
        s = _sign(p.polarity)
        vgs = ctx.multiply(s, ctx.subtract(vg, vs))
        vds = ctx.multiply(s, ctx.subtract(vd, vs))
        vsb = ctx.multiply(s, ctx.subtract(vs, vb))
        vth, dth = _threshold(vsb, p, ctx)
        if vth is None or dth is None:
            return None
        vov = ctx.subtract(vgs, vth)
        if vov <= 0:
            zero = Decimal(0)
            out = (REGION_CUTOFF, zero, zero, zero, zero, vth, vov)
            if trace is not None:
                trace.append((vgs, vds, vsb, out))
            return out
        lam_vds = ctx.multiply(p.Lambda, vds)
        grow = ctx.add(Decimal(1), lam_vds)
        if vds < vov:
            region = REGION_TRIODE
            core = ctx.subtract(ctx.multiply(vov, vds),
                                ctx.divide(ctx.multiply(vds, vds), Decimal(2)))
            idm = ctx.multiply(ctx.multiply(p.Kp, core), grow)
            gm_m = ctx.multiply(ctx.multiply(p.Kp, vds), grow)
            gds_m = ctx.add(
                ctx.multiply(ctx.multiply(p.Kp, ctx.subtract(vov, vds)), grow),
                ctx.multiply(ctx.multiply(p.Kp, core), p.Lambda))
        else:
            region = REGION_SATURATION
            vov2 = ctx.multiply(vov, vov)
            idm = ctx.multiply(
                ctx.multiply(ctx.divide(p.Kp, Decimal(2)), vov2), grow)
            gm_m = ctx.multiply(ctx.multiply(p.Kp, vov), grow)
            gds_m = ctx.multiply(
                ctx.multiply(ctx.divide(p.Kp, Decimal(2)), vov2), p.Lambda)
        gmb_n = ctx.multiply(ctx.minus(gm_m), dth)
        if not all(v.is_finite() for v in (idm, gm_m, gds_m, gmb_n, vth, vov)):
            return None
        out = (region, idm, gm_m, gds_m, gmb_n, vth, vov)
        if trace is not None:
            trace.append((vgs, vds, vsb, out))
        return out
    except (Overflow, InvalidOperation):
        return None


def mos_terminal_currents(
    vd: Decimal, vg: Decimal, vs: Decimal, vb: Decimal,
    p: MOSParams, ctx, trace: list | None = None,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Terminal currents entering the device ``(ID, IG, IS, IB)``.

    Gate and bulk draw no DC current. Non-finite evaluation yields
    ``Decimal('Infinity')`` entries (caller MUST check finiteness).
    """
    op = mos_operating_point(vd, vg, vs, vb, p, ctx, trace)
    if op is None:
        inf = Decimal("Infinity")
        return inf, inf, inf, inf
    _, idm, _, _, _, _, _ = op
    s = _sign(p.polarity)
    try:
        idc = ctx.multiply(s, idm)
        return idc, Decimal(0), ctx.minus(idc), Decimal(0)
    except (Overflow, InvalidOperation):
        inf = Decimal("Infinity")
        return inf, inf, inf, inf


def mos_conductances(
    vd: Decimal, vg: Decimal, vs: Decimal, vb: Decimal,
    p: MOSParams, ctx,
) -> tuple[Decimal, Decimal, Decimal] | None:
    """Small-signal trio ``(gm, gds, gmb)`` with actual-terminal meaning.

    ``gm = dID/dVG``, ``gds = dID/dVD``, ``gmb = dID/dVB`` (others held).
    ``None`` if non-finite.
    """
    op = mos_operating_point(vd, vg, vs, vb, p, ctx)
    if op is None:
        return None
    _, _, gm_m, gds_m, gmb_n, _, _ = op
    # s^2 = 1 folds the polarity out of gm/gds; gmb = -gmb_num.
    try:
        gmb = ctx.minus(gmb_n)
        if not all(v.is_finite() for v in (gm_m, gds_m, gmb)):
            return None
        return gm_m, gds_m, gmb
    except (Overflow, InvalidOperation):
        return None


def mos_jacobian(
    vd: Decimal, vg: Decimal, vs: Decimal, vb: Decimal,
    p: MOSParams, ctx, trace: list | None = None,
) -> tuple[tuple[Decimal, Decimal, Decimal, Decimal], ...] | None:
    """Analytic 4x4 Jacobian for ``(ID, IG, IS, IB)`` w.r.t. ``(VD, VG, VS, VB)``.

    Row order (D, G, S, B); gate/bulk rows are identically zero (no DC
    gate/bulk current). Source row = -(drain row) by KCL. ``None`` when
    non-finite.
    """
    op = mos_operating_point(vd, vg, vs, vb, p, ctx, trace)
    if op is None:
        return None
    try:
        _, _, gm_m, gds_m, gmb_n, _, _ = op
        s = _sign(p.polarity)
        # dIDM/dVS = -(gm + gds) - gmb_num ... via chain rule on
        # (vgs, vds, vsb): dvgs/dvs = dvds/dvs = -s, dvsb/dvs = +s.
        d_idm_dvs = ctx.add(
            ctx.multiply(ctx.add(ctx.minus(gm_m), ctx.minus(gds_m)), s),
            ctx.multiply(gmb_n, s))
        j_d = (gds_m, gm_m, ctx.multiply(s, d_idm_dvs),
               ctx.minus(gmb_n))
        j_s = tuple(ctx.minus(v) for v in j_d)
        zero4 = (Decimal(0), Decimal(0), Decimal(0), Decimal(0))
        for row in (j_d, j_s):
            for val in row:
                if not val.is_finite():
                    return None
        return (j_d, zero4, j_s, zero4)
    except (Overflow, InvalidOperation):
        return None


def mos_region(
    vd: Decimal, vg: Decimal, vs: Decimal, vb: Decimal,
    p: MOSParams, ctx,
) -> str | None:
    """Operating region name at a bias point (``None`` when non-finite)."""
    op = mos_operating_point(vd, vg, vs, vb, p, ctx)
    return None if op is None else op[0]


def mos_companion(
    vd: Decimal, vg: Decimal, vs: Decimal, vb: Decimal,
    p: MOSParams, ctx,
) -> tuple[
    tuple[Decimal, Decimal, Decimal, Decimal],
    tuple[tuple[Decimal, Decimal, Decimal, Decimal], ...] | None,
    tuple[Decimal, Decimal, Decimal, Decimal] | None,
]:
    """Linearized companion model at an operating point.

    ``I_k^(k+1) ~= sum_m (J_km * V_m^(k+1)) + I_k,eq`` with
    ``I_k,eq = I_k^(k) - sum_m (J_km * V_m^(k))``.
    """
    currents = mos_terminal_currents(vd, vg, vs, vb, p, ctx)
    jac = mos_jacobian(vd, vg, vs, vb, p, ctx)
    if not (all(i.is_finite() for i in currents) and jac is not None):
        return currents, None, None
    v_vec = (vd, vg, vs, vb)
    eq_list: list[Decimal] = []
    try:
        for row, i_curr in zip(jac, currents):
            lin = Decimal(0)
            for j_val, v_val in zip(row, v_vec):
                lin = ctx.add(lin, ctx.multiply(j_val, v_val))
            eq_list.append(ctx.subtract(i_curr, lin))
        return currents, jac, (eq_list[0], eq_list[1], eq_list[2], eq_list[3])
    except (Overflow, InvalidOperation):
        return currents, jac, None
