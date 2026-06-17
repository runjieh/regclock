"""Assemble a regulator-ready evidence/attestation pack for a period."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone

from pydantic import BaseModel, Field

from regclock.evidence.record import EvidenceRecord, make_record
from regclock.lifecycle.events import EventLog
from regclock.lifecycle.schedule import ScheduledInstance
from regclock.lifecycle.state_machine import LifecycleStatus, resolve_state
from regclock.model.calendar import BusinessCalendar
from regclock.model.obligation import Obligation
from regclock.schemas.types import State


class EvidencePack(BaseModel):
    """A snapshot of the obligation portfolio over a reporting period.

    Attributes:
        period_start: Inclusive start of the reporting period.
        period_end: Inclusive end of the reporting period.
        built_at: When the pack was assembled (UTC).
        records: Evidence records for each satisfied obligation.
        unresolved: One :class:`~regclock.lifecycle.state_machine.LifecycleStatus`
            per obligation that did not reach ``SATISFIED``.
        event_log_fingerprint: SHA-256 of the input event log.
        digest: SHA-256 of the pack content (filled by :func:`build_pack`).

    """

    period_start: date
    period_end: date
    built_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    records: list[EvidenceRecord] = Field(default_factory=list)
    unresolved: list[LifecycleStatus] = Field(default_factory=list)
    event_log_fingerprint: str = ""
    digest: str = ""

    model_config = {"arbitrary_types_allowed": True}


def build_pack(
    *,
    period_start: date,
    period_end: date,
    obligations: list[Obligation],
    schedule: list[ScheduledInstance],
    events: EventLog,
    calendars: dict[str, BusinessCalendar],
) -> EvidencePack:
    """Build an :class:`EvidencePack` covering ``[period_start, period_end]``.

    Args:
        period_start: Inclusive start of the reporting period.
        period_end: Inclusive end of the reporting period.
        obligations: Obligation definitions (already amended as of
            ``period_end`` if applicable).
        schedule: Scheduled instances within the period (typically the
            output of :func:`regclock.lifecycle.schedule.build_schedule`).
        events: The full event log.
        calendars: Jurisdiction calendars indexed by ISO code.

    Returns:
        A populated :class:`EvidencePack` whose ``digest`` is a SHA-256
        over its canonical JSON form.

    Example:
        >>> pack = build_pack(period_start=..., period_end=..., ...)
        >>> pack.digest[:8]
        'cb04ff21'

    """
    obligations_by_id = {o.id: o for o in obligations}
    records: list[EvidenceRecord] = []
    unresolved: list[LifecycleStatus] = []

    for inst in schedule:
        if not (period_start <= inst.due_on <= period_end):
            continue
        obligation = obligations_by_id.get(inst.obligation_id)
        if obligation is None:
            continue
        calendar = calendars.get(obligation.jurisdiction) or BusinessCalendar(
            jurisdiction=obligation.jurisdiction
        )
        status = resolve_state(obligation, inst, events, calendar, period_end)
        if status.state is State.SATISFIED and status.evidence is not None:
            records.append(make_record(obligation, status.evidence))
        else:
            unresolved.append(status)

    pack = EvidencePack(
        period_start=period_start,
        period_end=period_end,
        records=records,
        unresolved=unresolved,
        event_log_fingerprint=events.fingerprint(),
    )
    pack.digest = _digest(pack)
    return pack


def _digest(pack: EvidencePack) -> str:
    """Return a SHA-256 over the pack's canonical JSON (excluding ``digest``)."""
    payload = pack.model_dump(mode="json", exclude={"digest"})
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
