"""F8-Q.1 digital core -- test suite.

Test IDs Q1-001..Q1-020 follow the F8-Q.1 phase brief; Q1-P* are
seeded-permutation property checks (no hypothesis dependency), Q1-S*
static purity/security checks (design SEC-D01/D02, DIG-I006).
"""

from __future__ import annotations

import ast
import dataclasses
import random
from decimal import Decimal
from pathlib import Path

import pytest

from academic_core.domain.engineering.digital import (
    MAX_TIME,
    DigitalCircuit,
    DigitalEvent,
    DigitalNet,
    DigitalSimulator,
    EventQueue,
    LogicState,
    check_time,
)
from academic_core.domain.entities import DomainError
from academic_core.errors import AcademicCoreError, ValidationError, to_ui_error

D = Decimal
L, H = LogicState.LOW, LogicState.HIGH
DIGITAL_DIR = (Path(__file__).resolve().parents[1] / "src" / "academic_core"
               / "domain" / "engineering" / "digital")


def ev(t, seq, sid="e", net="a", state=H):
    return DigitalEvent(D(t) if isinstance(t, str) else t, seq, sid, net, state)


# --------------------------------------------------------------- LogicState

def test_q1_001_logic_state_low():
    assert L.value == 0 and L.name == "LOW" and LogicState(0) is L


def test_q1_002_logic_state_high():
    assert H.value == 1 and LogicState(1) is H
    assert L < H and hash(H) == hash(LogicState.HIGH)


@pytest.mark.parametrize("bad", [0, 1, True, False, "HIGH", None, 2])
def test_q1_003_invalid_logic_state(bad):
    with pytest.raises(ValidationError, match="INVALID_STATE"):
        DigitalNet("a", "a", bad)
    with pytest.raises(ValidationError, match="INVALID_STATE"):
        ev("0", 0, state=bad)
    with pytest.raises(ValueError):
        LogicState(2)


# --------------------------------------------------------------- time

def test_q1_004_decimal_time():
    assert check_time(D("0.001")) == D("0.001")
    assert check_time(3) == D(3) and isinstance(check_time(3), Decimal)
    assert D(0) < D(1) < D(2)
    assert D("0.1") == D("0.10")  # Decimal semantics: same instant
    # zero-delay: the timestamp is preserved exactly (representation kept)
    assert str(ev("10.000000", 0).time) == "10.000000"
    assert check_time(MAX_TIME) == MAX_TIME


@pytest.mark.parametrize("bad, reason", [
    (D(-1), "NEGATIVE_TIME"), (-1, "NEGATIVE_TIME"),
    (D("NaN"), "INVALID_TIME"), (D("sNaN"), "INVALID_TIME"),
    (D("Infinity"), "INVALID_TIME"), (D("-Infinity"), "INVALID_TIME"),
    (1.0, "INVALID_TIME"), (True, "INVALID_TIME"), ("1", "INVALID_TIME"),
    (None, "INVALID_TIME"), (MAX_TIME + 1, "TIME_LIMIT"),
])
def test_q1_005_negative_and_invalid_time(bad, reason):
    with pytest.raises(ValidationError, match=reason):
        check_time(bad)
    with pytest.raises(ValidationError, match=reason):
        DigitalEvent(bad, 0, "e", "a", H)


# --------------------------------------------------------------- events

