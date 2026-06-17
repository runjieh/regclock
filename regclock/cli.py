"""Command-line interface for regclock.

Subcommands:

* ``regclock schedule`` — expand a YAML obligation file into a
  concrete due-date schedule for a horizon.
* ``regclock status`` — replay an event log and print the lifecycle
  state of every obligation as of a reference date.
* ``regclock pack`` — assemble a regulator-ready evidence pack for a
  reporting period.

The CLI keeps all heavy logic inside the library; this file is a thin
shell around it so that the package is usable from both Python and a
terminal.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

import click
import yaml

from regclock import i18n
from regclock.emit.ics import to_ics
from regclock.emit.report import render_report
from regclock.evidence.pack import build_pack
from regclock.lifecycle.events import Event, EventLog
from regclock.lifecycle.schedule import build_schedule
from regclock.lifecycle.state_machine import resolve_state
from regclock.model.calendar import BusinessCalendar
from regclock.model.obligation import Obligation
from regclock.schemas.types import EventKind


def _default_lang_from_env() -> str:
    """Resolve the default CLI language from environment variables.

    Honours ``REGCLOCK_LANG`` first (explicit override), then ``LANG``
    (POSIX), falling back to English. Only the language part of a POSIX
    locale (e.g. ``"es_ES.UTF-8"`` → ``"es"``) is used.
    """
    raw = os.environ.get("REGCLOCK_LANG") or os.environ.get("LANG") or "en"
    return raw.split(".", 1)[0].split("_", 1)[0].lower() or "en"


@click.group()
@click.option(
    "--lang",
    default=None,
    help="Display language for human-readable output. "
    "Defaults to REGCLOCK_LANG, then LANG, then 'en'.",
)
@click.version_option(package_name="regclock")
def cli(lang: str | None) -> None:
    """A calendar-correct runtime for regulatory obligation deadlines."""
    i18n.set_default_language(lang or _default_lang_from_env())


@cli.command("schedule")
@click.argument("obligations_path", type=click.Path(exists=True, path_type=Path))
@click.option("--from", "horizon_start", required=True, type=click.DateTime(["%Y-%m-%d"]))
@click.option("--to", "horizon_end", required=True, type=click.DateTime(["%Y-%m-%d"]))
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "markdown", "ics"]),
    default="markdown",
)
def schedule_cmd(
    obligations_path: Path,
    horizon_start: Any,
    horizon_end: Any,
    fmt: str,
) -> None:
    """Expand obligations into a concrete due-date schedule."""
    obligations = _load_obligations(obligations_path)
    calendars = _calendars_for(obligations)
    schedule = build_schedule(
        obligations,
        horizon_start.date(),
        horizon_end.date(),
        calendars,
    )
    if fmt == "ics":
        click.echo(to_ics(schedule), nl=False)
        return
    if fmt == "json":
        rows = [
            {
                "obligation_id": s.obligation_id,
                "title": s.title,
                "jurisdiction": s.jurisdiction,
                "due_on": s.due_on.isoformat(),
                "kind": s.kind.value,
                "trigger_on": s.trigger_on.isoformat() if s.trigger_on else None,
            }
            for s in schedule
        ]
        click.echo(json.dumps(rows, indent=2))
        return
    lines = ["| Obligation | Title | Due | Kind |", "|---|---|---|---|"]
    for s in schedule:
        lines.append(f"| {s.obligation_id} | {s.title} | {s.due_on} | {s.kind.value} |")
    click.echo("\n".join(lines))


@cli.command("status")
@click.argument("obligations_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--events",
    "events_path",
    type=click.Path(exists=True, path_type=Path),
    required=True,
)
@click.option("--asof", "as_of", required=True, type=click.DateTime(["%Y-%m-%d"]))
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["markdown", "html", "json"]),
    default="markdown",
)
def status_cmd(obligations_path: Path, events_path: Path, as_of: Any, fmt: str) -> None:
    """Replay the event log and print lifecycle states as of a date."""
    obligations = _load_obligations(obligations_path)
    events = _load_events(events_path)
    calendars = _calendars_for(obligations)
    schedule = build_schedule(
        obligations,
        as_of.date().replace(month=1, day=1),
        as_of.date().replace(month=12, day=31),
        calendars,
        events=events,
    )
    obligations_by_id = {o.id: o for o in obligations}
    statuses = []
    for inst in schedule:
        obligation = obligations_by_id[inst.obligation_id]
        calendar = calendars[obligation.jurisdiction]
        statuses.append(resolve_state(obligation, inst, events, calendar, as_of.date()))
    click.echo(render_report(statuses, fmt=fmt))  # type: ignore[arg-type]


@cli.command("pack")
@click.argument("obligations_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--events",
    "events_path",
    type=click.Path(exists=True, path_type=Path),
    required=True,
)
@click.option("--period", required=True, help="e.g. 2026Q1 or 2026-01-01:2026-03-31")
@click.option("--out", "out_path", type=click.Path(path_type=Path), default=None)
def pack_cmd(obligations_path: Path, events_path: Path, period: str, out_path: Path | None) -> None:
    """Assemble an evidence pack for a reporting period."""
    start, end = _parse_period(period)
    obligations = _load_obligations(obligations_path)
    events = _load_events(events_path)
    calendars = _calendars_for(obligations)
    schedule = build_schedule(obligations, start, end, calendars, events=events)
    pack = build_pack(
        period_start=start,
        period_end=end,
        obligations=obligations,
        schedule=schedule,
        events=events,
        calendars=calendars,
    )
    payload = pack.model_dump(mode="json")
    text = json.dumps(payload, indent=2, default=str)
    if out_path is None:
        click.echo(text)
    else:
        out_path.write_text(text, encoding="utf-8")
        click.echo(f"wrote {out_path} (digest={pack.digest[:12]}…)")


def _load_obligations(path: Path) -> list[Obligation]:
    """Load a list of obligations from YAML or JSON."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "obligations" in raw:
        raw = raw["obligations"]
    if not isinstance(raw, list):
        click.echo("Expected a list of obligations or {obligations: [...]}", err=True)
        sys.exit(2)
    return [Obligation.model_validate(item) for item in raw]


def _load_events(path: Path) -> EventLog:
    """Load an event log from JSONL."""
    events: list[Event] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if "kind" in payload and isinstance(payload["kind"], str):
            payload["kind"] = EventKind(payload["kind"])
        events.append(Event.model_validate(payload))
    return EventLog(events=events)


def _calendars_for(obligations: list[Obligation]) -> dict[str, BusinessCalendar]:
    """Build a default :class:`BusinessCalendar` per jurisdiction seen."""
    jurisdictions = {o.jurisdiction for o in obligations}
    return {j: BusinessCalendar(jurisdiction=j) for j in jurisdictions}


def _parse_period(period: str) -> tuple[date, date]:
    """Parse a ``YYYYQn`` or ``start:end`` period string."""
    if ":" in period:
        a, b = period.split(":", 1)
        return date.fromisoformat(a), date.fromisoformat(b)
    if "Q" in period.upper():
        year_str, q_str = period.upper().split("Q", 1)
        year = int(year_str)
        q = int(q_str)
        month_start = {1: 1, 2: 4, 3: 7, 4: 10}[q]
        from calendar import monthrange

        month_end = month_start + 2
        return date(year, month_start, 1), date(year, month_end, monthrange(year, month_end)[1])
    raise click.BadParameter(f"Unrecognised period: {period}")


if __name__ == "__main__":  # pragma: no cover
    cli()
