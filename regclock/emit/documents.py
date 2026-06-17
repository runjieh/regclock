"""Render filing/document stubs and reminder payloads via Jinja2.

Templates live under ``regclock/templates/{lang}/``. The English pack
ships in-tree; additional language packs are registered at runtime via
:func:`regclock.i18n.register_language`. When a language registers no
template directory, the English templates are used with the registered
labels substituted in via the ``ui`` namespace and the
``state_label`` / ``event_kind_label`` Jinja globals.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from jinja2 import (
    ChoiceLoader,
    Environment,
    FileSystemLoader,
    StrictUndefined,
    select_autoescape,
)

from regclock import i18n
from regclock.lifecycle.state_machine import LifecycleStatus
from regclock.model.obligation import Obligation


def _env(lang: str | None = None) -> Environment:
    """Build a Jinja2 environment configured for ``lang``.

    The loader tries the language-specific template directory first
    (if registered via :func:`regclock.i18n.register_language`) and
    falls back to the in-tree English pack for any file the language
    pack does not override. ``ui``, ``state_label``, and
    ``event_kind_label`` are exposed as globals so templates do not
    need to import anything.
    """
    resolved_lang = (lang or i18n.get_default_language()).lower()
    en_dir = str(resources.files("regclock").joinpath("templates", "en"))
    loaders = []
    custom_dir = i18n.templates_dir_for(resolved_lang)
    if custom_dir is not None:
        loaders.append(FileSystemLoader(str(Path(custom_dir))))
    loaders.append(FileSystemLoader(en_dir))
    env = Environment(
        loader=ChoiceLoader(loaders),
        autoescape=select_autoescape(enabled_extensions=("html", "md")),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.globals["ui"] = i18n.labels_for_jinja(resolved_lang)
    env.globals["state_label"] = lambda state: i18n.label_for_state(state, resolved_lang)
    env.globals["event_kind_label"] = lambda kind: i18n.label_for_event_kind(kind, resolved_lang)
    return env


def render_stub(
    obligation: Obligation,
    status: LifecycleStatus,
    lang: str | None = None,
) -> str:
    """Render a Markdown filing/document stub for one obligation instance.

    Args:
        obligation: The obligation definition.
        status: The computed lifecycle status (provides due date,
            state, evidence references).
        lang: Language code; defaults to
            :func:`regclock.i18n.get_default_language`.

    Returns:
        A Markdown string ready to be saved to disk or attached to a
        ticket. The content is descriptive only: the engine does not
        sign or submit anything.

    Example:
        >>> render_stub(obl, status, lang="es")
        '# Borrador de presentación: ...'

    """
    template = _env(lang).get_template("filing_stub.md.j2")
    return template.render(obligation=obligation, status=status)


def render_reminder(
    obligation: Obligation,
    status: LifecycleStatus,
    lang: str | None = None,
) -> dict[str, str]:
    """Render a reminder payload for an upcoming or overdue instance.

    Args:
        obligation: The obligation definition.
        status: The computed lifecycle status.
        lang: Language code; defaults to
            :func:`regclock.i18n.get_default_language`.

    Returns:
        A dict with ``subject``, ``summary``, and ``body`` keys. The
        dict is intentionally minimal so it can be fed into email,
        Slack, or ticket-system adapters without further work.

    Example:
        >>> render_reminder(obl, status)
        {'subject': '...', 'summary': '...', 'body': '...'}

    """
    body_template = _env(lang).get_template("reminder_body.md.j2")
    body = body_template.render(obligation=obligation, status=status)
    subject = (
        f"[{obligation.jurisdiction}] {obligation.title} — "
        f"{i18n.t('ui.due_on', lang).lower()} {status.instance.due_on}"
    )
    summary = (
        f"{i18n.t('report.col_state', lang)}: "
        f"{i18n.label_for_state(status.state, lang)}; "
        f"{i18n.t('ui.reminder_due_date', lang).lower()} "
        f"({status.instance.due_on})."
    )
    return {"subject": subject, "summary": summary, "body": body}
