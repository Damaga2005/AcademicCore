# GATE-F8L: Certification Report — Time-Domain Transient DAE Analysis

> **Gate**: F8-L
> **Design reference**: `docs/gates/GATE-F8L-DESIGN.md` (`F8-L DESIGN READY`)
> **Prior state**: F8-H / F8-I / F8-J / F8-K CERTIFIED
> **Engine**: `f8l-transient/1.0` — implicit BE/TR/BDF2 DAE integration,
>   Decimal-native, adaptive LTE stepping, transactional rollback
> **External oracle**: ngspice 47 (`ngspice_con.exe`) + closed-form analytics
> **Final Verdict**: **`F8-L CERTIFIED`**

---

## 1. Header / Scope

F8-L adds time-domain transient simulation: capacitors and inductors with
companion models, three implicit integrators (Backward Euler, Trapezoidal,
variable-step Gear/BDF2), an LTE-driven adaptive controller (accept/reject/
retry, `h_min`/`h_max`), explicit/DC-derived initial conditions with DAE
consistency by construction, and per-step coupled DAE-Newton solves reusing
the certified F8-H/I/K device mathematics unmodified.

Out of scope (per design): distributed/frequency-dependent elements,
parasitic device capacitances (BSIM/Meyer), event-driven engines,
wall-clock criteria, internal Rs.

## 2. Implementation

| File | Change |
|:---|:---|
| `mna/transient.py` (new, ~1550 lines) | `TransientConfig/Result/Status`, waveforms (DC/step/pulse/sine), IC handling, `_TransientSystem` (residual/Jacobian), BE/TR/BDF2 companions, LTE controller, rollback history, `solve_transient` |
| `mna/problem.py` | `allow_transient` flag: C validated (`>0`, finite) with no static stamp (open); L validated with one aux unknown, statically a short (0 V pattern); `MNAProblem.l_aux_refs`; `size` extended |
| `mna/__init__.py` | `solve_transient`, `TransientConfig/Result/Status`, `MAX_TRANSIENT_STEPS` exports |
| `tests/test_f8l_transient.py` (new, 58 tests) | full §12 plan |
| `docs/gates/GATE-F8L-DESIGN.md` | normative design (established verbatim pre-implementation) |
| `docs/roadmap/ROADMAP.md` | F8-L CERTIFIED, F8-M NEXT |

Linear dispatch untouched (`SUPPORTED_TYPES` unchanged; C/L rejected without
the flag). `nonlinear.py`, BJT/MOS/JFET/diode math, AC engine: zero changes.
`dependent.py` shared validation untouched (L/C control rejection lives in
the transient pre-check → `INVALID`, preserving certified AC behaviour).

## 3. DAE formulation

Semi-explicit index-1 form `G·x + C_dyn·xdot + f_nl(x) − s(t) = 0` with
`x` = node voltages + V/E/H/O/T aux + one aux current per inductor.
Per step: `F(x_{n+1}) = A0·x − b(t_{n+1}) + D(x) = 0`, where `b(t)` substitutes
waveform levels for V rows / I injections, C contributes Norton
(`Geq`, `∓Ieq`), L constraint rows are overwritten with the series companion
(`+1/−1/−Req`, `Veq`), and `D` holds F8-H/I/K currents. Damped Newton,
frozen Q1 (RTOL/ATOL/STOL/MAX_ITER/MAX_BACKTRACK).

## 4. C / L stamps

- Capacitor: `i = Geq·vC − Ieq`; nodal `±Geq`, residual `∓Ieq`
  (BE: `C/h, C/h·vC(n)`; TR: `2C/h, 2C/h·vC(n)+iC(n)`;
  BDF2: `α0·C, −C(α1·vC(n)+α2·vC(n−1))`).
- Inductor: aux `iL` (1→2); KCL `±1` (static short pattern kept);
  row `Vp−Vn−Req·iL = Veq`
  (BE: `L/h, −L/h·iL(n)`; TR: `2L/h, −2L/h·iL(n)−vL(n)`;
  BDF2: `α0·L, L(α1·iL(n)+α2·iL(n−1))`).
- Variable BDF2: `α0=(2r+1)/((r+1)hn)`, `α1=−(r+1)/hn`,
  `α2=r²/((r+1)hn)`, `r=hn/h_{n−1}` (uniform → 3/2h, −2/h, 1/2h);
  first BDF2 step falls back to BE (startup, counted in stats).

## 5. Backward Euler / Trapezoidal / BDF2

