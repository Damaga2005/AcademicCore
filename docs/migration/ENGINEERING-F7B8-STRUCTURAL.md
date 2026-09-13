# Engineering Architecture & Audit: F7-B8 Structural Circuit Analysis

## 1. Overview & Architectural Role

Phase **F7-B8** introduces the structural interpretation and analysis planning layer in AcademicCore:
```
Canonical Circuit
        ↓
Structural Analysis (CircuitGraph)
        ↓
Recognized Topology (RuleRegistry)
        ↓
Analysis Classification (AnalysisClassifier)
        ↓
Analysis Plan (AnalysisPlan)
        ↓
Existing Calculation / Simulation Engines (F6/F7)
```

F7-B8 strictly operates as a **deterministic derived state** over the canonical `Circuit` model. It does not introduce duplicate calculation engines, does not store redundant tables in SQLite, does not use external cloud services or LLMs, and relies purely on graph theory and deterministic electrical engineering rules.

---

## 2. Architecture & Components

The structural analysis system is housed in `academic_core.domain.engineering.structural`:

1. **Graph Representation (`elements.py`)**:
   - `StructuralNode`: Encapsulates net name, canonical connected pins, reference/ground identification, and floating status.
   - `StructuralBranch`: Encapsulates 2-terminal branch connections between nodes.
   - `CircuitGraph`: Builds the electrical network graph, detects connectivity (isolated subgraphs), floating nodes, reference node (0/GND), short-circuits across ideal sources, parallel component groups, series component pairs/chains, KCL cutset nodes, fundamental KVL cycle bases via spanning tree, and boundary-aware series-parallel reduction.

2. **Types & Enums (`types.py`)**:
   - `TopologyType`: Strict enum for recognized topologies (`RESISTIVE`, `SINGLE_RESISTOR`, `SERIES_RESISTORS`, `PARALLEL_RESISTORS`, `SERIES_PARALLEL_REDUCIBLE`, `SERIES_PARALLEL_MIXED`, `VOLTAGE_DIVIDER`, `CURRENT_DIVIDER`, `RESISTIVE_BRIDGE`, `RESISTIVE_WITH_SOURCE`, `NON_REDUCIBLE_RESISTIVE`, `INDEPENDENT_VOLTAGE_SOURCE`, `INDEPENDENT_CURRENT_SOURCE`, `ENERGY_STORAGE`, `RC`, `RL`, `RLC`, `UNKNOWN_TOPOLOGY`).
   - `AnalysisType`: `DC_OPERATING_POINT`, `DC_SWEEP`, `DC_STEADY_STATE`, `TRANSIENT`, `AC`, `NOISE`, `SENSITIVITY`, `MONTE_CARLO`, `GUM_UNCERTAINTY`, `KCL`, `KVL`, `OHMS_LAW`, `VOLTAGE_DIVIDER`, `CURRENT_DIVIDER`, `POWER`, `THEVENIN`, `NORTON`.
   - `ApplicabilityStatus`: `PRIMARY`, `APPLICABLE`, `NOT_APPLICABLE`, `UNKNOWN`, `NEEDS_TARGET_TERMINALS`.
   - `ConfidenceLevel`: `DETERMINISTIC`, `HIGH`, `ABSTAINED`.

3. **Rule-Based Pattern Recognition (`rules.py`)**:
   - `RecognitionMatch`: Encapsulates matched topology, elements involved, and human-readable reason derived strictly from topological relations.
   - `RecognitionRule`: Abstract base class for all rules.
   - Core Rules: `SingleResistorRule`, `SeriesResistorsRule`, `ParallelResistorsRule`, `VoltageDividerRule`, `CurrentDividerRule`, `ResistiveBridgeRule`, `SeriesParallelReducibleRule`, `IndependentSourcesRule`, `DynamicNetworkRule`.
   - `RuleRegistry`: Extensible registry supporting dynamic addition of new rules without modifying the analyzer.

4. **Planning & Classification (`planning.py`)**:
   - `AnalysisClassifier`: Assigns applicability status to all analyses based on structural evidence.
   - `AnalysisStep`: Structured step with number, title, description, and optional closed-form equation reference.
   - `AnalysisPlan`: Full serializable plan with provenance, steps, loops, cutset nodes, and warnings.

5. **Analyzer Entry Point (`analyzer.py`)**:
   - `StructuralCircuitAnalyzer`: Orchestrates graph generation, rule evaluation, and classification.

---

## 3. Catalog of Recognized Topologies

