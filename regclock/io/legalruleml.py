"""Optional LegalRuleML importer.

This importer covers a *deliberately small* subset of LegalRuleML:

* ``lrml:PrescriptiveStatement`` containing
* ``lrml:Obligation`` with a Bearer, a deontic content (the required
  action), an optional Penalty, and optional temporal validity.

The aim is interoperability with the OASIS standard for ingest, not
parity. Anything richer (defeasibility, alternative deontic operators,
nested rule structures) is intentionally rejected: callers should reach
for a proper deontic reasoner there.

The :mod:`lxml` dependency is loaded lazily; without it, callers get a
clear :class:`LegalRuleMLImportError` rather than a cryptic import
failure at module load.
"""

from __future__ import annotations

import warnings
from datetime import date
from typing import Any

from regclock.model.obligation import (
    Bearer,
    DeadlineSpec,
    EvidenceRequirement,
    Obligation,
    Penalty,
    SourceCitation,
)
from regclock.schemas.types import DayBasis, DeadlineKind

LRML_NS = "http://docs.oasis-open.org/legalruleml/ns/v1.0/"
NSMAP = {"lrml": LRML_NS}


class LegalRuleMLImportError(RuntimeError):
    """Raised when the LegalRuleML importer cannot run or cannot parse input."""


class LegalRuleMLImportWarning(UserWarning):
    """Issued when a non-fatal field is missing and a placeholder is used.

    Importers should surface these via :mod:`warnings` so callers can
    decide to log, suppress, or escalate them. The most common case is
    ``lrml:Jurisdiction`` being absent, which forces the placeholder
    ``"ZZ"`` and almost always needs to be overridden before production
    use.
    """


def import_legalruleml(xml_source: str | bytes) -> list[Obligation]:
    """Parse a subset of LegalRuleML into :class:`Obligation` instances.

    Args:
        xml_source: Either an XML string/bytes payload or a filesystem
            path to an XML document.

    Returns:
        A list of obligations parsed from the document. Statements that
        do not match the supported subset are skipped.

    Raises:
        LegalRuleMLImportError: If :mod:`lxml` is not installed, or if
            the input cannot be parsed.

    Example:
        >>> import_legalruleml(open('breach.xml').read())
        [Obligation(id='breach.notif', ...)]

    """
    try:
        from lxml import etree  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise LegalRuleMLImportError(
            "LegalRuleML import requires the [legalruleml] extra "
            "(`pip install regclock[legalruleml]`)."
        ) from exc

    try:
        if isinstance(xml_source, (bytes, bytearray)):
            root = etree.fromstring(xml_source)
        elif _looks_like_xml(xml_source):
            root = etree.fromstring(xml_source.encode("utf-8"))
        else:
            tree = etree.parse(xml_source)
            root = tree.getroot()
    except etree.XMLSyntaxError as exc:
        raise LegalRuleMLImportError(f"Invalid XML: {exc}") from exc

    return [_parse_obligation(node) for node in root.iterfind(".//lrml:Obligation", NSMAP)]


def _looks_like_xml(value: str) -> bool:
    """Heuristic for "is this an XML payload vs a path?"."""
    return value.lstrip().startswith("<")


def _parse_obligation(node: Any) -> Obligation:
    """Translate one ``lrml:Obligation`` node into an :class:`Obligation`.

    The mapping is intentionally lossy. Fields the engine needs that
    LegalRuleML does not express directly (e.g. evidence kinds) fall
    back to sensible defaults so the result is at least *runnable*.
    """
    oid = node.get("key") or node.get("id") or "unknown"
    bearer_id = _text(node, "lrml:Bearer", "id") or "unknown_bearer"
    bearer_name = _text(node, "lrml:Bearer", default=bearer_id)
    action = _text(node, "lrml:DeonticSpecification", default="(action not specified)")
    title = _text(node, "lrml:Description", default=oid)
    citation = _text(node, "lrml:Source", default="(no citation)")
    raw_jurisdiction = _text(node, "lrml:Jurisdiction")
    if raw_jurisdiction:
        jurisdiction = raw_jurisdiction[:2].upper()
    else:
        warnings.warn(
            f"LegalRuleML obligation {oid!r} has no <lrml:Jurisdiction>; "
            "defaulting to placeholder 'ZZ'. Override before production use.",
            LegalRuleMLImportWarning,
            stacklevel=3,
        )
        jurisdiction = "ZZ"

    penalty_node = node.find("lrml:Penalty", NSMAP)
    penalty: Penalty | None = None
    if penalty_node is not None:
        penalty = Penalty(description=(penalty_node.text or "").strip() or "(penalty)")

    return Obligation(
        id=oid,
        title=title,
        bearer=Bearer(id=bearer_id, name=bearer_name),
        required_action=action,
        trigger=_text(node, "lrml:Trigger", default="(trigger not specified)"),
        deadline=DeadlineSpec(
            kind=DeadlineKind.RELATIVE,
            offset_days=int(_text(node, "lrml:OffsetDays", default="30") or 30),
            day_basis=DayBasis.CALENDAR,
        ),
        evidence=EvidenceRequirement(
            kinds=["legalruleml_imported"],
            description="Auto-imported from LegalRuleML; refine before production use.",
        ),
        penalty=penalty,
        source=SourceCitation(title=citation),
        jurisdiction=jurisdiction,
        effective_from=_date(node, "lrml:EffectiveFrom"),
        effective_until=_date(node, "lrml:EffectiveUntil"),
    )


def _text(node: Any, xpath: str, attr: str | None = None, default: str | None = None) -> str | None:
    """Helper to read either text content or an attribute from a child node."""
    child = node.find(xpath, NSMAP)
    if child is None:
        return default
    if attr is not None:
        return child.get(attr, default)
    return (child.text or "").strip() or default


def _date(node: Any, xpath: str) -> date | None:
    """Parse an ISO date from a child node, returning ``None`` if absent."""
    raw = _text(node, xpath)
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None
