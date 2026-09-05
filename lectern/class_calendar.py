"""Class-meeting calendar — expand a term's meeting patterns over a date range.

The deterministic core behind ``reg-admin-form``: administrative forms keep
asking *which* classes an absence actually touches, and the honest answer is a
function of three things the vault already knows — the term's meeting patterns,
the term boundaries, and the days campus does not hold class.

``meets`` strings are written by hand in two dialects (the term-spec's
``"TuTh 11:00-12:15"`` and the class-note's ``"TuTh 11:00 AM-12:15 PM"``), so
the parser accepts both, plus en/em dashes.

Nothing here reaches the network or the clock: every function takes the dates it
needs, which is what makes an absence record reproducible months later.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

# Weekday tokens, longest-first so "Th" wins over "T" and "Tu" over "T".
_DAY_TOKENS: list[tuple[str, int]] = [
    ("SU", 6), ("TU", 1), ("TH", 3), ("SA", 5),
    ("M", 0), ("T", 1), ("W", 2), ("F", 4), ("S", 5),
]
_WEEKDAY_NAME = ["Monday", "Tuesday", "Wednesday", "Thursday",
                 "Friday", "Saturday", "Sunday"]
_WEEKDAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

_DASHES = "‐‑‒–—―"
_TIME_RE = re.compile(
    r"(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<mer>[AaPp]\.?[Mm]\.?)?"
)


class MeetsParseError(ValueError):
    """Raised when a ``meets`` string cannot be read as days + a time range."""


@dataclass(frozen=True)
class MeetingPattern:
    """A parsed ``meets`` string: which weekdays, and the clock window."""

    weekdays: tuple[int, ...]          # Monday=0 … Sunday=6
    start: str | None = None           # "11:00", 24-hour
    end: str | None = None
    raw: str = ""

    @property
    def time_range(self) -> str:
        """``"11:00-12:15"``, or ``""`` when the pattern carried no times."""
        if self.start and self.end:
            return f"{self.start}-{self.end}"
        return self.start or ""

    def duration_hours(self) -> float | None:
        """Length of one meeting in hours, or ``None`` without both times."""
        if not (self.start and self.end):
            return None
        sh, sm = (int(x) for x in self.start.split(":"))
        eh, em = (int(x) for x in self.end.split(":"))
        return ((eh * 60 + em) - (sh * 60 + sm)) / 60.0


@dataclass(frozen=True)
class Meeting:
    """One class meeting on one date, carrying its section's identity."""

    date: date
    course: str
    section: str
    class_number: str | int | None
    room: str | None
    pattern: MeetingPattern
    topic: str | None = None           # filled in from the syllabus, when found

    @property
    def weekday_name(self) -> str:
        return _WEEKDAY_NAME[self.date.weekday()]

    @property
    def label(self) -> str:
        """``"CECS 378 §01"`` — how a section is named on a form."""
        return f"{self.course} §{self.section}"


@dataclass
class Closure:
    """A day (or span) with no class meetings, and why."""

    start: date
    end: date
    label: str

    def covers(self, day: date) -> bool:
        return self.start <= day <= self.end


