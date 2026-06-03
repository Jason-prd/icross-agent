"""Ozon data storage using JSON files - comprehensive data model."""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"


def _ensure_ozon_shop(client: Any, shop_id: str) -> None:
    """Register shop credentials with Ozon client from shops.json store."""
    store = JsonStore("shops.json")
    row = store._find("shop_id", shop_id)
    if row:
        client.add_shop(
            shop_id=shop_id,
            client_id=row.get("client_id") or None,
            api_key=row.get("api_key") or None,
            token=row.get("token") or None,
        )


def _get_data_path(filename: str) -> Path:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    return _DATA_DIR / filename


class JsonStore:
    """Base JSON file storage with class-level shared cache."""

    _shared_cache: dict[str, list[dict[str, Any]]] = {}

    def __init__(self, filename: str):
        self._path = _get_data_path(filename)
        self._cache_key = str(self._path)

    def _read(self) -> list[dict[str, Any]]:
        cached = self._shared_cache.get(self._cache_key)
        if cached is not None:
            return cached
        if not self._path.exists():
            return []
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._shared_cache[self._cache_key] = data
                return data
        except (json.JSONDecodeError, IOError):
            return []

    def _write(self, data: list[dict[str, Any]]) -> None:
        self._shared_cache[self._cache_key] = data
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _invalidate(self) -> None:
        self._shared_cache.pop(self._cache_key, None)

    def _find(self, key: str, value: Any) -> dict[str, Any] | None:
        for item in self._read():
            if item.get(key) == value:
                return item
        return None

    def _filter(self, **kwargs) -> list[dict[str, Any]]:
        results = []
        for item in self._read():
            if all(item.get(k) == v for k, v in kwargs.items()):
                results.append(item)
        return results

    def _upsert(self, key: str, value: Any, updates: dict[str, Any]) -> dict[str, Any]:
        data = self._read()
        for i, item in enumerate(data):
            if item.get(key) == value:
                data[i].update(updates)
                self._write(data)
                return data[i]
        new_item = {key: value, **updates}
        data.append(new_item)
        self._write(data)
        return new_item

    def _delete(self, key: str, value: Any) -> bool:
        data = self._read()
        new_data = [item for item in data if item.get(key) != value]
        if len(new_data) == len(data):
            return False
        self._write(new_data)
        return True

    def _insert(self, item: dict[str, Any]) -> dict[str, Any]:
        data = self._read()
        data.append(item)
        self._write(data)
        return item

    def _get_all(self) -> list[dict[str, Any]]:
        return self._read()


# ============================================================
# Shop Storage
# ============================================================

