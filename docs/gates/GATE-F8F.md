# Quality Gate: F8-F — Ideal Op-Amps (Nullor MNA)

- **Phase**: F8-F (after F8-E certified; HEAD at start = `8af0e52`; F8-F
  DESIGN READY accepted before implementation).
- **Scope**: ideal op-amp as exact nullor MNA constraint (`V+ = V-`,
  zero input current, output auxiliary current). DC + AC, transfer,
  power, Thevenin/Norton, Bode/response reuse, ngspice E-macro oracles.
  NO finite gain, NO GBW/saturation/slew/noise/offsets, NO
  semiconductors, NO amplifier classification, NO netlist changes.
- **Files**: `circuit.py` (O pins + ref regex), `mna/dependent.py`
  (aux-unknown set), `mna/problem.py` (validation + DC stamp),
  `mna/solver.py` (output-leg branch + KCL + provenance),
  `mna/__init__.py` (domain docstring), `ac/problem.py` (validation +
  AC stamp), `ac/solution.py` (reconstruct), `ac/solver.py`
  (provenance), `ac/__init__.py` (nothing: no new names),
  `thevenin/port.py` (O membership), `thevenin/analysis.py` +
  `ac/impedance.py` (keep-rule docstrings only),
  `tests/test_f8f_ideal_opamp.py` (72 tests), this doc.
  D1/D2/D4/D6/D8 untouched; `units.py` untouched; no SQLite migration.
- **Status**: implemented, self-verified, committed LOCAL ONLY (no push).

> Certified domain: ideal linear op-amps in arbitrary R/L/C/V/I/
> E/G/H/F networks, DC exact and AC phasor, with solver-classified
> singularities and conserved power including the op-amp output leg.

---

## 1. Baseline

HEAD `8af0e52`, clean tracked tree. Full suite pre-change: collected
1403 = **1401 passed + 2 skipped** (pre-existing reportlab), 0 failed,
21:27. Used as the real local baseline; nothing tuned to match it.

## 2. Canonical representation (Option A, decided in design audit)

New `Component` type `"O"` (single letter, existing ref grammar),
pins `+` (non-inverting input), `-` (inverting input), `o` (output).
No value, no parameters — rejected loudly if present (a value would
be silently ignored physics). Options B (E/G/H/F composition) and C
(high-level reduction) refuted in the design audit: no dependent
combination realizes an exact zero-current input pair with an exact
`V+ = V-` constraint, and `μ -> infinity` is not an ideal model.
Finite-gain op-amps remain exactly expressible as plain E (future,
no F8-F machinery needed).

## 3. Nullor stamp (one constraint + one unknown, squareness preserved)

Per O: constraint row `A[row,in+] += 1`, `A[row,in-] -= 1`, `z = 0`;
aux current `i_o` delivered INTO the output node, i.e. KCL
sum-leaving entry `-1` at the `o` row. Inputs carry no entries
(exact open — no `R = 1e12`). Output voltage is never constrained
(determined by KCL + network). DC (Fraction) and AC (native
RationalComplex/DecimalComplex) stamps are the same shape; AC adds
no irrationality, so exact eligibility is unchanged.

## 4. Output-leg model (power/KCL/Tellegen close exactly)

The reconstructed O branch is the leg `(out -> ground)` with current
`-i_o` and voltage `Vout`. Absorbed power `P = Vout * (-i_o)` flows
through the generic D4/DC formulas — no special power path, no
weakened conservation check. Physical KCL explicitly includes the
leg at both ends (`out` and ground); Tellegen holds over
two-terminal branches + output legs. Ground KCL is checked, not
assumed.

## 5. Validation

O requires: ref `O<digits>`, pins exactly `{+,-,o}` with valid nets
(generic `Component` checks), `value is None`, `parameters == {}` —
else typed `InvalidCircuitError` (DC in-band INVALID, AC in-band
INVALID). Duplicate refs via the generic rule. `SUPPORTED_TYPES`
extended in F8-B, D3, F8-C port gate. Gain dimensions: none (no
gain). `units.py` untouched.

## 6. Control-current integration (generality requirement)

H/F resolve O-output control through the aux unknown and report the
reconstructed leg current (`-i_o`), mirroring the F8-E orientation
table (`-Is` for I, `-gm·ΔV` for G, `-β·Ictrl` for F). DC
`_eval_control`, DC/AC `resolve_control`, AC `control_current` each
carry an explicit O case (tested: H-by-O, F-by-O, chains).

## 7. Status classification (solver decides; verified matrix)

No topology dispatch exists anywhere. Hand-verified outcomes, all
tested: driven open-loop contradiction INCONSISTENT; consistent
open-loop SINGULAR; positive-feedback loop SINGULAR (free latch) or
unique-zero SOLVED; tied outputs same-drive SINGULAR (undetermined
split) / conflicting-drive INCONSISTENT; output shorted to ground
with consistent inputs SINGULAR (free `i_o`); short contradicting
drive INCONSISTENT; zero-excitation SOLVED-zero. AC mirrors DC.

