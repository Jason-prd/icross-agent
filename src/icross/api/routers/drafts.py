"""REST API endpoints for draft review workflow."""

import asyncio
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from icross.core.storage.ozon_data import DraftStorage

router = APIRouter()
draft_storage = DraftStorage()


class DraftCreate(BaseModel):
    shop_id: str
    draft_type: str = "listing"
    title: str = ""
    description: str = ""
    price: float = 0
    old_price: float = 0
    stock: int = 0
    offer_id: str = ""
    source_url: str = ""
    images: list[str] = []
    description_category_id: int = 0
    type_id: int = 0
    category_attributes: list[dict] | None = None
    attrs: dict = {}


class DraftApprove(BaseModel):
    reviewed_by: str = ""


class DraftReject(BaseModel):
    reject_reason: str
    reviewed_by: str = ""


@router.post("/drafts/create")
async def create_draft(body: DraftCreate):
    """Create a new product draft."""
    if body.price < 0:
        return {"success": False, "error": "价格不能为负数"}
    if body.draft_type not in ("listing", "price_update", "stock_update"):
        return {"success": False, "error": "draft_type 必须是 listing/price_update/stock_update 之一"}

    # Merge category info into attrs
    merged_attrs = dict(body.attrs)
    if body.description_category_id:
        merged_attrs["description_category_id"] = body.description_category_id
    if body.type_id:
        merged_attrs["type_id"] = body.type_id
    if body.category_attributes:
        merged_attrs["category_attributes"] = body.category_attributes

    result = await draft_storage.create_draft(
        shop_id=body.shop_id,
        draft_type=body.draft_type,
        title=body.title,
        description=body.description,
        price=body.price,
        old_price=body.old_price,
        stock=body.stock,
        offer_id=body.offer_id,
        source_url=body.source_url,
        images=body.images,
        attrs=merged_attrs,
    )
    return {"success": True, "draft_id": result["id"], "status": result["status"]}


@router.get("/drafts")
async def list_drafts(
    shop_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """List product drafts with optional filters."""
    return await draft_storage.list_drafts(
        shop_id=shop_id, status=status, limit=limit, offset=offset
    )


@router.get("/drafts/{draft_id}")
async def get_draft(draft_id: str):
    """Get a draft by ID."""
    draft = await draft_storage.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return {"draft": draft}


@router.post("/drafts/{draft_id}/approve")
async def approve_draft(draft_id: str, body: DraftApprove = DraftApprove(), reviewed_by: str = ""):
    """Approve a draft. For listing-type drafts, publishes to Ozon automatically."""
    reviewer = reviewed_by or body.reviewed_by or "system"
    draft = await draft_storage.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft.get("status") != "pending":
        raise HTTPException(status_code=400, detail=f"Draft is already {draft['status']}")

    # Approve in storage first
    result = await draft_storage.approve_draft(draft_id, reviewed_by=reviewer)
    if not result:
        raise HTTPException(status_code=404, detail="Draft not found")

    # For listing-type drafts, publish to Ozon automatically
    publish_result = None
    if draft.get("draft_type") == "listing":
        publish_result = await _publish_draft_to_ozon(draft)

    return {
        "success": True,
        "draft": result,
        "publish_result": publish_result,
    }


async def _publish_draft_to_ozon(draft: dict) -> dict:
    """Publish an approved listing draft to Ozon.

    Uploads images to Ozon CDN before creating the product so that
    all image URLs are hosted on Ozon's infrastructure.
    """
    from icross.services.ozon import get_ozon_client

    shop_id = draft.get("shop_id", "")
    name = draft.get("title", "")
    offer_id = draft.get("offer_id", "") or f"auto_{draft['id']}"
    price = draft.get("price", 0)
    description = draft.get("description", "")
    images = draft.get("images", [])
    old_price = draft.get("old_price", 0) or None

    # Extract category and attributes from draft attrs
    attrs = draft.get("attrs", {}) or {}
    vat = attrs.get("vat", "VAT_20")
    description_category_id = attrs.get("description_category_id", 0)
    type_id = attrs.get("type_id")
    category_attributes = attrs.get("category_attributes")  # list of {id, values}

    if not name or price <= 0:
        return {"success": False, "error": "商品名称或价格无效"}

    try:
        client = get_ozon_client()

        # Upload images to Ozon CDN
        ozon_image_urls: list[str] = []
        for img_url in (images or []):
            if isinstance(img_url, dict):
                url = img_url.get("url", "")
            elif isinstance(img_url, str):
                url = img_url
            else:
                continue
            if not url:
                continue
            # Only upload external URLs (non-Ozon)
            if "cdn.ozon" not in url and "cdn-o" not in url:
                upload_result = await client.upload_image(shop_id, url)
                if upload_result and upload_result.get("url") and "_error" not in upload_result:
                    ozon_image_urls.append(upload_result["url"])
                else:
                    ozon_image_urls.append(url)
            else:
                ozon_image_urls.append(url)

        result = await client.create_product(
            shop_id=shop_id,
            name=name,
            offer_id=offer_id,
            price=price,
            vat=vat,
            description=description,
            images=ozon_image_urls or images,
            old_price=old_price,
            description_category_id=description_category_id,
            type_id=type_id,
            attributes=category_attributes,
        )
        # Update draft with publish info
        await draft_storage.update_draft_publish(
            draft["id"],
            published=True,
            ozon_task_id=result.get("task_id"),
        )
        return {
            "success": True,
            "task_id": result.get("task_id"),
            "message": "商品已提交到 Ozon 处理队列，请稍后查看上架状态",
        }
    except Exception as e:
        await draft_storage.update_draft_publish(
            draft["id"],
            published=False,
            publish_error=str(e),
        )
        return {"success": False, "error": str(e)}


@router.post("/drafts/{draft_id}/republish")
async def republish_draft(draft_id: str):
    """Re-publish an already-approved draft (retry after publish failure)."""
    draft = await draft_storage.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft.get("status") != "approved":
        raise HTTPException(status_code=400, detail="Only approved drafts can be re-published")

    publish_result = await _publish_draft_to_ozon(draft)
    return {
        "success": publish_result.get("success", False),
        "draft_id": draft_id,
        "publish_result": publish_result,
    }


@router.post("/drafts/{draft_id}/reject")
async def reject_draft(draft_id: str, body: DraftReject, reviewed_by: str = ""):
    """Reject a draft with a reason."""
    reviewer = reviewed_by or body.reviewed_by or "system"
    result = await draft_storage.reject_draft(
        draft_id, body.reject_reason, reviewed_by=reviewer
    )
    if not result:
        raise HTTPException(status_code=404, detail="Draft not found")
    return {"success": True, "draft": result}


@router.delete("/drafts/{draft_id}")
async def delete_draft(draft_id: str):
    """Delete a draft."""
    await draft_storage.delete_draft(draft_id)
    return {"success": True, "draft_id": draft_id}
