# SPDX-License-Identifier: MIT
"""F8-Q.1 digital core: logic states, nets, events, bounded queue, circuit.

Design authority: ``docs/gates/GATE-DIGITAL-ENGINE-DESIGN.md`` (option C,
LOW/HIGH, event-driven, Decimal seconds, zero-delay, canonical order
``(time, sequence, stable_id)``, bounded, deterministic).

Pure domain: stdlib only, no Qt/IO/logging/threads/clock/RNG. Errors use
the D2 hierarchy (``ValidationError`` AC-VAL-001 for bad input,
``DomainError`` AC-DOM-001 for model violations); messages start with a
stable reason token (``UNKNOWN_NET: ...``), the F8-N ``LabConfigError``
idiom.

Sequence policy (single source): ``DigitalSimulator.schedule`` is the
ONLY place that assigns ``sequence`` -- a per-simulator counter starting
at 0, +1 per scheduled event. Events built by hand (tests, future
deserialization) must carry an explicit valid sequence.

Duplicate policy: two events with an identical canonical key
``(time, sequence, stable_id)`` in one queue are FORBIDDEN
(``DUPLICATE_EVENT``); ties are never resolved by insertion order.
Decimal equality applies, so ``1.0`` and ``1.00`` are the same time.
"""

from __future__ import annotations

import heapq
import re
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import IntEnum

from academic_core.domain.entities import DomainError
from academic_core.errors import ValidationError

DIGITAL_CORE_VERSION = "digital-core/1"

MAX_NETS = 1024
MAX_EVENTS = 1_000_000
MAX_TIME = Decimal(3600)  # seconds of simulation time (design MAX_TRACE_DURATION)
# Per-timestamp event cap: zero-delay loop detection (design §17, F8-Q.2).
MAX_DELTA_EVENTS = 100_000

ID_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,63}\Z")
MAX_NAME_LEN = 128


def _domain_error(reason: str, message: str) -> DomainError:
    return DomainError(f"{reason}: {message}", code="AC-DOM-001")


def _invalid(reason: str, message: str) -> ValidationError:
    return ValidationError(f"{reason}: {message}")


class LogicState(IntEnum):
    """Two-valued v1 logic level. Serializes as 0/1; X/Z deferred."""

    LOW = 0
    HIGH = 1


def check_state(value: object) -> LogicState:
    if not isinstance(value, LogicState):
        raise _invalid("INVALID_STATE", f"expected LogicState, got {value!r}")
    return value


def check_id(value: object, what: str = "id") -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise _invalid("INVALID_ID", f"{what} {value!r} must match {ID_RE.pattern}")
    return value


def check_time(value: object) -> Decimal:
    """Canonical time: finite, non-negative Decimal seconds <= MAX_TIME.

    ``int`` is accepted and converted exactly; ``float``/``bool``/``str``
    are rejected (no binary-float time, no implicit parsing).
    """
    if isinstance(value, bool) or not isinstance(value, (Decimal, int)):
        raise _invalid("INVALID_TIME", f"time must be Decimal seconds, got {value!r}")
    t = Decimal(value)
    if not t.is_finite():
        raise _invalid("INVALID_TIME", f"time must be finite, got {t}")
    if t < 0:
        raise _invalid("NEGATIVE_TIME", f"time must be >= 0, got {t}")
    if t > MAX_TIME:
        raise _invalid("TIME_LIMIT", f"time {t} exceeds {MAX_TIME} s")
    return t


