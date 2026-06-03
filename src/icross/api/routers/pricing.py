"""Pricing rules management API endpoints (Phase 4)."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/pricing-rules", tags=["pricing-rules"])


class RuleAction(BaseModel):
    adjustment_type: str = Field(..., pattern=r"^(markup|discount|fixed|round|cost_plus)$")
    value: float = Field(..., gt=0)


class RuleCondition(BaseModel):
    category: str = ""
    min_price: float | None = None
    max_price: float | None = None


class CreateRuleRequest(BaseModel):
    shop_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1, max_length=100)
    rule_type: str = Field(default="discount", pattern=r"^(markup|discount|match_competitor|fixed|cost_plus)$")
    condition: RuleCondition = Field(default_factory=RuleCondition)
    action: RuleAction
    priority: int = 0
    enabled: bool = True


class UpdateRuleRequest(BaseModel):
    name: str | None = None
    rule_type: str | None = None
    condition: RuleCondition | None = None
    action: RuleAction | None = None
    priority: int | None = None
    enabled: bool | None = None


class ApplyAndPushRequest(BaseModel):
    shop_id: str = Field(..., min_length=1)
    product_ids: list[int] | None = None
    rule_id: str | None = None


class PushAllRequest(BaseModel):
    shop_id: str = Field(default="", description="Filter by shop, empty for all shops")


@router.get("")
async def list_rules(shop_id: str = ""):
    """List all pricing rules, optionally filtered by shop."""
    from icross.core.storage.ozon_data import PricingRuleStorage

    store = PricingRuleStorage()
    rules = await store.list_rules(shop_id=shop_id or None)
    return {"rules": rules, "total": len(rules)}


@router.post("")
async def create_rule(req: CreateRuleRequest):
    """Create a new pricing rule."""
    from icross.core.storage.ozon_data import PricingRuleStorage

    store = PricingRuleStorage()
    rule = await store.create_rule(
        shop_id=req.shop_id,
        name=req.name,
        rule_type=req.rule_type,
        condition=req.condition.model_dump(),
        action=req.action.model_dump(),
        priority=req.priority,
        enabled=req.enabled,
    )
    return {"success": True, "rule": rule}


@router.get("/{rule_id}")
async def get_rule(rule_id: str):
    """Get a pricing rule by ID."""
    from icross.core.storage.ozon_data import PricingRuleStorage

    store = PricingRuleStorage()
    rule = await store.get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


@router.put("/{rule_id}")
async def update_rule(rule_id: str, req: UpdateRuleRequest):
    """Update a pricing rule."""
    from icross.core.storage.ozon_data import PricingRuleStorage

    updates = {}
    for field in ("name", "rule_type", "priority", "enabled"):
        val = getattr(req, field, None)
        if val is not None:
            updates[field] = val
    if req.condition is not None:
        updates["condition"] = req.condition.model_dump()
    if req.action is not None:
        updates["action"] = req.action.model_dump()

    store = PricingRuleStorage()
    rule = await store.update_rule(rule_id, **updates)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"success": True, "rule": rule}


@router.delete("/{rule_id}")
async def delete_rule(rule_id: str):
    """Delete a pricing rule."""
    from icross.core.storage.ozon_data import PricingRuleStorage

    store = PricingRuleStorage()
    if await store.delete_rule(rule_id):
        return {"success": True}
    raise HTTPException(status_code=404, detail="Rule not found")


# ============================================================
# Cost Calculator Endpoints
# ============================================================


class CostCalcRequest(BaseModel):
    purchase_price_cny: float = Field(..., gt=0)
    weight_kg: float = Field(..., gt=0)
    category_name: str = ""
    target_margin: float = 20.0
    sales_model: str = "FBP"
    warehouse: str = "UNI"
    delivery_speed: str = "standard"
    packaging_cost_cny: float = 2.0
    return_reserve_pct: float = 2.0


class ProfitCalcRequest(BaseModel):
    purchase_price_cny: float = Field(..., gt=0)
    weight_kg: float = Field(..., gt=0)
    selling_price_rub: float = Field(..., gt=0)
    category_name: str = ""
    sales_model: str = "FBP"
    warehouse: str = "UNI"
    delivery_speed: str = "standard"


@router.post("/calculate-price", tags=["cost-calculator"])
async def calculate_price(req: CostCalcRequest):
    """Calculate recommended price for target profit margin."""
    from icross.services.ozon_costs import OzonCostCalculator, ProductCostInput

    calc = OzonCostCalculator()
    inp = ProductCostInput(
        purchase_price_cny=req.purchase_price_cny,
        weight_kg=req.weight_kg,
        category_name=req.category_name,
        sales_model=req.sales_model,  # type: ignore
        warehouse=req.warehouse,
        delivery_speed=req.delivery_speed,
        packaging_cost_cny=req.packaging_cost_cny,
        return_reserve_pct=req.return_reserve_pct,
    )
    result = calc.calculate(inp, target_margin=req.target_margin)
    return {"success": True, "result": result.__dict__}


@router.post("/calculate-profit", tags=["cost-calculator"])
async def calculate_profit(req: ProfitCalcRequest):
    """Calculate profit at a given selling price."""
    from icross.services.ozon_costs import OzonCostCalculator, ProductCostInput

    calc = OzonCostCalculator()
    inp = ProductCostInput(
        purchase_price_cny=req.purchase_price_cny,
        weight_kg=req.weight_kg,
        category_name=req.category_name,
        sales_model=req.sales_model,  # type: ignore
        warehouse=req.warehouse,
        delivery_speed=req.delivery_speed,
    )
    result = calc.calculate_from_price(inp, req.selling_price_rub)
    return {"success": True, "result": result.__dict__}


# ============================================================
# Batch Apply Rules
# ============================================================


class BatchApplyRequest(BaseModel):
    shop_id: str = Field(..., min_length=1)
    product_ids: list[int] | None = None
    rule_id: str | None = None


@router.post("/apply-batch")
async def batch_apply_rules(req: BatchApplyRequest):
    """Apply pricing rules to all (or specified) products."""
    from icross.core.storage.ozon_data import PricingRuleStorage, ProductStorage

    rule_store = PricingRuleStorage()
    product_store = ProductStorage()
    products_data = await product_store.list_products(shop_id=req.shop_id)
    products = products_data.get("items", [])

    if req.product_ids:
        pid_set = set(req.product_ids)
        products = [p for p in products if p.get("product_id") in pid_set]

    results = []
    for product in products:
        adjustment = await rule_store.apply_rules_to_product(req.shop_id, product)
        if adjustment and adjustment.get("adjusted_price") != adjustment.get("original_price"):
            results.append({
                "product_id": product.get("product_id"),
                "name": product.get("name"),
                "original_price": adjustment["original_price"],
                "adjusted_price": adjustment["adjusted_price"],
                "rule_name": adjustment.get("rule_name"),
            })

    return {"success": True, "total": len(products), "adjusted": len(results), "results": results}


class UpdateCostDataRequest(BaseModel):
    shop_id: str = Field(..., min_length=1)
    product_id: int = Field(..., gt=0)
    purchase_price_cny: float = Field(..., gt=0)
    weight_kg: float = Field(..., gt=0)
    category_name: str = ""


@router.post("/update-cost-data")
async def update_product_cost_data(req: UpdateCostDataRequest):
    """Update product cost data for cost_plus pricing."""
    from icross.core.storage.ozon_data import ProductStorage

    store = ProductStorage()
    product = await store.get_product(req.shop_id, req.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    attrs = product.get("attrs", {}) or {}
    attrs["purchase_price_cny"] = req.purchase_price_cny
    attrs["weight_kg"] = req.weight_kg
    if req.category_name:
        attrs["category_name"] = req.category_name
    product["attrs"] = attrs

    await store.update_product(req.shop_id, req.product_id, {"attrs": attrs})
    return {"success": True}


# ============================================================
# Price Push to Ozon
# ============================================================

import uuid
import logging as _logging
from datetime import datetime

_push_logger = _logging.getLogger(__name__)


async def push_price_to_ozon(
    product: dict,
    new_price: float,
    old_price: float | None = None,
) -> dict:
    """Push a single product's price to Ozon and log the result.

    This function:
      1. Calls OzonClient.update_price() with the new price
      2. On success, updates the product's stored local price
      3. Records the result in both the central push log (price_push_logs.json)
         and the product's inline price_push_logs list

    Args:
        product: Product dict from ProductStorage (must contain shop_id,
                 product_id, offer_id, and id fields).
        new_price: The new price to set on Ozon.
        old_price: The price before adjustment (for discount display and logging).

    Returns:
        Dict with:
          - success (bool)
          - log (dict): the push log entry that was saved
          - error (str | None): error message if failed
    """
    from icross.core.storage.ozon_data import ProductStorage, PricePushLogStorage
    from icross.services.ozon.client import OzonClient

    shop_id = product.get("shop_id")
    ozon_product_id = product.get("product_id")
    offer_id = product.get("offer_id", "")
    internal_id = product.get("id")
    current_price = product.get("price", 0)

    log_id = str(uuid.uuid4())
    pushed_at = datetime.now().isoformat()
    effective_old_price = old_price if old_price is not None else current_price

    # Validate that the product can be pushed
    if not shop_id or not ozon_product_id:
        log_entry = _build_push_log(
            log_id, internal_id, ozon_product_id, shop_id,
            effective_old_price, new_price,
            "failed", None, "Product missing shop_id or ozon_product_id", pushed_at,
        )
        log_store = PricePushLogStorage()
        await log_store.add_log(log_entry)
        return {"success": False, "log": log_entry, "error": "Missing shop_id or ozon_product_id"}

    # --- Attempt Ozon API call ---
    try:
        client = OzonClient()
        response = await client.update_price(
            shop_id=shop_id,
            product_id=ozon_product_id,
            offer_id=offer_id,
            price=new_price,
            old_price=effective_old_price,
        )
    except Exception as e:
        _push_logger.error("Price push exception for product %s: %s", internal_id, e)
        log_entry = _build_push_log(
            log_id, internal_id, ozon_product_id, shop_id,
            effective_old_price, new_price,
            "failed", None, str(e), pushed_at,
        )
        log_store = PricePushLogStorage()
        await log_store.add_log(log_entry)
        await _append_inline_log(internal_id, log_entry)
        return {"success": False, "log": log_entry, "error": str(e)}

    # Check API-level error response
    if "_error" in response:
        _push_logger.warning(
            "Price push API error for product %s: %s", internal_id, response["_error"]
        )
        log_entry = _build_push_log(
            log_id, internal_id, ozon_product_id, shop_id,
            effective_old_price, new_price,
            "failed", response, response["_error"], pushed_at,
        )
        log_store = PricePushLogStorage()
        await log_store.add_log(log_entry)
        await _append_inline_log(internal_id, log_entry)
        return {"success": False, "log": log_entry, "error": response["_error"]}

    # --- Success path ---
    log_entry = _build_push_log(
        log_id, internal_id, ozon_product_id, shop_id,
        effective_old_price, new_price,
        "success", response, None, pushed_at,
    )
    log_store = PricePushLogStorage()
    await log_store.add_log(log_entry)

    # Update local product price in storage
    try:
        product_store = ProductStorage()
        await product_store.update_product_price(
            internal_id=internal_id,
            new_price=new_price,
            old_price=effective_old_price,
        )
        await product_store.append_price_push_log(internal_id, log_entry)
    except Exception as e:
        _push_logger.warning("Failed to update local price for product %s: %s", internal_id, e)

    return {"success": True, "log": log_entry, "error": None}


def _build_push_log(
    log_id: str,
    internal_id: str | None,
    ozon_product_id: int | None,
    shop_id: str | None,
    old_price: float,
    new_price: float,
    status: str,
    ozon_response: dict | None,
    error: str | None,
    pushed_at: str,
) -> dict:
    """Build a push log entry dict."""
    return {
        "id": log_id,
        "product_id": internal_id,
        "ozon_product_id": ozon_product_id,
        "shop_id": shop_id,
        "old_price": old_price,
        "new_price": new_price,
        "status": status,
        "ozon_response": ozon_response,
        "error": error,
        "pushed_at": pushed_at,
    }


async def _append_inline_log(internal_id: str | None, log_entry: dict) -> None:
    """Append a push log entry to the product's inline log list (best-effort)."""
    if not internal_id:
        return
    try:
        from icross.core.storage.ozon_data import ProductStorage
        store = ProductStorage()
        await store.append_price_push_log(internal_id, log_entry)
    except Exception:
        pass


