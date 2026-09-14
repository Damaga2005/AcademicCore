# Quality Gate: F8-D8 — General AC Resonance & Quality Factor

- **Phase**: F8-D8 (eighth step of F8-D; F8-D1…D7 certified; F8-D8 DESIGN READY accepted before implementation).
- **Scope**: resonance verdict ladder over D5 sweeps (zero-confirmed /
  bracket-candidate / extremum-observed / no-resonance), energy-Q from
  lazy D3+D4 evaluations, conditional bandwidth-Q intervals, D7-port
  sweep mode. NO root finding, NO interpolation, NO refinement, NO
  poles/zeros, NO resonance bandwidth, NO universal f0/BW Q.
- **Files**: `ac/resonance.py` (new), `ac/__init__` exports (strictly
  necessary), `tests/test_f8d8_ac_resonance.py` (68 tests), this doc.
  Zero modifications to certified D1–D7 files; `units.py` untouched.
- **Status**: implemented, self-verified, committed LOCAL ONLY (no push).

> Certified domain: per-observable resonance findings and energy-Q over
> general linear steady-state AC networks via D5 sweeps, D6
> observables, lazy D3/D4 evidence, and D7 port-equivalent series.

---

## 1. Objective

Implement exactly the approved F8-D8 design: observable-indexed
resonance findings (never a bare frequency), energy-Q where
mathematically justified, conditional bandwidth-Q intervals, full
reuse of D1–D7 with no second solver/Circuit/MNA/Complex/Port/sweep.

## 2. Baseline

HEAD `67b3cde` (post-D7 local commit) atop `1148728`; tracked diff =
prior `units.py` var/VA+Siemens lines only. Full suite pre-change:
collected 1232 = **1230 passed + 2 skipped** (pre-existing reportlab),
0 failed — used as the real local baseline.

## 3. Architecture

Canonical Circuit → D5 `frequency_response` sweep → D6 observables
(`observed_extrema`, `analyze_bode` for transfers, canonical keys) →
D8 verdict ladder → `ResonanceReport`. Q path: candidate frequencies
→ D3 `solve_ac` → D4 `analyze_power` → energy-Q (lazy, candidates
only). D7 path: `ACOnePortEquivalent` series → same zero/bracket
machinery on `Zth` (port-as-seen-by-load, no Q).

## 4. Domain

Arbitrary R/L/C+V/I nets; any port incl. non-GND; multi-source (D5
network-transfer deactivation or operating ratios); branch and
transfer observables (all four kinds, both bases); strictly
increasing f > 0 caller grids. Resonance UNDEFINED with reason for:
nonreactive nets, all-invalid grids, single-sample grids (except
EXACT zero), non-SOLVED parents, non-FINITE values.

## 5. Resonance semantics

`ZERO_CONFIRMED` (EXACT, SOLVED, FINITE, native `im == 0` — includes
physical `Z = 0`; phasor-level `is_zero_exact` would wrongly demand
`re == 0`, documented); `BRACKET_CANDIDATE` (strict native sign
change, adjacent SOLVED+FINITE, mandatory pole note, never promoted);
`EXTREMUM_OBSERVED` (D6 kinds respected, corroboration only);
`NO_RESONANCE_OBSERVED` (summary when no zero/bracket evidence).
Reactivity gate: no L/C → no resonance findings, ever.

## 6. Observable semantics

Port-Z → series-reactance-zero; port-Y → parallel-susceptance-zero
(equivalent for FINITE-nonzero immittances); transfers → strict
isolated |H| maxima as peak candidates (never verdicts); branch
Z/Y → zero-conditions on operating ratios. Findings never migrate
between observables; D7-port resonance ≠ whole-circuit resonance.

## 7. Q semantics

Energy-Q `Qe = Σ|Q_L,C| / (2·ΣP_R)` from D4 branch powers, F6
type-filtered (R/L/C only; V/I/D/Q excluded), peak-phasor
convention, native arithmetic (ω cancels — EXACT-capable, no π).
DEFINED iff SOLVED + ΣP_R > 0 + Σ|Q| > 0. UNDEFINED: nonreactive,
lossless (never Infinity), non-SOLVED, non-positive dissipation.
Verified identities: series → (ωL+1/ωC)/2R (ωL/R at f0); driven
parallel tank → hand nodal form incl. series-R dissipation.

## 8. Bandwidth semantics

D6 `PassBand`/`CutoffBracket` reused verbatim (transfer only, incl.
D6 `analyze_bode` inside `scan_resonance` for transfers). −3 dB only
via D6's exact 10·log10(2) transfer threshold; rejection tests for
Z-kind, band-less, and two-peak inputs. No resonance bandwidth
computed (deferred with reason).

