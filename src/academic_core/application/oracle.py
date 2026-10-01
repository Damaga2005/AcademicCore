# SPDX-License-Identifier: MIT
"""ngspice as an independent oracle for operating-point results.

The exact MNA engine is the authority; ngspice is a second, unrelated implementation. This module
writes a SPICE netlist for a circuit, runs ``.op`` in ngspice and compares node voltages. It never
replaces or adjusts a result: it reports ``match``, ``differs``, ``unavailable`` or ``unsupported``
(with the reason) and the largest difference it saw. No Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from academic_core.domain.engineering.circuit import Circuit

# Element types this exporter writes faithfully. Others (M, J, O, T) are reported as unsupported
# rather than approximated, so a "match" always means a like-for-like comparison.
SUPPORTED = frozenset("RCLVIEGHFDQ")
ABS_TOL = Decimal("1E-4")          # volts
REL_TOL_LINEAR = Decimal("1E-4")
REL_TOL_SEMI = Decimal("2E-3")     # ngspice models carry small extras (gmin, temperature rounding)
_K_OVER_Q = Decimal("8.617333262E-5")  # eV/K: Vt = (k/q) * T


@dataclass(frozen=True)
class OracleView:
    status: str          # match | differs | unavailable | unsupported | error
    detail: str = ""
    version: str = ""
    nodes: int = 0
    max_abs_diff: str = ""   # volts, as written by the comparison


def _num(q) -> str:
    return format(q.to_base(), "f") if isinstance(q.to_base(), Decimal) else str(q.to_base())


def to_spice(circuit: Circuit, dc_overrides: dict | None = None):
    """``(netlist, semiconductor?)`` or ``(None, reason)`` when a component has no faithful SPICE form."""
    bad = sorted({c.type.upper() for c in circuit.components if c.type.upper() not in SUPPORTED})
    if bad:
        return None, f"componentes sin equivalente fiel en SPICE: {', '.join(bad)}"
    overrides = dc_overrides or {}
    lines, models, temps = [f"* {circuit.name}"], [], set()
    for c in sorted(circuit.components, key=lambda c: c.ref.upper()):
        t, ref, p = c.type.upper(), c.ref.upper(), c.pins
        value = overrides.get(ref, c.value)
        params = c.parameters or {}
        if t in "RCLVI":
            dc = "DC " if t in "VI" else ""
            lines.append(f"{ref} {p['1' if t in 'RCL' else '+']} {p['2' if t in 'RCL' else '-']} {dc}{_num(value)}")
        elif t in "EG":
            lines.append(f"{ref} {p['+']} {p['-']} {params['cp']} {params['cn']} {_num(value)}")
        elif t in "HF":
            lines.append(f"{ref} {p['+']} {p['-']} {str(params['control_ref']).upper()} {_num(value)}")
        elif t == "D":
            temps.add(params["Vt"].to_base())
            models.append(f".model DM_{ref} D(IS={_num(params['Is'])} N={_num(params['n'])})")
            lines.append(f"{ref} {p['A']} {p['K']} DM_{ref}")
        elif t == "Q":
            temps.add(params["Vt"].to_base())
            pol = str(params["polarity"]).upper()
            models.append(f".model QM_{ref} {pol}(IS={_num(params['Is'])} BF={_num(params['Bf'])} "
                          f"BR={_num(params['Br'])} NF={_num(params['Nf'])} NR={_num(params['Nr'])})")
            lines.append(f"{ref} {p['C']} {p['B']} {p['E']} QM_{ref}")
    if len(temps) > 1:
        return None, "los semiconductores usan tensiones térmicas Vt distintas"
    if temps:  # make ngspice's thermal voltage equal the circuit's Vt
        celsius = next(iter(temps)) / _K_OVER_Q - Decimal("273.15")
        lines.append(f".options temp={celsius:.4f} tnom={celsius:.4f}")
    lines += models + [".op", ".end"]
    return "\n".join(lines) + "\n", bool(temps)


def compare_op(circuit: Circuit, node_voltages, backend, dc_overrides: dict | None = None) -> OracleView:
    """Compare the engine's node voltages (``NodeVoltage`` items) against ngspice's ``.op``."""
    netlist, info = to_spice(circuit, dc_overrides)
    if netlist is None:
        return OracleView("unsupported", info)
    runtime = backend.detect()
    if not getattr(runtime, "available", False):
        return OracleView("unavailable", "ngspice no está instalado o no se encuentra")
    version = getattr(runtime, "version", "") or ""
    try:
        result = backend.simulate(netlist, analyses=("op",))
    except Exception as exc:  # the oracle must never break a run
        return OracleView("error", f"ngspice falló: {type(exc).__name__}", version)
    if result.status != "COMPLETED":
        return OracleView("error", f"ngspice terminó con estado {result.status}", version)
    signals = {name.lower(): sig.samples[0] for name, sig in result.signals.items() if sig.samples}
    rel = REL_TOL_SEMI if info else REL_TOL_LINEAR
    worst, compared, differs = Decimal(0), 0, []
    for nv in node_voltages:
        node = str(nv.node)
        if node in ("0", "GND"):
            continue
        ref = signals.get(f"v({node.lower()})")
        if ref is None:
            continue
        ours = nv.voltage.to_base()
        diff = abs(Decimal(ours) - Decimal(ref))
        compared += 1
        worst = max(worst, diff)
        if diff > ABS_TOL + rel * abs(Decimal(ours)):
            differs.append(node)
    if compared == 0:
        return OracleView("error", "ngspice no devolvió tensiones de nodo comparables", version)
    status = "differs" if differs else "match"
    detail = (f"difieren en: {', '.join(differs)}" if differs
              else f"{compared} nodos dentro de la tolerancia")
    return OracleView(status, detail, version, compared, format(worst, ".3E") if worst else "0")
