"""F8-Q.6 F15 integration + Logic Analyzer UI -- test suite.

Sections: application service (config, invocation, mapping, errors,
serialization/replay) / UI (channels, capture controls, trigger,
NOT_TRIGGERED, rendering, same timestamp, inspection, determinism,
no mutation) / architecture boundaries / bounds.
"""

from __future__ import annotations

import ast
import dataclasses
import logging
import os
import pathlib
import time
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from academic_core.application import AcademicApp
from academic_core.application import digital_service as ds
from academic_core.application.digital_service import (
    LOADED,
    AnalyzerRequest,
    CaptureView,
    DigitalAnalysisService,
    capture_view,
)
from academic_core.config import Settings
from academic_core.domain.engineering.digital import (
    CaptureConfig,
    DigitalCircuit,
    DigitalProbe,
    LogicAnalyzer,
    LogicState,
    ToggleStimulus,
    TriggerConfig,
    TriggerEdge,
)
from academic_core.errors import SerializationError, ValidationError, to_ui_error
from academic_core.ui.main_window import AcademicMainWindow
from academic_core.ui.waveform import layout_waveform

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "academic_core"
SVC = DigitalAnalysisService()


def req(demo="xor3_glitch", channels=("a", "y"), start="0", end="4", trigger="", edge="", pre="", post=""):
    return AnalyzerRequest(demo, tuple(channels), start, end, trigger, edge, pre, post)


@pytest.fixture()
def core(tmp_path, monkeypatch):
    monkeypatch.setenv("ACORE_DATA_DIR", str(tmp_path / "data"))
    core = AcademicApp(Settings.load())
    core.settings.ensure_dirs()
    return core


@pytest.fixture()
def dialogs(monkeypatch):
    """Record UI-error dialogs instead of blocking on a modal QMessageBox."""
    shown = []
    from academic_core.ui import errors as ui_errors
    for name in ("warning", "information", "critical"):
        monkeypatch.setattr(ui_errors.QMessageBox, name,
                            staticmethod(lambda parent, title, body, _n=name: shown.append((_n, title, body))))
    return shown


@pytest.fixture()
def panel(qtbot, core, dialogs):
    win = AcademicMainWindow(core)
    qtbot.addWidget(win)
    return win.logic_analyzer_panel


def _wait(qtbot, panel):
    qtbot.waitUntil(lambda: panel.state.value != "RUNNING", timeout=20000)


# =============================================================== application service

def test_q6_a01_service_wired_in_facade(core):
    assert isinstance(core.digital, DigitalAnalysisService)
    assert [d.key for d in core.digital.demos()] == ["half_adder", "repeated_inputs", "wide_nand", "xor3_glitch"]
    chans = core.digital.channels("xor3_glitch")
    assert [(c.channel_id, c.net_id, c.initial) for c in chans] == [
        ("a", "A", "LOW"), ("b", "B", "LOW"), ("c", "C", "LOW"), ("y", "Y", "LOW")]
    with pytest.raises(ValidationError, match="UNKNOWN_DEMO"):
        core.digital.channels("ghost")
    with pytest.raises(ValidationError, match="UNKNOWN_DEMO"):
        core.digital.capture(req(demo="__import__('os')"))


def test_q6_a02_request_translation():
    c = SVC.build_config(req(channels=["y", "a"], start="0.50", end="2", trigger="y", edge="FALLING",
                             pre="0.25", post="1"))
    assert isinstance(c, CaptureConfig) and c.channels == ("a", "y") and c.start == Decimal("0.5")
    assert c.trigger == TriggerConfig("y", TriggerEdge.FALLING, Decimal("0.25"), Decimal(1))
    assert SVC.build_config(req()).trigger is None


@pytest.mark.parametrize("bad", ["", " ", "1e3", "-1", "+1", "abc", "1,5", "NaN", "Infinity", "1.", ".5", "0x1",
                                 "1" * 70, "١"])
def test_q6_a03_invalid_time_text(bad):
    for request in (req(start=bad), req(end=bad), req(trigger="y", edge="RISING", pre=bad, post="0"),
                    req(trigger="y", edge="RISING", pre="0", post=bad)):
        with pytest.raises(ValidationError, match="INVALID_TIME"):
            SVC.build_config(request)
    with pytest.raises(ValidationError, match="INVALID_TIME"):
        SVC.build_config(AnalyzerRequest("xor3_glitch", ("a",), 1.5, "2"))


