"""Linear two-port network parameters over D5-style test measurements (F8-G).

Post-processing/observable layer only: no solver, no Circuit model, no MNA
here. Each parameter matrix is extracted from exactly the derived solves
its definition requires (open-circuit drive for Z, short-circuit drive
for Y, mixed boundary conditions for h/g/ABCD), reusing the certified
D5 machinery: ``deactivate_sources`` (independents off, E/G/H/F/O/T
kept), fresh 1 A / 0 V test sources, and the F8-D3 engine. No new
analysis mechanism exists in this module.

Conventions (frozen, tested):
  * Z/Y/h/g use port currents ENTERING both ports (D5 entering-A rule).
  * ABCD uses ``I1`` entering port 1 and ``-I2`` (leaving port 2):
    ``V1 = A·V2 - B·I2``, ``I1 = C·V2 - D·I2`` with ``I2`` entering.
  * Zero denominators follow the D5 ``_port_ratio`` rule exactly:
    nonzero/zero -> INFINITE, 0/0 -> UNDEFINED, exact-zero value ->
    ZERO. No ``Decimal("Infinity")`` anywhere.
  * A non-SOLVED derived solve degrades every entry of the requested
    matrix to UNDEFINED carrying the solver status — never a silent
    fallback, never a replaced verdict.
  * Ports must share no non-reference net (shared ground is fine):
    a shared net would carry the drive's return current into the
    other port's terminal, violating its open/short boundary
    condition. Overlapping ports raise TwoPortError explicitly.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from academic_core.domain.engineering.ac.impedance import (
    PortDefinition,
    deactivate_sources,
)
from academic_core.domain.engineering.ac.phasors import fmt_cartesian
from academic_core.domain.engineering.math.linsolve.problem import NumericMode
from academic_core.domain.engineering.units import Quantity, parse_unit

ENGINE_VERSION = "f8g-twoport/1.0"

#: Valid parameter kinds.
KINDS = ("z", "y", "h", "g", "abcd")


class TwoPortCategory(Enum):
    """Category of one matrix element.

    D5's ``ImpedanceCategory`` has no exact-zero member; two-port
    extraction needs ZERO as an explicit verdict (e.g. ideal B/C
    elements, series/shunt degeneracies), so the new observable family
    carries its own 4-valued vocabulary. Same zero/infinity semantics
    as D5, no parallel engine.
    """

    FINITE = "finite"
    ZERO = "zero"
    INFINITE = "infinite"
    UNDEFINED = "undefined"

#: Display unit per (kind, row, col), following D5 unit symbols.
_UNITS = {
    "z": (("Ω", "Ω"), ("Ω", "Ω")),
    "y": (("S", "S"), ("S", "S")),
    "h": (("Ω", "1"), ("1", "S")),
    "g": (("S", "1"), ("1", "Ω")),
    "abcd": (("1", "Ω"), ("S", "1")),
}


class TwoPortError(ValueError):
    """Misuse of the two-port layer (bad ports, bad kind, bad frequency)."""


@dataclass(frozen=True)
class TwoPortEntry:
    """One matrix element: value or honest category, never an infinity."""

    category: TwoPortCategory
    value: object | None  # native phasor when FINITE/ZERO, else None
    unit: str
    diagnostic: str

    def to_dict(self) -> dict:
        return {
            "category": self.category.value,
            "value": None if self.value is None else fmt_cartesian(self.value),
            "unit": self.unit,
            "diagnostic": self.diagnostic,
        }


@dataclass(frozen=True)
class TwoPortParameters:
    """One 2x2 parameter matrix (row-major a11/a12/a21/a22)."""

    kind: str
    frequency: str
    port1: dict
    port2: dict
    a11: TwoPortEntry
    a12: TwoPortEntry
    a21: TwoPortEntry
    a22: TwoPortEntry
    provenance: dict
    diagnostics: tuple[str, ...]
    digest: str

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "frequency": self.frequency,
            "port1": dict(self.port1),
            "port2": dict(self.port2),
            "a11": self.a11.to_dict(),
            "a12": self.a12.to_dict(),
            "a21": self.a21.to_dict(),
            "a22": self.a22.to_dict(),
            "provenance": dict(self.provenance),
            "diagnostics": list(self.diagnostics),
            "digest": self.digest,
        }


def _check_ports(circuit, port1, port2) -> None:
    for name, port in (("port1", port1), ("port2", port2)):
        if not isinstance(port, PortDefinition):
            raise TwoPortError(
                f"{name} must be a PortDefinition, got "
                f"{type(port).__name__}")
        for terminal in (port.node_a, port.node_b):
            if terminal not in set(circuit.nets):
                raise TwoPortError(
                    f"{name} terminal {terminal!r} is not a net of circuit "
                    f"{circuit.name!r}")
    # Single-test-source extraction is valid only when the ports share no
    # non-reference net: a shared net would carry the drive's return
    # current into the other port's terminal, violating its open/short
    # boundary condition (I=0 / V=0). Shared ground is fine (D5 rule:
    # port currents are read at A against the common reference).
    from academic_core.domain.engineering.ac.topology import reference_net
    try:
        ground = reference_net(set(circuit.nets))
    except Exception:
        return  # no usable ground: downstream solves fail honestly instead
    shared = ({port1.node_a, port1.node_b} & {port2.node_a, port2.node_b})
    shared.discard(ground)
    if shared:
        raise TwoPortError(
            f"ports share non-reference net(s) {sorted(shared)}: "
            f"single-source extraction cannot enforce the other port's "
            f"boundary condition; use non-overlapping ports")


def _free_ref(used: set[str], letter: str) -> str:
    k = 1
    while f"{letter}{k}" in used:
        k += 1
    return f"{letter}{k}"


def _drive_open(circuit, drive: PortDefinition, frequency,
                mode: NumericMode):
    """Derived solve with 1 A forced into the drive port, other port open.

    Returns (solution_or_None, status_value, v_drive, v_other, tag).
    Port currents by construction: 1 A entering drive, 0 A entering
    the open port.
    """
    from academic_core.domain.engineering.ac.solver import solve_ac
    from academic_core.domain.engineering.circuit import Circuit, Component

    derived = deactivate_sources(circuit)
    used = {c.ref.upper() for c in derived}
    tref = _free_ref(used, "I")
    derived.append(Component(
        tref, "I", Quantity(Decimal(1), parse_unit("A")),
        {"+": drive.node_a, "-": drive.node_b}, {},
    ))
    policy = (f"deactivation V->0V short/I->removed + test current "
              f"{tref}=1A entering {drive.node_a} (other port open)")
    fresh = Circuit(f"{circuit.name}+{tref}")
    for c in derived:
        fresh.add(c)
    res = solve_ac(fresh, frequency, mode)
    tag = f" [{policy}; test ref {tref}]"
    return res, tag


def _drive_short(circuit, drive: PortDefinition, shorted: PortDefinition,
                 frequency, mode: NumericMode):
    """Derived solve with 1 A into the drive port, 0 V across the other.

    Returns (solution_or_None, status_value, v_drive, i_short_entering,
    tag) where i_short_entering is the current entering the shorted
    port's A terminal (negation of the MNA unknown, D5 convention).
    """
    from academic_core.domain.engineering.ac.solver import solve_ac
    from academic_core.domain.engineering.circuit import Circuit, Component

    derived = deactivate_sources(circuit)
    used = {c.ref.upper() for c in derived}
    iref = _free_ref(used, "I")
    derived.append(Component(
        iref, "I", Quantity(Decimal(1), parse_unit("A")),
        {"+": drive.node_a, "-": drive.node_b}, {},
    ))
    used.add(iref.upper())
    vref = _free_ref(used, "V")
    derived.append(Component(
        vref, "V", Quantity(Decimal(0), parse_unit("V")),
        {"+": shorted.node_a, "-": shorted.node_b}, {},
    ))
    policy = (f"deactivation V->0V short/I->removed + test current "
              f"{iref}=1A entering {drive.node_a} + 0V short across "
              f"({shorted.node_a},{shorted.node_b})")
    fresh = Circuit(f"{circuit.name}+{iref}{vref}")
    for c in derived:
        fresh.add(c)
    res = solve_ac(fresh, frequency, mode)
    tag = f" [{policy}; test refs {iref},{vref}]"
    return res, tag, vref


def _port_voltage(res, port: PortDefinition):
    va = res.voltage_of(port.node_a)
    vb = res.voltage_of(port.node_b)
    assert va is not None and vb is not None
    return va - vb


def _ratio(num, den, unit: str, label: str):
    """D5 `_port_ratio` rule, shared: x/0 -> INFINITE, 0/0 -> UNDEFINED."""
    if not den.is_zero_exact():
        val = num / den
        if val.is_zero_exact():
            return TwoPortEntry(TwoPortCategory.ZERO, val, unit,
                                f"{label}: exact zero")
        return TwoPortEntry(TwoPortCategory.FINITE, val, unit, label)
    if not num.is_zero_exact():
        return TwoPortEntry(
            TwoPortCategory.INFINITE, None, unit,
            f"{label}: zero denominator at nonzero numerator "
            f"(open behavior, not a solver verdict)")
    return TwoPortEntry(
        TwoPortCategory.UNDEFINED, None, unit,
        f"{label}: 0/0 admits no ratio")


def _undefined_all(kind: str, units, status: str, detail: str):
    entries = tuple(
        TwoPortEntry(TwoPortCategory.UNDEFINED, None, units[r][c],
                     f"derived measurement solve: {status} ({detail})")
        for r in (0, 1) for c in (0, 1))
    return entries


def _assemble(kind, circuit, port1, port2, frequency, entries, conds,
              diagnostics):
    units = _UNITS[kind]
    (a11, a12, a21, a22) = entries
    freq_str = str(frequency.to_base()) if hasattr(frequency, "to_base") \
        else str(frequency)
    provenance = {
        "engine": ENGINE_VERSION,
        "version": "1.0",
        "kind": kind,
        "frequency_base_hz": freq_str,
        "port1": port1.to_dict(),
        "port2": port2.to_dict(),
        "conditions": list(conds),
        "units": [[units[r][c] for c in (0, 1)] for r in (0, 1)],
        "temporal_convention": "e^(+jwt)",
        "amplitude_convention": "peak",
    }
    digest = hashlib.sha256(json.dumps({
        "engine": ENGINE_VERSION,
        "kind": kind,
        "frequency_base_hz": freq_str,
        "port1": port1.to_dict(),
        "port2": port2.to_dict(),
        "circuit": sorted(c.ref.upper() for c in circuit.components),
        "entries": [e.to_dict() for e in entries],
        "conditions": list(conds),
    }, sort_keys=True, default=str).encode()).hexdigest()
    return TwoPortParameters(
        kind=kind, frequency=freq_str,
        port1=port1.to_dict(), port2=port2.to_dict(),
        a11=a11, a12=a12, a21=a21, a22=a22,
        provenance=provenance, diagnostics=tuple(diagnostics), digest=digest)


def _open_values(circuit, drive, other, frequency, mode):
    """Run one open-circuit drive; return (ok, res, v_drive, v_other, tag)."""
    from academic_core.domain.engineering.ac.solution import ACStatus

    res, tag = _drive_open(circuit, drive, frequency, mode)
    if res.status != ACStatus.SOLVED:
        return False, res, None, None, tag
    return True, res, _port_voltage(res, drive), _port_voltage(res, other), tag


def _short_values(circuit, drive, shorted, frequency, mode):
    """Run one short-circuit drive; return (ok, res, v_drive, i_short, tag)."""
    from academic_core.domain.engineering.ac.solution import ACStatus

    res, tag, vref = _drive_short(circuit, drive, shorted, frequency, mode)
    if res.status != ACStatus.SOLVED:
        return False, res, None, None, tag
    i_unknown = res.current_of(vref)
    assert i_unknown is not None
    return True, res, _port_voltage(res, drive), -i_unknown, tag


def _need2(cond_a_ok, cond_b_ok, status_a, status_b, tag_a, tag_b):
    if cond_a_ok and cond_b_ok:
        return True, ()
    bad = []
    if not cond_a_ok:
        bad.append(f"first condition: {status_a}{tag_a}")
    if not cond_b_ok:
        bad.append(f"second condition: {status_b}{tag_b}")
    return False, bad


def z_parameters(circuit, port1: PortDefinition, port2: PortDefinition,
                 frequency, mode: NumericMode = NumericMode.AUTO
                 ) -> TwoPortParameters:
    """Open-circuit impedance matrix: drive each port with 1 A in turn."""
    _check_ports(circuit, port1, port2)
    ok_a, res_a, v1a, v2a, tag_a = _open_values(
        circuit, port1, port2, frequency, mode)
    ok_b, res_b, v2b, v1b, tag_b = _open_values(
        circuit, port2, port1, frequency, mode)
    units = _UNITS["z"]
    diags = [f"z-matrix via open-circuit drives{tag_a}{tag_b}"]
    good, bad = _need2(ok_a, ok_b, res_a.status.value, res_b.status.value,
                       tag_a, tag_b)
    if not good:
        entries = _undefined_all("z", units, "; ".join(bad), "z-matrix")
        return _assemble("z", circuit, port1, port2, frequency, entries,
                         ("port2-open drive port1", "port1-open drive port2"),
                         diags + bad)
    # I1 = I2 = 1 A by construction; z11 = V1A, z21 = V2A, ...
    entries = (
        _ratio(v1a, _one_like(v1a), units[0][0], "z11 = V1/I1, port2 open"),
        _ratio(v1b, _one_like(v1b), units[0][1], "z12 = V1/I2, port1 open"),
        _ratio(v2a, _one_like(v2a), units[1][0], "z21 = V2/I1, port2 open"),
        _ratio(v2b, _one_like(v2b), units[1][1], "z22 = V2/I2, port1 open"),
    )
    return _assemble("z", circuit, port1, port2, frequency, entries,
                     ("port2-open drive port1", "port1-open drive port2"),
                     diags)


def y_parameters(circuit, port1: PortDefinition, port2: PortDefinition,
                 frequency, mode: NumericMode = NumericMode.AUTO
                 ) -> TwoPortParameters:
    """Short-circuit admittance matrix: drive each port with 1 A in turn."""
    _check_ports(circuit, port1, port2)
    ok_c, res_c, v1c, i2c, tag_c = _short_values(
        circuit, port1, port2, frequency, mode)
    ok_d, res_d, v2d, i1d, tag_d = _short_values(
        circuit, port2, port1, frequency, mode)
    units = _UNITS["y"]
    diags = [f"y-matrix via short-circuit drives{tag_c}{tag_d}"]
    good, bad = _need2(ok_c, ok_d, res_c.status.value, res_d.status.value,
                       tag_c, tag_d)
    if not good:
        entries = _undefined_all("y", units, "; ".join(bad), "y-matrix")
        return _assemble("y", circuit, port1, port2, frequency, entries,
                         ("port2-shorted drive port1",
                          "port1-shorted drive port2"),
                         diags + bad)
    # I1 = 1 A in cond C, I2 = 1 A in cond D by construction.
    entries = (
        _ratio(_one_like(v1c), v1c, units[0][0], "y11 = I1/V1, port2 shorted"),
        _ratio(i1d, v2d, units[0][1], "y12 = I1/V2, port1 shorted"),
        _ratio(i2c, v1c, units[1][0], "y21 = I2/V1, port2 shorted"),
        _ratio(_one_like(v2d), v2d, units[1][1], "y22 = I2/V2, port1 shorted"),
    )
    return _assemble("y", circuit, port1, port2, frequency, entries,
                     ("port2-shorted drive port1",
                      "port1-shorted drive port2"),
                     diags)


def h_parameters(circuit, port1: PortDefinition, port2: PortDefinition,
                 frequency, mode: NumericMode = NumericMode.AUTO
                 ) -> TwoPortParameters:
    """Hybrid matrix: port1-open drive port2, plus port2-shorted drive port1."""
    _check_ports(circuit, port1, port2)
    ok_b, res_b, v2b, v1b, tag_b = _open_values(
        circuit, port2, port1, frequency, mode)
    ok_c, res_c, v1c, i2c, tag_c = _short_values(
        circuit, port1, port2, frequency, mode)
    units = _UNITS["h"]
    diags = [f"h-matrix via mixed drives{tag_b}{tag_c}"]
    good, bad = _need2(ok_b, ok_c, res_b.status.value, res_c.status.value,
                       tag_b, tag_c)
    if not good:
        entries = _undefined_all("h", units, "; ".join(bad), "h-matrix")
        return _assemble("h", circuit, port1, port2, frequency, entries,
                         ("port1-open drive port2",
                          "port2-shorted drive port1"),
                         diags + bad)
    # Cond B: I1 = 0, I2 = 1 A. Cond C: I1 = 1 A, V2 = 0.
    entries = (
        _ratio(v1c, _one_like(v1c), units[0][0], "h11 = V1/I1, port2 shorted"),
        _ratio(v1b, v2b, units[0][1], "h12 = V1/V2, port1 open"),
        _ratio(i2c, _one_like(i2c), units[1][0], "h21 = I2/I1, port2 shorted"),
        _ratio(_one_like(v2b), v2b, units[1][1], "h22 = I2/V2, port1 open"),
    )
    return _assemble("h", circuit, port1, port2, frequency, entries,
                     ("port1-open drive port2",
                      "port2-shorted drive port1"),
                     diags)


def g_parameters(circuit, port1: PortDefinition, port2: PortDefinition,
                 frequency, mode: NumericMode = NumericMode.AUTO
                 ) -> TwoPortParameters:
    """Inverse-hybrid matrix: port2-open drive port1, plus port1-shorted
    drive port2."""
    _check_ports(circuit, port1, port2)
    ok_a, res_a, v1a, v2a, tag_a = _open_values(
        circuit, port1, port2, frequency, mode)
    ok_d, res_d, v2d, i1d, tag_d = _short_values(
        circuit, port2, port1, frequency, mode)
    units = _UNITS["g"]
    diags = [f"g-matrix via mixed drives{tag_a}{tag_d}"]
    good, bad = _need2(ok_a, ok_d, res_a.status.value, res_d.status.value,
                       tag_a, tag_d)
    if not good:
        entries = _undefined_all("g", units, "; ".join(bad), "g-matrix")
        return _assemble("g", circuit, port1, port2, frequency, entries,
                         ("port2-open drive port1",
                          "port1-shorted drive port2"),
                         diags + bad)
    # Cond A: I1 = 1 A, I2 = 0. Cond D: I2 = 1 A, V1 = 0.
    entries = (
        _ratio(_one_like(v1a), v1a, units[0][0], "g11 = I1/V1, port2 open"),
        _ratio(i1d, _one_like(i1d), units[0][1], "g12 = I1/I2, port1 shorted"),
        _ratio(v2a, v1a, units[1][0], "g21 = V2/V1, port2 open"),
        _ratio(v2d, _one_like(v2d), units[1][1], "g22 = V2/I2, port1 shorted"),
    )
    return _assemble("g", circuit, port1, port2, frequency, entries,
                     ("port2-open drive port1",
                      "port1-shorted drive port2"),
                     diags)


def abcd_parameters(circuit, port1: PortDefinition, port2: PortDefinition,
                    frequency, mode: NumericMode = NumericMode.AUTO
                    ) -> TwoPortParameters:
    """Cascade matrix with the standard -I2 convention: V1 = A·V2 - B·I2,
    I1 = C·V2 - D·I2, where I1/I2 both ENTER their ports. Uses the
    port2-open drive (A, C) and the port2-shorted drive (B, D)."""
    _check_ports(circuit, port1, port2)
    ok_a, res_a, v1a, v2a, tag_a = _open_values(
        circuit, port1, port2, frequency, mode)
    ok_c, res_c, v1c, i2c, tag_c = _short_values(
        circuit, port1, port2, frequency, mode)
    units = _UNITS["abcd"]
    diags = [f"abcd-matrix via open+short drives{tag_a}{tag_c}"]
    good, bad = _need2(ok_a, ok_c, res_a.status.value, res_c.status.value,
                       tag_a, tag_c)
    if not good:
        entries = _undefined_all("abcd", units, "; ".join(bad),
                                 "abcd-matrix")
        return _assemble("abcd", circuit, port1, port2, frequency, entries,
                         ("port2-open drive port1",
                          "port2-shorted drive port1"),
                         diags + bad)
    # Cond A: I2 entering = 0, so -I2 = 0: A = V1/V2, C = I1/V2 = 1/V2.
    # Cond C: V2 = 0, I2 entering measured: B = V1/(-I2_leaving)...
    # with I2 = entering: V1 = -B·I2 -> B = -V1/I2; I1 = -D·I2 -> D = -1/I2.
    entries = (
        _ratio(v1a, v2a, units[0][0], "A = V1/V2, port2 open"),
        _ratio(_neg(v1c), i2c, units[0][1], "B = -V1/I2, port2 shorted"),
        _ratio(_one_like(v2a), v2a, units[1][0], "C = I1/V2, port2 open"),
        _ratio(_neg(_one_like(i2c)), i2c, units[1][1],
               "D = -I1/I2, port2 shorted"),
    )
    return _assemble("abcd", circuit, port1, port2, frequency, entries,
                     ("port2-open drive port1",
                      "port2-shorted drive port1"),
                     diags)


def _one_like(sample):
    from academic_core.domain.engineering.math.decimal_complex import (
        DecimalComplex as _DC,
    )
    from academic_core.domain.engineering.math.rational import (
        RationalComplex as _RC,
    )
    return _DC.one() if isinstance(sample, _DC) else _RC.one()


def _neg(sample):
    return -sample


__all__ = [
    "ENGINE_VERSION",
    "KINDS",
    "TwoPortCategory",
    "TwoPortError",
    "TwoPortEntry",
    "TwoPortParameters",
    "z_parameters",
    "y_parameters",
    "h_parameters",
    "g_parameters",
    "abcd_parameters",
]
