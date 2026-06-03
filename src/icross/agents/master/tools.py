"""Tool definitions for Ozon operations - supports multi-shop execution."""

import asyncio
import json
import threading
from datetime import datetime
from typing import Any, Optional

from langchain_core.tools import tool

from icross.services.ozon import get_ozon_client
from icross.agents.master.tools_product import PHASE3_TOOLS
from icross.agents.tools import registry


# ── Background event loop ──────────────────────────────────────
# All async operations share ONE background loop so that aiohttp
# ClientSession (created once by the OzonAPI library and reused
# across threads) always lives on the same loop.  Without this,
# parallel tool calls in thread‑pool threads each create their own
# event loop, and aiohttp's TimerContext fails with
# "Timeout context manager should be used inside a task" because
# asyncio.current_task() can't find a task on the session's loop.
_BG_LOOP: asyncio.AbstractEventLoop | None = None
_BG_LOOP_LOCK: threading.Lock = threading.Lock()


def _get_bg_loop() -> asyncio.AbstractEventLoop:
    global _BG_LOOP
    if _BG_LOOP is None or _BG_LOOP.is_closed():
        with _BG_LOOP_LOCK:
            if _BG_LOOP is None or _BG_LOOP.is_closed():
                loop = asyncio.new_event_loop()
                t = threading.Thread(
                    target=loop.run_forever,
                    daemon=True,
                    name="icross-async-bg",
                )
                t.start()
                _BG_LOOP = loop
    return _BG_LOOP


def _run_async(coro):
    """Run async code synchronously on a dedicated background event loop.

    A single background loop (started once) is used for all tool calls so
    that aiohttp sessions created by the OzonAPI library are always bound
    to the same loop, avoiding ``TimerContext`` / ``current_task`` errors.
    """
    loop = _get_bg_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()


def _resolve_shop_ids(shop_id: str = None, shop_ids: list[str] = None) -> list[str]:
    """Resolve shop IDs from single or multi-shop input."""
    if shop_ids:
        return shop_ids
    if shop_id:
        return [shop_id]
    return []


def _aggregate_results(results: list, shop_ids: list[str], operation: str) -> dict:
    """Aggregate results from multiple shops."""
    aggregated = {
        "success": True,
        "operation": operation,
        "shops_processed": len(shop_ids),
        "shop_results": [],
        "summary": {},
    }

    all_items = []
    errors = []

    for shop_id, result in zip(shop_ids, results):
        if isinstance(result, dict) and "error" in result:
            errors.append({"shop_id": shop_id, "error": result["error"]})
            aggregated["shop_results"].append({
                "shop_id": shop_id,
                "success": False,
                "error": result["error"],
            })
        else:
            # Extract items from result
            items = result.get("items", []) if isinstance(result, dict) else []
            all_items.extend(items)
            aggregated["shop_results"].append({
                "shop_id": shop_id,
                "success": True,
                "data": result,
            })

    aggregated["errors"] = errors
    aggregated["summary"] = {
        "total_items": len(all_items),
        "shops_success": len(shop_ids) - len(errors),
        "shops_failed": len(errors),
    }

    return aggregated


def _describe(data: dict, fields: dict[str, str]) -> dict:
    """Attach field descriptions to tool return data for LLM context.

    The LLM receives both raw data and field descriptions, helping it
    understand field semantics and avoid calculation errors.

    Usage:
        result = _run_async(client.some_api(...))
        return json.dumps(_describe(result, {
            "amount": "总金额 (₽)",
            "commission": "佣金 (₽)，已从 amount 中扣除",
        }), ensure_ascii=False, indent=2)
    """
    data["_fields"] = fields
    return data


# ============================================================
# Ozon Product Tools (Multi-shop)
# ============================================================

async def _enrich_product_list(
    client: Any,
    shop_id: str,
    items: list[dict],
) -> list[dict]:
    """Enrich product list items with detailed info (price, stocks, etc.).

    Ozon's product list API doesn't return prices; this fetches detailed info
    in batches and merges price/stock/status fields back into list items.
    """
    product_ids = [
        item["product_id"] for item in items
        if isinstance(item.get("product_id"), int)
    ]
    if not product_ids:
        return items

    # Build {product_id: detail} lookup from batch info queries
    detail_map: dict[int, dict] = {}
    for i in range(0, len(product_ids), 100):
        batch = product_ids[i:i + 100]
        try:
            detail = await client.get_product_info_list(shop_id, product_ids=batch)
            for d in detail.get("items", []):
                pid = d.get("product_id")
                if pid is not None:
                    detail_map[pid] = d
        except Exception:
            continue

    if not detail_map:
        return items

    _DETAIL_FIELDS = [
        "name", "price", "old_price", "marketing_price", "min_price",
        "stocks", "status", "commissions", "vat", "currency_code",
        "barcodes", "primary_image", "color_image", "category_id",
        "type_id", "created_at", "updated_at",
        "is_archived", "is_discounted", "is_autoarchived",
        "is_kgt", "is_super", "volume_weight",
    ]

    enriched = []
    for item in items:
        pid = item.get("product_id")
        detail = detail_map.get(pid) if isinstance(pid, int) else None
        if detail:
            merged = dict(item)
            for key in _DETAIL_FIELDS:
                if key in detail and detail[key] is not None:
                    merged[key] = detail[key]
            enriched.append(merged)
        else:
            enriched.append(item)

    # Also fetch descriptions concurrently (per-product API, concurrency limit 5)
    try:
        sem = asyncio.Semaphore(5)

        async def _fetch_desc(pid: int) -> tuple[int, str | None]:
            async with sem:
                try:
                    desc_data = await client.get_product_description(shop_id, pid)
                    result_data = desc_data.get("result", desc_data)
                    if isinstance(result_data, dict):
                        desc = result_data.get("description", "")
                        return pid, desc if desc else None
                except Exception:
                    pass
                return pid, None

        desc_results = await asyncio.gather(*[_fetch_desc(pid) for pid in product_ids])
        desc_map: dict[int, str | None] = dict(desc_results)

        for item in enriched:
            pid = item.get("product_id")
            desc = desc_map.get(pid) if isinstance(pid, int) else None
            if desc is not None:
                item["description"] = desc
    except Exception:
        pass

    return enriched


async def _list_with_details(
    client: Any,
    shop_id: str,
    limit: int,
    last_id: str,
    offer_ids: list[str] | None,
    visibility: str,
) -> dict:
    """Get product list and asynchronously enrich with detailed info."""
    result = await client.list_products(
        shop_id=shop_id, limit=limit, last_id=last_id,
        offer_ids=offer_ids, visibility=visibility,
    )
    items = result.get("items", [])
    if items:
        result["items"] = await _enrich_product_list(client, shop_id, items)
    return result


@tool
def ozon_product_list(
    shop_id: str = None,
    shop_ids: list[str] = None,
    page: int = 1,
    page_size: int = 100,
    offer_ids: Optional[list[str]] = None,
    visibility: str = "ALL",
    refresh: bool = False,
) -> str:
    """获取 Ozon 店铺产品列表（支持多店铺，默认读本地缓存，可选刷新）。

    默认从本地已同步的产品数据中读取（含价格等详情），速度快且不消耗 API 配额。
    设置 refresh=True 时强制从 Ozon API 拉取最新数据并同步到本地。

    Args:
        shop_id: 单个店铺ID (与 shop_ids 二选一)
        shop_ids: 多个店铺ID (批量操作，会并行获取后聚合)
        page: 页码，从 1 开始
        page_size: 每页数量，最大 1000
        offer_ids: 按 offer_id 筛选（可选，此参数强制走线上）
        visibility: 可见性筛选（ALL, VISIBLE, INVISIBLE）
        refresh: 是否强制从 Ozon API 刷新（默认 False，读本地缓存）

    Returns:
        JSON 字符串，包含产品列表（已补全价格等详情）。多店铺时返回聚合结果。
    """
    targets = _resolve_shop_ids(shop_id, shop_ids)
    if not targets:
        return json.dumps({"error": "必须提供 shop_id 或 shop_ids"})

    try:
        client = get_ozon_client()
        from icross.core.storage.ozon_data import ProductStorage

        # ── 本地读路径 ──────────────────────────────────────
        if not refresh and not offer_ids:
            storage = ProductStorage()
            offset = (page - 1) * page_size

            if len(targets) == 1:
                result = _run_async(storage.list_products(
                    targets[0], limit=page_size, offset=offset,
                    visibility=visibility,
                ))
                if result.get("items"):
                    return json.dumps(result, ensure_ascii=False, indent=2)
                # fall through to API if local empty
            else:
                async def _read_local(sid):
                    return await storage.list_products(
                        sid, limit=page_size, offset=offset,
                        visibility=visibility,
                    )
                results = _run_async(asyncio.gather(*[
                    _read_local(sid) for sid in targets
                ], return_exceptions=True))
                processed = []
                all_empty = True
                for r in results:
                    if isinstance(r, Exception):
                        processed.append({"error": str(r)})
                    else:
                        processed.append(r)
                        if r.get("items"):
                            all_empty = False
                if not all_empty:
                    aggregated = _aggregate_results(processed, targets, "ozon_product_list")
                    return json.dumps(aggregated, ensure_ascii=False, indent=2)
                # fall through to API if all shops empty

        # ── 线上读路径（refresh=True 或本地无数据或 offer_ids 筛选） ──
        async def _list_and_enrich(sid: str):
            last_id = f"page_{page}" if page > 1 else ""
            result = await _list_with_details(
                client, sid,
                limit=min(page_size, 1000),
                last_id=last_id,
                offer_ids=offer_ids,
                visibility=visibility,
            )
            # Save to local cache for next read
            try:
                storage = ProductStorage()
                for item in result.get("items", []):
                    await storage.save_product(sid, item)
            except Exception:
                pass
            return result

        if len(targets) == 1:
            result = _run_async(_list_and_enrich(targets[0]))
            return json.dumps(_describe(result, {
                "items": "商品列表",
                "items[].product_id": "Ozon 商品 ID（整数）",
                "items[].offer_id": "商品外部编码（SKU）",
                "items[].name": "商品名称",
                "items[].price": "当前售价 (₽)",
                "items[].old_price": "原价 (₽)，划线价",
                "items[].stock": "当前库存数量（件）",
                "items[].currency_code": "货币代码（如 RUB）",
                "items[].commission": "Ozon 佣金金额 (₽)",
                "items[].commission_percent": "佣金百分比",
                "items[].category": "商品类目名称",
                "items[].state": "商品状态",
                "items[].visibility": "可见性（ARCHIVED/IN_MODERATION/PUBLISHED/REJECTED）",
                "total": "商品总数",
            }), ensure_ascii=False, indent=2)
        else:
            results = _run_async(asyncio.gather(*[
                _list_and_enrich(sid) for sid in targets
            ], return_exceptions=True))

            processed_results = []
            for r in results:
                if isinstance(r, Exception):
                    processed_results.append({"error": str(r)})
                else:
                    processed_results.append(r)

            aggregated = _aggregate_results(processed_results, targets, "ozon_product_list")
            return json.dumps(_describe(aggregated, {
                "operation": "操作名称",
                "shops_processed": "查询的店铺数量",
                "shop_results": "各店铺的商品数据",
                "shop_results[].shop_id": "店铺 ID",
                "shop_results[].data.items": "该店铺的商品列表，字段同 items[].*",
                "summary.total_items": "所有店铺商品总数",
            }), ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_product_list, toolset="ozon")
