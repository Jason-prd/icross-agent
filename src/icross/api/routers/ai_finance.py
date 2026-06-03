"""AI-powered finance analysis endpoints.

Provides:
- daily-commentary: Natural language summary of daily sales
- profit-anomalies: Detect profit deviations and analyze causes
- tag-transactions: Auto-classify transaction entries by type
"""
from fastapi import APIRouter, HTTPException, Query
from icross.api.ai_utils import _extract_json, get_ai_llm

router = APIRouter(prefix="/finance", tags=["ai_finance"])


@router.post("/ai/daily-commentary")
async def ai_daily_commentary(
    shop_id: str = Query(...),
    day: int = Query(None),
    month: int = Query(None),
    year: int = Query(None),
):
    """Generate natural language commentary for daily sales realization."""
    from datetime import datetime
    from icross.services.ozon.client import OzonClient

    now = datetime.now()
    d = day or now.day
    m = month or now.month
    y = year or now.year

    client = OzonClient()
    try:
        data = await client.get_daily_realization(shop_id, d, m, y)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch daily data: {e}")

    if not data or not data.get("rows"):
        return {"has_data": False, "message": f"{y}-{m:02d}-{d:02d} 暂无销售数据"}

    rows = data.get("rows", [])[:20]
    total_sales = sum(float(r.get("price", 0) or 0) for r in rows)
    order_count = len(rows)

    summary = f"日期: {y}-{m:02d}-{d:02d}\n总销售额: {total_sales:.2f} RUB\n订单数: {order_count}"

    prompt = f"""你是 Ozon 电商财务分析师。请基于以下每日销售数据，用中文写一段简练的销售评述（2-4句话）。

{summary}

请返回 JSON:
{{"commentary": "销售评述", "highlights": ["亮点1", "亮点2"], "warnings": ["需关注的问题"]}}"""

    llm = get_ai_llm("finance.daily.commentary")
    response = await llm.ainvoke([{"role": "user", "content": prompt}])
    raw = response.content
    if isinstance(raw, list):
        raw = "".join(b.get("text", "") for b in raw if isinstance(b, dict))
    json_str, _ = _extract_json(raw.strip())
    result = {"commentary": "销售数据分析完成", "highlights": [], "warnings": []}
    if json_str:
        import json as jmod
        try:
            result = jmod.loads(json_str)
        except Exception:
            pass

    result["date"] = f"{y}-{m:02d}-{d:02d}"
    result["total_sales"] = round(total_sales, 2)
    result["order_count"] = order_count
    return result


@router.post("/ai/profit-anomalies")
async def ai_profit_anomalies(
    shop_id: str = Query(...),
    month: int = Query(None),
    year: int = Query(None),
    threshold_pct: float = Query(20, ge=5, le=50),
):
    """Detect orders where actual profit deviates significantly from expected."""
    from datetime import datetime
    from icross.services.ozon.client import OzonClient

    now = datetime.now()
    m = month or now.month
    y = year or now.year

    client = OzonClient()
    try:
        data = await client.get_realization_posting(shop_id, m, y)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch realization: {e}")

    postings = data.get("postings", data.get("result", {}).get("postings", []))
    if not postings:
        return {"has_data": False, "message": f"{y}-{m:02d} 暂无入账数据"}

    # Summarize for LLM
    items = []
    for p in postings[:30]:
        items.append({
            "posting": p.get("posting_number", ""),
            "price": p.get("price", 0),
            "commission": p.get("commission_amount", 0),
            "delivery_cost": p.get("delivery_cost", 0),
            "payout": p.get("payout", 0),
            "service": ", ".join(p.get("services", [])[:3]),
        })

    prompt = f"""你是 Ozon 财务审计专家。分析以下订单入账数据，找出利润异常（实际利润偏离预期超过 {threshold_pct}%）。

订单数据 ({len(items)} 条):
{str(items)[:3000]}

返回 JSON:
{{"anomalies": [{{"posting": "订单号", "expected_profit": 预期利润, "actual_profit": 实际利润, "deviation_pct": 偏离%, "possible_reason": "原因", "severity": "high|medium|low"}}], "summary": "整体评估"}}"""

    llm = get_ai_llm("finance.profit.anomaly", max_tokens=4096)
    response = await llm.ainvoke([{"role": "user", "content": prompt}])
    raw = response.content
    if isinstance(raw, list):
        raw = "".join(b.get("text", "") for b in raw if isinstance(b, dict))
    json_str, _ = _extract_json(raw.strip())
    result = {"anomalies": [], "summary": "分析完成"}
    if json_str:
        import json as jmod
        try:
            result = jmod.loads(json_str)
        except Exception:
            pass

    result["period"] = f"{y}-{m:02d}"
    result["total_postings"] = len(postings)
    result["threshold_pct"] = threshold_pct
    return result


@router.post("/ai/tag-transactions")
async def ai_tag_transactions(
    shop_id: str = Query(...),
    date_from: str = Query(""),
    date_to: str = Query(""),
    limit: int = Query(50, ge=1, le=200),
):
    """Auto-classify finance transaction entries by type."""
    from icross.services.ozon.client import OzonClient

    client = OzonClient()
    try:
        data = await client.get_transaction_totals(shop_id, date_from, date_to)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch transactions: {e}")

    items = data.get("result", data.get("operations", []))
    if not items:
        try:
            txns = await client.list_transactions(shop_id, date_from or "", date_to or "", limit=limit)
            items = txns.get("result", {}).get("operations", [])
        except Exception:
            pass

    if not items:
        return {"has_data": False, "message": "暂无交易流水数据", "tagged": []}

    # Build summary for LLM
    summary_items = []
    for it in items[:limit]:
        summary_items.append({
            "type": it.get("type", ""),
            "operation_type": it.get("operation_type", ""),
            "amount": it.get("amount", 0),
            "name": it.get("name", it.get("operation_type_name", "")),
            "date": it.get("operation_date", ""),
        })

    prompt = f"""你是 Ozon 财务分类专家。将以下交易流水条目归类为: 佣金/物流/广告/罚款/退款/退货/仓储/其他。

交易数据 ({len(summary_items)} 条):
{str(summary_items)[:3000]}

返回 JSON:
{{"categories": {{"佣金": {{"count": N, "total": 金额}}, "物流": {{...}}, ...}}, "suggestions": ["建议1"]}}"""

    llm = get_ai_llm("finance.transaction.tag")
    response = await llm.ainvoke([{"role": "user", "content": prompt}])
    raw = response.content
    if isinstance(raw, list):
        raw = "".join(b.get("text", "") for b in raw if isinstance(b, dict))
    json_str, _ = _extract_json(raw.strip())
    result = {"categories": {}, "suggestions": []}
    if json_str:
        import json as jmod
        try:
            result = jmod.loads(json_str)
        except Exception:
            pass

    result["total_items"] = len(summary_items)
    return result
