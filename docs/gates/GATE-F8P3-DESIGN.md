# F8-P3 Design Gate — RF y Líneas de Transmisión

Documentation only: no code under `src/` was created or modified, no
tests were written, no engine was altered. The only output of this
phase is this file plus one local commit (no push).

## §1 Estado

- Repository `Damaga2005/AcademicCore`, branch `main`, baseline **`8ede3ee`**
  (`feat(engineering): certify F8-P2 digital signal processing`),
  `HEAD == origin/main` (verified at audit time; working tree clean).
- Certified at baseline: F0–F7 (incl. F7-B7 GUM), F8-A … F8-P2
  (gates on disk through `GATE-F8P2.md`; roadmap §6.1 lists F8-P2
  CERTIFICADO and marks **F8-P3 (NEXT)** per §5.1).
- F8-P3 literal definition (roadmap:171 + table:210): `RF y Líneas de
  Transmisión`, deps `F8-D1/D2, F8-P2`, scope `Carta de Smith,
  parámetros S, antenas, link budget`. The `antenas, link budget` theme
  is scoped in §4/§30: P3 delivers the conducted/network RF mathematics
  (lines, 2-ports, S, Smith math, matching, RF margins incl. transducer
  gain primitives); radiated antenna models and satcom link-budget
  synthesis belong to F8-P5 (roadmap:212 claims them as integrator).
- No-duplication grep (`src/`, case-insensitive): `smith|s_param|
  sparam|vswr|telegrapher|transmission.?line|stub|reflection coeff|
  return loss|insertion loss|Z0|characteristic|propagat|distributed|
  coax|microstrip` → zero functional hits (`ABCD` hits are the F8-G
  cascade matrix, `gamma` hits are `math.lgamma`/docs, `sens_params`
  is `.print sens`). `TODO|FIXME|NotImplemented|placeholder` in
  engineering → only Python-protocol returns, superseded `models.py`
  ideals, unrelated tracks.

## §2 Objetivo

Design — not implement — a coherent mathematical layer for RF +
transmission lines + two-port networks + S-parameters + impedance
matching + idealized electromagnetic propagation, with physical units,
complex magnitudes, deterministic serialization, traceability and
independent analytic validation. Precise enough that another person can
implement F8-P3 without inventing fundamental mathematical decisions.

## §3 Alcance

F8-P3 is the **conducted/network RF mathematics layer** over the
certified engines. It adds no circuit solver, no Bode engine, no
transient integrator, no sampler, no GUM math, no second polynomial /
root / stability / serialization / digest / replay implementation.

| ID | Capability |
|:---|:---|
| P3.1 | RF primitives: f, T, λ, v, Z, Y, S=P+jQ, RMS/peak phasors (frozen conventions) |
| P3.2 | Transmission-line core: Z0, γ=α+jβ, l, ZL, Zin, Γ, VSWR, RL, attenuation, phase delay |
| P3.3 | Lossless + lossy (RLGC) lines, degenerate limits, open/short/matched loads |
| P3.4 | λ/4, λ/2, impedance transformation, single-stub matching (short/open, series/shunt) |
| P3.5 | Two-port networks Z/Y/ABCD (+T derived view) with certified conversions |
| P3.6 | S-parameters S11/S21/S12/S22 (real + complex reference), RL/IL, reciprocity/symmetry |
| P3.7 | Exact deterministic cascading via S→ABCD→matmul→ABCD→S with validity domains |
| P3.8 | Smith mathematics (no graphics): z↔Γ, y↔Γ, R/X circles as equations, line rotation |
| P3.9 | Closed-form matching: conjugate, quarter-wave, single-stub, single L/C + realizability |
| P3.10 | RF margins: VSWR, RL, IL, mismatch loss, transducer gain, Rollett K/μ stability |

## §4 Out of Scope

| Item | Class | Reason / home |
|:---|:---:|:---|
| Full-wave EM, Maxwell PDE, FEM/FDTD/MoM, 3D geometry | UNSUPPORTED | field solvers, never lumped math |
| Antennas (radiated models), waveguides, microstrip EM, dielectric dispersion | UNSUPPORTED | P5 / future field phase |
| Satcom link-budget synthesis | UNSUPPORTED | F8-P5 integrator (roadmap:212); P3 gives GT/IL/ML primitives |
| Nonlinear RF, harmonic balance, noise, large-signal, RF transistors, mixers, PLL, radar | UNSUPPORTED | no certified nonlinear/noise/RF-device models |
| Microwave network synthesis, double-stub, broadband/multisection matching | UNSUPPORTED | future synthesis phase |
| Graphical Smith chart, RF plots, CAD/PCB | UNSUPPORTED | presentation layer (Smith stays math-only, §16) |
| Hardware | UNSUPPORTED | domain stays hardware-free |
| Bilateral/non-causal constructs smuggled as RF | UNSUPPORTED | causality discipline inherited |

