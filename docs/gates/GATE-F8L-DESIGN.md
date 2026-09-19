# GATE-F8L-DESIGN — Formal Architecture & Mathematical Specification for Transient Simulation (DAE)

## 1. HEADER & METADATA

- **Repository:** `Damaga2005/AcademicCore`
- **Normative Branch:** `main`
- **Current Certified State:**
  - F0–F7: CERTIFIED
  - F8-A → F8-K: CERTIFIED
  - F8-L: NEXT REGULATORY PHASE
- **Design Gate Status:** `F8-L DESIGN READY`
- **Document Type:** Formal Architectural & Mathematical Design Gate (Pre-Implementation)
- **Target Implementation:** Pure Decimal-native DAE Time-Domain Transient Solver

---

## 2. CURRENT CERTIFIED STATE & BASELINE

The repository has certified all previous circuit simulation phases:
- **F8-G:** Nonlinear MNA base infrastructure with strict Newton-Raphson line-search backtracking.
- **F8-H:** Shockley diode DC nonlinear solver.
- **F8-I:** Ebers-Moll BJT DC nonlinear solver (NPN/PNP).
- **F8-J:** Small-Signal AC linearizer around converged DC operating point.
- **F8-K:** Additional semiconductors (MOSFET Shichman-Hodges Level 1, JFET square-law, Zener breakdown, LED, Schottky, Photodiode).

All existing solvers operate strictly under **Decimal-native arithmetic** with zero binary float coercions in domain logic, zero dynamic execution (`eval`, `exec`, dynamic imports), and strict determinism.

---

## 3. SCOPE & NON-SCOPE

### In-Scope for F8-L
1. **Dynamic Linear Components:**
   - Capacitor ($C$): $I_C(t) = C \frac{\mathrm{d}V_C}{\mathrm{d}t}$
   - Inductor ($L$): $V_L(t) = L \frac{\mathrm{d}I_L}{\mathrm{d}t}$ with explicit auxiliary branch unknown in MNA.
2. **Implicit Integration Schemes:**
   - Backward Euler (BDF1): First-order $L$-stable implicit scheme (startup and robust stepping).
   - Trapezoidal Rule (TR): Second-order $A$-stable implicit scheme.
   - Gear / BDF2: Second-order $L(\alpha)$-stable scheme for stiff systems without trapezoidal ringing.
3. **Adaptive Timestep Engine:**
   - Local Truncation Error (LTE) mathematical estimator.
   - Timestep scaling with security factors ($\kappa \approx 0.85$), $\Delta t_{\min}$, $\Delta t_{\max}$.
   - Automatic retry on step rejection or Newton divergence.
4. **Initial Conditions (IC) & DAE Consistency:**
   - Explicit user-specified initial conditions ($V_C(0)$, $I_L(0)$).
   - Automatic DC operating point initialization (treating $C$ as open circuit, $L$ as short circuit).
   - DAE algebraic consistency checks at $t=0$.
5. **Coupled DAE-Newton Solver:**
   - Simultaneous solution of dynamic companion models and algebraic nonlinear device residuals ($D, Q, M, J$, etc.).
   - Pure Decimal-native companion matrix formulation.
   - Atomic transaction and history rollback on step rejection.

### Non-Scope for F8-L
- Frequency-dependent or transmission line components (distributed parameters).
- Parasitic device capacitances within semiconductor models (BSIM, Meyer, charge-conservation capacitance models deferred to device AC/transient extensions).
- Event-driven discrete simulation engines (VHDL-AMS / Verilog-A).
- Hardware-dependent timing assertions or wall-clock tolerances.
- Lossy inductors/capacitors internal series resistance ($R_s$ deferred as per F8-K).

---

## 4. DAE FORMULATION & MNA ARCHITECTURE

### 4.1 Global DAE System
An arbitrary nonlinear electrical network with dynamic elements is formalized as an implicit index-1 Differential-Algebraic Equation (DAE):

$$
\mathbf{F}(\mathbf{x}(t), \dot{\mathbf{x}}(t), t) = \mathbf{i}_{\text{alg}}(\mathbf{x}(t)) + \frac{\mathrm{d}}{\mathrm{d}t}\mathbf{q}(\mathbf{x}(t)) - \mathbf{s}(t) = \mathbf{0}
$$

