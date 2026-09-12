"""Pure schedule mathematics (Phase 1).

Ports Gestion-Academica `fechas_sesiones_horario` semantics exactly:
- One row = whole recurring series; concrete dates computed on demand.
- First occurrence of the weekday on/after fecha_inicio anchors the pattern;
  quincenal (interval 2) steps from that anchor, NOT from fecha_inicio.
- fecha_fin inclusive. No per-session exceptions: edit/delete hits the series.
- intervals_overlap uses [start, end) — touching edges do NOT overlap.

Generic extensions (documented, see docs/migration/CONFLICTS.md):
- dia_semana 1..7 (original grid was Mon–Fri 1..5); Academic Core allows
  weekend sessions, validation accepts 1..7.
- No other semantic change; equivalence tests pin identical output on 1..5.

No Qt. No SQLAlchemy. No I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

VALID_WEEKDAYS = (1, 2, 3, 4, 5, 6, 7)  # ISO 1=Mon..7=Sun
VALID_INTERVALS = (1, 2)  # 1=weekly, 2=fortnightly


@dataclass(frozen=True)
class Series:
    subject_id: str
    kind: str  # teoria|problemas|laboratorio|seminario|otro
    weekday: int  # ISO 1..7
    start: str  # "HH:MM"
    end: str  # "HH:MM"
    first_day: date
    last_day: date
    interval_weeks: int = 1
    room: str = ""

    def __post_init__(self) -> None:
        if self.weekday not in VALID_WEEKDAYS:
            raise ValueError(f"weekday must be one of {VALID_WEEKDAYS}")
        if self.interval_weeks not in VALID_INTERVALS:
            raise ValueError(f"interval_weeks must be one of {VALID_INTERVALS}")
        if self.end <= self.start:
            raise ValueError("end must be after start")
        if self.last_day < self.first_day:
            raise ValueError("last_day must be on/after first_day")


def expand_sessions(s: Series) -> list[date]:
    """Concrete session dates, first_day..last_day inclusive."""
    delta = (s.weekday - 1 - s.first_day.weekday()) % 7
    current = s.first_day + timedelta(days=delta)
    step = timedelta(weeks=s.interval_weeks)
    out: list[date] = []
    while current <= s.last_day:
        if current >= s.first_day:
            out.append(current)
        current += step
    return out


def is_session_day(day: date, s: Series) -> bool:
    """O(1) membership check without expanding the whole series."""
    if not (s.first_day <= day <= s.last_day):
        return False
    if day.isoweekday() != s.weekday:
        return False
    delta = (s.weekday - 1 - s.first_day.weekday()) % 7
    anchor = s.first_day + timedelta(days=delta)
    return (day - anchor).days % (7 * s.interval_weeks) == 0


def intervals_overlap(a_start: str, a_end: str, b_start: str, b_end: str) -> bool:
    """True when [a_start,a_end) and [b_start,b_end) intersect ("HH:MM")."""
    return a_start < b_end and b_start < a_end
