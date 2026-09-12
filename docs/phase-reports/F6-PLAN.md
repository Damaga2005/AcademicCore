# F6-PLAN — Engineering Foundation

Date: 2026-09-12 · Base: F5 `a915ce7` (174 passed, 2 skipped; tree clean)

## Pre-work (done)
`ENGINEERING-F6-AUDIT.md` (qué se reutiliza: conceptos; `eval()` del
Conversor explícitamente rechazado) + `F6_ENGINEERING_DESIGN.md` (capas,
quantities, equations seguras, circuito, frontera F7/F8).

## Build order
1. `domain/engineering/units.py`: dimensiones SI, tabla unidades+prefijos,
   `Quantity` Decimal, parsing, aritmética dimensional, conversiones.
2. `domain/engineering/equations.py`: lexer/parser propio, AST, evaluador
   seguro (whitelist), chequeo dimensional LHS/RHS.
3. `domain/engineering/calc.py`: Calculation/CalculationResult + provenance +
   librería de ecuaciones re-derivadas.
4. `domain/engineering/circuit.py`: Component/Pin/Net/Circuit, validación
   topológica, netlist determinista + parser, `EngineeringProject`.
5. `domain/engineering/models.py`: R/C/L/V/I/D/Q + `simulation.py`:
   `SimulationBackend`, `NullBackend`, `MockBackend`.
6. Migración `010_engineering.sql` + repos (`EngineeringRepository`) +
   `application/engineering.py` (proyectos/circuitos/cálculos, doc_links
   `calculation`/`circuit`).
7. `ui/engineering.py` tab + wiring en main_window + facade.
8. Tests: quantities/equations/calc/circuit/netlist/persist/prov/security/
   UI/perf/edges + arch (domain ⊄ Qt/subprocess/filesystem).
9. Docs: F6-REPORT, GATE-F6, README/CHANGELOG.

## Out
SPICE/ngspice/MNA/transient/AC/DC-sweep/MC/GUM/SCPI/hardware/CAD/KiCad/
LTspice/RAG/AI/OneDrive/installer/plugins. `render`/simulación: NOT IMPLEMENTED.
