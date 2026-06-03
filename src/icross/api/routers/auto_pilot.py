"""Auto-pilot configuration REST API (Phase C2).

Endpoints for managing per-shop auto-pilot settings:
enabled/disabled, cron schedule, push-to-Ozon toggle, pipeline defaults.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from icross.core.storage.ozon_data import AutoPilotConfigStorage

router = APIRouter(prefix="/auto-pilot", tags=["auto-pilot"])
config_store = AutoPilotConfigStorage()


@router.get("/config/{shop_id}")
async def get_auto_pilot_config(shop_id: str):
    """Get auto-pilot configuration for a shop."""
    config = await config_store.get_config(shop_id)
    return {"config": config}


@router.put("/config/{shop_id}")
async def save_auto_pilot_config(shop_id: str, body: dict):
    """Save auto-pilot configuration for a shop."""
    config = await config_store.save_config(shop_id, body)
    return {"success": True, "config": config}


@router.post("/config/{shop_id}/toggle")
async def toggle_auto_pilot(shop_id: str, body: dict):
    """Enable or disable auto-pilot for a shop."""
    enabled = body.get("enabled", False)
    config = await config_store.toggle(shop_id, enabled=enabled)
    return {"success": True, "enabled": enabled, "config": config}


@router.get("/configs")
async def list_auto_pilot_configs():
    """List all auto-pilot configurations."""
    configs = await config_store.list_configs()
    return {"configs": configs, "total": len(configs)}