# ============================================================
# Apply Rules + Push Endpoints
# ============================================================


@router.post("/apply-and-push")
async def apply_rules_and_push(req: ApplyAndPushRequest):
    """Apply pricing rules and push new prices to Ozon in one call.

    For each matching product, this calculates the new price from the rules,
    pushes it to Ozon, updates local storage, and logs the result.
    """
    from icross.core.storage.ozon_data import PricingRuleStorage, ProductStorage

    rule_store = PricingRuleStorage()
    product_store = ProductStorage()
    products_data = await product_store.list_products(shop_id=req.shop_id)
    products = products_data.get("items", [])

    if req.product_ids:
        pid_set = set(req.product_ids)
        products = [p for p in products if p.get("product_id") in pid_set]

    push_results = []
    for product in products:
        try:
            adjustment = await rule_store.apply_rules_to_product(req.shop_id, product)
        except Exception as e:
            _push_logger.error("Error applying rules to product %s: %s", product.get("id"), e)
            continue
        if adjustment and adjustment.get("adjusted_price") != adjustment.get("original_price"):
            push_result = await push_price_to_ozon(
                product=product,
                new_price=adjustment["adjusted_price"],
                old_price=adjustment["original_price"],
            )
            push_results.append(push_result)

    successful = sum(1 for r in push_results if r["success"])
    failed = len(push_results) - successful

    return {
        "success": True,
        "total_products": len(products),
        "adjusted_and_pushed": len(push_results),
        "successful": successful,
        "failed": failed,
        "results": push_results,
    }


