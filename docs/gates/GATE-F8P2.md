# F8-P2 Certification Gate

## Baseline

- Repository `Damaga2005/AcademicCore`, branch `main`.
- Design baseline `93c3dd8` (`docs(gates): add F8-P2 mathematical design
  gate`, verdict `F8-P2 DESIGN READY`).
- Preconditions verified at implementation start: `HEAD = 93c3dd8`,
  `origin/main = 93c3dd8`, branch `main`, working tree clean, no foreign
  changes (no `reset`/`clean`/`restore`/`rebase`/`merge`/`force push`
  used at any point).

## Design Gate

`docs/gates/GATE-F8P2-DESIGN.md` (570 lines, `F8-P2 DESIGN READY`) is the
contract. One design assumption proved infeasible without duplication
(MAX_Z_ORDER 64 vs the REUSEd P1 degree-32 engines) and was resolved
conservatively (see D-R3); one constructor reading (D-R1, constant-den
FIR) and one docstring precision (D-R2, prewarp units) were fixed
explicitly. No tolerance was relaxed; every equation, invariant,
tolerance, status, limit and interface in the gate maps onto certified
or new-audited behavior.

## Scope

DSP per roadmap `:209` (deps F8-P1): uniform sequences, DFT/FFT,
spectral theorems, unilateral causal Z, rational H(z) in `w = z^-1`,
FIR analysis, bilinear design + prewarp, IIR stability (bilinear+Routh
REUSEd), SOS, ideal sampling/Nyquist/alias/reconstruction, digital
margins, `f8p2-dsp/1` serialization + replay. Out of scope kept out:
bilateral Z, quantization/fixed-point, window design, STFT, multirate,
Bluestein, impulse/step-invariant maps, RF/comms (P3/P4), plots/UI/
hardware/filesystem/network.

## Files

| File | LOC | Role |
|:---|---:|:---|
| `dsp/__init__.py` | 128 | Public surface (`ENGINE_VERSION = "f8p2-dsp/1"`) |
| `dsp/sequences.py` | 234 | `Sequence`, ideal samplers (data-driven recipes) |
| `dsp/dft.py` | 251 | Twiddles, DFT/IDFT, radix-2 FFT/IFFT, DTFT, convolution, bins |
| `dsp/ztrans.py` | 255 | `TransferFunctionZ`, Z pairs, S/T, delay coefficients |
| `dsp/filters.py` | 629 | Bilinear design/back, stability, SOS, FIR phase/group delay |
| `dsp/margins_d.py` | 307 | Unit-circle GM/PM/τ (thin bisection solver) |
| `dsp/sampling.py` | 214 | Nyquist, alias map, sinc reconstruction, uniform bridge |
| `dsp/report.py` | 198 | `f8p2-dsp/1` docs, digests (REUSEd), replay/compare |
| `tests/test_f8p2_dsp.py` | 695 | 34 tests P2-001…P2-032+ |
| `tests/test_architecture.py` | +49 | `test_dsp_layer_direction` (extends, never weakens) |

Total new production: 2216 LOC. No new error module (REUSEd
`ControlStatus`/`ControlError` from `control.errors`, gate §Error
Model).

## LOC

See §Files. No certified file modified except the additive
`test_dsp_layer_direction` in `tests/test_architecture.py` (+49/−0).

## Mathematical Validation

