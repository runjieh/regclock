"""Recurrence and relative/absolute deadline rules.

This module turns the declarative ``DeadlineSpec`` from
:mod:`regclock.model.obligation` into a concrete sequence of dates over a
horizon. It is the single place where the package interprets recurrence
semantics; the rest of the engine treats the output as opaque data.
"""

from __future__ import annotations

import calendar as _stdlib_calendar
from dataclasses import dataclass
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from regclock.model.calendar import BusinessCalendar
from regclock.model.obligation import DeadlineSpec
from regclock.schemas.types import DayBasis, DeadlineKind, RecurrenceFreq


@dataclass(frozen=True)
class ExplicitDates:
    """A pre-materialised list of due dates.

    Useful when the recurrence cannot be expressed in a single
    :class:`RecurrenceRule` (e.g. an irregular legislative calendar).

    Attributes:
        dates: Sorted, deduplicated list of due dates.

    """

    dates: tuple[date, ...]

    def in_window(self, start: date, end: date) -> list[date]:
        """Return all explicit dates that fall within ``[start, end]``.

        Args:
            start: Inclusive lower bound.
            end: Inclusive upper bound.

        Returns:
            A new list containing the matching dates in order.

        """
        return [d for d in self.dates if start <= d <= end]


@dataclass(frozen=True)
class RecurrenceRule:
    """Compact recurrence description with optional offsets.

    Attributes:
        freq: How often the deadline recurs.
        anchor: The reference date that anchors the recurrence. For
            annual rules, only ``month`` and ``day`` are usually relevant.
        interval: Step between occurrences (``1`` = every period,
            ``2`` = every other period, etc.). Defaults to ``1``.

    """

    freq: RecurrenceFreq
    anchor: date
    interval: int = 1

    def occurrences(self, start: date, end: date) -> list[date]:
        """Yield occurrence dates within ``[start, end]``.

        Args:
            start: Inclusive lower bound.
            end: Inclusive upper bound.

        Returns:
            Sorted list of occurrence dates.

        Raises:
            ValueError: If ``interval`` is not positive.

        """
        if self.interval < 1:
            raise ValueError("interval must be >= 1")

        step = _step_for(self.freq, self.interval)
        cursor = _align_to_anchor(self.anchor, start, self.freq)
        out: list[date] = []
        while cursor <= end:
            if cursor >= start:
                out.append(cursor)
            cursor = cursor + step
        return out


def _step_for(freq: RecurrenceFreq, interval: int) -> relativedelta:
    """Build a ``relativedelta`` step for a given frequency."""
    if freq is RecurrenceFreq.DAILY:
        return relativedelta(days=interval)
    if freq is RecurrenceFreq.WEEKLY:
        return relativedelta(weeks=interval)
    if freq is RecurrenceFreq.MONTHLY:
        return relativedelta(months=interval)
    if freq is RecurrenceFreq.QUARTERLY:
        return relativedelta(months=3 * interval)
    if freq is RecurrenceFreq.ANNUALLY:
        return relativedelta(years=interval)
    raise ValueError(f"Unsupported frequency: {freq}")


def _align_to_anchor(anchor: date, start: date, freq: RecurrenceFreq) -> date:
    """Move ``anchor`` forward until it is on/after ``start``.

    For annual rules we walk year-by-year; for monthly and quarterly we
    walk in months; for daily/weekly we walk in days/weeks. The result is
    the first occurrence ``>= start`` that respects the anchor pattern.
    """
    if anchor >= start:
        return anchor
    if freq is RecurrenceFreq.ANNUALLY:
        candidate = anchor
        while candidate < start:
            try:
                candidate = candidate.replace(year=candidate.year + 1)
            except ValueError:
                # Feb-29 anchor in a non-leap year: clamp to Feb-28.
                candidate = date(candidate.year + 1, 2, 28)
        return candidate
    if freq is RecurrenceFreq.MONTHLY:
        candidate = anchor
        while candidate < start:
            candidate = _add_months(candidate, 1)
        return candidate
    if freq is RecurrenceFreq.QUARTERLY:
        candidate = anchor
        while candidate < start:
            candidate = _add_months(candidate, 3)
        return candidate
    if freq is RecurrenceFreq.WEEKLY:
        candidate = anchor
        while candidate < start:
            candidate = candidate + timedelta(weeks=1)
        return candidate
    if freq is RecurrenceFreq.DAILY:
        return start
    raise ValueError(f"Unsupported frequency: {freq}")


