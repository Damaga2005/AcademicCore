"""F8-M advanced analysis: sweeps, worst-case corners, native Monte Carlo.

One shared point-solve layer over the certified F8-H..L machinery (nothing
below duplicates Newton, MNA assembly, linsolve or device equations):

* every point is a native DC operating-point solve
  (``nonlinear.solve_nonlinear_dc_state``); linear circuits use the same
  path (one Newton step), so every family shares statuses and provenance;
* dynamic elements map to their DC equivalent exactly per the F8-J
  precedent (C removed, L -> deterministic 0 V short, IC/waves ignored);
* parameters are addressed through a CLOSED registry (:data:`PARAM_REGISTRY`)
  - never attribute traversal, never ``eval``/``getattr``;
* M1/M2/M3 share one point driver (:func:`_drive_points`) with warm-start
  chaining (R-02) and an explicit, recorded cold fallback;
* M5 draws every sample from a seeded plan (``random.Random.getrandbits``
  -> exact binary fractions -> Decimal Box-Muller), solves each sample from
  the zero vector, and records failed iterations without hiding them.

Everything is ``Decimal`` under explicit contexts (``make_context``);
``float`` never appears. Statuses are honest: a failed point/iteration is
recorded as such and never turned into a number.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from itertools import product

from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.math.trig import (
    decimal_cos,
    decimal_pi,
    make_context,
)
from academic_core.domain.engineering.mna.bjt import bjt_terminal_currents
from academic_core.domain.engineering.mna.dependent import DEPENDENT_TYPES
from academic_core.domain.engineering.mna.diode import (
    shockley_current,
    variant_current,
)
from academic_core.domain.engineering.mna.errors import (
    CircularControlError,
    DimensionalityError,
    FloatingCircuitError,
    InvalidCircuitError,
    MissingReferenceError,
    UnsupportedElementError,
)
from academic_core.domain.engineering.mna.jfet import jfet_terminal_currents
from academic_core.domain.engineering.mna.mosfet import (
    KP_DIM,
    LAMBDA_DIM,
    mos_terminal_currents,
)
from academic_core.domain.engineering.mna.nonlinear import (
    NewtonState,
    NonlinearResult,
    NonlinearStatus,
    solve_nonlinear_dc_state,
)
from academic_core.domain.engineering.mna.problem import build_mna_problem
from academic_core.domain.engineering.units import (
    ADMITTANCE,
    CAPACITANCE,
    CURRENT,
    DIMENSIONLESS,
    INDUCTANCE,
    POWER,
    RESISTANCE,
    VOLTAGE,
    Quantity,
    Unit,
    parse_unit,
)

ENGINE_VERSION = "f8m-analysis/1.0"

MAX_SWEEP_POINTS = 2000
MAX_MC_ITERATIONS = 10000
MAX_WORST_PARAMS = 10

CORNER_HONESTY = ("corner extremum over the enumerated 2^k corners only; "
                  "NOT a proven global optimum (interior extrema are "
                  "invisible to corner enumeration)")

_INVALID_ERRORS = (InvalidCircuitError, MissingReferenceError,
                   FloatingCircuitError, DimensionalityError,
                   CircularControlError)


# ---------------------------------------------------------------------------
# Statuses
# ---------------------------------------------------------------------------

class SweepStatus(Enum):
    COMPLETED = "completed"
    COMPLETED_WITH_POINT_FAILURES = "completed_with_point_failures"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"


class WorstCaseStatus(Enum):
    COMPLETED = "completed"
    COMPLETED_WITH_POINT_FAILURES = "completed_with_point_failures"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"


class MCStatus(Enum):
    COMPLETED = "completed"
    COMPLETED_WITH_FAILURES = "completed_with_failures"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"


# ---------------------------------------------------------------------------
# Closed parameter registry / ParamAddress
# ---------------------------------------------------------------------------

_POS, _NONNEG, _FINITE = "pos", "nonneg", "finite"

#: type -> field -> (dimension, domain). ``value`` fields live on
#: ``Component.value``; every other field lives in ``Component.parameters``.
#: Numeric fields only: ``polarity`` / ``kind`` are categorical and absent.
PARAM_REGISTRY: dict[str, dict[str, tuple[tuple, str]]] = {
    "R": {"value": (RESISTANCE, _POS)},
    "V": {"value": (VOLTAGE, _FINITE)},
    "I": {"value": (CURRENT, _FINITE)},
    "E": {"value": (DIMENSIONLESS, _FINITE)},
    "G": {"value": (ADMITTANCE, _FINITE)},
    "H": {"value": (RESISTANCE, _FINITE)},
    "F": {"value": (DIMENSIONLESS, _FINITE)},
    "T": {"value": (DIMENSIONLESS, _FINITE)},
    "D": {"Is": (CURRENT, _POS), "n": (DIMENSIONLESS, _POS),
          "Vt": (VOLTAGE, _POS), "Vz": (VOLTAGE, _POS),
          "nz": (DIMENSIONLESS, _POS), "Iz": (CURRENT, _POS),
          "Iph": (CURRENT, _NONNEG)},
    "Q": {"Is": (CURRENT, _POS), "Bf": (DIMENSIONLESS, _POS),
          "Br": (DIMENSIONLESS, _POS), "Nf": (DIMENSIONLESS, _POS),
          "Nr": (DIMENSIONLESS, _POS), "Vt": (VOLTAGE, _POS)},
    "M": {"Kp": (KP_DIM, _POS), "Vto": (VOLTAGE, _POS),
          "Lambda": (LAMBDA_DIM, _NONNEG), "Phi": (VOLTAGE, _NONNEG),
          "Gamma": (DIMENSIONLESS, _NONNEG)},
    "J": {"Idss": (CURRENT, _POS), "Vp": (VOLTAGE, _POS),
          "Lambda": (LAMBDA_DIM, _NONNEG)},
}

#: Extra addresses valid ONLY for M4-AC (``dynamic=True``): a DC engine would
#: silently ignore C/L (DC equivalent removes/shorts them), so DC-side
#: resolution rejects them instead of accepting a no-op parameter.
PARAM_REGISTRY_DYNAMIC: dict[str, dict[str, tuple[tuple, str]]] = {
    "C": {"value": (CAPACITANCE, _POS)},
    "L": {"value": (INDUCTANCE, _POS)},
}

_UNIT_SYMBOL = {RESISTANCE: "ohm", VOLTAGE: "V", CURRENT: "A",
                ADMITTANCE: "S", POWER: "W", CAPACITANCE: "F",
                INDUCTANCE: "H"}


def _fields_for(type_letter: str, dynamic: bool):
    if dynamic and type_letter in PARAM_REGISTRY_DYNAMIC:
        return PARAM_REGISTRY_DYNAMIC[type_letter]
    return PARAM_REGISTRY.get(type_letter)


@dataclass(frozen=True)
class ParamAddress:
    """``(ref, field)`` address into the closed parameter registry."""

    ref: str
    field: str

    def __post_init__(self) -> None:
        for name, v in (("ref", self.ref), ("field", self.field)):
            if not isinstance(v, str) or not v.strip():
                raise InvalidCircuitError(
                    f"ParamAddress.{name} must be a non-empty string")

    @property
    def key(self) -> str:
        return f"{self.ref.upper()}.{self.field}"


@dataclass(frozen=True)
class ResolvedParam:
    component: Component
    dimension: tuple
    domain: str
    nominal: Decimal


def resolve_param(circuit: Circuit, addr: ParamAddress, *,
                  dynamic: bool = False) -> ResolvedParam:
    """Resolve ``addr`` against ``circuit`` through the closed registry.

    ``dynamic=True`` (M4-AC only) additionally admits C/L ``value``.

    Raises ``InvalidCircuitError`` for an unknown ref, a type/field pair
    outside :data:`PARAM_REGISTRY` (including categorical fields), a
    field absent from the component, or a non-numeric stored value.
    """
    if not isinstance(addr, ParamAddress):
        raise InvalidCircuitError(
            f"parameter address must be a ParamAddress, "
            f"got {type(addr).__name__}")
    comp = next((c for c in circuit.components
                 if c.ref.upper() == addr.ref.upper()), None)
    if comp is None:
        raise InvalidCircuitError(f"unknown component {addr.ref!r}")
    fields = _fields_for(comp.type.upper(), dynamic)
    if fields is None or addr.field not in fields:
        raise InvalidCircuitError(
            f"{comp.ref}: field {addr.field!r} is not sweepable for type "
            f"{comp.type.upper()} (allowed: {sorted(fields or {})})")
    dim, domain = fields[addr.field]
    if addr.field == "value":
        if comp.value is None:
            raise InvalidCircuitError(f"{comp.ref}: has no value")
        q = comp.value
    else:
        q = (comp.parameters or {}).get(addr.field)
        if not isinstance(q, Quantity):
            raise InvalidCircuitError(
                f"{comp.ref}: parameter {addr.field!r} absent or not a "
                f"Quantity for this component")
    return ResolvedParam(comp, dim, domain, q.to_base())


def _unit1(dim: tuple) -> Unit:
    """Factor-1 (base-unit) ``Unit`` for ``dim``: exact ``to_base``."""
    if dim == DIMENSIONLESS:
        return parse_unit("1")
    sym = _UNIT_SYMBOL.get(dim, "SI")
    return Unit(sym, sym, "", dim, Decimal(1))


def coerce_value(raw, dim: tuple, domain: str, label: str) -> Decimal:
    """Base-unit ``Decimal`` from ``Decimal``/``int``/``Quantity`` (checked)."""
    if isinstance(raw, Quantity):
        if raw.dimension != dim:
            raise InvalidCircuitError(
                f"{label}: quantity {raw.format()} has the wrong dimension")
        v = raw.to_base()
    elif isinstance(raw, bool) or not isinstance(raw, (Decimal, int)):
        raise InvalidCircuitError(
            f"{label}: value must be Decimal/int/Quantity, "
            f"got {type(raw).__name__}")
    else:
        v = Decimal(raw)
    if not v.is_finite():
        raise InvalidCircuitError(f"{label}: non-finite value")
    if domain == _POS and v <= 0:
        raise InvalidCircuitError(f"{label}: value must be > 0, got {v}")
    if domain == _NONNEG and v < 0:
        raise InvalidCircuitError(f"{label}: value must be >= 0, got {v}")
    return v


def substitute(circuit: Circuit,
               assignments: dict[ParamAddress, Decimal], *,
               dynamic: bool = False) -> Circuit:
    """Fresh circuit with ``assignments`` applied (input never mutated)."""
    by_ref: dict[str, dict[str, Decimal]] = {}
    for addr, val in assignments.items():
        rp = resolve_param(circuit, addr, dynamic=dynamic)
        v = coerce_value(val, rp.dimension, rp.domain, addr.key)
        by_ref.setdefault(addr.ref.upper(), {})[addr.field] = v
    out = Circuit(name=circuit.name, notes=circuit.notes)
    for c in circuit.components:
        edits = by_ref.get(c.ref.upper())
        if not edits:
            out.add(c)
            continue
        value = c.value
        params = dict(c.parameters or {})
        for fld, v in edits.items():
            dim = _fields_for(c.type.upper(), dynamic)[fld][0]
            q = Quantity(v, _unit1(dim))
            if fld == "value":
                value = q
            else:
                params[fld] = q
        out.add(Component(ref=c.ref, type=c.type, value=value,
                          pins=dict(c.pins), parameters=params,
                          metadata=dict(c.metadata or {})))
    return out


# ---------------------------------------------------------------------------
# DC-equivalent mapping and digests
# ---------------------------------------------------------------------------

def dc_equivalent(circuit: Circuit) -> Circuit:
    """DC equivalent (F8-J precedent): C -> removed, L -> 0 V source.

    Waves/AC phases are ignored (sources use their DC ``value``); initial
    conditions are transient concepts and ignored. H/F current-controlled
    by a removed/shorted dynamic element are rejected (``InvalidCircuitError``).
    """
    if not any(c.type.upper() in ("L", "C") for c in circuit.components):
        return circuit
    dyn = {c.ref.upper() for c in circuit.components
           if c.type.upper() in ("L", "C")}
    for c in circuit.components:
        if c.type.upper() in ("H", "F") and \
                str((c.parameters or {}).get("control_ref", "")).upper() in dyn:
            raise InvalidCircuitError(
                f"{c.ref}: current-controlled by a dynamic element "
                f"({c.parameters['control_ref']}); DC equivalent undefined")
    nums = [int("".join(ch for ch in c.ref if ch.isdigit()) or 0)
            for c in circuit.components if c.type.upper() == "V"]
    base = max(nums + [9000])
    out = Circuit(name=f"{circuit.name}_dc")
    k = 0
    for c in circuit.components:
        t = c.type.upper()
        if t == "C":
            continue
        if t == "L":
            k += 1
            out.add(Component(
                ref=f"V{base + k}", type="V",
                value=Quantity(Decimal(0), parse_unit("V")),
                pins={"+": c.pins["1"], "-": c.pins["2"]}))
        else:
            out.add(c)
    return out


def _sha(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _dec_str(v) -> str | None:
    return None if v is None else str(v)


def circuit_digest(circuit: Circuit) -> str:
    """Order-independent topology+parameter digest of ``circuit``."""
    comps = []
    for c in sorted(circuit.components, key=lambda c: c.ref.upper()):
        params = {}
        for k, v in sorted((c.parameters or {}).items()):
            params[k] = str(v.to_base()) if isinstance(v, Quantity) else str(v)
        comps.append({
            "ref": c.ref.upper(), "type": c.type.upper(),
            "value": None if c.value is None else str(c.value.to_base()),
            "pins": dict(sorted(c.pins.items())), "parameters": params})
    return _sha({"name": circuit.name, "components": comps})


# ---------------------------------------------------------------------------
# Observables
# ---------------------------------------------------------------------------

OBS_NODE_VOLTAGE = "node_voltage"
OBS_AUX_CURRENT = "aux_current"
OBS_RESISTOR_CURRENT = "resistor_current"
OBS_RESISTOR_POWER = "resistor_power"
OBS_DEVICE_CURRENT = "device_current"
OBSERVABLE_KINDS = frozenset({OBS_NODE_VOLTAGE, OBS_AUX_CURRENT,
                              OBS_RESISTOR_CURRENT, OBS_RESISTOR_POWER,
                              OBS_DEVICE_CURRENT})

_OBS_DIM = {OBS_NODE_VOLTAGE: VOLTAGE, OBS_AUX_CURRENT: CURRENT,
            OBS_RESISTOR_CURRENT: CURRENT, OBS_RESISTOR_POWER: POWER,
            OBS_DEVICE_CURRENT: CURRENT}

_DEVICE_LEGS = {"Q": ("C", "B", "E"), "M": ("D", "G", "S", "B"),
                "J": ("D", "G", "S")}


@dataclass(frozen=True)
class ObservableSpec:
    """Observable of a converged DC point.

    ``node_voltage``: net name. ``aux_current``: ref of a V/E/H/O source or
    a transformer leg ``"T1:1"`` (MNA auxiliary unknown, problem sign
    convention). ``resistor_current``/``resistor_power``: R ref (pin1->pin2,
    ``P = V^2/R``). ``device_current``: ``"D1"`` (A->K) or
    ``"<ref>:<leg>"`` for Q/M/J (current entering the terminal).
    """

    kind: str
    locator: str

    def __post_init__(self) -> None:
        if self.kind not in OBSERVABLE_KINDS:
            raise InvalidCircuitError(
                f"unknown observable kind {self.kind!r}; "
                f"allowed: {sorted(OBSERVABLE_KINDS)}")
        if not isinstance(self.locator, str) or not self.locator.strip():
            raise InvalidCircuitError("observable locator must be a string")

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.locator}"

    @property
    def dimension(self) -> tuple:
        return _OBS_DIM[self.kind]


def validate_observable(spec: ObservableSpec, circuit: Circuit) -> None:
    """Config-time check against the original (pre-DC-mapping) circuit."""
    if not isinstance(spec, ObservableSpec):
        raise InvalidCircuitError(
            f"observable must be an ObservableSpec, got {type(spec).__name__}")
    by_ref = {c.ref.upper(): c for c in circuit.components}
    loc = spec.locator
    if spec.kind == OBS_NODE_VOLTAGE:
        if loc not in circuit.nets:
            raise InvalidCircuitError(f"unknown net {loc!r}")
    elif spec.kind == OBS_AUX_CURRENT:
        ref, _, leg = loc.partition(":")
        c = by_ref.get(ref.upper())
        if c is None or not (
                (c.type.upper() in ("V", "E", "H", "O") and not leg) or
                (c.type.upper() == "T" and leg in ("1", "2"))):
            raise InvalidCircuitError(
                f"{loc!r} is not an auxiliary-current branch "
                f"(V/E/H/O ref or T leg 'T1:1'/'T1:2')")
    elif spec.kind in (OBS_RESISTOR_CURRENT, OBS_RESISTOR_POWER):
        c = by_ref.get(loc.upper())
        if c is None or c.type.upper() != "R":
            raise InvalidCircuitError(f"{loc!r} is not a resistor")
    else:
        ref, _, leg = loc.partition(":")
        c = by_ref.get(ref.upper())
        if c is None or c.type.upper() not in ("D", "Q", "M", "J"):
            raise InvalidCircuitError(f"{loc!r} is not a D/Q/M/J device")
        if c.type.upper() == "D":
            if leg:
                raise InvalidCircuitError("diode current takes no leg")
        elif leg not in _DEVICE_LEGS[c.type.upper()]:
            raise InvalidCircuitError(
                f"{loc!r}: leg must be one of "
                f"{_DEVICE_LEGS[c.type.upper()]}")


def _node_v(state: NewtonState, net: str) -> Decimal:
    idx = state.problem.node_index.get(net)
    return Decimal(0) if idx is None else state.x[idx]


def observable_value(spec: ObservableSpec, state: NewtonState) -> Decimal:
    """Value of ``spec`` at the converged ``state`` (Decimal, context-explicit)."""
    ctx = make_context()
    pb = state.problem
    by_ref = {c.ref.upper(): c for c in pb.circuit.components}
    loc = spec.locator
    if spec.kind == OBS_NODE_VOLTAGE:
        return _node_v(state, loc)
    if spec.kind == OBS_AUX_CURRENT:
        ref, _, leg = loc.partition(":")
        key = next(k for k in pb.vsource_index
                   if k.upper() == (f"{ref}:{leg}" if leg else ref).upper())
        return state.x[pb.vsource_index[key]]
    if spec.kind in (OBS_RESISTOR_CURRENT, OBS_RESISTOR_POWER):
        c = by_ref[loc.upper()]
        v = ctx.subtract(_node_v(state, c.pins["1"]),
                         _node_v(state, c.pins["2"]))
        r = c.value.to_base()
        if spec.kind == OBS_RESISTOR_CURRENT:
            return ctx.divide(v, r)
        return ctx.divide(ctx.multiply(v, v), r)
    ref, _, leg = loc.partition(":")
    c = by_ref[ref.upper()]
    t = c.type.upper()
    sysm = state.system
    u = ref.upper()
    if t == "D":
        vd = ctx.subtract(_node_v(state, c.pins["A"]),
                          _node_v(state, c.pins["K"]))
        if u in sysm.variant_models:
            return variant_current(vd, sysm.variant_models[u], ctx)
        return shockley_current(vd, sysm.models[u], ctx)
    if t == "Q":
        cur = bjt_terminal_currents(
            _node_v(state, c.pins["C"]), _node_v(state, c.pins["B"]),
            _node_v(state, c.pins["E"]), sysm.bjt_models[u], ctx)
        return cur[("C", "B", "E").index(leg)]
    if t == "M":
        cur = mos_terminal_currents(
            _node_v(state, c.pins["D"]), _node_v(state, c.pins["G"]),
            _node_v(state, c.pins["S"]), _node_v(state, c.pins["B"]),
            sysm.mos_models[u], ctx)
        return cur[("D", "G", "S", "B").index(leg)]
    cur = jfet_terminal_currents(
        _node_v(state, c.pins["D"]), _node_v(state, c.pins["G"]),
        _node_v(state, c.pins["S"]), sysm.jfet_models[u], ctx)
    return cur[("D", "G", "S").index(leg)]


# ---------------------------------------------------------------------------
# Grids (M1 / M2)
# ---------------------------------------------------------------------------

def _grid_decimal(v, label: str) -> Decimal:
    if isinstance(v, bool) or not isinstance(v, (Decimal, int)):
        raise InvalidCircuitError(
            f"{label}: must be Decimal/int, got {type(v).__name__}")
    d = Decimal(v)
    if not d.is_finite():
        raise InvalidCircuitError(f"{label}: non-finite")
    return d


@dataclass(frozen=True)
class GridSpec:
    """Sweep grid: ``linear(start, stop, step)``, ``log(start, stop, n)`` or
    ``from_list(values)``. Use the constructors."""

    kind: str
    start: Decimal | None = None
    stop: Decimal | None = None
    step: Decimal | None = None
    n: int | None = None
    values: tuple = ()

    @staticmethod
    def linear(start, stop, step) -> "GridSpec":
        return GridSpec("linear", start=start, stop=stop, step=step)

    @staticmethod
    def log(start, stop, n) -> "GridSpec":
        return GridSpec("log", start=start, stop=stop, n=n)

    @staticmethod
    def from_list(values) -> "GridSpec":
        return GridSpec("list", values=tuple(values))


def expand_grid(grid: GridSpec) -> tuple[Decimal, ...]:
    """Exact ordered grid values. ``InvalidCircuitError`` on any violation
    (empty, sign/direction, log domain, ``> MAX_SWEEP_POINTS``)."""
    if not isinstance(grid, GridSpec):
        raise InvalidCircuitError("grid must be a GridSpec")
    ctx = make_context()
    if grid.kind == "list":
        if not grid.values:
            raise InvalidCircuitError("list grid must not be empty")
        if len(grid.values) > MAX_SWEEP_POINTS:
            raise InvalidCircuitError(
                f"grid has {len(grid.values)} points > "
                f"MAX_SWEEP_POINTS={MAX_SWEEP_POINTS}")
        return tuple(_grid_decimal(v, "list value") for v in grid.values)
    if grid.kind == "linear":
        start = _grid_decimal(grid.start, "start")
        stop = _grid_decimal(grid.stop, "stop")
        step = _grid_decimal(grid.step, "step")
        if step == 0:
            raise InvalidCircuitError("step must be nonzero")
        span = ctx.subtract(stop, start)
        if span == 0:
            return (start,)
        if (span > 0) != (step > 0):
            raise InvalidCircuitError(
                "step direction does not lead from start to stop")
        steps = int(ctx.divide_int(span, step))
        if steps + 2 > MAX_SWEEP_POINTS + 1:
            raise InvalidCircuitError(
                f"grid needs >= {steps + 1} points > "
                f"MAX_SWEEP_POINTS={MAX_SWEEP_POINTS}")
        pts = [ctx.add(start, ctx.multiply(Decimal(k), step))
               for k in range(steps + 1)]
        rem = ctx.subtract(stop, pts[-1])
        if rem != 0 and rem.copy_abs() <= ctx.divide(
                step.copy_abs(), Decimal(2)):
            pts.append(stop)
        if len(pts) > MAX_SWEEP_POINTS:
            raise InvalidCircuitError(
                f"grid has {len(pts)} points > "
                f"MAX_SWEEP_POINTS={MAX_SWEEP_POINTS}")
        return tuple(pts)
    if grid.kind == "log":
        start = _grid_decimal(grid.start, "start")
        stop = _grid_decimal(grid.stop, "stop")
        n = grid.n
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            raise InvalidCircuitError("log grid n must be an int >= 1")
        if n > MAX_SWEEP_POINTS:
            raise InvalidCircuitError(
                f"grid has {n} points > MAX_SWEEP_POINTS={MAX_SWEEP_POINTS}")
        if start <= 0 or stop <= 0:
            raise InvalidCircuitError("log grid requires start, stop > 0")
        if n == 1:
            if start != stop:
                raise InvalidCircuitError("log grid n=1 requires start==stop")
            return (start,)
        ln_ratio = ctx.ln(ctx.divide(stop, start))
        pts = [start]
        for k in range(1, n - 1):
            frac = ctx.divide(Decimal(k), Decimal(n - 1))
            pts.append(ctx.multiply(
                start, ctx.exp(ctx.multiply(frac, ln_ratio))))
        pts.append(stop)
        return tuple(pts)
    raise InvalidCircuitError(f"unknown grid kind {grid.kind!r}")


# ---------------------------------------------------------------------------
# Point solve + shared driver
# ---------------------------------------------------------------------------

def solve_point(circuit: Circuit, x_init=None
                ) -> tuple[NonlinearResult, NewtonState | None]:
    """One native DC operating point of ``circuit``'s DC equivalent."""
    try:
        dc = dc_equivalent(circuit)
    except InvalidCircuitError as exc:
        return NonlinearResult(status=NonlinearStatus.INVALID,
                               diagnostics=(str(exc),)), None
    return solve_nonlinear_dc_state(dc, x_init=x_init)


