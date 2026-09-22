"""F8-Q.7 final certification -- whole-pipeline, static, determinism and bound audits.

This file adds no features. It checks F8-Q (Q1-Q6) as one system:

Input -> DigitalCircuit -> DigitalSimulator -> DigitalTrace -> Q4 serialization
-> Q4 replay -> LogicAnalyzer -> CaptureResult -> DigitalAnalysisService view
-> waveform renderer geometry -> verification.
"""

from __future__ import annotations

import ast
import hashlib
import os
import pathlib
import subprocess
import sys
import time
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from academic_core.application.digital_service import AnalyzerRequest, DigitalAnalysisService, capture_view
from academic_core.domain.engineering.digital import (
    MAX_NETS,
    CaptureConfig,
    CaptureStatus,
    DigitalCircuit,
    DigitalComponent,
    DigitalProbe,
    DigitalSimulator,
    DigitalTrace,
    GateEvaluator,
    GateKind,
    LogicAnalyzer,
    LogicState,
    PatternStimulus,
    ToggleStimulus,
    TriggerConfig,
    TriggerEdge,
    verify_capture,
    verify_replay,
)
from academic_core.domain.engineering.digital import components as comp_mod

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "academic_core"
DIGITAL = SRC / "domain" / "engineering" / "digital"
F8Q_MODULES = sorted(DIGITAL.glob("*.py")) + [SRC / "application" / "digital_service.py",
                                              SRC / "ui" / "logic_analyzer.py", SRC / "ui" / "waveform.py"]
D = Decimal
L, H = LogicState.LOW, LogicState.HIGH


def mixed_circuit():
    """N-ary gates (2, 3, 8 pins), repeated input nets, cascades, same-time glitches."""
    c = DigitalCircuit()
    for x in ("A", "B", "C", "D", "P", "Q", "R", "S", "T"):
        c.add_net(x, L)
    c.add_component(DigitalComponent("g1", GateKind.NAND, ("A", "B", "A"), "P"))
    c.add_component(DigitalComponent("g2", GateKind.XNOR, ("P", "C", "D", "C"), "Q"))
    c.add_component(DigitalComponent("g3", GateKind.NOR, ("Q", "A", "D"), "R"))
    c.add_component(DigitalComponent("g4", GateKind.XOR, ("P", "Q", "R", "B", "B", "C", "D", "A"), "S"))
    c.add_component(DigitalComponent("g5", GateKind.NOT, ("S",), "T"))
    c.add_stimulus(ToggleStimulus("tA", "A", H, D(0), D("0.5"), 9))
    c.add_stimulus(PatternStimulus("pB", "B", D(0), D("0.5"), (H, H, L, H, L, L, H, L, H)))
    c.add_stimulus(ToggleStimulus("tC", "C", H, D(0), D("1.0"), 5))
    c.add_stimulus(PatternStimulus("pD", "D", D("0.5"), D("1.0"), (H, L, H, H)))
    for p, net in (("ch_P", "P"), ("ch_S", "S"), ("ch_T", "T"), ("ch_A", "A"), ("ch_A2", "A")):
        c.add_probe(DigitalProbe(p, net))
    return c


CONFIG = CaptureConfig(("ch_A", "ch_P", "ch_S", "ch_T"), D(0), D(5),
                       TriggerConfig("ch_S", TriggerEdge.FALLING, D("0.75"), D("1.5")))


def pipeline():
    """Every F8-Q stage in order; returns what each boundary produced."""
    sim = DigitalSimulator(mixed_circuit())
    sim.run()
    trace = sim.trace()  # Q3R
    text = trace.to_json()  # Q4 serialize
    loaded = DigitalTrace.from_json(text)  # Q4 deserialize
    replayed = verify_replay(loaded)  # Q4 replay + verify
    result = LogicAnalyzer().analyze(replayed, CONFIG)  # Q5 on the replayed trace
    view = capture_view(result, "mixed")  # Q6 application view
    from academic_core.ui.waveform import layout_waveform
    geometry = layout_waveform(view, 1000)  # Q6 renderer
    return trace, text, replayed, result, view, geometry


# =============================================================== end-to-end

