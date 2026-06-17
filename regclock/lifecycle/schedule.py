"""Expand obligations into concrete due-date schedules.

A :class:`ScheduledInstance` is a single "thing the bearer has to do by a
specific date". It is the unit consumed by the state machine, by reminder
emission, and by the iCalendar exporter.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from regclock.lifecycle.events import EventLog
from regclock.model.amendment import AmendmentLog
from regclock.model.calendar import BusinessCalendar
from regclock.model.obligation import Obligation
from regclock.model.recurrence import compute_due_date, expand_recurring
from regclock.schemas.types import DeadlineKind, EventKind


@dataclass(frozen=True)
class ScheduledInstance:
    """One concrete due date derived from an obligation.

    Attributes:
        obligation_id: ID of the source obligation.
        due_on: The computed due date.
        trigger_on: The date of the triggering event, when applicable.
        kind: The deadline kind that produced this instance.
        title: Human-readable title (mirrors the obligation's title).
        jurisdiction: ISO 3166-1 alpha-2 code, for downstream reporting.

    """

    obligation_id: str
    due_on: date
    trigger_on: date | None
    kind: DeadlineKind
    title: str
    jurisdiction: str


def build_schedule(
    obligations: list[Obligation],
    horizon_start: date,
    horizon_end: date,
    calendars: dict[str, BusinessCalendar],
    events: EventLog | None = None,
    amendments: AmendmentLog | None = None,
) -> list[ScheduledInstance]:
    """Materialise the full due-date schedule for a horizon.

    Args:
        obligations: The obligation definitions.
        horizon_start: Inclusive start date of the horizon.
        horizon_end: Inclusive end date of the horizon.
        calendars: Mapping of ISO jurisdiction code to a
            :class:`BusinessCalendar`. Obligations whose jurisdiction is
            missing fall back to a default calendar with no holidays.
        events: Optional event log. Trigger events from this log are used
            to expand ``RELATIVE`` / ``ON_DEMAND`` deadlines.
        amendments: Optional amendment log. If provided, each obligation
            is materialised as of ``horizon_end`` before scheduling.

    Returns:
        A sorted list of :class:`ScheduledInstance` covering every due
        date that lands inside the horizon.

    Example:
        >>> build_schedule(obls, date(2026, 1, 1), date(2026, 12, 31), cals)
        [ScheduledInstance(...), ...]

    """
    instances: list[ScheduledInstance] = []
    triggers_by_obligation: dict[str, list[date]] = {}
    if events is not None:
        for ev in events.sorted_by_occurred():
            if ev.kind is EventKind.TRIGGER:
                triggers_by_obligation.setdefault(ev.obligation_id, []).append(ev.occurred_on)

    for raw in obligations:
        obligation: Obligation | None = raw
        if amendments is not None:
            obligation = amendments.as_of(raw, horizon_end)
        if obligation is None:
            continue

        calendar = calendars.get(obligation.jurisdiction) or BusinessCalendar(
            jurisdiction=obligation.jurisdiction
        )
        spec = obligation.deadline

        if spec.kind in (DeadlineKind.RELATIVE, DeadlineKind.ON_DEMAND):
            triggers = triggers_by_obligation.get(obligation.id, [])
            for trigger in triggers:
                due = compute_due_date(spec, trigger, calendar)
                if horizon_start <= due <= horizon_end:
                    instances.append(
                        ScheduledInstance(
                            obligation_id=obligation.id,
                            due_on=due,
                            trigger_on=trigger,
                            kind=spec.kind,
                            title=obligation.title,
                            jurisdiction=obligation.jurisdiction,
                        )
                    )
        elif spec.kind is DeadlineKind.ABSOLUTE:
            anchor = horizon_start
            due = compute_due_date(spec, anchor, calendar)
            if horizon_start <= due <= horizon_end:
                instances.append(
                    ScheduledInstance(
                        obligation_id=obligation.id,
                        due_on=due,
                        trigger_on=None,
                        kind=spec.kind,
                        title=obligation.title,
                        jurisdiction=obligation.jurisdiction,
                    )
                )
        elif spec.kind is DeadlineKind.RECURRING:
            for due in expand_recurring(spec, horizon_start, horizon_end):
                if obligation.is_in_force(due):
                    instances.append(
                        ScheduledInstance(
                            obligation_id=obligation.id,
                            due_on=due,
                            trigger_on=None,
                            kind=spec.kind,
                            title=obligation.title,
                            jurisdiction=obligation.jurisdiction,
                        )
                    )

    instances.sort(key=lambda i: (i.due_on, i.obligation_id))
    return instances
