# GATE E0.1-R+ — Certification hardening + limitation fixes — FINAL

Design: [GATE-E0.1-R-DESIGN.md](GATE-E0.1-R-DESIGN.md).

```text
E0.1-R+ FINAL REPORT
```

## Baseline

- **Start:** `584c3c2` (E0.1 certified), with `HEAD == origin/main` and
  a clean tree.
- **Implementation:** `1bf45a2`.
- **Certification:** this commit.

## Hardening

- **GUM:**
  - `observer=None` vs a recording observer on 8 models: sum, product,
    quotient, numerical, correlated, zero sensitivity, zero uncertainty,
    all zero.
  - Identical: y, u_c, ν_eff, k, U, combined variance, covariance, full
    budget and coverage source.
  - Identical errors (invalid k, empty inputs).
  - Deterministic call sequence, in the engine's own order.
  - `get_sensitivity` is identical with and without the observer.
- **F8-N:**
  - Identical `to_dict`, provenance and diagnostics.
  - Identical call order (start, then one call per iteration, 1..n).
  - Identical INVALID and MAX_ITERATIONS paths.
  - Snapshots are immutable: an observer that tries to mutate gets a
    `TypeError`.
  - The recorded snapshot satisfies `J·Δx = −F` and `x_(k+1) = x_k +
    α·Δx` at the solver's precision.
- **F8-P:**
  - 5 loops, with identical `MarginsReport` and errors.
  - Every bracket ends with a stated stop reason.
  - Every recorded new interval is one half of the previous one.

## Limitations

| Limitation | Status | Evidence | Tests |
|---|---|---|---|
| L1 symbolic bounded | **FIXED** (extended; still bounded by design) | ∫aˣ, ∫1/cos²u, recorded √u → u^(1/2) rewrite, named neutral elements and product by zero, cancellation stated as "válida si el factor ≠ 0", domain notes for tan/log/sqrt/abs. `x^x`, ∫abs, ∫exp(x²), (x²−1)/(x−1) and non-linear equations stay honest (`NO_RULE` / unchanged). | `test_r_l1_*` |
| L2 symbolic vs numeric verification | **FIXED** | `verification_kind` = SYMBOLIC / NUMERIC / NONE on every math equivalence check. Numeric checks always carry a tolerance, and "demostrado" never appears on a numeric check. The renderer shows "verificación numérica, no es una demostración". E0 checks are unlabelled and unchanged. | `test_r_l2_*` |
| L3 GUM callable | **FIXED** for declarative models (equation + constant sensitivities `c.<name>`); callable **INTENTIONALLY RETAINED** | A callable is computed by `evaluate_gum` but explained as `UNSUPPORTED`, because code is not data. There is no pickle, eval or inspect. Symbolic ∂f/∂x_i comes from the declarative formula as a NUMERIC check. | `test_r_l3_*` |
| L4 F8-Q delta cycles | **FIXED** (observational) + declared fallback | The certified `DigitalSimulator` runs on an exact `digital-circuit/1` twin through public `step()`, `queue.size()` and `states()`. Every glitch and every unprobed internal net gets its exact delta cause. A CHECK asserts the twin run equals the capture, and the causes match an independent certified run. Otherwise `UNOBSERVABLE_INTERNAL_DELTA` is declared. `engineering/digital` is byte-identical to `0cf3554`. | `test_r_l4_*` |
| L5 F8-N input limits | **FIXED** (configurable, bounded) | The limits belong to the execution-trace/1 transport, not the solver. `max_lines` / `max_line_length` / `max_total_chars` are configurable within ceilings 250 / 512 / 128 250; the defaults are 200 / 500 / 20 000. Tested below, at and above each limit, plus a large payload, a control character and the ceilings. | `test_r_l5_*` |
| L6 GUM Decimal | **INTENTIONALLY RETAINED** (KEEP_CERTIFIED_BEHAVIOR) + audited | Decimal (50 digits) √ and Welch–Satterthwaite from the certified budget. Measured difference: u_c ≤ 6·10⁻¹⁷ and ν_eff ≤ 2.2·10⁻¹⁶ relative. Replacing the engine values would change certified outputs. | `test_r_l6_*` |
| L7 trace integrations | **FIXED** | Equation, GUM (declarative), F8-N (`explain_nonlinear_circuit`), F8-P (`explain_margins_tf`), F8-Q (demo, document, delta). Opaque inputs are refused (`UNSUPPORTED_PARAMETER`, `UNSUPPORTED`). | `test_r_l7_*` |

