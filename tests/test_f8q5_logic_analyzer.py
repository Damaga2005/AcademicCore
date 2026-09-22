"""F8-Q.5 Logic Analyzer -- test suite.

Sections: configuration / trigger / capture / same timestamp / N-ary /
replay (Q4) / determinism (incl. separate processes) / bounds / security /
golden fixtures / properties.
Deterministic generation only (LCG, no RNG module, no hypothesis).
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from academic_core.domain.engineering.digital import (
    MAX_CAPTURE_CHANNELS,
    MAX_CAPTURE_SAMPLES,
    MAX_NETS,
    MAX_PROBES,
    MAX_TIME,
    CaptureConfig,
    CaptureResult,
    CaptureStatus,
    ConstantStimulus,
    DigitalCircuit,
    DigitalComponent,
    DigitalProbe,
    DigitalSimulator,
    DigitalTrace,
    GateKind,
    LogicAnalyzer,
    LogicState,
    PatternStimulus,
    ToggleStimulus,
    TraceChannel,
    TraceSample,
    TriggerConfig,
    TriggerEdge,
    canonical_time,
    verify_capture,
    verify_replay,
)
from academic_core.domain.entities import DomainError
from academic_core.errors import IntegrationError, ValidationError

D = Decimal
L, H = LogicState.LOW, LogicState.HIGH
R, F, B = TriggerEdge.RISING, TriggerEdge.FALLING, TriggerEdge.BOTH
DIGITAL_DIR = Path(__file__).resolve().parents[1] / "src" / "academic_core" / "domain" / "engineering" / "digital"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "logic_analyzer"
LA = LogicAnalyzer()


# =============================================================== builders

def toggle_circuit(first=H, start="0.5", period="0.5", count=6, initial=L):
    """A toggled by a stimulus, Y = NOT A; probes a, y."""
    c = DigitalCircuit()
    c.add_net("A", initial)
    c.add_net("Y", L)
    c.add_component(DigitalComponent("inv", GateKind.NOT, ("A",), "Y"))
    c.add_stimulus(ToggleStimulus("tA", "A", first, D(start), D(period), count))
    c.add_probe(DigitalProbe("a", "A"))
    c.add_probe(DigitalProbe("y", "Y"))
    return c


def xor3_circuit(pattern=(H, L)):
    """XOR(A,B,C) with all inputs switching together: Y glitches 3x per step."""
    c = DigitalCircuit()
    for x in ("A", "B", "C", "Y"):
        c.add_net(x, L)
    c.add_component(DigitalComponent("x3", GateKind.XOR, ("A", "B", "C"), "Y"))
    for sid, net in (("sA", "A"), ("sB", "B"), ("sC", "C")):
        c.add_stimulus(PatternStimulus(sid, net, D(1), D(1), pattern))
    c.add_probe(DigitalProbe("y", "Y"))
    c.add_probe(DigitalProbe("a", "A"))
    return c


def xnor2_circuit():
    """XNOR(A,B) = HIGH initially; both rise at t=1 -> Y: HIGH->LOW->HIGH at t=1."""
    c = DigitalCircuit()
    for x in ("A", "B", "Y"):
        c.add_net(x, L)
    c.add_component(DigitalComponent("xn", GateKind.XNOR, ("A", "B"), "Y"))
    c.add_stimulus(PatternStimulus("sA", "A", D(1), D(1), (H,)))
    c.add_stimulus(PatternStimulus("sB", "B", D(1), D(1), (H,)))
    c.add_probe(DigitalProbe("y", "Y"))
    return c


def gate_circuit(kind, n, pins=None, toggled=0, others=H):
    """N-ary gate; input ``toggled`` toggles, the rest are held at ``others``."""
    c = DigitalCircuit()
    names = [f"i{k}" for k in range(n)]
    for k, x in enumerate(names):
        c.add_net(x, L if k == toggled else others)
    c.add_net("Y", L)
    c.add_component(DigitalComponent("g", kind, tuple(pins or names), "Y"))
    c.add_stimulus(ToggleStimulus("t", names[toggled], H, D(1), D(1), 4))
    c.add_probe(DigitalProbe("y", "Y"))
    c.add_probe(DigitalProbe("in", names[toggled]))
    return c


def cfg(channels, start="0", end="10", trigger=None):
    return CaptureConfig(tuple(channels), D(start), D(end), trigger)


def trig(channel, edge, pre="0", post="0"):
    return TriggerConfig(channel, edge, D(pre), D(post))


def _lcg(seed):
    state = seed
    while True:
        state = (state * 6364136223846793005 + 1442695040888963407) % (1 << 64)
        yield state >> 33


def samples(result, channel):
    return [(canonical_time(s.time), s.state) for s in result.trace.channel(channel).samples]


# =============================================================== configuration

def test_q5_c01_valid_config_normalized_and_frozen():
    chosen = ["y", "a"]
    c = CaptureConfig(chosen, D("0.50"), D(2), trig("y", R, "0.1", "0.2"))
    assert c.channels == ("a", "y") and chosen == ["y", "a"]  # sorted copy; caller's list untouched
    assert c.start == D("0.5") and c.trigger.pre_trigger == D("0.1")
    assert c.horizon == D("2.2")
    for obj, attr in ((c, "channels"), (c, "start"), (c, "trigger"), (c.trigger, "edge")):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(obj, attr, None)
    assert CaptureConfig(("a",), 0, 3).end == D(3)  # int -> exact Decimal (Q1 check_time rule)
    assert CaptureConfig(("a",), D(3600), D(3600), trig("a", B, "0", "5")).horizon == MAX_TIME


@pytest.mark.parametrize("bad", [1.0, -1, D(-1), D("NaN"), D("Infinity"), D("-Infinity"), "1", True, None,
                                 MAX_TIME + 1])
def test_q5_c02_invalid_times(bad):
    with pytest.raises(ValidationError, match="INVALID_CAPTURE"):
        CaptureConfig(("a",), bad, D(1))
    with pytest.raises(ValidationError, match="INVALID_CAPTURE"):
        CaptureConfig(("a",), D(0), bad)
    with pytest.raises(ValidationError, match="INVALID_CAPTURE"):
        TriggerConfig("a", R, bad, D(0))
    with pytest.raises(ValidationError, match="INVALID_CAPTURE"):
        TriggerConfig("a", R, D(0), bad)


def test_q5_c03_invalid_window_and_decimal_precision():
    with pytest.raises(ValidationError, match="before start"):
        cfg(["a"], "2", "1")
    # exact arithmetic: a window that cannot be computed without rounding is refused
    with pytest.raises(ValidationError, match="INVALID_TIME"):
        CaptureConfig(("a",), D(0), D(3000), TriggerConfig("a", R, D(0), D("1E-500"))).horizon  # noqa: B018


@pytest.mark.parametrize("bad", [(), [], "a", b"a", None, 5, ("",), ("1a",), ("a b",), ("a", "a"), (1,),
                                 tuple(f"c{k}" for k in range(MAX_CAPTURE_CHANNELS + 1))])
def test_q5_c04_invalid_channels(bad):
    with pytest.raises(ValidationError):
        CaptureConfig(bad, D(0), D(1))


def test_q5_c05_invalid_trigger():
    for edge in ("RISING", "rising", None, 1, L):
        with pytest.raises(ValidationError, match="INVALID_TRIGGER"):
            TriggerConfig("a", edge, D(0), D(0))
    with pytest.raises(ValidationError, match="INVALID_ID"):
        TriggerConfig("", R, D(0), D(0))
    with pytest.raises(ValidationError, match="not selected"):
        cfg(["a"], trigger=trig("y", R))
    with pytest.raises(ValidationError, match="INVALID_TRIGGER"):
        CaptureConfig(("a",), D(0), D(1), {"channel": "a"})
    for bad in (0, -1, True, 10**7, "5"):
        with pytest.raises(ValidationError, match="INVALID_LIMIT"):
            LogicAnalyzer(max_events=bad)


def test_q5_c06_unknown_channels_and_inputs():
    with pytest.raises(ValidationError, match="UNKNOWN_PROBE"):
        LA.capture(toggle_circuit(), cfg(["a", "ghost"]))
    tr = verify_replay(LA.capture(toggle_circuit(), cfg(["a"])).trace)
    with pytest.raises(ValidationError, match="UNKNOWN_PROBE"):
        LA.analyze(tr, cfg(["y"]))
    with pytest.raises(ValidationError, match="INVALID_CIRCUIT"):
        LA.capture(object(), cfg(["a"]))
    with pytest.raises(ValidationError, match="INVALID_CAPTURE"):
        LA.capture(toggle_circuit(), {"channels": ["a"]})
    with pytest.raises(ValidationError, match="INVALID_TRACE"):
        LA.analyze("trace", cfg(["a"]))
    with pytest.raises(ValidationError, match="INVALID_CAPTURE"):
        verify_capture("result")


def test_q5_c07_circuit_is_captured_once():
    c = toggle_circuit()
    first = LA.capture(c, cfg(["a"]))
    with pytest.raises(DomainError, match="CIRCUIT_CHANGED"):
        LA.capture(c, cfg(["a"]))
    assert LA.capture(toggle_circuit(), cfg(["a"])) == first  # fresh circuit -> identical


# =============================================================== trigger

def test_q5_t01_rising_falling_both():
    # A: LOW, edges HIGH@0.5 LOW@1 HIGH@1.5 LOW@2 HIGH@2.5 LOW@3
    r = LA.capture(toggle_circuit(), cfg(["a"], trigger=trig("a", R)))
    assert (r.status, r.trigger_time, r.trigger_edge, r.trigger_index) == (CaptureStatus.TRIGGERED, D("0.5"), R, 0)
    f = LA.capture(toggle_circuit(), cfg(["a"], trigger=trig("a", F)))
    assert (f.trigger_time, f.trigger_edge) == (D(1), F)
    b = LA.capture(toggle_circuit(), cfg(["a"], "1.2", "10", trig("a", B)))
    assert (b.trigger_time, b.trigger_edge) == (D("1.5"), R)
    b2 = LA.capture(toggle_circuit(), cfg(["a"], "1.6", "10", trig("a", B)))
    assert (b2.trigger_time, b2.trigger_edge) == (D(2), F)
    y = LA.capture(toggle_circuit(), cfg(["a", "y"], trigger=trig("y", R)))  # Y = NOT A
    assert y.trigger_time == D(0) and y.trigger_channel == "y"  # start-up settle LOW->HIGH at t=0


def test_q5_t02_first_qualifying_edge_wins_and_arming_window():
    r = LA.capture(toggle_circuit(), cfg(["a"], "0.6", "10", trig("a", R)))
    assert r.trigger_time == D("1.5")  # the edge at 0.5 is before arming
    r = LA.capture(toggle_circuit(), cfg(["a"], "1.5", "1.5", trig("a", R)))
    assert r.trigger_time == D("1.5")  # arming window inclusive at both ends
    r = LA.capture(toggle_circuit(), cfg(["a"], "3.5", "10", trig("a", B)))
    assert r.status is CaptureStatus.NOT_TRIGGERED  # no edge after 3
    r = LA.capture(toggle_circuit(), cfg(["a"], "0", "0.4", trig("a", B)))
    assert r.status is CaptureStatus.NOT_TRIGGERED  # first edge after arming end


def test_q5_t03_initial_state_is_not_an_edge():
    for initial in (L, H):
        for edge in (R, F, B):  # the stimulus re-drives the initial state: a no-op, not an edge
            r = LA.capture(_fresh_constant(initial), cfg(["a"], trigger=trig("a", edge)))
            assert r.status is CaptureStatus.NOT_TRIGGERED
            assert r.source.channel("a").noop_count == 1 and r.source.channel("a").samples == ()
    # a real transition at t=0 does trigger
    c = DigitalCircuit()
    c.add_net("A", L)
    c.add_stimulus(ConstantStimulus("s", "A", H, D(0)))
    c.add_probe(DigitalProbe("a", "A"))
    r = LA.capture(c, cfg(["a"], trigger=trig("a", R)))
    assert r.triggered and r.trigger_time == D(0)


def _fresh_constant(initial):
    c = DigitalCircuit()
    c.add_net("A", initial)
    c.add_stimulus(ConstantStimulus("s", "A", initial, D(0)))
    c.add_probe(DigitalProbe("a", "A"))
    return c


def test_q5_t04_not_triggered_is_explicit_not_an_error():
    r = LA.capture(toggle_circuit(), cfg(["a", "y"], "5", "9", trig("a", R, "1", "1")))
    assert r.status is CaptureStatus.NOT_TRIGGERED and r.status.value == "NOT_TRIGGERED"
    assert not r.triggered and r.trace is None and r.window is None and r.requested_window is None
    assert r.trigger_time is None and r.trigger_edge is None and r.trigger_index is None
    assert r.trigger_channel == "a"  # configured channel stays visible
    assert [c.probe_id for c in r.source.channels] == ["a", "y"]  # what was searched
    empty = LA.capture(toggle_circuit(), cfg(["a"], "5", "9"))
    assert empty.status is CaptureStatus.CAPTURED and empty.trace.channel("a").samples == ()  # empty != NOT_TRIGGERED
    assert empty != r


# =============================================================== capture

def test_q5_w01_window_capture_boundaries_inclusive():
    r = LA.capture(toggle_circuit(), cfg(["a", "y"], "1", "2"))
    assert r.status is CaptureStatus.CAPTURED and r.window == (D(1), D(2))
    assert samples(r, "a") == [("1", L), ("1.5", H), ("2", L)]  # both boundaries kept
    assert r.trace.channel("a").initial is H  # state just before t=1
    assert r.trace.channel("y").initial is L
    assert r.requested_window == (D(1), D(2)) and r.trigger_channel is None


def test_q5_w02_pre_and_post_trigger():
    r = LA.capture(toggle_circuit(), cfg(["a", "y"], "1.2", "10", trig("a", R, "0.5", "0.5")))
    assert r.trigger_time == D("1.5") and r.window == (D(1), D(2))
    assert samples(r, "a") == [("1", L), ("1.5", H), ("2", L)]
    assert r.trace.channel("a").samples[r.trigger_index].time == D("1.5")
    r = LA.capture(toggle_circuit(), cfg(["a"], "1.2", "10", trig("a", R, "0", "0")))
    assert r.window == (D("1.5"), D("1.5")) and samples(r, "a") == [("1.5", H)]  # trigger sample retained
    r = LA.capture(toggle_circuit(), cfg(["a"], "0", "10", trig("a", R, "2", "0.25")))
    assert r.requested_window == (D(0), D("0.75")) and r.window == (D(0), D("0.75"))  # pre clipped at 0
    assert r.trace.channel("a").initial is L and samples(r, "a") == [("0.5", H)]


def test_q5_w03_post_trigger_beyond_last_event_is_held():
    r = LA.capture(toggle_circuit(), cfg(["a"], "2.9", "10", trig("a", F, "0", "100")))
    assert r.trigger_time == D(3) and r.window == (D(3), D(103))  # state held after last event
    assert r.source.end == D(110)  # horizon = end + post


def test_q5_w04_exact_decimal_times():
    c = toggle_circuit(start="0.1", period="0.1", count=5)
    r = LA.capture(c, cfg(["a"], "0.2", "10", trig("a", R, "0.1", "0.2")))
    assert r.trigger_time == D("0.3") and r.window == (D("0.2"), D("0.5"))
    assert [s.time for s in r.trace.channel("a").samples] == [D("0.2"), D("0.3"), D("0.4"), D("0.5")]
    assert '"start_time":"0.2"' in r.trace.to_json() and '"end_time":"0.5"' in r.trace.to_json()
    assert all(isinstance(s.time, Decimal) for s in r.trace.channel("a").samples)


def test_q5_w05_run_until_horizon_leaves_later_events_queued():
    c = toggle_circuit()
    sim = DigitalSimulator(c)
    done = sim.run_until(D("1.5"))
    assert max(e.time for e in done) == D("1.5") and not sim.queue.empty()
    assert sim.queue.peek().time == D(2)
    rest = sim.run_until(D(100))
    assert sim.queue.empty() and min(e.time for e in rest) == D(2)
    r = LA.capture(toggle_circuit(), cfg(["a"], "0", "1"))
    assert r.source.end == D(1) and [s.time for s in r.source.channel("a").samples] == [D("0.5"), D(1)]


def test_q5_w06_noop_counts_only_for_full_window():
    c = DigitalCircuit()
    c.add_net("A", H)
    c.add_stimulus(PatternStimulus("p", "A", D(0), D(1), (H, H, L, L, L, H)))
    c.add_probe(DigitalProbe("a", "A"))
    full = LA.capture(c, cfg(["a"], "0", "5"))
    assert full.window == (full.source.start, full.source.end)
    assert full.trace.channel("a").noop_count == 4 and full.trace == full.source
    part = LA.analyze(full.source, cfg(["a"], "1", "5"))
    assert part.trace.channel("a").noop_count == 0 and part.source.channel("a").noop_count == 4


def test_q5_w07_window_outside_loaded_trace():
    tr = LA.capture(toggle_circuit(), cfg(["a"], "0", "2")).trace
    with pytest.raises(ValidationError, match="CAPTURE_WINDOW"):
        LA.analyze(tr, cfg(["a"], "5", "6"))
    part = LA.analyze(tr, cfg(["a"], "1.5", "6"))
    assert part.window == (D("1.5"), D(2)) and part.requested_window == (D("1.5"), D(6))


# =============================================================== same timestamp

def test_q5_s01_low_high_low_high_at_one_timestamp():
    r = LA.capture(xor3_circuit(), cfg(["a", "y"], "0", "1.5"))
    assert samples(r, "y") == [("1", H), ("1", L), ("1", H)]
    assert r.trace.channel("y").initial is L
    for edge, index, got in ((R, 0, R), (F, 1, F), (B, 0, R)):
        t = LA.capture(xor3_circuit(), cfg(["a", "y"], trigger=trig("y", edge, "0", "0")))
        assert (t.trigger_time, t.trigger_index, t.trigger_edge) == (D(1), index, got)
        assert samples(t, "y") == [("1", H), ("1", L), ("1", H)]  # the whole same-time run kept
        assert t.trace.channel("y").samples[t.trigger_index].state is (H if got is R else L)


def test_q5_s02_high_low_high_at_one_timestamp():
    r = LA.capture(xnor2_circuit(), cfg(["y"], "0.5", "10", trig("y", R, "0", "0")))
    assert r.trace.channel("y").initial is H  # XNOR(L,L) settled HIGH at t=0
    assert samples(r, "y") == [("1", L), ("1", H)]
    assert (r.trigger_index, r.trigger_edge) == (1, R)
    f = LA.capture(xnor2_circuit(), cfg(["y"], "0.5", "10", trig("y", F, "0", "0")))
    assert (f.trigger_index, f.trigger_edge) == (0, F)


def test_q5_s03_trigger_inside_same_time_run_at_window_start():
    # second step at t=2: Y goes LOW, HIGH, LOW; FALLING arming from 1.5 picks t=2 index 0
    r = LA.capture(xor3_circuit(), cfg(["a", "y"], "1.5", "10", trig("y", F, "0", "0")))
    assert r.trigger_time == D(2) and r.trigger_index == 0
    assert r.trace.channel("y").initial is H  # state before the run at t=2
    assert samples(r, "y") == [("2", L), ("2", H), ("2", L)]
    r = LA.capture(xor3_circuit(), cfg(["a", "y"], "1.5", "10", trig("y", R, "0", "0")))
    assert r.trigger_index == 1  # second transition of the run is the rising one


def test_q5_s04_multi_channel_order_deterministic():
    runs = [LA.capture(xor3_circuit(), cfg(order, trigger=trig("y", B, "1", "1")))
            for order in (["y", "a"], ["a", "y"], ("y", "a"))]
    assert runs[0] == runs[1] == runs[2]
    assert [c.probe_id for c in runs[0].trace.channels] == ["a", "y"]
    assert len({r.trace.to_json() for r in runs}) == 1


# =============================================================== N-ary

ORACLE = {
    GateKind.AND: lambda b: all(b), GateKind.OR: lambda b: any(b), GateKind.XOR: lambda b: sum(b) % 2 == 1,
    GateKind.NAND: lambda b: not all(b), GateKind.NOR: lambda b: not any(b), GateKind.XNOR: lambda b: sum(b) % 2 == 0,
}


@pytest.mark.parametrize("kind", list(ORACLE))
@pytest.mark.parametrize("n", [2, 3, 8, 64])
def test_q5_n01_nary_gates_captured_like_the_oracle(kind, n):
    others = H if kind in (GateKind.AND, GateKind.NAND) else L  # the toggled pin controls Y
    r = LA.capture(gate_circuit(kind, n, others=others), cfg(["in", "y"], "0", "10"))
    probe_in, probe_y = r.trace.channel("in"), r.trace.channel("y")
    times = [D(0)] + [s.time for s in probe_in.samples]
    for t in times:  # Y after every input change equals the closed-form oracle
        bits = [probe_in.state_at(t) is H] + [others is H] * (n - 1)
        assert probe_y.state_at(t) is (H if ORACLE[kind](bits) else L), (kind, n, t)
    assert len([s for s in probe_y.samples if s.time > 0]) == len(probe_in.samples)  # one flip per edge
    edge = R if ORACLE[kind]([True] + [others is H] * (n - 1)) else F
    t = LA.capture(gate_circuit(kind, n, others=others), cfg(["in", "y"], "0.5", "10", trig("y", edge)))
    assert t.trigger_time == D(1), (kind, n)  # the first input edge at t=1 flips Y


def test_q5_n02_wide_gate_at_max_nets():
    n = MAX_NETS - 1
    r = LA.capture(gate_circuit(GateKind.NAND, n, others=H), cfg(["in", "y"], "0.5", "10", trig("y", F)))
    assert r.trigger_time == D(1)  # all inputs HIGH -> NAND LOW
    assert samples(r, "y") == [("1", L)]


def test_q5_n03_repeated_input_nets():
    # XOR(A, A, B) = B: Y follows B, never A
    c = DigitalCircuit()
    for x in ("A", "B", "Y"):
        c.add_net(x, L)
    c.add_component(DigitalComponent("x", GateKind.XOR, ("A", "A", "B"), "Y"))
    c.add_stimulus(ToggleStimulus("tA", "A", H, D(0), D("0.5"), 6))
    c.add_stimulus(PatternStimulus("pB", "B", D(1), D(1), (H, L)))
    c.add_probe(DigitalProbe("y", "Y"))
    c.add_probe(DigitalProbe("b", "B"))
    r = LA.capture(c, cfg(["b", "y"], trigger=trig("y", R, "1", "2")))
    assert r.trigger_time == D(1) and samples(r, "y") == samples(r, "b") == [("1", H), ("2", L)]


def test_q5_n04_analyzer_never_evaluates_gates():
    tree = ast.parse((DIGITAL_DIR / "analyzer.py").read_text(encoding="utf-8"))
    imported = {(n.module or "") for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert "academic_core.domain.engineering.digital.components" not in imported
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not names & {"evaluate", "evaluator", "update_net", "output_state", "_evaluators", "_captured"}
    classes = [n.name for f in DIGITAL_DIR.glob("*.py")
               for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))) if isinstance(n, ast.ClassDef)]
    assert classes.count("LogicAnalyzer") == 1


# =============================================================== replay (Q4)

@pytest.mark.parametrize("build, config", [
    (toggle_circuit, cfg(["a", "y"], trigger=trig("a", F, "0.5", "0.5"))),
    (xor3_circuit, cfg(["a", "y"], trigger=trig("y", F, "0", "0"))),
    (xnor2_circuit, cfg(["y"], "0", "3")),
])
def test_q5_r01_capture_serialize_replay_verify(build, config):
    r = LA.capture(build(), config)
    text = r.trace.to_json()
    back = DigitalTrace.from_json(text)
    assert back == r.trace and back.digest() == r.trace.digest()
    assert verify_replay(back) == r.trace
    assert verify_capture(r) == r
    # analyzing the Q4-loaded source gives the very same capture
    source = DigitalTrace.from_json(r.source.to_json())
    assert LA.analyze(source, config) == r


def test_q5_r02_mismatch_detection():
    r = LA.capture(xor3_circuit(), cfg(["a", "y"], trigger=trig("y", F, "0", "0")))
    for tampered in (dataclasses.replace(r, trigger_index=0), dataclasses.replace(r, trigger_time=D(2)),
                     dataclasses.replace(r, status=CaptureStatus.CAPTURED),
                     dataclasses.replace(r, trace=LA.analyze(r.source, cfg(["a", "y"], "0", "1")).trace)):
        with pytest.raises(IntegrationError, match="REPLAY_MISMATCH") as info:
            verify_capture(tampered)
        assert info.value.code == "AC-INT-001"
    nt = LA.capture(toggle_circuit(), cfg(["a"], "9", "9", trig("a", R)))
    assert verify_capture(nt) == nt  # NOT_TRIGGERED verifies too (no captured trace)


# =============================================================== determinism

def test_q5_d01_repeated_runs_identical():
    config = cfg(["a", "y"], "0.5", "10", trig("y", B, "0.5", "1"))
    runs = [LA.capture(xor3_circuit(), config) for _ in range(5)]
    assert all(r == runs[0] for r in runs)
    assert len({r.trace.to_json() for r in runs}) == 1 and len({r.source.digest() for r in runs}) == 1


_CHILD = """
import sys
sys.path.insert(0, {src!r})
sys.path.insert(0, {tests!r})
import test_f8q5_logic_analyzer as m
from academic_core.domain.engineering.digital import verify_capture
out = []
for build, config in m.determinism_cases():
    r = m.LA.capture(build(), config)
    verify_capture(r)
    out.append(r.status.value + ":" + str(r.trigger_time) + ":" + str(r.trigger_index) + ":" +
               (r.trace.digest() if r.trace is not None else "-") + ":" + r.source.digest())
