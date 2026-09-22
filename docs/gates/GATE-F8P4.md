# F8-P4 Certification Gate

## §1 Estado

- Repository `Damaga2005/AcademicCore`, branch `main`.
- Design baseline `b5e3fc6` (`docs(engineering): design gate F8-P4
  digital communications`, verdict `F8-P4 DESIGN READY`), itself built
  on `cea608f` (`feat(engineering): certify F8-P3 RF and transmission
  lines`).
- Preconditions verified at implementation start: `HEAD = b5e3fc6`,
  `origin/main = cea608f`, branch `main`, working tree clean, no foreign
  changes (no `reset`/`clean`/`restore`/`rebase`/`merge`/force-push used
  at any point). `HEAD != origin/main` is expected: the design gate is
  deliberately local until this certification push.

## §2 Baseline

- `git status --short` → empty; `git branch --show-current` → `main`;
  `git rev-parse HEAD` → `b5e3fc6...`; `git rev-parse origin/main` →
  `cea608f...`; log head `b5e3fc6` (P4 design gate), `cea608f` (P3),
  `978667e` (P3 design gate).

## §3 Alcance

Digital communications per roadmap `:211` (deps F8-P2, F8-P3): bits/
symbols/alphabets (MSB-first), deterministic Gray constellations
(BPSK/QPSK/M-PSK/M-QAM-square/ASK/OOK, unit average energy), coherent
FSK tone sets (`df*Ts = 1/2`), baseband complex model + documentary
passband mapping, pulse shaping (rectangular/sinc/RC/RRC with closed
singular limits), AWGN (`CN(0,N0)`, `N0/2` per branch) + static
impairments (gain/phase/frequency-offset/timing, analytic, no tracking),
coherent detection (threshold/correlator/matched/ML; MAP only with
declared priors; non-coherent energy LIMITED to OOK/FSK), metrics
(SNR/EbN0/EsN0, EXACT vs APPROXIMATION labelled BER/SER), Shannon
capacity, seeded SHA256-counter simulation, `f8p4-comms/1`
serialization + replay. Out of scope kept out: channel coding of any
kind, sync loops, OFDM, MIMO, equalization, multipath/fading,
link-budget synthesis, antennas/EM, SDR/ADC/quantization/fixed-point,
plots/UI/hardware (all reserved for future phases / F8-P5, gate §9).

## §4 Implementation

| File | LOC | Role |
|:---|---:|:---|
| `comms/__init__.py` | 245 | Public surface (`ENGINE_VERSION = "f8p4-comms/1"`) |
| `comms/bits.py` | 167 | Bit/symbol/alphabet, MSB-first map/unmap/pad, `Rb = k*Rs` (Hz Quantity) |
| `comms/constellation.py` | 243 | Frozen Gray constellations, unit-energy normalisation, dmin |
| `comms/modulation.py` | 297 | Mod/demod rules, coherent FSK scheme, sps hold, documentary passband |
| `comms/pulse.py` | 195 | Rectangular/sinc/RC/RRC, L'Hopital singular branches |
| `comms/channel.py` | 166 | AWGN add, PSD separation, static impairment transforms |
| `comms/detection.py` | 189 | Threshold/correlator/matched/ML/MAP-declared/energy-LIMITED |
| `comms/metrics.py` | 305 | Q/erfc (Taylor + Laplace CF, Decimal-80), BER/SER, Shannon |
| `comms/simulation.py` | 177 | SHA256-counter streams, Box-Muller, seeded BPSK MC |
| `comms/report.py` | 174 | `f8p4-comms/1` docs + digests (REUSEd) + replay/compare |
| `tests/test_f8p4_comms.py` | 593 | 40 tests, P4-001…P4-040 |
| `tests/test_architecture.py` | +70 | `test_comms_layer_direction` (extends, never weakens) |

Total new production code: 2158 LOC across 10 modules. No new error
module (REUSEd `ControlStatus`/`ControlError` from `control.errors`).
No new digest/canonical-JSON engine (REUSEd `metrology.o5_traceability`
verbatim). No new trig/log/sqrt/complex/Sequence/sampling engine
(REUSEd `math.*`, `control.response.decimal_exp`, `dsp.*` vocabularies).

