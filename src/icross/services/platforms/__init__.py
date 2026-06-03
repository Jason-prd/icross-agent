"""Platform adapter factory — get a platform adapter by Platform enum.

Usage:
    from icross.services.platforms import Platform, get_platform_adapter

    adapter = get_platform_adapter(Platform.FEISHU, app_id="...", app_secret="...")
    await adapter.send("oc_xxx", "Hello")
"""

from __future__ import annotations

import logging
from typing import Any

from .base import BasePlatformAdapter, Platform

_logger = logging.getLogger(__name__)

_ADAPTER_REGISTRY: dict[Platform, type[BasePlatformAdapter]] = {}


def register_platform_adapter(platform: Platform, adapter_cls: type[BasePlatformAdapter]) -> None:
    """Register a platform adapter class for the given platform."""
    _ADAPTER_REGISTRY[platform] = adapter_cls
    _logger.debug("Registered platform adapter: %s -> %s", platform.value, adapter_cls.__name__)


def get_platform_adapter(platform: Platform, **kwargs: Any) -> BasePlatformAdapter | None:
    """Get a platform adapter instance for the given platform.

    Args:
        platform: The Platform enum value.
        **kwargs: Adapter-specific initialization arguments (e.g. app_id, app_secret).

    Returns:
        An adapter instance, or None if the platform is not registered.
    """
    cls = _ADAPTER_REGISTRY.get(platform)
    if cls is None:
        _logger.warning("No adapter registered for platform: %s", platform.value)
        return None
    try:
        return cls(**kwargs)
    except Exception as e:
        _logger.error("Failed to create adapter for %s: %s", platform.value, e)
        return None


def list_platforms() -> dict[str, dict[str, Any]]:
    """List all registered platforms and their status."""
    return {
        p.value: {"name": p.display_name(), "available": p in _ADAPTER_REGISTRY}
        for p in Platform
    }


# Import and register built-in adapters
from .feishu import FeishuAdapter  # noqa: E402
from .telegram import TelegramAdapter  # noqa: E402
from .dingtalk import DingTalkAdapter  # noqa: E402

register_platform_adapter(Platform.FEISHU, FeishuAdapter)
register_platform_adapter(Platform.TELEGRAM, TelegramAdapter)
register_platform_adapter(Platform.DINGTALK, DingTalkAdapter)


__all__ = [
    "BasePlatformAdapter",
    "Platform",
    "get_platform_adapter",
    "list_platforms",
    "register_platform_adapter",
]