@tool
def ozon_product_info(
    shop_id: str = None,
    shop_ids: list[str] = None,
    product_id: int = 0,
    product_ids: list[int] = None,
    refresh: bool = False,
) -> str:
    """获取 Ozon 产品详细信息（支持多店铺，默认读本地缓存）。

    默认从本地已同步的数据中读取。设置 refresh=True 时从 Ozon API 拉取最新数据。

    Args:
        shop_id: 单个店铺ID (与 shop_ids 二选一)
        shop_ids: 多个店铺ID (批量操作)
        product_id: Ozon 产品 ID（整数）
        product_ids: 多个产品 ID（在同一店铺查询）
        refresh: 是否强制从 Ozon API 刷新（默认 False）

    Returns:
        JSON 字符串，包含产品详细信息。多店铺时返回聚合结果。
    """
    targets = _resolve_shop_ids(shop_id, shop_ids)
    if not targets:
        return json.dumps({"error": "必须提供 shop_id 或 shop_ids"})

    if not product_id and not product_ids:
        return json.dumps({"error": "必须提供 product_id 或 product_ids"})

    try:
        client = get_ozon_client()
        from icross.core.storage.ozon_data import ProductStorage

        pids = product_ids or [product_id]

        # ── 本地读路径 ──────────────────────────────────────
        if not refresh:
            storage = ProductStorage()

            if len(targets) == 1 and len(pids) == 1:
                # Single shop, single product
                result = _run_async(storage.get_product(targets[0], pids[0]))
                if result:
                    return json.dumps(result, ensure_ascii=False, indent=2)
                # fall through to API
            elif len(targets) == 1:
                # Single shop, multiple products
                async def _read_products():
                    items = []
                    for pid in pids:
                        p = await storage.get_product(targets[0], pid)
                        if p:
                            items.append(p)
                    return {"items": items, "total": len(items)}
                result = _run_async(_read_products())
                if result.get("items"):
                    return json.dumps(result, ensure_ascii=False, indent=2)
                # fall through to API
            else:
                # Multiple shops (each gets same product_ids)
                async def _read_shop_products(sid):
                    items = []
                    for pid in pids:
                        p = await storage.get_product(sid, pid)
                        if p:
                            items.append(p)
                    return {"items": items, "total": len(items)}

                results = _run_async(asyncio.gather(*[
                    _read_shop_products(sid) for sid in targets
                ], return_exceptions=True))
                processed = [
                    r if not isinstance(r, Exception) else {"error": str(r)}
                    for r in results
                ]
                if any(
                    isinstance(r, dict) and r.get("items")
                    for r in processed
                ):
                    aggregated = _aggregate_results(processed, targets, "ozon_product_info")
                    return json.dumps(aggregated, ensure_ascii=False, indent=2)
                # fall through to API

        # ── 线上读路径 ──────────────────────────────────────
        if len(targets) > 1 and product_ids is None:
            pids_for_fetch = [product_id] if product_id else []

            async def fetch_shop(sid):
                result = await client.get_product_info_list(sid, product_ids=pids_for_fetch)
                # Save to local cache
                try:
                    storage = ProductStorage()
                    for item in result.get("items", []):
                        await storage.save_product(sid, item)
                except Exception:
                    pass
                return result

            results = _run_async(asyncio.gather(*[
                fetch_shop(sid) for sid in targets
            ], return_exceptions=True))

            processed_results = [
                r if not isinstance(r, Exception) else {"error": str(r)}
                for r in results
            ]
            aggregated = _aggregate_results(processed_results, targets, "ozon_product_info")
            return json.dumps(aggregated, ensure_ascii=False, indent=2)
        else:
            # Single shop or specific product list
            result = _run_async(client.get_product_info_list(targets[0], product_ids=pids))
            # Save to local cache
            try:
                storage = ProductStorage()
                for item in result.get("items", []):
                    _run_async(storage.save_product(targets[0], item))
            except Exception:
                pass
            return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_product_info, toolset="ozon")
@tool
def ozon_update_price(
    shop_id: str = None,
    shop_ids: list[str] = None,
    offer_id: str = "",
    product_id: int = 0,
    price: float = 0,
    old_price: float = 0,
    vat: str = "VAT_20",
) -> str:
    """更新 Ozon 产品价格（支持多店铺）。

    Args:
        shop_id: 单个店铺ID (与 shop_ids 二选一)
        shop_ids: 多个店铺ID (批量更新相同商品在不同店铺的价格)
        offer_id: 产品 offer_id (sku)
        product_id: Ozon 产品 ID（二选一）
        price: 新价格（必须是正数）
        old_price: 原价（用于显示折扣）
        vat: VAT 税率 (VAT_0, VAT_10, VAT_20)

    Returns:
        JSON 字符串，包含更新结果。多店铺时返回各店铺结果。
    """
    if price <= 0:
        return json.dumps({"success": False, "error": "价格必须大于 0"})
    if price > 1000000:
        return json.dumps({"success": False, "error": "价格超出允许范围"})

    targets = _resolve_shop_ids(shop_id, shop_ids)
    if not targets:
        return json.dumps({"success": False, "error": "必须提供 shop_id 或 shop_ids"})

    try:
        client = get_ozon_client()

        if len(targets) == 1:
            result = _run_async(client.update_price(
                shop_id=targets[0],
                offer_id=offer_id,
                product_id=product_id,
                price=price,
                old_price=old_price,
                vat=vat,
            ))
            return json.dumps({"success": True, "shop_id": targets[0], **result}, ensure_ascii=False, indent=2)
        else:
            async def update_shop(shop_id):
                return await client.update_price(
                    shop_id=shop_id,
                    offer_id=offer_id,
                    product_id=product_id,
                    price=price,
                    old_price=old_price,
                    vat=vat,
                )

            results = _run_async(asyncio.gather(*[
                update_shop(sid) for sid in targets
            ], return_exceptions=True))

            shop_results = []
            for sid, r in zip(targets, results):
                if isinstance(r, Exception):
                    shop_results.append({"shop_id": sid, "success": False, "error": str(r)})
                else:
                    shop_results.append({"shop_id": sid, "success": True, **r})

            return json.dumps({
                "success": True,
                "operation": "ozon_update_price",
                "shops_processed": len(targets),
                "shop_results": shop_results,
            }, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)



registry.register(ozon_update_price, toolset="ozon")
@tool
def ozon_update_stock(
    shop_id: str = None,
    shop_ids: list[str] = None,
    offer_id: str = "",
    product_id: int = 0,
    stock: int = 0,
    warehouse_id: int = 0,
) -> str:
    """更新 Ozon 产品库存（支持多店铺）。

    Args:
        shop_id: 单个店铺ID (与 shop_ids 二选一)
        shop_ids: 多个店铺ID (批量更新)
        offer_id: 产品 offer_id (sku)
        product_id: Ozon 产品 ID（二选一）
        stock: 新库存数量（必须是 >= 0）
        warehouse_id: 仓库 ID（FBS 必须）

    Returns:
        JSON 字符串，包含更新结果。
    """
    if stock < 0:
        return json.dumps({"success": False, "error": "库存不能为负数"})

    targets = _resolve_shop_ids(shop_id, shop_ids)
    if not targets:
        return json.dumps({"success": False, "error": "必须提供 shop_id 或 shop_ids"})

    try:
        client = get_ozon_client()

        if len(targets) == 1:
            result = _run_async(client.update_stock(
                shop_id=targets[0],
                offer_id=offer_id,
                product_id=product_id,
                stock=stock,
                warehouse_id=warehouse_id,
            ))
            return json.dumps({"success": True, "shop_id": targets[0], **result}, ensure_ascii=False, indent=2)
        else:
            async def update_shop(shop_id):
                return await client.update_stock(
                    shop_id=shop_id,
                    offer_id=offer_id,
                    product_id=product_id,
                    stock=stock,
                    warehouse_id=warehouse_id,
                )

            results = _run_async(asyncio.gather(*[
                update_shop(sid) for sid in targets
            ], return_exceptions=True))

            shop_results = []
            for sid, r in zip(targets, results):
                if isinstance(r, Exception):
                    shop_results.append({"shop_id": sid, "success": False, "error": str(r)})
                else:
                    shop_results.append({"shop_id": sid, "success": True, **r})

            return json.dumps({
                "success": True,
                "operation": "ozon_update_stock",
                "shops_processed": len(targets),
                "shop_results": shop_results,
            }, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)



