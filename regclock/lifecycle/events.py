"""Replayable, auditable event log.

The event log is the engine's source of truth for what *actually
happened*: when a trigger fired, when an action was performed, what
evidence was filed, when a waiver was granted, when the underlying
obligation was amended.

The log is append-only at the API level and is replayed from scratch
every time state is computed. That guarantees that two runs over the
same log produce the same state, which is what makes evidence packs
re-verifiable.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from regclock.schemas.types import EventKind


class Event(BaseModel):
    """A single entry on the replayable event log.

    Attributes:
        obligation_id: The obligation this event relates to. ``"*"`` is
            reserved for cross-cutting events.
        kind: What sort of event this is.
        occurred_on: The legally relevant date (e.g. when the trigger
            fired, when the action was performed).
        recorded_at: When the event was written to the log. Defaults to
            ``occurred_on`` at midnight UTC.
        payload: Free-form structured payload (evidence references,
            actor IDs, document URIs).
        actor: Optional identifier of the responsible party.

    """

    model_config = ConfigDict(frozen=True)

    obligation_id: str
    kind: EventKind
    occurred_on: date
    recorded_at: datetime | None = None
    payload: dict[str, object] = Field(default_factory=dict)
    actor: str | None = None


class EventLog(BaseModel):
    """An ordered collection of :class:`Event` records.

    Attributes:
        events: The events themselves. They are kept in insertion order;
            consumers should not rely on chronological order without
            calling :meth:`sorted_by_occurred`.

    Example:
        >>> log = EventLog(events=[...])
        >>> log.fingerprint()
        'a1b2...'

    """

    events: list[Event] = Field(default_factory=list)

    def append(self, event: Event) -> None:
        """Append a new event to the log.

        Args:
            event: The event to append.

        """
        self.events.append(event)

    def for_obligation(self, obligation_id: str) -> list[Event]:
        """Return all events related to one obligation, in insertion order.

        Args:
            obligation_id: The obligation's ``id``.

        Returns:
            A new list of matching events.

        """
        return [e for e in self.events if e.obligation_id == obligation_id]

    def sorted_by_occurred(self) -> list[Event]:
        """Return all events sorted by ``occurred_on`` ascending.

        Returns:
            A new sorted list. The original log is not mutated.

        """
        return sorted(self.events, key=lambda e: (e.occurred_on, e.kind.value))

    def iter_kind(self, kind: EventKind) -> Iterable[Event]:
        """Yield events of a specific kind.

        Args:
            kind: Which kind of event to yield.

        Yields:
            Matching events.

        """
        for event in self.events:
            if event.kind is kind:
                yield event

    def fingerprint(self) -> str:
        """Return a content-addressable hash of the log.

        The hash is over a deterministic JSON serialisation of the
        events. Two logs with the same payload will produce the same
        fingerprint regardless of insertion-time noise (the
        ``recorded_at`` timestamp is preserved as part of content).

        Returns:
            A hex-encoded SHA-256 digest.

        Example:
            >>> log.fingerprint()
            'fe23...'

        """
        material = json.dumps(
            [e.model_dump(mode="json") for e in self.events],
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()
