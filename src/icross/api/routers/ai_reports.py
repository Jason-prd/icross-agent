"""AI-powered report summary generation.

Provides:
- generate-summary: Generate executive summary from report data
"""
from fastapi import APIRouter, HTTPException, Query
from icross.api.ai_utils import _extract_json, get_ai_llm

router = APIRouter(prefix="/reports", tags=["ai_reports"])


@router.post("/ai/generate-summary")
async def ai_generate_summary(
    report_id: str = Query(...),
    shop_id: str = Query(...),
):
    """Generate a Chinese executive summary for a data report."""
    from icross.services.report_service import get_report_data
    from pathlib import Path

    try:
        report = get_report_data(report_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Report not found: {e}")

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # Extract key data points for the prompt
    report_type = report.get("type", "未知")
    rows = report.get("data", report.get("rows", []))

    # Build compact data summary
    data_preview = str(rows[:500]) if isinstance(rows, list) else str(rows)[:2000]

    prompt = f"""你是 Ozon 电商数据分析师。请为以下 {report_type} 报表生成中文执行摘要。

报告类型: {report_type}
数据预览: {data_preview[:2000]}

返回 JSON:
{{"summary": "3-5句话的执行摘要", "key_metrics": [{{"name": "指标名", "value": "值", "trend": "up|down|stable"}}], "recommendations": ["建议1", "建议2"]}}"""

    llm = get_ai_llm("report.summary.generate", max_tokens=2048)
    response = await llm.ainvoke([{"role": "user", "content": prompt}])
    raw = response.content
    if isinstance(raw, list):
        raw = "".join(b.get("text", "") for b in raw if isinstance(b, dict))
    json_str, _ = _extract_json(raw.strip())
    result = {"summary": "报表摘要生成完成", "key_metrics": [], "recommendations": []}
    if json_str:
        import json as jmod
        try:
            result = jmod.loads(json_str)
        except Exception:
            pass

    result["report_id"] = report_id
    result["report_type"] = report_type
    return result