def check_sequence(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _invalid("INVALID_SEQUENCE", f"sequence must be an int >= 0, got {value!r}")
    return value


@dataclass(frozen=True)
class DigitalNet:
    """Immutable net value. State changes produce a new net (``with_state``);
    only ``DigitalCircuit.apply`` swaps it in, so mutation is funnelled
    through events."""

    net_id: str
    name: str
    state: LogicState

    def __post_init__(self):
        check_id(self.net_id, "net_id")
        if not isinstance(self.name, str) or not self.name.strip() or len(self.name) > MAX_NAME_LEN:
            raise _invalid("INVALID_NAME", f"net name must be 1..{MAX_NAME_LEN} chars")
        check_state(self.state)

    def with_state(self, state: LogicState) -> "DigitalNet":
        return replace(self, state=check_state(state))


@dataclass(frozen=True, order=True)
class DigitalEvent:
    """Immutable scheduled transition. Field order IS the sort order:
    canonical key ``(time, sequence, stable_id)`` first; ``net_id`` and
    ``state`` only break ties the queue already forbids, keeping the
    comparison total."""

    time: Decimal
    sequence: int
    stable_id: str
    net_id: str
    state: LogicState

    def __post_init__(self):
        object.__setattr__(self, "time", check_time(self.time))
        check_sequence(self.sequence)
        check_id(self.stable_id, "stable_id")
        check_id(self.net_id, "net_id")
        check_state(self.state)

    @property
    def key(self) -> tuple[Decimal, int, str]:
        return (self.time, self.sequence, self.stable_id)


class EventQueue:
    """Bounded min-priority queue over the canonical event key."""

    def __init__(self, max_events: int = MAX_EVENTS):
        if isinstance(max_events, bool) or not isinstance(max_events, int) or not (
                1 <= max_events <= MAX_EVENTS):
            raise _invalid("INVALID_LIMIT", f"max_events must be 1..{MAX_EVENTS}")
        self.max_events = max_events
        self._heap: list[DigitalEvent] = []
        self._keys: set[tuple[Decimal, int, str]] = set()  # membership only, never iterated

    def push(self, event: DigitalEvent) -> None:
        if not isinstance(event, DigitalEvent):
            raise _invalid("INVALID_EVENT", f"expected DigitalEvent, got {type(event).__name__}")
        if event.key in self._keys:
            raise _invalid("DUPLICATE_EVENT", f"canonical key {event.key} already queued")
        if len(self._heap) >= self.max_events:
            raise _domain_error("EVENT_LIMIT", f"queue holds {self.max_events} events")
        heapq.heappush(self._heap, event)
        self._keys.add(event.key)

    def peek(self) -> DigitalEvent:
        if not self._heap:
            raise _domain_error("EMPTY_QUEUE", "no pending events")
        return self._heap[0]

    def pop(self) -> DigitalEvent:
        if not self._heap:
            raise _domain_error("EMPTY_QUEUE", "no pending events")
        event = heapq.heappop(self._heap)
        self._keys.discard(event.key)
        return event

    def empty(self) -> bool:
        return not self._heap

    def size(self) -> int:
        return len(self._heap)

    __len__ = size


class DigitalCircuit:
    """Nets + components + stimuli, keyed by stable ids (F8-Q.2 adds the last two).

    Single-driver rule (design §46): each net has at most one driver,
    a component output or a stimulus. Component and stimulus ids share one
    namespace. Since every driver owns one net, drivers <= nets <= MAX_NETS.
    """

    def __init__(self, max_nets: int = MAX_NETS):
        if isinstance(max_nets, bool) or not isinstance(max_nets, int) or not (
                1 <= max_nets <= MAX_NETS):
            raise _invalid("INVALID_LIMIT", f"max_nets must be 1..{MAX_NETS}")
        self.max_nets = max_nets
        self._nets: dict[str, DigitalNet] = {}
        self._components: dict[str, object] = {}
        self._stimuli: dict[str, object] = {}
        self._drivers: dict[str, str] = {}  # net_id -> driver id
        self._fanout: dict[str, tuple[str, ...]] = {}  # net_id -> sorted component ids
        self._probes: dict[str, object] = {}  # observers only, never drivers (Q.3R)
        self.revision = 0  # bumped by add_component/add_stimulus/add_probe
        self.state_revision = 0  # bumped by every state-changing apply

    def add_net(self, net_id: str, initial: LogicState, name: str | None = None) -> DigitalNet:
        """Register a net. ``initial`` is required (no magic default, DIG-I014)."""
        net = DigitalNet(net_id, net_id if name is None else name, initial)
        if net.net_id in self._nets:
            raise _invalid("DUPLICATE_NET", f"net {net.net_id!r} already registered")
        if len(self._nets) >= self.max_nets:
            raise _domain_error("NET_LIMIT", f"circuit holds {self.max_nets} nets")
        self._nets[net.net_id] = net
        return net

    def _claim_driver(self, driver_id: str, net_id: str) -> None:
        if driver_id in self._components or driver_id in self._stimuli:
            raise _invalid("DUPLICATE_COMPONENT", f"driver id {driver_id!r} already registered")
        self.net(net_id)
        if net_id in self._drivers:
            raise _invalid("DRIVER_CONFLICT",
                           f"net {net_id!r} driven by {self._drivers[net_id]!r} and {driver_id!r}")
        self._drivers[net_id] = driver_id

    def add_component(self, component):
        """Register a gate; all its nets must exist and its output be undriven."""
        # Local import: components.py imports this module's validators.
        from academic_core.domain.engineering.digital.components import DigitalComponent

        if not isinstance(component, DigitalComponent):
            raise _invalid("INVALID_COMPONENT", f"expected DigitalComponent, got {type(component).__name__}")
        for net_id in component.inputs:
            self.net(net_id)
        self._claim_driver(component.component_id, component.output)
        self._components[component.component_id] = component
        for net_id in component.inputs:
            readers = self._fanout.get(net_id, ())
            if component.component_id not in readers:  # a net may feed several pins (Q.3R)
                self._fanout[net_id] = tuple(sorted(readers + (component.component_id,)))
        self.revision += 1
        return component

    def add_probe(self, probe):
        """Register an observer channel. Never claims a driver, never mutates nets."""
        from academic_core.domain.engineering.digital.trace import MAX_PROBES, DigitalProbe

        if not isinstance(probe, DigitalProbe):
            raise _invalid("INVALID_PROBE", f"expected DigitalProbe, got {type(probe).__name__}")
        if probe.probe_id in self._probes:
            raise _invalid("DUPLICATE_PROBE", f"probe {probe.probe_id!r} already registered")
        self.net(probe.net_id)
        if len(self._probes) >= MAX_PROBES:
            raise _domain_error("PROBE_LIMIT", f"circuit holds {MAX_PROBES} probes")
        self._probes[probe.probe_id] = probe
        self.revision += 1
        return probe

    def probes(self) -> tuple:
        return tuple(self._probes[k] for k in sorted(self._probes))

    def add_stimulus(self, stimulus):
        """Register a stimulus as the sole driver of its net."""
        from academic_core.domain.engineering.digital.stimuli import STIMULUS_TYPES

        if not isinstance(stimulus, STIMULUS_TYPES):
            raise _invalid("INVALID_STIMULUS", f"expected a stimulus, got {type(stimulus).__name__}")
        self._claim_driver(stimulus.stimulus_id, stimulus.net_id)
        self._stimuli[stimulus.stimulus_id] = stimulus
        self.revision += 1
        return stimulus

    def components(self) -> tuple:
        return tuple(self._components[k] for k in sorted(self._components))

    def stimuli(self) -> tuple:
        return tuple(self._stimuli[k] for k in sorted(self._stimuli))

    def fanout(self, net_id: str) -> tuple:
        """Components reading ``net_id``, sorted by component id."""
        return tuple(self._components[k] for k in self._fanout.get(net_id, ()))

    def driver(self, net_id: str) -> str | None:
        self.net(net_id)
        return self._drivers.get(net_id)

    def net(self, net_id: str) -> DigitalNet:
        try:
            return self._nets[net_id]
        except (KeyError, TypeError):
            raise _domain_error("UNKNOWN_NET", f"net {net_id!r} is not registered") from None

    def state(self, net_id: str) -> LogicState:
        return self.net(net_id).state

    def nets(self) -> tuple[DigitalNet, ...]:
        """All nets sorted by id (never dict order)."""
        return tuple(self._nets[k] for k in sorted(self._nets))

    def states(self) -> tuple[tuple[str, LogicState], ...]:
        return tuple((n.net_id, n.state) for n in self.nets())

    def apply(self, event: DigitalEvent) -> bool:
        """Apply ``event`` to its net; return True iff the state changed."""
        if not isinstance(event, DigitalEvent):
            raise _invalid("INVALID_EVENT", f"expected DigitalEvent, got {type(event).__name__}")
        net = self.net(event.net_id)
        if net.state == event.state:
            return False
        self._nets[net.net_id] = net.with_state(event.state)
        self.state_revision += 1
        return True


class DigitalSimulator:
    """Single-threaded scheduler: owns the sequence counter and the queue.

    Zero-delay: an event is applied at exactly its scheduled time. Time
    never moves backwards (scheduling before ``now`` is refused), and the
    total number of events per simulator is capped by ``max_events``, so
    ``run`` always terminates.

    F8-Q.2 propagation happens in the same queue; there is no second mechanism.
    - Start-up happens on the first ``step``. Components are evaluated in id
      order (settling their outputs to the initial net states), then every
      stimulus edge is scheduled in stimulus-id order.
    - When an applied event changes a net, the fanout components are
      re-evaluated in id order. An output event is scheduled at the SAME
      time (zero-delay) only if it differs from the output's projected
      state, which is the last state scheduled for that net, falling back
      to the current state.
    - More than ``max_delta_events`` events at one timestamp is a
      zero-delay loop, reported as ``DomainError INVALID_CYCLE``
      (design §17). ``EVENT_LIMIT`` still caps the whole run.
    - Components/stimuli/probes must be registered before the first
      ``step``. A later registration raises ``CIRCUIT_CHANGED``.

    F8-Q.3R additions:
    - Gates are evaluated incrementally through per-run ``GateEvaluator``s,
      which cost O(pins on the changed net) instead of O(N). Outputs come
      from the same semantic function as ``DigitalComponent.evaluate``, and
      ``check_consistency()`` compares the two paths (dev/test oracle, never
      called on the hot path).
    - Changing net state behind the simulator's back (``circuit.apply``
      after start) would desynchronise the evaluators, so it raises
      ``CIRCUIT_CHANGED``.
    - Probed nets are captured into a ``DigitalTrace`` (``trace()``); see
      ``trace.py`` for the capture, no-op and same-timestamp policies.
    """

    def __init__(self, circuit: DigitalCircuit, max_events: int = MAX_EVENTS,
                 max_delta_events: int = MAX_DELTA_EVENTS):
        if not isinstance(circuit, DigitalCircuit):
            raise _invalid("INVALID_CIRCUIT", f"expected DigitalCircuit, got {type(circuit).__name__}")
        if isinstance(max_delta_events, bool) or not isinstance(max_delta_events, int) or not (
                1 <= max_delta_events <= MAX_DELTA_EVENTS):
            raise _invalid("INVALID_LIMIT", f"max_delta_events must be 1..{MAX_DELTA_EVENTS}")
        self.circuit = circuit
        self.queue = EventQueue(max_events)
        self.max_delta_events = max_delta_events
        self.now = Decimal(0)
        self._next_sequence = 0
        self._processed: list[DigitalEvent] = []
        self._projected: dict[str, LogicState] = {}  # net_id -> last scheduled state
        self._revision: int | None = None  # circuit revision seen at start-up
        self._state_revision = 0  # circuit.state_revision after our last apply
        self._delta: tuple[Decimal | None, int] = (None, 0)
        self._evaluators: dict[str, object] = {}  # component_id -> GateEvaluator
        self._start_time = Decimal(0)
        self._initial: dict[str, LogicState] = {}  # probed net -> state at start
        self._captured: dict[str, list[tuple[Decimal, int, LogicState]]] = {}  # probed net -> transitions
        self._noops: dict[str, int] = {}  # probed net -> no-op event count

    def schedule(self, time: Decimal, net_id: str, state: LogicState,
                 stable_id: str | None = None) -> DigitalEvent:
        """Create and enqueue an event; ``stable_id`` defaults to ``net_id``."""
        self.circuit.net(net_id)  # unknown net fails at schedule time
        if self._next_sequence >= self.queue.max_events:
            raise _domain_error("EVENT_LIMIT", f"simulator scheduled {self.queue.max_events} events")
        event = DigitalEvent(time, self._next_sequence,
                             net_id if stable_id is None else stable_id, net_id, state)
        if event.time < self.now:
            raise _domain_error("CAUSALITY", f"time {event.time} is before now={self.now}")
        self.queue.push(event)
        self._next_sequence += 1
        self._projected[net_id] = event.state
        return event

    def _project(self, component, out: LogicState) -> None:
        if out != self._projected.get(component.output, self.circuit.state(component.output)):
            self.schedule(self.now, component.output, out, component.component_id)

    def _start(self) -> None:
        if self._revision is None:
            self._revision = self.circuit.revision
            self._state_revision = self.circuit.state_revision
            self._start_time = self.now
            for probe in self.circuit.probes():
                self._initial[probe.net_id] = self.circuit.state(probe.net_id)
                self._captured[probe.net_id] = []
                self._noops[probe.net_id] = 0
            for component in self.circuit.components():
                ev = component.evaluator(tuple(self.circuit.state(n) for n in component.inputs))
                self._evaluators[component.component_id] = ev
                self._project(component, ev.output_state())
            for stimulus in self.circuit.stimuli():
                for t, state in stimulus.edges():
                    self.schedule(t, stimulus.net_id, state, stimulus.stimulus_id)
        elif self._revision != self.circuit.revision:
            raise _domain_error("CIRCUIT_CHANGED", "components/stimuli/probes added after simulation start")
        elif self._state_revision != self.circuit.state_revision:
            raise _domain_error("CIRCUIT_CHANGED", "net state changed outside the simulator")

    def step(self) -> DigitalEvent:
        self._start()
        nxt = self.queue.peek()
        last_time, count = self._delta
        count = count + 1 if nxt.time == last_time else 1
        if count > self.max_delta_events:
            raise _domain_error("INVALID_CYCLE", f"more than {self.max_delta_events} events at "
                                f"t={nxt.time} (zero-delay loop via net {nxt.net_id!r})")
        self._delta = (nxt.time, count)
        event = self.queue.pop()
        self.now = event.time
        old = self.circuit.state(event.net_id)
        changed = self.circuit.apply(event)
        self._state_revision = self.circuit.state_revision
        if changed:
            for component in self.circuit.fanout(event.net_id):
                ev = self._evaluators[component.component_id]
                ev.update_net(event.net_id, old, event.state)
                self._project(component, ev.output_state())
        if event.net_id in self._captured:
            if changed:
                self._captured[event.net_id].append((event.time, event.sequence, event.state))
            else:
                self._noops[event.net_id] += 1
        self._processed.append(event)
        return event

    def run(self) -> tuple[DigitalEvent, ...]:
        """Drain the queue in canonical order; return this call's events."""
        self._start()
        start = len(self._processed)
        while not self.queue.empty():
            self.step()
        return tuple(self._processed[start:])

    @property
    def processed(self) -> tuple[DigitalEvent, ...]:
        return tuple(self._processed)

    def trace(self):
        """Immutable ``DigitalTrace`` of all probes, window ``[start, now]``.

        Before the first step it is built from the circuit's current states
        (no samples). Transitions stored <= processed events <= max_events,
        once per net, however many probes observe it.
        """
        from academic_core.domain.engineering.digital.trace import (
            DigitalTrace,
            TraceChannel,
            TraceSample,
        )

        channels = []
        for probe in self.circuit.probes():
            net_id = probe.net_id
            channels.append(TraceChannel(
                probe.probe_id, net_id,
                self._initial.get(net_id, self.circuit.state(net_id)),
                tuple(TraceSample(t, seq, s) for t, seq, s in self._captured.get(net_id, ())),
                self._noops.get(net_id, 0)))
        return DigitalTrace(self._start_time, self.now, tuple(channels))

    def check_consistency(self) -> None:
        """Dev/test oracle: incremental gate state must equal full evaluation
        of the current net states. Raises ``IntegrationError`` on divergence."""
        from academic_core.errors import IntegrationError

        for cid in sorted(self._evaluators):
            ev = self._evaluators[cid]
            current = tuple(self.circuit.state(n) for n in ev.component.inputs)
            if ev.input_states != current or ev.output_state() is not ev.component.evaluate(current):
                raise IntegrationError(f"INCONSISTENT_EVALUATOR: {cid}")
