"""REST API endpoints for Ozon category management."""

import json
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from icross.core.storage.ozon_data import CategoryStorage

router = APIRouter()
_category_store = CategoryStorage()


class CategoryMatchRequest(BaseModel):
    product_name_cn: str
    product_description_cn: str = ""
    top_n: int = 5


# ============ Category Tree ============


@router.get("/categories/tree")
async def get_category_tree(
    shop_id: str = Query(default=""),
    refresh: bool = Query(default=False),
    language: str = Query(default="DEFAULT"),
):
    """Get flattened category tree. Cached by default; pass ?refresh=true to re-fetch from Ozon."""
    if refresh:
        if not shop_id:
            raise HTTPException(status_code=400, detail="refresh=True requires shop_id")
        from icross.services.ozon import get_ozon_client
        client = get_ozon_client()
        tree = await client.get_category_tree(shop_id, language=language)
        count = await _category_store.save_category_tree(tree.get("categories", []))
        return {"refreshed": True, "leaf_count": count}

    categories = await _category_store.get_flattened_categories()
    return {"categories": categories, "total": len(categories)}


@router.get("/categories/search")
async def search_categories(
    q: str = Query(default="", min_length=1),
    limit: int = Query(default=20, le=100),
):
    """Search categories by name."""
    if not q:
        raise HTTPException(status_code=400, detail="请提供搜索关键词 q")
    results = await _category_store.search_categories(q, limit=limit)
    return {"categories": results, "total": len(results)}


# ============ Category Attributes ============


@router.get("/categories/{category_id}/attributes")
async def get_category_attributes_route(
    category_id: int,
    type_id: int = Query(default=...),
    shop_id: str = Query(default=""),
    refresh: bool = Query(default=False),
    language: str = Query(default="DEFAULT"),
):
    """Get attributes for a category+type. Cached; pass ?refresh=true to re-fetch."""
    if refresh:
        if not shop_id:
            raise HTTPException(status_code=400, detail="refresh=True requires shop_id")
        from icross.services.ozon import get_ozon_client
        client = get_ozon_client()
        data = await client.get_category_attributes(shop_id, category_id, type_id, language=language)
        attrs = data.get("attributes", [])
        await _category_store.save_category_attributes(category_id, type_id, attrs)
        return {
            "category_id": category_id,
            "type_id": type_id,
            "attributes": attrs,
            "refreshed": True,
        }

    cached = await _category_store.get_category_attributes(category_id, type_id)
    if cached:
        return {
            "category_id": category_id,
            "type_id": type_id,
            "attributes": cached,
            "cached": True,
        }
    # If not cached and no shop_id, return empty
    if not shop_id:
        return {
            "category_id": category_id,
            "type_id": type_id,
            "attributes": [],
            "cached": False,
            "message": "No cached data. Pass ?refresh=true&shop_id=... to fetch."
        }
    # Try to fetch
    from icross.services.ozon import get_ozon_client
    client = get_ozon_client()
    data = await client.get_category_attributes(shop_id, category_id, type_id, language=language)
    attrs = data.get("attributes", [])
    await _category_store.save_category_attributes(category_id, type_id, attrs)
    return {
        "category_id": category_id,
        "type_id": type_id,
        "attributes": attrs,
        "refreshed": True,
    }


@router.get("/categories/attributes/{attribute_id}/values")
async def get_attribute_values(
    attribute_id: int,
    category_id: int = Query(default=...),
    type_id: int = Query(default=...),
    shop_id: str = Query(default=...),
    search: str | None = Query(default=None),
    language: str = Query(default="DEFAULT"),
):
    """Get dictionary values for a category attribute. Optionally search."""
    from icross.services.ozon import get_ozon_client
    client = get_ozon_client()

    if search:
        if len(search) < 2:
            raise HTTPException(status_code=400, detail="搜索关键词至少2个字符")
        result = await client.search_category_attribute_values(
            shop_id, category_id, type_id, attribute_id, search, limit=100
        )
    else:
        result = await client.get_category_attribute_values(
            shop_id, category_id, type_id, attribute_id, language=language
        )
    return result


# ============ Category Matching (Vector + LLM) ============


