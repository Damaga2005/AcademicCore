# F8-P2 Design Gate

Design gate for **F8-P2 — DSP (discrete-time signal processing)**.
Documentation only: no code under `src/` was created or modified, no
tests were written, no engine was altered. The only output of this
phase is this file plus one local commit (no push).

## Baseline

- Repository `Damaga2005/AcademicCore`, branch `main`, baseline **`3f8129a`**
  (`feat(engineering): certify F8-P1 control systems`), `HEAD == origin/main`
  (verified at audit time; working tree clean).
- Certified at baseline: F0–F7 (incl. F7-B7 GUM), F8-A … F8-P1
  (gates on disk through `GATE-F8P1.md`; roadmap §6.1 lists F8-P1
  CERTIFICADO and marks **F8-P2 (NEXT)** per §5.1).
- Working tree clean at audit time (`git status --short --branch` →
  `## main...origin/main`, no entries).

## Scope

F8-P2 is the **discrete-time DSP layer** over the certified engines. It
adds **no circuit solver, no Bode engine, no transient integrator, no
sampler core beyond the ideal uniform model, no GUM math, no second
polynomial/root/stability/serialization engine**. It adds:

| ID | Capability |
|:---|:---|
| C1 | Uniform sequences `x[n]` + DFT/IDFT definitional core (direct exact sums) |
| C2 | Radix-2 FFT/IFFT as exact reorderings + twiddle unit-magnitude gate |
| C3 | Spectral theorems: Parseval, circular convolution, shift/modulation, real-input symmetry |
| C4 | Unilateral Z-transform of causal sequences, standard pairs, exterior ROC |
| C5 | Rational `H(z)` in `w = z^-1` (REUSEd polynomial reading), unit-circle evaluation, `S+T ≡ 1` |
| C6 | FIR analysis (linear phase, group delay) + IIR stability via bilinear map + REUSEd Routh, DK cross-check |
| C7 | Bilinear design from P1 TF prototypes (+prewarp, round-trip) + SOS cascade (REUSEd DK) |
| C8 | Ideal uniform sampling model, Nyquist verdict, closed-form alias map, node-exact reconstruction identity |
| C9 | Digital GM/PM on the unit circle (thin bisection solver, pattern-inherited) |
| C10 | Canonical serialization `f8p2-dsp/1` + digests + replay/compare (F8-N/F8-O pattern) |

## Non-Scope

| Item | Reason | Future home |
|:---|:---|:---|
| Non-causal / bilateral Z-transform | Breaks exterior-ROC uniqueness; unbounded scope | later DSP phase |
| Quantization / wordlength / finite arithmetic effects | No certified quantization model; would fake physics | future fixed-point phase |
| Window design (Hann/Hamming/…), Parks–McClellan | Design-method machinery beyond analysis scope | future filter-design phase |
| STFT / overlap-add / multirate / polyphase | Needs framing + rate-change engines | future spectral phase |
| Bluestein / arbitrary-N fast transforms | DFT-direct fallback ≤512 covers it honestly | future if profiled |
| Impulse/step-invariant discretization | Needs integration machinery + aliasing subtleties; bilinear is algebraic | future |
| Time-varying / adaptive filters | No certified adaptation model | never in P2 |
| New Bode/sweep/transient/sampler/GUM/poly/root math | Certified in F8-D5/D6, F8-L, F8-M, F7-B7, F8-P1 | reused, never rewritten |
| RF/comms (Smith, S-params, BER, Shannon) | Explicitly F8-P3/F8-P4 per roadmap:210–211 | F8-P3/F8-P4 |
| Plots/GUI/hardware | Domain stays UI/hardware-free (`test_architecture.py`) | presentation layer |

## Repository Evidence

1. **Git**: `main`, `HEAD == origin/main == 3f8129a`; log head `3f8129a`
   (F8-P1 certification), `f762ccb` (F8-P1 design gate), `56136f7` (F8-O).
   Remote `origin https://github.com/Damaga2005/AcademicCore.git`.
2. **F8-P2 definition** (roadmap only; zero `src/`/`tests/` DSP hits):
   - `ROADMAP.md:170`: `F8-P2 DSP [8º] (NEXT)`.
   - `ROADMAP.md:209`: deps `F8-P1`; scope
     “FFT/DFT, transformada Z, FIR/IIR, muestreo, aliasing”.
   - `ROADMAP.md:271`: F8-P1 certified, **F8-P2 (NEXT)**.
   - Downstream: `ROADMAP.md:210` (F8-P3 needs F8-P2),
     `:211` (F8-P4 needs F8-P2), `:212` (F8-P5 integrates P1…P4).
