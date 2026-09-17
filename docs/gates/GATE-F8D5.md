# Quality Gate: F8-D5 — AC Impedance, Admittance & Frequency Response

- **Phase**: F8-D5 (fifth step of F8-D; F8-D1…D4 certified).
- **Scope**: branch/port impedance/admittance, four transfer kinds,
  single-point response + deterministic sweep, all over F8-D3 solutions
  at single positive frequencies. No filters/Bode/poles/zeros/resonance
  verdicts/RMS/transients/dependents/nonlinear/UI/persistence.
- **Files**: `ac/impedance.py` + `ac/response.py` (new, the only two
  modules allowed), `ac/__init__` exports, `units.py` (+ADMITTANCE
  dimension, `S` base, siemens aliases), `tests/test_f8d5_impedance.py`
  (90 tests), this doc.
- **Status**: implemented, self-verified, uncommitted (no commit/push).

> Certified domain: constitutive and operating-point impedance/
> admittance of any branch, two-terminal port impedance/admittance
> (branch-coincident or arbitrary via test source), voltage/current/
> transimpedance/transadmittance transfer functions, and deterministic
> linear/explicit-list frequency sweeps — for general linear
> steady-state AC networks of ideal R/L/C and independent V/I sources.

---

## 1. Units (D5-A)

`ADMITTANCE = (-1,-2,3,2,0,0,0)` derived from A/V = 1/Ω (verified:
`S×Ω` dimensionless, `A/V` converts to mS). `"S"` base appended last so
every previously valid parse is untouched; `"siemens"/"Siemens"`
aliases; prefixes (`mS…GS`) coherent. Documented reinterpretation:
`mS/uS/nS` previously fell through to *seconds* and now correctly read
millisiemens & co. (`ms` stays milliseconds — pinned by collision
tests asserting `ms != mS` dimensionally). F6 suite green; no dimension,
conversion, W behavior, or prefix altered.

## 2. Branch impedance/admittance (D5-A)

