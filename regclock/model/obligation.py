"""The :class:`Obligation` data model and its sub-components.

Concepts here are deliberately borrowed from LegalRuleML (Bearer, Penalty,
temporal validity, source citation) but expressed as a short Pydantic v2
schema instead of XML. We do not encode a full deontic logic; applicability
is a user-supplied boolean predicate or a string expression that the caller
chooses to evaluate.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from regclock.schemas.types import DayBasis, DeadlineKind, RecurrenceFreq


class Bearer(BaseModel):
    """The legal or natural person who bears the obligation.

    Borrowed from LegalRuleML's ``lrml:Bearer``. We keep only the fields a
    small obligated entity actually needs to act on its own duties.

    Attributes:
        id: Stable identifier used for cross-referencing (e.g. internal
            entity code).
        name: Human-readable name.
        role: Optional role label, e.g. ``"data_controller"``,
            ``"vat_taxable_person"``.

    """

    id: str
    name: str
    role: str | None = None


class Penalty(BaseModel):
    """The consequence of violating the obligation.

    This is informational only: the engine does not compute penalties, it
    just carries them through so reports can surface them.

    Attributes:
        description: Free-text description of the penalty.
        kind: Coarse classification used for filtering and reports.
        statutory_reference: Pointer to the statutory text creating the
            penalty (separate from the obligation's own citation when they
            differ).

    """

    description: str
    kind: Literal["administrative", "criminal", "civil", "other"] = "administrative"
    statutory_reference: str | None = None


class SourceCitation(BaseModel):
    """A precise reference to the statutory source of the obligation.

    Attributes:
        title: Short title, e.g. ``"GDPR"``.
        article: Article / section identifier, e.g. ``"Art. 33(1)"``.
        url: Optional canonical URL for the text.
        effective_date: The date from which the cited provision is in force.

    """

    title: str
    article: str | None = None
    url: str | None = None
    effective_date: date | None = None


class EvidenceRequirement(BaseModel):
    """What kind of evidence satisfies the obligation.

    The engine treats evidence as opaque: it only checks that an evidence
    record of one of the accepted ``kinds`` was produced before the
    deadline (or within the grace window).

    Attributes:
        kinds: Accepted evidence types (e.g. ``["filing_receipt",
            "signed_attestation"]``). At least one must be supplied.
        description: Human-readable explanation for the operator.
        retention_days: How long the evidence must be retained after
            satisfaction. Informational only.

    """

    kinds: list[str] = Field(..., min_length=1)
    description: str | None = None
    retention_days: int | None = Field(default=None, ge=0)


class DeadlineSpec(BaseModel):
    """How the deadline of an obligation instance is computed.

    The combination of fields that is valid depends on ``kind``:
      * ``RELATIVE``: ``offset_days`` and ``day_basis`` are required.
      * ``ABSOLUTE``: either ``absolute_date`` or (``month``, ``day``).
      * ``RECURRING``: ``recurrence`` is required, plus offset semantics.
      * ``ON_DEMAND``: ``offset_days`` and ``day_basis`` are required and
        apply once the trigger fires.

    Attributes:
        kind: See :class:`regclock.schemas.types.DeadlineKind`.
        offset_days: For relative / on-demand kinds, number of days after
            the trigger.
        day_basis: Whether ``offset_days`` is counted in business or
            calendar days.
        absolute_date: For one-off absolute deadlines.
        month: Month component for an annually recurring absolute deadline.
        day: Day-of-month component for an annually recurring absolute
            deadline.
        recurrence: Frequency for ``RECURRING`` deadlines.
        grace_days: Additional days after the deadline during which a late
            satisfaction still moves the state to ``SATISFIED`` (not
            ``OVERDUE``). Counted in the same day basis as ``day_basis``.
        due_window_days: How many days before the deadline the instance is
            in state ``UPCOMING`` rather than ``PENDING``. Defaults to 30.

    """

    kind: DeadlineKind
    offset_days: int | None = Field(default=None, ge=0)
    day_basis: DayBasis = DayBasis.CALENDAR
    absolute_date: date | None = None
    month: int | None = Field(default=None, ge=1, le=12)
    day: int | None = Field(default=None, ge=1, le=31)
    recurrence: RecurrenceFreq | None = None
    grace_days: int = Field(default=0, ge=0)
    due_window_days: int = Field(default=30, ge=0)

    @field_validator("offset_days")
    @classmethod
    def _validate_offset(cls, v: int | None) -> int | None:
        """Offset days must be non-negative when provided."""
        if v is not None and v < 0:
            raise ValueError("offset_days must be >= 0")
        return v


class Obligation(BaseModel):
    """A single regulatory obligation expressed as data.

    The shape borrows LegalRuleML's ``Obligation`` vocabulary (bearer,
    penalty, temporal validity) but stays small enough to author by hand
    in YAML.

    Attributes:
        id: Stable identifier (e.g. ``"gdpr.art33.breach_notification"``).
        title: Short human-readable title.
        bearer: Who is obligated.
        required_action: What the bearer must do.
        trigger: A free-text description of the triggering condition. The
            actual decision of whether the trigger has fired is supplied by
            the caller via the event log; the engine does not parse this.
        applicability: Optional callable that returns ``True``, ``False``,
            or ``None`` (undetermined) given a context dict. When ``None``
            (the field, not the return value) the obligation is always
            considered applicable. Stored as a Python callable; YAML/JSON
            inputs leave this as ``None`` and rely on the event log.
        deadline: How the due date is computed (see :class:`DeadlineSpec`).
        evidence: What evidence satisfies the obligation.
        penalty: The consequence of violation (informational).
        source: Statutory citation.
        jurisdiction: ISO 3166-1 alpha-2 code (e.g. ``"ES"`` or ``"DE"``)
            used to resolve the holiday calendar.
        effective_from: First date on which the obligation may apply.
        effective_until: Last date on which the obligation may apply.
        tags: Free-form tags used by reporting and filters.

    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str
    title: str
    bearer: Bearer
    required_action: str
    trigger: str
    applicability: Callable[[dict[str, object]], bool | None] | None = None
    deadline: DeadlineSpec
    evidence: EvidenceRequirement
    penalty: Penalty | None = None
    source: SourceCitation
    jurisdiction: str = Field(..., min_length=2, max_length=2)
    effective_from: date | None = None
    effective_until: date | None = None
    tags: list[str] = Field(default_factory=list)

    @field_validator("jurisdiction")
    @classmethod
    def _upper_jurisdiction(cls, v: str) -> str:
        """Normalise jurisdiction codes to upper case."""
        return v.upper()

    def is_in_force(self, on: date) -> bool:
        """Return whether the obligation is in force on ``on``.

        Args:
            on: The date to check.

        Returns:
            ``True`` if ``on`` falls within ``[effective_from,
            effective_until]`` (open-ended bounds treated as -inf/+inf).

        Example:
            >>> obl.is_in_force(date(2026, 6, 14))
            True

        """
        if self.effective_from and on < self.effective_from:
            return False
        if self.effective_until and on > self.effective_until:
            return False
        return True