def _precheck(circuit: Circuit) -> None:
    """Structural validation of the DC equivalent (config-level errors)."""
    build_mna_problem(dc_equivalent(circuit), allow_diodes=True,
                      allow_bjts=True, allow_mosfets=True, allow_jfets=True,
                      allow_diode_variants=True)


@dataclass(frozen=True)
class SweepPoint:
    """One solved (or failed) point; ``result`` links the full Newton result."""

    index: int
    label: str
    parameters: tuple  # ((address key, Decimal), ...) sorted by key
    status: NonlinearStatus
    init_mode: str  # cold | warm | warm-fallback-cold | cold-after-failure
    warm_start_used: bool
    fallback_used: bool
    iterations: int | None
    observables: dict = field(default_factory=dict)
    node_voltages: dict = field(default_factory=dict)
    diagnostic: str = ""
    newton_digest: str | None = None
    result: NonlinearResult | None = field(default=None, compare=False,
                                           repr=False)

    def to_dict(self) -> dict:
        return {
            "index": self.index, "label": self.label,
            "parameters": {k: str(v) for k, v in self.parameters},
            "status": self.status.value, "init_mode": self.init_mode,
            "warm_start_used": self.warm_start_used,
            "fallback_used": self.fallback_used,
            "iterations": self.iterations,
            "observables": {k: str(v) for k, v in
                            sorted(self.observables.items())},
            "node_voltages": {k: str(v) for k, v in
                              sorted(self.node_voltages.items())},
            "diagnostic": self.diagnostic,
            "newton_digest": self.newton_digest,
        }


