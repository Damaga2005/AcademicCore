# F7-B7 Audit — GUM / Measurement Uncertainty Evaluation Engine

Date: 2026-09-12 · Base: F7-B6 `e39efc9`

## 1. Overview & Architecture
F7-B7 implements an ISO/IEC Guide 98-3 (Guide to the Expression of Uncertainty in Measurement, GUM) evaluation engine within the AcademicCore scientific engineering domain:
- **`MeasurementModel`**: Functional relationship $Y = f(X_1, X_2, \dots, X_n)$ supporting:
  - Expression-based equations evaluated via the secure `AcademicCore` equation parser (strictly NO `eval` / `exec`).
  - Native Python callables (`evaluator: Callable[[dict[str, Decimal]], Decimal]`).
  - Explicit and user-overridable sensitivity coefficients.
- **`InputQuantity`**: Input quantity domain model supporting both Type A and Type B evaluations:
  - **Type A**: Evaluated from repeated experimental observations using sample standard deviation with Bessel's correction:
    $$s = \sqrt{\frac{1}{n-1} \sum_{i=1}^n (x_i - \bar{x})^2}, \quad u(x) = \frac{s}{\sqrt{n}}, \quad \nu = n - 1$$
  - **Type B Rectangular / Uniform**: Bounds $\pm a$ with standard uncertainty $u = \frac{a}{\sqrt{3}}$ and $\nu = \infty$.
  - **Type B Triangular**: Bounds $\pm a$ with standard uncertainty $u = \frac{a}{\sqrt{6}}$ and $\nu = \infty$.
  - **Type B Normal**: Stated expanded uncertainty $U$ with coverage factor $k$: $u = \frac{U}{k}$, with either $\nu = \infty$ or explicit calibration degrees of freedom.
  - **Type B Explicit**: Direct specification of nominal value, standard uncertainty, and degrees of freedom.
- **Sensitivity Coefficients ($c_i = \frac{\partial f}{\partial X_i}$)**:
  - **Explicit**: User-specified constant or formula callback.
  - **Analytic**: Recognized analytical patterns (sums, differences, linear forms).
  - **Numerical**: Central finite-difference scheme with scale-aware step size:
    $$c_i \approx \frac{f(x_1, \dots, x_i + h_i, \dots, x_n) - f(x_1, \dots, x_i - h_i, \dots, x_n)}{2 h_i}, \quad h_i = \max(|x_i| \cdot 10^{-6}, 10^{-8})$$
- **Correlation and Covariance Matrix**:
  - `CorrelationMatrix`: Validates symmetric $r(X_i, X_j) = r(X_j, X_i) \in [-1, 1]$ and unit diagonal $r(X_i, X_i) = 1$.
  - Covariance calculation: $\text{cov}(X_i, X_j) = r(X_i, X_j) \cdot u(X_i) \cdot u(X_j)$.
- **Combined Standard Uncertainty ($u_c(y)$)**:
  $$u_c^2(y) = \sum_{i=1}^n c_i^2 u^2(X_i) + 2 \sum_{i=1}^{n-1} \sum_{j=i+1}^n c_i c_j \text{cov}(X_i, X_j)$$
  $$u_c(y) = \sqrt{u_c^2(y)}$$
- **Effective Degrees of Freedom (Welch-Satterthwaite)**:
  $$\nu_{\text{eff}} = \frac{u_c^4(y)}{\sum_{i=1}^n \frac{(c_i u(X_i))^4}{\nu_i}}$$
  Components with infinite degrees of freedom ($\nu_i = \infty$) contribute zero to the denominator. If all components are infinite or total variance is zero, $\nu_{\text{eff}} = \infty$.
- **Pure-Python Student's t Distribution**:
  - Deterministic evaluation of regularized incomplete beta function $I_x(a, b)$ via Lentz's continued fraction method.
  - Newton-Raphson root finding for Student's t quantile function $t_p(\nu)$.
  - Exact reproduction of ISO/IEC Guide 98-3 Table G.2 values for $\nu \in [1, \dots, 100, \infty]$ at $95\%$ and $99\%$ confidence levels without external dependencies like `scipy`.
- **Coverage Factor $k$ and Expanded Uncertainty $U$**:
  - Dynamic derivation from Student's t quantile: $k = t_{(1+p)/2}(\nu_{\text{eff}})$ (strictly non-hardcoded).
  - Expanded uncertainty: $U = k \cdot u_c(y)$.
  - Explicit user override supported when requested.
