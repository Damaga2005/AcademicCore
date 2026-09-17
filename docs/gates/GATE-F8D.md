# Quality Gate & Technical Specification: F8-D General AC / Phasor Linear Circuit Analysis

## 1. Executive Summary

- **Phase**: F8-D — General AC / Phasor Linear Circuit Analysis
- **Scope**: Steady-state sinusoidal AC analysis of linear networks containing ideal resistors ($R$), inductors ($L$), capacitors ($C$), and independent sinusoidal voltage ($V$) and current ($I$) sources at a single operating frequency $\omega > 0$.
- **Baseline**: Builds upon certified F6 (`engcircuit/6.0`), F8-B (`mna`), and F8-C (`thevenin`), preserving all previous capabilities without modification.
- **Specification Status**: **F8-D-A HARDENED SPECIFICATION**

---

## 2. Mathematical Domain & Operating Regimes

### 2.1 Domain Declarations
- **Regime**: Steady-state sinusoidal regime (phasor domain).
- **Frequency**: Single excitation frequency per solve, specified via `OperatingPoint`:
  $$\omega = 2\pi f > 0 \quad (\text{angular frequency in rad/s, frequency in Hz})$$
- **Passive Components**: Ideal linear $R > 0, L > 0, C > 0$ with constant frequency-independent parameters.
- **Active Components**: Independent AC sinusoidal voltage ($V$) and current ($I$) sources.
- **Topologies**: Arbitrary connected planar and non-planar graphs, multiple nodes, parallel multigraph branches, arbitrary meshes, single reference ground node.

### 2.2 Explicit Non-Goals & Excluded Domains
- Multi-frequency simultaneous excitation (intermodulation, harmonics).
- Nonlinear and semiconductor components ($D, Q$, op-amps, MOSFETs).
- Coupled inductors ($M$), transformers, and transmission lines.
- Time-domain transient response ($v(t), i(t)$ differential equation time-stepping).
- Frequency sweeps / Bode plots (covered by F7-B4 ngspice / F7-B6).

---

## 3. Numeric Models: Exact vs. High-Precision

The solver strictly segregates exact algebraic computation from numerical approximation:

| Dimension | `NumericMode.EXACT` | `NumericMode.HIGH_PRECISION` |
| :--- | :--- | :--- |
| **Algebraic Field** | Gaussian Rationals $\mathbb{Q}(j)$ | High-Precision Complex $\mathbb{C}[\text{Decimal}]$ |
| **Numeric Types** | `(re: Fraction, im: Fraction)` | `(re: Decimal, im: Decimal)` with 50 guard digits |
| **Entry Conditions** | $\omega \in \mathbb{Q}$ (`rad/s`), $R,L,C \in \mathbb{Q}$, source phases $\phi \in \{0^\circ, 90^\circ, 180^\circ, 270^\circ\}$ | Frequency in $\text{Hz}$ ($\omega = 2\pi f$), source phases $\phi \in \{30^\circ, 45^\circ, \dots\}$ |
| **Zero Test** | Exact: $z == 0 \iff \operatorname{re}(z) == 0 \land \operatorname{im}(z) == 0$ | Numerical: $|z| \le \tau_{\text{sing}}$ on normalized matrix |
| **Elimination** | Exact Gauss-Jordan (lossless) | Gauss-Jordan with partial pivoting by maximum modulus |
| **Rank** | Exact integer matrix rank | Numerical rank based on pivot decay thresholds |
| **Conservation Residuals** | Identically $0 + j0$ | Bounded: $\le \tau_{\text{tol}}$ on dimensionless system |
| **Status Possibilities** | `SOLVED`, `SINGULAR`, `INCONSISTENT` | `SOLVED`, `SINGULAR`, `INCONSISTENT`, `NUMERICALLY_UNCERTAIN` |

**Honest Precision Rule**: An approximation is never converted into a `Fraction` to claim exactness. Every solve explicitly declares its `numeric_mode` in the result and provenance.