def _iters(result: NonlinearResult) -> int | None:
    return result.system_summary.get("iterations") \
        if result.system_summary else None


def _make_point(index, label, params, result, state, init_mode, warm_used,
                fallback_used, observables) -> SweepPoint:
    obs: dict = {}
    volts: dict = {}
    diag = ""
    if result.status is NonlinearStatus.CONVERGED and state is not None:
        volts = {nv.node: nv.voltage.to_base() for nv in result.node_voltages}
        for spec in observables:
            obs[spec.key] = observable_value(spec, state)
    else:
        diag = "; ".join(result.diagnostics[-1:]) if result.diagnostics else ""
    return SweepPoint(
        index=index, label=label, parameters=params, status=result.status,
        init_mode=init_mode, warm_start_used=warm_used,
        fallback_used=fallback_used, iterations=_iters(result),
        observables=obs, node_voltages=volts, diagnostic=diag,
        newton_digest=(result.provenance or {}).get("solver_digest"),
        result=result)


def _drive_points(circuit: Circuit, plan: list[tuple[str, dict]],
                  observables: tuple, warm_start: bool) -> list[SweepPoint]:
    """Shared M1/M2/M3 point driver.

    ``plan`` is an ordered list of ``(label, {ParamAddress: Decimal})``.
    Warm start (R-02): point ``k`` starts from point ``k-1`` iff that point
    converged; a failed warm attempt is re-solved from the zero vector and
    the fallback is recorded. A failed previous point forces a cold start
    (``cold-after-failure``). Nothing here converts a failure to success.
    """
    points: list[SweepPoint] = []
    prev_x = None
    prev_failed = False
    for i, (label, assign) in enumerate(plan):
        params = tuple(sorted(((a.key, v) for a, v in assign.items()),
                              key=lambda kv: kv[0]))
        try:
            variant = substitute(circuit, assign)
        except InvalidCircuitError as exc:
            res = NonlinearResult(status=NonlinearStatus.INVALID,
                                  diagnostics=(str(exc),))
            points.append(_make_point(i, label, params, res, None, "cold",
                                      False, False, observables))
            prev_x, prev_failed = None, True
            continue
        if warm_start and prev_x is not None:
            res, st = solve_point(variant, x_init=prev_x)
            if res.status is NonlinearStatus.CONVERGED:
                mode, warm, fb = "warm", True, False
            else:
                res, st = solve_point(variant)
                mode, warm, fb = "warm-fallback-cold", True, True
        else:
            res, st = solve_point(variant)
            mode = "cold-after-failure" if (warm_start and prev_failed) \
                else "cold"
            warm = fb = False
        points.append(_make_point(i, label, params, res, st, mode, warm, fb,
                                  observables))
        if res.status is NonlinearStatus.CONVERGED and st is not None:
            prev_x, prev_failed = st.x, False
        else:
            prev_x, prev_failed = None, True
    return points