## 9. Discrete/continuous policy

Bracket-only v1 (provenance-stamped): no interpolation, no root
finding, no adaptive refinement (single pass over caller grid).
Pole-vs-zero discrimination = documented caller rule (refine via
D5; interior fall = zero-consistent, rise = pole-consistent —
consistency check, not proof). HP exact-zero samples inert.

## 10. Status model

All six `ACStatus` reused; physical finding kinds are a separate
enum. Non-SOLVED samples excluded from brackets/extrema evidence;
UNCERTAIN never confirms (unit-tested at `_extract_phasor`);
sweep completed/partial preserved and linked.

## 11. D4 integration

Lazy: one D5 sweep first, candidates identified, then D3+D4 only at
candidate frequencies (zero samples + bracket endpoints + transfer
peaks). No power duplication, no convention duplication, SOLVED-only.

## 12. D5 integration

`frequency_response`/`SweepResult`/`ResponseDefinition` (all five
kinds), test-source/deactivation semantics, transfer bases —
authority untouched, nothing copied.

## 13. D6 integration

`observed_extrema` (all extrema), `analyze_bode` (transfer bands),
`canonical_frequency_key` (all identity incl. digest hash —
Hz/kHz digest equality tested), threshold/band rules. Native
zero/bracket scan is D8's own (exactness-preserving; D6's Decimal
coercion would round exact zeros — documented, not duplication).

## 14. D7 integration

`scan_port_equivalents(circuit, port, equivalents)`: Zth-FINITE
series through the same machinery; no Q (documented: Q needs
live-circuit D4); port-as-seen-by-load semantics; port-mismatch /
empty misuse errors; bracket parity with the D5 scan tested. D7
unmodified.

## 15. Generality

Ladders N = 1/2/4/8/16/32/64 (digest-stable, distinct), series,
parallel, bridges, meshes, stars, K3,3, multigraphs, GND/non-GND
ports, multi-source, R/L/C mixes; no topology conditionals (single
native scan + D6 authorities). Multi-resonance: parallel two-tank
port yields 3 brackets, each confirmed by hand-oracle AND ngspice
brackets; two transfer peaks stay ordered candidates, never verdicts.

## 16. Independent oracles

PI50 analytic f0 containment (series + parallel); closed-form Q(f)
(series + driven-parallel with series-R dissipation); hand
series/parallel reduction oracle for two-tank brackets (Decimal,
no D5/D8 path); Cramer/nodal references via the driven-parallel
form; Hz/kHz canonicalization; D5/D6 as inputs, never sole truth.

## 17. ngspice

6 REAL tests, 0 skipped (backend present): series bracket values +
ngspice-derived energy-Q (≤2%); parallel admittance independent sign
change; pole-straddle magnitudes (|Z|≈840/≈9500 asymmetric pair);
RC transfer values vs analytic |H| (≤2%); bridge non-GND node
voltages (≤0.05); two-tank D8 brackets ⊆ ngspice brackets. Analytic
expectation paired in every test; "ngspice says resonance" never
used. D5/D7 deck mappings reused (voltage-only decks, entering-A
currents summed from branch drops).

## 18. Metamorphic tests

Node/component permutation, A/B swap (identical keys), source
scaling (keys identical; Q within 1E-25 cross-magnitude HP
tolerance, observed 28-digit agreement documented), L-scaling
(f0 halves, bracket maps), Hz/kHz digest equality, repeat
determinism (full `to_dict` equality), ladder N determinism.

## 19. Edge cases

All 35 §28 cases: R-only (Z + flat transfer), series/parallel/
lossless/damped RLC, RC low-pass (endpoint peak, not resonance),
RL high-pass, bridge, ladder, mesh, star, multigraph, K3,3,
non-GND, multi-source (both transfer bases), multi-resonance,
exact zero (synthetic EXACT incl. Z = 0), HP-zero inertness,
brackets, pole-straddle, single sample, empty/dup/decreasing grids,
single-quantity misuse, bad-definition misuse, contradictory
sources (INCONSISTENT, honest), UNCERTAIN gating, two peaks,
flat response, endpoint extrema, ideal-V port, undefined transfer
(V(x,x) input), source/component scaling, A/B swap, rename,
determinism — plus bandwidth-Q accept/reject matrix.

## 20. Security

AST test on `resonance.py`: no eval/exec/compile/open/network/
subprocess/dynamic-import/shell/numpy/cmath/math (getattr exempt:
read-only dataclass access, as documented); blob scan for numeric
Infinity across a full two-tank report. D1–D7 profile kept.

