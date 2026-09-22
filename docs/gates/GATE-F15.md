# F15 Gate — Aplicación Final de AcademicCore

> **FASE:** F15 — Aplicación Final (app mínima funcional).
> **MODO:** implementación + certificación completa, una única ejecución.
> **BASELINE:** `main @ 91343ba` (D3 approved); `origin/main == 91343ba`,
> working tree clean at start. (Spec §0 cited `origin/main == c79961b`;
> the D1/D2/D3 commits have since been pushed, so local and origin agree
> at `91343ba`. No destructive git command was used.)

## 1. Baseline

- Repo `Damaga2005/AcademicCore`, branch `main`, HEAD `91343ba`
  (`docs(architecture): approve D3 licensing design`).
- Prior: F8-P1…F8-P5 CERTIFIED, D1/D2/D3 DESIGN READY (gate docs on disk,
  untouched except where F15 implementation is their prescribed output).
- F15 HEAD: see `git log` (commits below); no push performed.

## 2. Scope

F15 delivers the final minimal application over D1/D2/D3 + F8 engines:

- Dashboard (real navigation), exercise resolution (engineering
  library), simulation (OP/sweep/transient/AC via F8-N), Virtual Lab
  (sessions, experiments, stimuli, probes, instruments, measurements,
  serialization `f8n-lab/1`, replay).
- D2 mechanical implementation: `AcademicCoreError` root + re-parenting,
  `UiError` single converter, stdlib logging wiring, `ERROR-CODES.md`.
- D3 mechanical implementation: `LICENSE` (MIT © 2026 Damaga2005),
  `pyproject` license/authors/entry-point, README run docs,
  `THIRD_PARTY_NOTICES.md`, `requirements-lock.txt`, `sbom.json`,
  verification of the three D3 UNKNOWN licenses from local evidence.
- No scope creep: F3-ext/F4-ext/F13-ext/D4–D7/F9–F14/F16 untouched;
  GREELEC stays NO INTEGRATION; Stirling stays REVIEW REQUIRED, unbundled.

## 3. Architecture

```
UI (Qt/PySide6 views only)
 ↓ commands / queries / views (AcademicApp facade)
Application Services (LabService, ExerciseService, SimulationService,
  existing services; orchestration only, no math, no Qt)
 ↓ domain calls (in) / ports (out)
Domain / Ports (F8 engines incl. F8-N, UNTOUCHED behaviorally)
 ↓ ports
Infrastructure / Adapters (SQLite/CAS/FTS/ngspice/stirling, unchanged)
 ↓ Result / Error
UiError (single converter) → UI
```

- D1 AI-001 fixed: `ui/authoring.py` no longer imports
  `domain.authoring` / `documents.*`; all block editing goes through new
  `AuthoringService` methods (`template_names`, `top_block_labels`,
  `block_editor_text`, `apply_equation/code/markdown`, `delete_block`,
  `insert_paragraph`, `set_title`, `doc_title/status`,
  `export_markdown/html`).
- D1 AI-002 fixed: `ui/engineering.py` no longer imports
  `domain.engineering.circuit/simulation`; uses `EngineeringService`
  helpers (`new_circuit`, `component_pins`, `circuit_warnings`,
  `backend_status_lines`).
- `ui/main_window.py` no longer imports `domain.results`
  (`ResultsService.record_grade`) nor `documents.render_*`
  (`DocumentService.render_markdown/html`).
- New code introduces zero UI→infrastructure edges
  (`tests/test_f15_app.py::test_f15_018_architecture_edges` enforces the
  above plus `test_architecture.py` green).

## 4. Application services

