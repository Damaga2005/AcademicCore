# F8-P5 Certification Gate

## Baseline

- Repository `Damaga2005/AcademicCore`, branch `main`.
- Design baseline `58ca03a` (`docs(engineering): design gate F8-P5
  satcom synthesis`, verdict `F8-P5 DESIGN READY`), itself built on
  `2b7e017` (`feat(engineering): certify F8-P4 digital communications`).
- Preconditions verified at implementation start: `HEAD = 58ca03a`,
  `origin/main = 2b7e017`, branch `main`, working tree clean, no foreign
  changes (no `reset`/`clean`/`restore`/`rebase`/`merge`/force-push used
  at any point). `HEAD != origin/main` is expected: the design gate is
  deliberately local until this certification push.

## Implementation commits

Single certification commit (no intermediate pushes):

- `feat(engineering): certify F8-P5 satcom synthesis` — `satcom/`
  (9 modules), `tests/test_f8p5_satcom.py`, `+70/-0` architecture-test
  extension, `GATE-F8P5.md`, minimal roadmap update (P5 CERTIFIED).

## Supported scope

Link-budget integrator per roadmap `:212` (deps F8-P1..P4): exact SI
constants (`c`, `k`), wavelength, EIRP (linear/dB), FSPL (linear/dB
identity), Friis received power, ideal-aperture antennas
(G/Ae/η, dBi/dBd, beamwidth-APPROX), thermal noise (`kTB`, `N0`,
single-Tsys/Friis-cascade/Tant-input), `G/T`, `C/N0`, `C/N`
(single-B), `Eb/N0` bridge, P4 BER/SER/Shannon reuse (kinds
propagated), link margin, 1-leg/2-leg budgets, transparent linear
transponder, bent-pipe reciprocal combination, closed inverses
(required-EIRP, modem/Shannon max-Rb, BER→Eb/N0 bisection on EXACT
curves, min-Ptx bisection ≤ 200), `f8p5-satcom/1` serialization +
replay. Budgets: legs ≤ 2, losses ≤ 16, Friis ≤ 8 stages, antennas ≤ 2
per leg, Ptx ≤ 1e6 W, magnitudes ≤ 1e30, payload ≤ 64 MiB.

## Limited scope

Atmospheric/rain/polarization/pointing/implementation/misc/feed losses
as explicit dB inputs (allowlisted ledger — never physical models);
Tant as explicit input; beamwidth as labelled APPROXIMATION;
non-coherent/OOK-style concerns stay in P4 (untouched).

## Unsupported scope

Kept out with typed rejections: orbits/orbital propagation/slant-range
geometry, full-wave EM/patterns, rain/atmospheric/fading models,
coding/FEC gain, regenerative transponders, saturation/nonlinearity,
OFDM/MIMO/SDR/ADC/quantization, availability prediction, generic
optimizer, sync loops, plots/UI/hardware. Verified absent by
namespace audit (`test_p5020`) and hostile ledger tests (`test_p5030`).

## API implemented

| File | LOC | Role |
|:---|---:|:---|
| `satcom/__init__.py` | 173 | Public surface (`ENGINE_VERSION = "f8p5-satcom/1"`) |
| `satcom/constants.py` | 44 | Exact `c`, `k`, `λ = c/f`, magnitude guard |
| `satcom/losses.py` | 69 | Allowlisted loss ledger (16 max), exact sum |
| `satcom/antennas.py` | 133 | G/Ae/η identities, dBi/dBd, beamwidth-APPROX, XOR gate |
| `satcom/noise.py` | 91 | `kTB`/`N0`, Friis cascade (8 max), `G/T` |
| `satcom/metrics.py` | 156 | DbValue label algebra, dB conversions, Shannon C/N |
| `satcom/link.py` | 228 | Leg model, EIRP/FSPL/Pr/G-T/C-N0/C-N/Eb-N0, P3 feed reuse |
| `satcom/synthesis.py` | 277 | Forward/bent-pipe/margin + 4 closed inverses + bisections |
| `satcom/report.py` | 167 | `f8p5-satcom/1` docs + digests (REUSEd) + replay/compare |
| `tests/test_f8p5_satcom.py` | 555 | 44 tests, P5-001…P5-044 |
| `tests/test_architecture.py` | +70 | `test_satcom_layer_direction` (extends, never weakens) |

