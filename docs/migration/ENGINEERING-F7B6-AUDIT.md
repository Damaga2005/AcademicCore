# F7-B6 Audit — Monte Carlo y Análisis Estadístico con ngspice Real

Date: 2026-09-12 · Base: F7-B5 `b53f1db`

## 1. Overview & Architecture
F7-B6 implements a statistical parameter propagation and Monte Carlo simulation engine within the AcademicCore scientific engineering pipeline:
- **`MonteCarloAnalysis`**: Domain analysis specification defining:
  - `iterations: int` (must be $> 0$; $N=0$ and negative rejected, $N=1$ permitted)
  - `parameters: dict[str, ParameterDistribution]` (component distributions mapped by reference)
  - `output_variables: tuple[str, ...]` (scalar node voltages, branch currents, or derived metrics such as `fc`, `f0`, `max_current`)
  - `base_analysis: Any = "op"` (underlying SPICE analysis: `.op`, `ACAnalysis`, `TransientAnalysis`, `DCSweepAnalysis`)
  - `seed: int | None` (optional deterministic integer seed for absolute reproducibility)
  - `continue_on_error: bool = True` (configurable execution policy for partial failure resilience)
  - `metric_extractors: dict[str, Callable]` (optional extensible custom scalar metric extraction hooks)
- **`ParameterDistribution` Hierarchy**:
  - `UniformDistribution`: Continuous uniform parameter variation bounded by explicit $[low, high]$ or nominal with symmetric tolerance percentage ($low = nominal \cdot (1 - tol/100)$, $high = nominal \cdot (1 + tol/100)$).
  - `NormalDistribution`: Continuous Gaussian variation parameterized by nominal and either explicit $\sigma$ (`std_dev`) or tolerance percentage with explicit $\sigma$-coverage factor (`sigma_coverage`, default $3.0\sigma$ representing $99.73\%$ coverage), with optional $[min\_val, max\_val]$ clamping.
- **`VariableStatistics`**: Comprehensive sample statistics model:
  - Sample mean ($\bar{x}$)
  - Sample median
  - Minimum and maximum observed values
  - Sample variance ($s^2 = \frac{1}{N-1} \sum (x_i - \bar{x})^2$ for $N > 1$; $0$ for $N=1$)
  - Sample standard deviation ($s = \sqrt{s^2}$ for $N > 1$; $0$ for $N=1$)
  - Coefficient of variation ($CV = s / |\bar{x}|$ if $\bar{x} \neq 0$ else $0$)
  - Empirical percentiles: $P_1, P_5, P_{25}, P_{50}, P_{75}, P_{95}, P_{99}$ using rank linear interpolation
- **`MonteCarloIteration`**: Granular per-trial record linking trial index, sampled parameters, sub-seed, substituted netlist, execution result, extracted output values, status, and diagnostic errors.
- **`MonteCarloResult`**: Specialized `SimulationResult` subclass encapsulating requested/completed/failed trial counters, master seed, configuration, iterations sequence, aggregated statistics mapping, signals, execution provenance, and CAS raw payload hash.
- **Deterministic Pipeline**:
  $$\text{MonteCarloAnalysis} \longrightarrow \text{Pre-generated Parameter Samples} \longrightarrow \text{Netlist Substitution} \longrightarrow \text{ngspice 47 Batch} \longrightarrow \text{Statistical Aggregation}$$

---

## 2. Rigorous Definitions & Scope Boundaries
In strict compliance with metrological engineering standards and phase specifications:
- **MONTE CARLO $\neq$ GUM**: This engine implements repeated deterministic stochastic parameter propagation and empirical sample dispersion statistics.
- **NO GUM / ISO/IEC Guide 98-3**: Formal uncertainty budgets, sensitivity coefficients propagation ($u_c(y) = \sqrt{\sum c_i^2 u^2(x_i)}$), effective degrees of freedom (Welch-Satterthwaite), and coverage factors ($k$) are OUT OF SCOPE and reserved for a dedicated future phase.
- **Sample Standard Deviation $\neq$ Tolerance $\neq$ Error**:
  - *Tolerance* is a manufacturer component bound (e.g. $\pm 5\%$).
  - *Sample standard deviation* ($s$) is an empirical measure of dispersion of sampled outputs.
  - *Error* is the deviation from a known true reference value.
  - *Percentile* is an empirical distribution fractile, NOT a metrological uncertainty interval.
