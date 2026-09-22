# GATE F8-Q — Final Certification (Digital Engine + Logic Analyzer)

Scope: F8-Q as a whole. This covers the digital core, N-ary gates,
stimuli, hardening, `DigitalTrace`, serialization, replay, the Logic
Analyzer, the F15 integration and UI, and the final certification.
Design authority is [GATE-DIGITAL-ENGINE-DESIGN.md](GATE-DIGITAL-ENGINE-DESIGN.md).
The sub-phase logs are:

- [GATE-F8Q-DIGITAL-ENGINE.md](GATE-F8Q-DIGITAL-ENGINE.md) (Q1–Q4)
- [GATE-F8Q5-LOGIC-ANALYZER.md](GATE-F8Q5-LOGIC-ANALYZER.md)
- [GATE-F8Q6-F15-LOGIC-ANALYZER.md](GATE-F8Q6-F15-LOGIC-ANALYZER.md)

## Baseline

- Q4 certified baseline: `38e34a09c6976436fa8a3778647d16975587309f`
  (`feat(engineering): serialize and replay digital traces`) on `main`.
  The tree was clean and `HEAD == origin/main`.
- Full suite at that baseline: 2875 passed, 134 skipped, 0 failed.

## Q5 — Logic Analyzer

- **Implementation.** `domain/engineering/digital/analyzer.py`, plus one
  additive method in `core.py`: `DigitalSimulator.run_until(limit)`,
  which processes events with `time ≤ limit` in canonical order. Pure
  domain code: no Qt, logging, clock or RNG.
- **API.**
  - `TriggerEdge` (RISING / FALLING / BOTH)
  - `CaptureStatus` (CAPTURED / TRIGGERED / NOT_TRIGGERED)
  - frozen `TriggerConfig`, `CaptureConfig`, `CaptureResult`
  - stateless `LogicAnalyzer.capture(circuit, config)` and
    `.analyze(trace, config)`
  - `verify_capture`
  - `MAX_CAPTURE_CHANNELS` = 32, `MAX_CAPTURE_SAMPLES` = 200 000
- **Trigger.**
  - Only a recorded real transition can fire; the initial state never
    does. The arming window is inclusive.
  - The first qualifying transition in engine order wins.
  - The result reports the fired edge and its `trigger_index`.
  - `NOT_TRIGGERED` is a value, never an exception.
- **Capture.**
  - Window `[t − pre, t + post]` (or `[start, end]` without a trigger),
    clipped to the source window. Both the requested and the effective
    window are reported.
  - Exact Decimal arithmetic in a trapped exact context.
  - Inclusive boundaries; `initial` is the state just before the window.
  - The state is held up to the simulation horizon.
- **Same-timestamp.** Runs such as LOW→HIGH→LOW→HIGH (XOR3) and
  HIGH→LOW→HIGH (XNOR2) are kept in engine order and never collapsed.
  The trigger index names the exact transition.
- **Replay.**
  - A capture is a `DigitalTrace`, i.e. a `digital-trace/1` document, so
    there is no second format.
  - `verify_capture` Q4-replays the source and the capture, re-analyzes,
    and requires exact equality. Tampering is detected
    (`REPLAY_MISMATCH`).
- **Tests.** `tests/test_f8q5_logic_analyzer.py`, 87 tests, plus 4 golden
  fixtures in `tests/fixtures/logic_analyzer/`.
- **Commit.** `ba82af416a4545c8bdd1f1bf9798d6b237bdd4d5`
  (`feat(engineering): implement digital logic analyzer`).
  Remote: `origin/main == ba82af4` after the push.
- **Full suite at the Q5 commit:** 2962 passed, 134 skipped, 0 failed.

## Q6 — F15 integration + UI

- **Application service.** `application/digital_service.py`
  `DigitalAnalysisService`, wired as `AcademicApp.digital`, is the single
  UI↔engine boundary. It:
  - translates text to exact Decimal strictly
  - builds a fresh demo circuit for each capture
  - invokes `LogicAnalyzer`
  - returns frozen `str` / `int` view models (`CaptureView`,
    `WaveformChannelView`, `TransitionView`, `ReplayView`)
  - handles `digital-trace/1` load, replay and verify through Q4
  - raises D2 errors through the existing `to_ui_error`
  - imports no Qt and contains no gate, trigger or window logic