def _points_provenance(method: str, config_doc: dict, circuit: Circuit,
                       points: list[SweepPoint], extra: dict | None = None
                       ) -> dict:
    prov = {
        "engine": ENGINE_VERSION, "method": method,
        "config_digest": _sha(config_doc),
        "circuit_digest": circuit_digest(circuit),
        "n_points": len(points),
        "n_converged": sum(p.status is NonlinearStatus.CONVERGED
                           for p in points),
        "n_failed": sum(p.status is not NonlinearStatus.CONVERGED
                        for p in points),
        "n_warm_start_used": sum(p.warm_start_used for p in points),
        "n_fallback": sum(p.fallback_used for p in points),
        "dc_mapping": "C removed; L -> 0 V short; waves/IC ignored (DC value)",
    }
    if extra:
        prov.update(extra)
    return prov


def _result_digest(prov: dict, points: list[SweepPoint]) -> str:
    return _sha({"provenance": prov,
                 "points": [p.to_dict() for p in points]})


def _sweep_status(points: list[SweepPoint]) -> SweepStatus:
    return (SweepStatus.COMPLETED
            if all(p.status is NonlinearStatus.CONVERGED for p in points)
            else SweepStatus.COMPLETED_WITH_POINT_FAILURES)


def _config_error(exc: Exception):
    """Map a config/circuit exception to (sweep status enum name, message)."""
    if isinstance(exc, UnsupportedElementError):
        return "UNSUPPORTED", str(exc)
    return "INVALID", str(exc)