@router.post("/push-all")
async def push_all_prices(req: PushAllRequest):
    """Push all locally-stored product prices to Ozon.

    Iterates over all products (optionally filtered by shop) and pushes
    their current local price to Ozon, logging each result.
    This is useful for reconciling local state with Ozon after bulk changes.
    """
    from icross.core.storage.ozon_data import ProductStorage, ShopStorage

    product_store = ProductStorage()

    if req.shop_id:
        shops = [{"shop_id": req.shop_id}]
    else:
        shop_store = ShopStorage()
        shops = await shop_store.list_shops()

    push_results = []
    for shop in shops:
        shop_id = shop.get("shop_id") or shop.get("id")
        if not shop_id:
            continue
        try:
            products_data = await product_store.list_products(shop_id=shop_id, limit=1000)
            products = products_data.get("items", [])
        except Exception as e:
            _push_logger.error("Error listing products for shop %s: %s", shop_id, e)
            continue

        for product in products:
            current_price = product.get("price")
            if not current_price:
                continue
            push_result = await push_price_to_ozon(
                product=product,
                new_price=current_price,
                old_price=product.get("old_price"),
            )
            push_results.append(push_result)

    successful = sum(1 for r in push_results if r["success"])
    failed = len(push_results) - successful

    return {
        "success": True,
        "total_pushed": len(push_results),
        "successful": successful,
        "failed": failed,
        "results": push_results,
    }


