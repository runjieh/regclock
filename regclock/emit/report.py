"""Status reports in Markdown, HTML, or JSON.

JSON output keeps machine-readable English ``state.value`` strings so
that serialised reports remain locale-agnostic and diffable. Markdown
and HTML use the translated display strings registered via
:mod:`regclock.i18n`.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Literal

from regclock import i18n
from regclock.lifecycle.state_machine import LifecycleStatus


def render_report(
    statuses: Iterable[LifecycleStatus],
    fmt: Literal["markdown", "html", "json"] = "markdown",
    lang: str | None = None,
) -> str:
    """Render a flat status report for a collection of lifecycle statuses.

    Args:
        statuses: The lifecycle statuses to include.
        fmt: Output format: ``"markdown"`` (default), ``"html"``, or
            ``"json"``.
        lang: Language code for human-readable columns. JSON output is
            always machine-readable (English ``state.value``);
            ``lang`` only affects Markdown and HTML. Defaults to the
            current default language.

    Returns:
        The rendered report as a single string.

    Raises:
        ValueError: If ``fmt`` is not a recognised format.

    Example:
        >>> print(render_report(statuses))
        | Obligation | State | Due | ...

    """
    statuses_list = list(statuses)
    rows = [_row(s) for s in statuses_list]
    if fmt == "json":
        return json.dumps(rows, indent=2, default=str)
    resolved_lang = lang or i18n.get_default_language()
    display_rows = [
        {**row, "state_display": i18n.label_for_state(s.state, resolved_lang)}
        for row, s in zip(rows, statuses_list)
    ]
    if fmt == "markdown":
        return _markdown(display_rows, resolved_lang)
    if fmt == "html":
        return _html(display_rows, resolved_lang)
    raise ValueError(f"Unknown format: {fmt}")


def _row(status: LifecycleStatus) -> dict[str, object]:
    """Flatten a :class:`LifecycleStatus` into a serialisable row dict.

    ``state`` is always the machine-readable enum value (English) so
    that JSON output is locale-independent.
    """
    return {
        "obligation_id": status.instance.obligation_id,
        "title": status.instance.title,
        "jurisdiction": status.instance.jurisdiction,
        "due_on": status.instance.due_on.isoformat(),
        "state": status.state.value,
        "days_to_due": status.days_to_due,
        "evidence_on": status.evidence.occurred_on.isoformat() if status.evidence else None,
    }


def _headers(lang: str) -> dict[str, str]:
    return {
        "obligation": i18n.t("report.col_obligation", lang),
        "title": i18n.t("report.col_title", lang),
        "jurisdiction": i18n.t("report.col_jurisdiction", lang),
        "due": i18n.t("report.col_due", lang),
        "state": i18n.t("report.col_state", lang),
        "days": i18n.t("report.col_days", lang),
        "evidence": i18n.t("report.col_evidence", lang),
    }


def _markdown(rows: list[dict[str, object]], lang: str) -> str:
    """Render rows as a GitHub-flavoured Markdown table."""
    h = _headers(lang)
    header = (
        f"| {h['obligation']} | {h['title']} | {h['jurisdiction']} | "
        f"{h['due']} | {h['state']} | {h['days']} | {h['evidence']} |\n"
        "|---|---|---|---|---|---|---|\n"
    )
    body = "".join(
        f"| {r['obligation_id']} | {r['title']} | {r['jurisdiction']} | "
        f"{r['due_on']} | {r['state_display']} | {r['days_to_due']} | "
        f"{r['evidence_on'] or '-'} |\n"
        for r in rows
    )
    return header + body


def _html(rows: list[dict[str, object]], lang: str) -> str:
    """Render rows as a minimal HTML table."""
    h = _headers(lang)
    head = (
        "<table><thead><tr>"
        f"<th>{h['obligation']}</th><th>{h['title']}</th>"
        f"<th>{h['jurisdiction']}</th><th>{h['due']}</th>"
        f"<th>{h['state']}</th><th>{h['days']}</th>"
        f"<th>{h['evidence']}</th>"
        "</tr></thead><tbody>"
    )
    body = "".join(
        f"<tr><td>{r['obligation_id']}</td><td>{r['title']}</td>"
        f"<td>{r['jurisdiction']}</td><td>{r['due_on']}</td>"
        f"<td>{r['state_display']}</td><td>{r['days_to_due']}</td>"
        f"<td>{r['evidence_on'] or '-'}</td></tr>"
        for r in rows
    )
    return head + body + "</tbody></table>"