registry.register(ozon_update_stock, toolset="ozon")
@tool
def ozon_analytics_stocks(shop_id: str, skus: list[str] = None) -> str:
    """获取产品库存分析（销量、库存天数、流转等级）。

    Args:
        shop_id: 店铺 ID
        skus: Ozon SKU 列表（不传时自动获取店铺所有产品的库存分析）

    Returns:
        JSON 字符串，包含库存分析数据。
    """
    try:
        client = get_ozon_client()

        if not skus:
            # Auto-fetch all products' Ozon SKUs
            products = _run_async(client.list_products(shop_id, limit=1000))
            product_ids = [p.get("product_id") for p in products.get("items", []) if p.get("product_id")]
            if not product_ids:
                return json.dumps({"error": "店铺中没有找到产品"}, ensure_ascii=False)

            # Get Ozon SKU numbers from product info
            sku_numbers = []
            for i in range(0, len(product_ids), 100):
                batch = product_ids[i:i + 100]
                info = _run_async(client.get_product_info_list(shop_id, product_ids=batch))
                for item in info.get("items", []):
                    sku = item.get("sku")
                    if isinstance(sku, int):
                        sku_numbers.append(sku)
        else:
            # Convert string SKUs to int
            sku_numbers = [int(s) for s in skus if s.strip().isdigit()]

        if not sku_numbers:
            return json.dumps({"error": "没有有效的 SKU"}, ensure_ascii=False)
        if len(sku_numbers) > 100:
            sku_numbers = sku_numbers[:100]

        result = _run_async(client.get_analytics_stocks(shop_id, sku_numbers))
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_analytics_stocks, toolset="ozon")
@tool
def ozon_order_list(
    shop_id: str = None,
    shop_ids: list[str] = None,
    limit: int = 100,
    offset: int = 0,
    since: str = "",
    status: str = "",
) -> str:
    """获取 Ozon 订单列表（支持多店铺，合并 FBO + FBS）。

    Args:
        shop_id: 单个店铺ID (与 shop_ids 二选一)
        shop_ids: 多个店铺ID (批量获取订单)
        limit: 每页数量
        offset: 偏移量
        since: 筛选起始日期（ISO 格式）
        status: 订单状态筛选

    Returns:
        JSON 字符串，包含 FBO + FBS 订单列表。多店铺时返回聚合结果。
    """
    targets = _resolve_shop_ids(shop_id, shop_ids)
    if not targets:
        return json.dumps({"error": "必须提供 shop_id 或 shop_ids"})

    try:
        client = get_ozon_client()

        async def fetch_all_orders(sid):
            """Fetch both FBO and FBS orders for a shop."""
            fbo_result = await client.get_order_list(
                shop_id=sid, limit=limit, offset=offset,
                since=since, status=status,
            )
            fbs_result = await client.list_fbs_postings(
                shop_id=sid, limit=limit, offset=offset,
                since=since, status=status,
            )
            # Merge with type annotations
            merged = {
                "shop_id": sid,
                "total": (fbo_result.get("total", 0) or 0) + (fbs_result.get("total", 0) or 0),
                "items": [],
            }
            for item in (fbo_result.get("items") or []):
                item["order_type"] = "FBO"
                merged["items"].append(item)
            for item in (fbs_result.get("items") or []):
                item["order_type"] = "FBS"
                merged["items"].append(item)
            return merged

        if len(targets) == 1:
            result = _run_async(fetch_all_orders(targets[0]))
            return json.dumps(_describe(result, {
                "items": "订单列表（FBO + FBS 合并）",
                "items[].order_id": "订单 ID",
                "items[].order_type": "订单类型：FBO / FBS",
                "items[].posting_number": "发货单号",
                "items[].status": "订单状态",
                "items[].products": "订单内的商品列表",
                "items[].products[].sku": "商品 SKU",
                "items[].products[].name": "商品名称",
                "items[].products[].quantity": "购买数量",
                "items[].products[].price": "单价 (₽)",
                "items[].products[].commission": "佣金 (₽) = price × commission_rate%",
                "items[].products[].payout": "商品入账 (₽) = price - 分摊费用",
                "items[].delivery_commission": "物流费 (₽)",
                "items[].total_price": "订单总金额 (₽)",
                "total": "订单总数",
                "shop_id": "店铺 ID",
            }), ensure_ascii=False, indent=2)
        else:
            results = _run_async(asyncio.gather(*[
                fetch_all_orders(sid) for sid in targets
            ], return_exceptions=True))

            processed_results = [
                r if not isinstance(r, Exception) else {"error": str(r)}
                for r in results
            ]
            aggregated = _aggregate_results(processed_results, targets, "ozon_order_list")
            return json.dumps(_describe(aggregated, {
                "operation": "操作名称",
                "shop_results": "各店铺订单数据",
                "shop_results[].data.items": "该店铺订单列表",
                "shop_results[].data.total": "该店铺订单数",
                "summary.total_items": "所有店铺合计订单数",
            }), ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_order_list, toolset="ozon")
@tool
def ozon_seller_info(shop_id: str, refresh: bool = False) -> str:
    """获取 Ozon 卖家账户信息（默认读本地缓存）。

    默认从本地已同步的卖家信息中读取。设置 refresh=True 时从 Ozon API 拉取最新数据。

    Args:
        shop_id: 店铺 ID
        refresh: 是否强制从 Ozon API 刷新（默认 False）

    Returns:
        JSON 字符串，包含卖家信息和评分。
    """
    try:
        from icross.core.storage.ozon_data import SellerInfoStorage

        # ── 本地读路径 ──────────────────────────────────────
        if not refresh:
            storage = SellerInfoStorage()
            result = _run_async(storage.get_seller_info(shop_id))
            if result:
                return json.dumps(result, ensure_ascii=False, indent=2)

        # ── 线上读路径 ──────────────────────────────────────
        client = get_ozon_client()
        result = _run_async(client.get_seller_info(shop_id))
        # Save to local cache
        try:
            storage = SellerInfoStorage()
            _run_async(storage.save_seller_info(shop_id, result))
        except Exception:
            pass
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_seller_info, toolset="ozon")
@tool
def update_product_cost_price(
    shop_id: str,
    product_id: int,
    cost_price: float,
) -> str:
    """设置/更新产品的采购成本价（人民币），用于利润核算。

    成本价保存在本地数据库中，不会同步到 Ozon。
    设置后可在订单利润分析中查看成本 vs 售价的利润空间。

    Args:
        shop_id: 店铺 ID
        product_id: Ozon 产品 ID
        cost_price: 采购成本价（人民币，必须 >= 0）

    Returns:
        JSON 字符串，包含更新结果。
    """
    if cost_price < 0:
        return json.dumps({"success": False, "error": "成本价不能为负数"})

    try:
        from icross.core.storage.ozon_data import ProductStorage

        storage = ProductStorage()
        result = _run_async(storage.update_product(shop_id, product_id, {
            "cost_price": cost_price,
        }))
        if result:
            return json.dumps({
                "success": True,
                "shop_id": shop_id,
                "product_id": product_id,
                "cost_price": cost_price,
                "product_name": result.get("name", ""),
            }, ensure_ascii=False, indent=2)
        else:
            return json.dumps({
                "success": False,
                "error": f"产品 {product_id} 在店铺 {shop_id} 中未找到，请先同步产品列表",
            }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)



registry.register(update_product_cost_price, toolset="ozon")
@tool
def ozon_get_warehouses(shop_id: str, refresh: bool = False) -> str:
    """获取 Ozon 仓库列表（默认读本地缓存）。

    默认从本地已同步的仓库数据中读取。设置 refresh=True 时从 Ozon API 拉取最新数据。

    Args:
        shop_id: 店铺 ID
        refresh: 是否强制从 Ozon API 刷新（默认 False）

    Returns:
        JSON 字符串，包含仓库列表。
    """
    try:
        from icross.core.storage.ozon_data import WarehouseStorage

        # ── 本地读路径 ──────────────────────────────────────
        if not refresh:
            storage = WarehouseStorage()
            items = _run_async(storage.list_warehouses(shop_id))
            if items:
                return json.dumps({"items": items}, ensure_ascii=False, indent=2)

        # ── 线上读路径 ──────────────────────────────────────
        client = get_ozon_client()
        result = _run_async(client.get_warehouses(shop_id))
        # Save to local cache
        try:
            storage = WarehouseStorage()
            for item in result.get("items", []):
                _run_async(storage.save_warehouse(shop_id, item))
        except Exception:
            pass
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ============================================================
# Example Tools (Phase 1 MVP)
# ============================================================



registry.register(ozon_get_warehouses, toolset="ozon")
@tool
def calculator(expression: str) -> str:
    """执行数学计算。

    Args:
        expression: 数学表达式，如 "100 * 23" 或 "2^10"

    Returns:
        计算结果的字符串形式。
    """
    try:
        allowed_chars = set("0123456789+-*/.() ")
        if not all(c in allowed_chars for c in expression):
            return json.dumps({"error": "表达式包含不允许的字符"})
        result = eval(expression)  # noqa: S307
        return json.dumps({"expression": expression, "result": result})
    except Exception as e:
        return json.dumps({"error": str(e)})



