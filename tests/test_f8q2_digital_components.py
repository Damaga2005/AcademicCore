"""F8-Q.2 digital components + stimuli -- test suite.

Test IDs Q2-001..Q2-025 follow the F8-Q.2 phase brief. Gate checks are
exhaustive over the binary domain (2^n cases, no hypothesis). Every
circuit test runs through the Q1 ``DigitalSimulator``/``EventQueue``.
Purity of the new modules is covered by Q1-S01 (it globs digital/*.py).
"""

from __future__ import annotations

import dataclasses
import itertools
from decimal import Decimal

import pytest

from academic_core.domain.engineering.digital import (
    MAX_STIMULUS_EVENTS,
    MAX_TIME,
    TRUTH_TABLES,
    ConstantStimulus,
    DigitalCircuit,
    DigitalComponent,
    DigitalSimulator,
    GateKind,
    LogicState,
    PatternStimulus,
    Pin,
    PinDirection,
    PulseStimulus,
    ToggleStimulus,
)
from academic_core.domain.entities import DomainError
from academic_core.errors import AcademicCoreError, ValidationError, to_ui_error

D = Decimal
L, H = LogicState.LOW, LogicState.HIGH
BITS = (L, H)

REFERENCE = {  # independent oracle: Python boolean algebra on 0/1
    GateKind.NOT: lambda a: 1 - a,
    GateKind.AND: lambda a, b: a & b,
    GateKind.OR: lambda a, b: a | b,
    GateKind.XOR: lambda a, b: a ^ b,
}


def gate(cid, kind, inputs, output):
    return DigitalComponent(cid, kind, tuple(inputs), output)


def circuit(nets, init=L):
    c = DigitalCircuit()
    for n in nets:
        c.add_net(n, init)
    return c


def simulate_gate(kind, inputs):
    """Drive a single gate from constant stimuli through the full simulator."""
    names = [f"i{k}" for k in range(len(inputs))]
    c = circuit(names + ["y"])
    c.add_component(gate("g", kind, names, "y"))
    for n, s in zip(names, inputs):
        c.add_stimulus(ConstantStimulus(f"s_{n}", n, s))
    sim = DigitalSimulator(c)
    sim.run()
    return c.state("y")


# --------------------------------------------------------------- truth tables

def test_q2_001_not_low():
    assert gate("n", GateKind.NOT, ["a"], "y").evaluate((L,)) is H
    assert simulate_gate(GateKind.NOT, (L,)) is H


def test_q2_002_not_high():
    assert gate("n", GateKind.NOT, ["a"], "y").evaluate((H,)) is L
    assert simulate_gate(GateKind.NOT, (H,)) is L


@pytest.mark.parametrize("kind", [GateKind.AND, GateKind.OR, GateKind.XOR])
def test_q2_003_005_two_input_truth_tables(kind):
    g = gate("g", kind, ["a", "b"], "y")
    for a, b in itertools.product(BITS, repeat=2):
        expected = LogicState(REFERENCE[kind](a, b))
        assert g.evaluate((a, b)) is expected
        assert simulate_gate(kind, (a, b)) is expected


def test_q2_truth_tables_are_frozen_data():
    assert set(TRUTH_TABLES) == set(GateKind)
    for kind, table in TRUTH_TABLES.items():
        n = 1 if kind is GateKind.NOT else 2
        assert set(table) == set(itertools.product(BITS, repeat=n))  # exhaustive 2^n
        assert all(isinstance(v, LogicState) for v in table.values())
        with pytest.raises(TypeError):
            table[(L,) * n] = H
    with pytest.raises(TypeError):
        TRUTH_TABLES[GateKind.AND] = {}


def test_q2_gate_identities_exhaustive():
    t = TRUTH_TABLES
    for x in BITS:
        assert t[GateKind.NOT][(t[GateKind.NOT][(x,)],)] is x
        assert t[GateKind.AND][(x, L)] is L and t[GateKind.AND][(x, H)] is x
        assert t[GateKind.OR][(x, H)] is H and t[GateKind.OR][(x, L)] is x
        assert t[GateKind.XOR][(x, x)] is L and t[GateKind.XOR][(x, t[GateKind.NOT][(x,)])] is H
    for a, b in itertools.product(BITS, repeat=2):  # De Morgan
        n = lambda v: t[GateKind.NOT][(v,)]  # noqa: E731
        assert n(t[GateKind.AND][(a, b)]) is t[GateKind.OR][(n(a), n(b))]


# --------------------------------------------------------------- component contract

