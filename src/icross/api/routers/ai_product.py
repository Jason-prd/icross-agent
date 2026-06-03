"""AI-powered product editing endpoints (AGI + AIGC).

Provides LLM-assisted optimization for product titles, descriptions,
attributes, and quality checking — referencing Ozon platform rules.
"""

import json
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from icross.services.ozon_costs import CNY_TO_RUB

router = APIRouter()


# ── Request / Response models ─────────────────────────────────────


class OptimizeTitleRequest(BaseModel):
    title: str = ""
    category: str = ""
    keywords: list[str] = []


class GenerateDescriptionRequest(BaseModel):
    name: str = ""
    category: str = ""
    attributes: list[dict[str, Any]] = []
    description: str = ""


class QualityCheckResponse(BaseModel):
    score: int
    items: list[dict[str, Any]]
    summary: str


# ── Helpers ───────────────────────────────────────────────────────


def _extract_json(text: str) -> tuple[str | None, str | None]:
    """Extract JSON object/array from LLM response (strip markdown).

    Returns:
        (json_str, raw_text) — json_str is the extracted JSON or None,
        raw_text is the cleaned text for fallback display.
    """
    raw = text.strip()

    # Strip markdown code blocks
    text = raw
    if "```json" in text:
        text = text[text.find("```json") + 7:]
        text = text[:text.find("```")] if "```" in text else text
    elif "```" in text:
        text = text[text.find("```") + 3:]
        text = text[:text.find("```")] if "```" in text else text

    text = text.strip()

    # Direct parse (fast path)
    try:
        json.loads(text)
        return text, raw
    except json.JSONDecodeError:
        pass

    # Try to find the outermost JSON object/array by brace counting
    # and validate each candidate
    for pair in [("{", "}"), ("[", "]")]:
        start = text.find(pair[0])
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            # Skip string contents to avoid counting braces inside strings
            ch = text[i]
            if ch == '"':
                i += 1
                while i < len(text):
                    if text[i] == '\\':
                        i += 2
                        continue
                    if text[i] == '"':
                        break
                    i += 1
                continue
            if ch == pair[0]:
                depth += 1
            elif ch == pair[1]:
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    try:
                        json.loads(candidate)
                        return candidate, raw
                    except json.JSONDecodeError:
                        # Found a balanced brace pair but invalid JSON — continue
                        # looking (maybe there's a valid outer object)
                        continue

    # Fallback: try to find *any* substring that parses as JSON
    for m in re.finditer(r'\{[^{}]*\}', text):
        try:
            json.loads(m.group())
            return m.group(), raw
        except json.JSONDecodeError:
            continue

    return None, raw


def _call_llm(prompt: str, temperature: float = 0.3, max_tokens: int = 2048, feature_key: str = "product.quality.check") -> str:
    """Call LLM and return text response."""
    from icross.agents.master.tools_product import _run_async_in_tool
    from icross.api.ai_utils import get_ai_llm

    llm = get_ai_llm(feature_key, temperature=temperature, max_tokens=max_tokens)
    response = _run_async_in_tool(llm.ainvoke([{"role": "user", "content": prompt}]))

    raw = response.content
    if isinstance(raw, list):
        texts = []
        for block in raw:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))
        raw = "\n".join(texts)
    return raw.strip()


def _search_rules(query: str, limit: int = 5) -> str:
    """Search Ozon rules KB and return concatenated rule excerpts."""
    from icross.services.ozon_rules import OzonRuleKB
    kb = OzonRuleKB()
    results = kb.search(query, limit=limit)
    if not results:
        return "（未找到相关规则）"
    parts = []
    for r in results:
        title = r.get("title", "")
        content = r.get("content", "")[:800]
        parts.append(f"【{title}】\n{content}")
    return "\n\n---\n\n".join(parts)


async def _load_product(product_id: str) -> dict[str, Any]:
    """Load product from storage or raise 404."""
    from icross.core.storage.ozon_data import ProductStorage
    product = await ProductStorage().get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


# ── Endpoints ─────────────────────────────────────────────────────


