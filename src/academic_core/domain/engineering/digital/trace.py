# SPDX-License-Identifier: MIT
"""F8-Q.3R digital probes + DigitalTrace (design §§21, 27).

A ``DigitalProbe`` binds one channel (identified by ``probe_id``) to one
net. It is observation-only: never a driver, never schedules events, never
mutates the circuit. Several probes may observe the same net. Probes are
registered on the ``DigitalCircuit`` before the simulation starts
(``add_probe``). Registering one later raises ``CIRCUIT_CHANGED``, so a
channel never silently misses the beginning of a run.

Capture (performed by ``DigitalSimulator.step``). For every processed event
on a probed net:
- If the state changes (a real transition), it is recorded as a
  ``TraceSample(time, sequence, state)``.
- If it doesn't change (a no-op), only ``noop_count`` is incremented. No-op
  events are counted, never stored, so a trace cannot grow with redundant
  activity.

Each channel also records the net's ``initial`` state at simulation start.

Same-timestamp policy: several real transitions of one net at the same
time (zero-delay glitches, e.g. ``t=1 HIGH`` then ``t=1 LOW``) are ALL kept,
in canonical processing order (ascending ``sequence``). They are never
collapsed; a future renderer or analyzer decides how to show them.

Digest policy: ``DigitalTrace.canonical()`` is a deterministic text built
only from the channel ids, net ids, the initial states, and each channel's
samples in order (``str(Decimal)`` time, state 0/1), plus the trace window.
``digest()`` is its SHA-256. Raw event ``sequence`` numbers, no-op counts,
memory addresses, Python ``hash()``, dict/set order and wall-clock time are
excluded. Order within a channel is carried by position. This is an
internal canonical form; the ``digital-trace/1`` wire schema belongs to Q4.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal

from academic_core.domain.engineering.digital.core import (
    LogicState,
    _invalid,
    check_id,
    check_sequence,
    check_state,
    check_time,
)

MAX_PROBES = 32  # = design MAX_CHANNELS
TRACE_CANONICAL_VERSION = "digital-trace-internal/0"


@dataclass(frozen=True)
class DigitalProbe:
    probe_id: str
    net_id: str

    def __post_init__(self):
        check_id(self.probe_id, "probe_id")
        check_id(self.net_id, "net_id")


@dataclass(frozen=True)
class TraceSample:
    """One real transition: ``state`` became effective at ``time``."""

    time: Decimal
    sequence: int
    state: LogicState

    def __post_init__(self):
        object.__setattr__(self, "time", check_time(self.time))
        check_sequence(self.sequence)
        check_state(self.state)


@dataclass(frozen=True)
class TraceChannel:
    probe_id: str
    net_id: str
    initial: LogicState
    samples: tuple[TraceSample, ...]
    noop_count: int = 0

    def __post_init__(self):
        check_id(self.probe_id, "probe_id")
        check_id(self.net_id, "net_id")
        check_state(self.initial)
        if not isinstance(self.samples, tuple) or not all(isinstance(s, TraceSample) for s in self.samples):
            raise _invalid("INVALID_TRACE", "samples must be a tuple of TraceSample")
        keys = [(s.time, s.sequence) for s in self.samples]
        if any(a >= b for a, b in zip(keys, keys[1:])):
            raise _invalid("INVALID_TRACE", f"channel {self.probe_id!r} samples not in canonical order")
        prev = self.initial
        for s in self.samples:
            if s.state is prev:
                raise _invalid("INVALID_TRACE", f"channel {self.probe_id!r} stores a non-transition")
            prev = s.state
        if isinstance(self.noop_count, bool) or not isinstance(self.noop_count, int) or self.noop_count < 0:
            raise _invalid("INVALID_TRACE", "noop_count must be an int >= 0")

    @property
    def final(self) -> LogicState:
        return self.samples[-1].state if self.samples else self.initial

    def state_at(self, time: Decimal) -> LogicState:
        """State after all transitions at or before ``time`` (zero-order hold)."""
        t = check_time(time)
        state = self.initial
        for s in self.samples:
            if s.time > t:
                break
            state = s.state
        return state


@dataclass(frozen=True)
class DigitalTrace:
    """Immutable capture. Channels are sorted by ``probe_id``."""

    start: Decimal
    end: Decimal
    channels: tuple[TraceChannel, ...]

    def __post_init__(self):
        object.__setattr__(self, "start", check_time(self.start))
        object.__setattr__(self, "end", check_time(self.end))
        if self.end < self.start:
            raise _invalid("INVALID_TRACE", f"end {self.end} before start {self.start}")
        if not isinstance(self.channels, tuple) or not all(isinstance(c, TraceChannel) for c in self.channels):
            raise _invalid("INVALID_TRACE", "channels must be a tuple of TraceChannel")
        ids = [c.probe_id for c in self.channels]
        if ids != sorted(ids) or len(set(ids)) != len(ids):
            raise _invalid("INVALID_TRACE", "channels must be unique and sorted by probe_id")
        if len(self.channels) > MAX_PROBES:
            raise _invalid("INVALID_TRACE", f"more than {MAX_PROBES} channels")
        for c in self.channels:
            if c.samples and not (self.start <= c.samples[0].time and c.samples[-1].time <= self.end):
                raise _invalid("INVALID_TRACE", f"channel {c.probe_id!r} has samples outside the window")

    def channel(self, probe_id: str) -> TraceChannel:
        for c in self.channels:
            if c.probe_id == probe_id:
                return c
        raise _invalid("UNKNOWN_PROBE", f"no channel {probe_id!r}")

    @property
    def transition_count(self) -> int:
        return sum(len(c.samples) for c in self.channels)

    def canonical(self) -> str:
        lines = [TRACE_CANONICAL_VERSION, f"window|{self.start}|{self.end}"]
        for c in self.channels:
            lines.append(f"channel|{c.probe_id}|{c.net_id}|{int(c.initial)}")
            lines.extend(f"sample|{s.time}|{int(s.state)}" for s in c.samples)
        return "\n".join(lines) + "\n"

    def digest(self) -> str:
        return hashlib.sha256(self.canonical().encode("utf-8")).hexdigest()