def _add_months(d: date, months: int) -> date:
    """Add ``months`` to ``d``, clamping the day to the target month's length."""
    year = d.year + (d.month - 1 + months) // 12
    month = (d.month - 1 + months) % 12 + 1
    day = min(d.day, _stdlib_calendar.monthrange(year, month)[1])
    return date(year, month, day)


def compute_due_date(
    spec: DeadlineSpec,
    trigger: date,
    calendar: BusinessCalendar,
) -> date:
    """Compute the concrete due date for one obligation instance.

    Args:
        spec: The deadline specification from the obligation.
        trigger: The date the triggering event occurred (for relative
            and on-demand kinds). Ignored for pure absolute one-off
            deadlines.
        calendar: The jurisdiction-aware business-day calendar used to
            apply offsets in :attr:`DayBasis.BUSINESS` mode.

    Returns:
        The concrete due date.

    Raises:
        ValueError: If ``spec`` is internally inconsistent (e.g. relative
            kind with no ``offset_days``).

    Example:
        >>> compute_due_date(spec, date(2026, 6, 14), cal)
        datetime.date(2026, 7, 14)

    """
    if spec.kind in (DeadlineKind.RELATIVE, DeadlineKind.ON_DEMAND):
        if spec.offset_days is None:
            raise ValueError(f"{spec.kind} deadline requires offset_days")
        if spec.day_basis is DayBasis.BUSINESS:
            return calendar.add_business_days(trigger, spec.offset_days)
        return trigger + timedelta(days=spec.offset_days)

    if spec.kind is DeadlineKind.ABSOLUTE:
        if spec.absolute_date is not None:
            return spec.absolute_date
        if spec.month is not None and spec.day is not None:
            return _annual_date(trigger.year, spec.month, spec.day)
        raise ValueError("ABSOLUTE deadline needs absolute_date or month+day")

    raise ValueError(
        f"compute_due_date does not handle kind={spec.kind}; "
        "for RECURRING deadlines, expand the schedule first."
    )


def expand_recurring(
    spec: DeadlineSpec,
    start: date,
    end: date,
) -> list[date]:
    """Expand a ``RECURRING`` deadline spec into concrete due dates.

    Args:
        spec: A deadline spec whose ``kind`` is ``RECURRING``.
        start: Inclusive horizon start.
        end: Inclusive horizon end.

    Returns:
        Sorted list of due dates within the horizon.

    Raises:
        ValueError: If ``spec.kind`` is not ``RECURRING``.

    """
    if spec.kind is not DeadlineKind.RECURRING:
        raise ValueError("expand_recurring requires DeadlineKind.RECURRING")
    if spec.recurrence is None:
        raise ValueError("RECURRING deadline requires recurrence frequency")

    if spec.month is not None and spec.day is not None:
        anchor = _annual_date(start.year, spec.month, spec.day)
    elif spec.absolute_date is not None:
        anchor = spec.absolute_date
    else:
        anchor = start

    rule = RecurrenceRule(freq=spec.recurrence, anchor=anchor)
    return rule.occurrences(start, end)


def _annual_date(year: int, month: int, day: int) -> date:
    """Build a date in ``year``, clamping Feb-29 to Feb-28 in common years."""
    max_day = _stdlib_calendar.monthrange(year, month)[1]
    return date(year, month, min(day, max_day))
