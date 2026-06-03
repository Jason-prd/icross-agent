"""Vector-based category matching engine for Ozon categories.

Uses MiniMax embeddings for semantic similarity search across all Ozon categories,
followed by LLM-based re-ranking for final selection.

Usage:
    # Pre-compute embeddings for all categories
    await compute_and_cache_embeddings()

    # Full pipeline: product text -> vector search -> LLM re-rank -> best match
    result = await match_product_category("智能手机", "6.7寸屏幕 128GB 双卡")
"""

import json
import logging
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from icross.core.storage.ozon_data import CategoryStorage

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
_EMBEDDINGS_FILE = _DATA_DIR / "category_embeddings.json"
_BATCH_SIZE = 100


# ========================================================================
# Embeddings Model
# ========================================================================


def _get_embedder():
    """Get MiniMax embeddings model instance.

    Uses ``MINIMAX_API_KEY`` and ``MINIMAX_GROUP_ID`` from environment variables.

    Returns:
        An initialized ``MiniMaxEmbeddings`` instance.

    Raises:
        ImportError: If ``langchain_community`` is not installed.
    """
    from langchain_community.embeddings import MiniMaxEmbeddings

    return MiniMaxEmbeddings(model="embo-01")


# ========================================================================
# Cosine Similarity
# ========================================================================


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Args:
        a: First embedding vector.
        b: Second embedding vector.

    Returns:
        Cosine similarity in range [0, 1]. Returns 0 if either vector is
        zero-length or empty.
    """
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ========================================================================
# Embedding Computation & Caching
# ========================================================================


async def compute_and_cache_embeddings(shop_id: str | None = None) -> dict:
    """Load all categories from CategoryStorage, compute embeddings, cache to JSON.

    Category text for embedding = ``"{category_name} {type_name} {path}"`` where
    ``path`` is the full tree path from root (e.g. "Электроника / Смартфоны").

    Args:
        shop_id: Optional shop ID (currently unused since categories are global).

    Returns:
        A dict with status information:
        - ``success``: bool
        - ``total_categories``: int
        - ``cached_at``: ISO timestamp
        - ``error``: str (only on failure)
    """
    storage = CategoryStorage()
    # get_flattened_categories is async (reads from JSON store)
    categories = await storage.get_flattened_categories()

    if not categories:
        return {
            "success": False,
            "error": "分类树为空，请先调用 GET /api/categories/tree?refresh=true&shop_id=... 拉取分类数据",
        }

    # Build category texts for embedding
    # Format: "{category_name} {type_name} {path}"
    category_texts: list[str] = []
    category_ids: list[str] = []

    for cat in categories:
        name = cat.get("category_name", "") or ""
        type_name = cat.get("type_name", "") or ""
        path = cat.get("path", "") or ""
        text = f"{name} {type_name} {path}".strip()
        category_texts.append(text)
        category_ids.append(cat.get("id"))

    embedder = _get_embedder()
    all_embeddings: list[list[float]] = []

    # Compute embeddings in batches to avoid oversized requests
    for i in range(0, len(category_texts), _BATCH_SIZE):
        batch = category_texts[i : i + _BATCH_SIZE]
        try:
            batch_embeddings = embedder.embed_documents(batch)
            all_embeddings.extend(batch_embeddings)
            logger.info(
                "Computed embeddings for batch %d-%d (%d categories)",
                i,
                i + len(batch),
                len(categories),
            )
        except Exception as e:
            logger.error("Failed to compute embeddings for batch %d-%d: %s", i, i + len(batch), e)
            return {
                "success": False,
                "error": f"Embedding computation failed at batch {i}: {e}",
            }

    # Build cache structure
    cache = {
        "version": 1,
        "cached_at": datetime.now().isoformat(),
        "categories": [],
    }

    for i, cat in enumerate(categories):
        cache["categories"].append({
            "id": cat.get("id"),
            "description_category_id": cat.get("description_category_id"),
            "type_id": cat.get("type_id"),
            "category_name": cat.get("category_name"),
            "type_name": cat.get("type_name"),
            "path": cat.get("path"),
            "text": category_texts[i],
            "embedding": all_embeddings[i],
        })

    # Write to JSON file
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(_EMBEDDINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    logger.info("Cached %d category embeddings to %s", len(categories), _EMBEDDINGS_FILE)

    return {
        "success": True,
        "total_categories": len(categories),
        "cached_at": cache["cached_at"],
    }


def load_embeddings_cache() -> dict | None:
    """Load cached embeddings from JSON file.

    Returns:
        The cached embeddings dict, or ``None`` if the file does not exist
        or is corrupted.
    """
    if not _EMBEDDINGS_FILE.exists():
        return None
    try:
        with open(_EMBEDDINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning("Failed to load embeddings cache: %s", e)
        return None


# ========================================================================
# Vector Search
# ========================================================================


def find_matching_categories(product_text: str, top_k: int = 5) -> list[dict]:
    """Find top-k matching categories by cosine similarity.

    Embeds the product text using the same MiniMax model and compares
    against all cached category embeddings.

    Args:
        product_text: Product name/description text to match.
        top_k: Number of top results to return (default 5).

    Returns:
        List of candidate dicts, each containing:
        - ``description_category_id``: Ozon category ID
        - ``type_id``: Ozon type ID
        - ``category_name``: Category name
        - ``type_name``: Type name
        - ``path``: Full tree path
        - ``score``: Cosine similarity score

    Raises:
        ValueError: If no cached embeddings exist.
    """
    cache = load_embeddings_cache()
    if not cache or not cache.get("categories"):
        raise ValueError(
            "No cached embeddings found. Call compute_and_cache_embeddings() first "
            "or sync the category tree via GET /api/categories/tree?refresh=true&shop_id=..."
        )

    embedder = _get_embedder()
    query_embedding = embedder.embed_query(product_text)

    scored: list[dict[str, Any]] = []
    for cat in cache["categories"]:
        sim = cosine_similarity(query_embedding, cat["embedding"])
        scored.append({
            "description_category_id": cat["description_category_id"],
            "type_id": cat["type_id"],
            "category_name": cat["category_name"],
            "type_name": cat["type_name"],
            "path": cat["path"],
            "score": round(sim, 6),
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


# ========================================================================
# LLM Re-ranking
# ========================================================================


async def match_category_with_llm(
    product_name: str,
    product_description: str,
    top_candidates: list[dict],
) -> dict:
    """Use LLM to re-rank the top candidates and pick the best match.

    Sends the product info along with candidate categories to an LLM
    (MiniMax) for semantic re-ranking and final selection.

    Args:
        product_name: Product name in Chinese.
        product_description: Product description in Chinese.
        top_candidates: List of candidate dicts from vector search.

    Returns:
        A dict with:
        - ``description_category_id``: Chosen Ozon category ID
        - ``type_id``: Chosen Ozon type ID
        - ``category_name``: Category name
        - ``reason``: LLM's reasoning for the choice
    """
    from icross.api.ai_utils import get_ai_llm

    llm = get_ai_llm("category.match")

    # Build candidate list for the prompt
    candidate_lines = []
    for i, c in enumerate(top_candidates, 1):
        candidate_lines.append(
            f"{i}. ID={c['description_category_id']} TYPE={c['type_id']} "
            f"NAME={c['category_name']} TYPE_NAME={c['type_name']} "
            f"PATH={c['path']} SCORE={c['score']}"
        )
    candidate_text = "\n".join(candidate_lines)

    prompt = f"""你是一个Ozon分类匹配专家。根据产品信息，从以下候选分类中选择最合适的1个分类。