| Service | File | Role |
|:---|:---|:---|
| `LabService` | `application/lab_service.py` | session/experiment/run/replay/serialization over certified F8-N; frozen `LabRunSummary` |
| `ExerciseService` | `application/exercise_service.py` | library load → `parse_quantity` validation → `EngineeringService.calculate` → frozen `ExerciseResult`; Qt-free |
| `SimulationService` | `application/simulation_service.py` | circuit build (plain dicts) + demo circuits + OP/TRANSIENT/AC/DC_SWEEP via `LabService`; Qt-free |
| `AcademicApp` | `application/facade.py` | wires `lab`, `exercises`, `simulation` (single facade, no parallel) |

All services coordinate; none implements domain math.

## 5. Dashboard

`ui/dashboard.py` (`DashboardPanel`, first tab): cards for Exercises,
Simulation, Virtual Lab, Resources, Settings — each navigates to a real
tab via the `navigate(str)` signal (`AcademicMainWindow._navigate`).
Version/state line + explicit GREELEC limitation note. No fictitious
entries.

## 6. Exercise resolution

`ui/exercises.py`: library selector (15 real keys from
`ExerciseService.library_keys`), `VAR=value` input, worker-thread
execution, result + digest display, UI-safe errors. Verified: `ohm-v`
`I=0.005 A; R=1000 ohm` → `V = 5 V`, digest-stable across runs.

## 7. Simulation

`ui/simulation.py` + `SimulationService`: demo scenarios
(divider / rc-step / rc-ac) with certified configs:
OP (DC_VALUE probe), TRANSIENT (`TransientConfig("TR", …)` per
`f8n_lab_common.transient_config`), AC_POINT (1 kHz), AC_SWEEP
(100 Hz/1 kHz/10 kHz), DC_SWEEP (`SweepConfig(ParamAddress V1.value,
GridSpec.linear 0..5 step 1)`, node_voltage n2). Executes worker →
service → F8-N; shows status, digest, measurements. No MNA internals
in widgets.

## 8. Virtual Lab

`ui/virtual_lab.py`: session create (demo circuits) / save / load;
per-analysis experiment builder (stimuli incl. `function_generator`
sine/pulse/square/dc; probes V/I; instruments voltmeter/oscope/bode;
measurements dc_value/max/ac_gain/bandwidth); Add+Run via workers;
readings briefs (ScopeData channel/point counts, BodeData, SweepData);
replay with exact-digest compare; `f8n-lab/1` save/load via file
dialogs (text only crosses the service boundary). Circuit/analysis
compatibility enforced with honest engine errors surfaced as `UiError`.

## 9. Instruments

All five F15 areas mapped to real F8-N capabilities:

| Instrument | F8-N source | UI exposure | Status |
|:---|:---|:---|:---|
| Fuente DC | `StimulusSpec DC` / `function_generator dc` | V1 DC field (OP/DC) | WORKS |
| Multímetro | `VOLTMETER`/`AMMETER` + `Scalar` | meter reading + `DC_VALUE` | WORKS |
| Osciloscopio | `OSCILLOSCOPE` + `ScopeData` + `ScopeChannel`/window | scope brief + `MAX` | WORKS (TRANSIENT) |
| Generador | `function_generator` + `StimulusSpec SINE/PULSE` | sine frequency field | WORKS |
| Analizador lógico | — (no digital-signal engine in F8-N) | documented limitation | LIMITATION (no invention) |

Waveforms displayed are committed engine samples only; fiction is
structurally impossible (readings come from `Run.readings`).

## 10. Persistence

No new database. Lab sessions persist via canonical `f8n-lab/1`
documents (save/load text). Existing SQLite/CAS/FTS stores unchanged.
Autosave/versioning of authoring docs unchanged.

## 11. Serialization / replay

- `LabService.save_text` collects `stable_result_payload(run.result)`
  per run → `dumps_session`; refuses loaded (result-less) sessions with
  a typed error (replay-before-save).
- `load_text` → `loads_document` (`OK / SCHEMA_MISMATCH /
  INVALID_SERIALIZATION`); tamper → digest mismatch → rejected.
