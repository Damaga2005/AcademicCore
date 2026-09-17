# Quality Gate: F8-D6 — Bode / Log-Frequency Response + Level Metrics

- **Phase**: F8-D6 (sixth step of F8-D; F8-D1…D5 certified).
- **Scope**: log-frequency grids, dB magnitudes, deterministic phase
  unwrap, cutoff brackets, bandwidth intervals, observed discrete
  extrema, reactance-zero candidates — as pure post-processing of D5
  sweep results. No poles/zeros, no filters, no resonance verdicts/Q,
  no RMS model, no dependents/transients/nonlinear/symbolic, no
  Thevenin-AC, no UI/persistence.
- **Files**: `math/logarithm.py` + `ac/bode.py` (new; §8 path corrected
  to the real `domain/engineering/math/` package), `math/__init__` +
  `ac/__init__` exports (strictly necessary), `tests/test_f8d6_bode.py`
  (65 tests), this doc. Zero modifications to certified files.
- **Status**: implemented, self-verified, uncommitted (no commit/push).

> Certified domain: log-frequency Bode analysis (magnitude/dB, wrapped
> + deterministically unwrapped phase) with observed cutoff brackets,
> bandwidth intervals, discrete extrema and reactance-zero candidates,
> over general linear steady-state AC networks via D5 sweeps.

---

## 1. Numeric model (new primitives, same D1 model)

`decimal_nth_root(x, n)` (Newton from above, step + residual gates),
`decimal_log10(x)` (`x = m·10^e` exact split, atanh series,
`log10(1) = 0` exactly), single coherent `ln(10) = ln(2)+ln(5)` source
cached per explicit precision. Pure Decimal, explicit contexts, global
context untouched, iteration caps are tripwires raising
`ArithmeticError` (tested starved). No float/complex/math/cmath/numpy;
no third numeric type. EXACT R-only H values stay exact; dB/unwrap/grid
are Decimal approximations by statement (log10 of rationals is
generally irrational).

## 2. Log grid

`f_k = f_start·r^k`, `r = 10^(1/ppd)`, repeated-multiply accumulation,
strictly increasing, ppd ≥ 1 / n ≥ 1 validated, `f > 0` Hz enforced.
Frequencies canonicalized by normalized base-Hz keys (`1000 Hz` ≡
`1 kHz` ≡ `1000.0 Hz`, proven by digest-equality test).

## 3. dB / threshold

`20·log10|H|`; exact zero → `NEGATIVE_INFINITY_DB` category (never a
stored infinity); negative input rejected. Default threshold is
half-power below max valid dB with `10·log10(2)` computed, never `3.0`.

## 4. Unwrap

Minimize `|φ + 2πn − u_prev|` over the rounded estimate ±2 (always
contains the true minimizer); ties → smaller cumulative offset, then
smaller n; segments restart at every invalid point (never crossed,
never interpolated, never smoothed). Single-sample gradual winding
accumulates past 2π; single-step >2π jumps correctly resolve to the
minimal step (undersampling limitation documented, not invented).

## 5. Cutoffs / bandwidth / extrema / reactance

Brackets over index-adjacent valid samples only (exact hits → zero-width
brackets; flat-on-threshold runs are not crossings; nothing
interpolated, no root finding). Bandwidth DEFINED only with two
flanking brackets, as the rigorous interval
`[hi.lo_f − lo.hi_f, hi.hi_f − lo.lo_f]`; otherwise UNDEFINED with
reason (never 0 Hz-anchored — sweeps exclude DC); all bands reported.
Extrema are strict/flat/endpoint observations (full-constant sweeps
report both flat kinds); lone points claim nothing. Reactance-zero
brackets are candidates only — no `RESONANT`, no Q, no resonance
frequency anywhere. Transfers get bands; impedance kinds get extrema +
reactance (bandwidth is a transfer concept).

## 6. Statuses / generality / oracles

D2/D3 statuses propagate per point (UNCERTAIN never laundered — tested
via crafted mixed sweep); sweep-level completed/partial preserved.
64-node ladders, K3,3, multigraph, non-GND ports, multi-source, R/L/C
mixes; seeded N-scales; no topology conditionals in core (audited).
Oracles: PI50 closed forms, hand Cramer/fractions, −20 dB/decade
asymptotes, REAL ngspice exact-frequency decks (sampler-alignment and
auto-print hazards avoided by construction; current-sign mappings from
D3/D5 reused, never re-assumed). Metamorphic: permutation/rename
digests, amplitude invariance, valid scaling laws only, conjugation
algebraic-only.

## 7. Integrity

Read-only over circuits/sweeps/solutions (netlist + sweep snapshots
before/after asserted); idempotent digests; provenance links the exact
D5 sweep digest with grid/threshold/unwrap/bandwidth rules; timestamp-
free canonical digests. AST: no eval/exec/compile/import-magic/open/
subprocess/os/network/pickle/marshal/float/complex/math/cmath/numpy.
Post-processing is O(N) measured separately from solve time (N=1001
green); no caching, no MNA reuse (A(ω) differs per point — stated).

## 8. Regression & boundaries

Full suite must read 1112 + 65 = 1177 passed with the same 2 reportlab
skips; scope is exactly the four authorized paths plus necessary
`__init__` exports. F8-D7 and everything out-of-scope untouched.

## 9. Known limitations

Log grids only (fractional-power primitive now exists; log-axis *plots*
remain UI work); no interpolation/refinement of brackets (intervals are
the honest output); single-step >2π winding unrecoverable by principle;
derived (non-tested) D5 digest spellings are linked, not hashed, so
identical physics hashes identically.

---

F8-D6 STATUS:
PASS — CERTIFIED
Reconciliation (§50): baseline collected 1114 (1112 passed + 2 skipped);
D6 delta collected 66 (66 passed + 0 skipped); final collected 1180
(1178 passed + 2 pre-existing reportlab skips + 0 failed). Exact.