---

## 4. Dimensionless MNA Scaling & Invariance

To eliminate physical heterogeneity across admittance rows ($\Omega^{-1}$) and voltage rows ($V$), a two-sided diagonal equilibration is applied:

1. **Characteristic Scales**:
   $$Z_0 = \operatorname{median}(\{|\tilde{Z}_k| : \text{all passive components } k\}), \quad Y_0 = \frac{1}{Z_0}$$
   $$V_0 = \max(1\text{ V}, \max_k |\tilde{V}_{s, k}|), \quad I_0 = \frac{V_0}{Z_0}$$
2. **Normalized Dimensionless System**:
   $$\mathbf{A}_{\text{norm}} = \mathbf{D}_L \mathbf{A} \mathbf{D}_R, \quad \mathbf{x} = \mathbf{D}_R \mathbf{x}_{\text{norm}}, \quad \mathbf{b}_{\text{norm}} = \mathbf{D}_L \mathbf{b}$$
   $$\mathbf{A}_{\text{norm}} = \begin{pmatrix} \frac{1}{Y_0} \mathbf{Y} & \mathbf{B} \\ \mathbf{C} & \mathbf{0} \end{pmatrix} \in \mathbb{C}^{M \times M} \quad (\text{strictly dimensionless entries } O(1))$$
3. **Scaling Invariant Properties**:
   - The scaling is strictly reversible: $\mathbf{x} = \mathbf{D}_R \mathbf{x}_{\text{norm}}$.
   - The physical solution $\mathbf{x}$ is invariant to unit representations ($\Omega \leftrightarrow \text{k}\Omega$, $\text{V} \leftrightarrow \text{mV}$).
   - Numerical pivot decisions are invariant to physical impedance magnitude.

---

## 5. Rank Determination & Rouché-Capelli Theorem

The solvability of the circuit is classified strictly via the augmented matrix rank:
$$\operatorname{rank}(\mathbf{A}_{\text{norm}}) \quad \text{and} \quad \operatorname{rank}([\mathbf{A}_{\text{norm}} \mid \mathbf{b}_{\text{norm}}])$$
evaluated using identical normalization, pivoting, and tolerance thresholds:

1. **`SOLVED` (Unique Physical Solution)**:
   $$\operatorname{rank}(\mathbf{A}_{\text{norm}}) = \operatorname{rank}([\mathbf{A}_{\text{norm}} \mid \mathbf{b}_{\text{norm}}]) = M$$
2. **`SINGULAR` (Indeterminate / Infinitely Many Solutions)**:
   $$\operatorname{rank}(\mathbf{A}_{\text{norm}}) = \operatorname{rank}([\mathbf{A}_{\text{norm}} \mid \mathbf{b}_{\text{norm}}]) < M$$
3. **`INCONSISTENT` (Contradictory Constraints / No Solution)**:
   $$\operatorname{rank}(\mathbf{A}_{\text{norm}}) < \operatorname{rank}([\mathbf{A}_{\text{norm}} \mid \mathbf{b}_{\text{norm}}])$$
4. **`NUMERICALLY_UNCERTAIN` (Ambiguous Numerical Evidence in HIGH_PRECISION)**:
   - Evaluated using the **`pivot_separation_indicator`**:
     $$\Pi = \frac{\min_{k} |p_k|}{\max_{k} |p_k|}$$
   - If a normalized pivot $|p_k|$ falls within the uncertainty guard band $[\tau_{\text{sing}}, \tau_{\text{unc}}]$ (where $\tau_{\text{sing}} = 10^{-35}, \tau_{\text{unc}} = 10^{-20}$), the system returns `NUMERICALLY_UNCERTAIN` rather than making an uncertified binary classification.

---

## 6. Structural Connectivity vs. Algebraic Solvability

- **Structural Validation (Pre-Solve)**:
  Verifies graph connectivity, presence of a unique ground reference (`0` or `GND`), and component validity. A disconnected network raises `INVALID_TOPOLOGY`.