| Área | Resultado P2 | Referencia independiente | Error | Límite | PASS |
|:---|:---|:---|:---|:---|:---|
| DFT manual N=4 | `[1,1,1,1]`,`[4,0,0,0]`,`[0,0,4,0]` exactos | cálculo a mano | 0 | exacto | PASS |
| Twiddles | `|W|=1`, ejes exactos | identidades | <1e-48 | 1e-48 | PASS |
| FFT vs DFT N=64 | acuerdo | DFT directa propia | 1.08e-48 | 1e-40·(1+‖x‖) | PASS |
| IDFT round-trip | N=4/64 | suma directa | ≤1e-40 | 1e-40·(1+‖x‖) | PASS |
| Parseval | energías | sumas propias ctx-60 | 0 | rel 1e-40 | PASS |
| Convolución | `DFT(x⊗h)=X·H` | teorema + directa | <1e-36 | propiedad | PASS |
| Shift m=5 | fase `W^{km}` | teorema (mag+fase) | ≤1e-36 | propiedad | PASS |
| Simetría real | `X[N−k]=conj` | teorema | ≤1e-40 | propiedad | PASS |
| Zero-padding 16→64 | interpola DTFT | suma directa | <1e-45 | propiedad | PASS |
| Pares Z | δ/u/a^n/rampa | formas cerradas + ROC | exacto | exacto | PASS |
| H(z) FIR | 1.3125 | suma directa | 0 | exacto | PASS |
| S+T en z | identidad | simbólica + 3 pts | <1e-40 | propiedad | PASS |
| Bilineal 1/(s+1)@8Hz | polo 15/17 | álgebra a mano | rel<1e-12 | exacto | PASS |
| Prewarp π/4 | `\|H\|=1/√2` | Taylor propio | rel<1e-12 | 1e-12 | PASS |
| Round-trip orden 4 | forth/back | evaluación | <1e-40 | 1e-40 | PASS |
| FIR fase II/III | τ=3.5/1.0 | simetría exacta | 0/exacto | exacto | PASS |
| IIR 0.5/1.5/e^{jπ/4} | STABLE/UNSTABLE/MARGINAL | Routh acuerdo | exacto | acuerdo | PASS |
| SOS orden 8 | 4 secciones | evaluación directa | ≤1e-40·(1+‖H‖) | 1e-40 | PASS |
| GM/PM digital | 1.5/75.52° | bisección propia | rel<1e-9 | 1e-9/1e-12 | PASS |
| Alias fs=8,f=5 | 3 | fórmula a mano | 0 | exacto | PASS |
| Reconstrucción | nodos exactos; medio 2/π | Context-80 | rel<1e-9 | 1e-6 | PASS |

Every numeric comparison records absolute error, relative error where
defined, allowed tolerance and PASS/FAIL in-test (§75; no bare
"close enough" anywhere).

## Numerical Validation

- `Decimal` prec 50 at every boundary; `Fraction` exact rails inherited;
  `DecimalComplex` spectra; `float` 0 in `dsp/` (AST + substring audit).
- Twiddle axis snap (multiples of π/2) is mathematically exact, not
  rounding; all other angles via certified range-reduced trig.
- FFT agreement 1.08e-48 ≪ 1e-40 bound (identical flop multiset).
- Bilinear coefficient-exact (`T/2` Decimal factor); round-trip
  algebraically exact, Decimal rounding only.
- Bisection `≤ 1e-12` relative in θ with brackets always reported.
- Reconstruction midpoint tolerance 1e-6 lives ONLY in the truncated
  sinc path with a self-checked tail bound (never extended).
- Routh/rank/GCD/alias/Nyquist/ROC paths exact (no tolerance).

## Analytical References

Hand N=4 DFT vectors; twiddle axis values `(1,−j,−1,+j)`; closed Z
pairs with ROC radii; geometric FIR sum 1.3125; alias `f_a = 3`;
`Ku`-style analog anchors (15/17 pole, `1/√2` prewarp magnitude);
in-test Taylor tan/sin (P1 P-026 precedent) and stdlib Context-80
division/sqrt as independent high-precision paths; own bisection
re-solve for margins; F8-L has NO oracle role (digital filters are not
circuits — gate §14 honored).

## Invariants

`S+T ≡ 1` in z (shared denominator object + numeric); IDFT∘DFT
round-trip; Parseval; real conjugate symmetry; pole-count conservation
through REUSEd DK; ladder↔Routh agreement (else INCONSISTENT); bilinear
forth/back; LHP↔disc both directions; node-exact reconstruction;
insertion-order invariance; frozen dataclasses; content addressing; no
clock/UUID in digests.

## Units

`T: s`, `fs/f: Hz`, bins dimensionless, `θ: rad` label, `z`
dimensionless, `H`/gains endpoint-carried, group delay samples (×T →
s), dB/deg labels dimensionless; `T ≤ 0`/`fs ≤ 0`/mismatched loop units
→ `INVALID`; `Quantity`/`Unit` at the `Sequence` boundary (period must
be TIME dimension).