@router.get("/push-logs")
async def get_push_logs(
    shop_id: str = "",
    product_id: str = "",
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Get price push log history with pagination.

    Args:
        shop_id: Filter by shop ID.
        product_id: Filter by local product UUID.
        limit: Max records per page (max 500).
        offset: Pagination offset.
    """
    from icross.core.storage.ozon_data import PricePushLogStorage

    log_store = PricePushLogStorage()
    result = await log_store.list_logs(
        shop_id=shop_id or None,
        product_id=product_id or None,
        limit=limit,
        offset=offset,
    )
    return result


# ============================================================
# Auto-Pricing Scheduler
# ============================================================

import asyncio
import logging
from datetime import datetime

from icross.services.scheduler import scheduler_service, register_job_handler

_logger = logging.getLogger(__name__)

# Register auto-pricing handler with shared scheduler
register_job_handler("auto_pricing", "icross.api.routers.pricing._run_auto_pricing")


async def _run_auto_pricing(push_to_ozon: bool = True, **kwargs):
    """Run auto-pricing: apply rules to all shops, optionally push to Ozon."""
    from icross.core.storage.ozon_data import PricingRuleStorage, ProductStorage, ShopStorage

    _logger.info("Auto-pricing scheduler: starting batch apply (push_to_ozon=%s)...", push_to_ozon)

    shop_store = ShopStorage()
    shops = await shop_store.list_shops()
    rule_store = PricingRuleStorage()
    product_store = ProductStorage()

    total_adjusted = 0
    total_pushed = 0
    total_failed = 0
    for shop in shops:
        shop_id = shop.get("shop_id") or shop.get("id")
        if not shop_id:
            continue
        try:
            products_data = await product_store.list_products(shop_id=shop_id)
            products = products_data.get("items", [])
            for product in products:
                adjustment = await rule_store.apply_rules_to_product(shop_id, product)
                if adjustment and adjustment.get("adjusted_price") != adjustment.get("original_price"):
                    total_adjusted += 1
                    if push_to_ozon:
                        push_result = await push_price_to_ozon(
                            product=product,
                            new_price=adjustment["adjusted_price"],
                            old_price=adjustment["original_price"],
                        )
                        if push_result["success"]:
                            total_pushed += 1
                        else:
                            total_failed += 1
        except Exception as e:
            _logger.error("Auto-pricing error for shop %s: %s", shop_id, e)

    if push_to_ozon:
        _logger.info(
            "Auto-pricing scheduler: done — %d products adjusted, %d pushed, %d failed",
            total_adjusted, total_pushed, total_failed,
        )
    else:
        _logger.info("Auto-pricing scheduler: done, %d products adjusted", total_adjusted)


@router.post("/scheduler/start")
async def start_scheduler(cron: str = "0 3 * * *"):
    """Start the auto-pricing scheduler with a cron expression.

    Uses the shared SchedulerService under the hood.
    """
    if not scheduler_service.running:
        await scheduler_service.start()

    # Create or update the auto_pricing job
    existing = await scheduler_service.list_jobs()
    pricing_job = None
    for j in existing:
        if j.get("job_type") == "auto_pricing":
            pricing_job = j
            break

    if pricing_job:
        await scheduler_service.remove_job(pricing_job["id"])

    job_id = await scheduler_service.add_job({
        "name": "自动定价",
        "job_type": "auto_pricing",
        "cron_expr": cron,
        "params": {"push_to_ozon": True},
        "enabled": True,
    })

    job = await scheduler_service.get_job(job_id)
    return {"success": True, "cron": cron, "job_id": job_id, "next_run": job.get("next_run")}


@router.post("/scheduler/stop")
async def stop_scheduler():
    """Stop the auto-pricing scheduler."""
    existing = await scheduler_service.list_jobs()
    for j in existing:
        if j.get("job_type") == "auto_pricing":
            await scheduler_service.remove_job(j["id"])
    return {"success": True}


@router.get("/scheduler/status")
async def scheduler_status():
    """Get auto-pricing scheduler status."""
    status = scheduler_service.get_status()
    existing = await scheduler_service.list_jobs()
    pricing_job = None
    for j in existing:
        if j.get("job_type") == "auto_pricing":
            pricing_job = j
            break

    return {
        "enabled": pricing_job is not None if pricing_job else False,
        "cron": pricing_job.get("cron_expr", "") if pricing_job else "",
        "next_run": pricing_job.get("next_run") if pricing_job else None,
        "scheduler_running": status["running"],
    }


@router.post("/scheduler/run-now")
async def run_scheduler_now(push_to_ozon: bool = True):
    """Trigger immediate pricing rule application.

    Args:
        push_to_ozon: If True (default), also push adjusted prices to Ozon.
    """
    await _run_auto_pricing(push_to_ozon=push_to_ozon)
    return {"success": True, "push_to_ozon": push_to_ozon}
