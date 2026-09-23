"""F8-J: Small-Signal AC Analysis around a DC Operating Point.

Formulation and solution of linearized frequency-domain (AC) problems
starting from a converged DC operating point x0:

    f(x0 + dx) ~= f(x0) + J(x0) dx
    A_ac(j*w) * X~ = b~

Separates DC nonlinear solving (solve_nonlinear_dc) from complex AC
MNA linear solving (math.linsolve with NumericMode.HIGH_PRECISION).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, Overflow

from academic_core.domain.engineering.ac.errors import (
    ACFrequencyError,
    ACModeError,
    ACPhaseError,
    CircularControlError,
    DimensionalityError,
    FloatingCircuitError,
    InvalidCircuitError,
    MissingReferenceError,
    UnsupportedElementError,
)
from academic_core.domain.engineering.ac.operating_point import (
    ACOperatingPoint,
    AMPLITUDE_CONVENTION,
    PHASE_CONVENTION,
    TIME_CONVENTION,
)
from academic_core.domain.engineering.ac.phasors import (
    fmt_cartesian,
    magnitude,
    phase,
)
from academic_core.domain.engineering.ac.solution import (
    ACStatus,
    BranchCurrent,
    BranchVoltage,
    NodePhasor,
    Phasor,
)
from academic_core.domain.engineering.ac.topology import (
    check_connected,
    cycle_basis,
    reference_net,
)
from academic_core.domain.engineering.mna.result import (
    AnalysisResult,
    SolveStatus as LinearDCStatus,
)
from academic_core.domain.engineering.mna.solver import (
    fundamental_cycle_chords,
    solve_linear_dc,
)
from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.math.decimal_complex import DecimalComplex
from academic_core.domain.engineering.math.linsolve import (
    ComplexLinearProblem,
    NumericMode,
    SolveStatus as LinearStatus,
    solve as linsolve,
)
from academic_core.domain.engineering.math.trig import (
    decimal_cos,
    decimal_pi,
    decimal_sin,
    make_context,
)
from academic_core.domain.engineering.mna.bjt import (
    BJTParams,
    bjt_conductances,
    bjt_jacobian,
    bjt_terminal_currents,
    extract_bjt_params,
)
from academic_core.domain.engineering.mna.dependent import (
    DEPENDENT_TYPES,
    VOLTAGE_BRANCH_TYPES,
    check_control_cycles,
    resolution_order,
    validate_dependent_structure,
)
from academic_core.domain.engineering.mna.mosfet import (
    MOSParams,
    extract_mosfet_params,
    mos_conductances,
    mos_jacobian,
    mos_region,
    mos_terminal_currents,
)
from academic_core.domain.engineering.mna.jfet import (
    JFETParams,
    extract_jfet_params,
    jfet_conductances,
    jfet_jacobian,
    jfet_region,
    jfet_terminal_currents,
)
from academic_core.domain.engineering.mna.diode import (
    DiodeParams,
    extract_diode_params,
    extract_diode_variant_params,
    shockley_conductance,
    shockley_current,
    variant_conductance,
    variant_current,
)
from academic_core.domain.engineering.mna.nonlinear import (
    NonlinearResult,
    NonlinearStatus,
    solve_nonlinear_dc,
)
from academic_core.domain.engineering.units import (
    CURRENT,
    DIMENSIONLESS,
    FREQUENCY,
    VOLTAGE,
    Quantity,
    parse_quantity,
    parse_unit,
)

ENGINE_VERSION = "f8j-small-signal-ac/1.0"
SUPPORTED_TYPES = frozenset({"R", "L", "C", "V", "I", "E", "G", "H", "F",
                             "O", "T", "D", "Q", "M", "J"})

_INVALID_ERRORS = (
    InvalidCircuitError,
    MissingReferenceError,
    FloatingCircuitError,
    DimensionalityError,
    ACFrequencyError,
    ACPhaseError,
    ACModeError,
    CircularControlError,
)


@dataclass(frozen=True)
class DiodeSmallSignalParams:
    """Small-signal linearized parameters of a diode at DC operating point."""

    ref: str
    anode: str
    cathode: str
    v_d0: Decimal  # DC bias voltage V_D0 = V_A0 - V_K0 (V)
    i_d0: Decimal  # DC bias current I_D0 (A)
    g_d: Decimal   # Dynamic conductance dI/dV (S)
    r_d: Decimal   # Dynamic resistance 1/g_d (ohm)
    kind: str = "RECT"  # F8-K diode kind (RECT/ZENER/LED/SCHOTTKY/PHOTO)


@dataclass(frozen=True)
class MOSFETSmallSignalParams:
    """Small-signal linearized parameters of a Level-1 MOSFET at DC bias."""

    ref: str
    drain: str
    gate: str
    source: str
    bulk: str
    polarity: str  # "NMOS" | "PMOS"
    region: str  # "cutoff" | "triode" | "saturation"
    v_gs0: Decimal  # DC gate-source bias (signed actual, V)
    v_ds0: Decimal  # DC drain-source bias (signed actual, V)
    i_d0: Decimal  # DC drain terminal current (A)
    g_m: Decimal  # Transconductance dID/dVG (S)
    g_ds: Decimal  # Output conductance dID/dVD (S)
    g_mb: Decimal  # Body transconductance dID/dVB (S)
    jacobian: tuple[tuple[Decimal, Decimal, Decimal, Decimal], ...]  # 4x4


@dataclass(frozen=True)
class JFETSmallSignalParams:
    """Small-signal linearized parameters of a square-law JFET at DC bias."""

    ref: str
    drain: str
    gate: str
    source: str
    polarity: str  # "NCHAN" | "PCHAN"
    region: str  # "cutoff" | "triode" | "saturation"
    v_gs0: Decimal  # DC gate-source bias (signed actual, V)
    v_ds0: Decimal  # DC drain-source bias (signed actual, V)
    i_d0: Decimal  # DC drain terminal current (A)
    g_m: Decimal  # Transconductance dID/dVG (S)
    g_ds: Decimal  # Output conductance dID/dVD (S)
    jacobian: tuple[tuple[Decimal, Decimal, Decimal], ...]  # 3x3


@dataclass(frozen=True)
class BJTSmallSignalParams:
    """Small-signal linearized parameters of an Ebers-Moll BJT at DC operating point."""

    ref: str
    collector: str
    base: str
    emitter: str
    polarity: str  # "NPN" | "PNP"
    v_c0: Decimal  # DC collector node potential (V)
    v_b0: Decimal  # DC base node potential (V)
    v_e0: Decimal  # DC emitter node potential (V)
    v_be0: Decimal  # DC V_BE (V)
    v_ce0: Decimal  # DC V_CE (V)
    i_c0: Decimal   # DC collector terminal current (A)
    i_b0: Decimal   # DC base terminal current (A)
    i_e0: Decimal   # DC emitter terminal current (A)
    g_m: Decimal    # Transconductance (S)
    r_pi: Decimal   # Dynamic input resistance (ohm)
    g_F: Decimal    # Forward junction conductance (S)
    g_R: Decimal    # Reverse junction conductance (S)
    jacobian: tuple[tuple[Decimal, Decimal, Decimal], ...]  # 3x3 terminal conductance Jacobian


@dataclass(frozen=True)
class SmallSignalACResult:
    """Structured result of small-signal AC analysis."""

    status: ACStatus
    operating_point: ACOperatingPoint | None = None
    dc_operating_point: NonlinearResult | AnalysisResult | None = None
    node_voltages: tuple[NodePhasor, ...] = ()
    branch_currents: tuple[BranchCurrent, ...] = ()
    branch_voltages: tuple[BranchVoltage, ...] = ()
    diode_parameters: tuple[DiodeSmallSignalParams, ...] = ()
    bjt_parameters: tuple[BJTSmallSignalParams, ...] = ()
    mosfet_parameters: tuple[MOSFETSmallSignalParams, ...] = ()
    jfet_parameters: tuple[JFETSmallSignalParams, ...] = ()
    kcl_max_residual: Decimal | None = None
    kvl_max_residual: Decimal | None = None
    solver_result: object | None = None
    numeric_mode: NumericMode | None = None
    provenance: dict = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()
    digest: str = ""

    def voltage_of(self, node: str) -> Phasor | None:
        """Get complex phasor voltage for node name."""
        for nv in self.node_voltages:
            if nv.node == node:
                return nv.phasor
        return None

    def current_of(self, ref: str) -> Phasor | None:
        """Get complex phasor current for branch/component ref."""
        target = ref.upper()
        for bc in self.branch_currents:
            if bc.ref.upper() == target:
                return bc.current
        return None

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "operating_point": (
                self.operating_point.to_dict() if self.operating_point else None
            ),
            "dc_operating_point": (
                self.dc_operating_point.to_dict() if self.dc_operating_point else None
            ),
            "node_voltages": {
                nv.node: fmt_cartesian(nv.phasor) for nv in self.node_voltages
            },
            "branch_currents": {
                bc.ref: {
                    "current": fmt_cartesian(bc.current),
                    "convention": bc.convention,
                }
                for bc in self.branch_currents
            },
            "branch_voltages": {
                bv.ref: {
                    "voltage": fmt_cartesian(bv.voltage),
                    "convention": bv.convention,
                }
                for bv in self.branch_voltages
            },
            "diode_parameters": [
                {
                    "ref": dp.ref,
                    "anode": dp.anode,
                    "cathode": dp.cathode,
                    "v_d0": str(dp.v_d0),
                    "i_d0": str(dp.i_d0),
                    "g_d": str(dp.g_d),
                    "r_d": str(dp.r_d),
                    "kind": dp.kind,
                }
                for dp in self.diode_parameters
            ],
            "bjt_parameters": [
                {
                    "ref": bp.ref,
                    "collector": bp.collector,
                    "base": bp.base,
                    "emitter": bp.emitter,
                    "polarity": bp.polarity,
                    "v_c0": str(bp.v_c0),
                    "v_b0": str(bp.v_b0),
                    "v_e0": str(bp.v_e0),
                    "v_be0": str(bp.v_be0),
                    "v_ce0": str(bp.v_ce0),
                    "i_c0": str(bp.i_c0),
                    "i_b0": str(bp.i_b0),
                    "i_e0": str(bp.i_e0),
                    "g_m": str(bp.g_m),
                    "r_pi": str(bp.r_pi),
                    "g_F": str(bp.g_F),
                    "g_R": str(bp.g_R),
                }
                for bp in self.bjt_parameters
            ],
            "mosfet_parameters": [
                {
                    "ref": mp.ref,
                    "drain": mp.drain,
                    "gate": mp.gate,
                    "source": mp.source,
                    "bulk": mp.bulk,
                    "polarity": mp.polarity,
                    "region": mp.region,
                    "v_gs0": str(mp.v_gs0),
                    "v_ds0": str(mp.v_ds0),
                    "i_d0": str(mp.i_d0),
                    "g_m": str(mp.g_m),
                    "g_ds": str(mp.g_ds),
                    "g_mb": str(mp.g_mb),
                }
                for mp in self.mosfet_parameters
            ],
            "jfet_parameters": [
                {
                    "ref": jp.ref,
                    "drain": jp.drain,
                    "gate": jp.gate,
                    "source": jp.source,
                    "polarity": jp.polarity,
                    "region": jp.region,
                    "v_gs0": str(jp.v_gs0),
                    "v_ds0": str(jp.v_ds0),
                    "i_d0": str(jp.i_d0),
                    "g_m": str(jp.g_m),
                    "g_ds": str(jp.g_ds),
                }
                for jp in self.jfet_parameters
            ],
            "kcl_max_residual": str(self.kcl_max_residual) if self.kcl_max_residual is not None else None,
            "kvl_max_residual": str(self.kvl_max_residual) if self.kvl_max_residual is not None else None,
            "numeric_mode": self.numeric_mode.value if self.numeric_mode else None,
            "provenance": self.provenance,
            "diagnostics": list(self.diagnostics),
            "digest": self.digest,
        }


def _phase_decimal(raw: object) -> Decimal:
    if isinstance(raw, bool):
        raise ACPhaseError("bool phase is rejected")
    if isinstance(raw, int):
        return Decimal(raw)
    if isinstance(raw, Decimal):
        if not raw.is_finite():
            raise ACPhaseError(f"non-finite phase {raw!r}")
        return raw
    if isinstance(raw, str):
        try:
            v = Decimal(raw.strip())
        except Exception:
            raise ACPhaseError(f"unparseable phase {raw!r}") from None
        if not v.is_finite():
            raise ACPhaseError(f"non-finite phase {raw!r}")
        return v
    raise ACPhaseError(f"unsupported phase type: {type(raw).__name__}")


def _extract_source_ac_phasor(comp: Component, ctx) -> DecimalComplex:
    """Extract small-signal AC excitation phasor for V or I component.

    If no AC parameters are specified, returns 0 (pure DC source).
    """
    params = dict(comp.parameters or {})
    mag_val: Decimal | None = None
    phase_val: Decimal = Decimal(0)
    phase_unit: str = "deg"

    if "ac_mag" in params:
        raw_mag = params["ac_mag"]
        if isinstance(raw_mag, Quantity):
            mag_val = raw_mag.to_base()
        elif isinstance(raw_mag, str):
            mag_val = parse_quantity(raw_mag).to_base()
        elif isinstance(raw_mag, (int, Decimal)):
            mag_val = Decimal(raw_mag)
        else:
            raise ACPhaseError(f"{comp.ref}: invalid ac_mag type {type(raw_mag).__name__}")
        raw_ph = params.get("ac_phase", params.get("phase", 0))
        phase_val = _phase_decimal(raw_ph)
        phase_unit = str(params.get("phase_unit", "deg")).strip().lower()

    elif params.get("ac") is True:
        if comp.value is not None:
            mag_val = comp.value.to_base()
        else:
            mag_val = Decimal(0)
        raw_ph = params.get("ac_phase", params.get("phase", 0))
        phase_val = _phase_decimal(raw_ph)
        phase_unit = str(params.get("phase_unit", "deg")).strip().lower()

    elif "ac" in params and not isinstance(params["ac"], bool):
        raw_ac = params["ac"]
        if isinstance(raw_ac, Quantity):
            mag_val = raw_ac.to_base()
        elif isinstance(raw_ac, str):
            try:
                mag_val = parse_quantity(raw_ac).to_base()
            except Exception:
                mag_val = Decimal(raw_ac.strip())
        elif isinstance(raw_ac, (int, Decimal)):
            mag_val = Decimal(raw_ac)
        else:
            raise ACPhaseError(f"{comp.ref}: invalid ac parameter {raw_ac!r}")
        raw_ph = params.get("ac_phase", params.get("phase", 0))
        phase_val = _phase_decimal(raw_ph)
        phase_unit = str(params.get("phase_unit", "deg")).strip().lower()

    elif "phase" in params and "ac_mag" not in params:
        # If phase is given but no ac_mag, check if value is present
        raw_ph = params["phase"]
        phase_val = _phase_decimal(raw_ph)
        phase_unit = str(params.get("phase_unit", "deg")).strip().lower()
        if comp.value is not None:
            mag_val = comp.value.to_base()
        else:
            mag_val = Decimal(0)

    if mag_val is None or mag_val == Decimal(0):
        return DecimalComplex.zero()

    if phase_unit not in ("deg", "rad"):
        raise ACPhaseError(f"{comp.ref}: phase_unit must be 'deg' or 'rad', got {phase_unit!r}")

    if phase_unit == "deg":
        angle_rad = ctx.multiply(phase_val, ctx.divide(decimal_pi(), Decimal(180)))
    else:
        angle_rad = phase_val

    re = ctx.multiply(mag_val, decimal_cos(angle_rad, ctx))
    im = ctx.multiply(mag_val, decimal_sin(angle_rad, ctx))
    return DecimalComplex(re, im)


def _build_dc_equivalent_circuit(circuit: Circuit) -> Circuit:
    """Build DC equivalent circuit: C -> open circuit, L -> 0V V-source."""
    dc_c = Circuit(name=f"{circuit.name}_dc")
    has_l_or_c = any(c.type.upper() in ("L", "C") for c in circuit.components)
    if not has_l_or_c:
        return circuit

    existing_nums = [
        int(re.search(r"\d+", comp.ref).group(0))
        for comp in circuit.components
        if comp.type.upper() == "V" and re.search(r"\d+", comp.ref)
    ]
    base_v_num = max(existing_nums + [9000])

    v_aux_count = 1
    for c in circuit.components:
        t = c.type.upper()
        if t == "C":
            # In DC, ideal capacitors are open circuits.
            continue
        elif t == "L":
            # In DC, ideal inductors are short circuits (0V voltage source).
            short_ref = f"V{base_v_num + v_aux_count}"
            v_aux_count += 1
            dc_c.add(Component(
                ref=short_ref,
                type="V",
                pins={"+": c.pins["1"], "-": c.pins["2"]},
                value=Quantity(Decimal(0), parse_unit("V")),
            ))
        else:
            dc_c.add(c)
    return dc_c


def _validate_dc_result_compatibility(
    circuit: Circuit,
    dc_result: NonlinearResult | AnalysisResult,
) -> tuple[bool, str]:
    if isinstance(dc_result, NonlinearResult):
        if dc_result.status != NonlinearStatus.CONVERGED:
            return False, f"dc_result status is not CONVERGED ({dc_result.status.value})"
    elif isinstance(dc_result, AnalysisResult):
        if dc_result.status != LinearDCStatus.SOLVED:
            return False, f"dc_result status is not SOLVED ({dc_result.status.value})"
    else:
        return False, f"dc_result must be a NonlinearResult or AnalysisResult, got {type(dc_result).__name__}"

    ground = reference_net(circuit.nets)
    c_nodes = {n for n in circuit.nets if n != ground}
    dc_nodes = {nv.node for nv in dc_result.node_voltages if nv.node != ground}

    # Strict exact correspondence of non-ground nodes: c_nodes == dc_nodes
    if c_nodes != dc_nodes:
        missing = sorted(c_nodes - dc_nodes)
        if missing:
            return False, f"circuit nodes {missing} missing from dc_result"
        extra = sorted(dc_nodes - c_nodes)
        if extra:
            return False, f"dc_result contains extra nodes {extra} not in circuit"

    # Extract all component refs present in dc_result
    dc_refs: set[str] = set()
    for ep in getattr(dc_result, "element_powers", ()):
        dc_refs.add(ep.ref.split(":")[0].upper())
    for bc in getattr(dc_result, "branch_currents", ()):
        dc_refs.add(bc.ref.split(":")[0].upper())
    struct = dc_result.provenance.get("circuit_structure")
    if isinstance(struct, list):
        for item in struct:
            if isinstance(item, dict) and "ref" in item:
                dc_refs.add(str(item["ref"]).split(":")[0].upper())
    inputs = dc_result.provenance.get("inputs")
    if isinstance(inputs, list):
        for r in inputs:
            dc_refs.add(str(r).split(":")[0].upper())

    # In DC equivalent semantics:
    # C is omitted (open circuit in DC, never required in dc_result)
    # L is converted to an auxiliary short-circuit V-source (0V)
    all_c_refs = {c.ref.upper() for c in circuit.components}
    c_non_reactive = {c.ref.upper() for c in circuit.components if c.type.upper() not in ("C", "L")}
    has_l = any(c.type.upper() == "L" for c in circuit.components)

    # 1. Check missing non-reactive components
    missing_comps = c_non_reactive - dc_refs
    if missing_comps:
        return False, f"circuit components {sorted(missing_comps)} missing from dc_result"

    # 2. Check foreign/incompatible components in dc_result
    extra_comps = dc_refs - all_c_refs
    if has_l:
        extra_comps = {r for r in extra_comps if not r.startswith("V")}

    if extra_comps:
        return False, f"dc_result contains incompatible/extra components {sorted(extra_comps)}"

    return True, "compatible"


def solve_small_signal_ac(
    circuit: Circuit,
    frequency: Quantity | str,
    *,
    dc_result: NonlinearResult | AnalysisResult | None = None,
    observer=None,
) -> SmallSignalACResult:
    """Perform small-signal AC analysis of a circuit around its DC operating point.

    Args:
        circuit: Canonical Circuit definition.
        frequency: Operating frequency as Quantity (Hz) or string (e.g. '1kHz').
        dc_result: Optional pre-computed converged DC operating point.

    Returns:
        SmallSignalACResult containing node phasors, branch currents, linearized
        parameters and diagnostics.
    """
    ctx = make_context()

    # 1. Structural component validation
    if not circuit.components:
        return SmallSignalACResult(
            status=ACStatus.INVALID,
            diagnostics=("circuit has no components",),
        )

    for c in circuit.components:
        t = c.type.upper()
        if t not in SUPPORTED_TYPES:
            return SmallSignalACResult(
                status=ACStatus.UNSUPPORTED,
                diagnostics=(f"{c.ref}: type {c.type!r} is outside the small-signal AC domain",),
            )

    try:
        ground = reference_net(circuit.nets)
        check_connected(circuit.nets, circuit.components, ground)
        validate_dependent_structure(circuit)
        check_control_cycles(circuit)
    except UnsupportedElementError as exc:
        return SmallSignalACResult(status=ACStatus.UNSUPPORTED, diagnostics=(str(exc),))
    except _INVALID_ERRORS as exc:
        return SmallSignalACResult(status=ACStatus.INVALID, diagnostics=(str(exc),))

    # 2. Operating Point Frequency validation
    try:
        op = ACOperatingPoint.from_frequency(frequency, ground)
    except ACFrequencyError as exc:
        return SmallSignalACResult(status=ACStatus.INVALID, diagnostics=(str(exc),))
    except Exception as exc:
        return SmallSignalACResult(status=ACStatus.INVALID, diagnostics=(f"frequency error: {exc}",))

    # 3. DC Operating Point Resolution
    if dc_result is None:
        dc_circ = _build_dc_equivalent_circuit(circuit)
        has_nonlinear = any(c.type.upper() in ("D", "Q", "M", "J") for c in dc_circ.components)
        if has_nonlinear:
            dc_res = solve_nonlinear_dc(dc_circ)
            if dc_res.status != NonlinearStatus.CONVERGED:
                status_map = {
                    NonlinearStatus.INVALID: ACStatus.INVALID,
                    NonlinearStatus.UNSUPPORTED: ACStatus.UNSUPPORTED,
                    NonlinearStatus.SINGULAR_JACOBIAN: ACStatus.SINGULAR,
                    NonlinearStatus.DIVERGED: ACStatus.DIVERGED,
                    NonlinearStatus.MAX_ITERATIONS: ACStatus.DIVERGED,
                }
                ac_stat = status_map.get(dc_res.status, ACStatus.INVALID)
                return SmallSignalACResult(
                    status=ac_stat,
                    operating_point=op,
                    dc_operating_point=dc_res,
                    provenance={
                        "engine": ENGINE_VERSION,
                        "dc_status": dc_res.status.value,
                        "dc_provenance": dc_res.provenance,
                    },
                    diagnostics=tuple(list(dc_res.diagnostics) + [
                        f"DC operating point failed ({dc_res.status.value}): small-signal AC aborted"
                    ]),
                    digest=hashlib.sha256(json.dumps(dc_res.provenance, sort_keys=True).encode()).hexdigest(),
                )
        else:
            dc_res = solve_linear_dc(dc_circ)
            if dc_res.status != LinearDCStatus.SOLVED:
                status_map = {
                    LinearDCStatus.INVALID: ACStatus.INVALID,
                    LinearDCStatus.UNSUPPORTED: ACStatus.UNSUPPORTED,
                    LinearDCStatus.SINGULAR: ACStatus.SINGULAR,
                    LinearDCStatus.INCONSISTENT: ACStatus.INCONSISTENT,
                }
                ac_stat = status_map.get(dc_res.status, ACStatus.INVALID)
                return SmallSignalACResult(
                    status=ac_stat,
                    operating_point=op,
                    dc_operating_point=dc_res,
                    provenance={
                        "engine": ENGINE_VERSION,
                        "dc_status": dc_res.status.value,
                        "dc_provenance": dc_res.provenance,
                    },
                    diagnostics=tuple(list(dc_res.diagnostics) + [
                        f"DC operating point failed ({dc_res.status.value}): small-signal AC aborted"
                    ]),
                    digest=hashlib.sha256(json.dumps(dc_res.provenance, sort_keys=True).encode()).hexdigest(),
                )
    else:
        is_compat, reason = _validate_dc_result_compatibility(circuit, dc_result)
        if not is_compat:
            return SmallSignalACResult(
                status=ACStatus.INVALID,
                operating_point=op,
                dc_operating_point=dc_result,
                diagnostics=(f"incompatible dc_result: {reason}",),
            )
        dc_res = dc_result

    # Node voltages at DC operating point
    dc_node_v: dict[str, Decimal] = {ground: Decimal(0)}
    for nv in dc_res.node_voltages:
        dc_node_v[nv.node] = nv.voltage.to_base()

    def get_dc_v(net: str) -> Decimal:
        return dc_node_v.get(net, Decimal(0))

    # 4. Extract incremental small-signal parameters for D, Q, M and J
    diodes_ss: list[DiodeSmallSignalParams] = []
    bjts_ss: list[BJTSmallSignalParams] = []
    mosfets_ss: list[MOSFETSmallSignalParams] = []
    jfets_ss: list[JFETSmallSignalParams] = []

    for c in sorted(circuit.components, key=lambda e: e.ref.upper()):
        t = c.type.upper()
        if t == "D":
            from academic_core.domain.engineering.mna.diode import PARAM_KIND
            is_variant = PARAM_KIND in (c.parameters or {})
            try:
                if is_variant:
                    vp = extract_diode_variant_params(c)
                    kind = vp.kind
                else:
                    dp = extract_diode_params(c)
                    kind = "RECT"
            except InvalidCircuitError as exc:
                return SmallSignalACResult(status=ACStatus.INVALID, diagnostics=(str(exc),))
            v_a0 = get_dc_v(c.pins["A"])
            v_k0 = get_dc_v(c.pins["K"])
            vd0 = ctx.subtract(v_a0, v_k0)
            if is_variant:
                id0 = variant_current(vd0, vp, ctx)
                gd = variant_conductance(vd0, vp, ctx)
            else:
                id0 = shockley_current(vd0, dp, ctx)
                gd = shockley_conductance(vd0, dp, ctx)
            if not (id0.is_finite() and gd.is_finite()):
                return SmallSignalACResult(
                    status=ACStatus.DIVERGED,
                    diagnostics=(f"{c.ref}: non-finite diode small-signal evaluation at DC bias",),
                )
            rd = ctx.divide(Decimal(1), gd) if gd > 0 else Decimal("Infinity")
            diodes_ss.append(DiodeSmallSignalParams(
                ref=c.ref,
                anode=c.pins["A"],
                cathode=c.pins["K"],
                v_d0=vd0,
                i_d0=id0,
                g_d=gd,
                r_d=rd,
                kind=kind,
            ))
        elif t == "Q":
            try:
                bp = extract_bjt_params(c)
            except InvalidCircuitError as exc:
                return SmallSignalACResult(status=ACStatus.INVALID, diagnostics=(str(exc),))
            vc0 = get_dc_v(c.pins["C"])
            vb0 = get_dc_v(c.pins["B"])
            ve0 = get_dc_v(c.pins["E"])
            vbe0 = ctx.subtract(vb0, ve0)
            vce0 = ctx.subtract(vc0, ve0)
            ic0, ib0, ie0 = bjt_terminal_currents(vc0, vb0, ve0, bp, ctx)
            gf, gr = bjt_conductances(vc0, vb0, ve0, bp, ctx)
            jac = bjt_jacobian(vc0, vb0, ve0, bp, ctx)
            if jac is None or not (ic0.is_finite() and ib0.is_finite() and ie0.is_finite()):
                return SmallSignalACResult(
                    status=ACStatus.DIVERGED,
                    diagnostics=(f"{c.ref}: non-finite BJT small-signal evaluation at DC bias",),
                )
            gm = gf
            r_pi = ctx.divide(bp.Bf, gf) if gf > 0 else Decimal("Infinity")
            bjts_ss.append(BJTSmallSignalParams(
                ref=c.ref,
                collector=c.pins["C"],
                base=c.pins["B"],
                emitter=c.pins["E"],
                polarity=bp.polarity,
                v_c0=vc0,
                v_b0=vb0,
                v_e0=ve0,
                v_be0=vbe0,
                v_ce0=vce0,
                i_c0=ic0,
                i_b0=ib0,
                i_e0=ie0,
                g_m=gm,
                r_pi=r_pi,
                g_F=gf,
                g_R=gr,
                jacobian=jac,
            ))
        elif t == "M":
            try:
                mp = extract_mosfet_params(c)
            except InvalidCircuitError as exc:
                return SmallSignalACResult(status=ACStatus.INVALID, diagnostics=(str(exc),))
            vd0 = get_dc_v(c.pins["D"])
            vg0 = get_dc_v(c.pins["G"])
            vs0 = get_dc_v(c.pins["S"])
            vb0 = get_dc_v(c.pins["B"])
            region = mos_region(vd0, vg0, vs0, vb0, mp, ctx)
            trio = mos_conductances(vd0, vg0, vs0, vb0, mp, ctx)
            jac = mos_jacobian(vd0, vg0, vs0, vb0, mp, ctx)
            idc, _, _, _ = mos_terminal_currents(vd0, vg0, vs0, vb0, mp, ctx)
            if region is None or trio is None or jac is None or not idc.is_finite():
                return SmallSignalACResult(
                    status=ACStatus.DIVERGED,
                    diagnostics=(f"{c.ref}: non-finite MOSFET small-signal evaluation at DC bias",),
                )
            gm, gds, gmb = trio
            mosfets_ss.append(MOSFETSmallSignalParams(
                ref=c.ref,
                drain=c.pins["D"],
                gate=c.pins["G"],
                source=c.pins["S"],
                bulk=c.pins["B"],
                polarity=mp.polarity,
                region=region,
                v_gs0=ctx.subtract(vg0, vs0),
                v_ds0=ctx.subtract(vd0, vs0),
                i_d0=idc,
                g_m=gm,
                g_ds=gds,
                g_mb=gmb,
                jacobian=jac,
            ))
        elif t == "J":
            try:
                jp = extract_jfet_params(c)
            except InvalidCircuitError as exc:
                return SmallSignalACResult(status=ACStatus.INVALID, diagnostics=(str(exc),))
            vd0 = get_dc_v(c.pins["D"])
            vg0 = get_dc_v(c.pins["G"])
            vs0 = get_dc_v(c.pins["S"])
            region = jfet_region(vd0, vg0, vs0, jp, ctx)
            pair = jfet_conductances(vd0, vg0, vs0, jp, ctx)
            jac = jfet_jacobian(vd0, vg0, vs0, jp, ctx)
            idc, _, _ = jfet_terminal_currents(vd0, vg0, vs0, jp, ctx)
            if region is None or pair is None or jac is None or not idc.is_finite():
                return SmallSignalACResult(
                    status=ACStatus.DIVERGED,
                    diagnostics=(f"{c.ref}: non-finite JFET small-signal evaluation at DC bias",),
                )
            gm, gds = pair
            jfets_ss.append(JFETSmallSignalParams(
                ref=c.ref,
                drain=c.pins["D"],
                gate=c.pins["G"],
                source=c.pins["S"],
                polarity=jp.polarity,
                region=region,
                v_gs0=ctx.subtract(vg0, vs0),
                v_ds0=ctx.subtract(vd0, vs0),
                i_d0=idc,
                g_m=gm,
                g_ds=gds,
                jacobian=jac,
            ))

    # 5. Build Complex Small-Signal MNA Problem
    nodes = tuple(sorted(n for n in circuit.nets if n != ground))
    node_index = {n: i for i, n in enumerate(nodes)}
    n_nodes = len(nodes)

    vsource_refs = tuple(sorted(
        c.ref for c in circuit.components if c.type.upper() in VOLTAGE_BRANCH_TYPES
    ))
    tx_leg_refs = tuple(sorted(
        f"{c.ref}:{leg}" for c in circuit.components for leg in (1, 2)
        if c.type.upper() == "T"
    ))

    vsource_index = {ref: n_nodes + j for j, ref in enumerate(vsource_refs)}
    tx_index = {ref: n_nodes + len(vsource_refs) + j for j, ref in enumerate(tx_leg_refs)}
    vsource_index.update(tx_index)

    total_size = n_nodes + len(vsource_refs) + len(tx_leg_refs)
    matrix = [[DecimalComplex.zero() for _ in range(total_size)] for _ in range(total_size)]
    rhs = [DecimalComplex.zero() for _ in range(total_size)]

    def idx(net: str) -> int | None:
        return node_index.get(net)

    omega = op.omega
    one = DecimalComplex.one()

    # Precalculate source phasors and branch admittances
    by_ref = {c.ref.upper(): c for c in circuit.components}
    src_phasors: dict[str, DecimalComplex] = {}
    for c in circuit.components:
        if c.type.upper() in ("V", "I"):
            src_phasors[c.ref.upper()] = _extract_source_ac_phasor(c, ctx)

    # Control currents for H/F
    adm_of: dict[str, DecimalComplex] = {}
    for c in circuit.components:
        t = c.type.upper()
        if t == "R":
            base = c.value.to_base()
            adm_of[c.ref.upper()] = DecimalComplex(ctx.divide(Decimal(1), base), Decimal(0))
        elif t == "L":
            base = c.value.to_base()
            wl = ctx.multiply(omega, base)
            adm_of[c.ref.upper()] = DecimalComplex(Decimal(0), ctx.divide(Decimal(-1), wl))
        elif t == "C":
            base = c.value.to_base()
            wc = ctx.multiply(omega, base)
            adm_of[c.ref.upper()] = DecimalComplex(Decimal(0), wc)

    resolved: dict = {}

    def resolve_control(ref_upper: str, active: tuple = ()):
        if ref_upper in resolved:
            return resolved[ref_upper]
        if ref_upper in active:
            raise CircularControlError(f"circular current control involving {ref_upper}")
        target = by_ref[ref_upper]
        t = target.type.upper()
        z0 = DecimalComplex.zero()
        o1 = DecimalComplex.one()
        if t in VOLTAGE_BRANCH_TYPES and t != "O":
            form = ({}, {target.ref: o1}, z0)
        elif t == "O":
            form = ({}, {target.ref: -o1}, z0)
        elif t in ("R", "L", "C"):
            y = adm_of[ref_upper]
            a, b = target.pins["1"], target.pins["2"]
            form = ({a: y, b: -y}, {}, z0)
        elif t == "I":
            form = ({}, {}, -src_phasors[ref_upper])
        elif t == "G":
            gm = DecimalComplex(target.value.to_base(), Decimal(0))
            p = target.parameters
            form = ({p["cp"]: -gm, p["cn"]: gm}, {}, z0)
        elif t == "F":
            beta = DecimalComplex(target.value.to_base(), Decimal(0))
            ctrl = str(target.parameters["control_ref"]).upper()
            sub = resolve_control(ctrl, active + (ref_upper,))
            form = (
                {n: -beta * v for n, v in sub[0].items()},
                {r: -beta * v for r, v in sub[1].items()},
                -beta * sub[2],
            )
        else:
            raise UnsupportedElementError(
                f"{target.ref}: type {t!r} cannot carry control current"
            )
        resolved[ref_upper] = form
        return form

    for _ref in resolution_order(circuit):
        resolve_control(_ref)

    def apply_form(row: int, form, scale: DecimalComplex, *, negate: bool) -> None:
        for net, coef in form[0].items():
            j = idx(net)
            if j is not None:
                if negate:
                    matrix[row][j] = matrix[row][j] - scale * coef
                else:
                    matrix[row][j] = matrix[row][j] + scale * coef
        for ref, coef in form[1].items():
            if negate:
                matrix[row][vsource_index[ref]] = matrix[row][vsource_index[ref]] - scale * coef
            else:
                matrix[row][vsource_index[ref]] = matrix[row][vsource_index[ref]] + scale * coef
        if negate:
            rhs[row] = rhs[row] + scale * form[2]
        else:
            rhs[row] = rhs[row] - scale * form[2]

    # Stamping components
    diode_map = {dp.ref.upper(): dp for dp in diodes_ss}
    bjt_map = {bp.ref.upper(): bp for bp in bjts_ss}
    mosfet_map = {mp.ref.upper(): mp for mp in mosfets_ss}
    jfet_map = {jp.ref.upper(): jp for jp in jfets_ss}

    for c in sorted(circuit.components, key=lambda e: e.ref.upper()):
        t = c.type.upper()
        if t in ("R", "L", "C"):
            a, b = c.pins["1"], c.pins["2"]
            y = adm_of[c.ref.upper()]
            i1, i2 = idx(a), idx(b)
            if i1 is not None:
                matrix[i1][i1] = matrix[i1][i1] + y
            if i2 is not None:
                matrix[i2][i2] = matrix[i2][i2] + y
            if i1 is not None and i2 is not None:
                matrix[i1][i2] = matrix[i1][i2] - y
                matrix[i2][i1] = matrix[i2][i1] - y

        elif t == "D":
            dp = diode_map[c.ref.upper()]
            a, b = c.pins["A"], c.pins["K"]
            yd = DecimalComplex(dp.g_d, Decimal(0))
            ia, ik = idx(a), idx(b)
            if ia is not None:
                matrix[ia][ia] = matrix[ia][ia] + yd
            if ik is not None:
                matrix[ik][ik] = matrix[ik][ik] + yd
            if ia is not None and ik is not None:
                matrix[ia][ik] = matrix[ia][ik] - yd
                matrix[ik][ia] = matrix[ik][ia] - yd

        elif t == "Q":
            bp = bjt_map[c.ref.upper()]
            jac = bp.jacobian
            pin_nets = (c.pins["C"], c.pins["B"], c.pins["E"])
            pin_indices = tuple(idx(net) for net in pin_nets)
            for r in range(3):
                row_idx = pin_indices[r]
                if row_idx is None:
                    continue
                for s in range(3):
                    col_idx = pin_indices[s]
                    if col_idx is None:
                        continue
                    j_val = DecimalComplex(jac[r][s], Decimal(0))
                    matrix[row_idx][col_idx] = matrix[row_idx][col_idx] + j_val

        elif t == "M":
            mp = mosfet_map[c.ref.upper()]
            jac = mp.jacobian
            pin_nets = (c.pins["D"], c.pins["G"], c.pins["S"], c.pins["B"])
            pin_indices = tuple(idx(net) for net in pin_nets)
            for r in range(4):
                row_idx = pin_indices[r]
                if row_idx is None:
                    continue
                for s in range(4):
                    col_idx = pin_indices[s]
                    if col_idx is None:
                        continue
                    j_val = DecimalComplex(jac[r][s], Decimal(0))
                    matrix[row_idx][col_idx] = matrix[row_idx][col_idx] + j_val

        elif t == "J":
            jp = jfet_map[c.ref.upper()]
            jac = jp.jacobian
            pin_nets = (c.pins["D"], c.pins["G"], c.pins["S"])
            pin_indices = tuple(idx(net) for net in pin_nets)
            for r in range(3):
                row_idx = pin_indices[r]
                if row_idx is None:
                    continue
                for s in range(3):
                    col_idx = pin_indices[s]
                    if col_idx is None:
                        continue
                    j_val = DecimalComplex(jac[r][s], Decimal(0))
                    matrix[row_idx][col_idx] = matrix[row_idx][col_idx] + j_val

        elif t == "I":
            a, b = c.pins["+"], c.pins["-"]
            ph = src_phasors[c.ref.upper()]
            ip, im = idx(a), idx(b)
            if ip is not None:
                rhs[ip] = rhs[ip] + ph
            if im is not None:
                rhs[im] = rhs[im] - ph

        elif t in ("V", "E", "H"):
            a, b = c.pins["+"], c.pins["-"]
            ip, im = idx(a), idx(b)
            k = vsource_index[c.ref]
            if ip is not None:
                matrix[ip][k] = matrix[ip][k] + one
                matrix[k][ip] = matrix[k][ip] + one
            if im is not None:
                matrix[im][k] = matrix[im][k] - one
                matrix[k][im] = matrix[k][im] - one
            if t == "V":
                ph = src_phasors[c.ref.upper()]
                rhs[k] = rhs[k] + ph
            elif t == "E":
                mu = DecimalComplex(c.value.to_base(), Decimal(0))
                icp, icn = idx(c.parameters["cp"]), idx(c.parameters["cn"])
                if icp is not None:
                    matrix[k][icp] = matrix[k][icp] - mu
                if icn is not None:
                    matrix[k][icn] = matrix[k][icn] + mu
            else:  # H
                r_gain = DecimalComplex(c.value.to_base(), Decimal(0))
                ctrl = str(c.parameters["control_ref"]).upper()
                apply_form(k, resolve_control(ctrl), r_gain, negate=True)

        elif t == "O":
            inp, inm = idx(c.pins["+"]), idx(c.pins["-"])
            io = idx(c.pins["o"])
            k = vsource_index[c.ref]
            if io is not None:
                matrix[io][k] = matrix[io][k] - one
            if inp is not None:
                matrix[k][inp] = matrix[k][inp] + one
            if inm is not None:
                matrix[k][inm] = matrix[k][inm] - one

        elif t == "G":
            gm = DecimalComplex(c.value.to_base(), Decimal(0))
            a, b = c.pins["+"], c.pins["-"]
            icp, icn = idx(c.parameters["cp"]), idx(c.parameters["cn"])
            ip, im = idx(a), idx(b)
            if ip is not None:
                if icp is not None:
                    matrix[ip][icp] = matrix[ip][icp] - gm
                if icn is not None:
                    matrix[ip][icn] = matrix[ip][icn] + gm
            if im is not None:
                if icp is not None:
                    matrix[im][icp] = matrix[im][icp] + gm
                if icn is not None:
                    matrix[im][icn] = matrix[im][icn] - gm

        elif t == "F":
            beta = DecimalComplex(c.value.to_base(), Decimal(0))
            a, b = c.pins["+"], c.pins["-"]
            ip, im = idx(a), idx(b)
            ctrl = str(c.parameters["control_ref"]).upper()
            form = resolve_control(ctrl)
            if ip is not None:
                apply_form(ip, form, beta, negate=True)
            if im is not None:
                apply_form(im, form, beta, negate=False)

        elif t == "T":
            n_ratio = DecimalComplex(c.value.to_base(), Decimal(0))
            p1, p2 = idx(c.pins["1"]), idx(c.pins["2"])
            s1, s2 = idx(c.pins["3"]), idx(c.pins["4"])
            k1 = vsource_index[f"{c.ref}:1"]
            k2 = vsource_index[f"{c.ref}:2"]
            if p1 is not None:
                matrix[p1][k1] = matrix[p1][k1] + one
            if p2 is not None:
                matrix[p2][k1] = matrix[p2][k1] - one
            if s1 is not None:
                matrix[s1][k2] = matrix[s1][k2] + one
            if s2 is not None:
                matrix[s2][k2] = matrix[s2][k2] - one
            if s1 is not None:
                matrix[k1][s1] = matrix[k1][s1] + one
            if s2 is not None:
                matrix[k1][s2] = matrix[k1][s2] - one
            if p1 is not None:
                matrix[k1][p1] = matrix[k1][p1] - n_ratio
            if p2 is not None:
                matrix[k1][p2] = matrix[k1][p2] + n_ratio
            matrix[k2][k1] = matrix[k2][k1] + one
            matrix[k2][k2] = matrix[k2][k2] + n_ratio

    # 6. Linear Complex Solve
    lin_prob = ComplexLinearProblem.from_sequences(matrix, rhs)
    if observer is not None:
        # E0.3: the linearised complex system exactly as it is solved
        # (immutable snapshots; inert when observer is None).
        labels = [f"x{k}" for k in range(total_size)]
        for net, k in node_index.items():
            labels[k] = f"V({net})"
        for key, k in vsource_index.items():
            labels[k] = f"I({key})"
        observer.ac_system(tuple(labels), tuple(tuple(row) for row in matrix), tuple(rhs),
                           "decimal", op.frequency.to_base(), op.omega)
    lin_sol = linsolve(lin_prob, NumericMode.HIGH_PRECISION)
    if observer is not None:
        observer.ac_outcome(lin_sol.status.value, lin_sol.numeric_mode.value, lin_sol.rank_A,
                            lin_sol.solution, lin_sol.residual_norm, lin_sol.backward_error)

    status_map = {
        LinearStatus.SOLVED: ACStatus.SOLVED,
        LinearStatus.SINGULAR: ACStatus.SINGULAR,
        LinearStatus.INCONSISTENT: ACStatus.INCONSISTENT,
        LinearStatus.NUMERICALLY_UNCERTAIN: ACStatus.NUMERICALLY_UNCERTAIN,
    }
    final_status = status_map.get(lin_sol.status, ACStatus.INVALID)

    if final_status != ACStatus.SOLVED or lin_sol.solution is None:
        return SmallSignalACResult(
            status=final_status,
            operating_point=op,
            dc_operating_point=dc_res,
            diode_parameters=tuple(diodes_ss),
            bjt_parameters=tuple(bjts_ss),
            mosfet_parameters=tuple(mosfets_ss),
            jfet_parameters=tuple(jfets_ss),
            solver_result=lin_sol,
            numeric_mode=NumericMode.HIGH_PRECISION,
            diagnostics=(f"AC linear solve status: {lin_sol.status.value}",),
        )

    # 7. Reconstruct Node Phasors and Branch Observables
    sol_vec = lin_sol.solution
    node_v_map: dict[str, DecimalComplex] = {ground: DecimalComplex.zero()}
    node_voltages_list: list[NodePhasor] = [NodePhasor(ground, DecimalComplex.zero())]

    for net, i in node_index.items():
        v_phasor = sol_vec[i]
        node_v_map[net] = v_phasor
        node_voltages_list.append(NodePhasor(net, v_phasor))

    def node_v(net: str) -> DecimalComplex:
        return node_v_map.get(net, DecimalComplex.zero())

    branch_currents_list: list[BranchCurrent] = []
    branch_voltages_list: list[BranchVoltage] = []
    net_kcl_leaving: dict[str, DecimalComplex] = {n: DecimalComplex.zero() for n in circuit.nets}

    for c in sorted(circuit.components, key=lambda e: e.ref.upper()):
        t = c.type.upper()
        if t in ("R", "L", "C"):
            p1, p2 = c.pins["1"], c.pins["2"]
            y = adm_of[c.ref.upper()]
            v_br = node_v(p1) - node_v(p2)
            i_br = y * v_br
            branch_voltages_list.append(BranchVoltage(c.ref, v_br, "V1-V2"))
            branch_currents_list.append(BranchCurrent(c.ref, i_br, "pin1->pin2"))
            net_kcl_leaving[p1] = net_kcl_leaving[p1] + i_br
            net_kcl_leaving[p2] = net_kcl_leaving[p2] - i_br

        elif t == "D":
            a, k = c.pins["A"], c.pins["K"]
            dp = diode_map[c.ref.upper()]
            yd = DecimalComplex(dp.g_d, Decimal(0))
            v_br = node_v(a) - node_v(k)
            i_br = yd * v_br
            branch_voltages_list.append(BranchVoltage(c.ref, v_br, "VA-VK"))
            branch_currents_list.append(BranchCurrent(c.ref, i_br, "A->K"))
            net_kcl_leaving[a] = net_kcl_leaving[a] + i_br
            net_kcl_leaving[k] = net_kcl_leaving[k] - i_br

        elif t == "Q":
            bp = bjt_map[c.ref.upper()]
            jac = bp.jacobian
            vc = node_v(c.pins["C"])
            vb = node_v(c.pins["B"])
            ve = node_v(c.pins["E"])
            ic = DecimalComplex(jac[0][0], Decimal(0)) * vc + DecimalComplex(jac[0][1], Decimal(0)) * vb + DecimalComplex(jac[0][2], Decimal(0)) * ve
            ib = DecimalComplex(jac[1][0], Decimal(0)) * vc + DecimalComplex(jac[1][1], Decimal(0)) * vb + DecimalComplex(jac[1][2], Decimal(0)) * ve
            ie = DecimalComplex(jac[2][0], Decimal(0)) * vc + DecimalComplex(jac[2][1], Decimal(0)) * vb + DecimalComplex(jac[2][2], Decimal(0)) * ve

            branch_voltages_list.append(BranchVoltage(f"{c.ref}:BE", vb - ve, "VB-VE"))
            branch_voltages_list.append(BranchVoltage(f"{c.ref}:CE", vc - ve, "VC-VE"))
            branch_currents_list.append(BranchCurrent(f"{c.ref}:C", ic, "into_collector"))
            branch_currents_list.append(BranchCurrent(f"{c.ref}:B", ib, "into_base"))
            branch_currents_list.append(BranchCurrent(f"{c.ref}:E", ie, "into_emitter"))

            net_kcl_leaving[c.pins["C"]] = net_kcl_leaving[c.pins["C"]] + ic
            net_kcl_leaving[c.pins["B"]] = net_kcl_leaving[c.pins["B"]] + ib
            net_kcl_leaving[c.pins["E"]] = net_kcl_leaving[c.pins["E"]] + ie

        elif t == "M":
            mp = mosfet_map[c.ref.upper()]
            jac = mp.jacobian
            v_term = (node_v(c.pins["D"]), node_v(c.pins["G"]),
                      node_v(c.pins["S"]), node_v(c.pins["B"]))
            legs = ("D", "G", "S", "B")
            i_term = []
            for r in range(4):
                acc = DecimalComplex.zero()
                for s in range(4):
                    acc = acc + DecimalComplex(jac[r][s], Decimal(0)) * v_term[s]
                i_term.append(acc)
            branch_voltages_list.append(BranchVoltage(f"{c.ref}:GS", v_term[1] - v_term[2], "VG-VS"))
            branch_voltages_list.append(BranchVoltage(f"{c.ref}:DS", v_term[0] - v_term[2], "VD-VS"))
            for leg, cur in zip(legs, i_term):
                branch_currents_list.append(BranchCurrent(f"{c.ref}:{leg}", cur, f"into_{leg.lower()}"))
            for pin, cur in zip((c.pins["D"], c.pins["G"], c.pins["S"], c.pins["B"]), i_term):
                net_kcl_leaving[pin] = net_kcl_leaving[pin] + cur

        elif t == "J":
            jp = jfet_map[c.ref.upper()]
            jac = jp.jacobian
            v_term = (node_v(c.pins["D"]), node_v(c.pins["G"]), node_v(c.pins["S"]))
            legs = ("D", "G", "S")
            i_term = []
            for r in range(3):
                acc = DecimalComplex.zero()
                for s in range(3):
                    acc = acc + DecimalComplex(jac[r][s], Decimal(0)) * v_term[s]
                i_term.append(acc)
            branch_voltages_list.append(BranchVoltage(f"{c.ref}:GS", v_term[1] - v_term[2], "VG-VS"))
            branch_voltages_list.append(BranchVoltage(f"{c.ref}:DS", v_term[0] - v_term[2], "VD-VS"))
            for leg, cur in zip(legs, i_term):
                branch_currents_list.append(BranchCurrent(f"{c.ref}:{leg}", cur, f"into_{leg.lower()}"))
            for pin, cur in zip((c.pins["D"], c.pins["G"], c.pins["S"]), i_term):
                net_kcl_leaving[pin] = net_kcl_leaving[pin] + cur

        elif t == "I":
            p, m = c.pins["+"], c.pins["-"]
            v_br = node_v(p) - node_v(m)
            i_src = src_phasors[c.ref.upper()]
            i_br = -i_src  # through-element + -> -
            branch_voltages_list.append(BranchVoltage(c.ref, v_br, "V+-V-"))
            branch_currents_list.append(BranchCurrent(c.ref, i_br, "+->-"))
            net_kcl_leaving[p] = net_kcl_leaving[p] - i_src
            net_kcl_leaving[m] = net_kcl_leaving[m] + i_src

        elif t in ("V", "E", "H"):
            p, m = c.pins["+"], c.pins["-"]
            k = vsource_index[c.ref]
            i_br = sol_vec[k]
            v_br = src_phasors[c.ref.upper()] if t == "V" else (node_v(p) - node_v(m))
            branch_voltages_list.append(BranchVoltage(c.ref, v_br, "V+-V-"))
            branch_currents_list.append(BranchCurrent(c.ref, i_br, "+->-"))
            net_kcl_leaving[p] = net_kcl_leaving[p] + i_br
            net_kcl_leaving[m] = net_kcl_leaving[m] - i_br

        elif t == "O":
            k = vsource_index[c.ref]
            io = sol_vec[k]
            out_pin = c.pins["o"]
            v_br = node_v(out_pin) - node_v(ground)
            branch_voltages_list.append(BranchVoltage(c.ref, v_br, "Vo-GND"))
            branch_currents_list.append(BranchCurrent(c.ref, io, "o->GND"))
            net_kcl_leaving[out_pin] = net_kcl_leaving[out_pin] - io
            net_kcl_leaving[ground] = net_kcl_leaving[ground] + io

        elif t == "G":
            p, m = c.pins["+"], c.pins["-"]
            cp, cn = c.parameters["cp"], c.parameters["cn"]
            gm = DecimalComplex(c.value.to_base(), Decimal(0))
            i_out = gm * (node_v(cp) - node_v(cn))
            v_br = node_v(p) - node_v(m)
            branch_voltages_list.append(BranchVoltage(c.ref, v_br, "V+-V-"))
            branch_currents_list.append(BranchCurrent(c.ref, -i_out, "+->-"))
            net_kcl_leaving[p] = net_kcl_leaving[p] - i_out
            net_kcl_leaving[m] = net_kcl_leaving[m] + i_out

        elif t == "F":
            p, m = c.pins["+"], c.pins["-"]
            beta = DecimalComplex(c.value.to_base(), Decimal(0))
            ctrl = str(c.parameters["control_ref"]).upper()
            form = resolve_control(ctrl)
            # Evaluate control current from linear form
            i_ctrl = form[2]
            for net, coef in form[0].items():
                i_ctrl = i_ctrl + coef * node_v(net)
            for r_ref, coef in form[1].items():
                i_ctrl = i_ctrl + coef * sol_vec[vsource_index[r_ref]]
            i_out = beta * i_ctrl
            v_br = node_v(p) - node_v(m)
            branch_voltages_list.append(BranchVoltage(c.ref, v_br, "V+-V-"))
            branch_currents_list.append(BranchCurrent(c.ref, -i_out, "+->-"))
            net_kcl_leaving[p] = net_kcl_leaving[p] - i_out
            net_kcl_leaving[m] = net_kcl_leaving[m] + i_out

        elif t == "T":
            k1 = vsource_index[f"{c.ref}:1"]
            k2 = vsource_index[f"{c.ref}:2"]
            i1 = sol_vec[k1]
            i2 = sol_vec[k2]
            p1, p2 = c.pins["1"], c.pins["2"]
            s1, s2 = c.pins["3"], c.pins["4"]
            v1 = node_v(p1) - node_v(p2)
            v2 = node_v(s1) - node_v(s2)
            branch_voltages_list.append(BranchVoltage(f"{c.ref}:1", v1, "V1-V2"))
            branch_voltages_list.append(BranchVoltage(f"{c.ref}:2", v2, "V3-V4"))
            branch_currents_list.append(BranchCurrent(f"{c.ref}:1", i1, "1->2"))
            branch_currents_list.append(BranchCurrent(f"{c.ref}:2", i2, "3->4"))
            net_kcl_leaving[p1] = net_kcl_leaving[p1] + i1
            net_kcl_leaving[p2] = net_kcl_leaving[p2] - i1
            net_kcl_leaving[s1] = net_kcl_leaving[s1] + i2
            net_kcl_leaving[s2] = net_kcl_leaving[s2] - i2

    # Physical checks: KCL and KVL
    kcl_peak = max([magnitude(val) for val in net_kcl_leaving.values()] or [Decimal(0)])

    # KVL check over fundamental cycles
    kvl_peak = Decimal(0)
    for _a, _b, loop in fundamental_cycle_chords(circuit, ground):
        run = DecimalComplex.zero()
        for u, v in zip(loop, loop[1:] + loop[:1]):
            run = run + (node_v(u) - node_v(v))
        mag_run = magnitude(run)
        if mag_run > kvl_peak:
            kvl_peak = mag_run

    # Provenance and SHA-256 Digest
    prov_dict = {
        "engine": ENGINE_VERSION,
        "circuit_name": circuit.name,
        "n_nodes": len(nodes),
        "n_components": len(circuit.components),
        "frequency": op.to_dict(),
        "dc_operating_point_digest": dc_res.provenance.get("digest") if dc_res.provenance else "",
        "linear_solver": {
            "mode": "HIGH_PRECISION",
            "working_precision": 50,
            "status": lin_sol.status.value,
        },
        "status": final_status.value,
    }
    digest = hashlib.sha256(json.dumps(prov_dict, sort_keys=True).encode("utf-8")).hexdigest()

    diagnostics = [
        f"engine={ENGINE_VERSION}",
        f"status={final_status.value}",
        f"frequency={op.frequency.format()} (omega={op.omega} rad/s)",
        f"kcl_max_residual={kcl_peak}",
        f"kvl_max_residual={kvl_peak}",
        f"diodes_linearized={len(diodes_ss)}",
        f"bjts_linearized={len(bjts_ss)}",
        f"mosfets_linearized={len(mosfets_ss)}",
        f"jfets_linearized={len(jfets_ss)}",
    ]

    return SmallSignalACResult(
        status=final_status,
        operating_point=op,
        dc_operating_point=dc_res,
        node_voltages=tuple(node_voltages_list),
        branch_currents=tuple(branch_currents_list),
        branch_voltages=tuple(branch_voltages_list),
        diode_parameters=tuple(diodes_ss),
        bjt_parameters=tuple(bjts_ss),
        mosfet_parameters=tuple(mosfets_ss),
        jfet_parameters=tuple(jfets_ss),
        kcl_max_residual=kcl_peak,
        kvl_max_residual=kvl_peak,
        solver_result=lin_sol,
        numeric_mode=NumericMode.HIGH_PRECISION,
        provenance=prov_dict,
        diagnostics=tuple(diagnostics),
        digest=digest,
    )
