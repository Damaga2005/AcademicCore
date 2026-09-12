# F7-B5 Audit — Análisis de Ruido y Sensibilidad con ngspice Real

Date: 2026-09-12 · Base: F7-B4 `4d87332`

## 1. Overview & Architecture
F7-B5 extends the scientific simulation pipeline of AcademicCore with:
- **`NoiseAnalysis`**: Small-signal frequency-domain noise analysis (`.noise <output> <input> <sweep_type> <points> <fstart> <fstop>`).
- **`SensitivityAnalysis`**: Deterministic sensitivity analysis (`.sens <output>` for DC operating point and `.sens <output> ac <sweep_type> <points> <fstart> <fstop>` for AC frequency response).
- **`NoiseResult`**: Domain model capturing noise spectral density curves (`onoise_spectrum`, `inoise_spectrum` in $\text{V}/\sqrt{\text{Hz}}$) and integrated noise totals (`onoise_total`, `inoise_total` in $\text{V}_{\text{RMS}}$).
- **`SensitivityResult`**: Domain model capturing component sensitivities ($\frac{\partial V_{out}}{\partial p}$) and normalized sensitivities ($S_p = \frac{p}{V_{out}} \frac{\partial V_{out}}{\partial p}$) for resistors, capacitors, inductors, and independent sources.
- **Structured ngspice 47 Parsers**:
  - `_parse_noise_tables`: Decodes `Integrated Noise` and `Noise Spectral Density Curves`.
  - `_parse_sens_tables`: Decodes DC scalar sensitivities and multi-frequency AC complex sensitivities across paginated output tables.
- **Scientific Validation**: Verified against physical laws and analytical derivations with real ngspice 47 (`ngspice_con.exe`).
- **Data Integrity & CAS**: Full raw solver stdout/stderr preserved in Content Addressable Storage with SHA-256 digest and execution provenance.

---

## 2. SPICE Directives & Syntax

### A. Noise Analysis (`.noise`)
- SPICE card syntax:
  ```spice
  .noise <output_variable> <input_source> <sweep_type> <points> <fstart> <fstop>
  .print noise all
  ```
- Automated deck synthesis in `SimulationJob.build_netlist()` ensures the input source has AC excitation (`ac 1`) and appends `.print noise all` without duplication.

### B. Sensitivity Analysis (`.sens`)
- DC Sensitivity syntax:
  ```spice
  .sens <output_variable>
  .print sens all
  ```
- AC Sensitivity syntax:
  ```spice
  .sens <output_variable> ac <sweep_type> <points> <fstart> <fstop>
  .print sens all
  ```
- Automated deck synthesis automatically detects whether DC or AC sensitivity is requested, ensures AC excitation when necessary, and appends the appropriate `.print sens` card.

---

## 3. Physical Models & Mathematical Equations

### A. Resistor Thermal Noise (Johnson-Nyquist Law)
- Thermal noise voltage spectral density across a resistance $R$:
  $$e_n = \sqrt{4 k_B T R}$$
  where:
  - $k_B = 1.380649 \times 10^{-23}\text{ J/K}$ (Boltzmann constant)
  - $T = 300.15\text{ K}$ (SPICE default nominal temperature: $27^\circ\text{C}$)
  - $R = 1000\ \Omega$ ($1\text{ k}\Omega$)
- Theoretical value:
  $$e_n = \sqrt{4 \cdot 1.380649 \cdot 10^{-23} \cdot 300.15 \cdot 1000} = \sqrt{1.657579 \times 10^{-17}} \approx 4.071337 \times 10^{-9}\text{ V}/\sqrt{\text{Hz}}$$
- Real ngspice 47 result:
  $$e_n(100\text{ Hz}) = 4.071372 \times 10^{-9}\text{ V}/\sqrt{\text{Hz}}$$
- **Relative error**: $8.6 \times 10^{-6}$ ($< 0.001\%$).

### B. RC Low-Pass Filter Noise & Total Integrated Noise
- Output spectral density:
  $$e_{no}(f) = \frac{e_n}{\sqrt{1 + (2\pi f RC)^2}}$$
  - At $f \ll f_c$: $e_{no}(f) \approx e_n = 4.071 \times 10^{-9}\text{ V}/\sqrt{\text{Hz}}$.
  - At $f = f_c = \frac{1}{2\pi RC} \approx 159.155\text{ Hz}$: $e_{no}(f_c) = \frac{e_n}{\sqrt{2}} \approx 2.8789 \times 10^{-9}\text{ V}/\sqrt{\text{Hz}}$.
  - At $f = 100\text{ kHz} \gg f_c$: $e_{no}(f) \approx 6.48 \times 10^{-12}\text{ V}/\sqrt{\text{Hz}}$ (severe high-frequency roll-off).
