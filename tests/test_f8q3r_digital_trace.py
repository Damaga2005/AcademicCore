"""F8-Q.3R digital hardening + probes + DigitalTrace -- test suite.

Sections:
- A: NAND/NOR/XNOR, which are N-ary. Oracles are closed-form 0/1 definitions,
  exhaustive for N = 2..4 and property-based for N = 8..64.
- B: repeated input nets on one gate.
- C: incremental evaluation. The incremental path is compared against full
  evaluation both per gate and for whole simulations (event-for-event).
- Probes and DigitalTrace.
Deterministic generation only (LCG, no RNG module, no hypothesis).
"""

from __future__ import annotations

import itertools
from decimal import Decimal

import pytest

from academic_core.domain.engineering.digital import (
    ARITY_RANGE,
    GATE_SEMANTICS,
    MAX_NETS,
    MAX_PROBES,
    TRACE_CANONICAL_VERSION,
    TRUTH_TABLES,
    ConstantStimulus,
    DigitalCircuit,
    DigitalComponent,
    DigitalEvent,
    DigitalProbe,
    DigitalSimulator,
    DigitalTrace,
    GateEvaluator,
    GateKind,
    LogicState,
    PatternStimulus,
    PulseStimulus,
    ToggleStimulus,
    TraceChannel,
    TraceSample,
)
from academic_core.domain.engineering.digital import components as comp_mod
from academic_core.domain.entities import DomainError
from academic_core.errors import IntegrationError, ValidationError, to_ui_error

D = Decimal
L, H = LogicState.LOW, LogicState.HIGH
BITS = (L, H)
ALL_NARY = (GateKind.AND, GateKind.OR, GateKind.XOR, GateKind.NAND, GateKind.NOR, GateKind.XNOR)
INVERTED = {GateKind.NAND: GateKind.AND, GateKind.NOR: GateKind.OR, GateKind.XNOR: GateKind.XOR}

ORACLE = {
    GateKind.NOT: lambda b: 1 - b[0],
    GateKind.AND: lambda b: int(all(b)),
    GateKind.OR: lambda b: int(any(b)),
    GateKind.XOR: lambda b: sum(b) % 2,
    GateKind.NAND: lambda b: 1 - int(all(b)),
    GateKind.NOR: lambda b: int(not any(b)),
    GateKind.XNOR: lambda b: 1 - sum(b) % 2,
}


def expect(kind, states):
    return LogicState(ORACLE[kind]([int(s) for s in states]))


def names(n, prefix="i"):
    return tuple(f"{prefix}{k}" for k in range(n))


def gate(kind, n, cid="g", out="y"):
    return DigitalComponent(cid, kind, names(n), out)


def lcg(seed):
    x = seed
    while True:
        x = (1103515245 * x + 12345) % 2**31
        yield x


def vectors(n, count, seed=7):
    out = [(L,) * n, (H,) * n]
    out += [tuple(H if k == j else L for k in range(n)) for j in range(n)]
    g = lcg(seed)
    for _ in range(count):
        x = next(g)
        out.append(tuple(LogicState((x >> (k % 31)) & 1) for k in range(n)))
    return out


def run_constant(kind, inputs, states, init=L):
    """Distinct nets of ``inputs`` driven by constant stimuli at t=1."""
    nets = sorted(set(inputs))
    c = DigitalCircuit()
    for n in nets + ["y"]:
        c.add_net(n, init)
    c.add_component(DigitalComponent("g", kind, tuple(inputs), "y"))
    for n in nets:
        c.add_stimulus(ConstantStimulus(f"s_{n}", n, states[n], D(1)))
    sim = DigitalSimulator(c)
    sim.run()
    sim.check_consistency()
    return c.state("y")


# =============================================================== A. NAND/NOR/XNOR

@pytest.mark.parametrize("n", [2, 3, 4])
@pytest.mark.parametrize("kind", [GateKind.NAND, GateKind.NOR, GateKind.XNOR])
def test_q3r_a01_inverted_gates_exhaustive(kind, n):
    g = gate(kind, n)
    for combo in itertools.product(BITS, repeat=n):
        assert g.evaluate(combo) is expect(kind, combo), (kind, combo)
        assert g.evaluate(combo) is not gate(INVERTED[kind], n).evaluate(combo)  # = NOT(base)
        assert run_constant(kind, names(n), dict(zip(names(n), combo))) is expect(kind, combo)


