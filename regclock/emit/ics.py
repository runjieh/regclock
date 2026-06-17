"""Export a schedule to iCalendar (RFC 5545).

We hand-roll the ICS output instead of pulling in a third-party
dependency, because the format we emit (VEVENT only, all-day) is small,
stable, and easy to validate.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import date, datetime, timezone

from regclock.lifecycle.schedule import ScheduledInstance

_PRODID = "-//regclock//deadline-runtime//EN"


def to_ics(instances: Iterable[ScheduledInstance], calendar_name: str = "Obligations") -> str:
    """Render a list of scheduled instances as an iCalendar string.

    Args:
        instances: The scheduled instances to export.
        calendar_name: Human-readable name shown by calendar clients.

    Returns:
        An iCalendar VCALENDAR/VEVENT string using all-day events
        (``VALUE=DATE``).

    Example:
        >>> print(to_ics(schedule)[:64])
        BEGIN:VCALENDAR
        VERSION:2.0
        PRODID:-//regclock//deadline-runtime//EN

    """
    now = _utc_now_stamp()
    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{_PRODID}",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{_escape(calendar_name)}",
    ]
    for inst in instances:
        uid = _uid_for(inst)
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{now}",
                f"DTSTART;VALUE=DATE:{_ical_date(inst.due_on)}",
                f"DTEND;VALUE=DATE:{_ical_date(_next_day(inst.due_on))}",
                f"SUMMARY:{_escape(inst.title)}",
                f"DESCRIPTION:{_escape(f'Obligation {inst.obligation_id} ({inst.jurisdiction})')}",
                "TRANSP:TRANSPARENT",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def _ical_date(d: date) -> str:
    """Render a date as ``YYYYMMDD`` per RFC 5545 ``DATE`` value type."""
    return d.strftime("%Y%m%d")


def _next_day(d: date) -> date:
    """Return the day after ``d``; used for the exclusive DTEND of all-day events."""
    from datetime import timedelta

    return d + timedelta(days=1)


def _utc_now_stamp() -> str:
    """Return the current UTC time as an RFC 5545 ``DTSTAMP`` string."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _escape(text: str) -> str:
    """Escape backslashes, commas, semicolons and newlines per RFC 5545."""
    return (
        text.replace("\\", "\\\\")
        .replace(",", "\\,")
        .replace(";", "\\;")
        .replace("\n", "\\n")
    )


def _uid_for(inst: ScheduledInstance) -> str:
    """Build a stable, deterministic UID for one scheduled instance."""
    material = f"{inst.obligation_id}|{inst.due_on.isoformat()}|{inst.kind.value}"
    digest = hashlib.sha1(material.encode("utf-8")).hexdigest()
    return f"{digest}@regclock"
