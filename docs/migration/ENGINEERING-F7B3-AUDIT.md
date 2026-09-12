# F7-B3 Audit — Análisis Transitorio REAL con ngspice

Date: 2026-09-12 · Base: F7-B2 `a2e9805`

## Overview & Scope
F7-B3 adds Transient analysis (.tran) to the scientific simulation pipeline:
- `TransientAnalysis` domain specification with parameter validation (`tstep`, `tstop`, optional `tstart`, `tmax`, `uic`).
- `parse_spice_number` helper supporting engineering suffixes (`u`, `m`, `k`, `meg`, `n`, `p`, `g`, `t`, `f`).
- Deterministic SPICE deck generation for `.tran` and automated `.print tran` cards.
- Structured multi-point tabular parser for ngspice transient tables (`Index time v(...) i(...)`).
- Representation of time axis as `Signal` (`name="time"`, `axis="time"`, `unit="s"`).
- Multi-point sequence support in `SimulationResult` (`time_axis`, `points_count`, `sample_at`, `voltage_samples`, `current_samples`).
- Real scientific simulation and validation against ngspice 47 (`ngspice_con.exe`).
- Raw artifact reference in CAS (`FileBlobStore`) and execution provenance.

## Parameter Validation
- Enforced in `TransientAnalysis.__post_init__`:
  - `tstep` must be positive (`tstep > 0`).
  - `tstop` must be positive (`tstop > 0`).
  - `tstart` must be non-negative (`tstart >= 0`).
  - `tstop` must be strictly greater than `tstart` (`tstop > tstart`).
  - If `tmax` is specified, it must be positive (`tmax > 0`).
  - All numerical parameters are parsed and stored as domain `Decimal`.
  - Engineering suffixes (e.g. `"10u"`, `"5m"`, `"1k"`) parsed deterministically.

## SPICE Deck Generation
- Implemented in `SimulationJob.build_netlist()`:
  - Generates `.tran <tstep> <tstop> [<tstart> [<tmax>]] [uic]`.
  - Automatically identifies circuit nodes and independent sources to construct `.print tran v(...) i(...)` if not already present.
  - Avoids duplicating existing `.print tran` statements.
  - Injects directives immediately before `.end`.

## Structured Multi-point Parser
- Implemented in `academic_core.infrastructure.ngspice_parser` (`parse_ngspice_output`):
  - Identifies `Index` header and reads multi-row numerical tables.
  - Classifies signals:
    - Time variable: `name="time"`, `axis="time"`, `unit="s"`.
    - Node voltages: `axis="voltage"`, `unit="V"`.
    - Source branch currents: `axis="current"`, `unit="A"`, aliased to both `i(<source>)` and `<source>#branch`.
  - Maintains separation between solver IEEE 754 float samples (`raw_samples`) and domain Decimal samples (`samples`).
  - Supports `sample_at(signal_name, target_time)` for exact or nearest-neighbor sampling along the time axis.

## Real Scientific Evidence (ngspice 47 via `ngspice_con.exe`)

1. **Validation A — RC Step Charging ($V_C(t)$)**:
   - Circuit: $V_1 = \text{pulse}(0\ 5\ 0\ 1\text{n}\ 1\text{n}\ 10\text{m})$, $R_1 = 1\text{ k}\Omega$, $C_1 = 1\ \mu\text{F}$.
   - Time constant: $\tau = R_1 \cdot C_1 = 1000 \cdot 10^{-6} = 1\text{ ms} = 0.001\text{ s}$.
   - Transient range: $0\dots 5\text{ ms}$, step $10\ \mu\text{s}$ (501 points).
   - Theoretical law: $V_C(t) = 5 \cdot (1 - e^{-t/\tau})$.
   - Real Simulation Results:
     - $V_C(0) = 0.000000\text{ V}$ (error: $0.0000\text{ V}$, theoretical: $0\text{ V}$).
     - $V_C(1\text{ ms}) = 3.160603\text{ V}$ (theoretical: $5(1 - e^{-1}) \approx 3.160603\text{ V}$, error $< 10^{-5}\text{ V}$).
     - $V_C(5\text{ ms}) = 4.966310\text{ V}$ (theoretical: $5(1 - e^{-5}) \approx 4.966310\text{ V}$, error $< 10^{-5}\text{ V}$).
     - Justified tolerance: $\pm 0.02\text{ V}$ ($< 0.6\%$ relative error).
     - Status: `COMPLETED`, exit code: `0`, zero errors.

