# F8-P4 Design Gate — Digital Communications / Comunicaciones Digitales

Documentation only: no code under `src/` was created or modified, no
tests were written, no engine was altered. The only output of this
phase is this file plus one local commit (no push).

## §1 Estado

- Repository `Damaga2005/AcademicCore`, branch `main`, baseline **`cea608f`**
  (`feat(engineering): certify F8-P3 RF and transmission lines`),
  `HEAD == origin/main == cea608f` (verified at audit time; working tree clean).
- Certified at baseline: F0–F7 (incl. F7-B7 GUM), F8-A … F8-P3
  (gates on disk through `GATE-F8P3.md`; roadmap §6.1 lists F8-P3
  CERTIFICADO and marks **F8-P4 (NEXT)** per §5.1).
- F8-P4 literal definition (roadmap:172 + table:211): `Comunicaciones
  Digitales`, deps `F8-P2, F8-P3`, scope `Modulaciones, constelaciones,
  BER/SNR, Shannon`. The `F8-P5` row (:212) claims link-budget synthesis
  + modulation + noise + antennas as the downstream integrator; antennas,
  radiated models and satcom link-budget synthesis therefore belong to
  F8-P5, never to P4 (§4/§30 of this gate).
- No-duplication grep (`src/`, case-insensitive): `constellation|
  qpsk|bpsk|qam|modulat|demodul|ber\b|shannon|awgn|matched.?filter|
  pulse.?shap|raised.?cosine|rssi|evm\b` → zero functional hits (only
  prose mentions in gates/roadmap and generic `modulus()` accessors on
  `DecimalComplex`). `TODO|FIXME|NotImplemented|placeholder` in
  engineering → only Python-protocol returns, superseded `models.py`
  ideals, unrelated tracks (same verdict as P2/P3 audits).

## §2 Baseline

- `git status --short` → empty (clean).
- `git branch --show-current` → `main`.
- `git rev-parse HEAD` → `cea608f0dfba7b7101e21b9eeaa1336560401ec1`.
- `git rev-parse origin/main` → identical.
- `git log -n 15 --oneline` head `cea608f` (P3 certification), then
  `978667e` (P3 design gate), `8ede3ee` (P2 certification).

## §3 Roadmap (fuente normativa)

| Campo | Valor literal (roadmap) |
|:---|:---|
| Nombre exacto | `F8-P4 — Comunicaciones Digitales` (§5.1:172, tabla:211) |
| Posición | `[10º] (NEXT)` — primera fase pendiente de la familia F8 |
| Dependencias | `F8-P2, F8-P3` (tabla:211) |
| Objetivo | Capa matemática de comunicaciones digitales sobre DSP + RF conducida |
| Alcance literal | `Modulaciones, constelaciones, BER/SNR, Shannon` |
| Relación con F8-P2 | P2 aporta secuencias uniformes, DFT/FFT, muestreo/Nyquist/aliasing, filtros FIR/IIR, serialización `f8p2-dsp/1`, digests y replay |
| Relación con F8-P3 | P3 aporta disciplina RF conducida (frecuencia Hz, potencia W, dB como label, fasores pico, parámetros S); P4 **no** depende funcionalmente de `rf/` (§9, §34) |
| Siguiente fase | `F8-P5 — Síntesis Satcom [11º]`: link budget + modulación + ruido + antenas |
| Límites explícitos | Antenas, propagación radiada, link-budget-síntesis → F8-P5; `coding` no aparece en la fila P4; OFDM/MIMO/ecualización no aparecen en la fila P4 |

Si el roadmap calla sobre un área (codificación, OFDM, MIMO, sincronización
con lazos), este gate la clasifica UNSUPPORTED con la fila :211/:212 como
evidencia — nunca se rellena por suposición (§49).

## §4 Objetivo

Design — not implement — a coherent mathematical layer for digital
communications over the certified engines: bits/symbols/alphabets, Gray-mapped
constellations, coherent modulation/demodulation (BPSK/QPSK/M-PSK/square
M-QAM, ASK/OOK as 1-D specializations, coherent FSK), Nyquist pulse shaping
(rectangular/sinc/RC/RRC), ideal uniform sampling reuse, AWGN channel with
closed Eb/N0–Es/N0–SNR conventions, matched-filter/correlator detection,
analytic BER/SER with independent oracles, Shannon capacity, seeded Monte
Carlo simulation with replayable streams, deterministic serialization and
traceability. Precise enough that another person can implement F8-P4 without
inventing fundamental mathematical decisions.

## §5 Alcance

F8-P4 is the **digital-comms mathematics layer** over the certified engines.
It adds no circuit solver, no Bode engine, no transient integrator, no second
sampler, no GUM math, no second polynomial/root/stability/serialization/
digest/replay implementation, no channel coder, no tracking loop, no OFDM/
MIMO/equalizer, no SDR/ADC/fixed-point model.

| ID | Capability |
|:---|:---|
| P4.1 | Bits, symbols, alphabets, bit↔symbol mapping (MSB-first, power-of-2 M) |
| P4.2 | Deterministic constellations: id/label/coordinate/energy, unit-average-energy normalisation, Gray maps, dmin |
| P4.3 | Coherent modulation/demodulation: BPSK, QPSK, M-PSK, square M-QAM (closed M set) |
| P4.4 | 1-D specializations: ASK (M-ASK), OOK (as ASK-2 degenerate), documented — no second engine |
| P4.5 | Coherent FSK (orthogonal spacing, one formula, coherent detection only) |
| P4.6 | Baseband complex model + documentary passband mapping (frozen I/Q convention, §14) |
| P4.7 | Pulse shaping: rectangular (exact), sinc (truncated, tail bound), raised-cosine, root-raised-cosine, Nyquist/ISI condition |
| P4.8 | Ideal sampling reuse (P2): symbol rate, sample rate, integer samples/symbol, Nyquist/alias verdicts |
| P4.9 | AWGN channel (real/complex, one-sided/two-sided PSD closed), static impairments (gain/phase/frequency/timing offsets as analytic transforms) |
| P4.10 | Detection: threshold, correlator, matched filter, minimum-distance ML (uniform priors; MAP distinguished) |
| P4.11 | Metrics: SNR, Eb/N0, Es/N0 with closed conversions; analytic BER/SER (EXACT vs APPROXIMATION labelled) |
| P4.12 | Shannon: Hartley–Shannon capacity `C = B·log2(1+SNR)`, spectral efficiency, −1.59 dB limit (documented) |
| P4.13 | Seeded simulation: counter-based deterministic PRNG stream, same-seed determinism, MC never the primary oracle for closed forms |
| P4.14 | Canonical serialization `f8p4-comms/1` + digests + replay/compare (P2/P3 pattern, REUSEd helpers) |

