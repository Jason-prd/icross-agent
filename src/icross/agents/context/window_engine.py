"""SummaryWindowEngine — window-based compression with LLM summarization.

Strategy:
  1. Keep first N messages (system prompt + initial exchange).
  2. Keep last M messages (recent context).
  3. Compress middle messages into a single SystemMessage summary.

Threshold is dynamically calculated as 80% of the model's ``context_length``.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from langchain_core.messages import RemoveMessage, SystemMessage
from langchain_core.language_models.chat_models import BaseChatModel

from .engine import ContextEngine

_logger = logging.getLogger(__name__)

# Rough chars-per-token estimate for mixed CJK/English text
_CHARS_PER_TOKEN = 2.0

# Summary prompt used when calling the LLM to compress middle messages
_SUMMARY_PROMPT = """请总结以下对话的核心内容，保留关键信息：已完成的操作、已获取的数据、
用户的重要需求、已做出的决策。用中文简洁概括，控制在500字以内。

对话内容：
{content}"""


class SummaryWindowEngine(ContextEngine):
    """上下文窗口引擎 — 保留首尾消息，压缩中间部分为摘要。

    Args:
        context_length: 模型的最大上下文长度（token 数）。
        threshold_ratio: 压缩触发比例（默认 0.80 = 80%）。
        protect_first_n: 保留前 N 条消息。
        protect_last_n: 保留后 N 条消息。
        summary_llm: 用于生成摘要的 LLM。为 None 时只做窗口裁剪不做总结。
        chars_per_token: 字符到 token 的估算比例。
    """

    def __init__(
        self,
        context_length: int = 200000,
        *,
        threshold_ratio: float = 0.80,
        protect_first_n: int = 3,
        protect_last_n: int = 10,
        summary_llm: BaseChatModel | None = None,
        chars_per_token: float = _CHARS_PER_TOKEN,
    ) -> None:
        self._context_length = context_length
        self._threshold_ratio = threshold_ratio
        self._protect_first_n = protect_first_n
        self._protect_last_n = protect_last_n
        self._summary_llm = summary_llm
        self._chars_per_token = chars_per_token

        # Threshold in characters
        self._threshold_chars = int(context_length * threshold_ratio * chars_per_token)

        _logger.info(
            "SummaryWindowEngine: context_length=%d, threshold=%.1fK chars, "
            "protect_first=%d, protect_last=%d",
            context_length, self._threshold_chars / 1000,
            protect_first_n, protect_last_n,
        )

    # ---------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------

    async def should_compress(self, messages: list) -> bool:
        """Check if total message length exceeds the threshold."""
        if len(messages) <= self._protect_first_n + self._protect_last_n + 1:
            return False
        total_chars = sum(len(m.content) for m in messages if hasattr(m, "content"))
        return total_chars > self._threshold_chars

    async def compress(self, messages: list) -> list:
        """Compress messages: remove middle, insert summary.

        Returns a list of RemoveMessage / SystemMessage that the
        ``pre_model_hook`` should return as a state update.
        """
        if len(messages) <= self._protect_first_n + self._protect_last_n:
            return []

        first_n = self._protect_first_n
        last_n = self._protect_last_n

        # Messages to keep: first N + last M
        middle = messages[first_n:-last_n] if last_n > 0 else messages[first_n:]

        if not middle:
            return []

        # Build state update: RemoveMessage for each middle message
        state_updates: list = [
            RemoveMessage(id=m.id)
            for m in middle
            if hasattr(m, "id") and m.id
        ]

        # Try to generate a summary
        summary_text = await self._summarize(middle)

        if summary_text:
            # Insert summary as a SystemMessage after the first N messages
            state_updates.append(SystemMessage(content=f"[历史摘要]\n{summary_text}"))
            _logger.info(
                "Compressed %d middle messages into summary (%d chars)",
                len(middle), len(summary_text),
            )
        else:
            # Fallback: just remove middle without summary
            _logger.info(
                "Removed %d middle messages (no summary available)",
                len(middle),
            )

        return state_updates

    def update_usage(self, input_tokens: int, output_tokens: int) -> None:
        """Track token usage (for future adaptive threshold adjustment)."""
        pass  # Reserved for future adaptive logic

    # ---------------------------------------------------------------
    # Internal
    # ---------------------------------------------------------------

    async def _summarize(self, messages: list) -> str | None:
        """Call LLM to generate a summary of the middle messages."""
        if not self._summary_llm:
            return None

        # Serialize middle messages into text
        lines: list[str] = []
        for m in messages:
            role = getattr(m, "type", "unknown")
            content = getattr(m, "content", "")
            # Truncate very long individual messages
            if len(content) > 2000:
                content = content[:2000] + "..."
            lines.append(f"[{role}]: {content}")

        content_text = "\n\n".join(lines)

        # Truncate input if too long (keep last 15000 chars)
        if len(content_text) > 15000:
            content_text = "...(前文省略)...\n\n" + content_text[-15000:]

        try:
            prompt = _SUMMARY_PROMPT.format(content=content_text)
            result = await self._summary_llm.ainvoke(prompt)
            summary = result.content if hasattr(result, "content") else str(result)
            return summary.strip() if summary else None
        except Exception as e:
            _logger.warning("Summary generation failed: %s", e)
            return None

    def update_context_length(self, context_length: int) -> None:
        """Update the context length (e.g., when switching models)."""
        self._context_length = context_length
        self._threshold_chars = int(context_length * self._threshold_ratio * self._chars_per_token)
        _logger.info(
            "SummaryWindowEngine: context_length updated to %d, threshold=%.1fK chars",
            context_length, self._threshold_chars / 1000,
        )
