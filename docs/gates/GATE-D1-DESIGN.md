# D1 Design Gate — Arquitectura de módulos y plugins

Documentation only: no code under `src/` was created or modified, no
tests were written, no engine was altered, no UI was built, no
repository was fused. The only output of this phase is this file plus
one local commit (no push).

## 1. Baseline

- Repository `Damaga2005/AcademicCore`, branch `main`, baseline **`c79961b`**
  (`feat(engineering): certify F8-P5 satcom synthesis`),
  `HEAD == origin/main == c79961b` (verified at audit time; working tree clean).
- Certified at baseline: F0–F7, F8-A … F8-P5 (gates on disk through
  `GATE-F8P5.md`; roadmap §6.1 lists F8-P5 CERTIFICADO and closes F8;
  next per §5.1: decisions D1 [12º] → D2 [13º] → D3 [14º] → F15 [15º]).
- Roadmap authority for D1 (:213): `Arquitectura de módulos/plugins —
  Manifiesto común antes de fusionar GestionAcademicaGREELEC.exe, el
  conversor y AcademicCore`. Strict order, no parallelism without
  explicit decision.

## 2. Scope

D1 decides, on evidence from the existing code: module taxonomy,
plugin strategy, module manifest schema, dependency rules (DAG),
UI/application/domain/adapter/persistence/serialization boundaries,
versioning, determinism, security model, F8 + F8-N integration shape,
academic/knowledge integration shape, external-adapter mapping,
configuration/events/commands shape, D2/D3/F15 boundaries, invariants,
risks, test plan. D1 implements nothing.

## 3. Roadmap authority

| Row | Content | Status |
|:---|:---|:---|
| :213 D1 | module/plugin architecture; common manifest before fusing GREELEC + conversor + core | THIS GATE |
| :214 D2 | logging/errors standard; replaces conversor `except Exception: pass` | boundary only (§27) |
| :215 D3 | single license; conversor already MIT | boundary only (§28) |
| :216 F15 | final app; deps D1+D2+D3+all F8; Qt/PySide6 dashboard/exercises/simulation | prerequisites only (§29) |
| :217 F3-ext | HTML→MD/LaTeX conversor engine (Tkinter-decoupled) | adapter target (§22) |
| §6.2 note | F8 closed; next is D1/D2/D3 | confirmed |

## 4. Current architecture

Verified by inspection at baseline (all paths under `src/academic_core/`):

| Layer | Packages | Role (observed) |
|:---|:---|:---|
| entry | `app.py`, `__main__.py`, `__version__` | thin wiring: settings → facade → Qt window; no logic |
| ui | `ui/{main_window,dialogs,engineering,authoring}.py` | Qt views; `authoring.py` imports `domain.authoring` + `documents.*` directly, and `engineering.py` lazily imports `domain.engineering.circuit` (`Circuit` :136, `COMPONENT_PINS` :156) + `domain.engineering.simulation` (:230) inside handlers; `main_window.py` imports `domain.results` (:317). All are UI→domain shortcuts routed via services in F15 (issues AI-001/AI-002, §10). `test_architecture.test_ui_consumes_only_application_and_domain` permits ui→domain but forbids ui→infrastructure — the D1 rule tightens this to ui→application only |
| application | `application/{facade,services,academic_io,assessment,authoring,backup,documents,engineering,ingest,queries,search,security}.py` | services over domain+repos; `AcademicApp` facade; `AcademicQueries`; no Qt (verified) |
| domain | `domain/{academic,assessment,authoring,entities,grading,identity,ports,resources,results,schedule,status,conflicts,electronics,eo?,engineering,knowledge?}` + `documents/`, `engines/` | pure logic; `ports.py` ABCs (BlobStore/ResourceExtractor/ResourceIndexer/ResourceRecords); `resources/adapters.py` implements ports (LocalFileAdapter, kind/name/version) |
| infrastructure | `infrastructure/{repositories,database,cas,assessment,authoring,engineering,ngspice,ngspice_parser,resources}.py` | SQLite repos, CAS store, ngspice backend (`shell=False`), FTS indexer |
| storage/config | `storage/store.py`, `config/settings.py` | layered config (defaults < file < `ACORE_*` env < overrides), closed dataclasses |
| engines/pdf | `engines/*`, `pdf/{engine,stirling}.py` | provider/document backends; stirling spawns local Java (`shell=False`) |
| f8 engines | `domain/engineering/{mna,ac,lab,metrology,control,dsp,rf,comms,satcom,…}` | certified math; canonical versioned serialization per engine |