class ShopStorage:
    """Storage for Ozon seller shops.

    Data model:
    - shop_id: unique identifier
    - name: display name
    - client_id: Ozon API client ID
    - api_key: Ozon API key
    - token: OAuth token (alternative)
    - status: active/inactive
    - last_auth_check: timestamp of last auth verification
    - sync_days: number of days to sync orders (default 90)
    - created_at, updated_at: timestamps
    """

    def __init__(self):
        self._store = JsonStore("shops.json")

    async def add_shop(
        self,
        shop_id: str,
        name: str = "",
        client_id: str = "",
        api_key: str = "",
        token: str = "",
        sync_days: int = 90,
    ) -> dict[str, Any]:
        shop = {
            "shop_id": shop_id,
            "name": name or shop_id,
            "client_id": client_id,
            "api_key": api_key,
            "token": token,
            "status": "active",
            "sync_days": sync_days,
            "last_auth_check": None,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        existing = self._store._find("shop_id", shop_id)
        if existing:
            shop["created_at"] = existing.get("created_at", shop["created_at"])
            self._store._upsert("shop_id", shop_id, shop)
        else:
            self._store._insert(shop)
        return shop

    async def get_shop(self, shop_id: str) -> dict[str, Any] | None:
        return self._store._find("shop_id", shop_id)

    async def list_shops(self) -> list[dict[str, Any]]:
        shops = self._store._get_all()
        return [
            {
                "shop_id": s["shop_id"],
                "name": s.get("name", s["shop_id"]),
                "client_id": s.get("client_id", ""),
                "status": s.get("status", "active"),
                "sync_days": s.get("sync_days", 90),
                "last_auth_check": s.get("last_auth_check"),
                "created_at": s.get("created_at"),
                "updated_at": s.get("updated_at"),
            }
            for s in shops
        ]

    async def update_shop(self, shop_id: str, **kwargs) -> dict[str, Any] | None:
        kwargs["updated_at"] = datetime.now().isoformat()
        return self._store._upsert("shop_id", shop_id, kwargs)

    async def delete_shop(self, shop_id: str) -> None:
        self._store._delete("shop_id", shop_id)

    async def update_auth_check(self, shop_id: str, success: bool) -> None:
        self._store._upsert("shop_id", shop_id, {
            "last_auth_check": datetime.now().isoformat(),
            "auth_success": success,
            "updated_at": datetime.now().isoformat(),
        })

    async def authenticate_shop(self, shop_id: str) -> dict | None:
        """Verify shop credentials by making a test call to Ozon API."""
        shop = await self.get_shop(shop_id)
        if not shop:
            return None
        from icross.services.ozon import get_ozon_client
        client = get_ozon_client()
        client.add_shop(
            shop_id=shop_id,
            client_id=shop.get("client_id") or None,
            api_key=shop.get("api_key") or None,
            token=shop.get("token") or None,
        )
        try:
            info = await client.get_seller_info(shop_id)
            await self.update_auth_check(shop_id, True)
            return info
        except Exception:
            await self.update_auth_check(shop_id, False)
            return None


# ============================================================
# Product Storage
# ============================================================

class ProductStorage:
    """Storage for Ozon products.

    Data model:
    - id: internal UUID (not Ozon product_id)
    - shop_id: owning shop
    - product_id: Ozon product ID
    - offer_id: SKU
    - name: product name
    - price, old_price: current and original price
    - stock: available stock
    - status: product status
    - visibility: visibility state
    - images: product images
    - category_id, category_name: category info
    - brand: brand name
    - description: product description
    - attrs: additional attributes (JSON)
    - last_sync_at: last sync from Ozon
    - created_at, updated_at: timestamps
    """

    def __init__(self):
        self._products = JsonStore("products.json")
        self._price_history = JsonStore("price_history.json")
        self._stock_history = JsonStore("stock_history.json")

    async def save_product(self, shop_id: str, product_data: dict[str, Any]) -> None:
        """Save or update a product from Ozon API data."""
        product_id = product_data.get("product_id")
        if not product_id:
            return

        known_fields = {
            "product_id", "offer_id", "name", "price", "old_price", "cost_price",
            "stock", "status", "visibility", "archived",
            "has_fbo_stocks", "has_fbs_stocks", "is_discounted",
            "category_id", "category_name", "brand", "description",
            "images", "primary_image", "dimensions", "weight", "width", "height", "depth",
            "dimension_unit", "weight_unit",
            "attributes", "type_id",
            "currency_code",
        }
        product_attrs = {k: v for k, v in product_data.items() if k not in known_fields}

        updates = {
            "shop_id": shop_id,
            "product_id": product_id,
            "offer_id": product_data.get("offer_id"),
            "name": product_data.get("name", ""),
            "price": product_data.get("price"),
            "old_price": product_data.get("old_price"),
            "cost_price": product_data.get("cost_price"),
            "stock": product_data.get("stock", 0),
            "status": product_data.get("status"),
            "visibility": product_data.get("visibility"),
            "category_id": product_data.get("category_id"),
            "category_name": product_data.get("category_name"),
            "type_id": product_data.get("type_id"),
            "brand": product_data.get("brand"),
            "description": product_data.get("description"),
            "attributes": product_data.get("attributes"),
            "images": product_data.get("images", []),
            "primary_image": product_data.get("primary_image"),
            "currency_code": product_data.get("currency_code"),
            "weight": product_data.get("weight"),
            "width": product_data.get("width"),
            "height": product_data.get("height"),
            "depth": product_data.get("depth"),
            "dimension_unit": product_data.get("dimension_unit"),
            "weight_unit": product_data.get("weight_unit"),
            "attrs": product_attrs,
            "last_sync_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

        existing = self._find_by_shop_product(shop_id, product_id)
        if existing:
            # Track price changes
            if existing.get("price") != product_data.get("price"):
                self._price_history._insert({
                    "id": str(uuid.uuid4()),
                    "product_id": product_id,
                    "shop_id": shop_id,
                    "old_price": existing.get("price"),
                    "new_price": product_data.get("price"),
                    "changed_at": datetime.now().isoformat(),
                })
            # Track stock changes
            if existing.get("stock") != product_data.get("stock"):
                self._stock_history._insert({
                    "id": str(uuid.uuid4()),
                    "product_id": product_id,
                    "shop_id": shop_id,
                    "old_stock": existing.get("stock", 0),
                    "new_stock": product_data.get("stock", 0),
                    "changed_at": datetime.now().isoformat(),
                })
            self._products._upsert("id", existing["id"], updates)
        else:
            self._products._insert({"id": str(uuid.uuid4()), **updates})

    def _find_by_shop_product(self, shop_id: str, product_id: int) -> dict[str, Any] | None:
        for p in self._products._get_all():
            if p.get("shop_id") == shop_id and p.get("product_id") == product_id:
                return p
        return None

    async def get_product(self, shop_id: str, product_id: int) -> dict[str, Any] | None:
        return self._find_by_shop_product(shop_id, product_id)

    async def get_product_by_id(self, id: str) -> dict[str, Any] | None:
        """Look up product by internal UUID id field."""
        for p in self._products._get_all():
            if p.get("id") == id:
                return p
        return None

    async def list_products(
        self,
        shop_id: str,
        limit: int = 100,
        offset: int = 0,
        visibility: str | None = None,
    ) -> dict[str, Any]:
        all_products = self._products._filter(shop_id=shop_id)
        if visibility:
            all_products = [p for p in all_products if p.get("visibility") == visibility]

        total = len(all_products)
        items = sorted(all_products, key=lambda p: p.get("updated_at", ""), reverse=True)
        items = items[offset:offset + limit]
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    async def update_product_price(
        self,
        internal_id: str,
        new_price: float,
        old_price: float | None = None,
    ) -> None:
        """Update product price by internal UUID id."""
        all_products = self._products._get_all()
        for p in all_products:
            if p.get("id") == internal_id:
                p["price"] = new_price
                p["old_price"] = old_price
                p["updated_at"] = datetime.now().isoformat()
                self._products._write(all_products)
                product_id_int = p.get("product_id")
                if old_price is not None and product_id_int:
                    self._price_history._insert({
                        "id": str(uuid.uuid4()),
                        "product_id": product_id_int,
                        "old_price": old_price,
                        "new_price": new_price,
                        "changed_at": datetime.now().isoformat(),
                    })

    async def update_product(
        self,
        internal_id: str,
        updates: dict,
    ) -> None:
        """Update arbitrary product fields by internal UUID id."""
        all_products = self._products._get_all()
        for p in all_products:
            if p.get("id") == internal_id:
                for key, value in updates.items():
                    if value is not None:
                        p[key] = value
                p["updated_at"] = datetime.now().isoformat()
                self._products._write(all_products)
                return

    async def append_price_push_log(self, internal_id: str, log_entry: dict) -> None:
        """Append a price push log entry to the product's record.

        Keeps only the last 20 entries inline. The full history is
        stored in data/price_push_logs.json.
        """
        all_products = self._products._get_all()
        for p in all_products:
            if p.get("id") == internal_id:
                logs = p.get("price_push_logs", []) or []
                logs.append(log_entry)
                if len(logs) > 20:
                    logs = logs[-20:]
                p["price_push_logs"] = logs
                p["updated_at"] = datetime.now().isoformat()
                self._products._write(all_products)
                return

    async def update_product_by_ozon_ids(self, shop_id: str, product_id: int, updates: dict) -> dict | None:
        """Update arbitrary fields on a product by shop_id + Ozon product_id."""
        all_products = self._products._get_all()
        for p in all_products:
            if p.get("product_id") == product_id and p.get("shop_id") == shop_id:
                updates["updated_at"] = datetime.now().isoformat()
                p.update(updates)
                self._products._write(all_products)
                return p
        return None

    async def get_price_history(self, internal_id: str) -> list[dict[str, Any]]:
        """Get price history for a product by internal UUID id."""
        product = await self.get_product_by_id(internal_id)
        if not product:
            return []
        ozon_id = product.get("product_id")
        history = self._price_history._filter(product_id=ozon_id)
        return sorted(history, key=lambda h: h.get("changed_at", ""), reverse=True)

    async def get_stock_history(self, internal_id: str) -> list[dict[str, Any]]:
        """Get stock history for a product by internal UUID id."""
        product = await self.get_product_by_id(internal_id)
        if not product:
            return []
        ozon_id = product.get("product_id")
        history = self._stock_history._filter(product_id=ozon_id)
        return sorted(history, key=lambda h: h.get("changed_at", ""), reverse=True)

    async def delete_product(self, internal_id: str) -> None:
        """Delete a product by internal UUID id."""
        self._products._delete("id", internal_id)

    async def sync_from_ozon(self, shop_id: str, enrich: bool = True) -> dict[str, Any]:
        """Sync products from Ozon API.

        Args:
            shop_id: Shop identifier.
            enrich: If True, also fetch attributes, descriptions, and category names.
        """
        from icross.services.ozon import get_ozon_client

        client = get_ozon_client()
        _ensure_ozon_shop(client, shop_id)

        result = await client.list_products(shop_id, limit=1000)
        count = 0

        for item in result.get("items", []):
            await self.save_product(shop_id, item)
            count += 1

        all_product_ids = [item.get("product_id") for item in result.get("items", []) if item.get("product_id")]

        # Step 2: Get detailed info + resolve category names
        category_store = CategoryStorage() if enrich else None

        for i in range(0, len(all_product_ids), 100):
            batch_ids = all_product_ids[i:i + 100]
            try:
                detailed = await client.get_product_info_list(shop_id, product_ids=batch_ids)
                for item in detailed.get("items", []):
                    # Resolve category name from tree
                    if enrich and category_store:
                        cat_id = item.get("category_id")
                        if cat_id:
                            cat_info = await category_store.lookup_category_name(cat_id)
                            if cat_info:
                                item["category_name"] = cat_info.get("category_name", "")
                    await self.save_product(shop_id, item)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("Detail sync failed for batch %d–%d: %s", batch_ids[0], batch_ids[-1], e)

        # Step 3: Fetch attributes (batch call, max 1000 products)
        if enrich and all_product_ids:
            try:
                attrs_result = await client.get_product_attributes_list(shop_id, all_product_ids)
                attrs_items = attrs_result.get("result", [])
                for attr_item in attrs_items:
                    pid = attr_item.get("id")
                    if pid:
                        await self.update_product_by_ozon_ids(shop_id, pid, {
                            "attributes": attr_item.get("attributes", []),
                            "weight": attr_item.get("weight"),
                            "width": attr_item.get("width"),
                            "height": attr_item.get("height"),
                            "depth": attr_item.get("depth"),
                            "dimension_unit": attr_item.get("dimension_unit"),
                            "weight_unit": attr_item.get("weight_unit"),
                        })
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("Attributes fetch failed: %s", e)

        # Step 4: Fetch descriptions (with concurrency limit of 5)
        if enrich and all_product_ids:
            import asyncio
            sem = asyncio.Semaphore(5)

            async def _fetch_desc(pid: int) -> None:
                async with sem:
                    try:
                        desc_data = await client.get_product_description(shop_id, pid)
                        result_data = desc_data.get("result", desc_data)
                        if isinstance(result_data, dict):
                            desc = result_data.get("description", "")
                            if desc:
                                await self.update_product_by_ozon_ids(shop_id, pid, {"description": desc})
                    except Exception:
                        pass

            await asyncio.gather(*[_fetch_desc(pid) for pid in all_product_ids])

        return {"synced": count, "total": result.get("total", 0)}

    async def get_all_by_shop(self, shop_id: str) -> list[dict[str, Any]]:
        """Get all products for a shop (no pagination)."""
        return self._products._filter(shop_id=shop_id)


# ============================================================
# Order Storage
# ============================================================

class OrderStorage:
    """Storage for Ozon orders.

    Data model:
    - order_id: Ozon order ID
    - shop_id: owning shop
    - status: order status
    - created_at: order creation time
    - updated_at: last update
    - total: order total
    - items: list of order items
    - customer: customer info
    - address: delivery address
    """

    def __init__(self):
        self._orders = JsonStore("orders.json")

    async def save_order(self, shop_id: str, order_data: dict[str, Any]) -> None:
        """Save or update an order."""
        order_id = order_data.get("order_id")
        if not order_id:
            return

        existing = self._orders._find("order_id", order_id)

        updates = {
            "shop_id": shop_id,
            "order_id": order_id,
            "order_type": order_data.get("order_type"),
            "posting_number": order_data.get("posting_number") or order_data.get("posting_id"),
            "status": order_data.get("status"),
            "created_at": order_data.get("created_at") or (existing.get("created_at") if existing else None),
            "updated_at": datetime.now().isoformat(),
            "total": order_data.get("total") if order_data.get("total") is not None else (existing.get("total") if existing else None),
            "items": order_data.get("items", []),
            "products": order_data.get("products", []),
            "customer": order_data.get("customer", {}),
            "address": order_data.get("address", {}),
        }

        if existing:
            self._orders._upsert("order_id", order_id, updates)
        else:
            self._orders._insert(updates)

    async def get_order(self, order_id: str) -> dict[str, Any] | None:
        return self._orders._find("order_id", order_id)

    async def list_orders(
        self,
        shop_id: str,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        all_orders = self._orders._filter(shop_id=shop_id)
        if status:
            all_orders = [o for o in all_orders if o.get("status") == status]

        total = len(all_orders)
        items = sorted(all_orders, key=lambda o: o.get("created_at") or "", reverse=True)
        items = items[offset:offset + limit]
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    async def sync_from_ozon(self, shop_id: str, days: int = 30) -> dict[str, Any]:
        """Sync orders from Ozon API (FBO + FBS)."""
        from icross.services.ozon import get_ozon_client
        from datetime import datetime, timedelta

        client = get_ozon_client()
        _ensure_ozon_shop(client, shop_id)

        since = (datetime.now() - timedelta(days=days)).isoformat()
        count = 0

        # Sync FBO orders
        fbo_result = await client.get_order_list(shop_id, since=since)
        for item in fbo_result.get("items", []):
            item["order_type"] = "FBO"
            await self.save_order(shop_id, item)
            count += 1

        # Sync FBS postings
        fbs_result = await client.list_fbs_postings(shop_id, since=since)
        for item in fbs_result.get("items", []):
            item["order_type"] = "FBS"
            await self.save_order(shop_id, item)
            count += 1

        return {"synced": count, "total": count}


# ============================================================
# Analytics Storage
# ============================================================

class AnalyticsStorage:
    """Storage for Ozon analytics data.

    Data model:
    - id: unique ID
    - shop_id: owning shop
    - date: analytics date
    - type: type of analytics (stocks, sales, traffic)
    - data: analytics data JSON
    """

    def __init__(self):
        self._analytics = JsonStore("analytics.json")

    async def save_analytics(
        self,
        shop_id: str,
        analytics_type: str,
        date: str,
        data: dict[str, Any],
    ) -> None:
        """Save analytics data for a specific date."""
        key = f"{shop_id}_{analytics_type}_{date}"
        updates = {
            "shop_id": shop_id,
            "type": analytics_type,
            "date": date,
            "data": data,
            "saved_at": datetime.now().isoformat(),
        }
        existing = self._find_existing(shop_id, analytics_type, date)
        if existing:
            self._analytics._upsert("id", existing["id"], updates)
        else:
            self._analytics._insert({"id": key, **updates})

    def _find_existing(self, shop_id: str, analytics_type: str, date: str) -> dict[str, Any] | None:
        for item in self._analytics._get_all():
            if (item.get("shop_id") == shop_id and
                item.get("type") == analytics_type and
                item.get("date") == date):
                return item
        return None

    async def get_analytics(
        self,
        shop_id: str,
        analytics_type: str,
        date: str,
    ) -> dict[str, Any] | None:
        return self._find_existing(shop_id, analytics_type, date)

    async def list_analytics(
        self,
        shop_id: str,
        analytics_type: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[dict[str, Any]]:
        all_data = self._analytics._filter(shop_id=shop_id)
        if analytics_type:
            all_data = [d for d in all_data if d.get("type") == analytics_type]
        if from_date:
            all_data = [d for d in all_data if d.get("date", "") >= from_date]
        if to_date:
            all_data = [d for d in all_data if d.get("date", "") <= to_date]
        return sorted(all_data, key=lambda d: d.get("date", ""), reverse=True)

    async def sync_stocks_from_ozon(self, shop_id: str) -> dict[str, Any]:
        """Sync stock analytics from Ozon."""
        from datetime import datetime, timedelta
        from icross.services.ozon import get_ozon_client

        client = get_ozon_client()
        _ensure_ozon_shop(client, shop_id)
        date = datetime.now().strftime("%Y-%m-%d")

        try:
            # First get product list to obtain product_ids
            products = await client.list_products(shop_id, limit=1000)
            product_ids = [p.get("product_id") for p in products.get("items", []) if p.get("product_id")]
            if not product_ids:
                return {"success": True, "date": date, "items_count": 0, "message": "No products found"}

            # Batch-fetch product info to get Ozon SKUs (numeric IDs needed for analytics)
            all_sku_numbers = []
            for i in range(0, len(product_ids), 100):
                batch = product_ids[i:i + 100]
                info = await client.get_product_info_list(shop_id, product_ids=batch)
                for item in info.get("items", []):
                    sku = item.get("sku")
                    if isinstance(sku, int):
                        all_sku_numbers.append(sku)

            if not all_sku_numbers:
                return {"success": True, "date": date, "items_count": 0, "message": "No SKUs found"}

            # Fetch stock analytics for all products (batch of 100)
            all_items = []
            for i in range(0, len(all_sku_numbers), 100):
                batch = all_sku_numbers[i:i + 100]
                data = await client.get_analytics_stocks(shop_id, batch)
                all_items.extend(data.get("items", []))

            result = {"items": all_items, "total": len(all_items)}
            await self.save_analytics(shop_id, "stocks", date, result)
            return {"success": True, "date": date, "items_count": len(all_items)}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ============================================================
# Warehouse Storage
# ============================================================

class WarehouseStorage:
    """Storage for Ozon warehouses.

    Data model:
    - warehouse_id: Ozon warehouse ID
    - shop_id: owning shop
    - name: warehouse name
    - is_express: is express warehouse
    - is_fbo: FBO warehouse
    - is_fbs: FBS warehouse
    """

    def __init__(self):
        self._warehouses = JsonStore("warehouses.json")

    async def save_warehouse(self, shop_id: str, warehouse_data: dict[str, Any]) -> None:
        warehouse_id = warehouse_data.get("warehouse_id")
        if not warehouse_id:
            return

        updates = {
            "shop_id": shop_id,
            "warehouse_id": warehouse_id,
            "name": warehouse_data.get("name"),
            "status": warehouse_data.get("status", ""),
            "is_express": warehouse_data.get("is_express", False),
            "is_rfbs": warehouse_data.get("is_rfbs", False),
            "is_kgt": warehouse_data.get("is_kgt", False),
            "warehouse_type": warehouse_data.get("warehouse_type", ""),
            "address": warehouse_data.get("address", ""),
            "first_mile_type": warehouse_data.get("first_mile_type", ""),
        }

        existing = self._warehouses._find("warehouse_id", warehouse_id)
        if existing:
            self._warehouses._upsert("warehouse_id", warehouse_id, updates)
        else:
            self._warehouses._insert(updates)

    async def list_warehouses(self, shop_id: str) -> list[dict[str, Any]]:
        return self._warehouses._filter(shop_id=shop_id)

    async def sync_from_ozon(self, shop_id: str) -> dict[str, Any]:
        """Sync warehouses from Ozon."""
        from icross.services.ozon import get_ozon_client

        client = get_ozon_client()
        _ensure_ozon_shop(client, shop_id)
        try:
            result = await client.get_warehouses(shop_id)
            count = 0
            for wh in result.get("items", []):
                await self.save_warehouse(shop_id, wh)
                count += 1
            return {"synced": count}
        except Exception as e:
            return {"error": str(e)}


# ============================================================
# Session Storage
# ============================================================

class SessionStorage:
    """Storage for chat sessions.

    Data model:
    - session_id: unique ID
    - title: session title
    - created_at, updated_at: timestamps
    """

    def __init__(self):
        self._sessions = JsonStore("sessions.json")
        self._messages = JsonStore("session_messages.json")

    async def ensure_session(self, session_id: str, title: str | None = None) -> None:
        existing = self._sessions._find("session_id", session_id)
        if not existing:
            self._sessions._insert({
                "session_id": session_id,
                "title": title or f"会话 {session_id[:8]}",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            })

    async def save_message(
        self,
        session_id: str,
        message_type: str,
        content: Any,
        tool_name: str | None = None,
        tool_call_id: str | None = None,
        tool_calls: list[dict] | None = None,
    ) -> None:
        await self.ensure_session(session_id)
        self._messages._insert({
            "session_id": session_id,
            "message_type": message_type,
            "content": content,
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            "tool_calls": tool_calls,
            "created_at": datetime.now().isoformat(),
        })

    async def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        return self._messages._filter(session_id=session_id)

    async def update_last_ai_content(self, session_id: str, content: str) -> None:
        """Update the last AI message's content incrementally during streaming."""
        all_msgs = self._messages._get_all()
        for i in range(len(all_msgs) - 1, -1, -1):
            m = all_msgs[i]
            if m.get("session_id") == session_id and m.get("message_type") == "ai":
                all_msgs[i]["content"] = content
                self._messages._write(all_msgs)
                return

    async def list_sessions(self) -> list[dict[str, Any]]:
        sessions = self._sessions._get_all()
        return sorted(sessions, key=lambda s: s.get("updated_at", ""), reverse=True)

    async def delete_session(self, session_id: str) -> None:
        self._sessions._delete("session_id", session_id)
        all_msgs = self._messages._get_all()
        self._messages._write([m for m in all_msgs if m.get("session_id") != session_id])

    async def search_messages(self, keyword: str) -> list[dict[str, Any]]:
        results = []
        for msg in self._messages._get_all():
            content = str(msg.get("content", ""))
            if keyword.lower() in content.lower():
                session = self._sessions._find("session_id", msg["session_id"])
                results.append({
                    "session_id": msg["session_id"],
                    "session_title": session.get("title") if session else None,
                    "type": msg["message_type"],
                    "content": msg["content"],
                    "tool_name": msg.get("tool_name"),
                    "created_at": msg.get("created_at"),
                })
        return results

    async def update_session_title(self, session_id: str, title: str) -> None:
        self._sessions._upsert("session_id", session_id, {
            "title": title,
            "updated_at": datetime.now().isoformat(),
        })


# ============================================================
# Draft Storage
# ============================================================

class DraftStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class DraftStorage:
    """Storage for product drafts pending review.

    Data model:
    - id: unique ID
    - shop_id: owning shop
    - draft_type: listing | price_update | stock_update
    - title, description: product info
    - price, old_price, stock: values
    - offer_id, source_url: external references
    - images: product images
    - attrs: additional attributes
    - status: pending | approved | rejected
    - created_at, reviewed_at, reviewed_by, reject_reason
    """

    def __init__(self):
        self._drafts = JsonStore("drafts.json")

    async def create_draft(
        self,
        shop_id: str,
        draft_type: str,
        title: str = "",
        description: str = "",
        price: float = 0,
        old_price: float = 0,
        stock: int = 0,
        offer_id: str = "",
        source_url: str = "",
        images: list[str] | None = None,
        attrs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        draft_id = str(uuid.uuid4())[:8]
        draft = {
            "id": draft_id,
            "shop_id": shop_id,
            "draft_type": draft_type,
            "title": title,
            "description": description,
            "price": price,
            "old_price": old_price,
            "stock": stock,
            "offer_id": offer_id,
            "source_url": source_url,
            "images": images or [],
            "attrs": attrs or {},
            "status": DraftStatus.PENDING,
            "created_at": datetime.now().isoformat(),
            "reviewed_at": None,
            "reviewed_by": None,
            "reject_reason": None,
        }
        self._drafts._insert(draft)
        return {"id": draft_id, "status": DraftStatus.PENDING}

    async def get_draft(self, draft_id: str) -> dict[str, Any] | None:
        try:
            return self._drafts._find("id", int(draft_id))
        except (ValueError, TypeError):
            return self._drafts._find("id", draft_id)

    async def list_drafts(
        self,
        shop_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        all_drafts = self._drafts._get_all()

        if shop_id:
            all_drafts = [d for d in all_drafts if d.get("shop_id") == shop_id]
        if status:
            all_drafts = [d for d in all_drafts if d.get("status") == status]

        total = len(all_drafts)
        items = sorted(all_drafts, key=lambda d: d.get("created_at", ""), reverse=True)
        items = items[offset:offset + limit]
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    async def approve_draft(self, draft_id: str, reviewed_by: str = "system") -> dict[str, Any] | None:
        try:
            draft = self._drafts._find("id", int(draft_id))
        except (ValueError, TypeError):
            draft = self._drafts._find("id", draft_id)

        if not draft:
            return None

        self._drafts._upsert("id", draft["id"], {
            "status": DraftStatus.APPROVED,
            "reviewed_at": datetime.now().isoformat(),
            "reviewed_by": reviewed_by,
        })
        return self.get_draft(draft["id"])

    async def reject_draft(
        self,
        draft_id: str,
        reject_reason: str,
        reviewed_by: str = "system",
    ) -> dict[str, Any] | None:
        try:
            draft = self._drafts._find("id", int(draft_id))
        except (ValueError, TypeError):
            draft = self._drafts._find("id", draft_id)

        if not draft:
            return None

        self._drafts._upsert("id", draft["id"], {
            "status": DraftStatus.REJECTED,
            "reviewed_at": datetime.now().isoformat(),
            "reviewed_by": reviewed_by,
            "reject_reason": reject_reason,
        })
        return self.get_draft(draft["id"])

    async def update_draft_publish(
        self,
        draft_id: str,
        published: bool,
        ozon_task_id: int | None = None,
        publish_error: str | None = None,
    ) -> None:
        """Update draft with publish result after approving."""
        try:
            draft = self._drafts._find("id", int(draft_id))
        except (ValueError, TypeError):
            draft = self._drafts._find("id", draft_id)
        if not draft:
            return
        updates = {"published": published, "updated_at": datetime.now().isoformat()}
        if ozon_task_id is not None:
            updates["ozon_task_id"] = ozon_task_id
        if publish_error is not None:
            updates["publish_error"] = publish_error
        self._drafts._upsert("id", draft["id"], updates)

    async def delete_draft(self, draft_id: str) -> None:
        try:
            self._drafts._delete("id", int(draft_id))
        except (ValueError, TypeError):
            self._drafts._delete("id", draft_id)


# ============================================================
# Seller Info Storage
# ============================================================

class SellerInfoStorage:
    """Storage for Ozon seller info.

    Data model:
    - shop_id: owning shop
    - company: company name
    - email, phone: contact info
    - balance: account balance
    - metrics: performance metrics
    - cached_at: cache timestamp
    """

    def __init__(self):
        self._seller_info = JsonStore("seller_info.json")

    async def save_seller_info(self, shop_id: str, info: dict[str, Any]) -> None:
        updates = {
            "shop_id": shop_id,
            "company": info.get("name"),  # Ozon returns 'name' not 'company'
            "legal_name": info.get("legal_name"),
            "client_id": info.get("client_id"),
            "is_premium": info.get("is_premium", False),
            "ratings": info.get("ratings", []),
            "cached_at": datetime.now().isoformat(),
        }
        existing = self._seller_info._find("shop_id", shop_id)
        if existing:
            self._seller_info._upsert("shop_id", shop_id, updates)
        else:
            self._seller_info._insert(updates)

    async def get_seller_info(self, shop_id: str) -> dict[str, Any] | None:
        return self._seller_info._find("shop_id", shop_id)

    async def sync_from_ozon(self, shop_id: str) -> dict[str, Any]:
        """Sync seller info from Ozon."""
        from icross.services.ozon import get_ozon_client

        client = get_ozon_client()
        _ensure_ozon_shop(client, shop_id)
        try:
            info = await client.get_seller_info(shop_id)
            await self.save_seller_info(shop_id, info)
            return {"success": True, "company": info.get("name")}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ============================================================
# Sync Log Storage
# ============================================================

class SyncLogStorage:
    """Storage for sync operation logs.

    Data model:
    - id: unique ID
    - shop_id: owning shop
    - operation: sync operation type
    - status: success | failed
    - items_synced: number of items
    - error: error message if failed
    - started_at, completed_at: timestamps
    """

    def __init__(self):
        self._logs = JsonStore("sync_logs.json")

    def log_sync(
        self,
        shop_id: str,
        operation: str,
        status: str,
        items_synced: int = 0,
        error: str | None = None,
    ) -> None:
        self._logs._insert({
            "id": str(uuid.uuid4()),
            "shop_id": shop_id,
            "operation": operation,
            "status": status,
            "items_synced": items_synced,
            "error": error,
            "started_at": datetime.now().isoformat(),
            "completed_at": datetime.now().isoformat(),
        })

    async def get_logs(
        self,
        shop_id: str | None = None,
        operation: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        logs = self._logs._get_all()
        if shop_id:
            logs = [l for l in logs if l.get("shop_id") == shop_id]
        if operation:
            logs = [l for l in logs if l.get("operation") == operation]
        return sorted(logs, key=lambda l: l.get("completed_at", ""), reverse=True)[:limit]


# ============================================================
# Price Push Log Storage
# ============================================================

class PricePushLogStorage:
    """Storage for price push history logs.

    Data model:
    - id: unique log entry ID
    - product_id: local product UUID
    - ozon_product_id: Ozon product ID
    - shop_id: shop identifier
    - old_price: price before push
    - new_price: price after push
    - status: success | failed
    - ozon_response: Ozon API response dict (serialized)
    - error: error message if failed
    - pushed_at: ISO timestamp of push
    """

    def __init__(self):
        self._logs = JsonStore("price_push_logs.json")

    async def add_log(self, log_entry: dict) -> None:
        """Add a push log entry."""
        self._logs._insert(log_entry)

    async def list_logs(
        self,
        shop_id: str | None = None,
        product_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """List push logs with optional filters and pagination."""
        logs = self._logs._get_all()
        if shop_id:
            logs = [l for l in logs if l.get("shop_id") == shop_id]
        if product_id:
            logs = [l for l in logs if l.get("product_id") == product_id]
        logs.sort(key=lambda l: l.get("pushed_at", ""), reverse=True)
        total = len(logs)
        items = logs[offset:offset + limit]
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    async def get_log(self, log_id: str) -> dict | None:
        """Get a single push log entry by ID."""
        return self._logs._find("id", log_id)


# ============================================================
# Listing Template Storage (Phase 3)
# ============================================================

class ListingTemplateStorage:
    """Storage for Listing generation prompt templates.

    Data model:
    - id: unique ID
    - shop_id: owning shop (None = global)
    - name: template name
    - prompt_template: LLM prompt template text
    - is_default: is the default template
    - created_at, updated_at: timestamps
    """

    def __init__(self):
        self._templates = JsonStore("listing_templates.json")

    async def create_template(
        self,
        name: str,
        prompt_template: str,
        shop_id: str | None = None,
        is_default: bool = False,
    ) -> dict[str, Any]:
        template_id = str(uuid.uuid4())[:8]
        template = {
            "id": template_id,
            "shop_id": shop_id,
            "name": name,
            "prompt_template": prompt_template,
            "is_default": is_default,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        self._templates._insert(template)
        return template

    async def list_templates(
        self,
        shop_id: str | None = None,
    ) -> list[dict[str, Any]]:
        templates = self._templates._get_all()
        if shop_id:
            templates = [t for t in templates if t.get("shop_id") in (shop_id, None)]
        return sorted(templates, key=lambda t: (not t.get("is_default", False), t.get("name", "")))

    async def get_template(self, template_id: str) -> dict[str, Any] | None:
        return self._templates._find("id", template_id)

    async def get_default_template(self) -> dict[str, Any] | None:
        for t in self._templates._get_all():
            if t.get("is_default"):
                return t
        return None

    async def update_template(
        self,
        template_id: str,
        name: str | None = None,
        prompt_template: str | None = None,
        is_default: bool | None = None,
    ) -> dict[str, Any] | None:
        updates: dict[str, Any] = {"updated_at": datetime.now().isoformat()}
        if name is not None:
            updates["name"] = name
        if prompt_template is not None:
            updates["prompt_template"] = prompt_template
        if is_default is not None:
            updates["is_default"] = is_default
        return self._templates._upsert("id", template_id, updates)

    async def delete_template(self, template_id: str) -> None:
        self._templates._delete("id", template_id)


# ============================================================
# Pricing Rule Storage (Phase 4)
# ============================================================

class PricingRuleStorage:
    """Storage for auto-pricing rules.

    Data model:
    - id: unique ID
    - shop_id: owning shop
    - name: rule name
    - rule_type: markup | discount | match_competitor | fixed
    - condition: dict of conditions (category, min_price, max_price, etc.)
    - action: dict of action (adjustment_type, value)
    - priority: rule priority (lower = higher priority)
    - enabled: whether rule is active
    - last_applied: last application timestamp
    - created_at, updated_at: timestamps
    """

    def __init__(self):
        self._rules = JsonStore("pricing_rules.json")

    async def create_rule(
        self,
        shop_id: str,
        name: str,
        rule_type: str,
        condition: dict,
        action: dict,
        priority: int = 0,
        enabled: bool = True,
    ) -> dict:
        rule_id = str(uuid.uuid4())[:8]
        rule = {
            "id": rule_id,
            "shop_id": shop_id,
            "name": name,
            "rule_type": rule_type,
            "condition": condition,
            "action": action,
            "priority": priority,
            "enabled": enabled,
            "last_applied": None,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        self._rules._insert(rule)
        return rule

    async def list_rules(self, shop_id: str | None = None) -> list[dict]:
        rules = self._rules._get_all()
        if shop_id:
            rules = [r for r in rules if r.get("shop_id") == shop_id]
        return sorted(rules, key=lambda r: r.get("priority", 0))

    async def get_rule(self, rule_id: str) -> dict | None:
        return self._rules._find("id", rule_id)

    async def update_rule(self, rule_id: str, **kwargs) -> dict | None:
        kwargs["updated_at"] = datetime.now().isoformat()
        return self._rules._upsert("id", rule_id, kwargs)

    async def delete_rule(self, rule_id: str) -> bool:
        return self._rules._delete("id", rule_id)

    async def apply_rules_to_product(self, shop_id: str, product: dict) -> dict | None:
        """Apply matching rules to a product and return adjusted price."""
        rules = [r for r in await self.list_rules(shop_id) if r.get("enabled")]
        if not rules:
            return None

        current_price = product.get("price", 0)
        if not current_price:
            return None

        adjusted_price = current_price
        applied_rule = None

        for rule in rules:
            condition = rule.get("condition", {})
            # Check conditions
            cat_name = (product.get("category_name") or "").lower()
            cond_cat = (condition.get("category") or "").lower()
            if cond_cat and cond_cat not in cat_name:
                continue

            min_p = condition.get("min_price")
            max_p = condition.get("max_price")
            if min_p is not None and current_price < min_p:
                continue
            if max_p is not None and current_price > max_p:
                continue

            # Apply action
            action = rule.get("action", {})
            adj_type = action.get("adjustment_type", "fixed")
            adj_value = float(action.get("value", 0))

            if adj_type == "markup":
                adjusted_price = current_price * (1 + adj_value / 100)
            elif adj_type == "discount":
                adjusted_price = current_price * (1 - adj_value / 100)
            elif adj_type == "fixed":
                adjusted_price = adj_value
            elif adj_type == "round":
                adjusted_price = round(current_price / adj_value) * adj_value
            elif adj_type == "cost_plus":
                # cost_plus: use OzonCostCalculator to compute price from cost data
                # Product must have cost data stored in attrs
                adjusted_price = self._apply_cost_plus(product, adj_value)
                if adjusted_price is None:
                    continue  # skip if no cost data

            applied_rule = rule
            # Don't break — lower priority rules can override (since sorted by priority)
            # Actually with priority, lower number = higher priority, so break after first match
            break

        if applied_rule and adjusted_price != current_price:
            self._rules._upsert("id", applied_rule["id"], {
                "last_applied": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            })

        return {
            "original_price": current_price,
            "adjusted_price": round(adjusted_price, 2),
            "rule_name": applied_rule["name"] if applied_rule else None,
            "rule_id": applied_rule["id"] if applied_rule else None,
        }

    def _apply_cost_plus(self, product: dict, target_margin: float) -> float | None:
        """Apply cost-plus pricing using OzonCostCalculator.

        Reads cost data from product attrs or top-level fields.
        Returns None if no cost data available.
        """
        attrs = product.get("attrs", {}) or {}
        purchase = (
            product.get("purchase_price_cny")
            or attrs.get("purchase_price_cny")
        )
        weight = (
            product.get("weight")
            or attrs.get("weight_kg")
        )
        if not purchase or not weight:
            return None
        try:
            from icross.services.ozon_costs import OzonCostCalculator, ProductCostInput
            calc = OzonCostCalculator()
            inp = ProductCostInput(
                purchase_price_cny=float(purchase),
                weight_kg=float(weight),
                category_name=product.get("category_name") or attrs.get("category_name", ""),
                sales_model="FBP",
            )
            result = calc.calculate(inp, target_margin=float(target_margin))
            return result.recommended_price_rub
        except Exception:
            return None


# ============================================================
# Category Storage (Phase 3)
# ============================================================

class CategoryStorage:
    """Storage for Ozon category tree and attributes.

    Caches:
    - Category tree (full list of flattened categories for search)
    - Category attributes per (category_id, type_id)
    - Attribute dictionary values per attribute_id

    Flattened category schema:
    - id: unique key "cat_{description_category_id}_type_{type_id}"
    - description_category_id: Ozon category ID
    - type_id: Ozon type ID
    - category_name: category name
    - type_name: type name
    - path: full path from root (e.g. "Электроника / Смартфоны")
    - disabled: whether creation is disabled
    """

    def __init__(self):
        self._categories = JsonStore("ozon_categories.json")
        self._attributes = JsonStore("ozon_category_attributes.json")

    async def save_category_tree(self, tree_data: list[dict]) -> int:
        """Flatten and save category tree. Returns count of leaf categories."""
        flat = []
        seen_ids = set()

        def _flatten(items: list[dict], parent_path: str = ""):
            count = 0
            for item in items:
                name = item.get("category_name", "") or ""
                type_name = item.get("type_name", "") or ""
                # Leaf nodes use type_name when category_name is absent
                display_name = name or type_name
                path = f"{parent_path} / {display_name}".strip(" /") if parent_path else display_name
                children = item.get("children", []) or []
                type_id = item.get("type_id")
                description_category_id = item.get("description_category_id")
                disabled = item.get("disabled", False)

                # Save any node that has description_category_id (intermediate categories)
                if description_category_id is not None:
                    key = f"cat_{description_category_id}"
                    if key not in seen_ids:
                        seen_ids.add(key)
                        flat.append({
                            "id": key,
                            "description_category_id": description_category_id,
                            "type_id": type_id,
                            "category_name": name,
                            "type_name": type_name,
                            "path": path,
                            "disabled": disabled,
                        })

                # Save leaf nodes that have type_id
                if type_id and not children:
                    key = f"cat_{description_category_id}_type_{type_id}"
                    if key not in seen_ids:
                        seen_ids.add(key)
                        flat.append({
                            "id": key,
                            "description_category_id": description_category_id,
                            "type_id": type_id,
                            "category_name": name,
                            "type_name": type_name,
                            "path": path,
                            "disabled": disabled,
                        })
                        count += 1

                # Also save non-leaf entries that have type_id (some categories have both children and type_id)
                if type_id and children:
                    key = f"cat_{description_category_id}_type_{type_id}"
                    if key not in seen_ids:
                        seen_ids.add(key)
                        flat.append({
                            "id": key,
                            "description_category_id": description_category_id,
                            "type_id": type_id,
                            "category_name": name,
                            "type_name": type_name,
                            "path": path,
                            "disabled": disabled,
                        })

                # Recurse into children
                if children:
                    count += _flatten(children, path)
            return count

        leaf_count = _flatten(tree_data)
        self._categories._write(flat)
        return leaf_count

    async def lookup_category_name(self, description_category_id: int) -> dict | None:
        """Look up category name by description_category_id."""
        key = f"cat_{description_category_id}"
        return self._categories._find("id", key)

    async def lookup_category_path(self, description_category_id: int, type_id: int) -> dict | None:
        """Look up category by (description_category_id, type_id) for full path.

        First tries leaf node (cat_{id}_type_{type}), then leaf by type_id alone,
        then falls back to intermediate node.
        """
        key = f"cat_{description_category_id}_type_{type_id}"
        leaf = self._categories._find("id", key)
        if leaf:
            return leaf
        # Leaf nodes may be stored with None desc_id when the child has no description_category_id
        fallback_key = f"cat_None_type_{type_id}"
        leaf = self._categories._find("id", fallback_key)
        if leaf:
            return leaf
        return await self.lookup_category_name(description_category_id)

    async def get_flattened_categories(self) -> list[dict]:
        """Get all flattened categories."""
        return self._categories._get_all()

    async def search_categories(self, query: str, limit: int = 20) -> list[dict]:
        """Search categories by name or path."""
        results = []
        q = query.lower()
        for cat in self._categories._get_all():
            if q in cat.get("category_name", "").lower() or q in cat.get("path", "").lower():
                results.append(cat)
        return sorted(results, key=lambda c: c.get("path", ""))[:limit]

    async def get_category(self, description_category_id: int, type_id: int) -> dict | None:
        """Get a specific category by ID and type."""
        key = f"cat_{description_category_id}_type_{type_id}"
        return self._categories._find("id", key)

    async def get_category_by_id(self, category_id: str) -> dict | None:
        """Get a specific category by its storage ID."""
        return self._categories._find("id", category_id)

    async def save_category_attributes(
        self,
        category_id: int,
        type_id: int,
        attributes: list[dict],
    ) -> None:
        """Save attributes for a category+type combination."""
        key = f"attr_{category_id}_type_{type_id}"
        existing = self._attributes._find("id", key)
        data = {
            "id": key,
            "category_id": category_id,
            "type_id": type_id,
            "attributes": attributes,
            "cached_at": datetime.now().isoformat(),
        }
        if existing:
            self._attributes._upsert("id", key, data)
        else:
            self._attributes._insert(data)

    async def get_category_attributes(self, category_id: int, type_id: int) -> list[dict] | None:
        """Get cached attributes for a category+type."""
        key = f"attr_{category_id}_type_{type_id}"
        item = self._attributes._find("id", key)
        return item.get("attributes") if item else None

    async def save_dictionary_values(
        self,
        attribute_id: int,
        category_id: int,
        type_id: int,
        values: list[dict],
    ) -> None:
        """Cache dictionary values for an attribute in a category+type (ZH_HANS)."""
        key = f"dict_{attribute_id}_cat_{category_id}_type_{type_id}"
        existing = self._attributes._find("id", key)
        data = {
            "id": key,
            "attribute_id": attribute_id,
            "category_id": category_id,
            "type_id": type_id,
            "values": values,
            "cached_at": datetime.now().isoformat(),
        }
        if existing:
            self._attributes._upsert("id", key, data)
        else:
            self._attributes._insert(data)

    async def get_dictionary_values(self, attribute_id: int, category_id: int, type_id: int) -> list[dict] | None:
        """Get cached dictionary values for an attribute."""
        key = f"dict_{attribute_id}_cat_{category_id}_type_{type_id}"
        item = self._attributes._find("id", key)
        return item.get("values") if item else None

    async def delete_category_cache(self) -> None:
        """Clear all cached category data."""
        self._categories._write([])
        self._attributes._write([])

# ============================================================
# Listing Storage (Phase 3)
# ============================================================

class ListingStorage:
    """Storage for generated product listings."""

    def __init__(self):
        self._listings = JsonStore("listings.json")

    async def save_listing(self, shop_id: str, data: dict) -> dict:
        listing_id = str(uuid.uuid4())[:8]
        listing = {
            "id": listing_id,
            "shop_id": shop_id,
            "product_name_cn": data.get("product_name_cn", ""),
            "title": data.get("title", ""),
            "description": data.get("description", ""),
            "keywords": data.get("keywords", []),
            "category": data.get("category", ""),
            "description_category_id": data.get("description_category_id", 0),
            "type_id": data.get("type_id", 0),
            "template_id": data.get("template_id"),
            "status": "draft",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        self._listings._insert(listing)
        return listing

    async def list_listings(self, shop_id: str | None = None) -> list[dict]:
        listings = self._listings._get_all()
        if shop_id:
            listings = [l for l in listings if l.get("shop_id") == shop_id]
        return sorted(listings, key=lambda l: l.get("created_at", ""), reverse=True)

    async def get_listing(self, listing_id: str) -> dict | None:
        return self._listings._find("id", listing_id)

    async def update_listing(self, listing_id: str, **kwargs) -> dict | None:
        kwargs["updated_at"] = datetime.now().isoformat()
        return self._listings._upsert("id", listing_id, kwargs)

    async def delete_listing(self, listing_id: str) -> bool:
        return self._listings._delete("id", listing_id)


# ============================================================
# Task Storage (Phase 4 - Task Queue)
# ============================================================

class TaskStorage:
    """Storage for async task queue items.

    Data model:
    - id: unique ID
    - task_type: type of task (generate_listing, remove_bg, apply_pricing, etc.)
    - status: pending | running | completed | failed | cancelled
    - params: dict of input parameters
    - result: dict of result data
    - progress: float 0-100
    - error: error message if failed
    - priority: task priority (higher = more urgent)
    - created_at, started_at, completed_at
    """

    def __init__(self):
        self._tasks = JsonStore("tasks.json")

    async def create_task(
        self,
        task_type: str,
        params: dict[str, Any] | None = None,
        priority: int = 0,
    ) -> dict[str, Any]:
        task_id = str(uuid.uuid4())[:8]
        task = {
            "id": task_id,
            "task_type": task_type,
            "status": "pending",
            "params": params or {},
            "result": None,
            "progress": 0,
            "error": None,
            "priority": priority,
            "created_at": datetime.now().isoformat(),
            "started_at": None,
            "completed_at": None,
        }
        self._tasks._insert(task)
        return task

    async def get_task(self, task_id: str) -> dict[str, Any] | None:
        return self._tasks._find("id", task_id)

    async def update_task(self, task_id: str, **kwargs) -> dict[str, Any] | None:
        kwargs["updated_at"] = datetime.now().isoformat()
        return self._tasks._upsert("id", task_id, kwargs)

    async def list_tasks(
        self,
        task_type: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        tasks = self._tasks._get_all()
        if task_type:
            tasks = [t for t in tasks if t.get("task_type") == task_type]
        if status:
            tasks = [t for t in tasks if t.get("status") == status]
        tasks.sort(key=lambda t: (-t.get("priority", 0), t.get("created_at", "")), reverse=False)
        total = len(tasks)
        items = tasks[offset:offset + limit]
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    async def delete_task(self, task_id: str) -> bool:
        return self._tasks._delete("id", task_id)

    async def cancel_task(self, task_id: str) -> dict[str, Any] | None:
        return self._tasks._upsert("id", task_id, {"status": "cancelled", "updated_at": datetime.now().isoformat()})

    async def count_pending(self) -> int:
        return len([t for t in self._tasks._get_all() if t.get("status") == "pending"])

    async def retry_failed(self, task_id: str) -> dict[str, Any] | None:
        return self._tasks._upsert("id", task_id, {"status": "pending", "error": None, "progress": 0, "updated_at": datetime.now().isoformat()})


# ============================================================
# Workflow Storage (Phase 4 - Automation Pipeline)
# ============================================================

class WorkflowStorage:
    """Storage for automation workflow pipelines.

    Data model:
    - id: unique ID
    - name: pipeline name
    - shop_id: owning shop
    - steps: list of step definitions [{step_type, params, status, result, ...}]
    - status: pending | running | completed | failed | paused
    - current_step: index of active step
    - product_data: accumulated product data through pipeline
    - created_at, updated_at
    """

    def __init__(self):
        self._workflows = JsonStore("workflows.json")

    async def create_workflow(
        self,
        name: str,
        shop_id: str,
        steps: list[dict[str, Any]],
        product_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        wf_id = str(uuid.uuid4())[:8]
        wf = {
            "id": wf_id,
            "name": name,
            "shop_id": shop_id,
            "steps": steps,
            "status": "pending",
            "current_step": 0,
            "product_data": product_data or {},
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        self._workflows._insert(wf)
        return wf

    async def get_workflow(self, workflow_id: str) -> dict[str, Any] | None:
        return self._workflows._find("id", workflow_id)

    async def update_workflow(self, workflow_id: str, **kwargs) -> dict[str, Any] | None:
        kwargs["updated_at"] = datetime.now().isoformat()
        return self._workflows._upsert("id", workflow_id, kwargs)

    async def list_workflows(
        self,
        shop_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        wfs = self._workflows._get_all()
        if shop_id:
            wfs = [w for w in wfs if w.get("shop_id") == shop_id]
        if status:
            wfs = [w for w in wfs if w.get("status") == status]
        wfs.sort(key=lambda w: w.get("created_at", ""), reverse=True)
        total = len(wfs)
        items = wfs[offset:offset + limit]
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    async def delete_workflow(self, workflow_id: str) -> bool:
        return self._workflows._delete("id", workflow_id)


class ReportStorage:
    """JSON file storage for locally-generated reports.

    Each report record has:
      - id: UUID string
      - shop_id: str
      - type: str (products/orders/finance/stocks/analytics)
      - status: str (pending/generating/completed/failed)
      - params: dict (generation parameters)
      - file_path: str | None (path to generated .xlsx)
      - file_size: int
      - error: str | None
      - created_at: str (ISO datetime)
      - completed_at: str | None
    """

    def __init__(self):
        self._storage = JsonStore("reports.json")

    def _generate_id(self) -> str:
        import uuid
        return uuid.uuid4().hex[:12]

    async def create_report(self, shop_id: str, report_type: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        report = {
            "id": self._generate_id(),
            "shop_id": shop_id,
            "type": report_type,
            "status": "pending",
            "params": params or {},
            "file_path": None,
            "file_size": 0,
            "error": None,
            "created_at": datetime.now().isoformat(),
            "completed_at": None,
        }
        self._storage._insert(report)
        return report

    async def get_report(self, report_id: str) -> dict[str, Any] | None:
        return self._storage._find("id", report_id)

    async def update_report(self, report_id: str, **kwargs) -> dict[str, Any] | None:
        return self._storage._upsert("id", report_id, kwargs)

    async def list_reports(self, shop_id: str | None = None, report_type: str | None = None, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        items = self._storage._get_all()
        if shop_id:
            items = [r for r in items if r.get("shop_id") == shop_id]
        if report_type:
            items = [r for r in items if r.get("type") == report_type]
        items.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        total = len(items)
        return {"items": items[offset:offset + limit], "total": total, "limit": limit, "offset": offset}

    async def delete_report(self, report_id: str) -> bool:
        import os as _os
        report = await self.get_report(report_id)
        if report and report.get("file_path"):
            try:
                _os.remove(report["file_path"])
            except OSError:
                pass
        return self._storage._delete("id", report_id)


# ============================================================
# Auto-Pilot Configuration (Phase C2)
# ============================================================

class AutoPilotConfigStorage:
    """Storage for auto-pilot configuration.

    Each shop has one config dict with:
    - enabled: bool — master switch
    - cron_expr: str — schedule for auto-run
    - push_to_ozon: bool — auto-push after pricing
    - pipeline_params: dict — default params for run_full_pipeline
    - prompt_template: str — auto-pilot prompt template sent to Agent
    - prompt_generated_at: str | None — when prompt was last generated
    - created_at / updated_at: ISO timestamps
    """

    def __init__(self):
        self._store = JsonStore("auto_pilot_config.json")

    DEFAULT_PROMPT = """请帮我完成自动运营任务。

店铺ID: {shop_id}

请按以下步骤执行：
1. 先检查店铺当前状态（订单/库存/销售数据）
2. 根据数据结果执行相应操作
3. 报告执行结果"""

    async def get_config(self, shop_id: str) -> dict[str, Any]:
        """Get auto-pilot config for a shop, returning defaults if not set."""
        items = self._store._get_all()
        for c in items:
            if c.get("shop_id") == shop_id:
                # Ensure prompt_template has default if missing
                if "prompt_template" not in c:
                    c["prompt_template"] = self.DEFAULT_PROMPT
                return c
        return {
            "shop_id": shop_id,
            "enabled": False,
            "cron_expr": "0 3 * * *",
            "push_to_ozon": True,
            "pipeline_params": {
                "weight_kg": 0.5,
                "target_margin": 20.0,
            },
            "prompt_template": self.DEFAULT_PROMPT,
            "prompt_generated_at": None,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

    async def save_config(self, shop_id: str, config: dict[str, Any]) -> dict[str, Any]:
        """Save or update auto-pilot config for a shop."""
        existing = None
        items = self._store._get_all()
        for i, c in enumerate(items):
            if c.get("shop_id") == shop_id:
                existing = i
                break

        entry = {
            "shop_id": shop_id,
            "enabled": config.get("enabled", False),
            "cron_expr": config.get("cron_expr", "0 3 * * *"),
            "push_to_ozon": config.get("push_to_ozon", True),
            "pipeline_params": config.get("pipeline_params", {}),
            "prompt_template": config.get("prompt_template", self.DEFAULT_PROMPT),
            "prompt_generated_at": config.get("prompt_generated_at"),
            "updated_at": datetime.now().isoformat(),
        }

        if existing is not None:
            items[existing].update(entry)
            self._store._write(items)
            return items[existing]
        else:
            entry["created_at"] = datetime.now().isoformat()
            entries = items + [entry]
            self._store._write(entries)
            return entry

    async def list_configs(self) -> list[dict[str, Any]]:
        """List all auto-pilot configs."""
        return self._store._get_all()

    async def toggle(self, shop_id: str, enabled: bool) -> dict[str, Any]:
        """Enable or disable auto-pilot for a shop."""
        config = await self.get_config(shop_id)
        config["enabled"] = enabled
        return await self.save_config(shop_id, config)


# ============================================================
# Sourcing Session Storage (Phase 1 UX Redesign)
# ============================================================

class SourcingSessionStorage:
    """Persistent storage for product sourcing workflow progress.

    Each session tracks the incremental state of the sourcing flow:
      input → parsed → listing_generated → category_matched → draft_created

    Data model:
      - id: unique session ID
      - shop_id: str
      - status: input | parsed | listing_generated | category_matched | draft_created
      - materials: {text: str, url: str} | null
      - parse_result: {spu: dict, skus: list} | null
      - listing_result: {title: str, description: str, keywords: list} | null
      - category_result: {category_id: int, name: str} | null
      - draft_id: str | null
      - created_at: ISO datetime
      - updated_at: ISO datetime
    """

    def __init__(self):
        self._store = JsonStore("sourcing_sessions.json")

    async def create_session(self, shop_id: str) -> dict[str, Any]:
        session = {
            "id": uuid.uuid4().hex[:12],
            "shop_id": shop_id,
            "status": "input",
            "materials": None,
            "parse_result": None,
            "listing_result": None,
            "category_result": None,
            "draft_id": None,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        self._store._insert(session)
        return session

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        return self._store._find("id", session_id)

    async def update_session(self, session_id: str, **kwargs) -> dict[str, Any] | None:
        kwargs["updated_at"] = datetime.now().isoformat()
        return self._store._upsert("id", session_id, kwargs)

    async def list_sessions(self, shop_id: str, status: str | None = None) -> list[dict[str, Any]]:
        sessions = self._store._get_all()
        sessions = [s for s in sessions if s.get("shop_id") == shop_id]
        if status:
            sessions = [s for s in sessions if s.get("status") == status]
        return sorted(sessions, key=lambda s: s.get("updated_at", ""), reverse=True)

    async def delete_session(self, session_id: str) -> bool:
        return self._store._delete("id", session_id)