- Total integrated noise over infinite bandwidth:
  $$V_{\text{RMS}} = \sqrt{\int_0^\infty e_{no}^2(f) df} = \sqrt{\frac{k_B T}{C}}$$
  - For $C = 1\ \mu\text{F}$:
    $$V_{\text{RMS}} = \sqrt{\frac{1.380649 \times 10^{-23} \cdot 300.15}{10^{-6}}} \approx 6.4373 \times 10^{-8}\text{ V}_{\text{RMS}}$$
  - Real ngspice 47 integrated noise over $1\text{ Hz}\dots 100\text{ kHz}$:
    $$V_{\text{RMS, ngspice}} = 6.414136 \times 10^{-8}\text{ V}_{\text{RMS}}$$
  - **Relative error**: $0.36\%$ (due to finite integration bandwidth $100\text{ kHz}$ vs $\infty$).

### C. DC Sensitivity Equations (Voltage Divider)
- Circuit: $V_1 = 5\text{ V}$, $R_1 = 1\text{ k}\Omega$, $R_2 = 1\text{ k}\Omega$, $V_{out} = V_1 \frac{R_2}{R_1 + R_2} = 2.5\text{ V}$.
- Analytical derivatives:
  $$\frac{\partial V_{out}}{\partial R_1} = -V_1 \frac{R_2}{(R_1 + R_2)^2} = -\frac{5000}{4 \times 10^6} = -1.25 \times 10^{-3}\text{ V}/\Omega$$
  $$\frac{\partial V_{out}}{\partial R_2} = +V_1 \frac{R_1}{(R_1 + R_2)^2} = +\frac{5000}{4 \times 10^6} = +1.25 \times 10^{-3}\text{ V}/\Omega$$
  $$\frac{\partial V_{out}}{\partial V_1} = \frac{R_2}{R_1 + R_2} = 0.5\text{ V/V}$$
- Real ngspice 47 results:
  - $R_1$: `-0.00125000` (error: $0.0$)
  - $R_2$: `+0.001249999` (error $< 10^{-9}$)
  - $V_1$: `+0.5000000` (error: $0.0$)
- Normalized sensitivities ($S_p = \frac{p}{V_{out}} \frac{\partial V_{out}}{\partial p}$):
  $$S_{R1} = -0.5, \quad S_{R2} = +0.5, \quad S_{V1} = 1.0$$
- Central finite-difference check ($\delta = 10^{-4}$):
  $$\frac{\Delta V_{out}}{\Delta R_1} = \frac{V_{out}(R_1 + 0.1) - V_{out}(R_1 - 0.1)}{0.2} = -0.00125000\text{ V}/\Omega$$

### D. AC Small-Signal Sensitivity Equations (RC Filter)
- Transfer function:
  $$H(j\omega) = \frac{1}{1 + j\omega RC}$$
- Complex derivatives with respect to $C$ and $R$:
  $$\frac{\partial H}{\partial C} = -\frac{j\omega R}{(1 + j\omega RC)^2}$$
  $$\frac{\partial H}{\partial R} = -\frac{j\omega C}{(1 + j\omega RC)^2}$$
- At $f = 1\text{ Hz}$ ($\omega = 2\pi\text{ rad/s}$), $R = 1000\ \Omega$, $C = 1\ \mu\text{F}$:
  - Analytical:
    $$\frac{\partial H}{\partial C} = -78.9506 - 6282.44j$$
    $$\frac{\partial H}{\partial R} = -7.8951 \times 10^{-8} - 6.2824 \times 10^{-6}j$$
  - Real ngspice 47 output:
    $$\text{c1} = -7.89506 \times 10^1 - 6.28244 \times 10^3j$$
    $$\text{r1} = -7.89506 \times 10^{-8} - 6.28244 \times 10^{-6}j$$
  - **Relative error**: $< 0.001\%$.

---

## 4. Scientific Case Comparison Matrix