Facts constraining the design:

- **No plugin system exists**: zero `plugin` hits in `src/`; no
  `entry_points`, no `pkgutil`; sole `importlib` use is
  `importlib.resources` (static data, not code loading).
- **Ports-and-adapters already exists**: `domain/ports.py` ABCs +
  `resources/adapters.py` with `kind/name/version` per adapter — the
  manifest pattern (§8) generalizes this proven shape.
- **UI→Domain direct reads exist** (`ui/authoring.py` → `domain.authoring`,
  `documents.*`; `ui/engineering.py` → `domain.engineering.circuit/simulation`
  via lazy method-level imports; `ui/main_window.py` → `domain.results`);
  F15 must route through services. `test_architecture.py` currently PERMITS
  ui→domain and only forbids ui→infrastructure — D1 tightens the rule
  (D1-008) without breaking the existing test.
- **`subprocess` is confined** to `infrastructure/ngspice.py` and
  `pdf/stirling.py` (`shell=False`, timeouts); no `eval/exec/compile/
  os.system/shell=True/pickle` anywhere in `src/` (only Qt `.exec()`
  and `re.compile` false positives — §43 audit).
- **`except Exception` is pervasive but handled** (ingest degrades with
  provenance, UI reports, parsers degrade); D2 standardizes it, D1 only
  bounds it (§29). The roadmap-cited `except Exception: pass` belongs
  to the EXTERNAL conversor repo, not to `src/documents` (no bare-pass
  found in-repo).
- **GestionAcademicaGREELEC**: zero references repo-wide → UNKNOWN /
  REQUIRES INPUT (§22/§32). Nothing about it may be assumed.
- **Conversor**: in-repo engine `documents/conversor_*` (images, math,
  sanitize, tables) + external `Conversor-HTML-A-MD` repo (MIT, :217)
  → adapter target, not core.

## 5. Target architecture

```text
                    ┌──────────────────────┐
                    │      F15 UI          │
                    │     Qt/PySide6       │  views only; Qt signals local
                    └──────────┬───────────┘
                               │ commands / queries / views
                               ▼
                    ┌──────────────────────┐
                    │ Application Layer    │
                    │ Services + Facade    │  orchestration; ports out
                    └──────────┬───────────┘
                               │ domain calls (in) / ports (out)
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
       Academic           Engineering        Knowledge/
       Domain             Domain             Documents
              │                │                │
              │  MNA/AC/transient/lab/metrology │
              │  control/DSP/RF/comms/satcom    │
              └────────────────┼────────────────┘
                               │ ports (BlobStore, Records, Indexer,
                               ▼        SimulationBackend, …)
                    ┌──────────────────────┐
                    │ Infrastructure       │  SQLite/CAS/FTS/ngspice
                    │ + Adapters           │  file/md/pdf/conversor/
                    └──────────────────────┘  onedrive-future

              Manifest registry (static, §8) describes every module.
```

This matches the existing code: entry→facade→services→domain/ports→
infrastructure is already how `app.py` + `AcademicApp` +
`EngineeringService` + `EngineeringRepository` are wired. D1
formalizes it and closes the two gaps (UI→domain shortcut, §10;
unregistered future modules, §8).

## 6. Module taxonomy