async def _llm_only_match(product_name_cn: str, product_description_cn: str = "") -> dict:
    """Fallback: use LLM-only matching with up to 200 categories (context window limit).

    This is the original matching approach, kept as fallback when vector
    embeddings are not available.
    """
    from icross.agents.master.tools_product import _run_async_in_tool, _safe_format

    categories = await _category_store.get_flattened_categories()
    if not categories:
        return {"success": False, "error": "分类树为空，请先拉取分类数据"}

    cat_lines = []
    for c in categories[:200]:
        cat_lines.append(
            f"ID={c['description_category_id']} TYPE={c['type_id']} "
            f"NAME={c['category_name']} PATH={c['path']}"
        )
    cat_text = "\n".join(cat_lines)

    template = """你是一个Ozon分类匹配专家。根据产品信息，从以下分类树中选择最合适的分类。

产品名称：{product_name_cn}
产品描述：{product_description_cn or '无'}

可选分类（ID=分类ID TYPE=类型ID NAME=名称 PATH=路径）：
{cat_text}

请选择最匹配的1个分类。考虑产品名称、描述与分类名称和路径的语义匹配。
只返回JSON格式，不要其他文字：
{{"description_category_id": 分类ID, "type_id": 类型ID, "category_name": "分类名称", "reason": "选择理由"}}"""

    prompt = _safe_format(template,
        product_name_cn=product_name_cn,
        product_description_cn=product_description_cn or "",
        cat_text=cat_text,
    )

    try:
        from icross.api.ai_utils import get_ai_llm
        llm = get_ai_llm("category.match")
        response = _run_async_in_tool(llm.ainvoke([{"role": "user", "content": prompt}]))

        raw_content = response.content
        if isinstance(raw_content, list):
            texts = []
            for block in raw_content:
                if isinstance(block, dict) and block.get("type") == "text":
                    texts.append(block.get("text", ""))
            raw_content = "\n".join(texts)
        content = raw_content.strip()

        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            content = content[start:end].strip()
        elif "```" in content:
            start = content.find("```") + 3
            end = content.find("```", start)
            content = content[start:end].strip()

        result = json.loads(content)

        all_matches = []
        for c in categories:
            if (c["description_category_id"] == result.get("description_category_id") and
                c["type_id"] == result.get("type_id")):
                all_matches.append(c)

        return {
            "success": True,
            "match": result,
            "category_detail": all_matches[0] if all_matches else None,
            "method": "llm_fallback",
        }
    except Exception as e:
        return {"success": False, "error": str(e), "method": "llm_fallback"}


@router.post("/categories/match")
async def match_category(
    body: CategoryMatchRequest,
    refresh_embeddings: bool = Query(default=False),
):
    """Match a Chinese product name to the best Ozon category.

    Uses vector-based semantic search (MiniMax embeddings) across ALL
    categories, then LLM re-ranking. Falls back to LLM-only matching
    (limited to 200 categories) if embeddings are not cached.

    Query params:
        refresh_embeddings: If True, re-compute embeddings from cached
            category tree before matching.

    Request body:
        product_name_cn: Product name in Chinese (required).
        product_description_cn: Optional product description in Chinese.
        top_n: Number of candidates (default 5, unused in vector flow).
    """
    from icross.services.category_matcher import (
        compute_and_cache_embeddings,
        match_product_category,
    )

    # Step 0: Optionally refresh embeddings
    if refresh_embeddings:
        embed_result = await compute_and_cache_embeddings()
        if not embed_result.get("success"):
            return {
                "success": False,
                "error": f"Embedding refresh failed: {embed_result.get('error')}",
            }

    # Step 1: Try vector-based matching
    result = await match_product_category(
        product_name=body.product_name_cn,
        product_description=body.product_description_cn,
    )

    if result.get("success"):
        match = result["match"]
        return {
            "success": True,
            "match": match,
            "candidates": result.get("candidates"),
            "method": result.get("method", "vector_llm"),
        }

    # Step 2: Fall back to LLM-only matching
    if result.get("method") == "vector_unavailable":
        fallback = await _llm_only_match(body.product_name_cn, body.product_description_cn)
        if fallback.get("success"):
            return {
                "success": True,
                "match": fallback["match"],
                "category_detail": fallback.get("category_detail"),
                "method": "llm_fallback",
                "note": "Embeddings not cached. Use ?refresh_embeddings=true to enable vector search.",
            }
        return fallback

    # Propagate error from vector matching
    return result
