"""REST API endpoints for product management."""

import json

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from pydantic import BaseModel

from icross.core.storage.ozon_data import ProductStorage, CategoryStorage

router = APIRouter()
product_storage = ProductStorage()


CURRENCY_SYMBOLS = {"CNY": "¥", "RUB": "₽", "USD": "$", "EUR": "€"}


def _normalize_product(product: dict) -> dict:
    """Ensure currency_code is at top level (fallback from attrs)."""
    if product.get("currency_code") is None:
        attrs = product.get("attrs") or {}
        product["currency_code"] = attrs.get("currency_code", "CNY")
    return product


def _format_price(price: float | str | None, currency_code: str = "CNY") -> str | None:
    """Format a price with its currency symbol."""
    if price is None:
        return None
    symbol = CURRENCY_SYMBOLS.get(currency_code, currency_code)
    return f"{symbol} {float(price):,.2f}"


class PriceUpdate(BaseModel):
    new_price: float
    old_price: float | None = None


class ProductUpdate(BaseModel):
    name: str | None = None
    price: float | None = None
    stock: int | None = None
    description: str | None = None
    cost_price: float | None = None
    weight: int | None = None
    width: int | None = None
    height: int | None = None
    depth: int | None = None
    barcode: str | None = None


class RichContentUpdate(BaseModel):
    """Request body for saving rich content (attribute 11254)."""
    rich_content: list | dict


class ProductImagesUpdate(BaseModel):
    """Request body for replacing product images."""
    images: list[str]
    primary_image: str | None = None


class ProductPushRequest(BaseModel):
    """Fields to push to Ozon. Only provided fields will be updated."""
    name: str | None = None
    description: str | None = None
    price: float | None = None
    old_price: float | None = None
    stock: int | None = None
    attributes: list[dict] | None = None
    weight: int | None = None
    width: int | None = None
    height: int | None = None
    depth: int | None = None
    barcode: str | None = None


@router.get("/products")
async def list_products(
    shop_id: str = Query(default=...),
    limit: int = Query(default=100),
    offset: int = Query(default=0),
    visibility: str | None = None,
):
    """List products for a shop."""
    result = await product_storage.list_products(shop_id, limit, offset, visibility)
    for item in result.get("items", []):
        _normalize_product(item)
    return result


@router.get("/products/{product_id}")
async def get_product(product_id: str):
    """Get product details by internal id (UUID string)."""
    row = await product_storage.get_product_by_id(product_id)
    if not row:
        raise HTTPException(status_code=404, detail="Product not found")
    _normalize_product(row)
    return {"product": row}


@router.patch("/products/{product_id}/price")
async def update_product_price(product_id: str, update: PriceUpdate):
    """Update product price."""
    product = await product_storage.get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    await product_storage.update_product_price(
        internal_id=product_id,
        new_price=update.new_price,
        old_price=update.old_price,
    )
    return {"success": True, "product_id": product_id, "new_price": update.new_price}


@router.patch("/products/{product_id}")
async def update_product(product_id: str, update: ProductUpdate):
    """Update product fields (name, price, stock, description, cost_price)."""
    product = await product_storage.get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    await product_storage.update_product(product_id, update.model_dump(exclude_none=True))
    return {"success": True, "product_id": product_id}