| Kind | Owns | Examples |
|:---|:---|:---|
| `domain-module` | math/physics/solvers, pure values, versioned serialization contracts | `engineering.mna`, `engineering.lab`, `control`, `dsp`, `rf`, `comms`, `satcom`, `academic`, `assessment` |
| `application-service` | orchestration, repos via ports, reports/views | `EngineeringService`, `IngestionService`, `AcademicApp` facade |
| `adapter` | port implementation, external process/file/format | `LocalFileAdapter`, `NgSpiceBackend`, `FileBlobStore`, future conversor/GREELEC/OneDrive adapters |
| `infrastructure` | SQLite/CAS/FTS mechanics behind ports | `AcademicRepository`, `Database`, `FtsResourceIndexer` |
| `ui-view` | Qt presentation/control only | `main_window`, `dialogs`, `engineering` (shell), `authoring` (to be re-routed) |
| `plugin` (static) | = any of the above, registered in the manifest registry | future fused modules arrive as `plugin` entries, same rules |

No other kinds. A module has exactly one kind.

## 7. Plugin strategy

**Decision: A — static internal modules. B (dynamic discovery) is OUT.**

Justification (evidence, not taste):

1. Zero discovery machinery exists (no entry_points/pkgutil/loader);
   B would be new attack surface, not reuse.
2. Determinism (§17): static registry = fixed order, no filesystem/
   environment dependence. B risks unordered discovery.
3. Security (§18/§24): importing arbitrary third-party code cannot be
   sandboxed in CPython; B without a sandbox is a false promise. A
   keeps the trust boundary at code review + tests.
4. Traceability: every fused module arrives as reviewed source with
   tests and a manifest entry — the roadmap's "manifiesto común" is a
   description of static modules, not a loader protocol.
5. External code (conversor repo, GREELEC, OneDrive client) integrates
   as `adapter`/`plugin(static)` source or as spawned processes behind
   adapters (ngspice/stirling precedent) — never as runtime-discovered
   code.

## 8. Manifest schema

Generalizes the proven `ResourceExtractor.kind/name/version` shape
(`resources/adapters.py:49-56`). Each module package exposes
`manifest()` returning a frozen `ModuleManifest`:

```text
required: module_id (dotted, e.g. "engineering.virtual_lab")
required: name (human)
required: version (module version, §16)
required: api_version (major contract, §16)
required: kind (taxonomy §6)
required: dependencies (list of module_id, static, cycle-checked)
required: capabilities (closed string set declared by kind)
required: serialization_schemas (list, e.g. ["f8p3-rf/1"])
required: minimum_core_version
required: determinism (true + method note)
required: security_policy ("domain-pure" | "spawns-process:X" | "reads-files:scoped")
optional: maximum_core_version
optional: configuration_schema (closed key set + types)
```

Validation rules: unknown keys rejected; `dependencies` must resolve
inside the static registry (dangling → INVALID); cycles → INVALID
(checked at registry build, deterministically ordered); manifest text
is data (JSON-equivalent) — parsing it never executes code (D1-I004).

Static registry: `application/modules.py` (new in D1 implementation,
not this phase) holds the ordered tuple of manifests; order is
authored, never scanned.

## 9. Dependency rules

```text
ALLOWED:  ui-view → application-service
          ui-view → (Qt only + dialogs/views)
          application-service → domain-module
          application-service → ports
          adapter → ports
          infrastructure → ports
          domain-module → math/units/stdlib (existing DAGs)
          entry → config + facade + ui root
FORBIDDEN: domain-module → ui-view / Qt / plugin-loader / filesystem /
           network / subprocess
          application-service → Qt widgets / concrete adapters
          ui-view → domain internals (services own orchestration;
                   read-models via application queries)
          adapter → domain internals beyond ports
          any → dynamic code loading for module wiring
```

Enforcement: extend `tests/test_architecture.py` with D1 edge tests
(D1-001/D1-002/D1-009); existing N-110-style tests keep passing.

## 10. UI boundary

- Domain never imports Qt (tested today; D1-008 extends to P1..P5 +
  lab explicitly).
