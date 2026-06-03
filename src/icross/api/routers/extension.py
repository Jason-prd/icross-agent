"""REST API endpoints for the browser extension.

These endpoints are called by the iCross Browser Extension to submit
captured product data from 1688 / 拼多多 / 淘宝 and retrieve results.
"""

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from icross.core.storage.sourcing_platform import SourcingCaptureStorage
from icross.services.extension_processor import ExtensionCaptureProcessor

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/extension", tags=["extension"])
capture_storage = SourcingCaptureStorage()
processor = ExtensionCaptureProcessor()


# ── Request / Response models ────────────────────────────────────────


class CaptureRequest(BaseModel):
    """Product data captured by the browser extension."""

    platform: str  # "1688" | "pinduoduo" | "taobao"
    product_url: str
    shop_id: str = ""
    title: str = ""
    price: float | None = None
    original_price: float | None = None
    brand: str = ""
    category: str = ""
    description: str = ""
    images: list[str] = []
    attributes: dict[str, str] = {}
    skus: list[dict] = []
    stock: int = 0
    seller_name: str = ""
    seller_url: str = ""
    specs: list[dict] = []  # Product specification table [{name, value}]
    raw_html: str = ""  # Raw HTML snippet for fallback LLM parsing


class ProcessRequest(BaseModel):
    """Options for processing a captured product."""

    auto_generate_listing: bool = True
    auto_calculate_price: bool = True
    auto_create_draft: bool = False


# ── Endpoints ────────────────────────────────────────────────────────


@router.post("/capture")
async def capture_product(req: CaptureRequest):
    """Receive a product capture from the browser extension.

    Stores the raw capture data and optionally starts processing.
    Returns the capture record with an ID for status tracking.
    """
    if req.platform not in ("1688", "pinduoduo", "taobao"):
        raise HTTPException(status_code=400, detail=f"Unsupported platform: {req.platform}")

    raw_data = req.model_dump(exclude={"platform", "product_url", "shop_id"})
    # Remove None values for cleaner storage
    raw_data = {k: v for k, v in raw_data.items() if v is not None}

    record = await processor.receive_capture(
        platform=req.platform,
        product_url=req.product_url,
        raw_data=raw_data,
        shop_id=req.shop_id,
    )
    return {"success": True, "capture": record}


@router.get("/captures")
async def list_captures(
    platform: str | None = Query(None),
    status: str | None = Query(None),
    shop_id: str | None = Query(None),
    limit: int = Query(20, le=100),
):
    """List product captures, optionally filtered."""
    captures = capture_storage.list_captures(
        platform=platform,
        status=status,
        shop_id=shop_id,
        limit=limit,
    )
    return {"captures": captures, "total": len(captures)}


@router.get("/captures/{capture_id}")
async def get_capture(capture_id: str):
    """Get details of a specific capture."""
    record = capture_storage.get_capture(capture_id)
    if not record:
        raise HTTPException(status_code=404, detail="Capture not found")
    return record


@router.post("/captures/{capture_id}/process")
async def process_capture(capture_id: str, req: ProcessRequest = ProcessRequest()):
    """Process a captured product through the iCross pipeline.

    Steps: parse → (optional) generate listing → (optional) price → (optional) draft
    """
    result = await processor.process_capture(
        capture_id=capture_id,
        auto_generate_listing=req.auto_generate_listing,
        auto_calculate_price=req.auto_calculate_price,
        auto_create_draft=req.auto_create_draft,
    )
    return result


@router.delete("/captures/{capture_id}")
async def delete_capture(capture_id: str):
    """Delete a capture record."""
    if capture_storage.delete_capture(capture_id):
        return {"success": True}
    raise HTTPException(status_code=404, detail="Capture not found")


@router.get("/stats")
async def capture_stats():
    """Get capture statistics grouped by status."""
    return {"stats": capture_storage.count_by_status()}
