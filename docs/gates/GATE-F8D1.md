# Quality Gate: F8-D1 — Complex Numeric Foundation

- **Phase**: F8-D1 (first step of F8-D; spec: `GATE-F8D.md`, frozen F8-D-A).
- **Scope**: pure complex-number infrastructure ONLY. No MNA AC, no R/L/C AC,
  no AC sources, no OperatingPoint, no solver, no KCL/KVL AC, no Tellegen,
  no Thevenin/Norton AC, no ngspice AC, no sweep/Bode, no UI, no persistence.
- **Package**: `src/academic_core/domain/engineering/math/`
  (`__init__.py`, `rational.py`, `decimal_complex.py`, `trig.py`).
- **Tests**: `tests/test_f8d1_complex.py` (48 tests).
- **Status**: implemented, self-verified, uncommitted (no commit/push by rule).

---

## 1. RationalComplex — exact algebraic result

`RationalComplex(re: Fraction, im: Fraction)` is an exact Gaussian rational:
every `+ - * /`, unary `-`, `conjugate`, and `squared_modulus` is computed in
`fractions.Fraction` with zero rounding. The type is a frozen dataclass
(immutable, hashable, deterministic), accepts `int`/`Fraction` at construction
and in mixed operations, and rejects `float`/`Decimal`/`complex`/`str`/`bool`
with `TypeError`.

Exact results this type owns: `squared_modulus -> Fraction`
(`|z|^2 = re^2 + im^2`), conjugation identities, distributivity,
associativity, commutativity — all verified exactly, no tolerances.

What it does NOT own: `modulus`, `phase`, `sqrt`. `|z| = sqrt(re^2+im^2)` is
generally irrational and can never inhabit `Fraction`, so
`RationalComplex.modulus -> Decimal` is an explicitly approximate value
computed under the working context. There is intentionally no
`RationalComplex.sqrt`: irrational roots do not live in Q(j).

## 2. DecimalComplex — high-precision numerical approximation

`DecimalComplex(re: Decimal, im: Decimal)` runs every operation through an
explicit `decimal.Context` with `WORKING_PRECISION = 50`. The ambient global
context is never read for rounding and never mutated — not even for unary
negation (plain `-Decimal` would apply the global context, so negation uses
`ctx.minus`). Construction accepts `Decimal`/`int` only; `float`, `complex`,
`Fraction`, `str` are rejected at the boundary.

50 digits is a *working precision*, not a claim of 50 correct mathematical
digits: series truncation (arctan/Taylor with 15 guard digits) and
per-operation rounding make every result an approximation. `pi`, `sin`, `cos`,
`atan2` are implemented in pure `Decimal` (Machin identity, range-reduced
Taylor series) — no `math`/`cmath`/`float` constant is embedded anywhere; the
documented source of pi is `16*arctan(1/5) - 4*arctan(1/239)`.

## 3. Exactness boundary

| side | owns | never claims |
| :--- | :--- | :--- |
| `RationalComplex` | exact `+ - * /`, `conj`, `squared_modulus -> Fraction`, exact `==`, exact zero | roots, phases, transcendental values |
| `DecimalComplex` | 50-digit `+ - * /`, `modulus`, `sqrt` (principal branch, `sqrt(-1)=+j`), `phase`, polar construction | exactness of anything |

`Fraction(decimal_value)` as "recovered exactness" does not exist in this
package and must never be introduced. `Decimal -> Rational` conversion has no
API — not even a debug hook returning `RationalComplex` (a debug view would
return plain `Decimal` tuples, never an exact object).

## 4. Promotion rules

- Allowed: `RationalComplex -> DecimalComplex` via
  `RationalComplex.to_decimal()` / `DecimalComplex.from_rational()`, each
  component rounded once under the working context (1/3 becomes its 50-digit
  approximation; that rounding IS the boundary).
- Mixed arithmetic (`Rational + Decimal`, `Rational * Decimal`,
  `Rational / Decimal`, both operand orders) promotes the exact side first;
  the result is always `DecimalComplex`. `exact + approximate = approximate`,
  never a silent exact result.
- Mixed comparisons across the boundary are `False` by design
  (`RationalComplex(1,0) != DecimalComplex(1,0)` as `==`), forcing explicit
  promotion instead of silent mixing.
- Equality with real scalars is representation-exact on both sides
  (`z == 1` iff `im == 0` and `re == 1`); hashing follows the numeric tower
  so `z == k` implies `hash(z) == hash(k)`.

## 5. Zero semantics

- `RationalComplex.is_zero_exact()`: literally `re == 0 and im == 0`. Division
  by an exactly-zero denominator raises `ZeroDivisionError`; no epsilon policy
  exists here — a nonzero denominator, however small, divides normally.
- `DecimalComplex.__eq__` is representation-exact:
  `DecimalComplex(1e-30, 0) != DecimalComplex(0, 0)`.
- `DecimalComplex.is_zero(tolerance)`: the tolerance is a REQUIRED `Decimal`
  argument, so no threshold can hide inside `__eq__`. Solver-grade thresholds
  (`tau_sing`, `tau_unc`, `tau_tol` from F8-D-A) are deliberately NOT imported
  here; the future solver layer owns them.
- Division distinguishes exactly-zero denominators (`ZeroDivisionError`) from
  merely small ones (computed normally; singularity policy belongs to F8-D2/D3).

## 6. Modulus semantics

- `RationalComplex.squared_modulus -> Fraction` (exact);
  `RationalComplex.modulus -> Decimal` (explicitly approximate; single shared
  implementation `decimal_modulus_of_fractions`).
