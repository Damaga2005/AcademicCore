# SPDX-License-Identifier: MIT
"""iCalendar (RFC 5545 subset) adapter — F4.1 (port of Gestion ics/importar_ics).

Export: tasks as VEVENT (timed = floating local DTSTART/DTEND; untimed =
all-day DATE with exclusive DTEND) and each class series as ONE VEVENT with
a weekly/fortnightly RRULE. UIDs are stable (entity stable ids), output is
byte-deterministic for the same input (DTSTAMP is an explicit argument),
CRLF line endings and 75-octet folding per RFC 5545.

Import: bounded parser (size, event count, line length). UTC times are
converted to peninsular Spain local time without tzdata (Gestion rule:
UTC+2 between the last Sunday of March and of October at 01:00 UTC, else
UTC+1). Nothing is fetched, executed or written here: callers get plain
records and decide (human review) what to persist.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from academic_core.errors import AcademicCoreError

MAX_BYTES = 2 * 1024 * 1024
MAX_EVENTS = 5000
MAX_LINE = 8192
BYDAY = {1: "MO", 2: "TU", 3: "WE", 4: "TH", 5: "FR", 6: "SA", 7: "SU"}


class IcsError(AcademicCoreError):
    code = "AC-ICS-001"
    category = "adapter"


def escape(text: str) -> str:
    return (str(text or "").replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n"))


def unescape(value: str) -> str:
    return re.sub(r"\\([,;nN\\])", lambda m: "\n" if m.group(1) in "nN" else m.group(1), value)


def _fold(line: str) -> str:
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > (75 if not parts else 74):
            parts.append(cur.decode("utf-8"))
            cur = b""
        cur += b
    parts.append(cur.decode("utf-8"))
    return "\r\n ".join(parts)


def _hhmmss(hhmm: str) -> str:
    h, m = hhmm.split(":")[:2]
    return f"{int(h):02d}{int(m):02d}00"


@dataclass(frozen=True)
class ExportTask:
    uid: str
    title: str
    day: date
    start: str = ""
    end: str = ""
    location: str = ""
    description: str = ""
    prefix: str = ""  # subject acronym/name


@dataclass(frozen=True)
class ExportSeries:
    uid: str
    title: str
    weekday: int
    start: str
    end: str
    first_session: date | None
    last_day: date
    interval_weeks: int = 1
    location: str = ""
    prefix: str = ""


def export_calendar(tasks: list[ExportTask], series: list[ExportSeries], *,
                    dtstamp: str, prodid: str = "-//AcademicCore//F4.1//ES") -> str:
    if not re.fullmatch(r"\d{8}T\d{6}Z", dtstamp):
        raise IcsError("dtstamp must be YYYYMMDDTHHMMSSZ")
    out = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{prodid}", "CALSCALE:GREGORIAN"]
    for t in sorted(tasks, key=lambda t: (t.day, t.start, t.uid)):
        out += ["BEGIN:VEVENT", f"UID:{t.uid}@academiccore.local", f"DTSTAMP:{dtstamp}"]
        d = t.day.strftime("%Y%m%d")
        if t.start and t.end:
            out += [f"DTSTART:{d}T{_hhmmss(t.start)}", f"DTEND:{d}T{_hhmmss(t.end)}"]
        else:
            out += [f"DTSTART;VALUE=DATE:{d}",
                    f"DTEND;VALUE=DATE:{(t.day + timedelta(days=1)).strftime('%Y%m%d')}"]
        out.append("SUMMARY:" + escape(f"{t.prefix} · {t.title}" if t.prefix else t.title))
        if t.location:
            out.append("LOCATION:" + escape(t.location))
        if t.description:
            out.append("DESCRIPTION:" + escape(t.description))
        out.append("END:VEVENT")
    for s in sorted(series, key=lambda s: (s.weekday, s.start, s.uid)):
        if s.first_session is None:
            continue  # empty series: nothing to schedule
        d = s.first_session.strftime("%Y%m%d")
        rule = f"RRULE:FREQ=WEEKLY;BYDAY={BYDAY[s.weekday]}"
        if s.interval_weeks > 1:
            rule += f";INTERVAL={s.interval_weeks}"
        rule += f";UNTIL={s.last_day.strftime('%Y%m%d')}T235959Z"
        out += ["BEGIN:VEVENT", f"UID:{s.uid}@academiccore.local", f"DTSTAMP:{dtstamp}",
                f"DTSTART:{d}T{_hhmmss(s.start)}", f"DTEND:{d}T{_hhmmss(s.end)}", rule,
                "SUMMARY:" + escape(f"{s.prefix} · {s.title}" if s.prefix else s.title)]
        if s.location:
            out.append("LOCATION:" + escape(s.location))
        out.append("END:VEVENT")
    out.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in out) + "\r\n"


# ------------------------------------------------------------------ import

@dataclass(frozen=True)
class IcsEvent:
    summary: str
    day: date
    time: str | None  # "HH:MM" local, None = all-day
    course: str  # first CATEGORIES value (Moodle course name)
    url: str
    description: str
    uid: str


def _last_sunday(year: int, month: int) -> date:
    d = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def utc_to_madrid(dt: datetime) -> datetime:
    start = datetime.combine(_last_sunday(dt.year, 3), datetime.min.time()) + timedelta(hours=1)
    end = datetime.combine(_last_sunday(dt.year, 10), datetime.min.time()) + timedelta(hours=1)
    return dt + timedelta(hours=2 if start <= dt < end else 1)


def _when(params: str, value: str) -> tuple[date, str | None]:
    value = value.strip()
    if "VALUE=DATE" in params or re.fullmatch(r"\d{8}", value):
        return datetime.strptime(value[:8], "%Y%m%d").date(), None
    dt = datetime.strptime(value.rstrip("Z"), "%Y%m%dT%H%M%S")
    if value.endswith("Z"):
        dt = utc_to_madrid(dt)
    return dt.date(), dt.strftime("%H:%M")


def parse_calendar(raw: bytes) -> list[IcsEvent]:
    if len(raw) > MAX_BYTES:
        raise IcsError("calendar file too large")
    text = raw.decode("utf-8-sig", errors="replace")
    if "BEGIN:VCALENDAR" not in text:
        raise IcsError("not an iCalendar file")
    lines: list[str] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line[:1] in (" ", "\t") and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line)
        if len(lines[-1]) > MAX_LINE:
            raise IcsError("calendar line too long")
    events: list[dict] = []
    cur: dict | None = None
    for line in lines:
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT":
            if cur is not None:
                events.append(cur)
                if len(events) > MAX_EVENTS:
                    raise IcsError("too many events")
            cur = None
        elif cur is not None and ":" in line:
            head, value = line.split(":", 1)
            name, _, params = head.partition(";")
            cur.setdefault(name.upper(), (params.upper(), unescape(value)))
    out: list[IcsEvent] = []
    for ev in events:
        if "SUMMARY" not in ev or "DTSTART" not in ev:
            continue
        try:
            day, time = _when(*ev["DTSTART"])
        except ValueError:
            continue  # malformed date: skipped and counted by the caller
        out.append(IcsEvent(ev["SUMMARY"][1].strip(), day, time,
                            ev.get("CATEGORIES", ("", ""))[1].split(",")[0].strip(),
                            ev.get("URL", ("", ""))[1].strip(),
                            ev.get("DESCRIPTION", ("", ""))[1], ev.get("UID", ("", ""))[1]))
    return sorted(out, key=lambda e: (e.day, e.time or "", e.summary, e.uid))