## 21. Provenance

`f8d-ac-resonance/1.0`: circuit refs, observable, criterion,
definition dict, canonical grid keys, threshold-policy stamp,
Q/bandwidth criteria, numeric mode, sweep engine+digest link,
per-point statuses, Q records, conventions; timestamp-free
canonical sha256 (D6 §32 precedent: spelling-dependent D5 sweep
digest linked in provenance, excluded from hash).

## 22. Immutability

Snapshot (refs/types/values/pins/params) before/after scans;
SweepResult/BodeResult digests unchanged by D8; repeated scans
digest-equal. Circuit/ports/sweeps/D5/D6/D7 results unmodified.

## 23. Determinism

Repeat scans: equal digests + equal `to_dict`; findings ordered by
grid; quality ordered by sorted candidate positions; no timestamps,
no dict-order dependence (sorted refs), no identity dependence.

## 24. Performance

Measured splits (4-pt HP scans): N=16: 6.35 s; N=32: 39.7 s;
N=64: 363–441 s (machine variance) — wall time dominated by certified
D3 solves (D8 post-processing is O(points) + ≤2 lazy Q solves per
bracket). No global caching. Caps 120/240/600 s enforced in-test.

## 25. Adversarial audit

1. Im(Z)=0 false positive → reactivity gate + pole note + R-only/RC tests.
2. Pole sign change → parallel-LC straddle test (candidate, never confirmed).
3. Bracket as exact frequency → keys only, "claims no frequency" diagnostics.
4. Q → Infinity → UNDEFINED-lossless; blob scan.
5. Universal f0/BW → energy primary; bandwidth interval-or-UNDEFINED.
6. Peak as resonance → EXTREMUM kind; two-peak test asserts no verdict.
7. Zth vs internal → port-as-seen-by-load documented + tested.
8. UNCERTAIN → invalid by construction, unit-tested.
9. HP near-zero → inert rule, unit-tested.
10. R-only → NO_RESONANCE (Z + transfer).
11. Single-sample → no bracket (tested).
12. Unordered grid → ResonanceError (dup/decreasing/empty tested).
13. Topology hardcoding → transverse generality matrix, no conditionals.
14. Circuit mutation → immutability test.
15. Second solver → none (grep-auditable imports: D3/D4/D5/D6 only).
16. Numeric Infinity → blob scan + UNDEFINED-lossless.
17. Timestamp digest → canonical hash test (repeat + Hz/kHz equality).
18. Finding order → grid-ordered, determinism test.
19. ngspice-only → every NG test pairs analytic expectation.
20. Unsupported-as-solved → statuses propagate verbatim (INCONSISTENT test).

## 26. Limitations

- `ZERO_CONFIRMED` unreachable end-to-end on reactive nets: D3's
  exactness boundary refuses EXACT for any L/C (π), AUTO resolves
  HP; the rule is implemented, specified, and unit-proven on native
  EXACT samples, awaiting a future exact-eligible reactive path.
- Bandwidth-Q needs a D6-defined band + isolated peak; else UNDEFINED.
- Poles/zeros, root finding, interpolation, refinement, resonance
  bandwidth: deferred with acceptance criteria (design §11).
- Q in D7-mode unavailable (no live-circuit branch powers).
- Cross-magnitude HP Q agreement observed at 28 digits (tolerance
  1E-25 documented); N=64 scans are solver-bound (~6 min).

## 27. Regression

Final full suite: collected **1300** = baseline 1232 + D8 delta 68;
**1298 passed + 2 skipped** (same pre-existing reportlab), 0 failed.
D1–D7 files byte-untouched (`git diff` shows only prior units lines
plus the authorized `__init__` export hunk — see §28).

## 28. Diff audit

`git status`/`diff --stat`/`diff`/`diff --check`/`log -5` reviewed:
new `ac/resonance.py`, new `tests/test_f8d8_ac_resonance.py`, new
`docs/gates/GATE-F8D8.md`, `ac/__init__.py` export-only hunk. No
`.stfolder/`, no `pytest-result.txt`, no temp files, no D1–D7
modifications, `units.py` untouched. `git diff --check` clean.

## 29. Commit

`feat(engineering): certify F8-D8 resonance and quality factor`
(LOCAL ONLY — hash recorded in the final implementation report;
no fetch/pull/push/PR/merge; origin untouched).

## 30. Final verdict

All §42 conditions true with evidence above; no scope violation, no
invented frequencies, no invented Q, no false verdicts.

```
F8-D8 PASS — CERTIFIED
```