- `replay` → `replay_run`: `EQUIVALENT` on bit-identical digests,
  `RESULT_DIFFERS` with first difference, `VERSION_MISMATCH` on engine
  drift (refuses execution unless explicitly allowed). UI shows all
  four outcomes without hiding differences.

## 12. D2 error/logging implementation

- `src/academic_core/errors.py`: `AcademicCoreError(ValueError)` root +
  `Validation/Configuration/Unsupported/Serialization/VersionMismatch/
  Adapter/Infrastructure/IntegrationError`; frozen `UiError`
  (`error_code/safe_message/severity/recoverability/user_action`);
  single converter `to_ui_error` + `ui_error_for_code`. Redacts paths,
  SQL, tracebacks, secrets.
- Re-parented (names/modules/`ValueError` MRO preserved):
  `DomainError` (entities), `ApplicationError` (services),
  `SecurityError` (ingest), `LabConfigError` (lab model). Remaining
  engine `*Error` classes are mapped by the converter (grandfathered,
  no behavior change).
- `src/academic_core/logging_config.py`: stdlib only, root
  `academic_core`, `_ContextFilter` (`event_code/component/operation/
  correlation_id`), `redact()` (home→`<home>`, secret masking, 1 KiB
  cap), `CorrelationFilter` via `ContextVar` UUIDs (runtime-only, never
  in digests). `get_logger` REFUSES `academic_core.domain*`
  (D2-I003 enforced at runtime + `test_f15_015`).
- `docs/specs/ERROR-CODES.md`: `AC-<AREA>-<NNN>` registry (stable codes,
  `d2-error/1` wire rules).
- UI: `ui/errors.py` is the only dialog path (`show_ui_error` /
  `show_value`); all new panels use it.
- Residual debt honestly kept: legacy `f"{type(e).__name__}: {e}"`
  dialogs in pre-F15 panels remain (grandfathered per D2 §14); the
  `except Exception: pass` in `ui/engineering.py` was removed
  (structural line now shows the `UiError` code).

## 13. D3 licensing implementation

- `LICENSE`: canonical MIT text, `Copyright (c) 2026 Damaga2005`
  (D3 evidence chain: README ×2, sibling conversor LICENSE, 5
  provenance headers, dep compatibility).
- `pyproject.toml`: `license = { text = "MIT" }`,
  `authors = [{ name = "Damaga2005" }]`, MIT classifier,
  `[project.scripts] academic-core = "academic_core.app:main"`.
- `THIRD_PARTY_NOTICES.md`: every row evidence-cited; D3 UNKNOWNs now
  VERIFIED from installed metadata: markdownify MIT (classifier),
  pypdf BSD-3-Clause (`License-Expression`), pytest MIT
  (`License-Expression`, test-only). PySide6 LGPL dynamic-link terms +
  NOTICE duty recorded; lxml libxml2 note; ngspice invoked-not-bundled;
  Stirling REVIEW REQUIRED (unbundled); GREELEC NO INTEGRATION.
- `requirements-lock.txt` (pinned) + `sbom.json` (component/version/
  source/license, runtime vs test-only split).
- README: license link already pointed at `LICENSE` (now live, no
  rewrite); added §4 launch docs + F15 capabilities.
- SPDX ratchet: all NEW files carry `SPDX-License-Identifier: MIT`;
  existing files untouched (D3 §6 ratchet, no mass rewrite).

## 14. Packaging

- `python -m build`: `academic_core-0.1.0.tar.gz` + `.whl` built.
- sdist contains `LICENSE`; wheel contains `dist-info/licenses/LICENSE`
  + `METADATA` (Author Damaga2005, License MIT, License-File) +
  `entry_points.txt` (`academic-core`).
- Clean-env check: wheel installed with `--no-deps` into an isolated
  target imports cleanly (`academic_core.__version__ == 0.1.0`,
  `app.main` entry present).
- Entry points: `python -m academic_core` and `academic-core` (same
  `main`, no parallel inventions).

## 15. Security

