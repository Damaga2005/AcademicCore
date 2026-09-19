# GATE-F8K: Certification Report — Additional Semiconductors (MOSFET, JFET, Diode Kinds)

> **Gate**: F8-K
> **Design reference**: `docs/gates/GATE-F8K-DESIGN.md` (verdict `F8-K DESIGN READY`)
> **Preconditions**: closed in commit `a900d99` (roadmap F8-J certified; F8-J benchmark diagnostic-only)
> **Devices**: MOSFET Level 1 / Shichman-Hodges (`M`), JFET square-law (`J`),
>   Zener / LED / Schottky / Photodiode (`D` + `kind`)
> **Precision**: strict `Decimal`-native (prec 50), zero `float` in the domain solver
> **External oracle**: ngspice 47 (`ngspice_con.exe`)
> **Final Verdict**: **`F8-K CERTIFIED`**

---

## 1. Header / Scope

F8-K extends the certified nonlinear DC operating-point solver (`solve_nonlinear_dc`,
Newton–Raphson with strict-decrease bisection backtracking, frozen Q1 policy) from
two-terminal Shockley diodes (F8-H) and three-terminal Ebers-Moll BJTs (F8-I) to:

| Device | Type | Pins | Model |
|:---|:---:|:---:|:---|
| MOSFET Level 1 | `M` | D, G, S, B (bulk explicit) | Shichman-Hodges + body effect |
| JFET | `J` | D, G, S | square-law, NCHAN/PCHAN |
| Zener | `D` + `kind=ZENER` | A, K | Shockley forward + exponential reverse breakdown |
| LED | `D` + `kind=LED` | A, K | Shockley, application domain |
| Schottky | `D` + `kind=SCHOTTKY` | A, K | Shockley, application domain |
| Photodiode | `D` + `kind=PHOTO` | A, K | Shockley − Iph |

DC operating point only. No transient, no junction capacitances, no noise/temperature/
BSIM/RF, no optical dynamics, no series resistance Rs (deferred by design).

## 2. Implemented models (mathematics)

Notation: `Decimal` under `make_context()` (prec 50). `exp = ctx.exp`.
Overflow → `Infinity` → caller maps to `DIVERGED` (evaluation cause); never clipped.

### 2.1 MOSFET (NMOS shown; PMOS mirrors signs, `s = ±1`)

```text
VGS = s·(VG−VS),  VDS = s·(VD−VS),  VSB = s·(VS−VB)
Vth = Vto + Gamma·(sqrt(max(Phi+VSB,0)) − sqrt(Phi))   [Gamma=0 → Vth=Vto]
Vov = VGS − Vth
cutoff:     Vov ≤ 0            → ID = 0
triode:     Vov > 0, VDS < Vov → ID = Kp·(Vov·VDS − VDS²/2)·(1+Lambda·VDS)
saturation: Vov > 0, VDS ≥ Vov → ID = (Kp/2)·Vov²·(1+Lambda·VDS)
```

Terminal currents (entering): `(+ID, 0, −ID, 0)` on (D, G, S, B).
Derivatives: `gm = ∂ID/∂VGS`, `gds = ∂ID/∂VDS` per branch (exact rational
forms, no `exp`); `gmb = dID/dVB = gm·Gamma/(2·sqrt(Phi+VSB))` (0 when
`Gamma = 0` or `Phi+VSB ≤ 0`). 4×4 Jacobian: drain row from the chain rule,
source row = −drain row (KCL), gate/bulk rows identically zero; columns sum
to zero (reference invariance). Verified against central finite differences
(`< 1E-4`) and column/row-sum identities (`< 1E-18`).

### 2.2 JFET (NCHAN shown; PCHAN mirrors signs)

```text
cutoff:     VGS ≤ −Vp               → ID = 0
triode:     VGS > −Vp, VDS < VGS+Vp → ID = Idss·(2·(1+VGS/Vp)·(VDS/Vp) − (VDS/Vp)²)·(1+Lambda·VDS)
saturation: VGS > −Vp, VDS ≥ VGS+Vp → ID = Idss·(1+VGS/Vp)²·(1+Lambda·VDS)
```

Terminal currents `(+ID, 0, −ID)` on (D, G, S); analytic 3×3 Jacobian with the
same stamp pattern as the BJT. No `exp` anywhere. Cutoff boundary is
C0-continuous by construction (near `VGS = −Vp` any macroscopic VDS falls in
saturation where `ID → 0`).

### 2.3 Diode kinds (all reuse letter `D`, discriminated by required `kind`)