@pytest.mark.parametrize("kind, inputs", [
    (GateKind.NOT, ()), (GateKind.NOT, ("a", "b")),
    (GateKind.AND, ("a",)), (GateKind.OR, ("a", "b", "c")), (GateKind.XOR, ()),
])
def test_q2_006_invalid_arity(kind, inputs):
    with pytest.raises(ValidationError, match="INVALID_ARITY"):
        DigitalComponent("g", kind, inputs, "y")
    g = gate("g", GateKind.AND, ["a", "b"], "y")
    with pytest.raises(ValidationError, match="INVALID_ARITY"):
        g.evaluate((H,))
    with pytest.raises(ValidationError, match="INVALID_STATE"):
        g.evaluate((H, 1))


def test_q2_component_validation():
    with pytest.raises(ValidationError, match="INVALID_KIND"):
        DigitalComponent("g", "AND", ("a", "b"), "y")
    with pytest.raises(ValidationError, match="INVALID_INPUTS"):
        DigitalComponent("g", GateKind.AND, ["a", "b"], "y")
    with pytest.raises(ValidationError, match="INVALID_ID"):
        DigitalComponent("", GateKind.NOT, ("a",), "y")
    with pytest.raises(ValidationError, match="INVALID_ID"):
        DigitalComponent("g", GateKind.NOT, ("a b",), "y")
    g = gate("g", GateKind.NOT, ["a"], "y")
    with pytest.raises(dataclasses.FrozenInstanceError):
        g.kind = GateKind.AND


def test_q2_007_pins_and_unknown_pin():
    g = gate("g1", GateKind.AND, ["a", "b"], "y")
    assert g.pins == (Pin("in0", PinDirection.INPUT, "a"), Pin("in1", PinDirection.INPUT, "b"),
                      Pin("out", PinDirection.OUTPUT, "y"))
    assert g.pin("in1").net_id == "b" and g.pin("out").direction is PinDirection.OUTPUT
    for bad in ("in2", "OUT", ""):
        with pytest.raises(ValidationError, match="UNKNOWN_PIN"):
            g.pin(bad)
    with pytest.raises(ValidationError, match="INVALID_PIN_DIRECTION"):
        Pin("in0", "sideways", "a")
    # unknown nets are refused when wiring into a circuit
    c = circuit(["a", "y"])
    with pytest.raises(DomainError, match="UNKNOWN_NET"):
        c.add_component(g)
    with pytest.raises(DomainError, match="UNKNOWN_NET"):
        c.add_component(gate("g2", GateKind.NOT, ["a"], "ghost"))
    with pytest.raises(ValidationError, match="INVALID_COMPONENT"):
        c.add_component(object())
    assert c.components() == ()


def test_q2_008_duplicate_component():
    c = circuit(["a", "y", "z", "w"])
    c.add_component(gate("g", GateKind.NOT, ["a"], "y"))
    with pytest.raises(ValidationError, match="DUPLICATE_COMPONENT"):
        c.add_component(gate("g", GateKind.NOT, ["a"], "z"))
    with pytest.raises(ValidationError, match="DUPLICATE_COMPONENT"):  # shared driver namespace
        c.add_stimulus(ConstantStimulus("g", "w", H))
    assert [x.component_id for x in c.components()] == ["g"]


# --------------------------------------------------------------- propagation

def test_q2_009_component_composition_and_or():
    """A,B -> AND -> OUT1; OUT1,C -> OR -> OUT2, all 8 input combinations."""
    for a, b, cc in itertools.product(BITS, repeat=3):
        c = circuit(["A", "B", "C", "OUT1", "OUT2"])
        c.add_component(gate("g_and", GateKind.AND, ["A", "B"], "OUT1"))
        c.add_component(gate("g_or", GateKind.OR, ["OUT1", "C"], "OUT2"))
        for n, s in (("A", a), ("B", b), ("C", cc)):
            c.add_stimulus(ConstantStimulus(f"s{n}", n, s, D(1)))
        DigitalSimulator(c).run()
        assert c.state("OUT1") is LogicState(a & b)
        assert c.state("OUT2") is LogicState((a & b) | cc)


@pytest.mark.parametrize("a", BITS)
def test_q2_009b_not_not_chain(a):
    c = circuit(["A", "M", "OUT"])
    c.add_component(gate("n1", GateKind.NOT, ["A"], "M"))
    c.add_component(gate("n2", GateKind.NOT, ["M"], "OUT"))
    c.add_stimulus(ConstantStimulus("sA", "A", a, D(1)))
    DigitalSimulator(c).run()
    assert c.state("OUT") is a and c.state("M") is LogicState(1 - a)