def test_q3r_a02_semantics_examples():
    assert gate(GateKind.NAND, 3).evaluate((H, H, H)) is L
    assert gate(GateKind.NAND, 3).evaluate((H, L, H)) is H
    assert gate(GateKind.NOR, 4).evaluate((L, L, L, L)) is H
    assert gate(GateKind.NOR, 4).evaluate((L, L, H, L)) is L
    assert gate(GateKind.XNOR, 4).evaluate((H, H, L, L)) is H  # even number HIGH
    assert gate(GateKind.XNOR, 3).evaluate((H, L, L)) is L


@pytest.mark.parametrize("n", [8, 16, 32, 64])
@pytest.mark.parametrize("kind", ALL_NARY)
def test_q3r_a03_large_n_properties(kind, n):
    g = gate(kind, n)
    for v in vectors(n, 24):
        assert g.evaluate(v) is expect(kind, v)
        assert g.evaluate(tuple(reversed(v))) is g.evaluate(v)  # commutative
    if kind in INVERTED:
        base = gate(INVERTED[kind], n)
        assert all(g.evaluate(v) is not base.evaluate(v) for v in vectors(n, 8))
    v = vectors(n, 1, seed=n)[-1]
    assert run_constant(kind, names(n), dict(zip(names(n), v))) is g.evaluate(v)


def test_q3r_a04_arity_rules_for_all_kinds():
    assert ARITY_RANGE[GateKind.NOT] == (1, 1)
    for kind in ALL_NARY:
        assert ARITY_RANGE[kind] == (2, MAX_NETS)
        for bad in ((), ("a",)):
            with pytest.raises(ValidationError, match="INVALID_ARITY") as info:
                DigitalComponent("g", kind, bad, "y")
            assert to_ui_error(info.value).error_code == "AC-VAL-001"
        with pytest.raises(ValidationError, match="INVALID_ARITY"):
            gate(kind, MAX_NETS + 1)
        wide = gate(kind, MAX_NETS)
        assert wide.arity == MAX_NETS
        assert wide.evaluate((H,) * MAX_NETS) is expect(kind, (H,) * MAX_NETS)
    for bad in ((), ("a", "b")):
        with pytest.raises(ValidationError, match="INVALID_ARITY"):
            DigitalComponent("n", GateKind.NOT, bad, "y")


def test_q3r_a05_single_source_of_semantics():
    assert set(GATE_SEMANTICS) == set(GateKind) == set(TRUTH_TABLES)
    for kind, table in TRUTH_TABLES.items():  # derived view == oracle
        for combo, out in table.items():
            assert out is expect(kind, combo)
    with pytest.raises(TypeError):
        GATE_SEMANTICS[GateKind.AND] = ("ANY", False)
    # no 2^N materialisation: only NOT (2 rows) and 2-input (4 rows) tables exist
    assert all(len(t) in (2, 4) for t in TRUTH_TABLES.values())


# =============================================================== B. repeated input nets

@pytest.mark.parametrize("kind, inputs", [
    (GateKind.AND, ("A", "A")), (GateKind.OR, ("A", "A", "A")), (GateKind.XOR, ("A", "A")),
    (GateKind.XNOR, ("A", "A")), (GateKind.NAND, ("A", "A")), (GateKind.NOR, ("A", "A")),
    (GateKind.XOR, ("A", "A", "B")), (GateKind.XNOR, ("A", "B", "A", "B", "A")),
    (GateKind.AND, ("A", "B", "A", "C", "A")), (GateKind.NOR, ("B", "A", "B")),
])
def test_q3r_b01_repeated_input_nets(kind, inputs):
    nets = sorted(set(inputs))
    for combo in itertools.product(BITS, repeat=len(nets)):
        states = dict(zip(nets, combo))
        pin_states = tuple(states[n] for n in inputs)
        assert run_constant(kind, inputs, states) is expect(kind, pin_states)


def test_q3r_b02_named_identities():
    for a in BITS:
        na = LogicState(1 - a)
        assert run_constant(GateKind.NAND, ("A", "A"), {"A": a}) is na       # NAND(A,A) = NOT A
        assert run_constant(GateKind.NOR, ("A", "A"), {"A": a}) is na        # NOR(A,A) = NOT A
        assert run_constant(GateKind.XOR, ("A", "A"), {"A": a}) is L         # XOR(A,A) = 0
        assert run_constant(GateKind.XNOR, ("A", "A"), {"A": a}) is H        # XNOR(A,A) = 1
        for b in BITS:
            assert run_constant(GateKind.XOR, ("A", "A", "B"), {"A": a, "B": b}) is b