## Stability

Verdict ladder on REUSEd DK poles (`|p|<1` STABLE, simple-on MARGINAL,
outside/repeated-on UNSTABLE) cross-checked by inverse-bilinear +
REUSEd exact Routh; fixtures 0.5/1.5/e^{jπ/4} agree both rails; DK
non-convergence → honest UNDETERMINED (never guessed); no Jury (one
criterion per plane, gate Q2).

## Determinism

Triple FFT runs bit-identical; triple dumps/digests identical;
insertion-order-invariant digests; deterministic bit-reversal and stage
order; no RNG in `dsp/`; canonical JSON via REUSEd helper.

## Serialization

`f8p2-dsp/1`: closed schema, deterministic dumps, `≤ 64 MiB` guard,
unknown-field/bad-type/bad-JSON rejection, digest recompute (tamper →
INCONSISTENT on load), `str()` Decimals (never `normalize()`),
`DecimalComplex→{re,im}`, no NaN/Infinity/objects/class-names.

## Replay

`EQUIVALENT` (round-trip + triple-run), `RESULT_DIFFERS` (two valid
distinct), `VERSION_MISMATCH` (`f8p2-dsp/2`), `SCHEMA_MISMATCH`
(`f8o-metrology/1`), `INVALID_SERIALIZATION` (non-JSON/tampered);
aliases `VALID`/`RESULT_DIFFERENT` (F8-N/F8-O precedent).

## Security

Literal grep audit over `dsp/` (eval/exec/compile/getattr/setattr/
globals/locals/open/subprocess/pickle/marshal/importlib/socket/urllib/
numpy/scipy/`import math`/`float(`/cmath): 0 matches. AST audit
(P2-029): 0 banned calls, 0 banned top-level imports (incl.
math/numpy/scipy/re), no `lab`/`simulation`/UI/application/
infrastructure edges, 0 float literals, 0 `float(` substrings.
Deserialization typed/allowlisted/size-guarded/digest-verified, never
executes the artefact.

## Architecture

`dsp → {control, math.*, units, metrology.o5 (digest helpers only)}`;
`control↛dsp`, `{mna,ac,lab}↛dsp`, `dsp↛{lab,simulation,UI/FS/network}`
— all enforced by new `test_dsp_layer_direction` (AST, N-110 style) plus
the untouched existing nine architecture tests. DAG acyclic by
construction; no second polynomial/root/stability/MC/units/serde/
sensitivity/replay engine (P2-030 marker grep).

## Resource Limits

`MAX_FFT_N=4096`, `MAX_DIRECT_DFT_N=512`, `MAX_SEQUENCE_N=65536`,
`MAX_Z_ORDER=32` (D-R3: aligned with REUSEd P1 degree-32 engines, was
64 in the design gate — see §Deviations), `MAX_SOS_SECTIONS=16`,
`MAX_BISECT_ITER=200`, `MAX_SERIALIZED=64MiB`,
`MAX_RECON_LOBES=5000`, `MAX_TIME_POINTS` inherited. All enforced with
deterministic INVALID/UNSUPPORTED; budgets are rejections, never
truncations (P2-025 battery).

## Performance

Recorded (P2-031, no wall asserts): FFT n64 0.03 s, n1024 0.83–0.84 s,
n4096 4.3 s (peak bin asserted >1000 for the 256 Hz coherent tone);
bilinear order-32 <0.01 s; TFZ order-32 direct <0.01 s. Bottleneck: FFT
at N=4096/prec 50 (bounded, recorded not asserted). Structural check
(§40): FFT never degenerates to DFT internally (iterative DIT +
bit-reversal, distinct code path, agreement-tested).

## P2 Test Matrix

`tests/test_f8p2_dsp.py`: **34 tests, 34 PASS** (P2-001…P2-032 per gate
matrix plus bench/4096/pins extensions with justification). Types
covered: UNIT, ANALYTICAL, NUMERICAL, PROPERTY, BOUNDARY, ERROR,
SECURITY, DETERMINISM, SERIALIZATION, REGRESSION, PERFORMANCE
(recorded, no wall-clock asserts).

