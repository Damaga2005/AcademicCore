# GATE F8-Q.6 — F15 Integration + Logic Analyzer UI

Design authority: [GATE-DIGITAL-ENGINE-DESIGN.md](GATE-DIGITAL-ENGINE-DESIGN.md),
§§6, 25–26, 35–36. Domain analyzer:
[GATE-F8Q5-LOGIC-ANALYZER.md](GATE-F8Q5-LOGIC-ANALYZER.md).

## Baseline

The starting point is the F8-Q.5 commit
`ba82af416a4545c8bdd1f1bf9798d6b237bdd4d5` (`feat(engineering):
implement digital logic analyzer`) on `main`. At that commit
`HEAD == origin/main`, and the full suite gave 2962 passed, 134 skipped,
0 failed.

## Architecture

```text
UI  (ui/logic_analyzer.py LogicAnalyzerPanel  +  ui/waveform.py renderer)
 ↓  AnalyzerRequest (plain strings)            ↑ CaptureView / ReplayView (frozen str/int/tuple)
AcademicApp.digital  (application/facade.py)
 ↓
DigitalAnalysisService  (application/digital_service.py — no Qt)
 ↓  CaptureConfig / TriggerConfig (typed, validated by the domain)
LogicAnalyzer  (domain, F8-Q.5 — the only implementation)
 ↓
DigitalCircuit / DigitalSimulator  →  DigitalTrace / CaptureResult
 ↓
capture_view(): CaptureResult → CaptureView  (pure data mapping)
 ↓
layout_waveform() geometry → WaveformWidget paint
```

Boundaries are enforced by AST tests in `test_q6_x01` through
`test_q6_x03`:

- **UI modules:**
  - They import no `academic_core.domain*` and no infrastructure.
  - They make no calls named `evaluate` / `fires` / `analyze` /
    `run_until` / `step` / `run` / `schedule` / `state_at` / `to_json` /
    `from_json`.
  - They contain no `LogicAnalyzer(`, `GateKind` or `json.loads`.
- **Service:** it imports no PySide6 and uses no evaluator, edge or
  scheduling API. It only reads samples to build views.
- **Single analyzer:** there is exactly one `LogicAnalyzer` class in
  `src/`.
- **Domain:** it imports no PySide6, `academic_core.ui` or
  `academic_core.application`.

These add to the existing F15-018 edge test and the architecture suite.

## Application service — `DigitalAnalysisService` (`app.digital`)

| Method | Returns | Notes |
|:---|:---|:---|
| `demos()` | `tuple[DemoInfo]` | four certified-constructor circuits, sorted: `half_adder`, `repeated_inputs` (XOR(A,A,B), NOR(A,B,A)), `wide_nand` (16-input NAND), `xor3_glitch` (same-timestamp transitions) |
| `channels(demo)` | `tuple[ChannelInfo]` | probe id, net id, start-up state |
| `build_config(request)` | `CaptureConfig` | strict text → Decimal (`(0\|[1-9][0-9]*)(\.[0-9]+)?`, ≤ 64 chars, no exponent/sign/float); edge ∈ `RISING/FALLING/BOTH`; no trigger fields without a trigger channel |
| `capture(request)` | `CaptureView` | builds a **fresh** circuit per call → `LogicAnalyzer.capture` → `capture_view` |
| `capture_result(request)` | `CaptureResult` | domain value, for verification and tests |
| `verify(request)` | `ReplayView` | `verify_capture` → `EQUIVALENT` / `RESULT_DIFFERS` |
| `load_trace(text)` | `CaptureView` (`LOADED`) | renders a `digital-trace/1` document without running any circuit |
| `replay_trace(text)` | `ReplayView` | Q4 `verify_replay` → `EQUIVALENT` / `RESULT_DIFFERS` |

- **Errors.** Errors come from D2 through the unchanged `to_ui_error`,
  with no new codes:
  - `ValidationError` AC-VAL-001 (`INVALID_TIME`, `INVALID_TRIGGER`,
    `INVALID_CAPTURE`, `UNKNOWN_DEMO`, `UNKNOWN_PROBE`,
    `DUPLICATE_PROBE`, …)
  - `SerializationError` AC-SER-001
  - `VersionMismatchError` AC-VER-001
  - a schema error is shown as "unrecognized format"
- **Logging.** The service logs milestones only (request, status,
  correlation id). It never logs per transition, and never from the
  domain.

## View models (frozen; leaves are only `str`, `int`, `None`)

- `AnalyzerRequest`, `ChannelInfo`, `DemoInfo`, `ReplayView`.
- `CaptureView`:
  - status (`CAPTURED` / `TRIGGERED` / `NOT_TRIGGERED` / `LOADED`)
  - source
  - channels
  - effective and requested window
  - configured and fired edge
  - trigger time and index
  - pre/post
  - Q4 digest and canonical `trace_json`
