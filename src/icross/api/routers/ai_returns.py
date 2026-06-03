"""AI-powered return analysis endpoints.

Provides:
- return-decision: AI suggests accept/reject/partial_refund for a return
- pattern-analysis: AI analyzes return patterns over time
"""
from fastapi import APIRouter, HTTPException, Query
from icross.api.ai_utils import _extract_json, get_ai_llm

router = APIRouter(prefix="/returns", tags=["ai_returns"])


@router.post("/{return_id}/ai/decision")
async def ai_return_decision(
    return_id: str,
    shop_id: str = Query(...),
):
    """Analyze a return and suggest decision (accept/reject/partial_refund)."""
    from icross.services.ozon.client import OzonClient

    client = OzonClient()
    try:
        return_data = await client.get_return_info(shop_id, int(return_id))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch return info: {e}")

    if not return_data:
        raise HTTPException(status_code=404, detail="Return not found")

    reason = return_data.get("reason", "") or return_data.get("return_reason", "") or ""
    product_name = return_data.get("product_name", "") or ""
    price = return_data.get("price", 0) or 0

    prompt = f"""你是一个 Ozon 退货处理专家。请分析以下退货信息并给出决策建议。

退货信息:
- 商品: {product_name}
- 退货原因: {reason}
- 退货金额: {price} RUB

请返回 JSON 格式:
{{
    "recommendation": "accept|reject|partial_refund",
    "confidence": "high|medium|low",
    "reasoning": "分析理由",
    "suggested_refund_amount": 退款金额(卢布),
    "risks": ["风险1", "风险2"]
}}

注意: 若金额小且原因合理→建议同意。原因不明确或买家责任→建议拒绝。部分责任→部分退款。"""

    llm = get_ai_llm("return.decision.suggest")
    response = await llm.ainvoke([{"role": "user", "content": prompt}])
    raw = response.content
    if isinstance(raw, list):
        texts = []
        for block in raw:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))
        raw = "\n".join(texts)
    json_str, _ = _extract_json(raw.strip())
    parsed = {
        "recommendation": "accept",
        "confidence": "medium",
        "reasoning": "AI 分析失败，请人工判断",
        "suggested_refund_amount": int(price),
        "risks": [],
    }
    if json_str:
        import json as jmod
        try:
            parsed = jmod.loads(json_str)
        except Exception:
            pass

    parsed["return_id"] = return_id
    parsed["original_reason"] = reason
    return parsed


@router.post("/ai/pattern-analysis")
async def ai_return_pattern_analysis(
    shop_id: str = Query(...),
    days: int = Query(30, ge=1, le=365),
):
    """Analyze return patterns over a time period."""
    from icross.services.ozon.client import OzonClient

    client = OzonClient()
    try:
        returns_data = await client.list_returns(shop_id, limit=100)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch returns: {e}")

    returns_list = returns_data.get("returns", [])
    if not returns_list:
        return {
            "has_data": False,
            "message": "近期无退货数据",
            "analysis": "暂无退货数据可供分析",
        }

    reasons = {}
    statuses = {}
    total_amount = 0.0
    for r in returns_list:
        reason = r.get("reason", "") or r.get("return_reason", "") or "未知"
        reasons[reason] = reasons.get(reason, 0) + 1
        s = r.get("status", "") or "未知"
        statuses[s] = statuses.get(s, 0) + 1
        total_amount += float(r.get("price", 0) or 0)

    summary = f"""近期退货统计:
- 总退货数: {len(returns_list)}
- 总金额: {total_amount:.2f} RUB
- 原因分布: {', '.join(f'{k}({v}次)' for k, v in sorted(reasons.items(), key=lambda x: -x[1]))}
- 状态分布: {', '.join(f'{k}({v}件)' for k, v in sorted(statuses.items(), key=lambda x: -x[1]))}"""

    prompt = f"""你是一个 Ozon 退货数据分析专家。请分析以下退货统计数据，识别趋势和问题。

{summary}

请返回 JSON 格式:
{{
    "summary": "总体分析摘要",
    "key_findings": ["发现1", "发现2", "发现3"],
    "top_reasons": ["原因1", "原因2"],
    "suggestions": ["建议1", "建议2", "建议3"],
    "risk_level": "high|medium|low"
}}"""

    llm = get_ai_llm("return.pattern.analyze")
    response = await llm.ainvoke([{"role": "user", "content": prompt}])
    raw = response.content
    if isinstance(raw, list):
        texts = []
        for block in raw:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))
        raw = "\n".join(texts)
    json_str, _ = _extract_json(raw.strip())
    parsed = {
        "summary": "分析失败",
        "key_findings": [],
        "top_reasons": [],
        "suggestions": [],
        "risk_level": "medium",
    }
    if json_str:
        import json as jmod
        try:
            parsed = jmod.loads(json_str)
        except Exception:
            pass

    parsed["has_data"] = True
    parsed["total_returns"] = len(returns_list)
    parsed["total_amount"] = round(total_amount, 2)
    return parsed
