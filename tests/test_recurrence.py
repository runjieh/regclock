from datetime import date

import pytest

from regclock import BusinessCalendar, DayBasis, DeadlineKind, DeadlineSpec, RecurrenceFreq
from regclock.model.recurrence import (
    ExplicitDates,
    RecurrenceRule,
    compute_due_date,
    expand_recurring,
)


def test_compute_due_date_relative_calendar():
    spec = DeadlineSpec(
        kind=DeadlineKind.RELATIVE, offset_days=3, day_basis=DayBasis.CALENDAR
    )
    cal = BusinessCalendar(jurisdiction="ZZ")
    assert compute_due_date(spec, date(2026, 6, 10), cal) == date(2026, 6, 13)


def test_compute_due_date_relative_business():
    spec = DeadlineSpec(
        kind=DeadlineKind.RELATIVE, offset_days=3, day_basis=DayBasis.BUSINESS
    )
    cal = BusinessCalendar(jurisdiction="ZZ")
    # Friday + 3 business days -> Wednesday
    assert compute_due_date(spec, date(2026, 6, 12), cal) == date(2026, 6, 17)


def test_compute_due_date_absolute_month_day():
    spec = DeadlineSpec(kind=DeadlineKind.ABSOLUTE, month=3, day=31)
    cal = BusinessCalendar(jurisdiction="ZZ")
    # Anchor year drives the result.
    assert compute_due_date(spec, date(2026, 1, 1), cal) == date(2026, 3, 31)


def test_compute_due_date_absolute_explicit():
    spec = DeadlineSpec(kind=DeadlineKind.ABSOLUTE, absolute_date=date(2026, 12, 31))
    cal = BusinessCalendar(jurisdiction="ZZ")
    assert compute_due_date(spec, date(2025, 1, 1), cal) == date(2026, 12, 31)


def test_relative_without_offset_raises():
    spec = DeadlineSpec(kind=DeadlineKind.RELATIVE, offset_days=None)
    cal = BusinessCalendar(jurisdiction="ZZ")
    with pytest.raises(ValueError):
        compute_due_date(spec, date(2026, 6, 10), cal)


def test_recurring_quarterly():
    spec = DeadlineSpec(
        kind=DeadlineKind.RECURRING,
        recurrence=RecurrenceFreq.QUARTERLY,
        month=3,
        day=31,
    )
    dates = expand_recurring(spec, date(2026, 1, 1), date(2026, 12, 31))
    # Day-of-month "31" is clamped to 30 in 30-day months, and once clamped
    # it stays at 30 in subsequent steps (the anchor is not re-applied).
    # If you need calendar-quarter ends exactly, use ExplicitDates instead.
    assert dates == [
        date(2026, 3, 31),
        date(2026, 6, 30),
        date(2026, 9, 30),
        date(2026, 12, 30),
    ]


def test_recurring_requires_frequency():
    spec = DeadlineSpec(kind=DeadlineKind.RECURRING, recurrence=None)
    with pytest.raises(ValueError):
        expand_recurring(spec, date(2026, 1, 1), date(2026, 12, 31))


def test_recurrence_rule_interval():
    rule = RecurrenceRule(
        freq=RecurrenceFreq.MONTHLY, anchor=date(2026, 1, 15), interval=2
    )
    assert rule.occurrences(date(2026, 1, 1), date(2026, 12, 31)) == [
        date(2026, 1, 15),
        date(2026, 3, 15),
        date(2026, 5, 15),
        date(2026, 7, 15),
        date(2026, 9, 15),
        date(2026, 11, 15),
    ]


def test_recurrence_rule_zero_interval_raises():
    rule = RecurrenceRule(freq=RecurrenceFreq.DAILY, anchor=date(2026, 1, 1), interval=0)
    with pytest.raises(ValueError):
        rule.occurrences(date(2026, 1, 1), date(2026, 1, 10))


def test_explicit_dates_window():
    ed = ExplicitDates(dates=(date(2025, 1, 1), date(2026, 1, 1), date(2027, 1, 1)))
    assert ed.in_window(date(2026, 1, 1), date(2026, 12, 31)) == [date(2026, 1, 1)]