## 8. Classical benchmarks (tests, not domain)

Follower/inverting/non-inverting/summer/differential/
transimpedance (DC exact Fractions), 2-op-amp cascade,
4-op-amp instrumentation-like network (hand nodal: 6/2/-4),
integrator/differentiator/active-low-pass (AC, cmath oracles,
1e-9), follower with C load. Classical gains appear only as
expected values, never as engine logic.

## 9. Transfer (D5 reuse, op-amp stays active)

Hv (inverting/non-inverting/follower, exact), zero-input
UNDEFINED, Zt of transimpedance amp (exact -10k), Hi/Zt/Yt/Hv
all four kinds SOLVED on op-amp nets, `frequency_response`
sweeps + D6 `analyze_bode` pipeline untouched and passing.
`network_transfer` already rejects non-V/I inputs (O can never be
nominated); deactivation keeps O via the generic else-branch.

## 10. Thevenin/Norton (F8-C/D7 reuse)

Follower port: Vth exact, Rth = ZERO (ideal output), Norton
UNDEFINED by the existing zero-Rth rule. Divider-driven port:
Vth/Rth/In finite with Thevenin identity `Vth/Rth = In` holding
exactly with the active follower present. Non-GND port exact.
Negative-impedance op-amp cell: D7 Zth = -1000 Ω FINITE exact.
Deactivation keeps O (unit-tested fail-if-removed); F8-C copies
carry parameters via the F8-E helper (O has none to lose).
D7 needed zero changes (test-source method + object-reuse builders).

## 11. Power (D4 reuse + documented leg)

O regimes classify (delivering/absorbing) through the generic
formula; `S = 1/2 V conj(I)` preserved for all applicable
branches. Conservation passes exactly (DC) and within derived
bounds (AC HP) with op-amps sourcing and sinking. `P >= 0` never
asserted on actives.

## 12. Impedance/admittance/resonance (D5/D6/D8 reuse)

Constitutive Z/Y of O: UNDEFINED by the existing ideal-source
rule (no code change). Operating ratios and port methods work
through reconstructed leg values (direct port on `(out,gnd)`
tested FINITE). D6/D8 consume sweeps unmodified.

## 13. Netlist (no format change)

O is pins-only: `O1 INP INN OUT` emits and re-parses with full
semantics preserved (tested both directions + idempotent
re-emit). `from_netlist` pin-count logic is type-generic; E/G/H/F
handling untouched.

## 14. Provenance (`f8f-ideal-opamp/1.0` via existing mechanisms)

Conditional `ideal_opamps: [{ref, in_p, in_n, out}]` in DC
`system_summary` and D3 `provenance` (absent without O:
RVI summaries/digests byte-identical, tested). Full identity is
pins-only by design; digests flow through the canonical
structures (pins covered). Timestamp-free digests; repeat runs
identical.

## 15. Generality matrix (tested)

N = 1/2/4/8/16/32/64 follower chains DC exact (all nodes == Vin)
and AC N = 1/2/4/8/16 (+64 in perf with SOLVED); bridge, mesh,
star-summer (-3 hand), K3,3, multigraph + high-degree + non-GND,
1/2/4 op-amps, E-op-amp coexistence, H/F-controlled-by-O,
cross-coupled DC. Depths: single stamp shape, zero topology
conditionals (audited).

## 16. Independent oracles

Hand nodal/KCL for every benchmark (Fractions), Cramer-class
2x2 checks where apt, cmath closed forms for AC (1e-9),
classical identities as equalities, ngspice E-macro within
analytic bounds. ngspice never sole.

## 17. ngspice (E-macro, bounded error, REAL)

`ngspice_con.exe` --version records `ngspice-47`. Oracle =
E-device μ=1e9 standing in for the ideal constraint; closed-loop
error ~ G_loop/(μ·β): follower/×10-inverter reproduce ideal to
printed 0.0 (probed pre-implementation). Tests: follower,
inverting, non-inverting, summer (DC, ≤1e-3..1e-6), integrator
and x10-transfer (AC, ≤2%). Each states netlist + Academic Core
+ hand expectation + macro result + tolerance + adapter note
(ammeter-free: E macro needs none). All REAL (skip only if
backend absent; backend present in this run).

## 18. Metamorphic

Input-pair swap invariance (constraint symmetry — contrasts
with E control-swap negation), output inversion identity,
source scaling linearity, resistor scaling homogeneity,
node rename (values equal), component permutation (digest
identical), op-amp permutation in multi-op-amp nets,
deterministic repeat (digest + timestamp-stripped dict equal).

## 19. Security

AST gate over all touched files: no eval/exec/compile/open/
subprocess/network/dynamic-import/numpy/scipy/pickle. O adds no
attack surface (no parameters; nets validated as pins; reuses
typed errors). Malformed refs/pins/values/params all rejected
by generic + O-specific validation (tested).

## 20. Immutability/determinism