3. **P1-side boundary markers** (the certified code says what P2 is):
   - `GATE-F8P1-DESIGN.md:45`: “Sampled-data / Z-transform / FIR/IIR —
     Explicitly F8-P2 DSP per roadmap:209”.
   - `GATE-F8P1-DESIGN.md:107`: “F8-P2 (DSP) needs P1 transfer
     vocabulary” (the P1→P2 dependency, §6 below).
   - `control/response.py:164-180`: the only `sample*` hits in
     `control/` are collocation points (unrelated s-domain numerics).
4. **No-duplication grep** (`src/`, case-insensitive): `fft|dft|FIR|
   IIR|aliasing|Nyquist|Z-transform|ztransform|downsampl|upsampl|
   windowing|Hann|Hamming|Blackman|Bartlett|welch|periodogram|Goertzel|
   chirp` → only `ZERO_CONFIRMED` false positives in `ac/resonance.py`
   (unrelated resonance verdicts). `sampl*` hits are the legacy
   float-world `simulation.py` signal containers (forbidden to domain
   code since F8-P1), GUM Type-A observations, and MC sampling —
   no DSP engine. `TODO|FIXME|NotImplemented|placeholder` in
   engineering → only Python-protocol `NotImplemented` returns,
   superseded `models.py` ideal placeholders, and unrelated tracks
   (PDF providers, migration).
5. **Reuse surface (audited)**:
   - F8-P1 `control/`: `Polynomial`/`make_polynomial` (Horner,
     indeterminate-agnostic), `TransferFunctionTF` (bilinear preimages),
     `routh_of_poly` (exact `Fraction`), `durand_kerner_roots` +
     backward gate (SOS pairing, pole inventory), `ControlStatus`/
     `ControlError` vocabulary, `decimal_exp` pattern (cos/sin pairing),
     `f8p1-control/1` + replay vocabulary (pattern source).
   - Math: `DecimalComplex`, `decimal_cos/sin/atan2/pi/sqrt`
     (range-reduced, prec 50), `decimal_nth_root`, `Fraction` exactness,
     `Quantity`/`parse_unit` (Hz, s, dimensionless dB/rad/deg labels).
   - F8-N `lab/`: `Waveform` is a continuous-time piecewise-linear model
     over committed `(t_i, x_i)` — a different object from uniform DSP
     sequences (no uniform sampler exists; N-110 forbids any `dsp→lab`
     import edge, so Waveform→Sequence conversion is structural).
   - F8-O `metrology/o5_traceability.py`: `canonical_json`/
     `chain_digest` (`sha256(tag‖0x00‖canonical)`) function reuse;
     F8-M `MAX_SWEEP_POINTS=2000` bound precedent; F8-L oracle role does
     NOT transfer (digital filters are not circuits — analytic +
     property references instead, §14).

## Motivation

P2 turns the certified continuous-time stack into discrete-time
engineering: spectra of measured/simulated waveforms (via F8-N/F8-L
data, converted structurally), digital counterparts of P1-designed
loops (bilinear design from P1 prototypes), and the vocabulary F8-P3
(frequency-domain maturity) and F8-P4 (modulations need DFT) build on.
The roadmap orders it first among the P-phases after P1 for exactly
this reason. Every P2 computation bottoms out in certified arithmetic;
P2 contributes only the discrete-time mathematics the repo provably
lacks (§Repository Evidence 4).

## Existing Infrastructure

See reuse surface above. Structural rule inherited: `dsp/` may import
`control/` (downstream consumption — acyclic: `control/` never imports
`dsp/`, tested like N-110), `math.*`, `units`, and the digest helpers
of `metrology.o5_traceability`; it may **not** import `lab/` (N-110),
`simulation.py` (float world), UI/application/infrastructure, or any
network/filesystem/process module. No second polynomial, root,
stability, Monte Carlo, units, serialization, sensitivity, or replay
implementation.

## Mathematical Specification

### Domain

- **Objects**: causal uniform sequences `x[n]`, `n = 0..N−1`, `N ≥ 1`,
  real or `DecimalComplex` entries (finite `Decimal`s); sampling period
  `T > 0` (`Quantity`, seconds), `fs = 1/T`; rational
  `H(z) = B(w)/A(w)` in `w = z^-1` with `deg_w B ≤ deg_w A`
  (causal properness; violation → `INVALID`); FIR/IIR coefficient
  vectors; DFT bins `k = 0..N−1`.
- **Variables**: `n` (dimensionless index), `z ∈ ℂ` (dimensionless,
  evaluated as `DecimalComplex`), `f ∈ ℝ` (Hz), normalized
  `ν = f/fs ∈ [0, 0.5]`, digital `θ = 2πν` (rad, label), loop gain
  `K ∈ ℝ_{>0}` (digital locus/margin parameter, same contract as P1).