def test_q3r_b03_connection_fanout_and_drivers():
    g = DigitalComponent("g", GateKind.XOR, ("A", "B", "A"), "Y")
    assert g.pin_indices("A") == (0, 2) and g.pin_indices("B") == (1,) and g.pin_indices("Z") == ()
    assert [p.net_id for p in g.pins] == ["A", "B", "A", "Y"]
    c = DigitalCircuit()
    for n in ("A", "B", "Y"):
        c.add_net(n, L)
    c.add_component(g)
    assert [x.component_id for x in c.fanout("A")] == ["g"]  # listed once, not per pin
    # single-driver rule is untouched: two drivers on Y still conflict
    with pytest.raises(ValidationError, match="DRIVER_CONFLICT"):
        c.add_component(DigitalComponent("g2", GateKind.AND, ("A", "A"), "Y"))
    with pytest.raises(ValidationError, match="DUPLICATE_COMPONENT"):
        c.add_component(DigitalComponent("g", GateKind.AND, ("A", "A"), "B"))


def test_q3r_b04_repeated_net_propagation_counts_every_pin():
    """A feeds 3 of 4 pins of an 8-input AND; one A edge moves the HIGH count by 3."""
    inputs = ("A", "A", "B", "A", "C", "D", "E", "F")
    c = DigitalCircuit()
    for n in sorted(set(inputs)) + ["Y"]:
        c.add_net(n, H)
    c.add_component(DigitalComponent("g", GateKind.AND, inputs, "Y"))
    c.add_stimulus(PulseStimulus("pA", "A", D(1), D(1), level=L))
    sim = DigitalSimulator(c)
    events = sim.run()
    y = [(str(e.time), e.state) for e in events if e.net_id == "Y"]
    assert y == [("1", L), ("2", H)]
    sim.check_consistency()


# =============================================================== C. incremental evaluation

@pytest.mark.parametrize("kind", list(GateKind))
def test_q3r_c01_evaluator_matches_full_evaluation(kind):
    """Random walks of single-pin and whole-net updates vs full re-evaluation."""
    for n in ((1,) if kind is GateKind.NOT else (2, 3, 5, 8, 16, 64)):
        g = lcg(n * 31 + len(kind.value))
        nets = tuple(f"n{next(g) % max(1, n // 2)}" for _ in range(n))  # repeats on purpose
        comp = DigitalComponent("g", kind, nets, "y")
        net_state = {net: LogicState(next(g) & 1) for net in sorted(set(nets))}
        ev = comp.evaluator(tuple(net_state[x] for x in nets))
        for _ in range(200):
            net = sorted(net_state)[next(g) % len(net_state)]
            old = net_state[net]
            new = LogicState(1 - old)
            ev.update_net(net, old, new)
            net_state[net] = new
            current = tuple(net_state[x] for x in nets)
            assert ev.input_states == current
            assert ev.output_state() is comp.evaluate(current) is expect(kind, current)


def test_q3r_c02_evaluator_interface_and_transactional_updates():
    comp = gate(GateKind.NAND, 4)
    ev = GateEvaluator(comp, (H, H, H, L))
    assert ev.output_state() is H
    ev.update(3, L, H)
    assert ev.output_state() is L
    ev.initialize((L, L, L, L))
    assert ev.output_state() is H and ev.input_states == (L,) * 4
    before = ev.input_states
    with pytest.raises(IntegrationError, match="STALE_INPUT") as info:
        ev.update(0, H, L)  # pin 0 is LOW, the claim is wrong
    assert info.value.code == "AC-INT-001" and ev.input_states == before
    for bad in (-1, 4, True, "0"):
        with pytest.raises(ValidationError, match="UNKNOWN_PIN"):
            ev.update(bad, L, H)
    with pytest.raises(ValidationError, match="INVALID_STATE"):
        ev.update(0, L, 1)
    assert ev.input_states == before
    with pytest.raises(ValidationError, match="INVALID_ARITY"):
        ev.initialize((L, L))
    with pytest.raises(ValidationError, match="INVALID_COMPONENT"):
        GateEvaluator(object(), (L,))