- Application never depends on concrete widgets (holds today).
- UI consumes application services/queries; the existing
  `ui/authoring.py → domain.authoring` shortcut is recorded as
  architectural issue **AI-001**, and the `ui/engineering.py → domain.engineering.circuit/simulation`
  lazy imports (`Circuit`, `COMPONENT_PINS`, `NullSimulationBackend`) as
  **AI-002**, both to be re-routed in F15 (service methods already exist:
  `AuthoringService`, `EngineeringService.save_circuit/add_component/analyze_circuit`).
  `ui/main_window.py → domain.results` (:317) falls under the same rule. No engine change needed.
- `ui/engineering.py` (shell today) becomes the F15 lab/sim views;
  instrument widgets (Oscilloscope/Generator/Multimeter/LogicAnalyzer)
  carry NO math: they render `Measurement`/series values and send
  commands (§12, §24-25).
- Transport: commands in / results+reports out / queries return views;
  progress/errors as values; Qt signals stay inside `ui/` (§26).

## 11. Application boundary

Services orchestrate; ports go out; repos come in via constructor
(`EngineeringService(repo, …)` precedent — no globals). Commands
return report objects; queries return view dataclasses; both frozen.
`AcademicApp` facade remains the single UI entry (`app.py` wiring
unchanged in shape).

## 12. Domain boundary

Pure values + certified algorithms + versioned serialization
contracts. No filesystem, no clock, no RNG (seeds explicit), no
network, no Qt, no loader. F8 engines additionally: no second engines,
AST-pinned (existing gates). Domain errors are typed values; logging
and presentation of errors live outside (§29).

## 13. Adapter boundary

Adapters implement ports and translate external unruliness into typed
domain outcomes (degrade-with-provenance precedent:
`resources/adapters.py`, `ingest.py:122`). Adapters never contain
domain math. External processes (ngspice/stirling precedent) run with
`shell=False`, timeouts, cwd-scoped workspaces. New adapters
(conversor-fusion, GREELEC-if-any, OneDrive): same contract.

## 14. Persistence boundary

`domain → no filesystem` (tested). `application → ports/repos`
(constructed-in). `infrastructure → implementation` (SQLite/CAS/FTS).
F8 engines persist only via canonical documents through application
services — engines never open files. `storage/store.py` +
`infrastructure/*` remain the only writers. No new store in D1.

## 15. Serialization boundary

Registry (static table, D1 implementation): schema → owning module →
validator/loader. Rules: schema strings `"name/N"`; `N` bump =
breaking (migration required, old loader kept or explicit INVALID);
payloads closed (unknown fields rejected — P2..P5 precedent); digests
recomputed on load; tamper → INCONSISTENT. Existing `f8*/1` contracts
untouched (D1-I006).

## 16. Versioning

Quad: `core (pyproject) / module.version / api_version /
serialization N`. Semantics: `major` = breaking contract (api_version
bump, schema N bump); `minor` = additive, backward-compatible;
`patch` = behavior-preserving fix. Compatible iff
`minimum_core_version ≤ core ≤ maximum_core_version` (when declared)
AND `api_version` equal AND schema `N` supported by the loader.
No blind SemVer: the `name/N` convention already in use IS the
serialization major.

## 17. Determinism

Static registry order; no directory scans; no env vars in wiring
(config values are data, `ACORE_*` only selects files); no clock/RNG
in domain paths; canonical JSON (`str()` Decimals, sorted keys —
repo precedent); digests over canonical form. Module load order is
authored and asserted by test (D1-004).

## 18. Security

Model: static code reviewed + tested (no runtime trust decisions).
Manifests are data (D1-I004). Deserialization closed/typed digested
(P2..P5 precedent extended to any new module). `subprocess` only in
infrastructure adapters (`shell=False`, timeouts, scoped cwd —
ngspice/stirling precedent; no new spawners without a gate).
Banned repo-wide in new D1/F15 code (same list as P2..P5):
`eval/exec/compile/getattr/setattr/open/subprocess/pickle/marshal/
importlib/socket/urllib/numpy/scipy/math` (+`os.system/shell=True`),
with the Role principle: domain gets the strict subset (no `open`
at all), adapters get file/process rights narrowly. Audit method:
§43 greps + AST edge tests (D1-002/D1-010).

## 19. F8 integration