| Topology | Preconditions | Example |
| :--- | :--- | :--- |
| `SINGLE_RESISTOR` | Exactly one resistor in the circuit. | R1 |
| `SERIES_RESISTORS` | Two or more resistors connected in series sharing degree-2 internal nodes. | R1 - R2 |
| `PARALLEL_RESISTORS` | Two or more resistors connected across identical node pair. | R1 \|\| R2 |
| `SERIES_PARALLEL_REDUCIBLE` | Multi-resistor network reducible to single equivalent resistance between boundary terminals. | R1 + (R2 \|\| R3) |
| `SERIES_PARALLEL_MIXED` | Network exhibits both series and parallel connections. | R1 in series with R2 \|\| R3 |
| `VOLTAGE_DIVIDER` | Independent V source connected across series chain of >= 2 resistors with intermediate tap node(s). | V1 (10 V) with R1, R2 |
| `CURRENT_DIVIDER` | Independent I source feeding parallel resistors across common node pair. | I1 (2 mA) with R1 \|\| R2 |
| `RESISTIVE_BRIDGE` | 4 or 5 resistors forming a 4-node Wheatstone bridge with excitation and detector pairs. | Wheatstone bridge |
| `NON_REDUCIBLE_RESISTIVE` | Resistor network forming bridge/mesh that cannot be reduced via pure series/parallel equivalences. | Loaded bridge mesh |
| `INDEPENDENT_VOLTAGE_SOURCE` | Component of type `V` with pins `+` and `-`. | V1 10 V |
| `INDEPENDENT_CURRENT_SOURCE` | Component of type `I` with pins `+` and `-`. | I1 1 A |
| `ENERGY_STORAGE` | Circuit contains capacitors (`C`) or inductors (`L`). | C1, L1 |
| `RC` | First-order network comprising resistors and capacitors in a closed loop. | V1, R1, C1 |
| `RL` | First-order network comprising resistors and inductors in a closed loop. | V1, R1, L1 |
| `RLC` | Second-order network comprising resistors, inductors, and capacitors. | V1, R1, L1, C1 |
| `UNKNOWN_TOPOLOGY` | Disconnected, empty, or unclassifiable circuit topology. | Empty or isolated subgraphs |

---

## 4. Analytical Applicability Rules

