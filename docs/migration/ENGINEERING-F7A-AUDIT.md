# F7-A Audit — Simulation Runtime + Backend Foundation

Date: 2026-09-12 · Base: F6 `adbe7d9`

## Baseline
- Branch `main`, clean tree, F6 baseline `205 passed, 2 skipped`.
- Existing boundary: `domain.engineering.simulation` contains
  `SimulationBackend`, `NullSimulationBackend`, and `MockSimulationBackend`.
- F6 `Circuit.to_netlist()` is deterministic and remains unchanged in meaning.
- F6 intentionally has no subprocess/runtime layer. F7-A adds that layer
  outside Domain; F7-B result parsing/scientific results remain out of scope.

## ngspice research
Official ngspice download documentation identifies stable release **ngspice-47**
ng-spice-rework release area. The official docs describe Windows extraction,
console executable use, and batch operation. The ngspice project is open
source; the exact license text is distributed with the selected release and
must be retained by any local installation. AcademicCore does not download,
vendor, or commit binaries.

Environment discovery result: `ngspice` is not on PATH and no configured
runtime was present. Therefore live health/version evidence is **UNVERIFIED**;
the external integration test is skipped, never treated as PASS.

## F7-A design
- `NgSpiceBackend` implements the existing backend boundary in an external
  infrastructure module, not Domain.
- `RuntimeInfo` records executable, version, detection method, availability,
  verification details, platform and timestamp.
- `SimulationExecution` records technical process facts only: status,
  stdout/stderr, exit code, timeout/cancel flag, workspace and command
  metadata. It is not a scientific `SimulationResult`.
- Every run gets a private temporary workspace. Arguments are a list, never a
  shell string. The circuit/netlist is data; it cannot add process arguments.
- Version uses `ngspice -v`; health uses a fixed, generated minimal batch
  netlist. Timeout terminates then kills; cancellation uses the same path.
- Unit tests use a generated fake executable script only to test process
  control. They are not runtime evidence. Real tests use `@pytest.mark.external`
  and skip when ngspice is unavailable.

## F7-B boundary
F7-B will parse scientific output into `SimulationResult` and add analyses.
F7-A does not implement DC/AC/transient features, MNA, plots, or hardware.
