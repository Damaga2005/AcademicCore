# Quality Gate: F8-D4 — AC Power Analysis & Complex Power Foundation

- **Phase**: F8-D4 (fourth step of F8-D; F8-D1/D2/D3 certified).
- **Scope**: complex power over F8-D3 solutions ONLY. No RMS phasors,
  no transient/sweep/Bode, no dependent sources/nonlinear devices/
  transformers, no Thevenin/Norton AC, no hardware I/O.
- **Files**: `src/academic_core/domain/engineering/ac/power.py` (new),
  `src/.../units.py` (+2 additive base units), `ac/__init__.py` (exports),
  `tests/test_f8d4_ac_power.py` (61 tests), this doc.
- **Status**: implemented, self-verified, uncommitted (no commit/push).

> Certified domain: per-element and global complex power (S/P/Q/|S|/PF
> with absorbed-positive convention) for general linear steady-state AC
> networks of ideal R/L/C and independent V/I sources at one positive
> frequency, from peak phasors under `e^(+jwt)`.

---

## 1. Formulas (peak phasors, mandatory 1/2)

`S = 1/2 · V_branch · conj(I_branch)`, `S = P + jQ`, `P = Re(S)`,
`Q = Im(S)`, `|S| = √(P²+Q²)`, `PF = P/|S|`. The 1/2 is `Fraction(1,2)`
/ `Decimal('0.5')`, never float. `S = V·conj(I)` is never used on peak
phasors. RMS appears only as magnitudes (`Vrms = |Vpeak|/√2`); the
identity `S = Vrms·conj(Irms)` (complex RMS phasors = peak/√2) is a
required consistency test that catches any 1/2-factor bug.

## 2. Signs (uniform absorbed convention, no source special-casing)

D3 orientations reused verbatim (pin1→pin2 R/L/C, +→− V/I; V-branch
voltage = independent Vs; I-branch current = −Is). Hence: R absorbs
(P≥0, Q=0, PF=+1); L absorbs vars (P=0, Q>0); C delivers vars (P=0,
Q<0); sources absorb or deliver by sign (P<0 delivering, PF=−1 for a
resistive delivering source). Q>0 = inductive, Q<0 = capacitive under
`e^(+jwt)`; PF sign (absorb/deliver) is never read as lead/lag.

## 3. Zero/active policy

`|S| == 0` exactly → `PF = None` + explicit diagnostic; no division
executes, no epsilon converts zero. Small-but-nonzero computes normally
(no clamping, no forced PF=0). Regimes from exact comparisons:
zero / reactive-only / absorbing / delivering.

## 4. Units

`var`/`VA` added as `POWER`-dimension base units in F6 (`units.py`,
strictly additive: no dimension/conversion/W/prefix behavior changed;
`_unit_for_dim(POWER)` still returns W). W/var/VA are role labels over
one physical dimension — separate dimensions would be dishonest. PF is
a plain `Decimal|None`. Verified: W/kW/var/kvar/mvar/VA/kVA parse,
convert, and display correctly.

## 5. Conservation (Tellegen, necessary-not-sufficient by design)

`ΣS` accumulated in sorted-ref order. EXACT: must equal `0+0j`
identically. HP: derived two-term bound
`|ΣS| ≤ max|V|·N·kcl_max + M·64·ulp·max|S|` — identity defect from
`Σ_b Vb·conj(Ib) = Σ_n Vn·conj(KCL_n)` plus a fixed, generous
working-precision rounding account (counted basis, never fitted; the
KCL-only first term provably under-bounds because power products add
their own solve-propagated rounding). P and Q covered by the same
bound. Sufficiency is NOT claimed from ΣS=0 (global sign flips preserve
it): element laws, PI50 closed forms, hand fractions, multi-source
cross-term tests and the ngspice oracle jointly pin every sign.

## 6. Numeric modes

EXACT: S/P/Q exact (`RationalComplex`/`Fraction`); `|S|`, PF, RMS
explicitly approximate Decimals (D1 modulus semantics). HP:
`DecimalComplex`/Decimal under the D1 working context. No third model,
no float/complex/math/cmath/numpy. Non-SOLVED solutions refused
(`PowerAnalysisError` — power without (certified) branch quantities
would be numerology).

## 7. Tests (61)

Element laws (R/L/C/RL/RC/RLC/parallel ×3), topologies (bridge/ladder/
mesh/star-12/parallel/nongnd), sources (deliver/absorb/I/multi/mixed),
zero+PF table (S=0 ×2, PF None/+1/−1/0, Q±), conservation (exact zero,
HP bound formula equality + tightness, refusal, standalone), peak/RMS
(½-factor, RMS identity, peak≠RMS), PI50 closed forms, cross-terms
(non-linearity with hand fractions), metamorphic (k² exact/tol,
permutation≡digest, rename≡, conjugation algebraic-only), 7 ngspice-47
oracle cases (|S|/P/Q/sign/source/element, I-source analytical-only per
documented harness limit), ladders N=1..64, immutability, 100-run
determinism, AST security, provenance (keys, no timestamp, stable/
sensitive digest linked to solution digest).

## 8. Provenance / determinism / security

Keys: engine `f8d-ac-power/1.0`, frequency, ω, temporal/amplitude/power
conventions, numeric mode, branch refs, bound, conservation result,
solution digest, deterministic sha256 digest (no timestamp).
Read-only over Circuit/ACSolution (netlist+provenance before/after
asserted). AST: no eval/exec/compile/import-magic/open/subprocess/os/
network/pickle/marshal/math/cmath/float/complex/numpy; no new deps
(stdlib + intra-package only).

## 9. Regression & boundaries

Full suite must show 961 + 61 = 1022 passed with the same 2 skips; no
file touched outside `ac/power.py`, `ac/__init__` exports, the units
2-liner, D4 tests, this doc. No commit/push/PR/remote. F8-D5 NOT started.

## 10. Known limitations

HP `regime` follows exact comparisons (tiny-noise P classifies
absorbing — by §3 mandate, no epsilon); PF of near-zero-S systems is
computed unclamped (documented); I-source oracle coverage is analytical
(harness limit); power of UNCERTAIN solutions refused by design.
