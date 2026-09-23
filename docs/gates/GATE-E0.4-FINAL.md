# GATE E0.4 — Explainable Engineering Deep Observability & Resolver Retrofit — FINAL

Design: [GATE-E0.4-DESIGN.md](GATE-E0.4-DESIGN.md). It holds the audit,
the formal retrofit matrix, the new-resolver policy and the declared
limitations.

```text
E0.4 FINAL REPORT
```

## Implementation

- **Baseline:** `12625cf` (E0.3 certified), with `HEAD == origin/main`,
  branch `main` and a clean tree.
- **Implementation commit:** `cab74da` `feat: deepen explainable engineering
  observability`.
- **New module:** `domain/execution/engineering_deep.py`, with 12 text
  operations plus `lab.run-analysis`.
- **Registry:** fixed `ExplainService.deep_trace` / `explain_deep` /
  `explain_lab_run_analysis`.
- **Lessons:** `LESSON_OPERATIONS` is extended.
- **Schema:** `execution-trace/1` is unchanged.

## Engines integrated and real observations

- **F8-L transient** (`engineering.transient-newton`):
  - Per inner Newton iteration: x_k, F(x_k), the real J(x_k), Δx, α, every
    backtracking trial (α, trial norm, accepted/rejected, reason), ‖F‖ by
    block, res_ok and step_ok.
  - Per attempt: LTE / accept / reject / abort (E0.3).
  - A failed inner Newton carries its reason and the failing iteration.
  - Backtracking is real: the MOSFET gate-RC fixture backtracks.
    - α halves from 1, and only the last trial is accepted.
    - The event count equals Σ trials.
  - CHECKs:
    - J·Δx + F = 0: NUMERIC
    - Σ iterations = `stats.newton_total`: SYMBOLIC
    - x_(k+1) = x_k + α·Δx: NUMERIC
- **F8-D5 AC sweep** (`engineering.ac-sweep-mna`):
  - Per frequency: A(jω), identical to `build_ac_problem` at that
    frequency; b(jω); x(jω); H, |H| and ∠H from the sweep.
  - Matrices above 8×8 are OMITTED with a SHA-256 digest.
  - CHECKs: A·x = b per frequency, |H|², the frequency sequence.
- **F8-K** (through `engineering.nonlinear-dc`):
  - MOSFET NMOS/PMOS: VGS, VDS, VSB, Vth, Vov, region, I_D, I_S, gm, gds,
    gmb and the 4×4 block.
  - JFET: region, I_D, gm, gds and the 3×3 block.
  - Zener (forward / breakdown), LED, Schottky, photodiode: branch, Vd, I
    and g.
  - All are captured inside the certified models.
  - Tests recompute them with the engine's own functions from the recorded
    voltages and find them identical.
  - Text form: closed enumerations (NMOS/PMOS/NCHAN/PCHAN, diode kinds) and
    the `A/V2`, `/V` suffixes. It round-trips.
- **F8-M:**
  - Parameter sweep: every point with its real x₀ and Newton iterations.
  - Worst case: every corner, plus the engine's extrema, checked against
    their corners.
  - DC sensitivity: x*, J, dF/dp and dx/dp, where dx/dp equals the
    engine's `result.state`, with no second route. CHECK
    J·dx/dp + dF/dp = 0 (NUMERIC).
  - Monte Carlo: the given seed, plan digest, sub-seeds, sampled
    parameters, status, observables and engine statistics.
    - Same seed gives the same digest; a different seed gives different
      samples.
- **F8-O:** `evaluate_budget` hands the observer to the certified
  `evaluate_gum`. Its observation stream is identical to the E0.1 GUM
  trace's engine, so there is no second GUM. Results are unchanged.
- **F8-P1:** `control.routh`: exact table rows identical to
  `routh_of_tf`, verdict and RHP count, cross-checked against the
  Durand–Kerner inventory.
- **F8-P2:**
  - `dsp.fft`: bit-reversed input, the twiddles each stage actually used,
    each stage's vector, and X[k] = the last stage. CHECKs: FFT = the
    engine's direct DFT (NUMERIC), and log2 N stages (SYMBOLIC).
  - `dsp.sampling`: f_N, verdict, alias.
- **F8-P3:** `rf.reflection`: Γ, |Γ|, VSWR, RL and ML from engine calls,
  with the Smith map as an independent path (NUMERIC). Infinite RL is
  declared UNSUPPORTED.
- **F8-P4:** `comms.bpsk`: setup (Eb/N0, N0, σ, seed) and every simulated
  bit: uniform, bit, symbol, noise, received sample, decision, error.
  Errors equal the report's; the 5σ criterion is NUMERIC.
- **F8-P5:** `satcom.link-budget`: EIRP → FSPL → Lmisc → Grx → Pr → G/T →
  C/N0 → C/N → Eb/N0 from `forward_budget`, with NUMERIC identities.