registry.register(calculator, toolset="default")
@tool
def get_current_time(timezone: str = "UTC") -> str:
    """获取当前时间。

    Args:
        timezone: 时区名称，如 "Asia/Shanghai", "Europe/Moscow", "UTC"

    Returns:
        当前时间的 JSON 字符串。
    """
    now = datetime.now()
    return json.dumps({
        "timezone": timezone,
        "datetime": now.isoformat(),
        "timestamp": int(now.timestamp()),
        "formatted": now.strftime("%Y-%m-%d %H:%M:%S"),
    })


# ============================================================
# Draft Review Tools (Phase 2 - Human-in-the-loop)
# ============================================================



registry.register(get_current_time, toolset="default")
@tool
def create_product_draft(
    shop_id: str,
    draft_type: str,
    title: str,
    description: str = "",
    price: float = 0,
    old_price: float = 0,
    stock: int = 0,
    offer_id: str = "",
    source_url: str = "",
    images: list[str] = None,
    attrs: dict = None,
) -> str:
    """创建产品草稿（待人工审核后发布到 Ozon）。

    Args:
        shop_id: 店铺 ID
        draft_type: 草稿类型 ("listing" | "price_update" | "stock_update")
        title: 产品标题
        description: 产品描述（俄语，用于 Ozon SEO）
        price: 价格（卢布）
        old_price: 原价（用于显示折扣）
        stock: 库存数量
        offer_id: 产品 SKU
        source_url: 来源链接（1688/拼多多等）
        images: 产品图片 URL 列表
        attrs: 额外属性字典

    Returns:
        JSON 字符串，包含草稿 ID 和状态。
    """
    from icross.core.storage.ozon_data import DraftStorage

    if price < 0:
        return json.dumps({"success": False, "error": "价格不能为负数"})
    if draft_type not in ("listing", "price_update", "stock_update"):
        return json.dumps({"success": False, "error": "draft_type 必须是 listing/price_update/stock_update 之一"})

    draft_storage = DraftStorage()
    try:
        result = _run_async(draft_storage.create_draft(
            shop_id=shop_id,
            draft_type=draft_type,
            title=title,
            description=description,
            price=price,
            old_price=old_price,
            stock=stock,
            offer_id=offer_id,
            source_url=source_url,
            images=images or [],
            attrs=attrs or {},
        ))
        return json.dumps({"success": True, "draft_id": result["id"], "status": result["status"]}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)



registry.register(create_product_draft, toolset="ozon")
@tool
def list_pending_drafts(shop_id: str, status: str = "pending") -> str:
    """列出待审核的产品草稿。

    Args:
        shop_id: 店铺 ID
        status: 状态筛选 ("pending" | "approved" | "rejected")

    Returns:
        JSON 字符串，包含草稿列表。
    """
    from icross.core.storage.ozon_data import DraftStorage

    try:
        draft_storage = DraftStorage()
        result = _run_async(draft_storage.list_drafts(shop_id=shop_id, status=status))
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ============================================================
# Phase 3: Product Creation Tool (Human-in-the-loop)
# ============================================================



registry.register(list_pending_drafts, toolset="ozon")
@tool
def ozon_product_create(
    shop_id: str,
    name: str,
    offer_id: str,
    price: float,
    description: str = "",
    vat: str = "VAT_20",
    images: list[str] = None,
    old_price: float = 0,
    source_url: str = "",
    stock: int = 0,
    description_category_id: int = 0,
    type_id: int = 0,
    category_attributes: list[dict] = None,
) -> str:
    """在 Ozon 上架商品（创建产品草稿 → 人工审核 → 自动发布）。

    注意：此工具不会立即上架，而是创建草稿等待人工审核。
    人工审核通过后会自动发布到 Ozon。
    如果提供了 description_category_id 和 type_id，上架时会将商品挂载到指定类目下。
    category_attributes 可用于传递类目特定属性（如品牌、颜色、尺寸等）。

    Args:
        shop_id: 店铺 ID
        name: 产品名称（俄语，最长500字符）
        offer_id: 产品 SKU（卖家自定义编号，最长50字符）
        price: 售价（卢布，必须大于0）
        description: 产品描述（俄语 HTML，可选）
        vat: 税率 (VAT_0, VAT_10, VAT_20)，默认 VAT_20
        images: 产品图片 URL 列表（最多30张）
        old_price: 原价（可选，用于显示折扣）
        source_url: 来源链接（1688/拼多多等）
        stock: 初始库存数量
        description_category_id: Ozon 类目 ID（可选，从分类树获取）
        type_id: Ozon 类型 ID（可选，与类目对应）
        category_attributes: 类目属性列表，格式 [{"id": 123, "values": [{"value": "..."}]}]

    Returns:
        JSON 字符串，包含草稿 ID 和状态。
    """
    if price <= 0:
        return json.dumps({"success": False, "error": "价格必须大于 0"})
    if not name or not offer_id:
        return json.dumps({"success": False, "error": "名称和 SKU 不能为空"})

    from icross.core.storage.ozon_data import DraftStorage

    attrs = {"vat": vat, "created_by": "agent"}
    if description_category_id:
        attrs["description_category_id"] = description_category_id
    if type_id:
        attrs["type_id"] = type_id
    if category_attributes:
        attrs["category_attributes"] = category_attributes

    draft_storage = DraftStorage()
    try:
        result = _run_async(draft_storage.create_draft(
            shop_id=shop_id,
            draft_type="listing",
            title=name,
            description=description,
            price=price,
            old_price=old_price or 0,
            stock=stock,
            offer_id=offer_id,
            source_url=source_url,
            images=images or [],
            attrs=attrs,
        ))
        return json.dumps({
            "success": True,
            "draft_id": result["id"],
            "status": result["status"],
            "message": f"已创建上架草稿 #{result['id']}，请前往 草稿审核 页面确认后自动发布",
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


# ============================================================
# ============================================================
# Phase 5: FBS Order Management Tools
# ============================================================



registry.register(ozon_product_create, toolset="ozon")
@tool
def ozon_fbs_order_list(
    shop_id: str = None,
    shop_ids: list[str] = None,
    limit: int = 100,
    offset: int = 0,
    since: str = "",
    status: str = "",
) -> str:
    """获取 FBS 订单列表。

    查看所有需要商家自己发货的 FBS 订单。
    与 ozon_order_list 不同，此工具只返回 FBS（商家发货）模式的订单。

    Args:
        shop_id: 单个店铺ID
        shop_ids: 多个店铺ID
        limit: 每页数量（最大1000）
        offset: 偏移量
        since: 起始日期（ISO格式，如 "2025-01-01T00:00:00"）
        status: 订单状态筛选

    Returns:
        JSON字符串，包含FBS订单列表。
    """
    targets = _resolve_shop_ids(shop_id, shop_ids)
    if not targets:
        return json.dumps({"error": "必须提供 shop_id 或 shop_ids"})

    try:
        client = get_ozon_client()

        if len(targets) == 1:
            result = _run_async(client.list_fbs_postings(
                shop_id=targets[0],
                limit=limit,
                offset=offset,
                since=since,
                status=status,
            ))
            return json.dumps(_describe(result, {
                "items": "FBS 订单列表",
                "items[].posting_number": "发货单号（FBS订单标识）",
                "items[].status": "订单状态：awaiting_registration/awaiting_approve/awaiting_packaging/awaiting_deliver/delivering/delivered/cancelled",
                "items[].products": "订单内商品列表",
                "items[].products[].sku": "商品 SKU",
                "items[].products[].name": "商品名称",
                "items[].products[].quantity": "数量",
                "items[].products[].price": "单价 (₽)",
                "items[].products[].commission": "佣金 (₽)",
                "items[].shipment_date": "最晚发货日期",
                "items[].delivery_cost": "物流费用 (₽)",
                "items[].total_price": "订单总额 (₽)",
                "total": "订单总数",
            }), ensure_ascii=False, indent=2)
        else:
            async def fetch_shop(sid):
                return await client.list_fbs_postings(
                    shop_id=sid, limit=limit, offset=offset, since=since, status=status,
                )

            results = _run_async(asyncio.gather(*[
                fetch_shop(sid) for sid in targets
            ], return_exceptions=True))

            processed_results = [
                r if not isinstance(r, Exception) else {"error": str(r)}
                for r in results
            ]
            aggregated = _aggregate_results(processed_results, targets, "ozon_fbs_order_list")
            return json.dumps(_describe(aggregated, {
                "operation": "操作名称",
                "shop_results": "各店铺 FBS 订单数据",
                "shop_results[].data.items": "该店铺 FBS 订单列表",
                "shop_results[].data.total": "该店铺订单数",
                "summary.total_items": "所有店铺合计订单数",
            }), ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_fbs_order_list, toolset="ozon")
@tool
def ozon_fbs_order_info(shop_id: str, posting_id: str) -> str:
    """获取 FBS 订单详情。

    Args:
        shop_id: 店铺 ID
        posting_id: FBS 订单号（如 "123456-7890-0001"）

    Returns:
        JSON字符串，包含订单详细信息（商品、物流、费用等）。
    """
    if not posting_id:
        return json.dumps({"error": "必须提供 posting_id"})

    try:
        client = get_ozon_client()
        result = _run_async(client.get_fbs_posting(shop_id, posting_id))
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_fbs_order_info, toolset="ozon")
@tool
def ozon_fbs_ship_orders(shop_id: str, posting_ids: list[str]) -> str:
    """确认 FBS 订单已打包完成，准备发货。

    使用此方法后，订单状态将变为 awaiting_deliver。
    注意：状态码200不代表订单已成功备货，请使用 ozon_fbs_order_info 检查订单是否完成备货。

    Args:
        shop_id: 店铺 ID
        posting_ids: 要发货的订单号列表，如 ["123456-7890-0001", "123456-7890-0002"]

    Returns:
        JSON字符串，包含发货结果。
    """
    if not posting_ids:
        return json.dumps({"error": "必须提供 posting_ids"})
    if len(posting_ids) > 100:
        return json.dumps({"error": "单次最多处理 100 个订单"})

    try:
        client = get_ozon_client()
        result = _run_async(client.fbs_ship_postings(shop_id, posting_ids))
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_fbs_ship_orders, toolset="ozon")
@tool
def ozon_fbs_awaiting_delivery(shop_id: str, posting_ids: list[str]) -> str:
    """标记 FBS 订单为「等待配送」（已交给承运商）。

    在确认打包发货后，将订单标记为已交给物流承运商。

    Args:
        shop_id: 店铺 ID
        posting_ids: 订单号列表

    Returns:
        JSON字符串，包含操作结果。
    """
    if not posting_ids:
        return json.dumps({"error": "必须提供 posting_ids"})

    try:
        client = get_ozon_client()
        result = _run_async(client.fbs_awaiting_delivery(shop_id, posting_ids))
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_fbs_awaiting_delivery, toolset="ozon")
@tool
def ozon_fbs_create_act(shop_id: str) -> str:
    """创建 FBS 订单的验收报告（Act of Acceptance）。

    Args:
        shop_id: 店铺 ID

    Returns:
        JSON字符串，包含验收报告 ID 和状态。
    """
    try:
        client = get_ozon_client()
        result = _run_async(client.fbs_create_act(shop_id))
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_fbs_create_act, toolset="ozon")
@tool
def ozon_fbs_get_act_status(shop_id: str, act_id: int) -> str:
    """查询 FBS 验收报告的状态。

    Args:
        shop_id: 店铺 ID
        act_id: 验收报告 ID

    Returns:
        JSON字符串，包含验收报告状态。
    """
    if not act_id:
        return json.dumps({"error": "必须提供 act_id"})

    try:
        client = get_ozon_client()
        result = _run_async(client.fbs_get_act_status(shop_id, act_id))
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ============================================================
# Phase 5: Advertising Management Tools
# ============================================================