2. **Validation B — RC Charging Current ($I(t)$)**:
   - Circuit: identical RC setup with current monitored at source branch $I(V_1)$.
   - Theoretical law: $I(t) = \frac{V_0}{R} e^{-t/\tau}$; SPICE convention: $I(V_1)(t) = -5\text{ mA} \cdot e^{-t/\tau}$.
   - Real Simulation Results:
     - $I(0) = 0.000000\text{ A}$ (source at $0\text{ V}$ before pulse rise).
     - $I(10\ \mu\text{s}) = -0.004950\text{ A}$ ($-4.95\text{ mA}$, step reached $5\text{ V}$).
     - $I(1\text{ ms}) = -0.00183939\text{ A}$ (theoretical: $-5\text{ mA} \cdot e^{-1} \approx -1.839397\text{ mA}$).
     - $I(5\text{ ms}) = -0.00003369\text{ A}$ (theoretical: $-5\text{ mA} \cdot e^{-5} \approx -0.033689\text{ mA}$).
     - Justified tolerance: $\pm 0.0001\text{ A}$.
     - Status: `COMPLETED`, exit code: `0`, zero errors.

3. **Validation C — UIC (Use Initial Conditions)**:
   - Circuit: $V_1 = 5\text{ V}$ (DC), $R_1 = 1\text{ k}\Omega$, $C_1 = 1\ \mu\text{F}\ \text{ic}=0$, `.tran 10u 5m uic`.
   - Real Simulation Results:
     - $V_C(0) = 0.000000\text{ V}$.
     - $I(V_1)(0) = -0.005000\text{ A}$ ($-5.0\text{ mA}$).
     - $V_C(1\text{ ms}) = 3.160603\text{ V}$.
     - Status: `COMPLETED`, exit code: `0`, zero errors.

4. **Full Service Pipeline**:
   - `EngineeringService.simulate_circuit()`:
     - Circuit domain model: `Circuit("RC_STEP")` with $V_1 = 5\text{ V}$, $R_1 = 1\text{ k}\Omega$, $C_1 = 1\ \mu\text{F}$.
     - `TransientAnalysis("10u", "5m", uic=True)`.
     - $V_C(1\text{ ms}) = 3.1606\text{ V}$.
     - Status: `COMPLETED`, exit code: `0`.

## Limitations & Demarcation
- **Supported Analyses**: `.op`, `.dc`, `.tran`.
- **Out of Scope (F7-B4+)**:
  - AC small-signal analysis (`.ac`)
  - Noise analysis (`.noise`)
  - Monte Carlo analysis
  - GUM uncertainty evaluation
  - Hardware I/O / SCPI
  - Custom MNA solver
  - Advanced UI plotting
  - F7-B4 or later phases

## Tests & Regression
- F7-B3 tests (`tests/test_f7b3_transient.py`): **16 passed**
- F7-B2 tests (`tests/test_f7b2_dc_sweep.py`): **11 passed**
- F7-B1 tests (`tests/test_f7b1_simulation.py`): **12 passed**
- F7-A tests (`tests/test_f7a_runtime.py`): **16 passed**
- Total Phase 7 tests: **55 passed**
- Full repository regression (F0–F6 + F7-A + F7-B1 + F7-B2 + F7-B3): **260 passed, 2 skipped** (100% clean)

---

F7-B3 STATUS: PASS