- **F15 integration.** A **Logic Analyzer** tab in `main_window.py`,
  plus a dashboard card (`navigate("logic")`).
- **UI** (`ui/logic_analyzer.py`):
  - controls for channel selection (showing net and start-up state),
    start/end, trigger channel, edge and pre/post-trigger
  - Capture runs on the existing F15 `ServiceWorker` / `QThreadPool`
  - status is explicit text: `TRIGGERED — …` / `NOT_TRIGGERED — …;
    nothing captured` (WARNING, never an error dialog)
  - trigger details: channel, configured and fired edge, exact time,
    transition index, window
  - an exact transition table (`#`, time, channel, net, previous, new,
    same-time `k/n`) with `inspect(row)`
  - save, load and replay of `digital-trace/1`, rendered without
    re-running any circuit
- **Waveform renderer** (`ui/waveform.py`).
  - `layout_waveform` is pure and deterministic; `WaveformWidget` only
    paints it.
  - Each lane is labelled `channel (net)` and shows H/L level text, time
    ticks, a dashed trigger line with a text label, and pre/post-trigger
    regions.
  - Transitions that share a pixel column are drawn once and flagged
    `×n`; `merged_columns` is reported. The model keeps every
    transition.
- **Accessibility.**
  - Accessible names and tooltips on every control, keyboard mnemonics,
    and a focusable waveform.
  - States, levels and the trigger are shown as text, never by colour
    alone.
  - Exact values are in the table.
- **Tests.**
  - `tests/test_f8q6_f15_logic_analyzer.py`: 37 tests covering the
    service, the UI via qtbot, the renderer, architecture and bounds.
  - Three existing UI tests updated their exact tab count 12 → 13 for
    the new tab. They still check an exact count and now also the tab
    title.
- **Commit.** `54d031f6c8e8dccb49c7aa21dfa1d92ad2281abd`
  (`feat(ui): integrate digital logic analyzer`).
  Remote: `origin/main == 54d031f` after the push.
- **Full suite at the Q6 commit:** 2999 passed, 134 skipped, 0 failed.

## Q7 — Final regression and audits

The Q7 certification tests are in `tests/test_f8q7_certification.py`
(12 tests). Q7 adds no features.

### Complete regression

One run of the full suite on the Q7 tree, offscreen Qt,
`pytest -o addopts="" -q`. Per-group counts come from its JUnit report.

| Group | Passed | Failed | Skipped |
|:---|---:|---:|---:|
| F8-Q.1 | 85 | 0 | 0 |
| F8-Q.2 | 70 | 0 | 0 |
| F8-Q.2R | 43 | 0 | 0 |
| F8-Q.3R | 99 | 0 | 0 |
| F8-Q.4 | 144 | 0 | 0 |
| F8-Q.5 | 87 | 0 | 0 |
| F8-Q.6 | 37 | 0 | 0 |
| F8-Q.7 | 12 | 0 | 0 |
| F8-N | 125 | 0 | 0 |
| F8-P1 / P2 / P3 / P4 / P5 | 51 / 34 / 52 / 40 / 44 | 0 | 0 |
| F15 | 27 | 0 | 0 |
| architecture | 13 | 0 | 0 |
| AST | 5 | 0 | 0 |
| domain | 4 | 0 | 0 |
| engineering security | 5 | 0 | 0 |
| UI (`test_ui*`) | 7 | 0 | 0 |
| **Full suite** | **3011** | **0** | **134** |

- xfailed: 0. Collection errors: 0.
- **Skipped (134).** The count is unchanged since the Q4 baseline. All
  skips are environment-only external runtimes and are unrelated to
  F8-Q:
  - ngspice 47 backend unavailable, in the F7/F8-D/E/F suites
  - a Windows-only reference converter that is absent (`conversor_equiv`)
  - similar optional-tool gates
- **Environment note.** This container needed the system packages
  `libegl1`/`libgl1` (PySide6) and the Python package `cffi` (the pypdf
  crypto backend) to run the Qt and PDF suites. These are environment
  setup, not repository changes. Without `cffi`, 7 PDF tests fail at
  import; with it they pass.