- `WaveformChannelView`: `channel_id`, `net_id`, `initial`, `final` and
  its `transitions`.
- `TransitionView`: `index`, exact `time`, `previous`, `new`, plus
  `same_time_rank` / `same_time_count` (built in one linear pass).
- `CaptureView.transitions` lists every transition, ordered by
  (time, channel, index).
- Times are always the canonical exact Decimal text (`canonical_time`),
  never floats.

## UI — `Logic Analyzer` tab (`ui/logic_analyzer.py`)

- **Circuit and channels.**
  - Circuit selector: each demo's description is its tooltip.
  - Channel list: checkable, labelled `probe → net X (start: LOW)`.
  - `selected_channels()` and `set_channels()` read and set the
    selection.
- **Capture.**
  - Fields: start / end, which are the capture window or, with a
    trigger, the arming window.
  - Trigger channel: `(none)` means a plain window capture.
  - Edge: `RISING` / `FALLING` / `BOTH`.
  - Pre-trigger / post-trigger.
  - Every control maps 1:1 to a Q5 field. There are no controls for
    unsupported features (patterns, sampling, X/Z).
- **Buttons.**
  - **Capture** runs on the F15 `ServiceWorker` / `QThreadPool` pattern.
    Input is validated on the UI thread first (fail fast, D2 dialog).
    The result comes back through Qt signals, and widgets are never
    touched from the worker.
  - **Verify replay**, **Save trace…**, **Load trace…**,
    **Replay trace**. Files are `digital-trace/1` text, and files over
    16 MiB are refused before reading.
- **Status and trigger details.**
  - The status label holds explicit text: `TRIGGERED — …`,
    `NOT_TRIGGERED — no qualifying edge in the arming window; nothing
    captured`, `CAPTURED — …` or `LOADED — …`.
  - `NOT_TRIGGERED` sets the WARNING state, never ERROR, and shows no
    dialog.
  - The trigger-details label (selectable) shows the configured
    trigger, the fired edge, the exact time, the transition index, the
    window, a note when the window was clipped, and the digest.
- **Transition table.**
  - Columns: `#`, time (exact), channel, net, previous, new, same-time
    (`k/n`).
  - `inspect(row)` returns those exact values.
- **Errors.** All errors go through `show_ui_error` (the single D2 UI
  converter).
- **Wiring.** The tab is wired in `main_window.py`. The dashboard gains
  a **Logic Analyzer** card (`navigate("logic")`).

## Waveform renderer (`ui/waveform.py`)

- **`layout_waveform(view, width)`** is pure and deterministic
  (repeated calls return equal geometry).
  - x positions come from the exact Decimal times, rounded half-even to
    pixels for presentation only.
  - Per lane it builds a label `channel (net)`, HIGH/LOW level segments,
    and edges.
  - Five exact time ticks.
  - The trigger line and label `T <edge> on <channel> @ <t> s
    (transition #i)`, plus pre/post-trigger regions.
- **Merging is never silent.** Transitions that share a pixel column
  (same timestamp, or closer than a pixel) become one drawn edge that
  carries a `count`:
  - The widget prints `×n` above it.
  - `merged_columns` is reported, and the widget summary says the
    transitions are all listed in the table.
  - The model keeps every transition. Drawing is bounded by at most one
    edge per pixel column per lane.
- **`WaveformWidget`** only paints the cached geometry. It recomputes
  when the view or the width changes. It never mutates the view (tested:
  the view object, its trace text and its digest are unchanged, and two
  grabs give identical images).

## Accessibility

- Every control has an accessible name and a tooltip. Buttons have
  keyboard mnemonics (`&Capture`, `&Verify`, `&Save`, `&Load`,
  `&Replay`). The waveform takes keyboard focus and has an accessible
  description.
- States are text (`TRIGGERED` / `NOT_TRIGGERED` / `ERROR AC-…`), not
  colour. Levels are labelled `H` / `L`, lanes are labelled by channel
  and net, the trigger has a text label, and the pre/post regions are
  labelled in text.
- Exact values are available in the table and via `inspect`; a pixel
  never replaces the exact Decimal.

## Threading

- The only threads are the existing F15 `ServiceWorker` on `QThreadPool`.
  The domain and service stay thread-agnostic and share no state.
- The service creates a new circuit per capture, and the stateless
  analyzer returns frozen values, so concurrent captures cannot race.
- The Capture button is disabled while running and re-enabled on result
  or error.

## Security

- The new modules contain no `eval`, `exec`, `compile`, `__import__`,
  pickle, marshal, subprocess or importlib (AST test; F15-017 still
  passes).
