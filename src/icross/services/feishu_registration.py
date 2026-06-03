"""Feishu scan-to-create bot registration.

Splits the Hermes qr_register flow into async start/poll steps
so it can be driven by a web API instead of a blocking CLI call.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_logger = logging.getLogger(__name__)

_ONBOARD_ACCOUNTS_URLS = {
    "feishu": "https://accounts.feishu.cn",
    "lark": "https://accounts.larksuite.com",
}
_ONBOARD_OPEN_URLS = {
    "feishu": "https://open.feishu.cn",
    "lark": "https://open.larksuite.com",
}
_REGISTRATION_PATH = "/oauth/v1/app/registration"
_REQUEST_TIMEOUT_S = 10

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "data",
    "feishu_config.json",
)


@dataclass
class RegistrationState:
    """Tracks an in-progress QR registration."""
    device_code: str
    qr_url: str
    interval: int
    expire_in: int
    domain: str
    started_at: float


_registration: RegistrationState | None = None


def _accounts_base_url(domain: str) -> str:
    return _ONBOARD_ACCOUNTS_URLS.get(domain, _ONBOARD_ACCOUNTS_URLS["feishu"])


def _open_base_url(domain: str) -> str:
    return _ONBOARD_OPEN_URLS.get(domain, _ONBOARD_OPEN_URLS["feishu"])


def _post_form(url: str, body: dict[str, str]) -> dict[str, Any]:
    """POST form-encoded data, return parsed JSON (even on HTTP 4xx)."""
    data = urlencode(body).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urlopen(req, timeout=_REQUEST_TIMEOUT_S) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        body_bytes = exc.read()
        if body_bytes:
            try:
                return json.loads(body_bytes.decode("utf-8"))
            except (ValueError, json.JSONDecodeError):
                raise exc from None
        raise


def start_registration(domain: str = "feishu") -> dict[str, Any]:
    """Start the device-code registration flow.

    Returns:
        dict with device_code, qr_url, user_code, interval, expire_in, domain.
    """
    base_url = _accounts_base_url(domain)

    # Step 1: init — verify client_secret auth is supported
    res = _post_form(f"{base_url}{_REGISTRATION_PATH}", {"action": "init"})
    methods = res.get("supported_auth_methods") or []
    if "client_secret" not in methods:
        return {"error": f"不支持 client_secret 认证。支持的方法: {methods}"}

    # Step 2: begin — get device_code + qr_url
    res = _post_form(f"{base_url}{_REGISTRATION_PATH}", {
        "action": "begin",
        "archetype": "PersonalAgent",
        "auth_method": "client_secret",
        "request_user_info": "open_id",
    })
    device_code = res.get("device_code")
    if not device_code:
        return {"error": "飞书注册未返回 device_code"}

    qr_url = res.get("verification_uri_complete", "")
    if "?" in qr_url:
        qr_url += "&from=icross"
    else:
        qr_url += "?from=icross"

    global _registration
    _registration = RegistrationState(
        device_code=device_code,
        qr_url=qr_url,
        interval=res.get("interval") or 5,
        expire_in=res.get("expire_in") or 600,
        domain=domain,
        started_at=time.time(),
    )

    return {
        "device_code": device_code,
        "qr_url": qr_url,
        "user_code": res.get("user_code", ""),
        "interval": _registration.interval,
        "expire_in": _registration.expire_in,
        "domain": domain,
    }


def poll_registration() -> dict[str, Any]:
    """Poll the current registration for completion.

    Call repeatedly (every ~5s) until success or terminal state.

    Returns:
        On success: {"status": "done", "app_id": "...", "app_secret": "...", "domain": "...", "open_id": "..."}
        On pending: {"status": "pending"}
        On error:   {"status": "error", "error": "..."}
    """
    global _registration
    if _registration is None:
        return {"status": "error", "error": "没有正在进行的注册"}

    if time.time() - _registration.started_at > _registration.expire_in:
        _registration = None
        return {"status": "error", "error": "注册已超时，请重新开始"}

    base_url = _accounts_base_url(_registration.domain)
    current_domain = _registration.domain

    try:
        res = _post_form(f"{base_url}{_REGISTRATION_PATH}", {
            "action": "poll",
            "device_code": _registration.device_code,
            "tp": "ob_app",
        })
    except (URLError, OSError, json.JSONDecodeError) as e:
        return {"status": "pending", "error": str(e)}

    user_info = res.get("user_info") or {}
    tenant_brand = user_info.get("tenant_brand")
    if tenant_brand == "lark":
        current_domain = "lark"

    if res.get("client_id") and res.get("client_secret"):
        app_id = res["client_id"]
        app_secret = res["client_secret"]
        _registration = None

        # Probe bot (best-effort)
        bot_info = _probe_bot(app_id, app_secret, current_domain)

        return {
            "status": "done",
            "app_id": app_id,
            "app_secret": app_secret,
            "domain": current_domain,
            "open_id": user_info.get("open_id"),
            "bot_name": (bot_info or {}).get("bot_name"),
            "bot_open_id": (bot_info or {}).get("bot_open_id"),
        }

    error = res.get("error", "")
    if error == "access_denied":
        _registration = None
        return {"status": "error", "error": "用户拒绝了授权"}
    if error == "expired_token":
        _registration = None
        return {"status": "error", "error": "授权已过期，请重新开始"}

    return {"status": "pending"}


def save_config(config: dict[str, str]) -> dict[str, Any]:
    """Save Feishu credentials to JSON config file and update notification service.

    Expects: app_id, app_secret, domain, chat_id (optional).
    """
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)

    existing = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                existing = json.load(f)
            # Don't overwrite existing chat_id if not provided
            if "chat_id" not in config and "chat_id" in existing:
                config["chat_id"] = existing["chat_id"]
        except (json.JSONDecodeError, OSError):
            pass

    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    # Reload notification service to pick up new config
    _reload_notification_service(config)

    return {"success": True, "message": "飞书配置已保存"}


def _reload_notification_service(config: dict[str, str]) -> None:
    """Reload the notification service with new config."""
    try:
        from icross.services.notification import reload_notification_service
        reload_notification_service()
    except Exception as e:
        _logger.warning("Failed to reload notification service: %s", e)


def load_config() -> dict[str, str]:
    """Load saved Feishu config from JSON file."""
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _probe_bot(app_id: str, app_secret: str, domain: str) -> dict | None:
    """Verify bot connectivity via /open-apis/bot/v3/info."""
    base_url = _open_base_url(domain)
    try:
        # Get tenant access token
        token_data = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode("utf-8")
        token_req = Request(
            f"{base_url}/open-apis/auth/v3/tenant_access_token/internal",
            data=token_data,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(token_req, timeout=_REQUEST_TIMEOUT_S) as resp:
            token_res = json.loads(resp.read().decode("utf-8"))
        access_token = token_res.get("tenant_access_token")
        if not access_token:
            return None

        bot_req = Request(
            f"{base_url}/open-apis/bot/v3/info",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        )
        with urlopen(bot_req, timeout=_REQUEST_TIMEOUT_S) as resp:
            bot_res = json.loads(resp.read().decode("utf-8"))
        bot = bot_res.get("bot") or bot_res.get("data", {}).get("bot") or {}
        return {
            "bot_name": bot.get("app_name") or bot.get("bot_name"),
            "bot_open_id": bot.get("open_id"),
        }
    except Exception as e:
        _logger.debug("Bot probe failed: %s", e)
        return None