def _norm_observables(observables, circuit) -> tuple:
    obs = tuple(observables)
    keys = set()
    for o in obs:
        validate_observable(o, circuit)
        if o.key in keys:
            raise InvalidCircuitError(f"duplicate observable {o.key}")
        keys.add(o.key)
    return obs


# ---------------------------------------------------------------------------
# M1 / M2 - sweeps
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SweepConfig:
    """M1 DC sweep: ``target`` (independent V/I ``value``) over ``grid``."""

    target: ParamAddress
    grid: GridSpec
    observables: tuple = ()
    warm_start: bool = True


@dataclass(frozen=True)
class ParamSweepConfig:
    """M2 parameter sweep.

    ``mode='grid'``: ``target`` over ``grid``. ``mode='list'``: ``points``,
    an ordered sequence of ``{ParamAddress: value}`` dicts (user order is
    preserved and digested). ``mode='corners'``: ``corners`` is a sequence
    of ``(ParamAddress, low, high)``; the sampled corner SUBSET is
    ``all-low``, ``all-high`` and, per address (sorted), ``<key>:low`` /
    ``<key>:high`` with every other parameter nominal (full ``2^k``
    enumeration is M3).
    """

    mode: str
    target: ParamAddress | None = None
    grid: GridSpec | None = None
    points: tuple = ()
    corners: tuple = ()
    observables: tuple = ()
    warm_start: bool = True


@dataclass(frozen=True)
class SweepResult:
    status: SweepStatus
    points: tuple = ()
    provenance: dict = field(default_factory=dict)
    diagnostics: tuple = ()
    digest: str | None = None

    def to_dict(self) -> dict:
        return {"status": self.status.value,
                "points": [p.to_dict() for p in self.points],
                "provenance": self.provenance,
                "diagnostics": list(self.diagnostics),
                "digest": self.digest}


def _sweep_fail(status: SweepStatus, msg: str) -> SweepResult:
    return SweepResult(status=status, diagnostics=(msg,),
                       provenance={"engine": ENGINE_VERSION})


def _finish_sweep(method, config_doc, circuit, plan, observables,
                  warm_start, extra=None) -> SweepResult:
    points = _drive_points(circuit, plan, observables, warm_start)
    prov = _points_provenance(method, config_doc, circuit, points, extra)
    prov["warm_start_enabled"] = warm_start
    return SweepResult(status=_sweep_status(points), points=tuple(points),
                       provenance=prov, digest=_result_digest(prov, points))


def _grid_doc(target_key: str, values: tuple) -> dict:
    return {"target": target_key, "values": [str(v) for v in values]}


def solve_dc_sweep(circuit: Circuit, config: SweepConfig) -> SweepResult:
    """M1: sweep an independent V/I source over a linear/log/list grid."""
    try:
        if not isinstance(config, SweepConfig):
            raise InvalidCircuitError("config must be a SweepConfig")
        rp = resolve_param(circuit, config.target)
        if rp.component.type.upper() not in ("V", "I") or \
                config.target.field != "value":
            raise InvalidCircuitError(
                f"{config.target.key}: DC sweep target must be the value of "
                f"an independent V or I source")
        values = expand_grid(config.grid)
        for v in values:
            coerce_value(v, rp.dimension, rp.domain, config.target.key)
        observables = _norm_observables(config.observables, circuit)
        _precheck(circuit)
    except (InvalidCircuitError, UnsupportedElementError,
            *_INVALID_ERRORS) as exc:
        kind, msg = _config_error(exc)
        return _sweep_fail(SweepStatus[kind], msg)
    plan = [(f"{config.target.key}={v}", {config.target: v}) for v in values]
    doc = {"kind": "dc-sweep", "grid": _grid_doc(config.target.key, values),
           "observables": [o.key for o in observables],
           "warm_start": config.warm_start}
    return _finish_sweep("dc-sweep", doc, circuit, plan, observables,
                         config.warm_start,
                         {"grid_digest": _sha(doc["grid"])})


def _corner_plan(corners: tuple, nominal_of) -> list[tuple[str, dict]]:
    ent = sorted(corners, key=lambda c: c[0].key)
    lows = {a: lo for a, lo, _ in ent}
    highs = {a: hi for a, _, hi in ent}
    plan = [("all-low", dict(lows)), ("all-high", dict(highs))]
    if len(ent) > 1:
        for a, lo, hi in ent:
            plan.append((f"{a.key}:low", {a: lo}))
            plan.append((f"{a.key}:high", {a: hi}))
    return plan


