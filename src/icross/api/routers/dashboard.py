"""Dashboard summary API (Phase 8).

Aggregates data from multiple sources for the operations dashboard.
"""

import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Query

from icross.core.storage.ozon_data import (
    ProductStorage, ReportStorage, OrderStorage, AnalyticsStorage, WarehouseStorage, ShopStorage,
)

_logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.post("/invalidate-cache")
async def invalidate_dashboard_cache():
    """Invalidate all JsonStore caches so data files are re-read."""
    from icross.core.storage.ozon_data import ProductStorage, OrderStorage, AnalyticsStorage, DraftStorage, ShopStorage
    count = 0
    for cls in [ProductStorage, OrderStorage, AnalyticsStorage, DraftStorage, ShopStorage]:
        try:
            inst = cls()
            for attr in dir(inst):
                if attr.startswith('_') and hasattr(getattr(inst, attr), '_invalidate'):
                    getattr(inst, attr)._invalidate()
                    count += 1
        except Exception:
            pass
    return {"success": True, "invalidated": count}


def _mock_dashboard_summary() -> dict:
    """Return mock dashboard data for demo mode."""
    return {
        "rating": {"rating": 4.8, "rating_count": 326, "positive_rate": 98.5},
        "transactions": {"total": {"revenue": 458000, "commission": 45800, "payout": 412200}},
        "pending_returns": 3,
        "unread_chats": 5,
        "low_stock_count": 7,
        "active_actions": 2,
        "today_orders": 24,
        "today_gmv": 185000,
        "today_visitors": 1240,
        "conversion_rate": 1.9,
        "total_products": 156,
        "pending_drafts": 4,
        "shop_name": "演示店铺 (Demo)",
        "_demo": True,
    }


def _mock_dashboard_metrics() -> dict:
    """Return mock chart data for demo mode."""
    from datetime import datetime, timedelta
    today = datetime.now()
    daily_sales = []
    daily_orders = []
    for i in range(30):
        d = (today - timedelta(days=29 - i)).strftime("%Y-%m-%d")
        import random
        daily_sales.append({
            "date": d,
            "sales": round(random.uniform(3000, 12000), 2),
            "commission": round(random.uniform(300, 1200), 2),
            "payout": round(random.uniform(2700, 10800), 2),
        })
        daily_orders.append({
            "date": d,
            "orders": random.randint(5, 35),
        })
    return {
        "daily_sales": daily_sales,
        "daily_orders": daily_orders,
        "top_products": [
            {"name": "蓝牙耳机 Pro", "sales": 85000, "units": 120},
            {"name": "运动手表 S3", "sales": 72000, "units": 85},
            {"name": "智能手机壳", "sales": 45000, "units": 320},
            {"name": "无线充电器", "sales": 38000, "units": 210},
            {"name": "便携音箱 Mini", "sales": 29000, "units": 95},
        ],
        "period": {"date_from": (today - timedelta(days=30)).strftime("%Y-%m-%d"), "date_to": today.strftime("%Y-%m-%d")},
        "_demo": True,
    }


