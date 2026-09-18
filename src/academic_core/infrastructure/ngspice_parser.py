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

from academic_core.domain.engineering.simulation import (
    ComplexSignal,
    NoiseAnalysis,
    NoiseResult,
    SensitivityAnalysis,
    SensitivityResult,
    Signal,
    SimulationResult,
)

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
# Looser "this line looks like a name + numeric-ish value" shape, used only
# to detect candidate data rows that _TABLE_ROW_RE / Decimal() failed to
# parse (e.g. engineering-suffix notation like "1.234u" instead of
# "1.234e-06"). Never used to extract values, only to flag that something
# worth reporting was silently skipped.
_CANDIDATE_ROW_RE = re.compile(
    r"^\s*([a-zA-Z0-9_#\+\-\.]+)\s+([+-]?[0-9][^\s]*)\s*$"
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

    # 2. Extract Signals from tabular sections (.op, .dc, .tran, .ac, .noise, .sens)
    signals: dict[str, Signal] = {}
    complex_signals: dict[str, ComplexSignal] = {}
    data: dict[str, str] = {}
    # Non-fatal parse diagnostics: lines/values that looked like they were
    # meant to carry data (matched a recognized section/table header) but
    # could not be turned into a Signal/ComplexSignal (e.g. an unsupported
    # engineering-suffix number format such as "1.234u"). Used below to
    # distinguish "genuinely nothing to report" from "something was skipped".
    diagnostics: list[str] = []

    _parse_op_tables(stdout, signals, data, diagnostics)
    _parse_index_tables(stdout, signals, data, diagnostics)
    _parse_ac_tables(stdout, signals, complex_signals, data, diagnostics)
    noise_info = _parse_noise_tables(stdout, signals, data, diagnostics)
    sens_info = _parse_sens_tables(stdout, signals, complex_signals, data, diagnostics)

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

    have_any_signal = bool(signals) or bool(complex_signals) or bool(sens_info.get("sensitivities"))

    # If no signals extracted and execution was clean, but no circuit loaded or empty
    if not have_any_signal and status == "COMPLETED":
        if "no simulations run" in combined.lower() or "no circuits loaded" in combined.lower():
            status = "FAILED"
            if not errors_found:
                errors_found.append("no simulations run")
        elif diagnostics:
            # We saw recognized section/table headers and candidate data
            # rows, but extracted zero signals from them -- this is a parse
            # failure (e.g. unsupported engineering-suffix number format),
            # not a legitimately empty result, so it must not be reported as
            # a silent COMPLETED success.
            status = "FAILED"
            errors_found.append(
                "ngspice output parser found candidate data rows but "
                "extracted zero signals (possible unsupported number "
                "format, e.g. engineering-suffix notation like '1.234u' "
                "instead of '1.234e-06'): " + "; ".join(diagnostics[:5])
            )
    elif have_any_signal and diagnostics and status == "COMPLETED":
        # Some candidate rows in a recognized table parsed fine and others
        # in that SAME table were silently skipped (e.g. one row used an
        # unsupported engineering-suffix number format like "1.234u" while
        # sibling rows parsed normally). Signals are kept -- callers do not
        # lose the values that DID parse -- but this must never be reported
        # as a clean, unqualified COMPLETED, since it would hide a partial
        # data loss the caller has no other way to detect.
        status = "PARTIAL"
        errors_found.append(
            "ngspice output parser dropped some candidate data rows while "
            "other rows in the same table(s) parsed successfully (possible "
            "unsupported number format, e.g. engineering-suffix notation "
            "like '1.234u' instead of '1.234e-06'); signals reflect only "
            "what parsed: " + "; ".join(diagnostics[:5])
        )

    is_noise_analysis = any(
        isinstance(a, NoiseAnalysis) or (isinstance(a, str) and a.strip().lower().startswith("noise"))
        for a in analyses
    ) or noise_info.get("is_noise", False)

    is_sens_analysis = any(
        isinstance(a, SensitivityAnalysis) or (isinstance(a, str) and a.strip().lower().startswith("sens"))
        for a in analyses
    ) or sens_info.get("is_sens", False)

    if is_noise_analysis:
        return NoiseResult(
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
            onoise_total_val=noise_info.get("onoise_total"),
            inoise_total_val=noise_info.get("inoise_total"),
        )

    if is_sens_analysis:
        out_var = ""
        for a in analyses:
            if isinstance(a, SensitivityAnalysis):
                out_var = a.output_variable
                break
        return SensitivityResult(
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
            sensitivities_map=sens_info.get("sensitivities", {}),
            output_variable=out_var,
        )

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


def _parse_op_tables(
    text: str,
    signals: dict[str, Signal],
    data: dict[str, str],
    diagnostics: list[str] | None = None,
) -> None:
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
                    if diagnostics is not None:
                        diagnostics.append(f"unparsed {section} row: {lc!r}")
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
            elif diagnostics is not None and _CANDIDATE_ROW_RE.match(lc):
                # Shaped like "<name> <value>" inside a recognized
                # Node Voltage / Source Current section, but the value
                # didn't match the strict numeric grammar (e.g. an
                # engineering suffix like "1.23u").
                diagnostics.append(f"unparsed {section} row: {lc!r}")


def _parse_index_tables(
    text: str,
    signals: dict[str, Signal],
    data: dict[str, str],
    diagnostics: list[str] | None = None,
) -> None:
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
        if line_clean.startswith("\x0c") or line_clean.startswith("Note:") or line_clean.startswith("Circuit:") or "integrated noise" in line_clean.lower() or "noise spectral density" in line_clean.lower() or "sensitivity analysis" in line_clean.lower():
            active_headers = None
            continue

        parts = line_clean.split()
        if parts[0].lower() == "index":
            headers = [p.lower() for p in parts[1:]]
            if headers and (headers[0] == "frequency" or any("noise" in h for h in headers)):
                # AC analysis or Noise analysis table handled by specialized parsers
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
                    if diagnostics is not None:
                        diagnostics.append(
                            f"unparsed value for column {h!r}: {val_str!r}"
                        )

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
    diagnostics: list[str] | None = None,
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
        if line_clean.startswith("Note:") or line_clean.startswith("Circuit:") or line_clean.startswith("Total ") or "noise spectral density" in line_clean.lower() or "integrated noise" in line_clean.lower() or "sensitivity analysis" in line_clean.lower():
            active_headers = None
            continue
        if line_clean.startswith("\x0c"):
            active_headers = None
            continue

        parts = line_clean.split()
        if parts[0].lower() == "index":
            headers = [p.lower() for p in parts[1:]]
            if headers and headers[0] == "frequency" and not any("noise" in h for h in headers):
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
                if diagnostics is not None:
                    diagnostics.append(f"unparsed AC frequency value: {parts[1]!r}")
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
                    if diagnostics is not None:
                        diagnostics.append(
                            f"unparsed AC value for {var_name!r}: "
                            f"{re_str!r}/{im_str!r}"
                        )

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


def _parse_noise_tables(
    text: str,
    signals: dict[str, Signal],
    data: dict[str, str],
    diagnostics: list[str] | None = None,
) -> dict:
    """Parse ngspice .noise output tables (Integrated Noise and Noise Spectral Density Curves)."""
    lines = text.splitlines()
    result_info: dict = {"is_noise": False, "onoise_total": None, "inoise_total": None}

    # 1. Parse Integrated Noise table
    in_integrated = False
    int_headers: list[str] = []
    for line in lines:
        line_clean = line.strip()
        if "integrated noise" in line_clean.lower():
            in_integrated = True
            int_headers = []
            continue
        if in_integrated:
            if line_clean.startswith("-") or line_clean.startswith("="):
                continue
            if not line_clean or line_clean.startswith("\x0c") or "noise spectral density" in line_clean.lower():
                in_integrated = False
                continue
            parts = line_clean.split()
            if parts and parts[0].lower() == "index":
                int_headers = [p.lower() for p in parts[1:]]
                continue
            if parts and parts[0].isdigit() and int_headers:
                result_info["is_noise"] = True
                val_parts = parts[1:]
                for h, v_str in zip(int_headers, val_parts):
                    try:
                        v_dec = Decimal(v_str)
                        data[h] = str(v_dec)
                        if "onoise" in h:
                            result_info["onoise_total"] = v_dec
                        elif "inoise" in h:
                            result_info["inoise_total"] = v_dec
                    except Exception:
                        if diagnostics is not None:
                            diagnostics.append(
                                f"unparsed integrated noise value for {h!r}: {v_str!r}"
                            )
                in_integrated = False

    # 2. Parse Noise Spectral Density Curves table
    in_density = False
    density_headers: list[str] = []
    density_columns: dict[str, list[tuple[Decimal, float]]] = {}
    for line in lines:
        line_clean = line.strip()
        if "noise spectral density" in line_clean.lower():
            in_density = True
            density_headers = []
            continue
        if in_density:
            if line_clean.startswith("-") or line_clean.startswith("="):
                continue
            if line_clean.startswith("\x0c") or line_clean.startswith("Note:") or line_clean.startswith("Circuit:"):
                in_density = False
                continue
            if not line_clean:
                continue
            parts = line_clean.split()
            if parts and parts[0].lower() == "index":
                density_headers = [p.lower() for p in parts[1:]]
                for h in density_headers:
                    if h not in density_columns:
                        density_columns[h] = []
                continue
            if parts and parts[0].isdigit() and density_headers:
                result_info["is_noise"] = True
                val_parts = parts[1:]
                for h, v_str in zip(density_headers, val_parts):
                    try:
                        dec = Decimal(v_str)
                        flt = float(v_str)
                        density_columns[h].append((dec, flt))
                    except Exception:
                        if diagnostics is not None:
                            diagnostics.append(
                                f"unparsed noise density value for {h!r}: {v_str!r}"
                            )

    for col_name, sample_pairs in density_columns.items():
        if not sample_pairs:
            continue
        samples_dec = tuple(p[0] for p in sample_pairs)
        samples_flt = tuple(p[1] for p in sample_pairs)

        if col_name == "frequency":
            sig = Signal("frequency", "Hz", "frequency", samples_dec, samples_flt)
            signals["frequency"] = sig
            data["frequency"] = str(samples_dec)
        elif "onoise" in col_name:
            sig = Signal("onoise_spectrum", "V/sqrt(Hz)", "noise_density", samples_dec, samples_flt)
            signals["onoise_spectrum"] = sig
            signals["onoise"] = sig
            data["onoise_spectrum"] = str(samples_dec)
        elif "inoise" in col_name:
            sig = Signal("inoise_spectrum", "V/sqrt(Hz)", "noise_density", samples_dec, samples_flt)
            signals["inoise_spectrum"] = sig
            signals["inoise"] = sig
            data["inoise_spectrum"] = str(samples_dec)
        else:
            sig = Signal(col_name, "V/sqrt(Hz)", "noise_density", samples_dec, samples_flt)
            signals[col_name] = sig

    return result_info


def _parse_sens_tables(
    text: str,
    signals: dict[str, Signal],
    complex_signals: dict[str, ComplexSignal],
    data: dict[str, str],
    diagnostics: list[str] | None = None,
) -> dict:
    """Parse ngspice .sens output tables (DC scalar sensitivity and AC complex sensitivity)."""
    lines = text.splitlines()
    result_info: dict = {"is_sens": False, "sensitivities": {}}
    sens_map: dict[str, Decimal | ComplexSignal] = {}

    in_sens = False
    active_headers: list[str] | None = None
    is_ac_sens = False
    freq_samples: list[tuple[Decimal, float]] = []
    ac_columns: dict[str, list[tuple[Decimal, Decimal, complex]]] = {}

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue
        if "sensitivity analysis" in line_clean.lower():
            in_sens = True
            active_headers = None
            continue
        if not in_sens:
            continue

        if line_clean.startswith("-") or line_clean.startswith("="):
            continue
        if line_clean.startswith("Note:") or line_clean.startswith("Circuit:") or line_clean.startswith("Total "):
            in_sens = False
            active_headers = None
            continue
        if line_clean.startswith("\x0c"):
            # New page in paginated sens table
            active_headers = None
            continue

        parts = line_clean.split()
        if parts and parts[0].lower() == "index":
            active_headers = [p.lower() for p in parts[1:]]
            if active_headers and active_headers[0] == "frequency":
                is_ac_sens = True
                result_info["is_sens"] = True
                for h in active_headers[1:]:
                    if h not in ac_columns:
                        ac_columns[h] = []
            else:
                is_ac_sens = False
                result_info["is_sens"] = True
            continue

        if active_headers and parts and parts[0].isdigit():
            result_info["is_sens"] = True
            if is_ac_sens:
                idx = int(parts[0])
                try:
                    freq_dec = Decimal(parts[1])
                    freq_flt = float(parts[1])
                except Exception:
                    if diagnostics is not None:
                        diagnostics.append(f"unparsed sens frequency value: {parts[1]!r}")
                    continue
                if len(freq_samples) <= idx:
                    freq_samples.append((freq_dec, freq_flt))

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
                        ac_columns[var_name].append((re_dec, im_dec, c_val))
                    except Exception:
                        if diagnostics is not None:
                            diagnostics.append(
                                f"unparsed sens AC value for {var_name!r}: "
                                f"{re_str!r}/{im_str!r}"
                            )
            else:
                # DC scalar sensitivity row (row 0)
                val_parts = parts[1:]
                for h, val_str in zip(active_headers, val_parts):
                    try:
                        dec = Decimal(val_str)
                        flt = float(val_str)
                        sens_map[h] = dec
                        data[h] = str(dec)
                        # Also provide Signal accessor
                        signals[h] = Signal(h, "sensitivity", "sensitivity", (dec,), (flt,))
                    except Exception:
                        if diagnostics is not None:
                            diagnostics.append(
                                f"unparsed sens value for {h!r}: {val_str!r}"
                            )

    if is_ac_sens and freq_samples:
        f_dec = tuple(p[0] for p in freq_samples)
        f_flt = tuple(p[1] for p in freq_samples)
        signals["frequency"] = Signal("frequency", "Hz", "frequency", f_dec, f_flt)
        data["frequency"] = str(f_dec)

        for var_name, samples_list in ac_columns.items():
            if not samples_list:
                continue
            re_tuple = tuple(s[0] for s in samples_list)
            im_tuple = tuple(s[1] for s in samples_list)
            c_tuple = tuple(s[2] for s in samples_list)
            csig = ComplexSignal(var_name, "sensitivity", "sensitivity", re_tuple, im_tuple, c_tuple)
            complex_signals[var_name] = csig
            sens_map[var_name] = csig

    result_info["sensitivities"] = sens_map
    return result_info