registry.register(ozon_fbs_get_act_status, toolset="ozon")
@tool
def ozon_ad_campaigns_list(shop_id: str, page: int = 1, page_size: int = 50, state: str = "") -> str:
    """获取广告活动列表。

    Args:
        shop_id: 店铺 ID
        page: 页码
        page_size: 每页数量（最大1000）
        state: 按状态筛选（如 "CAMPAIGN_STATE_RUNNING", "CAMPAIGN_STATE_PLANNED"）

    Returns:
        JSON字符串，包含广告活动列表。
    """
    try:
        client = get_ozon_client()
        result = _run_async(client.list_ad_campaigns(shop_id, page=page, page_size=page_size, state=state))
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_ad_campaigns_list, toolset="ozon")
@tool
def ozon_ad_campaign_info(shop_id: str, campaign_id: int) -> str:
    """获取广告活动详情。

    Args:
        shop_id: 店铺 ID
        campaign_id: 广告活动 ID

    Returns:
        JSON字符串，包含广告活动详细信息。
    """
    if not campaign_id:
        return json.dumps({"error": "必须提供 campaign_id"})

    try:
        client = get_ozon_client()
        result = _run_async(client.get_ad_campaign(shop_id, campaign_id))
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_ad_campaign_info, toolset="ozon")
@tool
def ozon_ad_campaign_create(
    shop_id: str,
    title: str,
    daily_budget: float,
    start_date: str,
    end_date: str = "",
) -> str:
    """创建广告活动。

    Args:
        shop_id: 店铺 ID
        title: 广告活动名称
        daily_budget: 每日预算（卢布）
        start_date: 开始日期（ISO格式，如 "2025-06-01"）
        end_date: 结束日期（ISO格式，可选）

    Returns:
        JSON字符串，包含创建的广告活动信息。
    """
    if not title:
        return json.dumps({"error": "广告活动名称不能为空"})
    if daily_budget <= 0:
        return json.dumps({"error": "每日预算必须大于 0"})

    try:
        client = get_ozon_client()
        result = _run_async(client.create_ad_campaign(
            shop_id=shop_id,
            title=title,
            daily_budget=daily_budget,
            start_date=start_date,
            end_date=end_date,
        ))
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_ad_campaign_create, toolset="ozon")
@tool
def ozon_ad_campaign_update(
    shop_id: str,
    campaign_id: int,
    daily_budget: float = None,
    title: str = None,
) -> str:
    """更新广告活动。

    Args:
        shop_id: 店铺 ID
        campaign_id: 广告活动 ID
        daily_budget: 新的每日预算（可选）
        title: 新的活动名称（可选）

    Returns:
        JSON字符串，包含更新后的广告活动信息。
    """
    if not campaign_id:
        return json.dumps({"error": "必须提供 campaign_id"})

    try:
        client = get_ozon_client()
        result = _run_async(client.update_ad_campaign(
            shop_id=shop_id,
            campaign_id=campaign_id,
            daily_budget=daily_budget,
            title=title,
        ))
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_ad_campaign_update, toolset="ozon")
@tool
def ozon_ad_campaign_stats(
    shop_id: str,
    campaign_ids: list[int],
    date_from: str,
    date_to: str = "",
) -> str:
    """获取广告活动统计数据。

    包括展示次数、点击次数、花费、ROI 等指标。

    Args:
        shop_id: 店铺 ID
        campaign_ids: 广告活动 ID 列表
        date_from: 开始日期（ISO格式）
        date_to: 结束日期（ISO格式，可选）

    Returns:
        JSON字符串，包含广告活动统计数据。
    """
    if not campaign_ids:
        return json.dumps({"error": "必须提供 campaign_ids"})

    try:
        client = get_ozon_client()
        result = _run_async(client.get_ad_campaign_stats(
            shop_id=shop_id,
            campaign_ids=campaign_ids,
            date_from=date_from,
            date_to=date_to,
        ))
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_ad_campaign_stats, toolset="ozon")
@tool
def ozon_ad_campaign_products(shop_id: str, campaign_id: int, page: int = 1, page_size: int = 50) -> str:
    """获取广告活动中的商品列表。

    Args:
        shop_id: 店铺 ID
        campaign_id: 广告活动 ID
        page: 页码
        page_size: 每页数量

    Returns:
        JSON字符串，包含广告活动中的商品列表。
    """
    if not campaign_id:
        return json.dumps({"error": "必须提供 campaign_id"})

    try:
        client = get_ozon_client()
        result = _run_async(client.get_ad_campaign_products(
            shop_id=shop_id, campaign_id=campaign_id, page=page, page_size=page_size,
        ))
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ============================================================
# Phase 6: Returns Management
# ============================================================



registry.register(ozon_ad_campaign_products, toolset="ozon")
@tool
def ozon_returns_list(
    shop_id: str = None,
    shop_ids: list[str] = None,
    status: str = "",
    limit: int = 50,
    last_id: int = 0,
    return_schema: str = "",
) -> str:
    """获取 Ozon 退货列表（FBO + FBS/rFBS）。

    返回退货记录，包括商品、原因、状态、金额等信息。

    Args:
        shop_id: 单个店铺ID
        shop_ids: 多个店铺ID
        status: 按状态筛选（空=全部）
        limit: 每页数量
        last_id: 分页游标（上一页最后的退货ID）
        return_schema: 退货类型筛选（FBO/FBS/空=全部）

    Returns:
        JSON字符串，包含退货列表。
    """
    targets = _resolve_shop_ids(shop_id, shop_ids)
    if not targets:
        return json.dumps({"error": "必须提供 shop_id 或 shop_ids"})

    try:
        client = get_ozon_client()

        async def _fetch(sid):
            raw = await client.list_returns(sid, limit, last_id, return_schema, status)
            items = raw.get("returns") or raw.get("items") or []
            return {"items": items, "total": len(items), "has_next": raw.get("has_next", False)}

        if len(targets) == 1:
            result = _run_async(_fetch(targets[0]))
            return json.dumps(_describe(result, {
                "items": "退货列表",
                "items[].return_id": "退货 ID",
                "items[].product_name": "退货商品名称",
                "items[].sku": "商品 SKU",
                "items[].quantity": "退货数量",
                "items[].price": "商品售价 (₽)",
                "items[].return_reason": "退货原因描述",
                "items[].status": "退货状态：init/processing/returned_delivery/accepted/rejected/waiting_for_refund",
                "items[].created_at": "退货申请时间",
                "items[].return_type": "退货类型：FBO / FBS / rFBS",
                "items[].refund_amount": "退款金额 (₽)，通常等于商品售价",
                "total": "退货记录总数",
                "has_next": "是否有下一页数据",
            }), ensure_ascii=False, indent=2)
        else:
            results = _run_async(asyncio.gather(*[_fetch(sid) for sid in targets], return_exceptions=True))
            processed = []
            for r in results:
                if isinstance(r, Exception):
                    processed.append({"error": str(r)})
                else:
                    processed.append(r)
            aggregated = _aggregate_results(processed, targets, "ozon_returns_list")
            return json.dumps(_describe(aggregated, {
                "operation": "操作名称",
                "shop_results": "各店铺退货数据",
                "shop_results[].data.items": "该店铺退货列表",
                "summary.total_items": "所有店铺合计退货数",
            }), ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_returns_list, toolset="ozon")