Each engine exposes four stable surfaces (already true; D1 pins them):

```text
public API   package __init__ exports (e.g. forward_budget, modulate…)
internal API submodule functions (callable but not UI-facing)
serialization API  <report>.{dumps,loads,compare,replay} + SCHEMA
UI adapter API     NONE YET — F15 adds application-level adapters;
                   engines are never imported by ui/ (D1-008)
```

Engines: MNA/AC/transient/sweep/sensitivity/MC (F7/F8-A..M),
lab (F8-N), metrology (F8-O/GUM), control (P1), dsp (P2), rf (P3),
comms (P4), satcom (P5). No engine is modified for F15; adaptation
happens in application services (EngineeringService precedent).

## 20. F8-N integration

```text
F15 Lab View (Qt)
  ↓ commands/queries
Lab Application Service (F15-new, application/)
  ↓ engine calls
F8-N Lab Engine (domain/engineering/lab: session/experiment/run/…)
  ↓ stimuli/probes/measurements
Certified engines (MNA/transient/P2 sampling/…)
```

Instruments (DC source, multimeter, oscilloscope, function generator,
logic analyzer — `lab/instruments.py`, `measure.py`, `stimulus.py`)
stay domain value-engines. Widgets render `Measurement`/waveform
value-tuples and issue commands; zero FFT/sampling/solver code in
`ui/` (D1-007 pins current + future state).

## 21. Academic/Knowledge integration

`domain/{academic,assessment,authoring,…}` + `documents/*` (AST,
parsers, renderers, search) + `domain/electronics/*` stay Qt/F8/LLM/
filesystem-free (tested). Knowledge↔Academic↔Engineering meet ONLY in
application services (`AuthoringService`, `EngineeringService.
link_to_document`, `AssessmentService`) via IDs/links, never via
shared mutable objects. Simulation never sees document storage
internals (link IDs only).

## 22. External repositories