SUPPORTED/LIMITED/UNSUPPORTED legend: SUPPORTED = full contract below;
LIMITED = exact degenerate handling documented per case (e.g. Γ=±1
exact, VSWR infinite reported as UNSUPPORTED-never-Infinity);
UNSUPPORTED = explicit state with reason, never silent.

"RF" inside AcademicCore therefore means: **single-frequency (swept by
callers) complex-linear conducted network theory over Decimals —
telegrapher lines, 2-port matrix representations, power-wave
S-parameters, Smith-plane algebra and closed-form matching** — with P1
precision discipline and P2 serialization discipline.

## §5 Arquitectura

```text
domain
  ↓
engineering
  ↓
rf/                       NEW (F8-P3, conducted RF math layer)
  ├─ primitives.py        f/T/λ/v, Z/Y phasors, S=P+jQ, RMS/peak (frozen)
  ├─ lines.py             RLGC/lossless line, Z0/γ, Zin, Γ, VSWR/RL, delay
  ├─ networks.py          Z/Y/ABCD/T matrices, conversions, cascade
  ├─ sparams.py           S walls (real+complex ref), RL/IL, symmetry checks
  ├─ smith.py             z↔Γ, y↔Γ, circles, line rotation (math only)
  ├─ matching.py          conjugate/λ4/stub/LC closed forms + realizability
  ├─ margins.py           VSWR/RL/IL/ML/GT/K-μ RF margins
  └─ report.py            f8p3-rf/1 docs + digests + replay/compare
  ↓ (depends downward only)
certified: control.errors (statuses), control.response.decimal_exp,
           math.* (trig/log/sqrt/complex), units,
           metrology.o5_traceability (digest helpers only)
```

Module names follow the prompt skeleton modulo `serialization/replay`
folded into `report.py` (P1/P2 precedent: one envelope module).
`rf/` never imports `lab/` (N-110), `simulation.py` (float world),
UI/application/infrastructure, I/O/network. Nothing imports `rf/`
except future P4/P5/tests. DAG verified by AST test (§27).

## §6 Matemática

### Onda

`λ = v/f`, `β = 2π/λ` (β in rad/m label), `γ = α + jβ` with
`α` Np/m label, `β` rad/m label sharing the 1/m dimension (§7).
`v` (phase velocity, m/s) is an explicit line/cable parameter, never
a global constant (no hidden `c`).

### Telegrapher line (lossy, primary model)

Per-unit-length `R, L, G, C` (finite Decimals ≥ 0; ω = 2πf, f > 0):

`Z' = R + jωL`, `Y' = G + jωC` (DecimalComplex, exact arithmetic),
`γ = √(Z'Y')`, `Z0 = √(Z'/Y')` — complex square roots via REUSEd
`DecimalComplex.sqrt` (principal branch, documented). `Z0` is always
DERIVED (never an independent input contradicting RLGC); `Z0 = 0`
(G=∞-like degenerate) and non-finite ingress → INVALID.
Lossless limit `R = G = 0` is exact (no epsilon): `α = 0`,
`Z0 = √(L/C)` real, `β = ω√(LC)`.

Alternative constructor from measured `(Z0, γ, l)` (Z0 complex
allowed, γ recorded): equivalent representation, with a
consistency invariant against the RLGC path on fixtures. Both exact;
neither is "the" model.

### Zin (sin/cos primary form — never tan in the Zin path)

For load model `ZL` (tagged: `impedance(Z)` finite | `open` |
`short` | `matched(Z0ref)` — open/short are KINDS, never huge
numbers) on a line `(Z0, γ, l)`:

`Zin = Z0·(ZL·cosh(γl) + Z0·sinh(γl)) / (Z0·cosh(γl) + ZL·sinh(γl))`

with complex sinh/cosh from thin helpers on certified sin/cos/exp
(§8; REUSE pattern of P2 `_decimal_tan`). At βl = π/2 the lossless
limit resolves exactly through the equivalent sin/cos form
`Zin = Z0·(ZL·cos+jZ0·sin)/(Z0·cos+jZL·sin)` → `Z0²/ZL` (quarter-wave
identity, §17). `l = 0` is valid (`Zin = ZL`, tested). `γ = 0`
exact (`tanh(0) = 0` path, tested). Zero denominators → SINGULAR
(never NaN).

