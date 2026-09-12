# GATE F7-B2 — DC Sweep Real con ngspice

## Result: PASS

- [x] DCSweepAnalysis domain model and parameter validation
- [x] Detection of invalid steps (zero step, mismatched range/step signs)
- [x] Deterministic SPICE deck generation (.dc and automated .print dc cards)
- [x] Multi-point Signal representation with sweep axis
- [x] Separation of solver float precision and domain Decimal precision
- [x] Structured multi-point parser for ngspice DC transfer characteristic tables
- [x] CAS raw artifact reference and provenance metadata
- [x] Real DC Sweep Validation A: Resistive divider V1 = 0..10V, step = 1V, Vout = Vin / 2
- [x] Real DC Sweep Validation B: Symmetric range (-5..5V, step 0.5V, 21 points, extrema, current signal)
- [x] Full pipeline integration: Circuit → Netlist → SimulationJob → NgSpiceBackend → Parser → SimulationResult
- [x] F7-B2 specific tests: 11 passed
- [x] Total Phase 7 tests: 39 passed
- [x] Full regression suite (F0–F6 + F7-A + F7-B1 + F7-B2): 244 passed, 2 skipped

F7-B2 is certified PASS. F7-B3 has not started.
