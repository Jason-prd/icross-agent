"""AI-powered order analysis endpoints.

Provides:
- max-purchase-price: Calculate max purchase price for drop-shipping (支持 SKU 级)
- classify-issue: Classify cancellation reasons
"""
from fastapi import APIRouter, HTTPException, Query
from icross.api.ai_utils import _extract_json, get_ai_llm
from icross.services.ozon_costs import OzonCostCalculator, CNY_TO_RUB, detect_delivery_mode

router = APIRouter(prefix="/orders", tags=["ai_orders"])


async def _get_order_detail(
    posting_number: str, shop_id: str, order_type: str = ""
) -> dict | None:
    """Fetch order detail from Ozon API by posting_number (works for FBO/FBS).

    Tries the FBS get endpoint first (works for all order types),
    falls back to FBO list search.
    """
    from icross.services.ozon.client import OzonClient

    client = OzonClient()
    try:
        return await client.get_fbs_posting(shop_id, posting_number)
    except Exception:
        pass

    # Fallback: search FBO list
    resp = await client.get_order_list(shop_id, limit=50, since="")
    orders = resp if isinstance(resp, list) else (resp.get("items") or resp.get("orders") or [])
    for o in orders:
        if o.get("posting_number") == posting_number or str(o.get("posting_id")) == posting_number:
            return o
    return None


def _extract_sku_weight(product: dict) -> tuple[float | None, str, str, str]:
    """Extract weight and category for a single SKU.

    Priority:
    1. _fetched_weight_kg on product dict (pre-set by endpoint after Ozon API call)
    2. Local ProductStorage (weight, attrs.weight_kg, attrs.volume_weight)
    """
    offer_id = product.get("offer_id", "")
    weight_kg = None
    weight_from = ""
    category_name = ""
    category_from = ""

    # Priority 1: pre-fetched weight from Ozon API (set by endpoint)
    fetched = product.get("_fetched_weight_kg")
    if fetched is not None:
        return float(fetched), "api", category_name, category_from

    if offer_id:
        from icross.core.storage.ozon_data import ProductStorage
        store = ProductStorage()
        local_products = store._products._filter(offer_id=offer_id)
        if local_products:
            lp = local_products[0]
            w = lp.get("weight") or lp.get("attrs", {}).get("weight_kg") or lp.get("attrs", {}).get("volume_weight")
            if w:
                wkg = float(w)
                w_unit = lp.get("weight_unit")  # may be None for legacy data
                if w_unit == "g":
                    wkg = wkg / 1000
                elif w_unit != "kg" and wkg > 100:
                    # fallback: no explicit unit, large value → likely grams
                    wkg = wkg / 1000
                # else: kg unit or small value without unit → use as-is (assumed kg)
                weight_kg = wkg
                weight_from = "product"
            cat = lp.get("category_name") or lp.get("category_path", "")
            if cat:
                category_name = cat
                category_from = "product"

    return weight_kg, weight_from, category_name, category_from


def _calc_sku_purchase_price(product: dict, calc: OzonCostCalculator, target_margin: float, delivery_mode: str = "standard") -> dict:
    """Calculate max purchase price for a single SKU (per-unit)."""
    offer_id = product.get("offer_id", "")
    name = product.get("name", "")
    unit_price = float(product.get("price", 0) or 0)
    qty = int(product.get("quantity", 1) or 1)
    currency = product.get("currency_code", "RUB")
    if currency == "RUB":
        selling_cny = unit_price / CNY_TO_RUB  # per unit
        selling_price_rub = unit_price  # per unit
    else:  # CNY or others — price is already in CNY
        selling_cny = unit_price  # per unit
        selling_price_rub = unit_price * CNY_TO_RUB  # per unit

    # Look up per-SKU weight/category
    weight_kg, weight_from, category_name, category_from = _extract_sku_weight(product)

    if not weight_kg:
        weight_kg = 0.5
        weight_from = "estimated"

    result = calc.calculate_max_purchase_price(
        selling_price_cny=selling_cny,
        weight_kg=weight_kg,
        category_name=category_name,
        target_margin=target_margin,
        selling_price_rub=selling_price_rub,
        delivery_mode=delivery_mode,
    )

    # 将结果从 per-unit 转为该 SKU 行合计（× qty），
    # 注意 logistics 按件计费（一件代发场景），利润率和佣金率不变
    result["selling_price_cny"] = round(selling_cny * qty, 2)
    result["max_purchase_price_cny"] = round(result["max_purchase_price_cny"] * qty, 2)
    result["max_purchase_price_rub"] = round(result["max_purchase_price_rub"] * qty, 2)
    result["profit_cny"] = round(result["profit_cny"] * qty, 2)
    # cost_breakdown 中 logistics 按件计费 × qty，其余按比例
    if "cost_breakdown" in result:
        b = result["cost_breakdown"]
        b["commission_cny"] = round(b["commission_cny"] * qty, 2)
        b["logistics_cny"] = round(b["logistics_cny"] * qty, 2)
        b["customs_cny"] = round(b["customs_cny"] * qty, 2)
        b["return_reserve_cny"] = round(b["return_reserve_cny"] * qty, 2)
        b["packaging_cny"] = round(b["packaging_cny"] * qty, 2)

    result["offer_id"] = offer_id
    result["product_name"] = name
    result["quantity"] = qty
    result["source"] = {
        "weight_kg": weight_kg,
        "category_name": category_name,
        "weight_from": weight_from,
        "category_from": category_from,
    }
    return result


