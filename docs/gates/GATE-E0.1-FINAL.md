# GATE E0.1 — Explainable Execution Expansion — FINAL

Design: [GATE-E0.1-DESIGN.md](GATE-E0.1-DESIGN.md).

```text
E0.1 FINAL REPORT
```

## Baseline

- **Start:** `e519976` (`cert: certify E0 explainable execution`), with
  `HEAD == origin/main` and a clean tree.
- **Implementation commits:**
  - `c8464ed` feat(core): expand explainable execution with pedagogical
    steps
  - `f582c98` feat(engineering): integrate explainable solver steps
  - `bd32ef5` feat(ui): show pedagogical execution steps
- **E0 was not reopened.**
  - The `execution-trace/1` schema is unchanged.
  - The golden `voltage_divider.json` is byte-identical (test `x02`).
  - The E0 suite passes: 71/71.
  - The «Explicar» button keeps its E0 trace. The pedagogical mode is a
    separate «Paso a paso» button.

## Derivatives

- **Rules**, all recorded in their real sub-steps:
  - constant, variable, sign change, sum, difference, constant factor
  - product: identify u, v → u′ → v′ → substitute
  - quotient: the same
  - power d/dx xⁿ = n·xⁿ⁻¹, with `n = …` bound
  - chain: identify outer and inner → derive outer → derive inner →
    substitute
  - table: sin, cos, tan, exp, log, sqrt, abs
  - aᵘ with a constant base a
- **Simplification is a named step:** before → rules → after.
- **Checks:**
  - normal-form equivalence of the raw and the simplified derivative
  - central difference (h = 1e-6, relative tolerance 1e-9) at
    0.7 / 1.3 / 2.9 through the certified evaluator
  - NOT_APPLICABLE when there are free parameters
- **uᵛ with both parts variable** gives `NO_RULE` (AC-UNS-001). The
  steps done before it are kept.

## Integrals

- **Rules:**
  - constant, linearity, sign, constant factor
  - power (n = −1 gives log|x|)
  - table: sin, cos, exp, tan, sqrt
- **Change of variable, linear and general:** choose u → du, using the
  derivation engine's own steps → rewrite in u → integrate → undo.
- **By parts (LIATE):** log·xⁿ, and xⁿ·exp/sin/cos(ax+b). Repeated as
  needed; x²·sin x shows two applications.
- **Polynomial rewrite.** The normal form is rewritten, and the rewrite
  is recorded.
- **The + C step.**
- **Definite integrals** use Barrow's rule: F(b), F(a), then subtract.
  The result is exact when rational, else a Decimal from the certified
  evaluator. If the integrand is undefined in [a, b], the rule is
  refused (`DOMAIN`).
- **Failed tentative strategies** run on a scratch log and are never
  shown.
- **Checks:**
  - d/dx F ≡ f. Proven by normal form, or numeric (relative 1e-20)
    with the method stated.
  - Simpson n = 64 against Barrow (relative 1e-6).

## Equations

- **Linear, isolation:** state the equation → simplify each side →
  transpose the x term → transpose the constant → divide by the
  coefficient.
- **Zero coefficient:** a DECISION, identity or contradiction.
- **Check:** exact substitution into the original sides, e.g.
  `3*(-3) + 2 = -3 - 4` (both −7).
- **Non-linear equations** give `NO_RULE`.
- **Simplification** (`math.simplify`) records before → rule → after
  for every node that changes.

## Units

With `explain_equation(..., pedagogical=True)`, the steps are:

1. formula
2. data (NORMALIZATION)
3. «Conversión a unidades SI» (`Quantity.to_base()`, the conversion the
   evaluator uses in products and quotients)