### Reflexión

`Γ = (ZL − Z0)/(ZL + Z0)` (Z0 possibly complex — required by lossy);
inverse `ZL = Z0·(1+Γ)/(1−Γ)`; `Γ = −1` short exact, `Γ = +1` open
exact, `Γ = 0` matched exact. Denominator `ZL + Z0 = 0` (active
anti-matched edge) → SINGULAR, documented.

### VSWR / Return Loss / Insertion Loss / Mismatch

`VSWR = (1+|Γ|)/(1−|Γ|)` for `|Γ| < 1`; `|Γ| = 1` → UNSUPPORTED
("infinite VSWR", never Infinity stored — F8-G precedent);
`|Γ| > 1` (active) → UNSUPPORTED with reason (VSWR undefined for
active loads). `RL = −20·log10(|Γ|)` for `|Γ| > 0` finite (sign
preserved: negative RL = return gain, documented); `|Γ| = 0` →
UNSUPPORTED (infinite RL, never inf stored). `IL = −20·log10(|S21|)`
same domain rule. `ML = −10·log10(1−|Γ|²)` for `|Γ| < 1`
(mismatch loss ≥ 0); `|Γ| ≥ 1` → UNSUPPORTED. Log via certified
`decimal_log10`; dB is a dimensionless display label (§7).

### Potencia (frozen F8-D4 conventions)

Peak phasors, `e^{+jωt}`: `S = ½·V·conj(I)` absorbed-uniform
(`P < 0` delivers); RMS = peak/√2 (magnitude domain only, never
inside D3-style solves); `apparent = |S|`, `pf = P/|S|` (`None` iff
`|S| = 0` exact — F8-D4 rule, no epsilon). Transducer gain for
2-port + source `Zs` + load `ZL` (all in scope):

`GT = |S21|²·(1−|Γs|²)·(1−|ΓL|²) / (|1−Γs·Γin|²·|1−S22·ΓL|²)`

with `Γin` the loaded input reflection (derived, §13). Available
gain / max-stable-gain / unilateral approximations: OUT (future).

## §7 Unidades

| Cantidad | Símbolo | Dimensión | Nota |
|:---|:---|:---|:---|
| Impedancia Z, Z0, ZL, Zin, Zth | Ω | RESISTANCE | `Quantity`, exacta |
| Admitancia Y | S | ADMITTANCE | `Quantity`, exacta |
| Frecuencia f, fs | Hz | FREQUENCY | f > 0 |
| Pulsación ω | rad/s | label sobre 1/s | documentaria |
| Longitud l, λ | m | LENGTH | l ≥ 0 |
| Tiempo t | s | TIME | fronteras |
| Potencia P/Q/S | W | POWER | RMS/peak §6 |
| γ (α Np/m, β rad/m) | 1/m | LENGTH⁻¹ tuple | REUSE Dimension machinery; labels distinguish (dB/rad precedent) |
| Γ, S-params, VSWR | adimensional | DIMENSIONLESS | exact Decimal/Complex |
| RL/IL/ML/GT/K | dB / adim. | labels | nunca `Quantity` dB (units.py precedent) |
| θ eléctrico βl, fase | rad | label | atan2 certificado |

`T ≤ 0`, `f ≤ 0`, `l < 0`, R/L/G/C negativos o no finitos → INVALID.
`Quantity` at every boundary; dB/deg/rad/Np never `parse_unit`
targets (precedent: `MagnitudeResult`, `phase_unit` params).

## §8 Numérica

Precision base **50 digits** (P1/P2 precedent; justified: identical
flop-class complex algebra, shared trig/log/sqrt kernels, tolerance
precedents transfer verbatim). `Decimal`/`DecimalComplex`/`Fraction`/
`RationalComplex` REUSEd; 0 `float`/`numpy`/`scipy`/`math`/`cmath` in
the new core (AST+gated). New thin helpers ONLY where the repo provably
lacks them: complex `tanh/sinh/cosh` on certified sin/cos + REUSEd
`control.response.decimal_exp`, real `tan` on certified sin/cos (P2
`_decimal_tan` pattern), complex `exp(a+jb) = e^a(cos b + j sin b)`
(P2 collocation pattern). No second trig reducer (certified range
reduction inside trig), no second log (`decimal_log10`), no second
complex sqrt (`DecimalComplex.sqrt`).