Constitutive (element property, valid unexcited): R/L/C from D3's
branch admittance (`Z = 1/Y`; `Y` taken directly, never `1/Z`); ideal
sources UNDEFINED by rule (load-imposed V/I is not an impedance).
Operating ratio V/I resp. I/V from solved quantities, any branch,
labeled `operating-ratio`: FINITE (incl. exact zero), INFINITE (zero
denominator, nonzero numerator), UNDEFINED (0/0). No
`Decimal("Infinity")`/`float("inf")` — infinity is a category with
`value=None`. Zero tests representation-exact; small-but-nonzero
computes normally. Orientation: D3 conventions kept; constitutive
orientation-independent; ratio jointly invariant (proved by test, not
assumed). Magnitude/phase via the D1 authority; cartesian preserved;
`magnitude_in()` returns dimensionally honest F6 Quantities (round-trip
through `to_base()`, honoring F6's ambient-context boundary explicitly).

## 3. Ports + test source (D5-B)

`PortDefinition(A,B)`: `Vport = VA−VB`, `Iport` entering A — one
convention. Unique branch coincidence → direct readout (orientation
mapped); shared/no branch → test-source method required (ambiguity
raises, never guessed). Test source: FRESH derived circuit (original
byte-identical before/after, tested), V→0V short (MNA structure kept),
I→removed, 1A entering A (impedance, `Zport=Vport`) or 1V + at A
(admittance, `Yport=Iport` = negated MNA unknown), first-free
deterministic ref recorded in provenance. Non-SOLVED derived solves
degrade to labeled UNDEFINED carrying the solver status: INFINITE is
open behavior of a solved system, SINGULAR/INCONSISTENT verdicts are
preserved, never converted. Proved behaviors: direct-vs-test diverge
correctly (branch property R2 vs network R2‖R1), agree where they must
(series current loop), dead networks answer only via test source,
shorted ports read exact zero, reversed ports are reciprocal-equal.

## 4. Transfers (D5-C)

One `TransferFunction(kind, input, output, value|None, defined, basis,
unit, input_source, diagnostic)` for Hv/Hi/Zt/Yt with unambiguous
endpoints (`V(A,B)` / branch current in D3 orientation). Zero input →
UNDEFINED (no limit analysis). `network-transfer` (others deactivated,
excitation kept, provenance says so) vs `operating-point-ratio`
(labeled observation) — distinguished by construction and test
(1/2 vs 1/3 on a two-source network). No filter semantics.

## 5. Sweep (D5-D)

Per-point independent analysis (fresh operating point → D3 → D5
quantity; no MNA reuse, no cache). Explicit Hz lists + linear grids
(explicit-context step math; log deferred with documented reason:
fractional-power primitive absent). Failed points recorded with status
+ diagnostic, sweep continues (`completed` /
`completed_with_point_failures`); order/values/digest fully determined
(N=1…1000 tested: 1000-point tiny sweep green). Partial-failure path
proven by frequency-metadata-mismatch and all-singular sweeps. f=0,
f<0, wrong dimensions rejected as user errors.

## 6. Precision / phases / resonance / Bode

Mode inherited from the parent solution (never recomputed); R-only
stays exact end-to-end (proved: divider port `2000/3` exact). D1
`phase()`/`modulus()` exclusively (45°/135°/±180°/quadrant
regressions); wrapped (−π,π] always labeled; no unwrap. `Im(Z)` reported
as data; no RESONANT verdicts, no Bode/poles/zeros APIs.

## 7. Generality evidence

Seeded random R networks (N=1…64, ratio==property exact + Z·Y=1),
ladders to 64 nodes, bridge/mesh/star-12/K3,3/multigraph (parallel
R/L/C/V/I with edge identity — ambiguity raises), non-GND and
arbitrary ports, multi-source. No topology conditionals in core
(audited).

## 8. Independent verification

Hand Cramer 2×2/3×3 port values, series-ΣZ / parallel-ΣY oracles,
PI50 closed forms (RC/RL/RLC/transfer magnitude), hand nodal bridge,
deactivation hand derivations — all in Fractions/transcribed Decimals,
no D5 functions in oracle paths. ngspice-47 REAL oracle (11 cases:
branch Z ×3, gain+Zin, bridge, arbitrary port via mirrored derived
deck, non-GND port, current-source nodes, multi-source, sweep):
magnitude + wrap-aware phase + Re/Im with explicit tolerances.
Empirically pinned mappings (D3 `i(v1)` precedent honored): oracle
branch/port currents negate the +→− source current; ngspice I-sources
flow +→− (opposite D3 delivery-into-+) — both probed twice, documented
in-test, never assumed. Multi-point sampler nearest-match hazard found
during work → per-frequency exact decks by construction.

## 9. Metamorphic / integrity / security

Amplitude invariance of Z/H (exact + HP), per-element R/L/C and
f→kf scaling laws (derived, network-global laws explicitly refused),
rename/permutation invariance, conjugation algebraic-only, KCL-derived
oracle currents. Immutability (netlist/params/solution bytes before/
after every operation incl. deactivation), idempotence (repeated
measure/transfer/sweep digests), determinism. Provenance: engine/
version/kind/f/ω/mode/port+orientation/endpoint defs/deactivation +
test-source spec/sweep def + ordered frequencies + per-point status/
tolerances/categories/timestamp-free digests. AST: no eval/exec/
compile/import-magic/open/subprocess/os/network/pickle/marshal/math/
cmath/float/complex/numpy; stdlib + intra-package imports only.

## 10. Regression & hardening

Full suite must show 1022 + 90 = 1112 passed with the same 2 reportlab
skips; historical pins: ms/mS, no synthetic units, multigraph edge
identity, GND variants, F8-C coexistence (D5 port == Rth `2000/3`
cross-engine + A/B polarity), D1 45°/π edges, D2 status propagation
(no UNCERTAIN→FINITE laundering), D3 peak/sign/`e^(+jwt)`, D4 power
untouched. Performance measured (single/10/100/1000-point sweeps,
loose caps, linear shape, no caching claimed).

## 11. Known limitations

Test-source port on a shorted port reads the short (correct, documented);
V-test across a deactivated source is contradictory by construction
(labeled, tested); log grids, unwrap, resonance verdicts, RMS phasors
deferred with reasons; sweep cost is N×solve (measured, uncapped
architecturally).

## 12. Certification criteria

Table §82: all rows must read PASS (units, branch, port, arbitrary,
test-source, transfers, sweep, exact, HP, generality, ngspice,
metamorphic, immutability, determinism, provenance, security,
regression, scope) with the reconciled counts
(collected/passed/failed/skipped = baseline + D5 delta).