- **Units**: `x[n]` carries endpoint units via `Quantity`; `T`: `s`;
  `fs/f`: `Hz`; `z/θ/bins`: dimensionless (bins) / rad label;
  `H`, filter gains: endpoint-carried (`[u_out]/[u_in]`, P1-PID
  precedent); group delay: samples (×T → s); dB/deg: dimensionless
  labels (F8-N precedent). `T ≤ 0`, `fs ≤ 0`, non-finite ingress →
  `INVALID`.
- **Representation**: sequences as tuples (insertion-ordered, canonical
  JSON preserves order); `H(z)` ascending in `z^-1`
  (`b_0 + b_1 z^-1 + …`), normalised once at construction to P1
  descending-in-`w` polynomials (deterministic reversal); complex
  spectra as `DecimalComplex` tuples; exact side computations as
  `Fraction` where specified.

### Core definitions

1. **DFT/IDFT** (exact finite sums, no iteration):
   `X[k] = Σ_{n=0}^{N−1} x[n]·W_N^{kn}`,
   `x[n] = (1/N)·Σ_{k=0}^{N−1} X[k]·W_N^{−kn}`,
   `W_N = e^{−j2π/N}` via certified `decimal_cos/sin` (never `float`,
   never a trig literal). The IDFT `1/N` factor is exact Decimal
   division under the working context.
2. **Radix-2 FFT/IFFT**: decimation-in-time exact reordering of the
   same sum (`N = 2^m` required; non-power-of-2 → `INVALID` pointing at
   DFT-direct, never a silent Bluestein). Twiddle gate
   `|W_N^{kn}| = 1` per factor ( Backward-style per-element check).
3. **Z-transform** (unilateral, causal-only):
   `X(z) = Σ_{n≥0} x[n]·z^{−n}`, ROC exterior `|z| > R` recorded on
   every transform; pairs `δ↔1`, `u↔1/(1−w)`, `a^n·u↔1/(1−a·w)`,
   `n·a^n·u↔a·w/(1−a·w)²` (`w = z^-1`); delay
   `x[n−k]·u[n−k] ↔ w^k·X`; advance of causal sequences is
   non-causal → `UNSUPPORTED` (explicit, not a silent shift).
4. **Rational H(z)**: evaluation by REUSEd Horner at `w_0 = 1/z_0`
   (`z_0 = 0` with `B(∞)≠0` form → `SINGULAR`, the digital analogue of
   the P1 pole rule); `S(z) = 1/(1+L)`, `T(z) = L/(1+L)` share one
   denominator object ⇒ `S + T ≡ 1` symbolically in `z`.
5. **Bilinear design** (the P1→P2 bridge): for a P1 prototype `H(s)`
   and `fs`, `s = (2/T)·(z−1)/(z+1)` coefficient-exact
   (`T/2` Decimal factor); prewarp
   `Ω_0 = (2/T)·tan(ω_d·T/2)` for one protected cutoff (in-test Taylor
   reference); Nyquist prewarp (`ω_d = π/T`) → `UNSUPPORTED` (maps to
   infinite analog cutoff — documented singularity, not a number);
   analog pole at exactly `s = 2/T` (maps to `z = ∞`) →
   `UNSUPPORTED` degenerate. Round-trip
   `TF(s)→H(z)→TF(s)` is algebraically exact (tested `< 1e-40`).
6. **Stability** (no second criterion): poles from the REUSEd DK core
   on `A(w)`; verdict `|p| < 1 ∀p → STABLE`, simple `|p| = 1 → MARGINAL`,
   `|p| > 1` or repeated `|p| = 1 → UNSTABLE`; cross-check by mapping
   the denominator through the inverse bilinear map and running REUSEd
   `routh_of_poly` — disagreement → `INCONSISTENT` (P1 inventory
   pattern). Jury's test is explicitly NOT implemented (one stability
   engine per plane).
7. **FIR**: `y[n] = Σ_{k=0}^{M} b_k·x[n−k]`; linear phase
   `b_k = ±b_{M−k}` ⇒ constant group delay `τ_g = M/2` samples
   (antisymmetric forms documented with their `π/2` offset, never
   silently dropped); always `STABLE` (all-zero, verdict by
   construction + tested).
8. **IIR**: `y[n] = Σ b_k·x[n−k] − Σ_{k≥1} a_k·y[n−k]`; SOS cascade
   of biquads via REUSEd DK + deterministic pairing (conjugates
   together, sorted by radius descending — canonical, unique output);
   cascade ≡ direct by evaluation agreement.
9. **Sampling**: `x[n] = x_c(nT)`; Nyquist verdict (`f_max < fs/2 →
   CLEAN`, `= → MARGINAL` (node-only), `> → ALIASED`); alias map
   `f_a = |f − round(f/fs)·fs|` (exact integer/rational arithmetic);
   ideal reconstruction `x_r(t) = Σ x[n]·sinc((t−nT)/T)` with the
   node-exactness identity `x_r(nT) = x[n]` (finite, exact) and a
   truncated-lobe midpoint check with documented tail bound.