产品名称：{product_name}
产品描述：{product_description or '无'}

候选分类（按向量相似度排序）：
{candidate_text}

请从以上候选中选择最匹配的1个分类。考虑产品名称、描述与分类名称、路径的语义匹配。
如果候选分类都不太匹配，选择最接近的即可。

只返回JSON格式，不要其他文字：
{{"description_category_id": 分类ID, "type_id": 类型ID, "category_name": "分类名称", "reason": "选择理由"}}"""

    response = await llm.ainvoke([{"role": "user", "content": prompt}])

    # Handle various response formats (Anthropic SDK list blocks, etc.)
    raw_content = response.content
    if isinstance(raw_content, list):
        texts = []
        for block in raw_content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))
        raw_content = "\n".join(texts)

    content = raw_content.strip()

    # Strip code fences if present
    if "```json" in content:
        start = content.find("```json") + 7
        end = content.find("```", start)
        content = content[start:end].strip()
    elif "```" in content:
        start = content.find("```") + 3
        end = content.find("```", start)
        content = content[start:end].strip()

    result = json.loads(content)

    return {
        "description_category_id": result.get("description_category_id"),
        "type_id": result.get("type_id"),
        "category_name": result.get("category_name"),
        "reason": result.get("reason", ""),
    }


# ========================================================================
# Full Pipeline
# ========================================================================


async def match_product_category(
    product_name: str,
    product_description: str = "",
) -> dict:
    """Full pipeline: embed -> similarity search -> LLM re-rank -> return result.

    Args:
        product_name: Product name in Chinese.
        product_description: Optional product description in Chinese.

    Returns:
        A dict with:
        - ``success``: bool
        - ``match``: Selected category dict (``description_category_id``,
          ``type_id``, ``category_name``, ``reason``)
        - ``candidates``: List of top-5 candidates from vector search
        - ``method``: ``"vector_llm"`` or ``"llm_fallback"``
        - ``error``: Error message if failed
    """
    try:
        # Step 1: Vector similarity search
        product_text = f"{product_name} {product_description}".strip()
        candidates = find_matching_categories(product_text, top_k=5)

        if not candidates:
            return {"success": False, "error": "未找到任何匹配的分类候选", "method": "vector"}

        # Step 2: LLM re-ranking
        match = await match_category_with_llm(
            product_name=product_name,
            product_description=product_description,
            top_candidates=candidates,
        )

        return {
            "success": True,
            "match": match,
            "candidates": candidates,
            "method": "vector_llm",
        }

    except ValueError as e:
        # No cached embeddings -- return so caller can fall back to LLM-only
        return {
            "success": False,
            "error": str(e),
            "method": "vector_unavailable",
        }
    except Exception as e:
        logger.exception("Category matching pipeline failed")
        return {
            "success": False,
            "error": f"分类匹配失败: {e}",
            "method": "error",
        }