## §6 Dependencias

```text
comms → {dsp (sequences/sampling/DFT), control.errors, control.response.decimal_exp,
         math.* (trig/log/sqrt/complex), units, metrology.o5_traceability (digest helpers)}
comms ↛ rf (no functional import; dB/Hz/W discipline reused by value, §9)
dsp ↛ comms, control ↛ comms, math ↛ comms, units ↛ comms, rf ↛ comms (acyclicity, AST-tested)
comms ↛ {lab, simulation.py, mna, ac, UI, filesystem, network}
```

P4 consumes P2 vocabularies (Sequence, Nyquist, alias, DFT for spectral
checks) and P1/P3 conventions (dB labels, peak phasors, Quantity boundaries)
without importing live-circuit or float-world modules.

## §7 Supported

| Área | Estado | Condición |
|:---|:---|:---|
| Bit/Symbol/Alphabet/Mapping | SUPPORTED | §12 |
| Baseband complex | SUPPORTED | §14 |
| BPSK | SUPPORTED | §15, EXACT BER |
| QPSK (Gray) | SUPPORTED | §16, EXACT BER |
| M-PSK (M=8,16,32,64) | SUPPORTED | §17, SER APPROXIMATION labelled |
| Square M-QAM (M=4,16,64,256) | SUPPORTED | §17, SER APPROXIMATION labelled |
| ASK / OOK | SUPPORTED (1-D specialization) | §18, coherent |
| Coherent FSK | SUPPORTED (orthogonal, coherent only) | §18 |
| Rectangular/sinc/RC/RRC pulse | SUPPORTED | §19, singular limits closed |
| Ideal sampling reuse | SUPPORTED | §20, integer sps |
| AWGN (real/complex) | SUPPORTED | §21, PSD conventions closed |
| Coherent detection (threshold/correlator/matched/ML) | SUPPORTED | §24/§25 |
| BER/SER/SNR/EbN0/EsN0 | SUPPORTED | §23, EXACT vs APPROX separated |
| Shannon capacity | SUPPORTED | §21/§23 |
| Seeded MC simulation | SUPPORTED | §22, deterministic streams |

## §8 Limited

| Área | Estado | Condición |
|:---|:---|:---|
| Passband representation | LIMITED | documentary mapping from baseband (§14); no second modulator; fc explicit |
| Static channel impairments (gain, phase rotation, frequency offset, timing offset) | LIMITED | analytic frozen transforms (§26); no tracking, no estimation loops |
| Non-coherent detection | LIMITED | OOK/FSK energy detection only (§25); PSK/QAM stay coherent |
| Sinc pulse | LIMITED | truncated lobes + documented tail bound (the only truncation tolerance) |
| Simulation length | LIMITED | budgets in §35; rejections, never truncations |

## §9 Unsupported

| Área | Estado | Motivo / hogar |
|:---|:---|:---|
| Channel coding (parity/Hamming/block/conv/CRC/RS/LDPC/interleaving) | UNSUPPORTED | roadmap :211 silent; no second polynomial/bit engine (§28/§29) |
| Synchronization loops (carrier/timing/frequency recovery, PLL, iterative) | UNSUPPORTED | roadmap silent; state/update/stability scope belongs to a future phase (§27) |
| OFDM | UNSUPPORTED | needs framing/IFFT-multiplex engine; future phase |
| MIMO / diversity combining / beamforming | UNSUPPORTED | needs matrix-channel engine; future phase |
| Equalization (ZF/MMSE/DFE/adaptive) | UNSUPPORTED | needs estimation machinery; future phase |
| Multipath fading models (Rayleigh/Rician) | UNSUPPORTED | statistical channel synthesis; future/P5 |
| Link-budget synthesis, antennas, radiated EM | UNSUPPORTED | F8-P5 integrator (:212) |
| SDR / ADC-DAC / quantization / fixed point | UNSUPPORTED | no certified quantization model (P2 precedent) |
| Non-causal/bilateral constructs | UNSUPPORTED | causality discipline inherited |
| Plots/GUI/hardware | UNSUPPORTED | presentation layer; constellations stay math-only |

SUPPORTED/LIMITED/UNSUPPORTED legend: SUPPORTED = full contract below;
LIMITED = exact degenerate handling documented per case; UNSUPPORTED =
explicit typed state with reason, never silent.

## §10 Investigación

### 10.1 Información digital — SUPPORTED

Bits `{0,1}`, símbolos `0..M−1`, alfabetos de tamaño M potencia de 2,
`k = log2(M)` bits/símbolo, `Rb = k·Rs`, energía por bit/símbolo
`Eb = Es/k` bajo normalización de energía media unitaria. M no potencia
de 2 → INVALID (sin padding silencioso; el padding explícito serializa
su longitud, §12).

### 10.2 Señales — SUPPORTED (baseband) / LIMITED (passband)

Señal baseband compleja `s = I + jQ` (DecimalComplex, prec 50).
Envolvente compleja, fase `atan2` certificado, amplitud/módulo certificado.
Passband solo como mapeo documental §14 con `fc > 0` explícita.

### 10.3 Modulación — ver §7/§8/§9

ASK/OOK/FSK/PSK/BPSK/QPSK/M-PSK/QAM/M-QAM investigadas; el conjunto
SUPPORTED queda cerrado en §7. Cross-QAM, APSK, CPM, GMSK, OFDM-indexadas:
UNSUPPORTED (fuera de la fila :211).

### 10.4 Pulse shaping — SUPPORTED (§19)

Rectangular (exacta), sinc (truncada con cola acotada), Nyquist RC/RRC con
roll-off `α ∈ [0,1]`, ancho de banda `(1+α)/(2Ts)`, condición de Nyquist
ISI-cero, singularidades con límite cerrado.

### 10.5 Canal — AWGN SUPPORTED; resto ver §26

AWGN con PSD one-sided/two-sided cerrada. Atenuación/fase/offset-f/offset-t
como transforms analíticos estáticos (LIMITED). Multipath UNSUPPORTED.