def _norm_corner_entries(circuit, entries) -> tuple:
    out, seen = [], set()
    for e in entries:
        if not (isinstance(e, (tuple, list)) and len(e) == 3):
            raise InvalidCircuitError(
                "each corner entry must be (ParamAddress, low, high)")
        addr, lo, hi = e
        rp = resolve_param(circuit, addr)
        if addr.key in seen:
            raise InvalidCircuitError(f"duplicate parameter {addr.key}")
        seen.add(addr.key)
        lo_v = coerce_value(lo, rp.dimension, rp.domain, f"{addr.key} low")
        hi_v = coerce_value(hi, rp.dimension, rp.domain, f"{addr.key} high")
        if not lo_v < hi_v:
            raise InvalidCircuitError(
                f"{addr.key}: low must be < high (got {lo_v}, {hi_v})")
        out.append((addr, lo_v, hi_v))
    return tuple(out)


def solve_param_sweep(circuit: Circuit, config: ParamSweepConfig
                      ) -> SweepResult:
    """M2: parameter sweep over the closed :data:`PARAM_REGISTRY`."""
    try:
        if not isinstance(config, ParamSweepConfig):
            raise InvalidCircuitError("config must be a ParamSweepConfig")
        observables = _norm_observables(config.observables, circuit)
        _precheck(circuit)
        if config.mode == "grid":
            if config.target is None or config.grid is None:
                raise InvalidCircuitError("grid mode needs target and grid")
            rp = resolve_param(circuit, config.target)
            values = expand_grid(config.grid)
            for v in values:
                coerce_value(v, rp.dimension, rp.domain, config.target.key)
            plan = [(f"{config.target.key}={v}", {config.target: v})
                    for v in values]
            doc = {"kind": "param-grid",
                   "grid": _grid_doc(config.target.key, values)}
        elif config.mode == "list":
            if not config.points:
                raise InvalidCircuitError("list mode needs >= 1 point")
            if len(config.points) > MAX_SWEEP_POINTS:
                raise InvalidCircuitError(
                    f"{len(config.points)} points > "
                    f"MAX_SWEEP_POINTS={MAX_SWEEP_POINTS}")
            plan, ldoc = [], []
            for i, pt in enumerate(config.points):
                if not isinstance(pt, dict) or not pt:
                    raise InvalidCircuitError(
                        f"point {i} must be a non-empty dict")
                assign = {}
                for a, v in pt.items():
                    rp = resolve_param(circuit, a)
                    assign[a] = coerce_value(v, rp.dimension, rp.domain,
                                             a.key)
                plan.append((f"point-{i}", assign))
                ldoc.append({a.key: str(v) for a, v in assign.items()})
            doc = {"kind": "param-list", "points": ldoc}
        elif config.mode == "corners":
            ent = _norm_corner_entries(circuit, config.corners)
            if not ent:
                raise InvalidCircuitError("corners mode needs >= 1 parameter")
            if len(ent) > MAX_WORST_PARAMS:
                raise InvalidCircuitError(
                    f"{len(ent)} parameters > MAX_WORST_PARAMS="
                    f"{MAX_WORST_PARAMS}")
            plan = _corner_plan(ent, None)
            doc = {"kind": "param-corners",
                   "corners": [(a.key, str(lo), str(hi))
                               for a, lo, hi in sorted(
                                   ent, key=lambda c: c[0].key)]}
        else:
            raise InvalidCircuitError(
                f"unknown mode {config.mode!r} (grid|list|corners)")
    except (InvalidCircuitError, UnsupportedElementError,
            *_INVALID_ERRORS) as exc:
        kind, msg = _config_error(exc)
        return _sweep_fail(SweepStatus[kind], msg)
    doc["observables"] = [o.key for o in observables]
    doc["warm_start"] = config.warm_start
    return _finish_sweep(f"param-sweep/{config.mode}", doc, circuit, plan,
                         observables, config.warm_start,
                         {"grid_digest": _sha(doc)})


# ---------------------------------------------------------------------------
# M3 - worst-case corners
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WorstCaseConfig:
    """``parameters``: sequence of ``(ParamAddress, low, high)`` (1 <= k <=
    ``MAX_WORST_PARAMS``); ``observables``: at least one."""

    parameters: tuple
    observables: tuple
    warm_start: bool = True


@dataclass(frozen=True)
class WorstCaseResult:
    status: WorstCaseStatus
    corners: tuple = ()
    extrema: dict = field(default_factory=dict)
    failed_indices: tuple = ()
    scope: str = CORNER_HONESTY
    provenance: dict = field(default_factory=dict)
    diagnostics: tuple = ()
    digest: str | None = None

    def to_dict(self) -> dict:
        return {"status": self.status.value,
                "corners": [c.to_dict() for c in self.corners],
                "extrema": {k: _ext_doc(v) for k, v in self.extrema.items()},
                "failed_indices": list(self.failed_indices),
                "scope": self.scope, "provenance": self.provenance,
                "diagnostics": list(self.diagnostics),
                "digest": self.digest}


def _wc_fail(status: WorstCaseStatus, msg: str) -> WorstCaseResult:
    return WorstCaseResult(status=status, diagnostics=(msg,),
                           provenance={"engine": ENGINE_VERSION})


def solve_worst_case(circuit: Circuit, config: WorstCaseConfig
                     ) -> WorstCaseResult:
    """M3: enumerate all ``2^k`` corners, solve each, reduce per observable.

    Enumeration order: addresses sorted by key, first address most
    significant, ``low`` before ``high``. Ties: first corner in that order
    wins (all tied corner indices are listed). The extremum is a *corner*
    extremum, never claimed global.
    """
    try:
        if not isinstance(config, WorstCaseConfig):
            raise InvalidCircuitError("config must be a WorstCaseConfig")
        ent = _norm_corner_entries(circuit, config.parameters)
        if not ent:
            raise InvalidCircuitError(
                "worst-case needs k >= 1 parameters (k=0 has no range)")
        if len(ent) > MAX_WORST_PARAMS:
            raise InvalidCircuitError(
                f"k={len(ent)} parameters > MAX_WORST_PARAMS="
                f"{MAX_WORST_PARAMS} (2^k corner wall)")
        if not config.observables:
            raise InvalidCircuitError("worst-case needs >= 1 observable")
        observables = _norm_observables(config.observables, circuit)
        _precheck(circuit)
    except (InvalidCircuitError, UnsupportedElementError,
            *_INVALID_ERRORS) as exc:
        kind, msg = _config_error(exc)
        return _wc_fail(WorstCaseStatus[kind], msg)
    ent = tuple(sorted(ent, key=lambda c: c[0].key))
    plan = []
    for bits in product((0, 1), repeat=len(ent)):
        assign = {a: (hi if b else lo) for (a, lo, hi), b in zip(ent, bits)}
        label = "|".join(f"{a.key}={'high' if b else 'low'}"
                         for (a, _, _), b in zip(ent, bits))
        plan.append((label, assign))
    points = _drive_points(circuit, plan, observables, config.warm_start)
    extrema: dict = {}
    for spec in observables:
        ok = [p for p in points if spec.key in p.observables]
        rec: dict = {"dimension": list(spec.dimension), "min": None,
                     "max": None}
        if ok:
            best_lo = best_hi = ok[0]
            for p in ok[1:]:
                if p.observables[spec.key] < best_lo.observables[spec.key]:
                    best_lo = p
                if p.observables[spec.key] > best_hi.observables[spec.key]:
                    best_hi = p
            for name, best in (("min", best_lo), ("max", best_hi)):
                val = best.observables[spec.key]
                rec[name] = {
                    "value": val, "arg_corner_index": best.index,
                    "arg_corner": best.label,
                    "tied_corner_indices": [p.index for p in ok
                                            if p.observables[spec.key] == val]}
        extrema[spec.key] = rec
    doc = {"kind": "worst-case",
           "parameters": [(a.key, str(lo), str(hi)) for a, lo, hi in ent],
           "observables": [o.key for o in observables],
           "warm_start": config.warm_start}
    prov = _points_provenance("worst-case-corners", doc, circuit, points,
                              {"k": len(ent), "n_corners": len(points),
                               "extremum_scope": CORNER_HONESTY})
    status = (WorstCaseStatus.COMPLETED
              if all(p.status is NonlinearStatus.CONVERGED for p in points)
              else WorstCaseStatus.COMPLETED_WITH_POINT_FAILURES)
    failed = tuple(p.index for p in points
                   if p.status is not NonlinearStatus.CONVERGED)
    digest = _sha({"provenance": prov,
                   "points": [p.to_dict() for p in points],
                   "extrema": {k: _ext_doc(v) for k, v in extrema.items()}})
    return WorstCaseResult(status=status, corners=tuple(points),
                           extrema=extrema, failed_indices=failed,
                           provenance=prov, digest=digest)