### Architecture audit (static, AST)

- **Forbidden imports.** In every F8-Q module (`digital/*.py`,
  `digital_service.py`, `ui/logic_analyzer.py`, `ui/waveform.py`), there
  is no import of pickle, marshal, shelve, subprocess, importlib,
  pkgutil, ctypes or multiprocessing. There is also no
  `system` / `popen` / `entry_points` attribute and no `shell=True`
  (`test_q7_s01`).
- **Deterministic core.** `digital/*` imports no time, datetime, random,
  uuid, secrets, logging, threading, asyncio, PySide6, os, sys, io or
  pathlib (`test_q7_s02`, plus the Q1 purity test).
- **Dependency direction** (`test_q7_s03`, `test_q6_x01`/`x02`, F15-018,
  `test_architecture`):
  - domain → never application / ui / PySide6
  - application → never ui / PySide6
  - the new UI modules → never domain or infrastructure
- **Single analyzer.** Exactly one `LogicAnalyzer` and one
  `DigitalAnalysisService` class exist. The UI modules contain no
  `GateKind`, `LogicAnalyzer(`, `DigitalSimulator`, `.evaluate(`,
  `.fires(` or `json.loads` (`test_q7_s04`).
- **No new dependency.** `pyproject` dependencies are still
  `["PySide6>=6.7"]` and `requirements.txt` is unchanged. Every F8-Q
  import is stdlib, `academic_core`, PySide6 or `__future__`
  (`test_q7_s05`).
- **No dynamic plugin loading anywhere in F8-Q.** The only `importlib`
  use in `src/` is the pre-existing `importlib.resources` in
  `infrastructure/database.py`, a static resource read.

### Security audit

- There is no `eval`, `exec`, `compile`, `__import__`, pickle, marshal,
  subprocess, `os.system` or dynamic import in any F8-Q module (the AST
  tests above, F15-017, `test_q4_x02`, `test_q5_x01`, `test_q6_x03`).
- Deserialized data (`digital-trace/1`) is bounded before parsing:
  - 16 MiB
  - depth 5
  - 10⁶ values
  - 20-digit integers

  Then it is strictly validated: exact keys, canonical Decimal, LOW/HIGH
  only, ids, order, window, same-net agreement. Q4 has 144 tests,
  including malicious payloads that never reach `eval`.
- The UI refuses files over 16 MiB before reading them.
- Malformed configurations and traces produce controlled D2 errors
  (AC-VAL / AC-SER / AC-VER / AC-DOM / AC-INT). They are converted by
  the single `to_ui_error` and never crash the UI (`test_q6_u06`,
  `test_q6_u08`, `test_q6_a08`).

### Determinism audit

- The whole pipeline runs twice in-process with identical results.
- `test_q7_d01` runs it in 4 separate interpreter processes
  (`PYTHONHASHSEED` 0 / 1 / 31337 / random). All give byte-identical:
  - trace digest
  - canonical JSON hash
  - replay digest
  - status
  - trigger time and index
  - view digest
  - renderer geometry hash
- The same holds per phase: Q4 (`test_q4_z02`), Q5 (`test_q5_d02`,
  including `NOT_TRIGGERED`), and Q6 (`test_q6_a10`, independent of the
  log level; `test_q6_u10`, identical repaint).
- End to end (`test_q7_e01`): analyzing the serialized-and-replayed
  trace gives exactly the live capture. The view and the renderer are
  faithful projections of it. A reloaded capture renders identically
  without running a circuit.
- `test_q7_e02`: for every demo, the service view equals the direct
  domain path, and verify gives `EQUIVALENT`.

### Performance / bounds audit

- **Incremental evaluation only.** In `test_q7_p01`, a 1023-input NAND
  (`MAX_NETS` nets) with 2000 edges is captured while the full N-ary
  reduction is patched to raise. There are exactly 2000 O(1) pin
  updates, so no full-gate scan and no O(N²) behaviour were introduced.