def test_q2_010_output_transition_and_real_simulation():
    """stimulus -> net -> component -> event -> simulator -> output net."""
    c = circuit(["A", "Y"])
    c.add_component(gate("inv", GateKind.NOT, ["A"], "Y"))
    c.add_stimulus(PulseStimulus("pA", "A", D("1.5"), D("0.25")))
    sim = DigitalSimulator(c)
    events = sim.run()
    assert [(str(e.time), e.stable_id, e.net_id, e.state) for e in events] == [
        ("0", "inv", "Y", H),           # start-up settle: NOT(LOW) at t=0
        ("1.5", "pA", "A", H),
        ("1.5", "inv", "Y", L),         # zero-delay response, same timestamp
        ("1.75", "pA", "A", L),
        ("1.75", "inv", "Y", H),
    ]
    assert c.states() == (("A", L), ("Y", H))


def test_q2_011_no_redundant_output_transition():
    c = circuit(["A", "B", "Y"])
    c.add_component(gate("g", GateKind.OR, ["A", "B"], "Y"))
    c.add_stimulus(ConstantStimulus("sA", "A", H, D(1)))
    c.add_stimulus(ToggleStimulus("tB", "B", H, D(2), D(1), 4))  # B toggles while A=HIGH
    events = DigitalSimulator(c).run()
    y_events = [e for e in events if e.net_id == "Y"]
    assert [(str(e.time), e.state) for e in y_events] == [("1", H)]  # one real transition only


def test_q2_012_zero_delay_propagation():
    c = circuit(["A", "M", "OUT"])
    c.add_component(gate("n1", GateKind.NOT, ["A"], "M"))
    c.add_component(gate("n2", GateKind.NOT, ["M"], "OUT"))
    c.add_stimulus(ConstantStimulus("sA", "A", H, D(1)))
    events = DigitalSimulator(c).run()
    after = [e for e in events if e.time == D(1)]
    assert [e.net_id for e in after] == ["A", "M", "OUT"]
    assert all(str(e.time) == "1" for e in after)  # no artificial delta time
    assert c.state("OUT") is H


def test_q2_013_same_timestamp_ordering():
    """A rises and B falls at t=1 on an AND gate. Events resolve by
    (sequence, stable_id); the output compares against the projected state,
    so no stale HIGH survives even though Y=HIGH was queued first."""
    c = circuit(["A", "B", "Y"])
    c.add_component(gate("g", GateKind.AND, ["A", "B"], "Y"))
    c.add_stimulus(PatternStimulus("pA", "A", D(1), D(1), (H,)))
    c.add_stimulus(PatternStimulus("pB", "B", D(0), D(1), (H, L)))
    events = DigitalSimulator(c).run()
    at1 = [(e.sequence, e.stable_id, e.net_id, e.state) for e in events if e.time == D(1)]
    assert at1 == [(0, "pA", "A", H), (2, "pB", "B", L), (3, "g", "Y", H), (4, "g", "Y", L)]
    assert c.state("Y") is L


def test_q2_014_driver_conflict():
    c = circuit(["a", "b", "x"])
    c.add_component(gate("g1", GateKind.NOT, ["a"], "x"))
    with pytest.raises(ValidationError, match="DRIVER_CONFLICT") as info:
        c.add_component(gate("g2", GateKind.NOT, ["b"], "x"))
    assert "'g1'" in str(info.value) and "'g2'" in str(info.value)
    with pytest.raises(ValidationError, match="DRIVER_CONFLICT"):
        c.add_stimulus(ConstantStimulus("s", "x", H))
    c.add_stimulus(ConstantStimulus("sa", "a", H))
    with pytest.raises(ValidationError, match="DRIVER_CONFLICT"):
        c.add_stimulus(ToggleStimulus("sa2", "a", L, D(0), D(1), 2))
    assert c.driver("x") == "g1" and c.driver("a") == "sa" and c.driver("b") is None


def test_q2_015_combinational_loop():
    c = circuit(["A"])
    c.add_component(gate("ring", GateKind.NOT, ["A"], "A"))  # A -> NOT -> A
    sim = DigitalSimulator(c, max_delta_events=50)
    with pytest.raises(DomainError, match="INVALID_CYCLE") as info:
        sim.run()
    assert info.value.code == "AC-DOM-001"
    assert len(sim.processed) == 50 and sim.queue.size() == 1  # bounded, no growth