@router.post("/products/{product_id}/ai/optimize-title")
async def ai_optimize_title(product_id: str, body: OptimizeTitleRequest):
    """AI-optimize product title based on Ozon rules."""
    rules = _search_rules("商品标题 要求 SEO 规则")
    category = body.category or ""

    prompt = f"""你是一个 Ozon 电商平台的标题优化专家。请根据以下 Ozon 规则优化商品标题。

参考规则：
{rules}

当前标题：{body.title or "（空）"}
类目：{category or "未分类"}
关键词：{', '.join(body.keywords) if body.keywords else "无"}

要求：
1. 标题长度 50-150 字符（俄语）
2. 包含核心关键词（优先放在前面）
3. 符合俄语文法，自然流畅
4. 禁止营销词（скидка, лучший, супер 等）
5. 格式：关键词 + 产品名称 + 核心特性/规格

返回 JSON 格式：
{{"title": "优化后的俄语标题", "reason": "简述修改理由"}}
只返回 JSON，不要其他文字。"""

    result = _call_llm(prompt, feature_key="product.title.optimize")
    json_str, raw_text = _extract_json(result)
    if json_str:
        try:
            parsed = json.loads(json_str)
            title = parsed.get("title", "").strip()
            if not title:
                # JSON parsed but empty title — use raw as fallback
                parsed = {"title": raw_text[:500], "reason": "LLM 返回标题为空，使用原始响应"}
        except json.JSONDecodeError:
            parsed = {"title": raw_text[:500], "reason": "LLM 返回格式异常，请手动调整"}
    else:
        parsed = {"title": raw_text[:500] or body.title, "reason": "LLM 返回格式异常，请手动调整"}
    return {"product_id": product_id, "original_title": body.title, **parsed}


@router.post("/products/{product_id}/ai/generate-description")
async def ai_generate_description(product_id: str, body: GenerateDescriptionRequest):
    """AI-generate product description based on Ozon rules."""
    rules = _search_rules("商品描述 规范 要求")
    category = body.category or ""

    # Build attributes summary
    attr_lines = []
    if body.attributes:
        for a in body.attributes:
            aid = a.get("id")
            name = a.get("name", f"attr_{aid}")
            vals = a.get("values", [])
            val_str = ", ".join(v.get("value", "") for v in vals if v.get("value"))
            if val_str:
                attr_lines.append(f"  {name}: {val_str}")

    attr_text = "\n".join(attr_lines) if attr_lines else "无"

    prompt = f"""你是一个专业的 Ozon 电商平台商品描述写手。请根据以下规则和产品信息生成俄语商品描述。

参考规则：
{rules}

产品信息：
- 名称：{body.name or body.name}
- 类目：{category}
- 规格参数：
{attr_text}

要求：
1. 描述长度 500-2000 字符（俄语）
2. 结构：开头卖点 → 详细规格 → 使用场景 → 包装内容
3. 自然俄语，可读性强，段落分明
4. 无需重复标题内容
5. 禁止外部链接和联系方式

返回 JSON 格式：
{{"description": "生成的俄语描述", "keywords": ["关键词1", "关键词2"]}}
只返回 JSON，不要其他文字。"""

    result = _call_llm(prompt, temperature=0.5, feature_key="product.description.generate")
    json_str, raw_text = _extract_json(result)
    if json_str:
        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError:
            parsed = {"description": raw_text[:1000], "keywords": []}
    else:
        parsed = {"description": raw_text[:1000], "keywords": []}
    return {"product_id": product_id, "original_description": body.description, **parsed}