For linear dynamic storage elements ($C$ and $L$), this simplifies to the semi-explicit descriptor form:

$$
\mathbf{G} \mathbf{x}(t) + \mathbf{C}_{\text{dyn}} \dot{\mathbf{x}}(t) + \mathbf{f}_{\text{nl}}(\mathbf{x}(t)) - \mathbf{s}(t) = \mathbf{0}
$$

where:
- $\mathbf{x}(t) = \begin{bmatrix} \mathbf{v}_n(t) \\ \mathbf{i}_b(t) \end{bmatrix} \in \mathbb{R}^{N + M}$: Vector of nodal potentials $\mathbf{v}_n$ and auxiliary branch currents $\mathbf{i}_b$ (voltage sources, inductors).
- $\mathbf{G} \in \mathbb{R}^{(N+M) \times (N+M)}$: Static conductance and interconnection MNA matrix.
- $\mathbf{C}_{\text{dyn}} \in \mathbb{R}^{(N+M) \times (N+M)}$: Dynamic storage matrix containing capacitance values and inductance flux link coefficients.
- $\mathbf{f}_{\text{nl}}(\mathbf{x}(t))$: Memoryless nonlinear device currents (Diodes, BJTs, MOSFETs, JFETs).
- $\mathbf{s}(t)$: Time-dependent independent source vectors (step, pulse, sine, DC).

---

## 5. DYNAMIC COMPONENT MODELS & COMPANION SCHEMES

### 5.1 Capacitor ($C$)
- **Pins:** `p`, `n` (Positive and negative terminals).
- **Physical Law:** $i_C(t) = C \frac{\mathrm{d} v_C(t)}{\mathrm{d}t}$ where $v_C(t) = v_p(t) - v_n(t)$.
- **Discretization (General Linear Multistep):**

  $$
  i_C(t_{n+1}) = G_{\text{eq}, C} v_C(t_{n+1}) - I_{\text{eq}, C}
  $$

- **MNA Stamp for Node $p$ and Node $n$:**

  $$
  \begin{array}{c|cc|c}
   & v_p & v_n & \text{RHS} \\
  \hline
  p & +G_{\text{eq}, C} & -G_{\text{eq}, C} & +I_{\text{eq}, C} \\
  n & -G_{\text{eq}, C} & +G_{\text{eq}, C} & -I_{\text{eq}, C}
  \end{array}
  $$

### 5.2 Inductor ($L$)
- **Pins:** `p`, `n`.
- **Physical Law:** $v_L(t) = v_p(t) - v_n(t) = L \frac{\mathrm{d} i_L(t)}{\mathrm{d}t}$.
- **MNA Formulation:** Inductors introduce an explicit auxiliary current variable $i_L$ (row and column $k$ in MNA).
- **Discretization:**

  $$
  v_p(t_{n+1}) - v_n(t_{n+1}) - R_{\text{eq}, L} i_L(t_{n+1}) - V_{\text{eq}, L} = 0
  $$

- **MNA Stamp:**

  $$
  \begin{array}{c|ccc|c}
   & v_p & v_n & i_L & \text{RHS} \\
  \hline
  p & 0 & 0 & +1 & 0 \\
  n & 0 & 0 & -1 & 0 \\
  k & +1 & -1 & -R_{\text{eq}, L} & +V_{\text{eq}, L}
  \end{array}
  $$

---

## 6. INTEGRATION ALGORITHMS (BE, TR, BDF2)

Let $h = t_{n+1} - t_n$.

### 6.1 Backward Euler (BDF1) — Order 1, $L$-stable
Approximates $\dot{x}_{n+1} \approx \frac{x_{n+1} - x_n}{h}$.
- **Capacitor Companion:**

  $$
  G_{\text{eq}, C} = \frac{C}{h}, \quad I_{\text{eq}, C} = \frac{C}{h} v_C(t_n)
  $$
- **Inductor Companion:**

  $$
  R_{\text{eq}, L} = \frac{L}{h}, \quad V_{\text{eq}, L} = -\frac{L}{h} i_L(t_n)
  $$