10. **Digital margins** (unit circle, NEW thin solver): gain crossover
    `|L(e^{jθ})| = 1`, phase crossover `∠L = −180°`, same bisection
    contract as P1 (`≤ 1e-12` relative in `θ`, brackets reported,
    absent → `UNSUPPORTED`); `GM`, `PM`, delay in samples and seconds
    (`τ_dm[s] = τ_dm[samples]·T`). Warping note: digital margins are
    NOT bilinear images of analog margins (tested as inequality on a
    fixture — anti-confusion property).

## Equations

Pipeline:
`waveform/sequence-spec → x[n] → DFT/H(z) → stability/margins → filter/sampling verdict → report`.

- DFT/IDFT, twiddle `W_N^{kn} = cos(2πkn/N) − j·sin(2πkn/N)`.
- Parseval: `Σ|x[n]|² = (1/N)·Σ|X[k]|²`.
- Circular convolution: `DFT{(x⊗h)[n]} = X[k]·H[k]`,
  `(x⊗h)[n] = Σ_{m=0}^{N−1} x[m]·h[(n−m) mod N]`.
- Shift: `x[n−m] ↔ W_N^{km}·X[k]`; modulation:
  `W_N^{−ℓn}·x[n] ↔ X[(k−ℓ) mod N]`.
- Real symmetry: `x[n] ∈ ℝ ⇒ X[N−k] = conj(X[k])`.
- Bins: `f_k = k·fs/N`, Nyquist bin `k = N/2` (N even).
- Bilinear: `s = (2/T)(z−1)/(z+1)`, `z = ((2/T)+s)/((2/T)−s)`;
  prewarp `Ω_0 = (2/T)·tan(ω_d·T/2)`.
- LHP↔disc: `Re(s) < 0 ⟺ |z| < 1` (tested both directions on fixtures).
- Group delay: `τ_g(θ) = −d∠H(e^{jθ})/dθ` (samples; central
  differences of the analytic phase for the test oracle, bisection-free).
- Closed loop: `T(z) = C(z)P(z)/(1+C(z)P(z))`,
  `S + T ≡ 1` in `z`.

## Invariants

KCL/KVL/Tellegen on underlying solves (inherited); `S+T ≡ 1` in `z`;
IDFT(DFT(x)) ≡ x (round-trip); Parseval energy identity; real-input
conjugate symmetry; pole-count conservation through REUSEd DK
(`N_roots = N_degree`); Routh↔DK agreement after bilinear mapping;
bilinear forth/back round-trip; LHP↔disc correspondence; TF↔ZPK↔SS
equivalences inherited untouched from P1; Nyquist node-exactness of
reconstruction; insertion-order invariance of sequences; immutability;
content addressing; no wall-clock/UUID in digests.

## Dimensional Analysis

| Entrada | Operación | Resultante | Esperada |
|:---|:---|:---|:---|
| `x_c(t)` (V), `T` (s) | `x[n]=x_c(nT)` | V @ index | V ✓ |
| `T` (s) | `1/T` | Hz | fs ✓ |
| `k`, `N`, `fs` | `k·fs/N` | Hz | bin freq ✓ |
| `f` (Hz), `fs` | `/fs` | dimensionless | ν ✓ |
| `θ` (rad label) | `e^{jθ}` | dimensionless | z ✓ |
| `H₁,H₂` (V/V) | cascade `·` | V/V | V/V ✓ |
| `b_k,a_k` | difference eq. | `[u]/[u]` | `[u]/[u]` ✓ |
| `PM` (rad), `θ_gc` | unit-circle bisect | samples | τ_dm ✓ |
| `τ` (samples), `T` (s) | `·T` | s | delay ✓ |
| `t` (s), `T` | `/T` | dimensionless | node index ✓ |
| dB/rad/deg | display | dimensionless label | ✓ (precedent) |

`T ≤ 0`, `fs ≤ 0`, mismatched endpoint units in a loop → `INVALID`.
`Quantity` at every boundary.

## Numerical Precision

- `Decimal` working precision **50** (P1 precedent); `DecimalComplex`
  spectra; `Fraction` for exact side rails (Routh — inherited; bilinear
  coefficient audit; rank tests — inherited).
- `float` **forbidden** in the new core (no heredity claim needed: no
  wrapped float kernel is used — twiddles come from certified
  `decimal_cos/sin`, `1/N` is exact Decimal division).
- Constants via certified `decimal_pi/sqrt` etc.; twiddle arguments
  reduced by the certified range reduction inside trig (no second
  reducer).
- Overflow/underflow/NaN/Inf: non-finite ingress → `INVALID`;
  `H(z_0)` at a pole / `z_0 = 0` degenerate → `SINGULAR`; FFT length
  violations → `INVALID` (never silent Bluestein, never truncation).