- **Uncertainty Budget Table & Provenance**:
  - `UncertaintyBudgetRow`: Granular per-quantity breakdown (nominal, unit, type, distribution, standard uncertainty, degrees of freedom, sensitivity coefficient, calculation method, contribution $u_i(y) = c_i u_i$, variance contribution $(c_i u_i)^2$, percentage of total variance, correlation metadata, and source).
  - `UncertaintyBudget`: Sortable budget table (`by_contribution`, `by_name`), markdown table rendering, and deterministic JSON dictionary serialization.
  - `GUMResult`: Clean result model with CAS artifact storage integration (`FileBlobStore`) and execution provenance.

---

## 2. Rigorous Definitions & Scope Boundaries
- **GUM $\neq$ MONTE CARLO**: GUM (ISO/IEC Guide 98-3) is an analytical first-order Taylor expansion framework calculating combined uncertainty, sensitivity coefficients, effective degrees of freedom, and expanded uncertainty. It is completely decoupled from F7-B6 `MonteCarloResult`.
- **NO External Dependencies**: Implemented strictly in pure Python standard library (`math`, `decimal`, `statistics`, `hashlib`, `json`, `re`). `scipy` is NOT used or required.
- **NO eval/exec**: Arbitrary code execution is strictly prohibited. All equations are parsed and evaluated through the validated `AcademicCore` equation AST interpreter.
- **NO Sensor / Hardware Ingestion**: Real physical sensors, DAQ, and calibration document parsers are out of scope.
- **NO Bayesian / Fuzzy Uncertainty**: Out of scope.
- **F7-B8**: Not started.

---

## 3. Mathematical Models & Benchmark Validation

### A. Continued Fraction & Student-t Inversion
The regularized incomplete beta function:
$$I_x(a, b) = \frac{1}{B(a, b)} \int_0^x t^{a-1} (1-t)^{b-1} dt$$
is evaluated using Lentz's method:
$$I_x(a, b) = \frac{x^a (1-x)^b}{a B(a, b)} \cdot \cfrac{1}{1 + \cfrac{d_1}{1 + \cfrac{d_2}{1 + \dots}}}$$
For Student's t CDF with $\nu$ degrees of freedom:
$$F(t; \nu) = 1 - \frac{1}{2} I_x\left(\frac{\nu}{2}, \frac{1}{2}\right), \quad x = \frac{\nu}{\nu + t^2}$$
Quantiles are inverted via Newton-Raphson iteration with machine precision.

### B. ISO Guide 98-3 Table G.2 Benchmarks
Validation against standard ISO Guide 98-3 Table G.2:
| $\nu$ | $p = 0.95$ Target | Computed $k$ | Error | Verdict |
|---|---|---|---|---|
| 1 | 12.71 | 12.7062 | < 0.005 | PASS |
| 2 | 4.30 | 4.3027 | < 0.005 | PASS |
| 3 | 3.18 | 3.1824 | < 0.005 | PASS |
| 4 | 2.78 | 2.7764 | < 0.005 | PASS |
| 5 | 2.57 | 2.5706 | < 0.005 | PASS |
| 10 | 2.23 | 2.2281 | < 0.005 | PASS |
| 20 | 2.09 | 2.0860 | < 0.005 | PASS |
| 50 | 2.01 | 2.0086 | < 0.005 | PASS |
| 100 | 1.98 | 1.9840 | < 0.005 | PASS |
| $\infty$ | 1.960 | 1.95996 | < 0.001 | PASS |

---

## 4. Analytical Validation Cases (Cases A through J)

1. **Case A: Sum ($Y = X_1 + X_2$)**:
   - Inputs: $X_1 = 10 \text{ V}, u_1 = 0.1 \text{ V}$; $X_2 = 20 \text{ V}, u_2 = 0.2 \text{ V}$.
   - Sensitivities: $c_1 = 1.0, c_2 = 1.0$.
   - Result: $Y = 30.0 \text{ V}, u_c = \sqrt{0.1^2 + 0.2^2} = \sqrt{0.05} \approx 0.223607 \text{ V}$.
   - Contributions: $X_1 \to 20\%$, $X_2 \to 80\%$.
