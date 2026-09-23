# GATE E0.1 — Explainable Execution Expansion — DESIGN

Baseline: `e519976` (E0 certified). E0.1 extends E0; it does not reopen
it. The `execution-trace/1` schema, the E0 integrations' default output
and the E0 golden fixture are unchanged.

## 1. Audit (before implementing)

| Area | What exists | Consequence for E0.1 |
|---|---|---|
| Symbolic mathematics | None. "CAS" in the code base means *content-addressable storage*. The equation evaluator is numeric (Decimal + units). | There is no engine to reuse, so E0.1 adds ONE bounded, rule-based symbolic engine (`engineering/symbolic`). It is the only one, and it is not a second evaluator: numeric verification goes through the certified `equations.evaluate`. |
| F8-N (`mna/nonlinear.py`) | Damped Newton with backtracking; per-iteration facts (α, residual blocks, step peak, res_ok / step_ok). | An optional `observer=None` hook exposes those facts. The default path is bit-identical. |
| F8-P (`control/margins.py`) | Log scan and bisection on \|L(jω)\|−1 and Im L(jω). | An optional `observer=None` hook reports brackets, midpoints and the stop reason. |
| GUM (`gum.py`) | Budget rows already carry c_i, method, contributions, u_c, ν_eff, k and U. | An optional `observer=None` hook in `get_sensitivity` / `evaluate_gum` reports *how* each c_i was obtained (analytic pattern, or the central difference with h and f(x±h)). |
| F8-Q (`engineering/digital`) | Certified, and must stay byte-identical (`test_e0_q03`). The engine does not expose delta-cycle evaluation. | No hook is added. Causality comes from the captured trace plus the certified `DigitalComponent.evaluate`; anything that cannot be observed is declared. `digital-circuit/1` lives OUTSIDE the package. |
| E0 | `ExecutionTrace`, codec, replay, renderer and service. | Reused as is. The new operations are new integrations; pedagogical additions to E0 integrations are opt-in flags. |

## 2. Architecture

```text
engineering/symbolic (expr, normal, derive, integrate, solve, steps, numeric)   ← new engine, exact Fraction
engineering/{gum, mna/nonlinear, control/margins}                               ← + optional observer (default None)
engineering/digital_circuit.py                                                  ← digital-circuit/1 (outside digital/)
        │ (engines never import execution)
domain/execution/{symbolic, uncertainty, newton, control}.py                   ← new integrations
domain/execution/{equation, digital}.py                                         ← + pedagogical=False flag
        │
application/explain_render.py   ← + lessons (Paso N / Tipo / Regla / Entrada / Transformación / Salida / Explicación / Verificación)
application/explain_service.py  ← + math / GUM / Newton / margins / transition / circuit documents; fixed replay registry
        │
ui/exercises.py (math row, «Paso a paso»)   ui/logic_analyzer.py (transition explanation panel)
```

No cycles: engines never import `domain.execution` (test `z04`). The
renderer imports only the E0 core. The UI imports only `application`.

## 3. Symbolic engine: the "real step" contract

- **Expressions are data.** A recursive-descent parser over an
  allow-listed token set (numbers, names, `+ - * / ^ **`, parentheses,
  `sin cos tan exp log sqrt abs`). There is no `eval`, and every value
  is an exact `Fraction`.
- **One recorded step per rule application.** Every rule application
  appends one `Step(operation, rule, before, after, substitution,
  explanation, uses)`. The `uses` indices are the earlier steps whose
  results this step consumes.