@router.post("/products/{product_id}/push")
async def push_product_to_ozon(product_id: str, update: ProductPushRequest):
    """Push product changes to Ozon API.

    Validates what changed and calls the appropriate Ozon API(s):
    - name/description → POST /v1/product/import (full product update)
    - price/old_price → POST /v1/product/import/prices
    - stock → POST /v2/products/stocks
    - attributes → POST /v1/product/attributes/update

    Also saves changes locally after successful push.
    """
    product = await product_storage.get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    from icross.services.ozon import get_ozon_client
    client = get_ozon_client()
    from icross.core.storage.ozon_data import _ensure_ozon_shop
    _ensure_ozon_shop(client, product["shop_id"])

    fields = update.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    calls: list[dict] = []
    ozon_product_id = product.get("product_id")
    offer_id = product.get("offer_id")
    currency_code = product.get("currency_code") or (product.get("attrs") or {}).get("currency_code", "RUB")

    # 1. Full import needed when name, description, weight or dimensions changes
    needs_full_import = any(k in fields for k in ("name", "description", "weight", "width", "height", "depth"))
    if needs_full_import:
        name = fields.get("name") or product.get("name", "")
        description = fields.get("description") or product.get("description", "")
        weight = fields.get("weight") or product.get("weight", 500)
        depth = fields.get("depth") or product.get("depth", 10)
        width = fields.get("width") or product.get("width", 100)
        height = fields.get("height") or product.get("height", 100)

        # Build attributes list — preserve existing (excluding description, which
        # is already passed via the `description` parameter to create_product).
        # When attributes are also being separately updated (line 219), skip
        # sending old attributes here to avoid racing with the attribute update.
        if "attributes" in fields:
            attrs = None
        else:
            attrs = list(product.get("attributes") or [])
            attrs = [a for a in attrs if a.get("id") != 4196]

        try:
            result = await client.create_product(
                shop_id=product["shop_id"],
                name=name,
                offer_id=offer_id,
                price=fields.get("price") or product.get("price", 0) or 0,
                vat="VAT_20",
                description_category_id=product.get("category_id", 0),
                type_id=product.get("type_id"),
                description=description,
                images=product.get("images") or [],
                depth=depth,
                width=width,
                height=height,
                weight=weight,
                attributes=attrs,
                currency_code=currency_code,
            )
            calls.append({"api": "import_product", "task_id": result.get("task_id"), "status": "ok"})
        except Exception as e:
            calls.append({"api": "import_product", "error": str(e), "status": "error"})

    # 2. Price update
    if "price" in fields:
        try:
            old_price_val = fields.get("old_price") or product.get("old_price") or None
            if old_price_val is not None:
                try:
                    old_price_val = float(old_price_val)
                except (TypeError, ValueError):
                    old_price_val = None
            if old_price_val is not None and old_price_val <= float(fields["price"]):
                old_price_val = None
            result = await client.update_price(
                shop_id=product["shop_id"],
                offer_id=offer_id,
                product_id=ozon_product_id,
                price=fields["price"],
                old_price=old_price_val,
                currency=currency_code,
            )
            calls.append({"api": "update_price", "updated": result.get("updated"), "status": "ok"})
        except Exception as e:
            calls.append({"api": "update_price", "error": str(e), "status": "error"})

    # 3. Stock update (needs warehouse_id)
    if "stock" in fields:
        try:
            warehouses = await client.get_warehouses(product["shop_id"])
            wh_list = (warehouses.get("result") or []) if isinstance(warehouses, dict) else []
            wh_id = None
            if wh_list:
                wh_id = wh_list[0].get("warehouse_id") or wh_list[0].get("id")
            if wh_id:
                result = await client.update_stock(
                    shop_id=product["shop_id"],
                    offer_id=offer_id,
                    product_id=ozon_product_id,
                    stock=fields["stock"],
                    warehouse_id=wh_id,
                )
                calls.append({"api": "update_stock", "status": "ok"})
            else:
                calls.append({"api": "update_stock", "status": "skipped", "reason": "No warehouse found"})
        except Exception as e:
            calls.append({"api": "update_stock", "error": str(e), "status": "error"})

    # 4. Attributes update
    if "attributes" in fields:
        try:
            result = await client.update_product_attributes(
                shop_id=product["shop_id"],
                offer_id=offer_id,
                attributes=fields["attributes"],
            )
            calls.append({"api": "update_attributes", "task_id": result.get("task_id"), "status": "ok"})
        except Exception as e:
            calls.append({"api": "update_attributes", "error": str(e), "status": "error"})

    # Save changes locally regardless of Ozon push results
    local_updates = dict(fields)
    # Capture old price before update_product mutates the in-memory product
    old_price_val = None
    if "price" in fields:
        old_price_val = product.get("price")

    # Track push errors on the product for list indicator
    any_errors = any(c.get("status") == "error" for c in calls)
    if any_errors:
        local_updates["push_error"] = "; ".join(
            f"{c['api']}: {c['error']}" for c in calls if c.get("status") == "error"
        )
    elif "push_error" in product:
        local_updates["push_error"] = None  # clear on success

    await product_storage.update_product(product_id, local_updates)

    # Record price history if price changed
    if "price" in fields:
        await product_storage.update_product_price(
            internal_id=product_id,
            new_price=fields["price"],
            old_price=old_price_val,
        )

    return {
        "success": True,
        "product_id": product_id,
        "calls": calls,
        "local_saved": True,
        "has_errors": any_errors,
    }

