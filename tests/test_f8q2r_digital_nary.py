"""F8-Q.2R N-ary component architecture -- test suite.

Q2R-001..Q2R-020 follow the F8-Q.2R brief. Oracles are the mathematical
definitions (AND = all HIGH, OR = any HIGH, XOR = odd count of HIGH) on
plain 0/1 ints. They are exhaustive for N = 2, 3, 4 and use deterministic
generated vectors plus algebraic properties for N = 8..64 (no
hypothesis). Every circuit test runs through the Q1 simulator.
"""

from __future__ import annotations

import itertools
from decimal import Decimal

import pytest

from academic_core.domain.engineering.digital import (
    ARITY_RANGE,
    MAX_NETS,
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
)
from academic_core.domain.entities import DomainError
from academic_core.errors import ValidationError, to_ui_error

D = Decimal
L, H = LogicState.LOW, LogicState.HIGH
BITS = (L, H)
NARY = (GateKind.AND, GateKind.OR, GateKind.XOR)

ORACLE = {
    GateKind.AND: lambda bits: int(all(bits)),
    GateKind.OR: lambda bits: int(any(bits)),
    GateKind.XOR: lambda bits: sum(bits) % 2,
}


def names(n, prefix="i"):
    return tuple(f"{prefix}{k}" for k in range(n))


def gate(kind, n, cid="g", out="y", prefix="i"):
    return DigitalComponent(cid, kind, names(n, prefix), out)


def vectors(n, count=64):
    """Deterministic spread of N-bit vectors: all-low, all-high, one-hot,
    one-cold, then an LCG walk (no RNG module)."""
    out = [(L,) * n, (H,) * n]
    out += [tuple(H if k == j else L for k in range(n)) for j in range(n)]
    out += [tuple(L if k == j else H for k in range(n)) for j in range(n)]
    x = 12345
    for _ in range(count):
        x = (1103515245 * x + 12345) % 2**31
        out.append(tuple(LogicState((x >> (k % 31)) & 1) for k in range(n)))
    return out


def run_gate(kind, states):
    """Constant stimuli -> nets -> N-ary gate -> simulator -> output net."""
    n = len(states)
    c = DigitalCircuit()
    for nid in names(n) + ("y",):
        c.add_net(nid, L)
    c.add_component(gate(kind, n))
    for nid, s in zip(names(n), states):
        c.add_stimulus(ConstantStimulus(f"s_{nid}", nid, s, D(1)))
    DigitalSimulator(c).run()
    return c.state("y")


def check_exhaustive(kind, n, simulate=True):
    g = gate(kind, n)
    for combo in itertools.product(BITS, repeat=n):
        expected = LogicState(ORACLE[kind]([int(s) for s in combo]))
        assert g.evaluate(combo) is expected, (kind, combo)
        if simulate:
            assert run_gate(kind, combo) is expected, (kind, combo)


# --------------------------------------------------------------- truth semantics

def test_q2r_001_and_2_inputs():
    check_exhaustive(GateKind.AND, 2)


def test_q2r_002_and_3_inputs():
    check_exhaustive(GateKind.AND, 3)
    assert gate(GateKind.AND, 3).evaluate((H, H, H)) is H
    assert gate(GateKind.AND, 3).evaluate((H, H, L)) is L


def test_q2r_003_and_4_inputs():
    check_exhaustive(GateKind.AND, 4)


def test_q2r_004_and_8_inputs():
    g = gate(GateKind.AND, 8)
    for v in vectors(8):
        assert g.evaluate(v) is LogicState(ORACLE[GateKind.AND]([int(s) for s in v]))
    assert run_gate(GateKind.AND, (H,) * 8) is H
    assert run_gate(GateKind.AND, (H,) * 7 + (L,)) is L
    assert gate(GateKind.AND, 5).evaluate((H,) * 5) is H


def test_q2r_005_or_3_inputs():
    check_exhaustive(GateKind.OR, 3)
    assert gate(GateKind.OR, 3).evaluate((L, L, L)) is L


def test_q2r_006_or_4_inputs():
    check_exhaustive(GateKind.OR, 4)
    assert gate(GateKind.OR, 4).evaluate((L, L, H, L)) is H


def test_q2r_007_or_8_inputs():
    g = gate(GateKind.OR, 8)
    for v in vectors(8):
        assert g.evaluate(v) is LogicState(ORACLE[GateKind.OR]([int(s) for s in v]))
    assert run_gate(GateKind.OR, (L,) * 8) is L
    assert run_gate(GateKind.OR, (L,) * 7 + (H,)) is H


def test_q2r_008_xor_3_inputs():
    check_exhaustive(GateKind.XOR, 3)
    g = gate(GateKind.XOR, 3)
    assert g.evaluate((H, H, H)) is H and g.evaluate((H, H, L)) is L and g.evaluate((H, L, L)) is H


