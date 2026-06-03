"""Feishu notification client based on lark-oapi SDK.

Sends outbound messages (text/post) to Feishu chats.
Designed for one-way notification — no inbound event handling.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

_logger = logging.getLogger(__name__)

try:
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import (
        CreateMessageRequest,
        CreateMessageRequestBody,
    )
    from lark_oapi.core import AccessTokenType
    from lark_oapi.core.const import FEISHU_DOMAIN, LARK_DOMAIN
    from lark_oapi.core.model import BaseRequest

    FEISHU_AVAILABLE = True
except ImportError:
    FEISHU_AVAILABLE = False
    lark = None  # type: ignore[assignment]
    CreateMessageRequest = None  # type: ignore[assignment]
    CreateMessageRequestBody = None  # type: ignore[assignment]
    AccessTokenType = None  # type: ignore[assignment]
    FEISHU_DOMAIN = None  # type: ignore[assignment]
    LARK_DOMAIN = None  # type: ignore[assignment]
    BaseRequest = None  # type: ignore[assignment]


_MARKDOWN_HINT_RE = re.compile(r"[*#\[\(]")
_MARKDOWN_FENCE_OPEN_RE = re.compile(r"^```\w*")
_MARKDOWN_FENCE_CLOSE_RE = re.compile(r"^```")


def _build_markdown_post_payload(content: str) -> str:
    """Convert markdown text to Feishu post format payload."""
    rows = _build_markdown_post_rows(content)
    return json.dumps({"zh_cn": {"content": rows}}, ensure_ascii=False)


def _build_markdown_post_rows(content: str) -> list[list[dict[str, str]]]:
    """Build Feishu post rows, isolating fenced code blocks."""
    if not content:
        return [[{"tag": "md", "text": ""}]]
    if "```" not in content:
        return [[{"tag": "md", "text": content}]]

    rows: list[list[dict[str, str]]] = []
    current: list[str] = []
    in_code_block = False

    def _flush_current() -> None:
        nonlocal current
        if not current:
            return
        segment = "\n".join(current)
        if segment.strip():
            rows.append([{"tag": "md", "text": segment}])
        current = []

    for raw_line in content.splitlines():
        stripped_line = raw_line.strip()
        is_fence = bool(
            _MARKDOWN_FENCE_CLOSE_RE.match(stripped_line)
            if in_code_block
            else _MARKDOWN_FENCE_OPEN_RE.match(stripped_line)
        )

        if is_fence:
            if not in_code_block:
                _flush_current()
            current.append(raw_line)
            in_code_block = not in_code_block
            if not in_code_block:
                _flush_current()
            continue

        current.append(raw_line)

    _flush_current()
    return rows or [[{"tag": "md", "text": content}]]


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


class FeishuNotifier:
    """飞书消息通知客户端。基于 lark-oapi SDK，仅支持出站通知。

    Usage:
        notifier = FeishuNotifier(app_id="...", app_secret="...")
        await notifier.send_text("oc_xxx", "你好")
        await notifier.send_markdown("oc_xxx", "**粗体** 内容")
    """

    def __init__(
        self,
        app_id: str = "",
        app_secret: str = "",
        domain: str = "",
    ):
        self._app_id = app_id or os.getenv("FEISHU_APP_ID", "")
        self._app_secret = app_secret or os.getenv("FEISHU_APP_SECRET", "")
        self._domain = domain or os.getenv("FEISHU_DOMAIN", "feishu")
        self._client: Any = None

        if not FEISHU_AVAILABLE:
            _logger.warning("lark-oapi not installed; Feishu notifications disabled")
            return

        if not self._app_id or not self._app_secret:
            _logger.warning("FEISHU_APP_ID or FEISHU_APP_SECRET not set")
            return

        self._client = _build_onboard_client(self._app_id, self._app_secret, self._domain)

    @property
    def ready(self) -> bool:
        """Check if the notifier is properly configured."""
        return FEISHU_AVAILABLE and self._client is not None

    async def send_text(self, chat_id: str, text: str) -> dict[str, Any]:
        """发送纯文本消息到指定会话。

        Args:
            chat_id: 飞书群聊或会话的 chat_id (oc_xxx)。
            text: 消息文本内容。

        Returns:
            dict with code, msg, data.
        """
        if not self.ready:
            return {"code": -1, "msg": "Feishu notifier not configured"}

        payload = json.dumps({"text": text}, ensure_ascii=False)
        return await self._do_send(chat_id, "text", payload)

    async def send_markdown(self, chat_id: str, content: str) -> dict[str, Any]:
        """发送富文本消息（Markdown → Feishu post 格式）。

        Args:
            chat_id: 飞书群聊或会话的 chat_id (oc_xxx)。
            content: 支持基础 Markdown 的文本（粗体、标题、列表、代码块）。

        Returns:
            dict with code, msg, data.
        """
        if not self.ready:
            return {"code": -1, "msg": "Feishu notifier not configured"}

        payload = _build_markdown_post_payload(content)
        return await self._do_send(chat_id, "post", payload)

    async def send(self, chat_id: str, content: str) -> dict[str, Any]:
        """自动检测文本格式并发送（纯文本或 markdown）。

        Args:
            chat_id: 飞书群聊或会话的 chat_id (oc_xxx)。
            content: 消息内容，包含 markdown 标记时自动使用富文本格式。

        Returns:
            dict with code, msg, data.
        """
        if _MARKDOWN_HINT_RE.search(content):
            return await self.send_markdown(chat_id, content)
        return await self.send_text(chat_id, content)

    async def _do_send(self, chat_id: str, msg_type: str, content: str) -> dict[str, Any]:
        """Execute the message send via lark-oapi SDK."""
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

    async def close(self) -> None:
        """Clean up the lark client (no-op for now, for compatibility)."""
        self._client = None