- **Local Error:** $\mathcal{O}(h^2)$, global error $\mathcal{O}(h)$. Ideal for discontinuity traversal and startup.

### 6.2 Trapezoidal Rule (TR) — Order 2, $A$-stable
Approximates $x_{n+1} - x_n \approx \frac{h}{2} (\dot{x}_{n+1} + \dot{x}_n)$.
- **Capacitor Companion:**

  $$
  G_{\text{eq}, C} = \frac{2C}{h}, \quad I_{\text{eq}, C} = \frac{2C}{h} v_C(t_n) + i_C(t_n)
  $$
- **Inductor Companion:**

  $$
  R_{\text{eq}, L} = \frac{2L}{h}, \quad V_{\text{eq}, L} = -\frac{2L}{h} i_L(t_n) - v_L(t_n)
  $$
- **Local Error:** $\mathcal{O}(h^3)$, global error $\mathcal{O}(h^2)$. Can exhibit trapezoidal ringing under severe stiff steps.

### 6.3 Gear / BDF2 — Order 2, $L(\alpha)$-stable
Employs two past steps ($t_n, t_{n-1}$) with step ratio $r = \frac{h_n}{h_{n-1}}$ where $h_n = t_{n+1} - t_n$:

$$
\dot{x}_{n+1} \approx \alpha_0 x_{n+1} + \alpha_1 x_n + \alpha_2 x_{n-1}
$$

For uniform step $h_n = h_{n-1} = h$:
$$
\alpha_0 = \frac{3}{2h}, \quad \alpha_1 = -\frac{2}{h}, \quad \alpha_2 = \frac{1}{2h}
$$
- **Capacitor Companion:**

  $$
  G_{\text{eq}, C} = \alpha_0 C, \quad I_{\text{eq}, C} = -C (\alpha_1 v_C(t_n) + \alpha_2 v_C(t_{n-1}))
  $$
- **Inductor Companion:**

  $$
  R_{\text{eq}, L} = \alpha_0 L, \quad V_{\text{eq}, L} = L (\alpha_1 i_L(t_n) + \alpha_2 i_L(t_{n-1}))
  $$
- **Property:** Strongly suppresses ringing on highly stiff networks.

---

## 7. LOCAL TRUNCATION ERROR (LTE) & ADAPTIVE TIMESTEPPING

### 7.1 Mathematical LTE Estimation
For variable timesteps, LTE is computed on dynamic state variables $\mathbf{y} = [v_C, i_L]^T$:
- **Between Predictor (Divided Differences) and Corrector (Solved Solution):**

  $$
  \text{LTE}_k = \left| \frac{y_{k, n+1} - y_{k, \text{pred}}}{c_{\text{method}}} \right|
  $$
- **Tolerance Criterion:**

  $$
  \text{Tol}_k = \text{abstol} + \text{reltol} \cdot \max(|y_{k, n+1}|, |y_{k, n}|)
  $$
- **Normalized Scaled Error Norm:**

  $$
  E = \max_k \left( \frac{\text{LTE}_k}{\text{Tol}_k} \right)
  $$

### 7.2 Step Acceptance and Timestep Adaptation
1. If $E \le 1.0$: **Step Accepted.**

   $$
   h_{\text{new}} = \min\left(h_{\max}, \; h \cdot \min\left(2.0, \; \max\left(0.1, \; 0.85 \cdot E^{-\frac{1}{p+1}}\right)\right)\right)
   $$

   where $p$ is the method order ($p=1$ for BE, $p=2$ for TR/BDF2).
2. If $E > 1.0$: **Step Rejected.**
   Rollback to $t_n$, propose:

   $$
   h_{\text{retry}} = \max\left(h_{\min}, \; h \cdot \max\left(0.1, \; 0.85 \cdot E^{-\frac{1}{p+1}}\right)\right)
   $$

   If $h < h_{\min}$, terminate with `TRANSIENT_TIMESTEP_TOO_SMALL`.

---

## 8. ROLLBACK ARCHITECTURE & TRANSACTIONAL HISTORY

A transient step proposal must never corrupt history before acceptance:

```
[History Pipeline]
Step n-1 (committed) -> Step n (committed) -> [Tentative Step n+1]
                                                    |
                                       +------------+------------+
                                       |                         |
                                  [Converged]              [Diverged/Rejected]
                                       |                         |
                                 LTE Check OK?             Rollback state
                                  /         \              Restore history
                              (Yes)         (No)           h = h * 0.5
                                |            |             Retry step
                           Commit n+1    Rollback
```

The state machine encapsulates:
- `commit_step(t, x, x_dot)`: Appends snapshot to immutable history ring buffer.
- `rollback()`: Discards tentative iteration vectors, restores previous state vectors without heap leakage.

---

## 9. SOURCES & TIME-DEPENDENT EXCITATIONS

The transient module requires deterministic evaluation of independent sources:
1. **DC:** Constant value $v(t) = V_{\text{dc}}$.
2. **Step:** $v(t) = V_1$ if $t < t_0$, else $V_2$.
3. **Pulse:** Defined by $V_1, V_2, T_{\text{delay}}, T_{\text{rise}}, T_{\text{fall}}, T_{\text{width}}, T_{\text{period}}$.
4. **Sinusoidal:** $v(t) = V_o + V_a \sin(2\pi f (t - t_d))$ evaluated using Taylor-series or high-precision Decimal coordinate rotations.

All time parameters are strictly instances of `Decimal`.

---

## 10. COMPATIBILITY & NONLINEAR COUPLING

Nonlinear devices ($D, Q, M, J$, Zener, LED, Schottky, Photodiode) are instantiated in each transient Newton iteration without modification:
- Static stamps update their respective Jacobian contributions: $\mathbf{J}_{\text{nl}}(\mathbf{x}_{n+1})$.
- Dynamic companion conductances contribute to the main diagonal: $\mathbf{J}_{\text{total}} = \mathbf{G}_{\text{MNA}} + \mathbf{G}_{\text{eq, dyn}} + \mathbf{J}_{\text{nl}}$.
- The existing Newton-Raphson line-search engine guarantees strict descent on each time point.

---

## 11. DETERMINISM, PRECISION & SECURITY GUARANTEES

1. **Decimal Precision:** All state variables, timestamps, conductances, voltages, currents, and LTE estimates are strictly `Decimal`. No binary IEEE-754 coercions.
2. **Zero Dynamic Execution:** 0 `eval`, 0 `exec`, 0 dynamic `__import__`, 0 network, 0 subprocess.
3. **Determinism:** Identical input topology, tolerances, and integration method produce identical solution trajectories bit-for-bit, independent of platform or run duration.

---

## 12. TEST & VALIDATION PLAN

1. **Analytical Benchmarks:**
   - **RC Circuit:** Discharging capacitor $v(t) = V_0 e^{-t/RC}$. Error versus exact analytical curve across 5 time constants $< 10^{-4}$.
   - **RL Circuit:** Step response $i(t) = \frac{V}{R}(1 - e^{-Rt/L})$.
   - **RLC Circuit:** Underdamped, critically damped, and overdamped oscillations compared with closed-form algebraic solutions.
2. **Nonlinear Transient Circuits:**
   - Half-wave rectifier (Diode + RC filter).
   - Inverter transient switching with MOSFET Shichman-Hodges.
   - BJT switching amplifier.
3. **Method Stability & Robustness:**
   - Trapezoidal ringing detection and BDF2 damping verification.
   - Timestep reduction on steep pulses.
   - Rollback validation on simulated convergence failures.

---

## 13. DEFINITION OF DONE & CERTIFICATION CHECKLIST

- [ ] DAE mathematical framework formally established.
- [ ] Capacitor and Inductor companion models defined.
- [ ] Backward Euler, Trapezoidal, and BDF2 formulas specified.
- [ ] LTE mathematical estimator and adaptive stepping policy finalized.
- [ ] Rollback and history isolation specified.
- [ ] Integration with F8-H/I/J/K verified.
- [ ] Pure Decimal-native compliance verified.
- [ ] Zero dynamic execution / security compliance verified.

---

## 14. FINAL VERDICT

```
VERDICT: F8-L DESIGN READY
```