def _ext_doc(rec: dict) -> dict:
    out = {}
    for k, v in rec.items():
        out[k] = ({kk: (str(vv) if isinstance(vv, Decimal) else vv)
                   for kk, vv in v.items()} if isinstance(v, dict) else v)
    return out


# ---------------------------------------------------------------------------
# M5 - native Monte Carlo
# ---------------------------------------------------------------------------

_TWO53 = Decimal(2 ** 53)


def _exact_ctx():
    """Context wide enough that ``bits / 2^53`` is EXACT (<= 53 digits)."""
    return make_context(extra=40)


def _frac(bits: int, ectx) -> Decimal:
    return ectx.divide(Decimal(bits), _TWO53)


@dataclass(frozen=True)
class UniformDist:
    low: Decimal
    high: Decimal


@dataclass(frozen=True)
class NormalDist:
    """Gaussian with hard validity bounds ``[min, max]`` (samples outside
    are recorded as FAILED iterations - never clamped, never resampled)."""

    mean: Decimal
    std: Decimal
    min: Decimal
    max: Decimal


@dataclass(frozen=True)
class MCConfig:
    """``distributions``: sequence of ``(ParamAddress, UniformDist|NormalDist)``;
    ``seed``: REQUIRED int >= 0; ``base`` must be ``"dc-op"``."""

    iterations: int
    distributions: tuple
    seed: int | None = None
    observables: tuple = ()
    base: str = "dc-op"


@dataclass(frozen=True)
class MCIteration:
    index: int
    sub_seeds: tuple
    parameters: tuple
    status: str  # "ok" | "invalid_sample" | Newton status value
    init_mode: str
    iterations: int | None
    observables: dict = field(default_factory=dict)
    diagnostic: str = ""

    def to_dict(self) -> dict:
        return {"index": self.index, "sub_seeds": list(self.sub_seeds),
                "parameters": {k: str(v) for k, v in self.parameters},
                "status": self.status, "init_mode": self.init_mode,
                "iterations": self.iterations,
                "observables": {k: str(v) for k, v in
                                sorted(self.observables.items())},
                "diagnostic": self.diagnostic}


@dataclass(frozen=True)
class MCResult:
    status: MCStatus
    iterations: tuple = ()
    statistics: dict = field(default_factory=dict)
    failure_count: int = 0
    failure_indices: tuple = ()
    failure_statuses: dict = field(default_factory=dict)
    plan_digest: str | None = None
    provenance: dict = field(default_factory=dict)
    diagnostics: tuple = ()
    digest: str | None = None

    def to_dict(self) -> dict:
        return {"status": self.status.value,
                "iterations": [i.to_dict() for i in self.iterations],
                "statistics": {k: _stat_doc(v)
                               for k, v in self.statistics.items()},
                "failure_count": self.failure_count,
                "failure_indices": list(self.failure_indices),
                "failure_statuses": dict(self.failure_statuses),
                "plan_digest": self.plan_digest,
                "provenance": self.provenance,
                "diagnostics": list(self.diagnostics),
                "digest": self.digest}


def _stat_doc(st: dict) -> dict:
    return {k: (str(v) if isinstance(v, Decimal) else
                ({kk: str(vv) for kk, vv in v.items()}
                 if isinstance(v, dict) else v))
            for k, v in st.items()}


def native_statistics(values: list[Decimal]) -> dict:
    """Descriptive statistics in Decimal (no float, no numpy).

    ``variance``/``std`` use the sample estimator (n-1; ``None`` for n<2);
    percentiles use sorted-rank linear interpolation ``h=(n-1)p/100``.
    """
    ctx = make_context()
    n = len(values)
    if n == 0:
        return {"n": 0}
    vs = sorted(values)
    total = Decimal(0)
    for v in vs:
        total = ctx.add(total, v)
    mean = ctx.divide(total, Decimal(n))
    var = std = None
    if n > 1:
        acc = Decimal(0)
        for v in vs:
            d = ctx.subtract(v, mean)
            acc = ctx.add(acc, ctx.multiply(d, d))
        var = ctx.divide(acc, Decimal(n - 1))
        std = ctx.sqrt(var)
    pct = {}
    for p in (5, 25, 50, 75, 95):
        h = ctx.divide(ctx.multiply(Decimal(n - 1), Decimal(p)),
                       Decimal(100))
        lo = int(h)
        if lo + 1 < n:
            frac = ctx.subtract(h, Decimal(lo))
            val = ctx.add(vs[lo], ctx.multiply(
                frac, ctx.subtract(vs[lo + 1], vs[lo])))
        else:
            val = vs[lo]
        pct[f"p{p}"] = val
    return {"n": n, "mean": mean, "variance": var, "std": std,
            "min": vs[0], "max": vs[-1], "percentiles": pct}


def _draw(dist, sub_seed: int) -> Decimal:
    """One deterministic sample from ``dist`` seeded by ``sub_seed``."""
    ctx = make_context()
    ectx = _exact_ctx()
    rng = random.Random(sub_seed)
    if isinstance(dist, UniformDist):
        u = _frac(rng.getrandbits(53), ectx)
        return ctx.add(dist.low,
                       ctx.multiply(u, ctx.subtract(dist.high, dist.low)))
    u1 = _frac(rng.getrandbits(53) + 1, ectx)  # (0, 1]: ln finite
    u2 = _frac(rng.getrandbits(53), ectx)
    radius = ctx.sqrt(ctx.multiply(Decimal(-2), ctx.ln(u1)))
    angle = ctx.multiply(ctx.multiply(Decimal(2), decimal_pi(ctx)), u2)
    z = ctx.multiply(radius, decimal_cos(angle, ctx))
    return ctx.add(dist.mean, ctx.multiply(dist.std, z))


