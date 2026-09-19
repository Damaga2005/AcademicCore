"""F8-M sensitivity: M4 (DC, implicit-analytic) and M4-AC (linear elements).

M4 at a converged Newton point ``x*`` (certified J via ``NewtonState``):

    J(x*) . dx/dp = -dF/dp        (one HP linear solve per parameter)

``dF/dp`` is closed-form: linear-element stamp derivatives (shared with
M4-AC through :class:`_LinDeriv`) plus per-device analytic tables
(diode kinds, Ebers-Moll BJT, MOSFET L1, JFET). Finite differences are NOT
used here (they exist only in the test-suite as a validation oracle).
A singular ``J`` is reported as ``SINGULAR_JACOBIAN`` - never pseudo-inverted.

M4-AC on the F8-J/D3 complex system ``A X = b`` (linear elements only):

    dX/dp = A^-1 (db/dp - (dA/dp) X)

with magnitude / phase / dB chain rules. Nonlinear device parameters are
out of scope (``INVALID``); nonlinear devices in the circuit are
``UNSUPPORTED``.

Region-boundary policy (documented, branch-consistent): every derivative is
the derivative of the branch the certified device model actually selects at
``x*`` (MOS ``Vov<=0`` cutoff, ``VDS<Vov`` triode else saturation; JFET
``VGS<=-Vp`` cutoff, ``VDS<VGS+Vp`` triode else saturation; Zener
``Vd>=0`` forward). At an exact boundary this is the right-continuous
choice; the branch used is a property of the model, not smoothed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, Overflow
from enum import Enum

from academic_core.domain.engineering.ac.errors import ACFrequencyError
from academic_core.domain.engineering.ac.operating_point import ACOperatingPoint
from academic_core.domain.engineering.ac.problem import build_ac_problem
from academic_core.domain.engineering.ac.topology import reference_net
from academic_core.domain.engineering.circuit import Circuit
from academic_core.domain.engineering.math.decimal_complex import DecimalComplex
from academic_core.domain.engineering.math.linsolve import (
    ComplexLinearProblem,
    NumericMode,
    SolveStatus as LinearStatus,
    solve as linsolve,
)
from academic_core.domain.engineering.math.trig import decimal_pi, make_context
from academic_core.domain.engineering.mna.analysis import (
    ENGINE_VERSION,
    OBS_AUX_CURRENT,
    OBS_DEVICE_CURRENT,
    OBS_NODE_VOLTAGE,
    OBS_RESISTOR_CURRENT,
    OBS_RESISTOR_POWER,
    ObservableSpec,
    ParamAddress,
    _INVALID_ERRORS,
    _precheck,
    _sha,
    circuit_digest,
    observable_value,
    resolve_param,
    solve_point,
    validate_observable,
)
from academic_core.domain.engineering.mna.bjt import (
    bjt_injection_currents,
    bjt_jacobian,
)
from academic_core.domain.engineering.mna.diode import (
    DiodeVariantParams,
    KIND_PHOTO,
    KIND_ZENER,
    shockley_conductance,
    variant_conductance,
)
from academic_core.domain.engineering.mna.errors import (
    InvalidCircuitError,
    UnsupportedElementError,
)
from academic_core.domain.engineering.mna.jfet import jfet_jacobian
from academic_core.domain.engineering.mna.mosfet import (
    REGION_CUTOFF,
    mos_jacobian,
    mos_operating_point,
)
from academic_core.domain.engineering.mna.nonlinear import (
    NewtonState,
    NonlinearStatus,
)
from academic_core.domain.engineering.units import CURRENT, VOLTAGE


class SensitivityStatus(Enum):
    COMPLETED = "completed"
    POINT_NOT_CONVERGED = "point_not_converged"
    SINGULAR_JACOBIAN = "singular_jacobian"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"


def dim_sub(a: tuple, b: tuple) -> tuple:
    """Dimension of ``A/B``: tuple-wise difference of SI exponents."""
    return tuple(x - y for x, y in zip(a, b))


class _Undefined(Exception):
    """A derivative is mathematically undefined/non-finite at this point."""


def _dz() -> DecimalComplex:
    return DecimalComplex(Decimal(0), Decimal(0))


def _dr(v: Decimal) -> DecimalComplex:
    return DecimalComplex(v, Decimal(0))


# ---------------------------------------------------------------------------
# Linear-element stamp derivatives (shared by DC and AC)
# ---------------------------------------------------------------------------

class _LinDeriv:
    """``dA/dp`` / ``db/dp`` of the linear MNA stamps (R/L/C/V/I/E/G/H/F/T).

    Mirrors the certified stamp conventions of ``mna.problem`` and
    ``ac.problem`` (same row/column placement, same ``apply_form`` signs).
    ``omega=None`` is the DC case (no L/C present after DC mapping).
    """

    def __init__(self, circuit: Circuit, node_index: dict,
                 vsource_index: dict, omega: Decimal | None) -> None:
        self.circuit = circuit
        self.ni = node_index
        self.vi = vsource_index
        self.omega = omega
        self.ctx = make_context()
        self.by_ref = {c.ref.upper(): c for c in circuit.components}

    # -- element admittance and its parameter derivative -------------------
    def _y(self, c) -> DecimalComplex:
        ctx, t, base = self.ctx, c.type.upper(), c.value.to_base()
        if t == "R":
            return _dr(ctx.divide(Decimal(1), base))
        wl = ctx.multiply(self.omega, base)
        if t == "L":
            return DecimalComplex(Decimal(0), ctx.divide(Decimal(-1), wl))
        return DecimalComplex(Decimal(0), wl)

    def _dy(self, c) -> DecimalComplex:
        ctx, t, base = self.ctx, c.type.upper(), c.value.to_base()
        if t == "R":
            return _dr(ctx.minus(ctx.divide(Decimal(1),
                                            ctx.multiply(base, base))))
        if t == "L":
            return DecimalComplex(Decimal(0), ctx.divide(
                Decimal(1), ctx.multiply(self.omega, ctx.multiply(base, base))))
        return DecimalComplex(Decimal(0), self.omega)

    # -- current-control forms (net coefs, aux coefs, const) ---------------
    def _form(self, ref_u: str, p: ParamAddress):
        """``(form, dform)``; ``dform`` is d(form)/dp at fixed unknowns."""
        c = self.by_ref[ref_u]
        t = c.type.upper()
        is_p = c.ref.upper() == p.ref.upper()
        one = DecimalComplex(Decimal(1), Decimal(0))
        if t in ("V", "E", "H"):
            return ({}, {c.ref: one}, _dz()), ({}, {}, _dz())
        if t == "O":
            return ({}, {c.ref: -one}, _dz()), ({}, {}, _dz())
        if t in ("R", "L", "C"):
            y = self._y(c)
            a, b = c.pins["1"], c.pins["2"]
            form = ({a: y, b: -y}, {}, _dz())
            if is_p:
                dy = self._dy(c)
                return form, ({a: dy, b: -dy}, {}, _dz())
            return form, ({}, {}, _dz())
        if t == "I":
            ph = _dr(c.value.to_base())
            return ({}, {}, -ph), ({}, {}, -one if is_p else _dz())
        if t == "G":
            gm = _dr(c.value.to_base())
            q = c.parameters
            form = ({q["cp"]: -gm, q["cn"]: gm}, {}, _dz())
            if is_p:
                return form, ({q["cp"]: -one, q["cn"]: one}, {}, _dz())
            return form, ({}, {}, _dz())
        # F: form = -beta * sub ; dform = -dbeta*sub - beta*dsub
        beta = _dr(c.value.to_base())
        sub, dsub = self._form(str(c.parameters["control_ref"]).upper(), p)
        form = _scale(sub, -beta)
        dform = _scale(dsub, -beta)
        if is_p:
            dform = _add(dform, _scale(sub, -one))
        return form, dform

    def derive(self, p: ParamAddress):
        """``(dA_entries, db_entries)``: lists of ``(row, col, DC)`` / ``(row, DC)``."""
        c = self.by_ref[p.ref.upper()]
        t = c.type.upper()
        one = DecimalComplex(Decimal(1), Decimal(0))
        idx = self.ni.get
        dA: list = []
        db: list = []
        if t in ("R", "L", "C"):
            dy = self._dy(c)
            i1, i2 = idx(c.pins["1"]), idx(c.pins["2"])
            if i1 is not None:
                dA.append((i1, i1, dy))
            if i2 is not None:
                dA.append((i2, i2, dy))
            if i1 is not None and i2 is not None:
                dA.append((i1, i2, -dy))
                dA.append((i2, i1, -dy))
        elif t == "V":
            db.append((self.vi[c.ref], one))
        elif t == "I":
            ip, im = idx(c.pins["+"]), idx(c.pins["-"])
            if ip is not None:
                db.append((ip, one))
            if im is not None:
                db.append((im, -one))
        elif t == "E":
            k = self.vi[c.ref]
            icp, icn = idx(c.parameters["cp"]), idx(c.parameters["cn"])
            if icp is not None:
                dA.append((k, icp, -one))
            if icn is not None:
                dA.append((k, icn, one))
        elif t == "G":
            ip, im = idx(c.pins["+"]), idx(c.pins["-"])
            icp, icn = idx(c.parameters["cp"]), idx(c.parameters["cn"])
            for row, sgn in ((ip, -one), (im, one)):
                if row is None:
                    continue
                if icp is not None:
                    dA.append((row, icp, sgn))
                if icn is not None:
                    dA.append((row, icn, -sgn))
        elif t == "T":
            k1, k2 = self.vi[f"{c.ref}:1"], self.vi[f"{c.ref}:2"]
            p1, p2 = idx(c.pins["1"]), idx(c.pins["2"])
            if p1 is not None:
                dA.append((k1, p1, -one))
            if p2 is not None:
                dA.append((k1, p2, one))
            dA.append((k2, k2, one))
        # Dependent H/F stamps: d(gain*form)/dp, covers own gain and any
        # p that the control form depends on (R/L/C/G/I/F-chain).
        for s in self.circuit.components:
            st = s.type.upper()
            if st not in ("H", "F"):
                continue
            form, dform = self._form(
                str(s.parameters["control_ref"]).upper(), p)
            gain = _dr(s.value.to_base())
            prod = _scale(dform, gain)
            if s.ref.upper() == p.ref.upper():
                prod = _add(prod, form)
            rows = ([(self.vi[s.ref], True)] if st == "H" else
                    [(r, neg) for r, neg in (
                        (idx(s.pins["+"]), True), (idx(s.pins["-"]), False))
                     if r is not None])
            nets, aux, const = prod
            for row, negate in rows:
                sgn = -one if negate else one
                for net, coef in nets.items():
                    j = idx(net)
                    if j is not None:
                        dA.append((row, j, sgn * coef))
                for ref, coef in aux.items():
                    dA.append((row, self.vi[ref], sgn * coef))
                db.append((row, const if negate else -const))
        return dA, db


def _scale(form, s):
    nets, aux, const = form
    return ({k: v * s for k, v in nets.items()},
            {k: v * s for k, v in aux.items()}, const * s)


def _add(a, b):
    nets = dict(a[0])
    for k, v in b[0].items():
        nets[k] = nets[k] + v if k in nets else v
    aux = dict(a[1])
    for k, v in b[1].items():
        aux[k] = aux[k] + v if k in aux else v
    return nets, aux, a[2] + b[2]


# ---------------------------------------------------------------------------
# Device dF/dp tables (analytic, Decimal)
# ---------------------------------------------------------------------------

def _exp(ctx, v: Decimal) -> Decimal:
    try:
        r = ctx.exp(v)
    except (Overflow, InvalidOperation) as exc:
        raise _Undefined("exp overflow") from exc
    if not r.is_finite():
        raise _Undefined("exp overflow")
    return r


def _diode_partial(field_: str, vd: Decimal, p, ctx) -> Decimal:
    """``dI/dp`` (partial, ``vd`` fixed) of a diode-kind current."""
    Is, n, Vt = p.Is, p.n, p.Vt
    a = ctx.divide(vd, ctx.multiply(n, Vt))
    ea = _exp(ctx, a)
    kind = p.kind if isinstance(p, DiodeVariantParams) else None
    zener_rev = kind == KIND_ZENER and vd < 0
    if field_ == "Is":
        return ctx.subtract(ea, Decimal(1))
    if field_ in ("n", "Vt"):
        denom = n if field_ == "n" else Vt
        sh = ctx.minus(ctx.divide(ctx.multiply(ctx.multiply(Is, ea), a),
                                  denom))
        if field_ == "Vt" and zener_rev:
            b, c, eb, ec = _zener_terms(vd, p, ctx)
            extra = ctx.divide(ctx.multiply(p.Iz, ctx.subtract(
                ctx.multiply(eb, b), ctx.multiply(ec, c))), Vt)
            sh = ctx.add(sh, extra)
        return sh
    if kind == KIND_PHOTO and field_ == "Iph":
        return Decimal(-1)
    if kind == KIND_ZENER and field_ in ("Vz", "nz", "Iz"):
        if not zener_rev:
            return Decimal(0)
        b, c, eb, ec = _zener_terms(vd, p, ctx)
        if field_ == "Iz":
            return ctx.minus(ctx.subtract(eb, ec))
        if field_ == "Vz":
            return ctx.divide(ctx.multiply(p.Iz, ctx.subtract(eb, ec)),
                              ctx.multiply(p.nz, Vt))
        return ctx.divide(ctx.multiply(p.Iz, ctx.subtract(
            ctx.multiply(eb, b), ctx.multiply(ec, c))), p.nz)
    raise _Undefined(f"no dI/d{field_} for diode")


def _zener_terms(vd, p, ctx):
    nzv = ctx.multiply(p.nz, p.Vt)
    b = ctx.divide(ctx.minus(ctx.add(vd, p.Vz)), nzv)
    c = ctx.divide(ctx.minus(p.Vz), nzv)
    return b, c, _exp(ctx, b), _exp(ctx, c)


def _bjt_partial(field_: str, vc, vb, ve, p, ctx) -> tuple:
    s = Decimal(1) if p.polarity == "NPN" else Decimal(-1)
    if_v, ir_v = bjt_injection_currents(vc, vb, ve, p, ctx)
    if not (if_v.is_finite() and ir_v.is_finite()):
        raise _Undefined("BJT injection currents non-finite")
    if p.polarity == "NPN":
        vf, vr = ctx.subtract(vb, ve), ctx.subtract(vb, vc)
    else:
        vf, vr = ctx.subtract(ve, vb), ctx.subtract(vc, vb)
    af = ctx.divide(vf, ctx.multiply(p.Nf, p.Vt))
    ar = ctx.divide(vr, ctx.multiply(p.Nr, p.Vt))
    kf = ctx.divide(ctx.add(p.Bf, Decimal(1)), p.Bf)
    kr = ctx.divide(ctx.add(p.Br, Decimal(1)), p.Br)
    dif = dir_ = dbf = dbr = Decimal(0)
    if field_ == "Is":
        dif = ctx.subtract(_exp(ctx, af), Decimal(1))
        dir_ = ctx.subtract(_exp(ctx, ar), Decimal(1))
    elif field_ == "Nf":
        dif = ctx.minus(ctx.divide(ctx.multiply(
            ctx.multiply(p.Is, _exp(ctx, af)), af), p.Nf))
    elif field_ == "Nr":
        dir_ = ctx.minus(ctx.divide(ctx.multiply(
            ctx.multiply(p.Is, _exp(ctx, ar)), ar), p.Nr))
    elif field_ == "Vt":
        dif = ctx.minus(ctx.divide(ctx.multiply(
            ctx.multiply(p.Is, _exp(ctx, af)), af), p.Vt))
        dir_ = ctx.minus(ctx.divide(ctx.multiply(
            ctx.multiply(p.Is, _exp(ctx, ar)), ar), p.Vt))
    elif field_ == "Bf":
        dbf = Decimal(1)
    elif field_ == "Br":
        dbr = Decimal(1)
    else:
        raise _Undefined(f"no dI/d{field_} for BJT")
    bf2 = ctx.multiply(p.Bf, p.Bf)
    br2 = ctx.multiply(p.Br, p.Br)
    dkf = ctx.minus(ctx.divide(dbf, bf2))
    dkr = ctx.minus(ctx.divide(dbr, br2))
    ic = ctx.subtract(dif, ctx.add(ctx.multiply(dir_, kr),
                                   ctx.multiply(ir_v, dkr)))
    ib = ctx.subtract(
        ctx.add(ctx.divide(dif, p.Bf), ctx.divide(dir_, p.Br)),
        ctx.add(ctx.divide(ctx.multiply(if_v, dbf), bf2),
                ctx.divide(ctx.multiply(ir_v, dbr), br2)))
    ie = ctx.add(ctx.minus(ctx.add(ctx.multiply(dif, kf),
                                   ctx.multiply(if_v, dkf))), dir_)
    return (ctx.multiply(s, ic), ctx.multiply(s, ib), ctx.multiply(s, ie))


def _mos_partial(field_: str, vd, vg, vs, vb, p, ctx) -> tuple:
    op = mos_operating_point(vd, vg, vs, vb, p, ctx)
    if op is None:
        raise _Undefined("MOS operating point non-finite")
    region, idm, gm_m, _gds, _gmb, _vth, vov = op
    zero4 = (Decimal(0),) * 4
    if region == REGION_CUTOFF:
        return zero4
    s = Decimal(1) if p.polarity == "NMOS" else Decimal(-1)
    vds = ctx.multiply(s, ctx.subtract(vd, vs))
    vsb = ctx.multiply(s, ctx.subtract(vs, vb))
    if field_ == "Kp":
        d = ctx.divide(idm, p.Kp)
    elif field_ == "Vto":
        d = ctx.minus(gm_m)
    elif field_ == "Lambda":
        if vds < vov:
            core = ctx.subtract(ctx.multiply(vov, vds), ctx.divide(
                ctx.multiply(vds, vds), Decimal(2)))
            base = ctx.multiply(p.Kp, core)
        else:
            base = ctx.multiply(ctx.divide(p.Kp, Decimal(2)),
                                ctx.multiply(vov, vov))
        d = ctx.multiply(base, vds)
    elif field_ in ("Gamma", "Phi"):
        arg = ctx.add(p.Phi, vsb)
        if arg <= 0:
            dvth = Decimal(0)
        elif field_ == "Gamma":
            root_phi = ctx.sqrt(p.Phi) if p.Phi > 0 else Decimal(0)
            dvth = ctx.subtract(ctx.sqrt(arg), root_phi)
        elif p.Gamma == 0:
            dvth = Decimal(0)
        elif p.Phi == 0:
            raise _Undefined("dVth/dPhi is unbounded at Phi=0 with Gamma>0")
        else:
            dvth = ctx.multiply(p.Gamma, ctx.subtract(
                ctx.divide(Decimal(1), ctx.multiply(Decimal(2), ctx.sqrt(arg))),
                ctx.divide(Decimal(1), ctx.multiply(Decimal(2),
                                                    ctx.sqrt(p.Phi)))))
        d = ctx.minus(ctx.multiply(gm_m, dvth))
    else:
        raise _Undefined(f"no dI/d{field_} for MOSFET")
    dd = ctx.multiply(s, d)
    return (dd, Decimal(0), ctx.minus(dd), Decimal(0))


def _jfet_partial(field_: str, vd, vg, vs, p, ctx) -> tuple:
    s = Decimal(1) if p.polarity == "NCHAN" else Decimal(-1)
    vgs = ctx.multiply(s, ctx.subtract(vg, vs))
    vds = ctx.multiply(s, ctx.subtract(vd, vs))
    zero3 = (Decimal(0),) * 3
    if vgs <= ctx.minus(p.Vp):
        return zero3
    a = ctx.add(Decimal(1), ctx.divide(vgs, p.Vp))
    grow = ctx.add(Decimal(1), ctx.multiply(p.Lambda, vds))
    triode = vds < ctx.add(vgs, p.Vp)
    b = ctx.divide(vds, p.Vp)
    core = ctx.subtract(ctx.multiply(ctx.multiply(Decimal(2), a), b),
                        ctx.multiply(b, b))
    if field_ == "Idss":
        d = ctx.multiply(core if triode else ctx.multiply(a, a), grow)
    elif field_ == "Lambda":
        d = ctx.multiply(ctx.multiply(p.Idss,
                                      core if triode else ctx.multiply(a, a)),
                         vds)
    elif field_ == "Vp":
        vp2 = ctx.multiply(p.Vp, p.Vp)
        da = ctx.minus(ctx.divide(vgs, vp2))
        if triode:
            db_ = ctx.minus(ctx.divide(vds, vp2))
            dcore = ctx.subtract(
                ctx.multiply(Decimal(2), ctx.add(ctx.multiply(da, b),
                                                 ctx.multiply(a, db_))),
                ctx.multiply(ctx.multiply(Decimal(2), b), db_))
        else:
            dcore = ctx.multiply(ctx.multiply(Decimal(2), a), da)
        d = ctx.multiply(ctx.multiply(p.Idss, grow), dcore)
    else:
        raise _Undefined(f"no dI/d{field_} for JFET")
    dd = ctx.multiply(s, d)
    return (dd, Decimal(0), ctx.minus(dd))


def _device_terminals(comp, state: NewtonState):
    """``(node indices, partial-fn(field) -> per-terminal dI)`` for D/Q/M/J."""
    ctx = make_context()
    sysm = state.system
    u = comp.ref.upper()

    def v(net):
        idx = state.problem.node_index.get(net)
        return Decimal(0) if idx is None else state.x[idx]

    ni = state.problem.node_index.get
    t = comp.type.upper()
    if t == "D":
        p = sysm.variant_models.get(u) or sysm.models[u]
        vd = ctx.subtract(v(comp.pins["A"]), v(comp.pins["K"]))
        nodes = (ni(comp.pins["A"]), ni(comp.pins["K"]))

        def fn(f):
            d = _diode_partial(f, vd, p, ctx)
            return (d, ctx.minus(d))
        return nodes, fn
    if t == "Q":
        p = sysm.bjt_models[u]
        nodes = tuple(ni(comp.pins[k]) for k in ("C", "B", "E"))
        vv = tuple(v(comp.pins[k]) for k in ("C", "B", "E"))
        return nodes, lambda f: _bjt_partial(f, *vv, p, ctx)
    if t == "M":
        p = sysm.mos_models[u]
        nodes = tuple(ni(comp.pins[k]) for k in ("D", "G", "S", "B"))
        vv = tuple(v(comp.pins[k]) for k in ("D", "G", "S", "B"))
        return nodes, lambda f: _mos_partial(f, *vv, p, ctx)
    p = sysm.jfet_models[u]
    nodes = tuple(ni(comp.pins[k]) for k in ("D", "G", "S"))
    vv = tuple(v(comp.pins[k]) for k in ("D", "G", "S"))
    return nodes, lambda f: _jfet_partial(f, *vv, p, ctx)


# ---------------------------------------------------------------------------
# Observable gradients
# ---------------------------------------------------------------------------

def _obs_grad(spec: ObservableSpec, state: NewtonState):
    """``(grad: {index: Decimal}, explicit(addr) -> Decimal)``."""
    ctx = make_context()
    pb = state.problem
    ni = pb.node_index.get
    loc = spec.locator
    by_ref = {c.ref.upper(): c for c in pb.circuit.components}
    zero = lambda addr: Decimal(0)  # noqa: E731

    def vnet(net):
        i = ni(net)
        return Decimal(0) if i is None else state.x[i]

    if spec.kind == OBS_NODE_VOLTAGE:
        i = ni(loc)
        return ({} if i is None else {i: Decimal(1)}), zero
    if spec.kind == OBS_AUX_CURRENT:
        ref, _, leg = loc.partition(":")
        key = next(k for k in pb.vsource_index
                   if k.upper() == (f"{ref}:{leg}" if leg else ref).upper())
        return {pb.vsource_index[key]: Decimal(1)}, zero
    if spec.kind in (OBS_RESISTOR_CURRENT, OBS_RESISTOR_POWER):
        c = by_ref[loc.upper()]
        r = c.value.to_base()
        i1, i2 = ni(c.pins["1"]), ni(c.pins["2"])
        v = ctx.subtract(vnet(c.pins["1"]), vnet(c.pins["2"]))
        r2 = ctx.multiply(r, r)
        if spec.kind == OBS_RESISTOR_CURRENT:
            g = ctx.divide(Decimal(1), r)
            explicit = ctx.minus(ctx.divide(v, r2))
        else:
            g = ctx.divide(ctx.multiply(Decimal(2), v), r)
            explicit = ctx.minus(ctx.divide(ctx.multiply(v, v), r2))
        grad = {}
        if i1 is not None:
            grad[i1] = g
        if i2 is not None:
            grad[i2] = ctx.minus(g)
        return grad, (lambda addr: explicit if
                      (addr.ref.upper() == c.ref.upper()
                       and addr.field == "value") else Decimal(0))
    ref, _, leg = loc.partition(":")
    c = by_ref[ref.upper()]
    t = c.type.upper()
    sysm = state.system
    u = ref.upper()
    nodes, fn = _device_terminals(c, state)
    if t == "D":
        p = sysm.variant_models.get(u) or sysm.models[u]
        vd = ctx.subtract(vnet(c.pins["A"]), vnet(c.pins["K"]))
        g = (variant_conductance(vd, p, ctx) if u in sysm.variant_models
             else shockley_conductance(vd, p, ctx))
        grad = {}
        if nodes[0] is not None:
            grad[nodes[0]] = g
        if nodes[1] is not None:
            grad[nodes[1]] = ctx.minus(g)
        term = 0
    else:
        vv = tuple(vnet(c.pins[k]) for k in _LEGS[t])
        jac = {"Q": bjt_jacobian, "M": mos_jacobian,
               "J": jfet_jacobian}[t](*vv, sysm_model(sysm, t, u), ctx)
        if jac is None:
            raise _Undefined("device Jacobian non-finite")
        term = _LEGS[t].index(leg)
        grad = {}
        for col, n_i in enumerate(nodes):
            if n_i is not None:
                grad[n_i] = jac[term][col]

    def explicit(addr: ParamAddress) -> Decimal:
        if addr.ref.upper() != c.ref.upper():
            return Decimal(0)
        return fn(addr.field)[term]
    return grad, explicit


_LEGS = {"Q": ("C", "B", "E"), "M": ("D", "G", "S", "B"),
         "J": ("D", "G", "S")}


def sysm_model(sysm, t: str, u: str):
    return {"Q": sysm.bjt_models, "M": sysm.mos_models,
            "J": sysm.jfet_models}[t][u]


# ---------------------------------------------------------------------------
# M4 - DC sensitivity
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SensitivityConfig:
    """``parameters``: ParamAddress sequence (>= 1, no duplicates);
    ``observables``: optional; ``normalized``: add ``(p/o)(do/dp)``."""

    parameters: tuple
    observables: tuple = ()
    normalized: bool = False


@dataclass(frozen=True)
class SensitivityResult:
    status: SensitivityStatus
    point_status: str | None = None
    nominal: dict = field(default_factory=dict)
    state: dict = field(default_factory=dict)
    observables: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)
    diagnostics: tuple = ()
    digest: str | None = None

    def to_dict(self) -> dict:
        return _plain({
            "status": self.status.value, "point_status": self.point_status,
            "nominal": self.nominal, "state": self.state,
            "observables": self.observables,
            "provenance": self.provenance,
            "diagnostics": list(self.diagnostics), "digest": self.digest})


def _plain(o):
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, dict):
        return {str(k): _plain(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_plain(v) for v in o]
    return o


def _sens_fail(status, msg, point_status=None) -> SensitivityResult:
    return SensitivityResult(status=status, point_status=point_status,
                             diagnostics=(msg,),
                             provenance={"engine": ENGINE_VERSION})


def _validate_params(circuit, params, dynamic: bool = False) -> tuple:
    ps = tuple(params)
    if not ps:
        raise InvalidCircuitError("at least one parameter required")
    seen = set()
    for a in ps:
        resolve_param(circuit, a, dynamic=dynamic)
        if a.key in seen:
            raise InvalidCircuitError(f"duplicate parameter {a.key}")
        seen.add(a.key)
    return ps


def _unknown_names(state: NewtonState) -> list[tuple[str, tuple]]:
    pb = state.problem
    names = [(n, VOLTAGE) for n in pb.nodes]
    aux = sorted(pb.vsource_index.items(), key=lambda kv: kv[1])
    return names + [(f"I({k})", CURRENT) for k, _ in aux]


def _solve_real(jac, rhs):
    return linsolve(ComplexLinearProblem.from_sequences(jac, rhs),
                    NumericMode.HIGH_PRECISION)


def solve_dc_sensitivity(circuit: Circuit, config: SensitivityConfig
                         ) -> SensitivityResult:
    """M4: ``dx/dp = -J^-1 dF/dp`` (+ observables, normalized form)."""
    try:
        if not isinstance(config, SensitivityConfig):
            raise InvalidCircuitError("config must be a SensitivityConfig")
        params = _validate_params(circuit, config.parameters)
        specs = tuple(config.observables)
        keys = set()
        for o in specs:
            validate_observable(o, circuit)
            if o.key in keys:
                raise InvalidCircuitError(f"duplicate observable {o.key}")
            keys.add(o.key)
        _precheck(circuit)
    except (InvalidCircuitError, UnsupportedElementError,
            *_INVALID_ERRORS) as exc:
        return _sens_fail(
            SensitivityStatus.UNSUPPORTED
            if isinstance(exc, UnsupportedElementError)
            else SensitivityStatus.INVALID, str(exc))
    result, state = solve_point(circuit)
    if result.status is not NonlinearStatus.CONVERGED or state is None:
        return _sens_fail(
            SensitivityStatus.POINT_NOT_CONVERGED,
            f"operating point not converged ({result.status.value}); "
            f"sensitivity is only defined at a converged point",
            result.status.value)
    ctx = make_context()
    pb = state.problem
    n = pb.size
    x = state.x
    jac = state.system.jacobian(x)
    if jac is None:
        return _sens_fail(SensitivityStatus.UNSUPPORTED,
                          "Jacobian non-finite at the converged point",
                          result.status.value)
    lin_check = _solve_real(jac, [Decimal(0)] * n)
    if lin_check.status in (LinearStatus.SINGULAR, LinearStatus.INCONSISTENT):
        return _sens_fail(
            SensitivityStatus.SINGULAR_JACOBIAN,
            f"Jacobian {lin_check.status.value} (rank {lin_check.rank_A}/{n}) "
            f"at the converged point: sensitivity undefined (no "
            f"pseudo-inverse is used)", result.status.value)
    dc = pb.circuit
    lin = _LinDeriv(dc, pb.node_index, pb.vsource_index, None)
    unknowns = _unknown_names(state)
    state_out: dict = {}
    dx_of: dict = {}
    try:
        for a in params:
            rp = resolve_param(circuit, a)
            dA, db = lin.derive(a)
            dF = [Decimal(0)] * n
            for i, j, v in dA:
                dF[i] = ctx.add(dF[i], ctx.multiply(v.re, x[j]))
            for i, v in db:
                dF[i] = ctx.subtract(dF[i], v.re)
            comp = rp.component
            if comp.type.upper() in ("D", "Q", "M", "J"):
                nodes, fn = _device_terminals(_by_ref(dc, comp.ref), state)
                part = fn(a.field)
                for node_i, dI in zip(nodes, part):
                    if node_i is not None:
                        dF[node_i] = ctx.add(dF[node_i], dI)
            sol = _solve_real(jac, [ctx.minus(v) for v in dF])
            if sol.status is not LinearStatus.SOLVED or sol.solution is None:
                return _sens_fail(
                    SensitivityStatus.SINGULAR_JACOBIAN,
                    f"linear solve for {a.key}: {sol.status.value}",
                    result.status.value)
            s = tuple(e.re for e in sol.solution)
            dx_of[a.key] = s
            state_out[a.key] = {
                "parameter_dimension": rp.dimension,
                "values": {nm: {"value": s[i],
                                "dimension": dim_sub(dm, rp.dimension)}
                           for i, (nm, dm) in enumerate(unknowns)}}
        obs_out: dict = {}
        for spec in specs:
            val = observable_value(spec, state)
            grad, explicit = _obs_grad(spec, state)
            rec = {"value": val, "dimension": spec.dimension,
                   "sensitivities": {}}
            for a in params:
                rp = resolve_param(circuit, a)
                s = dx_of[a.key]
                d = explicit(a)
                for i, g in grad.items():
                    d = ctx.add(d, ctx.multiply(g, s[i]))
                item = {"derivative": d,
                        "dimension": dim_sub(spec.dimension, rp.dimension)}
                if config.normalized:
                    item["normalized"] = (
                        None if val == 0 else
                        ctx.multiply(ctx.divide(rp.nominal, val), d))
                rec["sensitivities"][a.key] = item
            obs_out[spec.key] = rec
    except (_Undefined, ArithmeticError) as exc:
        return _sens_fail(SensitivityStatus.UNSUPPORTED,
                          f"derivative undefined/non-finite: {exc!s} "
                          f"({type(exc).__name__})", result.status.value)
    doc = {"kind": "dc-sensitivity",
           "parameters": [a.key for a in params],
           "observables": [o.key for o in specs],
           "normalized": config.normalized}
    prov = {"engine": ENGINE_VERSION, "method": "dc-sensitivity/implicit",
            "config_digest": _sha(doc),
            "circuit_digest": circuit_digest(circuit),
            "point_solver_digest": (result.provenance or {}).get(
                "solver_digest"),
            "n_linear_solves": len(params),
            "algorithm": "J dx/dp = -dF/dp (analytic dF/dp, HP linsolve)",
            "finite_differences_in_production": False}
    nominal = {a.key: resolve_param(circuit, a).nominal for a in params}
    body = _plain({"prov": prov, "state": state_out, "obs": obs_out,
                   "nominal": nominal})
    return SensitivityResult(
        status=SensitivityStatus.COMPLETED,
        point_status=result.status.value, nominal=nominal,
        state=state_out, observables=obs_out, provenance=prov,
        digest=_sha(body))


def _by_ref(circuit: Circuit, ref: str):
    return next(c for c in circuit.components
                if c.ref.upper() == ref.upper())


# ---------------------------------------------------------------------------
# M4-AC - AC sensitivity, linear elements only
# ---------------------------------------------------------------------------

_AC_TYPES = frozenset({"R", "L", "C", "E", "G", "H", "F", "T"})


@dataclass(frozen=True)
class ACSensitivityConfig:
    """``frequency``: Quantity or string (e.g. ``"1kHz"``); ``parameters``:
    ``value`` of R/L/C/E/G/H/F/T; ``observables``: ``node_voltage`` /
    ``aux_current`` phasors."""

    frequency: object
    parameters: tuple
    observables: tuple


@dataclass(frozen=True)
class ACSensitivityResult:
    status: SensitivityStatus
    observables: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)
    diagnostics: tuple = ()
    digest: str | None = None

    def to_dict(self) -> dict:
        return _plain({
            "status": self.status.value, "observables": self.observables,
            "provenance": self.provenance,
            "diagnostics": list(self.diagnostics), "digest": self.digest})


def _cplx(z: DecimalComplex) -> dict:
    return {"re": z.re, "im": z.im}


def solve_ac_sensitivity(circuit: Circuit, config: ACSensitivityConfig
                         ) -> ACSensitivityResult:
    """M4-AC: ``dX/dp = A^-1 (db/dp - (dA/dp) X)`` + magnitude/phase/dB."""
    try:
        return _solve_ac_sensitivity(circuit, config)
    except ArithmeticError as exc:  # decimal overflow / impossible operation
        return ACSensitivityResult(
            status=SensitivityStatus.UNSUPPORTED,
            diagnostics=(f"AC derivative non-finite/out of range "
                         f"({type(exc).__name__})",),
            provenance={"engine": ENGINE_VERSION})


def _solve_ac_sensitivity(circuit: Circuit, config: ACSensitivityConfig
                          ) -> ACSensitivityResult:
    def fail(status, msg):
        return ACSensitivityResult(status=status, diagnostics=(msg,),
                                   provenance={"engine": ENGINE_VERSION})

    try:
        if not isinstance(config, ACSensitivityConfig):
            raise InvalidCircuitError("config must be an ACSensitivityConfig")
        params = _validate_params(circuit, config.parameters, dynamic=True)
        for a in params:
            c = resolve_param(circuit, a, dynamic=True).component
            if c.type.upper() not in _AC_TYPES or a.field != "value":
                raise InvalidCircuitError(
                    f"{a.key}: AC sensitivity supports linear-element "
                    f"'value' of {sorted(_AC_TYPES)} only (nonlinear "
                    f"device parameters and AC source magnitudes are out "
                    f"of F8-M scope)")
        specs = tuple(config.observables)
        if not specs:
            raise InvalidCircuitError("at least one observable required")
        for o in specs:
            validate_observable(o, circuit)
            if o.kind not in (OBS_NODE_VOLTAGE, OBS_AUX_CURRENT):
                raise InvalidCircuitError(
                    "AC observables: node_voltage or aux_current phasors")
        ground = reference_net(circuit.nets)
        op = ACOperatingPoint.from_frequency(config.frequency, ground)
        problem = build_ac_problem(circuit, op, NumericMode.HIGH_PRECISION)
    except UnsupportedElementError as exc:
        return fail(SensitivityStatus.UNSUPPORTED, str(exc))
    except (InvalidCircuitError, ACFrequencyError, ValueError,
            *_INVALID_ERRORS) as exc:
        return fail(SensitivityStatus.INVALID, str(exc))
    n = problem.size
    A = [list(r) for r in problem.matrix]
    base = linsolve(ComplexLinearProblem.from_sequences(A, list(problem.rhs)),
                    NumericMode.HIGH_PRECISION)
    if base.status is not LinearStatus.SOLVED or base.solution is None:
        st = (SensitivityStatus.SINGULAR_JACOBIAN
              if base.status in (LinearStatus.SINGULAR,
                                 LinearStatus.INCONSISTENT)
              else SensitivityStatus.UNSUPPORTED)
        return fail(st, f"AC system {base.status.value}: sensitivity "
                        f"undefined (no pseudo-inverse is used)")
    X = base.solution
    ctx = make_context()
    lin = _LinDeriv(circuit, problem.node_index, problem.vsource_index,
                    op.omega)
    dX_of: dict = {}
    for a in params:
        dA, db = lin.derive(a)
        rhs = [_dz() for _ in range(n)]
        for i, v in db:
            rhs[i] = rhs[i] + v
        for i, j, v in dA:
            rhs[i] = rhs[i] - v * X[j]
        sol = linsolve(ComplexLinearProblem.from_sequences(A, rhs),
                       NumericMode.HIGH_PRECISION)
        if sol.status is not LinearStatus.SOLVED or sol.solution is None:
            return fail(SensitivityStatus.SINGULAR_JACOBIAN,
                        f"AC linear solve for {a.key}: {sol.status.value}")
        dX_of[a.key] = sol.solution
    deg = ctx.divide(Decimal(180), decimal_pi(ctx))
    db_scale = ctx.divide(Decimal(20), ctx.ln(Decimal(10)))
    out: dict = {}
    for spec in specs:
        if spec.kind == OBS_NODE_VOLTAGE:
            i = problem.node_index.get(spec.locator)
        else:
            ref, _, leg = spec.locator.partition(":")
            key = next(k for k in problem.vsource_index
                       if k.upper() == (f"{ref}:{leg}" if leg
                                        else ref).upper())
            i = problem.vsource_index[key]
        H = _dz() if i is None else X[i]
        mag = H.modulus()
        rec = {"value": _cplx(H), "magnitude": mag,
               "dimension": spec.dimension, "sensitivities": {}}
        for a in params:
            rp = resolve_param(circuit, a, dynamic=True)
            dH = _dz() if i is None else dX_of[a.key][i]
            item = {"dimension": dim_sub(spec.dimension, rp.dimension),
                    "d_phasor": _cplx(dH)}
            if mag == 0:
                item.update(d_magnitude=None, d_phase_rad=None,
                            d_phase_deg=None, d_db=None)
            else:
                num = H.conjugate() * dH
                m2 = ctx.multiply(mag, mag)
                dphase = ctx.divide(num.im, m2)
                item.update(
                    d_magnitude=ctx.divide(num.re, mag),
                    d_phase_rad=dphase,
                    d_phase_deg=ctx.multiply(dphase, deg),
                    d_db=ctx.multiply(db_scale, ctx.divide(num.re, m2)))
            rec["sensitivities"][a.key] = item
        out[spec.key] = rec
    doc = {"kind": "ac-sensitivity", "frequency": str(op.frequency.to_base()),
           "parameters": [a.key for a in params],
           "observables": [o.key for o in specs]}
    prov = {"engine": ENGINE_VERSION, "method": "ac-sensitivity/implicit",
            "config_digest": _sha(doc),
            "circuit_digest": circuit_digest(circuit),
            "frequency_base_hz": str(op.frequency.to_base()),
            "omega_rad_per_s": str(op.omega),
            "numeric_mode": "high_precision",
            "n_linear_solves": len(params),
            "algorithm": "dX/dp = A^-1 (db/dp - dA/dp X)",
            "finite_differences_in_production": False,
            "scope": "linear elements only; device-parameter AC "
                     "sensitivity out of scope"}
    return ACSensitivityResult(
        status=SensitivityStatus.COMPLETED, observables=out, provenance=prov,
        digest=_sha(_plain({"prov": prov, "obs": out})))