- **Composite rules are recorded in their real sub-steps**, because the
  engine performs them in that order:
  - product: identify u, v → u′ → v′ → substitute
  - quotient: the same
  - chain: identify outer and inner → derive outer → derive inner →
    substitute
  - substitution: choose u → du (the derivative engine's own steps) →
    rewrite in u → integrate → undo
  - by parts: choose u, dv (LIATE) → du → v → formula → remaining
    integral → combine
  - Barrow: F(b) → F(a) → subtract
- **Failed attempts are never shown.** Tentative strategies run on a
  scratch log, and only a successful one is merged. If no registered
  rule applies, the engine raises `UnsupportedError NO_RULE`. The steps
  done before the failure stay in the trace, and nothing is filled in.
- **Simplification is named.** The normal form records
  `before → rule → after` per node, and only when the text changes.
  Rules: constant folding, like terms, distributive law, equal bases,
  power of a monomial, power expansion, quotient of monomials, zero
  terms, neutral element, canonical order.
- **Bounds:**
  - source ≤ 256 characters
  - depth ≤ 48
  - printed expression ≤ 480 characters
  - 256 terms per node
  - expansion up to power 8
  - 2000 steps
  - 500 characters per step field
  - integration depth ≤ 8

## 4. Verification (independent of the steps)

| Operation | CHECK |
|---|---|
| Derivative | Normal-form equivalence of the raw and the simplified derivative. Central difference (h = 1e-6, relative tolerance 1e-9) at x = 0.7, 1.3 and 2.9, through the certified evaluator. NOT_APPLICABLE with free parameters. |
| Integral | d/dx F ≡ f. Normal form if provable; else numeric at the fixed points (relative 1e-20), with the method stated. For a definite integral: Simpson n = 64 against F(b) − F(a) (relative 1e-6). |
| Linear equation | Exact Fraction substitution into the ORIGINAL sides. An identity or a contradiction is checked through lhs − rhs in normal form. |
| Simplify | Normal-form equivalence (else numeric). |
| GUM | Σ(c_i u_i)² + cov = u_c² (exact). u_c² ≈ variance (1e-12, because √ is float). U = k·u_c (exact). Σ% vs its definition. c_i vs the symbolic ∂f/∂x_i when the model parses and needs no unit scaling. |
| F8-N | The solver's KCL / KVL / power conservation, and the observed iteration count = provenance. |
| F8-P | \|L(jω_gc)\| = 1 (1e-9), and ω_gc inside its bracket. |
| F8-Q | E0 checks (Q4 replay, digest round trip, verify_capture, truth table). Each causal step records `consistent`: the certified evaluation equals the observed state. |

## 5. F8-Q causality (pedagogical mode)

This is off by default, so E0 traces stay byte-identical. In
pedagogical mode, each detailed transition gets:

- **Stimulus-driven:** the declared stimulus edge (time, state) from
  `edges()`.
- **Gate-driven, the last transition at that instant:** the settled
  observed input states at t, then `DigitalComponent.evaluate`. The
  refs point to the input transitions at t, which are the causes.
- **Gate-driven, an intermediate same-instant transition:** a WARNING.
  The engine does not expose delta-cycle evaluation, so no cause is
  invented.
- **Unprobed input:** if the net has no driver, it keeps its declared
  initial state (a topology fact). Otherwise a WARNING says the cause is
  not observable.

`explain_transition` extracts, and never computes, the explanation of
one Logic Analyzer row: time, channel, previous, new, driver, why,
cause and checks.

## 6. `digital-circuit/1`

- **Structure:**
  - canonical JSON (sorted keys, ASCII, sha256 digest)
  - nets, gates, stimuli and probes sorted by id
  - stimuli from a fixed type table (constant, toggle, pulse, pattern)
  - times as canonical decimal strings
- **Decoding is strict:**
  - size, depth and item limits
  - duplicate keys, floats and NaN rejected
  - unknown keys, unsorted ids, bad states and bad kinds rejected
  - `VersionMismatchError` for other versions
  - every object rebuilt through the certified constructors (so the
    single-driver rule etc. still apply)
- **Replay without a demo key:** a capture on a document records
  `circuit_digest`. `ExplainService.replay(trace, document)` checks the
  digest (`IntegrationError CIRCUIT_MISMATCH`), or asks for the document
  (`ValidationError MISSING_CIRCUIT`).

## 7. Renderer

- **Lessons.** `ExplanationView.lessons` holds one lesson per non-INPUT
  event, in order. A lesson is never merged, split or added.
- **Fields.** Tipo, Regla, Entrada, Transformación, Salida and
  Explicación are copied from the event's recorded values.
- **Verificación** lists the CHECK events whose refs reach this event
  through the recorded causal chain.
- **When lessons appear.** They exist only for E0.1 operations and for
  pedagogical traces, so E0 text output is unchanged.

## 8. Replay inputs

- **math.\***: expression or equation, variable, and the limits if any.
- **GUM:** measurand, equation, output unit, coverage, k, correlations,
  and one `value=…; unit=…; u=…; type=…; distribution=…; dof=…` spec per
  input.
- **F8-N:** one input per netlist line (`circuit.001` …), with
  `.param REF name=value` lines for device parameters. This is because
  the E0 text limit is 512 characters.
- **F8-P:** numerator and denominator coefficients.
- **Pedagogical mode:** `e0.mode` (equation) or `mode` (capture). Neither
  name can collide with a user variable or a context key.

## 9. Security and determinism

- **No dynamic code** anywhere new: no eval, exec, compile, pickle,
  marshal, dynamic import or shell (AST test).
- **No float in the symbolic engine.** GUM keeps its own certified
  float √ / ν_eff, and the trace says so with a WARNING.
- **Deterministic identity.** No random, clock or PID in any trace.
  Digests are compared across four `PYTHONHASHSEED` values in separate
  processes.

## 10. Known limits (declared, not hidden)

- **Symbolic coverage.**
  - Integration: power, table, substitution when the rest of the
    integrand is a constant multiple of g′, by parts for
    log·xⁿ / xⁿ·(exp|sin|cos)(ax+b), and polynomial rewriting.
  - Linear equations only, with numeric coefficients.
  - Anything else is `NO_RULE`.
- **Normal-form equivalence** is sufficient but not necessary. For
  example, trig identities and log|·| forms fall back to a numeric
  check, and the check says so.
- **F8-Q internal delta evaluation** is not observable without
  modifying the certified package. Same-instant intermediate states are
  reported as such.
- **GUM with a callable evaluator or callable sensitivities** cannot be
  recorded as data, so it is refused (`UNSUPPORTED`).