def test_q3r_c03_hot_path_never_runs_full_evaluation(monkeypatch):
    """Once started, propagation must not call the O(N) reduction."""
    c = DigitalCircuit()
    n = 64
    for x in names(n) + ("y",):
        c.add_net(x, H)
    c.add_component(gate(GateKind.AND, n))
    c.add_stimulus(ToggleStimulus("t17", "i17", L, D(1), D(1), 50))
    sim = DigitalSimulator(c)
    sim.step()  # start-up: evaluators initialised

    def forbidden(*_a, **_k):
        raise AssertionError("full O(N) evaluation on the hot path")

    monkeypatch.setattr(comp_mod, "_reduce", forbidden)
    sim.run()
    monkeypatch.undo()
    y = [e.state for e in sim.processed if e.net_id == "y"]
    assert y == [L, H] * 25  # in17 toggles LOW/HIGH, AND follows
    sim.check_consistency()


def _mixed_circuit():
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
    for p, net in (("ch_P", "P"), ("ch_S", "S"), ("ch_T", "T"), ("ch_A", "A")):
        c.add_probe(DigitalProbe(p, net))
    return c


def _event_log(sim):
    return [(e.time, e.sequence, e.stable_id, e.net_id, e.state) for e in sim.processed]


def test_q3r_c04_simulation_incremental_equals_full(monkeypatch):
    """Event-for-event identical to a full-reevaluation reference (Q2 behaviour):
    the incremental mechanism introduces no new or missing glitches."""
    inc = DigitalSimulator(_mixed_circuit())
    inc.run()
    inc.check_consistency()
    monkeypatch.setattr(GateEvaluator, "output_state",
                        lambda self: self.component.evaluate(self.input_states))
    ref = DigitalSimulator(_mixed_circuit())
    ref.run()
    assert _event_log(inc) == _event_log(ref)
    assert inc.circuit.states() == ref.circuit.states()
    assert inc.trace().digest() == ref.trace().digest()


def test_q3r_c05_out_of_band_state_change_refused():
    c = DigitalCircuit()
    for x in ("a", "y"):
        c.add_net(x, L)
    c.add_component(DigitalComponent("g", GateKind.NOT, ("a",), "y"))
    c.add_stimulus(ToggleStimulus("t", "a", H, D(1), D(1), 3))
    sim = DigitalSimulator(c)
    sim.step()
    c.apply(DigitalEvent(D(1), 999, "hack", "a", H))  # bypasses the simulator
    with pytest.raises(DomainError, match="CIRCUIT_CHANGED"):
        sim.step()


# =============================================================== same timestamp