| Repo | Evidence in workspace | D1 classification |
|:---|:---|:---|
| AcademicCore | this repo, fully inspected | core |
| Conversor-HTML-A-MD (external, MIT, :217) + in-repo `documents/conversor_*` engine | roadmap rows; in-repo engine files + `test_conversor_equiv.py`; external copy inspected at `Documents/HTML TO MD/conversor_html_notebooklm.py` (tkinter GUI + subprocess + sqlite3, single script) | `adapter` target (fuse behind `ResourceExtractor`-style port; decouple Tkinter, confine subprocess per ngspice precedent; error-pattern cleanup is D2's) |
| GestionAcademicaGREELEC.exe | ZERO references repo-wide | UNKNOWN / REQUIRES INPUT — no functionality assumed; adapter slot reserved, mapping to F4 model deferred until input exists |
| OneDrive/Cloud (F13) | `config.providers(onedrive_enabled=False)` + roadmap F13/F13-ext | future `adapter` behind ports; last-writer-wins + log per :218, no CRDT |

## 23. Configuration

Existing `config/settings.py` shape is kept: layered
defaults < file < `ACORE_*` env < explicit overrides; closed
dataclasses per area; no secrets on disk; no mutable globals
(constructed `Settings`, passed down). D1 adds: per-module
`configuration_schema` (closed keys, §8) validated at wiring;
experiment/project/user-preference separation lives in
application+repos, never in domain state.

## 24. Commands/Queries

CQRS-lite, following the existing de-facto split (services mutate and
return reports; `AcademicQueries` reads views): commands
(`RunExperiment`, `MeasureVoltage`, `RunSimulation`, `ImportDocument`,
`GenerateExercise`…) return frozen reports; queries
(`GetExperiment`, `GetMeasurement`, `GetCourse`, `GetConcept`…)
return frozen views. No framework, no bus: direct service calls.
Value: testability + UI decoupling (§26/§30). New F15 commands follow
the naming; old services unchanged.

## 25. Events

**No global event bus.** Rationale: all listed cases (simulation
completed, measurement acquired, experiment changed, document
imported, assessment completed) are synchronous service results today;
Qt signals already cover intra-UI notification. A bus would add
ordering/serialization/error semantics for zero evidenced need. If F15
later needs cross-view updates, Qt signals + query refresh is the
bounded mechanism (documented here so a future bus requires its own
gate).

## 26. Testability

Layers test independently: domain without Qt/app (holds; pinned),
application with fake repos/ports (existing `test_application.py`
pattern), adapters with fixtures, UI with `pytest-qt` (dev extra;
existing `test_ui*.py`). F8-N and P1..P5 keep passing without Qt
(D1-007/D1-008). F15 views testable against fake services.

## 27. D2 boundary

D1 leaves for D2: logging framework choice, error catalog, full
exception hierarchy, the conversor `except Exception: pass` cleanup
(:214), UI error-presentation strings. D1 fixes only the boundary:
domain errors = typed values; application errors = service-raised
typed errors + reports; adapter errors = degraded-with-provenance;
UI errors = presentation of the above (§29 matrix row).

## 28. D3 boundary

D1 leaves for D3: LICENSE/NOTICE/headers, single-license decision
(conversor already MIT per :215), header policy. D1 requires only
that future fused code arrives with license metadata in its manifest
(`security_policy` + provenance fields reserved).

## 29. F15 prerequisites

D1 implementation (separate phase, not this gate) + D2 + D3, then
F15 needs: Lab Application Service, engine UI-adapters (application
level), module registry + manifests, D1 edge tests green, fused
conversor adapter (or deferral), GREELEC input (or documented
deferral). Views/widgets list itself is F15's design, not D1's.

## 30. Invariants

| ID | Property | Future test |
|:---|:---|:---|
| D1-I001 | domain imports no UI/Qt | D1-001/D1-002 |
| D1-I002 | F8 engines independent of Qt | D1-008 |
| D1-I003 | F8-N independent of Qt | D1-007 |
| D1-I004 | manifest parsing executes no code | D1-003/D1-010 |
| D1-I005 | module discovery order deterministic | D1-004 |
| D1-I006 | serialization contracts unbroken | D1-006 |
| D1-I007 | adapters never contain domain math | review + D1-009 |
| D1-I008 | UI never calls solvers directly | D1-007/D1-008 |
| D1-I009 | no dependency cycles (authored DAG) | D1-001 |
| D1-I010 | versions resolve compatibly | D1-005 |

## 31. Risk matrix

| Risk | Prob. | Impact | Mitigation | Residual |
|:---|:---:|:---:|:---|:---|
| UI/domain coupling (authoring shortcut AI-001 + engineering lazy-import shortcut AI-002) | M | M | re-route via AuthoringService/EngineeringService in F15; D1-008 pins rest | low |
| Qt leakage into domain/services | L | H | edge tests D1-001/002/008; existing purity tests | low |
| Dynamic-loading temptation | L | H | strategy A normative (§7); AST bans loader imports in wiring | low |
| Dependency cycles via adapters | L | H | static DAG + cycle check at registry build (D1-001) | low |
| Serialization incompatibility on fusion | M | M | closed schemas + registry (§15); old loaders kept | low |
| Version mismatch fused modules | M | M | compat rule §16 + D1-005 | low |
| External repo contamination (GREELEC/conversor) | M | H | adapter-behind-port; UNKNOWN slot; no core edits (§22) | med |
| Nondeterministic discovery | L | M | no discovery; authored order + D1-004 | low |
| Configuration mutation at runtime | L | M | frozen dataclasses; validation at wiring | low |
| F8 regression via adaptation | L | H | engines untouched; adapters in application; suites green | low |
| Lab engine/UI coupling | L | H | instruments stay domain; widgets render values (D1-007) | low |
| Persistence leakage (engines opening files) | L | H | D1-001 edges; services own IO | low |
| Future AI coupling bypassing guardrails | M | H | AI stays provider-adapter behind validator→solver (roadmap F12 shape) | med |
| Manifest-as-code (deserialization exec) | L | H | data-only manifest + D1-003/010 | low |

## 32. Open questions

1. GREELEC functionality/model mapping — matters for its adapter; evidence missing (zero refs). NON-BLOCKING for D1 (slot reserved; blocks only that adapter's fusion).
2. External Conversor-HTML-A-MD repo exact API/state — matters for adapter detail; in-repo engine inspected, external falsely assumed nothing. NON-BLOCKING (port shape known).
3. Exact F15 view inventory — F15's design. NON-BLOCKING.
4. AI provider details (F12) — future phase. NON-BLOCKING.
5. OneDrive conflict UX — F13's design. NON-BLOCKING.
No BLOCKING questions remain.

## 33. Acceptance criteria

Defined (§40 prompt): architecture ✓ (§5) · modules ✓ (§6/§38-shape in §4) · boundaries ✓ (§§10-15) · dependencies ✓ (§9) · plugin strategy ✓ (§7) · manifest ✓ (§8/§39-shape) · versioning ✓ (§16) · serialization boundary ✓ (§15) · persistence boundary ✓ (§14) · UI boundary ✓ (§10) · F8-N conceptual integration ✓ (§20) · P1..P5 conceptual integration ✓ (§19) · external adapters ✓ (§22) · security model ✓ (§18) · determinism ✓ (§17) · test strategy ✓ (§26/§42-shape) · D2 boundary ✓ (§27) · D3 boundary ✓ (§28) · F15 prerequisites ✓ (§29). Module/responsibility/dependency matrices: §36-38 below.

## 34. Final verdict

All acceptance items closed on repository evidence; no BLOCKING open
questions; F8-P1..P5, prior gates and roadmap untouched; no F15/D2/D3
code created.

FINAL VERDICT: D1 DESIGN READY

---

## Appendix A. Responsibility matrix (§36)

| Responsibility | Domain | Application | Adapter | UI | Plugin(static) |
|---|:---:|:---:|:---:|:---:|:---:|
| Mathematics/physics/solvers | ✓ | | | | (as domain kind) |
| Orchestration (commands) | | ✓ | | | |
| Read models/queries | | ✓ | | | |
| Persistence impl | | | | | |
| Persistence ports | | ✓ (uses) | | | |
| Persistence impl detail | | | ✓/infra | | |
| Qt/presentation/control | | | | ✓ | |
| External integration | | | ✓ | | ✓ (registered) |
| Serialization contracts | ✓ (owns) | ✓ (uses) | ✓ (obeys) | | declares |
| Logging impl | | | ✓ | ✓ | ✓ |
| Error contracts | ✓ (typed) | ✓ (typed) | ✓ (degrade) | presents | declares |
| Determinism | ✓ | ✓ | bounded | n/a | declares |

## Appendix B. Dependency matrix (§37)

```text
ALLOWED:   ui → application-services/facade; ui → Qt/dialogs
           application → domain; application → ports
           adapter/infrastructure → ports; entry → config/facade/ui-root
           domain → math/units/stdlib (+certified DAGs)
FORBIDDEN: domain → ui/Qt/loader/filesystem/network/subprocess
           application → Qt-widgets/concrete-adapters
           ui → domain-internals/solver-privates
           adapter → domain-beyond-ports
           any → runtime code-loading for wiring
```

## Appendix C. Module matrix (§38, condensed)

Academic, Knowledge(documents/AST/parsers/renderers/search),
Engineering (MNA/AC/transient/structural/thevenin), Virtual Lab
(session/experiment/run/stimulus/probe/measurement/instruments),
Metrology+GUM, Control, DSP, RF, Comms, Satcom, Persistence
(SQLite/CAS/FTS), AI-providers (future adapter), UI views — each:
domain-pure (or adapter/UI by kind), public API = package exports,
serialization = owned versioned contracts, determinism = closed-form/
seeded, security = kind policy, UI exposure = via application only.

## Appendix D. Manifest contract (§39)

Schema `d1-manifest/1` (closed keys §8; unknown rejected; versions
resolve §16; capabilities/dependencies/security/determinism declared;
validation pure-data). D1 implementation will ship the validator +
static registry + D1-001…D1-010 tests; this gate freezes the shape.