- **F15 / Virtual Lab:**
  - `lab.run-analysis` re-observes PARAM_SWEEP, CORNERS, SENS_DC and
    MONTE_CARLO runs on their working circuit. CHECK "mismo resultado que
    el run" (SYMBOLIC digest).
  - Other kinds are UNSUPPORTED there.
  - «Explicar último» and «Explicar en detalle» are unchanged.
  - The lab replay gives EQUIVALENT.

## Data not observable

See §6 of the design gate:

- AC sensitivity
- per-sample Newton in Monte Carlo
- per-device small-signal rows inside the AC trace
- PID / state-space / root locus
- filter design
- RF matching and network conversions
- non-BPSK modulations
- satcom inverse synthesis
- SENS_AC in the lab

The inner-Newton *failure* path is observable, but no circuit tried made it
fail, so it is tested only as "never shown when not observed".

## Tests

`tests/test_e04_explainable_engineering_deep.py`: 36 tests covering:

- transient (4)
- AC sweep (2)
- F8-K (7 parametrized + 1)
- F8-M (5)
- F8-O (1)
- F8-P (5)
- F15 (1 + 4 parametrized + 1)
- anti-fake (1)
- determinism, boundedness, security, performance (4)

## Regression

- **E0 / E0.1 / E0.1-R+ / E0.2 / E0.3:** 71 / 113 / 74 / 31 / 39. The test
  files are unchanged and pass.
- **Engine families:** F8-H, F8-I, F8-J, F8-K, F8-L, F8-M, F8-N, F8-O,
  F8-P1..P5, F8-Q1..Q7, F15, architecture, AST, domain and security pass
  within the full suite.
- **Full suite:**
  - **passed:** 3381
  - **failed:** 0
  - **skipped:** 134 (environment-only)
  - **time:** 23 min 38 s, on `cab74da`
- **Goldens:** E0 golden, digital golden data, and the E0.1 / E0.1-R+ /
  E0.2 / E0.3 expectations are unmodified. The `engineering/digital`
  package is identical to `0cf3554`.

## Security

- **Execution modules:** `engineering_deep.py`, `newton.py` and
  `analog_detail.py` pass the AST checks: no eval, exec, compile,
  `__import__`, getattr, setattr, open, pickle, marshal, importlib or
  subprocess; no os, sys, shell or dynamic import.
- **Modified engines:** no eval, exec, compile or `__import__`, and no
  `domain.execution`, UI or Qt imports.
- **Inputs:** text, bounded and validated, with closed enumerations.

## Determinism

The digests of 11 traces are identical across `PYTHONHASHSEED` =
0 / 11 / 2024 / random, in separate processes:

- transient Newton
- AC sweep MNA
- parameter sweep
- Monte Carlo
- FFT
- BPSK
- NMOS, PMOS, JFET, Zener
- link budget

Truncation is deterministic.

## Performance

Best of 3; a recording observer against `observer=None`:

| Engine | Baseline | Observed | Overhead |
|---|---|---|---|
| transient (MOSFET) | 0.336 s | 0.372 s | 11 % |
| AC sweep (3 f) | 6.3 ms | 6.5 ms | 3 % |
| DC sensitivity | 8.8 ms | 8.7 ms | −1 % (noise) |
| FFT N=64 | 11.5 ms | 12.8 ms | 11 % |
| BPSK 200 bits | 58.0 ms | 61.3 ms | 6 % |

## Boundedness

- A(jω) is shown FULL up to 8×8, else OMITTED with a digest.
- The Newton J / Δx / x_k are shown up to 4×4, else as a digest.
- DC points and frequencies are limited to 500 and refused above that.
- Monte Carlo lists up to 200 samples and BPSK up to 64 bits; above that
  the trace carries an explicit `TRACE_TRUNCATED` with the omitted count.
- The detail budget is 4000 events / 5 MB (E0.3). A transient Newton trace
  under a 15-event budget is deterministic and still PASSES its checks.
- A full MOSFET transient trace is below 8 MiB and round-trips through a
  strict decode.

## Deviations

1. **F8-H determinism fix.**
   - `nonlinear.py` builds its per-net KCL table in sorted order.
   - Before, `max()` over hash-ordered nets reported `0E-51` or `0E-52`
     for the same zero residual depending on `PYTHONHASHSEED`. E0.4's
     determinism test found this on MOSFET circuits.
   - Values are unchanged; only the reported representative is now
     deterministic.
2. **E0.3 module refactor.**
   - `analog_detail._render_points` is extracted and `_sweep_checks` takes
     the point list, so F8-M reuses the E0.3 renderer.
   - The E0.3 traces are unchanged: their tests and cross-process digests
     pass.
   - The E0.3 transient observer stores `newton_failure`.
3. **`lab.run-analysis` is a new operation.** `lab.run-detail` keeps its
   E0.3 contract: its test `g03` pins PARAM_SWEEP as UNSUPPORTED.

## Commits

- Implementation: `cab74da`
- Certification: this commit

## origin/main

`HEAD == origin/main`, verified after the push.

## Tree

clean

## Final verdict

```text
E0.4 COMPLETE / CERTIFIED
```