def test_q6_a04_invalid_trigger_and_channels():
    for edge in ("", "rising", "UP", "X"):
        with pytest.raises(ValidationError, match="INVALID_TRIGGER"):
            SVC.build_config(req(trigger="y", edge=edge, pre="0", post="0"))
    with pytest.raises(ValidationError, match="INVALID_TRIGGER"):
        SVC.build_config(req(edge="RISING"))  # edge without a channel
    with pytest.raises(ValidationError, match="not selected"):
        SVC.build_config(req(channels=("a",), trigger="y", edge="RISING", pre="0", post="0"))
    with pytest.raises(ValidationError, match="DUPLICATE_PROBE"):
        SVC.build_config(req(channels=("a", "a")))
    with pytest.raises(ValidationError, match="UNKNOWN_PROBE"):
        SVC.capture(req(channels=("a", "zz")))
    with pytest.raises(ValidationError, match="INVALID_CAPTURE"):
        SVC.build_config(AnalyzerRequest("xor3_glitch", "ay", "0", "1"))  # a bare string is not a list
    with pytest.raises(ValidationError, match="INVALID_CAPTURE"):
        SVC.build_config({"demo": "xor3_glitch"})


def test_q6_a05_capture_mapping_triggered():
    v = SVC.capture(req(channels=("y", "a"), trigger="y", edge="FALLING", pre="0.5", post="1"))
    assert v.status == "TRIGGERED" and v.source == "xor3_glitch"
    assert (v.trigger_channel, v.trigger_edge, v.fired_edge, v.trigger_time, v.trigger_index) == \
        ("y", "FALLING", "FALLING", "1", 1)
    assert v.window == ("0.5", "2") and v.pre_trigger == "0.5" and v.post_trigger == "1"
    y = next(c for c in v.channels if c.channel_id == "y")
    assert [(t.time, t.previous, t.new, t.same_time_rank, t.same_time_count) for t in y.transitions][:3] == [
        ("1", "LOW", "HIGH", 0, 3), ("1", "HIGH", "LOW", 1, 3), ("1", "LOW", "HIGH", 2, 3)]
    # mapping is a pure projection of the domain result, no second analyzer
    circuit = ds._DEMOS["xor3_glitch"][1]()
    direct = LogicAnalyzer().capture(circuit, SVC.build_config(req(trigger="y", edge="FALLING", pre="0.5", post="1")))
    assert capture_view(direct, "xor3_glitch") == v
    assert v.digest == direct.trace.digest() and v.trace_json == direct.trace.to_json()


def test_q6_a06_capture_mapping_not_triggered_and_window():
    nt = SVC.capture(req(start="3.5", end="4", trigger="a", edge="RISING", pre="0", post="1"))
    assert nt.status == "NOT_TRIGGERED" and nt.channels == () and nt.window is None
    assert nt.trigger_channel == "a" and nt.trigger_time is None and nt.digest is None and nt.trace_json is None
    w = SVC.capture(req(start="0.5", end="1.5"))
    assert w.status == "CAPTURED" and w.window == ("0.5", "1.5") and w.trigger_channel is None
    assert len(next(c for c in w.channels if c.channel_id == "y").transitions) == 3


def test_q6_a07_view_models_are_frozen_plain_data():
    v = SVC.capture(req(trigger="y", edge="BOTH", pre="0", post="0"))

    def walk(node):
        if dataclasses.is_dataclass(node):
            for f in dataclasses.fields(node):
                yield from walk(getattr(node, f.name))
        elif isinstance(node, tuple):
            for x in node:
                yield from walk(x)
        else:
            yield node
    for leaf in walk(v):
        assert leaf is None or type(leaf) in (str, int), type(leaf)
    with pytest.raises(dataclasses.FrozenInstanceError):
        v.status = "X"
    with pytest.raises(dataclasses.FrozenInstanceError):
        v.channels[0].transitions[0].time = "0"


def test_q6_a08_error_conversion_is_d2():
    for exc_fn in (lambda: SVC.build_config(req(start="abc")), lambda: SVC.capture(req(channels=("zz",))),
                   lambda: SVC.channels("nope")):
        with pytest.raises(ValidationError) as info:
            exc_fn()
        ui = to_ui_error(info.value)
        assert ui.error_code == "AC-VAL-001" and ui.severity == "WARNING"
        assert "Traceback" not in ui.safe_message
    with pytest.raises(SerializationError) as info:
        SVC.load_trace("{not json")
    assert to_ui_error(info.value).error_code == "AC-SER-001"
    with pytest.raises(ValidationError) as info:
        SVC.load_trace('{"schema":"other","version":1,"window":{},"channels":[]}')
    assert "unrecognized format" in to_ui_error(info.value).safe_message