2. **Case B: Product ($Y = X_1 \cdot X_2$)**:
   - Inputs: $X_1 = 10 \text{ V}, u_1 = 0.1 \text{ V}$; $X_2 = 5 \text{ A}, u_2 = 0.05 \text{ A}$.
   - Sensitivities: $c_1 = X_2 = 5, c_2 = X_1 = 10$.
   - Result: $P = 50.0 \text{ W}, u_c = \sqrt{0.5^2 + 0.5^2} = \sqrt{0.5} \approx 0.707107 \text{ W}$.
   - Relative uncertainty: $\frac{u_c}{P} = \sqrt{0.01^2 + 0.01^2} = 1.414\%$.
3. **Case C: Voltage Divider ($V_{out} = V_{in} \cdot \frac{R_2}{R_1 + R_2}$)**:
   - Inputs: $V_{in} = 10 \text{ V}, u = 0.05 \text{ V}$; $R_1 = 1000\ \Omega, u = 10\ \Omega$; $R_2 = 1000\ \Omega, u = 10\ \Omega$.
   - Sensitivities: $c_{V_{in}} = 0.5$, $c_{R_1} = -0.0025 \text{ V}/\Omega$, $c_{R_2} = 0.0025 \text{ V}/\Omega$.
   - Result: $V_{out} = 5.0 \text{ V}, u_c \approx 0.043301 \text{ V}$.
4. **Case D: Perfect Correlation ($r = \pm 1$)**:
   - $r = +1 \implies u_c = u_1 + u_2 = 0.3 \text{ V}$.
   - $r = -1 \implies u_c = |u_1 - u_2| = 0.1 \text{ V}$.
5. **Case E: Type A from Observations**:
   - Evaluates sample mean, sample variance, standard error, and degrees of freedom $n - 1$.
6. **Case F: Type B Rectangular**:
   - Tolerance $\pm a \implies u = a / \sqrt{3}, \nu = \infty$.
7. **Case G: Type B Triangular**:
   - Tolerance $\pm a \implies u = a / \sqrt{6}, \nu = \infty$.
8. **Case H: Type B Normal**:
   - Calibration $U$ with factor $k \implies u = U / k$.
9. **Case I: Welch-Satterthwaite with Finite & Infinite Degrees of Freedom**:
   - Verified exact formula matching analytical fractions with zero division avoidance on infinite terms.
10. **Case J: Small $\nu_{\text{eff}}$ Producing $k \neq 2$**:
    - For $\nu_{\text{eff}} = 4$ at $95\%$ confidence, $k \approx 2.78 \neq 2.0$.

---

## 5. Verification Summary (Initial Submission)
- **F7-B7 Unit & Analytical Tests**: 30 passed in `tests/test_f7b7_gum.py`.
- **All F7 Test Suites**: 148 passed (`test_f7a_runtime.py`, `test_f7b1`..`test_f7b7`).
- **Full Repository Suite**: 353 passed, 2 skipped, 0 failed.

---

## 6. Post-Audit Hardening

Following independent audit review, the GUM engine underwent targeted hardening addressing two obligatory requirements and two recommended improvements with zero regressions and zero external dependencies.

### A. Finding 1 (Obligatory): Positive Semi-Definite (PSD) Validation of CorrelationMatrix
- **Problem Found**: `CorrelationMatrix` validated element bounds $r \in [-1, 1]$, symmetry $r_{ij} = r_{ji}$, and diagonal unity $r_{ii} = 1$, but did not verify that the matrix is positive semi-definite (PSD). A symmetric matrix with valid diagonals and bounds can possess negative eigenvalues and thus represent a mathematically impossible joint distribution.
- **Implemented Solution**: Developed a pure Python standard library real symmetric eigenvalue solver based on the classical Jacobi rotation method (`jacobi_eigenvalues`). Added `CorrelationMatrix.validate_psd(variables, tol)` which constructs the $n \times n$ correlation matrix, evaluates all real eigenvalues deterministically, and validates $\min(\lambda_i) \ge -\text{tol}$.
- **Chosen Tolerance**: $\text{tol} = 10^{-7}$. Real symmetric correlation matrices with unit diagonal exhibit roundoff errors on the order of $\mathcal{O}(n \cdot \varepsilon_{\text{mach}}) \approx 10^{-15}$. The tolerance $10^{-7}$ provides numerical headroom for rank-deficient or collinear matrices with true zero eigenvalues (e.g. perfect correlation with $\lambda=0$) while decisively rejecting inconsistent non-PSD matrices (whose negative eigenvalues are typically $\ge 10^{-4}$).
- **Automatic Enforcement**: Validation runs automatically in `CorrelationMatrix.__post_init__()` upon dictionary/pair initialization, and in `evaluate_gum()` across all active model variables prior to covariance calculation.
- **Tests Added**:
  - Test A: 3x3 identity matrix $\to$ PASS.
  - Test B: Valid correlation matrix ($r_{12}=0.5, r_{13}=0.2, r_{23}=0.3$) $\to$ PASS ($\lambda_{\min} \approx 0.487$).
  - Test C: Perfect positive correlation ($r_{12}=1$) $\to$ PASS ($\lambda \in \{0, 2\}$).
  - Test D: Perfect negative correlation ($r_{12}=-1$) $\to$ PASS ($\lambda \in \{0, 2\}$).
  - Test E: Symmetric but non-PSD matrices ($r_{12}=0.9, r_{13}=0.9, r_{23}=0.0$ and $r_{12}=0.8, r_{13}=0.8, r_{23}=-0.8$) $\to$ REJECT (`ValueError`).
  - Test F: $r > 1$ $\to$ REJECT (`ValueError`).
  - Test G: $r < -1$ $\to$ REJECT (`ValueError`).
  - Test H: Diagonal $r_{ii} \neq 1$ $\to$ REJECT (`ValueError`).
  - Test I: Rank-2 matrix with true zero eigenvalue $\to$ PASS within $10^{-7}$ tolerance.
  - Integration: `evaluate_gum` rejects non-PSD matrices before computing variance.