Tolerances (every one reasoned; §33 hard-stop on invented ones):
exact rational formulas (Γ/Z/VSWR/RL/IL/ABCD/S/T) → exact Decimal, no
tol; round-trips (Γ↔Z, S↔ABCD, Z↔Y, T-chain) `≤ 1e-40·(1+‖·‖)`
(rounding-only, P1/P2 precedent); Smith circle identities `≤ 1e-40`;
line≡2-port equivalence `≤ 1e-40`; matching verification residual
`|Zin−Ztarget|/|Ztarget| ≤ 1e-30` (solve is closed-form; conditioning
note for near-singular targets); cascade reproducibility exact (same
multiplication order); unitary/reciprocity EXACT equality for
reciprocity (`S12 == S21`), `≤ 1e-40` for unitarity (`S†S−I`,
products involved).

## §9 RF Primitives

`frequency(f)` (Hz>0), `period T = 1/f`, `wavelength(λ, v)`,
`phasor(mag, phase, peak/RMS tag)` (frozen e^{+jωt}/peak default;
RMS only via explicit conversion), impedance/admittance values
(`{FINITE,INFINITE,UNDEFINED}` discipline inherited from F8-D5 —
`INFINITE` behavioral open, `value=None`, never Infinity),
complex power `S = ½V·conj(I)` with F8-D4 sign regime. Every
primitive carries units + provenance-ready fields; invalid ingress
(INVALID), out-of-scope physics (UNSUPPORTED), singular ratios
(SINGULAR, e.g. `0/0` port ratios — F8-D5 `_port_ratio` precedent).

## §10 Transmission Lines

Line objects: `LineRLGC{R,L,G,C,l,f}` and `LineZGamma{Z0,γ,l,f}`
(Z0 complex allowed; both exact). Derived: `γ, Z0, βl (electrical
length, rad label), λ (via v = ω/β), attenuation e^{−αl} (REUSEd
decimal_exp), phase delay βl/ω (s)`. Load/source tagged models
(`impedance/open/short/matched`). `Zin` (sin/cos primary form),
input reflection `Γin`, delivered power, mismatch loss. Degenerate
battery: `l = 0` (identity), `γ = 0` (exact limit), open/short/
matched loads (exact Γ), lossless↔lossy continuity (R,G → 0 limit
fixture with exact-lossless reference).

## §11 Reflection

`Γ(ZL, Z0)`, `ZL(Γ, Z0)`, exact; open `+1`, short `−1`, matched `0`;
`ZL + Z0 = 0` → SINGULAR; `|Γ| > 1` representable (active) with
VSWR-gated downstream (§12). Status vocabulary: REUSEd
`ControlStatus` (`COMPLETED/INVALID/UNSUPPORTED/SINGULAR/
NUMERIC_ERROR/INCONSISTENT`; `DIVERGED/MAX_ITERATIONS`
inherited-only — P3 math is closed-form, no iterative solver).
No new states (mapping: old `CONVERGED` ≡ COMPLETED;
`UNDETERMINED` unneeded — every formula has an explicit branch).

## §12 VSWR / Return Loss

Per §6 formulas with explicit domains. Test battery: matched
(Γ=0 → VSWR=1, RL UNSUPPORTED-infinite), open/short (|Γ|=1 →
VSWR UNSUPPORTED, RL=0 exact), 2:1 (|Γ|=1/3 → VSWR=2, RL≈9.54dB
hand value), active (|Γ|=2 → VSWR UNSUPPORTED, RL≈−6.02dB
computed-with-sign), `f/fs−f` symmetry fixtures. Consistency
invariants P3-I010/I011 (VSWR↔|Γ|↔RL triangle, exact where defined).

## §13 Two-Port

Representations `Z/Y/ABCD` (+`T` scattering-transfer derived view)
as 2×2 `DecimalComplex` matrices with units per entry (F8-G `_UNITS`
table inherited: z Ω, y S, h Ω/1/1/S — h/g included for
representation completeness at matrix level; extraction stays F8-G).
Conventions FROZEN from F8-G (§30-Q4): entering currents both ports;
`V1 = A·V2 − B·I2`, `I1 = C·V2 − D·I2` (I2 entering). Conversions
`Z↔Y` (matrix inverse; singular → SINGULAR/UNDEFINED, F8-G
precedent), `Z/Y→ABCD` (standard formulas under the frozen sign),
`ABCD→Z/Y` (denominators nonzero else SINGULAR). Port order, signs
and reference impedance carried explicitly; reciprocity
(`Z12==Z21`/`Y12==Y21`/det conditions exact), symmetry
(`A==D` + port-interchange property), power conservation where
applicable. NO ambiguous conversions: every formula lists its domain.

