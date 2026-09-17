# Quality Gate: F8-D3 — General AC MNA (BLOCKED by out-of-scope defect)

- **Phase**: F8-D3 (third step of F8-D; F8-D1/F8-D2 certified, F8-D4 NOT started).
- **Scope**: single-frequency sinusoidal steady-state MNA ONLY. No power
  subsystem, no Thevenin/Norton AC, no sweep/Bode/transient, no dependent
  sources/transformers/semiconductors, no second Circuit, no second linear
  solver, ngspice as oracle-only.
- **Package**: `src/academic_core/domain/engineering/ac/` (`errors.py`,
  `topology.py`, `operating_point.py`, `phasors.py`, `problem.py`,
  `solution.py`, `solver.py`, `__init__.py`).
- **Tests**: `tests/test_f8d3_ac_mna.py` (105 tests; 104 pass, 1 fails on
  the defect below).
- **Status**: implemented, verified except §D, uncommitted (no commit/push).

> Certified domain: general linear steady-state AC networks composed of
> ideal R/L/C elements and independent V/I sources at a single positive
> operating frequency. Nothing more is claimed.

---

## A. Conventions (frozen)

- Time: `e^(+jwt)` globally. `Z_R=R`, `Z_L=jwL`, `Z_C=1/(jwC)`.
- Amplitude: PEAK everywhere inside the solver (`Vrms=Vpeak/sqrt(2)` is a
  magnitude-domain conversion only; RMS never enters assembly).
- Phase metadata: `Component.parameters["phase"]` + optional
  `phase_unit ∈ {deg, rad}` (defaults 0/deg); float rejected, per-source
  frequency metadata must match the operating point or assembly raises.
- `f > 0`, `w = 2*pi*f` as explicitly approximate Decimal. `f = 0`
  rejected (Option A: DC reduction belongs to a future orchestrator).
  `f < 0` rejected as a product boundary (Fourier significance noted).
- Radian is dimensionless: no new SI dimension; Hz is a Quantity, rad/s
  a documentary label on a plain Decimal.

## B. MNA formulation

Sorted non-ground nodes + one auxiliary current unknown per ideal V
source (F8-B rule). Admittance stamping for R/L/C (GND-aware); V-source
±1 coupling with `V(+)-V(-)=Vs`; I-source `+Is` at `+`, `-Is` at `-`.
Sign table: branch current pin1→pin2 (R/L/C) / +→− (V/I); branch voltage
`V1-V2` / `V+-V-`; reported I-source current `-Is` (F8-B rule, verified
against a 1A→1kΩ hand reference: node rises to exactly 1000 V).

## C. EXACT vs HIGH_PRECISION (§12)

EXACT iff R-only AND every source phase exactly axis-aligned in degrees
(Decimal modulo normalized for dividend-signed `%`; radian phases never
axis-checkable). Any L/C (w brings π) or non-axis phase → HIGH_PRECISION.
Forced EXACT otherwise raises `ACModeError`. Pi is never a Fraction.

## D. BLOCKING DEFECT — D1 `decimal_atan2` near ±45°/±135° (out of scope)

`trig._arctan` evaluates the Taylor series directly for |t| ≤ 1. At
|t| ≈ 1 convergence is ~1/n per term, so the silent 5000-iteration cap
truncates early: `atan2(1,1) = 0.78534816339794...` vs π/4 =
`0.78539816339744...` (error 5e-5; same at 135°). Axes, 30°, 89° and
small arguments are accurate (verified). D1's suite never probed the
|t|≈1 neighborhood, so certification missed it.

Blast radius in D3: exactly one assertion
(`quadrants[45]` phase-angle vs 1E-30; cartesian 45° results are
correct — sin/cos unaffected). All 9 ngspice oracle comparisons pass
(Re/Im/magnitude/phase at their angles). No D1/D2 file was modified
per gate rule 8 (STOP + report).

Minimal correction (proposed, NOT applied): in `_arctan`, for
|t| > 0.5 apply one half-angle step `arctan(t) = 2*arctan(t/(1+sqrt(1+t²)))`
(argument ≤ 0.414 → ~60 terms to 1E-67); replace the silent cap with an
explicit non-convergence error. Then re-run D1+D2+D3 suites.

Also established during diagnosis (documented, no action needed):
D3-level NUMERICALLY_UNCERTAIN is unreachable for F6-input circuits —
triggering it needs >28-digit conspiracies while F6 `to_base()` caps
inputs at the ambient 28 digits (proven by construction: D2 floors are
1E-40 of scale). The status is preserved as a mapping (unit-tested);
D2's suite triggers it. Exact resonance is likewise unrepresentable
(f0 irrational); near-resonance correctly yields SOLVED with huge
current (tested: |I| > 1E6, KCL/KVL ≤ 1E-30).

## E. Verification summary

- KCL physical (per-net leaving-current sums incl. ground; degrees
  2–16, parallel multigraph) and KVL physical (fundamental cycle basis
  with edge identity, E−V+1 counts asserted, V-source edges contribute
  independent Vs phasors): exact 0 in EXACT, ≤1E-38 otherwise.
- Independent refs: hand fractions (R divider/ladder/bridge/multi-node),
  PI50-derived closed forms (RL/RC/RLC series+parallel/divider), hand
  D2 cross-stamp; 9/9 ngspice-47 oracle cases (RC/RL/RLC/bridge/
  parallel/ladder/45°/branches/mesh) incl. phase-sign checks.
- Metamorphic (source×k, R×k physics, permutation≡digest, rename≡,
  conjugation exact, unit-spelling invariant), 100-run determinism,
  immutability (netlist+parameters frozen), AST security (no
  eval/exec/compile/open/subprocess/os/sys/network/pickle/marshal/
  numpy/scipy/math/cmath/float/complex in core; ngspice only in tests).
- Generality: ladders N=2..64 (65×65 HP, KCL/KVL ≤1E-30), bridge, mesh,
  star-16, parallel multigraph, nonplanar K3,3 (exact zeros),
  multi-source R/L/C/V/I mix.
- Regression: 956 passed, 2 pre-existing skips, 1 failed (the §D
  assertion). Zero modifications to tracked files; HEAD unchanged;
  no commit/push/PR/remote changes.

## F. Math-criterion answers (§43, condensed)

1. `e^(+jwt)`. 2. Peak. 3. `mag∠φ` → `mag·(cosφ+j·sinφ)` (D1 trig, HP;
   axis quadrants exact). 4. `w=2πf`, Decimal, Machin π. 5. EXACT iff
R-only + axis-deg phases, else HP (§C). 6. π forces HP; never Fraction.
7–8. Stamps §B. 9. From node phasors + Vs/Is phasors (§B table).
10. Per-net leaving sums incl. GND. 11. Fundamental cycles with Vs edges.
12. Own basis with (branch, sign) steps; parallel edges distinct.
13–14. Inherited 1:1 from D2 + physical hints, never overridden.
15. Near-resonance SOLVED/huge current; exact resonance unrepresentable.
16–17. Rejected explicitly (Option A; Fourier note for f<0).
18. F6 Quantity dims; radian dimensionless. 19. Peak-only solver +
magnitude-only RMS conversion test. 20. ngspice-47 oracle, peak
convention + current direction verified empirically, I-sources excluded
(unprobable branches) with analytical cover. 21. Hand fractions,
PI50 closed forms, hand D2 stamp. 22. Ladders to 64, K3,3, mesh, stars.
23. Read-only input use; netlist+parameters before/after asserted.
