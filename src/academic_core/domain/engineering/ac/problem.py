"""AC MNA problem assembly (F8-D3).

Builds the complex ``A x = b`` system from the canonical F6 ``Circuit``
plus an :class:`ACOperatingPoint`, reusing the F8-B formulation rules
(sorted node order, auxiliary current unknown per ideal voltage source,
admittance stamping, current-source RHS injection, sign table) with
complex admittances:

* ``Y_R = 1/R``;
* ``Y_L = -j/(wL)``;
* ``Y_C = j*wC``;
* voltage source: +1/-1 coupling with constraint ``V(+) - V(-) = Vs``;
* current source: ``+Is`` injected at "+", ``-Is`` at "-" (F8-B rule).

Sign table (unequivocal, tests derive from it):

* branch current: pin "1" -> pin "2" (R/L/C), "+" -> "-" (V/I);
* branch voltage: V(pin1) - V(pin2), resp. V(+) - V(-);
* source current unknown: + -> - through the source;
* reported current-source branch current: -Is (through-element + -> -
  direction while Is is delivered into "+", exactly the F8-B rule).

EXACT eligibility (AUTO resolves; forced EXACT otherwise raises
``ACModeError``): no L/C anywhere (w = 2*pi*f is irrational, so any
inductive/capacitive susceptance leaves Q(j)), and every source phase
axis-aligned in degrees (0/90/180/270 mod 360). Pi is never forced
into a Fraction. Dependent gains are always exactly representable
(finite Decimal -> exact Fraction), so they never affect eligibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

from academic_core.domain.engineering.ac.errors import (
    ACFrequencyError,
    ACModeError,
    ACPhaseError,
    DimensionalityError,
    FloatingCircuitError,
    InvalidCircuitError,
    MissingReferenceError,
    UnsupportedElementError,
)
from academic_core.domain.engineering.ac.operating_point import ACOperatingPoint
from academic_core.domain.engineering.ac.topology import check_connected, reference_net
from academic_core.domain.engineering.circuit import Circuit
from academic_core.domain.engineering.math.decimal_complex import DecimalComplex
from academic_core.domain.engineering.math.linsolve.problem import NumericMode
from academic_core.domain.engineering.math.rational import RationalComplex
from academic_core.domain.engineering.math.trig import (
    decimal_cos,
    decimal_pi,
    decimal_sin,
    make_context,
)
from academic_core.domain.engineering.mna.dependent import (
    DEPENDENT_TYPES,
    VOLTAGE_BRANCH_TYPES,
    check_control_cycles,
    resolution_order,
    validate_dependent_structure,
)
from academic_core.domain.engineering.mna.errors import CircularControlError
from academic_core.domain.engineering.units import (
    ADMITTANCE,
    CAPACITANCE,
    CURRENT,
    DIMENSIONLESS,
    INDUCTANCE,
    RESISTANCE,
    VOLTAGE,
    Quantity,
    parse_quantity,
)

SUPPORTED_TYPES = frozenset({"R", "L", "C", "V", "I", "E", "G", "H", "F", "O", "T"})

_EXPECTED_DIMENSION = {
    "R": RESISTANCE, "L": INDUCTANCE, "C": CAPACITANCE,
    "V": VOLTAGE, "I": CURRENT,
    "E": DIMENSIONLESS, "G": ADMITTANCE, "H": RESISTANCE, "F": DIMENSIONLESS,
    "T": DIMENSIONLESS,
}

_FREQ_METADATA_KEYS = ("frequency", "freq", "f", "omega", "w")


@dataclass(frozen=True)
class ACBranch:
    """One derived branch: orientation pin1->pin2 (R/L/C) or +->- (V/I/E/G/H/F)."""

    ref: str
    type: str
    node_a: str
    node_b: str
    admittance: RationalComplex | DecimalComplex | None
    source: RationalComplex | DecimalComplex | None
    vsource_pos: int | None  # MNA auxiliary-unknown column, voltage branches (V/E/H)
    control: tuple | None = None  # dependent descriptor (F8-E) or None


@dataclass(frozen=True)
class ACMNAProblem:
    circuit: Circuit
    operating_point: ACOperatingPoint
    ground: str
    nodes: tuple[str, ...]
    node_index: dict
    vsource_refs: tuple[str, ...]
    vsource_index: dict  # ...plus ideal-transformer leg keys "T1:1"/"T1:2"
    branches: tuple[ACBranch, ...]
    matrix: tuple
    rhs: tuple
    kind: str  # "rational" | "decimal"
    tx_leg_refs: tuple[str, ...] = ()  # sorted T leg keys, 2 aux cols each

    @property
    def size(self) -> int:
        return len(self.nodes) + len(self.vsource_refs) + len(self.tx_leg_refs)


def _phase_decimal(raw: object) -> Decimal:
    if isinstance(raw, bool):
        raise ACPhaseError("bool phase is rejected (exactness boundary)")
    if isinstance(raw, int):
        return Decimal(raw)
    if isinstance(raw, Decimal):
        if not raw.is_finite():
            raise ACPhaseError(f"non-finite phase {raw!r}")
        return raw
    if isinstance(raw, Fraction):
        ctx = make_context()
        return ctx.divide(Decimal(raw.numerator), Decimal(raw.denominator))
    if isinstance(raw, str):
        try:
            v = Decimal(raw.strip())
        except Exception:
            raise ACPhaseError(f"unparseable phase {raw!r}") from None
        if not v.is_finite():
            raise ACPhaseError(f"non-finite phase {raw!r}")
        return v
    raise ACPhaseError(
        f"phase must be int/Decimal/Fraction/str (degrees or radians per "
        f"phase_unit), got {type(raw).__name__}; float is rejected "
        f"(exactness boundary)"
    )


def _check_frequency_metadata(params: dict, op: ACOperatingPoint, ref: str) -> None:
    from academic_core.domain.engineering.units import FREQUENCY, parse_unit

    hz = parse_unit("Hz")
    for key in _FREQ_METADATA_KEYS:
        if key not in params:
            continue
        raw = params[key]
        angular = key.strip().lower() in ("omega", "w")
        q = None
        if isinstance(raw, Quantity):
            q = raw
        elif isinstance(raw, bool):
            raise ACFrequencyError(
                f"{ref}: uninterpretable frequency metadata {key}={raw!r}"
            )
        elif isinstance(raw, int):
            q = Quantity(Decimal(raw), hz)
        elif isinstance(raw, Decimal):
            if not raw.is_finite():
                raise ACFrequencyError(
                    f"{ref}: non-finite frequency metadata {key}={raw!r}"
                )
            q = Quantity(raw, hz)
        elif isinstance(raw, str):
            try:
                q = parse_quantity(raw.strip())
            except Exception:
                try:
                    q = Quantity(Decimal(raw.strip()), hz)
                except Exception:
                    raise ACFrequencyError(
                        f"{ref}: unparseable frequency metadata {key}={raw!r}"
                    ) from None
        else:
            raise ACFrequencyError(
                f"{ref}: unparseable frequency metadata {key}={raw!r}"
            )
        if angular:
            same = (q.dimension == FREQUENCY and q.to_base() == op.omega)
        else:
            same = (q.dimension == FREQUENCY
                    and q.to_base() == op.frequency.to_base())
        if not same:
            raise ACFrequencyError(
                f"{ref}: incompatible per-source frequency metadata "
                f"{key}={raw!r} vs operating point {op.frequency.format()} "
                f"(sources never carry their own frequency)"
            )


def _axis_quadrant(phase_deg: Decimal) -> int | None:
    """0/1/2/3 for exact axis alignment, else None (all exact Decimal ops).

    NOTE: ``Decimal.__mod__`` takes the dividend's sign (``-90 % 360 ==
    -90``), unlike int ``%``, so negative phases are normalized
    explicitly into [0, 360).
    """
    q = phase_deg % Decimal(360)
    if q < 0:
        q = q + Decimal(360)
    for deg, quad in ((0, 0), (90, 1), (180, 2), (270, 3)):
        if q == Decimal(deg):
            return quad
    return None


def _source_phasor_exact(value_base: Decimal, params: dict) -> RationalComplex | None:
    """Exact phasor, or None when the phase is not exactly axis-aligned."""
    unit = str(params.get("phase_unit", "deg")).strip().lower()
    if unit != "deg":
        return None
    quad = _axis_quadrant(_phase_decimal(params.get("phase", 0)))
    if quad is None:
        return None
    mag = Fraction(value_base)
    if quad == 0:
        return RationalComplex(mag, Fraction(0))
    if quad == 1:
        return RationalComplex(Fraction(0), mag)
    if quad == 2:
        return RationalComplex(-mag, Fraction(0))
    return RationalComplex(Fraction(0), -mag)


def _source_phasor_hp(
    value_base: Decimal, params: dict, ctx
) -> DecimalComplex:
    unit = str(params.get("phase_unit", "deg")).strip().lower()
    if unit not in ("deg", "rad"):
        raise ACPhaseError(
            f"phase_unit must be 'deg' or 'rad', got {params.get('phase_unit')!r}"
        )
    ph = _phase_decimal(params.get("phase", 0))
    if unit == "deg":
        angle = ctx.multiply(ph, ctx.divide(decimal_pi(), Decimal(180)))
    else:
        angle = ph
    mag = value_base
    return DecimalComplex(
        ctx.multiply(mag, decimal_cos(angle, ctx)),
        ctx.multiply(mag, decimal_sin(angle, ctx)),
    )


def _validate_components(circuit: Circuit, op: ACOperatingPoint) -> None:
    if not circuit.components:
        raise InvalidCircuitError(f"circuit {circuit.name!r} has no components")
    seen: set[str] = set()
    for c in circuit.components:
        if c.ref.upper() in seen:
            raise InvalidCircuitError(f"duplicate reference: {c.ref}")
        seen.add(c.ref.upper())
        t = c.type.upper()
        if t not in SUPPORTED_TYPES:
            raise UnsupportedElementError(
                f"{c.ref}: type {c.type!r} is outside the AC domain "
                f"(ideal R/L/C, independent V/I, dependent E/G/H/F and "
                f"ideal op-amp O only)"
            )
        if t == "O":
            # Ideal op-amp: parameter-free by design (see F8-B twin rule).
            if c.value is not None:
                raise InvalidCircuitError(
                    f"{c.ref}: ideal op-amp takes no value, got "
                    f"{c.value.format()}")
            if c.parameters:
                raise InvalidCircuitError(
                    f"{c.ref}: ideal op-amp takes no parameters, got "
                    f"{sorted(c.parameters)}")
            continue
        if t == "T":
            # Ideal transformer: turns ratio n in `value`
            # (dimensionless), no parameters. n = 0/negative allowed;
            # only finiteness is required (twin of the F8-B rule).
            if c.parameters:
                raise InvalidCircuitError(
                    f"{c.ref}: ideal transformer takes no parameters, got "
                    f"{sorted(c.parameters)}")
            if c.value is None:
                raise InvalidCircuitError(
                    f"{c.ref}: missing required turns-ratio value")
            if c.value.dimension != DIMENSIONLESS:
                raise DimensionalityError(
                    f"{c.ref}: value {c.value.format()} has the wrong "
                    f"dimension for a T component (dimensionless turns "
                    f"ratio required)")
            if not c.value.to_base().is_finite():
                raise InvalidCircuitError(
                    f"{c.ref}: non-finite turns ratio {c.value.format()}")
            continue
        if c.value is None:
            raise InvalidCircuitError(f"{c.ref}: missing required value")
        expected = _EXPECTED_DIMENSION[t]
        if c.value.dimension != expected:
            raise DimensionalityError(
                f"{c.ref}: value {c.value.format()} has the wrong dimension "
                f"for a {t} component"
            )
        base = c.value.to_base()
        if not base.is_finite():
            raise InvalidCircuitError(f"{c.ref}: non-finite value {c.value.format()}")
        if t in ("R", "L", "C") and base <= 0:
            raise InvalidCircuitError(
                f"{c.ref}: {t} must be > 0 in the declared ideal model, "
                f"got {c.value.format()} (R=0 shorts and C/L=0 degenerate "
                f"values are outside the model; use MNA-compatible "
                f"short/open structures instead)"
            )
        if t in ("V", "I"):
            _check_frequency_metadata(c.parameters, op, c.ref)
            unit = str(c.parameters.get("phase_unit", "deg")).strip().lower()
            if unit not in ("deg", "rad"):
                raise ACPhaseError(
                    f"{c.ref}: phase_unit must be 'deg' or 'rad', "
                    f"got {c.parameters.get('phase_unit')!r}"
                )
            _phase_decimal(c.parameters.get("phase", 0))
        if t in DEPENDENT_TYPES and not base.is_finite():
            raise InvalidCircuitError(
                f"{c.ref}: non-finite gain {c.value.format()}")
    validate_dependent_structure(circuit)
    check_control_cycles(circuit)


def _exact_eligible(circuit: Circuit) -> tuple[bool, str]:
    for c in circuit.components:
        t = c.type.upper()
        if t in ("L", "C"):
            return False, f"{c.ref}: {t} brings w=2*pi*f (irrational) into play"
        if t in ("V", "I"):
            unit = str(c.parameters.get("phase_unit", "deg")).strip().lower()
            if unit != "deg":
                return False, f"{c.ref}: radian phases are not axis-checkable exactly"
            if _axis_quadrant(_phase_decimal(c.parameters.get("phase", 0))) is None:
                return False, f"{c.ref}: non-axis-aligned phase needs trigonometry"
    return True, "R-only with axis-aligned degree phases"


def build_ac_problem(
    circuit: Circuit,
    operating_point: ACOperatingPoint,
    mode: NumericMode = NumericMode.AUTO,
) -> ACMNAProblem:
    """Validate and assemble the AC MNA ``A x = b`` system.

    Raises the typed errors of :mod:`ac.errors` for anything outside the
    declared domain. Never proceeds silently. With ``mode=AUTO`` the
    assembly is EXACT iff every coefficient stays exactly representable
    (R-only, axis-aligned degree phases); otherwise HIGH_PRECISION.
    Forced EXACT on an inexact-representable circuit raises ACModeError.
    """
    if not isinstance(mode, NumericMode):
        raise ACModeError(f"mode must be a NumericMode, got {mode!r}")
    _validate_components(circuit, operating_point)
    ground = reference_net(circuit.nets)
    if ground != operating_point.reference_node:
        raise InvalidCircuitError(
            f"operating point reference {operating_point.reference_node!r} "
            f"does not match circuit ground {ground!r}"
        )
    check_connected(circuit.nets, circuit.components, ground)

    eligible, reason = _exact_eligible(circuit)
    if mode == NumericMode.AUTO:
        exact = eligible
    elif mode == NumericMode.EXACT:
        if not eligible:
            raise ACModeError(
                f"EXACT mode refused: {reason} (forcing pi/irrationals "
                f"into Fraction would fake exactness)"
            )
        exact = True
    else:
        exact = False

    nodes = tuple(sorted(n for n in circuit.nets if n != ground))
    node_index = {n: i for i, n in enumerate(nodes)}
    vsource_refs = tuple(sorted(
        c.ref for c in circuit.components
        if c.type.upper() in VOLTAGE_BRANCH_TYPES))
    # Ideal-transformer leg keys ("T1:1" primary, "T1:2" secondary) share
    # the vsource aux namespace, mirroring F8-B: each leg owns exactly
    # one MNA current unknown, allocated deterministically after the
    # single-aux refs.
    tx_leg_refs = tuple(sorted(
        f"{c.ref}:{leg}" for c in circuit.components
        for leg in (1, 2) if c.type.upper() == "T"))
    n_nodes = len(nodes)
    vsource_index = {ref: n_nodes + j for j, ref in enumerate(vsource_refs)}
    tx_index = {ref: n_nodes + len(vsource_refs) + j
                for j, ref in enumerate(tx_leg_refs)}
    vsource_index.update(tx_index)
    size = n_nodes + len(vsource_refs) + len(tx_leg_refs)
    ctx = make_context()
    omega = operating_point.omega

    zero = RationalComplex.zero() if exact else DecimalComplex.zero()
    one = RationalComplex.one() if exact else DecimalComplex.one()
    matrix = [[zero for _ in range(size)] for _ in range(size)]
    rhs = [zero for _ in range(size)]
    branches: list[ACBranch] = []

    def idx(net: str) -> int | None:
        return node_index.get(net)

    def native_gain(c):
        base = c.value.to_base()
        if exact:
            return RationalComplex(Fraction(base), Fraction(0))
        return DecimalComplex(base, Decimal(0))

    def branch_admittance(t: str, base: Decimal):
        if t == "R":
            return (RationalComplex(Fraction(1) / Fraction(base), Fraction(0))
                    if exact else DecimalComplex(ctx.divide(Decimal(1), base), Decimal(0)))
        elif t == "L":
            wl = ctx.multiply(omega, base)
            return DecimalComplex(Decimal(0), ctx.divide(Decimal(-1), wl))
        else:
            wc = ctx.multiply(omega, base)
            return DecimalComplex(Decimal(0), wc)

    by_ref = {c.ref.upper(): c for c in circuit.components}
    adm_of = {c.ref.upper(): branch_admittance(c.type.upper(), c.value.to_base())
              for c in circuit.components if c.type.upper() in ("R", "L", "C")}
    src_of = {}
    for c in circuit.components:
        if c.type.upper() == "I":
            base = c.value.to_base() if c.value is not None else Decimal(0)
            src_of[c.ref.upper()] = (
                _source_phasor_exact(base, c.parameters) if exact
                else _source_phasor_hp(base, c.parameters, ctx))

    # Control-current linear forms over unknowns (native numbers),
    # following D3 reconstructed branch-current conventions. Cycles are
    # excluded at validation; the active set is defense in depth.
    resolved: dict = {}

    def resolve_control(ref_upper: str, active: tuple = ()):
        if ref_upper in resolved:
            return resolved[ref_upper]
        if ref_upper in active:
            raise CircularControlError(
                f"circular current control involving {ref_upper}")
        target = by_ref[ref_upper]
        t = target.type.upper()
        z0 = RationalComplex(Fraction(0), Fraction(0)) if exact \
            else DecimalComplex(Decimal(0), Decimal(0))
        o1 = RationalComplex(Fraction(1), Fraction(0)) if exact \
            else DecimalComplex(Decimal(1), Decimal(0))
        if t in VOLTAGE_BRANCH_TYPES and t != "O":
            form = ({}, {target.ref: o1}, z0)
        elif t == "O":
            # Op-amp output leg (out -> ground return) reports -i_o.
            form = ({}, {target.ref: -o1}, z0)
        elif t in ("R", "L", "C"):
            y = adm_of[ref_upper]
            a, b = target.pins["1"], target.pins["2"]
            form = ({a: y, b: -y}, {}, z0)
        elif t == "I":
            form = ({}, {}, -src_of[ref_upper])
        elif t == "G":
            gm = native_gain(target)
            p = target.parameters
            form = ({p["cp"]: -gm, p["cn"]: gm}, {}, z0)
        elif t == "F":
            beta = native_gain(target)
            ctrl = str(target.parameters["control_ref"]).upper()
            sub = resolve_control(ctrl, active + (ref_upper,))
            form = (
                {n: -beta * v for n, v in sub[0].items()},
                {r: -beta * v for r, v in sub[1].items()},
                -beta * sub[2],
            )
        else:
            raise UnsupportedElementError(
                f"{target.ref}: type {t!r} cannot carry control current")
        resolved[ref_upper] = form
        return form

    for _ref in resolution_order(circuit):
        resolve_control(_ref)

    def apply_form(row: int, form, scale, *, negate: bool) -> None:
        """Add scale·form (or its negation) to a KCL/constraint row.

        Variable coefficients take the row sign; the constant keeps the
        equation's right-hand side (KCL at "+" reads ``other = +J``,
        at "-" ``other = -J``; constraints read ``Vout = +r·Ictrl``).
        """
        for net, coef in form[0].items():
            j = idx(net)
            if j is not None:
                if negate:
                    matrix[row][j] = matrix[row][j] - scale * coef
                else:
                    matrix[row][j] = matrix[row][j] + scale * coef
        for ref, coef in form[1].items():
            if negate:
                matrix[row][vsource_index[ref]] = \
                    matrix[row][vsource_index[ref]] - scale * coef
            else:
                matrix[row][vsource_index[ref]] = \
                    matrix[row][vsource_index[ref]] + scale * coef
        if negate:
            rhs[row] = rhs[row] + scale * form[2]
        else:
            rhs[row] = rhs[row] - scale * form[2]

    for c in sorted(circuit.components, key=lambda e: e.ref.upper()):
        t = c.type.upper()
        base = c.value.to_base() if c.value is not None else Decimal(0)
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
            branches.append(ACBranch(c.ref, t, a, b, y, None, None))
        elif t == "I":
            a, b = c.pins["+"], c.pins["-"]
            ph = src_of[c.ref.upper()]
            assert ph is not None
            ip, im = idx(a), idx(b)
            if ip is not None:
                rhs[ip] = rhs[ip] + ph
            if im is not None:
                rhs[im] = rhs[im] - ph
            branches.append(ACBranch(c.ref, t, a, b, None, ph, None))
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
                ph = (_source_phasor_exact(base, c.parameters) if exact
                      else _source_phasor_hp(base, c.parameters, ctx))
                assert ph is not None
                rhs[k] = rhs[k] + ph
                branches.append(ACBranch(c.ref, t, a, b, None, ph, k))
            elif t == "E":
                # VCVS: V(+) - V(-) - μ·(Vcp - Vcn) = 0.
                mu = native_gain(c)
                icp, icn = idx(c.parameters["cp"]), idx(c.parameters["cn"])
                if icp is not None:
                    matrix[k][icp] = matrix[k][icp] - mu
                if icn is not None:
                    matrix[k][icn] = matrix[k][icn] + mu
                branches.append(ACBranch(
                    c.ref, t, a, b, None, None, k,
                    ("E", c.parameters["cp"], c.parameters["cn"], mu)))
            else:  # H — CCVS: V(+) - V(-) - r·Icontrol = 0.
                r = native_gain(c)
                ctrl = str(c.parameters["control_ref"]).upper()
                apply_form(k, resolve_control(ctrl), r, negate=True)
                branches.append(ACBranch(
                    c.ref, t, a, b, None, None, k, ("H", ctrl, r)))
        elif t == "O":
            # Ideal op-amp (nullor): constraint V(in+) - V(in-) = 0 plus
            # one auxiliary current unknown i_o delivered INTO "o"
            # (KCL sum-leaving at "o": -i_o). Inputs draw nothing.
            # rhs[k] stays zero (matrix/rhs start zeroed).
            inp, inm = idx(c.pins["+"]), idx(c.pins["-"])
            io = idx(c.pins["o"])
            k = vsource_index[c.ref]
            if io is not None:
                matrix[io][k] = matrix[io][k] - one
            if inp is not None:
                matrix[k][inp] = matrix[k][inp] + one
            if inm is not None:
                matrix[k][inm] = matrix[k][inm] - one
            branches.append(ACBranch(c.ref, t, c.pins["o"], ground,
                                     None, None, k))
        elif t == "G":
            # VCCS: J = gm·(Vcp - Vcn) delivered into "+" (I-convention).
            gm = native_gain(c)
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
            branches.append(ACBranch(
                c.ref, t, a, b, None, None, None,
                ("G", c.parameters["cp"], c.parameters["cn"], gm)))
        elif t == "F":
            # CCCS: J = β·Icontrol delivered into "+" (I-convention).
            beta = native_gain(c)
            a, b = c.pins["+"], c.pins["-"]
            ip, im = idx(a), idx(b)
            ctrl = str(c.parameters["control_ref"]).upper()
            form = resolve_control(ctrl)
            if ip is not None:
                apply_form(ip, form, beta, negate=True)
            if im is not None:
                apply_form(im, form, beta, negate=False)
            branches.append(ACBranch(
                c.ref, t, a, b, None, None, None, ("F", ctrl, beta)))
        elif t == "T":
            # Ideal transformer (turns ratio n): aux i1 = current 1->2,
            # aux i2 = current 3->4 (both leaving their "+" pin, exactly
            # like a V branch aux). Constraints: V(3)-V(4)-n(V(1)-V(2))
            # = 0 on row k1, and I1+n·I2 = 0 on row k2. Two leg records
            # ("T1:1"/"T1:2") keep every ref-keyed consumer generic.
            base = c.value.to_base()
            n = RationalComplex(Fraction(base), Fraction(0)) if exact \
                else DecimalComplex(base, Decimal(0))
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
                matrix[k1][p1] = matrix[k1][p1] - n
            if p2 is not None:
                matrix[k1][p2] = matrix[k1][p2] + n
            matrix[k2][k1] = matrix[k2][k1] + one
            matrix[k2][k2] = matrix[k2][k2] + n
            branches.append(ACBranch(f"{c.ref}:1", t, c.pins["1"], c.pins["2"],
                                     None, None, k1))
            branches.append(ACBranch(f"{c.ref}:2", t, c.pins["3"], c.pins["4"],
                                     None, None, k2))
        else:  # pragma: no cover - validation gates all types above
            raise UnsupportedElementError(
                f"{c.ref}: type {c.type!r} has no AC stamp")

    branches.sort(key=lambda br: br.ref.upper())
    return ACMNAProblem(
        circuit=circuit,
        operating_point=operating_point,
        ground=ground,
        nodes=nodes,
        node_index=node_index,
        vsource_refs=vsource_refs,
        vsource_index=vsource_index,
        branches=tuple(branches),
        matrix=tuple(tuple(row) for row in matrix),
        rhs=tuple(rhs),
        kind="rational" if exact else "decimal",
        tx_leg_refs=tx_leg_refs,
    )
