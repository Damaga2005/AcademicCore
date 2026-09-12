# GATE F7-B1 — Simulation Result + Signal + DC Operating Point

## Result: PASS

- [x] SimulationResult and Signal domain models
- [x] Separation of solver float precision and domain Decimal precision
- [x] SimulationJob netlist deck builder
- [x] Structured output parser for ngspice .op tables (voltages and currents)
- [x] Parser error detection and diagnostics extraction
- [x] CAS raw artifact hash reference
- [x] Full execution pipeline: Circuit → Netlist → SimulationJob → NgSpiceBackend → Parser → SimulationResult
- [x] Real scientific simulation with ngspice 47 (`ngspice_con.exe`)
- [x] Scientific validation of voltage divider and Ohm's Law
- [x] F7-B1 unit and integration tests: 12 passed
- [x] Full regression suite F0–F6 + F7-A + F7-B1: 233 passed, 2 skipped

F7-B1 is certified PASS. F7-B2 has not started.
