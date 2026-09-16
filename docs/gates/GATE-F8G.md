# Quality Gate: F8-G — Ideal Transformers + Linear Two-Port Network Parameters

- **Phase**: F8-G (after F8-F certified + published; HEAD at start =
  `26762e5`; F8-G DESIGN READY accepted before implementation).
- **Scope**: exact ideal transformer (`T`, `V2 - n*V1 = 0`,
  `I1 + n*I2 = 0`, +2 unknowns/+2 equations) in DC exact and AC
  phasor, plus a post-processing two-port observable layer
  (Z/Y/h/g/ABCD) over the certified D5 test-source machinery.
  NO semiconductors, NO mutual inductance, NO lossy magnetics,
  NO two-port composition algebra, NO new transients, NO finite-gain
  approximations, NO second solver, NO second Circuit.
- **Files (tracked modifications)**:
  `circuit.py` (T pins + ref regex), `units.py` (bare dimensionless in
  `compact()` — netlist roundtrip fix, see §11), `mna/problem.py`
  (validation + DC stamp + leg aux namespace), `mna/solver.py`
  (winding-leg branches + KCL + provenance), `mna/dependent.py`
  (H/F control by T rejected loudly), `thevenin/port.py` + `thevenin/
  analysis.py` (T membership/keep), `ac/problem.py` (validation + AC
  stamp + duplicate-`size` fix), `ac/solver.py` (provenance),
  `ac/__init__.py` (two-port re-exports).
- **Files (new, F8-G)**: `ac/twoport.py` (observable layer only),
  `tests/test_f8g_twoport_transformer.py` (101 tests), this doc.
- **Files (new, incorporated dependency baseline)**: the on-disk F8-D
  implementation (`ac/bode.py`, `ac/errors.py`, `ac/impedance.py`,
  `ac/operating_point.py`, `ac/phasors.py`, `ac/power.py`,
  `ac/response.py`, `ac/solution.py`, `ac/topology.py`,
  `math/*`, `tests/test_f8d1..d6*.py`) predates F8-G, was never
  committed, yet HEAD's own `ac/__init__.py` imports it — the
  committed tree cannot import without it. This commit incorporates
  those files unchanged-as-found (except `ac/problem.py`, see above)
  as the dependency baseline F8-G builds on. NOT included:
  `docs/gates/GATE-F8D*.md` (prior-session docs, out of scope),
  `full_result.log` (junk), `.stfolder/` (forbidden).
- **Status**: VERIFIED — committed LOCAL ONLY (no push).

> Certified domain: exact ideal transformers (any real finite `n`,
> including 0/negative/fractional) in arbitrary R/V/I/E/G/H/F/O
> (DC) and R/L/C/V/I/E/G/H/F/O (AC) networks, plus Z/Y/h/g/ABCD
> extraction with honest FINITE/ZERO/INFINITE/UNDEFINED verdicts.

---

## 1. Baseline (honest deviation recorded)

HEAD `26762e5` as expected, branch `main`. The §2 STOP rule fired:
tracked modifications (T stamp work) and untracked files (F8-D
implementation + F8-G draft tests) were already present from
prior session(s). Per the finishing mandate, instead of stopping,
every pre-existing hunk was reviewed (all T/two-port-scoped or
F8-D dependency files) before building on it. Pre-change F8-G file:
87/88 passing (one presentation-rounding assertion, fixed in §12).
Full-suite pre-change single run was not recorded; post-change full
regression is §17.

## 2. Canonical representation

`Component(ref, "T", gain_Q, pins, {})` with
`pins = {"1": primary+, "2": primary-, "3": secondary+,
"4": secondary-}`. `value` = turns ratio `n`: dimensionless,
finite, real, non-NaN (validated in DC + AC; params must be `{}`).
`n > 0`, `n < 0`, `n = 0` all admitted by design; fractional `n`
exact. NO `Transformer` class. H/F control naming a `T` (or a
`T1:1` leg record) is INVALID — two winding currents make a bare
ref ambiguous; rejected loudly, never guessed (§F8-G limitation).

## 3. Mathematical stamp (exact academic model)

`V1 = V(1)-V(2)`, `V2 = V(3)-V(4)`, aux `i1` = current 1→2, aux
`i2` = current 3→4 (both leaving their "+" pin, exactly the
V-branch convention). Rows: `V(3)-V(4)-n(V(1)-V(2)) = 0` on leg
row k1; `I1 + n·I2 = 0` on leg row k2. KCL: `+1/-1` at (p1,p2)
for k1, `+1/-1` at (s1,s2) for k2. Per T: +2 unknowns, +2
equations; matrix stays square (test pins shape 2+1+2=5).
Leg keys `"T1:1"/"T1:2"` share the `vsource_index` aux namespace,
so F8-E resolve/apply and F8-C `i_v` maps compose with no new
fields. No big resistor, no dependent-source approximation, no
epsilon, no finite gain. `n = 0` falls out of the same stamp
(`V2 = 0`, `I1 = 0`); the solver classifies the outcome.

## 4. Sign conventions (frozen in tests)

`I1, I2` ENTER winding 1/2 is the two-port convention; the MNA
aux unknowns leave "+" (V-branch convention) and every consumer
negates explicitly where the entering convention applies
(`_short_values` returns `-i_unknown`, D5 rule). ABCD uses `-I2`
(leaving port 2): `V1 = A·V2 - B·I2`, `I1 = C·V2 - D·I2` with `I2`
entering. Pinned by: sign-constraint tests, ABCD sign test
(`B = -V1/I2 = 0`, `D = -1/I2 = 2`, not the negations), and three
external hand vectors (n=2: `[[1/2,0],[1/500,2]]`; n=1/2:
`[[2,0],[1/2000,1/2]]`; n=-1: `[[-1,0],[-1/1000,-1]]`).

## 5. DC (F8-B extended to R/V/I/T + E/G/H/F/O)

Fraction path, no floats in the exact solver. Validated: n=1, 2,
1/2, -1, 0, fractional, chains (n1·n2 product), impedance
reflection
...[truncated 6154 chars]