@router.get("/products/{product_id}/price-history")
async def get_product_price_history(product_id: str):
    """Get price history for a product."""
    product = await product_storage.get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    history = await product_storage.get_price_history(product_id)
    return {"product_id": product_id, "history": history}


@router.get("/products/{product_id}/stock-history")
async def get_product_stock_history(product_id: str):
    """Get stock history for a product."""
    product = await product_storage.get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    history = await product_storage.get_stock_history(product_id)
    return {"product_id": product_id, "history": history}


@router.delete("/products/{product_id}")
async def delete_product(product_id: str):
    """Delete a product."""
    product = await product_storage.get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    await product_storage.delete_product(product_id)
    return {"success": True, "product_id": product_id}


@router.post("/products/sync")
async def sync_products(shop_id: str = Query(default=...), enrich: bool = Query(default=True)):
    """Sync products from Ozon API.

    Args:
        shop_id: Shop identifier.
        enrich: If True, also fetch attributes, descriptions, and category names.
    """
    result = await product_storage.sync_from_ozon(shop_id, enrich=enrich)
    return {"success": True, "shop_id": shop_id, **result}


@router.post("/products/enrich")
async def enrich_products(
    shop_id: str = Query(default=...),
    language: str = Query(default="DEFAULT"),
):
    """Enrich existing products with attributes, descriptions, and category names.

    Fetches missing data (attributes, descriptions, category names) for
    already-synced products without re-syncing the full product list.

    Returns immediately; processing happens in background.
    """
    import asyncio
    import logging

    logger = logging.getLogger(__name__)
    logger.info("enrich_products called shop_id=%s language=%s (background)", shop_id, language)

    # Start background task
    asyncio.create_task(_enrich_products(shop_id, language))

    return {"success": True, "background": True, "message": "Enrichment started in background"}


