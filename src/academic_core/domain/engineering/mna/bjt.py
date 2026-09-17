"""Ebers-Moll BJT model (NPN and PNP) for F8-I nonlinear DC operating point.

Transistor element: Q with pins ("C", "B", "E") (collector, base, emitter).
Model parameters (passed via `Component.parameters`):
    - polarity: "NPN" | "PNP" (string)
    - Is: transport saturation current (Quantity in amperes, > 0)
    - Bf: ideal forward maximum current gain (Quantity dimensionless, > 0)
    - Br: ideal reverse maximum current gain (Quantity dimensionless, > 0)
    - Nf: forward current ideality factor (Quantity dimensionless, > 0)
    - Nr: reverse current ideality factor (Quantity dimensionless, > 0)
    - Vt: thermal voltage k*T/q (Quantity in volts, > 0)

All calculations use Python `decimal.Decimal` under explicit contexts.
Float is strictly forbidden in physics and solver evaluation.
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
PARAM_IS = "Is"
PARAM_BF = "Bf"
PARAM_BR = "Br"
PARAM_NF = "Nf"
PARAM_NR = "Nr"
PARAM_VT = "Vt"

REQUIRED_PARAMS = frozenset({
    PARAM_POLARITY,
    PARAM_IS,
    PARAM_BF,
    PARAM_BR,
    PARAM_NF,
    PARAM_NR,
    PARAM_VT,
})


@dataclass(frozen=True)
class BJTParams:
    """Validated Ebers-Moll BJT parameters as base-unit Decimal values."""

    polarity: str  # "NPN" | "PNP"
    Is: Decimal    # ampere, > 0
    Bf: Decimal    # dimensionless, > 0
    Br: Decimal    # dimensionless, > 0
    Nf: Decimal    # dimensionless, > 0
    Nr: Decimal    # dimensionless, > 0
    Vt: Decimal    # volt, > 0
    alphaF: Decimal  # Bf / (Bf + 1)
    alphaR: Decimal  # Br / (Br + 1)


def extract_bjt_params(comp: Component) -> BJTParams:
    """Validate and extract BJT parameters from a Q component.

    Raises `InvalidCircuitError` if:
    - Component is not type 'Q'
    - Component has a non-None value
    - Missing or unexpected parameters
    - Parameters are not Quantity instances (except polarity which is str)
    - Wrong dimensions, non-finite values, or non-positive values
    - polarity is not 'NPN' or 'PNP'
    Never invents defaults.
    """
    if comp.type.upper() != "Q":
        raise InvalidCircuitError(
            f"{comp.ref}: extract_bjt_params requires a Q component, got {comp.type!r}")
    if comp.value is not None:
        raise InvalidCircuitError(
            f"{comp.ref}: BJT component takes no value (must be None), got {comp.value.format()}")

    params = dict(comp.parameters or {})
    if set(params) != REQUIRED_PARAMS:
        raise InvalidCircuitError(
            f"{comp.ref}: BJT needs exactly parameters {sorted(REQUIRED_PARAMS)}, "
            f"got {sorted(params)}")

    raw_pol = params[PARAM_POLARITY]
    if not isinstance(raw_pol, str) or raw_pol.upper() not in ("NPN", "PNP"):
        raise InvalidCircuitError(
            f"{comp.ref}: polarity must be 'NPN' or 'PNP', got {raw_pol!r}")
    polarity = raw_pol.upper()

    expected_dims = {
        PARAM_IS: CURRENT,
        PARAM_BF: DIMENSIONLESS,
        PARAM_BR: DIMENSIONLESS,
        PARAM_NF: DIMENSIONLESS,
        PARAM_NR: DIMENSIONLESS,
        PARAM_VT: VOLTAGE,
    }

    base: dict[str, Decimal] = {}
    for key, dim in expected_dims.items():
        raw = params[key]
        if not isinstance(raw, Quantity):
            raise InvalidCircuitError(
                f"{comp.ref}: BJT parameter {key!r} must be a Quantity, got {type(raw).__name__}")
        if raw.dimension != dim:
            raise InvalidCircuitError(
                f"{comp.ref}: BJT parameter {key!r} has wrong dimension (got {raw.format()}, need {dim})")
        val = raw.to_base()
        if not val.is_finite():
            raise InvalidCircuitError(
                f"{comp.ref}: BJT parameter {key!r} is non-finite ({raw.format()})")
        if val <= 0:
            raise InvalidCircuitError(
                f"{comp.ref}: BJT parameter {key!r} must be > 0, got {raw.format()}")
        base[key] = val

    ctx = make_context()
    bf = base[PARAM_BF]
    br = base[PARAM_BR]
    alpha_f = ctx.divide(bf, ctx.add(bf, Decimal(1)))
    alpha_r = ctx.divide(br, ctx.add(br, Decimal(1)))

    return BJTParams(
        polarity=polarity,
        Is=base[PARAM_IS],
        Bf=bf,
        Br=br,
        Nf=base[PARAM_NF],
        Nr=base[PARAM_NR],
        Vt=base[PARAM_VT],
        alphaF=alpha_f,
        alphaR=alpha_r,
    )


def bjt_injection_currents(
    vc: Decimal, vb: Decimal, ve: Decimal, p: BJTParams, ctx
) -> tuple[Decimal, Decimal]:
    """Calculate diode injection currents (IF, IR).

    For NPN:
        V_F = VBE = VB - VE
        V_R = VBC = VB - VC
    For PNP:
        V_F = VEB = VE - VB
        V_R = VCB = VC - VB

    IF = Is * (exp(V_F / (Nf * Vt)) - 1)
    IR = Is * (exp(V_R / (Nr * Vt)) - 1)

    Returns (IF, IR). May return Decimal("Infinity") on overflow.
    """
    if p.polarity == "NPN":
        vf = ctx.subtract(vb, ve)
        vr = ctx.subtract(vb, vc)
    else:  # PNP
        vf = ctx.subtract(ve, vb)
        vr = ctx.subtract(vc, vb)

    try:
        arg_f = ctx.divide(vf, ctx.multiply(p.Nf, p.Vt))
        if_val = ctx.multiply(p.Is, ctx.subtract(ctx.exp(arg_f), Decimal(1)))
    except (Overflow, InvalidOperation):
        if_val = Decimal("Infinity")

    try:
        arg_r = ctx.divide(vr, ctx.multiply(p.Nr, p.Vt))
        ir_val = ctx.multiply(p.Is, ctx.subtract(ctx.exp(arg_r), Decimal(1)))
    except (Overflow, InvalidOperation):
        ir_val = Decimal("Infinity")

    return if_val, ir_val


def bjt_terminal_currents(
    vc: Decimal, vb: Decimal, ve: Decimal, p: BJTParams, ctx
) -> tuple[Decimal, Decimal, Decimal]:
    """Terminal currents entering the device (IC, IB, IE).

    For NPN:
        IC = IF - IR / alphaR
        IB = IF / Bf + IR / Br
        IE = -IF / alphaF + IR
    For PNP:
        IC = -IF + IR / alphaR
        IB = -IF / Bf - IR / Br
        IE = IF / alphaF - IR

    In all cases: IC + IB + IE == 0 identically.
    Returns (IC, IB, IE). If any term overflows, entries are Decimal('Infinity').
    """
    if_val, ir_val = bjt_injection_currents(vc, vb, ve, p, ctx)
    if not (if_val.is_finite() and ir_val.is_finite()):
        inf = Decimal("Infinity")
        return inf, inf, inf

    try:
        if p.polarity == "NPN":
            # IC = IF - IR / alphaR
            ic = ctx.subtract(if_val, ctx.divide(ir_val, p.alphaR))
            # IB = IF / Bf + IR / Br
            ib = ctx.add(ctx.divide(if_val, p.Bf), ctx.divide(ir_val, p.Br))
            # IE = -IF / alphaF + IR
            ie = ctx.add(ctx.minus(ctx.divide(if_val, p.alphaF)), ir_val)
        else:  # PNP
            # IC = -IF + IR / alphaR
            ic = ctx.add(ctx.minus(if_val), ctx.divide(ir_val, p.alphaR))
            # IB = -IF / Bf - IR / Br
            ib = ctx.subtract(ctx.minus(ctx.divide(if_val, p.Bf)), ctx.divide(ir_val, p.Br))
            # IE = IF / alphaF - IR
            ie = ctx.subtract(ctx.divide(if_val, p.alphaF), ir_val)
        return ic, ib, ie
    except (Overflow, InvalidOperation):
        inf = Decimal("Infinity")
        return inf, inf, inf


def bjt_conductances(
    vc: Decimal, vb: Decimal, ve: Decimal, p: BJTParams, ctx
) -> tuple[Decimal, Decimal]:
    """Small-signal junction conductances (gF, gR).

    gF = d(IF) / d(V_F) = Is / (Nf * Vt) * exp(V_F / (Nf * Vt))
    gR = d(IR) / d(V_R) = Is / (Nr * Vt) * exp(V_R / (Nr * Vt))
    """
    if p.polarity == "NPN":
        vf = ctx.subtract(vb, ve)
        vr = ctx.subtract(vb, vc)
    else:  # PNP
        vf = ctx.subtract(ve, vb)
        vr = ctx.subtract(vc, vb)

    try:
        arg_f = ctx.divide(vf, ctx.multiply(p.Nf, p.Vt))
        gf = ctx.multiply(ctx.divide(p.Is, ctx.multiply(p.Nf, p.Vt)), ctx.exp(arg_f))
    except (Overflow, InvalidOperation):
        gf = Decimal("Infinity")

    try:
        arg_r = ctx.divide(vr, ctx.multiply(p.Nr, p.Vt))
        gr = ctx.multiply(ctx.divide(p.Is, ctx.multiply(p.Nr, p.Vt)), ctx.exp(arg_r))
    except (Overflow, InvalidOperation):
        gr = Decimal("Infinity")

    return gf, gr


def bjt_jacobian(
    vc: Decimal, vb: Decimal, ve: Decimal, p: BJTParams, ctx
) -> tuple[tuple[Decimal, Decimal, Decimal], ...] | None:
    """Analytic 3x3 Jacobian matrix for terminal currents [IC, IB, IE] w.r.t. [VC, VB, VE].

    Order:
        Row 0: dIC/dVC, dIC/dVB, dIC/dVE
        Row 1: dIB/dVC, dIB/dVB, dIB/dVE
        Row 2: dIE/dVC, dIE/dVB, dIE/dVE

    Algebraically identical for NPN and PNP when expressed in terms of (gF, gR):
        [ +gR / alphaR,   gF - gR / alphaR,    -gF          ]
        [ -gR / Br,        gF / Bf + gR / Br,   -gF / Bf     ]
        [ -gR,             -gF / alphaF + gR,   +gF / alphaF ]

    Returns 3x3 tuple of Decimals, or None if any term is non-finite.
    """
    gf, gr = bjt_conductances(vc, vb, ve, p, ctx)
    if not (gf.is_finite() and gr.is_finite()):
        return None

    try:
        # Row 0: dIC
        j00 = ctx.divide(gr, p.alphaR)
        j01 = ctx.subtract(gf, ctx.divide(gr, p.alphaR))
        j02 = ctx.minus(gf)

        # Row 1: dIB
        j10 = ctx.minus(ctx.divide(gr, p.Br))
        j11 = ctx.add(ctx.divide(gf, p.Bf), ctx.divide(gr, p.Br))
        j12 = ctx.minus(ctx.divide(gf, p.Bf))

        # Row 2: dIE
        j20 = ctx.minus(gr)
        j21 = ctx.add(ctx.minus(ctx.divide(gf, p.alphaF)), gr)
        j22 = ctx.divide(gf, p.alphaF)

        for row in ((j00, j01, j02), (j10, j11, j12), (j20, j21, j22)):
            for val in row:
                if not val.is_finite():
                    return None

        return (
            (j00, j01, j02),
            (j10, j11, j12),
            (j20, j21, j22),
        )
    except (Overflow, InvalidOperation):
        return None


def bjt_companion(
    vc: Decimal, vb: Decimal, ve: Decimal, p: BJTParams, ctx
) -> tuple[
    tuple[Decimal, Decimal, Decimal],
    tuple[tuple[Decimal, Decimal, Decimal], ...] | None,
    tuple[Decimal, Decimal, Decimal] | None,
]:
    """Linearized companion model at operating point (vc, vb, ve).

    I_k^(k+1) ~= sum_m (J_km * V_m^(k+1)) + I_k,eq
    where I_k,eq = I_k^(k) - sum_m (J_km * V_m^(k)).

    Returns:
        (IC, IB, IE), J_3x3, (IC_eq, IB_eq, IE_eq)
    Any entry can be non-finite on overflow.
    """
    currents = bjt_terminal_currents(vc, vb, ve, p, ctx)
    jac = bjt_jacobian(vc, vb, ve, p, ctx)
    if not (all(i.is_finite() for i in currents) and jac is not None):
        return currents, None, None

    ic, ib, ie = currents
    v_vec = (vc, vb, ve)
    eq_list: list[Decimal] = []
    try:
        for row, i_curr in zip(jac, (ic, ib, ie)):
            linear_sum = Decimal(0)
            for j_val, v_val in zip(row, v_vec):
                linear_sum = ctx.add(linear_sum, ctx.multiply(j_val, v_val))
            eq_list.append(ctx.subtract(i_curr, linear_sum))
        return currents, jac, (eq_list[0], eq_list[1], eq_list[2])
    except (Overflow, InvalidOperation):
        return currents, jac, None