def test_q7_e01_full_pipeline_is_consistent_at_every_boundary():
    trace, text, replayed, result, view, geometry = pipeline()
    assert replayed == trace and replayed.digest() == trace.digest()
    assert result.status is CaptureStatus.TRIGGERED
    # capturing live gives exactly what analyzing the serialized-and-replayed trace gave
    live = LogicAnalyzer().capture(mixed_circuit(), CONFIG)
    assert live.trace == result.trace and live.trigger_time == result.trigger_time
    assert live.trigger_index == result.trigger_index and live.trigger_edge == result.trigger_edge
    assert verify_capture(live) == live
    # the view is a faithful projection, the renderer consumes it unchanged
    assert view.digest == result.trace.digest() and view.trace_json == result.trace.to_json()
    assert sum(len(c.transitions) for c in view.channels) == result.trace.transition_count
    assert geometry.transitions_total == result.trace.transition_count
    assert geometry.trigger_x is not None and len(geometry.lanes) == len(CONFIG.channels)
    # a saved capture reloads and renders without running any circuit
    svc = DigitalAnalysisService()
    loaded_view = svc.load_trace(view.trace_json)
    assert loaded_view.channels == view.channels and svc.replay_trace(view.trace_json).status == "EQUIVALENT"


def test_q7_e02_service_equals_direct_domain_path():
    svc = DigitalAnalysisService()
    for demo in [d.key for d in svc.demos()]:
        channels = tuple(c.channel_id for c in svc.channels(demo))
        request = AnalyzerRequest(demo, channels, "0", "3", channels[-1], "BOTH", "0.5", "1")
        via_service = svc.capture(request)
        direct = LogicAnalyzer().capture(svc._circuit(demo), svc.build_config(request))
        assert via_service == capture_view(direct, demo), demo
        assert svc.verify(request).status == "EQUIVALENT", demo


# =============================================================== static architecture audit

def _tree(path):
    return ast.parse(path.read_text(encoding="utf-8"))


def _modules(tree):
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            out.add(node.module or "")
    return out


def test_q7_s01_no_forbidden_imports_or_dynamic_execution():
    banned_calls = {"eval", "exec", "compile", "__import__"}
    banned_mods = {"pickle", "marshal", "shelve", "subprocess", "importlib", "pkgutil", "ctypes", "multiprocessing"}
    for f in F8Q_MODULES:
        tree = _tree(f)
        assert not {m.split(".")[0] for m in _modules(tree)} & banned_mods, f.name
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in banned_calls, (f.name, node.func.id)
            if isinstance(node, ast.Attribute):
                assert node.attr not in ("system", "popen", "entry_points"), (f.name, node.attr)
        assert "shell=True" not in f.read_text(encoding="utf-8"), f.name


def test_q7_s02_deterministic_core_has_no_clock_rng_logging_or_qt():
    for f in sorted(DIGITAL.glob("*.py")):
        mods = {m.split(".")[0] for m in _modules(_tree(f))}
        assert not mods & {"time", "datetime", "random", "uuid", "secrets", "logging", "threading", "asyncio",
                           "PySide6", "os", "sys", "io", "pathlib"}, (f.name, mods)


def test_q7_s03_dependency_direction():
    for f in (SRC / "domain").rglob("*.py"):
        mods = _modules(_tree(f))
        assert not any(m.startswith(("academic_core.application", "academic_core.ui", "PySide6")) for m in mods), f
    for f in (SRC / "application").rglob("*.py"):
        mods = _modules(_tree(f))
        assert not any(m.startswith(("academic_core.ui", "PySide6")) for m in mods), f
    for name in ("logic_analyzer.py", "waveform.py"):
        mods = _modules(_tree(SRC / "ui" / name))
        assert not any(m.startswith(("academic_core.domain", "academic_core.infrastructure")) for m in mods), name


def test_q7_s04_single_logic_analyzer_and_no_ui_domain_logic():
    classes = [n.name for f in SRC.rglob("*.py") for n in ast.walk(_tree(f)) if isinstance(n, ast.ClassDef)]
    assert classes.count("LogicAnalyzer") == 1 and classes.count("DigitalAnalysisService") == 1
    for name in ("logic_analyzer.py", "waveform.py"):
        text = (SRC / "ui" / name).read_text(encoding="utf-8")
        for token in ("GateKind", "LogicAnalyzer(", "DigitalSimulator", ".evaluate(", ".fires(", "json.loads"):
            assert token not in text, (name, token)


def test_q7_s05_no_new_runtime_dependency():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'dependencies = [\n  "PySide6>=6.7",\n]' in pyproject
    reqs = [x for x in (ROOT / "requirements.txt").read_text(encoding="utf-8").split() if x]
    assert reqs == ["PySide6>=6.7", "beautifulsoup4>=4.12", "lxml>=5.0", "pypdf>=5.0"]
    stdlib = set(sys.stdlib_module_names)
    for f in F8Q_MODULES:
        for m in _modules(_tree(f)):
            top = m.split(".")[0]
            assert top in stdlib or top in ("academic_core", "PySide6", "__future__"), (f.name, m)


# =============================================================== determinism audit

