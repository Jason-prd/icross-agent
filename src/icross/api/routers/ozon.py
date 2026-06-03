"""REST API endpoints for Ozon operations (orders, analytics, warehouses)."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from icross.core.storage.ozon_data import (
    OrderStorage, AnalyticsStorage, WarehouseStorage,
    SellerInfoStorage, SyncLogStorage, ShopStorage
)

router = APIRouter()
order_storage = OrderStorage()
analytics_storage = AnalyticsStorage()
warehouse_storage = WarehouseStorage()
seller_info_storage = SellerInfoStorage()
sync_log_storage = SyncLogStorage()
shop_storage = ShopStorage()


# ============ Orders ============

@router.get("/orders")
async def list_orders(
    shop_id: str = Query(default=...),
    status: str | None = None,
    limit: int = Query(default=100),
    offset: int = Query(default=0),
):
    """List orders for a shop."""
    return await order_storage.list_orders(shop_id, status, limit, offset)


@router.get("/orders/{order_id}")
async def get_order(order_id: str):
    """Get order details."""
    order = await order_storage.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"order": order}


@router.post("/orders/sync")
async def sync_orders(shop_id: str = Query(default=...), days: int = Query(default=0)):
    """Sync orders from Ozon API. Uses shop's sync_days config when days is 0."""
    if days <= 0:
        shop = await shop_storage.get_shop(shop_id)
        days = shop.get("sync_days", 90) if shop else 90
    result = await order_storage.sync_from_ozon(shop_id, days)
    return {"success": True, "shop_id": shop_id, **result}


# ============ Analytics ============

@router.get("/analytics/stocks")
async def get_stocks_analytics(
    shop_id: str = Query(default=...),
    from_date: str | None = None,
    to_date: str | None = None,
):
    """Get stock analytics history."""
    return await analytics_storage.list_analytics(shop_id, "stocks", from_date, to_date)


@router.post("/analytics/stocks/sync")
async def sync_stocks_analytics(shop_id: str = Query(default=...)):
    """Sync stock analytics from Ozon."""
    result = await analytics_storage.sync_stocks_from_ozon(shop_id)
    return {"success": True, "shop_id": shop_id, **result}


# ============ Warehouses ============

@router.get("/warehouses")
async def list_warehouses(shop_id: str = Query(default=...)):
    """List warehouses for a shop."""
    return {"warehouses": await warehouse_storage.list_warehouses(shop_id)}


@router.post("/warehouses/sync")
async def sync_warehouses(shop_id: str = Query(default=...)):
    """Sync warehouses from Ozon."""
    result = await warehouse_storage.sync_from_ozon(shop_id)
    return {"success": True, "shop_id": shop_id, **result}


# ============ Seller Info ============

@router.get("/seller-info/{shop_id}")
async def get_seller_info(shop_id: str):
    """Get seller info (cached)."""
    info = await seller_info_storage.get_seller_info(shop_id)
    if not info:
        raise HTTPException(status_code=404, detail="Seller info not found")
    return {"seller_info": info}