### B. Finding 2 (Obligatory): Real Dimensional Validation in MeasurementModel
- **Problem Found**: `MeasurementModel.evaluate()` previously coerced all inputs to dimensionless `parse_unit("1")`, treating `output_unit` merely as a display string and bypassing physical unit algebra.
- **Implemented Solution**: Integrated the certified F6 unit system (`units.py`, `calc.py`, `equations.py`). Each `InputQuantity` enters the parsed equation AST with its real physical unit (`Quantity(nominal_value, parse_unit(unit))`). Added `MeasurementModel.evaluate_to_quantity()` which enforces strict dimensional compatibility during evaluation:
  - Additions and subtractions must have identical physical dimensions (e.g. $V + V$ is valid, but $V + s$, $V + A$, $A + \Omega$ are rejected with `UnitError`).
  - Products and quotients compute derived dimensions ($V / \Omega \to A$, $V \cdot A \to W$, $V / A \to \Omega$).
  - If declared `output_unit` is present, the calculated dimension is validated against `output_unit.dimension`, raising `UnitError` on mismatch and scaling exact factors (e.g. $\text{mV} \to \text{V}$) when compatible.
  - If `output_unit` is unspecified, the measurand preserves the calculated unit (`measurand_unit = q_res.unit.display`).
- **Tests Added**:
  - Test 1: $X_1 = 10\text{ V}, X_2 = 2\ \Omega, Y = X_1 / X_2 \implies 5\text{ A}$ (`measurand_unit = "A"`).
  - Test 2: $X_1 = 2\text{ V}, X_2 = 3\text{ A}, Y = X_1 \cdot X_2 \implies 6\text{ W}$ (`measurand_unit = "W"`).
  - Test 3: $X_1 = 10\text{ V}, X_2 = 2\text{ A}, Y = X_1 / X_2 \implies 5\ \Omega$ (`measurand_unit = "Ω"`).
  - Test 4: Incompatible addition $V + s \implies$ REJECT (`UnitError`).
  - Test 5: Incompatible addition $V + A \implies$ REJECT (`UnitError`).
  - Test 5b: Incompatible addition $A + \Omega \implies$ REJECT (`UnitError`).
  - Test 6: Declared `output_unit` incompatible with calculated dimension $\implies$ REJECT (`UnitError`).
  - Test 7: Declared `output_unit` matching calculated dimension $\implies$ PASS.
  - Test 8: Compatibility confirmed with all existing GUM equations.

### C. Finding 3 (Recommended): Precision of Numerical Sensitivity
- **Problem Found**: Numerical sensitivity differentiation applied an arbitrary truncation: `round(float(c_num), 9)`, which artificially discarded available precision.
- **Implemented Solution**: Eliminated `round(float(c_num), 9)`. Retained exact `Decimal` arithmetic: $c_{\text{num}} = (y_+ - y_-) / (2 \cdot h)$, preserving full available precision without artificial truncation.
- **Tests Added**: Validated numerical sensitivity for higher-order nonlinear functions ($Y = X^3 / 7$), verifying $>9$ significant decimal digits matching analytical derivative without truncation.