- **RECT**: delegates to F8-H `shockley_current`/`shockley_conductance` bit-for-bit.
- **Zener**: forward = Shockley (`Vd ≥ 0`); reverse (`Vd < 0`):
  `I = Is·(exp(Vd/(n·Vt))−1) − Iz·(exp(−(Vd+Vz)/(nz·Vt)) − exp(−Vz/(nz·Vt)))`,
  `g = Is/(n·Vt)·exp(Vd/(n·Vt)) + Iz/(nz·Vt)·exp(−(Vd+Vz)/(nz·Vt))`.
  C0-exact at `Vd = 0`, C1 up to the negligible `exp(−Vz/(nz·Vt))` term;
  dynamic resistance in breakdown is emergent (`1/g`).
- **LED / Schottky**: pure Shockley with kind tag (positivity/dimension
  validation identical to RECT — no arbitrary magic ranges).
- **Photodiode**: `I = Shockley(Vd) − Iph` (`Iph ≥ 0`, `0` = exact darkness);
  `g` = Shockley conductance (Iph constant).

### 2.4 DESIGN DEVIATION-01 (Zener reverse branch)

The design draft (`−Is − Iz·(exp(−(Vd+Vz)/(nz·Vt)) − 1)`) jumps by ~Iz at
`Vd = 0` (reverse limit `−Is + Iz` vs forward exactly `0`). The implemented
form above keeps identical parameters, regions, breakdown growth and emergent
`ro`, while being exactly continuous at the boundary — strictly easier for
the certified backtracking to traverse. Impact: none on other devices; Zener
tests pin continuity (`I(0) = 0` both sides, slope match `< 1E-6` relative).

### 2.5 SOLVER-EXT-01 (exact-flat-region standstill acceptance)

Piecewise devices make the residual EXACTLY zero in flat regions (MOSFET/JFET
cutoff: `ID = 0`, `J = 0`), after which strict decrease from exactly 0 is
impossible and the solver misreported stagnation (`DIVERGED` on valid cutoff
circuits — reproduced before the fix). The backtracking now additionally
accepts a non-increasing trial iff it already satisfies the certified block
tolerances. Unchanged: Q1 tolerances, the convergence certificate
(`res_ok AND step_ok`), strict decrease for every state-changing step, the
iteration budget. D/Q-only paths are unaffected (exp branches never hit exact
zero). Cause demonstrated, F8-H/I/J regression re-measured identical
(§9), mathematically justified (acceptance at tolerance cannot oscillate
beyond the bounded budget).

## 3. Parameter contracts

No silent defaults anywhere. Exact per-kind sets:
`M: {polarity∈{NMOS,PMOS}, Kp(A/V²)>0, Vto(V)>0, Lambda(1/V)≥0, Phi(V)≥0,
Gamma(descriptive sqrt(V) magnitude, dimensionless)≥0}`;
`J: {polarity∈{NCHAN,PCHAN}, Idss(A)>0, Vp(V)>0, Lambda(1/V)≥0}`;
`D+kind`: RECT/LED/SCHOTTKY `{kind,Is,n,Vt}`; ZENER `+{Vz,nz,Iz}>0`;
PHOTO `+{Iph≥0}`. Wrong type/value/dimension/non-finite/domain violations →
deterministic `InvalidCircuitError` (at validation) / `NonlinearStatus.INVALID`
(at solve). `M`/`J`/D-kind take no `value` (None, BJT precedent).
Gamma note: the unit registry only supports integer SI exponent tuples, so
√V has no exact dimension entry; the dimensionless magnitude is validated
(the design explicitly deferred this to implementation).

## 4. MNA integration

- `COMPONENT_PINS`: `M→(D,G,S,B)`, `J→(D,G,S)`; `_REF_RE` accepts `M`/`J`.
- Linear path untouched: `SUPPORTED_TYPES = {R,V,I,E,G,H,F,O,T}`; `build_mna_problem`
  gains `allow_mosfets/allow_jfets/allow_diode_variants` (default `False` →
  `UnsupportedElementError`, D/Q precedent). M/J/D-kind carry NO linear stamp.
- `solve_nonlinear_dc` enables all flags; legacy `D` (no `kind`) flows through
  the F8-H path bit-for-bit. No new MNA unknowns (companion stamps only).
- H/F with `control_ref` to M/J rejected (`InvalidCircuitError`, D/Q precedent);
  D-kind inherits the D rejection. Thevenin/port set unchanged (M/J auto-rejected).