### 10.6 Detección — SUPPORTED coherente (§25)

Coherent threshold/correlator/matched-filter/minimum-distance ML.
Non-coherent solo OOK/FSK (LIMITED). MAP solo si se declaran priors
(por defecto uniformes → ML = MAP, documentado).

### 10.7 Métricas — SUPPORTED (§23)

BER/SER/`Pe`, SNR, `Eb/N0`, `Es/N0` con conversiones cerradas y dominios
`[0,1]` para probabilidades (nunca fuera de rango).

### 10.8 Codificación — UNSUPPORTED

Parity/Hamming/block/conv/CRC/RS/LDPC/interleaving investigados y
excluidos: la fila :211 no los lista y el repo no dispone de motor de
codificación certificable sin duplicar polinomios/secuencias (§28/§29).

## §11 Matemática

Para cada funcionalidad SUPPORTED el contrato fija: variables, dominio,
ecuaciones, convenciones, unidades, entradas, salidas, singularidades,
precisión, invariantes y oracle. Ninguna fórmula se acepta sin dominio +
convención + unidades + tratamiento de casos límite (§49 hard-stop).

Núcleo común:

- Alfabeto `A = {0..M−1}`, `M = 2^k`, `k ≥ 1` entero.
- Constelación `C: id → (label ∈ {0,1}^k, z ∈ ℂ)` con `⟨|z|²⟩ = 1`
  (energía media unitaria), orden determinista por id, labels únicos.
- `Es = ⟨|z|²⟩ = 1` por construcción; `Eb = Es/k`; `Rs` (baud, Hz),
  `Rb = k·Rs` (bit/s); `Ts = 1/Rs`, `Tb = 1/Rb`.
- Ruido: PSD one-sided `N0` (W/Hz); compleja `n ~ CN(0, N0)` por muestra
  compleja (N0/2 por dimensión real); real `n ~ N(0, N0/2)` por dimensión.
- `Es/N0`, `Eb/N0 = Es/(k·N0)`, `SNR = Es·Rs/(N0·B)` con `B` explícito;
  en el caso Nyquist `B = Rs`: `SNR = Es/N0`.
- Oracles: derivación matemática > caso manual > identidad cerrada >
  referencia académica > motor certificado designado (nunca dos funciones
  de la misma implementación futura como oracle cruzado, §28).

## §12 Bits y símbolos

- `Bit ∈ {0,1}` (int); `Symbol ∈ {0..M−1}` (int); `Alphabet(M)` con
  `M = 2^k`, `1 ≤ k ≤ 8` (M ≤ 256, §35).
- `map_bits(bits, k)`: primer bit = MSB; longitud no múltiplo de k →
  INVALID (sin padding silencioso). `pad_bits(bits, k)` explícito:
  añade ceros y registra `pad_len` en el documento serializado; el
  `unmap` recupera exactamente los bits originales (invariante P4-I001).
- `unmap_symbols(syms, k)`: round-trip exacto (P4-I002).
- `Rb = k·Rs` con `Quantity` (Hz / bit/s como label entero); `Rs > 0`.
- Unidades: bits/símbolos adimensionales exactos (int/tupla); tasas en Hz.

## §13 Constelaciones

Representación inmutable y determinista: tupla ordenada por symbol id de
`(id, label, z: DecimalComplex, energy = |z|²)`.

- Orden: id ascendente; normalización: energía media exactamente 1
  (factor `1/sqrt(Es_avg)` aplicado una vez en construcción, registrado).
- Energía máxima, distancia mínima `dmin = min|zi − zj|` registradas.
- Gray mapping donde corresponda (BPSK/QPSK/M-PSK/M-QAM cuadrada);
  propiedad Gray verificada exhaustivamente para M ≤ 256 (P4-I006).
- Invariantes: labels únicos, coordenadas finitas, orden determinista,
  normalización determinista (P4-I003/I004/I005/I006).
- Sin gráficos (las constelaciones son matemática; el plot pertenece a UI).

## §14 Modulación

Para cada modulación SUPPORTED:

- input bits → symbol mapping → complex baseband symbol `z` (Es unitaria).
- passband documental (si aplica):
  `s_pb(t) = I(t)·cos(2π·fc·t) − Q(t)·sin(2π·fc·t)`,
  `fc > 0` (Quantity Hz) explícita, fase inicial 0, convención I/Q y
  signos congelados (sin variantes).
- energía/fase/amplitud: `|z|²` por símbolo; fase `atan2(Q, I)` certificado;
  RMS/peak según disciplina F8-D4/RF (peak por defecto en fasores).
- demodulation rule + decision rule por esquema (§15–§18, §25).
- I/Q, cos/sin, signos, fase inicial, normalización y RMS/peak quedan
  congelados aquí; cualquier desviación futura es DESIGN CONFLICT.

## §15 BPSK

- `0 → +1`, `1 → −1` (energía unitaria, fase 0/π).
- Demodulación coherente: `decide(y) = 0 si Re(y) ≥ 0, 1 en otro caso`.
- BER exacto en AWGN: `BER = Q(sqrt(2·Eb/N0)) = ½·erfc(sqrt(Eb/N0))`.
- Caso manual: `Eb/N0 = 0 dB` → `BER = ½·erfc(1) ≈ 0.0786496…`
  (verificable sin el futuro motor, oracle manual §28).
- Invariantes P4-I007/I008/I010.

## §16 QPSK

- Orden de fases congelado (Gray, primer cuadrante primero):
  `00 → (1+j)/√2`, `01 → (−1+j)/√2`, `11 → (−1−j)/√2`, `10 → (1−j)/√2`.
- Energía unitaria; `Es = 2·Eb` **justificado**: 2 bits/símbolo a Es
  unitaria ⇒ `Eb = Es/2` por definición de §11 (no se asume: se deriva
  de la normalización adoptada y se testea en P4-I008).
- Demodulación: decisión por cuadrante (signos de I y Q).
- BER (Gray, coherente): `BER = Q(sqrt(2·Eb/N0))` (igual que BPSK);
  `SER ≈ 2·Q(sqrt(2·Eb/N0))` (APPROXIMATION etiquetada, §23).

## §17 M-PSK / QAM