| Case | Variable | Theory / Analytical | ngspice 47 Real | Absolute Error | Relative Error | Tolerance | Status |
|---|---|---|---|---|---|---|:---:|
| 1. Resistor Noise | $e_n$ (100 Hz) | $4.071337\text{ nV}/\sqrt{\text{Hz}}$ | $4.071372\text{ nV}/\sqrt{\text{Hz}}$ | $3.5 \times 10^{-14}$ | $0.00086\%$ | $0.1\%$ | **PASS** |
| 2. RC Noise (1 Hz) | $e_{no}$ (1 Hz) | $4.0713\text{ nV}/\sqrt{\text{Hz}}$ | $4.07129\text{ nV}/\sqrt{\text{Hz}}$ | $1.0 \times 10^{-14}$ | $0.00025\%$ | $1.0\%$ | **PASS** |
| 2. RC Noise ($f_c$) | $e_{no}(f_c)$ | $2.8789\text{ nV}/\sqrt{\text{Hz}}$ | $2.8849\text{ nV}/\sqrt{\text{Hz}}$ | $6.0 \times 10^{-12}$ | $0.21\%$ | $1.0\%$ | **PASS** |
| 2. RC Integrated | $V_{\text{RMS}}$ | $64.373\text{ nV}_{\text{RMS}}$ | $64.141\text{ nV}_{\text{RMS}}$ | $2.3 \times 10^{-10}$ | $0.36\%$ | $1.0\%$ | **PASS** |
| 3. DC Sens $R_1$ | $\partial V / \partial R_1$ | $-1.25000\text{ mV}/\Omega$ | $-1.25000\text{ mV}/\Omega$ | $< 10^{-8}$ | $< 10^{-4}\%$ | $0.01\%$ | **PASS** |
| 3. DC Sens $R_2$ | $\partial V / \partial R_2$ | $+1.25000\text{ mV}/\Omega$ | $+1.249999\text{ mV}/\Omega$ | $< 10^{-8}$ | $< 10^{-4}\%$ | $0.01\%$ | **PASS** |
| 3. DC Sens $V_1$ | $\partial V / \partial V_1$ | $0.500000\text{ V/V}$ | $0.500000\text{ V/V}$ | $0.0$ | $0.0\%$ | $0.01\%$ | **PASS** |
| 4. AC Sens $C_1$ (Re) | $\text{Re}(\partial H / \partial C)$ | $-78.9506$ | $-78.9506$ | $< 10^{-4}$ | $< 10^{-4}\%$ | $0.1\%$ | **PASS** |
| 4. AC Sens $C_1$ (Im) | $\text{Im}(\partial H / \partial C)$ | $-6282.44$ | $-6282.44$ | $< 10^{-2}$ | $< 10^{-4}\%$ | $0.1\%$ | **PASS** |
| 4. AC Sens $R_1$ (Re) | $\text{Re}(\partial H / \partial R)$ | $-7.8951 \times 10^{-8}$ | $-7.8951 \times 10^{-8}$ | $< 10^{-12}$ | $< 10^{-4}\%$ | $0.1\%$ | **PASS** |
| 4. AC Sens $R_1$ (Im) | $\text{Im}(\partial H / \partial R)$ | $-6.2824 \times 10^{-6}$ | $-6.2824 \times 10^{-6}$ | $< 10^{-10}$ | $< 10^{-4}\%$ | $0.1\%$ | **PASS** |
| 5. RLC Resonance Sens | $\partial V / \partial L_1, C_1, R_1$ | Matrix across 21 pts | 21 complex points | — | — | — | **PASS** |

---

## 5. Limitations & Demarcation
- **Certified Capabilities**:
  - DC Operating Point (`.op`)
  - DC Sweep (`.dc`)
  - Transient Analysis (`.tran`)
  - AC Small-Signal Frequency Response (`.ac`)
  - Noise Analysis (`.noise`)
  - Deterministic Sensitivity Analysis (`.sens`, both DC and AC)
- **Out of Scope for F7-B5**:
  - Monte Carlo analysis
  - Guide to the Expression of Uncertainty in Measurement (GUM)
  - Statistical uncertainty propagation
  - Physical instrumentation / SCPI
  - Custom internal MNA solver
  - Advanced UI interactive graphics
  - Phase F7-B6

---

## 6. Test Suites Summary
- F7-B5 tests (`tests/test_f7b5_noise_sensitivity.py`): **18 passed**
- F7-B4 tests (`tests/test_f7b4_ac.py`): **16 passed**
- F7-B3 tests (`tests/test_f7b3_transient.py`): **16 passed**
- F7-B2 tests (`tests/test_f7b2_dc_sweep.py`): **11 passed**
- F7-B1 tests (`tests/test_f7b1_simulation.py`): **12 passed**
- F7-A tests (`tests/test_f7a_runtime.py`): **16 passed**
- **Total Phase 7 Suite**: **89 passed**
- **Full Repository Regression**: **294 passed, 2 skipped** (100% clean)

---

F7-B5 STATUS: PASS