@router.post("/products/{product_id}/ai/quality-check")
async def ai_quality_check(product_id: str):
    """AI quality check for a product against Ozon rules.

    Combines rule-based structural checks with LLM content assessment.
    Returns a score (0-100) and detailed item-level results.
    """
    product = await _load_product(product_id)

    # ── Rule-based checks ──
    items: list[dict[str, Any]] = []
    deductions = 0

    name = product.get("name", "") or ""
    description = product.get("description", "") or ""
    images = product.get("images") or []
    attributes = product.get("attributes") or []
    category = product.get("category_name") or product.get("category_id") or ""
    weight = product.get("weight")
    width = product.get("width")
    height_ = product.get("height")
    depth = product.get("depth")
    price = product.get("price")

    # Title checks
    if not name:
        items.append({"field": "title", "status": "error", "message": "标题为空"})
        deductions += 25
    elif len(name) < 30:
        items.append({"field": "title", "status": "warn", "message": f"标题过短（{len(name)}字符），建议50-150字符"})
        deductions += 10
    elif len(name) > 200:
        items.append({"field": "title", "status": "warn", "message": f"标题过长（{len(name)}字符），建议不超过150字符"})
        deductions += 5
    elif len(name) < 50:
        items.append({"field": "title", "status": "warn", "message": f"标题偏短（{len(name)}字符），建议50-150字符"})
        deductions += 3
    else:
        items.append({"field": "title", "status": "ok", "message": f"标题长度 {len(name)} 字符，符合要求"})

    # Description checks
    if not description:
        items.append({"field": "description", "status": "error", "message": "描述为空"})
        deductions += 25
    elif len(description) < 300:
        items.append({"field": "description", "status": "warn", "message": f"描述偏短（{len(description)}字符），建议500-2000字符"})
        deductions += 10
    elif len(description) < 500:
        items.append({"field": "description", "status": "warn", "message": f"描述偏短（{len(description)}字符），建议500-2000字符"})
        deductions += 5
    else:
        items.append({"field": "description", "status": "ok", "message": f"描述长度 {len(description)} 字符，符合要求"})

    # Image checks
    if len(images) == 0:
        items.append({"field": "images", "status": "error", "message": "未上传任何图片"})
        deductions += 20
    elif len(images) < 3:
        items.append({"field": "images", "status": "warn", "message": f"图片较少（{len(images)}张），建议至少上传5张"})
        deductions += 8
    elif len(images) < 5:
        items.append({"field": "images", "status": "warn", "message": f"图片偏少（{len(images)}张），建议上传5-10张"})
        deductions += 3
    else:
        items.append({"field": "images", "status": "ok", "message": f"已上传 {len(images)} 张图片"})

    # Primary image
    if not product.get("primary_image") and len(images) > 0:
        items.append({"field": "primary_image", "status": "warn", "message": "未设置主图，默认第一张为头图"})
        deductions += 3
    elif not product.get("primary_image") and len(images) == 0:
        items.append({"field": "primary_image", "status": "error", "message": "未设置主图"})
        deductions += 5
    else:
        items.append({"field": "primary_image", "status": "ok", "message": "主图已设置"})

    # Rich content check
    if attributes:
        has_rich = any(a.get("id") == 11254 for a in attributes)
        if has_rich:
            items.append({"field": "rich_content", "status": "ok", "message": "富内容（详情图集）已配置"})
        else:
            items.append({"field": "rich_content", "status": "warn", "message": "建议添加富内容（详情图集）提升转化率"})
            deductions += 3
    else:
        items.append({"field": "rich_content", "status": "warn", "message": "建议添加富内容（详情图集）提升转化率"})
        deductions += 3

    # Attributes check
    if not attributes:
        items.append({"field": "attributes", "status": "warn", "message": "未配置任何属性字段"})
        deductions += 10
    else:
        # Filter out description(4196) and rich content(11254) for counting
        real_attrs = [a for a in attributes if a.get("id") not in (4196, 11254)]
        if len(real_attrs) >= 5:
            items.append({"field": "attributes", "status": "ok", "message": f"已配置 {len(real_attrs)} 个属性"})
        elif len(real_attrs) > 0:
            items.append({"field": "attributes", "status": "warn", "message": f"属性较少（{len(real_attrs)}项），建议填完所有必填属性"})
            deductions += 5
        else:
            items.append({"field": "attributes", "status": "warn", "message": "未配置有效属性"})
            deductions += 8

    # Dimensions & weight
    dims_ok = all(v is not None for v in (weight, width, height_, depth))
    if dims_ok:
        items.append({"field": "dimensions", "status": "ok", "message": "重量和尺寸已填写"})
    else:
        items.append({"field": "dimensions", "status": "warn", "message": "重量或尺寸未填全，可能影响运费计算"})
        deductions += 5

    # Price
    if price and float(price) > 0:
        items.append({"field": "price", "status": "ok", "message": f"价格已设置: {price}"})
    else:
        items.append({"field": "price", "status": "error", "message": "价格未设置"})
        deductions += 15

    # Score
    score = max(0, 100 - deductions)

    # LLM content quality assessment (only if we have basic info)
    llm_comment = ""
    if name and description and len(description) > 100:
        rules = _search_rules("内容评级 商品质量", limit=3)
        quality_prompt = f"""你是一个 Ozon 商品内容质量评估专家。请根据以下规则对商品内容进行简要评估。

参考规则：
{rules}

商品名称：{name[:200]}
商品描述：{description[:500]}

请用一句话（中文）评价该商品的内容质量，指出主要问题（如有）。返回 JSON:
{{"quality": "good/needs_improvement", "comment": "一句话评价"}}
只返回 JSON。"""
        try:
            qr = _call_llm(quality_prompt, temperature=0.2, feature_key="product.quality.check")
            qj, _ = _extract_json(qr)
            if qj:
                qp = json.loads(qj)
                llm_comment = qp.get("comment", "")
                if qp.get("quality") == "needs_improvement":
                    deductions += 5
        except Exception:
            pass

    # Recalculate score with LLM deduction
    score = max(0, 100 - deductions)

    # Summary
    if score >= 80:
        summary = f"商品质量良好（{score}分）。" + (f" {llm_comment}" if llm_comment else "")
    elif score >= 60:
        summary = f"商品质量一般（{score}分），存在需要改进的地方。" + (f" {llm_comment}" if llm_comment else "")
    else:
        summary = f"商品质量较差（{score}分），请优先修复标红项目。" + (f" {llm_comment}" if llm_comment else "")

    return QualityCheckResponse(score=score, items=items, summary=summary)


