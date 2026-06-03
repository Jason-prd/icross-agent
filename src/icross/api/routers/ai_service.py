"""AI-powered customer service analysis endpoints.

Provides:
- suggest-reply: Generate Russian reply from chat history context
- suggest-answer: Auto-answer buyer product questions
- analyze-review: Sentiment + key issues from product reviews
"""
from fastapi import APIRouter, HTTPException, Query
from icross.api.ai_utils import _extract_json, get_ai_llm

router = APIRouter(prefix="/service", tags=["ai_service"])


@router.post("/ai/suggest-reply/{chat_id}")
async def ai_suggest_reply(
    chat_id: str,
    shop_id: str = Query(...),
    limit: int = Query(20, ge=1, le=50),
):
    """Generate a Russian reply suggestion based on recent chat history."""
    from icross.services.ozon.client import OzonClient

    client = OzonClient()
    try:
        history = await client.get_chat_history(shop_id, chat_id, limit)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch chat history: {e}")

    messages = history.get("result", {}).get("messages", [])
    if not messages:
        return {"has_data": False, "message": "暂无聊天记录"}

    chat_lines = []
    for msg in messages[-10:]:
        sender = "买家" if msg.get("direction") == "incoming" or msg.get("user", {}).get("is_buyer") else "卖家"
        text = msg.get("text", "").strip()
        if text:
            chat_lines.append(f"{sender}: {text[:200]}")

    prompt = f"""你是 Ozon 卖家客服助手。基于以下聊天历史，生成一段俄语回复。

聊天记录:
{chr(10).join(chat_lines)}

返回 JSON:
{{"reply_ru": "俄语回复", "reply_cn": "中文译文", "tone": "风格标签(友好/专业/致歉/解释)", "next_action": "建议下一步"}}"""

    llm = get_ai_llm("service.reply.suggest")
    response = await llm.ainvoke([{"role": "user", "content": prompt}])
    raw = response.content
    if isinstance(raw, list):
        raw = "".join(b.get("text", "") for b in raw if isinstance(b, dict))
    json_str, _ = _extract_json(raw.strip())
    result = {"reply_ru": "", "reply_cn": "", "tone": "专业", "next_action": ""}
    if json_str:
        import json as jmod
        try:
            result = jmod.loads(json_str)
        except Exception:
            pass

    result["chat_id"] = chat_id
    return result


@router.post("/ai/suggest-answer/{q_id}")
async def ai_suggest_answer(
    q_id: str,
    shop_id: str = Query(...),
):
    """Generate a Russian answer for a buyer question about a product."""
    from icross.services.ozon.client import OzonClient

    client = OzonClient()
    try:
        questions = await client.list_questions(shop_id, status="waiting_answer")
        questions_list = questions.get("result", questions)
        question_items = questions_list.get("items", []) if isinstance(questions_list, dict) else []
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch questions: {e}")

    if not question_items:
        return {"has_data": False, "message": "暂无待回答问题"}

    target = next((q for q in question_items if str(q.get("id")) == q_id), None)
    if not target:
        target = question_items[0] if question_items else None

    if not target:
        raise HTTPException(status_code=404, detail="Question not found")

    q_text = target.get("text", "")
    product_name = target.get("product_name", target.get("offer_id", ""))

    prompt = f"""你是 Ozon 卖家客服。买家对商品 "{product_name}" 提问: "{q_text}"

请生成俄语回答:
返回 JSON:
{{"answer_ru": "俄语回答", "answer_cn": "中文译文", "is_helpful": true}}"""

    llm = get_ai_llm("service.question.answer")
    response = await llm.ainvoke([{"role": "user", "content": prompt}])
    raw = response.content
    if isinstance(raw, list):
        raw = "".join(b.get("text", "") for b in raw if isinstance(b, dict))
    json_str, _ = _extract_json(raw.strip())
    result = {"answer_ru": "", "answer_cn": "", "is_helpful": True}
    if json_str:
        import json as jmod
        try:
            result = jmod.loads(json_str)
        except Exception:
            pass

    result["question_id"] = q_id
    result["question_text"] = q_text
    return result


@router.post("/ai/analyze-review/{review_id}")
async def ai_analyze_review(
    review_id: str,
    shop_id: str = Query(...),
):
    """Analyze product review: sentiment, key issues, suggested response."""
    from icross.services.ozon.client import OzonClient

    client = OzonClient()
    try:
        reviews = await client.list_reviews(shop_id, limit=50)
        reviews_list = reviews.get("result", reviews)
        review_items = reviews_list.get("reviews", []) if isinstance(reviews_list, dict) else []
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch reviews: {e}")

    target = next((r for r in review_items if str(r.get("id")) == review_id), None)

    if not target:
        raise HTTPException(status_code=404, detail="Review not found")

    text = target.get("text", "")
    rating = target.get("rating", 0)
    product_name = target.get("product_name", "")

    prompt = f"""你是 Ozon 评价分析专家。分析以下商品评价:

商品: {product_name}
评分: {rating}/5
内容: {text[:500]}

返回 JSON:
{{"sentiment": "positive|neutral|negative", "key_issues": ["问题1", "问题2"], "suggested_reply_ru": "建议俄语回复", "needs_attention": true/false}}"""

    llm = get_ai_llm("service.review.analyze")
    response = await llm.ainvoke([{"role": "user", "content": prompt}])
    raw = response.content
    if isinstance(raw, list):
        raw = "".join(b.get("text", "") for b in raw if isinstance(b, dict))
    json_str, _ = _extract_json(raw.strip())
    result = {"sentiment": "neutral", "key_issues": [], "suggested_reply_ru": "", "needs_attention": False}
    if json_str:
        import json as jmod
        try:
            result = jmod.loads(json_str)
        except Exception:
            pass

    result["review_id"] = review_id
    result["rating"] = rating
    return result
