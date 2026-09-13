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
   - `APPLICABLE` strictly when reactive elements are excited by an AC source (`parameters["ac"]` or `metadata["ac"]` in V/I source). An RLC circuit excited purely by a DC source has `AC = NOT_APPLICABLE` and `TRANSIENT = PRIMARY`.
9. **Statistical & Uncertainty (Monte Carlo, GUM, Sensitivity)**:
   - `APPLICABLE` strictly when components specify explicit tolerance, uncertainty, or sensitivity metadata/parameters. Plain nominal circuits without uncertainty parameters have these analyses marked `NOT_APPLICABLE`.

---

## 5. Ambiguity & Abstention Protocol & Hardening

The analyzer enforces strict refusal to guess and eliminates false-positive recognitions:
- **Empty Circuit**: Abstains with `confidence: ABSTAINED`, `classification: UNKNOWN_TOPOLOGY`, `recognized_topologies: []`, warning `"empty circuit"`.
- **Disconnected Circuit**: Detects disconnected subgraphs via BFS and abstains with `confidence: ABSTAINED`, `classification: UNKNOWN_TOPOLOGY`, `recognized_topologies: []`, warning `"circuit is disconnected into N isolated subgraphs"`.
- **Floating Nodes**: Detects dangling pins (`degree <= 1`) and rejects spurious RC/RL/RLC loop classifications.
- **Short Circuits**: Detects zero-resistance shorted voltage loops and abstains.
- **Unsupported Components**: Detects placeholder active devices (e.g. `D`, `Q`) and abstains from linear analysis.
- **Voltage Divider Tap Nodes**: Exposes intermediate nodes as `tap_nodes: [...]` with `output_node: None`, completely eliminating presumptive `Vout` assignments.
- **Resistive Bridge Diagonal Excitation**: Requires independent voltage or current excitation across opposite diagonal pairs `(A, B)` or `(C, D)`. A ring of 4 resistors without diagonal excitation is rejected.
- **Dynamic Coherent Loops (RC / RL / RLC)**:
  - Capacitors clamped directly across ideal voltage sources do not qualify as RC networks.
  - Every reactive element must participate in a closed loop with at least one resistor.
  - RLC requires coupled meshes where R, L, and C interact; independent uncoupled loops (e.g. separate RC and RL loops) are not classified as RLC.
- **Thévenin / Norton Port Validation**:
  - Missing `target_terminals`: marks `NEEDS_TARGET_TERMINALS`.
  - Degenerate `target_terminals` ($T_1 == T_2$), non-existent nodes, or nodes in disconnected subgraphs: returns `UNKNOWN` with actionable diagnostic warning.
- **Confidence Semantics**:
  - Topological rules are exact graph algorithms: `confidence` is `DETERMINISTIC` by default (warnings do not degrade this to `HIGH`). On abstention, confidence is `ABSTAINED`.

---

## 6. How to Add a New Recognition Rule in the Future

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