def _validate_dist(addr: ParamAddress, dist) -> None:
    if isinstance(dist, UniformDist):
        lo = _grid_decimal(dist.low, f"{addr.key} low")
        hi = _grid_decimal(dist.high, f"{addr.key} high")
        if not lo < hi:
            raise InvalidCircuitError(f"{addr.key}: low must be < high")
    elif isinstance(dist, NormalDist):
        m = _grid_decimal(dist.mean, f"{addr.key} mean")
        s = _grid_decimal(dist.std, f"{addr.key} std")
        lo = _grid_decimal(dist.min, f"{addr.key} min")
        hi = _grid_decimal(dist.max, f"{addr.key} max")
        if s < 0:
            raise InvalidCircuitError(f"{addr.key}: std must be >= 0")
        if not lo < hi:
            raise InvalidCircuitError(f"{addr.key}: min must be < max")
        if not lo <= m <= hi:
            raise InvalidCircuitError(f"{addr.key}: mean outside [min, max]")
    else:
        raise InvalidCircuitError(
            f"{addr.key}: unsupported distribution "
            f"{type(dist).__name__} (UniformDist | NormalDist)")


def _mc_fail(status: MCStatus, msg: str) -> MCResult:
    return MCResult(status=status, diagnostics=(msg,),
                    provenance={"engine": ENGINE_VERSION})


def build_mc_plan(distributions: tuple, iterations: int, seed: int
                  ) -> list[list[tuple]]:
    """Deterministic plan: ``plan[i] = [(addr, sub_seed, sample), ...]``.

    Master ``Random(seed)`` yields one 64-bit sub-seed per (iteration,
    address) in (index, sorted-address) order; each sample is drawn from its
    own ``Random(sub_seed)`` (exact binary fractions, Decimal Box-Muller).
    """
    dists = sorted(distributions, key=lambda d: d[0].key)
    master = random.Random(seed)
    plan = []
    for _ in range(iterations):
        row = []
        for addr, dist in dists:
            sub = master.getrandbits(64)
            row.append((addr, sub, _draw(dist, sub)))
        plan.append(row)
    return plan


def _dist_doc(d) -> dict:
    if isinstance(d, UniformDist):
        return {"type": "uniform", "low": str(d.low), "high": str(d.high)}
    return {"type": "normal", "mean": str(d.mean), "std": str(d.std),
            "min": str(d.min), "max": str(d.max)}


def run_monte_carlo_native(circuit: Circuit, config: MCConfig) -> MCResult:
    """M5: native Monte Carlo over the DC operating point (cold solves)."""
    try:
        if not isinstance(config, MCConfig):
            raise InvalidCircuitError("config must be an MCConfig")
        if config.base != "dc-op":
            raise UnsupportedElementError(
                f"MC base {config.base!r} unsupported (only 'dc-op'; "
                f"transient-base Monte Carlo is out of F8-M scope)")
        if config.seed is None:
            raise InvalidCircuitError(
                "seed is required (no random fallback in native MC)")
        if isinstance(config.seed, bool) or not isinstance(config.seed, int) \
                or config.seed < 0:
            raise InvalidCircuitError("seed must be an int >= 0")
        n = config.iterations
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            raise InvalidCircuitError("iterations must be an int >= 1")
        if n > MAX_MC_ITERATIONS:
            raise InvalidCircuitError(
                f"iterations {n} > MAX_MC_ITERATIONS={MAX_MC_ITERATIONS}")
        if not config.distributions:
            raise InvalidCircuitError("at least one distribution required")
        seen = set()
        for e in config.distributions:
            if not (isinstance(e, (tuple, list)) and len(e) == 2):
                raise InvalidCircuitError(
                    "each distribution entry must be (ParamAddress, dist)")
            addr, dist = e
            resolve_param(circuit, addr)
            if addr.key in seen:
                raise InvalidCircuitError(f"duplicate parameter {addr.key}")
            seen.add(addr.key)
            _validate_dist(addr, dist)
        observables = _norm_observables(config.observables, circuit)
        _precheck(circuit)
    except (InvalidCircuitError, UnsupportedElementError,
            *_INVALID_ERRORS) as exc:
        kind, msg = _config_error(exc)
        return _mc_fail(MCStatus[kind], msg)

    dists = tuple(sorted(config.distributions, key=lambda d: d[0].key))
    plan = build_mc_plan(dists, n, config.seed)
    plan_digest = _sha({
        "seed": config.seed, "n": n,
        "distributions": [(a.key, _dist_doc(d)) for a, d in dists],
        "samples": [[(a.key, s, str(v)) for a, s, v in row]
                    for row in plan]})
    iters: list[MCIteration] = []
    for i, row in enumerate(plan):
        assign = {a: v for a, _, v in row}
        params = tuple((a.key, v) for a, _, v in row)
        subs = tuple(s for _, s, _ in row)
        bad = next((f"{a.key}: sample {v} outside [{d.min}, {d.max}]"
                    for (a, _, v), (_, d) in zip(row, dists)
                    if isinstance(d, NormalDist)
                    and not d.min <= v <= d.max), None)
        if bad is None:
            try:
                variant = substitute(circuit, assign)
            except InvalidCircuitError as exc:
                bad = str(exc)
        if bad is not None:
            iters.append(MCIteration(i, subs, params, "invalid_sample",
                                     "none", None, diagnostic=bad))
            continue
        res, st = solve_point(variant)  # cold: never reuses prior state
        if res.status is NonlinearStatus.CONVERGED and st is not None:
            obs = {o.key: observable_value(o, st) for o in observables}
            iters.append(MCIteration(i, subs, params, "ok", "cold",
                                     _iters(res), obs))
        else:
            iters.append(MCIteration(
                i, subs, params, res.status.value, "cold", _iters(res),
                diagnostic="; ".join(res.diagnostics[-1:])))
    failed = [it for it in iters if it.status != "ok"]
    stats = {}
    for o in observables:
        vals = [it.observables[o.key] for it in iters if it.status == "ok"]
        stats[o.key] = native_statistics(vals)
    fstat: dict = {}
    for it in failed:
        fstat[it.status] = fstat.get(it.status, 0) + 1
    doc = {"kind": "monte-carlo", "n": n, "seed": config.seed,
           "base": config.base,
           "distributions": [(a.key, _dist_doc(d)) for a, d in dists],
           "observables": [o.key for o in observables]}
    prov = {"engine": ENGINE_VERSION, "method": "monte-carlo-native/dc-op",
            "config_digest": _sha(doc), "circuit_digest": circuit_digest(circuit),
            "seed": config.seed, "plan_digest": plan_digest,
            "n_iterations": n, "n_ok": n - len(failed),
            "n_failed": len(failed), "init_mode": "cold (every iteration)",
            "rng": "random.Random(seed).getrandbits(64) sub-seeds; "
                   "getrandbits(53)/2^53 exact fractions; Decimal Box-Muller",
            "dc_mapping": "C removed; L -> 0 V short; waves/IC ignored"}
    body = {"provenance": prov, "iterations": [i.to_dict() for i in iters],
            "statistics": {k: _stat_doc(v) for k, v in stats.items()}}
    return MCResult(
        status=(MCStatus.COMPLETED if not failed
                else MCStatus.COMPLETED_WITH_FAILURES),
        iterations=tuple(iters), statistics=stats,
        failure_count=len(failed),
        failure_indices=tuple(it.index for it in failed),
        failure_statuses=dict(sorted(fstat.items())),
        plan_digest=plan_digest, provenance=prov, digest=_sha(body))
