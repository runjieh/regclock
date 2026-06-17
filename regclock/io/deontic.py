"""Adapter Protocol for plugging an external deontic reasoner into regclock.

regclock deliberately does NOT include a defeasible/deontic reasoner.
When a real reasoner is needed (e.g. SPINdle, clingo/ASP, Carneades, or
an in-house HTTP service), wrap it in this :class:`DeonticReasoner`
Protocol and feed its verdict into the obligation's ``applicability``
callable via :func:`as_applicability`.

The boundary stays clean: regclock never knows which reasoner is in use,
the reasoner never knows about deadlines, and either side can be
replaced without touching the other.

Integration patterns (pick one):

* **subprocess** — ship a small wrapper class that serialises ``context``
  to the reasoner's input format, invokes the binary (e.g.
  ``java -jar spindle.jar``), parses the verdict and returns it. Best
  for SPINdle, Carneades, or any JVM-based tool.
* **embedded Python bindings** — for tools with first-class Python
  bindings (``clingo``, ``z3-solver``), call the API directly.
* **HTTP** — wrap a microservice/REST endpoint with ``httpx`` or
  ``requests``. Good fit when the reasoner is heavy or shared.

In every case the wrapper exposes a single :meth:`evaluate` method that
returns ``True`` (rule applies), ``False`` (rule does not apply), or
``None`` (undetermined). regclock maps these to ``applicable``,
``WAIVED``, and ``UNDETERMINED`` respectively.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable


@runtime_checkable
class DeonticReasoner(Protocol):
    """Anything that can decide whether a normative rule applies.

    Implementations are expected to be deterministic given the same
    ``rule_id`` and ``context`` so that regclock's overall behaviour
    remains reproducible. Any internal randomness or wall-clock
    dependency in the reasoner will break the reproducibility
    guarantees regclock offers downstream.

    Methods:
        evaluate: Return ``True`` if the rule applies, ``False`` if it
            does not, or ``None`` if the reasoner cannot decide from
            the given facts (caller surfaces this as ``UNDETERMINED``).

    """

    def evaluate(self, rule_id: str, context: dict[str, object]) -> bool | None:
        """Decide applicability of ``rule_id`` given ``context``."""
        ...


def as_applicability(
    reasoner: DeonticReasoner,
    rule_id: str,
    context_builder: Callable[[dict[str, object]], dict[str, object]] | None = None,
) -> Callable[[dict[str, object]], bool | None]:
    """Wrap a :class:`DeonticReasoner` into an ``applicability`` callable.

    Args:
        reasoner: The external reasoner.
        rule_id: Identifier of the normative rule inside the reasoner's
            theory (often the same as the obligation's ``id``, but kept
            separate so naming schemes can diverge).
        context_builder: Optional projection from regclock's runtime
            context (``{"obligation", "instance", "events", "as_of"}``)
            to the fact set the reasoner expects. When ``None``, the
            full context is passed through; reasoners that want only a
            curated fact set should supply this.

    Returns:
        A callable suitable for :attr:`Obligation.applicability`. Any
        exception raised by the reasoner is converted to ``None`` so
        the state machine surfaces ``UNDETERMINED`` rather than
        propagating an internal error.

    Example:
        >>> from regclock.io.deontic import as_applicability
        >>> obligation = Obligation(
        ...     id="gdpr.art35.dpia",
        ...     applicability=as_applicability(
        ...         my_spindle_wrapper, rule_id="gdpr.art35"
        ...     ),
        ...     ...,
        ... )

    """

    def _applicability(ctx: dict[str, object]) -> bool | None:
        facts = context_builder(ctx) if context_builder is not None else ctx
        try:
            return reasoner.evaluate(rule_id, facts)
        except Exception:
            return None

    return _applicability


__all__ = ["DeonticReasoner", "as_applicability"]