- `DecimalComplex.squared_modulus` / `modulus` under the working context
  (controlled, documented precision).
- Identity `|z|^2 = z * conj(z)` verified exactly (rational side) and within
  stated absolute/relative tolerances (decimal side).

## 7. Phase semantics

`DecimalComplex.phase()` returns radians in (-pi, pi] as an explicitly
approximate `Decimal`. `phase(j)` is conceptually pi/2; the returned value is
its 50-digit approximation and no exactness is claimed. `phase(0+0j)` returns
`Decimal(0)` by numerical convention (undefined; no physical meaning attached).
`complex_from_polar(magnitude, angle)` takes a real magnitude
(`int`/`Fraction`/`Decimal`) and an explicitly approximate radian `Decimal`
angle; no degrees/radians unit semantics live here (no Hz, rad/s, deg, rad —
those belong to the future OperatingPoint/AC layer). Polar construction exists
because it is small and its convention is documented; richer angle semantics
are out of scope.

## 8. Precision semantics

- Rational side: infinite (exact) within Q(j); memory-bounded only.
- Decimal side: 50 significant digits working context + 15 internal guard
  digits for series evaluation, one final rounding. Verified reference values:
  `sqrt(2)`, `sqrt(3)`, `pi`, `sin(pi/4)`, `cos(pi/3)` against 50-digit
  literals with explicit absolute tolerances (1e-40); test inputs are built
  under the explicit context so the suite measures library accuracy, not
  ambient-context rounding of literals.
- No solver tolerance policy, no equilibration (`Z0/V0/I0/DL/DR`) in D1.

## 9. Forbidden conversions (audited by tests)

- `DecimalComplex` exposes no `to_rational`/`to_exact`/`as_fraction`/
  `to_fraction`/`rationalize`/`exact` attribute (asserted).
- AST scan asserts no `Fraction(...)` construction call exists in
  `decimal_complex.py` (isinstance checks name the type without calling it).
- AST scans assert no `eval/exec/compile/__import__/open/input/breakpoint`
  calls; import-dependency scan asserts no `os/sys/pathlib/sqlite3/urllib/
  socket/http/ftplib/subprocess/pickle/marshal/ctypes/PySide6/numpy/scipy/
  math/cmath` and no `circuit/units/infrastructure/application/app` imports —
  the package is circuit-agnostic and domain-pure (consistent with
  `test_architecture.py`, which also passes unmodified).

## 10. Determinism & serialization

1000 repetitions of mixed exact/approximate pipelines produce identical type,
value, hash, and canonical JSON. Determinism inputs excluded by construction:
no timestamps, no randomness (seeded `random.Random(20260913)` in tests only),
no locale/memory/dict-order/global-context dependence. Frozen dataclasses
reject component mutation (`FrozenInstanceError`); every operation allocates a
new object. `to_dict`/`from_dict` give deterministic mappings
(`{"type":"rational_complex","re":"1/2","im":"3/4"}` and
`{"type":"decimal_complex","re":...,"im":...,"precision":50}` with strict
precision validation) for debugging/provenance/tests — no SQLite, no CAS.

## 11. Regression & boundaries

- Baseline `F0–F8-C` suite must remain green (`739 passed, 2 skipped` minimum);
  no existing file was modified (new files only: `math/` package + D1 tests +
  this gate doc). Any pre-existing failure stops certification — F6/F7/F8-A/B/C
  are not to be touched to make D1 pass.
- D1 does NOT advance to F8-D2: no OperatingPoint, no AC MNA, no R/L/C AC,
  no commit, no push, no remote modification.

## 12. Known limitations

- `DecimalComplex` trigonometry error budget is validated at 1e-40/1e-45
  for the reference points (axes, 45° family, near-unity arguments,
  quadrants); not proven for all arguments.
- `complex_from_polar` assumes radian input by convention; a unit-aware angle
  type is future work outside D1.
- `RationalComplex` with numerators/denominators of thousands of digits is
  exact but slow by design (no premature optimization, no numpy/scipy).

## 13. Correction record (authorized minimal fix, F8-D3 gate)

- Defect: `_arctan_series` evaluated the Taylor series directly up to
  |t| = 1, where convergence is ~1/n per term; the silent 5000-iteration
  cap truncated early (observed 5e-5 error at t = 1, i.e. 45°/135°).
- Fix (only `trig.py` touched): single half-angle reduction
  `arctan(t) = 2*arctan(t/(1+sqrt(1+t^2)))` for |t| > 1/2, giving
  |u| <= 1/(1+sqrt(2)) < 0.42, term ratio < 0.18, convergence in a few
  dozen terms against a 1e-67 truncation threshold; the iteration cap
  (10000) is now a tripwire raising `ArithmeticError`, never a silent
  truncation. Pure Decimal, explicit contexts, global context untouched,
  no float/math/cmath/numpy, `WORKING_PRECISION = 50` unchanged.
- Tests added (`tests/test_f8d1_complex.py`, section 12): cardinal
  angles, 45°/135°/−45°/−135° vs PI50-derived references (1e-45),
  near-unity arguments both sides in all quadrants (tan() cross-check +
  complementary-identity coherence), range/signs/tiny/huge/origin.
- Scope respected: no change to `RationalComplex`, `DecimalComplex`,
  units, phase conventions, D2 tolerances/solver, ngspice, or any file
  outside `trig.py` + D1 tests + this note.
