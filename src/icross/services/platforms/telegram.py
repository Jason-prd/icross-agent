"""Telegram platform adapter stub — placeholder for future implementation."""

from __future__ import annotations

import logging
import os
from typing import Any

from .base import BasePlatformAdapter, Platform

_logger = logging.getLogger(__name__)


class TelegramAdapter(BasePlatformAdapter):
    """Telegram 通知适配器（桩实现）。

    当前为桩实现，仅记录日志。需要时通过环境变量 TELEGRAM_BOT_TOKEN 配置。
    """

    def __init__(self, bot_token: str = ""):
        self._bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")

    @property
    def platform(self) -> Platform:
        return Platform.TELEGRAM

    @property
    def ready(self) -> bool:
        return bool(self._bot_token)

    async def send_text(self, chat_id: str, text: str) -> dict[str, Any]:
        _logger.info("Telegram stub: send_text to %s: %s", chat_id, text[:80])
        return {"code": -1, "msg": "Telegram adapter stub — not implemented"}

    async def send_markdown(self, chat_id: str, content: str) -> dict[str, Any]:
        _logger.info("Telegram stub: send_markdown to %s: %s", chat_id, content[:80])
        return {"code": -1, "msg": "Telegram adapter stub — not implemented"}
