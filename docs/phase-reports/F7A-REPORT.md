# F7-A Report — Runtime + Backend Foundation

## Status
**PASS**: Real ngspice 47 runtime detected and verified on Windows (`ngspice_con.exe`). All runtime gates and regression tests pass.

## Implemented
- `NgSpiceBackend`, `NgSpiceDiscovery`, `RuntimeInfo`, `SimulationExecution`.
- Separation of discovery logic from backend execution.
- Windows headless preference: `ngspice_con.exe` detected and prioritized over GUI `ngspice.exe`.
- Configurable executable paths via explicit argument, environment variables (`ACORE_NGSPICE_PATH`, `NGSPICE_PATH`), and settings.
- `ngspice -v` verification, fixed batch health netlist, stdout/stderr/exit capture, timeout, cancellation, isolated temp workspace, and cleanup.
- External integration tests with real ngspice runtime for health check, controlled failure, timeout, cancellation, orphan process prevention, and structured argument security.
- No scientific result parser, no SPICE feature, no F7-B work.

## Evidence
- Unit tests verify process control and edge cases.
- Real ngspice 47 runtime executed directly on Windows.
- Real health check: COMPLETED with exit code 0 and operating point output.
- Real failure: returns FAILED with exit code != 0, never COMPLETED.
- Real timeout: terminated and killed, returns TIMEOUT, workspace cleaned up.
- Real cancellation: terminated, returns CANCELLED, workspace cleaned up.
- No orphaned processes left running.
- Full regression F0–F6 + F7-A green (221 passed, 2 skipped).
