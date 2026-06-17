"""GDPR Art. 33 -- personal-data breach notification (72 hours).

GDPR Article 33(1) requires the data controller to notify the
supervisory authority within 72 hours of becoming aware of a personal-
data breach. The example replays a trigger (awareness on 2026-06-10)
and an evidence event (filing receipt on 2026-06-12) for a Spanish
controller, then resolves the lifecycle state on three reference dates.
"""

from datetime import date

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
    Penalty,
    SourceCitation,
    build_schedule,
    resolve_state,
)


def main() -> None:
    breach_notification = Obligation(
        id="gdpr.art33.breach_notification",
        title="Notify supervisory authority of personal-data breach",
        bearer=Bearer(id="acme", name="ACME S.A.", role="data_controller"),
        required_action="File a personal-data-breach notification with the SA.",
        trigger="Awareness of a personal-data breach.",
        deadline=DeadlineSpec(
            kind=DeadlineKind.RELATIVE,
            offset_days=3,
            day_basis=DayBasis.CALENDAR,
        ),
        evidence=EvidenceRequirement(kinds=["filing_receipt"]),
        penalty=Penalty(
            description="Administrative fines up to EUR 10M or 2% of worldwide turnover.",
            kind="administrative",
            statutory_reference="GDPR Art. 83(4)(a)",
        ),
        source=SourceCitation(
            title="GDPR",
            article="Art. 33(1)",
            url="https://eur-lex.europa.eu/eli/reg/2016/679/oj",
        ),
        jurisdiction="ES",
    )

    events = EventLog(events=[
        Event(
            obligation_id="gdpr.art33.breach_notification",
            kind=EventKind.TRIGGER,
            occurred_on=date(2026, 6, 10),
            payload={"breach_id": "INC-2026-0042"},
        ),
        Event(
            obligation_id="gdpr.art33.breach_notification",
            kind=EventKind.EVIDENCE,
            occurred_on=date(2026, 6, 12),
            payload={"evidence_kind": "filing_receipt", "ref": "AEPD-2026-1234"},
        ),
    ])

    calendars = {"ES": BusinessCalendar(jurisdiction="ES")}
    schedule = build_schedule(
        [breach_notification],
        date(2026, 1, 1),
        date(2026, 12, 31),
        calendars=calendars,
        events=events,
    )
    inst = schedule[0]

    print("GDPR Art. 33 -- breach notification (72-hour rule)")
    print("-" * 60)
    print(f"Breach awareness:  {inst.trigger_on}")
    print(f"Filing deadline:   {inst.due_on}")
    print()
    print(f"{'As of':<14} {'Days to due':<14} State")
    print("-" * 60)
    for as_of in [date(2026, 6, 11), date(2026, 6, 12), date(2026, 6, 20)]:
        status = resolve_state(breach_notification, inst, events, calendars["ES"], as_of)
        print(f"{str(as_of):<14} {status.days_to_due:>+5d} days     {status.state.value}")
    print()
    print(f"Event-log fingerprint: {events.fingerprint()[:16]}...")


if __name__ == "__main__":
    main()
