"""Structured parser for ngspice simulation output (Phase 7-B1, 7-B2, 7-B3 & 7-B4).

Extracts DC operating point (.op), DC sweep (.dc), Transient (.tran), and
AC small-signal (.ac) tabular data into domain Signal, ComplexSignal, and
SimulationResult models. Maintains separation between solver float/complex
precision and domain Decimal precision.
"""

from __future__ import annotations

import hashlib
import re
from decimal import Decimal
from typing import TYPE_CHECKING

from academic_core.domain.engineering.simulation import ComplexSignal, Signal, SimulationResult

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


def parse_ngspice_output(
    execution: SimulationExecution,
    netlist: str = "",
    cas_store: FileBlobStore | None = None,
    analyses: tuple = ("op",),
) -> SimulationResult:
    """Parse ngspice execution output for DC, Transient, or AC analysis into a SimulationResult.

    Extracts:
    - Sweep / Time / Frequency axis Signal
    - Node voltages (real & complex)
    - Source currents (real & complex)
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

    # 2. Extract Signals from tabular sections (.op, .dc, .tran, .ac)
    signals: dict[str, Signal] = {}
    complex_signals: dict[str, ComplexSignal] = {}
    data: dict[str, str] = {}

    _parse_op_tables(stdout, signals, data)
    _parse_index_tables(stdout, signals, data)
    _parse_ac_tables(stdout, signals, complex_signals, data)

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
    if not signals and not complex_signals and status == "COMPLETED":
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
        complex_signals=complex_signals,
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


# Alias for backward compatibility with F7-B1
parse_ngspice_op = parse_ngspice_output


def _parse_op_tables(text: str, signals: dict[str, Signal], data: dict[str, str]) -> None:
    """Parse standard ngspice 'Node Voltage' and 'Source Current' tables (.op format)."""
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


def _parse_index_tables(text: str, signals: dict[str, Signal], data: dict[str, str]) -> None:
    """Parse tabular .print output for .dc sweep and .op (Index col1 col2...).

    Supports multi-point series and multi-table / paginated outputs.
    """
    lines = text.splitlines()
    columns: dict[str, list[tuple[Decimal, float]]] = {}
    active_headers: list[str] | None = None

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            active_headers = None
            continue
        if line_clean.startswith("-") or line_clean.startswith("="):
            continue
        if line_clean.startswith("\x0c") or line_clean.startswith("Note:") or line_clean.startswith("Circuit:"):
            active_headers = None
            continue

        parts = line_clean.split()
        if parts[0].lower() == "index":
            headers = [p.lower() for p in parts[1:]]
            if headers and headers[0] == "frequency":
                # AC analysis table handled by _parse_ac_tables
                active_headers = None
                continue
            active_headers = headers
            for h in active_headers:
                if h not in columns:
                    columns[h] = []
            continue

        if active_headers and parts[0].isdigit():
            val_parts = parts[1:]
            for h, val_str in zip(active_headers, val_parts):
                try:
                    dec = Decimal(val_str)
                    flt = float(val_str)
                    columns[h].append((dec, flt))
                except Exception:
                    pass

    for col_name, sample_pairs in columns.items():
        if not sample_pairs:
            continue
        samples_dec = tuple(p[0] for p in sample_pairs)
        samples_flt = tuple(p[1] for p in sample_pairs)

        # Identify axis and unit
        if col_name == "time":
            axis = "time"
            unit = "s"
        elif col_name in ("v-sweep", "i-sweep", "sweep"):
            axis = "sweep"
            unit = "V" if "v" in col_name else "A"
        elif col_name.startswith("v(") or col_name.startswith("v_"):
            axis = "voltage"
            unit = "V"
        elif col_name.startswith("i(") or col_name.endswith("#branch"):
            axis = "current"
            unit = "A"
        else:
            axis = "sweep" if ("sweep" in col_name or (len(columns) > 1 and list(columns.keys())[0] == col_name)) else "voltage"
            unit = "V" if axis in ("voltage", "sweep") else "A"

        if col_name.endswith("#branch"):
            source_name = col_name[:-7]
            sig_name = f"i({source_name})"
            sig = Signal(name=sig_name, unit="A", axis="current", samples=samples_dec, raw_samples=samples_flt)
            signals[sig_name] = sig
            signals[col_name] = sig
            val_repr = str(samples_dec[0]) if len(samples_dec) == 1 else str(samples_dec)
            data[f"I({source_name.upper()})"] = val_repr
            data[sig_name] = val_repr
            data[col_name] = val_repr
        else:
            sig = Signal(name=col_name, unit=unit, axis=axis, samples=samples_dec, raw_samples=samples_flt)
            signals[col_name] = sig
            val_repr = str(samples_dec[0]) if len(samples_dec) == 1 else str(samples_dec)
            data[col_name] = val_repr


def _parse_ac_tables(
    text: str,
    signals: dict[str, Signal],
    complex_signals: dict[str, ComplexSignal],
    data: dict[str, str],
) -> None:
    """Parse tabular AC analysis output (.print ac) from ngspice.

    Extracts:
    - frequency axis (Signal with name='frequency', unit='Hz', axis='frequency')
    - complex responses (ComplexSignal) for node voltages and branch currents
    """
    lines = text.splitlines()
    active_headers: list[str] | None = None
    freq_samples: list[tuple[Decimal, float]] = []
    complex_columns: dict[str, list[tuple[Decimal, Decimal, complex]]] = {}

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            active_headers = None
            continue
        if line_clean.startswith("-") or line_clean.startswith("="):
            continue
        if line_clean.startswith("Note:") or line_clean.startswith("Circuit:") or line_clean.startswith("Total "):
            active_headers = None
            continue
        if line_clean.startswith("\x0c"):
            active_headers = None
            continue

        parts = line_clean.split()
        if parts[0].lower() == "index":
            headers = [p.lower() for p in parts[1:]]
            if headers and headers[0] == "frequency":
                active_headers = headers
                for h in headers[1:]:
                    if h not in complex_columns:
                        complex_columns[h] = []
            else:
                active_headers = None
            continue

        if active_headers and parts[0].isdigit():
            idx = int(parts[0])
            try:
                freq_dec = Decimal(parts[1])
                freq_flt = float(parts[1])
            except Exception:
                continue

            # Record frequency once across paginated tables
            if len(freq_samples) <= idx:
                freq_samples.append((freq_dec, freq_flt))

            # Remaining tokens are pairs of (real, imag) for each variable header
            var_headers = active_headers[1:]
            val_tokens = parts[2:]
            token_idx = 0
            for var_name in var_headers:
                if token_idx >= len(val_tokens):
                    break
                re_str = val_tokens[token_idx].rstrip(",")
                token_idx += 1
                if token_idx < len(val_tokens):
                    im_str = val_tokens[token_idx].rstrip(",")
                    token_idx += 1
                else:
                    im_str = "0.0"

                try:
                    re_dec = Decimal(re_str)
                    im_dec = Decimal(im_str)
                    c_val = complex(float(re_str), float(im_str))
                    complex_columns[var_name].append((re_dec, im_dec, c_val))
                except Exception:
                    pass

    if freq_samples:
        f_dec = tuple(p[0] for p in freq_samples)
        f_flt = tuple(p[1] for p in freq_samples)
        f_sig = Signal(name="frequency", unit="Hz", axis="frequency", samples=f_dec, raw_samples=f_flt)
        signals["frequency"] = f_sig
        data["frequency"] = str(f_dec)

    for col_name, triplets in complex_columns.items():
        if not triplets:
            continue
        re_samples = tuple(t[0] for t in triplets)
        im_samples = tuple(t[1] for t in triplets)
        c_samples = tuple(t[2] for t in triplets)

        if col_name.startswith("v(") or col_name.startswith("v_"):
            axis = "voltage"
            unit = "V"
        elif col_name.startswith("i(") or col_name.endswith("#branch"):
            axis = "current"
            unit = "A"
        else:
            axis = "voltage"
            unit = "V"

        if col_name.endswith("#branch"):
            source_name = col_name[:-7]
            sig_name = f"i({source_name})"
            csig = ComplexSignal(
                name=sig_name,
                unit="A",
                axis="current",
                real_samples=re_samples,
                imag_samples=im_samples,
                raw_complex_samples=c_samples,
            )
            complex_signals[sig_name] = csig
            complex_signals[col_name] = csig
            data[f"I({source_name.upper()})"] = str(c_samples)
            data[sig_name] = str(c_samples)
            data[col_name] = str(c_samples)
        else:
            csig = ComplexSignal(
                name=col_name,
                unit=unit,
                axis=axis,
                real_samples=re_samples,
                imag_samples=im_samples,
                raw_complex_samples=c_samples,
            )
            complex_signals[col_name] = csig
            data[col_name] = str(c_samples)
