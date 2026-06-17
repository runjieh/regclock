from datetime import date

import pytest

from regclock.lifecycle.events import Event
from regclock.schemas.types import EventKind
from regclock.utils.fiscal import (
    FiscalCalendar,
    FixedDateFiscalCalendar,
    LastWeekdayFiscalCalendar,
    fiscal_trigger_events,
)


def test_microsoft_fiscal_year_ends_30_jun():
    msft = FixedDateFiscalCalendar(start_month=7)
    assert msft.fiscal_year_end(2026) == date(2026, 6, 30)
    assert msft.fiscal_quarter_ends(2026) == [
        date(2025, 9, 30),
        date(2025, 12, 31),
        date(2026, 3, 31),
        date(2026, 6, 30),
    ]


def test_uk_individual_tax_year_5_apr():
    uk = FixedDateFiscalCalendar(start_month=4, start_day=6)
    assert uk.fiscal_year_end(2026) == date(2026, 4, 5)


def test_calendar_year_fiscal_calendar():
    cy = FixedDateFiscalCalendar(start_month=1, start_day=1)
    assert cy.fiscal_year_end(2026) == date(2026, 12, 31)


def test_apple_fiscal_year_ends_last_saturday_of_september():
    # Verified against published Apple 10-K filings.
    aapl = LastWeekdayFiscalCalendar(month=9, weekday=5)
    assert aapl.fiscal_year_end(2023) == date(2023, 9, 30)
    assert aapl.fiscal_year_end(2024) == date(2024, 9, 28)
    assert aapl.fiscal_year_end(2025) == date(2025, 9, 27)
    assert aapl.fiscal_year_end(2026) == date(2026, 9, 26)


def test_walmart_fiscal_year_ends_last_friday_of_january():
    wmt = LastWeekdayFiscalCalendar(month=1, weekday=4)
    # Walmart FY2024 = published as ending 26 Jan 2024 (last Friday of Jan).
    assert wmt.fiscal_year_end(2024) == date(2024, 1, 26)
    assert wmt.fiscal_year_end(2025) == date(2025, 1, 31)
    assert wmt.fiscal_year_end(2026) == date(2026, 1, 30)


def test_fiscal_calendars_satisfy_protocol():
    assert isinstance(FixedDateFiscalCalendar(start_month=7), FiscalCalendar)
    assert isinstance(LastWeekdayFiscalCalendar(month=9, weekday=5), FiscalCalendar)


def test_fiscal_trigger_events_year_granularity():
    aapl = LastWeekdayFiscalCalendar(month=9, weekday=5)
    triggers = fiscal_trigger_events(
        obligation_id="aapl.10k",
        calendar=aapl,
        fiscal_years=[2024, 2025, 2026],
    )
    assert len(triggers) == 3
    assert all(isinstance(e, Event) for e in triggers)
    assert all(e.kind is EventKind.TRIGGER for e in triggers)
    assert [e.occurred_on for e in triggers] == [
        date(2024, 9, 28),
        date(2025, 9, 27),
        date(2026, 9, 26),
    ]


def test_fiscal_trigger_events_quarterly_granularity():
    msft = FixedDateFiscalCalendar(start_month=7)
    triggers = fiscal_trigger_events(
        obligation_id="msft.10q",
        calendar=msft,
        fiscal_years=[2026],
        granularity="quarter",
    )
    assert len(triggers) == 4
    payloads = [e.payload["quarter"] for e in triggers]
    assert payloads == [1, 2, 3, 4]


def test_fiscal_trigger_events_invalid_granularity():
    msft = FixedDateFiscalCalendar(start_month=7)
    with pytest.raises(ValueError):
        fiscal_trigger_events(
            obligation_id="x",
            calendar=msft,
            fiscal_years=[2026],
            granularity="month",  # type: ignore[arg-type]
        )


def test_fixed_date_validates_month():
    with pytest.raises(ValueError):
        FixedDateFiscalCalendar(start_month=13)


def test_last_weekday_validates_weekday():
    with pytest.raises(ValueError):
        LastWeekdayFiscalCalendar(month=1, weekday=7)
