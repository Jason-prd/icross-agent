"""ContextEngine ABC — pluggable conversation history management.

Each engine implements a strategy for managing long message histories:
trimming, summarization, or windowing.

Engines are integrated into the agent via LangGraph's ``pre_model_hook``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ContextEngine(ABC):
    """Base class for conversation context management.

    Usage:
        engine = MyEngine(context_length=200000)
        if await engine.should_compress(messages):
            compressed = await engine.compress(messages)
            # Replace old messages with compressed using RemoveMessage
    """

    @abstractmethod
    async def should_compress(self, messages: list) -> bool:
        """Return True if the message list exceeds the compression threshold."""
        ...

    @abstractmethod
    async def compress(self, messages: list) -> list:
        """Compress messages: trim window + summarize middle section.

        Returns a list of messages where old messages are marked for removal
        and a summary message is inserted.
        """
        ...

    @abstractmethod
    def update_usage(self, input_tokens: int, output_tokens: int) -> None:
        """Track token usage for adaptive threshold adjustment."""
        ...
