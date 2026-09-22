# SPDX-License-Identifier: MIT
"""F8-Q.4 DigitalTrace replay: rebuild the observable trace through the engine.

``replay_trace(trace)`` re-runs exactly what ``digital-trace/1`` records
through the Q1 event engine. It does not re-simulate the original circuit,
because the schema carries no gates or stimuli.

1. One ``DigitalNet`` per distinct ``net_id``, whose initial state is the
   channel's ``initial``, plus one ``DigitalProbe`` per channel.
2. The simulator clock starts at the window ``start``.
3. Each net's samples are scheduled in stored order. Sequence numbers are
   assigned by ``DigitalSimulator.schedule``, so same-time transitions keep
   their order.
4. Each net gets ``noop_count`` no-op events (state = final state) at the
   window ``end``, scheduled after every transition, so the engine counts
   them as no-ops. No-op timing is not part of the schema (Q3R only counts
   them); only the count is observable, and it is reproduced exactly.
5. The queue is drained, the clock is brought to the window ``end`` (no
   event is pending by then), and ``sim.trace()`` is returned.

``verify_replay(trace)`` checks ``replay == trace`` and equal digests, and
raises ``IntegrationError REPLAY_MISMATCH`` (AC-INT-001) otherwise.
"""

from __future__ import annotations

from academic_core.domain.engineering.digital.core import (
    DigitalCircuit,
    DigitalSimulator,
    _invalid,
)
from academic_core.domain.engineering.digital.trace import DigitalProbe, DigitalTrace
from academic_core.errors import IntegrationError


def replay_trace(trace: DigitalTrace) -> DigitalTrace:
    """Replay ``trace`` through the event engine and return the new capture."""
    if not isinstance(trace, DigitalTrace):
        raise _invalid("INVALID_TRACE", f"expected DigitalTrace, got {type(trace).__name__}")
    by_net = {}
    for channel in trace.channels:  # same-net channels are identical (DigitalTrace invariant)
        by_net.setdefault(channel.net_id, channel)
    nets = sorted(by_net)
    circuit = DigitalCircuit()
    for net_id in nets:
        circuit.add_net(net_id, by_net[net_id].initial)
    for channel in trace.channels:
        circuit.add_probe(DigitalProbe(channel.probe_id, channel.net_id))
    sim = DigitalSimulator(circuit)
    sim.now = trace.start  # before the first step: becomes the trace window start
    for net_id in nets:
        for sample in by_net[net_id].samples:
            sim.schedule(sample.time, net_id, sample.state)
    for net_id in nets:
        channel = by_net[net_id]
        for _ in range(channel.noop_count):
            sim.schedule(trace.end, net_id, channel.final)
    sim.run()
    sim.now = trace.end  # queue drained; samples never exceed the window end
    return sim.trace()


def verify_replay(trace: DigitalTrace) -> DigitalTrace:
    """Replay and require ``replayed == trace`` with the same digest."""
    replayed = replay_trace(trace)
    if replayed != trace or replayed.digest() != trace.digest():
        raise IntegrationError("REPLAY_MISMATCH: replayed trace differs from the recorded one")
    return replayed
