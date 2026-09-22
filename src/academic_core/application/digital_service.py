# SPDX-License-Identifier: MIT
"""F8-Q.6 digital analysis application service (design §§6, 35; F15 §46 idioms).

The single integration boundary between the F15 UI and the F8-Q digital
engine:

    UI -> AcademicApp.digital (DigitalAnalysisService) -> LogicAnalyzer
       -> DigitalCircuit / DigitalSimulator -> DigitalTrace / CaptureResult
       -> frozen view models (this module) -> UI renderer

What it does:

- It translates plain UI values (strings) into the domain's typed
  configuration and fails with D2 errors.
- It builds a fresh demo circuit for every capture, so the same request
  always gives the same result.
- It calls ``LogicAnalyzer`` and maps ``CaptureResult`` into immutable
  view models made only of ``str`` / ``int`` / ``tuple``.
- It delegates serialization, loading and replay to Q4 (``digital-trace/1``
  text in/out; the UI owns the file dialogs).

What it never does: evaluate gates, detect edges, cut windows or mutate
traces (the domain does all of that), and it never imports Qt.

Logging covers milestones only (D2 §20): request, status, correlation id.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from decimal import Decimal

from academic_core.domain.engineering.digital import (
    MAX_TIME,
    MAX_TRACE_JSON_BYTES,
    CaptureConfig,
    CaptureResult,
    CaptureStatus,
    DigitalCircuit,
    DigitalComponent,
    DigitalProbe,
    DigitalTrace,
    GateKind,
    LogicAnalyzer,
    LogicState,
    PatternStimulus,
    ToggleStimulus,
    TriggerConfig,
    TriggerEdge,
    canonical_time,
    verify_capture,
    verify_replay,
)
from academic_core.errors import IntegrationError, ValidationError
from academic_core.logging_config import get_logger, log_event, new_correlation_id

logger = get_logger("academic_core.application.digital")

EDGES = tuple(e.value for e in TriggerEdge)  # ("RISING", "FALLING", "BOTH")
LOADED = "LOADED"  # view status of a trace opened from digital-trace/1 (no capture ran)
MAX_TIME_TEXT = 64
MAX_TRACE_FILE_BYTES = MAX_TRACE_JSON_BYTES  # the UI refuses bigger files before reading them
_TIME_TEXT = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")

_D = Decimal
_L, _H = LogicState.LOW, LogicState.HIGH


# ---------------------------------------------------------------- demo circuits
# Circuits are built only from certified Q1-Q3R constructors.

def _half_adder() -> DigitalCircuit:
    c = DigitalCircuit()
    for x in ("A", "B", "S", "C"):
        c.add_net(x, _L)
    c.add_component(DigitalComponent("xor_s", GateKind.XOR, ("A", "B"), "S"))
    c.add_component(DigitalComponent("and_c", GateKind.AND, ("A", "B"), "C"))
    c.add_stimulus(ToggleStimulus("clkA", "A", _H, _D("0.5"), _D("0.5"), 8))
    c.add_stimulus(ToggleStimulus("clkB", "B", _H, _D(1), _D(1), 4))
    for p, net in (("a", "A"), ("b", "B"), ("sum", "S"), ("carry", "C")):
        c.add_probe(DigitalProbe(p, net))
    return c


def _xor3_glitch() -> DigitalCircuit:
    c = DigitalCircuit()
    for x in ("A", "B", "C", "Y"):
        c.add_net(x, _L)
    c.add_component(DigitalComponent("x3", GateKind.XOR, ("A", "B", "C"), "Y"))
    for sid, net in (("sA", "A"), ("sB", "B"), ("sC", "C")):
        c.add_stimulus(PatternStimulus(sid, net, _D(1), _D(1), (_H, _L, _H)))
    for p, net in (("a", "A"), ("b", "B"), ("c", "C"), ("y", "Y")):
        c.add_probe(DigitalProbe(p, net))
    return c


def _wide_nand() -> DigitalCircuit:
    c = DigitalCircuit()
    names = tuple(f"i{k:02d}" for k in range(16))
    for k, x in enumerate(names):
        c.add_net(x, _L if k == 0 else _H)
    c.add_net("Y", _L)
    c.add_component(DigitalComponent("nand16", GateKind.NAND, names, "Y"))
    c.add_stimulus(ToggleStimulus("t0", "i00", _H, _D("0.25"), _D("0.25"), 8))
    c.add_probe(DigitalProbe("in0", "i00"))
    c.add_probe(DigitalProbe("y", "Y"))
    return c


def _repeated_inputs() -> DigitalCircuit:
    c = DigitalCircuit()
    for x in ("A", "B", "X", "N"):
        c.add_net(x, _L)
    c.add_component(DigitalComponent("xaab", GateKind.XOR, ("A", "A", "B"), "X"))  # = B
    c.add_component(DigitalComponent("nora", GateKind.NOR, ("A", "B", "A"), "N"))
    c.add_stimulus(ToggleStimulus("tA", "A", _H, _D("0.5"), _D("0.5"), 6))
    c.add_stimulus(PatternStimulus("pB", "B", _D("0.75"), _D(1), (_H, _L, _H)))
    for p, net in (("a", "A"), ("b", "B"), ("xor_aab", "X"), ("nor_aba", "N")):
        c.add_probe(DigitalProbe(p, net))
    return c


@dataclass(frozen=True)
class DemoInfo:
    key: str
    title: str
    description: str


_DEMOS = {
    "half_adder": (DemoInfo("half_adder", "Half adder (XOR / AND)",
                            "S = A XOR B, C = A AND B; A and B toggle at different rates."),
                   _half_adder),
    "xor3_glitch": (DemoInfo("xor3_glitch", "XOR3 zero-delay glitch",
                             "Three inputs switch together: Y shows same-timestamp transitions."),
                    _xor3_glitch),
    "wide_nand": (DemoInfo("wide_nand", "16-input NAND",
                           "One toggling input on an N-ary NAND; the other 15 held HIGH."),
                  _wide_nand),
    "repeated_inputs": (DemoInfo("repeated_inputs", "Repeated input nets",
                                 "XOR(A,A,B) = B and NOR(A,B,A) on shared nets."),
                        _repeated_inputs),
}


# ---------------------------------------------------------------- view models

@dataclass(frozen=True)
class ChannelInfo:
    channel_id: str
    net_id: str
    initial: str  # "LOW" / "HIGH" at the start of the run


@dataclass(frozen=True)
class AnalyzerRequest:
    """Plain UI values; the service validates and translates them."""

    demo: str
    channels: tuple[str, ...]
    start: str
    end: str
    trigger_channel: str = ""  # "" = no trigger (plain window capture)
    edge: str = ""
    pre_trigger: str = ""
    post_trigger: str = ""


@dataclass(frozen=True)
class TransitionView:
    """One real transition, exactly as recorded (never merged)."""

    channel_id: str
    net_id: str
    index: int  # position inside the channel
    time: str  # canonical exact Decimal text
    previous: str
    new: str
    same_time_rank: int  # 0-based order among this channel's transitions at ``time``
    same_time_count: int


@dataclass(frozen=True)
class WaveformChannelView:
    channel_id: str
    net_id: str
    initial: str
    final: str
    transitions: tuple[TransitionView, ...]


@dataclass(frozen=True)
class CaptureView:
    status: str  # CAPTURED / TRIGGERED / NOT_TRIGGERED / LOADED
    source: str  # demo key, or "digital-trace/1" for a loaded file
    channels: tuple[WaveformChannelView, ...]
    window: tuple[str, str] | None
    requested_window: tuple[str, str] | None = None
    trigger_channel: str | None = None
    trigger_edge: str | None = None  # configured edge
    fired_edge: str | None = None  # edge that actually fired
    trigger_time: str | None = None
    trigger_index: int | None = None
    pre_trigger: str | None = None
    post_trigger: str | None = None
    digest: str | None = None  # Q4 digest of the captured trace
    trace_json: str | None = None  # canonical digital-trace/1 text, for saving

    @property
    def transitions(self) -> tuple[TransitionView, ...]:
        """All transitions for inspection, by (time, channel, index); exact, unmerged."""
        rows = [t for ch in self.channels for t in ch.transitions]
        return tuple(sorted(rows, key=lambda t: (Decimal(t.time), t.channel_id, t.index)))


@dataclass(frozen=True)
class ReplayView:
    status: str  # "EQUIVALENT" or "RESULT_DIFFERS"
    digest: str


# ---------------------------------------------------------------- mapping

def _channel_view(channel) -> WaveformChannelView:
    """Linear: samples are time-ordered, so equal times form contiguous runs."""
    samples = channel.samples
    rows, previous, k = [], channel.initial, 0
    while k < len(samples):
        end = k
        while end < len(samples) and samples[end].time == samples[k].time:
            end += 1
        text = canonical_time(samples[k].time)
        for rank, s in enumerate(samples[k:end]):
            rows.append(TransitionView(channel.probe_id, channel.net_id, k + rank, text,
                                       previous.name, s.state.name, rank, end - k))
            previous = s.state
        k = end
    return WaveformChannelView(channel.probe_id, channel.net_id, channel.initial.name,
                               channel.final.name, tuple(rows))


def _trace_views(trace: DigitalTrace) -> tuple[WaveformChannelView, ...]:
    return tuple(_channel_view(c) for c in trace.channels)


def capture_view(result: CaptureResult, source: str) -> CaptureView:
    """Map a domain ``CaptureResult`` to its UI view (pure data mapping)."""
    trigger = result.config.trigger
    trace = result.trace
    window = None if trace is None else (canonical_time(trace.start), canonical_time(trace.end))
    requested = None
    if result.requested_window is not None:  # may extend past MAX_TIME before clipping
        requested = tuple(canonical_time(t) if t <= MAX_TIME else str(t) for t in result.requested_window)
    return CaptureView(
        status=result.status.value,
        source=source,
        channels=() if trace is None else _trace_views(trace),
        window=window,
        requested_window=requested,
        trigger_channel=result.trigger_channel,
        trigger_edge=None if trigger is None else trigger.edge.value,
        fired_edge=None if result.trigger_edge is None else result.trigger_edge.value,
        trigger_time=None if result.trigger_time is None else canonical_time(result.trigger_time),
        trigger_index=result.trigger_index,
        pre_trigger=None if trigger is None else canonical_time(trigger.pre_trigger),
        post_trigger=None if trigger is None else canonical_time(trigger.post_trigger),
        digest=None if trace is None else trace.digest(),
        trace_json=None if trace is None else trace.to_json(),
    )


def _time(text: object, what: str) -> Decimal:
    if not isinstance(text, str):
        raise ValidationError(f"INVALID_TIME: {what} must be text")
    raw = text.strip()
    if not raw or len(raw) > MAX_TIME_TEXT or not _TIME_TEXT.match(raw):
        raise ValidationError(f"INVALID_TIME: {what} must be a plain decimal number of seconds, "
                              f"e.g. 0 or 1.25")
    return Decimal(raw)  # exact; range checks happen in the domain


# ---------------------------------------------------------------- service

class DigitalAnalysisService:
    """Application coordinator over the certified F8-Q digital engine."""

    def __init__(self, analyzer: LogicAnalyzer | None = None):
        self.analyzer = analyzer or LogicAnalyzer()

    # -- discovery ------------------------------------------------------------
    def demos(self) -> tuple[DemoInfo, ...]:
        return tuple(_DEMOS[k][0] for k in sorted(_DEMOS))

    def _circuit(self, demo: object) -> DigitalCircuit:
        if not isinstance(demo, str) or demo not in _DEMOS:
            raise ValidationError(f"UNKNOWN_DEMO: {str(demo)[:64]!r} is not an available circuit")
        return _DEMOS[demo][1]()

    def channels(self, demo: str) -> tuple[ChannelInfo, ...]:
        """Available channels (probes) with their net and start-up state."""
        circuit = self._circuit(demo)
        return tuple(ChannelInfo(p.probe_id, p.net_id, circuit.state(p.net_id).name)
                     for p in circuit.probes())

    # -- configuration --------------------------------------------------------
    def build_config(self, request: AnalyzerRequest) -> CaptureConfig:
        if not isinstance(request, AnalyzerRequest):
            raise ValidationError("INVALID_CAPTURE: expected an AnalyzerRequest")
        if isinstance(request.channels, str) or not isinstance(request.channels, (tuple, list)):
            raise ValidationError("INVALID_CAPTURE: channels must be a list of channel ids")
        trigger = None
        if request.trigger_channel:
            if request.edge not in EDGES:
                raise ValidationError(f"INVALID_TRIGGER: edge must be one of {', '.join(EDGES)}")
            trigger = TriggerConfig(request.trigger_channel, TriggerEdge(request.edge),
                                    _time(request.pre_trigger, "pre-trigger"),
                                    _time(request.post_trigger, "post-trigger"))
        elif request.edge or request.pre_trigger or request.post_trigger:
            raise ValidationError("INVALID_TRIGGER: edge / pre / post need a trigger channel")
        return CaptureConfig(tuple(request.channels), _time(request.start, "start"),
                             _time(request.end, "end"), trigger)

    # -- capture --------------------------------------------------------------
    def capture(self, request: AnalyzerRequest) -> CaptureView:
        cid = new_correlation_id()
        config = self.build_config(request)
        circuit = self._circuit(request.demo)
        log_event(logger, logging.INFO, "AC-OK-001", "application.digital", "capture",
                  f"capture {request.demo} channels={len(config.channels)} [cid={cid}]")
        result = self.analyzer.capture(circuit, config)
        log_event(logger, logging.INFO, "AC-OK-001", "application.digital", "capture",
                  f"capture {result.status.value} [cid={cid}]")
        return capture_view(result, request.demo)

    def capture_result(self, request: AnalyzerRequest) -> CaptureResult:
        """Domain value, for verification (``verify``) and tests."""
        return self.analyzer.capture(self._circuit(request.demo), self.build_config(request))

    def verify(self, request: AnalyzerRequest) -> ReplayView:
        """Capture, then Q4-replay + re-analyze (``verify_capture``)."""
        result = self.capture_result(request)
        try:
            verify_capture(result)
        except IntegrationError:
            return ReplayView("RESULT_DIFFERS", "" if result.trace is None else result.trace.digest())
        return ReplayView("EQUIVALENT", result.source.digest())

    # -- digital-trace/1 (text in/out; the UI owns file dialogs) --------------
    def load_trace(self, text: object) -> CaptureView:
        """Render a saved trace without re-running any circuit."""
        trace = DigitalTrace.from_json(text)
        log_event(logger, logging.INFO, "AC-OK-001", "application.digital", "load_trace",
                  f"loaded {len(trace.channels)} channels")
        return CaptureView(status=LOADED, source="digital-trace/1", channels=_trace_views(trace),
                           window=(canonical_time(trace.start), canonical_time(trace.end)),
                           digest=trace.digest(), trace_json=trace.to_json())

    def replay_trace(self, text: object) -> ReplayView:
        """Q4 replay of a saved trace + equality/digest verification."""
        trace = DigitalTrace.from_json(text)
        try:
            verify_replay(trace)
        except IntegrationError:
            log_event(logger, logging.WARNING, "AC-INT-001", "application.digital", "replay_trace",
                      "replay differs")
            return ReplayView("RESULT_DIFFERS", trace.digest())
        return ReplayView("EQUIVALENT", trace.digest())


__all__ = [
    "EDGES",
    "LOADED",
    "MAX_TRACE_FILE_BYTES",
    "AnalyzerRequest",
    "CaptureStatus",
    "CaptureView",
    "ChannelInfo",
    "DemoInfo",
    "DigitalAnalysisService",
    "ReplayView",
    "TransitionView",
    "WaveformChannelView",
    "capture_view",
]
