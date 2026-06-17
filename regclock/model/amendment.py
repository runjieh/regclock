"""Versioning of obligations over calendar time.

Real obligations evolve: they are amended, partially derogated, or
superseded by later legislation. The :class:`AmendmentLog` keeps these
exogenous edits as an ordered, timestamped sequence so the rest of the
engine can ask: *what was the obligation, as it stood on date X?*

This is both legally necessary and analytically useful: the timestamped
edits are clean exogenous events for downstream causal analysis.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from regclock.model.obligation import Obligation


class Amendment(BaseModel):
    """A single timestamped change to an obligation.

    Attributes:
        effective_on: Date from which the amendment takes effect.
        kind: What the amendment does to the obligation:
            * ``"modify"``: replace specific fields.
            * ``"derogate"``: temporarily disable applicability.
            * ``"supersede"``: replace the obligation entirely with a
              new payload.
        target_obligation_id: ID of the obligation this amendment
            targets.
        patch: For ``"modify"``, a dict of field paths to new values
            (top-level fields only). For ``"supersede"``, the full
            replacement obligation payload.
        rationale: Optional human-readable justification.
        source: Citation of the amending instrument.

    """

    effective_on: date
    kind: Literal["modify", "derogate", "supersede"]
    target_obligation_id: str
    patch: dict[str, object] = Field(default_factory=dict)
    rationale: str | None = None
    source: str | None = None


class AmendmentLog(BaseModel):
    """An ordered, append-only log of amendments across all obligations.

    Attributes:
        entries: Amendments in the order they were recorded. They are
            applied in ``effective_on`` order when materialising
            obligations as of a date.

    """

    entries: list[Amendment] = Field(default_factory=list)

    def for_obligation(self, obligation_id: str) -> list[Amendment]:
        """Return amendments targeting one obligation, sorted by effective date.

        Args:
            obligation_id: The obligation's ``id`` field.

        Returns:
            A new list of matching amendments, in chronological order.

        """
        rows = [a for a in self.entries if a.target_obligation_id == obligation_id]
        return sorted(rows, key=lambda a: a.effective_on)

    def as_of(self, obligation: Obligation, on: date) -> Obligation | None:
        """Apply every relevant amendment up to ``on``.

        Args:
            obligation: The current definition of the obligation.
            on: The reference date. Amendments with
                ``effective_on <= on`` are applied; later ones are
                ignored.

        Returns:
            The obligation as it stood on ``on``. Returns ``None`` if the
            obligation has been derogated and the derogation has not yet
            been lifted. Returns the superseding obligation when one
            applies.

        Example:
            >>> log.as_of(obl, date(2026, 6, 14))
            Obligation(...)

        """
        current: Obligation | None = obligation
        for amendment in self.for_obligation(obligation.id):
            if amendment.effective_on > on:
                break
            if current is None:
                continue
            if amendment.kind == "modify":
                current = current.model_copy(update=dict(amendment.patch))
            elif amendment.kind == "derogate":
                current = None
            elif amendment.kind == "supersede":
                current = Obligation.model_validate(amendment.patch)
        return current