@router.post("/{posting_number}/ai/max-purchase-price")
async def ai_max_purchase_price(
    posting_number: str,
    shop_id: str = Query(...),
    order_type: str = Query("fbo"),
    target_margin: float = Query(20.0, ge=0, le=100),
    offer_id: str = Query(None),
    delivery_mode: str = Query(None),
):
    """Calculate maximum purchase price (CNY) for drop-shipping.

    If offer_id is provided, calculates for a single SKU.
    Otherwise, returns per-SKU results for all products in the order.

    delivery_mode: standard / economy (auto-detected from order if not specified)
    """
    order = await _get_order_detail(posting_number, shop_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    products = order.get("products", [])
    if not products:
        raise HTTPException(status_code=400, detail="No products in order")

    calc = OzonCostCalculator()

    # Auto-detect delivery_mode from order data
    analytics = order.get("analytics") or order.get("analytics_data", {})
    if not delivery_mode:
        delivery_mode = detect_delivery_mode(
            delivery_type=analytics.get("delivery_type", ""),
            is_express=order.get("is_express", False),
        )

    # ── Pre-fetch missing weights from Ozon API ──
    target_products = [p for p in products if p.get("offer_id") == offer_id] if offer_id else products
    need_fetch_ids = []
    for p in target_products:
        w, wf, _, _ = _extract_sku_weight(p)
        if not w:
            need_fetch_ids.append(p.get("offer_id"))
    if need_fetch_ids:
        try:
            from icross.services.ozon.client import OzonClient
            ozon = OzonClient()
            info = await ozon.get_product_info_list(shop_id, offer_ids=need_fetch_ids)
            items = info.get("items") or []
            # Map offer_id → product_id from product info for attribute lookup
            oid_to_pid: dict[str, int] = {}
            for item in items:
                oid = item.get("offer_id")
                pid = item.get("product_id")
                vw = item.get("volume_weight")
                if oid:
                    if pid:
                        oid_to_pid[oid] = pid
                    # Start with volume_weight as fallback
                    if vw is not None:
                        for p in products:
                            if p.get("offer_id") == oid:
                                p["_fetched_weight_kg"] = float(vw)
                                break

            # Step 2: Fetch actual weight from product attributes (more accurate)
            if oid_to_pid:
                try:
                    attr_result = await ozon.get_product_attributes_list(
                        shop_id, list(oid_to_pid.values())
                    )
                    for attr_item in attr_result.get("result") or []:
                        pid = attr_item.get("id")
                        if not pid:
                            continue
                        # Find offer_id for this product_id
                        oid = next((k for k, v in oid_to_pid.items() if v == pid), None)
                        if not oid:
                            continue
                        w = attr_item.get("weight")
                        w_unit = attr_item.get("weight_unit")
                        if w is not None and w > 0:
                            w_kg = float(w) / 1000 if w_unit == "g" else float(w)
                            for p in products:
                                if p.get("offer_id") == oid:
                                    p["_fetched_weight_kg"] = w_kg
                                    break
                except Exception:
                    pass  # non-critical, keep volume_weight fallback
        except Exception:
            pass  # non-critical, falls back to 0.5kg default

    if offer_id:
        product = next((p for p in products if p.get("offer_id") == offer_id), None)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        result = _calc_sku_purchase_price(product, calc, target_margin, delivery_mode)
        result["posting_number"] = posting_number
        result["delivery_mode"] = delivery_mode
        result["logistics_info"] = {
            "warehouse": analytics.get("warehouse", ""),
            "tpl_provider": analytics.get("tpl_provider", ""),
            "delivery_type": analytics.get("delivery_type", ""),
        }
        return result

    results = []
    for p in products:
        r = _calc_sku_purchase_price(p, calc, target_margin, delivery_mode)
        results.append(r)
    return {
        "posting_number": posting_number,
        "products": results,
        "delivery_mode": delivery_mode,
        "logistics_info": {
            "warehouse": analytics.get("warehouse", ""),
            "tpl_provider": analytics.get("tpl_provider", ""),
            "delivery_type": analytics.get("delivery_type", ""),
        },
    }


@router.post("/{posting_number}/ai/classify-issue")
async def ai_classify_issue(
    posting_number: str,
    shop_id: str = Query(...),
    order_type: str = Query("fbo"),
    cancel_reason: str = Query(default=""),
):
    """Classify order cancellation reason into structured categories."""
    order = await _get_order_detail(posting_number, shop_id)
    reason = cancel_reason or (order or {}).get("cancellation_reason", "") or ""
    if not reason:
        raise HTTPException(status_code=400, detail="No cancellation reason found")

    prompt = f"""请将以下 Ozon 订单取消原因归类为结构化分类。

取消原因: {reason}

返回 JSON 格式:
{{"category": "主分类", "sub_category": "子分类", "actionable": true/false, "suggestion": "处理建议"}}

分类选项: 尺寸/规格不符 | 价格争议 | 库存不足 | 物流问题 | 买家要求取消 | 重复订单 | 欺诈风险 | 其他"""

    llm = get_ai_llm("order.issue.classify")
    response = await llm.ainvoke([{"role": "user", "content": prompt}])
    raw = response.content
    if isinstance(raw, list):
        texts = []
        for block in raw:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))
        raw = "\n".join(texts)
    json_str, _ = _extract_json(raw.strip())
    parsed = {"category": "其他", "sub_category": "", "actionable": False, "suggestion": ""}
    if json_str:
        import json as jmod
        try:
            parsed = jmod.loads(json_str)
        except Exception:
            pass

    parsed["posting_number"] = posting_number
    parsed["original_reason"] = reason
    return parsed


