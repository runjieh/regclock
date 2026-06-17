"""Optional utilities: clause-to-draft LLM adapter and small helpers."""

from regclock.utils.llm_client import (
    DraftObligation,
    LLMNotConfigured,
    draft_obligation_from_clause,
)

__all__ = [
    "DraftObligation",
    "LLMNotConfigured",
    "draft_obligation_from_clause",
]
