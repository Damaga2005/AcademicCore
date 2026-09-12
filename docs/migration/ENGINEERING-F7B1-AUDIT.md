# F7-B1 Audit — Simulation Result + Signal + DC Operating Point

Date: 2026-09-12 · Base: F7-A `c8f513f`

## Overview & Scope
F7-B1 implements the first scientific block of Phase 7:
- Simulation data models (`Signal`, `SimulationResult`, `SimulationJob`)
- Structured parser for ngspice DC operating point (`.op`) output
- Precision separation: solver IEEE 754 float (`raw_samples`) vs domain `Decimal` (`samples`)
- Execution pipeline integration: `Circuit → Netlist → SimulationJob → NgSpiceBackend → Output Parser → SimulationResult`
- Real scientific simulation and validation against ngspice 47 (`ngspice_con.exe`)
- Persistence reference to raw simulation output in CAS (`FileBlobStore`)

## Scientific Models
- `Signal`:
  - `name`: e.g. `"v(out)"`, `"i(v1)"`
  - `unit`: e.g. `"V"`, `"A"`
  - `axis`: e.g. `"voltage"`, `"current"`
  - `samples`: `tuple[Decimal, ...]` for exact domain arithmetic
  - `raw_samples`: `tuple[float, ...]` directly from solver
  - Properties: `value` (`Decimal`), `raw_value` (`float`) for point operating analyses
- `SimulationResult`:
  - Backward-compatible with F6 mock/data dictionary (`data: dict`)
  - `signals: dict[str, Signal]`
  - `status`: `"COMPLETED" | "FAILED" | "TIMEOUT" | "CANCELLED"`
  - `exit_code: int | None`
  - `duration_seconds: float`
  - `raw_artifact_hash: str` (SHA-256 CAS content hash)
  - `raw_stdout: str`, `raw_stderr: str`
  - `provenance: dict` (backend metadata, version, executable, timestamp, input hash)
  - `errors: tuple[str, ...]`
  - Helper methods: `get_signal(name)`, `voltage(node)`, `current(source)` (case-insensitive)
- `SimulationJob`:
  - Connects `Circuit` / netlist to execution request
  - `build_netlist()` safely injects analysis directive (e.g. `.op`) before `.end` without duplicating existing cards

## Structured Output Parser
- Module: `academic_core.infrastructure.ngspice_parser` (`parse_ngspice_op`)
- Non-fragile table parsing for:
  - Node Voltages (`Node ... Voltage` section)
  - Source Currents (`Source ... Current` section)
  - `.print op` Index table format
- Error detection: parses explicit `Error:` and `Fatal error:` diagnostics from ngspice output
- CAS integration: stores full raw output bytes in `FileBlobStore` and records `raw_artifact_hash`
- Determinism: verified identical outputs across repeated parsing passes

## Real Scientific Validation
Executed directly using ngspice 47 (`ngspice_con.exe`):

1. **Resistive Voltage Divider**:
   - Circuit: $V_1 = 10\text{ V}$, $R_1 = 1\text{ k}\Omega$, $R_2 = 1\text{ k}\Omega$
   - Expected: $V(\text{in}) = 10.0\text{ V}$, $V(\text{out}) = 5.0\text{ V}$, $I(V_1) = -5.0\text{ mA}$
   - Real Simulation Result:
     - $V(\text{in}) = 10.000000\text{ V}$ (`Decimal('10.000000')`)
     - $V(\text{out}) = 5.000000\text{ V}$ (`Decimal('5.000000')`)
     - $I(V_1) = -0.0050000\text{ A}$ (`Decimal('-0.0050000')`)
     - Status: `COMPLETED`, exit code: `0`

2. **Ohm's Law Single Resistor**:
   - Circuit: $V_1 = 5\text{ V}$, $R_1 = 2.5\text{ k}\Omega$
   - Expected: $V(\text{in}) = 5.0\text{ V}$, $I(V_1) = -2.0\text{ mA}$
   - Real Simulation Result:
     - $V(\text{in}) = 5.000000\text{ V}$
     - $I(V_1) = -0.0020000\text{ A}$
     - Status: `COMPLETED`, exit code: `0`

3. **Full Pipeline via EngineeringService**:
   - `Circuit → Netlist → SimulationJob → NgSpiceBackend → Output Parser → SimulationResult`
   - Circuit: $V_1 = 12\text{ V}$, $R_1 = 3\text{ k}\Omega$, $R_2 = 1\text{ k}\Omega$
   - Real Simulation Result:
     - $V(\text{in}) = 12.000000\text{ V}$
     - $V(\text{mid}) = 3.000000\text{ V}$
     - $I(V_1) = -0.0030000\text{ A}$
     - Status: `COMPLETED`, exit code: `0`

## Limitations & Demarcation
- **DC Operating Point Only**: Only `.op` analysis is supported in F7-B1.
- **Out of Scope (F7-B2+)**:
  - DC sweep (`.dc`)
  - Transient analysis (`.tran`)
  - AC small-signal analysis (`.ac`)
  - Noise analysis (`.noise`)
  - Monte Carlo analysis
  - GUM uncertainty evaluation
  - Hardware I/O / SCPI
  - Custom MNA solver
  - Advanced plotting UI / waveform viewer

## Test & Regression Summary
- F7-B1 tests (`tests/test_f7b1_simulation.py`): `12 passed`
  - Model precision and accessors
  - Case-insensitivity and signal helper accessors
  - SimulationJob deck builder
  - Valid parser extraction (voltages and currents)
  - Parser error diagnostic handling
  - Malformed/empty output resilience
  - Parser determinism
  - CAS blob raw persistence
  - Real DC operating point voltage divider
  - Real DC operating point single resistor
  - Full pipeline service integration
  - Mock backend compatibility
- F7-A tests (`tests/test_f7a_runtime.py`): `16 passed`
- Full regression suite (F0–F6 + F7-A + F7-B1): `233 passed, 2 skipped` (reportlab, stirling bootstrap)

---

F7-B1 STATUS: PASS
