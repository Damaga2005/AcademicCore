# F7-A Audit — Simulation Runtime + Backend Foundation

Date: 2026-09-12 · Base: F6 `adbe7d9`

## Baseline
- Branch `main`, clean tree, F6 baseline `205 passed, 2 skipped`.
- Existing boundary: `domain.engineering.simulation` contains
  `SimulationBackend`, `NullSimulationBackend`, and `MockSimulationBackend`.
- F6 `Circuit.to_netlist()` is deterministic and remains unchanged in meaning.
- F6 intentionally has no subprocess/runtime layer. F7-A adds that layer
  outside Domain; F7-B result parsing/scientific results remain out of scope.

## ngspice Runtime Verification
Official ngspice release **ngspice-47** installed on Windows.
The headless console executable `ngspice_con.exe` is detected and preferred over the GUI variant `ngspice.exe` on Windows to guarantee headless execution without window popups or hanging interactive prompts.

### Discovery
- Runtime discovery is cleanly separated in `NgSpiceDiscovery`, respecting the `SimulationBackend` abstraction.
- Discovery order: explicit argument → environment variables (`ACORE_NGSPICE_PATH`, `NGSPICE_PATH`) → `Settings` configuration → PATH → standard system installations → user home / archive extractions.
- On Windows, `ngspice_con.exe` is discovered and preferred.
- Executable detected: `ngspice_con.exe`
- Version reported by runtime: `47` (`ngspice-47`)
- Exit code on `-v`: `0`

### Unit Verification
- Fake process objects verify process handling logic, status transitions, input validation, NUL byte rejections, and version parsing in isolation.
- Unit tests pass without requiring an external runtime.

### External Runtime Verification
- Real ngspice process executed directly via `NgSpiceBackend` and `NgSpiceDiscovery`.
- Executable verified: valid binary, version 47 confirmed from real stdout banner.
- Process starts, runs batch mode with `-b -o output.log input.cir`, captures stdout, stderr, and exit code.

### Real Health Check
- Netlist: fixed minimal `.op` batch netlist (`HEALTH_NETLIST`).
- Mode: batch (`-b`), non-interactive, headless.
- Result: status `COMPLETED`, exit code `0`, stderr empty, stdout contains `ngspice-47 done` and analysis operating point records.
- Workspace: temporary directory safely cleaned up upon completion (`keep_workspace=False`).

### Real Failure
- Netlist: invalid netlist (`* invalid\nR1 in\n.end\n`).
- Result: status `FAILED` (exit code `1`), never `COMPLETED`/`PASS`.
- Error diagnostic captured from ngspice log: `Error: incomplete or empty netlist`.
- Workspace: temporary directory safely cleaned up on failure.

### Real Timeout
- Executed against real ngspice running an extended loop in `.control`.
- Timeout trigger: configured `timeout_seconds=0.5`.
- Result: process terminated and killed upon expiration, status transitions to `TIMEOUT`.
- Cleanup: workspace safely removed, no orphaned processes left running.

### Real Cancellation
- Executed against real ngspice running an extended loop in `.control`.
- Cancellation trigger: background thread invokes `backend.cancel()`.
- Result: process terminated, status transitions to `CANCELLED`, `cancelled` flag set to `True`.
- Cleanup: workspace safely removed, no orphaned processes left running.

### Security
- Arguments passed as structured tuple/list (`shell=False` strictly enforced).
- Working directory isolated to a private temporary workspace per execution.
- Path validation and NUL character rejection enforced before subprocess launch.
- No arbitrary command execution or shell interpolation permitted.

### Regression
- F7-A unit tests: `8 passed`
- F7-A real integration tests: `8 passed` (total 16 passed in `test_f7a_runtime.py`)
- Full test suite regression (F0–F6 + F7-A): `221 passed, 2 skipped` (skipped: optional reportlab and live stirling bootstrap).

---

NGSPICE:
47

RUNTIME:
real Windows executable

REAL HEALTH CHECK:
PASS

REAL TIMEOUT:
PASS

REAL CANCELLATION:
PASS

SECURITY:
PASS

REGRESSION:
PASS

---

## Gate Verdict

F7-A STATUS: PASS

All gates verified against real ngspice-47 Windows runtime.
F7-B has not started.