@router.get("/summary")
async def dashboard_summary(shop_id: str = Query(default=...)):
    """Aggregate dashboard summary data for a shop."""
    from icross.core.config import is_demo_mode
    if is_demo_mode():
        return _mock_dashboard_summary()

    # ── 0. Check if any shops exist ──
    shop_store = ShopStorage()
    all_shops = await shop_store.list_shops()
    if not all_shops:
        return {"no_shop": True, "message": "请先在配置管理中添加 Ozon 店铺"}
    if not shop_id or shop_id not in {s["shop_id"] for s in all_shops}:
        shop_id = all_shops[0]["shop_id"]

    result: dict = {
        "rating": None,
        "transactions": None,
        "pending_returns": 0,
        "unread_chats": 0,
        "low_stock_count": 0,
        "active_actions": 0,
        "metrics": {},
    }

    # ── 1. Rating summary (from API) ──
    try:
        from icross.services.ozon import get_ozon_client
        client = get_ozon_client()
        rating = await client.get_rating_summary(shop_id)
        result["rating"] = rating.get("result", rating) if isinstance(rating, dict) else rating
    except Exception as e:
        _logger.debug(f"Rating fetch skipped: {e}")

    # ── 2. Transaction totals (from API) ──
    try:
        from datetime import datetime, timedelta
        today = datetime.now()
        date_from = (today - timedelta(days=7)).strftime("%Y-%m-%d")
        date_to = today.strftime("%Y-%m-%d")
        tx = await client.get_transaction_totals(shop_id, date_from, date_to)
        result["transactions"] = tx.get("result", tx) if isinstance(tx, dict) else tx
    except Exception as e:
        _logger.debug(f"Transaction totals skipped: {e}")

    # ── 3. Pending returns (local) ──
    try:
        order_store = OrderStorage()
        orders = await order_store.list_orders(shop_id=shop_id, status="returned", limit=100)
        items = orders if isinstance(orders, list) else orders.get("items", [])
        result["pending_returns"] = len([o for o in items if o.get("status") in ("returned", "returning", "")])
    except Exception as e:
        _logger.debug(f"Returns count skipped: {e}")

    # ── 4. Low stock / analytics (local) ──
    try:
        analytics_store = AnalyticsStorage()
        analytics = await analytics_store.list_analytics(shop_id=shop_id)
        analytics_items = analytics.get("items", []) if isinstance(analytics, dict) else analytics
        result["low_stock_count"] = sum(
            1 for a in analytics_items
            if a.get("stock", 999) < (a.get("min_stock", a.get("low_stock_threshold", 10)) or 10)
        )
    except Exception as e:
        _logger.debug(f"Analytics skip: {e}")

    # ── 5. Active actions (from API) ──
    try:
        actions = await client.list_actions(shop_id)
        action_list = actions.get("result", []) if isinstance(actions, dict) else actions
        if isinstance(action_list, list):
            now_raw = __import__("datetime").datetime.now().isoformat()
            result["active_actions"] = sum(
                1 for a in action_list
                if a.get("state") == "running" or (
                    a.get("date_start", "") <= now_raw[:10] <= a.get("date_end", "")
                )
            )
    except Exception as e:
        _logger.debug(f"Actions count skip: {e}")

    # ── 6. Unread chats count (from API) ──
    try:
        chats = await client.list_unread_chats(shop_id)
        result["unread_chats"] = len(chats.get("chats", [])) if isinstance(chats, dict) else 0
    except Exception as e:
        _logger.debug(f"Unread chats skip: {e}")

    # ── 7. Shop info ──
    try:
        shop = await shop_store.get_shop(shop_id)
        if shop:
            result["shop_name"] = shop.get("name", shop.get("shop_name", ""))
    except Exception:
        pass

    # ── 8. Total products ──
    try:
        product_store = ProductStorage()
        product_list = await product_store.list_products(shop_id, limit=1)
        result["total_products"] = product_list.get("total", 0)
    except Exception:
        result["total_products"] = 0

    # ── 9. Today orders & GMV ──
    try:
        order_store = OrderStorage()
        orders_all = await order_store.list_orders(shop_id=shop_id, limit=10000)
        order_items = orders_all.get("items", [])
        today = datetime.now().strftime("%Y-%m-%d")
        today_orders = [
            o for o in order_items
            if o.get("created_at", "").startswith(today)
        ]
        result["today_orders"] = len(today_orders)
        result["today_gmv"] = sum(
            float(o.get("total", 0)) for o in today_orders
            if o.get("total")
        )
    except Exception:
        result["today_orders"] = 0
        result["today_gmv"] = 0

    # ── 10. Pending drafts ──
    try:
        from icross.core.storage.ozon_data import DraftStorage
        draft_store = DraftStorage()
        pending = await draft_store.list_drafts(shop_id=shop_id, status="pending", limit=1)
        result["pending_drafts"] = pending.get("total", 0)
    except Exception:
        result["pending_drafts"] = 0

    # ── 11. Today visitors (from analytics API) ──
    try:
        from datetime import datetime, timedelta
        today = datetime.now()
        visitors = await client.get_analytics_data(
            shop_id,
            metrics=["visitors"],
            dimension=["day"],
            date_from=today.strftime("%Y-%m-%d"),
            date_to=today.strftime("%Y-%m-%d"),
            limit=100,
        )
        v_data = visitors.get("result", visitors) if isinstance(visitors, dict) else visitors
        v_rows = []
        if isinstance(v_data, dict):
            v_rows = v_data.get("data", [])
        elif isinstance(v_data, list):
            v_rows = v_data
        total_visitors = 0
        for row in v_rows:
            metrics_vals = row.get("metrics", []) if isinstance(row, dict) else []
            for m in metrics_vals:
                if isinstance(m, dict) and "visitors" in m.get("name", ""):
                    total_visitors += int(float(m.get("value", 0)))
        result["today_visitors"] = total_visitors
        result["conversion_rate"] = round(
            (result.get("today_orders", 0) / total_visitors * 100) if total_visitors > 0 else 0,
            1,
        )
    except Exception as e:
        _logger.debug(f"Visitors fetch skip: {e}")
        result["today_visitors"] = 0
        result["conversion_rate"] = 0

    return result