- Reporting: `M1:D/G/S/B`, `J1:D/G/S` terminal branch currents; absorbed-power
  convention; KCL/KVL/Tellegen checks cover new legs. Provenance records per-ref
  model cards + params; topology/solver SHA-256 digests extend deterministically.

## 5. Newton integration

Frozen Q1 policy (RTOL=1E-9, ATOL=1E-12, STOL=1E-12, MAX_ITER=50,
MAX_BACKTRACK=10, zero-vector init) + SOLVER-EXT-01 (§2.5). Status mapping
unchanged: overflow/non-finite → `DIVERGED`; singular Jacobian →honest
`SINGULAR_JACOBIAN`; bad params → `INVALID`; reactive L/C → `UNSUPPORTED`.

## 6. Small-signal contract (F8-J extension, no new AC engine)

`solve_small_signal_ac` accepts `M`/`J` (DC dispatch recognizes them as
nonlinear); new `MOSFETSmallSignalParams {region, vgs0, vds0, id0, gm, gds,
gmb, jacobian4x4}` and `JFETSmallSignalParams {…, gm, gds, jacobian3x3}`;
D-kind reuses the diode conductance path with a `kind` tag. Stamps: full
analytic Jacobian blocks as `DecimalComplex`. Verified: AC `SOLVED` with
`kcl < 1E-12` for M/J/Zener stages; exposed trio equals the DC conductance
functions exactly; 3-run digest identical. No capacitances, no AC dynamics.

## 7. Numerical guarantees

- `Decimal`-native end to end in `mna/` + `ac/small_signal.py`; zero `float(`
  (grep) and zero float literals (AST scan) in all touched/new engine files.
- `math.*`/`numpy`/`scipy`: absent from the domain solver path.
- Exponentials only in diode-kind branches with the F8-H overflow contract;
  MOSFET/JFET are `exp`-free (products/quotients/sqrt only, guarded domains).
- Determinism: sorted refs, zero-vector init, SHA-256 digests; 5-repeat
  identical `to_dict` + iterations; insertion-order invariance; AC digest
  stability — all tested.

## 8. Security

`git grep` over `src/academic_core/domain/engineering`: `eval(` 0, `exec(` 0,
`__import__` 0, `subprocess` 0, `os.system` 0; `compile(` only `re.compile`
(3 pre-existing regex sites). AST suite in `test_f8k_*` additionally forbids
`globals/locals/os/sys/importlib/socket/requests` imports and
`system/popen/run` attribute calls in all 10 touched/new engine files. Models
are purely mathematical and deterministic.

## 9. Tests (110 new, all passing)

`tests/test_f8k_additional_semiconductors.py` — 110 tests:
validation M/J/D-kind (34), MOSFET physics incl. FD-derivative and symmetry
checks (11), JFET physics (9), D-kind physics incl. Zener continuity (9),
biased DC circuits per device/region (10), mixed `D+M/D+J/M+Q/J+Q/M+J/M+Zener/
Q+D` (7), no-convergence paths (6), boundary sweeps incl. Zener clamp and
photo dark≡legacy identity (5), AC contract (4), determinism (3), AST+float
scans (2), diagnostic benchmarks (3), ngspice/external oracles (3).

| Suite | Passed | Failed | Skipped | Duration |
|:---|:---:|:---:|:---:|:---|
| test_f8k_additional_semiconductors.py | 110 | 0 | 0 | ~7 min (incl. N=64 ladders + ngspice) |
| test_f8h_nonlinear_dc.py | 69 | 0 | 0 | 81–100 s |
| test_f8i_bjt.py + test_f8i_nonlinear_bjt.py | 74 | 0 | 0 | 38–91 s |
| test_f8j_small_signal_ac.py | 29 | 0 | 0 | 147–572 s (diagnostic timing) |
| Batch eng-core/F8-A..C/generality | 271 | 0 | 0 | 121 s |
| Batch F8-D/E/F/G | 834 | 0 (+2 pre-existing deselected, 1 load-flake green in isolation) | 0 | ~48 min |
| Batch F7 | 314 | 0 | 0 | 17 s |
| Batch rest (F9/misc/UI) | 225 | 0 | 2 | 74 s |

Global: ~1926 passed, 2 skipped (pre-existing skips), 0 F8-K-related failures.

## 10. Regression (post-implementation)

