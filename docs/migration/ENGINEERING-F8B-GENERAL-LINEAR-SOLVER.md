# Engineering Architecture & Audit: F8-B General Linear Circuit Solver

## 1. Overview & Architectural Role

Phase **F8-B** builds the first general numeric solver in Academic Core: a Modified Nodal
Analysis (MNA) engine for DC linear resistive networks, closing the gap F8-A left explicit
(`analysis:thevenin`/`analysis:norton` marked `PARTIAL`/`NOT_IMPLEMENTED` for non-series-parallel
networks).

```
Canonical Circuit (F6: engineering/circuit.py)
      ↓
mna.build_mna_problem()      — validate + assemble A x = z
      ↓
mna.linear.solve_exact()     — exact Fraction Gauss-Jordan
      ↓
mna.solve_linear_dc()        — node voltages, branch currents, powers,
                                conservation checks, provenance
      ↓
AnalysisResult
```

F8-A's knowledge layer is a consumer of this solver, not a producer — no code in
`domain/electronics/` was touched, and `analysis:thevenin`/`analysis:norton`'s status is left
unchanged in this phase (flipping it is deliberately deferred, per the spec: "Thevenin/Norton
implemented as a natural consequence of the architecture" would need to be demonstrated for the
*entire* declared domain before being marked `IMPLEMENTED`, which was not attempted here).

## 2. Why Exact Rational Arithmetic, Not numpy/scipy

The audit preceding this phase found zero numeric linear-algebra dependencies anywhere in the
repository (no numpy, no scipy, no `fractions.Fraction` use, no `Matrix` class), and F6's own
`units.py` docstring states the repo's governing constraint: "No floats cross this boundary."
Introducing numpy/scipy for this phase would be the single largest architectural deviation
possible and was rejected in favor of a from-scratch `fractions.Fraction` Gauss-Jordan
elimination (`mna/linear.py`):

- Every value entering the matrix originates from a `Quantity` (`Decimal`); `Fraction(Decimal(...))`
  is an exact, lossless conversion — no floating-point ever appears.
- Singularity is `pivot == 0` **exactly**, so SINGULAR vs. INCONSISTENT classification needs no
  numerical tolerance at all — the ambiguous "how much tolerance is enough" question the prompt
  explicitly warns against simply does not arise.
- Decimal rounding is deferred entirely to the presentation boundary: the exact `Fraction`
  solution is used for every internal check (KCL/KVL/power residuals), and is only converted to
  `Decimal` (34 significant digits, a digit count, not an absolute epsilon) when wrapping the
  final node voltages/currents/powers in `Quantity` for the caller.

## 3. MNA Formulation

Unknowns: one voltage per non-reference net (sorted by name), followed by one branch-current
unknown per ideal voltage source (sorted by ref). For `n` nodes and `m` voltage sources, the
system is `(n+m) x (n+m)`.

**Resistor** (pins `"1"`, `"2"`, conductance `G = 1/R`):
```
A[n1,n1] += G   A[n1,n2] -= G
A[n2,n1] -= G   A[n2,n2] += G
```

**Ideal voltage source** (pins `"+"`, `"-"`, unknown current `I_V` defined flowing `+` → `-`
through the source):
```
A[+, k] += 1    A[k, +] += 1
A[-, k] -= 1    A[k, -] -= 1
z[k] += Vs
```

**Ideal current source** (`Is` delivered into the circuit at `+`, i.e. flows `-` → `+` through
the source):
```
z[+] += Is
z[-] -= Is
```

Ground rows/columns are simply omitted (the standard MNA reduction for `V(GND) = 0`), rather than
inventing a GND net when the circuit has none — a circuit with no net named `"0"`/`"GND"`
(case-insensitive) or more than one such distinct net raises `MissingReferenceError` before any
matrix is built.

Branch current / power reporting uses one consistent "through-the-element" direction for every
component type (documented exhaustively in `problem.py`'s and `solver.py`'s module docstrings):
resistor `"1"→"2"`, voltage source `"+"→"-"` (the MNA unknown itself), current source `"+"→"-"`
(the *negative* of the delivered value, since `Is` is defined flowing the opposite way). Using one
convention for every element is what makes `Σ P == 0` hold exactly (Tellegen's theorem) — an
earlier draft used the delivered-direction sign for current sources directly and the power
residual came out nonzero on a mixed R/I test circuit; the sign was corrected before certification
(see `git log` / the test `test_multiple_current_sources_superposition`, whose exact node voltage
depends only on this being right).

## 4. Validation, Not Special-Casing

Per the spec's central rule against `if len(branches) == 2`-style hardcoding, only three checks
happen *before* matrix assembly, all of them general (work for any N):

1. **Domain membership** — every component must be R, V, or I (`UnsupportedElementError`).
2. **Reference node** — exactly one net named `"0"`/`"GND"` (case-insensitive) must exist
   (`MissingReferenceError`).
3. **Reachability** — every net must have a graph path (through any component) to the reference
   node, checked via union-find (`FloatingCircuitError`).

Everything else — redundant/incompatible voltage sources, degenerate networks, short-circuited
sources — is left to the general exact linear solve to classify as SINGULAR or INCONSISTENT.
Nothing in the assembly or solve code branches on node/branch count.

## 5. Precision Boundary

Three explicitly separated precisions, per the spec:

| Layer | Representation | Rounding |
| :--- | :--- | :--- |
| Engineering quantity (`Quantity`) | `Decimal`, arbitrary precision | None (F6 invariant, untouched) |
| Linear algebra (`mna.linear`) | `fractions.Fraction` | None — exact rational arithmetic |
| Presentation (`AnalysisResult`) | `Decimal`, 34 significant digits | Rounding happens here only |

## 6. What This Phase Deliberately Does Not Do

- No dependent sources (VCVS/VCCS/CCVS/CCCS) — `Circuit.COMPONENT_PINS` has no such types today;
  adding them would mean extending F6, which is out of scope.
- No Siemens/conductance unit added to F6 — conductance stays an internal `Fraction`, never
  wrapped in `Quantity`, exactly as the spec anticipates for a unit F6 doesn't yet register.
- No Thevenin/Norton, AC, transient, or semiconductor analysis (sections 24/41 of the spec).
- No changes whatsoever to `domain/electronics/`, `domain/engineering/structural/`, `circuit.py`,
  or `units.py` — verified via `git status`/`git diff` showing this phase as purely additive.

## 7. Test Strategy

`tests/test_f8b_mna_solver.py` (74 tests) is organized into the sections named in the spec:
assembly/stamping, parametric generality (N ∈ {1,2,3,4,8,16,32} for series/parallel/ladder, plus
a non-reducible bridge), multiple/mixed sources, branch current/power sign conventions, KCL/KVL,
adversarial/degenerate circuits (12 dedicated cases), determinism, permutation invariance
(exhaustive over all 4! orderings for one circuit, randomized for the bridge), node-renaming
invariance, metamorphic scaling invariants (computed via exact `Fraction`, not the
presentation-rounded `Decimal` output — necessary because several of these circuits have
non-terminating-decimal exact values, e.g. the bridge's factor of 3, and comparing two
independently-34-digit-rounded decimals is not a fair equality test), series/parallel equivalent-
resistance laws, unit-prefix handling, the isolated linear-solve primitive, four real ngspice
cross-validation tests (`@pytest.mark.integration`, executed against a real local ngspice 47
install, not mocked), and a static AST/text security scan.

Full repository regression: `pytest -q` → 662 passed, 2 skipped (pre-existing, unrelated to this
phase).