- M-PSK: `M ∈ {8,16,32,64}`, puntos `zk = exp(j·(2πk/M + φ0))`,
  `φ0 = 0` congelado, Gray binario reflejado en el anillo; energía
  unitaria; `dmin = 2·sin(π/M)`; mapping y propiedad Gray registrados.
- QAM cuadrada: `M ∈ {4,16,64,256}` (QPSK ≡ 4-QAM por construcción),
  niveles I/Q `±1, ±3, …, ±(√M−1)`, spacing 2, energía media
  `Es_avg = 2(M−1)/3`, normalización `1/sqrt(Es_avg)`; Gray por cuadrante
  + filas/columnas; `dmin = 2/sqrt(Es_avg)` registrado.
- Fórmulas de error: solo BPSK/QPSK son EXACT; M-PSK
  `SER ≈ 2·Q(sqrt(2·Es/N0)·sin(π/M))` y M-QAM cuadrada
  `SER ≈ 4(1−1/√M)·Q(sqrt(3·Es/((M−1)·N0)))` son APPROXIMATION
  (etiquetadas como tales en código, docs y tests); el oracle NUMERICAL
  es integración Monte Carlo seeded con cola acotada + referencia
  académica citada (nunca presentada como exacta).

## §18 FSK / ASK / OOK

- ASK coherente: niveles `Ak = (2k − M + 1)·d/2`, `M = 2^k ≤ 64`,
  normalizados a Es unitaria; decisión por umbrales equidistantes (ML).
- OOK: ASK-2 degenerada (`0 → 0`, `1 → √2` antes de normalizar;
  documentada como caso 1-D, sin segundo motor); detección coherente por
  umbral `√2/2` o no-coherente por energía (LIMITED).
- FSK coherente: tonos `fi = fc + i·Δf`, separación ortogonal
  `Δf = 1/(2·Ts)` (mínima, coherente) registrada; fase continua por
  símbolo (fase inicial 0 por símbolo, documentado); energía unitaria;
  detección por banco de correladores (ML); BER BFSK coherente
  `BER = Q(sqrt(Eb/N0))` EXACT.
- FSK no-coherente, CPFSK/GMSK, desviaciones arbitrarias: UNSUPPORTED.

## §19 Pulse shaping

- Rectangular: `p(t) = 1` en `[0,Ts)`, energía `Ts` (exacta).
- Sinc: `p(t) = sinc(t/Ts)` truncada a `±L` lóbulos (`L ≤ 5000`,
  precedente P2 `MAX_RECON_LOBES`); identidad de exactitud nodal
  `p(n·Ts) = δ[n]` (finita, exacta); punto medio con cola acotada
  (única tolerancia de truncamiento, §33).
- Raised-cosine: `h(t) = sinc(t/Ts)·cos(παt/Ts)/(1 − (2αt/Ts)²)`,
  `α ∈ [0,1]`; ancho de banda `(1+α)/(2·Ts)`; condición Nyquist ISI-cero
  `h(n·Ts) = δ[n]` (P4-I012).
- Root-raised-cosine: par transmisor/receptor con
  `h_rrc ∗ h_rrc = h_rc` (verificado por convolución discreta en el
  plan de tests); mismo `α`, misma banda.
- Singularidades cerradas analíticamente: `t = 0 → h = 1`;
  `t = ±Ts/(2α)` (α > 0) → límite `πα/(4)·sinc(±1/(2α))` por L'Hôpital
  (nunca `0/0` numérico); `α = 0` colapsa bit a bit a sinc por la misma
  rama de código (sin segunda implementación).

## §20 Sampling

Reutilización P2 (sin segundo motor de sampling):

- `Rs` (baud, Hz > 0), `fs` (Hz > 0), `sps = fs/Rs` entero `1 ≤ sps ≤ 64`
  con `fs·Ts` exacto; violación → INVALID.
- Veredictos `nyquist_verdict`/`alias_of` REUSEd de `dsp.sampling`;
  secuencias de símbolos sobremuestreadas habitan `dsp.Sequence`
  (límite `MAX_SEQUENCE_N = 65536` heredado).
- Reconstrucción `reconstruct` REUSEd solo como oracle de identidad
  nodal en fixtures; el pulso P4 no reimplementa sinc.

## §21 AWGN

- PSD one-sided `N0` (W/Hz, Quantity energía/tiempo); two-sided `N0/2`
  por dimensión real — convención cerrada (nunca mezcladas; cada función
  declara cuál usa).
- Ruido real: `n ~ N(0, N0/2)`; ruido complejo: `n ~ CN(0, N0)`
  (`N0/2` por I/Q). `mean = 0` exacto; `variance` registrada.
- Relaciones cerradas: `SNR = Es·Rs/(N0·B)`; caso Nyquist `B = Rs`:
  `SNR = Es/N0`; `Es/N0 = k·Eb/N0`; en dB como labels (nunca Quantity).
- Dominios: `N0 > 0` finito; `N0 ≤ 0` o no finito → INVALID;
  `Eb/N0`, `Es/N0`, `SNR` finitos (dB cualquier real finito).
- Shannon (§23): `C = B·log2(1 + SNR)` con `log2` vía `decimal_log10`
  certificado (`log2(x) = log10(x)/log10(2)`); límite `Eb/N0 → ln 2`
  (−1.59 dB) documentado.

## §22 Randomness

- PRNG determinista por contador: `u_i = SHA256(seed ‖ 0x00 ‖ i)/2^256`
  en `[0,1)` (uniforme exacto por construcción entera); gaussianas por
  Box–Muller sobre `decimal_sin/cos/log/sqrt` certificados (NEW thin
  helper `uniform_stream`, justificado: el repo no posee stream uniforme
  version-estable — `random.Random` depende de versión stdlib; F8-M aporta
  solo la disciplina de semilla `int ≥ 0`, no un stream reutilizable).
- Contrato: `same seed + same input = same sequence` (P4-I015);
  semilla `int ≥ 0` (precedente F8-M/Lab `INVALID_SEED`); semilla ausente
  o negativa/booleana → INVALID.
- Separación estricta: `analytical result` (fórmula cerrada, oracle
  primario) vs `simulation result` (Monte Carlo, oracle secundario con
  intervalo documentado). El Monte Carlo nunca es oracle primario de una
  fórmula cerrada.
- Sin aleatoriedad del SO como fuente normativa (`os.urandom`, `random`
  sin semilla: prohibidos por AST).

## §23 BER / SER

