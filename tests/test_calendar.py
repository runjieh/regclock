from datetime import date

import pytest

from regclock import BusinessCalendar


def test_weekend_is_not_business_day():
    cal = BusinessCalendar(jurisdiction="ZZ")  # unknown jurisdiction -> no holidays
    assert not cal.is_business_day(date(2026, 6, 13))  # Saturday
    assert not cal.is_business_day(date(2026, 6, 14))  # Sunday
    assert cal.is_business_day(date(2026, 6, 12))      # Friday


def test_add_business_days_skips_weekend():
    cal = BusinessCalendar(jurisdiction="ZZ")
    # Friday + 1 business day -> Monday
    assert cal.add_business_days(date(2026, 6, 12), 1) == date(2026, 6, 15)
    # Friday + 3 business days -> Wednesday
    assert cal.add_business_days(date(2026, 6, 12), 3) == date(2026, 6, 17)


def test_add_business_days_zero_advances_to_next_business_day():
    cal = BusinessCalendar(jurisdiction="ZZ")
    # Saturday + 0 business days -> Monday
    assert cal.add_business_days(date(2026, 6, 13), 0) == date(2026, 6, 15)
    # Friday + 0 business days -> Friday (already business day)
    assert cal.add_business_days(date(2026, 6, 12), 0) == date(2026, 6, 12)


def test_sub_business_days():
    cal = BusinessCalendar(jurisdiction="ZZ")
    # Monday - 1 business day -> Friday
    assert cal.sub_business_days(date(2026, 6, 15), 1) == date(2026, 6, 12)


def test_negative_offsets_raise():
    cal = BusinessCalendar(jurisdiction="ZZ")
    with pytest.raises(ValueError):
        cal.add_business_days(date(2026, 6, 12), -1)
    with pytest.raises(ValueError):
        cal.sub_business_days(date(2026, 6, 12), -1)


def test_business_days_between_half_open():
    cal = BusinessCalendar(jurisdiction="ZZ")
    # Mon -> Fri (exclusive): 4 business days (Mon, Tue, Wed, Thu)
    assert cal.business_days_between(date(2026, 6, 15), date(2026, 6, 19)) == 4
    assert cal.business_days_between(date(2026, 6, 15), date(2026, 6, 15)) == 0


def test_extra_holidays_take_precedence():
    cal = BusinessCalendar(
        jurisdiction="ZZ",
        extra_holidays=frozenset({date(2026, 6, 15)}),
    )
    assert cal.is_holiday(date(2026, 6, 15))
    assert not cal.is_business_day(date(2026, 6, 15))
    # Friday + 1 should skip both weekend AND the Monday holiday -> Tuesday
    assert cal.add_business_days(date(2026, 6, 12), 1) == date(2026, 6, 16)


def test_jurisdiction_normalised_to_upper():
    cal = BusinessCalendar(jurisdiction="es")
    assert cal.jurisdiction == "ES"


def test_iter_business_days_inclusive():
    cal = BusinessCalendar(jurisdiction="ZZ")
    days = list(cal.iter_business_days(date(2026, 6, 15), date(2026, 6, 19)))
    assert days == [
        date(2026, 6, 15),
        date(2026, 6, 16),
        date(2026, 6, 17),
        date(2026, 6, 18),
        date(2026, 6, 19),
    ]