def test_q2r_009_xor_4_inputs():
    check_exhaustive(GateKind.XOR, 4)


def test_q2r_010_xor_8_inputs():
    g = gate(GateKind.XOR, 8)
    for v in vectors(8):
        assert g.evaluate(v) is LogicState(sum(int(s) for s in v) % 2)
    assert run_gate(GateKind.XOR, (H,) * 8) is L
    assert run_gate(GateKind.XOR, (H,) * 7 + (L,)) is H


@pytest.mark.parametrize("n", [16, 32, 64])
@pytest.mark.parametrize("kind", NARY)
def test_q2r_large_n_properties(kind, n):
    """Large N: generated vectors + algebraic properties; not built around 2 inputs."""
    g = gate(kind, n)
    for v in vectors(n, count=32):
        assert g.evaluate(v) is LogicState(ORACLE[kind]([int(s) for s in v]))
    for v in vectors(n, count=8):
        rev = tuple(reversed(v))
        assert g.evaluate(rev) is g.evaluate(v)  # commutative (order-insensitive)
    # absorbing / identity elements
    if kind is GateKind.AND:
        assert g.evaluate((L,) + (H,) * (n - 1)) is L and g.evaluate((H,) * n) is H
    if kind is GateKind.OR:
        assert g.evaluate((H,) + (L,) * (n - 1)) is H and g.evaluate((L,) * n) is L
    if kind is GateKind.XOR:  # flipping one input flips the output
        base = vectors(n, 1)[-1]
        flipped = (LogicState(1 - base[0]),) + base[1:]
        assert g.evaluate(flipped) is not g.evaluate(base)
    assert run_gate(kind, vectors(n, 1)[-1]) is g.evaluate(vectors(n, 1)[-1])


def test_q2r_nary_equals_cascaded_binary():
    """N-ary gate == left fold of the 2-input gate (associativity), N = 3..6."""
    for kind in NARY:
        for n in range(3, 7):
            g, two = gate(kind, n), gate(kind, 2)
            for combo in itertools.product(BITS, repeat=n):
                acc = combo[0]
                for s in combo[1:]:
                    acc = two.evaluate((acc, s))
                assert g.evaluate(combo) is acc


# --------------------------------------------------------------- arity / pins

def test_q2r_011_not_remains_unary():
    assert ARITY_RANGE[GateKind.NOT] == (1, 1)
    n = DigitalComponent("n", GateKind.NOT, ("a",), "y")
    assert n.arity == 1 and n.evaluate((L,)) is H and n.evaluate((H,)) is L
    assert [p.name for p in n.pins] == ["in0", "out"]


@pytest.mark.parametrize("kind", list(GateKind))
def test_q2r_012_zero_input_rejection(kind):
    with pytest.raises(ValidationError, match="INVALID_ARITY") as info:
        DigitalComponent("g", kind, (), "y")
    assert info.value.code == "AC-VAL-001"
    assert to_ui_error(info.value).error_code == "AC-VAL-001"


@pytest.mark.parametrize("inputs", [(), ("a", "b"), ("a", "b", "c")])
def test_q2r_013_invalid_not_arity(inputs):
    with pytest.raises(ValidationError, match="INVALID_ARITY"):
        DigitalComponent("n", GateKind.NOT, inputs, "y")


def test_q2r_minimum_and_maximum_arity():
    for kind in NARY:
        assert ARITY_RANGE[kind] == (2, MAX_NETS)
        with pytest.raises(ValidationError, match="INVALID_ARITY"):
            DigitalComponent("g", kind, ("a",), "y")
        with pytest.raises(ValidationError, match="INVALID_ARITY"):
            gate(kind, MAX_NETS + 1)
        assert gate(kind, MAX_NETS).arity == MAX_NETS  # bounded only by the core limit
    g = gate(GateKind.AND, 3)
    for bad in ((H, H), (H, H, H, H), [H, H, H], (H, H, 1)):
        with pytest.raises(ValidationError, match="INVALID_ARITY|INVALID_STATE"):
            g.evaluate(bad)


def test_q2r_014_deterministic_pin_generation():
    ins = ("n7", "n2", "n9", "n0", "n5")
    g = DigitalComponent("g", GateKind.OR, ins, "y")
    assert g.pins == tuple(Pin(f"in{k}", PinDirection.INPUT, net) for k, net in enumerate(ins)) + (
        Pin("out", PinDirection.OUTPUT, "y"),)
    assert g.pin("in4").net_id == "n5" and g.pin("in0").net_id == "n7"  # follows inputs, not sorting
    assert g.pins == DigitalComponent("g", GateKind.OR, ins, "y").pins
    with pytest.raises(ValidationError, match="UNKNOWN_PIN"):
        g.pin("in5")