@tool
def ozon_return_accept(
    shop_id: str,
    return_id: int,
    return_method_description: str = "",
) -> str:
    """验收退货（rFBS）。

    确认收到退货进行检验。

    Args:
        shop_id: 店铺 ID
        return_id: 退货 ID
        return_method_description: 退货方式描述（可选）

    Returns:
        JSON字符串，包含操作结果。
    """
    if not return_id:
        return json.dumps({"error": "必须提供 return_id"})
    try:
        client = get_ozon_client()
        result = _run_async(client.accept_return(shop_id, return_id, return_method_description))
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_return_accept, toolset="ozon")
@tool
def ozon_return_reject(
    shop_id: str,
    return_id: int,
    rejection_reason_id: int = 0,
    comment: str = "",
) -> str:
    """拒绝退货（rFBS），需要指定拒绝原因ID。

    Args:
        shop_id: 店铺 ID
        return_id: 退货 ID
        rejection_reason_id: 拒绝原因ID（通过 get_return_info 获取）
        comment: 拒绝备注（如果原因要求则必填）

    Returns:
        JSON字符串，包含操作结果。
    """
    if not return_id:
        return json.dumps({"error": "必须提供 return_id"})
    try:
        client = get_ozon_client()
        result = _run_async(client.reject_return(shop_id, return_id, rejection_reason_id, comment))
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_return_reject, toolset="ozon")
@tool
def ozon_finance_transactions(
    shop_id: str,
    from_date: str = "",
    to_date: str = "",
    page: int = 1,
    page_size: int = 100,
) -> str:
    """获取 Ozon 财务交易流水。

    Args:
        shop_id: 店铺 ID
        from_date: 开始日期（ISO格式）
        to_date: 结束日期（ISO格式）
        page: 页码
        page_size: 每页数量

    Returns:
        JSON字符串，包含交易流水。
    """
    if not shop_id:
        return json.dumps({"error": "必须提供 shop_id"})
    try:
        client = get_ozon_client()
        result = _run_async(client.list_transactions(shop_id, from_date, to_date, page, page_size))
        return json.dumps(_describe(result, {
            "rows": "交易流水行列表",
            "row.operation_date": "交易日期时间",
            "row.operation_type": "交易类型（如 Sale 销售、Commission 佣金、Delivery 物流费、Refund 退款等）",
            "row.operation_type_name": "交易类型的中文描述",
            "row.amount": "交易金额 (₽)，正数为收入，负数为支出",
            "row.type": "金额方向：accrual（收入）/ deduction（支出）",
            "row.description": "交易描述说明",
            "row.posting_number": "关联订单号（如果有）",
            "page": "当前页码",
            "page_size": "每页条数",
            "total": "总交易记录数",
        }), ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_finance_transactions, toolset="ozon")
@tool
def ozon_finance_daily_sales(
    shop_id: str,
    day: int,
    month: int,
    year: int,
) -> str:
    """获取每日销售报表（Premium Plus）。

    Args:
        shop_id: 店铺 ID
        day: 日（1-31）
        month: 月（1-12）
        year: 年

    Returns:
        JSON字符串，包含每日销售数据。
    """
    if not shop_id:
        return json.dumps({"error": "必须提供 shop_id"})
    if not day or not month or not year:
        return json.dumps({"error": "必须提供 day, month, year"})
    try:
        client = get_ozon_client()
        result = _run_async(client.get_daily_realization(shop_id, day, month, year))
        return json.dumps(_describe(result, {
            "rows": "每日销售明细行",
            "row.row_type": "行类型：aggregated（汇总）/ item（商品明细）",
            "row.product_name": "商品名称",
            "row.sku": "SKU 编码",
            "row.sale_price": "售价 (₽)",
            "row.quantity": "销售数量",
            "row.commission": "Ozon 佣金 (₽)",
            "row.payout": "入账金额 (₽) = sale_price × quantity - 各项费用",
            "row.accruals_sale": "销售应计金额 (₽)，佣金扣除前的收入",
            "row.accruals_delivery": "物流费补偿 (₽)",
            "header.total_payout": "当日总入账 (₽)，所有商品 payout 之和",
            "header.total_sales": "当日总销售额 (₽)，所有商品 sale_price × quantity 之和",
            "header.total_commission": "当日总佣金 (₽)",
        }), ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_finance_daily_sales, toolset="ozon")
@tool
def ozon_finance_realization(
    shop_id: str,
    month: int,
    year: int,
) -> str:
    """获取月度订单入账明细。

    Args:
        shop_id: 店铺 ID
        month: 月（1-12）
        year: 年

    Returns:
        JSON字符串，包含入账明细。
    """
    if not shop_id:
        return json.dumps({"error": "必须提供 shop_id"})
    if not month or not year:
        return json.dumps({"error": "必须提供 month 和 year"})
    try:
        client = get_ozon_client()
        result = _run_async(client.get_realization(shop_id, month, year))
        return json.dumps(_describe(result, {
            "rows": "入账明细行，每行对应一个商品的销售记录",
            "header.amount": "入账金额 (₽)，即扣除 Ozon 佣金后的实际到账收入",
            "header.sale_price": "商品售价 (₽)，买家支付金额",
            "header.commission": "Ozon 佣金金额 (₽) = sale_price × commission_rate%",
            "header.commission_rate": "佣金百分比，如 14 表示 14%",
            "header.quantity": "销售数量（件）",
            "header.payout": "最终入账 = sale_price - commission - 其他扣款",
            "header.accruals_sale": "销售应计金额 (₽)，佣金扣除前的收入",
            "header.accruals_delivery": "物流费补偿 (₽)",
            "row[key]": "row 中每项的 key=字段名, value=字段值",
        }), ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ============================================================
# Phase 7: Chat, Questions, Reviews & Marketing
# ============================================================



registry.register(ozon_finance_realization, toolset="ozon")
@tool
def ozon_chat_history(
    shop_id: str,
    chat_id: str,
    limit: int = 50,
) -> str:
    """获取 Ozon 买家聊天历史记录。

    Args:
        shop_id: 店铺 ID
        chat_id: 聊天会话 ID
        limit: 最大返回条数（最多 1000）

    Returns:
        JSON字符串，包含聊天消息列表。
    """
    if not shop_id:
        return json.dumps({"error": "必须提供 shop_id"})
    if not chat_id:
        return json.dumps({"error": "必须提供 chat_id"})
    try:
        client = get_ozon_client()
        result = _run_async(client.get_chat_history(shop_id, chat_id, limit))
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_chat_history, toolset="ozon")
@tool
def ozon_chat_send(
    shop_id: str,
    chat_id: str,
    text: str,
) -> str:
    """向买家发送聊天消息。

    Args:
        shop_id: 店铺 ID
        chat_id: 聊天会话 ID
        text: 消息内容

    Returns:
        JSON字符串，包含发送结果。
    """
    if not shop_id:
        return json.dumps({"error": "必须提供 shop_id"})
    if not chat_id:
        return json.dumps({"error": "必须提供 chat_id"})
    if not text:
        return json.dumps({"error": "消息内容不能为空"})
    try:
        client = get_ozon_client()
        result = _run_async(client.send_chat_message(shop_id, chat_id, text))
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_chat_send, toolset="ozon")
@tool
def ozon_chat_send_file(
    shop_id: str,
    chat_id: str,
    base64_content: str,
    file_name: str = "",
) -> str:
    """在聊天中发送文件（base64 编码）。

    Args:
        shop_id: 店铺 ID
        chat_id: 聊天会话 ID
        base64_content: 文件的 base64 编码内容
        file_name: 文件名（含扩展名）

    Returns:
        JSON字符串，包含发送结果。
    """
    if not shop_id:
        return json.dumps({"error": "必须提供 shop_id"})
    if not chat_id:
        return json.dumps({"error": "必须提供 chat_id"})
    if not base64_content:
        return json.dumps({"error": "文件内容不能为空"})
    try:
        client = get_ozon_client()
        result = _run_async(client.send_chat_file(shop_id, chat_id, base64_content, file_name))
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_chat_send_file, toolset="ozon")
@tool
def ozon_chat_unread_list(
    shop_id: str,
    limit: int = 30,
    cursor: str = "",
) -> str:
    """获取未读买家聊天会话列表。

    Args:
        shop_id: 店铺 ID
        limit: 每页数量（最多 1000）
        cursor: 分页游标（从上一页响应中获取）

    Returns:
        JSON字符串，包含未读会话列表。
    """
    if not shop_id:
        return json.dumps({"error": "必须提供 shop_id"})
    try:
        client = get_ozon_client()
        result = _run_async(client.list_unread_chats(shop_id, limit, cursor))
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_chat_unread_list, toolset="ozon")
@tool
def ozon_questions_list(
    shop_id: str,
    limit: int = 50,
    offset: int = 0,
    answered: bool = None,
) -> str:
    """获取 Ozon 商品买家问答列表。

    注意：Ozon 公开 Seller API 未提供问答相关接口，此功能不可用。

    Args:
        shop_id: 店铺 ID
        limit: 每页数量
        offset: 分页偏移
        answered: 按已回答状态筛选（True=已答，False=未答，None=全部）

    Returns:
        JSON字符串，包含问答列表。
    """
    return json.dumps({"_error": "Questions API is not available in the Ozon Seller API."}, ensure_ascii=False)



registry.register(ozon_questions_list, toolset="ozon")
@tool
def ozon_answer_question(
    shop_id: str,
    question_id: int,
    answer_text: str,
) -> str:
    """回答买家提问。

    注意：Ozon 公开 Seller API 未提供问答相关接口，此功能不可用。

    Args:
        shop_id: 店铺 ID
        question_id: 问题 ID
        answer_text: 回答内容

    Returns:
        JSON字符串，包含操作结果。
    """
    return json.dumps({"_error": "Questions API is not available in the Ozon Seller API."}, ensure_ascii=False)



