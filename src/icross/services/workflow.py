"""Automation workflow pipeline engine.

Chains: search products → generate image → generate listing → calculate price → create publish draft.
Each step is a task that feeds into the next.
"""

import json
import logging
from datetime import datetime
from typing import Any

from icross.core.storage.ozon_data import WorkflowStorage, TaskStorage, DraftStorage
from icross.services.task_queue import register_task

_logger = logging.getLogger(__name__)

# ── Step Types ──────────────────────────────────────────────────

STEP_TYPES = {
    "search_product": "搜索产品 (1688/PDD)",
    "match_category": "类目匹配 (Ozon)",
    "generate_image": "生成产品图片",
    "generate_listing": "生成俄语Listing",
    "calculate_price": "计算定价",
    "create_draft": "创建发布草稿",
}

# ── Pipeline Definitions ────────────────────────────────────────

def get_default_pipeline(shop_id: str, product_name_cn: str) -> list[dict[str, Any]]:
    """Return the default automation pipeline steps."""
    return [
        {
            "step_type": "search_product",
            "name": "搜索产品",
            "params": {"keyword": product_name_cn, "page_size": 5},
            "status": "pending",
            "result": None,
        },
        {
            "step_type": "match_category",
            "name": "类目匹配",
            "params": {"product_name_cn": product_name_cn},
            "status": "pending",
            "result": None,
        },
        {
            "step_type": "generate_listing",
            "name": "生成俄语Listing",
            "params": {"product_name_cn": product_name_cn},
            "status": "pending",
            "result": None,
        },
        {
            "step_type": "generate_image",
            "name": "生成产品图片",
            "params": {"product_name_cn": product_name_cn},
            "status": "pending",
            "result": None,
        },
        {
            "step_type": "calculate_price",
            "name": "计算定价",
            "params": {"purchase_price_cny": 0, "weight_kg": 0, "category_name": ""},
            "status": "pending",
            "result": None,
        },
        {
            "step_type": "create_draft",
            "name": "创建发布草稿",
            "params": {"shop_id": shop_id},
            "status": "pending",
            "result": None,
        },
    ]


# ── Task Handlers ───────────────────────────────────────────────

@register_task("workflow_step_search")
async def handle_search_product(keyword: str = "", page_size: int = 5, **kwargs) -> dict[str, Any]:
    """Search for products — crawler removed, use product_parser instead."""
    return {
        "products": [],
        "total": 0,
        "source": "deprecated",
        "keyword": keyword,
        "error": "爬虫功能已移除，请使用 parse_product_materials 工具上传产品材料进行选品",
    }


@register_task("workflow_step_category")
async def handle_match_category(
    product_name_cn: str = "",
    product_description_cn: str = "",
    **kwargs,
) -> dict[str, Any]:
    """Match product to an Ozon category using vector + LLM."""
    from icross.services.category_matcher import match_product_category

    result = await match_product_category(
        product_name=product_name_cn,
        product_description=product_description_cn,
    )

    if result.get("success"):
        match = result["match"]
        return {
            "description_category_id": match["description_category_id"],
            "type_id": match["type_id"],
            "category_name": match["category_name"],
            "reason": match.get("reason", ""),
            "method": result.get("method", "vector_llm"),
        }
    # Fallback: return what we can
    return {
        "description_category_id": 0,
        "type_id": 0,
        "category_name": "",
        "reason": result.get("error", "匹配失败"),
        "method": result.get("method", "error"),
    }


@register_task("workflow_step_listing")
async def handle_generate_listing(
    product_name_cn: str = "",
    product_description_cn: str = "",
    category: str = "",
    description_category_id: int = 0,
    type_id: int = 0,
    keywords: list[str] | None = None,
    target_market: str = "俄罗斯",
    template_id: str | None = None,
    **kwargs,
) -> dict[str, Any]:
    """Generate Russian listing from product info."""
    from icross.agents.master.tools_product import generate_listing
    kw = keywords or []
    result_str = generate_listing.func(
        product_name_cn=product_name_cn,
        product_description_cn=product_description_cn,
        category=category,
        keywords=kw,
        target_market=target_market,
        custom_prompt=None,
    )
    result = json.loads(result_str)
    # Pass through category IDs
    if description_category_id:
        result["description_category_id"] = description_category_id
    if type_id:
        result["type_id"] = type_id
    return result