### D. Finding 4 (Recommended): Strict Validation of explicit_k & Provenance Distinctions
- **Problem Found**: `explicit_k` did not explicitly validate positivity ($k > 0$) or filter non-physical inputs ($k \le 0$, $\text{NaN}$, $\pm\infty$).
- **Implemented Solution**: Validated that `explicit_k` is finite and strictly positive ($k > 0$). Raised `ValueError` on $k \le 0$, $\text{NaN}$, $\pm\infty$. Enforced provenance distinction in `coverage_factor_source`:
  - `"explicit_user"`: explicitly provided by caller.
  - `"student_t"`: dynamically computed from Welch-Satterthwaite finite $\nu_{\text{eff}}$.
  - `"normal_limit"`: standard normal approximation for infinite $\nu_{\text{eff}} = \infty$.
- **Type B Normal Default**: Documented $k=2$ in `InputQuantity.from_normal()` as an explicit user/model assumption for standard 95.45% normal calibration certificates, recorded in the quantity provenance.

---

## 7. Hardened Verification Summary
- **F7-B7 Hardened Suite (`tests/test_f7b7_gum.py`)**: 56 passed (increased from 30 to 56 tests).
- **Full F7 Engineering Regression (`tests/test_f7*.py`)**: 174 passed (increased from 148 to 174 tests).
- **Full Repository Suite (`pytest -q`)**: 379 passed, 2 skipped, 0 failed (increased from 353 to 379 tests).

---

## 8. Final Post-Audit Remediation (commit `fix(engineering): finalize F7-B7 unit-system hardening`)

A second independent audit found an architectural defect in the Finding-2 hardening above: `gum.py::_resolve_unit()` fell back to fabricating a **synthetic dimension** (a `SHA-256` hash of the unit string folded into the luminous-intensity exponent) whenever `parse_unit()` did not recognize a symbol. This let arbitrary unknown strings (e.g. `"mm"`, or any typo) silently resolve to a self-consistent but physically meaningless dimension, defeating the entire purpose of dimensional validation. This remediation removes that fallback and closes the underlying gap that motivated it.

### 8.1 Synthetic fallback: found and eliminated
- **File**: `src/academic_core/domain/engineering/gum.py`.
- **Before**: `_resolve_unit(symbol)` called `parse_unit(symbol)`, and on `UnitError` computed `h = int(hashlib.sha256(symbol...).hexdigest()[:8], 16)` and returned `Unit(symbol, symbol, "", (0,0,0,0,0,0,h), Decimal(1))` — an invented dimension in the (unused) luminous-intensity slot.
- **After**: `_resolve_unit(symbol)` maps only the empty string / `"1"` to the dimensionless unit; every other symbol is resolved exclusively via `parse_unit()` (`units.py`), and `UnitError` propagates unmodified. No hash, no fabricated dimension, no fallback path of any kind.
- **Impact**: `MeasurementModel.evaluate_to_quantity()` and `get_sensitivity()` (the only callers of `_resolve_unit`) now reject any input/output unit unknown to F6's `units.py` with a `UnitError`, instead of silently accepting it.

### 8.2 Root cause: F6 had no LENGTH dimension
The synthetic fallback existed because the GUM test suite (and real measurement workflows) use `"mm"` for length quantities, and F6's `units.py` had no length dimension or `m`/`mm`/`cm`/`km` units — so `parse_unit("mm")` genuinely failed. Rather than route around this in GUM, F6 was extended, which is the correct layer per the single-source-of-truth architecture (`MeasurementModel` → `units.py` → `Quantity` → `equations.py` → dimensional validation).

### 8.3 F6 `units.py` extension: LENGTH dimension
- Added `LENGTH = (0, 1, 0, 0, 0, 0, 0)` (SI base exponent tuple: mass, **length**, time, current, temperature, amount, luminous intensity) and registered it in `DIM_NAMES` as `"length"`.
- Added base unit `"m": (LENGTH, "1")` to `_BASE_UNITS`, appended after the existing electrical units so the base-symbol matching loop (which prefers longer/earlier-registered symbols) continues to resolve `"s"`, `"V"`, etc. before falling through to `"m"` — no ambiguity, no regression.
- Added SI prefix `"c": "-2"` (centi) to `PREFIXES`, needed for `cm`; the existing prefix-matching logic in `parse_unit()` already generalizes to any base unit, so `mm`, `cm`, and `km` all resolve automatically once `m` is a registered base and `c` is a registered prefix — no unit-specific special-casing was added.
- All factors are exact `Decimal` powers of ten (`Decimal(10) ** int(PREFIXES[prefix])`), consistent with the rest of `units.py`; no floats cross the unit-resolution boundary.