## §14 S-Parameters

Power waves (Kurokawa, one formula — real and complex ref unified):
`a_i = (V_i + Zref·I_i)/(2√Re(Zref))`,
`b_i = (V_i − conj(Zref)·I_i)/(2√Re(Zref))`, `b = S·a`,
`Re(Zref) > 0` required else INVALID (evanescent/complex-plane refs
OUT). `S11/S21/S12/S22` with matched-port semantics; identity
passthrough (`S = [[0,1],[1,0]]` exact); matched load → zero
reflection; reciprocal (`S12 == S21` exact); lossless unitary
(`S†S = I` within 1e-40). Reference impedance explicit on every
object (default 50 Ω exact Decimal; custom real/complex tested).

## §15 ABCD

`ABCD_line = [[cosh(γl), Z0·sinh(γl)], [sinh(γl)/Z0, cosh(γl)]]`
under the F8-G sign convention (derived §6). Lossless: cos/sin form
exact. Cascade `ABCD_total = A·B·…` (exact DecimalComplex matmul,
deterministic left-to-right order). `S→ABCD` requires `S21 ≠ 0`
(SINGULAR otherwise — unilateral/isolated documented); `ABCD→S`
requires `(A+B/Z0+C·Z0+D) ≠ 0` (SINGULAR otherwise). `T` (cascade
transfer) derived from S by exact formulas for chain reasoning;
never a separate engine.

## §16 Cascading

Only `ABCD_total = Π ABCD_i` multiplies; S never multiplies directly
(hard-stop §33 item). Chain API takes blocks + per-block reference
impedances (renormalization across differing Zref is part of the
contract: convert each block to the chain reference BEFORE
multiplying — explicit, tested). Chain limit `MAX_CASCADE_BLOCKS =
64` (linear cost, digest-bounded). Singular intermediate conversion
aborts the chain with SINGULAR + index (never skipped).

## §17 Smith Mathematics

Math only, no graphics: `z = Z/Z0`, `Γ = (z−1)/(z+1)`,
`Γ → z = (1+Γ)/(1−Γ)`, `y = 1/z`, `Γ_y` via same map on `y`
(one engine: the Möbius map + inversion, shared helper);
R-circles `|Γ − r/(r+1)| = 1/(r+1)` and X-circles
`|Γ − (1+j/x)| = 1/|x|` as TESTED equations (future UI plots them;
P3 proves points satisfy them); line movement
`Γ(l) = ΓL·e^{−2γl}` (lossless: pure rotation, angle −2βl);
impedance-at-position round-trips. Matching (§18) read through Γ is
the SAME closed forms (no second matching engine — one engine, two
views; P3-I tests assert Γ-plane/S-plane agreement).

## §18 Matching

Closed-form solvable set ONLY (each: analytic solution +
realizability predicate + UNSUPPORTED otherwise):
(a) conjugate match (resistive source Rs: ZL = conj(Zs));
(b) quarter-wave (real ZL>0: `Zλ/4 = √(Z0·ZL)`, `Zin = Z0²/ZL`
verified); (c) single shunt stub (short/open ends, two analytic
lengths via tan-half-angle quadratic; forbidden-conductance region →
UNSUPPORTED); (d) single series stub (dual); (e) single series/shunt
L/C at given f (analytic reactance/susceptance). Verification
invariant: cascade(match, load) reproduces the target (Γin residual
≤ 1e-30). OUT: double-stub, broadband/multisection, synthesis
(future phase).

## §19 Invariantes

