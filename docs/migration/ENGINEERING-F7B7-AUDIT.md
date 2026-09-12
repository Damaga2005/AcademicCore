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

## 5. Verification Summary
- **F7-B7 Unit & Analytical Tests**: 30 passed in `tests/test_f7b7_gum.py`.
- **All F7 Test Suites**: 148 passed (`test_f7a_runtime.py`, `test_f7b1`..`test_f7b7`).
- **Full Repository Suite**: 353 passed, 2 skipped, 0 failed.
