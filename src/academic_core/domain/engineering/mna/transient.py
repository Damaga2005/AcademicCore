"""F8-L transient (time-domain DAE) solver: implicit integration in Decimal.

Time discretisation of the semi-explicit index-1 DAE

    G x(t) + C_dyn xdot(t) + f_nl(x(t)) - s(t) = 0

with the unknown vector ``x`` = node voltages + aux branch currents
(V/E/H/O/T legs, exactly as in ``mna.problem``) + one auxiliary current
unknown per inductor. Each time step solves the coupled nonlinear
algebraic system

    F(x_{n+1}) = A0 x_{n+1} - b(t_{n+1}) + D(x_{n+1}) = 0

via damped Newton with strict-decrease bisection backtracking (same Q1
policy as ``mna.nonlinear``: RTOL/ATOL/STOL/MAX_ITER/MAX_BACKTRACK),
where ``D`` holds the dynamic companion stamps (C Norton / L series)
plus the memoryless nonlinear device currents (D/Q/M/J/variants, whose
``extract_*``/current/jacobian helpers are reused unmodified).

Methods (``TransientConfig.method``): ``BE`` (Backward Euler / BDF1),
``TR`` (Trapezoidal), ``BDF2`` (variable-step Gear). Adaptive stepping
is driven by a predictor/corrector LTE estimate with safety factor
0.85 (design §7); rejected steps never touch committed history
(transactional rollback). No wall-clock anywhere; no time asserts.

All numerics are ``Decimal`` under explicit contexts (``make_context``,
prec 50). ``float`` never appears. Timestamps are ``Decimal`` seconds.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, Overflow
from enum import Enum
from fractions import Fraction

from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.math.linsolve import (
    ComplexLinearProblem,
    NumericMode,
    SolveStatus as LinearStatus,
    solve as linsolve,
)
from academic_core.domain.engineering.math.trig import (
    decimal_pi,
    decimal_sin,
    make_context,
)
from academic_core.domain.engineering.mna.bjt import (
    BJTParams,
    bjt_jacobian,
    bjt_terminal_currents,
    extract_bjt_params,
)
from academic_core.domain.engineering.mna.dependent import DEPENDENT_TYPES
from academic_core.domain.engineering.mna.diode import (
    PARAM_KIND as DIODE_KIND_KEY,
    DiodeParams,
    DiodeVariantParams,
    companion,
    extract_diode_params,
    extract_diode_variant_params,
    shockley_current,
    variant_companion,
)
from academic_core.domain.engineering.mna.errors import (
    CircularControlError,
    DimensionalityError,
    FloatingCircuitError,
    InvalidCircuitError,
    MissingReferenceError,
    UnsupportedElementError,
)
from academic_core.domain.engineering.mna.jfet import (
    JFETParams,
    extract_jfet_params,
    jfet_jacobian,
    jfet_terminal_currents,
)
from academic_core.domain.engineering.mna.mosfet import (
    MOSParams,
    extract_mosfet_params,
    mos_jacobian,
    mos_terminal_currents,
)
from academic_core.domain.engineering.mna.nonlinear import (
    ATOL,
    MAX_BACKTRACK,
    MAX_ITER,
    RTOL,
    STOL,
    NonlinearStatus,
    solve_nonlinear_dc,
)
from academic_core.domain.engineering.mna.problem import (
    MNAProblem,
    build_mna_problem,
)
from academic_core.domain.engineering.units import (
    CURRENT,
    VOLTAGE,
    Quantity,
    parse_unit,
)

ENGINE_VERSION = "f8l-transient/1.0"

# Deterministic iteration budget for a whole transient run (analogous to
# MAX_ITER per Newton solve; recorded in provenance).
MAX_TRANSIENT_STEPS = 100000

# LTE predictor/corrector normalisation constants per method (documented
# engineering choice; adaptation behaviour is covered by tests, see
# GATE-F8L.md). BE uses a linear-extrapolation predictor (c=1); TR/BDF2
# use a quadratic-extrapolation predictor (c=3).
_LTE_C = {"BE": Decimal(1), "TR": Decimal(3), "BDF2": Decimal(3)}
_METHOD_ORDER = {"BE": 1, "TR": 2, "BDF2": 2}

_KAPPA = Decimal("0.85")
_GROW_MAX = Decimal("2.0")
_SHRINK_MIN = Decimal("0.1")

_VOLT = parse_unit("V")
_AMP = parse_unit("A")

_INVALID_ERRORS = (InvalidCircuitError, MissingReferenceError,
                   FloatingCircuitError, DimensionalityError,
                   CircularControlError)


class TransientStatus(Enum):
    """Solver verdicts for a transient run. Only COMPLETED carries history."""

    COMPLETED = "completed"
    MAX_STEPS = "max_steps"
    DIVERGED = "diverged"
    SINGULAR_JACOBIAN = "singular_jacobian"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"
    TIMESTEP_TOO_SMALL = "timestep_too_small"


@dataclass(frozen=True)
class TransientConfig:
    """Validated transient analysis configuration (all Decimal, no defaults).

    With ``adaptive=False`` (fixed-step verification mode) the LTE is
    still estimated and reported per step but never rejects: every
    Newton-converged step is committed at the requested ``h_init``
    (``h_min == h_max == h_init`` required). This mode exists for
    convergence-order verification; production runs use adaptive mode.
    """

    method: str  # "BE" | "TR" | "BDF2"
    tstop: Decimal  # seconds, > 0
    h_init: Decimal  # seconds, in [h_min, h_max]
    h_min: Decimal  # seconds, > 0
    h_max: Decimal  # seconds, >= h_min
    reltol: Decimal  # LTE relative tolerance, > 0
    abstol: Decimal  # LTE absolute tolerance, >= 0
    adaptive: bool = True

    def __post_init__(self):
        if not isinstance(self.method, str) or \
                self.method.upper() not in ("BE", "TR", "BDF2"):
            raise InvalidCircuitError(
                f"transient method must be 'BE', 'TR' or 'BDF2', "
                f"got {self.method!r}")
        object.__setattr__(self, "method", self.method.upper())
        for key in ("tstop", "h_init", "h_min", "h_max", "reltol", "abstol"):
            val = getattr(self, key)
            if isinstance(val, bool) or not isinstance(val, Decimal):
                raise InvalidCircuitError(
                    f"transient config {key!r} must be a Decimal, "
                    f"got {type(val).__name__}")
            if not val.is_finite():
                raise InvalidCircuitError(
                    f"transient config {key!r} is non-finite")
        if self.tstop <= 0:
            raise InvalidCircuitError("transient tstop must be > 0")
        if self.h_min <= 0:
            raise InvalidCircuitError("transient h_min must be > 0")
        if self.h_max < self.h_min:
            raise InvalidCircuitError("transient h_max must be >= h_min")
        if not (self.h_min <= self.h_init <= self.h_max):
            raise InvalidCircuitError(
                "transient h_init must lie in [h_min, h_max]")
        if self.reltol <= 0:
            raise InvalidCircuitError("transient reltol must be > 0")
        if self.abstol < 0:
            raise InvalidCircuitError("transient abstol must be >= 0")
        if not isinstance(self.adaptive, bool):
            raise InvalidCircuitError("transient adaptive must be a bool")


@dataclass(frozen=True)
class TransientResult:
    """Structured F8-L result: committed history only."""

    status: TransientStatus
    times: tuple[Decimal, ...] = ()
    node_trajectories: dict = field(default_factory=dict)
    inductor_currents: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()

    def node_trajectory(self, net: str) -> tuple[Decimal, ...] | None:
        """Voltage samples of a net across committed times (None if absent)."""
        return self.node_trajectories.get(net)

    def inductor_current(self, ref: str) -> tuple[Decimal, ...] | None:
        """Current samples of an inductor aux branch (None if absent)."""
        return self.inductor_currents.get(ref.upper())

    def value_at(self, net: str, t: Decimal) -> Decimal | None:
        """Nearest-sample node voltage at time t (first index wins ties)."""
        traj = self.node_trajectories.get(net)
        if not traj or not self.times:
            return None
        best, best_d = 0, abs(self.times[0] - t)
        for i, ti in enumerate(self.times[1:], start=1):
            d = abs(ti - t)
            if d < best_d:
                best, best_d = i, d
        return traj[best]

    def final_state(self) -> dict[str, Decimal]:
        """Last committed node voltages (empty unless COMPLETED)."""
        if not self.times:
            return {}
        last = len(self.times) - 1
        return {net: traj[last]
                for net, traj in self.node_trajectories.items()}

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "times": [str(t) for t in self.times],
            "node_trajectories": {
                net: [str(v) for v in traj]
                for net, traj in self.node_trajectories.items()
            },
            "inductor_currents": {
                ref: [str(v) for v in traj]
                for ref, traj in self.inductor_currents.items()
            },
            "stats": dict(self.stats),
            "provenance": self.provenance,
            "diagnostics": list(self.diagnostics),
        }


# ---------------------------------------------------------------------------
# Waveforms (time-dependent V/I sources)
# ---------------------------------------------------------------------------

_WAVE_REQUIRED = {
    "dc": frozenset(),
    "step": frozenset({"v1", "v2", "t0"}),
    "pulse": frozenset({"v1", "v2", "td", "tr", "tf", "width", "period"}),
    "sine": frozenset({"vo", "va", "freq", "td"}),
}


def _validate_wave(comp: Component) -> dict | None:
    """Validate the optional ``wave`` parameter of a V/I source.

    Returns the normalised spec (``{"type": ...}``) or ``None`` when the
    component carries no wave (pure DC at its ``value``). Raises
    ``InvalidCircuitError`` on any malformed spec. Never invents defaults.
    """
    raw = (comp.parameters or {}).get("wave")
    if raw is None:
        return None
    if comp.type.upper() not in ("V", "I"):
        raise InvalidCircuitError(
            f"{comp.ref}: 'wave' is only supported on V/I sources")
    if not isinstance(raw, dict):
        raise InvalidCircuitError(
            f"{comp.ref}: 'wave' must be a dict, got {type(raw).__name__}")
    wtype = raw.get("type")
    if not isinstance(wtype, str) or wtype.lower() not in _WAVE_REQUIRED:
        raise InvalidCircuitError(
            f"{comp.ref}: 'wave' type must be one of "
            f"{sorted(_WAVE_REQUIRED)}, got {wtype!r}")
    wtype = wtype.lower()
    want = _WAVE_REQUIRED[wtype] | {"type"}
    if set(raw) != want:
        raise InvalidCircuitError(
            f"{comp.ref}: wave {wtype!r} needs exactly keys "
            f"{sorted(want)}, got {sorted(raw)}")
    dim = VOLTAGE if comp.type.upper() == "V" else CURRENT
    spec: dict = {"type": wtype}
    for key, val in raw.items():
        if key == "type":
            continue
        if key in ("v1", "v2", "vo", "va"):
            if not isinstance(val, Quantity):
                raise InvalidCircuitError(
                    f"{comp.ref}: wave {key!r} must be a Quantity")
            if val.dimension != dim:
                raise InvalidCircuitError(
                    f"{comp.ref}: wave {key!r} has wrong dimension")
            base = val.to_base()
            if not base.is_finite():
                raise InvalidCircuitError(
                    f"{comp.ref}: wave {key!r} is non-finite")
            spec[key] = base
        else:
            if isinstance(val, bool) or not isinstance(val, Decimal):
                raise InvalidCircuitError(
                    f"{comp.ref}: wave time {key!r} must be a Decimal")
            if not val.is_finite() or val < 0:
                raise InvalidCircuitError(
                    f"{comp.ref}: wave time {key!r} must be finite >= 0")
            spec[key] = val
    if wtype == "sine" and spec["freq"] <= 0:
        raise InvalidCircuitError(
            f"{comp.ref}: sine wave freq must be > 0")
    return spec


def _wave_value(spec: dict | None, dc: Decimal, t: Decimal, ctx) -> Decimal:
    """Source value at time ``t`` (Decimal seconds). ``None`` spec = DC."""
    if spec is None:
        return dc
    wtype = spec["type"]
    if wtype == "dc":
        return dc
    if wtype == "step":
        return spec["v1"] if t < spec["t0"] else spec["v2"]
    if wtype == "sine":
        arg = ctx.multiply(
            ctx.multiply(Decimal(2), decimal_pi(ctx)),
            ctx.multiply(spec["freq"], ctx.subtract(t, spec["td"])))
        return ctx.add(spec["vo"],
                       ctx.multiply(spec["va"], decimal_sin(arg, ctx)))
    # pulse (SPICE-style trapezoidal, one-shot when period == 0)
    v1, v2 = spec["v1"], spec["v2"]
    td = spec["td"]
    if t < td:
        return v1
    span = ctx.subtract(t, td)
    if spec["period"] > 0:
        cyc = ctx.divide(span, spec["period"]).to_integral_value(
            rounding="ROUND_FLOOR")
        span = ctx.subtract(span, ctx.multiply(cyc, spec["period"]))
    tr, width, tf = spec["tr"], spec["width"], spec["tf"]
    try:
        if span < tr:
            if tr == 0:
                return v2
            frac = ctx.divide(span, tr)
            return ctx.add(v1, ctx.multiply(ctx.subtract(v2, v1), frac))
        span2 = ctx.subtract(span, tr)
        if span2 < width:
            return v2
        span3 = ctx.subtract(span2, width)
        if span3 < tf:
            if tf == 0:
                return v1
            frac = ctx.divide(span3, tf)
            return ctx.subtract(v2,
                                ctx.multiply(ctx.subtract(v2, v1), frac))
        return v1
    except (Overflow, InvalidOperation):
        return v1


def _extract_ic(comp: Component) -> Decimal | None:
    """Explicit initial condition (``ic`` Quantity) or ``None``.

    C expects a voltage, L a current; any sign allowed, must be finite.
    """
    raw = (comp.parameters or {}).get("ic")
    if raw is None:
        return None
    if comp.type.upper() not in ("C", "L"):
        raise InvalidCircuitError(
            f"{comp.ref}: 'ic' is only supported on C/L components")
    if not isinstance(raw, Quantity):
        raise InvalidCircuitError(
            f"{comp.ref}: 'ic' must be a Quantity")
    dim = VOLTAGE if comp.type.upper() == "C" else CURRENT
    if raw.dimension != dim:
        raise InvalidCircuitError(
            f"{comp.ref}: 'ic' has wrong dimension (got {raw.format()})")
    val = raw.to_base()
    if not val.is_finite():
        raise InvalidCircuitError(f"{comp.ref}: 'ic' is non-finite")
    return val


# ---------------------------------------------------------------------------
# Companion coefficients
# ---------------------------------------------------------------------------

def _bdf2_alphas(hn: Decimal, h_prev: Decimal | None, ctx):
    """Return ``(a0, a1, a2, uniform)`` for variable-step BDF2.

    With step ratio ``r = hn / h_prev``:
    ``a0 = (2r+1)/((r+1)hn)``, ``a1 = -(r+1)/hn``, ``a2 = r^2/((r+1)hn)``.
    Without a previous step (startup) this degenerates to Backward Euler
    (``uniform=False`` signals the fallback).
    """
    if h_prev is None or h_prev <= 0:
        return (ctx.divide(Decimal(1), hn),
                ctx.divide(Decimal(-1), hn), Decimal(0), False)
    r = ctx.divide(hn, h_prev)
    rp1 = ctx.add(r, Decimal(1))
    a0 = ctx.divide(ctx.add(ctx.multiply(Decimal(2), r), Decimal(1)),
                    ctx.multiply(rp1, hn))
    a1 = ctx.divide(ctx.minus(rp1), hn)
    a2 = ctx.divide(ctx.multiply(r, r), ctx.multiply(rp1, hn))
    return (a0, a1, a2, True)


def _decimal_of(fr: Fraction, ctx) -> Decimal:
    return ctx.divide(Decimal(fr.numerator), Decimal(fr.denominator))


def _block_ok(rows: list[Decimal], scale: Decimal) -> bool:
    if not rows:
        return True
    peak = max(abs(v) for v in rows)
    return peak <= ATOL + RTOL * max(Decimal(1), scale)


# ---------------------------------------------------------------------------
# Transient MNA system (per-step residual/Jacobian assembly)
# ---------------------------------------------------------------------------

class _TransientSystem:
    """Residual/Jacobian assembly over a fixed transient MNA layout."""

    def __init__(self, problem: MNAProblem,
                 diodes: dict[str, DiodeParams],
                 variants: dict[str, DiodeVariantParams],
                 bjts: dict[str, BJTParams],
                 mosfets: dict[str, MOSParams],
                 jfets: dict[str, JFETParams],
                 waves: dict[str, dict | None]) -> None:
        self.problem = problem
        self.ctx = make_context()
        self.n = problem.size
        self.n_nodes = len(problem.nodes)
        ctx = self.ctx

        self.cap_list = sorted(
            (c for c in problem.circuit.components
             if c.type.upper() == "C"),
            key=lambda c: c.ref.upper(),
        )
        self.cap_value = {c.ref.upper(): c.value.to_base()
                          for c in self.cap_list}
        self.cp_index = {c.ref.upper(): problem.node_index.get(c.pins["1"])
                         for c in self.cap_list}
        self.cn_index = {c.ref.upper(): problem.node_index.get(c.pins["2"])
                         for c in self.cap_list}

        self.ind_list = sorted(
            (c for c in problem.circuit.components
             if c.type.upper() == "L"),
            key=lambda c: c.ref.upper(),
        )
        self.ind_value = {c.ref.upper(): c.value.to_base()
                          for c in self.ind_list}
        self.lp_index = {c.ref.upper(): problem.node_index.get(c.pins["1"])
                         for c in self.ind_list}
        self.ln_index = {c.ref.upper(): problem.node_index.get(c.pins["2"])
                         for c in self.ind_list}
        self.lk_index = {c.ref.upper(): problem.vsource_index[c.ref]
                         for c in self.ind_list}

        self.diode_list = sorted(
            (c for c in problem.circuit.components
             if c.type.upper() == "D" and c.ref.upper() not in variants),
            key=lambda c: c.ref.upper(),
        )
        self.models = {c.ref.upper(): diodes[c.ref.upper()]
                       for c in self.diode_list}
        self.a_index = {c.ref.upper(): problem.node_index.get(c.pins["A"])
                        for c in self.diode_list}
        self.k_index = {c.ref.upper(): problem.node_index.get(c.pins["K"])
                        for c in self.diode_list}
        self.variant_list = sorted(
            (c for c in problem.circuit.components
             if c.type.upper() == "D" and c.ref.upper() in variants),
            key=lambda c: c.ref.upper(),
        )
        self.variant_models = {c.ref.upper(): variants[c.ref.upper()]
                               for c in self.variant_list}
        self.va_index = {c.ref.upper(): problem.node_index.get(c.pins["A"])
                         for c in self.variant_list}
        self.vk_index = {c.ref.upper(): problem.node_index.get(c.pins["K"])
                         for c in self.variant_list}

        self.bjt_list = sorted(
            (c for c in problem.circuit.components
             if c.type.upper() == "Q"),
            key=lambda c: c.ref.upper(),
        )
        self.bjt_models = {c.ref.upper(): bjts[c.ref.upper()]
                           for c in self.bjt_list}
        self.c_index = {c.ref.upper(): problem.node_index.get(c.pins["C"])
                        for c in self.bjt_list}
        self.b_index = {c.ref.upper(): problem.node_index.get(c.pins["B"])
                        for c in self.bjt_list}
        self.e_index = {c.ref.upper(): problem.node_index.get(c.pins["E"])
                        for c in self.bjt_list}

        self.mos_list = sorted(
            (c for c in problem.circuit.components
             if c.type.upper() == "M"),
            key=lambda c: c.ref.upper(),
        )
        self.mos_models = {c.ref.upper(): mosfets[c.ref.upper()]
                           for c in self.mos_list}

        self.jfet_list = sorted(
            (c for c in problem.circuit.components
             if c.type.upper() == "J"),
            key=lambda c: c.ref.upper(),
        )
        self.jfet_models = {c.ref.upper(): jfets[c.ref.upper()]
                            for c in self.jfet_list}

        # Time-varying sources: V constraint rows and I injection nets
        # with their DC base values (b0 carries the DC level; per-step
        # assembly substitutes s(t)).
        self.v_wave_rows: dict[str, int] = {}
        self.v_wave_dc: dict[str, Decimal] = {}
        self.i_wave_nets: dict[str, tuple[int | None, int | None]] = {}
        self.i_wave_dc: dict[str, Decimal] = {}
        by_ref = {c.ref.upper(): c for c in problem.circuit.components}
        for c in problem.circuit.components:
            t = c.type.upper()
            if t == "V":
                self.v_wave_rows[c.ref.upper()] = \
                    problem.vsource_index[c.ref]
                self.v_wave_dc[c.ref.upper()] = c.value.to_base()
            elif t == "I":
                self.i_wave_nets[c.ref.upper()] = (
                    problem.node_index.get(c.pins["+"]),
                    problem.node_index.get(c.pins["-"]))
                self.i_wave_dc[c.ref.upper()] = c.value.to_base()
        self.waves = waves
        self.by_ref = by_ref

        self.a0 = tuple(
            tuple(_decimal_of(v, ctx) for v in row)
            for row in problem.matrix)
        self.b0 = tuple(_decimal_of(v, ctx) for v in problem.rhs)

    # -- small helpers ----------------------------------------------------
    def _x_of(self, x: tuple[Decimal, ...], idx: int | None) -> Decimal:
        return Decimal(0) if idx is None else x[idx]

    # -- dynamic history access -------------------------------------------
    def _dyn(self, dyn_c, dyn_l, ref: str, level: int, kind: str) -> Decimal:
        """History value: kind in vC/iC/iL/vL; level 0 = newest."""
        if kind in ("vC", "iC"):
            seq = dyn_c.get(ref.upper(), ())
        else:
            seq = dyn_l.get(ref.upper(), ())
        if level < len(seq):
            return seq[level][0] if kind in ("vC", "iL") else seq[level][1]
        return Decimal(0)

    # -- companion coefficients -------------------------------------------
    def _cap_comp(self, ref: str, h: Decimal, method: str,
                  h_prev: Decimal | None, dyn_c, ctx):
        cval = self.cap_value[ref]
        if method == "BE" or (method == "BDF2" and h_prev is None):
            geq = ctx.divide(cval, h)
            ieq = ctx.multiply(geq, self._dyn(dyn_c, {}, ref, 0, "vC"))
            return geq, ieq, "BE"
        if method == "TR":
            two = Decimal(2)
            geq = ctx.divide(ctx.multiply(two, cval), h)
            ieq = ctx.add(ctx.multiply(geq, self._dyn(dyn_c, {}, ref, 0, "vC")),
                          self._dyn(dyn_c, {}, ref, 0, "iC"))
            return geq, ieq, "TR"
        a0, a1, a2, _ = _bdf2_alphas(h, h_prev, ctx)
        geq = ctx.multiply(a0, cval)
        ieq = ctx.minus(ctx.multiply(
            cval, ctx.add(ctx.multiply(a1, self._dyn(dyn_c, {}, ref, 0, "vC")),
                          ctx.multiply(a2, self._dyn(dyn_c, {}, ref, 1, "vC")))))
        return geq, ieq, "BDF2"

    def _ind_comp(self, ref: str, h: Decimal, method: str,
                  h_prev: Decimal | None, dyn_l, ctx):
        lval = self.ind_value[ref]
        if method == "BE" or (method == "BDF2" and h_prev is None):
            req = ctx.divide(lval, h)
            veq = ctx.minus(ctx.multiply(
                req, self._dyn({}, dyn_l, ref, 0, "iL")))
            return req, veq, "BE"
        if method == "TR":
            two = Decimal(2)
            req = ctx.divide(ctx.multiply(two, lval), h)
            veq = ctx.subtract(
                ctx.minus(ctx.multiply(
                    req, self._dyn({}, dyn_l, ref, 0, "iL"))),
                self._dyn({}, dyn_l, ref, 0, "vL"))
            return req, veq, "TR"
        a0, a1, a2, _ = _bdf2_alphas(h, h_prev, ctx)
        req = ctx.multiply(a0, lval)
        veq = ctx.multiply(
            lval, ctx.add(ctx.multiply(a1, self._dyn({}, dyn_l, ref, 0, "iL")),
                          ctx.multiply(a2, self._dyn({}, dyn_l, ref, 1, "iL"))))
        return req, veq, "BDF2"

    def _comps(self, h: Decimal, method: str, h_prev: Decimal | None,
               dyn_c, dyn_l, ctx):
        """All companion coefficients + effective method per L/C."""
        cap, used = {}, set()
        for c in self.cap_list:
            g, e, m = self._cap_comp(c.ref.upper(), h, method, h_prev,
                                     dyn_c, ctx)
            cap[c.ref.upper()] = (g, e)
            used.add(m)
        ind = {}
        for c in self.ind_list:
            r, e, m = self._ind_comp(c.ref.upper(), h, method, h_prev,
                                     dyn_l, ctx)
            ind[c.ref.upper()] = (r, e)
            used.add(m)
        return cap, ind, used

    # -- residual ----------------------------------------------------------
    def residual(self, x: tuple[Decimal, ...], t: Decimal,
                 comps, ctx) -> tuple[Decimal, ...] | None:
        cap, ind = comps
        try:
            acc = []
            for i in range(self.n):
                total = Decimal(0)
                row = self.a0[i]
                for j in range(self.n):
                    total = ctx.add(total, ctx.multiply(row[j], x[j]))
                acc.append(ctx.subtract(total, self.b0[i]))
            # Time-varying sources: substitute s(t) for the DC level.
            for ref, row in self.v_wave_rows.items():
                spec = self.waves.get(ref)
                if spec is None:
                    continue
                s = _wave_value(spec, self.v_wave_dc[ref], t, ctx)
                acc[row] = ctx.add(acc[row],
                                   ctx.subtract(self.v_wave_dc[ref], s))
            for ref, (ip, im) in self.i_wave_nets.items():
                spec = self.waves.get(ref)
                if spec is None:
                    continue
                s = _wave_value(spec, self.i_wave_dc[ref], t, ctx)
                delta = ctx.subtract(self.i_wave_dc[ref], s)
                if ip is not None:
                    acc[ip] = ctx.add(acc[ip], delta)
                if im is not None:
                    acc[im] = ctx.subtract(acc[im], delta)
            # Capacitor Norton companions.
            for c in self.cap_list:
                ref = c.ref.upper()
                geq, ieq = cap[ref]
                vp = self._x_of(x, self.cp_index[ref])
                vn = self._x_of(x, self.cn_index[ref])
                dv = ctx.subtract(vp, vn)
                ip, inn = self.cp_index[ref], self.cn_index[ref]
                if ip is not None:
                    acc[ip] = ctx.add(acc[ip],
                                      ctx.subtract(ctx.multiply(geq, dv), ieq))
                if inn is not None:
                    acc[inn] = ctx.add(
                        acc[inn],
                        ctx.add(ctx.multiply(geq, ctx.minus(dv)), ieq))
            # Inductor series companions (overwrite short-circuit rows).
            for c in self.ind_list:
                ref = c.ref.upper()
                req, veq = ind[ref]
                k = self.lk_index[ref]
                vp = self._x_of(x, self.lp_index[ref])
                vn = self._x_of(x, self.ln_index[ref])
                il = self._x_of(x, k)
                acc[k] = ctx.subtract(
                    ctx.subtract(ctx.subtract(vp, vn),
                                 ctx.multiply(req, il)), veq)
            # Memoryless nonlinear devices (F8-H/I/K, unmodified math).
            for ref in self.models:
                p = self.models[ref]
                vd = ctx.subtract(self._x_of(x, self.a_index[ref]),
                                  self._x_of(x, self.k_index[ref]))
                ival, _, _ = companion(vd, p, ctx)
                if not ival.is_finite():
                    return None
                ia, ik = self.a_index[ref], self.k_index[ref]
                if ia is not None:
                    acc[ia] = ctx.add(acc[ia], ival)
                if ik is not None:
                    acc[ik] = ctx.subtract(acc[ik], ival)
            for ref in self.variant_models:
                p = self.variant_models[ref]
                vd = ctx.subtract(self._x_of(x, self.va_index[ref]),
                                  self._x_of(x, self.vk_index[ref]))
                ival, _, _ = variant_companion(vd, p, ctx)
                if not ival.is_finite():
                    return None
                ia, ik = self.va_index[ref], self.vk_index[ref]
                if ia is not None:
                    acc[ia] = ctx.add(acc[ia], ival)
                if ik is not None:
                    acc[ik] = ctx.subtract(acc[ik], ival)
            for ref in self.bjt_models:
                bp = self.bjt_models[ref]
                vc = self._x_of(x, self.c_index[ref])
                vb = self._x_of(x, self.b_index[ref])
                ve = self._x_of(x, self.e_index[ref])
                ic, ib, ie = bjt_terminal_currents(vc, vb, ve, bp, ctx)
                if not (ic.is_finite() and ib.is_finite() and ie.is_finite()):
                    return None
                for idx, cur in ((self.c_index[ref], ic),
                                 (self.b_index[ref], ib),
                                 (self.e_index[ref], ie)):
                    if idx is not None:
                        acc[idx] = ctx.add(acc[idx], cur)
            for ref in self.mos_models:
                mp = self.mos_models[ref]
                pins = self.by_ref[ref].pins
                vd = self._x_of(x, self._nidx(pins["D"]))
                vg = self._x_of(x, self._nidx(pins["G"]))
                vs = self._x_of(x, self._nidx(pins["S"]))
                vb = self._x_of(x, self._nidx(pins["B"]))
                idc, ig, isc, ib = mos_terminal_currents(
                    vd, vg, vs, vb, mp, ctx)
                if not all(v.is_finite() for v in (idc, ig, isc, ib)):
                    return None
                for pin, cur in (("D", idc), ("G", ig),
                                 ("S", isc), ("B", ib)):
                    idx = self._nidx(pins[pin])
                    if idx is not None:
                        acc[idx] = ctx.add(acc[idx], cur)
            for ref in self.jfet_models:
                jp = self.jfet_models[ref]
                pins = self.by_ref[ref].pins
                vd = self._x_of(x, self._nidx(pins["D"]))
                vg = self._x_of(x, self._nidx(pins["G"]))
                vs = self._x_of(x, self._nidx(pins["S"]))
                idc, ig, isc = jfet_terminal_currents(vd, vg, vs, jp, ctx)
                if not all(v.is_finite() for v in (idc, ig, isc)):
                    return None
                for pin, cur in (("D", idc), ("G", ig), ("S", isc)):
                    idx = self._nidx(pins[pin])
                    if idx is not None:
                        acc[idx] = ctx.add(acc[idx], cur)
            if not all(v.is_finite() for v in acc):
                return None
            return tuple(acc)
        except (Overflow, InvalidOperation):
            return None

    def _nidx(self, net: str) -> int | None:
        return self.problem.node_index.get(net)

    # -- jacobian ----------------------------------------------------------
    def jacobian(self, x: tuple[Decimal, ...], comps, ctx,
                 ) -> list[list[Decimal]] | None:
        cap, ind = comps
        try:
            rows = [list(r) for r in self.a0]
            for c in self.cap_list:
                ref = c.ref.upper()
                geq, _ = cap[ref]
                ip, inn = self.cp_index[ref], self.cn_index[ref]
                if ip is not None:
                    rows[ip][ip] = ctx.add(rows[ip][ip], geq)
                if inn is not None:
                    rows[inn][inn] = ctx.add(rows[inn][inn], geq)
                if ip is not None and inn is not None:
                    rows[ip][inn] = ctx.subtract(rows[ip][inn], geq)
                    rows[inn][ip] = ctx.subtract(rows[inn][ip], geq)
            for c in self.ind_list:
                ref = c.ref.upper()
                req, _ = ind[ref]
                k = self.lk_index[ref]
                ip, inn = self.lp_index[ref], self.ln_index[ref]
                rows[k] = [Decimal(0)] * self.n
                if ip is not None:
                    rows[k][ip] = Decimal(1)
                if inn is not None:
                    rows[k][inn] = Decimal(-1)
                rows[k][k] = ctx.minus(req)
            for ref in self.models:
                p = self.models[ref]
                vd = ctx.subtract(self._x_of(x, self.a_index[ref]),
                                  self._x_of(x, self.k_index[ref]))
                _, gval, _ = companion(vd, p, ctx)
                if not gval.is_finite():
                    return None
                ia, ik = self.a_index[ref], self.k_index[ref]
                if ia is not None:
                    rows[ia][ia] = ctx.add(rows[ia][ia], gval)
                if ik is not None:
                    rows[ik][ik] = ctx.add(rows[ik][ik], gval)
                if ia is not None and ik is not None:
                    rows[ia][ik] = ctx.subtract(rows[ia][ik], gval)
                    rows[ik][ia] = ctx.subtract(rows[ik][ia], gval)
            for ref in self.variant_models:
                p = self.variant_models[ref]
                vd = ctx.subtract(self._x_of(x, self.va_index[ref]),
                                  self._x_of(x, self.vk_index[ref]))
                _, gval, _ = variant_companion(vd, p, ctx)
                if not gval.is_finite():
                    return None
                ia, ik = self.va_index[ref], self.vk_index[ref]
                if ia is not None:
                    rows[ia][ia] = ctx.add(rows[ia][ia], gval)
                if ik is not None:
                    rows[ik][ik] = ctx.add(rows[ik][ik], gval)
                if ia is not None and ik is not None:
                    rows[ia][ik] = ctx.subtract(rows[ia][ik], gval)
                    rows[ik][ia] = ctx.subtract(rows[ik][ia], gval)
            for ref in self.bjt_models:
                bp = self.bjt_models[ref]
                vc = self._x_of(x, self.c_index[ref])
                vb = self._x_of(x, self.b_index[ref])
                ve = self._x_of(x, self.e_index[ref])
                bj = bjt_jacobian(vc, vb, ve, bp, ctx)
                if bj is None:
                    return None
                nodes = (self.c_index[ref], self.b_index[ref],
                         self.e_index[ref])
                for r_i in range(3):
                    n_r = nodes[r_i]
                    if n_r is None:
                        continue
                    for c_j in range(3):
                        n_c = nodes[c_j]
                        if n_c is None:
                            continue
                        rows[n_r][n_c] = ctx.add(rows[n_r][n_c], bj[r_i][c_j])
            for ref in self.mos_models:
                mp = self.mos_models[ref]
                pins = self.by_ref[ref].pins
                vd = self._x_of(x, self._nidx(pins["D"]))
                vg = self._x_of(x, self._nidx(pins["G"]))
                vs = self._x_of(x, self._nidx(pins["S"]))
                vb = self._x_of(x, self._nidx(pins["B"]))
                mj = mos_jacobian(vd, vg, vs, vb, mp, ctx)
                if mj is None:
                    return None
                order = ("D", "G", "S", "B")
                for r_i, pin_r in enumerate(order):
                    n_r = self._nidx(pins[pin_r])
                    if n_r is None:
                        continue
                    for c_j, pin_c in enumerate(order):
                        n_c = self._nidx(pins[pin_c])
                        if n_c is None:
                            continue
                        rows[n_r][n_c] = ctx.add(rows[n_r][n_c],
                                                 mj[r_i][c_j])
            for ref in self.jfet_models:
                jp = self.jfet_models[ref]
                pins = self.by_ref[ref].pins
                vd = self._x_of(x, self._nidx(pins["D"]))
                vg = self._x_of(x, self._nidx(pins["G"]))
                vs = self._x_of(x, self._nidx(pins["S"]))
                jj = jfet_jacobian(vd, vg, vs, jp, ctx)
                if jj is None:
                    return None
                order = ("D", "G", "S")
                for r_i, pin_r in enumerate(order):
                    n_r = self._nidx(pins[pin_r])
                    if n_r is None:
                        continue
                    for c_j, pin_c in enumerate(order):
                        n_c = self._nidx(pins[pin_c])
                        if n_c is None:
                            continue
                        rows[n_r][n_c] = ctx.add(rows[n_r][n_c],
                                                 jj[r_i][c_j])
            for r in rows:
                if not all(v.is_finite() for v in r):
                    return None
            return rows
        except (Overflow, InvalidOperation):
            return None

    def block_norms(self, f: tuple[Decimal, ...]
                    ) -> tuple[Decimal, Decimal]:
        kcl = [abs(v) for v in f[:self.n_nodes]]
        aux = [abs(v) for v in f[self.n_nodes:]]
        zero = Decimal(0)
        return (max(kcl) if kcl else zero, max(aux) if aux else zero)

    def scale_of(self, x: tuple[Decimal, ...]) -> Decimal:
        peak = max([abs(v) for v in x] or [Decimal(0)])
        return max(Decimal(1), peak)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def _digest_for(structure: dict) -> str:
    return hashlib.sha256(
        json.dumps(structure, sort_keys=True, default=str).encode()
    ).hexdigest()


def _canonical_structure(circuit: Circuit, config: TransientConfig,
                         ics: dict[str, Decimal],
                         waves: dict[str, dict | None]) -> dict:
    entries = []
    for c in circuit.components:
        entry = {
            "ref": c.ref,
            "type": c.type.upper(),
            "value_base_units": (str(c.value.to_base())
                                 if c.value is not None else None),
            "pins": dict(sorted(c.pins.items())),
        }
        if c.type.upper() in DEPENDENT_TYPES:
            entry["control"] = {
                k: str(v) for k, v in sorted(
                    dict(c.parameters or {}).items(), key=lambda kv: kv[0])
            }
        if c.ref.upper() in ics:
            entry["ic"] = str(ics[c.ref.upper()])
        if c.ref.upper() in waves and waves[c.ref.upper()] is not None:
            entry["wave"] = {k: str(v)
                             for k, v in sorted(waves[c.ref.upper()].items())}
        entries.append(entry)
    return {
        "solver": ENGINE_VERSION,
        "formulation": ("transient DAE: A0 x - b(t) + D(x) + C/L companions; "
                        "implicit BE/TR/BDF2; damped Newton per step"),
        "method": config.method,
        "tolerances": {"reltol": str(config.reltol),
                       "abstol": str(config.abstol),
                       "newton_rtol": str(RTOL), "newton_atol": str(ATOL),
                       "newton_stol": str(STOL)},
        "tstop": str(config.tstop),
        "h_init": str(config.h_init),
        "h_min": str(config.h_min),
        "h_max": str(config.h_max),
        "circuit_name": circuit.name,
        "components": sorted(entries, key=lambda d: d["ref"]),
    }


def _fail(status: TransientStatus, diagnostics: tuple[str, ...],
          provenance: dict, stats: dict) -> TransientResult:
    return TransientResult(status=status, provenance=provenance,
                           stats=stats, diagnostics=diagnostics)


def solve_transient(circuit: Circuit, config: TransientConfig,
                    observer=None) -> TransientResult:
    """Time-domain transient analysis (F8-L) with implicit DAE integration.

    E0.3: an optional ``observer`` is told the facts of the real stepping
    loop, as immutable snapshots (tuples of Decimal/str/int/bool):
    ``transient_start`` once (method, order, LTE constant, unknown labels,
    x(0), dynamic states at t=0, step bounds), ``transient_reject`` for
    every rejected attempt (cause, t_n, h tried, retry h, LTE data when the
    cause is the LTE; retry h ``None`` = the attempt that stops the
    integrator) and ``transient_accept`` for every committed step
    (index of t_(n+1) in ``times``, t_n, h, t_(n+1), x_n, predictor,
    x_(n+1), Newton iterations, LTE per dynamic state, methods used, next h).
    ``newton`` rows are ``(k, α, ‖αΔx‖∞, ‖F_KCL‖, ‖F_aux‖, res_ok, step_ok,
    x_k, F(x_k), J(x_k), Δx, trials)`` (E0.4 appended the last five: the
    vectors and the Jacobian the inner Newton really used, and every
    backtracking trial ``(α, trial norm | None, accepted)``); the rejects
    also carry ``newton_failure = (reason | None, (k, x_k, F, J, Δx | None,
    trials) | None)`` for an inner Newton that stopped without converging.
    ``None`` (default) records nothing and keeps the solve byte-identical.
    """
    if not isinstance(config, TransientConfig):
        return TransientResult(
            status=TransientStatus.INVALID,
            diagnostics=("config must be a TransientConfig",))
    diagnostics: list[str] = [
        f"engine={ENGINE_VERSION}",
        f"method={config.method}",
        f"tstop={config.tstop} h_init={config.h_init} "
        f"h_min={config.h_min} h_max={config.h_max}",
        f"ltep: reltol={config.reltol} abstol={config.abstol}",
        f"newton: rtol={RTOL} atol={ATOL} stol={STOL} "
        f"max_iter={MAX_ITER} max_backtracking={MAX_BACKTRACK}",
    ]
    stats: dict = {"accepted": 0, "rejected": 0, "newton_total": 0,
                   "be_startup_steps": 0, "h_first": None, "h_last": None,
                   "method_counts": {}}

    # -- structural validation + dispatch ---------------------------------
    # H/F current control by dynamic branches is outside F8-L scope
    # (checked before the build so the verdict is INVALID, matching
    # the D/Q/M/J control-rejection precedent).
    try:
        by_ref = {c.ref.upper(): c for c in circuit.components}
        for c in circuit.components:
            if c.type.upper() in ("H", "F"):
                ctrl = str((c.parameters or {}).get("control_ref", "")
                           ).upper()
                target = by_ref.get(ctrl)
                if target is not None and \
                        target.type.upper() in ("C", "L"):
                    raise InvalidCircuitError(
                        f"{c.ref}: control_ref {ctrl!r} names a dynamic "
                        f"component — H/F control by C/L is not supported")
    except InvalidCircuitError as exc:
        return _fail(TransientStatus.INVALID, (str(exc),), {}, stats)
    try:
        problem = build_mna_problem(
            circuit, allow_diodes=True, allow_bjts=True, allow_mosfets=True,
            allow_jfets=True, allow_diode_variants=True, allow_transient=True)
    except UnsupportedElementError as exc:
        return _fail(TransientStatus.UNSUPPORTED, (str(exc),), {}, stats)
    except _INVALID_ERRORS as exc:
        return _fail(TransientStatus.INVALID, (str(exc),), {}, stats)

    # -- parameters: waves, ICs, device models ------------------------------
    try:
        waves: dict[str, dict | None] = {}
        for c in circuit.components:
            if c.type.upper() in ("V", "I"):
                waves[c.ref.upper()] = _validate_wave(c)
        ics: dict[str, Decimal] = {}
        for c in circuit.components:
            if c.type.upper() in ("C", "L"):
                ic = _extract_ic(c)
                if ic is not None:
                    ics[c.ref.upper()] = ic
        diodes = {c.ref.upper(): extract_diode_params(c)
                  for c in circuit.components
                  if c.type.upper() == "D" and
                  DIODE_KIND_KEY not in (c.parameters or {})}
        variants = {c.ref.upper(): extract_diode_variant_params(c)
                    for c in circuit.components
                    if c.type.upper() == "D" and
                    DIODE_KIND_KEY in (c.parameters or {})}
        bjts = {c.ref.upper(): extract_bjt_params(c)
                for c in circuit.components if c.type.upper() == "Q"}
        mosfets = {c.ref.upper(): extract_mosfet_params(c)
                   for c in circuit.components if c.type.upper() == "M"}
        jfets = {c.ref.upper(): extract_jfet_params(c)
                 for c in circuit.components if c.type.upper() == "J"}
    except InvalidCircuitError as exc:
        return _fail(TransientStatus.INVALID, (str(exc),), {}, stats)

    struct = _canonical_structure(circuit, config, ics, waves)
    topology_digest = _digest_for(struct)

    def _prov(status: TransientStatus, steps: int) -> dict:
        return {
            "engine": ENGINE_VERSION,
            "method": config.method,
            "tolerances": {"reltol": str(config.reltol),
                           "abstol": str(config.abstol)},
            "newton": {"rtol": str(RTOL), "atol": str(ATOL),
                       "stol": str(STOL), "max_iter": MAX_ITER},
            "tstop": str(config.tstop),
            "h_bounds": {"h_init": str(config.h_init),
                         "h_min": str(config.h_min),
                         "h_max": str(config.h_max)},
            "steps_accepted": steps,
            "final_status": status.value,
            "topology_digest": topology_digest,
        }

    system = _TransientSystem(problem, diodes, variants, bjts, mosfets,
                              jfets, waves)
    ctx = system.ctx
    n = system.n

    # -- t=0 initial state via DC-equivalent substitution --------------------
    # C with IC -> V source (IC); C without -> open (removed).
    # L with IC -> I source (IC); L without -> short (0 V source).
    init = Circuit(f"{circuit.name}_t0")
    take_v = [9000]
    subs: dict[str, tuple[str, str]] = {}  # orig ref -> (kind, sub ref)

    def _fresh(prefix: str) -> str:
        while True:
            take_v[0] += 1
            cand = f"{prefix}{take_v[0]}"
            if cand not in {c.ref.upper() for c in circuit.components}:
                return cand

    for c in circuit.components:
        t = c.type.upper()
        if t == "C" and c.ref.upper() not in ics:
            continue  # open circuit at DC
        if t == "C":
            sub = _fresh("V")
            subs[c.ref.upper()] = ("C-V", sub)
            init.add(Component(sub, "V", Quantity(ics[c.ref.upper()], _VOLT),
                               {"+": c.pins["1"], "-": c.pins["2"]}))
        elif t == "L" and c.ref.upper() not in ics:
            sub = _fresh("V")
            subs[c.ref.upper()] = ("L-sh", sub)
            init.add(Component(sub, "V", Quantity(Decimal(0), _VOLT),
                               {"+": c.pins["1"], "-": c.pins["2"]}))
        elif t == "L":
            sub = _fresh("I")
            subs[c.ref.upper()] = ("L-I", sub)
            # Orientation: the inductor branch current is defined 1->2,
            # so the substitute source must draw IL from pin "1"
            # (MNA I-sources deliver into "+"): "+" = pins["2"].
            init.add(Component(sub, "I", Quantity(ics[c.ref.upper()], _AMP),
                               {"+": c.pins["2"], "-": c.pins["1"]}))
        elif t in ("V", "I") and waves.get(c.ref.upper()) is not None:
            # t=0 state uses the waveform value at t=0, not the DC level.
            unit = _VOLT if t == "V" else _AMP
            s0 = _wave_value(waves[c.ref.upper()], c.value.to_base(),
                             Decimal(0), ctx)
            init.add(Component(c.ref, t, Quantity(s0, unit),
                               dict(c.pins),
                               parameters={k: v for k, v in
                                           (c.parameters or {}).items()
                                           if k != "wave"}))
        else:
            init.add(c)
    dc0 = solve_nonlinear_dc(init)
    if dc0.status != NonlinearStatus.CONVERGED:
        return _fail(
            TransientStatus.INVALID,
            tuple(diagnostics) + tuple(dc0.diagnostics) + (
                f"t=0 initial DC solve failed ({dc0.status.value}): "
                f"inconsistent initial conditions",),
            _prov(TransientStatus.INVALID, 0), stats)

    node0: dict[str, Decimal] = {problem.ground: Decimal(0)}
    for nv in dc0.node_voltages:
        node0[nv.node] = nv.voltage.to_base()
    aux0: dict[str, Decimal] = {}
    for bc in dc0.branch_currents:
        aux0[bc.ref.upper()] = bc.current.to_base()

    def _node(net: str) -> Decimal:
        return node0.get(net, Decimal(0))

    # Dynamic states at t=0.
    dyn_c: dict[str, list[tuple[Decimal, Decimal]]] = {}
    dyn_l: dict[str, list[tuple[Decimal, Decimal]]] = {}
    for c in system.cap_list:
        ref = c.ref.upper()
        v_c = ctx.subtract(_node(c.pins["1"]), _node(c.pins["2"]))
        kind, sub = subs.get(ref, (None, None))
        i_c = aux0.get(sub, Decimal(0)) if kind == "C-V" else Decimal(0)
        # NOTE: the V-substitute aux current is defined +->- through the
        # source, i.e. 1->2 through the capacitor terminals. Same for L.
        dyn_c[ref] = [(v_c, i_c)]
    for c in system.ind_list:
        ref = c.ref.upper()
        kind, sub = subs.get(ref, (None, None))
        if kind == "L-I":
            i_l = ics[ref]
            v_l = ctx.subtract(_node(c.pins["1"]), _node(c.pins["2"]))
        else:
            i_l = aux0.get(sub, Decimal(0))
            v_l = Decimal(0)
        dyn_l[ref] = [(i_l, v_l)]

    # Full unknown vector at t=0 (aux values seed Newton only).
    x0 = [Decimal(0)] * n
    for net, i in problem.node_index.items():
        x0[i] = _node(net)
    for ref, i in problem.vsource_index.items():
        base = ref.split(":")[0].upper()
        if base in aux0:
            # V/E/H/O aux (+ T legs): defined +->- like the scratch solve.
            x0[i] = aux0[base] if ":" not in ref else aux0.get(ref.upper(),
                                                               Decimal(0))
    for c in system.ind_list:
        ref = c.ref.upper()
        x0[system.lk_index[ref]] = dyn_l[ref][0][0]

    t_hist: list[Decimal] = [Decimal(0)]
    x_hist: list[tuple[Decimal, ...]] = [tuple(x0)]
    h_hist: list[Decimal] = []
    if observer is not None:
        from academic_core.domain.engineering.mna.problem import unknown_labels
        observer.transient_start(
            config.method, _METHOD_ORDER[config.method], _LTE_C[config.method],
            bool(config.adaptive), unknown_labels(problem), tuple(x0),
            tuple((ref, "C", v[0][0], v[0][1]) for ref, v in sorted(dyn_c.items()))
            + tuple((ref, "L", v[0][0], v[0][1]) for ref, v in sorted(dyn_l.items())),
            config.tstop, config.h_init, config.h_min, config.h_max,
            config.reltol, config.abstol)

    # -- main stepping loop ---------------------------------------------------
    h = config.h_init
    fixed = not config.adaptive
    first = True
    total_reject = 0

    def _predict(xn, xnm, hn, hpm1, ctx):
        if xnm is None or hpm1 is None or hpm1 == 0:
            return xn
        f = ctx.divide(hn, hpm1)
        return tuple(ctx.add(a, ctx.multiply(ctx.subtract(a, b), f))
                     for a, b in zip(xn, xnm))

    def _y_predict(dyn: dict[str, list], ref: str, slot: int,
                   hn: Decimal, h1: Decimal | None, h2: Decimal | None,
                   ctx, quadratic: bool,
                   deriv: Decimal | None) -> Decimal:
        """Divided-difference extrapolation of a dynamic state.

        Quadratic (second divided difference) when three history points
        exist and ``quadratic`` is set (TR/BDF2 predictor); linear
        extrapolation with two points; explicit-Euler step
        (``y0 + h*dy0``, second-order accurate) with a single point and a
        known derivative; zero-order hold only as a last resort. The
        single-point case matters: a zero-order predictor would measure
        the solution increment instead of the error and pin the
        controller below ``h_min`` on any tight tolerance.
        """
        seq = dyn.get(ref.upper(), ())
        if not seq:
            return Decimal(0)
        if quadratic and len(seq) >= 3 and h1 is not None and h1 > 0 and \
                h2 is not None and h2 > 0:
            y0, y1, y2 = seq[0][slot], seq[1][slot], seq[2][slot]
            d1 = ctx.divide(ctx.subtract(y0, y1), h1)
            d2 = ctx.divide(
                ctx.subtract(ctx.divide(ctx.subtract(y1, y2), h2), d1),
                ctx.add(h1, h2))
            hph1 = ctx.add(hn, h1)
            return ctx.add(ctx.add(y0, ctx.multiply(d1, hn)),
                           ctx.multiply(ctx.multiply(d2, hn), hph1))
        if len(seq) >= 2 and h1 is not None and h1 > 0:
            f = ctx.divide(hn, h1)
            a, b = seq[0][slot], seq[1][slot]
            return ctx.add(a, ctx.multiply(ctx.subtract(a, b), f))
        if deriv is not None:
            return ctx.add(seq[0][slot], ctx.multiply(deriv, hn))
        return seq[0][slot]

    def _ltep(y_new: Decimal, y_pred: Decimal, y_old: Decimal,
              c_m: Decimal, ctx):
        # Context-explicit throughout (no ambient-context abs()/ops on
        # working-precision values).
        try:
            lte = ctx.divide(ctx.subtract(y_new, y_pred).copy_abs(), c_m)
            scale = ctx.add(
                config.abstol,
                ctx.multiply(config.reltol,
                             max(y_new.copy_abs(), y_old.copy_abs())))
            if scale == 0:
                return None if lte != 0 else Decimal(0)
            return ctx.divide(lte, scale)
        except (Overflow, InvalidOperation):
            return None

    def _new_h(h: Decimal, e: Decimal, p: int, ctx,
               upper: bool) -> Decimal | None:
        try:
            if e <= 0:
                factor = _GROW_MAX
            else:
                inv = ctx.divide(Decimal(1), Decimal(p + 1))
                factor = ctx.multiply(
                    _KAPPA, ctx.exp(ctx.multiply(e.ln(ctx), ctx.minus(inv))))
            factor = min(_GROW_MAX, max(_SHRINK_MIN, factor))
            cand = ctx.multiply(h, factor)
            if upper:
                return min(config.h_max, cand)
            return cand
        except (Overflow, InvalidOperation, ValueError):
            return None

    while t_hist[-1] < config.tstop:
        if len(t_hist) - 1 >= MAX_TRANSIENT_STEPS:
            return _fail(TransientStatus.MAX_STEPS,
                         tuple(diagnostics) + (
                             f"step budget exhausted ({MAX_TRANSIENT_STEPS})",),
                         _prov(TransientStatus.MAX_STEPS, len(t_hist) - 1),
                         stats)
        t_n = t_hist[-1]
        remaining = ctx.subtract(config.tstop, t_n)
        final_step = remaining <= h
        if remaining < h:
            h = remaining
        x_n = x_hist[-1]
        x_nm = x_hist[-2] if len(x_hist) >= 2 else None
        hpm = h_hist[-1] if h_hist else None

        # Companion coefficients for this attempt.
        try:
            cap_c, ind_c, used = system._comps(h, config.method, hpm,
                                               dyn_c, dyn_l, ctx)
        except (Overflow, InvalidOperation):
            return _fail(TransientStatus.DIVERGED,
                         tuple(diagnostics) + (
                             "companion evaluation non-finite",),
                         _prov(TransientStatus.DIVERGED, len(t_hist) - 1),
                         stats)
        comps = (cap_c, ind_c)
        if "BE" in used:
            pass  # startup/method fallback recorded below
        t_next = ctx.add(t_n, h)

        # Newton solve at t_{n+1} from an extrapolated guess.
        x = _predict(x_n, x_nm, h, hpm, ctx)
        predictor = x
        f_cur = system.residual(x, t_next, comps, ctx)
        if f_cur is None:
            f_cur = system.residual(x_n, t_next, comps, ctx)
            x = x_n
            if f_cur is None:
                h_tried = h
                if fixed:
                    return _fail(
                        TransientStatus.DIVERGED,
                        tuple(diagnostics) + (
                            "initial residual non-finite at "
                            f"t={t_next} (fixed-step mode)",),
                        _prov(TransientStatus.DIVERGED, len(t_hist) - 1),
                        stats)
                h = ctx.divide(h, Decimal(2))
                if h < config.h_min:
                    return _fail(
                        TransientStatus.TIMESTEP_TOO_SMALL,
                        tuple(diagnostics) + (
                            "initial residual non-finite at "
                            f"t={t_next}",),
                        _prov(TransientStatus.TIMESTEP_TOO_SMALL,
                              len(t_hist) - 1), stats)
                total_reject += 1
                stats["rejected"] += 1
                if observer is not None:
                    observer.transient_reject("residual_nonfinite", t_n, h_tried, t_next, h,
                                              None, (), 0)
                continue
        k0, a0n = system.block_norms(f_cur)
        scale = system.scale_of(x)
        it = 0
        final_f = f_cur
        final_pair = (k0, a0n)
        newton_ok = _block_ok(list(f_cur[:system.n_nodes]), scale) and \
            _block_ok(list(f_cur[system.n_nodes:]), scale)
        diverged = False
        singular = False
        newton_log: list | None = [] if observer is not None else None
        # E0.4 (observer only): why the inner Newton stopped without converging.
        newton_failure: str | None = None
        failed_iteration: tuple | None = None
        while not newton_ok and it < MAX_ITER:
            jac = system.jacobian(x, comps, ctx)
            if jac is None:
                diverged = True
                newton_failure = "Jacobian evaluation non-finite"
                break
            try:
                lin = linsolve(
                    ComplexLinearProblem.from_sequences(
                        jac, [ctx.minus(v) for v in final_f]),
                    NumericMode.HIGH_PRECISION)
            except Exception:
                diverged = True
                newton_failure = "linear-solve entry refused"
                break
            if lin.status in (LinearStatus.SINGULAR,
                              LinearStatus.INCONSISTENT):
                singular = True
                newton_failure = f"Jacobian {lin.status.value}"
                if newton_log is not None:
                    failed_iteration = (it + 1, tuple(x), tuple(final_f),
                                        tuple(tuple(r) for r in jac), None, ())
                break
            if lin.status != LinearStatus.SOLVED or lin.solution is None:
                diverged = True
                newton_failure = f"Newton step not certified ({lin.status.value})"
                break
            dx = tuple(entry.re for entry in lin.solution)
            cur = max(final_pair)
            alpha = Decimal(1)
            accepted = None
            accepted_f = None
            trials: list | None = [] if observer is not None else None
            for _ in range(MAX_BACKTRACK + 1):
                trial = tuple(ctx.add(xv, ctx.multiply(alpha, dv))
                              for xv, dv in zip(x, dx))
                ft = system.residual(trial, t_next, comps, ctx)
                if ft is not None:
                    kt, at = system.block_norms(ft)
                    if max(kt, at) < cur:
                        accepted, accepted_f = trial, ft
                        if trials is not None:
                            trials.append((alpha, max(kt, at), True))
                        break
                    scale_t = system.scale_of(trial)
                    if max(kt, at) <= cur and \
                            _block_ok(list(ft[:system.n_nodes]), scale_t) and \
                            _block_ok(list(ft[system.n_nodes:]), scale_t):
                        accepted, accepted_f = trial, ft
                        if trials is not None:
                            trials.append((alpha, max(kt, at), True))
                        break
                if trials is not None:
                    trials.append((alpha, None if ft is None else max(system.block_norms(ft)), False))
                alpha = ctx.divide(alpha, Decimal(2))
            if accepted is None or accepted_f is None:
                diverged = True
                newton_failure = "backtracking exhausted"
                if newton_log is not None:
                    failed_iteration = (it + 1, tuple(x), tuple(final_f),
                                        tuple(tuple(r) for r in jac), dx, tuple(trials))
                break
            x_prev, f_prev = x, final_f
            step_peak = max([abs(ctx.multiply(alpha, dv)) for dv in dx]
                            or [Decimal(0)])
            x = accepted
            final_f = accepted_f
            final_pair = system.block_norms(final_f)
            it += 1
            scale = system.scale_of(x)
            res_ok = _block_ok(list(final_f[:system.n_nodes]), scale) and \
                _block_ok(list(final_f[system.n_nodes:]), scale)
            step_ok = step_peak <= STOL + RTOL * scale
            newton_ok = res_ok and step_ok
            if newton_log is not None:
                # E0.3 fields first (index-stable), then the E0.4 deep data:
                # x_k, F(x_k), J(x_k), Δx and every backtracking trial.
                newton_log.append((it, alpha, step_peak, final_pair[0], final_pair[1],
                                   res_ok, step_ok, tuple(x_prev), tuple(f_prev),
                                   tuple(tuple(r) for r in jac), dx, tuple(trials)))
        stats["newton_total"] += it
        if newton_log is not None and newton_failure is None and not newton_ok:
            newton_failure = f"iteration budget exhausted ({MAX_ITER})"

        def _abort(cause, e=None, lte=()):
            # E0.3: the attempt that stops the integrator (retry h = None).
            if observer is not None:
                observer.transient_reject(cause, t_n, h, t_next, None, e, tuple(lte), it,
                                          newton=tuple(newton_log),
                                          newton_failure=(newton_failure, failed_iteration))
        if singular:
            _abort("singular_jacobian")
            return _fail(
                TransientStatus.SINGULAR_JACOBIAN,
                tuple(diagnostics) + (
                    f"singular Jacobian at t={t_next}",),
                _prov(TransientStatus.SINGULAR_JACOBIAN, len(t_hist) - 1),
                stats)
        if not newton_ok:
            # Newton divergence -> deterministic retry at half step
            # (adaptive only; fixed-step mode reports DIVERGED).
            if fixed:
                _abort("newton_failed")
                return _fail(
                    TransientStatus.DIVERGED,
                    tuple(diagnostics) + (
                        f"Newton failed at t={t_next} (fixed-step mode)",),
                    _prov(TransientStatus.DIVERGED, len(t_hist) - 1), stats)
            h_tried = h
            h_half = ctx.divide(h, Decimal(2))
            if h <= config.h_min or h_half < config.h_min:
                if remaining <= config.h_min:
                    h_try = remaining
                else:
                    _abort("newton_failed")
                    return _fail(
                        TransientStatus.TIMESTEP_TOO_SMALL,
                        tuple(diagnostics) + (
                            f"Newton failed at t={t_next}, h below h_min",),
                        _prov(TransientStatus.TIMESTEP_TOO_SMALL,
                              len(t_hist) - 1), stats)
                if h_try <= 0 or h_try >= h:
                    _abort("newton_failed")
                    return _fail(
                        TransientStatus.DIVERGED,
                        tuple(diagnostics) + (
                            f"Newton failed at final t={t_next}",),
                        _prov(TransientStatus.DIVERGED, len(t_hist) - 1),
                        stats)
                h = h_try
            else:
                h = min(h_half, remaining) \
                    if remaining < h_half else h_half
            total_reject += 1
            stats["rejected"] += 1
            diagnostics.append(
                f"Newton retry at t={t_next} with h={h} "
                f"(rejected={total_reject})")
            if observer is not None:
                observer.transient_reject("newton_failed", t_n, h_tried, t_next, h, None, (), it,
                                          newton=tuple(newton_log),
                                          newton_failure=(newton_failure, failed_iteration))
            continue

        # LTE estimate on dynamic states (predictor vs corrector).
        c_m = _LTE_C[config.method]
        p_ord = _METHOD_ORDER[config.method]
        quad = config.method in ("TR", "BDF2")
        h1 = h_hist[-1] if h_hist else None
        h2 = h_hist[-2] if len(h_hist) >= 2 else None
        e_max: Decimal | None = Decimal(0)
        lte_log: list | None = [] if observer is not None else None
        for c in system.cap_list:
            ref = c.ref.upper()
            vp = system._x_of(x, system.cp_index[ref])
            vn = system._x_of(x, system.cn_index[ref])
            y_new = ctx.subtract(vp, vn)
            y_old = dyn_c[ref][0][0]
            d0 = ctx.divide(dyn_c[ref][0][1], system.cap_value[ref])
            y_pred = _y_predict(dyn_c, ref, 0, h, h1, h2, ctx, quad, d0)
            e = _ltep(y_new, y_pred, y_old, c_m, ctx)
            if lte_log is not None:
                lte_log.append((ref, "C", y_old, y_pred, y_new, e))
            if e is None:
                e_max = None
                break
            e_max = max(e_max, e)
        for c in system.ind_list:
            if e_max is None:
                break
            ref = c.ref.upper()
            y_new = system._x_of(x, system.lk_index[ref])
            y_old = dyn_l[ref][0][0]
            d0 = ctx.divide(dyn_l[ref][0][1], system.ind_value[ref])
            y_pred = _y_predict(dyn_l, ref, 0, h, h1, h2, ctx, quad, d0)
            e = _ltep(y_new, y_pred, y_old, c_m, ctx)
            if lte_log is not None:
                lte_log.append((ref, "L", y_old, y_pred, y_new, e))
            if e is None:
                e_max = None
                break
            e_max = max(e_max, e)
        if e_max is None:
            if fixed:
                diagnostics.append(
                    f"LTE non-finite at t={t_next} accepted "
                    f"(fixed-step mode)")
            else:
                h_tried = h
                h = ctx.divide(h, Decimal(2))
                if h < config.h_min and remaining > config.h_min:
                    return _fail(
                        TransientStatus.TIMESTEP_TOO_SMALL,
                        tuple(diagnostics) + (
                            f"LTE non-finite at t={t_next}",),
                        _prov(TransientStatus.TIMESTEP_TOO_SMALL,
                              len(t_hist) - 1), stats)
                total_reject += 1
                stats["rejected"] += 1
                if observer is not None:
                    observer.transient_reject("lte_nonfinite", t_n, h_tried, t_next, h, None,
                                              tuple(lte_log), it, newton=tuple(newton_log),
                                              newton_failure=(newton_failure, failed_iteration))
                continue

        if e_max is None or e_max <= 1 or fixed or \
                (final_step and remaining <= config.h_min):
            # ACCEPT (fixed mode / non-finite LTE accepted by policy above;
            # second clause: forced final partial step).
            forced = bool(e_max is not None and final_step
                          and remaining <= config.h_min and e_max > 1)
            # Dynamic branch states at t_{n+1} for history.
            new_dyn_c: dict[str, tuple[Decimal, Decimal]] = {}
            new_dyn_l: dict[str, tuple[Decimal, Decimal]] = {}
            for c in system.cap_list:
                ref = c.ref.upper()
                vp = system._x_of(x, system.cp_index[ref])
                vn = system._x_of(x, system.cn_index[ref])
                vc = ctx.subtract(vp, vn)
                geq, ieq = cap_c[ref]
                ic = ctx.add(ctx.multiply(geq, vc), ctx.minus(ieq))
                new_dyn_c[ref] = (vc, ic)
            for c in system.ind_list:
                ref = c.ref.upper()
                il = system._x_of(x, system.lk_index[ref])
                vp = system._x_of(x, system.lp_index[ref])
                vn = system._x_of(x, system.ln_index[ref])
                req, veq = ind_c[ref]
                vl = ctx.add(ctx.multiply(req, il), veq)
                new_dyn_l[ref] = (il, vl)
            t_hist.append(t_next)
            x_hist.append(x)
            h_hist.append(h)
            for ref, pair in new_dyn_c.items():
                dyn_c[ref].insert(0, pair)
            for ref, pair in new_dyn_l.items():
                dyn_l[ref].insert(0, pair)
            stats["accepted"] += 1
            if used == {"BE"} and config.method == "BDF2":
                stats["be_startup_steps"] += 1
            stats["method_counts"][config.method] = \
                stats["method_counts"].get(config.method, 0) + 1
            if first:
                stats["h_first"] = str(h)
                first = False
            stats["h_last"] = str(h)
            h_used = h
            if forced:
                diagnostics.append(
                    f"final partial step at t={t_next} accepted with "
                    f"E={e_max} (below h_min, cannot refine)")
            elif fixed:
                diagnostics.append(
                    f"accepted t={t_next} E={e_max} newton_it={it} "
                    f"(fixed-step mode)")
            else:
                hn = _new_h(h, e_max, p_ord, ctx, upper=True)
                h = hn if hn is not None else h
                diagnostics.append(
                    f"accepted t={t_next} E={e_max} newton_it={it} "
                    f"next_h={h}")
            if observer is not None:
                observer.transient_accept(
                    len(t_hist) - 1, t_n, h_used, t_next, x_n, predictor, x, it, final_pair[0],
                    final_pair[1], e_max, tuple(lte_log), tuple(sorted(used)),
                    None if (forced or fixed) else h, forced,
                    tuple((ref, "C", v[0], v[1]) for ref, v in sorted(new_dyn_c.items()))
                    + tuple((ref, "L", v[0], v[1]) for ref, v in sorted(new_dyn_l.items())),
                    newton=tuple(newton_log))
            if forced:
                break
        else:
            # REJECT: rollback (history untouched by construction) + retry.
            hn = _new_h(h, e_max, p_ord, ctx, upper=False)
            if hn is None or hn < config.h_min:
                _abort("lte", e_max, lte_log)
                return _fail(
                    TransientStatus.TIMESTEP_TOO_SMALL,
                    tuple(diagnostics) + (
                        f"LTE E={e_max} demands h < h_min at t={t_next}",),
                    _prov(TransientStatus.TIMESTEP_TOO_SMALL,
                          len(t_hist) - 1), stats)
            h_tried = h
            h = hn
            total_reject += 1
            stats["rejected"] += 1
            diagnostics.append(
                f"rejected t={t_next} E={e_max} retry_h={h} "
                f"(history intact at t={t_n})")
            if observer is not None:
                observer.transient_reject("lte", t_n, h_tried, t_next, h, e_max, tuple(lte_log), it,
                                          newton=tuple(newton_log),
                                          newton_failure=(newton_failure, failed_iteration))

    # -- assemble committed trajectories --------------------------------------
    node_trajs: dict[str, list[Decimal]] = {
        net: [] for net in problem.circuit.nets}
    ind_trajs: dict[str, list[Decimal]] = {
        c.ref.upper(): [] for c in system.ind_list}
    for xv in x_hist:
        for net, i in problem.node_index.items():
            node_trajs[net].append(xv[i])
        node_trajs.setdefault(problem.ground, []).append(Decimal(0))
        for c in system.ind_list:
            ind_trajs[c.ref.upper()].append(xv[system.lk_index[c.ref.upper()]])
    result = TransientResult(
        status=TransientStatus.COMPLETED,
        times=tuple(t_hist),
        node_trajectories={k: tuple(v) for k, v in node_trajs.items()},
        inductor_currents={k: tuple(v) for k, v in ind_trajs.items()},
        stats=dict(stats),
        provenance=_prov(TransientStatus.COMPLETED, len(t_hist) - 1),
        diagnostics=tuple(diagnostics),
    )
    return result
