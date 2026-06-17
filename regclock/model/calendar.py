"""Jurisdiction-aware business-day and holiday arithmetic.

The core implementation only relies on :mod:`python-dateutil` plus the
standard library. If the optional ``[calendars]`` extra (``holidays`` /
``workalendar``) is installed, the calendar will automatically use it to
skip jurisdiction holidays in business-day arithmetic.

Behavior is deterministic: a calendar with the same jurisdiction and the
same installed providers will always return the same answers, which is
critical for reproducible evidence packs.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta

# Optional providers - imported lazily inside the class so that the core
# package keeps working without them installed.
try:  # pragma: no cover - exercised only when the extra is installed
    import holidays as _holidays_pkg
except ImportError:  # pragma: no cover
    _holidays_pkg = None

try:  # pragma: no cover
    import workalendar.registry as _workalendar_registry
except ImportError:  # pragma: no cover
    _workalendar_registry = None


WEEKEND_DAYS: frozenset[int] = frozenset({5, 6})  # Saturday, Sunday


@dataclass
class BusinessCalendar:
    """A jurisdiction-aware business-day calendar.

    Attributes:
        jurisdiction: ISO 3166-1 alpha-2 code, e.g. ``"ES"``.
        extra_holidays: User-supplied dates that should also be treated as
            holidays (e.g. a regional bank holiday not yet in ``holidays``).
        weekend: Set of ISO weekday numbers (Mon=0, Sun=6) that count as
            weekends. Defaults to Saturday + Sunday.

    Example:
        >>> cal = BusinessCalendar(jurisdiction="ES")
        >>> cal.add_business_days(date(2026, 1, 2), 5)
        datetime.date(2026, 1, 12)

    """

    jurisdiction: str
    extra_holidays: frozenset[date] = field(default_factory=frozenset)
    weekend: frozenset[int] = WEEKEND_DAYS

    def __post_init__(self) -> None:
        """Normalise the jurisdiction code and resolve a holiday provider."""
        self.jurisdiction = self.jurisdiction.upper()
        self._provider = self._resolve_provider()

    def _resolve_provider(self):  # noqa: ANN202 - return type is provider-specific
        """Pick the best available holiday source.

        Returns:
            A callable ``provider(d: date) -> bool`` answering "is this a
            statutory holiday in this jurisdiction?". Falls back to
            ``lambda _: False`` if no provider is installed.

        """
        if _holidays_pkg is not None:
            try:
                hol = _holidays_pkg.country_holidays(self.jurisdiction)
                return lambda d: d in hol
            except (KeyError, NotImplementedError):
                pass
        if _workalendar_registry is not None:
            try:
                cls = _workalendar_registry.registry.get(self.jurisdiction)
                if cls is not None:
                    cal = cls()
                    return lambda d: not cal.is_working_day(d) and d.weekday() not in self.weekend
            except Exception:  # pragma: no cover - registry quirks
                pass
        return lambda _d: False

    def is_holiday(self, d: date) -> bool:
        """Return whether ``d`` is a statutory or user-declared holiday.

        Args:
            d: Date to check.

        Returns:
            ``True`` if the date is a holiday in this jurisdiction.

        Example:
            >>> cal.is_holiday(date(2026, 1, 1))
            True

        """
        if d in self.extra_holidays:
            return True
        return bool(self._provider(d))

    def is_business_day(self, d: date) -> bool:
        """Return whether ``d`` is a business day in this jurisdiction.

        Args:
            d: Date to check.

        Returns:
            ``True`` when ``d`` is neither a weekend day nor a holiday.

        """
        return d.weekday() not in self.weekend and not self.is_holiday(d)

    def add_business_days(self, start: date, n: int) -> date:
        """Add ``n`` business days to ``start``.

        Args:
            start: Reference date.
            n: Non-negative number of business days to add. ``0`` returns
                the next business day on or after ``start``.

        Returns:
            The resulting business day.

        Raises:
            ValueError: If ``n`` is negative (use :meth:`sub_business_days`
                instead).

        Example:
            >>> cal.add_business_days(date(2026, 6, 12), 3)  # Fri + 3
            datetime.date(2026, 6, 17)

        """
        if n < 0:
            raise ValueError("n must be >= 0; use sub_business_days for negative offsets")
        cursor = start
        if n == 0:
            while not self.is_business_day(cursor):
                cursor += timedelta(days=1)
            return cursor
        remaining = n
        while remaining > 0:
            cursor += timedelta(days=1)
            if self.is_business_day(cursor):
                remaining -= 1
        return cursor

    def sub_business_days(self, start: date, n: int) -> date:
        """Subtract ``n`` business days from ``start``.

        Args:
            start: Reference date.
            n: Non-negative number of business days to subtract.

        Returns:
            The resulting business day.

        Raises:
            ValueError: If ``n`` is negative.

        """
        if n < 0:
            raise ValueError("n must be >= 0")
        cursor = start
        remaining = n
        while remaining > 0:
            cursor -= timedelta(days=1)
            if self.is_business_day(cursor):
                remaining -= 1
        return cursor

    def business_days_between(self, start: date, end: date) -> int:
        """Count business days in the half-open interval ``[start, end)``.

        Args:
            start: Inclusive lower bound.
            end: Exclusive upper bound.

        Returns:
            Number of business days; ``0`` when ``end <= start``.

        """
        if end <= start:
            return 0
        count = 0
        cursor = start
        while cursor < end:
            if self.is_business_day(cursor):
                count += 1
            cursor += timedelta(days=1)
        return count

    def iter_business_days(self, start: date, end: date) -> Iterable[date]:
        """Yield every business day in the closed interval ``[start, end]``.

        Args:
            start: Inclusive lower bound.
            end: Inclusive upper bound.

        Yields:
            Business days in ascending order.

        """
        cursor = start
        while cursor <= end:
            if self.is_business_day(cursor):
                yield cursor
            cursor += timedelta(days=1)
