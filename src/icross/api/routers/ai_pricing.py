"""AI-powered competitive pricing analysis.

Provides:
- competitive-analysis: Analyze pricing strategy and optimization
"""
from fastapi import APIRouter, HTTPException, Query
from icross.api.ai_utils import _extract_json, get_ai_llm

router = APIRouter(prefix="/pricing", tags=["ai_pricing"])


@router.post("/ai/competitive-analysis/{product_id}")
async def ai_competitive_analysis(
    product_id: str,
    shop_id: str = Query(...),
):
    """Analyze pricing competitiveness for a product considering Ozon fees structure."""
    from icross.services.ozon.client import OzonClient

    client = OzonClient()
    try:
        pid = int(product_id)
        product = await client.get_product_info(shop_id, pid)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch product: {e}")

    price = product.get("price", 0)
    name = product.get("name", product.get("title", f"Product {product_id}"))
    category = product.get("category", "")
    stocks = product.get("stocks", {}).get("present", product.get("stock", 0))

    prompt = f"""你是 Ozon 定价策略专家。分析以下商品的定价竞争力。

商品: {name}
类目: {category}
当前售价: {price} RUB
当前库存: {stocks}

请考虑 Ozon 佣金阶梯、物流费用、市场行情，给出定价建议。

返回 JSON:
{{"current_competitiveness": "high|medium|low", "suggested_price_range": {{"min": 最低价, "max": 最高价, "optimal": 最优价}}, "price_adjustment_tips": ["建议1", "建议2"], "competition_notes": "竞争分析"}}"""

    llm = get_ai_llm("pricing.competitive.analyze")
    response = await llm.ainvoke([{"role": "user", "content": prompt}])
    raw = response.content
    if isinstance(raw, list):
        raw = "".join(b.get("text", "") for b in raw if isinstance(b, dict))
    json_str, _ = _extract_json(raw.strip())
    result = {"current_competitiveness": "medium", "suggested_price_range": {"min": price, "max": price, "optimal": price}, "price_adjustment_tips": [], "competition_notes": ""}
    if json_str:
        import json as jmod
        try:
            result = jmod.loads(json_str)
        except Exception:
            pass

    result["product_id"] = product_id
    result["current_price"] = price
    return result