F8-H (69), F8-I (74), F8-J (29, incl. rewritten J19 probing unknown type `X`
since `M` is now supported — design-mandated test update) all green with the
new code. Full-suite batches green except: (a) 2 pre-existing F8-D4 trig-
precision asserts (`pf == 1` at 1E-28, metamorphic at 1E-28 — reproduced on the
clean `a900d99` tree via stash, unrelated to F8-K); (b) 2 load-flaky perf-
threshold tests (`test_performance_split_scales`, `test_perf_f8g_scales`)
that pass in isolation (509 s / 24 s) and fail only under batch machine load —
same hardware-dependence class already closed for F8-J in `a900d99`.

## 11. Benchmarks (diagnostic, no time asserts)

N-stage ladders, Python 3.14.6 / Windows-11:
MOSFET `{1: 0.008 s/3it, 10: 0.96 s/8it, 32: 17.7 s/10it, 64: 119.9 s/10it}`;
JFET `{1: 0.019 s, 10: 0.74 s, 32: 9.4 s, 64: 73.5 s}`;
mixed M+J+D `0.159 s/8it`.
Newton counts grow mildly with N (3→10, vs BJT constant 7) — expected: stacked
stages span multiple regions; convergence remains robust.

## 12. External validation (ngspice 47)

- NMOS bias (Level 1, `kp=200u vto=1 lambda=0.02 phi=0.6 gamma=0.5`,
  R=2k, Vdd=5, Vgs=3): AcademicCore `Vs = 4.133858 V` vs ngspice `4.133858 V`,
  relative error **6.5E-8** (limit 1E-4).
- Zener regulator (`bv=5.1 ibv=1e-3` vs F8-K piecewise-exp branch):
  `5.140865 V` vs `5.140892 V` (Δ27 µV; knee formulations differ by convention,
  documented tolerance 0.1 V academic / 0.4 V ngspice).
- JFET triode closed-form oracle satisfied to `< 1E-9` (self-consistency +
  region predicate).

## 13. Known limitations (deliberate, normative)

Rs deferred (implicit equation, design-mandated); no gate-junction forward
diode in JFET/MOS (IG = 0 by scope); no junction capacitances/transient/noise/
temperature/BSIM; Gamma carried dimensionless (√V magnitude); netlist
`engcircuit/6.0` still carries connectivity only (parameters via
`Component.parameters`, F8-H Q3 precedent); PMOS/PCHAN via sign-mirror of the
same scalars (tested exact).

## 14. Findings

- CRITICAL: none. HIGH: none open (SOLVER-EXT-01 and DEVIATION-01 documented
  above with cause/regression/justification).
- MEDIUM: Newton iteration count grows with N on multi-region ladders
  (bounded, converges; diagnostic only).
- LOW: `test_f8j` J19 rewritten for the supported-`M` premise (design-mandated).
- INFO: pre-existing F8-D4 trig asserts (1E-28) and load-flaky perf thresholds
  reproduced on the clean tree; untouched by F8-K, reported for a future
  precision/benchmark policy pass.

## 15. Definition of Done

Models, equations, regions, analytic derivatives and boundaries implemented
and verified (§2–3, 110 tests); solver/MNA/backtracking coherent with frozen
Q1 + documented EXT-01 (§4–5); Decimal-native, overflow-safe, deterministic
(§7); security clean (§8); F8-H/I/J + batched global regression green (§9–10);
diagnostic benchmarks + ngspice correlation recorded (§11–12); gate filed
(this document). No `Rs`, no new unknowns, no relaxed tolerances, no pushes.

## 16. Gate Sign-Off & Verdict

| Criterion | Requirement | Observed | Status |
|:---|:---|:---:|:---:|
| Modelos | M, J, Zener, LED, Schottky, Photodiode integrados | 6/6 + dispatch/pinouts/validación | CERTIFIED |
| Matemática | Ecuaciones, regiones, derivadas, boundaries | Analíticas + FD + simetría + continuidad | CERTIFIED |
| Solver | MNA, Newton, Jacobiano, backtracking, errores | Q1 intacta; SINGULAR/DIVERGED/INVALID honestos | CERTIFIED |
| Numérico | Decimal-native, sin float, overflow, determinismo | grep+AST+5×repeat+digests | CERTIFIED |
| Seguridad | 0 dynamic exec/subprocess/red | grep + AST suite | CERTIFIED |
| Compatibilidad | F8-H/I/J + global verdes | 143+29+batches; solo pre-existentes ajenos | CERTIFIED |
| Validación | unit/circuit/mixed/boundary/bench/externa | 110 tests + ngspice 6.5E-8 | CERTIFIED |

**Final Verdict**: **`F8-K CERTIFIED`**
