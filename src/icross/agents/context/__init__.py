"""Pluggable Context Engine — conversation history management.

Usage:
    from icross.agents.context import SummaryWindowEngine, get_context_engine_for_provider

    engine = get_context_engine_for_provider("minimax")
    if await engine.should_compress(messages):
        updates = await engine.compress(messages)
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from .engine import ContextEngine
from .window_engine import SummaryWindowEngine

_logger = logging.getLogger(__name__)


def get_context_engine_for_provider(
    provider_id: str = "minimax",
    *,
    protect_first_n: int = 3,
    protect_last_n: int = 10,
    threshold_ratio: float = 0.80,
    summary_llm: BaseChatModel | None = None,
) -> ContextEngine:
    """Create a SummaryWindowEngine configured for the given provider.

    Reads the provider's ``context_length`` from ``providers.json`` and
    sets the compression threshold to ``context_length * threshold_ratio``.

    Args:
        provider_id: The provider ID (e.g. "minimax", "anthropic", "deepseek").
        protect_first_n: Number of initial messages to protect.
        protect_last_n: Number of trailing messages to protect.
        threshold_ratio: Fraction of context_length that triggers compression.
        summary_llm: Optional LLM for generating summaries. If None, only
                     window trimming is performed (no summarization).

    Returns:
        A configured SummaryWindowEngine instance.
    """
    try:
        from icross.agents.llm.models import get_provider

        provider = get_provider(provider_id)
        context_length = provider.context_length if provider else 200000
    except Exception as e:
        _logger.warning("Failed to load provider config: %s; using default 200K", e)
        context_length = 200000

    return SummaryWindowEngine(
        context_length=context_length,
        threshold_ratio=threshold_ratio,
        protect_first_n=protect_first_n,
        protect_last_n=protect_last_n,
        summary_llm=summary_llm,
    )


__all__ = [
    "ContextEngine",
    "SummaryWindowEngine",
    "get_context_engine_for_provider",
]