Implemented exactly per design §6 (companion tables verified term-by-term
against the gate). TR exposes iC/vL history dependence; BDF2 consumes two
history levels with the step-ratio formula above. Fixed-step verification
mode (`adaptive=False`: LTE reported, never rejects; Newton failure →
`DIVERGED`) exists for order testing.

## 6. Adaptive timestep

Predictor/corrector LTE on `y=[vC,iL]`: linear-extrapolation predictor for
BE, quadratic (second divided difference) for TR/BDF2 with ≥3 points,
explicit-Euler (`y+h·dy`, using stored `iC/C`, `vL/L`) with one point —
a zero-order predictor would measure the increment instead of the error and
pin the controller under `h_min` (found and fixed during implementation).
`E = max(LTE/Tol)`, `Tol = abstol+reltol·max(|y_{n+1}|,|y_n|)`;
accept iff `E≤1` (`h_new` with κ=0.85, clamp ×[0.1, 2.0], `h_max`);
reject → retry (`h·max(0.1, 0.85·E^{−1/(p+1)})`); below `h_min` →
`TRANSIENT_TIMESTEP_TOO_SMALL`. Newton divergence retries at h/2.
No wall-clock, no time asserts anywhere.

## 7. Error estimation (LTE)

Per §6 above. Normalisation constants BE:1 / TR:3 / BDF2:3 (documented
choice; adaptation behaviour covered by accept/reject/grow/shrink tests,
order verified independently with fixed steps).

## 8. Initial conditions

Explicit `ic` Quantity on C (V) / L (L→A, any sign, finite). t=0 state via
DC-equivalent substitution (C+IC→V source, C→open, L+IC→I source oriented
to draw from pin 1, L→0 V short) with **waveform levels evaluated at t=0**
(not DC values — fixed during implementation); wave-free sources keep
`value`. Failure of the t=0 solve → `INVALID` (inconsistent IC loudly
reported, never silently projected). Histories seeded with exact
`(vC,iC)/(iL,vL)` pairs (aux currents mapped with MNA sign conventions).

## 9. Rollback / history

Only accepted steps append `(t, x, h)` plus dynamic pairs; tentative Newton
vectors are locals. Rejection paths never mutate history (asserted: failed
runs carry empty trajectories; committed runs have uniform lengths and
strictly increasing times).

## 10. Nonlinear integration

D/Q/M/J/Zener/LED/Schottky/Photodiode evaluated per Newton iteration via
the certified extract/current/jacobian helpers (zero model duplication).
`J_total = G_MNA + G_eq,dyn + J_nl`. Proven: diode rectifier + RC,
MOSFET inverter (triode steady state 2.28 V reproduced), BJT switch,
Zener/JFET/Schottky step discontinuities — all `COMPLETED`, finite,
conserving.

## 11. Numerical guarantees

- `Decimal`-native end to end (prec-50 explicit contexts); `float(` grep = 0
  and AST float-literal/call scan = 0 on transient + touched engine files.
- Context-explicit ops in all new code (`copy_abs`, `ctx.*`; no ambient
  `abs()/round()` on working values — the bug class fixed upstream in P1).
- Overflow/non-finite → `DIVERGED`/`TIMESTEP_TOO_SMALL`/retry, never
  clipping, never NaN→0.
- Determinism: 3× identical `to_dict` (trajectories+stats) on a
  diode+pulse circuit; stats reproducible; insertion order irrelevant
  (sorted refs).

## 12. Determinism (§11 gate guarantees)

Verified per §11 of the design gate: identical topology + tolerances +
method → bit-identical trajectories, final state, accept/reject counts,
Newton totals.

## 13. Security

`eval/exec/__import__/subprocess/os.system` grep = 0 in `transient.py`;
AST suite additionally bans `globals/locals/compile`, `os/sys/importlib/
socket/requests/subprocess/shutil` imports and process-spawning attribute
calls across transient + problem/nonlinear/MOS/JFET/diode. 0 dynamic
execution, 0 process execution, 0 network.

## 14. Tests (58 new, all passing)

Validation (config 7, waves 12 incl. pulse/sine closed forms, BDF2 coeffs 3,
IC extract), analytic RC (4: discharge all-methods + TR 1E-4 + charge step),
RL (2), RLC regimes (3: period within 2%, monotone critical/overdamped),
order BE/TR/BDF2 via halving (3), adaptive (4: reject/retry, dt growth,
h_min termination with empty history, rollback integrity), IC (5),
nonlinear (4: rectifier/inverter/BJT-switch/gm-preservation),
discontinuity (4: Zener/JFET/Schottky/H-by-C rejection), determinism (2),
security (2), diagnostic benchmarks (3), ngspice RC (1).