- Cancellation: inherited P1 GCD/`ρ_cancel` discipline applies to the
  REUSEd rational algebra in `w`; no new radius is introduced.

## Error Analysis

- `E_a = |x − x_ref|`; `E_r = |x−x_ref|/max(|x_ref|, ε)`,
  `ε = 1e-30` (inherited pole/residual scale).
- Tolerances: DFT definition exact (no tol); twiddle gate `|W| = 1`
  within `1e-48` (justified: single trig rounding at prec 50);
  FFT-vs-DFT agreement `≤ 1e-40·(1+‖x‖∞)` (justified: identical flop
  multiset, different association — ~10 orders above accumulated
  prec-50 rounding at `MAX_FFT_N`); Parseval `rel ≤ 1e-40`
  (justified: sum-of-squares rounding at max N plus two roundings per
  product); IDFT round-trip `≤ 1e-40·(1+‖x‖∞)`; bilinear round-trip
  `≤ 1e-40` (algebraically exact, Decimal rounding only); SOS-vs-direct
  evaluation `≤ 1e-40·(1+‖H‖)`; crossover bisection width `≤ 1e-12`
  relative in `θ` (P1 precedent, 12 certified digits); reconstruction
  midpoint `≤ 1e-6` (truncation-dominated, tail-derived — the only
  truncation tolerance, bounded); Routh/rank/GCD/alias/Nyquist exact
  (no tol).
- No invented tolerances: every number derives from precision 50, P1
  precedent, flop-count rounding, or truncation tails.

## Stability

- Spectral leakage in fixtures: coherent-sampling rule for tests
  (integer cycles per window) — leakage is physics, never a test
  failure mode; non-coherent inputs are characterised, not asserted on.
- Twiddle precision at large N: per-factor unit-magnitude gate +
  FFT/DFT agreement (P2-002/P2-003).
- Bilinear warping mistaken for margin error: prewarp identity tested
  (P2-016) + digital≠analog-margins inequality fixture.
- IIR direct-form sensitivity: SOS cascade is the specified evaluation
  path above order 8 (documented, tested both paths agree).
- Poles on/near the unit circle: exact verdict ladder
  (simple-on → MARGINAL, repeated-on or outside → UNSTABLE) + Routh
  cross-check; disagreement → `INCONSISTENT`.
- Extreme `fs`/`T` (1e-30/1e30 scales): exact rational paths unaffected;
  trig arguments reduce honestly; non-finite → `INVALID`.
- Division by zero (`A(w) = 0`, `1+L = 0`, `N = 0` in IDFT,
  `T = 0` in `fs`): `SINGULAR`/`INVALID` per case, never silent.
- For each: detection → status → behaviour → guarantee (tables in the
  implementation prompt, contracts fixed here).

## Convergence

P2 contains **no iterative solver**: DFT/IDFT/FFT are closed-form finite
sums; twiddles closed-form; bilinear/SOS/Routh/GCD exact algebra. The
single refinement loop is the unit-circle margin bisection —
linear-convergent by construction on bracketed monotone segments with
bracket fallback (`UNSUPPORTED`), same contract as P1 margins. All P1
DK-backed paths (SOS pairing, pole inventory) inherit the P1 DK
contract verbatim (stop/budget/stagnation/backward gate); no second
convergence theory is claimed. Documented as **guaranteed finite
termination** (sums/recursions) except the inherited observed-convergence
DK reuse and the linear bisection — distinguished explicitly.

## Determinism

Same inputs + config + version = same result: insertion-ordered
sequences, bit-reversal FFT (no RNG anywhere in P2), required seeds only
inside reused F8-M paths (none planned in native P2), no clock/uuid/
locale/parallelism in digests, canonical JSON (`str()` Decimals per F8-N
D-R1, `normalize()` forbidden), `sha256(tag‖0x00‖canonical)`.

## Reproducibility

Inputs (sequences / circuit+recipe / P1 prototype + `fs` / Z-N-style
table entries), config (tolerances §Error Analysis + P2 constants),
engine versions, canonical serialization + digest. No hidden environment
dependence.

## Serialization

Schema `f8p2-dsp/1`: sequence/spectrum/H(z)/filter/margin/sampling
documents; deterministic, closed, size-guarded (`≤ 64 MiB` inherited
bound), digest-recomputed, tamper-evident; replay states
`EQUIVALENT/RESULT_DIFFERS/VERSION_MISMATCH/SCHEMA_MISMATCH/
INVALID_SERIALIZATION` (F8-N/F8-O vocabulary + tested aliases
`VALID`/`RESULT_DIFFERENT`); no pickle/eval/dynamic imports/class-name
reconstruction. Digest helpers REUSEd from
`metrology.o5_traceability` (no second hash construction).

## Security

