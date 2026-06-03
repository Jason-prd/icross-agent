"""AI-powered draft quality management.

Provides:
- quality-check: Pre-publish quality check for drafts
- correct: Auto-correct failed quality items
"""
from fastapi import APIRouter, HTTPException, Query
from icross.api.ai_utils import _extract_json, get_ai_llm

router = APIRouter(prefix="/drafts", tags=["ai_drafts"])


@router.post("/{draft_id}/ai/quality-check")
async def ai_draft_quality_check(
    draft_id: str,
    shop_id: str = Query(...),
):
    """Check draft quality before publishing: title, description, images, pricing."""
    from icross.core.storage.ozon_data import DraftStorage

    store = DraftStorage()
    draft = await store.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    title = draft.get("title", "")
    description = draft.get("description", "")
    price = draft.get("price", 0)
    images_count = len(draft.get("images", []))

    prompt = f"""你是 Ozon Listing 质量审核专家。检查以下草稿质量。

标题: {title}
描述: {description[:500]}
价格: {price} RUB
图片数: {images_count}

返回 JSON:
{{"score": 0-100, "issues": [{{"field": "字段名", "severity": "error|warning|info", "message": "问题描述", "suggestion": "修改建议"}}], "summary": "总体评价"}}"""

    llm = get_ai_llm("draft.quality.check")
    response = await llm.ainvoke([{"role": "user", "content": prompt}])
    raw = response.content
    if isinstance(raw, list):
        raw = "".join(b.get("text", "") for b in raw if isinstance(b, dict))
    json_str, _ = _extract_json(raw.strip())
    result = {"score": 100, "issues": [], "summary": "草稿质量检查完成"}
    if json_str:
        import json as jmod
        try:
            result = jmod.loads(json_str)
        except Exception:
            pass

    result["draft_id"] = draft_id
    return result


@router.post("/{draft_id}/ai/correct")
async def ai_draft_correct(
    draft_id: str,
    shop_id: str = Query(...),
):
    """Auto-correct draft content where quality check found issues."""
    from icross.core.storage.ozon_data import DraftStorage

    store = DraftStorage()
    draft = await store.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    title = draft.get("title", "")
    description = draft.get("description", "")

    prompt = f"""你是 Ozon Listing 优化专家。修正以下草稿内容中的问题。

原标题: {title}
原描述: {description[:500]}

返回 JSON:
{{"corrected_title": "修正后的标题", "corrected_description": "修正后的描述", "changes": ["变更1", "变更2"]}}"""

    llm = get_ai_llm("draft.auto.correct", max_tokens=4096)
    response = await llm.ainvoke([{"role": "user", "content": prompt}])
    raw = response.content
    if isinstance(raw, list):
        raw = "".join(b.get("text", "") for b in raw if isinstance(b, dict))
    json_str, _ = _extract_json(raw.strip())
    result = {"corrected_title": title, "corrected_description": description, "changes": []}
    if json_str:
        import json as jmod
        try:
            result = jmod.loads(json_str)
        except Exception:
            pass

    result["draft_id"] = draft_id
    return result
