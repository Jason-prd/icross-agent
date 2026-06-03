"""Notification dispatch service.

Supports multiple platforms through the adapter pattern.
Configured via environment variables or JSON config file.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from icross.services.platforms import (
    BasePlatformAdapter,
    Platform,
    get_platform_adapter,
)

_logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent.parent.parent.parent / "data" / "feishu_config.json"


class NotificationService:
    """通知调度器。管理多个平台的通知适配器，发送消息到已配置的目标。

    Usage:
        ns = NotificationService()
        await ns.send("标题", "内容", level="info")

    Configuration sources (优先级: 环境变量 > JSON 配置文件):
        FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_DOMAIN
        FEISHU_NOTIFY_CHAT_ID (default notification target)
    """

    def __init__(self):
        self._adapters: dict[Platform, BasePlatformAdapter] = {}
        self._channels: list[dict[str, str]] = []
        self._init_from_env()

    def _init_from_env(self) -> None:
        """Load configuration from environment and config file."""
        app_id = os.getenv("FEISHU_APP_ID", "")
        app_secret = os.getenv("FEISHU_APP_SECRET", "")
        domain = os.getenv("FEISHU_DOMAIN", "feishu")

        # Fallback to JSON config file
        if not app_id or not app_secret:
            config = _load_config_file()
            if config:
                app_id = app_id or config.get("app_id", "")
                app_secret = app_secret or config.get("app_secret", "")
                domain = config.get("domain", domain)

        feishu_chat_id = os.getenv("FEISHU_NOTIFY_CHAT_ID", "")
        if not feishu_chat_id:
            config = _load_config_file()
            if config:
                feishu_chat_id = config.get("chat_id", "")

        # Create Feishu adapter if credentials available
        if app_id and app_secret:
            feishu = get_platform_adapter(Platform.FEISHU, app_id=app_id, app_secret=app_secret, domain=domain)
            if feishu:
                self._adapters[Platform.FEISHU] = feishu

        if feishu_chat_id:
            self._channels.append({
                "id": feishu_chat_id,
                "name": os.getenv("FEISHU_NOTIFY_CHAT_NAME", "飞书通知群"),
                "type": "feishu",
                "platform": "feishu",
            })
            _logger.info("Notification channel configured: %s", feishu_chat_id)

        # Telegram adapter
        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if telegram_token:
            tg = get_platform_adapter(Platform.TELEGRAM, bot_token=telegram_token)
            if tg:
                self._adapters[Platform.TELEGRAM] = tg
                _logger.info("Telegram adapter configured")

        # DingTalk adapter
        dingtalk_webhook = os.getenv("DINGTALK_WEBHOOK", "")
        if dingtalk_webhook:
            dt = get_platform_adapter(Platform.DINGTALK, webhook=dingtalk_webhook)
            if dt:
                self._adapters[Platform.DINGTALK] = dt
                _logger.info("DingTalk adapter configured")

        if not self._channels:
            _logger.info("No notification channels configured; notifications disabled")

    # ---------------------------------------------------------------
    # Properties
    # ---------------------------------------------------------------

    @property
    def ready(self) -> bool:
        """Check if any notification channel is configured."""
        return bool(self._channels) and bool(self._adapters)

    @property
    def channels(self) -> list[dict[str, str]]:
        """List configured notification channels."""
        return list(self._channels)

    @property
    def adapters(self) -> dict[str, str]:
        """List available adapters by platform name."""
        return {p.value: a.__class__.__name__ for p, a in self._adapters.items()}

    # ---------------------------------------------------------------
    # Sending
    # ---------------------------------------------------------------

    async def send(
        self,
        title: str = "",
        content: str = "",
        level: str = "info",
        chat_id: str | None = None,
        platform: str | None = None,
    ) -> dict[str, Any]:
        """发送通知到指定或默认频道。

        Args:
            title: 通知标题（可选，会附加在 content 前）。
            content: 通知正文，支持 Markdown。
            level: 通知级别 (info/warning/error)。
            chat_id: 目标会话 ID。为 None 时发送到默认频道。
            platform: 目标平台（"feishu", "telegram" 等）。为 None 时使用第一个可用适配器。

        Returns:
            发送结果 dict。
        """
        if not self.ready:
            return {"success": False, "error": "未配置通知频道"}

        # Build message
        full_content = content
        if title:
            level_emoji = {"info": "", "warning": "⚠️ ", "error": "🚫 "}
            emoji = level_emoji.get(level, "")
            full_content = f"**{emoji}{title}**\n\n{content}"

        # Resolve adapter
        adapter: BasePlatformAdapter | None = None
        if platform:
            try:
                p = Platform(platform)
                adapter = self._adapters.get(p)
            except ValueError:
                return {"success": False, "error": f"未知平台: {platform}"}
        else:
            # Use first available adapter
            for p, a in self._adapters.items():
                adapter = a
                break

        if adapter is None:
            return {"success": False, "error": "未找到可用的通知适配器"}

        # Resolve target
        target = chat_id or (self._channels[0]["id"] if self._channels else "")
        if not target:
            return {"success": False, "error": "未指定通知目标 chat_id"}

        result = await adapter.send(target, full_content)
        success = result.get("code") == 0

        if success:
            _logger.info("Notification sent to %s (level=%s, platform=%s)", target, level, adapter.platform.value)
        else:
            _logger.warning("Notification failed to %s: %s", target, result.get("msg"))

        return {
            "success": success,
            "result": result,
            "channel": adapter.platform.value,
            "target": target,
        }

    async def send_to_channel(
        self,
        channel_type: str,
        chat_id: str,
        content: str,
        title: str = "",
        level: str = "info",
    ) -> dict[str, Any]:
        """Send notification to a specific channel type and chat_id.

        Args:
            channel_type: Platform name (e.g. "feishu", "telegram").
            chat_id: Target chat ID.
            content: Message content (supports markdown).
            title: Optional title.
            level: Notification level.

        Returns:
            Send result dict.
        """
        return await self.send(
            title=title,
            content=content,
            level=level,
            chat_id=chat_id,
            platform=channel_type,
        )

    async def close(self) -> None:
        """Clean up all adapters."""
        for adapter in self._adapters.values():
            await adapter.close()
        self._adapters.clear()


# Module-level singleton
_notification_service: NotificationService | None = None


def get_notification_service() -> NotificationService:
    """Get or create the notification service singleton."""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service


async def close_notification_service() -> None:
    """Clean up the notification service."""
    global _notification_service
    if _notification_service is not None:
        await _notification_service.close()
        _notification_service = None


def _load_config_file() -> dict[str, str]:
    """Load Feishu config from JSON file."""
    if not _CONFIG_PATH.exists():
        return {}
    try:
        with open(_CONFIG_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def reload_notification_service() -> NotificationService:
    """Reload the notification service from config (for post-registration update)."""
    global _notification_service
    _notification_service = NotificationService()
    _logger.info("Notification service reloaded from config")
    return _notification_service
