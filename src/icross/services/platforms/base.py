"""Platform adapter interfaces — abstract notification layer.

Follows Hermes Agent's BasePlatformAdapter pattern, adapted for iCross's
one-way notification use case (no inbound event handling).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any


class Platform(str, Enum):
    """Supported notification platforms."""
    FEISHU = "feishu"
    TELEGRAM = "telegram"
    WECHAT = "wechat"       # 企业微信
    DINGTALK = "dingtalk"

    def display_name(self) -> str:
        names = {
            "feishu": "飞书",
            "telegram": "Telegram",
            "wechat": "企业微信",
            "dingtalk": "钉钉",
        }
        return names.get(self.value, self.value)


class BasePlatformAdapter(ABC):
    """Abstract base class for platform notification adapters.

    Each platform adapter wraps its SDK and implements this common interface.
    Only outbound notification is required (no inbound event handling).

    Usage:
        adapter = get_platform_adapter(Platform.FEISHU)
        await adapter.send_message("chat_id", "Hello")
    """

    @property
    @abstractmethod
    def platform(self) -> Platform:
        """Return the platform enum value this adapter supports."""
        ...

    @property
    @abstractmethod
    def ready(self) -> bool:
        """Check if the adapter is properly configured and available."""
        ...

    @abstractmethod
    async def send_text(self, chat_id: str, text: str) -> dict[str, Any]:
        """Send a plain text message to the given chat/channel.

        Returns a dict with at minimum ``code`` (0 = success) and ``msg``.
        """
        ...

    @abstractmethod
    async def send_markdown(self, chat_id: str, content: str) -> dict[str, Any]:
        """Send a rich text (markdown-formatted) message.

        Returns a dict with at minimum ``code`` (0 = success) and ``msg``.
        """
        ...

    async def send(self, chat_id: str, content: str) -> dict[str, Any]:
        """Auto-detect and send plain text or markdown.

        Override in subclass for platform-specific detection logic.
        """
        return await self.send_text(chat_id, content)

    async def close(self) -> None:
        """Clean up adapter resources (optional)."""
        pass
