# AcademicCore

Academic engineering core, currently focused on the **electronics linear-circuits engine** (phases F0–F8). Modular monolith (Python), deterministic engines, evidence-gated certification per phase gate in `docs/gates/`.

## Status vocabulary

- **IMPLEMENTED** — code present in the working tree.
- **VERIFIED** — covered by tests with independent oracles where applicable.
- **BENCHMARKED** — measured (performance) with recorded numbers.
- **CERTIFIED** — phase gate declares PASS/CERTIFIED with evidence.
- **SIMULATED** — validated against the external ngspice 47 integration (not vendored).
- **EXPERIMENTAL** — present but not certified.
- **OUT OF SCOPE** — explicitly not part of any certified phase.

## Phase ledger (working tree at `main`)

| Phase | Capability | Status |
|---|---|---|
| F0 | Foundation: canonical model, MATRIX/ROADMAP, architecture docs/ADRs (no phase gate file) | IMPLEMENTED |
| F1 | Identity, SQLite (no ORM), grading, schedules, validation UI | CERTIFIED (`GATE-F1.md`) |
| F2 | Resources: CAS SHA-256, adapters, FTS5, Resources tab | CERTIFIED (`GATE-F2.md`) |
| F3 | Document engine (AST/parsers/renderers/provenance) + PDF (pypdf native; Stirling external, optional) | CERTIFIED (`GATE-F3.md`) |
| F4 | Academic management (tree CRUD, gradebook, queries, JSON I/O) | CERTIFIED (`GATE-F4.md`) |
| F5 | Authoring engine (deterministic commands, undo/redo, validation, search) | CERTIFIED (`GATE-F5.md`) |
| F6 | Engineering foundation (Decimal quantities/units/dimensions, equations, topology/netlists, persistence) | CERTIFIED (`GATE-F6.md`) |
| F7-A | Electronics knowledge base | CERTIFIED (`GATE-F7A.md`) |
| F7-B | Simulation suite (transient/AC/noise/Monte Carlo/GUM/structural); ngspice-backed | CERTIFIED (`GATE-F7B8.md`) |
| F8-A | Electronics knowledge core (concepts/models/applicability; no semiconductors) | CERTIFIED (`GATE-F8A.md`) |
| F8-B | General DC linear MNA solver (R, V, I, E/G/H/F, O; exact rationals) | CERTIFIED (`GATE-F8B.md`) |
| F8-C | General DC Thevenin/Norton (test-source method; active networks) | CERTIFIED (`GATE-F8C.md`) |
| F8-D1 | Complex mathematics (exact + high-precision) | CERTIFIED (`GATE-F8D1.md`) |
| F8-D2 | Complex linear solver | CERTIFIED (`GATE-F8D2.md`) |
| F8-D3 | General AC MNA (steady-state phasors, peak, `e^(+jωt)`) | CERTIFIED (`GATE-F8D3.md`) |
| F8-D4 | AC power (absorbed convention, Tellegen) | CERTIFIED (`GATE-F8D4.md`) |
| F8-D5 | AC impedance/admittance/transfer/sweep (test-source method) | CERTIFIED (`GATE-F8D5.md`) |
| F8-D6 | Log-frequency/Bode (dB, unwrap, cutoff brackets, bandwidth intervals) | CERTIFIED (`GATE-F8D6.md`) |
| F8-D7 | General AC Thevenin/Norton | CERTIFIED (`GATE-F8D7.md`) |
| F8-D8 | AC resonance & quality factor (bracket-only verdicts, energy-Q) | CERTIFIED (`GATE-F8D8.md`) |
| F8-E | Linear dependent sources VCVS/VCCS/CCVS/CCCS (DC + AC + power + transfer + Thevenin/Norton) | CERTIFIED (`GATE-F8E.md`) |
| ngspice 47 | EXTERNAL integration only (`ngspice_con.exe`, not vendored); comparison oracle, never authority | SIMULATED |
| F8-F | Ideal op-amps, nullor MNA (DC exact + AC phasor, solver-classified singularities) | CERTIFIED (`GATE-F8F.md`) |
| Beyond F8-F (BJT/MOSFET, nonlinear, transient-nonlinear, finite-gain/GBW/saturation) | Not started | OUT OF SCOPE |

Full suite (working tree): **1477 collected = 1475 passed + 2 skipped** (`pytest -p no:cacheprovider`; the 2 skips are the pre-existing reportlab skips). Per-phase evidence lives in each gate document; do not reuse older totals as evidence for the current tree.

## Known limitations (certified scope boundaries)

- The F6 netlist format covers basic structure only. Serialization/persistence of the E/G/H/F control parameters is out of scope: circuits with dependent sources are **not** netlist roundtrip-complete (`tests/test_f8e_netlist_limitation.py` pins this behavior).
- DC excludes L/C by certified rule (F8-B domain is R/V/I/E/G/H/F/O).
- `Component` is frozen at attribute level; contained `pins`/`parameters`/`metadata` dicts are never mutated by any engine (audited — see the KNOWN ARCHITECTURAL DEBT note on `Component` in `circuit.py`), but Python-level deep immutability is not enforced and no refactor is planned without a demonstrated defect.
- ngspice current sources use the opposite reference direction to the academic I-convention (delivered INTO "+"); oracle decks apply the documented mapping. The academic model is authoritative.
- F8-D8 reports resonance brackets/candidates, never interpolated resonance frequencies; energy-Q only where defined.
- Only part of the working tree is committed to git (tracked: gates through F8-E, F8-E engine files, F8-E tests); the D1–D8 engine sources and phase tests live in the working tree (Syncthing-synced). Reproduce from the working tree, not from git objects alone.

## Quickstart (Windows)

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pytest -m "not migration"      # fast loop
pytest -p no:cacheprovider     # full suite (evidence)
python -m academic_core        # minimal native window (Qt)
python -m academic_core --config=config.json
```

Headless smoke: `$env:QT_QPA_PLATFORM="offscreen"; python -m academic_core`.

## Tree (abridged)

```text
src/academic_core/  app.py  config/  domain/  storage/  engines/
                    infrastructure/  application/
src/academic_core/domain/engineering/
                    circuit.py  units.py  mna/  thevenin/  ac/  math/
                    simulation.py (ngspice-backed analyses)
tests/  per-phase suites incl. test_f8b*, test_f8c*, test_f8d*,
        test_f8e_dependent_sources.py, test_f8e_netlist_limitation.py
docs/   architecture/  adr/ (x16)  migration/  domain/  security/
        testing/  roadmap/  gates/ (F1–F8-E)  phase-reports/
```

No claims beyond the gates above. No marketing metrics: every number here traces to a gate, a test run, or git history.