- **Algebraic Solvability (Post-Assembly)**:
  `connected graph` $\neq$ `guaranteed nonsingular MNA`.
  - *Example of Connected yet Singular Circuit*: Two ideal voltage sources with identical phasors ($\tilde{V}_1 = \tilde{V}_2 = 10\angle 0^\circ\text{ V}$) connected in parallel between node `n1` and `0`. The graph is fully connected and valid, but KVL around the source loop leaves individual branch currents indeterminate ($\operatorname{rank}(\mathbf{A}) < M \implies$ `SINGULAR`).

---

## 7. Degenerate Parameter Policies

- **$R \le 0$**: `INVALID` parameter. Resistors must satisfy $R > 0$.
- **$L \le 0$**: `INVALID` parameter. Inductors must satisfy $L > 0$.
- **$C \le 0$**: `INVALID` parameter. Capacitors must satisfy $C > 0$.
- **$f = 0$**: `UNSUPPORTED for AC phasor mode`. Delegated to certified F8-B DC solver.
- **$f < 0$**: `OUT_OF_DOMAIN` / `INVALID` engineering boundary.

---

## 8. Resonance Semantics

- **Series $LC$**: $Z_s = j(\omega L - 1/(\omega C)) = 0\ \Omega$ at $\omega_0 = 1/\sqrt{LC}$.
  - With series resistor $R > 0$: $Z = R > 0 \implies$ full rank $\implies$ `SOLVED`.
  - Directly across ideal voltage source: KVL violation $\implies$ `INCONSISTENT`.
- **Parallel $LC$**: $Y_p = j(\omega C - 1/(\omega L)) = 0\ \Omega^{-1}$ at $\omega_0$.
  - Acts as open circuit $\implies$ full rank $\implies$ `SOLVED`.
- **Governing Rule**: Solvability is determined exclusively by the global MNA matrix rank, never by isolated branch subexpression shortcuts.

---

## 9. Verification & Conservation Laws

1. **Complex KCL**:
   $$\sum_{b \in \text{connected pins}} \tilde{I}_{b, \text{leaving}} = 0 + j0 \in \mathbb{C}$$
   verified across all nets including ground in Cartesian rectangular coordinates.
2. **Complex KVL**:
   $$\sum_{(n_i, n_{i+1}) \in \text{cycle}} (\tilde{V}_{n_i} - \tilde{V}_{n_{i+1}}) = 0 + j0 \in \mathbb{C}$$
   verified across all fundamental cycle chords on the circuit multigraph.
3. **Complex Power Conservation (Tellegen's Theorem)**:
   $$\sum_{k=1}^{N_{\text{branches}}} \frac{1}{2} \tilde{V}_k \tilde{I}_k^* = 0 + j0 \in \mathbb{C}$$
   evaluated with the factor $\frac{1}{2}$ adhering to canonical peak amplitude phasor convention.

---

## 10. External Oracle & Benchmarks

1. **ngspice 47 Oracle**: Real external verification using `.ac lin 1 <f> <f>` cross-checking peak magnitude, phase in degrees, and branch currents within documented tolerances.
2. **Independent Analytical References**: Minimum 12 hand-derived Cramer benchmarks ($R$-only, $RC$, $RL$, series $RLC$, parallel $LC$, Maxwell-Wien bridge, 3-node, 5-node planar mesh, multi-source phase offsets, non-GND ports).

---

## 11. Authorization Criteria for F8-D1

Phase F8-D1 may be authorized only when:
- [x] Mathematical specification complete and frozen.
- [x] Numeric mode boundaries strictly defined.
- [x] Two-sided diagonal equilibration formalized.
- [x] Rank and uncertainty classification formalized via Rouché-Capelli.
- [x] ngspice 47 AC peak convention empirically verified.
- [x] Zero regressions against baseline F0–F8-C (739 passed, 2 skipped).