Total new production code: 1338 LOC across 9 modules. No new error
module (REUSEd `ControlStatus`/`ControlError`). No new digest/
canonical-JSON engine (REUSEd `metrology.o5_traceability`). No new
log/exp/sqrt/trig/complex/BER/Shannon engine (REUSEd `math.*`,
`control.response.decimal_exp`, `comms.metrics`, `rf.margins`).

## Units

Hz/W/m/s via `units.Quantity`-compatible Decimal boundaries (same
ingress discipline as P4); temperature as Decimal + K label
(KELVIN dimension pending the sanctioned additive units extension —
no units.py edit in this phase); bit/s ≡ Hz dimensionally with
distinct label (P4 `bit_rate` precedent); full dB family as labels
(dB/dBW/dBm/dBi/dBd/dB-K/dBHz/dBK) with reference table and rejection
matrix (P5-I019). Reference planes P0..P4 fixed in `link.py`
(`G/T` at LNA input; feed loss inside `G/T`, never double-counted).

## dB policy

`10·log10` power / `20·log10` amplitude via REUSEd P4 kernels;
`dBm = dBW + 30` exact; `dBi = dBd + 2.15` fixed dipole reference;
`k = −228.599 dB(W/K/Hz)`; power±gain→power, same−same→dB,
everything else INVALID (`test_p5031` matrix, 5 rejections pinned).

## Numerical policy

Decimal-50 base at explicit contexts; Decimal-80 inherited inside
REUSEd P4 erfc paths (untouched); `x > 40 → 0` underflow rule
inherited with P4; no `float/numpy/scipy/math` in `satcom/` (AST +
substring audit, §Security); bare Decimal ops survive only where
exact (small-int bookkeeping) or inside tests with 1e-9-class
headroom — audited during implementation (three 1e-40 tolerances
were widened to CTX-exact comparisons after catching 28-digit
ambient-rounding in test-side arithmetic, never in `src/`).

## Reference cases

All gate §29 pins reproduce (tolerances per test):

| Caso | Esperado | Medido |
|:---|:---|:---|
| λ @12 GHz | 0.0249827 m | 0.0249827048… |
| FSPL 35786 km/12 GHz | 205.106 dB | 205.10567129… |
| EIRP 100 W/40 dBi/1 dB | 59.0 dBW | 59 exact |
| kTB 290 K/1 MHz | −143.975 dBW | −143.975187… |
| N0 290 K | −203.975 dBW/Hz | −203.975187… |
| G/T 40 dBi/200 K | 16.990 dB/K | 16.98970004… |
| C/N0 chain | 99.483 dBHz | 99.48319592… |
| Eb/N0 Rb = 10 Mb/s | 29.483 dB | 29.48319592… |
| Dish 1.2 m/η = 0.6/12 GHz | 41.355 dBi | 41.35534574… |
| Chain `59 − 205.106 + 228.599 + 16.990` | 99.483 | ✓ to 1e-3 |

## Test counts

`tests/test_f8p5_satcom.py`: **44 tests, 44 PASS** (P5-001…P5-044:
constants/units/dB/wavelength/EIRP/FSPL/antennas/noise/G-T/C-N0/C-N/
Eb-N0/P4-integration/Shannon/margin/budget/2-leg/reciprocal/
transponder/inverses/bisection/serialization/replay/determinism/
security/architecture). Types: UNIT, ANALYTICAL, NUMERICAL, PROPERTY,
BOUNDARY, ERROR, SECURITY, DETERMINISM, SERIALIZATION, REGRESSION,
PERFORMANCE (recorded, no wall-clock asserts).

## Regression results