def test_q6_a09_serialization_load_replay(monkeypatch):
    v = SVC.capture(req(trigger="y", edge="RISING", pre="1", post="1"))
    loaded = SVC.load_trace(v.trace_json)
    assert loaded.status == LOADED and loaded.source == "digital-trace/1"
    assert loaded.channels == v.channels and loaded.window == v.window and loaded.digest == v.digest
    assert SVC.load_trace(v.trace_json.encode("utf-8")) == loaded
    assert SVC.replay_trace(v.trace_json) == ds.ReplayView("EQUIVALENT", v.digest)
    assert SVC.verify(req(trigger="y", edge="RISING", pre="1", post="1")).status == "EQUIVALENT"
    from academic_core.errors import IntegrationError

    def broken(_trace):
        raise IntegrationError("REPLAY_MISMATCH: forced")
    monkeypatch.setattr(ds, "verify_replay", broken)
    assert SVC.replay_trace(v.trace_json).status == "RESULT_DIFFERS"
    monkeypatch.setattr(ds, "verify_capture", broken)
    assert SVC.verify(req()).status == "RESULT_DIFFERS"


def test_q6_a10_determinism_independent_of_logging():
    r = req(trigger="y", edge="BOTH", pre="0.5", post="2")
    first = SVC.capture(r)
    logger = logging.getLogger("academic_core")
    old = logger.level
    logger.setLevel(logging.DEBUG)
    try:
        second = DigitalAnalysisService().capture(r)
    finally:
        logger.setLevel(old)
    assert first == second and first.trace_json == second.trace_json


# =============================================================== UI

def test_q6_u01_tab_and_navigation(qtbot, core, dialogs):
    win = AcademicMainWindow(core)
    qtbot.addWidget(win)
    titles = [win.tabs.tabText(i) for i in range(win.tabs.count())]
    assert "Logic Analyzer" in titles
    win.dashboard_panel.navigate.emit("logic")
    assert win.tabs.currentWidget() is win.logic_analyzer_panel
    assert win.dashboard_panel._cards["logic"].isEnabled()


def test_q6_u02_channel_selection(panel):
    labels = [panel.channel_list.item(k).text() for k in range(panel.channel_list.count())]
    assert all("→ net" in t and "start:" in t for t in labels)
    panel.demo.setCurrentIndex(panel.demo.findData("xor3_glitch"))
    assert panel.selected_channels() == ("a", "b", "c", "y")
    panel.set_channels(["y"])
    assert panel.selected_channels() == ("y",)
    triggers = [panel.trigger_channel.itemData(k) for k in range(panel.trigger_channel.count())]
    assert triggers == ["", "a", "b", "c", "y"]  # "" = no trigger
    panel.demo.setCurrentIndex(panel.demo.findData("wide_nand"))
    assert panel.selected_channels() == ("in0", "y")


def test_q6_u03_capture_controls_map_to_request(panel):
    panel.demo.setCurrentIndex(panel.demo.findData("xor3_glitch"))
    panel.set_channels(["a", "y"])
    panel.start.setText("0.5")
    panel.end.setText("3")
    panel.trigger_channel.setCurrentIndex(panel.trigger_channel.findData("y"))
    panel.edge.setCurrentText("FALLING")
    panel.pre.setText("0.25")
    panel.post.setText("0.75")
    assert panel.request() == AnalyzerRequest("xor3_glitch", ("a", "y"), "0.5", "3", "y", "FALLING", "0.25", "0.75")
    assert [panel.edge.itemText(k) for k in range(panel.edge.count())] == ["RISING", "FALLING", "BOTH"]
    panel.trigger_channel.setCurrentIndex(0)
    r = panel.request()
    assert (r.trigger_channel, r.edge, r.pre_trigger, r.post_trigger) == ("", "", "", "")


