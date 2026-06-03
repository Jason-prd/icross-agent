"""Product listing generation tools — Phase 3+ (crawler tools removed)."""

import asyncio
import json
import re
from datetime import datetime
from typing import Any

from langchain_core.tools import tool
from icross.agents.tools import registry


def _run_async_in_tool(coro):
    """Run async code synchronously in tool context (where event loop may already be running)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    else:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()


def _safe_format(template: str, **kwargs) -> str:
    """Format a template string safely, handling {field or 'default'} patterns."""
    defaults = {}
    def _collect_default(m):
        field = m.group(1).strip()
        default = m.group(2).strip().strip("'\"")
        defaults[field] = default
        return "{" + field + "}"

    processed = re.sub(r"\{(\w+)\s+or\s+('[^']*'|\"[^\"]*\")\}", _collect_default, template)

    filled = dict(kwargs)
    for field, default in defaults.items():
        val = filled.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            filled[field] = default
        elif isinstance(val, list):
            filled[field] = ", ".join(val) if val else default

    return processed.format(**filled)


@tool
def generate_listing(
    product_name_cn: str,
    product_description_cn: str = "",
    category: str = "",
    keywords: list[str] = None,
    target_market: str = "俄罗斯",
    custom_prompt: str = "",
    skus: list[dict] = None,
) -> str:
    """生成俄语产品Listing（标题+描述），用于Ozon上架。

    Args:
        product_name_cn: 中文产品名称
        product_description_cn: 中文产品描述（可选）
        category: 产品类目（可选）
        keywords: 关键词列表（可选，用于SEO）
        target_market: 目标市场，默认俄罗斯
        custom_prompt: 自定义Prompt模板（可选）
        skus: SKU列表（可选），每个SKU包含name, attributes, price等

    Returns:
        JSON字符串，包含生成的俄语标题、描述、关键词
    """
    if keywords is None:
        keywords = []
    if skus is None:
        skus = []

    try:
        keyword_str = ", ".join(keywords) if keywords else ""
        if custom_prompt:
            prompt = _safe_format(custom_prompt,
                product_name_cn=product_name_cn,
                product_description_cn=product_description_cn or "",
                category=category or "",
                keyword_str=keyword_str or "",
                target_market=target_market,
            )
        else:
            sku_section = ""
            if skus:
                sku_lines = []
                for i, sku in enumerate(skus):
                    attrs = sku.get("attributes", {})
                    attr_str = ", ".join(f"{k}={v}" for k, v in attrs.items()) if attrs else ""
                    price = sku.get("price", 0)
                    sku_lines.append(f"    SKU {i+1}: {sku.get('name', '')} | 规格: {attr_str} | 价格: ¥{price}")
                sku_section = "\nSKU规格信息：\n" + "\n".join(sku_lines)

            prompt = f"""你是一个专业的电商Listing生成专家。请为Ozon电商平台生成俄语产品Listing。

产品信息：
- 中文名称：{product_name_cn}
- 中文描述：{product_description_cn or '无'}
- 类目：{category or '未分类'}
- 关键词：{keyword_str or '无'}
- 目标市场：{target_market}
{sku_section}

请生成：
1. 俄语产品标题（50-150字符，SEO优化，包含关键词）
2. 俄语产品描述（500-2000字符，详细描述产品特点、规格、使用方法）
3. 俄语关键词（5-10个，用逗号分隔）

只返回JSON格式：
{{
    "title": "俄语标题",
    "description": "俄语描述",
    "keywords": ["关键词1", "关键词2", ...]
}}

只返回JSON，不要其他文字。"""

        from icross.api.ai_utils import get_ai_llm

        llm = get_ai_llm("listing.generate")
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
        return json.dumps({
            "success": True,
            "original_name": product_name_cn,
            "title": result.get("title", ""),
            "description": result.get("description", ""),
            "keywords": result.get("keywords", []),
            "generated_at": datetime.now().isoformat(),
        }, ensure_ascii=False, indent=2)

    except json.JSONDecodeError:
        return json.dumps({"success": False, "error": "LLM返回格式错误，无法解析"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


registry.register(generate_listing, toolset="product")


@tool
def translate_text(
    text: str,
    target_lang: str = "俄语",
) -> str:
    """翻译文本到指定语言。

    Args:
        text: 要翻译的文本（中文）
        target_lang: 目标语言（默认俄语，也可选英语、日语等）

    Returns:
        JSON字符串，包含翻译结果
    """
    try:
        from icross.api.ai_utils import get_ai_llm

        prompt = f"""翻译以下文本到{target_lang}，只返回翻译结果，不要解释：

