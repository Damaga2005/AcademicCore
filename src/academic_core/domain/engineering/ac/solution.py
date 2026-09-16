"""AC solution, branch reconstruction, and physical verification (F8-D3).

Branch currents/voltages are RECONSTRUCTED from the solved node phasors
plus the independent source phasors — never read back from the MNA
matrix rows:

* R/L/C between a and b: ``Vbranch = V(a) - V(b)``, ``Ibranch = Y * Vbranch``;
* V source: ``Vbranch = Vs`` (the source's own phasor, an independent
  quantity — this is what makes loop verification non-trivial),
  ``Ibranch`` = the MNA auxiliary unknown (+ -> -);
* I source: ``Vbranch = V(+) - V(-)``, ``Ibranch = -Is`` (through-element
  + -> - direction while Is is delivered into "+", the F8-B rule).

KCL is physical: for every net including ground, the branch currents
leaving the net must sum to zero. KVL is physical: around every
fundamental cycle of the branch multigraph (edge identity preserved, so
parallel branches stay distinct), the oriented branch voltages must sum
to zero — with voltage-source edges contributing their independent Vs
phasors, so a mis-stamped source constraint cannot cancel itself away.
The expected cycle count for the connected graphs D3 accepts is
E - V + 1 and is asserted in diagnostics, not assumed.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from academic_core.domain.engineering.ac.operating_point import ACOperatingPoint
from academic_core.domain.engineering.ac.problem import ACBranch
from academic_core.domain.engineering.ac.topology import cycle_basis
from academic_core.domain.engineering.math.decimal_complex import DecimalComplex
from academic_core.domain.engineering.math.rational import RationalComplex

Phasor = RationalComplex | DecimalComplex


class ACStatus(Enum):
    SOLVED = "solved"
    SINGULAR = "singular"
    INCONSISTENT = "inconsistent"
    NUMERICALLY_UNCERTAIN = "numerically_uncertain"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class NodePhasor:
    node: str
    phasor: Phasor


@dataclass(frozen=True)
class BranchCurrent:
    ref: str
    current: Phasor
    convention: str  # "pin1->pin2" (R/L/C) or "+->-" (V/I)


@dataclass(frozen=True)
class BranchVoltage:
    ref: str
    voltage: Phasor
    convention: str  # "V1-V2" (R/L/C) or "V+-V-" (V/I)


@dataclass(frozen=True)
class ACSolution:
    status: ACStatus
    operating_point: ACOperatingPoint | None
    node_voltages: tuple[NodePhasor, ...]
    branch_currents: tuple[BranchCurrent, ...]
    branch_voltages: tuple[BranchVoltage, ...]
    residual: tuple | None
    kcl_max_residual: Decimal | None
    kvl_max_residual: Decimal | None
    kvl_cycles: int
    solver_result: object | None  # LinearSolveResult; object avoids import cycle
    numeric_mode: object | None  # NumericMode
    working_precision: int | None
    provenance: dict
    diagnostics: tuple[str, ...]
    digest: str

    def voltage_of(self, node: str) -> Phasor | None:
        for nv in self.node_voltages:
            if nv.node == node:
                return nv.phasor
        return None

    def current_of(self, ref: str) -> Phasor | None:
        for bc in self.branch_currents:
            if bc.ref.upper() == ref.upper():
                return bc.current
        return None

    def to_dict(self) -> dict:
        from academic_core.domain.engineering.ac.phasors import fmt_cartesian

        def _ph(e):
            return None if e is None else fmt_cartesian(e)

        return {
            "status": self.status.value,
            "operating_point": None if self.operating_point is None
            else self.operating_point.to_dict(),
            "node_voltages": {nv.node: _ph(nv.phasor) for nv in self.node_voltages},
            "branch_currents": {bc.ref: _ph(bc.current) for bc in self.branch_currents},
            "branch_voltages": {bv.ref: _ph(bv.voltage) for bv in self.branch_voltages},
            "kcl_max_residual": None if self.kcl_max_residual is None
            else str(self.kcl_max_residual),
            "kvl_max_residual": None if self.kvl_max_residual is None
            else str(self.kvl_max_residual),
            "kvl_cycles": self.kvl_cycles,
            "numeric_mode": None if self.numeric_mode is None else self.numeric_mode.value,
            "working_precision": self.working_precision,
            "provenance": dict(self.provenance),
            "diagnostics": list(self.diagnostics),
            "digest": self.digest,
        }


def reconstruct(
    branches: tuple[ACBranch, ...],
    node_map: dict[str, Phasor],
    solution: tuple[Phasor, ...],
    vsource_index: dict[str, int],
) -> tuple[tuple[BranchCurrent, ...], tuple[BranchVoltage, ...]]:
    """Rebuild physical branch currents/voltages from solved quantities."""
    from academic_core.domain.engineering.mna.errors import CircularControlError

    currents: list[BranchCurrent] = []
    voltages: list[BranchVoltage] = []
    by_ref = {br.ref.upper(): br for br in branches}
    memo: dict[str, Phasor] = {}

    def control_current(key_upper: str, active: tuple = ()):
        # Reconstructed branch current of a control target in D3
        # orientation (reported signs: -gm·ΔV for G, -β·Ictrl for F —
        # same convention as independent I). Cycles are excluded at
        # problem build; the active set is defense in depth.
        if key_upper in memo:
            return memo[key_upper]
        if key_upper in active:
            raise CircularControlError(
                f"circular current control involving {key_upper}")
        br = by_ref[key_upper]
        if br.type in ("R", "L", "C"):
            assert br.admittance is not None
            value = br.admittance * (node_map[br.node_a] - node_map[br.node_b])
        elif br.type in ("V", "E", "H"):
            assert br.vsource_pos is not None
            value = solution[br.vsource_pos]
        elif br.type == "O":
            # Op-amp output leg (out -> ground return) reports -i_o.
            assert br.vsource_pos is not None
            value = -solution[br.vsource_pos]
        elif br.type == "I":
            assert br.source is not None
            value = -br.source
        elif br.type == "G":
            assert br.control is not None
            _, cp, cn, gm = br.control
            value = -(gm * (node_map[cp] - node_map[cn]))
        elif br.type == "F":
            assert br.control is not None
            _, ctrl, beta = br.control
            value = -(beta * control_current(ctrl.upper(), active + (key_upper,)))
        else:
            raise ValueError(f"cannot reconstruct current of {br.ref!r}")
        memo[key_upper] = value
        return value

    for br in branches:
        va = node_map[br.node_a]
        vb = node_map[br.node_b]
        if br.type in ("R", "L", "C"):
            assert br.admittance is not None
            v = va - vb
            i = br.admittance * v
            currents.append(BranchCurrent(br.ref, i, "pin1->pin2"))
            voltages.append(BranchVoltage(br.ref, v, "V1-V2"))
        elif br.type == "T":
            # Ideal-transformer winding leg ("T1:1" primary 1->2,
            # "T1:2" secondary 3->4): current straight from the aux
            # unknown, voltage from the winding nodes. Per-leg power
            # sums to exactly zero for the ideal device via D4.
            assert br.vsource_pos is not None
            v = va - vb
            i = solution[br.vsource_pos]
            currents.append(BranchCurrent(
                br.ref, i, "winding (1->2 primary, 3->4 secondary): aux"))
            voltages.append(BranchVoltage(br.ref, v, "V1-V2 (winding)"))
        elif br.type in ("V", "E", "H"):
            assert br.vsource_pos is not None
            i = solution[br.vsource_pos]
            currents.append(BranchCurrent(br.ref, i, "+->-"))
            if br.type == "V":
                assert br.source is not None
                voltages.append(BranchVoltage(br.ref, br.source, "V+-V- (source Vs)"))
            else:
                voltages.append(BranchVoltage(br.ref, va - vb, "V+-V- (dependent)"))
        elif br.type in ("G", "F"):
            v = va - vb
            i = control_current(br.ref.upper())
            currents.append(BranchCurrent(br.ref, i, "+->-"))
            voltages.append(BranchVoltage(br.ref, v, "V+-V- (dependent)"))
        elif br.type == "O":
            # Output leg (out -> ground return): voltage Vout, current -i_o.
            # Absorbed power S = 1/2·Vout·conj(-i_o) via the generic D4
            # formula — no special power path.
            assert br.vsource_pos is not None
            v = va - vb
            i = -solution[br.vsource_pos]
            currents.append(BranchCurrent(br.ref, i, "o->gnd (op-amp output leg)"))
            voltages.append(BranchVoltage(br.ref, v, "Vout (op-amp output leg)"))
        else:  # I
            assert br.source is not None
            v = va - vb
            i = -br.source
            currents.append(BranchCurrent(br.ref, i, "+->-"))
            voltages.append(BranchVoltage(br.ref, v, "V+-V-"))
    currents.sort(key=lambda e: e.ref.upper())
    voltages.sort(key=lambda e: e.ref.upper())
    return tuple(currents), tuple(voltages)


def kcl_residual(
    branches: tuple[ACBranch, ...],
    currents: tuple[BranchCurrent, ...],
    nets,
) -> tuple[Decimal, dict[str, Phasor]]:
    """Physical KCL: per-net sum of leaving branch currents; max modulus."""
    by_ref = {c.ref.upper(): c.current for c in currents}
    per_net: dict[str, Phasor] = {}
    for net in nets:
        total = None
        for br in branches:
            i = by_ref[br.ref.upper()]
            if br.node_a == net:
                total = i if total is None else total + i
            if br.node_b == net:
                total = -i if total is None else total - i
        per_net[net] = total
    worst = Decimal(0)
    for total in per_net.values():
        if total is None:
            continue
        m = total.modulus()
        mod = m if isinstance(m, Decimal) else Decimal(m)
        if mod > worst:
            worst = mod
    return worst, per_net


def kvl_residual(
    branches: tuple[ACBranch, ...],
    voltages: tuple[BranchVoltage, ...],
) -> tuple[Decimal, int]:
    """Physical KVL over the fundamental cycle basis (edge identity kept).

    Voltage-source edges contribute their independent Vs phasors, so the
    check relates source data to the solution instead of cancelling
    identically. Returns (max_modulus, cycle_count).
    """
    by_ref = {v.ref.upper(): v.voltage for v in voltages}
    edges = [(br.node_a, br.node_b) for br in branches]
    cycles = cycle_basis(edges)
    worst = Decimal(0)
    for cyc in cycles:
        total = None
        for eid, sign in cyc:
            br = branches[eid]
            v = by_ref[br.ref.upper()]
            term = v if sign > 0 else -v
            total = term if total is None else total + term
        if total is None:
            continue
        m = total.modulus()
        mod = m if isinstance(m, Decimal) else Decimal(m)
        if mod > worst:
            worst = mod
    return worst, len(cycles)
