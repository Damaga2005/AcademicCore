# F8-H Design Audit — Nonlinear Circuits (DC Operating Point)

> Phase: audit only. No F8-H production code written, no certified file
> modified, no push, `.stfolder/` untouched. Verdict at §24.

---

## 1. Executive summary

F8-H is the jump from exact linear MNA (F8-B…F8-G) to **nonlinear DC
operating-point analysis** for general circuits containing diodes.
The audit finds the current architecture **supports** this jump
without redesign: the unknown-vector layout, the linear-stamp
machinery, the `math/linsolve` HP solver, the Decimal contexts, the
validation gates, and the provenance pattern are all reusable as-is,
and the nonlinear addition is a thin, well-bounded layer (residual +
analytic Jacobian + damped Newton reusing the certified linear
solver). Scope is deliberately narrow — **one smooth nonlinear
model (Shockley diode), DC only, no AC/transient, no BJT/MOSFET, no
ideal/PWL diode, no source-stepping** — so that generality is
achieved inside an explicitly declared mathematical domain rather
than by example-chasing. Verdict: **`F8-H DESIGN READY`** (§24),
with 5 open questions (§23) that constrain implementation choices
but do not threaten the architecture.

---

## 2. Current architecture audit

Tree audited at `7e85834` (HEAD `main`, +1 over `origin/main`;
working tree clean except pre-existing untracked
`GATE-F8D*.md`/`full_result.log`/`.stfolder/`, all out of scope).
Two read-only sub-audits were performed (DC/MNA/linear stack;
AC/linsolve/oracle stack); this section is their synthesis,
cross-checked against the files.

### 2.1 Canonical model (`circuit.py`)

- `Component(ref, type, value: Quantity|None, pins: dict, parameters:
  dict)` — frozen dataclass, but `pins`/`parameters` dicts are
  shallow-mutable (documented debt; engines never mutate).
- `COMPONENT_PINS` already declares `D: ("A","K")` and
  `Q: ("C","B","E")`; `_REF_RE` accepts `D\d+`/`Q\d+`. **Diodes are
  representable today; they are rejected downstream as
  UNSUPPORTED** (`mna/problem.py` `SUPPORTED_TYPES =
  {R,V,I,E,G,H,F,O,T}`; AC likewise without D/Q).
- **Design-vs-reality**: there are no `Pin`/`Net` classes. Nets are
  plain strings (`Circuit.nets: set[str]`), pins are
  `dict[str,str]`, ground is a string (`"0"`/`"GND"`). Any F8-H
  design speaking of "Pin/Net objects" must be translated to
  string-net reality.
- Netlist (`to_netlist`/`from_netlist`, `engcircuit/6.0`) is
  deterministic and strict, but **serializes no `parameters`**
  (AUDIT-002 precedent: E/G/H/F control data is lost on roundtrip
  by design limitation). Diode model parameters will hit the same
  wall — declared as limitation in §4, not silently extended.

### 2.2 Units (`units.py`)

- `Quantity(Decimal, Unit)`; `Decimal`-only, `to_base()` exact,
  `is_finite()` gates; matrix coefficients enter as
  `Fraction(Decimal)` — exact, never float.
- Dimension map enforced per type; `R > 0`, finite gains, valueless
  `O`. A diode will need a **parameter policy** (`Is`, `n`, … in
  `parameters`, with dimensions/units and finite/positive checks at
  the same gate).

### 2.3 DC linear core (`mna/`)

- Unknown layout (frozen contract): sorted non-ground nodes, then
  sorted `V/E/H/O` single aux refs, then sorted `T` leg keys
  (`"T1:1"`, `"T1:2"`); `size` property; ground has no row/col.
  F8-H reuses this layout **bit-for-bit** — the nonlinear residual
  lives on the same vector `x`.
- Assembly is `Fraction`-exact; `solve_exact` is Gauss-Jordan over
  `Fraction` (no numpy, deterministic pivot scan). Status:
  `UNIQUE/SINGULAR/INCONSISTENT` by exact rank; mapped to in-band
  `SOLVED/SINGULAR/INCONSISTENT`; validation failures raise typed
  errors mapped to `INVALID/UNSUPPORTED`. Conservation
  (KCL+KVL+power `== 0` exact, fundamental-cycle KVL) gates every
  `SOLVED`; `NumericalSolveError` is never swallowed.
