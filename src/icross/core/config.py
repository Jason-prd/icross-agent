"""Application configuration — demo mode detection and system status."""

import os

DEMO_MODE = os.getenv("ICROSS_DEMO_MODE", "").strip().lower() in ("1", "true", "yes", "demo")


def is_demo_mode() -> bool:
    """Check if the application is running in demo mode.

    Demo mode allows exploring the UI without real API keys by:
    - Providing mock provider and shop configurations
    - Returning mock data for dashboard and operations
    - Disabling the Agent chat (shows demo explanation instead)
    """
    return DEMO_MODE


def get_setup_status() -> dict:
    """Return current setup status for the onboarding wizard."""
    from icross.agents.llm.models import load_providers
    from icross.core.storage.ozon_data import ShopStorage

    providers = load_providers()
    configured_providers = [
        pid for pid, p in providers.items()
        if p.resolve_api_key()
    ]

    import asyncio
    try:
        loop = asyncio.get_event_loop()
        shops = loop.run_until_complete(ShopStorage().list_shops())
    except (RuntimeError, Exception):
        shops = []

    return {
        "demo_mode": is_demo_mode(),
        "has_llm": len(configured_providers) > 0,
        "has_shops": len(shops) > 0,
        "provider_count": len(configured_providers),
        "shop_count": len(shops),
        "configured_providers": configured_providers[:5],
    }