- **Near-limit same-timestamp traffic.** In `test_q7_p02`, XOR3 with 3000
  instants × 3 same-time transitions on 16 channels gives 144 000
  captured transitions. None are collapsed, and the capture round-trips
  through Q4.
- **Capture limit at the edge.** `test_q7_p03` uses 32 channels:
  - 5000 transitions per channel = 160 000, which is accepted
  - 7000 per channel = 224 000, which is refused (`CAPTURE_LIMIT`) and
    never truncated
- **Renderer.** 80 000 transitions lay out with at most one edge per
  pixel column per lane, and the merge is flagged (`test_q6_b01`).
- **Limits.** Existing and new limits are enforced by tests: `MAX_NETS`,
  `MAX_EVENTS`, `MAX_DELTA_EVENTS`, `MAX_TIME`, `MAX_PROBES`, the Q4 wire
  limits, and the Q5 capture limits.

### Git / diff audit

- The Q5–Q7 range `38e34a0..HEAD` has a clean `git diff --check`.
- No caches, `.pyc` files, logs or temporary files are tracked.
- There are no debug prints. The two `print` matches are a subprocess
  child script in a test and an AST policy list.
- There are no secrets, no commented-out code, no deleted tests and no
  dependency changes.
- Files touched outside the new modules:
  - `digital/core.py` (additive `run_until`) and `digital/__init__.py`
    (exports)
  - `application/facade.py` (+`digital`)
  - `ui/main_window.py` and `ui/dashboard.py` (tab and card)
  - three UI tests (tab count 12 → 13)
  - `docs/roadmap/ROADMAP.md` (F8-Q status)

## Known limitations (real, current)

1. **Triggers.** Only single-channel edge triggers exist
   (RISING / FALLING / BOTH). Pattern, level and multi-channel triggers
   are future work (design §23).
2. **No-op counts in partial windows.** `digital-trace/1` stores no-op
   counts without timestamps (Q3R/Q4). A partial capture window
   therefore reports 0 no-ops, and Q4 replay places no-ops at the window
   end.
3. **Event budget.** Stimuli are scheduled in full at start-up (Q2), so
   the `max_events` budget counts all stimulus edges, not only those
   inside the capture horizon.
4. **Demo circuits only in the UI.** The F15 UI captures only the four
   application demo circuits; building arbitrary circuits needs the
   future `digital-circuit/1` format or an editor (design §30). Loaded
   `digital-trace/1` files can be viewed and replayed.
5. **No zoom or scroll.** The waveform fits the captured window to the
   widget width. For closer inspection, capture a narrower window or use
   the exact transition table.
6. **Q4 wire limits.** A capture over 200 000 transitions, or a document
   over 16 MiB, is refused. Nothing is truncated.
7. **Out of scope by design.** v1 has no sequential logic, clocks, X/Z,
   mixed-signal or HDL (design §§43–47).

### Pre-existing issues found (outside F8-Q; recorded, not changed)

- **`ui/virtual_lab.py::_build_definition` uses `ExperimentDefinition`
  without importing it (ruff F821).**
  - Since `c1dea25` (F15), the Virtual Lab **Add + Run** button raises
    `NameError`, which the panel shows as a generic error dialog.
  - Reproduced by calling `VirtualLabPanel._build_definition()`
    directly.
  - The F15 tests exercise the service path, which works, not this
    widget method.
  - The fix is one import in an F15 change. It was not made here
    because it is outside F8-Q's scope.
- **`ui/authoring.py`** has an unused `QComboBox` import (ruff F401).
- **`GATE-F15.md` is now outdated on one point.** It still lists the
  logic analyzer as an F15 limitation. That is accurate for F8-N, and
  `test_f15_011` still holds, but the digital Logic Analyzer now exists
  as the F8-Q tab. The certified F15 gate text is left as is, and this
  document supersedes that note.

## Final verdict

Every required criterion is met, each backed by the evidence above:

- **Q5:** READY.
- **Q6:** READY.
- **Q7:**
  - full suite 3011 passed / 0 failed / 134 environment-only skips
  - the architecture, security, determinism, performance and diff
    audits all pass
  - `HEAD == origin/main`

```text
F8-Q COMPLETE / CERTIFIED
```
