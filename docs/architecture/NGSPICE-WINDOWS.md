# ngspice on Windows (F7-A)

AcademicCore does not bundle, download, or commit ngspice. The official
ngspice download page identifies stable **ngspice-47** and the official
Windows 64-bit archive `ngspice-47_64.7z` in the SourceForge
`ng-spice-rework` release area.

1. Download the official Windows archive from the ngspice project page.
2. Extract it to a user-controlled directory.
3. Configure `simulation.ngspice_path`, or put `ngspice.exe` on PATH.
4. Inspect `RuntimeInfo` or the Engineering backend status.

F7-A validates the executable with `ngspice -v`, then runs a fixed batch
health netlist in a private temporary workspace. It records version, path,
cannot add command arguments.

The current environment has no ngspice executable, so the live health check
is `SKIPPED_EXTERNAL` and the runtime certification is `UNVERIFIED`, not
PASS. F7-A does not parse scientific output; that belongs to F7-B.
