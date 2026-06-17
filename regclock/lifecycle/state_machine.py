"""Deterministic state machine over calendar time.

State transitions are pure functions of:

* the obligation definition (as of ``as_of``),
* the event log,
* the reference "now" date (``as_of``),
* and the jurisdiction calendar (for grace/business-day windows).

There is no hidden state and no implicit clock; given identical inputs,
:func:`resolve_state` always returns the same :class:`LifecycleStatus`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from regclock.lifecycle.events import Event, EventLog
from regclock.lifecycle.schedule import ScheduledInstance
from regclock.model.calendar import BusinessCalendar
from regclock.model.obligation import Obligation
from regclock.schemas.types import DayBasis, EventKind, State


@dataclass(frozen=True)
class LifecycleStatus:
    """The computed lifecycle state of one scheduled obligation instance.

    Attributes:
        instance: The scheduled instance this status refers to.
        state: The computed state on ``as_of``.
        as_of: The reference date used to compute the state.
        days_to_due: Negative when overdue, zero on the due day,
            positive when upcoming.
        evidence: The satisfying evidence event, if any.
        waiver: The waiver event, if any.

    """

    instance: ScheduledInstance
    state: State
    as_of: date
    days_to_due: int
    evidence: Event | None
    waiver: Event | None


def resolve_state(
    obligation: Obligation,
    instance: ScheduledInstance,
    events: EventLog,
    calendar: BusinessCalendar,
    as_of: date,
) -> LifecycleStatus:
    """Compute the lifecycle state of one scheduled instance on ``as_of``.

    Args:
        obligation: The obligation as it stood on ``as_of`` (the caller
            is responsible for applying amendments beforehand).
        instance: The scheduled instance.
        events: The full event log; only events for this obligation are
            consulted.
        calendar: Jurisdiction calendar, used for the grace window when
            the deadline counts in business days.
        as_of: The reference date.

    Returns:
        A :class:`LifecycleStatus` describing the state.

    Example:
        >>> resolve_state(obl, inst, log, cal, date(2026, 6, 14))
        LifecycleStatus(state=State.UPCOMING, days_to_due=17, ...)

    """
    if obligation.applicability is not None:
        verdict = _safe_applicability(obligation, instance, events, as_of)
        if verdict is None:
            return _status(instance, State.UNDETERMINED, as_of, None, None)
        if verdict is False:
            return _status(instance, State.WAIVED, as_of, None, None)

    obligation_events = events.for_obligation(obligation.id)
    waiver = _first_event(obligation_events, EventKind.WAIVER)
    if waiver is not None and waiver.occurred_on <= as_of:
        return _status(instance, State.WAIVED, as_of, None, waiver)

    evidence = _satisfying_evidence(obligation, obligation_events, instance, calendar)
    if evidence is not None and evidence.occurred_on <= as_of:
        return _status(instance, State.SATISFIED, as_of, evidence, None)

    if as_of < instance.due_on:
        window = obligation.deadline.due_window_days
        if (instance.due_on - as_of).days <= window:
            return _status(instance, State.UPCOMING, as_of, None, None)
        return _status(instance, State.PENDING, as_of, None, None)

    if as_of == instance.due_on:
        return _status(instance, State.DUE, as_of, None, None)

    grace_end = _grace_end(obligation, instance, calendar)
    if as_of <= grace_end:
        return _status(instance, State.DUE, as_of, None, None)
    return _status(instance, State.OVERDUE, as_of, None, None)


def _status(
    instance: ScheduledInstance,
    state: State,
    as_of: date,
    evidence: Event | None,
    waiver: Event | None,
) -> LifecycleStatus:
    """Bundle a :class:`LifecycleStatus` with a computed ``days_to_due``."""
    return LifecycleStatus(
        instance=instance,
        state=state,
        as_of=as_of,
        days_to_due=(instance.due_on - as_of).days,
        evidence=evidence,
        waiver=waiver,
    )


def _safe_applicability(
    obligation: Obligation,
    instance: ScheduledInstance,
    events: EventLog,
    as_of: date,
) -> bool | None:
    """Invoke the optional applicability predicate without leaking exceptions.

    Returns:
        ``True``, ``False`` or ``None``. Any exception raised by the
        user predicate is interpreted as ``None`` (undetermined): the
        engine refuses to guess.

    """
    if obligation.applicability is None:
        return True
    context: dict[str, object] = {
        "obligation": obligation,
        "instance": instance,
        "events": events,
        "as_of": as_of,
    }
    try:
        return obligation.applicability(context)
    except Exception:
        return None


def _first_event(events: list[Event], kind: EventKind) -> Event | None:
    """Return the earliest event of ``kind`` in ``events``."""
    matches = [e for e in events if e.kind is kind]
    if not matches:
        return None
    return min(matches, key=lambda e: e.occurred_on)


def _satisfying_evidence(
    obligation: Obligation,
    events: list[Event],
    instance: ScheduledInstance,
    calendar: BusinessCalendar,
) -> Event | None:
    """Find the first evidence event that satisfies ``instance``.

    Evidence satisfies an instance when it occurred on or after the
    trigger (if any) and on or before the end of the grace window
    (``due_on`` plus ``grace_days`` in the configured day basis).
    Evidence filed after the grace window ends does not satisfy the
    obligation: the instance is overdue.
    """
    candidates = [e for e in events if e.kind is EventKind.EVIDENCE]
    if not candidates:
        return None
    grace_end = _grace_end(obligation, instance, calendar)
    candidates.sort(key=lambda e: e.occurred_on)
    for ev in candidates:
        if instance.trigger_on and ev.occurred_on < instance.trigger_on:
            continue
        if ev.occurred_on <= grace_end:
            return ev
    return None


def _grace_end(
    obligation: Obligation,
    instance: ScheduledInstance,
    calendar: BusinessCalendar,
) -> date:
    """Return the last date on which a late satisfaction is still in time."""
    grace = obligation.deadline.grace_days
    if grace <= 0:
        return instance.due_on
    if obligation.deadline.day_basis is DayBasis.BUSINESS:
        return calendar.add_business_days(instance.due_on, grace)
    return instance.due_on + timedelta(days=grace)
