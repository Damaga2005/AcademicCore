# Engineering Architecture & Audit: F8-A Electronics Knowledge & Analysis Foundation

> **Hardening pass (F8-A HARDENING DEFINITIVO):** the original F8-A coverage encoded several
> concepts (series/parallel resistors, current divider, Thevenin/Norton) as fixed two-component
> formulas presented as if they were the general law. This pass separates GENERAL laws (real,
> arbitrary-N mathematics, executed by `electronics.calc` via associative reduction over F6's own
> `Quantity` arithmetic) from SPECIAL_CASE two-term equations (kept only as the named N=2
> instance), and makes Thevenin/Norton's real capability (`PARTIAL` — general for
> series-parallel-reducible ports, `NOT_IMPLEMENTED` for arbitrary linear networks) explicit
> instead of implicit. See sections 8a-8c below.

## 1. Overview & Architectural Role

Phase **F8-A** builds the deterministic knowledge layer that connects B8's certified structural
recognition to a future exam copilot:

```
Canonical Circuit
      ↓
F7-B8 StructuralCircuitAnalyzer (AnalysisPlan)
      ↓
ElectronicsConceptRecognizer  (registry/, recognition.py)
      ↓
ConceptCandidate[] (with evidence, ApplicabilityStatus)
      ↓
check_analysis_applicability()  (applicability.py)
      ↓
AnalysisApplicabilityResult (status, reason, evidence, confidence)
      ↓
AnalysisProcedure / AnalysisStep (procedures/)
      ↓
ElectronicsEquation (equations/, reusing F6's engine) → F7 simulation directives
```

F8-A does not re-derive circuit structure and never modifies B8's certified output — it is a
read-only adapter over `AnalysisPlan`. It does not implement a solver, a schematic editor, OCR,
or an LLM; it only structures *what is already known* about the recognized topology.

---

## 2. Architecture & Components

Housed in `academic_core.domain.electronics`:

1. **`types.py`** — `RelationType` (requires/related_to/is_a/contains/uses_model/uses_equation/
   uses_analysis/precedes), `ConceptCategory`, and `ApplicabilityStatus`
   (`APPLICABLE`/`NOT_APPLICABLE`/`NEEDS_INFORMATION`/`ABSTAINED`) — deliberately distinct from
   B8's own `ApplicabilityStatus`, which is a structural-only vocabulary (`UNKNOWN`,
   `NEEDS_TARGET_TERMINALS`) that this layer re-maps rather than duplicates or mutates.
2. **`concepts/`** — `ElectronicsConcept` (stable_id, category, description, components,
   topologies, level, relations, common_errors, simulation_mapping, provenance) + the `CONCEPTS`
   registry: the initial circuit-theory core (section 17).
3. **`models/`** — `ElectronicsModel` for the ideal linear component models actually needed
   (`model:resistor-ideal`, `model:vsource-ideal`, `model:isource-ideal`). No semiconductor models.
4. **`equations/`** — `ElectronicsEquation` wraps F6's real `Equation`/`parse_equation`/`evaluate`
   (`academic_core.domain.engineering.equations`) — never a second formula system. Formulas
   already in F6's `calc.LIBRARY` (Ohm's law, power, voltage-divider) are referenced read-only;
   only genuinely new formulas (series/parallel resistors, current divider, bridge balance) are
   declared here.
5. **`analyses/`** — `ElectronicsAnalysis` links a `stable_id` to B8's own `AnalysisType` (no
   parallel analysis-kind enum), required inputs/outputs, equations, a simulation directive
   family (`.op`/`.dc`/`.tran`/`.ac`), and limitations.
6. **`procedures/`** — `AnalysisProcedure`/`AnalysisStep` (order, description, required_inputs,
   equation, expected_output, dependencies, validation, mandatory). Not an executable workflow
   engine yet (section 12) — the ordered/dependency-checked structure is the foundation for one.
7. **`registry/`** — `TOPOLOGY_TO_CONCEPTS`: the single deterministic table mapping a matched B8
   `TopologyType` to candidate concept IDs, derived from each concept's own declared `topologies`
   (never a hand-maintained if/elif chain). `validate_registries()` checks the invariants of
   section 24 (no dangling refs, no duplicate IDs, valid dimensions/topologies).
8. **`recognition.py`** — `ElectronicsConceptRecognizer.recognize(plan)`: consumes a B8
   `AnalysisPlan`, looks up `TOPOLOGY_TO_CONCEPTS` for each `RecognitionMatch`, and additionally
   recognizes classification-anchored concepts (`dc-resistive-network`, `kcl`, `kvl`,
   `ohms-law`) directly from the plan's own `classification`/`kcl_nodes`/`kvl_loops`/
   `applicable_analyses`. Returns `ConceptCandidate` (concept, status, reason, evidence,
   confidence), sorted by concept ID for determinism. If B8 abstained, returns a single
   `ABSTAINED` candidate — never invents a positive concept over an abstained plan.
9. **`applicability.py`** — `check_analysis_applicability(analysis_id, plan)` returns a
   structured `AnalysisApplicabilityResult`, re-mapping B8's `ApplicabilityStatus` values onto
   this layer's own vocabulary (never a bare bool).

## 3. B8 Integration (section 20)

