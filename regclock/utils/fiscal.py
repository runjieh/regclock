"""Entity-specific fiscal calendars (opt-in).

regclock's default deadline model is calendar-year: an ``ABSOLUTE`` deadline
with ``month=3, day=31`` always means 31 March in the Gregorian calendar.
This is correct for the clear majority of small-entity compliance work.

Some entities — US-listed companies, large multinationals, retailers — run
on a fiscal year that does not align with the Gregorian calendar:

  * Microsoft   fiscal year 1 Jul .. 30 Jun
  * Apple       fiscal year ends on the last Saturday of September
  * Walmart     fiscal year ends on the Friday closest to 31 January
  * UK individuals   tax year 6 Apr .. 5 Apr

This module is **not imported by the core engine** and the scheduler never
reaches for it. Users opt in to fiscal-year semantics in three steps:

  1. Construct one of the fiscal calendars below.
  2. Call :func:`fiscal_trigger_events` to materialise fiscal-year (or
     fiscal-quarter) ends as :class:`~regclock.lifecycle.events.Event`
     records with ``kind=TRIGGER``.
  3. Append those events to the regular :class:`EventLog` and pair them
     with a ``RELATIVE`` obligation whose ``offset_days`` express
     "N days after fiscal year-end".

The engine itself remains pure: no special-casing of fiscal years inside
:mod:`regclock.lifecycle`. If you don't import from this module, nothing
in regclock behaves differently.

Convention: fiscal year ``N`` is the one that **ends in calendar year N**.
So Microsoft FY2026 covers 1 Jul 2025 .. 30 Jun 2026, and Apple FY2025
ends on 27 Sep 2025. This matches the public reporting conventions of all
three example companies above.
"""

from __future__ import annotations

import calendar as _stdlib_calendar
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal, Protocol, runtime_checkable

from regclock.lifecycle.events import Event
from regclock.schemas.types import EventKind


@runtime_checkable
class FiscalCalendar(Protocol):
    """A calendar that knows when fiscal years and quarters end.

    Custom calendars (e.g. 4-4-5 retail patterns) can implement this
    protocol and be passed straight to :func:`fiscal_trigger_events`.
    """

    def fiscal_year_end(self, fiscal_year: int) -> date:
        """Return the last day of fiscal year ``fiscal_year``."""

    def fiscal_quarter_ends(self, fiscal_year: int) -> list[date]:
        """Return [Q1_end, Q2_end, Q3_end, Q4_end] of ``fiscal_year``."""


@dataclass(frozen=True)
class FixedDateFiscalCalendar:
    """Fiscal year that starts on a fixed (month, day) each calendar year.

    Suitable for entities whose fiscal-year boundary is a stable date:
    Microsoft (7, 1), Japanese corporates (4, 1), UK individuals (4, 6),
    US federal government (10, 1).

    Attributes:
        start_month: Month in which the fiscal year starts (1..12).
        start_day: Day of month on which it starts (defaults to 1).

    Example:
        >>> msft = FixedDateFiscalCalendar(start_month=7)
        >>> msft.fiscal_year_end(2026)
        datetime.date(2026, 6, 30)
        >>> msft.fiscal_quarter_ends(2026)
        [datetime.date(2025, 9, 30), datetime.date(2025, 12, 31),
         datetime.date(2026, 3, 31), datetime.date(2026, 6, 30)]

    """

    start_month: int
    start_day: int = 1

    def __post_init__(self) -> None:
        if not 1 <= self.start_month <= 12:
            raise ValueError("start_month must be in 1..12")
        if not 1 <= self.start_day <= 31:
            raise ValueError("start_day must be in 1..31")

    def fiscal_year_end(self, fiscal_year: int) -> date:
        """Return the last day of fiscal year ``fiscal_year``.

        For calendar-year fiscal calendars (start = 1 Jan) this is simply
        31 December of ``fiscal_year``. Otherwise it is the day before the
        next fiscal year starts.
        """
        if self.start_month == 1 and self.start_day == 1:
            return date(fiscal_year, 12, 31)
        next_start = _clamp_day(fiscal_year, self.start_month, self.start_day)
        return next_start - timedelta(days=1)

    def fiscal_quarter_ends(self, fiscal_year: int) -> list[date]:
        """Return Q1..Q4 end dates of fiscal year ``fiscal_year``.

        Each quarter is three calendar months long, anchored at the fiscal-
        year start. Day-of-month is clamped to the target month's length.
        """
        if self.start_month == 1 and self.start_day == 1:
            start = date(fiscal_year, 1, 1)
        else:
            start = _clamp_day(fiscal_year - 1, self.start_month, self.start_day)
        ends: list[date] = []
        for q in range(1, 5):
            next_q_start = _add_months(start, q * 3)
            ends.append(next_q_start - timedelta(days=1))
        return ends