@router.post("/{posting_number}/ai/analyze")
async def ai_analyze_order(
    posting_number: str,
    shop_id: str = Query(...),
):
    """Analyze order for anomalies: large orders, high-risk products, suspicious addresses, etc."""
    order = await _get_order_detail(posting_number, shop_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    products = order.get("products", [])
    analytics = order.get("analytics_data") or order.get("analytics") or {}
    financial = order.get("financial_data") or []

    # Build product summary for the prompt
    product_lines = []
    total_qty = 0
    for p in products:
        name = p.get("name", "?")
        qty = p.get("quantity", 1) or 1
        price = p.get("price", "0")
        total_qty += qty
        product_lines.append(f"  - {name} × {qty} @ ¥{price}")

    # Calculate total value — check currency per product
    total_cny = 0
    for p in products:
        item_total = float(p.get("price", 0) or 0) * (p.get("quantity", 1) or 1)
        if p.get("currency_code", "RUB") == "RUB":
            total_cny += item_total / CNY_TO_RUB
        else:
            total_cny += item_total

    # Count status from financial data if available
    commission_total = sum(float(f.get("commission_amount", 0) or 0) for f in financial)

    prompt = f"""你是一个 Ozon 电商订单风险分析专家。分析以下订单是否存在异常风险。

订单号: {posting_number}
状态: {order.get("status", "")}
取消原因: {order.get("cancellation_reason", "无")}
总金额: ¥{total_cny:.2f}
商品总数: {total_qty}

商品列表:
{chr(10).join(product_lines) if product_lines else "  无"}

配送信息:
  城市: {analytics.get("city", "未知")}
  配送方式: {analytics.get("delivery_type", "未知")}
  地区: {analytics.get("region", "未知")}

佣金总额: {commission_total}

请分析以下风险维度:
1. 金额异常 — 是否远超正常订单金额
2. 数量异常 — 是否大批量采购（可能转售/刷单）
3. 取消风险 — 取消原因是否可疑
4. 地址风险 — 配送地址是否存在异常
5. 综合评估

返回 JSON:
{{"risk_level": "low|medium|high", "risk_score": 0-100, "anomalies": [{{"type": "金额异常|数量异常|取消风险|地址风险|其他", "detail": "说明", "severity": "low|medium|high"}}], "summary": "一句话总结"}}"""

    llm = get_ai_llm("order.anomaly.detect")
    response = await llm.ainvoke([{"role": "user", "content": prompt}])
    raw = response.content
    if isinstance(raw, list):
        texts = [b.get("text", "") for b in raw if isinstance(b, dict) and b.get("type") == "text"]
        raw = "\n".join(texts)

    json_str, _ = _extract_json(raw.strip())
    result = {"risk_level": "low", "risk_score": 0, "anomalies": [], "summary": "分析失败"}
    if json_str:
        import json as jmod
        try:
            result = jmod.loads(json_str)
        except Exception:
            pass

    result["posting_number"] = posting_number
    return result