New code: 0 `eval/exec/compile(builtin)/__import__/getattr/setattr/open/
subprocess/pickle/marshal/importlib/socket/urllib/numpy/scipy/math`
(`re.compile` distinguished from builtin `compile()` in review/tests);
frozen-dataclass discipline per F8-O (validation-only `__post_init__`);
equation/sequence input only through validated constructors; hostile
tests (non-power-of-2 FFT, `T ≤ 0`, over-budget N/order, NaN/Inf ingress,
tampered docs, invalid seeds — seeds only where F8-M is reused).

## Architecture

```text
domain
  ↓
engineering
  ↓
dsp/                    NEW (F8-P2, discrete-time layer)
  ├─ sequences.py       uniform x[n] + sampling model I/O validation
  ├─ dft.py             DFT/IDFT direct + radix-2 FFT/IFFT + theorems
  ├─ ztrans.py          unilateral Z, pairs, ROC, rational H(z) in w
  ├─ filters.py         FIR/IIR, bilinear design, SOS, stability verdicts
  ├─ margins_d.py       unit-circle GM/PM/Tdm (thin bisection solver)
  ├─ sampling.py        Nyquist verdict, alias map, reconstruction
  └─ report.py          f8p2-dsp/1 docs + digests + replay/compare
  ↓ (depends downward only)
certified: control.poly/tf/stability (Horner, TF, Routh, DK, statuses),
           math.*, units, metrology.o5 (digest helpers only)
```

`control/` never imports `dsp/` (acyclicity tested, N-110 style);
`dsp/` never imports `lab/` (N-110), `simulation.py`, UI/application/
infrastructure, or I/O/network. Import DAG as above; verified by AST
test in implementation (mirror of P-034/P-035 plus the
`control↛dsp` / `dsp↛lab` edge tests).

## API Contract

- `Sequence(x, T, unit)` — pre: finite Decimals/`DecimalComplex`,
  `N ≥ 1`, `T > 0` finite; post: frozen uniform sequence; errors
  `INVALID`; complexity O(1) construction, O(n) copy.
- `dft(x)/idft(X)` — exact sums; post: `DecimalComplex` tuple length N;
  O(n²). `fft(x)/ifft(X)` — pre: `N = 2^m`, `N ≤ MAX_FFT_N`; post:
  agreement with `dft` per §Error Analysis; O(n log n).
- `dtft_at(x, theta)` — direct sum at arbitrary digital frequency
  (analysis/reference path); O(n) per point.
- `z_pair(name, params)` — closed-form pairs (δ/step/geometric/ramp);
  post: `(num_w, den_w, roc_R)` with exterior ROC; O(1).
- `TransferFunctionZ(num, den)` — ascending in `w = z^-1`, normalised
  once to descending P1 polynomials; pre: finite, `den ≠ 0`,
  `len(num) ≤ len(den)`; post: frozen causal-proper H(z); O(n) eval.
- `evaluate(h, z)` — Horner at `w = 1/z`; `SINGULAR` at poles/`z = 0`
  degenerate.
- `bilinear_design(proto: TransferFunctionTF, fs, prewarp=None)` —
  pre: P1-proper proto, `fs > 0`; post: `TransferFunctionZ` + warp
  record; O(n²). `bilinear_back(h, T)` — exact inverse.
- `iir_stability(h)` — DK poles + `|·|` ladder + inverse-bilinear
  Routh cross-check; post: `STABLE/MARGINAL/UNSTABLE` + agreement flag;
  `INCONSISTENT` on disagreement.
- `sos_decompose(h)` — REUSEd DK + canonical pairing; post: biquad
  cascade evaluating per §Error Analysis; O(n²·DK-iters inherited).
- `fir_group_delay(b)` / `linear_phase_report(b)` — exact symmetry
  check + `τ_g = M/2`.
- `sample_signal(x_c_recipe, T, N)` — ideal uniform model; post:
  `Sequence`; O(n).
- `nyquist_verdict(f_max, fs)` — `CLEAN/MARGINAL/ALIASED`;
  `alias_of(f, fs)` — exact map; `reconstruct(seq, t)` — sinc sum with
  lobe budget + tail record.
- `digital_margins(loop, T)` — post: `(GM, θ_pc, PM, θ_gc, τ_dm)` +
  brackets; `UNSUPPORTED` when crossovers absent.
- `to_document/from_document/replay/compare` — schema `f8p2-dsp/1`.
All deterministic; no floats, paths, sockets, callbacks.

## Error Model

`COMPLETED | COMPLETED_WITH_FAILURES | INVALID | UNSUPPORTED |
SINGULAR | DIVERGED | MAX_ITERATIONS | NUMERIC_ERROR | INCONSISTENT |
SOLVER_FAILURE` (REUSEd `ControlStatus` vocabulary) (+ serialization
`SCHEMA/VERSION_MISMATCH`). `DIVERGED/MAX_ITERATIONS` are
inherited-only (P1-DK-backed paths); native P2 math uses
`INVALID/UNSUPPORTED/SINGULAR/NUMERIC_ERROR/INCONSISTENT`.
Engine statuses pass through verbatim. Missing crossovers →
`UNSUPPORTED` (explicit), never `GM = ∞` silently.

