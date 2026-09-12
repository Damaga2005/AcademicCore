# F7-B2 Audit — DC Sweep Real con ngspice

Date: 2026-09-12 · Base: F7-B1 `2f3efac`

## Overview & Scope
F7-B2 adds DC Sweep analysis to the simulation pipeline certified in F7-B1:
- `DCSweepAnalysis` domain specification with parameter validation (source, start, stop, step, non-zero step, sign consistency).
- Deterministic SPICE deck generation for `.dc` and automated `.print dc` cards.
- Structured multi-point tabular parser for ngspice `DC transfer characteristic` tables.
- Representation of sweep axis as `Signal` (`axis="sweep"`).
- Multi-point sequence support in `Signal` (`samples: tuple[Decimal, ...]`, `raw_samples: tuple[float, ...]`).
- Real scientific simulation and validation against ngspice 47 (`ngspice_con.exe`).
- Raw artifact reference in CAS (`FileBlobStore`) and provenance metadata.

## Parameter Validation
- Enforced in `DCSweepAnalysis.__post_init__`:
  - Source identifier must be non-empty string.
  - Start, stop, and step must be valid numerical values converted to domain `Decimal`.
  - Step size cannot be zero (`step == 0` raises `ValueError`).
  - Range direction and step sign must match (`start < stop` requires `step > 0`; `start > stop` requires `step < 0`).
  - Expected points count: calculated deterministically via `int((stop - start) // step) + 1`.

## SPICE Deck Generation
- Implemented in `SimulationJob.build_netlist()`:
  - Generates `.dc <SOURCE> <START> <STOP> <STEP>`.
  - Automatically identifies circuit nodes and independent sources to construct `.print dc v(...) i(...)` if not already present.
  - Injects directives immediately before `.end`.

## Structured Multi-point Parser
- Implemented in `academic_core.infrastructure.ngspice_parser` (`parse_ngspice_output`):
  - Identifies `Index` header and reads multi-row numerical tables.
  - Handles multi-point series and multi-table paginated outputs cleanly.
  - Classifies signals:
    - Sweep variable: `name="v-sweep"`, `axis="sweep"`, `unit="V"`.
    - Node voltages: `axis="voltage"`, `unit="V"`.
    - Source branch currents: `axis="current"`, `unit="A"`, aliased to both `i(<source>)` and `<source>#branch`.
  - Maintains separation between solver IEEE 754 float samples (`raw_samples`) and domain Decimal samples (`samples`).

## Real Scientific Evidence (ngspice 47 via `ngspice_con.exe`)

1. **Validation A — Resistive Voltage Divider Sweep**:
   - Circuit: $V_1 = 0\text{ V}\dots 10\text{ V}$, step = $1\text{ V}$ (11 points); $R_1 = 1\text{ k}\Omega$, $R_2 = 1\text{ k}\Omega$.
   - Real Simulation Results:
     - Exact point count: 11 points (Index 0 to 10).
     - Sweep axis $V_{\text{sweep}}$: `(0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0) V`.
     - Output voltage $V(\text{out})$: `(0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0) V`.
     - Relationship verified: $V(\text{out}) = V_1 / 2$ across all 11 points within $< 10^{-6}\text{ V}$.
     - Status: `COMPLETED`, exit code: `0`, zero errors.

2. **Validation B — Symmetric Range & Current Verification**:
   - Circuit: $V_1 = -5\text{ V}\dots +5\text{ V}$, step = $0.5\text{ V}$ (21 points); $R_1 = 1\text{ k}\Omega$, $R_2 = 1\text{ k}\Omega$.
   - Real Simulation Results:
     - Exact point count: 21 points.
     - Extrema: $V_{\text{start}} = -5.00000\text{ V}$, $V_{\text{stop}} = 5.000000\text{ V}$.
     - Current signal $I(V_1)$:
       - At $V_1 = -5\text{ V}$: $I(V_1) = +0.002500000\text{ A}$ ($+2.5\text{ mA}$).
       - At $V_1 = 0\text{ V}$: $I(V_1) = 0.000000\text{ A}$ ($0.0\text{ mA}$).
       - At $V_1 = +5\text{ V}$: $I(V_1) = -0.00250000\text{ A}$ ($-2.5\text{ mA}$).
       - Linear relationship $I(V_1) = -V_1 / (R_1 + R_2)$ verified across all 21 points within $< 10^{-7}\text{ A}$.
     - Status: `COMPLETED`, exit code: `0`, zero errors.

3. **Full Service Pipeline**:
   - `EngineeringService.simulate_circuit()`:
     - Circuit: $V_1 = 0\dots 12\text{ V}$ in $2\text{ V}$ steps (7 points), $R_1 = 2\text{ k}\Omega, R_2 = 2\text{ k}\Omega$.
     - $V(\text{out}) = (0, 1, 2, 3, 4, 5, 6)\text{ V}$.
     - Status: `COMPLETED`, exit code: `0`.

## Limitations & Demarcation
- **DC Operating Point and DC Sweep Only**: Only `.op` and `.dc` analyses are supported in F7-B1/F7-B2.
- **Out of Scope (F7-B3+)**:
  - Transient analysis (`.tran`)
  - AC small-signal analysis (`.ac`)
  - Noise analysis (`.noise`)
  - Monte Carlo analysis
  - GUM uncertainty evaluation
  - Hardware I/O / SCPI
  - Custom MNA solver
  - Advanced UI plotting
  - F7-B3 or later phases

## Tests & Regression
- F7-B2 tests (`tests/test_f7b2_dc_sweep.py`): **11 passed**
- F7-B1 tests (`tests/test_f7b1_simulation.py`): **12 passed**
- F7-A tests (`tests/test_f7a_runtime.py`): **16 passed**
- Total Phase 7 tests: **39 passed**
- Full repository regression (F0–F6 + F7-A + F7-B1 + F7-B2): **244 passed, 2 skipped**

---

F7-B2 STATUS: PASS
