# Quality Gate: F8-B General Linear Circuit Solver

## 1. Executive Summary

- **Phase**: F8-B — General Linear Circuit Solver (Modified Nodal Analysis)
- **Prior Baseline**: F8-A `CERTIFIED` (`136cc02`), F7-B8 `CERTIFIED`, unmodified by this phase.
- **Scope**: A general DC linear resistive solver (`src/academic_core/domain/engineering/mna/`)
  for arbitrary topologies built from ideal resistors (R) and ideal independent voltage/current
  sources (V, I), consuming the canonical `Circuit` model directly (no second circuit
  representation). No dependent sources, reactive elements, semiconductors, AC, transients, or
  Thevenin/Norton — those remain out of scope per the phase's declared domain.
- **Status**: **PASS**

---

## 2. Gate Verification Checklist

| Criterion | Requirement | Result | Evidence |
| :--- | :--- | :---: | :--- |
| **Canonical Circuit Truth** | No second `Circuit`/`Component`/`Pin`/`Net` model | **PASS** | `mna/problem.py` consumes `engineering.circuit.Circuit` directly; only derived structures (`MNAProblem`) are new |
| **MNA Formulation** | KCL + resistor stamps + voltage-source constraints, general (not ad-hoc per-topology) | **PASS** | `problem.py::build_mna_problem` stamps every R/V/I generically; zero `if len(...)==N` branching on topology |
| **Exact Arithmetic** | No numpy/scipy (none exist in repo); no floats crossing the solve boundary | **PASS** | `linear.py::solve_exact` — pure `fractions.Fraction` Gauss-Jordan; `Fraction(Decimal(...))` is lossless from `Quantity` |
| **Singular/Inconsistent Classification** | Distinguished without arbitrary numerical tolerance | **PASS** | Exact rational elimination: `pivot == 0` exactly; rank-deficient-but-consistent → SINGULAR, rank-deficient-and-contradictory → INCONSISTENT (`test_solve_exact_*`, `test_singular_*`, `test_inconsistent_*`) |
| **No Invented Ground** | Rejects circuits with no or ambiguous reference | **PASS** | `MissingReferenceError`; `test_missing_reference_node`, `test_ambiguous_reference_nodes` |
| **Floating Circuit Detection** | Nodes unreachable from ground rejected, independent of N | **PASS** | Union-find graph reachability (`_check_reachability`); `test_floating_disconnected_island` |
| **Unsupported Elements Never Silent** | D/Q (and any non-R/V/I) rejected explicitly | **PASS** | `UnsupportedElementError`; `test_unsupported_component_diode` |
| **Precision Separation** | Engineering `Quantity` (Decimal) ≠ linear-algebra precision (`Fraction`, exact) ≠ display rounding | **PASS** | `solver.py` docstring + `PRESENTATION_PRECISION`; no rounding before the final `Quantity` conversion |
| **Dimensionality** | R/V/I values must carry the correct physical dimension | **PASS** | `DimensionalityError`; `test_wrong_dimension_value_raises_at_build` |
| **Structured Result** | Status + node voltages + branch currents + element powers + conservation checks + provenance, never a bare `dict[str,float]` | **PASS** | `result.AnalysisResult` |
| **Branch Current / Power Convention** | Documented, deterministic, tested sign convention | **PASS** | `problem.py`/`solver.py` docstrings; `test_branch_currents_sign_convention_source_delivers` |
| **KCL/KVL/Power Validation** | Available in the result, general (not hardcoded to 1-2 loops) | **PASS** | `ConservationChecks`; KVL via spanning-tree fundamental-cycle basis (`_fundamental_cycle_kvl_residual`), general for arbitrary N |
| **Zero Arbitrary Tolerance** | Any tolerance must be documented/justified | **PASS** | Tolerance is exactly `0`, justified by exact rational arithmetic (see `ConservationChecks.tolerance`) |
| **Generality: N arbitrary** | Series/parallel/ladder tested at N ∈ {1,2,3,4,8,16,32} | **PASS** | `test_series`, `test_parallel`, `test_ladder` (parametrized) |
| **Generality: non-reducible topology** | Bridge (balanced/unbalanced) solved without series/parallel reduction | **PASS** | `test_bridge_unbalanced_exact_value`, `test_bridge_balanced_zero_across_galvanometer` |
| **Multiple/Mixed Sources** | Multiple V, multiple I, mixed V+I | **PASS** | `test_multiple_voltage_sources_series_aiding`, `test_multiple_current_sources_superposition`, `test_mixed_sources` |
| **Determinism** | Same circuit → same digest/result; timestamps excluded from content | **PASS** | `test_determinism_repeated_solve` |
| **Permutation Invariance** | Component insertion order does not affect the result | **PASS** | `test_permutation_invariance_series` (exhaustive over 4! orderings), `test_permutation_invariance_bridge_components` |
| **Node-Renaming Invariance** | Consistent net renaming does not change physical results | **PASS** | `test_node_renaming_invariance` |
| **Metamorphic: Scaling** | Source scaling → V,I ×k, P ×k²; resistance scaling → V unchanged, I/k, P/k | **PASS** | `test_scaling_sources_invariant`, `test_scaling_resistances_invariant` (exact `Fraction`, 3 values of k each) |
| **Metamorphic: Series/Parallel Laws** | Req = ΣRi (series), 1/Req = Σ1/Ri (parallel) | **PASS** | `test_series_equivalent_resistance_law`, `test_parallel_equivalent_resistance_law` |
| **Adversarial Coverage** | Empty, no-GND, floating, R≤0, duplicate ref, unsupported element, incompatible/redundant sources | **PASS** | Section 6 of the test file, 11 dedicated tests |
| **ngspice Cross-Validation** | Independent external oracle, solver never calls ngspice internally | **PASS** | 4 `@pytest.mark.integration` tests (series, parallel, bridge, mixed) — all executed and passing against real ngspice 47 on this machine, not mocked |
| **Security** | No eval/exec/subprocess/os.system/shell=True/pickle/dynamic import/network in the solver | **PASS** | `test_no_eval_exec_subprocess_in_mna_solver`, `test_no_shell_true_or_dynamic_import_in_mna_solver` — static AST + text scan |
| **B8/F8-A Untouched** | Zero modifications to `structural/`, `electronics/`, `circuit.py`, `units.py` | **PASS** | `git status`/`git diff` — F8-B is 100% additive (new `mna/` package + new test file) |
| **F8-B Specific Tests** | All new tests passing | **PASS** | 74 passed, `tests/test_f8b_mna_solver.py` |
| **Full Repository Regression** | Entire suite passing, no regressions | **PASS** | `pytest -q` → 662 passed, 2 skipped (pre-existing, unrelated) |
| **Clean Working Tree** | No stray files after commit | **PASS** | Verified via `git status` |

