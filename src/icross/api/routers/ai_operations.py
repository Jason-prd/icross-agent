"""AI-powered operations data analysis.

Provides:
- replenish: AI inventory replenishment suggestions
- trend-commentary: Natural language trend commentary for charts
"""
from fastapi import APIRouter, HTTPException, Query
from icross.api.ai_utils import _extract_json, get_ai_llm

router = APIRouter(prefix="/operations-data", tags=["ai_operations"])


@router.post("/ai/replenish")
async def ai_replenish_suggest(
    shop_id: str = Query(...),
):
    """Analyze inventory and suggest replenishment quantities and timing."""
    from icross.services.ozon.client import OzonClient

    client = OzonClient()
    try:
        stocks = await client.get_analytics_stocks(shop_id, limit=50)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch stock data: {e}")

    items = stocks.get("result", stocks).get("items", [])
    if not items:
        return {"has_data": False, "message": "暂无库存数据"}

    stock_lines = []
    for it in items[:20]:
        name = it.get("name", "")
        sku = it.get("offer_id", "")
        present = it.get("present", 0)
        reserved = it.get("reserved", 0)
        days_sold = it.get("days_sold", 0)
        stock_lines.append(f"SKU:{sku} | 商品:{name} | 库存:{present} | 在途:{reserved} | 销量(天):{days_sold}")

    prompt = f"""你是 Ozon 库存管理专家。分析以下库存数据，给出补货建议。

库存数据:
{chr(10).join(stock_lines[:3000])}

返回 JSON:
{{"urgent": [{{"sku": "SKU号", "name": "商品名", "current_stock": 库存量, "suggested_replenish": 建议补货量, "reason": "原因"}}], "recommended": [{{...}}], "summary": "整体库存评价"}}"""

    llm = get_ai_llm("operations.replenish.suggest")
    response = await llm.ainvoke([{"role": "user", "content": prompt}])
    raw = response.content
    if isinstance(raw, list):
        raw = "".join(b.get("text", "") for b in raw if isinstance(b, dict))
    json_str, _ = _extract_json(raw.strip())
    result = {"urgent": [], "recommended": [], "summary": "分析完成"}
    if json_str:
        import json as jmod
        try:
            result = jmod.loads(json_str)
        except Exception:
            pass

    result["analyzed_items"] = len(stock_lines)
    return result


@router.post("/ai/trend-commentary")
async def ai_trend_commentary(
    shop_id: str = Query(...),
    metrics_json: str = Query(default=""),
):
    """Generate 1-2 sentence Chinese trend commentary for dashboard charts."""
    import json as jmod
    try:
        metrics = jmod.loads(metrics_json) if metrics_json else {}
    except Exception:
        metrics = {}

    if not metrics:
        from icross.services.ozon.client import OzonClient
        client = OzonClient()
        try:
            stocks = await client.get_analytics_stocks(shop_id, limit=10)
            items = stocks.get("result", stocks).get("items", [])
            metrics = {"total_items": len(items), "stock_summary": str(items[:5])[:500]}
        except Exception:
            pass

    prompt = f"""你是电商运营数据分析师。基于以下数据写 1-2 句中文趋势评述。

数据: {str(metrics)[:1000]}

返回 JSON:
{{"commentary": "趋势评述", "direction": "up|down|stable"}}"""

    llm = get_ai_llm("operations.trend.commentary")
    response = await llm.ainvoke([{"role": "user", "content": prompt}])
    raw = response.content
    if isinstance(raw, list):
        raw = "".join(b.get("text", "") for b in raw if isinstance(b, dict))
    json_str, _ = _extract_json(raw.strip())
    result = {"commentary": "数据趋势分析完成", "direction": "stable"}
    if json_str:
        import json as jmod
        try:
            result = jmod.loads(json_str)
        except Exception:
            pass
    return result