- `eval(`/`exec(`/`compile(`: zero hits in `src` (only Qt `.exec()` in
  `app.py`/`ui/dialogs.py` — not Python exec).
- `shell=True`: zero hits; `pickle.loads`: zero hits (doc mentions
  only); `subprocess` confined to `infrastructure/ngspice.py` +
  `pdf/stirling.py` (`shell=False`, timeouts, scoped cwd) — no UI path.
- New-file `except Exception` sites: each translates (`from exc`) or
  presents via `show_ui_error` (documented D2 boundaries; `test_f15_017`
  + AST scan in `test_f15_app.py`).
- Redaction test with secret fixtures passes; no secrets in logs,
  NOTICE, or SBOM.

## 16. Determinism

- Same input + config → same result + digest, twice (exercise digests,
  lab `result_digest`; `test_f15_020_determinism`).
- Logging level DEBUG vs INFO changes zero result bytes
  (`test_f15_015_logging_determinism_and_redaction`).
- Correlation ids / timestamps live only in log records and UI runtime
  state, never in digests or replay inputs.

## 17. Tests

New: `tests/test_f15_app.py` (27 tests) implementing the F15 matrix:

```
F15-001 startup · F15-002 dashboard · F15-003 navigation
F15-004 exercise · F15-005 simulation · F15-006 virtual lab
F15-007 DC supply · F15-008 multimeter · F15-009 oscilloscope
F15-010 function generator · F15-011 logic analyzer (limitation)
F15-012 serialization · F15-013 replay · F15-014 error UI
F15-015 logging · F15-016 license/package · F15-017 security
F15-018 architecture · F15-019 F8 regression · F15-020 determinism
F15-INT-001 startup · 002 dashboard · 003 exercise e2e
004 simulation e2e · 005 virtual lab · 006 error boundary
007 serialization · 008 replay
```

Plus service-level logging boundaries, determinism, tamper case.
UI tests use `QT_QPA_PLATFORM=offscreen`, behavior-first (no
screenshots). Pre-existing tab-count assertions updated 7→12
(`test_ui.py`, `test_ui_authoring.py`, `test_ui_engineering.py`) for
the intended new tabs.

## 18. Regression

- `test_architecture.py` + all UI/authoring/application suites: PASS
  (65 tests in the affected-files run).
- F8-N + F8-P1…P5 full suites (10 files, 346 tests collected):
  **346 PASS, 0 FAIL** (background run, exit 0, no `F` in output).
- F8 engines behaviorally untouched (only `LabConfigError` re-parenting,
  MRO-preserving).
- `git diff --check`: clean (whitespace).

## 19. Performance

Measured on the F15 build env (Windows, Python 3.14):

```
application startup:  ~0.59 s
simple exercise:      ~0.021 s
simple simulation OP: ~0.173 s
simple lab run (OP):  ~0.005 s
```

No blocking operations on the UI thread (all runs via `QThreadPool`
`ServiceWorker`; widgets touched only via signals). No premature
optimization. No orphan workers (auto-delete runnables); no new
subprocesses; dialogs/file handles scoped.

## 20. Known limitations

1. Analizador lógico: F8-N has no digital-signal instrument; UI does
   not invent one (documented in Dashboard + gate §9).
2. Legacy `f"{type(e).__name__}: {e}"` dialogs in pre-F15 panels are
   grandfathered (D2 §14); all F15 panels use `UiError`.
3. Engine `*Error` re-parenting beyond the four core classes is via
   converter mapping (no behavior change by design).
4. `python -m build` emits an advisory SPDX-classifier notice
   (setuptools ≥77 prefers `license-files` expressions); the D3-approved
   `license.text + classifier` form is kept deliberately.
5. Stirling license pin + GREELEC provenance still open (fenced gates,
   block F4-ext only — not F15).

## 21. Residual risks