- `BER, SER, Pe ∈ [0,1]` (Decimal exacto en bordes); fuera de rango →
  INVALID (nunca se acepta `BER < 0 ∨ BER > 1`, `SER < 0 ∨ SER > 1`).
- Fórmulas: BPSK/QPSK/BFSK EXACT (§15/§16/§18); M-PSK/M-QAM
  APPROXIMATION etiquetada (§17); cada una con dominio, unidades
  (adimensional), precisión (§33) y oracle (§28).
- Fixtures analíticos: curvas `SNR → BER`, `Eb/N0 → BER`, `Es/N0 → SER`
  para BPSK en `Eb/N0 ∈ {−2, 0, 2, 4, 6, 8, 10} dB` con valores
  `½·erfc(sqrt(10^(dB/10)))` precalculados a 12 dígitos (casos manuales).
- Shannon: eficiencia espectral `C/B = log2(1+SNR)` como curva de
  referencia (no es BER; no se mezclan).

## §24 Matched filter

- Continuo: `h(t) = s*(T − t)` (conjugado y reverso temporal de la forma
  de pulso); propiedad de máximo SNR demostrada por Cauchy–Schwarz
  (derivación en el docstring futuro + test de identidad, no solo la
  afirmación).
- Discreto: `h[n] = conj(s[L − 1 − n])`; identidad
  matched ≡ correlator demostrada por igualdad de evaluación (P4-I013).
- Separación continuo/discreto: ambas ramas con sus dominios; el filtro
  digital P2 NO se asume automáticamente matched de P4 (se demuestra la
  identidad o no se reclama).

## §25 Detección

Para cada detector SUPPORTED: input (muestra compleja + constelación),
statistic, threshold/decision regions, decision, error event.

- Coherente: umbral 1-D (BPSK/ASK/OOK), cuadrante (QPSK), distancia
  mínima ML (M-PSK/M-QAM/FSK-coherente). ML con priors uniformes;
  MAP solo con priors declarados (nunca mezclar ML/MAP sin priors).
- No-coherente (LIMITED): OOK/FSK por energía `|y|²` vs umbral;
  PSK/QAM quedan coherentes (documentado).
- Correlator vs matched: misma evaluación (P4-I013); threshold como
  caso 1-D del ML (identidad testeada).

## §26 Canales

| Canal | Modelo | Estado |
|:---|:---|:---|
| AWGN | `y = x + n`, `n ~ CN(0,N0)` | SUPPORTED (§21) |
| attenuation | `y = a·x + n`, `a > 0` real exacto | LIMITED (estático) |
| phase rotation | `y = x·e^{jφ} + n`, `φ` rad label | LIMITED (estático) |
| frequency offset | `y_n = x_n·e^{j2πΔf·nT} + n`, `Δf` Hz | LIMITED (estático, sin tracking) |
| timing offset | interpolación fraccional del pulso en `τ ∈ [0,Ts)` | LIMITED (estático) |
| multipath | — | UNSUPPORTED (→ futuro/P5) |

Cada modelo declara parámetros, dominio, unidades (`a` adimensional,
`φ` rad label, `Δf` Hz, `τ` s) y determinismo (todos deterministas dado
el stream de ruido). Ningún modelo EM de P3 se introduce (sin líneas,
sin S, sin Smith).

## §27 Sincronización

No entra en P4 como lazo: carrier/timing/frequency/phase recovery con
estado iterativo, update, estabilidad, convergencia, máximo de
iteraciones y failure state quedan UNSUPPORTED (roadmap silent). Los
offsets estáticos de §26 son transforms analíticos sin estado; su
inversión perfecta es identidad testeada (no es un recovery loop).

## §28 Codificación

El roadmap no incluye channel coding en P4: parity/Hamming/block/
convolutional/CRC/Reed-Solomon/LDPC/interleaving quedan UNSUPPORTED.
Para cada código excluido el futuro test hostil registra el rechazo
tipado (no se implementa ni un codificador parcial).

## §29 Codificación y reutilización

Búsqueda en el repo (ver §1 y §10): no existe abstracción de bit,
secuencia binaria ni motor polinómico distinto de los certificados
(`control.poly`, `dsp.Sequence`, `math.*`). P4 NO crea: second bit
abstraction (usa tuplas de int + `Sequence` donde aplique), second
sequence abstraction (REUSE `dsp.Sequence`), second polynomial engine
(REUSE `control.poly` si alguna vez hiciera falta — en P4 no hace
falta). Documentado en §40.

## §30 Invariantes

| ID | Invariante | Método | Tolerancia | Oracle |
|:---|:---|:---|:---|:---|
| P4-I001 | bit/symbol round-trip | map→unmap | exacta | identidad |
| P4-I002 | mapping round-trip | unmap→map | exacta | identidad |
| P4-I003 | constellation normalization | `⟨\|z\|²⟩ = 1` | exacta/≤1e-40 | suma directa |
| P4-I004 | symbol energy | `\|zi\|²` registrado | exacta | cálculo a mano |
| P4-I005 | minimum distance | `dmin` registrado | ≤1e-40 | cálculo a mano |
| P4-I006 | Gray mapping | adyacencia exhaustiva | exacta | combinatoria |
| P4-I007 | mod/demod identity (sin ruido) | mod→demod | exacta | identidad |
| P4-I008 | Eb/Es consistency | `Es = k·Eb` | exacta | definición §11 |
| P4-I009 | SNR consistency | triángulo SNR/Es/Eb/N0 | exacta/≤1e-40 | definición §21 |
| P4-I010 | analytical BER (BPSK/QPSK/BFSK) | fórmula vs caso manual | rel ≤1e-12 | §15/§16/§18 |
| P4-I011 | analytical SER (M-PSK/M-QAM) | APPROX vs referencia | banda documentada | §17 (APPROX) |
| P4-I012 | Nyquist pulse condition | `h(nTs) = δ[n]` | exacta (nodos) | identidad |
| P4-I013 | matched-filter identity | matched ≡ correlator | ≤1e-40 | evaluación |
| P4-I014 | channel determinism | mismo stream → misma salida | exacta | digest |
| P4-I015 | seeded simulation determinism | misma seed → misma secuencia | bytes | digest |
| P4-I016 | serialization round-trip | doc→texto→doc | bytes | digest |
| P4-I017 | replay equivalence | re-ejecución | digest | §31 |
| P4-I018 | digest determinism | triple dump | bytes | §29/§35 |