def test_q2_015b_loop_default_caps_and_event_limit():
    c = circuit(["A"])
    c.add_component(gate("ring", GateKind.NOT, ["A"], "A"))
    with pytest.raises(DomainError, match="INVALID_CYCLE"):
        DigitalSimulator(c).run()  # default MAX_DELTA_EVENTS: still bounded
    c2 = circuit(["A"])
    c2.add_component(gate("ring", GateKind.NOT, ["A"], "A"))
    with pytest.raises(DomainError, match="EVENT_LIMIT"):
        DigitalSimulator(c2, max_events=20).run()  # Q1 global cap also holds
    for bad in (0, True, 10**6):
        with pytest.raises(ValidationError, match="INVALID_LIMIT"):
            DigitalSimulator(c2, max_delta_events=bad)


def test_q2_015c_xor_loop():
    # A -> XOR(A, HIGH) -> A oscillates too; detection does not depend on gate kind.
    c = circuit(["A", "K"])
    c.add_stimulus(ConstantStimulus("k", "K", H))
    c.add_component(gate("x", GateKind.XOR, ["A", "K"], "A"))
    with pytest.raises(DomainError, match="INVALID_CYCLE"):
        DigitalSimulator(c, max_delta_events=100).run()


def test_q2_circuit_changed_after_start():
    c = circuit(["a", "y", "z"])
    c.add_component(gate("g", GateKind.NOT, ["a"], "y"))
    sim = DigitalSimulator(c)
    sim.run()
    c.add_component(gate("g2", GateKind.NOT, ["a"], "z"))
    with pytest.raises(DomainError, match="CIRCUIT_CHANGED"):
        sim.run()


def test_q2_fanout_sorted_by_component_id():
    c = circuit(["a", "y1", "y2", "y3"])
    for cid, out in (("z", "y1"), ("b", "y2"), ("m", "y3")):
        c.add_component(gate(cid, GateKind.NOT, ["a"], out))
    assert [g.component_id for g in c.fanout("a")] == ["b", "m", "z"]
    c.add_stimulus(ConstantStimulus("s", "a", H, D(1)))
    events = DigitalSimulator(c).run()
    assert [e.stable_id for e in events if e.time == D(1)] == ["s", "b", "m", "z"]


# --------------------------------------------------------------- stimuli

def test_q2_016_constant_low():
    s = ConstantStimulus("s", "a", L, D(2))
    assert s.edges() == ((D(2), L),)
    c = circuit(["a"], init=H)
    c.add_stimulus(s)
    DigitalSimulator(c).run()
    assert c.state("a") is L


def test_q2_017_constant_high():
    assert ConstantStimulus("s", "a", H).edges() == ((D(0), H),)
    c = circuit(["a"])
    c.add_stimulus(ConstantStimulus("s", "a", H))
    DigitalSimulator(c).run()
    assert c.state("a") is H


def test_q2_018_toggle():
    t = ToggleStimulus("clk", "a", L, D("0.5"), D("0.25"), 5)
    assert t.edges() == ((D("0.5"), L), (D("0.75"), H), (D("1.00"), L), (D("1.25"), H), (D("1.50"), L))
    c = circuit(["a"])
    c.add_stimulus(ToggleStimulus("clk", "a", H, D(0), D(1), 4))
    events = DigitalSimulator(c).run()
    assert [(e.time, e.state) for e in events] == [(D(0), H), (D(1), L), (D(2), H), (D(3), L)]


def test_q2_019_pulse():
    p = PulseStimulus("p", "a", D(1), D("0.001"))
    assert p.edges() == ((D(1), H), (D("1.001"), L))
    assert PulseStimulus("p", "a", D(0), D(1), level=L).edges() == ((D(0), L), (D(1), H))
    c = circuit(["a"])
    c.add_stimulus(p)
    sim = DigitalSimulator(c)
    assert [e.state for e in sim.run()] == [H, L] and c.state("a") is L


def test_q2_020_pattern():
    pattern = (L, H, H, L, H)
    p = PatternStimulus("pat", "a", D(0), D("0.1"), pattern)
    assert [s for _, s in p.edges()] == list(pattern)
    assert [t for t, _ in p.edges()] == [D("0"), D("0.1"), D("0.2"), D("0.3"), D("0.4")]
    c = circuit(["a"])
    c.add_stimulus(p)
    events = DigitalSimulator(c).run()
    assert len(events) == 5 and c.state("a") is H
    for bad in ("LHHLH", [L, H], (L, 1), (lambda: H,), ()):
        with pytest.raises(ValidationError, match="INVALID_PATTERN|INVALID_STATE|STIMULUS_LIMIT"):
            PatternStimulus("pat", "a", D(0), D(1), bad)