registry.register(ozon_answer_question, toolset="ozon")
@tool
def ozon_reviews_list(
    shop_id: str,
    limit: int = 20,
    last_id: str = "",
    status: str = "ALL",
    sort_dir: str = "ASC",
) -> str:
    """获取商品评价列表（需 Premium Plus）。

    Args:
        shop_id: 店铺 ID
        limit: 每页数量（20-100）
        last_id: 分页游标（上一页最后的评价ID）
        status: ALL/UNPROCESSED/PROCESSED
        sort_dir: ASC/DESC

    Returns:
        JSON字符串，包含评价列表。
    """
    if not shop_id:
        return json.dumps({"error": "必须提供 shop_id"})
    try:
        client = get_ozon_client()
        result = _run_async(client.list_reviews(shop_id, limit, last_id, status, sort_dir))
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_reviews_list, toolset="ozon")
@tool
def ozon_reply_review(
    shop_id: str,
    review_id: str,
    reply_text: str,
    mark_as_processed: bool = True,
) -> str:
    """回复商品评价（需 Premium Plus）。

    Args:
        shop_id: 店铺 ID
        review_id: 评价 ID（字符串UUID）
        reply_text: 回复内容
        mark_as_processed: 是否标记为已处理

    Returns:
        JSON字符串，包含操作结果。
    """
    if not review_id:
        return json.dumps({"error": "必须提供 review_id"})
    if not reply_text:
        return json.dumps({"error": "必须提供 reply_text"})
    try:
        client = get_ozon_client()
        result = _run_async(client.reply_review(shop_id, review_id, reply_text, mark_as_processed))
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_reply_review, toolset="ozon")
@tool
def ozon_actions_list(
    shop_id: str = None,
    shop_ids: list[str] = None,
) -> str:
    """获取 Ozon 可用营销活动列表。

    Args:
        shop_id: 单个店铺ID
        shop_ids: 多个店铺ID

    Returns:
        JSON字符串，包含活动列表。
    """
    targets = _resolve_shop_ids(shop_id, shop_ids)
    if not targets:
        return json.dumps({"error": "必须提供 shop_id 或 shop_ids"})
    try:
        client = get_ozon_client()

        async def _fetch(sid):
            return await client.list_actions(sid)

        if len(targets) == 1:
            result = _run_async(_fetch(targets[0]))
            return json.dumps(result, ensure_ascii=False, indent=2)
        else:
            results = _run_async(asyncio.gather(*[_fetch(sid) for sid in targets], return_exceptions=True))
            processed = []
            for r in results:
                if isinstance(r, Exception):
                    processed.append({"error": str(r)})
                else:
                    processed.append(r)
            aggregated = _aggregate_results(processed, targets, "ozon_actions_list")
            return json.dumps(aggregated, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_actions_list, toolset="ozon")
@tool
def ozon_register_action_products(
    shop_id: str,
    action_id: int,
    products: list[dict],
) -> str:
    """将商品加入营销活动。

    每个商品需要指定: product_id(商品ID), action_price(活动价), stock(活动库存)。

    Args:
        shop_id: 店铺 ID
        action_id: 活动 ID
        products: 商品列表，每项为 {"product_id": int, "action_price": float, "stock": int}

    Returns:
        JSON字符串，包含操作结果。
    """
    if not action_id:
        return json.dumps({"error": "必须提供 action_id"})
    if not products:
        return json.dumps({"error": "必须提供 products"})
    try:
        client = get_ozon_client()
        result = _run_async(client.register_action_products(shop_id, action_id, products))
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ============================================================
# Phase 8: 数据报表 & 智能化
# ============================================================



registry.register(ozon_register_action_products, toolset="ozon")
@tool
def ozon_rating_summary(shop_id: str) -> str:
    """获取卖家评分摘要。

    Args:
        shop_id: 店铺 ID

    Returns:
        JSON字符串，包含评分数据（score, reviews_count 等）。
    """
    if not shop_id:
        return json.dumps({"error": "必须提供 shop_id"})
    try:
        client = get_ozon_client()
        result = _run_async(client.get_rating_summary(shop_id))
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_rating_summary, toolset="ozon")
@tool
def ozon_rating_history(shop_id: str, date_from: str = "", date_to: str = "") -> str:
    """获取评分历史趋势。

    Args:
        shop_id: 店铺 ID
        date_from: 开始日期 YYYY-MM-DD（可选）
        date_to: 结束日期 YYYY-MM-DD（可选）

    Returns:
        JSON字符串，包含评分历史数据。
    """
    if not shop_id:
        return json.dumps({"error": "必须提供 shop_id"})
    try:
        client = get_ozon_client()
        result = _run_async(client.get_rating_history(shop_id, date_from, date_to))
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_rating_history, toolset="ozon")
@tool
def ozon_transaction_totals(shop_id: str, date_from: str = "", date_to: str = "") -> str:
    """获取交易汇总数据（销售额、佣金、物流费、退款汇总）。

    Args:
        shop_id: 店铺 ID
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD

    Returns:
        JSON字符串，包含交易汇总数据。
    """
    if not shop_id:
        return json.dumps({"error": "必须提供 shop_id"})
    try:
        client = get_ozon_client()
        result = _run_async(client.get_transaction_totals(shop_id, date_from, date_to))
        return json.dumps(_describe(result, {
            "accruals_for_sale": "销售总收入 (₽)，包含所有订单的销售收入",
            "sale_commission": "Ozon 佣金总额 (₽) = 按订单收取的佣金之和",
            "processing_and_delivery": "订单处理和物流费用 (₽)",
            "accruals_for_delivery": "物流费补偿 (₽)，Ozon 给予的物流补贴",
            "accruals_for_buyer_change": "买家用后更改产生的费用调整 (₽)",
            "accruals_for_estimated_commission": "预估佣金调整 (₽)",
            "payout": "净入账 (₽) = accruals_for_sale - sale_commission - processing_and_delivery + adjustments",
        }), ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_transaction_totals, toolset="ozon")
@tool
def ozon_analytics_data(
    shop_id: str,
    metrics: str,
    dimension: str,
    date_from: str,
    date_to: str,
    limit: int = 1000,
) -> str:
    """获取Ozon数据分析（展示量、点击量、转化率、销售额等）。

    Args:
        shop_id: 店铺 ID
        metrics: 指标列表，逗号分隔（如 "hits_products_total,hits_search_total,orders,sales,conversion"）
        dimension: 维度，逗号分隔（如 "day,product"）
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
        limit: 最大返回行数（默认 1000）

    Returns:
        JSON字符串，包含分析数据。
    """
    if not shop_id:
        return json.dumps({"error": "必须提供 shop_id"})
    if not metrics or not dimension:
        return json.dumps({"error": "必须提供 metrics 和 dimension"})
    try:
        client = get_ozon_client()
        metric_list = [m.strip() for m in metrics.split(",")]
        dim_list = [d.strip() for d in dimension.split(",")]
        result = _run_async(client.get_analytics_data(
            shop_id, metric_list, dim_list, date_from, date_to, limit=limit,
        ))
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_analytics_data, toolset="ozon")
@tool
def ozon_product_queries(shop_id: str, date_from: str, date_to: str) -> str:
    """获取买家搜索词分析，了解买家通过什么关键词找到你的商品。

    Args:
        shop_id: 店铺 ID
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD

    Returns:
        JSON字符串，包含搜索词数据。
    """
    if not shop_id:
        return json.dumps({"error": "必须提供 shop_id"})
    if not date_from or not date_to:
        return json.dumps({"error": "必须提供 date_from 和 date_to"})
    try:
        client = get_ozon_client()
        result = _run_async(client.get_product_queries(shop_id, date_from, date_to))
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



