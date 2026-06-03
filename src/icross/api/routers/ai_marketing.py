"""AI-powered marketing campaign analysis.

Provides:
- analyze-campaign: AI analysis of advertising campaign performance
"""
from fastapi import APIRouter, HTTPException, Query
from icross.api.ai_utils import _extract_json, get_ai_llm

router = APIRouter(prefix="/marketing", tags=["ai_marketing"])


@router.post("/ai/analyze-campaign/{campaign_id}")
async def ai_analyze_campaign(
    campaign_id: str,
    shop_id: str = Query(...),
):
    """Analyze ad campaign performance: ROAS, CTR, conversion, and optimization tips."""
    from icross.services.ozon.client import OzonClient

    client = OzonClient()
    try:
        cid = int(campaign_id)
        campaign = await client.get_ad_campaign(shop_id, cid)
        stats = await client.get_ad_campaign_stats(shop_id, cid, "")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch campaign data: {e}")

    title = campaign.get("title", campaign.get("name", f"Campaign {campaign_id}"))
    impressions = stats.get("impressions", 0)
    clicks = stats.get("clicks", 0)
    ctr = stats.get("ctr", 0)
    spend = stats.get("spend", 0)
    orders = stats.get("orders", 0)
    revenue = stats.get("revenue", 0)
    roas = stats.get("roas", 0)

    prompt = f"""你是 Ozon 广告投流分析专家。分析以下广告活动效果，给出优化建议。

广告活动: {title}
展示量: {impressions}
点击量: {clicks}
CTR: {ctr}%
花费: {spend} RUB
订单数: {orders}
收入: {revenue} RUB
ROAS: {roas}

返回 JSON:
{{"score": 0-100, "analysis": "性能分析", "strengths": ["优势1", "优势2"], "weaknesses": ["弱点"], "suggestions": [{{"action": "操作建议", "expected_impact": "预期效果"}}], "budget_recommendation": "预算建议"}}"""

    llm = get_ai_llm("marketing.campaign.analyze")
    response = await llm.ainvoke([{"role": "user", "content": prompt}])
    raw = response.content
    if isinstance(raw, list):
        raw = "".join(b.get("text", "") for b in raw if isinstance(b, dict))
    json_str, _ = _extract_json(raw.strip())
    result = {"score": 0, "analysis": "分析完成", "strengths": [], "weaknesses": [], "suggestions": [], "budget_recommendation": ""}
    if json_str:
        import json as jmod
        try:
            result = jmod.loads(json_str)
        except Exception:
            pass

    result["campaign_id"] = campaign_id
    result["title"] = title
    result["stats"] = {"impressions": impressions, "clicks": clicks, "ctr": ctr, "spend": spend, "orders": orders, "revenue": revenue, "roas": roas}
    return result