## §31 Oráculos independientes

Jerarquía: (1) derivación matemática, (2) caso manual, (3) identidad
cerrada, (4) referencia académica citada, (5) motor certificado anterior
designado (P2 DFT/Sequence/sampling, `decimal_exp`, trig/log/sqrt).
Nunca dos funciones de la misma implementación futura como oracle
cruzado. Manuales mínimos: BPSK `Eb/N0 = 0 dB → BER ≈ 0.0786496`,
QPSK cuadrante, `λ`-no-aplica (sin líneas), RC `α = 0 ≡ sinc`,
Nyquist `h(nTs) = δ[n]`, Shannon `SNR = 0 dB → C/B = 1`.

## §32 Numérica

`Decimal` / `DecimalComplex` / `Fraction` / `RationalComplex` según el
caso (disciplina P1/P2/P3). Prohibido en el core nuevo: `float`, `numpy`,
`scipy`, `math` (auditoría §1 + grep/AST en implementación; barrido de
esta fase: 0 `float(`/`numpy`/`scipy`/`import math` en
`control/`+`dsp/`+`rf/`). Sin conversiones indirectas (ni vía `Fraction`
hacia float, ni vía `complex()` nativo).

NEW thin helpers ONLY donde el repo carece demostrablemente de ellos:
(1) `decimal_erfc`/`q_function` sobre `decimal_exp` REUSEd +
`decimal_sqrt` certificado (serie / fracción continua según régimen);
(2) `uniform_stream` por contador SHA256 (§22); (3) `complex_tanh/sinh/
cosh` por el patrón P3 ya certificado (solo si la RRC compleja lo exige;
en caso contrario se reutiliza por valor, sin duplicar). Sin segundo
reductor trigonométrico, sin segundo log, sin segundo sqrt complejo,
sin segundo canonicalizer/digest.

## §33 Precisión

Base **50 dígitos** (precedente P1/P2/P3; misma clase flop compleja,
mismos kernels, tolerancias transferibles verbatim).

| Operación | Precisión | Error esperado | Justificación |
|:---|:---|:---|:---|
| map/unmap, Gray, etiquetas | exacta (int) | 0 | combinatoria |
| constelación/energías/dmin | Decimal-50 | ≤1e-40 | redondeo prec-50 |
| modulación/demodulación ideal | Decimal-50 | exacta/≤1e-40 | álgebra cerrada |
| pulso RC/RRC (incl. límites) | Decimal-50 (Context-80 en-test) | ≤1e-40 (nodos exactos) | L'Hôpital cerrado |
| `erfc`/Q régimen medio | Decimal-50 | rel ≤1e-12 | serie/fracción continua |
| `erfc`/Q colas extremas | Decimal-80 (interna) | banda documentada | underflow Decimal |
| BER mid-range vs manual | Decimal-50 | rel ≤1e-12 | oracle manual 12 dígitos |
| Shannon `log2` | Decimal-50 vía `log10` | ≤1e-40 | kernels certificados |
| simulación MC | estadística + determinista | intervalo documentado | nunca oracle primario |

## §34 Estabilidad numérica

| Riesgo | Detección → Estado → Comportamiento → Garantía |
|:---|:---|
| `exp/log/sqrt/sin/cos` extremos | ingress finito gate → INVALID si no-finito; si no, kernels certificados |
| `erfc`/Q en colas (`Eb/N0 ≫ 1`) | régimen detectado → Decimal-80 interno → banda documentada, nunca 0 silencioso |
| BER/SNR extremos | `N0 ≤ 0` → INVALID; `SNR` enorme → Q-cola con banda; probabilidades clamp testeado `[0,1]` |
| energías cero / amplitudes enormes/diminutas | `Es = 0` → INVALID (constelación degenerada); escalas `1e±30` batería hostil con estados tipados |
| amplitudes `1e±30` | batería `1e-30/1e-15/1/1e15/1e30` → FINITE/INVALID/SINGULAR, nunca crash |
| filtros degenerados (`α < 0`, `α > 1`, `Ts ≤ 0`) | validador → INVALID |
| constelaciones degeneradas (M no potencia de 2, labels duplicados) | validador → INVALID |
| divisiones (`1/N`, `1/sqrt`, `ZL+Z0`-análogo `1−Γ`-no-aplica) | denominador cero → SINGULAR/INVALID por caso, nunca NaN |
| singularidades RC/RRC (`t = 0`, `t = ±Ts/2α`) | rama de límite cerrado → valor exacto, testeado |
| aleatoriedad/seed (`seed < 0`, `seed = None` en MC) | `INVALID_SEED` (precedente F8-M) |
| reproducibilidad | triple-run + digest (§35); divergencia → INCONSISTENT |

## §35 Determinismo

Motor analítico: `same input → same result → same canonical
serialization → same digest` (triple RUN 1/2/3, bytes+digest idénticos).
Simulación: `same seed → same result → same serialization → same digest`
(P4-I015). Sin reloj/UUID/azar del SO/orden de dict/locale/plataforma en
digests; bloques y símbolos en orden de inserción; sin RNG fuera del
stream seeded de §22.

## §36 Serialización

Schema `f8p4-comms/1` (cerrado, versionado): documentos bit/symbol/
constelación/modulación/pulso/canal/métrica/simulación; dumps
deterministas; `Decimal → str()` (nunca `normalize()`, precedente F8-N
D-R1); `DecimalComplex → {re,im}`; `Fraction → str()`; sin NaN/Infinity/
objetos/nombres de clase/código; guard `≤ 64 MiB`. Mecánica de envelope
REUSEd (`canonical_json`/`chain_digest` de `metrology.o5_traceability`) —
sin segundo hash, sin segundo canonicalizer. Tamper → INCONSISTENT en
carga (precedente F8-N/O/P2/P3).

## §37 Replay

Vocabulario REUSEd verbatim: `EQUIVALENT / RESULT_DIFFERS /
VERSION_MISMATCH / SCHEMA_MISMATCH / INVALID_SERIALIZATION` (+ aliases
testeados `VALID` / `RESULT_DIFFERENT`, precedente F8-N/O/P1/P2/P3).
Replay re-evalúa la especificación comms bajo mismo schema+versión y
compara digests; notas/anotaciones nunca afectan digests. Sin sistema
paralelo.

## §38 Seguridad