def _to_date(value) -> date:
    """Coerce YAML's date/str/datetime into a ``date``."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value).strip())


def parse_weekdays(token: str) -> tuple[int, ...]:
    """Parse ``"TuTh"`` / ``"MWF"`` / ``"M/W"`` into Monday=0 weekday numbers.

    A bare ``T`` means Tuesday, the US academic-scheduling convention that makes
    ``TTh`` and ``TuTh`` the same pattern.
    """
    cleaned = re.sub(r"[\s,/&+-]", "", token).upper()
    if not cleaned:
        raise MeetsParseError(f"no weekday letters in {token!r}")
    days: list[int] = []
    i = 0
    while i < len(cleaned):
        for tok, num in _DAY_TOKENS:
            if cleaned.startswith(tok, i):
                if num not in days:
                    days.append(num)
                i += len(tok)
                break
        else:
            raise MeetsParseError(
                f"unrecognized weekday letter {cleaned[i]!r} in {token!r}"
            )
    return tuple(sorted(days))


def _parse_time(text: str, *, pm_hint: bool = False) -> str:
    """Parse one clock time into 24-hour ``"HH:MM"``.

    ``pm_hint`` carries an end-time meridiem backwards onto a start time that
    omitted it, so ``"3:30-4:45 PM"`` does not become an 03:30 class.
    """
    m = _TIME_RE.search(text)
    if not m:
        raise MeetsParseError(f"cannot read a time from {text!r}")
    hour = int(m.group("h"))
    minute = int(m.group("m") or 0)
    mer = (m.group("mer") or "").replace(".", "").upper()
    if mer == "PM" and hour != 12:
        hour += 12
    elif mer == "AM" and hour == 12:
        hour = 0
    elif not mer and pm_hint and hour < 12:
        hour += 12
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise MeetsParseError(f"time out of range in {text!r}")
    return f"{hour:02d}:{minute:02d}"


def parse_meets(meets: str) -> MeetingPattern:
    """Parse a ``meets`` string into a :class:`MeetingPattern`.

    Accepts both vault dialects — ``"TuTh 11:00-12:15"`` (term-spec) and
    ``"TuTh 11:00 AM-12:15 PM"`` (class-note), with any Unicode dash.
    """
    if not meets or not str(meets).strip():
        raise MeetsParseError("empty meets string")
    text = str(meets).strip()
    for dash in _DASHES:
        text = text.replace(dash, "-")
    # Split leading day letters from the rest at the first digit.
    m = re.match(r"^(?P<days>[A-Za-z\s,/&+]+?)\s*(?P<rest>\d.*)?$", text)
    if not m:
        raise MeetsParseError(f"cannot read weekdays from {meets!r}")
    weekdays = parse_weekdays(m.group("days"))
    rest = (m.group("rest") or "").strip()
    if not rest:
        return MeetingPattern(weekdays=weekdays, raw=text)
    halves = [h.strip() for h in rest.split("-", 1)]
    if len(halves) == 1:
        return MeetingPattern(weekdays=weekdays,
                              start=_parse_time(halves[0]), raw=text)
    end = _parse_time(halves[1])
    # If the end is PM and the start gave no meridiem, the start is PM too.
    start_has_mer = bool(_TIME_RE.search(halves[0]).group("mer"))
    end_hour = int(end.split(":")[0])
    start = _parse_time(halves[0], pm_hint=not start_has_mer and end_hour >= 12)
    if start > end and not start_has_mer:      # "11:00-12:15" style rollover
        start = _parse_time(halves[0])
    return MeetingPattern(weekdays=weekdays, start=start, end=end, raw=text)


def load_closures(spec: dict) -> list[Closure]:
    """Read ``no-instruction`` from a term-spec into :class:`Closure` objects.

    Each entry is either a bare date or a mapping with ``start``/``end`` (or
    ``date``) plus an optional ``label``. Absent key = no closures, and callers
    are expected to say so rather than pretend the term has none.
    """
    closures: list[Closure] = []
    for entry in spec.get("no-instruction") or []:
        if isinstance(entry, dict):
            if "date" in entry:
                start = end = _to_date(entry["date"])
            else:
                start = _to_date(entry["start"])
                end = _to_date(entry.get("end", entry["start"]))
            label = str(entry.get("label", "no instruction"))
        else:
            start = end = _to_date(entry)
            label = "no instruction"
        if end < start:
            raise ValueError(f"closure ends before it starts: {start} > {end}")
        closures.append(Closure(start=start, end=end, label=label))
    return sorted(closures, key=lambda c: c.start)


def daterange(start: date, end: date):
    """Yield every date from ``start`` through ``end`` inclusive."""
    if end < start:
        raise ValueError(f"range ends before it starts: {start} > {end}")
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


@dataclass
class AffectedDay:
    """One calendar day inside an absence, and what it costs."""

    date: date
    meetings: list[Meeting] = field(default_factory=list)
    closure: Closure | None = None
    in_term: bool = True

    @property
    def weekday_name(self) -> str:
        return _WEEKDAY_NAME[self.date.weekday()]

    @property
    def weekday_abbr(self) -> str:
        return _WEEKDAY_ABBR[self.date.weekday()]

    @property
    def note(self) -> str:
        """Why a day with no meetings has none — blank when it does have some."""
        if self.meetings:
            return ""
        if not self.in_term:
            return "outside the instruction period"
        if self.closure:
            return self.closure.label
        return "no class scheduled"


def meetings_in_range(spec: dict, start: date, end: date,
                      *, sections: list[dict] | None = None) -> list[AffectedDay]:
    """Expand a term-spec's sections across ``start``..``end``.

    Returns one :class:`AffectedDay` per calendar day in the range — including
    the empty ones, because a form reviewer reading "Thu 11/26: Thanksgiving
    (campus closed)" learns something that a silently omitted row does not tell
    them.
    """
    start, end = _to_date(start), _to_date(end)
    term_start = _to_date(spec["start"]) if spec.get("start") else None
    term_end = _to_date(spec["end"]) if spec.get("end") else None
    closures = load_closures(spec)
    secs = sections if sections is not None else spec.get("sections") or []

    parsed: list[tuple[dict, MeetingPattern]] = []
    for sec in secs:
        parsed.append((sec, parse_meets(sec["meets"])))

    days: list[AffectedDay] = []
    for day in daterange(start, end):
        in_term = True
        if term_start and day < term_start:
            in_term = False
        if term_end and day > term_end:
            in_term = False
        closure = next((c for c in closures if c.covers(day)), None)
        entry = AffectedDay(date=day, closure=closure, in_term=in_term)
        if in_term and closure is None:
            for sec, pattern in parsed:
                if day.weekday() in pattern.weekdays:
                    entry.meetings.append(Meeting(
                        date=day,
                        course=str(sec["course"]),
                        section=str(sec["section"]),
                        class_number=sec.get("class-number"),
                        room=sec.get("room"),
                        pattern=pattern,
                    ))
            entry.meetings.sort(key=lambda m: (m.pattern.start or "", m.label))
        days.append(entry)
    return days


def all_meetings(days: list[AffectedDay]) -> list[Meeting]:
    """Flatten :func:`meetings_in_range` output to just the meetings."""
    return [m for d in days for m in d.meetings]


def contact_hours(days: list[AffectedDay]) -> float | None:
    """Total scheduled contact hours across the affected meetings.

    ``None`` if any meeting lacks a time range — a partial total on a leave form
    is worse than no total, since it reads as complete.
    """
    total = 0.0
    for meeting in all_meetings(days):
        hours = meeting.pattern.duration_hours()
        if hours is None:
            return None
        total += hours
    return round(total, 2)