def test_q1_006_event_immutability():
    e = ev("1", 0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        e.time = D(0)
    q = EventQueue()
    q.push(ev("2", 1, "late"))
    q.push(e)
    with pytest.raises(dataclasses.FrozenInstanceError):
        e.sequence = 99
    assert q.pop() is e


def test_q1_007_event_ordering_by_time():
    a, b, c = ev("2", 0), ev("0", 1), ev("1", 2)
    assert sorted([a, b, c]) == [b, c, a]
    assert ev("0.1", 1) < ev("0.2", 0)


def test_q1_008_sequence_ordering_same_timestamp():
    es = [ev("1.0", s, sid) for s, sid in ((2, "a"), (0, "z"), (1, "m"))]
    assert [e.sequence for e in sorted(es)] == [0, 1, 2]
    # 0.1 vs 0.10: equal times, so sequence decides
    assert ev("0.10", 0) < ev("0.1", 1)


def test_q1_009_stable_id_tie_break():
    es = [ev("1.0", 5, sid) for sid in ("c", "a", "b")]
    assert [e.stable_id for e in sorted(es)] == ["a", "b", "c"]


@pytest.mark.parametrize("bad", [-1, 1.0, True, "0", None])
def test_q1_invalid_sequence(bad):
    with pytest.raises(ValidationError, match="INVALID_SEQUENCE"):
        ev("0", bad)


@pytest.mark.parametrize("bad", ["", " ", "1abc", "a b", "a" * 65, None, 3, "é"])
def test_q1_invalid_ids(bad):
    with pytest.raises(ValidationError, match="INVALID_ID"):
        ev("0", 0, sid=bad)
    with pytest.raises(ValidationError, match="INVALID_ID"):
        DigitalNet(bad, "n", L)


# --------------------------------------------------------------- queue

def test_q1_010_queue_push_pop():
    q = EventQueue()
    events = [ev("1", 1, "b"), ev("0", 2, "a"), ev("1", 0, "c"), ev("1", 1, "a")]
    for e in events:
        q.push(e)
    assert q.peek() == ev("0", 2, "a") and q.size() == 4
    assert [q.pop().key for _ in range(4)] == [
        (D(0), 2, "a"), (D(1), 0, "c"), (D(1), 1, "a"), (D(1), 1, "b")]


def test_q1_011_queue_empty():
    q = EventQueue()
    assert q.empty()
    for op in (q.pop, q.peek):
        with pytest.raises(DomainError, match="EMPTY_QUEUE"):
            op()
    q.push(ev("0", 0))
    assert not q.empty()
    q.pop()
    assert q.empty()


def test_q1_012_queue_size():
    q = EventQueue()
    for i in range(5):
        q.push(ev(str(i), i))
    assert q.size() == len(q) == 5
    q.pop()
    assert q.size() == 4


def test_q1_013_queue_bound():
    q = EventQueue(max_events=3)
    for i in range(3):
        q.push(ev("0", i))
    with pytest.raises(DomainError, match="EVENT_LIMIT") as info:
        q.push(ev("0", 3))
    assert info.value.code == "AC-DOM-001" and q.size() == 3
    q.pop()
    q.push(ev("0", 3))  # room again after a pop
    for bad in (0, -1, True, 10**7):
        with pytest.raises(ValidationError, match="INVALID_LIMIT"):
            EventQueue(bad)


def test_q1_013b_simulator_total_event_bound():
    c = DigitalCircuit()
    c.add_net("a", L)
    sim = DigitalSimulator(c, max_events=2)
    sim.schedule(D(0), "a", H)
    sim.run()
    sim.schedule(D(1), "a", L)
    sim.run()
    # queue is empty, but the per-run total is capped
    with pytest.raises(DomainError, match="EVENT_LIMIT"):
        sim.schedule(D(2), "a", H)


def test_q1_duplicate_canonical_key_forbidden():
    q = EventQueue()
    q.push(ev("1.0", 0, "x", net="a", state=H))
    # same key, different target: still refused, never order-by-insertion
    with pytest.raises(ValidationError, match="DUPLICATE_EVENT"):
        q.push(ev("1.00", 0, "x", net="b", state=L))
    assert q.size() == 1
    q.pop()
    q.push(ev("1", 0, "x"))  # allowed once the original left the queue


# --------------------------------------------------------------- nets / circuit

def test_q1_014_net_creation():
    c = DigitalCircuit()
    n = c.add_net("clk", L, name="Clock")
    assert (n.net_id, n.name, n.state) == ("clk", "Clock", L)
    assert c.add_net("d0", H).name == "d0"
    with pytest.raises(dataclasses.FrozenInstanceError):
        n.state = H
    assert n.with_state(H).state is H and n.state is L
    with pytest.raises(ValidationError, match="INVALID_NAME"):
        c.add_net("x", L, name="")


def test_q1_015_duplicate_net():
    c = DigitalCircuit()
    c.add_net("a", L)
    with pytest.raises(ValidationError, match="DUPLICATE_NET"):
        c.add_net("a", H, name="other")
    assert c.state("a") is L  # not silently overwritten


def test_q1_net_limit():
    c = DigitalCircuit(max_nets=2)
    c.add_net("a", L)
    c.add_net("b", L)
    with pytest.raises(DomainError, match="NET_LIMIT"):
        c.add_net("c", L)


def test_q1_016_net_lookup():
    c = DigitalCircuit()
    for nid in ("b", "a", "c"):
        c.add_net(nid, L)
    assert c.net("a").net_id == "a" and c.state("b") is L
    assert [n.net_id for n in c.nets()] == ["a", "b", "c"]  # sorted, not insertion
    assert c.states() == (("a", L), ("b", L), ("c", L))


def test_q1_017_event_applies_to_net():
    c = DigitalCircuit()
    c.add_net("a", L)
    assert c.apply(ev("0", 0, net="a", state=H)) is True
    assert c.state("a") is H
    assert c.apply(ev("1", 1, net="a", state=H)) is False  # no transition
    assert c.state("a") is H


def test_q1_018_unknown_net():
    c = DigitalCircuit()
    c.add_net("a", L)
    for call in (lambda: c.apply(ev("0", 0, net="ghost")),
                 lambda: c.net("ghost"),
                 lambda: c.net(None),
                 lambda: DigitalSimulator(c).schedule(D(0), "ghost", H)):
        with pytest.raises(DomainError, match="UNKNOWN_NET") as info:
            call()
        assert not isinstance(info.value, KeyError)


# --------------------------------------------------------------- simulator

def _scenario():
    c = DigitalCircuit()
    for nid in ("a", "b", "c"):
        c.add_net(nid, L)
    sim = DigitalSimulator(c)
    sim.schedule(D("2"), "c", H)            # event C
    sim.schedule(D("1.0"), "a", H)          # event A
    sim.schedule(D("1.00"), "b", H)         # event B, same instant as A
    sim.schedule(D("1"), "a", L, "a_fall")  # same instant, later sequence
    return sim, sim.run()


def test_q1_019_deterministic_repeated_run():
    runs = [_scenario() for _ in range(3)]
    keys = [[e.key for e in events] for _, events in runs]
    finals = [sim.circuit.states() for sim, _ in runs]
    assert keys[0] == keys[1] == keys[2]
    assert finals[0] == finals[1] == finals[2]
    sim, events = runs[0]
    assert [(e.net_id, e.sequence) for e in events] == [("a", 1), ("b", 2), ("a", 3), ("c", 0)]
    assert sim.circuit.states() == (("a", L), ("b", H), ("c", H))
    assert sim.now == D(2) and sim.processed == events
    assert [str(e.time) for e in events] == ["1.0", "1.00", "1", "2"]  # zero-delay, exact


def test_q1_sequence_policy_and_causality():
    c = DigitalCircuit()
    c.add_net("a", L)
    sim = DigitalSimulator(c)
    seqs = [sim.schedule(D(i), "a", H if i % 2 else L).sequence for i in range(3)]
    assert seqs == [0, 1, 2]
    sim.step()
    sim.step()
    assert sim.now == D(1)
    with pytest.raises(DomainError, match="CAUSALITY"):
        sim.schedule(D("0.5"), "a", H)
    assert sim.schedule(D(1), "a", L, "same_instant").sequence == 3  # t == now is fine
    with pytest.raises(ValidationError, match="INVALID_CIRCUIT"):
        DigitalSimulator(object())


def test_q1_020_domain_error_compatibility():
    c = DigitalCircuit()
    c.add_net("a", L)
    errors = []
    for call in (lambda: c.add_net("a", L), lambda: c.net("x"), lambda: check_time(D(-1))):
        try:
            call()
        except AcademicCoreError as exc:
            errors.append(exc)
    q = EventQueue(1)
    q.push(ev("0", 0))
    try:
        q.push(ev("0", 1))
    except AcademicCoreError as exc:
        errors.append(exc)
    assert len(errors) == 4
    for exc in errors:
        assert isinstance(exc, ValueError)  # D2: every except ValueError still works
        assert exc.code in ("AC-VAL-001", "AC-DOM-001")
        ui = to_ui_error(exc)
        assert ui.error_code == exc.code and "Traceback" not in ui.safe_message


# --------------------------------------------------------------- properties

@pytest.mark.parametrize("seed", range(20))
def test_q1_p01_queue_always_pops_minimum_key(seed):
    rng = random.Random(seed)
    events = [ev(D(rng.randint(0, 5)) / 4, rng.randint(0, 3), rng.choice("abcd") + str(i))
              for i in range(200)]
    q = EventQueue()
    for e in events:
        q.push(e)
    out = [q.pop() for _ in range(len(events))]
    assert out == sorted(events)
    assert all(x.key < y.key for x, y in zip(out, out[1:]))


@pytest.mark.parametrize("seed", range(10))
def test_q1_p02_insertion_order_irrelevant(seed):
    events = [ev(D(i % 7) / 3, i % 5, f"s{i}") for i in range(500)]
    shuffled = events[:]
    random.Random(seed).shuffle(shuffled)
    q1, q2 = EventQueue(), EventQueue()
    for e in events:
        q1.push(e)
    for e in shuffled:
        q2.push(e)
    assert [q1.pop() for _ in events] == [q2.pop() for _ in events]


def test_q1_p03_medium_bounded_queue():
    c = DigitalCircuit()
    for i in range(64):
        c.add_net(f"n{i}", L)
    sim = DigitalSimulator(c, max_events=20_000)
    n = 64 * 312  # whole sweeps; sweep 311 (odd) drives LOW
    for i in range(n):
        sim.schedule(D(i) / 1000, f"n{i % 64}", H if (i // 64) % 2 == 0 else L)
    events = sim.run()
    assert len(events) == n and sim.queue.empty()
    assert all(s is L for _, s in c.states())  # last sweep drove every net LOW


# --------------------------------------------------------------- purity / security

_FORBIDDEN_MODULES = {"logging", "os", "sys", "subprocess", "socket", "threading",
                      "asyncio", "random", "uuid", "time", "datetime", "pickle",
                      "marshal", "importlib", "PySide6", "pathlib", "io", "shutil"}


def test_q1_s01_digital_core_is_pure():
    files = sorted(DIGITAL_DIR.glob("*.py"))
    assert files
    violations = []
    for f in files:
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [node.module or ""]
            for mod in mods:
                segs = mod.split(".")
                if segs[0] in _FORBIDDEN_MODULES:
                    violations.append(f"{f.name}: imports {mod}")
                if mod.startswith("academic_core.") and not (
                        mod.startswith("academic_core.domain")
                        or mod == "academic_core.errors"):
                    violations.append(f"{f.name}: imports {mod}")
                if "lab" in segs or "mna" in segs:
                    violations.append(f"{f.name}: imports F8-N/analog {mod}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in (
                    "eval", "exec", "compile", "__import__", "open", "print", "id", "hash"):
                violations.append(f"{f.name}: calls {node.func.id}()")
    assert not violations, violations