@router.get("/metrics")
async def dashboard_metrics(shop_id: str = Query(default=...)):
    """获取看板图表数据（销售趋势、日订单量、热销商品）。

    Returns time-series data for ECharts visualization.
    """
    from icross.core.config import is_demo_mode
    if is_demo_mode():
        return _mock_dashboard_metrics()

    # ── Check if any shops exist ──
    from icross.core.storage.ozon_data import ShopStorage as _ShopStorage
    _shop_store = _ShopStorage()
    _all_shops = await _shop_store.list_shops()
    if not _all_shops:
        return {"no_shop": True, "message": "请先在配置管理中添加 Ozon 店铺", "daily_sales": [], "daily_orders": [], "top_products": []}
    if not shop_id or shop_id not in {s["shop_id"] for s in _all_shops}:
        shop_id = _all_shops[0]["shop_id"]

    from icross.services.ozon import get_ozon_client
    client = get_ozon_client()

    today = datetime.now()
    date_to = today.strftime("%Y-%m-%d")
    date_from_30d = (today - timedelta(days=30)).strftime("%Y-%m-%d")

    daily_sales: list[dict] = []
    daily_orders: list[dict] = []
    top_products: list[dict] = []

    # ── 1. Daily sales for last 30 days ──
    for i in range(30):
        d = today - timedelta(days=i)
        try:
            data = await client.get_daily_realization(shop_id, d.day, d.month, d.year)
            rows = data.get("result", data) if isinstance(data, dict) else data
            if isinstance(rows, list) and rows:
                row = rows[0]
                daily_sales.append({
                    "date": d.strftime("%Y-%m-%d"),
                    "sales": float(row.get("sales", 0)),
                    "commission": float(row.get("commission", 0)),
                    "payout": float(row.get("payout", 0)),
                })
            else:
                daily_sales.append({"date": d.strftime("%Y-%m-%d"), "sales": 0, "commission": 0, "payout": 0})
        except Exception as e:
            _logger.debug("Daily realization skip %s: %s", d.date(), e)
            daily_sales.append({"date": d.strftime("%Y-%m-%d"), "sales": 0, "commission": 0, "payout": 0})
    daily_sales.reverse()

    # ── 2. Analytics data for orders + top products ──
    try:
        analytics = await client.get_analytics_data(
            shop_id,
            metrics=["ordered_units", "revenue"],
            dimension=["sku", "day"],
            date_from=date_from_30d,
            date_to=date_to,
            limit=1000,
        )
        result_data = analytics.get("result", analytics) if isinstance(analytics, dict) else analytics
        if isinstance(result_data, dict):
            # Build daily orders map
            day_orders: dict[str, int] = {}
            # Build product sales map
            product_sales: dict[str, dict] = {}

            data_rows = result_data.get("data", []) if isinstance(result_data, dict) else []
            if not data_rows and isinstance(result_data, list):
                data_rows = result_data

            for row in data_rows:
                dimensions = row.get("dimensions", []) if isinstance(row, dict) else []
                metrics_vals = row.get("metrics", []) if isinstance(row, dict) else []

                date_val = ""
                sku_val = ""
                ordered = 0
                revenue = 0

                for dim in dimensions:
                    if isinstance(dim, dict):
                        if dim.get("name") == "day" or dim.get("type") == "day":
                            date_val = dim.get("value", "")
                        elif dim.get("name") == "sku" or dim.get("type") == "sku":
                            sku_val = dim.get("value", "")

                for m in metrics_vals:
                    if isinstance(m, dict):
                        if "ordered_units" in m.get("name", ""):
                            ordered = int(float(m.get("value", 0)))
                        elif "revenue" in m.get("name", ""):
                            revenue = float(m.get("value", 0))

                if date_val:
                    day_orders[date_val] = day_orders.get(date_val, 0) + ordered
                if sku_val and ordered > 0:
                    name = sku_val
                    if name not in product_sales:
                        product_sales[name] = {"name": name, "sales": 0, "units": 0}
                    product_sales[name]["sales"] += revenue
                    product_sales[name]["units"] += ordered

            # Fill daily_orders list
            for i in range(30):
                d = (today - timedelta(days=29 - i)).strftime("%Y-%m-%d")
                daily_orders.append({
                    "date": d,
                    "orders": day_orders.get(d, 0),
                })

            # Top products sorted by sales
            sorted_products = sorted(product_sales.values(), key=lambda x: x["sales"], reverse=True)
            top_products = sorted_products[:10]

    except Exception as e:
        _logger.debug("Analytics data skip: %s", e)

    return {
        "daily_sales": daily_sales,
        "daily_orders": daily_orders,
        "top_products": top_products,
        "period": {"date_from": date_from_30d, "date_to": date_to},
    }