def test_q2r_from_pins_connection_model():
    pins = (Pin("out", PinDirection.OUTPUT, "y"), Pin("in2", PinDirection.INPUT, "c"),
            Pin("in0", PinDirection.INPUT, "a"), Pin("in1", PinDirection.INPUT, "b"))
    g = DigitalComponent.from_pins("g", GateKind.AND, pins)
    assert g == DigitalComponent("g", GateKind.AND, ("a", "b", "c"), "y")
    cases = [
        ((Pin("in0", PinDirection.INPUT, "a"), Pin("in1", PinDirection.INPUT, "b")), "MISSING_PIN"),
        ((Pin("out", PinDirection.OUTPUT, "y"), Pin("in0", PinDirection.INPUT, "a"),
          Pin("in2", PinDirection.INPUT, "c")), "MISSING_PIN"),
        ((Pin("out", PinDirection.OUTPUT, "y"), Pin("in0", PinDirection.INPUT, "a"),
          Pin("clk", PinDirection.INPUT, "c")), "UNKNOWN_PIN"),
        ((Pin("out", PinDirection.OUTPUT, "y"), Pin("in00", PinDirection.INPUT, "a")), "UNKNOWN_PIN"),
        ((Pin("out", PinDirection.INPUT, "y"), Pin("in0", PinDirection.INPUT, "a")),
         "INVALID_PIN_DIRECTION"),
        ((Pin("out", PinDirection.OUTPUT, "y"), Pin("in0", PinDirection.OUTPUT, "a"),
          Pin("in1", PinDirection.INPUT, "b")), "INVALID_PIN_DIRECTION"),
        ((Pin("out", PinDirection.OUTPUT, "y"), Pin("in0", PinDirection.INPUT, "a"),
          Pin("in0", PinDirection.INPUT, "b")), "DUPLICATE_PIN"),
        ((Pin("out", PinDirection.OUTPUT, "y"), Pin("in0", PinDirection.INPUT, "a")), "INVALID_ARITY"),
        ([Pin("out", PinDirection.OUTPUT, "y")], "INVALID_INPUTS"),
        (("out", "in0"), "INVALID_INPUTS"),
    ]
    for bad, reason in cases:
        with pytest.raises(ValidationError, match=reason):
            DigitalComponent.from_pins("g", GateKind.AND, bad)
    # F8-Q.3R: two input pins on one net is legal (was DUPLICATE_INPUT in Q2R).
    shared = DigitalComponent.from_pins("g", GateKind.AND, (
        Pin("out", PinDirection.OUTPUT, "y"), Pin("in0", PinDirection.INPUT, "a"),
        Pin("in1", PinDirection.INPUT, "a")))
    assert shared.inputs == ("a", "a")


def test_q2r_duplicate_input_and_unknown_net():
    # F8-Q.3R: repeated input nets are legal (was DUPLICATE_INPUT in Q2R).
    assert DigitalComponent("g", GateKind.AND, ("a", "b", "a"), "y").pin_indices("a") == (0, 2)
    c = DigitalCircuit()
    for nid in ("a", "b", "c", "y"):
        c.add_net(nid, L)
    with pytest.raises(DomainError, match="UNKNOWN_NET"):
        c.add_component(DigitalComponent("g", GateKind.AND, ("a", "b", "c", "ghost"), "y"))
    assert c.components() == () and c.driver("y") is None  # nothing half-registered


# --------------------------------------------------------------- propagation

def test_q2r_015_nary_propagation():
    """A 5-input AND goes HIGH only when the last input rises."""
    c = DigitalCircuit()
    for nid in names(5) + ("y",):
        c.add_net(nid, L)
    c.add_component(gate(GateKind.AND, 5))
    for k, nid in enumerate(names(5)):
        c.add_stimulus(ConstantStimulus(f"s{k}", nid, H, D(k + 1)))
    events = DigitalSimulator(c).run()
    y = [(str(e.time), e.state) for e in events if e.net_id == "y"]
    assert y == [("5", H)] and c.state("y") is H


@pytest.mark.parametrize("kind", NARY)
def test_q2r_016_nary_same_timestamp_changes(kind):
    """A, B, C of a 3-input gate all change at t=1: deterministic, no artificial delay,
    final output equals the gate of the final inputs (projected-output logic)."""
    for start, end in itertools.product(itertools.product(BITS, repeat=3), repeat=2):
        c = DigitalCircuit()
        for nid in names(3) + ("y",):
            c.add_net(nid, L)
        c.add_component(gate(kind, 3))
        for nid, s0, s1 in zip(names(3), start, end):
            c.add_stimulus(PatternStimulus(f"p_{nid}", nid, D(0), D(1), (s0, s1)))
        events = DigitalSimulator(c).run()
        assert c.state("y") is LogicState(ORACLE[kind]([int(s) for s in end]))
        assert {str(e.time) for e in events} <= {"0", "1"}  # zero-delay: no new timestamps
        keys = [e.key for e in events]
        assert keys == sorted(keys)