## §5 Mathematical validation

| Área | Resultado P4 | Referencia independiente | Error | Límite | PASS |
|:---|:---|:---|:---|:---|:---|
| BPSK map 0→+1/1→−1 | exact | frozen convention | 0 | exacto | PASS |
| QPSK 4 pts/labels/Gray | exact | frozen map + combinatorics | 0 | exacto | PASS |
| QPSK ≡ 4-QAM | identical sets | construction identity | 0 | exacto | PASS |
| M-PSK phi0 = 0, unit circle | first pt 1+0j | closed form | ≤1e-30 | energy | PASS |
| 16-QAM dmin² = 0.4 | 0.4 | hand (`(2/√10)²`) | ≤1e-40 | ≤1e-40 | PASS |
| Gray exhaustive (14 constellations) | all Gray | adjacency combinatorics | 0 | exacto | PASS |
| BPSK BER @0dB | 0.0786496035… | hand `½erfc(1)` | ≤1e-12 | 1e-12 | PASS |
| BPSK curve −2…10dB | 7 points | stdlib libm `erfc` in-test | ≤1e-12 | 1e-12 | PASS |
| Q/erfc battery (13 pts + mirror/clamp) | agree | libm + identities | ≤1e-12 (≤1e-40 mirror) | 1e-12 | PASS |
| FSK `df*Ts = 1/2` | 0.5 exact | design rule | 0 | exacto | PASS |
| FSK cross integral (fc·Ts integer) | −1.5e-53 | closed-form integral | ≤1e-40 | ≤1e-40 | PASS |
| RC singular (α=0.4, t=1.25Ts) | −0.1414213562… | hand `−√2/10` (D-R1) | ≤1e-40 | ≤1e-40 | PASS |
| RRC singular (α=0.25, t=Ts) | −0.06423715… | float direct limit ±ε | ≤1e-6 | limit | PASS |
| RRC peak t=0 | 1.0683098861… | hand `1+α(4/π−1)` | ≤1e-40 | ≤1e-40 | PASS |
| Nyquist nodes RC/sinc | 0 (≤7.3e-52) | identity `h(nTs)=δ[n]` | ≤1e-40 | exacto | PASS |
| Shannon C/B @0dB | 1 | `log2(2)` | exacto | exacto | PASS |
| Shannon limit Eb/N0 | ln2, −1.59dB | `log10(2)*ln10` + dB | ≤0.01dB | 0.01dB | PASS |
| MC BPSK 4dB/20000/seed7 | 236 err, 0.0118 | analytic 0.0125, 5σ bound | within | 5σ+floor | PASS |
| dB round-trip 10dB | 10 exact | `exp`/`ln10` kernels | ≤1e-40 | ≤1e-40 | PASS |

Every numeric comparison records absolute/relative error where defined,
allowed tolerance and PASS/FAIL in-test; no bare "close enough".

## §6 Numerical validation

- `Decimal`/`DecimalComplex` at 50-digit working precision (REUSEd
  `math.make_context`/`WORKING_PRECISION`) at every boundary; `float`
  0 in `comms/` (AST + substring audit, §10). No ambient
  `decimal.getcontext()` reliance for arithmetic: all hot paths use an
  explicit `Context` (`ctx.add/subtract/multiply/divide/sqrt/plus/minus`);
  bare `+`/`-` survive only where the result is exact (small ints,
  probability mirror differences) or inside tests with 1e-12-class
  comparison headroom — audited, no silent 28-digit truncation of a
  working value.
- `Q/erfc`: erf Maclaurin (|x|≤1) + Laplace `erfcx` continued fraction
  (modified Lentz, Decimal-80) + `x > 40 → 0` documented underflow rule
  (true Q(40) < 1e-350). Worst disagreement vs libm over 13 points:
  9.1e-15 (oracle-limited), bound 1e-12 holds with 3 orders of margin.
- Round-trip tolerances hold `≤1e-40·(1+‖·‖)`-class bounds (P1/P2/P3
  precedent); Nyquist node residuals measured ≤7.3e-52; rotation
  round-trip ≤1e-40; timing-shift-at-0 identity ≤1e-30 (sinc-tail
  honest, lobe-windowed).