## Resource Limits

| Limit | Value | Justification |
|:---|:---|:---|
| `MAX_FFT_N` | 4096 (2^12) | FFT prec-50 butterfly cost; 4096·12 ≈ 50k butterflies stay minutes-scale |
| `MAX_DIRECT_DFT_N` | 512 | O(n²) exact sums; 512² = 262k mults stay seconds-scale |
| `MAX_SEQUENCE_N` | 65536 | storage/serde bound (O(n) digests), not a compute licence |
| `MAX_Z_ORDER` | 64 | Routh O(n³) exact Fraction ops stay small; no DK in the verdict loop |
| `MAX_SOS_SECTIONS` | 32 | pairs with `MAX_Z_ORDER`; canonical pairing linearithmic |
| `MAX_BISECT_ITER` | 200 | inherits P1 margin contract |
| `MAX_SERIALIZED` | 64 MiB | inherits F8-N (DoS guard) |
| `MAX_TIME_POINTS` (recon.) | 10001 | inherits P1 response bound |

Budgets are rejections, never truncations.

## Complexity

DFT O(n²) time, O(n) memory; FFT O(n log n) time, O(n) memory;
twiddle O(1) each; bilinear O(n²); Routh O(n³) exact ops;
SOS O(n²·inherited-DK); sampling/alias/reconstruct O(n·l lobes);
margins O(log(1/tol)) direct evaluations per crossover; digests O(doc).
Bottleneck: FFT at N = 4096/prec 50 (bounded, recorded not asserted).

## Validation Matrix

Types: UNIT, ANALYTICAL, NUMERICAL, PROPERTY, BOUNDARY, ERROR, SECURITY,
DETERMINISM, SERIALIZATION, REGRESSION, PERFORMANCE. References:
ANALYTICAL > INDEPENDENT HIGH-PRECISION > PROPERTY > REGRESSION.

| ID | Objetivo | Entrada | Esperado / referencia / tolerancia |
|:---|:---|:---|:---|
| P2-001 | DFT N=4 exacta | `[1,0,0,0]`, `[1,1,1,1]`, `[1,−1,1,−1]` | `[1,1,1,1]`, `[4,0,0,0]`, `[0,0,4,0]` a mano ANALÍTICA |
| P2-002 | Twiddle unitario | `W_N^{kn}`, N=8..4096 | `|W| = 1` dentro `1e-48` |
| P2-003 | FFT = DFT | N=64 ruido-like determ. | acuerdo `≤ 1e-40·(1+‖x‖)` |
| P2-004 | IDFT round-trip | N=4/64 | `≤ 1e-40·(1+‖x‖)` PROPIEDAD |
| P2-005 | Parseval | N=64 | energía `rel ≤ 1e-40` PROPIEDAD |
| P2-006 | Convolución circular | pares N=16 | `DFT(x⊗h) = X·H` PROPIEDAD |
| P2-007 | Desplazamiento | N=16, m=5 | fase `W^{km}` exacta PROPIEDAD |
| P2-008 | Simetría real | entrada real N=32 | `X[N−k] = conj(X[k])` PROPIEDAD |
| P2-009 | Zero-padding | N=16→64 | interpola la misma DTFT (suma directa) |
| P2-010 | Bins + Nyquist | fs=8, N=8 | `f_k = k`, bin Nyquist k=4 |
| P2-011 | Pares Z | δ/u/a^n/rampa | formas cerradas + ROC ANALÍTICA |
| P2-012 | ROC exterior | dos racionales | exterior registrado, unicidad causal |
| P2-013 | H(z) vs suma | FIR geométrica | Horner = suma directa |
| P2-014 | `S+T≡1` en z | cualquier `L(z)` | identidad exacta PROPIEDAD |
| P2-015 | Bilineal preserva | prototipo estable P1 | digital STABLE + Routh acuerdo |
| P2-016 | Prewarp | corte protegido | identidad `tan` `< 1e-12` |
| P2-017 | Bilineal round-trip | orden 4 | `< 1e-40` PROPIEDAD |
| P2-018 | Fase lineal FIR | sim/antisim M=7 | `τ_g = 3.5` + linealidad |
| P2-019 | IIR estable/inest/marg | polos 0.5/1.5/e^{jθ} | veredicto + acuerdo Routh |
| P2-020 | SOS = directa | orden 8 | evaluación `< 1e-40·(1+‖H‖)` |
| P2-021 | GM/PM digital | lazo con cruces | bisección propia `< 1e-9`; sin cruce → UNSUPPORTED |
| P2-022 | Nyquist | f≶fs/2 | CLEAN/MARGINAL/ALIASED exactos |
| P2-023 | Alias cerrado | fs=8, f=5 | `f_a = 3` exacto ANALÍTICA |
| P2-024 | Reconstrucción | seno bandlimitado | nodos exactos; medio `< 1e-6` con cola |
| P2-025 | Batería límites | N=0/T≤0/órdenes/N>topes | INVALID/SINGULAR deterministas |
| P2-026 | Triple run + orden | cualquiera | 1 digest DETERMINISM |
| P2-027 | Serialización/replay | docs | round-trip, tamper, mismatch |
| P2-028 | Hostil | NaN/Inf/tamper/no-pot2 | fallo tipado explícito |
| P2-029 | AST/seguridad | `dsp/` | 0 banned, `re.compile`≠`compile()` |
| P2-030 | No-duplicación | grep | sin 2.º poli/raíz/estab/MC/units/serde |
| P2-031 | Bench | N=64/1024/4096, orden 64 | tiempos registrados |
| P2-032… | Regresión F7-B7,H…P1 | suites | verdes (ver estrategia) |