Prohibido en el core nuevo (grep + AST, AST autoritativo): `eval, exec,
compile, getattr, setattr, open, subprocess, pickle, marshal, importlib,
socket, urllib, numpy, scipy, math` (`re.compile` ≠ builtin `compile()`).
Disciplina frozen-dataclass; constructores validados; solo `random`
permitido: ninguno (el stream es SHA256 propio, §22 — ni siquiera
`random.Random`, para inmunidad a cambios de versión stdlib).
Batería hostil: payloads malformados, schema desconocido, versión
errónea, digest manipulado, NaN/Infinity textuales, oversize, M no
potencia de 2, labels duplicados, `sps ≤ 0`, `α ∉ [0,1]`, `N0 ≤ 0`,
semillas malformadas, entradas gigantes, constelaciones `M > 256`,
estructuras recursivas, schemas corruptos.

## §39 Arquitectura

```text
domain
  ↓
engineering
  ↓
comms/                      NEW (F8-P4, digital-comms math layer)
  ├─ bits.py                Bit/Symbol/Alphabet, map/unmap/pad
  ├─ constellation.py       ids/labels/coords/energy, Gray, dmin
  ├─ modulation.py          BPSK/QPSK/M-PSK/M-QAM/ASK/OOK/FSK + demod rules
  ├─ pulse.py               rectangular/sinc/RC/RRC, Nyquist/ISI
  ├─ channel.py             AWGN + static impairments (analytic)
  ├─ detection.py           threshold/correlator/matched/ML (+LIMITED noncoh)
  ├─ metrics.py             SNR/EbN0/EsN0, BER/SER, Shannon capacity
  ├─ simulation.py          seeded streams + MC runs (deterministic)
  └─ report.py              f8p4-comms/1 docs + digests + replay/compare
  ↓ (depends downward only)
certified: dsp.sequences/sampling/dft (containers + verdicts),
           control.errors (statuses), control.response.decimal_exp,
           math.* (trig/log/sqrt/complex), units,
           metrology.o5_traceability (digest helpers only)
```

Nombres según el esqueleto del mandato con `serialization/replay`
plegados en `report.py` (precedente P1/P2/P3: un módulo envelope).
`comms/` nunca importa `lab/` (N-110), `simulation.py` (mundo float),
`rf/` (sin dependencia funcional), UI/aplicación/infraestructura,
I/O/red. Nada importa `comms/` salvo futuro P5/tests. DAG verificado
por test AST (§42).

Dependencias prohibidas (ciclos): `dsp → comms`, `math → comms`,
`units → comms`, `rf → comms`, `control → comms`.

## §40 No duplicación

Motor normativo único para: sequences (`dsp.Sequence`), FFT/DFT
(`dsp.dft`), sampling/Nyquist/alias (`dsp.sampling`), filters
(disciplina P2; el pulso P4 es analítico, no un segundo FIR engine),
DecimalComplex/units/errors/serialization/replay/digest
(`math`/`units`/`control.errors`/`metrology.o5`). Cada reutilización
queda documentada en §6/§20/§32/§36 con su test de no-duplicación
(marker-grep + AST, estilo P2-030/P3-041).

## §41 Límites de recursos

| Límite | Valor | Razón |
|:---|:---|:---|
| bits por operación | ≤ 65536 | hereda `MAX_SEQUENCE_N` (cota serde/digest O(n)) |
| símbolos por operación | ≤ 65536 | hereda `MAX_SEQUENCE_N` |
| orden de constelación M | ≤ 256 (`k ≤ 8`) | Gray exhaustivo + dmin O(M²) acotados |
| samples/symbol | 1–64 entero | coste lineal, alias honestos |
| muestras totales | ≤ 65536 | coherente con secuencias P2 |
| bits simulados por run MC | ≤ 1 000 000 | coste estadístico acotado, rechazo explícito |
| lóbulos sinc | ≤ 5000 | precedente P2 `MAX_RECON_LOBES` |
| `MAX_SERIALIZED` | 64 MiB | hereda F8-N/P2/P3 (guard DoS) |
| frecuencia/portadora | `f, fc, fs, Rs > 0` finitos, sin cota superior | Decimal exacto, sin banda oculta |

Los presupuestos son rechazos (`INVALID`/`UNSUPPORTED`/`SINGULAR`),
nunca truncamientos silenciosos.

## §42 Test plan

P4-001…P4-040 (IDs estables; la implementación solo extiende con
justificación; nunca reduce). Cada test documenta input/expected/oracle/
tolerancia/failure-meaning.

| ID | Área | Oracle |
|:---|:---|:---|
| P4-001…003 | bits/symbols/map/unmap/pad + round-trips | identidades exactas |
| P4-004…006 | constelaciones (normalización/energía/dmin/Gray) | sumas directas + combinatoria |
| P4-007…009 | BPSK/QPSK mod/demod ideal + `Es = 2Eb` | identidades + §16 |
| P4-010…012 | M-PSK/M-QAM/ASK-OOK/FSK mod/demod ideal | fórmulas cerradas |
| P4-013…014 | energía/potencia/sampling (`sps`, Nyquist, alias) | P2 REUSEd + mano |
| P4-015…016 | pulsos (RC/RRC límites, Nyquist ISI-cero) | límites cerrados |
| P4-017…019 | AWGN (PSD uni/bilateral, `CN(0,N0)`, offsets estáticos) | definiciones §21 |
| P4-020…022 | detección (threshold/correlator/matched≡ML) | identidades P4-I013 |
| P4-023…025 | BER EXACT (BPSK/QPSK/BFSK) vs manuales | `½erfc` 12 dígitos |
| P4-026…027 | SER APPROX (M-PSK/M-QAM) etiquetada | referencia + banda |
| P4-028 | Shannon (`C/B`, límite −1.59 dB) | `log2` certificado |
| P4-029 | codificación/sync/OFDM/MIMO/ecualización → UNSUPPORTED | estados tipados |
| P4-030 | batería hostil (M, labels, sps, α, N0, seeds, oversize, tamper) | estados tipados |
| P4-031 | determinismo triple-run analítico | 1 digest |
| P4-032 | determinismo seeded (misma seed, streams idénticos) | bytes |
| P4-033 | serialización round-trip/tamper/mismatch | 5 estados |
| P4-034 | replay equivalence | digest |
| P4-035 | seguridad AST + grep | 0 banned |
| P4-036 | no-duplicación AST/grep | sin 2.º motores |
| P4-037 | arquitectura DAG | edge tests |
| P4-038 | límites/bench | registrados, sin wall asserts |
| P4-039… | regresión F7-B7,H…P3 | suites verdes |