- Extreme-scale battery (`N0 ≤ 0`, `M > 256`, `sps ∉ [1,64]`,
  `α ∉ [0,1]`, negative/huge seeds, NaN/Infinity ingress, oversize
  bits/symbols) all resolve to typed `INVALID`/`INCONSISTENT`, never a
  crash or silent number.

## §7 Invariants

All `P4-I001…P4-I018` have real, executed evidence:

| ID | Invariante | Evidencia |
|:---|:---|:---|
| P4-I001/I002 | bit/symbol round-trip | `test_p4001` (+pad `test_p4002`) |
| P4-I003 | constellation normalization | `test_p4004` (mean == 1 ≤1e-40) |
| P4-I004 | symbol energy | `test_p4004`/`test_p4008` |
| P4-I005 | minimum distance | `test_p4005`/`test_p4011` |
| P4-I006 | Gray mapping | `test_p4006` (14 constellations) |
| P4-I007 | mod/demod identity | `test_p4007`/`test_p4009`/`test_p4040` |
| P4-I008 | Eb/Es consistency | `test_p4008`/`test_p4027` |
| P4-I009 | SNR consistency | `test_p4027` (+P2 Nyquist reuse `test_p4013`) |
| P4-I010 | analytical BER | `test_p4023`/`test_p4024` |
| P4-I011 | analytical SER (APPROX) | `test_p4026` (kinds + monotonicity) |
| P4-I012 | Nyquist pulse condition | `test_p4015`/`test_p4016` |
| P4-I013 | matched-filter identity | `test_p4020` (matched/correlator/ML agree) |
| P4-I014 | channel determinism | `test_p4017` (zero-noise identity) |
| P4-I015 | seeded simulation determinism | `test_p4032` (streams + MC re-run) |
| P4-I016 | serialization round-trip | `test_p4033` |
| P4-I017 | replay equivalence | `test_p4034` |
| P4-I018 | digest determinism | `test_p4031` (triple-run, 1 digest) |

## §8 Independent oracles

Hand values (BPSK 0dB, QPSK quadrants, `dmin² = 0.4`, `−√2/10` RC
limit, RRC peak, Shannon 0/1/ln2); closed-form identities
(round-trips, `Es = k·Eb`, Nyquist nodes, matched≡correlator, FSK
orthogonality integral); stdlib libm `erfc` in-test references for the
BER curve and Q battery (C implementation, structurally independent of
the Decimal CF/series code — explicitly allowed, never the sole
reference for identities); REUSEd certified kernels (`decimal_exp`,
trig/log/sqrt, P2 Nyquist/alias) as designated oracles. No two
functions of the new implementation oracle each other (§31 gate).

## §9 Units

Bits/symbols/ids/labels dimensionless exact ints; `Rs/Rb` Hz
(`Quantity`-dimension-checked at the `bit_rate` boundary);
`Ts/T/tau` s; `N0` W/Hz label; `fc/fs/df` Hz; `Γ`-analogues n/a;
`BER/SER/Pe` dimensionless `[0,1]` (out-of-range → INVALID);
`Es/Eb/N0/SNR` linear ratios (dB display labels only, never
`Quantity`); `φ/θ` rad labels via certified `atan2`/polar helpers;
`C` bit/s. `Rs ≤ 0`, `Ts ≤ 0`, `N0 ≤ 0`, `B < 0` → `INVALID`.

## §10 Security

AST audit (`test_p4035_security_ast_grep`) over every `comms/*.py`:
0 banned calls (`eval, exec, open, getattr, setattr, compile,
__import__`), 0 banned top-level imports (`os, sys, subprocess,
socket, urllib, pickle, marshal, importlib, pathlib, sqlite3, math,
numpy, scipy, statistics, cmath, re, ctypes, http, ftplib, random`),
0 float literals, 0 `float(` substrings, 0 `numpy`/`scipy`/`import math`
substrings. Frozen-dataclass discipline; validated constructors only;
`random`/`os.urandom`/`secrets` absent (stream is counter-SHA256).
Hostile battery (`test_p4030`): oversize bits/symbols, `M > 256`,
non-power-of-2 `M`, bad `sps`/`α`/`N0`/seeds, NaN/Infinity ingress,
tampered/unknown-schema/non-JSON documents — all typed rejections.