Verified factors:
| Unit | Dimension | Factor to base (m) |
|---|---|---|
| `m`  | LENGTH | `1` |
| `mm` | LENGTH | `10^-3` |
| `cm` | LENGTH | `10^-2` |
| `km` | LENGTH | `10^3` |

### 8.4 Unknown units are rejected, not fabricated
`parse_unit("unknown_unit")`, `MeasurementModel` with `unit="unknown_unit"`, and `MeasurementModel` with `output_unit="unknown_unit"` all raise `UnitError`. There is no remaining code path in `gum.py` that creates a `Unit` with an invented dimension — confirmed by grepping the module for `synthetic`, `hashlib` (unit context), and every `Unit(`/`_resolve_unit(` call site (see §8.7).

### 8.5 New dimensional tests (Finding 7, Tests A–L)
Added `TestLengthDimensionAndNoSyntheticUnits` to `tests/test_f7b7_gum.py` (12 new tests, one per required case):
- **A**: `parse_unit("m").dimension == parse_unit("mm").dimension == parse_unit("cm").dimension == parse_unit("km").dimension == LENGTH`.
- **B**: `Quantity(1, m).convert_to("mm") == 1000 mm`.
- **C**: `Quantity(1, mm).convert_to("m") == 0.001 m`.
- **D**: `Quantity(100, mm).convert_to("m") == 0.1 m`.
- **E**: `parse_unit("unknown_unit")` → `UnitError`.
- **F**: `MeasurementModel` with input `unit="unknown_unit"` → `UnitError` via `evaluate_gum`.
- **G**: `MeasurementModel` with `output_unit="unknown_unit"` → `UnitError` via `evaluate_gum`.
- **H**: `X = 100 mm`, `Y = X / 2` preserves the LENGTH dimension and the `mm` unit in the budget row.
- **I**: Same as H with `output_unit="m"` → correctly converts to `0.05 m`.
- **J**: `1 mm + 1 s` → `UnitError` (cross-dimension, LENGTH vs TIME).
- **K**: `1 mm + 1 V` → `UnitError` (cross-dimension, LENGTH vs VOLTAGE).
- **L**: `1 m + 100 mm == 1.1 m` (same-dimension addition, unit conversion respected).

The pre-existing tests that already used `unit="mm"` (`test_type_b_triangular`, `test_case_e_type_a_evaluation_from_observations`) were **not modified** — they now exercise the real LENGTH dimension end-to-end instead of the old synthetic fallback, and continue to pass unchanged.

### 8.6 PSD / sensitivity precision / explicit_k — reconfirmed, untouched
Per scope, Findings 1, 3, and 4 from the first hardening pass were reviewed and left as-is:
- `CorrelationMatrix.validate_psd()` still uses the pure-Python Jacobi eigenvalue solver, `tol = 1e-7`, and does not reference `_resolve_unit`, `parse_unit`, or any unit type — confirmed independent of the unit system.
- Numerical sensitivity (`get_sensitivity`) still returns the full undivided `Decimal` value with no `round()` call.
- `explicit_k` still rejects `k <= 0`, `NaN`, and `±Inf`, and `coverage_factor_source` still distinguishes `explicit_user` / `student_t` / `normal_limit`.

### 8.7 Architecture review (required greps)
```
grep -rn "synthetic" src/academic_core/domain/engineering/gum.py   -> only a docstring stating none exists
grep -n "_resolve_unit" gum.py                                     -> def + 3 call sites, all delegate to parse_unit
grep -n "hash" gum.py (unit context)                                -> none; hashlib remains for provenance CAS hashing only
grep -n "Unit(" gum.py                                              -> only the dimensionless "1" literal construction
```
No synthetic units. No hash-derived dimensions. No fallback dimensional system. `units.py::parse_unit()` is the sole unit-resolution authority.

### 8.8 Final regression results
- `tests/test_f7b7_gum.py`: **68 passed** (56 → 68, +12 for Finding 7).
- `tests/test_f7*.py`: **186 passed** (174 → 186).
- Full suite (`pytest -q`): **391 passed, 2 skipped** (pre-existing `reportlab`-absent skips, unrelated), **0 failed**.

