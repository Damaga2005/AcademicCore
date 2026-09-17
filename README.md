# AcademicCore

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Tests Passing](https://img.shields.io/badge/tests-1680%2B%20passed-brightgreen.svg)]()
[![Status](https://img.shields.io/badge/status-F0--F8--I%20CERTIFIED-success.svg)]()
[![License](https://img.shields.io/badge/license-MIT-blue.svg)]()

AcademicCore is a high-precision, deterministic academic engineering and learning platform designed for electrical engineering, mathematics, metrology, and computer science. It combines a rigorous circuit simulation core (MNA DC, AC phasorial, and nonlinear semiconductor models) with structured knowledge representation, adaptive assessment, and AI-assisted tutoring governed by mathematical guardrails.

> [!IMPORTANT]
> **Deterministic Sovereignty Rule**:  
> AcademicCore operates fully without requiring an LLM. When a mathematical, physical, or numerical answer exists, it is obtained via deterministic algorithms. AI is utilized strictly as a conversational and pedagogical layer, never as the mathematical or physical authority of the system.

---

## Key Capabilities & Architectural Pillars

- **Zero-Float Physical Core**: All physical quantities, circuit equations, matrices, conductances, and voltages are calculated using exact rationals (`fractions.Fraction`) or arbitrary-precision `Decimal` (50-digit and 80-digit working contexts). Floating-point conversions are banned from physical calculations and verified via automated AST audits.
- **Unified MNA Engine**: Modified Nodal Analysis supporting linear DC, frequency-domain AC steady-state phasors, and damped Newton-Raphson nonlinear DC operating points.
- **Physical Law Verification**: Every solved operating point automatically evaluates and enforces Kirchhoff's Current Law (KCL), Kirchhoff's Voltage Law (KVL), and Tellegen's power balance theorem ($\sum P = 0$) with tolerances down to $10^{-24}$.
- **Semiconductor Physics**: Complete Shockley diode equations and coupled $3 \times 3$ analytical Jacobians for Bipolar Junction Transistors (BJT) under the Ebers-Moll model (both NPN and PNP polarities).
- **External Oracle Cross-Validation**: Automated regression against `ngspice 47` (64-bit) ensures continuous relative agreement $< 10^{-4}$ ($0.01\%$) with industry standard simulators.
- **Full Provenance & Reproducibility**: Deterministic execution digests (SHA-256) recorded for circuit topology, component parameters, and solver states.
- **Defense in Depth**: Zero execution of unsanitized dynamic code (`eval`, `exec`, `compile`, or uncontrolled subprocess calls).

---

## Supported Components & Elements

| Symbol | Name | Domain | Model & Formulation | Reference Document |
|:---:|:---|:---:|:---|:---:|
| **R** | Resistor | DC, AC, NL | Ohm's law: $V = R \cdot I$, conductance stamping $G = 1/R$ | [`GATE-F8B.md`](docs/gates/GATE-F8B.md) |
| **L** | Inductor | AC Phasor | Impedance $Z_L = j\omega L$, reactive power $Q_L = \frac{1}{2}\omega L \vert I\vert^2$ | [`GATE-F8D3.md`](docs/gates/GATE-F8D3.md) |
| **C** | Capacitor | AC Phasor | Admittance $Y_C = j\omega C$, reactive power $Q_C = -\frac{1}{2}\omega C \vert V\vert^2$ | [`GATE-F8D3.md`](docs/gates/GATE-F8D3.md) |
| **V** | Voltage Source | DC, AC, NL | Independent voltage constraint, auxiliary current variable | [`GATE-F8B.md`](docs/gates/GATE-F8B.md) |
| **I** | Current Source | DC, AC, NL | Independent current delivery into nodes | [`GATE-F8B.md`](docs/gates/GATE-F8B.md) |
| **E** | VCVS | DC, AC, NL | Voltage-Controlled Voltage Source ($V_{\text{out}} = \mu \cdot \Delta V_{\text{ctrl}}$) | [`GATE-F8E.md`](docs/gates/GATE-F8E.md) |
| **G** | VCCS | DC, AC, NL | Voltage-Controlled Current Source ($I_{\text{out}} = g_m \cdot \Delta V_{\text{ctrl}}$) | [`GATE-F8E.md`](docs/gates/GATE-F8E.md) |
| **H** | CCVS | DC, AC, NL | Current-Controlled Voltage Source ($V_{\text{out}} = r_m \cdot I_{\text{ctrl}}$) | [`GATE-F8E.md`](docs/gates/GATE-F8E.md) |
| **F** | CCCS | DC, AC, NL | Current-Controlled Current Source ($I_{\text{out}} = \beta \cdot I_{\text{ctrl}}$) | [`GATE-F8E.md`](docs/gates/GATE-F8E.md) |
| **O** | Op-Amp | DC, AC, NL | Ideal operational amplifier (nullor: $V_+ = V_-$, $i_+ = i_- = 0$) | [`GATE-F8F.md`](docs/gates/GATE-F8F.md) |
| **T** | Transformer | DC, AC, NL | Ideal transformer with turns ratio $n$ ($V_1 = n V_2, I_2 = -n I_1$) | [`GATE-F8G.md`](docs/gates/GATE-F8G.md) |
| **D** | Diode | Nonlinear DC | Shockley equation $I_D = I_S(\exp(V_D / n V_T) - 1)$, companion conductance | [`GATE-F8H.md`](docs/gates/GATE-F8H.md) |
| **Q** | BJT | Nonlinear DC | Ebers-Moll model (NPN/PNP), coupled analytical Jacobian matrix $\mathbf{J}_{\text{BJT}}$ | [`GATE-F8I.md`](docs/gates/GATE-F8I.md) |

---

## Phase Ledger & Status

| Phase | Description | Key Deliverables | Status | Gate Report |
|:---:|:---|:---|:---:|:---:|
| **F0** | Foundation & Audit | Architecture baseline, modular monolith design, ADRs (10). | **CERTIFIED** | [`MATRIX.md`](docs/migration/MATRIX.md) |
| **F1** | Domain & Identity | 20 domain entities, deterministic IDs, SQLite storage. | **CERTIFIED** | [`MIGRATION-REPORT-F1.md`](docs/migration/MIGRATION-REPORT-F1.md) |
| **F2** | Resource Engine | Content-Addressable Storage (CAS SHA-256), FTS5 indexing. | **CERTIFIED** | [`F2-REPORT.md`](docs/phase-reports/F2-REPORT.md) |
| **F3** | Document Engine | Canonical AST, Markdown/HTML parsers and renderers, native PDF. | **CERTIFIED** | [`F3-REPORT.md`](docs/phase-reports/F3-REPORT.md) |
| **F4** | Academic Management | Course catalog, topics, tree CRUD, gradebook calculations. | **CERTIFIED** | [`F4-REPORT.md`](docs/phase-reports/F4-REPORT.md) |
| **F5** | Authoring Engine | Structured authoring commands, validation rules, undo/redo. | **CERTIFIED** | [`F5-REPORT.md`](docs/phase-reports/F5-REPORT.md) |
| **F6** | Engineering Foundation | SI units, dimensional quantities, equation parser, netlists. | **CERTIFIED** | [`F6-REPORT.md`](docs/phase-reports/F6-REPORT.md) |
| **F7-A/B**| Simulation Runtime | ngspice backend integration, isolated subprocess execution. | **CERTIFIED** | [`F7-B8-HARDENING-REPORT.md`](F7-B8-HARDENING-REPORT.md) |
| **F8-A** | Electronics Knowledge Core | Circuit topology, models, boundary contracts, validation. | **CERTIFIED** | [`GATE-F8A.md`](docs/gates/GATE-F8A.md) |
| **F8-B** | General Linear DC MNA | Exact rational solver (`fractions.Fraction`) for $R, V, I, E, G, H, F, O$. | **CERTIFIED** | [`GATE-F8B.md`](docs/gates/GATE-F8B.md) |
| **F8-C** | DC Thévenin & Norton | Exact 1-port equivalent circuits via test-source injection. | **CERTIFIED** | [`GATE-F8C.md`](docs/gates/GATE-F8C.md) |
| **F8-D** | AC Small-Signal Phasor Suite | D1–D8: Complex math, complex solver, AC MNA, AC power, sweeps, Bode plots, AC Thévenin/Norton, resonance & Q. | **CERTIFIED** | [`GATE-F8D.md`](docs/gates/GATE-F8D.md) |
| **F8-E** | Linear Dependent Sources | VCVS, VCCS, CCVS, CCCS with cyclic dependency graph detection. | **CERTIFIED** | [`GATE-F8E.md`](docs/gates/GATE-F8E.md) |
| **F8-F** | Ideal Op-Amps | Nullor MNA stamping, singular circuit classification. | **CERTIFIED** | [`GATE-F8F.md`](docs/gates/GATE-F8F.md) |
| **F8-G** | Transformers & Two-Port | Ideal transformers and two-port parameter matrices ($Z, Y, H, ABCD$). | **CERTIFIED** | [`GATE-F8G.md`](docs/gates/GATE-F8G.md) |
| **F8-H** | Shockley Diode DC | Damped Newton-Raphson solver, Shockley companion model. | **CERTIFIED** | [`GATE-F8H.md`](docs/gates/GATE-F8H.md) |
| **F8-I** | BJT Ebers-Moll DC | NPN and PNP models, $3\times 3$ analytical Jacobian, B1–B15 canonical circuits, scaling $N=1..64$, ngspice 47 cross-validation. | **CERTIFIED** | [`GATE-F8I.md`](docs/gates/GATE-F8I.md) |
| **F8-J** | Small-Signal AC | Linearization around DC operating point ($g_m, r_\pi, r_o$). | *Planned* | [`ROADMAP.md`](docs/roadmap/ROADMAP.md) |
| **F8-K** | Additional Semiconductors | MOSFET, JFET, Zener, LED, Schottky, Photodiode models. | *Planned* | [`ROADMAP.md`](docs/roadmap/ROADMAP.md) |
| **F8-L** | Transient Simulation | Time-domain DAE integration (Backward Euler, Trapezoidal, BDF). | *Planned* | [`ROADMAP.md`](docs/roadmap/ROADMAP.md) |
| **F8-M** | Advanced Analyses | DC sweeps, parameter sweeps, sensitivity, Monte Carlo. | *Planned* | [`ROADMAP.md`](docs/roadmap/ROADMAP.md) |
| **F8-N** | Virtual Laboratory | Interactive instruments (multimeter, dual-channel scope, generator). | *Planned* | [`ROADMAP.md`](docs/roadmap/ROADMAP.md) |
| **F8-O** | Metrology Core | GUM uncertainty propagation (Type A, Type B, combined, expanded). | *Planned* | [`ROADMAP.md`](docs/roadmap/ROADMAP.md) |
| **F9–F15**| Academic & AI Platform | Assessment, Mastery, Adaptive Learning, Socratic AI Tutor, Cloud Sync, Desktop App. | *Planned* | [`ROADMAP.md`](docs/roadmap/ROADMAP.md) |

---

## Quickstart

### 1. Environment Setup

```bash
# Clone the repository
git clone https://github.com/Damaga2005/AcademicCore.git
cd AcademicCore

# Create and activate virtual environment
python -m venv .venv
# On Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# On Linux / macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 2. Running Tests

```bash
# Fast unit and regression test suite
pytest -q

# Run nonlinear electronics test suite (F8-H & F8-I: 143 tests)
pytest tests/test_f8h_nonlinear_dc.py tests/test_f8i_bjt.py tests/test_f8i_nonlinear_bjt.py -v

# Run full project test battery (1680+ tests)
pytest -p no:cacheprovider
```

### 3. Basic Usage Example: BJT Operating Point Analysis

```python
from academic_core.domain.engineering.circuit import Circuit, Component
from academic_core.domain.engineering.mna import solve_nonlinear_dc
from academic_core.domain.engineering.units import parse_quantity

# Create a common-emitter amplifier circuit
c = Circuit("common_emitter")
c.add(Component("V1", "V", parse_quantity("12 V"), pins={"+": "vcc", "-": "0"}))
c.add(Component("R1", "R", parse_quantity("220 kohm"), pins={"1": "vcc", "2": "b"}))
c.add(Component("R2", "R", parse_quantity("1 kohm"), pins={"1": "vcc", "2": "c"}))
c.add(Component("Q1", "Q", None, pins={"C": "c", "B": "b", "E": "0"},
                parameters={
                    "polarity": "NPN",
                    "Is": parse_quantity("1e-14 A"),
                    "Bf": parse_quantity("100"),
                    "Br": parse_quantity("1"),
                    "Nf": parse_quantity("1"),
                    "Nr": parse_quantity("1"),
                    "Vt": parse_quantity("0.02585 V"),
                }))

# Solve DC operating point
result = solve_nonlinear_dc(c)

print("Status:", result.status.value)
for nv in result.node_voltages:
    print(f"Node {nv.node}: {nv.voltage}")

for bc in result.branch_currents:
    print(f"Branch {bc.ref}: {bc.current}")

print("Conservation verified:", result.conservation_checks.passed)
```

---

## Repository Structure

```text
AcademicCore/
├── src/academic_core/
│   ├── domain/engineering/
│   │   ├── circuit.py           # Canonical circuit model, components & topology
│   │   ├── units.py             # Physical dimensions, units & exact Quantities
│   │   ├── mna/                 # MNA formulations (problem, solver, dependent, opamp, transformer)
│   │   │   ├── diode.py         # Shockley diode physics & companion models (F8-H)
│   │   │   ├── bjt.py           # Ebers-Moll BJT physics & analytical Jacobian (F8-I)
│   │   │   └── nonlinear.py     # Damped Newton-Raphson nonlinear DC solver
│   │   ├── ac/                  # Small-signal AC phasor engine, power & frequency sweeps
│   │   ├── thevenin/            # DC & AC Thévenin / Norton equivalence reductions
│   │   └── math/                # ComplexLinearProblem, high-precision Gauss elimination
│   ├── domain/academic/         # Curriculum models, subjects, rubrics & mastery
│   ├── engines/                 # Resource, document, authoring & AI engines
│   └── infrastructure/          # SQLite persistence, ngspice discovery & CAS storage
├── tests/                       # Comprehensive test suites (1680+ tests)
│   ├── test_f8h_nonlinear_dc.py # Shockley diode verification battery (69 tests)
│   ├── test_f8i_bjt.py          # BJT physics, Jacobian & region tests (33 tests)
│   └── test_f8i_nonlinear_bjt.py# BJT canonical circuits B1-B15 & scaling (41 tests)
├── docs/
│   ├── gates/                   # Gate certification reports (GATE-F1 through GATE-F8I)
│   ├── roadmap/                 # Complete roadmap and architecture vision (ROADMAP.md)
│   └── migration/               # Historical audit documents and reuse maps
├── pyproject.toml               # Project configuration and tool metadata
├── CHANGELOG.md                 # Semantic version history and phase audit trail
└── README.md                    # Project landing documentation
```

---

## Core Principles

```
BUILD SMALL
VERIFY EVERYTHING
EXTEND THE CORE
KEEP THE SYSTEM DETERMINISTIC
USE AI WHERE IT ADDS VALUE
NEVER LET AI REPLACE VERIFIED KNOWLEDGE
```