## §43 Regresión

La futura implementación ejecuta como mínimo:
`F7-B7, F8-H, F8-I, F8-J, F8-K, F8-L, F8-M, F8-N, F8-O, F8-P1, F8-P2,
F8-P3, F8-P4`. Cero regresiones aceptadas; nunca modificar tests
anteriores para ocultar regresiones; `pytest -q` global 0 failed salvo
skips de entorno preexistentes justificados.

## §44 Matriz de riesgos

| Riesgo | Prob. | Impacto | Detección | Mitigación | Test |
|:---|:---:|:---:|:---|:---|:---|
| `Eb/Es` incorrecto | M | A | P4-008/009 | definición §11 + normalización unitaria | P4-007…009 |
| SNR incorrecto (uni vs bilateral) | M | A | P4-017 | convención PSD cerrada §21 | P4-017…019 |
| normalización de constelación | M | A | P4-004 | `⟨\|z\|²⟩ = 1` + invariante | P4-004…006 |
| Gray mapping erróneo | M | M | P4-006 | exhaustivo M ≤ 256 | P4-004…006 |
| convención I/Q (signos, fase) | M | A | P4-007 | §14 congelada | P4-007…012 |
| fase inicial / `φ0` | B | M | P4-010 | `φ0 = 0` congelado | P4-010 |
| ruido (varianza por dimensión) | M | A | P4-017 | `N0/2` por I/Q §21 | P4-017…019 |
| PSD mezclada | M | A | P4-017 | una convención por función | P4-017 |
| BER exacta presentada como aprox y viceversa | M | A | P4-023…027 | etiquetas EXACT/APPROX | P4-023…027 |
| SER aproximada como exacta | M | A | P4-026/027 | APPROX obligatoria §17 | P4-026/027 |
| overflow/underflow Decimal | B | M | P4-030 | ingress finito + exactitud | P4-030 |
| singularidades RC/RRC | B | A | P4-015 | límites cerrados §19 | P4-015/016 |
| aleatoriedad no reproducible | M | A | P4-032 | SHA256-counter §22 | P4-032 |
| seed inválida silenciosa | B | M | P4-030 | `INVALID_SEED` | P4-030 |
| reproducibilidad MC | B | M | P4-032/034 | digest + replay | P4-032…034 |
| dependencia P2 rota/duplicada | B | A | P4-036/037 | allowlist + DAG | P4-036/037 |
| dependencia P3 injustificada | B | A | P4-037 | `comms ↛ rf` AST | P4-037 |
| ciclos arquitectónicos | B | A | P4-037 | edge tests | P4-037 |
| duplicación de infraestructura | B | A | P4-036 | marker-grep | P4-036 |
| scope creep (coding/OFDM/MIMO/sync/link-budget) | M | M | P4-029 | OUT explícito §9 | P4-029/030 |
| regresión H→P3 | B | A | suites + pytest | solo añade paquete | P4-039 |

## §45 Open questions

Resueltas antes del Design Gate (ninguna bloqueante):

1. Alcance exacto de P4 → §5/§7/§8/§9 (fila :211 como evidencia).
2. Modulaciones soportadas → BPSK/QPSK/M-PSK/M-QAM/ASK-OOK/FSK-coherente (§15–§18).
3. Baseband/passband → baseband SUPPORTED, passband LIMITED documental (§14).
4. AWGN → SUPPORTED con PSD cerrada (§21).
5. BER/SER → EXACT/APPROX separadas (§23).
6. Pulse shaping → rectangular/sinc/RC/RRC (§19).
7. Detection → coherente SUPPORTED, no-coherente LIMITED (§25).
8. Coding → UNSUPPORTED (§28).
9. Synchronization → UNSUPPORTED como lazo (§27).
10. Simulation → seeded SHA256-counter (§22).
11. Random seed → `int ≥ 0`, `INVALID_SEED` (precedente F8-M).
12. Normalization → energía media unitaria (§13).
13. `Eb/Es` → `Es = k·Eb` derivado, no asumido (§16/P4-I008).
14. Architecture → `comms/` aguas-abajo, AST-testeada (§39).
15. Serialization → `f8p4-comms/1` REUSEd (§36).

## §46 Deviations

Ninguna respecto al repositorio (fase greenfield sobre motores
certificados; convenciones F8-D4/P3 heredadas verbatim por valor, no
reinterpretadas). Respecto al mandato: replay aliases heredados
(`VALID`/`RESULT_DIFFERENT`); `FSK-no-coherente` y `sinc` quedan LIMITED
(con la fila :211 como paraguas de "Modulaciones"); la única tolerancia
de truncamiento sancionada es la de lóbulos sinc (`§33`, precedente
P2-reconstrucción); `erfc`/Q en Decimal-80 interno para colas es
estrategia numérica declarada, no relajación de tolerancia.

## §47 Certification plan

Implementación futura (fuera de esta fase): `comms/` (9 módulos §39) +
`tests/test_f8p4_comms.py` (P4-001…P4-039+) + extensión AST
(`control↛comms`, `dsp↛comms`, `rf↛comms`, `{mna,ac,lab}↛comms`,
`comms↛{lab,simulation,rf,mna,ac}`) + `GATE-F8P4.md` con evidencia real +
roadmap mínimo (P4 CERTIFIED, P5 NEXT) + commit único + push (nunca
force). Criterio: ecuación + referencia independiente + error
cuantificado + invariante + límites + determinismo + seguridad +
regresión H→P3 + pytest global 0 failed.

## §48 Verdict

Las quince preguntas del mandato (§45) quedan respondidas en
§5/§7–§9/§11–§23/§13/§22/§39/§36. Alcance literal del roadmap (`:211`,
deps `F8-P2, F8-P3`), matemática cerrada (mapas Gray, Möbius-no-aplica,
QPSK/BPSK exactos, RC/RRC con límites, Shannon vía `log10`),
convenciones cerradas (I/Q, `φ0 = 0`, PSD, peak, MSB-first),
arquitectura cerrada, tolerancias justificadas, sin preguntas críticas
abiertas.

F8-P4 DESIGN READY
