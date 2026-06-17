# regclock — Calendar-correct deadlines for regulatory obligations

![status](https://img.shields.io/badge/status-alpha-orange)
![python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)
![license](https://img.shields.io/badge/license-Apache--2.0-green)

A lightweight Python runtime that models regulatory **obligations** as plain
data and computes their **deadline lifecycle** — due dates, reminders, grace
periods, and satisfaction state — as a deterministic, auditable state machine.

> **Alpha (0.0.1).** 

```bash
pip install regclock
```

See [Install](#install) for optional extras (calendars, LegalRuleML, deontic, LLM).

## 60-second quickstart

```python
from datetime import date
from regclock import (
    Bearer, BusinessCalendar, DayBasis, DeadlineKind, DeadlineSpec,
    Event, EventKind, EventLog, EvidenceRequirement, Obligation,
    SourceCitation, build_schedule, resolve_state,
)

obl = Obligation(
    id="gdpr.art33", title="Breach notification",
    bearer=Bearer(id="acme", name="ACME S.A."),
    required_action="Notify SA.", trigger="Breach awareness.",
    deadline=DeadlineSpec(kind=DeadlineKind.RELATIVE, offset_days=3, day_basis=DayBasis.CALENDAR),
    evidence=EvidenceRequirement(kinds=["filing_receipt"]),
    source=SourceCitation(title="GDPR", article="Art. 33(1)"), jurisdiction="ES",
)
events = EventLog(events=[Event(obligation_id=obl.id, kind=EventKind.TRIGGER, occurred_on=date(2026, 6, 10))])
cals = {"ES": BusinessCalendar(jurisdiction="ES")}
schedule = build_schedule([obl], date(2026, 1, 1), date(2026, 12, 31), cals, events=events)
print(resolve_state(obl, schedule[0], events, cals["ES"], date(2026, 6, 11)).state.value)
# upcoming
```

For runnable end-to-end demos (Apple SEC 10-K, GDPR breach notification, the
CLI on real fixture data), see [`examples/`](examples/).

---

## What this package IS (and is NOT)

**IT IS:** a pip-installable, developer-friendly engine that represents a
regulatory obligation as plain data (a small Pydantic schema), and computes
its **deadline lifecycle** over real calendar time as a deterministic,
auditable state machine. It emits the artifacts a small obligated entity
actually needs: a due-date schedule, reminders, an evidence/satisfaction
record, and a filing/document stub.

**IT IS NOT, and must NOT reimplement:**

- a **tool that decides whether a regulation applies to you.**
  Applicability is an *input* — supplied by a compliance team, a curated
  obligation list, or an upstream reasoner via the `applicability`
  callback — not an output. When applicability cannot be decided from
  the inputs, the engine returns `UNDETERMINED`; it never guesses.
- a defeasible/deontic **LOGIC theorem prover** (do NOT rebuild Regorous /
  FCL / PCL / SPINdle). Applicability of an obligation is a simple
  user-supplied predicate (a callable or boolean expression), deliberately
  NOT a logic solver. See `regclock.io.deontic` for the adapter Protocol
  if you want to plug a real reasoner in upstream.
- a **security-controls framework** (do NOT duplicate OSCAL / Trestle /
  compliancelib).
- a **sanctions/entity screening** engine (that is OpenSanctions' job).
- a **rules-as-code calculation** engine for tax/benefit amounts
  (OpenFisca / Catala).

---

## Prior art

- **LegalRuleML (OASIS)** — source of the obligation vocabulary this model
  borrows from. `regclock` does not reimplement LegalRuleML's XML; it ships
  a small importer in `regclock.io.legalruleml` for interoperability.
- **Regorous / Formal Contract Language (FCL) / PCL / SPINdle** — deontic
  compliance reasoning. **Out of scope** here. If you need defeasible
  applicability, plug a real reasoner *upstream* of this engine and feed
  its verdict into the obligation's `applicability` predicate.
- **OSCAL / Trestle / compliancelib** — security-controls compliance-as-code.
  A **different layer** of the stack. Use them for controls; use
  `regclock` for the obligation/deadline runtime.
- **OpenFisca / Catala** — rules-as-code calculation of tax/benefit
  amounts. Out of scope: `regclock` does not compute amounts.

`regclock`'s contribution is the lightweight, calendar-correct,
reproducible **deadline-lifecycle runtime**, not the logic and not the
ontology.

### Where regclock sits in the compliance stack

```
   upstream                   regclock                  downstream
 ┌────────────────────┐    ┌────────────────────┐    ┌────────────────────┐
 │ WHICH obligations  │ →  │ WHEN each is due,  │ →  │ HOW they are met:  │
 │ apply:             │    │ WHETHER it has     │    │ controls (OSCAL),  │
 │  - compliance team │    │ been satisfied,    │    │ amounts (OpenFisca │
 │  - curated list    │    │ WHAT evidence is   │    │ / Catala), filings │
 │  - SPINdle/clingo  │    │ on record.         │    │ and submissions.   │
 │    via applicability│   │                    │    │                    │
 └────────────────────┘    └────────────────────┘    └────────────────────┘
```

`regclock.io.deontic` exposes a small `DeonticReasoner` Protocol so an
external reasoner (SPINdle via subprocess, clingo via Python bindings,
or your own HTTP service) can be wrapped into the `applicability`
callable without touching the core.

---

## Install

```bash
pip install regclock                       # core: pydantic, dateutil, jinja2, click
pip install "regclock[calendars]"          # workalendar + holidays
pip install "regclock[legalruleml]"        # lxml for the LRML importer
pip install "regclock[deontic]"            # clingo (ASP) for the optional reasoner adapter
pip install "regclock[llm]"                # openai + anthropic clause drafter
```

For local development:

```bash
git clone https://github.com/runjieh/regclock
cd regclock
pip install -e ".[dev]"
```

Python 3.10+.

---

## Runnable end-to-end example

Two obligations: one **relative** ("within N business days of the
trigger"), one **absolute recurring** ("by 31 March each year"), plus a
third whose applicability is `undetermined` because we deliberately do not
provide enough context. We compute the 2026 schedule, replay an event log,
and print the lifecycle state of each.

```python
from datetime import date

from regclock import (
    Bearer, BusinessCalendar, DayBasis, DeadlineKind, DeadlineSpec, Event,
    EventKind, EventLog, EvidenceRequirement, Obligation, Penalty,
    SourceCitation, build_schedule, resolve_state,
)

# --- 1. Define obligations ---------------------------------------------------

breach_notif = Obligation(
    id="gdpr.art33.breach_notification",
    title="Notify supervisory authority of personal-data breach",
    bearer=Bearer(id="acme", name="ACME S.A.", role="data_controller"),
    required_action="File a personal-data-breach notification with the SA.",
    trigger="Awareness of a personal-data breach.",
    deadline=DeadlineSpec(
        kind=DeadlineKind.RELATIVE,
        offset_days=3,
        day_basis=DayBasis.BUSINESS,
        grace_days=0,
    ),
    evidence=EvidenceRequirement(kinds=["filing_receipt"]),
    penalty=Penalty(description="Administrative fines up to 2% of global turnover."),
    source=SourceCitation(title="GDPR", article="Art. 33(1)"),
    jurisdiction="ES",
)

annual_filing = Obligation(
    id="acme.tax.annual_return",
    title="Annual corporate tax return",
    bearer=Bearer(id="acme", name="ACME S.A."),
    required_action="File the annual corporate tax return.",
    trigger="End of the fiscal year.",
    deadline=DeadlineSpec(kind=DeadlineKind.ABSOLUTE, month=3, day=31),
    evidence=EvidenceRequirement(kinds=["filing_receipt", "signed_attestation"]),
    source=SourceCitation(title="Spanish CIT regulation", article="Form 200"),
    jurisdiction="ES",
)

# Deliberately undetermined: applicability depends on data we do not pass in.
def _needs_dpia(ctx):
    return None  # we honestly do not know

dpia = Obligation(
    id="gdpr.art35.dpia",
    title="Carry out a Data Protection Impact Assessment",
    bearer=Bearer(id="acme", name="ACME S.A."),
    required_action="Conduct and document a DPIA before processing.",
    trigger="Planned high-risk processing.",
    applicability=_needs_dpia,
    deadline=DeadlineSpec(
        kind=DeadlineKind.RELATIVE, offset_days=30, day_basis=DayBasis.CALENDAR
    ),
    evidence=EvidenceRequirement(kinds=["dpia_report"]),
    source=SourceCitation(title="GDPR", article="Art. 35"),
    jurisdiction="ES",
)

# --- 2. Calendars and event log ---------------------------------------------

calendars = {"ES": BusinessCalendar(jurisdiction="ES")}
events = EventLog(events=[
    Event(
        obligation_id="gdpr.art33.breach_notification",
        kind=EventKind.TRIGGER,
        occurred_on=date(2026, 6, 10),
    ),
    Event(
        obligation_id="gdpr.art33.breach_notification",
        kind=EventKind.EVIDENCE,
        occurred_on=date(2026, 6, 12),
        payload={"evidence_kind": "filing_receipt", "ref": "SA-2026-1234"},
    ),
    # For the DPIA we deliberately log nothing.
])

# --- 3. Build the 2026 schedule ---------------------------------------------

schedule = build_schedule(
    [breach_notif, annual_filing, dpia],
    date(2026, 1, 1), date(2026, 12, 31),
    calendars=calendars,
    events=events,
)

# --- 4. Resolve lifecycle states as of 14 June 2026 -------------------------

obligations_by_id = {o.id: o for o in [breach_notif, annual_filing, dpia]}
for inst in schedule:
    o = obligations_by_id[inst.obligation_id]
    status = resolve_state(o, inst, events, calendars["ES"], date(2026, 6, 14))
    print(f"{o.id:42s} due={inst.due_on}  state={status.state.value}")
```

Expected output (assuming default holiday calendar for `ES`):

```
gdpr.art33.breach_notification             due=2026-06-15  state=satisfied
acme.tax.annual_return                     due=2026-03-31  state=overdue
```

The DPIA obligation has `applicability` returning `None`, so it never
materialises as a scheduled instance with a known trigger — and any time
the engine *is* asked to resolve it, it returns `UNDETERMINED` rather than
guessing. That is the honest answer.

---

## CLI

```bash
# Expand to a schedule
regclock schedule obligations.yaml --from 2026-01-01 --to 2026-12-31

# Replay an event log
regclock status obligations.yaml --events log.jsonl --asof 2026-06-14

# Build a regulator-ready evidence pack for Q1
regclock pack obligations.yaml --events log.jsonl --period 2026Q1 --out pack.json
```

---

## Internationalisation

Display strings (report column headers, filing stubs, reminder bodies)
are translatable. Machine-readable artefacts — JSON output,
`Event.kind`, `State` enum values, evidence-pack digests — stay in
English so serialised data is locale-independent and diffable.

```python
from regclock import i18n

i18n.register_language("es", labels={
    "state.satisfied": "Cumplida",
    "state.overdue": "Vencida",
    "ui.bearer": "Sujeto obligado",
    "ui.due_on": "Vence el",
    "report.col_obligation": "Obligación",
    # ...remaining keys fall back to English at lookup time
})
i18n.set_default_language("es")
```

Optionally point to a directory of translated Jinja templates:

```python
i18n.register_language(
    "zh",
    labels={...},
    templates_dir="/path/to/my/zh_templates",   # falls back to en/ per file
)
```

The CLI honours `--lang`, then `REGCLOCK_LANG`, then `LANG`, then `en`.

## Plugging in a deontic reasoner (optional)

For obligations whose applicability really does require defeasible /
deontic reasoning (e.g. complex GDPR carve-outs), wrap an external
reasoner in the `DeonticReasoner` Protocol and feed its verdict into
`Obligation.applicability`:

```python
from regclock.io.deontic import DeonticReasoner, as_applicability

class SPINdleWrapper:
    def evaluate(self, rule_id: str, context: dict) -> bool | None:
        # subprocess into SPINdle, parse the verdict, return True/False/None
        ...

obligation = Obligation(
    id="gdpr.art35.dpia",
    applicability=as_applicability(SPINdleWrapper(), rule_id="gdpr.art35"),
    ...
)
```

`regclock` ships **no** reasoner of its own — this is purely an
interoperability seam.

---

## Custom fiscal years (optional)

regclock's default deadline model is **calendar-year**: an `ABSOLUTE`
deadline with `month=3, day=31` always means 31 March in the Gregorian
calendar. This is correct for the clear majority of small-entity
compliance work.

Entities whose fiscal year does **not** align with the Gregorian
calendar — US-listed firms, retailers, large multinationals — can opt
in to entity-specific fiscal-year semantics via
`regclock.utils.fiscal`. The core engine never reaches for this module
and nothing in regclock behaves differently unless you import from it
explicitly.

The pattern is: build a fiscal calendar, materialise its year- or
quarter-ends as `Event(kind=TRIGGER)` records, and pair them with a
`RELATIVE` obligation.

```python
from datetime import date

from regclock import (
    Bearer, DeadlineKind, DeadlineSpec, DayBasis, EventLog,
    EvidenceRequirement, Obligation, SourceCitation,
)
from regclock.utils.fiscal import (
    LastWeekdayFiscalCalendar, fiscal_trigger_events,
)

# Apple's fiscal year ends on the last Saturday of September.
aapl_cal = LastWeekdayFiscalCalendar(month=9, weekday=5)  # 5 = Saturday

ten_k = Obligation(
    id="aapl.sec.10k",
    title="Annual report on Form 10-K",
    bearer=Bearer(id="aapl", name="Apple Inc."),
    required_action="File Form 10-K with the SEC.",
    trigger="End of fiscal year.",
    deadline=DeadlineSpec(
        kind=DeadlineKind.RELATIVE, offset_days=75, day_basis=DayBasis.CALENDAR,
    ),
    evidence=EvidenceRequirement(kinds=["edgar_acceptance"]),
    source=SourceCitation(title="Exchange Act", article="§13(a)"),
    jurisdiction="US",
)

events = EventLog(events=fiscal_trigger_events(
    obligation_id="aapl.sec.10k",
    calendar=aapl_cal,
    fiscal_years=range(2024, 2027),
))
# Apple FY2024 (FYE 2024-09-28) → 10-K due 2024-12-12
# Apple FY2025 (FYE 2025-09-27) → 10-K due 2025-12-11
```

Two ready-made calendars are shipped:

- **`FixedDateFiscalCalendar(start_month, start_day)`** for stable boundary
  dates: Microsoft `(7, 1)`, Japan/India corporates `(4, 1)`, UK
  individuals `(4, 6)`, US federal `(10, 1)`.
- **`LastWeekdayFiscalCalendar(month, weekday)`** for 52/53-week year-ends:
  Apple `(9, 5)`, Walmart `(1, 4)`, Target `(1, 5)`.

### Caveat on 52/53-week calendars

The shipped `LastWeekdayFiscalCalendar(month=9, weekday=5)`
reproduces Apple's published fiscal-year-end dates verbatim for
FY2017–FY2024, matching the rule stated in Apple's 10-K filings
("the 52- or 53-week period that ends on the last Saturday of
September"). The same goes for Walmart, Target, and other retailers
whose published rule is literally "last \<weekday\> of \<month\>".

What the shipped class does **not** cover is the small set of
entities whose published rule is something else — for example
"\<weekday\> *closest to* a fixed date" (some 4-4-5 anchors), or a
cycle that shifts deliberately every few years. For those, implement
the `FiscalCalendar` Protocol directly. Any object with
`fiscal_year_end(int) -> date` and
`fiscal_quarter_ends(int) -> list[date]` will be accepted:

```python
from datetime import date, timedelta

class SaturdayClosestToJan31:
    """52/53-week rule: Saturday closest to 31 January (illustrative)."""

    def fiscal_year_end(self, fiscal_year: int) -> date:
        anchor = date(fiscal_year, 1, 31)
        back = (anchor.weekday() - 5) % 7        # days back to Saturday
        fwd = (5 - anchor.weekday()) % 7         # days forward to Saturday
        return anchor - timedelta(days=back) if back <= fwd else anchor + timedelta(days=fwd)

    def fiscal_quarter_ends(self, fiscal_year: int) -> list[date]:
        prior = self.fiscal_year_end(fiscal_year - 1)
        this = self.fiscal_year_end(fiscal_year)
        return [prior + timedelta(weeks=w) for w in (13, 26, 39)] + [this]
```

### Stub: NRF 4-5-4 retail calendar

US retailers (Walmart, Target, Macy's, Home Depot) follow the
[NRF 4-5-4 calendar](https://nrf.com/resources/4-5-4-calendar): each
fiscal quarter is 13 weeks divided into months of 4, 5, and 4 weeks.
Every 5–6 years a 53rd week is appended to Q4. We do **not** ship a
class for this — different retailers anchor it differently and the
NRF publishes the canonical year-ends as a table. The recommended
pattern is to load that table as a list of explicit dates:

```python
from regclock.utils.fiscal import FiscalCalendar  # Protocol only

class NRF454Calendar:
    """Stub: looks up published NRF year-ends from a static table."""

    # Source: NRF 4-5-4 calendar (published years through FY2030).
    _YEAR_ENDS = {
        2024: date(2025, 2, 1),
        2025: date(2026, 1, 31),
        2026: date(2027, 1, 30),
        # ... fill from nrf.com/resources/4-5-4-calendar
    }

    def fiscal_year_end(self, fiscal_year: int) -> date:
        return self._YEAR_ENDS[fiscal_year]

    def fiscal_quarter_ends(self, fiscal_year: int) -> list[date]:
        prior = self._YEAR_ENDS[fiscal_year - 1]
        this = self._YEAR_ENDS[fiscal_year]
        return [prior + timedelta(weeks=w) for w in (13, 26, 39)] + [this]

assert isinstance(NRF454Calendar(), FiscalCalendar)  # Protocol check
```

This is genuinely 5 minutes of work because the hard part — the NRF
year-ends — is already published as a table. regclock provides the
seam; the entity's finance team owns the table.

## Project layout

```
regclock/
  model/         # Obligation data model, recurrence, calendars, amendments
  lifecycle/     # State machine, schedule expansion, event log
  evidence/      # Hashable evidence records and evidence packs
  emit/          # Filing stubs, ICS exporter, status reports
  io/            # LegalRuleML importer + DeonticReasoner adapter Protocol
  schemas/       # Shared types and enumerations
  utils/         # Optional LLM clause-to-draft adapter
  templates/
    en/          # Built-in English Jinja templates
  i18n.py        # Display-string registry; pluggable language packs
  cli.py         # `regclock` CLI (Click)
```

---

## License

Apache-2.0.
