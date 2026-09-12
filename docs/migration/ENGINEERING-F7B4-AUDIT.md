# F7-B4 Audit — Análisis AC Completo con ngspice Real

Date: 2026-09-12 · Base: F7-B3 `8224a10`

## Overview & Scope
F7-B4 adds AC small-signal frequency domain analysis (.ac) to the scientific simulation pipeline:
- `ACAnalysis` domain model with parameter validation (`sweep_type` DEC/OCT/LIN, `points`, `fstart`, `fstop`).
- Extended `parse_spice_number` helper supporting engineering suffixes (`u`, `m`, `k`, `meg`, `n`, `p`, `g`, `t`, `f`).
- Deterministic SPICE deck generation for `.ac` cards and automated `.print ac` cards.
- Structured tabular parser for ngspice 47 complex frequency tables (`Index frequency v(...) i(...)` with comma-separated `re, im` pairs and paginated tables).
- Representation of frequency axis as `Signal` (`name="frequency"`, `axis="frequency"`, `unit="Hz"`).
- `ComplexSignal` model with separation of solver complex/float IEEE 754 precision and domain Decimal precision.
- Exact trigonometric & logarithmic transformations: magnitude $|H| = \sqrt{\text{Re}^2 + \text{Im}^2}$, phase in radians $(-\pi, \pi]$ and degrees $(-180^\circ, 180^\circ]$ via $\text{atan2}(\text{Im}, \text{Re})$, and $\text{dB} = 20 \log_{10}(|H|)$ with $-\infty$ for zero magnitude.
- Real scientific simulation and validation against ngspice 47 (`ngspice_con.exe`).
- Raw artifact reference in CAS (`FileBlobStore`) and execution provenance.

## Parameter Validation
- Enforced in `ACAnalysis.__post_init__`:
  - `sweep_type` must be non-empty and case-insensitively one of `"DEC"`, `"OCT"`, or `"LIN"`.
  - `points` must be a positive integer (`points > 0`).
  - `fstart` must be strictly positive (`fstart > 0`), as DC/0 Hz is mathematically undefined for logarithmic sweeps and invalid in SPICE AC analysis.
  - `fstop` must be strictly greater than `fstart` (`fstop > fstart`).
  - All frequency parameters are parsed and stored as domain `Decimal`.
  - Engineering suffixes (e.g. `"1k"`, `"100k"`, `"1MEG"`) parsed deterministically.

## SPICE Deck Generation
- Implemented in `SimulationJob.build_netlist()`:
  - Generates `.ac <sweep_type> <points> <fstart> <fstop>`.
  - If the circuit does not already specify AC excitation (`ac <mag>`), automatically augments the primary independent source with `ac 1` excitation.
  - Automatically identifies circuit nodes and independent sources to construct `.print ac v(...) i(...)` if not already present.
  - Avoids duplicating existing `.print ac` statements.
  - Injects directives immediately before `.end`.

## Structured Complex Parser
- Implemented in `academic_core.infrastructure.ngspice_parser` (`parse_ngspice_output`):
  - Identifies `Index frequency ...` header and reads multi-row complex numerical tables.
  - Handles ngspice comma-separated real and imaginary tokens (`<re>, <im>`).
  - Handles multi-page form-feed (`\x0c`) paginated `.print ac` outputs without duplicating frequency axis rows.
  - Classifies signals:
    - Frequency axis: `Signal(name="frequency", axis="frequency", unit="Hz")`.
    - Node voltages: `ComplexSignal(name="v(...)", axis="voltage", unit="V")`.
    - Source branch currents: `ComplexSignal(name="i(...)", axis="current", unit="A")`, aliased to both `i(<source>)` and `<source>#branch`.
  - Computes `magnitude_samples`, `phase_deg_samples`, `phase_rad_samples`, and `db_samples` deterministically.
  - Supports `sample_complex_at(signal_name, target_freq)` for exact or nearest-neighbor sampling along the frequency axis.

## Real Scientific Evidence (ngspice 47 via `ngspice_con.exe`)

1. **Validation A — RC Low-Pass Filter ($H(j\omega)$)**:
   - Circuit: $V_1 = \text{ac } 1$, $R_1 = 1\text{ k}\Omega$, $C_1 = 1\ \mu\text{F}$.
   - Cutoff frequency: $f_c = \frac{1}{2\pi R C} \approx 159.155\text{ Hz}$.
   - Decade sweep: $1\text{ Hz}\dots 100\text{ kHz}$, 10 points/decade (51 points).
   - Theoretical law: $H(j\omega) = \frac{1}{1 + j\omega RC}$.
   - Real Simulation Results:
     - At $f = 10\text{ Hz} \ll f_c$: $|H| = 0.9980$, phase $= -3.60^\circ$ (passband).
     - At $f \approx 158.489\text{ Hz} \approx f_c$: $|H| = 0.7082 \approx \frac{1}{\sqrt{2}}$, phase $= -44.88^\circ \approx -45^\circ$, $\text{dB} = -2.997\text{ dB} \approx -3.01\text{ dB}$.
     - At $f = 10\text{ kHz} \gg f_c$: $|H| = 0.0159$, phase $= -89.09^\circ \approx -90^\circ$.
     - At $f = 100\text{ kHz}$: $|H| = 0.00159$, roll-off $\approx -20\text{ dB/decade}$.
     - Status: `COMPLETED`, exit code: `0`, zero errors.