| ID | Invariante | Método | Tolerancia | Evidencia |
|:---|:---|:---|:---|:---|
| P3-I001 | Γ→Z→Γ round-trip | fórmulas cerradas | ≤1e-40 | P3-011 |
| P3-I002 | Z→Γ→Z round-trip | fórmulas cerradas | ≤1e-40 | P3-011 |
| P3-I003 | Zin directo ≡ Zin two-port | ABCD_line + carga | ≤1e-40 | P3-013 |
| P3-I004 | ABCD cascade reproducible | mismo orden ×2 | exacta | P3-014 |
| P3-I005 | S↔ABCD round-trip | fórmulas + dominio | ≤1e-40 | P3-015 |
| P3-I006 | Z↔Y round-trip | inversa exacta | ≤1e-40 | P3-016 |
| P3-I007 | matched → Γ=0 | construcción | exacta | P3-017 |
| P3-I008 | open → Γ=+1 | kind open | exacta | P3-017 |
| P3-I009 | short → Γ=−1 | kind short | exacta | P3-017 |
| P3-I010 | VSWR consistency | triángulo \|Γ\| | exacta/<1e-40 | P3-018 |
| P3-I011 | RL consistency | −20log\|Γ\| | exacta/<1e-40 | P3-018 |
| P3-I012 | λβ consistency | λ=v/f, β=2π/λ | exacta | P3-019 |
| P3-I013 | lossless unitary | S†S=I | ≤1e-40 | P3-020 |
| P3-I014 | reciprocal | S12==S21 | exacta | P3-020 |
| P3-I015 | deterministic serialization | triple dump | bytes | P3-021 |
| P3-I016 | replay equivalence | re-ejecución | digest | P3-022 |
| P3-I017 | LHP-continuity lossy→lossless | límite R,G→0 | <1e-30 | P3-023 |
| P3-I018 | Smith circle membership | ecuaciones R/X | ≤1e-40 | P3-024 |
| P3-I019 | matching verification | cascada(match,load) | ≤1e-30 | P3-025 |
| P3-I020 | GT bounds 0≤GT≤1 (passive) | definición | exacta | P3-026 |

## §20 Referencias Analíticas

Closed forms as oracles (never the engine under test): short line
(Zin≈ZL for βl≪1 — tested as limit, not equality), λ/4
(`Z0²/ZL`), λ/2 (Zin=ZL exact), open/short/matched Γ pins,
2:1-VSWR hand values, ABCD of series-Z/shunt-Y/λ/4/λ/2/ideal-TF
(canonical matrices by hand), S of attenuator/passthrough,
cascade-by-hand (2 blocks), stub lengths from the quadratic
(independent re-derivation in-test), Smith rotation by hand angles.
Hierarchy ANALYTICAL > INDEPENDENT-HP (in-test Taylor/Context,
P1-P2 precedent) > PROPERTY > REGRESSION. F8-G circuit extraction
(`abcd_parameters` at f on lumped fixtures) is the independent
EXTERNAL oracle for ABCD/S of known networks (different code path,
different math — explicitly allowed, never the sole reference).

## §21 Serialización

Schema `f8p3-rf/1` (closed, versioned): line/network/S/match/margin
documents; deterministic dumps; `Decimal→str()` (never `normalize()`,
F8-N D-R1); `DecimalComplex→{re,im}`; no NaN/Infinity/objects/class
names; `≤ 64 MiB` guard. REUSE the `f8p2-dsp/1` envelope mechanics
(pre-convert + REUSEd `canonical_json`/`chain_digest` from
`metrology.o5_traceability`) — no second hash construction, no second
canonicalizer. Tamper → INCONSISTENT on load (F8-N/O/P2 precedent).

## §22 Replay / Provenance

States `EQUIVALENT/RESULT_DIFFERS/VERSION_MISMATCH/SCHEMA_MISMATCH/
INVALID_SERIALIZATION` (+ tested aliases `VALID`/`RESULT_DIFFERENT`),
REUSEd vocabulary and mechanics. Replay re-evaluates the RF
specification under same schema+version and compares digests; notes/
annotations never affect digests (F8-N precedent).

## §23 Determinismo

same input → same result → same canonical serialization → same digest;
triple-run mandated (RUN 1/2/3, bytes+digest identical); no clock/UUID/
random/dict-order/locale/platform dependence; insertion-ordered blocks
in cascades; no RNG anywhere in `rf/` (seeds only inside reused F8-M
paths — none planned natively).

## §24 Seguridad

Banned in the new core (grep + AST, AST authoritative):
`eval, exec, compile, getattr, setattr, open, subprocess, pickle,
marshal, importlib, socket, urllib, numpy, scipy, math`
(`re.compile` ≠ builtin `compile()`); frozen-dataclass discipline;
validated constructors only; hostile battery (malformed payloads,
unknown schema, wrong version, tampered digest, NaN/Infinity text,
oversize, invalid denominator, invalid sample — n/a —, degree/order
overruns, pathological complex (NaN components, zero denominators),
giant inputs vs `MAX_CASCADE_BLOCKS`/64 MiB).

## §25 Límites de Recursos

