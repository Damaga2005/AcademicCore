# Engineering Architecture & Audit: F8-C General Thevenin & Norton Analysis

## 1. Overview & Architectural Role

Phase **F8-C** implements the general two-terminal DC linear reduction engine (**Thevenin and Norton equivalents**) for Academic Core, directly building upon and consuming the certified **F8-B Modified Nodal Analysis (MNA)** solver without introducing any secondary linear solver or modifying F8-B code.

```
Canonical Circuit (F6: engineering/circuit.py)
      |
TheveninPort(A, B)           -- port validation (A != B, existence, reference check)
      |
mna._solve_exact(circuit)    -- F8-B exact MNA solve -> Vth = Va - Vb
      |
mna._solve_exact(c_vtest)    -- Deactivate (V->0V, I->open) + Vtest=1V (or Itest=1A fallback) -> Rth
      |
mna._solve_exact(c_sc)       -- Independent active short-circuit analysis (Vsc=0V) -> In = Isc
      |
Multi-load verification      -- Solve loaded original vs equivalent across standard test loads
      |
OnePortEquivalent (TheveninResult + NortonResult)
```

## 2. Fundamental Architectural Rule: Zero Solver Duplication

A core invariant of Academic Core is architectural minimalism: there is **no second linear solver**.
F8-C does not perform ad-hoc graph reductions, series-parallel resistor collapses, or matrix inversion loops. Every computation is performed by stamping the canonical `Circuit` through F8-B's `build_mna_problem` and solving it via `linear.solve_exact`.

- **Open-Circuit Voltage (Vth):** Solved by executing MNA on the active circuit: $V_{\text{th}} = V(A) - V(B)$.
- **Thevenin Resistance (Rth):** Evaluated on the deactivated circuit:
  - Independent voltage sources (V) are replaced by ideal 0 V sources (short circuit).
  - Independent current sources (I) are removed (open circuit).
  - A test source ($V_{\text{test}} = 1\text{ V}$) is connected across the port from A to B. The current delivered into the port $I_{\text{delivered}} = -I(V_{\text{test}})$ yields $R_{\text{th}} = 1 / I_{\text{delivered}}$.
  - If a zero-resistance path exists across the port ($V_{\text{test}}$ causes an inconsistency), a test current source ($I_{\text{test}} = 1\text{ A}$) is connected, measuring $V_{\text{drop}} = V(A) - V(B) = 0 \implies R_{\text{th}} = 0\ \Omega$.
- **Norton Current (In):** Computed independently by placing an ideal short-circuit voltage source ($V_{\text{sc}} = 0\text{ V}$) across the port on the active circuit, and solving for its branch current. In addition, when $R_{\text{th}}$ is finite and non-zero, it is cross-validated against $I_n = V_{\text{th}} / R_{\text{th}}$ over exact rationals $\mathbb{Q}$.
- **Multi-Load Verification:** For each load resistance $R_L \in \{0.1\ \Omega, 10\ \Omega, 100\ \Omega, 1000\ \Omega, 50000\ \Omega, 1\text{ M}\Omega\}$, an independent MNA problem is solved with $R_L$ connected across the original circuit, and terminal voltages and currents are compared against the equivalent model predictions.

## 3. Exact Rational Arithmetic vs. Presentation Precision

In accordance with Academic Core numerical principles:
- Internal calculations of $V_{\text{th}}$, $R_{\text{th}}$, $I_n$, and load verifications occur strictly over `fractions.Fraction` (lossless rational arithmetic).
- Conversion to `Decimal` (28 digits of precision) occurs only when wrapping results into `Quantity` objects for presentation and reporting.
- To prevent loss of precision during cross-validation, results maintain internal exact fields `_v_th_exact`, `_r_th_exact`, and `_i_n_exact`, guaranteeing that $V_{\text{th}} = I_n \cdot R_{\text{th}}$ holds identically over $\mathbb{Q}$.

## 4. Degenerate Case Handling

F8-C rigorously classifies port behavior without numerical fudge factors or arbitrarily large decimal approximations:
- **$R_{\text{th}} = 0\ \Omega$ (`ResistanceKind.ZERO`):** Occurs when an ideal voltage source or short-circuit path bridges the port. Norton current is classified as `EquivalentStatus.SHORT_CIRCUIT` (undefined/infinite).
- **$R_{\text{th}} = \infty$ (`ResistanceKind.INFINITE`):** Occurs when there is no conducting path between terminals in the deactivated network. Norton current is $I_n = I_{\text{sc}}$.
- **Singular Circuits (`EquivalentStatus.SINGULAR`):** Rank-deficient circuits (e.g. floating nodes, parallel identical voltage sources) correctly yield a singular status.
- **Inconsistent Circuits (`EquivalentStatus.INCONSISTENT`):** Contradictory circuits (e.g. ideal current sources forced into open-circuits without return paths, incompatible parallel voltage sources) yield an inconsistent status.
- **Invalid Port (`EquivalentStatus.INVALID_PORT`):** Port specification errors (same positive and negative terminal, or non-existent nets) are caught and rejected immediately.
- **Unsupported Elements (`EquivalentStatus.UNSUPPORTED`):** Any circuit containing components outside the linear DC domain (diodes, transistors, inductors, capacitors) is rejected via explicit abstention.

## 5. Provenance & Determinism

Every analysis result produces a canonical provenance record containing:
- Engine and version identifiers (`f8c-thevenin-norton/1.0`).
- Port designation and circuit component list.
- Deactivation and test-source methodologies.
- SHA-256 digest of the canonical analysis definition.
- Verification status across loads.

Timestamp fields are excluded from digest hashing to guarantee deterministic, idempotent provenance across repeated runs.

## 6. Scope & Explicit Limitations

- **Supported Domain:** DC linear resistive circuits with arbitrary topologies containing ideal resistors ($R$), independent voltage sources ($V$), and independent current sources ($I$), connected to a single ground reference node (`0` or `GND`).
- **Out of Scope (Explicit Abstention):**
  - Dependent sources (VCVS, VCCS, CCVS, CCCS) -- not present in canonical `Circuit.COMPONENT_PINS`.
  - Non-linear elements (diodes, BJTs, MOSFETs) -- rejected with `UNSUPPORTED`.
  - Dynamic/reactive elements ($C$, $L$) and AC analysis -- rejected with `UNSUPPORTED`.
  - Multi-port networks ($N \ge 3$ terminals) -- Thevenin/Norton applies strictly to two-terminal one-ports.