@register_task("workflow_step_image")
async def handle_generate_image(
    product_name_cn: str = "",
    product_description_cn: str = "",
    image_prompt: str = "",
    images: list[str] | None = None,
    **kwargs,
) -> dict[str, Any]:
    """Generate product image using Seedream AI.

    Builds a prompt from the product info if no explicit ``image_prompt`` is given.
    Returns a dict with the generated image URLs.
    """
    # Construct a descriptive prompt when none was provided
    if not image_prompt:
        prompt = f"电商产品图: {product_name_cn}"
        if product_description_cn:
            desc = product_description_cn[:120]
            prompt += f"，{desc}"
    else:
        prompt = image_prompt

    try:
        from icross.services.image_gen import SeedreamClient

        client = SeedreamClient()
        results = client.generate(
            prompt=prompt,
            size="2048x2048",
            n=1,
            response_format="url",
        )

        image_list = []
        for item in results:
            url = item.get("url")
            if url:
                image_list.append({"url": url, "prompt": prompt})

        return {
            "success": True,
            "count": len(image_list),
            "images": image_list,
            "prompt": prompt,
        }
    except ImportError:
        return {"success": False, "error": "Seedream 模块未安装 (VOLC_ACCESS_KEY 或依赖问题)", "images": []}
    except Exception as e:
        return {"success": False, "error": str(e), "images": []}


@register_task("workflow_step_price")
async def handle_calculate_price(
    purchase_price_cny: float = 0,
    weight_kg: float = 0,
    category_name: str = "",
    target_margin: float = 20.0,
    **kwargs,
) -> dict[str, Any]:
    """Calculate recommended price using OzonCostCalculator."""
    from icross.services.ozon_costs import OzonCostCalculator, ProductCostInput
    calc = OzonCostCalculator()
    inp = ProductCostInput(
        purchase_price_cny=purchase_price_cny,
        weight_kg=weight_kg,
        category_name=category_name,
        sales_model="FBP",
    )
    result = calc.calculate(inp, target_margin=target_margin)
    return result.__dict__


@register_task("workflow_step_draft")
async def handle_create_draft(
    shop_id: str = "",
    title: str = "",
    description: str = "",
    price: float = 0,
    offer_id: str = "",
    source_url: str = "",
    images: list[str] | None = None,
    description_category_id: int = 0,
    type_id: int = 0,
    category_attributes: list[dict] | None = None,
    **kwargs,
) -> dict[str, Any]:
    """Create a publish draft for human review."""
    store = DraftStorage()
    draft = await store.create_draft(
        shop_id=shop_id,
        draft_type="listing",
        title=title,
        description=description,
        price=price,
        offer_id=offer_id,
        source_url=source_url,
        images=images or [],
        attrs={
            "description_category_id": description_category_id,
            "type_id": type_id,
            "category_attributes": category_attributes or [],
        },
    )
    return draft


# ── Workflow Execution ──────────────────────────────────────────

async def execute_workflow_step(workflow_id: str) -> dict[str, Any] | None:
    """Execute the next pending step in a workflow."""
    from icross.services.task_queue import create_and_run_task

    store = WorkflowStorage()
    wf = await store.get_workflow(workflow_id)
    if not wf:
        return None

    steps = wf.get("steps", [])
    current_idx = wf.get("current_step", 0)

    if current_idx >= len(steps):
        await store.update_workflow(workflow_id, status="completed")
        return await store.get_workflow(workflow_id)

    step = steps[current_idx]
    if step["status"] != "pending":
        return wf

    # Mark step as running
    step["status"] = "running"
    step["started_at"] = datetime.now().isoformat()
    steps[current_idx] = step
    await store.update_workflow(workflow_id, steps=steps, status="running")

    # Map step type to task type
    task_type_map = {
        "search_product": "workflow_step_search",
        "match_category": "workflow_step_category",
        "generate_image": "workflow_step_image",
        "generate_listing": "workflow_step_listing",
        "calculate_price": "workflow_step_price",
        "create_draft": "workflow_step_draft",
    }
    task_type = task_type_map.get(step["step_type"])
    if not task_type:
        step["status"] = "failed"
        step["error"] = f"Unknown step type: {step['step_type']}"
        steps[current_idx] = step
        await store.update_workflow(workflow_id, steps=steps)
        return await store.get_workflow(workflow_id)

    # Merge accumulated product_data into step params
    params = dict(step.get("params", {}))
    product_data = wf.get("product_data", {})
    for k, v in product_data.items():
        if k not in params or not params[k]:
            params[k] = v

    try:
        task = await create_and_run_task(task_type, params=params)
        step["task_id"] = task["id"]
    except Exception as e:
        _logger.exception(f"Failed to create task for step {current_idx}")
        step["status"] = "failed"
        step["error"] = str(e)

    steps[current_idx] = step
    await store.update_workflow(workflow_id, steps=steps)
    return await store.get_workflow(workflow_id)


