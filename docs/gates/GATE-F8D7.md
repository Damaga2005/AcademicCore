# Quality Gate: F8-D7 — General AC Thevenin & Norton

- **Phase**: F8-D7 (seventh step of F8; F8-D1…D6 certified).
- **Scope**: one-port AC equivalents (Vth/Zth/In/Yn) over D3 solutions
  ONLY. No dependents/nonlinear/transformers, no resonance/Q/poles/
  zeros/filters/RMS/symbolic/optimization/UI/persistence.
- **Files**: `ac/thevenin.py` (new), `ac/__init__` exports (strictly
  necessary), `tests/test_f8d7_ac_thevenin_norton.py` (52 tests), this
  doc. Zero modifications to certified files.
- **Status**: implemented, self-verified, local commit only (no push).

> Certified domain: Thevenin (`Vth` open-circuit, `Zth` deactivated
> test-source) and Norton (`In` short-circuit, `Yn` V-test) equivalents
> of arbitrary two-terminal ports in general linear steady-state AC
> networks (ideal R/L/C, independent V/I, single f > 0, peak phasors,
> `e^(+jωt)`).

---

## 1. Formulas

`Vth = VA − VB` (live solution; co-located branches are internal and
stay connected). `Zth` = D5 test-source impedance on the deactivated
network — always the test method, never the direct ratio (different
questions). `In` = short-circuit current entering A, measured directly
with a 0 V source across the port (never `Vth/Zth`, which fails exactly
where Norton gets interesting). `Yn` = independent D5 V-test
measurement (never `1/Zth`). With `In` entering A, the invariant reads
`Vth + In·Zth = 0` (textbook `Vth = Isc·Zth` uses the A→B current, i.e.
the negation) — reported, never enforced.

## 2. Signs

Port current entering A everywhere; MNA unknowns (+→−) negate on read.
`Vth' = −Vth`, `In' = −In`, `Zth' = Zth`, `Yth' = Yth` under A/B swap
(tested). Ideal-source ports: `(Vs, 0)` Thevenin valid with UNDEFINED
Norton (short contradicts Vs≠0) — the physically correct answer, not a
failure.

## 3. Categories / statuses

D5 `FINITE/INFINITE/UNDEFINED` for Zth/Yn (INFINITE vocabulary-reserved;
test-source measurement yields FINITE incl. exact zero or UNDEFINED —
documented, since a forced 1 A test current always produces a finite
ratio or a solver verdict). Parent ACStatus inherited verbatim
(SOLVED/SINGULAR/INCONSISTENT/UNCERTAIN/INVALID/UNSUPPORTED); the
UNCERTAIN branch is the shared `!= SOLVED` path (structurally covered;
organic UNCERTAIN needs >28-digit conspiracies per the D3 proof).
Sub-measurement failures degrade single fields with diagnostics —
verdicts preserved, never replaced.

## 4. Modes / precision

Parent mode inherited end-to-end (R-only stays `RationalComplex`
exact, incl. digest stability); HP uses D2 precision + backward error
(provenance). No third numeric model, no float/complex, no faked
exactness (EXACT refused on decimal data by D2).

## 5. Generality evidence

Ladders N=1…64 with hand series/parallel reduction oracles (exact),
series/parallel/bridge/mesh/star/K3,3/multigraph, GND/non-GND/arbitrary
ports, multi-source with phases, R/L/C families, magnitudes 1e-9…1e12.
No topology conditionals in core (single generic path).

## 6. Independent verification

Hand nodal/Cramer/fraction derivations (divider, bridge with full
`Vth/Zth/In/Yn` hand values, ladder reduction, superposition,
superposition-violating cross-terms avoided by construction),
PI50 closed forms (RC/RL/RLC), F8-C parity (`Rth`/`Vth` agree incl.
exact privates), resistive-load checks (`Vth·ZL/(Zth+ZL)` vs loaded
full solve, exact), 8 REAL ngspice-47 cases (Vth/Zth/In/Yn, mag/phase/
Re/Im, explicit tolerances) reusing D5-established mappings only
(source-current negation, swapped Itest terminals, voltage-only decks
for I-source circuits, exact single-frequency decks).

## 7. Metamorphic / integrity / security

Permutation/rename digests, A/B swap laws, source scaling (Vth/In ×k,
Zth/Yn invariant), impedance scaling (Vth same, Zth ×k, In /k — derived,
not assumed), `Zth·Yn = 1` + `Vth + In·Zth = 0` when finite,
determinism (repeat digests), immutability (netlist + component count
before/after every operation incl. deactivation/short/load), AST clean
(no eval/exec/compile/import-magic/open/subprocess/os/network/pickle/
marshal/float/complex/math/cmath/numpy), deterministic timestamp-free
digests, full §20 provenance incl. solver statuses, residuals and
solution digest.

## 8. Regression & boundaries

Full suite must read 1178 + 52 = 1230 passed with the same 2 reportlab
skips; scope is exactly the four authorized paths; performance split
(build/solve/post) measured with loose caps, no caching. F8-D8 and all
out-of-scope items untouched.

## 9. Known limitations

`INFINITE` Zth/Yn unreachable via forced test-source (documented
category, not a gap in code); Norton requires a solvable shorted
system (ideal-V ports correctly UNDEFINED); load verification is
resistive-only by documented scope; `0 Hz`/negative-f rejected by D3
before D7 runs.

---

F8-D7 STATUS:
PASS — CERTIFIED
(Reconciliation: baseline collected 1180 = 1178 passed + 2 skipped;
D7 delta collected 52 = 52 passed + 0 skipped; final collected 1232 =
1230 passed + 2 pre-existing reportlab skips + 0 failed. Exact.)