def test_q6_u04_triggered_capture_end_to_end(qtbot, panel):
    panel.demo.setCurrentIndex(panel.demo.findData("xor3_glitch"))
    panel.set_channels(["a", "y"])
    panel.start.setText("0")
    panel.end.setText("4")
    panel.trigger_channel.setCurrentIndex(panel.trigger_channel.findData("y"))
    panel.edge.setCurrentText("FALLING")
    panel.pre.setText("0.5")
    panel.post.setText("1")
    panel.start_capture()
    _wait(qtbot, panel)
    assert panel.state.value == "SUCCESS"
    assert "TRIGGERED" in panel.status.text() and "NOT_TRIGGERED" not in panel.status.text()
    info = panel.trigger_info.text()
    assert "Fired: FALLING at t = 1 s" in info and "transition #1 of y" in info and "Window: [0.5, 2] s" in info
    assert panel.view == SVC.capture(panel.request())  # the UI shows exactly the service's view
    g = panel.waveform.geometry_cache
    assert g.trigger_x is not None and g.pre_region and g.post_region and "FALLING" in g.trigger_label


def test_q6_u05_not_triggered_is_explicit(qtbot, panel, dialogs):
    panel.demo.setCurrentIndex(panel.demo.findData("half_adder"))
    panel.set_channels(["a", "carry"])
    panel.start.setText("100")
    panel.end.setText("200")
    panel.trigger_channel.setCurrentIndex(panel.trigger_channel.findData("carry"))
    panel.edge.setCurrentText("RISING")
    panel.start_capture()
    _wait(qtbot, panel)
    assert panel.state.value == "WARNING" and dialogs == []  # a result, not an error
    assert "NOT_TRIGGERED" in panel.status.text() and "nothing captured" in panel.status.text()
    assert panel.table.rowCount() == 0
    assert "NOT_TRIGGERED" in panel.waveform.summary()


def test_q6_u06_invalid_input_goes_through_d2_dialog(qtbot, panel, dialogs):
    panel.start.setText("1e3")
    panel.start_capture()
    assert panel.state.value == "ERROR" and "AC-VAL-001" in panel.status.text()
    assert dialogs and dialogs[-1][0] == "warning" and "1e3" not in dialogs[-1][2]
    panel.start.setText("0")
    panel.set_channels([])
    panel.start_capture()
    assert panel.state.value == "ERROR"


def test_q6_u07_same_timestamp_rows_and_inspection(qtbot, panel):
    panel.demo.setCurrentIndex(panel.demo.findData("xor3_glitch"))
    panel.set_channels(["y"])
    panel.start.setText("0.5")
    panel.end.setText("1.5")
    panel.trigger_channel.setCurrentIndex(0)
    panel.start_capture()
    _wait(qtbot, panel)
    rows = [[panel.table.item(r, c).text() for c in range(panel.table.columnCount())]
            for r in range(panel.table.rowCount())]
    assert rows == [["0", "1", "y", "Y", "LOW", "HIGH", "1/3"],
                    ["1", "1", "y", "Y", "HIGH", "LOW", "2/3"],
                    ["2", "1", "y", "Y", "LOW", "HIGH", "3/3"]]
    assert panel.inspect(1) == {"time": "1", "channel": "y", "net": "Y", "previous": "HIGH", "new": "LOW",
                                "index": 1, "same_time": (1, 3)}
    lane = panel.waveform.geometry_cache.lanes[0]
    assert len(lane.edges) == 1 and lane.edges[0].count == 3  # one column, three transitions, flagged
    assert panel.waveform.geometry_cache.merged_columns == 1
    assert "hold several transitions" in panel.waveform.summary()


def test_q6_u08_load_and_replay_in_ui(qtbot, panel):
    v = SVC.capture(req(trigger="y", edge="RISING", pre="1", post="1"))
    panel.load_text(v.trace_json)
    assert panel.view.status == "LOADED" and "LOADED" in panel.status.text()
    assert panel.table.rowCount() == len(v.transitions)
    panel.replay()
    assert "Replay: EQUIVALENT" in panel.status.text()
    panel.load_text('{"schema":"digital-trace","version":2}')
    assert panel.state.value == "ERROR"


def test_q6_u09_renderer_deterministic_and_exact():
    v = SVC.capture(req(channels=("a", "y"), start="0", end="4"))
    g1, g2 = layout_waveform(v, 900), layout_waveform(v, 900)
    assert g1 == g2
    assert g1.x_start == 150 and g1.x_end == 876
    assert [t for _, t in g1.ticks] == ["0", "1", "2", "3", "4"]
    lane_a = g1.lanes[0]
    assert lane_a.label == "a (A)"
    assert [e.x for e in lane_a.edges] == [150 + round(726 * k / 4) for k in (1, 2, 3)]  # half-even pixels
    assert [(e.before, e.after) for e in lane_a.edges] == [("LOW", "HIGH"), ("HIGH", "LOW"), ("LOW", "HIGH")]
    assert lane_a.segments[0] == (150, lane_a.edges[0].x, "LOW") and lane_a.segments[-1][2] == "HIGH"
    assert g1.transitions_total == sum(len(c.transitions) for c in v.channels)
    nt = SVC.capture(req(start="9", end="9", trigger="a", edge="RISING", pre="0", post="0"))
    assert "NOT_TRIGGERED" in layout_waveform(nt).message and layout_waveform(nt).lanes == ()
    assert layout_waveform(None).message == "No capture yet."