## §11 Architecture

`comms → {comms.*, dsp (sequences/sampling vocabulary, no import of
live paths in the hot core), control.errors, control.response.
decimal_exp, math.*, units, metrology.o5_traceability (digest helpers),
stdlib decimal/fractions/dataclasses/hashlib/json}` only;
`control↛comms`, `math↛comms`, `dsp↛comms`, `units↛comms`,
`{mna,ac,lab}↛comms`, `comms↛{rf,lab,simulation,mna,ac,app,UI/FS/
network}` — enforced by new `test_comms_layer_direction` (AST, N-110/
dsp/rf-test style) plus in-suite `test_p4037_layer_direction`. In
particular `comms↛rf` holds: zero functional RF imports (gate §6/§39).
DAG acyclic; no second Sequence/FFT/DFT/sampling/filter/digest/
canonicalizer/serializer/replay/errors/units engine
(`test_p4036_no_second_engine` marker grep + REUSE imports).

## §12 Determinism

Triple-run on a 16-QAM modem document (symbols + BER + coordinates)
produces byte-identical serialization and identical digest
(`test_p4031`); seeded streams bit-identical across runs and
window-decomposable (`test_p4032`); MC report re-runs equal
(`SimReport` equality). No RNG/clock/UUID/dict-order/locale dependence
anywhere in `comms/` (AST-confirmed: no `random`/`time`/`uuid`).

## §13 Serialization

`f8p4-comms/1`: closed schema, deterministic canonical dumps (REUSEd
`canonical_json`/`chain_digest`, `≤64 MiB` guard), `Decimal→str()`
(never `normalize()`), `DecimalComplex→{re,im}`, `Fraction→str()`, no
NaN/Infinity/objects/class-names. Hostile battery: tampered digest
(→`INCONSISTENT` on load), unknown field, wrong schema/version,
non-JSON, empty, wrong-type document, oversize (`test_p4030`/
`test_p4033`).

## §14 Replay

`EQUIVALENT`/`RESULT_DIFFERS`/`VERSION_MISMATCH`/`SCHEMA_MISMATCH`/
`INVALID_SERIALIZATION` (+ tested aliases `VALID`/`RESULT_DIFFERENT`,
F8-N/O/P1/P2/P3 precedent) all exercised with real fixtures
(`test_p4033`/`test_p4034`).

## §15 Resource limits

`MAX_BITS/SYMBOLS = 65536` (P2 precedent), `MAX_ORDER_M = 256`,
`MAX_SPS = 64`, `MAX_SAMPLES = 65536`, `MAX_MC_BITS = 1000000`,
`MAX_LOBES = 5000` (P2 precedent), `MAX_SERIALIZED_BYTES = 64 MiB`
(F8-N/P2/P3 guard), FSK `M ≤ 64`, rates/frequencies `> 0` finite.
All enforced with deterministic `INVALID`/`UNSUPPORTED`/`SINGULAR`
(`test_p4038` boundary battery: M = 2/4/256 ok, 512 rejected;
`sps` 1/64 ok, 65 rejected; 65536-bit ok, 65537 rejected;
`MC > 1e6` rejected pre-compute). Budgets are rejections, never
truncations.

## §16 Performance

Recorded (`test_p4038` bench + MC evidence, no wall-clock asserts):
seeded BPSK MC 20000 bits at prec-50 (SHA256 + Box-Muller + decisions)
≈ 8.8 s; 256-QAM 256-symbol ML decision loop recorded in-test;
erfcx Lentz converges in tens of iterations at Decimal-80 (worst-case
oracle disagreement 9.1e-15). Bottleneck: MC gaussian transcendental
evaluations (bounded by `MAX_MC_BITS`, recorded not asserted). No
benchmark exceeded any certified limit; no new limit was introduced
because a benchmark was slow.

## §17 Regression