| Límite | Valor | Razón |
|:---|:---|:---|
| Per-op RF (Γ/Z/VSWR/S/conv) | O(1) | closed forms, bounded flops |
| 2-port object | 2×2 fixed | domain definition |
| `MAX_CASCADE_BLOCKS` | 64 | linear matmul cost, digest-bounded |
| `MAX_MATCH_CANDIDATES` | 8 | 2 solutions × {short,open} × {series,shunt} bound |
| `MAX_SERIALIZED` | 64 MiB | inherits F8-N (DoS guard) |
| Frequency | f > 0 finite, unbounded above | Decimal exact, no band cap |

Budgets are rejections, never truncations.

## §26 Arquitectura DAG

```text
rf/primitives ─┐
rf/lines ──────┤→ control.errors, control.response.decimal_exp
rf/networks ───┤→ math.* (complex/trig/log/sqrt), units
rf/sparams ────┤→ metrology.o5 (canonical_json/chain_digest only)
rf/smith ──────┤
rf/matching ───┘
rf/margins ────┘
rf/report ─────┘
```

Allowed: `rf → {control, math.*, units, metrology.o5}`.
Forbidden: `control → rf`, `math → rf`, `units → rf` (upward edges),
`rf → lab` (N-110), `rf → simulation` (float world), `rf → UI`,
`rf → filesystem`, `rf → network`. Verified by AST test (§27,
N-110 style + P2 `test_dsp_layer_direction` precedent).

## §27 Tests

P3-001…P3-044 (IDs stable; implementation extends only with
justification; never reduces):

| ID | Área | Oracle |
|:---|:---|:---|
| P3-001…006 | Primitives (f/T/λ, Z/Y, S, RMS/peak, units) | hand values + units |
| P3-007…012 | Γ/VSWR/RL/open/short/matched/active | hand pins + domains |
| P3-013…016 | Zin direct≡2-port, λ/4, λ/2, short-line limit | closed forms |
| P3-017…019 | Z0/γ/λβ, lossy→lossless, degenerate battery | analytic + limits |
| P3-020…024 | Z/Y/ABCD/T + conversions + round-trips | exact + F8-G extraction |
| P3-025…027 | S walls, reciprocity, unitarity | matrix identities |
| P3-028…029 | Cascade (2–3 blocks), singular S21 abort | hand cascade + SINGULAR |
| P3-030…031 | Smith maps + circles + rotation | equations + hand angles |
| P3-032…034 | Matching (conjugate/λ4/stub/LC) + verification | closed + residual ≤1e-30 |
| P3-035 | Margins (VSWR/RL/IL/ML/GT/K-μ) | hand + bounds |
| P3-036 | Hostile battery | typed states |
| P3-037 | Determinism triple-run | 1 digest |
| P3-038 | Serialization round-trip/tamper/mismatch | 5 states |
| P3-039 | Replay equivalence | digest |
| P3-040 | Security AST + grep | 0 banned |
| P3-041 | No-duplication AST/grep | no 2nd engines |
| P3-042 | Architecture DAG | edge tests |
| P3-043 | Resource limits/bench | recorded, no wall asserts |
| P3-044… | Regression F7-B7,H…P2 | suites green |

Each test records input/expected/oracle/tolerance/failure-meaning
(§75-analogue; no bare "close enough").

## §28 Regresión

Future implementation runs F7-B7, F8-H, F8-I, F8-J, F8-K, F8-L, F8-M,
F8-N, F8-O, F8-P1, F8-P2, F8-P3: zero regressions accepted; never
modify earlier tests to hide failures; global `pytest -q` 0 failed;
new skips require justification (reportlab precedent).

## §29 Riesgos