async def _enrich_products(shop_id: str, language: str):
    from icross.services.ozon import get_ozon_client
    from icross.core.storage.ozon_data import CategoryStorage, _ensure_ozon_shop

    client = get_ozon_client()
    _ensure_ozon_shop(client, shop_id)

    products = await product_storage.get_all_by_shop(shop_id)
    all_product_ids = [p.get("product_id") for p in products if p.get("product_id")]

    if not all_product_ids:
        return {"success": True, "enriched": 0, "message": "No products found"}

    enriched = 0

    # 1. Resolve category names (in specified language)
    category_store = CategoryStorage()
    if language.upper() != "DEFAULT":
        # Re-fetch category tree in target language for fresh resolution
        try:
            tree = await client.get_category_tree(shop_id, language=language)
            await category_store.save_category_tree(tree.get("categories", []))
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Category tree refresh failed: %s", e)

    for p in products:
        cat_id = p.get("category_id")
        type_id = p.get("type_id")
        if cat_id:
            cat_info = await category_store.lookup_category_path(cat_id, type_id)
            if cat_info:
                name = cat_info.get("category_name", "")
                path = cat_info.get("path", name or "")
                update = {"category_name": name or cat_info.get("type_name", "")}
                if path != p.get("category_path"):
                    update["category_path"] = path
                if update.get("category_name") != p.get("category_name") or "category_path" in update:
                    await product_storage.update_product_by_ozon_ids(p["shop_id"], p["product_id"], update)
                    enriched += 1
        elif not p.get("category_name") and cat_id:
            cat_info = await category_store.lookup_category_path(cat_id, p.get("type_id"))
            if cat_info:
                name = cat_info.get("category_name", "")
                path = cat_info.get("path", name or "")
                update = {"category_name": name or cat_info.get("type_name", "")}
                if path != name:
                    update["category_path"] = path
                if update:
                    await product_storage.update_product_by_ozon_ids(p["shop_id"], p["product_id"], update)
                    enriched += 1

    # 2. Fetch attributes (batch)
    try:
        attrs_result = await client.get_product_attributes_list(shop_id, all_product_ids)
        for attr_item in attrs_result.get("result", []):
            pid = attr_item.get("id")
            if pid:
                await product_storage.update_product_by_ozon_ids(shop_id, pid, {
                    "attributes": attr_item.get("attributes", []),
                    "weight": attr_item.get("weight"),
                    "width": attr_item.get("width"),
                    "height": attr_item.get("height"),
                    "depth": attr_item.get("depth"),
                    "dimension_unit": attr_item.get("dimension_unit"),
                    "weight_unit": attr_item.get("weight_unit"),
                })
    except BaseException as e:
        import logging
        logging.getLogger(__name__).warning("Attributes enrich failed: %s", e)

    # 3. Fetch descriptions (sequential - OzonAPI SessionManager doesn't support concurrency)
    import logging as _logging
    _logger = _logging.getLogger(__name__)
    for pid in all_product_ids:
        try:
            desc_data = await client.get_product_description(shop_id, pid)
            rd = desc_data.get("result", desc_data)
            if isinstance(rd, dict) and rd.get("description"):
                await product_storage.update_product_by_ozon_ids(shop_id, pid, {"description": rd["description"]})
        except BaseException:
            pass

    return {"success": True, "enriched": enriched, "total": len(all_product_ids)}


@router.post("/products/{product_id}/sync-attributes")
async def sync_product_attributes(product_id: str):
    """Fetch and save attributes + description for a single product from Ozon."""
    product = await product_storage.get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    shop_id = product.get("shop_id", "")
    ozon_product_id = product.get("product_id")
    if not ozon_product_id:
        raise HTTPException(status_code=400, detail="Product has no Ozon product_id")

    from icross.services.ozon import get_ozon_client
    from icross.core.storage.ozon_data import _ensure_ozon_shop
    client = get_ozon_client()
    _ensure_ozon_shop(client, shop_id)

    attrs_synced = 0
    dims_synced = False
    # Fetch attributes
    try:
        attrs_result = await client.get_product_attributes_list(shop_id, [ozon_product_id])
        for item in attrs_result.get("result", []):
            attrs = item.get("attributes", [])
            update = {}
            if attrs:
                update["attributes"] = attrs
                attrs_synced = len(attrs)
            # Save dimensions from the same response
            for dim in ("weight", "width", "height", "depth", "dimension_unit", "weight_unit"):
                val = item.get(dim)
                if val is not None:
                    update[dim] = val
            if update:
                await product_storage.update_product(product_id, update)
                dims_synced = True
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Attribute sync failed for %s: %s", product_id, e)

    # Fetch description
    desc_synced = False
    try:
        desc_data = await client.get_product_description(shop_id, ozon_product_id)
        rd = desc_data.get("result", desc_data)
        if isinstance(rd, dict) and rd.get("description"):
            await product_storage.update_product(product_id, {"description": rd["description"]})
            desc_synced = True
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Description sync failed for %s: %s", product_id, e)

    # Re-read product with updated data
    updated = await product_storage.get_product_by_id(product_id)

    return {
        "success": True,
        "product_id": product_id,
        "attributes_synced": attrs_synced,
        "description_synced": desc_synced,
        "product": _normalize_product(updated) if updated else None,
    }