- Loaded files go through the strict Q4 decoder. The size is checked
  before reading, and the service applies the Q4 limits.
- A demo key that is not in the fixed table is rejected (`UNKNOWN_DEMO`).
  There is no dynamic lookup.

## Tests — `tests/test_f8q6_f15_logic_analyzer.py` (37 tests)

- **Application:**
  - facade wiring and demos/channels
  - request translation, with 14 invalid time texts on every time field
  - invalid trigger and channel input
  - TRIGGERED mapping: `capture_view(direct LogicAnalyzer result)`
    equals the service view, same digest and JSON
  - NOT_TRIGGERED and CAPTURED mapping
  - frozen plain-data view models
  - D2 error conversion
  - load / replay / verify, including RESULT_DIFFERS
  - determinism with a changed log level
- **UI (qtbot, offscreen):**
  - tab and dashboard navigation
  - channel selection
  - controls → request mapping
  - triggered capture end-to-end through the worker (the view equals
    the service view)
  - NOT_TRIGGERED explicit: WARNING, no dialog
  - invalid input → D2 dialog, ERROR
  - same-timestamp rows `1/3 2/3 3/3`, `inspect`, a merged column
    flagged `×3`
  - load and replay in the UI
  - exact renderer geometry: pixel positions, levels, ticks
    `0 1 2 3 4`, NOT_TRIGGERED message
  - identical repeated paints with no mutation
- **Architecture:** UI/domain separation, the service as boundary, a
  single `LogicAnalyzer`, the domain's reverse dependencies, unsafe
  primitives.
- **Bounds:** an 80 000-transition capture lays out in under 10 s, with
  at most one edge per pixel column per lane and the merge flagged.
- **Existing F15 tests:** `test_f15_app.py` (27) passes unchanged.
  `test_f15_011` still holds: F8-N's `InstrumentKind` has no
  `logic_analyzer`, because the digital analyzer is a separate F8-Q
  surface and not an F8-N instrument.

## Regressions

Run on the Q6 tree, offscreen Qt:

| Suite | Result |
|:---|:---|
| Q6 (`test_f8q6_f15_logic_analyzer.py`) | 37 passed |
| F15 (`test_f15_app.py`) | 27 passed, unchanged |
| UI suites (`test_ui.py`, `test_ui_authoring.py`, `test_ui_engineering.py`) | passed |
| **Full suite** | **2999 passed, 134 skipped, 0 failed** (Q5 baseline 2962 + 37 new; same 134 skips) |

- **First run.** It had 3 failures, all the same assertion. Three UI
  tests pin the exact main-window tab count at 12 (Dashboard + 5 legacy +
  Authoring + Engineering + Exercises + Simulation + Virtual Lab +
  Settings). The new **Logic Analyzer** tab makes it 13.
- **The fix is an intended contract update, not a weakening.** The
  assertions still check the exact count, now 13, with the comment
  naming the new tab. `test_ui.py` also asserts the tab's title and
  position (just before Settings), in the same way F15 updated these
  counts when it added its tabs.
- **Second run.** After the update, the whole suite is green.
- No test was skipped, xfailed or deleted.

## Limitations (real)

- **Demo circuits only.** The UI captures only the four application
  demo circuits. Building arbitrary circuits in the UI would need a
  circuit editor or a `digital-circuit/1` format, neither of which
  exists yet (design §30 names `digital-circuit/1` as future). A loaded
  `digital-trace/1` file can still be inspected and replayed.
- **No zoom or scroll.** The waveform always fits the captured window to
  the widget width. To look more closely, capture a narrower window;
  the exact values are always in the table.
- **Pre-existing F15 defects (found, not changed here).** These are
  outside F8-Q's scope, so they are recorded rather than fixed.
  - `ui/virtual_lab.py::_build_definition` uses `ExperimentDefinition`
    without importing it (ruff F821).
    - Since `c1dea25`, the Virtual Lab **Add + Run** button always
      raises `NameError`. `_add_run` catches it and shows it as a
      generic D2 error dialog.
    - Reproduced directly: calling `VirtualLabPanel._build_definition()`
      raises `NameError: name 'ExperimentDefinition' is not defined`.
    - The F15 tests don't exercise that widget method. They test the
      service path, which works.
    - Fix: one import, in a separate F15 change. **Fixed afterwards**
      by `fix(ui): repair Virtual Lab Add + Run`, together with a second
      defect it had been hiding (`summary.run.*`). See
      [GATE-F8Q-FINAL.md](GATE-F8Q-FINAL.md).
  - `ui/authoring.py` has an unused `QComboBox` import (ruff F401).

## Verdict

```text
F8-Q.6 READY
```
