# F8-P5 Design Gate — Síntesis Satcom

Documentation only: no code under `src/` was created or modified, no
tests were written, no engine was altered. The only output of this
phase is this file plus one local commit (no push).

## §1 Baseline

- Repository `Damaga2005/AcademicCore`, branch `main`, baseline **`2b7e017`**
  (`feat(engineering): certify F8-P4 digital communications`),
  `HEAD == origin/main == 2b7e017` (verified at audit time; working tree clean).
- Certified at baseline: F0–F7 (incl. F7-B7 GUM), F8-A … F8-P4
  (gates on disk through `GATE-F8P4.md`; roadmap §6.1 lists F8-P4
  CERTIFICADO and marks **F8-P5 (NEXT)** per §5.1).
- F8-P5 literal definition (roadmap:173 + table:212): `Síntesis Satcom`,
  deps `F8-P1..P4`, scope `Módulo integrador: link budget + modulación +
  ruido + antenas`. The P3 row (:210) defers `antenas, link budget` to
  F8-P5. F16 (:230, `Contenido Aeroespacial/Satélite`, "Mecánica orbital
  básica; última fase, sin prisa") owns orbital dynamics — not P5.
- No-duplication grep (`src/`, case-sensitive): `FSPL|EIRP|link_budget|
  link budget|transponder|slant|272458|c.*299792|BOLTZMANN|380649` →
  zero functional hits. `dBm|dBW|dBi|dBd` → zero hits. `KELVIN|
  TEMPERATURE|kelvin` in engineering → zero hits (no temperature
  dimension exists). `antenna|orbit|GEO|LEO` → only prose (`rf/__init__`
  OUT-declarations, sampler `geometric{a}` recipes). `TODO|FIXME|
  NotImplemented|placeholder` in engineering → only Python-protocol
  returns and unrelated tracks (same verdict as P2/P3/P4 audits).

## §2 Roadmap scope

| Campo | Valor literal (roadmap) |
|:---|:---|
| Nombre exacto | `F8-P5 — Síntesis Satcom` (§5.1:173, tabla:212) |
| Posición | `[11º] (NEXT)` — última fase de la familia F8 antes del cierre |
| Dependencias | `F8-P1..P4` (tabla:212) |
| Objetivo | Módulo integrador: link budget + modulación + ruido + antenas |
| Alcance literal | `link budget`, `modulación`, `ruido`, `antenas` |
| Herencia P3 | `antenas, link budget` diferidos a P5 (:210) |
| Límite F16 | Mecánica orbital básica → F16 (:230), fuera de P5 |
| Siguiente paso | Cierre de F8 → decisiones D1/D2/D3 → F15 |

Si el roadmap calla sobre un área (coding, OFDM, órbitas, rain models,
transponder regenerativo), este gate la clasifica OUT con :212/:230
como evidencia — nunca se rellena por suposición.

## §3 Objectives

Design — not implement — the satcom synthesis integrator: closed-form
link-budget algebra (EIRP → FSPL → received power), ideal-antenna
identities (gain/aperture/efficiency), thermal-noise model (`kTB`,
`G/T`, `C/N0`, `C/N`), the normative bridge `C/N0 → Eb/N0 → P4
BER/SER`, Shannon reuse, link-margin diagnostics, and a closed set of
inverse-synthesis solves (min-Ptx, required-EIRP, max-Rb, required-Eb/N0
bisection over P4 exact curves). Deterministic, Decimal-50, unit-aware,
serializable (`f8p5-satcom/1`), replayable. Precise enough that Prompt 2
implements P5 without inventing mathematical decisions.

## §4 Non-goals

| Item | Class | Reason / home |
|:---|:---:|:---|
| Orbital dynamics, slant-range geometry, GEO/MEO/LEO, look angles | OUT | F16 (:230); P5 takes distance `d` as explicit input |
| Full-wave EM, MoM/FEM/FDTD, radiation patterns | OUT | no roadmap mandate; antennas stay at gain/aperture identities |
| Physical rain/atmospheric/cloud/gas models | OUT | no certified source; explicit loss inputs instead (§8 LIMITED) |
| Fading/multipath statistical channels | OUT | P4 is AWGN-only; no fading engine exists |
| Channel coding / FEC gain | OUT | P4 has no coding; roadmap silent |
| Regenerative transponders, saturation/backoff | OUT | needs demod/remod + nonlinearity; transparent-linear only |
| OFDM/MIMO/SDR/ADC/quantization | OUT | never in P-scope; P4 precedents |
| Availability prediction, rain statistics | OUT | margin is not availability (§17) |
| Plots/GUI/hardware | OUT | presentation layer |
| Generic optimizer | OUT | closed-form + bisection only (§16) |

SUPPORTED/LIMITED/OUT legend: SUPPORTED = full contract below;
LIMITED = explicit-input (accepted, not modeled) or labelled
approximation; OUT = explicit typed rejection, never silent.

## §5 P3 audit

Reusable from `rf/` (verified exports at audit time):

| P3 existing | P5 reuse | Motive |
|:---|:---|:---|
| `margins.mismatch_loss_db(Γ)` | feed mismatch loss | closed form, no re-derivation |
| `margins.return_loss_db/insertion_loss_db` | feed/passive block checks | same |
| `margins.transducer_gain` | reference only (NOT imported as link gain; planes differ — §22 documents the boundary) | avoid plane confusion |
| `margins.vswr` | diagnostic on feed Γ | same vocabulary |
| `lines.LineRLGC/LineZGamma`, `reflection_coefficient` | waveguide/feed segments when modelled as lines | optional leg detail |
| `matching.*` closed forms | feed matching blocks | reuse, never rewrite |
| dB-as-label discipline, peak phasors, Hz/W/Ω/S `Quantity` | reused by value | P5 extends the label family (§20) |
| `smith/sparams/networks` | NOT reused | no two-port cascade inside a budget leg |

No-duplication: P5 creates no second Γ/VSWR/RL/IL/ML engine; where a
feed loss is needed it calls `rf.margins` (`satcom → rf.margins`,
read-only, AST-pinned). `transducer_gain` is deliberately NOT the link
gain: §22 fixes the plane boundary.

## §6 P4 audit

Reusable from `comms/` (verified exports at audit time):

| P4 existing | P5 reuse | Motive |
|:---|:---|:---|
| `metrics.ber_bpsk/ber_qpsk/ber_bfsk/ber_ook` (EXACT) | Eb/N0 → BER bridge | no second Q/BER engine |
| `metrics.ser_*_approx` (APPROXIMATION) | Es/N0 → SER bridge | kind preserved end-to-end |
| `metrics.es_n0_from_eb_n0/eb_n0_from_es_n0` | k-conversions | exact |
| `metrics.to_db10/to_db20/from_db10` | dB bookkeeping kernels | certified log/exp paths |
| `metrics.shannon_capacity/spectral_efficiency` | Rb ≤ C bound | no second Shannon engine |
| `metrics.q_function/decimal_erfc` | required-Eb/N0 bisection target | exact curves only |
| `bits.bit_rate` | Rb = k·Rs | FREQUENCY-dimensioned |
| constellations/modems/simulation/pulse | NOT reused | P5 is budget algebra, not a modem |

Bridge law (§10): `Eb/N0 = C/N0 − 10·log10(Rb)` in dB, proved in
linear first. Scheme tag selects the P4 curve; APPROXIMATION kinds
propagate (never relabelled EXACT).

## §7 Satcom model

One link leg (uplink XOR downlink with identical engine + direction
tag; bent-pipe end-to-end via reciprocal combination, §8):

```text
Tx PA (Ptx) → Tx feed (Ltx) → Tx antenna (Gtx) → free space (FSPL + explicit losses)
→ Rx antenna (Grx) → Rx feed (Lrx) → LNA chain (Te cascade) → Rx output (C/N0, C/N, Eb/N0, margin)
```

- Independent magnitudes (inputs): `Ptx, Gtx, Ltx, f, d, Grx, Lrx,
  Tsys|(stages), B, Rb, scheme, explicit losses (Latm/Lrain/Lpol/Lpoint/
  Lmisc), required Eb/N0`.
- Derived magnitudes: `λ, EIRP, FSPL, Pr, N0, N, G/T, C/N0, C/N, Eb/N0,
  margin, Ae/G/η triple, C Shannon`.
- Physical constraints: every power/gain/loss finite; `f, d, B, Rb > 0`;
  `0 < η ≤ 1`; `T > 0`; probabilities n/a (no BER computed in P5 —
  P4 curves are called, kinds preserved).
- Error states: REUSEd `ControlStatus`
  (`INVALID/UNSUPPORTED/SINGULAR/NUMERIC_ERROR/INCONSISTENT`) — no new
  error module. `0/0`, `log(≤0)`, negative temperatures, empty legs →
  typed states per case, never NaN.

## §8 Link budget

Element classification:

| Elemento | Estado | Dominio / nota |
|:---|:---|:---|
| Tx power Ptx (W, dBW) | SUPPORTED | `> 0` finite |
| Tx gain Gtx (dBi) | SUPPORTED | input or aperture-derived (§9) |
| Tx feed/system losses Ltx (dB) | SUPPORTED | explicit sum, `≥ 0` |
| EIRP (dBW) | SUPPORTED | `EIRP = Ptx·Gtx/Ltx` (§7) |
| FSPL (dB) | SUPPORTED | `(4πd/λ)²`, §6 closed |
| Atmospheric/rain/cloud/gas losses | LIMITED | explicit dB inputs, NOT modeled |
| Polarization mismatch loss | LIMITED | explicit dB input |
| Pointing loss | LIMITED | explicit dB input |
| Rx gain Grx (dBi) | SUPPORTED | input or aperture-derived |
| Rx feed losses Lrx (dB) | SUPPORTED | explicit, `≥ 0` |
| G/T (dB/K) | SUPPORTED | §9/§11 |
| C/N0 (dBHz) | SUPPORTED | §11 |
| C/N (dB) | SUPPORTED | `C/N0 − 10log10(B)` |
| Eb/N0 (dB) | SUPPORTED | `C/N0 − 10log10(Rb)` (§10) |
| Link margin (dB) | SUPPORTED | available − required (§17) |
| Coding/FEC gain | OUT | no P4 coding exists |
| Availability % | OUT | margin ≠ availability |

FSPL closed (no magic constants, no hidden units):

```text
λ = c/f,  c = 299792458 m/s exact (NEW constants module, SI provenance)
FSPL = (4πd/λ)²,  FSPL_dB = 20·log10(4πd/λ)
d > 0 (m), f > 0 (Hz); d = 0 → INVALID (not −∞ dB); non-finite → INVALID.
```

Reference: FSPL(35786 km, 12 GHz) = 205.106 dB (§29).

## §9 Antennas

SUPPORTED identities (ideal aperture, closed form):

```text
Ae = G·λ²/(4π),  G = η·4πA/λ²,  A = πD²/4 (circular, D > 0)
G_input(dBi) XOR G_derived(η, A|D, λ) — never both silently (conflict → INVALID)
0 < η ≤ 1; Ae > 0; G > 0.
EIRP and G/T consume whichever form is declared (provenance recorded).
```

- Gain/beamwidth: `θ_3dB ≈ 70·λ/D` degrees — APPROXIMATION labelled
  (circular aperture, uniform illumination reference; never exact).
- Directivity vs gain: `G = η·Dir`; inputs declare which one they are
  (dBi accepted for both ONLY with an explicit `gain_kind` tag).
- dBd: accepted with FIXED offset `dBi = dBd + 2.15` (documented
  half-wave-dipole reference, not measured).
- Polarization, pointing-error, sidelobe models: OUT (losses are
  LIMITED inputs, §8).
- MoM/FEM/FDTD/patterns: OUT (§4).

## §10 Noise

- Constants: `k = 1.380649e−23 J/K exact` (NEW constants module, SI
  exact — grep-proved absent from repo).
- `N0 = k·T` (W/Hz), `N = k·T·B` (W); `T > 0` K, `B > 0` Hz.
- `Tsys`: SUPPORTED as single-value input; SUPPORTED as Friis cascade
  `Te = T1 + T2/G1 + T3/(G1·G2) + …` over ≤ 8 stages (gains linear
  `> 0`, stage temps `> 0`; reference plane = LNA input, §22).
- `Tant` (sky contribution): LIMITED explicit input (no sky model).
- P4 AWGN is NOT duplicated: P5 computes the LINK's `N0`/`C/N0`; P4's
  `CN(0,N0)` remains the sole sample-level noise model. Boundary:
  P5 delivers `Eb/N0` (dB) + scheme tag; P4 curves deliver BER/SER.

## §11 G/T y C/N0

Reference plane: LNA input (post-Rx-feed, §22).

```text
G/T  = Grx(dBi) − 10·log10(Tsys)            [dB/K]
C/N0 = EIRP(dBW) − L_total(dB) − 10·log10(k) + G/T   [dBHz]
L_total = FSPL + Ltx_misc + Latm + Lrain + Lpol + Lpoint + Lrx + ...
C/N  = C/N0 − 10·log10(B)                   [dB]
```

Dimensional closure: dBW − dB − (dBW/K/Hz) + (dB/K) = dBHz ✓
(`−10log10(k)` carries `+228.599 dB(W/K/Hz)⁻¹`; the label algebra in
§20 makes every step checkable). `k` in dB: `10log10(k) = −228.599`.

## §12 C/N

`C/N = C/N0 − 10·log10(B)` with the SAME `B` that defines the noise
bandwidth (declared once per leg; mismatch of noise-vs-signal
bandwidth → INVALID, never silent). `B > 0` finite.

## §13 Eb/N0

`Eb/N0 = C/N0 − 10·log10(Rb)` (dB), proved in linear:
`(C/N0)/Rb` with `Rb > 0` bit/s (FREQUENCY dimension, P4 `bit_rate`
precedent: bit/s ≡ Hz dimensionally, distinct label). Same-`Rb`
consistency with the modem declaration is checked (P5-I009).

## §14 Modulation integration

Scheme tag ∈ `{bpsk, qpsk, bfsk, ook, mpsk8/16/32/64, mqam16/64/256,
mask}` selects the P4 curve; `k = log2(M)` checked against the
declared `Rb/Rs`. P5 calls P4 BER/SER functions (kinds propagate);
P5 never re-implements `Q()`, constellations, or detectors.
Required-Eb/N0 bisection runs ONLY on EXACT P4 curves
(BPSK/QPSK/BFSK/OOK); APPROXIMATION curves are forward-only
(monotonicity without uniqueness proof → no inversion).

## §15 Shannon

REUSE `comms.metrics.shannon_capacity/spectral_efficiency` (no second
engine). P5 use: `Rb ≤ C` feasibility check + `Rb_max_Shannon = C`
inverse (closed form). Shannon-limit `−1.592 dB` documentary.

## §16 Synthesis/inverse problems

Forward `Ptx → margin` always. Closed inverse set (each with domain,
monotonicity proof, uniqueness):

| Inversión | Forma | Monotonía |
|:---|:---|:---|
| target margin → min Ptx | bisection on strictly increasing `margin(Ptx_dB)` (slope 1 dB/dB) | strict, unique; ≤ 200 iters (P1 precedent), bracket required |
| target Eb/N0 → required EIRP | closed: `EIRP = Eb/N0 + L + k − G/T + 10log10(Rb)` | linear, unique |
| EIRP → max Rb (modem) | closed: `Rb = (C/N0)_lin/(Eb/N0)_req,lin` | unique given req |
| EIRP → max Rb (Shannon) | closed: `Rb = C` | unique given B, SNR |
| target BER → required Eb/N0 | bisection on strictly decreasing EXACT P4 curves only | unique; APPROX excluded |

No generic optimizer (OUT, §4). Infeasible targets → UNSUPPORTED with
reason (e.g. required Ptx beyond `MAX_PTX_W`), never silent clipping.

## §17 Units

- SI via `units.Quantity` where dimensions exist: Hz, W, m, s
  (dBm/dBW INSIDE Quantity? No — dB family stays labels per P3/P4
  precedent; linear W/Hz/m/s travel as Quantity, dB values as tagged
  Decimals).
- NEW (Prompt-2 additive, precedented by F8-D5 ADMITTANCE): `KELVIN`
  dimension + `"K"` unit in `units.py`, additive-only (no other edits;
  pinned by regression). Until then temperatures are Decimal+K-label
  in P5 with the dimension check gated on the extension.
- Rates: bit/s, symbol/s ≡ Hz dimensionally (P4 precedent), distinct
  labels, never bare.
- Constants/assumptions/measurements/derived: `constants` module holds
  `c`, `k` (exact, SI provenance); assumptions travel in the document
  provenance (§23); measurements are inputs with units; derived values
  carry reference-plane tags (§22).

## §18 Numerical strategy

Decimal-50 base; Decimal-80 where P4 kernels already require it
(erfc tails — REUSEd, not re-implemented). New thin math ONLY:
`pow10_ratio` patterns via REUSEd `decimal_exp`/`decimal_log10`
(P4 `from_db10` precedent — actually REUSE `comms.metrics.from_db10`
directly), `20·log10(4πd/λ)` via certified `log10`. No new
transcendental engine. Future core bans: `float/numpy/scipy/math`
(AST+gated, same list as P2/P3/P4 §21/§25/§38).

## §19 Architecture

```text
domain
  ↓
engineering
  ↓
satcom/                     NEW (F8-P5, link-budget integrator)
  ├─ constants.py           c, k (exact, SI provenance)
  ├─ link.py                leg model, EIRP, FSPL, Pr, planes
  ├─ losses.py              explicit loss ledger (LIMITED inputs)
  ├─ antennas.py            G/Ae/η identities, dBi/dBd, beamwidth-APPROX
  ├─ noise.py               kTB, Friis cascade, G/T
  ├─ metrics.py             C/N0, C/N, Eb/N0, margin, dB-label algebra  (name TBD by Prompt 2; must not shadow comms.metrics — e.g. link_metrics.py if the repo layout requires)
  ├─ synthesis.py           forward + closed inverse set
  └─ report.py              f8p5-satcom/1 docs + digests + replay/compare
  ↓ (depends downward only)
certified: rf.margins (read-only margin functions), comms.metrics/bits
           (BER/Shannon/dB/Rb), control.errors, control.response.decimal_exp,
           math.*, units (+KELVIN additive), metrology.o5_traceability (digests)
```

`satcom/` never imports `lab/`, `simulation.py`, `dsp/` (unneeded),
`mna/`, `ac/`, UI/application/infrastructure, I/O/network. Nothing
imports `satcom/` except future tests/app. Module names follow the
prompt skeleton modulo `serialization/replay` folded into `report.py`
(P1–P4 precedent). The `metrics.py` filename collides conceptually
with `comms.metrics` — Prompt 2 resolves by import-alias discipline
or `link_metrics.py`; no second BER/Shannon engine either way.

## §20 DAG

Allowed: `satcom → {rf.margins, comms.metrics, comms.bits,
control.errors, control.response, math.*, units, metrology.o5}`.
Forbidden: `rf → satcom`, `comms → satcom`, `dsp → satcom`,
`control/math/units → satcom` (upward edges), `satcom → {rf∖margins,
comms∖{metrics,bits}, dsp, lab, simulation, mna, ac, UI, FS, network}`.
`rf.margins` and `comms.metrics` are leaf-consumer edges (they import
nothing new). Verified by AST test (P2/P3/P4 precedent).

## §21 Security

Banned in the new core (grep + AST, AST authoritative):
`eval, exec, compile, getattr, setattr, open, subprocess, pickle,
marshal, importlib, socket, urllib, numpy, scipy, math`
(`re.compile` ≠ builtin `compile()`); frozen-dataclass discipline;
validated constructors only; hostile battery (negative/zero `f/d/B/
Rb/Ptx/T`, `η ∉ (0,1]`, mismatched bandwidths, conflicting G input+derived,
dB-label abuse incl. dBi+dBi, NaN/Infinity text, oversize legs, tampered
docs, orbital/rain-model smuggling attempts → typed states).

## §22 Serialization

Schema `f8p5-satcom/1` (closed, versioned): leg/antenna/noise/metric/
synthesis documents; deterministic dumps; `Decimal→str()` (never
`normalize()`, F8-N D-R1); no NaN/Infinity/objects/class names;
`≤ 64 MiB` guard. Envelope mechanics REUSEd (`canonical_json`/
`chain_digest`) — no second hash, no second canonicalizer. Tamper →
INCONSISTENT on load (P2/P3/P4 precedent).

## §23 Replay

Vocabulary REUSEd verbatim: `EQUIVALENT/RESULT_DIFFERS/
VERSION_MISMATCH/SCHEMA_MISMATCH/INVALID_SERIALIZATION` (+ tested
aliases `VALID`/`RESULT_DIFFERENT`). Replay re-evaluates the link
specification under same schema+version and compares digests;
notes/annotations never affect digests. No parallel system.

## §24 Determinism

`same input → same result → same canonical serialization → same
digest`; triple-run mandated (RUN 1/2/3, bytes+digest identical); no
clock/UUID/RNG/dict-order/locale/platform dependence; legs in
insertion order; seeds only inside REUSEd P4-simulation paths (P5
adds no RNG — link math is closed-form + bisection).

## §25 Resource limits

| Límite | Valor | Razón |
|:---|:---|:---|
| legs per document | ≤ 2 (up/down) | domain definition |
| loss entries per leg | ≤ 16 | ledger bound, digest-sized |
| Friis stages | ≤ 8 | linear cost, exact algebra |
| antennas per leg | ≤ 2 (Tx/Rx shared or separate) | domain definition |
| bisection iterations | ≤ 200 | P1 margin precedent |
| `MAX_PTX_W` | 1e6 W (60 dBW) | sanity rejection, documented |
| input magnitudes | Langle: `f,d,B,Rb,Ptx,T ∈ (0, 1e30]` finite | Decimal exact, rejection on violation |
| `MAX_SERIALIZED` | 64 MiB | F8-N/P2/P3/P4 guard |

Budgets are rejections, never truncations.

## §26 Oracles

Hierarchy: (1) closed-form derivation, (2) hand computation (§29
values derived below from the formulas, provenance stated), (3)
closed identities (Friis `Pr = EIRP−L+Gr`, reciprocal
`1/(C/N0)tot = Σ1/(C/N0)i`, `S+T`-analogous dB triangle
`EIRP−L−k+G/T−10logB−10logRb` chain), (4) textbook references cited
(Marra–Sadeh-class Friis/FSPL, Johnson–Nyquist kTB, Shannon),
(5) certified engines as oracles (P3 margins on fixtures, P4 BER/
Shannon, P2-independent — never the future satcom code itself).

## §27 Invariants

| ID | Invariante | Método | Tolerancia | Oracle |
|:---|:---|:---|:---|:---|
| P5-I001 | dimensional closure (dB triangle) | label algebra | exacta | §11 |
| P5-I002 | FSPL identity | `(4πd/λ)²` vs `20log` form | ≤1e-40 | hand §29 |
| P5-I003 | EIRP bookkeeping | linear×dB agreement | ≤1e-40 | hand §29 |
| P5-I004 | received power (Friis round-trip) | forward≡inverse | ≤1e-40 | identidad |
| P5-I005 | kTB | `k·T·B` vs dB form | ≤1e-40 | hand §29 |
| P5-I006 | G/T | definition | ≤1e-40 | hand §29 |
| P5-I007 | C/N0 chain | EIRP−L−k+G/T | ≤1e-40 | hand §29 |
| P5-I008 | C/N bandwidth | `−10logB` | exacta | definición |
| P5-I009 | Eb/N0 rate | `−10logRb` + modem-k check | exacta | P4 bridge |
| P5-I010 | aperture round-trip | G↔Ae both ways | ≤1e-40 | identidad |
| P5-I011 | link margin | avail − req | exacta | definición |
| P5-I012 | Shannon bound | `Rb ≤ C` feasibility | exacta | P4 REUSE |
| P5-I013 | P4 integration (BER kind preserved) | scheme→curve | exacta/APPROX | P4 |
| P5-I014 | inverse uniqueness | monotonicity re-solve | ≤1e-12 (bisection) | prueba |
| P5-I015 | bent-pipe reciprocal | `1/tot = Σ1/i` | ≤1e-40 | identidad |
| P5-I016 | serialization round-trip | doc→text→doc | bytes | digest |
| P5-I017 | replay equivalence | re-ejecución | digest | §23 |
| P5-I018 | digest determinism | triple dump | bytes | §24 |
| P5-I019 | dB-label rejection | incompatible ops | typed | §20-table |
| P5-I020 | DAG/limits | AST + boundary battery | typed | §20/§25 |

## §28 Test plan

P5-001…P5-045 (IDs stable; Prompt 2 extends only with justification):

| ID | Área | Oracle |
|:---|:---|:---|
| P5-001…003 | constants (c, k exactness/provenance), λ = c/f | SI exact digits |
| P5-004…006 | FSPL formula/dB-form/domains (d = 0 → INVALID) | hand 205.106 dB |
| P5-007…009 | EIRP linear/dB, received power Friis | hand 59.0 dBW |
| P5-010…012 | kTB/N0/G/T | hand −143.975/−203.975/16.990 |
| P5-013…015 | C/N0/C/N/Eb/N0 chain | hand 99.483/29.483 |
| P5-016…017 | aperture G↔Ae, η bounds, dBi/dBd | hand 41.355 dBi |
| P5-018 | beamwidth APPROX label | approximation bound |
| P5-019…020 | Friis cascade, Tant-LIMITED | closed form |
| P5-021…023 | P4 bridge (EXACT kinds, APPROX preserved, k-check) | P4 curves |
| P5-024 | Shannon feasibility + max-Rb | P4 REUSE |
| P5-025…027 | margin + inverses (min-Ptx bisection, req-EIRP, max-Rb, BER→Eb/N0) | monotonicity |
| P5-028 | bent-pipe reciprocal | identity |
| P5-029 | transponder-linear block; regenerative → OUT | states |
| P5-030 | LIMITED losses accepted; rain/orbit models → OUT | states |
| P5-031 | dB-label algebra + rejection matrix | typed |
| P5-032 | units (Hz/W/m/K/s, bit/s≡Hz, dB labels) | Quantity/dim |
| P5-033 | hostile battery (magnitudes, NaN, oversize, tamper) | typed |
| P5-034 | determinism triple-run | 1 digest |
| P5-035 | serialization round-trip/tamper/mismatch | 5 states |
| P5-036 | replay equivalence | digest |
| P5-037 | security AST + grep | 0 banned |
| P5-038 | no-duplication AST/grep | no 2nd engines |
| P5-039 | architecture DAG | edge tests |
| P5-040 | resource limits/bench | recorded, no wall asserts |
| P5-041… | regression F7-B7,H…P4 | suites green |

Each test records input/expected/oracle/tolerance/failure-meaning
(P2/P3/P4 precedent; no bare "close enough").

## §29 Reference cases

Provenance: hand-derived from the closed forms (float scratch,
6-digit gate values; Prompt 2 verifies in Decimal-50). Distance
`d = 35786000 m` is a textbook GEO reference input (NOT computed
orbital geometry — §13 OUT).

| Caso | Entrada | Esperado |
|:---|:---|:---|
| λ @12 GHz | `c/f` | 0.0249827 m |
| FSPL | 35786 km, 12 GHz | 205.106 dB |
| EIRP | 100 W, 40 dBi, 1 dB | 59.0 dBW |
| kTB | 290 K, 1 MHz | −143.975 dBW |
| N0 | 290 K | −203.975 dBW/Hz |
| G/T | 40 dBi, 200 K | 16.990 dB/K |
| C/N0 | leg §11 (§29 chain) | 99.483 dBHz |
| Eb/N0 | Rb = 10 Mb/s | 29.483 dB |
| Dish gain | D = 1.2 m, η = 0.6, 12 GHz | 41.355 dBi |
| Shannon limit | — | −1.592 dB |

Chain check: `59.0 − 205.106 + 228.599 + 16.990 = 99.483` ✓;
`99.483 − 70.0 = 29.483` ✓.

## §30 Stability

| Escala | Magnitudes | Riesgo → garantía |
|:---|:---|:---|
| 1e-30 | — | below physical validity → INVALID (no silent subnormal physics) |
| 1e-20…1e-10 | k-scaled powers | Decimal exact, dB ≈ −200…−100, no underflow (Decimal range) |
| 1e-5…1 | small gains/losses | exact ratios, label algebra |
| 1…1e5 | nominal link terms | 50-digit headroom |
| 1e10…1e20 | FSPL linear (~1e20) | exact integer-power scale; dB path primary |
| 1e30 | input-magnitude ceiling | rejection past it |
| dB ±999 | extreme ratios | `log10` kernels certified; overflow → NUMERIC_ERROR, never inf |
| `log(≤0)` | zero/negative ingress | INVALID pre-checks on every log site |
| cancellation | EIRP−L chains | same-scale dB differences exact to 50 digits; linear cross-check invariant |

## §31 Risk matrix

| Riesgo | Prob. | Impacto | Detección | Mitigación | Test |
|:---|:---:|:---:|:---|:---|:---|
| dB/dBi/dBm/dBW/dBd/dB-K confusion | M | A | P5-031 | label algebra + rejection matrix | P5-031 |
| dBm↔dBW offset (±30) | M | A | P5-031 | reference table, tested pins | P5-031 |
| FSPL formula (λ vs f inverted) | B | A | P5-004 | `λ = c/f` + 205.106 pin | P5-004…006 |
| one/two-sided PSD mix | M | A | P5-013 | P4 convention inherited verbatim | P5-013 |
| Tsys plane (pre/post feed) | M | A | P5-010/019 | §22 plane fixed, cascade ref'd | P5-019 |
| bandwidth mismatch (noise vs signal) | M | A | P5-014 | single-B declaration, INVALID | P5-014 |
| Eb/N0 vs Es/N0 swap | M | A | P5-015 | modem-k check P5-I009 | P5-015/021 |
| G/T reference (dB/K label) | B | A | P5-012 | definition + 16.990 pin | P5-012 |
| aperture vs input gain conflict | B | M | P5-016 | XOR gate, INVALID | P5-016/033 |
| η out of (0,1] | B | M | P5-016 | validator | P5-033 |
| antenna temp modeled silently | B | M | P5-019 | LIMITED-input only | P5-019/030 |
| transponder saturation smuggled | B | A | P5-029 | linear-only + OUT states | P5-029 |
| orbit geometry smuggled | B | M | P5-030 | d-input only, F16 owns | P5-030 |
| coding gain smuggled | B | M | P5-030 | OUT states | P5-030 |
| inverse non-uniqueness | B | A | P5-025 | monotonicity proof + bisection | P5-025/027 |
| APPROX relabelled EXACT | B | A | P5-021 | kind propagation test | P5-021 |
| Decimal/global-ctx truncation | B | M | P5-034 | explicit ctx + triple digest | P5-034 |
| duplication (2nd Q/BER/Shannon/log) | B | A | P5-038 | marker-grep + REUSE imports | P5-038 |
| cycle satcom↔rf/comms | B | A | P5-039 | AST edges both directions | P5-039 |
| scope creep (rain/orbit/regen/MIMO) | M | M | P5-030 | OUT battery | P5-030 |
| regresión H→P4 | B | A | suites + pytest | solo añade paquete | P5-041 |

## §32 Open questions

1. ¿P5 necesita `satcom → rf` funcional o basta disciplina por valor? → CLOSED: `satcom → rf.margins` read-only (mismatch/RL/IL), resto por valor; transducer_gain excluido por planos (§5/§20/§22).
2. ¿P5 necesita `satcom → comms`? → CLOSED: sí, `comms.metrics` (BER/SER/Shannon/dB) + `comms.bits` (Rb); resto OUT (§6/§20).
3. ¿De dónde salen `c` y `k`? → CLOSED: NEW `constants.py`, SI exactos, ausencia grep-probada (§1/§19).
4. ¿Dimensión Kelvin? → CLOSED: extensión aditiva KELVIN+K en Prompt 2 (precedente F8-D5), resto del gate usa labels (§17).
5. ¿Modelo de cielo/lluvia? → CLOSED: no hay; pérdidas explícitas LIMITED (§8).
6. ¿Geometría orbital / slant range calculado? → CLOSED: OUT; `d` es input; F16 owns (§13).
7. ¿Transponder regenerativo / saturación? → CLOSED: OUT; transparente-lineal SUPPORTED (§8/§29-test).
8. ¿Uplink+downlink extremo a extremo? → CLOSED: dos legs + combinación recíproca (§8/§16).
9. ¿Coding gain? → CLOSED: OUT (P4 sin coding, roadmap silent) (§16).
10. ¿Inversión con qué unicidad? → CLOSED: tabla §16, bisección solo monótona-acotada.
11. ¿BER→Eb/N0 sobre APPROX? → CLOSED: no; solo curvas EXACT (§14).
12. ¿Margen = disponibilidad? → CLOSED: no; OUT explícito (§17).
13. ¿Beamwidth exacta? → CLOSED: no; APPROXIMATION etiquetada (§9).
14. ¿dBi vs dBd? → CLOSED: offset fijo +2.15 con tag (§9/§20).
15. ¿Segundo Shannon/Q/BER/log? → CLOSED: no; REUSE P4 + kernels (§15/§18).
16. ¿Estructura `metrics.py` vs `comms.metrics`? → CLOSED: alias/disciplina o `link_metrics.py` en Prompt 2 (§19).

## §33 Limitations

P5 is a budget integrator, not a field solver, not an orbit
propagator, not a modem, not a coder: environment losses are inputs
(not physics), antennas are identities (not patterns), noise is
single-value/Friis-cascade (not sky maps), inverses are closed-form +
bounded bisection (not optimization), availability is not predicted,
dB labels are not Quantities, beamwidth is approximate, KELVIN needs
the additive units extension, and every OUT in §4 stays OUT in
Prompt 2 unless the roadmap changes.

## §34 Deviations

Ninguna respecto al repositorio (fase greenfield sobre motores
certificados; convenciones P3/P4 heredadas verbatim por valor o por
import read-only declarado). Respecto al mandato: replay aliases
heredados (`VALID`/`RESULT_DIFFERENT`); `metrics.py` con nota de
colisión nominal (§19); `KELVIN` como extensión aditiva sancionada
(§17); beamwidth-APPROX como única aproximación sancionada además de
las heredadas de P4.

## §35 Final verdict

Las dieciséis preguntas abiertas (§32) quedan cerradas; alcance
literal del roadmap (`:212`, deps `F8-P1..P4`), matemática cerrada
(Friis/FSPL/kTB/G-T/cascade/recíproca/inversas monótonas),
convenciones cerradas (planos, labels dB, PSD P4 verbatim),
integración P3/P4 cerrada (read-only + REUSE, sin duplicación),
arquitectura cerrada, tolerancias justificadas, casos de referencia
derivados.

F8-P5 DESIGN READY