@router.get("/products/{product_id}/editable-attributes")
async def get_editable_attributes(product_id: str):
    """Get all category attribute definitions with options and current product values for editing."""
    product = await product_storage.get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    shop_id = product.get("shop_id", "")
    category_id = product.get("category_id")
    type_id = product.get("type_id")
    if not category_id or not type_id:
        raise HTTPException(status_code=400, detail="Product has no category or type defined")

    from icross.services.ozon import get_ozon_client
    from icross.core.storage.ozon_data import _ensure_ozon_shop
    category_store = CategoryStorage()
    client = get_ozon_client()
    _ensure_ozon_shop(client, shop_id)

    # 1. Get attribute definitions (cache → Ozon)
    attr_defs = await category_store.get_category_attributes(category_id, type_id)
    if not attr_defs:
        try:
            data = await client.get_category_attributes(shop_id, category_id, type_id, language="ZH_HANS")
            attr_defs = data.get("attributes", [])
            await category_store.save_category_attributes(category_id, type_id, attr_defs)
        except BaseException as e:
            import logging
            logging.getLogger(__name__).warning("Failed to fetch category attributes: %s", e)
            return {"product_id": product_id, "category_id": category_id, "type_id": type_id, "attributes": [], "error": str(e)}

    # 2. Build current values lookup: attribute_id -> [{dictionary_value_id, value}]
    raw_attributes: list[dict] = product.get("attributes") or []
    current_values: dict[int, list[dict]] = {}
    for attr in raw_attributes:
        aid = attr.get("id")
        if aid:
            current_values[aid] = attr.get("values", [])

    # 3. Build result — for dictionary attrs, fetch all possible values
    result = []
    for attr_def in attr_defs:
        aid = attr_def.get("id")
        if not aid:
            continue

        entry = {
            "id": aid,
            "name": attr_def.get("name", f"attr #{aid}"),
            "type": attr_def.get("type", "text"),
            "required": attr_def.get("required", False),
            "is_collection": attr_def.get("is_collection", False),
            "max_value_count": attr_def.get("max_value_count", 1),
            "current_values": current_values.get(aid, []),
            "options": [],
        }

        # Fetch dictionary values if this is a dictionary attribute
        if attr_def.get("dictionary_id"):
            cached_vals = await category_store.get_dictionary_values(aid, category_id, type_id)
            if cached_vals:
                entry["options"] = cached_vals
            else:
                try:
                    vals_result = await client.get_category_attribute_values(
                        shop_id, category_id, type_id, aid, language="ZH_HANS"
                    )
                    vals = vals_result.get("values", [])
                    if vals:
                        await category_store.save_dictionary_values(aid, category_id, type_id, vals)
                        entry["options"] = vals
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning("Failed to fetch dict values for attr %s: %s", aid, e)

        result.append(entry)

    return {
        "product_id": product_id,
        "category_id": category_id,
        "type_id": type_id,
        "attributes": result,
    }


@router.get("/products/shop/{shop_id}/ozon/{ozon_product_id}")
async def get_product_by_ozon_id(shop_id: str, ozon_product_id: int):
    """Get product by shop_id and Ozon product_id."""
    row = await product_storage.get_product(shop_id, ozon_product_id)
    if not row:
        raise HTTPException(status_code=404, detail="Product not found")
    _normalize_product(row)
    return {"product": row}