def test_q2r_017_fanout():
    c = DigitalCircuit()
    for nid in ("A", "B", "C", "y_and", "y_or", "y_xor", "y_not"):
        c.add_net(nid, L)
    c.add_component(DigitalComponent("g_and", GateKind.AND, ("A", "B", "C"), "y_and"))
    c.add_component(DigitalComponent("g_or", GateKind.OR, ("A", "B", "C"), "y_or"))
    c.add_component(DigitalComponent("g_xor", GateKind.XOR, ("A", "B", "C"), "y_xor"))
    c.add_component(DigitalComponent("g_not", GateKind.NOT, ("A",), "y_not"))
    assert [g.component_id for g in c.fanout("A")] == ["g_and", "g_not", "g_or", "g_xor"]
    assert [g.component_id for g in c.fanout("B")] == ["g_and", "g_or", "g_xor"]
    c.add_stimulus(ConstantStimulus("sA", "A", H, D(1)))
    c.add_stimulus(ConstantStimulus("sB", "B", H, D(1)))
    events = DigitalSimulator(c).run()
    assert [e.stable_id for e in events if e.time == D(1)][:2] == ["sA", "sB"]
    assert dict(c.states()) == {"A": H, "B": H, "C": L, "y_and": L, "y_or": H,
                                "y_xor": L, "y_not": L}


def _composition(a, b, cc, dd, e, xor_bits):
    """AND4(A..D) -> X1; OR5(X1, B, C, D, E) -> X2; XOR8(X2, F..L) -> X3."""
    c = DigitalCircuit()
    inputs = {"A": a, "B": b, "C": cc, "D": dd, "E": e}
    xor_in = {f"F{k}": s for k, s in enumerate(xor_bits)}
    for nid in list(inputs) + list(xor_in) + ["X1", "X2", "X3"]:
        c.add_net(nid, L)
    c.add_component(DigitalComponent("and4", GateKind.AND, ("A", "B", "C", "D"), "X1"))
    c.add_component(DigitalComponent("or5", GateKind.OR, ("X1", "B", "C", "D", "E"), "X2"))
    c.add_component(DigitalComponent("xor8", GateKind.XOR, ("X2",) + tuple(xor_in), "X3"))
    for nid, s in {**inputs, **xor_in}.items():
        c.add_stimulus(ConstantStimulus(f"s_{nid}", nid, s, D("0.5")))
    sim = DigitalSimulator(c)
    sim.run()
    return c, sim


def test_q2r_018_composition():
    xor_bits = (H, L, H, H, L, L, H)  # 4 HIGH among F0..F6
    for a, b, cc, dd, e in itertools.product((0, 1), repeat=5):
        c, _ = _composition(*(LogicState(x) for x in (a, b, cc, dd, e)), xor_bits)
        x1 = a & b & cc & dd
        x2 = x1 | b | cc | dd | e
        x3 = (x2 + 4) % 2
        assert (c.state("X1"), c.state("X2"), c.state("X3")) == tuple(map(LogicState, (x1, x2, x3)))


def test_q2r_019_nary_deterministic_repeated_run():
    def once():
        c, sim = _composition(H, H, L, H, L, (H, H, H, L, L, L, H))
        c2 = DigitalCircuit()
        for nid in names(8) + ("y",):
            c2.add_net(nid, L)
        c2.add_component(gate(GateKind.XOR, 8))
        for k, nid in enumerate(names(8)):
            c2.add_stimulus(PulseStimulus(f"p{k}", nid, D(k) / 4, D("0.3")))
        s2 = DigitalSimulator(c2)
        s2.run()
        return ([(e.time, e.sequence, e.stable_id, e.net_id, e.state) for e in sim.processed + s2.processed],
                c.states(), c2.states())
    runs = [once() for _ in range(3)]
    assert runs[0] == runs[1] == runs[2]


def test_q2r_020_backward_compatibility_with_q2():
    two = DigitalComponent("g", GateKind.AND, ("a", "b"), "y")
    assert two.arity == 2 and [p.name for p in two.pins] == ["in0", "in1", "out"]
    from academic_core.domain.engineering.digital import TRUTH_TABLES
    for kind in NARY:
        g = DigitalComponent("g", kind, ("a", "b"), "y")
        for combo, out in TRUTH_TABLES[kind].items():
            assert g.evaluate(combo) is out
    assert TRUTH_TABLES[GateKind.NOT] == {(L,): H, (H,): L}