`EngineeringService.recognize_electronics_concepts()` (`application/engineering.py`) is the only
integration point: it calls the existing `analyze_circuit` (B8) and feeds the resulting
`AnalysisPlan` into `ElectronicsConceptRecognizer`. B8's own module (`structural/`) is untouched.

## 4. Evidence & Abstention (sections 15-16)

Every `ConceptCandidate` carries `evidence` traced back to the `RecognitionMatch` that produced
it (topology, elements, reason, metadata) or to the plan's own structural fields. A concept is
never recognized on absence of evidence: e.g. `concept:voltage-divider` requires B8's
`tap_nodes` metadata to be non-empty, otherwise it returns `NEEDS_INFORMATION` rather than
`APPLICABLE`. An abstained B8 plan (empty/disconnected/shorted/unsupported circuit) propagates
to a single `ABSTAINED` concept candidate and to `ABSTAINED` on every analysis-applicability
check.

## 5. Provenance (section 22)

Every concept/model/analysis/equation/procedure carries `provenance = {"source":
"academic-core-internal", "version": "f8a-knowledge/1.0", "stable_id": ...}`. No external
evidence is fabricated. Structural provenance/digest is B8's own (unmodified).

## 6. Initial Coverage (section 17)

Ohm's law, KCL, KVL, series resistors, parallel resistors, voltage divider, current divider,
Thevenin, Norton, resistive (Wheatstone) bridge, DC resistive network. Diodes, BJT, MOSFET,
opamps, filters, advanced RLC, digital, RF, and power electronics are explicitly out of scope.

## 8a. GENERAL vs SPECIAL_CASE (section 5)

`types.Generality` (`GENERAL`/`SPECIAL_CASE`) is a checkable field on `ElectronicsConcept` and
`ElectronicsEquation`, not a documentation convention. A `SPECIAL_CASE` must declare `parent`
(enforced in `__post_init__`) and `validate_registries()` checks the parent actually resolves and
is itself `GENERAL`.

- `concept:two-resistor-divider` (SPECIAL_CASE) → parent `concept:voltage-divider` (GENERAL).
- `concept:wheatstone-bridge-balanced` (SPECIAL_CASE) → parent `concept:resistive-bridge` (GENERAL).
- `equation:series-resistors-pair` / `parallel-resistors-pair` / `current-divider-pair` /
  `voltage-divider-pair` (all SPECIAL_CASE, N=2) → parent `law:series-resistors` /
  `law:parallel-resistors` / `law:current-divider` / `law:voltage-divider` (all GENERAL).

## 8b. GeneralLaw + `electronics.calc` (sections 10/20/41)

F6's equation grammar (`engineering.equations.parse_equation`) parses fixed named-variable
expressions only — it has no "sum over N terms" construct, so a law like `Req = sum(Ri)` cannot
be one parsed `Equation`. `equations.GeneralLaw` represents such a law as structured text
(statement, domain, not_covered, conditions) plus a pointer to the actual arbitrary-N
implementation in `electronics.calc` (`series_equivalent`, `parallel_equivalent`,
`current_divider`, `voltage_divider_chain`). Each function is a pure composition of F6's own
`Quantity` arithmetic / `calculate()` via associative pairwise reduction — never a second math
engine, never capped at N=2 (parametrized N ∈ {1,2,3,4,8,16} in `tests/test_f8_generality.py`).

Building `current_divider` surfaced a real latent bug in F6's `Quantity.convert_to` (it always
re-parsed its own display symbol, which fails for derived dimensions with no registered SI unit,
e.g. conductance = 1/Ω): fixed minimally in `engineering/units.py` by short-circuiting when
converting a quantity to its own unit symbol (always a no-op) — no redesign of the units module.

## 8c. Thevenin/Norton honesty (section 6/36)

`analysis:thevenin`/`analysis:norton` now declare `implementation_status = PARTIAL`: Vth/Rth
computation is GENERAL (any N, any depth) for port sub-networks that reduce via repeated
series/parallel combination (`procedure:thevenin` steps 2/4 use `law:voltage-divider` /
`law:series-resistors`, not the old `equation:voltage-divider`/`equation:parallel-resistors`
pair-equations). A port needing a full linear-network solve (e.g. an unbalanced bridge sitting
inside the port) is `NOT_IMPLEMENTED` — never silently approximated by the two-resistor formulas.

## 7. Limitations

- Thevenin/Norton's Vth/Rth computation is `PARTIAL`: general for series-parallel-reducible port
  sub-networks (any N), `NOT_IMPLEMENTED` for arbitrary linear networks (needs a general
  nodal/mesh solver, out of scope for F8-A per section 43).
- `concept:wheatstone-bridge-balanced` recognition always returns `NEEDS_INFORMATION`: B8's
  `ResistiveBridgeRule` match metadata carries structural evidence (which resistors/nodes form the
  bridge) but not per-arm resistance values, so balance (`R1*R4 == R2*R3`) cannot be verified from
  recognition evidence alone — never inferred from topology/naming (section 13).
- `AnalysisProcedure` is a structured, dependency-checked model, not yet an executable workflow
  engine (explicitly deferred to a later phase per section 12).
- This phase does **not** claim complete electronics coverage (section 28) — only the first
  circuit-theory core.