---

## 3. Capability Table

| Capability | Status | Generality | Evidence | Limitation |
| :--- | :---: | :--- | :--- | :--- |
| DC resistive network solve (R, ideal V, ideal I) | **IMPLEMENTED** | Any connected topology, any N, single reference node | `solve_linear_dc`, full test suite | Domain is exactly R + independent V/I; no dependent sources, reactive elements, or semiconductors |
| Singular/inconsistent detection | **IMPLEMENTED** | General rank-based classification, no tolerance | `linear.solve_exact`, `test_solve_exact_*` | None within stated domain |
| Floating-circuit / missing-reference detection | **IMPLEMENTED** | Graph reachability, arbitrary N | `test_floating_disconnected_island`, `test_missing_reference_node` | None within stated domain |
| KCL/KVL/power-balance validation | **IMPLEMENTED** | General (fundamental-cycle basis), exact | `ConservationChecks`, `test_kcl_residual_zero_for_arbitrary_n`, `test_kvl_residual_zero_on_bridge` | Residuals are algebraic identities of a potential-based nodal solve; genuine as a self-consistency guard, not a substitute for the analytic cross-checks in the test suite |
| ngspice cross-validation | **VERIFIED** | 4 representative topologies (series, parallel, bridge, mixed) | `test_ngspice_cross_validation_*` | Not exhaustive over all topologies; a spot-check oracle, as intended |
| Thevenin/Norton for general (non-series-parallel) one-ports | **NOT_IMPLEMENTED** | — | Not attempted in F8-B | Explicitly deferred; F8-A's `analysis:thevenin`/`analysis:norton` remain `PARTIAL`/`NOT_IMPLEMENTED` until a later phase builds on this solver |
| Dependent sources (VCVS/VCCS/CCVS/CCCS) | **NOT_IMPLEMENTED** | — | `Circuit.COMPONENT_PINS` has no such types | Out of F8-B's declared scope (section 2.1); would require extending F6's `circuit.py` |
| AC / transient / semiconductor analysis | **NOT_IMPLEMENTED** | — | — | Explicitly out of scope (section 41) |

---

## 4. Certification

I hereby certify that phase **F8-B (General Linear Circuit Solver)** satisfies the functional,
mathematical, and safety requirements specified for this phase: a Modified-Nodal-Analysis solver
built on exact rational arithmetic, general over arbitrary connected topologies and node/branch
counts within its declared R/V/I domain, with honest abstention (never a fabricated `SOLVED`)
for singular, inconsistent, floating, or unsupported circuits, full provenance, permutation and
node-renaming invariance, metamorphic scaling invariants, and cross-validation against a real
ngspice installation.

- **Gate Status**: **PASS**
- **Date**: 2026-09-13

```text
F8-B STATUS: CERTIFIED
```

This certifies the general DC linear resistive solver (R, ideal independent V, ideal independent
I) only. It does NOT certify Thevenin/Norton reduction for non-series-parallel networks,
dependent sources, AC/small-signal analysis, or any time-domain behavior — those remain out of
scope for a future phase, which can now be built on top of `solve_linear_dc`/`build_mna_problem`
without re-deriving the linear-algebra layer.
