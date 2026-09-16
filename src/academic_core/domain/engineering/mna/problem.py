"""Validation + Modified Nodal Analysis matrix assembly.

Converts a canonical `Circuit` (F6) into an `MNAProblem`: the deterministic
`A x = z` system, plus enough bookkeeping (node/branch index maps) to later
recover node voltages, branch currents and element powers. Construction is
separated from the numeric solve (`linear.solve_exact`) so each layer is
independently testable/auditable (spec section 33).

Unknowns: one node-voltage variable per non-reference net (sorted by net
name for determinism), followed by one branch-current variable per ideal
voltage branch (independent V plus dependent E/H outputs, sorted by
component ref).

Sign conventions (documented once, used consistently everywhere in F8-B):
  * Resistor: current flows from pin "1" to pin "2"; I = (V1 - V2) / R.
  * Voltage source: the MNA unknown current I_V is defined flowing from
    pin "+" to pin "-" through the source. KCL row for "+" gets +I_V, KCL
    row for "-" gets -I_V; the source's own constraint row is
    V(+) - V(-) = Vs.
  * Current source: Is is defined flowing out of pin "-" and into pin "+"
    of the external circuit (i.e. delivered into the circuit at "+"),
    contributing +Is to node "+"'s injected-current term and -Is to node
    "-"'s. For *reporting* (branch current / power), the same "+ -> -"
    through-the-element direction used by every other element is applied,
    so the reported branch current is -Is (opposite of the delivered
    direction) — see `mna.solver` for the derivation.
  * Power for every element uses the passive sign convention with the same
    "pin1 -> pin2" (or "+ -> -") direction as its branch current:
    P = (V(pin1) - V(pin2)) * I(pin1->pin2). Positive = absorbed. This
    convention is what makes total power sum to exactly zero (Tellegen's
    theorem) for a consistent DC solve.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.mna.dependent import (
    DEPENDENT_TYPES,
    VOLTAGE_BRANCH_TYPES,
    check_control_cycles,
    describe_dependents,
    gain_fraction,
    resolution_order,
    validate_dependent_structure,
)
from academic_core.domain.engineering.mna.errors import (
    CircularControlError,
    DimensionalityError,
    FloatingCircuitError,
    InvalidCircuitError,
    MissingReferenceError,
    UnsupportedElementError,
)
from academic_core.domain.engineering.units import (
    ADMITTANCE,
    CURRENT,
    DIMENSIONLESS,
    RESISTANCE,
    VOLTAGE,
    Quantity,
)

SUPPORTED_TYPES = frozenset({"R", "V", "I", "E", "G", "H", "F", "O", "T"})

_EXPECTED_DIMENSION = {
    "R": RESISTANCE, "V": VOLTAGE, "I": CURRENT,
    "E": DIMENSIONLESS, "G": ADMITTANCE, "H": RESISTANCE, "F": DIMENSIONLESS,
    "T": DIMENSIONLESS,
}


def _to_fraction(q: Quantity) -> Fraction:
    return Fraction(q.to_base())


def _reference_net(circuit: Circuit) -> str:
    candidates = sorted({net for net in circuit.nets if net.strip().upper() in ("0", "GND")})
    if not candidates:
        raise MissingReferenceError(
            f"circuit {circuit.name!r} has no reference node "
            f"(expected a net named '0' or 'GND', case-insensitive)"
        )
    if len(candidates) > 1:
        raise MissingReferenceError(
            f"circuit {circuit.name!r} has ambiguous/incompatible reference "
            f"nodes: {candidates!r} (only one '0'/'GND' net is allowed)"
        )
    return candidates[0]


def _validate_components(circuit: Circuit) -> None:
    if not circuit.components:
        raise InvalidCircuitError(f"circuit {circuit.name!r} has no components")
    seen_refs: set[str] = set()
    for c in circuit.components:
        if c.ref.upper() in seen_refs:
            raise InvalidCircuitError(f"duplicate reference: {c.ref}")
        seen_refs.add(c.ref.upper())
        if c.type.upper() not in SUPPORTED_TYPES:
            raise UnsupportedElementError(
                f"{c.ref}: component type {c.type!r} is NOT_SUPPORTED by the "
                f"F8-B linear DC solver (domain: R, V, I, dependent "
                f"E, G, H, F, ideal op-amp O, ideal transformer T)"
            )
        if c.type.upper() == "O":
            # Ideal op-amp: parameter-free by design. A value or parameters
            # would be silently ignored physics — reject loudly instead.
            if c.value is not None:
                raise InvalidCircuitError(
                    f"{c.ref}: ideal op-amp takes no value, got "
                    f"{c.value.format()}")
            if c.parameters:
                raise InvalidCircuitError(
                    f"{c.ref}: ideal op-amp takes no parameters, got "
                    f"{sorted(c.parameters)}")
            continue
        if c.type.upper() == "T":
            # Ideal transformer: turns ratio n in `value` (dimensionless),
            # no parameters. n = 0/negative allowed (degenerate/inverting);
            # only finiteness is required.
            if c.parameters:
                raise InvalidCircuitError(
                    f"{c.ref}: ideal transformer takes no parameters, got "
                    f"{sorted(c.parameters)}")
        if c.value is None:
            raise InvalidCircuitError(f"{c.ref}: missing required value")
        expected_dim = _EXPECTED_DIMENSION[c.type.upper()]
        if c.value.dimension != expected_dim:
            raise DimensionalityError(
                f"{c.ref}: value {c.value.format()} has the wrong dimension "
                f"for a {c.type.upper()} component"
            )
        if c.type.upper() == "R" and c.value.to_base() <= 0:
            raise InvalidCircuitError(f"{c.ref}: resistance must be > 0, got {c.value.format()}")
        if c.type.upper() in DEPENDENT_TYPES and not c.value.to_base().is_finite():
            raise InvalidCircuitError(f"{c.ref}: non-finite gain {c.value.format()}")
        if c.type.upper() == "T" and not c.value.to_base().is_finite():
            raise InvalidCircuitError(
                f"{c.ref}: non-finite turns ratio {c.value.format()}")
    validate_dependent_structure(circuit)
    check_control_cycles(circuit)


def _connected_nets(circuit: Circuit) -> dict[str, set[str]]:
    """Union-find over nets, edges from every component's own pins."""
    parent: dict[str, str] = {net: net for net in circuit.nets}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for c in circuit.components:
        pin_nets = list(c.pins.values())
        for other in pin_nets[1:]:
            union(pin_nets[0], other)

    groups: dict[str, set[str]] = {}
    for net in circuit.nets:
        groups.setdefault(find(net), set()).add(net)
    return groups