_CHILD = """
import hashlib, sys
sys.path.insert(0, {src!r})
sys.path.insert(0, {tests!r})
import test_f8q7_certification as m
trace, text, replayed, result, view, geometry = m.pipeline()
parts = [trace.digest(), hashlib.sha256(text.encode()).hexdigest(), replayed.digest(),
         result.status.value, str(result.trigger_time), str(result.trigger_index), view.digest,
         hashlib.sha256(repr(geometry).encode()).hexdigest()]
print("|".join(parts))
"""


def test_q7_d01_pipeline_identical_across_runs_processes_and_hash_seeds():
    first, second = pipeline(), pipeline()
    assert first[0] == second[0] and first[1] == second[1] and first[3] == second[3]
    assert first[4] == second[4] and first[5] == second[5]
    code = _CHILD.format(src=str(ROOT / "src"), tests=str(ROOT / "tests"))
    outputs = set()
    for seed in ("0", "1", "31337", "random"):
        env = dict(os.environ, PYTHONHASHSEED=seed, QT_QPA_PLATFORM="offscreen")
        res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env,
                             timeout=180, check=True)
        outputs.add(res.stdout.strip().splitlines()[-1])
    assert len(outputs) == 1
    trace, text = first[0], first[1]
    assert next(iter(outputs)).startswith(trace.digest() + "|" + hashlib.sha256(text.encode()).hexdigest())


# =============================================================== performance / bounds audit

def test_q7_p01_wide_gate_uses_incremental_evaluation_only(monkeypatch):
    n = MAX_NETS - 1  # 1023-input NAND + output = MAX_NETS nets
    c = DigitalCircuit()
    names = [f"i{k}" for k in range(n)]
    for k, x in enumerate(names):
        c.add_net(x, L if k == 0 else H)
    c.add_net("Y", L)
    c.add_component(DigitalComponent("nand", GateKind.NAND, tuple(names), "Y"))
    c.add_stimulus(ToggleStimulus("t", "i0", H, D(0), D("0.001"), 2000))
    c.add_probe(DigitalProbe("y", "Y"))
    c.add_probe(DigitalProbe("in", "i0"))
    calls = {"update": 0}
    original = GateEvaluator.update

    def counting(self, index, old, new):
        calls["update"] += 1
        return original(self, index, old, new)

    def forbidden(*_a, **_k):
        raise AssertionError("full N-ary reduction during capture")

    monkeypatch.setattr(GateEvaluator, "update", counting)
    monkeypatch.setattr(comp_mod, "_reduce", forbidden)  # any full O(N) evaluation would fail
    t0 = time.perf_counter()
    r = LogicAnalyzer().capture(c, CaptureConfig(("in", "y"), D(0), D(3), TriggerConfig(
        "y", TriggerEdge.RISING, D("0.01"), D("0.01"))))
    elapsed = time.perf_counter() - t0
    assert calls["update"] == 2000  # exactly one O(1) pin update per input edge
    assert r.triggered and len(r.source.channel("y").samples) == 1 + 2000  # start-up settle + one per edge
    assert elapsed < 20


def test_q7_p02_near_limit_same_timestamp_and_channels():
    c = DigitalCircuit()
    for x in ("A", "B", "C", "Y"):
        c.add_net(x, L)
    c.add_component(DigitalComponent("x3", GateKind.XOR, ("A", "B", "C"), "Y"))
    for sid, net in (("sA", "A"), ("sB", "B"), ("sC", "C")):
        c.add_stimulus(ToggleStimulus(sid, net, H, D(0), D("0.001"), 3000))
    for k in range(16):
        c.add_probe(DigitalProbe(f"p{k:02d}", "Y"))
    r = LogicAnalyzer().capture(c, CaptureConfig(tuple(f"p{k:02d}" for k in range(16)), D(0), D(10)))
    assert len(r.trace.channels[0].samples) == 9000  # 3 same-time transitions at each of 3000 instants
    assert r.trace.transition_count == 16 * 9000  # 144 000 <= MAX_CAPTURE_SAMPLES, nothing collapsed
    assert DigitalTrace.from_json(r.trace.to_json()) == r.trace


@pytest.mark.parametrize("count, ok", [(5000, True), (7000, False)])
def test_q7_p03_capture_and_wire_bounds_are_enforced_not_truncated(count, ok):
    c = DigitalCircuit()
    c.add_net("A", L)
    c.add_stimulus(ToggleStimulus("t", "A", H, D(0), D("0.0001"), count))
    for k in range(32):
        c.add_probe(DigitalProbe(f"p{k:02d}", "A"))
    config = CaptureConfig(tuple(f"p{k:02d}" for k in range(32)), D(0), D(1))
    if ok:
        r = LogicAnalyzer().capture(c, config)
        assert r.trace.transition_count == 32 * count
    else:
        from academic_core.errors import ValidationError
        with pytest.raises(ValidationError, match="CAPTURE_LIMIT"):
            LogicAnalyzer().capture(c, config)
