"""DingTalk platform adapter stub — placeholder for future implementation."""

from __future__ import annotations

import logging
import os
from typing import Any

from .base import BasePlatformAdapter, Platform

_logger = logging.getLogger(__name__)


class DingTalkAdapter(BasePlatformAdapter):
    """钉钉通知适配器（桩实现）。

    当前为桩实现，仅记录日志。需要时通过环境变量 DINGTALK_WEBHOOK 配置。
    """

    def __init__(self, webhook: str = ""):
        self._webhook = webhook or os.getenv("DINGTALK_WEBHOOK", "")

    @property
    def platform(self) -> Platform:
        return Platform.DINGTALK

    @property
    def ready(self) -> bool:
        return bool(self._webhook)

    async def send_text(self, chat_id: str, text: str) -> dict[str, Any]:
        _logger.info("DingTalk stub: send_text to %s: %s", chat_id, text[:80])
        return {"code": -1, "msg": "DingTalk adapter stub — not implemented"}

    async def send_markdown(self, chat_id: str, content: str) -> dict[str, Any]:
        _logger.info("DingTalk stub: send_markdown to %s: %s", chat_id, content[:80])
        return {"code": -1, "msg": "DingTalk adapter stub — not implemented"}
