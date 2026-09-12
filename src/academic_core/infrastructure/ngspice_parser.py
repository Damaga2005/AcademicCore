"""Structured parser for ngspice simulation output (Phase 7-B1).

Extracts DC operating point (.op) node voltages and source currents into
domain Signal and SimulationResult models. Maintains separation between
solver float precision and domain Decimal precision.
"""

from __future__ import annotations

import hashlib
import re
from decimal import Decimal
from typing import TYPE_CHECKING

from academic_core.domain.engineering.simulation import Signal, SimulationResult

if TYPE_CHECKING:
    from academic_core.infrastructure.cas import FileBlobStore
    from academic_core.infrastructure.ngspice import SimulationExecution

_NUM_RE = r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
_TABLE_ROW_RE = re.compile(
    rf"^\s*([a-zA-Z0-9_#\+\-\.]+)\s+({_NUM_RE})\s*$"
)
_ERROR_RE = re.compile(
    r"^(?:Error|Fatal error):\s*(.+)$",
    re.I | re.MULTILINE
)


def parse_ngspice_op(
    execution: SimulationExecution,
    netlist: str = "",
    cas_store: FileBlobStore | None = None,
    analyses: tuple = ("op",),
) -> SimulationResult:
    """Parse ngspice execution output for DC operating point analysis into a SimulationResult.

    Extracts:
    - Node voltages (Unit 'V', Axis 'voltage')
    - Source currents (Unit 'A', Axis 'current')
    - Errors and diagnostic messages
    - Execution metadata and CAS reference
    """
    stdout = execution.stdout or ""
    stderr = execution.stderr or ""
    combined = stdout + "\n" + stderr

    # 1. Error detection
    errors_found = [m.strip() for m in _ERROR_RE.findall(combined)]
    status = execution.status
    if errors_found and status == "COMPLETED":
        status = "FAILED"
    elif execution.exit_code not in (0, None) and status == "COMPLETED":
        status = "FAILED"

    # 2. Extract Signals from tabular sections
    signals: dict[str, Signal] = {}
    data: dict[str, str] = {}

    _parse_op_tables(stdout, signals, data)
    _parse_index_table(stdout, signals, data)

    # 3. Digest and CAS raw artifact reference
    netlist_text = netlist or execution.input_hash
    netlist_digest = hashlib.sha256(netlist_text.encode("ascii", errors="replace")).hexdigest()

    raw_artifact_hash = ""
    raw_payload = stdout.encode("utf-8") + b"\n--- STDERR ---\n" + stderr.encode("utf-8")
    if cas_store is not None:
        try:
            raw_artifact_hash = cas_store.put_bytes(raw_payload)
        except Exception:
            raw_artifact_hash = hashlib.sha256(raw_payload).hexdigest()
    elif stdout:
        raw_artifact_hash = hashlib.sha256(raw_payload).hexdigest()

    # 4. Provenance
    provenance = {
        "backend_id": execution.backend_id,
        "backend_version": execution.backend_version,
        "executable_path": execution.executable_path,
        "started_at": execution.started_at,
        "finished_at": execution.finished_at,
        "duration_seconds": execution.duration_seconds,
        "exit_code": execution.exit_code,
        "input_hash": execution.input_hash,
        "command_metadata": execution.command_metadata,
        "timeout_seconds": execution.timeout_seconds,
        "cancelled": execution.cancelled,
    }

    # If no signals extracted and execution was clean, but no circuit loaded or empty
    if not signals and status == "COMPLETED":
        if "no simulations run" in combined.lower() or "no circuits loaded" in combined.lower():
            status = "FAILED"
            if not errors_found:
                errors_found.append("no simulations run")

    return SimulationResult(
        backend=execution.backend_id,
        netlist_digest=netlist_digest,
        analyses=tuple(analyses),
        data=data,
        mocked=False,
        signals=signals,
        status=status,
        exit_code=execution.exit_code,
        duration_seconds=execution.duration_seconds,
        started_at=execution.started_at,
        finished_at=execution.finished_at,
        raw_artifact_hash=raw_artifact_hash,
        raw_stdout=stdout,
        raw_stderr=stderr,
        provenance=provenance,
        errors=tuple(errors_found),
    )


def _parse_op_tables(text: str, signals: dict[str, Signal], data: dict[str, str]) -> None:
    """Parse standard ngspice 'Node Voltage' and 'Source Current' tables."""
    section: str | None = None
    for line in text.splitlines():
        lc = line.strip()
        if not lc:
            continue

        if re.search(r"\bNode\b.*\bVoltage\b", lc, re.I):
            section = "voltage"
            continue
        elif re.search(r"\bSource\b.*\bCurrent\b", lc, re.I):
            section = "current"
            continue
        elif lc.startswith("---") or lc.startswith("==="):
            continue
        elif any(lc.startswith(w) for w in (
            "Resistor", "Vsource", "Isource", "Capacitor", "Inductor",
            "Diode", "BJT", "MOS", "Total analysis", "Doing analysis",
            "No. of Data", "Circuit:", "Note:"
        )):
            section = None
            continue

        if section:
            m = _TABLE_ROW_RE.match(lc)
            if m:
                raw_name = m.group(1).strip().lower()
                val_str = m.group(2).strip()
                try:
                    dec = Decimal(val_str)
                    flt = float(val_str)
                except Exception:
                    continue

                if section == "voltage":
                    sig_name = f"v({raw_name})"
                    sig = Signal(
                        name=sig_name,
                        unit="V",
                        axis="voltage",
                        samples=(dec,),
                        raw_samples=(flt,),
                    )
                    signals[sig_name] = sig
                    data[f"V({raw_name.upper()})"] = val_str
                    data[sig_name] = str(dec)
                elif section == "current":
                    # Normalize source name (e.g. v1#branch -> i(v1))
                    source_name = raw_name[:-7] if raw_name.endswith("#branch") else raw_name
                    sig_name = f"i({source_name})"
                    sig = Signal(
                        name=sig_name,
                        unit="A",
                        axis="current",
                        samples=(dec,),
                        raw_samples=(flt,),
                    )
                    signals[sig_name] = sig
                    if raw_name != sig_name:
                        signals[raw_name] = sig
                    data[f"I({source_name.upper()})"] = val_str
                    data[sig_name] = str(dec)
                    data[raw_name] = str(dec)


def _parse_index_table(text: str, signals: dict[str, Signal], data: dict[str, str]) -> None:
    """Parse .print op tabular output (Index col1 col2...)."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        line_strip = line.strip()
        if line_strip.startswith("Index") and len(line_strip.split()) > 1:
            headers = line_strip.split()[1:]
            for j in range(i + 1, min(i + 6, len(lines))):
                row = lines[j].strip()
                if not row or row.startswith("-"):
                    continue
                parts = row.split()
                if len(parts) >= len(headers) + 1 and parts[0].isdigit():
                    values = parts[1 : len(headers) + 1]
                    for h, val_str in zip(headers, values):
                        h_clean = h.strip().lower()
                        unit = "V" if h_clean.startswith("v") else ("A" if h_clean.startswith("i") or "#branch" in h_clean else "")
                        axis = "voltage" if unit == "V" else ("current" if unit == "A" else "signal")
                        try:
                            dec = Decimal(val_str)
                            flt = float(val_str)
                            if h_clean not in signals:
                                signals[h_clean] = Signal(
                                    name=h_clean,
                                    unit=unit,
                                    axis=axis,
                                    samples=(dec,),
                                    raw_samples=(flt,),
                                )
                                data[h_clean] = str(dec)
                        except Exception:
                            pass
                    break