@router.post("/products/{product_id}/ai/complete-attributes")
async def ai_complete_attributes(product_id: str):
    """AI-suggest values for empty product attributes."""
    product = await _load_product(product_id)

    from icross.services.ozon import get_ozon_client
    from icross.core.storage.ozon_data import CategoryStorage, _ensure_ozon_shop

    shop_id = product.get("shop_id", "")
    category_id = product.get("category_id")
    type_id = product.get("type_id")
    if not category_id or not type_id:
        raise HTTPException(status_code=400, detail="Product has no category or type")

    category_store = CategoryStorage()
    client = get_ozon_client()
    _ensure_ozon_shop(client, shop_id)

    # Get attribute definitions
    attr_defs = await category_store.get_category_attributes(category_id, type_id)
    if not attr_defs:
        try:
            data = await client.get_category_attributes(shop_id, category_id, type_id, language="ZH_HANS")
            attr_defs = data.get("attributes", [])
            await category_store.save_category_attributes(category_id, type_id, attr_defs)
        except BaseException as e:
            raise HTTPException(status_code=502, detail=f"Failed to fetch attributes: {e}")

    # Build current values lookup
    raw_attributes: list[dict] = product.get("attributes") or []
    current_values: dict[int, list[dict]] = {}
    for attr in raw_attributes:
        aid = attr.get("id")
        if aid:
            current_values[aid] = attr.get("values", [])

    # Find empty attributes that could be suggested
    name = product.get("name", "") or ""
    description = product.get("description", "") or ""
    category_name = product.get("category_name") or ""

    empty_attrs = []
    for attr_def in attr_defs:
        aid = attr_def.get("id")
        if not aid:
            continue
        # Skip description(4196) and rich content(11254) — handled elsewhere
        if aid in (4196, 11254):
            continue
        vals = current_values.get(aid, [])
        if not vals or all(not v.get("value") for v in vals):
            empty_attrs.append({
                "id": aid,
                "name": attr_def.get("name", f"attr_{aid}"),
                "type": attr_def.get("type", "text"),
                "is_collection": attr_def.get("is_collection", False),
                "required": attr_def.get("required", False),
                "dictionary_id": attr_def.get("dictionary_id"),
                "description": attr_def.get("description", ""),
            })

    if not empty_attrs:
        return {"product_id": product_id, "suggestions": [], "message": "所有属性已填完"}

    # Fetch dictionary options for empty dictionary attributes
    dict_options: dict[int, list[dict]] = {}
    for attr in empty_attrs:
        if attr.get("dictionary_id"):
            aid = attr["id"]
            cached_vals = await category_store.get_dictionary_values(aid, category_id, type_id)
            if not cached_vals:
                try:
                    vals_result = await client.get_category_attribute_values(
                        shop_id, category_id, type_id, aid, language="ZH_HANS"
                    )
                    cached_vals = vals_result.get("values", [])
                    if cached_vals:
                        await category_store.save_dictionary_values(aid, category_id, type_id, cached_vals)
                except BaseException:
                    pass
            if cached_vals:
                dict_options[aid] = cached_vals

    # Build prompt
    attr_desc_lines = []
    for attr in empty_attrs:
        aid = attr["id"]
        aname = attr["name"]
        desc = attr.get("description", "")
        options = dict_options.get(aid, [])
        opt_str = ""
        if options:
            opt_list = [f"{o.get('id')}: {o.get('value')}" for o in options[:100]]
            opt_str = f"\n    可选值: {', '.join(opt_list)}"
        attr_desc_lines.append(f"  - {aname} (id={aid}){opt_str}")

    attr_text = "\n".join(attr_desc_lines)

    prompt = f"""你是一个 Ozon 商品属性填写专家。根据商品信息和类目，为以下空属性建议合适的值。

商品名称：{name[:300]}
类目：{category_name}
类目 ID：{category_id}
商品描述：{description[:500]}

需要填写的属性（含可选值列表，如有）：
{attr_text}

要求：
1. 根据商品名称、描述判断最合适的属性值
2. 对于有可选值列表的属性，必须从可选值中选择（用 id + value 返回）
3. 对于文本属性，根据商品特征填写合理的值
4. 只对信息明确的属性填写，不确定的留空
5. 如果属性不需要填或信息不足，值为 null

返回 JSON 格式（一个数组）：
[
  {{"id": 属性ID, "value": "文本值 或 null", "dictionary_value_id": 可选值ID 或 null}},
  ...
]
只返回 JSON，不要其他文字。"""

    from icross.api.ai_utils import get_ai_llm
    llm = get_ai_llm("product.attributes.complete", temperature=0.3, max_tokens=2048)
    response = await llm.ainvoke([{"role": "user", "content": prompt}])
    raw = response.content
    if isinstance(raw, list):
        texts = []
        for block in raw:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))
        raw = "\n".join(texts)
    json_str, _ = _extract_json(raw.strip())
    suggestions = []
    if json_str:
        try:
            parsed = json.loads(json_str)
            if isinstance(parsed, list):
                suggestions = parsed
            elif isinstance(parsed, dict) and "suggestions" in parsed:
                suggestions = parsed["suggestions"]
        except json.JSONDecodeError:
            pass

    # Normalise types: LLM returns strings, frontend expects numbers
    for s in suggestions:
        if s.get("dictionary_value_id") is not None:
            try:
                s["dictionary_value_id"] = int(s["dictionary_value_id"])
            except (ValueError, TypeError):
                pass
        if s.get("value") is not None:
            s["value"] = str(s["value"])

    return {"product_id": product_id, "suggestions": suggestions, "message": ""}