@router.get("/products/{product_id}/resolved-attributes")
async def get_resolved_attributes(product_id: str):
    """Resolve product attribute IDs to Chinese names and values.

    Fetches attribute definitions (with ZH_HANS language) for the product's
    category+type, then maps each raw attribute ID to its Chinese name and
    dictionary value IDs to Chinese text.
    """
    product = await product_storage.get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    raw_attributes: list[dict] = product.get("attributes") or []
    if not raw_attributes:
        return {"product_id": product_id, "attributes": []}

    shop_id = product.get("shop_id", "")
    category_id = product.get("category_id")
    type_id = product.get("type_id")
    if not category_id or not type_id:
        return {"product_id": product_id, "attributes": []}

    from icross.core.storage.ozon_data import CategoryStorage
    category_store = CategoryStorage()

    # 1. Get attribute definitions (cached) — fetch with ZH_HANS if not cached
    attr_defs = await category_store.get_category_attributes(category_id, type_id)
    if not attr_defs:
        # Fetch from Ozon API with Chinese language
        try:
            from icross.services.ozon import get_ozon_client
            client = get_ozon_client()
            from icross.core.storage.ozon_data import _ensure_ozon_shop
            _ensure_ozon_shop(client, shop_id)
            data = await client.get_category_attributes(shop_id, category_id, type_id, language="ZH_HANS")
            attr_defs = data.get("attributes", [])
            await category_store.save_category_attributes(category_id, type_id, attr_defs)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Failed to fetch attribute definitions: %s", e)

    # Build attribute_name_map: attribute_id -> name (Chinese)
    attr_name_map: dict[int, str] = {}
    attr_dict_map: dict[int, int] = {}  # attribute_id -> dictionary_id
    if attr_defs:
        for a in attr_defs:
            aid = a.get("id")
            if aid:
                attr_name_map[aid] = a.get("name", f"attr #{aid}")
                if a.get("dictionary_id"):
                    attr_dict_map[aid] = a["dictionary_id"]

    # 2. For attributes with dictionaries, fetch dictionary values (ZH_HANS)
    # value_id -> value_zh mapping per attribute
    dict_value_maps: dict[int, dict[int, str]] = {}  # attribute_id -> {value_id: value_zh}
    for attr in raw_attributes:
        aid = attr.get("id")
        if aid in attr_dict_map:
            cached_vals = await category_store.get_dictionary_values(aid, category_id, type_id)
            if cached_vals:
                dict_value_maps[aid] = {v.get("id"): (v.get("value") or "") for v in cached_vals}
            else:
                # Fetch from Ozon
                try:
                    from icross.services.ozon import get_ozon_client
                    client = get_ozon_client()
                    result = await client.get_category_attribute_values(
                        shop_id, category_id, type_id, aid, language="ZH_HANS"
                    )
                    vals = result.get("values", [])
                    if vals:
                        await category_store.save_dictionary_values(aid, category_id, type_id, vals)
                        dict_value_maps[aid] = {v.get("id"): (v.get("value") or "") for v in vals}
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning("Failed to fetch dictionary values for attr %s: %s", aid, e)

    # 3. Resolve each product attribute
    resolved = []
    for attr in raw_attributes:
        aid = attr.get("id")
        values = attr.get("values", [])
        resolved_values = []
        for v in values:
            dv_id = v.get("dictionary_value_id")
            raw_val = v.get("value") or ""
            if dv_id and aid in dict_value_maps and dv_id in dict_value_maps[aid]:
                resolved_values.append({"value": dict_value_maps[aid][dv_id]})
            else:
                resolved_values.append({"value": raw_val})

        resolved.append({
            "id": aid,
            "name": attr_name_map.get(aid, f"attr #{aid}"),
            "values": resolved_values,
        })

    return {"product_id": product_id, "attributes": resolved}