1. **KCL (Kirchhoff's Current Law)**:
   - `APPLICABLE` when circuit is connected and contains non-datum nodes of degree $\ge 2$.
2. **KVL (Kirchhoff's Voltage Law)**:
   - `APPLICABLE` when circuit contains fundamental cycles (closed loops) extracted via the spanning tree cycle basis.
3. **Ohm's Law**:
   - `APPLICABLE` whenever linear resistors are present.
4. **Power Analysis**:
   - `APPLICABLE` whenever resistors and/or independent sources are present in a connected circuit.
5. **Thévenin / Norton**:
   - If explicit `target_terminals` $(T_1, T_2)$ are provided and valid: `APPLICABLE`.
   - If `target_terminals` are omitted: `NEEDS_TARGET_TERMINALS` (strictly avoids inventing ports).
6. **DC Operating Point**:
   - `PRIMARY` for purely resistive circuits with sources.
   - `APPLICABLE` for steady-state evaluation of dynamic circuits.
7. **Transient**:
   - `PRIMARY` for RC, RL, and RLC networks.
8. **AC**:
   - `APPLICABLE` strictly when a `V`/`I` source carries **validated** AC excitation evidence:
     - an `"ac"`/`"AC"` key in `parameters` or `metadata` whose *value* is positively validated (rejects `False`, `None`, `""`, `0`, `"false"`, `"none"`, `"off"`, `"no"`); or
     - an explicit `"amplitude"` + `"frequency"` (or `"freq"`) pair, both carrying real values; or
     - a standalone, word-boundary-matched `"ac"` token inside any string parameter/metadata value (e.g. `"AC 5V 60Hz"`), never a substring match (`"trace"`, `"aircraft"` never match).
   - The mere presence of R+L+C (or the `"ac"` substring inside an unrelated key/value) is never sufficient. An RLC circuit excited purely by DC has `AC = NOT_APPLICABLE` and `TRANSIENT = PRIMARY`.
9. **Statistical & Uncertainty (Monte Carlo, GUM, Sensitivity)**:
   - `APPLICABLE` strictly when a component carries one of the following **exact, validated** keys (in `parameters` or `metadata`):
     - Monte Carlo: `tolerance` or `distribution`.
     - GUM: `uncertainty`.
     - Sensitivity: `sensitivity`.
   - The value itself must be positive evidence (non-null, non-empty, not `"false"`/`"none"`/`0`/etc.) -- the mere presence of the key with a negated/empty value does not count.
   - Deliberately excludes short/ambiguous keys (`u`, `dev`, `mc`, `tol`, `unc`, `gum`, `sens`, `vary`, `std_u`, `type_b`, ...) that could collide with unrelated metadata and turn absence-of-evidence into a false positive. Plain nominal circuits without these exact keys have all three analyses marked `NOT_APPLICABLE`.

---

## 5. Ambiguity & Abstention Protocol & Hardening

The analyzer enforces strict refusal to guess and eliminates false-positive recognitions:
- **Empty Circuit**: Abstains with `confidence: ABSTAINED`, `classification: UNKNOWN_TOPOLOGY`, `recognized_topologies: []`, warning `"empty circuit"`.
- **Disconnected Circuit**: Detects disconnected subgraphs via BFS and abstains with `confidence: ABSTAINED`, `classification: UNKNOWN_TOPOLOGY`, `recognized_topologies: []`, warning `"circuit is disconnected into N isolated subgraphs"`.
- **Floating Nodes**: Detects dangling pins (`degree <= 1`) and rejects spurious RC/RL/RLC loop classifications.
- **Short Circuits**: Detects zero-resistance shorted voltage loops and abstains.
- **Unsupported Components**: Detects placeholder active devices (e.g. `D`, `Q`) and abstains from linear analysis.
- **Voltage Divider Tap Nodes**: Exposes intermediate nodes as `tap_nodes: [...]` with `output_node: None`, completely eliminating presumptive `Vout` assignments.
- **Resistive Bridge Diagonal Excitation**: Requires real 4-arm topology matching -- the four arms `(A,C), (A,D), (B,C), (B,D)` must exist as actual resistor branches (never inferred from a component count of 4 or 5). The matched excitation source is stored **explicitly** in match metadata as `matched_source_pair` and `matched_source_ref` from the moment it is found (never derived from a residual/leftover loop variable), so the 5th-resistor diagonal decision and the result are deterministic and independent of component/source insertion order. A ring of 4 resistors without diagonal excitation, or with the source on an arm, is rejected. For 5 resistors, the fifth must land exactly on the opposite diagonal of the matched excitation pair.
- **Dynamic Coherent Loops (RC / RL / RLC)**:
  - Capacitors clamped directly across ideal voltage sources, or inductors clamped directly across ideal current sources, do not qualify as RC/RL networks (the ideal source removes the dynamic degree of freedom).
  - Every reactive element must participate in a closed loop with at least one resistor; disconnected/floating reactive elements are structurally rejected (the whole-circuit connectivity precondition means a genuinely disconnected RC+RL pair triggers ABSTENTION before dynamic classification even runs).
  - RLC requires coupled meshes where R, L, and C interact; independent uncoupled loops (e.g. separate RC and RL loops sharing only GND) are not classified as RLC, RC, or RL.
  - `ENERGY_STORAGE` (mere presence of C/L) is always kept semantically distinct from `RC`/`RL`/`RLC`/`TRANSIENT`: it never implies a concrete dynamic network was demonstrated.
- **Thévenin / Norton Port Validation**:
  - Missing `target_terminals`: marks `NEEDS_TARGET_TERMINALS`.
  - Degenerate `target_terminals` ($T_1 == T_2$), non-existent nodes, or nodes in disconnected subgraphs: returns `UNKNOWN` with actionable diagnostic warning. (In practice, a circuit that is disconnected at the target-terminal level is also disconnected overall and is caught earlier by the global disconnected-circuit abstention -- see Limitations.)
  - `THEVENIN`/`NORTON` are never marked `APPLICABLE` without demonstrating both terminals exist, are distinct, and belong to the same connected component.
- **Confidence Semantics**:
  - `DETERMINISTIC` means the decision was produced by an exact, deterministic graph algorithm -- it is **not** a synonym for "perfect" or "warning-free". A recognized topology with an accompanying structural warning (e.g. a benign extra terminal note) remains `DETERMINISTIC`; warnings never silently upgrade or downgrade confidence.
  - `HIGH` is reserved for future non-exact/heuristic-assisted recognition paths (not currently emitted by any B8 rule).
  - `ABSTAINED` means the analyzer refused to classify/recognize because required evidence was missing or the topology was ambiguous/invalid; `recognized_topologies` is always empty and `applicable_analyses` is all `NOT_APPLICABLE` in this state.
  - Confidence is never used as a proxy for numeric uncertainty -- that remains the domain of GUM/Monte Carlo (F7-B6/B7), not B8.
- **Floating Nodes / Missing GND -- Structural vs. Analytical Boundary**:
  - A floating pin (`degree <= 1`) or an absent reference/GND node produces a **warning**, not automatic abstention -- B8 is a structural recognizer, not a solver, so it does not need a datum to describe topology.
  - However, the absence of a reference node is never silently ignored: `DC_OPERATING_POINT`/`DC_STEADY_STATE`/`THEVENIN`/`NORTON` applicability is still computed structurally, but any consumer of the plan MUST treat magnitudes as undefined until an analytical engine (F7-B1..B7) supplies a reference. B8 stops at recognizing that a reference is missing; it does not resolve or assume one.

---

## 6. Provenance Digest & Determinism

`AnalysisPlan.provenance["digest"]` is a SHA-256 hash of a **canonical structural fingerprint** (`planning._canonical_structure`), which incorporates:

- circuit identity (name) and full node set,
- every component's ref, type, canonicalized value (via `Quantity.compact()`), pins, parameters, and metadata,
- every branch (id, ref, type, endpoints),
- every recognized topology match (topology, elements, metadata),
- the final classification,
- the requested target terminals (if any),
- the engine version.

It deliberately **excludes** the timestamp, Python object identities, and any non-deterministic value. Because components/branches/matches are sorted canonically before hashing (and `json.dumps(..., sort_keys=True)` is used), the digest is:

- **insertion-order independent**: component insertion order, node dict order, and metadata dict key order never change the digest;
- **content-sensitive**: two circuits differing in any component value, pin, parameter, metadata, topology match, classification, or target terminals produce different digests;
- **timestamp-independent**: two analyses of the same circuit at different `at=` timestamps produce identical digests (only `provenance["timestamp"]` differs).

An **abstained** plan's digest also incorporates the same canonical structural fingerprint (plus the abstention reason), so two different abstained circuits sharing the same name and reason never collide on digest -- provenance is never reduced to `circuit_name + reason`.

`AnalysisPlan.to_json()` uses `json.dumps(..., sort_keys=True)`, so full-plan serialization is stable and byte-identical across equivalent circuits built in different component/node insertion orders (verified by `test_full_plan_serialization_deterministic_across_permutations`).

`RuleRegistry` registers rules in a fixed, explicit order in `_register_defaults()` (not import order, not hash order, not component-name-derived); `evaluate_all()` additionally sorts the resulting matches by `(topology, elements)`, so recognition order never depends on dict/set iteration order.

---

## 7. Limitations (Honest Disclosure)

- The Thévenin/Norton "target terminals belong to disconnected subgraphs" code path exists and is exercised by `AnalysisClassifier`, but in practice a genuinely disconnected pair of terminals almost always means the whole circuit is disconnected, which the classifier already catches earlier via the global disconnected-circuit abstention. The path is defensive/future-proofing rather than reachable with the current whole-circuit-first abstention ordering.
- B8 does not solve or verify Thévenin/Norton equivalents, transient responses, AC phasors, nodal/mesh systems, or GUM/Monte Carlo numeric propagation -- it only determines structural *applicability* and produces a plan of steps referencing the analytical methods that F6/F7-B1..B7 (or future engines) must execute.
- `ConfidenceLevel.HIGH` is defined in the enum but is not currently emitted by any B8 rule; all successful recognitions are `DETERMINISTIC` and all refusals are `ABSTAINED`. This is intentional (see Confidence Semantics above) but worth stating plainly.
- Reactive-element "clamping" checks (capacitor across an ideal V source, inductor across an ideal I source) cover the two canonical degenerate cases; more exotic degeneracies (e.g. a capacitor and inductor both clamped by different ideal sources in the same coupled loop) are covered indirectly by the coupled-loop requirement but have not been exhaustively enumerated beyond the test matrix in this pass.

---

## 8. How to Add a New Recognition Rule in the Future

The architecture allows adding new rules (e.g. `DiodeRecognitionRule`, `OpAmpRecognitionRule`) without modifying `StructuralCircuitAnalyzer`:
```python
from academic_core.domain.engineering.structural import (
    RecognitionRule, RecognitionMatch, TopologyType, RuleRegistry, StructuralCircuitAnalyzer
)

class DiodeRecognitionRule(RecognitionRule):
    @property
    def rule_name(self) -> str:
        return "DiodeRecognitionRule"

    def evaluate(self, graph):
        matches = []
        diodes = [c for c in graph.components.values() if c.type == "D"]
        for d in diodes:
            matches.append(RecognitionMatch(
                topology=TopologyType.MIXED,
                elements=(d.ref,),
                reason=f"Diode {d.ref} detected across nodes {d.pins['A']} and {d.pins['K']}."
            ))
        return matches

# Registration
registry = RuleRegistry(default_rules=True)
registry.register(DiodeRecognitionRule())
analyzer = StructuralCircuitAnalyzer(registry=registry)
```
