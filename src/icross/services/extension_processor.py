"""Bridge between browser extension captures and the iCross processing pipeline.

The extension sends structured product data scraped from 1688 / 拼多多 / 淘宝.
This service:
  1. Receives structured capture data (title, price, images, specs, SKUs)
  2. Uses it directly (skip LLM re-extraction when data is already clean)
  3. For enrichment, falls back to ``parse_product_materials`` for messy data
  4. Wires into the existing listing → category → pricing → draft pipeline
"""

import json
import logging
from datetime import datetime
from typing import Any

from icross.core.storage.sourcing_platform import SourcingCaptureStorage

_logger = logging.getLogger(__name__)


class ExtensionCaptureProcessor:
    """Process browser extension captures through the iCross pipeline.

    Usage::

        processor = ExtensionCaptureProcessor()
        result = await processor.process_capture("cap_abc123")
        # Returns the capture record with parsed_data, draft_id, etc.
    """

    def __init__(self):
        self._storage = SourcingCaptureStorage()

    async def receive_capture(
        self,
        platform: str,
        product_url: str,
        raw_data: dict[str, Any],
        shop_id: str = "",
    ) -> dict[str, Any]:
        """Accept a new capture from the extension and store it."""
        record = self._storage.create_capture(
            platform=platform,
            product_url=product_url,
            raw_data=raw_data,
            shop_id=shop_id,
        )
        _logger.info("Extension capture %s: %s from %s", record["id"], raw_data.get("title", "?"), platform)
        return record

    async def process_capture(
        self,
        capture_id: str,
        auto_generate_listing: bool = True,
        auto_calculate_price: bool = False,
        auto_create_draft: bool = False,
    ) -> dict[str, Any]:
        """Process a capture through the pipeline.

        Steps:
          1. Validate the capture exists
          2. Build structured SPU/SKU from raw_data (direct mapping, no LLM)
          3. Optionally generate Listing, calculate price, create draft
          4. Update the capture record with results
        """
        record = self._storage.get_capture(capture_id)
        if not record:
            return {"success": False, "error": f"Capture {capture_id} not found"}

        self._storage.update_capture(capture_id, status="processing")

        try:
            raw = record.get("raw_data", {})

            # ── Step 1: Build SPU/SKU from structured extension data ──
            spu, skus = self._raw_to_spu_skus(raw, platform=record.get("platform", ""))

            parsed = {"spu": spu, "skus": skus}
            self._storage.update_capture(capture_id, parsed_data=parsed, status="parsed")

            result = {"success": True, "spu": spu, "skus": skus, "draft_id": None}

            # ── Step 2: Optionally generate listing ──
            if auto_generate_listing:
                listing = await self._generate_listing(spu, skus, record.get("platform", ""))
                result["listing"] = listing

            # ── Step 3: Optionally calculate price ──
            if auto_calculate_price:
                pricing = await self._calculate_pricing(spu, skus)
                result["pricing"] = pricing

            # ── Step 4: Optionally create draft ──
            if auto_create_draft:
                draft = await self._create_draft(spu, skus, record.get("shop_id", ""))
                if draft:
                    self._storage.update_capture(capture_id, draft_id=draft.get("id"))
                    result["draft_id"] = draft.get("id")
                    result["draft"] = draft

            self._storage.update_capture(capture_id, status="drafted" if auto_create_draft else "parsed")
            return result

        except Exception as e:
            _logger.exception("Failed to process capture %s", capture_id)
            self._storage.update_capture(capture_id, status="error", error=str(e))
            return {"success": False, "error": str(e)}

    # ── Internal helpers ──────────────────────────────────────────

    def _raw_to_spu_skus(self, raw: dict[str, Any], platform: str = "") -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Convert structured extension data to SPU/SKU format.

        Extension data is already fairly structured (title, price, images, specs),
        so this is a direct field mapping rather than LLM extraction.
        """
        spu = {
            "name": raw.get("title", ""),
            "brand": raw.get("brand", "自主品牌"),
            "category": raw.get("category", ""),
            "description": raw.get("description", ""),
            "attributes": raw.get("attributes", {}),
            "images": raw.get("images", []),
            "platform": platform,
            "source_url": raw.get("url", ""),
        }

        # Extension may provide structured SKU list directly
        raw_skus = raw.get("skus", [])
        if raw_skus and isinstance(raw_skus, list):
            skus = []
            for s in raw_skus:
                skus.append({
                    "name": s.get("name", spu["name"]),
                    "attributes": s.get("attributes", {}),
                    "price": float(s["price"]) if s.get("price") else 0.0,
                    "stock": int(s["stock"]) if s.get("stock") else 0,
                    "images": s.get("images", []),
                })
        else:
            # Fallback: create single SKU from top-level data
            skus = [{
                "name": spu["name"],
                "attributes": {},
                "price": float(raw["price"]) if raw.get("price") else 0.0,
                "stock": int(raw.get("stock", 0)),
                "images": spu["images"],
            }]

        return spu, skus

    async def _generate_listing(
        self, spu: dict[str, Any], skus: list[dict[str, Any]], platform: str
    ) -> dict[str, Any]:
        """Generate Ozon listing from SPU/SKU data using the existing pipeline.

        Delegates to the existing generate_listing tool.
        """
        try:
            from icross.agents.master.tools_product import generate_listing

            # Build keyword hints from the product attributes
            attrs = spu.get("attributes", {})
            keyword_hints = [spu.get("name", "")]
            if spu.get("category"):
                keyword_hints.append(spu["category"])
            keyword_hints.extend(v for v in attrs.values() if isinstance(v, str))

            result_str = generate_listing.invoke({
                "product_name_cn": spu.get("name", ""),
                "product_description_cn": spu.get("description", ""),
                "category": spu.get("category", ""),
                "keywords": keyword_hints[:10],
            })
            # The tool returns a JSON string
            if isinstance(result_str, str):
                result_str = result_str.strip()
                if result_str.startswith("{"):
                    return json.loads(result_str)
            return {"raw": str(result_str)}
        except Exception as e:
            _logger.warning("Listing generation failed (non-blocking): %s", e)
            return {"error": str(e)}

    async def _calculate_pricing(
        self, spu: dict[str, Any], skus: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Calculate pricing advice from cost data."""
        try:
            from icross.agents.master.tools_product import calculate_product_price

            purchase_price = 0.0
            if skus:
                purchase_price = skus[0].get("price", 0.0)

            if purchase_price <= 0:
                return {"error": "No purchase price available"}

            result_str = calculate_product_price.invoke({
                "purchase_price_cny": purchase_price,
            })
            if isinstance(result_str, str):
                return {"advice": result_str}
            return {"advice": str(result_str)}
        except Exception as e:
            _logger.warning("Price calculation failed (non-blocking): %s", e)
            return {"error": str(e)}

    async def _create_draft(
        self, spu: dict[str, Any], skus: list[dict[str, Any]], shop_id: str
    ) -> dict[str, Any] | None:
        """Create a product draft in iCross from the parsed data."""
        if not shop_id:
            _logger.info("No shop_id, skipping draft creation")
            return None
        try:
            from icross.core.storage.ozon_data import DraftStorage

            store = DraftStorage()
            draft = await store.create_draft(
                shop_id=shop_id,
                draft_type="listing",
                title=spu.get("name", ""),
                description=spu.get("description", ""),
                source_url=spu.get("source_url", ""),
            )
            return draft
        except Exception as e:
            _logger.warning("Draft creation failed (non-blocking): %s", e)
            return None