- **Concurrence & Parallelization**: Sequential execution is enforced to guarantee deterministic reproducibility, zero process leaks, and strict OS resource control. No multiprocessing or threading was introduced into simulation dispatch.
- **F7-B7**: Not started.

---

## 3. Mathematical Models & Algorithms

### A. Netlist Parameter Substitution
`substitute_netlist_parameters(netlist, params)` parses netlist decks line by line without altering SPICE dot-directives (`.op`, `.ac`, `.tran`, etc.) or comments (`*`):
- Two-terminal passive elements (`R`, `L`, `C`): Replaces value token (`parts[3]`), preserving all node designations and auxiliary parameters.
- Independent sources (`V`, `I`): Detects presence of `dc` token (e.g., `V1 in 0 dc 10 ac 1`) and updates the DC level while strictly preserving AC small-signal amplitudes.
- SPICE `.param` cards: Updates named parameter assignments (`.param R_val = <val>`).

### B. Statistical Formulas
For an output variable with $N$ successful trials $x_1, x_2, \dots, x_N$:
1. **Sample Mean**:
   $$\bar{x} = \frac{1}{N} \sum_{i=1}^N x_i$$
2. **Sample Variance (Bessel's Correction)**:
   $$s^2 = \begin{cases} \frac{1}{N-1} \sum_{i=1}^N (x_i - \bar{x})^2 & \text{for } N > 1 \\ 0 & \text{for } N = 1 \end{cases}$$
3. **Sample Standard Deviation**:
   $$s = \sqrt{s^2}$$
4. **Coefficient of Variation**:
   $$CV = \frac{s}{|\bar{x}|} \quad (\text{if } \bar{x} \neq 0)$$
5. **Linear Interpolation Percentiles**:
   For sorted values $x_{(0)} \le x_{(1)} \le \dots \le x_{(N-1)}$ and target percentile $p \in [0, 100]$:
   $$\text{Rank } r = (N - 1) \cdot \frac{p}{100}, \quad i = \lfloor r \rfloor, \quad f = r - i$$
   $$P_p = x_{(i)} + f \cdot (x_{(i+1)} - x_{(i)})$$

---

## 4. Scientific Validation Results (Real ngspice 47)

All validations were executed against the verified headless Windows console runtime:
`C:\Users\dmart\Documents\ngspice-47_64\Spice64\bin\ngspice_con.exe` (ngspice 47).

### Case 1: Resistive Voltage Divider (DC Operating Point)
- **Circuit**: $V_1 = 10\text{ V}$, $R_1 = 1000\ \Omega \pm 5\%$ uniform, $R_2 = 1000\ \Omega \pm 5\%$ uniform.
- **Analytical Model**:
  $$V_{out} = V_1 \frac{R_2}{R_1 + R_2}$$
  - Nominal: $V_{out} = 10 \cdot \frac{1000}{2000} = 5.0000\text{ V}$.
  - Extreme bounds:
    $$V_{out,\min} = 10 \cdot \frac{950}{1050 + 950} = 4.7500\text{ V}$$
    $$V_{out,\max} = 10 \cdot \frac{1050}{950 + 1050} = 5.2500\text{ V}$$
- **Real ngspice 47 Simulation (20 iterations, seed=12345)**:
  - Mean: $4.9960\text{ V}$ (deviation from nominal $< 0.08\%$)
  - Minimum: $4.8019\text{ V}$ ($> 4.75\text{ V}$)
  - Maximum: $5.1239\text{ V}$ ($< 5.25\text{ V}$)
  - Standard Deviation: $0.1033\text{ V}$
  - Median ($P_{50}$): $4.9818\text{ V}$
  - Status: `COMPLETED` (20/20 trials successful)

### Case 2: RC Low-Pass Filter (AC Frequency Response Cutoff)
- **Circuit**: $V_1 = 1\text{ V}_{\text{AC}}$, $R_1 = 1000\ \Omega \pm 5\%$ uniform, $C_1 = 1\ \mu\text{F} \pm 5\%$ uniform.
- **Analytical Model**:
  $$f_c = \frac{1}{2\pi R_1 C_1}$$
  - Nominal: $f_c = \frac{1}{2\pi \cdot 1000 \cdot 10^{-6}} \approx 159.155\text{ Hz}$.
  - Extreme bounds:
    $$f_{c,\min} = \frac{1}{2\pi \cdot 1050 \cdot 1.05 \times 10^{-6}} \approx 144.36\text{ Hz}$$
    $$f_{c,\max} = \frac{1}{2\pi \cdot 950 \cdot 0.95 \times 10^{-6}} \approx 176.35\text{ Hz}$$
- **Real ngspice 47 Simulation (15 iterations, AC sweep, seed=42)**:
  - Metric extracted: Frequency where $|V_{out}| / |V_{in}| = 1/\sqrt{2}$ ($-3.01\text{ dB}$).
  - Mean $f_c$: $163.07\text{ Hz}$ (within $2.5\%$ of nominal $159.15\text{ Hz}$)
  - Minimum $f_c$: $146.23\text{ Hz}$ (strictly within physical bounds)
  - Maximum $f_c$: $174.51\text{ Hz}$ (strictly within physical bounds)
  - Standard Deviation: $8.05\text{ Hz}$
  - Status: `COMPLETED` (15/15 trials successful)

### Case 3: Series RLC Resonant Circuit (Resonance Frequency & Peak Current)
- **Circuit**: $V_1 = 1\text{ V}_{\text{AC}}$, $R_1 = 10\ \Omega \pm 5\%$, $L_1 = 1\text{ mH} \pm 5\%$, $C_1 = 1\ \mu\text{F} \pm 5\%$.
- **Analytical Model**:
  $$f_0 = \frac{1}{2\pi\sqrt{L_1 C_1}}, \quad I_{\max} = \frac{V_1}{R_1} \quad (\text{at resonance } Z = R_1)$$
  - Nominal resonance: $f_0 = \frac{1}{2\pi\sqrt{10^{-3} \cdot 10^{-6}}} \approx 5032.92\text{ Hz}$.
  - Nominal peak current: $I_{\max} = \frac{1\text{ V}}{10\ \Omega} = 0.1000\text{ A}$.
  - Current bounds with $R_1 \in [9.5, 10.5]\ \Omega$: $I_{\max} \in [0.0952, 0.1053]\text{ A}$.
- **Real ngspice 47 Simulation (15 iterations, linear AC sweep, seed=999)**:
  - Mean $f_0$: $5032.06\text{ Hz}$ (deviation from nominal $< 0.02\%$)
  - Bounds on $f_0$: $[4856.99\text{ Hz}, 5192.56\text{ Hz}]$
  - Standard Deviation of $f_0$: $101.80\text{ Hz}$
  - Mean Peak Current: $0.1010\text{ A}$ (deviation from nominal $< 1\%$)
  - Status: `COMPLETED` (15/15 trials successful)

---

## 5. Determinism, Seed Reproducibility & Fault Handling
1. **RNG Reproducibility**:
   - Master RNG instantiated via `random.Random(analysis.seed)`.
   - Each trial $i$ receives a deterministic `sub_seed = master_seed_rng.randint(0, 2**31 - 1)`.
   - Parameter sampling order sorted alphabetically by component name to eliminate dict ordering variance.
   - Run 1 (seed 12345) and Run 2 (seed 12345) generated identical samples across all 20 iterations.
   - Run 3 (seed 54321) generated distinct samples.
2. **Partial Failures (`continue_on_error`)**:
   - `continue_on_error=True`: When a solver error occurs on iteration $k$, the failure is captured in `MonteCarloIteration(status="FAILED", errors=(...))`. Execution continues for remaining trials, and final status is marked `PARTIAL`.
   - `continue_on_error=False`: Halts immediately upon first trial failure, marking final status `FAILED`.
3. **Process Cleanup & Cancellation**:
   - `backend.cancel()` cleanly signals active ngspice processes and breaks the iteration loop, marking status `CANCELLED` without leaving orphaned background processes.
4. **CAS & Provenance**:
   - Serialized summary payload stored in `FileBlobStore` with SHA-256 digest.
   - Provenance records backend ID, ngspice version, executable path, seeds, parameters, and timestamps.

---

## 6. Test Suite & Verification Summary
- **F7-B6 Dedicated Tests** (`tests/test_f7b6_monte_carlo.py`): 29 passed.
- **F7 Full Pipeline Regression** (`tests/test_f7*.py`): 118 passed in 30.60s.
- **Repository Full Regression** (`pytest`): 323 passed, 2 skipped in 131.35s.
- **Regressions**: 0 failed, 0 broken contracts.
