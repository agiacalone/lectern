import textwrap
from datetime import date

import pytest
import yaml

from lectern.class_calendar import (
    MeetsParseError,
    all_meetings,
    contact_hours,
    load_closures,
    meetings_in_range,
    parse_meets,
    parse_weekdays,
)

SPEC = yaml.safe_load(textwrap.dedent("""\
    term: fa26
    start: 2026-08-24
    end: 2026-12-11
    no-instruction:
      - { date: 2026-09-07, label: "Labor Day (campus closed)" }
      - { start: 2026-11-23, end: 2026-11-25, label: "Fall Break" }
    sections:
      - course: CECS 378
        section: "01"
        class-number: 4785
        room: VEC-331
        meets: "TuTh 11:00-12:15"
      - course: CECS 326
        section: "01"
        class-number: 1131
        room: DESN-112
        meets: "TuTh 17:30-18:45"
"""))


@pytest.mark.parametrize("token,expected", [
    ("TuTh", (1, 3)),
    ("TTh", (1, 3)),          # bare T is Tuesday, the scheduling convention
    ("MWF", (0, 2, 4)),
    ("M/W", (0, 2)),
    ("Sa", (5,)),
    ("Su", (6,)),
    ("MTuWThF", (0, 1, 2, 3, 4)),
])
def test_parse_weekdays(token, expected):
    assert parse_weekdays(token) == expected


def test_parse_weekdays_rejects_junk():
    with pytest.raises(MeetsParseError):
        parse_weekdays("XQ")


@pytest.mark.parametrize("meets,days,rng,hours", [
    ("TuTh 11:00-12:15", (1, 3), "11:00-12:15", 1.25),
    ("TuTh 11:00 AM-12:15 PM", (1, 3), "11:00-12:15", 1.25),
    ("TuTh 11:00 AM–12:15 PM", (1, 3), "11:00-12:15", 1.25),   # en dash
    ("MWF 09:00-09:50", (0, 2, 4), "09:00-09:50", pytest.approx(0.8333, rel=1e-3)),
    ("M 18:00-20:45", (0,), "18:00-20:45", 2.75),
])
def test_parse_meets_dialects(meets, days, rng, hours):
    p = parse_meets(meets)
    assert p.weekdays == days
    assert p.time_range == rng
    assert p.duration_hours() == hours


def test_meridiem_carries_back_to_the_start_time():
    """`3:30-4:45 PM` is an afternoon class, not an 03:30 one."""
    p = parse_meets("TTh 3:30-4:45 PM")
    assert p.time_range == "15:30-16:45"


def test_parse_meets_without_times():
    p = parse_meets("TuTh")
    assert p.weekdays == (1, 3)
    assert p.duration_hours() is None


def test_parse_meets_rejects_empty():
    with pytest.raises(MeetsParseError):
        parse_meets("")


def test_load_closures_spans_and_singles():
    closures = load_closures(SPEC)
    assert len(closures) == 2
    assert closures[0].covers(date(2026, 9, 7))
    assert not closures[0].covers(date(2026, 9, 8))
    assert closures[1].covers(date(2026, 11, 24))


def test_meetings_on_a_teaching_thursday():
    days = meetings_in_range(SPEC, date(2026, 9, 10), date(2026, 9, 10))
    meetings = all_meetings(days)
    assert [m.label for m in meetings] == ["CECS 378 §01", "CECS 326 §01"]
    assert meetings[0].class_number == 4785
    assert meetings[0].room == "VEC-331"
    # sorted by start time, so the form lists the day in the order it happens
    assert [m.pattern.start for m in meetings] == ["11:00", "17:30"]


def test_closure_day_yields_no_meetings_but_says_why():
    days = meetings_in_range(SPEC, date(2026, 11, 24), date(2026, 11, 24))
    assert all_meetings(days) == []
    assert days[0].note == "Fall Break"


def test_a_monday_has_no_tuth_meetings():
    days = meetings_in_range(SPEC, date(2026, 9, 14), date(2026, 9, 14))
    assert all_meetings(days) == []
    assert days[0].note == "no class scheduled"


def test_dates_outside_the_term_are_flagged():
    days = meetings_in_range(SPEC, date(2026, 12, 17), date(2026, 12, 17))
    assert all_meetings(days) == []
    assert days[0].note == "outside the instruction period"


def test_contact_hours_sums_the_affected_meetings():
    days = meetings_in_range(SPEC, date(2026, 9, 8), date(2026, 9, 10))
    # Tue 9/8 and Thu 9/10, two sections each, 1.25h apiece
    assert len(all_meetings(days)) == 4
    assert contact_hours(days) == 5.0


def test_contact_hours_is_none_when_a_pattern_lacks_times():
    spec = {**SPEC, "sections": [{"course": "CECS 326", "section": "01",
                                  "meets": "TuTh"}]}
    days = meetings_in_range(spec, date(2026, 9, 10), date(2026, 9, 10))
    assert contact_hours(days) is None


def test_range_ending_before_it_starts_is_rejected():
    with pytest.raises(ValueError):
        list(meetings_in_range(SPEC, date(2026, 9, 10), date(2026, 9, 1)))