## Regression Evidence

| Suite | Collected | Passed | Failed | Skipped |
|:---|---:|---:|---:|---:|
| F8-P2 new (`test_f8p2_dsp.py`) | 34 | 34 | 0 | 0 |
| F8-P1 (`test_f8p1_control.py`, 51) | 51 | 51 | 0 | 0 |
| F7-B7 (`test_f7b7_gum.py`, 79) | 79 | 79 | 0 | 0 |
| F8-H (69) + F8-I (33+41) + F8-J (29) + F8-K (110) | 282 | 282 | 0 | 0 |
| F8-L (58) + F8-M (87) + F8-N (40+22+16+30+17) + F8-O (70) | 340 | 340 | 0 | 0 |
| `test_architecture.py` (9+1 new) | 10 | 10 | 0 | 0 |
| Rest (app/domain/eng/unit/F7rest/F8a–g/F9/misc/UI) | ≈1571 | ≈1571 | 0 | 2 pre-existing env (reportlab, as in F8-O/P1 gates) |

## Full pytest

Every test file executed across partitioned runs (single-session
timeout strategy from the F8-P1 certification): **0 failed** in all
chunks; the only skips are the 2 pre-existing reportlab environment
skips (documented since F8-O, unrelated). No new skip was introduced.

## Known Limitations

Inherited, unchanged: wrapped F8-L/F8-M oracles keep native tolerances;
P1 DK plateau/multiplicity behavior reused verbatim. New and
documented (see also §84 OUT OF SCOPE): FFT at N=4096 is seconds-scale
(4.3 s measured); multiplicity-≥8 clusters may report honest
DIVERGED/UNDETERMINED through REUSEd paths (never false precision);
reconstruction midpoint tolerance 1e-6 is truncation-only with a
self-checked tail bound; single-wrap phase normalisation (loops below
−360° need extension — outside certified scope); SOS real/complex
decision boundary `CLUSTER_IMAG_TOL=1e-9` (near-real poles pair within
1e-9 coefficient fidelity); endpoint-touching crossovers accepted under
the documented `1e-12` endpoint rule.

## Deviations

- **D-R1 (causality over length)**: constant-nonzero-denominator
  (pure feedforward/FIR, `H(∞)` finite) admitted despite
  `len(num) > len(den)`; feedback-improper forms stay INVALID. Without
  this reading no nontrivial FIR could inhabit `TransferFunctionZ`,
  contradicting gate C6/P2-013. No certified test touched.
- **D-R2 (formula over prose)**: prewarp `omega_d` is analog rad/s per
  the normative equation `Ω_0 = (2/T)·tan(ω_d·T/2)` (else `ω_d·T`
  is not dimensionless); the protected digital point is `θ = ω_d·T`.
  Docstring precision only; mathematics unchanged.
- **D-R3 (no-duplication over bound)**: `MAX_Z_ORDER 64 → 32`,
  `MAX_SOS_SECTIONS 32 → 16`, aligned with the REUSEd P1 degree-32
  engines (Horner/DK/Routh). Order-64 is constructible nowhere without
  a second polynomial engine (§5 forbids it); the limit is tightened,
  never relaxed, and no tolerance changed.
- **Replay vocabulary**: canonical `EQUIVALENT`/`RESULT_DIFFERS`;
  `VALID`/`RESULT_DIFFERENT` tested aliases (F8-N/F8-O precedent).

## Git State

- `git status --short`: `M tests/test_architecture.py`,
  `?? src/academic_core/domain/engineering/dsp/`,
  `?? tests/test_f8p2_dsp.py` (+ this gate + roadmap on commit).
- `git diff --check`: clean. Certified dirs (`mna/ ac/ lab/
  metrology/ control/ gum.py`): byte-unchanged per `git diff HEAD
  --stat` (empty).
- Commit: `feat(engineering): certify F8-P2 digital signal processing`
  (single commit, no `git add .`, no force).

## Final Verdict

F8-P2 CERTIFIED