| Suite | Result |
|:---|:---|
| F8-P5 new (`test_f8p5_satcom.py`) | 44 passed |
| `test_architecture.py` (12 existing + 1 new) | 13 passed |
| F7-B7 (`test_f7b7_gum.py`) | passed |
| F8-H (`test_f8h_nonlinear_dc.py`) | passed |
| F8-I (`test_f8i_bjt.py`, `test_f8i_nonlinear_bjt.py`) | passed |
| F8-J (`test_f8j_small_signal_ac.py`) | passed |
| F8-K (`test_f8k_additional_semiconductors.py`) | passed |
| F8-L (`test_f8l_transient.py`) | passed |
| F8-M (`test_f8m_analysis.py`) | passed |
| F8-N (`test_f8n_lab*.py`, 5 files) | passed (meta `test_n108` deselected in-block; passed standalone in the F8-P4 session; nothing since touches F8-N) |
| F8-O (`test_f8o_metrology.py`) | passed |
| F8-P1 (`test_f8p1_control.py`) | passed |
| F8-P2 (`test_f8p2_dsp.py`) | passed |
| F8-P3 (`test_f8p3_rf.py`) | passed |
| F8-P4 (`test_f8p4_comms.py`) | passed |

Explicit regression commands (all suites above run in blocks) exit 0;
**no new skip was introduced** by F8-P5. P3/P4 reuse bridges
(`test_p5041_feed_mismatch_p3_reuse`, `test_p5042_p4_reuse_bridge`)
exercise live P3/P4 functions. No certified file modified except the
additive architecture test (+70/−0).

## Security results

AST audit (`test_p5037`) over every `satcom/*.py`: 0 banned calls
(`eval, exec, open, getattr, setattr, compile, __import__` — one real
`getattr` in `BudgetResult.__post_init__` was found by the test and
rewritten to explicit field tuples before certification), 0 banned
top-level imports (incl. `math/numpy/scipy/re/random`), 0 float
literals, 0 `float(` substrings. Frozen-dataclass discipline;
hostile battery (`test_p5033`: magnitudes, NaN/Infinity, oversize,
tamper, schema-mismatch) all typed.

## Architecture results

`satcom → {rf.margins (read-only), comms.metrics/bits, control.errors,
control.response.decimal_exp, math.*, units, metrology.o5, stdlib
decimal/dataclasses/json}` only; `control/math/dsp/rf/comms/units ↛
satcom`; `{mna,ac,lab} ↛ satcom`; `satcom ↛ {lab,mna,ac,dsp (any),
rf∖margins, comms∖{metrics,bits}, simulation, app, UI/FS/network}` —
enforced by `test_satcom_layer_direction` (AST) + in-suite
`test_p5039`. DAG acyclic; no second Sequence/FFT/log/exp/Q/BER/
Shannon/digest/serializer/replay/errors/units engine
(`test_p5038` marker grep + REUSE imports).

## Serialization/replay results

`f8p5-satcom/1`: round-trip/tamper/mismatch (5 states +
`VALID`/`RESULT_DIFFERENT` aliases), replay intact/tampered/version,
deterministic triple-run single digest (`test_p5034/035/036`).
`≤ 64 MiB` guard; `Decimal→str()` (never `normalize()`); no
NaN/Infinity/objects.

## Determinism

Triple forward-budget run → byte-identical serialization, one digest;
bisections deterministic (bounded, bracket-checked); no RNG/clock/
UUID/dict-order/locale anywhere in `satcom/` (AST-confirmed).

## Known limitations

Inherited: 50-digit working precision and tolerance precedents
(P1–P4). New and documented: environment losses are caller-supplied
inputs (no physics); beamwidth is APPROXIMATION; KELVIN awaits the
sanctioned additive units extension (temperatures travel as
Decimal+K-label until then); required-Eb/N0 bisection runs on EXACT
P4 curves only (APPROX curves forward-only); margin is not
availability; forward budget at prec-50 is milliseconds-scale
(recorded, no wall asserts).

## Deviations

- **D-R1 (implementation hygiene, no math changed)**: one `getattr`
  in `BudgetResult.__post_init__` flagged by the mandatory AST scan
  and rewritten as explicit field tuples before certification.
- **D-R2 (label semantics, gate-consistent)**: `C/N` and `Eb/N0`
  return label `"dB"` (bandwidth/rate normalization strips Hz by
  documented plane semantics) instead of inheriting `"dBHz"` from
  the generic `x−dB→x` rule — the gate (§11/§13) defines both as dB.
- **Replay vocabulary**: canonical `EQUIVALENT`/`RESULT_DIFFERS`;
  `VALID`/`RESULT_DIFFERENT` tested aliases (F8-N/O/P1-P4 precedent).

## Final verdict

F8-P5 CERTIFIED
