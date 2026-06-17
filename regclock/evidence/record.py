"""Bind a satisfying action to an obligation in a reproducible way.

The hash of an :class:`EvidenceRecord` is deterministic over its content;
if the same inputs are presented to :func:`make_record` again, the same
hash comes out. That is what makes evidence packs re-verifiable months
later.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone

from pydantic import BaseModel, Field

from regclock.lifecycle.events import Event
from regclock.model.obligation import Obligation


class EvidenceRecord(BaseModel):
    """A canonical record that an obligation was satisfied.

    Attributes:
        obligation_id: ID of the obligation that was satisfied.
        bearer_id: ID of the bearer who satisfied it.
        action: Free-text description of the action taken.
        evidence_kind: One of the kinds accepted by the obligation's
            :class:`~regclock.model.obligation.EvidenceRequirement`.
        satisfied_on: The legally relevant date of satisfaction.
        recorded_at: When the record itself was built (UTC).
        attachments: Opaque references (URIs, hashes) to supporting
            documents stored outside the engine.
        digest: Hex SHA-256 of the record content. Filled in by
            :func:`make_record`; do not set by hand.

    """

    obligation_id: str
    bearer_id: str
    action: str
    evidence_kind: str
    satisfied_on: date
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    attachments: list[str] = Field(default_factory=list)
    digest: str = ""


def make_record(
    obligation: Obligation,
    evidence_event: Event,
    *,
    action: str | None = None,
    attachments: list[str] | None = None,
) -> EvidenceRecord:
    """Build a hashable evidence record from an evidence event.

    Args:
        obligation: The obligation that was satisfied.
        evidence_event: The :class:`~regclock.lifecycle.events.Event` of
            kind ``EVIDENCE`` that satisfies the obligation.
        action: Optional free-text action description. Defaults to the
            obligation's ``required_action`` field.
        attachments: Optional list of attachment URIs.

    Returns:
        A populated :class:`EvidenceRecord` whose ``digest`` field is the
        hex SHA-256 of its canonical JSON serialisation.

    Raises:
        ValueError: If the evidence event's ``payload`` does not include
            an ``evidence_kind`` that is accepted by the obligation.

    Example:
        >>> rec = make_record(obl, ev)
        >>> rec.digest[:8]
        '4f2a9c01'

    """
    kind = str(evidence_event.payload.get("evidence_kind", ""))
    if kind not in obligation.evidence.kinds:
        raise ValueError(
            f"evidence_kind '{kind}' not accepted by obligation "
            f"{obligation.id}; expected one of {obligation.evidence.kinds}"
        )
    record = EvidenceRecord(
        obligation_id=obligation.id,
        bearer_id=obligation.bearer.id,
        action=action or obligation.required_action,
        evidence_kind=kind,
        satisfied_on=evidence_event.occurred_on,
        attachments=list(attachments or []),
    )
    record.digest = _digest(record)
    return record


def _digest(record: EvidenceRecord) -> str:
    """Return the canonical SHA-256 of an evidence record (excluding the digest)."""
    payload = record.model_dump(mode="json", exclude={"digest"})
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