| Suite | Result |
|:---|:---|
| F8-P4 new (`test_f8p4_comms.py`) | 40 passed |
| `test_architecture.py` (11 existing + 1 new) | 12 passed |
| F7-B7 (`test_f7b7_gum.py`) | passed |
| F8-H (`test_f8h_nonlinear_dc.py`) | passed |
| F8-I (`test_f8i_bjt.py`, `test_f8i_nonlinear_bjt.py`) | passed |
| F8-J (`test_f8j_small_signal_ac.py`) | passed |
| F8-K (`test_f8k_additional_semiconductors.py`) | passed |
| F8-L (`test_f8l_transient.py`) | passed |
| F8-M (`test_f8m_analysis.py`) | passed |
| F8-N (`test_f8n_lab*.py`, 5 files incl. meta `test_n108`) | passed |
| F8-O (`test_f8o_metrology.py`) | passed |
| F8-P1 (`test_f8p1_control.py`) | passed |
| F8-P2 (`test_f8p2_dsp.py`) | passed |
| F8-P3 (`test_f8p3_rf.py`) | passed |

Explicit regression command (all suites above run in blocks) exits 0;
**no new skip was introduced** by F8-P4. Environment note: the global
`pytest -q` run in this sandbox was interrupted before completion, so
no global tallies are claimed; the pre-existing environment facts from
the F8-P3 gate (missing `bs4`/`PySide6`/`pypdf` optional deps) are
unchanged and untouched by F8-P4 (no new dependency added, no file
outside `comms/`+tests modified except the additive architecture test).

## §18 Limitations

Inherited, unchanged: 50-digit working precision and tolerance
precedents (P1/P2/P3). New and documented: `sinc` truncation is the
only truncation tolerance (lobe budget, P2 precedent); M-PSK/M-QAM/
M-ASK SER are APPROXIMATION by construction (machine-checked
`MetricResult.kind`); non-coherent detection LIMITED to OOK/FSK energy
rules; passband is a documentary single-sample mapping; static channel
impairments have no tracking (inversion identity is analytic, not a
recovery loop); `Q/erfc` underflow to 0 past `x > 40` (true value
< 1e-350); MC at 20000 bits is seconds-scale (≈ 8.8 s).

## §19 Deviations

- **D-R1 (design-gate formula correction, proved before certification)**:
  `GATE-F8P4-DESIGN.md §19` states the RC singular limit as
  `πα/4·sinc(±1/(2α))`; L'Hôpital gives `π/4·sinc(±1/(2α))` (the α
  cancels: `d/du[1−(2αu)²] = −4α` against `d/du[cos(παu)] = −πα·sin`),
  confirmed numerically (`α = 0.4, t = 1.25Ts → −0.1414213562… =
  −√2/10` to ≤1e-40). Implementation carries the proved value with the
  derivation in the docstring; the committed design-gate file is left
  byte-intact. No scope/convention/interface change — a closed-form
  value correction, same class as P3 D-R1.
- **D-R2 (simulation domain separation, no formula change)**: bits and
  noise draw disjoint windows (`[0,N)` vs `[N,…)`) of the gate-§22
  counter stream via a documented `offset` parameter; sharing indices
  correlated bit values with noise magnitudes (halved BER: 121 vs 236
  errors at the certification point). The gate formula
  `u_i = SHA256(seed‖0x00‖i)/2^256` is intact; determinism
  (`same seed → same report`) holds and is tested.
- **Replay vocabulary**: canonical `EQUIVALENT`/`RESULT_DIFFERS`;
  `VALID`/`RESULT_DIFFERENT` tested aliases (F8-N/O/P1/P2/P3 precedent),
  REUSEd verbatim.

## §20 Evidence

`tests/test_f8p4_comms.py`: **40 tests, 40 PASS** (P4-001…P4-040 per
gate matrix, no test removed or weakened). Types covered: UNIT,
ANALYTICAL, NUMERICAL, PROPERTY, BOUNDARY, ERROR, SECURITY,
DETERMINISM, SERIALIZATION, REGRESSION, PERFORMANCE (recorded, no
wall-clock asserts). Certification point pinned: BPSK MC
`4 dB / 20000 bits / seed 7 → 236 errors` (`test_p4039`).

## §21 Verdict

F8-P4 CERTIFIED