@router.post("/products/{product_id}/rich-content")
async def save_rich_content(product_id: str, body: RichContentUpdate):
    """Save rich content JSON (attribute 11254) for a product.

    Accepts either a JSON object (the rich content structure) or a list
    of image URLs (which gets wrapped into raShowcase/roll format).
    """
    product = await product_storage.get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    raw = body.get("rich_content")

    # If given a list of image URLs, wrap into raShowcase/roll format
    if isinstance(raw, list):
        raw = {
            "content": [
                {
                    "widgetName": "raShowcase",
                    "type": "roll",
                    "blocks": [
                        {
                            "imgLink": "",
                            "img": {
                                "src": url,
                                "srcMobile": url,
                                "alt": "",
                                "position": "width_full",
                                "positionMobile": "width_full",
                            }
                        }
                        for url in raw
                    ]
                }
            ]
        }

    # Serialize to JSON string
    rich_json = json.dumps(raw, ensure_ascii=False)

    # Update or append attribute 11254
    attrs = list(product.get("attributes") or [])
    found = False
    for a in attrs:
        if a.get("id") == 11254:
            a["values"] = [{"value": rich_json}]
            found = True
            break
    if not found:
        attrs.append({"id": 11254, "values": [{"value": rich_json}]})

    await product_storage.update_product(product_id, {"attributes": attrs})
    return {"success": True, "product_id": product_id}


@router.put("/products/{product_id}/images")
async def replace_product_images(product_id: str, body: ProductImagesUpdate):
    """Replace all images for a product.

    Calls Ozon API to update product pictures, then saves locally.
    """
    product = await product_storage.get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    shop_id = product.get("shop_id", "")
    ozon_product_id = product.get("product_id")
    if not ozon_product_id:
        raise HTTPException(status_code=400, detail="Product has no Ozon product_id")

    # Update on Ozon
    from icross.services.ozon import get_ozon_client
    client = get_ozon_client()
    ozon_result = await client.import_product_images(
        shop_id=shop_id,
        product_id=ozon_product_id,
        images=body.images,
    )

    # Save images locally
    updates = {"images": body.images}
    if body.primary_image:
        updates["primary_image"] = body.primary_image
    elif body.images:
        updates["primary_image"] = body.images[0]
    await product_storage.update_product(product_id, updates)

    return {"success": True, "product_id": product_id, "ozon_result": ozon_result}


@router.post("/products/{product_id}/images/upload")
async def upload_product_image(product_id: str, file: UploadFile = File(...)):
    """Upload an image file and push it to Ozon CDN.

    Saves the file locally (served at /uploads/... for dev use) and
    best-effort uploads to Ozon CDN, returning the CDN URL.
    """
    from pathlib import Path

    product = await product_storage.get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        raise HTTPException(status_code=400, detail=f"Unsupported image format: {ext}")

    content = await file.read()
    _uploads_dir = Path(__file__).parent.parent.parent.parent.parent / "uploads"
    _uploads_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(file.filename).name
    dest = _uploads_dir / safe_name
    counter = 1
    while dest.exists():
        dest = _uploads_dir / f"{dest.stem}_{counter}{dest.suffix}"
        counter += 1
    dest.write_bytes(content)

    local_url = f"/uploads/{dest.name}"
    result = {"success": True, "local_url": local_url, "filename": dest.name, "size": len(content)}

    # Best-effort: upload to Ozon CDN (requires a publicly reachable URL)
    shop_id = product.get("shop_id", "")
    if shop_id:
        from urllib.parse import urljoin
        full_url = urljoin("http://localhost:8000", local_url)
        try:
            from icross.services.ozon import get_ozon_client
            client = get_ozon_client()
            cdn = await client.upload_image(shop_id, full_url)
            if cdn.get("url"):
                result["ozon_url"] = cdn["url"]
                result["message"] = "已上传到 Ozon CDN"
            else:
                result["message"] = "Ozon CDN 上传失败（本地 URL 可能不可达），可使用本地 URL"
        except Exception as e:
            result["message"] = f"Ozon CDN 上传失败: {e}，可使用本地 URL"

    return result
