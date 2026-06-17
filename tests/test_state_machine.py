from datetime import date

import pytest

from regclock import (
    Bearer,
    BusinessCalendar,
    DayBasis,
    DeadlineKind,
    DeadlineSpec,
    Event,
    EventKind,
    EventLog,
    EvidenceRequirement,
    Obligation,
    SourceCitation,
    State,
    build_schedule,
    resolve_state,
)


def _make_obligation(applicability=None, grace_days=0):
    return Obligation(
        id="test.obl",
        title="Test obligation",
        bearer=Bearer(id="x", name="X"),
        required_action="Do the thing.",
        trigger="Trigger event.",
        applicability=applicability,
        deadline=DeadlineSpec(
            kind=DeadlineKind.RELATIVE,
            offset_days=3,
            day_basis=DayBasis.CALENDAR,
            grace_days=grace_days,
        ),
        evidence=EvidenceRequirement(kinds=["filing_receipt"]),
        source=SourceCitation(title="Test"),
        jurisdiction="ZZ",
    )


def _setup(obligation, events_list=()):
    events = EventLog(events=list(events_list))
    calendars = {"ZZ": BusinessCalendar(jurisdiction="ZZ")}
    schedule = build_schedule(
        [obligation],
        date(2026, 1, 1),
        date(2026, 12, 31),
        calendars=calendars,
        events=events,
    )
    return events, calendars["ZZ"], schedule


@pytest.fixture
def trigger_event():
    return Event(
        obligation_id="test.obl",
        kind=EventKind.TRIGGER,
        occurred_on=date(2026, 6, 10),
    )


def test_upcoming_before_deadline(trigger_event):
    obl = _make_obligation()
    events, cal, schedule = _setup(obl, [trigger_event])
    status = resolve_state(obl, schedule[0], events, cal, date(2026, 6, 11))
    assert status.state is State.UPCOMING
    assert status.days_to_due == 2


def test_due_on_deadline(trigger_event):
    obl = _make_obligation()
    events, cal, schedule = _setup(obl, [trigger_event])
    status = resolve_state(obl, schedule[0], events, cal, date(2026, 6, 13))
    assert status.state is State.DUE
    assert status.days_to_due == 0


def test_overdue_after_grace(trigger_event):
    obl = _make_obligation()
    events, cal, schedule = _setup(obl, [trigger_event])
    status = resolve_state(obl, schedule[0], events, cal, date(2026, 6, 20))
    assert status.state is State.OVERDUE
    assert status.days_to_due == -7


def test_satisfied_by_evidence_in_time(trigger_event):
    obl = _make_obligation()
    evidence = Event(
        obligation_id="test.obl",
        kind=EventKind.EVIDENCE,
        occurred_on=date(2026, 6, 12),
        payload={"evidence_kind": "filing_receipt"},
    )
    events, cal, schedule = _setup(obl, [trigger_event, evidence])
    status = resolve_state(obl, schedule[0], events, cal, date(2026, 6, 20))
    assert status.state is State.SATISFIED
    assert status.evidence == evidence


def test_evidence_after_grace_does_not_satisfy(trigger_event):
    obl = _make_obligation()
    late_evidence = Event(
        obligation_id="test.obl",
        kind=EventKind.EVIDENCE,
        occurred_on=date(2026, 6, 20),
    )
    events, cal, schedule = _setup(obl, [trigger_event, late_evidence])
    status = resolve_state(obl, schedule[0], events, cal, date(2026, 6, 25))
    assert status.state is State.OVERDUE


def test_grace_window_extends_satisfaction(trigger_event):
    obl = _make_obligation(grace_days=5)
    late_evidence = Event(
        obligation_id="test.obl",
        kind=EventKind.EVIDENCE,
        occurred_on=date(2026, 6, 16),  # 3 days after due (within 5-day grace)
    )
    events, cal, schedule = _setup(obl, [trigger_event, late_evidence])
    status = resolve_state(obl, schedule[0], events, cal, date(2026, 6, 25))
    assert status.state is State.SATISFIED


def test_waiver_supersedes_evidence(trigger_event):
    obl = _make_obligation()
    waiver = Event(
        obligation_id="test.obl",
        kind=EventKind.WAIVER,
        occurred_on=date(2026, 6, 11),
    )
    events, cal, schedule = _setup(obl, [trigger_event, waiver])
    status = resolve_state(obl, schedule[0], events, cal, date(2026, 6, 20))
    assert status.state is State.WAIVED
    assert status.waiver == waiver


def test_undetermined_when_applicability_returns_none(trigger_event):
    obl = _make_obligation(applicability=lambda _ctx: None)
    events, cal, schedule = _setup(obl, [trigger_event])
    status = resolve_state(obl, schedule[0], events, cal, date(2026, 6, 11))
    assert status.state is State.UNDETERMINED


def test_undetermined_when_applicability_raises(trigger_event):
    def bad(_ctx):
        raise RuntimeError("oops")
    obl = _make_obligation(applicability=bad)
    events, cal, schedule = _setup(obl, [trigger_event])
    status = resolve_state(obl, schedule[0], events, cal, date(2026, 6, 11))
    assert status.state is State.UNDETERMINED


def test_applicability_false_yields_waived(trigger_event):
    obl = _make_obligation(applicability=lambda _ctx: False)
    events, cal, schedule = _setup(obl, [trigger_event])
    status = resolve_state(obl, schedule[0], events, cal, date(2026, 6, 11))
    assert status.state is State.WAIVED


def test_determinism_same_inputs_same_state(trigger_event):
    obl = _make_obligation()
    events, cal, schedule = _setup(obl, [trigger_event])
    first = resolve_state(obl, schedule[0], events, cal, date(2026, 6, 14))
    second = resolve_state(obl, schedule[0], events, cal, date(2026, 6, 14))
    assert first == second


def test_event_log_fingerprint_is_stable(trigger_event):
    a = EventLog(events=[trigger_event])
    b = EventLog(events=[trigger_event])
    assert a.fingerprint() == b.fingerprint()