# ══════════════════════════════════════════════════════════════
# P2: AI 定价建议
# ══════════════════════════════════════════════════════════════


@router.post("/products/{product_id}/ai/suggest-price")
async def ai_suggest_price(product_id: str):
    """AI-powered pricing suggestion based on cost analysis and market intelligence.

    Combines OzonCostCalculator baseline with LLM market analysis to suggest
    optimal pricing (conservative / balanced / aggressive) with profit projections.
    Falls back to heuristic calculation when LLM is unavailable.

    Returns:
        - `missing_fields`: list of required fields the user needs to provide
        - `suggestions`: pricing tiers (each with `tier`, `price_cny`, `margin_pct`, `profit_cny`, `reason`)
        - `currency`: always "CNY"
    """
    product = await _load_product(product_id)

    from icross.services.ozon_costs import OzonCostCalculator, ProductCostInput

    name = product.get("name", "") or ""
    category_name = product.get("category_name") or ""
    category_path = product.get("category_path", "")
    price = product.get("price", 0) or 0
    cost_price = product.get("cost_price") or product.get("attrs", {}).get("purchase_price_cny")
    weight = product.get("weight") or product.get("attrs", {}).get("weight_kg")
    product_currency = product.get("currency_code") or (product.get("attrs") or {}).get("currency_code", "CNY")
    currency = "CNY"  # 建议价格统一用人民币

    # ── Step 0: Check for missing cost data ──
    missing_fields = []
    if not cost_price:
        missing_fields.append("cost_price")
    if not weight:
        missing_fields.append("weight")

    # ── Step 1: Cost-based calculation ──
    cost_suggestions = []
    if cost_price and weight:
        try:
            calc = OzonCostCalculator()
            wkg = float(weight) / 1000 if float(weight) > 100 else float(weight)
            inp = ProductCostInput(
                purchase_price_cny=float(cost_price),
                weight_kg=wkg,
                category_name=category_name or category_path,
                sales_model="FBP",
            )
            for margin in [15, 25, 40]:
                result = calc.calculate(inp, target_margin=margin)
                tier_name = "保守定价" if margin == 40 else "平衡定价" if margin == 25 else "激进定价"
                cost_suggestions.append({
                    "tier": tier_name,
                    "price_cny": round(result.recommended_price_rub / CNY_TO_RUB),
                    "margin_pct": round(result.profit_margin_pct, 1),
                    "profit_cny": round(result.profit_rub / CNY_TO_RUB),
                    "reason": f"目标毛利率{margin}%，含平台佣金+物流+关税",
                    "total_cost": round(result.total_cost_rub / CNY_TO_RUB, 2),
                })
        except Exception:
            pass

    # ── Step 2: Try LLM enhancement ──
    llm_suggestions = []
    llm_analysis = ""
    llm_recommended = ""
    llm_market_note = ""
    try:
        cost_line = f"成本：{cost_price} CNY" if cost_price else "成本：未知"
        weight_line = f"重量：{weight} {'g' if weight and float(weight) > 100 else 'kg'}" if weight else "重量：未知"
        prompt = f"""商品：{name[:200]}
类目：{category_name or category_path or "未分类"}
当前价：{price} {product_currency}
{cost_line}
{weight_line}

请为 Ozon 平台给出三档定价建议，售价单位为人民币 CNY（参考汇率 1 CNY ≈ {CNY_TO_RUB} RUB），返回 JSON:
{{"a":"当前定价简析", "s":[
  {{"t":"保守定价","p":数字,"m":毛利率,"r":"理由"}},
  {{"t":"平衡定价","p":数字,"m":毛利率,"r":"理由"}},
  {{"t":"激进定价","p":数字,"m":毛利率,"r":"理由"}}
], "rec":"推荐方案","note":"市场参考"}}

注意：返回的价格单位是人民币(CNY)，毛利率单位为百分比(%)。"""

        from icross.api.ai_utils import get_ai_llm
        llm = get_ai_llm("product.price.suggest", temperature=0.4, max_tokens=1024)
        response = await llm.ainvoke([{"role": "user", "content": prompt}])
        raw = response.content
        if isinstance(raw, list):
            texts = []
            for block in raw:
                if isinstance(block, dict) and block.get("type") == "text":
                    texts.append(block.get("text", ""))
            raw = "\n".join(texts)
        json_str, _ = _extract_json(raw.strip())
        if json_str:
            parsed = json.loads(json_str)
            if isinstance(parsed, dict):
                raw_suggestions = parsed.get("s", parsed.get("suggestions", []))
                llm_analysis = parsed.get("a", parsed.get("current_analysis", ""))
                llm_recommended = parsed.get("rec", parsed.get("recommended_tier", ""))
                llm_market_note = parsed.get("note", parsed.get("market_note", ""))
                # Normalise short key names
                for s in raw_suggestions:
                    if "t" in s and "tier" not in s:
                        s["tier"] = s.pop("t")
                    if "p" in s and "price_cny" not in s:
                        s["price_cny"] = s.pop("p")
                    if "m" in s and "margin_pct" not in s:
                        s["margin_pct"] = s.pop("m")
                    if "r" in s and "reason" not in s:
                        s["reason"] = s.pop("r")
                llm_suggestions = raw_suggestions
            elif isinstance(parsed, list):
                llm_suggestions = parsed
    except Exception:
        pass

    # ── Step 3: Merge — prefer LLM, fall back to cost-based ──
    suggestions = llm_suggestions if llm_suggestions else cost_suggestions

    # ── Step 4: Fallback — simple heuristic when no data at all ──
    if not suggestions and price:
        suggestions = [
            {"tier": "保守定价", "price_cny": round(price * 1.25), "margin_pct": None, "profit_cny": None, "reason": "在当前价格基础上提价 25%，留出促销空间（仅供参考，建议输入成本价获取精确计算）"},
            {"tier": "平衡定价", "price_cny": round(price * 1.10), "margin_pct": None, "profit_cny": None, "reason": "小幅提价 10%，保持竞争力（仅供参考，建议输入成本价获取精确计算）"},
            {"tier": "激进定价", "price_cny": round(price * 0.90), "margin_pct": None, "profit_cny": None, "reason": "降价 10% 抢占市场（仅供参考，建议输入成本价获取精确计算）"},
        ]

    analysis = llm_analysis or ""
    recommended = llm_recommended or ("平衡定价" if suggestions else "")
    market_note = llm_market_note or ""

    return {
        "product_id": product_id,
        "current_price": price,
        "product_currency": product_currency,
        "currency": currency,
        "cost_price": float(cost_price) if cost_price else None,
        "weight": float(weight) if weight else None,
        "missing_fields": missing_fields,
        "has_cost_data": bool(cost_suggestions),
        "suggestions": suggestions,
        "current_analysis": analysis,
        "recommended_tier": recommended,
        "market_note": market_note,
    }