@dataclass(frozen=True)
class LastWeekdayFiscalCalendar:
    """52/53-week fiscal year ending on the last ``weekday`` of ``month``.

    Suitable for entities on a 52/53-week retail/tech calendar:

      * Apple   last Saturday of September   ``(9, weekday=5)``
      * Walmart last Friday of January       ``(1, weekday=4)``
      * Target  last Saturday of January     ``(1, weekday=5)``

    Quarter ends sit at +13, +26, +39 weeks after the **prior** fiscal-
    year end, with Q4 absorbing the extra week in 53-week years.

    Attributes:
        month: The month in which fiscal year ends (1..12).
        weekday: Python weekday convention: 0=Monday .. 6=Sunday.

    Example:
        >>> aapl = LastWeekdayFiscalCalendar(month=9, weekday=5)
        >>> aapl.fiscal_year_end(2025)
        datetime.date(2025, 9, 27)

    """

    month: int
    weekday: int

    def __post_init__(self) -> None:
        if not 1 <= self.month <= 12:
            raise ValueError("month must be in 1..12")
        if not 0 <= self.weekday <= 6:
            raise ValueError("weekday must be in 0..6 (0=Monday)")

    def fiscal_year_end(self, fiscal_year: int) -> date:
        """Last occurrence of ``self.weekday`` in ``self.month`` of ``fiscal_year``."""
        return _last_weekday_in_month(fiscal_year, self.month, self.weekday)

    def fiscal_quarter_ends(self, fiscal_year: int) -> list[date]:
        """Q1..Q4 end dates, with Q4 absorbing the 53rd week when present."""
        prior_end = self.fiscal_year_end(fiscal_year - 1)
        this_end = self.fiscal_year_end(fiscal_year)
        return [
            prior_end + timedelta(weeks=13),
            prior_end + timedelta(weeks=26),
            prior_end + timedelta(weeks=39),
            this_end,
        ]


def fiscal_trigger_events(
    *,
    obligation_id: str,
    calendar: FiscalCalendar,
    fiscal_years: Iterable[int],
    granularity: Literal["year", "quarter"] = "year",
) -> list[Event]:
    """Materialise fiscal-year or -quarter ends as ``TRIGGER`` events.

    Pair the returned events with a ``RELATIVE`` :class:`Obligation` whose
    ``offset_days`` express "N days after the fiscal period closes".

    Args:
        obligation_id: ID of the obligation these triggers are for.
        calendar: Any :class:`FiscalCalendar` implementation.
        fiscal_years: Which fiscal years to materialise (e.g.
            ``range(2024, 2027)``).
        granularity: ``"year"`` for one trigger per fiscal year,
            ``"quarter"`` for four triggers per fiscal year.

    Returns:
        A list of :class:`Event` records ready to be appended to an
        :class:`EventLog`. Each event's ``payload`` includes
        ``fiscal_year`` and (for quarterly) ``quarter``.

    Raises:
        ValueError: If ``granularity`` is neither ``"year"`` nor
            ``"quarter"``.

    Example:
        >>> aapl = LastWeekdayFiscalCalendar(month=9, weekday=5)
        >>> triggers = fiscal_trigger_events(
        ...     obligation_id="aapl.10k",
        ...     calendar=aapl,
        ...     fiscal_years=range(2024, 2027),
        ... )
        >>> [e.occurred_on for e in triggers]
        [datetime.date(2024, 9, 28), datetime.date(2025, 9, 27),
         datetime.date(2026, 9, 26)]

    """
    events: list[Event] = []
    for fy in fiscal_years:
        if granularity == "year":
            events.append(
                Event(
                    obligation_id=obligation_id,
                    kind=EventKind.TRIGGER,
                    occurred_on=calendar.fiscal_year_end(fy),
                    payload={"fiscal_year": fy, "period": "year_end"},
                )
            )
        elif granularity == "quarter":
            for quarter, end in enumerate(calendar.fiscal_quarter_ends(fy), start=1):
                events.append(
                    Event(
                        obligation_id=obligation_id,
                        kind=EventKind.TRIGGER,
                        occurred_on=end,
                        payload={
                            "fiscal_year": fy,
                            "period": "quarter_end",
                            "quarter": quarter,
                        },
                    )
                )
        else:
            raise ValueError(
                f"granularity must be 'year' or 'quarter', got {granularity!r}"
            )
    return events


# ---- helpers --------------------------------------------------------------


def _clamp_day(year: int, month: int, day: int) -> date:
    """Build a date in ``(year, month)`` with ``day`` clamped to month length."""
    max_day = _stdlib_calendar.monthrange(year, month)[1]
    return date(year, month, min(day, max_day))


def _add_months(d: date, months: int) -> date:
    """Add ``months`` to ``d``, clamping the day to the target month's length."""
    year = d.year + (d.month - 1 + months) // 12
    month = (d.month - 1 + months) % 12 + 1
    return _clamp_day(year, month, d.day)


def _last_weekday_in_month(year: int, month: int, weekday: int) -> date:
    """Return the last occurrence of ``weekday`` (0=Mon..6=Sun) in ``(year, month)``."""
    last_day = _stdlib_calendar.monthrange(year, month)[1]
    d = date(year, month, last_day)
    offset = (d.weekday() - weekday) % 7
    return d - timedelta(days=offset)
