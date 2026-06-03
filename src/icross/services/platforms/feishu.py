"""Feishu platform adapter — wraps FeishuNotifier in the BasePlatformAdapter interface."""

from __future__ import annotations

import logging
from typing import Any

from .base import BasePlatformAdapter, Platform

_logger = logging.getLogger(__name__)

try:
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import (
        CreateMessageRequest,
        CreateMessageRequestBody,
    )
    from lark_oapi.core import AccessTokenType
    from lark_oapi.core.const import FEISHU_DOMAIN, LARK_DOMAIN

    FEISHU_AVAILABLE = True
except ImportError:
    FEISHU_AVAILABLE = False
    lark = None  # type: ignore[assignment]


def _build_onboard_client(app_id: str, app_secret: str, domain: str) -> Any:
    """Build a lark Client for the given credentials and domain."""
    sdk_domain = LARK_DOMAIN if domain == "lark" else FEISHU_DOMAIN
    return (
        lark.Client.builder()
        .app_id(app_id)
        .app_secret(app_secret)
        .domain(sdk_domain)
        .log_level(lark.LogLevel.WARNING)
        .build()
    )


class FeishuAdapter(BasePlatformAdapter):
    """飞书通知适配器。实现 BasePlatformAdapter 接口。

    Usage:
        adapter = FeishuAdapter(app_id="...", app_secret="...")
        await adapter.send("oc_xxx", "你好")
    """

    def __init__(
        self,
        app_id: str = "",
        app_secret: str = "",
        domain: str = "feishu",
    ):
        self._app_id = app_id
        self._app_secret = app_secret
        self._domain = domain
        self._client: Any = None

        if not FEISHU_AVAILABLE:
            _logger.warning("lark-oapi not installed; Feishu notifications disabled")
            return

        if not self._app_id or not self._app_secret:
            _logger.warning("FEISHU_APP_ID/FEISHU_APP_SECRET not set")
            return

        self._client = _build_onboard_client(self._app_id, self._app_secret, self._domain)

    # ---------------------------------------------------------------
    # BasePlatformAdapter interface
    # ---------------------------------------------------------------

    @property
    def platform(self) -> Platform:
        return Platform.FEISHU

    @property
    def ready(self) -> bool:
        return FEISHU_AVAILABLE and self._client is not None

    async def send_text(self, chat_id: str, text: str) -> dict[str, Any]:
        if not self.ready:
            return {"code": -1, "msg": "Feishu notifier not configured"}
        import json
        payload = json.dumps({"text": text}, ensure_ascii=False)
        return await self._do_send(chat_id, "text", payload)

    async def send_markdown(self, chat_id: str, content: str) -> dict[str, Any]:
        if not self.ready:
            return {"code": -1, "msg": "Feishu notifier not configured"}
        from icross.services.feishu_notifier import _build_markdown_post_payload
        payload = _build_markdown_post_payload(content)
        return await self._do_send(chat_id, "post", payload)

    async def send(self, chat_id: str, content: str) -> dict[str, Any]:
        """Auto-detect text format and send."""
        import re
        if re.search(r"[*#\[\(]", content):
            return await self.send_markdown(chat_id, content)
        return await self.send_text(chat_id, content)

    async def close(self) -> None:
        self._client = None

    # ---------------------------------------------------------------
    # Internal
    # ---------------------------------------------------------------

    async def _do_send(self, chat_id: str, msg_type: str, content: str) -> dict[str, Any]:
        import asyncio
        import json

        body = CreateMessageRequestBody.builder()
        body.receive_id(chat_id)
        body.msg_type(msg_type)
        body.content(content)
        request = CreateMessageRequest.builder()
        request.receive_id_type("chat_id")
        request.request_body(body.build())
        request.build()

        try:
            resp = await asyncio.to_thread(self._client.im.v1.message.create, request)
            raw = getattr(getattr(resp, "raw", None), "content", None)
            data = json.loads(raw) if raw else {}
            code = data.get("code", -1)
            if code != 0:
                _logger.warning("Feishu send failed: %s", data.get("msg", "unknown"))
            return data
        except Exception as e:
            _logger.error("Feishu send error: %s", e)
            return {"code": -1, "msg": str(e)}