- Dependent sources: `resolve_control`/`apply_form` linear forms
  with reported-current conventions (`+→−` aux; `I/G/F` reported
  as `-delivered`; `O` as `-i_o`; `T` legs direct). **H/F control
  targeting a `T` is loudly INVALID** — the precedent F8-H copies
  for diode-current control (§5.5).
- Provenance: `sha256` over canonical sorted JSON (digest inputs
  are timestamp-free), conditional `dependent_sources`/
  `ideal_opamps`/`ideal_transformers` blocks preserve byte-identity
  for circuits without them. Note: the emitted `provenance` dict
  *carries* a `timestamp` field (F8-G "timestamp-free" claims refer
  to digest inputs — F8-H must keep that distinction).

### 2.4 Linear algebra authority (`math/linsolve/`)

- Single authority: `ComplexLinearProblem.from_sequences` +
  `solve(problem, mode)` with
  `EXACT/HIGH_PRECISION/AUTO`; `SolveStatus =
  SOLVED/SINGULAR/INCONSISTENT/NUMERICALLY_UNCERTAIN` by
  Rouche–Capelli ranks; HP adds residual, backward error
  (`BE_TOL=1E-30`), pivot floors, equilibration.
- Refusal policy is the model: `EXACT`-on-decimal raises instead of
  faking exactness; `float/complex/str/bool` rejected at entry.
  F8-H copies this policy for its own refusals (§8).
- Number types: `RationalComplex` (exact) / `DecimalComplex`
  (`WORKING_PRECISION=50`, explicit contexts, one-way
  `from_rational`). A real Newton loop can drive the HP solver
  with zero-imaginary Decimals without introducing imaginary
  error (decision §7.5, alternative in §23/Q2).

### 2.5 AC + oracles + tests

- AC reuses the DC aux-leg scheme with complex stamps; EXACT
  eligibility (no L/C, axis-aligned degree phases) is the template
  for F8-H's own eligibility honesty.
- ngspice is a **bounded external oracle, never the definition**:
  hand derivation primary; decks (`V/R/L/C`, explicit `.model`,
  `ACAnalysis(lin,2,f,f+1)`, `sample_complex_at`) with tolerances;
  documented polarity mappings (E direct; H/F sense same-sign;
  G/F/I opposite-reference; voltage-only comparisons); skip pattern
  `NG is None → skipif` when the binary is absent.
- Inventory: ~75 test files, full suite 1578 cases at F8-G
  certification (0 failed, 2 pre-existing skips). F8-H must keep
  all of them green (§20).

### 2.6 Contracts F8-H must conserve (normative)

C1. Exact-`Fraction` MNA, tolerance-0 gate; rounding only in
presentation (`_fraction_to_decimal(28)`).
C2. Unknown order/keying/`size`/single-ground rules.
C3. Orientation/power/sign table (R `1→2`, rest `+→−`, legs,
`-delivered` reports, `P = V·I`, `ΣP == 0`).
C4. Dependent-source semantics (validation, cycles, order, gain
dimensions); `T` not a control target.
C5. `resolve_control`/`apply_form` conventions;
`CircularControlError` preserved.
C6. Status taxonomy + in-band mapping; never `SOLVED` on failed
conservation; never swallow `NumericalSolveError`.
C7. Fundamental-cycle KVL + KCL gate.
C8. Provenance digest inputs (sorted, timestamp-free) + conditional
blocks (byte-identity); `AnalysisResult` schema stable.
C9. `Quantity` boundary (Decimal-only, dimension map, finiteness).
C10. Netlist determinism; parameters unserialized (do not silently
change).
C11. `NumericMode` dispatch + EXACT refusal; HP thresholds;
`SolveStatus` 4-values + rank machinery.
C12. ngspice mapping caveats + hand-primary oracle rule + skip
patterns.

---

## 3. F8-H scope (normative)

**IN:**

- (a) Shockley diode as the single certified nonlinear element,
  pins `A`/`K` (already declared), model
  `I = Is·(exp(Vd/(n·Vt)) − 1)`, `Vd = V(A) − V(K)`, with
  branch-voltage orientation `A→K` and reported current following
  the `+→−` convention (diode `+` ≡ `A`).
- (b) DC operating-point solve
...[truncated 17919 chars]