print("|".join(out))
"""


def determinism_cases():
    return [
        (xor3_circuit, cfg(["a", "y"], trigger=trig("y", F, "0", "0"))),
        (toggle_circuit, cfg(["a", "y"], "1.2", "10", trig("a", B, "0.25", "1"))),
        (toggle_circuit, cfg(["a"], "7", "8", trig("a", R))),
        (lambda: gate_circuit(GateKind.XNOR, 17, others=L), cfg(["in", "y"], "0", "5")),
    ]


def test_q5_d02_separate_processes_and_hash_seeds():
    src = str(DIGITAL_DIR.parents[3])
    code = _CHILD.format(src=src, tests=str(Path(__file__).resolve().parent))
    outputs = set()
    for seed in ("0", "1", "4242", "random"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env,
                             timeout=120, check=True)
        outputs.add(res.stdout.strip())
    assert len(outputs) == 1
    assert "NOT_TRIGGERED:None:None:-" in next(iter(outputs))


# =============================================================== bounds

def test_q5_b01_event_budget():
    with pytest.raises(DomainError, match="EVENT_LIMIT"):
        LogicAnalyzer(max_events=5).capture(toggle_circuit(count=50), cfg(["a"], "0", "100"))
    ok = LogicAnalyzer(max_events=5).capture(toggle_circuit(count=2), cfg(["a"], "0", "0.9"))
    assert len(ok.source.channel("a").samples) == 1  # the horizon stops processing at 0.9


def test_q5_b02_capture_sample_limit():
    c = DigitalCircuit()
    c.add_net("A", L)
    c.add_stimulus(ToggleStimulus("t", "A", H, D(0), D("0.0001"), 7000))
    for k in range(MAX_PROBES):
        c.add_probe(DigitalProbe(f"p{k:02d}", "A"))
    everything = tuple(f"p{k:02d}" for k in range(MAX_PROBES))
    with pytest.raises(ValidationError, match="CAPTURE_LIMIT"):
        LA.capture(c, CaptureConfig(everything, D(0), D(1)))
    assert MAX_CAPTURE_SAMPLES == 200_000 and MAX_CAPTURE_CHANNELS == 32


def test_q5_b03_window_and_horizon_bounded_by_max_time():
    r = LA.capture(toggle_circuit(), CaptureConfig(("a",), D(0), MAX_TIME, trig("a", F, "0", str(MAX_TIME))))
    assert r.source.end == MAX_TIME and r.window == (D(1), MAX_TIME)


# =============================================================== security

def test_q5_x01_source_policy():
    banned_calls = {"eval", "exec", "compile", "__import__", "getattr", "setattr", "globals", "locals",
                    "vars", "open", "print", "id", "hash", "input", "breakpoint"}
    banned_modules = {"pickle", "marshal", "shelve", "importlib", "subprocess", "os", "sys", "io", "pathlib",
                      "time", "datetime", "random", "uuid", "logging", "threading", "PySide6", "json"}
    for name in ("analyzer.py", "core.py"):
        tree = ast.parse((DIGITAL_DIR / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in banned_calls, (name, node.func.id)
            if isinstance(node, ast.Import):
                assert not {a.name.split(".")[0] for a in node.names} & banned_modules, name
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in banned_modules, name


def test_q5_x02_result_is_immutable_value():
    r = LA.capture(toggle_circuit(), cfg(["a"], trigger=trig("a", R, "0", "1")))
    for attr in ("status", "trace", "source", "trigger_time", "config"):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(r, attr, None)
    assert isinstance(r.trace.channels, tuple) and isinstance(r.trace.channels[0].samples, tuple)
    assert not any(isinstance(v, (DigitalCircuit, DigitalSimulator)) for v in vars(r).values())


# =============================================================== golden fixtures

GOLDEN = {
    "rising_pre_post": (toggle_circuit, cfg(["a", "y"], "1.2", "10", trig("a", R, "0.5", "0.5"))),
    "falling_same_timestamp": (xor3_circuit, cfg(["a", "y"], trigger=trig("y", F, "0", "0"))),
    "high_low_high": (xnor2_circuit, cfg(["y"], trigger=trig("y", F, "1", "1"))),
    "window_capture": (xor3_circuit, cfg(["a", "y"], "0.5", "2.5")),
}
GOLDEN_META = {  # status, trigger time, trigger index, SHA-256 of the captured canonical bytes
    "rising_pre_post": ("TRIGGERED", "1.5", 1, "9e4895cc8b863212af2eb05f56a215fe0e655bf53b4ad543de40f3cd67af9835"),
    "falling_same_timestamp": ("TRIGGERED", "1", 1, "4a856680e73c2a35d7ddd1c702271d1d6d5e520fdb7659b4c4149a46b1b72eb8"),
    "high_low_high": ("TRIGGERED", "1", 1, "d719359142c5d3fede44ea0367d5b8ed6c1f7e01e3abecb6481deff1cd5cd898"),
    "window_capture": ("CAPTURED", "None", None, "f0280684f5be697818903dc6de0af0a00c7ef8f0a8257a588b173b9f8442f67f"),
}


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_q5_g01_golden_captures(name):
    build, config = GOLDEN[name]
    r = LA.capture(build(), config)
    raw = (FIXTURES / f"{name}.json").read_bytes()
    assert raw == r.trace.canonical_bytes() + b"\n"
    status, t, index, digest = GOLDEN_META[name]
    assert (r.status.value, str(r.trigger_time), r.trigger_index) == (status, t, index)
    assert hashlib.sha256(raw.rstrip(b"\n")).hexdigest() == digest == r.trace.digest()
    assert verify_replay(DigitalTrace.from_json(raw)) == r.trace


def test_q5_g02_golden_set_is_complete():
    assert sorted(p.stem for p in FIXTURES.glob("*.json")) == sorted(GOLDEN)


# =============================================================== properties

def _random_circuit(rng):
    nxt = lambda n: next(rng) % n  # noqa: E731
    kinds = list(ORACLE) + [GateKind.NOT]
    c = DigitalCircuit()
    inputs = [f"i{k}" for k in range(2 + nxt(3))]
    for x in inputs:
        c.add_net(x, H if nxt(2) else L)
    for k, x in enumerate(inputs):
        states = tuple(H if nxt(2) else L for _ in range(1 + nxt(6)))
        c.add_stimulus(PatternStimulus(f"s{k}", x, D(nxt(4)) / 4, D(1) / 4, states))
    outs = []
    for g in range(1 + nxt(3)):
        kind = kinds[nxt(len(kinds))]
        pool = inputs + outs
        pins = (pool[nxt(len(pool))],) if kind is GateKind.NOT else tuple(pool[nxt(len(pool))]
                                                                         for _ in range(2 + nxt(3)))
        out = f"o{g}"
        c.add_net(out, H if nxt(2) else L)
        c.add_component(DigitalComponent(f"g{g}", kind, pins, out))
        outs.append(out)
    nets = inputs + outs
    probes = sorted({nets[nxt(len(nets))] for _ in range(1 + nxt(4))} | {outs[-1]})
    for net in probes:
        c.add_probe(DigitalProbe(f"p_{net}", net))
    return c, [f"p_{n}" for n in probes]


def _brute_trigger(channel, trigger, start, end):
    prev = channel.initial
    for k, s in enumerate(channel.samples):
        rising = prev is L and s.state is H
        ok = {R: rising, F: not rising, B: True}[trigger.edge]
        if start <= s.time <= end and ok:
            return k, s
        prev = s.state
    return None


def test_q5_p01_capture_properties():
    rng = _lcg(20260922)
    nxt = lambda n: next(rng) % n  # noqa: E731
    seen = set()
    for case in range(120):
        circuit, channels = _random_circuit(rng)
        chosen = channels[: 1 + nxt(len(channels))]
        start = D(nxt(8)) / 4
        end = start + D(nxt(8)) / 4
        trigger = None
        if nxt(4):
            trigger = TriggerConfig(chosen[nxt(len(chosen))], (R, F, B)[nxt(3)], D(nxt(4)) / 4, D(nxt(6)) / 4)
        config = CaptureConfig(tuple(chosen), start, end, trigger)
        r = LA.capture(circuit, config)
        seen.add(r.status)
        src = r.source
        if trigger is not None:
            found = _brute_trigger(src.channel(trigger.channel), trigger, start, end)
            assert (r.status is CaptureStatus.TRIGGERED) == (found is not None), case
            if found is not None:
                k, s = found
                assert r.trigger_time == s.time
                captured = r.trace.channel(trigger.channel).samples
                assert captured[r.trigger_index].time == s.time and captured[r.trigger_index].state is s.state
                # the trigger sample is the k-th source sample: same number of earlier in-window samples
                assert r.trigger_index == sum(1 for x in src.channel(trigger.channel).samples[:k]
                                              if x.time >= r.trace.start)
        if r.trace is not None:
            ws, we = r.window
            assert src.start <= ws <= we <= src.end
            for ch in r.trace.channels:
                full = src.channel(ch.probe_id)
                inside = [(s.time, s.state) for s in full.samples if ws <= s.time <= we]
                assert [(s.time, s.state) for s in ch.samples] == inside
                before = [s.state for s in full.samples if s.time < ws]
                assert ch.initial is (before[-1] if before else full.initial)
            assert DigitalTrace.from_json(r.trace.to_json()) == r.trace
        assert LA.analyze(DigitalTrace.from_json(src.to_json()), config) == r
        assert verify_capture(r) == r
    assert seen == set(CaptureStatus)


def test_q5_p02_sample_constructor_rejects_forged_order():
    # the analyzer builds traces only through the validated Q3R constructors
    with pytest.raises(ValidationError, match="INVALID_TRACE"):
        TraceChannel("a", "A", L, (TraceSample(D(2), 0, H), TraceSample(D(1), 1, L)))
    assert isinstance(LA.capture(toggle_circuit(), cfg(["a"])), CaptureResult)