| Suite | Passed | Failed | Skipped | Duration |
|:---|:---:|:---:|:---:|:---|
| test_f8l_transient.py (58) | 58 | 0 | 0 | ~25 min (order sweeps + N-scale Newton) |
| test_f8h (69) / test_f8i (74) / test_f8j (29) / test_f8k (110) | 282 | 0 | 0 | — |
| Linear/DC batch (F8-B/C/E/F/G, eng) | 482 | 0 | 0 | 15 min |
| F8-D/F7 batch | 852 | 0 | 0 | ~7 min |
| Montecarlo + F8-J bench | 30 | 0 | 0 | ~2 min |
| Rest (F9/misc/UI/P0/quantities) | 266 | 0 | 2* | 85 s |

\*pre-existing skips. Global ≈ 1970 passed, 0 failed.

## 15. Regression

Post-implementation: F8-H/I/J/K green; linear/DC, F8-D/F7, Montecarlo, rest —
all green. No unexpected failures; the two pre-existing F8-D4 precision
asserts were already fixed upstream (verified passing).

## 16. Benchmarks (diagnostic, zero time asserts)

Python 3.14.6 / Windows-11: RC step `{BE: 6.9 s/584acc/1rej,
TR: 9.9 s/519/4, BDF2: 7.0 s/519/3}` (5 ms, tight tol);
RLC underdamped `45.6 s, 1745 acc / 85 rej / 3660 newton`;
nonlinear diode+MOS sine rectifier `14.5 s, 1325/22`.
Metrics recorded: runtime, accepted/rejected, Newton totals.

## 17. External validation

- ngspice 47 RC charging (PULSE 10 µs edges, `.tran`, 6 samples): all within
  **0.15 V** of the TR trajectory.
- Closed-form oracles: RC discharge (TR `<1E-4`), RL step (`<1E-2` all
  methods), RLC period (`<2%`), JFET-style triode self-consistency inherited.
- Method orders measured: BE ≈2.0×, TR ≈4×, BDF2 ≈4× per halving.

## 18. Findings

- CRITICAL/HIGH: none open.
- MEDIUM: ideal voltage steps force deep controller cutbacks (E∝h at kinks);
  resolved by honest sub-`h_min`-capable floors in step tests + documented
  tolerance policy (`step_cfg` rationale in-suite). No silent smoothing added.
- LOW: BDF2 order test needs sub-τ/5 steps to clear the BE-startup
  pre-asymptotic regime (documented in-test).
- INFO: fixed-step verification mode (`adaptive=False`) added for order
  testing (LTE still estimated/reported; Newton failure → `DIVERGED`).

## 19. Limitations (deliberate)

No breakpoints/event location (kinks resolved by adaptive cutback, not
landing); no charge-conserving device capacitances; no transmission lines;
`adaptive=False` is verification-only; `MAX_TRANSIENT_STEPS = 100000`
deterministic budget; sine uses `decimal_sin` Taylor precision.

## 20. Definition of Done

DAE framework, C/L companions, BE/TR/BDF2, LTE+adaptive policy, rollback
isolation, F8-H/I/J/K integration, Decimal-native, zero dynamic execution —
all specified items implemented, tested (58), regressed (~1970 green),
benchmarked (diagnostic), externally validated, documented. No F8-M content.

## 21. Gate Sign-Off & Verdict

| Criterion (mandate §27) | Observed | Status |
|:---|:---|:---:|
| Capacitor / Inductor + IC | analytic RC/RL/RLC green | CERTIFIED |
| Backward Euler / Trapezoidal / BDF2 | order 1×/2×/2× measured | CERTIFIED |
| Adaptive timestep + LTE | accept/reject/retry/grow/h_min tested | CERTIFIED |
| Initial conditions | zero/explicit/DC-derived/inconsistent | CERTIFIED |
| Rollback | history-intact + empty-on-failure | CERTIFIED |
| Nonlinear DAE-Newton | D/Q/M/J/kinds converge | CERTIFIED |
| Determinism | 3× bit-identical | CERTIFIED |
| Decimal-native, 0 float | grep + AST | CERTIFIED |
| Security | 0 dynamic/process/network | CERTIFIED |
| Regression global | ~1970 passed, 0 failed | CERTIFIED |
| Analytic validation | RC/RL/RLC + ngspice | CERTIFIED |

**Final Verdict**: **`F8-L CERTIFIED`**
