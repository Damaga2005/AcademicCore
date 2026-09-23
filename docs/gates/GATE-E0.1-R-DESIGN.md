# GATE E0.1-R+ — Certification hardening + limitation fixes — DESIGN

Baseline: `584c3c2` (E0.1 certified). `HEAD == origin/main`, clean tree.

Principle: REAL EXECUTION → OBSERVABLE FACTS → PEDAGOGICAL TRACE →
EXPLANATION. A limitation is closed only when the engine really exposes
the fact. Otherwise it stays `UNSUPPORTED` / `NO_RULE` /
`UNOBSERVABLE_INTERNAL_DELTA` / `KEEP_CERTIFIED_BEHAVIOR`.

## 1. Audit map (`git diff 0cf3554..HEAD`)

| Certified engine | Observer (optional, default `None`) | ExecutionTrace | Renderer |
|---|---|---|---|
| `gum.py` `get_sensitivity` / `evaluate_gum` | `sensitivity(name, method, rule, details)` | `execution/uncertainty.py` | lessons |
| `mna/nonlinear.py` damped Newton | `newton_start`, `newton_iteration` (+ R+: `x_prev`, `residual_prev`, `jacobian`, `dx`, `residual`) | `execution/newton.py` | lessons |
| `control/margins.py` bisection | `bracket`, `bisection` (+ R+: `f_lo`, `f_hi`, `new_lo`, `new_hi`, `width`), `refined` | `execution/control.py` | lessons |
| `engineering/digital` (Q1–Q7) | **none** (package unchanged) | `execution/digital.py`: public `DigitalSimulator.step()` on an exact twin | lessons, transition panel |
| `equations._Eval` (E0) | `leaf` / `operation` (E0) | `execution/equation.py` | lessons |
| — (new in E0.1) | — | `engineering/symbolic` → `execution/symbolic.py` | lessons |

**No second implementation:**

- the symbolic engine is the only CAS
- numeric verification goes through the certified `equations.evaluate`
- `digital_circuit.py` contains no gate logic (tested)
- the delta run executes the certified simulator; it is not a re-simulation

## 2. Observer hardening

- **Snapshots are immutable:** tuples of `Decimal` / `str` / `bool` /
  `int`. They are built only when an observer is present.
- **Equivalence tests:** `observer=None` vs a recording observer on
  - GUM: 8 models (sum, product, quotient, numerical, correlated, zero
    sensitivity, zero uncertainty, all zero)
  - F8-N: 2 circuits, plus the error and `MAX_ITERATIONS` paths
  - F8-P: 5 loops, plus the error path
- **Compared:**
  - results, errors, provenance and diagnostics
  - the order and count of the calls
  - determinism across runs and across processes / hash seeds
- **The recorded F8-N snapshot is the real linear solve.** `J·Δx = −F`
  and `x_(k+1) = x_k + α·Δx` hold on the recorded values at the solver's
  precision.

## 3. Limitation decisions

| L | Decision | How |
|---|---|---|
| L1 symbolic bounded | FIXED (extended), bounded by design | ∫aˣ, ∫1/cos²u, √u → u^(1/2) (recorded rewrite), named neutral elements (u+0, 1·u, 0·u), cancellation with the condition "≠ 0" in its name, domain notes (tan, log, sqrt, abs). Anything else stays `NO_RULE`. |
| L2 symbolic vs numeric | FIXED | `execution/verification.py`: `verification_kind` = SYMBOLIC (normal-form proof or exact rational arithmetic) / NUMERIC (tolerance) / NONE. The label is a suffix of the check detail, so the schema is unchanged. The renderer shows it. |
| L3 GUM callable | FIXED (declarative path); callable INTENTIONALLY RETAINED | Equation model + constant sensitivities (inputs `c.<name>`) are data and fully traced. A callable evaluator or sensitivity is still computed by `evaluate_gum`, but its explanation is `UNSUPPORTED`: code is not data. |
| L4 F8-Q delta | FIXED (observational), fallback declared | Exact twin via `digital-circuit/1`. Public `step()` / `queue.size()` / `states()` / `fanout()`. After step i, `i + queue.size()` sequences are allocated, so the step that scheduled each event is exact. A CHECK proves the twin run equals the certified capture. Beyond `MAX_DELTA_STEPS`, or on mismatch: `UNOBSERVABLE_INTERNAL_DELTA` WARNING and stable-instant causality. `engineering/digital` is untouched. |
| L5 F8-N limits | FIXED (configurable), bounded | The limits belong to the transport (one INPUT per line; texts ≤ 512; ≤ 256 inputs), not to the solver. `max_lines` / `max_line_length` / `max_total_chars` are configurable within ceilings 250 / 512 / 128 250. The defaults stay 200 / 500 / 20 000. |
| L6 GUM float | INTENTIONALLY RETAINED (KEEP_CERTIFIED_BEHAVIOR) + audited | `decimal_audit` recomputes √ and Welch–Satterthwaite in Decimal (50 digits) from the certified budget. Two CHECKs measure the difference (tolerances 1e-15 / 1e-12). Measured: u_c ≤ 6·10⁻¹⁷, ν_eff ≤ 2.2·10⁻¹⁶ relative. Replacing the engine values would change certified outputs, so it is not done. |
| L7 trace entry points | FIXED | Equation, GUM (declarative), F8-N (`explain_nonlinear_circuit(Circuit)`), F8-P (`explain_margins_tf(TransferFunctionTF)`), F8-Q (demo, document, delta). Opaque objects (non-Quantity parameters, callables) are refused, not guessed. |

## 4. Pedagogy improvements (real data only)

- **F8-N iteration:**
  - x_k, F(x_k), the Jacobian J(x_k) the solver factorised, Δx, α,
    x_(k+1), ‖F‖ blocks, ‖αΔx‖∞, res_ok and step_ok
  - up to 4 unknowns; above that, "detalle omitido" (a display bound)
  - a continuity CHECK
- **F8-P bisection:**
  - [lo, hi], ω_mid, f(lo), f(ω_mid), f(hi) *when the engine computed
    it* (phase: "no calculado por el motor")
  - the sign condition, the new interval, the engine's relative width,
    and the stop reason
- **Units: only the conversions the evaluator executes.**
  - `to_base` of the operands of `*` and `/`, the base of `**`, and
    function arguments
  - `convert_to` of the right operand of `+` / `-` when the units differ
  - each conversion is consumed by its operation
  - This corrects an E0.1 defect: E0.1 showed one conversion per
    prefixed input, even when the evaluator never converted it.

## 5. E0 / E0.1 compatibility

- **E0 is unchanged:** golden fixture, digest, serialization, replay and
  «Explicar» (71 tests).
- **E0.1:** 113 tests.
  - Two assertions encoded exactly what R+ corrects, and were made
    stricter:
    - `e01`: the check detail now carries its verification label
    - `x01`: R1's non-executed conversion must NOT appear; the executed
      conversions (R2, R1 + R2) must, and each is consumed by its
      operation
  - No test was removed, skipped or loosened.
- **Delta causality is a separate mode** (`mode = pedagogical-delta`).
  The E0.1 pedagogical mode keeps its behaviour.
