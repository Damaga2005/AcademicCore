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
    """Registry of nets keyed by stable id. No components/stimuli yet (F8-Q.2)."""

    def __init__(self, max_nets: int = MAX_NETS):
        if isinstance(max_nets, bool) or not isinstance(max_nets, int) or not (
                1 <= max_nets <= MAX_NETS):
            raise _invalid("INVALID_LIMIT", f"max_nets must be 1..{MAX_NETS}")
        self.max_nets = max_nets
        self._nets: dict[str, DigitalNet] = {}

    def add_net(self, net_id: str, initial: LogicState, name: str | None = None) -> DigitalNet:
        """Register a net. ``initial`` is required (no magic default, DIG-I014)."""
        net = DigitalNet(net_id, net_id if name is None else name, initial)
        if net.net_id in self._nets:
            raise _invalid("DUPLICATE_NET", f"net {net.net_id!r} already registered")
        if len(self._nets) >= self.max_nets:
            raise _domain_error("NET_LIMIT", f"circuit holds {self.max_nets} nets")
        self._nets[net.net_id] = net
        return net

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
        return True


class DigitalSimulator:
    """Single-threaded scheduler: owns the sequence counter and the queue.

    Zero-delay: an event is applied at exactly its scheduled time. Time
    never moves backwards (scheduling before ``now`` is refused), and the
    total number of events per simulator is capped by ``max_events``, so
    ``run`` always terminates.
    """

    def __init__(self, circuit: DigitalCircuit, max_events: int = MAX_EVENTS):
        if not isinstance(circuit, DigitalCircuit):
            raise _invalid("INVALID_CIRCUIT", f"expected DigitalCircuit, got {type(circuit).__name__}")
        self.circuit = circuit
        self.queue = EventQueue(max_events)
        self.now = Decimal(0)
        self._next_sequence = 0
        self._processed: list[DigitalEvent] = []

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
        return event

    def step(self) -> DigitalEvent:
        event = self.queue.pop()
        self.now = event.time
        self.circuit.apply(event)
        self._processed.append(event)
        return event

    def run(self) -> tuple[DigitalEvent, ...]:
        """Drain the queue in canonical order; return this call's events."""
        start = len(self._processed)
        while not self.queue.empty():
            self.step()
        return tuple(self._processed[start:])

    @property
    def processed(self) -> tuple[DigitalEvent, ...]:
        return tuple(self._processed)