@pytest.mark.parametrize("kind", ALL_NARY)
@pytest.mark.parametrize("inputs", [
    ("A", "B"), ("A", "B", "C"), ("A", "A", "B"), ("A", "B", "C", "D", "E", "F", "G", "H"),
])
def test_q3r_s01_simultaneous_input_changes(kind, inputs):
    """Every net changes (or not) at t=1 together; final output == oracle of the
    final inputs; no timestamps invented; evaluators consistent."""
    nets = sorted(set(inputs))
    combos = list(itertools.product(BITS, repeat=len(nets)))
    if len(combos) > 16:
        combos = [combos[i] for i in range(0, len(combos), len(combos) // 16)]
    for start in combos:
        for end in combos:
            c = DigitalCircuit()
            for x in nets + ["y"]:
                c.add_net(x, L)
            c.add_component(DigitalComponent("g", kind, inputs, "y"))
            for x, s0, s1 in zip(nets, start, end):
                c.add_stimulus(PatternStimulus(f"p_{x}", x, D(0), D(1), (s0, s1)))
            c.add_probe(DigitalProbe("y", "y"))
            sim = DigitalSimulator(c)
            events = sim.run()
            final = dict(zip(nets, end))
            assert c.state("y") is expect(kind, tuple(final[x] for x in inputs))
            assert {str(e.time) for e in events} <= {"0", "1"}
            assert [e.key for e in events] == sorted(e.key for e in events)
            assert sim.trace().channel("y").final is c.state("y")
            sim.check_consistency()


def test_q3r_s02_cascade_same_timestamp():
    c = DigitalCircuit()
    for x in ("A", "B", "M1", "M2", "M3", "OUT"):
        c.add_net(x, L)
    c.add_component(DigitalComponent("s1", GateKind.NAND, ("A", "B"), "M1"))
    c.add_component(DigitalComponent("s2", GateKind.NOR, ("M1", "A"), "M2"))
    c.add_component(DigitalComponent("s3", GateKind.XNOR, ("M2", "M1", "B"), "M3"))
    c.add_component(DigitalComponent("s4", GateKind.AND, ("M3", "M3", "A"), "OUT"))
    c.add_stimulus(ConstantStimulus("sA", "A", H, D(1)))
    c.add_stimulus(ConstantStimulus("sB", "B", H, D(1)))
    sim = DigitalSimulator(c)
    events = sim.run()
    a = b = 1
    m1 = 1 - (a & b)
    m2 = 1 - (m1 | a)
    m3 = 1 - ((m2 + m1 + b) % 2)
    out = m3 & a
    assert dict(c.states())["OUT"] is LogicState(out) and dict(c.states())["M3"] is LogicState(m3)
    assert all(e.time in (D(0), D(1)) for e in events)
    sim.check_consistency()


def test_q3r_s03_loops_and_bounds():
    c = DigitalCircuit()
    c.add_net("A", L)
    c.add_component(DigitalComponent("ring", GateKind.NAND, ("A", "A"), "A"))  # NAND(A,A) -> A
    sim = DigitalSimulator(c, max_delta_events=40)
    with pytest.raises(DomainError, match="INVALID_CYCLE"):
        sim.run()
    c2 = DigitalCircuit()
    c2.add_net("A", L)
    c2.add_component(DigitalComponent("ring", GateKind.XNOR, ("A", "A", "A"), "A"))
    with pytest.raises(DomainError, match="EVENT_LIMIT"):
        DigitalSimulator(c2, max_events=25).run()


# =============================================================== probes

def _probe_circuit(*probes, extra_gate=False):
    c = DigitalCircuit()
    for x in ("A", "Y", "Z", "U"):
        c.add_net(x, L)
    c.add_component(DigitalComponent("inv", GateKind.NOT, ("A",), "Y"))
    if extra_gate:
        c.add_net("W", L)
        c.add_component(DigitalComponent("zz", GateKind.OR, ("A", "U"), "W"))
    c.add_stimulus(PulseStimulus("pA", "A", D("1.5"), D("0.25")))
    for p in probes:
        c.add_probe(p)
    return c


def test_q3r_p01_single_probe_transitions():
    sim = DigitalSimulator(_probe_circuit(DigitalProbe("ch_y", "Y")))
    sim.run()
    ch = sim.trace().channel("ch_y")
    assert ch.net_id == "Y" and ch.initial is L
    assert [(str(s.time), s.state) for s in ch.samples] == [("0", H), ("1.5", L), ("1.75", H)]
    assert ch.final is H and ch.noop_count == 0
    assert ch.state_at(D(1)) is H and ch.state_at(D("1.6")) is L and ch.state_at(D(2)) is H


def test_q3r_p02_multiple_probes_and_same_net():
    probes = (DigitalProbe("z_last", "Y"), DigitalProbe("a_in", "A"), DigitalProbe("m_y2", "Y"))
    sim = DigitalSimulator(_probe_circuit(*probes))
    sim.run()
    tr = sim.trace()
    assert [c.probe_id for c in tr.channels] == ["a_in", "m_y2", "z_last"]  # sorted, not add order
    assert tr.channel("m_y2").samples == tr.channel("z_last").samples
    assert [s.state for s in tr.channel("a_in").samples] == [H, L]
    assert tr.transition_count == 2 + 3 + 3


def test_q3r_p03_probe_is_never_a_driver():
    base = DigitalSimulator(_probe_circuit())
    base.run()
    probed_circuit = _probe_circuit(DigitalProbe("u", "U"), DigitalProbe("y", "Y"), DigitalProbe("a", "A"))
    probed = DigitalSimulator(probed_circuit)
    probed.run()
    assert _event_log(base) == _event_log(probed)  # observation changes nothing
    assert probed_circuit.driver("U") is None and probed_circuit.driver("Y") == "inv"
    ch_u = probed.trace().channel("u")
    assert ch_u.samples == () and ch_u.initial is L


def test_q3r_p04_lifecycle():
    c = _probe_circuit(DigitalProbe("y", "Y"))
    sim = DigitalSimulator(c)
    before = sim.trace()  # before start: initial states, no samples
    assert before.channel("y").samples == () and before.start == before.end == D(0)
    sim.step()
    mid = sim.trace()
    assert len(mid.channel("y").samples) == 1 and mid.end == D(0)
    sim.run()
    end = sim.trace()
    assert end.end == D("1.75") and len(end.channel("y").samples) == 3
    assert mid.channel("y").samples == end.channel("y").samples[:1]  # snapshots are immutable
    c.add_probe(DigitalProbe("late", "A"))
    with pytest.raises(DomainError, match="CIRCUIT_CHANGED"):
        sim.step()


def test_q3r_p05_noops_counted_not_stored():
    c = DigitalCircuit()
    c.add_net("A", H)
    c.add_stimulus(PatternStimulus("p", "A", D(0), D(1), (H, H, L, L, L, H)))
    c.add_probe(DigitalProbe("a", "A"))
    sim = DigitalSimulator(c)
    events = sim.run()
    ch = sim.trace().channel("a")
    assert len(events) == 6
    assert [(s.time, s.state) for s in ch.samples] == [(D(2), L), (D(5), H)]
    assert ch.noop_count == 4


def test_q3r_p06_probe_validation_and_limit():
    c = DigitalCircuit()
    c.add_net("A", L)
    with pytest.raises(DomainError, match="UNKNOWN_NET"):
        c.add_probe(DigitalProbe("p", "ghost"))
    with pytest.raises(ValidationError, match="INVALID_ID"):
        DigitalProbe("", "A")
    with pytest.raises(ValidationError, match="INVALID_PROBE"):
        c.add_probe(object())
    c.add_probe(DigitalProbe("p", "A"))
    with pytest.raises(ValidationError, match="DUPLICATE_PROBE"):
        c.add_probe(DigitalProbe("p", "A"))
    for k in range(1, MAX_PROBES):
        c.add_probe(DigitalProbe(f"p{k}", "A"))
    assert len(c.probes()) == MAX_PROBES == 32
    with pytest.raises(DomainError, match="PROBE_LIMIT") as info:
        c.add_probe(DigitalProbe("one_more", "A"))
    assert info.value.code == "AC-DOM-001"


# =============================================================== trace

def test_q3r_t01_empty_trace():
    c = DigitalCircuit()
    c.add_net("A", L)
    c.add_stimulus(ConstantStimulus("s", "A", H, D(1)))
    sim = DigitalSimulator(c)
    sim.run()
    tr = sim.trace()
    assert tr.channels == () and tr.transition_count == 0 and tr.end == D(1)
    assert tr.canonical() == f"{TRACE_CANONICAL_VERSION}\nwindow|0|1\n"


def test_q3r_t02_one_and_multiple_transitions():
    c = DigitalCircuit()
    c.add_net("A", L)
    c.add_stimulus(ConstantStimulus("s", "A", H, D("0.5")))
    c.add_probe(DigitalProbe("a", "A"))
    sim = DigitalSimulator(c)
    sim.run()
    assert [(str(s.time), s.state) for s in sim.trace().channel("a").samples] == [("0.5", H)]
    c2 = DigitalCircuit()
    c2.add_net("A", L)
    c2.add_stimulus(ToggleStimulus("t", "A", H, D(0), D("0.1"), 6))
    c2.add_probe(DigitalProbe("a", "A"))
    s2 = DigitalSimulator(c2)
    s2.run()
    assert [s.state for s in s2.trace().channel("a").samples] == [H, L, H, L, H, L]


def test_q3r_t03_same_timestamp_glitch_is_kept():
    """Q2-013 hazard: Y goes HIGH then LOW at t=1. Both samples are kept, in order."""
    c = DigitalCircuit()
    for x in ("A", "B", "Y"):
        c.add_net(x, L)
    c.add_component(DigitalComponent("g", GateKind.AND, ("A", "B"), "Y"))
    c.add_stimulus(PatternStimulus("pA", "A", D(1), D(1), (H,)))
    c.add_stimulus(PatternStimulus("pB", "B", D(0), D(1), (H, L)))
    c.add_probe(DigitalProbe("y", "Y"))
    sim = DigitalSimulator(c)
    sim.run()
    samples = sim.trace().channel("y").samples
    assert [(str(s.time), s.state) for s in samples] == [("1", H), ("1", L)]
    assert samples[0].sequence < samples[1].sequence
    assert sim.trace().channel("y").state_at(D(1)) is L  # hold = last at-or-before


def test_q3r_t04_deterministic_digest():
    def once():
        sim = DigitalSimulator(_mixed_circuit())
        sim.run()
        return sim.trace()
    traces = [once() for _ in range(3)]
    digests = {t.digest() for t in traces}
    assert len(digests) == 1 and len(next(iter(digests))) == 64
    assert traces[0] == traces[1] == traces[2]
    # probe registration order does not matter
    a = DigitalSimulator(_probe_circuit(DigitalProbe("y", "Y"), DigitalProbe("a", "A")))
    b = DigitalSimulator(_probe_circuit(DigitalProbe("a", "A"), DigitalProbe("y", "Y")))
    a.run()
    b.run()
    assert a.trace().digest() == b.trace().digest()


def test_q3r_t05_digest_depends_on_observables_only():
    base = DigitalSimulator(_probe_circuit(DigitalProbe("y", "Y")))
    base.run()
    # an unrelated gate shifts event sequence numbers but not what the probe sees
    other = DigitalSimulator(_probe_circuit(DigitalProbe("y", "Y"), extra_gate=True))
    other.run()
    seqs = lambda s: [x.sequence for x in s.trace().channel("y").samples]  # noqa: E731
    assert seqs(base) != seqs(other)
    assert base.trace().digest() == other.trace().digest()
    # but any observable change moves the digest
    renamed = DigitalSimulator(_probe_circuit(DigitalProbe("y2", "Y")))
    renamed.run()
    assert renamed.trace().digest() != base.trace().digest()
    moved = TraceChannel("y", "Y", L, (TraceSample(D(0), 0, H), TraceSample(D("1.5"), 1, L),
                                       TraceSample(D("1.8"), 2, H)))
    assert DigitalTrace(D(0), D("1.8"), (moved,)).digest() != base.trace().digest()
    tr = base.trace()
    assert "sample|1.5|0" in tr.canonical() and "channel|y|Y|0" in tr.canonical()


def test_q3r_t06_trace_value_validation():
    s1, s2 = TraceSample(D(1), 3, H), TraceSample(D(1), 4, L)
    TraceChannel("c", "n", L, (s1, s2))  # same-time glitch, ordered by sequence: fine
    for samples, reason in (((s2, s1), "canonical order"), ((TraceSample(D(1), 3, L),), "non-transition"),
                            ([s1], "tuple")):
        with pytest.raises(ValidationError, match="INVALID_TRACE") as info:
            TraceChannel("c", "n", L, samples)
        assert reason in str(info.value)
    with pytest.raises(ValidationError, match="INVALID_TRACE"):
        TraceChannel("c", "n", L, (), noop_count=-1)
    ch_b, ch_a = TraceChannel("b", "n", L, ()), TraceChannel("a", "n", L, ())
    with pytest.raises(ValidationError, match="INVALID_TRACE"):
        DigitalTrace(D(0), D(1), (ch_b, ch_a))
    with pytest.raises(ValidationError, match="INVALID_TRACE"):
        DigitalTrace(D(2), D(1), ())
    with pytest.raises(ValidationError, match="INVALID_TRACE"):
        DigitalTrace(D(0), D("0.5"), (TraceChannel("c", "n", L, (s1,)),))
    with pytest.raises(ValidationError, match="INVALID_TRACE"):
        DigitalTrace(D(0), D(1), tuple(TraceChannel(f"c{k:02d}", "n", L, ()) for k in range(MAX_PROBES + 1)))
    with pytest.raises(ValidationError, match="UNKNOWN_PROBE"):
        DigitalTrace(D(0), D(1), ()).channel("x")


def test_q3r_t07_trace_bounded_by_event_limit():
    c = DigitalCircuit()
    c.add_net("A", L)
    c.add_stimulus(ToggleStimulus("t", "A", H, D(0), D("0.001"), 5000))
    for k in range(MAX_PROBES):
        c.add_probe(DigitalProbe(f"p{k:02d}", "A"))  # 32 channels, one net
    sim = DigitalSimulator(c, max_events=5000)
    sim.run()
    tr = sim.trace()
    assert all(len(ch.samples) == 5000 for ch in tr.channels)
    assert len(sim._captured) == 1 and len(sim._captured["A"]) == 5000  # stored once per net
    c2 = DigitalCircuit()
    c2.add_net("A", L)
    c2.add_stimulus(ToggleStimulus("t", "A", H, D(0), D(1), 10))
    c2.add_probe(DigitalProbe("a", "A"))
    with pytest.raises(DomainError, match="EVENT_LIMIT"):
        DigitalSimulator(c2, max_events=5).run()
