"""Apple Inc. -- SEC Form 10-K annual report deadline.

Apple's fiscal year ends on the last Saturday of September. SEC Rule
13a-1 requires a large accelerated filer to file Form 10-K within 60
calendar days of fiscal year-end. This example materialises FY2023-2026
year-ends as TRIGGER events, attaches the actual EDGAR filing dates as
EVIDENCE, and prints the resulting lifecycle state for each year.
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
    SourceCitation,
    build_schedule,
    resolve_state,
)
from regclock.utils.fiscal import LastWeekdayFiscalCalendar, fiscal_trigger_events


def main() -> None:
    aapl_fiscal = LastWeekdayFiscalCalendar(month=9, weekday=5)  # last Saturday of September

    form_10k = Obligation(
        id="aapl.sec.10k",
        title="Annual report on Form 10-K",
        bearer=Bearer(id="aapl", name="Apple Inc.", role="large_accelerated_filer"),
        required_action="File Form 10-K with the SEC via EDGAR.",
        trigger="End of fiscal year.",
        deadline=DeadlineSpec(
            kind=DeadlineKind.RELATIVE,
            offset_days=60,
            day_basis=DayBasis.CALENDAR,
        ),
        evidence=EvidenceRequirement(kinds=["edgar_acceptance"]),
        source=SourceCitation(
            title="Securities Exchange Act of 1934",
            article="Rule 13a-1 / Form 10-K General Instruction A",
            url="https://www.sec.gov/about/forms/form10-k.pdf",
        ),
        jurisdiction="US",
    )

    triggers = fiscal_trigger_events(
        obligation_id="aapl.sec.10k",
        calendar=aapl_fiscal,
        fiscal_years=range(2023, 2027),
    )

    actual_filings = {
        2023: date(2023, 11, 3),
        2024: date(2024, 11, 1),
        2025: date(2025, 10, 31),
    }
    evidence = [
        Event(
            obligation_id="aapl.sec.10k",
            kind=EventKind.EVIDENCE,
            occurred_on=filed_on,
            payload={"evidence_kind": "edgar_acceptance", "fiscal_year": fy},
        )
        for fy, filed_on in actual_filings.items()
    ]
    events = EventLog(events=triggers + evidence)

    calendars = {"US": BusinessCalendar(jurisdiction="US")}
    schedule = build_schedule(
        [form_10k],
        date(2023, 1, 1),
        date(2027, 12, 31),
        calendars=calendars,
        events=events,
    )

    as_of = date(2026, 6, 15)
    print("Apple Inc. -- Form 10-K filing deadlines")
    print("-" * 60)
    print(f"{'Fiscal Year':<12} {'FY-end':<12} {'Filing due':<12} {'State (as of ' + str(as_of) + ')'}")
    for inst in schedule:
        fy_label = f"FY{inst.trigger_on.year}"
        status = resolve_state(form_10k, inst, events, calendars["US"], as_of)
        print(
            f"{fy_label:<12} {str(inst.trigger_on):<12} "
            f"{str(inst.due_on):<12} {status.state.value}"
        )


if __name__ == "__main__":
    main()