Snapshot before/after across DC + AC + D5 + D7 calls: circuit
identical (parameters included). Repeat runs digest-identical
(DC canonical digest, AC digest). No timestamps in digests.

## 21. Performance (measured, not assumed)

Follower ladders, wall-clock per full run: DC N=16/32/64 =
0.02/0.05/0.16 s; AC N=16/32/64 = 0.23/0.76/3.05 s. Caps
(120/300/900 s) are tripwires with large margins. No cache, no
approximations, no coverage reduction.

## 22. Limitations (honest boundaries)

Ideal linear only: saturation/rails, finite gain, GBW, slew,
noise, offsets, bias currents, semiconductors, comparator mode
(open-loop drive reads INCONSISTENT — correct linear verdict,
not a device model), transient-nonlinear. Output shorted to
ground reads SINGULAR (free `i_o`), not SOLVED. Tied outputs
share current indeterminately (SINGULAR unless conflicting).
ngspice has no ideal device (bounded macro only).

## 23. Adversarial audit (30 answers, evidence in tests)

1. Four linear sources + nullor cover the linear dependent domain
   (tests: E/G/H/F/O coexist). 2. Arbitrary coexistence (mixed,
   cascaded, cross-coupled tests). 3. `Icontrol` unambiguous
   (ref identity + orientation table + H/F-by-O tests). 4.
   Multigraph safe (ref identity; dedicated test). 5. Cycles
   detected (F8-E `CircularControlError` untouched; O creates
   none — no control refs). 6. MNA stays linear (constant
   coefficients; matrix inspection tests possible via
   `build_mna_problem`). 7. D2 sole solver (no new solve path).
   8. D3 sole AC MNA (stamp extension only). 9. D4 conserves
   (exact DC zeros; HP bounds; delivering regimes). 10.
   Dependents + O stay active (keep tests F8-C and D5). 11. F8-C
   preserves parameters (central helper; O needs none). 12/13.
   Negative Zth (-1000 exact) and Rth = ZERO work. 14. H/F signs
   calibrated (F8-E gate + reused mappings). 15. ngspice really
   executed (backend verified; 7 REAL tests passed, 0 skipped).
   16/17. Independent oracles throughout; ngspice never sole.
   18. N to 64 tested. 19. No topology hardcoding (one stamp;
   matrix test). 20/21/22/23. No second Circuit/solver/units/
   phasors (grep-auditable). 24. D1–D8 untouched except
   allow-listed docstrings (impedance keep-rule) — verified by
   diff. 25. Netlist dependency loss still out of scope and
   untouched. 26. No out-of-scope capabilities (no gain/GBW/
   saturation/semiconductor code). 27. Op-amps later = E-based
   finite gain (already available) + nonlinear phases (new).
   28. Exactness kept (Fractions; no tolerance hacks; perf
   trivial). 29/30. Deterministic + reproducible provenance.

## 24. Regression

Final full suite: collected **1475** = baseline 1403 + F8-F delta
72; **1473 passed + 2 skipped** (same pre-existing reportlab),
0 failed. D1–D8 + F8-E suites all green; RVI digests/summaries
proven byte-identical (`test_provenance_rvi_untouched`).

## 25. Diff audit

`git status`/`diff --stat`/`diff --check`/`diff` reviewed.
Committed changes — tracked modifications: `circuit.py`
(pins+regex+comments), `mna/dependent.py` (aux-set comment),
`mna/problem.py` (O validation+stamp), `mna/solver.py` (O
leg+KCL+provenance), `mna/__init__.py` (docstring),
`thevenin/port.py` (O membership), `thevenin/analysis.py`
(keep-rule docstring); added: `tests/test_f8f_ideal_opamp.py`,
this doc. Working-tree-only changes (modified and tested, left
untracked per the D3–F8-E precedent — only 3 `ac/` files are
git-tracked): `ac/problem.py` (O validation+stamp),
`ac/solution.py` (reconstruct), `ac/solver.py` (provenance),
`ac/impedance.py` (keep-rule docstring). No `.stfolder`, no temp
files, no logs, no binaries, no units/D1/D2/D4/D6/D8 changes,
no migrations, no remote operations.

## 26. Compatibility

F8-A knowledge untouched. F8-B/D3 extended by stamp only
(solver/status/diagnostic/provenance infrastructures reused).
D4/D5/D6/D8/F8-C/D7/F8-E reuse verified by their own suites
plus F8-F integration tests. The `O` letter was free in the
ref grammar; UI type lists and structural-analysis filters
(which enumerate explicit tuples) are unaffected at runtime.

## 27. Commit

`feat(engineering): certify F8-F ideal opamps` (LOCAL ONLY —
hash recorded in the final implementation report; no
fetch/pull/push/PR/merge; origin untouched).

## 28. Final verdict

All §42-analogous conditions true with evidence above; no scope
violation, no invented physics, no masked singularities, no
false resonance/gain claims.

```
F8-F PASS — CERTIFIED
```