@pytest.mark.parametrize("make", [
    lambda t: ConstantStimulus("s", "a", H, t),
    lambda t: ToggleStimulus("s", "a", H, t, D(1), 1),
    lambda t: PulseStimulus("s", "a", t, D(1)),
    lambda t: PatternStimulus("s", "a", t, D(1), (H,)),
])
@pytest.mark.parametrize("bad", [D(-1), D("NaN"), D("Infinity"), 1.0, "0", MAX_TIME + 1])
def test_q2_021_invalid_stimulus_time(make, bad):
    with pytest.raises(ValidationError, match="TIME"):
        make(bad)


@pytest.mark.parametrize("bad", [D(0), D(-1), D("NaN"), 0.5, None])
def test_q2_022_invalid_period(bad):
    with pytest.raises(ValidationError, match="INVALID_PERIOD"):
        ToggleStimulus("t", "a", L, D(0), bad, 2)
    with pytest.raises(ValidationError, match="INVALID_PERIOD"):
        PatternStimulus("p", "a", D(0), bad, (L, H))


@pytest.mark.parametrize("bad", [D(0), D(-1), D("Infinity"), 0.001, None])
def test_q2_023_invalid_width(bad):
    with pytest.raises(ValidationError, match="INVALID_WIDTH"):
        PulseStimulus("p", "a", D(0), bad)


def test_q2_024_stimulus_bounds():
    for bad in (0, -1, MAX_STIMULUS_EVENTS + 1, True, 2.0):
        with pytest.raises(ValidationError, match="STIMULUS_LIMIT"):
            ToggleStimulus("t", "a", L, D(0), D("0.001"), bad)
    # last edge must stay within MAX_TIME
    with pytest.raises(ValidationError, match="TIME_LIMIT"):
        ToggleStimulus("t", "a", L, D(3000), D(1), 1000)
    with pytest.raises(ValidationError, match="TIME_LIMIT"):
        PulseStimulus("p", "a", MAX_TIME, D(1))
    # edge times are exact or refused (never silently rounded)
    with pytest.raises(ValidationError, match="INVALID_TIME"):
        ToggleStimulus("t", "a", L, D(1), D("1e-60"), 3)  # 1 + 2e-60 needs 61 digits
    # the largest allowed stimulus expands to exactly its bound
    big = ToggleStimulus("t", "a", L, D(0), D("0.001"), MAX_STIMULUS_EVENTS)
    assert len(big.edges()) == MAX_STIMULUS_EVENTS
    # stimuli still respect the simulator's EVENT_LIMIT
    c = circuit(["a"])
    c.add_stimulus(ToggleStimulus("t", "a", H, D(0), D(1), 10))
    with pytest.raises(DomainError, match="EVENT_LIMIT"):
        DigitalSimulator(c, max_events=5).run()
    with pytest.raises(ValidationError, match="INVALID_STIMULUS"):
        c.add_stimulus(lambda: H)


def _stimulus_run():
    c = circuit(["A", "B", "C", "X", "Y"])
    c.add_component(gate("g_xor", GateKind.XOR, ["A", "B"], "X"))
    c.add_component(gate("g_or", GateKind.OR, ["X", "C"], "Y"))
    c.add_stimulus(ToggleStimulus("clk", "A", H, D(0), D("0.5"), 8))
    c.add_stimulus(PatternStimulus("pat", "B", D("0.25"), D("0.5"), (H, H, L, H, L, L)))
    c.add_stimulus(PulseStimulus("pul", "C", D("1.5"), D("0.75")))
    sim = DigitalSimulator(c)
    events = sim.run()
    return [(e.time, e.sequence, e.stable_id, e.net_id, e.state) for e in events], c.states()


def test_q2_025_deterministic_stimulus():
    runs = [_stimulus_run() for _ in range(3)]
    assert runs[0] == runs[1] == runs[2]
    events, final = runs[0]
    keys = [e[:3] for e in events]
    assert keys == sorted(keys)  # canonical (t, seq, id) order
    assert final == (("A", L), ("B", L), ("C", L), ("X", L), ("Y", L))


# --------------------------------------------------------------- D2 compatibility

def test_q2_error_compatibility():
    c = circuit(["a", "y"])
    c.add_component(gate("g", GateKind.NOT, ["a"], "y"))
    failures = (lambda: DigitalComponent("g", GateKind.AND, ("a",), "y"),
                lambda: c.add_component(gate("g2", GateKind.NOT, ["a"], "y")),
                lambda: PulseStimulus("p", "a", D(0), D(0)),
                lambda: gate("g", GateKind.NOT, ["a"], "y").pin("zz"))
    for call in failures:
        with pytest.raises(AcademicCoreError) as info:
            call()
        exc = info.value
        assert isinstance(exc, ValueError) and exc.code == "AC-VAL-001"
        assert to_ui_error(exc).error_code == "AC-VAL-001"
