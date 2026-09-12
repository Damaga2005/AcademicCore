# F6-REPORT — Engineering Foundation

Date: 2026-09-12 · Base: F5 `a915ce7`

## Delivered
- `domain/engineering/units.py`: Decimal quantities, SI prefixes, named
  dimensions, exact conversions, dimensional arithmetic.
- `domain/engineering/equations.py`: explicit recursive parser/evaluator;
  whitelist functions only; no `eval`, `exec`, imports or process execution.
- `domain/engineering/calc.py`: deterministic Calculation/CalculationResult,
  input provenance, engine version, digest, and basic electrical equations.
- `domain/engineering/circuit.py`: project/circuit/component/pins/nets,
  topology warnings, deterministic netlist and parser round-trip.
- `domain/engineering/models.py`: typed R/C/L/V/I/D/Q model metadata and
  validation. No physical simulation.
- `domain/engineering/simulation.py`: F7 boundary only, Null and Mock backends.
  No SPICE, ngspice, MNA, subprocess, or binary installation.
- Migration `010_engineering.sql`, `EngineeringRepository`, service facade,
  Authoring links for `calculation` and `circuit`, and Engineering UI tab.

## Source audit
`docs/migration/ENGINEERING-F6-AUDIT.md`: Conversor concepts selectively
re-derived; its Tk/eval GUM implementation rejected. Sistemes provenance
principles retained. No source repository modified.

## Deliberate limits
Simulation is **NOT IMPLEMENTED** and remains F7. GUM/Monte Carlo,
hardware, SCPI, CAD/KiCad/LTspice and MNA remain out of scope.
