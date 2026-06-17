"""regclock: a calendar-correct runtime for regulatory obligation deadlines.

This package represents a regulatory obligation as plain data (a small
Pydantic schema) and computes its deadline lifecycle over real calendar
time as a deterministic, auditable state machine. See the README for
the *is / is not* scope and prior-art comparison.

Sub-namespaces of interest:

* :mod:`regclock.io` — importers (LegalRuleML) and reasoner adapters
  (:class:`regclock.io.deontic.DeonticReasoner`).
* :mod:`regclock.i18n` — language registry for display strings; English
  is built-in, other languages register via
  :func:`regclock.i18n.register_language`.
"""

from regclock import i18n
from regclock.lifecycle.events import Event, EventLog
from regclock.lifecycle.schedule import ScheduledInstance, build_schedule
from regclock.lifecycle.state_machine import LifecycleStatus, resolve_state
from regclock.model.amendment import Amendment, AmendmentLog
from regclock.model.calendar import BusinessCalendar
from regclock.model.obligation import (
    Bearer,
    DeadlineSpec,
    EvidenceRequirement,
    Obligation,
    Penalty,
    SourceCitation,
)
from regclock.schemas.types import (
    DayBasis,
    DeadlineKind,
    EventKind,
    RecurrenceFreq,
    State,
)

__all__ = [
    "Amendment",
    "AmendmentLog",
    "Bearer",
    "BusinessCalendar",
    "DayBasis",
    "DeadlineKind",
    "DeadlineSpec",
    "Event",
    "EventKind",
    "EventLog",
    "EvidenceRequirement",
    "LifecycleStatus",
    "Obligation",
    "Penalty",
    "RecurrenceFreq",
    "ScheduledInstance",
    "SourceCitation",
    "State",
    "build_schedule",
    "i18n",
    "resolve_state",
]

__version__ = "0.0.1"
