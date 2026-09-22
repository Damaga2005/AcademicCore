# SPDX-License-Identifier: MIT
"""F8-Q.5 Logic Analyzer (design §§22-26): trigger + capture over DigitalTrace.

The analyzer is event-native. It never samples, never evaluates gates and
never keeps a second copy of the circuit. It works in two stages:

1. **Source.** ``capture(circuit, config)`` drives the existing
   ``DigitalSimulator`` with ``run_until(horizon)`` and takes its
   ``DigitalTrace``. ``analyze(trace, config)`` starts directly from an
   existing ``DigitalTrace``, e.g. one loaded from ``digital-trace/1``.
2. **Capture.** It selects channels, searches for the trigger, cuts the
   window and returns a frozen ``CaptureResult``. The capture itself is a
   ``DigitalTrace``, so Q4 serialization and replay apply unchanged.

Channels are selected by ``probe_id`` (the Q3R/Q4 channel identity). The
selection is stored sorted. A duplicated id is ``DUPLICATE_PROBE``, an
unknown one ``UNKNOWN_PROBE``, and at most ``MAX_PROBES`` may be selected.

Trigger (v1, single channel, design §23): ``RISING`` (LOW→HIGH),
``FALLING`` (HIGH→LOW) or ``BOTH``, on one of the selected channels.

- Only recorded transitions (trace samples) can fire. The initial state
  is not an edge.
- The arming window is ``[start, end]``, both ends inclusive.
- The first qualifying sample in trace order wins, so of two transitions
  at the same time the first one wins.
- No qualifying edge gives ``NOT_TRIGGERED``. That is a normal result,
  not an error: it has no captured trace and no trigger fields.

Capture window (all Decimal, exact, inclusive):

- Without a trigger: ``[start, end]``, status ``CAPTURED``.
- With a trigger at ``t``: ``[t - pre_trigger, t + post_trigger]``,
  status ``TRIGGERED``.
- Either window is intersected with the source trace window. Both the
  requested and the effective window are reported.
- Each captured channel's ``initial`` is its state just before the
  window start. Its samples are every transition inside the window,
  boundaries included, in order. Same-time transitions are never
  collapsed.
- ``trigger_index`` is the position of the trigger sample inside the
  captured trigger channel. It tells apart same-time transitions.
- No-op counts: ``digital-trace/1`` stores a count, not times, so the
  counts are kept only when the effective window covers the whole source
  window. Otherwise they are 0.

Bounds: channel count, times (``check_time``: ≤ ``MAX_TIME``), simulated
events (``max_events`` ≤ ``MAX_EVENTS``) and captured samples
(``MAX_CAPTURE_SAMPLES`` = Q4 ``MAX_TRACE_SAMPLES``, so every capture is
serializable). Errors use existing D2 codes: ``ValidationError``
AC-VAL-001, ``DomainError`` AC-DOM-001, ``IntegrationError`` AC-INT-001.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, Inexact, InvalidOperation, Overflow, localcontext
from enum import Enum

from academic_core.domain.engineering.digital.core import (
    MAX_EVENTS,
    MAX_TIME,
    DigitalCircuit,
    DigitalSimulator,
    LogicState,
    _domain_error,
    _invalid,
    check_id,
    check_time,
)
from academic_core.domain.engineering.digital.replay import verify_replay
from academic_core.domain.engineering.digital.serialization import MAX_TRACE_SAMPLES
from academic_core.domain.engineering.digital.trace import (
    MAX_PROBES,
    DigitalTrace,
    TraceChannel,
    TraceSample,
)
from academic_core.errors import IntegrationError

MAX_CAPTURE_CHANNELS = MAX_PROBES
MAX_CAPTURE_SAMPLES = MAX_TRACE_SAMPLES

_EXACT = Context(prec=400, traps=[Inexact, InvalidOperation, Overflow])  # window arithmetic never rounds


def _exact_add(a: Decimal, b: Decimal) -> Decimal:
    try:
        with localcontext(_EXACT):
            return a + b
    except ArithmeticError:
        raise _invalid("INVALID_TIME", f"{a} + {b} is not exactly representable") from None


def _exact_sub(a: Decimal, b: Decimal) -> Decimal:
    try:
        with localcontext(_EXACT):
            return a - b
    except ArithmeticError:
        raise _invalid("INVALID_TIME", f"{a} - {b} is not exactly representable") from None


class TriggerEdge(str, Enum):
    RISING = "RISING"
    FALLING = "FALLING"
    BOTH = "BOTH"


class CaptureStatus(str, Enum):
    CAPTURED = "CAPTURED"  # no trigger configured: plain window capture
    TRIGGERED = "TRIGGERED"
    NOT_TRIGGERED = "NOT_TRIGGERED"


def _duration(value: object, what: str) -> Decimal:
    try:
        return check_time(value)
    except ValueError as exc:
        raise _invalid("INVALID_CAPTURE", f"{what}: {exc}") from None


@dataclass(frozen=True)
class TriggerConfig:
    """Single-channel edge trigger; ``pre_trigger``/``post_trigger`` are required."""

    channel: str
    edge: TriggerEdge
    pre_trigger: Decimal
    post_trigger: Decimal

    def __post_init__(self):
        check_id(self.channel, "trigger channel")
        if not isinstance(self.edge, TriggerEdge):
            raise _invalid("INVALID_TRIGGER", f"edge must be a TriggerEdge, got {self.edge!r}")
        object.__setattr__(self, "pre_trigger", _duration(self.pre_trigger, "pre_trigger"))
        object.__setattr__(self, "post_trigger", _duration(self.post_trigger, "post_trigger"))

    def fires(self, previous: LogicState, state: LogicState) -> bool:
        if previous is state:  # never happens for trace samples; kept total
            return False
        if self.edge is TriggerEdge.BOTH:
            return True
        return (state is LogicState.HIGH) == (self.edge is TriggerEdge.RISING)


@dataclass(frozen=True)
class CaptureConfig:
    """Channels + arming/capture window ``[start, end]`` + optional trigger."""

    channels: tuple[str, ...]
    start: Decimal
    end: Decimal
    trigger: TriggerConfig | None = None

    def __post_init__(self):
        if isinstance(self.channels, (str, bytes)) or not isinstance(self.channels, (tuple, list)):
            raise _invalid("INVALID_CAPTURE", "channels must be a sequence of probe ids")
        channels = tuple(self.channels)  # never keep (or mutate) the caller's list
        if not channels:
            raise _invalid("INVALID_CAPTURE", "select at least one channel")
        if len(channels) > MAX_CAPTURE_CHANNELS:
            raise _invalid("CAPTURE_LIMIT", f"more than {MAX_CAPTURE_CHANNELS} channels")
        for c in channels:
            check_id(c, "channel")
        if len(set(channels)) != len(channels):
            raise _invalid("DUPLICATE_PROBE", "a channel is selected twice")
        object.__setattr__(self, "channels", tuple(sorted(channels)))
        object.__setattr__(self, "start", _duration(self.start, "start"))
        object.__setattr__(self, "end", _duration(self.end, "end"))
        if self.end < self.start:
            raise _invalid("INVALID_CAPTURE", f"end {self.end} before start {self.start}")
        if self.trigger is not None:
            if not isinstance(self.trigger, TriggerConfig):
                raise _invalid("INVALID_TRIGGER", f"expected TriggerConfig, got {type(self.trigger).__name__}")
            if self.trigger.channel not in self.channels:
                raise _invalid("INVALID_TRIGGER", f"trigger channel {self.trigger.channel!r} is not selected")

    @property
    def horizon(self) -> Decimal:
        """Last simulation time the capture can need."""
        post = self.trigger.post_trigger if self.trigger is not None else Decimal(0)
        return min(_exact_add(self.end, post), MAX_TIME)


@dataclass(frozen=True)
class CaptureResult:
    """Immutable capture. ``trace`` is None iff ``status`` is NOT_TRIGGERED."""

    config: CaptureConfig
    status: CaptureStatus
    source: DigitalTrace  # the selected channels over the whole source window
    trace: DigitalTrace | None  # the captured window (digital-trace/1 value)
    requested_window: tuple[Decimal, Decimal] | None
    trigger_time: Decimal | None = None
    trigger_edge: TriggerEdge | None = None  # the edge that fired (RISING/FALLING)
    trigger_index: int | None = None  # position in the captured trigger channel

    @property
    def triggered(self) -> bool:
        return self.status is CaptureStatus.TRIGGERED

    @property
    def trigger_channel(self) -> str | None:
        return self.config.trigger.channel if self.config.trigger is not None else None

    @property
    def window(self) -> tuple[Decimal, Decimal] | None:
        return None if self.trace is None else (self.trace.start, self.trace.end)


def _state_before(channel: TraceChannel, t: Decimal) -> LogicState:
    state = channel.initial
    for s in channel.samples:
        if s.time >= t:
            break
        state = s.state
    return state


def _slice(channel: TraceChannel, start: Decimal, end: Decimal, keep_noops: bool) -> TraceChannel:
    samples = tuple(TraceSample(s.time, s.sequence, s.state) for s in channel.samples
                    if start <= s.time <= end)
    return TraceChannel(channel.probe_id, channel.net_id, _state_before(channel, start), samples,
                        channel.noop_count if keep_noops else 0)


class LogicAnalyzer:
    """Stateless analyzer: every call is a pure function of its arguments."""

    def __init__(self, max_events: int = MAX_EVENTS):
        if isinstance(max_events, bool) or not isinstance(max_events, int) or not 1 <= max_events <= MAX_EVENTS:
            raise _invalid("INVALID_LIMIT", f"max_events must be 1..{MAX_EVENTS}")
        self.max_events = max_events

    def capture(self, circuit: DigitalCircuit, config: CaptureConfig) -> CaptureResult:
        """Simulate a fresh circuit up to ``config.horizon`` and analyze its trace.

        The simulator mutates net states, so a circuit can be captured
        only once. A circuit that already ran raises ``CIRCUIT_CHANGED``;
        build a new one for another capture.
        """
        if not isinstance(circuit, DigitalCircuit):
            raise _invalid("INVALID_CIRCUIT", f"expected DigitalCircuit, got {type(circuit).__name__}")
        if not isinstance(config, CaptureConfig):
            raise _invalid("INVALID_CAPTURE", f"expected CaptureConfig, got {type(config).__name__}")
        if circuit.state_revision != 0:
            raise _domain_error("CIRCUIT_CHANGED", "circuit was already simulated; capture a fresh circuit")
        probes = {p.probe_id for p in circuit.probes()}
        missing = [c for c in config.channels if c not in probes]
        if missing:
            raise _invalid("UNKNOWN_PROBE", f"no probe {missing[0]!r} in the circuit")
        sim = DigitalSimulator(circuit, max_events=self.max_events)
        horizon = config.horizon
        sim.run_until(horizon)
        observed = sim.trace()
        # every event <= horizon was processed, so the state holds until the horizon
        return self.analyze(DigitalTrace(observed.start, max(observed.end, horizon), observed.channels), config)

    def analyze(self, trace: DigitalTrace, config: CaptureConfig) -> CaptureResult:
        if not isinstance(trace, DigitalTrace):
            raise _invalid("INVALID_TRACE", f"expected DigitalTrace, got {type(trace).__name__}")
        if not isinstance(config, CaptureConfig):
            raise _invalid("INVALID_CAPTURE", f"expected CaptureConfig, got {type(config).__name__}")
        source = DigitalTrace(trace.start, trace.end, tuple(trace.channel(c) for c in config.channels))
        trigger = config.trigger
        if trigger is None:
            return self._cut(source, config, CaptureStatus.CAPTURED, (config.start, config.end))
        samples = source.channel(trigger.channel).samples
        previous = source.channel(trigger.channel).initial
        for k, s in enumerate(samples):
            if s.time > config.end:
                break
            if s.time >= config.start and trigger.fires(previous, s.state):
                requested = (max(_exact_sub(s.time, trigger.pre_trigger), Decimal(0)),
                             _exact_add(s.time, trigger.post_trigger))
                cut = self._cut(source, config, CaptureStatus.TRIGGERED, requested)
                # position of the trigger inside the captured channel (samples are
                # time-ordered, so the earlier ones inside the window are contiguous)
                index = sum(1 for x in samples[:k] if x.time >= cut.trace.start)
                edge = TriggerEdge.RISING if s.state is LogicState.HIGH else TriggerEdge.FALLING
                return CaptureResult(config, CaptureStatus.TRIGGERED, source, cut.trace, requested,
                                     s.time, edge, index)
            previous = s.state
        return CaptureResult(config, CaptureStatus.NOT_TRIGGERED, source, None, None)

    @staticmethod
    def _cut(source: DigitalTrace, config: CaptureConfig, status: CaptureStatus,
             requested: tuple[Decimal, Decimal]) -> CaptureResult:
        start, end = max(requested[0], source.start), min(requested[1], source.end)
        if end < start:
            raise _invalid("CAPTURE_WINDOW", f"window [{requested[0]}, {requested[1]}] is outside the "
                           f"trace window [{source.start}, {source.end}]")
        keep_noops = start == source.start and end == source.end
        channels = tuple(_slice(c, start, end, keep_noops) for c in source.channels)
        total = sum(len(c.samples) for c in channels)
        if total > MAX_CAPTURE_SAMPLES:
            raise _invalid("CAPTURE_LIMIT", f"{total} captured samples exceed {MAX_CAPTURE_SAMPLES}")
        return CaptureResult(config, status, source, DigitalTrace(start, end, channels), requested)


def verify_capture(result: CaptureResult) -> CaptureResult:
    """Q4 replay of the source + re-analysis must reproduce ``result`` exactly.

    Raises ``IntegrationError REPLAY_MISMATCH`` (AC-INT-001) otherwise. The
    captured trace itself is also Q4-replayed when present.
    """
    if not isinstance(result, CaptureResult):
        raise _invalid("INVALID_CAPTURE", f"expected CaptureResult, got {type(result).__name__}")
    replayed = LogicAnalyzer().analyze(verify_replay(result.source), result.config)
    if result.trace is not None:
        verify_replay(result.trace)
    if replayed != result:
        raise IntegrationError("REPLAY_MISMATCH: re-analysis of the replayed source differs")
    return replayed