4. «Sustitución»
5. calculation (the evaluator's observer)
6. result
7. checks

Example: `R2 = 2 kΩ = 2000 Ω`; `Vout = (12 V) * (2 kohm) / ((1 kohm) +
(2 kohm))`.

## Numerical methods

Iterations are shown only if they come from the real solver.

- **F8-N:**
  - `solve_nonlinear_dc(..., observer=None)`
  - Each Newton iteration is recorded: α (backtracking), halvings, step
    peak, residual blocks, node voltages, res_ok / step_ok.
  - Checks: the solver's conservation checks, and observed iterations
    = `provenance["iterations"]`. Example: diode, 10 iterations with
    α = 0.125, 0.5, 1, ….
- **F8-P:**
  - `margins(..., observer=None)`
  - Recorded: every bracket, every bisection midpoint (lo, hi, ω_mid,
    f(ω_mid)), and the stop reason (relative width ≤ 1e-12).
  - Checks: |L(jω_gc)| = 1 (1e-9), and ω_gc inside its bracket.
- **Hooks are neutral.** Without an observer the results are identical
  (tests `n03`, `c03`, `g05`). The whole F8-N / F8-P / GUM regression
  passes.

## GUM

- **Recorded:**
  - magnitudes (x_i, u, type, distribution, ν)
  - y with the substitution
  - one sensitivity per input, with the engine's method: the ANALYTIC
    pattern and its values, or NUMERICAL h, x ± h, f(x ± h), which are
    the engine's real evaluations
  - contributions c_i·u_i, (c_i·u_i)² and %
  - covariance
  - u_c², u_c, ν_eff, k (and its source), U
- **Checks:**
  - Σ(c_i·u_i)² + cov = u_c² (exact)
  - u_c² ≈ variance (1e-12)
  - U = k·u_c (exact)
  - Σ% consistency
  - c_i against the symbolic ∂f/∂x_i where comparable
- **Declared limitation:** a WARNING states that √ and ν_eff are float
  in the certified engine.

## F8-Q

- **Pedagogical causality** (opt-in `mode = pedagogical`; E0 captures
  unchanged): circuit → stimuli → gate evaluation → transition → driver
  → trigger → capture → verification.
  - A stimulus-driven transition is traced to its declared edge.
  - A gate-driven transition is traced to its settled observed inputs
    and the certified `DigitalComponent.evaluate`. It refs the input
    transitions at the same instant and records `consistent`.
  - Zero-delay intermediate states and unobservable inputs are WARNINGs.
    No cause is invented.
- **`explain_transition`** extracts the time, channel, previous, new,
  driver, why, cause and checks of one row.
- **The simulator is not duplicated.** The certified
  `engineering/digital` package is byte-identical to `0cf3554` (tests
  `e0_q03` and `e01_z05`).

## digital-circuit/1

- **Location:** `domain/engineering/digital_circuit.py`, outside the
  certified package.
- **Encoding:** canonical JSON with a sha256 digest. Decoding is strict
  (size, depth, duplicate keys, floats, NaN, unknown keys, order,
  version), and everything is rebuilt through the certified
  constructors.
- **Round trip:** all four demos round-trip byte-exactly, and captures
  on a decoded circuit give the same `digital-trace/1` digest.
- **The demo key is no longer needed.** Captures on documents record
  `circuit_digest`, and `ExplainService.replay(trace, document)`
  verifies it (`CIRCUIT_MISMATCH` / `MISSING_CIRCUIT`).

## UI

- **Exercises:**
  - «Paso a paso» (datos → fórmula → conversión → sustitución →
    cálculo → resultado → verificación)
  - a math row: Derivar / Integrar (with optional limits a, b) /
    Resolver ecuación / Simplificar
- **Logic Analyzer:** selecting a transition fills an explanation panel.
  It shows the time, channel, previous, new, driver, why, cause, checks
  and event ids. The panel uses one cached pedagogical trace per
  capture. A loaded file says that no cause can be given.
- **No pedagogy in widgets,** and no domain imports.

## Renderer

- **Lessons.** `ExplanationView.lessons` holds one lesson per non-INPUT
  event: Paso N / Tipo / Regla / Entrada / Transformación / Salida /
  Explicación / Verificación.
- **Verificación** lists the checks whose refs reach the event through
  the causal chain.
- **Output.** Text and Markdown render a «Paso a paso» block only when
  lessons exist, so E0 output is unchanged.

## Anti-fake-step

- Every engine step is exactly one STEP event, the same sequence (`f01`),
  and refs follow the engine's `uses` (`f02`).
- A modified step changes the digest, and replay gives
  `RESULT_DIFFERS` at that event (`f03`).
- A removed event is rejected on decode, or a renumbered forgery fails
  replay. Nothing is filled in (`f04`).
- Missing internal steps are reported as NO_RULE errors or WARNINGs:
  the GUM float, F8-Q delta states, unobservable inputs (`f05`).
- Lessons map 1:1 to event ids and copy only recorded text (`f06`).
- The renderer imports only the E0 core and does not mutate the trace
  (`f07`).

## Security / determinism

- **AST:** no eval, exec, compile, getattr, open, pickle, marshal,
  importlib, subprocess, os or sys in any new module (`z02`).
- **No float** in the symbolic engine (`z03`).
- **Layering:** engines never import `domain.execution`; the UI imports
  only the application layer (`z04`).
- **Determinism:** the digests of nine traces (math, GUM, Newton,
  margins, pedagogical capture) are identical across `PYTHONHASHSEED` =
  0 / 1 / 4242 / random in separate processes (`z01`).
- **Bounds** as in the design (§3, §6, §8).

## Tests

`tests/test_e01_explainable_expansion.py`: **113 passed**.

## Regression

| Suites | Result |
|---|---|
| E0 | 71/71 |
| F8-Q1..Q7 + F15 (Logic Analyzer, Virtual Lab, app) | 681 passed with E0 |
| architecture, AST, eng-security, resource-security, F5 security, GUM F7-B7, F8-O, F8-P1..P5, F8-H, F8-I, F8-K, F8-L, F8-M, F8-N, equations | 890 passed, 11 skipped |

`test_f8n_lab_valid::test_n110_git_clean_certified` runs `git status`
on `mna/`. It was red only while the optional observer hook in
`nonlinear.py` was uncommitted, and it is green after the commit.

**Full `pytest`:** 3201 passed, 134 skipped (environment-only skips), 0
failed, in 16 min 41 s, on `bd32ef5`.

## Known limitations

- **Symbolic coverage is bounded** (see the design §10). Anything outside
  the registered rules is `NO_RULE`, by design.
- **Normal-form equivalence** is sufficient, not necessary. Identities
  with log|·| or trigonometry are verified numerically, and the check
  says so.
- **F8-Q delta cycles.** The internal delta-cycle evaluation cannot be
  observed without touching the certified package. Intermediate
  same-instant states are declared, not explained.
- **GUM** with callable evaluators or sensitivities cannot be traced as
  data (`UNSUPPORTED`). √ and ν_eff remain float in the certified
  engine, and the trace says so.
- **Text limits.** F8-N circuits are limited to 200 lines of ≤ 500
  characters, because the E0 text limit is 512.

## Final commit

This certification commit (see `git log`).

## origin/main

`HEAD == origin/main`, clean tree (verified after the push).

## Final verdict

```text
E0.1 COMPLETE / CERTIFIED
```