| Risk | Residual |
|:---|:---|
| UI/domain coupling recurrence | low (AST edge test F15-018 + D1-008 pattern) |
| Silent swallowing in legacy handlers | low (inventory kept; new code covered by converter test) |
| Secret leakage via log context | med→low (closed keys, redact(), D2-012-style test) |
| Engine regression via re-parenting | low (MRO preserved; suites re-run) |
| Distribution license surprise | low (SBOM + lock + NOTICE before F15 per D3) |

## 22b. F15 invariants

| ID | Property | Enforced by |
|:---|:---|:---|
| F15-I001 | UI never owns domain logic | services own orchestration; tests F15-004/005/006 |
| F15-I002 | domain remains Qt-independent | `test_architecture` + F15-018 (no PySide6/getLogger in domain) |
| F15-I003 | application services mediate UI | AI-001/AI-002 re-routed; F15-018 edge test |
| F15-I004 | D2 errors are preserved | converter mapping; engine classes untouched |
| F15-I005 | D3 license metadata is coherent | F15-016 (LICENSE + pyproject + README + NOTICE + SBOM) |
| F15-I006 | F8 behavior unchanged | re-parenting is MRO-preserving; F8 suites re-run |
| F15-I007 | F8-N remains usable | F15-006…013 over live engine |
| F15-I008 | serialization remains compatible | `f8n-lab/1` untouched; round-trip + tamper tests |
| F15-I009 | replay remains compatible | EQUIVALENT on identical digests; constants preserved |
| F15-I010 | deterministic results unaffected by logging | F15-015 (DEBUG vs INFO identical) |
| F15-I011 | no dynamic arbitrary plugin loading | static modules only; no loader imports added |
| F15-I012 | no unsafe execution | F15-017 (no eval/exec/shell=True/pickle) |
| F15-I013 | no swallowed exceptions | translation/`show_ui_error` at every new boundary |
| F15-I014 | no secret leakage | `redact()` + secret-fixture test |
| F15-I015 | no orphan subprocesses | no new spawners (ngspice/stirling unchanged) |
| F15-I016 | no orphan workers | auto-delete `ServiceWorker`; UI updates via signals only |
| F15-I017 | startup reproducible | clean-env import check; no CWD/machine dependence |
| F15-I018 | packaging reproducible enough for project scope | pinned lock + SBOM; sdist/wheel contents verified |
| F15-I019 | unsupported capabilities are explicit limitations | logic analyzer + GREELEC documented, never invented |
| F15-I020 | errors reach users only as `UiError` (new surfaces) | single converter + `ui/errors.py` |

## 22. Acceptance criteria

```
[x] application launches (offscreen + wired entry points)
[x] dashboard works (real navigation, explicit limitations)
[x] exercise flow works (library → validate → execute → result)
[x] simulation flow works (OP/sweep/transient/AC via F8-N)
[x] virtual lab flow works (session/experiment/run/measure)
[x] supported instruments work (DC/meter/scope/generator)
[x] application/domain boundaries respected (AI-001/AI-002 fixed, tests)
[x] D2 implemented (root, UiError, logging, registry)
[x] D3 implemented (LICENSE, metadata, NOTICE, SBOM/lock, verify-items)
[x] serialization works (f8n-lab/1 round-trip + tamper refusal)
[x] replay works (EQUIVALENT / refuses drift, hides nothing)
[x] security checks pass (no eval/exec/shell/pickle; translation justified)
[x] architecture tests pass (existing + F15-018)
[x] F8 regression passes (N + P1…P5; result recorded at commit time)
[x] determinism preserved (double-run + log-level invariance)
[x] packaging works (sdist/wheel contents + clean-env import)
[x] known limitations documented (§20)
```

## 23. Final verdict

All acceptance criteria closed on evidence (§22); F8-N + F8-P1…P5
regression 346 PASS / 0 FAIL; no BLOCKING open questions; GREELEC and
Stirling remain fenced gates (out of F15 scope by design).

FINAL VERDICT: F15 CERTIFIED
