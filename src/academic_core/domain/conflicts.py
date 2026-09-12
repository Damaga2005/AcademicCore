"""Pure conflict detection (Phase 1).

Port of `detectar_conflictos`: warn, never block — the caller decides.
Operates on plain records so UI, services and tests share one implementation.
"""

from __future__ import annotations

from dataclasses import dataclass

from academic_core.domain.schedule import intervals_overlap, is_session_day, Series


@dataclass(frozen=True)
class TimedItem:
    kind: str  # "task" | "series"
    ref: str  # stable_id or db key
    title: str
    day: str  # ISO date for tasks; "" for series (expanded via Series)
    start: str
    end: str


@dataclass(frozen=True)
class Conflict:
    kind: str
    ref: str
    title: str
    day: str
    start: str
    end: str


def detect(day: str, start: str, end: str, tasks: list[TimedItem],
           series: list[tuple[TimedItem, Series]]) -> list[Conflict]:
    out: list[Conflict] = []
    for t in tasks:
        if t.day == day and intervals_overlap(start, end, t.start, t.end):
            out.append(Conflict("task", t.ref, t.title, day, t.start, t.end))
    from datetime import date as _date
    d = _date.fromisoformat(day)
    for item, s in series:
        if is_session_day(d, s) and intervals_overlap(start, end, s.start, s.end):
            out.append(Conflict("series", item.ref, item.title, day, s.start, s.end))
    return out
