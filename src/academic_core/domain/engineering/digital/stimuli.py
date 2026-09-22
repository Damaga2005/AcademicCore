# SPDX-License-Identifier: MIT
"""F8-Q.2 digital stimuli: constant / toggle / pulse / pattern.

Stimuli are frozen data that expand to a finite, strictly increasing
tuple of ``(time, state)`` edges. The simulator schedules those edges
through the Q1 queue; stimuli never evaluate components (design §28).

Time follows the Q1 rules (``check_time``). Edge times are computed under
an exact Decimal context that traps ``Inexact``, so an edge time is never
silently rounded. Every stimulus is capped at ``MAX_STIMULUS_EVENTS``
edges and has no unbounded repeat.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, Inexact, InvalidOperation, Overflow, localcontext

from academic_core.domain.engineering.digital.core import (
    LogicState,
    _invalid,
    check_id,
    check_state,
    check_time,
)

MAX_STIMULUS_EVENTS = 100_000

_EXACT = Context(prec=60, traps=[Inexact, InvalidOperation, Overflow])

Edges = tuple[tuple[Decimal, LogicState], ...]


def _positive(value: object, reason: str) -> Decimal:
    try:
        d = check_time(value)
    except ValueError as exc:
        raise _invalid(reason, str(exc)) from None
    if d <= 0:
        raise _invalid(reason, f"must be > 0, got {d}")
    return d


def _count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not (
            1 <= value <= MAX_STIMULUS_EVENTS):
        raise _invalid("STIMULUS_LIMIT", f"edge count must be 1..{MAX_STIMULUS_EVENTS}, got {value!r}")
    return value


def _edge_time(start: Decimal, step: Decimal, index: int) -> Decimal:
    try:
        with localcontext(_EXACT):
            t = start + step * index
    except ArithmeticError:
        raise _invalid("INVALID_TIME", f"edge {index} time is not exactly representable") from None
    return check_time(t)


def _ids(stimulus_id: str, net_id: str) -> None:
    check_id(stimulus_id, "stimulus_id")
    check_id(net_id, "net_id")


@dataclass(frozen=True)
class ConstantStimulus:
    """Drive ``state`` once at ``time`` (default 0)."""

    stimulus_id: str
    net_id: str
    state: LogicState
    time: Decimal = Decimal(0)

    def __post_init__(self):
        _ids(self.stimulus_id, self.net_id)
        check_state(self.state)
        object.__setattr__(self, "time", check_time(self.time))

    def edges(self) -> Edges:
        return ((self.time, self.state),)


@dataclass(frozen=True)
class ToggleStimulus:
    """``count`` edges ``first, ¬first, first, ...`` at ``start + i*period``."""

    stimulus_id: str
    net_id: str
    first: LogicState
    start: Decimal
    period: Decimal
    count: int

    def __post_init__(self):
        _ids(self.stimulus_id, self.net_id)
        check_state(self.first)
        object.__setattr__(self, "start", check_time(self.start))
        object.__setattr__(self, "period", _positive(self.period, "INVALID_PERIOD"))
        _count(self.count)
        _edge_time(self.start, self.period, self.count - 1)  # last edge within MAX_TIME

    def edges(self) -> Edges:
        other = LogicState(1 - self.first)
        return tuple((_edge_time(self.start, self.period, i), self.first if i % 2 == 0 else other)
                     for i in range(self.count))


@dataclass(frozen=True)
class PulseStimulus:
    """Single pulse: ``level`` at ``start``, back to ``¬level`` at ``start + width``."""

    stimulus_id: str
    net_id: str
    start: Decimal
    width: Decimal
    level: LogicState = LogicState.HIGH

    def __post_init__(self):
        _ids(self.stimulus_id, self.net_id)
        check_state(self.level)
        object.__setattr__(self, "start", check_time(self.start))
        object.__setattr__(self, "width", _positive(self.width, "INVALID_WIDTH"))
        _edge_time(self.start, self.width, 1)

    def edges(self) -> Edges:
        return ((self.start, self.level),
                (_edge_time(self.start, self.width, 1), LogicState(1 - self.level)))


@dataclass(frozen=True)
class PatternStimulus:
    """Explicit state vector: ``states[i]`` at ``start + i*step``. Data only."""

    stimulus_id: str
    net_id: str
    start: Decimal
    step: Decimal
    states: tuple[LogicState, ...]

    def __post_init__(self):
        _ids(self.stimulus_id, self.net_id)
        object.__setattr__(self, "start", check_time(self.start))
        object.__setattr__(self, "step", _positive(self.step, "INVALID_PERIOD"))
        if not isinstance(self.states, tuple):
            raise _invalid("INVALID_PATTERN", "states must be a tuple of LogicState")
        _count(len(self.states))
        for s in self.states:
            check_state(s)
        _edge_time(self.start, self.step, len(self.states) - 1)

    def edges(self) -> Edges:
        return tuple((_edge_time(self.start, self.step, i), s) for i, s in enumerate(self.states))


STIMULUS_TYPES = (ConstantStimulus, ToggleStimulus, PulseStimulus, PatternStimulus)