| Riesgo | Prob. | Impacto | Detección | Mitigación | Test |
|:---|:---:|:---:|:---|:---|:---|
| Convención de signo (ABCD/I2) | M | A | P3-020 vs F8-G | convención congelada F8-G,Dual review | P3-020…024 |
| Referencia de impedancia (real vs compleja) | M | A | P3-025 | Kurokawa único + Re>0 gate | P3-025…027 |
| Complejos (ramas sqrt/inversos) | M | A | P3-013…017 | sqrt principal documentado, SINGULAR explícito | P3-016…019 |
| Singularidades (tan π/2, S21=0, 0/0) | M | A | P3-036 | forma sin/cos primaria, dominios | P3-007…029 |
| Pérdida de precisión (e^{±αl} extremo) | B | M | P3-017 | Decimal 1e±999999999 + ingress gate | P3-017/036 |
| Cascada incorrecta (S×S directo) | B | A | P3-028 | hard-stop §33, solo ABCD×ABCD | P3-028 |
| Conversión S↔ABCD singular | B | A | P3-028/029 | dominios + SINGULAR indexado | P3-028 |
| Líneas muy largas (βl≫2π) | B | B | P3-016 | reducción trig certificada | P3-016 |
| αl extremo | B | B | P3-017 | exp Decimal + gate no-finito | P3-017 |
| Γ cerca de 1 (VSWR/RL sensibles) | M | M | P3-007 | fórmulas exactas, UNSUPPORTED en ±1 | P3-007/008 |
| Matching degenerado (sin solución) | M | M | P3-032 | predicado realizabilidad + UNSUPPORTED | P3-032…034 |
| Matrices singulares (Z↔Y) | B | M | P3-024 | SINGULAR/UNDEFINED F8-G precedent | P3-024 |
| Overflow/underflow Decimal | B | M | P3-036 | ingress finito + exactitud | P3-036 |
| Determinismo (orden, redondeo) | B | M | P3-037 | triple-run + canónico | P3-037…039 |
| Duplicación de infraestructura | B | A | P3-041 | allowlist + DAG | P3-041/042 |
| Scope creep (antenas/link-budget) | M | M | §4/Q-gate | OUT explícito + UNSUPPORTED | P3-036 |
| Regresión H→P2 | B | A | suites + pytest | solo añade paquete | P3-044 |

## §30 Decisiones

Todas cerradas (ninguna bloqueante):
- **Modelo de línea**: telegrapher RLGC primario + constructor directo
  (Z0,γ,l) equivalente; Z0 siempre derivado o medido, nunca contradictorio.
- **Z0 complejo**: SUPPORTED (exigido por lossy).
- **Referencia S compleja**: SUPPORTED vía Kurokawa único,
  `Re(Zref) > 0` else INVALID.
- **Convenciones ABCD**: EXACTAMENTE F8-G (V1=A·V2−B·I2, I1=C·V2−D·I2,
  corrientes entrantes). Sin variantes.
- **Ganancia**: transducer gain GT (análisis) SUPPORTED; available/
  max-stable/unilateral OUT (futuro).
- **Matching**: conjunto cerrado §18 (conjugado/λ4/stub/LC) + UNSUPPORTED
  explícito; double-stub/banda ancha/síntesis OUT.
- **Smith**: exclusivamente matemático en P3 (sin plots).
- **Pérdidas**: SUPPORTED (RLGC + límites exactos al lossless).
- **Cascada**: 64 bloques, renormalización de Zref explícita, T como
  vista derivada.
- **Antenas/link-budget-síntesis**: OUT → F8-P5 (roadmap:212). P3
  entrega primitivas GT/IL/ML. La mención `antenas, link budget` de la
  fila P3 (:210) se honra como tema aguas-abajo, no como alcance P3.

## §31 Deviations

Ninguna respecto al repositorio (fase greenfield sobre motores
certificados; convenciones F8-G/D4/D5 heredadas verbatim, no
reinterpretadas). Respecto al mandato: replay aliases heredados
(`VALID`/`RESULT_DIFFERENT`); `ANTENAS/link-synthesis` clasificados
OUT→P5 con la fila :212 como evidencia (no es scope recortado en
silencio: §4 + §30 lo declaran); ninguna tolerancia inventada.

## §32 Certification Plan

Implementación futura (fuera de esta fase): `rf/` (8 módulos §5) +
`tests/test_f8p3_rf.py` (P3-001…P3-044) + extensión AST (`control↛rf`,
`{mna,ac,lab}↛rf`, `rf↛{lab,simulation}`) + `GATE-F8P3.md` con evidencia
real + roadmap mínimo (P3 CERTIFIED, P4 NEXT) + commit único +
push (nunca force). Criterio: ecuación + referencia independiente +
error cuantificado + invariante + límites + determinismo + seguridad +
regresión H→P2 + pytest global 0 failed.

## §33 Verdict

Las diez preguntas del mandato (§30-origen) quedan respondidas en
§6/§7/§19/§8/§20/§11/§20/§5+§26/§25/§27. Alcance literal del roadmap
(`:210`, deps `F8-D1/D2, F8-P2`), matemática cerrada (telegrapher,
Möbius, Kurokawa, ABCD×ABCD, stub cuadrático), convenciones cerradas
(F8-G/D4/D5 verbatim), arquitectura cerrada, tolerancias justificadas,
sin preguntas críticas abiertas.

F8-P3 DESIGN READY