registry.register(ozon_product_queries, toolset="ozon")
@tool
def generate_report(
    shop_id: str,
    report_type: str,
    date_from: str = "",
    date_to: str = "",
) -> str:
    """生成数据报表（异步任务，返回后可通过 report_id 查询进度）。

    支持的报表类型: products(商品列表), orders(订单报表), finance(入账明细), stocks(库存报表), analytics(数据分析)

    Args:
        shop_id: 店铺 ID
        report_type: 报表类型（products/orders/finance/stocks/analytics）
        date_from: 开始日期 YYYY-MM-DD（可选）
        date_to: 结束日期 YYYY-MM-DD（可选）

    Returns:
        JSON字符串，包含报表生成任务信息。
    """
    if not shop_id:
        return json.dumps({"error": "必须提供 shop_id"})
    if report_type not in ("products", "orders", "finance", "stocks", "analytics"):
        return json.dumps({"error": "报表类型必须为: products/orders/finance/stocks/analytics"})
    try:
        from icross.services.task_queue import create_and_run_task
        result = _run_async(create_and_run_task(
            task_type=f"report_{report_type}",
            params={
                "shop_id": shop_id,
                "report_id": "",  # will be set by the API; here just run the handler directly
                "date_from": date_from,
                "date_to": date_to,
            },
        ))
        return json.dumps(_describe(result, {
            "task_id": "报表任务 ID",
            "status": "任务状态：running / completed / failed",
            "report_type": "报表类型（products/orders/finance/stocks/analytics）",
            "created_at": "任务创建时间",
            "result": "报表数据（完成后填充）",
        }), ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ============================================================
# Notification Tools (Phase 8)
# ============================================================



registry.register(generate_report, toolset="ozon")
@tool
def send_notification(
    title: str = "",
    content: str = "",
    level: str = "info",
    target: str = "",
) -> str:
    """发送通知。任务完成时通知运营团队。

    默认发送到配置的飞书群，也可通过 target 参数指定目标平台和频道。

    Args:
        title: 通知标题（可选）。
        content: 通知正文，支持 Markdown 格式。
        level: 通知级别，可选 info / warning / error。
        target: 目标地址 "platform:chat_id" 格式，如 "feishu:oc_xxx"。为空时发到默认频道。

    Returns:
        JSON字符串，包含发送结果。
    """
    try:
        from icross.services.notification import get_notification_service
        from icross.services.platforms.routing import DeliveryTarget
        ns = get_notification_service()
        if not ns.ready:
            return json.dumps({
                "success": False,
                "error": "未配置通知频道。请在 .env 中设置飞书凭据或通过系统设置页面配置",
            }, ensure_ascii=False, indent=2)

        kwargs = {"title": title, "content": content, "level": level}
        if target:
            parsed = DeliveryTarget.parse(target)
            if parsed and parsed.is_valid():
                kwargs["chat_id"] = parsed.chat_id
                kwargs["platform"] = parsed.platform
            else:
                return json.dumps({
                    "success": False,
                    "error": f"无效的目标地址: {target}。格式应为 platform:chat_id，如 feishu:oc_xxx",
                }, ensure_ascii=False, indent=2)

        result = _run_async(ns.send(**kwargs))
        return json.dumps(_describe(result, {
            "success": "是否发送成功",
            "channel": "通知渠道",
            "target": "目标聊天 ID",
            "result": "API 返回的原始结果",
        }), ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ============================================================
# Phase 9 P2: Orchestration Tools
# ============================================================


@tool
def create_task_plan(name: str, steps: list, shop_id: str = "") -> dict:
    """创建一个多步骤任务计划。

    用于将复杂业务操作拆分为有序步骤，逐步执行。
    创建后使用 execute_task_plan 推进执行。

    Args:
        name: 计划名称，如 "退货处理+补货通知"。
        steps: 步骤列表，每个元素为 {"step_type": str, "description": str, "params": dict}。
               step_type 可选: "process_return" | "restock" | "notify" | "custom"
        shop_id: 关联店铺 ID（可选）。

    Returns:
        创建的计划对象，含 id 和 steps 列表。
    """
    from icross.services.plan_storage import create_plan as _create_plan
    plan = _create_plan(name, steps, shop_id=shop_id)
    return {
        "plan_id": plan["id"],
        "name": plan["name"],
        "status": plan["status"],
        "total_steps": len(plan["steps"]),
        "steps": [
            {"step_type": s["step_type"], "description": s["description"], "status": s["status"]}
            for s in plan["steps"]
        ],
    }


@tool
def execute_task_plan(plan_id: str) -> str:
    """推进任务计划到下一步。

    将当前步骤标记为已完成，然后激活下一个待办步骤。
    重复调用此工具可逐步推进计划。

    Args:
        plan_id: 任务计划 ID（由 create_task_plan 返回）。

    Returns:
        操作结果描述，告知 Agent 下一步该做什么。
    """
    from icross.services.plan_storage import get_plan, update_step, update_plan

    plan = get_plan(plan_id)
    if not plan:
        return f"错误: 未找到计划 '{plan_id}'"

    steps = plan.get("steps", [])
    current = plan.get("current_step", 0)
    status = plan.get("status", "pending")

    if status == "completed":
        return "计划已全部完成，无需继续。"

    if status == "failed":
        return "计划已失败，无法继续。"

    # Mark current step as completed if it's running
    if current < len(steps) and steps[current].get("status") == "running":
        update_step(plan_id, current, {"status": "completed"})
        current += 1
        update_plan(plan_id, {"current_step": current})

    # Find next pending step
    for i in range(current, len(steps)):
        if steps[i].get("status") == "pending":
            update_step(plan_id, i, {"status": "running"})
            remaining = len(steps) - i - 1
            return (
                f"请执行第 {i + 1}/{len(steps)} 步: {steps[i]['description']}\n"
                f"步骤类型: {steps[i]['step_type']}\n"
                f"参数: {steps[i].get('params', {})}\n"
                f"剩余步骤: {remaining}\n"
                f"完成后请再次调用 execute_task_plan(plan_id='{plan_id}') 继续下一步。"
            )

    # All steps complete
    update_plan(plan_id, {"status": "completed"})
    return "所有步骤已完成！任务计划执行完毕。"


@tool
def get_plan_status(plan_id: str = "") -> list:
    """查询任务计划的状态。

    Args:
        plan_id: 可选，指定计划 ID。不传则返回所有计划。

    Returns:
        计划状态列表，包含每个计划的进度和步骤状态。
    """
    from icross.services.plan_storage import get_plan, list_plans

    if plan_id:
        plans_data = [get_plan(plan_id)] if get_plan(plan_id) else []
    else:
        plans_data = list_plans()

    result = []
    for p in plans_data:
        steps = p.get("steps", [])
        done = sum(1 for s in steps if s.get("status") == "completed")
        result.append({
            "plan_id": p["id"],
            "name": p["name"],
            "status": p["status"],
            "progress": f"{done}/{len(steps)}",
            "current_step": p.get("current_step", 0),
            "steps": [
                {"description": s["description"], "status": s["status"], "step_type": s["step_type"]}
                for s in steps
            ],
        })
    return result


@tool
def schedule_job(
    name: str,
    job_type: str,
    cron_expr: str,
    params: dict = None,
    timezone: str = "Asia/Shanghai",
) -> dict:
    """创建一个定时任务（Cron 作业）。

    用于安排定期执行的任务，如每日销售报告推送飞书。

    Args:
        name: 任务名称，如 "每日销售报告"。
        job_type: 任务类型:
                 - "daily_sales_report": 生成销售日报并推送飞书
                 - "notification": 发送定时通知
                 - "custom_task": 自定义任务
        cron_expr: Cron 表达式，5 段式 "分 时 日 月 周"。
                   例如 "0 9 * * *" = 每天 9:00。
        params: 参数字典。对于 daily_sales_report:
                - shop_id: 店铺 ID
                - chat_id: 通知目标会话 ID
                - report_type: 报表类型 (finance/orders/products/stocks/analytics)
        timezone: 时区，默认 Asia/Shanghai。

    Returns:
        创建的定时任务信息。
    """
    from icross.services.scheduler import scheduler_service

    # Must import report_service to register handler
    import icross.services.report_service  # noqa: F401

    job_def = {
        "name": name,
        "job_type": job_type,
        "cron_expr": cron_expr,
        "params": params or {},
        "timezone": timezone,
        "enabled": True,
    }
    job_id = _run_async(scheduler_service.add_job(job_def))
    return {
        "success": True,
        "job_id": job_id,
        "name": name,
        "cron_expr": cron_expr,
        "next_run": cron_expr,
    }


@tool
def list_scheduled_jobs() -> list:
    """查看所有已配置的定时任务。

    Returns:
        定时任务列表，含名称、类型、Cron 表达式、启用状态。
    """
    from icross.services.scheduler import scheduler_service

    jobs = _run_async(scheduler_service.list_jobs())
    return [
        {
            "job_id": j.get("id"),
            "name": j.get("name"),
            "job_type": j.get("job_type"),
            "cron_expr": j.get("cron_expr"),
            "enabled": j.get("enabled"),
            "last_run": j.get("last_run"),
            "next_run": j.get("next_run"),
        }
        for j in jobs
    ]


# ============================================================
# Tool List for Agent Registration
# ============================================================


registry.register(send_notification, toolset="ozon")
registry.register(create_task_plan, toolset="ozon")
registry.register(execute_task_plan, toolset="ozon")
registry.register(get_plan_status, toolset="ozon")
registry.register(schedule_job, toolset="ozon")
registry.register(list_scheduled_jobs, toolset="ozon")
TOOLS = [
    # Example tools
    calculator,
    get_current_time,
    # Ozon tools (multi-shop enabled)
    ozon_product_list,
    ozon_product_info,
    ozon_update_price,
    ozon_update_stock,
    ozon_analytics_stocks,
    ozon_order_list,
    ozon_seller_info,
    ozon_get_warehouses,
    # Product cost price management
    update_product_cost_price,
    # Draft review tools
    create_product_draft,
    list_pending_drafts,
    # Phase 3: Product search & listing generation
    *PHASE3_TOOLS,
    # Phase 3: Product creation
    ozon_product_create,
    # Phase 5: FBS order management
    ozon_fbs_order_list,
    ozon_fbs_order_info,
    ozon_fbs_ship_orders,
    ozon_fbs_awaiting_delivery,
    ozon_fbs_create_act,
    ozon_fbs_get_act_status,
    # Phase 5: Advertising management
    ozon_ad_campaigns_list,
    ozon_ad_campaign_info,
    ozon_ad_campaign_create,
    ozon_ad_campaign_update,
    ozon_ad_campaign_stats,
    ozon_ad_campaign_products,
    # Phase 6: Returns & Finance
    ozon_returns_list,
    ozon_return_accept,
    ozon_return_reject,
    ozon_finance_transactions,
    ozon_finance_daily_sales,
    ozon_finance_realization,
    # Phase 7: Chat, Questions, Reviews & Marketing
    ozon_chat_history,
    ozon_chat_send,
    ozon_chat_send_file,
    ozon_chat_unread_list,
    ozon_questions_list,
    ozon_answer_question,
    ozon_reviews_list,
    ozon_reply_review,
    ozon_actions_list,
    ozon_register_action_products,
    # Phase 8: Rating, Analytics & Reports
    ozon_rating_summary,
    ozon_rating_history,
    ozon_transaction_totals,
    ozon_analytics_data,
    ozon_product_queries,
    generate_report,
    # Phase 8: Notification
    send_notification,
]