# F7-A Report — Runtime + Backend Foundation

## Status
**UNVERIFIED** for real ngspice runtime: no ngspice executable is installed
in this environment. Unit infrastructure is implemented and verified.

## Implemented
- `NgSpiceBackend`, `RuntimeInfo`, `SimulationExecution`.
- Explicit path → PATH → documented known Windows install locations.
- `ngspice -v` verification, fixed batch health netlist, stdout/stderr/exit
  capture, timeout, cancellation, isolated temp workspace and cleanup.
- Configuration: `simulation.ngspice_path`, timeout, integration flag.
- External integration test is separate and skips when unavailable.
- No scientific result parser, no SPICE feature, no F7-B work.

## Evidence
- Unit tests use patched process objects strictly for process-control behavior;
  they are not runtime evidence.
- External test status: `SKIPPED_EXTERNAL` because `ngspice` is not on PATH.
- Official release research: stable ngspice-47 / official Windows archive;
  no binary downloaded or committed.
