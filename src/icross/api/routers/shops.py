"""REST API endpoints for shop management."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from icross.core.storage.ozon_data import ShopStorage

router = APIRouter()
shop_storage = ShopStorage()


class ShopCreate(BaseModel):
    shop_id: str
    name: str = ""
    client_id: str = ""
    api_key: str = ""
    token: str = ""
    sync_days: int = 90


class ShopUpdate(BaseModel):
    name: str | None = None
    client_id: str | None = None
    api_key: str | None = None
    token: str | None = None
    status: str | None = None
    sync_days: int | None = None


@router.get("/shops")
async def list_shops():
    """List all shops."""
    return {"shops": await shop_storage.list_shops()}


@router.post("/shops")
async def create_shop(shop: ShopCreate):
    """Add a new shop."""
    existing = await shop_storage.get_shop(shop.shop_id)
    if existing:
        raise HTTPException(status_code=400, detail="Shop already exists")

    result = await shop_storage.add_shop(
        shop_id=shop.shop_id,
        name=shop.name,
        client_id=shop.client_id,
        api_key=shop.api_key,
        token=shop.token,
        sync_days=shop.sync_days,
    )
    return {"shop": result}


@router.get("/shops/{shop_id}")
async def get_shop(shop_id: str):
    """Get shop details."""
    shop = await shop_storage.get_shop(shop_id)
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    return {"shop": shop}


@router.patch("/shops/{shop_id}")
async def update_shop(shop_id: str, update: ShopUpdate):
    """Update shop."""
    shop = await shop_storage.get_shop(shop_id)
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    result = await shop_storage.update_shop(shop_id, **update_data)
    return {"shop": result}


@router.delete("/shops/{shop_id}")
async def delete_shop(shop_id: str):
    """Delete a shop."""
    shop = await shop_storage.get_shop(shop_id)
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    await shop_storage.delete_shop(shop_id)
    return {"success": True, "shop_id": shop_id}


@router.post("/shops/{shop_id}/authenticate")
async def authenticate_shop(shop_id: str):
    """Verify shop credentials by calling Ozon API."""
    result = await shop_storage.authenticate_shop(shop_id)
    if result is None:
        raise HTTPException(status_code=401, detail="Authentication failed")
    return {"success": True, "shop_id": shop_id, "info": result}