Count derives from coverage (≥32 + regressions); implementation extends
only with justification.

## Regression Strategy

Implementation runs: F7-B7 → F8-H → F8-I → F8-J → F8-K → F8-L → F8-M →
F8-N → F8-O → F8-P1 (51) → new `tests/test_f8p2_dsp.py` (P2-001…) →
`test_architecture.py` → global `pytest -q` (0 failed, 0 unjustified
skips). `mna/ac/lab/gum/metrology/control/circuit/units/equations`
byte-unchanged (P2 only adds `dsp/` + tests).

## Risks

| Riesgo | Prob. | Impacto | Detección | Mitigación |
|:---|:---:|:---:|:---|:---|
| Leakage leído como fallo | M | B | P2-001/008 (coherentes) | regla de muestreo coherente; no-coherente se caracteriza |
| Warping confundido con error de margen | M | M | P2-016 + desigualdad | prewarp documentado; digital≠analógico testeado |
| Precisión twiddle en N grande | B | M | P2-002/003 | gate por factor + acuerdo FFT/DFT |
| Float accidental | B | A | P2-028 AST | 0-float en núcleo; trig certificado |
| Duplicar motores P1 | B | A | P2-029 + DAG | allowlist; `simulation.py` prohibido |
| Scope creep (cuantización/multirate) | M | M | batería P2-025 | no-alcance explícito + rutas UNSUPPORTED |
| Coste N=4096 (prec 50) | B | B | P2-031 | `MAX_FFT_N=4096`, rechazo explícito |
| Alias en fixtures de validación | B | M | P2-022/023 | solo señales analíticas bandlimitadas |
| Determinismo bit-reversal | B | M | P2-026 | triple-run + invariancia de orden |
| Regresión H→P1 | B | A | suites + `pytest -q` | solo añade paquete |

## Open Questions

Ninguna bloqueante. Decisiones cerradas en este diseño: (Q1) Z
unilateral-causal (bilateral OUT — unicidad vía ROC exterior); (Q2)
estabilidad por bilineal+Routh REUSEd (Jury no implementado — un
criterio por plano); (Q3) N no-potencia-de-2 por DFT-directa ≤512
(Bluestein OUT — honestidad sobre magia); (Q4) arista `dsp→control`
permitida aguas-abajo (acíclica, testeada estilo N-110; `control↛dsp`,
`dsp↛lab`); (Q5) cuantización/wordlength OUT (sin modelo certificado —
física no fingida).

## Deviations

Ninguna respecto al repositorio (fase greenfield sobre motores
certificados). Respecto al mandato: el alias de vocabulario de replay se
hereda de F8-N/F8-O (`EQUIVALENT/…` + `VALID`/`RESULT_DIFFERENT`);
causalidad `len(num_w) ≤ len(den_w)` es `INVALID` (no “avance soportado”);
la única tolerancia de truncamiento sancionada es la de reconstrucción
(`≤ 1e-6` con cola documentada).

## Final Verdict

Las diez preguntas del mandato quedan respondidas: (1) ecuaciones en
§Mathematical Specification/§Equations; (2) unidades en §Dimensional
Analysis; (3) invariantes en §Invariants; (4) errores en §Error Analysis;
(5) referencias en §Validation Matrix (ANALYTICAL-first); (6) fallos en
§Error Model; (7) determinismo en §Determinism; (8) reutilización en
§Repository Evidence/§Existing Infrastructure/§Architecture; (9) límites
en §Resource Limits; (10) test por garantía en §Validation Matrix.
Alcance literal del roadmap (`:209`, “FFT/DFT, transformada Z, FIR/IIR,
muestreo, aliasing”, deps F8-P1), matemática cerrada, arquitectura
cerrada, sin preguntas críticas abiertas.

F8-P2 DESIGN READY
