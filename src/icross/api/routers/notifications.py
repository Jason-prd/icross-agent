"""Notification REST API (Phase 8).

Endpoints for sending, listing, and registering notification channels.
Supports delivery routing via ``"platform:chat_id"`` format.
"""

import logging
from fastapi import APIRouter

from icross.services.notification import get_notification_service
from icross.services.platforms.routing import DeliveryTarget

_logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.post("/send")
async def send_notification(
    title: str = "",
    content: str = "",
    level: str = "info",
    chat_id: str | None = None,
    platform: str | None = None,
    target: str | None = None,
):
    """发送通知到指定频道。

    Args:
        title: 通知标题。
        content: 通知正文（支持 Markdown）。
        level: 级别 (info/warning/error)。
        chat_id: 目标会话 ID，不传则发到默认频道。
        platform: 目标平台 ("feishu", "telegram" 等)。
        target: 目标地址 "platform:chat_id" 格式（优先级高于 platform+chat_id）。
    """
    ns = get_notification_service()

    # Parse target string if provided (highest priority)
    if target:
        parsed = DeliveryTarget.parse(target)
        if parsed and parsed.is_valid():
            return await ns.send(
                title=title, content=content, level=level,
                chat_id=parsed.chat_id, platform=parsed.platform,
            )
        return {"success": False, "error": f"无效的目标地址: {target}"}

    return await ns.send(
        title=title, content=content, level=level,
        chat_id=chat_id, platform=platform,
    )


@router.get("/channels")
async def list_channels():
    """查看已配置的通知频道和可用平台列表。"""
    from icross.services.platforms import list_platforms
    ns = get_notification_service()
    return {
        "ready": ns.ready,
        "channels": ns.channels,
        "adapters": ns.adapters,
        "available_platforms": list_platforms(),
    }


# ============================================================
# Feishu QR Registration
# ============================================================


@router.post("/register/start")
async def register_start():
    """开始飞书机器人注册流程（scan-to-create）。

    返回 QR 码 URL，用户扫码后在飞书确认，即可自动创建 Bot 应用。
    """
    from icross.services.feishu_registration import start_registration
    return start_registration()


@router.post("/register/poll")
async def register_poll():
    """轮询飞书注册状态。

    客户端应每 3-5 秒调用一次，直到返回 status=done 或 status=error。
    """
    from icross.services.feishu_registration import poll_registration
    return poll_registration()


@router.post("/register/config")
async def register_config():
    """获取当前已保存的飞书配置状态。"""
    from icross.services.feishu_registration import load_config
    config = load_config()
    ns = get_notification_service()
    return {
        "configured": bool(config.get("app_id") and config.get("app_secret")),
        "has_chat_id": bool(config.get("chat_id")),
        "ready": ns.ready,
        "channels": ns.channels,
    }


@router.post("/register/save")
async def register_save(
    app_id: str = "",
    app_secret: str = "",
    domain: str = "feishu",
    chat_id: str = "",
    bot_name: str = "",
):
    """保存飞书配置到 JSON 文件。

    注册完成后或手动输入凭据后调用。
    """
    from icross.services.feishu_registration import save_config
    config = {
        "app_id": app_id,
        "app_secret": app_secret,
        "domain": domain,
        "chat_id": chat_id or "",
        "bot_name": bot_name or "",
    }
    result = save_config(config)
    # Reload notification service
    from icross.services.notification import reload_notification_service
    reload_notification_service()
    return result