@router.post("/seller-info/{shop_id}/sync")
async def sync_seller_info(shop_id: str):
    """Sync seller info from Ozon."""
    result = await seller_info_storage.sync_from_ozon(shop_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Sync failed"))
    return {"success": True, "shop_id": shop_id, **result}


# ============ Sync Logs ============

@router.get("/sync-logs")
async def get_sync_logs(
    shop_id: str | None = None,
    operation: str | None = None,
    limit: int = Query(default=50),
):
    """Get sync operation history."""
    return {"logs": await sync_log_storage.get_logs(shop_id, operation, limit)}


# ============ FBO / FBS Orders (live from Ozon API) ============

from icross.services.ozon import get_ozon_client


# Status group priority for sorting (lower = earlier)
STATUS_GROUP_PRIORITY: dict[str, int] = {
    "pending": 0,
    "ready_to_ship": 1,
    "delivering": 2,
    "completed": 3,
    "cancelled": 4,
}

# FBS status → group mapping
FBS_STATUS_GROUP: dict[str, str] = {
    "awaiting_registration": "pending",
    "awaiting_approve": "pending",
    "awaiting_packaging": "pending",
    "awaiting_deliver": "ready_to_ship",
    "delivering": "delivering",
    "delivered": "completed",
    "cancelled": "cancelled",
}

# FBO status → group mapping
FBO_STATUS_GROUP: dict[str, str] = {
    "not_accepted": "pending",
    "accepted": "pending",
    "awaiting_deliver": "pending",
    "delivering": "delivering",
    "delivered": "completed",
    "cancelled": "cancelled",
}


def _annotate_orders(items: list[dict], status_group_map: dict[str, str], order_type: str) -> list[dict]:
    """Add status_group and order_type to each order item, sorted by priority."""
    for item in items:
        item["order_type"] = order_type
        status = item.get("status", "")
        item["status_group"] = status_group_map.get(status, "pending")
    items.sort(key=lambda o: (
        STATUS_GROUP_PRIORITY.get(o.get("status_group", "pending"), 0),
        o.get("created_at", "") or "",
    ))
    return items


@router.get("/fbo/orders")
async def list_fbo_orders(
    shop_id: str = Query(default=...),
    limit: int = Query(default=50),
    offset: int = Query(default=0),
    since: str = "",
    status: str = "",
):
    """List FBO orders live from Ozon API, with status_group annotation."""
    client = get_ozon_client()
    result = await client.get_order_list(
        shop_id=shop_id, limit=limit, offset=offset,
        since=since, status=status,
    )
    items = result.get("items") or []
    result["items"] = _annotate_orders(items, FBO_STATUS_GROUP, "FBO")
    return result


@router.get("/fbs/orders")
async def list_fbs_orders(
    shop_id: str = Query(default=...),
    limit: int = Query(default=50),
    offset: int = Query(default=0),
    since: str = "",
    status: str = "",
):
    """List FBS orders live from Ozon API, with status_group annotation."""
    client = get_ozon_client()
    result = await client.list_fbs_postings(
        shop_id=shop_id, limit=limit, offset=offset,
        since=since, status=status,
    )
    items = result.get("items") or []
    result["items"] = _annotate_orders(items, FBS_STATUS_GROUP, "FBS")
    return result


@router.get("/all-orders")
async def list_all_orders(
    shop_id: str = Query(default=...),
    limit: int = Query(default=50),
    offset: int = Query(default=0),
    since: str = "",
    status: str = "",
):
    """List ALL orders (FBO + FBS) live from Ozon API, merged with type annotation."""
    from datetime import datetime, timedelta
    client = get_ozon_client()

    fbo_result = await client.get_order_list(
        shop_id=shop_id, limit=limit, offset=offset,
        since=since, status=status,
    )
    fbs_result = await client.list_fbs_postings(
        shop_id=shop_id, limit=limit, offset=offset,
        since=since, status=status,
    )

    merged = {"items": [], "total": 0, "shop_id": shop_id}
    fbo_items = fbo_result.get("items") or []
    fbs_items = fbs_result.get("items") or []
    _annotate_orders(fbo_items, FBO_STATUS_GROUP, "FBO")
    _annotate_orders(fbs_items, FBS_STATUS_GROUP, "FBS")
    merged["items"] = fbo_items + fbs_items
    merged["total"] = len(merged["items"])
    return merged


@router.get("/order-detail")
async def get_order_detail_by_posting(
    shop_id: str = Query(default=...),
    posting_number: str = Query(default=...),
):
    """Get order detail by posting_number from Ozon API.

    Uses the FBS get endpoint which works for both FBO and FBS orders.
    Falls back to FBO list fetch if FBS get fails.
    """
    from icross.services.ozon.client import OzonClient

    client = OzonClient()
    try:
        data = await client.get_fbs_posting(shop_id, posting_number)
    except Exception:
        # Fallback: search FBO list for this posting
        orders_resp = await client.get_order_list(shop_id, limit=50, since="")
        orders = orders_resp if isinstance(orders_resp, list) else (orders_resp.get("items") or orders_resp.get("orders") or [])
        data = None
        for o in orders:
            if o.get("posting_number") == posting_number or str(o.get("posting_id")) == posting_number:
                data = o
                break
    if not data:
        raise HTTPException(status_code=404, detail="Order not found")

    # Enrich products with images from product info API
    products = data.get("products") or []
    if products:
        offer_ids = [p.get("offer_id") for p in products if p.get("offer_id")]
        if offer_ids:
            try:
                info = await client.get_product_info_list(shop_id, offer_ids=offer_ids)
                items = info.get("items") or []
                img_map: dict[str, list[str]] = {}
                for item in items:
                    oid = item.get("offer_id")
                    if oid:
                        images = item.get("images") or []
                        primary = item.get("primary_image")
                        img_map[oid] = images or ([primary] if primary else [])
                for p in products:
                    oid = p.get("offer_id")
                    if oid and oid in img_map:
                        p["images"] = img_map[oid]
            except Exception:
                pass  # non-critical — images are optional enrichment

    return {"order": data}


@router.get("/fbs/order-info")
async def get_fbs_order_info(
    shop_id: str = Query(default=...),
    posting_id: str = Query(default=...),
):
    """Get FBS order detail from Ozon API."""
    client = get_ozon_client()
    result = await client.get_fbs_posting(shop_id, posting_id)
    return result


class FbsShipRequest(BaseModel):
    shop_id: str
    posting_ids: list[str]


@router.post("/fbs/ship")
async def ship_fbs_orders(req: FbsShipRequest):
    """Ship FBS orders (confirm packing)."""
    client = get_ozon_client()
    result = await client.fbs_ship_postings(req.shop_id, req.posting_ids)
    return result


@router.post("/fbs/await-delivery")
async def await_delivery_fbs(req: FbsShipRequest):
    """Mark FBS orders as awaiting delivery."""
    client = get_ozon_client()
    result = await client.fbs_awaiting_delivery(req.shop_id, req.posting_ids)
    return result


class FbsLabelRequest(BaseModel):
    shop_id: str
    posting_numbers: list[str]


@router.post("/fbs/package-label")
async def fbs_package_label(req: FbsLabelRequest):
    """Generate PDF labels for FBS postings (max 20, must be in ``awaiting_deliver`` status)."""
    client = get_ozon_client()
    result = await client.get_package_label(req.shop_id, req.posting_numbers)

    from fastapi.responses import StreamingResponse
    import base64, io

    pdf_bytes = base64.b64decode(result["file_content"])
    filename = result.get("file_name", "labels.pdf")
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class FbsActRequest(BaseModel):
    shop_id: str


@router.post("/fbs/create-act")
async def create_fbs_act(req: FbsActRequest):
    """Create FBS acceptance act."""
    client = get_ozon_client()
    result = await client.fbs_create_act(req.shop_id)
    return result


# ============ Advertising ============


@router.get("/ad/campaigns")
async def list_ad_campaigns(
    shop_id: str = Query(default=...),
    page: int = Query(default=1),
    page_size: int = Query(default=50),
    state: str = "",
):
    """List advertising campaigns."""
    client = get_ozon_client()
    result = await client.list_ad_campaigns(shop_id, page, page_size, state)
    return result


class AdCreateRequest(BaseModel):
    shop_id: str
    title: str
    daily_budget: float
    start_date: str
    end_date: str = ""


@router.post("/ad/campaigns")
async def create_ad_campaign(req: AdCreateRequest):
    """Create an advertising campaign."""
    client = get_ozon_client()
    result = await client.create_ad_campaign(
        shop_id=req.shop_id,
        title=req.title,
        daily_budget=req.daily_budget,
        start_date=req.start_date,
        end_date=req.end_date,
    )
    return result


class AdCampaignActionRequest(BaseModel):
    shop_id: str
    action: str  # "ON" | "OFF" | "ACTIVATE" | "PAUSE"


@router.post("/ad/campaigns/{campaign_id}")
async def ad_campaign_action(
    campaign_id: int,
    req: AdCampaignActionRequest,
):
    """Perform an action on an advertising campaign (activate/pause)."""
    client = get_ozon_client()
    state_map = {"ON": "ON", "OFF": "OFF", "ACTIVATE": "ON", "PAUSE": "OFF", "activate": "ON", "deactivate": "OFF", "resume": "ON", "pause": "OFF"}
    state = state_map.get(req.action)
    if not state:
        raise HTTPException(status_code=400, detail=f"Unknown action: {req.action}")
    result = await client.update_ad_campaign(
        shop_id=req.shop_id, campaign_id=campaign_id, state=state,
    )
    return result


@router.get("/ad/campaigns/{campaign_id}")
async def get_ad_campaign(
    campaign_id: int,
    shop_id: str = Query(default=...),
):
    """Get advertising campaign details."""
    client = get_ozon_client()
    result = await client.get_ad_campaign(shop_id, campaign_id)
    return result


@router.get("/ad/campaigns/{campaign_id}/stats")
async def get_ad_campaign_stats(
    campaign_id: int,
    shop_id: str = Query(default=...),
    date_from: str = Query(default=...),
    date_to: str = "",
):
    """Get advertising campaign statistics."""
    client = get_ozon_client()
    result = await client.get_ad_campaign_stats(
        shop_id, [campaign_id], date_from, date_to or "",
    )
    return result


# ============ Returns (Phase 6) ============


@router.get("/returns")
async def list_returns(
    shop_id: str = Query(default=...),
    status: str = "",
    return_schema: str = "",
    limit: int = Query(default=50),
    last_id: int = Query(default=0),
):
    """List FBO/FBS returns."""
    client = get_ozon_client()
    return await client.list_returns(shop_id, limit, last_id, return_schema, status)


@router.get("/fbs-returns")
async def list_fbs_returns(
    shop_id: str = Query(default=...),
    limit: int = Query(default=50),
    last_id: int = Query(default=0),
):
    """List FBS/rFBS returns."""
    client = get_ozon_client()
    return await client.list_fbs_returns(shop_id, limit, last_id)


@router.get("/returns/{return_id}")
async def get_return_info(
    return_id: int,
    shop_id: str = Query(default=...),
):
    """Get return details."""
    client = get_ozon_client()
    return await client.get_return_info(shop_id, return_id)


class ReturnActionRequest(BaseModel):
    shop_id: str
    return_id: int
    return_method_description: str = ""
    comment: str = ""
    rejection_reason_id: int = 0


@router.post("/returns/accept")
async def accept_return(req: ReturnActionRequest):
    """Approve an rFBS return request."""
    client = get_ozon_client()
    return await client.accept_return(req.shop_id, req.return_id, req.return_method_description)


@router.post("/returns/reject")
async def reject_return(req: ReturnActionRequest):
    """Reject an rFBS return request with reason."""
    client = get_ozon_client()
    return await client.reject_return(req.shop_id, req.return_id, req.rejection_reason_id, req.comment)


@router.post("/returns/refund")
async def refund_return(req: ReturnActionRequest):
    """Refund customer for an rFBS return."""
    client = get_ozon_client()
    return await client.refund_return(req.shop_id, req.return_id)


@router.get("/claims")
async def list_claims(
    shop_id: str = Query(default=...),
    limit: int = Query(default=50),
    last_id: int = Query(default=0),
    state: str = "ALL",
):
    """List rFBS cancellation requests."""
    client = get_ozon_client()
    return await client.list_claims(shop_id, limit, last_id, state)


@router.get("/claims/{claim_id}")
async def get_claim_info(
    claim_id: int,
    shop_id: str = Query(default=...),
):
    """Get claim details."""
    client = get_ozon_client()
    return await client.get_claim_info(shop_id, claim_id)


# ============ Finance (Phase 6) ============


@router.get("/finance/transactions")
async def list_transactions(
    shop_id: str = Query(default=...),
    from_date: str = "",
    to_date: str = "",
    page: int = Query(default=1),
    page_size: int = Query(default=100),
):
    """List finance transactions."""
    client = get_ozon_client()
    return await client.list_transactions(shop_id, from_date, to_date, page, page_size)


@router.get("/finance/daily-sales")
async def get_daily_sales(
    shop_id: str = Query(default=...),
    day: int = Query(default=...),
    month: int = Query(default=...),
    year: int = Query(default=...),
):
    """Get daily sales realization report (Premium Plus)."""
    client = get_ozon_client()
    return await client.get_daily_realization(shop_id, day, month, year)


@router.get("/finance/realization")
async def get_realization(
    shop_id: str = Query(default=...),
    month: int = Query(default=...),
    year: int = Query(default=...),
):
    """Get monthly sales realization report."""
    client = get_ozon_client()
    return await client.get_realization(shop_id, month, year)


# ============ Chat (Phase 7) ============


@router.get("/chat/history")
async def get_chat_history(
    shop_id: str = Query(default=...),
    chat_id: str = Query(default=...),
    limit: int = Query(default=100),
):
    """Get chat history."""
    client = get_ozon_client()
    return await client.get_chat_history(shop_id, chat_id, limit)


class ChatSendRequest(BaseModel):
    shop_id: str
    chat_id: str
    text: str


@router.post("/chat/send")
async def send_chat_message(req: ChatSendRequest):
    """Send a chat message."""
    client = get_ozon_client()
    return await client.send_chat_message(req.shop_id, req.chat_id, req.text)


class ChatSendFileRequest(BaseModel):
    shop_id: str
    chat_id: str
    base64_content: str
    file_name: str = ""


@router.post("/chat/send-file")
async def send_chat_file(req: ChatSendFileRequest):
    """Send a file in chat (base64 encoded)."""
    client = get_ozon_client()
    return await client.send_chat_file(req.shop_id, req.chat_id, req.base64_content, req.file_name)


@router.get("/chat/unread")
async def list_unread_chats(
    shop_id: str = Query(default=...),
    limit: int = Query(default=30),
    cursor: str = "",
):
    """List unread chats."""
    client = get_ozon_client()
    return await client.list_unread_chats(shop_id, limit, cursor)


# ============ Questions (Phase 7) ============


@router.get("/questions")
async def list_questions(
    shop_id: str = Query(default=...),
    limit: int = Query(default=50),
    offset: int = Query(default=0),
    answered: bool | None = None,
):
    """List product questions."""
    client = get_ozon_client()
    return await client.list_questions(shop_id, limit, offset, answered)


class AnswerQuestionRequest(BaseModel):
    shop_id: str
    question_id: int
    answer_text: str


@router.post("/questions/answer")
async def answer_question(req: AnswerQuestionRequest):
    """Answer a product question."""
    client = get_ozon_client()
    return await client.answer_question(req.shop_id, req.question_id, req.answer_text)


class DeleteQuestionRequest(BaseModel):
    shop_id: str
    question_id: int


@router.post("/questions/delete")
async def delete_question(req: DeleteQuestionRequest):
    """Delete a product question."""
    client = get_ozon_client()
    return await client.delete_question(req.shop_id, req.question_id)


# ============ Reviews (Phase 7) ============


@router.get("/reviews")
async def list_reviews(
    shop_id: str = Query(default=...),
    limit: int = Query(default=20),
    last_id: str = "",
    status: str = "ALL",
    sort_dir: str = "ASC",
):
    """List product reviews (Premium Plus)."""
    client = get_ozon_client()
    return await client.list_reviews(shop_id, limit, last_id, status, sort_dir)


class ReplyReviewRequest(BaseModel):
    shop_id: str
    review_id: str
    reply_text: str
    mark_as_processed: bool = True


@router.post("/reviews/reply")
async def reply_review(req: ReplyReviewRequest):
    """Reply to a product review (Premium Plus)."""
    client = get_ozon_client()
    return await client.reply_review(req.shop_id, req.review_id, req.reply_text, req.mark_as_processed)


# ============ Marketing / Promotions (Phase 7) ============


@router.get("/actions")
async def list_actions(
    shop_id: str = Query(default=...),
):
    """List available marketing actions."""
    client = get_ozon_client()
    return {"actions": await client.list_actions(shop_id)}


@router.get("/actions/{action_id}/products")
async def list_action_products(
    action_id: int,
    shop_id: str = Query(default=...),
    limit: int = Query(default=50),
    offset: int = Query(default=0),
    last_id: str = Query(default=""),
):
    """List products in a marketing action."""
    client = get_ozon_client()
    return await client.list_action_products(shop_id, action_id, limit, offset, last_id)


class ActionRegisterProduct(BaseModel):
    product_id: int
    action_price: float
    stock: int


class ActionRegisterRequest(BaseModel):
    shop_id: str
    action_id: int
    products: list[ActionRegisterProduct]


@router.post("/actions/register")
async def register_action_products(req: ActionRegisterRequest):
    """Register products in a marketing action.

    Each product requires: product_id, action_price, stock.
    """
    client = get_ozon_client()
    products_data = [p.model_dump() for p in req.products]
    return await client.register_action_products(req.shop_id, req.action_id, products_data)


class ActionUnregisterRequest(BaseModel):
    shop_id: str
    action_id: int
    product_ids: list[int]


@router.post("/actions/unregister")
async def unregister_action_products(req: ActionUnregisterRequest):
    """Unregister products from a marketing action."""
    client = get_ozon_client()
    return await client.unregister_action_products(req.shop_id, req.action_id, req.product_ids)


# ============ Ratings ============


@router.get("/rating/summary")
async def get_rating_summary(
    shop_id: str = Query(default=...),
):
    """Get seller rating summary."""
    client = get_ozon_client()
    return await client.get_rating_summary(shop_id)


@router.get("/rating/history")
async def get_rating_history(
    shop_id: str = Query(default=...),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
):
    """Get seller rating history."""
    client = get_ozon_client()
    return await client.get_rating_history(shop_id, date_from, date_to)


# ============ Finance — Additional ============


@router.get("/finance/transaction-totals")
async def get_transaction_totals(
    shop_id: str = Query(default=...),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
):
    """Get finance transaction totals."""
    client = get_ozon_client()
    return await client.get_transaction_totals(shop_id, date_from, date_to)


@router.get("/finance/cash-flow")
async def get_cash_flow(
    shop_id: str = Query(default=...),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
):
    """Get cash flow statement."""
    client = get_ozon_client()
    return await client.get_cash_flow_statement(shop_id, date_from, date_to)


@router.get("/finance/mutual-settlement")
async def get_mutual_settlement(
    shop_id: str = Query(default=...),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
):
    """Get mutual settlement report."""
    client = get_ozon_client()
    return await client.get_mutual_settlement(shop_id, date_from, date_to)


@router.get("/finance/compensation")
async def get_compensation(
    shop_id: str = Query(default=...),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
):
    """Get compensation report."""
    client = get_ozon_client()
    return await client.get_compensation(shop_id, date_from, date_to)


@router.get("/finance/products-buyout")
async def get_products_buyout(
    shop_id: str = Query(default=...),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
):
    """Get products buyout report."""
    client = get_ozon_client()
    return await client.get_products_buyout(shop_id, date_from, date_to)


@router.get("/finance/realization-posting")
async def get_realization_posting(
    shop_id: str = Query(default=...),
    month: int = Query(default=...),
    year: int = Query(default=...),
):
    """Get sales realization by posting (order-level detail)."""
    client = get_ozon_client()
    return await client.get_realization_posting(shop_id, month, year)


# ============ Analytics ============


@router.get("/analytics/data")
async def get_analytics_data(
    shop_id: str = Query(default=...),
    metrics: str = Query(default="revenue,ordered_units"),
    dimension: str = Query(default="sku,day"),
    date_from: str = Query(default=...),
    date_to: str = Query(default=...),
    limit: int = Query(default=100),
):
    """Get analytics data with metrics and dimensions."""
    client = get_ozon_client()
    metrics_list = [m.strip() for m in metrics.split(",")]
    dim_list = [d.strip() for d in dimension.split(",")]
    return await client.get_analytics_data(shop_id, metrics_list, dim_list, date_from, date_to, limit)


@router.get("/analytics/product-queries")
async def get_product_queries(
    shop_id: str = Query(default=...),
    date_from: str = Query(default=...),
    date_to: str = Query(default=...),
):
    """Get product queries analytics."""
    client = get_ozon_client()
    return await client.get_product_queries(shop_id, date_from, date_to)


# ============ Ozon Async Reports ============


@router.post("/reports/ozon/create")
async def create_ozon_report(
    shop_id: str = Query(default=...),
    report_type: str = Query(default=...),
):
    """Create an async report on Ozon side."""
    client = get_ozon_client()
    return await client.create_ozon_report(shop_id, report_type)


class OzonReportStatusRequest(BaseModel):
    shop_id: str
    code: str


@router.post("/reports/ozon/status")
async def get_ozon_report_status(req: OzonReportStatusRequest):
    """Get async report status by code."""
    client = get_ozon_client()
    return await client.get_ozon_report(req.shop_id, req.code)


@router.get("/reports/ozon/list")
async def list_ozon_reports(
    shop_id: str = Query(default=...),
    page: int = Query(default=1),
    page_size: int = Query(default=20),
):
    """List previously generated reports."""
    client = get_ozon_client()
    return await client.list_ozon_reports(shop_id, page, page_size)