def test_q6_u10_widget_paint_is_deterministic_and_does_not_mutate(qtbot, panel):
    v = SVC.capture(req(trigger="y", edge="BOTH", pre="0.5", post="1.5"))
    snapshot = (v, v.trace_json, v.digest)
    panel.show_view(v)
    panel.waveform.resize(900, 300)
    img1 = panel.waveform.grab().toImage()
    img2 = panel.waveform.grab().toImage()
    assert img1 == img2
    assert (panel.view, panel.view.trace_json, panel.view.digest) == snapshot and panel.view is v
    assert SVC.load_trace(v.trace_json).digest == v.digest  # trace text untouched by the UI


# =============================================================== architecture

def _imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            mods.add(node.module or "")
    return tree, mods


def test_q6_x01_ui_never_touches_the_digital_domain():
    for name in ("logic_analyzer.py", "waveform.py"):
        tree, mods = _imports(SRC / "ui" / name)
        assert not any(m.startswith("academic_core.domain") for m in mods), (name, mods)
        assert not any(m.startswith("academic_core.infrastructure") for m in mods), name
        calls = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        assert not calls & {"evaluate", "fires", "analyze", "run_until", "step", "run", "to_json", "from_json",
                            "state_at", "schedule"}, (name, calls & {"evaluate", "fires", "analyze"})
        text = (SRC / "ui" / name).read_text(encoding="utf-8")
        assert "LogicAnalyzer(" not in text and "GateKind" not in text and "json.loads" not in text


def test_q6_x02_service_is_the_boundary():
    _, mods = _imports(SRC / "application" / "digital_service.py")
    assert not any(m.startswith("PySide6") for m in mods)
    assert "academic_core.domain.engineering.digital" in mods
    tree = ast.parse((SRC / "application" / "digital_service.py").read_text(encoding="utf-8"))
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    # reading samples to build views is mapping; evaluating, edge-testing or scheduling would be domain logic
    assert not attrs & {"evaluate", "fires", "state_at", "run_until", "schedule", "step", "_captured", "_evaluators"}
    classes = [n.name for f in SRC.rglob("*.py") for n in ast.walk(ast.parse(f.read_text(encoding="utf-8")))
               if isinstance(n, ast.ClassDef)]
    assert classes.count("LogicAnalyzer") == 1
    for f in (SRC / "domain").rglob("*.py"):
        _, mods = _imports(f)
        assert not any(m.startswith(("PySide6", "academic_core.ui", "academic_core.application")) for m in mods), f


def test_q6_x03_no_unsafe_primitives_in_new_modules():
    for f in (SRC / "application" / "digital_service.py", SRC / "ui" / "logic_analyzer.py",
              SRC / "ui" / "waveform.py"):
        tree, mods = _imports(f)
        assert not {m.split(".")[0] for m in mods} & {"pickle", "marshal", "subprocess", "importlib", "shelve"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in ("eval", "exec", "compile", "__import__"), f


# =============================================================== bounds

def test_q6_b01_large_capture_renders_bounded():
    c = DigitalCircuit()
    c.add_net("A", LogicState.LOW)
    c.add_stimulus(ToggleStimulus("t", "A", LogicState.HIGH, Decimal(0), Decimal("0.0001"), 20000))
    for k in range(4):
        c.add_probe(DigitalProbe(f"p{k}", "A"))
    r = LogicAnalyzer().capture(c, CaptureConfig(tuple(f"p{k}" for k in range(4)), Decimal(0), Decimal(2)))
    view = capture_view(r, "stress")
    t0 = time.perf_counter()
    g = layout_waveform(view, 900)
    elapsed = time.perf_counter() - t0
    assert g.transitions_total == 80000
    assert g.edges_drawn <= 4 * (g.x_end - g.x_start + 1)  # at most one edge per pixel column per lane
    assert g.merged_columns > 0  # merging is reported, never silent
    assert elapsed < 10
    assert isinstance(view, CaptureView) and len(view.transitions) == 80000  # the model keeps every one
