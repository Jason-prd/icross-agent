"""Ozon API client wrapper for multi-account support."""

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from ozonapi import SellerAPI, SellerAPIConfig

# Load .env
_env_file = Path(__file__).parent.parent.parent.parent.parent / ".env"
if _env_file.exists():
    load_dotenv(_env_file)


def _dt_str(val: Any) -> str:
    """Convert a datetime or date value to ISO string, empty string if None."""
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, str):
        return val
    return str(val)


@dataclass
class OzonShopConfig:
    """Configuration for an Ozon seller shop."""
    shop_id: str
    client_id: str = ""
    api_key: str = ""
    token: str = ""

    @classmethod
    def from_env(cls, shop_id: str) -> "OzonShopConfig":
        """Load shop config from environment variables."""
        return cls(
            shop_id=shop_id,
            client_id=os.getenv(f"OZON_{shop_id.upper()}_CLIENT_ID", ""),
            api_key=os.getenv(f"OZON_{shop_id.upper()}_API_KEY", ""),
            token=os.getenv(f"OZON_{shop_id.upper()}_TOKEN", ""),
        )


class OzonClient:
    """Async Ozon API client with multi-shop support.

    Usage:
        client = OzonClient()
        client.add_shop("shop_001", client_id="xxx", api_key="yyy")

        # List products
        result = await client.list_products("shop_001")

        # Update price
        await client.update_price("shop_001", offer_id="SKU123", price=1500)
    """

    def __init__(self):
        self._shops: dict[str, SellerAPI] = {}

    def add_shop(self, shop_id: str, client_id: str | None = None, api_key: str | None = None, token: str | None = None) -> None:
        """Add a shop configuration.

        Args:
            shop_id: Unique shop identifier.
            client_id: Ozon client ID (or set via OZON_SHOPID_CLIENT_ID env var).
            api_key: Ozon API key (or set via OZON_SHOPID_API_KEY env var).
            token: OAuth token (alternative to client_id+api_key).
        """
        # Check if already added with valid credentials
        if shop_id in self._shops:
            # If explicit credentials provided and current ones are empty, re-initialize
            has_explicit = client_id or api_key or token
            if has_explicit:
                # Remove old instance and re-initialize with new credentials
                del self._shops[shop_id]
            else:
                return  # No new credentials, keep existing
        else:
            pass  # New shop, continue to add

        # Load from env if not provided
        if not client_id:
            client_id_env = os.getenv(f"OZON_{shop_id.upper()}_CLIENT_ID")
            if not client_id_env:
                client_id_env = os.getenv("OZON_CLIENT_ID")
            if client_id_env:
                client_id = client_id_env
        if not api_key:
            api_key_env = os.getenv(f"OZON_{shop_id.upper()}_API_KEY")
            if not api_key_env:
                api_key_env = os.getenv("OZON_API_KEY")
            if api_key_env:
                api_key = api_key_env
        if not token:
            token_env = os.getenv(f"OZON_{shop_id.upper()}_TOKEN")
            if token_env:
                token = token_env

        config = SellerAPIConfig(
            client_id=client_id,
            api_key=api_key,
            token=token,
            log_level="WARNING",
        )
        self._shops[shop_id] = SellerAPI(config=config)

    async def list_products(
        self,
        shop_id: str,
        limit: int = 100,
        last_id: str = "",
        offer_ids: list[str] | None = None,
        product_ids: list[int] | None = None,
        visibility: str = "ALL",
    ) -> dict[str, Any]:
        """List products for a shop.

        Args:
            shop_id: Shop identifier.
            limit: Results per page (max 1000).
            last_id: Pagination cursor.
            offer_ids: Filter by offer IDs.
            product_ids: Filter by product IDs.
            visibility: Filter by visibility (ALL, VISIBLE, INVISIBLE).

        Returns:
            Dict with items, total, last_id.
        """
        from ozonapi.seller.schemas.products import ProductListRequest, ProductListFilter
        from ozonapi.seller.common.enumerations.products import Visibility

        api = self._get_api(shop_id)
        vis = Visibility[visibility.upper()]

        filter_kwargs = {"visibility": vis}
        if offer_ids:
            filter_kwargs["offer_id"] = offer_ids
        if product_ids:
            filter_kwargs["product_id"] = product_ids

        request = ProductListRequest(
            filter=ProductListFilter(**filter_kwargs),
            limit=limit,
            last_id=last_id,
        )
        result = await api.product_list(request)
        # Handle both vendor and installed versions (result vs result.result)
        items = result.items if hasattr(result, 'items') else result.result.items
        total = result.total if hasattr(result, 'total') else result.result.total
        last_id = result.last_id if hasattr(result, 'last_id') else result.result.last_id
        return {
            "items": [self._product_item_to_dict(item) for item in items],
            "total": total,
            "last_id": last_id,
        }

    async def get_product_info(self, shop_id: str, product_id: int) -> dict[str, Any]:
        """Get product details by ID.

        Args:
            shop_id: Shop identifier.
            product_id: Ozon product ID.

        Returns:
            Product info dict.
        """
        from ozonapi.seller.schemas.products import ProductInfoListRequest

        api = self._get_api(shop_id)
        request = ProductInfoListRequest(product_id=[product_id])
        result = await api.product_info_list(request)
        items = result.items if hasattr(result, 'items') else []
        if items:
            return self._product_info_to_dict(items[0])
        return {}

    async def get_product_info_list(self, shop_id: str, product_ids: list[int] | None = None, offer_ids: list[str] | None = None) -> dict[str, Any]:
        """Get product details by IDs.

        Args:
            shop_id: Shop identifier.
            product_ids: List of Ozon product IDs (max 1000).
            offer_ids: List of offer IDs (alternative to product_ids).

        Returns:
            Dict with items and total.
        """
        from ozonapi.seller.schemas.products import ProductInfoListRequest

        api = self._get_api(shop_id)
        request_kwargs = {}
        if product_ids:
            request_kwargs["product_id"] = product_ids[:1000]
        elif offer_ids:
            request_kwargs["offer_id"] = offer_ids[:1000]
        else:
            return {"items": [], "total": 0}

        request = ProductInfoListRequest(**request_kwargs)
        result = await api.product_info_list(request)
        items = result.items if hasattr(result, 'items') else result.result.items if hasattr(result, 'result') else []
        return {
            "items": [self._product_info_to_dict(item) for item in items],
            "total": len(items),
        }

    async def get_product_attributes_list(
        self,
        shop_id: str,
        product_ids: list[int],
    ) -> dict[str, Any]:
        """Get product attributes/characteristics (/v4/product/info/attributes).

        Args:
            shop_id: Shop identifier.
            product_ids: List of Ozon product IDs (max 1000).

        Returns:
            Dict with result list containing attributes per product.
        """
        from ozonapi.seller.schemas.products import (
            ProductInfoAttributesRequest,
            ProductInfoAttributesFilter,
        )

        api = self._get_api(shop_id)
        request = ProductInfoAttributesRequest(
            filter=ProductInfoAttributesFilter(product_id=product_ids[:1000]),
            limit=1000,
        )
        response = await api.product_info_attributes(request)
        return json.loads(response.model_dump_json())

    async def get_product_description(self, shop_id: str, product_id: int) -> dict[str, Any]:
        """Get product description (/v1/product/info/description).

        Args:
            shop_id: Shop identifier.
            product_id: Ozon product ID.

        Returns:
            Dict with description, name, offer_id.
        """
        from ozonapi.seller.schemas.products import ProductInfoDescriptionRequest

        api = self._get_api(shop_id)
        request = ProductInfoDescriptionRequest(product_id=product_id)
        response = await api.product_info_description(request)
        return json.loads(response.model_dump_json())

    async def update_price(
        self,
        shop_id: str,
        offer_id: str = "",
        product_id: int = 0,
        price: float = 0,
        old_price: float = 0,
        vat: str = "VAT_20",
        currency: str = "RUB",
    ) -> dict[str, Any]:
        """Update product price.

        Args:
            shop_id: Shop identifier.
            offer_id: Offer ID (sku).
            product_id: Ozon product ID (alternative to offer_id).
            price: New price.
            old_price: Original price (for discount display).
            vat: VAT rate (VAT_0, VAT_10, VAT_20).
            currency: Currency code (RUB, USD, etc.).

        Returns:
            Result dict.
        """
        from ozonapi.seller.schemas.prices_and_stocks import (
            ProductImportPricesRequest,
            ProductImportPricesItem,
        )
        from ozonapi.seller.common.enumerations.prices import VAT as VATEnum
        from ozonapi.seller.common.enumerations.localization import CurrencyCode

        api = self._get_api(shop_id)

        vat_key = vat.replace("VAT_", "PERCENT_") if vat.startswith("VAT_") else vat
        vat_enum = getattr(VATEnum, vat_key, VATEnum.PERCENT_20)
        curr_enum = getattr(CurrencyCode, currency.upper(), CurrencyCode.RUB)

        item = ProductImportPricesItem(
            offer_id=offer_id,
            product_id=product_id or None,
            price=str(price),
            old_price=str(old_price) if old_price else None,
            vat=vat_enum,
            currency_code=curr_enum,
        )
        request = ProductImportPricesRequest(prices=[item])
        result = await api.product_import_prices(request)
        r = result.result[0] if result.result else {}
        return {"status": "ok", "updated": r.updated if hasattr(r, 'updated') else False}

    async def update_stock(
        self,
        shop_id: str,
        offer_id: str = "",
        product_id: int = 0,
        stock: int = 0,
        warehouse_id: int = 0,
    ) -> dict[str, Any]:
        """Update product stock via /v2/products/stocks.

        Args:
            shop_id: Shop identifier.
            offer_id: Offer ID (sku).
            product_id: Ozon product ID (alternative to offer_id).
            stock: Stock count.
            warehouse_id: Warehouse ID (required for FBS).

        Returns:
            Result dict.
        """
        from ozonapi.seller.schemas.prices_and_stocks import (
            ProductsStocksRequest,
            ProductsStocksItem,
        )

        api = self._get_api(shop_id)

        item = ProductsStocksItem(
            offer_id=offer_id,
            product_id=product_id or None,
            stock=stock,
            warehouse_id=warehouse_id or None,
        )
        request = ProductsStocksRequest(stocks=[item])
        result = await api.products_stocks(request)
        return {"status": "ok", "result": result.model_dump()}

    async def get_analytics_stocks(
        self,
        shop_id: str,
        skus: list[int],
        warehouse_ids: list[int] | None = None,
        cluster_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """Get inventory analytics.

        Args:
            shop_id: Shop identifier.
            skus: List of offer IDs (1-100).
            warehouse_ids: Filter by warehouse.
            cluster_ids: Filter by cluster.

        Returns:
            Analytics data with ads, days_without_sales, turnover_grade, etc.
        """
        from ozonapi.seller.schemas.beta import AnalyticsStocksRequest

        api = self._get_api(shop_id)
        request = AnalyticsStocksRequest(
            skus=skus,
            warehouse_ids=warehouse_ids,
            cluster_ids=cluster_ids,
        )
        result = await api.analytics_stocks(request)
        items = [self._stock_analytics_to_dict(item) for item in result.items]
        return {
            "items": items,
            "total": len(items),
        }

    async def get_order_list(
        self,
        shop_id: str,
        limit: int = 100,
        offset: int = 0,
        since: str = "",
        status: str = "",
    ) -> dict[str, Any]:
        """List FBO orders (fulfilled by Ozon).

        Args:
            shop_id: Shop identifier.
            limit: Results per page.
            offset: Pagination offset.
            since: Filter since date (ISO format string or empty).
            status: Filter by status.

        Returns:
            List of orders with financial data.
        """
        from datetime import datetime, timedelta
        from ozonapi.seller.schemas.fbo import PostingFBOListRequest, PostingFilter, PostingFilterWith

        api = self._get_api(shop_id)
        # Parse since string (ISO format with possible Z suffix)
        if since:
            since_clean = since.replace('Z', '+00:00').replace('.000', '')
            since_dt = datetime.fromisoformat(since_clean)
        else:
            since_dt = datetime.now() - timedelta(days=30)

        req_filter = PostingFilter(
            since=since_dt,
            to=datetime.now(),
            status=status or None,
        )
        request = PostingFBOListRequest(
            limit=limit,
            offset=offset,
            filter=req_filter,
            with_=PostingFilterWith(analytics_data=True, financial_data=True, legal_info=True),
        )
        response = await api.posting_fbo_list(request)
        items = response.result or []
        item_count = len(items)
        # Ozon API does not return total count; estimate pagination from returned count
        total = offset + item_count + (1 if item_count >= limit else 0)
        return {
            "items": [self._posting_to_dict(item) for item in items],
            "total": total,
        }

    async def get_seller_info(self, shop_id: str) -> dict[str, Any]:
        """Get seller account info.

        Args:
            shop_id: Shop identifier.

        Returns:
            Seller info with ratings.
        """
        api = self._get_api(shop_id)
        result = await api.seller_info()
        return {
            "name": result.company.name if result.company else "Unknown",
            "legal_name": result.company.legal_name if result.company else "",
            "client_id": result.company.inn if result.company else "",
            "is_premium": result.subscription.is_premium if result.subscription else False,
            "ratings": [
                {
                    "name": r.name,
                    "current_value": r.current_value.formatted if r.current_value else None,
                    "status": r.status,
                }
                for r in (result.ratings or [])
            ],
        }

    async def create_product(
        self,
        shop_id: str,
        name: str,
        offer_id: str,
        price: float,
        vat: str = "VAT_20",
        description_category_id: int = 0,
        type_id: int | None = None,
        description: str = "",
        images: list[str] | None = None,
        primary_image: str = "",
        old_price: float | None = None,
        depth: int = 10,
        width: int = 100,
        height: int = 100,
        dimension_unit: str = "mm",
        weight: int = 500,
        weight_unit: str = "g",
        barcode: str = "",
        currency_code: str = "RUB",
        attributes: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Create a product on Ozon.

        Uses the v3/product/import API. Creates an import task — use
        get_product_import_status to check completion.

        Args:
            shop_id: Shop identifier.
            name: Product name (max 500 chars).
            offer_id: SKU / seller's product identifier (max 50 chars).
            price: Current selling price in RUB.
            vat: VAT rate (VAT_0, VAT_10, VAT_20).
            description_category_id: Category ID from description_category_tree().
            type_id: Type ID from description_category_tree().
            description: HTML description (passed as attribute id=4196).
            images: List of public image URLs (max 30).
            primary_image: Primary image URL.
            old_price: Original price for discount display.
            depth, width, height: Package dimensions.
            dimension_unit: "mm", "cm", or "in".
            weight: Package weight.
            weight_unit: "g", "kg", or "lb".
            barcode: Product barcode.
            currency_code: Currency (RUB, CNY, etc).
            attributes: List of additional attribute dicts like
                [{"id": 4196, "values": [{"value": "..."}]}].

        Returns:
            Dict with task_id for status polling.
        """
        from ozonapi.seller.schemas.products.v3__product_import import (
            ProductImportRequest,
            ProductImportItem,
            ProductImportRequestItemPromotion,
        )
        from ozonapi.seller.common.enumerations.prices import VAT as VATEnum
        from ozonapi.seller.common.enumerations.localization import CurrencyCode as CurrencyCodeEnum
        from ozonapi.seller.common.enumerations.products import ServiceType
        from ozonapi.seller.schemas.products.base import (
            ProductAttribute,
            ProductAttributeValue,
        )

        api = self._get_api(shop_id)

        # Build attributes list — include description if provided
        attrs_list: list[ProductAttribute] = []
        if description:
            attrs_list.append(ProductAttribute(
                complex_id=0,
                id=4196,  # description attribute
                values=[ProductAttributeValue(value=description)],
            ))
        if attributes:
            for a in attributes:
                vals = [ProductAttributeValue(**v) for v in a.get("values", [])]
                attrs_list.append(ProductAttribute(
                    complex_id=a.get("complex_id", 0),
                    id=a["id"],
                    values=vals,
                ))

        vat_key = vat.replace("VAT_", "PERCENT_") if vat.startswith("VAT_") else vat
        vat_enum = getattr(VATEnum, vat_key, VATEnum.PERCENT_20)
        curr_enum = getattr(CurrencyCodeEnum, currency_code.upper(), CurrencyCodeEnum.RUB)

        item = ProductImportItem(
            name=name[:500],
            offer_id=offer_id[:50],
            price=str(price),
            old_price=str(old_price) if old_price else None,
            vat=vat_enum,
            currency_code=curr_enum,
            new_description_category_id=description_category_id,
            description_category_id=description_category_id,
            type_id=type_id,
            images=images or [],
            primary_image=primary_image or None,
            barcode=barcode or None,
            depth=depth,
            width=width,
            height=height,
            dimension_unit=dimension_unit,
            weight=weight,
            weight_unit=weight_unit,
            attributes=attrs_list or None,
            service_type=ServiceType.IS_CODE_SERVICE,
            promotions=[ProductImportRequestItemPromotion()],
        )

        request = ProductImportRequest(items=[item])
        result = await api.product_import(request)
        return {"task_id": result.result.task_id, "status": "importing", "shop_id": shop_id}

    async def update_product_attributes(
        self,
        shop_id: str,
        offer_id: str,
        attributes: list[dict],
    ) -> dict[str, Any]:
        """Update product attributes via /v1/product/attributes/update.

        Args:
            shop_id: Shop identifier.
            offer_id: Offer ID (sku) of the product.
            attributes: List of attribute dicts like
                [{"id": 85, "complex_id": 0, "values": [{"dictionary_value_id": 123, "value": "..."}]}]

        Returns:
            Dict with task_id.
        """
        from ozonapi.seller.schemas.products import (
            ProductAttributesUpdateRequest,
            ProductAttributesUpdateItem,
            ProductAttributesUpdateItemAttribute,
            ProductAttributesUpdateItemAttributeValue,
        )

        api = self._get_api(shop_id)

        attr_list = []
        for a in attributes:
            vals = [
                ProductAttributesUpdateItemAttributeValue(
                    dictionary_value_id=v.get("dictionary_value_id", 0),
                    value=v.get("value", ""),
                )
                for v in (a.get("values") or [])
            ]
            attr_list.append(ProductAttributesUpdateItemAttribute(
                complex_id=a.get("complex_id", 0),
                id=a["id"],
                values=vals,
            ))

        request = ProductAttributesUpdateRequest(
            items=[ProductAttributesUpdateItem(
                offer_id=offer_id,
                attributes=attr_list,
            )]
        )
        result = await api.product_attributes_update(request)
        return {"task_id": result.task_id, "status": "importing"}

    async def get_product_import_status(self, shop_id: str, task_id: int) -> dict[str, Any]:
        """Check the status of a product import task.

        Args:
            shop_id: Shop identifier.
            task_id: Task ID from create_product().

        Returns:
            Dict with task status and items details.
        """
        from ozonapi.seller.schemas.products import ProductImportInfoRequest, ProductImportInfoResponse

        api = self._get_api(shop_id)
        request = ProductImportInfoRequest(task_id=task_id)
        result = await api.product_import_info(request)
        items = []
        if result.result and hasattr(result.result, 'items'):
            for item in result.result.items:
                items.append({
                    "product_id": getattr(item, 'product_id', None),
                    "offer_id": getattr(item, 'offer_id', None),
                    "status": getattr(item, 'status', None),
                    "errors": [
                        {"code": e.code, "message": e.message}
                        for e in (getattr(item, 'errors', []) or [])
                    ] if hasattr(item, 'errors') else [],
                })
        return {
            "task_id": task_id,
            "status": result.result.status if result.result else "unknown",
            "total": result.result.total if result.result else 0,
            "items": items,
        }

    async def get_category_tree(
        self,
        shop_id: str,
        language: str = "DEFAULT",
    ) -> dict[str, Any]:
        """Get Ozon product category tree.

        Args:
            shop_id: Shop identifier.
            language: Response language (DEFAULT, RU, EN).

        Returns:
            Category tree as nested list.
        """
        from ozonapi.seller.schemas.attributes_and_characteristics import DescriptionCategoryTreeRequest
        from ozonapi.seller.common.enumerations.localization import Language

        api = self._get_api(shop_id)
        lang = getattr(Language, language.upper(), Language.DEFAULT)
        request = DescriptionCategoryTreeRequest(language=lang)
        result = await api.description_category_tree(request)
        return {"categories": [self._category_tree_to_dict(item) for item in result.result]}

    async def get_category_attributes(
        self,
        shop_id: str,
        category_id: int,
        type_id: int,
        language: str = "DEFAULT",
    ) -> dict[str, Any]:
        """Get attributes for a specific category and type.

        Args:
            shop_id: Shop identifier.
            category_id: Description category ID from tree.
            type_id: Type ID from tree.
            language: Response language.

        Returns:
            List of attribute definitions.
        """
        from ozonapi.seller.schemas.attributes_and_characteristics import DescriptionCategoryAttributeRequest
        from ozonapi.seller.common.enumerations.localization import Language

        api = self._get_api(shop_id)
        lang = getattr(Language, language.upper(), Language.DEFAULT)
        request = DescriptionCategoryAttributeRequest(
            description_category_id=category_id,
            type_id=type_id,
            language=lang,
        )
        result = await api.description_category_attribute(request)
        return {
            "category_id": category_id,
            "type_id": type_id,
            "attributes": [self._category_attribute_to_dict(item) for item in result.result],
        }

    async def get_category_attribute_values(
        self,
        shop_id: str,
        category_id: int,
        type_id: int,
        attribute_id: int,
        last_value_id: int | None = None,
        limit: int = 2000,
        language: str = "DEFAULT",
    ) -> dict[str, Any]:
        """Get dictionary values for a category attribute.

        Args:
            shop_id: Shop identifier.
            category_id: Description category ID.
            type_id: Type ID.
            attribute_id: Attribute ID.
            last_value_id: Pagination cursor.
            limit: Max results (max 2000).
            language: Response language.

        Returns:
            List of attribute values with has_next pagination.
        """
        from ozonapi.seller.schemas.attributes_and_characteristics import DescriptionCategoryAttributeValuesRequest
        from ozonapi.seller.common.enumerations.localization import Language

        api = self._get_api(shop_id)
        lang = getattr(Language, language.upper(), Language.DEFAULT)
        request = DescriptionCategoryAttributeValuesRequest(
            description_category_id=category_id,
            type_id=type_id,
            attribute_id=attribute_id,
            language=lang,
            last_value_id=last_value_id,
            limit=limit,
        )
        result = await api.description_category_attribute_values(request)
        return {
            "attribute_id": attribute_id,
            "values": [self._attribute_value_to_dict(item) for item in result.result],
            "has_next": getattr(result, "has_next", False),
        }

    async def search_category_attribute_values(
        self,
        shop_id: str,
        category_id: int,
        type_id: int,
        attribute_id: int,
        value: str,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Search dictionary values for a category attribute.

        Args:
            shop_id: Shop identifier.
            category_id: Description category ID.
            type_id: Type ID.
            attribute_id: Attribute ID.
            value: Search query (min 2 chars).
            limit: Max results (max 100).

        Returns:
            Matching attribute values.
        """
        from ozonapi.seller.schemas.attributes_and_characteristics import DescriptionCategoryAttributeValuesSearchRequest

        api = self._get_api(shop_id)
        request = DescriptionCategoryAttributeValuesSearchRequest(
            description_category_id=category_id,
            type_id=type_id,
            attribute_id=attribute_id,
            value=value,
            limit=limit,
        )
        result = await api.description_category_attribute_values_search(request)
        return {
            "attribute_id": attribute_id,
            "values": [self._attribute_value_to_dict(item) for item in result.result],
        }

    async def get_warehouses(self, shop_id: str) -> dict[str, Any]:
        """List warehouses using v2 API.

        Args:
            shop_id: Shop identifier.

        Returns:
            List of warehouses.
        """
        api = self._get_api(shop_id)
        headers = {
            "Client-Id": api.client_id,
            "Api-Key": api._api_key,
            "Content-Type": "application/json",
        }
        base_url = "https://api-seller.ozon.ru"

        all_warehouses: list[dict[str, Any]] = []
        cursor: str | None = None

        async with httpx.AsyncClient() as client:
            while True:
                payload: dict[str, Any] = {"limit": 200}
                if cursor:
                    payload["cursor"] = cursor

                response = await client.post(
                    f"{base_url}/v2/warehouse/list",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

                warehouses = data.get("warehouses", []) or []
                for wh in warehouses:
                    all_warehouses.append(self._warehouse_v2_to_dict(wh))

                has_next = data.get("has_next", False)
                cursor = data.get("cursor")
                if not has_next or not cursor:
                    break

        return {"items": all_warehouses}

    @staticmethod
    def _enum_val(val: Any) -> str:
        """Extract string value from an enum or return the value itself."""
        if val is None:
            return ""
        if hasattr(val, "value"):
            return val.value
        return str(val)

    def _get_api(self, shop_id: str) -> SellerAPI:
        """Get or create API instance for shop."""
        if shop_id not in self._shops:
            self.add_shop(shop_id)
        return self._shops[shop_id]

    async def _direct_post(self, shop_id: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make a direct POST request to the Ozon API.

        Args:
            shop_id: Shop identifier.
            path: API path like "/v2/warehouse/list".
            payload: Request body dict.

        Returns:
            Parsed JSON response dict, or {"_error": msg} on failure.
        """
        api = self._get_api(shop_id)
        headers = {
            "Client-Id": api.client_id,
            "Api-Key": api._api_key,
            "Content-Type": "application/json",
        }
        base_url = "https://api-seller.ozon.ru"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{base_url}{path}",
                    headers=headers,
                    json=payload or {},
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            return {"_error": f"Ozon API HTTP {e.response.status_code}: {e.response.text[:200]}"}
        except httpx.ConnectError as e:
            return {"_error": f"Cannot reach Ozon API: {type(e).__name__}"}
        except httpx.TimeoutException as e:
            return {"_error": f"Ozon API timeout: {type(e).__name__}"}
        except Exception as e:
            return {"_error": f"Ozon API error: {type(e).__name__}: {str(e)[:200]}"}

    async def upload_image(self, shop_id: str, image_url: str, name: str = "") -> dict[str, Any]:
        """Upload an image to Ozon CDN from a public URL.

        Uses POST /v2/product/images/upload. Ozon downloads the image from the
        provided URL and hosts it on their own CDN, returning a new CDN URL.

        Args:
            shop_id: Shop identifier.
            image_url: Public URL of the source image.
            name: Optional image file name.

        Returns:
            Dict with ``id`` (image_id) and ``url`` (Ozon CDN URL) on success,
            or ``{"_error": msg}`` on failure.
        """
        payload: dict[str, Any] = {"image_url": image_url}
        if name:
            payload["name"] = name
        result = await self._direct_post(shop_id, "/v2/product/images/upload", payload)
        return result

    async def import_product_images(
        self,
        shop_id: str,
        product_id: int,
        images: list[str] | None = None,
        color_image: str | None = None,
        images360: list[str] | None = None,
    ) -> dict[str, Any]:
        """Replace all images for a product via /v1/product/pictures/import.

        Args:
            shop_id: Shop identifier.
            product_id: Ozon product ID.
            images: Public image URLs (max 30, first is primary).
            color_image: Marketing color image URL.
            images360: 360-degree image URLs (max 70).

        Returns:
            Dict with result containing picture states.
        """
        from ozonapi.seller.schemas.products import ProductPicturesImportRequest

        api = self._get_api(shop_id)
        request = ProductPicturesImportRequest(
            product_id=product_id,
            images=images or [],
            color_image=color_image,
            images360=images360 or [],
        )
        response = await api.product_pictures_import(request)
        return json.loads(response.model_dump_json())

    async def get_product_images(
        self,
        shop_id: str,
        product_ids: list[int],
    ) -> dict[str, Any]:
        """Get product image info via /v2/product/pictures/info.

        Args:
            shop_id: Shop identifier.
            product_ids: List of Ozon product IDs (max 1000).

        Returns:
            Dict with items containing primary_photo, photo, color_photo, photo_360 per product.
        """
        from ozonapi.seller.schemas.products import ProductPicturesInfoRequest

        api = self._get_api(shop_id)
        request = ProductPicturesInfoRequest(product_id=product_ids)
        response = await api.product_pictures_info(request)
        return json.loads(response.model_dump_json())

    async def _direct_get(self, shop_id: str, path: str) -> dict[str, Any]:
        """Make a direct GET request to the Ozon API.

        Args:
            shop_id: Shop identifier.
            path: API path like "/v1/actions".

        Returns:
            Parsed JSON response dict, or {"_error": msg} on failure.
        """
        api = self._get_api(shop_id)
        headers = {
            "Client-Id": api.client_id,
            "Api-Key": api._api_key,
            "Content-Type": "application/json",
        }
        base_url = "https://api-seller.ozon.ru"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{base_url}{path}",
                    headers=headers,
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            return {"_error": f"Ozon API HTTP {e.response.status_code}: {e.response.text[:200]}"}
        except httpx.ConnectError as e:
            return {"_error": f"Cannot reach Ozon API: {type(e).__name__}"}
        except httpx.TimeoutException as e:
            return {"_error": f"Ozon API timeout: {type(e).__name__}"}
        except Exception as e:
            return {"_error": f"Ozon API error: {type(e).__name__}: {str(e)[:200]}"}

    async def _direct_performance_post(self, shop_id: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make a direct POST request to the Ozon Performance API (ads).

        Uses a separate API key (Performance API) and base URL.

        Args:
            shop_id: Shop identifier.
            path: API path like "/api/client/campaign/list".
            payload: Request body dict.

        Returns:
            Parsed JSON response dict.
        """
        perf_key = os.getenv(f"OZON_{shop_id.upper()}_PERF_KEY", "")
        if not perf_key:
            perf_key = os.getenv("OZON_PERF_KEY", "")
        if not perf_key:
            # Try the token field as fallback
            api = self._get_api(shop_id)
            token = getattr(api, 'token', '') or os.getenv(f"OZON_{shop_id.upper()}_TOKEN", "")
            perf_key = token
        if not perf_key:
            raise ValueError(
                f"Performance API key not configured for shop '{shop_id}'. "
                f"Set OZON_{shop_id.upper()}_PERF_KEY or OZON_PERF_KEY env var."
            )

        headers = {
            "Authorization": f"Bearer {perf_key}",
            "Content-Type": "application/json",
        }
        base_url = "https://api-performance.ozon.ru"
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{base_url}{path}",
                headers=headers,
                json=payload or {},
            )
            response.raise_for_status()
            return response.json()

    # ============================================================
    # FBS Order Management
    # ============================================================

    async def list_fbs_postings(
        self,
        shop_id: str,
        limit: int = 100,
        offset: int = 0,
        since: str = "",
        to: str = "",
        status: str = "",
    ) -> dict[str, Any]:
        """List FBS postings (orders).

        Args:
            shop_id: Shop identifier.
            limit: Results per page (max 1000).
            offset: Pagination offset.
            since: Filter start date (ISO format).
            to: Filter end date (ISO format).
            status: Filter by status.

        Returns:
            Dict with items and total.
        """
        from datetime import datetime, timedelta
        from ozonapi.seller.schemas.fbs import PostingFBSListRequest, PostingFBSListFilter, PostingFBSFilterWith

        api = self._get_api(shop_id)
        if since:
            since_dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
        else:
            since_dt = datetime.now() - timedelta(days=30)
        if to:
            to_dt = datetime.fromisoformat(to.replace('Z', '+00:00'))
        else:
            to_dt = datetime.now()

        req_filter = PostingFBSListFilter(
            since=since_dt,
            to=to_dt,
            status=status or None,
        )
        request = PostingFBSListRequest(
            limit=min(limit, 1000),
            offset=offset,
            filter=req_filter,
            with_=PostingFBSFilterWith(analytics_data=True, financial_data=True, legal_info=True),
        )
        response = await api.posting_fbs_list(request)
        items = response.result.postings or [] if response.result else []
        has_next = response.result.has_next if response.result else False
        total = offset + len(items) + (1 if has_next else 0)
        return {
            "items": [self._fbs_posting_to_dict(item) for item in items],
            "total": total,
            "has_next": has_next,
        }

    async def get_fbs_posting(self, shop_id: str, posting_number: str) -> dict[str, Any]:
        """Get FBS posting details.

        Args:
            shop_id: Shop identifier.
            posting_number: Posting number (e.g., "123456-7890-0001").

        Returns:
            Posting details dict.
        """
        from ozonapi.seller.schemas.fbs import PostingFBSGetRequest
        from ozonapi.seller.schemas.fbs.v3__posting_fbs_get import PostingFBSGetRequestWith

        api = self._get_api(shop_id)
        request = PostingFBSGetRequest(
            posting_number=posting_number,
            with_=PostingFBSGetRequestWith(financial_data=True, analytics_data=True, barcodes=True),
        )
        response = await api.posting_fbs_get(request)
        item = response.result
        return self._posting_full_to_dict(item) if item else {}

    async def fbs_ship_postings(self, shop_id: str, posting_ids: list[str]) -> dict[str, Any]:
        """Ship FBS postings (confirm packing).

        After calling this, posting status changes to ``awaiting_deliver``.

        Args:
            shop_id: Shop identifier.
            posting_ids: List of posting IDs to ship.

        Returns:
            Dict with shipment result.
        """
        data = await self._direct_post(shop_id, "/v4/posting/fbs/ship", {
            "posting_ids": posting_ids,
        })
        return data.get("result", data)

    async def fbs_awaiting_delivery(self, shop_id: str, posting_ids: list[str]) -> dict[str, Any]:
        """Mark FBS postings as 'awaiting delivery' (handed to carrier).

        Args:
            shop_id: Shop identifier.
            posting_ids: List of posting IDs.

        Returns:
            Result dict.
        """
        from ozonapi.seller.schemas.fbs import PostingFBSAwaitingDeliveryRequest

        api = self._get_api(shop_id)
        request = PostingFBSAwaitingDeliveryRequest(posting_number=posting_ids)
        response = await api.posting_fbs_awaiting_delivery(request)
        return {"result": response.result}

    async def fbs_create_act(self, shop_id: str) -> dict[str, Any]:
        """Create an act of acceptance for FBS shipments.

        Returns:
            Dict with act_id and status.
        """
        data = await self._direct_post(shop_id, "/v2/posting/fbs/act/create", {})
        return data.get("result", data)

    async def fbs_get_act_status(self, shop_id: str, act_id: int) -> dict[str, Any]:
        """Check the status of an act of acceptance.

        Args:
            shop_id: Shop identifier.
            act_id: Act ID from fbs_create_act.

        Returns:
            Dict with act status.
        """
        data = await self._direct_post(shop_id, "/v2/posting/fbs/act/check-status", {
            "id": act_id,
        })
        return data.get("result", data)

    async def get_package_label(self, shop_id: str, posting_numbers: list[str]) -> dict[str, Any]:
        """Generate PDF labels for FBS postings (max 20, must be in ``awaiting_deliver`` status).

        Args:
            shop_id: Shop identifier.
            posting_numbers: List of posting numbers (max 20).

        Returns:
            Dict with ``file_content`` (base64 string), ``file_name``, ``content_type``.
        """
        from ozonapi.seller.schemas.fbs import PostingFBSPackageLabelRequest

        api = self._get_api(shop_id)
        request = PostingFBSPackageLabelRequest(posting_number=posting_numbers)
        response = await api.posting_fbs_package_label(request)
        return {
            "file_content": response.file_content,
            "file_name": response.file_name,
            "content_type": response.content_type,
        }

    # ============================================================
    # Advertising Management
    # ============================================================

    async def list_ad_campaigns(
        self,
        shop_id: str,
        page: int = 1,
        page_size: int = 50,
        state: str = "",
    ) -> dict[str, Any]:
        """List advertising campaigns via Performance API.

        Args:
            shop_id: Shop identifier.
            page: Page number.
            page_size: Items per page.
            state: Filter by state (campaign_state enum).

        Returns:
            List of campaigns.
        """
        payload: dict[str, Any] = {
            "page": page,
            "page_size": min(page_size, 1000),
        }
        if state:
            payload["state"] = state
        data = await self._direct_performance_post(shop_id, "/api/client/campaign/list", payload)
        return data.get("result", data)

    async def get_ad_campaign(self, shop_id: str, campaign_id: int) -> dict[str, Any]:
        """Get advertising campaign details via Performance API.

        Args:
            shop_id: Shop identifier.
            campaign_id: Campaign ID.

        Returns:
            Campaign details.
        """
        data = await self._direct_performance_post(shop_id, "/api/client/campaign", {
            "id": campaign_id,
        })
        return data.get("result", data)

    async def create_ad_campaign(
        self,
        shop_id: str,
        title: str,
        daily_budget: float,
        start_date: str,
        end_date: str = "",
    ) -> dict[str, Any]:
        """Create an advertising campaign via Performance API.

        Args:
            shop_id: Shop identifier.
            title: Campaign title.
            daily_budget: Daily budget in RUB.
            start_date: Campaign start date (ISO format).
            end_date: Campaign end date (ISO format, optional).

        Returns:
            Created campaign info.
        """
        payload: dict[str, Any] = {
            "title": title,
            "daily_budget": daily_budget,
            "start_date": start_date,
        }
        if end_date:
            payload["end_date"] = end_date
        data = await self._direct_performance_post(shop_id, "/api/client/campaign", payload)
        return data.get("result", data)

    async def update_ad_campaign(
        self,
        shop_id: str,
        campaign_id: int,
        daily_budget: float | None = None,
        title: str | None = None,
        state: str | None = None,
    ) -> dict[str, Any]:
        """Update an advertising campaign via Performance API.

        Args:
            shop_id: Shop identifier.
            campaign_id: Campaign ID.
            daily_budget: New daily budget.
            title: New title.
            state: Campaign state (e.g. "ON", "OFF", "ACTIVE", "PAUSED").

        Returns:
            Updated campaign info.
        """
        payload: dict[str, Any] = {"id": campaign_id}
        if daily_budget is not None:
            payload["daily_budget"] = daily_budget
        if title is not None:
            payload["title"] = title
        if state is not None:
            payload["state"] = state
        data = await self._direct_performance_post(shop_id, "/api/client/campaign/update", payload)
        return data.get("result", data)

    async def get_ad_campaign_stats(
        self,
        shop_id: str,
        campaign_ids: list[int],
        date_from: str,
        date_to: str = "",
    ) -> dict[str, Any]:
        """Get advertising campaign statistics via Performance API.

        Args:
            shop_id: Shop identifier.
            campaign_ids: List of campaign IDs.
            date_from: Start date (ISO format).
            date_to: End date (ISO format).

        Returns:
            Campaign statistics.
        """
        payload: dict[str, Any] = {
            "campaign_ids": campaign_ids,
            "date_from": date_from,
        }
        if date_to:
            payload["date_to"] = date_to
        data = await self._direct_performance_post(shop_id, "/api/client/campaign/statistics", payload)
        return data.get("result", data)

    async def get_ad_campaign_products(
        self,
        shop_id: str,
        campaign_id: int,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """Get products in an advertising campaign via Performance API.

        Args:
            shop_id: Shop identifier.
            campaign_id: Campaign ID.
            page: Page number.
            page_size: Items per page.

        Returns:
            List of campaign products.
        """
        data = await self._direct_performance_post(shop_id, "/api/client/campaign/products", {
            "id": campaign_id,
            "page": page,
            "page_size": min(page_size, 1000),
        })
        return data.get("result", data)

    async def get_ad_campaigns_stats(self, shop_id: str, campaign_ids: list[int], date_from: str, date_to: str = "") -> dict[str, Any]:
        """Get advertising campaign statistics (alternative method).

        Args:
            shop_id: Shop identifier.
            campaign_ids: List of campaign IDs.
            date_from: Start date (ISO format).
            date_to: End date (ISO format).

        Returns:
            Campaign statistics.
        """
        payload: dict[str, Any] = {
            "campaign_ids": campaign_ids,
            "date_from": date_from,
        }
        if date_to:
            payload["date_to"] = date_to
        data = await self._direct_performance_post(shop_id, "/api/client/campaign/statistics", payload)
        return data.get("result", data)

    # ============================================================
    # Returns Management (Phase 6)
    # ============================================================

    async def list_returns(
        self,
        shop_id: str,
        limit: int = 50,
        last_id: int = 0,
        return_schema: str = "",
        status: str = "",
    ) -> dict[str, Any]:
        """List FBO/FBS returns.

        Uses /v1/returns/list (FBO and FBS returns).

        Args:
            shop_id: Shop identifier.
            limit: Items per page (max 500).
            last_id: Pagination cursor (return_id of last item).
            return_schema: "FBO" or "FBS" or "" (all).
            status: Filter by visual status name.

        Returns:
            Dict with returns and has_next.
        """
        payload: dict[str, Any] = {
            "filter": {},
            "limit": min(limit, 500),
            "last_id": last_id,
        }
        if return_schema:
            payload["filter"]["return_schema"] = return_schema
        if status:
            payload["filter"]["visual_status_name"] = status
        return await self._direct_post(shop_id, "/v1/returns/list", payload)

    async def list_fbs_returns(
        self,
        shop_id: str,
        limit: int = 50,
        last_id: int = 0,
    ) -> dict[str, Any]:
        """List FBS/rFBS returns via the unified /v1/returns/list with FBS filter.

        Args:
            shop_id: Shop identifier.
            limit: Items per page (max 500).
            last_id: Pagination cursor.

        Returns:
            Dict with returns and has_next.
        """
        return await self.list_returns(shop_id, limit=limit, last_id=last_id, return_schema="FBS")

    async def list_rfbs_returns(
        self,
        shop_id: str,
        limit: int = 50,
        last_id: str = "",
    ) -> dict[str, Any]:
        """List rFBS return requests via dedicated endpoint.

        Uses POST /v2/returns/rfbs/list for rFBS-specific returns.
        These are return requests initiated by buyers for rFBS shipments.

        Args:
            shop_id: Shop identifier.
            limit: Items per page (max 200).
            last_id: Cursor from previous page response.

        Returns:
            Dict with rFBS return requests.
        """
        payload: dict[str, Any] = {"limit": min(limit, 200)}
        if last_id:
            payload["last_id"] = last_id
        return await self._direct_post(shop_id, "/v2/returns/rfbs/list", payload)

    async def get_return_info(self, shop_id: str, return_id: int) -> dict[str, Any]:
        """Get rFBS return request details.

        Args:
            shop_id: Shop identifier.
            return_id: Return ID.

        Returns:
            Return details with available_actions.
        """
        return await self._direct_post(shop_id, "/v2/returns/rfbs/get", {
            "return_id": return_id,
        })

    async def accept_return(self, shop_id: str, return_id: int, return_method_description: str = "") -> dict[str, Any]:
        """Approve an rFBS return request (agree to receive product for verification).

        Args:
            shop_id: Shop identifier.
            return_id: Return ID.
            return_method_description: Method of product return.

        Returns:
            Result dict.
        """
        payload: dict[str, Any] = {"return_id": return_id}
        if return_method_description:
            payload["return_method_description"] = return_method_description
        return await self._direct_post(shop_id, "/v2/returns/rfbs/verify", payload)

    async def reject_return(self, shop_id: str, return_id: int, rejection_reason_id: int = 0, comment: str = "") -> dict[str, Any]:
        """Reject an rFBS return request with reason.

        Args:
            shop_id: Shop identifier.
            return_id: Return ID.
            rejection_reason_id: Reason ID from get_return_info rejection_reason list.
            comment: Rejection comment (required if reason mandates it).

        Returns:
            Result dict.
        """
        payload: dict[str, Any] = {"return_id": return_id}
        if rejection_reason_id:
            payload["rejection_reason_id"] = rejection_reason_id
        if comment:
            payload["comment"] = comment
        return await self._direct_post(shop_id, "/v2/returns/rfbs/reject", payload)

    async def refund_return(self, shop_id: str, return_id: int, return_for_back_way: float = 0) -> dict[str, Any]:
        """Refund the customer for an rFBS return.

        Args:
            shop_id: Shop identifier.
            return_id: Return ID.
            return_for_back_way: Refund amount for shipping the product.

        Returns:
            Result dict.
        """
        payload: dict[str, Any] = {"return_id": return_id}
        if return_for_back_way:
            payload["return_for_back_way"] = return_for_back_way
        return await self._direct_post(shop_id, "/v2/returns/rfbs/return-money", payload)

    async def list_claims(self, shop_id: str, limit: int = 50, last_id: int = 0, state: str = "ALL") -> dict[str, Any]:
        """List rFBS cancellation requests (claims).

        Uses /v2/conditional-cancellation/list.

        Args:
            shop_id: Shop identifier.
            limit: Items per page (max 500).
            last_id: Pagination cursor (cancellation_id of last item).
            state: Filter by state ("ALL", "ON_APPROVAL", etc.).

        Returns:
            Dict with cancellation requests.
        """
        return await self._direct_post(shop_id, "/v2/conditional-cancellation/list", {
            "filters": {"state": state},
            "limit": min(limit, 500),
            "last_id": last_id or None,
        })

    async def get_claim_info(self, shop_id: str, claim_id: int) -> dict[str, Any]:
        """Get rFBS cancellation request details.

        Uses /v2/conditional-cancellation/list filtered by posting_number.

        Args:
            shop_id: Shop identifier.
            claim_id: Cancellation request ID.

        Returns:
            Claim details.
        """
        return await self._direct_post(shop_id, "/v2/conditional-cancellation/list", {
            "filters": {"cancellation_initiator": []},
            "limit": 1,
            "last_id": claim_id,
        })

    async def approve_claim(self, shop_id: str, cancellation_id: int, comment: str = "") -> dict[str, Any]:
        """Approve an rFBS cancellation request.

        Args:
            shop_id: Shop identifier.
            cancellation_id: Cancellation request ID.
            comment: Optional comment.

        Returns:
            Result dict.
        """
        payload: dict[str, Any] = {"cancellation_id": cancellation_id}
        if comment:
            payload["comment"] = comment
        return await self._direct_post(shop_id, "/v2/conditional-cancellation/approve", payload)

    async def reject_claim(self, shop_id: str, cancellation_id: int, comment: str = "") -> dict[str, Any]:
        """Reject an rFBS cancellation request.

        Args:
            shop_id: Shop identifier.
            cancellation_id: Cancellation request ID.
            comment: Reason for rejection.

        Returns:
            Result dict.
        """
        payload: dict[str, Any] = {"cancellation_id": cancellation_id}
        if comment:
            payload["comment"] = comment
        return await self._direct_post(shop_id, "/v2/conditional-cancellation/reject", payload)

    async def confirm_receipt(self, shop_id: str, return_id: int) -> dict[str, Any]:
        """Confirm receipt of a returned product for check (rFBS).

        Args:
            shop_id: Shop identifier.
            return_id: Return ID.

        Returns:
            Result dict.
        """
        return await self._direct_post(shop_id, "/v2/returns/rfbs/receive-return", {
            "return_id": return_id,
        })

    # ============================================================
    # Finance Management (Phase 6)
    # ============================================================

    async def list_transactions(
        self,
        shop_id: str,
        from_date: str = "",
        to_date: str = "",
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        """List finance transactions.

        Args:
            shop_id: Shop identifier.
            from_date: Start date (ISO format).
            to_date: End date (ISO format).
            page: Page number.
            page_size: Items per page.

        Returns:
            Dict with transactions.
        """
        from datetime import datetime, timedelta
        filt: dict[str, Any] = {
            "date": {
                "from": from_date or (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "to": to_date or datetime.now().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            },
        }
        payload: dict[str, Any] = {
            "filter": filt,
            "page": page,
            "page_size": min(page_size, 1000),
        }
        return await self._direct_post(shop_id, "/v3/finance/transaction/list", payload)

    async def get_daily_realization(self, shop_id: str, day: int, month: int, year: int) -> dict[str, Any]:
        """Get daily sales realization report (Premium Plus).

        Uses /v1/finance/realization/by-day with day/month/year.

        Args:
            shop_id: Shop identifier.
            day: Day of month.
            month: Month (1-12).
            year: Year.

        Returns:
            Dict with daily rows.
        """
        return await self._direct_post(shop_id, "/v1/finance/realization/by-day", {
            "day": day,
            "month": month,
            "year": year,
        })

    async def get_realization(
        self,
        shop_id: str,
        month: int,
        year: int,
    ) -> dict[str, Any]:
        """Get monthly sales realization report.

        Uses /v2/finance/realization with month/year.

        Args:
            shop_id: Shop identifier.
            month: Month (1-12).
            year: Year.

        Returns:
            Dict with realization data (header + rows).
        """
        return await self._direct_post(shop_id, "/v2/finance/realization", {
            "month": month,
            "year": year,
        })

    # ============================================================
    # Chat Management (Phase 7)
    # ============================================================

    async def get_chat_history(self, shop_id: str, chat_id: str, limit: int = 50) -> dict[str, Any]:
        """Get chat message history (V3).

        Args:
            shop_id: Shop identifier.
            chat_id: Chat ID.
            limit: Max messages (max 1000).

        Returns:
            Dict with chat history (messages, has_next).
        """
        return await self._direct_post(shop_id, "/v3/chat/history", {
            "chat_id": chat_id,
            "limit": min(limit, 1000),
        })

    async def send_chat_message(self, shop_id: str, chat_id: str, text: str) -> dict[str, Any]:
        """Send a chat message to a buyer.

        Args:
            shop_id: Shop identifier.
            chat_id: Chat ID.
            text: Message text.

        Returns:
            Result dict.
        """
        return await self._direct_post(shop_id, "/v1/chat/send/message", {
            "chat_id": chat_id,
            "text": text,
        })

    async def send_chat_file(self, shop_id: str, chat_id: str, base64_content: str, file_name: str = "") -> dict[str, Any]:
        """Send a file in chat (base64 encoded).

        Args:
            shop_id: Shop identifier.
            chat_id: Chat ID.
            base64_content: File content as base64 string.
            file_name: File name with extension.

        Returns:
            Result dict.
        """
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "base64_content": base64_content,
        }
        if file_name:
            payload["name"] = file_name
        return await self._direct_post(shop_id, "/v1/chat/send/file", payload)

    async def list_unread_chats(self, shop_id: str, limit: int = 30, cursor: str = "") -> dict[str, Any]:
        """List chats with unread filter (V3).

        Args:
            shop_id: Shop identifier.
            limit: Max results (max 1000).
            cursor: Pagination cursor from previous response.

        Returns:
            Dict with chats, total_unread_count, cursor, has_next.
        """
        payload: dict[str, Any] = {
            "filter": {"unread_only": True},
            "limit": min(limit, 1000),
        }
        if cursor:
            payload["cursor"] = cursor
        return await self._direct_post(shop_id, "/v3/chat/list", payload)

    # ============================================================
    # Questions & Reviews (Phase 7)
    # ============================================================

    async def list_questions(
        self,
        shop_id: str,
        limit: int = 50,
        offset: int = 0,
        answered: bool | None = None,
    ) -> dict[str, Any]:
        """List product questions.

        Note: This endpoint is NOT available in the Ozon Seller API.
        The Ozon public API does not expose questions/Q&A endpoints.

        Args:
            shop_id: Shop identifier.
            limit: Items per page.
            offset: Pagination offset.
            answered: Filter by answered status.

        Returns:
            Error dict indicating unavailability.
        """
        return {"_error": "Questions API is not available in the Ozon Seller API. Questions/Q&A endpoints are not exposed by Ozon."}

    async def answer_question(self, shop_id: str, question_id: int, answer_text: str) -> dict[str, Any]:
        """Answer a product question.

        Note: This endpoint is NOT available in the Ozon Seller API.

        Args:
            shop_id: Shop identifier.
            question_id: Question ID.
            answer_text: Answer text.

        Returns:
            Error dict indicating unavailability.
        """
        return {"_error": "Questions API is not available in the Ozon Seller API."}

    async def delete_question(self, shop_id: str, question_id: int) -> dict[str, Any]:
        """Delete a product question.

        Note: This endpoint is NOT available in the Ozon Seller API.

        Args:
            shop_id: Shop identifier.
            question_id: Question ID.

        Returns:
            Error dict indicating unavailability.
        """
        return {"_error": "Questions API is not available in the Ozon Seller API."}

    async def list_reviews(
        self,
        shop_id: str,
        limit: int = 20,
        last_id: str = "",
        status: str = "ALL",
        sort_dir: str = "ASC",
    ) -> dict[str, Any]:
        """List product reviews (Premium Plus).

        Uses /v1/review/list with cursor-based pagination.

        Args:
            shop_id: Shop identifier.
            limit: Items per page (20-100).
            last_id: Cursor (last review ID from previous page).
            status: "ALL", "UNPROCESSED", or "PROCESSED".
            sort_dir: "ASC" or "DESC".

        Returns:
            Dict with reviews, has_next, last_id.
        """
        return await self._direct_post(shop_id, "/v1/review/list", {
            "limit": max(20, min(limit, 100)),
            "last_id": last_id,
            "status": status,
            "sort_dir": sort_dir,
        })

    async def reply_review(self, shop_id: str, review_id: str, reply_text: str, mark_as_processed: bool = True) -> dict[str, Any]:
        """Reply to a product review (Premium Plus).

        Uses /v1/review/comment/create.

        Args:
            shop_id: Shop identifier.
            review_id: Review ID (string UUID).
            reply_text: Reply text.
            mark_as_processed: Whether to mark review as processed.

        Returns:
            Dict with comment_id.
        """
        return await self._direct_post(shop_id, "/v1/review/comment/create", {
            "review_id": review_id,
            "text": reply_text,
            "mark_review_as_processed": mark_as_processed,
        })

    # ============================================================
    # Marketing / Promotions (Phase 7)
    # ============================================================

    async def list_actions(self, shop_id: str) -> dict[str, Any]:
        """List available marketing actions/promotions.

        Args:
            shop_id: Shop identifier.

        Returns:
            Dict with actions.
        """
        return await self._direct_get(shop_id, "/v1/actions")

    async def list_action_products(
        self,
        shop_id: str,
        action_id: int,
        limit: int = 50,
        offset: int = 0,
        last_id: str = "",
    ) -> dict[str, Any]:
        """List products in a marketing action.

        Uses POST /v1/actions/products with limit/offset/last_id pagination.

        Args:
            shop_id: Shop identifier.
            action_id: Action ID.
            limit: Items per page (max 1000).
            offset: Pagination offset.
            last_id: Cursor for pagination.

        Returns:
            Dict with products.
        """
        payload: dict[str, Any] = {
            "action_id": action_id,
            "limit": min(limit, 1000),
            "offset": offset,
        }
        if last_id:
            payload["last_id"] = last_id
        return await self._direct_post(shop_id, "/v1/actions/products", payload)

    async def register_action_products(
        self,
        shop_id: str,
        action_id: int,
        products: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Register products in a marketing action.

        Uses POST /v1/actions/products/activate.
        Each product must have: product_id (int), action_price (float), stock (int).

        Args:
            shop_id: Shop identifier.
            action_id: Action ID.
            products: List of {"product_id": int, "action_price": float, "stock": int}.

        Returns:
            Result dict.
        """
        return await self._direct_post(shop_id, "/v1/actions/products/activate", {
            "action_id": action_id,
            "products": products,
        })

    async def unregister_action_products(self, shop_id: str, action_id: int, product_ids: list[int]) -> dict[str, Any]:
        """Unregister products from a marketing action.

        Args:
            shop_id: Shop identifier.
            action_id: Action ID.
            product_ids: List of product IDs.

        Returns:
            Result dict.
        """
        return await self._direct_post(shop_id, "/v1/actions/products/deactivate", {
            "action_id": action_id,
            "product_ids": product_ids,
        })

    # ============ Ratings ============

    async def get_rating_summary(self, shop_id: str) -> dict[str, Any]:
        """Get current seller rating summary.

        Uses POST /v1/rating/summary.
        """
        return await self._direct_post(shop_id, "/v1/rating/summary", {})

    async def get_rating_history(self, shop_id: str, date_from: str = "", date_to: str = "") -> dict[str, Any]:
        """Get seller rating history for a period.

        Uses POST /v1/rating/history.

        Args:
            shop_id: Shop identifier.
            date_from: Start date (ISO format).
            date_to: End date (ISO format).
        """
        payload: dict[str, Any] = {}
        if date_from:
            payload["date_from"] = date_from
        if date_to:
            payload["date_to"] = date_to
        return await self._direct_post(shop_id, "/v1/rating/history", payload)

    # ============ Finance — Additional ============

    async def get_transaction_totals(self, shop_id: str, date_from: str = "", date_to: str = "") -> dict[str, Any]:
        """Get transaction totals summary.

        Uses POST /v3/finance/transaction/totals.
        Returns aggregates: accruals_for_sale, sale_commission, processing_and_delivery, etc.

        Args:
            shop_id: Shop identifier.
            date_from: Start date (ISO format).
            date_to: End date (ISO format).
        """
        payload: dict[str, Any] = {
            "filter": {"date": {}, "posting_number": "", "transaction_type": "all"},
        }
        if date_from:
            payload["filter"]["date"]["from"] = date_from
        if date_to:
            payload["filter"]["date"]["to"] = date_to
        return await self._direct_post(shop_id, "/v3/finance/transaction/totals", payload)

    async def get_cash_flow_statement(self, shop_id: str, date_from: str = "", date_to: str = "") -> dict[str, Any]:
        """Get cash flow statement.

        Uses POST /v1/finance/cash-flow-statement/list.
        """
        payload: dict[str, Any] = {}
        if date_from:
            payload["date_from"] = date_from
        if date_to:
            payload["date_to"] = date_to
        return await self._direct_post(shop_id, "/v1/finance/cash-flow-statement/list", payload)

    async def get_mutual_settlement(self, shop_id: str, date_from: str = "", date_to: str = "") -> dict[str, Any]:
        """Get mutual settlement report.

        Uses POST /v1/finance/mutual-settlement.
        """
        payload: dict[str, Any] = {}
        if date_from:
            payload["date_from"] = date_from
        if date_to:
            payload["date_to"] = date_to
        return await self._direct_post(shop_id, "/v1/finance/mutual-settlement", payload)

    async def get_compensation(self, shop_id: str, date_from: str = "", date_to: str = "") -> dict[str, Any]:
        """Get compensation report.

        Uses POST /v1/finance/compensation.
        """
        payload: dict[str, Any] = {}
        if date_from:
            payload["date_from"] = date_from
        if date_to:
            payload["date_to"] = date_to
        return await self._direct_post(shop_id, "/v1/finance/compensation", payload)

    async def get_products_buyout(self, shop_id: str, date_from: str = "", date_to: str = "") -> dict[str, Any]:
        """Get products buyout report.

        Uses POST /v1/finance/products/buyout.
        """
        payload: dict[str, Any] = {}
        if date_from:
            payload["date_from"] = date_from
        if date_to:
            payload["date_to"] = date_to
        return await self._direct_post(shop_id, "/v1/finance/products/buyout", payload)

    async def get_realization_posting(self, shop_id: str, month: int, year: int) -> dict[str, Any]:
        """Get sales realization report by posting (order-level detail).

        Uses POST /v1/finance/realization/posting.
        Returns per-order rows with order number, product, amounts.

        Args:
            shop_id: Shop identifier.
            month: Month (1-12).
            year: Year (e.g., 2026).
        """
        return await self._direct_post(shop_id, "/v1/finance/realization/posting", {
            "month": month,
            "year": year,
        })

    # ============ Analytics ============

    async def get_analytics_data(self, shop_id: str, metrics: list[str], dimension: list[str], date_from: str, date_to: str, limit: int = 1000, offset: int = 0) -> dict[str, Any]:
        """Get analytics data with specified metrics and dimensions.

        Uses POST /v1/analytics/data.
        Powerful endpoint — supports impressions, clicks, conversions, revenue, etc.
        Rate limit: 1 request/min per Client-Id.

        Args:
            shop_id: Shop identifier.
            metrics: List of metric codes (e.g., ["revenue", "ordered_units"]).
            dimension: List of dimension codes (e.g., ["sku", "day"]).
            date_from: Start date (YYYY-MM-DD).
            date_to: End date (YYYY-MM-DD).
            limit: Max results (1-1000).
            offset: Offset for pagination.
        """
        return await self._direct_post(shop_id, "/v1/analytics/data", {
            "metrics": metrics,
            "dimension": dimension,
            "date_from": date_from,
            "date_to": date_to,
            "limit": min(limit, 1000),
            "offset": offset,
        })

    async def get_product_queries(self, shop_id: str, date_from: str, date_to: str) -> dict[str, Any]:
        """Get product queries analytics (what buyers search for).

        Uses POST /v1/analytics/product-queries.
        """
        return await self._direct_post(shop_id, "/v1/analytics/product-queries", {
            "date_from": date_from,
            "date_to": date_to,
        })

    # ============ Ozon Async Reports ============

    async def create_ozon_report(self, shop_id: str, report_type: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Create an async report on Ozon side.

        Supported report_type values and their API paths:
        - "products" -> /v1/report/products/create
        - "returns"  -> /v2/report/returns/create
        - "postings" -> /v1/report/postings/create
        - "discounted" -> /v1/report/discounted/create
        - "stocks"   -> /v1/report/warehouse/stock

        Args:
            shop_id: Shop identifier.
            report_type: Type of report (products/returns/postings/discounted/stocks).
            params: Additional parameters for the specific report type.

        Returns:
            Dict with report code for status polling.
        """
        path_map = {
            "products": "/v1/report/products/create",
            "returns": "/v2/report/returns/create",
            "postings": "/v1/report/postings/create",
            "discounted": "/v1/report/discounted/create",
            "stocks": "/v1/report/warehouse/stock",
        }
        path = path_map.get(report_type)
        if not path:
            return {"_error": f"Unknown report type: {report_type}"}
        return await self._direct_post(shop_id, path, params or {})

    async def get_ozon_report(self, shop_id: str, report_code: str) -> dict[str, Any]:
        """Get async report status and download URL.

        Uses POST /v1/report/info.

        Args:
            shop_id: Shop identifier.
            report_code: Report code returned from create_ozon_report.

        Returns:
            Dict with status, file_url, etc.
        """
        return await self._direct_post(shop_id, "/v1/report/info", {
            "code": report_code,
        })

    async def list_ozon_reports(self, shop_id: str, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        """List previously generated reports.

        Uses POST /v1/report/list.

        Args:
            shop_id: Shop identifier.
            page: Page number.
            page_size: Items per page (max 200).
        """
        return await self._direct_post(shop_id, "/v1/report/list", {
            "page": page,
            "page_size": min(page_size, 200),
        })

    def _product_item_to_dict(self, item: Any) -> dict[str, Any]:
        """Convert product item to dict."""
        # Handle both vendor and installed versions
        result = {
            "product_id": getattr(item, 'product_id', None),
            "offer_id": getattr(item, 'offer_id', None),
            "archived": getattr(item, 'archived', False),
            "has_fbo_stocks": getattr(item, 'has_fbo_stocks', False),
            "has_fbs_stocks": getattr(item, 'has_fbs_stocks', False),
            "is_discounted": getattr(item, 'is_discounted', False),
            "name": getattr(item, 'name', None),
            "price": getattr(item, 'price', None),
            "old_price": getattr(item, 'old_price', None),
            "status": getattr(item, 'status', None),
            "visibility": getattr(item, 'visibility', None),
            "quantity": getattr(item, 'stocks', None),
            "images": getattr(item, 'images', []) or [],
        }
        return result

    def _product_info_to_dict(self, item: Any) -> dict[str, Any]:
        """Convert detailed product info (from product_info_list) to dict."""
        # Extract stocks info
        stocks_info = {}
        if hasattr(item, 'stocks') and item.stocks:
            stocks_info = {
                "has_stock": item.stocks.has_stock if hasattr(item.stocks, 'has_stock') else None,
                "stocks_detail": [
                    {"source": s.source, "present": s.present, "reserved": s.reserved}
                    for s in (item.stocks.stocks or [])
                ]
            }

        # Extract status info
        status_info = {}
        if hasattr(item, 'statuses') and item.statuses:
            status_info = {
                "status": getattr(item.statuses, 'status', None),
                "status_name": getattr(item.statuses, 'status_name', None),
                "is_created": getattr(item.statuses, 'is_created', None),
                "moderate_status": getattr(item.statuses, 'moderate_status', None),
                "validation_status": getattr(item.statuses, 'validation_status', None),
            }

        # Extract SKU from sources array
        sku = None
        if hasattr(item, 'sources') and item.sources:
            for src in item.sources:
                if hasattr(src, 'sku') and src.sku:
                    sku = src.sku
                    break

        # Extract total stock count
        total_stock = 0
        if stocks_info.get("stocks_detail"):
            total_stock = sum(s.get("present", 0) for s in stocks_info["stocks_detail"])

        return {
            "product_id": getattr(item, 'id', None),
            "offer_id": getattr(item, 'offer_id', None),
            "sku": sku,
            "name": getattr(item, 'name', None),
            "price": getattr(item, 'price', None),
            "old_price": getattr(item, 'old_price', None),
            "marketing_price": getattr(item, 'marketing_price', None),
            "vat": str(getattr(item, 'vat', '')) if hasattr(item, 'vat') else None,
            "currency_code": str(getattr(item, 'currency_code', '')) if hasattr(item, 'currency_code') else None,
            "barcodes": getattr(item, 'barcodes', None),
            "images": getattr(item, 'images', None) or [],
            "primary_image": getattr(item, 'primary_image', None),
            "color_image": getattr(item, 'color_image', None),
            "volume_weight": getattr(item, 'volume_weight', None),
            "category_id": getattr(item, 'description_category_id', None),
            "type_id": getattr(item, 'type_id', None),
            "created_at": str(getattr(item, 'created_at', '')) if hasattr(item, 'created_at') else None,
            "updated_at": str(getattr(item, 'updated_at', '')) if hasattr(item, 'updated_at') else None,
            "is_archived": getattr(item, 'is_archived', False),
            "is_discounted": getattr(item, 'is_discounted', False),
            "is_autoarchived": getattr(item, 'is_autoarchived', False),
            "is_kgt": getattr(item, 'is_kgt', False),
            "is_super": getattr(item, 'is_super', False),
            "is_prepayment_allowed": getattr(item, 'is_prepayment_allowed', False),
            "min_price": getattr(item, 'min_price', None),
            "volume_weight": getattr(item, 'volume_weight', None),
            "commissions": [
                {"sale_schema": c.sale_schema, "percent": c.percent, "value": c.value}
                for c in (getattr(item, 'commissions', []) or [])
            ],
            "stocks": stocks_info,
            "stock": total_stock,
            "status": status_info,
        }

    def _stock_analytics_to_dict(self, item: Any) -> dict[str, Any]:
        """Convert stock analytics item to dict."""
        return {
            "offer_id": item.offer_id,
            "sku": item.sku,
            "name": getattr(item, "name", ""),
            "ads": item.ads,
            "ads_cluster": getattr(item, "ads_cluster", None),
            "days_without_sales": item.days_without_sales,
            "days_without_sales_cluster": getattr(item, "days_without_sales_cluster", None),
            "turnover_grade": item.turnover_grade,
            "turnover_grade_cluster": getattr(item, "turnover_grade_cluster", None),
            "idc": item.idc,
            "idc_cluster": getattr(item, "idc_cluster", None),
            "available_stock_count": item.available_stock_count,
            "valid_stock_count": item.valid_stock_count,
        }

    def _posting_to_dict(self, item: Any) -> dict[str, Any]:
        """Convert posting to dict."""
        # Compute total from financial data
        total = 0
        if hasattr(item, "financial_data") and item.financial_data:
            total = sum(
                float(getattr(f, "total", 0) or 0)
                for f in item.financial_data
            )
        result = {
            "posting_number": getattr(item, "posting_number", str(getattr(item, "posting_id", ""))),
            "posting_id": item.posting_id,
            "order_id": item.order_id,
            "status": self._enum_val(item.status),
            "created_at": _dt_str(item.created_at),
            "total": total,
            "analytics_data": item.analytics_data.dict() if hasattr(item, "analytics_data") and item.analytics_data else {},
            "financial_data": [f.dict() for f in item.financial_data] if hasattr(item, "financial_data") else [],
        }

        # Products
        if hasattr(item, "products") and item.products:
            result["products"] = [
                {
                    "sku": getattr(p, "sku", ""),
                    "name": getattr(p, "name", ""),
                    "offer_id": getattr(p, "offer_id", ""),
                    "price": str(getattr(p, "price", "")),
                    "quantity": getattr(p, "quantity", 0),
                    "currency_code": self._enum_val(getattr(p, "currency_code", "")),
                }
                for p in item.products
            ]

        return result

    def _fbs_posting_to_dict(self, item: Any) -> dict[str, Any]:
        """Convert FBS posting (from list endpoint) to dict."""
        # Compute total from financial data
        total = 0
        if hasattr(item, "financial_data") and item.financial_data:
            total = sum(
                float(getattr(f, "total", 0) or 0)
                for f in item.financial_data
            )
        result = {
            "posting_number": getattr(item, "posting_number", ""),
            "order_id": getattr(item, "order_id", ""),
            "order_number": getattr(item, "order_number", ""),
            "status": self._enum_val(getattr(item, "status", "")),
            "substatus": self._enum_val(getattr(item, "substatus", "")),
            "created_at": _dt_str(getattr(item, "created_at", "")),
            "total": total,
            "in_process_at": _dt_str(getattr(item, "in_process_at", "")),
            "shipment_date": _dt_str(getattr(item, "shipment_date", "")),
            "delivering_date": _dt_str(getattr(item, "delivering_date", "")),
            "cancellation_reason": getattr(item, "cancellation", None).cancel_reason if hasattr(item, "cancellation") and item.cancellation else "",
            "is_express": getattr(item, "is_express", False),
            "is_multibox": getattr(item, "is_multibox", False),
            "tracking_number": getattr(item, "tracking_number", ""),
            "tpl_integration_type": self._enum_val(getattr(item, "tpl_integration_type", "")),
            "available_actions": [self._enum_val(a) for a in (getattr(item, "available_actions", []) or [])],
        }

        # Products
        if hasattr(item, "products") and item.products:
            result["products"] = [
                {
                    "sku": getattr(p, "sku", ""),
                    "name": getattr(p, "name", ""),
                    "offer_id": getattr(p, "offer_id", ""),
                    "price": str(getattr(p, "price", "")),
                    "quantity": getattr(p, "quantity", 0),
                    "currency_code": self._enum_val(getattr(p, "currency_code", "")),
                }
                for p in item.products
            ]

        # Analytics
        if hasattr(item, "analytics_data") and item.analytics_data:
            ad = item.analytics_data
            result["analytics"] = {
                "city": getattr(ad, "city", ""),
                "delivery_type": getattr(ad, "delivery_type", ""),
                "region": getattr(ad, "region", ""),
                "warehouse": getattr(ad, "warehouse", ""),
                "warehouse_id": getattr(ad, "warehouse_id", 0),
                "tpl_provider": getattr(ad, "tpl_provider", ""),
                "tpl_provider_id": getattr(ad, "tpl_provider_id", 0),
                "is_premium": getattr(ad, "is_premium", False),
            }

        # Delivery method
        if hasattr(item, "delivery_method") and item.delivery_method:
            dm = item.delivery_method
            result["delivery_method"] = {
                "id": getattr(dm, "id", 0),
                "name": getattr(dm, "name", ""),
                "tpl_provider": getattr(dm, "tpl_provider", ""),
                "tpl_provider_id": getattr(dm, "tpl_provider_id", 0),
                "warehouse": getattr(dm, "warehouse", ""),
                "warehouse_id": getattr(dm, "warehouse_id", 0),
            }

        # Tariffication
        if hasattr(item, "tariffication") and item.tariffication:
            t = item.tariffication
            result["tariffication"] = {
                "current_tariff_rate": getattr(t, "current_tariff_rate", 0),
                "current_tariff_type": getattr(t, "current_tariff_type", ""),
                "current_tariff_charge": str(getattr(t, "current_tariff_charge", "")),
                "current_tariff_charge_currency_code": getattr(t, "current_tariff_charge_currency_code", ""),
            }

        # Financial data — each PostingFinancialData has a products list
        if hasattr(item, "financial_data") and item.financial_data:
            fin_products = []
            for fd in item.financial_data:
                for p in getattr(fd, "products", []) or []:
                    fin_products.append({
                        "product_id": getattr(p, "product_id", ""),
                        "price": str(getattr(p, "price", "")),
                        "commission_amount": str(getattr(p, "commission_amount", "")),
                        "commission_percent": getattr(p, "commission_percent", 0),
                        "payout": str(getattr(p, "payout", "")),
                        "old_price": str(getattr(p, "old_price", "")),
                        "quantity": getattr(p, "quantity", 0),
                        "currency_code": self._enum_val(getattr(p, "currency_code", "")),
                    })
            result["financial_data"] = fin_products

        # Barcodes
        if hasattr(item, "barcodes") and item.barcodes:
            result["barcodes"] = [str(b) for b in item.barcodes]

        return result

    def _posting_full_to_dict(self, item: Any) -> dict[str, Any]:
        """Convert full posting detail (FBS get) to dict."""
        result = {
            "posting_number": getattr(item, "posting_number", ""),
            "order_id": getattr(item, "order_id", ""),
            "order_number": getattr(item, "order_number", ""),
            "status": self._enum_val(getattr(item, "status", "")),
            "substatus": self._enum_val(getattr(item, "substatus", "")),
            "created_at": _dt_str(getattr(item, "created_at", "")),
            "in_process_at": _dt_str(getattr(item, "in_process_at", "")),
            "shipment_date": _dt_str(getattr(item, "shipment_date", "")),
            "delivering_date": _dt_str(getattr(item, "delivering_date", "")),
            "cancellation_reason": getattr(item, "cancellation", None).cancel_reason if hasattr(item, "cancellation") and item.cancellation else "",
            "is_express": getattr(item, "is_express", False),
            "tracking_number": getattr(item, "tracking_number", ""),
            "provider_status": getattr(item, "provider_status", ""),
            "delivery_price": str(getattr(item, "delivery_price", "")),
            "tpl_integration_type": self._enum_val(getattr(item, "tpl_integration_type", "")),
            "available_actions": [self._enum_val(a) for a in (getattr(item, "available_actions", []) or [])],
        }

        # Products
        if hasattr(item, "products") and item.products:
            result["products"] = [
                {
                    "sku": getattr(p, "sku", ""),
                    "name": getattr(p, "name", ""),
                    "offer_id": getattr(p, "offer_id", ""),
                    "price": str(getattr(p, "price", "")),
                    "quantity": getattr(p, "quantity", 0),
                    "currency_code": self._enum_val(getattr(p, "currency_code", "")),
                }
                for p in item.products
            ]

        # Analytics
        if hasattr(item, "analytics_data") and item.analytics_data:
            ad = item.analytics_data
            result["analytics"] = {
                "city": getattr(ad, "city", ""),
                "delivery_type": getattr(ad, "delivery_type", ""),
                "region": getattr(ad, "region", ""),
                "warehouse": getattr(ad, "warehouse", ""),
                "warehouse_id": getattr(ad, "warehouse_id", 0),
                "tpl_provider": getattr(ad, "tpl_provider", ""),
                "tpl_provider_id": getattr(ad, "tpl_provider_id", 0),
                "is_premium": getattr(ad, "is_premium", False),
            }

        # Delivery method
        if hasattr(item, "delivery_method") and item.delivery_method:
            dm = item.delivery_method
            result["delivery_method"] = {
                "id": getattr(dm, "id", 0),
                "name": getattr(dm, "name", ""),
                "tpl_provider": getattr(dm, "tpl_provider", ""),
                "tpl_provider_id": getattr(dm, "tpl_provider_id", 0),
                "warehouse": getattr(dm, "warehouse", ""),
                "warehouse_id": getattr(dm, "warehouse_id", 0),
            }

        # Tariffication
        if hasattr(item, "tariffication") and item.tariffication:
            t = item.tariffication
            result["tariffication"] = {
                "current_tariff_rate": getattr(t, "current_tariff_rate", 0),
                "current_tariff_type": getattr(t, "current_tariff_type", ""),
                "current_tariff_charge": str(getattr(t, "current_tariff_charge", "")),
                "current_tariff_charge_currency_code": getattr(t, "current_tariff_charge_currency_code", ""),
            }

        # Financial data — each PostingFinancialData has a products list
        if hasattr(item, "financial_data") and item.financial_data:
            fin_products = []
            for fd in item.financial_data:
                for p in getattr(fd, "products", []) or []:
                    fin_products.append({
                        "product_id": getattr(p, "product_id", ""),
                        "price": str(getattr(p, "price", "")),
                        "commission_amount": str(getattr(p, "commission_amount", "")),
                        "commission_percent": getattr(p, "commission_percent", 0),
                        "payout": str(getattr(p, "payout", "")),
                        "old_price": str(getattr(p, "old_price", "")),
                        "quantity": getattr(p, "quantity", 0),
                        "currency_code": self._enum_val(getattr(p, "currency_code", "")),
                    })
            result["financial_data"] = fin_products

        # Barcodes
        if hasattr(item, "barcodes") and item.barcodes:
            result["barcodes"] = [str(b) for b in item.barcodes]

        return result

    def _warehouse_v2_to_dict(self, wh: dict[str, Any]) -> dict[str, Any]:
        """Convert v2 warehouse API response item to dict."""
        first_mile = wh.get("first_mile") or {}
        return {
            "warehouse_id": wh.get("warehouse_id"),
            "name": wh.get("name", ""),
            "status": wh.get("status", ""),
            "is_rfbs": wh.get("is_rfbs", False),
            "is_kgt": wh.get("is_kgt", False),
            "is_express": wh.get("is_express", False),
            "is_comfort": wh.get("is_comfort", False),
            "is_auto_assembly": wh.get("is_auto_assembly", False),
            "is_waybill_enabled": wh.get("is_waybill_enabled", False),
            "has_entrusted_acceptance": wh.get("has_entrusted_acceptance", False),
            "has_postings_limit": wh.get("has_postings_limit", False),
            "min_postings_limit": wh.get("min_postings_limit", 0),
            "postings_limit": wh.get("postings_limit", -1),
            "carriage_label_type": wh.get("carriage_label_type", ""),
            "warehouse_type": wh.get("warehouse_type", ""),
            "phone": wh.get("phone", ""),
            "courier_comment": wh.get("courier_comment", ""),
            "address": (wh.get("address_info") or {}).get("address", ""),
            "first_mile_type": first_mile.get("type", ""),
            "working_days": wh.get("working_days", []),
            "created_at": wh.get("created_at", ""),
            "updated_at": wh.get("updated_at", ""),
        }

    def _category_tree_to_dict(self, item: Any) -> dict[str, Any]:
        """Convert category tree item to dict recursively."""
        return {
            "description_category_id": item.description_category_id,
            "category_name": item.category_name,
            "disabled": item.disabled,
            "type_id": item.type_id,
            "type_name": item.type_name,
            "children": [
                self._category_tree_to_dict(child) for child in (item.children or [])
            ] if hasattr(item, 'children') else [],
        }

    def _category_attribute_to_dict(self, item: Any) -> dict[str, Any]:
        """Convert category attribute item to dict."""
        return {
            "id": item.id,
            "name": item.name,
            "description": item.description,
            "type": item.type,
            "is_required": item.is_required,
            "is_collection": item.is_collection,
            "is_aspect": item.is_aspect,
            "category_dependent": item.category_dependent,
            "dictionary_id": item.dictionary_id,
            "group_id": item.group_id,
            "group_name": item.group_name,
            "attribute_complex_id": item.attribute_complex_id,
            "max_value_count": item.max_value_count,
            "complex_is_collection": item.complex_is_collection,
        }

    def _attribute_value_to_dict(self, item: Any) -> dict[str, Any]:
        """Convert attribute dictionary value to dict."""
        return {
            "id": getattr(item, 'id', None),
            "value": getattr(item, 'value', None),
            "info": getattr(item, 'info', None),
        }


# Global client instance
_ozon_client: OzonClient | None = None


def get_ozon_client() -> OzonClient:
    """Get global OzonClient instance."""
    global _ozon_client
    if _ozon_client is None:
        _ozon_client = OzonClient()
    return _ozon_client