{text}"""

        llm = get_ai_llm("listing.generate", temperature=0.3, max_tokens=2048)
        response = _run_async_in_tool(llm.ainvoke([{"role": "user", "content": prompt}]))

        raw = response.content
        if isinstance(raw, list):
            raw = "".join(b.get("text", "") for b in raw if isinstance(b, dict))

        return json.dumps({
            "success": True,
            "original_text": text,
            "translated_text": raw.strip(),
            "target_lang": target_lang,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


registry.register(translate_text, toolset="product")


@tool
def generate_product_image(
    product_name_cn: str,
    product_description_cn: str = "",
    category: str = "",
    style: str = "white background, studio lighting, product photography",
    num_images: int = 1,
) -> str:
    """使用 AI 生成产品图片（基于产品描述）。

    通过 Seedream API 生成产品展示图片。

    Args:
        product_name_cn: 中文产品名称
        product_description_cn: 中文产品描述
        category: 产品类目
        style: 图片风格描述
        num_images: 生成图片数量（1-4）

    Returns:
        JSON字符串，包含生成的图片URL列表
    """
    try:
        prompt = f"Product photo of {product_name_cn}"
        if product_description_cn:
            prompt += f": {product_description_cn[:200]}"
        if category:
            prompt += f", category: {category}"
        prompt += f", {style}"

        from icross.services.image_gen import generate_image_seedream
        result = _run_async_in_tool(generate_image_seedream(prompt, num_images))

        return json.dumps({
            "success": True,
            "prompt": prompt,
            "images": result.get("images", []),
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


registry.register(generate_product_image, toolset="product")


@tool
def remove_background(image_url: str) -> str:
    """去除图片背景（rembg）。

    Args:
        image_url: 图片URL或本地路径

    Returns:
        JSON字符串，包含去除背景后的图片URL/path
    """
    try:
        from icross.services.image_gen import remove_background_sync
        result = remove_background_sync(image_url)
        return json.dumps({"success": True, "result": result}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


registry.register(remove_background, toolset="product")


@tool
def apply_pricing_rule(
    shop_id: str,
    product_id: int = 0,
    product_ids: list[int] = None,
) -> str:
    """根据定价规则自动调整产品价格。

    适用于：批量调价、促销调价、竞争调价等场景。
    规则类型：加价(markup)、打折(discount)、固定价格(fixed)、取整(round)。
    规则条件可按：类目、价格范围筛选。

    注意：此工具只计算调整后的价格并创建草稿，不会直接修改线上价格。
    需要在草稿审核页面人工确认后才会同步到 Ozon。

    Args:
        shop_id: 店铺 ID
        product_id: 单个产品 ID
        product_ids: 多个产品 ID 列表

    Returns:
        JSON字符串，包含每个产品的原价、调整后价格和应用的规则
    """
    try:
        from icross.core.storage.ozon_data import PricingRuleStorage, ProductStorage, DraftStorage

        pids = product_ids or ([product_id] if product_id else [])
        if not pids:
            return json.dumps({"success": False, "error": "必须提供 product_id 或 product_ids"})

        product_storage = ProductStorage()
        rule_storage = PricingRuleStorage()
        draft_storage = DraftStorage()

        async def _run():
            results = []
            for pid in pids:
                product = await product_storage.get_product(shop_id, pid)
                if not product:
                    results.append({"product_id": pid, "error": "产品不存在"})
                    continue

                adjustment = await rule_storage.apply_rules_to_product(shop_id, product)
                if not adjustment.get("applied"):
                    results.append({"product_id": pid, "original_price": product.get("price"), "skipped": True})
                    continue

                new_price = adjustment.get("new_price")
                old_price = product.get("price", 0)
                draft = await draft_storage.create_draft(
                    shop_id=shop_id,
                    draft_type="price_update",
                    title=product.get("title", ""),
                    description=product.get("description", ""),
                    price=new_price,
                    offer_id=product.get("offer_id", ""),
                    source_url="",
                    images=[],
                    attrs={"original_price": old_price, "rule_name": adjustment.get("rule_name")},
                )
                results.append({
                    "product_id": pid,
                    "original_price": old_price,
                    "new_price": new_price,
                    "rule_name": adjustment.get("rule_name"),
                    "draft_id": draft.get("id"),
                })
            return results

        results = _run_async_in_tool(_run())
        return json.dumps({"success": True, "results": results}, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


registry.register(apply_pricing_rule, toolset="product")


@tool
def calculate_product_price(
    purchase_price_cny: float,
    weight_kg: float = 0.5,
    target_margin: float = 20.0,
    category: str = "",
    shop_id: str = "",
) -> str:
    """计算产品在 Ozon 上的建议售价。

    基于采购成本、物流费用、平台佣金等计算最终售价。

    Args:
        purchase_price_cny: 采购成本（人民币）
        weight_kg: 商品重量（公斤）
        target_margin: 目标利润率（%）
        category: Ozon 类目名称（影响佣金率）
        shop_id: 店铺 ID（用于获取店铺特定费用配置）

    Returns:
        JSON字符串，包含各项费用明细和建议售价
    """
    try:
        from icross.services.ozon_costs import calculate_full_cost

        result = calculate_full_cost(
            purchase_price_cny=purchase_price_cny,
            weight_kg=weight_kg,
            target_margin=target_margin,
            category=category,
            shop_id=shop_id or None,
        )
        return json.dumps({"success": True, **result}, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


registry.register(calculate_product_price, toolset="product")


@tool
def calculate_profit_at_price(
    purchase_price_cny: float,
    selling_price_rub: float,
    weight_kg: float = 0.5,
    category: str = "",
    shop_id: str = "",
) -> str:
    """计算在指定售价下的利润。

    Args:
        purchase_price_cny: 采购成本（人民币）
        selling_price_rub: 销售价格（卢布）
        weight_kg: 商品重量（公斤）
        category: Ozon 类目名称
        shop_id: 店铺 ID

    Returns:
        JSON字符串，包含利润率、各项费用明细
    """
    try:
        from icross.services.ozon_costs import calculate_profit
        result = calculate_profit(
            purchase_price_cny=purchase_price_cny,
            selling_price_rub=selling_price_rub,
            weight_kg=weight_kg,
            category=category,
            shop_id=shop_id or None,
        )
        return json.dumps({"success": True, **result}, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


registry.register(calculate_profit_at_price, toolset="product")


@tool
def check_listing_quality(
    title: str = "",
    description: str = "",
    keywords: list[str] = None,
) -> str:
    """检查 Listing 质量并给出改进建议。

    Args:
        title: 俄语标题
        description: 俄语描述
        keywords: 关键词列表

    Returns:
        JSON字符串，包含质量评分和问题列表
    """
    if keywords is None:
        keywords = []

    issues = []
    score = 100

    if not title:
        issues.append("标题不能为空")
        score -= 30
    elif len(title) < 30:
        issues.append(f"标题过短 ({len(title)}字符)，建议50-150字符")
        score -= 10
    elif len(title) > 200:
        issues.append(f"标题过长 ({len(title)}字符)，建议不超过150字符")
        score -= 5

    if not description:
        issues.append("描述不能为空")
        score -= 30
    elif len(description) < 300:
        issues.append(f"描述过短 ({len(description)}字符)，建议500-2000字符")
        score -= 10

    if not keywords:
        issues.append("关键词不能为空")
        score -= 20
    elif len(keywords) < 3:
        issues.append(f"关键词太少 ({len(keywords)}个)，建议5-10个")
        score -= 10

    return json.dumps({
        "score": max(0, score),
        "issues": issues,
        "summary": "优秀" if score >= 80 else ("良好" if score >= 60 else "需要改进"),
    }, ensure_ascii=False)


registry.register(check_listing_quality, toolset="product")


@tool
def batch_generate_listings(
    products: list[str],
    category: str = "",
    target_market: str = "俄罗斯",
) -> str:
    """批量生成多个产品的 Listing。

    Args:
        products: 中文产品名称列表
        category: 产品类目
        target_market: 目标市场

    Returns:
        JSON字符串，包含每个产品的 Listing
    """
    results = []
    for name in products:
        try:
            result_str = generate_listing(
                product_name_cn=name,
                category=category,
                target_market=target_market,
            )
            result = json.loads(result_str)
            results.append(result)
        except Exception as e:
            results.append({"product_name": name, "error": str(e)})

    return json.dumps({
        "success": True,
        "total": len(products),
        "generated": len([r for r in results if r.get("success")]),
        "results": results,
    }, ensure_ascii=False, indent=2)


registry.register(batch_generate_listings, toolset="product")


@tool
def parse_product_materials(
    text: str = "",
    file_paths: list[str] = None,
    shop_id: str = "",
) -> str:
    """解析产品材料，提取结构化 SPU/SKU 数据。

    支持文本描述或上传的文档（PDF/Excel/Word/图片）的内容。

    Args:
        text: 产品文字描述（中文）
        file_paths: 已上传的文件路径列表（workspace 中的文件）
        shop_id: 店铺 ID

    Returns:
        JSON字符串，包含提取的 SPU 和 SKU 信息
    """
    try:
        from icross.services.product_parser import parse_product_async
        result = _run_async_in_tool(parse_product_async(
            text=text,
            file_paths=file_paths or [],
            shop_id=shop_id,
        ))
        return json.dumps({"success": True, "data": result}, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


registry.register(parse_product_materials, toolset="product")


@tool
def get_auto_pilot_config(shop_id: str) -> str:
    """获取店铺的自动运营配置。

    Args:
        shop_id: 店铺ID

    Returns:
        JSON字符串，包含自动运营配置
    """
    from icross.core.storage.ozon_data import AutoPilotConfigStorage
    store = AutoPilotConfigStorage()
    try:
        loop = asyncio.get_running_loop()
        config = loop.run_until_complete(store.get_config(shop_id))
    except RuntimeError:
        config = asyncio.run(store.get_config(shop_id))
    return json.dumps(config, ensure_ascii=False, indent=2)


@tool
def save_auto_pilot_config(shop_id: str, enabled: bool = False, cron_expr: str = "0 3 * * *",
                           push_to_ozon: bool = True, weight_kg: float = 0.5,
                           target_margin: float = 20.0) -> str:
    """保存或更新店铺的自动运营配置。

    设置店铺的自动运营参数，包括启用/禁用、定时执行规则、定价后自动推送到Ozon、
    流水线默认参数等。

    Args:
        shop_id: 店铺ID
        enabled: 是否启用自动运营
        cron_expr: Cron 定时表达式（如 "0 3 * * *" 表示每天凌晨3点）
        push_to_ozon: 定价后是否自动推送到Ozon
        weight_kg: 默认商品重量（kg）
        target_margin: 目标利润率（%）
    """
    from icross.core.storage.ozon_data import AutoPilotConfigStorage
    store = AutoPilotConfigStorage()
    config = {
        "enabled": enabled,
        "cron_expr": cron_expr,
        "push_to_ozon": push_to_ozon,
        "pipeline_params": {
            "weight_kg": weight_kg,
            "target_margin": target_margin,
        },
    }
    try:
        loop = asyncio.get_running_loop()
        result = loop.run_until_complete(store.save_config(shop_id, config))
    except RuntimeError:
        result = asyncio.run(store.save_config(shop_id, config))
    return json.dumps({"success": True, "config": result}, ensure_ascii=False, indent=2)


registry.register(get_auto_pilot_config, toolset="product")
registry.register(save_auto_pilot_config, toolset="product")

PHASE3_TOOLS = [
    generate_listing,
    translate_text,
    generate_product_image,
    remove_background,
    apply_pricing_rule,
    calculate_product_price,
    calculate_profit_at_price,
    check_listing_quality,
    batch_generate_listings,
    parse_product_materials,
]