async def complete_workflow_step(workflow_id: str, task_result: dict[str, Any]):
    """Called when a workflow step task completes."""
    store = WorkflowStorage()
    wf = await store.get_workflow(workflow_id)
    if not wf:
        return

    steps = wf.get("steps", [])
    current_idx = wf.get("current_step", 0)

    if current_idx >= len(steps):
        return

    step = steps[current_idx]
    step["status"] = "completed"
    step["result"] = task_result
    step["completed_at"] = datetime.now().isoformat()
    steps[current_idx] = step

    # Propagate result data to product_data
    product_data = dict(wf.get("product_data", {}))
    step_type = step["step_type"]
    if task_result:
        if step_type == "search_product":
            products = task_result.get("products", [])
            if products:
                product_data["source_url"] = products[0].get("url", "")
                product_data["product_name_cn"] = products[0].get("name", product_data.get("product_name_cn", ""))
                product_data["purchase_price_cny"] = products[0].get("price", 0)
                product_data["images"] = [products[0].get("image", "")] if products[0].get("image") else []
        elif step_type == "match_category":
            cat_id = task_result.get("description_category_id", 0)
            type_id = task_result.get("type_id", 0)
            cat_name = task_result.get("category_name", "")
            if cat_id:
                product_data["description_category_id"] = cat_id
                product_data["type_id"] = type_id
                product_data["category"] = cat_name
        elif step_type == "generate_listing":
            product_data["title"] = task_result.get("title", "")
            product_data["description"] = task_result.get("description", "")
            product_data["keywords"] = task_result.get("keywords", [])
            # Pass through category IDs from listing result
            if task_result.get("description_category_id"):
                product_data["description_category_id"] = task_result["description_category_id"]
            if task_result.get("type_id"):
                product_data["type_id"] = task_result["type_id"]
            # Save listing to ListingStorage
            try:
                from icross.core.storage.ozon_data import ListingStorage
                ls = ListingStorage()
                await ls.save_listing(
                    shop_id=wf.get("shop_id", ""),
                    data={
                        "product_name_cn": product_data.get("product_name_cn", ""),
                        "title": task_result.get("title", ""),
                        "description": task_result.get("description", ""),
                        "keywords": task_result.get("keywords", []),
                        "category": product_data.get("category", ""),
                        "description_category_id": product_data.get("description_category_id", 0),
                        "type_id": product_data.get("type_id", 0),
                    },
                )
            except Exception:
                _logger.exception("Failed to save listing to ListingStorage")
        elif step_type == "calculate_price":
            product_data["recommended_price"] = task_result.get("recommended_price_rub", 0)
            product_data["profit_margin"] = task_result.get("profit_margin_pct", 0)
        elif step_type == "generate_image":
            if task_result.get("success"):
                generated_images = task_result.get("images", [])
                if generated_images:
                    product_data["images"] = generated_images

    # Move to next step
    next_idx = current_idx + 1
    await store.update_workflow(
        workflow_id,
        steps=steps,
        current_step=next_idx,
        product_data=product_data,
        status="running" if next_idx < len(steps) else "completed",
    )

    # Auto-advance to the next step when there are more steps
    if next_idx < len(steps):
        await execute_workflow_step(workflow_id)


async def start_workflow(workflow_id: str) -> dict[str, Any] | None:
    """Start executing a workflow from its first pending step."""
    wf = await execute_workflow_step(workflow_id)
    return wf


async def run_full_pipeline(
    shop_id: str,
    product_name_cn: str,
    product_description_cn: str = "",
    category: str = "",
    purchase_price_cny: float = 0,
    weight_kg: float = 0,
    target_margin: float = 20.0,
) -> dict[str, Any]:
    """Create and start a full automation pipeline workflow."""
    store = WorkflowStorage()

    steps = [
        {
            "step_type": "search_product",
            "name": f"搜索产品: {product_name_cn}",
            "params": {"keyword": product_name_cn, "page_size": 5},
            "status": "pending",
            "result": None,
        },
        {
            "step_type": "match_category",
            "name": "类目匹配 (Ozon)",
            "params": {
                "product_name_cn": product_name_cn,
                "product_description_cn": product_description_cn,
            },
            "status": "pending",
            "result": None,
        },
        {
            "step_type": "generate_listing",
            "name": "生成俄语Listing",
            "params": {
                "product_name_cn": product_name_cn,
                "product_description_cn": product_description_cn,
                "category": category,
            },
            "status": "pending",
            "result": None,
        },
        {
            "step_type": "generate_image",
            "name": "生成产品图片",
            "params": {
                "product_name_cn": product_name_cn,
                "product_description_cn": product_description_cn,
            },
            "status": "pending",
            "result": None,
        },
        {
            "step_type": "calculate_price",
            "name": "计算定价",
            "params": {
                "purchase_price_cny": purchase_price_cny,
                "weight_kg": weight_kg,
                "category_name": category,
                "target_margin": target_margin,
            },
            "status": "pending",
            "result": None,
        },
        {
            "step_type": "create_draft",
            "name": "创建发布草稿",
            "params": {"shop_id": shop_id},
            "status": "pending",
            "result": None,
        },
    ]

    product_data = {
        "product_name_cn": product_name_cn,
        "product_description_cn": product_description_cn,
        "purchase_price_cny": purchase_price_cny,
        "weight_kg": weight_kg,
        "category": category,
    }

    wf = await store.create_workflow(
        name=f"自动化: {product_name_cn}",
        shop_id=shop_id,
        steps=steps,
        product_data=product_data,
    )

    # Start executing
    await start_workflow(wf["id"])
    return wf