### Pedagogy on real data

- **F8-N:** x_k, F(x_k), the real J(x_k), Δx, α, x_(k+1), ‖F‖ and
  ‖αΔx‖∞; "detalle omitido" above 4 unknowns.
- **F8-P:** f(lo), f(ω_mid), and f(hi) only when computed; the sign
  condition, the new interval and the relative width.
- **Units:** only the executed conversions. This corrects an E0.1
  over-report.
- **Equations:** fractions and parentheses are tested.

## Digital circuit

- **Round trip:** encode → canonical JSON → decode is byte-identical for
  the 4 demos. The digest is identical.
- **Same simulation:** the certified simulator's processed events are
  identical for the original and the decoded circuit.
- **Strict decoding:** malformed input is rejected, including unknown
  nets through the certified constructors.
- **No gate logic** in the serializer (tested).

## E0 compatibility

- **71/71 tests.**
- The golden `voltage_divider.json`, digest, serialization, replay and
  «Explicar» are unchanged.

## E0.1 compatibility

- **113/113 tests.**
- Two assertions were made stricter because they encoded exactly what R+
  corrects:
  - `e01`: the verification label is now required
  - `x01`: the non-executed R1 conversion must not appear, and the
    executed conversions must be consumed by their operation
- Nothing was removed, skipped or loosened.

## New tests

- `tests/test_e01r_hardening.py`: 25
- `tests/test_e01r_limitations.py`: 49

## Full suite

- **Run:** `pytest -q` gave 3274 passed, 134 skipped (environment-only)
  and 1 failed, in 16 min 47 s.
- **The failure:** `test_f8n_lab_valid::test_n110_git_clean_certified`,
  which runs `git status` on `mna/`. It was red only because the
  extended observer call in `nonlinear.py` was not yet committed. It
  passes after commit `1bf45a2`, whose code is identical to the code
  that was tested.
- **Effective result:** 3275 passed, 134 skipped, 0 failed.

## Security

- **Scans:** eval, exec, compile, pickle, marshal, subprocess, os.system
  and importlib in `src` give only `re.compile` (regex) and a docstring.
  There is no dynamic execution.
- **AST tests:** E0.1 `z02`/`z03` and E0 `x*` pass.
- **Inputs** are bounded, typed, validated and deterministic. Control
  characters are rejected before reaching a trace.

## Determinism

- **Across processes:** the digests of 7 new traces are identical across
  `PYTHONHASHSEED` = 0 / 3 / 31337 / random in separate processes. The
  traces are: delta capture, Newton, margins, GUM with declared
  sensitivity, ∫1/√x, simplify x/x, and pedagogical units.
- **Across runs:** traces repeat byte-for-byte.

## Performance

Best of 5 runs, on this container.

| Measurement | Time |
|---|---|
| F8-N (2 diodes), `observer=None` | 10.1 ms |
| F8-N, recording observer | 10.5 ms |
| F8-N, full trace | 11.6 ms |
| GUM, `observer=None` | 0.4 ms |
| GUM, recording observer | 0.3 ms |
| Symbolic, simple (d/dx x³) | 1.1 ms |
| Symbolic, bounded (∫x² sin x) | 4.2 ms |
| `digital-circuit/1` encode + decode (16-input NAND) | 0.2 ms |
| Pedagogical capture | 4.8 ms |
| Pedagogical capture + delta | 5.7 ms |

There is no significant regression, and every path stays bounded:
`MAX_DELTA_STEPS`, symbolic limits and input ceilings.

## Commit

- Implementation: `1bf45a2`
- Certification: this commit

## origin/main

`HEAD == origin/main`, verified after the push.

## Tree

clean

## Final verdict

```text
E0.1-R+ COMPLETE / CERTIFIED
```
