"""Optional LLM adapter: draft an Obligation YAML from a free-text clause.

This module is intentionally a thin client over either OpenAI or
Anthropic SDKs. It is **never required** by the engine: ``regclock``
runs fully offline by default. Any output produced here is a *draft for
a human to review*, never trusted blind: the adapter returns the LLM's
suggested YAML alongside a structured warning that a human review is
required, and the CLI flags this in its output.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

_SYSTEM_PROMPT = """You are an assistant that drafts machine-readable regulatory obligations.
Output ONLY a YAML document that conforms to the `regclock.model.Obligation`
schema. Do not include any prose. Do not invent statutory citations. If a
field cannot be determined from the clause, use `null` or a clearly
placeholder string like "TBD".
"""


@dataclass
class DraftObligation:
    """A draft obligation suggested by an LLM.

    Attributes:
        yaml: The raw YAML payload returned by the model. The caller is
            expected to parse and validate this with
            :class:`~regclock.model.obligation.Obligation`.
        warnings: Hard-coded warnings reminding the operator that the
            draft must be reviewed by a competent human before use.
        provider: ``"openai"`` or ``"anthropic"``.
        model: Model identifier used.

    """

    yaml: str
    warnings: list[str]
    provider: Literal["openai", "anthropic"]
    model: str


class LLMNotConfigured(RuntimeError):
    """Raised when no LLM provider is configured (missing SDK or API key)."""


def draft_obligation_from_clause(
    clause: str,
    *,
    provider: Literal["openai", "anthropic", "auto"] = "auto",
    model: str | None = None,
) -> DraftObligation:
    """Draft an obligation YAML from a free-text regulatory clause.

    Args:
        clause: The verbatim regulatory clause.
        provider: Which provider to use. ``"auto"`` picks Anthropic if
            its SDK is installed and ``ANTHROPIC_API_KEY`` is set,
            otherwise OpenAI.
        model: Optional model identifier override.

    Returns:
        A :class:`DraftObligation` whose ``yaml`` field holds the model's
        suggested YAML and whose ``warnings`` field documents that this
        is a draft for human review only.

    Raises:
        LLMNotConfigured: If the selected provider's SDK is missing or
            no API key is configured.

    Example:
        >>> draft = draft_obligation_from_clause("Notify the authority within 72 hours.")
        >>> print(draft.yaml[:32])
        id: TBD
        title: TBD

    """
    chosen = _pick_provider(provider)
    if chosen == "anthropic":
        yaml = _draft_with_anthropic(clause, model or "claude-haiku-4-5-20251001")
        used_model = model or "claude-haiku-4-5-20251001"
    elif chosen == "openai":
        yaml = _draft_with_openai(clause, model or "gpt-4o-mini")
        used_model = model or "gpt-4o-mini"
    else:  # pragma: no cover - defensive
        raise LLMNotConfigured(f"No usable LLM provider: {provider}")

    return DraftObligation(
        yaml=yaml,
        warnings=[
            "This obligation was drafted by an LLM and must be reviewed by a "
            "qualified human before use.",
            "Do not run a deadline pipeline against an unreviewed draft.",
        ],
        provider=chosen,
        model=used_model,
    )


def _pick_provider(preference: str) -> Literal["openai", "anthropic"]:
    """Choose a provider based on what's installed and configured."""
    if preference == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise LLMNotConfigured("ANTHROPIC_API_KEY is not set")
        return "anthropic"
    if preference == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            raise LLMNotConfigured("OPENAI_API_KEY is not set")
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic  # noqa: F401

            return "anthropic"
        except ImportError:
            pass
    if os.environ.get("OPENAI_API_KEY"):
        try:
            import openai  # noqa: F401

            return "openai"
        except ImportError:  # pragma: no cover
            pass
    raise LLMNotConfigured(
        "No LLM provider available. Install regclock[llm] and set "
        "ANTHROPIC_API_KEY or OPENAI_API_KEY."
    )


def _draft_with_anthropic(clause: str, model: str) -> str:
    """Call the Anthropic SDK and return the model's raw text output."""
    try:
        import anthropic  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise LLMNotConfigured("`anthropic` SDK not installed") from exc

    client = anthropic.Anthropic()
    message = client.messages.create(
        model=model,
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": clause}],
    )
    return "".join(block.text for block in message.content if hasattr(block, "text"))


def _draft_with_openai(clause: str, model: str) -> str:
    """Call the OpenAI SDK and return the model's raw text output."""
    try:
        from openai import OpenAI  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise LLMNotConfigured("`openai` SDK not installed") from exc

    client = OpenAI()
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": clause},
        ],
    )
    return completion.choices[0].message.content or ""
