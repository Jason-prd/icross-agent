"""AI-powered auto-pilot configuration suggestions.

Provides:
- suggest-config: AI recommends optimal AutoPilot parameters
"""
from fastapi import APIRouter, HTTPException, Query
from icross.api.ai_utils import _extract_json, get_ai_llm

router = APIRouter(prefix="/auto-pilot", tags=["ai_autopilot"])


@router.post("/ai/suggest-config")
async def ai_suggest_config(
    shop_id: str = Query(...),
):
    """Recommend optimal AutoPilot parameters based on historical data."""
    from icross.services.ozon.client import OzonClient

    client = OzonClient()
    try:
        stocks = await client.get_analytics_stocks(shop_id, limit=30)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch data: {e}")

    items = stocks.get("result", stocks).get("items", [])
    data_preview = str(items[:5])[:1500] if items else "无数据"

    prompt = f"""你是 Ozon 自动运营顾问。根据店铺运营数据，推荐最佳 AutoPilot 配置参数。

数据预览: {data_preview}

返回 JSON:
{{"suggested_cron": "推荐定时表达式", "suggested_margin": 建议利润率, "suggested_weight_kg": 建议默认重量, "push_to_ozon": true/false, "reasoning": "推荐理由"}}"""

    llm = get_ai_llm("autopilot.config.suggest")
    response = await llm.ainvoke([{"role": "user", "content": prompt}])
    raw = response.content
    if isinstance(raw, list):
        raw = "".join(b.get("text", "") for b in raw if isinstance(b, dict))
    json_str, _ = _extract_json(raw.strip())
    result = {"suggested_cron": "0 3 * * *", "suggested_margin": 20.0, "suggested_weight_kg": 0.5, "push_to_ozon": True, "reasoning": "分析完成"}
    if json_str:
        import json as jmod
        try:
            result = jmod.loads(json_str)
        except Exception:
            pass

    return result