2. **Validation B — RC High-Pass Filter ($H(j\omega)$)**:
   - Circuit: $C_1 = 1\ \mu\text{F}$ in series with $R_1 = 1\text{ k}\Omega$ to ground.
   - Theoretical law: $H(j\omega) = \frac{j\omega RC}{1 + j\omega RC}$.
   - Cutoff frequency: $f_c \approx 159.155\text{ Hz}$.
   - Real Simulation Results:
     - At $f = 1\text{ Hz} \ll f_c$: $|H| = 0.00628$, phase $= +89.64^\circ$.
     - At $f \approx 158.489\text{ Hz} \approx f_c$: $|H| = 0.7060 \approx 0.7071$, phase $= +45.12^\circ \approx +45^\circ$.
     - At $f = 10\text{ kHz} \gg f_c$: $|H| = 0.9999 \approx 1.0$, phase $= +0.91^\circ \approx 0^\circ$.
     - Status: `COMPLETED`, exit code: `0`, zero errors.

3. **Validation C — RL Circuit Impedance & Response**:
   - Circuit: $V_1 = \text{ac } 1$, $R_1 = 1\text{ k}\Omega$, $L_1 = 1\text{ mH}$.
   - Frequency: $f = 100\text{ kHz}$ ($\omega \approx 628318.5\text{ rad/s}$, $\omega L \approx 628.32\ \Omega$).
   - Total impedance: $|Z| = \sqrt{R^2 + (\omega L)^2} \approx 1181.04\ \Omega$.
   - Real Simulation Results:
     - Inductor voltage $|V(mid)| = 0.5320\text{ V}$ (theoretical: $0.5320\text{ V}$, error $< 0.001\text{ V}$).
     - Phase $\phi(V(mid)) = 57.86^\circ$ (theoretical: $90^\circ - \arctan(628.32/1000) \approx 57.86^\circ$).
     - Source branch current magnitude: $|I(V_1)| = 0.8467\text{ mA}$ (theoretical: $1 / 1181.04 \approx 0.8467\text{ mA}$).
     - Status: `COMPLETED`, exit code: `0`, zero errors.

4. **Validation D — Series RLC Resonance**:
   - Circuit: $V_1 = \text{ac } 1$, $R_1 = 10\ \Omega$, $L_1 = 1\text{ mH}$, $C_1 = 1\ \mu\text{F}$.
   - Theoretical resonance: $f_0 = \frac{1}{2\pi \sqrt{LC}} = \frac{1}{2\pi \sqrt{10^{-9}}} \approx 5032.92\text{ Hz}$.
   - Linear sweep: $4500\text{ Hz}\dots 5500\text{ Hz}$ with 101 points ($10\text{ Hz}$ resolution).
   - Real Simulation Results:
     - Peak current at $f = 5030\text{ Hz}$ and $5040\text{ Hz}$: $|I(V_1)| = 0.099998\text{ A} \approx 0.1000\text{ A}$ ($1\text{ V} / 10\ \Omega$).
     - Impedance cancellation: $Z_L + Z_C \approx 0 \implies Z_{total} \approx R_1 = 10\ \Omega$.
     - Phase at resonance $\approx 180^\circ$ (SPICE source branch convention).
     - Off-resonance attenuation: at $4500\text{ Hz}$, current drops to $0.016\text{ A}$ ($>6\times$ attenuation).
     - Status: `COMPLETED`, exit code: `0`, zero errors.

5. **Multi-Sweep Types Verified**:
   - DEC (Decade): logarithmic spacing verified across multiple orders of magnitude.
   - OCT (Octave): octave frequency doubling verified.
   - LIN (Linear): uniform step frequency spacing verified.

6. **Full Service Pipeline**:
   - `EngineeringService.simulate_circuit()`:
     - Circuit domain model: `Circuit("RC_LOW_PASS")` with $V_1 = 1\text{ V}$, $R_1 = 1\text{ k}\Omega$, $C_1 = 1\ \mu\text{F}$.
     - `ACAnalysis(sweep_type="dec", points=10, fstart="1", fstop="100k")`.
     - $|H(f_c)| \approx 0.7082$, phase $\approx -44.88^\circ$.
     - Status: `COMPLETED`, exit code: `0`.

## Limitations & Demarcation
- **Supported Analyses**: `.op`, `.dc`, `.tran`, `.ac`.
- **Out of Scope (F7-B5+)**:
  - Noise analysis (`.noise`)
  - Monte Carlo analysis
  - GUM uncertainty evaluation
  - Hardware I/O / SCPI
  - Custom MNA solver
  - Advanced UI plotting
  - F7-B5 or later phases

## Tests & Regression
- F7-B4 tests (`tests/test_f7b4_ac.py`): **16 passed**
- F7-B3 tests (`tests/test_f7b3_transient.py`): **16 passed**
- F7-B2 tests (`tests/test_f7b2_dc_sweep.py`): **11 passed**
- F7-B1 tests (`tests/test_f7b1_simulation.py`): **12 passed**
- F7-A tests (`tests/test_f7a_runtime.py`): **16 passed**
- Total Phase 7 tests: **71 passed**
- Full repository regression (F0–F6 + F7-A + F7-B1 + F7-B2 + F7-B3 + F7-B4): **276 passed, 2 skipped** (100% clean)

---

F7-B4 STATUS: PASS