def _check_reachability(circuit: Circuit, ground: str) -> None:
    groups = _connected_nets(circuit)
    ground_group = next(g for g in groups.values() if ground in g)
    unreachable = sorted(net for net in circuit.nets if net not in ground_group)
    if unreachable:
        raise FloatingCircuitError(
            f"circuit {circuit.name!r} has node(s) with no path to the "
            f"reference node {ground!r}: {unreachable!r}"
        )


@dataclass(frozen=True)
class MNAProblem:
    circuit: Circuit
    ground: str
    nodes: tuple[str, ...]  # non-reference nets, sorted
    node_index: dict
    vsource_refs: tuple[str, ...]  # sorted refs of voltage branches (V, E, H)
    vsource_index: dict  # ...plus ideal-transformer leg keys "T1:1"/"T1:2"
    matrix: tuple
    rhs: tuple
    tx_leg_refs: tuple[str, ...] = ()  # sorted T leg keys, 2 aux cols each

    @property
    def size(self) -> int:
        return len(self.nodes) + len(self.vsource_refs) + len(self.tx_leg_refs)


def build_mna_problem(circuit: Circuit) -> MNAProblem:
    """Validate `circuit` and assemble its MNA `A x = z` system.

    Raises `InvalidCircuitError`, `UnsupportedElementError`,
    `DimensionalityError`, `MissingReferenceError` or `FloatingCircuitError`
    for any circuit outside F8-B's declared domain. Never proceeds silently.
    """
    _validate_components(circuit)
    ground = _reference_net(circuit)
    _check_reachability(circuit, ground)

    nodes = tuple(sorted(n for n in circuit.nets if n != ground))
    node_index = {n: i for i, n in enumerate(nodes)}

    vsource_refs = tuple(sorted(
        c.ref for c in circuit.components if c.type.upper() in VOLTAGE_BRANCH_TYPES))
    # Ideal-transformer leg keys ("T1:1" primary, "T1:2" secondary) share
    # the vsource aux namespace: each leg owns exactly one MNA current
    # unknown, allocated deterministically after the single-aux refs.
    # F8-E resolve_control/apply_form and F8-C i_v_map address aux unknowns
    # exclusively through vsource_index, so legs compose without new fields.
    tx_leg_refs = tuple(sorted(
        f"{c.ref}:{leg}" for c in circuit.components
        for leg in (1, 2) if c.type.upper() == "T"))
    n_nodes = len(nodes)
    vsource_index = {ref: n_nodes + j for j, ref in enumerate(vsource_refs)}
    tx_index = {ref: n_nodes + len(vsource_refs) + j
                for j, ref in enumerate(tx_leg_refs)}
    vsource_index.update(tx_index)

    size = n_nodes + len(vsource_refs) + len(tx_leg_refs)
    matrix = [[Fraction(0) for _ in range(size)] for _ in range(size)]
    rhs = [Fraction(0) for _ in range(size)]

    def idx(net: str) -> int | None:
        return node_index.get(net)

    by_ref = {c.ref.upper(): c for c in circuit.components}

    def gain_of(c) -> Fraction:
        return gain_fraction(c.value)

    # Control-current linear forms over unknowns: ({net: coef}, {aux: coef},
    # const), following D3/F8-B reconstructed branch-current conventions
    # (pin1->pin2 for R, +->- aux unknown for V/E/H, -Is for I,
    # -gm·ΔV for G, -β·Ictrl for F). Reported orientation throughout:
    # H constraints (Vout = r·Irep) and F stamps (delivered +β·Irep
    # into "+") both consume these reported forms. Cycles are excluded
    # at validation; the active set below is defense in depth.
    resolved: dict[str, tuple[dict, dict, Fraction]] = {}

    def resolve_control(ref_upper: str, active: tuple[str, ...] = ()) -> tuple[dict, dict, Fraction]:
        if ref_upper in resolved:
            return resolved[ref_upper]
        if ref_upper in active:
            raise CircularControlError(
                f"circular current control involving {ref_upper}")
        target = by_ref[ref_upper]
        t = target.type.upper()
        if t in VOLTAGE_BRANCH_TYPES and t != "O":
            form = ({}, {target.ref: 1}, Fraction(0))
        elif t == "O":
            # Op-amp output leg (out -> ground return) reports -i_o;
            # control sees the reconstructed branch current.
            form = ({}, {target.ref: -1}, Fraction(0))
        elif t == "R":
            r = Fraction(target.value.to_base())
            a, b = target.pins["1"], target.pins["2"]
            form = ({a: Fraction(1) / r, b: -Fraction(1) / r}, {}, Fraction(0))
        elif t == "I":
            form = ({}, {}, -Fraction(target.value.to_base()))
        elif t == "G":
            gm = gain_of(target)
            p = target.parameters
            form = ({p["cp"]: -gm, p["cn"]: gm}, {}, Fraction(0))
        elif t == "F":
            beta = gain_of(target)
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

    def apply_form(row: int, form, scale: Fraction, *, negate: bool) -> None:
        """Add scale·form (or its negation) to a KCL/constraint row.

        Variable coefficients take the row sign; the constant term keeps
        the equation's right-hand side: KCL at "+" reads
        ``other_leaving = +J`` (source delivers into "+"), at "-"
        ``other_leaving = -J``. Same pattern for constraint rows
        (``Vout - r·Ictrl = 0`` reads ``Vout = +r·Ictrl``).
        """
        sign = Fraction(-1) if negate else Fraction(1)
        for net, coef in form[0].items():
            j = idx(net)
            if j is not None:
                matrix[row][j] += sign * scale * coef
        for ref, coef in form[1].items():
            matrix[row][vsource_index[ref]] += sign * scale * coef
        rhs[row] -= sign * scale * form[2]

    for c in circuit.components:
        t = c.type.upper()
        if t == "R":
            g = Fraction(1) / _to_fraction(c.value)
            i1, i2 = idx(c.pins["1"]), idx(c.pins["2"])
            if i1 is not None:
                matrix[i1][i1] += g
            if i2 is not None:
                matrix[i2][i2] += g
            if i1 is not None and i2 is not None:
                matrix[i1][i2] -= g
                matrix[i2][i1] -= g
        elif t == "I":
            is_val = _to_fraction(c.value)
            ip, im = idx(c.pins["+"]), idx(c.pins["-"])
            if ip is not None:
                rhs[ip] += is_val
            if im is not None:
                rhs[im] -= is_val
        elif t == "V":
            vs_val = _to_fraction(c.value)
            ip, im = idx(c.pins["+"]), idx(c.pins["-"])
            k = vsource_index[c.ref]
            if ip is not None:
                matrix[ip][k] += 1
                matrix[k][ip] += 1
            if im is not None:
                matrix[im][k] -= 1
                matrix[k][im] -= 1
            rhs[k] += vs_val
        elif t == "E":
            # VCVS: V(+) - V(-) - μ·(Vcp - Vcn) = 0, aux current like V.
            mu = gain_of(c)
            ip, im = idx(c.pins["+"]), idx(c.pins["-"])
            k = vsource_index[c.ref]
            if ip is not None:
                matrix[ip][k] += 1
                matrix[k][ip] += 1
            if im is not None:
                matrix[im][k] -= 1
                matrix[k][im] -= 1
            icp, icn = idx(c.parameters["cp"]), idx(c.parameters["cn"])
            if icp is not None:
                matrix[k][icp] -= mu
            if icn is not None:
                matrix[k][icn] += mu
        elif t == "H":
            # CCVS: V(+) - V(-) - r·Icontrol = 0, aux current like V.
            r = gain_of(c)
            ip, im = idx(c.pins["+"]), idx(c.pins["-"])
            k = vsource_index[c.ref]
            if ip is not None:
                matrix[ip][k] += 1
                matrix[k][ip] += 1
            if im is not None:
                matrix[im][k] -= 1
                matrix[k][im] -= 1
            form = resolve_control(str(c.parameters["control_ref"]).upper())
            apply_form(k, form, r, negate=True)
        elif t == "O":
            # Ideal op-amp (nullor): constraint V(in+) - V(in-) = 0 plus
            # one auxiliary current unknown i_o delivered INTO the output
            # node (KCL sum-leaving at "o": -i_o). Inputs draw nothing:
            # no stamp entries at "+" / "-" is the exact open circuit.
            # rhs[k] stays 0 (matrix/rhs start zeroed).
            inp, inm = idx(c.pins["+"]), idx(c.pins["-"])
            io = idx(c.pins["o"])
            k = vsource_index[c.ref]
            if io is not None:
                matrix[io][k] -= 1
            if inp is not None:
                matrix[k][inp] += 1
            if inm is not None:
                matrix[k][inm] -= 1
        elif t == "G":
            # VCCS: J = gm·(Vcp - Vcn) delivered into "+" (I-convention).
            gm = gain_of(c)
            ip, im = idx(c.pins["+"]), idx(c.pins["-"])
            icp, icn = idx(c.parameters["cp"]), idx(c.parameters["cn"])
            if ip is not None:
                if icp is not None:
                    matrix[ip][icp] -= gm
                if icn is not None:
                    matrix[ip][icn] += gm
            if im is not None:
                if icp is not None:
                    matrix[im][icp] += gm
                if icn is not None:
                    matrix[im][icn] -= gm
        elif t == "F":
            # CCCS: J = β·Icontrol delivered into "+" (I-convention).
            beta = gain_of(c)
            ip, im = idx(c.pins["+"]), idx(c.pins["-"])
            form = resolve_control(str(c.parameters["control_ref"]).upper())
            if ip is not None:
                apply_form(ip, form, beta, negate=True)
            if im is not None:
                apply_form(im, form, beta, negate=False)
        elif t == "T":
            # Ideal transformer (turns ratio n): aux i1 = current 1->2,
            # aux i2 = current 3->4 (both leaving their "+" pin, exactly
            # like a V branch aux). Constraints: V(3)-V(4)-n(V(1)-V(2))
            # = 0 on row k1, and I1+n·I2 = 0 on row k2. Both rows/cols
            # keep the matrix square (+2 unknowns, +2 equations).
            n = Fraction(c.value.to_base())
            p1, p2 = idx(c.pins["1"]), idx(c.pins["2"])
            s1, s2 = idx(c.pins["3"]), idx(c.pins["4"])
            k1 = vsource_index[f"{c.ref}:1"]
            k2 = vsource_index[f"{c.ref}:2"]
            if p1 is not None:
                matrix[p1][k1] += 1
            if p2 is not None:
                matrix[p2][k1] -= 1
            if s1 is not None:
                matrix[s1][k2] += 1
            if s2 is not None:
                matrix[s2][k2] -= 1
            if s1 is not None:
                matrix[k1][s1] += 1
            if s2 is not None:
                matrix[k1][s2] -= 1
            if p1 is not None:
                matrix[k1][p1] -= n
            if p2 is not None:
                matrix[k1][p2] += n
            matrix[k2][k1] += 1
            matrix[k2][k2] += n

    return MNAProblem(
        circuit=circuit,
        ground=ground,
        nodes=nodes,
        node_index=node_index,
        vsource_refs=vsource_refs,
        vsource_index=vsource_index,
        matrix=tuple(tuple(row) for row in matrix),
        rhs=tuple(rhs),
        tx_leg_refs=tx_leg_refs,
    )
