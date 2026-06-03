"""Enrich existing products with attributes, descriptions, and category names.

Run standalone: uv run python scripts/enrich_products.py
"""
import asyncio
import json
import sys
import os
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "vendors" / "OzonAPI-main" / "src"))

SHOP_ID = "Chencai Global"


async def enrich():
    from icross.core.storage.ozon_data import ProductStorage, CategoryStorage, _ensure_ozon_shop
    from icross.services.ozon import get_ozon_client

    product_storage = ProductStorage()

    # Step 1: Resolve category names
    print("Step 1: Resolving category names...")
    category_store = CategoryStorage()
    products = await product_storage.get_all_by_shop(SHOP_ID)
    print(f"  Products: {len(products)}")

    enriched_cat = 0
    for p in products:
        cat_id = p.get("category_id")
        if cat_id and not p.get("category_name"):
            cat_info = await category_store.lookup_category_name(cat_id)
            if cat_info:
                name = cat_info.get("category_name", "")
                if name:
                    await product_storage.update_product(p["shop_id"], p["product_id"], {"category_name": name})
                    enriched_cat += 1
    print(f"  Category names resolved: {enriched_cat}")

    # Step 2: Fetch attributes (fresh client)
    print("Step 2: Fetching attributes...")
    client = get_ozon_client()
    _ensure_ozon_shop(client, SHOP_ID)

    all_ids = [p.get("product_id") for p in products if p.get("product_id")]
    attrs_count = 0
    if all_ids:
        try:
            attrs_result = await client.get_product_attributes_list(SHOP_ID, all_ids)
            for attr_item in attrs_result.get("result", []):
                pid = attr_item.get("id")
                if pid:
                    await product_storage.update_product(SHOP_ID, pid, {"attributes": attr_item.get("attributes", [])})
                    attrs_count += 1
            print(f"  Attributes fetched: {attrs_count}")
        except Exception as e:
            print(f"  Attributes failed: {type(e).__name__}: {e}")

    # Step 3: Fetch descriptions (fresh client)
    print("Step 3: Fetching descriptions (352 products, concurrency=5)...")
    client2 = get_ozon_client()
    _ensure_ozon_shop(client2, SHOP_ID)

    sem = asyncio.Semaphore(5)
    desc_count = 0
    fail_count = 0

    async def _fetch_desc(pid):
        nonlocal desc_count, fail_count
        async with sem:
            try:
                desc_data = await client2.get_product_description(SHOP_ID, pid)
                rd = desc_data.get("result", desc_data)
                if isinstance(rd, dict) and rd.get("description"):
                    await product_storage.update_product(SHOP_ID, pid, {"description": rd["description"]})
                    desc_count += 1
            except asyncio.CancelledError:
                pass
            except Exception:
                fail_count += 1

    await asyncio.gather(*[_fetch_desc(pid) for pid in all_ids])
    print(f"  Descriptions fetched: {desc_count}, failed: {fail_count}")

    # Final summary
    products2 = await product_storage.get_all_by_shop(SHOP_ID)
    print(f"\n{'='*50}")
    print(f"ENRICH COMPLETE: {len(products2)} products")
    print(f"  With category_name: {sum(1 for p in products2 if p.get('category_name'))}")
    print(f"  With description: {sum(1 for p in products2 if p.get('description'))}")
    print(f"  With attributes: {sum(1 for p in products2 if p.get('attributes'))}")


if __name__ == "__main__":
    asyncio.run(enrich())
